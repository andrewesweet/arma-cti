"""The Remote Control crash read, in its one home.

`tools/rc_health.py` exists because a bridge that cannot refresh a session's
token kills that session and tells nobody: the transcript stops, telemetry goes
quiet at the last completed turn with no error event, and the only record is
three lines in a tmux pane whose scrollback a reconnect storm evicts in seconds.
On 2026-08-12 the gap between the death (07:13) and its discovery (22:44) was
fifteen hours; two earlier instances were never noticed at all.

What is pinned here is what a reader gets from that record: the crash surfaces
once and then stops surfacing, a lone refresh warning does not read as a lost
session, a crash arriving after an acknowledged warning is **not** pre-silenced,
and the resume command is derived rather than typed — including the case where
the transcript cannot be found, which is said out loud rather than dropped.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

rc_health = load_tool("rc_health")

SESSION = "cse_01Czi2G6JHvdRZxNPymhnmCr"
SERVER = "claude-rc-arma-cti"
WORKTREE = "/home/andre/code/github.com/andrewesweet/arma-cti/.claude/worktrees/bridge-" + SESSION
CRASH_AT = 1786515210  # 2026-08-12T07:13:30+01:00, the incident this module answers


def seen(kind: str, *, at: int, worktree: str = WORKTREE) -> rc_health.Marker:
    """One thing the wrapper saw, as it hands it over."""
    return rc_health.Marker(
        session=SESSION,
        server=SERVER,
        kind=kind,
        detail="Session failed: Process exited with error",
        worktree=worktree,
        detected_at=at,
        acknowledged_at=0,
    )


def crash(directory: Path, *, at: int = CRASH_AT, worktree: str = WORKTREE) -> rc_health.Marker:
    """Record the crash of the incident."""
    return rc_health.record(directory, seen(rc_health.KIND_CRASHED, at=at, worktree=worktree))


def warn(directory: Path, *, at: int = CRASH_AT - 312) -> rc_health.Marker:
    """Record the refresh warning that preceded the incident's crash by 5m 12s."""
    return rc_health.record(directory, seen(rc_health.KIND_REFRESH_FAILED, at=at))


# ------------------------------------------------------- the project-dir mapping


def test_project_dir_name_folds_every_non_alphanumeric_character() -> None:
    """`/`, `.` and `_` all become hyphens — the rule, not three special cases."""
    assert rc_health.project_dir_name(WORKTREE) == (
        "-home-andre-code-github-com-andrewesweet-arma-cti"
        "--claude-worktrees-bridge-cse-01Czi2G6JHvdRZxNPymhnmCr"
    )


def test_project_dir_name_doubles_the_hyphen_before_a_dot_directory() -> None:
    """The `/.` pair is two characters, so it is two hyphens, not one."""
    assert rc_health.project_dir_name("/a/.claude/b") == "-a--claude-b"


# ------------------------------------------------------------ the resume command


def test_resume_names_the_newest_transcript_in_the_project_directory(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    directory = projects / rc_health.project_dir_name(WORKTREE)
    directory.mkdir(parents=True)
    older = directory / "11111111-1111-1111-1111-111111111111.jsonl"
    newer = directory / "30c63ade-de7f-4269-890d-b4ecdb5c53ac.jsonl"
    older.write_text("{}\n", encoding="utf-8")
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    assert rc_health.resume_command(WORKTREE, projects) == (
        "claude --resume 30c63ade-de7f-4269-890d-b4ecdb5c53ac"
    )


def test_resume_says_so_when_no_transcript_can_be_found(tmp_path: Path) -> None:
    """Silence would read as nothing to do; the worktree is stranded either way."""
    answer = rc_health.resume_command(WORKTREE, tmp_path)
    assert "resume by hand" in answer
    assert rc_health.project_dir_name(WORKTREE) in answer


# ------------------------------------------------------------------- the record


def test_a_crash_is_reported_once_and_then_stays_quiet(tmp_path: Path) -> None:
    crash(tmp_path)
    (first,) = rc_health.unread(tmp_path, include_read=False)
    assert first.kind == rc_health.KIND_CRASHED

    rc_health.write_marker(tmp_path, first._replace(acknowledged_at=CRASH_AT + 60))
    assert rc_health.unread(tmp_path, include_read=False) == ()
    assert len(rc_health.unread(tmp_path, include_read=True)) == 1


def test_a_refresh_warning_does_not_claim_the_session_died(tmp_path: Path) -> None:
    warn(tmp_path)
    (marker,) = rc_health.unread(tmp_path, include_read=False)
    line = rc_health.headline(marker, tmp_path)
    assert line.startswith("RC-WARN ")
    assert "still alive" in line


def test_a_crash_after_an_acknowledged_warning_still_surfaces(tmp_path: Path) -> None:
    """The 07:08 warning read and dismissed must not pre-silence the 07:13 loss."""
    warned = warn(tmp_path)
    rc_health.write_marker(tmp_path, warned._replace(acknowledged_at=CRASH_AT - 300))

    crash(tmp_path)
    (marker,) = rc_health.unread(tmp_path, include_read=False)
    assert marker.kind == rc_health.KIND_CRASHED
    assert marker.acknowledged_at == 0


def test_a_late_warning_never_downgrades_a_recorded_crash(tmp_path: Path) -> None:
    """Pane lines are read in batches; the older news must not win on arrival."""
    crash(tmp_path)
    warn(tmp_path, at=CRASH_AT + 5)
    (marker,) = rc_health.unread(tmp_path, include_read=False)
    assert marker.kind == rc_health.KIND_CRASHED
    assert marker.detected_at == CRASH_AT


def test_a_crash_keeps_the_worktree_the_warning_named(tmp_path: Path) -> None:
    """The bridge names the worktree on one line only; it must survive the other."""
    warn(tmp_path)
    marker = crash(tmp_path, worktree="")
    assert marker.worktree == WORKTREE


# ------------------------------------------------------------------ the reading


def test_the_headline_carries_the_resume_command(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    directory = projects / rc_health.project_dir_name(WORKTREE)
    directory.mkdir(parents=True)
    (directory / "30c63ade-de7f-4269-890d-b4ecdb5c53ac.jsonl").write_text("{}\n", encoding="utf-8")

    marker = crash(tmp_path / "state")
    line = rc_health.headline(marker, projects)
    assert line.startswith(f"RC-CRASH {SESSION} on {SERVER} was killed at ")
    assert "claude --resume 30c63ade-de7f-4269-890d-b4ecdb5c53ac" in line
    assert WORKTREE in line


def test_an_unreadable_record_is_skipped_rather_than_taking_out_the_report(
    tmp_path: Path,
) -> None:
    """Print beside the breaker's read and the queue's; one bad file must not kill them."""
    crash(tmp_path)
    (tmp_path / "half-written.json").write_text('{"session": "cse_x", ', encoding="utf-8")

    (marker,) = rc_health.unread(tmp_path, include_read=False)
    assert marker.session == SESSION


def test_report_is_silent_on_a_directory_that_does_not_exist(tmp_path: Path) -> None:
    """Nothing has ever crashed on a fresh box; that is silence, not an error."""
    assert rc_health.unread(tmp_path / "never-written", include_read=False) == ()


# -------------------------------------------------------------------- the verbs


def test_main_report_ack_marks_what_it_printed_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    crash(tmp_path)
    exit_code = rc_health.main(
        ["--rc-health-dir", str(tmp_path), "--projects-dir", str(tmp_path), "report", "--ack"]
    )
    assert exit_code == 0
    printed = capsys.readouterr().out
    assert printed.startswith("RC-CRASH ")

    assert rc_health.main(["--rc-health-dir", str(tmp_path), "report"]) == 0
    assert capsys.readouterr().out == ""


def test_main_record_writes_the_document_report_reads(tmp_path: Path) -> None:
    assert (
        rc_health.main(
            [
                "--rc-health-dir",
                str(tmp_path),
                "--now",
                str(CRASH_AT),
                "record",
                "--session",
                SESSION,
                "--server",
                SERVER,
                "--worktree",
                WORKTREE,
                "--detail",
                "Session failed",
            ]
        )
        == 0
    )
    document = json.loads(rc_health.marker_path(tmp_path, SESSION).read_text(encoding="utf-8"))
    assert document["kind"] == rc_health.KIND_CRASHED
    assert document["detected_at"] == CRASH_AT
    assert document["worktree"] == WORKTREE


def test_main_ack_on_a_session_with_no_record_is_not_an_error(tmp_path: Path) -> None:
    assert rc_health.main(["--rc-health-dir", str(tmp_path), "ack", "--session", "cse_nope"]) == 0


# ------------------------------------------------------- the recipe that reads it


def test_watch_report_prints_a_staged_crash(tmp_path: Path) -> None:
    """Assert the effect, not the text: run the recipe and read what it says.

    A pin on `tools/rc_health.py report` appearing in the justfile passes just as
    happily when the line is orphaned or the tool is a no-op (#324, #343). So this stages
    a crash under the seam and runs `just watch-report` as a caller runs it, with
    every other read's directory pointed at empty ground so only this one speaks.
    """
    rc_health_dir = tmp_path / "rc-health"
    rc_health.record(
        rc_health_dir,
        rc_health.Marker(
            session=SESSION,
            server=SERVER,
            kind=rc_health.KIND_CRASHED,
            detail="Session failed",
            worktree=WORKTREE,
            detected_at=CRASH_AT,
            acknowledged_at=0,
        ),
    )
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    (queue_dir / "policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "freeze": {"state": "open", "since": "now", "ruling": "test"},
                "wip_limit": {"value": 0, "since": "now", "ruling": "test"},
                "packages": [],
            }
        ),
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "CTI_ADMISSION_DIR": str(tmp_path / "admission"),
        "CTI_BREAKER_DIR": str(tmp_path / "breaker"),
        "CTI_CLAUDE_PROJECTS_DIR": str(tmp_path / "projects"),
        "CTI_DISPATCH_DIR": str(tmp_path / "dispatches"),
        "CTI_QUEUE_DIR": str(queue_dir),
        "CTI_QUEUE_ROOT": str(tmp_path / "queue-root"),
        "CTI_RC_HEALTH_DIR": str(rc_health_dir),
        "CTI_WATCH_DIR": str(tmp_path / "watch"),
    }
    printed = subprocess.run(
        # S607: `just` resolves off PATH on purpose, as everywhere else in this suite —
        # the recipe under test is the one a caller runs.
        ["just", "watch-report"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    ).stdout
    crashes = [line for line in printed.splitlines() if line.startswith("RC-CRASH ")]
    assert len(crashes) == 1, printed
    assert SESSION in crashes[0]


# --------------------------------------------------------------- the pane-log scan

# The incident's own three lines, verbatim from the pane, with the ordinary reconnect
# noise between them that the storm buried them in.
PANE = f"""[07:08:18] Error: Failed to refresh session cse_01Czi2G6JHvdRZxNPymhnmCr token:
[07:08:20] Reconnected after 5s
[07:13:30] Session failed: Process exited with error cse_01Czi2G6JHvdRZxNPymhnmCr
[07:13:30] kept worktree {WORKTREE} · session crashed
[07:13:35] Reconnected after 4s
"""


def test_scan_text_reads_the_incidents_own_pane_lines() -> None:
    warning, killed = rc_health.scan_text(PANE)
    assert (warning.kind, warning.session) == (rc_health.KIND_REFRESH_FAILED, SESSION)
    assert (killed.kind, killed.session) == (rc_health.KIND_CRASHED, SESSION)
    assert killed.worktree == WORKTREE, "the worktree is on the following line, not the crash's"


def test_scan_text_ignores_the_reconnect_noise_that_buries_them() -> None:
    assert rc_health.scan_text("[06:50:10] Reconnected after 6s\n" * 500) == ()


def test_a_crash_without_its_worktree_line_does_not_borrow_the_previous_ones() -> None:
    """Two sessions dying in one batch is when a wrong path would be most confident."""
    other = "cse_01OtherSessionAAAAAAAAAA"
    text = (
        f"[07:13:30] Session failed: Process exited with error {SESSION}\n"
        f"[07:13:30] kept worktree {WORKTREE} · session crashed\n"
        f"[07:13:31] Session failed: Process exited with error {other}\n"
    )
    first, second = rc_health.scan_text(text)
    assert first.worktree == WORKTREE
    assert second.worktree == ""


def test_scan_records_each_line_once_across_calls(tmp_path: Path) -> None:
    """The caller is a 30-second loop; a re-read must not resurface an old crash."""
    log = tmp_path / "pane.log"
    log.write_text(PANE, encoding="utf-8")
    state = tmp_path / "state"

    first = rc_health.scan(state, log, server=SERVER, now=CRASH_AT)
    assert [marker.kind for marker in first] == [
        rc_health.KIND_REFRESH_FAILED,
        rc_health.KIND_CRASHED,
    ]

    assert rc_health.scan(state, log, server=SERVER, now=CRASH_AT + 30) == ()
    (marker,) = rc_health.unread(state, include_read=False)
    assert marker.detected_at == CRASH_AT, "the second pass must not re-stamp the first's find"


def test_scan_survives_an_offset_that_outlives_the_wrapper(tmp_path: Path) -> None:
    """Systemd restarts the unit; an in-memory offset would replay the log as news."""
    log = tmp_path / "pane.log"
    log.write_text(PANE, encoding="utf-8")
    state = tmp_path / "state"
    rc_health.scan(state, log, server=SERVER, now=CRASH_AT)

    with log.open("a", encoding="utf-8") as handle:
        handle.write("[07:20:00] Reconnected after 3s\n")
    assert rc_health.scan(state, log, server=SERVER, now=CRASH_AT + 400) == ()
    assert int(rc_health.offset_path(state, log).read_text(encoding="utf-8")) == log.stat().st_size


def test_scan_restarts_at_zero_when_the_log_was_rotated(tmp_path: Path) -> None:
    """A file shorter than the offset was rotated; reading from the old one finds nothing."""
    log = tmp_path / "pane.log"
    log.write_text(PANE + "[07:20:00] Reconnected after 3s\n" * 40, encoding="utf-8")
    state = tmp_path / "state"
    rc_health.scan(state, log, server=SERVER, now=CRASH_AT)

    log.write_text(
        "[08:01:02] Session failed: Process exited with error cse_01Fresh\n", encoding="utf-8"
    )
    (fresh,) = rc_health.scan(state, log, server=SERVER, now=CRASH_AT + 2800)
    assert fresh.session == "cse_01Fresh"


def test_scan_on_a_log_that_does_not_exist_yet_is_silent(tmp_path: Path) -> None:
    """The wrapper arms `pipe-pane` and scans on the same loop; the first pass may race it."""
    assert rc_health.scan(tmp_path, tmp_path / "absent.log", server=SERVER, now=CRASH_AT) == ()
