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
    # Where the world last saw it, to the nearest authored place: an Objective
    # id, a Base id, or empty for the open ground between them. Coarse on
    # purpose — a Commander reasons about places, not coordinates (ADR-0008).
    at: str = ""


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

    def roll(self, side: str) -> tuple[Squad, ...]:
        """One side's Squads, in the order they were bought.

        A side rather than the whole map, for the reason `of` takes one: there
        is no call that hands out the enemy's order of battle, so an in-process
        planner cannot read it even by accident (#27).
        """
        return tuple(squad for squad in self._squads.values() if squad.side == side)

    def reconcile(self, seen: dict[str, tuple[int, str]]) -> tuple[str, ...]:
        """Take the world's account of which Squads exist, and where.

        Head count and ground underfoot are facts only the world can see, and
        existence is one of them: a Squad the world no longer holds has been
        wiped out. Returns the ids that were lost, so a Squad leaving the
        campaign is something the caller can report rather than something that
        silently stops appearing.
        """
        lost = tuple(squad_id for squad_id in self._squads if squad_id not in seen)
        for squad_id in lost:
            del self._squads[squad_id]
        for squad_id, (size, at) in seen.items():
            squad = self._squads.get(squad_id)
            if squad is not None:
                squad.size = size
                squad.at = at
        return lost
