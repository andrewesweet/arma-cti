"""What the daemon does when a Campaign is won (#35).

The rules are the Campaign's and are tested in `test_win_conditions.py`. What is
tested here is everything the rules are not: the world being told once, the
summary being sourced from telemetry rather than from campaign state, the
completed Campaign being archived, the Commanders being stood down, and the next
boot starting a fresh Campaign rather than resuming a finished one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cti_daemon import planner
from cti_daemon.commands import serialise_effect
from cti_daemon.transport import build_daemon

if TYPE_CHECKING:
    from cti_daemon.daemon import Daemon


def reply_to(daemon: Daemon, **envelope: object) -> dict[str, Any]:
    """Send one request and return its decoded reply."""
    return json.loads(daemon.handle_line(json.dumps(envelope)))


def observe(daemon: Daemon, request_id: str, **payload: object) -> dict[str, Any]:
    """Report what the world can see, and take back the strategic picture."""
    return reply_to(daemon, id=request_id, verb="observe", payload={"time": 1, **payload})["result"]


def rows(log: Path, event: str) -> list[dict[str, Any]]:
    """Every telemetry row of one kind."""
    written = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [row for row in written if row["event"] == event]


def effects(daemon: Daemon, name: str) -> list[dict[str, Any]]:
    """Every pending outbox message of one effect kind."""
    return [
        serialise_effect(entry.effect)
        for entry in daemon.outbox.pending()
        if entry.effect.name == name
    ]


def raze(daemon: Daemon, request_id: str, base: str, by: str, at_time: float = 90) -> None:
    """Report one Base's HQ destroyed, the way the world does."""
    observe(daemon, request_id, time=at_time, hq={base: {"destroyed": True, "by": by}})


def test_a_decapitation_reported_by_the_world_ends_the_campaign(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    raze(daemon, "v-1", "csat_kamino", by="WEST")

    assert daemon.campaign.outcome is not None
    assert daemon.campaign.outcome.winner == "WEST"


def test_the_world_is_told_once_that_the_campaign_is_over(tmp_path: Path) -> None:
    # Through the outbox, like every other world effect: a human-issued Campaign
    # and an AI-issued one end down the same path, and #19 has one to audit
    # (ADR-0012). Once, because the world keeps reporting rubble as rubble.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    raze(daemon, "v-2", "csat_kamino", by="WEST")
    raze(daemon, "v-3", "csat_kamino", by="WEST", at_time=95)

    (won,) = effects(daemon, "campaign_won")
    assert won["side"] == "WEST"
    assert won["args"]["condition"] == "decapitation"
    assert won["args"]["at"] == 90


def test_the_end_screen_carries_a_summary_drawn_from_telemetry(tmp_path: Path) -> None:
    # "End screen with a summary from telemetry" (docs/mvp-scope.md). The summary
    # rides the effect because the world is the thing that has a screen, and it
    # is read back off the telemetry file rather than assembled from campaign
    # state — which is the only way the numbers on it are the numbers on disk.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    reply_to(
        daemon,
        id="v-4",
        verb="command",
        payload={"command": "purchase", "side": "WEST", "args": {"squad_type": "rifle"}},
    )
    observe(daemon, "v-5", time=30, presence={"agia_marina": ["WEST"]})
    observe(daemon, "v-6", time=61, presence={"agia_marina": ["WEST"]})
    raze(daemon, "v-7", "csat_kamino", by="WEST", at_time=120)

    (won,) = effects(daemon, "campaign_won")
    summary = won["args"]["summary"]
    assert summary["winner"] == "WEST"
    assert summary["condition"] == "decapitation"
    assert summary["owners"]["agia_marina"] == "WEST"
    assert summary["commands"]["WEST"] == 1
    assert summary["income"]["WEST"] == 15
    assert summary["headquarters"] == [
        {"base": "csat_kamino", "side": "EAST", "by": "WEST", "at": 120}
    ]


def test_the_summary_is_small_enough_to_cross_one_extension_return(tmp_path: Path) -> None:
    # The effect travels in a poll reply, which is capped at 10,240 bytes and
    # truncated in silence (ADR-0004). A summary that counted rows rather than
    # listing them is what keeps this true of a long Campaign as well as a short
    # one, so the shape is asserted rather than the length alone.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    for index in range(200):
        observe(daemon, f"v-8-{index}", time=index, presence={"agia_marina": ["WEST"]})
    raze(daemon, "v-9", "csat_kamino", by="WEST", at_time=500)

    (won,) = effects(daemon, "campaign_won")
    assert len(json.dumps(won, separators=(",", ":"))) < 2_048


def test_a_won_campaign_is_written_down_and_archived(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    raze(daemon, "v-10", "csat_kamino", by="WEST")

    (won,) = rows(log, "campaign_won")
    assert (won["side"], won["condition"], won["at"]) == ("WEST", "decapitation", 90)

    (archived,) = rows(log, "campaign_archived")
    document = json.loads(Path(archived["path"]).read_text(encoding="utf-8"))
    assert document["winner"] == "WEST"
    assert document["condition"] == "decapitation"


def test_the_archive_is_a_record_rather_than_a_campaign_to_resume(tmp_path: Path) -> None:
    # ADR-0023: what is archived is what happened, not a state to load. A fresh
    # daemon on the same directory therefore starts a fresh Campaign — nothing
    # here reads the archive back, and there is nothing in it to read back.
    log = tmp_path / "telemetry.jsonl"
    raze(build_daemon(telemetry_path=log), "v-11", "csat_kamino", by="WEST")

    reborn = build_daemon(telemetry_path=log)
    assert reborn.campaign.outcome is None
    assert reborn.campaign.headquarters() == {"nato_airbase": "intact", "csat_kamino": "intact"}
    assert set(reborn.campaign.owners().values()) == {"NEUTRAL"}


def test_the_commanders_stand_down_when_the_campaign_is_over(tmp_path: Path) -> None:
    # An AI Commander that kept buying and ordering after the end screen would
    # spend a finished Campaign's Funds and fill the outbox the world has stopped
    # caring about.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    daemon.commanded_by(
        "WEST",
        planner.UtilityPlanner(
            map_manifest=daemon.campaign.map_manifest, table=daemon.campaign.table, seed=1
        ),
    )
    observe(daemon, "v-12", time=1, presence={})
    assert rows(log, "command_issued")

    raze(daemon, "v-13", "csat_kamino", by="WEST", at_time=10)
    before = len(rows(log, "command_issued"))
    observe(daemon, "v-14", time=20, presence={})
    assert len(rows(log, "command_issued")) == before


def test_a_human_command_after_the_end_screen_is_refused_on_the_wire(tmp_path: Path) -> None:
    # The other half of the stand-down above (#59). An AI Commander stops being
    # asked; a human is still holding a map screen and can still click, and the
    # gateway carries what it clicks to the same port. So the refusal is a
    # judgement with a code the game already knows — the map says why, rather
    # than the Command quietly spending a finished Campaign's Funds.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    raze(daemon, "v-17", "csat_kamino", by="WEST")
    funds = daemon.campaign.ledger.balance("WEST")

    reply = reply_to(
        daemon,
        id="v-18",
        verb="command",
        payload={"command": "purchase", "side": "WEST", "args": {"squad_type": "rifle"}},
    )

    assert reply["status"] == "rejected"
    assert reply["reason"]["code"] == "campaign_over"
    assert daemon.campaign.ledger.balance("WEST") == funds
    assert daemon.campaign.roster.roll("WEST") == ()
    assert effects(daemon, "squad_spawned") == []


def test_the_observation_reply_still_answers_after_the_campaign_ends(tmp_path: Path) -> None:
    # The world is still reporting and still waiting on a reply. A daemon that
    # stopped answering would hang the report loop rather than end a Campaign.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    raze(daemon, "v-15", "csat_kamino", by="WEST")
    reply = observe(daemon, "v-16", time=95, presence={"agia_marina": ["WEST"]})

    assert reply["hq"]["csat_kamino"] == "destroyed"
    assert reply["owners"]["agia_marina"] == "NEUTRAL"
