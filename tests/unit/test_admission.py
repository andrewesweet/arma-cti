"""The pre-registered admission bar (#224, ADR-0061 Decision 6).

The bar is a number the human ruled on 2026-08-05T20:00Z, and the whole value of a
pre-registered number is that it does not move once the lane's own numbers are in. So the
first thing here is a guard on the constants themselves: if `N`, the unclean allowance, the
attempt count, the citation floor or Part A's four criteria change, a test goes red and the
change has to be argued rather than absorbed.

The rest are the claims that would let a bar look like a bar and admit anything:

- that "no allowance" really means the first missed criterion ends the attempt, and is not
  quietly a nine-out-of-ten;
- that a criterion nobody passed does not read as met (#41's shape, and the ruling's own
  reasoning for putting criterion 3 at 10/10);
- that attempts do not pool, and that there is no third one to improvise;
- that the citation bar pools its counts rather than averaging per dispatch, and that ten
  dispatches citing nothing fail rather than clear;
- that the git cross-check can only refuse, and that a cross-check which could not run
  refuses the record instead of passing it.

Nothing here reaches a provider, a collector or this box's real records: every store is a
`tmp_path`, and the OTel endpoint is one nothing listens on, so the assertion about the
journal is that it is complete whether or not the collector took the record.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

admission: ModuleType = load_tool("admission")
dispatch: ModuleType = load_tool("dispatch")

# A port nothing listens on, so the export fails the way a stopped collector fails. Inside
# the tier's allocation [2400, 3000) and away from the slot stride.
DEAD_ENDPOINT = "http://127.0.0.1:2998/v1/logs"

NOW = 1_785_000_000.0

LANE = "zai"
PROFILE = "zai-glm52-max"


def store(tmp_path: Path) -> Any:  # noqa: ANN401 — a tools/ module loads dynamically, so its types are Unknown here
    """Build an admission store whose collector is deliberately not there."""
    return admission.Store(directory=tmp_path / "admission", endpoint=DEAD_ENDPOINT)


def assessment(issue: int, **overrides: Any) -> Any:  # noqa: ANN401 — same
    """One clean gate assessment, with any criterion or the unclean list overridden."""
    criteria = dict.fromkeys(admission.PART_A_KEYS, admission.MET)
    criteria.update(overrides.pop("criteria", {}))
    return admission.Assessment(
        issue=issue,
        dispatch_id=f"d-test-{issue}",
        criteria=tuple(sorted(criteria.items())),
        unclean=tuple(overrides.pop("unclean", ())),
        landing_sha=overrides.pop("landing_sha", ""),
        recorded_at=NOW + issue,
    )


def citing(issue: int, resolved: int, total: int) -> Any:  # noqa: ANN401 — same
    """One recon assessment: how many of its citations resolved, out of how many."""
    return admission.Assessment(
        issue=issue,
        dispatch_id=f"d-test-{issue}",
        citations_resolved=resolved,
        citations_total=total,
        recorded_at=NOW + issue,
    )


def feed(state: Any, seat: str, assessments: list[Any]) -> Any:  # noqa: ANN401 — same
    """Append a run of assessments to one route and return the standing after them."""
    standing = admission.standing_for(state, LANE, PROFILE, seat)
    for item in assessments:
        _, standing, refusal = admission.append(state, LANE, PROFILE, seat, item)
        assert refusal is None, refusal
    return standing


# ------------------------------------------------------ the bar itself, as pre-registered


def test_the_ruled_numbers_are_what_the_module_carries() -> None:
    # The point of pre-registration: these move only by a human ruling, never by a lane's
    # numbers arriving. A red here is a bar that changed, which is the thing #224 exists
    # to prevent.
    assert admission.N == 10
    assert admission.MAX_UNCLEAN == 1
    assert admission.MAX_ATTEMPTS == 2
    assert admission.CITATION_FLOOR == 0.90
    assert admission.OPERATING_CHARACTERISTICS == ((0.885, 0.68), (0.75, 0.24), (0.60, 0.05))
    assert admission.CLAUDE_BASELINE == (116, 131)
    assert admission.BAR_ID == "cti.admission/224"
    assert "2026-08-05T20:00Z" in admission.RULING


def test_part_a_is_the_four_criteria_the_ruling_names() -> None:
    assert admission.PART_A_KEYS == (
        "close_names_sha",
        "fast_green",
        "corpus_verdict",
        "hooks_clean",
    )
    # Only the corpus criterion is conditional, because only it is written "where the
    # landing touches an in-world surface". The other three bind on every issue.
    waivable = {criterion.key for criterion in admission.PART_A if criterion.waivable}
    assert waivable == {"corpus_verdict"}


def test_part_b_names_the_three_unclean_reasons_from_the_derivation() -> None:
    assert admission.UNCLEAN_REASONS == ("rework", "finding", "reopen")


def test_bar_prints_both_parts_the_retry_rule_and_the_operating_characteristics() -> None:
    printed = "\n".join(admission.bar_lines())
    assert "n=10" in printed
    assert "attempts=2" in printed
    assert "part_a=every criterion, every issue, 10/10, no allowance" in printed
    assert "part_b=at most 1 unclean in 10" in printed
    assert "oc.clean_rate=0.885 p_clears=0.68" in printed
    assert "oc.clean_rate=0.600 p_clears=0.05" in printed
    assert "citation_bar=at least 90% of cited file:line resolve, pooled" in printed
    for key in admission.PART_A_KEYS:
        assert key in printed


# --------------------------------------------------------------------- Part A, no allowance


def test_ten_clean_issues_admit_the_profile() -> None:
    verdict = admission.judge_gate_attempt([assessment(n) for n in range(1, 11)])
    assert verdict.state == admission.CLEARED
    assert verdict.assessed == 10


def test_nine_clean_issues_are_not_yet_ten() -> None:
    verdict = admission.judge_gate_attempt([assessment(n) for n in range(1, 10)])
    assert verdict.state == admission.OPEN
    assert verdict.remaining == 1


def test_one_missed_criterion_ends_the_attempt_at_once() -> None:
    # "No allowance" is not "nine out of ten": the attempt is over on the issue that
    # missed, and the nine clean issues after it do not rescue it.
    run = [assessment(1, criteria={"fast_green": admission.NOT_MET})]
    run += [assessment(n) for n in range(2, 11)]
    verdict = admission.judge_gate_attempt(run)
    assert verdict.state == admission.FAILED
    assert "Part A allows no failure in 10" in verdict.reason
    assert any("issue=1 missed=fast_green" in line for line in verdict.detail)


def test_a_criterion_nobody_judged_does_not_pass() -> None:
    # The #41 shape, and the ruling's own reasoning for 10/10 on criterion 3: an absent
    # signal is not a clean one.
    silent = admission.Assessment(issue=1, dispatch_id="d", criteria=(("fast_green", "met"),))
    assert set(silent.part_a_missed()) == {"close_names_sha", "corpus_verdict", "hooks_clean"}
    assert admission.judge_gate_attempt([silent]).state == admission.FAILED


def test_the_corpus_criterion_may_be_waived_where_it_does_not_apply() -> None:
    run = [
        assessment(n, criteria={"corpus_verdict": admission.NOT_APPLICABLE}) for n in range(1, 11)
    ]
    assert admission.judge_gate_attempt(run).state == admission.CLEARED


def test_a_waived_criterion_is_the_only_one_that_may_be_waived() -> None:
    run = [assessment(1, criteria={"fast_green": admission.NOT_APPLICABLE})]
    assert admission.judge_gate_attempt(run).state == admission.FAILED


# ------------------------------------------------------------------------ Part B, outcomes


def test_one_unclean_issue_in_ten_still_clears() -> None:
    run = [assessment(1, unclean=("rework",))] + [assessment(n) for n in range(2, 11)]
    assert admission.judge_gate_attempt(run).state == admission.CLEARED


@pytest.mark.parametrize(
    "reasons",
    [("rework", "finding"), ("reopen", "reopen"), ("finding", "rework")],
)
def test_two_unclean_issues_in_ten_fail(reasons: tuple[str, str]) -> None:
    run = [assessment(1, unclean=(reasons[0],)), assessment(2, unclean=(reasons[1],))]
    run += [assessment(n) for n in range(3, 11)]
    verdict = admission.judge_gate_attempt(run)
    assert verdict.state == admission.FAILED
    assert "Part B allows at most 1 unclean in 10" in verdict.reason


def test_part_a_decides_before_part_b_when_both_are_broken() -> None:
    # Reported as the process failure it is, because Part B measures outcomes conditional
    # on the gates having run and a skipped gate makes Part B's reading meaningless.
    run = [assessment(1, criteria={"hooks_clean": admission.NOT_MET}, unclean=("rework",))]
    run += [assessment(n, unclean=("finding",)) for n in range(2, 4)]
    assert "Part A" in admission.judge_gate_attempt(run).reason


# ------------------------------------------------------- attempts, and the ruling's retry


def test_a_fresh_route_starts_at_zero_on_attempt_one_and_is_dispatchable(tmp_path: Path) -> None:
    standing = admission.standing_for(store(tmp_path), LANE, PROFILE, "implementer")
    assert standing.state == admission.PROBATION
    assert standing.attempt == 1
    assert standing.judgement.assessed == 0
    assert standing.dispatchable
    assert not standing.admitted


def test_probation_is_dispatchable_because_the_record_accrues_only_by_running(
    tmp_path: Path,
) -> None:
    state = store(tmp_path)
    standing = feed(state, "implementer", [assessment(n) for n in range(1, 6)])
    assert standing.state == admission.PROBATION
    assert standing.judgement.assessed == 5
    assert admission.dispatch_refusal(state, LANE, PROFILE, "implementer") is None


def test_ten_clean_records_admit_and_the_transition_is_journalled(tmp_path: Path) -> None:
    state = store(tmp_path)
    standing = feed(state, "implementer", [assessment(n) for n in range(1, 11)])
    assert standing.state == admission.ADMITTED
    assert standing.admitted

    lines = [json.loads(line) for line in state.journal.read_text("utf-8").splitlines()]
    assert [line["attributes"]["cti.admission.to"] for line in lines] == [admission.ADMITTED]
    # The collector is not there, and the journal is still the complete record.
    assert lines[0]["exported"] is False
    assert lines[0]["attributes"]["cti.admission.bar_id"] == admission.BAR_ID


def test_a_failed_attempt_starts_the_next_one_empty(tmp_path: Path) -> None:
    state = store(tmp_path)
    standing = feed(state, "implementer", [assessment(1, criteria={"fast_green": "not_met"})])
    assert standing.state == admission.PROBATION
    assert standing.attempt == 2
    # Attempts do not pool: the failed attempt's issue is history, not credit.
    assert standing.judgement.assessed == 0
    assert "do not pool" in standing.reason


def test_a_second_failed_attempt_escalates_and_stops_dispatch(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "implementer", [assessment(1, criteria={"fast_green": "not_met"})])
    standing = feed(state, "implementer", [assessment(2, criteria={"hooks_clean": "not_met"})])
    assert standing.state == admission.ESCALATED
    assert not standing.dispatchable
    assert admission.dispatch_refusal(state, LANE, PROFILE, "implementer") is not None


def test_there_is_no_third_attempt_to_improvise(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "implementer", [assessment(1, criteria={"fast_green": "not_met"})])
    feed(state, "implementer", [assessment(2, criteria={"fast_green": "not_met"})])
    _, _, refusal = admission.append(state, LANE, PROFILE, "implementer", assessment(3))
    assert refusal is not None
    assert refusal.kind == "admission_escalated"


def test_an_admitted_route_refuses_further_assessments(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "implementer", [assessment(n) for n in range(1, 11)])
    _, _, refusal = admission.append(state, LANE, PROFILE, "implementer", assessment(11))
    assert refusal is not None
    assert refusal.kind == "already_admitted"
    assert "breaker" in refusal.action


def test_reset_is_what_ends_an_escalation(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "implementer", [assessment(1, criteria={"fast_green": "not_met"})])
    feed(state, "implementer", [assessment(2, criteria={"fast_green": "not_met"})])
    after = admission.clear(state, LANE, PROFILE, "implementer", NOW)
    assert after.state == admission.PROBATION
    assert after.attempt == 1
    assert after.judgement.assessed == 0


# ------------------------------------------------------------- the seats, and inheritance


def test_clearing_the_implementer_bar_admits_the_mechanical_seat_with_no_second_ten(
    tmp_path: Path,
) -> None:
    state = store(tmp_path)
    feed(state, "implementer", [assessment(n) for n in range(1, 11)])
    mechanical = admission.standing_for(state, LANE, PROFILE, "mechanical")
    assert mechanical.admitted
    assert "implementer" in mechanical.reason
    assert mechanical.judgement.assessed == 0


def test_the_mechanical_seat_can_also_be_earned_directly(tmp_path: Path) -> None:
    state = store(tmp_path)
    standing = feed(state, "mechanical", [assessment(n) for n in range(1, 11)])
    assert standing.admitted
    # Earned, not inherited: the implementer seat has run nothing.
    assert admission.standing_for(state, LANE, PROFILE, "implementer").state == admission.PROBATION


def test_the_implementer_seat_does_not_inherit_from_mechanical(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "mechanical", [assessment(n) for n in range(1, 11)])
    assert not admission.standing_for(state, LANE, PROFILE, "implementer").admitted


def test_claude_native_is_exempt_because_nothing_leaves_claude_there(tmp_path: Path) -> None:
    standing = admission.standing_for(store(tmp_path), "claude-native", "opus-high", "implementer")
    assert standing.state == admission.EXEMPT
    assert standing.dispatchable
    assert not standing.admitted


@pytest.mark.parametrize("seat", ["fable", "orchestrator"])
def test_a_seat_decision_two_bars_has_no_admission_route(tmp_path: Path, seat: str) -> None:
    standing = admission.standing_for(store(tmp_path), LANE, PROFILE, seat)
    assert standing.state == admission.NO_ROUTE
    assert "Decision 2" in standing.reason


# ------------------------------------------------------- the recon and review substitute


def test_the_citation_bar_clears_at_the_floor() -> None:
    run = [citing(n, 9, 10) for n in range(1, 11)]
    verdict = admission.judge_citation_attempt(run)
    assert verdict.state == admission.CLEARED
    assert verdict.citation_rate == pytest.approx(0.90)


def test_the_citation_bar_fails_below_the_floor() -> None:
    run = [citing(n, 8, 10) for n in range(1, 11)]
    assert admission.judge_citation_attempt(run).state == admission.FAILED


def test_citations_pool_across_the_ten_rather_than_averaging_per_dispatch() -> None:
    # Nine dispatches raising one citation each and getting it right, and one raising
    # ninety and getting sixty-three right: the per-dispatch mean is 96.4%, and the
    # population the ruling names — "its findings' citations" — is 72/99, which fails.
    run = [citing(n, 1, 1) for n in range(1, 10)] + [citing(10, 63, 90)]
    verdict = admission.judge_citation_attempt(run)
    assert verdict.citations_resolved == 72
    assert verdict.citations_total == 99
    assert verdict.state == admission.FAILED


def test_ten_dispatches_citing_nothing_fail_rather_than_clear() -> None:
    verdict = admission.judge_citation_attempt([citing(n, 0, 0) for n in range(1, 11)])
    assert verdict.state == admission.FAILED
    assert "absence is not a pass" in verdict.reason


def test_the_citation_bar_has_no_early_failure() -> None:
    # How many citations remain to be counted is unknown until the dispatches are run, so
    # a rate below the floor at dispatch three says nothing about the rate at ten.
    verdict = admission.judge_citation_attempt([citing(n, 0, 10) for n in range(1, 4)])
    assert verdict.state == admission.OPEN


@pytest.mark.parametrize("seat", ["recon", "review"])
def test_both_review_seats_are_judged_on_citations(tmp_path: Path, seat: str) -> None:
    state = store(tmp_path)
    standing = feed(state, seat, [citing(n, 10, 10) for n in range(1, 11)])
    assert standing.bar == admission.CITATION_BAR
    assert standing.admitted


# ------------------------------------------------------------------- the git cross-check


def run_git(repo: Path, *argv: str) -> str:
    """Run one git command in a scratch repo and return its stdout."""
    # S603/S607: fixed literals and this test's own strings, and `git` resolves off PATH
    # on purpose — the same reasoning `tools/admission.py` records for its own helper.
    return subprocess.run(  # noqa: S603
        ["git", *argv],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit(repo: Path, paths: dict[str, str], message: str = "test: a landing") -> str:
    """Write files into a scratch repo, commit them, and return the commit's SHA."""
    if not (repo / ".git").is_dir():
        repo.mkdir(parents=True, exist_ok=True)
        run_git(repo, "init", "-q")
        run_git(repo, "config", "user.email", "t@example.invalid")
        run_git(repo, "config", "user.name", "t")
    for name, body in paths.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", message)
    return run_git(repo, "rev-parse", "HEAD")


def test_the_cross_check_refuses_a_waived_corpus_on_an_in_world_landing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"addons/cti_core/fn_thing.sqf": "// x\n"})
    waived = assessment(1, criteria={"corpus_verdict": admission.NOT_APPLICABLE})
    found = admission.crosscheck(waived, admission.landing_paths(repo, sha))
    assert any("in-world surface" in line for line in found)


def test_the_cross_check_refuses_a_clean_hooks_claim_over_an_edited_spec(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"tests/specs/sp-001.yaml": "id: sp-001\n"})
    found = admission.crosscheck(assessment(1), admission.landing_paths(repo, sha))
    assert any("gated path" in line for line in found)


def test_the_cross_check_grants_nothing_on_an_ordinary_landing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"docs/note.md": "hello\n"})
    waived = assessment(1, criteria={"corpus_verdict": admission.NOT_APPLICABLE})
    assert admission.crosscheck(waived, admission.landing_paths(repo, sha)) == ()


def test_a_cross_check_that_could_not_run_is_not_one_that_passed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    commit(repo, {"docs/note.md": "hello\n"})
    absent = admission.landing_paths(repo, "0" * 40)
    assert absent is None
    found = admission.crosscheck(assessment(1), absent)
    assert found[0] == "crosscheck=unavailable"


def test_a_daemon_change_off_the_wire_is_not_an_in_world_surface() -> None:
    assert admission.touches_in_world(["src/cti_daemon/planner.py"]) == ()
    assert admission.touches_in_world(["src/cti_daemon/port.py"]) == ("src/cti_daemon/port.py",)


# ------------------------------------------------------------------------------ the store


def test_a_record_round_trips_through_its_file(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "implementer", [assessment(n) for n in range(1, 4)])
    read = admission.read_record(state.directory, LANE, PROFILE, "implementer")
    assert [item.issue for item in read.current.assessments] == [1, 2, 3]
    assert read.current.assessments[0].state_of("hooks_clean") == admission.MET


def test_an_unreadable_record_reads_as_a_route_at_zero_rather_than_an_escalation(
    tmp_path: Path,
) -> None:
    state = store(tmp_path)
    state.directory.mkdir(parents=True)
    admission.record_path(state.directory, LANE, PROFILE, "implementer").write_text(
        "{not json", encoding="utf-8"
    )
    standing = admission.standing_for(state, LANE, PROFILE, "implementer")
    assert standing.state == admission.PROBATION
    assert standing.dispatchable


def test_status_says_what_starts_at_zero(tmp_path: Path) -> None:
    printed = "\n".join(admission.status_lines(store(tmp_path)))
    assert "baseline=zero" in printed
    assert "nothing is back-filled" in printed
    for lane, profile in admission.FOREIGN_PROFILES:
        assert f"lane={lane} profile={profile} seat=implementer" in printed
    assert "assessed=0/10" in printed


def test_status_stops_claiming_zero_once_something_is_recorded(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "implementer", [assessment(1)])
    assert "baseline=zero" not in "\n".join(admission.status_lines(state))


# --------------------------------------------------------------------------------- the CLI


def cli(tmp_path: Path, *argv: str) -> int:
    """Run the CLI against a store in `tmp_path`, with no collector behind it."""
    return admission.main(
        ["--admission-dir", str(tmp_path / "admission"), "--otlp-endpoint", DEAD_ENDPOINT, *argv]
    )


def record_argv(repo: Path, sha: str, issue: int, *extra: str) -> list[str]:
    """Build the argv for one clean gate record."""
    return [
        "record",
        "--lane",
        LANE,
        "--profile",
        PROFILE,
        "--seat",
        "implementer",
        "--issue",
        str(issue),
        "--sha",
        sha,
        "--repo",
        str(repo),
        "--close-names-sha",
        "met",
        "--fast-green",
        "met",
        "--corpus-verdict",
        "met",
        "--hooks-clean",
        "met",
        *extra,
    ]


def test_cli_bar_and_status_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli(tmp_path, "bar") == 0
    assert cli(tmp_path, "status") == 0
    assert "bar_id=cti.admission/224" in capsys.readouterr().out


def test_cli_record_refuses_an_unjudged_criterion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"docs/note.md": "x\n"})
    argv = record_argv(repo, sha, 1)
    del argv[argv.index("--fast-green") : argv.index("--fast-green") + 2]
    assert cli(tmp_path, *argv) == admission.EXIT_REFUSED
    printed = capsys.readouterr().err
    assert "refusal=criteria_missing" in printed
    assert "fast_green" in printed


def test_cli_record_refuses_a_waived_corpus_the_diff_contradicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"missions/cti/init.sqf": "// x\n"})
    argv = record_argv(repo, sha, 1)
    argv[argv.index("--corpus-verdict") + 1] = admission.NOT_APPLICABLE
    assert cli(tmp_path, *argv) == admission.EXIT_REFUSED
    assert "refusal=crosscheck_failed" in capsys.readouterr().err
    # Nothing was written: a refused record is not a half-recorded one.
    assert (
        admission.read_record(tmp_path / "admission", LANE, PROFILE, "implementer").attempts == ()
    )


def test_cli_record_refuses_an_unknown_unclean_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"docs/note.md": "x\n"})
    assert cli(tmp_path, *record_argv(repo, sha, 1, "--unclean", "vibes")) == admission.EXIT_REFUSED
    assert "refusal=unknown_unclean_reason" in capsys.readouterr().err


def test_cli_record_refuses_citation_counts_on_a_gate_seat(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"docs/note.md": "x\n"})
    argv = record_argv(repo, sha, 1, "--citations-total", "4", "--citations-resolved", "4")
    assert cli(tmp_path, *argv) == admission.EXIT_REFUSED
    assert "refusal=wrong_bar_evidence" in capsys.readouterr().err


def test_cli_record_refuses_part_a_evidence_on_a_recon_seat(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "record",
        "--lane",
        LANE,
        "--profile",
        PROFILE,
        "--seat",
        "recon",
        "--issue",
        "1",
        "--fast-green",
        "met",
        "--citations-total",
        "4",
        "--citations-resolved",
        "4",
    ]
    assert cli(tmp_path, *argv) == admission.EXIT_REFUSED
    assert "refusal=wrong_bar_evidence" in capsys.readouterr().err


def test_cli_check_exits_nonzero_only_on_an_escalation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    check = ["check", "--lane", LANE, "--profile", PROFILE, "--seat", "implementer"]
    assert cli(tmp_path, *check) == 0
    state = admission.Store(directory=tmp_path / "admission", endpoint=DEAD_ENDPOINT)
    feed(state, "implementer", [assessment(1, criteria={"fast_green": "not_met"})])
    feed(state, "implementer", [assessment(2, criteria={"fast_green": "not_met"})])
    capsys.readouterr()
    assert cli(tmp_path, *check) == admission.EXIT_REFUSED
    assert "state=escalated" in capsys.readouterr().err


def test_cli_reset_needs_force(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli(tmp_path, "reset", "--lane", LANE, "--profile", PROFILE, "--seat", "implementer")


# ------------------------------------------------------- what `just dispatch` reads of it


def test_dispatch_refuses_a_profile_that_has_spent_both_attempts(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "implementer", [assessment(1, criteria={"fast_green": "not_met"})])
    feed(state, "implementer", [assessment(2, criteria={"fast_green": "not_met"})])
    refusal = dispatch.admission_refusal(LANE, PROFILE, "implementer", state.directory)
    assert refusal is not None
    assert refusal.kind == "admission_escalated"
    # No failure class: this says nothing about a provider or about the code under test.
    assert refusal.failure_class == ""
    assert "human" in refusal.action


def test_dispatch_lets_a_profile_on_probation_through(tmp_path: Path) -> None:
    state = store(tmp_path)
    feed(state, "implementer", [assessment(n) for n in range(1, 6)])
    assert dispatch.admission_refusal(LANE, PROFILE, "implementer", state.directory) is None


def test_dispatch_does_not_consult_admission_for_claude_native(tmp_path: Path) -> None:
    assert dispatch.admission_refusal("claude-native", "opus-high", "implementer", tmp_path) is None


def test_the_bar_governs_exactly_the_registry_dispatch_carries() -> None:
    # `tools/admission.py` keeps its own copy of the foreign lanes and profiles, because a
    # cycle between it and the dispatcher would make either one unloadable alone. This is
    # the guard that keeps the copy honest: registering a lane or profile in one place and
    # not the other is a red unit tier rather than a route nothing judges.
    foreign_lanes = tuple(sorted(name for name, lane in dispatch.LANES.items() if lane.foreign))
    assert foreign_lanes == admission.FOREIGN_LANES
    foreign_profiles = tuple(
        sorted(
            (profile.lane, profile.name)
            for profile in dispatch.PROFILES.values()
            if dispatch.LANES[profile.lane].foreign
        )
    )
    assert tuple(sorted(admission.FOREIGN_PROFILES)) == foreign_profiles


def test_every_seat_a_foreign_lane_accepts_has_a_bar() -> None:
    eligible = {seat for seat, allowed in dispatch.SEATS.items() if allowed}
    assert set(admission.SEAT_BARS) == eligible
