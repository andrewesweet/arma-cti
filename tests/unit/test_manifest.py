"""Map manifest loading and validation.

The manifest is authored by hand, so the validator's job is to catch authoring
slips before a Play Session does. A malformed manifest must fail here — in
`just unit` — rather than half-building a world on a dedicated server.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any, Final

import pytest
from conftest import REPO

from cti_daemon import manifest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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


def test_an_objective_id_that_collides_with_a_base_id_is_refused(stratis: dict[str, Any]) -> None:
    # One id namespace (ADR-0020): an Order names a Place of either kind, so an
    # id both kinds answer to is ground the port could not tell apart. The
    # message says which id, because that is the only thing an author can fix.
    base_id = stratis["bases"][0]["id"]
    broken = mutate(stratis, lambda d: d["objectives"][0].__setitem__("id", base_id))
    with pytest.raises(manifest.ManifestError, match=base_id):
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


@pytest.mark.parametrize("missing", ["objectives", "bases", "world", "display_name"])
def test_a_manifest_missing_a_required_key_is_refused_in_its_own_words(
    stratis: dict[str, Any], missing: str
) -> None:
    # A bare KeyError names the key and nothing else, and escapes the one error
    # type every caller of this module catches (#88).
    broken = copy.deepcopy(stratis)
    del broken[missing]
    with pytest.raises(manifest.ManifestError, match=missing):
        manifest.parse(broken)


@pytest.mark.parametrize(
    "missing", ["display_name", "position", "capture_radius", "income", "adjacent"]
)
def test_an_objective_missing_a_required_key_is_refused_in_its_own_words(
    stratis: dict[str, Any], missing: str
) -> None:
    broken = copy.deepcopy(stratis)
    del broken["objectives"][0][missing]
    with pytest.raises(manifest.ManifestError, match=missing):
        manifest.parse(broken)


@pytest.mark.parametrize("missing", ["side", "display_name", "position", "hq", "adjacent"])
def test_a_base_missing_a_required_key_is_refused_in_its_own_words(
    stratis: dict[str, Any], missing: str
) -> None:
    broken = copy.deepcopy(stratis)
    del broken["bases"][0][missing]
    with pytest.raises(manifest.ManifestError, match=missing):
        manifest.parse(broken)


# The same class one level in from the keys above (#155): the key was there and
# what sat under it was not what the rules read. `"position": []` used to reach
# `_build` and raise a bare IndexError, and a non-list `adjacent` a bare
# TypeError, both past the error type callers of this module catch.
MALFORMED_POSITIONS: Final = [[], [1.0], [1.0, 2.0, 3.0], "1,2", {"x": 1, "y": 2}, None, [1.0, "y"]]
MALFORMED_ADJACENCIES: Final = ["camp_tempest", 7, None, {"camp_tempest": True}, [["camp_tempest"]]]


@pytest.mark.parametrize("kind", ["objectives", "bases"])
@pytest.mark.parametrize("position", MALFORMED_POSITIONS)
def test_a_place_whose_position_is_not_two_numbers_is_refused(
    stratis: dict[str, Any], kind: str, position: object
) -> None:
    broken = mutate(stratis, lambda d: d[kind][0].__setitem__("position", position))
    with pytest.raises(manifest.ManifestError, match="position"):
        manifest.parse(broken)


@pytest.mark.parametrize("kind", ["objectives", "bases"])
@pytest.mark.parametrize("adjacent", MALFORMED_ADJACENCIES)
def test_a_place_whose_adjacency_is_not_a_list_of_ids_is_refused(
    stratis: dict[str, Any], kind: str, adjacent: object
) -> None:
    broken = mutate(stratis, lambda d: d[kind][0].__setitem__("adjacent", adjacent))
    with pytest.raises(manifest.ManifestError, match="adjacent"):
        manifest.parse(broken)


def test_a_refused_position_says_what_a_position_is_and_why(stratis: dict[str, Any]) -> None:
    # The author reading this has typed something wrong once; the message is the
    # whole of what they get back, so it carries the rule and its consequence.
    broken = mutate(stratis, lambda d: d["objectives"][0].__setitem__("position", []))
    with pytest.raises(manifest.ManifestError, match=r"two numbers \[x, y\].*nowhere on the map"):
        manifest.parse(broken)
