"""What a corpus run's own record says when it is quoted into an issue (#199).

The fixtures under `tests/fixtures/pools/` are real `pool.json` documents this
tier wrote on 2026-08-04 and 2026-08-05, copied in verbatim: a 25-of-25 green,
a run starved out at eight probes with fifteen never run, a red carrying one
`assertion_failed`, and one written before `worst_class` was a field. Real
records rather than hand-written approximations, because the whole of this
tool's job is reading records it did not write. Their evidence paths are
relocated into each test's own directory on the way in, so no test reads — or
depends on the survival of — the evidence the fixture was captured from.

Two of the criteria are structural rather than textual and are asserted as
such: the per-probe block is `pool_merge.render_summary`'s output compared line
for line (criterion 2), and the renderer cannot post because it has no way to
(criterion 7).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from conftest import REPO, load_tool

if TYPE_CHECKING:
    import pytest

pool_comment = load_tool("pool_comment")
pool_merge = load_tool("pool_merge")

FIXTURES = REPO / "tests" / "fixtures" / "pools"
GREEN = "green-25.json"
STARVED = "starved.json"
RED = "red-assertion.json"
LEGACY = "legacy-no-worst-class.json"


def staged(
    runs: Path,
    fixture: str = GREEN,
    *,
    stamp: str = "20260805T025128Z-3447440-pool",
    **overrides: Any,  # noqa: ANN401 — the pool.json fields a test varies, as they are
) -> Path:
    """Write one captured pool record into a test's own runs directory."""
    document = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    document.update(overrides)
    for row in document.get("verdicts", []):
        row["evidence"] = str(runs / Path(row["evidence"]).name)
    directory = runs / stamp
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pool.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    return directory


def probe_evidence(runs: Path, probe: str, **fields: object) -> Path:
    """Write one probe's `verdict.json` where the pool record points at it."""
    directory = runs / f"20260805T015715Z-{probe}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "verdict.json").write_text(
        json.dumps({"probe": probe, "git_dirty": False, "detail": "", **fields}),
        encoding="utf-8",
    )
    return directory


def rendered(target: Path) -> str:
    """Render the body the tool would hand an agent to paste."""
    return "\n".join(pool_comment.comment_for(pool_comment.resolve(target)))


def test_a_green_pool_states_its_worst_class_count_wall_sha_and_evidence(tmp_path: Path) -> None:
    body = rendered(staged(tmp_path))

    assert "worst class `pass`" in body
    assert "25 of 25 pass" in body
    assert "wall 1120 s across 3 slot(s)" in body
    assert "sha `8127fab02377`" in body
    assert str(tmp_path / "20260805T025128Z-3447440-pool") in body


def test_the_per_probe_block_is_the_runner_s_own_summary_line_for_line(tmp_path: Path) -> None:
    pool = staged(tmp_path)
    document = json.loads((pool / "pool.json").read_text(encoding="utf-8"))
    summary = pool_merge.render_summary(
        pool_merge.merged_from_pool(document),
        started_at=document["started_at"],
        git_sha=document["git_sha"],
        slot_count=len(document["slots"]),
    )

    body = rendered(pool)

    assert [line for line in summary if line]
    for line in summary:
        if line:
            assert line in body


def test_every_probe_gets_a_line_so_the_quote_outlives_the_pruned_evidence(
    tmp_path: Path,
) -> None:
    pool = staged(tmp_path)
    document = json.loads((pool / "pool.json").read_text(encoding="utf-8"))

    body = rendered(pool)

    for row in document["verdicts"]:
        assert row["probe"] in body
        assert row["evidence"] in body


def test_a_red_names_the_failing_probe_and_quotes_the_detail_it_recorded(tmp_path: Path) -> None:
    pool = staged(tmp_path, RED, stamp="20260805T014200Z-2741777-pool")
    probe_evidence(
        tmp_path,
        "respawn-base",
        detail="FAIL class=assertion_failed respawn_probe_came_back_early took=29.788 delay=30",
    )

    body = rendered(pool)

    assert "worst class `assertion_failed`" in body
    assert "23 of 24 pass" in body
    assert "respawn_probe_came_back_early took=29.788 delay=30" in body


def test_a_non_pass_probe_whose_evidence_is_gone_says_so_rather_than_nothing(
    tmp_path: Path,
) -> None:
    pool = staged(tmp_path, RED, stamp="20260805T014200Z-2741777-pool")

    body = rendered(pool)

    assert "no verdict.json" in body
    assert "respawn-base" in body


def test_infra_unavailable_renders_as_the_stop_it_is(tmp_path: Path) -> None:
    pool = staged(tmp_path, STARVED, stamp="20260805T010849Z-2195526-pool")

    body = rendered(pool)

    assert "worst class `infra_unavailable`" in body
    assert "not a result" in body
    assert "Do not interpret" in body
    assert "7 of 8 pass" in body
    assert "15 probe(s) never run" in body
    assert "infra_unavailable in slot 3 on contacts" in body


def test_a_record_written_before_worst_class_was_a_field_derives_it_and_says_so(
    tmp_path: Path,
) -> None:
    pool = staged(tmp_path, LEGACY, stamp="20260804T202621Z-3846863-pool")

    body = rendered(pool)

    assert "worst class `timeout`" in body
    assert "derived" in body


def test_a_record_that_understates_its_own_rows_is_quoted_at_the_worse_of_the_two(
    tmp_path: Path,
) -> None:
    pool = staged(tmp_path, LEGACY, stamp="20260804T202621Z-3846863-pool", worst_class="pass")

    body = rendered(pool)

    assert "worst class `timeout`" in body
    assert "understates" in body
    assert "disagree" in body


def test_a_dirty_tree_at_run_time_is_flagged_against_the_sha_it_would_not_reproduce(
    tmp_path: Path,
) -> None:
    pool = staged(tmp_path, RED, stamp="20260805T014200Z-2741777-pool")
    probe_evidence(tmp_path, "respawn-base", git_dirty=True, detail="FAIL class=assertion_failed")

    body = rendered(pool)

    assert "dirty" in body
    assert "does not reproduce" in body


def test_a_tree_state_nobody_recorded_is_unrecorded_rather_than_clean(tmp_path: Path) -> None:
    body = rendered(staged(tmp_path))

    assert "tree state unrecorded" in body
    assert "tree clean" not in body


def test_a_slot_held_and_never_used_is_named(tmp_path: Path) -> None:
    pool = staged(
        tmp_path,
        dirty_slots=[
            {
                "slot": 1,
                "class": "infra_unavailable",
                "detail": "a dead run's server still on 2502",
            }
        ],
    )

    body = rendered(pool)

    assert "slot 1" in body
    assert "a dead run's server still on 2502" in body


def test_the_newest_pool_is_what_the_default_reads(tmp_path: Path) -> None:
    older = staged(tmp_path, STARVED, stamp="20260805T010849Z-2195526-pool")
    newer = staged(tmp_path, GREEN, stamp="20260805T025128Z-3447440-pool")
    (older / "pool.json").touch()
    (newer / "pool.json").touch()

    assert pool_comment.newest_pool(tmp_path) == newer / "pool.json"


def test_a_pool_directory_with_no_pool_json_is_refused_as_a_run_that_died(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dead = tmp_path / "20260805T031500Z-9-pool"
    dead.mkdir(parents=True)

    exit_code = pool_comment.main([str(dead)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "ADR-0022" in captured.err


def test_a_directory_that_is_no_run_s_evidence_is_refused_as_that_rather_than_as_a_death(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = pool_comment.main([str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "not a pool evidence directory" in captured.err
    assert "ADR-0022" not in captured.err


def test_a_probe_evidence_directory_is_refused_and_told_where_to_point(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    probe = probe_evidence(tmp_path, "respawn-base")

    exit_code = pool_comment.main([str(probe)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "*-pool" in captured.err


def test_a_half_written_record_is_refused_rather_than_partly_rendered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pool = staged(tmp_path)
    (pool / "pool.json").write_text('{"started_at": "2026-08-05T02:5', encoding="utf-8")

    exit_code = pool_comment.main([str(pool)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "not a readable" in captured.err


def test_a_record_that_measured_nothing_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pool = staged(tmp_path, verdicts=[], not_run=[], stopped_early="")

    exit_code = pool_comment.main([str(pool)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "nothing to quote" in captured.err


def test_no_pool_at_all_under_the_runs_directory_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = pool_comment.main(["--runs-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "no pool evidence" in captured.err


def test_the_body_goes_to_stdout_and_the_run_reports_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    staged(tmp_path)

    exit_code = pool_comment.main(["--runs-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "worst class `pass`" in captured.out
    assert captured.err == ""


def test_the_renderer_has_no_way_to_post_what_it_renders(tmp_path: Path) -> None:
    source = (REPO / "tools" / "pool_comment.py").read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "gh issue comment" not in source
    assert rendered(staged(tmp_path))
