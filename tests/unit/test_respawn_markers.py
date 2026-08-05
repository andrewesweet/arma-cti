"""A mission's respawn markers, held to the Base positions its manifest owns.

ADR-0052's ruling 1 sends a dead player to his own side's Base, and the engine
resolves "his own Base" through the per-side `respawn_west` / `respawn_east`
markers `respawn = "BASE"` looks for (topics/Arma_3_Respawn.wiki:77-93) — which
makes those markers a second copy of a position `addons/main/manifests/*.json`
already owns. The two were authored to agree and nothing kept them agreeing:
move a Base in the manifest and every Objective, every income tick and every
Decapitation reckons from the new place while the respawn marker stays in a
field a kilometre away. Nothing in the no-Arma tier could see that, and in-world
only a death would show it — a player materialising in the sea, once, in a
session nobody was measuring respawn in.

So the agreement is mechanical here (#189): drift is a red `just unit` rather
than a discovery. The check is Python because the fact is authored in two files
neither of which the game has to be running to read; the in-world probe
`spike/probes/respawn-base.sqf` asks a different question — that a dead player
actually arrives inside the Base's radius — and it would pass on a world whose
manifest and markers agreed with each other about the wrong place.

The delay is checked here for the same reason and it is the same kind of fault:
`respawnDelay` is authored twice as well (description.ext, and `class
ScenarioData` in mission.sqm, which is the face Eden gives the same attribute —
topics/Mission_sqm.wiki:53). The vendored wiki nowhere states which one the
engine reads when both exist, so rather than guess a precedence the mission sets
both and this refuses to let them disagree. A tune that moves one and not the
other would otherwise land a number nobody could predict the effect of.

Which missions are checked is decided by the missions themselves: a mission
names its manifest with `cti_manifest_map`, and one that names none — the
phase-0 spike world — has nothing to be held to. That keeps the pairing out of
this file, where it would be a third copy of the same fact.
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING, Final

import pytest
from conftest import MANIFESTS, REPO

from cti_daemon import manifest

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.manifest import Base

MISSIONS: Final = REPO / "missions"

# `respawn = "BASE"` looks for markers whose name *starts* with the side's
# prefix, so `respawn_west`, `respawn_west1` and `respawn_westBase` are all
# respawn points for WEST (topics/Arma_3_Respawn.wiki:93). The check follows the
# engine rather than the one name this mission happens to author: an extra
# marker added later is another place the engine may drop a player, and it has
# to be on the Base too.
MARKER_PREFIX: Final = "respawn_"


def _without_comments(text: str) -> str:
    """Blank `//` and `/* */` comments, keeping every other byte's position.

    mission.sqm is machine-written and carries none, but description.ext is
    prose-heavy and this file's own subject gets discussed in it — a sentence
    mentioning `respawnDelay` must not read as a second assignment of it.
    """
    without_block = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group()), text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", lambda m: " " * len(m.group()), without_block)


def _enclosing_body(text: str, index: int) -> str:
    """Return the innermost brace-balanced block containing `index`."""
    depth = 0
    start = -1
    for position in range(index, -1, -1):
        character = text[position]
        if character == "}":
            depth += 1
        elif character == "{":
            if depth == 0:
                start = position
                break
            depth -= 1
    if start < 0:
        message = "no enclosing block"
        raise ValueError(message)

    depth = 0
    for position in range(start, len(text)):
        character = text[position]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : position]
    message = "unbalanced block"
    raise ValueError(message)


def markers(sqm: str) -> dict[str, tuple[float, float]]:
    """Every marker a mission.sqm authors, by name, as (easting, northing).

    A marker's `position[]` is the editor's three-axis form — easting, altitude,
    northing — and the manifest's is the two the game is played on, so the
    middle number is dropped rather than compared. Anchored on the `dataType`
    that makes an item a Marker, because an Object item carries a `name` too
    (`cti_hq_west` is one) and nests it a class deep.
    """
    found: dict[str, tuple[float, float]] = {}
    for match in re.finditer(r'dataType\s*=\s*"Marker"', sqm):
        body = _enclosing_body(sqm, match.start())
        name = re.search(r'\bname\s*=\s*"([^"]*)"', body)
        position = re.search(r"\bposition\[\]\s*=\s*\{([^}]*)\}", body)
        if name is None or position is None:
            continue
        axes = [float(axis) for axis in position.group(1).split(",")]
        found[name.group(1)] = (axes[0], axes[2])
    return found


def number(text: str, key: str) -> float | None:
    """Read one `key = <number>;` out of a mission config file, if it is set."""
    match = re.search(rf"\b{re.escape(key)}\s*=\s*(-?[0-9.]+)\s*;", _without_comments(text))
    return None if match is None else float(match.group(1))


def string(text: str, key: str) -> str | None:
    """Read one `key = "<value>";` out of a mission config file, if it is set."""
    match = re.search(rf'\b{re.escape(key)}\s*=\s*"([^"]*)"\s*;', _without_comments(text))
    return None if match is None else match.group(1)


def drift(sqm: str, bases: list[Base]) -> list[str]:
    """Every disagreement between a mission's respawn markers and its Bases.

    Both directions are faults and they are different faults, so they are said
    differently: a marker away from its Base drops the player in the wrong
    place, and a side with no marker at all drops him where he started the
    mission (topics/Arma_3_Respawn.wiki:93) — which for a Commander is the
    editor slot he has never stood in.
    """
    complaints: list[str] = []
    by_side = {base.side.upper(): base for base in bases}

    for name, position in sorted(markers(sqm).items()):
        if not name.startswith(MARKER_PREFIX):
            continue
        side = name.removeprefix(MARKER_PREFIX).upper()
        base = next((held for held in by_side.values() if side.startswith(held.side.upper())), None)
        if base is None:
            complaints.append(f"marker {name} names no side the manifest plays")
        elif position != base.position:
            complaints.append(
                f"marker {name} is at {position}, but Base {base.id} is at {base.position}",
            )

    for side, base in sorted(by_side.items()):
        wanted = MARKER_PREFIX + side.lower()
        if not any(name.startswith(wanted) for name in markers(sqm)):
            complaints.append(f"Base {base.id} ({side}) has no {wanted} marker")

    return complaints


def _missions_naming_a_manifest() -> list[tuple[str, Path, Path]]:
    """Every mission that says which manifest it is played against, and that manifest."""
    paired: list[tuple[str, Path, Path]] = []
    for mission in sorted(MISSIONS.iterdir()):
        description = mission / "description.ext"
        if not description.is_file():
            continue
        named = string(description.read_text(encoding="utf-8"), "cti_manifest_map")
        if named is None:
            continue
        paired.append((mission.name, mission, MANIFESTS / f"{named}.json"))
    return paired


def _every_authored_mission() -> list[tuple[str, Path]]:
    """Every mission in the repository that has both files a delay can be set in.

    Wider than `_missions_naming_a_manifest` on purpose: the two-copies fault is
    the engine's ambiguity about `respawnDelay`, which a mission suffers whether
    or not it plays a manifest. The spike world has no Bases and is still able
    to set its delay twice.
    """
    return [
        (mission.name, mission)
        for mission in sorted(MISSIONS.iterdir())
        if (mission / "description.ext").is_file() and (mission / "mission.sqm").is_file()
    ]


PAIRED: Final = _missions_naming_a_manifest()
AUTHORED: Final = _every_authored_mission()


def test_the_selections_below_are_not_empty() -> None:
    """Both parametrisations are vacuous if these ever stop being true (#116)."""
    assert [name for name, _, _ in PAIRED] == ["cti.Stratis"]
    assert [name for name, _ in AUTHORED] == ["cti.Stratis", "spike.Stratis"]


@pytest.mark.parametrize(("name", "mission", "manifest_path"), PAIRED, ids=[p[0] for p in PAIRED])
def test_every_respawn_marker_sits_on_its_sides_base(
    name: str,
    mission: Path,
    manifest_path: Path,
) -> None:
    played = manifest.load(manifest_path)
    sqm = (mission / "mission.sqm").read_text(encoding="utf-8")
    assert drift(sqm, list(played.bases)) == [], name


@pytest.mark.parametrize(("name", "mission"), AUTHORED, ids=[p[0] for p in AUTHORED])
def test_the_two_authored_copies_of_the_respawn_delay_agree(name: str, mission: Path) -> None:
    described = number((mission / "description.ext").read_text(encoding="utf-8"), "respawnDelay")
    scenario = number((mission / "mission.sqm").read_text(encoding="utf-8"), "respawnDelay")
    assert described == scenario, (
        f"{name}: description.ext says {described}, mission.sqm's ScenarioData says {scenario} "
        "— the engine picks one and the wiki does not say which"
    )


def test_the_played_mission_carries_the_ruling_the_adr_took() -> None:
    """ADR-0052 ruling 6's number, at the one place a reader would look for it.

    Pinned rather than left to the agreement test above, which would be just as
    happy with both copies wrong. A playtest moving it edits this line too, and
    that is the point: 30 is a placeholder, not a secret.
    """
    played = MISSIONS / "cti.Stratis" / "description.ext"
    assert number(played.read_text(encoding="utf-8"), "respawnDelay") == 30


def test_a_marker_moved_off_its_base_is_refused() -> None:
    """The check's own red, against the authored mission with one marker moved."""
    played = manifest.load(MANIFESTS / "stratis.json")
    sqm = (MISSIONS / "cti.Stratis" / "mission.sqm").read_text(encoding="utf-8")
    moved = sqm.replace("position[]={1987.31,15,5625.9}", "position[]={1987.31,15,5225.9}")
    assert moved != sqm, "the fixture edited nothing — the authored marker moved under it"

    complaints = drift(moved, list(played.bases))

    assert len(complaints) == 1
    assert "marker respawn_west is at (1987.31, 5225.9)" in complaints[0]
    assert "Base nato_airbase is at (1987.31, 5625.9)" in complaints[0]


def test_a_base_moved_out_from_under_its_marker_is_refused() -> None:
    """The same drift from the other side, which is the direction play would cause."""
    played = manifest.load(MANIFESTS / "stratis.json")
    sqm = (MISSIONS / "cti.Stratis" / "mission.sqm").read_text(encoding="utf-8")
    elsewhere = [
        base if base.side != "EAST" else replace_position(base, (6401.97, 4000.0))
        for base in played.bases
    ]

    complaints = drift(sqm, elsewhere)

    assert len(complaints) == 1
    assert "marker respawn_east" in complaints[0]


def test_a_side_with_no_respawn_marker_is_refused() -> None:
    played = manifest.load(MANIFESTS / "stratis.json")
    sqm = (MISSIONS / "cti.Stratis" / "mission.sqm").read_text(encoding="utf-8")
    without = sqm.replace('name="respawn_east"', 'name="somewhere_else"')

    complaints = drift(without, list(played.bases))

    assert complaints == ["Base csat_kamino (EAST) has no respawn_east marker"]


def test_a_suffixed_marker_is_read_as_that_sides_respawn_point() -> None:
    """`respawn_west1` is a WEST respawn point to the engine, so it is one here."""
    played = manifest.load(MANIFESTS / "stratis.json")
    sqm = (MISSIONS / "cti.Stratis" / "mission.sqm").read_text(encoding="utf-8")
    suffixed = sqm.replace('name="respawn_west"', 'name="respawn_westBeach"')

    assert drift(suffixed, list(played.bases)) == []


def test_an_objects_name_is_not_mistaken_for_a_markers() -> None:
    """`cti_hq_west` is an Object with a nested `name`, and never a marker."""
    sqm = (MISSIONS / "cti.Stratis" / "mission.sqm").read_text(encoding="utf-8")

    assert set(markers(sqm)) == {"respawn_west", "respawn_east"}


def test_a_commented_out_delay_is_not_read_as_the_setting() -> None:
    assert number("// respawnDelay = 5;\nrespawnDelay = 30;\n", "respawnDelay") == 30
    assert number("/* respawnDelay = 5; */\nrespawnDelay = 30;\n", "respawnDelay") == 30


def replace_position(base: Base, position: tuple[float, float]) -> Base:
    """Return the same Base standing somewhere else."""
    return dataclasses.replace(base, position=position)
