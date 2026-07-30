"""The strategic picture a Commander plans against (#15).

Two things are pinned here. The observation carries what ADR-0008 calls
strategic and nothing it calls tactical, because a planner tested against a
closed schema has to be tested against the one that survives a resume. And it
fits inside one `callExtension` return, because the engine truncates a longer
one in silence.
"""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from cti_daemon import campaign, economy, manifest, observation, port, protocol
from cti_daemon.commands import Command
from cti_daemon.outbox import Outbox

REPO = Path(__file__).parents[2]

SQUAD_VIEWS = st.builds(
    observation.SquadView,
    id=st.text(min_size=1, max_size=12),
    side=st.sampled_from(("WEST", "EAST")),
    squad_type=st.text(min_size=1, max_size=12),
    size=st.integers(min_value=0, max_value=64),
    order=st.sampled_from(("capture", "defend", "reserve")),
    objective=st.text(max_size=24),
    at=st.text(max_size=24),
)
OBSERVATIONS = st.builds(
    observation.Observation,
    at_time=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    owners=st.dictionaries(
        st.text(min_size=1, max_size=24),
        st.sampled_from(("WEST", "EAST", "NEUTRAL", "CONTESTED")),
        max_size=12,
    ),
    funds=st.dictionaries(st.sampled_from(("WEST", "EAST")), st.integers(), max_size=2),
    squads=st.lists(SQUAD_VIEWS, max_size=12).map(tuple),
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

    (squad,) = world.observation().squads
    assert squad == observation.SquadView(
        id="WEST-1",
        side="WEST",
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
    document = observation.serialise(world.observation())
    (squad,) = document["squads"]
    assert set(squad) == {"id", "side", "type", "size", "order", "objective", "at"}


def test_a_squad_the_world_no_longer_holds_leaves_the_observation() -> None:
    world = live()
    open_port = port.CommandPort(campaign=world)
    for _ in range(2):
        open_port.submit(Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST")

    assert world.roster.reconcile({"WEST-2": (8, "")}) == ("WEST-1",)
    assert [squad.id for squad in world.observation().squads] == ["WEST-2"]


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
    world.roster.reconcile({squad.id: (8, "camp_rogain") for squad in world.roster.roll()})
    return world


def test_a_crowded_stratis_observation_fits_inside_one_callextension_return() -> None:
    # The engine caps the return at 10,240 bytes and truncates in silence
    # (ADR-0004). Measured on the whole reply envelope, because that is what
    # actually crosses.
    world = crowded()
    document = observation.serialise(world.observation())
    document["paid"] = []
    document["lost"] = []
    encoded = protocol.encode(protocol.accepted("obs-1", document))

    assert len(world.observation().squads) == 32
    assert len(encoded) < observation.RETURN_CAP_BYTES, (
        f"{len(encoded)} bytes leaves no headroom under {observation.RETURN_CAP_BYTES}"
    )
    # Recorded rather than merely asserted: the number is the headroom later
    # fields get to spend, and a bare "it fits" would hide it shrinking.
    headroom = observation.RETURN_CAP_BYTES - len(encoded)
    assert headroom > 2_000, f"only {headroom} bytes of headroom left"
