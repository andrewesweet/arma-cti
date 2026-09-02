"""How N slots' worth of claims become one verdict set (#185, ADR-0049).

The pool's merge lived in `spike/regress.sh` as decision logic end to end —
the dead-slot rule (ADR-0022), client-lock-blocked typing (#127), the mem-stop
overlay (#125), worst-class ranking, and `pool.json` assembled by forty lines
of `printf` over a hand-rolled `json_string` — read back through `json_field`,
an indentation-dependent `sed`. `tools/pool_merge.py` is that merge as
functions under pytest, plus the two riders that go wherever the merge goes:
`prune-passes` (the `grep -l '"verdict": "PASS"'` reader) and
`fallback-verdict` (the typer-failed heredoc, `verdict.json`'s second writer).

The behaviour asserted is the one `regress.sh` had, byte-for-byte where a
reader depends on the bytes: `tests/unit/test_pool_slots.py` asserts on the
summary's stderr and reads `pool.json` back, and the shell acts on the
`key=value` stdout lines.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

pool_merge = load_tool("pool_merge")
probe_verdict = load_tool("probe_verdict")

STARTED = "2026-08-04T10:11:12Z"
SHA = "4ccaed031df054a7a36e"


# ------------------------------------------------------------------- severity


def test_the_severity_ladder_is_the_failure_class_table() -> None:
    """Severity orders the summary and picks the worst class; exit codes do not."""
    ladder = [
        ("untyped_harness_failure", 90),
        ("infra_unavailable", 80),
        ("node_crashed", 70),
        ("engine_drift", 60),
        ("oracle_disagreement", 50),
        ("schema_stale", 40),
        ("timeout", 30),
        ("assertion_failed", 20),
        ("flake_quarantine", 0),
        ("pass", 0),
    ]
    for class_, expected in ladder:
        assert pool_merge.severity(class_) == expected, class_


def test_an_unknown_class_is_an_untyped_red_worst_of_all() -> None:
    assert pool_merge.severity("banana") == 90


# ------------------------------------------------- the in-mission boundary (#147)
# `run.sh`'s `class_of` was a bash sed with no notion of which classes exist, so
# an in-world typo (`class=timout`) flowed through the whole tier as an unknown
# class and surfaced as an undocumented exit. The mapping joined this home —
# the class table's own seam, per the routing #161 wrote at its definition —
# and validates where the line is first read.


@pytest.mark.parametrize(
    "declared",
    [
        "assertion_failed",
        "timeout",
        "node_crashed",
        "oracle_disagreement",
        "infra_unavailable",
        "engine_drift",
        "schema_stale",
    ],
)
def test_a_declared_table_class_is_kept_with_the_line_as_detail(declared: str) -> None:
    line = f"FAIL class={declared} probe_never_finished step=3"
    assert pool_merge.mission_class(line) == (declared, line)


def test_a_bare_fail_is_still_an_assertion() -> None:
    """No class declared is the old behaviour, kept (#23)."""
    line = "FAIL nothing_matched expected=3 got=0"
    assert pool_merge.mission_class(line) == ("assertion_failed", line)


def test_a_class_the_table_never_heard_of_is_caught_as_the_harness_bug_it_is() -> None:
    class_, detail = pool_merge.mission_class("FAIL class=timout probe_never_finished")
    assert class_ == "untyped_harness_failure"
    assert "timout" in detail
    assert "FAIL class=timout probe_never_finished" in detail


@pytest.mark.parametrize("smuggled", ["pass", "untyped_harness_failure", "flake_quarantine"])
def test_a_class_no_fail_line_may_claim_is_refused_at_the_boundary(smuggled: str) -> None:
    """A world-claimed class the boundary reserves for the harness is refused.

    `class=pass` would invert the verdict downstream; the other two are the
    harness's and the quarantine header's words, never the world's.
    """
    class_, detail = pool_merge.mission_class(f"FAIL class={smuggled} smuggled")
    assert class_ == "untyped_harness_failure"
    assert smuggled in detail


def test_the_last_class_token_wins_as_the_old_sed_read_it() -> None:
    """The greedy `.*class=` matched the final occurrence; the reader keeps that."""
    line = "FAIL class=timeout detail=class=oracle_disagreement"
    assert pool_merge.mission_class(line) == ("oracle_disagreement", line)


def test_class_of_main_prints_the_lines_the_shell_acts_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = pool_merge.main(["class-of", "--line", "FAIL class=timeout probe_never_finished"])
    assert status == 0
    assert capsys.readouterr().out.splitlines() == [
        "class=timeout",
        "detail=FAIL class=timeout probe_never_finished",
    ]


# ------------------------------------------------------------------ the merge


def claim(  # noqa: PLR0913 — the facts a worker leaves behind, one parameter apiece.
    pool: Path,
    name: str,
    *,
    slot: str = "1",
    verdict: dict | None = None,
    raw: str | None = None,
    done: bool = True,
) -> Path:
    """Stage one claim directory the way a worker leaves it, and return the evidence dir."""
    directory = pool / "claims" / name
    directory.mkdir(parents=True)
    (directory / "slot").write_text(f"{slot}\n", encoding="utf-8")
    out = pool / "runs" / f"20260804T000000Z-{name}"
    out.mkdir(parents=True, exist_ok=True)
    (directory / "evidence").write_text(f"{out}\n", encoding="utf-8")
    if raw is not None:
        (out / "verdict.json").write_text(raw, encoding="utf-8")
    elif verdict is not None:
        (out / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    if done:
        (directory / "done").write_text("done\n", encoding="utf-8")
    return out


def merged(pool: Path, corpus: list[str], **overrides: object) -> Any:  # noqa: ANN401 — a
    # MergedPool, but the module is loaded by path and its types are its own.
    fields: dict[str, object] = {
        "corpus": corpus,
        "claims_dir": pool / "claims",
        "host_probes": frozenset(),
        "client_lock_blocked": False,
        "client_lock_evidence": "",
        "mem_stopped": False,
        **overrides,
    }
    return pool_merge.merge_claims(**fields)


def test_a_verdicts_class_and_elapsed_come_from_its_json(tmp_path: Path) -> None:
    out = claim(tmp_path, "contacts", verdict={"class": "timeout", "elapsed_secs": 97})
    pool = merged(tmp_path, ["contacts"])
    (row,) = pool.rows
    assert row.class_ == "timeout"
    assert row.elapsed_secs == 97
    assert row.slot == "1"
    assert row.evidence == str(out)
    assert pool.worst_class == "timeout"
    assert pool.reclaim_slots == []


def test_a_claim_with_no_verdict_is_a_dead_worker_not_a_result(tmp_path: Path) -> None:
    """ADR-0022: nothing was measured under conditions anyone can interpret."""
    claim(tmp_path, "casualties", slot="2", verdict=None, done=False)
    pool = merged(tmp_path, ["casualties"])
    (row,) = pool.rows
    assert row.class_ == "infra_unavailable"
    assert row.elapsed_secs == 0
    assert pool.worst_class == "infra_unavailable"
    # The merge decides; the shell releases and reclaims (ADR-0049).
    assert pool.reclaim_slots == ["2"]
    assert pool.notices == [
        (
            "slot 2 claimed casualties and wrote no verdict — "
            "the worker died mid-probe; not a result (ADR-0022)"
        )
    ]


def test_a_dead_worker_on_an_unknown_slot_reclaims_nothing(tmp_path: Path) -> None:
    """A slot nobody recorded is not a slot the shell can release."""
    directory = tmp_path / "claims" / "contacts"
    directory.mkdir(parents=True)
    pool = merged(tmp_path, ["contacts"])
    (row,) = pool.rows
    assert row.class_ == "infra_unavailable"
    assert row.slot == "?"
    assert row.evidence == str(directory)
    assert pool.reclaim_slots == []


def test_a_corrupt_verdict_is_a_harness_bug_not_a_crash(tmp_path: Path) -> None:
    """The failure-class table's preamble: an untyped red says fix the harness first."""
    claim(tmp_path, "contacts", raw="{half a document")
    pool = merged(tmp_path, ["contacts"])
    assert pool.rows[0].class_ == "untyped_harness_failure"
    assert pool.rows[0].elapsed_secs == 0


def test_a_verdict_missing_its_class_is_untyped(tmp_path: Path) -> None:
    claim(tmp_path, "contacts", verdict={"verdict": "FAIL"})
    pool = merged(tmp_path, ["contacts"])
    assert pool.rows[0].class_ == "untyped_harness_failure"


def test_an_unclaimed_probe_is_not_run_and_carries_no_class(tmp_path: Path) -> None:
    (tmp_path / "claims").mkdir()
    pool = merged(tmp_path, ["contacts", "bareworld"])
    assert pool.rows == []
    assert pool.not_run == ["contacts", "bareworld"]
    assert pool.worst_class == "pass"


def test_a_lock_blocked_host_probe_is_typed_rather_than_dropped(tmp_path: Path) -> None:
    """#127: `not_run` carries no class, so a silently dropped tail exits green."""
    (tmp_path / "claims").mkdir()
    pool = merged(
        tmp_path,
        ["client-port"],
        host_probes=frozenset({"client-port"}),
        client_lock_blocked=True,
        client_lock_evidence="/state/windows-client.lock.info",
    )
    (row,) = pool.rows
    assert row.class_ == "infra_unavailable"
    assert row.slot == "-"
    assert row.evidence == "/state/windows-client.lock.info"
    assert pool.not_run == []
    assert pool.worst_class == "infra_unavailable"
    assert pool.notices == [
        "client-port never ran: another run held the Windows client; not a result"
    ]


def test_a_lock_blocked_ordinary_probe_is_still_not_run(tmp_path: Path) -> None:
    """The lock is about the one headed client; a parallel probe it kept out is not typed."""
    (tmp_path / "claims").mkdir()
    pool = merged(tmp_path, ["contacts"], client_lock_blocked=True)
    assert pool.not_run == ["contacts"]
    assert pool.worst_class == "pass"


def test_worst_class_ranks_by_severity_not_by_exit_code(tmp_path: Path) -> None:
    """`schema_stale` exits 7 and `infra_unavailable` exits 5; severity says who wins."""
    claim(tmp_path, "schema-stale", verdict={"class": "schema_stale", "elapsed_secs": 1})
    claim(tmp_path, "contacts", verdict={"class": "infra_unavailable", "elapsed_secs": 1})
    pool = merged(tmp_path, ["schema-stale", "contacts"])
    assert pool.worst_class == "infra_unavailable"


def test_mem_stop_overlays_infra_unavailable_on_a_green_pool(tmp_path: Path) -> None:
    """#125: no probe carries the class — none launched — so the pool raises it itself."""
    claim(tmp_path, "contacts", verdict={"class": "pass", "elapsed_secs": 3})
    pool = merged(tmp_path, ["contacts"], mem_stopped=True)
    assert pool.worst_class == "infra_unavailable"


def test_mem_stop_does_not_soften_a_worse_class(tmp_path: Path) -> None:
    claim(tmp_path, "contacts", raw="not json at all")
    pool = merged(tmp_path, ["contacts"], mem_stopped=True)
    assert pool.worst_class == "untyped_harness_failure"


def test_the_merge_reads_what_the_typer_writes(tmp_path: Path) -> None:
    """The two tools share `verdict.json`; a drift between them is pinned here."""
    results = tmp_path / "results.env"
    results.write_text(
        "server_version=2.22.153995\nverdict=FAIL\nfailure_class=oracle_disagreement\n",
        encoding="utf-8",
    )
    out = claim(tmp_path, "contacts")
    assert (
        probe_verdict.main(
            [
                "--probe",
                "contacts",
                "--results",
                str(results),
                "--verdict-json",
                str(out / "verdict.json"),
                "--run-status",
                "1",
                "--window",
                "240",
                "--watchdog",
                "840",
                "--margin",
                "600",
                "--elapsed",
                "97",
                "--stamp",
                "20260804T101112Z",
                "--git-sha",
                SHA,
                "--git-dirty",
                "false",
                "--slot",
                "1",
                "--host",
                "local",
                "--evidence",
                str(out),
            ]
        )
        == 0
    )
    pool = merged(tmp_path, ["contacts"])
    assert pool.rows[0].class_ == "oracle_disagreement"
    assert pool.rows[0].elapsed_secs == 97


# ----------------------------------------------------------------- the CLI


def run_merge(
    pool: Path, capsys: pytest.CaptureFixture[str], corpus: list[str], *extra: str
) -> tuple[int, str, str]:
    """Drive `merge` once; give back the exit status, stdout and stderr."""
    (pool / "claims").mkdir(parents=True, exist_ok=True)
    argv = [
        "merge",
        "--pool-out",
        str(pool),
        "--corpus",
        *corpus,
        "--started-at",
        STARTED,
        "--git-sha",
        SHA,
        "--host",
        "local",
        "--slots",
        "0",
        "1",
        "--wall-secs",
        "61",
        "--peak-mem-used-kb",
        "7100000",
        "--peak-tier-rss-kb",
        "5100000",
        "--peak-pool-rss-kb",
        "4800000",
        "--least-mem-available-kb",
        "3900000",
        *extra,
    ]
    status = pool_merge.main(argv)
    captured = capsys.readouterr()
    return status, captured.out, captured.err


def test_main_writes_the_pool_document_the_suites_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    claim(tmp_path, "contacts", slot="0", verdict={"class": "pass", "elapsed_secs": 42})
    (tmp_path / "stop").write_text("two probes crashed a node (a b)\n", encoding="utf-8")
    status, _, _ = run_merge(
        tmp_path,
        capsys,
        ["contacts", "bareworld"],
        "--dirty-slot",
        "2:survivors still on ports 2602-2606/9101: 31337(arma3server_x64)",
    )
    assert status == 0
    document = json.loads((tmp_path / "pool.json").read_text(encoding="utf-8"))
    assert document["started_at"] == STARTED
    assert document["git_sha"] == SHA
    assert document["slots"] == [0, 1]
    assert document["host"] == "local"
    # The merge's own answer, recorded (#182): contacts passed, and a not_run
    # probe contributes no row, so the worst class here is pass — the field is
    # what the pool pruner believes.
    assert document["worst_class"] == "pass"
    assert document["wall_secs"] == 61
    assert document["peak_mem_used_kb"] == 7100000
    assert document["peak_tier_rss_kb"] == 5100000
    # Both figures, recorded (#182): tier is machine-wide, pool is ours.
    assert document["peak_pool_rss_kb"] == 4800000
    assert document["least_mem_available_kb"] == 3900000
    assert document["stopped_early"] == "two probes crashed a node (a b)"
    assert document["dirty_slots"] == [
        {
            "slot": 2,
            "class": "infra_unavailable",
            "detail": "survivors still on ports 2602-2606/9101: 31337(arma3server_x64)",
        }
    ]
    assert document["not_run"] == ["bareworld"]
    # The slot is a string in `pool.json` — it can be `-` or `?` — and a number
    # in each probe's own `verdict.json`; both suites read them as they are.
    assert document["verdicts"] == [
        {
            "probe": "contacts",
            "class": "pass",
            "slot": "0",
            "elapsed_secs": 42,
            "evidence": str(tmp_path / "runs" / "20260804T000000Z-contacts"),
        }
    ]


def test_a_dirty_details_newlines_flatten_as_json_string_did(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reclaim's survivors arrive one per line; the record is one line, as ever."""
    claim(tmp_path, "contacts", verdict={"class": "pass", "elapsed_secs": 1})
    status, _, _ = run_merge(
        tmp_path, capsys, ["contacts"], "--dirty-slot", "1:31337(a)\n31338(b)\tc"
    )
    assert status == 0
    document = json.loads((tmp_path / "pool.json").read_text(encoding="utf-8"))
    assert document["dirty_slots"][0]["detail"] == "31337(a) 31338(b) c"


def test_main_prints_the_lines_the_shell_acts_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Python home decides, the shell acts: release and reclaim are process seams."""
    claim(tmp_path, "casualties", slot="2", verdict=None, done=False)
    claim(tmp_path, "contacts", slot="0", verdict={"class": "pass", "elapsed_secs": 3})
    status, out, _ = run_merge(tmp_path, capsys, ["contacts", "casualties"])
    assert status == 0
    lines = out.splitlines()
    assert "worst_class=infra_unavailable" in lines
    assert "reclaim_slot=2" in lines


def test_main_renders_the_summary_worst_first_in_the_runners_own_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The stderr the runner has always printed, byte for byte, worst class first."""
    out_pass = claim(tmp_path, "contacts", slot="0", verdict={"class": "pass", "elapsed_secs": 3})
    out_red = claim(
        tmp_path, "bareworld", slot="1", verdict={"class": "timeout", "elapsed_secs": 151}
    )
    status, _, err = run_merge(tmp_path, capsys, ["contacts", "bareworld", "recall"])
    assert status == 0
    assert err.splitlines() == [
        "",
        f"[regress] ==== verdicts ({STARTED}, sha 4ccaed031df0, N=2) ====",
        f"[regress] bareworld            timeout             151s  slot 1  {out_red}",
        f"[regress] contacts             pass                  3s  slot 0  {out_pass}",
        "[regress] 1 probe(s) not run: recall",
    ]


def test_main_logs_the_dead_worker_before_the_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    claim(tmp_path, "casualties", slot="2", verdict=None, done=False)
    _, _, err = run_merge(tmp_path, capsys, ["casualties"])
    assert err.splitlines()[0] == (
        "[regress] slot 2 claimed casualties and wrote no verdict — "
        "the worker died mid-probe; not a result (ADR-0022)"
    )


def test_main_refuses_a_pool_out_with_no_claims_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A merge pointed somewhere the pool never wrote must stop, not report all-not-run.

    The call site fails closed on any non-zero exit (ADR-0049), and this is the
    one wrong invocation that would otherwise read as a quietly green pool.
    """
    argv = [
        "merge",
        "--pool-out",
        str(tmp_path / "absent"),
        "--corpus",
        "contacts",
        "--started-at",
        STARTED,
        "--git-sha",
        SHA,
        "--host",
        "local",
        "--slots",
        "0",
        "--wall-secs",
        "0",
        "--peak-mem-used-kb",
        "0",
        "--peak-tier-rss-kb",
        "0",
        "--peak-pool-rss-kb",
        "0",
        "--least-mem-available-kb",
        "0",
    ]
    assert pool_merge.main(argv) != 0
    assert "claims" in capsys.readouterr().err


# ------------------------------------------------------------- prune-passes


def pass_dir(runs: Path, stamp: str, name: str, verdict: str = "PASS") -> Path:
    directory = runs / f"{stamp}-{name}"
    directory.mkdir(parents=True)
    (directory / "verdict.json").write_text(
        json.dumps({"probe": name, "verdict": verdict, "class": "pass"}, indent=2) + "\n",
        encoding="utf-8",
    )
    return directory


def test_prune_lists_the_oldest_passes_beyond_the_room(tmp_path: Path) -> None:
    """Room is left for the pass the run is about to write, exactly as the grep did."""
    oldest = pass_dir(tmp_path, "20260801T000000Z", "contacts")
    older = pass_dir(tmp_path, "20260802T000000Z", "contacts")
    pass_dir(tmp_path, "20260803T000000Z", "contacts")
    pass_dir(tmp_path, "20260804T000000Z", "contacts")
    doomed = pool_merge.prune_candidates(tmp_path, "contacts", keep=3)
    assert doomed == [oldest, older]


def test_prune_never_lists_a_failure_or_another_probes_pass(tmp_path: Path) -> None:
    """Failures are kept until the issue that consumed them closes."""
    pass_dir(tmp_path, "20260801T000000Z", "contacts", verdict="FAIL")
    pass_dir(tmp_path, "20260801T000001Z", "bareworld")
    pass_dir(tmp_path, "20260801T000002Z", "bareworld")
    pass_dir(tmp_path, "20260801T000003Z", "bareworld")
    pass_dir(tmp_path, "20260801T000004Z", "bareworld")
    assert pool_merge.prune_candidates(tmp_path, "contacts", keep=3) == []


def test_prune_does_not_mistake_a_probe_name_suffix_for_the_probe(tmp_path: Path) -> None:
    """`*-assault` also matched `base-assault`; the evidence's probe is the anchor."""
    for stamp in (
        "20260801T000000Z",
        "20260802T000000Z",
        "20260803T000000Z",
        "20260804T000000Z",
    ):
        pass_dir(tmp_path, stamp, "base-assault")
    assert pool_merge.prune_candidates(tmp_path, "assault", keep=3) == []


def test_prune_only_reads_runs_with_an_anchored_timestamp_prefix(tmp_path: Path) -> None:
    for stamp in (
        "archive-20260801T000000Z",
        "archive-20260802T000000Z",
        "archive-20260803T000000Z",
        "archive-20260804T000000Z",
    ):
        pass_dir(tmp_path, stamp, "contacts")
    assert pool_merge.prune_candidates(tmp_path, "contacts", keep=3) == []


def test_prune_leaves_a_short_history_alone(tmp_path: Path) -> None:
    pass_dir(tmp_path, "20260801T000000Z", "contacts")
    pass_dir(tmp_path, "20260802T000000Z", "contacts")
    assert pool_merge.prune_candidates(tmp_path, "contacts", keep=3) == []


def test_prune_keeps_a_directory_whose_verdict_cannot_be_read(tmp_path: Path) -> None:
    """Deciding on evidence it cannot read is the one thing the pruner must not do."""
    directory = tmp_path / "20260801T000000Z-contacts"
    directory.mkdir(parents=True)
    (directory / "verdict.json").write_text("{torn", encoding="utf-8")
    for stamp in ("20260802T000000Z", "20260803T000000Z", "20260804T000000Z"):
        pass_dir(tmp_path, stamp, "contacts")
    doomed = pool_merge.prune_candidates(tmp_path, "contacts", keep=3)
    assert directory not in doomed
    assert doomed == [tmp_path / "20260802T000000Z-contacts"]


def test_prune_main_prints_one_doomed_directory_per_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oldest = pass_dir(tmp_path, "20260801T000000Z", "contacts")
    for stamp in ("20260802T000000Z", "20260803T000000Z"):
        pass_dir(tmp_path, stamp, "contacts")
    status = pool_merge.main(
        ["prune-passes", "--runs-dir", str(tmp_path), "--probe", "contacts", "--keep", "3"]
    )
    assert status == 0
    assert capsys.readouterr().out.splitlines() == [str(oldest)]


# -------------------------------------------------------- prune-interrupted


def test_interrupted_evidence_is_prunable_only_after_its_horizon(tmp_path: Path) -> None:
    old = tmp_path / "20260701T000000Z-contacts"
    recent = tmp_path / "20260807T000000Z-contacts"
    completed = tmp_path / "20260701T000001Z-bareworld"
    unrelated = tmp_path / "scratch-contacts"
    for directory in (old, recent, completed, unrelated):
        directory.mkdir()
    (completed / "verdict.json").write_text("{}\n", encoding="utf-8")

    now = datetime(2026, 8, 8, tzinfo=UTC)
    assert pool_merge.prune_interrupted_candidates(
        tmp_path, older_than=timedelta(days=7), now=now
    ) == [old]


def test_prune_interrupted_main_prints_one_doomed_directory_per_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = tmp_path / "20000101T000000Z-contacts"
    old.mkdir()
    status = pool_merge.main(
        ["prune-interrupted", "--runs-dir", str(tmp_path), "--older-than-days", "7"]
    )
    assert status == 0
    assert capsys.readouterr().out.splitlines() == [str(old)]


# -------------------------------------------------------------- prune-pools
# Verdict-aware, where the old prune was count-only (#182): the starvation
# episodes' primary RAM traces were pruned while the issues that needed them
# were still open. Only a pool whose own record reads green is a candidate.


def pool_dir(runs: Path, stamp: str, document: object) -> Path:
    directory = runs / f"{stamp}-pool"
    directory.mkdir(parents=True)
    if document is not None:
        text = document if isinstance(document, str) else json.dumps(document, indent=2) + "\n"
        (directory / "pool.json").write_text(text, encoding="utf-8")
    return directory


def test_pool_prune_lists_the_oldest_greens_beyond_the_room(tmp_path: Path) -> None:
    """Room is left for the pool the run is about to record, as prune-passes leaves it."""
    oldest = pool_dir(tmp_path, "20260801T000000Z-1", {"worst_class": "pass"})
    older = pool_dir(tmp_path, "20260801T000001Z-1", {"worst_class": "pass"})
    for stamp in ("20260802T000000Z-1", "20260803T000000Z-1", "20260804T000000Z-1"):
        pool_dir(tmp_path, stamp, {"worst_class": "pass"})
    assert pool_merge.prune_pool_candidates(tmp_path, keep=4) == [oldest, older]
    assert pool_merge.prune_pool_candidates(tmp_path, keep=5) == [oldest]
    assert pool_merge.prune_pool_candidates(tmp_path, keep=6) == []


def test_pool_prune_never_lists_a_pool_an_issue_may_still_need(tmp_path: Path) -> None:
    """A failed pool's RAM trace is the primary record of its episode.

    The recorded worst_class is believed as written — including the mem-stop
    shape, where every verdict is a pass and the pool-level overlay is the
    whole story.
    """
    pool_dir(tmp_path, "20260801T000000Z-1", {"worst_class": "timeout"})
    pool_dir(
        tmp_path,
        "20260801T000001Z-1",
        {"worst_class": "infra_unavailable", "verdicts": [{"class": "pass"}]},
    )
    for stamp in ("20260802T000000Z-1", "20260803T000000Z-1"):
        pool_dir(tmp_path, stamp, {"worst_class": "pass"})
    assert pool_merge.prune_pool_candidates(tmp_path, keep=2) == [
        tmp_path / "20260802T000000Z-1-pool"
    ]


def test_pool_prune_reads_a_legacy_document_off_its_verdicts(tmp_path: Path) -> None:
    """Pools recorded before worst_class existed are judged by what they carry.

    A non-empty stopped_early is not green: those runs' mem-stop overlay lived
    only in the exit code nobody kept.
    """
    green = pool_dir(
        tmp_path,
        "20260801T000000Z-1",
        {"verdicts": [{"class": "pass"}, {"class": "flake_quarantine"}], "stopped_early": ""},
    )
    pool_dir(tmp_path, "20260801T000001Z-1", {"verdicts": [{"class": "timeout"}]})
    pool_dir(
        tmp_path,
        "20260801T000002Z-1",
        {"verdicts": [{"class": "pass"}], "stopped_early": "only 40 MiB available"},
    )
    assert pool_merge.prune_pool_candidates(tmp_path, keep=1) == [green]


def test_pool_prune_keeps_what_it_cannot_read(tmp_path: Path) -> None:
    """A torn pool.json, or a run that died before its merge, is not the pruner's call."""
    pool_dir(tmp_path, "20260801T000000Z-1", "{torn")
    pool_dir(tmp_path, "20260801T000001Z-1", None)
    pool_dir(tmp_path, "20260801T000002Z-1", {"verdicts": []})
    green = pool_dir(tmp_path, "20260801T000003Z-1", {"worst_class": "pass"})
    assert pool_merge.prune_pool_candidates(tmp_path, keep=1) == [green]


def test_pool_prune_main_prints_one_doomed_directory_per_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    oldest = pool_dir(tmp_path, "20260801T000000Z-1", {"worst_class": "pass"})
    pool_dir(tmp_path, "20260801T000001Z-1", {"worst_class": "pass"})
    status = pool_merge.main(["prune-pools", "--runs-dir", str(tmp_path), "--keep", "2"])
    assert status == 0
    assert capsys.readouterr().out.splitlines() == [str(oldest)]


# --------------------------------------------------------- fallback-verdict


def test_fallback_writes_the_least_the_merge_reads(tmp_path: Path) -> None:
    """#171 left this heredoc in bash; it has one writer now, and the merge is its reader."""
    verdict_json = tmp_path / "verdict.json"
    status = pool_merge.main(
        [
            "fallback-verdict",
            "--probe",
            "contacts",
            "--class",
            "untyped_harness_failure",
            "--detail",
            'the verdict typer failed (exit 3) — "harness\\bug"',
            "--elapsed",
            "97",
            "--evidence",
            str(tmp_path),
            "--verdict-json",
            str(verdict_json),
        ]
    )
    assert status == 0
    document = json.loads(verdict_json.read_text(encoding="utf-8"))
    assert document == {
        "probe": "contacts",
        "verdict": "FAIL",
        "class": "untyped_harness_failure",
        "detail": 'the verdict typer failed (exit 3) — "harness\\bug"',
        "elapsed_secs": 97,
        "evidence": str(tmp_path),
    }
    assert pool_merge.read_verdict(verdict_json) == ("untyped_harness_failure", 97)


# ------------------------------------------------------------ stop-decision (#72)
# Two consecutive `node_crashed` verdicts are the tier telling you the crash is
# systemic: one bad `.so`, one broken `CfgFunctions`, and every further bring-up
# is a non-result bought at full price, N slots at a time. The decision is a
# threshold over a run of classes, so it lives here rather than in the shell
# (ADR-0049), and the worker writes the flag it is told.


def _record(tmp_path: Path, *entries: tuple[str, str]) -> Path:
    """Write a completion record the way `regress.sh`'s workers append to it."""
    record = tmp_path / "completions.tsv"
    record.write_text("".join(f"{name}\t{class_}\n" for name, class_ in entries), encoding="utf-8")
    return record


def test_two_consecutive_crashes_trip_the_breaker(tmp_path: Path) -> None:
    record = _record(
        tmp_path,
        ("base-assault", "node_crashed"),
        ("contacts", "node_crashed"),
    )
    trip, stop_line, failure_class = pool_merge.crash_stop(record)
    assert trip is True
    assert failure_class is None
    assert pool_merge.finalize_stop_line(stop_line, 26) == (
        "node_crashed in base-assault, then contacts — abandoned after 2 "
        "consecutive node_crashed, 26 probe(s) not run"
    )


def test_a_verdict_between_two_crashes_restarts_the_run(tmp_path: Path) -> None:
    """`consecutive` is the rule: a world that survives proves the crash is not systemic."""
    trip, stop_line, failure_class = pool_merge.crash_stop(
        _record(
            tmp_path,
            ("base-assault", "node_crashed"),
            ("contacts", "pass"),
            ("massed-assault", "node_crashed"),
        )
    )
    assert trip is False
    assert stop_line == ""
    assert failure_class is None


def test_one_crash_alone_never_trips(tmp_path: Path) -> None:
    trip, _, failure_class = pool_merge.crash_stop(_record(tmp_path, ("contacts", "node_crashed")))
    assert trip is False
    assert failure_class is None


def test_a_longer_run_names_every_crash_it_ran_past(tmp_path: Path) -> None:
    """A decision that answered late still says the whole run, never just the last two.

    The count is the run's own length, so the named probes and the claimed
    number can never disagree (#683).
    """
    trip, stop_line, failure_class = pool_merge.crash_stop(
        _record(
            tmp_path,
            ("a", "node_crashed"),
            ("b", "node_crashed"),
            ("c", "node_crashed"),
        )
    )
    assert trip is True
    assert failure_class is None
    assert (
        stop_line
        == "node_crashed in a, then b, then c — abandoned after 3 consecutive node_crashed"
    )


def test_an_unreadable_record_trips_fail_closed(tmp_path: Path) -> None:
    """The breaker protects the machine; unreadable is stop, with the reason spelled."""
    trip, stop_line, failure_class = pool_merge.crash_stop(tmp_path / "absent.tsv")
    assert trip is True
    assert "no completion record readable" in stop_line
    assert failure_class == "infra_unavailable"


def test_a_corrupt_record_trips_fail_closed(tmp_path: Path) -> None:
    record = tmp_path / "completions.tsv"
    record.write_text("base-assault\nnode_crashed without a name", encoding="utf-8")
    trip, stop_line, failure_class = pool_merge.crash_stop(record)
    assert trip is True
    assert "the completion record is corrupt at line 1" in stop_line
    assert failure_class == "untyped_harness_failure"


# ------------------------------------------------- the stop-decision failures


def test_the_merge_stands_the_worst_candidate_whichever_worker_wrote_first(
    tmp_path: Path,
) -> None:
    """Two racing workers leave two candidates; the worst class stands (#683).

    Completion order is the only order a pool has, so the merge must reach the
    same answer either way round — the race this closes had a delayed
    `infra_unavailable` overwriting an `untyped_harness_failure` already on
    disk.
    """
    failures = tmp_path / "stop-decision-failures"
    failures.mkdir()
    (failures / "early-probe").write_text("infra_unavailable\n", encoding="utf-8")
    (failures / "late-probe").write_text("untyped_harness_failure\n", encoding="utf-8")
    assert pool_merge.read_stop_decision_failures(tmp_path) == "untyped_harness_failure"


def test_the_selection_is_over_severity_never_over_directory_order(
    tmp_path: Path,
) -> None:
    """The same two candidates under the other names give the same answer."""
    failures = tmp_path / "stop-decision-failures"
    failures.mkdir()
    (failures / "early-probe").write_text("untyped_harness_failure\n", encoding="utf-8")
    (failures / "late-probe").write_text("infra_unavailable\n", encoding="utf-8")
    assert pool_merge.read_stop_decision_failures(tmp_path) == "untyped_harness_failure"


def test_a_pool_with_no_stop_decision_failure_reads_none(tmp_path: Path) -> None:
    """No candidates, no overlay — the ordinary pool's shape, empty dir included."""
    assert pool_merge.read_stop_decision_failures(tmp_path) is None
    (tmp_path / "stop-decision-failures").mkdir()
    assert pool_merge.read_stop_decision_failures(tmp_path) is None


def test_an_unreadable_candidate_is_an_untyped_red(tmp_path: Path) -> None:
    """A candidate the merge cannot read or parse stops worse, never silently."""
    failures = tmp_path / "stop-decision-failures"
    failures.mkdir()
    (failures / "probe").write_bytes(b"\xff\xfe not utf-8")
    assert pool_merge.read_stop_decision_failures(tmp_path) == "untyped_harness_failure"
    (failures / "probe").write_text("a class the table has never heard of\n", encoding="utf-8")
    assert pool_merge.read_stop_decision_failures(tmp_path) == "untyped_harness_failure"


def test_the_merge_overlays_the_worst_candidate_onto_worst_class(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An all-pass pool that stopped on an unread decision is still not a result."""
    claim(tmp_path, "contacts", verdict={"class": "pass", "elapsed_secs": 1})
    failures = tmp_path / "stop-decision-failures"
    failures.mkdir()
    (failures / "contacts").write_text("infra_unavailable\n", encoding="utf-8")

    status, _, err = run_merge(tmp_path, capsys, ["contacts"])

    assert status == 0
    document = json.loads((tmp_path / "pool.json").read_text(encoding="utf-8"))
    assert document["worst_class"] == "infra_unavailable"
    assert "the stop decision failed as infra_unavailable" in err


def test_the_subcommand_prints_the_lines_the_shell_acts_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = _record(tmp_path, ("base-assault", "node_crashed"), ("contacts", "node_crashed"))
    assert pool_merge.main(["stop-decision", "--record", str(record)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "trip=yes"
    assert out[1].startswith("stop_line=node_crashed in base-assault, then contacts")


def test_the_subcommand_answers_trip_no_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = _record(tmp_path, ("contacts", "pass"))
    assert pool_merge.main(["stop-decision", "--record", str(record)]) == 0
    assert capsys.readouterr().out.splitlines() == ["trip=no"]


@pytest.mark.parametrize(
    ("record_kind", "expected_class"),
    [
        ("unreadable", "infra_unavailable"),
        ("corrupt", "untyped_harness_failure"),
    ],
)
def test_the_subcommand_names_a_record_failure_for_the_shell(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    record_kind: str,
    expected_class: str,
) -> None:
    record = tmp_path / f"{record_kind}.tsv"
    if record_kind == "corrupt":
        record.write_text("corrupt completion\n", encoding="utf-8")

    assert pool_merge.main(["stop-decision", "--record", str(record)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "trip=yes"
    assert out[1].startswith("stop_line=")
    assert out[2] == f"failure_class={expected_class}"


def test_the_merge_recounts_crash_stop_after_in_flight_survivors_finish(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The final pool record counts not-run probes after workers have drained (#72)."""
    claim(tmp_path, "crash-a", verdict={"class": "node_crashed", "elapsed_secs": 1})
    claim(tmp_path, "crash-b", verdict={"class": "node_crashed", "elapsed_secs": 1})
    claim(tmp_path, "in_flight-pass", verdict={"class": "pass", "elapsed_secs": 1})
    (tmp_path / "stop").write_text(
        "node_crashed in crash-a, then crash-b — abandoned after 2 consecutive node_crashed\n",
        encoding="utf-8",
    )

    status, _, _ = run_merge(
        tmp_path,
        capsys,
        ["crash-a", "crash-b", "in_flight-pass", "not-started"],
    )

    assert status == 0
    document = json.loads((tmp_path / "pool.json").read_text(encoding="utf-8"))
    assert document["not_run"] == ["not-started"]
    assert document["stopped_early"].endswith(", 1 probe(s) not run")
    assert (tmp_path / "stop").read_text(encoding="utf-8").strip() == document["stopped_early"]
