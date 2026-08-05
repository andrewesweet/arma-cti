"""The free transport a Squad is issued, as authored (#170).

The human's ruling of 2026-08-03 puts a free ride in the MVP: "squad leaders (or
AI commander on behalf of squad leaders) should be able to access the weakest,
most basic form of motorised transport sufficient for their squad size for free
at all times". ADR-0059 records the shape; this is its daemon half.

Named `motorpool` rather than `transport` because `cti_daemon.transport` is
already the TCP wire, and two modules called transport in one package is one
import away from a bad afternoon. The domain word stays the human's own —
motorised transport — and this is the place one is issued from.

**Nothing here runs during a Campaign.** The truck costs no Funds, is judged by
no rule and changes no roster, so it is world-side in its entirety (ADR-0012):
no Command, no Effect, no Observation field, no snapshot field. What the daemon
owns is the one fact the world cannot check for itself — that the authored menu
seats the Squads the authored economy sells. `config/economy.json` owns a
Squad's size (#159) and this document owns how many a vehicle carries, and a
menu whose largest vehicle seats seven would be a Squad walking to Agia Marina
with one man left behind, discovered in a Play Session. `capacity_covers` is
that check, and `just unit` is where it fires.

The document is `addons/main/catalogue/transport.json`, ADR-0056's pattern: one
authored file, shipped in the PBO where `loadFile` can reach it and read by the
addon that issues the vehicle, validated in Python over the same bytes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.economy import EconomyTable

SCHEMA_VERSION: Final = 1


class MotorpoolError(Exception):
    """The authored transport menu is not one we can play with."""


def _refuse(detail: str) -> NoReturn:
    """Raise the one error type callers catch. See `manifest._refuse` on why two."""
    raise MotorpoolError(detail)


def _required(document: dict[str, Any], key: str, what: str) -> Any:  # noqa: ANN401 — the value
    # is whatever the document held; every caller checks its type next.
    """Return an authored key, or refuse the document for not having it."""
    if key not in document:
        _refuse(f"{what} must carry {key!r}")
    return document[key]


@dataclass(frozen=True, slots=True)
class Transport:
    """One row of the menu: a vehicle, and how many men it carries.

    One classname rather than one per side, which is where this parts company
    with `loadouts.Kit` and `economy.SquadType`. Those are men, and a side's men
    wear its own faction's classnames; this is a civilian truck, which belongs
    to no faction in vanilla Arma — the human's "a civilian open truck perhaps?"
    is what makes the row side-neutral, and a row that varied by side would be
    inventing a distinction the ruling does not have.

    `seats` is authored rather than read off the engine because the check this
    module exists for has to run without Arma. The world asserts the authored
    number against the vehicle it actually spawned, and a disagreement there is
    `engine_drift` rather than a bug of ours.
    """

    id: str
    display_name: str
    seats: int
    vehicle: str


@dataclass(frozen=True, slots=True)
class Motorpool:
    """The whole menu, weakest first — which is the order it is issued from.

    Authored order *is* the doctrine. "The weakest, most basic form of motorised
    transport sufficient for their squad size" is a first-match rule over an
    escalation, and putting the escalation in the file rather than deriving it
    from `seats` keeps it a design decision: two vehicles that seat the same
    number are not equally basic, and nothing in the numbers says which is.
    """

    fleet: tuple[Transport, ...]

    @classmethod
    def empty(cls) -> Motorpool:
        """Return a menu with nothing on it, for a Campaign wired without one.

        Not a document anybody may author — `parse` refuses an empty `fleet` —
        but the honest default for a caller that is not about transport: no
        vehicle is issued, rather than the first one to hand.
        """
        return cls(fleet=())

    def weakest_for(self, men: int) -> Transport | None:
        """Return the first row that seats `men`, or None when nothing does.

        None rather than the largest row: a Squad that does not fit is a menu to
        fix, and issuing the biggest thing available would hide it behind men
        left standing at the Base.
        """
        for transport in self.fleet:
            if transport.seats >= men:
                return transport
        return None

    def ids(self) -> tuple[str, ...]:
        """Every transport id, in authored order."""
        return tuple(transport.id for transport in self.fleet)


def _check_fleet(fleet: list[dict[str, Any]]) -> None:
    """Every row is distinct, named, seats somebody, and names a vehicle."""
    for row in fleet:
        if not isinstance(_required(row, "id", "a transport"), str) or not row["id"]:
            _refuse("transport id must be a non-empty string")
        what = f"transport {row['id']!r}"
        if not isinstance(_required(row, "display_name", what), str) or not row["display_name"]:
            _refuse(f"{row['id']}: display_name must be a non-empty string")
        # Bools excluded explicitly, because `isinstance(True, int)` is true and
        # `True` would author a one-seat truck.
        seats = _required(row, "seats", what)
        if isinstance(seats, bool) or not isinstance(seats, int) or seats <= 0:
            _refuse(f"{row['id']}: seats must be a positive whole number")
        # The class the engine builds the vehicle from: a blank one spawns
        # nothing at all, silently, in a Play Session.
        if not isinstance(_required(row, "vehicle", what), str) or not row["vehicle"]:
            _refuse(f"{row['id']}: vehicle must be a non-empty classname")

    ids = [row["id"] for row in fleet]
    duplicates = sorted({name for name in ids if ids.count(name) > 1})
    if duplicates:
        _refuse(f"duplicate transport id: {', '.join(duplicates)}")

    # Weakest first is what `weakest_for` reads, and a file authored out of order
    # would answer that question with a vehicle nobody called the most basic. The
    # rule is on `seats` because that is the only part of "basic" this module can
    # see; which of two equally-seated rows comes first stays the author's.
    seating = [row["seats"] for row in fleet]
    if seating != sorted(seating):
        _refuse(f"the fleet must be authored weakest first, got seats {seating}")


def parse(document: object) -> Motorpool:
    """Validate an authored transport menu and build the motorpool."""
    if not isinstance(document, dict):
        _refuse(f"the transport catalogue must be an object, got {type(document).__name__}")
    authored = cast("dict[str, Any]", document)

    if authored.get("schema_version") != SCHEMA_VERSION:
        _refuse(f"schema_version must be {SCHEMA_VERSION}, got {authored.get('schema_version')!r}")

    fleet: list[dict[str, Any]] = _required(authored, "fleet", "the transport catalogue")
    if not isinstance(fleet, list):
        _refuse(f"fleet must be a list, got {type(fleet).__name__}")
    if not fleet:
        # A menu the world would read and then have nothing to issue from.
        _refuse("the transport catalogue must offer at least one transport")
    _check_fleet(fleet)

    return Motorpool(
        fleet=tuple(
            Transport(
                id=row["id"],
                display_name=row["display_name"],
                seats=row["seats"],
                vehicle=row["vehicle"],
            )
            for row in fleet
        )
    )


def load(path: Path) -> Motorpool:
    """Read and validate the authored transport menu."""
    return parse(json.loads(path.read_text(encoding="utf-8")))


def capacity_covers(pool: Motorpool, table: EconomyTable) -> tuple[str, ...]:
    """Which Squad types the menu cannot seat, in authored order.

    The cross-check this module exists for, and the one neither document can
    make alone: `config/economy.json` owns how many men a Squad is bought at
    (#159) and `transport.json` owns how many a vehicle carries. Empty is the
    passing answer.

    Read against the *purchased* size rather than a Squad's standing strength,
    because a thinned Squad is about to be Reinforced back to it and a vehicle
    issued for today's casualties is one seat short tomorrow.
    """
    return tuple(squad.id for squad in table.squads if pool.weakest_for(squad.size) is None)
