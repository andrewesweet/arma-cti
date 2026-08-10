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
    """One roster Squad: who owns it, what it is, and what it has been told.

    Most of them are bought. One per side need not be: the player who takes the
    squad-leader role gets a dedicated roster Squad at own Base with himself as
    its sole member, composition-unassigned until the Commander's first fill
    (ADR-0070, CONTEXT.md's amended **Squad**). The three fields below are the
    whole of what such a shell is, and they are on `Squad` rather than on a
    subclass because a shell is a *state* of a Squad and not a second noun —
    which is the ADR's own reason for minting no new term.
    """

    id: str
    side: str
    squad_type: str
    size: int
    order: Order = RESERVE
    # Which player leads it, by UID, and empty for an ordinary bought Squad.
    # UID rather than unit or machine id, for ADR-0025's reason: respawn hands
    # the player a new unit and reconnection a new machine id, and neither is a
    # change of who is leading.
    player_uid: str = ""
    # Whether the authored table's composition has been assigned to it. True for
    # every Squad that was bought, because a Purchase names the type it is
    # buying; False only for a shell nobody has filled yet.
    #
    # A flag rather than an empty `squad_type` doing double duty, and that is
    # fixed rather than a preference (ADR-0070): `Campaign.missing` answers 0
    # both for an unassigned shell and for a Squad whose type the table has
    # stopped selling, and the port types the second `malformed_command`. Were
    # the two the same state, the first refusal a player meets would be a lie
    # about the economy table.
    composition_assigned: bool = True
    # Whether the shell's player has disconnected before its first fill
    # (ADR-0070 ruling 7). Defined only for a composition-unassigned Squad: a
    # filled Squad survives disconnect under an engine-selected AI leader
    # (ruling 5), which is what keeps the two rulings from contradicting each
    # other. A suspended shell keeps its roster identity and its minted id,
    # contributes no presence, and is ineligible for filling.
    suspended: bool = False
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
        squad = self._mint(side, squad_type=squad_type, size=size)
        self._squads[squad.id] = squad
        return squad

    def enrol(self, side: str, player_uid: str) -> Squad:
        """Mint the shell a player squad leader leads: no composition, no price.

        The same id counter `add` takes, deliberately (ADR-0003): a shell is a
        roster Squad in every respect the roster cares about, so a resumed
        Campaign that enrolled a player before buying a Squad has to mint the
        same two ids in the same order it did the first time.

        One member — the player — and no composition until the Commander's first
        fill assigns one (ADR-0070 ruling 1). Nothing is charged here, because
        there is nothing to charge for: the shell is not a Purchase, and the
        side pays only when the composition arrives (ruling 3).
        """
        squad = self._mint(side, squad_type="", size=1)
        squad.player_uid = player_uid
        squad.composition_assigned = False
        self._squads[squad.id] = squad
        return squad

    def _mint(self, side: str, *, squad_type: str, size: int) -> Squad:
        """Take the next id for that side and build the Squad wearing it."""
        minted = self._minted.get(side, 0) + 1
        self._minted[side] = minted
        return Squad(id=f"{side}-{minted}", side=side, squad_type=squad_type, size=size)

    def led_by(self, player_uid: str) -> Squad | None:
        """Return the Squad that player leads, or None if he leads none.

        By UID across both sides, which is not the order-of-battle read `all`
        is: a player is on one side, so this can answer at most one Squad and
        cannot be walked to enumerate anybody's roster (#27). The lookup exists
        because the claim that reaches the daemon is a player UID (ADR-0025) and
        the roster is what knows whether that player already has a Squad — a
        reconnecting player's shell has to be found again rather than minted
        twice.
        """
        if not player_uid:
            return None
        for squad in self._squads.values():
            if squad.player_uid == player_uid:
                return squad
        return None

    def active_shells(self) -> tuple[Squad, ...]:
        """Every composition-unassigned Squad a player is currently leading.

        The set a report suspends from when it stops naming that player
        (ADR-0070 ruling 7). Derived rather than remembered, so it answers the
        same after a daemon restart as before one: what makes a Squad a live
        shell is `player_uid`, `composition_assigned` and `suspended`, and the
        snapshot carries all three.

        A filled Squad is never in it, which is ruling 5 rather than an
        optimisation — it survives its player's disconnect under an
        engine-selected AI leader and keeps its Order, so there is nothing here
        for a departure to do to it.
        """
        return tuple(
            squad
            for squad in self._squads.values()
            if squad.player_uid and not squad.composition_assigned and not squad.suspended
        )

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

        And a Squad with no living members *by construction* is not one it has
        lost either (ADR-0070, found before it was built). `fn_squadSample`
        counts `{alive _x} count units _group` and omits a Squad at zero, which
        a composition-unassigned shell reaches without anything having gone
        wrong: suspended it has no members at all, and active its only member is
        the player — whose death is a certainty, made a thirty-second certainty
        by ADR-0052, with #189 measuring that no AI is promoted and the corpse
        holds the seat for the whole window. A *filled* Squad has AI members and
        meets the rule only when it really has been wiped out, so the exemption
        is exactly the unassigned ones and nothing wider.
        """
        lost = tuple(
            squad_id
            for squad_id, squad in self._squads.items()
            if squad_id not in seen and squad.fielded and squad.composition_assigned
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
