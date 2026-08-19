"""Tests for the arbiter-copy gate (issue #390).

The gate exists because the enumeration of this rule's copies was wrong at all
five counts anyone made on #361, so the tests that matter are the ones that
reproduce those shapes rather than the ones that assert the regex fires: a
docstring restating the walk, a second copy in the same file that a file-level
sweep would take to be covered, and the live tree.

`tests/` being inside the subject set is asserted on purpose. The sweep brief
that hunted the last round of copies said to grep `config/`, `docs/`, `AGENTS.md`
and `tools/`, and the copy that survived sat in `tests/` — the issue's
second-order finding, that a hand-written scope is an enumeration too.
"""

from __future__ import annotations

from conftest import REPO, load_tool

check_arbiter_copies = load_tool("check_arbiter_copies")

# arbiter-rule: stated — fixture: this module's subject is prose that states the rule, so
# its arrangements have to contain it. Each fixture carries its own marker rather than one
# covering the file, which is the granularity the gate itself insists on (#390).
DOCSTRING = '"""It is built in tools/arbiter.py: the entry head, then the entry tail."""'
# arbiter-rule: stated — fixture, as above (#390).
FALSE_COPY = '"""tools/arbiter.py does not walk the entry tail; that is unbuilt."""'
# arbiter-rule: stated — fixture, as above (#390).
POINTER = '"""What the arbiter walk does is stated in tools/arbiter.py and nowhere else."""'
# arbiter-rule: stated — fixture, as above (#390).
PREFERENCE = "# ADR-0071 ruling 2's preference column, head first. resolve_seat walks this.\n"


def test_a_docstring_restating_the_walk_is_a_finding() -> None:
    # #361's fifth copy in its own shape: `dispatch.escalation_head`'s docstring,
    # which two sweeps' enumerations did not reach.
    findings = check_arbiter_copies.scan_source(DOCSTRING, "tools/dispatch.py")
    assert len(findings) == 1
    assert findings[0].line == 1
    assert "tools/arbiter.py" in findings[0].problem
    assert "tools/arbiter.py" in findings[0].remedy


def test_the_gate_does_not_judge_whether_the_statement_is_true() -> None:
    # The false sentence and the true one are the same finding. The gate's claim is
    # that nothing checkable was left to drift, never that a copy is correct.
    assert len(check_arbiter_copies.scan_source(FALSE_COPY, "tools/dispatch.py")) == 1
    assert len(check_arbiter_copies.scan_source(DOCSTRING, "tools/dispatch.py")) == 1


def test_a_pointer_passes() -> None:
    assert check_arbiter_copies.scan_source(POINTER, "tools/dispatch.py") == []


def test_the_authority_states_the_rule_and_is_not_a_copy_of_it() -> None:
    assert check_arbiter_copies.scan_source(DOCSTRING, "tools/arbiter.py") == []
    assert check_arbiter_copies.stated_in(DOCSTRING, "tools/arbiter.py") == []


def test_resolve_seats_own_walk_is_not_this_rule() -> None:
    # "head first" is ruling 2's phrase for the preference list as well, and the
    # registry comment that uses it names no arbiter. Matching it would put a marker
    # on a comment about a different resolution.
    # arbiter-rule: stated — this negative fixture explains the regex boundary (#390).
    assert check_arbiter_copies.scan_source(PREFERENCE, "tools/dispatch.py") == []


def test_a_marker_needs_a_reason() -> None:
    bare = f"# arbiter-rule: stated\n{DOCSTRING}"
    assert len(check_arbiter_copies.scan_source(bare, "tools/dispatch.py")) == 1
    reasoned = f"# arbiter-rule: stated — the authority's own test (#390)\n{DOCSTRING}"
    assert check_arbiter_copies.scan_source(reasoned, "tools/dispatch.py") == []
    (site, reason) = check_arbiter_copies.stated_in(reasoned, "tools/dispatch.py")[0]
    assert reason == "the authority's own test (#390)"
    assert site.claim_line() == 2


def test_a_python_marker_may_sit_below_the_string_it_covers() -> None:
    # A printed string cannot carry the marker inside it without changing what the
    # program prints, so the code around it is the only place left.
    below = f"{DOCSTRING}\n# arbiter-rule: stated — printed output (#390)\n"
    assert check_arbiter_copies.scan_source(below, "tools/dispatch.py") == []


def test_one_comment_run_does_not_cover_the_next() -> None:
    # #361's sixth copy stood 140 lines above the fifth in the same file, and round 3
    # reported the set derived. Two comment runs separated by code are two places.
    source = (
        "# arbiter-rule: stated — the first run's reason (#390)\n"
        "# tools/arbiter.py walks the entry head, then the entry tail.\n"
        "escalation: tuple[str, ...] = ()\n"
        "# tools/arbiter.py walks the entry head, then the entry tail.\n"
        # arbiter-rule: stated — fixture intentionally contains the unmarked second copy (#390).
    )
    findings = check_arbiter_copies.scan_source(source, "tools/dispatch.py")
    assert [finding.line for finding in findings] == [4]


def test_one_marked_changelog_bullet_does_not_cover_its_neighbour() -> None:
    source = (
        "- **One landing.** The walk takes the entry head, then the entry tail.\n"
        "  <!-- arbiter-rule: stated — a dated entry (#390) -->\n"
        "- **Another landing.** The arbiter walk falls through to the entry tail.\n"
    )
    findings = check_arbiter_copies.scan_source(source, "CHANGELOG.md")
    assert [finding.line for finding in findings] == [3]


def test_one_marked_changelog_bullet_does_not_cover_a_nested_neighbour() -> None:
    source = (
        "- **One landing.** The walk takes the entry head, then the entry tail.\n"
        "  <!-- arbiter-rule: stated — a dated entry (#390) -->\n"
        "  - **Nested landing.** The arbiter walk falls through to the entry tail.\n"
    )
    findings = check_arbiter_copies.scan_source(source, "CHANGELOG.md")
    assert [finding.line for finding in findings] == [3]


def test_one_marked_table_row_does_not_cover_its_neighbour() -> None:
    source = (
        "| `just x` | The arbiter walk takes the entry head. |"
        " <!-- arbiter-rule: stated — a row (#390) -->\n"
        "| `just y` | The arbiter walk then takes the entry tail. |\n"
    )
    findings = check_arbiter_copies.scan_source(source, "AGENTS.md")
    assert [finding.line for finding in findings] == [2]


def test_one_marked_table_row_does_not_cover_an_indented_neighbour() -> None:
    source = (
        "| `just x` | The arbiter walk takes the entry head. |"
        " <!-- arbiter-rule: stated — a row (#390) -->\n"
        "  | `just y` | The arbiter walk then takes the entry tail. |\n"
    )
    findings = check_arbiter_copies.scan_source(source, "AGENTS.md")
    assert [finding.line for finding in findings] == [2]


def test_the_subject_set_is_derived_and_reaches_tests() -> None:
    tracked = check_arbiter_copies.tracked_files(REPO)
    assert "tests/unit/test_routing_policy.py" in tracked
    assert "CHANGELOG.md" in tracked
    assert "config/escalation-conditions.json" in tracked
    # Nothing narrows it: the scan's own subject set is every tracked file, so the
    # count is the repository's, not a list this checker keeps.
    assert len(tracked) > 1000


def test_the_live_tree_leaves_nothing_checkable_to_drift() -> None:
    """The assertion #390 was raised over, and the only one a later edit can fail."""
    assert check_arbiter_copies.scan_tree(REPO) == []


def test_every_marked_restatement_in_the_tree_carries_a_reason() -> None:
    stated = check_arbiter_copies.tree_stated(REPO)
    # Design 1's escape is enumerated by the check rather than recalled, which is the
    # whole substitution: the set is read off the tree, and every entry says why.
    assert stated, "the escape exists and the tree uses it; an empty list means it stopped working"
    assert all(reason.strip() for _, reason in stated)
    assert all("#390" in reason for _, reason in stated)
