"""The picture a human Commander is handed, and the one Commander per side (#18).

The human Commander commands through the same port the planner does, so nothing
here is about Commands. What #18 adds to the wire is the other half of the
symmetry: the planner reads `Campaign.observation(side)` in-process, and the
human has to read the same call over the wire or the two are playing different
games. `view` is that call, and these are the properties that make it safe to
serve — it is one side's projection and never the board, and a side already
under an AI Commander has no view to hand out and no Commands to take.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from conftest import reply_to

from cti_daemon import planner
from cti_daemon.transport import build_daemon

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.daemon import Daemon


def under_ai(daemon: Daemon, side: str, seed: int = 1) -> Daemon:
    """Put one side under an AI Commander, the way bring-up does."""
    daemon.commanded_by(
        side,
        planner.UtilityPlanner(
            map_manifest=daemon.campaign.map_manifest,
            table=daemon.campaign.table,
            seed=seed,
        ),
    )
    return daemon


def test_a_view_carries_that_side_and_what_only_it_may_know(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply_to(
        daemon,
        id="r-1",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )

    reply = reply_to(daemon, id="r-2", verb="view", payload={"side": "WEST"})

    assert reply["status"] == "ok"
    result = reply["result"]
    assert result["side"] == "WEST"
    assert result["funds"] == daemon.campaign.table.starting_funds - 100
    assert [squad["type"] for squad in result["squads"]] == ["rifle"]
    assert result["contacts"] == []
    # The public half is in every view, nobody's included: the two win conditions
    # are the scoreboard rather than intelligence (#27, #35).
    manifest = daemon.campaign.map_manifest
    assert set(result["owners"]) == {objective.id for objective in manifest.objectives}
    assert set(result["hq"]) == {base.id for base in manifest.bases}


def test_a_view_is_one_sides_projection_and_never_the_board(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply_to(
        daemon,
        id="r-1",
        verb="command",
        payload={
            "command": "purchase",
            "side": "EAST",
            "acting_side": "EAST",
            "args": {"squad_type": "rifle"},
        },
    )

    west = reply_to(daemon, id="r-2", verb="view", payload={"side": "WEST"})["result"]

    # EAST bought a Squad and spent Funds; WEST's view says nothing of either.
    assert west["squads"] == []
    assert west["funds"] == daemon.campaign.table.starting_funds
    assert json.dumps(west).count("EAST") == 0


def test_a_side_under_an_ai_commander_has_no_view_to_hand_out(tmp_path: Path) -> None:
    daemon = under_ai(build_daemon(telemetry_path=tmp_path / "telemetry.jsonl"), "EAST")

    reply = reply_to(daemon, id="r-1", verb="view", payload={"side": "EAST"})

    assert reply["status"] == "rejected"
    assert reply["reason"]["code"] == "wrong_side"


def test_the_side_a_human_plays_still_has_a_view_when_the_other_is_ai(tmp_path: Path) -> None:
    daemon = under_ai(build_daemon(telemetry_path=tmp_path / "telemetry.jsonl"), "EAST")

    reply = reply_to(daemon, id="r-1", verb="view", payload={"side": "WEST"})

    assert reply["status"] == "ok"
    assert reply["result"]["side"] == "WEST"


def test_a_view_of_a_side_that_is_not_playing_is_malformed(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")

    reply = reply_to(daemon, id="r-1", verb="view", payload={"side": "RESISTANCE"})

    assert reply["status"] == "error"
    assert reply["error"]["class"] == "malformed_request"


def test_a_view_with_no_side_named_is_malformed(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")

    reply = reply_to(daemon, id="r-1", verb="view", payload={})

    assert reply["status"] == "error"
    assert reply["error"]["class"] == "malformed_request"


def test_a_wire_command_for_a_side_under_an_ai_commander_is_refused(tmp_path: Path) -> None:
    daemon = under_ai(build_daemon(telemetry_path=tmp_path / "telemetry.jsonl"), "WEST")

    reply = reply_to(
        daemon,
        id="r-1",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )

    assert reply["status"] == "rejected"
    assert reply["reason"]["code"] == "wrong_side"
    # Refused before the rules, so nothing moved: no Funds spent, no Squad minted.
    assert daemon.campaign.ledger.balance("WEST") == daemon.campaign.table.starting_funds
    assert daemon.campaign.roster.roll("WEST") == ()


def test_the_ai_commander_itself_is_not_refused_by_that_rule(tmp_path: Path) -> None:
    # The check is on the wire, not in the port: the planner reaches the port
    # in-process, and one refused for being under a Commander is one refused for
    # existing.
    daemon = under_ai(build_daemon(telemetry_path=tmp_path / "telemetry.jsonl"), "WEST")

    reply_to(daemon, id="r-1", verb="observe", payload={"time": 10.0, "presence": {}})

    assert daemon.campaign.ledger.balance("WEST") < daemon.campaign.table.starting_funds


def test_a_view_is_attributed_to_the_side_that_asked(tmp_path: Path) -> None:
    telemetry = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=telemetry)

    reply_to(daemon, id="r-1", verb="view", payload={"side": "WEST"})

    rows = [json.loads(line) for line in telemetry.read_text(encoding="utf-8").splitlines()]
    asked = next(row for row in rows if row.get("verb") == "view")
    assert asked["side"] == "WEST"
