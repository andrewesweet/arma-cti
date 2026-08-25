"""`just watch-report`'s gate-duration half: the gate got durably slower, said once.

Between 2026-08-05 and 2026-08-19 this project's gate roughly doubled and nobody
noticed for two weeks (#446). Nothing recorded how long a gate run took, so the
only evidence was Claude Code's session transcripts, an accident nobody
committed to retaining. And no commit caused it: the suite's test count grew
2.43× while its measured work grew 1.23×, because `pytest-xdist`'s `--dist load`
charges a scheduling penalty that scales with test count — every commit made the
gate slightly worse and no bisect could stand out. A regression with no guilty
commit is exactly the kind only a standing measurement catches.

So every gate run appends one row to `~/.arma-cti/gate-clock/records.jsonl`
(outside every worktree, accumulating across branches and lanes), and this
module's `report` — folded into `just watch-report` — compares a median of
recent green runs against an **anchor** held in `tools/gate-clock-anchor.json`,
in the tree. Every recipe that gates a landing records (`RECIPES`, #483), and
each row carries the run's legs — name, outcome and wall seconds each — so a
red leg's identity and a doubled leg are on the record rather than lost in one
aggregate status. The recipes hand their legs to this module's `run` verb and it
runs them in order, records the row, and exits the legs' own status: the
per-leg scaffold has one home rather than one per recipe, and a recipe run by
hand records exactly as one the gate runs.

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
the tree with every recipe named, so a file that is missing, unparseable, or
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
flagged where it sits, which is how a misspelling presents. Since #483 widened
`RECIPES` past the recipes an anchor exists for, the one entry that names a
recipe without anchoring it is `anchor_seconds: null`: a deliberate, reviewed
unset — no anchor has been derived for that recipe's rows yet — read by the
loader and kept distinct from a dropped key, which is damage. Deliberately
unset and nulled away are different facts, and `ANCHORED_RECIPES` is what
tells them apart: the null is readable only for a recipe no anchor was ever
derived for, while the same null on an anchored recipe is the one edit that
would re-open the doubling unnoticed — an anchor removed reads as damage and
reddens `just check`, never as a configuration choice. `assess`'s
`anchor_unset` rung is what a readable unset produces, the honest unknown; the
recipes the file must name are `RECIPES`, the set the recorder writes rows
for, so the file and the loader cannot drift apart silently.

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

**The mutation-carrying recipes' comparisons exclude the zero rows; `unit` and
`check` record the count and compare on it not at all.** Excluded rather than
weighted, because the 93.6 s anchor was derived from four runs whose diff
carried `tests/unit/test_generate_seats.py` (`6a769cb`) and so paid the
mutation leg: the like-for-like population is the runs that paid it too, and a
second anchor derived from the cheap kind is a derivation nobody has done.
Direction settles the rest — the issue's reading has #450's three docs-only
landings at 81.49, 82.53 and 81.35 s, the floor of a recorded span reaching
231 s, and a median those drag down makes a real slowdown read as ordinary,
the false-negative direction on an instrument built to catch slow growth.
`mutation` joins `fast` in `MUTATION_LEG_RECIPES` for the same reason one step
purer: its whole wall is the diff-scoped tier, so a zero-target row is a
floor-priced run with nothing else in it. `unit` and `check` are left
unfiltered because their own legs are diff-independent: a zero-target row of
either is the same measurement as any other, and filtering it would only
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
each: a `just fast` now starts four — its own runner and the nested `check`,
`unit` and `mutation` runners — against a ~190 s tier, under 1%) and one small
file write at collection time; nothing is added to any assertion or test. The
#466 count adds one import of `tools/mutation_smoke.py` and two passes of its
`changed` git reads (`merge-base`, `diff --name-only`, `status --porcelain`) —
stated as a count rather than a duration, because nobody has timed it. `just
fast` invoking `just check`, `just unit` and `just mutation` records four rows —
each nested recipe's own wall plus the whole recipe's — and all four are real
measurements of real invocations.

**Three leg outcomes, and absence as the fourth.** `passed` ran and exited
zero; `failed` ran and did not; `not_run` was skipped and cost nothing — since
#566, only a leg whose declared prerequisite did not pass, the reason carried
beside it; before #566, any leg behind the first red one; and a row whose
`legs` is `None` predates #483 and claims no breakdown at all. None of these
renders as another — a `not_run` leg with no wall is not a fast pass, and an
absent breakdown is not an empty one — which is the standing rule
`docs/observatory/hazards.md` states over the observatory's other three-state
fields, applied here from the first row rather than after a conflation. A red
run's shell line names every leg's outcome for the same reason: a red recipe
must not be mistaken for a fast one, and since #566 the line answers every leg
rather than the legs up to the first red — one unrelated red no longer costs
the reader every leg behind it.

The state directory is `CTI_GATE_CLOCK_DIR`, the seam `CTI_WATCH_DIR`,
`CTI_BREAKER_DIR` and `CTI_RC_HEALTH_DIR` exist for (#249): without it a unit
test of this reporter reads the live box, and whatever the box happens to be
carrying reddens an unrelated run.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path — the device gate.py and
# dispatch.py use; it is what makes mutation_smoke importable below.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes these importable. `review_loop` for the review
# root's one home — the stage journal lives under it — and neither it nor the
# registry imports this module, so the edge stays one-way.
import attribute_registry
import review_loop

DEFAULT_GATE_CLOCK_DIR: Final = Path.home() / ".arma-cti" / "gate-clock"
RECORDS_NAME: Final = "records.jsonl"
ANCHOR_PATH: Final = Path(__file__).with_name("gate-clock-anchor.json")
PROC_UPTIME: Final = Path("/proc/uptime")
PROC_LOADAVG: Final = Path("/proc/loadavg")

# The ref the mutation tier measures a landing against, and the tree it is
# measured in — the same pair `just mutation` itself uses, so the count below
# can never disagree with the tier it describes.
BASE_REF: Final = "origin/main"
REPO_ROOT: Final = Path(__file__).resolve().parents[1]

# Every recipe that gates a landing (#483): `just fast` runs all four as legs,
# and each is run alone while iterating. The two-recipe set this replaces
# (#446) excluded `check` and `mutation` as noise against a 200 s tier — an
# argument about the drift assessment, which a recorded row need not receive:
# `assess` stays silent wherever no anchor is set, so recording a recipe costs
# the file's append and nothing else. One home: adding a recipe is an edit here
# plus a call site in the justfile, never a silent omission, and the anchor
# file must name the newcomer (`anchor_seconds: null` until an anchor is
# derived from its rows).
RECIPES: Final = ("unit", "fast", "check", "mutation")

# The recipes an anchor has been derived for. `anchor_seconds: null` reads as
# the deliberate unset only for a recipe this tuple excludes — recorded, never
# anchored — because the same null on a recipe this tuple names is a nulled
# anchor: the disarm path #446 exists to catch, wearing the unset state's
# spelling, and a gate that can be silently disarmed that way is the two-week
# doubling again. The tuple and the shipped file cannot drift apart: deriving
# an anchor writes the value in the file and adds the recipe here in the one
# hand-edit, and the test module asserts the two agree on the tree's own file.
ANCHORED_RECIPES: Final = ("unit", "fast")

# The recipes whose cost the diff moves through the mutation tier, and so the
# only ones whose comparison reads `mutation_targets` (#466): `fast`, which
# carries `just mutation` as one leg of three, and `mutation`, whose whole wall
# is that tier and so is diff-scoped end to end. Every other leg prices the
# whole tree whatever the diff holds, so a `unit` or `check` row's count is
# provenance and never a filter. One home for that rule: `assess` and `history`
# both ask here, and the anchor file's `mutation` note states its anchor would
# be read the same way.
MUTATION_LEG_RECIPES: Final = ("fast", "mutation")

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

# The three facts a leg's outcome carries (#483). They are different facts and
# render differently, never as each other: `passed` ran and exited zero,
# `failed` ran and did not, `not_run` was skipped and cost nothing — since
# #566 the only skip is a declared prerequisite that did not pass, and the
# reason rides beside the outcome. The set this vocabulary comes from —
# absence, a value and a third state conflated five separate times in one
# week — is the standing rule
# in `docs/observatory/hazards.md`.
LEG_OUTCOMES: Final = ("passed", "failed", "not_run")

# A failed leg's evidence, bounded (#576). A red unit leg used to leave only a
# status integer: pytest's own `lastfailed` cache is erased by the next green
# run, which is exactly when someone looks. So the runner mints a per-leg file,
# names it in `CTI_GATE_CLOCK_FAILED_FILE`, and `tests/unit/conftest.py` writes
# the failed node ids there at summary time; a leg that failed copies them onto
# its row at the moment of failure, where no later run erases them. A green leg
# writes nothing, so healthy rows do not grow. The cap bounds a hundreds-red
# run to this many ids, and a truncation states itself as the list's last
# entry — an under-reporting list that reads as complete is the observatory's
# standing hazard, never repeated silently.
FAILED_TESTS_RECORDED: Final = 20
FAILED_FILE_VARIABLE: Final = "CTI_GATE_CLOCK_FAILED_FILE"

# What the row's `foreign_gate_processes` counts: any process whose command
# line names the Python or Rust test runners, the two things that make a gate
# slow by being a gate. The shell scaffold this module replaced counted them
# with `pgrep -fc 'pytest|cargo test'` at start; this is the same match, read
# from `/proc` so the recorder spawns nothing of its own.
FOREIGN_GATE_PATTERN: Final = re.compile(r"pytest|cargo test")


class Leg(NamedTuple):
    """One leg inside a recipe's run, as the row carries it.

    `wall_seconds` is `None` for a `not_run` leg — it was never measured — and
    a number for every leg that ran, passed or failed alike. `reason` names the
    prerequisite that did not pass, for a leg skipped by one (#566); `None` for
    every leg that ran and for a row that predates the field. `failed_tests`
    carries the node ids a failed pytest leg named, bounded by
    `FAILED_TESTS_RECORDED` (#576), and keeps three answers apart (#576
    round 2): ids for a run that named some, an empty tuple for one that
    completed and named none, and `None` where there is no claim at all — a
    green or `not_run` leg, a failed leg whose id file could not be read, or a
    row that predates the field. The field belongs to failed legs alone; the
    codec drops it on write and ignores it on read anywhere else.
    """

    name: str
    outcome: str
    wall_seconds: float | None
    reason: str | None = None
    failed_tests: tuple[str, ...] | None = None


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
    legs: tuple[Leg, ...] | None = None


class Verdict(NamedTuple):
    """What `report` says about one recipe — a line, or the reason there is none."""

    recipe: str
    reason: str
    line: str | None


class AnchorState(NamedTuple):
    """What `load_anchors` read.

    The anchors, their `set` moments, the deliberately unset recipes, and the
    unreadable entries.
    """

    anchors: dict[str, float]
    set_dates: dict[str, datetime]
    problems: dict[str, str]
    unset: frozenset[str] = frozenset()


def median(values: list[float]) -> float:
    """Return the middle value, averaging the middle two on an even count."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def leg_document(leg: Leg) -> dict[str, object]:
    """Render one leg as its object inside the row.

    `reason` is written only when there is one, so a row's passed and failed
    legs keep the shape they had before #566 and the archive stays readable
    beside the new rows. `failed_tests` is written only on a failed leg —
    the codec's half of the failed-only invariant (#576 round 2), so a future
    writer cannot attach ids to a leg that passed — and an empty list is
    written rather than elided, because "named none" is an answer and not an
    absence. Green rows still do not grow: a green leg never carries the field.
    """
    document: dict[str, object] = {
        "name": leg.name,
        "outcome": leg.outcome,
        "wall_seconds": leg.wall_seconds,
    }
    if leg.reason is not None:
        document["reason"] = leg.reason
    if leg.failed_tests is not None and leg.outcome == "failed":
        document["failed_tests"] = list(leg.failed_tests)
    return document


def parse_leg(entry: object) -> Leg | None:
    """Read one leg back, answering `None` for anything malformed."""
    if not isinstance(entry, dict):
        return None
    try:
        name = str(entry["name"])
        outcome = str(entry["outcome"])
        if outcome not in LEG_OUTCOMES:
            return None
        wall = entry["wall_seconds"]
        reason = entry.get("reason")
        # The field belongs to failed legs alone (#576 round 2): on any other
        # outcome the key is a malformed claim and reads as none, the same as
        # anything but a list — a half-written value must not redden the
        # archive, and ids on a passing leg must not survive the read either.
        raw_failed = entry.get("failed_tests") if outcome == "failed" else None
        failed = tuple(str(item) for item in raw_failed) if isinstance(raw_failed, list) else None
        return Leg(
            name,
            outcome,
            None if wall is None else float(wall),
            None if reason is None else str(reason),
            failed,
        )
    except (KeyError, TypeError, ValueError):
        return None


def record_document(row: Record) -> dict[str, object]:
    """Render one run as the JSONL row the next report reads."""
    return {
        "at": row.at,
        "recipe": row.recipe,
        "wall_seconds": row.wall_seconds,
        "status": row.status,
        "head": row.head,
        "tests_collected": row.tests_collected,
        "load_1m": row.load_1m,
        "foreign_gate_processes": row.foreign_gate_processes,
        "mutation_targets": row.mutation_targets,
        "legs": None if row.legs is None else [leg_document(leg) for leg in row.legs],
    }


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

    A row without `legs` predates #483 and reads as `None` the same way: no
    breakdown claimed, never an empty one guessed at. A row whose `legs` list
    carries an element that will not read also reads as `None`, declining the
    whole breakdown rather than a part of it — a partial list would present a
    recipe's later legs as absent when they ran, which is the exact reading
    `not_run` exists to prevent.
    """
    if not isinstance(document, dict):
        return None
    try:
        raw_legs = document.get("legs")
        legs = None
        if isinstance(raw_legs, list):
            read_legs: list[Leg] = []
            for entry in raw_legs:
                one = parse_leg(entry)
                if one is None:
                    break
                read_legs.append(one)
            else:
                legs = tuple(read_legs)
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
            legs=legs,
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
        lines = path.read_bytes().splitlines()
    except OSError:
        return ()
    rows: list[Record] = []
    for encoded_line in lines:
        try:
            line = encoded_line.decode("utf-8")
        except UnicodeDecodeError:
            continue
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


def append_record(gate_clock_dir: Path, row: Record) -> Path:
    """Append one row, creating the state directory on first use."""
    path = records_path(gate_clock_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record_document(row)) + "\n")
    return path


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


def _read_anchor_entry(name: str, entry: object) -> tuple[float, datetime] | str | None:
    """Return one entry's read: `(anchor, set moment)`, unset, or the problem.

    `None` answers deliberately unset; a string answers the problem with the
    entry as a message.

    Split out of `load_anchors` so the file-level failures (missing,
    unparseable, not an object) and the per-entry ladder read separately.

    `anchor_seconds: null` is the deliberate unset state (#483) — a recipe the
    recorder writes but no anchor has been derived for yet — and which recipes
    those are is `ANCHORED_RECIPES`'s one statement, because the same null on a
    recipe an anchor has been derived for is that anchor nulled away: the
    disarm #446 exists to catch, and damage, not a configuration choice. A
    dropped key or a misspelled one is damage either way, and `assess`'s
    `anchor_unset` rung is what a readable unset produces.
    """
    if not isinstance(entry, dict):
        return f"{name} entry is not an object"
    if entry.get("anchor_seconds") is None:
        if "anchor_seconds" not in entry:
            return f"{name}.anchor_seconds is not a positive number"
        return (
            None
            if name not in ANCHORED_RECIPES
            else f"{name}.anchor_seconds is null but an anchor has been derived for "
            f"{name} — a nulled anchor is damage, not the unset state; restore the "
            "value or re-derive it"
        )
    seconds = entry["anchor_seconds"]
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
    The one entry that names a recipe without anchoring it is
    `anchor_seconds: null` (#483): an explicit, reviewed decision that no anchor
    has been derived for that recipe, kept distinct from a missing key by being
    a value the loader reads — and readable only where `ANCHORED_RECIPES` says
    no anchor was ever derived, because on a recipe it names the same null is a
    disarmed instrument and a problem, the same damage a dropped key is. `set`
    is required wherever an anchor is set,
    because the report bounds its window by it: an anchor without a set moment
    could not be lowered without false-firing against the rows that predate the
    change. A date bounds from that day's start; a full timestamp bounds from
    the moment it names, so a re-set on a day already run excludes that
    morning's rows.
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
    unset: set[str] = set()
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
        if read is None:
            unset.add(name)
        elif isinstance(read, str):
            problems[name] = read
        else:
            anchors[name], set_dates[name] = read
    named = anchors.keys() | problems.keys() | unset
    for recipe in set(RECIPES) - named:
        problems[recipe] = f"{recipe} entry is missing from the anchor file"
    return AnchorState(anchors, set_dates, problems, frozenset(unset))


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


def read_loadavg(path: Path | None = None) -> float | None:
    """Read the 1-minute load average, or answer `None` — never a guess.

    Same shape as `proc_uptime`: a kernel file read at the run's start for the
    row's `load_1m`, with `path` resolving the module's `PROC_LOADAVG` at call
    time so a test can stage it. The shell scaffold this replaced read it with
    `cut -d' ' -f1 /proc/loadavg` and passed it as `--load-1m`.
    """
    try:
        first = (PROC_LOADAVG if path is None else path).read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError):
        return None
    try:
        return float(first)
    except ValueError:
        return None


def foreign_gate_processes(proc: Path = Path("/proc")) -> int | None:
    """Count other gate processes at start, or `None` when `/proc` cannot be read.

    The `FOREIGN_GATE_PATTERN` match the shell scaffold took from
    `pgrep -fc 'pytest|cargo test'`, read from `/proc/*/cmdline` instead so the
    recorder spawns nothing of its own and a test can stage a directory — the
    same shape as `arma_tier_processes`. This recorder's own command line names
    neither runner, so it never counts itself.
    """
    try:
        entries = list(proc.iterdir())
    except OSError:
        return None
    count = 0
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (
                (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
            )
        except OSError:
            continue
        if FOREIGN_GATE_PATTERN.search(cmdline):
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
            lines.append(f"{recipe}: {len(rows)} records ({detail}), {reason}, {anchor_text}")
            continue
        walls = [row.wall_seconds for row in greens]
        window = walls[-REPORT_WINDOW:]
        lines.append(
            f"{recipe}: {len(rows)} records ({detail}), "
            f"median(last {len(window)} green) {median(window):.0f}s, "
            f"span {min(walls):.0f}s to {max(walls):.0f}s, {anchor_text}"
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


def bounded_failed_tests(ids: list[str]) -> tuple[str, ...]:
    """Cap a failed leg's identities, stating the cut rather than making it silently.

    Twenty ids bounds a hundreds-red run to a fixed row cost, and the omitted
    count rides as the list's own last entry so every reader — the observatory,
    a hand read of the JSONL, `just gate-clock-history`'s future — sees the
    list is a sample without knowing this module's cap (#576).
    """
    if len(ids) > FAILED_TESTS_RECORDED:
        omitted = len(ids) - FAILED_TESTS_RECORDED
        return (*ids[:FAILED_TESTS_RECORDED], f"... and {omitted} more not recorded")
    return tuple(ids)


def read_failed_file(path: Path) -> list[str] | None:
    """Read the node ids a leg's run named, keeping "named none" apart from "could not tell".

    The file is minted empty by the runner and written only by a pytest run
    that failed (`tests/unit/conftest.py`), so an empty read is an affirmative
    answer: the run completed with the channel intact and named nothing. A
    missing or unreadable file is `None` — no claim, because the channel
    itself broke — and never an empty list, which would let a failure that
    recorded nothing read as one that recorded a definite answer (#576
    round 2). Either way the read stays quiet: evidence for a later
    investigation must never redden the gate it rides on.
    """
    try:
        return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return None


def runner_legs(names: list[str], forwarded: list[str]) -> list[tuple[str, list[str]]]:
    """Turn the CLI's `--leg` names and forwarded tail into runnable argv pairs.

    Every leg is its just recipe — the recording call site stays in the recipe,
    so a recipe run by hand records exactly as one the gate runs does — and the
    arguments after the leg list belong to the last leg alone, which is how
    `just mutation --paths tests/unit/x.py` forwards through to its one body
    recipe without the runner learning a second command shape.
    """
    legs = [(name, ["just", name]) for name in names]
    if legs:
        last_name, last_argv = legs[-1]
        legs[-1] = (last_name, [*last_argv, *forwarded])
    return legs


def parse_depends(entries: list[str], names: list[str]) -> dict[str, str]:
    """Read `--depends` entries into a map, refusing the typo shapes.

    A declaration nobody could satisfy — a side that is not a leg of this run,
    or a prerequisite sitting behind its dependent in the order — would either
    never fire or fire on a leg not yet reached, so both are loud usage errors
    rather than silent behaviour (#566).
    """
    depends: dict[str, str] = {}
    for entry in entries:
        leg, separator, prerequisite = entry.partition("=")
        if not separator or not leg or not prerequisite:
            problem = "expects LEG=PREREQ"
        elif leg in depends:
            problem = f"names {leg} twice"
        elif leg not in names or prerequisite not in names:
            problem = "names a leg this run does not have"
        elif names.index(prerequisite) >= names.index(leg):
            problem = "prerequisite sits behind its leg"
        else:
            depends[leg] = prerequisite
            continue
        message = f"gate-clock: --depends {problem}: {entry!r}"
        # A usage refusal's whole output is this message; a bare exit code
        # would leave the caller guessing which of the four shapes fired.
        raise SystemExit(message)
    return depends


def run_recipe(
    recipe: str,
    legs: list[tuple[str, list[str]]],
    gate_clock_dir: Path,
    depends: dict[str, str] | None = None,
) -> int:
    """Run one recipe's legs in order, record the row, and answer the legs' status.

    The recipe bodies' own scaffold (#483): this is what a `just` recipe hands
    its legs to, so the per-leg outcomes and the whole-recipe wall are taken by
    the same code for every recipe. Every leg runs whatever the legs before it
    did (#566): one red leg no longer hides the legs behind it, and the recipe
    still exits red — the first red leg's own status. The one skip the runner
    knows is declared, never positional: `depends` names, per leg, a
    prerequisite leg that must pass first, and a leg whose prerequisite did not
    pass is recorded `not_run` with the reason beside it — the fact a leg did
    not run stays distinct from one that ran and passed, and a row that could
    not tell them apart would let an unfinished recipe read as a fast green one
    (#83's shape). The cost is stated rather than discovered: a red run now
    pays the legs a green one always did, where it used to stop at the first
    red. A failed leg also carries the node ids its own run named through
    `CTI_GATE_CLOCK_FAILED_FILE` (#576), bounded and never silently truncated,
    because the row is the one place the identity of a failure survives the
    next green run — an empty list where the run completed and named none, and
    no claim at all where the id file could not be read, two answers that must
    not collapse (#576 round 2).

    Recording stays advisory: an unreadable clock or an unwritable records
    directory prints to stderr and never changes the exit status, because a
    gate that cannot record is still a gate. The wall is `/proc/uptime` at both
    ends, per leg and for the recipe, exactly as `record` takes it.

    A `fast` run inside a dispatched implementer's session is also the
    pipeline's own-gate stage reached (#490), recorded before the legs run so a
    crash mid-gate still shows the gate was reached. The environment names the
    item — the dispatcher exports `CTI_DISPATCH_ISSUE`, `CTI_DISPATCH_ID` and
    `CTI_DISPATCH_SEAT` to every child — so a run with no dispatch behind it (a
    human's, a test's, the landing's re-gate in the same session) records no
    arrival, the re-gate records none because the recorder deduplicates one
    dispatch's arrival at a stage, and a dispatched seat whose work is not a
    pipeline pass (retro, recon, planner, fable, orchestrator) records none
    either: the own gate is the implementer's act — `STAGE_OF_SEAT` maps the
    seat to `implementation` or it is not this stage's arrival at all, the same
    filter the brief seam applies (#490 round 2, finding 2). Fail-open in the
    recorder; a gate that cannot take its own record is still a gate.
    """
    import subprocess  # noqa: PLC0415 — kept beside its only caller, like head_sha's

    if recipe == "fast":
        issue = os.environ.get("CTI_DISPATCH_ISSUE", "")
        seat = os.environ.get("CTI_DISPATCH_SEAT", "")
        if issue.isdigit() and attribute_registry.STAGE_OF_SEAT.get(seat) == "implementation":
            attribute_registry.record_stage_arrival(
                "own_gate",
                int(issue),
                review_loop.review_root(),
                datetime.now(UTC).timestamp(),
                dispatch_id=os.environ.get("CTI_DISPATCH_ID", ""),
            )
    start_up = proc_uptime()
    start_load = read_loadavg()
    start_foreign = foreign_gate_processes()
    status = 0
    leg_rows: list[Leg] = []
    outcomes: dict[str, str] = {}
    for name, argv in legs:
        prerequisite = (depends or {}).get(name)
        # The runner's one skip: declared, not positional. A prerequisite that
        # has not passed — failed, itself skipped, or not yet reached — leaves
        # the leg `not_run` with the reason beside it, and never a wall.
        if prerequisite is not None and outcomes.get(prerequisite) != "passed":
            blocker = outcomes.get(prerequisite, "not reached")
            leg_rows.append(Leg(name, "not_run", None, f"{prerequisite} {blocker}"))
            outcomes[name] = "not_run"
            continue
        # Minted fresh per leg, so an id can only come from this leg's own run
        # — never from an earlier red's leavings, which is `lastfailed`'s flaw
        # (#576). The variable reaches every child; only a failing pytest run
        # writes the file, and `just mutation` strips it from its judges, whose
        # kills are failing tests by design and would misattribute here.
        handle, minted = tempfile.mkstemp(prefix="gate-clock-failed-")
        os.close(handle)
        failed_file = Path(minted)
        leg_start = proc_uptime()
        done = subprocess.run(  # noqa: S603 — argv is the recipe's own leg list, never user text
            argv,
            check=False,
            env={**os.environ, FAILED_FILE_VARIABLE: minted},
        )
        leg_end = proc_uptime()
        wall = None if leg_start is None or leg_end is None else max(leg_end - leg_start, 0.0)
        outcome = "passed" if done.returncode == 0 else "failed"
        named_failures = read_failed_file(failed_file) if outcome == "failed" else None
        with contextlib.suppress(OSError):
            failed_file.unlink()
        leg_rows.append(
            Leg(
                name,
                outcome,
                wall,
                failed_tests=None
                if named_failures is None
                else bounded_failed_tests(named_failures),
            )
        )
        outcomes[name] = outcome
        if done.returncode != 0 and status == 0:
            status = done.returncode
    now_up = proc_uptime()
    if start_up is None or now_up is None or start_up > now_up:
        print(  # noqa: T201 — the shell reads this
            "gate-clock: recording failed — /proc/uptime unreadable at one end",
            file=sys.stderr,
        )
        return status
    row = Record(
        at=datetime.now(UTC).isoformat(),
        recipe=recipe,
        wall_seconds=max(now_up - start_up, 0.0),
        status=status,
        head=head_sha(),
        tests_collected=read_collected_file(),
        load_1m=start_load,
        foreign_gate_processes=start_foreign,
        mutation_targets=read_mutation_targets(),
        legs=tuple(leg_rows),
    )
    try:
        append_record(gate_clock_dir, row)
    except OSError as error:
        print(  # noqa: T201 — the shell reads this
            f"gate-clock: recording failed — {error.strerror or error}", file=sys.stderr
        )
        return status
    health = "green" if row.status == 0 else f"status {row.status}"
    count = f" {row.tests_collected} tests" if row.tests_collected is not None else ""
    targets = (
        f", {row.mutation_targets} mutation target(s)" if row.mutation_targets is not None else ""
    )
    # A red run's line names its legs — outcome, and the reason with it for a
    # skipped one — so the whole answer is visible in the run's own output
    # rather than only in a row nobody opens: a red recipe must not be mistaken
    # for a fast one, and since #566 a red names what the legs behind it found
    # rather than stopping at the first red (#483, story 16).
    leg_text = ""
    if row.status != 0 and row.legs:
        leg_text = (
            " (legs: "
            + ", ".join(
                f"{leg.name}={leg.outcome}" + (f" ({leg.reason})" if leg.reason else "")
                for leg in row.legs
            )
            + ")"
        )
    print(  # noqa: T201 — the shell reads this
        f"gate-clock: recorded {row.recipe} {row.wall_seconds:.1f}s "
        f"{health}{count}{targets}{leg_text}"
    )
    return status


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Five verbs: run, record, report, history, check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate-clock-dir",
        type=Path,
        default=Path(os.environ.get("CTI_GATE_CLOCK_DIR", str(DEFAULT_GATE_CLOCK_DIR))),
    )
    verbs = parser.add_subparsers(dest="verb", required=True)

    entry = verbs.add_parser(
        "run", help="run one recipe's legs, record the row, exit the legs' own status"
    )
    entry.add_argument("--recipe", choices=RECIPES, required=True)
    entry.add_argument(
        "--leg",
        action="append",
        required=True,
        metavar="RECIPE",
        help="one leg, named by the just recipe that runs it, in order",
    )
    entry.add_argument(
        "forwarded",
        nargs="*",
        metavar="ARG",
        help="arguments for the last leg's invocation only",
    )
    entry.add_argument(
        "--depends",
        action="append",
        default=[],
        metavar="LEG=PREREQ",
        help="declare one leg's prerequisite: the leg runs only if PREREQ passed, "
        "else is recorded not_run naming it (#566)",
    )

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
    """Run a recipe, record, report, read history or check the anchor.

    `run` answers the legs' own status, not 0: it is the gate. Every other verb
    exits 0 — the reads never gate — except `check`, the reason it exists: a
    malformed anchor is a red at `just check` time rather than a line nobody is
    obliged to read at watch-report time.
    """
    args = parse_args(argv)

    if args.verb == "run":
        return run_recipe(
            args.recipe,
            runner_legs(args.leg, args.forwarded),
            args.gate_clock_dir,
            parse_depends(args.depends, args.leg),
        )

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
        )
        append_record(args.gate_clock_dir, row)
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
            f"gate-clock: recorded {row.recipe} {row.wall_seconds:.1f}s {health}{count}{targets}"
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
