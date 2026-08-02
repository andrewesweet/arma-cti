"""The two sides of the observe report, held together without Arma (#74).

The daemon reads the report through `cti_daemon.report.SHAPES` and the samplers
build it through the same shapes, exported into
`addons/main/generated/command-schema.json`. What that leaves is the question a
`schema_stale` gate exists to answer: does the SQF that ships actually name the
fields the schema declares? Adding or renaming a field on one side alone fails
here, in `just unit`, rather than in the Arma tier one field at a time.

The scan is structural rather than textual: each `cti_fnc_reportObject` call
site is read as the array it is, and the field names are the literals that open
a pair inside it — so a name buried in an expression (`getOrDefault ["by", ""]`)
is not mistaken for a field of the object being built.
"""

from __future__ import annotations

import re
from pathlib import Path

from cti_daemon import report

FUNCTIONS = Path(__file__).parents[2] / "addons" / "main" / "functions"
BUILDER = "call cti_fnc_reportObject"

# Where a name sits in `["shape", [["field", value], ...]]`: the shape opens the
# argument array, and each field opens a pair two brackets deeper.
_SHAPE_DEPTH = 1
_FIELD_DEPTH = 3


def _argument(source: str, before: int) -> str:
    """Read the array literal handed to one builder call."""
    end = source.rindex("]", 0, before)
    depth = 0
    for index in range(end, -1, -1):
        if source[index] == "]":
            depth += 1
        elif source[index] == "[":
            depth -= 1
            if depth == 0:
                return source[index : end + 1]
    message = f"unbalanced builder argument ending at {end}"
    raise AssertionError(message)


def _built(argument: str) -> tuple[str, list[str]]:
    """Read one call site as the shape it builds and the fields it offers."""
    shape = ""
    fields: list[str] = []
    depth = 0
    opened = False
    index = 0
    while index < len(argument):
        char = argument[index]
        if char == '"':
            end = argument.index('"', index + 1)
            literal = argument[index + 1 : end]
            if opened and depth == _SHAPE_DEPTH:
                shape = literal
            elif opened and depth == _FIELD_DEPTH:
                fields.append(literal)
            opened = False
            index = end + 1
            continue
        if char == "[":
            depth += 1
            opened = True
        elif char == "]":
            depth -= 1
            opened = False
        elif not char.isspace():
            opened = False
        index += 1
    return shape, fields


def _call_sites() -> list[tuple[Path, str, list[str]]]:
    """Every object the addon builds through the report schema."""
    sites: list[tuple[Path, str, list[str]]] = []
    for path in sorted(FUNCTIONS.glob("*.sqf")):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(re.escape(BUILDER), source):
            shape, fields = _built(_argument(source, match.start()))
            sites.append((path, shape, fields))
    return sites


def test_the_addon_builds_the_report_through_the_schema() -> None:
    # Not a hypothetical scan: if this finds nothing, the samplers have gone
    # back to assembling the report out of literals and the pairing below is
    # vacuously true.
    assert _call_sites()


def test_every_declared_shape_is_one_the_samplers_build() -> None:
    # A shape nothing builds is a shape the daemon insists on for a document
    # nobody sends, which is the drift running the other way.
    built = {shape for _, shape, _ in _call_sites()}
    assert built == set(report.SHAPES)


def test_every_built_object_carries_exactly_the_declared_fields() -> None:
    for path, shape, fields in _call_sites():
        declared = [field.name for field in report.SHAPES[shape].fields]
        assert sorted(set(fields)) == sorted(declared), f"{path.name} builds {shape}"
