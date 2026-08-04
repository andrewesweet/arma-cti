"""The two sides of the outbound Observation, held together without Arma (#163).

`tests/unit/test_report_schema.py` does this for the report coming *in*; this is
the half going out. The daemon writes the document through
`cti_daemon.observation.serialise`, the export carries its field names into
`addons/main/generated/command-schema.json`, and the map UI reads them as
literals. Renaming a field on either side alone fails here rather than in a Play
Session, which is the surface #95 found least defended.

Two claims, because the seam has two joints. The export must be the names
`serialise` actually writes — asserted against a serialised document rather than
against the declaration, so a `serialise` that stopped reading the declaration
would be caught. And every observation key the map functions read must be one
the export declares.

The scan is receiver-aware rather than textual: `_view getOrDefault ["side", …]`
is a document key, `_x getOrDefault ["type", …]` inside a `forEach` over
`squads` or `contacts` is a record field, and `_schema getOrDefault […]` is the
Command catalogue, which `test_export_command_schema.py` owns. An unrecognised
receiver fails rather than being skipped, so a new reader arrives here for a
decision instead of passing unnoticed.

Not asserted: that the UI reads every declared field. It legitimately does not —
`hq` is drawn by the server from the public picture — and a rule saying otherwise
would make adding a field to the wire a UI ticket.
"""

from __future__ import annotations

import json
import re
from typing import Any

from conftest import REPO

from cti_daemon import observation
from cti_daemon.contacts import Contact
from cti_daemon.observation import Observation, SquadView

FUNCTIONS = REPO / "addons" / "main" / "functions"
SCHEMA = REPO / "addons" / "main" / "generated" / "command-schema.json"

# The document's readership inside the addon. `spike/probes/human-commander.sqf`
# reads it too and is deliberately not scanned: a probe that reads a renamed
# field goes red in the tier it belongs to, whereas the map UI's only tier was a
# Play Session.
READERS = ("fn_mapObservation.sqf", "fn_mapRender.sqf", "fn_mapIssue.sqf")

# `<receiver> getOrDefault ["<key>"` — the only form a literal key is read in.
_READ = re.compile(r'(\w+) +getOrDefault +\["([^"]+)"')

# What each receiver in those functions is holding. `_sold` is one Command
# catalogue *entry* — the Squad type the map divides current strength by
# (#174) — and belongs to the catalogue's owner with `_schema`, not to this
# seam: `test_export_command_schema.py` pins `size` into every sold entry.
_DOCUMENT = "_view"
_RECORD = "_x"
_CATALOGUE = ("_schema", "_sold")


def _reads() -> list[tuple[str, str, str]]:
    """Every literal-keyed hashmap read the map functions make."""
    found: list[tuple[str, str, str]] = []
    for name in READERS:
        source = (FUNCTIONS / name).read_text(encoding="utf-8")
        found += [(name, receiver, key) for receiver, key in _READ.findall(source)]
    return found


def _serialised() -> dict[str, Any]:
    """Build a Commander's view carrying one of everything the document holds."""
    return observation.serialise(
        Observation(
            at_time=12.0,
            owners={"agia_marina": "WEST"},
            hq={"base_west": observation.INTACT},
            for_side="WEST",
            funds=300,
            squads=(
                SquadView(
                    id="w1", squad_type="rifle", size=8, order="attack", place="agia_marina", at=""
                ),
            ),
            contacts=(
                Contact(at="agia_marina", echelon="squad", posture="holding", assets=(), age=30),
            ),
        )
    )


def test_the_export_is_the_names_serialise_writes() -> None:
    document = _serialised()
    exported = observation.exported()
    assert exported["document"] == list(document)
    assert exported["squad"] == list(document["squads"][0])
    assert exported["contact"] == list(document["contacts"][0])


def test_the_public_picture_carries_exactly_the_public_fields() -> None:
    # The projection #27 exists for, stated on the wire: the view belonging to
    # nobody carries no side's half of the declaration.
    public = observation.serialise(Observation(at_time=1.0, owners={}, hq={}))
    assert list(public) == list(observation.PUBLIC_FIELDS)


def test_the_shipped_export_carries_the_observation_shapes() -> None:
    # What the addon actually has on disk. `just check` fails a stale copy as
    # `schema_stale`; this says the current one holds the shapes at all.
    shipped = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert shipped["observation"] == observation.exported()


def test_the_map_functions_read_the_document_at_all() -> None:
    # Non-vacuity, the way the report scan takes it: if this finds nothing, the
    # pairing below is true of an empty set.
    assert [read for read in _reads() if read[1] == _DOCUMENT]
    assert [read for read in _reads() if read[1] == _RECORD]


def test_every_key_the_map_reads_is_one_the_export_declares() -> None:
    exported = observation.exported()
    records = set(exported["squad"]) | set(exported["contact"])
    for name, receiver, key in _reads():
        if receiver == _DOCUMENT:
            assert key in exported["document"], f"{name} reads an undeclared document key"
        elif receiver == _RECORD:
            assert key in records, f"{name} reads an undeclared squad or contact field"
        else:
            # Anything else is a hashmap this seam does not own — and the only
            # ones there are hold the Command catalogue.
            assert receiver in _CATALOGUE, f"{name} reads {receiver}, which nothing pins"
