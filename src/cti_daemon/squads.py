"""Squads, and the standing Orders they carry.

An Order is standing rather than a waypoint consumed and forgotten (#14): it
outlives the leader who received it, whether that leader was killed and replaced
by engine AI or was a player who respawned. That makes an Order *state*, and
state the world is driven from belongs in the daemon where it is testable — the
same split ADR-0012 draws for ownership and Funds.

The world holds the geometry: this names a Place — an Objective or a Base by
its manifest id (ADR-0020) — never a position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, NamedTuple

# What a Commander may tell a Squad to do. Assault is Decapitation as an Order
# (ADR-0020): close with the enemy Base and destroy its HQ structure.
ORDERS: Final = ("capture", "defend", "assault", "reserve")

# The three that name ground. Reserve is the absence of a destination rather
# than a destination of its own, so it carries no Place and refuses one. Which
# Places each of the three may name is the port's rule, not this list's.
NEEDS_PLACE: Final = ("capture", "defend", "assault")


class Held(NamedTuple):
    """What the world can see of one Squad: how many men, and where.

    Named rather than an anonymous `(int, str)` pair (#90) — the facts a report
    carries per Squad are the ones the world alone can observe, and a tuple
    whose members have to be remembered positionally is one transposition away
    from a Squad standing at "8".

    `where` is now two answers rather than one (#175, ADR-0058): the Place it is
    standing in, and the map position it is standing at. The Place is the
    coarse one an Order names and can honestly be empty; the position is where
    it actually is, in whole metres, and is empty only for a Squad no report has
    ever held.
    """

    size: int
    at: str
    # `()` for a Squad the world has not reported. Defaulted for the reason
    # `Squad.at` is: a caller saying "the world holds eight men at Girna" is
    # making a claim about the head count and the ground, and a coordinate it
    # does not care about would be noise it had to invent.
    pos: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class Order:
    """One standing instruction to one Squad."""

    kind: str
    # The Place it names: an Objective id, a Base id, or empty for Reserve.
    place: str = ""


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
    # And where that was on the map, in whole metres (#175, ADR-0058). Beside
    # `at` rather than instead of it: `at` is what an Order names and what the
    # planner reasons in, and this is only what a marker is drawn at. Empty
    # until the world has reported this Squad standing at all, which is the same
    # moment `fielded` turns true.
    pos: tuple[int, ...] = ()
    # Whether the world has ever reported it standing. A Squad is bought here
    # and spawned there, so a report taken in between says nothing about it.
    fielded: bool = False


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

    def owned_by(self, squad_id: str, side: str) -> Squad | None:
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

        A side rather than the whole map, for the reason `owned_by` takes one: there
        is no call that hands out the enemy's order of battle, so an in-process
        planner cannot read it even by accident (#27).
        """
        return tuple(squad for squad in self._squads.values() if squad.side == side)

    def all(self) -> tuple[Squad, ...]:
        """Every Squad both sides hold, in the order they were bought.

        The snapshot's view of the roster (ADR-0008, #291): both sides in one
        document, in buy order, which is what makes a round trip put a Squad back
        where the save found it. Named apart from `roll` because a snapshot is the
        one caller entitled to both sides' order of battle at once — a view never
        is (#27), and a planner reaches the roster only through its own side.
        """
        return tuple(self._squads.values())

    def restore(self, squads: tuple[Squad, ...]) -> None:
        """Rebuild the roster from a saved record, ids and mint counter intact.

        A resumed Campaign has to mint the same ids in the same order (ADR-0003):
        the ids the snapshot carried are put back exactly, and `_minted` is set so
        the next Purchase continues the count rather than colliding with a Squad
        the save already holds. The mint counter is read off the id suffix a
        `Roster.add` writes, so a save from this codebase round-trips; an id that
        does not carry one leaves that side's counter at the number of Squads it
        holds, which is the safe lower bound for the next mint.
        """
        rebuilt: dict[str, Squad] = {}
        counts: dict[str, int] = {}
        for squad in squads:
            rebuilt[squad.id] = squad
            counts[squad.side] = counts.get(squad.side, 0) + 1
        self._squads = rebuilt
        # The highest id suffix per side, so the next mint does not reuse a live
        # id. Falls back to the count for an id `add` did not shape.
        minted: dict[str, int] = {}
        for side, count in counts.items():
            highest = 0
            for squad in rebuilt.values():
                if squad.side != side:
                    continue
                prefix = f"{side}-"
                if squad.id.startswith(prefix):
                    rest = squad.id.removeprefix(prefix)
                    if rest.isdigit():
                        highest = max(highest, int(rest))
            minted[side] = highest or count
        self._minted = minted

    def reconcile(self, seen: dict[str, Held]) -> tuple[str, ...]:
        """Take the world's account of which Squads exist, and where.

        Head count and ground underfoot are facts only the world can see, and
        existence is one of them: a Squad the world no longer holds has been
        wiped out. Returns the ids that were lost, so a Squad leaving the
        campaign is something the caller can report rather than something that
        silently stops appearing.

        A Squad the world has never held is not one it has lost. A Purchase is
        judged here and carried out there, so a report taken between the two is
        silent about a Squad that is on its way — and deleting it on that
        silence leaves the group that arrives answering to an id the roster no
        longer knows: a Squad nobody can order and nobody counts.
        """
        lost = tuple(
            squad_id
            for squad_id, squad in self._squads.items()
            if squad_id not in seen and squad.fielded
        )
        for squad_id in lost:
            del self._squads[squad_id]
        for squad_id, held in seen.items():
            squad = self._squads.get(squad_id)
            if squad is not None:
                squad.size = held.size
                squad.at = held.at
                squad.pos = held.pos
                squad.fielded = True
        return lost
