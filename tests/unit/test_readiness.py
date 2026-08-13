"""Definition of ready, and the corpus the gate was fitted to (#241).

Three layers.

The extractors come first: what counts as a criteria unit, a directive lead and an
evidence shape. They are pure functions over a string, so each one is asserted against the
body shape it exists for and against the near-miss that must not trip it.

Then the corpus. `tests/fixtures/readiness-corpus/` holds the twenty most recently
dispatched issues at the time this landed, verbatim, and the measurement that decided
which sub-checks refuse is re-run here rather than remembered. Every one of the twenty was
dispatched and landed, so every refusal on that corpus is a false positive by
construction: `test_the_measured_false_positive_rates_are_the_ones_the_split_was_set_from`
is the derivation, and it reds if anybody tightens a sub-check without re-measuring.

Then the negatives, which are the only true positives this check has. `criteria_absent`
fired on none of the twenty — that is what earned it a hard refusal and it is also why the
unready bodies below are the whole of its evidence that it fires at all.
"""

from __future__ import annotations

import pytest
from conftest import REPO, load_tool

readiness = load_tool("readiness")

CORPUS = REPO / "tests" / "fixtures" / "readiness-corpus"

# The population, and the shape each issue was read as. The shape is a hand classification
# and it is the point of the table: the enumerability sub-check's error rate is not one
# number, it is 0% on feature work and 67% on ruling executions, and an average over the
# twenty would hide exactly the structure that made it advisory.
POPULATION: dict[int, str] = {
    243: "feature",
    240: "feature",
    239: "feature",
    238: "ruling",
    232: "ruling",
    231: "defect",
    230: "feature",
    228: "feature",
    227: "feature",
    226: "feature",
    225: "feature",
    224: "ruling",
    223: "feature",
    220: "experiment",
    219: "experiment",
    218: "experiment",
    214: "feature",
    213: "feature",
    210: "feature",
    207: "feature",
}

# The three the enumerability sub-check refuses, measured. Named rather than counted,
# because "three of them" would survive a change that swapped which three.
UNENUMERABLE = (238, 232, 231)


def body(issue: int) -> str:
    """Read one vendored issue body."""
    return (CORPUS / f"{issue}.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------- criteria units


def test_a_task_list_counts_one_unit_per_item() -> None:
    assert readiness.count_units("- [ ] first\n- [ ] second\n- [x] third\n") == 3


def test_a_bulleted_or_ordered_list_counts_the_same_as_a_task_list() -> None:
    assert readiness.count_units("- first\n- second\n") == 2
    assert readiness.count_units("1. first\n2. second\n") == 2


def test_a_tables_body_rows_count_and_its_header_and_rule_do_not() -> None:
    table = (
        "| Refusal | When |\n|---|---|\n| dirty_tree | uncommitted |\n| gate_red | fast failed |\n"
    )
    assert readiness.count_units(table) == 2


def test_an_inline_enumeration_counts_its_run() -> None:
    assert readiness.count_units("Scope: (1) the tool, (2) the measurement, (3) the remedy.") == 3


def test_a_lone_inline_marker_enumerates_nothing() -> None:
    assert readiness.count_units("Fix the ledger (1) as the close describes.") == 0


def test_an_inline_run_that_does_not_start_at_one_enumerates_nothing() -> None:
    assert readiness.count_units("See item (3) and item (4) of the sweep.") == 0


def test_a_parenthesised_number_that_is_not_a_marker_is_not_a_run() -> None:
    assert readiness.count_units("It cut 1,669 lines (1,669 of them release history).") == 0


def test_a_fenced_code_block_contributes_no_units() -> None:
    fenced = (
        "Run it:\n\n```sh\ngh api repos/x/y \\\n  --jq '.[] | select(.a)'\n- not a criterion\n```\n"
    )
    assert readiness.count_units(fenced) == 0


# ------------------------------------------------------------------ directive leads


def test_a_heading_a_bold_label_and_a_colon_led_clause_all_lead() -> None:
    assert readiness.find_leads("## Acceptance criteria\n") == ("acceptance",)
    assert readiness.find_leads("**Scope**: the rung.\n") == ("scope",)
    assert readiness.find_leads("Build: a rung in the dispatch ladder.\n") == ("build",)


def test_a_lead_opens_a_sentence_and_not_only_a_line() -> None:
    """#183's shape, and the one false positive the open queue turned up against this check.

    Its criteria are the third sentence of a paragraph — "… outside #168's authorised diff.
    Scope: apply the same treatment …" — and a line-anchored reading called that body
    criteria-free. The fix is where the extractor looks, not what it looks for, and the
    derivation corpus re-runs unchanged above.
    """
    body_text = (
        "The other entries were left outside the authorised diff. Scope: apply the same "
        "`|| exit 2` treatment, and extend the empty-PATH wiring test to every entry.\n"
    )
    assert readiness.find_leads(body_text) == ("scope",)
    assert readiness.assess(body_text).blocking == ()


def test_a_lead_word_in_the_middle_of_a_sentence_does_not_lead() -> None:
    assert readiness.find_leads("The agent should fix the ledger's spend column.\n") == ()


# ------------------------------------------------------------------ evidence shapes


@pytest.mark.parametrize(
    ("text", "shape"),
    [
        ("`just fast` green.", "recipe"),
        ("Unit-test the decision in the no-Arma tier.", "test"),
        ("The gate reds on a vacuous suite.", "gate"),
        ("The probe carries its own verdict.", "verdict"),
        ("It refuses with infra_unavailable and the reset time.", "class"),
        ("Its home is tools/ledger.py.", "path"),
        ("Landed repair in a885306.", "sha"),
    ],
)
def test_each_evidence_shape_is_recognised_where_it_appears(text: str, shape: str) -> None:
    assert shape in readiness.find_evidence(text)


def test_prose_with_no_mechanical_anchor_names_no_evidence_shape() -> None:
    assert readiness.find_evidence("Make the dispatcher nicer to use for everyone.") == ()


# ------------------------------------------------------------------------ the corpus


def test_the_vendored_corpus_is_the_population_the_measurement_names() -> None:
    """The fixtures and the shape table are one population, or the rates below are fiction."""
    vendored = {int(path.stem) for path in CORPUS.glob("*.md")}
    assert vendored == set(POPULATION)


def test_the_measured_false_positive_rates_are_the_ones_the_split_was_set_from() -> None:
    """Re-run the derivation. Every refusal here is a false positive by construction.

    Each of these twenty was dispatched and landed, so a sub-check that refuses one is
    wrong about it. `criteria_absent` and `criteria_without_evidence_shape` refuse none and
    are hard; `criteria_not_enumerable` refuses three and is advisory. Tightening any of
    them without re-measuring reds here, which is the point of keeping the corpus.
    """
    refused: dict[str, list[int]] = {
        "criteria_absent": [],
        "criteria_not_enumerable": [],
        "criteria_without_evidence_shape": [],
    }
    for issue in POPULATION:
        for finding in readiness.assess(body(issue)).findings:
            refused[finding.kind].append(issue)

    assert refused["criteria_absent"] == []
    assert refused["criteria_without_evidence_shape"] == []
    assert sorted(refused["criteria_not_enumerable"], reverse=True) == sorted(
        UNENUMERABLE, reverse=True
    )


def test_no_issue_in_the_corpus_is_refused_a_dispatch() -> None:
    """The hard half of the split, stated as the property that matters: nothing blocks."""
    for issue in POPULATION:
        assert readiness.assess(body(issue)).blocking == (), issue


def test_the_enumerability_rate_is_carried_by_the_ruling_and_defect_shapes() -> None:
    """Per shape, because the 15% average is what would have hidden the reason for it."""
    by_shape: dict[str, list[int]] = {}
    for issue, shape in POPULATION.items():
        kinds = {finding.kind for finding in readiness.assess(body(issue)).findings}
        by_shape.setdefault(shape, []).extend([issue] if "criteria_not_enumerable" in kinds else [])

    assert by_shape["feature"] == []
    assert by_shape["experiment"] == []
    assert sorted(by_shape["ruling"], reverse=True) == [238, 232]
    assert by_shape["defect"] == [231]


def test_the_refused_three_carry_no_units_and_the_thinnest_pass_carries_three() -> None:
    """The boundary sits in a gap, which is why the threshold is stated and not tuned."""
    assert [readiness.count_units(body(issue)) for issue in UNENUMERABLE] == [0, 0, 0]
    cleared = [
        readiness.count_units(body(issue)) for issue in POPULATION if issue not in UNENUMERABLE
    ]
    assert min(cleared) == 3


def test_every_issue_the_check_clears_on_enumerability_also_leads_the_reader_in() -> None:
    """A body with units but no lead would be a shape the vocabulary has not met yet."""
    for issue in POPULATION:
        assert readiness.find_leads(body(issue)), issue


# ------------------------------------------------------------------- unready bodies


def test_a_body_with_no_criteria_and_no_evidence_is_refused_on_both_hard_sub_checks() -> None:
    found = readiness.assess("The dispatcher feels slow lately and somebody should look.\n")
    assert [finding.kind for finding in found.blocking] == [
        "criteria_absent",
        "criteria_without_evidence_shape",
    ]


def test_criteria_absent_is_reported_alone_and_never_beside_unenumerable() -> None:
    """Two ways of saying the body has no criteria is one of them too many."""
    kinds = {finding.kind for finding in readiness.assess("Nothing to see here.\n").findings}
    assert "criteria_absent" in kinds
    assert "criteria_not_enumerable" not in kinds


def test_a_body_that_enumerates_but_names_no_evidence_is_refused_on_that_alone() -> None:
    found = readiness.assess("Scope:\n\n- make it faster\n- make it nicer\n- make it clearer\n")
    assert [finding.kind for finding in found.blocking] == ["criteria_without_evidence_shape"]
    assert found.advisory == ()


def test_a_prose_ruling_with_an_evidence_shape_is_advised_and_never_refused() -> None:
    """The measured shape: #238's body in miniature — a ruling, transcribed, not a checklist."""
    found = readiness.assess(
        "Human ruling, 2026-08-05: the lane dispatches only off-peak.\n\n"
        "Build: a rung that refuses outside the window. Tests both directions.\n"
    )
    assert found.blocking == ()
    assert [finding.kind for finding in found.advisory] == ["criteria_not_enumerable"]


def test_the_strictness_split_is_the_one_the_corpus_decided() -> None:
    """The split is data, not taste, so it is asserted rather than left to a reader."""
    assert sorted(readiness.HARD) == ["criteria_absent", "criteria_without_evidence_shape"]
    assert sorted(readiness.ADVISORY) == ["criteria_not_enumerable"]
    assert not readiness.HARD & readiness.ADVISORY


def test_an_assessment_renders_the_counts_behind_its_verdict() -> None:
    found = readiness.assess("## Scope\n\n- one thing, under `just fast`\n- another thing\n")
    assert found.lines() == (
        "criteria_units=2",
        "directive_leads=scope",
        "evidence_shapes=recipe",
    )


# ---------------------------------------------------------------------- the gh seam


def test_a_missing_gh_is_a_reason_rather_than_an_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreadable body is the caller's to classify, so the seam hands back a reason."""

    def absent(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(readiness.subprocess, "run", absent)
    assert readiness.fetch_body(241) == ("", "gh is not on PATH")


def test_a_gh_timeout_names_the_bound_it_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(*_args: object, **_kwargs: object) -> None:
        raise readiness.subprocess.TimeoutExpired(cmd="gh", timeout=readiness.FETCH_TIMEOUT_SECONDS)

    monkeypatch.setattr(readiness.subprocess, "run", slow)
    body_text, why = readiness.fetch_body(241)
    assert body_text == ""
    assert str(readiness.FETCH_TIMEOUT_SECONDS) in why


def test_a_gh_failure_hands_back_its_own_first_line(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*_args: object, **_kwargs: object) -> object:
        return type("Done", (), {"returncode": 1, "stdout": "", "stderr": "no such issue\ntrace"})()

    monkeypatch.setattr(readiness.subprocess, "run", refused)
    assert readiness.fetch_body(241) == ("", "no such issue")


def test_an_empty_body_is_unreadable_rather_than_unready(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blank body could mean a wrong issue number, so it is not judged as a body at all."""

    def blank(*_args: object, **_kwargs: object) -> object:
        return type("Done", (), {"returncode": 0, "stdout": "\n", "stderr": ""})()

    monkeypatch.setattr(readiness.subprocess, "run", blank)
    assert readiness.fetch_body(241) == ("", "the issue body is empty")


def test_the_fetch_asks_gh_for_the_body_and_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    """The thread is what makes `gh issue view` expensive (#210); this asks for one field."""
    seen: dict[str, object] = {}

    def capture(argv: list[str], **kwargs: object) -> object:
        seen["argv"] = argv
        seen["timeout"] = kwargs.get("timeout")
        return type("Done", (), {"returncode": 0, "stdout": "body\n", "stderr": ""})()

    monkeypatch.setattr(readiness.subprocess, "run", capture)
    readiness.fetch_body(241)
    assert seen["argv"] == [
        "gh",
        "issue",
        "view",
        "241",
        "--repo",
        readiness.REPO_SLUG,
        "--json",
        "body",
        "--jq",
        ".body",
    ]
    assert seen["timeout"] == readiness.FETCH_TIMEOUT_SECONDS


# ------------------------------------------------------------------- the labels seam
#
# `fetch_labels` shares `fetch_body`'s transport and error policy through `_run_gh`, with the
# one real difference kept visible: an empty result is a valid checked absence for labels and
# is unreadable for a body (#323 review finding 4). The tests mirror the body seam above so a
# drift in the shared transport reds on whichever side it touches.


def test_a_missing_gh_is_a_reason_rather_than_an_exception_for_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def absent(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(readiness.subprocess, "run", absent)
    assert readiness.fetch_labels(241) == ((), "gh is not on PATH")


def test_a_gh_timeout_names_the_bound_it_exceeded_for_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def slow(*_args: object, **_kwargs: object) -> None:
        raise readiness.subprocess.TimeoutExpired(cmd="gh", timeout=readiness.FETCH_TIMEOUT_SECONDS)

    monkeypatch.setattr(readiness.subprocess, "run", slow)
    labels, why = readiness.fetch_labels(241)
    assert labels == ()
    assert str(readiness.FETCH_TIMEOUT_SECONDS) in why


def test_a_gh_failure_hands_back_its_own_first_line_for_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(*_args: object, **_kwargs: object) -> object:
        return type("Done", (), {"returncode": 1, "stdout": "", "stderr": "no such issue\ntrace"})()

    monkeypatch.setattr(readiness.subprocess, "run", refused)
    assert readiness.fetch_labels(241) == ((), "no such issue")


def test_an_empty_label_list_is_a_valid_checked_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The one difference from `fetch_body`: a blank result is `((), "")`, not a reason. An
    # issue that carries no labels is not an issue nobody could look at.
    def blank(*_args: object, **_kwargs: object) -> object:
        return type("Done", (), {"returncode": 0, "stdout": "\n", "stderr": ""})()

    monkeypatch.setattr(readiness.subprocess, "run", blank)
    assert readiness.fetch_labels(241) == ((), "")


def test_the_label_fetch_asks_gh_for_the_label_names_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def capture(argv: list[str], **kwargs: object) -> object:
        seen["argv"] = argv
        seen["timeout"] = kwargs.get("timeout")
        return type("Done", (), {"returncode": 0, "stdout": "bug\nui\n", "stderr": ""})()

    monkeypatch.setattr(readiness.subprocess, "run", capture)
    assert readiness.fetch_labels(241) == (("bug", "ui"), "")
    assert seen["argv"] == [
        "gh",
        "issue",
        "view",
        "241",
        "--repo",
        readiness.REPO_SLUG,
        "--json",
        "labels",
        "--jq",
        ".labels[].name",
    ]
    assert seen["timeout"] == readiness.FETCH_TIMEOUT_SECONDS


def test_fetch_body_and_fetch_labels_route_through_the_one_shared_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #323 review finding 4: both callers go through `_run_gh`, so a transport change is one
    # edit, not two — and the empty-result difference stays in the callers, where it belongs.
    seen: dict[tuple[str, str], tuple[object, ...]] = {}

    def fake_run_gh(issue: int, repo: str, json_field: str, jq: str) -> tuple[str, str]:
        seen[(json_field, jq)] = (issue, repo)
        return "raw\n", ""

    monkeypatch.setattr(readiness, "_run_gh", fake_run_gh)
    readiness.fetch_body(241)
    readiness.fetch_labels(241)
    assert seen[("body", ".body")] == (241, readiness.REPO_SLUG)
    assert seen[("labels", ".labels[].name")] == (241, readiness.REPO_SLUG)
