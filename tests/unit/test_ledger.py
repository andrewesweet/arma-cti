"""The per-dispatch ledger: a materialised view over the OTel bus (#227, ADR-0061).

Five claims, and the arrangement of every test is chosen to make one of them falsifiable.

**It is a view, not a writer.** The collector owns the records. So the tests assert on
what the ledger does *not* touch as hard as on what it produces: the rotating capture's
bytes are checksummed across a sync, and a dispatch with no records gets a row that says
so rather than a row filled in from the plan it could see all along.

**It names its source, and degrades typed and loudly.** Until the human runs #230's root
script there is no durable per-dispatch export, only the rotating capture — which carries
the same records and silently drops them at 50 MB × 5. Both worlds are exercised here,
because the difference between them is the difference between "this dispatch reached no
provider" and "this view cannot see", and typing the second as the first would be a
fabricated `infra_unavailable`.

**It normalises three lanes that report the same fact three ways.** The staged records
are provider-shaped and nothing calls a provider: Claude Code metric datapoints keyed by
`type`, an AI SDK span carrying `gen_ai.usage.*` *and* its own `ai.usage.*` copy of the
same numbers, and a cumulative counter — the three arrangements where a plausible reader
gets a wrong number rather than an error.

**Content logging is off, and the view is where it could come back on.** One test stages
a record carrying prompt text and asserts no byte of it reaches `ledger.json`.

**Its spend column is fraction-of-cap, and every way that column could lie is staged.**
The list-price figure is anti-correlated with plan cost by three orders of magnitude
(#218), so the tests assert on what the row must *not* say as much as on the arithmetic:
a foreign lane is never booked a Claude cost of zero, an unknown lane is never defaulted
onto Claude, the meter's absent half is `null` and never `0.0`, and no key called
`cost_usd` survives anywhere in the row.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from conftest import REPO, load_tool

ledger = load_tool("ledger")
prereqs = load_tool("prereqs")

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
DISPATCH = "d-20260805-120000-abc123"


# --------------------------------------------------------------------------- staging


def attrs(pairs: dict[str, Any]) -> list[dict[str, Any]]:
    """Render a mapping as an OTLP attribute list, picking each value's own wrapper."""
    rendered = []
    for key, value in pairs.items():
        if isinstance(value, bool):
            wrapper: dict[str, Any] = {"boolValue": value}
        elif isinstance(value, int):
            wrapper = {"intValue": str(value)}
        elif isinstance(value, float):
            wrapper = {"doubleValue": value}
        else:
            wrapper = {"stringValue": str(value)}
        rendered.append({"key": key, "value": wrapper})
    return rendered


def resource(dispatch_id: str | None = DISPATCH, **extra: str) -> dict[str, Any]:
    """Build a resource block as `just dispatch` tags it, via `OTEL_RESOURCE_ATTRIBUTES`."""
    block = {"service.name": "claude-code", "service.version": "2.1.222", **extra}
    if dispatch_id is not None:
        block |= {
            "cti.dispatch_id": dispatch_id,
            "cti.lane": "claude-native",
            "cti.profile": "opus-high",
            "cti.seat": "implementer",
            "cti.issue": "227",
        }
    return {"attributes": attrs(block)}


def metric_batch(
    name: str,
    points: list[tuple[dict[str, Any], float]],
    *,
    dispatch_id: str | None = DISPATCH,
    temporality: int = 1,
) -> dict[str, Any]:
    """One OTLP metric batch: a sum with the datapoints given, at the temporality given."""
    return {
        "resourceMetrics": [
            {
                "resource": resource(dispatch_id),
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": name,
                                "sum": {
                                    "aggregationTemporality": temporality,
                                    "isMonotonic": True,
                                    "dataPoints": [
                                        {
                                            "attributes": attrs(point_attrs),
                                            "asDouble": value,
                                            "timeUnixNano": "1785931331493000000",
                                        }
                                        for point_attrs, value in points
                                    ],
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }


def log_batch(
    event: str, event_attrs: dict[str, Any], *, dispatch_id: str | None = DISPATCH
) -> dict[str, Any]:
    """One OTLP log batch, in the shape Claude Code's events arrive in."""
    return {
        "resourceLogs": [
            {
                "resource": resource(dispatch_id),
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "timeUnixNano": "1785933263048000000",
                                "body": {"stringValue": event},
                                "attributes": attrs({"event.name": event, **event_attrs}),
                            }
                        ]
                    }
                ],
            }
        ]
    }


def span_batch(
    name: str, span_attrs: dict[str, Any], *, dispatch_id: str | None = DISPATCH
) -> dict[str, Any]:
    """One OTLP span batch, in the shape an opencode AI SDK span arrives in."""
    return {
        "resourceSpans": [
            {
                "resource": resource(dispatch_id, **{"service.name": "opencode"}),
                "scopeSpans": [{"spans": [{"name": name, "attributes": attrs(span_attrs)}]}],
            }
        ]
    }


def write_jsonl(path: Path, batches: list[dict[str, Any]]) -> Path:
    """Write OTLP batches as the line-delimited JSON the file exporter writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(batch) + "\n" for batch in batches), encoding="utf-8")
    return path


def stage_record(
    root: Path,
    *,
    dispatch_id: str = DISPATCH,
    issue: int = 227,
    base_sha: str = "0" * 40,
    result: dict[str, Any] | None = None,
    **plan: str,
) -> Path:
    """Lay down a dispatch record the way `just dispatch` leaves one.

    Any further keyword overrides a field of the plan — `lane="zai"` for a foreign one.
    """
    record = root / dispatch_id
    record.mkdir(parents=True, exist_ok=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": dispatch_id,
                "lane": "claude-native",
                "profile": "opus-high",
                "seat": "implementer",
                "issue": issue,
                "base_sha": base_sha,
                **plan,
            }
        ),
        encoding="utf-8",
    )
    if result is not None:
        (record / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return record


# ANN401: the tool is loaded by path rather than imported, so its `Options` NamedTuple
# has no importable name to annotate a return with.
def options(tmp_path: Path, **overrides: object) -> Any:  # noqa: ANN401
    """Build every path an action touches, all inside a tmp_path."""
    defaults = {
        "dispatch_root": tmp_path / "dispatches",
        "export_dir": tmp_path / "export",
        "capture": tmp_path / "capture" / "claude-telemetry.jsonl",
        "repo": tmp_path,
        "days": ledger.RETENTION_DAYS,
        "apply": False,
        "dispatch": "",
    }
    return ledger.Options(**{**defaults, **overrides})


def items_from(batches: list[dict[str, Any]], dispatch_id: str = DISPATCH) -> list[Any]:
    """Flatten staged batches the way the reader does, without going through a file."""
    return [item for batch in batches for item in ledger.items_for(batch, dispatch_id)]


# ---------------------------------------------------------------- cross-lane usage


def test_claude_code_token_datapoints_total_by_their_type_attribute() -> None:
    items = items_from(
        [
            metric_batch(
                "claude_code.token.usage",
                [
                    ({"type": "input"}, 100),
                    ({"type": "input"}, 40),
                    ({"type": "output"}, 7),
                    ({"type": "cacheRead"}, 20000),
                    ({"type": "cacheCreation"}, 3000),
                ],
            ),
            metric_batch("claude_code.cost.usage", [({"model": "opus"}, 0.25)]),
        ]
    )
    usage = ledger.normalise_usage(items)
    assert (usage.input_tokens, usage.output_tokens) == (140, 7)
    assert (usage.cache_read_tokens, usage.cache_creation_tokens) == (20000, 3000)
    assert (usage.list_price_usd, usage.list_priced) == (0.25, True)


def test_a_cumulative_counter_contributes_its_maximum_and_not_its_sum() -> None:
    # A monotonic cumulative series reports its running total on every export, so summing
    # its datapoints multiplies the dispatch's spend by how often the collector scraped.
    # Claude Code exports delta today; Codex's temporality is unverified, which is the
    # whole reason the reader believes the record's own `aggregationTemporality`.
    same_series = {"type": "input", "model": "glm"}
    items = items_from(
        [
            metric_batch(
                "codex.turn.token_usage",
                [(same_series, 100), (same_series, 250), (same_series, 400)],
                temporality=2,
            )
        ]
    )
    assert ledger.normalise_usage(items).input_tokens == 400


def test_two_cumulative_series_of_one_metric_each_contribute_their_own_maximum() -> None:
    items = items_from(
        [
            metric_batch(
                "codex.turn.token_usage",
                [
                    ({"type": "input", "model": "a"}, 100),
                    ({"type": "input", "model": "a"}, 300),
                    ({"type": "input", "model": "b"}, 50),
                ],
                temporality=2,
            )
        ]
    )
    assert ledger.normalise_usage(items).input_tokens == 350


def test_an_ai_sdk_span_carrying_both_spellings_is_counted_once() -> None:
    # The AI SDK puts `gen_ai.usage.input_tokens` and `ai.usage.inputTokens` on the same
    # span with the same number in each. Adding both doubles every opencode dispatch.
    items = items_from(
        [
            span_batch(
                "ai.generateText.doGenerate",
                {
                    "gen_ai.usage.input_tokens": 1200,
                    "ai.usage.inputTokens": 1200,
                    "gen_ai.usage.output_tokens": 340,
                    "ai.usage.outputTokens": 340,
                    "ai.usage.cachedInputTokens": 900,
                },
            )
        ]
    )
    usage = ledger.normalise_usage(items)
    assert (usage.input_tokens, usage.output_tokens, usage.cache_read_tokens) == (1200, 340, 900)


def test_a_lane_that_reports_tokens_and_no_list_price_is_unpriced_rather_than_free() -> None:
    # opencode reports tokens and never money. A zero here would read as a free dispatch.
    items = items_from([span_batch("RunInteractive.turn", {"gen_ai.usage.input_tokens": 500})])
    usage = ledger.normalise_usage(items)
    assert (usage.list_priced, usage.list_price_usd) == (False, 0.0)
    assert usage.document()["list_price_usd"] is None


def test_a_token_type_the_reader_does_not_know_is_reported_not_dropped() -> None:
    items = items_from([metric_batch("codex.turn.token_usage", [({"type": "reasoning"}, 900)])])
    usage = ledger.normalise_usage(items)
    assert usage.input_tokens == 0
    assert usage.unclassified == ("codex.turn.token_usage:type='reasoning'",)


def test_another_dispatch_s_records_in_the_same_file_are_not_read() -> None:
    batches = [
        metric_batch("claude_code.token.usage", [({"type": "input"}, 10)]),
        metric_batch("claude_code.token.usage", [({"type": "input"}, 999)], dispatch_id="d-other"),
        metric_batch("claude_code.token.usage", [({"type": "input"}, 500)], dispatch_id=None),
    ]
    assert ledger.normalise_usage(items_from(batches)).input_tokens == 10


# ------------------------------------------------------------- the spend column
#
# ADR-0061 Decision 1 optimises Claude spend, and #220 settles what that number is:
# percentage points of the binding plan window, estimated from output tokens over a
# measured constant. Every test below is arranged so that one way of getting that wrong —
# ranking on list price, defaulting a foreign lane to zero, reporting an estimator nobody
# can check, or reading a silent meter as free — produces a red rather than a plausible
# number.


def test_a_claude_dispatch_is_priced_in_points_of_both_windows_from_its_output_tokens() -> None:
    # One five-hour point is 30,209 output tokens and one seven-day point is 181,253
    # (#218's control arm: 6 and 1 points on the same 181,253 tokens).
    windows = ledger.cap_fraction("claude-native", ledger.Usage(output_tokens=30209)).document()[
        "windows"
    ]
    assert windows["five_hour"]["est"] == pytest.approx(1.0)
    assert windows["seven_day"]["est"] == pytest.approx(30209 / 181253)
    assert (windows["five_hour"]["tokens_per_point"], windows["seven_day"]["tokens_per_point"]) == (
        30209,
        181253,
    )


def test_the_estimator_reads_output_tokens_and_nothing_else() -> None:
    # Cache reads are 97% of this project's raw tokens and measured at under 1/450th the
    # per-token plan weight. A dispatch that read a hundred million of them and wrote
    # nothing costs the plan nothing, and `excludes` is where that assumption is named.
    priced = ledger.cap_fraction(
        "claude-native",
        ledger.Usage(input_tokens=4_000_000, cache_read_tokens=100_000_000, output_tokens=0),
    ).document()
    assert priced["windows"]["five_hour"]["est"] == 0.0
    assert (priced["basis"], priced["excludes"]) == ("output_tokens", ["cache_read"])


def test_both_halves_are_recorded_per_window_and_the_meter_half_is_absent_not_zero() -> None:
    # Recording only `observed` gives a ledger of zeroes — a single dispatch is two to
    # three orders of magnitude below the meter's integer resolution. Recording only
    # `est` gives a ledger nobody can check. And a 0.0 here would assert that the meter
    # said "free", which is #218's third confound: meter silence is not evidence of free.
    document = ledger.cap_fraction("claude-native", ledger.Usage(output_tokens=90627)).document()
    for window in ("five_hour", "seven_day"):
        assert set(document["windows"][window]) >= {"est", "observed"}
        assert document["windows"][window]["observed"] is None
    assert "quota feed" in document["observed_reason"]


def test_a_foreign_lane_is_priced_against_its_own_pool_and_never_claude_at_zero() -> None:
    # The counters on a z.ai row are z.ai's tokens. Dividing them by a Claude calibration
    # would charge the wrong pool; booking the row a Claude cost of zero would make
    # routing work off Claude look free by construction. Neither happens: the pool is
    # z.ai's, no Claude calibration is applied, and the estimator says why it is absent.
    document = ledger.cap_fraction("zai", ledger.Usage(output_tokens=50_000)).document()
    assert document["pool"] == "zai"
    assert document["calibration_id"] is None
    assert [window["est"] for window in document["windows"].values()] == [None, None]
    assert "prompt counts" in document["est_reason"]
    assert all(half is None for window in document["windows"].values() for half in window.values())


def test_an_unrecognised_lane_is_unpriced_rather_than_defaulted_onto_claude() -> None:
    for lane in (None, "", "codex"):
        document = ledger.cap_fraction(lane, ledger.Usage(output_tokens=30209)).document()
        assert (document["pool"], document["windows"], document["calibration_id"]) == (
            None,
            {},
            None,
        )


def test_the_row_carries_every_input_the_estimator_ran_on() -> None:
    # A recalibration must re-derive history rather than invalidate it: without the
    # calibration id, the first plan change silently rewrites every past number.
    document = ledger.cap_fraction("claude-native", ledger.Usage(output_tokens=1)).document()
    assert document["calibration_id"] == "claude/218-2026-08-05"
    assert (document["unit"], document["basis"]) == ("percentage_points", "output_tokens")
    assert document["windows"]["five_hour"]["tokens_per_point"] == 30209


def test_the_binding_window_is_the_meters_answer_and_is_never_guessed() -> None:
    # Scarcity routing, when it replaces Decision 1's greedy rule, routes on the window
    # nearest exhaustion. Which one that is depends on accumulated consumption, not on
    # this dispatch's share, so a view with no meter names none.
    document = ledger.cap_fraction("claude-native", ledger.Usage(output_tokens=30209)).document()
    assert document["binding_window"] is None
    assert "guessing" in document["binding_reason"]


def test_the_orchestrators_own_turns_are_recorded_as_missing_rather_than_zero() -> None:
    # An in-session subagent shares its parent's resource block, so the turns that
    # composed a briefing and read its report reach no row. Under-attribution stated is
    # the difference between an incomplete number and a wrong one.
    for lane in ("claude-native", "zai"):
        document = ledger.cap_fraction(lane, ledger.Usage(output_tokens=10)).document()
        assert document["attribution"] == "dispatch_only"
        assert "under-attribution" in document["attribution_note"]


# --------------------------------------------------------------- source preference


def test_the_durable_export_is_preferred_over_the_rotating_capture(tmp_path: Path) -> None:
    export = write_jsonl(tmp_path / "export" / f"dispatch-{DISPATCH}.jsonl", [])
    capture = write_jsonl(tmp_path / "capture.jsonl", [])
    source = ledger.choose_source(DISPATCH, export.parent, capture)
    assert (source.kind, source.path, source.degraded) == (ledger.SOURCE_EXPORT, export, False)


def test_the_rotating_capture_is_the_source_until_the_export_exists(tmp_path: Path) -> None:
    capture = write_jsonl(tmp_path / "capture.jsonl", [])
    source = ledger.choose_source(DISPATCH, tmp_path / "export", capture)
    assert (source.kind, source.degraded) == (ledger.SOURCE_CAPTURE, True)


def test_a_sync_with_neither_source_refuses_infra_unavailable(tmp_path: Path) -> None:
    stage_record(tmp_path / "dispatches")
    lines, code = ledger.sync(options(tmp_path), NOW)
    assert code == ledger.EXIT_REFUSED
    assert "refused=telemetry_source_absent" in lines
    assert "class=infra_unavailable" in lines
    assert any("Stop." in line for line in lines)


def test_a_row_read_from_the_capture_says_so_and_the_sync_warns(tmp_path: Path) -> None:
    record = stage_record(tmp_path / "dispatches", result={"returncode": 0})
    write_jsonl(
        tmp_path / "capture" / "claude-telemetry.jsonl",
        [metric_batch("claude_code.token.usage", [({"type": "input"}, 5)])],
    )
    lines, code = ledger.sync(options(tmp_path), NOW)
    row = json.loads((record / "ledger.json").read_text(encoding="utf-8"))
    assert code == 0
    assert row["source"]["degraded"] is True
    assert row["source"]["kind"] == ledger.SOURCE_CAPTURE
    assert any(line.startswith("warning=degraded_source") for line in lines)
    assert any("source=rotating_capture degraded=true" in line for line in lines)


# ------------------------------------------------------------------ end-state typing


def test_a_dispatcher_refusal_carries_its_own_class_through(tmp_path: Path) -> None:
    source = ledger.Source(ledger.SOURCE_EXPORT, tmp_path / "f.jsonl")
    state = ledger.type_end_state(
        [], {"refusal": "worktree_missing", "failure_class": "infra_unavailable"}, source
    )
    assert state.class_ == "infra_unavailable"
    assert "worktree_missing" in state.evidence[0]


def test_a_provider_refusal_record_types_the_dispatch_provider_refused() -> None:
    items = items_from(
        [log_batch("claude_code.api_refusal", {"refusal_category": "policy", "model": "glm-5.2"})]
    )
    state = ledger.type_end_state(
        items, {"returncode": 1}, ledger.Source(ledger.SOURCE_EXPORT, None)
    )
    assert state.class_ == "provider_refused"
    assert state.evidence == ("claude_code.api_refusal refusal_category=policy model=glm-5.2",)


def test_a_rate_limited_provider_error_types_the_dispatch_quota_exhausted() -> None:
    items = items_from(
        [
            log_batch(
                "claude_code.api_error",
                {
                    "status_code": "429",
                    "error_type": "rate_limit_error",
                    "reset_at": "2026-08-05T17:00:00Z",
                },
            )
        ]
    )
    state = ledger.type_end_state(
        items, {"returncode": 1}, ledger.Source(ledger.SOURCE_EXPORT, None)
    )
    assert state.class_ == "quota_exhausted"
    # The reset time is copied verbatim from the record and never computed here: what a
    # closed lane then waits for, and when it reopens, is #226's breaker, not the view's.
    assert "reset_at=2026-08-05T17:00:00Z" in state.evidence[0]


def test_a_refusal_outranks_a_quota_error_in_the_same_run() -> None:
    items = items_from(
        [
            log_batch("claude_code.api_error", {"status_code": "429"}),
            log_batch("claude_code.api_refusal", {"refusal_category": "policy"}),
        ]
    )
    state = ledger.type_end_state(
        items, {"returncode": 1}, ledger.Source(ledger.SOURCE_EXPORT, None)
    )
    assert state.class_ == "provider_refused"


def test_no_record_in_the_durable_export_means_the_dispatch_reached_no_provider() -> None:
    state = ledger.type_end_state(
        [], {"returncode": 0}, ledger.Source(ledger.SOURCE_EXPORT, Path("dispatch-x.jsonl"))
    )
    assert state.class_ == "infra_unavailable"


def test_no_record_from_a_rotating_source_is_unknown_and_never_infra_unavailable() -> None:
    # The capture drops records at 50MB x 5. Reading that absence as "reached no
    # provider" would be the view inventing a fact about the dispatch from its own
    # blindness — which is exactly what `infra_unavailable` says not to interpret.
    state = ledger.type_end_state(
        [], {"returncode": 0}, ledger.Source(ledger.SOURCE_CAPTURE, Path("capture.jsonl"))
    )
    assert state.class_ == "unknown"
    assert "rotates" in state.reason


def test_a_run_with_no_result_yet_is_unknown_rather_than_ended() -> None:
    items = items_from([metric_batch("claude_code.token.usage", [({"type": "input"}, 1)])])
    state = ledger.type_end_state(items, None, ledger.Source(ledger.SOURCE_EXPORT, None))
    assert (state.class_, state.evidence) == ("unknown", ())
    assert "has not ended" in state.reason


def test_a_run_that_ended_with_records_and_no_provider_failure_is_ok() -> None:
    items = items_from([metric_batch("claude_code.token.usage", [({"type": "input"}, 1)])])
    state = ledger.type_end_state(
        items, {"returncode": 0}, ledger.Source(ledger.SOURCE_EXPORT, None)
    )
    assert state.class_ == "ok"


# -------------------------------------------------------------------- content logging


def test_no_attribute_outside_the_allowlist_reaches_the_row(tmp_path: Path) -> None:
    # Content logging is off and the `prompt` attribute is the literal `<REDACTED>`
    # today. The ledger is where it would come back on, so the row copies only codes,
    # categories and timestamps — never a body, never a value a model wrote.
    body = "def deploy_key(): return 'sk-live-not-a-real-key'"
    record = stage_record(tmp_path / "dispatches", result={"returncode": 1})
    write_jsonl(
        tmp_path / "export" / f"dispatch-{DISPATCH}.jsonl",
        [
            log_batch("claude_code.user_prompt", {"prompt": body, "prompt_length": 42}),
            log_batch("claude_code.api_refusal", {"refusal_category": "policy", "detail": body}),
        ],
    )
    ledger.sync(options(tmp_path), NOW)
    written = (record / "ledger.json").read_text(encoding="utf-8")
    assert body not in written
    assert "deploy_key" not in written
    assert "refusal_category=policy" in written


# ---------------------------------------------------------------------------- the join


def run_git(*args: str, cwd: Path) -> None:
    """Run one git command in the staged repo, failing the test if it refuses."""
    # S603/S607: fixed literals and a tmp_path, and `git` resolves off PATH as everywhere.
    subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Build a real repository with a real `origin/main`, since that is what the join reads."""
    root = tmp_path / "repo"
    root.mkdir()
    run_git("init", "-q", "-b", "main", cwd=root)
    run_git("config", "user.email", "t@example.com", cwd=root)
    run_git("config", "user.name", "T", cwd=root)
    (root / "a.txt").write_text("one", encoding="utf-8")
    run_git("add", ".", cwd=root)
    run_git("commit", "-qm", "chore: the base", cwd=root)
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=root)
    return root


def head(repo_path: Path) -> str:
    """Return the staged repo's current commit."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def land(repo_path: Path, message: str) -> str:
    """Commit on `main` and move `origin/main` to it, as a push then a fetch would."""
    (repo_path / f"{time.time_ns()}.txt").write_text("x", encoding="utf-8")
    run_git("add", ".", cwd=repo_path)
    run_git("commit", "-qm", message, cwd=repo_path)
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo_path)
    return head(repo_path)


def test_the_landed_sha_is_the_commit_on_origin_main_that_references_the_issue(repo: Path) -> None:
    base = head(repo)
    landed_sha = land(repo, "feat: the telemetry spine\n\nrefs #227")
    landing = ledger.landed(repo, 227, base)
    assert (landing.sha, landing.commits) == (landed_sha, 1)


def test_several_commits_on_one_issue_report_the_newest_and_the_count(repo: Path) -> None:
    base = head(repo)
    land(repo, "feat: the first half\n\nrefs #227")
    newest = land(repo, "test: the second half\n\nrefs #227")
    landing = ledger.landed(repo, 227, base)
    assert (landing.sha, landing.commits) == (newest, 2)


def test_a_longer_issue_number_is_not_a_match_for_a_shorter_one(repo: Path) -> None:
    base = head(repo)
    land(repo, "feat: something else\n\nrefs #2270")
    assert ledger.landed(repo, 227, base).sha is None


def test_a_commit_before_the_dispatch_s_base_sha_is_not_this_dispatch_s_landing(repo: Path) -> None:
    land(repo, "feat: landed before the dispatch was armed\n\nrefs #227")
    base = head(repo)
    assert ledger.landed(repo, 227, base).sha is None


def test_a_checkout_without_the_ref_says_so_rather_than_claiming_nothing_landed(
    repo: Path,
) -> None:
    run_git("update-ref", "-d", "refs/remotes/origin/main", cwd=repo)
    landing = ledger.landed(repo, 227, head(repo))
    assert (landing.sha, landing.reason) == (None, "origin/main is not in this checkout")


def test_the_gate_outcome_is_landed_when_a_commit_carries_the_issue() -> None:
    landing = ledger.Landing("abc", 1, "referenced")
    outcome = ledger.gate_outcome(landing, {"returncode": 0}, ledger.EndState("ok", ""))
    assert outcome == "landed"


def test_a_run_still_going_is_running_rather_than_not_landed() -> None:
    outcome = ledger.gate_outcome(
        ledger.Landing(None, 0, "x"), None, ledger.EndState("unknown", "")
    )
    assert outcome == "running"


def test_a_dispatch_that_was_never_a_result_is_not_reported_as_a_failed_gate() -> None:
    # `quota_exhausted` says nothing about the code under test, so calling it a gate
    # failure would put a routing fact into the quality record ADR-0061 Decision 6 reads.
    outcome = ledger.gate_outcome(
        ledger.Landing(None, 0, "x"), {"returncode": 1}, ledger.EndState("quota_exhausted", "")
    )
    assert outcome == "not_a_result"


def test_a_completed_run_that_landed_nothing_is_not_landed() -> None:
    outcome = ledger.gate_outcome(
        ledger.Landing(None, 0, "x"), {"returncode": 0}, ledger.EndState("ok", "")
    )
    assert outcome == "not_landed"


# ------------------------------------------------------------- the durable row itself


def test_a_dispatched_run_produces_one_durable_record_keyed_by_its_dispatch_id(
    tmp_path: Path, repo: Path
) -> None:
    base = head(repo)
    landed_sha = land(repo, "feat: the spine\n\nrefs #227")
    record = stage_record(
        tmp_path / "dispatches",
        base_sha=base,
        result={"returncode": 0, "ended_at": "2026-08-05T11:00:00+00:00"},
    )
    write_jsonl(
        tmp_path / "export" / f"dispatch-{DISPATCH}.jsonl",
        [
            metric_batch(
                "claude_code.token.usage", [({"type": "input"}, 120), ({"type": "output"}, 8)]
            ),
            metric_batch("claude_code.cost.usage", [({"model": "opus"}, 0.5)]),
            log_batch("claude_code.api_request", {"model": "opus"}),
        ],
    )
    lines, code = ledger.sync(options(tmp_path, repo=repo), NOW)

    row = json.loads((record / "ledger.json").read_text(encoding="utf-8"))
    assert code == 0
    assert row["schema"] == ledger.SCHEMA
    assert (row["dispatch_id"], row["lane"], row["issue"]) == (DISPATCH, "claude-native", 227)
    assert row["source"] == {
        "kind": ledger.SOURCE_EXPORT,
        "path": str(tmp_path / "export" / f"dispatch-{DISPATCH}.jsonl"),
        "degraded": False,
    }
    assert row["records"] == {"total": 4, "metrics": 3, "logs": 1, "spans": 0}
    assert (row["usage"]["input_tokens"], row["usage"]["list_price_usd"]) == (120, 0.5)
    assert row["cap_fraction"]["pool"] == "claude"
    assert row["cap_fraction"]["windows"]["five_hour"]["est"] == pytest.approx(8 / 30209)
    assert row["end_state"]["class"] == "ok"
    assert (row["gate"]["outcome"], row["gate"]["landed"]["sha"]) == ("landed", landed_sha)
    assert any(line.startswith("ok=synced rows=1 degraded=0") for line in lines)


def test_no_row_calls_anything_cost_usd_and_the_summary_line_carries_both_halves(
    tmp_path: Path,
) -> None:
    # The one number ADR-0061 Decision 1 optimises must resolve to fraction-of-cap. A key
    # called `cost_usd` is how it would resolve to list price instead — #218 modelled
    # $849.76 for a run that moved the plan meter zero — so the name is gone from the row
    # and the summary line prices in points, both halves, list price nowhere.
    record = stage_record(tmp_path / "dispatches", result={"returncode": 0})
    write_jsonl(
        tmp_path / "export" / f"dispatch-{DISPATCH}.jsonl",
        [
            metric_batch("claude_code.token.usage", [({"type": "output"}, 30209)]),
            metric_batch("claude_code.cost.usage", [({"model": "opus"}, 849.76)]),
        ],
    )
    lines, _ = ledger.sync(options(tmp_path), NOW)
    row = json.loads((record / "ledger.json").read_text(encoding="utf-8"))

    assert "cost_usd" not in json.dumps(row).replace("list_price_usd", "")
    assert row["usage"]["list_price_usd"] == 849.76
    summary = next(line for line in lines if line.startswith("dispatch="))
    assert "cap5h_est=1.000000" in summary
    assert "cap5h_obs=none" in summary
    assert "849" not in summary


def test_a_foreign_lanes_row_takes_its_pool_from_the_plan_and_not_from_the_counters(
    tmp_path: Path,
) -> None:
    # The counters look identical whichever lane emitted them — the z.ai lane runs the
    # same binary against a different endpoint — so the pool has to come from the plan.
    # Reading it off the records would price z.ai's tokens against Claude's calibration.
    record = stage_record(tmp_path / "dispatches", lane="zai", result={"returncode": 0})
    write_jsonl(
        tmp_path / "export" / f"dispatch-{DISPATCH}.jsonl",
        [metric_batch("claude_code.token.usage", [({"type": "output"}, 30209)])],
    )
    ledger.sync(options(tmp_path), NOW)
    row = json.loads((record / "ledger.json").read_text(encoding="utf-8"))
    assert (row["lane"], row["cap_fraction"]["pool"]) == ("zai", "zai")
    assert row["cap_fraction"]["windows"]["five_hour"]["est"] is None
    assert row["usage"]["output_tokens"] == 30209


def test_the_row_is_derived_and_never_synthesised_from_the_plan(tmp_path: Path) -> None:
    # The plan holds a lane, a profile and an issue. A dispatch that put nothing on the
    # bus must still report zero records rather than a row that reads like a run.
    record = stage_record(tmp_path / "dispatches", result={"returncode": 0})
    write_jsonl(tmp_path / "export" / f"dispatch-{DISPATCH}.jsonl", [])
    ledger.sync(options(tmp_path), NOW)
    row = json.loads((record / "ledger.json").read_text(encoding="utf-8"))
    assert row["records"]["total"] == 0
    assert row["usage"]["input_tokens"] == 0
    assert row["usage"]["list_price_usd"] is None
    assert row["end_state"]["class"] == "infra_unavailable"


def test_a_second_sync_over_unchanged_records_writes_the_same_row(tmp_path: Path) -> None:
    record = stage_record(tmp_path / "dispatches", result={"returncode": 0})
    write_jsonl(
        tmp_path / "export" / f"dispatch-{DISPATCH}.jsonl",
        [metric_batch("claude_code.token.usage", [({"type": "input"}, 3)])],
    )
    ledger.sync(options(tmp_path), NOW)
    first = (record / "ledger.json").read_text(encoding="utf-8")
    ledger.sync(options(tmp_path), NOW)
    assert (record / "ledger.json").read_text(encoding="utf-8") == first


def test_one_dispatch_can_be_synced_without_reading_the_others(tmp_path: Path) -> None:
    stage_record(tmp_path / "dispatches", dispatch_id="d-one", result={"returncode": 0})
    stage_record(tmp_path / "dispatches", dispatch_id="d-two", result={"returncode": 0})
    write_jsonl(tmp_path / "export" / "dispatch-d-one.jsonl", [])
    ledger.sync(options(tmp_path, dispatch="d-one"), NOW)
    assert (tmp_path / "dispatches" / "d-one" / "ledger.json").is_file()
    assert not (tmp_path / "dispatches" / "d-two" / "ledger.json").exists()


def test_show_refuses_a_dispatch_that_has_not_been_synced(tmp_path: Path) -> None:
    stage_record(tmp_path / "dispatches")
    lines, code = ledger.show(options(tmp_path, dispatch=DISPATCH))
    assert (code, "refused=not_materialised" in lines) == (ledger.EXIT_REFUSED, True)


# ------------------------------------------ the capture and the diagnostics skill


def test_a_sync_leaves_the_rotating_capture_byte_for_byte_unchanged(tmp_path: Path) -> None:
    # One writer, and it is the collector. A view that appended to its own source would
    # be the second writer ADR-0061's telemetry ruling exists to forbid.
    stage_record(tmp_path / "dispatches", result={"returncode": 0})
    capture = write_jsonl(
        tmp_path / "capture" / "claude-telemetry.jsonl",
        [
            metric_batch("claude_code.token.usage", [({"type": "input"}, 9)]),
            metric_batch("claude_code.token.usage", [({"type": "input"}, 9)], dispatch_id=None),
        ],
    )
    before = hashlib.sha256(capture.read_bytes()).hexdigest()
    ledger.sync(options(tmp_path), NOW)
    assert hashlib.sha256(capture.read_bytes()).hexdigest() == before


def last_seen_per_session(path: Path) -> dict[str, str]:
    """Run the diagnostics skill's own query, transcribed from its `Data sources` §2.

    `~/.claude/skills/wsl-session-diagnostics/SKILL.md` walks
    `resourceMetrics[].scopeMetrics[].metrics[].sum.dataPoints[]` for `session.id` and
    `timeUnixNano`. Transcribed rather than imported because the skill is a global one
    this repository must never edit: the copy here is the assertion that the shape it
    reads still exists once dispatches are putting `cti.*` records through the same file.
    """
    last: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        document = json.loads(line)
        for block in document.get("resourceMetrics", []):
            for scope in block.get("scopeMetrics", []):
                for metric in scope.get("metrics", []):
                    for point in metric.get("sum", {}).get("dataPoints", []):
                        session = next(
                            (
                                entry["value"]["stringValue"]
                                for entry in point.get("attributes", [])
                                if entry["key"] == "session.id"
                            ),
                            None,
                        )
                        if session:
                            last[session] = max(
                                last.get(session, ""), point.get("timeUnixNano", "")
                            )
    return last


def test_the_diagnostics_skill_s_query_still_resolves_a_capture_carrying_cti_records(
    tmp_path: Path,
) -> None:
    capture = write_jsonl(
        tmp_path / "capture.jsonl",
        [
            metric_batch(
                "claude_code.token.usage",
                [({"session.id": "plain-session", "type": "input"}, 1)],
                dispatch_id=None,
            ),
            metric_batch(
                "claude_code.token.usage",
                [({"session.id": "dispatched-session", "type": "input"}, 2)],
            ),
        ],
    )
    assert last_seen_per_session(capture) == {
        "plain-session": "1785931331493000000",
        "dispatched-session": "1785931331493000000",
    }


def test_the_merged_collector_config_leaves_the_skill_s_own_leg_intact() -> None:
    # #230 asserts every existing line survives the merge. This asserts the three facts
    # the skill depends on by name, so a future edit to the merge that kept the lines but
    # moved the skill's exporter out of its pipeline would still be caught here.
    current = (REPO / "tests" / "fixtures" / "otelcol" / "config.yaml").read_text(encoding="utf-8")
    merged = prereqs.merge_collector_config(current).text
    assert "path: /var/log/claude-otel/claude-telemetry.jsonl" in merged
    for signal in ("metrics", "logs"):
        leg = f"    {signal}:\n      receivers: [otlp]\n"
        assert leg + "      processors: [batch]\n      exporters: [file/claude]" in merged
    assert "max_megabytes: 50" in merged


# ------------------------------------------------------------------------- retention


def age(path: Path, days: float) -> None:
    """Backdate a file, since the retention horizon is read off its mtime."""
    when = time.time() - days * ledger.SECONDS_PER_DAY
    os.utime(path, (when, when))


def stage_for_prune(
    tmp_path: Path, *, days: float, records: int = 1, source: str | None = None
) -> Path:
    """Stage a raw export file plus, unless `source` says otherwise, the row from it."""
    export = write_jsonl(
        tmp_path / "export" / f"dispatch-{DISPATCH}.jsonl",
        [metric_batch("claude_code.token.usage", [({"type": "input"}, 1)])] * records,
    )
    if source is not None:
        record = stage_record(tmp_path / "dispatches")
        (record / "ledger.json").write_text(
            json.dumps({"source": {"kind": source}, "records": {"total": records}}),
            encoding="utf-8",
        )
    age(export, days)
    return export


def test_a_raw_file_past_the_horizon_whose_row_came_from_it_is_prunable(tmp_path: Path) -> None:
    stage_for_prune(tmp_path, days=45, source=ledger.SOURCE_EXPORT)
    verdicts = ledger.prunable(options(tmp_path), time.time())
    assert [(verdict.prunable, verdict.reason) for verdict in verdicts] == [
        (True, "materialised from this file")
    ]


def test_a_raw_file_inside_the_horizon_is_kept(tmp_path: Path) -> None:
    stage_for_prune(tmp_path, days=2, source=ledger.SOURCE_EXPORT)
    assert ledger.prunable(options(tmp_path), time.time())[0].prunable is False


def test_a_raw_file_the_view_never_read_is_never_pruned(tmp_path: Path) -> None:
    # Pruning ahead of the view destroys the only copy of records nothing has read.
    stage_for_prune(tmp_path, days=99, source=None)
    verdict = ledger.prunable(options(tmp_path), time.time())[0]
    assert (verdict.prunable, "ledger-sync" in verdict.reason) == (False, True)


def test_a_row_taken_from_the_rotating_capture_does_not_licence_pruning_the_export(
    tmp_path: Path,
) -> None:
    stage_for_prune(tmp_path, days=99, source=ledger.SOURCE_CAPTURE)
    verdict = ledger.prunable(options(tmp_path), time.time())[0]
    assert (verdict.prunable, "rotating capture" in verdict.reason) == (False, True)


def test_a_row_that_read_no_records_out_of_the_file_does_not_licence_pruning_it(
    tmp_path: Path,
) -> None:
    stage_for_prune(tmp_path, days=99, records=0, source=ledger.SOURCE_EXPORT)
    assert ledger.prunable(options(tmp_path), time.time())[0].prunable is False


def test_prune_deletes_nothing_without_apply(tmp_path: Path) -> None:
    export = stage_for_prune(tmp_path, days=45, source=ledger.SOURCE_EXPORT)
    lines, code = ledger.prune(options(tmp_path), time.time())
    assert (code, export.is_file()) == (0, True)
    assert any(line.startswith("ok=dry_run") for line in lines)
    assert "action=re-run with --apply to delete them" in lines


def test_prune_with_apply_deletes_only_the_prunable_files(tmp_path: Path) -> None:
    doomed = stage_for_prune(tmp_path, days=45, source=ledger.SOURCE_EXPORT)
    spared = write_jsonl(tmp_path / "export" / "dispatch-d-unread.jsonl", [])
    age(spared, 99)
    lines, code = ledger.prune(options(tmp_path, apply=True), time.time())
    assert (code, doomed.exists(), spared.is_file()) == (0, False, True)
    assert any(line.startswith("ok=pruned files=2 prunable=1") for line in lines)


def test_the_materialised_rows_have_no_horizon_of_their_own(tmp_path: Path) -> None:
    # The rows are the evidence quoted into an issue months later, and they are small.
    # Nothing here deletes one, at any age; only the raw export has a horizon.
    record = stage_record(tmp_path / "dispatches")
    (record / "ledger.json").write_text(
        json.dumps({"source": {"kind": ledger.SOURCE_EXPORT}, "records": {"total": 1}}),
        encoding="utf-8",
    )
    age(record / "ledger.json", 3650)
    stage_for_prune(tmp_path, days=3650, source=ledger.SOURCE_EXPORT)
    ledger.prune(options(tmp_path, apply=True), time.time())
    assert (record / "ledger.json").is_file()


# ---------------------------------------------------------------------------- the seam


def test_the_recipe_runs_the_tool_and_the_tool_answers() -> None:
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    assert "ledger-sync" in justfile
    assert "uv run python tools/ledger.py" in justfile


def test_the_command_line_defaults_to_a_sync_over_the_state_directory() -> None:
    action, parsed = ledger.parse_args([])
    assert action == "sync"
    assert parsed.dispatch_root == ledger.DISPATCH_ROOT
    assert parsed.export_dir == ledger.LEDGER_EXPORT
    assert parsed.capture == ledger.ROTATING_CAPTURE
    assert parsed.apply is False


def test_show_without_a_dispatch_refuses_rather_than_printing_everything(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A refusal goes to stderr, as `tools/dispatch.py` does it: a caller piping stdout
    # into something must not receive a refusal as if it were a row.
    assert ledger.main(["show"]) == ledger.EXIT_REFUSED
    assert "refused=no_dispatch" in capsys.readouterr().err
