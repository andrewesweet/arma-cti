"""Run the eval corpus: tasks against agent configurations, compared task by task (#617).

This repository verifies code at every layer — `just check` + `just unit` after every
edit, mutation smoke, the in-world probe corpus — and verifies prompts, briefs and
skills nowhere, though those are executable components a Process Change may edit
autonomously (#377's allowlist). This is the measurement half of #615: an operator
names a corpus and one or two configurations and gets a typed verdict per case, a
task-by-task comparison, and the cost of the run.

The subject is stochastic and the harness treats it that way. A trial is one sample; a
task's verdict is a rate over its repeats, judged against its tolerance. Four rules are
load-bearing rather than decorative:

- a task states its expected outcome as a **class**, its repeats and its tolerance; the
  verdict is a rate over the repeats, never a layout. What a failure class means is
  AGENTS.md's table's to say; this runner types outcomes, it does not restate semantics;
- a case whose outcomes spread beyond its tolerance is **quarantined with its
  reproduction baseline** — `flake_quarantine`'s discipline, applied to a stochastic
  subject;
- a trial stopped by budget, and an infrastructure failure, are recorded as exactly
  that and never as a failed configuration. Mistyping either makes the comparison's
  answer wrong rather than merely noisy;
- a metric with too few observations says so. The statistics #615 quotes — about
  ±17.5pp over 20 and ±11.1 over 50 independent tasks at a true rate of 80%, and 3/n
  where nothing fails — are **derived** from the case count here, never restated from
  prose, so the printed figures move with the corpus instead of drifting from it.

Two configurations are compared task by task and never netted: the per-case structure
survives into the output, so a change that fixes one case and breaks another shows
both. No aggregate rate is printed anywhere — the net is the least informative summary
available, and the corpus-level power statement is computed from case counts, never
from an average of rates.

What this is not: a judge of whether an expected outcome is the *right* expectation
(the corpus author's judgement, held to review), a model benchmark, or a causal claim.
A passing run says the corpus detected no regression, nothing more.

Isolation and integrity are criteria, not flavour, and the words say exactly what is
true. A trial is a fresh workspace holding only what the task declares, in a child
environment assembled from an allowlist that carries no lane variable, credential or
dispatch identity. **There is no sandbox.** The child runs as this user with its real
`HOME`, the proxy variables the allowlist carries, and the whole filesystem its user
can reach; a descendant that escapes its process group is not contained either. What
the runner does promise: graders are hash-verified, copied into the run directory —
outside every trial workspace, whose path never reaches the harness child — and
re-executed per trial from those verified bytes, so no grader module global carries
between trials or configurations; the wall-time budget is enforced over the trial's
whole process group; token and command ceilings are checked against what the adapter
reports after the trial, which is the only place those numbers exist; every trial
retains its workspace, its captured streams and its graded record, and nothing is
written twice; and a configuration may pin `pins.repo_sha`, which refuses the run on
any other HEAD, so a run is reproducible at the tree it measured. The child
interpreter is whatever the configuration's `argv[0]` resolves to against the
allowlisted `PATH`; the run records that resolution in `run.json`.

The task↔runner contract prints from this module (`--contract`), rendered from the same
field registries the loader validates against and the same severity table the run exits
with, so a key added there appears in the output and cannot drift —
`tools/probe_contract.py`'s shape, with the mutation `tests/unit/test_eval_contract.py`
plants to prove it is live.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR: Final = ROOT / "evals" / "corpus"
DEFAULT_RUNS_ROOT: Final = Path.home() / ".arma-cti" / "evals" / "runs"

TASK_SCHEMA: Final = "cti.eval-task/1"
MANIFEST_SCHEMA: Final = "cti.eval-corpus-manifest/1"
RUN_SCHEMA: Final = "cti.eval-run/1"
CONFIGURATION_SCHEMA: Final = "cti.eval-configuration/1"
TRIAL_RECORD_SCHEMA: Final = "cti.eval-trial-record/1"
GRADER_ENTRY: Final = "grade"

# Per-trial ceiling defaults. A task or a configuration overrides any leg; the defaults
# exist so a task that states none is still bounded rather than unbounded. Only the
# seconds leg is enforced — the runner kills the trial's process group at the deadline;
# the token and command legs are ceilings over what the adapter reports afterwards.
DEFAULT_BUDGET_SECONDS: Final = 900.0
DEFAULT_BUDGET_TOKENS: Final = 400_000
DEFAULT_BUDGET_COMMANDS: Final = 400

# The corpus statistics are derived, never restated from #615's prose: the half-width
# is the normal 95% interval at the reference rate, and the zero-failure bound is the
# rule of three. Move the reference rate and every printed figure follows it.
Z_95: Final = 1.96
POWER_REFERENCE_RATE: Final = 0.80
DEFAULT_MIN_CASES_FOR_CLAIM: Final = 20
REFUSAL_EXIT: Final = 6
MAX_CONFIGURATIONS: Final = 2

TRIAL_FILE: Final = "task.txt"
ADAPTER_RECORD: Final = "trial.json"
# A configuration's argv may carry this token; it expands to the repository root, so a
# committed configuration can name a shipped adapter without an absolute path.
REPO_TOKEN: Final = "{repo}"  # noqa: S105 — a path substitution token, not a credential


class EvalRefusalError(ValueError):
    """A typed refusal raised before any verdict exists.

    The kind is the machine-readable half; details name what was read. Raised only for
    inputs and integrity — never for a case outcome, which is a result.
    """

    def __init__(self, kind: str, details: tuple[str, ...] = ()) -> None:
        """Carry the kind and the details the report will print."""
        super().__init__(kind)
        self.kind = kind
        self.details = details


@dataclass(frozen=True)
class ContractField:
    """One field a document may carry, with the runner's own reason for it.

    The loader validates against these tuples and `--contract` renders from the same
    tuples, so a field added here is demanded and documented in one place — the drift
    `tools/probe_contract.py` exists to prevent, closed structurally.
    """

    name: str
    required: bool
    purpose: str


# Every key a task file may carry, and the one registry the loader and the contract
# both read. Adding a field here is what makes it real.
TASK_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("schema", True, f"exactly {TASK_SCHEMA}"),
    ContractField("id", True, "task identity, unique within the corpus"),
    ContractField("provenance", True, "the issue or commit this task grew from"),
    ContractField("prompt", True, "the self-contained work the harness is given"),
    ContractField("classes", True, "the outcome classes the grader may return"),
    ContractField("expected_class", True, "the class a good run produces, from classes"),
    ContractField("repeats", True, "independent trials per case, at least 1"),
    ContractField("tolerance", True, "allowed disagreement across repeats, 0.0 to 1.0"),
    ContractField("grader", True, "grader module path, relative to evals/"),
    ContractField("grader_sha256", True, "the grader's pinned sha256"),
    ContractField("title", False, "human-readable label"),
    ContractField("variants", False, "the ablation arms; default is one context-free arm"),
    ContractField(
        "budget",
        False,
        "per-trial ceiling override: seconds enforced; tokens and commands are"
        " ceilings over the adapter's post-trial report",
    ),
)

CONFIGURATION_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("schema", True, f"exactly {CONFIGURATION_SCHEMA}"),
    ContractField("name", True, "configuration identity, unique within the run"),
    ContractField(
        "harness.argv",
        True,
        "the adapter command, run inside the trial workspace;"
        f" {REPO_TOKEN} expands to the repository root",
    ),
    ContractField(
        "harness.env", False, "extra child environment entries; names recorded, never values"
    ),
    ContractField(
        "budget",
        False,
        "per-trial ceiling: seconds enforced; tokens and commands are ceilings"
        " over the adapter's post-trial report",
    ),
    ContractField("unit_costs", False, "currency reporting: input_per_1m, output_per_1m, currency"),
    ContractField("pins.repo_sha", False, "refuse the run unless HEAD is exactly this commit"),
)

ADAPTER_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("answer", True, "the harness's answer text, graded as written"),
    ContractField("stopped_by", True, "completed, budget or crash"),
    ContractField("tokens_in", True, "input tokens the harness reports, 0 when unknown"),
    ContractField("tokens_out", True, "output tokens the harness reports, 0 when unknown"),
    ContractField("commands", True, "tool commands the harness ran, 0 when unknown"),
    ContractField("harness", False, "the harness's self-description, recorded verbatim"),
)

GRADER_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("grade", True, "function: record -> {'class': str, 'note': str?}"),
)


class CaseState(StrEnum):
    """How a case's rate is classified.

    A case's verdict is its **rate** — `met` over its graded repeats, judged against
    the task's tolerance — and the state is that rate's classification, never a
    substitute for it. A rate exists only when every repeat graded: a case the budget
    touched is `budget_stopped`, no rate and no verdict, because a rate over a partial
    denominator is the measurement the specification forbids. `pass`, `fail`,
    `infra_unavailable` and `untyped_harness_failure` take their meaning from
    AGENTS.md's failure-class table and this output restates none of it; `quarantined`
    is `flake_quarantine`'s discipline carried by a case whose outcomes spread beyond
    their tolerance.
    """

    PASS = "pass"  # noqa: S105 — the class name, not a credential
    QUARANTINED = "quarantined"
    BUDGET_STOPPED = "budget_stopped"
    FAIL = "fail"
    INFRA_UNAVAILABLE = "infra_unavailable"
    UNTYPED_HARNESS_FAILURE = "untyped_harness_failure"


# Severity is also the exit code: the run exits on the worst class present, the probe
# corpus's own convention. These ranks are this runner's vocabulary for eval states;
# the names shared with the failure-class table keep their table meaning, never redefined.
CASE_SEVERITY: Final[dict[CaseState, int]] = {
    CaseState.PASS: 0,
    CaseState.QUARANTINED: 1,
    CaseState.BUDGET_STOPPED: 2,
    CaseState.FAIL: 3,
    CaseState.INFRA_UNAVAILABLE: 4,
    CaseState.UNTYPED_HARNESS_FAILURE: 5,
}


class TrialState(StrEnum):
    """One trial's state, before any case verdict exists.

    `graded_pending` is a record the oracle can read; `met` and `not_met` are its
    answers. The other three are the states that make a case not-a-result: a budget
    the trial hit, infrastructure that failed under it, and a harness that broke —
    each one exactly what AGENTS.md's failure-class table says it is.
    """

    GRADED_PENDING = "graded_pending"
    MET = "met"
    NOT_MET = "not_met"
    BUDGET_STOPPED = "budget_stopped"
    INFRA_UNAVAILABLE = "infra_unavailable"
    UNTYPED_HARNESS_FAILURE = "untyped_harness_failure"


# What the adapter's `stopped_by` may say, and what each answer costs the case.
STOPPED_COMPLETED: Final = "completed"
STOPPED_BY_BUDGET: Final = "budget"
STOPPED_BY_CRASH: Final = "crash"

# The child environment is an allowlist, not an inheritance: a lane variable such as
# ANTHROPIC_BASE_URL, a credential, or CTI_DISPATCH_ID must not reach an eval child,
# because a trial that inherits the orchestrator's identity is not a fresh environment.
# Anything else a harness needs is declared per configuration, names recorded only.
CHILD_ENV_ALLOWLIST: Final = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TZ",
    "USER",
    "SHELL",
    "TERM",
    "TMPDIR",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "https_proxy",
    "http_proxy",
    "no_proxy",
)


@dataclass(frozen=True)
class Variant:
    """One arm of a task: the context artefact the trial workspace is seeded with."""

    id: str
    file: Path | None  # corpus file copied into the workspace as the arm's context
    repo_file: str | None  # repository file copied at run time, its hash recorded


@dataclass(frozen=True)
class Budget:
    """The per-trial ceiling, named precisely because its legs are not equals.

    `seconds` is a budget the runner enforces: the trial's whole process group is
    killed at the deadline. `tokens` and `commands` are ceilings over what the
    adapter reports after the trial — self-reports are the only place those numbers
    exist, so a trial over either leg is recorded as a budget stop after the fact,
    never prevented. A descendant that escapes its process group (it calls
    `setsid` itself) evades the seconds leg too; nothing in this repository
    sandboxes children, and this module does not pretend otherwise.
    """

    seconds: float
    tokens: int
    commands: int


@dataclass(frozen=True)
class UnitCosts:
    """Declared per-million-token prices, the only source of a currency figure."""

    input_per_1m: float
    output_per_1m: float
    currency: str


@dataclass(frozen=True)
class Task:
    """One corpus task: the work, the expectation, and how it is graded."""

    id: str
    title: str
    provenance: str
    prompt: str
    classes: tuple[str, ...]
    expected_class: str
    repeats: int
    tolerance: float
    grader: Path
    grader_sha256: str
    variants: tuple[Variant, ...]
    budget: Budget | None

    @property
    def case_ids(self) -> list[str]:
        """Every case this task contributes, one per variant."""
        return [f"{self.id}/{variant.id}" for variant in self.variants]


@dataclass(frozen=True)
class Configuration:
    """One agent configuration: how the harness is invoked and what it may spend."""

    name: str
    path: Path
    argv: tuple[str, ...]
    env: dict[str, str]
    budget: Budget | None
    unit_costs: UnitCosts | None
    pins_repo_sha: str | None


@dataclass
class TrialOutcome:
    """One trial's result, before any rate exists."""

    index: str
    graded_class: str | None
    state: TrialState
    detail: str = ""
    reported: dict[str, int] | None = None  # the adapter's usage report, whatever the outcome


@dataclass
class CaseResult:
    """One case under one configuration: the rate, the state, and the evidence."""

    configuration: str
    case_id: str
    state: CaseState
    rate: float | None = None
    met: int = 0
    graded: int = 0
    budget_stops: int = 0
    not_a_result: int = 0
    classes_seen: dict[str, int] = field(default_factory=dict)
    under_powered: bool = False
    baseline: dict[str, object] | None = None
    wall_seconds: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    commands: int = 0
    currency_cost: float | None = None
    details: list[str] = field(default_factory=list)


def sha256_bytes(data: bytes) -> str:
    """Return the hex sha256 of `data`."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the hex sha256 of a file's bytes."""
    return sha256_bytes(path.read_bytes())


def verify_grader_hash(source: Path, expected_sha: str) -> None:
    """Refuse unless the grader on disk is the one its task pinned.

    Called before the run directory is even created, so a moved oracle refuses the run
    rather than being trusted with one — the integrity half of the grader criterion.
    """
    observed = sha256_file(source)
    if observed != expected_sha:
        raise EvalRefusalError(
            "grader_hash_mismatch",
            (f"grader={source.name}", f"expected={expected_sha}", f"observed={observed}"),
        )


def half_width(observations: int, rate: float = POWER_REFERENCE_RATE) -> float:
    """Return the 95% normal-approximation half-width at `rate` over `observations`.

    This is the whole of the corpus statistics: #615's ±17.5pp over 20 independent
    tasks and ±11.1 over 50, at the reference rate, come out of this one formula, so
    the printed power statement moves with the corpus instead of drifting from prose.
    """
    if observations <= 0:
        return float("inf")
    return Z_95 * math.sqrt(rate * (1.0 - rate) / observations)


def zero_failure_upper_bound(observations: int) -> float:
    """Return the rule of three: the 95% upper bound on failure probability at zero failures."""
    if observations <= 0:
        return 1.0
    return 3.0 / observations


def percentage(value: float) -> str:
    """Render a proportion as percentage points, one decimal."""
    return f"{value * 100:.1f}pp"


def _required(mapping: dict[str, object], key: str, label: str) -> object:
    """Read a required key, refusing with the document's label when absent."""
    if key not in mapping:
        raise EvalRefusalError("input_invalid", (f"missing={label}.{key}",))
    return mapping[key]


def _string(mapping: dict[str, object], key: str, label: str) -> str:
    """Read a required nonempty string field."""
    value = _required(mapping, key, label)
    if not isinstance(value, str) or not value:
        raise EvalRefusalError("input_invalid", (f"not_a_nonempty_string={label}.{key}",))
    return value


def _integer(mapping: dict[str, object], key: str, label: str, minimum: int) -> int:
    """Read a required integer field bounded below by `minimum`."""
    value = _required(mapping, key, label)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvalRefusalError(
            "input_invalid", (f"not_an_integer_above_{minimum - 1}={label}.{key}",)
        )
    return value


def _budget(mapping: object | None, label: str) -> Budget | None:
    """Read an optional budget block, each leg independently defaulted."""
    if mapping is None:
        return None
    if not isinstance(mapping, dict):
        raise EvalRefusalError("input_invalid", (f"budget_not_an_object={label}",))
    seconds = mapping.get("seconds", DEFAULT_BUDGET_SECONDS)
    tokens = mapping.get("tokens", DEFAULT_BUDGET_TOKENS)
    commands = mapping.get("commands", DEFAULT_BUDGET_COMMANDS)
    for name, value, floor in (
        ("seconds", seconds, 1.0),
        ("tokens", tokens, 1),
        ("commands", commands, 1),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < floor:
            raise EvalRefusalError("input_invalid", (f"budget_out_of_range={label}.{name}",))
    return Budget(float(seconds), int(tokens), int(commands))


def read_json(path: Path) -> dict[str, object]:
    """Read one JSON document, refusing anything that is not an object."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as failure:
        raise EvalRefusalError(
            "input_invalid", (f"unreadable={path}", f"error={failure}")
        ) from None
    if not isinstance(document, dict):
        raise EvalRefusalError("input_invalid", (f"not_an_object={path}",))
    return document


def load_manifest(corpus_dir: Path) -> dict[str, object]:
    """Read the optional corpus manifest; its keys are corpus-level, never per task."""
    path = corpus_dir / "corpus.json"
    if not path.exists():
        return {}
    document = read_json(path)
    if document.get("schema") != MANIFEST_SCHEMA:
        raise EvalRefusalError("input_invalid", (f"schema={path}",))
    return document


def _variants(document: dict[str, object], path: Path, repo_root: Path) -> tuple[Variant, ...]:
    """Read the task's arms; a task with none stated has one context-free arm."""
    raw = document.get("variants")
    if raw is None:
        return (Variant("default", None, None),)
    if not isinstance(raw, list) or not raw:
        raise EvalRefusalError("input_invalid", (f"variants_not_a_nonempty_list={path.name}",))
    variants: list[Variant] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise EvalRefusalError("input_invalid", (f"variant_not_an_object={path.name}",))
        variant_id = entry.get("id")
        if not isinstance(variant_id, str) or not variant_id:
            raise EvalRefusalError("input_invalid", (f"variant_id_invalid={path.name}",))
        file_value = entry.get("file")
        repo_value = entry.get("repo_file")
        if file_value is not None and repo_value is not None:
            raise EvalRefusalError(
                "input_invalid", (f"variant_two_sources={path.name}.{variant_id}",)
            )
        context: Path | None = None
        if isinstance(file_value, str):
            candidate = path.parent.parent / file_value
            if not candidate.is_file():
                raise EvalRefusalError("input_invalid", (f"variant_file_missing={file_value}",))
            context = candidate
        elif file_value is not None:
            raise EvalRefusalError(
                "input_invalid", (f"variant_file_not_a_path={path.name}.{variant_id}",)
            )
        repo_path: str | None = None
        if isinstance(repo_value, str):
            if not (repo_root / repo_value).is_file():
                raise EvalRefusalError("input_invalid", (f"repo_file_missing={repo_value}",))
            repo_path = repo_value
        elif repo_value is not None:
            raise EvalRefusalError(
                "input_invalid", (f"repo_file_not_a_path={path.name}.{variant_id}",)
            )
        variants.append(Variant(variant_id, context, repo_path))
    return tuple(variants)


def load_task(corpus_dir: Path, path: Path, repo_root: Path) -> Task:
    """Load and validate one task file against the runner's own field registry."""
    document = read_json(path)
    if document.get("schema") != TASK_SCHEMA:
        raise EvalRefusalError("input_invalid", (f"schema={path}",))
    for contract in TASK_FIELDS:
        if contract.required and contract.name not in document:
            raise EvalRefusalError("input_invalid", (f"missing={path.name}.{contract.name}",))
    classes = _required(document, "classes", path.name)
    if not isinstance(classes, list) or not classes:
        raise EvalRefusalError("input_invalid", (f"classes_not_a_list={path.name}",))
    if not all(isinstance(entry, str) for entry in classes):
        raise EvalRefusalError("input_invalid", (f"classes_not_strings={path.name}",))
    expected = _string(document, "expected_class", path.name)
    if expected not in classes:
        raise EvalRefusalError("input_invalid", (f"expected_class_not_in_classes={path.name}",))
    tolerance = _required(document, "tolerance", path.name)
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
        raise EvalRefusalError("input_invalid", (f"tolerance_not_a_number={path.name}",))
    if not 0.0 <= float(tolerance) <= 1.0:
        raise EvalRefusalError("input_invalid", (f"tolerance_out_of_range={path.name}",))
    return Task(
        id=_string(document, "id", path.name),
        title=str(document.get("title", "")),
        provenance=_string(document, "provenance", path.name),
        prompt=_string(document, "prompt", path.name),
        classes=tuple(str(entry) for entry in classes),
        expected_class=expected,
        repeats=_integer(document, "repeats", path.name, 1),
        tolerance=float(tolerance),
        grader=corpus_dir.parent / _string(document, "grader", path.name),
        grader_sha256=_string(document, "grader_sha256", path.name),
        variants=_variants(document, path, repo_root),
        budget=_budget(document.get("budget"), path.name),
    )


def load_corpus(corpus_dir: Path, repo_root: Path) -> tuple[list[Task], dict[str, object]]:
    """Load every task in the corpus directory, in name order."""
    if not corpus_dir.is_dir():
        raise EvalRefusalError("input_invalid", (f"corpus_dir_missing={corpus_dir}",))
    tasks = [
        load_task(corpus_dir, path, repo_root)
        for path in sorted(corpus_dir.glob("*.json"))
        if path.name != "corpus.json"
    ]
    if not tasks:
        raise EvalRefusalError("input_invalid", (f"corpus_empty={corpus_dir}",))
    ids = [task.id for task in tasks]
    if len(set(ids)) != len(ids):
        raise EvalRefusalError("input_invalid", (f"duplicate_task_id={corpus_dir}",))
    return tasks, load_manifest(corpus_dir)


def load_configuration(path: Path) -> Configuration:
    """Load and validate one configuration against the runner's own field registry."""
    document = read_json(path)
    if document.get("schema") != CONFIGURATION_SCHEMA:
        raise EvalRefusalError("input_invalid", (f"schema={path}",))
    for contract in CONFIGURATION_FIELDS:
        if not contract.required:
            continue
        parent, _, leaf = contract.name.partition(".")
        if leaf and parent in document:
            section = document[parent]
            if not isinstance(section, dict) or leaf not in section:
                raise EvalRefusalError("input_invalid", (f"missing={path.name}.{contract.name}",))
        elif contract.name not in document:
            raise EvalRefusalError("input_invalid", (f"missing={path.name}.{contract.name}",))
    harness = document.get("harness")
    if not isinstance(harness, dict) or not isinstance(harness.get("argv"), list):
        raise EvalRefusalError("input_invalid", (f"harness_not_an_object={path.name}",))
    argv = harness["argv"]
    if not argv or not all(isinstance(entry, str) for entry in argv):
        raise EvalRefusalError("input_invalid", (f"harness_argv_not_an_argv={path.name}",))
    env_raw = harness.get("env", {})
    if not isinstance(env_raw, dict) or not all(
        isinstance(name, str) and isinstance(value, str) for name, value in env_raw.items()
    ):
        raise EvalRefusalError("input_invalid", (f"harness_env_not_a_string_map={path.name}",))
    pins = document.get("pins")
    pins_repo_sha: str | None = None
    if pins is not None:
        if not isinstance(pins, dict):
            raise EvalRefusalError("input_invalid", (f"pins_not_an_object={path.name}",))
        pins_repo_sha = pins.get("repo_sha") or None
        if pins_repo_sha is not None and not isinstance(pins_repo_sha, str):
            raise EvalRefusalError("input_invalid", (f"pins_repo_sha_not_a_sha={path.name}",))
    unit_costs = document.get("unit_costs")
    costs: UnitCosts | None = None
    if unit_costs is not None:
        if not isinstance(unit_costs, dict):
            raise EvalRefusalError("input_invalid", (f"unit_costs_not_an_object={path.name}",))
        costs = UnitCosts(
            input_per_1m=float(unit_costs.get("input_per_1m", 0.0)),
            output_per_1m=float(unit_costs.get("output_per_1m", 0.0)),
            currency=str(unit_costs.get("currency", "USD")),
        )
    return Configuration(
        name=_string(document, "name", path.name),
        path=path,
        argv=tuple(argv),
        env=dict(env_raw),
        budget=_budget(document.get("budget"), path.name),
        unit_costs=costs,
        pins_repo_sha=pins_repo_sha,
    )


class Grader:
    """A hash-verified grader module, loaded from the run's own copy, fresh per call.

    The hash is verified before the module is loaded at all, so a grader that does
    not match what the task pinned is refused before any trial — the run is not
    trusted rather than graded with a moved oracle. The copy lives in the run
    directory, never a trial workspace, whose path never reaches the harness child.
    The module is re-executed for every `grade` call from those verified bytes, so a
    grader's module globals cannot carry state between trials, between variants, or
    between the two configurations of a comparison — the cross-trial contamination
    path a shared module object leaves open.
    """

    def __init__(self, source: Path, expected_sha: str, graders_dir: Path, name: str) -> None:
        """Verify the hash, copy into `graders_dir`, and load that copy once to check it."""
        verify_grader_hash(source, expected_sha)
        target = graders_dir / expected_sha[:12] / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        self._spec = importlib.util.spec_from_file_location(f"eval_grader_{name}", target)
        if self._spec is None or self._spec.loader is None:
            raise EvalRefusalError("grader_unloadable", (f"grader={source.name}",))
        entry = self._fresh_entry()
        if not callable(entry):
            raise EvalRefusalError(
                "grader_unloadable", (f"missing={GRADER_ENTRY}()", f"grader={source.name}")
            )
        self.name = name
        self.path = target
        self.sha256 = expected_sha

    def _fresh_entry(self) -> object:
        """Execute the verified bytes into a brand-new module and return its entry point.

        A grader that keeps module globals cannot leak one trial's state into the
        next: every call re-runs the module top level, so the only state that
        survives a call is whatever the grader wrote to disk itself.
        """
        module = importlib.util.module_from_spec(self._spec)
        self._spec.loader.exec_module(module)
        return getattr(module, GRADER_ENTRY, None)

    def grade(self, record: dict[str, object], classes: tuple[str, ...]) -> tuple[str, str]:
        """Return the class the grader assigns, refusing one outside the task's set.

        A grader that raises, or returns a class the task never declared, is a harness
        failure: the oracle broke, and a broken oracle's answer says nothing about the
        configuration.
        """
        entry = self._fresh_entry()
        try:
            verdict = entry(record)
        except Exception as failure:  # noqa: BLE001 — a grader crash is the harness's fault
            raise EvalRefusalError(
                "untyped_harness_failure", (f"grader={self.name}", f"error={failure!r}")
            ) from None
        if not isinstance(verdict, dict):
            raise EvalRefusalError(
                "untyped_harness_failure", (f"grader={self.name}", "verdict_not_an_object")
            )
        assigned = verdict.get("class")
        if not isinstance(assigned, str) or assigned not in classes:
            raise EvalRefusalError(
                "untyped_harness_failure",
                (f"grader={self.name}", f"class_not_in_task_vocabulary={assigned!r}"),
            )
        note = verdict.get("note", "")
        return assigned, note if isinstance(note, str) else ""


def effective_budget(task: Task, configuration: Configuration) -> Budget:
    """Resolve the trial's budget: task legs override configuration legs override defaults.

    Deliberately blunt about precedence: a task's stated leg wins whenever the task
    states that leg at all, and a leg the task leaves out falls to the configuration
    and then to the runner's defaults. A budget the operator cannot predict is worse
    than a blunt one.
    """
    budget = configuration.budget or Budget(
        DEFAULT_BUDGET_SECONDS, DEFAULT_BUDGET_TOKENS, DEFAULT_BUDGET_COMMANDS
    )
    if task.budget is None:
        return budget
    return Budget(
        task.budget.seconds if task.budget.seconds != DEFAULT_BUDGET_SECONDS else budget.seconds,
        task.budget.tokens if task.budget.tokens != DEFAULT_BUDGET_TOKENS else budget.tokens,
        task.budget.commands
        if task.budget.commands != DEFAULT_BUDGET_COMMANDS
        else budget.commands,
    )


def child_environment(configuration: Configuration) -> dict[str, str]:
    """Assemble the child environment: the allowlist plus the declared extras only.

    This is the seam that keeps an eval trial a fresh environment. A lane variable, a
    credential or CTI_DISPATCH_ID reaches a trial only if the configuration names it,
    and a configuration that names a lane secret is recorded — by name, never by value
    — in the run directory.
    """
    selected = {name: value for name, value in os.environ.items() if name in CHILD_ENV_ALLOWLIST}
    selected.update(configuration.env)
    return selected


def seed_workspace(
    workspace: Path,
    task: Task,
    variant: Variant,
    repo_root: Path,
) -> dict[str, object]:
    """Seed one fresh workspace with the prompt and the arm's context, if any.

    The workspace receives nothing else: no repository, no ledger, no state from any
    earlier trial — that is the isolation criterion, and what the workspace holds is
    recorded so the run shows its own arrangement.
    """
    workspace.mkdir(parents=True)
    (workspace / TRIAL_FILE).write_text(task.prompt, encoding="utf-8")
    seeded: dict[str, object] = {
        "prompt_file": TRIAL_FILE,
        "context": None,
        "context_sha256": None,
    }
    if variant.file is not None:
        target = workspace / variant.file.name
        target.write_bytes(variant.file.read_bytes())
        seeded = {
            "prompt_file": TRIAL_FILE,
            "context": variant.file.name,
            "context_sha256": sha256_file(variant.file),
        }
    if variant.repo_file is not None:
        source = repo_root / variant.repo_file
        target = workspace / Path(variant.repo_file).name
        target.write_bytes(source.read_bytes())
        seeded = {
            "prompt_file": TRIAL_FILE,
            "context": Path(variant.repo_file).name,
            "context_sha256": sha256_file(source),
        }
    return seeded


def execute_trial(
    task: Task,
    variant: Variant,
    configuration: Configuration,
    trial_dir: Path,
    repo_root: Path,
) -> tuple[TrialOutcome, dict[str, object] | None]:
    """Run one trial in a fresh workspace and return its outcome and its record.

    State is one of `graded_pending` (a record the grader can read), `budget_stopped`,
    `infra_unavailable` or `untyped_harness_failure`. Grading happens in `grade_trial`,
    never here: this half owns execution and isolation, that half owns the oracle.
    """
    workspace = trial_dir / "workspace"
    seeded = seed_workspace(workspace, task, variant, repo_root)
    budget = effective_budget(task, configuration)
    try:
        argv = [token.replace(REPO_TOKEN, str(repo_root)) for token in configuration.argv]
        completed = subprocess.run(  # noqa: S603 — argv is a validated configuration input
            argv,
            cwd=workspace,
            env=child_environment(configuration),
            capture_output=True,
            timeout=budget.seconds,
            check=False,
        )
        (trial_dir / "harness-stdout.txt").write_bytes(completed.stdout)
        (trial_dir / "harness-stderr.txt").write_bytes(completed.stderr)
        if completed.returncode != 0:
            return (
                TrialOutcome(
                    trial_dir.name,
                    None,
                    "infra_unavailable",
                    f"harness_exit={completed.returncode}",
                ),
                None,
            )
    except subprocess.TimeoutExpired:
        (trial_dir / "harness-timeout.txt").write_text(
            f"time budget {budget.seconds}s exhausted\n", encoding="utf-8"
        )
        return TrialOutcome(trial_dir.name, None, "budget_stopped", "budget=time"), None
    except OSError as failure:
        return (
            TrialOutcome(
                trial_dir.name,
                None,
                "infra_unavailable",
                f"harness_oserror={failure}",
            ),
            None,
        )
    return read_adapter_record(trial_dir, workspace, budget, seeded)


def read_adapter_record(
    trial_dir: Path,
    workspace: Path,
    budget: Budget,
    seeded: dict[str, object],
) -> tuple[TrialOutcome, dict[str, object] | None]:
    """Validate what the adapter wrote, typing every way it can be unusable."""
    record_path = workspace / ADAPTER_RECORD
    if not record_path.is_file():
        return (
            TrialOutcome(
                trial_dir.name,
                None,
                "untyped_harness_failure",
                f"missing={ADAPTER_RECORD}",
            ),
            None,
        )
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as failure:
        return (
            TrialOutcome(
                trial_dir.name,
                None,
                "untyped_harness_failure",
                f"record_unreadable={failure}",
            ),
            None,
        )
    if not isinstance(record, dict):
        return (
            TrialOutcome(trial_dir.name, None, "untyped_harness_failure", "record_not_an_object"),
            None,
        )
    for contract in ADAPTER_FIELDS:
        if contract.required and contract.name not in record:
            return (
                TrialOutcome(
                    trial_dir.name,
                    None,
                    "untyped_harness_failure",
                    f"missing={ADAPTER_RECORD}.{contract.name}",
                ),
                None,
            )
    return enforce_budget(trial_dir, record, budget, seeded)


def enforce_budget(
    trial_dir: Path,
    record: dict[str, object],
    budget: Budget,
    seeded: dict[str, object],
) -> tuple[TrialOutcome, dict[str, object] | None]:
    """Type a budget stop, an infra stop, or a usable record for grading."""
    stopped_by = record.get("stopped_by")
    if stopped_by not in (STOPPED_COMPLETED, STOPPED_BY_BUDGET, STOPPED_BY_CRASH):
        return (
            TrialOutcome(
                trial_dir.name, None, "untyped_harness_failure", f"stopped_by={stopped_by!r}"
            ),
            None,
        )
    tokens_in = int(record.get("tokens_in", 0))
    tokens_out = int(record.get("tokens_out", 0))
    commands = int(record.get("commands", 0))
    over_budget = tokens_in + tokens_out > budget.tokens or commands > budget.commands
    if stopped_by == STOPPED_BY_BUDGET or over_budget:
        reason = (
            record.get("stopped_by")
            if stopped_by == STOPPED_BY_BUDGET
            else "tokens"
            if tokens_in + tokens_out > budget.tokens
            else "commands"
        )
        return (
            TrialOutcome(trial_dir.name, None, "budget_stopped", f"budget={reason}"),
            None,
        )
    if stopped_by == STOPPED_BY_CRASH:
        return (
            TrialOutcome(trial_dir.name, None, "infra_unavailable", "harness=crashed"),
            None,
        )
    answer = record.get("answer")
    if not isinstance(answer, str):
        return (
            TrialOutcome(trial_dir.name, None, "untyped_harness_failure", "answer_not_a_string"),
            None,
        )
    record_out = dict(record)
    record_out["schema"] = TRIAL_RECORD_SCHEMA
    record_out["seeded"] = seeded
    (trial_dir / "record.json").write_text(
        json.dumps(record_out, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return TrialOutcome(trial_dir.name, None, "graded_pending", "record accepted"), record_out


def grade_trial(
    outcome: TrialOutcome,
    record: dict[str, object],
    grader: Grader,
    task: Task,
) -> TrialOutcome:
    """Grade one trial's answer and turn it into met/not_met."""
    assigned, note = grader.grade(record, task.classes)
    outcome.graded_class = assigned
    outcome.state = "met" if assigned == task.expected_class else "not_met"
    outcome.detail = f"class={assigned} note={note}".strip()
    return outcome


def aggregate_case(
    configuration_name: str,
    case_id: str,
    trials: list[TrialOutcome],
    expected_class: str,
    tolerance: float,
    usage: dict[str, float],
) -> CaseResult:
    """Turn a case's trials into its verdict: a rate over the graded repeats.

    The ladder's order is the criteria's order. An infrastructure or harness failure in
    any trial types the whole case not-a-result — never a failed configuration — and no
    rate is computed at all, because a partial measurement is not a measurement. Then a
    spread beyond tolerance quarantines the case with its reproduction baseline. Only a
    case whose trials agree within tolerance is judged on its rate, and a case the
    budget ended before it graded anything is a budget stop, never a fail.
    """
    result = CaseResult(configuration_name, case_id, CaseState.PASS)
    result.wall_seconds = usage["wall_seconds"]
    result.tokens_in = int(usage["tokens_in"])
    result.tokens_out = int(usage["tokens_out"])
    result.commands = int(usage["commands"])
    result.currency_cost = (
        float(usage["currency_cost"]) if usage.get("currency_cost") is not None else None
    )
    for trial in trials:
        if trial.state == "budget_stopped":
            result.budget_stops += 1
            result.details.append(f"trial={trial.index} budget_stopped {trial.detail}")
        elif trial.state in ("infra_unavailable", "untyped_harness_failure"):
            result.not_a_result += 1
            result.details.append(f"trial={trial.index} {trial.state} {trial.detail}")
        else:
            key = trial.graded_class or "?"
            result.classes_seen[key] = result.classes_seen.get(key, 0) + 1
    if result.not_a_result:
        result.state = (
            CaseState.UNTYPED_HARNESS_FAILURE
            if any(trial.state == "untyped_harness_failure" for trial in trials)
            else CaseState.INFRA_UNAVAILABLE
        )
        return result
    result.graded = sum(result.classes_seen.values())
    result.met = result.classes_seen.get(expected_class, 0)
    if result.graded == 0:
        result.state = CaseState.BUDGET_STOPPED
        result.details.append(
            f"budget_stops={result.budget_stops} graded=0 — no observation, no verdict"
        )
        return result
    dominant = max(result.classes_seen.values())
    disagreement = 1.0 - dominant / result.graded
    if disagreement > tolerance:
        result.state = CaseState.QUARANTINED
        result.baseline = {
            "arrangement": "fresh workspace per trial, one configuration, no state carried",
            "run_count": result.graded,
            "outcomes": [t.graded_class for t in trials if t.graded_class is not None],
            "disagreement": round(disagreement, 4),
            "tolerance": tolerance,
        }
        return result
    rate = result.met / result.graded
    result.under_powered = half_width(result.graded) > tolerance
    result.state = CaseState.PASS if rate >= 1.0 - tolerance else CaseState.FAIL
    result.details.append(
        f"rate={rate:.2f} met={result.met}/{result.graded} tolerance={tolerance}"
        f" half_width={percentage(half_width(result.graded))}"
    )
    return result


def currency_cost(configuration: Configuration, usage: dict[str, float]) -> float | None:
    """Return the run's currency cost, only when the configuration declared its prices."""
    if configuration.unit_costs is None:
        return None
    return (
        usage["tokens_in"] / 1_000_000 * configuration.unit_costs.input_per_1m
        + usage["tokens_out"] / 1_000_000 * configuration.unit_costs.output_per_1m
    )


def run_configuration(
    tasks: list[Task],
    configuration: Configuration,
    run_dir: Path,
    repo_root: Path,
    graders: dict[str, Grader],
) -> tuple[list[CaseResult], dict[str, float]]:
    """Run every case of every task under one configuration and total its cost."""
    config_dir = run_dir / "configurations" / configuration.name
    config_dir.mkdir(parents=True, exist_ok=True)
    results: list[CaseResult] = []
    totals = {
        "tokens_in": 0.0,
        "tokens_out": 0.0,
        "commands": 0.0,
        "wall_seconds": 0.0,
        "currency_cost": 0.0,
    }
    for task in tasks:
        for variant in task.variants:
            case_id = f"{task.id}/{variant.id}"
            case_dir = config_dir / case_id.replace("/", "__")
            trials: list[TrialOutcome] = []
            usage: dict[str, float] = {
                "wall_seconds": 0.0,
                "tokens_in": 0.0,
                "tokens_out": 0.0,
                "commands": 0.0,
                "currency_cost": 0.0,
            }
            for index in range(1, task.repeats + 1):
                started = datetime.now(UTC)
                trial_dir = case_dir / f"trial-{index:03d}"
                outcome, record = execute_trial(task, variant, configuration, trial_dir, repo_root)
                if outcome.state == "graded_pending":
                    outcome = grade_trial(outcome, record, graders[task.id], task)
                usage["wall_seconds"] += (datetime.now(UTC) - started).total_seconds()
                if outcome.graded_class is not None:
                    usage["tokens_in"] += int(record.get("tokens_in", 0))
                    usage["tokens_out"] += int(record.get("tokens_out", 0))
                    usage["commands"] += int(record.get("commands", 0))
                (trial_dir / "outcome.json").write_text(
                    json.dumps(
                        {
                            "index": outcome.index,
                            "state": outcome.state,
                            "graded_class": outcome.graded_class,
                            "detail": outcome.detail,
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
                trials.append(outcome)
            usage["currency_cost"] = currency_cost(configuration, usage) or 0.0
            results.append(
                aggregate_case(
                    configuration.name, case_id, trials, task.expected_class, task.tolerance, usage
                )
            )
            for key in totals:
                totals[key] += usage[key]
    return results, totals


def power_statement(independent_cases: int, min_cases_for_claim: int) -> list[str]:
    """Derive the corpus statistics from the case count, never from prose.

    These are the figures #615 states — about ±17.5pp over 20 independent tasks and
    ±11.1 over 50, at a true rate of 80%, and 3/n where nothing fails — computed here
    so they move with the corpus instead of drifting from prose.
    """
    supported = independent_cases >= min_cases_for_claim
    lines = [
        f"power: independent_cases={independent_cases}",
        (
            f"power: half_width n=20 {percentage(half_width(20))}"
            f" n=50 {percentage(half_width(50))}"
            f" at p={POWER_REFERENCE_RATE} (95% normal approximation)"
        ),
        (
            f"power: zero_failure_upper_bound=3/n n={independent_cases}"
            f" {percentage(zero_failure_upper_bound(independent_cases))}"
        ),
        (
            f"claim={'supported' if supported else 'not_supported'}"
            f" min_cases_for_claim={min_cases_for_claim}"
        ),
    ]
    if not supported:
        lines.append(
            "power: too few independent tasks to support a claim about a configuration;"
            " this corpus catches large regressions, proves the harness, and exposes"
            " qualitative failures — nothing finer"
        )
    return lines


def worst_state(results: list[CaseResult]) -> CaseState:
    """Return the worst class present, which is the run's exit code."""
    return max(results, key=lambda result: CASE_SEVERITY[result.state]).state


def toolchain_pin(repo_root: Path) -> dict[str, object]:
    """Record what produced the run: interpreter, runner bytes and tree identity."""
    return {
        "python": sys.version.split()[0],
        "runner_sha256": sha256_file(Path(__file__)),
        "head": git_head(repo_root),
    }


def git_head(repo_root: Path) -> str | None:
    """Return the repository HEAD, or None outside a repository."""
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607 — fixed command, the repository's own git
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def render_report(
    run_id: str,
    configurations: list[Configuration],
    per_configuration: dict[str, list[CaseResult]],
    totals: dict[str, dict[str, float]],
    independent_cases: int,
    min_cases_for_claim: int,
) -> str:
    """Render the human report: per case, per configuration, never netted."""
    lines = [f"eval_run={run_id} configurations={len(configurations)} cases={independent_cases}"]
    for configuration in configurations:
        counts: dict[str, int] = {}
        for result in per_configuration[configuration.name]:
            counts[result.state.value] = counts.get(result.state.value, 0) + 1
        summary = " ".join(f"{name}={counts[name]}" for name in sorted(counts))
        name_w = max(len(c.name) for c in configurations)
        case_count = len(per_configuration[configuration.name])
        lines.append(f"config={configuration.name:<{name_w}} cases={case_count} {summary}")
    for configuration in configurations:
        for result in per_configuration[configuration.name]:
            lines.append(
                f"case={result.case_id} config={result.configuration} state={result.state.value}"
                f" met={result.met}/{result.graded} budget_stops={result.budget_stops}"
                f" not_a_result={result.not_a_result}"
                f" under_powered={'yes' if result.under_powered else 'no'}"
            )
            lines.extend(f"  {detail}" for detail in result.details)
            if result.baseline is not None:
                lines.append(
                    f"  quarantined_baseline={json.dumps(result.baseline, sort_keys=True)}"
                )
    lines.extend(power_statement(independent_cases, min_cases_for_claim))
    for configuration in configurations:
        name = configuration.name
        cost_line = (
            f"cost: config={name} tokens_in={int(totals[name]['tokens_in'])}"
            f" tokens_out={int(totals[name]['tokens_out'])}"
            f" commands={int(totals[name]['commands'])}"
            f" wall_s={totals[name]['wall_seconds']:.1f}"
        )
        if configuration.unit_costs is not None:
            cost_line += (
                f" currency={totals[name]['currency_cost']:.4f} {configuration.unit_costs.currency}"
            )
        else:
            cost_line += " currency=unreported (no unit_costs declared)"
        lines.append(cost_line)
    if len(configurations) == MAX_CONFIGURATIONS:
        lines.append("comparison=task_by_task netted=no")
        first, second = configurations[0].name, configurations[1].name
        left = {result.case_id: result for result in per_configuration[first]}
        right = {result.case_id: result for result in per_configuration[second]}
        divergent = 0
        for case_id in sorted(left):
            differed = left[case_id].state != right[case_id].state
            divergent += 1 if differed else 0
            lines.append(
                f"pair={case_id} {first}={left[case_id].state.value}"
                f" {second}={right[case_id].state.value} divergent={'yes' if differed else 'no'}"
            )
        lines.append(f"divergent_cases={divergent}")
    worst = worst_state([r for results in per_configuration.values() for r in results])
    lines.append(f"worst_class={worst.value} exit={CASE_SEVERITY[worst]}")
    return "\n".join(lines) + "\n"


def render_contract() -> str:
    """Print the task↔runner contract from the registries the loader validates against.

    Everything here is derived from the tuples and enums above: a field, a state or an
    adapter key added to this module appears here without a second edit. What a failure
    class *means* is AGENTS.md's table's to say, and this output restates none of it.
    """
    lines = [
        "eval-corpus contract — derived from tools/eval_corpus.py",
        "",
        "Rendered from the same field registries, state enum and severity table the",
        "runner validates and exits with. If this module gains a field and this output",
        "does not name it, that is a bug (tests/unit/test_eval_contract.py plants it).",
        "",
        "=== Task file (schema " + TASK_SCHEMA + ") ===",
    ]
    lines.extend(_field_block(TASK_FIELDS))
    lines.extend(["", "=== Configuration file (schema " + CONFIGURATION_SCHEMA + ") ==="])
    lines.extend(_field_block(CONFIGURATION_FIELDS))
    interfaces = [
        "",
        "=== What the adapter owes the runner (written to " + ADAPTER_RECORD + " in its cwd) ===",
        "The adapter runs with cwd = a fresh trial workspace holding only `task.txt`",
        "(the prompt) and the arm's context file, if the task declares one. It inherits",
        f"an allowlisted environment ({', '.join(CHILD_ENV_ALLOWLIST)}) plus the",
        "configuration's harness.env entries — never a lane variable, a credential or a",
        "dispatch identity. Unknown record keys are ignored and retained verbatim.",
    ]
    lines.extend(interfaces)
    lines.extend(_field_block(ADAPTER_FIELDS))
    lines.extend(["", "=== What the grader owes the runner ==="])
    lines.extend(_field_block(GRADER_FIELDS))
    grader_block = [
        "",
        "A grader lives under evals/graders/, pinned by the task's grader_sha256, is",
        "copied into the run directory before any trial and imported from that copy —",
        "never from a trial workspace, whose path never reaches the harness child. A hash",
        "that does not match refuses the run before any trial; a class outside the task's",
        "`classes` is a harness failure, not a graded outcome.",
        "",
        "=== Verdict and exit codes ===",
        "A trial stopped by its budget, and an infrastructure failure, are recorded as",
        "exactly that. A case is a rate over its graded repeats; a spread beyond the",
        "task's tolerance quarantines it with its reproduction baseline. The run's exit",
        "code is the worst class present. What a failure class *means* — including for",
        "the names this runner shares with AGENTS.md's failure-class table — is the",
        "table's to say; this output restates none of it:",
    ]
    lines.extend(grader_block)
    lines.extend(f"  {CASE_SEVERITY[state]}  {state.value}" for state in CaseState)
    lines.extend(
        [
            f"  {REFUSAL_EXIT}  (refusal before any trial: input_invalid, grader_hash_mismatch,",
            "       pin_mismatch, run_dir_exists — never a verdict)",
            "=== Comparison ===",
            "One configuration runs the corpus alone (an ablation across its own variants).",
            "Two configurations are compared case by case; divergent cases are named and no",
            "aggregate rate is printed anywhere, so a change that fixes one case and breaks",
            "another shows both.",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the runner's arguments; `--contract` prints and exits before anything runs."""
    parser = argparse.ArgumentParser(
        description="Run the eval corpus against agent configurations, compared task by task.",
    )
    parser.add_argument("--contract", action="store_true", help="print the task↔runner contract")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_DIR, help="corpus directory")
    parser.add_argument(
        "--configuration",
        type=Path,
        action="append",
        required=False,
        help="a configuration file; one for a solo run, two for a pairwise comparison",
    )
    parser.add_argument(
        "--runs-root", type=Path, default=DEFAULT_RUNS_ROOT, help="run root directory"
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan and run nothing")
    return parser.parse_args(argv)


def print_refusal(refusal: EvalRefusalError, stage: str) -> None:
    """Print one refusal's typed lines to stderr; a refusal is never a verdict."""
    sys.stderr.write(f"refused={refusal.kind} stage={stage}\n")
    for detail in refusal.details:
        sys.stderr.write(f"  {detail}\n")


def print_plan(line: str) -> None:
    """Print one dry-run plan line to stdout."""
    sys.stdout.write(f"plan: {line}\n")


def prepare_run(
    args: argparse.Namespace,
) -> tuple[list[Configuration], list[Task], dict[str, object]]:
    """Validate every input before any trial exists.

    Integrity comes first on purpose: a grader whose hash does not match is refused
    before the run is trusted at all, and a pinned HEAD is checked before any trial,
    because a run that measured the wrong tree is not evidence of anything.
    """
    configurations = [load_configuration(path) for path in (args.configuration or [])]
    if not configurations or len(configurations) > MAX_CONFIGURATIONS:
        raise EvalRefusalError(
            "input_invalid", ("configurations=", "give one or two --configuration files")
        )
    names = {configuration.name for configuration in configurations}
    if len(names) != len(configurations):
        raise EvalRefusalError("input_invalid", ("duplicate_configuration_name=",))
    tasks, manifest = load_corpus(args.corpus, ROOT)
    for task in tasks:
        verify_grader_hash(task.grader, task.grader_sha256)
    for configuration in configurations:
        pin = configuration.pins_repo_sha
        if pin is not None and git_head(ROOT) != pin:
            raise EvalRefusalError(
                "pin_mismatch", (f"configuration={configuration.name}", f"expected={pin}")
            )
    return configurations, tasks, manifest


def main(argv: list[str] | None = None) -> int:
    """Run the corpus, write the run directory, and exit on the worst class."""
    args = parse_args(argv)
    if args.contract:
        sys.stdout.write(render_contract())
        return 0
    try:
        prepared = prepare_run(args)
    except EvalRefusalError as refusal:
        print_refusal(refusal, "before any trial")
        return REFUSAL_EXIT
    configurations, tasks, manifest = prepared
    independent_cases = sum(len(task.variants) for task in tasks)
    min_cases = int(manifest.get("min_cases_for_claim", DEFAULT_MIN_CASES_FOR_CLAIM))
    if args.dry_run:
        for configuration in configurations:
            for task in tasks:
                for variant in task.variants:
                    print_plan(
                        f"config={configuration.name} case={task.id}/{variant.id}"
                        f" repeats={task.repeats} tolerance={task.tolerance}"
                        f" expected={task.expected_class}"
                        f" budget={effective_budget(task, configuration)}"
                    )
        for line in power_statement(independent_cases, min_cases):
            print_plan(line)
        return 0
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = args.runs_root / run_id
    try:
        run_dir.mkdir(parents=True)
    except OSError:
        print_refusal(
            EvalRefusalError("run_dir_exists", (f"run_dir={run_dir}",)), "before any trial"
        )
        return REFUSAL_EXIT
    # The graders load after the dry-run branch and after the run directory exists, so
    # a dry run writes nothing at all and a real run's grader copies live beside its
    # evidence, hash-verified before any trial.
    graders = {
        task.id: Grader(task.grader, task.grader_sha256, args.runs_root / "graders", task.id)
        for task in tasks
    }
    per_configuration: dict[str, list[CaseResult]] = {}
    totals: dict[str, dict[str, float]] = {}
    for configuration in configurations:
        results, config_totals = run_configuration(tasks, configuration, run_dir, ROOT, graders)
        per_configuration[configuration.name] = results
        totals[configuration.name] = config_totals
    report = render_report(
        run_id, configurations, per_configuration, totals, independent_cases, min_cases
    )
    (run_dir / "report.txt").write_text(report, encoding="utf-8")
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "schema": RUN_SCHEMA,
                "run_id": run_id,
                "corpus": str(args.corpus),
                "toolchain": toolchain_pin(ROOT),
                "configurations": [c.name for c in configurations],
                "graders": {name: g.sha256 for name, g in graders.items()},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    sys.stdout.write(report)
    worst = worst_state([r for results in per_configuration.values() for r in results])
    return CASE_SEVERITY[worst]


if __name__ == "__main__":
    sys.exit(main())


def _field_block(fields: tuple[ContractField, ...]) -> list[str]:
    """Render one registry as the contract's field lines."""
    width = max(len(field.name) for field in fields)
    return [
        f"  {field.name:<{width}}  {'required' if field.required else 'optional '}  {field.purpose}"
        for field in fields
    ]
    """Render one registry as the contract's field lines."""
    width = max(len(field.name) for field in fields)
    return [
        f"  {field.name:<{width}}  {'required' if field.required else 'optional '}  {field.purpose}"
        for field in fields
    ]
