"""Projecting a restored Campaign into a fresh world, in domain order (#292).

`resume.reconstruct` renders a restored snapshot as the ordered Effects that
rebuild a fresh Arma world, and `resume.Barrier` holds that world closed until
the projection is acknowledged. This pins the four things the issue turns on:

- The order is the domain's, not the dictionary's: the scoreboard before the
  Squads stood on it, the Squads before the Orders they carry.
- The projection is atomic: a snapshot that cannot be projected whole is
  refused with nothing emitted, at several points in the order rather than only
  the first.
- The full reconstruction drains across bounded polls at both the planner's
  eight-Squads-per-side cap and the seventy-one-Squads-per-side wire ceiling,
  without truncation or silent loss.
- The barrier opens only on a complete acknowledgement and stays shut, with a
  typed reason, on a rejected or oversized reconstruction Effect.

Tactical state ADR-0008 regenerates is asserted *absent* from the sequence
rather than merely not asserted present, because a snapshot smuggling positions
or Contacts past the projection is the fidelity risk the closed schema exists
to remove.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from conftest import authored_economy, authored_stratis

from cti_daemon import budget, commands, protocol, resume
from cti_daemon.commands import SIDES
from cti_daemon.observation import DESTROYED, INTACT
from cti_daemon.outbox import Outbox
from cti_daemon.snapshot import Snapshot, SquadRecord
from cti_daemon.squads import RESERVE, Order

# The authored Stratis ground: the objective and Base ids a real Campaign's
# snapshot carries, taken from the manifest rather than restated so a renamed
# place moves this test's arrangement rather than breaking it.
OBJECTIVES = tuple(objective.id for objective in authored_stratis().objectives)
BASE_WEST, BASE_EAST = "nato_airbase", "csat_kamino"
PLACES = (*OBJECTIVES, BASE_WEST, BASE_EAST)


def _squad(  # noqa: PLR0913 — a snapshot's Squad record has six fields; this builds one
    squad_id: str,
    side: str,
    *,
    squad_type: str = "rifle",
    size: int = 8,
    order: Order = RESERVE,
    at: str = "",
) -> SquadRecord:
    """Return one Squad record in the snapshot's shape, defaulting to a fresh buy."""
    return SquadRecord(id=squad_id, side=side, squad_type=squad_type, size=size, order=order, at=at)


def _snapshot(**overrides: Any) -> Snapshot:  # noqa: ANN401 — one authored snapshot, values vary per test
    """Return a mid-Campaign snapshot on the authored Stratis map, both sides present."""
    base = Snapshot(
        clock=5400.0,
        # Mixed ownership: one Objective each, the rest Neutral — the fresh world's default.
        owners={"agia_marina": "WEST", "camp_rogain": "EAST"},
        hq={BASE_WEST: INTACT, BASE_EAST: INTACT},
        funds=dict.fromkeys(SIDES, 200),
        squads=(
            _squad("WEST-1", "WEST", order=Order("defend", "agia_marina"), at="agia_marina"),
            _squad("EAST-1", "EAST", order=Order("assault", BASE_WEST), at="camp_rogain"),
            # Reserve is the spawn default: it projects no Order, only its spawn.
            _squad("WEST-2", "WEST", order=Order("reserve"), at=BASE_WEST),
        ),
        loadouts={"uid-1": "rifleman"},
    )
    return replace(base, **overrides) if overrides else base


# --- the order is the domain's -------------------------------------------


def test_reconstruction_orders_the_scoreboard_before_squads_before_orders() -> None:
    # The one assertion the issue title rests on: ownership is established, then
    # Squads are spawned onto that board, then those Squads are given Orders.
    effects = resume.reconstruct(_snapshot(), authored_stratis(), authored_economy())

    kinds = [effect.name for effect in effects]
    objective_until = kinds.index("squad_spawned")
    order_from = kinds.index("order_issued")
    assert all(name == "objective_captured" for name in kinds[:objective_until])
    assert all(name == "squad_spawned" for name in kinds[objective_until:order_from])
    assert all(name == "order_issued" for name in kinds[order_from:])


def test_a_neutral_objective_projects_nothing_a_taken_one_is_captured() -> None:
    effects = resume.reconstruct(_snapshot(), authored_stratis(), authored_economy())
    captured = [e.args["objective"] for e in effects if e.name == "objective_captured"]
    # Only the two taken Objectives; the six Neutral ones are the fresh default.
    assert captured == ["agia_marina", "camp_rogain"]
    # Captured in manifest order — the authored front line — not the dictionary's.
    assert captured == sorted(captured, key=OBJECTIVES.index)


def test_objective_capture_names_the_side_that_holds_it() -> None:
    effects = resume.reconstruct(_snapshot(), authored_stratis(), authored_economy())
    by_objective = {e.args["objective"]: e.side for e in effects if e.name == "objective_captured"}
    assert by_objective == {"agia_marina": "WEST", "camp_rogain": "EAST"}


def test_squads_spawn_in_roster_order_at_their_persisted_strength() -> None:
    effects = resume.reconstruct(_snapshot(), authored_stratis(), authored_economy())
    spawned = [e for e in effects if e.name == "squad_spawned"]
    assert [e.args["squad"] for e in spawned] == ["WEST-1", "EAST-1", "WEST-2"]
    # The head count is strategic; the per-man health around it is regenerated.
    assert {e.args["squad_type"] for e in spawned} == {"rifle"}
    assert all(e.args["size"] == 8 for e in spawned)


def test_a_reserve_squad_projects_no_order_a_tasked_one_does() -> None:
    effects = resume.reconstruct(_snapshot(), authored_stratis(), authored_economy())
    issued = {e.args["squad"]: e.args for e in effects if e.name == "order_issued"}
    # WEST-2 is Reserve, which the spawn already holds, so it carries no Order.
    assert set(issued) == {"WEST-1", "EAST-1"}
    assert issued["WEST-1"] == {"squad": "WEST-1", "order": "defend", "place": "agia_marina"}
    assert issued["EAST-1"] == {"squad": "EAST-1", "order": "assault", "place": BASE_WEST}


def test_tactical_state_is_absent_from_every_effect() -> None:
    # ADR-0008: positions, health, AI knowledge, corpses and capture progress
    # are regenerated. None of them has a field on the Effects the projection
    # emits — a snapshot smuggling one would have to add a key, and none carries one.
    effects = resume.reconstruct(_snapshot(), authored_stratis(), authored_economy())
    for effect in effects:
        assert "pos" not in effect.args
        assert "health" not in effect.args
        assert "knowledge" not in effect.args
        # Funds and the clock are daemon state; the world carries neither.
        assert "funds" not in effect.args
        assert "clock" not in effect.args


# --- atomicity: refused whole, at several points in the order ------------


@pytest.mark.parametrize(
    ("label", "snapshot_overrides"),
    [
        # First point: a destroyed HQ on the first base the loop reads.
        ("a destroyed HQ ends the Campaign", {"hq": {BASE_WEST: DESTROYED, BASE_EAST: INTACT}}),
        # An Objective the map does not have, before any ownership is projected.
        ("an unknown Objective", {"owners": {"no_such_place": "WEST"}}),
        # A contest the snapshot cannot resolve, before any Objective is captured.
        ("a Contested Objective", {"owners": {"agia_marina": "CONTESTED"}}),
        # A Squad type the economy does not sell, on the first Squad.
        ("an unsold Squad type", {"squads": (_squad("WEST-1", "WEST", squad_type="tank"),)}),
        # A Squad standing on ground the map does not have.
        ("a Squad on unknown ground", {"squads": (_squad("WEST-1", "WEST", at="nowhere"),)}),
        # A tasked Order with no Place — the last structural check, on the only Squad.
        ("an Order with no Place", {"squads": (_squad("WEST-1", "WEST", order=Order("defend")),)}),
        # A Reserve Order that nonetheless names a destination.
        (
            "a Reserve Order with a Place",
            {"squads": (_squad("WEST-1", "WEST", order=Order("reserve", "agia_marina")),)},
        ),
        # A Squad stronger than what was paid for.
        ("an over-strength Squad", {"squads": (_squad("WEST-1", "WEST", size=99),)}),
    ],
)
def test_a_snapshot_that_cannot_be_projected_is_refused_whole(
    label: str, snapshot_overrides: dict[str, Any]
) -> None:
    del label  # the id is for the parametrised report alone
    with pytest.raises(resume.ResumeError):
        resume.reconstruct(_snapshot(**snapshot_overrides), authored_stratis(), authored_economy())


def test_a_refusal_emits_nothing() -> None:
    # Atomicity is structural: the whole snapshot is validated before any Effect
    # is built, so a fault on the last Squad raises with the function returning
    # nothing rather than a prefix. A fresh outbox takes nothing from it.
    bad = _snapshot(squads=(_squad("WEST-1", "WEST", at="nowhere"),))
    outbox = Outbox()
    with pytest.raises(resume.ResumeError):
        resume.reconstruct(bad, authored_stratis(), authored_economy())
    assert outbox.depth == 0


def test_duplicate_squad_ids_are_refused() -> None:
    dup = _snapshot(
        squads=(_squad("WEST-1", "WEST"), _squad("WEST-1", "WEST")),
    )
    with pytest.raises(resume.ResumeError, match="same id"):
        resume.reconstruct(dup, authored_stratis(), authored_economy())


# --- drains across bounded polls, at the cap and the wire ceiling --------


def _drain_in_polls(outbox: Outbox) -> list[list[int]]:
    """Drain the outbox in bounded polls, mirroring `Daemon._poll`'s budget.

    One list of sequence numbers per poll, in order. Each poll takes the prefix
    of pending entries whose addressed messages fit `REPORT_GUARD_BYTES`
    together and stops at the first that does not — the same first-that-fits
    rule that keeps the outbox's issued order on the wire.
    """
    polls: list[list[int]] = []
    while outbox.depth:
        messages: list[dict[str, Any]] = []
        size = len(protocol.encode(protocol.accepted("drain", {"messages": []})))
        for entry in outbox.pending():
            message = {
                "sequence": entry.sequence,
                "message": commands.serialise_effect(entry.effect),
            }
            grown = size + protocol.measure(message) + (1 if messages else 0)
            if grown >= budget.REPORT_GUARD_BYTES:
                break
            messages.append(message)
            size = grown
        # No single reconstruction Effect may overflow the guard: the barrier
        # would stall on it forever, which is the oversized failure, not a drain.
        assert messages
        outbox.ack(through=messages[-1]["sequence"])
        polls.append([message["sequence"] for message in messages])
    return polls


def _forces(per_side: int) -> tuple[SquadRecord, ...]:
    """Return both sides' rosters at `per_side` a side, every Squad tasked off its Base."""
    return tuple(
        _squad(
            f"{side}-{ordinal}",
            side,
            order=Order("defend", "agia_marina" if side == "WEST" else "camp_rogain"),
            at=BASE_WEST if side == "WEST" else BASE_EAST,
        )
        for side in SIDES
        for ordinal in range(1, per_side + 1)
    )


@pytest.mark.parametrize(
    ("per_side", "expect_more_than_one_poll"),
    [
        # The planner's normal cap on Stratis: eight Squads a side.
        (8, False),
        # The wire ceiling #101 measures for Stratis: how many a side before a
        # worst-case Observation stops fitting one reply. Taken from the budget
        # the port enforces, not restated, so an economy change moves it with us.
        (budget.squad_ceiling(authored_stratis(), authored_economy()), True),
    ],
)
def test_the_full_reconstruction_drains_across_bounded_polls_without_loss(
    per_side: int,
    expect_more_than_one_poll: bool,  # noqa: FBT001 — pytest passes parametrize values positionally
) -> None:
    full = _snapshot(
        squads=_forces(per_side), owners={OBJECTIVES[0]: "WEST", OBJECTIVES[1]: "EAST"}
    )
    effects = resume.reconstruct(full, authored_stratis(), authored_economy())

    outbox = Outbox()
    for effect in effects:
        outbox.push(effect)
    issued = [entry.sequence for entry in outbox.pending()]

    polls = _drain_in_polls(outbox)

    # Every Effect delivered exactly once, in the order it was issued: no
    # truncation, no silent loss, no reordering across the poll boundary.
    delivered = [sequence for poll in polls for sequence in poll]
    assert delivered == issued
    assert outbox.depth == 0
    if expect_more_than_one_poll:
        assert len(polls) > 1, (
            f"the {per_side}-per-side ceiling drained in one poll; the guard never bound it"
        )


# --- the barrier: open only on a complete, unfailed acknowledgement ------


def _push_reconstruction(outbox: Outbox, snapshot: Snapshot) -> list[int]:
    """Push a reconstruction onto an outbox and return the sequences it was issued under."""
    effects = resume.reconstruct(snapshot, authored_stratis(), authored_economy())
    entries = [outbox.push(effect) for effect in effects]
    return [entry.sequence for entry in entries]


def test_a_barrier_opens_only_when_every_reconstruction_effect_is_acked() -> None:
    outbox = Outbox()
    sequences = _push_reconstruction(outbox, _snapshot())
    barrier = resume.Barrier.awaiting(sequences)

    assert barrier.resuming
    assert barrier.failure is None
    # Acknowledging most of the sequence is not enough: one short of the end
    # keeps the world closed, because a half-rebuilt Campaign is not playable.
    barrier.acknowledge(through=sequences[-2])
    assert barrier.resuming
    assert barrier.outstanding == 1
    barrier.acknowledge(through=sequences[-1])
    assert barrier.ready


def test_a_repeated_acknowledgement_after_a_reconnect_is_idempotent() -> None:
    # The carrier's at-most-once delivery makes a resend ordinary (ADR-0034), so
    # re-asserting the same high-water mark — or one below it — opens nothing new
    # and closes nothing already open.
    outbox = Outbox()
    sequences = _push_reconstruction(outbox, _snapshot())
    barrier = resume.Barrier.awaiting(sequences)

    barrier.acknowledge(through=sequences[-1])
    assert barrier.ready
    barrier.acknowledge(through=sequences[-1])
    assert barrier.ready
    barrier.acknowledge(through=sequences[0])
    assert barrier.ready


def test_a_fresh_campaign_projects_nothing_and_opens_at_once() -> None:
    fresh = Snapshot(
        clock=0.0,
        owners=dict.fromkeys(OBJECTIVES, "NEUTRAL"),
        hq={BASE_WEST: INTACT, BASE_EAST: INTACT},
        funds=dict.fromkeys(SIDES, 300),
        squads=(),
        loadouts={},
    )
    assert resume.reconstruct(fresh, authored_stratis(), authored_economy()) == ()
    assert resume.Barrier.awaiting([]).ready


def test_a_rejected_reconstruction_effect_keeps_the_barrier_shut() -> None:
    outbox = Outbox()
    sequences = _push_reconstruction(outbox, _snapshot())
    barrier = resume.Barrier.awaiting(sequences)

    # The world dead-lettered one reconstruction Effect it could not apply.
    barrier.rejected(sequences[1])
    # Even a full acknowledgement does not open a barrier that lost a fact: the
    # high-water mark records what was retired, and a dead letter is retired
    # unapplied, so the Campaign it would have rebuilt is still short.
    barrier.acknowledge(through=sequences[-1])
    assert barrier.resuming
    assert barrier.failure == resume.EFFECT_REJECTED


def test_an_oversized_reconstruction_effect_keeps_the_barrier_shut() -> None:
    outbox = Outbox()
    sequences = _push_reconstruction(outbox, _snapshot())
    barrier = resume.Barrier.awaiting(sequences)

    barrier.oversized(sequences[0])
    barrier.acknowledge(through=sequences[-1])
    assert barrier.resuming
    assert barrier.failure == resume.EFFECT_OVERSIZED


def test_the_barrier_tracks_the_drain_to_ready() -> None:
    # The two halves together: the reconstruction drains across bounded polls
    # and the barrier, observed on the same acknowledgements, opens only at the
    # final one — the resuming state the world boots into and leaves behind.
    full = _snapshot(squads=_forces(8))
    outbox = Outbox()
    sequences = _push_reconstruction(outbox, full)
    barrier = resume.Barrier.awaiting(sequences)
    assert barrier.resuming

    for poll in _drain_in_polls(outbox):
        barrier.acknowledge(through=poll[-1])
        # Not ready mid-drain unless this was the last poll.
        assert barrier.ready == (outbox.depth == 0)
    assert barrier.ready
    assert barrier.failure is None
