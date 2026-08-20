"""`just watch-report`'s gate-duration half: the gate got durably slower, said once.

Between 2026-08-05 and 2026-08-19 this project's gate roughly doubled and nobody
noticed for two weeks (#446). Nothing recorded how long a gate run took, so the
only evidence was Claude Code's session transcripts, an accident nobody
committed to retaining. And no commit caused it: the suite's test count grew
2.43× while its measured work grew 1.23×, because `pytest-xdist`'s `--dist load`
charges a scheduling penalty that scales with test count — every commit made the
gate slightly worse and no bisect could stand out. A regression with no guilty
commit is exactly the kind only a standing measurement catches.

So every `just unit` and `just fast` run appends one row to
`~/.arma-cti/gate-clock/records.jsonl` (outside every worktree, accumulating
across branches and lanes), and this module's `report` — folded into
`just watch-report` — compares a median of recent green runs against an
**anchor** held in `tools/gate-clock-anchor.json`, in the tree.

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

**Only green runs are compared.** A red run is faster — the #446 investigation
has a 306-failure run finishing in 221 s where the green run took 271 s — so a
red admitted to the median flatters it. Red rows are still recorded, with their
status, because the history is the point of recording; they are excluded from
every comparison.

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
nothing is added to any assertion or test. `just fast` invoking `just unit`
records two rows — the unit tier's own wall and the whole recipe's — and both
are real measurements of real invocations.

The state directory is `CTI_GATE_CLOCK_DIR`, the seam `CTI_WATCH_DIR`,
`CTI_BREAKER_DIR` and `CTI_RC_HEALTH_DIR` exist for (#249): without it a unit
test of this reporter reads the live box, and whatever the box happens to be
carrying reddens an unrelated run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NamedTuple

DEFAULT_GATE_CLOCK_DIR: Final = Path.home() / ".arma-cti" / "gate-clock"
RECORDS_NAME: Final = "records.jsonl"
ANCHOR_PATH: Final = Path(__file__).with_name("gate-clock-anchor.json")

# The two recipes that run the gate (issue #446): a bare `just unit` is most of
# the recorded population (22.27 h of the 57.51 h the investigation measured),
# while the whole `just fast` is the figure the subagent-wait threshold applies
# to. `just check` (~10 s) and `just mutation` (~0 s) are noise against a 200 s
# tier, and a record nobody will read is not worth the line.
RECIPES: Final = ("unit", "fast")

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


class Verdict(NamedTuple):
    """What `report` says about one recipe — a line, or the reason there is none."""

    recipe: str
    reason: str
    line: str | None


def median(values: list[float]) -> float:
    """Return the middle value, averaging the middle two on an even count."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


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
    }


def parse_record(document: object) -> Record | None:
    """Read one JSONL row back, answering `None` for anything malformed.

    Fail-quiet rather than fail-closed, and only on the report path: this read
    feeds the top of an orchestrator turn, so one truncated line (a box that
    died mid-append) must not take out the breaker and queue lines printed
    beside it. The malformed line stays on disk for a later look.
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


def load_anchors(path: Path) -> tuple[dict[str, float], str | None]:
    """Read the anchor file, or say why it could not be read.

    Returns `(anchors, problem)`. An absent file is the shipped unset state —
    every recipe silent, reason `anchor_unset` — while a file that exists but
    will not parse is `anchor_unreadable`: an anchor somebody half-edited must
    not read as *no* anchor, which would be silence dressed as health. Recipes
    the file simply does not name are unset, not errors; the file grows one row
    at a time as anchors are derived.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}, None
    try:
        document = json.loads(text)
    except ValueError:
        return {}, f"anchor file {path} is not valid JSON"
    if not isinstance(document, dict):
        return {}, f"anchor file {path} is not an object"
    anchors: dict[str, float] = {}
    for recipe, entry in document.items():
        if recipe.startswith("_") or not isinstance(entry, dict):
            continue
        seconds = entry.get("anchor_seconds")
        if isinstance(seconds, (int, float)) and seconds > 0:
            anchors[str(recipe)] = float(seconds)
    return anchors, None


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


def assess(
    records: tuple[Record, ...],
    anchors: dict[str, float],
    anchor_problem: str | None = None,
    *,
    arma_running: bool = False,
) -> tuple[Verdict, ...]:
    """Decide, per recipe, whether the gate counts as durably slower.

    One verdict per recipe in `RECIPES`, in that order, each carrying the
    reason it is silent or the one line it fires. The ladder, and why each rung
    is where it is:

    1. `arma_tier_running` — the corpus or a play server owns the box; a slow
       gate under that is a busy box, not a regression. Ahead of everything so
       an anchored watcher cannot cry regression during a play session.
    2. `anchor_unreadable` — the file exists and will not parse. Said before
       `anchor_unset` because it is the state a half-edit leaves behind.
    3. `anchor_unset` — no anchor for this recipe. The shipped state for a
       fresh clone: unknown, never healthy.
    4. `insufficient_sample` — fewer than `MIN_SAMPLE` green runs. A median of
       two runs says what the scheduler did, not what the suite costs.
    5. `healthy` — the window median is at or under `THRESHOLD`× the anchor.
    6. `slower` — over it, with the one line.
    """
    if arma_running:
        return tuple(Verdict(recipe, "arma_tier_running", None) for recipe in RECIPES)
    if anchor_problem is not None:
        return tuple(Verdict(recipe, "anchor_unreadable", None) for recipe in RECIPES)
    verdicts: list[Verdict] = []
    for recipe in RECIPES:
        anchor = anchors.get(recipe)
        if anchor is None:
            verdicts.append(Verdict(recipe, "anchor_unset", None))
            continue
        greens = [row.wall_seconds for row in records if row.recipe == recipe and row.status == 0]
        if len(greens) < MIN_SAMPLE:
            verdicts.append(Verdict(recipe, "insufficient_sample", None))
            continue
        window = greens[-REPORT_WINDOW:]
        current = median(window)
        if current <= anchor * THRESHOLD:
            verdicts.append(Verdict(recipe, "healthy", None))
            continue
        verdicts.append(
            Verdict(
                recipe,
                "slower",
                f"gate-clock {recipe} durably slower: median {current:.0f}s over the "
                f"last {len(window)} green runs, {current / anchor:.2f}× the "
                f"{anchor:.0f}s anchor — no single commit does this; the anchor "
                f"moves only by hand, in a diff",
            )
        )
    return tuple(verdicts)


def history(gate_clock_dir: Path, anchors: dict[str, float]) -> list[str]:
    """One line per recipe, for the retro asking what it would be raising.

    Story 7 of #446: a proposal to move the anchor should quote what it is
    moving from. Silent-when-healthy is the report's contract; this verb is the
    explicit ask, and prints whether an anchor is set.
    """
    records = load_records(gate_clock_dir)
    lines: list[str] = []
    for recipe in RECIPES:
        rows = [row for row in records if row.recipe == recipe]
        walls = [row.wall_seconds for row in rows if row.status == 0]
        anchor = anchors.get(recipe)
        anchor_text = f"{anchor:.0f}s anchor" if anchor is not None else "no anchor set"
        if not walls:
            lines.append(f"{recipe}: no green runs recorded, {anchor_text}")
            continue
        window = walls[-REPORT_WINDOW:]
        lines.append(
            f"{recipe}: {len(rows)} records ({len(walls)} green), "
            f"median(last {len(window)} green) {median(window):.0f}s, "
            f"span {min(walls):.0f}s to {max(walls):.0f}s, {anchor_text}"
        )
    return lines


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Three verbs: record a finished run, report drift, read the history."""
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
        "--start-epoch-ns",
        type=int,
        required=True,
        help="the recipe's own start, from bash's `date +%s%N`",
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Record, report or read history. Exit 0 throughout — this reads, never gates."""
    args = parse_args(argv)

    if args.verb == "record":
        start = args.start_epoch_ns / 1_000_000_000
        row = Record(
            at=datetime.fromtimestamp(start, tz=UTC).isoformat(),
            recipe=args.recipe,
            wall_seconds=max(time.time_ns() / 1_000_000_000 - start, 0.0),
            status=args.status,
            head=head_sha(),
            tests_collected=read_collected_file(),
            load_1m=args.load_1m,
            foreign_gate_processes=args.foreign_gate,
        )
        append_record(args.gate_clock_dir, row)
        health = "green" if row.status == 0 else f"status {row.status}"
        print(  # noqa: T201 — the shell reads this
            f"gate-clock: recorded {row.recipe} {row.wall_seconds:.1f}s {health}"
        )
        return 0

    anchors, problem = load_anchors(ANCHOR_PATH)

    if args.verb == "history":
        for line in history(args.gate_clock_dir, anchors):
            print(line)  # noqa: T201 — the ask is the output
        return 0

    for verdict in assess(
        load_records(args.gate_clock_dir),
        anchors,
        problem,
        arma_running=arma_tier_processes() > 0,
    ):
        if verdict.line is not None:
            print(verdict.line)  # noqa: T201 — the seat reads these lines
    return 0


if __name__ == "__main__":
    sys.exit(main())
