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
shipped store, because a cookbook that does not run is worse than none.

**The flow view is percentiles, never a mean, and abandoned work is derived.** The
staged world carries a right-skewed landed sample on which nearest-rank and linear
interpolation disagree at every percentile, and the view's values are pinned to the
nearest-rank ones so a change of method is a red. The view's column list is pinned
exactly, so no mean can enter the headline slot. An abandoned work item is typed by
its dispatch's own `gate_outcome` — `not_a_result`, the existing vocabulary — never
by a list of issue numbers or an age heuristic, and the terminal residue without a
failure class is `stopped`, the boundary #489 will widen.

**The rework view ranks only where its denominator exists, and marks its own limits.**
ADR-0071 ruling 6's key — fix rounds per landing — is computed for implementer-seat
profiles and no others, with the seat set derived from the registries rather than
named. A profile with no landings keeps its rounds visible and its rate undefined,
never a division; a seat that lands nothing by contract keeps its rework reported and
unranked, its reason distinguishing the contract from a miss. The companion measure,
dispatches per issue, is reported beside the key and explicitly unranked; the outcome
columns carry a `measures` marker naming them description; and the summary line states
the key's own spread and that its sample limit is an estimate, not a measurement.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Mapping

import pytest
from conftest import REPO, load_tool

observatory = load_tool("observatory")
ledger = observatory.ledger
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
# abandoned by a dispatcher refusal, and one stopped — ended, never landed, no failure
# class. Their lead times with ISSUE's 41400 give the percentile tests a sample,
# [3600, 7200, 10800, 41400], on which nearest-rank and linear interpolation disagree
# at every percentile pinned below.
FLOW_A = "d-20260805-120000-flow01"
FLOW_B = "d-20260805-120000-flow02"
FLOW_C = "d-20260805-120000-flow03"
FLOW_D = "d-20260805-120000-flow04"
FLOW_E = "d-20260805-120000-flow05"

LANDED_ONE_HOUR = 490
LANDED_TWO_HOURS = 491
LANDED_THREE_HOURS = 492
ABANDONED_ISSUE = 493
STOPPED_ISSUE = 494
# The rework view's own issue: five rounds recorded against a dispatch that never
# lands — the zero-denominator row the ruled key must carry unranked, with its rounds
# visible, rather than as a division.
ROUNDY_ISSUE = 495

# One five-hour-window point exactly: the calibration's own numerator, so the cost
# row's arithmetic is pinned against `ledger`'s constant rather than a restated 30209.
CLAUDE_OUTPUT = ledger.CLAUDE_TOKENS_PER_POINT["five_hour"]
CODEX_OUTPUT = 54321


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
    seat: str = "implementer",
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
    store_dir: Path
    repo: Path
    base_sha: str
    landed_sha: str


@pytest.fixture
def world(tmp_path: Path) -> World:
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
    ):
        stage_record(dispatch_root, dispatch, issue=issue)
    # FLOW_D ended child_not_launched with a failure class — the record's own terminal
    # refusal, which is what makes the issue's work item abandoned rather than stopped.
    (dispatch_root / FLOW_D / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": FLOW_D,
                "status": "child_not_launched",
                "refusal": "lane_breaker_open",
                "failure_class": "provider_refused",
                "ended_at": "2026-08-05T12:10:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    # FLOW_E ran to a clean exit and landed nothing — terminal without a failure class.
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

    return World(dispatch_root, export_dir, review_root, tmp_path / "store", repo, base, landed_sha)


def rebuild_world(world: World) -> dict[str, Any]:
    """Rebuild the staged world's store and return the document."""
    return observatory.rebuild(
        world.dispatch_root, world.export_dir, world.review_root, world.repo, world.store_dir
    )


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
    assert store["coverage"]["malformed_lines"] == 1
    assert store["malformed"] == [{"file": f"dispatch-{CODEX_DISPATCH}.jsonl", "lines": 1}]
    # The dispatch's spend still read, from the lines that did parse.
    assert cost_row(store, ISSUE, "codex")["output_tokens"] == CODEX_OUTPUT
    lines = observatory.summary_lines(store, world.store_dir)
    assert any("malformed_lines=1" in line for line in lines)
    assert any(f"file=dispatch-{CODEX_DISPATCH}.jsonl" in line for line in lines)


def test_the_rebuild_states_its_own_coverage(world: World) -> None:
    store = rebuild_world(world)
    coverage = store["coverage"]
    assert coverage["dispatches"] == 9
    assert coverage["dispatches_with_telemetry"] == 3
    assert coverage["dispatches_with_spend"] == 3
    assert coverage["dispatches_without_telemetry"] == [
        BARE_DISPATCH,
        FLOW_A,
        FLOW_B,
        FLOW_C,
        FLOW_D,
        FLOW_E,
    ]
    assert coverage["issues"] == 7
    assert coverage["issues_with_landings"] == 4
    lines = observatory.summary_lines(store, world.store_dir)
    assert any(
        "dispatches=9" in line and "with_spend=3" in line and "issues_with_landings=4" in line
        for line in lines
    )


def test_the_landed_sha_is_attributed_to_the_issue_that_landed(world: World) -> None:
    store = rebuild_world(world)
    assert cost_row(store, ISSUE, "claude-native")["landed_sha"] == world.landed_sha
    assert cost_row(store, OTHER_ISSUE, "claude-native")["landed"] is False
    assert cost_row(store, OTHER_ISSUE, "claude-native")["landed_sha_reason"]


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
    }
    # The partition is derived, never declared: the abandoned item's own dispatch row
    # carries the class that made it abandoned, and the stopped one carries not_landed.
    abandoned = next(row for row in store["dispatches"] if row["dispatch_id"] == FLOW_D)
    assert abandoned["end_state_class"] == "provider_refused"
    assert abandoned["gate_outcome"] == "not_a_result"
    stopped = next(row for row in store["dispatches"] if row["dispatch_id"] == FLOW_E)
    assert stopped["gate_outcome"] == "not_landed"
    lines = observatory.summary_lines(store, world.store_dir)
    assert "flow work_items=7 landed=4 open=1 abandoned=1 stopped=1" in lines


def test_abandoned_work_is_excluded_from_lead_time_and_counted_separately(
    world: World,
) -> None:
    store = rebuild_world(world)
    # Excluded: the distribution's denominator is the landed items alone, so the
    # abandoned issue never enters it however long it sat; counted: its own row and the
    # coverage block carry it as abandoned, not as a silently dropped item.
    assert work_item(store, ABANDONED_ISSUE)["lead_time_seconds"] is None
    assert store["coverage"]["work_items"] == 7
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
    observatory.rebuild(dispatch_root, export_dir, review_root, tmp_path, store_dir)
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


def test_an_unparseable_loop_is_counted_named_and_survived(world: World) -> None:
    loop_dir = world.review_root / str(ABANDONED_ISSUE)
    loop_dir.mkdir()
    (loop_dir / "loop.json").write_text("{ not json", encoding="utf-8")
    store = rebuild_world(world)
    assert store["coverage"]["review_loops_unreadable"] == [str(ABANDONED_ISSUE)]
    assert "unreadable loop issue=493" in observatory.summary_lines(store, world.store_dir)
    row = next(row for row in store["issue_rework"] if row["issue"] == ABANDONED_ISSUE)
    assert row["review_rounds"] is None


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
    rebuild_world(world)
    cookbook = (REPO / "docs" / "observatory" / "cookbook.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```sql\n(.*?)```", cookbook, flags=re.DOTALL)
    assert blocks, "the cookbook carries no SQL to run"
    for statement in blocks:
        rows = observatory.query(world.store_dir, statement.strip().rstrip(";"))
        assert rows, f"a cookbook query returned nothing: {statement!r}"


def test_the_store_answers_sql_by_issue_and_lane(world: World) -> None:
    rebuild_world(world)
    rows = observatory.query(
        world.store_dir,
        "SELECT lane, cost FROM issue_cost WHERE landed = 1 ORDER BY lane",
    )
    assert ("claude-native", CLAUDE_OUTPUT / ledger.CLAUDE_TOKENS_PER_POINT["five_hour"]) in rows
