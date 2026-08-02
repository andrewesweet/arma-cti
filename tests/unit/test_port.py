"""The Command Port entry function: the sole mutator of strategic state.

ADR-0012 makes the daemon the rules authority and this function the only door
into the campaign, for the human UI and the AI planner alike. The planner does
not cross the wire — it builds the same Command objects and calls this — so
Commander symmetry is one validator rather than two kept honest by convention.
"""

from __future__ import annotations

import pytest
from conftest import REPO, authored_economy, live
from hypothesis import given
from hypothesis import strategies as st

from cti_daemon import budget, manifest, port, squads
from cti_daemon.commands import Command, Effect

MAP = manifest.load(REPO / "addons" / "main" / "manifests" / "stratis.json")
WEST_BASE = next(base.id for base in MAP.bases if base.side == "WEST")
EAST_BASE = next(base.id for base in MAP.bases if base.side == "EAST")


def fresh() -> port.CommandPort:
    """Return a port over the authored map and economy, everything Neutral."""
    return port.CommandPort(campaign=live())


@pytest.fixture
def open_port() -> port.CommandPort:
    """Return the same port, for a test that wants one example not the matrix."""
    return fresh()


def bought(open_port: port.CommandPort, side: str = "WEST") -> str:
    """Buy one rifle Squad for `side` and return the id it was minted with."""
    judgement = open_port.submit(
        Command("purchase", side, {"squad_type": "rifle"}), acting_side=side
    )
    return str(judgement.result["squad"])


def standing(open_port: port.CommandPort, squad_id: str, side: str = "WEST") -> squads.Order:
    """Return the Order that Squad is currently carrying, refusing a ghost.

    The assert narrows `Squad | None` and says what it is doing: a Squad the
    roster does not have has no Order, which is a different failure.
    """
    squad = open_port.campaign.roster.owned_by(squad_id, side)
    assert squad is not None
    return squad.order


def test_a_purchase_is_accepted_and_costs_its_price(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert judgement.accepted
    assert open_port.ledger.balance("WEST") == 200


def test_an_accepted_purchase_reports_the_remaining_funds_and_what_it_bought(
    open_port: port.CommandPort,
) -> None:
    # Advisory only: the UI may show it, but the world is never mutated from a
    # reply (ADR-0012). The Squad id is there so a Commander can order what it
    # just bought without waiting for the next observation.
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert judgement.result == {"squad": "WEST-1", "funds": 200}


def test_an_accepted_purchase_queues_its_effect_rather_than_returning_it(
    open_port: port.CommandPort,
) -> None:
    # Every world effect rides the outbox, for both Commanders, so #19 has one
    # effect path to audit rather than two.
    open_port.submit(Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST")
    (entry,) = open_port.outbox.pending()
    assert entry.effect.name == "squad_spawned"
    assert entry.effect.side == "WEST"
    assert entry.effect.args["squad_type"] == "rifle"


def test_a_purchase_beyond_the_balance_is_rejected_and_costs_nothing(
    open_port: port.CommandPort,
) -> None:
    for _ in range(3):
        open_port.submit(Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST")
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert not judgement.accepted
    assert judgement.code == "insufficient_funds"
    assert open_port.ledger.balance("WEST") == 0
    assert len(open_port.outbox.pending()) == 3


def test_a_command_nobody_implements_is_rejected(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(Command("bombard", "WEST", {}), acting_side="WEST")
    assert judgement.code == "unknown_command"


def test_a_purchase_of_something_not_sold_is_rejected(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "battleship"}), acting_side="WEST"
    )
    assert judgement.code == "malformed_command"


def test_a_purchase_without_a_squad_type_is_rejected(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(Command("purchase", "WEST", {}), acting_side="WEST")
    assert judgement.code == "malformed_command"


def test_commanding_a_side_that_is_not_yours_is_rejected(open_port: port.CommandPort) -> None:
    # The gateway stamps the acting side server-side; a Command claiming another
    # side is a caller reaching past its own authority.
    judgement = open_port.submit(
        Command("purchase", "EAST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert judgement.code == "wrong_side"
    assert open_port.ledger.balance("EAST") == 300
    assert open_port.outbox.pending() == []


def test_the_rejection_codes_are_the_only_ones_the_port_issues() -> None:
    # The SQF side is generated from this set, so a code added without going
    # through here is one the game has never been told about.
    assert (
        frozenset(
            {
                "insufficient_funds",
                "unknown_command",
                "malformed_command",
                "wrong_side",
                "unknown_squad",
                "already_held",
                "wrong_ground",
                "campaign_over",
                # The second principal's own refusal (ADR-0040): a squad leader
                # reaching for a Squad that is not the one he leads.
                "not_your_squad",
                # The wire's own limit on how big a force can get (#101): the
                # measured point past which a side's Observation stops fitting
                # one callExtension return.
                "force_limit",
                # Minted by the gateway, not by this module (#97): the daemon
                # was never reached, so nothing was judged or spent.
                "port_unavailable",
                # A caller nobody stamped (ADR-0044): the line carried no
                # server-side `acting_side`, so who is acting is unknown.
                "unknown_caller",
            }
        )
        == port.REJECTION_CODES
    )


def test_an_order_is_recorded_against_the_squad_and_announced_as_an_effect(
    open_port: port.CommandPort,
) -> None:
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "capture", "place": "agia_marina"}),
        acting_side="WEST",
    )
    assert judgement.accepted
    assert standing(open_port, squad) == squads.Order("capture", "agia_marina")
    assert Effect(
        name="order_issued",
        side="WEST",
        args={"squad": squad, "order": "capture", "place": "agia_marina"},
    ) in [entry.effect for entry in open_port.outbox.pending()]


def test_a_later_order_supersedes_the_one_before_it(open_port: port.CommandPort) -> None:
    # Standing, not accumulating: a Squad carries one Order, and the newest one
    # is what the world is driven from.
    squad = bought(open_port)
    for kind in ("capture", "defend"):
        open_port.submit(
            Command("order", "WEST", {"squad": squad, "order": kind, "place": "girna"}),
            acting_side="WEST",
        )
    assert standing(open_port, squad) == squads.Order("defend", "girna")


def test_reserve_needs_no_place(open_port: port.CommandPort) -> None:
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "reserve", "place": ""}),
        acting_side="WEST",
    )
    assert judgement.accepted
    assert judgement.result["place"] == ""


def test_reserve_refuses_a_place_rather_than_ignoring_it(open_port: port.CommandPort) -> None:
    # Dropping it silently would hide a UI bug behind an Order that looked
    # accepted and sent the Squad somewhere else.
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "reserve", "place": "girna"}),
        acting_side="WEST",
    )
    assert judgement.code == "malformed_command"


def test_capturing_ground_your_own_side_holds_is_rejected(open_port: port.CommandPort) -> None:
    # Acceptance criterion 4 on #3: a nonsensical Order is refused rather than
    # quietly accepted as a no-op, so a Commander is told why.
    open_port.campaign.observe(30, {"agia_marina": ["WEST"]})
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "capture", "place": "agia_marina"}),
        acting_side="WEST",
    )
    assert judgement.code == "already_held"
    assert "agia_marina" in judgement.detail
    assert standing(open_port, squad) == squads.RESERVE


def test_defending_ground_your_own_side_holds_is_the_point_of_defending(
    open_port: port.CommandPort,
) -> None:
    open_port.campaign.observe(30, {"agia_marina": ["WEST"]})
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "defend", "place": "agia_marina"}),
        acting_side="WEST",
    )
    assert judgement.accepted


def test_capturing_ground_the_other_side_holds_is_allowed(open_port: port.CommandPort) -> None:
    open_port.campaign.observe(30, {"agia_marina": ["EAST"]})
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "capture", "place": "agia_marina"}),
        acting_side="WEST",
    )
    assert judgement.accepted


def test_ordering_a_squad_that_was_never_bought_is_rejected(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": "WEST-9", "order": "reserve", "place": ""}),
        acting_side="WEST",
    )
    assert judgement.code == "unknown_squad"


def test_ordering_the_other_sides_squad_is_rejected(open_port: port.CommandPort) -> None:
    squad = bought(open_port, "EAST")
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "reserve", "place": ""}),
        acting_side="WEST",
    )
    assert judgement.code == "unknown_squad"
    assert standing(open_port, squad, "EAST") == squads.RESERVE


@pytest.mark.parametrize(
    ("args", "why"),
    [
        ({"squad": "WEST-1", "order": "advance"}, "no such Order"),
        ({"squad": "WEST-1"}, "no Order at all"),
        ({"order": "reserve"}, "no Squad named"),
        ({"squad": "", "order": "reserve"}, "an empty Squad id"),
        ({"squad": "WEST-1", "order": "capture"}, "Capture with no ground"),
        ({"squad": "WEST-1", "order": "capture", "place": "narnia"}, "ground off the map"),
    ],
)
def test_an_order_the_rules_cannot_read_is_rejected(
    open_port: port.CommandPort, args: dict[str, object], why: str
) -> None:
    bought(open_port)
    judgement = open_port.submit(Command("order", "WEST", args), acting_side="WEST")
    assert judgement.code == "malformed_command", why


def test_an_order_for_a_side_that_is_not_yours_is_refused_before_the_squad_is_looked_up(
    open_port: port.CommandPort,
) -> None:
    squad = bought(open_port, "EAST")
    judgement = open_port.submit(
        Command("order", "EAST", {"squad": squad, "order": "reserve", "place": ""}),
        acting_side="WEST",
    )
    assert judgement.code == "wrong_side"


# The whole of the ground the map has, in one namespace, because an Order names
# a Place and a Place is either kind (ADR-0020).
BASE_SIDES = {base.id: base.side for base in MAP.bases}
OBJECTIVE_IDS = tuple(objective.id for objective in MAP.objectives)
PLACE_IDS = (*OBJECTIVE_IDS, *BASE_SIDES)
GROUND_ORDERS = st.sampled_from(squads.NEEDS_PLACE)
PLACES = st.sampled_from(PLACE_IDS)
HOLDERS = st.sampled_from(("", "WEST", "EAST"))


def refusal(kind: str, place: str, owner: str, *, side: str = "WEST") -> str:
    """Say what the rules make of `side` ordering `kind` onto `place`.

    Written out as ADR-0020 states it rather than by calling the port, so the
    matrix is asserted against the decision and not against the implementation
    of it.
    """
    base_side = BASE_SIDES.get(place)
    if kind == "capture":
        if base_side is not None:
            return "wrong_ground"
        return "already_held" if owner == side else ""
    if kind == "assault":
        return "" if base_side is not None and base_side != side else "wrong_ground"
    return "wrong_ground" if base_side not in (None, side) else ""


@given(kind=GROUND_ORDERS, place=PLACES, holder=HOLDERS)
def test_the_ground_each_order_may_name_is_the_only_ground_it_is_given(
    kind: str, place: str, holder: str
) -> None:
    # Through the real port over the authored map, in the style #16 used for the
    # planner: every kind that names ground against every Place the map has,
    # under every ownership that Place can be in, judged by the rules that will
    # judge it in play rather than by a restatement of them here.
    open_port = fresh()
    if holder and place in OBJECTIVE_IDS:
        open_port.campaign.observe(30, {place: [holder]})
    owner = open_port.campaign.holds(place) or ""
    squad = bought(open_port)

    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": kind, "place": place}),
        acting_side="WEST",
    )

    expected = refusal(kind, place, owner)
    assert judgement.code == expected, (kind, place, owner, judgement.detail)
    assert judgement.accepted == (expected == "")
    # A refused Order leaves the Squad under the one it was already carrying,
    # and puts nothing on the outbox for the world to act on.
    assert standing(open_port, squad) == (
        squads.Order(kind, place) if judgement.accepted else squads.RESERVE
    )
    issued = [entry.effect.name for entry in open_port.outbox.pending()]
    assert issued.count("order_issued") == int(judgement.accepted)


@given(kind=GROUND_ORDERS, place=st.text(max_size=24).filter(lambda name: name not in PLACE_IDS))
def test_a_place_this_map_does_not_have_is_malformed_rather_than_wrong_ground(
    kind: str, place: str
) -> None:
    # The distinction ADR-0020 draws: `wrong_ground` is ground the map has that
    # this Order may not name, so an id the map lacks stays the older refusal
    # and a Commander is not told a typo is a rules mistake.
    open_port = fresh()
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": kind, "place": place}),
        acting_side="WEST",
    )
    assert judgement.code == "malformed_command"


def test_the_four_forms_the_order_vocabulary_refuses_are_all_wrong_ground() -> None:
    # ADR-0020's matrix as named examples beside the property above, so the four
    # forms it decided are legible here rather than only derivable from a
    # strategy.
    forms = [
        ("capture", WEST_BASE),
        ("assault", "girna"),
        ("assault", WEST_BASE),
        ("defend", EAST_BASE),
    ]
    for kind, place in forms:
        open_port = fresh()
        squad = bought(open_port)
        judgement = open_port.submit(
            Command("order", "WEST", {"squad": squad, "order": kind, "place": place}),
            acting_side="WEST",
        )
        assert judgement.code == "wrong_ground", (kind, place)


def test_the_two_forms_the_vocabulary_widened_to_are_accepted() -> None:
    for kind, place in (("assault", EAST_BASE), ("defend", WEST_BASE)):
        open_port = fresh()
        squad = bought(open_port)
        judgement = open_port.submit(
            Command("order", "WEST", {"squad": squad, "order": kind, "place": place}),
            acting_side="WEST",
        )
        assert judgement.accepted, (kind, place)
        assert standing(open_port, squad) == squads.Order(kind, place)


# -------------------------------------------- Reinforce, and the two principals


BASE_OF = {"WEST": WEST_BASE, "EAST": EAST_BASE}


def reported(open_port: port.CommandPort, **standing: squads.Held) -> None:
    """Have the world report where every bought Squad is, and how many are up.

    Through `reconcile`, which is the only way those two facts ever reach the
    daemon (ADR-0012): head count and ground underfoot are what the world alone
    can see. Squads not named are reported where they were, so a test that
    arranges one Squad does not wipe the rest of the roster out.
    """
    seen = {
        squad.id: standing.get(squad.id, squads.Held(size=squad.size, at=squad.at))
        for side in ("WEST", "EAST")
        for squad in open_port.campaign.roster.roll(side)
    }
    open_port.campaign.reconcile(seen)


def home(open_port: port.CommandPort, squad_id: str, *, size: int = 5, side: str = "WEST") -> None:
    """Put one Squad at its own Base, `size` men standing."""
    reported(open_port, **{squad_id: squads.Held(size=size, at=BASE_OF[side])})


def test_a_commander_reinforces_a_squad_of_his_own_side(open_port: port.CommandPort) -> None:
    squad = bought(open_port)
    home(open_port, squad, size=5)
    funds = open_port.ledger.balance("WEST")

    judgement = open_port.submit(Command("reinforce", "WEST", {"squad": squad}), acting_side="WEST")

    # Missing fraction x price x discount, rounded up: three of eight men of a
    # 100-Funds Squad at 0.8 is 30.
    assert judgement.accepted
    assert judgement.result == {"squad": squad, "funds": funds - 30, "cost": 30, "size": 8}
    assert open_port.ledger.balance("WEST") == funds - 30


def test_an_accepted_reinforce_rides_the_outbox_like_every_other_effect(
    open_port: port.CommandPort,
) -> None:
    # ADR-0012/0018: a judgement is never work. The men arrive because the world
    # polled the outbox, on the one path #19 has to audit.
    squad = bought(open_port)
    home(open_port, squad, size=5)
    open_port.submit(Command("reinforce", "WEST", {"squad": squad}), acting_side="WEST")

    assert Effect(name="squad_reinforced", side="WEST", args={"squad": squad, "size": 8}) in [
        entry.effect for entry in open_port.outbox.pending()
    ]


def test_a_squad_leader_reinforces_the_squad_he_leads(open_port: port.CommandPort) -> None:
    # The second principal (ADR-0040). The stamp is the server's, not the
    # caller's: the gateway resolves it from the Squad the caller actually leads.
    squad = bought(open_port)
    home(open_port, squad, size=6)

    judgement = open_port.submit(
        Command("reinforce", "WEST", {"squad": squad}), acting_side="WEST", acting_squad=squad
    )

    assert judgement.accepted
    assert open_port.campaign.roster.roll("WEST")[0].size == 8


def test_a_squad_leader_may_not_reinforce_another_squad_of_his_own_side(
    open_port: port.CommandPort,
) -> None:
    mine = bought(open_port)
    theirs = bought(open_port)
    home(open_port, theirs, size=4)
    funds = open_port.ledger.balance("WEST")

    judgement = open_port.submit(
        Command("reinforce", "WEST", {"squad": theirs}), acting_side="WEST", acting_squad=mine
    )

    assert judgement.code == "not_your_squad"
    assert open_port.ledger.balance("WEST") == funds
    assert open_port.campaign.roster.roll("WEST")[1].size == 4


def test_a_squad_leader_learns_nothing_about_a_squad_id_he_guessed_at(
    open_port: port.CommandPort,
) -> None:
    # `not_your_squad` before the roster is consulted, so a Squad that exists and
    # one that never did are refused in the same words: a leader cannot map his
    # own side's order of battle, let alone the enemy's, by trying ids.
    mine = bought(open_port)
    real = bought(open_port, "EAST")

    refusals = {
        named: open_port.submit(
            Command("reinforce", "WEST", {"squad": named}), acting_side="WEST", acting_squad=mine
        )
        for named in (real, "WEST-99", "EAST-99")
    }

    assert {named: judgement.code for named, judgement in refusals.items()} == {
        real: "not_your_squad",
        "WEST-99": "not_your_squad",
        "EAST-99": "not_your_squad",
    }
    assert len({judgement.detail for judgement in refusals.values()}) == 1


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("purchase", {"squad_type": "rifle"}),
        ("order", {"squad": "WEST-1", "order": "reserve", "place": ""}),
    ],
)
def test_a_squad_leader_may_not_issue_the_commanders_own_commands(
    open_port: port.CommandPort, name: str, args: dict[str, object]
) -> None:
    # ADR-0040 widened the issuer set for Reinforce alone. Purchase and Order
    # stay a Commander's, so a leader asking for one is reaching past his
    # authority — which is what `wrong_side` has always named.
    squad = bought(open_port)
    funds = open_port.ledger.balance("WEST")

    judgement = open_port.submit(
        Command(name, "WEST", args), acting_side="WEST", acting_squad=squad
    )

    assert judgement.code == "wrong_side"
    assert open_port.ledger.balance("WEST") == funds
    assert standing(open_port, squad) == squads.RESERVE


def test_a_squad_leader_may_not_reinforce_for_another_side(open_port: port.CommandPort) -> None:
    # The first axis still binds: a leader stamped for WEST cannot reach EAST's
    # roster by naming an EAST Squad and an EAST side.
    theirs = bought(open_port, "EAST")
    judgement = open_port.submit(
        Command("reinforce", "EAST", {"squad": theirs}), acting_side="WEST", acting_squad=theirs
    )
    assert judgement.code == "wrong_side"


def test_reinforcing_a_squad_at_full_strength_is_refused(open_port: port.CommandPort) -> None:
    # Accepting it would take Funds for nothing and put an effect on the outbox
    # the world would carry out by spawning nobody.
    squad = bought(open_port)
    home(open_port, squad, size=8)
    funds = open_port.ledger.balance("WEST")

    judgement = open_port.submit(Command("reinforce", "WEST", {"squad": squad}), acting_side="WEST")

    assert judgement.code == "already_held"
    assert open_port.ledger.balance("WEST") == funds
    assert [entry.effect.name for entry in open_port.outbox.pending()] == ["squad_spawned"]


@pytest.mark.parametrize(
    ("where", "why"),
    [
        ("", "a Squad the world has never reported is nowhere"),
        ("agia_marina", "an Objective is not a Base"),
        (EAST_BASE, "the enemy's Base is not its own"),
    ],
)
def test_reinforcing_away_from_its_own_base_is_refused(
    open_port: port.CommandPort, where: str, why: str
) -> None:
    # CONTEXT.md puts Reinforce at own Base. The Place is the coarse one the
    # world reports, so this is about where the Squad is standing.
    squad = bought(open_port)
    reported(open_port, **{squad: squads.Held(size=5, at=where)})

    judgement = open_port.submit(Command("reinforce", "WEST", {"squad": squad}), acting_side="WEST")

    assert judgement.code == "wrong_ground", why


def test_reinforcing_beyond_the_balance_is_refused_and_costs_nothing(
    open_port: port.CommandPort,
) -> None:
    squad = bought(open_port)
    home(open_port, squad, size=1)
    open_port.ledger.spend("WEST", open_port.ledger.balance("WEST"))

    judgement = open_port.submit(Command("reinforce", "WEST", {"squad": squad}), acting_side="WEST")

    assert judgement.code == "insufficient_funds"
    assert open_port.ledger.balance("WEST") == 0
    assert open_port.campaign.roster.roll("WEST")[0].size == 1


def test_reinforcing_a_squad_nobody_bought_is_rejected(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(
        Command("reinforce", "WEST", {"squad": "WEST-9"}), acting_side="WEST"
    )
    assert judgement.code == "unknown_squad"


def test_reinforcing_the_other_sides_squad_is_rejected(open_port: port.CommandPort) -> None:
    theirs = bought(open_port, "EAST")
    home(open_port, theirs, size=5, side="EAST")

    judgement = open_port.submit(
        Command("reinforce", "WEST", {"squad": theirs}), acting_side="WEST"
    )

    assert judgement.code == "unknown_squad"
    assert open_port.campaign.roster.roll("EAST")[0].size == 5


@pytest.mark.parametrize(
    ("args", "why"),
    [
        ({}, "no Squad named"),
        ({"squad": ""}, "an empty Squad id"),
        ({"squad": 7}, "a Squad id that is not a string"),
    ],
)
def test_a_reinforce_the_rules_cannot_read_is_rejected(
    open_port: port.CommandPort, args: dict[str, object], why: str
) -> None:
    judgement = open_port.submit(Command("reinforce", "WEST", args), acting_side="WEST")
    assert judgement.code == "malformed_command", why


def test_a_reinforce_after_the_campaign_is_won_is_refused_and_costs_nothing(
    open_port: port.CommandPort,
) -> None:
    squad = bought(open_port)
    home(open_port, squad, size=5)
    won(open_port)
    funds = open_port.ledger.balance("WEST")
    queued = len(open_port.outbox.pending())

    judgement = open_port.submit(Command("reinforce", "WEST", {"squad": squad}), acting_side="WEST")

    assert judgement.code == "campaign_over"
    assert open_port.ledger.balance("WEST") == funds
    assert len(open_port.outbox.pending()) == queued


PRINCIPALS = st.sampled_from(("commander", "own_leader", "other_leader"))
COMMAND_NAMES = st.sampled_from(("purchase", "order", "reinforce"))


@given(principal=PRINCIPALS, name=COMMAND_NAMES)
def test_who_may_issue_what_is_the_matrix_adr_0040_wrote_down(principal: str, name: str) -> None:
    # The ownership matrix through the real port: every principal against every
    # Command in the catalogue, judged by the rules that will judge them in play
    # rather than by a restatement of them here. Asserted on the *code*, so a
    # refusal arriving under the wrong name is as red as one that never came.
    open_port = fresh()
    mine = bought(open_port)
    other = bought(open_port)
    home(open_port, mine, size=5)
    home(open_port, other, size=5)
    acting_squad = {"commander": "", "own_leader": mine, "other_leader": other}[principal]
    args: dict[str, str] = {
        "purchase": {"squad_type": "rifle"},
        "order": {"squad": mine, "order": "reserve", "place": ""},
        "reinforce": {"squad": mine},
    }[name]

    judgement = open_port.submit(
        Command(name, "WEST", args), acting_side="WEST", acting_squad=acting_squad
    )

    expected = ""
    if principal != "commander":
        # ADR-0040 as written: a squad leader has Reinforce, for his own Squad.
        expected = "wrong_side" if name != "reinforce" else ""
        if name == "reinforce" and principal == "other_leader":
            expected = "not_your_squad"
    assert judgement.code == expected, (principal, name, judgement.detail)
    assert judgement.accepted == (expected == "")


# ----------------------------------------------- A Campaign that has been won


def won(open_port: port.CommandPort) -> None:
    """End the Campaign the way the world ends one: WEST takes EAST's HQ."""
    open_port.campaign.raze(EAST_BASE, at_time=90)
    assert open_port.campaign.complete


def test_a_purchase_after_the_campaign_is_won_is_refused_and_costs_nothing(
    open_port: port.CommandPort,
) -> None:
    # #59: the aggregate's central invariant — a won Campaign is no longer being
    # played — reaching the one door ADR-0012 calls the only way strategic state
    # ever moves. Funds spent here would be a finished Campaign's, and the Squad
    # would spawn into a world that has already had its end screen.
    funds = open_port.ledger.balance("WEST")
    won(open_port)

    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )

    assert not judgement.accepted
    assert judgement.code == "campaign_over"
    assert open_port.ledger.balance("WEST") == funds
    assert open_port.campaign.roster.roll("WEST") == ()
    assert open_port.outbox.pending() == []


def test_an_order_after_the_campaign_is_won_leaves_the_squad_carrying_the_last_one(
    open_port: port.CommandPort,
) -> None:
    squad = bought(open_port)
    open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "capture", "place": "girna"}),
        acting_side="WEST",
    )
    won(open_port)
    queued = len(open_port.outbox.pending())

    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "defend", "place": "agia_marina"}),
        acting_side="WEST",
    )

    assert judgement.code == "campaign_over"
    assert standing(open_port, squad) == squads.Order("capture", "girna")
    assert len(open_port.outbox.pending()) == queued


def stock(open_port: port.CommandPort, squads_held: int, side: str = "WEST") -> None:
    """Give a side that many Squads and the Funds to keep buying.

    Minted straight onto the roster rather than bought: what is under test is
    the bound on the roster's size, and buying forty Squads through the port to
    reach it would be testing the Ledger.
    """
    for _ in range(squads_held):
        open_port.campaign.roster.add(side, "rifle", 8)
    open_port.ledger.deposit(side, 10_000)


def test_the_squad_ceiling_is_the_one_the_wire_was_measured_at(
    open_port: port.CommandPort,
) -> None:
    # Measured rather than chosen (#101): the port refuses at the point this
    # map's worst-case Observation stops fitting one callExtension return, so
    # nobody has picked a force cap and no map carries a number of its own.
    assert open_port.squad_ceiling == budget.squad_ceiling(MAP, authored_economy())


def test_a_purchase_past_what_the_wire_carries_is_refused(open_port: port.CommandPort) -> None:
    # The 36th Squad truncated a Commander's picture in silence, and the session
    # degraded every cycle afterwards with the cause hours behind it. Funds were
    # the only question a Purchase was judged on; the wire is now one too.
    ceiling = open_port.squad_ceiling
    assert ceiling is not None
    stock(open_port, ceiling)
    funds = open_port.ledger.balance("WEST")

    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )

    assert not judgement.accepted
    assert judgement.code == "force_limit"
    assert open_port.ledger.balance("WEST") == funds
    assert open_port.outbox.pending() == []


def test_the_last_squad_the_wire_carries_is_still_bought(open_port: port.CommandPort) -> None:
    # The bound stops the roster growing past what fits, and not one Squad
    # earlier: a cap that refused the Squad the wire can carry would be a
    # balance decision arriving as a safety margin.
    ceiling = open_port.squad_ceiling
    assert ceiling is not None
    stock(open_port, ceiling - 1)

    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )

    assert judgement.accepted
    assert len(open_port.campaign.roster.roll("WEST")) == ceiling


def test_the_wires_limit_binds_each_side_on_its_own(open_port: port.CommandPort) -> None:
    # An Observation carries one side (#27), so a side at the limit says nothing
    # about the other's picture and must not spend the enemy's headroom.
    ceiling = open_port.squad_ceiling
    assert ceiling is not None
    stock(open_port, ceiling)
    open_port.ledger.deposit("EAST", 10_000)

    judgement = open_port.submit(
        Command("purchase", "EAST", {"squad_type": "rifle"}), acting_side="EAST"
    )

    assert judgement.accepted
