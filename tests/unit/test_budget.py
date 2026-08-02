"""What an Observation costs on the wire, and what a map may therefore carry.

Moved out of `test_observation.py` with #78, along with the module under test:
the budget measures an envelope-encoded document against a limit the engine
imposes, which is a boundary question rather than a question about what a
Commander may know.

ADR-0030: the ceiling is a property of the map, so a map whose worst case cannot
cross one `callExtension` return fails `just unit` when it is authored rather
than truncating in silence in a Play Session.
"""

from __future__ import annotations

import json

import pytest
from conftest import REPO

from cti_daemon import budget, economy, manifest

SCHEMA = REPO / "addons" / "main" / "generated" / "command-schema.json"
DAEMON_CALL = REPO / "addons" / "main" / "functions" / "fn_daemonCall.sqf"


def stratis() -> manifest.MapManifest:
    """Return the authored Stratis manifest."""
    return manifest.load(REPO / "addons" / "main" / "manifests" / "stratis.json")


def island(objectives: int) -> manifest.MapManifest:
    """Return a manifest of `objectives` Objectives at Stratis place-name length.

    Ids rather than a real island, because only their length is being measured
    and Stratis's average eleven characters is what a Greek place name costs.
    Every Objective adjacent to the first, which the manifest requires to be one
    connected graph and #26 does not care about.
    """
    stems = [objective.id for objective in stratis().objectives]
    names = [
        stem if round_ == 0 else f"{stem}_{round_}"
        for round_ in range((objectives // len(stems)) + 1)
        for stem in stems
    ][:objectives]
    return manifest.parse(
        {
            "schema_version": manifest.SCHEMA_VERSION,
            "id": "island",
            "world": "Island",
            "display_name": "Island",
            "bases": [
                {
                    "id": base,
                    "side": side,
                    "display_name": "Base",
                    "position": [float(index * 10), 0.0],
                    "hq": f"cti_hq_{side.lower()}",
                    "adjacent": [names[0]],
                }
                for index, (base, side) in enumerate(
                    (("nato_airbase", "WEST"), ("csat_kamino", "EAST"))
                )
            ],
            "objectives": [
                {
                    "id": name,
                    "display_name": name,
                    "position": [float(index), 0.0],
                    "capture_radius": 200,
                    "income": 10,
                    "adjacent": [names[0]] if index else names[1:],
                }
                for index, name in enumerate(names)
            ],
        }
    )


# What #26 asked to be pinned: the Squad ceiling at growing map sizes, measured
# on the worst case the schema admits rather than on a plausible moment. The
# numbers are recorded so a change that shrinks headroom fails here rather than
# being noticed in a Play Session — and the shape of the table is the finding.
# The binding term is no longer Squad count but **place** count: #28's Contacts
# are keyed by place, so an island pays for its own size before either side has
# bought anything.
CEILINGS = (
    (8, 1_631, 70),
    (10, 1_943, 65),
    (20, 3_469, 51),
    (30, 5_005, 37),
    (40, 6_535, 24),
    (50, 8_073, 10),
    (60, 9_599, None),
    (90, 14_223, None),
)


@pytest.mark.parametrize(("objectives", "empty_bytes", "ceiling"), CEILINGS)
def test_the_squad_ceiling_falls_as_the_island_grows(
    objectives: int, empty_bytes: int, ceiling: int | None
) -> None:
    table = economy.load(REPO / "config" / "economy.json")
    map_manifest = island(objectives)

    assert budget.worst_case_bytes(map_manifest, table, squads_per_side=0) == empty_bytes
    assert budget.squad_ceiling(map_manifest, table) == ceiling


def test_an_island_can_outgrow_the_observation_before_a_squad_is_bought() -> None:
    # The finding that replaces #26's own table. It read "the island's size is
    # nearly irrelevant; the binding constraint is Squad count", measured when
    # the document carried both sides' rosters. #27 removed the enemy roster and
    # #28 put Contacts in its place — one per place rather than one per enemy
    # Squad — which is bounded by the map and therefore *is* the map's size. So
    # a sixty-Objective island now spends its whole budget on the ground itself.
    table = economy.load(REPO / "config" / "economy.json")

    assert budget.squad_ceiling(island(50), table) is not None
    assert budget.squad_ceiling(island(60), table) is None


def test_every_authored_map_fits_inside_one_callextension_return() -> None:
    # The guard that makes the ceiling enforced rather than merely known: a map
    # whose worst case cannot fit fails `just unit` when it is authored, rather
    # than truncating in silence in a Play Session. `docs/mvp-scope.md` ships one
    # map, and this is what a second one has to answer to.
    table = economy.load(REPO / "config" / "economy.json")

    for map_id, map_manifest in manifest.load_all(REPO / "addons" / "main" / "manifests").items():
        ceiling = budget.squad_ceiling(map_manifest, table)
        assert ceiling is not None, f"{map_id} cannot fit an observation with no Squads at all"
        # Well clear of what the map's own economy can fund: Stratis pays 85
        # Funds a minute at full domination against a rifle Squad's 100, so a
        # roster this size is a Campaign hours long that has lost nothing.
        assert ceiling > 40, f"{map_id} tops out at {ceiling} Squads a side"


def test_the_world_reads_its_guard_out_of_the_exported_budget() -> None:
    # #78: the SQF guard used to be a literal, held equal to the Python one by a
    # test that grepped this file's source. The exported schema is the seam that
    # carries a number to SQF (ADR-0017), so the structural guarantee replaces
    # the textual one — a stale export is `schema_stale` in `just check`, and
    # the guard cannot be edited out of step with the budget it enforces.
    exported = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert exported["reply_guard_bytes"] == budget.REPORT_GUARD_BYTES
    assert exported["return_cap_bytes"] == budget.RETURN_CAP_BYTES

    source = DAEMON_CALL.read_text(encoding="utf-8")
    assert 'getOrDefault ["reply_guard_bytes", 0]' in source
    # And the literal it replaced is gone rather than merely unused.
    assert str(budget.REPORT_GUARD_BYTES) not in source


def test_the_guard_is_nine_tenths_of_the_cap() -> None:
    # A reply merely close to truncating should fail a run rather than a Play
    # Session, which is the whole reason the guard is not the cap itself.
    assert budget.REPORT_GUARD_BYTES * 10 == budget.RETURN_CAP_BYTES * 9
