"""Tests for the validated-marker gate (issue #186).

Pinned in three directions, because this gate's scope is the interesting part
of it. A header narrating a use its own count does not reach is a finding; the
live repository is not; and the inline parenthetical whose drift was the second
violation is asserted *not* to be a finding, because no rule derived from the
corpus counts its exemplars — an untested gap is indistinguishable from one the
next reader assumes is covered.

The live repository is checked too. That is the assertion #186 was raised over,
and it is the only form of this test that a future marker edit can fail.
"""

from __future__ import annotations

from conftest import REPO, load_tool

check_validated_markers = load_tool("check_validated_markers")

HEADER = "> Status: validated ×{count} — {body}\n"


def test_a_header_whose_count_reaches_its_last_use_passes() -> None:
    source = HEADER.format(count=3, body="first use, 2026-08-01. Third use: clean.")
    assert check_validated_markers.scan_source(source, "docs/agents/x.md") == []


def test_a_use_beyond_the_count_is_a_finding() -> None:
    # The first violation, in its own shape: the fourteenth retro's commit added
    # recovery.md's ninth use and left the count at eight.
    source = HEADER.format(
        count=8,
        body="Eighth use (2026-08-02): #51's agent stalled. Ninth use (2026-08-02): the\n"
        "> orchestrating session itself died mid-cycle.",
    )
    findings = check_validated_markers.scan_source(source, "docs/agents/recovery.md")
    assert len(findings) == 1
    assert "×8" in findings[0].problem
    assert "ninth" in findings[0].problem
    assert "9" in findings[0].problem


def test_the_finding_points_at_the_marker() -> None:
    source = "# Doc\n\nSome prose.\n\n" + HEADER.format(count=1, body="Second use: it held.")
    findings = check_validated_markers.scan_source(source, "docs/agents/x.md")
    assert str(findings[0]).startswith("docs/agents/x.md:5:")


def test_an_ordinal_that_does_not_qualify_a_use_is_ignored() -> None:
    # recovery.md ×13 says "the attribution question the eighteenth retro left
    # open is answered" and "(The fourteenth retro's edit added the ninth use".
    # Counting every ordinal in the header would red the live tree on both.
    source = HEADER.format(
        count=13,
        body="Thirteenth use (2026-08-04): stalls five and six. The eighteenth retro's\n"
        "> question is answered, and the fourteenth retro's edit is why.",
    )
    assert check_validated_markers.scan_source(source, "docs/agents/x.md") == []


def test_compound_ordinals_are_read() -> None:
    source = HEADER.format(count=20, body="Twenty-first use (2026-08-04): it held.")
    findings = check_validated_markers.scan_source(source, "x.md")
    assert len(findings) == 1
    assert "21" in findings[0].problem


def test_a_plural_use_phrase_is_read() -> None:
    source = HEADER.format(count=5, body="Sixth and seventh uses (2026-08-02): both resumed.")
    findings = check_validated_markers.scan_source(source, "x.md")
    assert len(findings) == 1
    assert "7" in findings[0].problem


def test_an_inline_parenthetical_is_inventoried_but_not_counted() -> None:
    # The second violation's shape: convention-lands' #131 exemplar appended
    # with the count still ×3. This gate does not catch it, and says so — see
    # UNCOUNTABLE in the checker for the corpus evidence that no rule does.
    source = (
        "- A rule. _(validated ×3 — #23 landed it. #116 landed it. #118 landed it. #131: it.)_\n"
    )
    assert check_validated_markers.scan_source(source, "CLAUDE.md") == []
    markers = check_validated_markers.markers_in(source, "CLAUDE.md")
    assert [(m.shape, m.count) for m in markers] == [("inline parenthetical", 3)]


def test_a_marker_in_neither_shape_is_a_finding() -> None:
    # A marker the gate cannot recognise is a marker the gate does not check,
    # so the inventory itself is the assertion.
    findings = check_validated_markers.scan_source("Status: validated ×4 — uses.\n", "x.md")
    assert len(findings) == 1
    assert "shape" in findings[0].problem


def test_a_marker_without_a_number_is_not_one() -> None:
    # CLAUDE.md's own prose says "its own `validated ×N` marker".
    assert check_validated_markers.scan_source("its own `validated ×N` marker\n", "CLAUDE.md") == []


def test_the_repositorys_own_markers_pass() -> None:
    findings = check_validated_markers.scan_tree(REPO)
    assert findings == [], "\n".join(str(f) for f in findings)


def test_the_markers_are_found_at_all() -> None:
    # Without this, an empty scan would satisfy the test above.
    markers = check_validated_markers.tree_markers(REPO)
    shapes = sorted(m.shape for m in markers)
    assert shapes.count("status header") >= 4, shapes
    assert shapes.count("inline parenthetical") >= 5, shapes


def test_the_narrated_uses_of_the_live_headers_are_read() -> None:
    # The gate is a lower bound, so a header nobody parses would pass silently.
    # recovery.md is the one that narrates every use by ordinal.
    recovery = (REPO / "docs" / "agents" / "recovery.md").read_text(encoding="utf-8")
    header = next(
        m for m in check_validated_markers.markers_in(recovery, "docs/agents/recovery.md")
    )
    uses = check_validated_markers.narrated_uses(header.body)
    assert max(value for _, value in uses) == header.count


def test_nested_agent_worktrees_are_not_scanned() -> None:
    scanned = {
        path.relative_to(REPO).as_posix() for path in check_validated_markers.marker_files(REPO)
    }
    assert scanned, "expected to find our own marker-bearing files"
    assert not any(path.startswith(".claude/worktrees/") for path in scanned)


def test_the_vendored_wiki_is_not_scanned() -> None:
    scanned = {
        path.relative_to(REPO).as_posix() for path in check_validated_markers.marker_files(REPO)
    }
    assert not any(path.startswith("docs/reference/") for path in scanned)


def test_the_narrating_records_are_not_scanned() -> None:
    # The process log and the ADRs quote counts as history — "Failure classes
    # `×3` → `×4`" — which is a record of a marker, not a marker.
    scanned = {
        path.relative_to(REPO).as_posix() for path in check_validated_markers.marker_files(REPO)
    }
    assert "docs/process-log.md" not in scanned
    assert not any(path.startswith("docs/adr/") for path in scanned)
