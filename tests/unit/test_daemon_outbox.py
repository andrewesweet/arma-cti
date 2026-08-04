"""Delivery guarantees for messages the daemon pushes to the game.

ADR-0005: callback delivery is at-most-once across mission boundaries — a
callback fired before a handler exists sits in the engine buffer, and a mission
restart clears it. Nothing downstream can recover a message that was dropped
there, so the daemon holds every pushed message until the game says it arrived.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from conftest import live, reply_to, rows

from cti_daemon.commands import EFFECTS, Effect, serialise_effect
from cti_daemon.daemon import OUTBOX_DEPTH_STEP
from cti_daemon.outbox import Outbox, UnknownSequenceError
from cti_daemon.transport import build_daemon

if TYPE_CHECKING:
    from pathlib import Path


def order(n: int = 0) -> Effect:
    """One Effect, the domain object the outbox now holds (#77), catalogue-shaped (#145)."""
    return Effect(
        name="order_issued",
        side="WEST",
        args={"squad": f"WEST-{n}", "order": "reserve", "place": ""},
    )


def test_a_pushed_message_is_pending_until_it_is_acknowledged() -> None:
    outbox = Outbox()
    outbox.push(order())
    assert [entry.effect for entry in outbox.pending()] == [order()]


def test_sequence_numbers_are_issued_in_order_from_one() -> None:
    outbox = Outbox()
    assert [outbox.push(order(n)).sequence for n in range(3)] == [1, 2, 3]


def test_acknowledging_a_sequence_clears_it_and_everything_before_it() -> None:
    outbox = Outbox()
    for n in range(4):
        outbox.push(order(n))
    outbox.ack(through=2)
    assert [entry.sequence for entry in outbox.pending()] == [3, 4]


def test_an_unacknowledged_message_is_delivered_again() -> None:
    # The mission restarted, the engine buffer was cleared, and the game asks
    # again from where it last acknowledged. Nothing is lost.
    outbox = Outbox()
    outbox.push(order(1))
    outbox.push(order(2))
    outbox.ack(through=1)
    first_retry = [entry.sequence for entry in outbox.pending()]
    second_retry = [entry.sequence for entry in outbox.pending()]
    assert first_retry == second_retry == [2]


def test_a_redelivered_squad_spawn_carries_the_same_squad_id() -> None:
    # The daemon's half of #141. The world deduplicates a redelivered effect by
    # the Squad id it carries (`fn_effectApply`), and that only works because
    # this side re-hands the *same* effect rather than a fresh rendering of the
    # same intent: the outbox holds the `Effect` object the Purchase minted, so
    # every redelivery of an unacknowledged `squad_spawned` renders identically,
    # down to the id the roster minted once.
    #
    # Asserted through a real Purchase rather than a hand-built Effect, because
    # what is being claimed is end-to-end: the id the world dedupes on is the id
    # the roster minted, and nothing between the two re-mints it.
    campaign = live()
    squad, _ = campaign.purchase("WEST", "rifle")

    handed = [serialise_effect(entry.effect) for entry in campaign.outbox.pending()]
    again = [serialise_effect(entry.effect) for entry in campaign.outbox.pending()]

    assert handed == again
    assert [message["effect"] for message in handed] == ["squad_spawned"]
    assert handed[0]["args"]["squad"] == squad.id


def test_redelivery_does_not_mint_a_second_squad() -> None:
    # The other half of the same claim, and the reason the guard belongs in the
    # world rather than here: an unacknowledged effect being handed over again
    # is a read of the outbox, so the daemon's roster still holds exactly the
    # one Squad it was paid for however many times the world is told about it.
    # The daemon therefore cannot see the duplicate the world would make, which
    # is what made #141 silent.
    campaign = live()
    campaign.purchase("WEST", "rifle")

    for _ in range(3):
        assert [entry.sequence for entry in campaign.outbox.pending()] == [1]
    assert [squad.id for squad in campaign.roster.roll("WEST")] == ["WEST-1"]


def test_acknowledging_twice_is_not_an_error() -> None:
    # At-most-once delivery means a duplicate ack is expected, not a fault.
    outbox = Outbox()
    outbox.push(order(1))
    assert outbox.ack(through=1) == 1
    assert outbox.ack(through=1) == 0


def test_acknowledging_a_sequence_that_was_never_issued_is_refused() -> None:
    outbox = Outbox()
    outbox.push(order(1))
    with pytest.raises(UnknownSequenceError):
        outbox.ack(through=9)


def test_an_effect_the_catalogue_does_not_declare_is_refused_at_the_door() -> None:
    # #145: this is the one path every world effect takes (ADR-0012), so the
    # catalogue binding here binds every producer, present and future — the
    # outbound half of what #74 did for the inbound path. Raised rather than
    # rejected, because an out-of-catalogue Effect is a producer's bug, not a
    # payload some caller sent.
    with pytest.raises(ValueError, match="arsenal_opened"):
        Outbox().push(Effect(name="arsenal_opened", side="WEST", args={}))


@pytest.mark.parametrize(
    "args",
    [
        pytest.param({"squad": "WEST-1", "order": "reserve"}, id="a declared argument missing"),
        pytest.param(
            {"squad": "WEST-1", "order": "reserve", "place": "", "speed": "fast"},
            id="an argument the catalogue does not declare",
        ),
        pytest.param({}, id="no arguments at all"),
    ],
)
def test_an_effect_whose_args_are_not_its_catalogue_entrys_is_refused(
    args: dict[str, str],
) -> None:
    # Exactly the declared set, not a superset: an extra argument riding a real
    # effect is the same undeclared schema a whole undeclared effect is.
    with pytest.raises(ValueError, match="order_issued"):
        Outbox().push(Effect(name="order_issued", side="WEST", args=args))


def test_every_effect_in_the_catalogue_is_accepted_with_exactly_its_declared_args() -> None:
    # The guard refuses drift, never the catalogue itself: every declared
    # effect, built with exactly its declared arguments, goes through.
    outbox = Outbox()
    for name, declared in EFFECTS.items():
        outbox.push(Effect(name=name, side="WEST", args=dict.fromkeys(declared, "x")))
    assert outbox.depth == len(EFFECTS)


def test_depth_counts_what_is_still_waiting() -> None:
    outbox = Outbox()
    for n in range(3):
        outbox.push(order(n))
    outbox.ack(through=1)
    assert outbox.depth == 2


# The gauge (#142). `outbox_handed` is written on a successful drain only, so
# the failure that matters — the pump dead while both Commanders keep buying
# (#102, #125) — is the one that writes no row at all.


def test_growth_is_visible_in_telemetry_without_a_single_successful_poll(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    for n in range(OUTBOX_DEPTH_STEP):
        daemon.outbox.push(order(n))

    # Any request will do: the depth is gauged wherever it can have changed, and
    # nothing here polls.
    reply_to(daemon, id="g-1", verb="ping")

    assert not rows(log, "outbox_handed"), "this test must not have drained anything"
    (row,) = rows(log, "outbox_depth")
    assert row["depth"] == OUTBOX_DEPTH_STEP
    assert row["step"] == OUTBOX_DEPTH_STEP
    assert row["epoch"] == daemon.epoch


def test_a_backlog_below_the_step_is_not_worth_a_row(tmp_path: Path) -> None:
    # A row per request would bury the log this is written to, and a handful of
    # undelivered effects between two polls is the ordinary case.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    for n in range(OUTBOX_DEPTH_STEP - 1):
        daemon.outbox.push(order(n))
        reply_to(daemon, id=f"g-{n}", verb="ping")

    assert not rows(log, "outbox_depth")


def test_each_further_band_is_announced_once(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    for n in range(3 * OUTBOX_DEPTH_STEP):
        daemon.outbox.push(order(n))
        reply_to(daemon, id=f"g-{n}", verb="ping")

    assert [row["depth"] for row in rows(log, "outbox_depth")] == [
        OUTBOX_DEPTH_STEP,
        2 * OUTBOX_DEPTH_STEP,
        3 * OUTBOX_DEPTH_STEP,
    ]


def test_a_backlog_that_cleared_says_so_too(tmp_path: Path) -> None:
    # Downwards as well as up: an operator reading a growth row needs to know
    # whether it ever came back, and silence would read as "still deep".
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    for n in range(OUTBOX_DEPTH_STEP):
        daemon.outbox.push(order(n))
    reply_to(daemon, id="g-1", verb="ping")

    reply_to(daemon, id="g-2", verb="ack", payload={"through": OUTBOX_DEPTH_STEP})

    assert [row["depth"] for row in rows(log, "outbox_depth")] == [OUTBOX_DEPTH_STEP, 0]
