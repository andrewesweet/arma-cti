"""The worktree protocol's refusal ladder, and the recipe over a real git repo (#214).

Two layers, both in the no-Arma tier. The ladders are pure functions over the
strings git prints, so every refusal class is asserted by its own name and its
own words — ADR-0049's requirement, and the reason a rung cannot drift the way
three bash copies of a ladder do.

Under them sit end-to-end tests against real `git worktree` in a temporary
repository, because the parsers' subject is git's actual output and a fixture
that only ever sees the strings this file invented would prove nothing about it.

The heaviest claims here are the ones about what the tool does **not** do: an
occupied tree, a dirty tree and a stale registration all survive their refusal
untouched. CLAUDE.md's rule is that foreign files mean stop and report, never
reset, and #105's damage came from a routine reset over another agent's work —
so "it refused" is only half the assertion, and "the other holder's files are
still there afterwards" is the half that matters.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    import pytest

worktree = load_tool("worktree")

_CLEAN = worktree.Preflight((), ())

MAIN_AND_LINKED = """\
worktree /home/a/repo
HEAD 1111111111111111111111111111111111111111
branch refs/heads/main

worktree /home/a/repo/.claude/worktrees/issue-1
HEAD 2222222222222222222222222222222222222222
detached

"""

STALE_BLOCK = """\
worktree /home/a/repo
HEAD 1111111111111111111111111111111111111111
branch refs/heads/main

worktree /home/a/repo/.claude/worktrees/gone
HEAD 2222222222222222222222222222222222222222
detached
prunable gitdir file points to non-existent location

"""


def holder(
    *,
    registered: bool = True,
    exists: bool = True,
    subject: str = "feat: something",
    status: object = _CLEAN,
    unlanded: int | None = 0,
) -> object:
    """Build a `Holder` in one line, with the field under test varied."""
    registration = (
        worktree.Registration(
            path=Path("/home/a/repo/.claude/worktrees/issue-1"),
            head="2222222",
            branch="",
            prunable="",
            bare=False,
        )
        if registered
        else None
    )
    return worktree.Holder(
        registration=registration,
        exists=exists,
        subject=subject,
        status=status,
        unlanded=unlanded,
        entries=(),
    )


# ----------------------------------------------------------- parsing git's own


def test_registrations_parse_main_first_then_the_linked_worktrees() -> None:
    parsed = worktree.parse_registrations(MAIN_AND_LINKED)
    assert [str(r.path) for r in parsed] == [
        "/home/a/repo",
        "/home/a/repo/.claude/worktrees/issue-1",
    ]
    assert parsed[0].state == "main"
    assert parsed[1].state == "detached"
    assert parsed[1].detached


def test_a_prunable_block_is_still_a_registration() -> None:
    """The stale rung needs the entry, not git's silence about it."""
    parsed = worktree.parse_registrations(STALE_BLOCK)
    assert parsed[1].prunable.startswith("gitdir file points to")


def test_a_final_block_without_a_trailing_blank_line_is_not_dropped() -> None:
    parsed = worktree.parse_registrations("worktree /home/a/repo\nHEAD abc\nbranch refs/heads/main")
    assert len(parsed) == 1
    assert parsed[0].state == "main"


def test_status_splits_tracked_changes_from_untracked_files() -> None:
    status = worktree.read_status(" M justfile\n?? scratch.txt\nA  tools/new.py\n")
    assert status.tracked == (" M justfile", "A  tools/new.py")
    assert status.untracked == ("?? scratch.txt",)
    assert not status.clean


def test_an_empty_status_is_the_clean_tree_the_preflight_wants() -> None:
    assert worktree.read_status("").clean


# ------------------------------------------------------------------- the names


def test_an_empty_name_refuses_with_the_example() -> None:
    refusal = worktree.classify_name("")
    assert refusal.kind == "invalid_name"
    assert "just worktree add issue-214" in refusal.action


def test_a_name_that_is_a_path_refuses() -> None:
    for name in ("../escape", "a/b", ".hidden", "with space", "-flag"):
        refusal = worktree.classify_name(name)
        assert refusal is not None, name
        assert refusal.kind == "invalid_name"


def test_an_issue_name_is_accepted() -> None:
    assert worktree.classify_name("issue-214") is None


# --------------------------------------------------------------- the occupancy


def test_a_free_path_is_not_refused() -> None:
    free = worktree.Holder(None, exists=False, subject="", status=None, unlanded=None, entries=())
    assert worktree.classify_target(Path("/home/a/repo/.claude/worktrees/issue-1"), free) is None


def test_an_occupied_worktree_names_the_other_holder() -> None:
    """#105's damage came from not knowing who else was in the tree (AC2)."""
    path = Path("/home/a/repo/.claude/worktrees/issue-1")
    refusal = worktree.classify_target(
        path,
        holder(
            status=worktree.Preflight((" M justfile",), ("?? notes.md",)),
            unlanded=2,
            subject="feat: another agent's work",
        ),
    )
    assert refusal.kind == "worktree_occupied"
    assert f"worktree={path}" in refusal.found
    assert "holder_head=2222222 feat: another agent's work" in refusal.found
    assert "holder_state=detached" in refusal.found
    assert "holder_uncommitted=2" in refusal.found
    assert "holder_unlanded=2 commits not on origin/main" in refusal.found
    assert "never reset" in refusal.action


def test_an_unreadable_holder_status_is_reported_as_unreadable_not_as_clean() -> None:
    refusal = worktree.classify_target(
        Path("/home/a/repo/.claude/worktrees/issue-1"),
        worktree.Holder(
            registration=worktree.Registration(Path("x"), "2222222", "", "", bare=False),
            exists=True,
            subject="",
            status=None,
            unlanded=None,
            entries=(),
        ),
    )
    assert refusal.kind == "worktree_occupied"
    assert "holder_uncommitted=unreadable" in refusal.found


def test_a_registration_whose_directory_is_gone_is_stale_and_prunes_nothing() -> None:
    refusal = worktree.classify_target(
        Path("/home/a/repo/.claude/worktrees/gone"), holder(exists=False)
    )
    assert refusal.kind == "stale_registration"
    assert "git worktree prune" in refusal.action
    assert "never prunes for you" in refusal.action


def test_an_unregistered_directory_is_occupied_and_its_contents_are_named() -> None:
    refusal = worktree.classify_target(
        Path("/home/a/repo/.claude/worktrees/issue-1"),
        worktree.Holder(
            registration=None,
            exists=True,
            subject="",
            status=None,
            unlanded=None,
            entries=("notes.md", "src"),
        ),
    )
    assert refusal.kind == "worktree_occupied"
    assert "registered=no" in refusal.found
    assert "contents=notes.md, src" in refusal.found


# ---------------------------------------------------------------- the flight


def test_a_clean_tree_passes_the_preflight() -> None:
    assert worktree.classify_preflight(Path("/w"), worktree.Preflight((), ())) is None


def test_foreign_files_refuse_by_name_and_say_never_reset() -> None:
    refusal = worktree.classify_preflight(
        Path("/w"), worktree.Preflight((" M justfile",), ("?? theirs.txt",))
    )
    assert refusal.kind == "dirty_tree"
    assert "tracked= M justfile" in refusal.found
    assert "untracked=?? theirs.txt" in refusal.found
    assert "never reset" in refusal.action


def test_a_long_list_is_truncated_and_says_how_much_it_hid() -> None:
    status = worktree.Preflight((), tuple(f"?? f{n}" for n in range(25)))
    refusal = worktree.classify_preflight(Path("/w"), status)
    assert sum(line.startswith("untracked=") for line in refusal.found) == worktree.HOW_MANY_SHOWN
    assert "and=15 more" in refusal.found


def test_the_mid_run_check_cannot_call_a_dirty_tree_foreign_and_does_not_pretend_to() -> None:
    """A file the caller wrote and a file another agent wrote are the same two lines."""
    unproven = worktree.classify_exclusivity(
        Path("/w"), worktree.Preflight((" M justfile",), ("?? mine.py",))
    )
    assert unproven.kind == "unverified"
    assert "tracked= M justfile" in unproven.found
    assert "untracked=?? mine.py" in unproven.found
    assert "Anything you did not write means stop and report, never reset" in unproven.action
    assert "commit it and check again" in unproven.action
    assert worktree.classify_exclusivity(Path("/w"), worktree.Preflight((), ())) is None


def test_a_refusal_renders_its_class_first_and_its_instruction_last() -> None:
    lines = worktree.Refusal("dirty_tree", ("worktree=/w",), "Stop.").lines()
    assert lines == ("refusal=dirty_tree", "worktree=/w", "action=Stop.")


# --------------------------------------------------------------------- teardown


def test_a_clean_landed_worktree_is_finished_with() -> None:
    assert worktree.classify_done(Path("/w"), holder(unlanded=0)) is None


def test_a_name_git_does_not_know_refuses_rather_than_removing() -> None:
    refusal = worktree.classify_done(Path("/w"), holder(registered=False))
    assert refusal.kind == "no_such_worktree"


def test_unlanded_commits_refuse_and_say_what_removal_would_cost() -> None:
    refusal = worktree.classify_done(Path("/w"), holder(unlanded=3))
    assert refusal.kind == "unlanded_work"
    assert "unlanded=3 commits not on origin/main" in refusal.found
    assert "loses 3 commits" in refusal.action


def test_a_dirty_tree_refuses_teardown_before_the_landed_check() -> None:
    refusal = worktree.classify_done(
        Path("/w"), holder(status=worktree.Preflight((), ("?? theirs.txt",)), unlanded=0)
    )
    assert refusal.kind == "dirty_tree"


def test_an_unreadable_check_fails_closed() -> None:
    """A check that could not run is not a check that passed (#41)."""
    for broken in (holder(status=None), holder(unlanded=None)):
        refusal = worktree.classify_done(Path("/w"), broken)
        assert refusal.kind == "git_failed"
        assert "Nothing was removed." in refusal.action


# ------------------------------------------------------- against the real thing


def git(*args: str, cwd: Path) -> str:
    """Run git in the arrangement, failing the test on git's own error."""
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def a_repo(tmp_path: Path) -> Path:
    """Return a checkout with an `origin` carrying one commit on `main`."""
    origin = tmp_path / "origin.git"
    git("init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    repo = tmp_path / "repo"
    git("clone", "-q", str(origin), str(repo), cwd=tmp_path)
    for key, value in (
        ("user.email", "agent@example.invalid"),
        ("user.name", "Agent"),
        ("commit.gpgsign", "false"),
    ):
        git("config", key, value, cwd=repo)
    git("checkout", "-q", "-b", "main", cwd=repo)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git("add", "README.md", cwd=repo)
    git("commit", "-q", "-m", "base", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    return repo


def run(monkeypatch: pytest.MonkeyPatch, repo: Path, *argv: str) -> int:
    """Run the tool as the recipe runs it, from inside `repo`, and return its exit code."""
    monkeypatch.chdir(repo)
    return worktree.main(list(argv))


def lines_of(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Everything the tool printed, whichever stream it chose."""
    captured = capsys.readouterr()
    return [line for line in (captured.out + captured.err).splitlines() if line]


def test_add_creates_the_worktree_and_prints_the_path_and_the_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    code = run(monkeypatch, repo, "add", "issue-1")
    printed = lines_of(capsys)
    created = repo.resolve() / ".claude" / "worktrees" / "issue-1"
    base = git("rev-parse", "--short", "origin/main", cwd=repo).strip()
    assert code == 0
    assert printed[0] == "ok=worktree_created"
    assert f"worktree={created}" in printed
    assert any(line.startswith(f"base={base} origin/main") for line in printed)
    assert "preflight=clean" in printed
    assert (created / "README.md").exists()
    assert (
        git("rev-parse", "HEAD", cwd=created).strip()
        == git("rev-parse", "origin/main", cwd=repo).strip()
    )


def test_add_over_a_live_worktree_refuses_and_leaves_the_other_agents_work_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC3: the refusal path removes nothing, so a collision costs a dispatch, not work."""
    repo = a_repo(tmp_path)
    run(monkeypatch, repo, "add", "issue-1")
    capsys.readouterr()
    theirs = repo / ".claude" / "worktrees" / "issue-1" / "their-notes.md"
    theirs.write_text("another agent's uncommitted work\n", encoding="utf-8")

    code = run(monkeypatch, repo, "add", "issue-1")
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=worktree_occupied"
    assert "holder_uncommitted=1" in printed
    assert theirs.read_text(encoding="utf-8") == "another agent's uncommitted work\n"


def test_add_over_an_unregistered_directory_refuses_without_deleting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    squatter = repo / ".claude" / "worktrees" / "issue-1"
    squatter.mkdir(parents=True)
    (squatter / "notes.md").write_text("someone's\n", encoding="utf-8")

    code = run(monkeypatch, repo, "add", "issue-1")
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=worktree_occupied"
    assert "contents=notes.md" in printed
    assert (squatter / "notes.md").exists()


def test_add_onto_a_stale_registration_refuses_and_does_not_prune(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    run(monkeypatch, repo, "add", "issue-1")
    capsys.readouterr()
    created = repo / ".claude" / "worktrees" / "issue-1"
    for path in sorted(created.rglob("*"), reverse=True):
        path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
    created.rmdir()

    code = run(monkeypatch, repo, "add", "issue-1")
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=stale_registration"
    assert "issue-1" in git("worktree", "list", "--porcelain", cwd=repo)


def test_an_invalid_name_refuses_before_touching_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    code = run(monkeypatch, repo, "add", "../escape")
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=invalid_name"
    assert not (repo / ".claude").exists()


def test_check_passes_a_fresh_worktree_and_leaves_a_dirty_one_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    run(monkeypatch, repo, "add", "issue-1")
    capsys.readouterr()

    code = run(monkeypatch, repo, "check", "issue-1")
    printed = lines_of(capsys)
    assert code == 0
    assert printed[0] == "ok=preflight_clean"
    assert "unlanded=0" in printed

    foreign = repo / ".claude" / "worktrees" / "issue-1" / "foreign.txt"
    foreign.write_text("not mine\n", encoding="utf-8")
    code = run(monkeypatch, repo, "check", "issue-1")
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=unverified"
    assert "untracked=?? foreign.txt" in printed
    assert foreign.exists()


def test_check_without_a_name_reads_the_tree_the_caller_is_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    run(monkeypatch, repo, "add", "issue-1")
    capsys.readouterr()
    created = repo / ".claude" / "worktrees" / "issue-1"

    code = run(monkeypatch, created, "check")
    printed = lines_of(capsys)
    assert code == 0
    assert f"worktree={created.resolve()}" in printed


def test_list_sweeps_every_registration_and_flags_the_stale_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    run(monkeypatch, repo, "add", "issue-1")
    run(monkeypatch, repo, "add", "issue-2")
    capsys.readouterr()
    gone = repo / ".claude" / "worktrees" / "issue-2"
    for path in sorted(gone.rglob("*"), reverse=True):
        path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
    gone.rmdir()

    code = run(monkeypatch, repo, "list")
    printed = lines_of(capsys)
    assert code == 0
    assert "registrations=3" in printed
    assert sum(line.startswith("live ") for line in printed) == 2
    assert any(line.startswith("stale ") and "issue-2" in line for line in printed)
    assert any("git worktree prune" in line for line in printed)


def test_done_removes_a_clean_landed_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    run(monkeypatch, repo, "add", "issue-1")
    capsys.readouterr()

    code = run(monkeypatch, repo, "done", "issue-1")
    printed = lines_of(capsys)
    assert code == 0
    assert printed[0] == "ok=worktree_removed"
    assert not (repo / ".claude" / "worktrees" / "issue-1").exists()
    assert "issue-1" not in git("worktree", "list", "--porcelain", cwd=repo)


def test_done_refuses_unlanded_commits_and_keeps_the_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The removal git itself allows, and the one that would lose committed work."""
    repo = a_repo(tmp_path)
    run(monkeypatch, repo, "add", "issue-1")
    capsys.readouterr()
    created = repo / ".claude" / "worktrees" / "issue-1"
    (created / "work.md").write_text("landed nowhere\n", encoding="utf-8")
    git("add", "work.md", cwd=created)
    git("commit", "-q", "-m", "feat: unlanded", cwd=created)

    code = run(monkeypatch, repo, "done", "issue-1")
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=unlanded_work"
    assert "unlanded=1 commits not on origin/main" in printed
    assert (created / "work.md").exists()


def test_done_refuses_a_dirty_tree_and_keeps_the_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    run(monkeypatch, repo, "add", "issue-1")
    capsys.readouterr()
    theirs = repo / ".claude" / "worktrees" / "issue-1" / "theirs.txt"
    theirs.write_text("uncommitted\n", encoding="utf-8")

    code = run(monkeypatch, repo, "done", "issue-1")
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=dirty_tree"
    assert theirs.exists()


def test_outside_a_repository_the_tool_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path / "nowhere"
    outside.mkdir()
    code = run(monkeypatch, outside, "list")
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=git_failed"
    assert any(line.startswith("stderr=") for line in printed)
