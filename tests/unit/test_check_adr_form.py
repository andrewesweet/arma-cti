"""Tests for the two ADR form gates: ADR-0019's delegated block, ADR-0071's trailer.

Pinned in both directions, because a rule that only ever passes is
indistinguishable from one that does not run: an ADR missing a required line is a
finding, an ADR that has it in any of the spellings the corpus uses is not, and an
ADR the convention does not reach is not this gate's business at all.

The live repository is checked too. That is the assertion #137 was raised over —
the three retrofitted ADRs and every future one — and it is the only form of this
test that a new ADR can fail.

Three of the supersession tests exist because three independent reviews defeated
three prose-sniffing versions of that check in a row. What replaced it reads no
prose, so those tests now pin the *absence* of inference: the trailer is required
of every governed ADR whatever its body says, and nothing in the body can excuse
it.
"""

from __future__ import annotations

from conftest import REPO, load_tool

check_adr_form = load_tool("check_adr_form")

FIELDS = "Delegated-decision: yes\nDate: 2026-08-02\nReviewed-by-human: pending\n"
BODY = "\n## What would overturn this\n\n- Evidence.\n"


def test_an_adr_with_the_section_passes() -> None:
    source = f"# A decision\n\n{FIELDS}{BODY}"
    assert check_adr_form.scan_source(source, "docs/adr/0001-x.md") == []


def test_an_adr_without_it_is_a_finding() -> None:
    findings = check_adr_form.scan_source(
        f"# A decision\n\n{FIELDS}\n## Body\n\nNothing.\n", "docs/adr/0001-x.md"
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
        "## Notes\n\n**Overturning evidence:** a playtest showing otherwise.",
        "## Notes\n\nOverturned only if seeded variety proves too weak.",
    ):
        assert check_adr_form.scan_source(f"{FIELDS}\n{wording}\n", "x.md") == []


def test_a_missing_review_line_is_a_finding() -> None:
    source = f"Delegated-decision: yes\n{BODY}"
    findings = check_adr_form.scan_source(source, "docs/adr/0001-x.md")
    assert [f.missing for f in findings] == ["`Reviewed-by-human:` line"]


def test_an_empty_review_line_does_not_count_as_one() -> None:
    source = f"Delegated-decision: yes\nReviewed-by-human:\n{BODY}"
    findings = check_adr_form.scan_source(source, "docs/adr/0001-x.md")
    assert [f.missing for f in findings] == ["`Reviewed-by-human:` line"]


def test_a_review_line_in_body_prose_does_not_count() -> None:
    # It would otherwise drop the ADR off the human's `Reviewed-by-human: pending`
    # worklist without a human having seen it — ADR-0013's own grep.
    source = f"Delegated-decision: yes\n{BODY}\nReviewed-by-human: someone said so\n"
    findings = check_adr_form.scan_source(source, "docs/adr/0001-x.md")
    assert [f.missing for f in findings] == ["`Reviewed-by-human:` line"]


def test_a_marker_inside_a_fenced_example_does_not_make_an_adr_delegated() -> None:
    source = "# A decision\n\nDate: 2026-08-02\n\n## Body\n\n```\nDelegated-decision: yes\n```\n"
    assert check_adr_form.scan_source(source, "docs/adr/0001-x.md") == []


def test_overturning_evidence_must_be_in_the_body_not_the_header() -> None:
    source = (
        "Delegated-decision: yes\nReviewed-by-human: pending\nClaimed: no overturn\n\n## Body\n"
    )
    findings = check_adr_form.scan_source(source, "docs/adr/0001-x.md")
    assert [f.missing for f in findings] == ["overturning evidence"]


def test_every_governed_adr_needs_the_trailer_whatever_its_body_says() -> None:
    # The point of the rewrite: no prose decides this. Three earlier versions
    # tried and each was defeated by wording a reviewer supplied in minutes.
    for prose in (
        "ADR-0061 decision 2 is withdrawn.",
        "Routing class 7 is deleted.",
        "The Model roles mapping is replaced.",
        "This ADR does not supersede anything at all.",
        "Nothing here is rescinded.",
        "",
    ):
        findings = check_adr_form.scan_source(
            f"# A decision\n\nDate: 2026-08-11\n\n## Body\n\n{prose}\n", "docs/adr/0071-x.md"
        )
        assert [f.missing for f in findings] == ["`Supersedes:` line"], prose


def test_superseding_nothing_is_said_explicitly() -> None:
    source = "# A decision\n\nDate: 2026-08-11\nSupersedes: none\n\n## Body\n\nNew ground.\n"
    assert check_adr_form.scan_source(source, "docs/adr/0071-x.md") == []


def test_an_empty_trailer_does_not_count_as_one() -> None:
    source = "# A decision\n\nSupersedes:\n\n## Body\n\nADR-0061 decision 2 is withdrawn.\n"
    findings = check_adr_form.scan_source(source, "docs/adr/0071-x.md")
    assert [f.missing for f in findings] == ["`Supersedes:` line"]


def test_a_trailer_below_the_first_section_is_not_in_the_field_block() -> None:
    source = "# A decision\n\nDate: 2026-08-11\n\n## Body\n\nSupersedes: ADR-0061 decision 2\n"
    findings = check_adr_form.scan_source(source, "docs/adr/0071-x.md")
    assert [f.missing for f in findings] == ["`Supersedes:` line"]


def test_a_trailer_inside_a_fenced_example_is_not_a_trailer() -> None:
    source = "# A decision\n\nDate: 2026-08-11\n\n```\nSupersedes: ADR-0001\n```\n\n## Body\n"
    findings = check_adr_form.scan_source(source, "docs/adr/0071-x.md")
    assert [f.missing for f in findings] == ["`Supersedes:` line"]


def test_the_cutoff_is_pinned_on_both_sides() -> None:
    source = "# A decision\n\nDate: 2026-08-11\n\n## Body\n\nADR-0061 decision 2 is withdrawn.\n"
    for number in ("0069", "0070"):
        assert check_adr_form.scan_source(source, f"docs/adr/{number}-x.md") == [], number
    for number in ("0071", "0072", "0100"):
        findings = check_adr_form.scan_source(source, f"docs/adr/{number}-x.md")
        assert [f.missing for f in findings] == ["`Supersedes:` line"], number


def test_a_path_with_no_adr_number_is_not_governed() -> None:
    assert check_adr_form.governed("docs/adr/notes.md") is False
    assert check_adr_form.governed("0071-x.md") is True


def test_the_live_governed_adrs_would_all_fail_without_their_trailers() -> None:
    # Without this, the repository-wide pass below is satisfied by a check that
    # fires on nothing we actually have. Every governed ADR is stripped, not just
    # one, and the trailer is now one line per target so stripping is exact.
    governed = {
        path.name: path.read_text(encoding="utf-8")
        for path in check_adr_form.adr_files(REPO)
        if check_adr_form.governed(path.name)
    }
    assert governed, "expected at least one ADR at or above the cutoff"
    for name, text in governed.items():
        stripped = "\n".join(
            line for line in text.splitlines() if not line.startswith("Supersedes:")
        )
        findings = check_adr_form.scan_source(stripped, f"docs/adr/{name}")
        assert "`Supersedes:` line" in [f.missing for f in findings], name


def test_the_trailer_is_one_line_per_target() -> None:
    # The convention's promise is that `rg '^Supersedes:'` returns the amended
    # set. A wrapped list answers no such grep, so every governed ADR that
    # supersedes more than one thing carries more than one line.
    for path in check_adr_form.adr_files(REPO):
        if not check_adr_form.governed(path.name):
            continue
        text = path.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.startswith("Supersedes:")]
        assert lines, path.name
        for line in lines:
            assert line.strip() != "Supersedes:", path.name


def test_the_repositorys_own_adrs_pass() -> None:
    findings = check_adr_form.scan_tree(REPO)
    assert findings == [], "\n".join(str(f) for f in findings)


def test_the_delegated_decisions_are_found_at_all() -> None:
    # Without this, an empty scan would satisfy the test above.
    sources = [path.read_text(encoding="utf-8") for path in check_adr_form.adr_files(REPO)]
    delegated = [s for s in sources if check_adr_form.MARKER.search(check_adr_form.field_block(s))]
    assert len(delegated) > 20, f"expected the delegated-decision set, found {len(delegated)}"


def test_nested_agent_worktrees_are_not_scanned() -> None:
    scanned = {path.relative_to(REPO).as_posix() for path in check_adr_form.adr_files(REPO)}
    assert scanned, "expected to find our own ADRs"
    assert all(path.startswith("docs/adr/") for path in scanned)
