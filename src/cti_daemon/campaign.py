"""Who owns what, and what that pays.

The world reports who is standing where; this decides what it means. The split
follows ADR-0012 — presence is a fact only the game can observe, ownership and
Funds are rules, and rules live in the daemon where they are testable.

Time is an argument rather than a clock reading. The unit is in-game seconds,
which stop when the Play Session does, so income accrues only while a session is
live without anything here having to know what a session is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from cti_daemon.commands import SIDES, Effect, serialise_effect
from cti_daemon.squads import Roster

if TYPE_CHECKING:
    from cti_daemon.economy import EconomyTable, Ledger
    from cti_daemon.manifest import MapManifest
    from cti_daemon.outbox import Outbox

NEUTRAL: Final = "NEUTRAL"
CONTESTED: Final = "CONTESTED"


@dataclass(slots=True)
class ObjectiveState:
    """One Objective's owner, and any capture in progress on it."""

    owner: str = NEUTRAL
    # The side currently accumulating a hold, and how long it has held. Reset
    # whenever the ground changes hands or is contested.
    holder: str = ""
    held_seconds: float = 0.0


@dataclass(slots=True)
class Campaign:
    """The strategic state of one playthrough: ownership and Funds."""

    map_manifest: MapManifest
    table: EconomyTable
    ledger: Ledger
    outbox: Outbox
    # The Squads each side has bought and what each has been told to do (#14).
    # Ownership, Funds and Squads are one playthrough's strategic state, so they
    # sit behind one object rather than three the caller has to keep in step.
    roster: Roster = field(default_factory=Roster)
    elapsed: float = 0.0
    _states: dict[str, ObjectiveState] = field(default_factory=dict)
    _since_payout: float = 0.0

    def __post_init__(self) -> None:
        """Start every Objective Neutral, as the manifest authored them."""
        self._states = {
            objective.id: ObjectiveState() for objective in self.map_manifest.objectives
        }

    def owner(self, objective: str) -> str:
        """Who holds `objective` — a side, Neutral, or Contested."""
        return self._states[objective].owner

    def holds(self, objective: str) -> str | None:
        """Who holds `objective`, or None when this map has no such Objective.

        The forgiving reading of `owner`, for validating a Command that names
        ground: an Objective nobody authored is a Commander's mistake to be
        told about, not an exception to escape the port.
        """
        state = self._states.get(objective)
        return None if state is None else state.owner

    def owners(self) -> dict[str, str]:
        """Every Objective's owner, for a Commander to reason over."""
        return {name: state.owner for name, state in self._states.items()}

    def funds(self) -> dict[str, int]:
        """Return what each side holds, for a Commander and for the UI."""
        return {side: self.ledger.balance(side) for side in SIDES}

    def observe(self, at_time: float, presence: dict[str, list[str]]) -> list[dict[str, int]]:
        """Take one report of who is standing where, at an in-game time.

        `presence` maps Objective id to the sides inside its capture radius.
        An Objective the report omits is treated as empty, which is what an
        empty radius looks like from the world.

        Returns one entry per income tick the elapsed time covered, so a caller
        can record that Funds moved. Paying in silence would leave the economy
        the one part of the campaign nobody can watch.
        """
        # In-game time restarts at zero when the mission does. A negative
        # interval would claw back Funds already paid, so a step backwards is a
        # new session rather than a refund.
        interval = at_time - self.elapsed
        if interval < 0:
            interval = 0.0
        self.elapsed = at_time

        for name, state in self._states.items():
            self._advance(name, state, presence.get(name, []), interval)

        return self._accrue(interval)

    def _advance(self, name: str, state: ObjectiveState, sides: list[str], interval: float) -> None:
        """Move one Objective's capture on by `interval` seconds."""
        present = sorted({side for side in sides if side in SIDES})

        if len(present) > 1:
            # Contested is a state, not a moment: it persists until somebody is
            # alone in the radius again, and it pays nobody while it lasts.
            self._set_owner(name, state, CONTESTED)
            state.holder = ""
            state.held_seconds = 0.0
            return

        if not present:
            # Ground already taken stays taken; holding it should not require
            # standing on it forever.
            state.holder = ""
            state.held_seconds = 0.0
            return

        side = present[0]
        if state.owner == side:
            state.holder = ""
            state.held_seconds = 0.0
            return

        if state.holder != side:
            state.holder = side
            state.held_seconds = 0.0
        state.held_seconds += interval

        if state.held_seconds >= self.table.capture_seconds:
            self._set_owner(name, state, side)
            state.holder = ""
            state.held_seconds = 0.0

    def _set_owner(self, name: str, state: ObjectiveState, owner: str) -> None:
        """Record a change of hands and tell the world about it."""
        if state.owner == owner:
            return
        state.owner = owner
        self.outbox.push(
            serialise_effect(
                Effect(name="objective_captured", side=owner, args={"objective": name})
            )
        )

    def _accrue(self, interval: float) -> list[dict[str, int]]:
        """Pay every income tick the elapsed time covers."""
        paid: list[dict[str, int]] = []
        self._since_payout += interval
        tick = self.table.income_tick_seconds
        while self._since_payout >= tick:
            self._since_payout -= tick
            paid.append(self._pay())
        return paid

    def _pay(self) -> dict[str, int]:
        """One tick: the sum over owned Objectives, plus the flat stipend."""
        income = dict.fromkeys(SIDES, self.table.stipend)
        for objective in self.map_manifest.objectives:
            owner = self._states[objective.id].owner
            # Neutral and Contested Objectives pay nobody.
            if owner in income:
                income[owner] += objective.income
        for side, amount in income.items():
            self.ledger.deposit(side, amount)
        return income
