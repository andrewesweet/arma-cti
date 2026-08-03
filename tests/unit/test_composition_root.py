"""What Main decides, and what a command line can reach of it (#164).

`cti_daemon.transport` is the composition root: it resolves this checkout's
authored files, assembles the object graph, and hands it to a `Daemon`. These
tests cover the two halves of that from the outside — that a caller may boot on
files of its own rather than the authored ones, and that the command line can
say so, which #4's "a hand-authored fixture boots directly" criterion needs.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from conftest import MANIFESTS, REPO

from cti_daemon import transport

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _economy(tmp_path: Path, **overrides: Any) -> Path:  # noqa: ANN401 — one authored
    # document, whose fields are of every type the schema has.
    """Write a fixture economy: the authored one, with fields overridden."""
    document = json.loads((REPO / "config" / "economy.json").read_text(encoding="utf-8"))
    document.update(overrides)
    path = tmp_path / "economy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _manifests(tmp_path: Path, map_id: str, world: str = "ProvingGround") -> Path:
    """Write a fixture manifests directory holding one map under `map_id`.

    Named after the world rather than the map id, because the addon resolves a
    manifest from `worldName` alone (ADR-0017) and `load_all` enforces it.
    """
    document = json.loads((MANIFESTS / "stratis.json").read_text(encoding="utf-8"))
    document["id"] = map_id
    document["world"] = world
    directory = tmp_path / "manifests"
    directory.mkdir()
    (directory / f"{world.lower()}.json").write_text(json.dumps(document), encoding="utf-8")
    return directory


def test_a_daemon_boots_on_a_fixture_economy_rather_than_the_authored_one(
    tmp_path: Path,
) -> None:
    # The knob that makes a Campaign start somewhere other than where the
    # shipped table says. Read off the Ledger rather than off the table, because
    # what is being checked is that the fixture reached the Campaign in play and
    # not merely that `economy.load` was called with it.
    daemon = transport.build_daemon(
        telemetry_path=tmp_path / "telemetry.jsonl",
        economy_path=_economy(tmp_path, starting_funds=4242),
    )

    assert daemon.campaign.ledger.holdings() == {"WEST": 4242, "EAST": 4242}


def test_a_daemon_boots_a_map_the_shipped_manifests_do_not_carry(tmp_path: Path) -> None:
    # `--map` is worth nothing without `--manifests`: the authored directory
    # ships one map, so the second is a fixture directory or it is nothing.
    daemon = transport.build_daemon(
        telemetry_path=tmp_path / "telemetry.jsonl",
        manifests_path=_manifests(tmp_path, "proving_ground"),
        map_id="proving_ground",
    )

    assert daemon.campaign.map_manifest.id == "proving_ground"


def test_the_wiring_is_one_campaign_the_port_and_the_cycle_agree_about(
    tmp_path: Path,
) -> None:
    # The reason `Wiring` is one record rather than four parameters (#164): two
    # of anything here would be two answers to what a side owns. The port judges
    # against the Campaign the cycle plays, and both are the daemon's.
    wiring = transport.wire(telemetry_path=tmp_path / "telemetry.jsonl")

    assert wiring.port.campaign is wiring.campaign
    assert wiring.cycle.campaign is wiring.campaign


def test_the_command_line_hands_its_authored_files_to_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `build_daemon` has taken these since #76 and nothing could reach them from
    # a command line. The assertion is on what `serve` was handed, because
    # threading a flag to the wrong parameter is the whole failure mode here and
    # a booted daemon would hide which flag arrived where.
    handed: dict[str, Any] = {}
    monkeypatch.setattr(transport, "serve", lambda *_, **named: handed.update(named))
    economy_path = _economy(tmp_path)
    manifests_path = _manifests(tmp_path, "proving_ground")

    code = transport.main(
        [
            "--telemetry",
            str(tmp_path / "telemetry.jsonl"),
            "--economy",
            str(economy_path),
            "--manifests",
            str(manifests_path),
            "--map",
            "proving_ground",
        ]
    )

    assert code == 0
    assert handed["economy_path"] == economy_path
    assert handed["manifests_path"] == manifests_path
    assert handed["map_id"] == "proving_ground"


def test_the_command_line_defaults_to_the_authored_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nothing said, nothing changed: the flags default to `None` so that
    # `build_daemon` stays the one answer to where the authored files live,
    # rather than the argument parser holding a second copy of those paths.
    handed: dict[str, Any] = {}
    monkeypatch.setattr(transport, "serve", lambda *_, **named: handed.update(named))

    transport.main(["--telemetry", str(tmp_path / "telemetry.jsonl")])

    assert handed["economy_path"] is None
    assert handed["manifests_path"] is None
    assert handed["map_id"] == transport.DEFAULT_MAP


def test_a_map_no_manifest_describes_is_refused_in_words(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The one lookup a flag can miss, and the operator's own mistake rather than
    # a traceback: `load_all` keys on the id each manifest declares.
    code = transport.main(
        [
            "--telemetry",
            str(tmp_path / "telemetry.jsonl"),
            "--map",
            "altis",
        ]
    )

    said = capsys.readouterr().err
    assert code == 2
    assert "no manifest" in said
    # Named, and so is where it looked: an operator who mistyped a map id and an
    # operator pointing at the wrong directory read the same refusal otherwise.
    assert "'altis'" in said
    assert str(transport.DEFAULT_MANIFESTS) in said
