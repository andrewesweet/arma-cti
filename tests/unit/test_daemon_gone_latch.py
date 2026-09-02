"""The pump's dead-daemon noise is latched, not hammered (#72).

A daemon that died mid-run used to earn an identical `CTI|daemon_unreachable`
line at every loop's poll cadence for the rest of a probe's window. `#72`'s
second half is the latch: after a bounded run of consecutive transport errors,
the per-call line goes quiet and the fact is said once — legible, not loud.

What can be asserted at this tier is the document: SQF has no mutation arm and
the latch's only in-world reader is the evidence a corpus run writes, which is
why the world-facing half of this change is owed the full corpus at landing and
why these assertions read the source rather than execute it. The in-world
behaviour the latch must not break — a restarted daemon still being noticed, a
recovery still being said — is pinned by `spike/probes/daemon-restart.sqf`,
which pings through the outage and expects the epoch change to freeze the world.
"""

from __future__ import annotations

from conftest import REPO

DAEMON_CALL = REPO / "addons" / "main" / "functions" / "fn_daemonCall.sqf"


def source() -> str:
    """Read the one file the latch lives in."""
    return DAEMON_CALL.read_text(encoding="utf-8")


def test_the_run_is_counted_in_the_one_place_every_failure_passes_through() -> None:
    body = source()
    # Counted on the tally the file already broadcasts, so a probe reading
    # `cti_daemonCall` sees the run the log is being quieted against.
    assert 'getOrDefault ["consecutive_unreachable", 0]' in body
    assert '_tally set ["consecutive_unreachable", _run]' in body


def test_the_per_call_line_goes_quiet_past_the_threshold() -> None:
    body = source()
    # The noisy line is emitted only inside the below-threshold guard.
    assert "if (_run < _latchAfter) then {" in body
    assert "CTI|daemon_unreachable verb=%1 detail=%2" in body


def test_the_latch_is_said_once_at_the_threshold() -> None:
    body = source()
    assert "if (_run isEqualTo _latchAfter) then {" in body
    assert "CTI|daemon_gone_latched consecutive=%1 detail=%2 " in body
    assert "— daemon_unreachable lines quiet until the daemon answers" in body


def test_the_threshold_is_five_consecutive_transport_errors() -> None:
    assert "private _latchAfter = 5;" in source()


def test_the_calls_never_stop_so_a_restarted_daemon_is_still_noticed() -> None:
    """A call-suppressing latch would deafen the world to the epoch change (#96)."""
    body = source()
    # The wire call still precedes the branch that counts the failure, and the
    # run resets on the first reply — any reply — so recovery is discoverable.
    call_at = body.index("_raw = (_extension callExtension")
    branch_at = body.index('if !("status" in _reply) exitWith {')
    assert call_at < branch_at
    assert '_tally set ["consecutive_unreachable", 0];' in body
    reset_at = body.index('_tally set ["consecutive_unreachable", 0];')
    branch_end = body.index('["unreachable", _reply, _raw] call _answer')
    assert reset_at > branch_end
