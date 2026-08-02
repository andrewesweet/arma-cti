"""What one side has seen of the other (#28).

A Contact says what was observed, never what the enemy is. These tests hold that
line from the inside: the register is handed sightings that carry no Squad id and
no enemy roster, so there is nothing for a leak to be made of, and what it
produces is a band rather than a count.
"""

from __future__ import annotations

from cti_daemon import contacts


def test_enemies_seen_at_one_place_become_one_contact_there() -> None:
    # One Contact per place, never per enemy Squad (CONTEXT.md, **Contact**).
    register = contacts.Contacts()
    register.report(
        "WEST",
        at_time=100.0,
        seen=tuple(contacts.Sighting(at="girna", kind="Infantry", age=0.0) for _ in range(5)),
        observed=("girna",),
    )

    (contact,) = register.aged_to("WEST", at_time=100.0)
    assert contact.at == "girna"
    assert contact.echelon == "squad"


def test_observing_a_place_and_finding_nobody_clears_its_contact() -> None:
    # Absence of contact is not evidence; observed absence is. The only removal
    # rule there is, and principled rather than tuned.
    register = contacts.Contacts()
    register.report(
        "WEST",
        at_time=100.0,
        seen=(contacts.Sighting(at="girna", kind="Infantry", age=0.0),),
        observed=("girna",),
    )
    register.report("WEST", at_time=160.0, seen=(), observed=("girna",))

    assert register.aged_to("WEST", at_time=160.0) == ()


def test_a_place_nobody_looked_at_keeps_its_contact_and_ages() -> None:
    # The engine's knowledge model resets to zero after 120 s without sight. A
    # Commander's picture must not: one that emptied every two minutes would
    # leave #16's scorer reacting to what is in someone's sights this instant.
    register = contacts.Contacts()
    register.report(
        "WEST",
        at_time=100.0,
        seen=(contacts.Sighting(at="girna", kind="Infantry", age=0.0),),
        observed=("girna",),
    )
    register.report(
        "WEST",
        at_time=400.0,
        seen=(contacts.Sighting(at="camp_maxwell", kind="Infantry", age=0.0),),
        observed=("camp_maxwell",),
    )

    aged = {contact.at: contact.age for contact in register.aged_to("WEST", at_time=400.0)}
    assert aged == {"girna": 300.0, "camp_maxwell": 0.0}


def west_saw(*kinds: str) -> contacts.Contact:
    """Return the one Contact WEST holds after seeing `kinds` at one place."""
    register = contacts.Contacts()
    register.report(
        "WEST",
        at_time=100.0,
        seen=tuple(contacts.Sighting(at="girna", kind=kind, age=0.0) for kind in kinds),
        observed=("girna",),
    )
    (contact,) = register.aged_to("WEST", at_time=100.0)
    return contact


def test_infantry_on_foot_is_reported_on_foot() -> None:
    assert west_saw("Infantry", "AT", "Medic").posture == "foot"


def test_posture_comes_from_the_heaviest_vehicle_seen() -> None:
    # Heaviest rather than most numerous: a squad that walked in with one truck
    # is motorised, and what a Commander needs to know is what the place can do.
    assert west_saw("Infantry", "Car").posture == "motorised"


def test_a_weapons_squads_teams_are_named_as_assets() -> None:
    # The MVP-exercisable half: `docs/mvp-scope.md` puts armour and air out of
    # scope entirely, so a weapons Squad's AT and MG are what the game can
    # actually produce.
    assert west_saw("Infantry", "AT", "MG", "Infantry").assets == ("AT", "MG")


def test_the_vehicle_vocabulary_is_defined_before_phase_4_can_exercise_it() -> None:
    # Unexercisable until Phase 4 adds vehicles (`docs/mvp-scope.md`), and
    # pinned here anyway so the schema #18's map UI renders does not churn when
    # it arrives. Said out loud rather than left to read as tested.
    assert west_saw("Tank", "Infantry").posture == "armoured"
    assert west_saw("Helicopter").posture == "air"
    assert west_saw("TrackedAPC").posture == "mechanised"
    assert west_saw("Tank", "TrackedAPC", "StaticWeapon", "Plane").assets == (
        "static",
        "IFV",
        "MBT",
        "air",
    )


def test_an_unrecognised_contact_is_honestly_unidentified() -> None:
    # `targetsQuery` returns perceived data and `BIS_fnc_objectType` classifies
    # the perceived type, so a thing nobody has made out reads as men on foot
    # carrying nothing notable rather than as a silently exact answer.
    unknown = west_saw("UnknownObject", "UnknownObject")
    assert unknown.posture == "foot"
    assert unknown.assets == ()
    assert unknown.echelon == "team"
