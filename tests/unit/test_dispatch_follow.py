"""The attached dispatch follower restores one honest completion edge (#280)."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence


dispatch_follow = load_tool("dispatch_follow")
JUSTFILE = REPO / "justfile"


def write_record(
    root: Path,
    dispatch_id: str,
    result_path: Path,
    *,
    runner_pipe: Path | None = None,
) -> Path:
    """Write only the follower-owned fields of a dispatch record."""
    record = root / dispatch_id
    record.mkdir(parents=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": dispatch_id,
                "result_path": str(result_path),
                "runner_pipe": str(runner_pipe or record / "runner.pipe"),
            }
        ),
        encoding="utf-8",
    )
    return record


def test_a_written_result_prints_the_id_and_nonstandard_path_from_the_record(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatch_id = "d-20260808-120000-a1b2c3"
    recorded_result = tmp_path / "somewhere-deliberately-different" / "answer.json"
    recorded_result.parent.mkdir()
    recorded_result.write_text("{}\n", encoding="utf-8")
    write_record(tmp_path, dispatch_id, recorded_result)

    assert dispatch_follow.main([dispatch_id, "--dispatch-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "completion=dispatch_result_written",
        f"dispatch={dispatch_id}",
        f"result={recorded_result}",
        # `unrecorded` rather than a guess: this result predates `terminal_state` (#359),
        # and inventing `committed` for a tree nobody read is #375's reading exactly.
        "terminal=unrecorded",
    ]


def test_a_runner_that_disappeared_without_a_result_is_a_named_finding(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dispatch_id = "d-20260808-120001-b2c3d4"
    result_path = tmp_path / "missing-result.json"
    runner_pipe = tmp_path / "runner.pipe"
    os.mkfifo(runner_pipe)
    write_record(tmp_path, dispatch_id, result_path, runner_pipe=runner_pipe)

    assert (
        dispatch_follow.main([dispatch_id, "--dispatch-dir", str(tmp_path)])
        == dispatch_follow.EXIT_FINDING
    )
    output = capsys.readouterr().err
    assert "finding=runner_disappeared" in output
    assert f"dispatch={dispatch_id}" in output
    assert f"result={result_path}" in output
    assert "completion=" not in output
    assert "class=" not in output


def test_a_nonzero_child_result_is_still_a_completion_not_an_invented_class(
    tmp_path: Path,
) -> None:
    dispatch_id = "d-20260808-120002-c3d4e5"
    result_path = tmp_path / "result.json"
    result_path.write_text('{"returncode": 17}\n', encoding="utf-8")
    write_record(tmp_path, dispatch_id, result_path)

    target = dispatch_follow.read_target(tmp_path, dispatch_id)
    code, lines = dispatch_follow.follow(target)
    assert code == 0
    assert lines[0] == "completion=dispatch_result_written"
    assert not any(line.startswith("class=") for line in lines)


def test_the_wait_uses_the_runner_pipe_with_no_timeout_or_polling_interval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    read_fd, write_fd = os.pipe()
    target = dispatch_follow.FollowTarget(
        dispatch_id="d-20260808-120003-d4e5f6",
        result_path=tmp_path / "result.json",
        runner_pipe=tmp_path / "runner.pipe",
    )
    selected: list[tuple[Sequence[int], Sequence[int], Sequence[int]]] = []

    def raise_blocking() -> bytes:
        raise BlockingIOError

    monkeypatch.setattr(dispatch_follow.os, "open", lambda _path, _flags: read_fd)
    monkeypatch.setattr(dispatch_follow.os, "read", lambda _fd, _size: raise_blocking())

    def select_without_timeout(
        readable: Sequence[int], writable: Sequence[int], exceptional: Sequence[int]
    ) -> tuple[Sequence[int], Sequence[int], Sequence[int]]:
        selected.append((readable, writable, exceptional))
        return readable, writable, exceptional

    monkeypatch.setattr(dispatch_follow.select, "select", select_without_timeout)
    try:
        dispatch_follow.wait_for_runner(target)
    finally:
        os.close(write_fd)

    assert selected == [((read_fd,), (), ())]


def test_no_timeout_option_exists() -> None:
    with pytest.raises(SystemExit):
        dispatch_follow.parse_args(["d-20260808-120004-e5f6a7", "--timeout", "60"])


def test_arming_adds_the_runner_identity_and_authoritative_paths(tmp_path: Path) -> None:
    record = tmp_path / "dispatches" / "d-20260808-120005-f6a7b8"
    record.mkdir(parents=True)
    runner_pipe = record / "runner.pipe"
    os.mkfifo(runner_pipe)
    (record / "dispatch.json").write_text(
        json.dumps({"dispatch_id": record.name, "existing": "kept"}), encoding="utf-8"
    )

    dispatch_follow.arm_record(record, 7654, runner_pipe)

    document = json.loads((record / "dispatch.json").read_text(encoding="utf-8"))
    assert document["dispatch_id"] == record.name
    assert document["existing"] == "kept"
    # `launcher_pid`, and never `runner_pid`: the value is the process the seam forked,
    # not the session it starts, and the old name invited the check that produced #105's
    # sixth instance (#308).
    assert document["launcher_pid"] == 7654
    assert "runner_pid" not in document
    assert document["runner_pipe"] == str(runner_pipe)
    assert document["result_path"] == str(record / "result.json")


def test_the_recipe_is_an_attached_foreground_invocation() -> None:
    recipe = JUSTFILE.read_text(encoding="utf-8").split("\ndispatch-follow *args:", maxsplit=1)[1]
    body = recipe.split("\n\n", maxsplit=1)[0]
    assert "uv run python tools/dispatch_follow.py" in body
    assert "nohup" not in body
    assert "&" not in body


def test_the_first_finished_dispatch_is_reported_and_the_rest_are_named_pending(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    finished = tmp_path / "finished.json"
    finished.write_text("{}\n", encoding="utf-8")
    slow_pipe = tmp_path / "slow.pipe"
    os.mkfifo(slow_pipe)
    write_record(
        tmp_path, "d-20260809-120000-aaaaaa", tmp_path / "slow.json", runner_pipe=slow_pipe
    )
    write_record(tmp_path, "d-20260809-120001-bbbbbb", finished)

    code = dispatch_follow.main(
        [
            "d-20260809-120000-aaaaaa",
            "d-20260809-120001-bbbbbb",
            "--dispatch-dir",
            str(tmp_path),
        ]
    )

    assert code == 0
    assert capsys.readouterr().out.splitlines() == [
        "completion=dispatch_result_written",
        "dispatch=d-20260809-120001-bbbbbb",
        f"result={finished}",
        "terminal=unrecorded",
        "pending=d-20260809-120000-aaaaaa",
    ]


def test_following_one_dispatch_prints_no_pending_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result_path = tmp_path / "only.json"
    result_path.write_text("{}\n", encoding="utf-8")
    write_record(tmp_path, "d-20260809-120002-cccccc", result_path)

    dispatch_follow.main(["d-20260809-120002-cccccc", "--dispatch-dir", str(tmp_path)])

    assert not any("pending=" in line for line in capsys.readouterr().out.splitlines())


def test_a_pipe_that_is_already_closed_ends_the_wait_on_that_target(tmp_path: Path) -> None:
    open_pipe = tmp_path / "open.pipe"
    closed_pipe = tmp_path / "closed.pipe"
    os.mkfifo(open_pipe)
    os.mkfifo(closed_pipe)
    holder = os.open(open_pipe, os.O_RDWR)
    slow = dispatch_follow.FollowTarget("d-slow", tmp_path / "slow.json", open_pipe)
    quick = dispatch_follow.FollowTarget("d-quick", tmp_path / "quick.json", closed_pipe)

    try:
        assert dispatch_follow.wait_for_first((slow, quick)) is quick
    finally:
        os.close(holder)


def test_a_disappeared_first_runner_is_a_finding_that_still_names_the_pending_rest(
    tmp_path: Path,
) -> None:
    gone_pipe = tmp_path / "gone.pipe"
    os.mkfifo(gone_pipe)
    gone = dispatch_follow.FollowTarget("d-gone", tmp_path / "gone.json", gone_pipe)
    other = dispatch_follow.FollowTarget("d-other", tmp_path / "other.json", tmp_path / "o.pipe")

    code, lines = dispatch_follow.follow_first((gone, other))

    assert code == dispatch_follow.EXIT_FINDING
    assert lines[0] == "finding=runner_disappeared"
    assert "dispatch=d-gone" in lines
    assert "pending=d-other" in lines


def test_a_repeated_id_is_followed_once_so_a_cohort_loop_cannot_double_count() -> None:
    assert dispatch_follow.unique_ids(["d-a", "d-b", "d-a"]) == ("d-a", "d-b")


def test_no_id_at_all_is_refused_by_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = dispatch_follow.main(["--dispatch-dir", str(tmp_path)])

    assert code == dispatch_follow.EXIT_REFUSED
    assert capsys.readouterr().err.splitlines() == ["refusal=dispatch_id_missing"]


def test_one_unreadable_record_refuses_by_that_id_rather_than_following_the_others(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result_path = tmp_path / "fine.json"
    result_path.write_text("{}\n", encoding="utf-8")
    write_record(tmp_path, "d-20260809-120003-dddddd", result_path)

    code = dispatch_follow.main(
        [
            "d-20260809-120003-dddddd",
            "d-20260809-120004-eeeeee",
            "--dispatch-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert code == dispatch_follow.EXIT_REFUSED
    assert "refusal=dispatch_follow_unavailable" in captured.err
    assert "dispatch=d-20260809-120004-eeeeee" in captured.err
    assert captured.out == ""


# ------------------------------------------------- the delivery report (#359)


def survey_record(root: Path, dispatch_id: str, *, held: list[int]) -> Path:
    """Write a record whose runner is alive, holding its pipe open until the test ends."""
    record = write_record(root, dispatch_id, root / dispatch_id / "result.json")
    pipe = record / "runner.pipe"
    os.mkfifo(pipe)
    held.append(os.open(pipe, os.O_RDWR))
    return record


@pytest.fixture
def held_pipes() -> Iterator[list[int]]:
    """Hold every arranged runner's write end open, and close them however the test ends."""
    open_fds: list[int] = []
    try:
        yield open_fds
    finally:
        for fd in open_fds:
            os.close(fd)


def test_a_live_runner_reads_as_running_and_a_closed_one_as_abandoned(
    tmp_path: Path, held_pipes: list[int]
) -> None:
    """The stale/live distinction, from the record alone and without blocking (#359)."""
    live = survey_record(tmp_path, "d-20260816-120000-aaaaaa", held=held_pipes)
    assert dispatch_follow.runner_state(live) == dispatch_follow.RUNNER_RUNNING

    dead = write_record(tmp_path, "d-20260816-120001-bbbbbb", tmp_path / "b.json")
    os.mkfifo(dead / "runner.pipe")
    assert dispatch_follow.runner_state(dead) == dispatch_follow.RUNNER_ABANDONED

    (live / "result.json").write_text("{}\n", encoding="utf-8")
    assert dispatch_follow.runner_state(live) == dispatch_follow.RUNNER_FINISHED

    # No pipe at all is a record older than the arming, and is neither alive nor dead.
    older = write_record(tmp_path, "d-20260816-120002-cccccc", tmp_path / "c.json")
    assert dispatch_follow.runner_state(older) == dispatch_follow.RUNNER_UNKNOWN


def test_a_running_dispatch_nobody_follows_is_reported_with_the_form_that_arms_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], held_pipes: list[int]
) -> None:
    """The 2026-08-16 shape: armed four times in a form that notified nothing (#359)."""
    survey_record(tmp_path, "d-20260816-130000-aaaaaa", held=held_pipes)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0

    printed = capsys.readouterr().out.splitlines()
    assert "finding=wake_unarmed" in printed
    assert "dispatch=d-20260816-130000-aaaaaa" in printed
    assert "action=just dispatch-follow d-20260816-130000-aaaaaa" in printed


def test_a_running_dispatch_stays_reported_because_it_is_still_true(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], held_pipes: list[int]
) -> None:
    """Standing rather than once-only: repetition is the only pressure available."""
    survey_record(tmp_path, "d-20260816-130100-bbbbbb", held=held_pipes)

    dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)])
    capsys.readouterr()
    dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)])

    assert "finding=wake_unarmed" in capsys.readouterr().out


def dead_pid() -> int:
    """Name a pid that is certainly not running: one past this kernel's maximum.

    Deterministic where a spawned-and-reaped pid is not — `kill` answers `ESRCH` for an
    out-of-range pid, and no scheduling accident can make this one exist mid-test.
    """
    return int(Path("/proc/sys/kernel/pid_max").read_text(encoding="utf-8")) + 1


def test_a_followed_dispatch_is_owed_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], held_pipes: list[int]
) -> None:
    record = survey_record(tmp_path, "d-20260816-130200-cccccc", held=held_pipes)
    dispatch_follow.note_attachment(record, os.getpid(), 1_755_000_000.0)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_a_follower_that_is_no_longer_running_is_not_listening(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], held_pipes: list[int]
) -> None:
    """Attachment is a claim about a process, and the process is checked (#359 review 1).

    Constructed by the reviewer as attach, terminate the follower, and watch the dispatch
    stay exempt from the report for good — a watcher that is not listening, silent by
    construction rather than merely unreported.
    """
    record = survey_record(tmp_path, "d-20260816-190000-aaaaaa", held=held_pipes)
    dispatch_follow.note_attachment(record, dead_pid(), 1_755_000_000.0)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0

    printed = capsys.readouterr().out.splitlines()
    assert "finding=wake_unarmed" in printed
    assert "dispatch=d-20260816-190000-aaaaaa" in printed


def test_a_completion_whose_follower_died_before_it_is_still_owed_a_wake(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other half of the same trigger: the run finished, and nobody was told."""
    record = write_record(tmp_path, "d-20260816-190100-bbbbbb", tmp_path / "b.json")
    (record / "result.json").write_text("{}\n", encoding="utf-8")
    dispatch_follow.note_attachment(record, dead_pid(), 1_755_000_000.0)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    assert "finding=wake_undelivered" in capsys.readouterr().out


def test_a_completion_whose_wake_was_delivered_is_owed_nothing_after_the_follower_exits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Why liveness alone cannot answer this: the delivered case leaves the same dead pid.

    A follower that printed the completion and exited is indistinguishable from one that
    was killed before it, unless the delivery is its own recorded fact (#359 review 1).
    """
    record = write_record(tmp_path, "d-20260816-190200-cccccc", tmp_path / "c.json")
    (record / "result.json").write_text("{}\n", encoding="utf-8")
    dispatch_follow.note_attachment(record, dead_pid(), 1_755_000_000.0)
    dispatch_follow.note_delivery(record, 1_755_000_001.0)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_a_result_a_live_follower_has_not_printed_yet_is_not_a_lost_wake(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ordinary window between the result landing and the follower waking on it."""
    record = write_record(tmp_path, "d-20260816-190300-dddddd", tmp_path / "d.json")
    (record / "result.json").write_text("{}\n", encoding="utf-8")
    dispatch_follow.note_attachment(record, os.getpid(), 1_755_000_000.0)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_the_cohort_a_follow_did_not_wake_on_is_left_owed_a_wake(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], held_pipes: list[int]
) -> None:
    """#295's `pending=` list, which used to be exempt from the report for good (#359).

    The follow returns on the first completion and the process ends, so nothing is
    listening to the rest from that moment. The mechanism built to shorten the cohort's
    wake was the mechanism that blinded the report for the rest of the cohort.
    """
    slow = survey_record(tmp_path, "d-20260816-200000-aaaaaa", held=held_pipes)
    quick_id = "d-20260816-200001-bbbbbb"
    quick = write_record(tmp_path, quick_id, tmp_path / quick_id / "result.json")
    (quick / "result.json").write_text("{}\n", encoding="utf-8")

    assert (
        dispatch_follow.main(
            [
                "d-20260816-200000-aaaaaa",
                "d-20260816-200001-bbbbbb",
                "--dispatch-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert "pending=d-20260816-200000-aaaaaa" in capsys.readouterr().out
    assert not (slow / "follow.json").exists()

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0

    printed = capsys.readouterr().out.splitlines()
    assert "finding=wake_unarmed" in printed
    assert "dispatch=d-20260816-200000-aaaaaa" in printed
    # And the one it did wake on is owed nothing, because that wake was delivered.
    assert "dispatch=d-20260816-200001-bbbbbb" not in printed


def test_a_completion_that_woke_nobody_is_reported_once_with_its_terminal_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Printing the finding *is* the delivery, so a second read is not news (#359)."""
    record = write_record(tmp_path, "d-20260816-140000-dddddd", tmp_path / "d.json")
    (record / "result.json").write_text(
        json.dumps({"returncode": 0, "outcome": "ok", "terminal_state": "uncommitted"}),
        encoding="utf-8",
    )

    dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)])
    first = capsys.readouterr().out.splitlines()
    assert "finding=wake_undelivered" in first
    assert "terminal=uncommitted" in first

    dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)])
    assert capsys.readouterr().out == ""

    dispatch_follow.main(["--report", "--all", "--dispatch-dir", str(tmp_path)])
    assert "finding=wake_undelivered" in capsys.readouterr().out


def test_a_runner_gone_without_a_result_is_reported_as_stale_rather_than_in_flight(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The 2026-08-10 record that counted as in flight for six days (#359)."""
    record = write_record(tmp_path, "d-20260816-150000-eeeeee", tmp_path / "e.json")
    os.mkfifo(record / "runner.pipe")

    dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)])

    printed = capsys.readouterr().out.splitlines()
    assert "finding=dispatch_abandoned" in printed
    assert "dispatch=d-20260816-150000-eeeeee" in printed
    assert f"record={record}" in printed


def test_a_record_whose_pipe_cannot_be_read_claims_no_lost_wake(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`unknown` is not evidence of anything, and a report that guessed would be noise."""
    write_record(tmp_path, "d-20260816-160000-ffffff", tmp_path / "f.json")

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def made_findings(root: Path, count: int, *, once: bool) -> tuple[dispatch_follow.Finding, ...]:
    """`count` findings of one kind, each rendering a single line naming itself."""
    kind = "wake_undelivered" if once else "wake_unarmed"
    return tuple(
        dispatch_follow.Finding(
            kind, root / f"d-{kind}-{index}", (f"dispatch=d-{kind}-{index}",), once=once
        )
        for index in range(count)
    )


def test_the_report_names_the_remainder_it_did_not_print(tmp_path: Path) -> None:
    """A cap that truncated in silence would read as "everything is covered"."""
    findings = made_findings(tmp_path, dispatch_follow.REPORT_LIMIT + 3, once=True)

    lines = dispatch_follow.report_lines(findings)

    assert len(lines) == dispatch_follow.REPORT_LIMIT + 1
    assert lines[-1].startswith("more=3 ")


def test_standing_findings_cannot_fill_the_read_and_stall_the_backlog(tmp_path: Path) -> None:
    """A standing finding is never stamped, so enough of them would drain nothing (#359).

    Ten unfollowed running dispatches would have filled every read for as long as they ran,
    and every completion that woke nobody would have queued behind them. A standing finding
    dropped from one read is true again on the next, which is what makes it the safe loss.
    """
    findings = (
        *made_findings(tmp_path, dispatch_follow.REPORT_LIMIT, once=False),
        *made_findings(tmp_path, 4, once=True),
    )

    shown = dispatch_follow.shown_findings(findings)

    assert sum(1 for finding in shown if not finding.once) == dispatch_follow.STANDING_LIMIT
    assert sum(1 for finding in shown if finding.once) == 4
    assert dispatch_follow.report_lines(findings)[-1].startswith("more=5 ")


def test_a_read_stamps_exactly_what_it_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], held_pipes: list[int]
) -> None:
    """A finding held back by the cap is not delivered, so it must not be stamped.

    The survey is newest-first, so the older completion sits behind ten standing findings
    and is printed only because standing findings are capped — which is exactly the case
    where "stamp the first ten" and "stamp what was printed" disagree.
    """
    for index in range(dispatch_follow.REPORT_LIMIT):
        survey_record(tmp_path, f"d-20260816-2100{index:02d}-aaaaaa", held=held_pipes)
    older = write_record(tmp_path, "d-20260810-000000-bbbbbb", tmp_path / "older.json")
    (older / "result.json").write_text("{}\n", encoding="utf-8")

    dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)])
    first = capsys.readouterr().out
    dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)])
    second = capsys.readouterr().out

    # Printed once and stamped once; the standing findings repeat because they still hold.
    assert first.count("finding=wake_undelivered") == 1
    assert "finding=wake_undelivered" not in second
    assert "finding=wake_unarmed" in second


def test_the_backlog_a_box_carried_before_this_existed_is_stamped_by_one_deliberate_act(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """341 historical `wake_undelivered` is ~34 reads at the top of ~34 turns (#359).

    Stamped rather than deleted, in the open and with the count printed, so `--report --all`
    still shows every one of them.
    """
    for index in range(3):
        record = write_record(tmp_path, f"d-20260810-0000{index:02d}-aaaaaa", tmp_path / "r.json")
        (record / "result.json").write_text("{}\n", encoding="utf-8")

    assert dispatch_follow.main(["--backfill", "--dispatch-dir", str(tmp_path)]) == 0
    assert "backfilled=3" in capsys.readouterr().out

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""

    dispatch_follow.main(["--report", "--all", "--dispatch-dir", str(tmp_path)])
    assert capsys.readouterr().out.count("finding=wake_undelivered") == 3


# ------------------------------------- the two triggers, with a follower that really runs
#
# The report's whole subject is a process that is not there any more, and an in-process
# `note_attachment` cannot construct one: the pid it writes is pytest's own and stays alive
# for the rest of the session. These three run the follower as the harness runs it — a
# separate process with its own pid — and end it the two ways the review found: by
# returning on the first of a cohort, and by being killed.

FOLLOWER: Path = REPO / "tools" / "dispatch_follow.py"


def start_follower(root: Path, dispatch_ids: Sequence[str]) -> subprocess.Popen[str]:
    """Run the real follower over these ids, as its own process with its own pid."""
    return subprocess.Popen(  # noqa: S603 - the interpreter running this suite
        [sys.executable, str(FOLLOWER), *dispatch_ids, "--dispatch-dir", str(root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def await_attachment(record: Path, seconds: float = 30.0) -> int:
    """Wait for the follower to write its pid onto this record, and answer with it.

    Bounded and polled rather than slept through: the follower is a separate process, so
    its attachment genuinely arrives after the call that started it. The window is sized to
    an interpreter's cold start, not stretched until something passes.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            document = json.loads((record / "follow.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            document = {}
        if document.get("follower_pid"):
            return int(document["follower_pid"])
        time.sleep(0.05)
    message = f"no follower attached to {record} inside {seconds}s"
    raise AssertionError(message)


def end_run(record: Path, held: int) -> None:
    """Record a result and let the runner's pipe go, which is how a dispatch ends."""
    (record / "result.json").write_text(
        json.dumps({"returncode": 0, "outcome": "ok", "terminal_state": "committed"}),
        encoding="utf-8",
    )
    os.close(held)


def test_a_real_follower_leaves_the_cohort_it_did_not_wake_on_owed_a_wake(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The review's deterministic trigger, reconstructed with a follower that really exits.

    Follow two, wake on the first, and the second is `pending=` in the line the seat reads.
    It used to carry that follower's attachment for good, so `--report` never named it
    again — the mechanism built to shorten the cohort's wake blinding the report for the
    rest of the cohort.
    """
    first = write_record(tmp_path, "d-B1", tmp_path / "d-B1" / "result.json")
    second = write_record(tmp_path, "d-B2", tmp_path / "d-B2" / "result.json")
    os.mkfifo(first / "runner.pipe")
    os.mkfifo(second / "runner.pipe")
    runners = [os.open(record / "runner.pipe", os.O_RDWR) for record in (first, second)]

    follower = start_follower(tmp_path, ("d-B1", "d-B2"))
    try:
        await_attachment(first)
        await_attachment(second)
        end_run(first, runners[0])
        printed, _ = follower.communicate(timeout=30)
    finally:
        if follower.poll() is None:  # pragma: no cover - only on a failure above
            follower.kill()
    assert follower.returncode == 0
    assert "pending=d-B2" in printed

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    running = capsys.readouterr().out.splitlines()
    assert "finding=wake_unarmed" in running
    assert "dispatch=d-B2" in running

    end_run(second, runners[1])
    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    finished = capsys.readouterr().out.splitlines()
    assert "finding=wake_undelivered" in finished
    assert "dispatch=d-B2" in finished


def test_a_real_follower_that_is_killed_leaves_its_completion_owed_a_wake(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The review's conditional trigger: attach, terminate, complete the run (#359).

    "A watcher that is not listening", which the record used to answer as a wake already
    delivered. The pid on the record is what makes the difference, and it is a real one.
    """
    record = write_record(tmp_path, "d-C", tmp_path / "d-C" / "result.json")
    os.mkfifo(record / "runner.pipe")
    runner = os.open(record / "runner.pipe", os.O_RDWR)

    follower = start_follower(tmp_path, ("d-C",))
    pid = await_attachment(record)
    assert pid != os.getpid()
    os.kill(pid, signal.SIGKILL)
    follower.communicate(timeout=30)
    end_run(record, runner)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert "finding=wake_undelivered" in printed
    assert "dispatch=d-C" in printed


def test_a_real_follower_that_delivered_its_wake_leaves_nothing_owed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control the two above need: the same dead pid, and no finding.

    Without it, "the follower's process is gone" would report every completion this
    mechanism ever delivered, which is a report nobody could keep reading.
    """
    record = write_record(tmp_path, "d-E", tmp_path / "d-E" / "result.json")
    os.mkfifo(record / "runner.pipe")
    runner = os.open(record / "runner.pipe", os.O_RDWR)

    follower = start_follower(tmp_path, ("d-E",))
    pid = await_attachment(record)
    end_run(record, runner)
    printed, _ = follower.communicate(timeout=30)

    assert follower.returncode == 0
    assert "completion=dispatch_result_written" in printed
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_a_record_that_cannot_be_stamped_still_reports_and_leaves_the_chain_standing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--report` runs ahead of the stall watchers, so its one write may not raise (#359).

    A record removed between the survey and the stamp, or a read-only mount, would
    otherwise take the read that catches what this one misses down with it. The cost of
    swallowing it is the finding printed again next read, which is the direction that keeps
    saying something.
    """
    record = write_record(tmp_path, "d-20260816-220000-aaaaaa", tmp_path / "a.json")
    (record / "result.json").write_text("{}\n", encoding="utf-8")

    def refuse_write(*_args: object, **_kwargs: object) -> int:
        message = "read-only file system"
        raise OSError(message)

    monkeypatch.setattr(Path, "write_text", refuse_write)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    assert "finding=wake_undelivered" in capsys.readouterr().out


def test_following_a_dispatch_records_the_attachment_the_report_reads_back(
    tmp_path: Path,
) -> None:
    """A follower is attached while it waits, so the fact is written when it starts."""
    dispatch_id = "d-20260816-170000-abcdef"
    record = write_record(tmp_path, dispatch_id, tmp_path / dispatch_id / "result.json")
    (record / "result.json").write_text("{}\n", encoding="utf-8")

    assert dispatch_follow.main([dispatch_id, "--dispatch-dir", str(tmp_path)]) == 0

    document = json.loads((record / "follow.json").read_text(encoding="utf-8"))
    assert document["follower_pid"] == os.getpid()
    assert document["followed_at"] > 0


def unreadable_record_refusal(root: Path) -> tuple[Path, list[str]]:
    """Arrange a follow refused before the attachment loop: one named id has no record."""
    good = "d-20260816-180000-aaaaaa"
    record = write_record(root, good, root / good / "result.json")
    (record / "result.json").write_text("{}\n", encoding="utf-8")
    return record, [good, "d-20260816-180001-bbbbbb"]


def unobservable_runner_refusal(root: Path) -> tuple[Path, list[str]]:
    """Arrange a follow refused *after* it, by a record whose pipe cannot be opened."""
    identifier = "d-20260816-180002-cccccc"
    record = write_record(root, identifier, root / identifier / "result.json")
    return record, [identifier]


@pytest.mark.parametrize(
    "arrange", [unreadable_record_refusal, unobservable_runner_refusal], ids=["record", "runner"]
)
def test_a_refused_follow_leaves_no_claim_that_anything_was_listening(
    tmp_path: Path,
    arrange: Callable[[Path], tuple[Path, list[str]]],
) -> None:
    """Both refusals, because the property is about refusing and not about one path (#359).

    Attachment is noted after every target reads back, so the first refusal never writes
    it; the second refuses having observed nothing with the attachment already written, and
    used to leave every one of its records exempt from `--report` for good. The test that
    named this property covered only the first, which is a check that did not run reading
    as one that passed.
    """
    record, argv = arrange(tmp_path)

    code = dispatch_follow.main([*argv, "--dispatch-dir", str(tmp_path)])

    assert code == dispatch_follow.EXIT_REFUSED
    assert not (record / "follow.json").exists()
