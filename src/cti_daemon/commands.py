"""The Command Port's wire format: Commands in, effects out.

ADR-0012 makes this module the single schema source. The daemon is the sole
validator, the AI planner builds these objects in-process rather than crossing
the wire, and the SQF constructors the human UI uses are generated from here —
so "one wire format for human and AI" is a property of the code rather than a
convention anyone has to remember.

A Command is a domain payload carried inside the #10 transport envelope, never
the envelope itself: transport verbs (`ping`, `poll`, `ack`) and Commands do
not share a namespace.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, cast

# Engine side names, matching manifest.SIDES, so SQF needs no translation table.
SIDES: Final = ("WEST", "EAST")

# What an Objective's owner can be. A Command is always *issued by* a side, so
# it takes SIDES; an Effect reports something that may concern ground no side
# holds, so it takes these. Contested is a real state, not a transient (#13).
OWNERS: Final = (*SIDES, "NEUTRAL", "CONTESTED")

# The Command catalogue: name -> the argument names it requires. This is the
# source the SQF constructors are generated from, so a Command the game can
# build and a Command the daemon accepts cannot drift apart.
CATALOGUE: Final[dict[str, tuple[str, ...]]] = {
    "purchase": ("squad_type",),
    # Reserve names no ground, but it travels in the same shape as the others
    # rather than in a second one: a constructor with a fixed argument list is
    # a constructor SQF cannot build wrong. The ground field is `place` because
    # it can hold an Objective id or a Base id (ADR-0020).
    "order": ("squad", "order", "place"),
}

# The effects a Command can produce, and the arguments each carries. An
# Objective changing hands is one of them even though no Command asks for it —
# the campaign's own rules push it, and the game applies it the same way.
EFFECTS: Final[dict[str, tuple[str, ...]]] = {
    "squad_spawned": ("squad", "squad_type", "size"),
    "order_issued": ("squad", "order", "place"),
    "objective_captured": ("objective",),
    # The last effect any Campaign produces (#35): which condition ended it, the
    # in-game moment it ended, and the telemetry-sourced summary the end screen
    # is drawn from. `side` is the winner, as it is the owner on a capture.
    "campaign_won": ("condition", "at", "summary"),
}


@dataclass(frozen=True, slots=True)
class Command:
    """One Commander instruction, in the format both Commanders use."""

    name: str
    side: str
    args: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Effect:
    """One world change the daemon has accepted and the game must carry out.

    Effects ride the outbox rather than a Command's reply, so an AI-issued
    effect and a human-issued one travel the same path and #19 has one path to
    audit (ADR-0012). A Command's reply is a judgement; an Effect is the work.
    """

    name: str
    side: str
    args: dict[str, Any]


class MalformedCommandError(Exception):
    """The payload is not a Command.

    A *rejection*, not an error: the caller sent something the rules refuse,
    which is a different fault from our own transport failing to parse a line
    (ADR-0012, and the envelope's `malformed_request` stays an error).
    """


def _side_and_args(
    payload: dict[str, Any], allowed: tuple[str, ...] = SIDES
) -> tuple[str, dict[str, Any]]:
    """Validate the two fields every payload in this format carries."""
    side = payload.get("side")
    if side not in allowed:
        detail = f"`side` must be one of {list(allowed)}, got {side!r}"
        raise MalformedCommandError(detail)

    args = payload.get("args", {})
    if not isinstance(args, dict):
        detail = f"`args` must be an object, got {type(args).__name__}"
        raise MalformedCommandError(detail)

    return side, args


def _named(payload: object, key: str, what: str) -> tuple[str, dict[str, Any]]:
    """Validate the envelope shape shared by Commands and Effects."""
    if not isinstance(payload, dict):
        detail = f"{what} must be an object, got {type(payload).__name__}"
        raise MalformedCommandError(detail)
    # Checked above; the fields it must carry are checked by the callers.
    envelope = cast("dict[str, Any]", payload)

    name = envelope.get(key)
    if not isinstance(name, str) or not name:
        detail = f"`{key}` must be a non-empty string, got {name!r}"
        raise MalformedCommandError(detail)

    return name, envelope


def parse(payload: object) -> Command:
    """Build a Command from a decoded envelope payload, or refuse it."""
    name, envelope = _named(payload, "command", "a Command")
    side, args = _side_and_args(envelope)
    return Command(name=name, side=side, args=args)


def serialise(command: Command) -> dict[str, Any]:
    """Render a Command as the envelope payload that crosses the wire."""
    return {"command": command.name, "side": command.side, "args": command.args}


def parse_effect(payload: object) -> Effect:
    """Build an Effect from a pushed outbox message, or refuse it."""
    name, envelope = _named(payload, "effect", "an Effect")
    side, args = _side_and_args(envelope, OWNERS)
    return Effect(name=name, side=side, args=args)


def serialise_effect(effect: Effect) -> dict[str, Any]:
    """Render an Effect as the outbox message that crosses the wire."""
    return {"effect": effect.name, "side": effect.side, "args": effect.args}
