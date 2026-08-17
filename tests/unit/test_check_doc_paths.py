"""Tests for the doc-path gate (issue #395).

The gate exists because a passage can merge **cleanly** through a rebase and be
made false by what landed underneath it. Its named first case is the one #329
left behind — `docs/agents/orchestration.md` naming `tools/admission.py` after
#328 renamed that file away — and it is pinned here as a test rather than only
as prose, because "it would have caught this" is the claim the issue is about.

Pinned in both directions, like the conflict-marker gate's tests. **Yes**: a
departed path, a glob that selects nothing, and a directory that is gone. **No**:
`origin/main`, `~/.claude/settings.json`, a wiki page under `commands/`, a path
git ignores, and anything inside a fenced block — every one of which is either
not a claim about this tree or not a claim about this tree's *contents*, and a
gate that reds on them reds on documents that are correct.

The self-reference lesson of #186/#207 applies to this module too, in a way the
conflict-marker one does not have to handle: the fixtures below name paths that
are absent by construction (`tools/departed.py`), and this file is not in the
gate's scope — `tools/check_doc_paths.py` judges `docs/**` and `AGENTS.md`
only — so nothing here can red the tree it protects.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

check_doc_paths = load_tool("check_doc_paths")

MARKER = "<!-- absent-path -->"

# A tree with one of everything the rules turn on: a file, a nested file, a file
# under a dotted root, and — by omission — no `spike/` at all, so `spike/x.sqf`
# fails the tracked-root test rather than the resolution one.
TRACKED = [
    "AGENTS.md",
    "tools/trial.py",
    "tools/land.py",
    "docs/adr/0016-phase1.md",
    "docs/reference/arma-wiki/commands/INDEX.md",
    ".claude/agents/cti-planner.md",
]


def _tree() -> Any:
    return check_doc_paths.Tree.of(TRACKED)


def _scan(*lines: str, path: str = "docs/agents/orchestration.md") -> list[Any]:
    return check_doc_paths.scan_source("\n".join(lines) + "\n", path, _tree())


def _git(*args: str, cwd: Path) -> str:
    # S603/S607: fixed literals and tmp_path-derived paths, and `git` off PATH on
    # purpose — the same reasoning as the tool under test.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


# ------------------------------------------------------------------ the first case


def test_the_orchestration_runbook_sentence_is_a_finding() -> None:
    """#395's named first case, in the words #329's clean merge left behind.

    The file it names had been renamed by the very commit the branch was rebased
    onto, and the region never conflicted, so no resolver read it.
    """
    findings = _scan(
        "**The inconsistency this section once stated rather than resolved is closed.**",
        "this branch sits on — carried both out in the code: there is no `tools/admission.py`,",
    )

    assert len(findings) == 1
    assert findings[0].line == 2
    assert findings[0].named == "tools/admission.py"
    assert "`tools/admission.py` is not in the tree" in str(findings[0])


def test_the_orchestration_runbook_sentence_clears_once_marked() -> None:
    """The same sentence, once its author says the absence is the point of it."""
    assert not _scan(
        f"this branch sits on: there is no `tools/admission.py`, the harness is "
        f"`tools/trial.py` {MARKER}",
    )


# ---------------------------------------------------------------------- resolution


def test_a_path_the_tree_carries_is_not_a_finding() -> None:
    assert not _scan("The harness is `tools/trial.py`, and `tools/land.py` calls it.")


def test_a_directory_the_tree_implies_is_not_a_finding() -> None:
    """`docs/adr/` is nobody's tracked file and every ADR's parent."""
    assert not _scan("Binding decisions live in `docs/adr/`.")


def test_a_line_reference_is_not_part_of_the_path() -> None:
    """`tools/land.py:135` is a claim about the file, not about a file of that name."""
    assert not _scan("`_walk_first` (`tools/land.py:135`) takes the entry head.")


def test_a_glob_resolves_when_the_tree_matches_it() -> None:
    assert not _scan("Every seat surface under `.claude/agents/*.md` is generated.")


def test_a_glob_that_selects_nothing_is_a_finding() -> None:
    """A pattern selecting nothing makes the same claim as a name that is gone."""
    findings = _scan("The probes live in `spike/probes/*.sqf`.")

    assert [finding.named for finding in findings] == ["spike/probes/*.sqf"]


def test_a_departed_path_is_reported_at_its_line() -> None:
    findings = _scan("one", "two `tools/departed.py` three", "four")

    assert [(finding.line, finding.named) for finding in findings] == [(2, "tools/departed.py")]


def test_one_line_naming_a_path_twice_reports_it_once() -> None:
    findings = _scan("`tools/departed.py` and again `tools/departed.py`")

    assert len(findings) == 1


# ------------------------------------------------------- what is not a claim at all


def test_a_token_whose_first_segment_is_no_tracked_root_is_not_judged() -> None:
    """`origin/main` and a wiki page's own path are not claims about this tree."""
    assert not _scan("Rebase onto `origin/main`, then read `commands/setDamage.wiki`.")


def test_a_home_path_is_not_judged_against_this_repository() -> None:
    """The `~` in `SEGMENT` earns itself here.

    Without it the token would start at `.claude/`, and a *host* file would resolve
    against this repository's own `.claude/` — a false green, which is the one
    outcome worse than a false red on a gate nobody then trusts.
    """
    assert not _scan("Credentials come from `~/.arma-cti/credentials.env` at mode 0600.")
    assert not _scan("`~/.claude/settings.json` redirects every session on this box.")


def test_a_host_path_under_a_tracked_root_name_is_still_not_judged() -> None:
    """`~/.claude/nothing-here.md` is absent from this tree and is not its business."""
    assert not _scan("RTK's `~/.claude/RTK.md` was deleted from this host on 2026-08-16.")


def test_a_fenced_block_carries_no_inline_span() -> None:
    """Fences are out of scope as a consequence, not as a rule — so pin the consequence."""
    assert not _scan("```python", 'PATHS = ["tools/departed.py"]', "```")


def test_text_outside_backticks_is_not_judged() -> None:
    assert not _scan("The old tools/departed.py is gone.")


# -------------------------------------------------------------------- the marker


def test_a_line_marker_exempts_only_its_own_line() -> None:
    findings = _scan(f"`tools/departed.py` {MARKER}", "`tools/other.py` still counts")

    assert [(finding.line, finding.named) for finding in findings] == [(2, "tools/other.py")]


def test_a_marker_may_carry_its_reason() -> None:
    """A bare marker mid-prose explains nothing to the human who meets it next."""
    assert not _scan("`tools/departed.py` <!-- absent-path: renamed by #328 to tools/trial.py -->")


def test_a_marker_alone_on_a_line_exempts_the_whole_file() -> None:
    """Whole file, not the rest of it: a finding *above* the marker clears too."""
    assert not _scan("`tools/departed.py`", "", MARKER, "", "`tools/other.py`")


def test_a_whole_file_marker_may_carry_its_reason_too() -> None:
    assert not _scan("<!-- absent-path: a dated record -->", "`tools/departed.py`")


def test_a_marker_naming_something_else_is_not_this_marker() -> None:
    findings = _scan("`tools/departed.py` <!-- historical -->")

    assert len(findings) == 1


# ------------------------------------------------------------------------- scope


def test_the_vendored_wiki_is_out_of_scope() -> None:
    """6,690 upstream pages are not ours to mark, and name wiki paths, not ours."""
    assert check_doc_paths.documents(TRACKED) == [
        "AGENTS.md",
        "docs/adr/0016-phase1.md",
    ]


def test_only_markdown_is_judged() -> None:
    assert check_doc_paths.documents(["docs/schema.json", "docs/notes.md"]) == ["docs/notes.md"]


def test_claude_md_is_not_judged_twice() -> None:
    """It is a committed symlink to `AGENTS.md` (#264); judging both judges one file twice."""
    assert check_doc_paths.documents(["AGENTS.md", "CLAUDE.md"]) == ["AGENTS.md"]


# ------------------------------------------------------------- against a real tree


def _fixture_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    _git("init", "--initial-branch=main", str(root), cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=root)
    _git("config", "user.name", "T", cwd=root)
    (root / ".gitignore").write_text(".claude/worktrees/\n", encoding="utf-8")
    (root / "tools").mkdir()
    (root / "tools" / "trial.py").write_text("", encoding="utf-8")
    return root


def _commit_all(root: Path) -> None:
    _git("add", "-A", cwd=root)
    _git("commit", "-m", "feat: fixture", cwd=root)


def test_find_in_tree_reports_a_departed_path(tmp_path: Path) -> None:
    root = _fixture_repo(tmp_path)
    (root / "docs" / "runbook.md").write_text(
        "The harness is `tools/trial.py`, once `tools/admission.py`.\n", encoding="utf-8"
    )
    _commit_all(root)

    findings = check_doc_paths.find_in_tree(root)

    assert [(finding.path, finding.named) for finding in findings] == [
        ("docs/runbook.md", "tools/admission.py")
    ]


def test_a_path_git_ignores_is_runtime_state_and_not_a_finding(tmp_path: Path) -> None:
    """`.claude/worktrees/` is where every dispatched agent works, by design absent.

    Both spellings, because `.gitignore`'s directory patterns end in a slash and
    `git check-ignore` answers about the string it is handed.
    """
    root = _fixture_repo(tmp_path)
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    (root / "docs" / "runbook.md").write_text(
        "Agents work in `.claude/worktrees/` — say, `.claude/worktrees/issue-395`.\n",
        encoding="utf-8",
    )
    _commit_all(root)

    assert not check_doc_paths.find_in_tree(root)


def test_an_untracked_file_does_not_make_a_path_resolve(tmp_path: Path) -> None:
    """Resolution is against `git ls-files`, never the filesystem.

    A build artefact on the machine that built it would otherwise clear a path that
    is red everywhere else — a gate whose answer depends on who ran it.
    """
    root = _fixture_repo(tmp_path)
    (root / "docs" / "runbook.md").write_text("Built into `tools/artefact.py`.\n", encoding="utf-8")
    _commit_all(root)
    (root / "tools" / "artefact.py").write_text("", encoding="utf-8")

    assert [finding.named for finding in check_doc_paths.find_in_tree(root)] == [
        "tools/artefact.py"
    ]


def test_main_prints_every_finding_and_the_remedy_once(
    tmp_path: Path, capsys: Any, monkeypatch: Any
) -> None:
    root = _fixture_repo(tmp_path)
    (root / "docs" / "a.md").write_text("`tools/gone.py`\n", encoding="utf-8")
    (root / "docs" / "b.md").write_text("`tools/also-gone.py`\n", encoding="utf-8")
    _commit_all(root)
    monkeypatch.chdir(root)

    code = check_doc_paths.main([])

    err = capsys.readouterr().err
    assert code == 1
    assert "docs/a.md:1: `tools/gone.py` is not in the tree" in err
    assert "docs/b.md:1: `tools/also-gone.py` is not in the tree" in err
    assert "2 absent path(s) named in 2 document(s)" in err
    assert err.count(MARKER) == 1


def test_main_is_silent_and_green_on_a_clean_tree(
    tmp_path: Path, capsys: Any, monkeypatch: Any
) -> None:
    root = _fixture_repo(tmp_path)
    (root / "docs" / "a.md").write_text("`tools/trial.py`\n", encoding="utf-8")
    _commit_all(root)
    monkeypatch.chdir(root)

    code = check_doc_paths.main([])

    assert code == 0
    assert capsys.readouterr().err == ""
