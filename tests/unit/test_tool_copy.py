"""A session runs its own copy of the project's tools, and #676 makes that copy visible.

`just dispatch` runs `tools/dispatch.py` from the dispatching session's worktree, so a
landing that changes the dispatch path does not govern the session that landed it until
someone notices. The claims here are about the two halves that make the copy visible:

- the dispatch record carries which revision of the governed files the dispatching tree
  actually ran, so a stale dispatcher is tellable from a current one after the fact; and
- `tools/tool_copy.py report` — a `just watch-report` rung — names the drift one line per
  governed path, and never fixes it: rebasing a live session's tree is a judgement, not
  something a report does.

Every claim is made against real git repositories, because each one is a claim about what
git can see: a blob on one side, a ref on the other, an ancestry between two commits. A
stubbed git would let them pass over code that cannot read a tree at all.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

tool_copy = load_tool("tool_copy")

JUSTFILE = """\
demo:
    uv run python tools/a.py run
    uv run python tools/gone.py run
"""


def _git(*args: str, cwd: Path) -> str:
    """Run one git command for its stdout, failing the test on git's own error."""
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _commit_all(root: Path, message: str) -> None:
    _git("add", "-A", cwd=root)
    _git("commit", "-qm", message, cwd=root)


def _repository(path: Path, *, bare: bool = False) -> Path:
    path.mkdir(parents=True)
    _git("init", "-q", "-b", "main", *(("--bare",) if bare else ()), cwd=path)
    if not bare:
        _git("config", "user.email", "t@example.invalid", cwd=path)
        _git("config", "user.name", "t", cwd=path)
    return path


def _seed(root: Path) -> None:
    """Lay down the command machinery a session runs, committed once."""
    (root / "tools").mkdir(parents=True)
    (root / "justfile").write_text(JUSTFILE, encoding="utf-8")
    (root / "tools" / "a.py").write_text("run = 1\n", encoding="utf-8")
    (root / "tools" / "unused.py").write_text("unused = 1\n", encoding="utf-8")
    (root / "README.md").write_text("readme\n", encoding="utf-8")
    hooks = root / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "a.py").write_text("hook = 1\n", encoding="utf-8")
    (hooks / "__pycache__").mkdir()
    (hooks / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\x00")
    (root / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    _commit_all(root, "chore: base")


def _with_origin(tmp_path: Path) -> Path:
    """Give a repository committed governed files and an `origin` it can fetch from."""
    remote = _repository(tmp_path / "remote.git", bare=True)
    root = _repository(tmp_path / "tree")
    _seed(root)
    _git("remote", "add", "origin", str(remote), cwd=root)
    _git("push", "-q", "-u", "origin", "main", cwd=root)
    return root


def _advance_origin_with(
    root: Path, tmp_path: Path, label: str, edit: Callable[[Path], None]
) -> None:
    """Land one commit on `origin/main` built by `edit`, without the local tree moving."""
    ahead = tmp_path / f"ahead-{label}"
    subprocess.run(  # noqa: S603
        ["git", "clone", "-q", str(tmp_path / "remote.git"), str(ahead)],  # noqa: S607
        check=True,
        capture_output=True,
    )
    _git("config", "user.email", "t@example.invalid", cwd=ahead)
    _git("config", "user.name", "t", cwd=ahead)
    edit(ahead)
    _commit_all(ahead, "feat: ahead")
    _git("push", "-q", "origin", "main", cwd=ahead)
    _git("fetch", "-q", "origin", cwd=root)


def _advance_origin(root: Path, tmp_path: Path, path: str, content: str) -> None:
    """Land one commit on `origin/main` that changes `path`, without the local tree moving."""

    def write(ahead: Path) -> None:
        target = ahead / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    _advance_origin_with(root, tmp_path, path.replace("/", "-"), write)


def test_governed_paths_are_the_machinery_directories_and_their_wiring(tmp_path: Path) -> None:
    root = _with_origin(tmp_path)
    names = {str(path) for path in tool_copy.governed_paths(root)}
    # The whole of tools/ — the helpers dispatch.py imports and runs are machinery no
    # recipe names — beside the hook surface, the wiring and the justfile. Naming a
    # landed change to a tool this session never invoked is the correct direction of
    # error (#676's narrowing ruling): "your copy is not what landed" stays true either
    # way, while under-reporting silently ships a stale dispatcher.
    assert names == {
        "justfile",
        "tools/a.py",
        "tools/unused.py",
        ".claude/hooks/a.py",
        ".claude/settings.json",
    }


def test_a_tree_behind_origin_main_is_named_per_governed_path(tmp_path: Path) -> None:
    root = _with_origin(tmp_path)
    _advance_origin(root, tmp_path, "tools/a.py", "run = 2\n")

    survey = tool_copy.survey(root)

    assert survey.behind_origin_main is True
    assert survey.stale_paths() == ("tools/a.py",)


def test_a_path_origin_main_did_not_touch_is_not_drift(tmp_path: Path) -> None:
    root = _with_origin(tmp_path)
    _advance_origin(root, tmp_path, "README.md", "changed readme\n")

    survey = tool_copy.survey(root)

    # The tree is behind `origin/main`, but nothing it runs changed — the drift is
    # path-scoped, never a whole-tree verdict.
    assert survey.behind_origin_main is True
    assert survey.stale_paths() == ()


def test_a_tree_carrying_its_own_commits_is_never_named_behind(tmp_path: Path) -> None:
    root = _with_origin(tmp_path)
    (root / "tools" / "a.py").write_text("run = 3\n", encoding="utf-8")
    _commit_all(root, "feat: this session's own work")

    survey = tool_copy.survey(root)

    assert survey.behind_origin_main is False
    assert survey.stale_paths() == ()


def test_a_governed_path_origin_main_does_not_have_is_never_named_behind(
    tmp_path: Path,
) -> None:
    root = _with_origin(tmp_path)
    (root / "tools" / "b.py").write_text("b = 1\n", encoding="utf-8")
    (root / "justfile").write_text(
        JUSTFILE + "    uv run python tools/b.py run\n", encoding="utf-8"
    )

    survey = tool_copy.survey(root)

    # The tree is behind `origin/main` — but this path is this session's own new work,
    # which no landing has superseded, so the report stays silent about it. The justfile
    # the session itself edited, by contrast, is named: its bytes are not what landed,
    # which is the drift this module exists to name.
    assert survey.behind_origin_main is True
    assert "tools/b.py" not in survey.stale_paths()
    assert survey.stale_paths() == ("justfile",)
    assert "tools/b.py" in survey.paths


def test_a_governed_path_only_origin_main_has_is_surveyed_and_named(tmp_path: Path) -> None:
    root = _with_origin(tmp_path)

    def add(ahead: Path) -> None:
        (ahead / "tools" / "new.py").write_text("new = 1\n", encoding="utf-8")
        (ahead / "justfile").write_text(
            JUSTFILE + "    uv run python tools/new.py run\n", encoding="utf-8"
        )

    _advance_origin_with(root, tmp_path, "adds-a-tool", add)

    survey = tool_copy.survey(root)

    # A landing that adds machinery this tree's justfile has never heard of is the case
    # this issue is most about: the union of the two governed sets is what is walked, so
    # the origin side's new path is named even though no local set could have held it.
    assert survey.behind_origin_main is True
    assert survey.stale_paths() == ("justfile", "tools/new.py")
    assert survey.paths["tools/new.py"]["worktree"] == ""
    assert survey.paths["tools/new.py"]["origin_main"]


def test_a_governed_path_origin_main_deleted_is_named_behind(tmp_path: Path) -> None:
    root = _with_origin(tmp_path)

    def delete(ahead: Path) -> None:
        (ahead / "tools" / "a.py").unlink()

    _advance_origin_with(root, tmp_path, "deletes-a-tool", delete)

    survey = tool_copy.survey(root)

    # A path the landing removed is not "nothing to say": it is a landed removal this
    # tree has not taken yet, named like any other drift. The `head` blob is what tells
    # it from this session's own new work, which HEAD does not hold either.
    assert survey.behind_origin_main is True
    assert "tools/a.py" in survey.stale_paths()
    assert survey.paths["tools/a.py"]["origin_main"] == ""
    assert survey.paths["tools/a.py"]["head"]


def test_a_failing_ancestry_check_is_untellable_not_current(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _with_origin(tmp_path)
    _advance_origin(root, tmp_path, "tools/a.py", "run = 2\n")
    # `merge-base --is-ancestor` answers in its exit code — 0 yes, 1 no — and errors with
    # 128. Head's own commit object removed makes that real: the origin side still reads,
    # while the ancestry question cannot be answered at all.
    head = _git("rev-parse", "HEAD", cwd=root)
    (root / ".git" / "objects" / head[:2] / head[2:]).unlink()

    survey = tool_copy.survey(root)

    # Git failing to answer is untellable, never a folded "no": the rung says so out loud
    # rather than reading as health.
    assert survey.behind_origin_main is None
    assert survey.stale_paths() == ()
    assert tool_copy.main(["report", "--repo", str(root)]) == 0
    assert "cannot tell" in capsys.readouterr().out


def test_an_origin_main_that_cannot_be_read_is_reported_as_untellable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repository(tmp_path / "tree")
    _seed(root)

    survey = tool_copy.survey(root)

    assert survey.behind_origin_main is None
    assert tool_copy.main(["report", "--repo", str(root)]) == 0
    assert "cannot tell" in capsys.readouterr().out


def test_the_report_is_silent_while_current_and_loud_per_path_otherwise(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _with_origin(tmp_path)
    assert tool_copy.main(["report", "--repo", str(root)]) == 0
    assert capsys.readouterr().out == ""

    _advance_origin(root, tmp_path, "tools/a.py", "run = 2\n")
    _advance_origin(root, tmp_path, ".claude/hooks/a.py", "hook = 2\n")

    assert tool_copy.main(["report", "--repo", str(root)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert all(line.startswith("tool-copy: ") for line in lines)
    assert any("tools/a.py" in line for line in lines)
    assert any(".claude/hooks/a.py" in line for line in lines)


def test_the_record_document_names_both_sides_of_a_drifted_path(tmp_path: Path) -> None:
    root = _with_origin(tmp_path)
    _advance_origin(root, tmp_path, "tools/a.py", "run = 2\n")

    document = tool_copy.survey(root).document()

    drifted = document["paths"]
    assert sorted(drifted) == ["tools/a.py"]
    assert drifted["tools/a.py"]["worktree"]
    assert drifted["tools/a.py"]["origin_main"]
    assert drifted["tools/a.py"]["worktree"] != drifted["tools/a.py"]["origin_main"]


def test_a_path_only_the_origin_set_governs_is_hashed_not_named_superseded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round three, finding 3: "not hashed" was being read as "not present".

    Origin newly governs a file this tree holds byte-identical, but the local set does not
    name it — here arranged with a narrowed local set, the shape a future set definition
    could produce. The union walk must hash the file the tree actually holds rather than
    read the absent map entry as an empty worktree sha and report the path superseded.
    """
    root = _with_origin(tmp_path)
    (root / "tools" / "extra.py").write_text("extra = 1\n", encoding="utf-8")

    def add(ahead: Path) -> None:
        (ahead / "tools" / "extra.py").write_text("extra = 1\n", encoding="utf-8")
        (ahead / "justfile").write_text(
            JUSTFILE + "    uv run python tools/extra.py run\n", encoding="utf-8"
        )

    _advance_origin_with(root, tmp_path, "governs-extra", add)
    monkeypatch.setattr(
        tool_copy,
        "governed_paths",
        lambda _root: (Path("justfile"), Path("tools/a.py")),
    )

    survey = tool_copy.survey(root)

    assert survey.behind_origin_main is True
    assert survey.stale_paths() == ("justfile",)
    assert survey.paths.get("tools/extra.py") is None


def test_a_git_read_that_never_answers_is_untellable_not_a_hang(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round three, finding 4's Python half: the survey is bounded, so the turn-top read is.

    A git that never answers must surface as the typed "cannot tell" verdict the module
    already has, never as a stalled `just watch-report` (ADR-0049). The git here is real
    — a PATH shim that sleeps — and the module's own timeout is shortened for the test.
    """
    root = _with_origin(tmp_path)
    _advance_origin(root, tmp_path, "tools/a.py", "run = 2\n")
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "git").write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    # The file, not the directory: a non-executable candidate on PATH is skipped silently
    # by execvp's search, and the real git answers — the bug the shim exists to catch.
    (shim / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}:{os.environ['PATH']}")
    monkeypatch.setattr(tool_copy, "GIT_TIMEOUT", 1.0)

    survey = tool_copy.survey(root)

    assert survey.behind_origin_main is None
    assert tool_copy.main(["report", "--repo", str(root)]) == 0
    assert "cannot tell" in capsys.readouterr().out
