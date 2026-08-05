"""Tests for the oversized-read guard, `.claude/hooks/deny-oversized-reads.py`.

The hook denies a `Read` whose window would deliver more than 40,000 characters,
where #203 measured 28 reads carrying 5.0% of every tool-result byte in this
project's history. Three things need pinning, and #120's lesson — that an
over-eager hook costs more than the rule it guards — is why the second and third
get as many tests as the first:

* the oversized read is denied, and the denial names the size and the remedy;
* what is *not* the target passes: an ordinary source read, a bounded window on
  the same oversized file, a big file whose first 2,000 lines are small, and the
  media whose `Read` has no `offset`/`limit` to fall back on;
* the failure modes. Everything the hook cannot read is denied (#41, #94), and
  everything `Read` itself will fail on is left to `Read`.

Sizes are built in `tmp_path` rather than taken from repo files, so a test says
what it means and no edit to `planner.py` can move a boundary underneath it.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
from typing import TYPE_CHECKING

from conftest import HOOKS, REPO, load_hook

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    import pytest

hook = load_hook("deny-oversized-reads")

LINE = "x" * 79 + "\n"  # 80 bytes, near this repo's 100-column ceiling


def call(monkeypatch: pytest.MonkeyPatch, stdin: str) -> int:
    """Run the hook's stdin contract and return the exit code it would use."""
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return hook.main()


def read_of(
    path: str | Path,
    *,
    offset: int | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    """Build the `tool_input` of one Read call."""
    tool_input: dict[str, object] = {"file_path": str(path)}
    if offset is not None:
        tool_input["offset"] = offset
    if limit is not None:
        tool_input["limit"] = limit
    return tool_input


def event(path: str | Path, *, offset: int | None = None, limit: int | None = None) -> str:
    """Build the hook input for one Read call."""
    return json.dumps(
        {"tool_name": "Read", "tool_input": read_of(path, offset=offset, limit=limit)}
    )


def a_file(tmp_path: Path, name: str, *, chars: int, line: str = LINE) -> Path:
    """Write a file of about `chars` bytes, in lines of a stated length."""
    target = tmp_path / name
    target.write_text(line * (chars // len(line)), encoding="utf-8")
    return target


def wired_commands() -> Iterable[str]:
    """Every `.claude/settings.json` PreToolUse entry that runs this hook."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return [
        wired["command"]
        for entry in settings["hooks"]["PreToolUse"]
        for wired in entry["hooks"]
        if "deny-oversized-reads" in wired["command"]
    ]


# --- the oversized read is denied -------------------------------------------


def test_a_whole_file_read_above_the_threshold_is_denied(tmp_path: Path) -> None:
    """#207's headline acceptance criterion."""
    target = a_file(tmp_path, "planner.py", chars=60_000)
    assert hook.denial(read_of(target)) is not None


def test_the_denial_names_the_size_and_the_remedy(tmp_path: Path) -> None:
    target = a_file(tmp_path, "planner.py", chars=60_000)
    reason = hook.denial(read_of(target))
    assert reason is not None
    assert "60,000 characters" in reason
    assert f"{hook.THRESHOLD:,}" in reason
    assert "offset" in reason
    assert "limit" in reason
    assert "Grep" in reason


def test_the_denial_names_the_file(tmp_path: Path) -> None:
    target = a_file(tmp_path, "process-log.md", chars=60_000)
    reason = hook.denial(read_of(target))
    assert reason is not None
    assert "process-log.md" in reason


def test_the_denial_suggests_a_window_that_fits(tmp_path: Path) -> None:
    """80-byte lines, 40,000-character limit: 500 of them fit."""
    target = a_file(tmp_path, "big.md", chars=80_000)
    reason = hook.denial(read_of(target))
    assert reason is not None
    assert "500 lines" in reason


def test_a_file_just_over_the_threshold_is_denied(tmp_path: Path) -> None:
    target = a_file(tmp_path, "edge.md", chars=hook.THRESHOLD + 80)
    assert hook.denial(read_of(target)) is not None


def test_a_read_whose_limit_asks_for_too_much_is_denied(tmp_path: Path) -> None:
    """The hook measures the window asked for, not the presence of the argument.

    #207 would permit any call carrying `offset`/`limit`. That leaves the denial
    message's own advice as its bypass: `limit: 999999` after being told to use
    `limit` lands the identical payload. Measuring the window closes it, and
    costs nothing — every ordinary bounded read is far under the threshold.
    """
    target = a_file(tmp_path, "big.md", chars=200_000)
    assert hook.denial(read_of(target, limit=999_999)) is not None


def test_an_oversized_window_deep_in_a_file_is_denied(tmp_path: Path) -> None:
    target = a_file(tmp_path, "big.md", chars=200_000)
    assert hook.denial(read_of(target, offset=1_000, limit=2_000)) is not None


def test_a_file_of_one_enormous_line_is_denied(tmp_path: Path) -> None:
    """A stated over-block: a payload is a payload however few lines carry it."""
    target = tmp_path / "bundle.min.js"
    target.write_text("y" * 120_000, encoding="utf-8")
    assert hook.denial(read_of(target)) is not None


def test_a_vendored_wiki_page_gets_no_exemption(tmp_path: Path) -> None:
    """The wiki was checked and needs none; CLAUDE.md's INDEX.md rule points away already."""
    wiki = tmp_path / "docs" / "reference" / "arma-wiki" / "classnames"
    wiki.mkdir(parents=True)
    target = a_file(wiki, "Arma_3_CfgVehicles_WEST.wiki", chars=76_000)
    assert hook.denial(read_of(target)) is not None


# --- what is not the target passes ------------------------------------------


def test_an_ordinary_source_read_is_allowed() -> None:
    """#207's third acceptance criterion, against a real file of the ordinary size."""
    assert hook.denial(read_of(HOOKS / "deny-oversized-reads.py")) is None


def test_a_file_just_under_the_threshold_is_allowed(tmp_path: Path) -> None:
    target = a_file(tmp_path, "edge.md", chars=hook.THRESHOLD - 80)
    assert hook.denial(read_of(target)) is None


def test_a_file_exactly_at_the_threshold_is_allowed(tmp_path: Path) -> None:
    """The limit is what a read may deliver, so the boundary itself passes."""
    target = a_file(tmp_path, "edge.md", chars=hook.THRESHOLD)
    assert target.stat().st_size == hook.THRESHOLD
    assert hook.denial(read_of(target)) is None


def test_the_same_oversized_file_is_allowed_with_offset_and_limit(tmp_path: Path) -> None:
    """#207's second acceptance criterion."""
    target = a_file(tmp_path, "planner.py", chars=60_000)
    assert hook.denial(read_of(target, offset=200, limit=200)) is None


def test_a_bounded_limit_alone_is_allowed(tmp_path: Path) -> None:
    target = a_file(tmp_path, "planner.py", chars=60_000)
    assert hook.denial(read_of(target, limit=300)) is None


def test_a_tail_read_past_the_bulk_of_a_big_file_is_allowed(tmp_path: Path) -> None:
    target = a_file(tmp_path, "big.md", chars=200_000)
    assert hook.denial(read_of(target, offset=2_400)) is None


def test_a_huge_file_whose_first_2000_lines_are_small_is_allowed(tmp_path: Path) -> None:
    """`Read` stops at 2,000 lines, so the file's size on disk is the wrong question.

    Measured on the real corpus: `Western_Sahara_classNames.wiki` is 572,976
    bytes and delivers 39,256 of them. A stat-sized gate would deny it and would
    name a number six times larger than the one the agent would have paid.
    """
    target = a_file(tmp_path, "classnames.wiki", chars=500_000, line="short\n")
    assert target.stat().st_size > hook.THRESHOLD
    assert hook.denial(read_of(target)) is None


def test_a_screenshot_is_allowed(tmp_path: Path) -> None:
    """`Read` renders an image, and `offset`/`limit` is not a remedy that exists for it."""
    target = a_file(tmp_path, "0001-marker-collision.png", chars=650_000)
    assert hook.denial(read_of(target)) is None


def test_a_pdf_is_allowed(tmp_path: Path) -> None:
    """A PDF's window is `pages`, which `Read` already requires past ten of them."""
    target = a_file(tmp_path, "manual.pdf", chars=650_000)
    assert hook.denial(read_of(target)) is None


def test_an_uppercase_suffix_is_matched(tmp_path: Path) -> None:
    target = a_file(tmp_path, "SCREENSHOT.PNG", chars=650_000)
    assert hook.denial(read_of(target)) is None


def test_an_svg_is_not_exempt(tmp_path: Path) -> None:
    """An SVG is text, and reading a slice of one is exactly as available as anywhere else."""
    target = a_file(tmp_path, "diagram.svg", chars=120_000)
    assert hook.denial(read_of(target)) is not None


# --- what `Read` will fail on is left to `Read` -----------------------------


def test_a_missing_file_is_allowed(tmp_path: Path) -> None:
    """`Read` raises its own error and no bytes reach the context: nothing to prevent."""
    assert hook.denial(read_of(tmp_path / "no-such-file.py")) is None


def test_a_directory_is_allowed(tmp_path: Path) -> None:
    assert hook.denial(read_of(tmp_path)) is None


def test_an_empty_file_is_allowed(tmp_path: Path) -> None:
    target = tmp_path / "empty.md"
    target.write_text("", encoding="utf-8")
    assert hook.denial(read_of(target)) is None


# --- the stdin contract fails closed (#41, #94) ------------------------------


def test_unreadable_stdin_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, "not json") == 2


def test_a_non_object_payload_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, '["Read", "/etc/passwd"]') == 2


def test_a_call_without_a_file_path_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"tool_name": "Read", "tool_input": {}})) == 2


def test_a_call_without_tool_input_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"tool_name": "Read"})) == 2


def test_an_empty_file_path_is_denied() -> None:
    assert hook.denial({"file_path": "   "}) is not None


def test_a_non_numeric_limit_is_denied(tmp_path: Path) -> None:
    """An argument the hook cannot read is an unbounded read, not a small one."""
    target = a_file(tmp_path, "planner.py", chars=60_000)
    assert hook.denial(read_of(target) | {"limit": "200"}) is not None


def test_a_negative_offset_is_denied(tmp_path: Path) -> None:
    target = a_file(tmp_path, "planner.py", chars=60_000)
    assert hook.denial(read_of(target) | {"offset": -1}) is not None


def test_the_denied_read_says_why_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    target = a_file(tmp_path, "planner.py", chars=60_000)
    assert call(monkeypatch, event(target)) == 2
    assert "offset" in capsys.readouterr().err


def test_another_tool_routed_here_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`Edit` names a `file_path` too; a widened matcher must not turn edits into denials."""
    target = a_file(tmp_path, "planner.py", chars=60_000)
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(target)}})
    assert call(monkeypatch, payload) == 0


# --- the wiring itself (#168, #183) -----------------------------------------


def test_the_hook_is_wired_on_read_once() -> None:
    assert len(list(wired_commands())) == 1


def test_the_wiring_denies_when_the_interpreter_is_missing() -> None:
    """A missing python3 must deny, and only exit 2 blocks a PreToolUse hook.

    A bare `python3 hook.py` exits 127 with no interpreter on PATH, Claude Code
    reads any exit other than 2 as non-blocking, and the oversized read lands —
    #168's finding, one layer further out than the hook's own code can reach. So
    the settings.json wiring maps every hook failure to 2, and this test runs
    that wiring, verbatim, with an empty PATH.
    """
    for command in wired_commands():
        completed = run_wiring(command, stdin="{}", path="/nonexistent")
        assert completed.returncode == 2


def test_the_wiring_still_permits_an_allowed_call() -> None:
    """The other direction of `|| exit 2`: it must not turn every read into a denial."""
    for command in wired_commands():
        stdin = event(HOOKS / "deny-oversized-reads.py")
        completed = run_wiring(command, stdin=stdin, path=os.environ["PATH"])
        assert completed.returncode == 0, completed.stderr


def test_the_wiring_denies_an_oversized_read(tmp_path: Path) -> None:
    """End to end through the wiring: the shape #207 exists to stop."""
    target = a_file(tmp_path, "planner.py", chars=60_000)
    for command in wired_commands():
        completed = run_wiring(command, stdin=event(target), path=os.environ["PATH"])
        assert completed.returncode == 2
        assert "60,000 characters" in completed.stderr


def run_wiring(command: str, *, stdin: str, path: str) -> subprocess.CompletedProcess[str]:
    """Run one settings.json hook command verbatim under a chosen PATH."""
    # S603: the repo's own settings.json wiring, quoted verbatim.
    return subprocess.run(  # noqa: S603
        ["/bin/sh", "-c", command],
        input=stdin,
        env={"PATH": path, "CLAUDE_PROJECT_DIR": str(REPO)},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
