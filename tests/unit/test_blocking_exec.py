"""Tests for the blocking-handle exec wrapper (#678).

`ansible-playbook` refuses non-blocking standard handles before any playbook
work, and a dispatched session's captured output presents exactly that
arrangement — so `check-machine-b` used to pass or fail on who called the
gate rather than on the tree. The wrapper satisfies the precondition instead
of tripping it, and these tests pin both halves of that claim: that a
non-blocking handle really is flipped before exec (proved inside the execed
process, not by trusting the wrapper's own report), and that the recipe's
ansible invocations actually go through it, so a drift back to a bare
`uv run ansible-playbook` line reds here rather than on the next dispatched
gate run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    import pytest

BLOCKING_EXEC = load_tool("blocking_exec")


def test_ensure_blocking_flips_only_non_blocking_fds() -> None:
    read_fd, write_fd = os.pipe()
    try:
        os.set_blocking(write_fd, False)
        assert BLOCKING_EXEC.ensure_blocking((read_fd, write_fd)) == [write_fd]
        assert os.get_blocking(read_fd)
        assert os.get_blocking(write_fd)
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_ensure_blocking_skips_closed_fds() -> None:
    fd = os.open(os.devnull, os.O_RDONLY)
    os.close(fd)
    assert BLOCKING_EXEC.ensure_blocking((fd,)) == []


def test_main_execs_named_command_with_its_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, ...]] = []

    def fake_execvp(*args: object) -> None:
        seen.append(args)

    monkeypatch.setattr(BLOCKING_EXEC.os, "execvp", fake_execvp)
    assert BLOCKING_EXEC.main(["ansible-playbook", "--syntax-check", "x.yml"]) == 0
    assert seen == [("ansible-playbook", ["ansible-playbook", "--syntax-check", "x.yml"])]


def test_main_returns_127_for_a_missing_command(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_execvp(*args: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", str(args[0]))

    monkeypatch.setattr(BLOCKING_EXEC.os, "execvp", missing_execvp)
    assert BLOCKING_EXEC.main(["no-such-command"]) == 127


def test_main_refuses_an_empty_command_line(capsys: pytest.CaptureFixture[str]) -> None:
    assert BLOCKING_EXEC.main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_execed_process_sees_blocking_stdout_even_when_captured_non_blocking() -> None:
    """The proof the wrapper exists for: the handle is blocking after exec.

    The child's stdout is a pipe set non-blocking by this test — the
    arrangement a capturing dispatched session presents — and the execed
    python reports what its own handle really is, read back through the
    pipe's other end.
    """
    read_fd, write_fd = os.pipe()
    os.set_blocking(write_fd, False)
    try:
        proc = subprocess.Popen(  # noqa: S603 — fixed argv built from REPO and sys.executable, no shell
            [
                sys.executable,
                str(REPO / "tools" / "blocking_exec.py"),
                sys.executable,
                "-c",
                "import os; print(os.get_blocking(1))",
            ],
            stdin=read_fd,
            stdout=write_fd,
        )
    finally:
        os.close(write_fd)
    try:
        chunks = []
        while True:
            chunk = os.read(read_fd, 4096)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(read_fd)
    proc.wait()
    assert proc.returncode == 0
    assert b"".join(chunks).strip() == b"True"


def test_recipe_ansible_lines_go_through_the_wrapper() -> None:
    """A bare `uv run ansible-playbook` line in the recipe re-opens #678."""
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    recipe = justfile.split("check-machine-b:", 1)[1].split("\n\n", 1)[0]
    ansible_lines = [
        line.strip() for line in recipe.splitlines() if line.strip().startswith("uv run")
    ]
    assert len(ansible_lines) == 3
    for line in ansible_lines:
        assert line.startswith("uv run python tools/blocking_exec.py "), line
