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
        map_manifest=manifest.load(REPO / "addons" / "main" / "manifests" / "stratis.json"),
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
        command.args["squad"]: (command.args["order"], command.args["place"])
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
# Ground a Contact may be reported on, which since ADR-0020 includes both Bases:
# ownership still moves on Objectives alone, but a Squad seen at a Base is the
# news the two new candidates turn on, and a property run that never generated
# one would leave them exercised by the examples above only.
SIGHTED = (*PLACES, "nato_airbase", "csat_kamino")
REPORTS = st.lists(
    st.builds(
        lambda presence, seen: (presence, seen),
        presence=st.dictionaries(
            st.sampled_from(PLACES),
            st.lists(st.sampled_from(("WEST", "EAST")), max_size=2, unique=True),
            max_size=4,
        ),
        seen=st.dictionaries(st.sampled_from(SIGHTED), st.integers(min_value=0, max_value=30)),
    ),
    min_size=1,
    max_size=8,
)

# The same reports, played from the other end of the Campaign. `REPORTS` moves
# ground on six of the eight Objectives, so a run of it never holds the island
# and therefore never issues an Assault — measured, and it makes the massing
# property below vacuous rather than false. This one hands WEST the whole island
# from the first step and generates only what was *seen*, which is the position
# ADR-0020's arc converges on and the only one where a Base is worth going to.
LATE = st.lists(
    st.dictionaries(st.sampled_from(SIGHTED), st.integers(min_value=0, max_value=30)),
    min_size=4,
    max_size=8,
)


def late(
    sightings: list[dict[str, int]],
) -> list[tuple[dict[str, list[str]], dict[str, int]]]:
    """Turn a run of sightings into reports off a WEST-held island."""
    ours = {objective.id: ["WEST"] for objective in live().map_manifest.objectives}
    return [(dict(ours), seen) for seen in sightings]


def drive(
    seed: int, reports: list[tuple[dict[str, list[str]], dict[str, int]]]
) -> tuple[list[Command], list[port.Judgement], campaign.Campaign]:
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
            {squad.id: (8, squad.order.place) for squad in world.roster.roll("WEST")}
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
    return issued, judged, world


@given(REPORTS)
def test_no_command_the_planner_issues_is_one_the_port_would_refuse(
    reports: list[tuple[dict[str, list[str]], dict[str, int]]],
) -> None:
    # Judged by the real port rather than by a restatement of its rules here:
    # `already_held`, `insufficient_funds` and `unknown_squad` are all reachable
    # by a scorer that plans against ownership it has misread, and a test that
    # re-implemented the port would agree with the planner about the mistake.
    # Since ADR-0020 the port also types which ground each Order kind may name,
    # so a scorer that offered Capture(Base), Assault(Objective) or Defend on
    # the enemy's Base would be refused `wrong_ground` here rather than in-world.
    _, judgements, _ = drive(seed=7, reports=reports)
    refused = [(one.code, one.detail) for one in judgements if not one.accepted]
    assert refused == []


@given(REPORTS)
def test_a_commander_never_spends_funds_it_does_not_have(
    reports: list[tuple[dict[str, list[str]], dict[str, int]]],
) -> None:
    # The port refuses an unaffordable purchase, so overspending would show up
    # above as a refusal — but the balance is the thing that actually has to
    # hold, and it holds through the real Ledger rather than through the port's
    # answer about it.
    _, _, world = drive(seed=7, reports=reports)
    assert world.ledger.balance("WEST") >= 0


@given(REPORTS)
def test_the_same_seed_and_the_same_reports_produce_the_same_commands(
    reports: list[tuple[dict[str, list[str]], dict[str, int]]],
) -> None:
    # The determinism ADR-0004 asks for, as a property rather than an aspiration.
    assert drive(seed=7, reports=reports)[0] == drive(seed=7, reports=reports)[0]


@given(LATE)
def test_no_order_issued_off_a_held_island_is_one_the_port_would_refuse(
    sightings: list[dict[str, int]],
) -> None:
    # The never-rejected property at the end of the Campaign, where the Orders
    # that get issued are Assaults. Several Squads named on one Base is the new
    # shape #38 puts on the wire, and whether the port minds is not a thing to
    # reason about from here: it is asked.
    _, judgements, _ = drive(seed=7, reports=late(sightings))
    assert [(one.code, one.detail) for one in judgements if not one.accepted] == []


@given(LATE)
def test_no_squad_is_ever_left_alone_against_a_base_that_wants_more(
    sightings: list[dict[str, int]],
) -> None:
    # #38 as a property over played-out Campaigns rather than over three staged
    # positions: whatever the reports say, at the end of every cycle the Squads
    # standing under Assault on the enemy Base are either none of them or enough
    # of them. The standing Order is what is read, not the Commands issued, so a
    # Squad that was sent when the Base looked empty and is still marching when
    # a company turns up is covered too — the Order has to be taken back off it.
    _, _, world = drive(seed=7, reports=late(sightings))
    contact = {one.at: one for one in world.contacts.of("WEST", world.elapsed)}
    for base in world.map_manifest.bases:
        if base.side == "WEST":
            continue
        seen = contact.get(base.id)
        wanted = planner.ASSAULT_MASS[seen.echelon] if seen else planner.ASSAULT_MASS["team"]
        sent = [
            squad
            for squad in world.roster.roll("WEST")
            if (squad.order.kind, squad.order.place) == ("assault", base.id)
        ]
        assert not sent or len(sent) >= wanted


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


# Both Bases are candidates from here down (#34, ADR-0020). Everything above
# this line is Domination; everything below is the Campaign having a second way
# to end, which is a scorer change and not a geometry one — the adjacency graph
# already carried both Bases as nodes.


def terms(decision: planner.Decision, choice: str) -> dict[str, float]:
    """Return what one candidate in a decision was made of."""
    (candidate,) = [one for one in decision.candidates if one.choice == choice]
    return candidate.terms


def test_the_opening_move_is_income_bearing_ground_and_not_the_enemy_base() -> None:
    # The arc the placeholder `decapitation` is sized for: a Commander that
    # opened with a raid across the whole island would skip the Campaign, and a
    # Commander that never raided could only win by Domination. Every seed,
    # because `jitter` may reorder ground the graph has tied and must never
    # reach as far as this.
    for seed in range(6):
        world = quiet_start()
        (order,) = orders(brain(world, seed=seed).plan(world.observation("WEST"))).values()
        assert order[0] == "capture"


def island_held(*spare: str) -> campaign.Campaign:
    """Return the late position: WEST holds every Objective and stands on each.

    Plus a Squad at each of `spare`, which is the Commander with nothing left to
    take — the position the whole second half of the Campaign converges on, and
    the one Domination-only play had no answer to.
    """
    world = live()
    places = [objective.id for objective in world.map_manifest.objectives]
    for place in places:
        held(world, place, "WEST")
    fielded(world, "WEST", *places, *spare)
    return world


def test_an_undefended_enemy_base_with_a_squad_to_spare_is_assaulted() -> None:
    # The other end of the arc. The Squad past one-per-Objective has no ground
    # of its own left to take, and what it is for is ending the Campaign.
    # Judged by the real port, because Assault is the newest Order kind and the
    # refusal matrix that types it is the thing a scorer can most easily get
    # wrong — Capture(Base) and Defend(enemy Base) are both one line away.
    world = island_held("nato_airbase")
    (enemy,) = [base for base in world.map_manifest.bases if base.side == "EAST"]

    plan, judgements = cycle(world, brain(world), "WEST")

    assert ("assault", enemy.id) in orders(plan).values()
    assert [one.code for one in judgements if not one.accepted] == []


def test_a_defended_enemy_base_is_worth_less_to_assault_than_an_open_one() -> None:
    # Threat reads on a Base the way it reads on anything else: a company seen
    # at Kamino costs the Assault the same four it would cost a Capture, so a
    # defended Base is reached for after an open one and after anything the
    # Commander can do more cheaply. Priced rather than chosen, because with the
    # island held there is nothing left for the Assault to lose to — a Commander
    # with no ground to take and a garrison to fight through still goes, which
    # is the right answer and not the one that would demonstrate the term.
    def assault_score(men: int) -> float:
        world = island_held("nato_airbase")
        if men:
            sighted(world, "WEST", "csat_kamino", men=men)
        squad = only(brain(world).plan(world.observation("WEST")).decisions, "WEST-8")
        return scores(squad)["assault csat_kamino"]

    # Against the fog floor rather than against zero: an unreported Base is
    # already assumed to hold a team, so what the sighting adds is the seven
    # teams between a team and a company.
    news = planner.ECHELON_THREAT["company"] - planner.UNKNOWN_THREAT
    assert assault_score(0) - assault_score(25) == pytest.approx(planner.Weights().threat * news)


def test_a_company_at_its_own_base_turns_a_squad_round_from_marching_on() -> None:
    # The same relation ADR-0014 fixed for held Objectives, at the one place
    # whose loss ends the Campaign: a Commander told to press marches on past a
    # sighting behind it and turns round for a massed one. A Base pays no
    # income, so what makes this hold is the new term rather than the garrison
    # value of the ground — take the term out and 8.0 of company loses to 8.4
    # of Agia Marina, and the Commander walks away from its own HQ.
    world = live()
    fielded(world, "WEST", "nato_airbase")
    sighted(world, "WEST", "nato_airbase", men=25)

    (order,) = orders(brain(world).plan(world.observation("WEST"))).values()
    assert order == ("defend", "nato_airbase")


def test_a_platoon_at_its_own_base_does_not_stop_the_advance() -> None:
    # And the other side of that relation, which is the half that keeps a
    # Commander playing: a Base is not a reason to sit at home, or the fog floor
    # alone would garrison it from the first cycle and the Campaign would open
    # with nobody going anywhere.
    world = live()
    fielded(world, "WEST", "nato_airbase")
    sighted(world, "WEST", "nato_airbase", men=10)

    (order,) = orders(brain(world).plan(world.observation("WEST"))).values()
    assert order[0] == "capture"


def test_a_base_nobody_is_standing_on_is_not_scored_as_safe_ground() -> None:
    # `UNKNOWN_THREAT` applies to the Base as to any held ground (ADR-0020):
    # nobody watching it means possibly-threatened, never empty. Every Squad is
    # forward on an Objective and each is looking at the ground under it, so the
    # Base behind them all is unknown and scores a team standing on it — the
    # same fog rule that bought ADR-0014's WEST-4, at the place that would end
    # the Campaign.
    world = island_held()

    decision = only(brain(world).plan(world.observation("WEST")).decisions, "WEST-1")
    assert terms(decision, "defend nato_airbase")["threat"] == pytest.approx(
        planner.Weights().defend * planner.UNKNOWN_THREAT
    )


def test_the_trace_carries_both_bases_and_says_what_a_base_was_worth() -> None:
    # #16's bargain: every candidate the scorer weighed is counted and the top
    # few are carried with the terms that made them, so an argument about a
    # Base is an argument about numbers. `scored` counts the Places on the map
    # — both Bases included — rather than the Objectives, because a silent
    # omission there reads as "the Base was never considered".
    world = island_held()
    decision = only(brain(world).plan(world.observation("WEST")).decisions, "WEST-1")

    assert decision.scored == len(world.map_manifest.objectives) + len(world.map_manifest.bases)
    assert terms(decision, "assault csat_kamino")["decapitation"] == pytest.approx(
        planner.Weights().decapitation
    )
    assert terms(decision, "defend nato_airbase")["decapitation"] == pytest.approx(
        planner.Weights().garrison * planner.Weights().decapitation
    )


def test_adr_0014s_weight_set_is_the_one_this_ticket_found() -> None:
    # ADR-0020 said the eight weights and ADR-0014's four calls do not move to
    # make room for Bases, and this is that promise as a test rather than as a
    # sentence in a commit message: the new term is an addition, and if one term
    # cannot carry both ends of the Campaign the escalation is the threat-model
    # ticket, not a retune. #38 is that escalation, and it went the way the
    # sentence said it would — a threat model beside the scorer, so the whole
    # set including `decapitation` is asserted here field by field and none of
    # it moved.
    assert planner.Weights() == planner.Weights(
        income=1.0,
        garrison=0.1,
        contested=6.0,
        threat=0.5,
        defend=1.0,
        travel=1.0,
        commitment=2.0,
        jitter=0.3,
        decapitation=8.0,
        stale_seconds=300.0,
    )


# The threat model is from here down (#38, ADR-0027): not what a Base is worth,
# which is above, but how much force one needs. It is an assignment rule rather
# than a term, so what these read is who was sent rather than what anything
# scored.

SEEDS = 200


def raiders(world: campaign.Campaign, seed: int = 0) -> list[str]:
    """Return the Squads told to Assault Kamino, under `seed`."""
    plan = brain(world, seed=seed).plan(world.observation("WEST"))
    return [squad for squad, order in orders(plan).items() if order == ("assault", "csat_kamino")]


def island_held_by(*places: str) -> campaign.Campaign:
    """Return a WEST-held island garrisoned only at `places`.

    `_advance` keeps ground once taken, so an island can be held by a force too
    small to stand on all of it — which is what a Commander that has been ground
    down looks like, and the position where declining is the live answer.
    """
    world = live()
    for objective in world.map_manifest.objectives:
        held(world, objective.id, "WEST")
    fielded(world, "WEST", *places)
    return world


def assault_row(world: campaign.Campaign, seed: int = 0) -> planner.Decision:
    """Return what the Commander decided about the Assault itself."""
    return only(
        brain(world, seed=seed).plan(world.observation("WEST")).decisions, "assault csat_kamino"
    )


def test_an_undefended_enemy_base_is_still_raided_by_one_squad_on_every_seed() -> None:
    # The half of #38 that is a promise not to change anything: an unreported
    # Base is the fog floor, the fog floor is a team, and a team is one Squad's
    # worth — so #34's late position plans exactly as #34 measured it. Swept
    # rather than sampled because the mass is new machinery and a seed that
    # quietly detailed a second Squad would be a regression nobody saw.
    for seed in range(SEEDS):
        assert len(raiders(island_held("nato_airbase"), seed)) == 1


def test_a_company_at_the_enemy_base_is_massed_against_on_every_seed() -> None:
    # The other half, and the ticket: #35's Assault arrived as eight men against
    # three Squads and lost five of them in twenty-five seconds. The Contact
    # says company, doctrine says four Squads, and four is what goes — every
    # seed, out of a force of eight with an island to garrison.
    for seed in range(SEEDS):
        world = island_held()
        sighted(world, "WEST", "csat_kamino", men=25)
        assert len(raiders(world, seed)) == planner.ASSAULT_MASS["company"]


def test_a_commander_that_cannot_mass_declines_the_assault_on_every_seed() -> None:
    # All-or-nothing, which is the point: three Squads is not a company's worth
    # under any doctrine, so what a Commander with three does about a defended
    # Base is nothing. The island is still held — declining costs the Campaign
    # nothing, and going would cost it three Squads.
    for seed in range(SEEDS):
        world = island_held_by("camp_rogain", "lz_baldy", "air_station")
        sighted(world, "WEST", "csat_kamino", men=25)
        assert raiders(world, seed) == []


def test_the_force_an_assault_brings_is_read_off_the_band_and_off_nothing_else() -> None:
    # A Contact carries no count and #28 made sure none can be recovered, so the
    # threat model is a table from a band to a number of our own Squads. Nine
    # men and twenty-four men are one band and get one answer, which is the
    # guarantee holding rather than a coincidence: a rule that divided men by
    # eight would send three Squads at one and would have had to invent the
    # count to do it.
    for men, band in ((1, "team"), (4, "squad"), (9, "platoon"), (24, "platoon"), (25, "company")):
        world = island_held()
        sighted(world, "WEST", "csat_kamino", men=men)
        assert len(raiders(world)) == planner.ASSAULT_MASS[band]


def test_every_band_the_register_can_report_has_a_mass_to_go_with_it() -> None:
    # The two tables are written apart and have to stay in step. `_demanded`
    # falls back to the heaviest mass for a band it does not know, so a drift
    # here would not crash — it would quietly send four Squads at a team, which
    # is the kind of bug that reads as a balance complaint.
    assert set(planner.ASSAULT_MASS) == {band for _, band in contacts.ECHELONS}


def test_age_discounts_what_a_base_costs_and_never_what_taking_it_needs() -> None:
    # #28's honesty signal, read the one way round that is safe. A ten-minute-old
    # company may well have marched off, so it stops *deterring* the Assault —
    # the price falls back to the fog floor, exactly as it does for any stale
    # Contact. It does not stop the Assault *bringing* four Squads, because the
    # two mistakes are not the same size: four Squads at an empty Base is a
    # wasted march, and one Squad at a company that never left is #35 again.
    # Only somebody looking lowers this, and looking clears the Contact outright.
    world = island_held()
    sighted(world, "WEST", "csat_kamino", men=25, age=600.0)

    decision = only(brain(world).plan(world.observation("WEST")).decisions, "WEST-1")
    assert terms(decision, "assault csat_kamino")["threat"] == pytest.approx(
        -planner.Weights().threat * planner.UNKNOWN_THREAT
    )
    assert len(raiders(world)) == planner.ASSAULT_MASS["company"]


def test_a_declined_assault_says_so_rather_than_going_quiet() -> None:
    # "Nobody was sent to Kamino" is otherwise a silence, and three different
    # things wear it: massed, called off, and never worth it. A Commander that
    # declined on purpose has to be distinguishable in the trace from one that
    # never considered the Base, or the only evidence for a threat model is that
    # nothing happened.
    world = island_held_by("camp_rogain", "lz_baldy", "air_station")
    sighted(world, "WEST", "csat_kamino", men=25)

    row = assault_row(world)
    assert row.chose == "declined"
    assert row.because == "company reported; 4 wanted, 3 could be spared"


def test_a_squad_kept_off_a_declined_assault_is_told_that_is_why() -> None:
    # The Squad that wanted to go is the one the trace has to explain itself to.
    # Without this it reads as having lost the Base to another Squad, which is
    # the one thing that did not happen.
    world = island_held_by("camp_rogain", "lz_baldy", "air_station")
    sighted(world, "WEST", "csat_kamino", men=25)

    decision = only(brain(world).plan(world.observation("WEST")).decisions, "WEST-1")
    assert decision.chose != "assault csat_kamino"
    assert "called off for want of mass" in decision.because


def test_an_assault_nothing_outbid_is_not_the_same_as_one_called_off() -> None:
    # The opening position: the Base is worth less than the ground still worth
    # taking, so no Squad asked to go and there was nothing to call off. #34's
    # arc, which the threat model must not turn into a refusal.
    world = quiet_start()

    assert assault_row(world).chose == "not sought"
