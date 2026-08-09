"""The durable whole-Campaign document, and its pure serialise/restore boundary.

ADR-0003 makes one versioned snapshot the authoritative campaign state, and
ADR-0008 fixes what it carries: the strategic set alone, everything tactical
regenerated at boot. This is that document and the pure boundary that writes and
reads it — no transport, no file I/O (#289). A Phase-2 `save`/`load` is a handler
in the daemon and bytes on disk; both land later and inherit a tested document
rather than a format to invent.

Both sides, deliberately. The Observation (`cti_daemon.observation`) is one
Commander's momentary picture, projected to drop the enemy (#27); a snapshot is
nobody's picture, it is the state itself, so it carries both sides' Funds and
both sides' Squads. The two share vocabulary — an Order, the HQ-status words —
but not a document or a name, and a document of either kind is refused by the
other's parser: a view cannot be loaded as a save, and a save cannot be served
as a view. That is the mechanical form of the ruling that the snapshot is never
returned through `view`, `observe`, a debug verb or the oracle (#288).

What is here is exactly ADR-0008's persistent set and nothing tactical:

- Objective ownership and each Base's HQ status — the scoreboard, public.
- Funds, per side.
- Squads: their side, composition type, member count, standing Order and coarse
  Place (`at`). The map position (`pos`) is tactical and regenerated, so it is
  not here; a Squad's `fielded` flag is bookkeeping for the reconcile that
  re-runs on the first report after a resume, so it is not here either.
- The campaign clock — in-game seconds elapsed.
- The chosen loadout catalogue id per player UID (ADR-0056).

Two things ADR-0008 names are **not** here, and both are deliberate deferrals
rather than oversights, flagged for the sign-off gate rather than decided in
code:

- **Contacts are absent.** ADR-0008 regenerates AI knowledge at boot, and a
  Contact is the enemy picture assembled from that knowledge — momentary, like
  the Observation that carries it. The snapshot regenerates Contacts from the
  first reports after a resume rather than freezing a picture of the enemy that
  the engine has since forgotten for good reason.
- **Player role/Squad is deferred to #25.** The daemon-owned half of ADR-0008's
  player set — the loadout choice — is here; the Commander/squad-leader
  assignment is server-side state (ADR-0025), and #25 has not decided the
  composition-unassigned/suspended states a player-led Squad can be in. This
  schema invents no parallel representation for them: when #25's decision record
  settles how assignment reaches a daemon-persisted field, it arrives as an
  additive migration, not a redesign (ADR-0008).

A completed Campaign is not a snapshot. ADR-0023 retires the resumable snapshot
on victory and writes a telemetry-sourced record instead, so this schema carries
no outcome — a won Campaign has nothing to resume, by construction. The record's
field set is distinct from this one's, so `restore` refuses it rather than
half-loading a Campaign that should start fresh.

Forward compatibility is a requirement, not an accident (ADR-0008): the document
carries an explicit integer `version`, and a save written by an older version is
walked forward through registered migrations before it is read. A field a later
version added is filled with a documented safe default; a version with no
registered path to the current one is a typed refusal — never a fresh Campaign,
because a silent fresh start is the corrupted-world outcome this exists to
prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast

from cti_daemon.commands import OWNERS, SIDES
from cti_daemon.observation import DESTROYED, INTACT
from cti_daemon.squads import ORDERS, Order

if TYPE_CHECKING:
    from collections.abc import Callable

# The document's version. A single integer that moves forward on every schema
# change, additive or not: an additive field arrives as a migration that fills a
# safe default, so the version is the count of those changes rather than a
# major/minor guess at how breaking each was. A save at a version other than
# this is either migrated forward or refused — never read as-is.
CURRENT_VERSION: Final = 1

# The HQ-status vocabulary, shared with the Observation because both documents
# carry the same scoreboard fact. Imported rather than restated so the two
# cannot drift: a third status is a decision for both at once, not one.
HQ_STATES: Final = (INTACT, DESTROYED)

# The document's own keys, declared once. `serialise` writes them and `restore`
# reads them against this list, so a closed typed field set is a property of the
# code rather than a convention a round-trip test holds after the fact. An
# unknown key or a missing one is a malformed document, refused on load.
VERSION_KEY: Final = "version"
CLOCK_KEY: Final = "clock"
OWNERS_KEY: Final = "owners"
HQ_KEY: Final = "hq"
FUNDS_KEY: Final = "funds"
SQUADS_KEY: Final = "squads"
LOADOUTS_KEY: Final = "loadouts"

DOCUMENT_KEYS: Final[tuple[str, ...]] = (
    VERSION_KEY,
    CLOCK_KEY,
    OWNERS_KEY,
    HQ_KEY,
    FUNDS_KEY,
    SQUADS_KEY,
    LOADOUTS_KEY,
)

# The wire names of one Squad's record, declared once for the same reason the
# document's keys are. `serialise` and `restore` both read this, so renaming a
# field is one edit rather than two held in step by a round-trip test noticing
# afterwards. `order` is the Order's kind and `place` is the ground it names, as
# on the Observation's SquadView; `at` is the coarse Place the Squad stands on,
# which is all ADR-0008 persists — the map metres are tactical and regenerated.
SQUAD_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("id", "id"),
    ("side", "side"),
    ("type", "squad_type"),
    ("size", "size"),
    ("order", "order"),
    ("place", "place"),
    ("at", "at"),
)


class SnapshotError(Exception):
    """A snapshot document is not one this version can load.

    The one type a caller catches, in the spirit of `ManifestError` and
    `LoadoutError`: what matters is that the document was refused, and the
    message says why. `restore` raises rather than returning a fresh snapshot on
    any fault, because a save that half-loads is the corrupted-world outcome
    durability exists to prevent (ADR-0003).
    """


class UnsupportedSnapshotVersionError(SnapshotError):
    """A snapshot whose version has no registered migration to the current one.

    Typed apart from a malformed document because the response differs: a
    malformed save is a bug to fix, an unsupported version is a save this build
    is too old or too new to read. Either way it is a refusal and never a fresh
    Campaign — the typed class lets a caller say "refused for the version"
    without re-parsing the message (#289).
    """

    def __init__(self, version: int) -> None:
        """Record the version the build cannot migrate from or to."""
        super().__init__(
            f"snapshot version {version} has no supported migration to {CURRENT_VERSION}"
        )
        self.version = version


@dataclass(frozen=True, slots=True)
class SquadRecord:
    """One Squad as the snapshot carries it: both sides, coarse Place, no metres.

    Distinct from `observation.SquadView` for the two reasons a snapshot is not a
    view: it carries a `side` (a view is projected to one side and drops it), and
    it carries no `pos` (the map metres are tactical, regenerated at boot). The
    standing Order is the same value type — `squads.Order` — because its
    semantics are identical, and reusing it is the half of "distinct documents,
    shared value types" that is not the document shape (#289).
    """

    id: str
    side: str
    squad_type: str
    size: int
    order: Order
    at: str


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The whole Campaign's strategic state, for both sides, at one moment.

    A value type rather than the `Campaign` aggregate: this is what crosses the
    serialise/restore boundary, and a snapshot is a photograph of the state
    rather than the live object that plays it. Plain dicts and a tuple, so the
    property target `restore(serialise(s)) == s` is equality of values rather
    than identity of objects (ADR-0003).
    """

    clock: float
    owners: dict[str, str]
    hq: dict[str, str]
    funds: dict[str, int]
    squads: tuple[SquadRecord, ...]
    loadouts: dict[str, str]


def _refuse(detail: str) -> NoReturn:
    """Raise the one error type callers catch. See `manifest._refuse` on why two."""
    raise SnapshotError(detail)


def _migrate_loadouts(document: dict[str, Any]) -> dict[str, Any]:
    """Step 0 -> 1: add the loadout record ADR-0056 introduced, empty by default."""
    migrated = dict(document)
    migrated.setdefault(LOADOUTS_KEY, {})
    migrated[VERSION_KEY] = 1
    return migrated


# Forward migrations: each maps an older version's document to the next version
# up, as a pure transform that may add fields with safe defaults. A document at
# version N is walked N -> N+1 -> ... -> CURRENT; a version with no entry here
# is a typed refusal rather than a save read as-is. The keys are the *source*
# version of each step.
_MIGRATIONS: Final[dict[int, Callable[[dict[str, Any]], dict[str, Any]]]] = {
    # Version 0 is a constructed predecessor that predates the loadout field
    # (ADR-0056). No real save was ever written at version 0 — loadouts and
    # versioning arrive together in #289 — but the step exists so the migration
    # machinery is exercised on first release rather than first relied upon. The
    # safe default is the empty record: nobody has chosen a kit, so every player
    # re-picks on resume, which is the named-but-not-fatal case ADR-0056 already
    # handles for a kit the menu no longer offers.
    0: _migrate_loadouts,
}


def serialise(snapshot: Snapshot) -> dict[str, Any]:
    """Render a snapshot as the document a durable write would store.

    Always at `CURRENT_VERSION`: a snapshot in memory is the current shape, and a
    save is a photograph of what is held, not of a past schema. Fresh dicts, so a
    caller holding the document cannot edit the snapshot it was built from.
    """
    return {
        VERSION_KEY: CURRENT_VERSION,
        CLOCK_KEY: snapshot.clock,
        OWNERS_KEY: dict(snapshot.owners),
        HQ_KEY: dict(snapshot.hq),
        FUNDS_KEY: dict(snapshot.funds),
        SQUADS_KEY: [_render_squad(squad) for squad in snapshot.squads],
        LOADOUTS_KEY: dict(snapshot.loadouts),
    }


def restore(document: object) -> Snapshot:
    """Rebuild a snapshot from a stored document, migrating forward or refusing.

    Pure: no file, no socket, no clock. The catalogue the loadout ids are
    eventually checked against is not asked for here, because checking a kit id
    against today's menu is the loader's step (it reports which saved kits the
    menu no longer offers, via `loadouts.Chosen.restore`) rather than the
    document's. This boundary says the document is well-formed and current; the
    loader says it is playable.
    """
    if not isinstance(document, dict):
        _refuse(f"a snapshot must be an object, got {type(document).__name__}")
    cast_document = cast("dict[str, Any]", document)

    version = cast_document.get(VERSION_KEY)
    if not isinstance(version, int) or isinstance(version, bool):
        _refuse(f"a snapshot must carry an integer {VERSION_KEY!r}, got {version!r}")

    if version > CURRENT_VERSION:
        raise UnsupportedSnapshotVersionError(version)

    migrated = cast_document
    step_version = version
    while step_version < CURRENT_VERSION:
        step = _MIGRATIONS.get(step_version)
        if step is None:
            raise UnsupportedSnapshotVersionError(step_version)
        migrated = step(migrated)
        step_version += 1

    _check_closed_set(migrated)
    return Snapshot(
        clock=_as_clock(migrated[CLOCK_KEY]),
        owners=_as_str_map(migrated[OWNERS_KEY], OWNERS_KEY, "an owner", OWNERS),
        hq=_as_str_map(migrated[HQ_KEY], HQ_KEY, "an HQ status", HQ_STATES),
        funds=_as_int_map(migrated[FUNDS_KEY]),
        squads=_as_squads(migrated[SQUADS_KEY]),
        loadouts=_as_loadouts(migrated[LOADOUTS_KEY]),
    )


def _check_closed_set(document: dict[str, Any]) -> None:
    """Refuse a document that is not exactly the current field set."""
    keys = set(document)
    unknown = sorted(keys - set(DOCUMENT_KEYS))
    if unknown:
        _refuse(f"a snapshot carries only {list(DOCUMENT_KEYS)}, got unknown keys {unknown}")
    missing = sorted(set(DOCUMENT_KEYS) - keys)
    if missing:
        _refuse(f"a snapshot must carry {missing}, which this document lacks")


def _as_clock(value: object) -> float:
    """Return the campaign clock as a number of in-game seconds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _refuse(f"{CLOCK_KEY!r} must be a number of in-game seconds, got {value!r}")
    return float(value)


def _as_str_map(value: object, key: str, what: str, allowed: tuple[str, ...]) -> dict[str, str]:
    """Return a place-to-status map whose values are one of a closed vocabulary."""
    if not isinstance(value, dict):
        _refuse(f"{key!r} must be an object keyed by id, got {type(value).__name__}")
    rendered: dict[str, str] = {}
    for name, status in value.items():
        if not isinstance(name, str) or not name:
            _refuse(f"{key!r} must be keyed by a non-empty id, got {name!r}")
        if not isinstance(status, str) or status not in allowed:
            _refuse(f"{name}: {what} must be one of {list(allowed)}, got {status!r}")
        rendered[name] = status
    return rendered


def _as_int_map(value: object) -> dict[str, int]:
    """Return a side-to-Funds map of whole Funds keyed by side."""
    if not isinstance(value, dict):
        _refuse(f"{FUNDS_KEY!r} must be an object keyed by side, got {type(value).__name__}")
    rendered: dict[str, int] = {}
    for side, funds in value.items():
        if not isinstance(side, str) or not side:
            _refuse(f"{FUNDS_KEY!r} must be keyed by a side, got {side!r}")
        if isinstance(funds, bool) or not isinstance(funds, int):
            _refuse(f"{side}: Funds must be a whole number, got {funds!r}")
        rendered[side] = funds
    return rendered


def _as_squads(value: object) -> tuple[SquadRecord, ...]:
    """Return the Squads of both sides, each a well-formed record."""
    if not isinstance(value, list):
        _refuse(f"{SQUADS_KEY!r} must be a list of squad records, got {type(value).__name__}")
    return tuple(_as_squad(entry) for entry in value)


def _as_squad(entry: object) -> SquadRecord:
    """One squad record, validated field by field."""
    if not isinstance(entry, dict):
        _refuse(f"a squad record must be an object, got {type(entry).__name__}")
    record = cast("dict[str, Any]", entry)

    squad_id = record.get("id")
    if not isinstance(squad_id, str) or not squad_id:
        _refuse(f"a squad id must be a non-empty string, got {squad_id!r}")
    side = record.get("side")
    if side not in SIDES:
        _refuse(f"{squad_id}: `side` must be one of {list(SIDES)}, got {side!r}")
    squad_type = record.get("type")
    if not isinstance(squad_type, str) or not squad_type:
        _refuse(f"{squad_id}: `type` must be a non-empty string, got {squad_type!r}")
    size = record.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        _refuse(f"{squad_id}: `size` must be a non-negative whole number, got {size!r}")
    kind = record.get("order")
    if kind not in ORDERS:
        _refuse(f"{squad_id}: `order` must be one of {list(ORDERS)}, got {kind!r}")
    place = record.get("place")
    if not isinstance(place, str):
        _refuse(f"{squad_id}: `place` must be a string, got {place!r}")
    at = record.get("at")
    if not isinstance(at, str):
        _refuse(f"{squad_id}: `at` must be a string, got {at!r}")

    return SquadRecord(
        id=squad_id,
        side=side,
        squad_type=squad_type,
        size=size,
        order=Order(kind=kind, place=place),
        at=at,
    )


def _as_loadouts(value: object) -> dict[str, str]:
    """Return the chosen-kit record: one catalogue id per player UID, never an engine array."""
    if not isinstance(value, dict):
        _refuse(
            f"{LOADOUTS_KEY!r} must be an object keyed by player UID, got {type(value).__name__}"
        )
    rendered: dict[str, str] = {}
    for uid, kit_id in value.items():
        if not isinstance(uid, str) or not uid:
            _refuse(f"{LOADOUTS_KEY!r} must be keyed by a player UID, got {uid!r}")
        if not isinstance(kit_id, str):
            _refuse(f"{uid}: a saved kit id must be a string, got {kit_id!r}")
        rendered[uid] = kit_id
    return rendered


def _render_squad(squad: SquadRecord) -> dict[str, Any]:
    """Render one squad record as its document object."""
    return {
        "id": squad.id,
        "side": squad.side,
        "type": squad.squad_type,
        "size": squad.size,
        "order": squad.order.kind,
        "place": squad.order.place,
        "at": squad.at,
    }


# Re-exported so a test pins the document's shape to the names this module reads,
# as `observation.exported` does for the view — minus the wire publication, which
# the snapshot never gets (it is not exposed to a Commander: #289, #288).
def shape() -> dict[str, list[str]]:
    """Render the document's field names, for tests to hold the schema against."""
    return {
        "document": list(DOCUMENT_KEYS),
        "squad": [key for key, _ in SQUAD_FIELDS],
    }
