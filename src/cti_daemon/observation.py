"""The strategic picture a Commander plans against.

An observation is the whole of what either Commander can reasonably know:
which side holds each Objective, what each side has to spend, and where its
Squads are and what they were told to do. It is deliberately the same set
ADR-0008 persists — strategic state, nothing tactical — so the Phase-2 snapshot
schema is this shape rather than a second one, and a planner tested against a
closed schema is tested against the one that survives a resume.

Excluded on purpose, not for want of a field: exact positions, health, ammo,
vehicle damage and AI knowledge. A Squad's position is the Objective or Base it
is standing on, because that is the resolution a Commander reasons at.

Assembled here rather than reported wholesale by the world: ownership, Funds and
Orders are the daemon's own (ADR-0012), and only the head count and the ground
underfoot are facts the world alone can see.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# What a `callExtension` return may carry in one call (ADR-0004). An observation
# that does not fit is an observation to make smaller, never a reason to invent
# a chunking protocol in passing — Phase 2 decides chunking against the snapshot
# schema's size profile.
RETURN_CAP_BYTES = 10_240


@dataclass(frozen=True, slots=True)
class SquadView:
    """One Squad as a Commander sees it."""

    id: str
    side: str
    squad_type: str
    size: int
    order: str
    objective: str
    # Where it is, to the nearest authored place: an Objective id, a Base id, or
    # empty for open ground between them.
    at: str


@dataclass(frozen=True, slots=True)
class Observation:
    """Everything strategic, at one in-game moment."""

    at_time: float
    owners: dict[str, str]
    funds: dict[str, int]
    squads: tuple[SquadView, ...]


def serialise(observation: Observation) -> dict[str, Any]:
    """Render an observation as the document that crosses the wire."""
    return {
        "at": observation.at_time,
        "owners": observation.owners,
        "funds": observation.funds,
        "squads": [
            {
                "id": squad.id,
                "side": squad.side,
                "type": squad.squad_type,
                "size": squad.size,
                "order": squad.order,
                "objective": squad.objective,
                "at": squad.at,
            }
            for squad in observation.squads
        ],
    }


def parse(document: dict[str, Any]) -> Observation:
    """Rebuild an observation from its wire document."""
    return Observation(
        at_time=document["at"],
        owners=dict(document["owners"]),
        funds=dict(document["funds"]),
        squads=tuple(
            SquadView(
                id=squad["id"],
                side=squad["side"],
                squad_type=squad["type"],
                size=squad["size"],
                order=squad["order"],
                objective=squad["objective"],
                at=squad["at"],
            )
            for squad in document["squads"]
        ),
    )
