"""The observatory store (#482, spec #478): a cache rebuilt from immutable sources.

Six claims, and every test's arrangement exists to falsify one of them.

**Both spend encodings are read.** The staged world carries one lane's spend as
per-request log records and another's as a histogram metric — the two encodings the
issue names as its whole point — and the tests assert both appear, because the
failure mode is not an error but a lane booked at zero while looking correct.

**Spend is per lane and never summed.** A negative test walks every key the store
contains for a cross-lane total, because ADR-0061 Decision 5 is enforced
mechanically here or not at all.

**Absence is never cheap.** An uncalibrated lane renders `uncalibrated` with a null
cost, and a dispatch with no telemetry is a row with a reason rather than a dropped
row — the store's nulls all carry reasons, walked wholesale by one test.

**Malformed input is counted, named, and survived.** One truncated JSON line sits in
the staged world; the rebuild completes and the count appears in the output.

**The rebuild is deterministic and refused, not partial.** Two runs produce identical
bytes, and a source directory the process cannot see is a named refusal that writes
nothing.

**A pruned source is read visibly, never silently.** `ledger prune` deletes an export
file once a row materialised from it exists, so the staged world also stages the day
after a prune: file gone, `ledger.json` left. The numbers the row carries survive, the
numbers it cannot carry (the log-record encoding) render absent with a reason, and the
coverage line itself changes — a rebuild after a prune must not look like a rebuild
before one.

**The documentation runs.** The cookbook's first query is executed against the
shipped store, and the test executes every SQL block because a cookbook query that
does not run is worse than none.

**The occupancy view counts spans the run's own records attest, and the method is
pinned, not documented.** A dispatch's span is its `started_at` to its `ended_at`;
occupied time is the live count at each whole minute of a window the reader names,
summed — the method `tools/occupancy.py` published (#295). The staged world's spans
are arranged so every headline figure is hand-derived in the test: used 70 of
capacity 120 over sixty minutes, mean 1.1667, one thirty-minute gap, and a histogram
that runs above the ruled limit so `used` is a count of live dispatches and never a
clipped one. The mini-fixture pins the sampling itself: a dispatch whose forty
seconds cross no minute boundary contributes zero minutes, which is what separates
boundary sampling from duration rounding — two methods that disagree on exactly that
dispatch. A span is attested only by the run's own records: the current stop closeout
has an explicit `stopped` terminal state and no end, while a legacy closeout the stop
sweep wrote and a result that recorded no start of its own each occupy nothing and are
named by their reason — the fabrication that held 58% of the live store's
`used` until round 2 rejected it by record shape, never by dispatch id. Work that
started and did not complete is read from #489's `terminal_state` block (bounded
abandoned work occupies its own span; unbounded work occupies nothing and is named),
and a pruned dispatch's end and terminal state come from its row, never guessed.

**The flow view is percentiles, never a mean, and abandoned work is derived.** The
staged world carries a right-skewed landed sample on which nearest-rank and linear
interpolation disagree at every percentile, and the view's values are pinned to the
nearest-rank ones so a change of method is a red. The view's column list is pinned
exactly, so no mean can enter the headline slot. An abandoned work item is typed by
its dispatch's own `gate_outcome` — `not_a_result`, the existing vocabulary, every
not-a-result class of it — never by a list of issue numbers or an age heuristic.
The terminal residue is `stopped`: ended without a failure class, refused before
any child launched (#489's line — work that never started is not work that started
and did not finish, and the quota death that *did* start is the abandoned one), or
abandoned only by a seat that lands nothing — a review-seat death keeps its own
`not_a_result` row and never brands its item (#524).

**The rework view ranks only where its denominator exists, and marks its own limits.**
ADR-0071 ruling 6's key — fix rounds per landing — is computed for implementer-seat
profiles and no others, with the seat set derived from the registries rather than
named. A profile with no landings keeps its rounds visible and its rate undefined,
never a division; a seat that lands nothing by contract keeps its rework reported and
unranked, its reason distinguishing the contract from a miss. The companion measure,
dispatches per issue, is reported beside the key and explicitly unranked; the outcome
columns carry a `measures` marker naming them description; and the summary line states
the key's own spread and that its sample limit is an estimate, not a measurement.

**The session view states its boundary in every rendering path, and apportions to no
issue.** The staged spool carries one session spanning two months with its July render
in a rolled generation — so the period comes from the timestamp and not the file
boundary — a second session whose payload never carries the duration or lines
counters, a pre-#488 bare line, a render with no session id and a truncated line. The
cost counters are cumulative the way the real payload's are, so the per-period
figures are pinned as deltas; the token keys are staged as the window gauges the live
spool carries — falling and rising between renders — so a reader that mistakes one
for a counter is caught, not flattered. The orchestrator's absence is asserted as a
column on every row of both tables and a word on the summary line; the output-token
columns are absences whose reason names the gauge; the fully-loaded figure is absent
with the reason naming the halves' incommensurability, and carries the same boundary
as the overhead it derives from; and neither table holds
an issue column, so per-issue overhead is not something the output can express.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Mapping

import pytest
from conftest import REPO, load_tool

observatory = load_tool("observatory")
ledger = observatory.ledger
attribute_registry = load_tool("attribute_registry")
dispatch = load_tool("dispatch")

PLANNED = "2026-08-05T12:00:00+00:00"
AFTER_PLANNED = "2026-08-05T23:30:00+00:00"
ISSUE = 482
OTHER_ISSUE = 483

CLAUDE_DISPATCH = "d-20260805-120000-claud1"
CODEX_DISPATCH = "d-20260805-120000-codex1"
ZAI_DISPATCH = "d-20260805-120000-zai001"
BARE_DISPATCH = "d-20260805-120000-bare01"

# The flow view's own issues: three more landings at one, two and three hours, one
# abandoned by a quota death that started, one stopped — ended, never landed, no
# failure class — and one refused before any child launched, which #489 keeps out
# of abandoned and in the stopped residue. Their lead times with ISSUE's 41400 give
# the percentile tests a sample, [3600, 7200, 10800, 41400], on which nearest-rank
# and linear interpolation disagree at every percentile pinned below.
FLOW_A = "d-20260805-120000-flow01"
FLOW_B = "d-20260805-120000-flow02"
FLOW_C = "d-20260805-120000-flow03"
FLOW_D = "d-20260805-120000-flow04"
FLOW_E = "d-20260805-120000-flow05"
# Not `flow06`: the clock-endpoint test stages that id for its own issue, and two
# ids this close want no reader wondering whether they ever met in one world.
FLOW_F = "d-20260805-120000-flow07"
# The review-death issue's two halves: the implementer that ended clean and unlanded,
# and the review dispatch whose own harness closeout failed.
FLOW_G = "d-20260805-120000-flow08"
FLOW_H = "d-20260805-120000-flow09"

LANDED_ONE_HOUR = 490
LANDED_TWO_HOURS = 491
LANDED_THREE_HOURS = 492
ABANDONED_ISSUE = 493
STOPPED_ISSUE = 494
REFUSED_ISSUE = 496
BOUNDARY_IN_FLIGHT_ISSUE = 598
BOUNDARY_LANDED_ISSUE = 599
# #524's round-two shape: every implementer dispatch ended clean and unlanded, and a
# review dispatch's own harness closeout died — which must not brand the item.
REVIEW_DIED_ISSUE = 497
# The rework view's own issue: five rounds recorded against a dispatch that never
# lands — the zero-denominator row the ruled key must carry unranked, with its rounds
# visible, rather than as a division.
ROUNDY_ISSUE = 495

# One five-hour-window point exactly: the calibration's own numerator, so the cost
# row's arithmetic is pinned against `ledger`'s constant rather than a restated 30209.
CLAUDE_OUTPUT = ledger.CLAUDE_TOKENS_PER_POINT["five_hour"]
CODEX_OUTPUT = 54321

# The session view's own sessions: one spanning two months with token totals, one
# brief August session whose payload never carries a token total — the two
# arrangements the overhead's meter question turns on.
HUMAN_SESSION = "019fd51b-835f-7732-8855-a73841a75d01"
BRIEF_SESSION = "019fd51b-835f-7732-8855-a73841a75d02"


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


def resource(dispatch_id: str | None, lane: str) -> dict[str, Any]:
    """Build a resource block as `just dispatch` tags it, via `OTEL_RESOURCE_ATTRIBUTES`."""
    block: dict[str, Any] = {"service.name": "claude-code"}
    if dispatch_id is not None:
        block |= {
            "cti.dispatch_id": dispatch_id,
            "cti.lane": lane,
            "cti.profile": "a-profile",
            "cti.seat": "implementer",
            "cti.issue": str(ISSUE),
        }
    return {"attributes": attrs(block)}


def log_batch(
    event: str, event_attrs: dict[str, Any], *, dispatch_id: str, lane: str
) -> dict[str, Any]:
    """One OTLP log batch, in the shape Claude Code's per-request events arrive in."""
    return {
        "resourceLogs": [
            {
                "resource": resource(dispatch_id, lane),
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


def sum_metric_batch(
    name: str, points: list[tuple[dict[str, Any], float]], *, dispatch_id: str, lane: str
) -> dict[str, Any]:
    """One OTLP metric batch: a delta sum with the datapoints given."""
    return {
        "resourceMetrics": [
            {
                "resource": resource(dispatch_id, lane),
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": name,
                                "sum": {
                                    "aggregationTemporality": 1,
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


def histogram_metric_batch(
    name: str, points: list[tuple[dict[str, Any], float]], *, dispatch_id: str, lane: str
) -> dict[str, Any]:
    """One OTLP metric batch whose body is a histogram — Codex's token encoding.

    A histogram datapoint carries no `asInt`/`asDouble`; its `sum` over one turn's
    single observation is the count itself. A reader that models only scalar bodies
    returns rows, looks correct, and books the lane at zero (#243, and this issue's
    own trap).
    """
    return {
        "resourceMetrics": [
            {
                "resource": resource(dispatch_id, lane),
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": name,
                                "histogram": {
                                    "aggregationTemporality": 1,
                                    "dataPoints": [
                                        {"attributes": attrs(point_attrs), "sum": value}
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


def write_export(
    export_dir: Path, dispatch_id: str, batches: list[dict[str, Any]], *, truncate: str = ""
) -> Path:
    """Write one dispatch's export file, optionally ending in a truncated JSON line."""
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"dispatch-{dispatch_id}.jsonl"
    body = "".join(json.dumps(batch) + "\n" for batch in batches)
    path.write_text(body + truncate, encoding="utf-8")
    return path


def stage_record(  # noqa: PLR0913 — the seven parameters are the dispatch record's own fields
    root: Path,
    dispatch_id: str,
    *,
    issue: int = ISSUE,
    lane: str = "claude-native",
    profile: str = "a-profile",
    seat: str | None = "implementer",
    base_sha: str = "0" * 40,
) -> Path:
    """Lay down a dispatch record the way `just dispatch` leaves one.

    `base_sha` defaults to the never-landable placeholder: a dispatch staged after the
    fixture is a dispatch that lands nothing unless the test arms it from the world's
    real base, which is the arrangement a landing needs.
    """
    record = root / dispatch_id
    record.mkdir(parents=True, exist_ok=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": dispatch_id,
                "lane": lane,
                "profile": profile,
                "seat": seat,
                "issue": issue,
                "base_sha": base_sha,
                "planned_at": PLANNED,
            }
        ),
        encoding="utf-8",
    )
    return record


def write_loop(review_root: Path, issue: int, rounds: int) -> None:
    """Lay down one issue's `loop.json` the way `review_loop.store_loop` leaves it."""
    directory = review_root / str(issue)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "loop.json").write_text(
        json.dumps(
            {
                "version": 1,
                "issue": issue,
                "review_rounds": rounds,
                "findings": [],
            }
        ),
        encoding="utf-8",
    )


# The `end_state` block every materialised row carries — `ledger.py` writes it
# unconditionally — is where a pruned dispatch's typing is derived from, so the
# fixture writes the block a real row carries rather than omitting it.
PRUNED_END_STATE: dict[str, Any] = {
    "class": "ok",
    "reason": "the run ended and its records carry no refusal or quota failure",
    "evidence": [],
}


def write_ledger_row(
    record: Path,
    usage: dict[str, int],
    *,
    body: str | None = None,
    end_state: Mapping[str, Any] | None = PRUNED_END_STATE,
) -> None:
    """Lay down the `ledger.json` a sync leaves, or the exact bytes `body` names.

    The `end_state` block is written by default exactly as `ledger` writes it, because
    the post-prune read derives a dispatch's typing from it; pass `None` to reach the
    row-without-block read. The rest is the row's own shape, abbreviated to what a
    reader could plausibly reach for.
    """
    document = (
        body
        if body is not None
        else json.dumps(
            {
                "schema": ledger.SCHEMA,
                "dispatch_id": record.name,
                "source": {"kind": "ledger_export", "path": "/gone", "degraded": False},
                "records": {"total": 3, "metrics": 3, "logs": 0, "spans": 0},
                "usage": usage,
                "end_state": end_state,
            }
        )
    )
    (record / "ledger.json").write_text(document, encoding="utf-8")


def prune_export(world: World, dispatch_id: str, usage: dict[str, int]) -> None:
    """Stage the day after a prune: export file deleted, materialised row left."""
    (world.export_dir / f"dispatch-{dispatch_id}.jsonl").unlink()
    write_ledger_row(world.dispatch_root / dispatch_id, usage)


def write_render(  # noqa: PLR0913 — the eight parameters are the payload's own fields
    path: Path,
    ts: str,
    session_id: str,
    *,
    cost_usd: float | None = None,
    duration_ms: float | None = None,
    lines_added: float | None = None,
    lines_removed: float | None = None,
    window_output_tokens: float | None = None,
    window_input_tokens: float | None = None,
) -> None:
    """Append one #488-envelope render to a spool file the way the tap now leaves one.

    The payload is the shape the live spool carries: `cost` holds the four
    session-lifetime running totals, and every token key lives under
    `context_window` as a gauge of the current window — falling and rising between
    renders of one session, never a counter. A fixture that models a payload the
    source does not emit is what let the first round read a numerator that does not
    exist (#486's F2 raised in this very store), so this one emits no
    `cost.total_output_tokens` at all.
    """
    cost = {
        key: value
        for key, value in (
            ("total_cost_usd", cost_usd),
            ("total_duration_ms", duration_ms),
            ("total_lines_added", lines_added),
            ("total_lines_removed", lines_removed),
        )
        if value is not None
    }
    context_window = {
        key: value
        for key, value in (
            ("total_output_tokens", window_output_tokens),
            ("total_input_tokens", window_input_tokens),
        )
        if value is not None
    }
    payload: dict[str, Any] = {"session_id": session_id, "cost": cost}
    if context_window:
        payload["context_window"] = context_window
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as spool:
        spool.write(json.dumps({"ts": ts, "payload": payload}) + "\n")


def run_git(*args: str, cwd: Path, at: str = "") -> None:
    """Run one git command in the staged repo, failing the test if it refuses."""
    # S603/S607: fixed literals and a tmp_path, and `git` resolves off PATH as everywhere.
    subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_AUTHOR_DATE": at, "GIT_COMMITTER_DATE": at} if at else None,
    )


class World(NamedTuple):
    """The staged world: four dispatches, three lanes, two issues, one landing."""

    dispatch_root: Path
    export_dir: Path
    review_root: Path
    spool: Path
    store_dir: Path
    repo: Path
    base_sha: str
    landed_sha: str
    queue_dir: Path


@pytest.fixture
def world(  # noqa: PLR0915 — the staged world is the arrangement, one statement per dispatch shape it owes the suites below
    tmp_path: Path,
) -> World:
    """Stage one dispatch per encoding, one without telemetry, and one landing.

    The Claude dispatch's spend exists **only** as `claude_code.api_request` log
    records, the Codex dispatch's **only** as a `codex.turn.token_usage` histogram,
    and the z.ai dispatch's as the `claude_code.token.usage` sum metric the `claude`
    binary emits on that lane — the three arrangements a one-encoding reader gets
    wrong, each wrong in a different column. The Codex export ends in a truncated
    JSON line, and the bare dispatch has no export file at all.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git("init", "-q", "-b", "main", cwd=repo)
    run_git("config", "user.email", "t@example.com", cwd=repo)
    run_git("config", "user.name", "T", cwd=repo)
    (repo / "a.txt").write_text("one", encoding="utf-8")
    run_git("add", ".", cwd=repo)
    run_git("commit", "-qm", "chore: the base", cwd=repo)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)

    dispatch_root = tmp_path / "dispatches"
    export_dir = tmp_path / "export"
    review_root = tmp_path / "review"
    review_root.mkdir()
    # Three loops over the fixture's own issues: zero, one and two rounds. Zero rounds
    # is the common case the summary line has to state rather than hide — most issues
    # sit at round zero — and the two-round issue gives the key a numerator.
    write_loop(review_root, ISSUE, 0)
    write_loop(review_root, LANDED_ONE_HOUR, 1)
    write_loop(review_root, LANDED_TWO_HOURS, 2)
    stage_record(dispatch_root, CLAUDE_DISPATCH, lane="claude-native")
    stage_record(dispatch_root, CODEX_DISPATCH, lane="codex")
    stage_record(dispatch_root, ZAI_DISPATCH, lane="zai")
    stage_record(dispatch_root, BARE_DISPATCH, issue=OTHER_ISSUE)
    for dispatch, issue in (
        (FLOW_A, LANDED_ONE_HOUR),
        (FLOW_B, LANDED_TWO_HOURS),
        (FLOW_C, LANDED_THREE_HOURS),
        (FLOW_D, ABANDONED_ISSUE),
        (FLOW_E, STOPPED_ISSUE),
        (FLOW_F, REFUSED_ISSUE),
        (FLOW_G, REVIEW_DIED_ISSUE),
    ):
        stage_record(dispatch_root, dispatch, issue=issue)
    # FLOW_D is #489's live quota death, in the shape the record actually carries: the
    # child launched and exited 1, the OTel bus said nothing (no export file), and the
    # only witness is the dispatcher's own classification of its run's log. A fixture
    # modelling any other shape is what cost #488 a review round.
    (dispatch_root / FLOW_D / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": FLOW_D,
                "status": "child_finished",
                "returncode": 1,
                "outcome": "quota_exhausted",
                "started_at": "2026-08-05T12:30:00+00:00",
                "ended_at": "2026-08-05T12:40:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    # FLOW_E ran to a clean exit and landed nothing — terminal without a failure class.
    # FLOW_G/FLOW_H are #524's round-two shape: the implementer half ended clean and
    # unlanded (work complete, landing not yet ours to give), and the review half's own
    # harness closeout failed after its child ran — the not-a-result typing that must
    # stay on the review row and never brand the issue.
    (dispatch_root / FLOW_E / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": FLOW_E,
                "status": "child_finished",
                "returncode": 0,
                "started_at": "2026-08-05T12:30:00+00:00",
                "ended_at": "2026-08-05T13:30:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    # FLOW_F refused before any child launched — a failure class on work that never
    # started, which is not "work that started and did not finish" (#489's line).
    (dispatch_root / FLOW_F / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": FLOW_F,
                "status": "child_not_launched",
                "refusal": "worktree_missing",
                "failure_class": "infra_unavailable",
                "ended_at": "2026-08-05T12:10:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    stage_record(dispatch_root, FLOW_H, issue=REVIEW_DIED_ISSUE, seat="review")
    # The implementer half: clean exit, nothing landed — `not_landed`, the outcome of
    # work that ended and awaits a landing.
    (dispatch_root / FLOW_G / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": FLOW_G,
                "status": "child_finished",
                "returncode": 0,
                "started_at": "2026-08-05T12:30:00+00:00",
                "ended_at": "2026-08-05T13:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    # The review half: the dispatcher's own closeout failed after the review child ran
    # — #489's widened typing makes it `untyped_harness_failure`, and this test exists
    # to hold that the typing stops at the dispatch row.
    (dispatch_root / FLOW_H / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": FLOW_H,
                "status": "harness_failed_after_child",
                "returncode": 1,
                "started_at": "2026-08-05T13:10:00+00:00",
                "ended_at": "2026-08-05T13:40:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    # Claude: per-request log records, no metric — the encoding half no reader covered.
    write_export(
        export_dir,
        CLAUDE_DISPATCH,
        [
            log_batch(
                "claude_code.api_request",
                {
                    "input_tokens": 1_000,
                    "output_tokens": CLAUDE_OUTPUT,
                    "cache_read_tokens": 500,
                    "cache_creation_tokens": 250,
                    "model": "opus",
                },
                dispatch_id=CLAUDE_DISPATCH,
                lane="claude-native",
            )
        ],
    )
    # Codex: a histogram metric with a token_type attribute, ending mid-JSON.
    write_export(
        export_dir,
        CODEX_DISPATCH,
        [
            histogram_metric_batch(
                "codex.turn.token_usage",
                [({"token_type": "output"}, float(CODEX_OUTPUT))],
                dispatch_id=CODEX_DISPATCH,
                lane="codex",
            ),
            histogram_metric_batch(
                "codex.turn.token_usage",
                [({"token_type": "input"}, 9_000.0)],
                dispatch_id=CODEX_DISPATCH,
                lane="codex",
            ),
        ],
        truncate='{"resourceMetrics": [{"resource": {"attr',
    )
    # z.ai: the `claude` binary's own token metric, present but uncalibrated.
    write_export(
        export_dir,
        ZAI_DISPATCH,
        [
            sum_metric_batch(
                "claude_code.token.usage",
                [
                    ({"type": "input"}, 2_000.0),
                    ({"type": "output"}, 4_000.0),
                ],
                dispatch_id=ZAI_DISPATCH,
                lane="zai",
            )
        ],
    )
    # BARE: no export file at all.

    # The status-line spool: one session spanning two months — with its July render
    # in a rolled generation, so the generation seam and the period boundary visibly
    # disagree — one session whose payload carries the window gauges alone, one
    # pre-#488 bare line, one render with no session id, and one truncated line. The
    # cost counters are cumulative the way the real payload's are; the window gauges
    # fall and rise the way the live ones measurably do, so a reader that mistakes
    # one for a counter is caught by the tests below, not flattered.
    spool = tmp_path / "quota" / "statusline.jsonl"
    write_render(
        spool.parent / "statusline.jsonl.1",
        "2026-07-31T23:00:00+00:00",
        HUMAN_SESSION,
        cost_usd=1.0,
        duration_ms=100_000,
        lines_added=50,
        lines_removed=10,
        window_output_tokens=5_000,
        window_input_tokens=90_000,
    )
    write_render(
        spool,
        "2026-08-01T01:00:00+00:00",
        HUMAN_SESSION,
        cost_usd=2.0,
        duration_ms=200_000,
        lines_added=80,
        lines_removed=20,
        window_output_tokens=6_000,
        window_input_tokens=60_000,
    )
    write_render(
        spool,
        "2026-08-05T12:00:00+00:00",
        HUMAN_SESSION,
        cost_usd=3.0,
        duration_ms=300_000,
        lines_added=120,
        lines_removed=30,
        window_output_tokens=4_000,
        window_input_tokens=80_000,
    )
    write_render(
        spool,
        "2026-08-05T13:00:00+00:00",
        BRIEF_SESSION,
        cost_usd=0.5,
        window_output_tokens=500,
        window_input_tokens=9_000,
    )
    # Append, never replace: the three lines above are already in the file. A bare
    # pre-#488 line (untimestamped), an envelope with no session id, and a truncated
    # line — one of each absence the reader must count rather than swallow.
    with spool.open("a", encoding="utf-8") as handle:
        handle.write(
            '{"session_id":"s-pre-488","cost":{"total_cost_usd":0.4}}\n'
            '{"ts":"2026-08-05T14:00:00+00:00","payload":{"cost":{"total_cost_usd":0.1}}}\n'
            '{"ts":"2026-08-05T15:00:00+00:0'
        )

    for issue, hour, name in (
        (LANDED_ONE_HOUR, 13, "c.txt"),
        (LANDED_TWO_HOURS, 14, "d.txt"),
        (LANDED_THREE_HOURS, 15, "e.txt"),
    ):
        (repo / name).write_text(name, encoding="utf-8")
        run_git("add", ".", cwd=repo)
        run_git(
            "commit",
            "-qm",
            f"feat: flow {name}\n\nrefs #{issue}",
            cwd=repo,
            at=f"2026-08-05T{hour}:00:00+00:00",
        )
    (repo / "b.txt").write_text("two", encoding="utf-8")
    run_git("add", ".", cwd=repo)
    run_git("commit", "-qm", f"feat: the landing\n\nrefs #{ISSUE}", cwd=repo, at=AFTER_PLANNED)
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
    landed_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # Every staged dispatch armed from the base its landing must descend from.
    for name in dispatch_root.iterdir():
        plan_path = name / "dispatch.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["base_sha"] = base
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

    # The queue surface's own state (#492): two samples of the sampler's
    # journal, staged in the shape `queue_depth.sample` writes — a counted
    # empty ready queue in both, and a landing queue that went from one
    # waiting item to none, so the view's newest-sample query has a change to
    # find. One truncated line sits at the end: the reader counts it as
    # malformed and loads the rest, the stage reader's line one family over.
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    with (queue_dir / attribute_registry.QUEUE_DEPTH_JOURNAL).open("w", encoding="utf-8") as handle:
        samples: list[tuple[float, str, str, int | None, str, float | None]] = [
            (1_000.0, "ready_work", "counted", 0, "none", None),
            (1_000.0, "landing", "counted", 1, "unrecorded", None),
            (2_000.0, "ready_work", "counted", 0, "none", None),
            (2_000.0, "landing", "counted", 0, "none", None),
            (2_000.0, "reviewer", "unreadable", None, "unrecorded", None),
        ]
        for at, queue, state, count, oldest, age in samples:
            attributes: dict[str, object] = {
                "cti.queue.depth.queue": queue,
                "cti.queue.depth.state": state,
                "cti.queue.depth.oldest": oldest,
            }
            if count is not None:
                attributes["cti.queue.depth.count"] = count
            if age is not None:
                attributes["cti.queue.depth.oldest_age_s"] = age
            handle.write(
                json.dumps(
                    {
                        "event": attribute_registry.QUEUE_DEPTH_EVENT,
                        "at": at,
                        "attributes": attributes,
                        "resource": {"service.name": "test"},
                        "exported": False,
                        "export_detail": "test",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        handle.write('{"event": "cti.queue.depth", "at": 3_0')

    return World(
        dispatch_root,
        export_dir,
        review_root,
        spool,
        tmp_path / "store",
        repo,
        base,
        landed_sha,
        queue_dir,
    )


def rebuild_world(world: World) -> dict[str, Any]:
    """Rebuild the staged world's store and return the document."""
    return observatory.rebuild(
        world.dispatch_root,
        world.export_dir,
        world.review_root,
        world.spool,
        world.repo,
        world.store_dir,
        world.queue_dir,
    )


def summary_check_args(world: World, *, export_dir: Path | None = None) -> list[str]:
    """Build the CLI paths for the read-only committed-summary check."""
    return [
        "check",
        "--dispatch-root",
        str(world.dispatch_root),
        "--export-dir",
        str(world.export_dir if export_dir is None else export_dir),
        "--review-root",
        str(world.review_root),
        "--queue-dir",
        str(world.queue_dir),
        "--spool",
        str(world.spool),
        "--repo",
        str(world.repo),
    ]


def cost_row(store: dict[str, Any], issue: int, lane: str) -> dict[str, Any]:
    """Return one (issue, lane) cost row from the store."""
    return next(row for row in store["issue_cost"] if row["issue"] == issue and row["lane"] == lane)


def work_item(store: dict[str, Any], issue: int) -> dict[str, Any]:
    """Return one issue's work-item row from the store."""
    return next(row for row in store["work_items"] if row["issue"] == issue)


def cookbook_blocks() -> list[str]:
    """Every SQL block the shipped cookbook carries, in document order."""
    cookbook = (REPO / "docs" / "observatory" / "cookbook.md").read_text(encoding="utf-8")
    return re.findall(r"```sql\n(.*?)```", cookbook, flags=re.DOTALL)


def summary_row(store: dict[str, Any], issue: int) -> dict[str, Any]:
    """Return one landed-issue summary row from the staged store."""
    return next(row for row in store["issue_summary"] if row["issue"] == issue)


def test_landed_summary_is_generated_from_store_and_excludes_unlanded_work(world: World) -> None:
    store = rebuild_world(world)
    path = world.repo / observatory.SUMMARY_PATH
    assert path.read_text(encoding="utf-8") == observatory.render_summary(store)
    assert path.read_text(encoding="utf-8").startswith(observatory.SUMMARY_HEADER + "\n\n")
    assert "A dispatched implementer repairs a clean stale projection" in observatory.SUMMARY_HEADER
    assert "An uncommitted hand edit stays red" in observatory.SUMMARY_HEADER
    assert "a committed hand edit is indistinguishable from" in observatory.SUMMARY_HEADER
    assert "summary_mismatch" in observatory.SUMMARY_HEADER
    data_rows = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("|") and not line.startswith("| ---")
    ]
    assert len(data_rows) == len(store["issue_summary"]) + 1  # header plus one row per landing
    assert {row["issue"] for row in store["issue_summary"]} == {
        LANDED_ONE_HOUR,
        LANDED_TWO_HOURS,
        LANDED_THREE_HOURS,
        ISSUE,
    }
    assert ABANDONED_ISSUE not in {row["issue"] for row in store["issue_summary"]}
    assert "total" not in data_rows[0].lower()
    assert "combined" not in data_rows[0].lower()


def test_landed_summary_uses_commit_time_when_sha_order_disagrees(tmp_path: Path) -> None:
    """A later commit with a smaller SHA must win the issue's summary row."""
    repo = tmp_path / "ordering-repo"
    repo.mkdir()
    run_git("init", "-q", "-b", "main", cwd=repo)
    run_git("config", "user.email", "t@example.com", cwd=repo)
    run_git("config", "user.name", "T", cwd=repo)
    (repo / "base.txt").write_text("base", encoding="utf-8")
    run_git("add", "base.txt", cwd=repo)
    run_git("commit", "-qm", "chore: the base", cwd=repo, at="2026-08-05T00:00:00+00:00")

    candidates: list[str] = []
    older_sha: str | None = None
    newer_sha: str | None = None
    for index in range(64):
        name = f"candidate-{index}.txt"
        (repo / name).write_text(name, encoding="utf-8")
        run_git("add", name, cwd=repo)
        run_git(
            "commit",
            "-qm",
            f"feat: issue ordering {index}\n\nrefs #548",
            cwd=repo,
            at=f"2026-08-05T{index // 60:02}:{index % 60:02}:00+00:00",
        )
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 — fixed Git executable and tmp_path repo
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        prior = next((candidate for candidate in candidates if candidate > sha), None)
        if prior is not None:
            older_sha, newer_sha = prior, sha
            break
        candidates.append(sha)

    assert older_sha is not None, "staged commit sequence found no older candidate"
    assert newer_sha is not None, "staged commit sequence found no newer candidate"
    assert older_sha > newer_sha  # Lexical order picks older commit, by construction.
    store: dict[str, Any] = {
        "inputs": {"repo": str(repo)},
        "dispatches": [
            {"issue": 548, "lane": "claude-native"},
            {"issue": 548, "lane": "zai"},
        ],
        "issue_cost": [
            {
                "issue": 548,
                "lane": "claude-native",
                "landed_sha": older_sha,
                "cost": None,
                "meter": "test-meter",
                "cost_reason": "test",
            },
            {
                "issue": 548,
                "lane": "zai",
                "landed_sha": newer_sha,
                "cost": None,
                "meter": "test-meter",
                "cost_reason": "test",
            },
        ],
        "issue_rework": [],
        "work_items": [{"issue": 548, "state": "landed"}],
    }

    summary = observatory.issue_summary_rows(store, repo)
    assert summary[0]["landed_sha"] == newer_sha
    assert any(
        line.startswith(f"|548|{newer_sha}|")
        for line in observatory.render_summary({**store, "issue_summary": summary}).splitlines()
    )


def test_summary_preserves_counted_zero_unknown_and_not_involved(world: World) -> None:
    store = rebuild_world(world)
    one = summary_row(store, LANDED_ONE_HOUR)
    assert one["costs"]["claude-native"]["state"] == observatory.SUMMARY_COST_UNRECORDED
    assert one["costs"]["claude-native"]["rendering"] == "absent"
    assert one["costs"]["claude-native"]["cost_reason"]
    assert one["costs"]["codex"]["state"] == observatory.SUMMARY_COST_NONE
    assert one["costs"]["codex"]["rendering"] == "not_involved"
    assert one["costs"]["codex"]["cost_reason"]
    rendered = observatory.render_summary(store)
    assert "|U|U|" in rendered
    assert "|A|N|N|" in rendered
    assert "|R|" in rendered
    assert "C<number>" in rendered
    assert observatory.UNCALIBRATED_REASON not in rendered
    assert observatory.NO_TELEMETRY_REASON not in rendered

    observatory_cost = next(
        row
        for row in store["issue_cost"]
        if row["issue"] == LANDED_ONE_HOUR and row["lane"] == "claude-native"
    )
    observatory_cost["cost"] = 0.0
    observatory_cost["cost_reason"] = None
    store["issue_summary"] = observatory.issue_summary_rows(store)
    zero = summary_row(store, LANDED_ONE_HOUR)
    assert zero["costs"]["claude-native"]["state"] == observatory.SUMMARY_COST_COUNTED
    assert zero["costs"]["claude-native"]["cost"] == 0.0
    assert f"|{LANDED_ONE_HOUR}|" in observatory.render_summary(store)
    assert "|C0|N|N|" in observatory.render_summary(store)

    observatory_cost["cost"] = 2.15866132609487
    store["issue_summary"] = observatory.issue_summary_rows(store)
    rendered = observatory.render_summary(store)
    assert "|C2.15866|N|N|" in rendered
    assert "C2.15866132609487" not in rendered


@pytest.mark.parametrize("seat", [None, "implementer", "review"])
def test_an_uncommitted_hand_edit_to_the_summary_is_a_red_in_every_seat(
    world: World,
    seat: str | None,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebuild_world(world)
    run_git("add", str(observatory.SUMMARY_PATH), cwd=world.repo)
    run_git("commit", "-qm", "chore: generated summary", cwd=world.repo)
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=world.repo)
    path = world.repo / observatory.SUMMARY_PATH
    path.write_text(
        path.read_text(encoding="utf-8").replace("Generated by", "Hand edited", 1),
        encoding="utf-8",
    )
    if seat is None:
        monkeypatch.delenv("CTI_DISPATCH_ID", raising=False)
        monkeypatch.delenv("CTI_DISPATCH_SEAT", raising=False)
    else:
        monkeypatch.setenv("CTI_DISPATCH_ID", f"d-test-observatory-{seat}")
        monkeypatch.setenv("CTI_DISPATCH_SEAT", seat)

    code = observatory.main(summary_check_args(world))
    captured = capsys.readouterr()

    assert code == 1
    assert captured.out == ""
    assert "refused=summary_mismatch" in captured.err
    assert "Hand edited" in path.read_text(encoding="utf-8")


def test_a_committed_hand_edit_can_be_overwritten_by_implementer_repair(
    world: World,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed edit has no provenance bit that separates it from stale bytes."""
    expected = rebuild_world(world)
    path = world.repo / observatory.SUMMARY_PATH
    run_git("add", str(observatory.SUMMARY_PATH), cwd=world.repo)
    run_git("commit", "-qm", "chore: generated summary", cwd=world.repo)
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=world.repo)
    path.write_text(
        path.read_text(encoding="utf-8").replace("Generated by", "Hand edited", 1), encoding="utf-8"
    )
    run_git("add", str(observatory.SUMMARY_PATH), cwd=world.repo)
    run_git("commit", "-qm", "fix: edit generated summary", cwd=world.repo)
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=world.repo)
    monkeypatch.setenv("CTI_DISPATCH_ID", "d-test-observatory-committed-edit")
    monkeypatch.setenv("CTI_DISPATCH_SEAT", "implementer")

    code = observatory.main(summary_check_args(world))
    captured = capsys.readouterr()

    assert code == 0
    assert captured.err == ""
    assert "observatory_summary=regenerated state=working_tree" in captured.out
    assert path.read_text(encoding="utf-8") == observatory.render_summary(expected)


def test_check_reports_pass_for_a_readable_matching_summary(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    rebuild_world(world)
    code = observatory.main(summary_check_args(world))
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert captured.out == f"observatory_summary=ok path={world.repo / observatory.SUMMARY_PATH}\n"


def test_an_unreadable_source_stays_red_in_a_dispatched_implementer(
    world: World,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CTI_DISPATCH_ID", "d-test-observatory-skip")
    monkeypatch.setenv("CTI_DISPATCH_SEAT", "implementer")
    gone = world.export_dir.parent / "nowhere"
    code = observatory.main(summary_check_args(world, export_dir=gone))
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "refused=export_dir_unreadable" in captured.err


def test_an_unreadable_source_stays_red_outside_a_dispatched_implementer(
    world: World,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CTI_DISPATCH_ID", raising=False)
    monkeypatch.delenv("CTI_DISPATCH_SEAT", raising=False)
    gone = world.export_dir.parent / "nowhere"
    code = observatory.main(summary_check_args(world, export_dir=gone))
    captured = capsys.readouterr()
    assert code == 1
    assert "refused=export_dir_unreadable" in captured.err
    assert "observatory_summary=skipped" not in captured.out
    assert captured.out == ""


def test_a_dispatch_on_an_unlanded_issue_does_not_churn_the_summary_check(world: World) -> None:
    rebuild_world(world)
    stage_record(
        world.dispatch_root,
        "d-20260805-120000-boundary1",
        issue=BOUNDARY_IN_FLIGHT_ISSUE,
    )
    observatory.check_summary(
        world.dispatch_root,
        world.export_dir,
        world.review_root,
        world.spool,
        world.repo,
        world.queue_dir,
    )


def test_a_new_landing_makes_the_summary_check_red_until_regeneration(world: World) -> None:
    rebuild_world(world)
    stage_record(
        world.dispatch_root,
        "d-20260805-120000-boundary2",
        issue=BOUNDARY_LANDED_ISSUE,
        base_sha=world.base_sha,
    )
    (world.repo / "boundary.txt").write_text("landed", encoding="utf-8")
    run_git("add", "boundary.txt", cwd=world.repo)
    run_git(
        "commit",
        "-qm",
        f"feat: boundary landing\n\nrefs #{BOUNDARY_LANDED_ISSUE}",
        cwd=world.repo,
        at="2026-08-06T12:00:00+00:00",
    )
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=world.repo)
    with pytest.raises(observatory.SummaryMismatchError, match="summary_mismatch"):
        observatory.check_summary(
            world.dispatch_root,
            world.export_dir,
            world.review_root,
            world.spool,
            world.repo,
            world.queue_dir,
        )


@pytest.mark.parametrize("seat", [None, "review", "implementer"])
def test_a_clean_stale_summary_is_repaired_only_by_an_implementer(
    world: World,
    seat: str | None,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebuild_world(world)
    run_git("add", str(observatory.SUMMARY_PATH), cwd=world.repo)
    run_git("commit", "-qm", "chore: generated summary", cwd=world.repo)
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=world.repo)
    stage_record(
        world.dispatch_root,
        "d-20260805-120000-boundary3",
        issue=BOUNDARY_LANDED_ISSUE,
        base_sha=world.base_sha,
    )
    (world.repo / "boundary.txt").write_text("landed", encoding="utf-8")
    run_git("add", "boundary.txt", cwd=world.repo)
    run_git(
        "commit",
        "-qm",
        f"feat: boundary landing\n\nrefs #{BOUNDARY_LANDED_ISSUE}",
        cwd=world.repo,
        at="2026-08-06T12:00:00+00:00",
    )
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=world.repo)
    if seat is None:
        monkeypatch.delenv("CTI_DISPATCH_ID", raising=False)
        monkeypatch.delenv("CTI_DISPATCH_SEAT", raising=False)
    else:
        monkeypatch.setenv("CTI_DISPATCH_ID", f"d-test-observatory-{seat}")
        monkeypatch.setenv("CTI_DISPATCH_SEAT", seat)

    code = observatory.main(summary_check_args(world))
    captured = capsys.readouterr()

    if seat == "implementer":
        assert code == 0
        assert captured.err == ""
        assert "observatory_summary=regenerated state=working_tree" in captured.out
        assert f"path={world.repo / observatory.SUMMARY_PATH}" in captured.out
        assert f"|{BOUNDARY_LANDED_ISSUE}|" in (world.repo / observatory.SUMMARY_PATH).read_text(
            encoding="utf-8"
        )
    else:
        assert code == 1
        assert captured.out == ""
        assert "refused=summary_mismatch" in captured.err


def test_the_landed_summary_cookbook_query_runs_against_the_shipped_store(world: World) -> None:
    rebuild_world(world)
    block = next(block for block in cookbook_blocks() if "FROM issue_summary" in block)
    rows = observatory.query(world.store_dir, block.strip().rstrip(";"))
    assert {row[0] for row in rows} == {
        ISSUE,
        LANDED_ONE_HOUR,
        LANDED_TWO_HOURS,
        LANDED_THREE_HOURS,
    }


# ---------------------------------------------------------------- both encodings read


def test_both_spend_encodings_appear_and_neither_lane_books_zero(world: World) -> None:
    store = rebuild_world(world)
    claude = cost_row(store, ISSUE, "claude-native")
    codex = cost_row(store, ISSUE, "codex")
    assert claude["spend_encoding"] == "log_records"
    assert claude["output_tokens"] == CLAUDE_OUTPUT
    assert codex["spend_encoding"] == "metric"
    assert codex["output_tokens"] == CODEX_OUTPUT
    assert codex["input_tokens"] == 9_000


def test_zai_spend_reads_the_metric_the_claude_binary_emits(world: World) -> None:
    store = rebuild_world(world)
    zai = cost_row(store, ISSUE, "zai")
    assert zai["spend_encoding"] == "metric"
    assert (zai["input_tokens"], zai["output_tokens"]) == (2_000, 4_000)


def test_claude_cost_is_window_points_from_the_ledger_calibration(world: World) -> None:
    store = rebuild_world(world)
    claude = cost_row(store, ISSUE, "claude-native")
    assert claude["meter"] == "claude_five_hour_window_points"
    assert claude["calibration_id"] == ledger.CALIBRATION_ID
    assert claude["cost"] == CLAUDE_OUTPUT / ledger.CLAUDE_TOKENS_PER_POINT["five_hour"]


# ------------------------------------------------------------------- never summed


def _walk(node: object) -> list[tuple[str, object]]:
    """Collect every key-value pair in a nested document, at any depth."""
    found: list[tuple[str, object]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append((str(key), value))
            found.extend(_walk(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk(item))
    return found


def test_no_summed_across_lanes_column_exists_anywhere(world: World) -> None:
    store = rebuild_world(world)
    banned = re.compile(r"(?i)total|summed|combined|grand|all.?lane|cross.?lane")
    for key, _ in _walk(store):
        assert not banned.search(str(key)), f"cross-lane total column: {key}"
    lanes_by_issue: dict[int, set[str]] = {}
    for row in store["dispatches"]:
        if row["issue"] is not None and row["lane"] is not None:
            lanes_by_issue.setdefault(row["issue"], set()).add(row["lane"])
    keys = set()
    for row in store["issue_cost"]:
        assert row["lane"] in lanes_by_issue[row["issue"]]
        keys.add((row["issue"], row["lane"]))
    assert len(keys) == len(store["issue_cost"]), "one row per (issue, lane), never a merged one"


# ---------------------------------------------------------------- never cheap


def test_a_lane_without_a_calibration_renders_uncalibrated(world: World) -> None:
    store = rebuild_world(world)
    for lane in ("zai", "codex"):
        row = cost_row(store, ISSUE, lane)
        assert row["cost"] is None
        assert row["cost"] != 0
        assert "uncalibrated" in row["cost_reason"]
        assert row["meter"] == "uncalibrated_provider_tokens"
        assert row["calibration_id"] is None


def test_a_dispatch_with_no_telemetry_is_a_row_with_a_reason(world: World) -> None:
    store = rebuild_world(world)
    row = next(row for row in store["dispatches"] if row["dispatch_id"] == BARE_DISPATCH)
    assert row["telemetry_source"] == "absent"
    assert row["telemetry_path_reason"]
    assert row["spend_encoding"] is None
    assert row["output_tokens"] is None
    assert row["output_tokens_reason"]
    assert cost_row(store, OTHER_ISSUE, "claude-native")["spend_encoding"] is None


def test_every_null_in_the_store_carries_a_reason(world: World) -> None:
    store = rebuild_world(world)

    def unreasoned(node: object) -> list[str]:
        """Flag a column whose null and reason sibling disagree, in either direction.

        A column is null exactly when its `<column>_reason` is non-null — so a null
        never appears without its why, and a reason never dresses a number.
        """
        bad: list[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                name = str(key)
                if not name.endswith("_reason") and (value is None) != bool(
                    node.get(f"{name}_reason")
                ):
                    bad.append(name)
            for value in node.values():
                bad.extend(unreasoned(value))
        elif isinstance(node, list):
            for item in node:
                bad.extend(unreasoned(item))
        return bad

    assert not unreasoned(store), f"nulls without reasons: {unreasoned(store)}"


# ------------------------------------------------------------ the pruned-source read


def test_a_pruned_export_falls_back_to_the_row_and_keeps_its_numbers(world: World) -> None:
    prune_export(world, ZAI_DISPATCH, {"input_tokens": 1_500, "output_tokens": 3_500})
    store = rebuild_world(world)
    row = next(row for row in store["dispatches"] if row["dispatch_id"] == ZAI_DISPATCH)
    assert row["telemetry_source"] == "ledger_row"
    assert row["telemetry_path"] is None
    assert "prune" in str(row["telemetry_path_reason"])
    assert row["spend_encoding"] == "metric"
    assert (row["input_tokens"], row["output_tokens"]) == (1_500, 3_500)
    assert cost_row(store, ISSUE, "zai")["output_tokens"] == 3_500


def test_a_rebuild_after_a_prune_does_not_look_like_a_rebuild_before_one(world: World) -> None:
    before = rebuild_world(world)
    before_line = next(
        line
        for line in observatory.summary_lines(before, world.store_dir)
        if line.startswith("coverage")
    )
    prune_export(world, ZAI_DISPATCH, {"input_tokens": 1_500, "output_tokens": 3_500})
    after = rebuild_world(world)
    after_line = next(
        line
        for line in observatory.summary_lines(after, world.store_dir)
        if line.startswith("coverage")
    )
    assert before_line != after_line
    assert "from_ledger_rows=0" in before_line
    assert "from_ledger_rows=1" in after_line
    assert after["coverage"]["dispatches_without_telemetry"] == [
        BARE_DISPATCH,
        FLOW_A,
        FLOW_B,
        FLOW_C,
        FLOW_D,
        FLOW_E,
        FLOW_F,
        FLOW_G,
        FLOW_H,
    ]


def test_a_pruned_log_record_dispatch_is_visibly_absent_not_zero(world: World) -> None:
    # The Claude dispatch's spend lives only in log records; the materialised row
    # never carried it, so the day after a prune nothing surviving can answer.
    prune_export(
        world,
        CLAUDE_DISPATCH,
        {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_creation_tokens": 0},
    )
    store = rebuild_world(world)
    row = next(row for row in store["dispatches"] if row["dispatch_id"] == CLAUDE_DISPATCH)
    assert row["telemetry_source"] == "ledger_row"
    assert row["spend_encoding"] is None
    assert row["output_tokens"] is None
    assert "not derivable" in str(row["output_tokens_reason"])
    cost = cost_row(store, ISSUE, "claude-native")
    assert cost["output_tokens"] is None
    assert "not derivable" in str(cost["output_tokens_reason"])
    assert cost["cost"] is None
    assert "not derivable" in str(cost["cost_reason"])


def test_an_unparseable_ledger_row_is_a_row_with_a_reason(world: World) -> None:
    prune_export(world, ZAI_DISPATCH, {})
    write_ledger_row(world.dispatch_root / ZAI_DISPATCH, {}, body="{not json")
    store = rebuild_world(world)
    row = next(row for row in store["dispatches"] if row["dispatch_id"] == ZAI_DISPATCH)
    assert row["telemetry_source"] == "ledger_row"
    assert row["spend_encoding"] is None
    assert "would not parse" in str(row["spend_encoding_reason"])


def test_a_pruned_dispatch_s_typing_is_derived_from_the_row_it_left(world: World) -> None:
    # The records the typing would have read are gone; the row's own `end_state` block
    # — which every materialised row carries — is what answers, so the abandoned
    # typing survives its export's prune rather than degrading to a null.
    write_ledger_row(
        world.dispatch_root / FLOW_D,
        {},
        end_state={
            "class": "provider_refused",
            "reason": "the provider refused the request",
            "evidence": [],
        },
    )
    store = rebuild_world(world)
    row = next(row for row in store["dispatches"] if row["dispatch_id"] == FLOW_D)
    assert row["telemetry_source"] == "ledger_row"
    assert row["end_state_class"] == "provider_refused"
    assert row["gate_outcome"] == "not_a_result"
    assert work_item(store, ABANDONED_ISSUE)["state"] == "abandoned"
    # A row without the block is a null with its reason, never a guessed class.
    write_ledger_row(world.dispatch_root / FLOW_D, {}, end_state=None)
    store = rebuild_world(world)
    row = next(row for row in store["dispatches"] if row["dispatch_id"] == FLOW_D)
    assert row["end_state_class"] is None
    assert row["gate_outcome"] is None
    assert row["gate_outcome_reason"]


def test_an_absent_cost_renders_absent_and_an_uncalibrated_one_renders_uncalibrated(
    world: World,
) -> None:
    store = rebuild_world(world)
    lines = observatory.summary_lines(store, world.store_dir)
    # OTHER_ISSUE's bare dispatch: a calibrated meter whose spend is absent.
    assert any(
        "cost=absent" in line and "meter=claude_five_hour_window_points" in line
        for line in lines
        if f"issue={OTHER_ISSUE}" in line
    )
    # The z.ai row: a cost that exists as a concept for no calibration.
    assert any(
        "cost=uncalibrated" in line
        for line in lines
        if f"issue={ISSUE}" in line and "lane=zai" in line
    )


# ------------------------------------------------------------- malformed and coverage


def test_a_truncated_line_is_counted_named_and_survived(world: World) -> None:
    store = rebuild_world(world)
    # One truncated export line, one truncated spool line, one truncated
    # queue-depth line — the same discipline at each parse boundary, each named
    # for its own file.
    assert store["coverage"]["malformed_lines"] == 3
    assert store["malformed"] == [
        {"file": f"dispatch-{CODEX_DISPATCH}.jsonl", "lines": 1},
        {"file": "queue/queue-depths.jsonl", "lines": 1},
        {"file": "statusline.jsonl", "lines": 1},
    ]
    # The dispatch's spend still read, from the lines that did parse.
    assert cost_row(store, ISSUE, "codex")["output_tokens"] == CODEX_OUTPUT
    lines = observatory.summary_lines(store, world.store_dir)
    assert any("malformed_lines=3" in line for line in lines)
    assert any(f"file=dispatch-{CODEX_DISPATCH}.jsonl" in line for line in lines)
    assert any("file=statusline.jsonl" in line for line in lines)
    assert any("file=queue/queue-depths.jsonl" in line for line in lines)


def test_the_rebuild_states_its_own_coverage(world: World) -> None:
    store = rebuild_world(world)
    coverage = store["coverage"]
    assert coverage["dispatches"] == 12
    assert coverage["dispatches_with_telemetry"] == 3
    assert coverage["dispatches_with_spend"] == 3
    assert coverage["dispatches_without_telemetry"] == [
        BARE_DISPATCH,
        FLOW_A,
        FLOW_B,
        FLOW_C,
        FLOW_D,
        FLOW_E,
        FLOW_F,
        FLOW_G,
        FLOW_H,
    ]
    # The occupancy view's floor: eight dispatches attest no span — seven with no
    # result.json at all and the never-launched refusal, whose closeout carries no
    # start of the run's own — so any window's used minutes is computed over the
    # other four alone.
    assert coverage["dispatches_unbounded"] == [
        BARE_DISPATCH,
        CLAUDE_DISPATCH,
        CODEX_DISPATCH,
        FLOW_A,
        FLOW_B,
        FLOW_C,
        FLOW_F,
        ZAI_DISPATCH,
    ]
    assert coverage["issues"] == 9
    assert coverage["issues_with_landings"] == 4
    lines = observatory.summary_lines(store, world.store_dir)
    assert any(
        "dispatches=12" in line
        and "with_spend=3" in line
        and "unbounded=8" in line
        and "issues_with_landings=4" in line
        for line in lines
    )


def test_the_landed_sha_is_attributed_to_the_issue_that_landed(world: World) -> None:
    store = rebuild_world(world)
    assert cost_row(store, ISSUE, "claude-native")["landed_sha"] == world.landed_sha
    assert cost_row(store, OTHER_ISSUE, "claude-native")["landed"] is False
    assert cost_row(store, OTHER_ISSUE, "claude-native")["landed_sha_reason"]


# ------------------------------------------- the journal owns the landing (#563)

# The landing-preference tests' own issue, dispatches and instants: one issue, one
# implementer dispatch armed at PLANNED, and a repo whose commits land inside and
# outside the shapes the preference has to tell apart.
JOURNAL_ISSUE = 552
JOURNAL_DISPATCH = "d-20260805-120000-jour01"
JOURNAL_CO_AUTHOR = "d-20260805-120000-jour02"
GENUINE_AT = "2026-08-05T23:00:00+00:00"
REGENERATE_AT = "2026-08-05T23:30:00+00:00"


def _landing_world(tmp_path: Path) -> dict[str, Path]:
    """Every root the rebuild reads, present and empty where unused, over a real repo."""
    world = {
        "dispatch_root": tmp_path / "dispatches",
        "export_dir": tmp_path / "export",
        "review_root": tmp_path / "review",
        "spool": tmp_path / "spool" / "statusline.jsonl",
        "repo": tmp_path / "repo",
        "store_dir": tmp_path / "store",
    }
    for key in ("dispatch_root", "export_dir", "review_root"):
        world[key].mkdir(parents=True, exist_ok=True)
    world["spool"].parent.mkdir(parents=True, exist_ok=True)
    world["spool"].write_text("", encoding="utf-8")
    repo = world["repo"]
    repo.mkdir()
    run_git("init", "-q", "-b", "main", cwd=repo)
    run_git("config", "user.email", "t@example.com", cwd=repo)
    run_git("config", "user.name", "T", cwd=repo)
    (repo / "base.txt").write_text("base", encoding="utf-8")
    run_git("add", "base.txt", cwd=repo)
    run_git("commit", "-qm", "chore: the base", cwd=repo, at="2026-08-05T11:00:00+00:00")
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
    return world


def _head_of(repo: Path) -> str:
    """Return the staged repo's current commit."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607 — fixed Git executable and the staged repo
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _stage_landing(world: dict[str, Path], message: str, at: str) -> str:
    """Commit on the staged repo's main and move `origin/main` to it, as a push would."""
    repo = world["repo"]
    name = f"{time.time_ns()}.txt"
    (repo / name).write_text(name, encoding="utf-8")
    run_git("add", name, cwd=repo)
    run_git("commit", "-qm", message, cwd=repo, at=at)
    run_git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
    return _head_of(repo)


def write_landing_journal(review_root: Path, issue: int, produced: str) -> Path:
    """Lay down one landings-journal line, in the flat shape the recorder renders."""
    path = review_root / str(issue) / attribute_registry.LANDING_JOURNAL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "event": attribute_registry.LANDING_EVENT,
                "at": 1_800_000_000.0,
                "attributes": {
                    "cti.issue": issue,
                    "cti.relation.produced": f"commit:{produced}",
                    "cti.relation.author": f"dispatch:{JOURNAL_DISPATCH}",
                    "cti.relation.reviewer": f"dispatch:{JOURNAL_CO_AUTHOR}",
                },
                "resource": {"service.name": "arma-cti-landing"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _rebuild_landing_world(world: dict[str, Path]) -> dict[str, Any]:
    """Rebuild the landing world's store and return the document."""
    return observatory.rebuild(
        world["dispatch_root"],
        world["export_dir"],
        world["review_root"],
        world["spool"],
        world["repo"],
        world["store_dir"],
    )


def _armed_landing_world(tmp_path: Path) -> tuple[dict[str, Path], str]:
    """Return the landing world with its dispatch armed from the base a landing descends from."""
    world = _landing_world(tmp_path)
    base = _head_of(world["repo"])
    stage_record(world["dispatch_root"], JOURNAL_DISPATCH, issue=JOURNAL_ISSUE, base_sha=base)
    return world, base


def test_the_journal_s_produced_commit_owns_the_row_over_a_newer_referencing_commit(
    tmp_path: Path,
) -> None:
    # #552's shape exactly: the true landing carries no issue token at all, the
    # projection regenerate after it credits the issue with one, and the derivation
    # picked the regenerate — corrupting the row and growing lead_time_seconds with
    # every later mention. Where the journal names the produced commit, that commit
    # is the answer the projection reports, at every layer that renders it.
    world, _ = _armed_landing_world(tmp_path)
    genuine = _stage_landing(world, "fix(land): the work\n\nno issue token anywhere", GENUINE_AT)
    _stage_landing(world, "chore(observatory): regenerate\n\nrefs #552", REGENERATE_AT)
    write_landing_journal(world["review_root"], JOURNAL_ISSUE, genuine)
    store = _rebuild_landing_world(world)
    assert cost_row(store, JOURNAL_ISSUE, "claude-native")["landed_sha"] == genuine
    assert summary_row(store, JOURNAL_ISSUE)["landed_sha"] == genuine
    item = work_item(store, JOURNAL_ISSUE)
    assert item["state"] == "landed"
    assert item["clock_end"] == GENUINE_AT
    assert item["lead_time_seconds"] == 39_600  # PLANNED 12:00 to the 23:00 genuine landing


def test_a_journal_that_will_not_read_is_reported_not_fallen_back_from(tmp_path: Path) -> None:
    # The absent-or-undecidable rule this store keeps closing instances of: the git
    # derivation would land here — the refs commit is in the window — and a damaged
    # journal must not render as that healthy answer. The row says what happened to
    # the record instead.
    world, _ = _armed_landing_world(tmp_path)
    _stage_landing(world, "feat: the work\n\nrefs #552", GENUINE_AT)
    journal = world["review_root"] / str(JOURNAL_ISSUE) / attribute_registry.LANDING_JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text('{"event": "cti.landing.reviewed", "at": 1.0, "attri', encoding="utf-8")
    store = _rebuild_landing_world(world)
    row = cost_row(store, JOURNAL_ISSUE, "claude-native")
    assert row["landed"] is False
    assert row["landed_sha_reason"] == "the landings journal could not be read"


def test_a_journal_that_records_landings_but_names_no_commit_says_so(tmp_path: Path) -> None:
    # The pre-relation historical shape: the event parses, the issue reads, and no
    # produced relation exists. The journal cannot answer, and the derivation is not
    # quietly asked in its place.
    world, _ = _armed_landing_world(tmp_path)
    _stage_landing(world, "feat: the work\n\nrefs #552", GENUINE_AT)
    journal = world["review_root"] / str(JOURNAL_ISSUE) / attribute_registry.LANDING_JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        json.dumps(
            {
                "event": attribute_registry.LANDING_EVENT,
                "at": 1.0,
                "attributes": {"cti.issue": JOURNAL_ISSUE},
                "resource": {"service.name": "arma-cti-landing"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    store = _rebuild_landing_world(world)
    row = cost_row(store, JOURNAL_ISSUE, "claude-native")
    assert row["landed"] is False
    assert row["landed_sha_reason"] == observatory.NO_COMMIT_RELATION_REASON


def test_a_journal_naming_a_commit_absent_from_the_checkout_says_so(tmp_path: Path) -> None:
    world, _ = _armed_landing_world(tmp_path)
    write_landing_journal(world["review_root"], JOURNAL_ISSUE, "f" * 40)
    store = _rebuild_landing_world(world)
    row = cost_row(store, JOURNAL_ISSUE, "claude-native")
    assert row["landed"] is False
    assert row["landed_sha_reason"] == (
        f"the committer date for landed SHA {'f' * 40} could not be read from this checkout"
    )


def test_equal_committer_instants_break_the_tie_on_the_lexically_greatest_sha(
    tmp_path: Path,
) -> None:
    # #561's secondary key, staged at the one instant it exists for. The pair is
    # handed over smallest-first because `max` returns the first maximal element:
    # a mutant deleting the SHA from the key would answer the smaller commit, and
    # this test goes red rather than letting it survive.
    world = _landing_world(tmp_path)
    one = _stage_landing(world, "feat: one\n\nrefs #552", GENUINE_AT)
    two = _stage_landing(world, "feat: two\n\nrefs #552", GENUINE_AT)
    smaller, greater = sorted((one, two))
    sha, reason = observatory._newest_landed_sha(  # noqa: SLF001 — the picker is the unit; a staged store would test the fixture
        world["repo"], (smaller, greater)
    )
    assert (sha, reason) == (greater, None)


# --------------------------------------------------------------------- the flow view


def test_lead_time_percentiles_are_nearest_rank_pinned_where_linear_differs(
    world: World,
) -> None:
    rebuild_world(world)
    rows = observatory.query(world.store_dir, "SELECT * FROM flow_lead_time")
    # Nearest-rank on the landed sample [3600, 7200, 10800, 41400]: the p-th percentile
    # is the value at rank ceil(p*n/100), a member of the sample. Linear interpolation
    # on the same sample gives (9000, 13860, 27630, 36810) — it disagrees with the
    # pinned row at every percentile, so a change of method is a red, not a silent drift.
    assert rows == ((7200, 10800, 41400, 41400, 4),)


def test_the_lead_time_rendering_path_emits_percentiles_only(world: World) -> None:
    rebuild_world(world)
    with observatory.connect(world.store_dir) as connection:
        columns = tuple(
            str(row[1]) for row in connection.execute("PRAGMA table_info(flow_lead_time)")
        )
    # Exact-set equality: the headline slot holds percentiles and the sample size and
    # nothing else, so a mean cannot be added to it without this test going red.
    assert columns == ("p50_seconds", "p70_seconds", "p85_seconds", "p95_seconds", "items")


def test_the_clock_runs_from_the_first_dispatch_start_to_the_landing_commit(
    world: World,
) -> None:
    store = rebuild_world(world)
    item = work_item(store, ISSUE)
    assert item["state"] == "landed"
    assert item["clock_start"] == "2026-08-05T12:00:00+00:00"
    assert item["clock_end"] == "2026-08-05T23:30:00+00:00"
    assert item["lead_time_seconds"] == 41400
    short = work_item(store, LANDED_ONE_HOUR)
    assert (short["clock_start"], short["lead_time_seconds"]) == (
        "2026-08-05T12:00:00+00:00",
        3600,
    )


def test_work_items_partition_into_four_states(world: World) -> None:
    store = rebuild_world(world)
    states = {item["issue"]: item["state"] for item in store["work_items"]}
    assert states == {
        ISSUE: "landed",
        OTHER_ISSUE: "open",
        LANDED_ONE_HOUR: "landed",
        LANDED_TWO_HOURS: "landed",
        LANDED_THREE_HOURS: "landed",
        ABANDONED_ISSUE: "abandoned",
        STOPPED_ISSUE: "stopped",
        REFUSED_ISSUE: "stopped",
        REVIEW_DIED_ISSUE: "stopped",
    }
    # The partition is derived, never declared: the abandoned item's own dispatch row
    # carries the class that made it abandoned, and the stopped one carries not_landed.
    abandoned = next(row for row in store["dispatches"] if row["dispatch_id"] == FLOW_D)
    assert abandoned["end_state_class"] == "quota_exhausted"
    assert abandoned["gate_outcome"] == "not_a_result"
    stopped = next(row for row in store["dispatches"] if row["dispatch_id"] == FLOW_E)
    assert stopped["gate_outcome"] == "not_landed"
    lines = observatory.summary_lines(store, world.store_dir)
    assert "flow work_items=9 landed=4 open=1 abandoned=1 stopped=3" in lines


def test_work_that_never_started_is_not_abandoned_work(world: World) -> None:
    # #489's line, visible in the output: a refusal before the child launched carries
    # its failure class and still does not make the item abandoned, because work that
    # never started is not work that started and did not finish. The dispatch row says
    # `never_started`, and the item departs to the stopped residue.
    store = rebuild_world(world)
    row = next(row for row in store["dispatches"] if row["dispatch_id"] == FLOW_F)
    assert row["end_state_class"] == "infra_unavailable"
    assert row["gate_outcome"] == "never_started"
    assert work_item(store, REFUSED_ISSUE)["state"] == "stopped"
    assert store["coverage"]["work_items_abandoned"] == 1


def test_a_review_seat_death_never_brands_its_item_abandoned(world: World) -> None:
    # Round 2's #524 finding: three review dispatches ended in harness closeout
    # failures, every implementer dispatch on the issue succeeded, and the item read
    # `abandoned` — half the live abandoned count was an issue nobody abandoned. The
    # seat weighing holds the line: the review row keeps its own widened typing
    # (`untyped_harness_failure` → `not_a_result`), and the item reads from its
    # work-bearing dispatches alone, so it lands in the stopped residue.
    store = rebuild_world(world)
    review = next(row for row in store["dispatches"] if row["dispatch_id"] == FLOW_H)
    assert review["seat"] == "review"
    assert review["end_state_class"] == "untyped_harness_failure"
    assert review["gate_outcome"] == "not_a_result"
    item = work_item(store, REVIEW_DIED_ISSUE)
    assert item["state"] == "stopped"
    assert store["coverage"]["work_items_abandoned"] == 1


def test_a_seatless_or_unknown_seat_dispatch_still_brands_its_item() -> None:
    # The residual the docs state: `seat_shape` defaults a record with no seat — or a
    # seat no registry knows — to work-bearing, so a historical dispatch's
    # not-a-result still brands its item instead of falling silent, and the seat
    # weighing never eats the pre-seat corpus.
    for seat in (None, "a-seat-no-registry-knows"):
        assert (
            observatory._work_item_state(  # noqa: SLF001 — the seat-weighing reducer is the unit under test; staging a full rebuild for two row shapes would test the fixture instead
                [{"gate_outcome": "not_a_result", "seat": seat}]
            )
            == "abandoned"
        )


def test_abandoned_work_is_excluded_from_lead_time_and_counted_separately(
    world: World,
) -> None:
    store = rebuild_world(world)
    # Excluded: the distribution's denominator is the landed items alone, so the
    # abandoned issue never enters it however long it sat; counted: its own row and the
    # coverage block carry it as abandoned, not as a silently dropped item.
    assert work_item(store, ABANDONED_ISSUE)["lead_time_seconds"] is None
    assert store["coverage"]["work_items"] == 9
    assert store["coverage"]["work_items_abandoned"] == 1
    assert observatory.query(world.store_dir, "SELECT items FROM flow_lead_time") == ((4,),)


def test_throughput_is_an_exact_count_of_landed_items_over_a_window(world: World) -> None:
    rebuild_world(world)
    block = next(block for block in cookbook_blocks() if "strftime" in block)
    rows = observatory.query(world.store_dir, block.strip().rstrip(";"))
    assert rows == (("2026-08", 4),)


def test_an_open_item_s_age_reads_against_the_historical_band(world: World) -> None:
    rebuild_world(world)
    block = next(block for block in cookbook_blocks() if "age_seconds" in block)
    rows = observatory.query(world.store_dir, block.strip().rstrip(";"))
    # The staged as-of is one day after the open item's start, and its age sits above
    # the historical 85th percentile — the one leading indicator in the set.
    assert rows == ((OTHER_ISSUE, 86400, 7200, 10800, 41400),)


def test_the_clock_s_endpoints_pick_by_instant_never_by_iso_string(world: World) -> None:
    # `13:00+02:00` is 11:00Z — earlier than `12:00+00:00` as an instant and later
    # than it as a string. Both the pick and the subtraction must go by time: under a
    # string sort this item's clock would start at 12:00Z and read 3600.
    extra = stage_record(world.dispatch_root, "d-20260805-120000-flow06", issue=LANDED_ONE_HOUR)
    (extra / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": "d-20260805-120000-flow06",
                "status": "child_finished",
                "returncode": 0,
                "started_at": "2026-08-05T13:00:00+02:00",
                "ended_at": "2026-08-05T13:30:00+02:00",
            }
        ),
        encoding="utf-8",
    )
    store = rebuild_world(world)
    item = work_item(store, LANDED_ONE_HOUR)
    assert item["clock_start"] == "2026-08-05T13:00:00+02:00"
    assert item["lead_time_seconds"] == 7200


def test_an_empty_landed_sample_states_itself_as_zero_items(tmp_path: Path) -> None:
    # No dispatches at all is the empty store's own arrangement: the percentiles are
    # null — no member exists to read — while `items` is 0, an empty sample stated
    # rather than rendered as an unknown size.
    dispatch_root = tmp_path / "dispatches"
    export_dir = tmp_path / "export"
    review_root = tmp_path / "review"
    store_dir = tmp_path / "store"
    dispatch_root.mkdir()
    export_dir.mkdir()
    review_root.mkdir()
    observatory.rebuild(
        dispatch_root, export_dir, review_root, tmp_path / "spool.jsonl", tmp_path, store_dir
    )
    assert observatory.query(store_dir, "SELECT * FROM flow_lead_time") == (
        (None, None, None, None, 0),
    )


# ------------------------------------------------------------- determinism, refusal


def test_two_rebuilds_over_the_same_inputs_produce_identical_output(world: World) -> None:
    first = rebuild_world(world)
    first_bytes = (world.store_dir / "store.json").read_bytes()
    first_lines = observatory.summary_lines(first, world.store_dir)
    second = rebuild_world(world)
    assert (world.store_dir / "store.json").read_bytes() == first_bytes
    assert observatory.summary_lines(second, world.store_dir) == first_lines


def test_an_unreadable_source_directory_is_a_named_refusal(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    gone = world.export_dir.parent / "nowhere"
    code = observatory.main(
        [
            "--dispatch-root",
            str(world.dispatch_root),
            "--export-dir",
            str(gone),
            "--review-root",
            str(world.review_root),
            "--store-dir",
            str(world.store_dir),
            "--repo",
            str(world.repo),
        ]
    )
    assert code == 1
    printed = capsys.readouterr().err
    assert "refused=export_dir_unreadable" in printed
    assert f"path={gone}" in printed
    assert not (world.store_dir / "store.json").exists()


def test_an_unreadable_dispatch_root_refuses_by_name(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    code = observatory.main(
        [
            "--dispatch-root",
            str(world.dispatch_root / "nowhere"),
            "--export-dir",
            str(world.export_dir),
            "--review-root",
            str(world.review_root),
            "--store-dir",
            str(world.store_dir),
            "--repo",
            str(world.repo),
        ]
    )
    assert code == 1
    assert "refused=dispatch_root_unreadable" in capsys.readouterr().err
    assert not (world.store_dir / "store.json").exists()


def test_a_store_of_another_schema_refuses_by_name(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    # The shape a `/1` store actually has: no `work_items`, because that table is what
    # `/2` added. Reading it as SQL has to refuse by name — the schema it carries, the
    # schema needed — not die on the absent table's KeyError.
    rebuild_world(world)
    store_path = world.store_dir / "store.json"
    document = json.loads(store_path.read_text(encoding="utf-8"))
    del document["work_items"]
    document["schema"] = "cti.observatory/1"
    store_path.write_text(json.dumps(document), encoding="utf-8")
    code = observatory.main(
        ["query", "SELECT * FROM flow_lead_time", "--store-dir", str(world.store_dir)]
    )
    assert code == 1
    printed = capsys.readouterr().err
    assert "refused=schema_mismatch" in printed
    assert "found=cti.observatory/1" in printed
    assert f"needed={observatory.SCHEMA}" in printed


# --------------------------------------------------------------- the store's home


def test_the_store_lives_outside_every_worktree() -> None:
    expected_home = Path.home() / ".arma-cti" / "observatory"
    assert expected_home == observatory.DEFAULT_STORE_DIR
    assert not observatory.DEFAULT_STORE_DIR.is_relative_to(REPO)
    assert not observatory.DEFAULT_REVIEW_ROOT.is_relative_to(REPO)


# ------------------------------------------------------------------- the rework view


def test_the_ruled_key_ranks_only_implementer_seat_profiles(world: World) -> None:
    # A second seat on the same profile: the review seat dispatched the two-round
    # issue, so rework appeared on its row too — reported, contract-named, unranked.
    stage_record(
        world.dispatch_root,
        "d-20260805-120000-revw01",
        issue=LANDED_TWO_HOURS,
        seat="review",
    )
    store = rebuild_world(world)
    rows = {(row["profile"], row["seat"]): row for row in store["profile_rework"]}
    implementer = rows[("a-profile", "implementer")]
    # Rounds over the implementer-dispatched issues with loops: 0 + 1 + 2; landings:
    # the three ISSUE dispatches and FLOW_A/B/C each see their issue's commit.
    assert (implementer["rounds"], implementer["landings"]) == (3, 6)
    assert implementer["rounds_per_landing"] == 0.5
    assert implementer["ranked"] == 1
    assert implementer["rounds_per_landing_reason"] is None
    review = rows[("a-profile", "review")]
    assert review["rounds"] == 2
    assert review["landings"] == 0
    assert review["rounds_per_landing"] is None
    assert "by contract" in review["rounds_per_landing_reason"]
    assert review["ranked"] == 0
    # The ranked seat set is derived from the registries, never named: today exactly
    # the implementer seat both lands (`dispatch.SEATS`' column) and lands work rather
    # than a journal (`ledger`'s shape). A new seat joins by its registry rows or not
    # at all — this pin goes red the day one arrives, and that is its job.
    expected_ranked = frozenset({"implementer"})
    assert expected_ranked == observatory.RANKED_SEATS
    assert all(
        dispatch.SEATS[name].lands and ledger.seat_shape(name) == "work"
        for name in observatory.RANKED_SEATS
    )


def test_a_profile_with_no_landings_is_unranked_with_its_rounds_visible(world: World) -> None:
    write_loop(world.review_root, ROUNDY_ISSUE, 5)
    stage_record(
        world.dispatch_root, "d-20260805-120000-rndy01", issue=ROUNDY_ISSUE, profile="b-profile"
    )
    store = rebuild_world(world)
    row = next(
        row
        for row in store["profile_rework"]
        if row["profile"] == "b-profile" and row["seat"] == "implementer"
    )
    # Zero landings is an undefined rate, not zero rework and not an error: the rounds
    # stay readable and the key stays null with its reason, never a division.
    assert row["rounds"] == 5
    assert row["landings"] == 0
    assert row["rounds_per_landing"] is None
    assert "never rendered as a division" in row["rounds_per_landing_reason"]
    assert row["ranked"] == 0


def test_seats_that_land_nothing_by_contract_report_and_never_rank(world: World) -> None:
    for seat, dispatch_id in (
        ("review", "d-20260805-120000-revw02"),
        ("recon", "d-20260805-120000-recn01"),
    ):
        stage_record(world.dispatch_root, dispatch_id, issue=LANDED_TWO_HOURS, seat=seat)
    store = rebuild_world(world)
    for seat in ("review", "recon"):
        row = next(row for row in store["profile_rework"] if row["seat"] == seat)
        assert row["rounds"] == 2
        assert row["rounds_per_landing"] is None
        assert row["ranked"] == 0
        assert "by contract" in row["rounds_per_landing_reason"]
        # The contract reason and the no-landings reason are different facts; a reader
        # must be able to tell "cannot land" from "did not land".
        assert row["rounds_per_landing_reason"] != observatory.NO_LANDING_KEY_REASON


def test_a_record_with_no_seat_names_the_absence_not_a_python_repr(world: World) -> None:
    stage_record(
        world.dispatch_root, "d-20260805-120000-noseat1", issue=LANDED_TWO_HOURS, seat=None
    )
    store = rebuild_world(world)
    row = next(row for row in store["profile_rework"] if row["seat"] is None)
    assert row["rounds_per_landing"] is None
    assert row["ranked"] == 0
    # The reason renders the absence, never the Python repr of what is missing —
    # "the None seat is in no seat registry" reads as a seat named None.
    assert row["rounds_per_landing_reason"] == (
        "the unnamed seat is in no seat registry, so whether it may rank is not "
        "derivable — reported and never ranked"
    )


def test_dispatches_per_issue_is_reported_beside_the_key_and_explicitly_unranked(
    world: World,
) -> None:
    store = rebuild_world(world)
    rows = {row["issue"]: row for row in store["issue_rework"]}
    assert rows[LANDED_TWO_HOURS]["dispatches"] == 1
    assert rows[LANDED_TWO_HOURS]["review_rounds"] == 2
    # An issue with no loop carries null rounds and the reason that names it — an
    # absence is never zero rounds.
    assert rows[STOPPED_ISSUE]["review_rounds"] is None
    assert "no review loop" in rows[STOPPED_ISSUE]["review_rounds_reason"]
    for row in rows.values():
        assert row["ranked"] == 0
        assert "never strata" in row["measures"]


def test_the_rework_summary_line_states_its_spread_and_its_estimate(world: World) -> None:
    store = rebuild_world(world)
    lines = observatory.summary_lines(store, world.store_dir)
    # One ranked profile holding one key value: the key does not vary, and the line
    # says so rather than presenting an order over near-identical values. The
    # sample-limit marker carries the ADR's own account of its figures.
    assert (
        "rework ranked_seats=implementer loops=3 round_zero=1 ranked_profiles=1 "
        "key_varies=no measures=description sample_limit=estimate_not_measurement" in lines
    )
    # A second ranked profile with a different key — one landing over the one-round
    # issue — makes the key vary, and the line says that too.
    stage_record(
        world.dispatch_root,
        "d-20260805-120000-vary01",
        issue=LANDED_ONE_HOUR,
        profile="c-profile",
        base_sha=world.base_sha,
    )
    store = rebuild_world(world)
    lines = observatory.summary_lines(store, world.store_dir)
    assert (
        "rework ranked_seats=implementer loops=3 round_zero=1 ranked_profiles=2 "
        "key_varies=yes measures=description sample_limit=estimate_not_measurement" in lines
    )


# ------------------------------------------------------------- the stage view (#490)


def arrival_line(stage: str, status: str, *, issue: int) -> str:
    """One stage journal line exactly as the recorder's emission journalled it."""
    return (
        json.dumps(
            {
                "event": "cti.stage.transition",
                "at": 1_800_000_000.0,
                "attributes": {
                    "cti.stage.name": stage,
                    "cti.stage.first_pass": status,
                    "cti.issue": issue,
                },
                "resource": {"service.name": "arma-cti-stage"},
                "exported": False,
                "export_detail": "unreachable:ConnectionRefusedError",
            },
            sort_keys=True,
        )
        + "\n"
    )


def test_first_pass_yield_per_stage_is_a_grouping_over_the_record(world: World) -> None:
    """No inference: the arrivals' own statuses are the whole of the derivation."""
    one = world.review_root / "501" / attribute_registry.STAGE_JOURNAL
    two = world.review_root / "502" / attribute_registry.STAGE_JOURNAL
    one.parent.mkdir(parents=True)
    two.parent.mkdir(parents=True)
    # Two items through brief: one first-time, one after rework — yield two thirds.
    # Two through implementation: one first-time, one undetermined — the undetermined
    # sits beside the yield, never inside its denominator.
    one.write_text(
        arrival_line("brief", "first_time", issue=501)
        + arrival_line("implementation", "first_time", issue=501),
        encoding="utf-8",
    )
    two.write_text(
        arrival_line("brief", "first_time", issue=502)
        + arrival_line("brief", "after_rework", issue=502)
        + arrival_line("implementation", "first_time", issue=502)
        + arrival_line("implementation", "undetermined", issue=502),
        encoding="utf-8",
    )
    store = rebuild_world(world)
    by_stage = {row["stage"]: row for row in store["stage_first_pass"]}
    assert set(by_stage) == set(attribute_registry.STAGES), "every stage states itself"
    assert (by_stage["brief"]["arrivals"], by_stage["brief"]["first_time"]) == (3, 2)
    assert by_stage["brief"]["first_pass_yield"] == 2 / 3
    assert by_stage["implementation"]["undetermined"] == 1
    assert by_stage["implementation"]["first_pass_yield"] == 1.0, (
        "the undetermined arrival is not in the denominator"
    )
    assert by_stage["land"]["arrivals"] == 0
    assert by_stage["land"]["first_pass_yield"] is None
    assert by_stage["land"]["first_pass_yield_reason"] == observatory.NO_DETERMINED_ARRIVALS_REASON
    assert store["coverage"]["stage_arrivals_undetermined"] == 1
    # The stage summary line carries counts and the boundary's own name, never a yield.
    assert (
        "stages journals=2 arrivals=6 undetermined=1 history=journalled_only"
        in observatory.summary_lines(store, world.store_dir)
    )


def test_a_damaged_journal_line_is_malformed_never_bucketed_undetermined(world: World) -> None:
    """Damage to the record and an undeterminable status are different facts."""
    damaged = world.review_root / "503" / attribute_registry.STAGE_JOURNAL
    damaged.parent.mkdir(parents=True)
    damaged.write_text(
        arrival_line("brief", "first_time", issue=503)
        + arrival_line("brief", "probably", issue=503)
        + "{not json\n",
        encoding="utf-8",
    )
    store = rebuild_world(world)
    by_stage = {row["stage"]: row for row in store["stage_first_pass"]}
    assert by_stage["brief"]["arrivals"] == 1, "the damaged lines counted as nothing"
    assert {"file": "503/stages.jsonl", "lines": 2} in store["malformed"]


# ---------------------------------------------------------------- the queue-depth view


def test_queue_depth_rows_load_with_their_absences_as_nulls(world: World) -> None:
    """Zero, unread and unknown stay three different rows through the rebuild."""
    store = rebuild_world(world)
    by_key = {(row["sampled_at"], row["queue"]): row for row in store["queue_depth"]}
    empty = by_key[(2_000.0, "ready_work")]
    assert (empty["state"], empty["count"], empty["oldest"], empty["oldest_age_s"]) == (
        "counted",
        0,
        "none",
        None,
    )
    unreadable = by_key[(2_000.0, "reviewer")]
    assert (unreadable["state"], unreadable["count"]) == ("unreadable", None)
    assert store["coverage"]["queue_depth_samples"] == 5
    assert store["coverage"]["queue_depth_queues"] == 3
    assert store["coverage"]["queue_depth_samples_uncounted"] == 1
    assert store["coverage"]["queue_depth_last_at"] == 2_000.0
    # The staged truncated line is counted as malformed, and its siblings load.
    assert {"file": "queue/queue-depths.jsonl", "lines": 1} in store["malformed"]
    # The line's last term states the one queue definition a reader has misread
    # without it: `human_ruling` counts the open above-Low set of running loops,
    # never every open finding (#554).
    assert (
        "queue_depth samples=5 queues=3 uncounted=1 last=2000.0 "
        "human_ruling_scope=open_above_low_of_running_loops"
    ) in observatory.summary_lines(store, world.store_dir)


def test_an_absent_sampler_journal_is_zero_rows_never_a_refusal(world: World) -> None:
    """A rebuild before the sampler ever ran renders no samples, not a partial store."""
    (world.queue_dir / attribute_registry.QUEUE_DEPTH_JOURNAL).unlink()
    store = rebuild_world(world)
    assert store["queue_depth"] == []
    assert store["coverage"]["queue_depth_samples"] == 0
    assert store["coverage"]["queue_depth_last_at"] is None
    assert not any(entry["file"] == "queue/queue-depths.jsonl" for entry in store["malformed"])


def test_an_unreadable_sampler_journal_is_named_malformed_not_never_sampled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    path = queue_root / attribute_registry.QUEUE_DEPTH_JOURNAL
    path.write_text("{}\n", encoding="utf-8")
    real_read_text = Path.read_text

    def unreadable(
        target: Path,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        if target == path:
            raise OSError
        return real_read_text(target, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "read_text", unreadable)
    rows, malformed = observatory.read_queue_depths(queue_root)
    assert rows == []
    assert malformed == {"queue/queue-depths.jsonl": 1}


def test_a_queue_depth_reader_carries_a_candidate_refusal_reason(tmp_path: Path) -> None:
    queue_root = tmp_path / "queue"
    queue_root.mkdir()
    path = queue_root / attribute_registry.QUEUE_DEPTH_JOURNAL
    path.write_text(
        json.dumps(
            {
                "event": attribute_registry.QUEUE_DEPTH_EVENT,
                "at": 2_000.0,
                "attributes": {
                    "cti.queue.depth.queue": "ready_work",
                    "cti.queue.depth.state": "unrecorded",
                    "cti.queue.depth.reason": "github_unreadable",
                    "cti.queue.depth.oldest": "unrecorded",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows, malformed = observatory.read_queue_depths(queue_root)
    assert malformed == {}
    assert rows[0]["count"] is None
    assert rows[0]["count_reason"] == "unrecorded: github_unreadable"


def test_the_cookbook_s_queue_depth_query_runs_against_the_shipped_store(world: World) -> None:
    """The newest-sample query is the one rendering path for a current depth."""
    rebuild_world(world)
    block = next(found for found in cookbook_blocks() if "queue_depth" in found)
    rows = observatory.query(world.store_dir, block.strip().rstrip(";"))
    newest = {row[0]: row for row in rows}
    # The landing queue's newest sample is the empty one — the earlier waiting
    # sample is history the query's MAX deliberately leaves behind.
    assert newest["landing"][1:5] == ("counted", 0, "none", None)
    assert newest["reviewer"][1] == "unreadable"
    assert newest["reviewer"][2] is None, "an unreadable depth is a null, never a zero"


def test_the_cookbook_s_stage_query_runs_against_the_shipped_store(world: World) -> None:
    journal = world.review_root / str(ISSUE) / attribute_registry.STAGE_JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        arrival_line("brief", "first_time", issue=ISSUE)
        + arrival_line("brief", "after_rework", issue=ISSUE),
        encoding="utf-8",
    )
    rebuild_world(world)
    block = next(found for found in cookbook_blocks() if "stage_first_pass" in found)
    rows = observatory.query(world.store_dir, block.strip().rstrip(";"))
    by_stage = {row[0]: row for row in rows}
    assert by_stage["brief"] == (
        "brief",
        2,
        1,
        1,
        0,
        0.5,
        None,
        observatory.STAGE_BOUNDARY,
    )


def test_an_unparseable_loop_is_counted_named_and_survived(world: World) -> None:
    loop_dir = world.review_root / str(ABANDONED_ISSUE)
    loop_dir.mkdir()
    (loop_dir / "loop.json").write_text("{ not json", encoding="utf-8")
    store = rebuild_world(world)
    assert store["coverage"]["review_loops_unreadable"] == [str(ABANDONED_ISSUE)]
    assert "unreadable loop issue=493" in observatory.summary_lines(store, world.store_dir)
    row = next(row for row in store["issue_rework"] if row["issue"] == ABANDONED_ISSUE)
    assert row["review_rounds"] is None
    # The reason, not only the null: a loop that exists and would not parse is a
    # different absence from no loop at all, and the column must not flatten them.
    assert row["review_rounds_reason"] == observatory.UNREADABLE_LOOP_REASON
    no_loop = next(row for row in store["issue_rework"] if row["issue"] == STOPPED_ISSUE)
    assert no_loop["review_rounds_reason"] == observatory.NO_LOOP_REASON
    assert observatory.UNREADABLE_LOOP_REASON != observatory.NO_LOOP_REASON


def test_an_unreadable_review_root_refuses_by_name(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    gone = world.review_root / "nowhere"
    code = observatory.main(
        [
            "--dispatch-root",
            str(world.dispatch_root),
            "--export-dir",
            str(world.export_dir),
            "--review-root",
            str(gone),
            "--store-dir",
            str(world.store_dir),
            "--repo",
            str(world.repo),
        ]
    )
    assert code == 1
    assert "refused=review_root_unreadable" in capsys.readouterr().err
    assert not (world.store_dir / "store.json").exists()


# ---------------------------------------------------------------- documentation runs


def test_the_cookbook_s_first_query_runs_against_the_shipped_store(world: World) -> None:
    # One journalled landing, staged here rather than in the fixture because the
    # landing coverage counts are per-assertion facts like the stage journals. Every
    # staged dispatch record shares `a-profile`, so the honest-looking reviewer and
    # author pair is the violation the never-alone query exists to find, and the
    # gate cause gives the grouped query its row — a cookbook whose block returns
    # nothing on the shipped store is a broken block.
    journal = attribute_registry.landing_journal(ISSUE, world.review_root)
    journal.parent.mkdir(parents=True, exist_ok=True)
    relations = (
        attribute_registry.relation("subject", "issue", str(ISSUE)),
        attribute_registry.relation("produced", "commit", world.landed_sha),
        attribute_registry.relation("reviewer", "dispatch", CODEX_DISPATCH),
        attribute_registry.relation("author", "dispatch", ZAI_DISPATCH),
    )
    event = attribute_registry.landing_event(relations, 1_800_000_000.0, gate_cause="cross_lane")
    journal.write_text(
        json.dumps(
            {
                "event": event.name,
                "at": event.at,
                "attributes": dict(event.attributes),
                "resource": dict(event.resource),
                "exported": True,
                "export_detail": "http_200",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    rebuild_world(world)
    cookbook = (REPO / "docs" / "observatory" / "cookbook.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```sql\n(.*?)```", cookbook, flags=re.DOTALL)
    assert blocks, "the cookbook carries no SQL to run"
    for statement in blocks:
        rows = observatory.query(world.store_dir, statement.strip().rstrip(";"))
        assert rows, f"a cookbook query returned nothing: {statement!r}"


def test_an_unresolvable_relation_surfaces_rather_than_clears_the_check(
    world: World,
) -> None:
    """A relation the check cannot join is a finding, never a silent clearance (#491 r2 F1).

    The reviewer ran the round-1 block with a reviewer id that resolved nowhere and
    got `no violations` — the inner join dropped the one landing the question was
    about, which is #491's own failure mode one level up: a line the project
    believed. The block now returns the unresolvable relation as its own finding,
    the rebuild names the landing, and `uncheckable` counts it.
    """
    ghost_author = "d-20260805-120000-ghost1"
    ghost_reviewer = "d-20260805-120000-ghost2"
    for issue, reviewer_id in ((ISSUE, CODEX_DISPATCH), (OTHER_ISSUE, ghost_reviewer)):
        journal = attribute_registry.landing_journal(issue, world.review_root)
        journal.parent.mkdir(parents=True, exist_ok=True)
        # ISSUE's author is the ghost and its reviewer resolves — the arrangement
        # where the old block read clean while the author it should have compared
        # against was unresolvable; the second landing inverts it, an unresolvable
        # reviewer the old block's inner join dropped whole.
        relations = (
            attribute_registry.relation("subject", "issue", str(issue)),
            attribute_registry.relation("produced", "commit", world.landed_sha),
            attribute_registry.relation("reviewer", "dispatch", reviewer_id),
            attribute_registry.relation(
                "author", "dispatch", ghost_author if issue == ISSUE else ZAI_DISPATCH
            ),
        )
        event = attribute_registry.landing_event(relations, 1_800_000_000.0)
        journal.write_text(
            json.dumps(
                {
                    "event": event.name,
                    "at": event.at,
                    "attributes": dict(event.attributes),
                    "resource": dict(event.resource),
                    "exported": True,
                    "export_detail": "http_200",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    store = rebuild_world(world)
    landing = f"{ISSUE}/{world.landed_sha}"
    other_landing = f"{OTHER_ISSUE}/{world.landed_sha}"
    coverage = store["coverage"]
    assert coverage["landings_with_unresolved_relations"] == [landing, other_landing]
    assert coverage["landings_without_authors"] == [], "both landings name an author"
    line = next(
        line
        for line in observatory.summary_lines(store, world.store_dir)
        if line.startswith("landings ")
    )
    assert "uncheckable=2" in line, line
    block = next(
        found for found in cookbook_blocks() if "reviewer_is_author" in found and "UNION" in found
    )
    rows = observatory.query(world.store_dir, block.strip().rstrip(";"))
    findings = {(row[1], row[2]) for row in rows}
    assert ("unresolvable_author", ghost_author) in findings
    assert ("unresolvable_reviewer", ghost_reviewer) in findings
    assert not any(row[1] == "reviewer_is_author" for row in rows), (
        "no landing here pairs a resolvable reviewer with a resolvable author"
    )


def test_the_store_answers_sql_by_issue_and_lane(world: World) -> None:
    rebuild_world(world)
    rows = observatory.query(
        world.store_dir,
        "SELECT lane, cost FROM issue_cost WHERE landed = 1 ORDER BY lane",
    )
    assert ("claude-native", CLAUDE_OUTPUT / ledger.CLAUDE_TOKENS_PER_POINT["five_hour"]) in rows


# ------------------------------------------------------------------ the occupancy view

# The staged world's window, chosen so every span the fixture carries is visible to
# the arithmetic below: FLOW_D 12:30→12:40, FLOW_E 12:30→13:30, FLOW_G 12:30→13:00,
# FLOW_H 13:10→13:40 (outside), FLOW_F planned 12:00 and never launched — no span,
# contributing nothing — and the seven dispatches with no result.json at all,
# unbounded the same way.
WINDOW_SINCE = "2026-08-05T12:00:00+00:00"
WINDOW_UNTIL = "2026-08-05T13:00:00+00:00"
WINDOW_MINUTES = 60

OCCUPANCY_PREAMBLE = """
WITH RECURSIVE
bounds(since_iso, until_iso, ruled) AS (
    VALUES ('{since}', '{until}', {ruled})
),
spans AS (
    SELECT CAST(strftime('%s', started_at) AS INTEGER) AS s,
           CAST(strftime('%s', ended_at) AS INTEGER) AS e
    FROM dispatches
    WHERE started_at IS NOT NULL AND ended_at IS NOT NULL
),
minutes(t) AS (
    SELECT CAST(strftime('%s', since_iso) AS INTEGER) FROM bounds
    UNION ALL
    SELECT minutes.t + 60 FROM minutes CROSS JOIN bounds
    WHERE minutes.t + 60 < CAST(strftime('%s', until_iso) AS INTEGER)
),
series AS (
    SELECT minutes.t AS t, COUNT(spans.s) AS level
    FROM minutes LEFT JOIN spans ON spans.s <= minutes.t AND minutes.t < spans.e
    GROUP BY minutes.t
)
"""

OCCUPANCY_HEADLINE = (
    OCCUPANCY_PREAMBLE  # noqa: S608 — this module's own constant over the store's own tables, never input
    + """
SELECT (SELECT since_iso FROM bounds) AS window_since,
       (SELECT until_iso FROM bounds) AS window_until,
       (SELECT ruled FROM bounds) AS ruled_wip,
       COUNT(*) AS minutes,
       SUM(level) AS used_minutes,
       (SELECT ruled FROM bounds) * COUNT(*) AS capacity_minutes,
       (SELECT ruled FROM bounds) * COUNT(*) - SUM(level) AS lost_minutes,
       ROUND(CAST(SUM(level) AS REAL) / COUNT(*), 4) AS mean_concurrency,
       SUM(CASE WHEN level = 0 THEN 1 ELSE 0 END) AS idle_minutes,
       (SELECT COUNT(*) FROM dispatches d CROSS JOIN bounds b
         WHERE d.started_at IS NOT NULL AND d.ended_at IS NULL
           AND strftime('%s', d.started_at) < CAST(strftime('%s', b.until_iso) AS INTEGER)
       ) AS unbounded_dispatches
FROM series
"""
)

OCCUPANCY_HISTOGRAM = (
    OCCUPANCY_PREAMBLE
    + """
SELECT level AS concurrency, COUNT(*) AS minutes
FROM series
GROUP BY level
ORDER BY level
"""
)

OCCUPANCY_GAPS = (
    OCCUPANCY_PREAMBLE  # noqa: S608 — this module's own constant over the store's own tables, never input
    + """,
zeros AS (
    SELECT t, ROW_NUMBER() OVER (ORDER BY t) AS rn
    FROM series
    WHERE level = 0
)
SELECT strftime('%Y-%m-%dT%H:%M:%SZ', MIN(t), 'unixepoch') AS gap_start,
       strftime('%Y-%m-%dT%H:%M:%SZ', MAX(t) + 60, 'unixepoch') AS gap_end,
       COUNT(*) * 60 AS duration_seconds
FROM zeros
GROUP BY t - rn * 60
ORDER BY MIN(t)
"""
)


def occupancy(
    world: World, statement: str, *, since: str, until: str, ruled: int
) -> tuple[tuple[Any, ...], ...]:
    """Rebuild the staged world and run one occupancy statement over the window named."""
    rebuild_world(world)
    return observatory.query(
        world.store_dir, statement.format(since=since, until=until, ruled=ruled)
    )


def test_occupancy_reports_capacity_used_lost_and_mean_over_any_window(world: World) -> None:
    # Hand-derived over the staged spans, minute by minute: 12:00-12:29 nothing
    # (level 0, thirty minutes — FLOW_F never launched and the seven unbounded
    # dispatches occupy nothing), 12:30-12:39 FLOW_D, FLOW_E and FLOW_G together
    # (level 3, ten), 12:40-12:59 FLOW_E and FLOW_G (level 2, twenty).
    # Used 10*3 + 20*2 = 70 of capacity 2*60 = 120.
    rows = occupancy(
        world,
        OCCUPANCY_HEADLINE,
        since=WINDOW_SINCE,
        until=WINDOW_UNTIL,
        ruled=2,
    )
    assert rows == (
        (
            WINDOW_SINCE,
            WINDOW_UNTIL,
            2,
            WINDOW_MINUTES,
            70,
            120,
            50,
            1.1667,
            30,
            8,
        ),
    )


def test_the_concurrency_distribution_is_available_not_only_its_mean(world: World) -> None:
    rows = occupancy(
        world,
        OCCUPANCY_HISTOGRAM,
        since=WINDOW_SINCE,
        until=WINDOW_UNTIL,
        ruled=2,
    )
    # Level 3 against a ruled limit of 2: minutes above the limit count at their own
    # level, so `used` is a live count and never a clipped one.
    assert rows == ((0, 30), (2, 20), (3, 10))


def test_idle_gaps_list_start_end_and_duration(world: World) -> None:
    rows = occupancy(
        world,
        OCCUPANCY_GAPS,
        since=WINDOW_SINCE,
        until=WINDOW_UNTIL,
        ruled=2,
    )
    # The one run of idle minutes is 12:00 through 12:29 — the window opens idle,
    # because FLOW_F never launched; the gap ends at the close of its last idle
    # minute, and its duration is the histogram's level-0 row.
    assert rows == (("2026-08-05T12:00:00Z", "2026-08-05T12:30:00Z", 1800),)


def test_minute_boundaries_sample_the_grid_never_round_a_duration(
    world: World, tmp_path: Path
) -> None:
    # The mini-fixture that separates the two candidate methods: boundary sampling
    # and duration rounding disagree on exactly the forty-second dispatch, which
    # crosses no minute boundary and so contributes zero minutes (#486's pinned-
    # method pattern, applied to occupancy).
    root = tmp_path / "mini-dispatches"
    export = tmp_path / "mini-export"
    review = tmp_path / "mini-review"
    spool_parent = tmp_path / "mini-quota"
    export.mkdir()
    review.mkdir()
    spool_parent.mkdir()
    spans = {
        # Forty seconds across no minute boundary: live at neither 12:00 nor 12:01.
        "d-20260805-120000-occu01": ("2026-08-05T12:00:10+00:00", "2026-08-05T12:00:50+00:00"),
        # Live at 12:01 and 12:02 only.
        "d-20260805-120000-occu02": ("2026-08-05T12:00:20+00:00", "2026-08-05T12:02:10+00:00"),
        # Exactly aligned: live at 12:03 and 12:04, not 12:05.
        "d-20260805-120000-occu03": ("2026-08-05T12:03:00+00:00", "2026-08-05T12:05:00+00:00"),
    }
    for dispatch_id, (started, ended) in spans.items():
        stage_record(root, dispatch_id)
        (root / dispatch_id / "result.json").write_text(
            json.dumps(
                {
                    "dispatch_id": dispatch_id,
                    "status": "child_finished",
                    "returncode": 0,
                    "started_at": started,
                    "ended_at": ended,
                }
            ),
            encoding="utf-8",
        )
    observatory.rebuild(
        root, export, review, spool_parent / "statusline.jsonl", world.repo, tmp_path / "mini-store"
    )
    rows = observatory.query(
        tmp_path / "mini-store",
        OCCUPANCY_HEADLINE.format(
            since="2026-08-05T12:00:00+00:00", until="2026-08-05T12:06:00+00:00", ruled=1
        ),
    )
    # Six minutes, four of them live (two at level 1 from the second span, two from
    # the third) — the forty seconds of the first are not in the count anywhere.
    assert rows == (
        ("2026-08-05T12:00:00+00:00", "2026-08-05T12:06:00+00:00", 1, 6, 4, 6, 2, 0.6667, 2, 0),
    )
    gaps = observatory.query(
        tmp_path / "mini-store",
        OCCUPANCY_GAPS.format(
            since="2026-08-05T12:00:00+00:00", until="2026-08-05T12:06:00+00:00", ruled=1
        ),
    )
    assert gaps == (
        ("2026-08-05T12:00:00Z", "2026-08-05T12:01:00Z", 60),
        ("2026-08-05T12:05:00Z", "2026-08-05T12:06:00Z", 60),
    )


def test_a_closeout_the_run_did_not_write_fabricates_no_span(world: World, tmp_path: Path) -> None:
    # #551 round 2's fixture correction: the current stop writer writes this exact
    # closeout shape — the explicit terminal marker, no run end. Round 1 of #485 paired
    # the legacy sweep's clock with the plan's `planned_at` fallback and booked a week
    # of occupancy from one record — eleven of them held 58% of the live store's `used`.
    # The separate legacy record below keeps #485's reader guard load-bearing. The
    # rejection is by record shape, never by a list of dispatch ids: a relocated
    # declaration is what #501/#503/#504 closed.
    root = tmp_path / "swept-dispatches"
    export = tmp_path / "swept-export"
    review = tmp_path / "swept-review"
    spool_parent = tmp_path / "swept-quota"
    export.mkdir()
    review.mkdir()
    spool_parent.mkdir()
    swept = "d-20260805-120000-swept1"
    # Planned a week before the sweep, exactly the live worst case, and no process
    # existed to kill — the sweep's `killed` list is empty and the work's own end is
    # not derivable from anything that survives.
    (root / swept).mkdir(parents=True)
    (root / swept / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": swept,
                "lane": "claude-native",
                "profile": "a-profile",
                "seat": "implementer",
                "issue": ISSUE,
                "base_sha": "0" * 40,
                "planned_at": "2026-08-05T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (root / swept / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": swept,
                "stopped_by": "just dispatch --stop",
                "stopped_at": "2026-08-12T09:00:00+00:00",
                "killed": [],
                "terminal_state": {"state": "stopped"},
            }
        ),
        encoding="utf-8",
    )
    legacy_swept = "d-20260805-120000-legacy1"
    (root / legacy_swept).mkdir(parents=True)
    (root / legacy_swept / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": legacy_swept,
                "lane": "claude-native",
                "profile": "a-profile",
                "seat": "implementer",
                "issue": ISSUE,
                "base_sha": "0" * 40,
                "planned_at": "2026-08-05T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (root / legacy_swept / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": legacy_swept,
                "stopped_by": "just dispatch --stop",
                "stopped_at": "2026-08-12T09:00:00+00:00",
                "killed": [],
                "ended_at": "2026-08-12T09:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    # The same fabrication through the pruned-row path: a row whose `gate` block
    # carries an end and no start attests no span either, because `started_at` there
    # is the result's own and its absence is the same fact over that source.
    row_bound = "d-20260805-120000-rowbnd1"
    stage_record(root, row_bound)
    write_ledger_row(
        root / row_bound,
        {"input_tokens": 1, "output_tokens": 2},
        body=json.dumps(
            {
                "schema": ledger.SCHEMA,
                "dispatch_id": row_bound,
                "source": {"kind": "ledger_export", "path": "/gone", "degraded": False},
                "records": {"total": 1, "metrics": 1, "logs": 0, "spans": 0},
                "usage": {"input_tokens": 1, "output_tokens": 2},
                "end_state": PRUNED_END_STATE,
                "gate": {"ended_at": "2026-08-05T12:30:00+00:00"},
            }
        ),
    )
    observatory.rebuild(
        root,
        export,
        review,
        spool_parent / "statusline.jsonl",
        world.repo,
        tmp_path / "swept-store",
    )
    by_id = {
        row["dispatch_id"]: row
        for row in json.loads(
            (tmp_path / "swept-store" / "store.json").read_text(encoding="utf-8")
        )["dispatches"]
    }
    assert by_id[swept]["ended_at"] is None
    assert by_id[swept]["ended_at_reason"] == observatory.NO_END_STOP_SWEEP_REASON
    assert "sweep's clock" not in by_id[swept]["ended_at_reason"]
    assert by_id[swept]["terminal_state"] == "stopped"
    assert by_id[legacy_swept]["ended_at"] is None
    assert by_id[legacy_swept]["ended_at_reason"] == observatory.NO_END_STOP_SWEEP_REASON
    assert by_id[row_bound]["ended_at"] is None
    assert by_id[row_bound]["ended_at_reason"] == observatory.NO_END_NO_OWN_START_REASON
    # Over an hour that the fabricated span would have covered end to end, the
    # swept dispatch contributes nothing and is counted, not hidden.
    rows = observatory.query(
        tmp_path / "swept-store",
        OCCUPANCY_HEADLINE.format(
            since="2026-08-05T12:00:00+00:00", until="2026-08-05T13:00:00+00:00", ruled=1
        ),
    )
    assert rows == (
        ("2026-08-05T12:00:00+00:00", "2026-08-05T13:00:00+00:00", 1, 60, 0, 60, 60, 0.0, 60, 3),
    )


def test_unbounded_work_occupies_nothing_and_is_named_by_fact_not_inference(
    world: World,
) -> None:
    store = rebuild_world(world)
    by_id = {row["dispatch_id"]: row for row in store["dispatches"]}
    # The quota death started and did not complete — #489's block says so — and its
    # ten real minutes are occupied, because the seat really held them.
    assert by_id[FLOW_D]["terminal_state"] == "abandoned"
    assert by_id[FLOW_D]["ended_at"] == "2026-08-05T12:40:00+00:00"
    # The never-launched refusal is not "started and did not complete" either, and it
    # attests no span: its closeout's end would open a span at the plan's `planned_at`,
    # which is a launch attempt and never occupancy.
    assert by_id[FLOW_F]["terminal_state"] is None
    assert by_id[FLOW_F]["terminal_state_reason"] == observatory.TERMINAL_NEVER_STARTED_REASON
    assert by_id[FLOW_F]["ended_at"] is None
    assert by_id[FLOW_F]["ended_at_reason"] == observatory.NO_END_NO_OWN_START_REASON
    # A dispatch with no result.json has no bound, and the store says why without
    # guessing: still running and dead-without-closeout are indistinguishable here.
    assert by_id[CLAUDE_DISPATCH]["ended_at"] is None
    assert by_id[CLAUDE_DISPATCH]["ended_at_reason"] == observatory.NO_END_RUNNING_REASON
    assert by_id[CLAUDE_DISPATCH]["terminal_state_reason"] == observatory.TERMINAL_RUNNING_REASON
    # The headline names the eight it could not bound, and its used minutes (70,
    # pinned above) contain none of them: unbounded work inflates nothing.
    rows = observatory.query(
        world.store_dir,
        OCCUPANCY_HEADLINE.format(since=WINDOW_SINCE, until=WINDOW_UNTIL, ruled=2),
    )
    assert rows[0][9] == 8
    assert rows[0][4] == 70


def test_a_pruned_dispatch_s_end_and_terminal_state_come_from_its_row(world: World) -> None:
    # The day-after-prune row carries both facts under its own keys: the end under
    # `gate.ended_at`, the terminal state as #489's block. A row without them is an
    # absence with its own reason, never a guess.
    full_row = json.dumps(
        {
            "schema": ledger.SCHEMA,
            "dispatch_id": FLOW_D,
            "source": {"kind": "ledger_export", "path": "/gone", "degraded": False},
            "records": {"total": 1, "metrics": 1, "logs": 0, "spans": 0},
            "usage": {"input_tokens": 10, "output_tokens": 20},
            "end_state": PRUNED_END_STATE,
            "terminal_state": {"state": "abandoned", "class": "quota_exhausted"},
            "gate": {
                "started_at": "2026-08-05T12:30:00+00:00",
                "ended_at": "2026-08-05T12:45:00+00:00",
            },
        }
    )
    # FLOW_D and FLOW_E carry no export file in this world, so a surviving ledger row
    # is already the pruned-source read: `telemetry_source` goes to `ledger_row` and
    # the row's own keys are all that answers.
    write_ledger_row(
        world.dispatch_root / FLOW_D, {"input_tokens": 10, "output_tokens": 20}, body=full_row
    )
    write_ledger_row(world.dispatch_root / FLOW_E, {"input_tokens": 30, "output_tokens": 40})
    store = rebuild_world(world)
    by_id = {row["dispatch_id"]: row for row in store["dispatches"]}
    assert by_id[FLOW_D]["ended_at"] == "2026-08-05T12:45:00+00:00"
    assert by_id[FLOW_D]["terminal_state"] == "abandoned"
    assert by_id[FLOW_E]["ended_at"] is None
    assert by_id[FLOW_E]["ended_at_reason"] == observatory.NO_END_ROW_REASON
    assert by_id[FLOW_E]["terminal_state_reason"] == observatory.TERMINAL_ROW_REASON


def test_the_cookbook_s_occupancy_queries_run_over_the_research_window(world: World) -> None:
    # §1's own window, carried by the cookbook: 2026-08-05T17:28Z to 2026-08-21T06:09Z
    # is 22,361 whole minutes — the document's own 22,361 wall minutes, restated by
    # the query rather than trusted — and the staged world sits entirely before it,
    # so the window is idle end to end and every figure is exact.
    rebuild_world(world)
    headline = next(block for block in cookbook_blocks() if "mean_concurrency" in block)
    rows = observatory.query(world.store_dir, headline.strip().rstrip(";"))
    assert rows == (
        (
            "2026-08-05T17:28:00+00:00",
            "2026-08-21T06:09:00+00:00",
            3,
            22361,
            0,
            67083,
            67083,
            0.0,
            22361,
            8,
        ),
    )
    gaps = next(block for block in cookbook_blocks() if "gap_start" in block)
    assert observatory.query(world.store_dir, gaps.strip().rstrip(";")) == (
        ("2026-08-05T17:28:00Z", "2026-08-21T06:09:00Z", 1341660),
    )
    histogram = next(block for block in cookbook_blocks() if "AS concurrency" in block)
    assert observatory.query(world.store_dir, histogram.strip().rstrip(";")) == ((0, 22361),)


# ---------------------------------------------------------------- the session view


def session_row(store: dict[str, Any], session_id: str, period: str) -> dict[str, Any]:
    """Return one (session, period) row from the store."""
    return next(
        row
        for row in store["session_period"]
        if row["session_id"] == session_id and row["period"] == period
    )


def period_row(store: dict[str, Any], period: str) -> dict[str, Any]:
    """Return one period's overhead row from the store."""
    return next(row for row in store["period_overhead"] if row["period"] == period)


def test_session_spend_is_reported_as_period_deltas_never_running_totals(
    world: World,
) -> None:
    store = rebuild_world(world)
    # July's render sits in the rolled generation, August's in the live spool: the
    # periods come from the timestamps, so the seam between the files is nothing and
    # the July period is July's by its own instant.
    july = session_row(store, HUMAN_SESSION, "2026-07")
    august = session_row(store, HUMAN_SESSION, "2026-08")
    assert (july["renders"], july["cost_usd_list_price"]) == (1, 1.0)
    assert (july["duration_ms"], july["lines_added"], july["lines_removed"]) == (
        100_000.0,
        50.0,
        10.0,
    )
    # Deltas, never the running totals: August's end-of-period cumulatives are
    # 3.0 / 300_000 / 120 / 30, and the row holds the differences from July's
    # 1.0 / 100_000 / 50 / 10.
    assert (august["renders"], august["cost_usd_list_price"]) == (2, 2.0)
    assert (august["duration_ms"], august["lines_added"], august["lines_removed"]) == (
        200_000.0,
        70.0,
        20.0,
    )
    assert august["last_render_at"] == "2026-08-05T12:00:00+00:00"


def test_a_counter_the_source_never_carried_is_absent_with_its_own_reason(
    world: World,
) -> None:
    store = rebuild_world(world)
    brief = session_row(store, BRIEF_SESSION, "2026-08")
    assert brief["cost_usd_list_price"] == 0.5
    # The brief session's payload never carried the duration or lines counters, so
    # those absences name the source's ceiling.
    assert brief["duration_ms_reason"] == observatory.NO_COUNTER_REASON
    assert brief["lines_added_reason"] == observatory.NO_COUNTER_REASON
    # The other session carries every counter, so its rows never see that reason.
    human = session_row(store, HUMAN_SESSION, "2026-08")
    assert human["duration_ms"] == 200_000.0
    assert human["duration_ms_reason"] is None


def test_no_token_key_is_read_as_a_counter_where_every_render_carries_the_gauge(
    world: World,
) -> None:
    store = rebuild_world(world)
    # Every staged render carries `context_window.total_output_tokens`, and the
    # gauge falls and rises between renders of the one session — the shape the live
    # spool measurably carries. A reader that mistakes it for a session-lifetime
    # counter would emit a negative August delta here; the column must be absent
    # with the reason that names the gauge instead (#488 round 2).
    for row in store["session_period"]:
        assert row["output_tokens"] is None
        assert row["output_tokens_reason"] == observatory.NO_OUTPUT_TOKENS_REASON
    august = period_row(store, "2026-08")
    assert august["sessions_with_output"] == 0
    assert august["output_tokens"] is None
    assert august["output_tokens_reason"] == observatory.NO_OUTPUT_TOKENS_REASON
    assert august["overhead_window_points"] is None
    assert august["overhead_window_points_reason"] == observatory.NO_OUTPUT_TOKENS_REASON


def test_every_rendering_path_names_the_orchestrator_s_absence(world: World) -> None:
    store = rebuild_world(world)
    # The boundary is a column on every row of both tables, so a reader querying the
    # table directly — without the cookbook or the schema reference — still meets it,
    # and it names the orchestrator specifically, never generic incompleteness.
    for row in [*store["session_period"], *store["period_overhead"]]:
        assert "orchestrator" in row["boundary"]
        assert "renders none" in row["boundary"]
    lines = observatory.summary_lines(store, world.store_dir)
    assert any("orchestrator=absent" in line for line in lines)
    assert any("meter=list_price_not_spend" in line for line in lines)


def test_the_fully_loaded_figure_is_an_absence_naming_the_incommensurability(
    world: World,
) -> None:
    store = rebuild_world(world)
    august = period_row(store, "2026-08")
    # The direct half still exists — the fixture's one Claude-lane point, with the
    # other three landings of the period visible as a shortfall between `landings`
    # and `direct_landings`, never as a smaller number — and the overhead half
    # exists in list-price dollars. No single meter holds both, so the sum the
    # column names is null on every row with the reason saying why — never a
    # partial sum and never zero (#488 round 2).
    assert august["landings"] == 4
    assert august["direct_landings"] == 1
    assert (
        august["direct_window_points"]
        == CLAUDE_OUTPUT / ledger.CLAUDE_TOKENS_PER_POINT["five_hour"]
    )
    assert august["cost_usd_list_price"] == 2.5
    assert august["fully_loaded_window_points"] is None
    assert (
        august["fully_loaded_window_points_reason"]
        == observatory.FULLY_LOADED_INCOMMENSURABLE_REASON
    )
    # A period whose direct half is absent gets the same absence, not a different
    # one: the incommensurability holds before either half is even missing.
    july = period_row(store, "2026-07")
    assert july["direct_window_points"] is None
    assert july["direct_window_points_reason"] == observatory.DIRECT_ABSENT_REASON
    assert july["fully_loaded_window_points"] is None
    assert (
        july["fully_loaded_window_points_reason"] == observatory.FULLY_LOADED_INCOMMENSURABLE_REASON
    )
    # The derived column carries the same boundary warning as the overhead it
    # derives from — including the orchestrator clause.
    assert august["boundary"] == observatory.PERIOD_BOUNDARY
    assert observatory.PERIOD_BOUNDARY.startswith(observatory.SESSION_BOUNDARY)


def test_no_overhead_figure_is_attached_to_an_issue_anywhere(world: World) -> None:
    store = rebuild_world(world)
    # Structural, not a rule: neither table carries an issue column, so apportioning
    # overhead to an issue is not something the output can express — the way #486
    # made "no mean as the headline" the view's whole column list.
    banned = re.compile(r"(?i)issue")
    for table in ("session_period", "period_overhead"):
        with observatory.connect(world.store_dir) as connection:
            columns = tuple(
                str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
            )
        assert columns == getattr(observatory, f"{table.upper()}_COLUMNS")
        assert not any(banned.search(column) for column in columns), table
        for row in store[table]:
            assert not any(banned.search(str(key)) for key in row), table


def test_untimestamped_and_unattributable_renders_are_counted_never_summed(
    world: World,
) -> None:
    store = rebuild_world(world)
    coverage = store["coverage"]
    # One bare pre-#488 line, one envelope without a session id, one truncated line:
    # three absences, three counters, none read as a render and none swallowed.
    assert coverage["session_renders_untimestamped"] == 1
    assert coverage["session_renders_without_session_id"] == 1
    assert coverage["session_renders"] == 4  # three HUMAN, one BRIEF
    assert coverage["session_spend_sessions"] == 2
    assert coverage["session_spend_periods"] == 2
    assert {entry["file"] for entry in store["malformed"]} == {
        f"dispatch-{CODEX_DISPATCH}.jsonl",
        world.spool.name,
        # The queue-depth journal's staged truncated line (#492) — the same
        # discipline at a third parse boundary, named for its own file.
        "queue/queue-depths.jsonl",
    }
    assert "s-pre-488" not in {row["session_id"] for row in store["session_period"]}


def test_the_spool_is_read_generations_first_and_periods_come_from_timestamps(
    world: World,
) -> None:
    store = rebuild_world(world)
    # The July render lives only in `.1`; that it appears at all proves the
    # generations were read, and that it is July's own period — not "generation one"
    # — proves the period came from the timestamp and not the file boundary.
    assert session_row(store, HUMAN_SESSION, "2026-07")["renders"] == 1
    assert period_row(store, "2026-07")["sessions"] == 1


def test_an_unreadable_spool_directory_refuses_by_name(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    gone = world.spool.parent / "nowhere" / "statusline.jsonl"
    code = observatory.main(
        [
            "--dispatch-root",
            str(world.dispatch_root),
            "--export-dir",
            str(world.export_dir),
            "--review-root",
            str(world.review_root),
            "--spool",
            str(gone),
            "--store-dir",
            str(world.store_dir),
            "--repo",
            str(world.repo),
        ]
    )
    assert code == 1
    printed = capsys.readouterr().err
    assert "refused=spool_unreadable" in printed
    assert f"path={gone.parent}" in printed
    assert not (world.store_dir / "store.json").exists()


def test_the_spool_lives_outside_every_worktree() -> None:
    expected = Path.home() / ".arma-cti" / "quota" / "statusline.jsonl"
    assert expected == observatory.DEFAULT_SPOOL
    assert not observatory.DEFAULT_SPOOL.is_relative_to(REPO)
