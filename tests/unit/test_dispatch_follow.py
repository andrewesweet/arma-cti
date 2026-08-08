"""The attached dispatch follower restores one honest completion edge (#280)."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from collections.abc import Sequence
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
    assert document["runner_pid"] == 7654
    assert document["runner_pipe"] == str(runner_pipe)
    assert document["result_path"] == str(record / "result.json")


def test_the_recipe_is_an_attached_foreground_invocation() -> None:
    recipe = JUSTFILE.read_text(encoding="utf-8").split("dispatch-follow dispatch_id", maxsplit=1)[
        1
    ]
    body = recipe.split("\n\n", maxsplit=1)[0]
    assert "uv run python tools/dispatch_follow.py" in body
    assert "nohup" not in body
    assert "&" not in body
