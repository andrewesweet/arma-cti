"""The lane breaker: its two trip families, its feeds, and its refusal (#226, ADR-0061).

The claims worth making here are mostly *negative*, and they are the ones the sweep's
rejection of LiteLLM turns on. It is easy to write a breaker that opens; the questions
are whether it ever invents a cooldown, whether a quality trip can heal itself, whether
an estimate we know to be in the wrong unit can refuse real work, and whether a
transition that nobody could export is lost. Each has a test that would go red if the
answer changed.

Nothing here touches a provider. Every feed is a staged document — a status-line payload,
an `account/rateLimits/read` result, a ledger of dispatch records — because no credential
exists yet and a test that needed one would be a test that never runs. The OTel half is
pointed at an endpoint that refuses, on purpose: the assertion is that the journal is
complete whether or not the collector took the record.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

breaker: ModuleType = load_tool("breaker")
otel_event: ModuleType = load_tool("otel_event")

# A port nothing listens on, so `post` fails the way a stopped collector fails. Inside
# the tier's own allocation [2400, 3000) and away from the slot stride, so a test can
# never collide with a running world.
DEAD_ENDPOINT = "http://127.0.0.1:2999/v1/logs"

NOW = 1_785_000_000.0
HOUR = 3600.0


def store(tmp_path: Path) -> Any:  # noqa: ANN401 — a tools/ module loads dynamically, so its types are Unknown here
    """Build a breaker store whose collector is deliberately not there."""
    return breaker.Store(directory=tmp_path / "breaker", endpoint=DEAD_ENDPOINT)


def feed(state: Any, lane: str, outcomes: list[str], now: float = NOW) -> Any:  # noqa: ANN401 — same
    """Push a run of outcomes at one lane, one second apart."""
    circuit = None
    for step, name in enumerate(outcomes):
        circuit, _ = breaker.record_outcome(state, lane, breaker.Outcome(name), now + step)
    return circuit


# ------------------------------------------------------------------ the pure core (#72)


def test_an_ordinary_outcome_moves_nothing_and_a_closed_lane_conducts() -> None:
    circuit, transition = breaker.advance(
        breaker.Circuit(), breaker.LANE_RULES, breaker.Outcome(breaker.OK), NOW
    )
    assert circuit.state == breaker.CLOSED
    assert transition is None
    assert breaker.verdict("zai", circuit, breaker.LANE_RULES).conducting is True


def test_the_quality_trip_needs_three_consecutive_and_one_good_run_resets_the_count() -> None:
    circuit = breaker.Circuit()
    for _ in range(2):
        circuit, _ = breaker.advance(
            circuit, breaker.LANE_RULES, breaker.Outcome(breaker.GATE_FAILED), NOW
        )
    assert circuit.state == breaker.CLOSED
    assert circuit.streak("quality") == 2

    circuit, _ = breaker.advance(circuit, breaker.LANE_RULES, breaker.Outcome(breaker.OK), NOW)
    assert circuit.streak("quality") == 0

    for _ in range(2):
        circuit, _ = breaker.advance(
            circuit, breaker.LANE_RULES, breaker.Outcome(breaker.GATE_FAILED), NOW
        )
    assert circuit.state == breaker.CLOSED, "two after a reset is two, not four"


def test_a_gate_failure_and_a_refusal_are_the_same_streak() -> None:
    """One rule counts both: a lane refusing and a lane failing gates are both it, wrong."""
    circuit = breaker.Circuit()
    for name in (breaker.GATE_FAILED, breaker.PROVIDER_REFUSED, breaker.GATE_FAILED):
        circuit, transition = breaker.advance(
            circuit, breaker.LANE_RULES, breaker.Outcome(name), NOW
        )
    assert circuit.state == breaker.OPEN
    assert transition is not None
    assert transition.rule == "quality"


def test_the_quality_trip_escalates_and_carries_no_reset_time_at_all() -> None:
    """The load-bearing negative: a quality trip must never acquire a timer."""
    circuit = breaker.Circuit()
    for _ in range(3):
        circuit, _ = breaker.advance(
            circuit,
            breaker.LANE_RULES,
            # A reset time offered *with* the outcome, which a lesser breaker would keep.
            breaker.Outcome(breaker.GATE_FAILED, reset_at=NOW + HOUR),
            NOW,
        )
    assert circuit.state == breaker.OPEN
    assert circuit.escalated is True
    assert circuit.reset_at is None

    settled, transition = breaker.settle(circuit, breaker.LANE_RULES, NOW + 10 * HOUR)
    assert settled == circuit, "ten hours later it is still open"
    assert transition is None
    assert breaker.verdict("zai", settled, breaker.LANE_RULES).conducting is False


def test_a_quota_trip_opens_to_the_published_reset_and_half_opens_when_it_arrives() -> None:
    reset = NOW + HOUR
    circuit, transition = breaker.advance(
        breaker.Circuit(),
        breaker.LANE_RULES,
        breaker.Outcome(breaker.QUOTA_EXHAUSTED, reset_at=reset),
        NOW,
    )
    assert circuit.state == breaker.OPEN
    assert circuit.reset_at == reset
    assert transition is not None
    assert transition.escalates is False, "quota is expected output, not an incident"

    early, none_yet = breaker.settle(circuit, breaker.LANE_RULES, reset - 1)
    assert early.state == breaker.OPEN
    assert none_yet is None

    half, arrived = breaker.settle(circuit, breaker.LANE_RULES, reset)
    assert half.state == breaker.HALF_OPEN
    assert arrived is not None
    assert breaker.verdict("zai", half, breaker.LANE_RULES).conducting is True, (
        "half-open conducts: that one dispatch is the probe"
    )


def test_the_probe_closes_the_circuit_and_a_second_exhaustion_reopens_it() -> None:
    reset = NOW + HOUR
    circuit, _ = breaker.advance(
        breaker.Circuit(),
        breaker.LANE_RULES,
        breaker.Outcome(breaker.QUOTA_EXHAUSTED, reset_at=reset),
        NOW,
    )
    half, _ = breaker.settle(circuit, breaker.LANE_RULES, reset)
    closed, transition = breaker.advance(
        half, breaker.LANE_RULES, breaker.Outcome(breaker.OK), reset + 1
    )
    assert closed == breaker.Circuit()
    assert transition is not None
    assert (transition.from_state, transition.to_state) == (breaker.HALF_OPEN, breaker.CLOSED)

    again, reopened = breaker.advance(
        half,
        breaker.LANE_RULES,
        breaker.Outcome(breaker.QUOTA_EXHAUSTED, reset_at=reset + HOUR),
        reset + 1,
    )
    assert again.state == breaker.OPEN
    assert again.reset_at == reset + HOUR
    assert reopened is not None


def test_three_provider_errors_hold_the_lane_and_no_amount_of_time_reopens_it() -> None:
    """LiteLLM's defect, asserted against: no published reset means no cooldown at all."""
    circuit = breaker.Circuit()
    for _ in range(3):
        circuit, transition = breaker.advance(
            circuit, breaker.LANE_RULES, breaker.Outcome(breaker.PROVIDER_ERROR), NOW
        )
    assert circuit.state == breaker.OPEN
    assert circuit.rule == "provider_errors"
    assert circuit.reset_at is None
    assert transition is not None
    assert transition.escalates is True

    for later in (NOW + 5, NOW + 300, NOW + 100 * HOUR):
        settled, moved = breaker.settle(circuit, breaker.LANE_RULES, later)
        assert settled.state == breaker.OPEN
        assert moved is None

    assert (
        breaker.verdict("zai", circuit, breaker.LANE_RULES).failure_class == "infra_unavailable"
    ), "a lane that cannot be reached is the infra row, not the quota one"


def test_an_unclassified_outcome_moves_no_streak_in_either_direction() -> None:
    """A class we could not read is not evidence — the #41 shape, refused here."""
    circuit = breaker.Circuit()
    for _ in range(2):
        circuit, _ = breaker.advance(
            circuit, breaker.LANE_RULES, breaker.Outcome(breaker.GATE_FAILED), NOW
        )
    before = circuit
    after, transition = breaker.advance(
        circuit, breaker.LANE_RULES, breaker.Outcome(breaker.UNCLASSIFIED), NOW
    )
    assert after == before
    assert transition is None
    assert after.streak("quality") == 2, "it neither advanced the streak nor cleared it"


def test_a_quota_trip_cannot_overwrite_an_escalated_lane_into_a_timed_wait() -> None:
    circuit = breaker.Circuit()
    for _ in range(3):
        circuit, _ = breaker.advance(
            circuit, breaker.LANE_RULES, breaker.Outcome(breaker.GATE_FAILED), NOW
        )
    assert circuit.escalated is True

    after, transition = breaker.advance(
        circuit,
        breaker.LANE_RULES,
        breaker.Outcome(breaker.QUOTA_EXHAUSTED, reset_at=NOW + HOUR),
        NOW,
    )
    assert after.rule == "quality"
    assert after.reset_at is None
    assert after.escalated is True
    assert transition is None
    assert after.streak("quota") == 1, "the quota streak still counts; it just cannot take over"


def test_the_rules_a_consumer_would_write_for_issue_72_work_unchanged() -> None:
    """#72's corpus loop: two consecutive `node_crashed` abandon the rest of the corpus.

    Written here as that consumer would write it — its own rule, its own N, its own
    outcome name, and nothing from the lane vocabulary — because the claim the issue
    asks for is that the abstraction is usable by it, not that it resembles it.
    """
    systemic = breaker.TripRule(
        name="systemic_crash",
        on=frozenset({"node_crashed"}),
        consecutive=2,
        family=breaker.AVAILABILITY,
        auto_reset=False,
        escalates=True,
        failure_class="node_crashed",
    )
    rules = (systemic,)
    circuit = breaker.Circuit()
    verdicts = ["assertion_failed", "node_crashed", "node_crashed", "ok", "ok"]
    abandoned_after = None
    for index, seen in enumerate(verdicts):
        outcome = "node_crashed" if seen == "node_crashed" else breaker.OK
        circuit, transition = breaker.advance(circuit, rules, breaker.Outcome(outcome), NOW)
        if transition is not None and transition.to_state == breaker.OPEN:
            abandoned_after = index
            break
    assert abandoned_after == 2, "the second crash is what abandons, not the third"
    assert breaker.verdict("corpus", circuit, rules).failure_class == "node_crashed"
    assert len(verdicts) - abandoned_after - 1 == 2, "two probes not run, which the summary says"


# ------------------------------------------------------------------------------ feeds


def test_the_status_line_feed_reads_both_windows_and_their_reset_times() -> None:
    payload = {
        "rate_limits": {
            "five_hour": {"used_percentage": 62, "resets_at": NOW + HOUR},
            "seven_day": {"used_percentage": 12.5, "resets_at": NOW + 100 * HOUR},
        }
    }
    reading = breaker.reading_from_status_line(payload, "claude-native", NOW)
    assert reading.available is True
    assert reading.estimated is False
    assert [window.name for window in reading.windows] == ["five_hour", "seven_day"]
    assert reading.windows[0].used_fraction == pytest.approx(0.62)
    assert reading.windows[0].resets_at == NOW + HOUR
    assert reading.exhausted_window() is None


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({}, "rate_limits_absent"),
        ({"rate_limits": None}, "rate_limits_absent"),
        ({"rate_limits": {}}, "rate_limits_empty"),
        ({"rate_limits": {"five_hour": {}}}, "rate_limits_empty"),
    ],
)
def test_a_status_line_with_no_quota_says_so_rather_than_reading_as_zero(
    payload: dict[str, object], expected: str
) -> None:
    """Pro/Max only, and only after the first API response — every absence is typed."""
    reading = breaker.reading_from_status_line(payload, "claude-native", NOW)
    assert reading.available is False
    assert reading.unavailable == expected
    assert reading.windows == ()


def test_one_window_present_and_one_absent_is_read_as_the_one_that_is_there() -> None:
    payload = {"rate_limits": {"seven_day": {"used_percentage": 90, "resets_at": NOW + HOUR}}}
    reading = breaker.reading_from_status_line(payload, "claude-native", NOW)
    assert [window.name for window in reading.windows] == ["seven_day"]


def test_the_codex_feed_reads_the_documented_shape_and_its_reached_type_outranks_the_percent() -> (
    None
):
    """The documented example from `codex-rs/app-server/README.md` section 7, verbatim."""
    payload = {
        "rateLimits": {
            "primary": {"usedPercent": 25, "windowDurationMins": 15, "resetsAt": 1730947200},
            "secondary": None,
            "rateLimitReachedType": None,
        }
    }
    reading = breaker.reading_from_codex_rate_limits(payload, "codex", NOW)
    assert reading.available is True
    assert reading.windows[0].used_fraction == pytest.approx(0.25)
    assert reading.windows[0].resets_at == 1730947200
    assert reading.exhausted_window() is None

    reached = json.loads(json.dumps(payload))
    reached["rateLimits"]["rateLimitReachedType"] = "primary"
    hit = breaker.reading_from_codex_rate_limits(reached, "codex", NOW)
    assert hit.exhausted_window() is not None, "the backend's own word outranks 25%"
    assert hit.exhausted_window().resets_at == 1730947200


def test_the_codex_feed_accepts_the_json_rpc_envelope_as_well_as_the_bare_result() -> None:
    inner = {"rateLimits": {"primary": {"usedPercent": 10, "resetsAt": NOW}}}
    assert breaker.reading_from_codex_rate_limits(
        {"result": inner}, "codex", NOW
    ) == breaker.reading_from_codex_rate_limits(inner, "codex", NOW)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1730947200, 1730947200.0),
        ("1730947200", 1730947200.0),
        ("2026-08-05T18:13:20+00:00", 1785953600.0),
        ("2026-08-05T18:13:20Z", 1785953600.0),
        (None, None),
        ("", None),
        ("soon", None),
        (True, None),
    ],
)
def test_a_reset_time_is_read_from_either_spelling_and_never_invented(
    value: object, expected: float | None
) -> None:
    """An unreadable timestamp becomes no reset time, which the refusal then says aloud."""
    assert breaker.as_epoch(value) == expected


def test_an_exhausted_first_party_window_trips_the_lane_to_its_published_reset() -> None:
    reset = NOW + 2 * HOUR
    reading = breaker.reading_from_status_line(
        {"rate_limits": {"five_hour": {"used_percentage": 100, "resets_at": reset}}},
        "claude-native",
        NOW,
    )
    circuit, transition = breaker.apply_reading(breaker.Circuit(), breaker.LANE_RULES, reading, NOW)
    assert circuit.state == breaker.OPEN
    assert circuit.reset_at == reset
    assert transition is not None


def test_two_exhausted_windows_trip_to_whichever_comes_back_first() -> None:
    reading = breaker.reading_from_status_line(
        {
            "rate_limits": {
                "five_hour": {"used_percentage": 100, "resets_at": NOW + HOUR},
                "seven_day": {"used_percentage": 100, "resets_at": NOW + 100 * HOUR},
            }
        },
        "claude-native",
        NOW,
    )
    circuit, _ = breaker.apply_reading(breaker.Circuit(), breaker.LANE_RULES, reading, NOW)
    assert circuit.reset_at == NOW + HOUR


def test_a_healthy_first_party_reading_releases_a_held_lane_but_never_a_quality_trip() -> None:
    healthy = breaker.reading_from_status_line(
        {"rate_limits": {"five_hour": {"used_percentage": 3, "resets_at": NOW + HOUR}}},
        "claude-native",
        NOW,
    )

    held = breaker.Circuit()
    for _ in range(3):
        held, _ = breaker.advance(
            held, breaker.LANE_RULES, breaker.Outcome(breaker.PROVIDER_ERROR), NOW
        )
    released, transition = breaker.apply_reading(held, breaker.LANE_RULES, healthy, NOW)
    assert released.state == breaker.CLOSED
    assert transition is not None

    quality = breaker.Circuit()
    for _ in range(3):
        quality, _ = breaker.advance(
            quality, breaker.LANE_RULES, breaker.Outcome(breaker.GATE_FAILED), NOW
        )
    unmoved, none_taken = breaker.apply_reading(quality, breaker.LANE_RULES, healthy, NOW)
    assert unmoved == quality, "having quota says nothing about serving the right thing"
    assert none_taken is None


# --------------------------------------------------------------------- the z.ai estimate


def test_an_unknown_plan_tier_is_a_typed_state_and_not_a_guessed_cap() -> None:
    reading = breaker.estimate_zai((NOW - 60,), "", NOW)
    assert reading.available is False
    assert reading.unavailable == "plan_tier_unknown"
    assert reading.windows == ()
    assert reading.estimated is True


def test_the_estimate_charges_peak_at_full_and_off_peak_at_half() -> None:
    """z.ai's published multiplier: peak is Mon-Fri 14:00-18:00 SGT, off-peak is half."""
    # 2026-08-05 is a Wednesday. 15:00 SGT is 07:00 UTC; 03:00 SGT is 19:00 UTC the day before.
    peak = 1785913200.0
    off_peak = peak - 12 * HOUR
    assert breaker.zai_is_peak(peak) is True
    assert breaker.zai_is_peak(off_peak) is False

    at_peak = breaker.estimate_zai((peak,), "lite", peak + 60)
    at_off = breaker.estimate_zai((off_peak,), "lite", off_peak + 60)
    five_hour_cap = breaker.ZAI_TIERS["lite"][0]
    assert at_peak.windows[0].used_fraction == pytest.approx(1 / five_hour_cap)
    assert at_off.windows[0].used_fraction == pytest.approx(0.5 / five_hour_cap)


def test_the_band_lifts_at_its_own_upper_boundary_and_not_a_minute_later() -> None:
    """What #238's refusal hands a dispatcher back: the published boundary, computed."""
    # 2026-08-05 is a Wednesday; 15:00 SGT is 07:00 UTC and 18:00 SGT is 10:00 UTC.
    at_15 = 1785913200.0
    opens = breaker.zai_off_peak_opens_at(at_15)
    assert opens == at_15 + 3 * HOUR
    assert breaker.zai_is_peak(opens - 1) is True
    assert breaker.zai_is_peak(opens) is False, "half-open: 18:00:00 exactly is off-peak"


def test_a_moment_already_off_peak_answers_itself_rather_than_naming_a_wait() -> None:
    off_peak = 1785913200.0 - 12 * HOUR
    assert breaker.zai_off_peak_opens_at(off_peak) == off_peak


def test_a_weekend_is_never_peak_however_it_falls_in_the_band() -> None:
    saturday_3pm_sgt = 1786172400.0
    assert breaker.zai_is_peak(saturday_3pm_sgt) is False


def test_the_estimate_computes_its_window_reset_from_our_own_records() -> None:
    first = NOW - 2 * HOUR
    reading = breaker.estimate_zai((first, NOW - HOUR), "pro", NOW)
    five_hour = reading.windows[0]
    assert five_hour.resets_at == first + breaker.FIVE_HOURS_SECS, (
        "five hours after the first consumption in the window, which our ledger knows"
    )


def test_an_estimate_cannot_trip_a_lane_however_far_over_the_cap_it_reads() -> None:
    """The unit is wrong and we know it, so this number never refuses real work."""
    flooded = tuple(NOW - index for index in range(9000))
    reading = breaker.estimate_zai(flooded, "lite", NOW)
    assert reading.windows[0].used_fraction > 1.0
    assert reading.exhausted_window() is not None, "the reading itself says it is over"

    circuit, transition = breaker.apply_reading(breaker.Circuit(), breaker.LANE_RULES, reading, NOW)
    assert circuit.state == breaker.CLOSED, "and the breaker still lets the lane serve"
    assert transition is None
    assert reading.unit == "dispatches"


def test_the_ledger_reads_only_this_lanes_dispatches(tmp_path: Path) -> None:
    root = tmp_path / "dispatches"
    for name, lane, when in (
        ("a", "zai", "2026-08-05T10:00:00+00:00"),
        ("b", "claude-native", "2026-08-05T11:00:00+00:00"),
        ("c", "zai", "2026-08-05T09:00:00+00:00"),
    ):
        record = root / name
        record.mkdir(parents=True)
        (record / "dispatch.json").write_text(
            json.dumps({"lane": lane, "planned_at": when}), encoding="utf-8"
        )
    (root / "d").mkdir()
    (root / "d" / "dispatch.json").write_text("{ not json", encoding="utf-8")

    events = breaker.zai_dispatch_events(root)
    assert len(events) == 2, "the other lane's dispatch and the unreadable record are skipped"
    assert events == tuple(sorted(events)), "oldest first, which the window arithmetic needs"


# --------------------------------------------------------- classifying a finished run


@pytest.mark.parametrize(
    ("returncode", "output", "expected"),
    [
        (0, "", breaker.OK),
        (0, "Claude AI usage limit reached", breaker.OK),
        (1, "API Error: 429 rate limit exceeded", breaker.QUOTA_EXHAUSTED),
        (1, "Claude AI usage limit reached|1785953600", breaker.QUOTA_EXHAUSTED),
        (1, "Error: insufficient quota for this key", breaker.QUOTA_EXHAUSTED),
        (1, "connection refused", breaker.PROVIDER_ERROR),
        (1, "API Error: 503 Service Unavailable", breaker.PROVIDER_ERROR),
        (1, "the agent decided the issue was already done", breaker.UNCLASSIFIED),
        (2, "", breaker.UNCLASSIFIED),
    ],
)
def test_a_finished_runs_own_output_is_classified_narrowly(
    returncode: int, output: str, expected: str
) -> None:
    """Narrow on purpose: an output nobody can place moves no streak."""
    assert breaker.classify_run(returncode, output)[0] == expected


def test_the_limit_line_hands_over_its_own_reset_epoch() -> None:
    outcome, reset_at = breaker.classify_run(1, "Claude AI usage limit reached|1785953600")
    assert outcome == breaker.QUOTA_EXHAUSTED
    assert reset_at == 1785953600.0


def test_a_limit_with_no_epoch_yields_no_reset_rather_than_a_computed_one() -> None:
    outcome, reset_at = breaker.classify_run(1, "429 rate limit exceeded, try later")
    assert outcome == breaker.QUOTA_EXHAUSTED
    assert reset_at is None


# ------------------------------------------------------------------ store and telemetry


def test_the_state_survives_the_process_that_wrote_it(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "zai", [breaker.GATE_FAILED] * 3)
    assert breaker.lane_verdict(state, "zai", NOW + 10).conducting is False

    fresh = breaker.Store(directory=tmp_path / "breaker", endpoint=DEAD_ENDPOINT)
    again = breaker.lane_verdict(fresh, "zai", NOW + 10)
    assert again.conducting is False
    assert again.failure_class == "provider_refused"
    assert again.escalates is True


def test_an_unreadable_state_file_reads_as_a_fresh_lane_rather_than_a_refusal(
    tmp_path: Path,
) -> None:
    state = store(tmp_path)
    (tmp_path / "breaker").mkdir(parents=True)
    breaker.state_path(tmp_path / "breaker", "zai").write_text("{ broken", encoding="utf-8")
    assert breaker.lane_verdict(state, "zai", NOW).conducting is True


def test_every_transition_reaches_the_journal_even_when_the_collector_refuses(
    tmp_path: Path,
) -> None:
    """The claim ADR-0061 makes against LiteLLM: transitions are observable, always."""
    state = store(tmp_path)
    feed(state, "zai", [breaker.GATE_FAILED] * 3)
    lines = [
        json.loads(line)
        for line in state.journal.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 1, "one trip, one transition"
    record = lines[0]
    assert record["event"] == "cti.breaker.transition"
    assert record["exported"] is False, "the endpoint under test is deliberately dead"
    assert record["attributes"]["cti.breaker.to"] == breaker.OPEN
    assert record["attributes"]["cti.breaker.rule"] == "quality"
    assert record["attributes"]["cti.breaker.escalates"] is True
    assert record["resource"]["cti.lane"] == "zai"


def test_the_otel_document_is_a_valid_export_request_carrying_the_lanes_attributes() -> None:
    event = otel_event.Event(
        name="cti.breaker.transition",
        at=NOW,
        attributes={
            "cti.breaker.to": "open",
            "cti.breaker.streak": 3,
            "cti.breaker.escalates": True,
        },
        resource={"service.name": "arma-cti-breaker", "cti.lane": "zai"},
    )
    document = otel_event.log_record(event)
    resource_logs = document["resourceLogs"][0]
    record = resource_logs["scopeLogs"][0]["logRecords"][0]
    assert record["body"]["stringValue"] == "cti.breaker.transition"
    assert record["timeUnixNano"] == str(int(NOW * otel_event.NANOS_PER_SEC))
    keyed = {entry["key"]: entry["value"] for entry in record["attributes"]}
    assert keyed["event.name"] == {"stringValue": "cti.breaker.transition"}
    assert keyed["cti.breaker.streak"] == {"intValue": "3"}, "an int stays an int for the query"
    assert keyed["cti.breaker.escalates"] == {"boolValue": True}
    resource = {entry["key"]: entry["value"] for entry in resource_logs["resource"]["attributes"]}
    assert resource["cti.lane"] == {"stringValue": "zai"}


def test_the_exporter_never_raises_at_a_caller_whatever_the_endpoint_does() -> None:
    document = otel_event.log_record(otel_event.Event("e", NOW, {}, {}))
    assert otel_event.post(document, DEAD_ENDPOINT, timeout=1.0)[0] is False
    assert otel_event.post(document, "file:///etc/passwd")[0] is False
    assert otel_event.post(document, "not a url at all")[0] is False


def test_the_endpoint_comes_from_the_standard_variables_before_loopback() -> None:
    assert otel_event.endpoint_from_environment({}) == otel_event.DEFAULT_ENDPOINT
    assert (
        otel_event.endpoint_from_environment({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://host:4318/"})
        == "http://host:4318/v1/logs"
    )
    assert (
        otel_event.endpoint_from_environment(
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://base:4318",
                "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://exact/v1/logs",
            }
        )
        == "http://exact/v1/logs"
    )


def test_a_window_reset_that_elapsed_while_nothing_was_running_is_noticed_by_the_reader(
    tmp_path: Path,
) -> None:
    """Settling in the reader is what makes "state read before dispatch" sufficient."""
    state = store(tmp_path)
    reset = NOW + HOUR
    breaker.record_outcome(
        state, "zai", breaker.Outcome(breaker.QUOTA_EXHAUSTED, reset_at=reset), NOW
    )
    assert breaker.lane_verdict(state, "zai", NOW).conducting is False
    assert breaker.lane_verdict(state, "zai", reset + 1).conducting is True
    assert breaker.read_state(tmp_path / "breaker", "zai").circuit.state == breaker.HALF_OPEN


def test_clearing_a_lane_by_hand_closes_it_and_says_what_it_cleared(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "zai", [breaker.GATE_FAILED] * 3)
    transition = breaker.clear_lane(state, "zai", NOW + 100)
    assert transition is not None
    assert (transition.from_state, transition.to_state) == (breaker.OPEN, breaker.CLOSED)
    assert transition.rule == "quality"
    assert breaker.lane_verdict(state, "zai", NOW + 101).conducting is True
    assert breaker.clear_lane(state, "zai", NOW + 102) is None, "clearing a closed lane is a no-op"


# ----------------------------------------------------------------------- the report


def test_the_report_is_silent_about_every_lane_that_is_fine(tmp_path: Path) -> None:
    assert breaker.report_lines(store(tmp_path), NOW) == ()


def test_the_report_prints_one_verdict_line_per_lane_that_needs_one(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "zai", [breaker.GATE_FAILED] * 3)
    breaker.record_outcome(
        state,
        "claude-native",
        breaker.Outcome(breaker.QUOTA_EXHAUSTED, reset_at=NOW + 2 * HOUR),
        NOW,
    )
    lines = breaker.report_lines(state, NOW + 10)
    assert len(lines) == 2
    by_lane = {line.split()[0]: line for line in lines}
    assert "dispatch=refused" in by_lane["lane=claude-native"]
    assert "class=quota_exhausted" in by_lane["lane=claude-native"]
    assert "in=1h 59m" in by_lane["lane=claude-native"]
    assert "class=provider_refused" in by_lane["lane=zai"]
    assert "escalate=true" in by_lane["lane=zai"]


def test_a_verdict_line_never_says_open_or_closed_at_a_reader(tmp_path: Path) -> None:
    """Those two words mean opposite things to an electrician and to a shopkeeper."""
    state = store(tmp_path)
    feed(state, "zai", [breaker.GATE_FAILED] * 3)
    line = breaker.report_lines(state, NOW + 10)[0]
    words = line.replace("=", " ").split()
    assert "open" not in words
    assert "closed" not in words
    assert "dispatch=refused" in line


def test_a_quota_trip_with_no_published_reset_states_the_degradation_in_its_own_line(
    tmp_path: Path,
) -> None:
    state = store(tmp_path)
    breaker.record_outcome(state, "zai", breaker.Outcome(breaker.QUOTA_EXHAUSTED), NOW)
    line = breaker.report_lines(state, NOW + 10)[0]
    assert "until=unknown" in line
    assert "degraded=reacting-to-429s" in line
    assert "just prereqs statusline" in line


def test_an_estimate_appears_in_the_report_only_once_it_is_worth_knowing(tmp_path: Path) -> None:
    state = store(tmp_path)
    cap = breaker.ZAI_TIERS["lite"][0]
    quiet = breaker.estimate_zai(tuple(NOW - index for index in range(10)), "lite", NOW)
    breaker.record_reading(state, "zai", quiet, NOW)
    assert breaker.report_lines(state, NOW) == (), (
        "a lane well under its cap is a lane that is fine"
    )

    loud = breaker.estimate_zai(tuple(NOW - index for index in range(2 * cap)), "lite", NOW)
    breaker.record_reading(state, "zai", loud, NOW)
    line = breaker.report_lines(state, NOW)[0]
    assert "quota=estimated" in line
    assert "dispatch=allowed" in line, "an advisory is not a refusal"
    assert "unit=dispatches" in line


def test_the_state_view_names_a_lane_whose_feed_has_never_said_anything(tmp_path: Path) -> None:
    lines = breaker.state_lines(store(tmp_path), NOW)
    assert len(lines) == len(breaker.KNOWN_LANES)
    for line in lines:
        assert "feed=absent" in line
        assert "degraded=reacting-to-429s" in line
        assert "streak.quality=0/3" in line


def test_the_state_view_shows_a_ruled_lanes_window_so_a_refused_dispatcher_sees_why(
    tmp_path: Path,
) -> None:
    """#238: the breaker is the wrong home for the rule, and the right place to read it.

    A dispatcher refused by the off-peak rung reads this print next, so the window it was
    refused against is stated here. Only lanes with a published schedule carry it.
    """
    # 2026-08-05 is a Wednesday; 15:00 SGT is 07:00 UTC and inside z.ai's peak band.
    peak = 1785913200.0
    lines = {line.split(" ", 1)[0]: line for line in breaker.state_lines(store(tmp_path), peak)}
    zai = lines["lane=zai"]
    assert f"window={breaker.ZAI_PEAK_WINDOW}" in zai
    assert "band=peak" in zai
    assert f"opens={breaker.iso(breaker.zai_off_peak_opens_at(peak))}" in zai
    assert "window=" not in lines["lane=claude-native"], "a lane with no schedule states none"

    off_peak = peak - 12 * HOUR
    at_off = next(
        line for line in breaker.state_lines(store(tmp_path), off_peak) if "lane=zai" in line
    )
    assert "band=off-peak" in at_off
    assert "opens=" not in at_off, "nothing to wait for, so nothing to say about waiting"


def test_the_state_view_names_the_recipe_that_fixes_an_unknown_plan_tier(tmp_path: Path) -> None:
    state = store(tmp_path)
    breaker.record_reading(state, "zai", breaker.estimate_zai((), "", NOW), NOW)
    line = next(line for line in breaker.state_lines(state, NOW) if line.startswith("lane=zai "))
    assert "feed=ledger_estimate:plan_tier_unknown" in line
    assert "just prereqs plan-tier" in line


# ---------------------------------------------------------------------------- the CLI


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the tool as the recipe runs it, which is the surface a caller actually has."""
    # S603: fixed interpreter plus literals and paths this test built.
    return subprocess.run(  # noqa: S603
        [sys.executable, str(REPO / "tools" / "breaker.py"), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO / "tools")},
    )


def test_check_exits_zero_on_a_lane_that_conducts_and_one_on_a_lane_that_does_not(
    tmp_path: Path,
) -> None:
    args = ("--breaker-dir", str(tmp_path / "breaker"), "--otlp-endpoint", DEAD_ENDPOINT)
    allowed = run_cli(*args, "check", "--lane", "zai")
    assert allowed.returncode == 0
    assert "dispatch=allowed" in allowed.stdout

    for _ in range(3):
        run_cli(*args, "record", "--lane", "zai", "--outcome", "gate_failed")
    refused = run_cli(*args, "check", "--lane", "zai")
    assert refused.returncode == 1
    assert "class=provider_refused" in refused.stderr


def test_the_status_line_tap_passes_the_chained_line_through_byte_for_byte(
    tmp_path: Path,
) -> None:
    """The human's status line is theirs; this sits in front of it and changes nothing."""
    payload = json.dumps(
        {"rate_limits": {"five_hour": {"used_percentage": 44, "resets_at": NOW + HOUR}}}
    )
    done = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(REPO / "tools" / "breaker.py"),
            "--breaker-dir",
            str(tmp_path / "breaker"),
            "--otlp-endpoint",
            DEAD_ENDPOINT,
            "--now",
            str(NOW),
            "tap",
            "--lane",
            "claude-native",
            "--chain",
            "cat",
        ],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO / "tools")},
    )
    assert done.returncode == 0
    assert done.stdout == payload, "the chained status line's output survives verbatim"

    reading = breaker.read_state(tmp_path / "breaker", "claude-native").reading
    assert reading is not None
    assert reading.source == "status_line"
    assert reading.windows[0].used_fraction == pytest.approx(0.44)


def test_the_tap_passes_a_status_line_through_even_when_the_payload_is_not_json(
    tmp_path: Path,
) -> None:
    """A tap that broke on a surprise would break the human's status line on every render."""
    done = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(REPO / "tools" / "breaker.py"),
            "--breaker-dir",
            str(tmp_path / "breaker"),
            "tap",
            "--chain",
            "cat",
        ],
        input="not json at all",
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO / "tools")},
    )
    assert done.returncode == 0
    assert done.stdout == "not json at all"


def test_the_estimate_verb_refuses_without_a_plan_tier_and_names_the_recipe(
    tmp_path: Path,
) -> None:
    done = run_cli(
        "--breaker-dir",
        str(tmp_path / "breaker"),
        "--dispatch-dir",
        str(tmp_path / "dispatches"),
        "estimate",
        "--tier",
        "",
    )
    assert done.returncode == 1
    assert "plan_tier_unknown" in done.stderr
    assert "just prereqs plan-tier" in done.stderr


def test_watch_report_prints_the_verdicts_and_stays_silent_when_nothing_is_tripped(
    tmp_path: Path,
) -> None:
    """The recipe itself, run twice: once on healthy lanes and once on a tripped one.

    Both of the recipe's halves get a `tmp_path`. Injecting the breaker alone left the
    watch read on the box's live `~/.arma-cti/watch/`, so any unacknowledged watcher
    finding — two `watch_broken` ones from a crash cluster, in the case that found this
    — reddened this assertion for a diff that had touched neither (#249).
    """
    directory = tmp_path / "breaker"
    environment = {
        **os.environ,
        "CTI_ADMISSION_DIR": str(tmp_path / "admission"),
        "CTI_BREAKER_DIR": str(directory),
        "CTI_WATCH_DIR": str(tmp_path / "watch"),
    }

    def watch_report() -> str:
        return subprocess.run(
            # S607: `just` resolves off PATH on purpose, like every other tool this
            # project shells out to — the recipe under test is the one a caller runs.
            ["just", "watch-report"],  # noqa: S607
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        ).stdout

    assert watch_report().strip() == "", "every lane fine, and the read says nothing"

    # The recipe reads the wall clock, so the staged window has to be a real future one:
    # a reset already in the past would have settled to half-open and read as fine.
    wall = time.time()
    breaker.record_outcome(
        breaker.Store(directory=directory, endpoint=DEAD_ENDPOINT),
        "zai",
        breaker.Outcome(breaker.QUOTA_EXHAUSTED, reset_at=wall + HOUR),
        wall,
    )
    printed = [line for line in watch_report().splitlines() if line.startswith("lane=")]
    assert len(printed) == 1, "one line for the one lane that needs one"
    assert "lane=zai" in printed[0]
    assert "class=quota_exhausted" in printed[0]


def test_the_recipe_folds_the_breaker_into_the_read_at_the_top_of_a_turn() -> None:
    """`just watch-report` is what CLAUDE.md already puts at the top of an orchestrator turn."""
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    body = justfile.split("watch-report *args:", 1)[1].split("\n\n", 1)[0]
    assert "tools/breaker.py report" in body
    assert "tools/stall_watch.py report" in body
    assert "tools/admission.py trial-report" in body
    assert body.index("breaker.py") < body.index("stall_watch.py"), "the verdicts read first"
    assert body.index("stall_watch.py") < body.index("admission.py")
    assert "\nbreaker *args:\n" in justfile
