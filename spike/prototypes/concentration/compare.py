"""PROTOTYPE — throwaway. One command, four arms, the whole comparison (#187).

    uv run python spike/prototypes/concentration/compare.py

Prints every efficacy number the acceptance criteria ask for, per arm, per
board, swept across seeds. The complexity half is a hand count and lives in the
comparison document, not here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent))

import arms  # noqa: E402
import harness  # noqa: E402

from cti_daemon import planner, port  # noqa: E402
from cti_daemon.squads import Held  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable

    from cti_daemon import campaign

SEEDS = 30
CYCLES = 20

# Each arm, and whether its Squads march to a rally before the last leg. The
# baseline has no synchronisation to offer — that is the hole #177 opened with.
ARMS: tuple[tuple[str, Callable[[campaign.Campaign, int], object], bool], ...] = (
    (
        "a  status quo",
        lambda world, seed: arms.Baseline(
            map_manifest=world.map_manifest, table=world.table, seed=seed
        ),
        False,
    ),
    (
        "b1 term x^2",
        lambda world, seed: arms.ConcentrationTerm(
            map_manifest=world.map_manifest, table=world.table, seed=seed, shortfall_power=2.0
        ),
        True,
    ),
    (
        "b1 term x^1",
        lambda world, seed: arms.ConcentrationTerm(
            map_manifest=world.map_manifest, table=world.table, seed=seed, shortfall_power=1.0
        ),
        True,
    ),
    (
        "b1 term step",
        lambda world, seed: arms.ConcentrationTerm(
            map_manifest=world.map_manifest, table=world.table, seed=seed, shortfall_power=0.0
        ),
        True,
    ),
    (
        "b2 muster",
        lambda world, seed: arms.ConcentrationMuster(
            map_manifest=world.map_manifest, table=world.table, seed=seed
        ),
        True,
    ),
    (
        "c  detachment",
        lambda world, seed: arms.DetachmentLayer(
            inner=arms.EchelonScorer(map_manifest=world.map_manifest, table=world.table, seed=seed)
        ),
        True,
    ),
)


@dataclass(frozen=True, slots=True)
class Row:
    """One arm's answer on one board, over the whole sweep."""

    arm: str
    sent: tuple[int, ...]
    strength: tuple[int, ...]
    first: tuple[float, ...]
    separation: tuple[float, ...]
    consolidated: tuple[float, ...]
    # How many distinct Places the side's *other* Squads were sent to. The
    # veto's legitimate job, measured: concentration that empties the island is
    # #34's failure, not a fix.
    elsewhere: tuple[int, ...]
    rallies: tuple[str, ...]
    refusals: tuple[str, ...]


def spread(values: tuple[float, ...]) -> str:
    """`min-max` where a sweep disagreed with itself, one number where it did not."""
    if not values:
        return "-"
    low, high = min(values), max(values)
    if abs(high - low) < 0.05:
        return f"{low:.0f}"
    return f"{low:.0f}-{high:.0f}"


def one_board(
    build: Callable[[], campaign.Campaign],
    target: str,
    synchronised: bool,  # noqa: FBT001
) -> dict[str, Row]:
    """Run every arm over one board, seed by seed."""
    rows: dict[str, Row] = {}
    for name, make, syncs in ARMS:
        sent, strength, first, separation = [], [], [], []
        consolidated, elsewhere, rallies, refusals = [], [], [], []
        for seed in range(SEEDS):
            world = build()
            mind = make(world, seed)
            observation = world.observation("WEST")
            plan = mind.plan(observation)
            open_port = port.CommandPort(campaign=world)
            refusals += [
                judged.code
                for command in plan.commands
                if not (judged := open_port.submit(command, acting_side="WEST")).accepted
            ]
            crew = harness.ordered_to(plan, observation, target)
            walk = harness.march_together if (syncs and synchronised) else harness.march_alone
            read = harness.efficacy(walk(mind_geometry(mind), crew, target))
            sent.append(read.sent)
            strength.append(read.strength_at_contact)
            first.append(read.first)
            separation.append(read.separation)
            consolidated.append(read.consolidated)
            elsewhere.append(harness.dispersion(plan, observation, target))
            rallies.append(read.rally)
        rows[name] = Row(
            arm=name,
            sent=tuple(sent),
            strength=tuple(strength),
            first=tuple(first),
            separation=tuple(separation),
            consolidated=tuple(consolidated),
            elsewhere=tuple(elsewhere),
            rallies=tuple(rallies),
            refusals=tuple(refusals),
        )
    return rows


def mind_geometry(mind: object) -> planner.UtilityPlanner:
    """The scorer holding `_reach`, whether the arm is one or wraps one."""
    return mind.inner if isinstance(mind, arms.DetachmentLayer) else mind


def report(title: str, note: str, rows: dict[str, Row]) -> None:
    """Print one board's table."""
    print(f"\n{title}")
    print(f"  {note}")
    print(
        f"  {'arm':<15}{'sent':>6}{'men @ contact':>15}{'1st contact s':>15}"
        f"{'separation s':>14}{'all-on-target s':>17}{'other places':>14}{'rally':>14}{'refused':>9}"
    )
    for name, _, _ in ARMS:
        row = rows[name]
        rally = sorted({one for one in row.rallies if one}) or ["-"]
        print(
            f"  {name:<15}{spread(tuple(float(one) for one in row.sent)):>6}"
            f"{spread(tuple(float(one) for one in row.strength)):>15}"
            f"{spread(row.first):>15}{spread(row.separation):>14}"
            f"{spread(row.consolidated):>17}"
            f"{spread(tuple(float(one) for one in row.elsewhere)):>14}"
            f"{('/'.join(rally))[:13]:>14}{len(row.refusals):>9}"
        )


# ------------------------------------------------------------------ thrash rate


def thrash(build: Callable[[], campaign.Campaign], target: str) -> dict[str, tuple[int, int]]:
    """Count committed Squads re-tasked over a flickering sweep — #181's shape.

    The disturbance is #181's exactly, moved off the Base and onto the ground
    the concentration is aimed at: the Contact on `target` flickers out and back
    on alternate cycles, which in-world is a leader losing sight of a garrison
    twenty-five metres away for one sample. A **committed** Squad is one standing
    under an offensive Order naming a place; a **re-tasking** is that Squad being
    given a different Order in a later cycle. The rate is re-taskings over
    committed-Squad-cycles.

    The purse is emptied first: a Commander with Funds buys a Squad a cycle, and
    a fresh Squad taking the ground another was marching to re-tasks it for a
    reason that has nothing to do with the picture (#181's own note).
    """
    counted: dict[str, tuple[int, int]] = {}
    for name, make, _ in ARMS:
        retasked = 0
        committed_cycles = 0
        for seed in range(SEEDS):
            world = build()
            world.ledger.spend("WEST", world.ledger.balance("WEST"))
            mind = make(world, seed)
            previous: dict[str, tuple[str, str]] = {}
            for step in range(CYCLES):
                if step % 2:
                    world.contacts.report(
                        "WEST", at_time=world.elapsed, seen=(), observed=(target,)
                    )
                else:
                    harness.sighted(world, "WEST", target, men=4)
                observation = world.observation("WEST")
                plan = mind.plan(observation)
                open_port = port.CommandPort(campaign=world)
                for command in plan.commands:
                    open_port.submit(command, acting_side="WEST")
                now = {
                    squad.id: (squad.order.kind, squad.order.place)
                    for squad in world.roster.roll("WEST")
                }
                for squad, order in previous.items():
                    if order[0] not in arms.OFFENSIVE or squad not in now:
                        continue
                    committed_cycles += 1
                    if now[squad] != order:
                        retasked += 1
                previous = now
                # The world carries the Orders out: everyone stands where sent.
                world.roster.reconcile(
                    {
                        squad.id: Held(squad.size, squad.order.place or squad.at)
                        for squad in world.roster.roll("WEST")
                    }
                )
                world.observe(world.elapsed + 30.0, {})
        counted[name] = (retasked, committed_cycles)
    return counted


def main() -> None:
    """Run every board and print the comparison."""
    print("PROTOTYPE #187 — concentrating force: three shapes, measured offline")
    print(f"real planner, real CommandPort, staged Stratis boards, {SEEDS} seeds, no Arma")
    print(f"march model: {harness.MARCH_SPEED} m/s on foot along the authored adjacency graph")

    report(
        "BOARD A — an EAST-held Objective with a squad-banded garrison (camp_rogain)",
        "four WEST Squads within reach; doctrine (ASSAULT_MASS) wants 2 against a squad band",
        one_board(harness.objective_concentration_board, "camp_rogain", synchronised=True),
    )
    report(
        "BOARD B — the staged two-Squad Assault on the enemy Base (csat_kamino)",
        "island held, squad-banded Contact on the Base; every arm sends the doctrine mass",
        one_board(harness.base_assault_board, "csat_kamino", synchronised=True),
    )
    report(
        "BOARD B' — the same Assault with synchronisation switched off",
        "what the sync mechanism itself is worth, holding the number of Squads fixed",
        one_board(harness.base_assault_board, "csat_kamino", synchronised=False),
    )

    print("\nTHRASH — committed Squads re-tasked under a flickering Contact (#181's shape)")
    print(f"  {CYCLES} cycles x {SEEDS} seeds, purse emptied, Contact on camp_rogain flickering")
    print(f"  {'arm':<15}{'re-tasked':>12}{'committed cycles':>20}{'rate':>10}")
    for name, counts in thrash(harness.objective_concentration_board, "camp_rogain").items():
        retasked, cycles = counts
        rate = f"{retasked / cycles:.3f}" if cycles else "-"
        print(f"  {name:<15}{retasked:>12}{cycles:>20}{rate:>10}")


if __name__ == "__main__":
    main()
