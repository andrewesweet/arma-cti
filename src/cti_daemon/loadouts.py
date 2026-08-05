"""The curated loadout menu, and which kit each player has chosen (#172).

The human's ruling of 2026-08-04 puts loadout customisation in the MVP as a
curated menu, free, players only, at Base only, surviving respawn and the
session save. ADR-0056 records the shape; this is its daemon half, and it holds
two things that are deliberately not one.

`Catalogue` is the menu as authored: `addons/main/catalogue/loadouts.json`, one
document read both by the addon that applies a kit and by the daemon that
records the choice (ADR-0017's pattern, the same as the map manifests). Each kit
names a vanilla unit class per side and `setUnitLoadout` extracts the kit from
that class's config, so the authored file is six rows rather than several
hundred item classnames.

`Chosen` is what the snapshot persists: one catalogue id per player UID, never
the engine's loadout array. ADR-0008 regenerates ammo and every other tactical
thing at session boot, and a `getUnitLoadout` array is mostly exactly that — so
the durable fact is *which kit he picked*, and the world re-applies the
catalogue on resume. That also keeps the persisted vocabulary closed, which is
what makes it testable: a kit id is one of six, and a loadout array is anything
the engine happened to be carrying.

Phase 2 (#4) has not built `save` or `load` yet. `serialise` and `restore` are
the shape it will use, property-tested here so the field arrives with its round
trip rather than after it (ADR-0003).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast

from cti_daemon.commands import SIDES

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA_VERSION: Final = 1


class LoadoutError(Exception):
    """The authored menu, or a saved record of it, is not one we can play with."""


def _refuse(detail: str) -> NoReturn:
    """Raise the one error type callers catch. See `manifest._refuse` on why two."""
    raise LoadoutError(detail)


def _required(document: dict[str, Any], key: str, what: str) -> Any:  # noqa: ANN401 — the value
    # is whatever the document held; every caller checks its type next.
    """Return an authored key, or refuse the document for not having it."""
    if key not in document:
        _refuse(f"{what} must carry {key!r}")
    return document[key]


@dataclass(frozen=True, slots=True)
class Kit:
    """One row of the menu: what it is called, and who wears it on each side.

    Per side because a side's men wear its own faction's kit and nothing else
    varies with side — the same reason `economy.SquadType` holds a roster per
    side rather than one list.
    """

    id: str
    display_name: str
    units: dict[str, str]

    def unit(self, side: str) -> str:
        """Return the unit class this kit is taken from, for that side.

        Empty for a side this Campaign is not played by. A parsed catalogue
        carries a class for every side in `SIDES`, so an empty answer means the
        caller named something that is not one.
        """
        return self.units.get(side, "")


@dataclass(frozen=True, slots=True)
class Catalogue:
    """The whole menu, in the order it was authored — which is the order shown."""

    kits: tuple[Kit, ...]

    @classmethod
    def empty(cls) -> Catalogue:
        """Return a menu with nothing on it, for a Campaign wired without one.

        Not a document anybody may author — `parse` refuses an empty `kits` —
        but the honest default for a `Campaign` built in a test that is not
        about loadouts: no kit is offered, rather than every kit.
        """
        return cls(kits=())

    def offered(self, kit_id: str) -> Kit | None:
        """Return the kit on the menu under that id, or None if none is."""
        for kit in self.kits:
            if kit.id == kit_id:
                return kit
        return None

    def ids(self) -> tuple[str, ...]:
        """Every kit id, in authored order."""
        return tuple(kit.id for kit in self.kits)


def _check_units(kit: dict[str, Any]) -> None:
    """Every kit dresses a man on both sides, from a class that is named."""
    name = kit["id"]
    units = _required(kit, "units", f"kit {name!r}")
    if not isinstance(units, dict):
        _refuse(f"{name}: units must be an object keyed by side")

    authored = cast("dict[str, Any]", units)
    if set(authored) != set(SIDES):
        _refuse(f"{name}: units must name a unit class for exactly {list(SIDES)}")

    for side in SIDES:
        # The class the engine reads the kit out of: a blank one dresses the
        # player in nothing at all, silently, in a Play Session.
        if not isinstance(authored[side], str) or not authored[side]:
            _refuse(f"{name}: the {side} unit class must be a non-empty classname")


def _check_kits(kits: list[dict[str, Any]]) -> None:
    """Every kit is distinct, named, and dresses somebody."""
    for kit in kits:
        if not isinstance(_required(kit, "id", "a kit"), str) or not kit["id"]:
            _refuse("kit id must be a non-empty string")
        what = f"kit {kit['id']!r}"
        if not isinstance(_required(kit, "display_name", what), str) or not kit["display_name"]:
            _refuse(f"{kit['id']}: display_name must be a non-empty string")
        _check_units(kit)

    ids = [kit["id"] for kit in kits]
    duplicates = sorted({name for name in ids if ids.count(name) > 1})
    if duplicates:
        _refuse(f"duplicate kit id: {', '.join(duplicates)}")


def parse(document: object) -> Catalogue:
    """Validate an authored menu and build the catalogue."""
    if not isinstance(document, dict):
        _refuse(f"the loadout catalogue must be an object, got {type(document).__name__}")
    authored = cast("dict[str, Any]", document)

    if authored.get("schema_version") != SCHEMA_VERSION:
        _refuse(f"schema_version must be {SCHEMA_VERSION}, got {authored.get('schema_version')!r}")

    kits: list[dict[str, Any]] = _required(authored, "kits", "the loadout catalogue")
    if not isinstance(kits, list):
        _refuse(f"kits must be a list, got {type(kits).__name__}")
    if not kits:
        # A menu the world would offer and then have nothing to put on it.
        _refuse("the loadout catalogue must offer at least one kit")
    _check_kits(kits)

    return Catalogue(
        kits=tuple(
            Kit(
                id=kit["id"],
                display_name=kit["display_name"],
                units={side: kit["units"][side] for side in SIDES},
            )
            for kit in kits
        )
    )


def load(path: Path) -> Catalogue:
    """Read and validate the authored menu."""
    return parse(json.loads(path.read_text(encoding="utf-8")))


@dataclass(slots=True)
class Chosen:
    """Which kit each player has picked, by player UID. The snapshot's field.

    Keyed by UID rather than by unit, because a unit does not survive the death
    the record has to survive — ADR-0025 latches the Commander by UID for the
    same reason, and it is the only identity a player carries across a respawn
    and across a Play Session.

    It refuses a kit the menu does not offer, so the persisted vocabulary is
    closed by construction: everything in here is a row of the catalogue it was
    built with, and a snapshot cannot come to hold a classname somebody typed.
    """

    catalogue: Catalogue
    _by_uid: dict[str, str] = field(default_factory=dict)

    def choose(self, uid: str, kit_id: str) -> bool:
        """Record that this player wears that kit. False if he may not.

        False rather than raised: the id arrives from the world, on the observe
        report, and a stale PBO offering a kit this daemon's catalogue has never
        heard of is a mismatch to report rather than a Campaign to stop. The
        caller writes the refusal down; nothing is recorded here.
        """
        if not uid or self.catalogue.offered(kit_id) is None:
            return False
        self._by_uid[uid] = kit_id
        return True

    def of(self, uid: str) -> str:
        """Which kit that player wears, or "" for one who has chosen none."""
        return self._by_uid.get(uid, "")

    def serialise(self) -> dict[str, str]:
        """Render the record as a snapshot would write it: UID to kit id.

        A copy, so a caller holding the document cannot edit the Campaign it
        was photographing.
        """
        return dict(self._by_uid)

    @classmethod
    def restore(cls, catalogue: Catalogue, document: object) -> tuple[Chosen, tuple[str, ...]]:
        """Read a saved record back, against the menu as it is authored today.

        Returns the record and the UIDs whose saved kit the menu no longer
        offers. Dropped rather than refused, because ADR-0008 requires a field
        to default sensibly when a later version cannot read it: retuning the
        menu must not make last week's Campaign unloadable. Named rather than
        dropped in silence, because a player quietly back in his default kit is
        exactly the kind of quiet this project does not keep.

        A document that is not a map of UID to string is refused outright: that
        is not a menu that moved, it is a file we did not write.
        """
        if not isinstance(document, dict):
            _refuse(f"a saved loadout record must be an object, got {type(document).__name__}")
        saved = cast("dict[Any, Any]", document)

        restored = cls(catalogue=catalogue)
        dropped: list[str] = []
        for uid, kit_id in saved.items():
            if not isinstance(uid, str) or not uid:
                _refuse("a saved loadout record must be keyed by player UID")
            if not isinstance(kit_id, str):
                _refuse(f"{uid}: a saved kit id must be a string")
            if not restored.choose(uid, kit_id):
                dropped.append(uid)
        return restored, tuple(dropped)
