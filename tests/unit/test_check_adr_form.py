"""Tests for the delegated-decision ADR form gate (ADR-0019, issue #137).

Pinned in both directions, because a rule that only ever passes is
indistinguishable from one that does not run: an ADR missing the section is a
finding, an ADR that has it in any of the spellings the corpus uses is not, and
an ADR without the marker is not this gate's business at all.

The live repository is checked too. That is the assertion #137 was raised over
— the three retrofitted ADRs and every future one — and it is the only form of
this test that a new ADR can fail.
"""

from __future__ import annotations

from conftest import REPO, load_tool

check_adr_form = load_tool("check_adr_form")

FIELDS = "Delegated-decision: yes\nDate: 2026-08-02\nReviewed-by-human: pending\n"


def test_an_adr_with_the_section_passes() -> None:
    source = f"# A decision\n\n{FIELDS}\n## What would overturn this\n\n- Evidence.\n"
    assert check_adr_form.scan_source(source, "docs/adr/0001-x.md") == []


def test_an_adr_without_it_is_a_finding() -> None:
    findings = check_adr_form.scan_source(
        f"# A decision\n\n{FIELDS}\nBody.\n", "docs/adr/0001-x.md"
    )
    assert [f.missing for f in findings] == ["overturning evidence"]


def test_an_adr_with_no_marker_is_not_checked() -> None:
    assert check_adr_form.scan_source("# A decision\n\nDate: 2026-08-02\n\nBody.\n", "x.md") == []


def test_a_marker_set_to_no_is_not_checked() -> None:
    assert check_adr_form.scan_source("Delegated-decision: no\n\nBody.\n", "x.md") == []


def test_the_spellings_the_corpus_actually_uses_all_pass() -> None:
    # ADR-0014 states its overturning evidence per decision in prose, 0022 and
    # 0024 head it "Overturned by", 0027 "What would overturn each decision".
    # The gate asks for the word, not for a heading, so none of them is a
    # finding for spelling its section differently.
    for wording in (
        "## What would overturn this",
        "## Overturned by",
        "## What would overturn each decision",
        "**Overturning evidence:** a playtest showing otherwise.",
        "Overturned only if seeded variety proves too weak.",
    ):
        assert check_adr_form.scan_source(f"{FIELDS}\n{wording}\n", "x.md") == []


def test_a_missing_review_line_is_a_finding() -> None:
    source = "Delegated-decision: yes\n\n## What would overturn this\n\n- Evidence.\n"
    findings = check_adr_form.scan_source(source, "docs/adr/0001-x.md")
    assert [f.missing for f in findings] == ["`Reviewed-by-human:` line"]


def test_an_empty_review_line_does_not_count_as_one() -> None:
    source = "Delegated-decision: yes\nReviewed-by-human:\n\n## Overturned by\n\n- Evidence.\n"
    findings = check_adr_form.scan_source(source, "docs/adr/0001-x.md")
    assert [f.missing for f in findings] == ["`Reviewed-by-human:` line"]


def test_the_repositorys_own_adrs_pass() -> None:
    findings = check_adr_form.scan_tree(REPO)
    assert findings == [], "\n".join(str(f) for f in findings)


def test_the_delegated_decisions_are_found_at_all() -> None:
    # Without this, an empty scan would satisfy the test above.
    sources = [path.read_text(encoding="utf-8") for path in check_adr_form.adr_files(REPO)]
    delegated = [source for source in sources if check_adr_form.MARKER.search(source)]
    assert len(delegated) > 20, f"expected the delegated-decision set, found {len(delegated)}"


def test_nested_agent_worktrees_are_not_scanned() -> None:
    scanned = {path.relative_to(REPO).as_posix() for path in check_adr_form.adr_files(REPO)}
    assert scanned, "expected to find our own ADRs"
    assert all(path.startswith("docs/adr/") for path in scanned)
