"""Tests for the validated-marker gate (issue #186).

Both marker shapes are counted, each against its own unit. A status header
narrating a use its own count does not reach is a finding, and both historical
violations' shapes are reproduced red: the first (a use appended with the count
left behind) against a header, the second (an exemplar appended with the count
left behind) against an inline list under the reference-and-colon convention
the human ruled on #186.

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


def test_an_inline_list_whose_count_matches_passes() -> None:
    source = "- A rule. _(validated ×3 — #23: held. #116: held again. #131: and again.)_\n"
    assert check_validated_markers.scan_source(source, "CLAUDE.md") == []


def test_an_appended_exemplar_without_a_count_move_is_a_finding() -> None:
    # The second violation, in its own shape: the fifteenth retro's commit
    # appended convention-lands' #131 exemplar and left the count at ×3.
    source = "- A rule. _(validated ×3 — #23: held. #116: held. #118: held. #131: appended.)_\n"
    findings = check_validated_markers.scan_source(source, "CLAUDE.md")
    assert len(findings) == 1
    assert "×3" in findings[0].problem
    assert "4" in findings[0].problem


def test_an_inline_list_not_in_the_convention_is_a_finding() -> None:
    # The pre-ruling prose style: references without their colons. Openers are
    # what the gate counts, so a list it cannot parse must red rather than
    # miscount — this exact body would otherwise read as 1 against ×3.
    source = "- A rule. _(validated ×3 — #23 held. #116 held. #131: appended.)_\n"
    findings = check_validated_markers.scan_source(source, "CLAUDE.md")
    assert len(findings) == 1
    assert "reference-and-colon" in findings[0].problem


def test_slash_runs_adr_runs_and_phases_each_open_one_exemplar() -> None:
    source = (
        "- A rule. _(validated ×4 — Phase 0: held. #80/#96/#102: one event. "
        "ADR-0039/0040/0041: one renumber chain; #171: claimed and renumbered.)_\n"
    )
    assert check_validated_markers.scan_source(source, "CLAUDE.md") == []


def test_a_mid_sentence_or_possessive_reference_is_not_an_opener() -> None:
    # "#37's 0024 claim" and "and #24 rode the same discipline" are prose inside
    # an exemplar, not exemplars — the colon anchor is what the #186 brief's
    # unanchored-grep caution is about, from the other side.
    source = (
        "- A rule. _(validated ×2 — #35/#37: #35 claimed 0022; #37's 0024 claim, "
        "posted on #35's thread, held. #104/#24: proven first; and #24 rode the "
        "same discipline the same day, 150 to 300.)_\n"
    )
    assert check_validated_markers.scan_source(source, "CLAUDE.md") == []


def test_a_pruned_list_keeps_exactly_the_newest_five() -> None:
    prelude = "newest five exemplars, the rest pruned to docs/process-log.md per #201: "
    five = "#1: a. #2: b. #3: c. #4: d. #5: e."
    source = f"- A rule. _(validated ×8 — {prelude}{five})_\n"
    assert check_validated_markers.scan_source(source, "CLAUDE.md") == []
    appended = f"- A rule. _(validated ×8 — {prelude}{five} #6: appended.)_\n"
    findings = check_validated_markers.scan_source(appended, "CLAUDE.md")
    assert len(findings) == 1
    assert "6" in findings[0].problem
    assert "newest 5" in findings[0].problem


def test_a_prune_prelude_under_a_countable_list_is_a_finding() -> None:
    # ×5 fits inline, so the prelude claims a prune that cannot have happened.
    prelude = "newest five exemplars, the rest pruned to docs/process-log.md per #201: "
    source = f"- A rule. _(validated ×5 — {prelude}#1: a. #2: b. #3: c. #4: d. #5: e.)_\n"
    findings = check_validated_markers.scan_source(source, "CLAUDE.md")
    assert len(findings) == 1
    assert "×5" in findings[0].problem


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
    assert shapes.count("inline parenthetical") >= 6, shapes


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
