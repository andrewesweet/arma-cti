"""Stopping a dispatch, and refusing a second one into an occupied tree (#308, from #105).

The heaviest tests here are the **negative** ones, and deliberately so. This tool sends
signals, and the predicate it sends them on is "cwd inside the worktree" — so the way it
fails catastrophically is not by missing a process, it is by matching one it must never
touch: the repository root, where the orchestrator's own session sits; a sibling agent's
worktree; or a tree whose name merely starts the same way, which the by-hand
`case "$cwd" in *issue-304*)` scan from the incident would have matched. Those three come
first, and the positive case follows them.

Two layers, for the reason `tests/unit/test_dispatch.py` states about its fake `claude`:
the decisions run against an arranged `/proc` so that the exclusions can be stated exactly
and the signalling order asserted without spawning anything; and one end-to-end test runs
the real tool against the real `/proc` and a real process it starts, because the contract
under test is the kernel's and an arranged one could agree with a wrong reading of it.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from collections.abc import Iterable

dispatch_stop = load_tool("dispatch_stop")
dispatch = load_tool("dispatch")

# `load_tool` imports a `tools/` script by path, so the types it defines have no import
# statement that could name them and no static type to annotate against. These aliases
# say what the helpers below hand back without claiming a name that does not resolve.
AMachine = Any
ARecord = Any

# A pid nothing in an arranged `/proc` is given, so a test that plants it is asserting
# that the tool went looking for a pid rather than for a working directory.
RECORDED_LAUNCHER_PID = 424242


# --------------------------------------------------------------------------- arranging


def procfs(tmp_path: Path, entries: dict[int, str], name: str = "proc") -> Path:
    """Build a `/proc` holding exactly these pids, each with the cwd link named.

    Real symlinks, because the tool reads them with `os.readlink` and a link target is
    arbitrary text — which is what lets the `" (deleted)"` case be arranged at all.
    """
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    # A non-numeric entry, which `/proc` is full of and the scan must step over.
    (root / "self").mkdir(exist_ok=True)
    for pid, cwd in entries.items():
        directory = root / str(pid)
        directory.mkdir(exist_ok=True)
        (directory / "cwd").symlink_to(cwd)
        (directory / "cmdline").write_bytes(f"claude\x00--print\x00pid-{pid}\x00".encode())
        (directory / "status").write_text("Name:\tclaude\nPPid:\t1\n", encoding="utf-8")
    return root


def parent(root: Path, pid: int, ppid: int) -> None:
    """Point one arranged process at a parent, which is how the self-chain is built."""
    (root / str(pid) / "status").write_text(f"Name:\tt\nPPid:\t{ppid}\n", encoding="utf-8")


def machine(root: Path, killed: list[tuple[int, int]], self_pid: int = 999999) -> AMachine:
    """Build a `Machine` whose kill removes the pid from the arranged `/proc`, never waiting.

    Removal on signal is what makes the re-scan a real verification in these tests: the
    tool only ever learns that a process is gone by looking again.
    """

    def kill(pid: int, number: int) -> None:
        killed.append((pid, number))
        directory = root / str(pid)
        if directory.is_dir():
            (directory / "cwd").unlink(missing_ok=True)
            (directory / "cmdline").unlink(missing_ok=True)
            (directory / "status").unlink(missing_ok=True)
            directory.rmdir()

    return dispatch_stop.Machine(
        procfs=root,
        kill=kill,
        monotonic=time.monotonic,
        pause=lambda _: None,
        term_grace=0.0,
        kill_grace=0.0,
        poll=0.0,
        self_pid=self_pid,
    )


def stubborn(root: Path, killed: list[tuple[int, int]], survives: Iterable[int]) -> AMachine:
    """Build a `Machine` whose named pids ignore SIGTERM and only go on SIGKILL."""
    immune = set(survives)

    def kill(pid: int, number: int) -> None:
        killed.append((pid, number))
        if pid in immune and number == signal.SIGTERM:
            return
        directory = root / str(pid)
        if directory.is_dir():
            for child in sorted(directory.iterdir()):
                child.unlink()
            directory.rmdir()

    return dispatch_stop.Machine(
        procfs=root,
        kill=kill,
        pause=lambda _: None,
        term_grace=0.0,
        kill_grace=0.0,
        poll=0.0,
        self_pid=999999,
    )


def deaf(root: Path, killed: list[tuple[int, int]]) -> AMachine:
    """Build a `Machine` whose processes ignore every signal — the unverified case."""

    def kill(pid: int, number: int) -> None:
        killed.append((pid, number))

    return dispatch_stop.Machine(
        procfs=root,
        kill=kill,
        pause=lambda _: None,
        term_grace=0.0,
        kill_grace=0.0,
        poll=0.0,
        self_pid=999999,
    )


def record(
    tmp_path: Path, worktree: Path, dispatch_id: str = "d-20260810-141138-0fb6a9"
) -> ARecord:
    """Write a dispatch record over this worktree and return it as the tool reads it."""
    directory = tmp_path / "dispatches" / dispatch_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": dispatch_id,
                "issue": 304,
                "worktree": str(worktree),
                # The trap this whole issue exists to defuse: a pid on the record. It
                # names a process that is not in the tree, so any tool that reaches for
                # it instead of for the worktree kills the wrong thing.
                "launcher_pid": RECORDED_LAUNCHER_PID,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return dispatch_stop.Record(dispatch_id, worktree, directory)


def finished(target: ARecord, returncode: int = 0) -> None:
    """Give a record the result its own run would have written."""
    (target.directory / "result.json").write_text(
        json.dumps({"dispatch_id": target.dispatch_id, "returncode": returncode}), encoding="utf-8"
    )


def trees(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Lay out the four paths the predicate has to tell apart, as this project lays them.

    A repository root, the worktree under test, a sibling worktree, and a tree whose name
    starts with the target's — the case a glob gets wrong.
    """
    root = tmp_path / "arma-cti"
    target = root / ".claude" / "worktrees" / "issue-308"
    sibling = root / ".claude" / "worktrees" / "issue-304"
    lookalike = root / ".claude" / "worktrees" / "issue-3080"
    for path in (root, target, sibling, lookalike):
        path.mkdir(parents=True, exist_ok=True)
    return root, target, sibling, lookalike


def lines(found: Iterable[str]) -> dict[str, str]:
    """Fold the tier's `key=value` output into a mapping, last value winning."""
    out: dict[str, str] = {}
    for line in found:
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip()] = value
    return out


# ------------------------------------------------ the predicate, negative cases first


def test_the_repository_root_is_never_inside_one_of_its_own_worktrees(tmp_path: Path) -> None:
    """The orchestrator's own session sits here. Matching it is the catastrophic failure."""
    root, target, _, _ = trees(tmp_path)
    assert not dispatch_stop.inside(root.resolve(), target.resolve())
    assert not dispatch_stop.inside((root / ".claude").resolve(), target.resolve())
    assert not dispatch_stop.inside((root / ".claude" / "worktrees").resolve(), target.resolve())


def test_a_sibling_agents_worktree_is_never_inside_the_target(tmp_path: Path) -> None:
    _, target, sibling, _ = trees(tmp_path)
    assert not dispatch_stop.inside(sibling.resolve(), target.resolve())
    assert not dispatch_stop.inside((sibling / "addons").resolve(), target.resolve())


def test_a_tree_whose_name_merely_starts_the_same_is_not_inside(tmp_path: Path) -> None:
    """`issue-3080` against `issue-308`: what the incident's own `*issue-304*` glob got wrong."""
    _, target, _, lookalike = trees(tmp_path)
    assert not dispatch_stop.inside(lookalike.resolve(), target.resolve())


def test_the_worktree_itself_and_anything_under_it_is_inside(tmp_path: Path) -> None:
    _, target, _, _ = trees(tmp_path)
    assert dispatch_stop.inside(target.resolve(), target.resolve())
    assert dispatch_stop.inside((target / "addons" / "main").resolve(), target.resolve())


def test_the_scan_leaves_every_neighbouring_tree_alone(tmp_path: Path) -> None:
    """The predicate is asserted again through the scan, where a bug would actually kill."""
    root, target, sibling, lookalike = trees(tmp_path)
    fake = procfs(
        tmp_path,
        {
            11: str(root),
            12: str(sibling),
            13: str(lookalike),
            14: str(root / ".claude" / "worktrees"),
            15: str(target),
        },
    )
    found = dispatch_stop.scan(target, machine(fake, []))
    assert [process.pid for process in found.matched] == [15]


def test_a_symlinked_worktree_path_still_matches_its_own_processes(tmp_path: Path) -> None:
    """`/proc` reports canonical paths, so the recorded tree has to be resolved to compare."""
    _, target, _, _ = trees(tmp_path)
    link = tmp_path / "linked-tree"
    link.symlink_to(target)
    fake = procfs(tmp_path, {21: str(target.resolve())})
    found = dispatch_stop.scan(link, machine(fake, []))
    assert [process.pid for process in found.matched] == [21]


def test_a_deleted_working_directory_is_counted_and_never_signalled(tmp_path: Path) -> None:
    """After `worktree done` + `worktree add` at one path, that text is the old occupant's."""
    _, target, _, _ = trees(tmp_path)
    fake = procfs(tmp_path, {31: f"{target} (deleted)", 32: str(target)})
    killed: list[tuple[int, int]] = []
    found = dispatch_stop.scan(target, machine(fake, killed))
    assert [process.pid for process in found.matched] == [32]
    assert found.deleted == 1


def test_this_process_and_its_ancestors_are_reported_and_never_signalled(tmp_path: Path) -> None:
    """`just dispatch --stop` typed from inside the tree must not kill the shell that typed it."""
    _, target, _, _ = trees(tmp_path)
    fake = procfs(tmp_path, {41: str(target), 42: str(target), 43: str(target)})
    parent(fake, 43, 42)
    parent(fake, 42, 1)
    found = dispatch_stop.scan(target, machine(fake, [], self_pid=43))
    assert [process.pid for process in found.matched] == [41]
    assert sorted(process.pid for process in found.mine) == [42, 43]


def test_the_command_line_is_rendered_for_the_report(tmp_path: Path) -> None:
    """Four processes were killed in the incident and only one was the session."""
    _, target, _, _ = trees(tmp_path)
    fake = procfs(tmp_path, {51: str(target)})
    found = dispatch_stop.scan(target, machine(fake, []))
    assert found.matched[0].command == "claude --print pid-51"


# -------------------------------------------------------------------------- stopping


def test_a_stop_kills_every_process_in_the_tree_and_verifies_by_re_scanning(
    tmp_path: Path,
) -> None:
    root, target, sibling, _ = trees(tmp_path)
    fake = procfs(
        tmp_path,
        {61: str(target), 62: str(target / "addons"), 63: str(root), 64: str(sibling)},
    )
    killed: list[tuple[int, int]] = []
    target_record = record(tmp_path, target)

    code, printed = dispatch_stop.stop(target_record, machine(fake, killed))

    assert code == 0
    found = lines(printed)
    assert found["stop"] == "stopped"
    assert found["killed"] == "2"
    assert found["verified"] == "no_process_in_worktree"
    assert found["killed.61"] == "SIGTERM claude --print pid-61"
    assert found["killed.62"] == "SIGTERM claude --print pid-62"
    # The two processes outside the tree were never signalled, which is the assertion
    # that matters more than the two that were.
    assert sorted(pid for pid, _ in killed) == [61, 62]


def test_a_stop_never_keys_on_the_recorded_launcher_pid(tmp_path: Path) -> None:
    """#105: the record's pid is the launcher, and the session reparents away from it."""
    root, target, _, _ = trees(tmp_path)
    fake = procfs(tmp_path, {RECORDED_LAUNCHER_PID: str(root), 71: str(target)})
    killed: list[tuple[int, int]] = []

    code, printed = dispatch_stop.stop(record(tmp_path, target), machine(fake, killed))

    assert code == 0
    assert sorted(pid for pid, _ in killed) == [71]
    assert RECORDED_LAUNCHER_PID not in {pid for pid, _ in killed}
    assert f"killed.{RECORDED_LAUNCHER_PID}" not in lines(printed)


def test_a_process_that_ignores_sigterm_is_escalated_and_then_verified(tmp_path: Path) -> None:
    _, target, _, _ = trees(tmp_path)
    fake = procfs(tmp_path, {81: str(target), 82: str(target)})
    killed: list[tuple[int, int]] = []

    code, printed = dispatch_stop.stop(record(tmp_path, target), stubborn(fake, killed, {82}))

    assert code == 0
    found = lines(printed)
    assert found["killed.81"].startswith("SIGTERM ")
    assert found["killed.82"].startswith("SIGKILL ")
    assert (82, signal.SIGTERM) in killed
    assert (82, signal.SIGKILL) in killed


def test_a_tree_that_is_still_occupied_after_sigkill_is_a_finding_and_not_a_stop(
    tmp_path: Path,
) -> None:
    """A stop that does not verify is a guess, which is the whole of #105's second half."""
    _, target, _, _ = trees(tmp_path)
    fake = procfs(tmp_path, {91: str(target)})
    killed: list[tuple[int, int]] = []
    target_record = record(tmp_path, target)

    code, printed = dispatch_stop.stop(target_record, deaf(fake, killed))

    assert code == dispatch_stop.EXIT_FINDING
    found = lines(printed)
    assert found["finding"] == "stop_unverified"
    assert found["survivor.91"] == "claude --print pid-91"
    assert found["verified"] == "no"
    assert found["result"] == "none"
    assert "Do not re-dispatch into this tree" in found["action"]
    # And no result is recorded, so the occupancy rung keeps refusing this tree.
    assert not (target_record.directory / "result.json").exists()


def test_a_stop_records_an_ending_so_the_tree_becomes_dispatchable_again(tmp_path: Path) -> None:
    _, target, _, _ = trees(tmp_path)
    fake = procfs(tmp_path, {101: str(target)})
    target_record = record(tmp_path, target)

    dispatch_stop.stop(target_record, machine(fake, []))

    written = json.loads((target_record.directory / "result.json").read_text(encoding="utf-8"))
    assert written["dispatch_id"] == target_record.dispatch_id
    assert written["stopped_by"] == "just dispatch --stop"
    assert written["killed"] == ["101 SIGTERM"]
    # Facts only, and specifically no `refusal`: `tools/ledger.py` reads that key as proof
    # the dispatcher refused before the lane was reached, which is false of a stop.
    assert "refusal" not in written
    assert dispatch_stop.holders(target, tmp_path / "dispatches") == ()


def test_a_stop_never_overwrites_the_runs_own_account_of_itself(tmp_path: Path) -> None:
    _, target, _, _ = trees(tmp_path)
    fake = procfs(tmp_path, {111: str(target)})
    target_record = record(tmp_path, target)
    finished(target_record, returncode=17)
    before = (target_record.directory / "result.json").read_bytes()

    code, printed = dispatch_stop.stop(target_record, machine(fake, []))

    assert code == 0
    assert lines(printed)["result"] == "preserved"
    assert lines(printed)["killed"] == "1"
    assert (target_record.directory / "result.json").read_bytes() == before


# ------------------------------------------------------- the two benign empty endings


def test_stopping_a_dispatch_that_already_finished_is_a_named_outcome(tmp_path: Path) -> None:
    """The case a seat that has lost track of what is running will type."""
    _, target, _, _ = trees(tmp_path)
    fake = procfs(tmp_path, {})
    target_record = record(tmp_path, target)
    finished(target_record)
    before = (target_record.directory / "result.json").read_bytes()

    code, printed = dispatch_stop.stop(target_record, machine(fake, []))

    assert code == 0
    found = lines(printed)
    assert found["stop"] == "already_finished"
    assert found["killed"] == "0"
    assert found["result"] == "preserved"
    assert (target_record.directory / "result.json").read_bytes() == before


def test_stopping_a_dispatch_that_died_without_saying_so_records_the_ending(
    tmp_path: Path,
) -> None:
    """Otherwise a crashed dispatch blocks its tree with no remedy anywhere."""
    _, target, _, _ = trees(tmp_path)
    target_record = record(tmp_path, target)

    code, printed = dispatch_stop.stop(target_record, machine(procfs(tmp_path, {}), []))

    assert code == 0
    found = lines(printed)
    assert found["stop"] == "already_stopped"
    assert found["killed"] == "0"
    assert (target_record.directory / "result.json").is_file()
    assert dispatch_stop.holders(target, tmp_path / "dispatches") == ()


# ------------------------------------------------------------------------- refusals


def test_an_unknown_dispatch_id_refuses_without_signalling_or_writing(tmp_path: Path) -> None:
    (tmp_path / "dispatches").mkdir()
    code, printed = dispatch_stop.stop_by_id(tmp_path / "dispatches", "d-20260810-000000-abcdef")
    assert code == dispatch_stop.EXIT_REFUSED
    assert lines(printed)["refusal"] == "unknown_dispatch"
    assert list((tmp_path / "dispatches").iterdir()) == []


def test_a_dispatch_id_outside_the_minted_alphabet_is_refused_before_any_path_is_joined(
    tmp_path: Path,
) -> None:
    code, printed = dispatch_stop.stop_by_id(tmp_path / "dispatches", "../../etc")
    assert code == dispatch_stop.EXIT_REFUSED
    assert lines(printed)["refusal"] == "invalid_dispatch_id"


def test_an_unreadable_record_refuses_rather_than_guessing_at_a_tree(tmp_path: Path) -> None:
    directory = tmp_path / "dispatches" / "d-20260810-141138-0fb6a9"
    directory.mkdir(parents=True)
    (directory / "dispatch.json").write_text("{ not json", encoding="utf-8")

    code, printed = dispatch_stop.stop_by_id(tmp_path / "dispatches", directory.name)

    found = lines(printed)
    assert code == dispatch_stop.EXIT_REFUSED
    assert found["refusal"] == "dispatch_unreadable"
    assert found["class"] == "infra_unavailable"
    assert not (directory / "result.json").exists()


def test_a_worktree_that_is_gone_refuses_and_kills_nothing(tmp_path: Path) -> None:
    """Absence of the tree does not prove absence of the work: a removed cwd still reads."""
    _, target, _, _ = trees(tmp_path)
    target_record = record(tmp_path, target / "vanished")
    killed: list[tuple[int, int]] = []

    code, printed = dispatch_stop.stop(target_record, machine(procfs(tmp_path, {}), killed))

    found = lines(printed)
    assert code == dispatch_stop.EXIT_REFUSED
    assert found["refusal"] == "worktree_gone"
    assert found["class"] == "infra_unavailable"
    assert killed == []
    assert not (target_record.directory / "result.json").exists()


def test_a_box_with_no_procfs_refuses_rather_than_reporting_an_empty_tree(
    tmp_path: Path,
) -> None:
    _, target, _, _ = trees(tmp_path)
    target_record = record(tmp_path, target)
    absent = dispatch_stop.Machine(procfs=tmp_path / "no-proc", self_pid=1)

    code, printed = dispatch_stop.stop(target_record, absent)

    found = lines(printed)
    assert code == dispatch_stop.EXIT_REFUSED
    assert found["refusal"] == "procfs_unavailable"
    assert found["class"] == "infra_unavailable"
    assert not (target_record.directory / "result.json").exists()


# ----------------------------------------------------- the occupancy rung at dispatch


def test_a_tree_holding_a_result_less_dispatch_refuses_a_second_one_by_name(
    tmp_path: Path,
) -> None:
    _, target, _, _ = trees(tmp_path)
    holder = record(tmp_path, target)

    refusal = dispatch_stop.occupancy_refusal(target, tmp_path / "dispatches")

    assert refusal is not None
    assert refusal.kind == "worktree_occupied_by_dispatch"
    assert any(f"holder={holder.dispatch_id}" in line for line in refusal.found)
    # No failure class: nothing was found about any provider, lane or code.
    assert refusal.failure_class == ""
    assert "just dispatch --stop" in refusal.action


def test_a_predecessor_that_recorded_an_ending_does_not_occupy_its_tree(tmp_path: Path) -> None:
    _, target, _, _ = trees(tmp_path)
    finished(record(tmp_path, target))
    assert dispatch_stop.occupancy_refusal(target, tmp_path / "dispatches") is None


def test_a_dispatch_over_another_tree_does_not_occupy_this_one(tmp_path: Path) -> None:
    _, target, sibling, lookalike = trees(tmp_path)
    record(tmp_path, sibling, "d-20260810-133639-58403e")
    record(tmp_path, lookalike, "d-20260810-133704-240d0a")
    assert dispatch_stop.occupancy_refusal(target, tmp_path / "dispatches") is None


def test_every_holder_of_the_tree_is_named_and_not_merely_the_first(tmp_path: Path) -> None:
    _, target, _, _ = trees(tmp_path)
    record(tmp_path, target, "d-20260810-133639-58403e")
    record(tmp_path, target, "d-20260810-133704-240d0a")

    refusal = dispatch_stop.occupancy_refusal(target, tmp_path / "dispatches")

    assert refusal is not None
    named = [line for line in refusal.found if line.startswith("holder=")]
    assert len(named) == 2


def test_an_unreadable_neighbour_record_does_not_stop_the_rung_reading_the_rest(
    tmp_path: Path,
) -> None:
    _, target, _, _ = trees(tmp_path)
    broken = tmp_path / "dispatches" / "d-20260810-000000-bbbbbb"
    broken.mkdir(parents=True)
    (broken / "dispatch.json").write_text("{ not json", encoding="utf-8")
    record(tmp_path, target)

    refusal = dispatch_stop.occupancy_refusal(target, tmp_path / "dispatches")

    assert refusal is not None
    assert refusal.kind == "worktree_occupied_by_dispatch"


def test_no_dispatch_directory_at_all_occupies_nothing(tmp_path: Path) -> None:
    _, target, _, _ = trees(tmp_path)
    assert dispatch_stop.occupancy_refusal(target, tmp_path / "never-dispatched") is None


# --------------------------------------------------- the rung inside the real planner


def git_worktree(tmp_path: Path, name: str = "tree") -> Path:
    """Build a real git repository, because the planner's worktree checks are real git."""
    root = tmp_path / name
    root.mkdir(parents=True)
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "t@example.invalid"),
        ("config", "user.name", "t"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    (root / "README.md").write_text("t\n", encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-qm", "t")):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)  # noqa: S603, S607
    return root


def open_policy(tmp_path: Path) -> Path:
    """Write a dispatch policy of this test's own: open, with a limit nothing here reaches."""
    directory = tmp_path / "queue"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "freeze": {"state": "open", "since": "2026-08-10T00:00:00Z", "ruling": "a test"},
                "wip_limit": {"value": 9, "since": "2026-08-10T00:00:00Z", "ruling": "a test"},
                "packages": [],
            }
        ),
        encoding="utf-8",
    )
    return directory


def plan_over(tmp_path: Path, worktree: Path) -> tuple[Any, str, Any]:
    """Plan a `claude-native` dispatch over this exact tree, writing nothing."""
    request = {
        "lane": "claude-native",
        "profile": "opus-high",
        "seat": "implementer",
        "issue": 308,
        "worktree": str(worktree),
        "brief_file": "",
        "base_sha": "",
        "permission_mode": "acceptEdits",
        "dispatch_dir": str(tmp_path / "dispatches"),
        "credentials": str(tmp_path / "credentials.env"),
        "breaker_dir": str(tmp_path / "breaker"),
        "issue_body": str(REPO / "tests" / "fixtures" / "routing-eligible.md"),
        "queue_dir": str(open_policy(tmp_path)),
        "queue_root": str(tmp_path / "queue-root"),
        # No profile is under review here; the `implementer` seat declares none (#322).
        "reviewing": "",
    }
    args = type("Args", (), request)()
    return dispatch.plan_dispatch(args, REPO, datetime.now(tz=UTC))


def test_the_planner_refuses_a_second_dispatch_into_an_occupied_tree(tmp_path: Path) -> None:
    """#105's sixth instance, as the rung that would have stopped it in the second it happened."""
    worktree = git_worktree(tmp_path)
    holder = record(tmp_path, worktree, "d-20260810-133639-58403e")

    plan, _, refusal = plan_over(tmp_path, worktree)

    assert plan is None
    assert refusal is not None
    assert refusal.kind == "worktree_occupied_by_dispatch"
    assert any(f"holder={holder.dispatch_id}" in line for line in refusal.found)
    # Nothing was written: the refusal happens before the record directory is made.
    assert sorted(p.name for p in (tmp_path / "dispatches").iterdir()) == [holder.dispatch_id]


def test_the_planner_admits_a_tree_whose_predecessor_recorded_an_ending(tmp_path: Path) -> None:
    worktree = git_worktree(tmp_path)
    finished(record(tmp_path, worktree, "d-20260810-133639-58403e"))

    plan, _, refusal = plan_over(tmp_path, worktree)

    assert refusal is None
    assert plan is not None
    assert plan.worktree == worktree


def test_the_stop_surface_needs_no_lane_profile_seat_or_issue(tmp_path: Path) -> None:
    """A stop names a dispatch that already exists and takes the rest from its record."""
    (tmp_path / "dispatches").mkdir()
    code = dispatch.main(
        [
            "--stop",
            "d-20260810-000000-abcdef",
            "--dispatch-dir",
            str(tmp_path / "dispatches"),
        ]
    )
    # Refused because that id is unknown, and specifically *not* `incomplete_request`.
    assert code == dispatch.EXIT_REFUSED


@pytest.mark.parametrize("flag", ["--stop-pid", "--no-verify", "--force-stop", "--stop-launcher"])
def test_no_option_on_this_surface_stops_by_pid_or_skips_the_verifying_re_scan(flag: str) -> None:
    """The verification is not optional and the pid is not a handle, so neither has a flag."""
    with pytest.raises(SystemExit):
        dispatch.parse_args([flag, "1"])


# ------------------------------------------------------------- against the real /proc


def test_a_real_process_working_in_the_tree_is_found_stopped_and_verified(
    tmp_path: Path,
) -> None:
    """The end-to-end claim, against the kernel's own `/proc` and a process we started.

    Arranged `/proc` trees can only ever agree with this module's reading of the kernel's
    contract. This one is the contract: a real child with a real working directory, found
    by the real scan, signalled, and proven gone by the real re-scan.
    """
    if not Path("/proc").is_dir():  # pragma: no cover - this project's tier is Linux
        pytest.skip("no /proc on this box")
    _, target, sibling, _ = trees(tmp_path)
    # One process in the tree and one in the neighbouring tree. The second is the claim.
    # S603: this interpreter and a fixed literal, which is the whole of the input.
    idle = [sys.executable, "-c", "import time; time.sleep(120)"]
    inside_tree = subprocess.Popen(idle, cwd=target)  # noqa: S603
    outside = subprocess.Popen(idle, cwd=sibling)  # noqa: S603
    try:
        target_record = record(tmp_path, target)
        code, printed = dispatch_stop.stop(target_record)

        found = lines(printed)
        assert code == 0, printed
        assert found["stop"] == "stopped"
        assert f"killed.{inside_tree.pid}" in found
        assert f"killed.{outside.pid}" not in found
        assert found["verified"] == "no_process_in_worktree"
        assert inside_tree.wait(timeout=10) != 0
        assert outside.poll() is None, "the neighbouring tree's process was signalled"
    finally:
        for child in (inside_tree, outside):
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)
