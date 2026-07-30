"""Funds: the per-side currency, and what a Squad costs.

The ledger lives in the daemon because strategic state is snapshot-owned
(ADR-0003) and belongs where it can be property-tested rather than in the world
(ADR-0012). Prices are authored data in `config/economy.json` so playtest tuning
is an edit, not a code change (docs/mvp-scope.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA_VERSION: Final = 1
IDENTIFIER_ERROR: Final = "squad id must be a non-empty string"


class EconomyError(Exception):
    """The authored economy table is not one this project can play with."""


class InsufficientFundsError(Exception):
    """A side tried to spend more Funds than it holds."""


def _refuse(detail: str) -> NoReturn:
    raise EconomyError(detail)


@dataclass(frozen=True, slots=True)
class SquadType:
    """One purchasable Squad and what it costs."""

    id: str
    display_name: str
    price: int
    size: int


@dataclass(frozen=True, slots=True)
class EconomyTable:
    """The authored economy: starting balance, stipend and the price table."""

    starting_funds: int
    stipend: int
    squads: tuple[SquadType, ...]

    def price(self, squad_type: str) -> int | None:
        """Return what `squad_type` costs, or None when nothing by that name is sold."""
        for squad in self.squads:
            if squad.id == squad_type:
                return squad.price
        return None


def parse(document: object) -> EconomyTable:
    """Validate an authored economy document and build the table."""
    if not isinstance(document, dict):
        _refuse(f"economy table must be an object, got {type(document).__name__}")
    table = cast("dict[str, Any]", document)

    if table.get("schema_version") != SCHEMA_VERSION:
        _refuse(f"schema_version must be {SCHEMA_VERSION}, got {table.get('schema_version')!r}")

    squads: list[dict[str, Any]] = table["squads"]
    ids = [squad["id"] for squad in squads]
    duplicates = sorted({name for name in ids if ids.count(name) > 1})
    if duplicates:
        _refuse(f"duplicate squad id: {', '.join(duplicates)}")

    for squad in squads:
        if not isinstance(squad["id"], str) or not squad["id"]:
            _refuse(IDENTIFIER_ERROR)
        if not isinstance(squad["price"], int) or squad["price"] < 0:
            _refuse(f"{squad['id']}: price must be a whole number of Funds, not negative")
        if not isinstance(squad["size"], int) or squad["size"] <= 0:
            _refuse(f"{squad['id']}: size must be a positive whole number")

    for key in ("starting_funds", "stipend"):
        if not isinstance(table[key], int) or table[key] < 0:
            _refuse(f"{key} must be a whole number of Funds, not negative")

    return EconomyTable(
        starting_funds=table["starting_funds"],
        stipend=table["stipend"],
        squads=tuple(
            SquadType(
                id=squad["id"],
                display_name=squad["display_name"],
                price=squad["price"],
                size=squad["size"],
            )
            for squad in squads
        ),
    )


def load(path: Path) -> EconomyTable:
    """Read and validate the authored economy table."""
    return parse(json.loads(path.read_text(encoding="utf-8")))


@dataclass(slots=True)
class Ledger:
    """Per-side Funds. The only thing that may move them is a spend."""

    starting_funds: int
    _balances: dict[str, int] = field(default_factory=dict)

    def balance(self, side: str) -> int:
        """Return what `side` currently holds."""
        return self._balances.setdefault(side, self.starting_funds)

    def can_afford(self, side: str, cost: int) -> bool:
        """Whether `side` could pay `cost` right now."""
        return self.balance(side) >= cost

    def spend(self, side: str, cost: int) -> int:
        """Deduct `cost` from `side` and return the new balance.

        Refuses rather than going negative: Funds are the whole economy, and an
        overdraft would be a silent gift.
        """
        if not self.can_afford(side, cost):
            message = f"{side} holds {self.balance(side)}, cannot spend {cost}"
            raise InsufficientFundsError(message)
        self._balances[side] = self.balance(side) - cost
        return self._balances[side]
