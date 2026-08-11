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


def test_a_rescinding_adr_without_the_trailer_is_a_finding() -> None:
    source = "# A decision\n\nDate: 2026-08-11\n\nADR-0061 decision 2 is rescinded.\n"
    findings = check_adr_form.scan_source(source, "docs/adr/0071-x.md")
    assert [f.missing for f in findings] == ["`Supersedes:` line"]


def test_a_rescinding_adr_with_the_trailer_passes() -> None:
    source = (
        "# A decision\n\nDate: 2026-08-11\nSupersedes: ADR-0061 decision 2\n\n"
        "ADR-0061 decision 2 is rescinded.\n"
    )
    assert check_adr_form.scan_source(source, "docs/adr/0071-x.md") == []


def test_an_empty_supersedes_line_does_not_count_as_one() -> None:
    source = "# A decision\n\nSupersedes:\n\nADR-0061 decision 2 is rescinded.\n"
    findings = check_adr_form.scan_source(source, "docs/adr/0071-x.md")
    assert [f.missing for f in findings] == ["`Supersedes:` line"]


def test_the_domain_sense_of_the_word_is_not_a_rescission() -> None:
    # ADR-0005's presence reports supersede one another, and ADR-0005 amends two
    # of its own clauses. Neither takes a prior *ruling* out of force, so neither
    # is this check's business — which is why the trigger needs both words.
    for wording in (
        "because the next report carries the whole picture again and supersedes it",
        "Two clauses above are superseded",
    ):
        assert check_adr_form.scan_source(f"# A decision\n\n{wording}.\n", "x.md") == []


def test_the_trailer_is_required_regardless_of_who_decided() -> None:
    # ADR-0071 carries `Delegated-decision: no` — every ruling in it was the
    # human's — and still rescinds four decisions of ADR-0061.
    source = "Delegated-decision: no\n\nADR-0061 decision 4 is rescinded.\n"
    findings = check_adr_form.scan_source(source, "docs/adr/0071-x.md")
    assert [f.missing for f in findings] == ["`Supersedes:` line"]


def test_the_wordings_an_adr_actually_uses_all_trigger() -> None:
    # The first version of this check recognised only `rescind` and `supersede`,
    # and so missed every one of ADR-0071's four principal withdrawals — it fired
    # on one incidental sentence and looked like it worked.
    for wording in (
        "ADR-0061 decisions 2, 3 and 4 are withdrawn",
        "ADR-0061 decision 6 is rescinded",
        "This ADR supersedes ADR-0014's mechanism",
        "Amends ADR-0022's declined-runbook clause",
        "the ruling is repealed",
        "this decision replaces the mapping of 2026-08-04",
    ):
        assert check_adr_form.rescinds_a_ruling(wording), wording


def test_a_negated_or_hypothetical_rescission_is_not_one() -> None:
    for wording in (
        "This ADR does not supersede ADR-0014",
        "Nothing here rescinds ADR-0061 decision 5",
        "ADR-0061 decision 5 is never withdrawn by this",
    ):
        assert not check_adr_form.rescinds_a_ruling(wording), wording


def test_adrs_written_before_the_convention_are_not_checked() -> None:
    source = "# A decision\n\nThis ADR supersedes ADR-0014's mechanism.\n"
    assert check_adr_form.scan_source(source, "docs/adr/0031-x.md") == []
    findings = check_adr_form.scan_source(source, "docs/adr/0071-x.md")
    assert [f.missing for f in findings] == ["`Supersedes:` line"]


def test_a_trailer_below_the_first_section_is_not_in_the_field_block() -> None:
    # An unanchored search would be satisfied by a line in a body paragraph or a
    # fenced example, which answers no question a reader has.
    source = (
        "# A decision\n\nDate: 2026-08-11\n\n## Body\n\n"
        "ADR-0061 decision 2 is withdrawn.\nSupersedes: ADR-0061 decision 2\n"
    )
    findings = check_adr_form.scan_source(source, "docs/adr/0071-x.md")
    assert [f.missing for f in findings] == ["`Supersedes:` line"]


def test_the_live_adrs_principal_rescissions_are_the_ones_detected() -> None:
    # Without this, the repository-wide pass below is satisfied by a check that
    # fires on one passing sentence while missing what the ADR actually does.
    sources = {
        path.name: path.read_text(encoding="utf-8") for path in check_adr_form.adr_files(REPO)
    }
    carrying = {
        name: text
        for name, text in sources.items()
        if check_adr_form.SUPERSEDES.search(check_adr_form.field_block(text))
    }
    assert carrying, "expected at least one ADR carrying the trailer"
    for name, text in carrying.items():
        triggers = [
            line
            for line in text.splitlines()
            if check_adr_form.RESCISSION.search(line)
            and check_adr_form.GOVERNANCE.search(line)
            and not check_adr_form.NEGATED.search(line)
            and not line.lstrip().startswith("Supersedes:")
        ]
        assert len(triggers) > 1, f"{name}: detected on one line only — {triggers}"
        stripped = "\n".join(
            line for line in text.splitlines() if not line.startswith("Supersedes:")
        )
        findings = check_adr_form.scan_source(stripped, f"docs/adr/{name}")
        assert [f.missing for f in findings] == ["`Supersedes:` line"], name


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
