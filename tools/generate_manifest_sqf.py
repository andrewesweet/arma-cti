"""Generate the addon's copy of the map manifests.

The manifests are authored once, as JSON, and read by two runtimes. Python
reads the JSON directly. SQF has no JSON parser, so this writes the same data
as an SQF function returning a HashMap — one source of truth, two readers, and
no chance of the two drifting because only one of them is written by hand.

`--check` regenerates into memory and compares, so a stale generated file is a
`schema_stale` failure in `just check` rather than a surprise in a Play Session.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from cti_daemon import manifest

if TYPE_CHECKING:
    from cti_daemon.manifest import MapManifest

BANNER = (
    "// Generated from manifests/*.json by tools/generate_manifest_sqf.py.\n"
    "// Do not edit by hand: change the JSON and run `just generate`.\n"
)
INDENT = "    "


def _number(value: float) -> str:
    """Render a number the way SQF reads it, without Python's float noise."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _string(value: str) -> str:
    """Render an SQF string literal, doubling any quote inside it."""
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


def _array(values: list[str]) -> str:
    return "[" + ", ".join(values) + "]"


def _pairs(pairs: list[tuple[str, str]], depth: int) -> str:
    """Render `createHashMapFromArray` over key/value pairs."""
    pad = INDENT * depth
    inner = ",\n".join(f"{pad}{INDENT}[{_string(key)}, {value}]" for key, value in pairs)
    return f"createHashMapFromArray [\n{inner}\n{pad}]"


def _objective(objective: object, depth: int) -> str:
    assert isinstance(objective, manifest.Objective)  # noqa: S101 — narrows for the type checker
    return _pairs(
        [
            ("id", _string(objective.id)),
            ("display_name", _string(objective.display_name)),
            ("position", _array([_number(axis) for axis in objective.position])),
            ("capture_radius", _number(objective.capture_radius)),
            ("income", _number(objective.income)),
            ("adjacent", _array([_string(name) for name in objective.adjacent])),
        ],
        depth,
    )


def _base(base: object, depth: int) -> str:
    assert isinstance(base, manifest.Base)  # noqa: S101 — narrows for the type checker
    return _pairs(
        [
            ("id", _string(base.id)),
            ("side", _string(base.side)),
            ("display_name", _string(base.display_name)),
            ("position", _array([_number(axis) for axis in base.position])),
            ("hq", _string(base.hq)),
            ("adjacent", _array([_string(name) for name in base.adjacent])),
        ],
        depth,
    )


def _map(map_manifest: MapManifest, depth: int) -> str:
    pad = INDENT * (depth + 1)
    objectives = ",\n".join(
        pad + INDENT + _objective(o, depth + 2) for o in map_manifest.objectives
    )
    bases = ",\n".join(pad + INDENT + _base(b, depth + 2) for b in map_manifest.bases)
    return _pairs(
        [
            ("id", _string(map_manifest.id)),
            ("world", _string(map_manifest.world)),
            ("display_name", _string(map_manifest.display_name)),
            ("bases", f"[\n{bases}\n{pad}]"),
            ("objectives", f"[\n{objectives}\n{pad}]"),
        ],
        depth,
    )


def render(maps: dict[str, MapManifest]) -> str:
    """Build the whole generated SQF file."""
    entries = ",\n".join(
        f'{INDENT}["{map_id}", {_map(maps[map_id], 1)}]' for map_id in sorted(maps)
    )
    body = f"createHashMapFromArray [\n{entries}\n]\n"
    header = (
        "/*\n"
        " * Author: arma-cti (generated)\n"
        " * Every authored map manifest, keyed by map id. Read through\n"
        " * cti_fnc_manifestLoad rather than called directly.\n"
        " *\n"
        " * Arguments: none\n"
        " *\n"
        " * Return Value: maps <HASHMAP>\n"
        " */\n"
    )
    return BANNER + header + body


def main(argv: list[str] | None = None) -> int:
    """Write the generated manifest, or check the one on disk is current."""
    repo = Path(__file__).parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", type=Path, default=repo / "manifests")
    parser.add_argument(
        "--output", type=Path, default=repo / "addons/main/generated/fn_manifestData.sqf"
    )
    parser.add_argument(
        "--check", action="store_true", help="fail if the file on disk is not what we would write"
    )
    args = parser.parse_args(argv)

    rendered = render(manifest.load_all(args.manifests))
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            print(  # noqa: T201 — this is the gate's output channel
                f"schema_stale: {args.output} does not match manifests/. Run `just generate`.",
                file=sys.stderr,
            )
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
