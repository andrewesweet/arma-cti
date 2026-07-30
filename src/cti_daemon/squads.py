"""Squads, and the standing Orders they carry.

An Order is standing rather than a waypoint consumed and forgotten (#14): it
outlives the leader who received it, whether that leader was killed and replaced
by engine AI or was a player who respawned. That makes an Order *state*, and
state the world is driven from belongs in the daemon where it is testable — the
same split ADR-0012 draws for ownership and Funds.

The world holds the geometry: this names an Objective, never a position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# What a Commander may tell a Squad to do.
ORDERS: Final = ("capture", "defend", "reserve")

# The two that name ground. Reserve is the absence of a destination rather than
# a destination of its own, so it carries no Objective and refuses one.
NEEDS_OBJECTIVE: Final = ("capture", "defend")


@dataclass(frozen=True, slots=True)
class Order:
    """One standing instruction to one Squad."""

    kind: str
    objective: str = ""


# What a Squad does until told otherwise. A Squad that has just been bought is
# standing at its own Base, which is exactly what Reserve means.
RESERVE: Final = Order("reserve")


@dataclass(slots=True)
class Squad:
    """One bought Squad: who owns it, what it is, and what it has been told."""

    id: str
    side: str
    squad_type: str
    size: int
    order: Order = RESERVE


@dataclass(slots=True)
class Roster:
    """Every Squad each side has bought, and what each is currently doing."""

    _squads: dict[str, Squad] = field(default_factory=dict)
    _minted: dict[str, int] = field(default_factory=dict)

    def add(self, side: str, squad_type: str, size: int) -> Squad:
        """Mint a Squad with an id stable enough to order and to snapshot.

        The id counts up per side rather than coming from a clock or a random
        source: a resumed campaign has to mint the same ids in the same order
        (ADR-0003), and a Commander has to be able to say one out loud.
        """
        minted = self._minted.get(side, 0) + 1
        self._minted[side] = minted
        squad = Squad(id=f"{side}-{minted}", side=side, squad_type=squad_type, size=size)
        self._squads[squad.id] = squad
        return squad

    def of(self, squad_id: str, side: str) -> Squad | None:
        """Return `side`'s Squad by that id, or None if it has no such Squad.

        Another side's Squad is not found rather than refused separately: a
        Commander has no business learning which Squads the enemy has bought by
        guessing at ids.
        """
        squad = self._squads.get(squad_id)
        if squad is None or squad.side != side:
            return None
        return squad

    def roll(self) -> tuple[Squad, ...]:
        """Every Squad on the map, in the order they were bought."""
        return tuple(self._squads.values())
