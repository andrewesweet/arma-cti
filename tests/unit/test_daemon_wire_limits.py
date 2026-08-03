"""What one reply may carry, and what a resent request may do twice.

Two halves of the same integration point (#58). A `callExtension` return is
capped at 10,240 bytes and truncated in silence (ADR-0004), so a drain the
daemon does not bound is effects lost with nothing said (#67). And the shim
resends a request whose exchange failed on its cached connection, so a write
that succeeded before the read failed is a Command carried out twice unless the
receiver refuses the second copy (#69, ADR-0034).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from conftest import REPO, reply_to, rows

from cti_daemon import budget
from cti_daemon.commands import Effect, serialise_effect
from cti_daemon.transport import build_daemon

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.daemon import Daemon


def encoded(daemon: Daemon, **envelope: object) -> str:
    """Send one request and return the line that goes back over the socket."""
    return daemon.handle_line(json.dumps(envelope))


def spawn_effect(index: int) -> Effect:
    """One real effect, the shape and size a Purchase actually queues."""
    return Effect(
        name="squad_spawned",
        side="WEST",
        args={"squad": f"WEST-{index}", "squad_type": "weapons", "size": 8},
    )


def test_the_drain_is_bounded_by_the_budget_module_rather_than_a_second_literal() -> None:
    # #164: the drain used to carry its own `POLL_GUARD_BYTES = 9_216`, held
    # equal to the budget's figure by a test — the two-literals-and-a-pairing-
    # test shape #78 took out of SQF, surviving one module from the one built to
    # own the wire caps. There is one figure now, so there is nothing left to
    # hold together: what `test_budget.py` pins about the number (nine tenths of
    # the cap, and exported to the world's own backstop) is what the drain is
    # bounded by, by construction. Pinned here is only that the drain reads it
    # from there rather than from a copy.
    source = (REPO / "src" / "cti_daemon" / "daemon.py").read_text(encoding="utf-8")
    assert "budget.REPORT_GUARD_BYTES" in source
    assert str(budget.REPORT_GUARD_BYTES) not in source


def test_one_poll_reply_stays_under_the_guard_however_long_the_backlog(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    for index in range(500):
        daemon.outbox.push(spawn_effect(index))

    line = encoded(daemon, id="w-1", verb="poll")
    assert len(line) < budget.REPORT_GUARD_BYTES


def test_the_drain_is_bounded_at_the_entry_that_would_have_crossed_the_guard(
    tmp_path: Path,
) -> None:
    # The boundary itself: one more entry than the reply carried would have put
    # it over. Without that, "under the guard" is satisfied by handing over one
    # message at a time.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    for index in range(500):
        daemon.outbox.push(spawn_effect(index))

    reply = reply_to(daemon, id="w-2", verb="poll")
    handed = reply["result"]["messages"]
    pending = daemon.outbox.pending()
    one_more = {
        "id": "w-2",
        "status": "ok",
        "result": {
            "messages": [
                *handed,
                {
                    "sequence": pending[len(handed)].sequence,
                    "message": serialise_effect(pending[len(handed)].effect),
                },
            ]
        },
    }
    assert len(json.dumps(one_more, separators=(",", ":"))) >= budget.REPORT_GUARD_BYTES


def test_one_drain_carries_a_measured_number_of_real_effects(tmp_path: Path) -> None:
    # The bound in the unit that matters at the other end. A `squad_spawned`
    # entry is 123 bytes on the wire, so the guard carries 72 of them in one
    # drain. ADR-0018 measured the largest drain two AI Commanders produced at 4
    # effects and the analytic worst case at 18, against the engine's
    # 100-callbacks-per-frame cap (ADR-0004) — so the byte guard sits above
    # ordinary play by 18 times and just under the frame cap, which is where a bound
    # on this path wants to be. It catches a runaway backlog rather than
    # throttling a busy one.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    for index in range(500):
        daemon.outbox.push(spawn_effect(index))

    handed = reply_to(daemon, id="w-3", verb="poll")["result"]["messages"]
    assert len(handed) > 18


def test_a_backlog_larger_than_one_reply_drains_across_polls_in_order(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    for index in range(200):
        daemon.outbox.push(spawn_effect(index))

    drained: list[int] = []
    for poll in range(20):
        messages = reply_to(daemon, id=f"w-4-{poll}", verb="poll")["result"]["messages"]
        if not messages:
            break
        drained.extend(entry["sequence"] for entry in messages)
        through = messages[-1]["sequence"]
        reply_to(daemon, id=f"w-5-{poll}", verb="ack", payload={"through": through})

    assert drained == list(range(1, 201))


def test_a_single_message_too_large_to_fit_is_a_loud_failure_not_a_truncation(
    tmp_path: Path,
) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    daemon.outbox.push(Effect(name="campaign_won", side="WEST", args={"blob": "x" * 20_000}))

    reply = reply_to(daemon, id="w-6", verb="poll")
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "oversized_message"
    assert "1" in reply["error"]["detail"]
    assert rows(log, "outbox_oversized")


def test_an_oversized_message_does_not_hide_the_backlog_behind_it(tmp_path: Path) -> None:
    # It stalls it, loudly, and stays on the outbox. Retiring it to get at what
    # is behind would be the silent loss the guard exists to prevent.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push(Effect(name="campaign_won", side="WEST", args={"blob": "x" * 20_000}))
    daemon.outbox.push(spawn_effect(1))

    assert reply_to(daemon, id="w-7", verb="poll")["status"] == "error"
    assert len(daemon.outbox.pending()) == 2


def test_the_drain_telemetry_says_how_much_was_left_behind(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    for index in range(500):
        daemon.outbox.push(spawn_effect(index))

    handed = reply_to(daemon, id="w-8", verb="poll")["result"]["messages"]
    (row,) = rows(log, "outbox_handed")
    assert row["handed"] == len(handed)
    assert row["deferred"] == 500 - len(handed)


def purchase(daemon: Daemon, request_id: str, side: str = "WEST") -> dict[str, Any]:
    """One Purchase, sent under the id the caller names."""
    return reply_to(
        daemon,
        id=request_id,
        verb="command",
        payload={
            "command": "purchase",
            "side": side,
            "acting_side": side,
            "args": {"squad_type": "rifle"},
        },
    )


def test_a_resent_purchase_spends_funds_once(tmp_path: Path) -> None:
    # The #69 hazard end to end: the shim wrote the line, the read failed, and
    # it sent the identical line again on a fresh connection. The receiver is
    # what makes that safe — the second copy is answered from the first answer.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    first = purchase(daemon, "cmd-1")
    second = purchase(daemon, "cmd-1")

    assert first == second
    assert daemon.campaign.ledger.balance("WEST") == 200
    assert len(daemon.campaign.roster.roll("WEST")) == 1


def test_a_resent_purchase_queues_its_effect_once(tmp_path: Path) -> None:
    # Not just the Funds: a second `squad_spawned` on the outbox is a second
    # Squad in the world, which is the same duplicate arriving one path along.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    purchase(daemon, "cmd-2")
    purchase(daemon, "cmd-2")

    assert len(daemon.outbox.pending()) == 1


def test_a_replayed_request_is_written_down_as_a_replay(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    purchase(daemon, "cmd-3")
    purchase(daemon, "cmd-3")

    (replayed,) = rows(log, "request_replayed")
    assert replayed["id"] == "cmd-3"
    assert replayed["verb"] == "command"


def test_a_different_request_under_a_reused_id_is_carried_out(tmp_path: Path) -> None:
    # The key is the request, not the label on it. A resend is byte-identical by
    # construction; anything else is a different request whose caller reused an
    # id, and refusing to act on it would lose real work.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    purchase(daemon, "cmd-4", side="WEST")
    purchase(daemon, "cmd-4", side="EAST")

    assert daemon.campaign.ledger.balance("WEST") == 200
    assert daemon.campaign.ledger.balance("EAST") == 200


def test_a_resent_report_does_not_give_the_commanders_a_second_turn(tmp_path: Path) -> None:
    # `observe` is state-changing too: it folds the world's report and then each
    # AI Commander plays on it. A resent report played twice is a Commander
    # taking two turns on one report and spending twice.
    from cti_daemon import planner  # noqa: PLC0415 — one test needs a Commander

    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.commanded_by(
        "WEST",
        planner.UtilityPlanner(
            map_manifest=daemon.campaign.map_manifest,
            table=daemon.campaign.table,
            seed=7,
        ),
    )
    report: dict[str, object] = {"time": 30, "presence": {}}
    first = reply_to(daemon, id="obs-1", verb="observe", payload=report)
    spent_once = daemon.campaign.ledger.balance("WEST")
    second = reply_to(daemon, id="obs-1", verb="observe", payload=report)

    assert first == second
    assert daemon.campaign.ledger.balance("WEST") == spent_once


def test_the_window_of_remembered_answers_is_bounded(tmp_path: Path) -> None:
    # A dedupe window that grew without limit would be a leak on a session-long
    # process. The shim only ever resends the request it just sent, so the
    # window has one request's worth of work to do and a few hundred is already
    # generous.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    for index in range(1_000):
        reply_to(daemon, id=f"ping-{index}", verb="ping")

    assert len(daemon.answered) <= 512
