"""The Command wire format both Commanders use.

ADR-0012: a Command is a domain payload carried inside the #10 transport
envelope, not the envelope itself. These tests pin the payload shape, because
the human UI and the AI planner both build it and neither may drift.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cti_daemon import campaign, commands, manifest


def test_a_purchase_command_parses_into_its_parts() -> None:
    command = commands.parse(
        {"command": "purchase", "side": "WEST", "args": {"squad_type": "rifle"}}
    )
    assert (command.name, command.side, command.args) == (
        "purchase",
        "WEST",
        {"squad_type": "rifle"},
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("purchase", id="a bare string is not a Command"),
        pytest.param([], id="a list is not a Command"),
        pytest.param({"side": "WEST"}, id="no command name"),
        pytest.param({"command": "", "side": "WEST"}, id="an empty command name"),
        pytest.param({"command": 7, "side": "WEST"}, id="a command name that is not a string"),
        pytest.param({"command": "purchase"}, id="no side"),
        pytest.param({"command": "purchase", "side": "GUER"}, id="a side nobody commands"),
        pytest.param(
            {"command": "purchase", "side": "west"}, id="engine side names are upper case"
        ),
        pytest.param(
            {"command": "purchase", "side": "WEST", "args": 3}, id="args that are not an object"
        ),
    ],
)
def test_a_payload_that_is_not_a_command_is_refused(payload: object) -> None:
    # ADR-0012: a malformed *command* is a rejection, not an error — the caller
    # is at fault, not our transport. The port turns this into that rejection.
    with pytest.raises(commands.MalformedCommandError):
        commands.parse(payload)


def test_an_absent_args_object_is_an_empty_one() -> None:
    # A Command with no arguments is ordinary; requiring `args: {}` would make
    # every hand-built SQF Command carry an empty object for nothing.
    assert commands.parse({"command": "purchase", "side": "EAST"}).args == {}


LEAVES = (
    st.none()
    | st.booleans()
    | st.integers()
    | st.text()
    | st.floats(allow_nan=False, allow_infinity=False)
)
JSON_VALUES = st.recursive(
    LEAVES,
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(), children, max_size=4)
    ),
    max_leaves=8,
)
ARGS = st.dictionaries(st.text(min_size=1), JSON_VALUES, max_size=4)
NAMES = st.text(min_size=1)


@given(name=NAMES, side=st.sampled_from(commands.SIDES), args=ARGS)
def test_a_command_survives_the_wire_unchanged(name: str, side: str, args: dict[str, Any]) -> None:
    # The payload crosses a socket as JSON, so the round trip is tested through
    # JSON rather than through the dataclass alone.
    command = commands.Command(name=name, side=side, args=args)
    restored = commands.parse(json.loads(json.dumps(commands.serialise(command))))
    assert restored == command


@given(name=NAMES, side=st.sampled_from(commands.SIDES), args=ARGS)
def test_an_effect_survives_the_wire_unchanged(name: str, side: str, args: dict[str, Any]) -> None:
    effect = commands.Effect(name=name, side=side, args=args)
    restored = commands.parse_effect(json.loads(json.dumps(commands.serialise_effect(effect))))
    assert restored == effect


def test_a_command_and_an_effect_are_not_the_same_payload() -> None:
    # They share a schema source but not a key, so a Command can never be
    # mistaken for an instruction to mutate the world (ADR-0012).
    command = commands.serialise(commands.Command("purchase", "WEST", {}))
    effect = commands.serialise_effect(commands.Effect("squad_spawned", "WEST", {}))
    assert "command" in command
    assert "command" not in effect
    assert "effect" in effect
    assert "effect" not in command


def test_an_effect_may_concern_ground_no_side_holds() -> None:
    # A Command is issued *by* a side, so it takes a side. An Effect reports
    # what happened, and an Objective going Contested is a real thing to report.
    for owner in ("NEUTRAL", "CONTESTED"):
        effect = commands.parse_effect({"effect": "objective_captured", "side": owner})
        assert effect.side == owner


def test_a_command_still_may_not_claim_a_state_as_its_side() -> None:
    with pytest.raises(commands.MalformedCommandError):
        commands.parse({"command": "purchase", "side": "CONTESTED"})


def test_every_module_that_speaks_of_sides_speaks_of_the_same_ones() -> None:
    # One definition, not copies held in step by a comment (#65). Identity
    # rather than equality: an equal tuple declared elsewhere is the thing this
    # test exists to catch coming back.
    assert manifest.SIDES is commands.SIDES
    assert campaign.NEUTRAL is commands.NEUTRAL
    assert campaign.CONTESTED is commands.CONTESTED
    assert set(commands.OWNERS) == {*commands.SIDES, commands.NEUTRAL, commands.CONTESTED}
