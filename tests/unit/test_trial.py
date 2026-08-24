"""`tools/trial.py`: the pre-registration harness, and the closure of the trial it ran (#260, #328).

#242 ruling 1 seated the orchestration loop at opus/high as a pre-registered trial in #219's and
#224's shape: ten consecutive dispatch cycles, failing on any one of five criteria the human
pre-registered. The value of pre-registering is that the bar does not move once the numbers are
in, so the first thing here is a guard on the constants themselves — if the cycle count, the bar
id or the five criteria change, a test goes red and the change is argued.

ADR-0071 ruling 2 then closed that trial as **inconclusive**, and the second thing here is a
guard on the closure: that the default surface reads closed, that starting, recording and
clearing are all refused by name, that the cycles already recorded survive it, and that the five
criteria it leaves unmeasured are printed by name rather than as a count. A closure a reader
cannot see is the departure this issue exists to avoid making twice.

Everything else is the harness, exercised with `closure=None` — which is not a test-only escape
hatch but the shape a later pre-registration would use, and the whole reason the harness outlives
the trial. Those are the claims that would let a trial look like a trial and admit anything:

- that "not started" is a state distinct from "0/10", because the clock starts at an explicit act
  and not at this tool's existence;
- that the first missed criterion ends it — no allowance, no nine-out-of-ten;
- that a failure records and reports but never auto-reverts anything and never carries a failure
  class, because nothing here is found about a provider, a lane or the code under test;
- that the three mechanical criteria are computed where the artefacts decide and left to the
  recorder where they do not, and that the two hand criteria can never be filled from an audit;
- that the bar is immutable once the first assessment lands, so a record under a different bar id
  is refused.

Nothing here reaches a provider, a collector or this box's real records: every store and every
queue dir is a `tmp_path`, and the OTel endpoint is one nothing listens on.
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

# `harness` rather than `trial`, because a `Trial` value is the thing under test in several of
# these and the module would shadow it.
harness: ModuleType = load_tool("trial")
queue_policy: ModuleType = load_tool("queue_policy")

# A port nothing listens on, so the export fails the way a stopped collector fails.
DEAD_ENDPOINT = "http://127.0.0.1:2996/v1/logs"

NOW = 1_785_000_000.0

# Pinned, and straddling the dispatch window, so the audit's window check does not ride the
# wall clock. The landing is armed before and committed after, exactly as `landed_setup` pins it.
DISPATCH_ARMED = "2026-08-06T20:00:00+00:00"
COMMIT_BEFORE = "2026-08-06T19:00:00+00:00"
COMMIT_AFTER = "2026-08-06T20:30:00+00:00"


def store(tmp_path: Path) -> Any:  # noqa: ANN401 — a tools/ module loads dynamically, so its types are Unknown here
    """Build an admission store whose collector is deliberately not there."""
    return harness.Store(directory=tmp_path / "admission", endpoint=DEAD_ENDPOINT)


# The harness with no closure applied. Every test below that exercises the *machinery* rather
# than the closure goes through these, and that is the point of the argument existing: a
# pre-registration harness that only ever runs closed is not a harness, it is a tombstone.
def start_trial(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 — a dynamically loaded module
    """`start_trial` as a live pre-registration sees it."""
    return harness.start_trial(*args, closure=None, **kwargs)


def record_trial_cycle(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 — same
    """`record_trial_cycle` as a live pre-registration sees it."""
    return harness.record_trial_cycle(*args, closure=None, **kwargs)


def trial_standing(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 — same
    """`trial_standing` as a live pre-registration sees it."""
    return harness.trial_standing(*args, closure=None, **kwargs)


def reset_trial(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 — same
    """`reset_trial` as a live pre-registration sees it."""
    return harness.reset_trial(*args, closure=None, **kwargs)


def verdicts(**overrides: str) -> tuple[Any, ...]:
    """All five criteria met, with any criterion overridden to `not_met` or another state."""
    base = dict.fromkeys(harness.TRIAL_CRITERION_KEYS, harness.MET)
    base.update(overrides)
    return tuple(
        harness.CriterionVerdict(key, value, harness.HAND_ASSERTED) for key, value in base.items()
    )


def cycle(number: int, issue: int | None = None, **overrides: str) -> Any:  # noqa: ANN401 — same
    """One clean cycle, with any criterion verdict overridden."""
    return harness.CycleAssessment(
        cycle=number,
        issue=issue if issue is not None else 259 + number,
        dispatch_id=f"d-cycle-{number}",
        criteria=verdicts(**overrides),
        landing_sha="abc1234",
        recorded_at=NOW + number,
    )


def policy_json(
    queue_dir: Path,
    *,
    frozen: bool = False,
    packages: list[dict[str, Any]] | None = None,
) -> Path:
    """Write a queue policy the freeze criterion reads, minimal and schema-valid."""
    queue_dir.mkdir(parents=True, exist_ok=True)
    document = {
        "version": 1,
        "freeze": {
            "state": "frozen" if frozen else "open",
            "since": "2026-08-06",
            "ruling": "human, 2026-08-06",
        },
        "wip_limit": {"value": 3, "since": "2026-08-06", "ruling": "human, 2026-08-06"},
        "packages": packages or [],
    }
    path = queue_dir / "policy.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def run_git(repo: Path, *argv: str, when: str = "") -> str:
    """Run one git command in a scratch repo, pinning author/committer dates when `when` is set."""
    env = None
    if when:
        env = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when, "PATH": "/usr/bin:/bin"}
    return subprocess.run(  # noqa: S603 — fixed literals and this test's own strings
        ["git", *argv],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def commit(repo: Path, paths: dict[str, str], message: str, when: str = "") -> str:
    """Commit files into a scratch repo and return the SHA on `origin/main`."""
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
    run_git(repo, "commit", "-q", "-m", message, when=when)
    sha = run_git(repo, "rev-parse", "HEAD")
    # Make the audit's default ref real so the tests exercise the branch holding the landing.
    run_git(repo, "update-ref", "refs/remotes/origin/main", sha)
    return sha


def dispatch_record(
    root: Path, dispatch_id: str, *, issue: int, base_sha: str, seat: str = "implementer"
) -> Path:
    """Write one dispatch record in the shape `tools/dispatch.py` writes."""
    directory = root / dispatch_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": dispatch_id,
                "lane": "zai",
                "profile": "zai-glm52-max",
                "seat": seat,
                "issue": issue,
                "base_sha": base_sha,
                "planned_at": DISPATCH_ARMED,
            }
        ),
        encoding="utf-8",
    )
    (directory / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": dispatch_id,
                "returncode": 0,
                "outcome": "ok",
                "started_at": DISPATCH_ARMED,
            }
        ),
        encoding="utf-8",
    )
    return directory


# ----------------------------------------------------------------------- the bar, as ruled


def test_the_constants_are_what_was_ruled() -> None:
    """Hold the pre-registered numbers and criteria still."""
    assert harness.TRIAL_N == 10
    assert harness.TRIAL_BAR_ID == "cti.admission.orchestration-trial/242"
    assert [c.key for c in harness.TRIAL_CRITERIA] == [
        "freeze_or_reservation",
        "non_result_treated_as_result",
        "landing_in_window",
        "gated_surface_approved",
        "no_drafting_slack_transcribed",
    ]
    # Three mechanical, two hand — the split the standing prints, verbatim from the ruling.
    assert [c.mechanical for c in harness.TRIAL_CRITERIA] == [True, False, True, True, False]
    assert [c.text for c in harness.TRIAL_CRITERIA] == [
        "a dispatch launched against a freeze or reservation the policy file recorded",
        (
            "an `infra_unavailable`, `quota_exhausted`, `provider_refused` or "
            "`untyped_harness_failure` treated as a result"
        ),
        "a landing recorded against an issue its dispatch could not have made",
        "a gated surface edited without human approval or an ADR-0013 record",
        (
            "a ruling with drafting slack transcribed onto a gated semantic surface from the "
            "orchestration seat rather than dispatched (#217 decision 4)"
        ),
    ]


# ------------------------------------------------------------- the closure, and its cost


def test_the_trial_is_closed_as_inconclusive_by_default(tmp_path: Path) -> None:
    """#328's third criterion: the default surface reads closed, not running and not failed."""
    harness.start_trial(store(tmp_path), "2026-08-06", NOW, closure=None)
    standing = harness.trial_standing(harness.read_trial(store(tmp_path).directory))
    assert standing.state == harness.TRIAL_CLOSED
    assert harness.TRIAL_CLOSURE.verdict == harness.TRIAL_CLOSED
    assert harness.TRIAL_CLOSURE.bar_id == harness.TRIAL_BAR_ID
    assert "opus/high" in harness.TRIAL_CLOSURE.why
    assert "opus/xhigh" in harness.TRIAL_CLOSURE.why


def test_the_closure_names_all_five_unmeasured_criteria_rather_than_counting_them() -> None:
    """Print the loss as a list rather than a count.

    A count reads as an accounting entry and hides which questions nobody is asking any
    more, which is the whole reason this is called a loss.
    """
    assert harness.TRIAL_CLOSURE.unmeasured == harness.TRIAL_CRITERION_KEYS
    assert len(harness.TRIAL_CLOSURE.unmeasured) == 5
    printed = "\n".join(harness.closure_lines(harness.TRIAL_CLOSURE))
    for criterion in harness.TRIAL_CRITERIA:
        assert criterion.key in printed
        assert criterion.text in printed
    # And the sentence that says what an unmeasured criterion is not.
    assert "loss, not a substitution" in printed
    assert "a criterion nobody violates" in printed
    assert "did not finish is not a trial that passed" in printed
    # `just trial bar` is the surface a reader meets it on.
    assert "loss, not a substitution" in "\n".join(harness.trial_bar_lines())


def test_the_closed_trial_keeps_its_cycles_as_history(tmp_path: Path) -> None:
    """Closed is not cleared. A closure that discarded the record would be an erasure."""
    start_trial(store(tmp_path), "2026-08-06", NOW)
    record_trial_cycle(store(tmp_path), cycle(1))
    reread = harness.read_trial(store(tmp_path).directory)
    assert len(reread.cycles) == 1
    standing = harness.trial_standing(reread)
    assert standing.state == harness.TRIAL_CLOSED
    assert standing.judgement.assessed == 1
    assert "assessed=1/10" in standing.line()


def test_a_closed_trial_is_not_started_recorded_against_or_cleared(tmp_path: Path) -> None:
    """It is closed rather than restarted, and each of the three acts refuses by the same name."""
    _, start_refusal = harness.start_trial(store(tmp_path), "2026-08-06", NOW)
    assert start_refusal is not None
    assert start_refusal.kind == "trial_closed"

    start_trial(store(tmp_path), "2026-08-06", NOW)
    _, _, record_refusal = harness.record_trial_cycle(store(tmp_path), cycle(1))
    assert record_refusal is not None
    assert record_refusal.kind == "trial_closed"

    _, reset_refusal = harness.reset_trial(store(tmp_path), NOW + 1)
    assert reset_refusal is not None
    assert reset_refusal.kind == "trial_closed"
    # And the refusal carries the loss rather than only the verdict.
    assert any("loss, not a substitution" in line for line in reset_refusal.lines())


def test_a_closed_trial_is_silent_on_the_watch_report_surface(tmp_path: Path) -> None:
    """A closure is a record, not a finding: there is nothing for a turn's top line to do."""
    start_trial(store(tmp_path), "2026-08-06", NOW)
    assert harness.trial_standing(harness.read_trial(store(tmp_path).directory)).report_line() is (
        None
    )


def test_a_closure_for_another_bar_does_not_reach_this_one(tmp_path: Path) -> None:
    """One pre-registration's verdict never silently lands on another's.

    The same rule the record's own `bar_id` check enforces, in the same direction — so a
    later trial started under a new id runs rather than inheriting this one's ending.
    """
    start_trial(store(tmp_path), "2026-08-06", NOW)
    other = harness.TRIAL_CLOSURE._replace(bar_id="cti.something-else/999")
    standing = harness.trial_standing(harness.read_trial(store(tmp_path).directory), other)
    assert standing.state == harness.TRIAL_RUNNING


def test_the_bar_is_not_a_dispatch_gate() -> None:
    """Keep trial reporting outside the dispatch gate."""
    # No trial refusal is exposed under a name the dispatcher could read.
    assert not hasattr(harness, "trial_dispatch_refusal")
    # And since #328 the module exposes no dispatch read of any kind: the bar that had one
    # is gone, so a dispatcher importing this would find nothing to refuse on.
    assert not hasattr(harness, "dispatch_refusal")
    # The namespace also keeps these distinct from route refusals.
    kinds = (
        "trial_not_started",
        "trial_already_started",
        "trial_bar_amended",
        "trial_failed",
        "trial_cleared",
    )
    assert all(kind.startswith("trial_") for kind in kinds)


def test_the_cycle_recorder_cannot_skip_the_mechanical_audit() -> None:
    with pytest.raises(SystemExit):
        harness.parse_args(["record", "--cycle", "1", "--issue", "260"])


# ------------------------------------------------------------------ the clock and its states


def test_an_absent_trial_reads_as_not_started_not_zero_of_ten(tmp_path: Path) -> None:
    """The tool does not begin counting because it exists; nothing has started the clock."""
    standing = trial_standing(harness.read_trial(store(tmp_path).directory))
    assert standing.state == harness.TRIAL_NOT_STARTED
    assert standing.started is False
    assert standing.judgement.assessed == 0


def test_starting_the_clock_moves_to_zero_of_ten_not_started_distinct(tmp_path: Path) -> None:
    """Move from not started to a distinct running 0/10."""
    after, refusal = start_trial(store(tmp_path), "2026-08-06", NOW)
    assert refusal is None
    assert after.state == harness.TRIAL_RUNNING
    assert after.started is True
    assert after.judgement.assessed == 0
    assert after.judgement.remaining == harness.TRIAL_N
    # And it is distinct from not_started: the sentinel is gone, the ruling is recorded.
    reread = trial_standing(harness.read_trial(store(tmp_path).directory))
    assert reread.state == harness.TRIAL_RUNNING
    assert reread.started is True
    assert reread.seat_drop_date == "2026-08-06"


def test_starting_the_clock_requires_an_explicit_iso_date(tmp_path: Path) -> None:
    after, refusal = start_trial(store(tmp_path), "6 August", NOW)
    assert after.state == harness.TRIAL_NOT_STARTED
    assert refusal is not None
    assert refusal.kind == "trial_start_date_invalid"
    assert not (store(tmp_path).directory / harness.TRIAL_FILE).exists()


def test_the_clock_starts_once(tmp_path: Path) -> None:
    """A second start is refused, not silently idempotent — the start is one recorded act."""
    start_trial(store(tmp_path), "2026-08-06", NOW)
    _, refusal = start_trial(store(tmp_path), "2026-08-07", NOW + 1)
    assert refusal is not None
    assert refusal.kind == "trial_already_started"


def test_a_cycle_recorded_before_the_clock_starts_is_refused(tmp_path: Path) -> None:
    """No start, no cycles: a record against a not_started trial accrues nothing."""
    _, _, refusal = record_trial_cycle(store(tmp_path), cycle(1))
    assert refusal is not None
    assert refusal.kind == "trial_not_started"


# ------------------------------------------------------------------------- judging the trial


def test_a_clean_cycle_accrues_running_k_of_ten(tmp_path: Path) -> None:
    start_trial(store(tmp_path), "2026-08-06", NOW)
    before, after, refusal = record_trial_cycle(store(tmp_path), cycle(1))
    assert refusal is None
    assert before.judgement.assessed == 0
    assert after.state == harness.TRIAL_RUNNING
    assert after.judgement.assessed == 1
    assert after.judgement.remaining == 9


def test_ten_consecutive_clean_cycles_clear_the_trial(tmp_path: Path) -> None:
    start_trial(store(tmp_path), "2026-08-06", NOW)
    for number in range(1, harness.TRIAL_N + 1):
        record_trial_cycle(store(tmp_path), cycle(number))
    standing = trial_standing(harness.read_trial(store(tmp_path).directory))
    assert standing.state == harness.CLEARED


def test_a_clear_refuses_further_cycles(tmp_path: Path) -> None:
    start_trial(store(tmp_path), "2026-08-06", NOW)
    for number in range(1, harness.TRIAL_N + 1):
        record_trial_cycle(store(tmp_path), cycle(number))
    _, _, refusal = record_trial_cycle(store(tmp_path), cycle(99))
    assert refusal is not None
    assert refusal.kind == "trial_cleared"


@pytest.mark.parametrize("criterion", harness.TRIAL_CRITERION_KEYS)
def test_the_first_missed_criterion_ends_the_trial_no_allowance(
    tmp_path: Path, criterion: str
) -> None:
    """No allowance: the first criterion any cycle misses fails the whole trial at once."""
    start_trial(store(tmp_path), "2026-08-06", NOW)
    record_trial_cycle(store(tmp_path), cycle(1))
    before, after, refusal = record_trial_cycle(
        store(tmp_path), cycle(2, **{criterion: harness.NOT_MET})
    )
    assert refusal is None
    assert before.state == harness.TRIAL_RUNNING
    assert after.state == harness.FAILED
    assert criterion in after.judgement.detail[0]


def test_a_failure_carries_no_class_and_does_not_refuse_dispatch(tmp_path: Path) -> None:
    """A failed trial is a finding for the human; it names no provider, lane or code."""
    start_trial(store(tmp_path), "2026-08-06", NOW)
    _, after, _ = record_trial_cycle(
        store(tmp_path), cycle(1, non_result_treated_as_result=harness.NOT_MET)
    )
    assert after.state == harness.FAILED
    # No failure class anywhere in the detail: the verdict says nothing about a provider or lane.
    assert all("class=" not in line for line in after.judgement.detail)
    # And the standing line carries the no-auto-revert, no-class reasoning.
    report = after.report_line()
    assert report is not None
    assert "no failure class" in report


def test_a_failed_trial_refuses_further_cycles_until_the_human_clears_it(tmp_path: Path) -> None:
    start_trial(store(tmp_path), "2026-08-06", NOW)
    record_trial_cycle(store(tmp_path), cycle(1, landing_in_window=harness.NOT_MET))
    _, _, refusal = record_trial_cycle(store(tmp_path), cycle(2))
    assert refusal is not None
    assert refusal.kind == "trial_failed"
    # A clear returns the trial to not_started, where a fresh start accrues from cycle 1 again.
    reset, reset_refusal = reset_trial(store(tmp_path), NOW + 2)
    assert reset_refusal is None
    assert reset.state == harness.TRIAL_NOT_STARTED


def test_cycles_are_consecutive_and_one_per_issue(tmp_path: Path) -> None:
    start_trial(store(tmp_path), "2026-08-06", NOW)
    _, _, skipped = record_trial_cycle(store(tmp_path), cycle(2))
    assert skipped is not None
    assert skipped.kind == "trial_cycle_out_of_sequence"

    record_trial_cycle(store(tmp_path), cycle(1))
    _, _, repeated = record_trial_cycle(store(tmp_path), cycle(2, issue=260))
    assert repeated is not None
    assert repeated.kind == "trial_issue_repeated"


# -------------------------------------------------------------------- the silent-while-clean report


def test_the_report_is_silent_while_clean(tmp_path: Path) -> None:
    """Print nothing while the trial is not started, running, or cleared."""
    not_started = trial_standing(harness.read_trial(store(tmp_path).directory))
    assert not_started.report_line() is None
    start_trial(store(tmp_path), "2026-08-06", NOW)
    running = trial_standing(harness.read_trial(store(tmp_path).directory))
    assert running.report_line() is None
    for number in range(1, harness.TRIAL_N + 1):
        record_trial_cycle(store(tmp_path), cycle(number))
    cleared = trial_standing(harness.read_trial(store(tmp_path).directory))
    assert cleared.report_line() is None


def test_the_report_names_the_failed_cycle_when_the_trial_fails(tmp_path: Path) -> None:
    start_trial(store(tmp_path), "2026-08-06", NOW)
    record_trial_cycle(store(tmp_path), cycle(1, freeze_or_reservation=harness.NOT_MET))
    failed = trial_standing(harness.read_trial(store(tmp_path).directory))
    line = failed.report_line()
    assert line is not None
    assert line.startswith("orchestration-trial=failed")
    assert "cycle=1" in line


# ----------------------------------------------- three mechanical, two hand, visibly marked


def test_the_audit_computes_three_mechanical_and_names_the_two_hand(tmp_path: Path) -> None:
    """The audit answers the three it can and says the two it cannot; hand is never filled."""
    repo = tmp_path / "repo"
    base = commit(repo, {"docs/note.md": "before\n"}, "docs: the base", when=COMMIT_BEFORE)
    landing = commit(
        repo, {"docs/note.md": "after\n"}, "docs: a landing\n\nrefs #260", when=COMMIT_AFTER
    )
    root = tmp_path / "dispatches"
    dispatch_record(root, "d-20260806-200000-abcdef", issue=260, base_sha=base)
    policy_json(tmp_path / "queue")
    result = harness.trial_audit(
        repo,
        260,
        f"Landed at {landing[:7]}.",
        dispatch_root=root,
        queue_dir=tmp_path / "queue",
        source="file=test",
    )
    keys = {criterion.key for criterion in result.criteria}
    # Exactly the three mechanical, never the two hand.
    assert keys == {"freeze_or_reservation", "landing_in_window", "gated_surface_approved"}
    # The landing is in its window and touched nothing gated, so those two are met.
    assert result.verdict_of("landing_in_window") == harness.MET
    assert result.verdict_of("gated_surface_approved") == harness.MET
    # And the rendered audit tells the recorder which two to assert by hand.
    assert "non_result_treated_as_result" in " ".join(result.lines())
    assert "no_drafting_slack_transcribed" in " ".join(result.lines())


def test_the_recorder_marks_three_tool_checks_and_two_hand_assertions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = store(tmp_path).directory
    start_trial(store(tmp_path), "2026-08-06", NOW)
    result = harness.TrialAudit(
        issue=260,
        sha="abc1234",
        shas=("abc1234",),
        dispatch_id="d-cycle-1",
        source="fixture",
        criteria=tuple(
            harness.TrialCriterionResult(key, harness.MET, "fixture")
            for key in ("freeze_or_reservation", "landing_in_window", "gated_surface_approved")
        ),
    )
    monkeypatch.setattr(harness, "run_trial_audit_for", lambda _args: (result, None))
    # The CLI as a live pre-registration runs it: this exercises the recorder, not the closure.
    monkeypatch.setattr(harness, "closure_in_force", lambda: None)
    args = harness.parse_args(
        [
            "--admission-dir",
            str(directory),
            "record",
            "--cycle",
            "1",
            "--issue",
            "260",
            "--from-audit",
            "--non-result-treated-as-result",
            harness.MET,
            "--no-drafting-slack-transcribed",
            harness.MET,
        ]
    )
    assert harness.run_trial_record(args) == 0
    recorded = harness.read_trial(directory).cycles[0]
    assert [verdict.source for verdict in recorded.criteria] == [
        harness.TOOL_CHECKED,
        harness.HAND_ASSERTED,
        harness.TOOL_CHECKED,
        harness.TOOL_CHECKED,
        harness.HAND_ASSERTED,
    ]
    output = capsys.readouterr().out
    assert (
        "assessed_by_tool=freeze_or_reservation landing_in_window gated_surface_approved" in output
    )
    assert "asserted_by_hand=non_result_treated_as_result no_drafting_slack_transcribed" in output


def test_the_recorder_refuses_a_hand_assertion_that_contradicts_the_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = harness.TrialAudit(
        issue=260,
        sha="abc1234",
        shas=("abc1234",),
        dispatch_id="d-cycle-1",
        source="fixture",
        criteria=(harness.TrialCriterionResult("freeze_or_reservation", harness.MET, "fixture"),),
    )
    monkeypatch.setattr(harness, "run_trial_audit_for", lambda _args: (result, None))
    # The CLI as a live pre-registration runs it: this exercises the recorder, not the closure.
    monkeypatch.setattr(harness, "closure_in_force", lambda: None)
    args = harness.parse_args(
        [
            "--admission-dir",
            str(store(tmp_path).directory),
            "record",
            "--cycle",
            "1",
            "--issue",
            "260",
            "--from-audit",
            "--freeze-or-reservation",
            harness.NOT_MET,
        ]
    )
    assert harness.run_trial_record(args) == harness.EXIT_REFUSED
    assert "refusal=trial_audit_conflict" in capsys.readouterr().err


def test_the_recorder_refuses_a_closed_trial_before_it_runs_the_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`trial_closed` is the CLI's answer too, and it costs no `gh` fetch and no git walk.

    The library check inside `record_trial_cycle` fires only after the cycle is built, so
    against a closed trial the audit would run first and an unsupplied criterion would refuse
    `trial_criteria_missing` — the wrong name for why nothing can be recorded.
    """
    audited: list[object] = []

    def spy(args: object) -> tuple[object, object]:
        audited.append(args)
        return None, None

    monkeypatch.setattr(harness, "run_trial_audit_for", spy)
    args = harness.parse_args(
        [
            "--trial-dir",
            str(store(tmp_path).directory),
            "record",
            "--cycle",
            "1",
            "--issue",
            "260",
            "--from-audit",
        ]
    )
    assert harness.run_trial_record(args) == harness.EXIT_REFUSED
    assert not audited
    assert "refusal=trial_closed" in capsys.readouterr().err


def test_criterion_one_reads_freeze_not_met_where_the_policy_froze_the_issue(
    tmp_path: Path,
) -> None:
    policy_json(tmp_path / "queue", frozen=True)
    verdict = harness.trial_policy_verdict(tmp_path / "queue", 260)
    assert verdict.verdict == harness.NOT_MET
    assert verdict.decisive


def test_criterion_one_is_decisive_met_with_no_freeze_and_no_reservations(tmp_path: Path) -> None:
    policy_json(tmp_path / "queue", frozen=False)
    verdict = harness.trial_policy_verdict(tmp_path / "queue", 260)
    assert verdict.verdict == harness.MET


def test_criterion_one_leaves_reservations_to_the_recorder(tmp_path: Path) -> None:
    """A reservation violation depends on in-flight slot state the policy alone does not carry."""
    policy_json(
        tmp_path / "queue",
        packages=[
            {
                "name": "carve",
                "issues": [300],
                "exempt_from_freeze": False,
                "wip_reserved": 2,
                "since": "2026-08-06",
                "ruling": "human",
                "note": "",
            }
        ],
    )
    verdict = harness.trial_policy_verdict(tmp_path / "queue", 260)
    assert not verdict.decisive
    assert "reservation" in verdict.detail


def test_criterion_four_leaves_an_acceptance_spec_to_the_approval_record(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"tests/specs/spec.md": "# a spec\n"}, "edit an acceptance spec")
    verdict = harness.trial_gated_verdict(repo, (sha,))
    assert not verdict.decisive
    assert "approving comment" in verdict.detail


def test_criterion_four_is_met_where_no_gated_surface_was_touched(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"tools/x.py": "# code\n"}, "ordinary code")
    verdict = harness.trial_gated_verdict(repo, (sha,))
    assert verdict.verdict == harness.MET


def test_criterion_four_leaves_an_unapproved_gated_edit_to_the_recorder(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sha = commit(repo, {"CONTEXT.md": "# ctx\n"}, "edit a gated surface, no delegation record")
    verdict = harness.trial_gated_verdict(repo, (sha,))
    assert not verdict.decisive


def test_criterion_four_checks_the_source_of_a_rename_out_of_the_gated_set(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    commit(repo, {"CONTEXT.md": "# context\n"}, "gated source")
    destination = repo / "notes" / "context.md"
    destination.parent.mkdir(parents=True)
    (repo / "CONTEXT.md").rename(destination)
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "rename out of gate")
    sha = run_git(repo, "rev-parse", "HEAD")
    run_git(repo, "update-ref", "refs/remotes/origin/main", sha)

    paths = harness.landing_paths(repo, sha)
    verdict = harness.trial_gated_verdict(repo, (sha,))

    assert paths is not None
    assert "CONTEXT.md" in paths
    assert "notes/context.md" in paths
    assert not verdict.decisive
    assert "gated=CONTEXT.md" in verdict.detail


def test_criterion_four_is_met_where_every_gated_surface_is_its_own_delegated_record(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    sha = commit(
        repo,
        {"docs/adr/ADR-9999.md": "# A delegation\n\nDelegated-decision: yes\n"},
        "record a delegated decision",
    )
    verdict = harness.trial_gated_verdict(repo, (sha,))
    assert verdict.verdict == harness.MET
    assert "ADR-9999.md" in verdict.detail


def test_a_delegated_adr_does_not_authorise_a_gated_surface_travelling_beside_it(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    sha = commit(
        repo,
        {
            "CONTEXT.md": "# ctx\n",
            "docs/adr/ADR-9999.md": "# A delegation\n\nDelegated-decision: yes\n",
        },
        "edit a gated surface under that delegation",
    )
    verdict = harness.trial_gated_verdict(repo, (sha,))
    assert verdict.verdict != harness.MET
    assert not verdict.decisive
    assert "gated=CONTEXT.md" in verdict.detail
    assert "ADR-9999.md" in verdict.detail
    assert "authorises only itself" in verdict.detail


def test_an_unrelated_delegated_adr_does_not_approve_a_later_gated_edit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    commit(
        repo,
        {"docs/adr/ADR-9999.md": "# Another decision\n\nDelegated-decision: yes\n"},
        "an earlier delegation",
    )
    sha = commit(repo, {"CONTEXT.md": "# ctx\n"}, "an unrelated gated edit")
    verdict = harness.trial_gated_verdict(repo, (sha,))
    assert not verdict.decisive


def test_the_delegated_decision_marker_is_a_line_not_a_fragment(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    # A marker in body prose must not count: only the ADR field block records delegation.
    commit(
        repo,
        {"docs/adr/ADR-9998.md": "We discussed Delegated-decision: yes as an option.\n"},
        "adr",
    )
    assert harness.delegated_decisions_in(repo, (run_git(repo, "rev-parse", "HEAD"),)) == ()


def test_criterion_three_reuses_the_route_audit_s_window_check() -> None:
    """A landing outside its dispatch's window is criterion three not_met; inside is met."""
    inside = harness.Audit(
        issue=260,
        sha="abc",
        dispatch_id="d",
        source="t",
        checks=(harness.Check("dispatch_window", harness.AUDIT_OK, "in window"),),
    )
    assert harness.trial_window_verdict(inside).verdict == harness.MET
    outside = harness.Audit(
        issue=260,
        sha="abc",
        dispatch_id="d",
        source="t",
        checks=(harness.Check("dispatch_window", harness.AUDIT_OUTSIDE_WINDOW, "outside"),),
    )
    assert harness.trial_window_verdict(outside).verdict == harness.NOT_MET
    unbounded = harness.Audit(
        issue=260,
        sha="abc",
        dispatch_id="d",
        source="t",
        checks=(harness.Check("dispatch_window", harness.AUDIT_UNBOUNDED, "no records"),),
    )
    assert not harness.trial_window_verdict(unbounded).decisive


# ---------------------------------------------------------------- immutability + provenance


def test_the_bar_is_immutable_once_assessments_have_landed(tmp_path: Path) -> None:
    """Refuse a record added under a different bar id."""
    start_trial(store(tmp_path), "2026-08-06", NOW)
    record_trial_cycle(store(tmp_path), cycle(1))
    # Corrupt the stored bar id as a changed criterion would surface to an old record.
    trial = harness.read_trial(store(tmp_path).directory)
    harness.write_trial(
        store(tmp_path).directory, trial._replace(bar_id="cti.admission.orchestration-trial/other")
    )
    _, _, refusal = record_trial_cycle(store(tmp_path), cycle(2))
    assert refusal is not None
    assert refusal.kind == "trial_bar_amended"


def test_a_criterion_s_provenance_is_recorded_and_round_trips(tmp_path: Path) -> None:
    """A tool-checked criterion reads back `tool`; a hand-asserted one reads back `hand`."""
    mechanical = {c.key: harness.MET for c in harness.TRIAL_CRITERIA}
    criteria = tuple(
        harness.CriterionVerdict(
            key,
            value,
            harness.TOOL_CHECKED if c.mechanical else harness.HAND_ASSERTED,
        )
        for c, (key, value) in zip(harness.TRIAL_CRITERIA, mechanical.items(), strict=True)
    )
    one = harness.CycleAssessment(1, 260, "d", criteria, "abc", NOW)
    start_trial(store(tmp_path), "2026-08-06", NOW)
    record_trial_cycle(store(tmp_path), one)
    reread = harness.read_trial(store(tmp_path).directory).cycles[0]
    sources = {cv.key: cv.source for cv in reread.criteria}
    assert sources["landing_in_window"] == harness.TOOL_CHECKED
    assert sources["non_result_treated_as_result"] == harness.HAND_ASSERTED
    rendered = reread.lines()
    assert (
        "assessed_by_tool=freeze_or_reservation landing_in_window gated_surface_approved"
        in rendered
    )
    assert "asserted_by_hand=non_result_treated_as_result no_drafting_slack_transcribed" in rendered
    assert any(
        "criterion.2.hand=non_result_treated_as_result result=met" in line for line in rendered
    )


def test_a_hand_only_criterion_cannot_read_back_as_tool_checked(tmp_path: Path) -> None:
    directory = store(tmp_path).directory
    directory.mkdir(parents=True, exist_ok=True)
    document = (
        harness.empty_trial()
        ._replace(
            seat_drop_date="2026-08-06",
            cycles=(cycle(1),),
        )
        .document()
    )
    document["cycles"][0]["criteria"][1]["source"] = harness.TOOL_CHECKED
    (directory / harness.TRIAL_FILE).write_text(json.dumps(document), encoding="utf-8")
    assert harness.read_trial(directory).cycles == ()


def test_an_unreadable_cycle_is_dropped_not_silently_rejudged(
    tmp_path: Path,
) -> None:
    """Drop a hand-edited cycle whose shape this reader does not recognise."""
    directory = store(tmp_path).directory
    directory.mkdir(parents=True, exist_ok=True)
    (directory / harness.TRIAL_FILE).write_text(
        json.dumps(
            {
                "bar_id": harness.TRIAL_BAR_ID,
                "ruling": "r",
                "seat_drop_date": "2026-08-06",
                "cycles": [
                    {
                        "cycle": 1,
                        "issue": 260,
                        "dispatch_id": "d",
                        "landing_sha": "",
                        "recorded_at": 0.0,
                        # A criterion nobody ruled on cannot survive as `unknown`.
                        "criteria": [
                            {
                                "key": "freeze_or_reservation",
                                "verdict": "unknown",
                                "source": "tool",
                            },
                            {"key": "landing_in_window", "verdict": "met", "source": "tool"},
                            {"key": "gated_surface_approved", "verdict": "met", "source": "tool"},
                            {
                                "key": "non_result_treated_as_result",
                                "verdict": "met",
                                "source": "hand",
                            },
                            {
                                "key": "no_drafting_slack_transcribed",
                                "verdict": "met",
                                "source": "hand",
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    # The unreadable cycle is dropped, not silently re-judged.
    assert harness.read_trial(directory).cycles == ()
