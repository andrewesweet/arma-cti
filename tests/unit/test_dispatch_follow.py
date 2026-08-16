"""The attached dispatch follower restores one honest completion edge (#280)."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path


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


def test_a_followed_dispatch_is_owed_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], held_pipes: list[int]
) -> None:
    record = survey_record(tmp_path, "d-20260816-130200-cccccc", held=held_pipes)
    dispatch_follow.note_attachment(record, 4321, 1_755_000_000.0)

    assert dispatch_follow.main(["--report", "--dispatch-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


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


def test_the_report_names_the_remainder_it_did_not_print(tmp_path: Path) -> None:
    """A cap that truncated in silence would read as "everything is covered"."""
    findings = tuple(
        dispatch_follow.Finding(
            "wake_unarmed", tmp_path / f"d-{index}", (f"dispatch=d-{index}",), once=False
        )
        for index in range(dispatch_follow.REPORT_LIMIT + 3)
    )

    lines = dispatch_follow.report_lines(findings)

    assert len(lines) == dispatch_follow.REPORT_LIMIT + 1
    assert lines[-1].startswith("more=3 ")


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


def test_a_refused_follow_leaves_no_claim_that_anything_was_listening(
    tmp_path: Path,
) -> None:
    """Attachment is noted after every target reads back, never per id as they are read."""
    good = "d-20260816-180000-aaaaaa"
    record = write_record(tmp_path, good, tmp_path / good / "result.json")
    (record / "result.json").write_text("{}\n", encoding="utf-8")

    code = dispatch_follow.main([good, "d-20260816-180001-bbbbbb", "--dispatch-dir", str(tmp_path)])

    assert code == dispatch_follow.EXIT_REFUSED
    assert not (record / "follow.json").exists()
