"""The recovery runbook's two computable procedures (#253, orchestration-design §4).

`docs/agents/recovery.md` sets its own codification threshold — "two identical saves" —
and two of its procedures have now crossed it. The twenty-fourth retro resolved four BLIND
watcher findings by hand over removed prior-art research worktrees; the twenty-fifth
resolved two dead review-watcher assessors the same way. This is those two looks, plus the
resumption briefing's two computable reconstructions, run the same way every time.

## The property this is built for

Not the saved reading. **A tool prints only what it read.** The runbook records a briefing
that reasoned from "clean, zero ahead" to "announced work died uncommitted", when the same
evidence meant the opposite — the agent had pushed and then carried on (2026-08-02). The
rule written in response, *state what the evidence shows, not what it implies*, is prose
that a tired reader can decline to follow. Here it is construction: every verdict carries
the `basis` that forced it, every reading is printed beside the conclusion drawn from it,
and the one reconstruction that is judgement is emitted as an empty heading rather than
guessed at. The runbook says this binds hardest where the briefer is the party that lost
its memory, which is exactly the case this tool exists to serve.

## `check <name>` — the BLIND look

A BLIND finding means the watcher could not read a worktree's HEAD, and `tools/stall_watch`
is deliberate that could-not-observe is never "still running". Resolving one asks whether
the tree is absent with its output landed, or absent with work unlanded. The readings are
worktree presence, git's own registration, HEAD from whichever of three sources still holds
one, whether that HEAD is an ancestor of `origin/main`, the dispatch record over the same
worktree, and what landed on `origin/main` while the watch was live.

| Verdict | What forced it |
|---|---|
| `lost_work` | A knowable HEAD carries commits that are not on `origin/main` |
| `still_live` | The worktree is on disk and its HEAD reads |
| `finished_and_cleaned` | The tree is gone, and its last HEAD is on `origin/main` |
| `finished_and_cleaned` | The tree is gone, and something positive says its work finished |
| `unproven` | None of the above |

`lost_work` names the commits and the files they touch; `still_live` says only that the
tree can be read, because whether its agent is alive is judgement and not a reading;
`unproven` says the look did not resolve, rather than clearing it.

**`unproven` exists because of the vacuity rule.** An absent tree with nothing attributable
to it has no unlanded commits *because it has no commits this box can see*, and reporting
that as `finished_and_cleaned` would be `just prereqs` calling an unproven config `ok`
(#116). So the cleared verdict needs positive evidence — a dispatch record over that
worktree carrying a `result.json`, or at least one commit landing on `origin/main` inside
the watch's own window — and it prints, in the same breath, what that evidence cannot
exclude: a tree deleted while carrying unlanded commits reads identically from here.

**It acks nothing and writes nothing.** `just watch-report --ack` stays the judgement
(ADR-0053: the machine's half ends at noticing), and this tool opens the watch directory
read-only. It resets nothing, prunes nothing and removes nothing — the standing rule that a
refusal path never touches another agent's tree (#105), read across to a reporting tool.

## `brief <issue|worktree>` — the resumption briefing's computable halves

The runbook names three reconstructions, and says omitting any one silently corrupts the
resumed work into defects that look ordinary:

1. **What moved on `origin/main`** since the dead agent's last commit — commits, ADR files
   added, issues opened and closed in that window. Computed.
2. **What of its own environment died** — the worktree's state, evidence directories
   carrying no `verdict.json` (ADR-0022: not a result), the slot locks' recorded holders.
   Computed.
3. **Which of its assumptions no longer hold.** Judgement. The heading is printed with
   nothing under it, and no input fills it.

`just handoff <issue>`'s output is printed beside all three, so the predecessor's own
account and the computed delta arrive together. A thread carrying no handoff carries that
tool's exit-1 message instead — never silence, which reads as "no state to carry" when it
may mean "wrong issue" (#168/#183).

Two words are absent from everything `brief` prints, on purpose: *landed* and *lost*. A
commit is "on origin/main" or "not on origin/main", which is what git answered; which of
those two the agent's work **is** is the resumed agent's to verify on wake, and the
briefing that guessed it is the error above.

**Locks are read, never taken.** A slot's `flock` frees itself on holder death (ADR-0022)
and a tool that acquired one to report on it would be a holder. What is read is the
`*.lock.info` metadata the holder wrote and whether that pid is still alive.

**`infra_unavailable` is never interpreted here.** Nothing in this module reads a run's
class or acts on one; the evidence directories it lists are listed as ADR-0022 stale state,
which is the failure-class table's required response and not a reading of any verdict.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `stall_watch.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes this importable. The handoff is fetched through the
# tool that owns it rather than by a second `gh` call, so the two cannot disagree about
# what a handoff is or about what "no handoff" prints.
import handoff_fetch

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

REPO_SLUG: Final = "andrewesweet/arma-cti"

# The checkout this script runs out of. Everything git is asked runs here, and the main
# checkout — where `.claude/worktrees` lives — is derived from git's own porcelain.
REPO: Final = Path(__file__).resolve().parents[1]

# Outside every worktree, beside the tier's own evidence, for `stall_watch`'s reason: these
# outlive the worktrees and the sessions they are about.
DEFAULT_WATCH_DIR: Final = Path.home() / ".arma-cti" / "watch"
DEFAULT_RUNS_DIR: Final = Path.home() / ".arma-cti" / "runs"
DEFAULT_DISPATCH_DIR: Final = Path.home() / ".arma-cti" / "dispatches"
DEFAULT_SLOT_DIR: Final = Path.home() / ".arma-cti" / "slots"

# Every subprocess this makes is bounded (#144): a call that never returns is a held turn.
GIT_TIMEOUT_S: Final = 30
GH_TIMEOUT_S: Final = 30

# `git log --format` with a separator no commit subject contains, so a subject with spaces
# survives the split that a `%h %s` parse would get wrong on the first tab-indented one.
LOG_FORMAT: Final = "%h\x1f%s"
UNIT_SEP: Final = "\x1f"

# `git status --porcelain` puts two status columns and a space before the path.
STATUS_PREFIX: Final = 3

# How many rows of any list the summary prints before it says how many more there are. The
# lists are evidence, so they are bounded rather than truncated silently.
SHOWN: Final = 12

FINISHED: Final = "finished_and_cleaned"
LOST: Final = "lost_work"
LIVE: Final = "still_live"
UNPROVEN: Final = "unproven"

# Where a HEAD came from, worst-to-best kept distinct because the reader's confidence in
# the verdict depends on it: a HEAD read out of the tree is the tree's, a HEAD read out of
# a stale finding is what the watcher last saw before it went blind.
FROM_WORKTREE: Final = "worktree"
FROM_REGISTRATION: Final = "git-registration"
FROM_FINDING: Final = "watch-finding"
FROM_NONE: Final = "none"

CANNOT_EXCLUDE_DELETED: Final = (
    "a worktree deleted while carrying unlanded commits reads identically from here —"
    " its commits, if any, are unreachable and this tool did not see them"
)


# ------------------------------------------------------------------------- what was read


class Commit(NamedTuple):
    """One commit, as `git log` was asked to print it."""

    sha: str
    subject: str

    def line(self) -> str:
        """Render the commit the way every other tool in this tier quotes one."""
        return f"{self.sha} {self.subject}"


class Tree(NamedTuple):
    """What is left of one agent's worktree, and which source answered for each reading."""

    path: Path
    present: bool
    registered: bool
    head: str
    head_source: str
    uncommitted: tuple[str, ...]
    ahead: tuple[Commit, ...]
    files: tuple[str, ...]
    # `yes`, `no`, or `unknown` — three answers, because "git could not tell" must not
    # collapse into either (the tri-state `stall_watch.Observation` keeps for the same
    # reason, and the shape #41 and #44 were both caught by).
    on_main: str


class Watch(NamedTuple):
    """What `just watch` recorded about one agent, spec and finding together."""

    name: str
    spec_path: Path
    finding_path: Path
    worktree: str
    baseline_head: str
    armed_at: int
    subject: str
    issue: str
    state: str
    head: str
    assessed_at: int
    acknowledged_at: int

    def last_live(self) -> int:
        """When this watch was last known to be looking, in epoch seconds, or 0.

        The end of the window `check` reports commits over. A finding the assessor wrote is
        the best answer; a finding an orchestrator only acknowledged is the next best; and a
        watch that recorded neither leaves the caller to decide, which is `now`. Bounding it
        matters because the window grows for as long as nobody bounds it, and a window that
        grows turns a reading into a list of everything that has happened since.
        """
        return self.assessed_at or self.acknowledged_at


class Dispatch(NamedTuple):
    """One dispatch record, reduced to what a recovery look needs from it."""

    dispatch_id: str
    issue: int
    worktree: str
    base_sha: str
    finished: bool


class Evidence(NamedTuple):
    """Everything `check` read, gathered before anything is concluded from it."""

    name: str
    watch: Watch | None
    tree: Tree
    dispatches: tuple[Dispatch, ...]
    window: tuple[Commit, ...]
    window_from: int
    window_to: int


class Verdict(NamedTuple):
    """What the readings forced, and — where it matters — what they cannot exclude."""

    kind: str
    basis: str
    cannot_exclude: str = ""


# --------------------------------------------------------------------------- the deciding


def finished_dispatch(evidence: Evidence) -> Dispatch | None:
    """Return a dispatch over this worktree that carries a result, if one does.

    A `result.json` is written when a dispatch returns, so it is positive evidence that the
    watched work reached an end — the one thing an absent worktree cannot say for itself.
    """
    return next(
        (
            record
            for record in evidence.dispatches
            if record.finished and record.worktree == str(evidence.tree.path)
        ),
        None,
    )


def completion_evidence(evidence: Evidence) -> str:
    """Say what positive evidence exists that this agent's work finished, or nothing.

    Two shapes, in the order they carry weight. A dispatch record naming this worktree and
    carrying a result is about *this agent*. Commits landing on `origin/main` inside the
    watch's own window are about the window, not the agent, and the phrasing says so —
    which is why the caller pairs it with what it cannot exclude.
    """
    record = finished_dispatch(evidence)
    if record is not None:
        return (
            f"dispatch {record.dispatch_id} for #{record.issue} over this worktree"
            f" carries a result.json, so that dispatch returned"
        )
    if evidence.window:
        return (
            f"{len(evidence.window)} commit(s) reached origin/main while this watch was"
            f" live; this window is not attribution, and the commits are listed below"
        )
    return ""


def decide(evidence: Evidence) -> Verdict:
    """Resolve one BLIND look, naming the reading that forced the answer."""
    tree = evidence.tree
    if tree.ahead:
        return Verdict(
            LOST,
            f"{len(tree.ahead)} commit(s) on HEAD {tree.head[:12]} ({tree.head_source})"
            f" are not on origin/main",
        )
    if tree.present and tree.head:
        return Verdict(
            LIVE,
            f"the worktree is on disk and HEAD {tree.head[:12]} reads;"
            f" whether its agent is alive is judgement, not this tool's",
        )
    if tree.head and tree.on_main == "yes":
        return Verdict(
            FINISHED,
            f"the worktree is gone and its last HEAD {tree.head[:12]} ({tree.head_source})"
            f" is an ancestor of origin/main",
        )
    positive = completion_evidence(evidence) if not tree.present else ""
    if positive:
        return Verdict(FINISHED, positive, CANNOT_EXCLUDE_DELETED)
    return Verdict(
        UNPROVEN,
        "no HEAD is knowable for this name and nothing says its work finished,"
        " so this look did not resolve — clearing it here would be a guess",
    )


# -------------------------------------------------------------------------- the git seam


def _run(argv: Sequence[str], cwd: Path, timeout: int = GIT_TIMEOUT_S) -> tuple[int, str]:
    """Run one command and return `(exit code, stdout)`, never raising.

    A git that cannot run is data here rather than an error: every caller has a reading for
    "could not tell", and none of them may treat it as a pass.
    """
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv, no shell, no interpolation
            list(argv),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout


def git(*args: str, cwd: Path) -> str:
    """Run one git command and return its stdout, or empty if git refused."""
    code, out = _run(["git", *args], cwd=cwd)
    return out.strip() if code == 0 else ""


def commits(spec: str, cwd: Path) -> tuple[Commit, ...]:
    """Return the commits in one revision range, newest first."""
    listing = git("log", f"--format={LOG_FORMAT}", spec, cwd=cwd)
    found: list[Commit] = []
    for line in listing.splitlines():
        sha, _, subject = line.partition(UNIT_SEP)
        if sha:
            found.append(Commit(sha, subject))
    return tuple(found)


def registrations(repo: Path) -> tuple[tuple[Path, str], ...]:
    """Every worktree git holds a registration for, with the HEAD it recorded.

    The main checkout comes first in git's porcelain from any worktree, which is what
    `main_checkout` relies on and why one read answers both questions.
    """
    porcelain = git("worktree", "list", "--porcelain", cwd=repo)
    found: list[tuple[Path, str]] = []
    path: Path | None = None
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree ").strip())
            found.append((path, ""))
        elif line.startswith("HEAD ") and found:
            found[-1] = (found[-1][0], line.removeprefix("HEAD ").strip())
    return tuple(found)


def main_checkout(repo: Path) -> Path:
    """Return the main checkout, which is where `.claude/worktrees` lives.

    A look run from inside a worktree must resolve `issue-253` to the sibling under the
    main checkout, not to `<this worktree>/.claude/worktrees/issue-253`, which is nowhere.
    """
    listed = registrations(repo)
    return listed[0][0] if listed else repo


def read_tree(path: Path, repo: Path, *, registered_head: str = "", finding_head: str = "") -> Tree:
    """Read one worktree's state from every source that still holds part of it.

    Three sources answer for HEAD, and which one did is carried into the verdict: the tree
    itself, git's registration for a directory that has gone, and the last HEAD the watcher
    saw before it went blind. A HEAD from any of them is then tested against `origin/main`
    the same way, and a HEAD whose object git no longer holds reads `unknown` rather than
    `no` — a commit this box cannot resolve is not a commit it has seen to be unlanded.
    """
    present = path.is_dir()
    head, source = "", FROM_NONE
    if present:
        head = git("rev-parse", "HEAD", cwd=path)
        source = FROM_WORKTREE if head else FROM_NONE
    if not head and registered_head:
        head, source = registered_head, FROM_REGISTRATION
    if not head and finding_head:
        head, source = finding_head, FROM_FINDING

    uncommitted: tuple[str, ...] = ()
    if present:
        status = git("status", "--porcelain", cwd=path)
        uncommitted = tuple(
            line[STATUS_PREFIX:].strip()
            for line in status.splitlines()
            if len(line) > STATUS_PREFIX
        )

    on_main, ahead, files = "unknown", (), ()
    if head and _run(["git", "cat-file", "-e", f"{head}^{{commit}}"], cwd=repo)[0] == 0:
        on_main = (
            "yes"
            if _run(["git", "merge-base", "--is-ancestor", head, "origin/main"], cwd=repo)[0] == 0
            else "no"
        )
        ahead = commits(f"origin/main..{head}", cwd=repo)
        if ahead:
            listing = git("diff", "--name-only", f"origin/main...{head}", cwd=repo)
            files = tuple(line.strip() for line in listing.splitlines() if line.strip())
    return Tree(
        path=path,
        present=present,
        registered=bool(registered_head),
        head=head,
        head_source=source,
        uncommitted=uncommitted,
        ahead=ahead,
        files=files,
        on_main=on_main,
    )


def commits_between(repo: Path, start: int, end: int) -> tuple[Commit, ...]:
    """Every commit that reached `origin/main` between two instants, newest first.

    The window is the watch's own — armed until last assessed — so what it reports is what
    landed while this agent was being watched. That is a window and never an attribution,
    and the verdict that quotes it says so in the same breath.
    """
    if not start or end <= start:
        return ()
    listing = git(
        "log",
        f"--format={LOG_FORMAT}",
        f"--since=@{start}",
        f"--until=@{end}",
        "origin/main",
        cwd=repo,
    )
    found: list[Commit] = []
    for line in listing.splitlines():
        sha, _, subject = line.partition(UNIT_SEP)
        if sha:
            found.append(Commit(sha, subject))
    return tuple(found)


def committed_at(repo: Path, sha: str) -> int:
    """When a commit was made, in epoch seconds, or 0 if git could not say."""
    stamp = git("show", "-s", "--format=%ct", sha, cwd=repo)
    return int(stamp) if stamp.isdigit() else 0


# ------------------------------------------------------------------ the watch-record seam


def read_json(path: Path) -> dict[str, object]:
    """Read one JSON object, answering an empty one for anything unreadable.

    Unreadable is data, not an error: a spec half-written by a dying session is exactly the
    thing a recovery look exists to read, and it must not take the look down with it.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def watch_names(watch_dir: Path) -> tuple[str, ...]:
    """Every watch this box holds a spec or a finding for."""
    if not watch_dir.is_dir():
        return ()
    found = {
        path.name.removesuffix(".spec.json").removesuffix(".finding.json")
        for path in watch_dir.iterdir()
        if path.name.endswith((".spec.json", ".finding.json"))
    }
    return tuple(sorted(found))


def read_watch(name: str, watch_dir: Path) -> Watch | None:
    """Read one watch's spec and finding, or `None` if this box holds neither."""
    spec_path = watch_dir / f"{name}.spec.json"
    finding_path = watch_dir / f"{name}.finding.json"
    spec, finding = read_json(spec_path), read_json(finding_path)
    if not spec and not finding:
        return None
    return Watch(
        name=name,
        spec_path=spec_path,
        finding_path=finding_path,
        worktree=str(spec.get("worktree") or finding.get("worktree") or ""),
        baseline_head=str(spec.get("baseline_head") or finding.get("baseline_head") or ""),
        armed_at=int(spec.get("armed_at") or 0),
        subject=str(spec.get("subject") or ""),
        issue=str(spec.get("issue") or finding.get("issue") or ""),
        state=str(finding.get("state") or ""),
        head=str(finding.get("head") or ""),
        assessed_at=int(finding.get("assessed_at") or 0),
        acknowledged_at=int(finding.get("acknowledged_at") or 0),
    )


def read_dispatches(directory: Path) -> tuple[Dispatch, ...]:
    """Read every dispatch record this box holds, oldest first."""
    if not directory.is_dir():
        return ()
    found: list[Dispatch] = []
    for record in sorted(directory.iterdir()):
        plan = read_json(record / "dispatch.json")
        if not plan:
            continue
        issue = plan.get("issue")
        found.append(
            Dispatch(
                dispatch_id=str(plan.get("dispatch_id") or record.name),
                issue=issue if isinstance(issue, int) and not isinstance(issue, bool) else 0,
                worktree=str(plan.get("worktree") or ""),
                base_sha=str(plan.get("base_sha") or ""),
                finished=(record / "result.json").is_file(),
            )
        )
    return tuple(found)


# ------------------------------------------------------------------------- gathering `check`


def gather_check(  # noqa: PLR0913 — one keyword per directory this box keeps state in,
    # plus the two readings a test points elsewhere; collapsing them into a context object
    # would hide exactly which seam a caller redirected.
    name: str,
    *,
    repo: Path,
    watch_dir: Path,
    dispatch_dir: Path,
    now: int,
    read_window: Callable[[Path, int, int], tuple[Commit, ...]] = commits_between,
    read_worktree: Callable[..., Tree] = read_tree,
) -> Evidence | None:
    """Read everything one BLIND look needs, or `None` if nothing knows this name.

    A name nothing on this box knows is a refusal rather than an `unproven`: an empty answer
    to a mistyped name reads as "nothing is wrong there", which is the silent-empty shape
    #168 and #183 named one tool over.
    """
    watch = read_watch(name, watch_dir)
    checkout = main_checkout(repo)
    path = (
        Path(watch.worktree)
        if watch and watch.worktree
        else checkout / ".claude" / "worktrees" / name
    )
    registered = dict(registrations(repo))
    dispatches = read_dispatches(dispatch_dir)
    known = (
        watch is not None
        or path.is_dir()
        or path in registered
        or any(record.worktree == str(path) for record in dispatches)
    )
    if not known:
        return None
    tree = read_worktree(
        path,
        repo,
        registered_head=registered.get(path, ""),
        finding_head=watch.head if watch else "",
    )
    start = watch.armed_at if watch else 0
    end = (watch.last_live() or now) if watch else now
    window = read_window(repo, start, end) if start and end > start else ()
    return Evidence(
        name=name,
        watch=watch,
        tree=tree,
        dispatches=dispatches,
        window=window,
        window_from=start,
        window_to=end,
    )


# ------------------------------------------------------------------------ rendering `check`


def _bounded(rows: Sequence[str], indent: str = "  ") -> list[str]:
    """Print a list as evidence: bounded, and saying how much it did not print."""
    shown = [f"{indent}{row}" for row in rows[:SHOWN]]
    if len(rows) > SHOWN:
        shown.append(f"{indent}... {len(rows) - SHOWN} more")
    return shown


def render_check(evidence: Evidence, verdict: Verdict) -> str:
    """Render the verdict, the basis, and every reading the basis was drawn from."""
    tree = evidence.tree
    lines = [f"verdict={verdict.kind}", f"name={evidence.name}", f"basis={verdict.basis}"]
    if verdict.cannot_exclude:
        lines.append(f"cannot_exclude={verdict.cannot_exclude}")
    lines.append("-- what was read")
    watch = evidence.watch
    if watch is None:
        lines.append("watch=absent — this box holds no spec or finding under that name")
    else:
        lines += [
            f"watch.state={watch.state or 'none recorded'} issue={watch.issue or 'unstated'}",
            f"watch.subject={watch.subject or 'unstated'}",
            f"watch.baseline_head={watch.baseline_head or 'unrecorded'}",
            f"watch.head_last_seen={watch.head or 'never read'}",
            f"watch.spec={watch.spec_path}",
            f"watch.finding={watch.finding_path}",
        ]
    lines += [
        f"worktree={tree.path}",
        f"worktree.present={'yes' if tree.present else 'no'}",
        f"worktree.registered={'yes' if tree.registered else 'no'}",
        f"head={tree.head or 'unreadable'} ({tree.head_source})",
        f"head.on_origin_main={tree.on_main}",
        f"commits_not_on_origin_main={len(tree.ahead)}",
    ]
    lines += _bounded([commit.line() for commit in tree.ahead])
    if tree.files:
        lines.append(f"files_those_commits_touch={len(tree.files)}")
        lines += _bounded(list(tree.files))
    lines.append(f"uncommitted={len(tree.uncommitted)}")
    lines += _bounded(list(tree.uncommitted))
    if tree.present and tree.uncommitted:
        lines.append(
            "work_at_risk=uncommitted work dies with the worktree (recovery.md's"
            " thirteenth use); commit before anything else"
        )
    matching = [record for record in evidence.dispatches if record.worktree == str(tree.path)]
    lines.append(f"dispatch_records_over_this_worktree={len(matching)}")
    lines += _bounded(
        [
            f"{record.dispatch_id} #{record.issue} base={record.base_sha[:12]}"
            f" result={'yes' if record.finished else 'no'}"
            for record in matching
        ]
    )
    lines.append(
        f"commits_on_origin_main_while_watched={len(evidence.window)}"
        f" (window {evidence.window_from}..{evidence.window_to})"
    )
    lines += _bounded([commit.line() for commit in evidence.window])
    lines.append(
        "-- this look acked nothing; `just watch-report --ack` stays the judgement (ADR-0053)"
    )
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------ gathering `brief`


class Moved(NamedTuple):
    """Reconstruction 1: what moved on `origin/main` while the agent was dead."""

    since: str
    since_source: str
    commits: tuple[Commit, ...]
    adrs: tuple[str, ...]
    opened: tuple[str, ...]
    closed: tuple[str, ...]
    tracker: str


class Environment(NamedTuple):
    """Reconstruction 2: what of the agent's own environment died with it."""

    tree: Tree
    watches: tuple[Watch, ...]
    evidence_without_verdict: tuple[str, ...]
    locks: tuple[str, ...]


class Handoff(NamedTuple):
    """`just handoff`'s answer, whichever of its three it gave."""

    code: int
    text: str


class Resumption(NamedTuple):
    """Everything the briefing prints, gathered before any of it is rendered."""

    target: str
    issue: int
    moved: Moved
    environment: Environment
    handoff: Handoff


def reference_commit(
    tree: Tree, watch: Watch | None, dispatches: Sequence[Dispatch]
) -> tuple[str, str]:
    """Name the point to measure `origin/main`'s movement from, and say who answered.

    Four sources, best first, and **no default**. An unresolvable reference reports itself
    as unresolvable: defaulting to `origin/main` would print "nothing moved", which is a
    false reassurance rather than a missing reading.
    """
    if tree.head:
        return tree.head, f"the agent's last commit, read from the {tree.head_source}"
    match = next((record for record in dispatches if record.worktree == str(tree.path)), None)
    if match is not None and match.base_sha:
        return match.base_sha, f"the base SHA of dispatch {match.dispatch_id}"
    if watch is not None and watch.baseline_head:
        return watch.baseline_head, f"the baseline `just watch {watch.name}` recorded"
    return "", "unresolvable — no HEAD, no dispatch base and no watch baseline"


def adr_files(repo: Path, since: str) -> tuple[str, ...]:
    """Every ADR file added to `origin/main` since a point, by path."""
    listing = git(
        "diff",
        "--name-only",
        "--diff-filter=A",
        f"{since}..origin/main",
        "--",
        "docs/adr",
        cwd=repo,
    )
    return tuple(line.strip() for line in listing.splitlines() if line.strip())


def fetch_issue_rows(repo_slug: str = REPO_SLUG) -> list[dict[str, object]]:
    """Read the tracker's recent issues, or raise `OSError` if `gh` could not be reached."""
    code, out = _run(
        [
            "gh", "issue", "list", "--repo", repo_slug, "--state", "all", "--limit", "200",
            "--json", "number,title,state,createdAt,closedAt",
        ],
        cwd=REPO,
        timeout=GH_TIMEOUT_S,
    )  # fmt: skip
    if code != 0:
        message = "`gh` could not be reached"
        raise OSError(message)
    try:
        document = json.loads(out)
    except (json.JSONDecodeError, ValueError) as broken:
        message = f"`gh` answered with something that is not JSON: {broken}"
        raise OSError(message) from broken
    if not isinstance(document, list):
        message = "`gh issue list` returned nothing this could parse"
        raise OSError(message)
    return [row for row in document if isinstance(row, dict)]


def _epoch(stamp: object) -> int:
    """Read one ISO-8601 instant as epoch seconds, or 0 for anything unreadable."""
    text = str(stamp or "").replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except (TypeError, ValueError):
        return 0


def issues_in_window(
    rows: Sequence[dict[str, object]], start: int, end: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split the tracker's rows into those opened and those closed inside a window."""
    opened: list[str] = []
    closed: list[str] = []
    for row in rows:
        label = f"#{row.get('number')} {row.get('title') or ''}".strip()
        if start <= _epoch(row.get("createdAt")) <= end:
            opened.append(label)
        if start <= _epoch(row.get("closedAt")) <= end:
            closed.append(label)
    return tuple(opened), tuple(closed)


def evidence_without_verdict(runs_dir: Path, not_before: int) -> tuple[str, ...]:
    """Every run directory written since a point that carries no verdict of any kind.

    ADR-0022: evidence without a `verdict.json` is not a result. This lists them so the
    resumed agent knows what is *there* and must not be cited, which is the opposite of
    inheriting them.
    """
    if not runs_dir.is_dir():
        return ()
    found: list[str] = []
    for run in sorted(runs_dir.iterdir()):
        if not run.is_dir() or (run / "verdict.json").is_file() or (run / "pool.json").is_file():
            continue
        try:
            stamp = int(run.stat().st_mtime)
        except OSError:
            continue
        if stamp >= not_before:
            found.append(str(run))
    return tuple(found)


def pid_alive(pid: int) -> bool:
    """Whether a recorded holder's process still exists on this box."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def lock_holders(slot_dir: Path, *, alive: Callable[[int], bool] = pid_alive) -> tuple[str, ...]:
    """Read what each slot lock's holder wrote about itself, never taking the lock.

    A slot's `flock` frees itself on holder death (ADR-0022, proven on the first holder
    death), so what is worth reporting is the metadata a holder left and whether that
    process is still there. Acquiring the lock to find out would make this a holder.
    """
    if not slot_dir.is_dir():
        return ()
    found: list[str] = []
    for info in sorted(slot_dir.glob("*.lock.info")):
        fields = dict(
            line.split("=", 1)
            for line in info.read_text(encoding="utf-8", errors="replace").splitlines()
            if "=" in line
        )
        pid = int(fields.get("pid", "0")) if fields.get("pid", "0").isdigit() else 0
        state = "process still alive" if alive(pid) else "process gone — stale metadata"
        found.append(
            f"{info.name}: slot={fields.get('slot', '?')} pid={pid}"
            f" started={fields.get('started_at', '?')} {state}"
        )
    return tuple(found)


def read_handoff(issue: int) -> Handoff:
    """Run the handoff tool in-process and keep whichever of its three answers it gave.

    In-process rather than as a subprocess so the exit code and the exact refusal message
    are the ones that tool prints — there is no second copy of either to drift.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        # The transport is looked up on the module at call time rather than left to that
        # tool's own keyword default, which binds at definition: a caller — a test above
        # all — that points the transport elsewhere must not fall through to a live `gh`.
        code = handoff_fetch.main([str(issue)], fetch=handoff_fetch.fetch_comments)
    return Handoff(code, (out.getvalue() + err.getvalue()).strip())


def gather_brief(  # noqa: PLR0913 — as `gather_check`: one keyword per state directory
    # and per injected reading, so a caller's redirection is visible at the call site.
    target: str,
    *,
    repo: Path,
    watch_dir: Path,
    dispatch_dir: Path,
    runs_dir: Path,
    slot_dir: Path,
    now: int,
    read_rows: Callable[[], list[dict[str, object]]] = fetch_issue_rows,
    read_handoff_for: Callable[[int], Handoff] = read_handoff,
    read_worktree: Callable[..., Tree] = read_tree,
) -> Resumption:
    """Read both computable reconstructions, and the predecessor's own account beside them."""
    checkout = main_checkout(repo)
    issue = int(target.removeprefix("#")) if target.removeprefix("#").isdigit() else 0
    watches = tuple(
        found
        for found in (read_watch(name, watch_dir) for name in watch_names(watch_dir))
        if found is not None
    )
    if issue:
        path = checkout / ".claude" / "worktrees" / f"issue-{issue}"
    else:
        named = next((found for found in watches if found.name == target), None)
        path = (
            Path(named.worktree)
            if named and named.worktree
            else checkout / ".claude" / "worktrees" / target
        )
    mine = tuple(found for found in watches if found.worktree == str(path))
    registered = dict(registrations(repo))
    dispatches = read_dispatches(dispatch_dir)
    tree = read_worktree(
        path,
        repo,
        registered_head=registered.get(path, ""),
        finding_head=next((found.head for found in mine if found.head), ""),
    )
    if not issue:
        issue = next((record.issue for record in dispatches if record.worktree == str(path)), 0)

    since, source = reference_commit(tree, mine[0] if mine else None, dispatches)
    window_start = committed_at(repo, since) if since else 0
    try:
        rows = read_rows()
        opened, closed = issues_in_window(rows, window_start, now) if window_start else ((), ())
        tracker = "read" if window_start else "not read — no reference commit to date the window"
    except OSError as failure:
        opened, closed, tracker = (), (), f"unread — {failure}"
    moved = Moved(
        since=since,
        since_source=source,
        commits=commits(f"{since}..origin/main", cwd=repo) if since else (),
        adrs=adr_files(repo, since) if since else (),
        opened=opened,
        closed=closed,
        tracker=tracker,
    )
    environment = Environment(
        tree=tree,
        watches=mine,
        evidence_without_verdict=evidence_without_verdict(runs_dir, window_start),
        locks=lock_holders(slot_dir),
    )
    return Resumption(
        target=target,
        issue=issue,
        moved=moved,
        environment=environment,
        handoff=read_handoff_for(issue) if issue else Handoff(0, ""),
    )


# ------------------------------------------------------------------------- rendering `brief`

# Reconstruction 3, entire. A constant with nothing interpolated into it, so that no input
# can fill it and a test can assert the section is byte-for-byte this (criterion 4).
PREAMBLE: Final = (
    "Computed by `just recover brief`. Reconstructions 1 and 2 are read off this box;"
    " reconstruction 3 is judgement and is left empty. Every line below is a reading, not an"
    " inference: what the evidence *means* for this work is the resumed agent's to verify on"
    " wake (recovery.md, the resumed agent's side)."
)

RECONSTRUCTION_THREE: Final = (
    "_Empty by construction. Which of the resumed agent's assumptions no longer hold —"
    " ADR numbers that collided, surfaces another agent now owns, eliminations whose tested"
    " context changed — is judgement, and it stays the orchestrator's. A tool that guessed"
    " here would be the 2026-08-02 briefing error in a new place._"
)

NO_HANDOFF_NOTE: Final = (
    "`just handoff` found none. That is its answer, printed rather than swallowed:"
    ' an empty space here reads as "no state to carry" when it may mean the wrong issue.'
)


def _section(title: str) -> list[str]:
    """Open one section of the briefing."""
    return ["", f"## {title}", ""]


def render_brief(resumption: Resumption) -> str:
    """Render both computed reconstructions, the empty third, and the handoff beside them."""
    moved, environment = resumption.moved, resumption.environment
    tree = environment.tree
    lines = [f"# Resumption briefing — {resumption.target} (computed halves)", "", PREAMBLE]
    lines += _section(f"1. What moved on origin/main since {moved.since or 'an unresolved point'}")
    lines.append(f"reference={moved.since or 'none'} — {moved.since_source}")
    if not moved.since:
        lines.append(
            "Nothing below could be computed. No reference point means no window, and a"
            ' window defaulted to origin/main would print "nothing moved".'
        )
    lines.append(f"commits={len(moved.commits)}")
    lines += _bounded([commit.line() for commit in moved.commits])
    lines.append(f"adr_files_added={len(moved.adrs)}")
    lines += _bounded(list(moved.adrs))
    lines.append(f"tracker={moved.tracker}")
    lines.append(f"issues_opened_in_window={len(moved.opened)}")
    lines += _bounded(list(moved.opened))
    lines.append(f"issues_closed_in_window={len(moved.closed)}")
    lines += _bounded(list(moved.closed))

    lines += _section("2. What of its own environment died with it")
    lines += [
        f"worktree={tree.path}",
        f"worktree.present={'yes' if tree.present else 'no'}",
        f"worktree.registered={'yes' if tree.registered else 'no'}",
        f"head={tree.head or 'unreadable'} ({tree.head_source})",
        f"head.on_origin_main={tree.on_main}",
        f"commits_not_on_origin_main={len(tree.ahead)}",
    ]
    lines += _bounded([commit.line() for commit in tree.ahead])
    lines.append(f"uncommitted={len(tree.uncommitted)}")
    lines += _bounded(list(tree.uncommitted))
    lines.append(f"watch_records={len(environment.watches)}")
    lines += _bounded(
        [f"{found.name} state={found.state or 'none recorded'}" for found in environment.watches]
    )
    lines.append(
        f"evidence_without_verdict_json={len(environment.evidence_without_verdict)}"
        " (ADR-0022: not a result — do not cite, redo the verification)"
    )
    lines += _bounded(list(environment.evidence_without_verdict))
    lines.append(f"slot_lock_metadata={len(environment.locks)} (read, never acquired)")
    lines += _bounded(list(environment.locks))

    lines += _section("3. Which of its assumptions no longer hold")
    lines.append(RECONSTRUCTION_THREE)

    lines += _section(f"The predecessor's own account — `just handoff {resumption.issue}`")
    if not resumption.issue:
        lines.append("No issue number resolves for this target, so no handoff was looked for.")
    elif resumption.handoff.code == 0 and resumption.handoff.text:
        lines.append(resumption.handoff.text)
    else:
        lines += [NO_HANDOFF_NOTE, "", f"exit={resumption.handoff.code}", resumption.handoff.text]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------- the CLI


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Two verbs over one shared computation: resolve a BLIND look, or brief a resumption."""
    parser = argparse.ArgumentParser(
        prog="just recover",
        description="The recovery runbook's two computable procedures (#253).",
    )
    parser.add_argument("--repo", type=Path, default=REPO, help=argparse.SUPPRESS)
    parser.add_argument(
        "--watch-dir",
        type=Path,
        default=Path(os.environ.get("CTI_WATCH_DIR", str(DEFAULT_WATCH_DIR))),
        help="where `just watch` keeps its specs and findings",
    )
    parser.add_argument("--dispatch-dir", type=Path, default=DEFAULT_DISPATCH_DIR)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--slot-dir", type=Path, default=DEFAULT_SLOT_DIR)
    parser.add_argument("--now", type=int, default=0, help=argparse.SUPPRESS)
    verbs = parser.add_subparsers(dest="verb", required=True)

    check = verbs.add_parser("check", help="resolve one BLIND watcher finding")
    check.add_argument("name", help="the watch name, or a worktree name")

    brief = verbs.add_parser("brief", help="the resumption briefing's computable halves")
    brief.add_argument("target", help="an issue number, or a worktree name")
    return parser.parse_args(argv)


def run_check(args: argparse.Namespace, now: int) -> int:
    """Resolve one BLIND look, or refuse a name nothing on this box knows."""
    evidence = gather_check(
        args.name,
        repo=args.repo,
        watch_dir=args.watch_dir,
        dispatch_dir=args.dispatch_dir,
        now=now,
    )
    if evidence is None:
        known = ", ".join(watch_names(args.watch_dir)) or "none"
        print(  # noqa: T201 — a CLI's refusal channel
            f"[recover] no watch, worktree, registration or dispatch names {args.name!r}."
            f" Nothing was looked at. Watches on this box: {known}",
            file=sys.stderr,
        )
        return 1
    print(render_check(evidence, decide(evidence)), end="")  # noqa: T201 — the look IS the output
    return 0


def run_brief(args: argparse.Namespace, now: int) -> int:
    """Compose the resumption briefing's computable halves."""
    resumption = gather_brief(
        args.target,
        repo=args.repo,
        watch_dir=args.watch_dir,
        dispatch_dir=args.dispatch_dir,
        runs_dir=args.runs_dir,
        slot_dir=args.slot_dir,
        now=now,
    )
    print(render_brief(resumption), end="")  # noqa: T201 — the briefing IS the output
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the verb. Both are reads; neither writes anything anywhere."""
    args = parse_args(argv)
    now = args.now or int(time.time())
    return run_check(args, now) if args.verb == "check" else run_brief(args, now)


if __name__ == "__main__":
    sys.exit(main())
