"""Map manifest loading and validation.

The manifest is authored by hand, so the validator's job is to catch authoring
slips before a Play Session does. A malformed manifest must fail here — in
`just unit` — rather than half-building a world on a dedicated server.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from cti_daemon import manifest

if TYPE_CHECKING:
    from collections.abc import Callable

REPO = Path(__file__).parents[2]
# The authored manifests live inside the addon, because the addon ships and
# reads them verbatim (ADR-0017). There is no second copy to point at.
MANIFESTS = REPO / "addons" / "main" / "manifests"


@pytest.fixture
def stratis() -> dict[str, Any]:
    """Return the authored Stratis manifest as a mutable document."""
    return json.loads((MANIFESTS / "stratis.json").read_text(encoding="utf-8"))


def test_the_authored_stratis_manifest_is_valid() -> None:
    stratis_map = manifest.load(MANIFESTS / "stratis.json")
    assert stratis_map.id == "stratis"
    assert stratis_map.world == "Stratis"


def test_every_authored_manifest_in_the_repository_is_valid() -> None:
    maps = manifest.load_all(MANIFESTS)
    assert "stratis" in maps


def test_a_manifest_filename_that_does_not_name_its_world_is_refused(tmp_path: Path) -> None:
    # The addon resolves a manifest from `worldName` alone, so the filename is
    # the lookup key. A manifest the game could never find is an authoring slip
    # Python is the only reader positioned to catch.
    document = json.loads((MANIFESTS / "stratis.json").read_text(encoding="utf-8"))
    (tmp_path / "altis.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(manifest.ManifestError, match=r"altis\.json"):
        manifest.load_all(tmp_path)


def test_a_manifest_filename_that_names_its_world_is_accepted(tmp_path: Path) -> None:
    document = json.loads((MANIFESTS / "stratis.json").read_text(encoding="utf-8"))
    (tmp_path / "stratis.json").write_text(json.dumps(document), encoding="utf-8")
    assert "stratis" in manifest.load_all(tmp_path)


def mutate(document: dict[str, Any], change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Apply an authoring slip to a copy of a valid manifest."""
    broken = copy.deepcopy(document)
    change(broken)
    return broken


def test_an_unknown_schema_version_is_refused(stratis: dict[str, Any]) -> None:
    # A manifest from a future format would be read with today's meaning.
    broken = mutate(stratis, lambda d: d.__setitem__("schema_version", 99))
    with pytest.raises(manifest.ManifestError, match="schema_version"):
        manifest.parse(broken)


def test_a_duplicated_objective_id_is_refused(stratis: dict[str, Any]) -> None:
    broken = mutate(stratis, lambda d: d["objectives"].append(copy.deepcopy(d["objectives"][0])))
    with pytest.raises(manifest.ManifestError, match="duplicate"):
        manifest.parse(broken)


def test_an_objective_id_that_is_not_a_stable_slug_is_refused(stratis: dict[str, Any]) -> None:
    # IDs are authored and outlive the positions they name, so they are held to
    # a shape rather than to whatever the author typed.
    broken = mutate(stratis, lambda d: d["objectives"][0].__setitem__("id", "Agia Marina"))
    with pytest.raises(manifest.ManifestError, match="id"):
        manifest.parse(broken)


def test_a_capture_radius_of_zero_is_refused(stratis: dict[str, Any]) -> None:
    broken = mutate(stratis, lambda d: d["objectives"][0].__setitem__("capture_radius", 0))
    with pytest.raises(manifest.ManifestError, match="capture_radius"):
        manifest.parse(broken)


def test_negative_income_is_refused(stratis: dict[str, Any]) -> None:
    broken = mutate(stratis, lambda d: d["objectives"][0].__setitem__("income", -1))
    with pytest.raises(manifest.ManifestError, match="income"):
        manifest.parse(broken)


def test_a_map_without_one_base_per_side_is_refused(stratis: dict[str, Any]) -> None:
    broken = mutate(stratis, lambda d: d["bases"][1].__setitem__("side", "WEST"))
    with pytest.raises(manifest.ManifestError, match="side"):
        manifest.parse(broken)


def test_a_base_without_an_hq_structure_is_refused(stratis: dict[str, Any]) -> None:
    # Decapitation is a loss condition; a Base with no HQ cannot lose that way.
    broken = mutate(stratis, lambda d: d["bases"][0].__setitem__("hq", ""))
    with pytest.raises(manifest.ManifestError, match="hq"):
        manifest.parse(broken)


def test_two_bases_sharing_one_hq_structure_is_refused(stratis: dict[str, Any]) -> None:
    broken = mutate(stratis, lambda d: d["bases"][1].__setitem__("hq", d["bases"][0]["hq"]))
    with pytest.raises(manifest.ManifestError, match="hq"):
        manifest.parse(broken)


def test_adjacency_naming_an_objective_that_does_not_exist_is_refused(
    stratis: dict[str, Any],
) -> None:
    broken = mutate(stratis, lambda d: d["objectives"][0]["adjacent"].append("atlantis"))
    with pytest.raises(manifest.ManifestError, match="atlantis"):
        manifest.parse(broken)


def test_one_sided_adjacency_is_refused(stratis: dict[str, Any]) -> None:
    # A front line the planner can cross in one direction only is an authoring
    # slip, never a design.
    broken = mutate(stratis, lambda d: d["objectives"][0]["adjacent"].remove("camp_tempest"))
    with pytest.raises(manifest.ManifestError, match=r"one-sided|symmetric"):
        manifest.parse(broken)


def test_an_objective_adjacent_to_itself_is_refused(stratis: dict[str, Any]) -> None:
    broken = mutate(
        stratis, lambda d: d["objectives"][0]["adjacent"].append(d["objectives"][0]["id"])
    )
    with pytest.raises(manifest.ManifestError, match="itself"):
        manifest.parse(broken)


def test_an_unreachable_objective_is_refused(stratis: dict[str, Any]) -> None:
    # An Objective no side can walk to cannot be captured, so Domination could
    # never be won on that map.
    def isolate(document: dict[str, Any]) -> None:
        orphan = document["objectives"][0]
        for neighbour in list(orphan["adjacent"]):
            other = next(o for o in document["objectives"] if o["id"] == neighbour)
            other["adjacent"].remove(orphan["id"])
        orphan["adjacent"] = []
        for base in document["bases"]:
            if orphan["id"] in base["adjacent"]:
                base["adjacent"].remove(orphan["id"])

    with pytest.raises(manifest.ManifestError, match="unreachable"):
        manifest.parse(mutate(stratis, isolate))


def test_a_base_adjacent_to_an_objective_that_does_not_exist_is_refused(
    stratis: dict[str, Any],
) -> None:
    broken = mutate(stratis, lambda d: d["bases"][0]["adjacent"].append("atlantis"))
    with pytest.raises(manifest.ManifestError, match="atlantis"):
        manifest.parse(broken)
