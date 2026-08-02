"""The campaign's tunable numbers: Funds, prices, and the rule clocks.

Named for Funds because that is what it started as; it now also carries the
income tick and capture durations, which are the same kind of thing — numbers
the MVP scope calls playtest-tuned placeholders, where the structure is the
contract and the values are expected to move.

The ledger lives in the daemon because strategic state is snapshot-owned
(ADR-0003) and belongs where it can be property-tested rather than in the world
(ADR-0012). Prices are authored data in `config/economy.json` so playtest tuning
is an edit, not a code change (docs/mvp-scope.md).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast

from cti_daemon.commands import SIDES

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA_VERSION: Final = 1
IDENTIFIER_ERROR: Final = "squad id must be a non-empty string"


class EconomyError(Exception):
    """The authored economy table is not one this project can play with."""


class InsufficientFundsError(Exception):
    """A side tried to spend more Funds than it holds."""


class UnknownSideError(Exception):
    """Funds were asked of a side this Campaign is not played by (#66).

    A caller's mistake rather than a Commander's — the port judges the side a
    Command names before anything reaches the Ledger — so it is raised rather
    than returned, and it is not an `EconomyError`: the authored table is fine.
    """


def _refuse(detail: str) -> NoReturn:
    """Raise the one error type callers catch. See `manifest._refuse` on why two."""
    raise EconomyError(detail)


@dataclass(frozen=True, slots=True)
class SquadType:
    """One purchasable Squad, what it costs, and what it is made of."""

    id: str
    display_name: str
    price: int
    size: int
    # What the Squad is made of, as an ordered roster of unit classnames per
    # side — one entry per man, so the roster's length *is* the Squad's size
    # (#79, #82). Authored rather than held as a literal in the addon for the
    # reason the prices are: what a rifle or weapons Squad consists of is a
    # design decision, and ADR-0020 calls today's values placeholders whose
    # structure is the contract. Per side because a side's men are its own
    # faction's classnames and nothing else varies with side.
    #
    # Positional: slot 0 is the man the Squad is built around, and a Reinforce
    # refills from the rear, so a Squad down to five men gets slots 5-7 back.
    # Unobservable while every slot of a roster is the same classname, which is
    # exactly the state #79 asked to be able to leave.
    composition: dict[str, tuple[str, ...]]

    def roster(self, side: str) -> tuple[str, ...]:
        """Return the classnames this Squad is made of, for that side.

        Empty for a side this Campaign is not played by. A parsed table carries
        a roster for every side in `SIDES`, so an empty answer means the caller
        named something that is not one.
        """
        return self.composition.get(side, ())


@dataclass(frozen=True, slots=True)
class EconomyTable:
    """The authored economy: starting balance, stipend and the price table."""

    starting_funds: int
    stipend: int
    income_tick_seconds: int
    capture_seconds: int
    # How long one side must own every Objective at once to win by Domination
    # (docs/mvp-scope.md: ten in-game minutes). Authored here with the other rule
    # clocks because it is the same kind of number — the structure is the
    # contract and the value is expected to move under playtest.
    domination_seconds: int
    # What a replacement man costs relative to a new one, as a fraction of the
    # Squad's price (docs/mvp-scope.md: "missing fraction x price x ~0.8
    # discount"). A **playtest-tuned placeholder** in ADR-0020's sense: the
    # structure — Reinforce is priced off what is missing, and priced below
    # buying the same men fresh — is the contract, and 0.8 is a number nobody
    # has played against yet. Authored rather than coded so tuning it is an edit
    # (docs/mvp-scope.md), and it wants a human's sign-off on feel.
    reinforce_discount: float
    squads: tuple[SquadType, ...]

    def sold(self, squad_type: str) -> SquadType | None:
        """Return the Squad type sold under that name, or None if none is.

        One lookup for both the callers that had one (#87): the port asked
        `price` to find out whether a Purchase named anything real, then the
        Campaign scanned the same tuple again to find the entry the port had
        already had in its hand.
        """
        for squad in self.squads:
            if squad.id == squad_type:
                return squad
        return None

    def reinforce_cost(self, squad_type: str, missing: int) -> int | None:
        """Return what it costs to put `missing` men back into a Squad of that type.

        The missing fraction of the Squad's price, discounted (ADR-0040, #123).
        Rounded up rather than down, so replacing one man is never free and a
        Squad cannot be refilled a man at a time for nothing — which is the one
        way a fractional price can be exploited rather than merely mistuned.

        None when nothing by that name is sold, for the reason `price` answers
        None: an authored table that no longer sells a Squad somebody bought is
        a fault to report, not a free refill.
        """
        found = self.sold(squad_type)
        if found is None:
            return None
        if missing <= 0:
            return 0
        return math.ceil(found.price * (missing / found.size) * self.reinforce_discount)

    def price(self, squad_type: str) -> int | None:
        """Return what `squad_type` costs, or None when nothing by that name is sold."""
        found = self.sold(squad_type)
        return None if found is None else found.price


def _required(document: dict[str, Any], key: str, what: str) -> Any:  # noqa: ANN401 — the
    # value is whatever the document held; every caller checks its type next.
    """Return an authored key, or refuse the document for not having it.

    A missing key used to raise a bare `KeyError` naming the key and nothing
    else, past the one error type every caller of this module catches (#88).
    """
    if key not in document:
        _refuse(f"{what} must carry {key!r}")
    return document[key]


def _check_composition(squad: dict[str, Any]) -> None:
    """Every Squad type is made of somebody, on both sides, in the right number.

    The check the addon cannot make for itself (#79): `fn_effectApply` reads
    this roster to decide what to spawn, and the failure it would otherwise
    meet — a type with no roster, or a roster that is not the size the price was
    set against — is a world with the wrong number of men in it, discovered in
    an Arma run. Here it is a red `just unit`.
    """
    name = squad["id"]
    composition = _required(squad, "composition", f"squad {name!r}")
    if not isinstance(composition, dict):
        _refuse(f"{name}: composition must be an object keyed by side")

    authored = cast("dict[str, Any]", composition)
    if set(authored) != set(SIDES):
        _refuse(f"{name}: composition must carry a roster for exactly {list(SIDES)}")

    for side in SIDES:
        roster = authored[side]
        if not isinstance(roster, list):
            _refuse(f"{name}: {side} composition must be a list of unit classnames")
        entries = cast("list[Any]", roster)
        if any(not isinstance(entry, str) or not entry for entry in entries):
            _refuse(f"{name}: {side} composition entries must be non-empty classnames")
        # The roster is one entry per man, so a roster of a different length is
        # a Squad whose price was set against a size the world will not spawn.
        if len(entries) != squad["size"]:
            _refuse(
                f"{name}: {side} composition has {len(entries)} men "
                f"but the Squad's size is {squad['size']}"
            )


def _check_squads(squads: list[dict[str, Any]]) -> None:
    """Every Squad type is distinct, named, and costs a sane amount."""
    # Ids are checked to be strings *before* they are collected and sorted: a
    # numeric id used to die comparing int against str inside `sorted` (#88),
    # which is neither this module's error type nor a sentence about the table.
    for squad in squads:
        what = "a squad"
        if not isinstance(_required(squad, "id", what), str) or not squad["id"]:
            _refuse(IDENTIFIER_ERROR)
        what = f"squad {squad['id']!r}"
        if not isinstance(_required(squad, "display_name", what), str) or not squad["display_name"]:
            _refuse(f"{squad['id']}: display_name must be a non-empty string")
        if not isinstance(_required(squad, "price", what), int) or squad["price"] < 0:
            _refuse(f"{squad['id']}: price must be a whole number of Funds, not negative")
        if not isinstance(_required(squad, "size", what), int) or squad["size"] <= 0:
            _refuse(f"{squad['id']}: size must be a positive whole number")
        _check_composition(squad)

    ids = [squad["id"] for squad in squads]
    duplicates = sorted({name for name in ids if ids.count(name) > 1})
    if duplicates:
        _refuse(f"duplicate squad id: {', '.join(duplicates)}")


def _check_numbers(table: dict[str, Any]) -> None:
    """Funds are whole and not negative; the rule clocks take real time."""
    for key in ("starting_funds", "stipend"):
        if not isinstance(_required(table, key, "the economy table"), int) or table[key] < 0:
            _refuse(f"{key} must be a whole number of Funds, not negative")

    # A tick or a capture that takes no time would pay continuously, or flip an
    # Objective the instant anyone walked past it. A Domination of no length
    # would end the Campaign on the frame the last Objective changed hands,
    # which is the grind's opposite failure and just as unplayable.
    for key in ("income_tick_seconds", "capture_seconds", "domination_seconds"):
        if not isinstance(_required(table, key, "the economy table"), int) or table[key] <= 0:
            _refuse(f"{key} must be a positive whole number of seconds")

    # A discount, so it is a fraction of the price and never more than it: a
    # Reinforce dearer than buying the Squad again is a table nobody meant to
    # author, and a free one is Funds with nothing to spend them on. Bools are
    # excluded explicitly because `isinstance(True, int)` is true and `True`
    # would author a full-price refill.
    discount = _required(table, "reinforce_discount", "the economy table")
    if isinstance(discount, bool) or not isinstance(discount, int | float) or not 0 < discount <= 1:
        _refuse("reinforce_discount must be a fraction of the price, above 0 and at most 1")


def parse(document: object) -> EconomyTable:
    """Validate an authored economy document and build the table."""
    if not isinstance(document, dict):
        _refuse(f"economy table must be an object, got {type(document).__name__}")
    table = cast("dict[str, Any]", document)

    if table.get("schema_version") != SCHEMA_VERSION:
        _refuse(f"schema_version must be {SCHEMA_VERSION}, got {table.get('schema_version')!r}")

    squads: list[dict[str, Any]] = _required(table, "squads", "the economy table")
    if not isinstance(squads, list):
        _refuse(f"squads must be a list, got {type(squads).__name__}")
    _check_squads(squads)
    _check_numbers(table)

    return EconomyTable(
        starting_funds=table["starting_funds"],
        stipend=table["stipend"],
        income_tick_seconds=table["income_tick_seconds"],
        capture_seconds=table["capture_seconds"],
        domination_seconds=table["domination_seconds"],
        reinforce_discount=float(table["reinforce_discount"]),
        squads=tuple(
            SquadType(
                id=squad["id"],
                display_name=squad["display_name"],
                price=squad["price"],
                size=squad["size"],
                composition={side: tuple(squad["composition"][side]) for side in SIDES},
            )
            for squad in squads
        ),
    )


def load(path: Path) -> EconomyTable:
    """Read and validate the authored economy table."""
    return parse(json.loads(path.read_text(encoding="utf-8")))


@dataclass(slots=True)
class Ledger:
    """Per-side Funds. The only thing that may move them is a spend.

    It knows which sides are playing, and holds Funds for those and no others
    (#66). Seeded at construction rather than minted on demand: a ledger that
    invented a starting balance for whatever string it was handed turned a typo
    into a fortune, made `balance` a query that mutated, and pushed the "only
    playing sides hold Funds" invariant out to whichever call site remembered it.
    """

    starting_funds: int
    # Who is playing. The wire's own side vocabulary by default (#65), and
    # narrowable for a test that wants a one-sided ledger.
    sides: tuple[str, ...] = SIDES
    _balances: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Open an account for each playing side, and for nobody else."""
        self._balances = dict.fromkeys(self.sides, self.starting_funds)

    def holdings(self) -> dict[str, int]:
        """Return what every playing side holds — the whole of who has an account."""
        return dict(self._balances)

    def _account(self, side: str) -> int:
        """Return `side`'s balance, or refuse a side that has no account."""
        held = self._balances.get(side)
        if held is None:
            message = (
                f"no side named {side!r} holds Funds; this Campaign is played by {list(self.sides)}"
            )
            raise UnknownSideError(message)
        return held

    def balance(self, side: str) -> int:
        """Return what `side` currently holds. A read, and only a read."""
        return self._account(side)

    def can_afford(self, side: str, cost: int) -> bool:
        """Whether `side` could pay `cost` right now."""
        return self._account(side) >= cost

    def deposit(self, side: str, amount: int) -> int:
        """Add `amount` to `side` and return the new balance."""
        self._balances[side] = self._account(side) + amount
        return self._balances[side]

    def spend(self, side: str, cost: int) -> int:
        """Deduct `cost` from `side` and return the new balance.

        Refuses rather than going negative: Funds are the whole economy, and an
        overdraft would be a silent gift.
        """
        held = self._account(side)
        if held < cost:
            message = f"{side} holds {held}, cannot spend {cost}"
            raise InsufficientFundsError(message)
        self._balances[side] = held - cost
        return self._balances[side]
