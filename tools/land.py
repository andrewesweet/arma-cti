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

**The second gate is the corpus, and it runs after the first** (#302,
`tools/corpus_gate.py`). A landing whose real diff reaches an in-world surface
owes `just regress`, full corpus and no filter, and until now nothing read that
obligation at landing time — `85dfb1b` landed 181 changed lines of the daemon's
transport with no corpus run and was found three landings later. `--corpus`
names the evidence and skips nothing: every claim it makes is checked against
the pool's own record, so pointing it at the wrong run refuses. It sits *after*
`just fast` deliberately, because the corpus costs a slot of the Arma tier and
twenty minutes of it, and nobody should be sent there over a tree that fails
ruff.

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
    routing_policy_gate     a non-exempt lane's real rebased diff touches a
                            class the trusted policy keeps on Claude (#266)
    routing_policy_gate_unreadable / routing_policy_diff_unreadable
                            the enforcing routing check could not run; fail closed
    gate_red                `just fast` failed; its own output is above
    gate_blocked            the gate could not be run to completion. A check
                            that could not run is not a check that passed (#41)
    corpus_owed             the diff reaches an in-world surface and no passing
                            full-corpus run over this tree was named (#302)
    corpus_not_pass         one was, and its worst class is not `pass`
    corpus_check_unreadable the corpus rung could not run; fail closed
    not_fast_forward        the remote moved under the push
    merge_blocked_by_sandbox    the push landed, the ff-only merge did not run
    merge_not_fast_forward      the push landed, the main checkout cannot
                            fast-forward — it carries commits of its own
    git_failed              any other git step, with git's own words

Exit 0 is landed. Exit 1 is "nothing landed". Exit 2 is the pair above it: the
work **is** on `origin/main` and a step is outstanding — a distinction an
orchestrator can act on without parsing prose, and never a success exit (#213's
criterion 4). A `--dry-run` lands nothing whatever it finds, so its exit carries its
verdict instead: 0 where no rung it could consult refused, 1 for **any** refusal, the
routing gate's included. A plan that decides something needs a machine channel for the
decision (#344). Any, and not only routing's: `dirty_tree`, `nothing_to_land` and
`git_failed` are all decided before the dry-run branch and all exit 1 too, so a caller
keying 1 to "routing refused" would read a dirty tree as a routing verdict (review
round 2 claim 5). The body names which one; the code says only that one fired. A dry
run's **whole output** is on stdout, refusals included, for the same reason: it lands
nothing, so it has no error output to separate, and its exit being non-zero exactly
when it has the most to say is what emptied stdout in the case #344 was filed about.

Nothing here resets, cleans or aborts on a refusal path, for `tools/worktree.py`'s
reason: on a shared tree the files are evidence, and the judgement of what a
refusal means stays the agent's.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a
# sibling import needs the script's own directory on the path — the same device
# `timeline.py` uses to reach `telemetry_log`. Placed before the import it
# enables, which is why the import below sits apart from the block above.
sys.path.insert(0, str(Path(__file__).parent))

import corpus_gate
import routing_policy
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

# The lane the routing gate never judges, as one literal in this module. The trusted
# policy carries its own name for it (`claude_lane`) and `_exempt_lane` prefers that;
# this is what remains when the policy could not be read at all, and it is the default
# every entry point here uses.
CLAUDE_LANE: Final = "claude-native"

# The rungs `--dry-run` genuinely cannot consult, because each needs the tree the
# rebase produces or a command the dry run refuses to run. Named in the output so a
# plan's silence is not read as a clearance it never gave (#344). Two lists, because
# the plan mirrors the landing's own control flow: a tree with nothing to push reaches
# neither the rebase nor the gate, and naming rungs that will not run would be the same
# defect pointing the other way.
NOT_CHECKED: Final = (
    "the rebase itself, conflict markers in the rebased tree, `just fast`, the push race, "
    "whether the push and the ff-only merge can be run at all, and whether the main "
    "checkout carries commits of its own"
)
NOT_CHECKED_MERGE_ONLY: Final = (
    "whether the ff-only merge into the main checkout can be run at all, and whether that "
    "checkout carries commits of its own"
)

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


# The past-tense half of the routing refusal's remedy. A landing really did decline to
# push and needs it; a dry run pushed nothing whatever it found, and printing it two
# lines under "This ran nothing." describes an act that was never in prospect. Named once
# so the plan can drop exactly the clause the landing keeps (#344, round 2 claim 7).
#
# **Every** routing refusal ends with it, and that is what makes the plan's `removesuffix`
# a rule rather than a special case. Round 2 named the clause once and then left the two
# unreadable kinds carrying their own past-tense wording inline, so the plan printed those
# two unchanged — and they are precisely the kinds a dry run meets when something is
# broken (round 2 claim 3). The wording before the clause is now tenseless in all three.
PUSHED_CLAUSE: Final = " Nothing was pushed."


def _exempt_lane(read: routing_policy.ReadResult, lane: str) -> bool:
    """Whether the *landing* rung's per-policy lane exemption covers this lane.

    **Not the one home for the lane question, and since #326 it cannot be.** The routing
    policy's exemption is decided per row inside `routing_policy._refusing_rules`: a row
    carrying `required_seats` binds every lane, Claude's included. This predicate is the
    landing rung's coarser, per-policy copy, and the two agree today only because
    `parse_policy` refuses a `required_seats` row any `landing_path_prefixes` — so no row
    that binds Claude can reach the landing rung at all. Relax that guard and they diverge
    silently, which is why this docstring names the coupling rather than claiming sole
    ownership (review round 2 claim 9).

    The policy's own `claude_lane` is the authority and `enforcing_match` reads it from
    there; the constant is the fallback for a policy that could not be read, which is
    also the order the gate needs — the Claude lane must not be refused for an unreadable
    policy it is the remedy for. One predicate rather than a literal at each site, because
    a second copy is how changing `claude_lane` would silently move only one of them
    (#344, review round 1 claim 6).

    The policy **replaces** the constant rather than joining it. Round 1 unioned the two,
    which left the exempt set both `CLAUDE_LANE` and `policy.claude_lane` while
    `enforcing_match` exempts only the policy's name — so a policy moving `claude_lane`
    elsewhere would have had `land.py` exempt the old name silently, and this is the
    enforcing rung, not the dry run's half (#344, review round 2 claim 1).
    """
    if read.policy is not None:
        return lane == read.policy.claude_lane
    return lane == CLAUDE_LANE


def classify_routing(
    read: routing_policy.ReadResult,
    paths: tuple[str, ...] | None,
    lane: str,
    detail: str = "",
) -> Refusal | None:
    """Enforce the routing policy against the real non-exempt diff.

    This is the gate. Unlike dispatch's advisory issue-declaration read, an empty match
    here says something about the paths that will actually be pushed. An unreadable
    policy or diff refuses: a check that did not run is not a clearance (#41).

    A clear read is **not** a statement that the diff was covered, and since #326 it says
    so: the policy's own `coverage` line rides on every routing verdict, so the incomplete
    coverage of the class list is met by the reader the classes are being applied to rather
    than left in a docstring. It rides on every refusal and not only class 6's, because a
    reader refused under one class is exactly the reader forming a belief about what the
    table checks — and, since review round 1 claim 3, on the clear read too. Round 1 put the
    line only on refusals, which left the one reader who is *told nothing is wrong* as the
    only reader who never meets "a surface this file does not name is uncovered, never
    cleared" — and that reader is the one forming the belief. `routing_clearance` below is
    where the clear read says it.
    """
    if _exempt_lane(read, lane):
        return None
    if read.policy is None:
        return Refusal(
            "routing_policy_gate_unreadable",
            ("check=enforcing actual diff", f"policy={read.error}"),
            "The trusted routing policy could not be read, so the routing gate cannot clear "
            "this landing. Repair the policy on Claude and run `just land` "
            f"again.{PUSHED_CLAUSE}",
        )
    if paths is None:
        return Refusal(
            "routing_policy_diff_unreadable",
            ("check=enforcing actual diff", f"detail={detail}"),
            "Git could not name the real diff, so the routing gate cannot run and a check "
            "that could not run is not a check that passed (#41). Repair the repository "
            f"state and run `just land` again.{PUSHED_CLAUSE}",
        )
    match = routing_policy.enforcing_match(read.policy, paths, lane)
    if match is None:
        return None
    return Refusal(
        "routing_policy_gate",
        (
            "check=enforcing actual diff",
            f"routing_class={match.rule.id}:{match.rule.name}",
            f"class_label={match.rule.label}",
            *match.evidence,
            f"source={read.policy.source}",
            f"coverage={read.policy.coverage}",
        ),
        f"{match.rule.remedy}{PUSHED_CLAUSE}",
    )


def routing_clearance(read: routing_policy.ReadResult, lane: str) -> tuple[str, ...]:
    """Say what a *clear* routing read did and did not establish, for one non-exempt lane.

    The counterpart to `classify_routing`'s refusal and deliberately not a silence. A
    landing whose routing rung finds no match currently prints nothing at all, so the
    incomplete coverage of the class table — stated on every refusal — is the one thing the
    cleared lander never hears. Concretely, the case that motivated this: a `zai` landing
    touching `tools/check_seat_config.py`, a gate `just check` runs and class 6 does not
    name, passed the routing rung in silence and read as approved (review round 1 claim 3).

    Empty only for a non-exempt lane whose policy could not be read, which is somebody else's
    verdict to state: `classify_routing` has already refused that case with the error in it.
    The exempt lane meets an unreadable policy in silence otherwise, because that refusal is
    the one it is exempt from.

    **An exempt lane gets a line, and round 1's reasoning for withholding one was the wrong
    way round (review round 2 claim 6).** "A coverage sentence there would describe a check
    that did not run" is exactly what the sentence exists to say — a rung that did not run is
    not a rung that passed — and the Claude lander is both the reader most likely to land
    `docs/adr/` from an unappointed seat and the one this rung structurally cannot catch. So
    the exempt lane is told that it was exempted rather than cleared, in its own words rather
    than in the non-exempt lane's.
    """
    if _exempt_lane(read, lane):
        stated = (
            f"coverage={read.policy.coverage}"
            if read.policy is not None
            else f"policy={read.error}"
        )
        return (
            f"routing=exempt lane={lane} check=not run",
            "exempt=this lane never consulted the class table, so nothing here was cleared",
            stated,
        )
    if read.policy is None:
        return ()
    return (
        f"routing=clear lane={lane} check=enforcing actual diff",
        f"coverage={read.policy.coverage}",
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


def classify_corpus(finding: corpus_gate.Finding | None) -> Refusal | None:
    """Turn the corpus rung's answer into this recipe's refusal vocabulary.

    The decision is `tools/corpus_gate.py`'s and the words are its own; all this
    does is hand them to the same `Refusal` every other rung refuses with, so a
    reader meets one output shape rather than two.
    """
    if finding is None:
        return None
    return Refusal(finding.kind, finding.found, finding.action)


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


def _routing_inputs(path: Path) -> tuple[routing_policy.ReadResult, tuple[str, ...] | None, str]:
    """Read the trusted policy from fetched origin/main and this branch's own paths.

    Reading the worktree's copy would let the very diff under judgement weaken the
    policy that judges it. `land` has already fetched at this point, so `origin/main` is
    both current and outside the candidate diff.

    **Three dots, and the third is load-bearing.** `git diff A..B` is a synonym for
    `git diff A B` — a symmetric tree comparison, not a commit range — so on a fetched
    base it reports this branch's paths *and* every path the incoming commits touch.
    That is harmless after a rebase, where the two sets coincide, and wrong before one, in
    **both** directions. Adding: `landing_match` matches on any path, so a pre-rebase
    caller would refuse an ungated diff for a class a sibling brought. Dropping, which is
    the fail-open half and the one worth naming — a tree comparison lists only paths where
    the two trees *differ*, so where a sibling has already landed a patch-identical change
    the path is in neither difference and falls out of the set entirely, and a
    non-exempt landing of a gated class would have been told `would_pass`.
    `origin/main...HEAD` is merge-base relative, so this answers with the branch's own
    paths wherever it is called from. The enforcing rung's answer was previously right by
    accident of ordering; this makes it right by construction, so moving the call cannot
    quietly reintroduce the bug (#344, review round 1 claim 1).

    One divergence survives, and it is the other direction of the rebase rather than the
    sibling one: a commit of this branch's that the rebase discards as already upstream —
    a patch-identical change a sibling landed first — is in the merge-base-relative set
    and gone from the post-rebase tree. A pre-rebase caller can therefore still refuse a
    class the landing will not see. Fail-closed, and it needs the identical patch already
    on `origin/main`; stated because "right by construction" is what a later reader will
    rely on (review round 2 claim 6). Note the direction: on that same scenario the
    two-dot form was fail-*open*, which is why "only ever adds matches" was the wrong
    account of it and is not the one above (review round 2 claim 4).
    """
    try:
        policy_text = git("show", f"{BASE}:{routing_policy.POLICY_RELATIVE.as_posix()}", cwd=path)
    except GitError as error:
        read = routing_policy.ReadResult(None, error.stderr)
    else:
        try:
            read = routing_policy.ReadResult(routing_policy.parse_policy(policy_text))
        except (ValueError, KeyError, TypeError) as error:
            read = routing_policy.ReadResult(None, str(error))

    try:
        listed = git("diff", "--name-only", f"{BASE}...HEAD", cwd=path)
    except GitError as error:
        return read, None, error.stderr
    paths = tuple(line.strip() for line in listed.splitlines() if line.strip())
    return read, paths, ""


def _commit_known(path: Path, sha: str) -> bool:
    """Whether that commit resolves here at all, so a claim about it can be checked."""
    if not sha:
        return False
    code, _stderr = _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=path)
    return code == 0


def _tree_difference(path: Path, sha: str) -> tuple[str, ...] | None:
    """Every path that differs between that commit's tree and HEAD's.

    A tree comparison rather than a range, deliberately: `just land` rebases, so the
    commit a corpus ran over is not an ancestor of what gets pushed whenever a sibling
    landed first. What the corpus rung has to know is whether the world it measured is
    the world being pushed, and that is a question about trees.
    """
    try:
        listed = git("diff", "--name-only", sha, "HEAD", cwd=path)
    except GitError:
        return None
    return tuple(line.strip() for line in listed.splitlines() if line.strip())


def corpus_finding(  # noqa: PLR0911 — a ladder of named refusals, one return per rung
    path: Path,
    read: routing_policy.ReadResult,
    paths: tuple[str, ...] | None,
    detail: str,
    named: Path | None,
) -> corpus_gate.Outcome:
    """Assemble everything git can answer, then let `corpus_gate` decide.

    The policy comes from fetched `origin/main` rather than from this tree, for
    `_routing_inputs`' reason one rung along: a landing must not be able to widen
    the surface list that judges it in the same diff.
    """
    if read.policy is None:
        return corpus_gate.Outcome(corpus_gate.unreadable((f"policy={read.error}",)))
    if paths is None:
        return corpus_gate.Outcome(corpus_gate.unreadable((f"detail={detail}",)))
    in_world = routing_policy.in_world_paths(read.policy, paths)
    if not in_world:
        return corpus_gate.Outcome(None)
    if named is None:
        return corpus_gate.Outcome(corpus_gate.owed_with_no_run(in_world), in_world)

    document, why = corpus_gate.read_record(named)
    if document is None:
        return corpus_gate.Outcome(
            corpus_gate.Finding(
                corpus_gate.OWED, (f"corpus_run={named}", f"rejected=unreadable detail={why}")
            ),
            in_world,
        )
    sha = str(document.get("git_sha", ""))
    known = _commit_known(path, sha)
    since = _tree_difference(path, sha) if known else ()
    if since is None:
        return corpus_gate.Outcome(
            corpus_gate.unreadable((f"corpus_run={named}", f"detail=git could not diff {sha}")),
            in_world,
        )
    finding = corpus_gate.judge(
        corpus_gate.Run(
            path=named,
            document=document,
            sha=sha,
            known=known,
            moved=routing_policy.in_world_paths(read.policy, since),
            dirty=corpus_gate.recorded_dirty(document),
        ),
        corpus_gate.full_corpus(path),
    )
    return corpus_gate.Outcome(finding, in_world)


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


def land(  # noqa: PLR0913 — the protocol's inputs, one parameter apiece
    root: Path,
    here: Path,
    *,
    gate: Gate = run_gate,
    dry_run: bool = False,
    lane: str = CLAUDE_LANE,
    corpus: Path | None = None,
) -> Report:
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
        return _dry_run(root, here, ahead, incoming, corpus, lane)

    lines = [f"worktree={here}", f"commits={ahead}"]
    if ahead:
        moved = _rebase_and_gate(here, incoming, gate, lines, lane, corpus)
        if moved is not None:
            return moved
    else:
        # Nothing to push: this is the re-run after a blocked merge. The gate is
        # not skipped by a flag — there is simply nothing new being landed, and
        # the outstanding step is the merge the last run could not make.
        #
        # The routing and corpus rungs are named here as skipped, in the same words the
        # dry run's `_nothing_to_push_plan` uses, because this is the run that prints
        # `ok=landed` (#326 review round 3 claim 8). The exit-2 refusal it follows carried a
        # routing verdict; without these lines the one output a reader quotes into an
        # issue as the successful landing is the one output with no routing line at all,
        # and an omission reads as a clearance for exactly the reason `not_checked=`
        # exists.
        why = "reason=nothing_to_push"
        lines += [
            "rebase=not_attempted",
            f"gate=not_run {why}",
            f"routing=not_consulted {why}",
            f"corpus=not_consulted {why}",
        ]

    pushed = _push(here, ahead, lines)
    if isinstance(pushed, Report):
        return pushed
    return _merge(root, here, pushed, lines)


def _rebase_and_gate(  # noqa: PLR0911, PLR0913, PLR0917 — one rung per return, one input apiece
    here: Path, incoming: int, gate: Gate, lines: list[str], lane: str, corpus: Path | None
) -> Report | None:
    """Rebase onto `origin/main`, then gate the result. Any rung may refuse."""
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

    # Dispatch's body match is advisory because planned surfaces can be understated.
    # This independently reads the actual rebased diff and is the enforcing gate.
    policy, paths, detail = _routing_inputs(here)
    misrouted = classify_routing(policy, paths, lane, detail)
    if misrouted is not None:
        return Report.refused(misrouted)
    lines.extend(routing_clearance(policy, lane))

    red = classify_gate(here, gate(here))
    if red is not None:
        return Report.refused(red)
    lines.append(f"gate=green ({' '.join(GATE)})")

    # After the gate on purpose: the corpus costs a slot of the Arma tier, and a tree
    # that cannot pass `just fast` has no business being sent there (#302).
    outcome = corpus_finding(here, policy, paths, detail, corpus)
    owed = classify_corpus(outcome.finding)
    if owed is not None:
        return Report.refused(owed)
    lines.append(outcome.line(corpus))
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
    """Fast-forward the main checkout, and make a merge that did not run loud.

    The exit-2 refusal keeps the lines the landing already earned, and it is the one refusal
    that must (review round 2 claim 8). Every other discard path is a landing that did not
    happen, so the routing clearance and the gate line describe work with no consequence; on
    this path the work **is** on `origin/main`, and dropping the lines would leave the only
    lander who has actually shipped as the only one never told what the routing rung did and
    did not check.
    """
    if not _merge_needed(here, root):
        lines.append(f"merge=not_needed reason=landed_from_the_main_checkout ({root})")
        return Report((("ok=landed"), *lines), 0)
    code, stderr = _run(merge_argv(root), cwd=root)
    outstanding = classify_merge(root, pushed, code, stderr)
    if outstanding is not None:
        return Report((*lines, *outstanding.lines()), EXIT_LANDED_INCOMPLETE)
    lines.append(f"merge=fast-forwarded {root} to {pushed}")
    return Report((("ok=landed"), *lines), 0)


def _dry_run(  # noqa: PLR0913, PLR0917 — the plan's inputs, one parameter apiece
    root: Path, here: Path, ahead: int, incoming: int, corpus: Path | None, lane: str
) -> Report:
    """Print the plan and change nothing. Not a landing, and it says so.

    The routing rung is **consulted here**, not merely mentioned: its inputs are the
    trusted policy on fetched `origin/main` and the merge-base-relative
    `origin/main...HEAD` diff, and neither needs the rebase — which is why `--dry-run`
    printing `would_run=git push` for a landing the gate refuses was a silence rather
    than a limit (#344). What a dry run genuinely cannot reach — the rebase's own
    result, the markers in the rebased tree, `just fast`, whether the push and the merge
    can be run at all — it names, so its silence stops reading as a clearance (#41's
    line, applied to a plan).

    **It mirrors the landing's own control flow, including where that flow skips the
    gate.** With nothing to push, `land` skips `_rebase_and_gate` entirely and finishes
    the outstanding merge, so classifying routing here would be a verdict about a rung
    that will not run — a new way to be wrong, not a more honest plan (review round 1
    claim 2).

    The exit code carries the verdict, because a dry run lands nothing either way and
    the body is the only other channel there is: 0 where no rung it could consult
    refused, `EXIT_REFUSED` where the routing gate would (review round 1 claim 7). It is
    not a routing-only channel — the rungs `land` decides before this branch exit 1 as
    well, so 1 means "some refusal, read which" (round 2 claim 5).
    """
    merge_command = " ".join(merge_argv(root))
    merge_step = merge_command if _merge_needed(here, root) else None
    head = (
        "ok=dry_run",
        "landed=no",
        f"worktree={here}",
        f"main_checkout={root}",
        f"head={_describe(here)}",
        f"commits={ahead}",
        f"incoming={incoming} new commits on {BASE}",
    )
    ran_nothing = "This ran nothing. `just land` runs it, gate included."
    if not ahead:
        plan = _nothing_to_push_plan(merge_command)
        return Report((*head, *plan, f"not_checked={NOT_CHECKED_MERGE_ONLY}", ran_nothing), 0)

    read, paths, detail = _routing_inputs(here)
    misrouted = classify_routing(read, paths, lane, detail)
    onward = [" ".join(push_argv()), merge_step or "(merge not needed)"]
    plan = [f"would_run={step}" for step in (f"git rebase {BASE}", " ".join(GATE))]
    if misrouted is None:
        plan += [f"would_run={step}" for step in onward]
    else:
        plan += [f"would_not_run={step} reason={misrouted.kind}" for step in onward]
    return Report(
        (
            *head,
            *plan,
            *_routing_plan(read, misrouted, lane),
            *_corpus_plan(here, read, paths, detail, corpus),
            f"not_checked={NOT_CHECKED}",
            ran_nothing,
        ),
        EXIT_REFUSED if misrouted is not None else 0,
    )


def _nothing_to_push_plan(merge_step: str) -> tuple[str, ...]:
    """Plan the one state `land` handles by skipping the gate altogether.

    `ahead == 0` past `classify_nothing_to_land` is the re-run after
    `merge_blocked_by_sandbox`: the work is already on `origin/main`, so the landing
    skips the rebase, the markers, the routing gate, `just fast` and the corpus alike,
    pushes nothing, and finishes the merge the last run could not make. Each skipped
    rung is named with the reason the landing itself gives, rather than left out — an
    omission here would read as a clearance for exactly the reason `not_checked=` exists
    (#344, review round 1 claim 2).

    The merge step is a `str` and not an optional one, because reaching here at all
    implies it exists: `ahead == 0` survives `classify_nothing_to_land` only when the
    main checkout is behind, and that is what `_merge_needed` reports. Round 1 branched
    on it regardless and the second arm was unreachable — invisible to `just mutation`
    too, which plants only in what the tests execute (round 2 claim 4).
    """
    why = "reason=nothing_to_push"
    return (
        f"would_skip=git rebase {BASE} {why}",
        f"would_skip={' '.join(GATE)} {why}",
        f"would_skip={' '.join(push_argv())} reason=already_on_origin/main",
        f"routing=not_consulted {why}",
        f"corpus=not_consulted {why}",
        f"would_run={merge_step}",
    )


def _routing_plan(
    read: routing_policy.ReadResult, misrouted: Refusal | None, lane: str
) -> tuple[str, ...]:
    """State the routing rung's verdict on this branch's own diff, refusal and evidence alike.

    A verdict rather than a plan step, because the check really did run, on exactly the
    inputs the enforcing rung uses one step later: the trusted policy from fetched
    `origin/main`, and `origin/main...HEAD`, which is merge-base relative and so names
    this branch's own paths whether or not the rebase has happened (`_routing_inputs`).

    Both verdicts carry the same qualification, and deliberately. The caveat used to sit
    on the pass and not on the refusal, which steered a reader away from whichever line
    was the one that could be wrong; they are claims about one path set and are stated as
    that (review round 1 claim 5).

    The remedy is printed without its `Nothing was pushed.` clause: the `Refusal` carries
    one action string for the landing and the plan alike, and here nothing was ever going
    to be pushed, two lines above "This ran nothing." (review round 2 claim 7). Every
    routing refusal ends with `PUSHED_CLAUSE` so that one `removesuffix` covers all three
    kinds; round 2's stripped only the gate's and left the two unreadable kinds — the ones
    a dry run meets when something is broken — printing it (review round 2 claim 3).

    The caveat names the divergence rather than only the provenance. "Merge-base relative"
    on its own reads as a statement of precision, and the case a lander needs warning about
    is the one where this verdict and the real landing disagree: a commit of this branch's
    that the rebase will discard as already upstream is in this path set and gone from the
    tree that gets pushed, so a `would_refuse` can dissolve on the rebase. The docstring is
    where round 2 put that; the line below is where the lander looks (round 2 claim 8).
    """
    where = (
        "(this branch's own diff, merge-base relative; a commit the rebase drops as "
        "already upstream is still counted, so a refusal can dissolve on the rebase)"
    )
    if _exempt_lane(read, lane):
        return (f"routing=not_applicable lane={lane}",)
    if misrouted is None:
        return (
            f"routing=would_pass lane={lane} {where}",
            # The same reason the enforcing rung says it: the reader told the diff is fine is
            # the reader who most needs "a surface this file does not name is uncovered,
            # never cleared" (review round 1 claim 3). `routing_clearance` is not reused here
            # because its own first line is a verdict on the real diff, and this is a plan.
            *((f"coverage={read.policy.coverage}",) if read.policy is not None else ()),
        )
    return (
        f"routing=would_refuse lane={lane} refusal={misrouted.kind} {where}",
        *misrouted.found,
        f"action={misrouted.action.removesuffix(PUSHED_CLAUSE)}",
    )


def _corpus_plan(
    here: Path,
    read: routing_policy.ReadResult,
    paths: tuple[str, ...] | None,
    detail: str,
    corpus: Path | None,
) -> tuple[str, ...]:
    """Say whether this diff owes the corpus, computed the same way the rung computes it.

    Worth saying here rather than only at the refusal, because the whole cost of the
    corpus is a slot of the Arma tier and knowing before the rebase is what lets an
    agent hand back instead of running a gate it cannot clear. The diff is the one
    `_routing_inputs` names — merge-base relative, this branch's own — and it is stated
    as that rather than as a pre-rebase approximation of it.
    """
    outcome = corpus_finding(here, read, paths, detail, corpus)
    if outcome.finding is not None and outcome.finding.kind == corpus_gate.UNREADABLE:
        return (f"corpus=unknown detail={' '.join(outcome.finding.found)}",)
    if not outcome.in_world:
        return (
            "corpus=not_owed reason=no_in_world_path (this branch's own diff, merge-base relative)",
        )
    listed = " ".join(outcome.in_world[:HOW_MANY_SHOWN])
    owed = f"corpus=owed in_world={listed}"
    if outcome.finding is None:
        return (owed, f"corpus_run={corpus} would_clear=yes")
    why = [line for line in outcome.finding.found if not line.startswith("in_world=")]
    return (owed, f"corpus_run={corpus or 'none'} would_clear=no", *(f"why={line}" for line in why))


# ------------------------------------------------------------------ invocation


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Two optional flags, and deliberately no others.

    There is no `--no-gate`, no `--force`, and no way to name the refspec or the
    remote: those are #213's criterion 2 and the `git push origin main` trap,
    and the surface that cannot express them is the mechanism.

    `--corpus` is not an exception to that. It **names evidence**; it does not
    excuse the check. Every claim a named pool makes is verified against the
    pool's own record — the right corpus, whole, over this landing's history,
    green — so pointing it at a convenient green run refuses rather than passes,
    and there is no `--no-corpus` to reach for instead (#302).
    """
    parser = argparse.ArgumentParser(prog="just land", description="Land this worktree on main.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and run nothing at all",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        metavar="POOL",
        help="the pool evidence directory of the full `just regress` run over this tree",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the protocol, print what happened, and exit what it decided."""
    args = parse_args(argv)
    try:
        here = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()).strip()).resolve()
        root = main_checkout(here).resolve()
        report = land(
            root,
            here,
            dry_run=args.dry_run,
            lane=os.environ.get("CTI_DISPATCH_LANE", CLAUDE_LANE),
            corpus=args.corpus,
        )
    except GitError as failure:
        report = Report.refused(
            Refusal(
                "git_failed",
                (f"command=git {' '.join(failure.args_run)}", f"stderr={failure.stderr}"),
                "Read git's own error above. Check what actually happened with "
                "`git log --oneline origin/main..HEAD` before running anything else.",
            )
        )
    # A landing's refusal is an error and belongs on stderr. Since #344 gave a dry run a
    # verdict its exit is non-zero exactly when it has the most to say, so routing on the
    # code alone emptied stdout in the one case #344 was filed about, leaving a
    # seat on another lane with a bare `recipe … failed` banner that this project trains
    # agents to read as a harness failure (round 2 claim 3).
    #
    # The condition is `--dry-run` and not "is a plan", so **everything** a dry run prints
    # goes to stdout — the plan, and equally the `dirty_tree`, `nothing_to_land` and
    # `git_failed` refusals `land` decides before it reaches the plan. Deliberate, and
    # stated because three surfaces used to say "the plan": a run that lands nothing has
    # no error output to separate, and the seat reading it needs the words wherever it
    # looks. What must not move is a real landing's refusal (round 2 claim 5).
    stream = sys.stdout if report.code == 0 or args.dry_run else sys.stderr
    for line in report.lines:
        print(line, file=stream)
    return report.code


if __name__ == "__main__":
    sys.exit(main())
