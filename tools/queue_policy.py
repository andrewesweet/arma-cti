"""The dispatch queue as data: the policy a running session reads, not a memory it holds (#250).

`docs/orchestration-design.md` §2 is the design; this is its implementation. The queue is a
**derived view** over three sources and only one of them is a file this project writes:

1. **Candidate work** — `gh issue list --label ready-for-agent`, read live, never copied. A
   second copy of the tracker would drift, and drift on a coordination surface is the failure
   `tools/check_validated_markers.py` exists to catch one level down.
2. **Policy** — the freeze, the carve-out packages, the WIP limit, the reservations. These are
   the human's rulings and exist in no machine-readable place today: they live in an
   orchestrator's memory and in issue comments. **This is the file.**
3. **In-flight** — derived from the box, never counted by hand.

## Why a file at all

A freeze recorded on an issue and in session memory does not reach an orchestrator session
already running — ADR-0042's stale-copy window one level up. The human recorded that caveat on
#217 at 2026-08-05T17:12Z and the twenty-fifth retro correctly declined to land it, because the
seat holding the retro could not read orchestrator memory. A freeze in a file that
`just dispatch` reads **per dispatch** does reach a running session, because the read happens
per dispatch rather than per session. That is the identical conversion #238 made for the
off-peak window, refusal and all — including the part that is easy to get wrong, that it
**carries no failure class**: nothing was found about any provider, any lane or any code.

There is deliberately **no override on this surface**: no flag, no environment variable, no
per-dispatch exemption. The freeze is the human's and only they amend it.

## Why every entry quotes a ruling

`tools/admission.py` requires a choice on every Part A criterion with no default, because a
criterion nobody passed is a criterion nobody checked. The same discipline, applied to the one
surface whose scheduling rules have no provenance at all today: **a write without `--ruling` is
refused, and a read that finds an entry without one refuses `policy_invalid`.** The human's own
carve-out wording is the worked case — it says confirm the package's scope with the human
rather than infer it from what is landing, and a policy entry that cannot quote a ruling is
exactly that inference.

## Why an absent or unreadable policy refuses rather than permits

Fail closed, on #41's shape: a check that could not run is not a check that passed. A policy
nobody can parse is not a policy that permits, and an absent one is a box where nobody has
recorded a freeze state at all — which must not read as "open". Seeding is one call per entry
(`just queue open|freeze|wip`), each carrying its own ruling, so the file is built from rulings
rather than from a default nobody chose.

## What this does not decide

Readiness is #241's rung and this consumes its verdict rather than inventing a second one. Lane
and profile belong to the breaker and the admission bar. Semantic dependency order is judgement:
an optional `Blocked-by: #N` body line is read where it exists and its absence is reported. And
**the scheduler selects and prints; it never dispatches** — ADR-0053's split, the same reason
`just watch` never messages the agent it watched.

## Why this file is not called `queue.py`

`tools/` is put on `sys.path` by every script in it that imports a sibling, so a module here
named `queue` would shadow the standard library's `queue` for the whole process — and
`concurrent.futures`, `multiprocessing` and pytest-xdist's own transport all import that one.
The recipe is still `just queue`; only the module carries the longer name.

Refs #250, #242, #217, #241, #238, #209, ADR-0042, ADR-0049, ADR-0051, ADR-0053.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import otel_event  # the path insert above is what makes this importable

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

# Outside every worktree, beside `~/.arma-cti/breaker/`, `~/.arma-cti/admission/` and the rest
# of this project's orchestration state. A tracked file would put a gate cycle between a
# human's ruling and its taking effect, and would collide across the concurrent worktrees that
# make this project's ADR-numbering rule necessary.
DEFAULT_QUEUE_DIR: Final = Path.home() / ".arma-cti" / "queue"
POLICY_FILE: Final = "policy.json"
TRANSITION_JOURNAL: Final = "transitions.jsonl"
TRANSITION_EVENT: Final = "cti.queue.transition"

# The document's own version. A file carrying anything else is refused rather than guessed at,
# because a reader that "handles" a version it does not know is a reader inventing policy.
VERSION: Final = 1

FROZEN: Final = "frozen"
OPEN: Final = "open"

EXIT_REFUSED: Final = 1

# `.claude/worktrees/issue-<N>` is the shape `just worktree add issue-<N>` makes and every
# dispatch briefing calls for. `agent-<hex>` trees are the harness's own per-session isolation
# trees and are excluded **by name**: measured on this box for #242's study, 93 worktree
# registrations against 6 dispatch records, so neither source alone is a WIP signal.
ISSUE_TREE: Final = re.compile(r"^issue-(\d+)$")

# The optional dependency line a body may carry. Judgement where it is absent (reported as
# such), mechanical where it is present.
BLOCKED_BY: Final = re.compile(r"^\s*Blocked-by:\s*#(\d+)\s*$", re.MULTILINE)

READY_LABEL: Final = "ready-for-agent"

# The verbs that amend the policy. Each one demands a `--ruling`; the rest only read.
WRITE_VERBS: Final = frozenset({"freeze", "open", "wip", "package"})

# Bounded, and short. Every `gh` read here is a refinement of an answer this tool can already
# give without it, so a slow tracker must cost a moment and never a turn.
GH_TIMEOUT_S: Final = 20.0

# `git status --porcelain` prefixes every path with two status columns and a space.
STATUS_PREFIX: Final = 3

PACKAGE_KEYS: Final = frozenset(
    {"name", "issues", "exempt_from_freeze", "wip_reserved", "since", "ruling", "note"}
)
FREEZE_KEYS: Final = frozenset({"state", "since", "ruling"})
WIP_KEYS: Final = frozenset({"value", "since", "ruling"})
POLICY_KEYS: Final = frozenset({"version", "wip_limit", "freeze", "packages"})


class Refusal(NamedTuple):
    """One refusal: its class, what was found, and what the caller should do."""

    kind: str
    found: tuple[str, ...]
    action: str
    failure_class: str = ""

    def lines(self) -> tuple[str, ...]:
        """Render the refusal as the lines the caller reads."""
        classed = (f"class={self.failure_class}",) if self.failure_class else ()
        return (f"refusal={self.kind}", *classed, *self.found, f"action={self.action}")


# --------------------------------------------------------------------------- the document


class Freeze(NamedTuple):
    """Whether dispatch is frozen, since when, and on whose ruling."""

    state: str
    since: str
    ruling: str

    @property
    def frozen(self) -> bool:
        """Whether this entry stops a dispatch."""
        return self.state == FROZEN

    def document(self) -> dict[str, object]:
        """Render this entry as it is written."""
        return {"state": self.state, "since": self.since, "ruling": self.ruling}


class WipLimit(NamedTuple):
    """How many issues may be in flight at once, and on whose ruling."""

    value: int
    since: str
    ruling: str

    def document(self) -> dict[str, object]:
        """Render this entry as it is written."""
        return {"value": self.value, "since": self.since, "ruling": self.ruling}


class Package(NamedTuple):
    """A named work package: the carve-out and the reservation the human ruled for it."""

    name: str
    issues: tuple[int, ...]
    exempt_from_freeze: bool
    wip_reserved: int
    since: str
    ruling: str
    # Free text, and deliberately part of the schema rather than a comment nobody may write:
    # a ruling's un-mechanisable half — "and retros", where a retro carries no issue number —
    # is recorded here and reported by `state`, instead of being silently dropped.
    note: str = ""

    def document(self) -> dict[str, object]:
        """Render this entry as it is written."""
        return {
            "name": self.name,
            "issues": list(self.issues),
            "exempt_from_freeze": self.exempt_from_freeze,
            "wip_reserved": self.wip_reserved,
            "since": self.since,
            "ruling": self.ruling,
            "note": self.note,
        }


class Policy(NamedTuple):
    """The whole of what GitHub cannot carry: freeze, limit, carve-outs, reservations."""

    freeze: Freeze
    wip_limit: WipLimit
    packages: tuple[Package, ...] = ()
    version: int = VERSION

    def document(self) -> dict[str, object]:
        """Render the policy exactly as it is written to disk."""
        return {
            "version": self.version,
            "freeze": self.freeze.document(),
            "wip_limit": self.wip_limit.document(),
            "packages": [package.document() for package in self.packages],
        }

    def exempting(self, issue: int) -> tuple[Package, ...]:
        """Every package whose carve-out covers this issue."""
        return tuple(p for p in self.packages if p.exempt_from_freeze and issue in p.issues)


def _refuse_policy(*found: str, action: str = "") -> Refusal:
    """Build the one refusal every unreadable policy shares."""
    return Refusal(
        "policy_invalid",
        tuple(found),
        action
        or (
            "The policy file is never hand-edited. Rewrite the entry through `just queue "
            "freeze|open|wip|package`, each carrying its `--ruling`. Not a result: nothing "
            "here says dispatch is permitted."
        ),
    )


def _entry(document: object, name: str, known: frozenset[str]) -> tuple[dict, Refusal | None]:
    """Read one policy entry, refusing an absent one, a wrong shape, or a key nobody wrote."""
    if document is None:
        return {}, _refuse_policy(f"entry={name}", "state=absent")
    if not isinstance(document, dict):
        return {}, _refuse_policy(f"entry={name}", f"type={type(document).__name__}")
    unknown = sorted(set(document) - known)
    if unknown:
        return {}, _refuse_policy(f"entry={name}", f"unknown_keys={' '.join(unknown)}")
    ruling = document.get("ruling")
    if not isinstance(ruling, str) or not ruling.strip():
        return {}, _refuse_policy(f"entry={name}", "ruling=missing")
    return document, None


def _envelope(document: object) -> Refusal | None:
    """Refuse anything that is not this reader's document at all."""
    if not isinstance(document, dict):
        return _refuse_policy(f"type={type(document).__name__}", "want=object")
    unknown = sorted(set(document) - POLICY_KEYS)
    if unknown:
        return _refuse_policy(f"unknown_keys={' '.join(unknown)}")
    if document.get("version") != VERSION:
        return _refuse_policy(f"version={document.get('version')!r}", f"want={VERSION}")
    return None


def _parse_freeze(document: object) -> tuple[Freeze | None, Refusal | None]:
    """Read the freeze entry, refusing a state outside the vocabulary."""
    entry, refusal = _entry(document, "freeze", FREEZE_KEYS)
    if refusal is not None:
        return None, refusal
    state = entry.get("state")
    if state not in (FROZEN, OPEN):
        return None, _refuse_policy("entry=freeze", f"state={state!r}", f"want={FROZEN}|{OPEN}")
    return (
        Freeze(
            state=str(state),
            since=str(entry.get("since", "")),
            ruling=str(entry["ruling"]),
        ),
        None,
    )


def _parse_wip(document: object) -> tuple[WipLimit | None, Refusal | None]:
    """Read the WIP entry, refusing a limit that is not a whole number of issues."""
    entry, refusal = _entry(document, "wip_limit", WIP_KEYS)
    if refusal is not None:
        return None, refusal
    value = entry.get("value")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None, _refuse_policy("entry=wip_limit", f"value={value!r}", "want=whole number")
    return (
        WipLimit(
            value=value,
            since=str(entry.get("since", "")),
            ruling=str(entry["ruling"]),
        ),
        None,
    )


def parse_policy(document: object) -> tuple[Policy | None, Refusal | None]:
    """Read a policy document strictly, or say precisely what could not be read.

    Strict on every axis a hand-edit moves: an unknown key, a missing entry, a missing or
    empty `ruling`, a state outside the vocabulary, a limit that is not a whole number. Each
    of those refuses `policy_invalid` and none of them is a result — a policy nobody can parse
    is not a policy that permits.
    """
    refusal = _envelope(document)
    if refusal is not None:
        return None, refusal
    entries = document if isinstance(document, dict) else {}

    freeze, refusal = _parse_freeze(entries.get("freeze"))
    if refusal is not None or freeze is None:
        return None, refusal
    wip_limit, refusal = _parse_wip(entries.get("wip_limit"))
    if refusal is not None or wip_limit is None:
        return None, refusal
    packages, refusal = _parse_packages(entries.get("packages", []))
    if refusal is not None:
        return None, refusal
    return Policy(freeze=freeze, wip_limit=wip_limit, packages=packages), None


def _parse_package(block: object, label: str) -> tuple[Package | None, Refusal | None]:
    """Read one carve-out entry, refusing anything a hand-edit could have put in it."""
    entry, refusal = _entry(block, label, PACKAGE_KEYS)
    if refusal is not None:
        return None, refusal
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, _refuse_policy(f"entry={label}", "name=missing")
    issues = entry.get("issues")
    if not isinstance(issues, list) or not all(
        isinstance(n, int) and not isinstance(n, bool) for n in issues
    ):
        return None, _refuse_policy(f"entry={label}", f"issues={issues!r}", "want=[int]")
    reserved = entry.get("wip_reserved", 0)
    if not isinstance(reserved, int) or isinstance(reserved, bool) or reserved < 0:
        return None, _refuse_policy(f"entry={label}", f"wip_reserved={reserved!r}")
    exempt = entry.get("exempt_from_freeze", False)
    if not isinstance(exempt, bool):
        return None, _refuse_policy(f"entry={label}", f"exempt_from_freeze={exempt!r}")
    return (
        Package(
            name=name,
            issues=tuple(sorted(set(issues))),
            exempt_from_freeze=exempt,
            wip_reserved=reserved,
            since=str(entry.get("since", "")),
            ruling=str(entry["ruling"]),
            note=str(entry.get("note", "")),
        ),
        None,
    )


def _parse_packages(document: object) -> tuple[tuple[Package, ...], Refusal | None]:
    """Read the carve-out list, refusing anything a hand-edit could have put there."""
    if not isinstance(document, list):
        return (), _refuse_policy("entry=packages", f"type={type(document).__name__}")
    packages: list[Package] = []
    for index, block in enumerate(document):
        name = block.get("name") if isinstance(block, dict) else None
        label = f"packages[{index}]" + (f" name={name}" if isinstance(name, str) else "")
        package, refusal = _parse_package(block, label)
        if refusal is not None or package is None:
            return (), refusal
        packages.append(package)
    return tuple(packages), None


# ------------------------------------------------------------------------------ the store


class Store(NamedTuple):
    """Where the policy lives and where transitions are sent."""

    directory: Path = DEFAULT_QUEUE_DIR
    endpoint: str = ""

    @property
    def policy_path(self) -> Path:
        """The state document."""
        return self.directory / POLICY_FILE

    @property
    def journal(self) -> Path:
        """Where every write is recorded, whether or not the collector took it."""
        return self.directory / TRANSITION_JOURNAL


def read_raw(store: Store) -> tuple[object, Refusal | None]:
    """Read the file as JSON, refusing an absent one and an unparseable one separately."""
    path = store.policy_path
    if not path.exists():
        return None, Refusal(
            "policy_absent",
            (f"path={path}",),
            (
                "No dispatch policy is recorded on this box, so nothing here says dispatch is "
                "permitted and this is not a result. Seed it from the human's rulings, one "
                'call per entry: `just queue open --ruling "..."` (or `freeze`), then '
                '`just queue wip --limit 3 --ruling "..."`.'
            ),
        )
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError, ValueError) as failure:
        return None, _refuse_policy(f"path={path}", f"error={failure}")


def read_policy(store: Store) -> tuple[Policy | None, Refusal | None]:
    """Read and validate the policy, or say why it could not be read."""
    document, refusal = read_raw(store)
    if refusal is not None:
        return None, refusal
    return parse_policy(document)


def write_policy(store: Store, policy: Policy) -> None:
    """Write the policy, replacing the file rather than editing it in place."""
    store.directory.mkdir(parents=True, exist_ok=True)
    scratch = store.policy_path.with_suffix(".json.tmp")
    scratch.write_text(json.dumps(policy.document(), indent=2) + "\n", encoding="utf-8")
    scratch.replace(store.policy_path)


def emit_transition(store: Store, verb: str, detail: Mapping[str, object], at: float) -> bool:
    """Put one policy change in OTel and in the journal beside the file.

    Emission never fails the write. A ruling that was transcribed is a ruling that was
    transcribed, and a `just queue freeze` that refused because a collector was down would be
    strictly worse than one with no telemetry — `tools/otel_event.py`'s own reasoning.
    """
    return otel_event.emit(
        otel_event.Event(
            name=TRANSITION_EVENT,
            at=at,
            attributes={"cti.queue.verb": verb, **{f"cti.queue.{k}": v for k, v in detail.items()}},
            resource={"service.name": "arma-cti-queue"},
        ),
        journal=store.journal,
        endpoint=store.endpoint,
    )


# ------------------------------------------------------------------------ deriving in flight


class Holder(NamedTuple):
    """One issue that is in flight, and every source that says so."""

    issue: int
    sources: tuple[str, ...]
    worktree: Path | None
    closed: bool = False

    def line(self) -> str:
        """Render the list row — the evidence, of which the count is only the summary."""
        return f"in_flight.{self.issue}={' '.join(self.sources)}"


class InFlight(NamedTuple):
    """The derived in-flight set, its stated floor, and what the tracker said."""

    holders: tuple[Holder, ...]
    owed: tuple[Holder, ...]
    github: str

    @property
    def issues(self) -> tuple[int, ...]:
        """The issue numbers in flight, in order."""
        return tuple(h.issue for h in self.holders)

    def lines(self) -> tuple[str, ...]:
        """Print the list, then the count it was derived from (ADR-0051, #209).

        The count is a **floor** and this says so: an agent dispatched against an issue that
        neither ran `just worktree add` nor went through `just dispatch` is invisible to it.
        The mitigation is that the list is printed, so an undercount is visible to the reader
        rather than hidden inside a number.
        """
        rows = [h.line() for h in self.holders]
        rows += [f"worktree_done_owed.{h.issue}={h.worktree}" for h in self.owed]
        rows.append(f"github={self.github}")
        rows.append(f"in_flight={len(self.holders)} floor=yes")
        return tuple(rows)


def issue_of_tree(name: str) -> int | None:
    """Read an issue number out of a worktree name, or `None` for a tree that names none.

    `agent-<hex>` is the case this exists to exclude by name, and it is excluded by not
    matching rather than by a deny-list, so any future harness tree shape is excluded too.
    """
    found = ISSUE_TREE.match(name)
    return int(found.group(1)) if found else None


def derive_in_flight(
    worktrees: Sequence[Path],
    dispatches: Sequence[tuple[int, str, bool]],
    closed: Callable[[Sequence[int]], tuple[frozenset[int], str]],
) -> InFlight:
    """Union the two sources that name an issue, then drop the ones GitHub reports closed.

    `dispatches` is `(issue, dispatch_id, finished)` per record: a record carrying an issue
    and having no `result.json` is in flight. `closed` answers for a set of issue numbers and
    says how the tracker read — an unreadable tracker keeps every issue in the count, which is
    the refusing direction, and says so rather than silently shrinking the set.
    """
    sources: dict[int, list[str]] = {}
    trees: dict[int, Path] = {}
    for path in worktrees:
        issue = issue_of_tree(path.name)
        if issue is None:
            continue
        sources.setdefault(issue, []).append(f"worktree:{path}")
        trees[issue] = path
    for issue, dispatch_id, finished in dispatches:
        if issue <= 0 or finished:
            continue
        sources.setdefault(issue, []).append(f"dispatch:{dispatch_id}")

    numbers = sorted(sources)
    shut, github = closed(numbers)
    holders = tuple(
        Holder(issue, tuple(sources[issue]), trees.get(issue), issue in shut) for issue in numbers
    )
    return InFlight(
        holders=tuple(h for h in holders if not h.closed),
        owed=tuple(h for h in holders if h.closed),
        github=github,
    )


# ----------------------------------------------------------------------------- the rungs


def freeze_refusal(policy: Policy, issue: int) -> Refusal | None:
    """Refuse a dispatch the human's freeze covers, naming the ruling and every carve-out.

    **No failure class**, and the reasoning is `tools/dispatch.py`'s off-peak rung exactly.
    CLAUDE.md's table types what a run *found*, and this refusal found nothing: no provider was
    asked, no lane was tried, no code was run. This project simply declined to spend now.
    """
    if not policy.freeze.frozen or policy.exempting(issue):
        return None
    found = [
        f"issue={issue}",
        f"freeze={policy.freeze.state}",
        f"since={policy.freeze.since}",
        f"ruling={policy.freeze.ruling}",
    ]
    if policy.packages:
        found += [
            f"carve_out.{package.name}=issues={_render_issues(package.issues)} "
            f"exempt={package.exempt_from_freeze}"
            for package in policy.packages
        ]
        found += [
            f"carve_out_note.{package.name}={package.note}"
            for package in policy.packages
            if package.note
        ]
    else:
        found.append("carve_outs=none")
    return Refusal(
        "dispatch_frozen",
        tuple(found),
        (
            "Dispatch is frozen by the ruling above and this issue is in no carve-out package. "
            "Nothing was dispatched and nothing is known about the code under test. There is no "
            "override here — no flag, no environment variable — because the freeze is the "
            "human's and only they amend it. If they have widened the carve-out, record it: "
            '`just queue package add --name "..." --issues N,... --exempt-freeze --ruling "..."`.'
        ),
    )


def _reserved_elsewhere(policy: Policy, issue: int, in_flight: Sequence[int]) -> int:
    """How many slots other packages' reservations are holding open against this issue."""
    held = 0
    for package in policy.packages:
        if package.wip_reserved <= 0 or issue in package.issues:
            continue
        taken = sum(1 for number in in_flight if number in package.issues)
        held += max(0, package.wip_reserved - taken)
    return held


def wip_refusal(policy: Policy, issue: int, in_flight: InFlight) -> Refusal | None:
    """Refuse a dispatch that would breach the ruled limit, naming the list and never a number.

    An issue already in flight does not count against itself: re-dispatching one — a resumption
    after a crash, ADR-0024's case — must not be refused for occupying the slot it already has.
    """
    limit = policy.wip_limit.value
    counted = [number for number in in_flight.issues if number != issue]
    reserved = _reserved_elsewhere(policy, issue, in_flight.issues)
    available = limit - len(counted) - reserved
    if available > 0:
        return None
    found = [
        f"issue={issue}",
        *in_flight.lines(),
        f"limit={limit}",
        f"ruling={policy.wip_limit.ruling}",
    ]
    if reserved:
        found += [
            f"reserved.{package.name}={package.wip_reserved}"
            for package in policy.packages
            if package.wip_reserved > 0 and issue not in package.issues
        ]
    return Refusal(
        "wip_reached",
        tuple(found),
        (
            "The ruled limit is reached by the list above, which is the evidence; the count is "
            "its summary and is a floor. Nothing was dispatched. Land or close one of those "
            "issues, or have the human amend the limit — `just queue wip --limit N --ruling "
            '"..."` records their words, it does not decide them.'
        ),
    )


def surface_refusal(
    issue: int, candidate: Sequence[str], others: Mapping[int, Sequence[str]]
) -> Refusal | None:
    """Refuse where two in-flight trees are writing the same paths, naming holder and paths.

    **A stated limit, not papered over:** a candidate's surface *before work starts* is not
    computable — a fresh worktree has touched nothing — so this rung cannot see a conflict at
    the moment of dispatch and does not pretend to. What it does see is two trees that are
    already writing the same files, which is the conflict that actually costs a rebase.
    Declaring a surface up front belongs to #241's readiness criteria, not to a second gate
    here (`docs/orchestration-design.md` §2).
    """
    mine = set(candidate)
    if not mine:
        return None
    for holder, paths in sorted(others.items()):
        if holder == issue:
            continue
        shared = sorted(mine & set(paths))
        if shared:
            return Refusal(
                "surface_conflict",
                (f"issue={issue}", f"holder={holder}", f"paths={' '.join(shared)}"),
                (
                    "Two in-flight trees are writing the same paths, and whichever lands second "
                    "resolves the conflict. Nothing was dispatched. Sequence them: finish or "
                    "land the holder above first."
                ),
            )
    return None


def check_refusal(
    policy: Policy, issue: int, in_flight: InFlight, surfaces: Mapping[int, Sequence[str]]
) -> Refusal | None:
    """Climb the queue's rungs for one issue and stop at the first that refuses.

    The order is the ladder's own idea, read for this surface: **the refusal that lasts longest
    is the one worth hearing.** A freeze lifts only when the human says so; the WIP limit clears
    when something lands, which is hours; a surface conflict clears when the holder lands, which
    is sooner still and is advice about sequencing rather than about permission.
    """
    refusal = freeze_refusal(policy, issue)
    if refusal is not None:
        return refusal
    refusal = wip_refusal(policy, issue, in_flight)
    if refusal is not None:
        return refusal
    return surface_refusal(issue, surfaces.get(issue, ()), surfaces)


# ------------------------------------------------------------------------------ selection


class Candidate(NamedTuple):
    """One `ready-for-agent` issue, as the tracker reported it."""

    issue: int
    title: str
    body: str = ""

    @property
    def blocked_by(self) -> int | None:
        """The optional `Blocked-by: #N` line, or `None` where the body carries none."""
        found = BLOCKED_BY.search(self.body)
        return int(found.group(1)) if found else None


class Selection(NamedTuple):
    """What `next` decided, and the whole derivation it decided it from."""

    chosen: tuple[Candidate, ...]
    considered: tuple[str, ...]
    refusal: Refusal | None = None


def select(
    policy: Policy,
    candidates: Sequence[Candidate],
    in_flight: InFlight,
    count: int,
) -> Selection:
    """Pick the next dispatchable issues, printing why every candidate survived or did not.

    Nothing here dispatches. ADR-0053's split: the machine's half ends at noticing, and the
    same reason `just watch` never messages the agent it watched.
    """
    considered: list[str] = []
    survivors: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda c: c.issue):
        reason = _drops(policy, candidate, in_flight)
        considered.append(f"considered.{candidate.issue}={reason or 'eligible'}")
        if reason is None:
            survivors.append(candidate)

    if not candidates:
        return Selection(
            (),
            tuple(considered),
            Refusal(
                "no_ready_issue",
                (f"label={READY_LABEL}", "open=0"),
                "Nothing is labelled ready-for-agent. Triage, or file the work first.",
            ),
        )
    if not survivors:
        frozen_out = all(policy.freeze.frozen and not policy.exempting(c.issue) for c in candidates)
        if frozen_out:
            return Selection((), tuple(considered), freeze_refusal(policy, candidates[0].issue))
        return Selection(
            (),
            tuple(considered),
            Refusal(
                "no_ready_issue",
                (f"label={READY_LABEL}", f"open={len(candidates)}", *considered),
                (
                    "Every ready issue was dropped for the reason beside it above. Nothing was "
                    "dispatched and nothing was selected."
                ),
            ),
        )

    room = policy.wip_limit.value - len(in_flight.issues)
    if room <= 0:
        return Selection((), tuple(considered), wip_refusal(policy, survivors[0].issue, in_flight))
    return Selection(tuple(survivors[: min(count, room)]), tuple(considered))


def _drops(policy: Policy, candidate: Candidate, in_flight: InFlight) -> str | None:
    """Why this candidate is not dispatchable, or `None` where it is."""
    if candidate.issue in in_flight.issues:
        return "already-in-flight"
    if policy.freeze.frozen and not policy.exempting(candidate.issue):
        return "frozen-and-not-carved-out"
    blocked = candidate.blocked_by
    if blocked is not None:
        return f"blocked-by-{blocked}"
    return None


# ------------------------------------------------------------------- reading the real box


def _run(argv: Sequence[str], cwd: Path | None = None, timeout: float | None = None) -> str:
    """Run a read-only command and return its stdout, or the empty string when it failed."""
    try:
        done = subprocess.run(  # noqa: S603
            list(argv),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def worktree_paths(root: Path) -> tuple[Path, ...]:
    """Every registered worktree path, from git's own porcelain."""
    porcelain = _run(["git", "worktree", "list", "--porcelain"], cwd=root)
    return tuple(
        Path(line.split(" ", 1)[1].strip())
        for line in porcelain.splitlines()
        if line.startswith("worktree ")
    )


def dispatch_records(directory: Path) -> tuple[tuple[int, str, bool], ...]:
    """Read `(issue, dispatch_id, finished)` from every dispatch record on this box."""
    if not directory.is_dir():
        return ()
    records: list[tuple[int, str, bool]] = []
    for record in sorted(directory.iterdir()):
        plan = record / "dispatch.json"
        if not plan.is_file():
            continue
        try:
            document = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        issue = document.get("issue", 0) if isinstance(document, dict) else 0
        if not isinstance(issue, int) or isinstance(issue, bool):
            continue
        records.append((issue, record.name, (record / "result.json").is_file()))
    return tuple(records)


def closed_issues(numbers: Sequence[int]) -> tuple[frozenset[int], str]:
    """Ask the tracker which of these issues it reports closed, and say how the read went.

    A tracker this could not reach keeps every issue in the count — the refusing direction —
    and reports `unreadable` rather than an empty set, because a check that could not run is
    not a check that passed (#41's shape).
    """
    if not numbers:
        return frozenset(), "not-needed"
    if shutil.which("gh") is None:
        return frozenset(), "unreadable:no-gh"
    shut: set[int] = set()
    for number in numbers:
        out = _run(
            ["gh", "issue", "view", str(number), "--json", "state", "--jq", ".state"],
            timeout=GH_TIMEOUT_S,
        ).strip()
        if not out:
            return frozenset(), f"unreadable:issue-{number}"
        if out.upper() == "CLOSED":
            shut.add(number)
    return frozenset(shut), "read"


def ready_candidates() -> tuple[tuple[Candidate, ...], Refusal | None]:
    """Read the `ready-for-agent` issues live, never from a copy."""
    if shutil.which("gh") is None:
        return (), Refusal(
            "github_unreadable",
            ("tool=gh", "state=not-on-path"),
            (
                "The tracker is the candidate list and it could not be read, so this is not a "
                "result. Install `gh` and authenticate it."
            ),
            failure_class="infra_unavailable",
        )
    out = _run(
        [
            "gh",
            "issue",
            "list",
            "--label",
            READY_LABEL,
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,title,body",
        ],
        timeout=GH_TIMEOUT_S,
    )
    try:
        document = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        document = None
    if not isinstance(document, list):
        return (), Refusal(
            "github_unreadable",
            ("tool=gh", f"label={READY_LABEL}", "read=failed"),
            (
                "`gh issue list` returned nothing this could parse. Not a result: no candidate "
                "list was read, so no candidate was chosen and none was ruled out."
            ),
            failure_class="infra_unavailable",
        )
    return (
        tuple(
            Candidate(
                issue=int(row.get("number", 0)),
                title=str(row.get("title", "")),
                body=str(row.get("body") or ""),
            )
            for row in document
            if isinstance(row, dict)
        ),
        None,
    )


def tree_surface(path: Path) -> tuple[str, ...]:
    """Every path this worktree is writing: unlanded commits plus what is not yet committed."""
    if not path.is_dir():
        return ()
    landed = _run(["git", "diff", "--name-only", "origin/main...HEAD"], cwd=path)
    working = _run(["git", "status", "--porcelain"], cwd=path)
    touched = {line.strip() for line in landed.splitlines() if line.strip()}
    touched |= {
        line[STATUS_PREFIX:].strip() for line in working.splitlines() if len(line) > STATUS_PREFIX
    }
    return tuple(sorted(touched))


def surfaces_of(in_flight: InFlight) -> dict[int, tuple[str, ...]]:
    """Read the surface every in-flight tree is writing, by issue."""
    return {
        holder.issue: tree_surface(holder.worktree)
        for holder in in_flight.holders
        if holder.worktree is not None
    }


def gather(root: Path, dispatch_dir: Path) -> InFlight:
    """Derive the in-flight set from this box, using every source that names an issue."""
    return derive_in_flight(worktree_paths(root), dispatch_records(dispatch_dir), closed_issues)


# ------------------------------------------------------------------------------- the writes


def _render_issues(issues: Sequence[int]) -> str:
    """Render an issue set the way `--issues` accepts it back: ranges collapsed."""
    if not issues:
        return "none"
    parts: list[str] = []
    run_start = run_end = issues[0]
    for number in issues[1:]:
        if number == run_end + 1:
            run_end = number
            continue
        parts.append(str(run_start) if run_start == run_end else f"{run_start}-{run_end}")
        run_start = run_end = number
    parts.append(str(run_start) if run_start == run_end else f"{run_start}-{run_end}")
    return ",".join(parts)


def parse_issues(text: str) -> tuple[tuple[int, ...], Refusal | None]:
    """Read `221-230,238` into issue numbers, refusing anything else."""
    numbers: set[int] = set()
    for chunk in text.split(","):
        piece = chunk.strip()
        if not piece:
            continue
        low, dash, high = piece.partition("-")
        if not low.isdigit() or (dash and not high.isdigit()):
            return (), Refusal(
                "bad_issue_list",
                (f"got={piece}",),
                "Issues are numbers and ranges: `--issues 221-230,238`.",
            )
        first, last = int(low), int(high or low)
        if last < first:
            return (), Refusal(
                "bad_issue_list",
                (f"got={piece}", "range=descending"),
                "A range runs upwards: `--issues 221-230`.",
            )
        numbers.update(range(first, last + 1))
    if not numbers:
        return (), Refusal(
            "bad_issue_list",
            ("got=empty",),
            "A package names the issues it covers: `--issues 221-230,238`.",
        )
    return tuple(sorted(numbers)), None


def read_for_write(store: Store) -> tuple[dict, Refusal | None]:
    """Read the document a write is about to amend, refusing rather than overwriting a mess.

    An absent file is where seeding starts and is not a refusal here; anything present that
    this reader does not recognise is, because overwriting a policy nobody could parse would
    destroy the evidence of what was in it.
    """
    if not store.policy_path.exists():
        return {}, None
    document, refusal = read_raw(store)
    if refusal is not None:
        return {}, refusal
    if not isinstance(document, dict):
        return {}, _refuse_policy(f"type={type(document).__name__}", "want=object")
    unknown = sorted(set(document) - POLICY_KEYS)
    if unknown:
        return {}, _refuse_policy(f"unknown_keys={' '.join(unknown)}")
    return document, None


def _write(store: Store, document: dict, verb: str, detail: Mapping[str, object]) -> None:
    """Write the amended document and record the transition beside it."""
    document["version"] = VERSION
    document.setdefault("packages", [])
    store.directory.mkdir(parents=True, exist_ok=True)
    scratch = store.policy_path.with_suffix(".json.tmp")
    scratch.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    scratch.replace(store.policy_path)
    emit_transition(store, verb, detail, datetime.now(tz=UTC).timestamp())


def set_freeze(
    store: Store, state: str, ruling: str, now: str
) -> tuple[tuple[str, ...], Refusal | None]:
    """Record the human's freeze, or its lifting, with the ruling it came from."""
    document, refusal = read_for_write(store)
    if refusal is not None:
        return (), refusal
    document["freeze"] = {"state": state, "since": now, "ruling": ruling}
    _write(store, document, f"freeze:{state}", {"state": state, "ruling": ruling})
    return (f"freeze={state}", f"since={now}", f"ruling={ruling}"), None


def set_wip(
    store: Store, limit: int, ruling: str, now: str
) -> tuple[tuple[str, ...], Refusal | None]:
    """Record the ruled WIP limit with the ruling it came from."""
    document, refusal = read_for_write(store)
    if refusal is not None:
        return (), refusal
    document["wip_limit"] = {"value": limit, "since": now, "ruling": ruling}
    _write(store, document, "wip", {"value": limit, "ruling": ruling})
    return (f"wip_limit={limit}", f"since={now}", f"ruling={ruling}"), None


def add_package(
    store: Store,
    package: Package,
) -> tuple[tuple[str, ...], Refusal | None]:
    """Record a carve-out package, replacing any entry of the same name."""
    document, refusal = read_for_write(store)
    if refusal is not None:
        return (), refusal
    packages = [
        block
        for block in document.get("packages", [])
        if not (isinstance(block, dict) and block.get("name") == package.name)
    ]
    packages.append(package.document())
    document["packages"] = packages
    _write(
        store,
        document,
        "package:add",
        {"name": package.name, "issues": len(package.issues), "ruling": package.ruling},
    )
    return (
        (
            f"package={package.name}",
            f"issues={_render_issues(package.issues)}",
            f"exempt_from_freeze={package.exempt_from_freeze}",
            f"wip_reserved={package.wip_reserved}",
            f"since={package.since}",
            f"ruling={package.ruling}",
        ),
        None,
    )


def drop_package(
    store: Store, name: str, ruling: str, now: str
) -> tuple[tuple[str, ...], Refusal | None]:
    """Remove a carve-out package, refusing a name the policy does not carry."""
    document, refusal = read_for_write(store)
    if refusal is not None:
        return (), refusal
    packages = document.get("packages", [])
    kept = [
        block for block in packages if not (isinstance(block, dict) and block.get("name") == name)
    ]
    if len(kept) == len(packages):
        return (), Refusal(
            "no_such_package",
            (f"name={name}", f"known={' '.join(_names(packages)) or 'none'}"),
            "Name a package the policy carries. Nothing was changed.",
        )
    document["packages"] = kept
    _write(store, document, "package:drop", {"name": name, "ruling": ruling})
    return (f"dropped={name}", f"since={now}", f"ruling={ruling}"), None


def _names(packages: Iterable[object]) -> tuple[str, ...]:
    """Every package name in a raw document."""
    return tuple(
        str(block["name"])
        for block in packages
        if isinstance(block, dict) and isinstance(block.get("name"), str)
    )


# ------------------------------------------------------------------------------ rendering


def state_lines(store: Store, policy: Policy, in_flight: InFlight) -> tuple[str, ...]:
    """Every policy entry with its ruling, then the in-flight list, then the count."""
    lines = [
        f"policy={store.policy_path}",
        f"version={policy.version}",
        f"freeze={policy.freeze.state}",
        f"freeze_since={policy.freeze.since}",
        f"freeze_ruling={policy.freeze.ruling}",
        f"wip_limit={policy.wip_limit.value}",
        f"wip_since={policy.wip_limit.since}",
        f"wip_ruling={policy.wip_limit.ruling}",
        f"packages={len(policy.packages)}",
    ]
    for package in policy.packages:
        lines += [
            f"package.{package.name}.issues={_render_issues(package.issues)}",
            f"package.{package.name}.exempt_from_freeze={package.exempt_from_freeze}",
            f"package.{package.name}.wip_reserved={package.wip_reserved}",
            f"package.{package.name}.since={package.since}",
            f"package.{package.name}.ruling={package.ruling}",
        ]
        if package.note:
            lines.append(f"package.{package.name}.note={package.note}")
    lines += list(in_flight.lines())
    return tuple(lines)


def next_lines(selection: Selection, in_flight: InFlight) -> tuple[str, ...]:
    """Render the candidates with their derivation, list before count."""
    lines = [*in_flight.lines(), *selection.considered]
    lines += [f"candidate={c.issue} title={c.title}" for c in selection.chosen]
    lines.append(f"selected={len(selection.chosen)}")
    return tuple(lines)


# ----------------------------------------------------------------------------------- CLI


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse one verb and what it takes."""
    parser = argparse.ArgumentParser(prog="just queue", description=__doc__)
    parser.add_argument(
        "--queue-dir",
        default=os.environ.get("CTI_QUEUE_DIR", str(DEFAULT_QUEUE_DIR)),
    )
    # `CTI_QUEUE_ROOT` and `--dispatch-dir` are `CTI_BREAKER_DIR`'s twins and exist for its
    # reason: `tools/dispatch.sh` forks a fresh process, which no in-process patch reaches, so
    # a test needs the derivation pointed at its own trees and records rather than at this
    # box's. Neither touches the freeze, which has no override of any kind.
    parser.add_argument("--root", default=os.environ.get("CTI_QUEUE_ROOT", ""))
    parser.add_argument(
        "--dispatch-dir",
        default=os.environ.get("CTI_DISPATCH_DIR", str(Path.home() / ".arma-cti" / "dispatches")),
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    verbs.add_parser("state", help="every entry with its ruling, the in-flight list, the count")
    following = verbs.add_parser("next", help="the next dispatchable issues, with the derivation")
    following.add_argument("--count", type=int, default=1)
    checking = verbs.add_parser("check", help="one issue, as an exit code: the pre-dispatch read")
    checking.add_argument("--issue", type=int, required=True)

    for name, help_text in (
        ("freeze", "record a dispatch freeze"),
        ("open", "record the freeze lifting"),
    ):
        verb = verbs.add_parser(name, help=help_text)
        verb.add_argument("--ruling", default="")

    wip = verbs.add_parser("wip", help="record the ruled WIP limit")
    wip.add_argument("--limit", type=int, required=True)
    wip.add_argument("--ruling", default="")

    package = verbs.add_parser("package", help="record or drop a carve-out package")
    actions = package.add_subparsers(dest="action", required=True)
    adding = actions.add_parser("add", help="record a carve-out package")
    adding.add_argument("--name", required=True)
    adding.add_argument("--issues", default="")
    adding.add_argument("--exempt-freeze", action="store_true")
    adding.add_argument("--reserve", type=int, default=0)
    adding.add_argument("--note", default="")
    adding.add_argument("--ruling", default="")
    dropping = actions.add_parser("drop", help="remove a carve-out package")
    dropping.add_argument("--name", required=True)
    dropping.add_argument("--ruling", default="")

    return parser.parse_args(argv)


def missing_ruling(args: argparse.Namespace) -> Refusal | None:
    """Refuse any write that cannot say where its rule came from.

    This is the whole discipline in four lines. A policy entry without a ruling is an
    orchestrator's inference recorded as a human's decision, which is precisely what the
    human's own carve-out wording forbids ("confirm the scope, do not infer it").
    """
    if not str(getattr(args, "ruling", "") or "").strip():
        return Refusal(
            "ruling_required",
            (f"verb={args.verb}", "ruling=missing"),
            (
                "Every policy entry quotes the ruling it came from: `--ruling \"<the human's "
                'words, or the issue-comment URL>"`. Nothing was written. An entry without a '
                "ruling is an inference recorded as a decision."
            ),
        )
    return None


def emit(lines: Iterable[str], code: int) -> int:
    """Print to the stream the exit code implies, and return it."""
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def _root(args: argparse.Namespace) -> Path:
    """Where the worktree registrations are read from."""
    if args.root:
        return Path(args.root).expanduser()
    porcelain = _run(["git", "worktree", "list", "--porcelain"], cwd=Path.cwd())
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            return Path(line.split(" ", 1)[1].strip())
    return Path.cwd()


def _write_verb(
    args: argparse.Namespace, store: Store, now: str
) -> tuple[tuple[str, ...], Refusal | None]:
    """Run the write the verb names, having already checked it carries a ruling."""
    if args.verb in {"freeze", "open"}:
        return set_freeze(store, FROZEN if args.verb == "freeze" else OPEN, args.ruling, now)
    if args.verb == "wip":
        if args.limit < 0:
            return (), Refusal(
                "bad_limit",
                (f"limit={args.limit}",),
                "A WIP limit is zero or more. Zero is a freeze by another name; use `freeze`.",
            )
        return set_wip(store, args.limit, args.ruling, now)
    if args.action == "drop":
        return drop_package(store, args.name, args.ruling, now)
    issues, refusal = parse_issues(args.issues)
    if refusal is not None:
        return (), refusal
    return add_package(
        store,
        Package(
            name=args.name,
            issues=issues,
            exempt_from_freeze=args.exempt_freeze,
            wip_reserved=args.reserve,
            since=now,
            ruling=args.ruling,
            note=args.note,
        ),
    )


def _read_verb(
    args: argparse.Namespace, store: Store, policy: Policy, in_flight: InFlight
) -> tuple[tuple[str, ...], int]:
    """Answer a read verb: the whole state, one issue's verdict, or the next candidates."""
    if args.verb == "state":
        return state_lines(store, policy, in_flight), 0
    if args.verb == "check":
        found = check_refusal(policy, args.issue, in_flight, surfaces_of(in_flight))
        if found is not None:
            return found.lines(), EXIT_REFUSED
        return (f"issue={args.issue}", "queue=clear", *in_flight.lines()), 0
    candidates, refusal = ready_candidates()
    if refusal is not None:
        return refusal.lines(), EXIT_REFUSED
    selection = select(policy, candidates, in_flight, max(1, args.count))
    if selection.refusal is not None:
        return (*selection.considered, *selection.refusal.lines()), EXIT_REFUSED
    return next_lines(selection, in_flight), 0


def _run_write(args: argparse.Namespace, store: Store) -> int:
    """Run a write verb, having first insisted it quotes a ruling."""
    refusal = missing_ruling(args)
    if refusal is not None:
        return emit(refusal.lines(), EXIT_REFUSED)
    lines, refusal = _write_verb(args, store, datetime.now(tz=UTC).isoformat())
    return emit(refusal.lines(), EXIT_REFUSED) if refusal else emit(lines, 0)


def main(argv: list[str] | None = None) -> int:
    """Read or write the dispatch policy, and never dispatch anything."""
    args = parse_args(argv)
    store = Store(directory=Path(args.queue_dir).expanduser())
    if args.verb in WRITE_VERBS:
        return _run_write(args, store)

    policy, refusal = read_policy(store)
    if refusal is not None or policy is None:
        return emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    in_flight = gather(_root(args), Path(args.dispatch_dir).expanduser())
    lines, code = _read_verb(args, store, policy, in_flight)
    return emit(lines, code)


if __name__ == "__main__":
    sys.exit(main())
