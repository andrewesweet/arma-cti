"""The recon seat cannot affect a landing, because its tree is disposable (#407, #600).

ADR-0071 does not make `recon` a landing seat. Its ruling-2 table row and body still reason
from the unranked profile head, the routing class 2 admission and the absent escalation
entry. #600 gives the seat a dispatch-owned tree: both runner families can execute the gate,
and edits remain disposable rather than reaching the reviewed ref.

The claims are made through `plan_dispatch` and `main`, following `test_dispatch_seat.py`'s
rule: what a caller gets is a plan or a refusal, and a registry column that read back correctly
while `build_argv` rendered something else would satisfy an internal test and none of the
criteria. So every containment claim below is about the **rendered argv**, on both runner
families, and the Codex ones name the scoped workspace-write policy and measured cache grants.

Arrangements are clock-free for that module's reason, and its `plan_for` is reused rather than
copied: the criterion is about the seat, and a second copy of the request shape is a second
thing to drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool
from test_dispatch_seat import git_worktree, open_policy, plan_for, trip

if TYPE_CHECKING:
    from pathlib import Path

dispatch = load_tool("dispatch")

READY_BODY = REPO / "tests" / "fixtures" / "routing-eligible.md"

# What the dispatcher really passes when a caller types no `--permission-mode` at all. Every
# claim here is made against it, because "without the caller passing anything" is the
# criterion and passing `plan` would test the caller rather than the seat.
WRITABLE_DEFAULT = "acceptEdits"


def recon_plan(tmp_path: Path, **overrides: object):  # noqa: ANN201 — the planner's own tuple, named where it is unpacked
    """Plan a recon dispatch at the writable default, which is what the gap looked like."""
    return plan_for(tmp_path, seat="recon", permission_mode=WRITABLE_DEFAULT, **overrides)


def recon_dry_run_argv(tmp_path: Path) -> list[str]:
    """Build the command line a recon dry run is, with every state directory this test's own.

    Written out rather than borrowed from `test_dispatch_seat.seat_only_argv`, which names
    `implementer`: appending a second `--seat` would work on argparse's last-wins rule and
    would read as a command nobody would type.
    """
    return [
        "--seat",
        "recon",
        "--issue",
        "407",
        "--worktree",
        str(git_worktree(tmp_path)),
        "--issue-body",
        str(READY_BODY),
        "--dispatch-dir",
        str(tmp_path / "dispatches"),
        "--credentials",
        str(tmp_path / "credentials.env"),
        "--breaker-dir",
        str(tmp_path / "breaker"),
        "--queue-dir",
        str(open_policy(tmp_path)),
        "--queue-root",
        str(tmp_path / "queue-root"),
        "--dry-run",
    ]


def dry_run_argv_line(capsys: pytest.CaptureFixture[str]) -> str:
    """Pull the one printed line a reader of a dry run checks the containment on."""
    return next(line for line in capsys.readouterr().out.splitlines() if line.startswith("argv="))


# ------------------------------------- criterion 1: the column is the seat's, not the caller's


def test_the_recon_row_forces_a_read_only_mode_the_way_the_review_row_does() -> None:
    """The ADR's read-only is a property the registry holds, not a sentence about the seat."""
    assert dispatch.SEATS["recon"].permission_mode == "plan"
    assert dispatch.SEATS["recon"].permission_mode == dispatch.SEATS["review"].permission_mode


def test_the_seats_that_gate_and_land_keep_the_mode_the_caller_asked_for() -> None:
    """Contained seats write nothing; an implementer that cannot run its own gate is not one."""
    for name in ("planner", "implementer", "retro", "fable", "orchestrator"):
        assert dispatch.SEATS[name].permission_mode == "", name


# ---------------------------------------- criteria 2 and 3: the rendered argv on both families


def test_a_codex_lane_recon_runs_in_the_disposable_tree_without_the_caller_passing_anything(
    tmp_path: Path,
) -> None:
    """The seat's Codex rung, whose vocabulary for the mode is a sandbox policy.

    `codex-luna-medium` headed this seat until the human's ruling of 2026-08-27 put
    `zai-glm53flash-high` in front of it; this arrangement carries no z.ai key, so the
    Codex rung is what a bare `--seat recon` reaches here.
    """
    plan, _, refusal = recon_plan(tmp_path)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.lane == "codex"
    assert plan.permission_mode == "plan"
    assert "--sandbox" in plan.argv
    assert plan.argv[plan.argv.index("--sandbox") + 1] == "workspace-write"


def test_a_codex_lane_recon_gets_only_the_measured_cache_roots_and_network(tmp_path: Path) -> None:
    """The disposable cwd is writable; only the existing measured cache grants are added."""
    plan, _, refusal = recon_plan(tmp_path)
    assert refusal is None, refusal
    assert plan is not None
    roots = [part for part in plan.argv if part.startswith("sandbox_workspace_write.")]
    assert len(roots) == 2
    assert all("/home/andre/.claude" not in part for part in roots)
    assert "workspace-write" in plan.argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in plan.argv


def test_a_claude_lane_recon_runs_read_only_without_the_caller_passing_anything(
    tmp_path: Path,
) -> None:
    """The other family, reached by walking the seat's Codex rung past a tripped breaker."""
    trip(tmp_path, "codex", "gate_failed", 3)
    plan, _, refusal = recon_plan(tmp_path)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.identity.lane == "claude-native"
    assert plan.permission_mode == "plan"
    assert "--permission-mode" in plan.argv
    assert plan.argv[plan.argv.index("--permission-mode") + 1] == "plan"
    assert WRITABLE_DEFAULT not in plan.argv


# -------------------------------- criterion 5: overridden rather than obeyed, and never silent


@pytest.mark.parametrize("asked", ["acceptEdits", "bypassPermissions", "default"])
def test_the_seat_overrides_whatever_permission_mode_the_caller_typed(
    tmp_path: Path, asked: str
) -> None:
    """Overridden rather than refused, and the code says why.

    `--permission-mode` *defaults* to a writable value, so a refusal could not tell a caller
    who typed one from one who typed nothing, and would refuse the ordinary dispatch along
    with the deliberate one.
    """
    plan, _, refusal = plan_for(tmp_path, seat="recon", permission_mode=asked)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.permission_mode == "plan"


def test_naming_a_route_by_hand_does_not_buy_a_writable_recon_dispatch(tmp_path: Path) -> None:
    """`--profile` is a way of choosing and never a way around, containment included."""
    plan, _, refusal = plan_for(
        tmp_path,
        seat="recon",
        lane="claude-native",
        profile="haiku-medium",
        permission_mode="bypassPermissions",
    )
    assert refusal is None, refusal
    assert plan is not None
    assert plan.permission_mode == "plan"
    assert plan.argv[plan.argv.index("--permission-mode") + 1] == "plan"
    assert "--dangerously-bypass-approvals-and-sandbox" not in plan.argv


def test_the_forcing_is_recorded_rather_than_silent(tmp_path: Path) -> None:
    """A reader who typed a writable mode and got a read-only run can see who overrode them."""
    plan, _, _ = recon_plan(tmp_path)
    assert plan is not None
    assert (
        "route_permission_mode=plan forced_by_seat=recon (no caller override)" in plan.route.lines()
    )


# --------------------------------- criterion 4: the dry run a reader is asked to check shows it


def test_the_dry_run_shows_the_disposable_workspace_flag_in_the_argv_it_would_launch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criterion 4's substance, made a check rather than a transcript.

    A pasted dry run records what the command printed on one day; this asserts the same
    printed line every run, so a later edit that quietly widened the recon sandbox reds here
    instead of being caught by whoever next re-reads an old issue comment.
    """
    assert dispatch.main(recon_dry_run_argv(tmp_path)) == 0
    line = dry_run_argv_line(capsys)
    assert "--sandbox workspace-write" in line
    assert "sandbox_workspace_write.writable_roots=" in line
    assert "sandbox_workspace_write.network_access=true" in line
    assert "--dangerously-bypass-approvals-and-sandbox" not in line


def test_the_dry_run_on_the_claude_family_shows_it_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same reading on the other runner, reached by walking the Codex rung past a breaker."""
    trip(tmp_path, "codex", "gate_failed", 3)
    assert dispatch.main(recon_dry_run_argv(tmp_path)) == 0
    line = dry_run_argv_line(capsys)
    assert "--permission-mode plan" in line
    assert WRITABLE_DEFAULT not in line


def test_a_disposable_dry_run_names_the_tree_the_real_dispatch_would_use(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rehearsal describes the dispatch-owned cwd without creating it."""
    assert dispatch.main(recon_dry_run_argv(tmp_path)) == 0
    output = capsys.readouterr().out.splitlines()
    worktree = next(line for line in output if line.startswith("worktree="))
    assert "/.claude/worktrees/dispatch-" in worktree
    assert str(tmp_path / "tree") not in worktree


def test_a_non_materialized_disposable_plan_is_recorded_as_disposable(tmp_path: Path) -> None:
    """Dry-run planning keeps the same containment metadata as a real dispatch."""
    plan, _, refusal = recon_plan(tmp_path, dry_run=True)
    assert refusal is None, refusal
    assert plan is not None
    assert plan.disposable_worktree is True
    assert plan.worktree.name.startswith("dispatch-")
    assert not plan.worktree.exists()


def test_the_registry_listing_states_the_recon_seats_containment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--list` is where a reader asks what a seat does differently, and now it answers."""
    assert dispatch.main(["--list"]) == 0
    block = capsys.readouterr().out.split("seat=recon\n")[1].split("seat=")[0]
    assert "  permission_mode=plan forced=true (no caller override)" in block
