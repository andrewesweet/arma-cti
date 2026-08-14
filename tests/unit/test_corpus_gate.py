"""The corpus rung: what makes a landing owe `just regress`, and what clears it (#302).

Two claims are worth more than the rest here.

**The prefix list has one authority.** `config/dispatch-routing-policy.json`'s class 5
is it; the routing gate, `tools/admission.py`'s cross-check and this rung all read that
row, and the tests below assert they agree rather than that each is individually right.
#302 exists because a list with three copies is a list that rots.

**A run that does not cover the landing is still owed, not red.** Coverage and verdict are
separate questions and only the second one is about the code under test, so a pool from
another commit, a filtered pool and a pool with a probe left unrun all come out
`corpus_owed`. Calling any of them a red would invite a reader to act on a measurement of
somebody else's tree.

The corpus enumeration is *proven* rather than mirrored on faith: one test runs
`spike/regress.sh --list` — the runner's own selection path, no lock, no world — and
asserts the tool agrees with it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import REPO, load_tool

pool_merge = load_tool("pool_merge")
pool_comment = load_tool("pool_comment")
routing_policy = load_tool("routing_policy")
corpus_gate = load_tool("corpus_gate")
admission = load_tool("admission")

POLICY = REPO / routing_policy.POLICY_RELATIVE
REGRESS = REPO / "spike" / "regress.sh"
BASH = shutil.which("bash") or "/bin/bash"


def _policy() -> Any:  # noqa: ANN401 — load_tool hands back a runtime module type
    read = routing_policy.read_policy(POLICY)
    assert read.policy is not None, read.error
    return read.policy


def _row(probe: str, class_: str = "pass", evidence: str = "") -> dict[str, object]:
    return {
        "probe": probe,
        "class": class_,
        "slot": "0",
        "elapsed_secs": 12,
        "evidence": evidence,
    }


def _pool(
    *,
    sha: str = "c0ffee1",
    worst: str = "pass",
    verdicts: list[dict[str, object]] | None = None,
    not_run: list[str] | None = None,
    stopped_early: str = "",
) -> dict[str, object]:
    return {
        "git_sha": sha,
        "worst_class": worst,
        "stopped_early": stopped_early,
        "not_run": not_run or [],
        "verdicts": verdicts if verdicts is not None else [_row("alpha"), _row("beta")],
    }


def _run(document: dict[str, object], **overrides: object) -> Any:  # noqa: ANN401
    fields: dict[str, object] = {
        "path": Path("/runs/20260809T100000Z-pool"),
        "document": document,
        "sha": str(document.get("git_sha", "")),
        "known": True,
        "moved": (),
        "dirty": None,
    }
    fields.update(overrides)
    return corpus_gate.Run(**fields)


def _lines(finding: Any) -> str:  # noqa: ANN401
    return "\n".join(finding.found)


# ------------------------------------------------------------- the one authority


def test_the_landing_check_and_the_routing_policy_read_the_same_prefixes() -> None:
    """#302's acceptance criterion: one authority, with a test that the readers agree."""
    policy = _policy()
    class_five = next(rule for rule in policy.rules if rule.id == routing_policy.IN_WORLD_CLASS_ID)
    assert class_five.name == routing_policy.IN_WORLD_CLASS
    assert routing_policy.in_world_prefixes(policy) == class_five.landing_path_prefixes


def test_the_admission_crosscheck_reads_that_same_authority() -> None:
    """`tools/brief.py`'s gate prediction reads this constant too, so all three agree."""
    assert routing_policy.in_world_prefixes(_policy()) == admission.IN_WORLD_PREFIXES


def test_the_rows_two_halves_agree_so_a_dispatch_and_a_landing_mean_the_same_thing() -> None:
    class_five = next(rule for rule in _policy().rules if rule.id == 5)
    assert class_five.issue_path_prefixes == class_five.landing_path_prefixes


def test_a_policy_that_lost_the_in_world_class_cannot_govern_at_all() -> None:
    """Otherwise the rung computes 'nothing is in-world' and passes every in-world diff."""
    document = json.loads(POLICY.read_text(encoding="utf-8"))
    for rule in document["classes"]:
        if rule["id"] == 5:
            rule["landing_path_prefixes"] = []
    with pytest.raises(routing_policy.PolicyError, match="one authority"):
        routing_policy.parse_policy(json.dumps(document))


def test_the_authority_is_found_by_id_so_the_rows_own_name_is_not_load_bearing() -> None:
    """The ids are validated as ascending and unique, which makes them the stable handle."""
    document = json.loads(POLICY.read_text(encoding="utf-8"))
    for rule in document["classes"]:
        if rule["id"] == routing_policy.IN_WORLD_CLASS_ID:
            rule["name"] = "world_landings"
    policy = routing_policy.parse_policy(json.dumps(document))
    assert routing_policy.in_world_prefixes(policy) == admission.IN_WORLD_PREFIXES


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("addons/main/functions/fn_effectApply.sqf", True),
        ("missions/cti.Stratis/init.sqf", True),
        ("extension/src/lib.rs", True),
        ("src/cti_daemon/transport.py", True),
        ("src/cti_daemon/planner.py", False),
        ("tools/land.py", False),
        ("docs/adr/0064-mutation.md", False),
    ],
)
def test_the_filter_answers_the_incident_and_its_neighbours(path: str, *, expected: bool) -> None:
    """`85dfb1b`'s own file is the first row: 181 lines of it landed with no corpus."""
    assert bool(routing_policy.in_world_paths(_policy(), (path,))) is expected


# ------------------------------------------------------------- the corpus itself


def test_the_full_corpus_is_what_the_runner_itself_selects_with_no_filter(tmp_path: Path) -> None:
    """Derived from the runner rather than mirrored on faith (#157's rule, one level on).

    `CTI_TIER_STATE` is redirected because this drives a real tier script, and a unit
    test that forgets it takes the machine-wide locks under `$HOME/.arma-cti` for real
    (#132). `--list` takes none of them, but the tripwire in `test_client_lock.py` is
    about the habit rather than about this one path.
    """
    env = dict(os.environ)
    env["CTI_TIER_STATE"] = str(tmp_path / "state")
    listed = subprocess.run(  # noqa: S603 — this repo's own script, no arguments of ours
        [BASH, str(REGRESS), "--list"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert listed.returncode == 0, listed.stderr
    assert corpus_gate.full_corpus(REPO) == tuple(listed.stdout.split())


def test_a_tree_with_no_probes_has_an_empty_corpus_rather_than_raising(tmp_path: Path) -> None:
    assert corpus_gate.full_corpus(tmp_path) == ()


# --------------------------------------------------------- reading a pool record


def test_only_probes_with_a_verdict_row_count_as_measured() -> None:
    """A probe the merge left in `not_run` never started, so the pool did not measure it."""
    document = _pool(verdicts=[_row("alpha")], not_run=["beta"])
    assert corpus_gate.measured(document) == frozenset({"alpha"})


def test_the_pool_class_is_the_worse_of_what_the_record_says_and_what_its_rows_show() -> None:
    """A record below its own rows is a record disagreeing with itself (#199's rule)."""
    document = _pool(worst="pass", verdicts=[_row("alpha"), _row("beta", "assertion_failed")])
    assert corpus_gate.pool_class(document) == "assertion_failed"


def test_a_green_pool_reads_green() -> None:
    assert corpus_gate.pool_class(_pool()) == corpus_gate.PASS


def test_a_pool_that_stopped_early_is_raised_to_the_stop_class() -> None:
    """`pool_reads_green` reads one as not green for this reason; so does this."""
    document = _pool(stopped_early="machine fell under the memory floor")
    assert corpus_gate.pool_class(document) == corpus_gate.STOP_CLASS


def test_a_quarantined_probe_does_not_make_a_green_pool_red() -> None:
    """The class table's own severity: `flake_quarantine` runs, reports and does not gate."""
    document = _pool(verdicts=[_row("alpha"), _row("beta", "flake_quarantine")])
    assert corpus_gate.pool_class(document) == corpus_gate.PASS


def test_nobody_recording_the_tree_state_is_unknown_rather_than_clean(tmp_path: Path) -> None:
    assert (
        corpus_gate.recorded_dirty(_pool(verdicts=[_row("alpha", evidence=str(tmp_path))])) is None
    )


def test_a_probe_that_recorded_a_dirty_tree_is_read_as_dirty(tmp_path: Path) -> None:
    (tmp_path / "verdict.json").write_text(json.dumps({"git_dirty": True}), encoding="utf-8")
    document = _pool(verdicts=[_row("alpha", evidence=str(tmp_path))])
    assert corpus_gate.recorded_dirty(document) is True


def test_a_probe_that_recorded_a_clean_tree_is_read_as_clean(tmp_path: Path) -> None:
    (tmp_path / "verdict.json").write_text(json.dumps({"git_dirty": False}), encoding="utf-8")
    document = _pool(verdicts=[_row("alpha", evidence=str(tmp_path))])
    assert corpus_gate.recorded_dirty(document) is False


def test_a_directory_with_no_pool_record_is_not_a_result(tmp_path: Path) -> None:
    """ADR-0022: a run that died before its merge measured nothing anyone can interpret."""
    pool = tmp_path / "20260809T100000Z-pool"
    pool.mkdir()
    document, why = corpus_gate.read_record(pool)
    assert document is None
    assert "pool_unreadable" in why


def test_a_believable_pool_record_reads_back(tmp_path: Path) -> None:
    pool = tmp_path / "20260809T100000Z-pool"
    pool.mkdir()
    (pool / "pool.json").write_text(json.dumps(_pool()), encoding="utf-8")
    document, why = corpus_gate.read_record(pool)
    assert why == ""
    assert document is not None
    assert document["git_sha"] == "c0ffee1"


# ------------------------------------------------------------------ the judgement


def test_a_whole_green_run_over_this_landings_history_clears_it() -> None:
    assert corpus_gate.judge(_run(_pool()), ("alpha", "beta")) is None


def test_a_run_whose_commit_this_repository_has_never_seen_leaves_it_owed() -> None:
    """Nothing about that run can be checked here, so nothing about it clears anything."""
    finding = corpus_gate.judge(_run(_pool(), known=False), ("alpha", "beta"))
    assert finding.kind == corpus_gate.OWED
    assert "rejected=commit_not_in_this_repository" in _lines(finding)


def test_a_filtered_run_leaves_the_corpus_owed_and_names_what_was_missed() -> None:
    """`--issues` is provenance; CLAUDE.md is explicit it is never a gate for your own issue."""
    finding = corpus_gate.judge(_run(_pool(verdicts=[_row("alpha")])), ("alpha", "beta"))
    assert finding.kind == corpus_gate.OWED
    assert "rejected=partial_corpus" in _lines(finding)
    assert "missing=beta" in _lines(finding)


def test_a_probe_left_unrun_is_a_gap_even_though_the_pool_reads_green() -> None:
    document = _pool(verdicts=[_row("alpha")], not_run=["beta"])
    finding = corpus_gate.judge(_run(document), ("alpha", "beta"))
    assert finding.kind == corpus_gate.OWED
    assert "missing=beta" in _lines(finding)


def test_an_in_world_commit_landing_under_the_run_supersedes_it() -> None:
    """A rebase over somebody else's in-world commit is a tree the corpus has not seen."""
    finding = corpus_gate.judge(_run(_pool(), moved=("src/cti_daemon/port.py",)), ("alpha", "beta"))
    assert finding.kind == corpus_gate.OWED
    assert "rejected=superseded" in _lines(finding)
    assert "changed_since=src/cti_daemon/port.py" in _lines(finding)


def test_a_run_taken_over_a_dirty_tree_does_not_clear_the_sha_it_names() -> None:
    finding = corpus_gate.judge(_run(_pool(), dirty=True), ("alpha", "beta"))
    assert finding.kind == corpus_gate.OWED
    assert "rejected=tree_dirty_at_run_time" in _lines(finding)


def test_a_red_run_is_a_different_refusal_from_a_missing_one() -> None:
    """The second conversation: the corpus ran and the world disagreed with the change."""
    document = _pool(
        worst="assertion_failed", verdicts=[_row("alpha"), _row("beta", "assertion_failed")]
    )
    finding = corpus_gate.judge(_run(document), ("alpha", "beta"))
    assert finding.kind == corpus_gate.NOT_PASS
    assert "corpus_class=assertion_failed" in _lines(finding)


def test_a_stop_is_named_as_its_own_class_rather_than_as_a_red() -> None:
    """Why the refusal is not called `corpus_red`: `infra_unavailable` is not a result."""
    document = _pool(worst="infra_unavailable", verdicts=[_row("alpha"), _row("beta")])
    finding = corpus_gate.judge(_run(document), ("alpha", "beta"))
    assert finding.kind == corpus_gate.NOT_PASS
    assert "corpus_class=infra_unavailable" in _lines(finding)
    assert "failure-class table" in finding.action


def test_coverage_is_judged_before_the_verdict_so_a_stale_red_is_not_reported_as_one() -> None:
    document = _pool(worst="assertion_failed", verdicts=[_row("alpha", "assertion_failed")])
    finding = corpus_gate.judge(_run(document, known=False), ("alpha", "beta"))
    assert finding.kind == corpus_gate.OWED


def test_a_long_list_of_missing_probes_is_capped_but_says_how_many() -> None:
    corpus = tuple(f"probe{n}" for n in range(25))
    finding = corpus_gate.judge(_run(_pool(verdicts=[])), corpus)
    assert f"and={25 - corpus_gate.HOW_MANY_SHOWN} more" in _lines(finding)


# ------------------------------------------------------------------- what it says


def test_the_refusal_for_a_landing_with_no_run_names_the_paths_that_owe_it() -> None:
    finding = corpus_gate.owed_with_no_run(("src/cti_daemon/transport.py",))
    assert finding.kind == corpus_gate.OWED
    assert "in_world=src/cti_daemon/transport.py" in _lines(finding)
    assert "corpus_run=none" in _lines(finding)


def test_the_owed_refusal_says_who_can_clear_it_and_that_a_dispatch_cannot() -> None:
    """#302's design question (a): the orchestrator is the only party who can run it."""
    action = corpus_gate.owed_with_no_run(("addons/main/x.sqf",)).action
    assert "dispatched session cannot" in action
    assert "orchestrator" in action
    assert "just regress" in action
    assert "just verdict" in action


def test_a_check_that_could_not_run_says_so_rather_than_passing() -> None:
    finding = corpus_gate.unreadable(("policy=absent",))
    assert finding.kind == corpus_gate.UNREADABLE
    assert "#41" in finding.action


def test_a_landing_that_owes_nothing_says_that_rather_than_saying_cleared() -> None:
    assert "not_owed" in corpus_gate.Outcome(None).line(None)


def test_a_cleared_landing_names_the_run_that_cleared_it() -> None:
    outcome = corpus_gate.Outcome(None, ("addons/main/x.sqf",))
    assert "cleared" in outcome.line(Path("/runs/p"))
    assert "/runs/p" in outcome.line(Path("/runs/p"))
