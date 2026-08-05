"""The landing protocol as one call: rebase, gate, push, merge — or refuse by name (#213, ADR-0049).

Every landing narrates the same five steps — fetch, rebase onto `origin/main`,
re-gate, `git push origin HEAD:main`, `git -C <main checkout> merge --ff-only
origin/main`. #209 measured 220 `Bash` calls doing exactly that across 117 of
214 agents, the second-widest hand loop in the project.

The token case is real and secondary. The correctness case is that **a recipe
cannot forget a step, and prose demonstrably does**:

- CLAUDE.md spells the refspec `HEAD:main` because agents kept typing `git push
  origin main`, which pushes the local `main` branch — which a detached worktree
  is not on — and is rejected as non-fast-forward. Here the refspec is a
  constant (`PUSH_REFSPEC`) and no argument reaches it, so that trap is refused
  by construction rather than by remembering.
- The `merge --ff-only` step into the main checkout is the one that gets
  skipped, and a stale main checkout is where ADR-0042's stale-hook window comes
  from (#130; #120's fourth false positive fired inside it).
- CLAUDE.md already says a sandbox-blocked merge must be handed to the
  orchestrator, "never skip it silently" — until now a prose obligation with no
  mechanism behind it, so the failure mode was silence. It is now
  `merge_blocked_by_sandbox`: a non-zero exit whose own line, `merge_command=`,
  is the exact command the orchestrator must run.

**The gate is inside the protocol, not beside it.** `just fast` runs after the
rebase, unconditionally, on every landing that pushes anything. There is no flag
that skips it and there is deliberately no heuristic that decides it is
unnecessary: "our surfaces were disjoint" is a judgement about *other* agents'
commits which this tool cannot verify, and encoding it would be a gate bypass
wearing a convenience wrapper. What the tool does instead is report the movement
honestly — `rebase=replayed onto N new commits` or `rebase=already_current` — so
the reader can see what the gate covered. The gate's output is not captured at
all: it streams to the caller, so `gate_red` hands back the gate's own words
rather than this tool's summary of them.

Refusals are this recipe's own vocabulary, not the harness failure-class table:
a landing is not a corpus verdict and must not borrow its class names. What it
borrows is the discipline — a named, actionable refusal rather than an opaque
exit code.

    dirty_tree              uncommitted or untracked files here (#105's
                            pre-flight condition), refused before anything runs
    nothing_to_land         clean, level with origin/main, main checkout already
                            carries it: nothing was landed and nothing was owed
    rebase_conflict         stop and hand back. The rebase is left in progress —
                            nothing here resolves or aborts on your behalf
    conflict_markers        the rebased tree carries git conflict markers, named
                            by file and line (#231, ADR-0062)
    gate_red                `just fast` failed; its own output is above
    gate_blocked            the gate could not be run to completion. A check
                            that could not run is not a check that passed (#41)
    not_fast_forward        the remote moved under the push
    merge_blocked_by_sandbox    the push landed, the ff-only merge did not run
    merge_not_fast_forward      the push landed, the main checkout cannot
                            fast-forward — it carries commits of its own
    git_failed              any other git step, with git's own words

Exit 0 is landed. Exit 1 is "nothing landed". Exit 2 is the pair above it: the
work **is** on `origin/main` and a step is outstanding — a distinction an
orchestrator can act on without parsing prose, and never a success exit (#213's
criterion 4).

Nothing here resets, cleans or aborts on a refusal path, for `tools/worktree.py`'s
reason: on a shared tree the files are evidence, and the judgement of what a
refusal means stays the agent's.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a
# sibling import needs the script's own directory on the path — the same device
# `timeline.py` uses to reach `telemetry_log`. Placed before the import it
# enables, which is why the import below sits apart from the block above.
sys.path.insert(0, str(Path(__file__).parent))

from check_conflict_markers import Finding, find_in_tree
from worktree import BASE, GitError, Preflight, Refusal, git, main_checkout, read_status

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    # What `land` calls to run the gate. A parameter rather than an environment
    # variable or a flag on purpose: tests substitute it, and nothing on argv or
    # in the environment can. `just land --no-gate` is the thing #213 asks not
    # to exist, and there is no seam here for one to grow out of.
    Gate = Callable[[Path], "GateResult"]

# The refspec, as a constant nothing parameterises. `git push origin main` from
# a detached worktree pushes the local `main` branch, not HEAD, and CLAUDE.md
# documents `HEAD:main` because agents kept typing the other one.
PUSH_REFSPEC: Final = "HEAD:main"
REMOTE: Final = "origin"
GATE: Final = ("just", "fast")

# Generous against a gate measured at about 1:02 since #197. A bound, not an
# expectation: an unbounded `uv run` is what #144 was about.
GATE_TIMEOUT_S: Final = 1800

EXIT_REFUSED: Final = 1
# The work is on origin/main; a step after the push is outstanding. Separated
# from 1 so "nothing landed" and "landed, merge owed" are not one exit code.
EXIT_LANDED_INCOMPLETE: Final = 2

HOW_MANY_SHOWN: Final = 10

# git's own words when a push loses a race, across its several phrasings.
REJECTED_MARKERS: Final = ("non-fast-forward", "fetch first", "stale info", "[rejected]")
# git's words when the main checkout has diverged rather than merely lagged.
NOT_FF_MARKERS: Final = ("not possible to fast-forward", "refusing to merge unrelated histories")


class GateResult(NamedTuple):
    """What running the gate produced: an exit code, or `None` if it never finished."""

    code: int | None
    detail: str


class Report(NamedTuple):
    """One landing's whole answer: the lines to print and the exit code they carry."""

    lines: tuple[str, ...]
    code: int

    @classmethod
    def refused(cls, refusal: Refusal, code: int = EXIT_REFUSED) -> Report:
        """Render a refusal. The default code is 'nothing landed'."""
        return cls(refusal.lines(), code)


# --------------------------------------------------------------------- ladders


def classify_tree(path: Path, status: Preflight, *, rebasing: bool) -> Refusal | None:
    """Refuse a tree that is not ready to be landed from, before anything runs.

    Both halves of CLAUDE.md's pre-flight refuse: uncommitted tracked changes are
    work a rebase would drag through or drop, and untracked files are #105's
    condition — your file and another agent's look identical in `git status`, so
    a landing must not rebase over them and must not tidy them away.
    """
    if rebasing:
        return Refusal(
            "rebase_conflict",
            (f"worktree={path}", "rebase=already in progress here"),
            "A rebase is already under way in this tree. Finish it — resolve and "
            "`git rebase --continue`, or `git rebase --abort` — then run `just land` again. "
            "Nothing here continues or aborts one for you.",
        )
    if status.clean:
        return None
    return Refusal(
        "dirty_tree",
        _found(path, status),
        "Commit your work before landing it: a rebase over uncommitted changes is how they "
        "get lost. Anything in that list you did not write means another agent is in this "
        "tree — stop and report, never reset (#105).",
    )


def _found(path: Path, status: Preflight) -> tuple[str, ...]:
    """List the files themselves, capped: a count is not something to judge on."""
    found = [f"worktree={path}"]
    found += [f"tracked={line}" for line in status.tracked[:HOW_MANY_SHOWN]]
    found += [f"untracked={line}" for line in status.untracked[:HOW_MANY_SHOWN]]
    shown = min(len(status.tracked), HOW_MANY_SHOWN) + min(len(status.untracked), HOW_MANY_SHOWN)
    total = len(status.tracked) + len(status.untracked)
    if total > shown:
        found.append(f"and={total - shown} more")
    return tuple(found)


def classify_nothing_to_land(path: Path, ahead: int, main_behind: int | None) -> Refusal | None:
    """Refuse a landing that would push nothing and owe nothing.

    Only when both are true: this tree is level with `origin/main` *and* the main
    checkout already carries it. A tree with nothing to push but a stale main
    checkout is not this — that is the re-run after `merge_blocked_by_sandbox`,
    and it has a merge to finish.
    """
    if ahead or main_behind is None or main_behind:
        return None
    return Refusal(
        "nothing_to_land",
        (f"worktree={path}", f"ahead=0 commits over {BASE}", "main_checkout=already current"),
        "Nothing was landed, because there was nothing to land: this tree carries no commit "
        f"{BASE} does not already have. If you meant to land work, check you committed it "
        "(`git log --oneline origin/main..HEAD`).",
    )


def classify_rebase(
    path: Path, code: int, conflicted: tuple[str, ...], stderr: str
) -> Refusal | None:
    """Refuse a rebase that stopped, naming what conflicted and both ways out.

    The rebase is deliberately left in progress. Aborting for the caller would
    discard whatever git already merged cleanly, and `tools/worktree.py`'s rule
    holds here too: a recipe that tidies on a refusal path is a recipe that
    destroys work. Both continuations are named because a tree left mid-rebase
    is a state an agent must be told how to leave.
    """
    if code == 0:
        return None
    if not conflicted:
        return Refusal(
            "git_failed",
            (f"worktree={path}", f"command=git rebase {BASE}", f"stderr={stderr.strip()}"),
            "The rebase failed without leaving conflicts to resolve. Read git's words above; "
            "`git rebase --abort` if a rebase is still in progress.",
        )
    return Refusal(
        "rebase_conflict",
        (f"worktree={path}", *[f"conflict={name}" for name in conflicted[:HOW_MANY_SHOWN]]),
        "Resolve them, `git rebase --continue`, then run `just land` again — or "
        "`git rebase --abort` to leave this tree as it was. CHANGELOG.md is the only "
        "conflict 264 landings have produced; take both entries, keep both.",
    )


def classify_conflict_markers(path: Path, findings: Sequence[Finding]) -> Refusal | None:
    """Refuse a rebased tree carrying git conflict markers, naming each one (#231).

    Judged on the tree *after* the rebase, which is the tree that would be
    pushed — so a marker inherited from `origin/main` refuses this landing too,
    and deliberately: #231's mechanism is that a marker in the base poisons the
    next resolution, and the next resolution is what this rung is standing in
    front of. The only landing it lets through is the one that removes it.

    `just check` runs the same checker, so the coverage here is not new; what is
    new is that it arrives **as a named refusal, before the gate's minute**,
    rather than as a `gate_red` the reader has to scroll for.
    """
    if not findings:
        return None
    named = [f"marker={finding}" for finding in findings[:HOW_MANY_SHOWN]]
    if len(findings) > HOW_MANY_SHOWN:
        named.append(f"and={len(findings) - HOW_MANY_SHOWN} more")
    return Refusal(
        "conflict_markers",
        (f"worktree={path}", *named),
        "Delete every marker line and commit the resolution, then run `just land` again. "
        "Nothing was pushed. A marker that reaches the base is not untidiness — the next "
        "agent's rebase resolves against it, which is how 1,669 changelog lines were lost "
        "between 2b4f99b and 5a966f3 (#231).",
    )


def classify_gate(path: Path, result: GateResult) -> Refusal | None:
    """Refuse on a red gate, and separately on a gate that never reached a verdict.

    Two classes rather than one, for #41's reason and #83's: a check that could
    not run is not a check that passed, and folding "the tests failed" together
    with "the gate never finished" would be exactly the untyped red those two
    issues are about. The required responses differ — fix the code, against fix
    the environment.
    """
    if result.code == 0:
        return None
    if result.code is None:
        return Refusal(
            "gate_blocked",
            (f"worktree={path}", f"gate={' '.join(GATE)}", f"detail={result.detail}"),
            "The gate did not reach a verdict, so nothing was pushed. A check that could not "
            "run is not a check that passed (#41). Fix the environment and run `just land` again.",
        )
    return Refusal(
        "gate_red",
        (f"worktree={path}", f"gate={' '.join(GATE)}", f"exit={result.code}"),
        "The gate's own output is above, unabridged — nothing was captured or summarised. "
        "Fix what it names and run `just land` again. Nothing was pushed.",
    )


def classify_push(code: int, stderr: str) -> Refusal | None:
    """Tell a lost race from any other push failure."""
    if code == 0:
        return None
    lowered = stderr.lower()
    if any(marker in lowered for marker in REJECTED_MARKERS):
        return Refusal(
            "not_fast_forward",
            (f"command=git push {REMOTE} {PUSH_REFSPEC}", f"stderr={stderr.strip()}"),
            f"{BASE} moved under the push — another agent landed first. Run `just land` again: "
            "it fetches, rebases onto the new tip and re-gates before pushing.",
        )
    return Refusal(
        "git_failed",
        (f"command=git push {REMOTE} {PUSH_REFSPEC}", f"stderr={stderr.strip()}"),
        "The push failed for a reason that is not a lost race. Read git's words above. "
        "Nothing was landed.",
    )


def merge_argv(main: Path) -> list[str]:
    """Return the exact ff-only merge, as one argv — the command a refusal has to name."""
    return ["git", "-C", str(main), "merge", "--ff-only", BASE]


def push_argv() -> list[str]:
    """Return the exact push. `HEAD:main`, from a constant, with nothing parameterised."""
    return ["git", "push", REMOTE, PUSH_REFSPEC]


def classify_merge(main: Path, pushed: str, code: int | None, stderr: str) -> Refusal | None:
    """Classify the ff-only merge into the main checkout, after the push has landed.

    Both refusals here carry exit 2, never 0 and never 1: the work is on
    `origin/main`, so calling this a failed landing would be as wrong as calling
    it a finished one. `merge_command=` is the line an orchestrator greps —
    CLAUDE.md's "hand it to the orchestrator" with a mechanism behind it at last.
    """
    if code == 0:
        return None
    named = f"merge_command={' '.join(merge_argv(main))}"
    lowered = stderr.lower()
    if code is not None and any(marker in lowered for marker in NOT_FF_MARKERS):
        return Refusal(
            "merge_not_fast_forward",
            (f"pushed={pushed} {BASE}", f"main_checkout={main}", named, f"stderr={stderr.strip()}"),
            "THE WORK IS LANDED on origin/main; the main checkout is stale and cannot simply "
            "fast-forward, because it carries commits of its own. Someone must reconcile it by "
            "hand — a stale main checkout is where ADR-0042's stale-hook window comes from (#130).",
        )
    return Refusal(
        "merge_blocked_by_sandbox",
        (f"pushed={pushed} {BASE}", f"main_checkout={main}", named, f"detail={stderr.strip()}"),
        "THE WORK IS LANDED on origin/main; the merge into the main checkout did not run. "
        "Hand the command above to the orchestrator and say so in your report — do not report "
        "this landing as complete. A stale main checkout is where ADR-0042's stale-hook window "
        "comes from (#130), and it is why this is not a success exit.",
    )


# ------------------------------------------------------------------ git access


def rebase_in_progress(path: Path) -> bool:
    """Report whether this worktree is sitting mid-rebase."""
    for kind in ("rebase-merge", "rebase-apply"):
        where = git("rev-parse", "--git-path", kind, cwd=path, check=False).strip()
        if where and (path / where).exists():
            return True
    return False


def conflicted_paths(path: Path) -> tuple[str, ...]:
    """Return the unmerged paths a stopped rebase left, in git's own order."""
    listed = git("diff", "--name-only", "--diff-filter=U", cwd=path, check=False)
    return tuple(line.strip() for line in listed.splitlines() if line.strip())


def counted(*args: str, cwd: Path) -> int | None:
    """`git rev-list --count` as an int, or `None` when it could not be read."""
    out = git("rev-list", "--count", *args, cwd=cwd, check=False).strip()
    return int(out) if out.isdigit() else None


def run_gate(path: Path) -> GateResult:
    """Run `just fast` in the landing worktree, streaming its output to the caller.

    Nothing is captured. That is the whole of `gate_red`'s "verbatim, not a
    summary": what the caller reads is the gate writing to the caller's own
    streams, and there is no place in this function for a summary to be made.
    """
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv, no shell, no interpolation
            list(GATE),
            cwd=path,
            check=False,
            timeout=GATE_TIMEOUT_S,
        )
    except FileNotFoundError:
        return GateResult(None, f"{GATE[0]} is not on PATH")
    except subprocess.TimeoutExpired:
        return GateResult(None, f"killed at the {GATE_TIMEOUT_S}s bound without a verdict")
    return GateResult(done.returncode, "")


def _run(argv: list[str], cwd: Path) -> tuple[int | None, str]:
    """Run one argv, returning its exit code and stderr — `None` when it never ran.

    `None` and a reason rather than an exception, because "the command could not
    be run at all" is the sandbox-blocked shape and it has to reach a classifier
    as a value.
    """
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv built from constants and computed paths
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=GATE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as blocked:
        return None, f"{type(blocked).__name__}: {blocked}"
    return done.returncode, done.stderr


# ---------------------------------------------------------------------- the run


def _describe(path: Path) -> str:
    """`<short sha> <subject>` for this tree's HEAD."""
    return git("log", "-1", "--format=%h %s", cwd=path, check=False).strip()


def _merge_needed(here: Path, main: Path) -> bool:
    """Whether the ff-only merge has anything to do.

    Landing from the main checkout while it is on `main` already moved it: the
    push updated `origin/main` from the branch the checkout is on. Any other
    arrangement — a linked worktree, or a detached main checkout — needs it.
    """
    if here != main:
        return True
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=main, check=False).strip()
    return branch != "main"


def land(root: Path, here: Path, *, gate: Gate = run_gate, dry_run: bool = False) -> Report:
    """Run the whole protocol, or refuse by name at the first rung that says no."""
    status = read_status(git("status", "--porcelain", cwd=here))
    blocked = classify_tree(here, status, rebasing=rebase_in_progress(here))
    if blocked is not None:
        return Report.refused(blocked)

    git("fetch", REMOTE, cwd=here)
    base_before = git("merge-base", "HEAD", BASE, cwd=here).strip()
    incoming = counted(f"{base_before}..{BASE}", cwd=here) or 0
    ahead = counted(f"{BASE}..HEAD", cwd=here)
    if ahead is None:
        message = f"rev-list --count {BASE}..HEAD"
        raise GitError(("rev-list",), message)

    main_behind = counted(f"HEAD..{BASE}", cwd=root) if _merge_needed(here, root) else 0
    idle = classify_nothing_to_land(here, ahead, main_behind)
    if idle is not None:
        return Report.refused(idle)

    if dry_run:
        return _dry_run(root, here, ahead, incoming)

    lines = [f"worktree={here}", f"commits={ahead}"]
    if ahead:
        moved = _rebase_and_gate(here, incoming, gate, lines)
        if moved is not None:
            return moved
    else:
        # Nothing to push: this is the re-run after a blocked merge. The gate is
        # not skipped by a flag — there is simply nothing new being landed, and
        # the outstanding step is the merge the last run could not make.
        lines += ["rebase=not_attempted", "gate=not_run reason=nothing_to_push"]

    pushed = _push(here, ahead, lines)
    if isinstance(pushed, Report):
        return pushed
    return _merge(root, here, pushed, lines)


def _rebase_and_gate(here: Path, incoming: int, gate: Gate, lines: list[str]) -> Report | None:
    """Rebase onto `origin/main`, then gate the result. Either may refuse."""
    code, stderr = _run(["git", "rebase", BASE], cwd=here)
    if code is None:
        return Report.refused(
            Refusal(
                "git_failed",
                (f"worktree={here}", f"command=git rebase {BASE}", f"detail={stderr}"),
                "The rebase could not be run at all. Nothing was pushed.",
            )
        )
    stopped = classify_rebase(here, code, conflicted_paths(here), stderr)
    if stopped is not None:
        return Report.refused(stopped)
    lines.append(
        f"rebase=replayed onto {incoming} new commits" if incoming else "rebase=already_current"
    )

    poisoned = classify_conflict_markers(here, find_in_tree(here))
    if poisoned is not None:
        return Report.refused(poisoned)

    red = classify_gate(here, gate(here))
    if red is not None:
        return Report.refused(red)
    lines.append(f"gate=green ({' '.join(GATE)})")
    return None


def _push(here: Path, ahead: int, lines: list[str]) -> Report | str:
    """Push, or refuse. Returns the landed short SHA on success."""
    if not ahead:
        lines.append("push=not_needed reason=already_on_origin/main")
        return git("rev-parse", "--short", "HEAD", cwd=here).strip()
    code, stderr = _run(push_argv(), cwd=here)
    if code is None:
        return Report.refused(
            Refusal(
                "git_failed",
                (f"command=git push {REMOTE} {PUSH_REFSPEC}", f"detail={stderr}"),
                "The push could not be run at all. Nothing was landed.",
            )
        )
    lost = classify_push(code, stderr)
    if lost is not None:
        return Report.refused(lost)
    pushed = git("rev-parse", "--short", "HEAD", cwd=here).strip()
    lines.append(f"pushed={pushed} {BASE}")
    return pushed


def _merge(root: Path, here: Path, pushed: str, lines: list[str]) -> Report:
    """Fast-forward the main checkout, and make a merge that did not run loud."""
    if not _merge_needed(here, root):
        lines.append(f"merge=not_needed reason=landed_from_the_main_checkout ({root})")
        return Report((("ok=landed"), *lines), 0)
    code, stderr = _run(merge_argv(root), cwd=root)
    outstanding = classify_merge(root, pushed, code, stderr)
    if outstanding is not None:
        return Report.refused(outstanding, EXIT_LANDED_INCOMPLETE)
    lines.append(f"merge=fast-forwarded {root} to {pushed}")
    return Report((("ok=landed"), *lines), 0)


def _dry_run(root: Path, here: Path, ahead: int, incoming: int) -> Report:
    """Print the plan and change nothing. Not a landing, and it says so."""
    plan = [
        f"git rebase {BASE}",
        " ".join(GATE),
        " ".join(push_argv()),
        " ".join(merge_argv(root)) if _merge_needed(here, root) else "(merge not needed)",
    ]
    return Report(
        (
            "ok=dry_run",
            "landed=no",
            f"worktree={here}",
            f"main_checkout={root}",
            f"head={_describe(here)}",
            f"commits={ahead}",
            f"incoming={incoming} new commits on {BASE}",
            *[f"would_run={step}" for step in plan],
            "This ran nothing. `just land` runs it, gate included.",
        ),
        0,
    )


# ------------------------------------------------------------------ invocation


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """One optional flag, and deliberately no others.

    There is no `--no-gate`, no `--force`, and no way to name the refspec or the
    remote: those are #213's criterion 2 and the `git push origin main` trap,
    and the surface that cannot express them is the mechanism.
    """
    parser = argparse.ArgumentParser(prog="just land", description="Land this worktree on main.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and run nothing at all",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the protocol, print what happened, and exit what it decided."""
    args = parse_args(argv)
    try:
        here = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()).strip()).resolve()
        root = main_checkout(here).resolve()
        report = land(root, here, dry_run=args.dry_run)
    except GitError as failure:
        report = Report.refused(
            Refusal(
                "git_failed",
                (f"command=git {' '.join(failure.args_run)}", f"stderr={failure.stderr}"),
                "Read git's own error above. Check what actually happened with "
                "`git log --oneline origin/main..HEAD` before running anything else.",
            )
        )
    stream = sys.stdout if report.code == 0 else sys.stderr
    for line in report.lines:
        print(line, file=stream)
    return report.code


if __name__ == "__main__":
    sys.exit(main())
