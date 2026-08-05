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

import subprocess
from pathlib import Path

import pytest
from conftest import load_tool

# `land` imports `worktree` as a sibling script, so the sibling is loaded first
# and registered under its own name for that import to find.
worktree = load_tool("worktree")
land = load_tool("land")

_CLEAN = worktree.Preflight((), ())
_HERE = Path("/home/a/repo/.claude/worktrees/issue-213")
_MAIN = Path("/home/a/repo")


def _kind(refusal: object) -> str:
    return refusal.kind  # type: ignore[attr-defined]


def _text(refusal: object) -> str:
    return "\n".join(refusal.lines())  # type: ignore[attr-defined]


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
    (path / name).write_text(body, encoding="utf-8")
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
