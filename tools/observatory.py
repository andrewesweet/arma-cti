#!/usr/bin/env python3
"""The retrospective observatory (ADR-0071 ruling 6, #336) — it reports and never routes.

The upfront admission bar was dropped by #328, and nothing upfront replaces it. What
replaces it is this: a rollup read over time, from records rather than from opinion,
answering one question — **which routes produced work that needed rework, and how often**.

Nothing here excludes a profile, reroutes work or trips a breaker. The action on a bad
ranking is a human ruling at a retro, and a threshold that acted by itself would be the
upfront bar rebuilt with extra steps.

## What it reads, and what it cannot

Two directories, both outside every worktree:

- `~/.arma-cti/dispatches/<id>/dispatch.json` — lane, profile, seat, issue, and the
  pre-work `strata` #323 added and #347 gave typed degradation codes. `ledger.json`
  beside it where `just ledger-sync` has materialised the row, for spend.
- `~/.arma-cti/review/<issue>/` — `loop.json` while a loop runs, `landing.json` once its
  terminus has run (#333).

**A dispatched seat cannot reach either** (#294's confinement, measured again on this
issue's own worktree: `ls ~/.arma-cti/` is refused). So both roots are options with
environment twins, the way `tools/queue_policy.py` takes `CTI_DISPATCH_DIR`, and a root
this process cannot see is `state_unreachable` at exit 3 — an act that could not be
performed — never an empty rollup at exit 0. An observatory that reported "no rework
anywhere" because it was standing in a room with no windows would be worse than no
observatory, and that is the exact failure mode the bar died of, inverted.

## The key, and everything beside it

**Fix rounds per landing**, and only that. Five dimensions do not order themselves and
inventing a conversion between them is ADR-0061 Decision 5's error; a different key is a
ruling, not a preference. It is defined only where its denominator exists, so it ranks
**profiles dispatched in the `implementer` seat and no others**. `review`, `recon`,
`planner` and `retro` land nothing by contract — their rework is reported, never ranked —
and an implementer whose work never reached a terminus is a zero denominator that shows as
an unranked row with its rounds visible, never as a division.

A **landing** here is a review loop that reached its terminus: `landing.json` exists for
that issue. That is the one durable per-issue fact that pairs with `review_rounds`, which
is also per issue. It is deliberately not the ledger's `gate.landed`, which is per dispatch
and exists only where `just ledger-sync` has run — a missing row would read as "did not
land" and make the denominator smaller, which flatters or damns a profile on the strength
of whether a housekeeping command was run.

**Rounds are booked to the implementer, and that is where rework appeared, never who
caused it.** This ADR's own second escalation condition says a repeated three-round state
is evidence the *item* was under-specified — caused upstream, by planning. Stratifying
helps and does not solve it; apportioning between implementer and planner would be the
forbidden conversion. The rollup states this rather than correcting for it.

## Spend, strata, and the column that is absent

Spend is reported **per lane and never summed**. Three meters — the Anthropic plan's
five-hour window, z.ai's prompt count, Codex's absence of published terms — do not convert
into one another, so there is no total line and no cross-lane comparison, by construction:
`render_spend` emits one line per lane and there is nowhere for a total to go.

Stratification uses **only the pre-work signals** on the record — gate tier, routing class,
labels — read through `dispatch.read_strata`, so a record predating #323 or carrying a
malformed signal classifies by its typed `code` rather than by prose. Outcome measures sit
beside them and the `note` line says which fields are which, because a reader who cannot
tell a stratum from an outcome will stratify on an outcome eventually.

**There is no containment column.** A bypassed commit hook leaves no durable fact: this
repo's `.claude/hooks/block-no-verify.py` *denies* the command rather than recording it,
none of the nine hooks writes a bypass anywhere (only `deny-oversized-reads.py` opens a
file at all, and not for this), and the ledger records no command body by design. So the
column would sit empty and be read as evidence that bypasses did not occur, which is worse
than no column. ADR-0071 ruling 6 makes that the condition; the condition is unmet; the
column is absent and this paragraph is the documentation of the choice.

## What the numbers cannot support

The bar this replaces was dropped because it never adjudicated once. A rollup that reported
confident quality judgements off two records would fail the same way from the other end, so
thin evidence is a stated verdict on the row rather than a rank. `THIN_EVIDENCE_BELOW` is
**an estimate, not a measurement** — no power calculation, base rate or effect size stands
behind ADR-0071's "20 to 30 landings", and the ADR says so in as many words. Every caveat
the ruling records is printed with the rollup rather than kept in a document beside it,
because a caveat a reader has to go and find is one that will be read after the conclusion.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `dispatch.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes this importable. `read_strata` is the whole reason:
# #347 put a typed degradation code on every stratum precisely so this module need not
# re-derive the state from prose, and a second reader here would be a second opinion about
# what a malformed record means.
import dispatch

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

DEFAULT_DISPATCH_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"
DEFAULT_REVIEW_ROOT: Final = Path.home() / ".arma-cti" / "review"

# The seat whose landings give the key its denominator. ADR-0071 ruling 2 leaves this as
# the only seat that reaches `just land` under a review loop, and ruling 6 ranks it alone.
RANKED_SEAT: Final = "implementer"

# Below this many landings a row carries its numbers and no rank. An estimate, not a
# measurement — see the module docstring. Named here so a reader can see the figure the
# verdict turns on rather than infer it from behaviour.
THIN_EVIDENCE_BELOW: Final = 20

LOOP_FILE: Final = "loop.json"
LANDING_FILE: Final = "landing.json"
DISPATCH_FILE: Final = "dispatch.json"
LEDGER_FILE: Final = "ledger.json"

RANKED: Final = "ranked"
THIN: Final = "thin_evidence"
NO_LANDINGS: Final = "no_landings"

UNREACHABLE: Final = "state_unreachable"


class Record(NamedTuple):
    """One dispatch, reduced to what the rollup joins and stratifies on."""

    dispatch_id: str
    lane: str
    profile: str
    seat: str
    issue: int
    strata: dispatch.Strata


class Scan(NamedTuple):
    """What a root yielded, and what in it would not read.

    The unreadable ids are carried rather than dropped: a rollup that silently skipped a
    corrupt record would report a smaller, cleaner world than the one on disk, and the
    count of records it could not read is the first thing that tells a reader how much of
    the answer is missing.
    """

    records: tuple[Record, ...]
    unreadable: tuple[str, ...]


class LoopState(NamedTuple):
    """One issue's review loop: how many fix rounds it took, and whether it terminated.

    `terminus` is `landing.json` existing — the loop reached its landing decision. That is
    the landing this rollup counts, for the reason the module docstring gives.
    """

    issue: int
    review_rounds: int
    terminus: bool


class Row(NamedTuple):
    """One profile's rework, with the verdict that says whether it may be ranked."""

    profile: str
    seat: str
    dispatches: int
    issues: int
    landings: int
    rounds: int
    verdict: str

    @property
    def key(self) -> float | None:
        """Fix rounds per landing, or `None` where the denominator does not exist.

        `None` rather than infinity: a profile with no landings has no ranking, and a
        number that sorts is exactly what would put it in the ordering anyway.
        """
        if self.landings == 0:
            return None
        return self.rounds / self.landings


class Spend(NamedTuple):
    """One lane's spend. There is no field here that could hold a cross-lane total."""

    lane: str
    dispatches: int
    rows: int
    input_tokens: int
    output_tokens: int


class Rollup(NamedTuple):
    """Everything the rollup found, before it is rendered."""

    dispatches: Scan
    loops: tuple[LoopState, ...]
    unreadable_loops: tuple[str, ...]
    rows: tuple[Row, ...]
    spend: tuple[Spend, ...]
    strata: tuple[tuple[str, str, Counter[str]], ...]
    shared_issues: int


def read_json(path: Path) -> Mapping[str, object] | None:
    """Read one JSON object, or `None` where it is absent, broken or not an object.

    Every caller distinguishes those three the same way — it cannot use the file — so they
    are one answer here rather than three exceptions each caller re-catches.
    """
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def _int(value: object) -> int | None:
    """Narrow a recorded integer, refusing the bool that `isinstance(True, int)` admits."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def read_record(directory: Path) -> Record | None:
    """Read one dispatch record, or `None` where it will not read as one this rollup joins.

    An issue is required, because the join to the review loop is on the issue number and a
    dispatch that names none cannot be attributed to any rework at all. Refusing it here
    rather than carrying it as issue zero keeps a whole class of unjoinable rows out of the
    denominators, and the caller counts what it refused.
    """
    document = read_json(directory / DISPATCH_FILE)
    if document is None:
        return None
    issue = _int(document.get("issue"))
    lane = document.get("lane")
    profile = document.get("profile")
    seat = document.get("seat")
    if issue is None or issue <= 0:
        return None
    if not (isinstance(lane, str) and isinstance(profile, str) and isinstance(seat, str)):
        return None
    return Record(
        dispatch_id=directory.name,
        lane=lane,
        profile=profile,
        seat=seat,
        issue=issue,
        strata=dispatch.read_strata(document),
    )


def read_dispatches(root: Path) -> Scan:
    """Read every dispatch record under `root`, sorted, with the unreadable ones named."""
    records: list[Record] = []
    unreadable: list[str] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        record = read_record(directory)
        if record is None:
            unreadable.append(directory.name)
        else:
            records.append(record)
    return Scan(tuple(records), tuple(unreadable))


def read_loop(directory: Path) -> LoopState | None:
    """Read one issue's loop state, preferring the terminus record over the in-flight one.

    `landing.json` is the loop's final word on its own round count and is the file that
    makes the landing true, so it is read first; `loop.json` answers for a loop still in
    flight. A directory whose name is not an issue number, or which carries neither file in
    a readable shape, is not a loop this rollup can join.
    """
    if not directory.name.isdigit():
        return None
    landing = read_json(directory / LANDING_FILE)
    document = landing if landing is not None else read_json(directory / LOOP_FILE)
    if document is None:
        return None
    rounds = _int(document.get("review_rounds"))
    if rounds is None or rounds < 0:
        return None
    return LoopState(issue=int(directory.name), review_rounds=rounds, terminus=landing is not None)


def read_loops(root: Path) -> tuple[tuple[LoopState, ...], tuple[str, ...]]:
    """Read every review loop under `root`, with the directories that would not read named."""
    loops: list[LoopState] = []
    unreadable: list[str] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        loop = read_loop(directory)
        if loop is None:
            unreadable.append(directory.name)
        else:
            loops.append(loop)
    return tuple(loops), tuple(unreadable)


def verdict(landings: int) -> str:
    """Say whether this row's landings support a rank, thin evidence, or no denominator."""
    if landings == 0:
        return NO_LANDINGS
    if landings < THIN_EVIDENCE_BELOW:
        return THIN
    return RANKED


def build_rows(records: Sequence[Record], loops: Mapping[int, LoopState]) -> tuple[Row, ...]:
    """One row per (profile, seat), carrying the rework that appeared on its issues.

    Rounds and landings are counted **per issue, once**, not per dispatch: three dispatches
    of one profile onto one issue are one loop with one round count, and counting the loop
    three times would multiply one item's rework into a profile-wide finding.

    Rows are ordered by the key where it exists, and the two verdicts without a rank follow
    it — thin evidence before no denominator, each alphabetically. That ordering is the
    ranking: a reader who sorts these rows by eye must not be able to place an unranked row
    among the ranked ones by accident.
    """
    issues: dict[tuple[str, str], set[int]] = {}
    dispatch_counts: Counter[tuple[str, str]] = Counter()
    for record in records:
        identity = (record.profile, record.seat)
        dispatch_counts[identity] += 1
        issues.setdefault(identity, set()).add(record.issue)
    rows: list[Row] = []
    for identity, seen in issues.items():
        profile, seat = identity
        # A seat that lands nothing by contract has its rework reported and never ranked,
        # so its landings are not counted at all rather than counted and found to be zero:
        # `no_landings` on a `review` row would read as a failure to land rather than as
        # the contract.
        ranked_seat = seat == RANKED_SEAT
        landings = sum(1 for issue in seen if loops.get(issue, None) and loops[issue].terminus)
        rounds = sum(loops[issue].review_rounds for issue in seen if issue in loops)
        rows.append(
            Row(
                profile=profile,
                seat=seat,
                dispatches=dispatch_counts[identity],
                issues=len(seen),
                landings=landings if ranked_seat else 0,
                rounds=rounds,
                verdict=verdict(landings) if ranked_seat else "lands_nothing",
            )
        )
    order = {RANKED: 0, THIN: 1, NO_LANDINGS: 2, "lands_nothing": 3}
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                order.get(row.verdict, 4),
                row.key if row.key is not None else 0.0,
                row.profile,
                row.seat,
            ),
        )
    )


def build_spend(records: Sequence[Record], root: Path) -> tuple[Spend, ...]:
    """Sum spend within each lane and never across them.

    The return is one entry per lane and the renderer emits one line per entry, so there is
    no place a total could be written. That is the point: ADR-0061 Decision 5's error is
    inventing a conversion between meters that do not convert, and the cheapest defence
    against inventing one later is a shape with nowhere to put it.

    A dispatch whose `ledger.json` has not been materialised is counted as a dispatch and
    not as a row, so a lane's `rows` short of its `dispatches` says how much of that lane's
    spend is simply unmeasured rather than zero.
    """
    dispatches: Counter[str] = Counter()
    rows: Counter[str] = Counter()
    inputs: Counter[str] = Counter()
    outputs: Counter[str] = Counter()
    for record in records:
        dispatches[record.lane] += 1
        row = read_json(root / record.dispatch_id / LEDGER_FILE)
        if row is None:
            continue
        usage = row.get("usage")
        if not isinstance(usage, dict):
            continue
        rows[record.lane] += 1
        inputs[record.lane] += _int(usage.get("input_tokens")) or 0
        outputs[record.lane] += _int(usage.get("output_tokens")) or 0
    return tuple(
        Spend(
            lane=lane,
            dispatches=dispatches[lane],
            rows=rows[lane],
            input_tokens=inputs[lane],
            output_tokens=outputs[lane],
        )
        for lane in sorted(dispatches)
    )


def _stratum_key(stratum: dispatch.Stratum) -> str:
    """Render one signal as its grouping key: the value where checked, the code where not.

    The code and never the reason (#347). `unchecked_why` is diagnostic prose, and #323 left
    the degradation states apart only by their reasons — four examples that happened not to
    collide rather than a contract.
    """
    if not stratum.checked:
        return stratum.code
    value = stratum.value
    if isinstance(value, dispatch.RoutingClass):
        return value.rule_id or "none"
    if isinstance(value, tuple):
        return ",".join(sorted(str(item) for item in value)) or "none"
    return str(value) if value else "none"


def build_strata(records: Sequence[Record]) -> tuple[tuple[str, str, Counter[str]], ...]:
    """Per ranked-seat profile, the distribution of each pre-work signal.

    Only the three signals on the record, which are knowable before the seat starts work.
    Nothing derived from an outcome reaches this function, and that absence is what makes
    the strata strata — a gate tier read back off the diff would put the router's own
    assignment into a profile finding in a subtler form.

    Only the ranked seat, because the strata exist to say whether a comparison between two
    ranked rows is like for like, and there is no comparison to qualify anywhere else.
    """
    counts: dict[tuple[str, str], Counter[str]] = {}
    for record in records:
        if record.seat != RANKED_SEAT:
            continue
        for signal, stratum in (
            ("gate_tier", record.strata.gate_tier),
            ("routing_class", record.strata.routing_class),
            ("labels", record.strata.labels),
        ):
            counts.setdefault((record.profile, signal), Counter())[_stratum_key(stratum)] += 1
    return tuple((profile, signal, counts[(profile, signal)]) for profile, signal in sorted(counts))


def rollup(dispatch_root: Path, review_root: Path) -> Rollup:
    """Read both roots and assemble the whole rollup."""
    scan = read_dispatches(dispatch_root)
    loops, unreadable_loops = read_loops(review_root)
    by_issue = {loop.issue: loop for loop in loops}
    implementers: dict[int, set[str]] = {}
    for record in scan.records:
        if record.seat == RANKED_SEAT:
            implementers.setdefault(record.issue, set()).add(record.profile)
    return Rollup(
        dispatches=scan,
        loops=loops,
        unreadable_loops=unreadable_loops,
        rows=build_rows(scan.records, by_issue),
        spend=build_spend(scan.records, dispatch_root),
        strata=build_strata(scan.records),
        # An issue two implementer profiles were dispatched onto books its rounds to both.
        # ADR-0071 records the subagent under-attribution as a known distortion; this is
        # its sibling, and the count is printed so a reader can see how much of the rollup
        # rests on it rather than being told it exists in the abstract.
        shared_issues=sum(1 for profiles in implementers.values() if len(profiles) > 1),
    )


def _counts(counter: Counter[str]) -> str:
    """Render a distribution in a stable order — by descending count, then by key."""
    return ",".join(
        f"{key}:{count}" for key, count in sorted(counter.items(), key=lambda p: (-p[1], p[0]))
    )


CAVEATS: Final = (
    (
        "the key is where rework appeared and never who caused it — a repeated three-round"
        " state is ADR-0071's own evidence that the item was under-specified, which is caused"
        " upstream by planning and booked here to the implementer"
    ),
    (
        "attribution is dispatch_only: the orchestrator's own turns carry no dispatch id and"
        " reach no row, and an in-session subagent shares its parent's resource block and"
        " cannot be ledgered at all, so this is all dispatched work and never all work"
    ),
    (
        f"thin_evidence below {THIN_EVIDENCE_BELOW} landings is an estimate and not a"
        " measurement — no power calculation, base rate or effect size stands behind it"
    ),
    (
        "fallback profiles accumulate observations only during breaker incidents, because"
        " seat resolution always takes the head profile — systematically confounded and"
        " never numerous"
    ),
    (
        "there is no containment column: a bypassed commit hook leaves no durable record, so"
        " the column would sit empty and be misread as evidence that bypasses did not occur"
    ),
    "spend is per lane and is never summed: three meters that do not convert into one another",
    "this reports and never routes — the action on a bad ranking is a human ruling at a retro",
)


def render(found: Rollup, dispatch_root: Path, review_root: Path) -> tuple[str, ...]:
    """Render the rollup as the tier's `key=value` lines, caveats included in the output."""
    lines = [
        " ".join(
            (
                "observatory",
                f"dispatch_root={dispatch_root}",
                f"review_root={review_root}",
                f"dispatches={len(found.dispatches.records)}",
                f"dispatches_unreadable={len(found.dispatches.unreadable)}",
                f"loops={len(found.loops)}",
                f"loops_unreadable={len(found.unreadable_loops)}",
                f"terminated={sum(1 for loop in found.loops if loop.terminus)}",
                f"shared_issues={found.shared_issues}",
            )
        ),
        " ".join(
            (
                "note",
                f"ranking_key=rounds_per_landing ranked_seat={RANKED_SEAT}",
                "strata_fields=gate_tier,routing_class,labels",
                "description_fields=dispatches,issues,landings,rounds,key",
                "containment_column=absent",
            )
        ),
    ]
    for row in found.rows:
        key = f"{row.key:.3f}" if row.key is not None else "none"
        lines.append(
            " ".join(
                (
                    "row",
                    f"profile={row.profile}",
                    f"seat={row.seat}",
                    f"verdict={row.verdict}",
                    f"key={key}",
                    f"rounds={row.rounds}",
                    f"landings={row.landings}",
                    f"issues={row.issues}",
                    f"dispatches={row.dispatches}",
                )
            )
        )
    lines.extend(
        " ".join(
            (
                "spend",
                f"lane={spend.lane}",
                f"dispatches={spend.dispatches}",
                f"ledger_rows={spend.rows}",
                f"in={spend.input_tokens}",
                f"out={spend.output_tokens}",
            )
        )
        for spend in found.spend
    )
    lines.extend(
        f"strata profile={profile} signal={signal} {_counts(counter)}"
        for profile, signal, counter in found.strata
    )
    lines.extend(f"caveat {caveat}" for caveat in CAVEATS)
    return tuple(lines)


def unreachable(dispatch_root: Path, review_root: Path) -> tuple[str, ...]:
    """Name the roots this process cannot see, or return empty where it can see both.

    Separate from the read so that "I could not look" is decided before anything is
    counted. A rollup assembled over a root that is not there is a confident zero, and this
    is the one refusal that keeps it from ever being printed.
    """
    return tuple(f"root={root}" for root in (dispatch_root, review_root) if not root.is_dir())


def refusal(missing: Sequence[str]) -> tuple[str, ...]:
    """Render the `state_unreachable` refusal: class, evidence, remedy — the tier's shape."""
    return (
        f"refusal={UNREACHABLE}",
        *missing,
        (
            "This process cannot see the records the rollup reads. A dispatched seat is"
            " confined to its worktree (#294) and ~/.arma-cti is outside it, so the rollup"
            " cannot run from inside a dispatch — run it from a session that can read the"
            " state, or point --dispatch-root and --review-root at readable copies. Nothing"
            " was counted; this is not an empty rollup."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the rollup over both roots, or refuse at exit 3 the one it cannot see."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dispatch-root",
        type=Path,
        default=Path(os.environ.get("CTI_DISPATCH_DIR", str(DEFAULT_DISPATCH_ROOT))),
    )
    parser.add_argument(
        "--review-root",
        type=Path,
        default=Path(os.environ.get("CTI_REVIEW_DIR", str(DEFAULT_REVIEW_ROOT))),
    )
    args = parser.parse_args(argv)
    missing = unreachable(args.dispatch_root, args.review_root)
    if missing:
        # Exit 3 is an act that could not be performed, never a result and never a green —
        # the same code `just review-loop` gives when it could not look.
        print("\n".join(refusal(missing)), file=sys.stderr)  # noqa: T201 — a CLI's refusal channel
        return 3
    found = rollup(args.dispatch_root, args.review_root)
    print(  # noqa: T201 — a CLI's output channel
        "\n".join(render(found, args.dispatch_root, args.review_root))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
