"""An AI Commander driving one side through the daemon (#16).

The planner is exercised on its own in `test_planner.py`. What is pinned here is
the wiring: that a Commander left alone plays, that it plays through the same
Command Port a human does and no other path, and that everything it decided
lands in telemetry as observability and nothing else (ADR-0003).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cti_daemon import planner, transport
from cti_daemon.commands import Command
from cti_daemon.planner import Candidate, Decision, Plan
from cti_daemon.transport import build_daemon

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.daemon import Daemon
    from cti_daemon.observation import Observation

SIDE = "WEST"


def reply_to(daemon: Daemon, **envelope: object) -> dict[str, Any]:
    """Send one request and return its decoded reply."""
    return json.loads(daemon.handle_line(json.dumps(envelope)))


def commanded(path: Path, brain: planner.Planner | None = None, seed: int = 0) -> Daemon:
    """Return a daemon with WEST under an AI Commander."""
    daemon = build_daemon(telemetry_path=path)
    daemon.commanded_by(
        SIDE,
        brain
        or planner.UtilityPlanner(
            map_manifest=daemon.campaign.map_manifest, table=daemon.campaign.table, seed=seed
        ),
    )
    return daemon


def turn(daemon: Daemon, step: int) -> dict[str, Any]:
    """One turn of a world that spawns what it is told and goes where it is sent.

    A stand-in for Arma, and only for Arma: the campaign, the port and the
    planner are the real ones, and this supplies the two facts only the world
    can report — who is standing where, and what has become of each Squad.
    """
    roll = daemon.campaign.roster.roll(SIDE)
    presence: dict[str, list[str]] = {}
    for squad in roll:
        if squad.order.place:
            presence.setdefault(squad.order.place, []).append(SIDE)
    return reply_to(
        daemon,
        id=f"turn-{step}",
        verb="observe",
        payload={
            "time": (step + 1) * 30,
            "presence": presence,
            "squads": {squad.id: {"size": squad.size, "at": squad.order.place} for squad in roll},
        },
    )["result"]


def rows(path: Path, event: str) -> list[dict[str, Any]]:
    """Return the telemetry rows of one kind."""
    return [
        record
        for line in path.read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line))["event"] == event
    ]


def test_an_ai_commander_left_alone_buys_squads_and_takes_ground(tmp_path: Path) -> None:
    # The demoable thing #16 asks for: nobody sends a Command, and the side
    # still fields an army and starts taking the island. Driven only by the
    # world's report, which is the one cadence there is (ADR-0005).
    daemon = commanded(tmp_path / "telemetry.jsonl")
    owners: dict[str, str] = {}
    for step in range(8):
        owners = turn(daemon, step)["owners"]

    assert len(daemon.campaign.roster.roll(SIDE)) > 1
    assert SIDE in owners.values()
    effects = [entry.effect.name for entry in daemon.outbox.pending()]
    assert {"squad_spawned", "order_issued", "objective_captured"} <= set(effects)


def test_a_commander_reacts_when_ground_changes_hands(tmp_path: Path) -> None:
    # Capture is for ground the side does not hold, so an Objective it has just
    # taken has to stop being a target — otherwise the port refuses the Order
    # and the Squad stands still under one that was never accepted.
    daemon = commanded(tmp_path / "telemetry.jsonl")
    for step in range(8):
        turn(daemon, step)

    held = {name for name, owner in daemon.campaign.owners().items() if owner == SIDE}
    assert held
    ordered = {
        squad.order.place
        for squad in daemon.campaign.roster.roll(SIDE)
        if squad.order.kind == "capture"
    }
    assert ordered.isdisjoint(held)


def test_every_decision_lands_in_telemetry_with_what_it_was_weighed_against(
    tmp_path: Path,
) -> None:
    # The flight recorder for "why did the AI do that" (ADR-0004): what was
    # scored, what won, and why. A choice on its own is not a trace.
    log = tmp_path / "telemetry.jsonl"
    daemon = commanded(log)
    for step in range(3):
        turn(daemon, step)

    decisions = rows(log, "decision")
    assert {decision["about"] for decision in decisions} >= {"funds", "WEST-1"}
    chosen = next(row for row in decisions if row["about"] == "WEST-1")
    assert chosen["side"] == SIDE
    assert chosen["because"]
    assert chosen["scored"] >= len(chosen["candidates"]) > 0
    assert set(chosen["candidates"][0]) == {"choice", "score", "terms"}
    assert chosen["chose"] == chosen["candidates"][0]["choice"]


def test_a_trace_nobody_could_write_changes_nothing_about_the_campaign(
    tmp_path: Path,
) -> None:
    # ADR-0003: telemetry is never an input to campaign state, and a decision
    # trace is telemetry. Asked the only way that answers it — by taking the log
    # away entirely. A planner that read its own trace back would diverge here.
    written = commanded(tmp_path / "telemetry.jsonl")
    silent = commanded(tmp_path / "no-such-directory" / "telemetry.jsonl")
    for step in range(6):
        turn(written, step)
        turn(silent, step)

    assert written.campaign.owners() == silent.campaign.owners()
    assert [(squad.id, squad.order) for squad in written.campaign.roster.roll(SIDE)] == [
        (squad.id, squad.order) for squad in silent.campaign.roster.roll(SIDE)
    ]


class Contrarian:
    """A planner that is not the scorer, to prove the daemon does not know one."""

    def plan(self, observation: Observation) -> Plan:
        """Purchase a weapons Squad on sight and explain itself in the same shape."""
        return Plan(
            commands=(Command("purchase", observation.for_side, {"squad_type": "weapons"}),),
            decisions=(
                Decision(
                    about="funds",
                    chose="purchase weapons",
                    because="because I say so",
                    scored=1,
                    candidates=(
                        Candidate(choice="purchase weapons", score=1.0, terms={"whim": 1.0}),
                    ),
                ),
            ),
        )


def test_a_different_planner_drives_the_same_port_and_the_same_trace(tmp_path: Path) -> None:
    # ADR-0004 names HTN as the escalation and an LLM as post-MVP, and #16 asks
    # that neither change the port or the trace format. Held by handing the
    # daemon something that scores nothing at all.
    log = tmp_path / "telemetry.jsonl"
    daemon = commanded(log, brain=Contrarian())
    turn(daemon, 0)

    assert [squad.squad_type for squad in daemon.campaign.roster.roll(SIDE)] == ["weapons"]
    (decision,) = rows(log, "decision")
    assert decision["chose"] == "purchase weapons"
    assert decision["candidates"] == [
        {"choice": "purchase weapons", "score": 1.0, "terms": {"whim": 1.0}}
    ]


class Overreacher:
    """A planner with a bug in it: it orders a Squad that does not exist."""

    def plan(self, observation: Observation) -> Plan:
        """Order a Squad nobody bought."""
        return Plan(
            commands=(
                Command(
                    "order",
                    observation.for_side,
                    {"squad": "WEST-99", "order": "capture", "place": "girna"},
                ),
            ),
            decisions=(),
        )


def test_a_command_the_port_refuses_is_recorded_rather_than_swallowed(tmp_path: Path) -> None:
    # A planner bug, and the port is where it surfaces. It must not stop the
    # world being told who owns what — the report loop is how the map is
    # painted — so it is written down and the cycle finishes.
    log = tmp_path / "telemetry.jsonl"
    daemon = commanded(log, brain=Overreacher())

    assert "owners" in turn(daemon, 0)
    (refused,) = rows(log, "plan_refused")
    assert refused["code"] == "unknown_squad"
    assert refused["side"] == SIDE


def test_a_daemon_under_nobodys_command_plans_nothing(tmp_path: Path) -> None:
    # #16 drives one side; the other is the human's, or #17's. A daemon nobody
    # has put under command must not quietly start playing for somebody.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    for step in range(4):
        turn(daemon, step)

    assert daemon.campaign.roster.roll(SIDE) == ()
    assert rows(log, "decision") == []


def test_the_daemon_can_be_brought_up_under_an_ai_commander(tmp_path: Path) -> None:
    # How a session actually starts one (#16's demoable): a flag at bring-up,
    # and nothing else to remember. The seed is a flag too, because Phase 2 has
    # to be able to resume a Campaign into the character it had.
    daemon = transport.build(tmp_path / "telemetry.jsonl", ai=[(SIDE, 3)])
    for step in range(4):
        turn(daemon, step)

    assert daemon.campaign.roster.roll(SIDE) != ()
    assert daemon.commanders == (SIDE,)
    assert transport.build(tmp_path / "telemetry.jsonl", ai=None).commanders == ()
