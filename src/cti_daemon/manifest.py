"""Map manifests: the authored world Objectives and Bases sit on.

One document per map (ADR-0007: each map gets a mission plus its manifest), so
the format carries more maps than the one authored without changing shape.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast

if TYPE_CHECKING:
    from pathlib import Path

import networkx as nx

# The two playable sides, from the one module that defines them (#65). A
# manifest is authored against the same side names the wire carries, so a second
# tuple here would be a second answer to who is playing.
from cti_daemon.commands import SIDES

SCHEMA_VERSION: Final = 1
# Authored IDs are referenced from SQF, from telemetry and from a snapshot, so
# they are held to a shape that survives all three.
IDENTIFIER: Final = re.compile(r"[a-z][a-z0-9_]*")


class ManifestError(Exception):
    """The manifest is not one this project can play on."""


@dataclass(frozen=True, slots=True)
class Objective:
    """A capturable point of interest with a stable authored ID."""

    id: str
    display_name: str
    position: tuple[float, float]
    capture_radius: float
    income: int
    adjacent: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Base:
    """A side's fixed home location and the HQ structure that can lose it."""

    id: str
    side: str
    display_name: str
    position: tuple[float, float]
    hq: str
    adjacent: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MapManifest:
    """One playable map."""

    id: str
    world: str
    display_name: str
    bases: tuple[Base, ...]
    objectives: tuple[Objective, ...]


def load(path: Path) -> MapManifest:
    """Read and validate one manifest document."""
    document: Any = json.loads(path.read_text(encoding="utf-8"))
    return parse(document)


def load_all(directory: Path) -> dict[str, MapManifest]:
    """Read every manifest in a directory, keyed by map id.

    The addon ships these files verbatim and resolves one at mission start from
    `worldName` alone (ADR-0017), so the filename is the lookup key rather than
    decoration. Python is the only reader that can see the whole directory, so
    the naming rule is enforced here — a manifest the game could never find
    fails `just unit` instead of producing an empty world on a server.
    """
    maps: dict[str, MapManifest] = {}
    for path in sorted(directory.glob("*.json")):
        found = load(path)
        if path.stem != found.world.lower():
            _refuse(
                f"{path.name} describes world {found.world!r}, so the addon would look for "
                f"{found.world.lower()}.json and find nothing"
            )
        maps[found.id] = found
    return maps


def _refuse(detail: str) -> NoReturn:
    """Raise the one error type callers catch.

    `economy._refuse` looks identical and is deliberately not shared (#87): the
    difference between the two is the exception each raises, which is the whole
    of what they are for — a caller catches `ManifestError` because it was
    reading a manifest, and would learn nothing from a shared refusal that could
    be either. Sharing the body would leave the type as a parameter and put the
    thing that matters furthest from the call.
    """
    raise ManifestError(detail)


# Every key the rules below index, by the kind of thing that must carry it.
# Declared rather than discovered one KeyError at a time (#88), and checked in
# one pass before any rule runs, so an authoring slip is one sentence about the
# manifest rather than an exception about a dictionary.
MAP_KEYS: Final = ("id", "world", "display_name", "bases", "objectives")
OBJECTIVE_KEYS: Final = ("id", "display_name", "position", "capture_radius", "income", "adjacent")
BASE_KEYS: Final = ("id", "side", "display_name", "position", "hq", "adjacent")


def _check_keys(document: dict[str, Any], keys: tuple[str, ...], what: str) -> None:
    """Refuse anything not carrying every key the rules will read off it."""
    missing = [key for key in keys if key not in document]
    if missing:
        _refuse(f"{what} must carry {', '.join(missing)}")


def _checked_list(value: object, what: str) -> list[dict[str, Any]]:
    """Read a list of authored objects, or refuse whatever was there instead."""
    if not isinstance(value, list) or any(not isinstance(entry, dict) for entry in value):
        _refuse(f"{what} must be a list of objects, got {type(value).__name__}")
    return cast("list[dict[str, Any]]", value)


def _check_identifier(value: object, what: str) -> None:
    """Hold an authored ID to a shape: it outlives the position it names."""
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        _refuse(f"{what} id must match {IDENTIFIER.pattern}, got {value!r}")


def _check_unique(ids: list[str], what: str) -> None:
    """Refuse a repeated authored id. `economy._check_squads` says the same thing.

    Not shared, for `_refuse`'s reason: the duplicate-finding is one expression
    and the error type is the substance. Kept spelled the same way in both so
    that reading one tells you what the other does.
    """
    duplicates = sorted({name for name in ids if ids.count(name) > 1})
    if duplicates:
        _refuse(f"duplicate {what} id: {', '.join(duplicates)}")


def _check_one_namespace(objectives: list[dict[str, Any]], bases: list[dict[str, Any]]) -> None:
    """Objectives and Bases share one id namespace (ADR-0020).

    An Order names a Place, and a Place is either kind, so an id both kinds
    answer to is ambiguous ground: the port could not tell whether Capture was
    naming an Objective it may take or a Base it may not. Uniqueness within a
    kind is not enough once one field can hold either.
    """
    collisions = sorted({base["id"] for base in bases} & {o["id"] for o in objectives})
    if collisions:
        _refuse(
            f"id names both an Objective and a Base: {', '.join(collisions)}. "
            f"An Order names a Place of either kind, so one id may name only one of them"
        )


def _check_objective(objective: dict[str, Any]) -> None:
    _check_identifier(objective.get("id"), "objective")
    if not (
        isinstance(objective["capture_radius"], (int, float)) and objective["capture_radius"] > 0
    ):
        _refuse(f"{objective['id']}: capture_radius must be positive")
    if not (isinstance(objective["income"], int) and objective["income"] >= 0):
        _refuse(f"{objective['id']}: income must be a whole number of Funds, not negative")


def _check_bases(bases: list[dict[str, Any]]) -> None:
    sides = [base["side"] for base in bases]
    if sorted(sides) != sorted(SIDES):
        _refuse(f"expected exactly one Base per side {sorted(SIDES)}, got {sides}")
    headquarters = [base["hq"] for base in bases]
    if any(not isinstance(hq, str) or not hq for hq in headquarters):
        _refuse(
            "every Base needs an hq structure — Decapitation has nothing to destroy without one"
        )
    if len(set(headquarters)) != len(headquarters):
        _refuse(f"two Bases name the same hq structure: {headquarters}")


def _check_adjacency_targets(holders: list[dict[str, Any]], known: set[str]) -> None:
    """Every adjacency names a real Objective, and never its own holder."""
    for holder in holders:
        for neighbour in holder["adjacent"]:
            if neighbour not in known:
                _refuse(f"{holder['id']} is adjacent to {neighbour!r}, which is not an Objective")
            if neighbour == holder["id"]:
                _refuse(f"{holder['id']} is adjacent to itself")


def _link_mutual_adjacency(objectives: list[dict[str, Any]], graph: nx.Graph) -> None:
    """Add each Objective's edges, refusing a front line crossable one way only.

    Named for both jobs rather than for the check alone (#90): it walks the
    authored adjacency once, and refusing a one-sided edge and adding a mutual
    one are the two things it can do with what it finds.
    """
    for objective in objectives:
        for neighbour in objective["adjacent"]:
            other = next(o for o in objectives if o["id"] == neighbour)
            if objective["id"] not in other["adjacent"]:
                _refuse(
                    f"one-sided adjacency: {objective['id']} lists {neighbour}, "
                    f"but {neighbour} does not list it back"
                )
            graph.add_edge(objective["id"], neighbour)


def _check_adjacency(objectives: list[dict[str, Any]], bases: list[dict[str, Any]]) -> None:
    """Check the Objective graph the AI Commander's utility scorer reasons over.

    Without it the planner has no notion of a front line, so the invariants it
    depends on are enforced here rather than discovered mid-Campaign.
    """
    known = {objective["id"] for objective in objectives}
    graph = nx.Graph()
    graph.add_nodes_from(known)

    _check_adjacency_targets([*objectives, *bases], known)
    _link_mutual_adjacency(objectives, graph)

    # Bases anchor the graph: an Objective reachable from neither Base is one
    # neither side can take, so Domination could never be won on this map.
    for base in bases:
        graph.add_node(base["id"])
        for neighbour in base["adjacent"]:
            graph.add_edge(base["id"], neighbour)
    if known and not nx.is_connected(graph):
        stranded = sorted(known - nx.node_connected_component(graph, bases[0]["id"]))
        _refuse(f"unreachable from {bases[0]['id']}: {', '.join(stranded)}")


def _validate(document: object) -> dict[str, Any]:
    """Refuse anything this project cannot play on."""
    if not isinstance(document, dict):
        _refuse(f"manifest must be an object, got {type(document).__name__}")
    # Checked above; every key it must carry is checked by the rules below.
    validated = cast("dict[str, Any]", document)

    if validated.get("schema_version") != SCHEMA_VERSION:
        _refuse(f"schema_version must be {SCHEMA_VERSION}, got {validated.get('schema_version')!r}")
    _check_keys(validated, MAP_KEYS, "the manifest")
    _check_identifier(validated.get("id"), "map")

    objectives: list[dict[str, Any]] = _checked_list(validated["objectives"], "objectives")
    bases: list[dict[str, Any]] = _checked_list(validated["bases"], "bases")
    # Every key every rule below indexes, before any of them run. A rule that
    # met a missing key raised a bare KeyError naming the key and nothing else,
    # past the one error type callers of this module catch (#88).
    for objective in objectives:
        _check_keys(objective, OBJECTIVE_KEYS, "an objective")
    for base in bases:
        _check_keys(base, BASE_KEYS, "a base")

    _check_unique([objective["id"] for objective in objectives], "objective")
    for objective in objectives:
        _check_objective(objective)

    _check_unique([base["id"] for base in bases], "base")
    _check_bases(bases)
    _check_one_namespace(objectives, bases)

    _check_adjacency(objectives, bases)
    return validated


def parse(document: object) -> MapManifest:
    """Validate a manifest document and build the map it describes."""
    validated = _validate(document)
    return _build(validated)


def _build(document: dict[str, Any]) -> MapManifest:
    """Turn a validated document into the map it describes."""
    return MapManifest(
        id=document["id"],
        world=document["world"],
        display_name=document["display_name"],
        bases=tuple(
            Base(
                id=base["id"],
                side=base["side"],
                display_name=base["display_name"],
                position=(base["position"][0], base["position"][1]),
                hq=base["hq"],
                adjacent=tuple(base["adjacent"]),
            )
            for base in document["bases"]
        ),
        objectives=tuple(
            Objective(
                id=objective["id"],
                display_name=objective["display_name"],
                position=(objective["position"][0], objective["position"][1]),
                capture_radius=objective["capture_radius"],
                income=objective["income"],
                adjacent=tuple(objective["adjacent"]),
            )
            for objective in document["objectives"]
        ),
    )
