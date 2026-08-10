"""The composition-unassigned player shell, and the Commander-only first fill.

ADR-0070's rulings as they reach the daemon (#310). A player squad leader leads
a roster Squad that begins as a shell: minted at own Base with himself as its
sole member, active, composition-unassigned and costing nothing; suspended if he
disconnects before it is filled; assigned a composition exactly once, by his
Commander, at ordinary Reinforce pricing.

What is pinned here is the aggregate's lifecycle and the port's judgements over
it. The roster's own half is in `test_squads`, the document's in `test_snapshot`
and `test_campaign_snapshot`, and the wire's in `test_commands`.
"""

from __future__ import annotations

import inspect

import pytest
from conftest import authored_economy, live, starting_funds
from test_port import BASE_OF, EAST_BASE, WEST_BASE, bought, fresh, home, reported

from cti_daemon import port, squads
from cti_daemon.commands import Command, Effect

# The authored rifle Squad the acceptance criteria are written against: price
# 100, size 8, so a fill for a player already standing is seven eighths at the
# 0.8 discount. Read off the table rather than restated, because what is being
# pinned below is the arithmetic's *answer* and not the table.
RIFLE = "rifle"


def enrol(open_port: port.CommandPort, side: str = "WEST", uid: str = "uid-1") -> squads.Squad:
    """Enrol a player squad leader's shell for `side`.

    Through the Campaign rather than the port: taking the slot is not a Command
    — no Funds move and the rules judge nothing — so it reaches the daemon on
    the observe report, exactly as a chosen loadout does.
    """
    return open_port.campaign.enrol(side, uid)


def fill(
    open_port: port.CommandPort, squad_id: str, side: str = "WEST", squad_type: str = RIFLE
) -> port.Judgement:
    """Issue the Commander's composition-carrying Reinforce for that Squad."""
    return open_port.submit(
        Command("reinforce_composition", side, {"squad": squad_id, "squad_type": squad_type}),
        acting_side=side,
    )


# --- the shell as it is minted --------------------------------------------


def test_a_shell_mints_at_own_base_with_one_man_and_costs_nothing() -> None:
    # Ruling 1, and the Ledger is what says "costs nothing": asserting on the
    # absence of an exception would pass just as well against a Campaign that
    # charged for it and could afford to.
    open_port = fresh()
    before = open_port.campaign.ledger.balance("WEST")

    shell = enrol(open_port)

    assert open_port.campaign.ledger.balance("WEST") == before == starting_funds()
    assert (shell.side, shell.size, shell.at) == ("WEST", 1, WEST_BASE)
    assert shell.squad_type == ""
    assert shell.composition_assigned is False
    assert shell.suspended is False
    assert shell.player_uid == "uid-1"


def test_enrolment_tells_the_world_which_group_answers_to_the_minted_id() -> None:
    # The daemon mints Squad ids for the resume determinism ADR-0003 requires,
    # and the player's group already exists because the engine made it for the
    # slot. Without the pairing no Order can reach the Squad — so the effect
    # exists to create nobody and spend nothing, and to say only that.
    open_port = fresh()
    shell = enrol(open_port)

    assert Effect(
        name="squad_enrolled", side="WEST", args={"squad": shell.id, "player": "uid-1"}
    ) in [entry.effect for entry in open_port.campaign.outbox.pending()]


def test_a_shell_is_an_ordinary_roster_squad_everywhere_a_squad_is_counted() -> None:
    # Ruling 1 again: it is a roster Squad and not an out-of-roster avatar, so
    # it appears in the roll, in its Commander's Observation and in the
    # snapshot. Asserted directly rather than as the absence of an error — a
    # Squad that had quietly dropped out of all three would raise nothing.
    open_port = fresh()
    shell = enrol(open_port)
    campaign = open_port.campaign

    assert [squad.id for squad in campaign.roster.roll("WEST")] == [shell.id]
    assert [view.id for view in campaign.observation("WEST").squads] == [shell.id]
    assert [record.id for record in campaign.to_snapshot().squads] == [shell.id]
    # And against the enemy's picture, which is the projection #27 exists for.
    assert campaign.observation("EAST").squads == ()


def test_a_shell_counts_against_the_force_the_wire_carries() -> None:
    # ADR-0070 records this as a consequence of ruling 1 rather than a new
    # decision, so that it is not rediscovered as a bug: a shell is a roster
    # Squad, so a side fielding one may buy one fewer.
    open_port = fresh()
    ceiling = open_port.squad_ceiling
    assert ceiling is not None
    enrol(open_port)
    for _ in range(ceiling - 1):
        open_port.campaign.roster.add("WEST", RIFLE, 8)
    open_port.campaign.ledger.deposit("WEST", 10_000)

    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": RIFLE}), acting_side="WEST"
    )

    assert judgement.code == "force_limit"


def test_presence_is_sampled_from_bodies_and_has_never_known_whose_squad_they_are() -> None:
    # Ruling 8: every living member of a player-led Squad contributes to
    # Objective presence exactly like a member of an AI-led one, and leadership
    # alters no presence rule. Stated as the property rather than trusted:
    # `observe` takes an in-game time and a map of Objective ids to the sides
    # standing in each radius, so there is no argument it could filter by and
    # no Squad it could name.
    assert [name for name in inspect.signature(live().observe).parameters if name != "self"] == [
        "at_time",
        "presence",
    ]

    # And the same capture completes identically whether or not the side owns a
    # player-led shell, which is what "no code path filters by leadership" means
    # in play.
    seconds = authored_economy().capture_seconds
    plain, with_shell = live(), live()
    with_shell.enrol("WEST", "uid-1")
    for campaign in (plain, with_shell):
        campaign.observe(seconds, {"agia_marina": ["WEST"]})
    assert plain.owners() == with_shell.owners()
    assert with_shell.owner("agia_marina") == "WEST"


# --- the ordinary Reinforce meeting a shell -------------------------------


def test_the_ordinary_reinforce_on_a_shell_is_refused_for_what_it_actually_is() -> None:
    # The refusal ADR-0070 minted a code for: `Campaign.missing` answers 0 both
    # for a Squad the table has stopped selling and for one with no type at all,
    # so the older rule typed this `malformed_command` — telling a Commander the
    # economy table is broken when it is not, and doing it as the first refusal
    # a player squad leader ever meets.
    open_port = fresh()
    shell = enrol(open_port)
    funds = open_port.campaign.ledger.balance("WEST")

    judgement = open_port.submit(
        Command("reinforce", "WEST", {"squad": shell.id}), acting_side="WEST"
    )

    assert judgement.code == "composition_unassigned"
    assert judgement.code != "malformed_command"
    assert open_port.campaign.ledger.balance("WEST") == funds


def test_the_ordinary_reinforce_on_a_suspended_shell_names_the_suspension() -> None:
    # Both refusals are true of a suspended shell, and the useful one is that
    # its player is gone rather than that its composition is missing.
    open_port = fresh()
    shell = enrol(open_port)
    open_port.campaign.suspend(shell.id, "WEST")

    judgement = open_port.submit(
        Command("reinforce", "WEST", {"squad": shell.id}), acting_side="WEST"
    )

    assert judgement.code == "squad_suspended"


def test_a_squad_the_table_no_longer_sells_is_still_the_tables_fault() -> None:
    # The distinction the new code exists to preserve, from the other side: a
    # Squad that *was* bought and whose type has since left the authored table
    # is a fault in the table, and stays `malformed_command`.
    open_port = fresh()
    squad = bought(open_port)
    home(open_port, squad, size=5)
    held = open_port.campaign.roster.owned_by(squad, "WEST")
    assert held is not None
    held.squad_type = "battleship"

    judgement = open_port.submit(Command("reinforce", "WEST", {"squad": squad}), acting_side="WEST")

    assert judgement.code == "malformed_command"


# --- the first fill -------------------------------------------------------


def test_the_first_fill_charges_seventy_funds_for_the_authored_rifle_squad() -> None:
    # Ruling 3's own worked example: the missing fraction of the assigned
    # composition's price at the existing Reinforce discount, which for an
    # eight-man composition whose player is already standing is
    # ceil(100 x 7/8 x 0.8) = 70. Written out rather than recomputed from the
    # table here, because a test that repeats the expression under test agrees
    # with it by construction.
    open_port = fresh()
    shell = enrol(open_port)
    funds = open_port.campaign.ledger.balance("WEST")

    judgement = fill(open_port, shell.id)

    assert judgement.accepted, judgement.detail
    assert judgement.result == {"squad": shell.id, "funds": funds - 70, "cost": 70, "size": 8}
    assert open_port.campaign.ledger.balance("WEST") == funds - 70


def test_an_accepted_first_fill_assigns_the_composition_and_tells_the_world() -> None:
    # The type rides the effect because `fn_effectApply`'s `squad_reinforced`
    # branch reads it off `cti_squadType`, which the world set at spawn — and a
    # shell was never spawned by an effect, so it carries none.
    open_port = fresh()
    shell = enrol(open_port)

    fill(open_port, shell.id)

    assert shell.squad_type == RIFLE
    assert shell.composition_assigned is True
    assert shell.size == 8
    assert Effect(
        name="squad_filled",
        side="WEST",
        args={"squad": shell.id, "squad_type": RIFLE, "size": 8},
    ) in [entry.effect for entry in open_port.campaign.outbox.pending()]


def test_a_filled_squad_is_reinforced_at_the_ordinary_rule_from_then_on() -> None:
    # Ruling 3's second half: from the first fill the composition is fixed and
    # persisted like any other Squad's, and later Reinforce restores it rather
    # than reclassifying it. Three of eight men of a 100-Funds Squad at 0.8 is
    # 30, which is what every other rifle Squad pays.
    open_port = fresh()
    shell = enrol(open_port)
    fill(open_port, shell.id)
    home(open_port, shell.id, size=5)
    funds = open_port.campaign.ledger.balance("WEST")

    judgement = open_port.submit(
        Command("reinforce", "WEST", {"squad": shell.id}), acting_side="WEST"
    )

    assert judgement.accepted, judgement.detail
    assert judgement.result == {"squad": shell.id, "funds": funds - 30, "cost": 30, "size": 8}
    assert shell.squad_type == RIFLE


def test_a_second_first_fill_is_refused_and_the_composition_is_unchanged() -> None:
    # The once-only rule (ruling 3). Not `already_held`, which means "at the
    # strength it was bought at" and is a claim about men rather than about what
    # the Squad is.
    open_port = fresh()
    shell = enrol(open_port)
    fill(open_port, shell.id)
    funds = open_port.campaign.ledger.balance("WEST")

    judgement = fill(open_port, shell.id, squad_type=authored_economy().squads[1].id)

    assert judgement.code == "composition_fixed"
    assert shell.squad_type == RIFLE
    assert open_port.campaign.ledger.balance("WEST") == funds


def test_the_first_fill_form_on_an_ordinary_bought_squad_is_the_same_refusal() -> None:
    # A bought Squad has carried a composition since the moment it was paid
    # for, so the once-only rule reaches it by the same route.
    open_port = fresh()
    squad = bought(open_port)
    home(open_port, squad, size=5)

    assert fill(open_port, squad).code == "composition_fixed"


def test_the_first_fill_of_a_suspended_shell_is_refused_and_costs_nothing() -> None:
    # Ruling 7: while suspended it is ineligible for filling and has spent no
    # Funds.
    open_port = fresh()
    shell = enrol(open_port)
    open_port.campaign.suspend(shell.id, "WEST")
    funds = open_port.campaign.ledger.balance("WEST")

    judgement = fill(open_port, shell.id)

    assert judgement.code == "squad_suspended"
    assert shell.composition_assigned is False
    assert open_port.campaign.ledger.balance("WEST") == funds


def test_the_first_fill_of_a_shell_away_from_its_own_base_is_wrong_ground() -> None:
    # `wrong_ground` already covers this and covers it correctly (ADR-0070), so
    # no code was minted for it: the men arrive where the manifest puts the
    # side's Base, exactly as an ordinary Reinforce's do.
    open_port = fresh()
    shell = enrol(open_port)
    reported(open_port, **{shell.id: squads.Held(size=1, at="agia_marina")})

    assert fill(open_port, shell.id).code == "wrong_ground"


def test_the_first_fill_of_the_other_sides_shell_is_simply_not_found() -> None:
    # `unknown_squad` already covers it through the roster's forgiving read: a
    # Commander has no business learning the enemy's ids by guessing.
    open_port = fresh()
    theirs = enrol(open_port, side="EAST", uid="uid-2")

    judgement = fill(open_port, theirs.id)

    assert judgement.code == "unknown_squad"
    assert theirs.composition_assigned is False


def test_the_first_fill_of_a_composition_the_table_does_not_sell_is_malformed() -> None:
    open_port = fresh()
    shell = enrol(open_port)

    assert fill(open_port, shell.id, squad_type="battleship").code == "malformed_command"


@pytest.mark.parametrize(
    ("args", "why"),
    [
        ({}, "no Squad named"),
        ({"squad": ""}, "an empty Squad id"),
        ({"squad": "WEST-1"}, "no composition named"),
        ({"squad": "WEST-1", "squad_type": ""}, "an empty composition"),
        ({"squad": "WEST-1", "squad_type": 7}, "a composition that is not a string"),
    ],
)
def test_a_first_fill_the_rules_cannot_read_is_rejected(args: dict[str, object], why: str) -> None:
    open_port = fresh()
    enrol(open_port)
    judgement = open_port.submit(Command("reinforce_composition", "WEST", args), acting_side="WEST")
    assert judgement.code == "malformed_command", why


def test_a_first_fill_beyond_the_balance_is_refused_and_assigns_nothing() -> None:
    open_port = fresh()
    shell = enrol(open_port)
    open_port.campaign.ledger.spend("WEST", open_port.campaign.ledger.balance("WEST"))

    judgement = fill(open_port, shell.id)

    assert judgement.code == "insufficient_funds"
    assert shell.composition_assigned is False
    assert shell.squad_type == ""


# --- the second principal may not choose his own composition --------------


def test_a_squad_leader_may_not_choose_his_own_squads_first_composition() -> None:
    # Ruling 4, and it is a property to assert rather than a mechanism to build:
    # a squad-leader caller is stamped with `acting_squad` and is refused
    # anything that is not the plain `reinforce`, so the composition-carrying
    # form is outside ADR-0040's second principal without a rule of its own.
    open_port = fresh()
    shell = enrol(open_port)
    funds = open_port.campaign.ledger.balance("WEST")

    judgement = open_port.submit(
        Command("reinforce_composition", "WEST", {"squad": shell.id, "squad_type": RIFLE}),
        acting_side="WEST",
        acting_squad=shell.id,
    )

    assert judgement.code == "wrong_side"
    assert shell.composition_assigned is False
    assert open_port.campaign.ledger.balance("WEST") == funds


def test_the_principal_rule_gained_no_branch_for_the_composition_carrying_form() -> None:
    # The half the behaviour above cannot show. A new branch here would mean the
    # second principal's authority had been restated in two places, which is
    # exactly what ADR-0040 put this rule in `submit` to prevent — so the
    # refusal has to come from the existing "anything that is not `reinforce`"
    # rule and not from a rule naming this Command.
    source = inspect.getsource(port.CommandPort._principal_refusal)  # noqa: SLF001 — the subject
    # The docstring is excluded rather than scanned: prose there may legitimately
    # name the Command, and what must not exist is a *branch* on it.
    _before, docstring, body = source.split('"""')
    assert "ADR-0040" in docstring, "the docstring split found no docstring to exclude"

    assert "reinforce_composition" not in body


# --- suspension and reactivation ------------------------------------------


def test_suspending_a_shell_empties_it_and_moves_no_funds() -> None:
    # Ruling 7: while suspended it contributes no presence and has spent no
    # Funds. "Contributes no presence" is an absence of bodies rather than an
    # exemption, which is what the head count going to nought says.
    open_port = fresh()
    shell = enrol(open_port)
    funds = open_port.campaign.ledger.balance("WEST")
    queued = len(open_port.campaign.outbox.pending())

    open_port.campaign.suspend(shell.id, "WEST")

    assert shell.suspended is True
    assert shell.size == 0
    assert shell.composition_assigned is False
    assert open_port.campaign.ledger.balance("WEST") == funds
    # Nothing to carry out: the player's group went with him.
    assert len(open_port.campaign.outbox.pending()) == queued


def test_reactivation_returns_the_same_roster_id_at_own_base_still_unassigned() -> None:
    # The whole of why suspension was chosen over dissolution: the same roster
    # identity — and its minted id — comes back with the player, and no Funds
    # moved across the cycle.
    open_port = fresh()
    shell = enrol(open_port)
    before = open_port.campaign.ledger.balance("WEST")
    open_port.campaign.suspend(shell.id, "WEST")

    back = open_port.campaign.reactivate(shell.id, "WEST")

    assert back is shell
    assert back.id == shell.id
    assert (back.suspended, back.size, back.at) == (False, 1, WEST_BASE)
    assert back.composition_assigned is False
    assert back.player_uid == "uid-1"
    assert open_port.campaign.ledger.balance("WEST") == before == starting_funds()


def test_reactivation_tells_the_world_which_group_answers_to_the_id_again() -> None:
    # A reconnecting player arrives on a group the server has never paired with
    # this id, so the enrolment effect is pushed a second time rather than a
    # third effect being minted for it.
    open_port = fresh()
    shell = enrol(open_port)
    open_port.campaign.suspend(shell.id, "WEST")

    open_port.campaign.reactivate(shell.id, "WEST")

    enrolments = [
        entry.effect
        for entry in open_port.campaign.outbox.pending()
        if entry.effect.name == "squad_enrolled"
    ]
    assert len(enrolments) == 2
    assert enrolments[-1].args == {"squad": shell.id, "player": "uid-1"}


def test_a_reactivated_shell_can_then_be_filled_at_the_ordinary_price() -> None:
    # The cycle end to end: enrol, suspend, reactivate, fill — and the fill
    # costs what it would have cost before the player ever left.
    open_port = fresh()
    shell = enrol(open_port)
    funds = open_port.campaign.ledger.balance("WEST")
    open_port.campaign.suspend(shell.id, "WEST")
    open_port.campaign.reactivate(shell.id, "WEST")

    judgement = fill(open_port, shell.id)

    assert judgement.accepted, judgement.detail
    assert open_port.campaign.ledger.balance("WEST") == funds - 70


@pytest.mark.parametrize("doing", ["suspend", "reactivate"])
def test_suspension_is_defined_for_a_composition_unassigned_squad_alone(doing: str) -> None:
    # Ruling 5 against ruling 7: a filled Squad survives disconnect under an
    # engine-selected AI leader and keeps its Order, so suspending one would
    # contradict the ruling beside it. Raised rather than refused — nothing
    # commands a suspension, so a caller reaching here with an ordinary Squad
    # has not asked what it was holding.
    open_port = fresh()
    squad = bought(open_port)

    with pytest.raises(ValueError, match="composition-unassigned"):
        getattr(open_port.campaign, doing)(squad, "WEST")


@pytest.mark.parametrize("doing", ["suspend", "reactivate"])
def test_suspending_a_squad_the_side_does_not_hold_is_a_callers_mistake(doing: str) -> None:
    open_port = fresh()
    theirs = enrol(open_port, side="EAST", uid="uid-2")

    with pytest.raises(KeyError, match=theirs.id):
        getattr(open_port.campaign, doing)(theirs.id, "WEST")


# --- a won Campaign takes none of it --------------------------------------


@pytest.mark.parametrize("verb", ["enrol", "suspend", "reactivate", "first_fill"])
def test_no_shell_verb_changes_a_campaign_that_has_been_won(verb: str) -> None:
    # #60's invariant reaching the four verbs ADR-0070 added: a Campaign that
    # has been won is no longer being played, and every mutating verb says so
    # rather than leaving the check to whichever caller remembered it.
    open_port = fresh()
    shell = enrol(open_port)
    open_port.campaign.raze(EAST_BASE, at_time=90)
    assert open_port.campaign.complete
    arguments = {
        "enrol": ("WEST", "uid-2"),
        "suspend": (shell.id, "WEST"),
        "reactivate": (shell.id, "WEST"),
        "first_fill": (shell.id, "WEST", RIFLE),
    }[verb]

    with pytest.raises(Exception, match="was won by"):
        getattr(open_port.campaign, verb)(*arguments)


def test_the_east_shell_is_minted_at_easts_own_base() -> None:
    # The Base is looked up per side rather than assumed, which one side alone
    # cannot show.
    open_port = fresh()
    assert enrol(open_port, side="EAST", uid="uid-2").at == EAST_BASE == BASE_OF["EAST"]
