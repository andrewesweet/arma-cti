"""The BLIND look and the resumption briefing's computable halves (#253).

Four layers.

The deciding first, as a pure function over readings, so every verdict is asserted by its
own name *and* by the basis it printed — a verdict whose reasoning is not asserted can be
reached for the wrong reason and still be green.

Then the replay, which is acceptance criterion 1 and the reason this file vendors records
rather than inventing them: `tests/fixtures/recovery-blind/` holds the twenty-fourth
retro's four BLIND watcher findings and the twenty-fifth's two dead assessors exactly as
`~/.arma-cti/watch/` recorded them, the two review dispatch records beside them, and the
commits each watch's own window covered. The by-hand verdicts are in
`docs/process-log.md`; this asserts the tool reaches the same six.

Then the tool against real git, because a tree carrying unlanded commits is the case the
whole `lost_work` verdict exists for, and a fixture that only ever sees strings this file
invented would prove nothing about what git prints.

Then the briefing's three properties, each of which is a criterion: reconstruction 3 is
empty and no input fills it; a clean tree zero commits ahead produces evidence and no
assertion about what that evidence means; and an issue carrying no handoff carries the
handoff tool's own refusal rather than a blank space.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from collections.abc import Sequence

recovery = load_tool("recovery")
handoff_fetch = load_tool("handoff_fetch")

BLIND_CORPUS = REPO / "tests" / "fixtures" / "recovery-blind"
WATCH_CORPUS = BLIND_CORPUS / "watch"
DISPATCH_CORPUS = BLIND_CORPUS / "dispatches"
WINDOWS = json.loads((BLIND_CORPUS / "windows.json").read_text(encoding="utf-8"))

# The twenty-fourth retro's four, over the removed prior-art research worktrees, and the
# output `docs/agents/recovery.md` records as having reached main under each of them.
RESEARCH_FOUR = (
    "research-evals",
    "research-observability",
    "research-portability",
    "research-routing",
)
RECORDED_SHAS = ("2449d2d", "ff5e5b2", "fb43cc9", "b3953f6")

# The twenty-fifth's two: both review-watcher assessors died in crash cluster two, leaving
# `watch_broken` findings and 0-byte logs, and the by-hand look found both watched agents
# had finished. Their dispatch records are what says so.
ASSESSOR_TWO = ("review-227-zai", "review-92-claude")


# ------------------------------------------------------------------------ the arrangement


def a_tree(**fields: object) -> recovery.Tree:
    """Build a `Tree` in one line, with the reading under test varied.

    The defaults are the hardest case this tool faces: a worktree that is gone, that git
    holds no registration for, and that no HEAD is knowable for.
    """
    defaults: dict[str, object] = {
        "path": Path("/repo/.claude/worktrees/issue-1"),
        "present": False,
        "registered": False,
        "head": "",
        "head_source": recovery.FROM_NONE,
        "uncommitted": (),
        "ahead": (),
        "files": (),
        "on_main": "unknown",
    }
    return recovery.Tree(**{**defaults, **fields})


def a_watch(**fields: object) -> recovery.Watch:
    """Build a `Watch` in one line."""
    defaults: dict[str, object] = {
        "name": "w",
        "spec_path": Path("/w/w.spec.json"),
        "finding_path": Path("/w/w.finding.json"),
        "worktree": "/repo/.claude/worktrees/issue-1",
        "baseline_head": "b" * 40,
        "armed_at": 1000,
        "subject": "pool",
        "issue": "#1",
        "state": "watch_blind",
        "head": "",
        "assessed_at": 2000,
        "acknowledged_at": 0,
    }
    return recovery.Watch(**{**defaults, **fields})


def evidence_of(tree: recovery.Tree, **fields: object) -> recovery.Evidence:
    """Build an `Evidence` around one tree, with the other readings varied."""
    defaults: dict[str, object] = {
        "name": "w",
        "watch": a_watch(),
        "tree": tree,
        "dispatches": (),
        "window": (),
        "window_from": 1000,
        "window_to": 2000,
    }
    return recovery.Evidence(**{**defaults, **fields})


def a_dispatch(**fields: object) -> recovery.Dispatch:
    """Build a `Dispatch` record in one line."""
    defaults: dict[str, object] = {
        "dispatch_id": "d-1",
        "issue": 1,
        "worktree": "/repo/.claude/worktrees/issue-1",
        "base_sha": "a" * 40,
        "finished": True,
    }
    return recovery.Dispatch(**{**defaults, **fields})


# ---------------------------------------------------------------------------- the deciding


def test_unlanded_commits_are_lost_work_whatever_else_is_true() -> None:
    verdict = recovery.decide(
        evidence_of(
            a_tree(
                present=True,
                head="f4ce30f9b521",
                head_source=recovery.FROM_WORKTREE,
                on_main="no",
                ahead=(recovery.Commit("f4ce30f", "fix: a thing"),),
            ),
            dispatches=(a_dispatch(),),
            window=(recovery.Commit("abc1234", "feat: something else"),),
        )
    )
    assert verdict.kind == recovery.LOST
    assert "1 commit(s)" in verdict.basis
    assert "f4ce30f9b521" in verdict.basis
    assert "not on origin/main" in verdict.basis
    # The cleared verdict's caveat belongs to the cleared verdict alone.
    assert verdict.cannot_exclude == ""


def test_a_worktree_on_disk_whose_head_reads_is_still_live() -> None:
    verdict = recovery.decide(
        evidence_of(a_tree(present=True, head="a" * 40, head_source=recovery.FROM_WORKTREE))
    )
    assert verdict.kind == recovery.LIVE
    assert "judgement" in verdict.basis


def test_a_gone_tree_whose_last_head_is_on_main_is_finished_and_cleaned() -> None:
    verdict = recovery.decide(
        evidence_of(
            a_tree(
                registered=True,
                head="c" * 40,
                head_source=recovery.FROM_REGISTRATION,
                on_main="yes",
            )
        )
    )
    assert verdict.kind == recovery.FINISHED
    assert "ancestor of origin/main" in verdict.basis
    assert recovery.FROM_REGISTRATION in verdict.basis
    # A HEAD that is provably on main needs no caveat: the reading is exact.
    assert verdict.cannot_exclude == ""


def test_a_finished_dispatch_clears_a_gone_tree_and_says_what_it_cannot_exclude() -> None:
    verdict = recovery.decide(evidence_of(a_tree(), dispatches=(a_dispatch(),)))
    assert verdict.kind == recovery.FINISHED
    assert "d-1" in verdict.basis
    assert "result.json" in verdict.basis
    assert "reads identically" in verdict.cannot_exclude


def test_an_unfinished_dispatch_clears_nothing() -> None:
    """A dispatch record with no result says the dispatch was made, not that it returned."""
    verdict = recovery.decide(evidence_of(a_tree(), dispatches=(a_dispatch(finished=False),)))
    assert verdict.kind == recovery.UNPROVEN


def test_a_dispatch_over_another_worktree_clears_nothing() -> None:
    verdict = recovery.decide(
        evidence_of(a_tree(), dispatches=(a_dispatch(worktree="/repo/.claude/worktrees/issue-9"),))
    )
    assert verdict.kind == recovery.UNPROVEN


def test_the_window_clears_a_gone_tree_and_is_called_a_window_not_an_attribution() -> None:
    verdict = recovery.decide(
        evidence_of(a_tree(), window=(recovery.Commit("2449d2d", "docs: sweep the prior art"),))
    )
    assert verdict.kind == recovery.FINISHED
    assert "1 commit(s) reached origin/main while this watch was live" in verdict.basis
    assert "not attribution" in verdict.basis
    assert verdict.cannot_exclude


def test_nothing_positive_leaves_the_look_unproven_rather_than_cleared() -> None:
    """The vacuity rule (#116): an absent tree with nothing attributable proves nothing."""
    verdict = recovery.decide(evidence_of(a_tree()))
    assert verdict.kind == recovery.UNPROVEN
    assert "did not resolve" in verdict.basis
    assert "guess" in verdict.basis


def test_a_present_tree_is_never_cleared_by_a_window_it_did_not_make() -> None:
    """Positive evidence answers for a tree that is *gone*; a tree on disk answers for itself."""
    verdict = recovery.decide(
        evidence_of(
            a_tree(present=True),
            dispatches=(a_dispatch(),),
            window=(recovery.Commit("2449d2d", "docs: sweep"),),
        )
    )
    assert verdict.kind == recovery.UNPROVEN


def test_a_head_git_cannot_resolve_is_not_read_as_landed() -> None:
    """`unknown` is a third answer, and it must not collapse into `yes` (#41, #44)."""
    verdict = recovery.decide(
        evidence_of(a_tree(head="d" * 40, head_source=recovery.FROM_FINDING, on_main="unknown"))
    )
    assert verdict.kind == recovery.UNPROVEN


# ------------------------------------------------------------------------------ the replay


def replay(name: str) -> tuple[recovery.Evidence, recovery.Verdict]:
    """Resolve one vendored BLIND finding exactly as `just recover check` would.

    Only the git readings are stubbed, and they are stubbed with what this box's git
    actually answered for that watch's own window, vendored in `windows.json`. The worktree
    stub is the state each of these six was in when the by-hand look ran: gone, with no
    registration and no HEAD anywhere.
    """
    recorded = WINDOWS[name]
    window = tuple(recovery.Commit(sha, subject) for sha, subject in recorded["commits"])
    evidence = recovery.gather_check(
        name,
        repo=REPO,
        watch_dir=WATCH_CORPUS,
        dispatch_dir=DISPATCH_CORPUS,
        now=recorded["until"],
        read_window=lambda _repo, _start, _end: window,
        read_worktree=lambda path, _repo, **_readings: a_tree(path=path),
    )
    assert evidence is not None, f"{name} is vendored, so it must be found"
    return evidence, recovery.decide(evidence)


@pytest.mark.parametrize("name", [*RESEARCH_FOUR, *ASSESSOR_TWO])
def test_the_by_hand_verdicts_are_reproduced(name: str) -> None:
    """Criterion 1: all six resolved `finished_and_cleaned` by hand, and do so here."""
    _, verdict = replay(name)
    assert verdict.kind == recovery.FINISHED


@pytest.mark.parametrize("name", list(RESEARCH_FOUR))
def test_the_research_four_name_the_output_the_runbook_records(name: str) -> None:
    """The four SHAs `docs/agents/recovery.md` names must be in what the look prints."""
    evidence, verdict = replay(name)
    printed = recovery.render_check(evidence, verdict)
    for sha in RECORDED_SHAS:
        assert sha in printed
    assert "while this watch was live" in verdict.basis


@pytest.mark.parametrize(("name", "dispatch_id", "issue"), [
    ("review-227-zai", "d-20260805-221743-8957c3", 227),
    ("review-92-claude", "d-20260805-221747-a5056c", 92),
])  # fmt: skip
def test_the_two_assessors_are_cleared_by_their_dispatch_record(
    name: str, dispatch_id: str, issue: int
) -> None:
    """The stronger of the two clearing routes: a record about *this* agent, not a window."""
    evidence, verdict = replay(name)
    assert dispatch_id in verdict.basis
    assert f"#{issue}" in verdict.basis
    assert "result.json" in verdict.basis
    assert dispatch_id in recovery.render_check(evidence, verdict)


def test_the_vendored_windows_are_the_watchs_own_and_not_open_ended() -> None:
    """A window nobody bounds grows, and a growing window is a list of everything since."""
    for name in (*RESEARCH_FOUR, *ASSESSOR_TWO):
        watch = recovery.read_watch(name, WATCH_CORPUS)
        assert watch is not None
        assert watch.last_live() > watch.armed_at
        assert WINDOWS[name]["until"] == watch.last_live()


def test_a_watch_recording_neither_assessment_nor_ack_bounds_nothing() -> None:
    assert a_watch(assessed_at=0, acknowledged_at=0).last_live() == 0
    assert a_watch(assessed_at=0, acknowledged_at=77).last_live() == 77
    assert a_watch(assessed_at=55, acknowledged_at=77).last_live() == 55


# ------------------------------------------------------------------- reading the records


def test_a_watch_is_read_from_its_spec_and_its_finding_together() -> None:
    watch = recovery.read_watch("research-evals", WATCH_CORPUS)
    assert watch is not None
    assert watch.state == "watch_blind"
    assert watch.head == ""
    assert watch.baseline_head == "7fea7104879fa1f1deddb1084d4ef8b6885f56d1"
    assert watch.worktree.endswith("/.claude/worktrees/research-evals")
    assert watch.armed_at == 1785939036


def test_a_name_this_box_holds_nothing_for_reads_as_no_watch() -> None:
    assert recovery.read_watch("never-armed", WATCH_CORPUS) is None


def test_every_vendored_name_is_listed() -> None:
    assert set(recovery.watch_names(WATCH_CORPUS)) == {*RESEARCH_FOUR, *ASSESSOR_TWO}


def test_a_dispatch_record_is_read_with_whether_it_returned() -> None:
    records = {record.dispatch_id: record for record in recovery.read_dispatches(DISPATCH_CORPUS)}
    assert records["d-20260805-221743-8957c3"].issue == 227
    assert records["d-20260805-221743-8957c3"].finished is True
    assert records["d-20260805-221743-8957c3"].base_sha.startswith("a885306")


def test_a_dispatch_record_with_no_result_has_not_returned(tmp_path: Path) -> None:
    record = tmp_path / "d-2"
    record.mkdir()
    (record / "dispatch.json").write_text(
        json.dumps({"dispatch_id": "d-2", "issue": 5, "worktree": "/w"}), encoding="utf-8"
    )
    assert recovery.read_dispatches(tmp_path)[0].finished is False


def test_an_unreadable_record_is_skipped_rather_than_fatal(tmp_path: Path) -> None:
    """A half-written record is what a dying session leaves, and reading one is the job."""
    broken = tmp_path / "d-3"
    broken.mkdir()
    (broken / "dispatch.json").write_text("{ not json", encoding="utf-8")
    assert recovery.read_dispatches(tmp_path) == ()


def test_a_lock_is_read_and_never_acquired(tmp_path: Path) -> None:
    (tmp_path / "1.lock").write_text("", encoding="utf-8")
    (tmp_path / "1.lock.info").write_text(
        "pid=424242\nslot=1\nstarted_at=2026-08-05T11:40:36Z\n", encoding="utf-8"
    )
    dead = recovery.lock_holders(tmp_path, alive=lambda _pid: False)
    assert "slot=1" in dead[0]
    assert "pid=424242" in dead[0]
    assert "process gone — stale metadata" in dead[0]
    assert "process still alive" in recovery.lock_holders(tmp_path, alive=lambda _pid: True)[0]


def test_evidence_with_a_verdict_is_not_listed_as_stale(tmp_path: Path) -> None:
    """ADR-0022 is about evidence with no verdict; a run that wrote one is a result."""
    for name, files in (("done", ("verdict.json",)), ("pooled", ("pool.json",)), ("half", ())):
        run = tmp_path / name
        run.mkdir()
        for file in files:
            (run / file).write_text("{}", encoding="utf-8")
    listed = recovery.evidence_without_verdict(tmp_path, 0)
    assert [Path(path).name for path in listed] == ["half"]


def test_evidence_older_than_the_window_is_not_the_dead_agents(tmp_path: Path) -> None:
    run = tmp_path / "old"
    run.mkdir()
    assert recovery.evidence_without_verdict(tmp_path, 2**40) == ()


def test_issues_are_split_by_when_the_tracker_says_they_moved() -> None:
    rows = [
        {"number": 1, "title": "opened inside", "createdAt": "2026-08-05T12:00:00Z"},
        {"number": 2, "title": "closed inside", "createdAt": "2026-01-01T00:00:00Z",
         "closedAt": "2026-08-05T13:00:00Z"},
        {"number": 3, "title": "opened after", "createdAt": "2026-09-05T12:00:00Z"},
    ]  # fmt: skip
    start = recovery._epoch("2026-08-05T00:00:00Z")  # noqa: SLF001 — this module's own helper
    end = recovery._epoch("2026-08-06T00:00:00Z")  # noqa: SLF001
    opened, closed = recovery.issues_in_window(rows, start, end)
    assert opened == ("#1 opened inside",)
    assert closed == ("#2 closed inside",)


def test_an_unreadable_instant_dates_nothing() -> None:
    assert recovery._epoch(None) == 0  # noqa: SLF001
    assert recovery._epoch("not a time") == 0  # noqa: SLF001


# ---------------------------------------------------------------- the reference commit


def test_the_reference_is_the_agents_own_head_when_one_reads() -> None:
    since, source = recovery.reference_commit(
        a_tree(present=True, head="e" * 40, head_source=recovery.FROM_WORKTREE), a_watch(), ()
    )
    assert since == "e" * 40
    assert "last commit" in source


def test_the_reference_falls_back_to_the_dispatch_base_then_the_watch_baseline() -> None:
    on_dispatch = recovery.reference_commit(a_tree(), a_watch(), (a_dispatch(),))
    assert on_dispatch[0] == "a" * 40
    assert "d-1" in on_dispatch[1]
    on_watch = recovery.reference_commit(a_tree(), a_watch(), ())
    assert on_watch[0] == "b" * 40
    assert "baseline" in on_watch[1]


def test_an_unresolvable_reference_says_so_rather_than_defaulting_to_main() -> None:
    """A window defaulted to origin/main prints "nothing moved", which is a false comfort."""
    since, source = recovery.reference_commit(a_tree(), None, ())
    assert since == ""
    assert "unresolvable" in source


# --------------------------------------------------------------------- against real git


def git(*args: str, cwd: Path) -> str:
    """Run git in the arrangement, failing the test on git's own error."""
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def a_repo(tmp_path: Path) -> Path:
    """Return a checkout with an `origin` carrying one commit on `main`."""
    origin = tmp_path / "origin.git"
    git("init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    repo = tmp_path / "repo"
    git("clone", "-q", str(origin), str(repo), cwd=tmp_path)
    for key, value in (
        ("user.email", "agent@example.invalid"),
        ("user.name", "Agent"),
        ("commit.gpgsign", "false"),
    ):
        git("config", key, value, cwd=repo)
    git("checkout", "-q", "-b", "main", cwd=repo)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git("add", "README.md", cwd=repo)
    git("commit", "-q", "-m", "base", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    return repo


def a_worktree(repo: Path, name: str) -> Path:
    """Add a worktree the way `just worktree add` does: off `origin/main`, detached."""
    path = repo / ".claude" / "worktrees" / name
    git("worktree", "add", "-q", "--detach", str(path), "origin/main", cwd=repo)
    return path


def commit_in(tree: Path, filename: str, message: str) -> None:
    """Make one commit in a worktree."""
    (tree / filename).write_text("work\n", encoding="utf-8")
    git("add", filename, cwd=tree)
    git("commit", "-q", "-m", message, cwd=tree)


def check_output(
    repo: Path, watch_dir: Path, dispatch_dir: Path, name: str, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    """Run `check` as the recipe runs it and return its exit code and everything it printed."""
    code = recovery.main(
        [
            "--repo", str(repo), "--watch-dir", str(watch_dir),
            "--dispatch-dir", str(dispatch_dir), "check", name,
        ]
    )  # fmt: skip
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_a_tree_with_unlanded_commits_names_both_the_commits_and_the_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criterion 2, against real git rather than against strings this file invented."""
    repo = a_repo(tmp_path)
    tree = a_worktree(repo, "issue-1")
    commit_in(tree, "one.txt", "feat: the first thing")
    commit_in(tree, "two.txt", "fix: the second thing")
    (tree / "scratch.txt").write_text("not committed\n", encoding="utf-8")

    code, printed = check_output(
        repo, tmp_path / "watch", tmp_path / "dispatches", "issue-1", capsys
    )

    assert code == 0
    assert "verdict=lost_work" in printed
    assert "2 commit(s)" in printed
    assert "feat: the first thing" in printed
    assert "fix: the second thing" in printed
    assert "one.txt" in printed
    assert "two.txt" in printed
    assert "uncommitted=1" in printed
    assert "scratch.txt" in printed
    assert "work_at_risk=" in printed


def test_a_tree_whose_work_is_on_main_reads_as_live_with_nothing_ahead(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = a_repo(tmp_path)
    a_worktree(repo, "issue-2")
    code, printed = check_output(
        repo, tmp_path / "watch", tmp_path / "dispatches", "issue-2", capsys
    )
    assert code == 0
    assert "verdict=still_live" in printed
    assert "commits_not_on_origin_main=0" in printed
    assert "head.on_origin_main=yes" in printed


def test_a_removed_tree_whose_registration_still_holds_its_head_is_read_from_it(
    tmp_path: Path,
) -> None:
    """The second of three HEAD sources: git's registration outlives the directory."""
    repo = a_repo(tmp_path)
    tree = a_worktree(repo, "issue-3")
    commit_in(tree, "one.txt", "feat: unlanded")
    head = git("rev-parse", "HEAD", cwd=tree).strip()
    for path in sorted(tree.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    tree.rmdir()

    state = recovery.read_tree(tree, repo, registered_head=head)
    assert state.present is False
    assert state.head == head
    assert state.head_source == recovery.FROM_REGISTRATION
    assert state.on_main == "no"
    assert recovery.decide(evidence_of(state)).kind == recovery.LOST


def test_a_head_no_object_backs_is_unknown_rather_than_unlanded(tmp_path: Path) -> None:
    repo = a_repo(tmp_path)
    state = recovery.read_tree(repo / "gone", repo, finding_head="0" * 40)
    assert state.head_source == recovery.FROM_FINDING
    assert state.on_main == "unknown"
    assert state.ahead == ()


def test_the_main_checkout_answers_for_a_look_run_from_inside_a_worktree(
    tmp_path: Path,
) -> None:
    """`issue-1` from inside a worktree must be the sibling, not a path under this tree."""
    repo = a_repo(tmp_path)
    tree = a_worktree(repo, "issue-4")
    assert recovery.main_checkout(tree) == repo.resolve()


def test_a_name_nothing_knows_is_refused_rather_than_reported_unproven(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A silent empty answer to a mistyped name reads as "nothing is wrong there"."""
    repo = a_repo(tmp_path)
    code, printed = check_output(repo, WATCH_CORPUS, tmp_path / "dispatches", "typo", capsys)
    assert code == 1
    assert "Nothing was looked at" in printed
    assert "research-evals" in printed


# -------------------------------------------------------------------- what check must not do


def snapshot(directory: Path) -> dict[str, tuple[int, bytes]]:
    """Every file under a directory, with its mtime and its bytes."""
    return {
        str(path.relative_to(directory)): (path.stat().st_mtime_ns, path.read_bytes())
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_check_acks_nothing_and_writes_nothing_to_the_watch_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Criterion 3. `just watch-report --ack` stays the judgement (ADR-0053)."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    for source in sorted(WATCH_CORPUS.iterdir()):
        (watch_dir / source.name).write_bytes(source.read_bytes())
    before = snapshot(watch_dir)

    for name in (*RESEARCH_FOUR, *ASSESSOR_TWO):
        code, _ = check_output(REPO, watch_dir, DISPATCH_CORPUS, name, capsys)
        assert code == 0

    assert snapshot(watch_dir) == before


def test_the_watch_directory_comes_from_the_environment_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`CTI_WATCH_DIR` (#249): a test must never read what the live box is carrying."""
    monkeypatch.setenv("CTI_WATCH_DIR", str(tmp_path / "elsewhere"))
    assert recovery.parse_args(["check", "x"]).watch_dir == tmp_path / "elsewhere"


# ------------------------------------------------------------------------- the briefing


def a_resumption(**fields: object) -> recovery.Resumption:
    """Build a `Resumption` in one line, with the reading under test varied."""
    moved = recovery.Moved(
        since="a" * 40,
        since_source="the agent's last commit, read from the worktree",
        commits=(recovery.Commit("abc1234", "feat: something"),),
        adrs=("docs/adr/0066-a-thing.md",),
        opened=("#300 a new issue",),
        closed=("#299 an old issue",),
        tracker="read",
    )
    environment = recovery.Environment(
        tree=a_tree(present=True, head="a" * 40, head_source=recovery.FROM_WORKTREE, on_main="yes"),
        watches=(a_watch(),),
        evidence_without_verdict=("/runs/20260806T0000Z-thing",),
        locks=("1.lock.info: slot=1 pid=1 started=? process gone — stale metadata",),
    )
    defaults: dict[str, object] = {
        "target": "253",
        "issue": 253,
        "moved": moved,
        "environment": environment,
        "handoff": recovery.Handoff(0, "Handoff-for: #253"),
    }
    return recovery.Resumption(**{**defaults, **fields})


def third_reconstruction(rendered: str) -> str:
    """Everything the briefing puts under reconstruction 3's heading."""
    after = rendered.split("## 3. Which of its assumptions no longer hold", 1)[1]
    return after.split("\n## ", 1)[0].strip()


def computed_half(rendered: str) -> str:
    """Everything this tool wrote, excluding the predecessor's own words."""
    return rendered.split("## The predecessor's own account", 1)[0]


@pytest.mark.parametrize(
    "varied",
    [
        {},
        {"issue": 0, "target": "research-evals", "handoff": recovery.Handoff(1, "[handoff] none")},
        {"environment": recovery.Environment(
            tree=a_tree(ahead=(recovery.Commit("dead123", "feat: never landed"),),
                        files=("addons/main/x.sqf",), head="dead123",
                        head_source=recovery.FROM_FINDING, on_main="no"),
            watches=(), evidence_without_verdict=(), locks=())},
        {"moved": recovery.Moved("", "unresolvable — no HEAD", (), (), (), (), "unread — no gh")},
    ],
)  # fmt: skip
def test_reconstruction_three_is_empty_and_no_input_fills_it(varied: dict[str, object]) -> None:
    """Criterion 4: the judgement half is a heading, whatever the readings say."""
    section = third_reconstruction(recovery.render_brief(a_resumption(**varied)))
    assert section == recovery.RECONSTRUCTION_THREE
    assert "judgement" in section


def test_a_clean_tree_zero_ahead_states_the_evidence_and_asserts_nothing_from_it(
    tmp_path: Path,
) -> None:
    """Criterion 5, and the 2026-08-02 error: "clean, zero ahead" meant landed, not lost.

    The briefing may say a commit is on `origin/main` or is not, because that is what git
    answered. Which of those the *work* is remains the resumed agent's to verify on wake, so
    neither word that would decide it for them appears anywhere this tool wrote.
    """
    repo = a_repo(tmp_path)
    tree = a_worktree(repo, "issue-5")
    resumption = recovery.gather_brief(
        "5",
        repo=repo,
        watch_dir=tmp_path / "watch",
        dispatch_dir=tmp_path / "dispatches",
        runs_dir=tmp_path / "runs",
        slot_dir=tmp_path / "slots",
        now=2**31,
        read_rows=list,
        read_handoff_for=lambda _issue: recovery.Handoff(0, "Handoff-for: #5"),
    )
    rendered = recovery.render_brief(resumption)
    computed = computed_half(rendered)

    assert resumption.environment.tree.path == tree
    assert "worktree.present=yes" in computed
    assert "uncommitted=0" in computed
    assert "commits_not_on_origin_main=0" in computed
    assert "head.on_origin_main=yes" in computed
    assert "landed" not in computed.lower()
    assert "lost" not in computed.lower()
    assert "uncommitted work" not in computed.lower()


def test_an_unresolvable_reference_computes_no_window_and_says_which(tmp_path: Path) -> None:
    repo = a_repo(tmp_path)
    resumption = recovery.gather_brief(
        "never-existed",
        repo=repo,
        watch_dir=tmp_path / "watch",
        dispatch_dir=tmp_path / "dispatches",
        runs_dir=tmp_path / "runs",
        slot_dir=tmp_path / "slots",
        now=2**31,
        read_rows=list,
        read_handoff_for=lambda _issue: recovery.Handoff(0, ""),
    )
    rendered = recovery.render_brief(resumption)
    assert resumption.moved.since == ""
    assert "commits=0" in rendered
    assert "unresolvable" in rendered
    assert "Nothing below could be computed" in rendered


def test_a_tracker_that_could_not_be_reached_reads_unread_not_empty(tmp_path: Path) -> None:
    """A check that could not run is not a check that passed (#41)."""
    repo = a_repo(tmp_path)

    def refuse() -> list[dict[str, object]]:
        message = "`gh` could not be reached"
        raise OSError(message)

    resumption = recovery.gather_brief(
        "6",
        repo=repo,
        watch_dir=tmp_path / "watch",
        dispatch_dir=tmp_path / "dispatches",
        runs_dir=tmp_path / "runs",
        slot_dir=tmp_path / "slots",
        now=2**31,
        read_rows=refuse,
        read_handoff_for=lambda _issue: recovery.Handoff(0, ""),
    )
    assert resumption.moved.tracker.startswith("unread — ")
    assert "tracker=unread" in recovery.render_brief(resumption)


# ---------------------------------------------------------------------- the handoff beside


def test_an_issue_with_no_handoff_carries_that_tools_own_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 6. The refusal is fetched from the tool that owns it, not re-worded here."""
    monkeypatch.setattr(handoff_fetch, "fetch_comments", lambda _issue: '"a comment"\n')
    monkeypatch.setattr(recovery.handoff_fetch, "fetch_comments", lambda _issue: '"a comment"\n')
    answer = recovery.read_handoff(7)
    assert answer.code == handoff_fetch.NO_HANDOFF
    assert "no handoff on #7" in answer.text
    assert "1 comment(s) scanned" in answer.text

    rendered = recovery.render_brief(a_resumption(issue=7, handoff=answer))
    assert "no handoff on #7" in rendered
    assert "exit=1" in rendered
    assert recovery.NO_HANDOFF_NOTE in rendered


def test_a_handoff_that_exists_is_printed_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    body = "Handoff-for: #7\n\nState: parked, gate green."
    monkeypatch.setattr(
        recovery.handoff_fetch, "fetch_comments", lambda _issue: json.dumps(body) + "\n"
    )
    answer = recovery.read_handoff(7)
    assert answer.code == 0
    assert answer.text == body
    assert body in recovery.render_brief(a_resumption(issue=7, handoff=answer))


def test_a_target_with_no_issue_looks_for_no_handoff() -> None:
    rendered = recovery.render_brief(a_resumption(issue=0, target="research-evals"))
    assert "No issue number resolves for this target" in rendered


# ------------------------------------------------------------------------------ rendering


def test_a_list_is_bounded_and_says_how_much_it_did_not_print() -> None:
    rows = [f"row {index}" for index in range(recovery.SHOWN + 3)]
    printed = recovery._bounded(rows)  # noqa: SLF001 — this module's own helper
    assert len(printed) == recovery.SHOWN + 1
    assert printed[-1].strip() == "... 3 more"


def test_the_check_output_carries_the_basis_and_the_readings_it_came_from() -> None:
    evidence, verdict = replay("research-evals")
    printed = recovery.render_check(evidence, verdict)
    assert printed.startswith("verdict=finished_and_cleaned\n")
    assert f"basis={verdict.basis}" in printed
    assert f"cannot_exclude={verdict.cannot_exclude}" in printed
    assert "worktree.present=no" in printed
    assert "head=unreadable (none)" in printed
    assert "acked nothing" in printed


def _no_missing_verbs(argv: Sequence[str]) -> None:
    """Assert that a parser with no verb refuses rather than defaulting to one."""
    with pytest.raises(SystemExit):
        recovery.parse_args(list(argv))


def test_a_verb_is_required() -> None:
    _no_missing_verbs([])
    _no_missing_verbs(["--repo", "."])
