"""The guarded discard's refusal ladder, and the recipe over a real git repo (#287).

Two layers, both in the no-Arma tier. The rungs are pure functions over the
strings git prints, so every refusal class is asserted by its own name and its
own words; under them sit end-to-end tests against real git in a temporary
repository, because the parsers' subject is git's actual output and a fixture
that only ever saw the strings this file invented would prove nothing about it.

**Every refusal test asserts that the working tree is unchanged afterwards.** A
guard that returned non-zero having already discarded something would be worse
than no guard at all, so "it refused" is only half the assertion and `state(repo)
== before` is the half that matters. `state` covers file bytes *and*
`git status`, because the staged rung's whole claim is about the index.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    import pytest

discard = load_tool("discard")

RULING = "#287 (human ruling 2026-08-08 on #248)"


# ----------------------------------------------------------- parsing git's own


def test_status_splits_the_two_letter_code_from_the_path() -> None:
    parsed = discard.read_status(" M tools/x.py\0?? scratch.txt\0")
    assert [(entry.code, entry.path) for entry in parsed] == [
        (" M", "tools/x.py"),
        ("??", "scratch.txt"),
    ]


def test_a_renames_source_field_is_consumed_and_not_reported_as_a_second_path() -> None:
    r"""Under -z a rename is `XY to\0from\0`, and the file that changed is the destination."""
    parsed = discard.read_status("R  tools/new.py\0tools/old.py\0 M justfile\0")
    assert [entry.path for entry in parsed] == ["tools/new.py", "justfile"]


def test_a_path_carrying_a_space_survives_because_the_separator_is_nul() -> None:
    parsed = discard.read_status(" M docs/a file.md\0")
    assert parsed[0].path == "docs/a file.md"


def test_the_unmerged_codes_are_conflicted_and_the_ordinary_ones_are_not() -> None:
    assert discard.read_status("UU a\0")[0].conflicted
    assert discard.read_status("AA a\0")[0].conflicted
    assert not discard.read_status("MM a\0")[0].conflicted


def test_an_index_change_reads_as_staged_and_a_worktree_only_change_does_not() -> None:
    assert discard.read_status("M  a\0")[0].staged
    assert discard.read_status("MM a\0")[0].staged
    assert not discard.read_status(" M a\0")[0].staged
    assert not discard.read_status("?? a\0")[0].staged


def test_untracked_is_its_own_code_rather_than_an_absence() -> None:
    assert discard.read_status("?? a\0")[0].untracked
    assert not discard.read_status(" M a\0")[0].untracked


def test_worktree_registrations_are_read_off_the_porcelain_listing() -> None:
    listed = discard.read_worktrees(
        "worktree /home/a/repo\nHEAD 1111\nbranch refs/heads/main\n\n"
        "worktree /home/a/repo/.claude/worktrees/issue-1\nHEAD 2222\ndetached\n\n"
    )
    assert [str(path) for path in listed] == [
        "/home/a/repo",
        "/home/a/repo/.claude/worktrees/issue-1",
    ]


# ------------------------------------------------------------------ the rungs


def test_a_blank_ruling_reference_refuses() -> None:
    for blank in ("", "   "):
        refusal = discard.classify_ruling(blank)
        assert refusal.kind == "no_ruling"
        assert "ruling=<empty>" in refusal.found


def test_a_ruling_reference_naming_no_decision_refuses() -> None:
    refusal = discard.classify_ruling("because I said so")
    assert refusal.kind == "unnamed_ruling"
    assert "expected=an issue (#287) or an ADR (ADR-0013)" in refusal.found


def test_an_issue_or_an_adr_is_a_named_decision() -> None:
    assert discard.classify_ruling(RULING) is None
    assert discard.classify_ruling("ADR-0013 delegated decision") is None


def test_zero_and_two_paths_both_refuse_as_not_one_path() -> None:
    for raw in ((), ("",), ("a.py", "b.py")):
        refusal = discard.classify_paths(raw)
        assert refusal.kind == "not_one_path"
    assert discard.classify_paths(("a.py",)) is None


def test_the_number_of_paths_counts_only_the_non_blank_ones() -> None:
    """The recipe always passes a path argument, so an unnamed one arrives as ``''``."""
    refusal = discard.classify_paths(("",))
    assert "paths=0" in refusal.found


def test_every_glob_metacharacter_refuses() -> None:
    for glob in ("tools/*.py", "tools/x?.py", "tools/[ab].py"):
        refusal = discard.classify_paths((glob,))
        assert refusal.kind == "glob"
        assert f"path={glob}" in refusal.found


def test_a_directory_refuses_and_an_untracked_file_refuses() -> None:
    assert discard.classify_target("tools", is_dir=True, tracked=True).kind == "directory"
    assert discard.classify_target("x.py", is_dir=False, tracked=False).kind == "untracked"
    assert discard.classify_target("x.py", is_dir=False, tracked=True) is None


def test_a_path_above_the_worktree_root_refuses() -> None:
    refusal = discard.classify_location(Path("/w"), (Path("/w"),), Path("/elsewhere/x.py"), "../x")
    assert refusal.kind == "outside_worktree"
    assert "worktree=/w" in refusal.found


def test_a_path_inside_another_registered_worktree_refuses_even_though_it_is_nested() -> None:
    """`.claude/worktrees/issue-N` is inside the main checkout and belongs to another agent."""
    refusal = discard.classify_location(
        Path("/w"),
        (Path("/w"), Path("/w/.claude/worktrees/issue-1")),
        Path("/w/.claude/worktrees/issue-1/x.py"),
        ".claude/worktrees/issue-1/x.py",
    )
    assert refusal.kind == "outside_worktree"
    assert "belongs_to=/w/.claude/worktrees/issue-1" in refusal.found


def test_a_path_inside_the_worktree_it_was_run_in_passes_the_location_rung() -> None:
    assert (
        discard.classify_location(Path("/w"), (Path("/w"),), Path("/w/tools/x.py"), "tools/x.py")
        is None
    )


def test_a_path_is_owned_by_the_most_specific_registration_containing_it() -> None:
    """Nested registrations contain the same file; the deeper one owns it."""
    nested = (Path("/w"), Path("/w/.claude/worktrees/issue-1"))
    assert discard.owner_of(nested, Path("/w/.claude/worktrees/issue-1/x.py")) == Path(
        "/w/.claude/worktrees/issue-1"
    )
    assert discard.owner_of(nested, Path("/w/tools/x.py")) == Path("/w")
    assert discard.owner_of(nested, Path("/elsewhere/x.py")) is None


def test_this_projects_own_nesting_passes_the_location_rung() -> None:
    """`<main>/.claude/worktrees/N` is inside the main checkout, and its own files are its own.

    The defect this pins: an any-container rule read the main checkout as a
    second owner and refused every file in every agent worktree, which is the
    only place the command exists to be used.
    """
    mine = Path("/w/.claude/worktrees/issue-287")
    assert (
        discard.classify_location(mine, (Path("/w"), mine), mine / "docs/note.md", "docs/note.md")
        is None
    )


def test_the_location_rung_still_refuses_a_sibling_agent_worktree() -> None:
    """Longest prefix must not weaken the rung that #105 is about."""
    mine = Path("/w/.claude/worktrees/issue-287")
    theirs = Path("/w/.claude/worktrees/issue-other")
    refusal = discard.classify_location(
        mine,
        (Path("/w"), mine, theirs),
        theirs / "x.py",
        "../issue-other/x.py",
    )
    assert refusal.kind == "outside_worktree"
    assert f"belongs_to={theirs}" in refusal.found


def test_the_main_checkout_is_a_foreign_tree_from_inside_a_nested_worktree() -> None:
    """Upwards is refused too: the enclosing checkout is not this agent's to reset."""
    mine = Path("/w/.claude/worktrees/issue-287")
    refusal = discard.classify_location(
        mine, (Path("/w"), mine), Path("/w/README.md"), "../../../README.md"
    )
    assert refusal.kind == "outside_worktree"
    assert "belongs_to=/w" in refusal.found


def test_a_conflicted_path_refuses_before_anything_else_is_considered() -> None:
    refusal = discard.classify_change("a.py", discard.read_status("UU a.py\0"))
    assert refusal.kind == "conflicted"
    assert "status=UU" in refusal.found


def test_a_staged_path_refuses_even_when_it_also_has_an_unstaged_change() -> None:
    refusal = discard.classify_change("a.py", discard.read_status("MM a.py\0"))
    assert refusal.kind == "staged"
    assert "status=MM" in refusal.found


def test_one_other_dirty_path_is_enough_to_refuse_and_it_is_named() -> None:
    refusal = discard.classify_change("a.py", discard.read_status(" M a.py\0?? scratch.txt\0"))
    assert refusal.kind == "other_dirty_path"
    assert "other_dirty=1" in refusal.found
    assert "?? scratch.txt" in refusal.found


def test_a_clean_named_path_in_a_clean_tree_has_nothing_to_discard() -> None:
    refusal = discard.classify_change("a.py", ())
    assert refusal.kind == "nothing_to_discard"


def test_the_named_paths_unstaged_change_alone_passes_every_rung() -> None:
    assert discard.classify_change("a.py", discard.read_status(" M a.py\0")) is None
    assert discard.classify_change("a.py", discard.read_status(" D a.py\0")) is None


# ------------------------------------------------------- against the real thing


def git(*args: str, cwd: Path, check: bool = True) -> str:
    """Run git in the arrangement, failing the test on git's own error."""
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )
    return done.stdout


def a_repo(tmp_path: Path) -> Path:
    """Return a checkout with an `origin` carrying two tracked files on `main`."""
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
    (repo / "sibling.md").write_text("sibling\n", encoding="utf-8")
    git("add", "README.md", "sibling.md", cwd=repo)
    git("commit", "-q", "-m", "base", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    return repo


def state(root: Path) -> tuple[dict[str, str], str]:
    """Every file's bytes under `root`, plus `git status` — the whole of "nothing moved".

    The status half is not decoration: the staged rung's claim is about the
    index, which no amount of reading file bytes would notice.
    """
    files = {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    }
    return files, git("status", "--porcelain", cwd=root)


def run(monkeypatch: pytest.MonkeyPatch, cwd: Path, *argv: str) -> int:
    """Run the tool as the recipe runs it, from inside `cwd`, and return its exit code."""
    monkeypatch.chdir(cwd)
    return discard.main(list(argv))


def lines_of(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Everything the tool printed, whichever stream it chose."""
    captured = capsys.readouterr()
    return [line for line in (captured.out + captured.err).splitlines() if line]


def test_the_permitted_case_discards_the_one_file_and_prints_the_path_and_the_ruling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    (repo / "README.md").write_text("residue an orchestrator-run probe left\n", encoding="utf-8")

    code = run(monkeypatch, repo, "README.md", "--ruling", RULING)
    printed = lines_of(capsys)
    assert code == 0
    assert printed[0] == "ok=discarded"
    assert "path=README.md" in printed
    assert f"ruling={RULING}" in printed
    assert (repo / "README.md").read_text(encoding="utf-8") == "base\n"
    assert git("status", "--porcelain", cwd=repo) == ""


def test_the_permitted_case_restores_a_file_deleted_in_the_working_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A deletion is an unstaged working-tree change like any other."""
    repo = a_repo(tmp_path)
    (repo / "README.md").unlink()

    code = run(monkeypatch, repo, "README.md", "--ruling", RULING)
    assert code == 0
    assert lines_of(capsys)[0] == "ok=discarded"
    assert (repo / "README.md").read_text(encoding="utf-8") == "base\n"


def test_it_reaches_the_file_from_a_subdirectory_by_normalising_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Repository-relative is what the tool computes, not what the caller typed."""
    repo = a_repo(tmp_path)
    nested = repo / "docs"
    nested.mkdir()
    (nested / "note.md").write_text("original\n", encoding="utf-8")
    git("add", "docs/note.md", cwd=repo)
    git("commit", "-q", "-m", "docs: note", cwd=repo)
    (nested / "note.md").write_text("residue\n", encoding="utf-8")

    code = run(monkeypatch, nested, "note.md", "--ruling", RULING)
    assert code == 0
    assert "path=docs/note.md" in lines_of(capsys)
    assert (nested / "note.md").read_text(encoding="utf-8") == "original\n"


def test_a_run_with_no_ruling_reference_refuses_and_discards_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    (repo / "README.md").write_text("residue\n", encoding="utf-8")
    before = state(repo)

    code = run(monkeypatch, repo, "README.md")
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=no_ruling"
    assert state(repo) == before


def test_a_ruling_reference_that_names_no_decision_refuses_and_discards_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    (repo / "README.md").write_text("residue\n", encoding="utf-8")
    before = state(repo)

    code = run(monkeypatch, repo, "README.md", "--ruling", "the orchestrator said so")
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=unnamed_ruling"
    assert state(repo) == before


def test_a_glob_refuses_and_discards_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The shape that would otherwise reach git and match both dirty files at once."""
    repo = a_repo(tmp_path)
    (repo / "README.md").write_text("residue\n", encoding="utf-8")
    (repo / "sibling.md").write_text("residue\n", encoding="utf-8")
    before = state(repo)

    code = run(monkeypatch, repo, "*.md", "--ruling", RULING)
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=glob"
    assert state(repo) == before


def test_two_paths_refuse_and_discard_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    (repo / "README.md").write_text("residue\n", encoding="utf-8")
    (repo / "sibling.md").write_text("residue\n", encoding="utf-8")
    before = state(repo)

    code = run(monkeypatch, repo, "README.md", "sibling.md", "--ruling", RULING)
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=not_one_path"
    assert state(repo) == before


def test_a_directory_refuses_and_discards_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    nested = repo / "docs"
    nested.mkdir()
    (nested / "note.md").write_text("original\n", encoding="utf-8")
    git("add", "docs/note.md", cwd=repo)
    git("commit", "-q", "-m", "docs: note", cwd=repo)
    (nested / "note.md").write_text("residue\n", encoding="utf-8")
    before = state(repo)

    code = run(monkeypatch, repo, "docs", "--ruling", RULING)
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=directory"
    assert state(repo) == before


def test_an_untracked_file_refuses_and_is_left_where_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The #105 shape: an untracked file may be another agent's, and there is no index version."""
    repo = a_repo(tmp_path)
    (repo / "theirs.md").write_text("another agent's uncommitted work\n", encoding="utf-8")
    before = state(repo)

    code = run(monkeypatch, repo, "theirs.md", "--ruling", RULING)
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=untracked"
    assert state(repo) == before


def test_a_conflicted_file_refuses_and_the_resolution_in_progress_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    git("checkout", "-q", "-b", "other", cwd=repo)
    (repo / "README.md").write_text("theirs\n", encoding="utf-8")
    git("commit", "-q", "-am", "feat: theirs", cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    (repo / "README.md").write_text("ours\n", encoding="utf-8")
    git("commit", "-q", "-am", "feat: ours", cwd=repo)
    git("merge", "-q", "other", cwd=repo, check=False)
    before = state(repo)
    assert "UU README.md" in before[1]

    code = run(monkeypatch, repo, "README.md", "--ruling", RULING)
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=conflicted"
    assert state(repo) == before


def test_a_staged_change_refuses_and_the_index_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    (repo / "README.md").write_text("staged work\n", encoding="utf-8")
    git("add", "README.md", cwd=repo)
    before = state(repo)

    code = run(monkeypatch, repo, "README.md", "--ruling", RULING)
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=staged"
    assert state(repo) == before


def test_another_dirty_path_refuses_and_neither_file_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rung that makes this useless as a general cleaner, so it cannot become a `git reset`."""
    repo = a_repo(tmp_path)
    (repo / "README.md").write_text("residue\n", encoding="utf-8")
    (repo / "sibling.md").write_text("someone else's residue\n", encoding="utf-8")
    before = state(repo)

    code = run(monkeypatch, repo, "README.md", "--ruling", RULING)
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=other_dirty_path"
    assert " M sibling.md" in printed
    assert state(repo) == before


def test_an_untracked_file_elsewhere_is_another_dirty_path_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A foreign untracked file is exactly what #105 is about, so it blocks the run."""
    repo = a_repo(tmp_path)
    (repo / "README.md").write_text("residue\n", encoding="utf-8")
    (repo / "theirs.md").write_text("another agent's uncommitted work\n", encoding="utf-8")
    before = state(repo)

    code = run(monkeypatch, repo, "README.md", "--ruling", RULING)
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=other_dirty_path"
    assert state(repo) == before


def test_a_path_outside_the_worktree_refuses_and_the_file_out_there_is_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    outside = tmp_path / "elsewhere.md"
    outside.write_text("not ours\n", encoding="utf-8")
    before = state(repo)

    code = run(monkeypatch, repo, "../elsewhere.md", "--ruling", RULING)
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=outside_worktree"
    assert outside.read_text(encoding="utf-8") == "not ours\n"
    assert state(repo) == before


def test_a_path_in_another_agents_worktree_refuses_and_their_work_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nested under this checkout by path, and another holder's tree by registration (#105)."""
    repo = a_repo(tmp_path)
    theirs = repo / ".claude" / "worktrees" / "issue-1"
    git("worktree", "add", "-q", "--detach", str(theirs), cwd=repo)
    (theirs / "README.md").write_text("another agent's uncommitted work\n", encoding="utf-8")

    code = run(monkeypatch, repo, ".claude/worktrees/issue-1/README.md", "--ruling", RULING)
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=outside_worktree"
    assert any(line.startswith("belongs_to=") for line in printed)
    assert (theirs / "README.md").read_text(
        encoding="utf-8"
    ) == "another agent's uncommitted work\n"


def an_agent_worktree(repo: Path, name: str) -> Path:
    """Add a worktree where this project actually puts them: *inside* the main checkout.

    `a_repo`'s registrations are flat, so nothing built on it can tell an
    any-container ownership rule from a longest-prefix one. `<main>/.claude/
    worktrees/<name>` is the arrangement the recipe is run in, and it is the one
    that caught the defect.
    """
    tree = repo / ".claude" / "worktrees" / name
    git("worktree", "add", "-q", "--detach", str(tree), cwd=repo)
    return tree


def test_the_permitted_case_works_inside_a_worktree_nested_in_the_main_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The only arrangement a dispatched session ever runs in, and it used to refuse.

    Every file under `<main>/.claude/worktrees/N` is contained by the main
    checkout as well as by its own tree, so reading ownership as "any containing
    registration" made the command refuse itself everywhere it exists to be used.
    """
    repo = a_repo(tmp_path)
    mine = an_agent_worktree(repo, "issue-287")
    (mine / "README.md").write_text("residue an orchestrator-run probe left\n", encoding="utf-8")

    code = run(monkeypatch, mine, "README.md", "--ruling", RULING)
    printed = lines_of(capsys)
    assert code == 0, printed
    assert printed[0] == "ok=discarded"
    assert f"worktree={mine}" in printed
    assert (mine / "README.md").read_text(encoding="utf-8") == "base\n"
    assert git("status", "--porcelain", cwd=mine) == ""


def test_a_sibling_agent_worktree_still_refuses_from_inside_a_nested_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The protection longest-prefix must not have cost: another holder's tree (#105)."""
    repo = a_repo(tmp_path)
    mine = an_agent_worktree(repo, "issue-287")
    theirs = an_agent_worktree(repo, "issue-other")
    (theirs / "README.md").write_text("another agent's uncommitted work\n", encoding="utf-8")
    before = state(theirs)

    code = run(monkeypatch, mine, "../issue-other/README.md", "--ruling", RULING)
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=outside_worktree"
    assert f"belongs_to={theirs}" in printed
    assert state(theirs) == before


def test_the_enclosing_main_checkout_still_refuses_from_inside_a_nested_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Upwards is foreign too — the main checkout is not the dispatched agent's to reset."""
    repo = a_repo(tmp_path)
    mine = an_agent_worktree(repo, "issue-287")
    (repo / "README.md").write_text("the orchestrator's own uncommitted work\n", encoding="utf-8")
    before = (repo / "README.md").read_text(encoding="utf-8")

    code = run(monkeypatch, mine, "../../../README.md", "--ruling", RULING)
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=outside_worktree"
    assert f"belongs_to={repo}" in printed
    assert (repo / "README.md").read_text(encoding="utf-8") == before


def test_a_clean_named_path_refuses_rather_than_reporting_a_discard_that_did_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    before = state(repo)

    code = run(monkeypatch, repo, "README.md", "--ruling", RULING)
    assert code == 1
    assert lines_of(capsys)[0] == "refusal=nothing_to_discard"
    assert state(repo) == before


def test_outside_a_repository_the_tool_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path / "nowhere"
    outside.mkdir()
    (outside / "x.md").write_text("mine\n", encoding="utf-8")

    code = run(monkeypatch, outside, "x.md", "--ruling", RULING)
    printed = lines_of(capsys)
    assert code == 1
    assert printed[0] == "refusal=git_failed"
    assert any(line.startswith("stderr=") for line in printed)
    assert (outside / "x.md").read_text(encoding="utf-8") == "mine\n"


def test_every_refusal_says_the_fallback_and_the_standing_foreign_files_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refusal that does not say what to do next is what sent two dispatches home empty."""
    repo = a_repo(tmp_path)
    (repo / "README.md").write_text("residue\n", encoding="utf-8")
    (repo / "sibling.md").write_text("residue\n", encoding="utf-8")

    run(monkeypatch, repo, "README.md", "--ruling", RULING)
    action = next(line for line in lines_of(capsys) if line.startswith("action="))
    assert "#105" in action
    assert "orchestrator-clears-residue" in action
