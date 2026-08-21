"""`just watch-report`'s gate-duration half: the gate got durably slower, said once.

Between 2026-08-05 and 2026-08-19 this project's gate roughly doubled and nobody
noticed for two weeks (#446). Nothing recorded how long a gate run took, so the
only evidence was Claude Code's session transcripts, an accident nobody
committed to retaining. And no commit caused it: the suite's test count grew
2.43× while its measured work grew 1.23×, because `pytest-xdist`'s `--dist load`
charges a scheduling penalty that scales with test count — every commit made the
gate slightly worse and no bisect could stand out. A regression with no guilty
commit is exactly the kind only a standing measurement catches.

So every `just unit` and `just fast` run attempts one row in
`~/.arma-cti/gate-clock/records.jsonl` (outside every worktree, accumulating
across branches and lanes). A dispatched run that cannot write there queues its
row in a sandbox-writable outbox, or reports the outbox write failure. Each
active session holds that outbox's
`flock`; after the session exits, the unsandboxed dispatcher appends its rows
under the canonical history's file lock. A stable per-history temp root lets
the next dispatcher find every unlocked outbox whose dispatcher died. Each new
row has a delivery id, so a retry after canonical append but before outbox
cleanup does not append it twice. A failed host append is reported and leaves
the outbox in place. This module's `report` — folded into
`just watch-report` — compares a median of recent green runs against an
**anchor** held in `tools/gate-clock-anchor.json`, in the tree.

**Coverage is unknowable.** Recording failures before #472 were not counted,
and a non-dispatched recorder still has no host harness that could durably count
a failed write. `history` states that beside every numeric sample. While host
temp storage remains, a successfully queued row is recoverable after dispatcher
death; the mechanism does not survive host temp cleanup, recover old rows, or
manufacture a denominator.

**Anchored, not rolling, and that was measured rather than argued.** A
self-normalising watcher — trailing N runs against the previous N — is the
obvious design and normalises to exactly the drift it exists to catch. Over the
454 `just unit` runs of the regression window, the worst step a rolling 30-vs-30
watcher ever saw was 1.41× (an artefact of the pre-#197 tail) against
steady-state steps of 0.85× to 1.27×, indistinguishable from box noise: any
threshold low enough to fire would have false-fired constantly while the gate
doubled underneath it. Anchored to the post-#197 median it fires on 2026-08-10,
ten days before anyone noticed:

    2026-08-05  109s  1.00×   (anchor, post-#197)
    2026-08-06  110s  1.01×
    2026-08-08  124s  1.14×
    2026-08-10  150s  1.37×   <- a 1.25× threshold fires here
    2026-08-13  169s  1.55×
    2026-08-15  192s  1.76×
    2026-08-17  232s  2.13×

**The threshold is 1.25× because that is what this table supports**: it fires
on the 08-10 shape and stays silent on 08-06 (1.01×) and 08-08 (1.14×). Box
load varies by about ±30% between runs here and day medians swing from 148 s to
232 s within a week, so the comparison is a median over the last
`REPORT_WINDOW` green runs, never a single run, and the report says nothing
until `MIN_SAMPLE` green runs exist. If the threshold or the window is ever
adjusted, adjust it by re-running this derivation over the records this module
will by then hold, not by argument — three separate inherited inferences about
the same suite (#442's 1.11×, 1.6×, 1.6× to 2.2×) were all wrong, and one
eight-minute run settled the figure at 1.23×.

**The anchor moves only by hand.** A number that moves by itself cannot detect
slow growth; a number only a human or a retro moves, deliberately and in a
visible diff, can. This file's counterpart `tools/mutation-baseline.json` is
the inverse ratchet — there a recorded rate rises automatically and *lowering*
is the hand-edit; here the expected duration *falls* when a deliberate
improvement is re-measured and *raising* it is the hand-edit. Nothing in this
module writes the anchor file, under any verb, ever. A landing that speeds the
gate up (#442, #447) re-derives and lowers it as part of itself, so a deliberate
improvement becomes the new expectation instead of being reported forever as
drift in the wrong direction.

**Each entry's `set` bounds the window, so lowering the anchor cannot
false-fire against the rows that predate it.** The records accumulate across
branches and lanes with no reset, so an anchor lowered from 176 s to 110 s
would otherwise sit beside ten green rows at ~176 s and fire at ~1.6× on every
orchestrator turn until new rows crowded them out — the first use of the
maintenance path producing the false alarms the report exists to avoid. Only
green runs at or after the entry's `set` enter the median, which after a
re-set leaves the recipe at `insufficient_sample` until five post-`set` greens
exist: unknown, never healthy — the honest state of a re-set instrument. `set`
takes a date or a full ISO timestamp: a date bounds from that day's start,
while a timestamp bounds from the moment it names — the shape a same-day re-set
needs, because an implementer who improves the gate on a day they have already
run it leaves that morning's slower rows on disk, and a day-granular bound
would keep them in the window against the lowered anchor. A row whose `at`
will not parse is excluded rather than guessed at.

**A broken anchor is the one state where noise is correct.** The file ships in
the tree with both recipes anchored, so a file that is missing, unparseable, or
carrying a half-edited entry (a quoted number, a dropped key) is a broken
instrument and not the shipped unset state: every recipe it leaves unreadable
prints one line saying so, ahead of the Arma-tier suppression, because it
claims nothing about the gate and a busy box does not license a broken
instrument's silence. Silence there would be exactly the failure #446 exists
to prevent, reintroduced inside the fix. `just check`'s `check-gate-clock` leg
makes the same finding a red, so a half-edited anchor cannot land through its
own gate. A file that fails to *name* a recipe the recorder writes is the same
damage — a deleted key, or one misspelled into a key nothing reads — so a
missing recipe is a problem too, and a key outside the recorder's recipes is
flagged where it sits, which is how a misspelling presents. `assess`'s
`anchor_unset` rung stays as a backstop for a state the loader no longer
produces; the recipes the file must name are `RECIPES`, the set the recorder
writes rows for, so the file and the loader cannot drift apart silently.

**The wall is read from the kernel's monotonic clock.** Both ends of a recorded
wall read `/proc/uptime` — `CLOCK_REALTIME` steps under NTP and a step mid-run
would record a duration the suite never cost. The row's `at` is wall-clock
provenance for a later investigation, never an input to the wall.

**The fired line carries its own load context.** The rows' `load_1m` and
`foreign_gate_processes` fields separate a busy box from a regression when
investigated — and a loaded stretch is not always visible at report time (a
Windows play session does not appear in a `/proc` scan), while the rows it
leaves behind stay in the window after the load ends. So the one line that
fires names the window's load-1m median, and the reader can tell a busy box
from the line itself rather than from an investigation the line invites.

**Only green runs are compared.** A red run is faster — the #446 investigation
has a 306-failure run finishing in 221 s where the green run took 271 s — so a
red admitted to the median flatters it. Red rows are still recorded, with their
status, because the history is the point of recording; they are excluded from
every comparison.

**A run whose diff gave the mutation tier nothing to work on is a different
measurement, and the row records which (#466).** Every other leg of both
recipes prices the whole tree whatever the diff holds — `ruff check .`,
`ty check`, `hemtt check -p -e`, `gitleaks dir .`, the whole pytest suite —
so `just mutation` is the one leg whose cost the diff moves, and `just fast`
carries it while `just unit` does not. `mutation_targets` is therefore the
count of what that tier will do work on: the test modules
`tools/mutation_smoke.py`'s `in_scope` selects, **minus** the ones its
`NO_MUTABLE_SUBJECT` list excuses, plus its Rust arm as one — obtained at
record time by asking those names of the tier against the tree the run just
gated. No flag declares it, ever.

**Targets selected, not mutants planted, and the noun is deliberate.** What
the comparison cares about is the expensive half, which is planting; how many
mutants a run planted is decided inside a run this recorder cannot see and
could not re-derive without paying the tier's cost a second time. What it can
read cheaply is the selection, and selecting is a fair stand-in for planting
exactly where selecting a target commits the tier to work: `smoke` runs one
coverage-instrumented pytest pass of the module (`measure`) before it can know
whether there is anything to plant on, so a target that plants nothing has
already been paid for. The word is the tier's own — `mutation_smoke`'s
`targets` are the test modules a run smokes, while its `subject` is the
product module a target is measured against, a different noun and the one this
field's first draft wrongly borrowed.

**The exempt list is the one place where selecting costs nothing, which is
why it is subtracted.** `_judge` prints an `-- exempt:` line for a target in
`NO_MUTABLE_SUBJECT` and moves on without calling `smoke`, so a run whose only
changed test module is exempt plants nothing and costs a floor-priced run —
the shape `fast`'s window exists to keep out. Two of that list's five entries
are on it *because* they are expensive (`test_client_lock.py` at 216.6 s,
`test_pool_slots.py` at 190.8 s), so counting them would put a row's biggest
claimed target where the run spent none of its time. Checked rather than
assumed, and it is the only such place: every non-exempt target reaches
`measure`; a target whose `measure` refuses (not green on its own, or past the
collect timeout) has run it anyway and reds the recipe besides, so no green row
carries one; and the Rust arm has no exemption list at all — in scope means
`cargo-mutants` runs.

**It is not a docs-only flag and must not be read as one.** Zero means the
mutation tier had nothing to work on. A docs-only diff earns that; so does a
config or comment edit; so does a change to a product module that adds or
rewrites no test module. Those three cost the same, and the cost is what this
instrument measures — a field that separated them by what the diff looked like
would be a token standing in for the thing (#458 tracks eight of that class in
this tree). The convenient shape here was a `docs_only` boolean, which would
have had to call that third case a code run while it cost what a docs run
costs; this field names what it counted instead, and answers "did the tier have
work" rather than "was this documentation".

**`fast`'s comparison excludes the zero rows; `unit` records the count and
compares on it not at all.** Excluded rather than weighted, because the
93.6 s anchor was derived from four runs whose diff carried
`tests/unit/test_generate_seats.py` (`6a769cb`) and so paid the mutation leg:
the like-for-like population is the runs that paid it too, and a second
anchor derived from the cheap kind is a derivation nobody has done. Direction
settles the rest — the issue's reading has #450's three docs-only landings at
81.49, 82.53 and 81.35 s, the floor of a recorded span reaching 231 s, and a
median those drag down makes a real slowdown read as ordinary, the
false-negative direction on an instrument built to catch slow growth. `unit`
is left unfiltered because its own legs are diff-independent: a zero-target
`unit` row is the same measurement as any other, and filtering it would only
shrink the sample.

**Rows written before #466 carry no count and read as `None` — unclassified,
never guessed at.** They leave `fast`'s window alongside the zero rows, so
the recipe stands at `insufficient_sample` until five classified green runs
exist: the same honest unknown a re-set anchor reads. `history` counts both
kinds among a recipe's green runs and names each on its line only when its
count is nonzero, so a reader can see how much of the history the window is
declining to use rather than inferring it from a shrunken median.

**It only notices.** Nothing here refuses a dispatch, trips a breaker or blocks
a landing; whether to act on the line is a judgement, and the consequences
already live in `.claude/hooks/deny-subagent-waits.py`'s threshold and the retro
cadence. `report` is quiet while the Arma tier is running (`just regress`,
`just spike`, a play session's WSL server): a gate slowed by another agent's
corpus run is a busy box, not a code regression. A play session on the Windows
host is invisible to a `/proc` scan and quiet is not guaranteed for it — the
rows' `load_1m` and `foreign_gate_processes` fields are what separates that case
when it is investigated.

**What recording costs.** One `uv run python` start per recorded recipe (~0.3 s
against a ~190 s tier, under 0.2%) and one small file write at collection time;
nothing is added to any assertion or test. The #466 count adds one import of
`tools/mutation_smoke.py` and two passes of its `changed` git reads
(`merge-base`, `diff --name-only`, `status --porcelain`) — stated as a count
rather than a duration, because nobody has timed it. `just fast` invoking
`just unit` records two rows — the unit tier's own wall and the whole
recipe's — and both are real measurements of real invocations.

The selected state directory is `CTI_GATE_CLOCK_DIR`, the seam
`CTI_WATCH_DIR`, `CTI_BREAKER_DIR` and `CTI_RC_HEALTH_DIR` exist for (#249):
without it a unit test of this reporter reads the live box, and whatever the box
happens to be carrying reddens an unrelated run. It never selects a dispatch's
canonical history: during dispatch, a row written to a different selected
directory is also queued for canonical collection, or the queue failure is
stated. Outside a dispatch, the recorder says that the canonical history does
not include it.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Final, NamedTuple
from uuid import uuid4

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path — the device gate.py and
# dispatch.py use; it is what makes mutation_smoke importable below.
sys.path.insert(0, str(Path(__file__).parent))

DEFAULT_GATE_CLOCK_DIR: Final = Path.home() / ".arma-cti" / "gate-clock"
RECORDS_NAME: Final = "records.jsonl"
CANONICAL_DIR_ENV: Final = "CTI_GATE_CLOCK_CANONICAL_DIR"
OUTBOX_DIR_ENV: Final = "CTI_GATE_CLOCK_OUTBOX_DIR"
ANCHOR_PATH: Final = Path(__file__).with_name("gate-clock-anchor.json")
PROC_UPTIME: Final = Path("/proc/uptime")

# The ref the mutation tier measures a landing against, and the tree it is
# measured in — the same pair `just mutation` itself uses, so the count below
# can never disagree with the tier it describes.
BASE_REF: Final = "origin/main"
REPO_ROOT: Final = Path(__file__).resolve().parents[1]

# The two recipes that run the gate (issue #446): a bare `just unit` is most of
# the recorded population (22.27 h of the 57.51 h the investigation measured),
# while the whole `just fast` is the figure the subagent-wait threshold applies
# to. `just check` (~10 s) and `just mutation` (~0 s) are noise against a 200 s
# tier, and a record nobody will read is not worth the line.
RECIPES: Final = ("unit", "fast")

# The recipes that carry `just mutation`, and so the only ones whose comparison
# reads `mutation_targets` (#466). Every other leg of both recipes prices the
# whole tree, so a `unit` row's count is provenance and never a filter. One
# home for that rule: `assess` and `history` both ask here.
MUTATION_LEG_RECIPES: Final = ("fast",)

# The comparison window and floor. The window is ten green runs because the
# day medians the threshold was derived from are runs-of-a-day shapes; the floor
# is five because below that a median of this box's ±30% run-to-run spread says
# more about the scheduler than about the suite.
REPORT_WINDOW: Final = 10
MIN_SAMPLE: Final = 5

# Derived, not chosen: fires on the 08-10 shape (1.37×), silent on 08-06
# (1.01×) and 08-08 (1.14×). See the header before touching this.
THRESHOLD: Final = 1.25

# The comm names an Arma server process carries under Linux (`comm` truncates
# at 15 characters, which `arma3server_x64` exactly fits).
ARMA_TIER_PREFIX: Final = "arma3server"


class Record(NamedTuple):
    """One finished gate run, as `report` reads it back."""

    at: str
    recipe: str
    wall_seconds: float
    status: int
    head: str
    tests_collected: int | None
    load_1m: float | None
    foreign_gate_processes: int | None
    mutation_targets: int | None
    record_id: str = ""


class Verdict(NamedTuple):
    """What `report` says about one recipe — a line, or the reason there is none."""

    recipe: str
    reason: str
    line: str | None


class AnchorState(NamedTuple):
    """What `load_anchors` read: the anchors, their `set` moments, and the unreadable entries."""

    anchors: dict[str, float]
    set_dates: dict[str, datetime]
    problems: dict[str, str]


def median(values: list[float]) -> float:
    """Return the middle value, averaging the middle two on an even count."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def record_document(row: Record) -> dict[str, object]:
    """Render one run as the JSONL row the next report reads."""
    document: dict[str, object] = {
        "at": row.at,
        "recipe": row.recipe,
        "wall_seconds": row.wall_seconds,
        "status": row.status,
        "head": row.head,
        "tests_collected": row.tests_collected,
        "load_1m": row.load_1m,
        "foreign_gate_processes": row.foreign_gate_processes,
        "mutation_targets": row.mutation_targets,
    }
    if row.record_id:
        document["record_id"] = row.record_id
    return document


def parse_record(document: object) -> Record | None:
    """Read one JSONL row back, answering `None` for anything malformed.

    Fail-quiet rather than fail-closed, and only on the report path: this read
    feeds the top of an orchestrator turn, so one truncated line (a box that
    died mid-append) must not take out the breaker and queue lines printed
    beside it. The malformed line stays on disk for a later look.

    A row without `mutation_targets` predates #466 and reads as `None` —
    unclassified, never guessed — which is how the fifty-odd existing records
    stay readable without re-deriving a diff nobody kept. The rows this
    branch's own runs wrote under the field's first name are in that set
    deliberately: their count was taken by a definition that included the
    exempt targets, so reading them as unclassified is the honest fate of a
    figure derived by a rule that has since changed.

    A row without `record_id` predates #472 and remains readable. Collection
    uses that legacy row's exact contents as its retry identity; every row this
    version records carries a generated id instead.
    """
    if not isinstance(document, dict):
        return None
    try:
        return Record(
            at=str(document["at"]),
            recipe=str(document["recipe"]),
            wall_seconds=float(document["wall_seconds"]),
            status=int(document["status"]),
            head=str(document.get("head", "") or ""),
            tests_collected=(
                int(document["tests_collected"])
                if document.get("tests_collected") is not None
                else None
            ),
            load_1m=(float(document["load_1m"]) if document.get("load_1m") is not None else None),
            foreign_gate_processes=(
                int(document["foreign_gate_processes"])
                if document.get("foreign_gate_processes") is not None
                else None
            ),
            mutation_targets=(
                int(document["mutation_targets"])
                if document.get("mutation_targets") is not None
                else None
            ),
            record_id=str(document.get("record_id", "") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


def records_path(gate_clock_dir: Path) -> Path:
    """Where the append-only history lives."""
    return gate_clock_dir / RECORDS_NAME


def load_records(gate_clock_dir: Path) -> tuple[Record, ...]:
    """Every readable row, oldest first; nothing at all on a missing directory."""
    path = records_path(gate_clock_dir)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    rows: list[Record] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            document = json.loads(line)
        except ValueError:
            continue
        parsed = parse_record(document)
        if parsed is not None:
            rows.append(parsed)
    return tuple(rows)


def _record_identity(row: Record) -> object:
    """Stable delivery identity, with exact legacy-row fallback."""
    return ("id", row.record_id) if row.record_id else ("legacy", row)


def _append_records(
    gate_clock_dir: Path, rows: tuple[Record, ...], *, idempotent: bool
) -> tuple[Path, int]:
    """Append rows under one file lock and return how many were new."""
    path = records_path(gate_clock_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        existing_text = handle.read()
        known = (
            {_record_identity(row) for row in load_records(gate_clock_dir)} if idempotent else set()
        )
        pending = []
        for row in rows:
            identity = _record_identity(row)
            if identity in known:
                continue
            pending.append(row)
            known.add(identity)
        handle.seek(0, os.SEEK_END)
        if existing_text and not existing_text.endswith("\n"):
            handle.write("\n")
        for row in pending:
            handle.write(json.dumps(record_document(row)) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path, len(pending)


def append_record(gate_clock_dir: Path, row: Record) -> Path:
    """Append one row, creating the state directory on first use."""
    path, _appended = _append_records(gate_clock_dir, (row,), idempotent=False)
    return path


def append_records_once(gate_clock_dir: Path, rows: tuple[Record, ...]) -> int:
    """Durably append each delivery identity at most once."""
    _path, appended = _append_records(gate_clock_dir, rows, idempotent=True)
    return appended


def record_or_queue(gate_clock_dir: Path, row: Record) -> str | None:
    """Write one row, or leave it in the dispatch outbox for the host to collect.

    The outbox is injected only by `just dispatch`. It is writable inside the
    session sandbox; the unsandboxed dispatcher appends its rows to the canonical
    history after the session exits. A caller-selected noncanonical destination is
    still written, but its row also enters the outbox so `CTI_GATE_CLOCK_DIR` cannot
    silently fork dispatched history.

    `None` means this function already reported the one non-gating failure line.
    Otherwise the string is appended to the ordinary recorded line.
    """
    canonical = Path(os.environ.get(CANONICAL_DIR_ENV, str(DEFAULT_GATE_CLOCK_DIR))).absolute()
    primary = gate_clock_dir.absolute()
    outbox_text = os.environ.get(OUTBOX_DIR_ENV, "")
    outbox = Path(outbox_text).absolute() if outbox_text else None
    try:
        append_record(primary, row)
    except OSError as primary_error:
        if outbox is None:
            failure = f"gate-clock {row.recipe} recording failed: {primary_error}"
        else:
            try:
                append_record(outbox, row)
            except OSError as outbox_error:
                failure = (
                    f"gate-clock {row.recipe} recording failed: canonical write "
                    f"failed: {primary_error}; dispatch outbox write failed: {outbox_error}"
                )
            else:
                failure = (
                    f"gate-clock {row.recipe} canonical write failed: {primary_error}; "
                    "queued for dispatch harness"
                )
        print(failure, file=sys.stderr)  # noqa: T201 — the run's report surface
        return None

    if primary == canonical:
        return ""
    if outbox is None:
        return "; canonical history does not include this row"
    try:
        append_record(outbox, row)
    except OSError as outbox_error:
        return f"; canonical collection failed: {outbox_error}"
    return "; queued for canonical collection"


def head_sha() -> str:
    """Answer the tree's HEAD, or an empty string when git cannot.

    The SHA is provenance for a later investigation, not an input to any
    decision here, so a tree without git answers "" rather than failing a gate
    run that already finished.
    """
    import subprocess  # noqa: PLC0415 — kept beside its only caller, like the hooks' readers

    try:
        done = subprocess.run(  # "git" resolves off PATH on purpose, like land.py's callers
            ["git", "rev-parse", "HEAD"],  # noqa: S607 — same reason, stated once above
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def read_collected_file() -> int | None:
    """Read the suite's collected test count from the path the recipe exported.

    `tests/unit/conftest.py` writes the count at collection time when
    `CTI_GATE_CLOCK_COLLECTED_FILE` is set, which only the recording recipes do
    — so a bare `uv run pytest`, and `just mutation`'s own runs, write nothing.
    An unreadable or non-numeric file is `None` rather than a guess.
    """
    named = os.environ.get("CTI_GATE_CLOCK_COLLECTED_FILE", "")
    if not named:
        return None
    try:
        return int(Path(named).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def read_mutation_targets(root: Path | None = None) -> int | None:
    """Count what the mutation tier will do work on in the tree this run gated.

    The tier's own selection, asked of the tier: `mutation_smoke.in_scope` for
    the Python targets and `mutation_rust.in_scope` for the shim arm, counted
    as one. Calling those rather than re-deriving them here is the whole point
    — a copy of the rule could drift from the tier whose cost it claims to
    describe, and then the field would be a token standing in for the thing
    (#458). It costs a second pass of `changed`'s git reads, which is the price
    of the count having one home.

    **`NO_MUTABLE_SUBJECT` is subtracted, because `_judge` skips those targets
    without calling `smoke` at all**: an exempt target plants nothing and costs
    nothing, so counting it would let a floor-priced run into `fast`'s window
    wearing a code run's count — this issue's own bias in a narrower form. Every
    other selected target reaches `measure`, one coverage-instrumented pytest
    pass of the module, before the tier can know whether there is anything to
    plant on; so a target that ends up planting nothing was still paid for, and
    a target whose `measure` refuses reds the recipe and never reaches a green
    row. The header states the check that this exemption is the only divergence.

    Zero means the tier has nothing to work on: a docs-only diff, a config or
    comment edit, an exempt-only diff, and a product-module change that adds or
    rewrites no test module all reach it, and all four cost the same. This is
    not a docs-only flag — `mutation_targets` answers "did the tier have work",
    never "was this documentation", and the module header states why the honest
    question is the narrower one.

    `None` only when git or the tree cannot be read; the row then carries no
    count, and `MUTATION_LEG_RECIPES`' comparison drops it as unclassified
    rather than guessing a kind for it.
    """
    repo = REPO_ROOT if root is None else root
    try:
        import mutation_rust  # noqa: PLC0415 — beside its only caller, like head_sha's subprocess
        import mutation_smoke  # noqa: PLC0415 — same reason

        targets = sum(
            1
            for name in mutation_smoke.in_scope(repo, BASE_REF)
            if name not in mutation_smoke.NO_MUTABLE_SUBJECT
        )
        if mutation_rust.in_scope(mutation_smoke.changed(repo, BASE_REF)):
            targets += 1
    except OSError:
        return None
    return targets


def had_mutation_target(row: Record) -> bool:
    """Whether this row's run gave the mutation tier something to work on.

    `False` for the cheap kind — nothing to plant against, whatever the diff
    looked like — and `False` for the rows carrying no count at all, which is
    why a comparison reading this excludes those rows rather than inventing a
    kind for them.
    """
    return (row.mutation_targets or 0) > 0


def _read_anchor_entry(name: str, entry: object) -> tuple[float, datetime] | str:
    """Return one entry's `(anchor, set moment)`, or the problem with it as a string.

    Split out of `load_anchors` so the file-level failures (missing,
    unparseable, not an object) and the per-entry ladder read separately.
    """
    if not isinstance(entry, dict):
        return f"{name} entry is not an object"
    seconds = entry.get("anchor_seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        return f"{name}.anchor_seconds is not a positive number"
    try:
        moment = as_utc(datetime.fromisoformat(str(entry["set"])))
    except (KeyError, TypeError, ValueError):
        return f"{name}.set is missing or not an ISO date or timestamp"
    return float(seconds), moment


def load_anchors(path: Path) -> AnchorState:
    """Read the anchor file: the anchors, their `set` moments, and every entry that will not read.

    The file ships in the tree with both recipes anchored, so a file that cannot
    be read at all is a broken instrument, not the unset state: every recipe in
    `RECIPES` is returned as unreadable with the reason. An entry that exists
    but is half-edited — a quoted number, a dropped key, a `set` that is neither
    an ISO date nor a timestamp — is a problem for that recipe alone. So is a
    recipe the file fails to name: the file ships naming every recipe the
    recorder writes, so a missing key — deleted, or misspelled into a key
    nothing reads — is damage rather than the unset state, and a key outside
    `RECIPES` is flagged where it sits, which is how a misspelling presents.
    `set` is required because the report bounds its window by it: an anchor
    without a set moment could not be lowered without false-firing against the
    rows that predate the change. A date bounds from that day's start; a full
    timestamp bounds from the moment it names, so a re-set on a day already run
    excludes that morning's rows.
    """
    state = AnchorState({}, {}, {})
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        reason = f"anchor file {path} cannot be read ({error.strerror or error})"
        return state._replace(problems=dict.fromkeys(RECIPES, reason))
    try:
        document = json.loads(text)
    except ValueError:
        reason = f"anchor file {path} is not valid JSON"
        return state._replace(problems=dict.fromkeys(RECIPES, reason))
    if not isinstance(document, dict):
        reason = f"anchor file {path} is not an object"
        return state._replace(problems=dict.fromkeys(RECIPES, reason))
    anchors: dict[str, float] = {}
    set_dates: dict[str, datetime] = {}
    problems: dict[str, str] = {}
    for recipe, entry in document.items():
        if recipe.startswith("_"):
            continue
        name = str(recipe)
        if name not in RECIPES:
            problems[name] = (
                f"{name} is not a recipe the recorder writes (expected one of {', '.join(RECIPES)})"
            )
            continue
        read = _read_anchor_entry(name, entry)
        if isinstance(read, str):
            problems[name] = read
        else:
            anchors[name], set_dates[name] = read
    for recipe in RECIPES:
        if recipe not in anchors and recipe not in problems:
            problems[recipe] = f"{recipe} entry is missing from the anchor file"
    return AnchorState(anchors, set_dates, problems)


def arma_tier_processes(proc: Path = Path("/proc")) -> int:
    """Count running Arma server processes, the busiest thing this box carries.

    Reads `/proc`'s `comm` files rather than spawning `pgrep`, so the reporter
    adds no process of its own and a test can point this at a staged directory.
    Only the tier's own WSL-side servers are visible: a play session on the
    Windows host does not appear here, which the header states as a limit
    rather than pretending otherwise.
    """
    count = 0
    try:
        entries = list(proc.iterdir())
    except OSError:
        return 0
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if comm.startswith(ARMA_TIER_PREFIX):
            count += 1
    return count


def as_utc(moment: datetime) -> datetime:
    """Read a naive moment as UTC, because both sides of the window bound must compare.

    The recorder writes aware timestamps; a naive value arises only from a
    hand-written `set` or an arranged row, and assuming UTC beats crashing the
    comparison that assumption feeds.
    """
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def record_moment(row: Record) -> datetime | None:
    """Return the row's moment in UTC, or `None` when `at` will not parse.

    Used only to place a row against an anchor's `set` moment; a row that
    cannot be placed in time is excluded from a bounded window rather than
    guessed at.
    """
    try:
        return as_utc(datetime.fromisoformat(row.at))
    except ValueError:
        return None


def assess(
    records: tuple[Record, ...],
    anchor_state: AnchorState,
    *,
    arma_running: bool = False,
) -> tuple[Verdict, ...]:
    """Decide, per recipe, whether the gate counts as durably slower.

    One verdict per recipe in `RECIPES`, in that order, each carrying the
    reason it is silent or the one line it fires. The ladder, and why each rung
    is where it is:

    1. `anchor_unreadable` — the file or this recipe's entry will not read, and
       this rung *prints*, even while the Arma tier owns the box: it is a
       broken instrument, not a claim about the gate, so a busy box does not
       license its silence. Ahead of everything because a half-edited anchor
       reading as health is the failure #446 exists to prevent.
    2. `arma_tier_running` — the corpus or a play server owns the box; a slow
       gate under that is a busy box, not a regression. Ahead of the comparison
       rungs so an anchored watcher cannot cry regression during a play session.
    3. `anchor_unset` — no anchor for this recipe. A backstop the loader no
       longer produces — `load_anchors` treats a missing entry as a broken
       file — kept so a hand-built state cannot fall through to a comparison
       against nothing: unknown, never healthy.
    4. `insufficient_sample` — fewer than `MIN_SAMPLE` green runs **at or after
       the anchor's `set` moment**, and for a `MUTATION_LEG_RECIPES` recipe
       only those that gave the mutation tier a target (#466; the reasoning is
       in the module header, the predicate at `had_mutation_target`). Also the
       honest state right after a re-set: the pre-`set` rows are excluded, so a
       lowered anchor reads as unknown until five new greens exist rather than
       false-firing at the old rows — including the same morning's rows when
       `set` names a timestamp, and including every pre-#466 row for `fast`.
    5. `healthy` — the window median is at or under `THRESHOLD`× the anchor.
    6. `slower` — over it, with the one line, which carries the window's
       load-1m median so a busy box can be read off the line itself.
    """
    verdicts: list[Verdict] = []
    for recipe in RECIPES:
        problem = anchor_state.problems.get(recipe)
        if problem is not None:
            verdicts.append(
                Verdict(
                    recipe,
                    "anchor_unreadable",
                    f"gate-clock {recipe} anchor unreadable: {problem} — a broken "
                    "instrument must not read as a healthy gate; fix "
                    "tools/gate-clock-anchor.json in a diff",
                )
            )
            continue
        if arma_running:
            verdicts.append(Verdict(recipe, "arma_tier_running", None))
            continue
        anchor = anchor_state.anchors.get(recipe)
        if anchor is None:
            verdicts.append(Verdict(recipe, "anchor_unset", None))
            continue
        greens = [row for row in records if row.recipe == recipe and row.status == 0]
        set_on = anchor_state.set_dates.get(recipe)
        if set_on is not None:
            greens = [
                row for row in greens if (when := record_moment(row)) is not None and when >= set_on
            ]
        # #466: a run that gave the mutation tier no target skipped this
        # recipe's one diff-scoped leg and is systematically cheaper, so
        # admitting it drags the median down — the false-negative direction on
        # an instrument built to catch slow growth. Excluded rather than
        # weighted, because the anchor was derived from runs that paid that leg
        # and the like-for-like population is those runs alone; the rows written
        # before the count carry none and are dropped here as unclassified
        # rather than guessed at. Both choices, why the count is of targets
        # selected rather than mutants planted, and the reason a docs-only flag
        # was not the field, are in the module header.
        if recipe in MUTATION_LEG_RECIPES:
            greens = [row for row in greens if had_mutation_target(row)]
        if len(greens) < MIN_SAMPLE:
            verdicts.append(Verdict(recipe, "insufficient_sample", None))
            continue
        window = greens[-REPORT_WINDOW:]
        current = median([row.wall_seconds for row in window])
        load_text = ""
        loads = [row.load_1m for row in window if row.load_1m is not None]
        if loads:
            load_text = f", window load-1m median {median(loads):.2f}"
        if current <= anchor * THRESHOLD:
            verdicts.append(Verdict(recipe, "healthy", None))
            continue
        verdicts.append(
            Verdict(
                recipe,
                "slower",
                f"gate-clock {recipe} durably slower: median {current:.0f}s over the "
                f"last {len(window)} green runs{load_text}, {current / anchor:.2f}× the "
                f"{anchor:.0f}s anchor — no single commit does this; the anchor "
                f"moves only by hand, in a diff",
            )
        )
    return tuple(verdicts)


def history(gate_clock_dir: Path, anchor_state: AnchorState) -> list[str]:
    """One line per recipe, for the retro asking what it would be raising.

    Story 7 of #446: a proposal to move the anchor should quote what it is
    moving from. Silent-when-healthy is the report's contract; this verb is the
    explicit ask, and prints whether an anchor is set, its value and its set
    date — the date the report's window is bounded by.

    #466 adds the kinds to that line. Every recipe's line counts its green runs
    that gave the mutation tier no target and its green runs written before the
    count existed, so a reader can see how much of the history is being declined
    rather than infer it. For a `MUTATION_LEG_RECIPES` recipe the median and the
    span are taken over the rest — `assess`'s kind filter, so a retro quoting
    this median quotes a figure drawn from the same population the anchor is
    compared against. Only the kind filter is shared: `assess` also bounds its
    window by the anchor's `set` moment and this verb never has, which is why
    the line prints that date beside the median rather than applying it.
    """
    records = load_records(gate_clock_dir)
    lines: list[str] = []
    for recipe in RECIPES:
        rows = [row for row in records if row.recipe == recipe]
        all_green = [row for row in rows if row.status == 0]
        greens = (
            [row for row in all_green if had_mutation_target(row)]
            if recipe in MUTATION_LEG_RECIPES
            else all_green
        )
        anchor = anchor_state.anchors.get(recipe)
        set_on = anchor_state.set_dates.get(recipe)
        if anchor is None:
            anchor_text = "no anchor set"
        elif set_on is None:
            anchor_text = f"{anchor:.0f}s anchor, set date unrecorded"
        elif set_on.time() == time(0):
            anchor_text = f"{anchor:.0f}s anchor set {set_on.date().isoformat()}"
        else:
            anchor_text = f"{anchor:.0f}s anchor set {set_on.isoformat()}"
        cheap = sum(1 for row in all_green if row.mutation_targets == 0)
        unrecorded = sum(1 for row in all_green if row.mutation_targets is None)
        detail = f"{len(all_green)} green"
        if cheap:
            detail += f", {cheap} with no mutation target"
        if unrecorded:
            detail += f", {unrecorded} predating the target count"
        if not greens:
            reason = "no green runs recorded" if not all_green else "no comparable green runs"
            lines.append(
                f"{recipe}: {len(rows)} records ({detail}), {reason}, {anchor_text}; "
                "coverage unknowable: failed recording attempts are not durably counted"
            )
            continue
        walls = [row.wall_seconds for row in greens]
        window = walls[-REPORT_WINDOW:]
        lines.append(
            f"{recipe}: {len(rows)} records ({detail}), "
            f"median(last {len(window)} green) {median(window):.0f}s, "
            f"span {min(walls):.0f}s to {max(walls):.0f}s, {anchor_text}; "
            "coverage unknowable: failed recording attempts are not durably counted"
        )
    return lines


def proc_uptime(path: Path | None = None) -> float | None:
    """Seconds since boot from `/proc/uptime` — the kernel's monotonic clock.

    Both ends of a recorded wall read this rather than `CLOCK_REALTIME`, which
    steps under NTP: a step mid-run would record a duration the suite never
    cost. `path` resolves the module's `PROC_UPTIME` at call time rather than
    as a def-time default, so a test can stage it; `None` when it cannot be
    read, never a guess.
    """
    try:
        first = (PROC_UPTIME if path is None else path).read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        return None
    try:
        return float(first)
    except ValueError:
        return None


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Four verbs: record a finished run, report drift, read the history, check the anchor."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate-clock-dir",
        type=Path,
        default=Path(os.environ.get("CTI_GATE_CLOCK_DIR", str(DEFAULT_GATE_CLOCK_DIR))),
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    entry = verbs.add_parser("record", help="append one finished gate run")
    entry.add_argument("--recipe", choices=RECIPES, required=True)
    entry.add_argument(
        "--start-uptime",
        type=float,
        required=True,
        help="the recipe's own start, from /proc/uptime's first field",
    )
    entry.add_argument("--status", type=int, required=True)
    entry.add_argument("--load-1m", type=float, default=None, help="load average at start")
    entry.add_argument(
        "--foreign-gate",
        type=int,
        default=None,
        help="other gate processes counted at start",
    )

    verbs.add_parser("report", help="one line per durably slower recipe; silent when healthy")

    verbs.add_parser("history", help="per-recipe medians and spans, anchor stated")

    verbs.add_parser("check", help="refuse a malformed anchor file; the `just check` leg")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Record, report, read history or check the anchor.

    Exit 0 for every verb but `check` — the reads never gate. `check` is the
    one exception and the reason it exists: a malformed anchor is a red at
    `just check` time rather than a line nobody is obliged to read at
    watch-report time.
    """
    args = parse_args(argv)

    if args.verb == "record":
        now_up = proc_uptime()
        if now_up is None or args.start_uptime > now_up:
            print(  # noqa: T201 — the shell reads this
                "gate-clock: recording failed — /proc/uptime unreadable at one end",
                file=sys.stderr,
            )
            return 0
        row = Record(
            at=datetime.now(UTC).isoformat(),
            recipe=args.recipe,
            wall_seconds=max(now_up - args.start_uptime, 0.0),
            status=args.status,
            head=head_sha(),
            tests_collected=read_collected_file(),
            load_1m=args.load_1m,
            foreign_gate_processes=args.foreign_gate,
            mutation_targets=read_mutation_targets(),
            record_id=uuid4().hex,
        )
        note = record_or_queue(args.gate_clock_dir, row)
        if note is None:
            return 0
        health = "green" if row.status == 0 else f"status {row.status}"
        count = f" {row.tests_collected} tests" if row.tests_collected is not None else ""
        # The target count is on the line for the reason the test count is: a
        # zero — the kind `fast`'s comparison will decline — is then visible in
        # the run's own output rather than only in a row nobody opens (#466).
        targets = (
            f", {row.mutation_targets} mutation target(s)"
            if row.mutation_targets is not None
            else ""
        )
        print(  # noqa: T201 — the shell reads this
            f"gate-clock: recorded {row.recipe} {row.wall_seconds:.1f}s "
            f"{health}{count}{targets}{note}"
        )
        return 0

    anchor_state = load_anchors(ANCHOR_PATH)

    if args.verb == "history":
        for line in history(args.gate_clock_dir, anchor_state):
            print(line)  # noqa: T201 — the ask is the output
        return 0

    if args.verb == "check":
        for recipe, problem in sorted(anchor_state.problems.items()):
            print(f"gate-clock {recipe} anchor unreadable: {problem}")  # noqa: T201 — the red
        return 1 if anchor_state.problems else 0

    for verdict in assess(
        load_records(args.gate_clock_dir),
        anchor_state,
        arma_running=arma_tier_processes() > 0,
    ):
        if verdict.line is not None:
            print(verdict.line)  # noqa: T201 — the seat reads these lines
    return 0


if __name__ == "__main__":
    sys.exit(main())
