"""The Squad roster: identity stable enough to be ordered.

An Order names a Squad, so a Squad needs a name. #14 requires that name to
survive the leader who was carrying it, which starts here: the id belongs to the
Squad, not to whoever happens to be leading it.
"""

from __future__ import annotations

from cti_daemon import squads
from cti_daemon.squads import Held


def test_a_bought_squad_gets_an_id_a_commander_can_say() -> None:
    roster = squads.Roster()
    assert roster.add("WEST", "rifle", 8).id == "WEST-1"


def test_ids_count_up_within_a_side_and_never_collide_across_sides() -> None:
    # Derived from a per-side count rather than a clock: a resumed campaign has
    # to mint the same ids in the same order (ADR-0003).
    roster = squads.Roster()
    minted = [roster.add(side, "rifle", 8).id for side in ("WEST", "EAST", "WEST")]
    assert minted == ["WEST-1", "EAST-1", "WEST-2"]


def test_a_new_squad_is_in_reserve_until_it_is_told_otherwise() -> None:
    # A Squad that has just been bought is standing at its own Base, which is
    # what Reserve means. Having no Order at all would leave the world without
    # an answer for what it should be doing.
    roster = squads.Roster()
    assert roster.add("WEST", "rifle", 8).order == squads.Order("reserve")


def test_a_squad_is_found_by_the_side_that_owns_it() -> None:
    roster = squads.Roster()
    squad = roster.add("WEST", "rifle", 8)
    assert roster.owned_by(squad.id, "WEST") is squad


def test_the_other_sides_squad_is_simply_not_found() -> None:
    # Not a separate refusal: a Commander has no business learning which Squads
    # the enemy holds by guessing at ids.
    roster = squads.Roster()
    squad = roster.add("WEST", "rifle", 8)
    assert roster.owned_by(squad.id, "EAST") is None


def test_a_squad_nobody_bought_is_not_found() -> None:
    assert squads.Roster().owned_by("WEST-9", "WEST") is None


def test_a_sides_roll_lists_its_own_squads_in_the_order_they_were_bought() -> None:
    roster = squads.Roster()
    roster.add("WEST", "rifle", 8)
    roster.add("EAST", "weapons", 8)
    roster.add("WEST", "weapons", 8)
    assert [squad.id for squad in roster.roll("WEST")] == ["WEST-1", "WEST-2"]


def test_no_call_hands_out_the_whole_map_of_squads() -> None:
    # #27: the projection has to hold against an in-process planner, so the
    # roster has no reading that returns both sides for one to reach for.
    roster = squads.Roster()
    roster.add("WEST", "rifle", 8)
    roster.add("EAST", "weapons", 8)
    assert roster.roll("EAST") == (roster.owned_by("EAST-1", "EAST"),)


def test_reserve_is_the_only_order_that_names_no_ground() -> None:
    assert set(squads.ORDERS) - set(squads.NEEDS_PLACE) == {"reserve"}


def test_assault_is_in_the_vocabulary() -> None:
    # ADR-0020: Decapitation is a win condition, and until Assault is an Order
    # a Commander has no words for it. Which Place it may name is the port's
    # rule; that it exists at all is this one's.
    assert "assault" in squads.ORDERS


def test_a_squad_the_world_has_never_held_is_not_a_squad_the_world_has_lost() -> None:
    # A Squad is bought in the daemon and spawned in the game, and a report
    # taken between the two says nothing about it. Reading that silence as a
    # loss deletes the Squad on its way into the world, and the group that
    # arrives a moment later answers to an id the roster no longer knows — a
    # ghost the Commander cannot order and does not count, so it buys another.
    # The AI Commander (#16) buys on that cadence, which is how this surfaced.
    roster = squads.Roster()
    roster.add("WEST", "rifle", 8)

    assert roster.reconcile({}) == ()
    assert [squad.id for squad in roster.roll("WEST")] == ["WEST-1"]


def test_a_squad_the_world_did_hold_and_no_longer_does_is_lost() -> None:
    roster = squads.Roster()
    roster.add("WEST", "rifle", 8)
    roster.reconcile({"WEST-1": Held(8, "girna")})

    assert roster.reconcile({}) == ("WEST-1",)
    assert roster.roll("WEST") == ()


def test_an_assault_outlives_the_leader_who_was_carrying_it() -> None:
    # An Order is standing rather than a waypoint consumed and forgotten (#14),
    # and the roster is the unit-level half of that: the world reports how many
    # of a Squad are standing and where, and the Order it is under is not among
    # the facts it gets to report. Assault is the case that matters most (#33) —
    # the Squad is inside the enemy Base when its leader is killed, and one that
    # fell back to Reserve there would turn round and walk home.
    roster = squads.Roster()
    squad = roster.add("WEST", "rifle", 8)
    squad.order = squads.Order("assault", "csat_kamino")
    roster.reconcile({"WEST-1": Held(8, "")})

    roster.reconcile({"WEST-1": Held(5, "csat_kamino")})

    surviving = roster.owned_by("WEST-1", "WEST")
    assert surviving is not None
    assert surviving.order == squads.Order("assault", "csat_kamino")
    assert (surviving.size, surviving.at) == (5, "csat_kamino")
