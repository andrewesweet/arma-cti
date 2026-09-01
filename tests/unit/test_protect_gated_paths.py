"""Tests for the gated-path guard, `.claude/hooks/protect-gated-paths.py`.

The hook denies writes to generated files and acceptance specs. #168: it was
wired on Edit|Write only, so a Bash `sed -i`, `tee`, or shell redirect onto the
same paths landed unchecked. These tests pin the Bash classification: every
write shape the issue names is denied, read-shaped commands on the same paths
pass, and anything the hook cannot read is denied — the fail-safe direction
this hook family was already burned on (#94 findings 1-2).
"""

from __future__ import annotations

import io
import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_hook

if TYPE_CHECKING:
    from pathlib import Path

hook = load_hook("protect-gated-paths")

GENERATED = "addons/main/generated/commands.hpp"
SPEC = "tests/specs/campaign.yaml"


def call(monkeypatch: pytest.MonkeyPatch, stdin: str) -> int:
    """Run the hook's stdin contract and return the exit code it would use."""
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return hook.main()


def bash(monkeypatch: pytest.MonkeyPatch, command: str) -> int:
    return call(
        monkeypatch,
        json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
    )


def git(repo: Path, *args: str) -> None:
    """Run fixture Git, with any failure visible in the assertion."""
    completed = subprocess.run(  # noqa: S603 — fixture Git argv only
        ["git", *args],  # noqa: S607 — Git resolves from the test toolchain
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def linked_worktree_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Create a disposable main and linked worktree pair."""
    main = tmp_path / "main-checkout"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(main, "config", "user.email", "test@example.invalid")
    git(main, "config", "user.name", "test")
    (main / "ordinary.txt").write_text("before\n", encoding="utf-8")
    git(main, "add", "ordinary.txt")
    git(main, "commit", "-q", "-m", "base")

    assigned = tmp_path / "assigned-worktree"
    git(main, "worktree", "add", "-q", "--detach", str(assigned), "HEAD")
    return main, assigned


# --- write shapes onto a gated path are denied ------------------------------


def test_a_redirect_onto_a_generated_file_is_denied() -> None:
    assert hook.bash_denial(f'echo "class X {{}};" > {GENERATED}') is not None


def test_an_appending_redirect_onto_a_spec_is_denied() -> None:
    assert hook.bash_denial(f"echo 'then: it passes' >> {SPEC}") is not None


def test_an_in_place_sed_on_a_generated_file_is_denied() -> None:
    assert hook.bash_denial(f"sed -i 's/old/new/' {GENERATED}") is not None


def test_an_in_place_sed_with_a_clustered_flag_is_denied() -> None:
    assert hook.bash_denial(f"sed -Ei 's/old/new/' {SPEC}") is not None


def test_a_tee_onto_a_spec_is_denied() -> None:
    assert hook.bash_denial(f"cat /tmp/draft.yaml | tee {SPEC}") is not None


def test_an_rm_of_a_generated_file_is_denied() -> None:
    assert hook.bash_denial(f"rm {GENERATED}") is not None


def test_an_rm_of_the_generated_directory_itself_is_denied() -> None:
    assert hook.bash_denial("rm -rf addons/main/generated") is not None


def test_a_cp_onto_a_spec_is_denied() -> None:
    assert hook.bash_denial(f"cp /tmp/draft.yaml {SPEC}") is not None


def test_a_cp_into_the_specs_directory_is_denied() -> None:
    assert hook.bash_denial("cp /tmp/draft.yaml tests/specs/") is not None


def test_a_cp_with_a_target_directory_flag_is_denied() -> None:
    assert hook.bash_denial("cp -t tests/specs /tmp/draft.yaml") is not None


def test_a_mv_onto_a_generated_file_is_denied() -> None:
    assert hook.bash_denial(f"mv /tmp/generated.hpp {GENERATED}") is not None


def test_a_touch_of_a_spec_is_denied() -> None:
    assert hook.bash_denial(f"touch {SPEC}") is not None


def test_a_truncate_of_a_generated_file_is_denied() -> None:
    assert hook.bash_denial(f"truncate -s 0 {GENERATED}") is not None


def test_a_dd_writing_onto_a_spec_is_denied() -> None:
    assert hook.bash_denial(f"dd if=/tmp/draft.yaml of={SPEC}") is not None


def test_a_heredoc_redirected_onto_a_spec_is_denied() -> None:
    command = f"cat > {SPEC} <<'EOF'\ngiven: a Campaign\nEOF"
    assert hook.bash_denial(command) is not None


def test_a_write_behind_a_chain_is_denied() -> None:
    assert hook.bash_denial(f"just check && sed -i 's/a/b/' {GENERATED}") is not None


def test_a_write_on_a_later_line_is_denied() -> None:
    assert hook.bash_denial(f"git status\ntee {SPEC} < /tmp/draft.yaml") is not None


def test_a_relative_path_from_inside_the_addon_is_denied() -> None:
    assert hook.bash_denial("cd addons/main && sed -i 's/a/b/' generated/commands.hpp") is not None


# --- read shapes on the same paths pass -------------------------------------


def test_reading_a_generated_file_is_allowed() -> None:
    assert hook.bash_denial(f"cat {GENERATED}") is None


def test_grepping_a_spec_is_allowed() -> None:
    assert hook.bash_denial(f"grep -n given {SPEC}") is None


def test_diffing_a_spec_is_allowed() -> None:
    assert hook.bash_denial(f"diff {SPEC} /tmp/draft.yaml") is None


def test_listing_the_specs_directory_is_allowed() -> None:
    assert hook.bash_denial("ls -la tests/specs/") is None


def test_a_sed_without_in_place_is_a_read_and_is_allowed() -> None:
    assert hook.bash_denial(f"sed -n '1,10p' {SPEC}") is None


def test_copying_a_spec_out_is_a_read_and_is_allowed() -> None:
    assert hook.bash_denial(f"cp {SPEC} /tmp/inspect.yaml") is None


def test_redirecting_a_read_of_a_spec_elsewhere_is_allowed() -> None:
    assert hook.bash_denial(f"grep given {SPEC} > /tmp/hits.txt") is None


def test_a_gated_path_inside_a_quoted_string_is_prose() -> None:
    assert hook.bash_denial(f'gh issue comment 168 --body "never sed -i {SPEC} by hand"') is None


def test_a_gated_path_in_a_heredoc_body_is_prose() -> None:
    command = f"cat > /tmp/note.md <<'EOF'\nnever run tee {SPEC}\nEOF"
    assert hook.bash_denial(command) is None


def test_a_write_to_an_ungated_path_is_allowed() -> None:
    assert hook.bash_denial("echo done > /tmp/status.txt") is None


def test_an_ordinary_command_is_allowed() -> None:
    assert hook.bash_denial("just fast") is None


# --- uncertainty is denied ---------------------------------------------------


def test_an_unbalanced_quote_is_denied() -> None:
    assert hook.bash_denial("echo 'unclosed") is not None


def test_an_unterminated_heredoc_is_denied() -> None:
    assert hook.bash_denial("cat <<'EOF' > /tmp/note.md\nno end marker") is not None


# --- the Edit/Write leg is unchanged ----------------------------------------


def test_editing_a_generated_file_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": GENERATED}})
    assert call(monkeypatch, stdin) == 2


def test_writing_a_spec_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = json.dumps({"tool_name": "Write", "tool_input": {"file_path": SPEC}})
    assert call(monkeypatch, stdin) == 2


def test_editing_an_ungated_file_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/cti_daemon/port.py"}})
    assert call(monkeypatch, stdin) == 0


def test_an_absolute_target_outside_the_assigned_worktree_is_denied(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """#666: an absolute main target is denied from any checkout layout."""
    main, assigned = linked_worktree_pair(tmp_path)
    monkeypatch.setattr(hook, "REPO", assigned)
    target = str(main / "main-checkout-probe.md")
    patch = f"*** Begin Patch\n*** Update File: {target}\n@@\n-before\n+after\n*** End Patch\n"

    assert (
        call(monkeypatch, json.dumps({"tool_name": "apply_patch", "tool_input": {"patch": patch}}))
        == 2
    )
    assert bash(monkeypatch, f"touch {target}") == 2


def test_a_custom_gitdir_still_identifies_the_main_checkout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A non-standard metadata location must not make a main target safe."""
    main = tmp_path / "main-checkout"
    common_git = main / ".git"
    common_git.mkdir(parents=True)
    (common_git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    assigned = tmp_path / "assigned-worktree"
    assigned.mkdir()
    metadata = tmp_path / "metadata" / "nested" / "worktrees" / "issue-666"
    metadata.mkdir(parents=True)
    (metadata / "commondir").write_text(f"{common_git}\n", encoding="utf-8")
    (assigned / ".git").write_text(f"gitdir: {metadata}\n", encoding="utf-8")

    monkeypatch.setattr(hook, "REPO", assigned)
    assert bash(monkeypatch, f"touch {main / 'main-checkout-probe.md'}") == 2


@pytest.mark.parametrize("git_state", ["malformed_marker", "missing_head"])
def test_unreadable_git_metadata_denies_even_an_assigned_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    git_state: str,
) -> None:
    """Unknown checkout metadata must not silently disable containment."""
    assigned = tmp_path / "assigned-worktree"
    assigned.mkdir()
    git_path = assigned / ".git"
    if git_state == "malformed_marker":
        git_path.write_text("not a gitdir marker\n", encoding="utf-8")
    else:
        git_path.mkdir()

    monkeypatch.setattr(hook, "REPO", assigned)
    assert bash(monkeypatch, f"touch {assigned / 'ordinary.txt'}") == 2


# --- the stdin contract fails closed (#94 findings 1-2) ----------------------


def test_a_denied_bash_command_exits_two_and_says_why(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert bash(monkeypatch, f"tee {SPEC}") == 2
    assert "sign-off gated" in capsys.readouterr().err


def test_an_allowed_bash_command_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    assert bash(monkeypatch, "git status") == 0


def test_a_bash_call_without_a_command_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"tool_name": "Bash", "tool_input": {}})) == 2


def test_unreadable_stdin_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, "not json") == 2


def test_an_edit_call_without_a_path_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"tool_name": "Edit", "tool_input": {}})) == 2


def test_the_wiring_denies_when_the_interpreter_is_missing() -> None:
    """A missing python3 must deny, and only exit 2 blocks a PreToolUse hook.

    A bare `python3 hook.py` exits 127 with no interpreter on PATH, Claude Code
    reads any exit other than 2 as non-blocking, and the write lands — the #94
    fail-open class, one layer further out than the hook's own code can reach.
    So the settings.json wiring itself maps every hook failure to 2, and this
    test runs that wiring, verbatim, with an empty PATH.
    """
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        wired["command"]
        for entry in settings["hooks"]["PreToolUse"]
        for wired in entry["hooks"]
        if "protect-gated-paths" in wired["command"]
    ]
    assert len(commands) == 2  # wired on Edit|Write and on Bash
    for command in commands:
        # S603: the repo's own settings.json wiring, quoted verbatim.
        completed = subprocess.run(  # noqa: S603
            ["/bin/sh", "-c", command],
            input="{}",
            env={"PATH": "/nonexistent", "CLAUDE_PROJECT_DIR": str(REPO)},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert completed.returncode == 2
