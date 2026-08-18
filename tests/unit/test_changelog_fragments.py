"""The changelog fragment engine: parse, merge, fold, and the check over it (#358).

Three layers. The pure halves — `parse_fragment`, `collect`, `merge_text` — are
functions over text, so every malformed shape is refused by its own name and
every merge claim is asserted on the exact lines the fold produces. Under them
the writing halves run against real `git` (the same bare-origin arrangement
`test_land.py` uses), because the claims worth making about `fold` are about
what it commits and what it leaves behind, not about string splicing.

The ordering claims are the ones the issue exists for: the merge is a pure
function of the fragment set (two different creation orders in one directory
produce one `[Unreleased]`), and the fold's commit removes every fragment it
merged, so `origin/main` never carries one for the next rebase to inherit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import load_tool

# `check_changelog` imports `changelog_fragments` as a sibling script, so the
# sibling is loaded first and registered under its own name for that import to
# find — the same device `test_land.py` uses for `land` and `worktree`.
changelog_fragments = load_tool("changelog_fragments")
check_changelog = load_tool("check_changelog")

CHANGELOG = """\
# Changelog

## [Unreleased]

### Changed

- Existing entry.

## [1.0.0] - 2026-01-01

### Added

- Released entry.
"""


def _fragment(root: Path, name: str, body: str) -> Path:
    """Write one fragment under `root`, creating `changelog.d/` for it."""
    directory = root / "changelog.d"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_text(body, encoding="utf-8")
    return target


# ------------------------------------------------------------------ the parse


def test_a_sectioned_fragment_parses_into_category_and_text(tmp_path: Path) -> None:
    target = _fragment(
        tmp_path, "358-fold.md", "### Added\n\n- New thing.\n\n### Fixed\n\n- Old bug.\n"
    )
    parsed = changelog_fragments.parse_fragment(target)
    assert parsed.sections == (("Added", "- New thing."), ("Fixed", "- Old bug."))


def test_blank_runs_around_a_sections_text_are_normalised_not_kept(tmp_path: Path) -> None:
    target = _fragment(
        tmp_path, "358-fold.md", "### Added\n\n\n\n- Entry.\n\n\n\n### Fixed\n- Other.\n"
    )
    parsed = changelog_fragments.parse_fragment(target)
    assert parsed.sections == (("Added", "- Entry."), ("Fixed", "- Other."))


def test_a_deeper_heading_is_content_not_structure(tmp_path: Path) -> None:
    """`####` belongs to the entry above it, so it survives the parse verbatim."""
    target = _fragment(
        tmp_path, "358-fold.md", "### Added\n\n- Entry.\n\n#### Detail\n\n- Words.\n"
    )
    parsed = changelog_fragments.parse_fragment(target)
    assert parsed.sections == (("Added", "- Entry.\n\n#### Detail\n\n- Words."),)


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("358-prose.md", "A line before any heading.\n\n### Added\n\n- Entry.\n"),
        ("358-unknown.md", "### Better\n\n- Entry.\n"),
        ("358-duplicate.md", "### Added\n\n- One.\n\n### Added\n\n- Two.\n"),
        ("358-empty.md", "### Added\n\n\n"),
        ("358-bare.md", "Nothing but prose, no heading at all.\n"),
    ],
)
def test_every_malformed_shape_refuses_malformed_with_a_line_that_named_it(
    tmp_path: Path, name: str, body: str
) -> None:
    target = _fragment(tmp_path, name, body)
    with pytest.raises(changelog_fragments.FragmentError) as raised:
        changelog_fragments.parse_fragment(target)
    assert raised.value.kind == "changelog_fragment_malformed"
    assert raised.value.found


def test_the_directory_order_is_issue_number_then_filename_not_enumeration(
    tmp_path: Path,
) -> None:
    _fragment(tmp_path, "412-aardvark.md", "### Fixed\n\n- A.\n")
    _fragment(tmp_path, "358-zulu.md", "### Fixed\n\n- Z.\n")
    _fragment(tmp_path, "358-alpha.md", "### Fixed\n\n- B.\n")
    collected = changelog_fragments.collect(tmp_path)
    assert [fragment.path.name for fragment in collected] == [
        "358-alpha.md",
        "358-zulu.md",
        "412-aardvark.md",
    ]


def test_an_absent_directory_is_no_fragments_rather_than_an_error(tmp_path: Path) -> None:
    assert changelog_fragments.collect(tmp_path) == []


def test_a_stray_filename_is_refused_not_skipped(tmp_path: Path) -> None:
    _fragment(tmp_path, "358-fold.md", "### Added\n\n- Entry.\n")
    _fragment(tmp_path, "NOTES.md", "a note\n")
    with pytest.raises(changelog_fragments.FragmentError) as raised:
        changelog_fragments.collect(tmp_path)
    assert raised.value.kind == "changelog_fragment_malformed"
    assert "stray=NOTES.md" in raised.value.found


# ------------------------------------------------------------------ the merge


def test_entries_append_under_the_category_the_section_already_carries() -> None:
    fragment = changelog_fragments.Fragment(
        Path("/w/changelog.d/358-fold.md"), (("Changed", "- New entry. (#358)"),)
    )
    merged = changelog_fragments.merge_text(CHANGELOG, [fragment])
    assert (
        """
### Changed

- Existing entry.

- New entry. (#358)
"""
        in merged
    )
    # Surgical: the released section is untouched, entries only ever append.
    assert merged.count("## [1.0.0] - 2026-01-01") == 1
    assert "- Released entry." in merged


def test_a_category_the_section_lacks_gains_a_heading_at_its_end() -> None:
    fragment = changelog_fragments.Fragment(
        Path("/w/changelog.d/358-fold.md"), (("Fixed", "- A fix. (#358)"),)
    )
    merged = changelog_fragments.merge_text(CHANGELOG, [fragment])
    head, _, released = merged.partition("## [1.0.0]")
    assert "### Fixed\n\n- A fix. (#358)" in head
    assert "### Fixed" not in released


def test_two_new_categories_land_at_one_edge_in_the_canonical_order() -> None:
    """Both arrive at the section's end; `Removed` precedes `Security` there."""
    fragment = changelog_fragments.Fragment(
        Path("/w/changelog.d/358-fold.md"),
        (("Security", "- A hardening. (#358)"), ("Removed", "- A removal. (#358)")),
    )
    merged = changelog_fragments.merge_text(CHANGELOG, [fragment])
    head = merged.partition("## [1.0.0]")[0]
    assert head.index("### Removed") < head.index("### Security")


def test_a_repeated_heading_keeps_its_place_and_the_fold_appends_to_the_first() -> None:
    doubled = CHANGELOG.replace(
        "- Existing entry.\n", "- Existing entry.\n\n### Changed\n\n- Repeat section.\n"
    )
    fragment = changelog_fragments.Fragment(
        Path("/w/changelog.d/358-fold.md"), (("Changed", "- New entry. (#358)"),)
    )
    merged = changelog_fragments.merge_text(doubled, [fragment])
    head = merged.partition("## [1.0.0]")[0]
    assert "- Existing entry.\n\n- New entry. (#358)\n\n### Changed" in head
    assert "- Repeat section." in head


def test_two_fragments_of_one_category_join_in_issue_order_with_a_blank_between() -> None:
    fragments = [
        changelog_fragments.Fragment(
            Path("/w/changelog.d/412-a.md"), (("Added", "- Four hundred twelve. (#412)"),)
        ),
        changelog_fragments.Fragment(
            Path("/w/changelog.d/358-b.md"), (("Added", "- Three fifty-eight. (#358)"),)
        ),
    ]
    merged = changelog_fragments.merge_text(CHANGELOG, fragments)
    assert "- Three fifty-eight. (#358)\n\n- Four hundred twelve. (#412)" in merged


def test_the_merge_is_a_pure_function_of_the_fragment_set(tmp_path: Path) -> None:
    """The claim `05e478f`'s mis-merge priced: order is the set's, not the disk's."""
    names = ("358-b.md", "358-a.md", "412-c.md")
    merged: set[str] = set()
    for index, order in enumerate((names, tuple(reversed(names)), names[1:] + names[:1])):
        root = tmp_path / f"tree{index}"
        root.mkdir()
        for name in order:
            _fragment(root, name, f"### Added\n\n- Entry {name}.\n")
        merged.add(changelog_fragments.merge_text(CHANGELOG, changelog_fragments.collect(root)))
    assert len(merged) == 1


def test_the_trailing_newline_is_the_files_own_state_kept_not_normalised() -> None:
    fragment = changelog_fragments.Fragment(
        Path("/w/changelog.d/358-fold.md"), (("Added", "- Entry. (#358)"),)
    )
    with_newline = changelog_fragments.merge_text(CHANGELOG, [fragment])
    assert with_newline.endswith("- Released entry.\n")
    bare = changelog_fragments.merge_text(CHANGELOG.rstrip("\n"), [fragment])
    assert not bare.endswith("\n")


def test_no_unreleased_heading_refuses_before_anything_is_written() -> None:
    fragment = changelog_fragments.Fragment(
        Path("/w/changelog.d/358-fold.md"), (("Added", "- Entry. (#358)"),)
    )
    with pytest.raises(changelog_fragments.FragmentError) as raised:
        changelog_fragments.merge_text("# Changelog\n\n## [1.0.0]\n", [fragment])
    assert raised.value.kind == "changelog_unreleased_missing"


# ----------------------------------------------------------- the fold over git


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


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A committed repository with a `CHANGELOG.md` shaped like the real one."""
    _git("init", "--initial-branch=main", str(tmp_path), cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=tmp_path)
    _git("config", "user.name", "T", cwd=tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    _git("add", "CHANGELOG.md", cwd=tmp_path)
    _git("commit", "-m", "chore: seed changelog", cwd=tmp_path)
    return tmp_path


def test_the_fold_commits_the_merge_and_removes_every_fragment(tree: Path) -> None:
    _fragment(tree, "358-fold.md", "### Changed\n\n- Folded entry. (#358)\n")
    # Committed, as a branch carries it: the fold's commit then shows the fragment
    # leaving the tree beside the entries arriving in the changelog.
    _git("add", "-A", cwd=tree)
    _git("commit", "-m", "feat: record the entry", cwd=tree)

    result = changelog_fragments.fold(tree)

    assert result.refusal is None
    assert result.merged == 1
    assert result.line.startswith("changelog=merged 1 fragment(s) as ")
    assert not (tree / "changelog.d" / "358-fold.md").exists()
    assert "- Folded entry. (#358)" in (tree / "CHANGELOG.md").read_text(encoding="utf-8")
    # The fold is one commit touching the changelog and the directory, nothing else.
    subject = _git("log", "-1", "--format=%s", cwd=tree).strip()
    assert subject == "chore(changelog): fold 1 fragment(s) into [Unreleased]"
    touched = _git("show", "--name-only", "--format=", "HEAD", cwd=tree).split()
    assert set(touched) == {"CHANGELOG.md", "changelog.d/358-fold.md"}
    assert _git("status", "--porcelain", cwd=tree).strip() == ""


def test_a_tree_with_no_fragments_folds_nothing_and_commits_nothing(tree: Path) -> None:
    before = _git("rev-parse", "HEAD", cwd=tree).strip()
    result = changelog_fragments.fold(tree)
    assert result.refusal is None
    assert result.merged == 0
    assert result.line == "changelog=not_needed reason=no_fragments"
    assert _git("rev-parse", "HEAD", cwd=tree).strip() == before


def test_a_malformed_fragment_refuses_and_writes_not_one_byte(tree: Path) -> None:
    _fragment(tree, "358-prose.md", "Prose before a heading.\n\n### Added\n\n- Entry.\n")
    before = (tree / "CHANGELOG.md").read_text(encoding="utf-8")
    head = _git("rev-parse", "HEAD", cwd=tree).strip()

    result = changelog_fragments.fold(tree)

    assert result.refusal is not None
    assert result.refusal.kind == "changelog_fragment_malformed"
    assert (tree / "CHANGELOG.md").read_text(encoding="utf-8") == before
    assert _git("rev-parse", "HEAD", cwd=tree).strip() == head
    assert (tree / "changelog.d" / "358-prose.md").exists()


def test_a_changelog_with_no_unreleased_refuses_by_name(tree: Path) -> None:
    (tree / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    _git("add", "CHANGELOG.md", cwd=tree)
    _git("commit", "-m", "chore: release", cwd=tree)
    _fragment(tree, "358-fold.md", "### Added\n\n- Entry. (#358)\n")
    result = changelog_fragments.fold(tree)
    assert result.refusal is not None
    assert result.refusal.kind == "changelog_unreleased_missing"


def test_fragments_with_no_changelog_refuse_rather_than_making_one(tree: Path) -> None:
    (tree / "CHANGELOG.md").unlink()
    _git("add", "-A", cwd=tree)
    _git("commit", "-m", "chore: remove changelog", cwd=tree)
    _fragment(tree, "358-fold.md", "### Added\n\n- Entry. (#358)\n")
    result = changelog_fragments.fold(tree)
    assert result.refusal is not None
    assert result.refusal.kind == "changelog_missing"


def test_inspect_reports_what_a_fold_would_do_and_writes_nothing(tree: Path) -> None:
    _fragment(tree, "358-fold.md", "### Changed\n\n- Entry. (#358)\n")
    head = _git("rev-parse", "HEAD", cwd=tree).strip()
    result = changelog_fragments.inspect(tree)
    assert result.merged == 1
    assert result.line == "changelog=would_fold 1 fragment(s)"
    assert _git("rev-parse", "HEAD", cwd=tree).strip() == head
    assert (tree / "changelog.d" / "358-fold.md").exists()


def test_inspect_carries_the_refusal_a_fold_would_raise(tree: Path) -> None:
    _fragment(tree, "358-stray.md", "### Added\n\n- Entry.\n")
    _fragment(tree, "notes.txt", "a note\n")
    result = changelog_fragments.inspect(tree)
    assert result.refusal is not None
    assert result.refusal.kind == "changelog_fragment_malformed"


# ------------------------------------------------- the check over the same tree


def _origin_tree(tmp_path: Path) -> Path:
    """A repository with a bare `origin`, for the check's diff against `origin/main`."""
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "--initial-branch=main", str(origin), cwd=tmp_path)
    work = tmp_path / "work"
    _git("clone", str(origin), str(work), cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=work)
    _git("config", "user.name", "T", cwd=work)
    (work / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    _git("add", "CHANGELOG.md", cwd=work)
    _git("commit", "-m", "chore: seed changelog", cwd=work)
    _git("push", "origin", "main", cwd=work)
    return work


def _commit(work: Path, subject: str) -> None:
    target = work / "file.txt"
    target.write_text(subject, encoding="utf-8")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", subject, cwd=work)


def test_a_user_visible_commit_with_a_fragment_is_clear(tmp_path: Path) -> None:
    work = _origin_tree(tmp_path)
    _commit(work, "feat: a visible thing")
    _fragment(work, "358-fragments.md", "### Added\n\n- A visible thing. (#358)\n")
    assert check_changelog.scan(work) == []


def test_a_user_visible_commit_with_a_changelog_edit_is_still_clear(tmp_path: Path) -> None:
    """The requirement, not the mechanism: the shared-file edit remains an entry."""
    work = _origin_tree(tmp_path)
    _commit(work, "fix: a repair")
    changelog = work / "CHANGELOG.md"
    changelog.write_text(
        CHANGELOG.replace("- Existing entry.\n", "- Existing entry.\n\n- A repair. (#358)\n"),
        encoding="utf-8",
    )
    _git("add", "CHANGELOG.md", cwd=work)
    _git("commit", "-m", "chore: entry", cwd=work)
    assert check_changelog.scan(work) == []


def test_a_user_visible_commit_with_no_entry_anywhere_is_a_finding(tmp_path: Path) -> None:
    work = _origin_tree(tmp_path)
    _commit(work, "feat: a visible thing")
    findings = check_changelog.scan(work)
    assert len(findings) == 1
    assert "no changelog entry" in findings[0].detail
    assert "changelog.d/" in findings[0].remedy


def test_a_breaking_commit_of_any_type_owes_an_entry(tmp_path: Path) -> None:
    work = _origin_tree(tmp_path)
    _commit(work, "refactor!: a breaking change")
    _fragment(work, "358-fragments.md", "### Changed\n\n- A breaking change. (#358)\n")
    assert check_changelog.scan(work) == []


@pytest.mark.parametrize(
    ("subject", "owes"),
    [
        ("feat: a feature", True),
        ("fix: a repair", True),
        ("feat(seat)!: breaking", True),
        ("docs: a document", False),
        ("chore: a chore", False),
        ("test: a test", False),
        ("not conventional at all", False),
    ],
)
def test_the_boundary_is_the_commit_type_vocabulary(subject: str, owes: bool) -> None:
    assert check_changelog.needs_entry([subject]) == ([subject] if owes else [])


def test_an_unparseable_fragment_is_a_finding_at_check_time_not_landing_time(
    tmp_path: Path,
) -> None:
    work = _origin_tree(tmp_path)
    _commit(work, "feat: a visible thing")
    _fragment(work, "358-fragments.md", "### Better\n\n- A category that is not one.\n")
    findings = check_changelog.scan(work)
    assert any(finding.detail.startswith("fragment=changelog.d/") for finding in findings)


def test_fragments_with_no_unreleased_to_fold_into_is_a_finding(tmp_path: Path) -> None:
    work = _origin_tree(tmp_path)
    _commit(work, "feat: a visible thing")
    _fragment(work, "358-fragments.md", "### Added\n\n- A visible thing. (#358)\n")
    (work / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    _git("add", "-A", cwd=work)
    _git("commit", "-m", "chore: release everything", cwd=work)
    findings = check_changelog.scan(work)
    assert any("no `## [Unreleased]`" in finding.detail for finding in findings)


def test_a_tree_with_no_origin_main_is_unchecked_not_clear(tmp_path: Path) -> None:
    work = tmp_path / "lonely"
    _git("init", "--initial-branch=main", str(work), cwd=tmp_path)
    findings = check_changelog.scan(work)
    assert len(findings) == 1
    assert "no `origin/main`" in findings[0].detail
    assert "unchecked" in findings[0].remedy
