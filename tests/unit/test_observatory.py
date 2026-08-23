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

**The documentation runs.** The cookbook's first query is executed against the
shipped store, because a cookbook that does not run is worse than none.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from conftest import REPO, load_tool

observatory = load_tool("observatory")
ledger = observatory.ledger

PLANNED = "2026-08-05T12:00:00+00:00"
AFTER_PLANNED = "2026-08-05T23:30:00+00:00"
ISSUE = 482
OTHER_ISSUE = 483

CLAUDE_DISPATCH = "d-20260805-120000-claud1"
CODEX_DISPATCH = "d-20260805-120000-codex1"
ZAI_DISPATCH = "d-20260805-120000-zai001"
BARE_DISPATCH = "d-20260805-120000-bare01"

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


def stage_record(
    root: Path,
    dispatch_id: str,
    *,
    issue: int = ISSUE,
    lane: str = "claude-native",
) -> Path:
    """Lay down a dispatch record the way `just dispatch` leaves one."""
    record = root / dispatch_id
    record.mkdir(parents=True, exist_ok=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": dispatch_id,
                "lane": lane,
                "profile": "a-profile",
                "seat": "implementer",
                "issue": issue,
                "base_sha": "0" * 40,
                "planned_at": PLANNED,
            }
        ),
        encoding="utf-8",
    )
    return record


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
    store_dir: Path
    repo: Path
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
    stage_record(dispatch_root, CLAUDE_DISPATCH, lane="claude-native")
    stage_record(dispatch_root, CODEX_DISPATCH, lane="codex")
    stage_record(dispatch_root, ZAI_DISPATCH, lane="zai")
    stage_record(dispatch_root, BARE_DISPATCH, issue=OTHER_ISSUE)

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

    return World(dispatch_root, export_dir, tmp_path / "store", repo, landed_sha)


def rebuild_world(world: World) -> dict[str, Any]:
    """Rebuild the staged world's store and return the document."""
    return observatory.rebuild(world.dispatch_root, world.export_dir, world.repo, world.store_dir)


def cost_row(store: dict[str, Any], issue: int, lane: str) -> dict[str, Any]:
    """Return one (issue, lane) cost row from the store."""
    return next(row for row in store["issue_cost"] if row["issue"] == issue and row["lane"] == lane)


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
    assert coverage["dispatches"] == 4
    assert coverage["dispatches_with_telemetry"] == 3
    assert coverage["dispatches_with_spend"] == 3
    assert coverage["dispatches_without_telemetry"] == [BARE_DISPATCH]
    assert coverage["issues"] == 2
    assert coverage["issues_with_landings"] == 1
    lines = observatory.summary_lines(store, world.store_dir)
    assert any(
        "dispatches=4" in line and "with_spend=3" in line and "issues_with_landings=1" in line
        for line in lines
    )


def test_the_landed_sha_is_attributed_to_the_issue_that_landed(world: World) -> None:
    store = rebuild_world(world)
    assert cost_row(store, ISSUE, "claude-native")["landed_sha"] == world.landed_sha
    assert cost_row(store, OTHER_ISSUE, "claude-native")["landed"] is False
    assert cost_row(store, OTHER_ISSUE, "claude-native")["landed_sha_reason"]


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
            "--store-dir",
            str(world.store_dir),
            "--repo",
            str(world.repo),
        ]
    )
    assert code == 1
    assert "refused=dispatch_root_unreadable" in capsys.readouterr().err
    assert not (world.store_dir / "store.json").exists()


# --------------------------------------------------------------- the store's home


def test_the_store_lives_outside_every_worktree() -> None:
    expected_home = Path.home() / ".arma-cti" / "observatory"
    assert expected_home == observatory.DEFAULT_STORE_DIR
    assert not observatory.DEFAULT_STORE_DIR.is_relative_to(REPO)


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
