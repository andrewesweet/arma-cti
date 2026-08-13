"""The landing protocol's refusal ladder, and the recipe over a real git repository (#213).

Two layers, both in the no-Arma tier, for `test_worktree.py`'s reason: the
ladders are pure functions over the strings git prints, so every refusal class
is asserted by its own name and its own words (ADR-0049, and #83's precedent
that a classification bug should be a red `just unit` rather than a discovery).

Under them sit end-to-end runs against real `git` — a bare repository standing
in for `origin`, a main checkout, and a linked worktree — because the parsers'
subject is git's actual output, and because the claims worth making here are
about what does and does not reach the remote.

The heaviest of those: **the gate is inside the protocol, not beside it.** The
gate is injected, so the tests can see when it ran and what it saw, and they
assert that it ran *after* the rebase (it is handed a tree already carrying the
sibling's commit) and that a red one leaves `origin/main` exactly where it was.
Nothing here ever runs `just land` against the real remote — #213's own gate
note: test the ladder, not the network.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import REPO, load_tool

# `land` imports `worktree` as a sibling script, so the sibling is loaded first
# and registered under its own name for that import to find.
worktree = load_tool("worktree")
check_conflict_markers = load_tool("check_conflict_markers")
pool_merge = load_tool("pool_merge")
pool_comment = load_tool("pool_comment")
corpus_gate = load_tool("corpus_gate")
land = load_tool("land")
routing_policy = load_tool("routing_policy")

POLICY = REPO / routing_policy.POLICY_RELATIVE

# The fixture repository's own corpus: two probes, so "the whole corpus" is a claim a
# pool record can fail to make rather than a vacuous one.
FIXTURE_PROBES = ("alpha", "beta")

_CLEAN = worktree.Preflight((), ())
_HERE = Path("/home/a/repo/.claude/worktrees/issue-213")
_MAIN = Path("/home/a/repo")


# ANN401: a `tools/` script is loaded by path, so its `Refusal` is not a type any
# annotation here could name — `Any` is what the module object actually hands back.
def _kind(refusal: Any) -> str:  # noqa: ANN401
    return refusal.kind


def _text(refusal: Any) -> str:  # noqa: ANN401
    return "\n".join(refusal.lines())


# ------------------------------------------------------- the pre-flight rungs


def test_a_clean_tree_not_mid_rebase_passes_the_preflight() -> None:
    assert land.classify_tree(_HERE, _CLEAN, rebasing=False) is None


def test_uncommitted_tracked_changes_refuse_dirty_tree_and_name_the_files() -> None:
    status = worktree.Preflight((" M tools/land.py",), ())
    refusal = land.classify_tree(_HERE, status, rebasing=False)
    assert _kind(refusal) == "dirty_tree"
    assert "tracked= M tools/land.py" in _text(refusal)


def test_untracked_files_refuse_dirty_tree_and_say_never_reset() -> None:
    """#105's condition: a foreign file and your own look identical in `git status`."""
    status = worktree.Preflight((), ("?? spike/scratch.sqf",))
    refusal = land.classify_tree(_HERE, status, rebasing=False)
    assert _kind(refusal) == "dirty_tree"
    assert "untracked=?? spike/scratch.sqf" in _text(refusal)
    assert "never reset" in _text(refusal)
    assert "#105" in _text(refusal)


def test_the_file_list_is_capped_but_says_how_many_it_did_not_show() -> None:
    status = worktree.Preflight(tuple(f" M f{n}" for n in range(25)), ())
    refusal = land.classify_tree(_HERE, status, rebasing=False)
    assert "and=15 more" in _text(refusal)


def test_a_tree_already_mid_rebase_refuses_rather_than_reading_as_dirty() -> None:
    refusal = land.classify_tree(_HERE, _CLEAN, rebasing=True)
    assert _kind(refusal) == "rebase_conflict"
    assert "git rebase --continue" in _text(refusal)
    assert "git rebase --abort" in _text(refusal)


# ------------------------------------------------------------ nothing to land


def test_level_with_origin_and_a_current_main_checkout_is_nothing_to_land() -> None:
    refusal = land.classify_nothing_to_land(_HERE, ahead=0, main_behind=0)
    assert _kind(refusal) == "nothing_to_land"
    assert "check you committed it" in _text(refusal)


def test_commits_to_push_are_not_nothing_to_land() -> None:
    assert land.classify_nothing_to_land(_HERE, ahead=3, main_behind=0) is None


def test_nothing_to_push_but_a_stale_main_checkout_proceeds_to_the_merge() -> None:
    """The re-run after `merge_blocked_by_sandbox`: the push is done, the merge is not."""
    assert land.classify_nothing_to_land(_HERE, ahead=0, main_behind=2) is None


def test_an_unreadable_main_checkout_is_not_read_as_nothing_to_land() -> None:
    assert land.classify_nothing_to_land(_HERE, ahead=0, main_behind=None) is None


# ------------------------------------------------------------------- rebasing


def test_a_clean_rebase_does_not_refuse() -> None:
    assert land.classify_rebase(_HERE, 0, (), "") is None


def test_a_stopped_rebase_names_the_conflicts_and_both_ways_out() -> None:
    refusal = land.classify_rebase(_HERE, 1, ("CHANGELOG.md",), "CONFLICT (content)")
    assert _kind(refusal) == "rebase_conflict"
    assert "conflict=CHANGELOG.md" in _text(refusal)
    assert "git rebase --continue" in _text(refusal)
    assert "git rebase --abort" in _text(refusal)


def test_a_failed_rebase_with_nothing_conflicted_is_git_failed_not_a_conflict() -> None:
    refusal = land.classify_rebase(_HERE, 128, (), "fatal: invalid upstream")
    assert _kind(refusal) == "git_failed"
    assert "fatal: invalid upstream" in _text(refusal)


# ------------------------------------------------------------- conflict markers


def test_a_tree_with_no_conflict_markers_does_not_refuse() -> None:
    assert land.classify_conflict_markers(_HERE, []) is None


def test_conflict_markers_refuse_by_name_and_name_every_one() -> None:
    findings = [
        check_conflict_markers.Finding("CHANGELOG.md", 812, "<"),
        check_conflict_markers.Finding("CHANGELOG.md", 815, "|"),
    ]
    refusal = land.classify_conflict_markers(_HERE, findings)
    assert _kind(refusal) == "conflict_markers"
    assert "CHANGELOG.md:812" in _text(refusal)
    assert "CHANGELOG.md:815" in _text(refusal)
    assert "2b4f99b" in _text(refusal)


def test_a_long_list_of_markers_is_capped_and_says_how_many_it_did_not_show() -> None:
    findings = [check_conflict_markers.Finding("CHANGELOG.md", n, "<") for n in range(1, 15)]
    refusal = land.classify_conflict_markers(_HERE, findings)
    assert f"and={14 - land.HOW_MANY_SHOWN} more" in _text(refusal)


# ----------------------------------------------------------------- the gate


def test_a_green_gate_does_not_refuse() -> None:
    assert land.classify_gate(_HERE, land.GateResult(0, "")) is None


def test_a_red_gate_refuses_gate_red_and_points_at_the_gates_own_output() -> None:
    refusal = land.classify_gate(_HERE, land.GateResult(1, ""))
    assert _kind(refusal) == "gate_red"
    assert "Nothing was pushed" in _text(refusal)


def test_a_gate_that_never_finished_is_gate_blocked_not_gate_red() -> None:
    """#41: a check that could not run is not a check that passed — nor is it a red one."""
    refusal = land.classify_gate(_HERE, land.GateResult(None, "killed at the 1800s bound"))
    assert _kind(refusal) == "gate_blocked"
    assert "killed at the 1800s bound" in _text(refusal)
    assert "#41" in _text(refusal)


# ------------------------------------------------------ routing policy gate


def _policy_read() -> Any:  # noqa: ANN401 — load_tool returns a runtime module type
    return routing_policy.read_policy(POLICY)


def _seed(prefix: str) -> str:
    return f"{prefix}seed.txt" if prefix.endswith("/") else prefix


def test_every_path_backed_class_is_exercised_beyond_the_first_row() -> None:
    read = _policy_read()
    assert read.policy is not None
    path_backed = [rule for rule in read.policy.rules if rule.landing_path_prefixes]
    assert [rule.id for rule in path_backed] == [1, 2, 3, 5, 6, 7]
    for rule in path_backed:
        match = routing_policy.landing_match(rule, (_seed(rule.landing_path_prefixes[0]),))
        assert match is not None, rule.name
        assert match.rule.id == rule.id


def test_the_181_shape_stays_declaration_only_because_no_diff_path_can_prove_it() -> None:
    read = _policy_read()
    assert read.policy is not None
    diagnosis = read.policy.rules[3]
    assert diagnosis.id == 4
    assert diagnosis.landing_path_prefixes == ()
    assert routing_policy.landing_match(diagnosis, ("tools/anything.py",)) is None


def test_a_foreign_keep_class_diff_is_an_enforcing_named_refusal() -> None:
    refusal = land.classify_routing(_policy_read(), ("addons/main/ui.sqf",), "zai")
    assert _kind(refusal) == "routing_policy_gate"
    assert "check=enforcing actual diff" in _text(refusal)
    assert "routing_class=5:in_world_landings" in _text(refusal)
    assert "full `just regress` corpus" in _text(refusal)


def test_a_non_class_diff_clears_the_routing_gate() -> None:
    assert land.classify_routing(_policy_read(), ("tools/worker.py",), "zai") is None


def test_an_unreadable_diff_refuses_instead_of_passing() -> None:
    refusal = land.classify_routing(_policy_read(), None, "zai", "fatal: bad revision")
    assert _kind(refusal) == "routing_policy_diff_unreadable"
    assert "check=enforcing actual diff" in _text(refusal)
    assert "#41" in _text(refusal)


def test_an_unreadable_policy_refuses_a_foreign_landing() -> None:
    read = routing_policy.ReadResult(None, "policy is absent")
    refusal = land.classify_routing(read, ("tools/worker.py",), "zai")
    assert _kind(refusal) == "routing_policy_gate_unreadable"


def test_native_landings_do_not_need_the_foreign_routing_gate() -> None:
    read = routing_policy.ReadResult(None, "policy is absent")
    assert land.classify_routing(read, None, "claude-native") is None


# ------------------------------------------------------------------ the corpus rung


def test_a_corpus_rung_with_nothing_to_say_does_not_refuse() -> None:
    assert land.classify_corpus(None) is None


@pytest.mark.parametrize("kind", [corpus_gate.OWED, corpus_gate.NOT_PASS, corpus_gate.UNREADABLE])
def test_every_corpus_finding_becomes_a_refusal_in_this_recipes_own_vocabulary(kind: str) -> None:
    refusal = land.classify_corpus(corpus_gate.Finding(kind, ("evidence=here",)))
    assert _kind(refusal) == kind
    assert "evidence=here" in _text(refusal)
    assert _text(refusal).splitlines()[-1].startswith("action=")


def test_there_is_no_flag_that_skips_the_corpus_check() -> None:
    """#302: `--corpus` names evidence and is verified; nothing excuses the check."""
    for bypass in ("--no-corpus", "--skip-corpus", "--corpus-owed", "--force-corpus"):
        with pytest.raises(SystemExit):
            land.parse_args([bypass])


def test_the_corpus_flag_takes_a_pool_path_and_defaults_to_naming_nothing() -> None:
    assert land.parse_args([]).corpus is None
    assert land.parse_args(["--corpus", "/runs/p"]).corpus == Path("/runs/p")


# ------------------------------------------------------------------- the push


def test_the_push_refspec_is_head_colon_main_and_nothing_parameterises_it() -> None:
    """The `git push origin main` trap, refused by construction rather than by memory."""
    assert land.push_argv() == ["git", "push", "origin", "HEAD:main"]


def test_no_argument_can_turn_the_push_into_the_trap() -> None:
    """There is no remote, refspec or force flag on the surface to reach for."""
    for trap in ("--force", "--remote", "origin", "main", "--refspec"):
        with pytest.raises(SystemExit):
            land.parse_args([trap])


def test_there_is_no_flag_that_skips_the_gate() -> None:
    """#213 criterion 2: a `--no-gate` would be a gate bypass wearing a wrapper."""
    for bypass in ("--no-gate", "--skip-gate", "--no-verify"):
        with pytest.raises(SystemExit):
            land.parse_args([bypass])


@pytest.mark.parametrize(
    "stderr",
    [
        "! [rejected]        HEAD -> main (non-fast-forward)",
        "hint: Updates were rejected because the remote contains work... fetch first",
        "! [rejected] main -> main (stale info)",
    ],
)
def test_a_lost_race_is_not_fast_forward_and_says_to_run_land_again(stderr: str) -> None:
    refusal = land.classify_push(1, stderr)
    assert _kind(refusal) == "not_fast_forward"
    assert "just land" in _text(refusal)


def test_any_other_push_failure_is_git_failed_with_gits_own_words() -> None:
    refusal = land.classify_push(128, "fatal: could not read Username for 'https://github.com'")
    assert _kind(refusal) == "git_failed"
    assert "could not read Username" in _text(refusal)


def test_a_successful_push_does_not_refuse() -> None:
    assert land.classify_push(0, "") is None


# ------------------------------------------------------------------ the merge


def test_the_merge_argv_names_the_main_checkout_it_was_given() -> None:
    assert land.merge_argv(_MAIN) == [
        "git",
        "-C",
        "/home/a/repo",
        "merge",
        "--ff-only",
        "origin/main",
    ]


def test_a_merge_that_could_not_run_is_blocked_by_sandbox_and_names_the_command() -> None:
    """#213 criterion 4, and CLAUDE.md's 'never skip it silently' with a mechanism at last."""
    refusal = land.classify_merge(_MAIN, "abc1234", None, "PermissionError: sandbox denied")
    assert _kind(refusal) == "merge_blocked_by_sandbox"
    assert "merge_command=git -C /home/a/repo merge --ff-only origin/main" in _text(refusal)
    assert "pushed=abc1234 origin/main" in _text(refusal)
    assert "THE WORK IS LANDED" in _text(refusal)


def test_a_failing_merge_command_is_blocked_by_sandbox_with_its_stderr_kept() -> None:
    refusal = land.classify_merge(_MAIN, "abc1234", 1, "operation not permitted")
    assert _kind(refusal) == "merge_blocked_by_sandbox"
    assert "operation not permitted" in _text(refusal)


def test_a_diverged_main_checkout_is_named_apart_from_a_blocked_one() -> None:
    """Different required response: reconcile by hand, not 'run this command'."""
    refusal = land.classify_merge(
        _MAIN, "abc1234", 1, "fatal: Not possible to fast-forward, aborting."
    )
    assert _kind(refusal) == "merge_not_fast_forward"
    assert "commits of its own" in _text(refusal)


def test_a_completed_merge_does_not_refuse() -> None:
    assert land.classify_merge(_MAIN, "abc1234", 0, "") is None


def test_the_gate_exempts_the_lane_the_policy_names_rather_than_a_second_literal() -> None:
    """Claim 6: one home for 'which lane the routing gate never judges'.

    The policy's `claude_lane` is the authority, and the constant is what remains when
    the policy could not be read — which is also the order the gate needs, since the
    Claude lane must not be refused for an unreadable policy it is the remedy for.

    **Driven against a policy that names a different lane**, because the shipped policy's
    `claude_lane` and `land.CLAUDE_LANE` are the same string: every assertion phrased in
    terms of both at once passes whichever one the code actually reads, which is how
    round 1's version of this test went green on the pre-fix code (review round 2
    claim 2). Renaming the policy's lane separates them, so the constant-only form reds
    on the first assertion and the union form reds on the second.
    """
    shipped = routing_policy.parse_policy(POLICY.read_text(encoding="utf-8"))
    renamed = shipped._replace(claude_lane="claude-anthropic")
    read = routing_policy.ReadResult(renamed)
    gated = ("addons/main/ui.sqf",)

    # The policy's name is exempt, and it is not the constant.
    assert renamed.claude_lane != land.CLAUDE_LANE
    assert land.classify_routing(read, gated, renamed.claude_lane) is None
    # The constant is *replaced*, not joined: a readable policy that does not name it
    # leaves it judged like any other lane.
    assert _kind(land.classify_routing(read, gated, land.CLAUDE_LANE)) == "routing_policy_gate"
    assert land.classify_routing(read, gated, "zai") is not None
    # With no policy to read, the constant is what is left — and the Claude lane must not
    # be refused for an unreadable policy it is the remedy for.
    unreadable = routing_policy.ReadResult(None, "could not be read")
    assert land.classify_routing(unreadable, gated, land.CLAUDE_LANE) is None
    assert (
        _kind(land.classify_routing(unreadable, gated, "zai")) == "routing_policy_gate_unreadable"
    )


# ---------------------------------------------------------------- end to end


def _git(*args: str, cwd: Path) -> str:
    # S603/S607: fixed literals and tmp_path-derived paths, and `git` off PATH on
    # purpose — the same reasoning as the tool under test.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _commit(path: Path, name: str, body: str) -> None:
    target = path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _git("add", name, cwd=path)
    _git("commit", "-m", f"feat: {name}", cwd=path)


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build a bare `origin`, a main checkout on `main`, and one linked worktree.

    The arrangement a landing actually runs in, which is the only arrangement in
    which the ff-only merge into a *second* checkout is a real step at all.
    """
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "--initial-branch=main", str(origin), cwd=tmp_path)
    main = tmp_path / "repo"
    _git("clone", str(origin), str(main), cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=main)
    _git("config", "user.name", "T", cwd=main)
    _commit(main, "README.md", "one\n")
    _commit(
        main,
        routing_policy.POLICY_RELATIVE.as_posix(),
        POLICY.read_text(encoding="utf-8"),
    )
    # A corpus of two, so "the whole corpus" is a claim a pool record can fail to make.
    for probe in FIXTURE_PROBES:
        _commit(main, f"spike/probes/{probe}.sqf", f"// probe: {probe}\n")
    _git("push", "origin", "main", cwd=main)

    here = main / ".claude" / "worktrees" / "issue-213"
    _git("worktree", "add", str(here), "origin/main", "--detach", cwd=main)
    return origin, main, here


def _tip(origin: Path) -> str:
    return _git("rev-parse", "main", cwd=origin).strip()


class _Gate:
    """A gate that records what it saw, so the tests can assert when it ran."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.calls: list[str] = []

    def __call__(self, path: Path) -> object:
        self.calls.append(_git("log", "-1", "--format=%s", cwd=path).strip())
        return land.GateResult(self.code, "")


def test_a_landing_pushes_the_work_and_fast_forwards_the_main_checkout(
    repo: tuple[Path, Path, Path],
) -> None:
    origin, main, here = repo
    _commit(here, "feature.txt", "work\n")
    gate = _Gate()

    report = land.land(main, here, gate=gate)

    assert report.code == 0
    assert report.lines[0] == "ok=landed"
    assert _tip(origin) == _git("rev-parse", "HEAD", cwd=here).strip()
    assert _git("rev-parse", "main", cwd=main).strip() == _tip(origin)
    assert "\n".join(report.lines).count("merge=fast-forwarded") == 1


def test_the_gate_runs_on_the_rebased_tree_not_the_tree_as_it_was(
    repo: tuple[Path, Path, Path],
) -> None:
    """The whole of the re-gate-on-movement answer: it runs, and it runs after the rebase."""
    _origin, main, here = repo
    _commit(main, "sibling.txt", "landed first\n")
    _git("push", "origin", "main", cwd=main)
    _commit(here, "feature.txt", "work\n")
    gate = _Gate()

    report = land.land(main, here, gate=gate)

    assert report.code == 0
    assert len(gate.calls) == 1
    # The tree the gate saw carries our commit replayed on top of the sibling's.
    assert gate.calls == ["feat: feature.txt"]
    assert "sibling.txt" in _git("show", "--name-only", "--format=", "HEAD~1", cwd=here)
    assert "rebase=replayed onto 1 new commits" in report.lines


def test_a_red_gate_leaves_origin_exactly_where_it_was(
    repo: tuple[Path, Path, Path],
) -> None:
    origin, main, here = repo
    before = _tip(origin)
    _commit(here, "feature.txt", "work\n")

    report = land.land(main, here, gate=_Gate(code=1))

    assert report.code == 1
    assert report.lines[0] == "refusal=gate_red"
    assert _tip(origin) == before


def test_a_foreign_keep_class_diff_refuses_before_the_normal_gate_or_push(
    repo: tuple[Path, Path, Path],
) -> None:
    origin, _main, here = repo
    before = _tip(origin)
    _commit(here, "addons/main/ui.sqf", "in-world work\n")
    gate = _Gate()

    report = land.land(_main, here, gate=gate, lane="zai")

    assert report.code == 1
    assert report.lines[0] == "refusal=routing_policy_gate"
    assert "routing_class=5:in_world_landings" in report.lines
    assert gate.calls == []
    assert _tip(origin) == before


def test_a_foreign_diff_outside_every_class_lands_unimpeded(
    repo: tuple[Path, Path, Path],
) -> None:
    origin, main, here = repo
    _commit(here, "tools/worker.py", "eligible work\n")
    gate = _Gate()

    report = land.land(main, here, gate=gate, lane="zai")

    assert report.code == 0
    assert gate.calls == ["feat: tools/worker.py"]
    assert _tip(origin) == _git("rev-parse", "HEAD", cwd=here).strip()


def test_a_dirty_tree_refuses_before_the_gate_or_the_remote_is_touched(
    repo: tuple[Path, Path, Path],
) -> None:
    origin, main, here = repo
    before = _tip(origin)
    _commit(here, "feature.txt", "work\n")
    (here / "foreign.txt").write_text("someone else's\n", encoding="utf-8")
    gate = _Gate()

    report = land.land(main, here, gate=gate)

    assert report.code == 1
    assert report.lines[0] == "refusal=dirty_tree"
    assert gate.calls == []
    assert _tip(origin) == before
    # Nothing was tidied: the foreign file is evidence, and it is still there.
    assert (here / "foreign.txt").exists()


def test_a_worktree_with_nothing_to_land_refuses_rather_than_reporting_success(
    repo: tuple[Path, Path, Path],
) -> None:
    _origin, main, here = repo
    gate = _Gate()

    report = land.land(main, here, gate=gate)

    assert report.code == 1
    assert report.lines[0] == "refusal=nothing_to_land"
    assert gate.calls == []


def test_a_rerun_after_a_blocked_merge_finishes_the_merge_and_pushes_nothing(
    repo: tuple[Path, Path, Path],
) -> None:
    """The idempotent path: the work is already on origin/main, the main checkout is stale."""
    origin, main, here = repo
    _commit(here, "feature.txt", "work\n")
    _git("push", "origin", "HEAD:main", cwd=here)
    landed = _tip(origin)
    gate = _Gate()

    report = land.land(main, here, gate=gate)

    assert report.code == 0
    assert gate.calls == []
    assert "push=not_needed reason=already_on_origin/main" in report.lines
    assert _git("rev-parse", "main", cwd=main).strip() == landed


def test_a_diverged_main_checkout_reports_the_work_landed_and_the_merge_owed(
    repo: tuple[Path, Path, Path],
) -> None:
    origin, main, here = repo
    _commit(main, "local-only.txt", "never pushed\n")
    _commit(here, "feature.txt", "work\n")

    report = land.land(main, here, gate=_Gate())

    assert report.code == land.EXIT_LANDED_INCOMPLETE
    assert report.lines[0] == "refusal=merge_not_fast_forward"
    assert _tip(origin) == _git("rev-parse", "HEAD", cwd=here).strip()
    assert any(line.startswith("merge_command=") for line in report.lines)


def test_a_conflicting_rebase_stops_before_the_gate_and_leaves_the_rebase_in_progress(
    repo: tuple[Path, Path, Path],
) -> None:
    origin, main, here = repo
    _commit(main, "CHANGELOG.md", "theirs\n")
    _git("push", "origin", "main", cwd=main)
    before = _tip(origin)
    _commit(here, "CHANGELOG.md", "ours\n")
    gate = _Gate()

    report = land.land(main, here, gate=gate)

    assert report.code == 1
    assert report.lines[0] == "refusal=rebase_conflict"
    assert "conflict=CHANGELOG.md" in report.lines
    assert gate.calls == []
    assert _tip(origin) == before
    assert land.rebase_in_progress(here)


def test_a_committed_conflict_marker_refuses_before_the_gate_and_pushes_nothing(
    repo: tuple[Path, Path, Path],
) -> None:
    """#231's defect, at the rung that now stands in front of it.

    The marker is committed rather than left in the working tree, because that
    is what happened: 2b4f99b *landed* with one, and the landing after it
    resolved against the corrupted file. The gate never runs and `origin/main`
    never moves.
    """
    origin, main, here = repo
    before = _tip(origin)
    marker = "|" * 7
    _commit(here, "CHANGELOG.md", f"### Added\n\n{marker} parent of 7bea7f6\n- an entry.\n")
    gate = _Gate()

    report = land.land(main, here, gate=gate)

    assert report.code == 1
    assert report.lines[0] == "refusal=conflict_markers"
    assert any("CHANGELOG.md:3" in line for line in report.lines)
    assert gate.calls == []
    assert _tip(origin) == before


def test_a_marker_inherited_from_origin_refuses_this_landing_too(
    repo: tuple[Path, Path, Path],
) -> None:
    """The base-poisoning half: a clean commit must not ride out on a poisoned base.

    #231's mechanism is that the *next* resolution inherits the damage, so the
    rung judges the rebased tree — the tree that would be pushed — and the only
    landing it lets through is one that removes the marker.
    """
    origin, main, here = repo
    marker = "<" * 7
    _commit(main, "CHANGELOG.md", f"{marker} HEAD\n- theirs.\n")
    _git("push", "origin", "main", cwd=main)
    before = _tip(origin)
    _commit(here, "feature.txt", "work\n")
    gate = _Gate()

    report = land.land(main, here, gate=gate)

    assert report.code == 1
    assert report.lines[0] == "refusal=conflict_markers"
    assert gate.calls == []
    assert _tip(origin) == before


def test_a_dry_run_runs_nothing_and_says_so(repo: tuple[Path, Path, Path]) -> None:
    origin, main, here = repo
    before = _tip(origin)
    _commit(here, "feature.txt", "work\n")
    gate = _Gate()

    report = land.land(main, here, gate=gate, dry_run=True)

    assert report.code == 0
    assert "landed=no" in report.lines
    assert gate.calls == []
    assert _tip(origin) == before
    assert any(line == "would_run=git push origin HEAD:main" for line in report.lines)
    # Whatever it could not consult, it names.
    assert any(line.startswith("not_checked=") for line in report.lines)


# ANN401: `land` is loaded by path, so its `Report` is not a type an annotation here names.
def _pushes_unqualified(report: Any) -> bool:  # noqa: ANN401
    """Whether this plan presents the push as a step it would take, with no caveat."""
    return any(line == "would_run=git push origin HEAD:main" for line in report.lines)


# The qualification both routing verdicts carry, spelled out here so the assertions on it
# fail on a rewording rather than passing on its absence (round 2 claim 9).
_CAVEAT = "(this branch's own diff, merge-base relative)"


def test_a_dry_run_on_a_gated_surface_from_a_foreign_lane_does_not_plan_to_push(
    repo: tuple[Path, Path, Path],
) -> None:
    """#344: the dry run consulted no routing rung, so it planned a push the gate refuses.

    The push step is asserted behaviourally, through `_pushes_unqualified`. The routing
    assertions are **not** wording-independent and are not meant to be: the emitted line
    is this rung's contract with its reader, so renaming `would_refuse` reds these on
    purpose. Verified by running it — see the round's own note on #344; the claim that a
    rewording stays green was wrong about these three assertions (review round 1 claim 8).
    """
    origin, main, here = repo
    before = _tip(origin)
    _commit(here, "addons/main/ui.sqf", "in-world work\n")

    report = land.land(main, here, gate=_Gate(), dry_run=True, lane="zai")

    assert report.code == land.EXIT_REFUSED
    assert not _pushes_unqualified(report)
    assert any("routing=would_refuse" in line for line in report.lines)
    assert any("routing_policy_gate" in line for line in report.lines)
    assert any("routing_class=5:in_world_landings" in line for line in report.lines)
    # The caveat, on the refusal and not only on the pass — that was round 1 claim 5's
    # whole substance and nothing pinned it, so stripping it stayed green (round 2
    # claim 9).
    assert any(line.endswith(_CAVEAT) for line in report.lines if "routing=would_refuse" in line)
    # And the remedy without the clause about a push that was never in prospect.
    action = next(line for line in report.lines if line.startswith("action="))
    assert not action.endswith("Nothing was pushed.")
    assert _tip(origin) == before


def test_a_dry_run_on_an_ungated_surface_from_a_foreign_lane_still_plans_the_push(
    repo: tuple[Path, Path, Path],
) -> None:
    """The other half: the rung ran and cleared, and the plan says which it was."""
    _origin, main, here = repo
    _commit(here, "tools/worker.py", "eligible work\n")

    report = land.land(main, here, gate=_Gate(), dry_run=True, lane="zai")

    assert report.code == 0
    assert _pushes_unqualified(report)
    assert f"routing=would_pass lane=zai {_CAVEAT}" in report.lines


def test_a_sibling_landing_a_gated_path_does_not_make_this_ungated_diff_refuse(
    repo: tuple[Path, Path, Path],
) -> None:
    """The pre-rebase superset, which turned #344's fix the other way round.

    `git diff A..B` is a symmetric tree comparison, so before the rebase — and `land`
    has already fetched by then — it reported this branch's paths *and* every path the
    incoming commits touched. A sibling landing an ADR while a `zai` seat worked on one
    ungated doc was enough to make the dry run refuse work the real landing accepts, and
    hand it back. `origin/main...HEAD` is merge-base relative, so it answers with this
    branch's own paths and the sibling's ADR is not among them.
    """
    _origin, main, here = repo
    _commit(here, "docs/telemetry-ledger.md", "ungated work\n")
    _commit(main, "docs/adr/0099-a-sibling-decision.md", "# ADR\n")
    _git("push", "origin", "main", cwd=main)

    report = land.land(main, here, gate=_Gate(), dry_run=True, lane="zai")

    assert report.code == 0
    assert _pushes_unqualified(report)
    assert f"routing=would_pass lane=zai {_CAVEAT}" in report.lines


def test_a_dry_run_with_nothing_to_push_mirrors_the_landing_and_consults_no_gate(
    repo: tuple[Path, Path, Path],
) -> None:
    """The re-run after a blocked merge, where the real landing skips the gate entirely.

    `ahead == 0` with a stale main checkout reaches `_push`'s not-needed branch without
    ever entering `_rebase_and_gate`, so routing is never consulted and the merge is the
    one outstanding step. A plan that classified routing here would refuse that merge for
    a rung that does not run — which is what it did (review round 1 claim 2).
    """
    _origin, main, here = repo
    _commit(here, "addons/main/ui.sqf", "in-world work\n")
    _git("push", "origin", "HEAD:main", cwd=here)

    report = land.land(main, here, gate=_Gate(), dry_run=True, lane="zai")

    assert report.code == 0
    assert "routing=not_consulted reason=nothing_to_push" in report.lines
    assert "corpus=not_consulted reason=nothing_to_push" in report.lines
    assert not any(line.startswith("would_not_run=") for line in report.lines)
    assert any(
        line.startswith("would_run=git -C ") and "merge --ff-only" in line for line in report.lines
    )
    # What it did not check is the merge's, not the gate's: the gate does not run here.
    unchecked = [line for line in report.lines if line.startswith("not_checked=")]
    assert unchecked == [f"not_checked={land.NOT_CHECKED_MERGE_ONLY}"]


def test_a_native_dry_run_says_the_routing_rung_does_not_apply_to_it(
    repo: tuple[Path, Path, Path],
) -> None:
    """A gated path on `claude-native` is not misrouted, and the plan must not imply it is."""
    _origin, main, here = repo
    _commit(here, "addons/main/ui.sqf", "in-world work\n")

    report = land.land(main, here, gate=_Gate(), dry_run=True)

    assert _pushes_unqualified(report)
    assert "routing=not_applicable lane=claude-native" in report.lines


def test_a_refusing_dry_run_still_prints_its_plan_on_stdout(
    repo: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`main` routes on the exit code, and a refusing dry run's code is now non-zero.

    Left alone that emptied stdout exactly when the plan had the most to say, so the
    foreign-lane seat #344 was filed for got a bare `recipe … failed` banner — the shape
    this project trains agents to read as a harness failure rather than a verdict
    (review round 2 claim 3).
    """
    _origin, _main, here = repo
    _commit(here, "addons/main/ui.sqf", "in-world work\n")
    monkeypatch.chdir(here)
    monkeypatch.setenv("CTI_DISPATCH_LANE", "zai")

    code = land.main(["--dry-run"])

    captured = capsys.readouterr()
    assert code == land.EXIT_REFUSED
    assert any("routing=would_refuse" in line for line in captured.out.splitlines())
    assert captured.err == ""


# ------------------------------------------ the corpus rung, against a real repository


def _write_pool(
    at: Path,
    *,
    sha: str,
    probes: tuple[str, ...] = FIXTURE_PROBES,
    worst: str = "pass",
    class_: str = "pass",
) -> Path:
    """Write the pool record a finished `just regress` leaves, and return its directory."""
    pool = at / "20260809T101500Z-pool"
    pool.mkdir(parents=True)
    document = {
        "started_at": "20260809T101500Z",
        "git_sha": sha,
        "slots": [0, 1, 2],
        "worst_class": worst,
        "wall_secs": 900,
        "stopped_early": "",
        "not_run": [],
        "verdicts": [
            {"probe": probe, "class": class_, "slot": "0", "elapsed_secs": 12, "evidence": ""}
            for probe in probes
        ],
    }
    (pool / "pool.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    return pool


def test_an_in_world_landing_with_no_corpus_run_refuses_by_name_and_pushes_nothing(
    repo: tuple[Path, Path, Path],
) -> None:
    """#302's incident, at the rung that now stands in front of it."""
    origin, main, here = repo
    before = _tip(origin)
    _commit(here, "src/cti_daemon/transport.py", "181 changed lines\n")
    gate = _Gate()

    report = land.land(main, here, gate=gate)

    assert report.code == 1
    assert report.lines[0] == "refusal=corpus_owed"
    assert "in_world=src/cti_daemon/transport.py" in report.lines
    assert _tip(origin) == before
    # The cheap gate ran first: nobody is sent to a slot of the Arma tier over a red ruff.
    assert gate.calls == ["feat: src/cti_daemon/transport.py"]


def test_a_landing_that_reaches_no_in_world_surface_does_not_owe_the_corpus(
    repo: tuple[Path, Path, Path],
) -> None:
    origin, main, here = repo
    _commit(here, "tools/worker.py", "tooling\n")

    report = land.land(main, here, gate=_Gate())

    assert report.code == 0
    assert "corpus=not_owed reason=no_in_world_path" in report.lines
    assert _tip(origin) == _git("rev-parse", "HEAD", cwd=here).strip()


def test_a_whole_green_run_over_this_head_clears_the_in_world_landing(
    repo: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    origin, main, here = repo
    _commit(here, "addons/main/functions/fn_effectApply.sqf", "in-world work\n")
    pool = _write_pool(tmp_path, sha=_git("rev-parse", "HEAD", cwd=here).strip())

    report = land.land(main, here, gate=_Gate(), corpus=pool)

    assert report.code == 0
    assert any(line.startswith("corpus=cleared") for line in report.lines)
    assert _tip(origin) == _git("rev-parse", "HEAD", cwd=here).strip()


def test_a_run_naming_a_commit_this_repository_has_never_seen_leaves_it_owed(
    repo: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    """Naming a convenient green pool is not a bypass: the rung checks whose tree it measured."""
    origin, main, here = repo
    before = _tip(origin)
    _commit(here, "addons/main/functions/fn_effectApply.sqf", "in-world work\n")
    pool = _write_pool(tmp_path, sha="0" * 40)

    report = land.land(main, here, gate=_Gate(), corpus=pool)

    assert report.code == 1
    assert report.lines[0] == "refusal=corpus_owed"
    assert "rejected=commit_not_in_this_repository" in report.lines
    assert _tip(origin) == before


def test_a_rebase_over_a_sibling_that_touched_nothing_in_world_keeps_the_run_valid(
    repo: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    """Why coverage is a tree comparison and not ancestry.

    `just land` rebases, so the commit a corpus ran over is orphaned by every landing
    that follows a sibling's. An ancestry rule would make this gate unclearable in
    ordinary traffic; what has to hold is that the world measured is the world pushed.
    """
    origin, main, here = repo
    _commit(here, "addons/main/functions/fn_effectApply.sqf", "in-world work\n")
    pool = _write_pool(tmp_path, sha=_git("rev-parse", "HEAD", cwd=here).strip())
    _commit(main, "tools/sibling.py", "somebody else's tooling\n")
    _git("push", "origin", "main", cwd=main)

    report = land.land(main, here, gate=_Gate(), corpus=pool)

    assert report.code == 0
    assert "rebase=replayed onto 1 new commits" in report.lines
    assert any(line.startswith("corpus=cleared") for line in report.lines)
    assert _tip(origin) == _git("rev-parse", "HEAD", cwd=here).strip()


def test_a_filtered_run_leaves_the_corpus_owed_against_the_trees_own_probe_list(
    repo: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    origin, main, here = repo
    before = _tip(origin)
    _commit(here, "missions/cti.Stratis/init.sqf", "in-world work\n")
    pool = _write_pool(tmp_path, sha=_git("rev-parse", "HEAD", cwd=here).strip(), probes=("alpha",))

    report = land.land(main, here, gate=_Gate(), corpus=pool)

    assert report.code == 1
    assert report.lines[0] == "refusal=corpus_owed"
    assert "missing=beta" in report.lines
    assert _tip(origin) == before


def test_a_red_run_over_this_head_refuses_apart_from_a_missing_one(
    repo: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    origin, main, here = repo
    before = _tip(origin)
    _commit(here, "extension/src/lib.rs", "in-world work\n")
    pool = _write_pool(
        tmp_path,
        sha=_git("rev-parse", "HEAD", cwd=here).strip(),
        worst="assertion_failed",
        class_="assertion_failed",
    )

    report = land.land(main, here, gate=_Gate(), corpus=pool)

    assert report.code == 1
    assert report.lines[0] == "refusal=corpus_not_pass"
    assert "corpus_class=assertion_failed" in report.lines
    assert _tip(origin) == before


def test_a_run_superseded_by_someone_elses_in_world_commit_no_longer_clears(
    repo: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    """The rebase replayed this work over a tree the corpus never saw."""
    origin, main, here = repo
    before = _tip(origin)
    _commit(here, "addons/main/functions/fn_effectApply.sqf", "in-world work\n")
    pool = _write_pool(tmp_path, sha=_git("rev-parse", "HEAD", cwd=here).strip())
    _commit(main, "src/cti_daemon/outbox.py", "somebody else's in-world change\n")
    _git("push", "origin", "main", cwd=main)

    report = land.land(main, here, gate=_Gate(), corpus=pool)

    assert report.code == 1
    assert report.lines[0] == "refusal=corpus_owed"
    assert "rejected=superseded" in report.lines
    assert "changed_since=src/cti_daemon/outbox.py" in report.lines
    assert _tip(origin) != before


def test_a_pool_directory_that_never_got_its_merge_is_not_a_result(
    repo: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    """ADR-0022, at the landing gate: a run that died before its merge clears nothing."""
    _origin, main, here = repo
    _commit(here, "addons/main/functions/fn_effectApply.sqf", "in-world work\n")
    dead = tmp_path / "20260809T101500Z-pool"
    dead.mkdir()

    report = land.land(main, here, gate=_Gate(), corpus=dead)

    assert report.code == 1
    assert report.lines[0] == "refusal=corpus_owed"
    assert any("rejected=unreadable" in line for line in report.lines)


def test_a_dry_run_says_whether_the_corpus_is_owed_before_anything_is_spent(
    repo: tuple[Path, Path, Path],
) -> None:
    _origin, main, here = repo
    _commit(here, "src/cti_daemon/protocol.py", "in-world work\n")

    report = land.land(main, here, gate=_Gate(), dry_run=True, corpus=None)

    assert report.code == 0
    assert any(line.startswith("corpus=owed") for line in report.lines)
    assert any("would_clear=no" in line for line in report.lines)
