"""The composed briefing, the derived gate, and the two corpora it was measured on (#251).

Four layers.

The extractors first — path tokens, domain vocabulary, flake selection — as pure functions
over strings, each asserted against the shape it exists for and against the near-miss that
must not trip it. A bare `addons/` and `addons/main/x.sqf` are the pair the whole first
signal rests on.

Then the gate table, which is acceptance criterion 1: an issue touching `addons/` gets the
full-corpus line, a docs-only issue gets `just fast`, and an issue whose surfaces cannot be
read says so instead of taking the cheaper gate.

Then the two corpora, which are the measurement re-run rather than remembered.
`tests/fixtures/gate-corpus/` holds the fourteen issues whose landings touched an in-world
prefix — every `fast` there is under-gating by construction — and
`tests/fixtures/readiness-corpus/` holds the twenty that landed elsewhere, where every
`regress` is over-gating by construction. Both counts are asserted, so tightening either
signal without re-measuring reds.

Then composition: what reaches the brief, what is refused, and the placeholder that makes
an unedited brief obviously unfinished.

The reserved surfaces (#294) sit with the extractors and again with the composition, for the
two ways that section can fail: naming the wrong paths, and staying silent about the right
ones. A worktree path is the near-miss there, because every brief already quotes one.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

brief = load_tool("brief")
admission = load_tool("admission")
dispatch = load_tool("dispatch")
handoff_fetch = load_tool("handoff_fetch")
readiness = load_tool("readiness")

GATE_CORPUS = REPO / "tests" / "fixtures" / "gate-corpus"
READINESS_CORPUS = REPO / "tests" / "fixtures" / "readiness-corpus"

# Every issue in the last 400 commits whose landing touched an in-world prefix — a complete
# sweep of that window rather than a sample. Every `fast` verdict here is under-gating.
LANDED_IN_WORLD = (145, 149, 152, 156, 159, 162, 164, 165, 172, 174, 175, 176, 188, 189)

# The twenty #241 vendored, every one of which landed touching no in-world path. Every
# `regress` verdict here is over-gating.
LANDED_ELSEWHERE = (
    207, 210, 213, 214, 218, 219, 220, 223, 224, 225,
    226, 227, 228, 230, 231, 232, 238, 239, 240, 243,
)  # fmt: skip

# The measured split, named rather than counted: "eight of them" would survive a change
# that swapped which eight.
IN_WORLD_REGRESSED = (145, 156, 159, 162, 164, 165, 188, 189)
IN_WORLD_UNDETERMINED = (149, 152, 172, 174, 175, 176)
ELSEWHERE_UNDETERMINED = (224, 228, 243)

VOCABULARY = brief.read_vocabulary(REPO)


def run_git(repo: Path, *args: str, at: str = "") -> str:
    """Run git in a scratch repository, optionally pinning the commit date."""
    env = {**os.environ, "GIT_AUTHOR_DATE": at, "GIT_COMMITTER_DATE": at} if at else None
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def commit(repo: Path, subject: str, *, at: str) -> str:
    """Land one dated commit on the scratch repository's `origin/main`."""
    path = repo / f"{len(tuple(repo.iterdir()))}.txt"
    path.write_text(subject, encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-qm", subject, at=at)
    run_git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return run_git(repo, "rev-parse", "HEAD")


@pytest.fixture
def prior_work_repo(tmp_path: Path) -> Path:
    """Build a repository whose main has reference forms and unrelated commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q", "-b", "main")
    run_git(repo, "config", "user.email", "t@example.invalid")
    run_git(repo, "config", "user.name", "T")
    commit(repo, "chore: no issue reference", at="2026-08-01T12:00:00+00:00")
    commit(repo, "docs: refs form\n\nrefs #305", at="2026-08-02T12:00:00+00:00")
    commit(repo, "docs: unrelated work", at="2026-08-03T12:00:00+00:00")
    commit(repo, "fix: closing form\n\nCloses #305", at="2026-08-04T12:00:00+00:00")
    commit(repo, "feat: squash form (#305)", at="2026-08-05T12:00:00+00:00")
    commit(repo, "fix: fixes form\n\nfixes #305", at="2026-08-06T12:00:00+00:00")
    commit(repo, "fix: resolves form\n\nresolves #305", at="2026-08-07T12:00:00+00:00")
    commit(repo, "docs: adjacent issues\n\nrefs #30 and #3050", at="2026-08-08T12:00:00+00:00")
    return repo


# ---------------------------------------------------- prior work already on origin/main


def test_prior_work_reads_every_supported_reference_form_and_skips_other_commits(
    prior_work_repo: Path,
) -> None:
    work = brief.prior_work(305, prior_work_repo)
    assert [item.subject for item in work] == [
        "fix: resolves form",
        "fix: fixes form",
        "feat: squash form (#305)",
        "fix: closing form",
        "docs: refs form",
    ]
    assert [item.date for item in work] == [
        "2026-08-07",
        "2026-08-06",
        "2026-08-05",
        "2026-08-04",
        "2026-08-02",
    ]
    assert "unrelated" not in " ".join(item.subject for item in work)


def test_issue_number_boundaries_do_not_borrow_adjacent_references(
    prior_work_repo: Path,
) -> None:
    assert brief.prior_work(3, prior_work_repo) == ()
    subjects = [item.subject for item in brief.prior_work(305, prior_work_repo)]
    assert "docs: adjacent issues" not in subjects


def test_a_repository_without_a_reference_produces_no_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q", "-b", "main")
    run_git(repo, "config", "user.email", "t@example.invalid")
    run_git(repo, "config", "user.name", "T")
    commit(repo, "docs: unrelated work", at="2026-08-01T12:00:00+00:00")
    assert brief.prior_work(305, repo) == ()
    assert brief.render_prior_work(305, ()) == ""


def gate_of(issue: int, corpus: Path) -> brief.Gate:
    """Derive the gate for one vendored issue body."""
    return brief.derive_gate((corpus / f"{issue}.md").read_text(encoding="utf-8"), VOCABULARY)


# ------------------------------------------------------------------------ path extraction


def test_a_path_with_a_segment_after_the_separator_is_a_named_surface() -> None:
    assert brief.named_paths("edit addons/main/functions/fn_x.sqf now") == (
        "addons/main/functions/fn_x.sqf",
    )


def test_a_bare_directory_prefix_names_no_surface() -> None:
    # #251's own body names all three in-world directories while touching none of them.
    assert brief.named_paths("surfaces reach `addons/`, `missions/`, `extension/`") == ()


def test_named_paths_are_deduplicated_and_sorted() -> None:
    assert brief.named_paths("b/two a/one b/two") == ("a/one", "b/two")


def test_in_world_reads_admissions_list_and_not_a_second_copy() -> None:
    assert brief.in_world(("addons/main/x.sqf", "tools/y.py")) == ("addons/main/x.sqf",)
    assert brief.in_world(("src/cti_daemon/port.py",)) == ("src/cti_daemon/port.py",)
    assert brief.in_world(("src/cti_daemon/planner.py",)) == ()
    for prefix in admission.IN_WORLD_PREFIXES:
        assert brief.in_world((f"{prefix}whatever",)) == (f"{prefix}whatever",)


# ------------------------------------------------------------------- the reserved surfaces


def test_every_directory_under_dot_claude_is_a_reserved_surface() -> None:
    """#294 measured the whole directory reserved, not the four subdirectories it names."""
    assert brief.reserved_surfaces(
        (".claude/hooks/edit_payload.py", ".claude/skills/retro/SKILL.md", ".claude/notes/x.md")
    ) == (".claude/hooks/edit_payload.py", ".claude/skills/retro/SKILL.md", ".claude/notes/x.md")


def test_a_path_outside_dot_claude_is_not_reserved() -> None:
    assert brief.reserved_surfaces(("tools/brief.py", "docs/adr/0068-seats.md")) == ()


def test_a_worktree_path_is_a_location_and_not_a_reserved_surface() -> None:
    """Every brief quotes one, and the files inside it are ordinary repo paths."""
    assert brief.reserved_surfaces((".claude/worktrees/issue-294/tools/brief.py",)) == ()


def test_a_reserved_surface_beside_a_worktree_path_is_still_reported() -> None:
    paths = (".claude/worktrees/issue-294/x.py", ".claude/hooks/format-on-edit.py")
    assert brief.reserved_surfaces(paths) == (".claude/hooks/format-on-edit.py",)


def test_the_prefix_and_its_exemption_are_read_from_one_place_each() -> None:
    """A second copy of either list is a second home for the #294 measurement."""
    assert brief.RESERVED_PREFIXES == (".claude/",)
    assert brief.RESERVED_EXEMPT == (".claude/worktrees/",)


# ------------------------------------------------------------------- the domain vocabulary


def test_the_vocabulary_is_context_mds_terms_plus_the_two_engine_words() -> None:
    vocabulary = brief.domain_vocabulary("**Squad**:\n  a thing\n**Command Port**:\n  another\n")
    assert set(vocabulary) == {"Squad", "Command Port", "SQF", "in-world"}


def test_the_vocabulary_is_longest_first_so_a_compound_term_wins() -> None:
    vocabulary = brief.domain_vocabulary("**Command**:\n x\n**Command Port**:\n y\n")
    assert brief.domain_mentions("the Command Port refuses", vocabulary) == ("Command Port",)


def test_the_live_context_document_is_readable_and_carries_its_language() -> None:
    assert "Squad" in VOCABULARY
    assert "Commander" in VOCABULARY
    assert "SQF" in VOCABULARY


def test_an_unreadable_context_document_yields_no_vocabulary(tmp_path: Path) -> None:
    assert brief.read_vocabulary(tmp_path) == ()


def test_a_domain_term_is_matched_case_sensitively_on_a_word_boundary() -> None:
    vocabulary = ("Base",)
    assert brief.domain_mentions("the Base falls", vocabulary) == ("Base",)
    assert brief.domain_mentions("the base sha", vocabulary) == ()
    assert brief.domain_mentions("Baseline noise", vocabulary) == ()


def test_no_vocabulary_means_no_mentions_rather_than_an_empty_pattern() -> None:
    assert brief.domain_mentions("Squad Commander", ()) == ()


# ------------------------------------------------- the gate table, acceptance criterion 1


def test_an_issue_touching_addons_gets_the_full_corpus_line() -> None:
    gate = brief.derive_gate("rework addons/main/functions/fn_effectApply.sqf", VOCABULARY)
    assert gate.kind == brief.GATE_REGRESS
    assert "full corpus" in gate.line
    assert "no filter" in gate.line
    assert "addons/main/functions/fn_effectApply.sqf" in gate.because[0]
    assert gate.reads_a_verdict


def test_a_docs_only_issue_gets_just_fast() -> None:
    gate = brief.derive_gate("rewrite docs/agents/handoff.md and tools/land.py", VOCABULARY)
    assert gate.kind == brief.GATE_FAST
    assert gate.line == "`just fast`"
    assert not gate.reads_a_verdict


def test_an_issue_naming_no_path_at_all_says_the_surface_is_undetermined() -> None:
    gate = brief.derive_gate("make the thing better, somehow", VOCABULARY)
    assert gate.kind == brief.GATE_UNDETERMINED
    assert "named_paths=none" in gate.because[0]
    assert brief.PLACEHOLDER not in gate.line
    assert "UNDETERMINED" in gate.line


def test_an_issue_speaking_the_domain_language_with_no_in_world_path_is_undetermined() -> None:
    gate = brief.derive_gate("the Commander misreads docs/playtest/0001.md", VOCABULARY)
    assert gate.kind == brief.GATE_UNDETERMINED
    assert "Commander" in gate.because[0]


def test_an_unreadable_vocabulary_refuses_to_decide_rather_than_taking_the_cheap_gate() -> None:
    gate = brief.derive_gate("rewrite docs/agents/handoff.md", ())
    assert gate.kind == brief.GATE_UNDETERMINED
    assert gate.because[0] == "vocabulary=unreadable"


def test_an_in_world_path_outranks_a_silent_vocabulary() -> None:
    # The first signal is positive evidence, so it decides even when the second cannot run.
    assert brief.derive_gate("addons/main/x.sqf", ()).kind == brief.GATE_REGRESS


def test_only_the_regress_gate_reads_a_verdict() -> None:
    kinds = {
        brief.GATE_REGRESS: True,
        brief.GATE_FAST: False,
        brief.GATE_UNDETERMINED: False,
    }
    for kind, expected in kinds.items():
        assert brief.Gate(kind, "x", ()).reads_a_verdict is expected


# ---------------------------------------------------------------------- the two corpora


@pytest.mark.parametrize("issue", LANDED_IN_WORLD)
def test_no_issue_that_landed_in_world_is_ever_sent_to_the_cheaper_gate(issue: int) -> None:
    """Under-gating is the defect the table exists to prevent, so it is asserted per issue."""
    assert gate_of(issue, GATE_CORPUS).kind != brief.GATE_FAST


@pytest.mark.parametrize("issue", LANDED_ELSEWHERE)
def test_no_issue_that_landed_elsewhere_is_ever_sent_to_the_corpus(issue: int) -> None:
    """Over-gating spends Arma tier time, so it is asserted per issue too."""
    assert gate_of(issue, READINESS_CORPUS).kind != brief.GATE_REGRESS


def test_the_measured_split_on_the_in_world_population_is_the_one_recorded() -> None:
    regressed = tuple(
        issue for issue in LANDED_IN_WORLD if gate_of(issue, GATE_CORPUS).kind == brief.GATE_REGRESS
    )
    undetermined = tuple(
        issue
        for issue in LANDED_IN_WORLD
        if gate_of(issue, GATE_CORPUS).kind == brief.GATE_UNDETERMINED
    )
    assert regressed == IN_WORLD_REGRESSED
    assert undetermined == IN_WORLD_UNDETERMINED


def test_the_measured_split_on_the_other_population_is_the_one_recorded() -> None:
    undetermined = tuple(
        issue
        for issue in LANDED_ELSEWHERE
        if gate_of(issue, READINESS_CORPUS).kind == brief.GATE_UNDETERMINED
    )
    fast = tuple(
        issue
        for issue in LANDED_ELSEWHERE
        if gate_of(issue, READINESS_CORPUS).kind == brief.GATE_FAST
    )
    assert undetermined == ELSEWHERE_UNDETERMINED
    assert len(fast) == len(LANDED_ELSEWHERE) - len(ELSEWHERE_UNDETERMINED)


def test_the_first_signal_alone_would_have_under_gated_four_of_the_fourteen() -> None:
    """The vocabulary signal's whole reason for existing, stated as a number."""
    paths_only = tuple(
        issue
        for issue in LANDED_IN_WORLD
        if not brief.in_world(
            brief.named_paths((GATE_CORPUS / f"{issue}.md").read_text(encoding="utf-8"))
        )
        and brief.named_paths((GATE_CORPUS / f"{issue}.md").read_text(encoding="utf-8"))
    )
    assert paths_only == (152, 172, 174, 175, 176)


# ------------------------------------------------------- the flake lines, criterion 2


def flake_row(number: int, title: str, body: str = "") -> dict[str, object]:
    """One row in the shape `gh issue list --json number,title,body` returns."""
    return {"number": number, "title": title, "body": body}


def test_a_title_naming_a_test_and_saying_it_flakes_is_a_flake() -> None:
    assert brief.is_flake("test_a_holders_age_reads_as_a_duration flakes under load", "")
    assert brief.is_flake("test_the_observer_guards_against_staging flaked once", "")


def test_a_title_naming_a_test_without_the_flake_word_is_not_a_flake() -> None:
    assert not brief.is_flake("test_a_holders_age_reads_as_a_duration is wrong", "")


def test_a_title_saying_flake_without_naming_a_test_is_not_a_flake() -> None:
    assert not brief.is_flake("the suite is flaky under load", "")


def test_a_body_typing_itself_with_the_class_is_a_flake_whatever_the_title_says() -> None:
    assert brief.is_flake("something broke", "Class: `flake_quarantine`. Nobody acts.\n")


def test_merely_citing_the_class_table_is_not_a_flake() -> None:
    # Two of the four open issues mentioning the class do exactly this.
    assert not brief.is_flake(
        "Measure the handoff break-even",
        "reported per the `flake_quarantine` row's discipline",
    )


def test_a_selected_flake_carries_its_test_and_its_module() -> None:
    (flake,) = brief.select_flakes(
        [
            flake_row(
                222,
                "test_a_holders_age_reads_as_a_duration flakes under full-suite load",
                "`tests/unit/test_client_lock.py::test_a_holders_age_reads_as_a_duration`",
            )
        ]
    )
    assert flake.issue == 222
    assert flake.test == "test_a_holders_age_reads_as_a_duration"
    assert flake.module == "tests/unit/test_client_lock.py"
    assert flake.line() == (
        "- #222 `tests/unit/test_client_lock.py::test_a_holders_age_reads_as_a_duration`"
    )


def test_a_flake_whose_body_names_no_module_still_renders_its_test() -> None:
    (flake,) = brief.select_flakes([flake_row(9, "test_something_here flakes", "")])
    assert flake.line() == "- #9 `test_something_here`"


def test_flakes_come_back_in_issue_order() -> None:
    selected = brief.select_flakes(
        [flake_row(233, "test_b_flakes flaked"), flake_row(222, "test_a_thing flakes")]
    )
    assert [flake.issue for flake in selected] == [222, 233]


def test_a_closed_flake_drops_out_of_the_next_briefing() -> None:
    """Criterion 2: the section is what the tracker answered, never what was remembered."""
    open_today = [
        flake_row(222, "test_a_holders_age_reads_as_a_duration flakes under load"),
        flake_row(233, "test_the_observer_guards_against_staging flaked once"),
        flake_row(251, "just brief: compose a dispatch briefing invariant half"),
    ]
    assert [flake.issue for flake in brief.select_flakes(open_today)] == [222, 233]

    # #222 is fixed and closed, so `gh issue list --state open` stops returning it.
    open_tomorrow = [row for row in open_today if row["number"] != 222]
    assert [flake.issue for flake in brief.select_flakes(open_tomorrow)] == [233]


def test_the_open_issue_read_asks_for_open_issues_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def record(args: list[str]) -> str:
        seen.append(args)
        return "[]"

    monkeypatch.setattr(brief, "_gh", record)
    assert brief.fetch_open_issues("owner/repo") == []
    assert seen[0][:2] == ["issue", "list"]
    assert "--state" in seen[0]
    assert seen[0][seen[0].index("--state") + 1] == "open"


# ------------------------------------------------------------------------------ the seat


def test_every_registered_seat_has_a_model_roles_reason() -> None:
    """A seat cannot join the dispatch registry without a line a briefing can state."""
    assert set(brief.SEAT_REASON) == set(dispatch.SEATS)


def test_the_default_seat_is_the_implementer_and_owes_no_further_reason() -> None:
    seat = brief.derive_seat("")
    assert seat.name == "implementer"
    assert seat.reason == brief.SEAT_REASON["implementer"]
    assert not seat.owes_reason


def test_a_non_default_seat_still_owes_the_orchestrators_reason() -> None:
    seat = brief.derive_seat("review")
    assert seat.name == "review"
    assert seat.owes_reason


def test_naming_the_default_seat_explicitly_owes_nothing_extra() -> None:
    assert not brief.derive_seat("implementer").owes_reason


# -------------------------------------------------------------------------- the worktree


def test_the_base_sha_the_caller_gives_is_the_one_that_is_printed(tmp_path: Path) -> None:
    tree = brief.resolve_tree(251, "deadbee", tmp_path)
    assert tree.base == "deadbee"
    assert tree.source == "given"
    assert tree.path == tmp_path / ".claude" / "worktrees" / "issue-251"


def test_the_worktree_hangs_off_the_main_checkout_and_not_off_this_tree() -> None:
    """Composing from inside a worktree once named `<worktree>/.claude/worktrees/…`."""
    tree = brief.resolve_tree(251, "deadbee", REPO)
    assert ".claude/worktrees/issue-251/.claude" not in str(tree.path)
    assert tree.path == dispatch.main_checkout(REPO) / ".claude" / "worktrees" / "issue-251"


def test_an_existing_worktree_answers_with_its_own_head() -> None:
    tree = brief.resolve_tree(251, "", REPO)
    assert tree.source in {"worktree", "origin/main"}
    assert tree.base


def test_a_checkout_git_cannot_read_leaves_the_sha_to_the_worktree_call(tmp_path: Path) -> None:
    tree = brief.resolve_tree(251, "", tmp_path)
    assert tree.base == ""
    assert tree.source == "unresolved"


# ----------------------------------------------------------------------- the composition


def composed(**over: object) -> str:
    """Render a brief with one part varied, so a test names only what it is about."""
    base = brief.Briefing(
        issue=251,
        title="a title",
        gate=brief.derive_gate("touch tools/land.py", VOCABULARY),
        flakes=(),
        seat=brief.derive_seat(""),
        tree=brief.Tree(REPO / ".claude" / "worktrees" / "issue-251", "0f21191", "worktree"),
        assessment=readiness.assess("- [ ] one\n- [ ] two\nGate: `just fast`\n"),
    )
    return brief.compose(base._replace(**over))


def test_the_brief_carries_the_worktree_protocol_as_the_two_calls_it_now_is() -> None:
    rendered = composed()
    assert "`just worktree add issue-251`" in rendered
    assert "`just worktree done issue-251`" in rendered
    assert "never reset (#105)" in rendered


def test_the_brief_carries_the_landing_protocol_and_the_commit_trailer() -> None:
    rendered = composed()
    assert "`refs #251`" in rendered
    assert "Conventional Commits" in rendered
    assert "paste its output verbatim" in rendered


def test_prior_work_is_loud_and_states_without_interpreting() -> None:
    work = (
        brief.PriorWork(
            sha="3d4e5630123456789",
            date="2026-08-09",
            subject="docs(routing): design backlog restriction removal",
        ),
    )
    rendered = composed(prior_work=work)
    assert "## PRIOR WORK ALREADY ON `origin/main` — READ BEFORE DISPATCH (1)" in rendered
    assert "`3d4e563` 2026-08-09 — docs(routing): design backlog restriction removal" in rendered
    assert "does not decide whether #251 is done, superseded, or wants another lens" in rendered


def test_no_prior_work_adds_no_permanently_empty_section() -> None:
    rendered = composed()
    assert "PRIOR WORK" not in rendered
    assert brief.PRIOR_WORK_RULE not in rendered


# --------------------------------------------------------------- the handoff (#309)

# #212 measured that `tools/brief.py` never called `handoff_fetch`, so no cold-start
# dispatched subagent had ever read a handoff. #309 wires the fetch in; these assert the
# three states stay as distinguishable in the brief as they are in the tool's exit codes.

A_HANDOFF = (
    "Handoff-for: #251\n\n"
    "**State:**     Landed and green.\n"
    "**SHA:**       `0f21191` on `main`, pushed.\n"
    "**Gates:**     `just fast` green at `0f21191`.\n"
)


def handoff_payload(*bodies: str) -> str:
    """Render comment bodies the way `gh api --jq '.[] | .body | @json'` does."""
    return "".join(json.dumps(body) + "\n" for body in bodies)


def no_handoff(_issue: int) -> object:
    """Return a clean-absence handoff seam — no network, for the main() tests that compose."""
    return brief.Handoff(brief.HANDOFF_ABSENT)


def test_fetch_handoff_returns_the_newest_handoff_carried() -> None:
    h = brief.fetch_handoff(251, fetch=lambda _i: handoff_payload("noise", A_HANDOFF))
    assert h.state == brief.HANDOFF_CARRIED
    assert h.body == A_HANDOFF


def test_fetch_handoff_finds_no_marker_as_a_clean_absence() -> None:
    h = brief.fetch_handoff(251, fetch=lambda _i: handoff_payload("just a comment"))
    assert h.state == brief.HANDOFF_ABSENT
    assert h.body == ""


def test_fetch_handoff_encodes_a_fetch_error_as_could_not_look_not_absent() -> None:
    detail = "`gh` could not read #251: 404"

    # Raise the exact class `brief.fetch_handoff` catches — the sibling module `brief`
    # imports is not identity-equal to the one `load_tool` hands this test, so reaching
    # through `brief.handoff_fetch` is what reproduces the production path faithfully.
    def refusing(_issue: int) -> str:
        raise brief.handoff_fetch.FetchError(detail)

    h = brief.fetch_handoff(251, fetch=refusing)
    assert h.state == brief.HANDOFF_UNAVAILABLE
    assert h.state != brief.HANDOFF_ABSENT
    assert "404" in h.detail


def test_a_carried_handoff_is_composed_byte_for_byte_from_select() -> None:
    # The verdict paste rule applied to a second artefact (#219): what reaches the brief is
    # exactly what `handoff_fetch.select` returns, never retyped.
    expected = handoff_fetch.select([A_HANDOFF])
    rendered = composed(handoff=brief.Handoff(brief.HANDOFF_CARRIED, body=expected))
    assert brief.HANDOFF_HEADING in rendered
    assert rendered.count(expected) == 1
    # the body sits unchanged under the heading, separated by one blank line
    assert f"{brief.HANDOFF_HEADING}\n\n{expected}" in rendered


def test_an_absent_handoff_composes_no_section() -> None:
    """A clean absence renders nothing — a fresh dispatch, not a continuation with nothing."""
    rendered = composed(handoff=brief.Handoff(brief.HANDOFF_ABSENT))
    assert "## Handoff" not in rendered
    assert brief.HANDOFF_HEADING not in rendered


def test_a_handoff_that_could_not_be_looked_is_a_loud_line_not_an_absence() -> None:
    rendered = composed(
        handoff=brief.Handoff(brief.HANDOFF_UNAVAILABLE, detail="`gh` could not read #251: 404")
    )
    assert "## Handoff" in rendered
    assert "HANDOFF UNAVAILABLE" in rendered
    assert "could not look" in rendered
    assert "404" in rendered
    assert "not confirm there is none" in rendered
    assert "`just handoff 251`" in rendered


def test_a_handoff_under_the_cap_carries_no_size_report() -> None:
    assert brief.handoff_oversize("x" * brief.HANDOFF_CAP) == ""
    assert brief.handoff_oversize("x" * (brief.HANDOFF_CAP - 1)) == ""


def test_a_handoff_over_the_cap_is_reported() -> None:
    report = brief.handoff_oversize("x" * (brief.HANDOFF_CAP + 1))
    assert report
    assert "over the" in report
    assert f"{brief.HANDOFF_CAP:,}" in report


def test_an_oversize_handoff_is_still_composed_verbatim_with_the_report() -> None:
    body = "Handoff-for: #251\n\n" + "x" * (brief.HANDOFF_CAP + 10) + "\n"
    rendered = composed(handoff=brief.Handoff(brief.HANDOFF_CARRIED, body=body))
    assert body in rendered  # still composed — the check informs, it does not block
    assert "over the" in rendered


def test_main_composes_a_carried_handoff_through_the_seam(tmp_path: Path) -> None:
    out = tmp_path / "brief.md"
    code = brief.main(
        ["251", "--out", str(out)],
        read_issue=lambda _issue, _repo: {
            "number": 251,
            "title": "t",
            "body": "rewrite tools/land.py",
            "state": "OPEN",
        },
        read_open=lambda _repo: [],
        read_handoff=lambda _issue: brief.Handoff(brief.HANDOFF_CARRIED, body=A_HANDOFF),
        repo=REPO,
    )
    assert code == 0
    assert A_HANDOFF in out.read_text(encoding="utf-8")


def test_main_does_not_refuse_when_the_handoff_could_not_be_looked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "brief.md"
    code = brief.main(
        ["251", "--out", str(out)],
        read_issue=lambda _issue, _repo: {
            "number": 251,
            "title": "t",
            "body": "rewrite tools/land.py",
            "state": "OPEN",
        },
        read_open=lambda _repo: [],
        read_handoff=lambda _issue: brief.Handoff(
            brief.HANDOFF_UNAVAILABLE, detail="`gh` is not on PATH"
        ),
        repo=REPO,
    )
    assert code == 0  # a handoff fetch failure is one section's problem, not the dispatch's
    assert "handoff=unavailable" in capsys.readouterr().err
    assert "HANDOFF UNAVAILABLE" in out.read_text(encoding="utf-8")


def test_the_brief_carries_the_derived_gate_line_and_its_derivation() -> None:
    rendered = composed(gate=brief.derive_gate("addons/main/x.sqf", VOCABULARY))
    assert "## Gate: `just regress`" in rendered
    assert "addons/main/x.sqf" in rendered


def test_the_paste_rule_reaches_a_brief_whose_gate_produces_a_verdict() -> None:
    rendered = composed(gate=brief.derive_gate("addons/main/x.sqf", VOCABULARY))
    assert "## Paste rule" in rendered
    assert "never retype the SHA or the evidence path" in rendered


def test_the_paste_rule_stays_out_of_a_brief_whose_gate_produces_none() -> None:
    assert "## Paste rule" not in composed()


def test_the_flake_section_states_the_required_response_when_a_flake_is_open() -> None:
    rendered = composed(flakes=brief.select_flakes([flake_row(222, "test_a_thing flakes")]))
    assert "## Open flakes (1, read live at composition)" in rendered
    assert "`flake_quarantine`: do not act." in rendered
    assert "re-run once" in rendered


def test_an_empty_flake_section_says_so_rather_than_going_silent() -> None:
    rendered = composed()
    assert "## Open flakes (0, read live at composition)" in rendered
    assert "None open. Any red is yours." in rendered
    assert "flake_quarantine" not in rendered


def test_the_variable_half_is_a_visible_placeholder_and_not_composed() -> None:
    """Criterion 5: an unedited brief must be obviously unfinished."""
    rendered = composed()
    assert brief.PLACEHOLDER in rendered
    assert "The task statement, the scope boundary, and the ground truth to read." in rendered


def test_a_non_default_seat_opens_a_second_placeholder_for_its_reason() -> None:
    # `planner`, not `review`: the review seat opens a placeholder of its own for the profile
    # under review (#322), and a count assertion over two unrelated placeholders would stop
    # being about the seat reason.
    rendered = composed(seat=brief.derive_seat("planner"))
    assert "## Seat: planner" in rendered
    assert rendered.count(brief.PLACEHOLDER) == 2
    assert "Why this issue wants a non-default seat." in rendered


def test_the_default_seat_opens_only_the_one_placeholder() -> None:
    assert composed().count(brief.PLACEHOLDER) == 1


def test_the_review_seat_still_opens_the_placeholder_for_its_own_reason() -> None:
    """Restored coverage for the seat the assertion above used to be made on (#322 claim 4).

    That assertion moved to `planner` when the review seat grew a second, unrelated
    placeholder, and nothing replaced it — so a regression removing the seat-reason
    placeholder from `review` alone would have stayed green. The count is meaningful again
    here because the subject is *named*, which closes the other placeholder: two left, and
    both are the ones every non-default seat opens.
    """
    rendered = composed(seat=brief.derive_seat("review", "opus-high"))
    assert "## Seat: review" in rendered
    assert "Why this issue wants a non-default seat." in rendered
    assert rendered.count(brief.PLACEHOLDER) == 2


def test_a_review_briefing_with_no_subject_opens_the_seat_reason_placeholder_as_well() -> None:
    """The other arrangement, so the count claim above cannot be satisfied by a swap.

    Three placeholders: the task statement's, the seat reason's, and the subject's. A fix
    that dropped the seat reason and kept the subject would keep the two-placeholder count
    above at two on the named arrangement, and this one names which three are expected.
    """
    rendered = composed(seat=brief.derive_seat("review"))
    assert "Why this issue wants a non-default seat." in rendered
    assert "Which profile's work this review judges." in rendered
    assert rendered.count(brief.PLACEHOLDER) == 3


def test_a_review_briefing_states_the_relationship_its_dispatch_now_requires() -> None:
    """#322: an orchestrator meeting `--reviewing` at dispatch time met it too late."""
    rendered = composed(seat=brief.derive_seat("review", "opus-high"))
    assert "## Seat: review" in rendered
    assert "Dispatch this seat with `--reviewing <profile>`" in rendered
    assert "Reviewing: `opus-high`." in rendered
    assert "review_subject_contradicted" in rendered
    # The relationship the dispatcher actually enforces, not the narrower one round 1 stated:
    # every profile the records place on the work is resolved past, not the declared one.
    assert "nor any other one the issue's own dispatch records place on the work" in rendered


def test_a_review_briefing_composed_without_a_subject_opens_a_placeholder_for_it() -> None:
    """Silence would compose a briefing for a dispatch that cannot be made."""
    rendered = composed(seat=brief.derive_seat("review"))
    assert "Which profile's work this review judges." in rendered
    assert "Reviewing: `" not in rendered


def test_no_other_seat_is_told_to_declare_a_subject() -> None:
    """The section follows the registry's `reviews` column, not a name this module tests for."""
    for name, seat in dispatch.SEATS.items():
        if seat.reviews:
            continue
        assert "--reviewing <profile>" not in composed(seat=brief.derive_seat(name)), name


def test_the_composer_takes_the_subject_from_the_command_line() -> None:
    """A real option on the real parser, not a namespace field a test sets."""
    assert brief.parse_args(["322", "--seat", "review", "--reviewing", "opus-high"]).reviewing == (
        "opus-high"
    )


@pytest.mark.parametrize("seat", ["implementer", "planner", "recon", "retro"])
def test_the_composer_refuses_the_subject_in_the_dispatchers_own_refusal_shape(
    capsys: pytest.CaptureFixture[str], seat: str
) -> None:
    """The two command surfaces answer the same question the same way (#322, round 3 claim 5).

    Round 2 made them agree in wording and left them disagreeing in form: the composer emitted
    an argparse usage error that *mentioned* `reviewing_without_review_seat` in prose, where
    the dispatcher emits a typed refusal. So the claim is the whole rendered shape — the same
    lines, in the same order, at the same exit code — rather than a substring that a sentence
    happening to contain the token would satisfy.
    """
    expected = dispatch.reviewed_profile_refusal(seat, "opus-high")
    assert expected is not None
    assert expected.kind == "reviewing_without_review_seat"
    with pytest.raises(SystemExit) as refused:
        brief.parse_args(["322", "--seat", seat, "--reviewing", "opus-high"])
    assert refused.value.code == dispatch.EXIT_REFUSED
    printed = capsys.readouterr().err.splitlines()
    assert printed == [f"[brief] {line}" for line in expected.lines()]


def test_the_composers_refusal_is_the_dispatchers_and_not_a_second_copy_of_it(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One home, proven by moving it: a paraphrase here would not follow the dispatcher.

    Asserting the two strings are equal cannot distinguish "reads the dispatcher's refusal"
    from "carries an identical copy". Changing the dispatcher's wording can, and this is the
    substring assertion round 2 settled for, made honest.

    Patched on `brief.dispatch` and not on this module's `dispatch`: `load_tool` loads a
    standalone script into a module object of its own, so the copy a test holds is not the
    copy `brief` imported, and patching the wrong one leaves a claim like this quietly
    asserting nothing.
    """
    real = brief.dispatch.reviewed_profile_refusal

    def moved(seat_name: str, reviewing: str) -> dispatch.Refusal | None:
        found = real(seat_name, reviewing)
        if found is None or found.kind != "reviewing_without_review_seat":
            return found
        return found._replace(action="the dispatcher's wording, moved")

    monkeypatch.setattr(brief.dispatch, "reviewed_profile_refusal", moved)
    with pytest.raises(SystemExit):
        brief.parse_args(["322", "--seat", "implementer", "--reviewing", "opus-high"])
    assert "action=the dispatcher's wording, moved" in capsys.readouterr().err


def test_a_seat_outside_the_dispatchers_registry_refuses_rather_than_composing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed on the one arrival the parser's own `choices` cannot produce.

    `--seat` is validated against the registry, so this is reachable only by this module's
    default drifting out of it. A check that could not run is not a check that passed (#41),
    and the refusal says which half could not be read rather than composing anyway.
    """
    monkeypatch.setattr(brief, "DEFAULT_SEAT", "nonesuch")
    with pytest.raises(SystemExit) as refused:
        brief.parse_args(["322", "--reviewing", "opus-high"])
    assert refused.value.code == dispatch.EXIT_REFUSED
    printed = capsys.readouterr().err
    assert "[brief] refusal=reviewing_without_review_seat" in printed
    assert "[brief] registry=absent" in printed


def test_the_composer_refuses_the_subject_on_the_default_seat_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The default is `implementer`, which reviews nothing, so an omitted `--seat` is not a gap."""
    with pytest.raises(SystemExit):
        brief.parse_args(["322", "--reviewing", "opus-high"])
    assert "[brief] refusal=reviewing_without_review_seat" in capsys.readouterr().err


def test_the_review_seat_still_takes_the_subject_and_composes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The negative: only this one pair is borrowed from the dispatcher.

    A review briefing with a subject composes, and one without opens a placeholder rather than
    meeting the dispatcher's `review_subject_unknown` — that refusal belongs at dispatch time,
    where the resolution it guards actually happens.
    """
    assert brief.parse_args(["322", "--seat", "review", "--reviewing", "opus-high"]).reviewing == (
        "opus-high"
    )
    assert brief.parse_args(["322", "--seat", "review"]).reviewing == ""
    # An unregistered profile name is still carried through: `derive_seat` states why the
    # composer does not hold a second, weaker copy of the registry check.
    assert brief.parse_args(["322", "--seat", "review", "--reviewing", "opus-hgih"]).reviewing == (
        "opus-hgih"
    )
    assert capsys.readouterr().err == ""


def test_the_footer_names_the_readiness_findings_and_refuses_the_token_claim() -> None:
    rendered = composed(assessment=readiness.assess("nothing here"))
    assert "criteria_absent" in rendered
    assert "Token effect unmeasured (#212)" in rendered


def test_the_footer_says_none_when_readiness_found_nothing() -> None:
    assert "Readiness findings: none." in composed()


def test_the_brief_states_the_base_sha_and_where_it_came_from() -> None:
    rendered = composed()
    assert "base `0f21191` (worktree)" in rendered


def test_an_unresolved_base_sha_defers_to_the_worktree_call_rather_than_inventing_one() -> None:
    rendered = composed(tree=brief.Tree(REPO, "", "unresolved"))
    assert "base `printed by that call` (unresolved)" in rendered


def test_a_brief_naming_a_reserved_surface_says_so_and_says_what_to_do_instead() -> None:
    rendered = composed(reserved=(".claude/skills/retro/SKILL.md",))
    assert "## Reserved surfaces (1)" in rendered
    assert "`.claude/skills/retro/SKILL.md`" in rendered
    assert "Do not attempt the edit and do not route around it." in rendered
    assert "the orchestrator transcribes it" in rendered


def test_a_brief_naming_no_reserved_surface_opens_no_such_section() -> None:
    """The section appears only where it applies; silence is the default, not an empty box."""
    rendered = composed()
    assert "## Reserved surfaces" not in rendered
    assert brief.RESERVED_RULE not in rendered


def test_the_reserved_section_counts_the_surfaces_it_lists() -> None:
    rendered = composed(reserved=(".claude/hooks/a.py", ".claude/agents/b.md"))
    assert "## Reserved surfaces (2)" in rendered
    assert "`.claude/hooks/a.py`, `.claude/agents/b.md`" in rendered


def test_the_composed_half_stays_within_the_designs_size() -> None:
    """The design says fifteen to twenty-five lines; this is the honest count beside it."""
    assert len(composed().splitlines()) <= 40


# ----------------------------------------------------------- the single-shot contract (#279)


# The verbatim instruction #279 proposed, pinned word-for-word so a later edit cannot soften
# it silently. The contract lives once, in dispatch.SINGLE_SHOT_CONTRACT, and both briefs
# render that constant — so this string and the constant are asserted equal in both roles.
SINGLE_SHOT_VERBATIM = (
    "A dispatched session is single-shot: it has no second turn for a background completion"
    " or a question. Run awaited work in the foreground; decide routine ambiguities, act,"
    " and record the reasoning. If a choice is genuinely the human's, finish the unambiguous"
    " part and state exactly what remains and why."
)


def test_the_contract_constant_is_the_issues_verbatim_wording() -> None:
    """#279 proposed this instruction verbatim; the constant must match it word for word."""
    assert dispatch.SINGLE_SHOT_CONTRACT == SINGLE_SHOT_VERBATIM


def test_the_composed_brief_carries_the_single_shot_contract_under_its_heading() -> None:
    rendered = composed()
    assert "## Single-shot" in rendered
    assert dispatch.SINGLE_SHOT_CONTRACT in rendered


def test_the_default_brief_carries_the_same_single_shot_contract() -> None:
    """Criterion 1's other half: the unnamed-file brief carries the same contract.

    One home — both briefs render `dispatch.SINGLE_SHOT_CONTRACT` — so the composed brief
    and the default brief cannot drift apart, and this asserts they read the same constant.
    """
    identity = dispatch.Identity(
        dispatch_id="d-test",
        lane="claude-native",
        profile="opus-high",
        seat="implementer",
        issue=279,
        base_sha="deadbee",
    )
    rendered = dispatch.default_brief(identity, REPO / ".claude" / "worktrees" / "issue-279")
    assert dispatch.SINGLE_SHOT_CONTRACT in rendered


# ------------------------------------------------------------------- the CLI's refusals


def refusing_read(_issue: int, _repo: str) -> dict[str, object]:
    """Fail the way a missing issue or an unreachable `gh` does."""
    message = "could not resolve to an Issue"
    raise brief.FetchError(message)


def test_an_issue_that_cannot_be_read_exits_non_zero_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criterion 3: never a silent empty brief (#168/#183)."""
    out = tmp_path / "brief.md"
    code = brief.main(
        ["9999", "--out", str(out)],
        read_issue=refusing_read,
        read_open=lambda _repo: [],
        repo=REPO,
    )
    assert code == brief.NO_RESULT
    assert code != 0
    assert not out.exists()
    assert "could not resolve to an Issue" in capsys.readouterr().err


def test_an_unreadable_flake_list_refuses_too_rather_than_composing_an_empty_section(
    tmp_path: Path,
) -> None:
    def refusing_list(_repo: str) -> list[dict[str, object]]:
        message = "`gh` is not on PATH, so no issue could be read."
        raise brief.FetchError(message)

    out = tmp_path / "brief.md"
    code = brief.main(
        ["251", "--out", str(out)],
        read_issue=lambda _issue, _repo: {
            "number": 251,
            "title": "t",
            "body": "b",
            "state": "OPEN",
        },
        read_open=refusing_list,
        repo=REPO,
    )
    assert code == brief.NO_RESULT
    assert not out.exists()


def test_the_out_flag_writes_the_brief_to_the_named_file(tmp_path: Path) -> None:
    out = tmp_path / "brief.md"
    code = brief.main(
        ["251", "--out", str(out)],
        read_issue=lambda _issue, _repo: {
            "number": 251,
            "title": "compose a briefing",
            "body": "rewrite tools/land.py",
            "state": "OPEN",
        },
        read_open=lambda _repo: [],
        read_handoff=no_handoff,
        repo=REPO,
    )
    assert code == 0
    assert "# Dispatch brief — #251: compose a briefing" in out.read_text(encoding="utf-8")


def test_the_reserved_section_is_composed_from_the_real_issue_body(tmp_path: Path) -> None:
    """#294's own body names `.claude/hooks/edit_payload.py`; the brief must not stay silent."""
    out = tmp_path / "brief.md"
    code = brief.main(
        ["294", "--out", str(out)],
        read_issue=lambda _issue, _repo: {
            "number": 294,
            "title": "a dispatched session cannot write under .claude/",
            "body": "patch `.claude/hooks/edit_payload.py` and `.claude/skills/retro/SKILL.md`",
            "state": "OPEN",
        },
        read_open=lambda _repo: [],
        read_handoff=no_handoff,
        repo=REPO,
    )
    assert code == 0
    rendered = out.read_text(encoding="utf-8")
    assert "## Reserved surfaces (2)" in rendered
    assert brief.RESERVED_RULE in rendered


def test_a_brief_with_no_out_flag_goes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    code = brief.main(
        ["251"],
        read_issue=lambda _issue, _repo: {
            "number": 251,
            "title": "t",
            "body": "rewrite tools/land.py",
            "state": "OPEN",
        },
        read_open=lambda _repo: [],
        read_handoff=no_handoff,
        repo=REPO,
    )
    assert code == 0
    assert "## Gate: `just fast`" in capsys.readouterr().out


def test_prior_work_is_reachable_without_composing_a_brief(
    capsys: pytest.CaptureFixture[str],
) -> None:
    work = (brief.PriorWork("3d4e563f", "2026-08-09", "docs: the prior study"),)

    def issue_read_must_not_run(_issue: int, _repo: str) -> dict[str, object]:
        message = "standalone prior-work lookup read the issue"
        raise AssertionError(message)

    code = brief.main(
        ["305", "--prior-work"],
        read_issue=issue_read_must_not_run,
        read_open=lambda _repo: [],
        read_prior=lambda _issue, _repo: work,
        repo=REPO,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "PRIOR WORK ALREADY" in captured.out
    assert "# Dispatch brief" not in captured.out
    assert captured.err == ""


def test_a_standalone_lookup_with_no_prior_work_is_silent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = brief.main(
        ["305", "--prior-work"],
        read_issue=lambda _issue, _repo: {},
        read_open=lambda _repo: [],
        read_prior=lambda _issue, _repo: (),
        repo=REPO,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_a_prior_work_lookup_that_could_not_run_refuses_loudly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(brief.PriorWorkError, match="could not inspect origin/main"):
        brief.prior_work(305, tmp_path)

    def unreadable(_issue: int, _repo: Path) -> tuple[brief.PriorWork, ...]:
        message = "git could not inspect origin/main"
        raise brief.PriorWorkError(message)

    code = brief.main(
        ["305", "--prior-work"],
        read_prior=unreadable,
        repo=tmp_path,
    )
    captured = capsys.readouterr()
    assert code == brief.NO_RESULT
    assert captured.out == ""
    assert "git could not inspect origin/main" in captured.err
    assert "No report was produced" in captured.err


def test_an_undetermined_gate_is_loud_on_stderr_as_well_as_in_the_brief(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = brief.main(
        ["251"],
        read_issue=lambda _issue, _repo: {
            "number": 251,
            "title": "t",
            "body": "make it better",
            "state": "OPEN",
        },
        read_open=lambda _repo: [],
        read_handoff=no_handoff,
        repo=REPO,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "gate=undetermined" in captured.err
    assert "does not default to the cheaper gate" in captured.err
    assert "UNDETERMINED" in captured.out


def test_composing_for_a_closed_issue_says_so_without_refusing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = brief.main(
        ["251"],
        read_issue=lambda _issue, _repo: {
            "number": 251,
            "title": "t",
            "body": "rewrite tools/land.py",
            "state": "CLOSED",
        },
        read_open=lambda _repo: [],
        read_handoff=no_handoff,
        repo=REPO,
    )
    assert code == 0
    assert "is CLOSED" in capsys.readouterr().err


def test_an_issue_reference_parses_with_or_without_the_hash() -> None:
    assert brief.issue_number("251") == 251
    assert brief.issue_number("#251") == 251
    for bad in ("", "0", "-3", "two-five-one"):
        with pytest.raises(Exception, match="not an issue number"):
            brief.issue_number(bad)


def test_the_seat_flag_only_accepts_a_registered_seat() -> None:
    assert brief.parse_args(["251", "--seat", "review"]).seat == "review"
    with pytest.raises(SystemExit):
        brief.parse_args(["251", "--seat", "nonesuch"])


def test_a_gh_that_returns_no_issue_is_a_refusal_and_not_an_empty_brief(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(brief, "_gh", lambda _args: "{}")
    with pytest.raises(brief.FetchError, match="no readable issue"):
        brief.fetch_issue(9999)


def test_a_gh_that_answers_unparseably_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(brief, "_gh", lambda _args: "not json")
    with pytest.raises(brief.FetchError, match="not JSON"):
        brief.fetch_issue(251)
    with pytest.raises(brief.FetchError, match="not JSON"):
        brief.fetch_open_issues()


def test_a_gh_list_that_answers_with_the_wrong_shape_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(brief, "_gh", lambda _args: '{"number": 1}')
    with pytest.raises(brief.FetchError, match="nothing this could parse"):
        brief.fetch_open_issues()


def test_a_gh_that_is_not_on_path_is_a_refusal_naming_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(brief.FetchError, match="not on PATH"):
        brief.fetch_issue(251)
