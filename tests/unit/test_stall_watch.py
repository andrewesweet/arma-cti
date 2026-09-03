"""When a dispatched agent has parked on a finished run (#198, ADR-0049).

Six stalls in one cycle were caught by an orchestrator watching by hand, at
about 4.24% of this project's whole token bill (#195). The detection was always
mechanical — a completion artefact exists, no report inside a grace window, the
worktree's HEAD has not moved — so it belongs where a unit test can reach it,
and the shell keeps only the detaching, the polling and the `git`.

What is asserted here is the ladder and the two escalation branches the record
distinguishes: a stall on a clean tree costs a dispatch, a stall on uncommitted
work risks the work (#149's 90 minutes on five addon files). The payload a prod
quotes is asserted against `pool_merge.render_summary` directly, because the
issue's second criterion is that the block is reused rather than re-rendered.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    import pytest

stall_watch = load_tool("stall_watch")
pool_merge = load_tool("pool_merge")

SHA = "8127fab023776a7d856fb0ac958e05bd1e9be3c6"
MOVED = "64e13f4a11119cb51d0c0d4f2b1a9e8d3c7f5a20"
NOW = 1_785_900_000
ARMED = NOW - 3600


def write_pool(
    runs: Path,
    *,
    stamp: str = "20260805T025128Z-3447440-pool",
    worst: str = "pass",
    verdicts: list[dict[str, object]] | None = None,
    finished_at: int = NOW - 1800,
) -> Path:
    """One finished pool run's evidence, mtimed where the test wants it."""
    if verdicts is None:
        verdicts = [
            {
                "probe": "ai-commander",
                "class": "pass",
                "slot": "2",
                "elapsed_secs": 43,
                "evidence": "/runs/20260805T025917Z-ai-commander",
            },
            {
                "probe": "bareworld",
                "class": "pass",
                "slot": "0",
                "elapsed_secs": 25,
                "evidence": "/runs/20260805T030116Z-bareworld",
            },
        ]
    directory = runs / stamp
    directory.mkdir(parents=True, exist_ok=True)
    artefact = directory / "pool.json"
    artefact.write_text(
        json.dumps(
            {
                "started_at": "2026-08-05T02:51:28Z",
                "git_sha": SHA,
                "slots": [0, 1, 2],
                "host": "local",
                "worst_class": worst,
                "wall_secs": 1120,
                "not_run": [],
                "verdicts": verdicts,
            }
        ),
        encoding="utf-8",
    )
    os.utime(artefact, (finished_at, finished_at))
    return directory


def spec(runs: Path, **overrides: object) -> object:
    """Arm a watch an hour ago over a pool, varying only the field under test."""
    fields: dict[str, object] = {
        "name": "issue-198",
        "worktree": "/wt/issue-198",
        "baseline_head": SHA,
        "armed_at": ARMED,
        "subject": "pool",
        "runs_dir": str(runs),
        "grace_secs": 600,
        "deadline_secs": 14400,
        "issue": "#198",
        **overrides,
    }
    return stall_watch.Spec(**fields)


def seen(**overrides: object) -> object:
    """One pass of readings, defaulting to a silent agent on a clean tree."""
    fields: dict[str, object] = {"now": NOW, "head": SHA, **overrides}
    return stall_watch.Observation(**fields)


# --- the predicate's three conjuncts ---------------------------------------


def test_no_completion_artefact_is_not_a_stall(tmp_path: Path) -> None:
    """The first conjunct: a run still going is an agent still working."""
    finding = stall_watch.assess(spec(tmp_path), seen(), {})
    assert finding.state == stall_watch.WATCHING
    assert finding.terminal is False


def test_a_pool_that_finished_before_the_watch_was_armed_is_another_run(tmp_path: Path) -> None:
    write_pool(tmp_path, finished_at=ARMED - 60)
    finding = stall_watch.assess(spec(tmp_path), seen(), {})
    assert finding.state == stall_watch.WATCHING


def test_a_head_that_moves_after_the_edge_is_the_agent_reading_its_own_run(
    tmp_path: Path,
) -> None:
    """The third conjunct: a commit after the run finished means the agent acted."""
    write_pool(tmp_path)
    finding = stall_watch.assess(spec(tmp_path), seen(head=MOVED), {"head_at_edge": SHA})
    assert finding.state == stall_watch.AGENT_MOVED
    assert finding.terminal is True
    assert "the agent read it" in finding.prod


def test_a_head_that_moved_before_the_edge_does_not_excuse_the_silence(tmp_path: Path) -> None:
    """#168's shape: its fix was committed (`e24e25d`) *before* the run it parked on.

    Measuring the conjunct from arming would have read that stall as an agent
    who had read its own run, which is exactly the stall the watcher exists to
    catch — twice in one evening, at the identical point.
    """
    write_pool(tmp_path, finished_at=NOW - 900)
    finding = stall_watch.assess(spec(tmp_path), seen(head=MOVED), {"head_at_edge": MOVED})
    assert finding.state == stall_watch.STALLED_CLEAN
    assert finding.terminal is True
    assert f"HEAD {MOVED[:12]} is committed" in finding.prod


def test_the_first_pass_after_the_edge_settles_rather_than_guessing(tmp_path: Path) -> None:
    """Nothing on that pass can say whether the move came before the edge or after."""
    write_pool(tmp_path, finished_at=NOW - 900)
    finding = stall_watch.assess(spec(tmp_path), seen(head=MOVED), {})
    assert finding.state == stall_watch.SETTLING


def test_the_head_at_the_edge_is_recorded_for_the_next_pass_to_measure_against(
    tmp_path: Path,
) -> None:
    write_pool(tmp_path, finished_at=NOW - 900)
    watched, observed = spec(tmp_path), seen(head=MOVED)
    finding = stall_watch.assess(watched, observed, {})
    document = stall_watch.finding_document(watched, observed, finding, {})
    assert document["head_at_edge"] == MOVED
    # And it is not invented before the edge lands.
    bare = stall_watch.assess(spec(tmp_path, runs_dir=str(tmp_path / "empty")), observed, {})
    assert stall_watch.finding_document(watched, observed, bare, {})["head_at_edge"] == ""


def test_silence_inside_the_grace_window_is_not_yet_a_stall(tmp_path: Path) -> None:
    """The boundary, below: a finished corpus takes reading and landing."""
    write_pool(tmp_path, finished_at=NOW - 599)
    finding = stall_watch.assess(spec(tmp_path), seen(), {})
    assert finding.state == stall_watch.SETTLING
    assert finding.terminal is False


def test_silence_at_the_grace_window_is_a_stall(tmp_path: Path) -> None:
    """The boundary, at: the second conjunct fires exactly on the stated grace."""
    write_pool(tmp_path, finished_at=NOW - 600)
    finding = stall_watch.assess(spec(tmp_path), seen(), {})
    assert finding.state == stall_watch.STALLED_CLEAN
    assert finding.terminal is True


def test_activity_after_the_edge_restarts_the_quiet_clock(tmp_path: Path) -> None:
    """An agent still editing after its run finished is working, not parked."""
    write_pool(tmp_path, finished_at=NOW - 1800)
    finding = stall_watch.assess(spec(tmp_path), seen(activity_epoch=NOW - 30), {})
    assert finding.state == stall_watch.SETTLING
    assert finding.quiet_secs == 30


def test_activity_before_the_edge_does_not_excuse_the_silence(tmp_path: Path) -> None:
    write_pool(tmp_path, finished_at=NOW - 900)
    finding = stall_watch.assess(spec(tmp_path), seen(activity_epoch=NOW - 3000), {})
    assert finding.state == stall_watch.STALLED_CLEAN
    assert finding.quiet_secs == 900


# --- the two escalation branches -------------------------------------------


def test_a_stall_on_a_clean_tree_costs_a_dispatch_and_says_so(tmp_path: Path) -> None:
    write_pool(tmp_path, finished_at=NOW - 900)
    finding = stall_watch.assess(spec(tmp_path), seen(), {})
    assert finding.state == stall_watch.STALLED_CLEAN
    assert "nothing of yours is at risk" in finding.prod
    assert "lost dispatch, not lost work" in finding.prod
    assert "tree=clean@" in finding.headline


def test_a_stall_on_uncommitted_work_names_the_files_and_orders_the_commit(
    tmp_path: Path,
) -> None:
    """#149's shape: 90 minutes silent on five uncommitted addon files."""
    write_pool(tmp_path, finished_at=NOW - 5400)
    dirty = (
        "addons/main/functions/fn_reinforce.sqf",
        "addons/main/functions/fn_muster.sqf",
        "addons/main/XEH_preInit.sqf",
        "addons/main/config.cpp",
        "addons/main/manifests/stratis.json",
    )
    finding = stall_watch.assess(spec(tmp_path, armed_at=NOW - 7200), seen(dirty=dirty), {})
    assert finding.state == stall_watch.STALLED_DIRTY
    assert finding.terminal is True
    assert "5 path(s) uncommitted" in finding.prod
    assert "fn_reinforce.sqf" in finding.prod
    assert "Commit first" in finding.prod
    assert "#149" in finding.prod
    assert "tree=dirty(5)@" in finding.headline


def test_a_long_dirty_list_is_summarised_rather_than_dumped(tmp_path: Path) -> None:
    write_pool(tmp_path, finished_at=NOW - 5400)
    dirty = tuple(f"src/cti_daemon/mod{index}.py" for index in range(9))
    finding = stall_watch.assess(spec(tmp_path, armed_at=NOW - 7200), seen(dirty=dirty), {})
    assert "(+4 more)" in finding.prod
    assert finding.prod.count("mod") == stall_watch.DIRTY_NAMES_SHOWN


# --- the classes the watcher must not act on --------------------------------


def test_an_infra_unavailable_pool_is_reported_as_a_stop(tmp_path: Path) -> None:
    """The failure-class table: not a result, do not interpret, do not retry."""
    write_pool(
        tmp_path,
        worst="infra_unavailable",
        verdicts=[{"probe": "bareworld", "class": "infra_unavailable", "slot": "0"}],
        finished_at=NOW - 900,
    )
    finding = stall_watch.assess(spec(tmp_path), seen(), {})
    assert finding.state == stall_watch.STALLED_CLEAN
    assert finding.prod.startswith("STOP")
    assert "not a result" in finding.prod
    assert "do not retry" in finding.prod
    assert "Re-dispatch is a judgement" in finding.prod


def test_an_unreadable_worktree_is_blind_not_alive(tmp_path: Path) -> None:
    """recovery.md's fail-closed rule: could-not-observe is never still-running."""
    write_pool(tmp_path, finished_at=NOW - 900)
    finding = stall_watch.assess(spec(tmp_path), seen(head=""), {})
    assert finding.state == stall_watch.WATCH_BLIND
    assert finding.terminal is True
    assert "could not observe" in finding.prod


def test_a_run_that_never_produced_an_artefact_expires_rather_than_watching_forever(
    tmp_path: Path,
) -> None:
    finding = stall_watch.assess(spec(tmp_path, deadline_secs=1800), seen(), {})
    assert finding.state == stall_watch.WATCH_EXPIRED
    assert finding.terminal is True
    assert "may never have started" in finding.prod


def test_a_pool_with_no_class_at_all_is_an_untyped_red(tmp_path: Path) -> None:
    """The table's preamble as a row (ADR-0050): a class nobody typed is worst."""
    directory = tmp_path / "20260805T000000Z-1-pool"
    directory.mkdir(parents=True)
    (directory / "pool.json").write_text("{ truncated", encoding="utf-8")
    os.utime(directory / "pool.json", (NOW - 900, NOW - 900))
    finding = stall_watch.assess(spec(tmp_path), seen(), {})
    assert finding.completion is not None
    assert finding.completion.class_ == "untyped_harness_failure"


# --- the payload the prod quotes -------------------------------------------


def test_the_summary_block_is_the_runners_own_rendering(tmp_path: Path) -> None:
    """#198 criterion 2: reuse `render_summary`, never re-render the verdicts."""
    write_pool(tmp_path, finished_at=NOW - 900)
    finding = stall_watch.assess(spec(tmp_path), seen(), {})
    expected = pool_merge.render_summary(
        pool_merge.MergedPool(
            [
                pool_merge.ProbeRow(
                    "ai-commander", "pass", "2", 43, "/runs/20260805T025917Z-ai-commander"
                ),
                pool_merge.ProbeRow(
                    "bareworld", "pass", "0", 25, "/runs/20260805T030116Z-bareworld"
                ),
            ],
            [],
            [],
            [],
            "pass",
        ),
        started_at="2026-08-05T02:51:28Z",
        git_sha=SHA,
        slot_count=3,
    )
    assert finding.completion is not None
    assert list(finding.completion.summary) == [line for line in expected if line]


def test_the_one_line_carries_who_what_and_the_prod(tmp_path: Path) -> None:
    directory = write_pool(tmp_path, finished_at=NOW - 900)
    finding = stall_watch.assess(spec(tmp_path), seen(), {})
    assert finding.headline.startswith("STALL issue-198 #198 quiet 15m past pool ")
    assert "worst=pass, 2/2 pass, 1120s, sha 8127fab02377" in finding.headline
    assert f"evidence={directory}" in finding.headline
    assert " prod: " in finding.headline
    assert "\n" not in finding.headline


# --- the other completion edges --------------------------------------------


def test_a_probe_run_completes_the_watch(tmp_path: Path) -> None:
    directory = tmp_path / "20260805T030116Z-bareworld"
    directory.mkdir(parents=True)
    (directory / "verdict.json").write_text(
        json.dumps(
            {
                "probe": "bareworld",
                "class": "timeout",
                "slot": 0,
                "elapsed_secs": 150,
                "git_sha": SHA,
                "started_at": "2026-08-05T03:01:16Z",
            }
        ),
        encoding="utf-8",
    )
    os.utime(directory / "verdict.json", (NOW - 900, NOW - 900))
    finding = stall_watch.assess(spec(tmp_path, subject="probe:bareworld"), seen(), {})
    assert finding.state == stall_watch.STALLED_CLEAN
    assert finding.completion is not None
    assert finding.completion.class_ == "timeout"
    assert "worst=timeout, 0/1 pass, 150s" in finding.headline


def test_a_watched_process_completes_when_it_is_gone(tmp_path: Path) -> None:
    """#168's shape, twice in one evening: background `just unit`, run finished."""
    subject = spec(tmp_path, subject="process", pid=4242, grace_secs=300)
    still = stall_watch.assess(subject, seen(process_alive="true"), {})
    assert still.state == stall_watch.WATCHING
    gone = stall_watch.assess(subject, seen(process_alive="false"), {})
    assert gone.state == stall_watch.SETTLING


def test_the_moment_a_process_was_first_seen_gone_is_kept(tmp_path: Path) -> None:
    """Otherwise the quiet clock resets on every pass and never reaches the grace."""
    subject = spec(tmp_path, subject="process", pid=4242, grace_secs=300)
    finding = stall_watch.assess(subject, seen(process_alive="false"), {"completed_at": NOW - 400})
    assert finding.state == stall_watch.STALLED_CLEAN
    assert finding.quiet_secs == 400


def test_an_unknown_process_state_is_never_read_as_finished(tmp_path: Path) -> None:
    subject = spec(tmp_path, subject="process", pid=4242)
    finding = stall_watch.assess(subject, seen(process_alive="unknown"), {})
    assert finding.state == stall_watch.WATCHING


def test_an_awaited_path_completes_the_watch(tmp_path: Path) -> None:
    flag = tmp_path / "done.flag"
    subject = spec(tmp_path, subject="path", await_path=str(flag), grace_secs=60)
    assert stall_watch.assess(subject, seen(), {}).state == stall_watch.WATCHING
    flag.write_text("", encoding="utf-8")
    os.utime(flag, (NOW - 900, NOW - 900))
    assert stall_watch.assess(subject, seen(), {}).state == stall_watch.STALLED_CLEAN


# --- the shell's readings ---------------------------------------------------


def test_porcelain_paths_are_read_off_the_two_status_columns(tmp_path: Path) -> None:
    path = tmp_path / "porcelain"
    path.write_text(
        " M addons/main/config.cpp\n"
        "?? spike/probes/new.sqf\n"
        'R  "old name.md" -> docs/new-name.md\n'
        "A  src/cti_daemon/planner.py\n",
        encoding="utf-8",
    )
    assert stall_watch.read_porcelain(path) == (
        "addons/main/config.cpp",
        "spike/probes/new.sqf",
        "docs/new-name.md",
        "src/cti_daemon/planner.py",
    )


def test_an_absent_porcelain_file_is_a_clean_tree(tmp_path: Path) -> None:
    assert stall_watch.read_porcelain(tmp_path / "nothing") == ()
    assert stall_watch.read_porcelain(None) == ()


def test_a_duration_reads_the_way_a_human_scanning_one_line_wants_it() -> None:
    assert stall_watch.human_secs(45) == "45s"
    assert stall_watch.human_secs(900) == "15m"
    assert stall_watch.human_secs(5400) == "1h30m"


def test_a_watch_name_becomes_a_filename() -> None:
    assert stall_watch.slug("#198 cti-implementer") == "198-cti-implementer"
    assert stall_watch.slug("///") == "watch"


# --- the CLI the shell and the orchestrator drive ---------------------------


def arm(watch_dir: Path, runs: Path, worktree: Path, **extra: str) -> int:
    """Arm one watch through the CLI, the way `stall-watch.sh` does."""
    return stall_watch.main(
        [
            "--watch-dir",
            str(watch_dir),
            "--now",
            str(ARMED),
            "arm",
            "--name",
            "issue-198",
            "--worktree",
            str(worktree),
            "--baseline-head",
            SHA,
            "--runs-dir",
            str(runs),
            "--issue",
            "#198",
            *[token for pair in extra.items() for token in (f"--{pair[0]}", pair[1])],
        ]
    )


def test_the_cli_arms_assesses_reports_and_acknowledges(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole path the orchestrator uses, and it reports each finding once."""
    watch_dir, runs, worktree = tmp_path / "watch", tmp_path / "runs", tmp_path / "wt"
    worktree.mkdir()
    assert arm(watch_dir, runs, worktree) == 0
    capsys.readouterr()

    # Nothing has finished, so there is nothing to report.
    assert stall_watch.main(["--watch-dir", str(watch_dir), "--now", str(NOW), "report"]) == 0
    assert capsys.readouterr().out == ""

    write_pool(runs, finished_at=NOW - 900)
    assert (
        stall_watch.main(
            [
                "--watch-dir",
                str(watch_dir),
                "--now",
                str(NOW),
                "assess",
                "--name",
                "issue-198",
                "--head",
                SHA,
            ]
        )
        == 0
    )
    lines = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines() if "=" in line)
    assert lines["state"] == "stalled_clean"
    assert lines["terminal"] == "true"

    assert (
        stall_watch.main(["--watch-dir", str(watch_dir), "--now", str(NOW), "report", "--ack"]) == 0
    )
    assert capsys.readouterr().out.startswith("STALL issue-198 #198")

    # Read once: an acknowledged finding never resurfaces as news.
    stall_watch.main(["--watch-dir", str(watch_dir), "--now", str(NOW), "report"])
    assert capsys.readouterr().out == ""
    stall_watch.main(["--watch-dir", str(watch_dir), "--now", str(NOW), "report", "--all"])
    assert "STALL issue-198" in capsys.readouterr().out


def test_arming_clears_the_previous_watchs_finding(tmp_path: Path) -> None:
    """A re-dispatch must not inherit the stall its predecessor was prodded for."""
    watch_dir, runs, worktree = tmp_path / "watch", tmp_path / "runs", tmp_path / "wt"
    worktree.mkdir()
    arm(watch_dir, runs, worktree)
    finding = stall_watch.finding_path(watch_dir, "issue-198")
    finding.write_text('{"state": "stalled_clean", "terminal": true}\n', encoding="utf-8")
    arm(watch_dir, runs, worktree)
    assert not finding.exists()


def test_the_shell_is_handed_the_spec_fields_it_takes_readings_with(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    watch_dir, runs, worktree = tmp_path / "watch", tmp_path / "runs", tmp_path / "wt"
    worktree.mkdir()
    arm(watch_dir, runs, worktree)
    capsys.readouterr()
    assert stall_watch.main(["--watch-dir", str(watch_dir), "spec-env", "--name", "issue-198"]) == 0
    lines = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines() if "=" in line)
    assert lines["worktree"] == str(worktree.resolve())
    assert lines["subject"] == "pool"
    assert lines["finding"].endswith("issue-198.finding.json")


def test_a_verb_against_a_watch_that_does_not_exist_fails_rather_than_passing(
    tmp_path: Path,
) -> None:
    """A check that could not run is not a check that passed (#41)."""
    assert stall_watch.main(["--watch-dir", str(tmp_path), "assess", "--name", "nobody"]) == 1
    assert stall_watch.main(["--watch-dir", str(tmp_path), "spec-env", "--name", "nobody"]) == 1
    assert stall_watch.main(["--watch-dir", str(tmp_path), "ack", "--name", "nobody"]) == 1


def test_the_finding_file_carries_the_evidence_the_prod_quotes(tmp_path: Path) -> None:
    watch_dir, runs, worktree = tmp_path / "watch", tmp_path / "runs", tmp_path / "wt"
    worktree.mkdir()
    arm(watch_dir, runs, worktree)
    directory = write_pool(runs, finished_at=NOW - 900)
    stall_watch.main(
        [
            "--watch-dir",
            str(watch_dir),
            "--now",
            str(NOW),
            "assess",
            "--name",
            "issue-198",
            "--head",
            SHA,
        ]
    )
    document = json.loads(
        stall_watch.finding_path(watch_dir, "issue-198").read_text(encoding="utf-8")
    )
    assert document["state"] == "stalled_clean"
    assert document["evidence"] == str(directory)
    assert document["run_class"] == "pass"
    assert document["baseline_head"] == SHA
    assert document["issue"] == "#198"
    assert any("ai-commander" in line for line in document["summary"])


# --- the process seam, driven for real --------------------------------------
#
# ADR-0049 keeps the shell only where the shell is the subject, and says a test
# of that code is a test of the shell's behaviour — so these drive
# `tools/stall-watch.sh` itself rather than a stand-in. `loop` is run in the
# foreground with a grace of zero, which makes its first pass terminal: the
# whole seam is exercised (spec read-back, `git`, porcelain, the bounded
# `uv run`, the terminal exit) without the test waiting on anything.

SEAM = REPO / "tools" / "stall-watch.sh"
# Resolved once so the calls below name an absolute executable, which is what
# `git` on a bare PATH would not be.
GIT = shutil.which("git") or "git"


def git(repo: Path, *argv: str) -> str:
    """Run one git command in a scratch repo and hand back what it printed."""
    return subprocess.run(  # noqa: S603
        [GIT, "-C", str(repo), *argv], check=True, capture_output=True, text=True
    ).stdout.strip()


def a_repo_with_one_commit(path: Path) -> str:
    """Build a worktree the watcher can read a HEAD out of."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "watcher@example.invalid")
    git(path, "config", "user.name", "Watcher")
    (path / "README.md").write_text("work\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "chore: start")
    return git(path, "rev-parse", "HEAD")


def seam(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run one invocation of the real script, bounded so a hang is a red."""
    return subprocess.run(  # noqa: S603
        [str(SEAM), *argv],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env=None if env is None else {**os.environ, **env},
    )


def test_the_seam_arms_a_detached_watch_and_returns_at_once(tmp_path: Path) -> None:
    """The whole point: arming must not hold the arming turn open."""
    worktree, watch_dir = tmp_path / "wt", tmp_path / "watch"
    a_repo_with_one_commit(worktree)
    started = time.monotonic()
    result = seam(
        "arm",
        "--name",
        "seam-detach",
        "--worktree",
        str(worktree),
        "--watch-dir",
        str(watch_dir),
        "--subject",
        "path",
        "--await-path",
        str(tmp_path / "never"),
        "--deadline",
        "1",
        "--interval",
        "1",
        "--runs-dir",
        str(tmp_path / "runs"),
    )
    assert result.returncode == 0, result.stderr
    assert time.monotonic() - started < 30
    emitted = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert Path(emitted["spec"]).exists()
    assert emitted["watcher_pid"].isdigit()


def test_the_seam_refuses_a_worktree_it_cannot_read_a_head_from(tmp_path: Path) -> None:
    """A watch blind from its first pass is not a watch worth arming."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    result = seam("arm", "--name", "seam-blind", "--worktree", str(plain))
    assert result.returncode == 2
    assert "cannot read HEAD" in result.stderr


def test_the_seam_reads_the_worktree_and_types_the_stall_itself(tmp_path: Path) -> None:
    """One foreground pass over a real dirty worktree, end to end.

    quarantined: #428 tests/unit/test_stall_watch.py::test_stall_watch —
    one observed red (the loop's stdout was not the STALL
    line) in a full `just fast`, and never reproduced: 455 runs of the exact
    arrangement under the gate's own `-n auto` load, 0 reds. The mechanism the
    marker serves is the flake list a `just brief` derives from open issues and
    from these markers, so a dispatched reader quotes this issue for its one
    sanctioned retry even after the issue has closed. Remove
    the marker when a reproduction exists and the synchronisation is fixed, or
    when the arrangement is made deterministic by construction.
    """
    worktree, watch_dir, runs = tmp_path / "wt", tmp_path / "watch", tmp_path / "runs"
    head = a_repo_with_one_commit(worktree)
    (worktree / "addons").mkdir()
    (worktree / "addons" / "fn_muster.sqf").write_text("// uncommitted\n", encoding="utf-8")

    armed = seam(
        "arm",
        "--name",
        "seam-stall",
        "--worktree",
        str(worktree),
        "--watch-dir",
        str(watch_dir),
        "--runs-dir",
        str(runs),
        "--grace",
        "0",
        # A bound, not a wait: if the pool below is somehow not seen, the loop
        # expires rather than becoming the poll loop this issue removes.
        "--deadline",
        "45",
        "--interval",
        "1",
        "--issue",
        "#198",
    )
    assert armed.returncode == 0, armed.stderr
    write_pool(runs, finished_at=int(time.time()))

    looped = seam("loop", "--name", "seam-stall", "--watch-dir", str(watch_dir), "--interval", "1")
    assert looped.returncode == 0, looped.stderr
    assert looped.stdout.startswith("STALL seam-stall #198"), looped.stdout

    document = json.loads(
        stall_watch.finding_path(watch_dir, "seam-stall").read_text(encoding="utf-8")
    )
    assert document["state"] == "stalled_dirty"
    assert document["dirty"] == ["addons/fn_muster.sqf"]
    assert document["head"] == head
    assert document["terminal"] is True


def test_an_issue_reference_survives_a_recipe_body_that_cannot_carry_a_hash() -> None:
    """`--issue 198`, because `#` opens a comment in a `just` recipe's shell."""
    assert stall_watch.issue_ref("198") == "#198"
    assert stall_watch.issue_ref("#198") == "#198"
    assert stall_watch.issue_ref("") == ""


def test_the_seam_names_the_option_whose_value_went_missing(tmp_path: Path) -> None:
    """`set -u`'s "$2: unbound variable" is an error nobody can act on."""
    worktree = tmp_path / "wt"
    a_repo_with_one_commit(worktree)
    result = seam("arm", "--name", "seam-argless", "--worktree", str(worktree), "--issue")
    assert result.returncode == 2
    assert "--issue takes a value" in result.stderr


# --- the injectable watch tree (#249) ---------------------------------------
#
# `just watch-report` folds two reads into one recipe and forwards its arguments
# to the watchers' half only, so a caller who wants the *other* half pointed
# somewhere else has no flag to reach for. `CTI_BREAKER_DIR` is why the breaker
# half already had a seam; `CTI_WATCH_DIR` is this half's twin of it. Without
# one, the unit test of that recipe read the box's live `~/.arma-cti/watch/` and
# went red on two `watch_broken` findings a docs-only diff had not caused.


def test_the_watch_directory_is_injectable_by_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seam the recipe's caller has, since the recipe forwards it no flag."""
    injected = tmp_path / "watch"
    monkeypatch.setenv("CTI_WATCH_DIR", str(injected))
    assert stall_watch.parse_args(["report"]).watch_dir == injected

    # An explicit flag still wins: the environment is the fallback, not an override.
    elsewhere = tmp_path / "elsewhere"
    parsed = stall_watch.parse_args(["--watch-dir", str(elsewhere), "report"])
    assert parsed.watch_dir == elsewhere

    monkeypatch.delenv("CTI_WATCH_DIR")
    assert stall_watch.parse_args(["report"]).watch_dir == stall_watch.DEFAULT_WATCH_DIR


def test_the_environment_alone_steers_the_read_the_recipe_makes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No flag anywhere, exactly as `just watch-report` invokes it — and it still lands."""
    watch_dir, runs, worktree = tmp_path / "watch", tmp_path / "runs", tmp_path / "wt"
    worktree.mkdir()
    arm(watch_dir, runs, worktree)
    write_pool(runs, finished_at=NOW - 900)
    stall_watch.main(
        [
            "--watch-dir",
            str(watch_dir),
            "--now",
            str(NOW),
            "assess",
            "--name",
            "issue-198",
            "--head",
            SHA,
        ]
    )
    capsys.readouterr()

    monkeypatch.setenv("CTI_WATCH_DIR", str(watch_dir))
    assert stall_watch.main(["--now", str(NOW), "report"]) == 0
    assert capsys.readouterr().out.startswith("STALL issue-198 #198")

    # And an injected tree with nothing in it reports nothing — the assertion the
    # leaking test was making, now about a tree the test owns.
    monkeypatch.setenv("CTI_WATCH_DIR", str(tmp_path / "empty"))
    assert stall_watch.main(["--now", str(NOW), "report"]) == 0
    assert capsys.readouterr().out == ""


def test_the_shell_half_honours_the_same_environment_seam(tmp_path: Path) -> None:
    """Both halves or neither: a read moved without the write is the leak relocated."""
    worktree, watch_dir = tmp_path / "wt", tmp_path / "watch"
    a_repo_with_one_commit(worktree)
    result = seam(
        "arm",
        "--name",
        "seam-injected",
        "--worktree",
        str(worktree),
        "--subject",
        "path",
        "--await-path",
        str(tmp_path / "never"),
        "--deadline",
        "1",
        "--interval",
        "1",
        "--runs-dir",
        str(tmp_path / "runs"),
        env={"CTI_WATCH_DIR": str(watch_dir)},
    )
    assert result.returncode == 0, result.stderr
    assert stall_watch.spec_path(watch_dir, "seam-injected").exists()
    emitted = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert Path(emitted["spec"]).parent == watch_dir


def test_no_unit_test_reads_the_boxs_own_watch_tree() -> None:
    """The tripwire beside #132's, one tree over: the no-Arma tier owns no host state.

    #132's version guards the machine-wide locks; this one guards the watchers'
    findings, and the failure it catches is the same shape — a unit gate whose
    verdict depends on what the box happens to be carrying rather than on the diff
    under test. `--watch-dir` or `CTI_WATCH_DIR` is what moves the read into a
    `tmp_path`; a driver with neither reads `~/.arma-cti/watch/` for real, so every
    landing on this box reds until somebody acknowledges an unrelated finding, which
    is state mutation a unit gate must never require (#249).

    An assignment or an argv token, never a bare mention: #132's first draft was
    satisfied by a comment naming the variable and stayed green with its own fix
    deleted.
    """
    drivers = ('"watch-report"', "stall_watch.main(", "stall-watch.sh")
    injected = re.compile(r"""(CTI_WATCH_DIR["'\]]*\s*[=:])|(["']--watch-dir["'])""")
    offenders = [
        path.name
        for path in sorted(Path(__file__).parent.glob("test_*.py"))
        for text in [path.read_text(encoding="utf-8")]
        if any(driver in text for driver in drivers) and not injected.search(text)
    ]
    assert not offenders, (
        f"{offenders} drive the watch tooling without injecting a watch directory, so they "
        "read ~/.arma-cti/watch/ for real and red on findings no diff of theirs caused"
    )


def test_a_completion_with_no_verdict_is_not_described_as_one(tmp_path: Path) -> None:
    """A process exit carries no class, tally or SHA — so the line claims none."""
    subject = spec(tmp_path, subject="process", pid=4242, grace_secs=300)
    finding = stall_watch.assess(subject, seen(process_alive="false"), {"completed_at": NOW - 400})
    assert "past process pid 4242 " in finding.headline
    assert "worst=" not in finding.headline
    assert "the process you were waiting on finished (pid 4242)" in finding.prod
    assert "pick the work back up" in finding.prod
