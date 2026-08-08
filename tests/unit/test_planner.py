"""The AI Commander's scorer (#16).

A pure function of one Observation and the authored data behind it, so every
test here runs without Arma. What it plans against is the same fogged picture a
human Commander gets (ADR-0012) — banded, aged Contacts and no enemy roster —
so a test that reached for ground truth would be testing a planner nobody is
going to ship.
"""

from __future__ import annotations

import itertools

import pytest
from conftest import authored_economy, live
from hypothesis import given
from hypothesis import strategies as st

from cti_daemon import budget, campaign, contacts, economy, manifest, planner, port
from cti_daemon.commands import Command
from cti_daemon.outbox import Outbox
from cti_daemon.squads import Held


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
        {
            squad.id: Held(8, place)
            for squad, place in zip(world.roster.roll(side), places, strict=True)
        }
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
    # A company, because that is the echelon the curves are tuned to stop for:
    # a Commander told to press (`Considerations`) marches on past a squad-sized
    # sighting behind it and turns round only for a real massed incursion. The
    # `hold` curve is what carries that since ADR-0031 — squared, so its
    # crossing point sits between a platoon and a company.
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
            {squad.id: Held(8, squad.order.place) for squad in world.roster.roll("WEST")}
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
    contact = {one.at: one for one in world.contacts.aged_to("WEST", world.elapsed)}
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


def assault_score_and_terms(men: int) -> tuple[float, dict[str, float]]:
    """Return the Assault's score and terms with `men` reported at the enemy Base."""
    world = island_held("nato_airbase")
    if men:
        sighted(world, "WEST", "csat_kamino", men=men)
    squad = only(brain(world).plan(world.observation("WEST")).decisions, "WEST-8")
    return scores(squad)["assault csat_kamino"], terms(squad, "assault csat_kamino")


def test_a_defended_enemy_base_is_worth_less_to_assault_than_an_open_one() -> None:
    # Threat reads on a Base the way it reads on anything else: a company seen
    # at Kamino costs the Assault the same four it would cost a Capture, so a
    # defended Base is reached for after an open one and after anything the
    # Commander can do more cheaply. Priced rather than chosen, because with the
    # island held there is nothing left for the Assault to lose to — a Commander
    # with no ground to take and a garrison to fight through still goes, which
    # is the right answer and not the one that would demonstrate the term.
    open_score, _ = assault_score_and_terms(0)
    held_score, _ = assault_score_and_terms(25)

    assert held_score < open_score


def test_a_contact_at_the_enemy_base_changes_only_the_assaults_danger() -> None:
    _, open_terms = assault_score_and_terms(0)
    _, held_terms = assault_score_and_terms(25)

    # Against the fog floor rather than against zero: an unreported Base is
    # already assumed to hold a team, so what the sighting costs is the distance
    # along the `danger` curve between a team and a company. Since ADR-0031 that
    # is the *whole* of what the Contact does to the option — every other
    # consideration is untouched, which is a stronger claim than the summed
    # scorer's and the one a product lets us make.
    assert {name: value for name, value in held_terms.items() if name != "danger"} == pytest.approx(
        {name: value for name, value in open_terms.items() if name != "danger"}
    )


def test_a_company_at_the_enemy_base_sets_the_assaults_danger() -> None:
    _, held_terms = assault_score_and_terms(25)
    mind = brain(live())

    assert held_terms["danger"] == pytest.approx(
        mind._danger(planner.ECHELON_THREAT["company"])  # noqa: SLF001 — the curve is the claim
    )


def test_an_unreported_enemy_base_uses_the_fog_floor_for_the_assaults_danger() -> None:
    _, open_terms = assault_score_and_terms(0)
    mind = brain(live())

    assert open_terms["danger"] == pytest.approx(mind._danger(planner.UNKNOWN_THREAT))  # noqa: SLF001


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
    assert terms(decision, "defend nato_airbase")["hold"] == pytest.approx(
        brain(world)._hold(planner.UNKNOWN_THREAT)  # noqa: SLF001 — the curve is the claim
    )
    # And that the floor is genuinely above the curve's own floor: unknown is
    # not empty, so an unwatched Base is worth more to stand on than one being
    # looked at and reporting nobody.
    assert brain(world)._hold(planner.UNKNOWN_THREAT) > brain(world)._hold(0.0)  # noqa: SLF001


def traced_base_decision() -> tuple[campaign.Campaign, planner.Decision]:
    """Return the late-Campaign position and one Squad's trace over both Bases."""
    world = island_held()
    decision = only(brain(world).plan(world.observation("WEST")).decisions, "WEST-1")
    return world, decision


def test_the_trace_counts_the_legal_options_at_both_bases() -> None:
    # #16's bargain: every candidate the scorer weighed is counted and the top
    # few are carried with the terms that made them, so an argument about a
    # Base is an argument about numbers. `scored` counts the Places on the map
    # — both Bases included — rather than the Objectives, because a silent
    # omission there reads as "the Base was never considered".
    world, decision = traced_base_decision()

    assert decision.scored == len(world.map_manifest.objectives) + len(world.map_manifest.bases)


def test_the_trace_counts_the_vetoed_options_at_both_bases() -> None:
    _, decision = traced_base_decision()

    # And the half of the space that never got that far: one kind per Place is
    # the one the port would refuse, so exactly as many options are vetoed as
    # are scored (ADR-0031).
    assert decision.vetoed == decision.scored


def base_worth(choice: str) -> tuple[float, float]:
    """Return a traced Base option's worth and the authored value it should carry."""
    world, decision = traced_base_decision()
    shape = planner.Considerations()
    ceiling = max(
        [objective.income for objective in world.map_manifest.objectives]
        + [shape.decapitation, shape.homeland]
    )
    authored = {
        "assault csat_kamino": shape.decapitation,
        "defend nato_airbase": shape.homeland,
    }
    return terms(decision, choice)["worth"], authored[choice] / ceiling


def test_the_trace_says_what_assaulting_the_enemy_base_was_worth() -> None:
    traced, expected = base_worth("assault csat_kamino")

    assert traced == pytest.approx(expected)


def test_the_trace_says_what_defending_the_home_base_was_worth() -> None:
    traced, expected = base_worth("defend nato_airbase")

    assert traced == pytest.approx(expected)


def vetoed_options() -> list[tuple[str, dict[str, float]]]:
    """Return each option the port refuses, with the terms the trace carries."""
    world = island_held()
    mind = brain(world)
    squad = world.observation("WEST").squads[0]
    return [
        (option.choice, option.terms)
        for option in mind._options(world.observation("WEST"), squad)  # noqa: SLF001
        if option.score <= 0.0
    ]


def test_the_trace_names_every_vetoed_option() -> None:
    # The mandatory class doing its job (ADR-0031). An option the port would
    # refuse is not scored badly, it is scored zero and abandoned before any
    # other consideration is computed — so the trace carries `legal: 0.0` and
    # nothing else, which is a sentence rather than an arithmetic accident.
    assert {choice for choice, _ in vetoed_options()} == {
        "capture agia_marina",
        "capture camp_tempest",
        "capture girna",
        "capture camp_maxwell",
        "capture air_station",
        "capture lz_baldy",
        "capture camp_rogain",
        "capture old_outpost",
        "defend csat_kamino",
        "assault nato_airbase",
    }


def test_a_vetoed_option_carries_only_its_failed_legality_term() -> None:
    assert all(option_terms == {"legal": 0.0} for _, option_terms in vetoed_options())


def test_a_seed_can_break_ties_only_within_three_hundred_metres() -> None:
    shape = planner.Considerations()

    # ADR-0031 keeps ADR-0014's `jitter < travel` call: the seed may only break ties geography has
    # left within three hundred metres. `flavour` is the whole span of the
    # preference and `reach_km` is what a kilometre costs, so their product is
    # the seed's reach in kilometres of march — and it is 0.3, exactly what
    # ADR-0014 measured `jitter = 0.3` against `travel = 1.0` to be.
    assert shape.flavour * shape.reach_km == pytest.approx(0.3)


def test_holding_quiet_ground_is_worth_one_tenth_of_taking_it() -> None:
    shape = planner.Considerations()

    assert 0.0 < shape.hold_floor < 1.0
    assert shape.hold_floor == pytest.approx(0.1)


def test_the_anti_thrash_margin_covers_everything_the_seed_can_move() -> None:
    shape = planner.Considerations()

    assert shape.momentum > shape.flavour


def test_threat_makes_ground_expensive_but_never_impossible() -> None:
    shape = planner.Considerations()

    assert 0.0 < shape.danger_bite < 1.0


def test_the_compensation_factor_cannot_change_which_option_wins() -> None:
    # Lewis's compensation-factor problem, answered on the algebra rather than
    # on an attribution #48 could not trace to a primary. The formula is applied
    # for legibility — eight considerations put a good option at 0.3 — and the
    # claim that buys is that it is strictly increasing on [0, 1] for a fixed
    # consideration count, so it can move the numbers and never the rank order.
    # Every option carries every consideration, at 1.0 where inapplicable, which
    # is what makes the count fixed and this proof apply to all of them.
    rungs = [step / 500 for step in range(501)]
    lifted = [planner._compensated(rung) for rung in rungs]  # noqa: SLF001 — the claim is the map
    assert lifted == sorted(lifted)
    assert all(one < other for one, other in itertools.pairwise(lifted))
    assert lifted[0] == 0.0
    assert lifted[-1] == pytest.approx(1.0)
    assert all(rung <= raised <= 1.0 for rung, raised in zip(rungs, lifted, strict=True))


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


@pytest.fixture(scope="module")
def undefended_enemy_base() -> campaign.Campaign:
    """Return a held island with one Squad free to Assault the open enemy Base."""
    return island_held("nato_airbase")


@pytest.fixture(scope="module")
def company_at_enemy_base() -> campaign.Campaign:
    """Return a held island with a fresh company Contact at the enemy Base."""
    world = island_held()
    sighted(world, "WEST", "csat_kamino", men=25)
    return world


@pytest.fixture(scope="module")
def force_that_cannot_mass() -> campaign.Campaign:
    """Return a held island with only three Squads facing a company at the enemy Base."""
    world = island_held_by("camp_rogain", "lz_baldy", "air_station")
    sighted(world, "WEST", "csat_kamino", men=25)
    return world


@pytest.mark.parametrize("seed", range(SEEDS))
def test_an_undefended_enemy_base_is_still_raided_by_one_squad_on_every_seed(
    seed: int,
    undefended_enemy_base: campaign.Campaign,
) -> None:
    # The half of #38 that is a promise not to change anything: an unreported
    # Base is the fog floor, the fog floor is a team, and a team is one Squad's
    # worth — so #34's late position plans exactly as #34 measured it. Swept
    # rather than sampled because the mass is new machinery and a seed that
    # quietly detailed a second Squad would be a regression nobody saw.
    assert len(raiders(undefended_enemy_base, seed)) == 1


@pytest.mark.parametrize("seed", range(SEEDS))
def test_a_company_at_the_enemy_base_is_massed_against_on_every_seed(
    seed: int,
    company_at_enemy_base: campaign.Campaign,
) -> None:
    # The other half, and the ticket: #35's Assault arrived as eight men against
    # three Squads and lost five of them in twenty-five seconds. The Contact
    # says company, doctrine says four Squads, and four is what goes — every
    # seed, out of a force of eight with an island to garrison.
    assert len(raiders(company_at_enemy_base, seed)) == planner.ASSAULT_MASS["company"]


@pytest.mark.parametrize("seed", range(SEEDS))
def test_a_commander_that_cannot_mass_declines_the_assault_on_every_seed(
    seed: int,
    force_that_cannot_mass: campaign.Campaign,
) -> None:
    # All-or-nothing, which is the point: three Squads is not a company's worth
    # under any doctrine, so what a Commander with three does about a defended
    # Base is nothing. The island is still held — declining costs the Campaign
    # nothing, and going would cost it three Squads.
    assert raiders(force_that_cannot_mass, seed) == []


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


def stale_company_at_the_enemy_base() -> campaign.Campaign:
    """Return a held island with a ten-minute-old company Contact at the enemy Base."""
    world = island_held()
    sighted(world, "WEST", "csat_kamino", men=25, age=600.0)
    return world


def test_age_discounts_what_an_enemy_base_costs_to_the_fog_floor() -> None:
    # #28's honesty signal, read the one way round that is safe. A ten-minute-old
    # company may well have marched off, so it stops *deterring* the Assault —
    # the price falls back to the fog floor, exactly as it does for any stale
    # Contact. It does not stop the Assault *bringing* four Squads, because the
    # two mistakes are not the same size: four Squads at an empty Base is a
    # wasted march, and one Squad at a company that never left is #35 again.
    # Only somebody looking lowers this, and looking clears the Contact outright.
    world = stale_company_at_the_enemy_base()

    decision = only(brain(world).plan(world.observation("WEST")).decisions, "WEST-1")
    assert terms(decision, "assault csat_kamino")["danger"] == pytest.approx(
        brain(world)._danger(planner.UNKNOWN_THREAT)  # noqa: SLF001 — the curve is the claim
    )


def test_age_never_discounts_the_force_taking_an_enemy_base_needs() -> None:
    world = stale_company_at_the_enemy_base()

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


# The commitment hysteresis is from here down (#181; human ruling on #177,
# 2026-08-04: a committed assault holds). The demand above is re-derived from
# the picture every cycle, and in-world the picture flickers — the red run's
# Decision rows went "squad reported; 2 wanted" to "nothing reported; 1 wanted"
# in one cycle, with a leader standing on the Base, and the demand shed a Squad
# whose own top-scored option was still the assault. These are the offline
# proof in the #104 pattern: the real planner and the real port over the staged
# board, across seeds. Pre-fix both disturbances re-task a committed Squad on
# 30 of 30 seeds; the fix is the `_Demand` floor, not anything in these tests.


def massed_on_kamino(seed: int) -> tuple[campaign.Campaign, planner.UtilityPlanner, list[str]]:
    """Return the probe's position: a mass of two ordered onto Kamino, arrived.

    A WEST-held island, a squad-banded Contact on the enemy Base, the mass
    ordered through the real port, and every Squad standing where it was sent —
    which puts the crew on the Base itself, looking at the ground the Contact
    is about to vanish from, exactly as the red run had it.
    """
    world = island_held()
    sighted(world, "WEST", "csat_kamino", men=4)
    mind = brain(world, seed=seed)
    cycle(world, mind, "WEST")
    committed = [
        squad.id
        for squad in world.roster.roll("WEST")
        if (squad.order.kind, squad.order.place) == ("assault", "csat_kamino")
    ]
    world.roster.reconcile(
        {squad.id: Held(8, squad.order.place) for squad in world.roster.roll("WEST")}
    )
    return world, mind, committed


def unpicked(plan: planner.Plan, committed: list[str]) -> dict[str, tuple[str, str]]:
    """Return every Order this plan takes off a committed Squad."""
    return {
        squad: order
        for squad, order in orders(plan).items()
        if squad in committed and order != ("assault", "csat_kamino")
    }


def test_a_committed_assault_survives_its_contact_flickering_out_on_every_seed() -> None:
    # #181's red run exactly: "observed empty" is the engine's knowledge model,
    # and a leader standing on the Base lost sight of a garrison 25 m away for
    # one sample, so #28's removal rule cleared the Contact and the demand fell
    # to the fog floor's one Squad. The commitment floor is what holds: the
    # picture may raise what an Assault brings, never shed what it sent.
    for seed in range(30):
        world, mind, committed = massed_on_kamino(seed)
        assert len(committed) == planner.ASSAULT_MASS["squad"]

        world.contacts.report("WEST", at_time=world.elapsed, seen=(), observed=("csat_kamino",))
        plan, judgements = cycle(world, mind, "WEST")

        assert unpicked(plan, committed) == {}
        assert [one.code for one in judgements if not one.accepted] == []


def test_a_committed_assault_survives_its_contact_rebanding_down_on_every_seed() -> None:
    # The gentler flicker: the Contact does not vanish, the band drops a rung —
    # one man still in sight bands team, and a team wants one Squad. Same
    # doctrine, same floor: an estimate shrinking is not a commitment shrinking.
    for seed in range(30):
        world, mind, committed = massed_on_kamino(seed)
        assert len(committed) == planner.ASSAULT_MASS["squad"]

        sighted(world, "WEST", "csat_kamino", men=1)
        plan, _ = cycle(world, mind, "WEST")

        assert unpicked(plan, committed) == {}


def test_a_mass_held_by_commitment_says_so_in_the_trace() -> None:
    # The trace has to carry the hysteresis or it lies about the arithmetic: a
    # row reading "1 wanted" over a mass of two is an argument no reader could
    # follow. The banded demand and the commitment are both said, so the row
    # names the thing that actually held the number up.
    world, mind, committed = massed_on_kamino(seed=0)
    world.contacts.report("WEST", at_time=world.elapsed, seen=(), observed=("csat_kamino",))

    plan, _ = cycle(world, mind, "WEST")

    row = only(plan.decisions, "assault csat_kamino")
    assert row.chose == f"massed {len(committed)}"
    assert row.because == "nothing reported; 1 wanted, 2 committed"


def test_a_committed_assault_the_force_can_no_longer_mass_for_is_released() -> None:
    # The release condition, named: hysteresis is not a deadlock, and a
    # committed assault that is genuinely lost still retreats. The garrison
    # rebands to company, doctrine wants four, three Squads is all there is —
    # so all-or-nothing declines exactly as it always did, the commitment floor
    # notwithstanding, and both committed Squads are taken off the Base rather
    # than left to press a fight the Commander has already called off.
    world = island_held_by("camp_rogain", "lz_baldy", "air_station")
    # Broke, before this line existed, for the reason the standing-order test
    # names: `fielded` leaves the purse full, the Commander buys a fourth Squad
    # a cycle, and the company masses instead of declining. Three Squads and an
    # empty purse is the position where the force genuinely cannot answer.
    world.ledger.spend("WEST", world.ledger.balance("WEST"))
    sighted(world, "WEST", "csat_kamino", men=4)
    mind = brain(world)
    cycle(world, mind, "WEST")
    committed = [
        squad.id
        for squad in world.roster.roll("WEST")
        if (squad.order.kind, squad.order.place) == ("assault", "csat_kamino")
    ]
    assert len(committed) == planner.ASSAULT_MASS["squad"]
    world.roster.reconcile(
        {squad.id: Held(8, squad.order.place) for squad in world.roster.roll("WEST")}
    )

    sighted(world, "WEST", "csat_kamino", men=25)
    plan, _ = cycle(world, mind, "WEST")

    assert only(plan.decisions, "assault csat_kamino").chose == "declined"
    released = {squad for squad, order in orders(plan).items() if squad in committed}
    assert released == set(committed)
    assert all(order != ("assault", "csat_kamino") for order in orders(plan).values())


# The Reinforce consideration is from here down (#150, human ruling 2026-08-04;
# #191). The AI Commander Reinforces: an understrength Squad standing at Base
# is refilled when a fresh Squad is off the table — the wire's force limit, the
# map's cap, or a purse no fresh Squad fits — or when the discounted pro-rata
# refill beats the fresh Squad the planner would otherwise buy. These are the
# offline proof in the #104 pattern: the real planner and the real port over
# staged boards, across seeds 0-29.


def reinforces(plan: planner.Plan) -> list[str]:
    """Return the Squads this plan refills."""
    return [command.args["squad"] for command in plan.commands if command.name == "reinforce"]


def purchases(plan: planner.Plan) -> list[str]:
    """Return the Squad types this plan buys."""
    return [command.args["squad_type"] for command in plan.commands if command.name == "purchase"]


def bought(world: campaign.Campaign, side: str, squad_type: str = "rifle") -> str:
    """Buy one Squad through the port and return its id."""
    judged = port.CommandPort(campaign=world).submit(
        Command("purchase", side, {"squad_type": squad_type}), acting_side=side
    )
    assert judged.accepted, judged.detail
    return judged.result["squad"]


def test_a_refill_that_undercuts_a_fresh_squad_is_bought_instead_on_every_seed() -> None:
    # Trigger (b) of the #150 ruling: a rifle Squad missing three refills at 30
    # against a fresh rifle at 100, so the refill is the cheaper way to add men
    # and wins the cycle's one spend. Judged by the real port, and the roster
    # read back refilled — the Campaign applied it, not merely planned it.
    for seed in range(30):
        world = live()
        squad = bought(world, "WEST")
        world.roster.reconcile({squad: Held(5, "nato_airbase")})

        plan, judgements = cycle(world, brain(world, seed=seed), "WEST")

        assert reinforces(plan) == [squad]
        assert purchases(plan) == []
        assert [one.code for one in judgements if not one.accepted] == []
        (refilled,) = [one for one in world.roster.roll("WEST") if one.id == squad]
        assert refilled.size == 8


def test_a_refill_dearer_than_a_fresh_squad_loses_to_the_purchase_on_every_seed() -> None:
    # The comparison is live with the authored prices, not a hypothetical: a
    # weapons Squad missing seven refills at 105, a fresh rifle costs 100, so
    # the fresh Squad is the cheaper way to add men and the refill waits.
    for seed in range(30):
        world = live()
        squad = bought(world, "WEST", "weapons")
        world.roster.reconcile({squad: Held(1, "nato_airbase")})

        plan, judgements = cycle(world, brain(world, seed=seed), "WEST")

        assert reinforces(plan) == []
        assert purchases(plan) == ["rifle"]
        assert [one.code for one in judgements if not one.accepted] == []


def capped_with_a_thinned_squad(men: int) -> tuple[campaign.Campaign, str]:
    """Return a map-capped WEST force whose first Squad stands `men` strong at Base."""
    world = live()
    places = [objective.id for objective in world.map_manifest.objectives]
    fielded(world, "WEST", *places)
    thinned = world.roster.roll("WEST")[0].id
    picture = {squad.id: Held(squad.size, squad.at) for squad in world.roster.roll("WEST")}
    picture[thinned] = Held(men, "nato_airbase")
    world.roster.reconcile(picture)
    return world, thinned


def test_at_the_maps_cap_an_understrength_squad_at_base_is_still_refilled_on_every_seed() -> None:
    # Trigger (a) in the planner's own economy: at one Squad per Objective the
    # scorer stops buying, and before #150 the funds row read "nothing" while a
    # five-man Squad stood at Base with a full purse. A refill adds men without
    # adding a Squad, so neither ceiling bars it.
    for seed in range(30):
        world, thinned = capped_with_a_thinned_squad(5)

        plan, judgements = cycle(world, brain(world, seed=seed), "WEST")

        assert reinforces(plan) == [thinned]
        assert purchases(plan) == []
        assert [one.code for one in judgements if not one.accepted] == []


def long_frontier() -> campaign.Campaign:
    """Return a Campaign on a map long enough that the wire binds before the map.

    Stratis cannot stage the #150 ruling's force-limit trigger: its wire
    carries 71 Squads and its map caps the scorer at eight, so `force_limit`
    sits far behind a ceiling the planner reaches first. Contacts are keyed by
    place and grow with the map (#26), so a fifty-Objective chain pulls
    `budget.squad_ceiling` down to 17 — under the fifty the map would
    otherwise invite — and the wire becomes the ceiling that binds.
    """
    count = 50
    objectives = []
    for index in range(count):
        adjacent = []
        if index > 0:
            adjacent.append(f"town_{index - 1:02d}")
        if index < count - 1:
            adjacent.append(f"town_{index + 1:02d}")
        objectives.append(
            {
                "id": f"town_{index:02d}",
                "display_name": f"Town {index}",
                "position": [1_000.0 + index * 500, 5_000.0],
                "capture_radius": 100,
                "income": 10,
                "adjacent": adjacent,
            }
        )
    table = authored_economy()
    return campaign.Campaign(
        map_manifest=manifest.parse(
            {
                "schema_version": 1,
                "id": "frontier",
                "world": "Frontier",
                "display_name": "Frontier",
                "bases": [
                    {
                        "id": "west_base",
                        "side": "WEST",
                        "display_name": "West Base",
                        "position": [500.0, 5_000.0],
                        "hq": "hq_west",
                        "adjacent": ["town_00"],
                    },
                    {
                        "id": "east_base",
                        "side": "EAST",
                        "display_name": "East Base",
                        "position": [1_000.0 + count * 500, 5_000.0],
                        "hq": "hq_east",
                        "adjacent": [f"town_{count - 1:02d}"],
                    },
                ],
                "objectives": objectives,
            }
        ),
        table=table,
        ledger=economy.Ledger(table.starting_funds),
        outbox=Outbox(),
    )


def test_at_the_force_limit_the_refill_is_the_only_way_men_are_added_on_every_seed() -> None:
    # Trigger (a) as ruled: at `force_limit` a Purchase is refused, and the
    # planner reads the same measurement the port refuses by
    # (`budget.squad_ceiling` over the same manifest and table), so it
    # Reinforces instead of issuing a Command whose refusal it cannot read.
    # The staging is proven through the port before anything is planned: the
    # Purchase past the ceiling really is refused `force_limit`.
    world = long_frontier()
    limit = budget.squad_ceiling(world.map_manifest, world.table)
    assert limit is not None
    assert limit < len(world.map_manifest.objectives)

    world.ledger.deposit("WEST", 100 * limit + 1_000)
    open_port = port.CommandPort(campaign=world)
    for _ in range(limit):
        judged = open_port.submit(
            Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
        )
        assert judged.accepted, judged.detail
    refused = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert refused.code == "force_limit"

    thinned = world.roster.roll("WEST")[0].id
    picture = {squad.id: Held(8, "") for squad in world.roster.roll("WEST")}
    picture[thinned] = Held(5, "west_base")
    world.roster.reconcile(picture)

    for seed in range(30):
        plan = brain(world, seed=seed).plan(world.observation("WEST"))
        assert reinforces(plan) == [thinned]
        assert purchases(plan) == []
        row = only(plan.decisions, "funds")
        assert row.because == (
            f"3 men short at Base; {limit} Squads fielded of {limit} the wire carries"
        )

    # And the whole plan through the real port once, because the sweep above is
    # pure: every Command the force-limited Commander issues is one the port
    # takes, the Reinforce included.
    _, judgements = cycle(world, brain(world), "WEST")
    assert [one.code for one in judgements if not one.accepted] == []
    (refilled,) = [one for one in world.roster.roll("WEST") if one.id == thinned]
    assert refilled.size == 8


def test_a_refill_the_purse_cannot_pay_for_is_not_asked_for() -> None:
    # The port would refuse it `insufficient_funds`, and the planner does not
    # issue Commands it can see refused. Five Funds refill nobody, and the row
    # says which silence this is rather than going quiet.
    world = live()
    squad = bought(world, "WEST")
    world.roster.reconcile({squad: Held(5, "nato_airbase")})
    world.ledger.spend("WEST", world.ledger.balance("WEST") - 5)

    plan, judgements = cycle(world, brain(world), "WEST")

    assert reinforces(plan) == []
    assert purchases(plan) == []
    assert [one.code for one in judgements if not one.accepted] == []
    row = only(plan.decisions, "funds")
    assert row.chose == "nothing"
    assert row.because == "5 Funds purchase no Squad this map sells and refill none"


def test_a_squad_short_of_men_in_the_field_is_not_reinforced() -> None:
    # Reinforce refills a Squad at its own Base (CONTEXT.md, ADR-0040), and the
    # port would refuse `wrong_ground` anywhere else. A five-man Squad standing
    # on an Objective is the deploy scorer's problem, not the purse's.
    world = live()
    squad = bought(world, "WEST")
    world.roster.reconcile({squad: Held(5, "agia_marina")})

    plan, judgements = cycle(world, brain(world), "WEST")

    assert reinforces(plan) == []
    assert [one.code for one in judgements if not one.accepted] == []


def test_a_refill_that_wins_traces_what_it_beat() -> None:
    # The funds row carries both ways to add men on the one price axis, winner
    # first as every Decision row promises, with the refill's `missing` beside
    # its price — a refill's cost means nothing without it.
    world = live()
    squad = bought(world, "WEST")
    world.roster.reconcile({squad: Held(5, "nato_airbase")})

    row = only(brain(world).plan(world.observation("WEST")).decisions, "funds")

    assert row.chose == f"reinforce {squad}"
    assert row.because == "3 men short at Base; 30 beats rifle at 100"
    assert row.candidates[0].choice == f"reinforce {squad}"
    assert terms(row, f"reinforce {squad}") == {"price": -30, "missing": 3}
    assert scores(row)["rifle"] == -100.0
    assert row.scored == len(world.table.squads) + 1


def test_a_refill_forced_by_the_maps_cap_names_the_bar_in_the_trace() -> None:
    # The trigger has to be arguable from the row alone: a refill chosen with
    # no fresh price beside it would otherwise read as a comparison nobody can
    # reconstruct. Fresh Squads a cap barred are absent from the candidates —
    # a listed candidate outscoring the winner and losing anyway is a trace
    # lying about its own arithmetic — and the bar is named in the sentence.
    world, thinned = capped_with_a_thinned_squad(5)

    row = only(brain(world).plan(world.observation("WEST")).decisions, "funds")

    assert row.chose == f"reinforce {thinned}"
    assert row.because == "3 men short at Base; 8 Squads fielded of 8 the map holds"
    assert [candidate.choice for candidate in row.candidates] == [f"reinforce {thinned}"]


def test_a_purchase_chosen_over_a_live_refill_says_what_it_beat() -> None:
    world = live()
    squad = bought(world, "WEST", "weapons")
    world.roster.reconcile({squad: Held(1, "nato_airbase")})

    row = only(brain(world).plan(world.observation("WEST")).decisions, "funds")

    assert row.chose == "purchase rifle"
    assert row.because == (
        f"1 Squads fielded; rifle at 100 adds a whole Squad against refilling {squad} at 105"
    )
    assert [candidate.choice for candidate in row.candidates] == [
        "rifle",
        f"reinforce {squad}",
        "weapons",
    ]


ROSTER = st.lists(st.integers(min_value=1, max_value=8), min_size=1, max_size=8)


@given(ROSTER, st.integers(min_value=0, max_value=3))
def test_no_reinforce_the_planner_issues_is_one_the_port_would_refuse(
    sizes: list[int], cycles: int
) -> None:
    # The never-refused family (ADR-0031's detector) over the boards #150 adds:
    # rosters of every strength standing at Base, played for several cycles so
    # a Squad refilled last cycle is a board this cycle plans against.
    # `already_held`, `wrong_ground` and `insufficient_funds` are each one
    # misread comparison away, and the real port is the judge.
    world = live()
    world.ledger.deposit("WEST", 10_000)
    open_port = port.CommandPort(campaign=world)
    for _ in sizes:
        judged = open_port.submit(
            Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
        )
        assert judged.accepted, judged.detail
    world.roster.reconcile(
        {
            squad.id: Held(size, "nato_airbase")
            for squad, size in zip(world.roster.roll("WEST"), sizes, strict=True)
        }
    )
    mind = brain(world)
    for _ in range(cycles + 1):
        _, judgements = cycle(world, mind, "WEST")
        assert [(one.code, one.detail) for one in judgements if not one.accepted] == []
