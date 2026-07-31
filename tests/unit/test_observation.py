"""The strategic picture a Commander plans against (#15), and only its own (#27).

Three things are pinned here. The observation carries what ADR-0008 calls
strategic and nothing it calls tactical, because a planner tested against a
closed schema has to be tested against the one that survives a resume. It
carries one side, because ADR-0012's Commander symmetry covers knowing as well
as commanding. And it fits inside one `callExtension` return, because the engine
truncates a longer one in silence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cti_daemon import campaign, economy, manifest, observation, port, protocol
from cti_daemon.commands import Command
from cti_daemon.outbox import Outbox

REPO = Path(__file__).parents[2]

SQUAD_VIEWS = st.builds(
    observation.SquadView,
    id=st.text(min_size=1, max_size=12),
    squad_type=st.text(min_size=1, max_size=12),
    size=st.integers(min_value=0, max_value=64),
    order=st.sampled_from(("capture", "defend", "reserve")),
    objective=st.text(max_size=24),
    at=st.text(max_size=24),
)
AT_TIMES = st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)
OWNERS = st.dictionaries(
    st.text(min_size=1, max_size=24),
    st.sampled_from(("WEST", "EAST", "NEUTRAL", "CONTESTED")),
    max_size=12,
)
OBSERVATIONS = st.one_of(
    st.builds(observation.Observation, at_time=AT_TIMES, owners=OWNERS),
    st.builds(
        observation.Observation,
        at_time=AT_TIMES,
        owners=OWNERS,
        for_side=st.sampled_from(("WEST", "EAST")),
        funds=st.integers(),
        squads=st.lists(SQUAD_VIEWS, max_size=12).map(tuple),
    ),
)


@given(OBSERVATIONS)
def test_an_observation_survives_the_wire_unchanged(
    original: observation.Observation,
) -> None:
    # It crosses a socket as JSON, so the round trip is tested through JSON
    # rather than through the dataclass alone.
    document = json.loads(json.dumps(observation.serialise(original)))
    assert observation.parse(document) == original


def live() -> campaign.Campaign:
    """Return a campaign on the authored Stratis map, everything Neutral."""
    table = economy.load(REPO / "config" / "economy.json")
    return campaign.Campaign(
        map_manifest=manifest.load(REPO / "manifests" / "stratis.json"),
        table=table,
        ledger=economy.Ledger(table.starting_funds),
        outbox=Outbox(),
    )


def test_an_observation_reports_every_objective_including_contested_ones() -> None:
    world = live()
    world.observe(30, {"agia_marina": ["WEST"], "girna": ["WEST", "EAST"]})
    owners = world.observation().owners
    assert owners["agia_marina"] == "WEST"
    assert owners["girna"] == "CONTESTED"
    assert len(owners) == len(world.map_manifest.objectives)


def test_an_observation_reports_each_squad_with_what_it_was_told_to_do() -> None:
    world = live()
    open_port = port.CommandPort(campaign=world)
    open_port.submit(Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST")
    open_port.submit(
        Command("order", "WEST", {"squad": "WEST-1", "order": "capture", "objective": "girna"}),
        acting_side="WEST",
    )
    world.roster.reconcile({"WEST-1": (6, "agia_marina")})

    (squad,) = world.observation("WEST").squads
    assert squad == observation.SquadView(
        id="WEST-1",
        squad_type="rifle",
        size=6,
        order="capture",
        objective="girna",
        at="agia_marina",
    )


def test_an_observation_carries_nothing_tactical() -> None:
    # ADR-0008 draws the line and #15 keeps to it: exact positions, health,
    # ammo and AI knowledge are regenerated, never reported.
    world = live()
    port.CommandPort(campaign=world).submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    document = observation.serialise(world.observation("WEST"))
    (squad,) = document["squads"]
    assert set(squad) == {"id", "type", "size", "order", "objective", "at"}


def test_a_squad_the_world_no_longer_holds_leaves_the_observation() -> None:
    world = live()
    open_port = port.CommandPort(campaign=world)
    for _ in range(2):
        open_port.submit(Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST")

    assert world.roster.reconcile({"WEST-2": (8, "")}) == ("WEST-1",)
    assert [squad.id for squad in world.observation("WEST").squads] == ["WEST-2"]


def contested() -> campaign.Campaign:
    """Return a campaign with both sides bought in and under standing Orders."""
    world = live()
    open_port = port.CommandPort(campaign=world)
    for side in ("WEST", "EAST"):
        open_port.submit(Command("purchase", side, {"squad_type": "rifle"}), acting_side=side)
        open_port.submit(
            Command(
                "order",
                side,
                {"squad": f"{side}-1", "order": "capture", "objective": "girna"},
            ),
            acting_side=side,
        )
    world.roster.reconcile({"WEST-1": (8, "agia_marina"), "EAST-1": (5, "girna")})
    return world


def test_a_commander_learns_nothing_of_the_enemys_order_of_battle() -> None:
    # #27, the whole point: not that the enemy happens to be absent from this
    # sample, but that the document a Commander holds says nothing about EAST
    # anywhere outside the ownership both sides are entitled to read.
    world = contested()
    west = world.observation("WEST")

    assert [squad.id for squad in west.squads] == ["WEST-1"]
    document = observation.serialise(west)
    private = {key: value for key, value in document.items() if key != "owners"}
    assert "EAST" not in json.dumps(private)


def test_enemy_funds_have_no_key_to_arrive_under() -> None:
    # Funds are one number rather than a table keyed by side, so a later change
    # cannot leak the enemy's by filling in a field that was already there.
    world = contested()
    world.ledger.deposit("EAST", 5_000)
    assert world.observation("WEST").funds == world.ledger.balance("WEST")


def test_the_public_picture_is_ownership_and_nothing_else() -> None:
    # What the server takes: enough to paint markers, and no side's view.
    world = contested()
    assert set(observation.serialise(world.observation())) == {"at", "owners"}


def test_a_picture_belonging_to_nobody_cannot_carry_somebodys_secrets() -> None:
    with pytest.raises(ValueError, match="public picture"):
        observation.Observation(at_time=0.0, owners={}, funds=300)


def test_a_side_that_is_not_playing_has_no_observation_to_take() -> None:
    # `Ledger.balance` mints a balance for any string, so a mistyped side would
    # otherwise come back with an invented fortune and an empty roster.
    with pytest.raises(ValueError, match="west"):
        live().observation("west")


def crowded() -> campaign.Campaign:
    """Return a Stratis fuller than the map can sensibly hold.

    Every Objective owned, and sixteen Squads a side — more than the Funds of a
    long Campaign would keep alive at once on an eight-Objective map. If the
    observation fits this, it fits Stratis.
    """
    world = live()
    world.ledger.deposit("WEST", 100_000)
    world.ledger.deposit("EAST", 100_000)
    open_port = port.CommandPort(campaign=world)
    for objective in world.map_manifest.objectives:
        world.observe(world.elapsed + 30, {objective.id: ["WEST"]})
    for side in ("WEST", "EAST"):
        for index in range(16):
            open_port.submit(Command("purchase", side, {"squad_type": "weapons"}), acting_side=side)
            open_port.submit(
                Command(
                    "order",
                    side,
                    {
                        "squad": f"{side}-{index + 1}",
                        "order": "capture" if side == "EAST" else "defend",
                        "objective": "camp_rogain",
                    },
                ),
                acting_side=side,
            )
    world.roster.reconcile(
        {
            squad.id: (8, "camp_rogain")
            for side in ("WEST", "EAST")
            for squad in world.roster.roll(side)
        }
    )
    return world


def test_a_crowded_stratis_observation_fits_inside_one_callextension_return() -> None:
    # The engine caps the return at 10,240 bytes and truncates in silence
    # (ADR-0004). Measured on the whole reply envelope, because that is what
    # actually crosses. Measured on a Commander's view rather than the server's
    # public one: the public picture is a dozen Objectives and stays small, so
    # the view that grows with the Campaign is the one worth watching, and #18
    # is what will put it on a wire.
    world = crowded()
    encoded = protocol.encode(
        protocol.accepted("obs-1", observation.serialise(world.observation("WEST")))
    )

    assert len(world.observation("WEST").squads) == 16
    assert len(encoded) < observation.RETURN_CAP_BYTES, (
        f"{len(encoded)} bytes leaves no headroom under {observation.RETURN_CAP_BYTES}"
    )
    # Recorded rather than merely asserted: the number is the headroom later
    # fields get to spend, and a bare "it fits" would hide it shrinking. #28's
    # Contacts are what spend it next.
    headroom = observation.RETURN_CAP_BYTES - len(encoded)
    assert headroom > 2_000, f"only {headroom} bytes of headroom left"
