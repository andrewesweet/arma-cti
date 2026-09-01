"""Run the eval corpus: tasks against agent configurations, compared task by task (#617).

This repository verifies code at every layer — `just check` + `just unit` after every
edit, mutation smoke, the in-world probe corpus — and verifies prompts, briefs and
skills nowhere, though those are executable components a Process Change may edit
autonomously (#377's allowlist). This is the measurement half of #615: an operator
names a corpus and one or two configurations and gets a typed verdict per case, a
task-by-task comparison, and the cost of the run.

The subject is stochastic and the harness treats it that way. A trial is one sample; a
task's verdict is a rate over its graded answers, judged against its tolerance, with
unclassified answers reported separately. Four rules are
load-bearing rather than decorative:

- a task states its expected outcome as a **class**, its repeats and its tolerance; the
  verdict is a rate over graded answers, never a layout. What a failure class means is
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
true. A trial is a fresh bubblewrap workspace and PID boundary holding only what the
task declares, in a child environment assembled from an allowlist that carries no lane
variable, credential or dispatch identity. Host home, repository, temporary, runtime
and prior-run state are not mounted; descendants stay inside the trial boundary and
the runner's process group. The harness executable is resolved before the run,
content-hashed and mounted read-only, with the resolution recorded in `run.json`;
`pins.toolchain_sha256` can require an exact hash. Graders are hash-verified, copied
into that run directory — outside every trial workspace, whose path never reaches the
harness child — and re-executed per trial from those verified bytes, so no grader
module global carries between trials or configurations. The wall-time, token and
command budgets are enforced while the adapter runs from its live usage sidecar;
every trial retains its workspace, sidecar, captured streams and graded record, and
nothing is written twice. A configuration may pin `pins.repo_sha`, which refuses the
run on any other HEAD, so a run is reproducible at the tree it measured.

The task↔runner contract prints from this module (`--contract`), rendered from the same
field registries the loader validates against and the same severity table the run exits
with, so adding a key to a registry changes the contract and its validation together —
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
import re
import shutil
import signal
import subprocess
import sys
import threading
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
UNCLASSIFIED: Final = "unclassified"
TASK_CONFIGURATION_SCOPE: Final = "per-run"
USAGE_RECORD: Final = "usage.json"
SANDBOX_WORKSPACE: Final = "/work"
SANDBOX_INPUTS: Final = "/inputs"
SANDBOX_TOOLCHAIN: Final = "/toolchain"
SANDBOX_HOME: Final = "/home/eval"
SAFE_SYSTEM_PATH: Final = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
BWRAP_BINARY: Final = "bwrap"
SANDBOX_BIND_ROOTS: Final = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc")
SANDBOX_HIDDEN_ROOTS: Final = ("/home", "/root", "/tmp", "/var", "/run")  # noqa: S108 — mounts hide host state
IDENTIFIER_PATTERN: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
ENV_NAME_PATTERN: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
SHA256_PATTERN: Final = re.compile(r"[0-9a-fA-F]{64}\Z")

# Per-trial ceiling defaults. A task or a configuration overrides any leg; the defaults
# exist so a task that states none is still bounded rather than unbounded. The runner
# watches the adapter's usage sidecar and kills its process group at every ceiling.
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
ADAPTER_ENV_USAGE_FILE: Final = "CTI_EVAL_USAGE_FILE"
ADAPTER_ENV_TOKEN_BUDGET: Final = "CTI_EVAL_TOKEN_BUDGET"  # noqa: S105 — environment name, not a credential
ADAPTER_ENV_COMMAND_BUDGET: Final = "CTI_EVAL_COMMAND_BUDGET"
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
    ContractField(
        "configuration",
        True,
        f"configuration scope; must be {TASK_CONFIGURATION_SCOPE}, with the run "
        "naming the actual configuration",
    ),
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
        "per-trial ceiling override: seconds, tokens and commands enforced from live usage",
    ),
)

VARIANT_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("id", True, "variant identity, unique within its task"),
    ContractField("file", False, "corpus stimulus copied into the trial workspace"),
    ContractField("repo_file", False, "repository stimulus copied at run time and hash recorded"),
    ContractField(
        "derived_from",
        False,
        "object with repo_file and sha256 pin for a frozen reduction; stale source refuses",
    ),
)

BUDGET_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("seconds", False, "wall-time ceiling, enforced by the runner"),
    ContractField("tokens", False, "token ceiling, enforced from the live usage sidecar"),
    ContractField("commands", False, "command ceiling, enforced from the live usage sidecar"),
)

UNIT_COST_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("input_per_1m", False, "currency cost per million input tokens; defaults to 0"),
    ContractField("output_per_1m", False, "currency cost per million output tokens; defaults to 0"),
    ContractField("currency", False, "currency code or label; defaults to USD"),
)

PIN_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("repo_sha", False, "exact repository HEAD required before the run"),
    ContractField(
        "toolchain_sha256",
        False,
        "optional exact hash for the executable resolved from harness.argv[0]",
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
        "per-trial ceiling: seconds, tokens and commands enforced from live usage",
    ),
    ContractField("unit_costs", False, "currency reporting: input_per_1m, output_per_1m, currency"),
    ContractField("pins.repo_sha", False, "refuse the run unless HEAD is exactly this commit"),
    ContractField(
        "pins.toolchain_sha256",
        False,
        "refuse the run unless the resolved harness executable has this sha256",
    ),
)

ADAPTER_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("answer", True, "the harness's answer text, graded as written"),
    ContractField("stopped_by", True, "completed, budget or crash"),
    ContractField("tokens_in", True, f"input tokens; must exactly equal {USAGE_RECORD}.tokens_in"),
    ContractField(
        "tokens_out", True, f"output tokens; must exactly equal {USAGE_RECORD}.tokens_out"
    ),
    ContractField("commands", True, f"tool commands; must exactly equal {USAGE_RECORD}.commands"),
    ContractField("harness", False, "the harness's self-description, recorded verbatim"),
)

ADAPTER_ENV_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField(
        ADAPTER_ENV_USAGE_FILE,
        True,
        f"absolute sandbox path where the adapter atomically updates {USAGE_RECORD}",
    ),
    ContractField(
        ADAPTER_ENV_TOKEN_BUDGET,
        True,
        "runner-owned token ceiling; the adapter may read it but cannot change it",
    ),
    ContractField(
        ADAPTER_ENV_COMMAND_BUDGET,
        True,
        "runner-owned command ceiling; the adapter may read it but cannot change it",
    ),
)

USAGE_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("tokens_in", True, "cumulative input tokens, updated while the adapter runs"),
    ContractField("tokens_out", True, "cumulative output tokens, updated while the adapter runs"),
    ContractField("commands", True, "cumulative tool commands, updated while the adapter runs"),
)

GRADER_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("grade", True, "function: record -> {'class': str, 'note': str?}"),
)

CASE_FIELDS: Final[tuple[ContractField, ...]] = (
    ContractField("task.id", True, "task identity carried into every materialized case"),
    ContractField("task.provenance", True, "task provenance carried into every materialized case"),
    ContractField("configuration", True, "actual configuration under test"),
    ContractField("variant", True, "ablation arm under test"),
)

CONTRACT_REGISTRIES: Final[tuple[tuple[str, tuple[ContractField, ...]], ...]] = (
    ("task", TASK_FIELDS),
    ("variant", VARIANT_FIELDS),
    ("budget", BUDGET_FIELDS),
    ("unit_costs", UNIT_COST_FIELDS),
    ("pins", PIN_FIELDS),
    ("configuration", CONFIGURATION_FIELDS),
    ("adapter_environment", ADAPTER_ENV_FIELDS),
    ("adapter", ADAPTER_FIELDS),
    ("usage", USAGE_FIELDS),
    ("grader", GRADER_FIELDS),
    ("case", CASE_FIELDS),
)


class CaseState(StrEnum):
    """How a case's rate is classified.

    A case's verdict is its **rate** — `met` over the graded repeats, judged against
    the task's tolerance — and this enum is that rate's status. `unclassified` answers
    are counted separately and make an otherwise passing case visible as incomplete.
    A rate exists only when every repeat completed, even when some completed answers
    were unclassified. Infrastructure and harness failures remain typed not-a-result;
    `quarantined` carries the `flake_quarantine` discipline.
    """

    WITHIN_TOLERANCE = "within_tolerance"
    UNCLASSIFIED = "unclassified"
    QUARANTINED = "quarantined"
    BUDGET_STOPPED = "budget_stopped"
    OUTSIDE_TOLERANCE = "outside_tolerance"
    INFRA_UNAVAILABLE = "infra_unavailable"
    UNTYPED_HARNESS_FAILURE = "untyped_harness_failure"


# Severity is also the exit code: the run exits on the worst class present, the probe
# corpus's own convention. These ranks are this runner's vocabulary for eval states;
# the names shared with the failure-class table keep their table meaning, never redefined.
CASE_SEVERITY: Final[dict[CaseState, int]] = {
    CaseState.WITHIN_TOLERANCE: 0,
    CaseState.UNCLASSIFIED: 1,
    CaseState.QUARANTINED: 1,
    CaseState.BUDGET_STOPPED: 2,
    CaseState.OUTSIDE_TOLERANCE: 3,
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
    "LANG",
    "LC_ALL",
    "TZ",
    "USER",
    "SHELL",
    "TERM",
)
FORBIDDEN_ENV_NAMES: Final = frozenset(
    {
        "HOME",
        "PATH",
        "TMPDIR",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "CTI_DISPATCH_ID",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "FTP_PROXY",
        "SSH_AUTH_SOCK",
        "BASH_ENV",
        "ENV",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    }
)
FORBIDDEN_ENV_MARKERS: Final = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


@dataclass(frozen=True)
class Variant:
    """One arm of a task: the context artefact the trial workspace is seeded with."""

    id: str
    file: Path | None  # corpus file copied into the workspace as the arm's context
    repo_file: str | None  # repository file copied at run time, its hash recorded
    derived_from_repo_file: str | None = None  # source of a frozen reduction
    derived_from_sha256: str | None = None  # digest pinned for that source


@dataclass(frozen=True)
class Budget:
    """The fully resolved per-trial ceiling enforced by the runner."""

    seconds: float
    tokens: int
    commands: int


@dataclass(frozen=True)
class BudgetSpec:
    """An optional budget override, retaining which legs the document stated."""

    seconds: float | None
    tokens: int | None
    commands: int | None


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
    budget: BudgetSpec | None
    configuration: str = TASK_CONFIGURATION_SCOPE

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
    budget: BudgetSpec | None
    unit_costs: UnitCosts | None
    pins_repo_sha: str | None
    pins_toolchain_sha256: str | None = None


@dataclass(frozen=True)
class Toolchain:
    """Executable identity pinned for one run and checked before each trial."""

    requested: str
    resolved: Path
    sha256: str
    sandbox_path: str
    version: str
    root: Path | None = None


@dataclass
class TrialOutcome:
    """One trial's result, before any rate exists."""

    index: str
    graded_class: str | None
    state: TrialState
    detail: str = ""
    reported: dict[str, int] | None = None  # live usage, whatever the outcome


@dataclass
class CaseResult:
    """One case under one configuration: the rate, the state, and the evidence."""

    configuration: str
    case_id: str
    state: CaseState
    task_id: str = ""
    task_provenance: str = ""
    variant_id: str = ""
    expected_class: str = ""
    tolerance: float = 0.0
    rate: float | None = None
    met: int = 0
    graded: int = 0
    unclassified: int = 0
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


def _identifier(value: object, label: str) -> str:
    """Read a path-safe identity used as a durable directory component."""
    if not isinstance(value, str) or not value or IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise EvalRefusalError("input_invalid", (f"identifier_invalid={label}",))
    return value


def _sha256(value: object, label: str) -> str:
    """Read a lowercase-or-uppercase sha256 string."""
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise EvalRefusalError("input_invalid", (f"sha256_invalid={label}",))
    return value.lower()


def _confined_path(root: Path, value: str, label: str) -> Path:
    """Resolve a declared path and refuse it if it escapes `root`."""
    root_resolved = root.resolve()
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        raise EvalRefusalError("input_invalid", (f"path_outside_root={label}",)) from None
    return candidate


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


def _require_registry_fields(
    mapping: dict[str, object], fields: tuple[ContractField, ...], label: str
) -> None:
    """Require the fields marked required by one contract registry."""
    for contract in fields:
        if not contract.required:
            continue
        parent, separator, leaf = contract.name.partition(".")
        if separator:
            section = mapping.get(parent)
            present = isinstance(section, dict) and leaf in section
        else:
            present = contract.name in mapping
        if not present:
            raise EvalRefusalError("input_invalid", (f"missing={label}.{contract.name}",))


def _integer(mapping: dict[str, object], key: str, label: str, minimum: int) -> int:
    """Read a required integer field bounded below by `minimum`."""
    value = _required(mapping, key, label)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvalRefusalError(
            "input_invalid", (f"not_an_integer_above_{minimum - 1}={label}.{key}",)
        )
    return value


def _budget(mapping: object | None, label: str) -> BudgetSpec | None:
    """Read an optional budget block without losing which legs were stated."""
    if mapping is None:
        return None
    if not isinstance(mapping, dict):
        raise EvalRefusalError("input_invalid", (f"budget_not_an_object={label}",))
    values: dict[str, float | int | None] = {
        "seconds": mapping.get("seconds"),
        "tokens": mapping.get("tokens"),
        "commands": mapping.get("commands"),
    }
    for name, value, floor in (
        ("seconds", values["seconds"], 1.0),
        ("tokens", values["tokens"], 1),
        ("commands", values["commands"], 1),
    ):
        if value is None:
            continue
        valid_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if name == "seconds":
            valid_number = valid_number and math.isfinite(float(value))
        else:
            valid_number = valid_number and isinstance(value, int)
        if not valid_number or value < floor:
            raise EvalRefusalError("input_invalid", (f"budget_out_of_range={label}.{name}",))
    return BudgetSpec(
        float(values["seconds"]) if values["seconds"] is not None else None,
        int(values["tokens"]) if values["tokens"] is not None else None,
        int(values["commands"]) if values["commands"] is not None else None,
    )


def _budget_override(
    spec: BudgetSpec | Budget | None, name: str, default: float
) -> float | int | None:
    """Return one stated override, treating legacy full defaults as omitted."""
    if spec is None:
        return None
    value = getattr(spec, name)
    if value is None:
        return None
    # Budget was the public fixture type before partial overrides existed. Its
    # default-valued legs represented omission; BudgetSpec preserves an explicit
    # default and therefore takes the normal path below.
    if isinstance(spec, Budget) and value == default:
        return None
    return value


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
    minimum = document.get("min_cases_for_claim", DEFAULT_MIN_CASES_FOR_CLAIM)
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise EvalRefusalError("input_invalid", (f"min_cases_for_claim_invalid={path}",))
    return document


def _derived_source(
    entry: dict[str, object],
    path: Path,
    variant_id: str,
    context: Path | None,
    repo_path: str | None,
    repo_root: Path,
) -> tuple[str | None, str | None]:
    """Read a frozen reduction's pinned repository source, if it has one."""
    derived_value = entry.get("derived_from")
    if derived_value is None:
        return None, None
    if not isinstance(derived_value, dict):
        raise EvalRefusalError(
            "input_invalid", (f"derived_from_not_an_object={path.name}.{variant_id}",)
        )
    if context is None or repo_path is not None:
        raise EvalRefusalError(
            "input_invalid", (f"derived_from_requires_frozen_file={path.name}.{variant_id}",)
        )
    source_value = _string(derived_value, "repo_file", f"{path.name}.{variant_id}.derived_from")
    _confined_path(repo_root, source_value, f"{path.name}.{variant_id}.derived_from.repo_file")
    expected_sha256 = _sha256(
        _required(derived_value, "sha256", f"{path.name}.{variant_id}.derived_from"),
        f"{path.name}.{variant_id}.derived_from.sha256",
    )
    return source_value, expected_sha256


def _variants(document: dict[str, object], path: Path, repo_root: Path) -> tuple[Variant, ...]:
    """Read the task's arms; a task with none stated has one context-free arm."""
    raw = document.get("variants")
    if raw is None:
        return (Variant("default", None, None),)
    if not isinstance(raw, list) or not raw:
        raise EvalRefusalError("input_invalid", (f"variants_not_a_nonempty_list={path.name}",))
    variants: list[Variant] = []
    variant_ids: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise EvalRefusalError("input_invalid", (f"variant_not_an_object={path.name}",))
        _require_registry_fields(entry, VARIANT_FIELDS, f"{path.name}.variant")
        raw_variant_id = entry.get("id")
        if (
            not isinstance(raw_variant_id, str)
            or not raw_variant_id
            or IDENTIFIER_PATTERN.fullmatch(raw_variant_id) is None
        ):
            raise EvalRefusalError("input_invalid", (f"variant_id_invalid={path.name}",))
        variant_id = raw_variant_id
        if variant_id in variant_ids:
            raise EvalRefusalError(
                "input_invalid", (f"duplicate_variant_id={path.name}.{variant_id}",)
            )
        variant_ids.add(variant_id)
        file_value = entry.get("file")
        repo_value = entry.get("repo_file")
        if file_value is not None and repo_value is not None:
            raise EvalRefusalError(
                "input_invalid", (f"variant_two_sources={path.name}.{variant_id}",)
            )
        context: Path | None = None
        if isinstance(file_value, str):
            candidate = _confined_path(path.parent.parent, file_value, f"{path.name}.file")
            if not candidate.is_file():
                raise EvalRefusalError("input_invalid", (f"variant_file_missing={file_value}",))
            if candidate.name in {TRIAL_FILE, ADAPTER_RECORD, USAGE_RECORD}:
                raise EvalRefusalError("input_invalid", (f"variant_file_reserved={file_value}",))
            context = candidate
        elif file_value is not None:
            raise EvalRefusalError(
                "input_invalid", (f"variant_file_not_a_path={path.name}.{variant_id}",)
            )
        repo_path: str | None = None
        if isinstance(repo_value, str):
            candidate = _confined_path(repo_root, repo_value, f"{path.name}.repo_file")
            if not candidate.is_file():
                raise EvalRefusalError("input_invalid", (f"repo_file_missing={repo_value}",))
            if candidate.name in {TRIAL_FILE, ADAPTER_RECORD, USAGE_RECORD}:
                raise EvalRefusalError("input_invalid", (f"repo_file_reserved={repo_value}",))
            repo_path = repo_value
        elif repo_value is not None:
            raise EvalRefusalError(
                "input_invalid", (f"repo_file_not_a_path={path.name}.{variant_id}",)
            )
        derived_repo_path, derived_sha256 = _derived_source(
            entry, path, variant_id, context, repo_path, repo_root
        )
        variants.append(Variant(variant_id, context, repo_path, derived_repo_path, derived_sha256))
    return tuple(variants)


def load_task(corpus_dir: Path, path: Path, repo_root: Path) -> Task:
    """Load and validate one task file against the runner's own field registry."""
    document = read_json(path)
    if document.get("schema") != TASK_SCHEMA:
        raise EvalRefusalError("input_invalid", (f"schema={path}",))
    _require_registry_fields(document, TASK_FIELDS, path.name)
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
    configuration = _string(document, "configuration", path.name)
    if configuration != TASK_CONFIGURATION_SCOPE:
        raise EvalRefusalError("input_invalid", (f"configuration_scope_invalid={path.name}"))
    return Task(
        id=_identifier(document.get("id"), f"{path.name}.id"),
        title=str(document.get("title", "")),
        provenance=_string(document, "provenance", path.name),
        prompt=_string(document, "prompt", path.name),
        classes=tuple(str(entry) for entry in classes),
        expected_class=expected,
        repeats=_integer(document, "repeats", path.name, 1),
        tolerance=float(tolerance),
        grader=_confined_path(
            corpus_dir.parent, _string(document, "grader", path.name), f"{path.name}.grader"
        ),
        grader_sha256=_sha256(_string(document, "grader_sha256", path.name), path.name),
        variants=_variants(document, path, repo_root),
        budget=_budget(document.get("budget"), path.name),
        configuration=configuration,
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


def verify_context_pins(tasks: list[Task], repo_root: Path) -> None:
    """Verify frozen reductions against live sources at corpus-run preflight."""
    for task in tasks:
        for variant in task.variants:
            source_value = variant.derived_from_repo_file
            expected_sha256 = variant.derived_from_sha256
            if source_value is None:
                continue
            if expected_sha256 is None:
                raise EvalRefusalError(
                    "input_invalid", (f"derived_from_sha256_missing={task.id}.{variant.id}",)
                )
            source_path = _confined_path(
                repo_root,
                source_value,
                f"{task.id}.{variant.id}.derived_from.repo_file",
            )
            if not source_path.is_file():
                raise EvalRefusalError("input_invalid", (f"derived_from_missing={source_value}",))
            observed_sha256 = sha256_file(source_path)
            if observed_sha256 != expected_sha256:
                raise EvalRefusalError(
                    "context_pin_stale",
                    (
                        f"variant={task.id}/{variant.id}",
                        f"source={source_value}",
                        f"expected={expected_sha256}",
                        f"observed={observed_sha256}",
                    ),
                )


def _configuration_pins(document: dict[str, object], path: Path) -> tuple[str | None, str | None]:
    """Read optional repository and executable pins."""
    pins = document.get("pins")
    if pins is None:
        return None, None
    if not isinstance(pins, dict):
        raise EvalRefusalError("input_invalid", (f"pins_not_an_object={path.name}",))
    repo_sha = pins.get("repo_sha")
    toolchain_sha = pins.get("toolchain_sha256")
    return (
        _sha256(repo_sha, f"{path.name}.pins.repo_sha") if repo_sha is not None else None,
        (
            _sha256(toolchain_sha, f"{path.name}.pins.toolchain_sha256")
            if toolchain_sha is not None
            else None
        ),
    )


def _configuration_costs(document: dict[str, object], path: Path) -> UnitCosts | None:
    """Read optional unit prices, with explicit zero/US-dollar defaults."""
    unit_costs = document.get("unit_costs")
    if unit_costs is None:
        return None
    if not isinstance(unit_costs, dict):
        raise EvalRefusalError("input_invalid", (f"unit_costs_not_an_object={path.name}",))
    raw_costs: dict[str, object] = {
        name: unit_costs.get(name) for name in ("input_per_1m", "output_per_1m", "currency")
    }
    for name in ("input_per_1m", "output_per_1m"):
        value = raw_costs[name]
        if value is None:
            value = 0.0
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
        ):
            raise EvalRefusalError("input_invalid", (f"unit_cost_invalid={path.name}.{name}",))
        raw_costs[name] = float(value)
    currency = raw_costs["currency"]
    if currency is None:
        currency = "USD"
    if not isinstance(currency, str) or not currency:
        raise EvalRefusalError("input_invalid", (f"unit_cost_invalid={path.name}.currency",))
    return UnitCosts(float(raw_costs["input_per_1m"]), float(raw_costs["output_per_1m"]), currency)


def load_configuration(path: Path) -> Configuration:
    """Load and validate one configuration against the runner's own field registry."""
    document = read_json(path)
    if document.get("schema") != CONFIGURATION_SCHEMA:
        raise EvalRefusalError("input_invalid", (f"schema={path}",))
    _require_registry_fields(document, CONFIGURATION_FIELDS, path.name)
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
    for name in env_raw:
        if ENV_NAME_PATTERN.fullmatch(name) is None:
            raise EvalRefusalError(
                "input_invalid", (f"harness_env_name_invalid={path.name}.{name}",)
            )
        if (
            name.upper() in FORBIDDEN_ENV_NAMES
            # This non-secret marker is reserved for boundary tests; every runner-owned
            # CTI_EVAL_* name remains protected from configuration overrides.
            or (name.startswith("CTI_EVAL_") and name != "CTI_EVAL_MARKER")
            or any(marker in name.upper() for marker in FORBIDDEN_ENV_MARKERS)
        ):
            raise EvalRefusalError(
                "input_invalid", (f"harness_env_name_forbidden={path.name}.{name}",)
            )
    pins_repo_sha, pins_toolchain_sha256 = _configuration_pins(document, path)
    return Configuration(
        name=_identifier(document.get("name"), f"{path.name}.name"),
        path=path,
        argv=tuple(argv),
        env=dict(env_raw),
        budget=_budget(document.get("budget"), path.name),
        unit_costs=_configuration_costs(document, path),
        pins_repo_sha=pins_repo_sha,
        pins_toolchain_sha256=pins_toolchain_sha256,
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
        self.name = name
        self.path = target
        self.sha256 = expected_sha
        entry = self._fresh_entry()
        if not callable(entry):
            raise EvalRefusalError(
                "grader_unloadable", (f"missing={GRADER_ENTRY}()", f"grader={source.name}")
            )

    def _fresh_entry(self) -> object:
        """Execute the verified bytes into a brand-new module and return its entry point.

        A grader that keeps module globals cannot leak one trial's state into the
        next: every call re-runs the module top level, so the only state that
        survives a call is whatever the grader wrote to disk itself.
        """
        try:
            module = importlib.util.module_from_spec(self._spec)
            self._spec.loader.exec_module(module)
        except Exception as failure:  # noqa: BLE001 — a grader import is harness input
            raise EvalRefusalError(
                "untyped_harness_failure", (f"grader={self.name}", f"error={failure!r}")
            ) from None
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
    """Resolve task legs over configuration legs over runner defaults."""
    configuration_budget = configuration.budget
    task_budget = task.budget

    def leg(name: str, default: float) -> float | int:
        """Resolve one leg while retaining partial override semantics."""
        task_value = _budget_override(task_budget, name, float(default))
        if task_value is not None:
            return task_value
        config_value = _budget_override(configuration_budget, name, float(default))
        return config_value if config_value is not None else default

    return Budget(
        float(leg("seconds", DEFAULT_BUDGET_SECONDS)),
        int(leg("tokens", DEFAULT_BUDGET_TOKENS)),
        int(leg("commands", DEFAULT_BUDGET_COMMANDS)),
    )


def child_environment(configuration: Configuration) -> dict[str, str]:
    """Assemble safe inherited names plus explicitly declared non-secret extras."""
    selected = {name: value for name, value in os.environ.items() if name in CHILD_ENV_ALLOWLIST}
    selected.update(configuration.env)
    return selected


def _resolve_executable(requested: str, repo_root: Path) -> Path:
    """Resolve argv[0] once, refusing a missing or non-executable command."""
    expanded = requested.replace(REPO_TOKEN, str(repo_root))
    candidate = Path(expanded)
    if not candidate.is_absolute():
        resolved_name = shutil.which(expanded, path=os.environ.get("PATH", SAFE_SYSTEM_PATH))
        if resolved_name is None:
            raise EvalRefusalError("toolchain_unavailable", (f"executable={requested}",))
        candidate = Path(resolved_name)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise EvalRefusalError("toolchain_unavailable", (f"executable={requested}",)) from None
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise EvalRefusalError("toolchain_unavailable", (f"not_executable={resolved}",))
    return resolved


def _toolchain_root(executable: Path, repo_root: Path) -> Path | None:
    """Return an install root that can be mounted read-only into the trial."""
    if executable.is_relative_to(repo_root.resolve()):
        return None
    for root_name in ("/usr", "/bin", "/sbin", "/lib", "/lib64"):
        root = Path(root_name)
        if executable == root or executable.is_relative_to(root):
            return None
    if executable.parent.name == "bin":
        return executable.parent.parent
    return executable.parent


def resolve_toolchain(configuration: Configuration, repo_root: Path = ROOT) -> Toolchain:
    """Resolve and hash argv[0]; the same bytes are required for every trial."""
    resolved = _resolve_executable(configuration.argv[0], repo_root)
    digest = sha256_file(resolved)
    if (
        configuration.pins_toolchain_sha256 is not None
        and digest != configuration.pins_toolchain_sha256
    ):
        raise EvalRefusalError(
            "toolchain_hash_mismatch",
            (
                f"configuration={configuration.name}",
                f"expected={configuration.pins_toolchain_sha256}",
                f"observed={digest}",
            ),
        )
    root = _toolchain_root(resolved, repo_root)
    if root is not None:
        relative = resolved.relative_to(root)
        sandbox_path = str(Path(SANDBOX_TOOLCHAIN) / relative)
    elif resolved.is_relative_to(repo_root.resolve()):
        sandbox_path = f"{SANDBOX_INPUTS}/toolchain-{digest[:12]}-{resolved.name}"
    else:
        sandbox_path = str(resolved)
    return Toolchain(
        requested=configuration.argv[0],
        resolved=resolved,
        sha256=digest,
        sandbox_path=sandbox_path,
        version=f"{resolved.name} sha256={digest}",
        root=root,
    )


def _sandbox_binary() -> Path:
    """Find bubblewrap, the required filesystem and process boundary."""
    executable = shutil.which(BWRAP_BINARY, path=os.environ.get("PATH", SAFE_SYSTEM_PATH))
    if executable is None:
        raise EvalRefusalError("sandbox_unavailable", (f"executable={BWRAP_BINARY}",))
    return Path(executable).resolve()


def _stage_input(source: Path, inputs: Path, label: str) -> str:
    """Copy one declared command input into this trial's read-only input mount."""
    digest = sha256_file(source)
    target = inputs / f"{label}-{digest[:12]}-{source.name}"
    if not target.exists():
        shutil.copyfile(source, target)
        shutil.copymode(source, target)
    return f"{SANDBOX_INPUTS}/{target.name}"


def _sandbox_argument(
    raw: str,
    index: int,
    toolchain: Toolchain,
    workspace: Path,
    inputs: Path,
    repo_root: Path,
) -> str:
    """Map a configuration argument into the sandbox or stage its declared file."""
    if index == 0:
        if toolchain.root is not None or not toolchain.resolved.is_relative_to(repo_root.resolve()):
            return toolchain.sandbox_path
        return _stage_input(toolchain.resolved, inputs, "toolchain")
    value = raw.replace(REPO_TOKEN, str(repo_root))
    workspace_text = str(workspace.resolve())
    result: str
    if value == workspace_text or value.startswith(workspace_text + os.sep):
        relative = Path(value).resolve().relative_to(workspace.resolve())
        result = str(Path(SANDBOX_WORKSPACE) / relative)
    elif REPO_TOKEN in raw:
        source = _confined_path(repo_root, raw.replace(REPO_TOKEN, "").lstrip("/"), "harness.argv")
        if not source.is_file():
            raise EvalRefusalError("input_invalid", (f"harness_argument_not_a_file={raw}",))
        result = _stage_input(source, inputs, "repo-input")
    elif Path(value).is_absolute():
        source = Path(value)
        if source.is_file():
            result = _stage_input(source.resolve(), inputs, "argument")
        elif value in {SANDBOX_WORKSPACE, SANDBOX_INPUTS, SANDBOX_TOOLCHAIN}:
            result = value
        else:
            raise EvalRefusalError("input_invalid", (f"absolute_harness_argument={raw}",))
    else:
        result = value
    return result


def sandbox_command(
    configuration: Configuration,
    toolchain: Toolchain,
    workspace: Path,
    inputs: Path,
    repo_root: Path,
    budget: Budget,
) -> list[str]:
    """Build a bubblewrap command with only OS, toolchain and trial mounts visible."""
    bwrap = _sandbox_binary()
    inputs.mkdir(parents=True, exist_ok=True)
    mapped = [
        _sandbox_argument(raw, index, toolchain, workspace, inputs, repo_root)
        for index, raw in enumerate(configuration.argv)
    ]
    command = [
        str(bwrap),
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--clearenv",
    ]
    for root in SANDBOX_BIND_ROOTS:
        if Path(root).exists():
            command.extend(("--ro-bind", root, root))
    for root in SANDBOX_HIDDEN_ROOTS:
        command.extend(("--tmpfs", root))
    command.extend(
        (
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--dir",
            SANDBOX_HOME,
            "--bind",
            str(workspace),
            SANDBOX_WORKSPACE,
            "--ro-bind",
            str(inputs),
            SANDBOX_INPUTS,
        )
    )
    if toolchain.root is not None:
        command.extend(("--ro-bind", str(toolchain.root), SANDBOX_TOOLCHAIN))
    environment = child_environment(configuration)
    environment.update(
        {
            "HOME": SANDBOX_HOME,
            "PWD": SANDBOX_WORKSPACE,
            "PATH": f"{SANDBOX_TOOLCHAIN}/bin:{SAFE_SYSTEM_PATH}"
            if toolchain.root is not None
            else SAFE_SYSTEM_PATH,
            ADAPTER_ENV_USAGE_FILE: f"{SANDBOX_WORKSPACE}/{USAGE_RECORD}",
            ADAPTER_ENV_TOKEN_BUDGET: str(budget.tokens),
            ADAPTER_ENV_COMMAND_BUDGET: str(budget.commands),
        }
    )
    for name, value in environment.items():
        command.extend(("--setenv", name, value))
    command.extend(("--chdir", SANDBOX_WORKSPACE, "--", *mapped))
    return command


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
        "context_pin": None,
    }
    if variant.file is not None:
        target = workspace / variant.file.name
        target.write_bytes(variant.file.read_bytes())
        seeded = {
            "prompt_file": TRIAL_FILE,
            "context": variant.file.name,
            "context_sha256": sha256_file(variant.file),
            "context_pin": (
                {
                    "repo_file": variant.derived_from_repo_file,
                    "sha256": variant.derived_from_sha256,
                }
                if variant.derived_from_repo_file is not None
                else None
            ),
        }
    if variant.repo_file is not None:
        source = repo_root / variant.repo_file
        target = workspace / Path(variant.repo_file).name
        target.write_bytes(source.read_bytes())
        seeded = {
            "prompt_file": TRIAL_FILE,
            "context": Path(variant.repo_file).name,
            "context_sha256": sha256_file(source),
            "context_pin": None,
        }
    return seeded


def _usage_from_mapping(mapping: object, label: str) -> dict[str, int]:
    """Validate cumulative usage counters from the live sidecar or final record."""
    if not isinstance(mapping, dict):
        detail = f"{label}_not_an_object"
        raise TypeError(detail)
    usage: dict[str, int] = {}
    for contract in USAGE_FIELDS:
        value = mapping.get(contract.name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            detail = f"{label}.{contract.name}_not_a_nonnegative_integer"
            raise ValueError(detail)
        usage[contract.name] = value
    return usage


def read_usage(path: Path) -> tuple[dict[str, int] | None, str | None]:
    """Read the adapter's cumulative usage sidecar without raising into the runner."""
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _usage_from_mapping(raw, USAGE_RECORD), None
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as failure:
        return None, str(failure)


def _budget_reason(usage: dict[str, int], budget: Budget) -> str | None:
    """Return the first exceeded live usage leg, if any."""
    if usage["tokens_in"] + usage["tokens_out"] > budget.tokens:
        return "tokens"
    if usage["commands"] > budget.commands:
        return "commands"
    return None


@dataclass
class ProcessWatch:
    """Shared state between the process wait and live budget monitor."""

    done: threading.Event = field(default_factory=threading.Event)
    state: TrialState | None = None
    detail: str = ""
    reported: dict[str, int] | None = None


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Stop the complete trial process group, including descendants."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=0.25)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait()


def _watch_process_usage(
    process: subprocess.Popen[bytes], usage_path: Path, budget: Budget, watch: ProcessWatch
) -> None:
    """Kill a live trial when its sidecar reports a token or command ceiling."""
    while process.poll() is None and not watch.done.is_set():
        usage, error = read_usage(usage_path)
        if error is not None:
            watch.state = TrialState.UNTYPED_HARNESS_FAILURE
            watch.detail = f"usage_unreadable={error}"
            _terminate_process_group(process)
            return
        if usage is not None:
            watch.reported = usage
            reason = _budget_reason(usage, budget)
            if reason is not None:
                watch.state = TrialState.BUDGET_STOPPED
                watch.detail = f"budget={reason}"
                _terminate_process_group(process)
                return
        watch.done.wait(0.01)


def _write_streams(trial_dir: Path, stdout: bytes | None, stderr: bytes | None) -> None:
    """Retain both harness streams, including output collected after a timeout."""
    (trial_dir / "harness-stdout.txt").write_bytes(stdout or b"")
    (trial_dir / "harness-stderr.txt").write_bytes(stderr or b"")


def _raw_adapter_record(workspace: Path) -> dict[str, object] | None:
    """Read a final adapter record for exit-code classification."""
    path = workspace / ADAPTER_RECORD
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _record_context(
    task: Task, variant: Variant, configuration: Configuration, toolchain: Toolchain
) -> dict[str, object]:
    """Return provenance carried into every accepted trial record."""
    return {
        "task": {"id": task.id, "provenance": task.provenance},
        "configuration": configuration.name,
        "variant": variant.id,
        "toolchain": {
            "requested": toolchain.requested,
            "resolved": str(toolchain.resolved),
            "sha256": toolchain.sha256,
        },
    }


def _run_adapter_process(
    trial_dir: Path,
    workspace: Path,
    argv: list[str],
    budget: Budget,
) -> tuple[TrialOutcome | None, dict[str, int] | None]:
    """Run one sandboxed adapter and return a terminal process outcome, if any."""
    process = subprocess.Popen(  # noqa: S603 — argv is a validated configuration input
        argv,
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=False,
    )
    usage_path = workspace / USAGE_RECORD
    watch = ProcessWatch()
    monitor = threading.Thread(
        target=_watch_process_usage,
        args=(process, usage_path, budget, watch),
        name=f"eval-budget-{trial_dir.name}",
        daemon=True,
    )
    monitor.start()
    outcome: TrialOutcome | None = None
    observed: dict[str, int] | None = None
    try:
        stdout, stderr = process.communicate(timeout=budget.seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        stdout, stderr = process.communicate()
        outcome = TrialOutcome(
            trial_dir.name,
            None,
            TrialState.BUDGET_STOPPED,
            f"budget=time ({budget.seconds}s)",
        )
        (trial_dir / "harness-timeout.txt").write_text(
            f"time budget {budget.seconds}s exhausted\n", encoding="utf-8"
        )
    finally:
        watch.done.set()
        monitor.join()
    _write_streams(trial_dir, stdout, stderr)
    observed, usage_error = read_usage(usage_path)
    if outcome is None and watch.state is not None:
        outcome = TrialOutcome(
            trial_dir.name,
            None,
            watch.state,
            watch.detail,
            observed or watch.reported,
        )
    if outcome is None and process.returncode != 0:
        raw_record = _raw_adapter_record(workspace)
        crash_record = raw_record is not None and raw_record.get("stopped_by") == STOPPED_BY_CRASH
        sandbox_error = stderr.startswith(b"bwrap:")
        if crash_record or sandbox_error:
            outcome = TrialOutcome(
                trial_dir.name,
                None,
                TrialState.INFRA_UNAVAILABLE,
                (
                    f"harness_crash_exit={process.returncode}"
                    if crash_record
                    else f"sandbox_exit={process.returncode}"
                ),
                observed,
            )
        else:
            outcome = TrialOutcome(
                trial_dir.name,
                None,
                TrialState.UNTYPED_HARNESS_FAILURE,
                f"harness_exit={process.returncode}",
                observed,
            )
    if outcome is None and usage_error is not None:
        outcome = TrialOutcome(
            trial_dir.name,
            None,
            TrialState.UNTYPED_HARNESS_FAILURE,
            f"usage_unreadable={usage_error}",
            observed,
        )
    if outcome is None and observed is None:
        outcome = TrialOutcome(
            trial_dir.name,
            None,
            TrialState.UNTYPED_HARNESS_FAILURE,
            f"missing={USAGE_RECORD}",
        )
    if outcome is not None and outcome.reported is None:
        outcome.reported = observed
    return outcome, observed


def execute_trial(
    task: Task,
    variant: Variant,
    configuration: Configuration,
    trial_dir: Path,
    repo_root: Path,
    toolchain: Toolchain | None = None,
) -> tuple[TrialOutcome, dict[str, object] | None]:
    """Run one trial in a fresh workspace and return its outcome and its record.

    The adapter runs in a bubblewrap filesystem and PID boundary. Its usage sidecar is
    watched while it runs; a ceiling kills the whole process group before a verdict can
    exist. Grading happens in `grade_trial`, never here.
    """
    try:
        trial_dir.mkdir(parents=True, exist_ok=False)
        workspace = trial_dir / "workspace"
        seeded = seed_workspace(workspace, task, variant, repo_root)
        budget = effective_budget(task, configuration)
        resolved_toolchain = toolchain or resolve_toolchain(configuration, repo_root)
        if sha256_file(resolved_toolchain.resolved) != resolved_toolchain.sha256:
            outcome = TrialOutcome(
                trial_dir.name,
                None,
                TrialState.INFRA_UNAVAILABLE,
                "toolchain_changed_before_trial",
            )
            return outcome, None
        inputs = trial_dir / "inputs"
        argv = sandbox_command(
            configuration, resolved_toolchain, workspace, inputs, repo_root, budget
        )
        outcome, observed = _run_adapter_process(trial_dir, workspace, argv, budget)
        if outcome is not None:
            return outcome, None
    except (EvalRefusalError, OSError) as failure:
        kind = failure.kind if isinstance(failure, EvalRefusalError) else "harness_oserror"
        detail = (
            ",".join(failure.details) if isinstance(failure, EvalRefusalError) else str(failure)
        )
        return (
            TrialOutcome(
                trial_dir.name,
                None,
                TrialState.INFRA_UNAVAILABLE
                if isinstance(failure, OSError)
                else TrialState.UNTYPED_HARNESS_FAILURE,
                f"{kind}={detail}",
            ),
            None,
        )
    except Exception as failure:  # noqa: BLE001 — any runner failure must be typed
        return (
            TrialOutcome(
                trial_dir.name,
                None,
                TrialState.UNTYPED_HARNESS_FAILURE,
                f"runner_exception={failure!r}",
            ),
            None,
        )
    return read_adapter_record(
        trial_dir,
        workspace,
        budget,
        seeded,
        observed_usage=observed,
        require_live_usage=True,
        context=_record_context(task, variant, configuration, resolved_toolchain),
    )


def read_adapter_record(
    trial_dir: Path,
    workspace: Path,
    budget: Budget,
    seeded: dict[str, object],
    *,
    observed_usage: dict[str, int] | None = None,
    require_live_usage: bool = False,
    context: dict[str, object] | None = None,
) -> tuple[TrialOutcome, dict[str, object] | None]:
    """Validate what the adapter wrote, typing every way it can be unusable."""
    record_path = workspace / ADAPTER_RECORD
    if not record_path.is_file():
        return (
            TrialOutcome(
                trial_dir.name,
                None,
                TrialState.UNTYPED_HARNESS_FAILURE,
                f"missing={ADAPTER_RECORD}",
            ),
            None,
        )
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as failure:
        return (
            TrialOutcome(
                trial_dir.name,
                None,
                TrialState.UNTYPED_HARNESS_FAILURE,
                f"record_unreadable={failure}",
            ),
            None,
        )
    if not isinstance(record, dict):
        return (
            TrialOutcome(
                trial_dir.name, None, TrialState.UNTYPED_HARNESS_FAILURE, "record_not_an_object"
            ),
            None,
        )
    for contract in ADAPTER_FIELDS:
        if contract.required and contract.name not in record:
            return (
                TrialOutcome(
                    trial_dir.name,
                    None,
                    TrialState.UNTYPED_HARNESS_FAILURE,
                    f"missing={ADAPTER_RECORD}.{contract.name}",
                ),
                None,
            )
    return enforce_budget(
        trial_dir,
        record,
        budget,
        seeded,
        observed_usage=observed_usage,
        require_live_usage=require_live_usage,
        context=context,
    )


def enforce_budget(
    trial_dir: Path,
    record: dict[str, object],
    budget: Budget,
    seeded: dict[str, object],
    *,
    observed_usage: dict[str, int] | None = None,
    require_live_usage: bool = False,
    context: dict[str, object] | None = None,
) -> tuple[TrialOutcome, dict[str, object] | None]:
    """Type a budget stop, an infra stop, or a usable record for grading."""
    stopped_by = record.get("stopped_by")
    outcome: TrialOutcome | None = None
    record_usage: dict[str, int] | None = None
    if stopped_by not in (STOPPED_COMPLETED, STOPPED_BY_BUDGET, STOPPED_BY_CRASH):
        outcome = TrialOutcome(
            trial_dir.name,
            None,
            TrialState.UNTYPED_HARNESS_FAILURE,
            f"stopped_by={stopped_by!r}",
            observed_usage,
        )
    else:
        try:
            record_usage = _usage_from_mapping(record, ADAPTER_RECORD)
        except (TypeError, ValueError) as failure:
            outcome = TrialOutcome(
                trial_dir.name,
                None,
                TrialState.UNTYPED_HARNESS_FAILURE,
                str(failure),
                observed_usage,
            )
        if outcome is None and require_live_usage and observed_usage is None:
            outcome = TrialOutcome(
                trial_dir.name,
                None,
                TrialState.UNTYPED_HARNESS_FAILURE,
                f"missing={USAGE_RECORD}",
                record_usage,
            )
        if outcome is None and observed_usage is not None and observed_usage != record_usage:
            outcome = TrialOutcome(
                trial_dir.name,
                None,
                TrialState.UNTYPED_HARNESS_FAILURE,
                "usage_mismatch=trial.json_vs_usage.json",
                observed_usage,
            )
        if outcome is None:
            usage = observed_usage or record_usage
            if usage is None:
                outcome = TrialOutcome(
                    trial_dir.name,
                    None,
                    TrialState.UNTYPED_HARNESS_FAILURE,
                    f"missing={USAGE_RECORD}",
                    observed_usage,
                )
            else:
                reason = _budget_reason(usage, budget)
                if stopped_by == STOPPED_BY_BUDGET or reason is not None:
                    detail = f"budget={stopped_by if stopped_by == STOPPED_BY_BUDGET else reason}"
                    outcome = TrialOutcome(
                        trial_dir.name, None, TrialState.BUDGET_STOPPED, detail, usage
                    )
                elif stopped_by == STOPPED_BY_CRASH:
                    outcome = TrialOutcome(
                        trial_dir.name,
                        None,
                        TrialState.INFRA_UNAVAILABLE,
                        "harness=crashed",
                        usage,
                    )
                elif not isinstance(record.get("answer"), str):
                    outcome = TrialOutcome(
                        trial_dir.name,
                        None,
                        TrialState.UNTYPED_HARNESS_FAILURE,
                        "answer_not_a_string",
                        usage,
                    )
                else:
                    record_out = dict(record)
                    record_out["schema"] = TRIAL_RECORD_SCHEMA
                    record_out["seeded"] = seeded
                    record_out["usage"] = usage
                    if context is not None:
                        record_out.update(context)
                    (trial_dir / "record.json").write_text(
                        json.dumps(record_out, indent=2, sort_keys=True),
                        encoding="utf-8",
                    )
                    return TrialOutcome(
                        trial_dir.name, None, TrialState.GRADED_PENDING, "record accepted", usage
                    ), record_out
    return outcome or TrialOutcome(
        trial_dir.name,
        None,
        TrialState.UNTYPED_HARNESS_FAILURE,
        "budget_enforcement_incomplete",
        observed_usage,
    ), None


def grade_trial(
    outcome: TrialOutcome,
    record: dict[str, object],
    grader: Grader,
    task: Task,
) -> TrialOutcome:
    """Grade one trial's answer and turn it into met/not_met."""
    assigned, note = grader.grade(record, task.classes)
    outcome.graded_class = assigned
    outcome.state = TrialState.MET if assigned == task.expected_class else TrialState.NOT_MET
    outcome.detail = f"class={assigned} note={note}".strip()
    return outcome


def _collect_trial_states(trials: list[TrialOutcome], result: CaseResult) -> tuple[bool, bool]:
    """Count trial classes and return whether harness or infrastructure failed."""
    saw_untyped = False
    saw_infra = False
    for trial in trials:
        try:
            state = TrialState(trial.state)
        except ValueError:
            state = TrialState.UNTYPED_HARNESS_FAILURE
            trial.detail = f"unknown_trial_state={trial.state!r} {trial.detail}".strip()
            trial.state = state
        saw_untyped = saw_untyped or state is TrialState.UNTYPED_HARNESS_FAILURE
        saw_infra = saw_infra or state is TrialState.INFRA_UNAVAILABLE
        if state is TrialState.BUDGET_STOPPED:
            result.budget_stops += 1
            result.details.append(f"trial={trial.index} budget_stopped {trial.detail}")
        elif state in (TrialState.INFRA_UNAVAILABLE, TrialState.UNTYPED_HARNESS_FAILURE):
            result.not_a_result += 1
            result.details.append(f"trial={trial.index} {state.value} {trial.detail}")
        elif state in (TrialState.MET, TrialState.NOT_MET):
            key = trial.graded_class or "?"
            if key == UNCLASSIFIED:
                result.unclassified += 1
            else:
                result.classes_seen[key] = result.classes_seen.get(key, 0) + 1
        else:
            result.not_a_result += 1
            result.details.append(f"trial={trial.index} {state.value} not graded")
    result.graded = sum(result.classes_seen.values())
    return saw_untyped, saw_infra


def _quarantine_baseline(
    result: CaseResult,
    trials: list[TrialOutcome],
    task_id: str,
    variant_id: str,
    configuration_name: str,
    toolchain: Toolchain | None,
) -> None:
    """Attach the complete arrangement and outcome record for a quarantined case."""
    result.baseline = {
        "arrangement": {
            "task": task_id,
            "variant": variant_id,
            "configuration": configuration_name,
            "fresh_workspace_per_trial": True,
            "toolchain": toolchain.sha256 if toolchain is not None else "unknown",
        },
        "run_count": len(trials),
        "stated_repeats": len(trials),
        "outcomes": [
            {
                "trial": trial.index,
                "state": TrialState(trial.state).value,
                "class": trial.graded_class,
                "detail": trial.detail,
            }
            for trial in trials
        ],
        "budget_stops": result.budget_stops,
        "disagreement": round(1.0 - max(result.classes_seen.values()) / result.graded, 4),
        "tolerance": result.tolerance,
    }


def aggregate_case(
    configuration_name: str,
    case_id: str,
    trials: list[TrialOutcome],
    expected_class: str,
    tolerance: float,
    usage: dict[str, float],
    *,
    task: Task | None = None,
    variant: Variant | None = None,
    toolchain: Toolchain | None = None,
) -> CaseResult:
    """Turn a case's trials into its verdict: a rate over the graded repeats.

    The ladder's order is the criteria's order. An infrastructure or harness failure in
    any trial types the whole case not-a-result — never a failed configuration — and no
    rate is computed at all, because a partial measurement is not a measurement. Then a
    spread beyond tolerance quarantines the case with its reproduction baseline. Only a
    case whose graded trials agree within tolerance is judged on its rate, and a case
    the budget ended before it graded anything is a budget stop, never a fail.
    """
    task_id = task.id if task is not None else case_id.split("/", maxsplit=1)[0]
    variant_id = variant.id if variant is not None else case_id.rsplit("/", maxsplit=1)[-1]
    provenance = task.provenance if task is not None else ""
    result = CaseResult(
        configuration=configuration_name,
        case_id=case_id,
        state=CaseState.WITHIN_TOLERANCE,
        task_id=task_id,
        task_provenance=provenance,
        variant_id=variant_id,
        expected_class=expected_class,
        tolerance=tolerance,
    )
    result.wall_seconds = usage["wall_seconds"]
    result.tokens_in = int(usage["tokens_in"])
    result.tokens_out = int(usage["tokens_out"])
    result.commands = int(usage["commands"])
    result.currency_cost = (
        float(usage["currency_cost"]) if usage.get("currency_cost") is not None else None
    )
    saw_untyped, saw_infra = _collect_trial_states(trials, result)
    if saw_untyped:
        result.state = CaseState.UNTYPED_HARNESS_FAILURE
    elif saw_infra:
        result.state = CaseState.INFRA_UNAVAILABLE
    elif result.not_a_result:
        result.state = CaseState.UNTYPED_HARNESS_FAILURE
    elif result.budget_stops:
        result.state = CaseState.BUDGET_STOPPED
        result.details.append(
            f"budget_stops={result.budget_stops} graded={result.graded} — no complete rate"
        )
    elif result.graded + result.unclassified != len(trials):
        result.state = CaseState.UNTYPED_HARNESS_FAILURE
        result.details.append(
            f"graded={result.graded} unclassified={result.unclassified} repeats={len(trials)}"
        )
    if result.state is not CaseState.WITHIN_TOLERANCE:
        return result
    result.met = result.classes_seen.get(expected_class, 0)
    if result.graded == 0:
        if result.unclassified:
            result.state = CaseState.UNCLASSIFIED
            result.details.append(
                f"graded=0 unclassified={result.unclassified} — no rate over graded answers"
            )
        else:
            result.state = CaseState.UNTYPED_HARNESS_FAILURE
            result.details.append("graded=0 — no observation, no verdict")
        return result
    disagreement = 1.0 - max(result.classes_seen.values()) / result.graded
    if disagreement > tolerance:
        result.state = CaseState.QUARANTINED
        _quarantine_baseline(result, trials, task_id, variant_id, configuration_name, toolchain)
        return result
    result.rate = result.met / result.graded
    result.under_powered = half_width(result.graded) > tolerance
    rate_state = (
        CaseState.WITHIN_TOLERANCE
        if result.rate >= 1.0 - tolerance
        else CaseState.OUTSIDE_TOLERANCE
    )
    result.state = (
        CaseState.UNCLASSIFIED
        if result.unclassified and rate_state is CaseState.WITHIN_TOLERANCE
        else rate_state
    )
    result.details.append(
        f"verdict_rate={result.rate:.2f} over=graded_answers met={result.met}/{result.graded}"
        f" unclassified={result.unclassified} tolerance={tolerance}"
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
    toolchain: Toolchain | None = None,
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
        "usage_unknown": 0.0,
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
                "usage_unknown": 0.0,
            }
            for index in range(1, task.repeats + 1):
                started = datetime.now(UTC)
                trial_dir = case_dir / f"trial-{index:03d}"
                outcome, record = execute_trial(
                    task, variant, configuration, trial_dir, repo_root, toolchain
                )
                if outcome.state is TrialState.GRADED_PENDING and record is not None:
                    try:
                        outcome = grade_trial(outcome, record, graders[task.id], task)
                    except EvalRefusalError as failure:
                        outcome.state = TrialState.UNTYPED_HARNESS_FAILURE
                        outcome.detail = (
                            f"grader={failure.kind} {' '.join(failure.details)}"
                        ).strip()
                usage["wall_seconds"] += (datetime.now(UTC) - started).total_seconds()
                if outcome.reported is None:
                    usage["usage_unknown"] += 1.0
                else:
                    usage["tokens_in"] += outcome.reported["tokens_in"]
                    usage["tokens_out"] += outcome.reported["tokens_out"]
                    usage["commands"] += outcome.reported["commands"]
                (trial_dir / "outcome.json").write_text(
                    json.dumps(
                        {
                            "index": outcome.index,
                            "state": outcome.state.value,
                            "graded_class": outcome.graded_class,
                            "detail": outcome.detail,
                            "reported": outcome.reported,
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
                    configuration.name,
                    case_id,
                    trials,
                    task.expected_class,
                    task.tolerance,
                    usage,
                    task=task,
                    variant=variant,
                    toolchain=toolchain,
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
        f"power: independent_tasks={independent_cases}",
        (
            f"power: half_width observed_n={independent_cases}"
            f" {percentage(half_width(independent_cases))}"
            f" reference_n=20 {percentage(half_width(20))}"
            f" reference_n=50 {percentage(half_width(50))}"
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


def toolchain_pin(
    repo_root: Path, toolchains: dict[str, Toolchain] | None = None
) -> dict[str, object]:
    """Record runner identity and each configuration's executable pin."""
    return {
        "python": sys.version.split()[0],
        "runner_sha256": sha256_file(Path(__file__)),
        "head": git_head(repo_root),
        "configurations": {
            name: {
                "requested": toolchain.requested,
                "resolved": str(toolchain.resolved),
                "sha256": toolchain.sha256,
                "version": toolchain.version,
            }
            for name, toolchain in (toolchains or {}).items()
        },
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


def _field_block(fields: tuple[ContractField, ...]) -> list[str]:
    """Render one registry as the contract's field lines."""
    width = max(len(field.name) for field in fields)
    return [
        f"  {field.name:<{width}}  {'required' if field.required else 'optional '}  {field.purpose}"
        for field in fields
    ]


def _group_by_task(results: list[CaseResult]) -> dict[str, list[CaseResult]]:
    """Group materialized variant cases without treating them as independent tasks."""
    grouped: dict[str, list[CaseResult]] = {}
    for result in results:
        grouped.setdefault(result.task_id, []).append(result)
    return grouped


def render_report(
    run_id: str,
    configurations: list[Configuration],
    per_configuration: dict[str, list[CaseResult]],
    totals: dict[str, dict[str, float]],
    independent_cases: int,
    min_cases_for_claim: int,
) -> str:
    """Render the human report: per case, per configuration, never netted."""
    materialized_cases = len(next(iter(per_configuration.values()), []))
    lines = [
        (
            f"eval_run={run_id} configurations={len(configurations)}"
            f" independent_tasks={independent_cases} materialized_cases={materialized_cases}"
        )
    ]
    for configuration in configurations:
        counts: dict[str, int] = {}
        for result in per_configuration[configuration.name]:
            counts[result.state.value] = counts.get(result.state.value, 0) + 1
        summary = " ".join(f"{name}={counts[name]}" for name in sorted(counts))
        name_w = max(len(c.name) for c in configurations)
        case_count = len(per_configuration[configuration.name])
        lines.append(f"config={configuration.name:<{name_w}} cases={case_count} {summary}")
    for configuration in configurations:
        grouped = _group_by_task(per_configuration[configuration.name])
        for task_id in sorted(grouped):
            task_state = worst_state(grouped[task_id])
            lines.append(
                f"task={task_id} config={configuration.name} verdict={task_state.value}"
                f" cases={len(grouped[task_id])}"
            )
    for configuration in configurations:
        for result in per_configuration[configuration.name]:
            verdict = (
                f"rate={result.rate:.2f} rate_over=graded_answers"
                if result.rate is not None
                else "unavailable"
            )
            power = (
                "not_applicable"
                if result.rate is None
                else ("yes" if result.under_powered else "no")
            )
            lines.append(
                f"case={result.case_id} task={result.task_id}"
                f" config={result.configuration} variant={result.variant_id}"
                f" expected={result.expected_class} tolerance={result.tolerance}"
                f" verdict={verdict} status={result.state.value}"
                f" met={result.met}/{result.graded} graded={result.graded}"
                f" unclassified={result.unclassified} budget_stops={result.budget_stops}"
                f" not_a_result={result.not_a_result}"
                f" under_powered={power}"
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
        if totals[name]["usage_unknown"]:
            cost_line += f" currency=unreported usage_unknown={int(totals[name]['usage_unknown'])}"
        elif configuration.unit_costs is not None:
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
            differed = (
                left[case_id].state != right[case_id].state
                or left[case_id].rate != right[case_id].rate
            )
            divergent += 1 if differed else 0
            lines.append(
                f"pair={case_id} {first}={left[case_id].state.value}"
                f" {second}={right[case_id].state.value} divergent={'yes' if differed else 'no'}"
            )
        lines.append(f"divergent_cases={divergent}")
        left_tasks = _group_by_task(per_configuration[first])
        right_tasks = _group_by_task(per_configuration[second])
        for task_id in sorted(left_tasks):
            left_state = worst_state(left_tasks[task_id])
            right_state = worst_state(right_tasks[task_id])
            lines.append(
                f"task_pair={task_id} {first}={left_state.value}"
                f" {second}={right_state.value}"
                f" divergent={'yes' if left_state != right_state else 'no'}"
            )
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
        "runner validates and exits with. If a field is added to one registry and this",
        "output does not name it, that is a bug (tests/unit/test_eval_contract.py plants it).",
        "",
        "=== Task file (schema " + TASK_SCHEMA + ") ===",
    ]
    lines.extend(_field_block(TASK_FIELDS))
    lines.extend(["", "=== Task variants ==="])
    lines.extend(_field_block(VARIANT_FIELDS))
    lines.extend(["", "=== Budget override ==="])
    lines.extend(_field_block(BUDGET_FIELDS))
    lines.extend(["", "=== Unit costs ==="])
    lines.extend(_field_block(UNIT_COST_FIELDS))
    lines.extend(["", "=== Configuration pins ==="])
    lines.extend(_field_block(PIN_FIELDS))
    lines.extend(["", "=== Configuration file (schema " + CONFIGURATION_SCHEMA + ") ==="])
    lines.extend(_field_block(CONFIGURATION_FIELDS))
    interfaces = [
        "",
        "=== What the adapter owes the runner (written to " + ADAPTER_RECORD + " in its cwd) ===",
        "The adapter runs in a fresh bubblewrap workspace holding only `task.txt`",
        "(the prompt), the arm's context file, and its own output files. Host home,",
        "temporary, repository and prior run state are not mounted. The child receives",
        f"an allowlisted environment ({', '.join(CHILD_ENV_ALLOWLIST)}) plus safe",
        "configuration entries — never a lane variable, credential or dispatch identity.",
        "Runner-owned HOME, PWD, PATH and the adapter environment below are fixed by",
        "the runner and point only inside the sandbox.",
        "The adapter must atomically update `usage.json` while running, then write",
        "`trial.json`; its three usage counters must exactly match the final `usage.json`",
        "counters. Zero is a valid measured count; a missing or unreadable sidecar is",
        "a harness failure, not an unknown value.",
        "Unknown record keys are ignored and retained verbatim.",
    ]
    lines.extend(interfaces)
    lines.extend(["", "=== Runner-owned adapter environment ==="])
    lines.extend(_field_block(ADAPTER_ENV_FIELDS))
    lines.extend(["", "=== Adapter record ==="])
    lines.extend(_field_block(ADAPTER_FIELDS))
    lines.extend(["", "=== Live usage sidecar (written to " + USAGE_RECORD + ") ==="])
    lines.extend(_field_block(USAGE_FIELDS))
    lines.extend(["", "=== What the grader owes the runner ==="])
    lines.extend(_field_block(GRADER_FIELDS))
    grader_block = [
        "",
        "A grader lives under evals/graders/, pinned by the task's grader_sha256, is",
        "copied into this run directory before any trial and imported from that copy —",
        "never from a trial workspace, whose path never reaches the harness child. A hash",
        "that does not match refuses the run before any trial; a class outside the task's",
        "`classes` is a harness failure, not a graded outcome.",
        "",
        "=== Verdict and exit codes ===",
        "A trial stopped by its budget, and an infrastructure failure, are recorded as",
        "exactly that. A case verdict is a rate over graded answers only;",
        "`unclassified` answers are counted separately, and a spread beyond the",
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
            "       context_pin_stale, pin_mismatch, run_dir_exists — never a verdict)",
            "",
            "=== Materialized case ===",
            *(_field_block(CASE_FIELDS)),
            "",
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
    _sandbox_binary()
    tasks, manifest = load_corpus(args.corpus, ROOT)
    verify_context_pins(tasks, ROOT)
    for task in tasks:
        verify_grader_hash(task.grader, task.grader_sha256)
    for configuration in configurations:
        pin = configuration.pins_repo_sha
        if pin is not None and git_head(ROOT) != pin:
            raise EvalRefusalError(
                "pin_mismatch", (f"configuration={configuration.name}", f"expected={pin}")
            )
        resolve_toolchain(configuration, ROOT)
    return configurations, tasks, manifest


def run_prepared(
    args: argparse.Namespace,
    configurations: list[Configuration],
    tasks: list[Task],
    manifest: dict[str, object],
) -> int:
    """Run inputs that passed the no-trial validation phase."""
    toolchains = {
        configuration.name: resolve_toolchain(configuration, ROOT)
        for configuration in configurations
    }
    independent_cases = len(tasks)
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
                        f" toolchain_sha256={toolchains[configuration.name].sha256}"
                    )
        for line in power_statement(independent_cases, min_cases):
            print_plan(line)
        return 0
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = (args.runs_root / run_id).resolve()
    try:
        run_dir.mkdir(parents=True)
    except OSError as failure:
        raise EvalRefusalError(
            "run_dir_exists", (f"run_dir={run_dir}", f"error={failure}")
        ) from None
    # The graders load after the dry-run branch and after the run directory exists, so
    # a dry run writes nothing at all and a real run's grader copies live beside its
    # evidence, hash-verified before any trial.
    graders = {
        task.id: Grader(task.grader, task.grader_sha256, run_dir / "graders", task.id)
        for task in tasks
    }
    per_configuration: dict[str, list[CaseResult]] = {}
    totals: dict[str, dict[str, float]] = {}
    for configuration in configurations:
        results, config_totals = run_configuration(
            tasks, configuration, run_dir, ROOT, graders, toolchains[configuration.name]
        )
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
                "toolchain": toolchain_pin(ROOT, toolchains),
                "configurations": [c.name for c in configurations],
                "graders": {name: g.sha256 for name, g in graders.items()},
                "independent_tasks": independent_cases,
                "materialized_cases": sum(len(task.variants) for task in tasks),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    sys.stdout.write(report)
    worst = worst_state([r for results in per_configuration.values() for r in results])
    return CASE_SEVERITY[worst]


def main(argv: list[str] | None = None) -> int:
    """Run the corpus, write the run directory, and exit on the worst class."""
    args = parse_args(argv)
    if args.contract:
        sys.stdout.write(render_contract())
        return 0
    try:
        configurations, tasks, manifest = prepare_run(args)
        return run_prepared(args, configurations, tasks, manifest)
    except EvalRefusalError as refusal:
        print_refusal(refusal, "before any trial")
        return REFUSAL_EXIT


if __name__ == "__main__":
    sys.exit(main())
