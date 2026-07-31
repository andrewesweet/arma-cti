"""The AI Commander's scorer (#16).

A pure function of one Observation and the authored data behind it, so every
test here runs without Arma. What it plans against is the same fogged picture a
human Commander gets (ADR-0012) — banded, aged Contacts and no enemy roster —
so a test that reached for ground truth would be testing a planner nobody is
going to ship.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cti_daemon import campaign, contacts, economy, manifest, planner, port
from cti_daemon.commands import Command
from cti_daemon.outbox import Outbox

REPO = Path(__file__).parents[2]


def live() -> campaign.Campaign:
    """Return a campaign on the authored Stratis map, everything Neutral."""
    table = economy.load(REPO / "config" / "economy.json")
    return campaign.Campaign(
        map_manifest=manifest.load(REPO / "manifests" / "stratis.json"),
        table=table,
        ledger=economy.Ledger(table.starting_funds),
        outbox=Outbox(),
    )


def brain(world: campaign.Campaign, seed: int = 0) -> planner.UtilityPlanner:
    """Return a planner reading the authored data this campaign runs on."""
    return planner.UtilityPlanner(map_manifest=world.map_manifest, table=world.table, seed=seed)


def test_a_commander_with_funds_and_no_squads_buys_one() -> None:
    # Funds buy nothing on their own: the only thing they convert into is force,
    # and a Commander sitting on its starting balance has made no move at all.
    world = live()
    (bought,) = brain(world).plan(world.observation("WEST")).commands

    assert bought.name == "purchase"
    assert bought.side == "WEST"
    assert bought.args["squad_type"] in {squad.id for squad in world.table.squads}


def fielded(world: campaign.Campaign, side: str, *places: str) -> None:
    """Stand one of `side`'s Squads on each of `places`, Funds no object."""
    open_port = port.CommandPort(campaign=world)
    world.ledger.deposit(side, 100_000)
    for _ in places:
        open_port.submit(Command("purchase", side, {"squad_type": "rifle"}), acting_side=side)
    world.roster.reconcile(
        {squad.id: (8, place) for squad, place in zip(world.roster.roll(side), places, strict=True)}
    )


def only(decisions: tuple[planner.Decision, ...], about: str) -> planner.Decision:
    """Return the one decision made about `about`."""
    (decision,) = [decision for decision in decisions if decision.about == about]
    return decision


def test_a_commander_stops_buying_once_it_has_a_squad_for_every_objective() -> None:
    # A Squad takes ground by standing in a capture radius, and there are only
    # so many radii. Buying past that is Funds converted into men with nowhere
    # of their own to be — and #26's byte ceiling is what a runaway force blows.
    world = live()
    fielded(world, "WEST", *[""] * len(world.map_manifest.objectives))

    plan = brain(world).plan(world.observation("WEST"))

    assert [command for command in plan.commands if command.name == "purchase"] == []
    assert only(plan.decisions, "funds").chose == "nothing"


def test_a_commander_that_cannot_afford_anything_says_so_rather_than_buying() -> None:
    world = live()
    world.ledger.spend("WEST", world.ledger.balance("WEST"))

    decision = only(brain(world).plan(world.observation("WEST")).decisions, "funds")
    assert decision.chose == "nothing"
    assert decision.candidates == ()


def orders(plan: planner.Plan) -> dict[str, tuple[str, str]]:
    """Return the Order each Squad is being given, keyed by Squad id."""
    return {
        command.args["squad"]: (command.args["order"], command.args["objective"])
        for command in plan.commands
        if command.name == "order"
    }


def test_a_squad_at_base_is_sent_at_ground_the_side_does_not_hold() -> None:
    # Adjacency is the whole geometry the scorer has (ADR-0004), so the answer
    # is read out of the manifest rather than out of the planner: the Squad goes
    # to ground the Base actually touches, not to the far end of the island.
    world = live()
    fielded(world, "WEST", "nato_airbase")
    (base,) = [base for base in world.map_manifest.bases if base.side == "WEST"]

    (order,) = orders(brain(world).plan(world.observation("WEST"))).values()
    assert order[0] == "capture"
    assert order[1] in set(base.adjacent)


def held(world: campaign.Campaign, objective: str, side: str) -> None:
    """Walk `side` onto `objective` for long enough to take it."""
    world.observe(world.elapsed + world.table.capture_seconds + 1, {objective: [side]})


def test_a_squad_on_quiet_ground_its_side_holds_moves_on_to_take_more() -> None:
    # `Campaign._advance` keeps ground taken once taken, so standing on it buys
    # nothing the Campaign was not already paying. A garrison is for ground
    # somebody is coming for, and nobody is.
    world = live()
    held(world, "agia_marina", "WEST")
    fielded(world, "WEST", "agia_marina")

    (order,) = orders(brain(world).plan(world.observation("WEST"))).values()
    assert order[0] == "capture"
    assert order[1] != "agia_marina"


def test_a_squad_on_threatened_ground_its_side_holds_is_told_to_garrison_it() -> None:
    # The same Contact reads opposite ways depending on who holds the ground:
    # a reason to stay away from ground the enemy holds, a reason to stand on
    # ground you do. And never Capture, which the port refuses on ground the
    # side already holds — a scorer that needed telling is one issuing dead
    # Orders every cycle.
    #
    # A company, because that is the echelon the weights are tuned to stop for:
    # a Commander told to press (`Weights`) marches on past a squad-sized
    # sighting behind it and turns round only for a real massed incursion.
    world = live()
    held(world, "agia_marina", "WEST")
    fielded(world, "WEST", "agia_marina")
    world.contacts.report(
        "WEST",
        at_time=world.elapsed,
        seen=tuple(
            contacts.Sighting(at="agia_marina", kind="Infantry", age=0.0) for _ in range(25)
        ),
        observed=("agia_marina",),
    )

    (order,) = orders(brain(world).plan(world.observation("WEST"))).values()
    assert order == ("defend", "agia_marina")


def sighted(world: campaign.Campaign, side: str, place: str, men: int, age: float = 0.0) -> None:
    """Let `side` see `men` of the enemy at `place`, `age` seconds ago."""
    world.contacts.report(
        side,
        at_time=world.elapsed,
        seen=tuple(contacts.Sighting(at=place, kind="Infantry", age=age) for _ in range(men)),
        observed=(place,),
    )


def test_a_squad_is_steered_away_from_ground_the_enemy_is_standing_on() -> None:
    # Both are one hop from the Base and pay the same, so the Contact is the
    # only thing between them and the choice is the whole of what it is for.
    world = quiet_start()
    sighted(world, "WEST", "agia_marina", men=25)

    (order,) = orders(brain(world).plan(world.observation("WEST"))).values()
    assert order == ("capture", "camp_tempest")


def quiet_start() -> campaign.Campaign:
    """Return the opening position: one Squad at Base, nothing ever seen."""
    world = live()
    fielded(world, "WEST", "nato_airbase")
    return world


def test_a_contact_nobody_has_refreshed_stops_steering_anything() -> None:
    # Staleness weighed rather than ignored (#16's fog note): a company seen ten
    # minutes ago is not a company standing there now. What it decays *to* is
    # the next test's business — here it is only that it stops deciding.
    world = quiet_start()
    sighted(world, "WEST", "agia_marina", men=25, age=600.0)
    baseline = quiet_start()

    assert orders(brain(world).plan(world.observation("WEST"))) == orders(
        brain(baseline).plan(baseline.observation("WEST"))
    )


def scores(decision: planner.Decision) -> dict[str, float]:
    """Return what each candidate in a decision was worth."""
    return {candidate.choice: candidate.score for candidate in decision.candidates}


def test_ground_nobody_is_looking_at_is_not_scored_as_empty_ground() -> None:
    # The trap #16 names: absence of a Contact is not absence of the enemy. One
    # of ours is standing on agia_marina and reporting nobody, and nobody has
    # been near camp_tempest — so the first is empty and the second is unknown,
    # and a scorer that could not tell them apart would walk into things.
    world = live()
    fielded(world, "WEST", "nato_airbase", "agia_marina")

    weighed = scores(only(brain(world).plan(world.observation("WEST")).decisions, "WEST-1"))
    assert weighed["capture agia_marina"] > weighed["capture camp_tempest"]


def cycle(
    world: campaign.Campaign, mind: planner.UtilityPlanner, side: str
) -> tuple[planner.Plan, list[port.Judgement]]:
    """Run one report-and-plan cycle: the Commander decides, the port judges."""
    plan = mind.plan(world.observation(side))
    open_port = port.CommandPort(campaign=world)
    return plan, [open_port.submit(command, acting_side=side) for command in plan.commands]


def test_a_commander_stops_repeating_an_order_the_squad_is_already_under() -> None:
    # Progress rather than chatter: an unchanged world produces no second round
    # of Orders, so the outbox carries what changed and #19 has something to
    # audit rather than the same eight effects every five seconds.
    world = live()
    fielded(world, "WEST", *[""] * len(world.map_manifest.objectives))
    mind = brain(world)

    first, _ = cycle(world, mind, "WEST")
    second, _ = cycle(world, mind, "WEST")

    assert len(orders(first)) == len(world.roster.roll("WEST"))
    assert orders(second) == {}


def test_a_standing_order_survives_news_too_small_to_act_on() -> None:
    # Hysteresis, and the whole anti-thrash rule: a Squad already marching
    # somewhere does not turn round for a team, and does turn round for a
    # company. Without the margin, two Objectives whose scores cross and recross
    # would have it countermarching every five seconds and arriving nowhere.
    # Broke for a Commander with Funds: it buys a Squad a cycle, the new Squad
    # takes the Objective WEST-1 would have turned round for, and WEST-1 keeps
    # its place for a reason that has nothing to do with the margin. One Squad
    # and an empty purse is the position where the margin is the only thing
    # deciding.
    world = quiet_start()
    world.ledger.spend("WEST", world.ledger.balance("WEST"))
    mind = brain(world)
    first, _ = cycle(world, mind, "WEST")
    (_, marching_on) = orders(first)["WEST-1"]

    sighted(world, "WEST", marching_on, men=1)
    noise, _ = cycle(world, mind, "WEST")
    sighted(world, "WEST", marching_on, men=25)
    news, _ = cycle(world, mind, "WEST")

    assert orders(noise) == {}
    assert orders(news)["WEST-1"][1] != marching_on


PLACES = ("agia_marina", "camp_tempest", "girna", "camp_maxwell", "air_station", "lz_baldy")
REPORTS = st.lists(
    st.builds(
        lambda presence, seen: (presence, seen),
        presence=st.dictionaries(
            st.sampled_from(PLACES),
            st.lists(st.sampled_from(("WEST", "EAST")), max_size=2, unique=True),
            max_size=4,
        ),
        seen=st.dictionaries(st.sampled_from(PLACES), st.integers(min_value=0, max_value=30)),
    ),
    min_size=1,
    max_size=8,
)


def drive(
    seed: int, reports: list[tuple[dict[str, list[str]], dict[str, int]]]
) -> tuple[list[Command], list[port.Judgement]]:
    """Play a Campaign out against a sequence of reports, and say what happened.

    The world is a stand-in — Squads arrive wherever they were sent and the
    reports are generated — but the campaign, the port and the planner are the
    real ones, so what is being tested is the planner against the rules that
    will actually judge it.
    """
    world = live()
    mind = brain(world, seed=seed)
    issued: list[Command] = []
    judged: list[port.Judgement] = []
    for step, (presence, seen) in enumerate(reports):
        world.observe((step + 1) * 30.0, presence)
        world.roster.reconcile(
            {squad.id: (8, squad.order.objective) for squad in world.roster.roll("WEST")}
        )
        world.contacts.report(
            "WEST",
            at_time=world.elapsed,
            seen=tuple(
                contacts.Sighting(at=place, kind="Infantry", age=0.0)
                for place, men in seen.items()
                for _ in range(men)
            ),
            observed=tuple(seen),
        )
        plan, judgements = cycle(world, mind, "WEST")
        issued.extend(plan.commands)
        judged.extend(judgements)
    return issued, judged


@given(REPORTS)
def test_no_command_the_planner_issues_is_one_the_port_would_refuse(
    reports: list[tuple[dict[str, list[str]], dict[str, int]]],
) -> None:
    # Judged by the real port rather than by a restatement of its rules here:
    # `already_held`, `insufficient_funds` and `unknown_squad` are all reachable
    # by a scorer that plans against ownership it has misread, and a test that
    # re-implemented the port would agree with the planner about the mistake.
    _, judgements = drive(seed=7, reports=reports)
    refused = [(one.code, one.detail) for one in judgements if not one.accepted]
    assert refused == []


@given(REPORTS)
def test_the_same_seed_and_the_same_reports_produce_the_same_commands(
    reports: list[tuple[dict[str, list[str]], dict[str, int]]],
) -> None:
    # The determinism ADR-0004 asks for, as a property rather than an aspiration.
    assert drive(seed=7, reports=reports)[0] == drive(seed=7, reports=reports)[0]


def sent_from_agia_marina(seed: int) -> tuple[str, str]:
    """Return where a Squad holding Agia Marina is sent next, under `seed`."""
    world = live()
    held(world, "agia_marina", "WEST")
    fielded(world, "WEST", "agia_marina")
    (order,) = orders(brain(world, seed=seed).plan(world.observation("WEST"))).values()
    return order


def test_when_geography_ties_the_seed_is_what_decides() -> None:
    # Determinism is not sameness. The tie is a real one on the authored map:
    # from Agia Marina, LZ Baldy is 1,905 m along the graph and Camp Rogain
    # 1,983 m, and both pay ten — so 78 m is all that separates them and a
    # scorer without a seed would play every Campaign the same way from here.
    # Anywhere the gap is wider, geography decides and the seed cannot reach it,
    # which is why `jitter` is the smallest weight there is.
    assert len({sent_from_agia_marina(seed) for seed in range(6)}) > 1


def test_a_seeded_preference_is_fixed_across_runs_and_not_by_this_process() -> None:
    # The determinism property above runs twice inside one process, where a
    # preference drawn from `hash` would agree with itself and pass. This is the
    # claim it cannot make: the number is a constant of the seed and the name,
    # recorded from the seeded PRNG, and `hash` is salted per process.
    assert planner._stable_fraction(0, "girna") == 0.4430515296569216  # noqa: SLF001


def test_a_planner_cannot_plan_from_a_picture_that_belongs_to_nobody() -> None:
    # The public picture carries no Funds and no Squads (#27), so planning from
    # one would silently be a Commander with nothing and no way to notice.
    world = live()
    with pytest.raises(ValueError, match="public"):
        brain(world).plan(world.observation())


def test_the_nearer_of_two_equal_objectives_is_the_one_a_squad_is_sent_to() -> None:
    # Both are one hop from the WEST Base and both pay ten, so a scorer counting
    # hops sends a Squad 2,065 m when 1,076 m was on offer and lets the seed
    # decide which — measured in-world, `spike/probes/ai-commander.sqf`. The
    # graph is still the graph #16 asks the scorer to reason over; its edges
    # just carry the length the manifest already authored.
    world = quiet_start()
    (base,) = [one for one in world.map_manifest.bases if one.side == "WEST"]
    reach = {
        objective.id: (objective.position[0] - base.position[0]) ** 2
        + (objective.position[1] - base.position[1]) ** 2
        for objective in world.map_manifest.objectives
        if objective.id in base.adjacent
    }

    (order,) = orders(brain(world).plan(world.observation("WEST"))).values()
    assert order == ("capture", min(reach, key=lambda name: reach[name]))
