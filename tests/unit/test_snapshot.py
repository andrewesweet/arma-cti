"""The versioned whole-Campaign snapshot, and its pure serialise/restore boundary (#289).

ADR-0003 makes a single versioned snapshot the authoritative campaign state, and
ADR-0008 fixes what it carries — the strategic set for both sides, everything
tactical regenerated. This pins the document `cti_daemon.snapshot` defines:

- `restore(serialise(s)) == s` over representative state for both sides, the
  property ADR-0003 targets (mirroring the round trip `test_loadouts` holds for
  the loadout field alone).
- A closed typed field set: unknown or malformed required fields refuse.
- Additive migration from a golden old-version fixture, absent fields defaulted.
- A version with no supported migration is a typed refusal, never a fresh Campaign.
- The snapshot is not exposed by any daemon handler, and a view cannot be loaded
  as a save nor a save served as a view.
- A completed-Campaign record (ADR-0023) cannot be parsed as a snapshot.
- Loadouts persist catalogue ids, and the snapshot's record feeds the
  `Chosen.restore` that names kits the menu no longer offers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cti_daemon import archive, daemon, loadouts, observation, snapshot
from cti_daemon.campaign import Outcome
from cti_daemon.commands import OWNERS, SIDES
from cti_daemon.observation import DESTROYED, INTACT
from cti_daemon.snapshot import (
    CURRENT_VERSION,
    Snapshot,
    SnapshotError,
    SquadRecord,
    UnsupportedSnapshotVersionError,
)
from cti_daemon.squads import ORDERS, Order

REPO = Path(__file__).resolve().parents[2]
FIXTURE_V0 = REPO / "tests" / "fixtures" / "snapshot-v0.json"

# Places the snapshot carries as ids. Owners and HQ are keyed by an id, which the
# parser holds to a non-empty string, so the keys sample only named ground; a
# Squad's `at` and an Order's `place` may be empty (open ground, Reserve), so
# those sample the empty string too.
OBJECTIVES = ("agia_marina", "girna", "pyrgos", "maxwell")
BASES = ("base_west", "base_east")
PLACES = (*OBJECTIVES, *BASES, "")
SQUAD_TYPES = ("rifle", "at", "recon", "mg")
KITS = ("rifleman", "medic", "marksman")
UIDS = st.text(min_size=1, max_size=20, alphabet=st.characters(min_codepoint=48, max_codepoint=122))

_squad = st.builds(
    SquadRecord,
    id=st.sampled_from(("w1", "e1", "w2", "e2", "w3", "e3")),
    side=st.sampled_from(SIDES),
    squad_type=st.sampled_from(SQUAD_TYPES),
    size=st.integers(min_value=0, max_value=12),
    order=st.builds(Order, kind=st.sampled_from(ORDERS), place=st.sampled_from(PLACES)),
    at=st.sampled_from(PLACES),
)

snapshots = st.builds(
    Snapshot,
    clock=st.floats(min_value=0, allow_nan=False, allow_infinity=False),
    owners=st.dictionaries(st.sampled_from(OBJECTIVES), st.sampled_from(OWNERS), max_size=4),
    hq=st.dictionaries(st.sampled_from(BASES), st.sampled_from((INTACT, DESTROYED)), max_size=2),
    funds=st.dictionaries(st.sampled_from(SIDES), st.integers(min_value=0), max_size=2),
    squads=st.lists(_squad, max_size=6).map(tuple),
    loadouts=st.dictionaries(UIDS, st.sampled_from(KITS), max_size=6),
)


def _document(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401 — one authored document,
    # whose values are whatever the caller is putting under test.
    """Return a well-formed current-version document, with fields overridden."""
    document = snapshot.serialise(
        Snapshot(
            clock=120.0,
            owners={"agia_marina": "WEST"},
            hq={"base_west": INTACT},
            funds=dict.fromkeys(SIDES, 200),
            squads=(
                SquadRecord(
                    id="w1",
                    side="WEST",
                    squad_type="rifle",
                    size=8,
                    order=Order(kind="defend", place="agia_marina"),
                    at="agia_marina",
                ),
            ),
            loadouts={"uid-1": "rifleman"},
        )
    )
    return document | overrides


# --- the round trip ADR-0003 targets -------------------------------------


@given(value=snapshots)
def test_a_restored_snapshot_is_the_one_that_was_saved(value: Snapshot) -> None:
    assert snapshot.restore(snapshot.serialise(value)) == value


def test_a_fresh_campaign_round_trips() -> None:
    # Both sides present, everything Neutral and intact, nothing bought: the
    # state a new session snapshots before its first change.
    fresh = Snapshot(
        clock=0.0,
        owners=dict.fromkeys(OBJECTIVES, "NEUTRAL"),
        hq=dict.fromkeys(BASES, INTACT),
        funds=dict.fromkeys(SIDES, 300),
        squads=(),
        loadouts={},
    )
    assert snapshot.restore(snapshot.serialise(fresh)) == fresh


def test_a_mid_campaign_with_both_sides_round_trips() -> None:
    # The case the Observation cannot represent: both sides' Funds and both sides'
    # Squads in one document, mixed ownership, an HQ fallen, two players kitted.
    mid = Snapshot(
        clock=5400.0,
        owners={
            "agia_marina": "WEST",
            "girna": "CONTESTED",
            "pyrgos": "NEUTRAL",
            "maxwell": "EAST",
        },
        hq={"base_west": INTACT, "base_east": DESTROYED},
        funds={"WEST": 320, "EAST": 150},
        squads=(
            SquadRecord("w1", "WEST", "rifle", 8, Order("defend", "agia_marina"), "agia_marina"),
            SquadRecord("e1", "EAST", "at", 6, Order("assault", "base_west"), "girna"),
            SquadRecord("w2", "WEST", "recon", 4, Order("reserve", ""), "base_west"),
        ),
        loadouts={"uid-1": "rifleman", "uid-2": "medic"},
    )
    assert snapshot.restore(snapshot.serialise(mid)) == mid


# --- a closed typed field set --------------------------------------------


def test_the_document_carries_exactly_the_declared_keys() -> None:
    assert set(snapshot.serialise(Snapshot(0.0, {}, {}, {}, (), {}))) == set(snapshot.DOCUMENT_KEYS)
    assert snapshot.shape() == {
        "document": list(snapshot.DOCUMENT_KEYS),
        "squad": [key for key, _ in snapshot.SQUAD_FIELDS],
    }


def test_serialise_writes_the_current_version() -> None:
    assert snapshot.serialise(Snapshot(0.0, {}, {}, {}, (), {}))["version"] == CURRENT_VERSION


@pytest.mark.parametrize(
    "document",
    [[], "not an object", 3, None],
)
def test_a_document_that_is_not_an_object_is_refused(document: object) -> None:
    with pytest.raises(SnapshotError, match="must be an object"):
        snapshot.restore(document)


def test_an_unknown_key_is_refused() -> None:
    with pytest.raises(SnapshotError, match="unknown keys"):
        snapshot.restore(_document(treasure="both sides' Funds"))


@pytest.mark.parametrize("missing", list(snapshot.DOCUMENT_KEYS))
def test_a_missing_required_key_is_refused(missing: str) -> None:
    document = _document()
    del document[missing]
    with pytest.raises(SnapshotError, match="must carry"):
        snapshot.restore(document)


@pytest.mark.parametrize("version", ["1", 1.0, True, None])
def test_a_version_that_is_not_an_integer_is_refused(version: object) -> None:
    with pytest.raises(SnapshotError, match="integer"):
        snapshot.restore(_document(version=version))


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("clock", "soon"),
        ("owners", []),
        ("hq", "intact"),
        ("funds", {"WEST": "lots"}),
        ("funds", {"WEST": True}),
        ("squads", {"w1": {}}),
    ],
)
def test_a_malformed_field_is_refused(key: str, bad: object) -> None:
    with pytest.raises(SnapshotError):
        snapshot.restore(_document(**{key: bad}))


def test_an_owner_value_outside_the_vocabulary_is_refused() -> None:
    with pytest.raises(SnapshotError, match="owner"):
        snapshot.restore(_document(owners={"agia_marina": "GREEN"}))


def test_an_hq_status_outside_the_two_states_is_refused() -> None:
    with pytest.raises(SnapshotError, match="HQ status"):
        snapshot.restore(_document(hq={"base_west": "damaged"}))


def test_a_squad_whose_side_is_not_playing_is_refused() -> None:
    document = _document(
        squads=[
            {
                "id": "r1",
                "side": "RESISTANCE",
                "type": "rifle",
                "size": 8,
                "order": "defend",
                "place": "agia_marina",
                "at": "agia_marina",
            }
        ]
    )
    with pytest.raises(SnapshotError, match="`side`"):
        snapshot.restore(document)


def test_a_squad_whose_order_is_unknown_is_refused() -> None:
    document = _document(
        squads=[
            {
                "id": "w1",
                "side": "WEST",
                "type": "rifle",
                "size": 8,
                "order": "attack",
                "place": "agia_marina",
                "at": "agia_marina",
            }
        ]
    )
    with pytest.raises(SnapshotError, match="`order`"):
        snapshot.restore(document)


def test_a_loadout_value_that_is_not_a_catalogue_id_is_refused() -> None:
    # A kit id is one word; an engine loadout array is anything the engine was
    # carrying, which is exactly what ADR-0056 keeps out of the save.
    with pytest.raises(SnapshotError, match="kit id"):
        snapshot.restore(_document(loadouts={"uid-1": ["arifle", "30rnd"]}))


# --- additive migration from a golden old version ------------------------


def test_a_golden_version_zero_fixture_migrates_to_current() -> None:
    # The fixture predates the loadout field (ADR-0056). It migrates additively:
    # the absent field arrives with the documented safe default — nobody has
    # chosen a kit — and every field that was there is preserved unchanged.
    restored = snapshot.restore(json.loads(FIXTURE_V0.read_text(encoding="utf-8")))

    assert restored.loadouts == {}
    assert restored.clock == 5400.0
    assert restored.owners == {
        "agia_marina": "WEST",
        "girna": "CONTESTED",
        "pyrgos": "NEUTRAL",
        "maxwell": "EAST",
    }
    assert restored.hq == {"base_west": INTACT, "base_east": DESTROYED}
    assert restored.funds == {"WEST": 320, "EAST": 150}
    assert restored.squads == (
        SquadRecord("WEST-1", "WEST", "rifle", 8, Order("defend", "agia_marina"), "agia_marina"),
        SquadRecord("EAST-1", "EAST", "at", 6, Order("assault", "base_west"), "girna"),
        SquadRecord("WEST-2", "WEST", "recon", 4, Order("reserve", ""), "base_west"),
    )


def test_a_version_zero_fixture_its_fields_were_not_touched_by_the_loadout_default() -> None:
    # The migration is additive only: round-tripping the migrated snapshot
    # through the current schema loses nothing the fixture carried.
    restored = snapshot.restore(json.loads(FIXTURE_V0.read_text(encoding="utf-8")))
    assert snapshot.restore(snapshot.serialise(restored)) == restored


def test_an_old_version_that_is_malformed_is_refused_after_migration() -> None:
    # A version-0 document still has to be well-formed once the loadout default
    # is filled: migration fixes absence, not corruption.
    document = json.loads(FIXTURE_V0.read_text(encoding="utf-8"))
    document["owners"]["agia_marina"] = "GREEN"
    with pytest.raises(SnapshotError, match="owner"):
        snapshot.restore(document)


# --- a version with no supported migration is a typed refusal ------------


def test_a_version_newer_than_current_is_a_typed_refusal() -> None:
    future = _document(version=CURRENT_VERSION + 1)
    with pytest.raises(UnsupportedSnapshotVersionError) as exc:
        snapshot.restore(future)
    assert exc.value.version == CURRENT_VERSION + 1


def test_a_version_with_no_registered_migration_is_a_typed_refusal() -> None:
    # Negative versions have no forward step registered, so they are refused
    # rather than read as a save at the current shape.
    with pytest.raises(UnsupportedSnapshotVersionError) as exc:
        snapshot.restore(_document(version=-1))
    assert exc.value.version == -1


def test_a_refusal_is_never_a_fresh_campaign() -> None:
    # The load-bearing property: every fault raises rather than returning a
    # snapshot, so a save that cannot be read cannot become a fresh Campaign.
    for bad in (_document(version=CURRENT_VERSION + 1), _document(version=-1), {"version": 1}):
        with pytest.raises(SnapshotError):
            snapshot.restore(bad)


# --- not exposed to a Commander ------------------------------------------


@pytest.mark.parametrize("verb", ["save", "load", "snapshot", "restore"])
def test_no_daemon_handler_exposes_the_snapshot(verb: str) -> None:
    # The snapshot is not a transport verb. The daemon's table is the one place a
    # handler is wired, and none of these names is in it (#288, #289).
    assert verb not in daemon.HANDLERS


def test_a_view_cannot_be_loaded_as_a_snapshot() -> None:
    # The Observation's document has no `version` and a single-side Funds, so a
    # Commander's view refused by the snapshot parser is a save that can never be
    # served back through `view` or `observe` as state.
    view = observation.serialise(
        observation.Observation(
            at_time=10.0,
            owners={"agia_marina": "WEST"},
            hq={"base_west": INTACT},
            for_side="WEST",
            funds=200,
            squads=(
                observation.SquadView(
                    id="w1", squad_type="rifle", size=8, order="defend", place="agia_marina", at=""
                ),
            ),
            contacts=(),
        )
    )
    with pytest.raises(SnapshotError, match="integer"):
        snapshot.restore(view)


def test_a_snapshot_cannot_be_served_as_a_view() -> None:
    # And the reverse: a snapshot carries both sides and a version, which the
    # Observation's document cannot make sense of — so a leaked save is not a
    # view the world could read even if it reached the wire.
    document = snapshot.serialise(
        Snapshot(
            10.0, {"agia_marina": "WEST"}, {"base_west": INTACT}, {"WEST": 200, "EAST": 150}, (), {}
        )
    )
    with pytest.raises(KeyError):
        observation.parse(document)


# --- a completed-Campaign record is not a snapshot -----------------------


def test_a_completed_campaign_record_cannot_be_parsed_as_a_snapshot(tmp_path: Path) -> None:
    # ADR-0023: a won Campaign is archived as a telemetry-sourced record, never a
    # resumable snapshot. `archive.summarise` returns exactly that record's shape,
    # and the snapshot parser refuses it — distinct field sets, by construction.
    record = archive.summarise(
        tmp_path / "no-such-telemetry.jsonl",
        Outcome(winner="WEST", condition="domination", at_time=3600.0),
    )
    with pytest.raises(SnapshotError, match="integer"):
        snapshot.restore(record)


def test_a_record_spoofing_a_version_is_still_refused(tmp_path: Path) -> None:
    # Adding a version to a completed-Campaign record does not make it a snapshot:
    # it still carries the record's own keys (winner, condition, base, income...),
    # which the closed set refuses as unknown before any field is even read.
    record = archive.summarise(
        tmp_path / "no-such-telemetry.jsonl",
        Outcome(winner="WEST", condition="domination", at_time=3600.0),
    )
    record["version"] = CURRENT_VERSION
    with pytest.raises(SnapshotError, match="unknown keys"):
        snapshot.restore(record)


# --- loadouts persist catalogue ids, and drops are reported --------------


def test_loadouts_are_catalogue_ids_per_uid_not_engine_arrays() -> None:
    document = snapshot.serialise(
        Snapshot(0.0, {}, {}, {}, (), {"uid-1": "rifleman", "uid-2": "medic"})
    )
    # One word per player, never the engine's loadout array (ADR-0056).
    assert document["loadouts"] == {"uid-1": "rifleman", "uid-2": "medic"}
    assert all(isinstance(kit, str) for kit in document["loadouts"].values())


def test_the_snapshot_loadouts_report_kits_the_menu_no_longer_offers() -> None:
    # The snapshot carries the ids; the loader checks them against today's menu
    # via `Chosen.restore`, which names the players whose saved kit is gone
    # rather than refusing the save (ADR-0008's forward-compatibility rule).
    catalogue = loadouts.parse(
        {
            "schema_version": 1,
            "kits": [
                {
                    "id": "rifleman",
                    "display_name": "Rifleman",
                    "units": dict.fromkeys(SIDES, "B_Soldier_F"),
                }
            ],
        }
    )
    saved = Snapshot(0.0, {}, {}, {}, (), {"uid-1": "rifleman", "uid-2": "jetpack"})
    _, dropped = loadouts.Chosen.restore(catalogue, saved.loadouts)
    assert dropped == ("uid-2",)
