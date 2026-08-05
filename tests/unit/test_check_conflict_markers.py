"""Tests for the conflict-marker gate (issue #231, ADR-0062).

Pinned in both directions, because a gate that only ever says yes and a gate
that reds on its own tree fail in exactly opposite ways and this one has to
avoid both.

**Yes**: the diff3 common-ancestor line gets a test of its own, since that is
the form that actually reached `main` in 2b4f99b; and one test takes its fixture
from `git` itself rather than from this file's idea of what a marker looks like,
by driving a real conflicting rebase and reading what git wrote.

**No**: a lone separator is asserted *not* to be a finding, against the six
vendored wiki pages that carry such lines today — an unconditional rule would
red `just check` on the tree it protects, which is #186/#207's self-reference
lesson in its second form.

Its first form governs this file's own source. Every marker below is *derived*
(`"<" * SIZE`) and never written out, and fixtures are written into `tmp_path`
rather than committed, so nothing here is a tracked file the gate would find.
`test_the_live_repository_carries_no_conflict_markers` is the assertion that
keeps it that way: it is the test that fails if a fixture ever leaks into the
tree.

`SIZE` is spelled `7` here rather than imported, so the tests pin git's default
marker size independently of the module that has to agree with it.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

check_conflict_markers = load_tool("check_conflict_markers")

SIZE = 7
OPEN = "<" * SIZE
ORIGIN = "|" * SIZE
SPLIT = "=" * SIZE
CLOSE = ">" * SIZE


# A `tools/` script is loaded by path, so its `Finding` is not a type any
# annotation here could name — `Any` is what the module object hands back.
def _scan(*lines: str) -> list[Any]:
    return check_conflict_markers.scan_source("\n".join(lines) + "\n", "CHANGELOG.md")


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


# --------------------------------------------------------------- the four forms


def test_the_diff3_ancestor_line_is_a_finding_even_with_no_region_around_it() -> None:
    """#231's actual defect: one stray ancestor line, alone, inside 2b4f99b."""
    findings = _scan("### Added", "", f"{ORIGIN} parent of 7bea7f6", "- an entry.")

    assert len(findings) == 1
    assert findings[0].line == 3
    assert "common-ancestor" in findings[0].problem


def test_a_whole_conflict_region_is_reported_line_by_line() -> None:
    findings = _scan(
        f"{OPEN} HEAD",
        "- ours.",
        f"{ORIGIN} parent of d0ee428",
        f"{SPLIT}",
        "- theirs.",
        f"{CLOSE} d0ee428",
    )

    assert [finding.line for finding in findings] == [1, 3, 4, 6]


def test_a_separator_inside_a_region_is_a_finding_and_one_outside_is_not() -> None:
    inside = _scan(f"{OPEN} HEAD", f"{SPLIT}", f"{CLOSE} abc123")
    outside = _scan("Startup Parameters", f"{SPLIT}", "Prose under a setext heading.")

    assert [finding.line for finding in inside] == [1, 2, 3]
    assert outside == []


def test_the_vendored_wiki_separators_are_not_findings() -> None:
    """The concrete false positive an unconditional separator rule would produce."""
    page = REPO / "docs" / "reference" / "arma-wiki" / "topics" / "Crash_Files.wiki"
    source = page.read_text(encoding="utf-8", errors="replace")

    assert f"\n{SPLIT}" in source, "fixture drifted: this page no longer carries a separator line"
    assert check_conflict_markers.scan_source(source, page.name) == []


# ------------------------------------------------------------------ the edges


def test_a_run_one_short_of_the_marker_size_is_not_a_finding() -> None:
    assert _scan(f"{'<' * (SIZE - 1)} HEAD") == []


def test_a_longer_run_is_a_finding_because_conflict_marker_size_can_be_raised() -> None:
    findings = _scan(f"{'<' * 12} HEAD")

    assert len(findings) == 1


def test_a_marker_named_inline_in_prose_is_not_a_finding() -> None:
    """Anchoring to the line start is what lets ADR-0062 and the checker name the forms."""
    assert _scan(f"The form that slipped is `{ORIGIN}`, which diff3 writes.") == []
    assert _scan(f"- `{OPEN}` opens the region.") == []


def test_the_finding_points_at_the_marker() -> None:
    findings = _scan("# Changelog", "", f"{CLOSE} 5a966f3")

    assert str(findings[0]).startswith("CHANGELOG.md:3: ")
    assert "#231" in str(findings[0])


# ------------------------------------------------------- over a real git tree


def test_a_marker_in_a_tracked_file_is_found_and_an_untracked_one_is_not(
    tmp_path: Path,
) -> None:
    """#105's scope: what lands is what is tracked, and untracked files are not judged here."""
    _git("init", "-q", "--initial-branch=main", ".", cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=tmp_path)
    _git("config", "user.name", "T", cwd=tmp_path)
    (tmp_path / "tracked.md").write_text(f"{ORIGIN} parent of 7bea7f6\n", encoding="utf-8")
    (tmp_path / "scratch.md").write_text(f"{OPEN} HEAD\n", encoding="utf-8")
    _git("add", "tracked.md", cwd=tmp_path)
    _git("commit", "-qm", "chore: tracked", cwd=tmp_path)

    findings = check_conflict_markers.find_in_tree(tmp_path)

    assert [finding.path for finding in findings] == ["tracked.md"]


def test_a_real_rebase_conflict_is_caught_in_the_shape_git_actually_writes(
    tmp_path: Path,
) -> None:
    """The fixture comes from git, not from this file's idea of a marker.

    #231's sequence in miniature: two landings touch the same changelog region,
    the second rebases, and the tree it leaves is the tree the next agent would
    resolve against.
    """
    _git("init", "-q", "--initial-branch=main", ".", cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=tmp_path)
    _git("config", "user.name", "T", cwd=tmp_path)
    _git("config", "merge.conflictStyle", "diff3", cwd=tmp_path)
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [Unreleased]\n\n### Added\n\n- base.\n", encoding="utf-8")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-qm", "chore: base", cwd=tmp_path)
    base = _git("rev-parse", "HEAD", cwd=tmp_path).strip()

    changelog.write_text("## [Unreleased]\n\n### Added\n\n- base.\n- theirs.\n", encoding="utf-8")
    _git("commit", "-qam", "feat: theirs", cwd=tmp_path)
    _git("checkout", "-q", "-b", "ours", base, cwd=tmp_path)
    changelog.write_text("## [Unreleased]\n\n### Added\n\n- base.\n- ours.\n", encoding="utf-8")
    _git("commit", "-qam", "feat: ours", cwd=tmp_path)
    # Not `_git`: a conflicting rebase exits non-zero, and that is the arrangement.
    subprocess.run(
        ["git", "rebase", "main"],  # noqa: S607 — `git` off PATH, as everywhere else here
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )

    findings = check_conflict_markers.find_in_tree(tmp_path)

    assert {finding.path for finding in findings} == {"CHANGELOG.md"}
    # All four forms, because diff3 is what this box's global config selects and
    # the ancestor line is the one that reached main.
    assert {finding.mark for finding in findings} == {"<", "|", "=", ">"}


def test_the_live_repository_carries_no_conflict_markers() -> None:
    """The assertion #231 was raised over — and the one this file's fixtures must not fail."""
    assert check_conflict_markers.find_in_tree(REPO) == []
