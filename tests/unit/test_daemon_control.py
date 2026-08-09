"""The daemon's save/load control lane: acks only, typed refusals, no head-of-line block (#291).

Save and load live behind their own dispatch (`CONTROL_HANDLERS`) rather than the
transport verb table (`HANDLERS`) — which is what keeps the snapshot off the wire
(#289's guard, `test_no_daemon_handler_exposes_the_snapshot`). What this pins is
the Phase-2 contract the handlers carry on top of the seam `test_store` holds:

- An ack carries operational facts alone — version, checksum, generation, a
  rollback warning, the loadouts a load dropped — never the snapshot document
  (#288's acknowledgement-only rule).
- A refused load leaves the live Campaign untouched and its three failure modes
  are typed apart (criterion 5).
- The slow durability work happens off the lock, so a save cannot head-of-line
  block a synchronous Command judgement (criterion 3), and a Command in flight
  alongside a save is still judged (criterion 8).
- A load mints a new epoch, so a world attached to this daemon cannot resume
  against the replaced state silently (criterion 6).
- Replay is idempotent, and a busy refusal is not remembered (criterion 7).
"""

from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING, Any

from conftest import rows

from cti_daemon import snapshot, transport
from cti_daemon.daemon import (
    CONTROL_HANDLERS,
    HANDLERS,
    LOCK_WAIT_SECONDS,
    Daemon,
)
from cti_daemon.store import FakeStore, Loaded, SaveOutcome, checksum

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

# The snapshot's content keys that must never reach an ack. `version` is shared
# with the document but is an operational fact (which schema was saved), not a
# leak, so it is excluded here.
SECRET_KEYS = frozenset({"clock", "owners", "hq", "funds", "squads", "loadouts"})


def _daemon(tmp_path: Path, store: FakeStore | None = None) -> Daemon:
    """Build a daemon on this checkout's authored map, wired with the given store."""
    return Daemon(
        wiring=transport.wire(telemetry_path=tmp_path / "telemetry.jsonl"),
        store=store,
    )


def _save(request_id: str) -> str:
    return json.dumps({"id": request_id, "verb": "save", "payload": {}})


def _load(request_id: str) -> str:
    return json.dumps({"id": request_id, "verb": "load", "payload": {}})


def _control(daemon: Daemon, line: str) -> dict[str, Any]:
    return json.loads(daemon.handle_control_line(line))


def _purchase(
    daemon: Daemon, request_id: str, side: str = "WEST", squad_type: str = "rifle"
) -> dict[str, Any]:
    """Issue a Purchase down the command lane, to play the Campaign under test."""
    return json.loads(
        daemon.handle_line(
            json.dumps(
                {
                    "id": request_id,
                    "verb": "command",
                    "payload": {
                        "command": "purchase",
                        "side": side,
                        "acting_side": side,
                        "args": {"squad_type": squad_type},
                    },
                }
            )
        )
    )


def _store_holding(document: Mapping[str, object], generation: int = 5) -> FakeStore:
    """Return a FakeStore pre-loaded with a document, as if a save had written it.

    How a test injects an unsupported or corrupt document: the durability layer
    has handed the bytes back, and what the handler does with them is what is
    under test, so the bad document is placed where a real store's read would
    leave it.
    """
    store = FakeStore()
    store._document = dict(document)  # noqa: SLF001 — test arrangement of a test double
    store._generation = generation  # noqa: SLF001 — ditto
    store._checksum = checksum(document)  # noqa: SLF001 — ditto
    return store


class _CountingStore(FakeStore):
    """A FakeStore that counts how many times each method actually ran."""

    def __init__(self) -> None:
        super().__init__()
        self.saves = 0
        self.loads = 0

    def save(self, document: Mapping[str, object]) -> SaveOutcome:
        self.saves += 1
        return super().save(document)

    def load(self) -> Loaded:
        self.loads += 1
        return super().load()


class _SlowStore(FakeStore):
    """A FakeStore whose save blocks until released, to hold the off-lock work."""

    def __init__(self) -> None:
        super().__init__()
        self.in_save = threading.Event()
        self.release = threading.Event()

    def save(self, document: Mapping[str, object]) -> SaveOutcome:
        # Reached only after the daemon has photographed the Campaign and released
        # the lock, so the caller that sets `in_save` knows the lock is free.
        self.in_save.set()
        self.release.wait(timeout=30)
        return super().save(document)


# --- the snapshot is reachable only through the control lane --------------


def test_save_and_load_live_on_their_own_table_not_the_transport_verbs() -> None:
    # #289's guard holds save and load out of `HANDLERS`; this pins that they are
    # nonetheless reachable, on a dispatch the transport verbs do not share
    # (criterion 2: no transport path retrieves the snapshot; criterion 3: the
    # slow work has a lane of its own).
    assert set(CONTROL_HANDLERS) == {"save", "load"}
    assert not (set(CONTROL_HANDLERS) & set(HANDLERS)), (
        "the control lane and the transport lane share a verb"
    )


# --- a daemon without a store refuses rather than guessing one ------------


def test_a_daemon_without_a_store_refuses_save_and_load_by_name(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    save = _control(daemon, _save("s-1"))
    load = _control(daemon, _load("l-1"))
    assert save["error"]["class"] == "no_store"
    assert load["error"]["class"] == "no_store"


# --- acknowledgement-only: operational facts, never the snapshot ----------


def test_a_save_ack_carries_only_operational_facts_not_the_snapshot(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path, FakeStore())
    # Play the Campaign so the snapshot is non-trivial — a Squad bought, Funds
    # spent — and the ack must still carry none of it.
    purchase = _purchase(daemon, "c-1")
    assert purchase["status"] == "ok"
    save = _control(daemon, _save("s-1"))

    assert save["status"] == "ok"
    assert set(save["result"]) == {"saved", "version", "checksum", "generation"}
    assert not (set(save["result"]) & SECRET_KEYS), "the save ack leaked a snapshot field"
    assert save["result"]["generation"] == 1
    assert save["result"]["version"] == snapshot.CURRENT_VERSION
    # The checksum is a hex digest, not the document it digests.
    assert len(save["result"]["checksum"]) == 64


def test_a_load_ack_carries_only_operational_facts_not_the_snapshot(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path, FakeStore())
    _control(daemon, _save("s-1"))  # prime the store
    load = _control(daemon, _load("l-1"))

    assert load["status"] == "ok"
    assert set(load["result"]) == {
        "loaded",
        "version",
        "checksum",
        "generation",
        "rollback_warning",
        "dropped_loadouts",
    }
    assert not (set(load["result"]) & SECRET_KEYS), "the load ack leaked a snapshot field"
    assert load["result"]["rollback_warning"] is False
    assert load["result"]["dropped_loadouts"] == []


def test_every_control_reply_carries_the_epoch(tmp_path: Path) -> None:
    # The epoch invariant the command lane carries (#96, ADR-0036) extends to the
    # control lane: a control reply says who answered it, whatever its status.
    daemon = _daemon(tmp_path, FakeStore())
    save = _control(daemon, _save("s-1"))
    refusal = _control(daemon, json.dumps({"id": "x-1", "verb": "snapshot", "payload": {}}))
    assert save["epoch"] == daemon.epoch
    assert refusal["epoch"] == daemon.epoch


# --- typed refusals: three failure modes, the live Campaign untouched ------


def test_a_load_off_an_empty_store_is_no_valid_generation_and_leaves_the_campaign(
    tmp_path: Path,
) -> None:
    daemon = _daemon(tmp_path, FakeStore())
    before = daemon.cycle.snapshot()
    refusal = _control(daemon, _load("l-1"))
    assert refusal["error"]["class"] == "no_valid_generation"
    assert daemon.cycle.snapshot() == before, "a refused load touched the live Campaign"


def test_a_load_of_an_unsupported_schema_is_typed_apart_and_leaves_the_campaign(
    tmp_path: Path,
) -> None:
    daemon = _daemon(tmp_path, _store_holding({"version": snapshot.CURRENT_VERSION + 1}))
    before = daemon.cycle.snapshot()
    refusal = _control(daemon, _load("l-1"))
    assert refusal["error"]["class"] == "unsupported_schema"
    assert daemon.cycle.snapshot() == before


def test_a_load_of_a_corrupt_document_is_typed_apart_and_leaves_the_campaign(
    tmp_path: Path,
) -> None:
    corrupt = {
        "version": snapshot.CURRENT_VERSION,
        "clock": 0.0,
        "owners": {},
        "hq": {},
        "funds": {"WEST": "not-a-number"},
        "squads": [],
        "loadouts": {},
    }
    daemon = _daemon(tmp_path, _store_holding(corrupt))
    before = daemon.cycle.snapshot()
    refusal = _control(daemon, _load("l-1"))
    assert refusal["error"]["class"] == "corrupt"
    assert daemon.cycle.snapshot() == before


def test_the_three_load_refusals_are_distinguishable_from_one_another(tmp_path: Path) -> None:
    # A refused save must be distinguishable from a lost one (#291): the three
    # load refusals carry three different classes, so a caller reads which
    # failure it got rather than re-parsing a message.
    classes = {
        _control(_daemon(tmp_path, FakeStore()), _load("l-1"))["error"]["class"],
        _control(
            _daemon(tmp_path, _store_holding({"version": snapshot.CURRENT_VERSION + 1})),
            _load("l-1"),
        )["error"]["class"],
        _control(
            _daemon(
                tmp_path,
                _store_holding(
                    {
                        "version": snapshot.CURRENT_VERSION,
                        "clock": 0.0,
                        "owners": {},
                        "hq": {},
                        "funds": {"WEST": "x"},
                        "squads": [],
                        "loadouts": {},
                    }
                ),
            ),
            _load("l-1"),
        )["error"]["class"],
    }
    assert classes == {"no_valid_generation", "unsupported_schema", "corrupt"}


def test_a_malformed_control_line_is_answered_not_dropped(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path, FakeStore())
    reply = json.loads(daemon.handle_control_line("{not json"))
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "malformed_request"


def test_an_unknown_control_verb_is_a_typed_refusal(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path, FakeStore())
    reply = _control(daemon, json.dumps({"id": "x-1", "verb": "snapshot", "payload": {}}))
    assert reply["error"]["class"] == "unknown_verb"


# --- a busy refusal is not remembered, so the resend is carried out -------


def test_a_busy_save_is_not_remembered_so_the_resend_is_actually_written(
    tmp_path: Path,
) -> None:
    store = _CountingStore()
    daemon = _daemon(tmp_path, store)
    line = _save("s-1")

    # Hold the command lock so the save's photograph is shed rather than parked.
    daemon._lock.acquire()  # noqa: SLF001 — the lock is the subject under arrangement
    busy = _control(daemon, line)
    daemon._lock.release()  # noqa: SLF001 — ditto

    assert busy["error"]["class"] == "busy"
    assert store.saves == 0, "a shed save wrote to the store"

    carried = _control(daemon, line)
    assert carried["status"] == "ok", "a shed save was not retried on the resend"
    assert carried["result"]["generation"] == 1
    assert store.saves == 1


def test_a_busy_load_is_not_remembered_so_the_resend_applies(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path, FakeStore())
    _control(daemon, _save("s-1"))  # prime
    line = _load("l-1")
    before = daemon.epoch

    daemon._lock.acquire()  # noqa: SLF001 — the lock is the subject under arrangement
    busy = _control(daemon, line)
    daemon._lock.release()  # noqa: SLF001 — ditto

    assert busy["error"]["class"] == "busy"
    assert daemon.epoch == before, "a shed load applied before it was refused"

    carried = _control(daemon, line)
    assert carried["status"] == "ok"
    assert daemon.epoch != before, "a shed load was not applied on the resend"


# --- replay is idempotent: a resend is answered, not repeated ------------


def test_a_resent_save_is_answered_from_the_record_not_written_again(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    store = _CountingStore()
    daemon = _daemon(tmp_path, store)
    line = _save("s-1")

    first = _control(daemon, line)
    again = _control(daemon, line)

    assert first["result"]["generation"] == 1
    assert again == first, "a resent save was not answered from the record"
    assert store.saves == 1, "a resent save wrote a second time"
    assert len(rows(log, "control_replayed")) == 1


def test_a_resent_load_is_answered_from_the_record_and_mints_no_second_epoch(
    tmp_path: Path,
) -> None:
    store = _CountingStore()
    daemon = _daemon(tmp_path, store)
    _control(daemon, _save("s-1"))  # prime
    line = _load("l-1")

    first = _control(daemon, line)
    again = _control(daemon, line)

    assert again == first, "a resent load was not answered from the record"
    assert store.loads == 1, "a resent load read the store a second time"
    assert daemon.epoch == first["epoch"], "a resent load minted a second epoch"


# --- a load mints a new epoch (criterion 6) -------------------------------


def test_a_load_mints_a_new_epoch_so_the_world_cannot_resume_silently(
    tmp_path: Path,
) -> None:
    daemon = _daemon(tmp_path, FakeStore())
    _control(daemon, _save("s-1"))
    before = daemon.epoch

    loaded = _control(daemon, _load("l-1"))

    assert loaded["status"] == "ok"
    assert daemon.epoch != before, "a load replaced the Campaign without changing identity"
    assert loaded["epoch"] == daemon.epoch, "the load's reply does not carry the new identity"


# --- the rollback warning fires only for an older generation -------------


def test_a_load_of_an_older_generation_warns_of_rollback(tmp_path: Path) -> None:
    store = FakeStore()
    daemon = _daemon(tmp_path, store)
    _control(daemon, _save("s-1"))  # generation 1
    _control(daemon, _save("s-2"))  # generation 2; _last_saved_generation == 2

    # The store now hands back the older generation, as a real last-known-good
    # might after the latest write was quarantined.
    store._generation = 1  # noqa: SLF001 — test arrangement of a test double
    rolled = _control(daemon, _load("l-1"))
    assert rolled["result"]["rollback_warning"] is True


def test_a_load_of_the_current_generation_does_not_warn_of_rollback(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path, FakeStore())
    _control(daemon, _save("s-1"))  # generation 1; _last_saved_generation == 1
    loaded = _control(daemon, _load("l-1"))
    assert loaded["result"]["rollback_warning"] is False


def test_a_load_when_nothing_was_ever_saved_does_not_warn_of_rollback(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)  # no daemon save yet; _last_saved_generation is None
    daemon.store = _store_holding(snapshot.serialise(daemon.cycle.snapshot()))
    loaded = _control(daemon, _load("l-1"))
    assert loaded["result"]["rollback_warning"] is False


# --- no head-of-line block: the slow save stays off the lock -------------


def test_a_slow_save_does_not_head_of_line_block_a_concurrent_command(
    tmp_path: Path,
) -> None:
    # Criterion 3 and 8 together: the save's durability write is off the lock,
    # so while it is wedged a synchronous Command Judgement goes through — judged
    # and spent, not parked behind the save — well inside the lock bound.
    store = _SlowStore()
    daemon = _daemon(tmp_path, store)

    def _save_in_background() -> None:
        daemon.handle_control_line(_save("s-1"))

    thread = threading.Thread(target=_save_in_background, daemon=True)
    thread.start()
    assert store.in_save.wait(timeout=5), "the save never reached the slow store"

    started = time.perf_counter()
    purchase = _purchase(daemon, "c-1")
    elapsed = time.perf_counter() - started

    assert purchase["status"] == "ok", "a save wedged off the lock still blocked a Command"
    assert elapsed < LOCK_WAIT_SECONDS, (
        f"a Command waited {elapsed:.3f}s behind a save that holds no lock"
    )

    store.release.set()
    thread.join(timeout=30)
    assert not thread.is_alive(), "the save never completed once released"
