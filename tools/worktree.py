"""The worktree protocol as one call: create, prove exclusivity, refuse loudly (#214, ADR-0049).

Every dispatch narrates the same procedure — fetch, `git worktree add
.claude/worktrees/<name> origin/main --detach`, then CLAUDE.md's pre-flight:
clean `git status`, no foreign untracked files. #209 measured it as the widest
hand loop in the project (212 calls across 106 of 214 agents) and #105 is why it
exists: worktree assignment handed two agents one tree five times in one
evening, and instance 3 destroyed an agent's uncommitted work.

A pre-flight an agent performs from memory, in whatever form it improvises, is
not the same as one that always runs the same checks. This is that pre-flight,
decided here where pytest can reach it (`tests/unit/test_worktree.py`), with the
justfile keeping only the process seam.

Six actions, one refusal vocabulary:

- ``add <name>``   fetch, create off ``origin/main`` detached, pre-flight the
  result, print the absolute path and the base SHA — the two things a dispatch
  briefing otherwise restates.
- ``check [name]`` the pre-flight alone: non-destructive, safe mid-run, and the
  answer to "is this tree still provably only mine?" — which only a clean tree
  answers yes, so a dirty one comes back ``unverified`` with the files listed
  and the judgement left where it belongs. A tree whose status could not be read
  answers ``unverified`` as well, naming the read rather than the contents: an
  unread tree is not a clean one (#375).
- ``list``         the hygiene sweep: every registration, its state, how many
  commits are not proven on ``origin/main``, and which registrations are stale.
- ``done <name>``  verify clean and that every commit is reachable from
  ``origin/main`` or is a ``git cherry``-nominated non-merge with an exact diff
  there, then remove. Never ``--force``.
  Durability through any other ref stays explicit through the archive call and
  is never inferred (#272).
- ``archive <name> --ref <remote-ref>``  verify the tree is clean and the named
  remote ref resolves to its exact HEAD, then remove the worktree. The ref is
  read, never created or moved — it is the preservation act a handoff pushed,
  and removal proceeds only on the evidence that the exact HEAD SHA is on the
  remote (``git ls-remote``, the check the #170 incident used). Not a landing:
  it never prints ``done`` or ``landed``.
- ``restore <name> --ref <remote-ref>``  recreate a detached worktree from that
  exact remote ref and run the same exclusivity pre-flight as ``add``, so
  recovery stays in the protocol rather than a remembered bare-git recipe.

`done` and `archive` write a **teardown record** into the worktree's own git
admin directory before `git worktree remove` runs (#632). Git deletes the
working copy before the administrative entry, so a removal that fails part-way
leaves unstaged deletions behind a still-registered tree — which every later
clean-check reads as a dirty tree and refuses, deadlocking the sanctioned
teardown behind its own failure. The record is what a retry reads to recognise
that state, and what `tools/dispatch.py` reads to keep its advice from telling
a reader to commit a removal's own deletions. It is a recorded fact, written
where only this registration's removal can put it — never an inference from
the shape of the dirt.

**Nothing here resets, cleans, prunes or removes on a refusal path.** CLAUDE.md
is explicit that foreign files mean stop and report, and a recipe that tidies is
a recipe that destroys the work of whoever else is in that tree. `add` does not
even remove the worktree it has just created when the pre-flight refuses it: the
files it found are evidence, and something wrote them.

Refusals are named, and each says what was found and what to do:
``worktree_occupied`` (naming the other holder — #105's damage came from not
knowing), ``dirty_tree``, ``unverified``, ``stale_registration``,
``unlanded_work``, ``no_such_worktree``, ``invalid_name``, ``invalid_ref``,
``not_on_remote``, ``ref_mismatch``, ``git_failed``, ``teardown_ambiguous``,
``worktree_remove_failed``. Exit 0 is proceed, 1 is a refusal; the class is the
first line, in the tier's ``key=value`` form.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NamedTuple

BASE: Final = "origin/main"
WORKTREES: Final = Path(".claude") / "worktrees"
EXIT_REFUSED: Final = 1
# The default deadline on every `remote_ref_sha` read — same whole-call reasoning as
# `review_loop.ROUTING_READ_TIMEOUT_S`, stated there; one order above what a working
# link needs for this repository's refs, well inside the afternoon it exists to cut short.
REMOTE_READ_TIMEOUT_S: Final = 60

# A worktree name becomes a path segment under .claude/worktrees, so it is one
# segment: no separators, no leading dot, nothing that walks upwards.
VALID_NAME: Final = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")
FULL_COMMIT_SHA: Final = re.compile(r"\A[0-9a-f]{40}\Z")
COMMIT_SHA_ERROR: Final = "a commit is named by its full 40-character SHA, never a shortened form"

STOP_AND_REPORT: Final = (
    "Stop and report which tree and which holder. Another agent may be live in it — "
    "never reset, clean or remove another holder's tree (#105)."
)
FOREIGN_FILES: Final = (
    "Stop and report the files. Foreign files mean another agent is in this tree; "
    "never reset or clean them away (#105)."
)
UNCOMMITTED_ON_TEARDOWN: Final = (
    "Nothing was removed. If the work is yours, commit and land it first; if you did not "
    "write these files, another agent is in this tree — stop and report, never reset (#105)."
)
# #632: the two answers a recorded teardown makes possible, beside the refusal that
# keeps standing where no record does. The recovery names the one reset-shaped command
# that is safe here, because the record proves the differences were made by a removal
# this recipe started — `git checkout -- .` from a clean index restores exactly those
# deletions and nothing else.
TEARDOWN_RECOVERY: Final = (
    "This tree is in the middle of its own removal: the teardown record says `just worktree "
    "done` (or `archive`) began removing it and git aborted part-way through the working "
    "copy. Every difference above is that removal's — the head has not moved since it "
    "started — so never commit them. Run `git checkout -- .` in the worktree, which "
    "restores exactly these deletions and nothing else, then run `just worktree done "
    "<name>` again: it recognises this state and completes the removal."
)
TEARDOWN_AMBIGUOUS_ACTION: Final = (
    "A teardown record exists, but the tree does not match what that removal alone could "
    "have left: only unstaged deletions, at the head the record names. Something else has "
    "written here since the removal began, so this tool refuses rather than assume whose "
    "the differences are. Nothing was restored and nothing was removed — read the tree "
    "before acting (#105)."
)
REMOVE_FAILED_ACTION: Final = (
    "git aborted the removal after it had begun, so the working copy may be partly deleted. "
    "The teardown record is in place, so the state is recognisable. Fix what git names "
    "above, then run `just worktree done <name>` again: it completes the removal. Never "
    "commit the deletions the removal left."
)
NOT_ON_REMOTE: Final = (
    "Push the ref to the remote first (`git push origin HEAD:<ref>`), or point --ref at the one "
    "already holding this HEAD. archive never creates or moves a ref, and removed nothing (#272)."
)
REF_MISMATCH: Final = (
    "The remote ref is not at this tree's HEAD. archive never moves a ref; push it yourself or "
    "point --ref at the one holding this exact HEAD. Nothing was removed (#272)."
)
HOW_MANY_SHOWN: Final = 10


class Refusal(NamedTuple):
    """One refusal: its class, what was found, and what the agent should do."""

    kind: str
    found: tuple[str, ...]
    action: str

    def lines(self) -> tuple[str, ...]:
        """Render the refusal as the lines the caller reads."""
        return (f"refusal={self.kind}", *self.found, f"action={self.action}")


class Registration(NamedTuple):
    """One entry of `git worktree list --porcelain`."""

    path: Path
    head: str
    branch: str
    prunable: str
    bare: bool

    @property
    def detached(self) -> bool:
        """True when the worktree sits on no branch, which is how we make them."""
        return not self.branch and not self.bare

    @property
    def state(self) -> str:
        """`main`, `detached`, or the branch name — for the sweep's state column."""
        if self.bare:
            return "bare"
        if self.branch:
            return self.branch.removeprefix("refs/heads/")
        return "detached"


class Preflight(NamedTuple):
    """What `git status --porcelain` found, split the way the rule reads it."""

    tracked: tuple[str, ...]
    untracked: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """A clean tree is the whole of CLAUDE.md's pre-flight condition."""
        return not self.tracked and not self.untracked


class Holder(NamedTuple):
    """Whatever already occupies a path, as far as we can see it."""

    registration: Registration | None
    exists: bool
    subject: str
    status: Preflight | None
    unlanded: int | None
    entries: tuple[str, ...]


class TeardownRecord(NamedTuple):
    """The fact a removal records before it starts: which HEAD it was removing, and when."""

    head: str
    began: str


# The four answers `attribute_teardown` gives, each a distinct instruction downstream:
# proceed, recover the removal, refuse `never reset`, or refuse without assuming.
CLEAN: Final = "clean"
TEARDOWN: Final = "teardown"
UNRECORDED: Final = "unrecorded"
AMBIGUOUS: Final = "ambiguous"

# Lives in the worktree's own git admin directory, so it follows the registration
# rather than the tree's path, and git deletes it exactly when a removal succeeds —
# which is what retires it.
TEARDOWN_RECORD: Final = "teardown-record"


# --------------------------------------------------------------------- parsing


def parse_registrations(porcelain: str) -> tuple[Registration, ...]:
    """Parse `git worktree list --porcelain` into one record per registration.

    The format is blank-line-separated blocks of `key value` lines, where
    `detached`, `bare` and (since 2.36) `prunable` may carry no value at all.
    """
    out: list[Registration] = []
    fields: dict[str, str] = {}
    for raw in porcelain.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            if fields:
                out.append(_registration(fields))
                fields = {}
            continue
        key, _, value = line.partition(" ")
        fields[key] = value
    if fields:
        out.append(_registration(fields))
    return tuple(out)


def _registration(fields: dict[str, str]) -> Registration:
    return Registration(
        path=Path(fields.get("worktree", "")),
        head=fields.get("HEAD", ""),
        branch=fields.get("branch", ""),
        prunable=fields.get("prunable", "") if "prunable" in fields else "",
        bare="bare" in fields,
    )


def read_status(porcelain: str) -> Preflight:
    """Split `git status --porcelain` into tracked changes and untracked files.

    Both refuse, and both are reported verbatim: an agent that has to decide
    whether a file is its own needs the name, not a count.
    """
    tracked: list[str] = []
    untracked: list[str] = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        (untracked if line.startswith("??") else tracked).append(line.rstrip())
    return Preflight(tuple(tracked), tuple(untracked))


# ------------------------------------------------------------- teardown record


def teardown_record_path(tree: Path) -> Path:
    """Return the record's path inside the tree's own git admin directory.

    `git rev-parse --git-path` is git's own answer for where per-worktree state lives,
    so the record follows the registration and can never be confused between a tree
    that was removed and one later recreated under the same name.
    """
    answered = Path(git("rev-parse", "--git-path", TEARDOWN_RECORD, cwd=tree).strip())
    return answered if answered.is_absolute() else tree / answered


def write_teardown_record(tree: Path, head: str) -> None:
    """Record that this recipe's removal is about to start on `tree`, at this HEAD."""
    began = datetime.now(UTC).isoformat(timespec="seconds")
    teardown_record_path(tree).write_text(f"head={head}\nbegan={began}\n", encoding="utf-8")


def read_teardown_record(tree: Path) -> TeardownRecord | None:
    """Read the record back, or `None` where no removal of this tree ever started.

    A record that cannot be read answers `None` too, and that is the safe direction:
    `None` attributes every difference to the session, whose answer is the `never
    reset` refusal — a refusal, never a discard. What `None` can never do is unlock
    the recovery path, so a record this tool wrote but cannot read back costs the
    deadlock back, not work. The same holds where git itself will not answer — a
    broken gitdir is refused as `git_failed` upstream, at the status rung.
    """
    try:
        text = teardown_record_path(tree).read_text(encoding="utf-8")
    except (OSError, GitError, UnicodeDecodeError):
        return None
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    return TeardownRecord(fields.get("head", ""), fields.get("began", ""))


def _unstaged_deletions_only(status: Preflight) -> bool:
    """Whether `git status` holds nothing but ` D` lines — what a part-finished deletion leaves."""
    return not status.untracked and all(line.startswith(" D") for line in status.tracked)


def attribute_teardown(record: TeardownRecord | None, head: str, status: Preflight) -> str:
    """Answer whose the uncommitted differences in a tree are: the removal's, or the session's.

    Four answers, each derived from a record rather than guessed from the dirt (#632):

    - ``clean`` — nothing to attribute.
    - ``teardown`` — a record exists for this exact HEAD and the tree holds nothing
      but unstaged deletions. The tree was clean when the removal started, which is
      the rung the removal passed, so every deletion was made by that removal; and the
      head has not moved since to admit anyone else's work.
    - ``unrecorded`` — no record, so this recipe never began removing this tree and
      the differences are the session's: the `never reset` refusal stands. A removal
      that failed before #632 left no record, and this answer cannot tell that case
      from a session's deletions — it refuses either way, which loses no work and
      costs only the reading of the list.
    - ``ambiguous`` — a record exists and the tree does not match what that removal
      alone could have left: a different HEAD, or anything beyond unstaged deletions.
      Something else has written since the removal began, so the caller refuses
      rather than assume either answer.
    """
    if status.clean:
        return CLEAN
    if record is None:
        return UNRECORDED
    if head != record.head or not _unstaged_deletions_only(status):
        return AMBIGUOUS
    return TEARDOWN


def attribute_teardown_at(tree: Path, status: Preflight) -> str:
    """`attribute_teardown` for a caller holding only the tree and a status read.

    Raises `GitError` where the head could not be read, which the callers' existing
    fail-closed handling turns into `git_failed` — an unread tree never becomes a
    clean one (#375's shape).
    """
    return attribute_teardown(
        read_teardown_record(tree), git("rev-parse", "HEAD", cwd=tree).strip(), status
    )


# --------------------------------------------------------------------- ladders


def classify_name(name: str) -> Refusal | None:
    """Refuse a name that is not one path segment under `.claude/worktrees`."""
    if not name:
        return Refusal(
            "invalid_name",
            ("name=<empty>",),
            "Name the worktree after its issue, e.g. `just worktree add issue-214`.",
        )
    if not VALID_NAME.fullmatch(name):
        return Refusal(
            "invalid_name",
            (f"name={name}", "expected=one segment of [A-Za-z0-9._-], not starting with a dot"),
            "A worktree name is a directory name under .claude/worktrees, not a path. "
            "Use e.g. `issue-214`.",
        )
    return None


def classify_target(path: Path, holder: Holder) -> Refusal | None:
    """Decide whether `path` is free to become a new worktree.

    Three ways it is not, and each names what is there, because #105's damage
    came from an agent not knowing who else was in the tree.
    """
    registration = holder.registration
    if registration is not None and not holder.exists:
        return Refusal(
            "stale_registration",
            (
                f"worktree={path}",
                "registered=yes",
                "directory=missing",
                f"head={registration.head[:7] or '(none)'}",
            ),
            "Run `git worktree prune` yourself once you are sure nothing is using it — "
            "this recipe never prunes for you.",
        )
    if registration is not None:
        return Refusal("worktree_occupied", _holder_lines(path, holder), STOP_AND_REPORT)
    if holder.exists:
        return Refusal(
            "worktree_occupied",
            (
                f"worktree={path}",
                "registered=no",
                "directory=exists",
                f"contents={', '.join(holder.entries) or '(empty)'}",
            ),
            STOP_AND_REPORT,
        )
    return None


def _holder_lines(path: Path, holder: Holder) -> tuple[str, ...]:
    """Name the competing holder: what it is on, and what it would cost to lose."""
    registration = holder.registration
    assert registration is not None  # noqa: S101 — only called on the registered rung
    status = holder.status
    dirty = "unreadable" if status is None else f"{len(status.tracked) + len(status.untracked)}"
    lines = [
        f"worktree={path}",
        "registered=yes",
        f"holder_head={registration.head[:7] or '(none)'} {holder.subject}".rstrip(),
        f"holder_state={registration.state}",
        f"holder_uncommitted={dirty}",
    ]
    if holder.unlanded:
        lines.append(
            f"holder_unlanded={holder.unlanded} commits not proven byte-for-byte on {BASE}"
        )
    return tuple(lines)


def classify_preflight(
    path: Path, status: Preflight, action: str = FOREIGN_FILES
) -> Refusal | None:
    """CLAUDE.md's pre-flight where dirt is provably wrong: a tree nobody has worked in yet.

    `add` runs it on the checkout git has just made, and `done` on a tree its
    owner says is finished with. Anything in either is somebody else's, or
    somebody's unsaved work — never the caller's work in progress, which is why
    this rung is a flat refusal and `classify_exclusivity` is not. The two
    callers differ only in what the agent should do about it, which is why the
    instruction is the argument.
    """
    if status.clean:
        return None
    return Refusal("dirty_tree", _found(path, status), action)


def classify_exclusivity(path: Path, status: Preflight) -> Refusal | None:
    """Answer the mid-run question of whether the tree is still provably the caller's.

    Only "clean" proves it. A dirty tree proves nothing either way, because a
    file the caller wrote five minutes ago and a file another agent wrote five
    minutes ago are the same two lines of `git status` — the tool cannot tell
    them apart and must not pretend to. So it hands back the list and the
    judgement, under the class that says what actually happened: the check could
    not reach a verdict (#41's shape). Calling this `dirty_tree` would refuse
    every agent that has ever edited a file, and a refusal an agent learns to
    ignore is worse than none.
    """
    if status.clean:
        return None
    return Refusal(
        "unverified",
        _found(path, status),
        "Exclusivity is unproven while the tree is dirty: your files and another agent's "
        "look identical here. Read the list. Anything you did not write means stop and "
        "report, never reset (#105); if it is all yours, commit it and check again.",
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


def classify_done(
    path: Path, holder: Holder, record: TeardownRecord | None = None
) -> Refusal | None:
    """Decide whether a worktree is registered, clean, and safe to remove.

    After the presence and clean-status proofs, ``holder.unlanded`` carries
    ``count_unlanded``'s result: each commit unreachable from ``origin/main``
    must be a ``git cherry`` nominee whose full-index binary diff bytes exactly
    match an upstream commit's. ``git cherry`` omits merges, so an unreachable
    merge cannot be nominated and always refuses. A dirty tree is somebody's
    uncommitted work; an unproven commit is somebody's committed work; both
    vanish with the directory, and ``git worktree remove`` only refuses the first.

    The dirty rung asks the teardown record first (#632): dirt a recorded removal
    left behind proceeds to the landed proof rather than refusing, because the
    next step restores exactly that dirt and removes the tree.
    """
    missing = _classify_present(path, holder)
    if missing is not None:
        return missing
    assert holder.registration is not None  # noqa: S101 — _classify_present proved it
    status = holder.status
    if status is None:
        return _could_not_run(path, "status=unreadable")
    dirty = _teardown_dirt_refusal(path, holder, status, record)
    if dirty is not None:
        return dirty
    return _classify_landed(path, holder.unlanded)


def _classify_present(path: Path, holder: Holder) -> Refusal | None:
    """Refuse a name git does not know, and one whose directory has gone."""
    if holder.registration is None:
        return Refusal(
            "no_such_worktree",
            (f"worktree={path}", "registered=no"),
            "Nothing to remove under that name. `just worktree list` shows what is registered.",
        )
    if not holder.exists:
        return Refusal(
            "stale_registration",
            (f"worktree={path}", "registered=yes", "directory=missing"),
            "Run `git worktree prune` yourself once you are sure nothing is using it — "
            "this recipe never prunes for you.",
        )
    return None


def _classify_landed(path: Path, unlanded: int | None) -> Refusal | None:
    """Refuse unless every unreachable commit has an exact change match upstream."""
    if unlanded is None:
        return _could_not_run(path, f"unlanded=unreadable against {BASE}")
    if unlanded:
        return Refusal(
            "unlanded_work",
            (
                f"worktree={path}",
                f"unlanded={unlanded} commits not proven byte-for-byte on {BASE}",
            ),
            "Land them first (`git push origin HEAD:main`) or say so in your report. "
            "Removing this tree now could lose work; patch identity alone never permits "
            "removal, and merge commits remain unproven.",
        )
    return None


def _could_not_run(path: Path, detail: str) -> Refusal:
    """Fail closed: a check that could not run is not a check that passed (#41)."""
    return Refusal(
        "git_failed",
        (f"worktree={path}", detail),
        "A check that could not run is not a check that passed. Nothing was removed.",
    )


def _teardown_dirt_refusal(
    path: Path, holder: Holder, status: Preflight, record: TeardownRecord | None
) -> Refusal | None:
    """Return the dirty rung `classify_done` and `classify_archive` share (#632).

    Asks the teardown record before refusing: dirt a recorded removal left behind
    passes the rung, because the next step restores exactly that dirt and removes
    the tree; an unrecorded tree keeps the plain `dirty_tree` refusal; and a record
    the tree does not match refuses `teardown_ambiguous` without assuming either.
    """
    attribution = attribute_teardown(record, holder.registration.head, status)
    if attribution == AMBIGUOUS:
        return Refusal("teardown_ambiguous", _found(path, status), TEARDOWN_AMBIGUOUS_ACTION)
    if attribution == UNRECORDED:
        return classify_preflight(path, status, UNCOMMITTED_ON_TEARDOWN)
    return None


def classify_archive(
    path: Path,
    holder: Holder,
    ref: str,
    remote_sha: str | None,
    record: TeardownRecord | None = None,
) -> Refusal | None:
    """Decide whether a worktree may be removed against a preservation ref.

    `done` proves each commit through SHA reachability or, for a `git cherry`-
    nominated non-merge, an exact diff on `origin/main`. A preservation ref is a
    different proof: this ladder requires the tree to be registered, present,
    clean, and — the whole point — its exact HEAD verifiably on the remote at
    `ref` (#170, #272). Not "a ref exists", not "the branch name looks right":
    the SHA, confirmed against the remote. The ref is read, never created or
    moved, so a refusal leaves both untouched.

    The dirty rung asks the teardown record first, exactly as `classify_done`'s
    does (#632): archive makes the same `git worktree remove` call and carries
    the same exposure.
    """
    present = _classify_present(path, holder)
    if present is not None:
        return present
    assert holder.registration is not None  # noqa: S101 — _classify_present proved it
    status = holder.status
    if status is None:
        return _could_not_run(path, "status=unreadable")
    dirty = _teardown_dirt_refusal(path, holder, status, record)
    if dirty is not None:
        return dirty
    head = holder.registration.head
    if remote_sha is None:
        return Refusal(
            "not_on_remote",
            (f"worktree={path}", f"ref={ref}", "resolved=no (local-only or absent on origin)"),
            NOT_ON_REMOTE,
        )
    if remote_sha != head:
        return Refusal(
            "ref_mismatch",
            (f"worktree={path}", f"head={head}", f"ref={ref}", f"resolved={remote_sha}"),
            REF_MISMATCH,
        )
    return None


# ------------------------------------------------------------------ git access


class GitError(RuntimeError):
    """A git command this tool depends on failed, and the caller must be told which."""

    def __init__(self, args: tuple[str, ...], stderr: str) -> None:
        """Keep the argv and git's own words, which is what the refusal quotes."""
        super().__init__(f"git {' '.join(args)}: {stderr.strip()}")
        self.args_run = args
        self.stderr = stderr.strip()


def git(*args: str, cwd: Path, check: bool = True, timeout: float | None = None) -> str:
    """Run one git command and return its stdout, raising `GitError` when it fails.

    `timeout` bounds the *call*, not any socket inside it: a read that is still running
    at its deadline has its direct `git` child killed and is raised as `GitError`
    naming the bound — the same whole-call property `bounded_request` buys for
    `urlopen` with a daemon thread's join (#425), on the subprocess a git read already
    is. The kill reaches only that child: helper processes git itself spawned can
    outlive it. A resolver stall, a silent remote, a wedged pack negotiation all expire
    alike; `check` still governs only git's own exit code.
    """
    # S603/S607: the argv is fixed literals plus paths this tool computed, and
    # `git` resolves off PATH on purpose — the repo's toolchain is the caller's.
    try:
        done = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as expired:
        raise GitError(args, f"gave no answer within {timeout}s") from expired
    if check and done.returncode != 0:
        raise GitError(args, done.stderr)
    return done.stdout


def _git_bytes(*args: str, cwd: Path) -> bytes:
    """Run one local git read without decoding or newline conversion."""
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607 — git resolves off PATH by design
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        raise GitError(args, done.stderr.decode("utf-8", errors="replace"))
    return done.stdout


def invalid_commit_sha(sha: str, *, field: str = "sha") -> Refusal | None:
    """Return the one form refusal shared by every commit-recording path."""
    if FULL_COMMIT_SHA.fullmatch(sha):
        return None
    return Refusal(
        "invalid_sha",
        (f"{field}={sha}", COMMIT_SHA_ERROR),
        f"Name the reviewed commit in full — {COMMIT_SHA_ERROR}.",
    )


def validate_commit(repo: Path, sha: str) -> Refusal | None:
    """Ask whether ``sha`` names a commit in ``repo``."""
    if invalid := invalid_commit_sha(sha):
        return invalid
    # S603/S607: fixed git operations plus the caller's SHA, passed as one argv word.
    commit = subprocess.run(  # noqa: S603
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],  # noqa: S607
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        return Refusal(
            "commit_not_found",
            (f"repository={repo}", f"sha={sha}", "commit=missing_or_not_a_commit"),
            "Re-read the full SHA and name a commit this repository holds. Nothing was recorded.",
        )
    return None


def main_checkout(cwd: Path) -> Path:
    """Return the main checkout, which is where `.claude/worktrees` lives.

    `git worktree list` puts the main worktree first from any of them, so this
    answers the same whether the caller ran the recipe from the checkout or from
    inside one of its worktrees.
    """
    registrations = parse_registrations(git("worktree", "list", "--porcelain", cwd=cwd))
    if not registrations:
        raise GitError(("worktree", "list"), "no worktree registrations")
    return registrations[0].path


def read_preflight(path: Path) -> Preflight | None:
    """Read one tree's `git status --porcelain`, or `None` where the read itself failed.

    A failing status command prints nothing, and nothing parses as a *clean*
    tree — so reading it with `check=False` manufactures the very absence the
    pre-flight exists to establish, and hands `check`, `done` and `archive` an
    exclusivity nobody proved (#375, the `tools/review_exchange.py` defect
    #332's round 1 closed on the push path). Failure is `None`, which every
    ladder above already reads as unproven rather than as clean.
    """
    try:
        return read_status(git("status", "--porcelain", cwd=path))
    except GitError:
        return None


def gather(root: Path, path: Path, registrations: tuple[Registration, ...]) -> Holder:
    """Read everything the ladders need about one path, in one place."""
    registration = next((r for r in registrations if r.path == path), None)
    exists = path.exists()
    subject = ""
    status: Preflight | None = None
    unlanded: int | None = None
    entries: tuple[str, ...] = ()
    if registration is not None and registration.head:
        # `check=False`: the subject is a display line beside the head SHA, and a
        # missing one hides nothing — no rung reads it.
        subject = git("log", "-1", "--format=%s", registration.head, cwd=root, check=False).strip()
    if exists and registration is not None:
        status = read_preflight(path)
        unlanded = count_unlanded(path)
    elif exists:
        entries = tuple(sorted(p.name for p in path.iterdir())[:HOW_MANY_SHOWN])
    return Holder(registration, exists, subject, status, unlanded, entries)


def count_unlanded(path: Path) -> int | None:
    """Count unreachable commits not nominated and proven by an exact upstream diff."""
    try:
        unreachable = git("rev-list", f"{BASE}..HEAD", cwd=path).splitlines()
        if not unreachable:
            return 0
        cherries = git("cherry", BASE, "HEAD", cwd=path).splitlines()
        nominees = {line[2:] for line in cherries if line.startswith("- ")}
        if not nominees:
            return len(unreachable)
        upstream = git("rev-list", "--no-merges", f"HEAD..{BASE}", cwd=path).splitlines()
        upstream_diffs = {_exact_commit_diff(path, sha) for sha in upstream}
        return sum(
            sha not in nominees or _exact_commit_diff(path, sha) not in upstream_diffs
            for sha in unreachable
        )
    except GitError:
        return None


def _exact_commit_diff(path: Path, sha: str) -> bytes:
    """Return Git's byte-exact parent-to-commit diff for one non-merge commit."""
    # `git cherry` only nominates: patch IDs discard whitespace and line numbers, and
    # its candidate list omits merges. Neither fact may permit irreversible removal.
    # Full-index binary diff bytes preserve whitespace, hunk locations, paths, modes and
    # full before/after blob IDs; a nominee passes only when every byte equals upstream.
    return _git_bytes(
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        "--ignore-submodules=none",
        "--full-index",
        "--binary",
        "--diff-algorithm=myers",
        "--no-indent-heuristic",
        "-p",
        sha,
        cwd=path,
    )


def remote_ref_sha(root: Path, ref: str, timeout: float = REMOTE_READ_TIMEOUT_S) -> str | None:
    """Return the exact SHA a remote ref resolves to on `origin`, else None.

    `git ls-remote` reads the remote's own ref table, so a ref that lives only
    locally (never pushed) answers None — the #170 incident's check, used
    verbatim. A reachable remote with no such ref exits zero and empty, so None
    is distinct from a network failure, which raises `GitError` (and lands as
    ``git_failed`` at the caller). That separation is what makes "local-only
    ref refuses" and "unreadable remote refuses" two different classes.
    `timeout` defaults to a finite bound because every call of this function
    dials `origin` — an opt-in bound left archive, restore and exchange
    unbounded (#425 round 2). `git()`'s own `None` default stands: most of its
    calls are local.
    """
    out = git("ls-remote", "origin", ref, cwd=root, timeout=timeout).strip()
    if not out:
        return None
    return out.splitlines()[0].split(maxsplit=1)[0]


# --------------------------------------------------------------------- actions


class Report(NamedTuple):
    """One action's whole answer: lines to print and the exit code they carry."""

    lines: tuple[str, ...]
    code: int

    @classmethod
    def refused(cls, refusal: Refusal) -> Report:
        """Render a refusal at the exit code every refusal shares."""
        return cls(refusal.lines(), EXIT_REFUSED)


def add(root: Path, name: str) -> Report:
    """Fetch, create the worktree off `origin/main`, pre-flight it, print the pair."""
    bad_name = classify_name(name)
    if bad_name is not None:
        return Report.refused(bad_name)
    path = root / WORKTREES / name

    registrations = parse_registrations(git("worktree", "list", "--porcelain", cwd=root))
    occupied = classify_target(path, gather(root, path, registrations))
    if occupied is not None:
        return Report.refused(occupied)

    # Bounded (#434): the same whole-call deadline `remote_ref_sha` reads under, so a
    # wedged remote refuses as `git_failed` rather than hanging the protocol's start.
    git("fetch", "origin", cwd=root, timeout=REMOTE_READ_TIMEOUT_S)
    base = git("rev-parse", "--short", BASE, cwd=root).strip()
    git("worktree", "add", str(path), BASE, "--detach", cwd=root)

    # The pre-flight is on the tree we just made, and it can still refuse: a
    # fresh checkout with anything in it means something else is writing there.
    # Nothing is removed on that path — the files are evidence.
    dirty = classify_preflight(path, read_status(git("status", "--porcelain", cwd=path)))
    if dirty is not None:
        return Report.refused(dirty)

    subject = git("log", "-1", "--format=%s", BASE, cwd=root).strip()
    return Report(
        (
            "ok=worktree_created",
            f"worktree={path}",
            f"base={base} {BASE} {subject}".rstrip(),
            "preflight=clean",
            (
                "Work only in that path and commit early. If files you did not write "
                "appear during your run: stop and report, never reset (#105)."
            ),
        ),
        0,
    )


def check(root: Path, name: str) -> Report:
    """Re-run the pre-flight alone. Reads; creates, removes and fetches nothing."""
    path = _named_or_here(root, name)
    if path is None:
        return Report.refused(
            Refusal(
                "invalid_name",
                (f"name={name}",),
                "A worktree name is a directory name under .claude/worktrees, not a path.",
            )
        )
    registrations = parse_registrations(git("worktree", "list", "--porcelain", cwd=root))
    holder = gather(root, path, registrations)
    if holder.registration is None:
        return Report.refused(
            Refusal(
                "no_such_worktree",
                (f"worktree={path}", "registered=no"),
                "Nothing git knows as a worktree is at that path. "
                "`just worktree list` shows what is registered.",
            )
        )
    if not holder.exists:
        return Report.refused(
            Refusal(
                "stale_registration",
                (f"worktree={path}", "registered=yes", "directory=missing"),
                "Run `git worktree prune` yourself once you are sure nothing is using it — "
                "this recipe never prunes for you.",
            )
        )
    if holder.status is None:
        # Unproven for a different reason than a dirty tree is, so it says which:
        # nothing was found in the tree, because nothing could be read from it.
        return Report.refused(
            Refusal(
                "unverified",
                (f"worktree={path}", "registered=yes", "status=unreadable"),
                "The status read itself failed, so exclusivity is unproven — this is not a "
                "report about what the tree contains. Run `git status` there yourself and "
                "read git's own error. An unread tree is never a clean one (#375).",
            )
        )
    unproven = classify_exclusivity(path, holder.status)
    if unproven is not None:
        return Report.refused(unproven)
    head = holder.registration.head[:7] or "(none)"
    unlanded = "unknown" if holder.unlanded is None else str(holder.unlanded)
    return Report(
        (
            "ok=preflight_clean",
            f"worktree={path}",
            f"head={head} {holder.subject}".rstrip(),
            f"unlanded={unlanded}",
        ),
        0,
    )


def _named_or_here(root: Path, name: str) -> Path | None:
    """Return the named worktree's path, or the tree the caller is in."""
    if not name:
        return Path.cwd().resolve()
    if classify_name(name) is not None:
        return None
    return root / WORKTREES / name


def sweep(root: Path) -> Report:
    """One line per registration: where, what it is on, and whether it is finished with.

    No fetch: `unlanded` is judged against whatever `origin/main` this checkout
    last saw, and the header names that SHA so the reading is honest.
    """
    registrations = parse_registrations(git("worktree", "list", "--porcelain", cwd=root))
    # `check=False`: the sweep gates nothing, and a base it could not resolve
    # prints as `(unknown)` rather than as a SHA nobody read.
    base = git("rev-parse", "--short", BASE, cwd=root, check=False).strip() or "(unknown)"
    lines = [f"base={base} {BASE} (local ref, not fetched)", f"registrations={len(registrations)}"]
    stale = 0
    for registration in registrations:
        holder = gather(root, registration.path, registrations)
        if not holder.exists:
            stale += 1
            lines.append(f"stale {registration.path} (directory missing)")
            continue
        status = holder.status
        if status is None:
            dirty = "unreadable"
        elif status.clean:
            dirty = "clean"
        else:
            dirty = f"DIRTY({len(status.tracked) + len(status.untracked)})"
        unlanded = "?" if holder.unlanded is None else str(holder.unlanded)
        lines.append(
            f"live  {registration.path} {registration.head[:7]} "
            f"{registration.state} {dirty} unlanded={unlanded}"
        )
    if stale:
        lines.append(
            f"action=Run `git worktree prune` yourself for the {stale} stale "
            "registration(s) once you are sure nothing is using them."
        )
    return Report(tuple(lines), 0)


def _finish_removal(
    root: Path,
    path: Path,
    holder: Holder,
    ok: tuple[str, ...],
    tail: tuple[str, ...],
) -> Report:
    """Record the removal's start, restore what an interrupted removal deleted, then remove.

    A dirty status reaching here is the teardown-attributed rung — every other dirty
    shape was refused above — so `git checkout -- .` discards nothing but the deletions
    the failed removal itself made: the index is untouched (the shape check admits only
    unstaged deletions), so it restores the recorded HEAD's files and nothing else. The
    record goes down before `git worktree remove`, so a removal that fails part-way is
    recognisable on the retry; and git retires it with the admin directory when the
    removal succeeds.
    """
    status = holder.status
    restored = 0
    if status is not None and not status.clean:
        restored = len(status.tracked)
        git("checkout", "--", ".", cwd=path)
        after = read_preflight(path)
        if after is None or not after.clean:
            return Report.refused(
                _could_not_run(
                    path, "status=dirty after restoring the interrupted removal's deletions"
                )
            )
    if holder.registration is not None:
        with contextlib.suppress(OSError):
            # Best effort: without the record, a later part-failure answers `unrecorded`
            # — the pre-#632 answer, whose refusal discards nothing and never unlocks
            # the recovery path.
            write_teardown_record(path, holder.registration.head)
    try:
        git("worktree", "remove", str(path), cwd=root)
    except GitError as failure:
        return Report.refused(
            Refusal(
                "worktree_remove_failed",
                (
                    f"worktree={path}",
                    f"command=git {' '.join(failure.args_run)}",
                    f"stderr={failure.stderr}",
                ),
                REMOVE_FAILED_ACTION,
            )
        )
    lines = (*ok, f"worktree={path}")
    if restored:
        lines += (f"restored={restored} deletions left by the interrupted removal",)
    return Report((*lines, *tail), 0)


def done(root: Path, name: str) -> Report:
    """Verify clean and the upstream proof for every commit, then remove."""
    bad_name = classify_name(name)
    if bad_name is not None:
        return Report.refused(bad_name)
    path = root / WORKTREES / name
    # `check=False`: a fetch that fails leaves an older `origin/main`, against
    # which exact upstream matches can only be missed — the refusing direction. A
    # fetch that expires at its bound (#434) is tolerated identically: it cannot
    # manufacture an exact match in the older local `origin/main`.
    with contextlib.suppress(GitError):
        git("fetch", "origin", cwd=root, check=False, timeout=REMOTE_READ_TIMEOUT_S)
    registrations = parse_registrations(git("worktree", "list", "--porcelain", cwd=root))
    holder = gather(root, path, registrations)
    present = _classify_present(path, holder)
    if present is not None:
        return Report.refused(present)
    record = read_teardown_record(path)
    refusal = classify_done(path, holder, record)
    if refusal is not None:
        return Report.refused(refusal)
    return _finish_removal(root, path, holder, ok=("ok=worktree_removed",), tail=("unlanded=0",))


def archive(root: Path, name: str, ref: str) -> Report:
    """Verify clean and preserved on a remote ref, then remove. Never on a refusal."""
    bad_name = classify_name(name)
    if bad_name is not None:
        return Report.refused(bad_name)
    if not ref:
        return Report.refused(
            Refusal(
                "invalid_ref",
                (f"worktree={root / WORKTREES / name}", "ref=<empty>"),
                "archive needs the remote ref preserving this HEAD, "
                "e.g. `--ref refs/heads/issue-170-parked`.",
            )
        )
    path = root / WORKTREES / name
    registrations = parse_registrations(git("worktree", "list", "--porcelain", cwd=root))
    holder = gather(root, path, registrations)
    remote_sha = remote_ref_sha(root, ref)
    present = _classify_present(path, holder)
    if present is not None:
        return Report.refused(present)
    record = read_teardown_record(path)
    refusal = classify_archive(path, holder, ref, remote_sha, record)
    if refusal is not None:
        return Report.refused(refusal)
    head = holder.registration.head
    return _finish_removal(
        root,
        path,
        holder,
        ok=("ok=worktree_archived",),
        tail=(
            f"head={head}",
            f"ref={ref} resolved={remote_sha}",
            "preserved=yes (remote ref, not origin/main)",
        ),
    )


def restore(root: Path, name: str, ref: str) -> Report:
    """Recreate a detached worktree from a remote ref, then pre-flight it like ``add``."""
    bad_name = classify_name(name)
    if bad_name is not None:
        return Report.refused(bad_name)
    if not ref:
        return Report.refused(
            Refusal(
                "invalid_ref",
                (f"worktree={root / WORKTREES / name}", "ref=<empty>"),
                "restore needs the remote ref to recreate from, "
                "e.g. `--ref refs/heads/issue-170-parked`.",
            )
        )
    path = root / WORKTREES / name
    registrations = parse_registrations(git("worktree", "list", "--porcelain", cwd=root))
    occupied = classify_target(path, gather(root, path, registrations))
    if occupied is not None:
        return Report.refused(occupied)
    sha = remote_ref_sha(root, ref)
    if sha is None:
        return Report.refused(
            Refusal(
                "not_on_remote",
                (f"worktree={path}", f"ref={ref}", "resolved=no (local-only or absent on origin)"),
                "Nothing to restore from: the ref is not on the remote. "
                "Push it first, or point --ref at one that is.",
            )
        )
    # Bounded (#434): one call after the already-bounded `remote_ref_sha`, so the
    # fetch of the ref it resolved cannot hang where the read that named it did not.
    git("fetch", "origin", ref, cwd=root, timeout=REMOTE_READ_TIMEOUT_S)
    git("worktree", "add", str(path), sha, "--detach", cwd=root)
    dirty = classify_preflight(path, read_status(git("status", "--porcelain", cwd=path)))
    if dirty is not None:
        return Report.refused(dirty)
    # `check=False`: as in `gather`, the subject is display beside a SHA already
    # verified on the remote, and its absence decides nothing.
    subject = git("log", "-1", "--format=%s", sha, cwd=root, check=False).strip()
    return Report(
        (
            "ok=worktree_restored",
            f"worktree={path}",
            f"base={sha[:7]} {ref} {subject}".rstrip(),
            "preflight=clean",
            "Restored off a preservation ref, not origin/main. An archive is not a landing.",
        ),
        0,
    )


def restore_commit(root: Path, name: str, sha: str) -> Report:
    """Recreate a detached worktree from an explicit full commit SHA."""
    bad_name = classify_name(name)
    if bad_name is not None:
        return Report.refused(bad_name)
    invalid = invalid_commit_sha(sha)
    if invalid is not None:
        return Report.refused(invalid)
    path = root / WORKTREES / name
    registrations = parse_registrations(git("worktree", "list", "--porcelain", cwd=root))
    occupied = classify_target(path, gather(root, path, registrations))
    if occupied is not None:
        return Report.refused(occupied)
    missing = validate_commit(root, sha)
    if missing is not None:
        return Report.refused(missing)
    git("worktree", "add", str(path), sha, "--detach", cwd=root)
    dirty = classify_preflight(path, read_status(git("status", "--porcelain", cwd=path)))
    if dirty is not None:
        return Report.refused(dirty)
    subject = git("log", "-1", "--format=%s", sha, cwd=root, check=False).strip()
    return Report(
        (
            "ok=worktree_restored",
            f"worktree={path}",
            f"base={sha[:7]} commit={sha} {subject}".rstrip(),
            "preflight=clean",
            "Restored from the requested base commit, not a preservation ref.",
        ),
        0,
    )


# ------------------------------------------------------------------ invocation


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """One action defaulting to ``check``, and its name where it takes one."""
    parser = argparse.ArgumentParser(prog="just worktree", description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        default="check",
        choices=("add", "check", "list", "done", "archive", "restore"),
    )
    parser.add_argument("name", nargs="?", default="")
    parser.add_argument("--ref", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one action, print its lines, and exit what it decided."""
    args = parse_args(argv)
    try:
        root = main_checkout(Path.cwd())
        if args.action == "add":
            report = add(root, args.name)
        elif args.action == "check":
            report = check(root, args.name)
        elif args.action == "list":
            report = sweep(root)
        elif args.action == "archive":
            report = archive(root, args.name, args.ref)
        elif args.action == "restore":
            report = restore(root, args.name, args.ref)
        else:
            report = done(root, args.name)
    except GitError as failure:
        # Fail closed, with git's own words: a step of the protocol that did not
        # run is not a step that passed (#41's shape).
        report = Report.refused(
            Refusal(
                "git_failed",
                (f"command=git {' '.join(failure.args_run)}", f"stderr={failure.stderr}"),
                "Read git's own error above. Nothing was created, moved or removed.",
            )
        )
    stream = sys.stdout if report.code == 0 else sys.stderr
    for line in report.lines:
        print(line, file=stream)
    return report.code


if __name__ == "__main__":
    sys.exit(main())
