"""PROTOTYPE — throwaway. Offline boards, a march model, and the three measures (#187).

Not production code and not a gate. It exists to answer one question — what does
concentrating force cost and buy, in each of three shapes — and it is deleted
once the human has ruled. Nothing here is imported by `src/` or by the unit tier.

The pattern is #104's and #181's: the **real** planner and the **real**
`CommandPort` over staged boards, swept across seeds, no Arma anywhere. What is
a stand-in is the world — Squads march at a constant speed along the same
adjacency graph the planner scores over, and nobody shoots. What that bounds is
written up in the comparison document; the short version is that every number
below is a *plan* measured in metres and seconds, never a fight.

March speed: 2.0 m/s. Read off the planner's own docstring, which records the
in-world measurement from `spike/probes/ai-commander.sqf` — 1,076 m in about
nine minutes and 2,065 m in about seventeen, which is 1.99 and 2.02 m/s. It is
foot infantry over Stratis, and it is the only kinematic constant here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tests" / "unit"))

from conftest import live  # noqa: E402 — the path insert above is what makes it importable

from cti_daemon import campaign, contacts, planner, port  # noqa: E402
from cti_daemon.commands import Command  # noqa: E402
from cti_daemon.squads import Held  # noqa: E402

if TYPE_CHECKING:
    from cti_daemon.observation import Observation

# Metres per second, on foot. See the module docstring for where it comes from.
MARCH_SPEED = 2.0

# How many men a Squad is bought at, and therefore what one contributes to a
# combined strength. The authored `rifle` Squad; read from the table rather than
# hard-coded would be tidier and is not worth the indirection in a prototype.
SQUAD_MEN = 8


# ---------------------------------------------------------------- staged boards


def held(world: campaign.Campaign, objective: str, side: str) -> None:
    """Walk `side` onto `objective` for long enough to take it."""
    world.observe(world.elapsed + world.table.capture_seconds + 1, {objective: [side]})


def fielded(world: campaign.Campaign, side: str, *places: str) -> None:
    """Stand one of `side`'s Squads on each of `places`, Funds no object."""
    open_port = port.CommandPort(campaign=world)
    world.ledger.deposit(side, 100_000)
    for _ in places:
        open_port.submit(Command("purchase", side, {"squad_type": "rifle"}), acting_side=side)
    world.roster.reconcile(
        {
            squad.id: Held(SQUAD_MEN, place)
            for squad, place in zip(world.roster.roll(side), places, strict=True)
        }
    )


def sighted(world: campaign.Campaign, side: str, place: str, men: int, age: float = 0.0) -> None:
    """Let `side` see `men` of the enemy at `place`, `age` seconds ago."""
    world.contacts.report(
        side,
        at_time=world.elapsed,
        seen=tuple(contacts.Sighting(at=place, kind="Infantry", age=age) for _ in range(men)),
        observed=(place,),
    )


def island_held(*spare: str) -> campaign.Campaign:
    """WEST holds every Objective and stands on each, plus a Squad at each of `spare`."""
    world = live()
    places = [objective.id for objective in world.map_manifest.objectives]
    for place in places:
        held(world, place, "WEST")
    fielded(world, "WEST", *places, *spare)
    return world


def base_assault_board() -> campaign.Campaign:
    """Board B: the staged two-Squad Assault the acceptance criteria name.

    #181's `massed_on_kamino` position. A squad-banded Contact on the enemy Base
    demands `ASSAULT_MASS["squad"]` — two — so every arm sends the same number
    and what separates them is *how* the two travel.
    """
    world = island_held()
    sighted(world, "WEST", "csat_kamino", men=4)
    return world


def objective_concentration_board() -> campaign.Campaign:
    """Board A: one EAST-held Objective with more on it than one Squad answers.

    The playtest's own case, and the one the status-quo veto forbids outright:
    `_assign` gives a Place to one Squad and turns the rest away, so a
    squad-banded garrison on an Objective is attacked eight men at a time no
    matter how much force is standing next door.

    Camp Rogain because it is the Objective the enemy Base touches, so it is
    where a real Campaign's fighting concentrates, and because three WEST Squads
    sit within two kilometres of it.
    """
    world = live()
    for objective in world.map_manifest.objectives:
        if objective.id != "camp_rogain":
            held(world, objective.id, "WEST")
    held(world, "camp_rogain", "EAST")
    fielded(world, "WEST", "lz_baldy", "agia_marina", "old_outpost", "air_station")
    sighted(world, "WEST", "camp_rogain", men=4)
    return world


# ------------------------------------------------------------- the march model


@dataclass(frozen=True, slots=True)
class March:
    """One Squad's trip: where it starts, where it is sent, how long that takes."""

    squad: str
    origin: str
    target: str
    # Seconds from the Order to standing on the target, waiting included.
    arrives: float
    # Where it waited for the rest, or "" for a Squad that marched straight there.
    rallied: str = ""


def kilometres(mind: planner.UtilityPlanner, origin: str, target: str) -> float:
    """Graph distance in km — the planner's own `_reach`, so both agree on geography."""
    return mind._reach[origin][target]  # noqa: SLF001 — a prototype reading the real geometry


def seconds(mind: planner.UtilityPlanner, origin: str, target: str) -> float:
    """How long a Squad takes to walk from one Place to another."""
    return kilometres(mind, origin, target) * 1_000.0 / MARCH_SPEED


def march_alone(mind: planner.UtilityPlanner, crew: dict[str, str], target: str) -> list[March]:
    """Every Squad walks from where it is, the moment it is told. The status quo."""
    return [
        March(squad=squad, origin=origin, target=target, arrives=seconds(mind, origin, target))
        for squad, origin in sorted(crew.items())
    ]


def rally_point(mind: planner.UtilityPlanner, crew: dict[str, str], target: str) -> str:
    """Pick where a crew forms up before the last leg.

    Minimises when the **combined** force reaches the target: the last Squad's
    walk to the rally, plus the joint walk from the rally onward. Never the
    target itself — a rally on the objective is piecemeal arrival wearing a
    different name, which is the thing the mechanism exists to stop.
    """
    candidates = [place for place in mind._reach if place != target]  # noqa: SLF001
    return min(
        candidates,
        key=lambda place: (
            max(seconds(mind, origin, place) for origin in crew.values())
            + seconds(mind, place, target),
            place,
        ),
    )


def march_together(mind: planner.UtilityPlanner, crew: dict[str, str], target: str) -> list[March]:
    """Everyone walks to a rally, waits for the last, and the crew goes on as one."""
    if len(crew) < 2:
        return march_alone(mind, crew, target)
    rally = rally_point(mind, crew, target)
    ready = max(seconds(mind, origin, rally) for origin in crew.values())
    arrives = ready + seconds(mind, rally, target)
    return [
        March(squad=squad, origin=origin, target=target, arrives=arrives, rallied=rally)
        for squad, origin in sorted(crew.items())
    ]


# ------------------------------------------------------------------- the measures


@dataclass(frozen=True, slots=True)
class Efficacy:
    """What one arm's plan is worth on one board."""

    # How many Squads the arm sent at the place.
    sent: int
    # Men standing on the target when the first of them walks onto it.
    strength_at_contact: int
    # When that first contact happens. Synchronisation buys strength here and
    # pays for it in seconds, and this is the column the bill arrives on.
    first: float
    # Seconds between the first arrival and the last. Zero for a force that
    # arrives as one.
    separation: float
    # When the whole force is finally on the target. What synchronisation costs
    # is visible here and nowhere else.
    consolidated: float
    rally: str = ""


def efficacy(marches: list[March]) -> Efficacy:
    """Read the three arrival numbers off one crew's marches."""
    if not marches:
        return Efficacy(sent=0, strength_at_contact=0, first=0.0, separation=0.0, consolidated=0.0)
    first = min(one.arrives for one in marches)
    last = max(one.arrives for one in marches)
    # First contact is the moment the leading Squad walks onto the target. What
    # fights at that moment is every Squad already there — which, unsynchronised,
    # is the leading Squad alone.
    together = sum(1 for one in marches if one.arrives <= first + 1e-9)
    return Efficacy(
        sent=len(marches),
        strength_at_contact=together * SQUAD_MEN,
        first=first,
        separation=last - first,
        consolidated=last,
        rally=next((one.rallied for one in marches if one.rallied), ""),
    )


def dispersion(plan: planner.Plan, observation: Observation, target: str) -> int:
    """How many distinct Places the Squads *not* concentrating were sent to.

    The veto's legitimate job stated as a number. A concentration arm that takes
    the whole force to one town scores 0 here and has fixed #177 by causing #34.
    """
    going: dict[str, str] = {
        squad.id: squad.place for squad in observation.squads if squad.order and squad.place
    }
    for command in plan.commands:
        if command.name == "order":
            going[command.args["squad"]] = command.args["place"]
    return len({place for place in going.values() if place and place != target})


def ordered_to(plan: planner.Plan, observation: Observation, place: str) -> dict[str, str]:
    """Squads this plan sends to `place`, mapped to where each is standing now.

    Both halves of "sent there": Squads given a fresh Order this cycle, and
    Squads already standing under one for the same Place — a plan repeats no
    Order it need not (`_deploy`), so a committed crew issues no Commands at all
    and reading only the Commands would count it as nobody.
    """
    standing = {squad.id: squad for squad in observation.squads}
    going = {
        squad.id: squad.at for squad in observation.squads if squad.place == place and squad.order
    }
    for command in plan.commands:
        if command.name != "order":
            continue
        squad = standing[command.args["squad"]]
        if command.args["place"] == place:
            going[squad.id] = squad.at
        else:
            going.pop(squad.id, None)
    return going
