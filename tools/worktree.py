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
  and the judgement left where it belongs.
- ``list``         the hygiene sweep: every registration, its state, whether its
  HEAD is landed, and which registrations are stale.
- ``done <name>``  verify clean and landed, then remove. Never ``--force``.
  Remains landed-on-``origin/main`` only: durability is explicit through the
  archive call, never inferred from arbitrary refs (#272).
- ``archive <name> --ref <remote-ref>``  verify the tree is clean and the named
  remote ref resolves to its exact HEAD, then remove the worktree. The ref is
  read, never created or moved — it is the preservation act a handoff pushed,
  and removal proceeds only on the evidence that the exact HEAD SHA is on the
  remote (``git ls-remote``, the check the #170 incident used). Not a landing:
  it never prints ``done`` or ``landed``.
- ``restore <name> --ref <remote-ref>``  recreate a detached worktree from that
  exact remote ref and run the same exclusivity pre-flight as ``add``, so
  recovery stays in the protocol rather than a remembered bare-git recipe.

**Nothing here resets, cleans, prunes or removes on a refusal path.** CLAUDE.md
is explicit that foreign files mean stop and report, and a recipe that tidies is
a recipe that destroys the work of whoever else is in that tree. `add` does not
even remove the worktree it has just created when the pre-flight refuses it: the
files it found are evidence, and something wrote them.

Refusals are named, and each says what was found and what to do:
``worktree_occupied`` (naming the other holder — #105's damage came from not
knowing), ``dirty_tree``, ``unverified``, ``stale_registration``,
``unlanded_work``, ``no_such_worktree``, ``invalid_name``, ``invalid_ref``,
``not_on_remote``, ``ref_mismatch``, ``git_failed``. Exit 0 is proceed, 1 is a
refusal; the class is the first line, in the tier's ``key=value`` form.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Final, NamedTuple

BASE: Final = "origin/main"
WORKTREES: Final = Path(".claude") / "worktrees"
EXIT_REFUSED: Final = 1

# A worktree name becomes a path segment under .claude/worktrees, so it is one
# segment: no separators, no leading dot, nothing that walks upwards.
VALID_NAME: Final = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")

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
        lines.append(f"holder_unlanded={holder.unlanded} commits not on {BASE}")
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


def classify_done(path: Path, holder: Holder) -> Refusal | None:
    """Decide whether a worktree is finished with: registered, clean, and landed.

    The order is the order the damage runs in. A dirty tree is somebody's
    uncommitted work; unlanded commits are somebody's committed work; both
    vanish with the directory, and `git worktree remove` only refuses the first.
    """
    missing = _classify_present(path, holder)
    if missing is not None:
        return missing
    status = holder.status
    if status is None:
        return _could_not_run(path, "status=unreadable")
    dirty = classify_preflight(path, status, UNCOMMITTED_ON_TEARDOWN)
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
    """Refuse a removal that would take commits `origin/main` has never seen."""
    if unlanded is None:
        return _could_not_run(path, f"unlanded=unreadable against {BASE}")
    if unlanded:
        return Refusal(
            "unlanded_work",
            (f"worktree={path}", f"unlanded={unlanded} commits not on {BASE}"),
            f"Land them first (`git push origin HEAD:main`) or say so in your report. "
            f"Removing this tree now loses {unlanded} commits.",
        )
    return None


def _could_not_run(path: Path, detail: str) -> Refusal:
    """Fail closed: a check that could not run is not a check that passed (#41)."""
    return Refusal(
        "git_failed",
        (f"worktree={path}", detail),
        "A check that could not run is not a check that passed. Nothing was removed.",
    )


def classify_archive(
    path: Path, holder: Holder, ref: str, remote_sha: str | None
) -> Refusal | None:
    """Decide whether a worktree may be removed against a preservation ref.

    `done`'s ladder equates "not on `origin/main`" with "not durable", which is
    right for a local-only commit and wrong for a tree a handoff has pushed to a
    preservation ref (#170, #272). This ladder is the explicit durability call:
    the tree must still be registered, present, clean, and — the whole point —
    its exact HEAD must be verifiably on the remote at `ref`. Not "a ref exists",
    not "the branch name looks right": the SHA, confirmed against the remote.
    The ref is read, never created or moved, so a refusal leaves both untouched.
    """
    present = _classify_present(path, holder)
    if present is not None:
        return present
    status = holder.status
    if status is None:
        return _could_not_run(path, "status=unreadable")
    dirty = classify_preflight(path, status, UNCOMMITTED_ON_TEARDOWN)
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


def git(*args: str, cwd: Path, check: bool = True) -> str:
    """Run one git command and return its stdout, raising `GitError` when it fails."""
    # S603/S607: the argv is fixed literals plus paths this tool computed, and
    # `git` resolves off PATH on purpose — the repo's toolchain is the caller's.
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and done.returncode != 0:
        raise GitError(args, done.stderr)
    return done.stdout


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


def gather(root: Path, path: Path, registrations: tuple[Registration, ...]) -> Holder:
    """Read everything the ladders need about one path, in one place."""
    registration = next((r for r in registrations if r.path == path), None)
    exists = path.exists()
    subject = ""
    status: Preflight | None = None
    unlanded: int | None = None
    entries: tuple[str, ...] = ()
    if registration is not None and registration.head:
        subject = git("log", "-1", "--format=%s", registration.head, cwd=root, check=False).strip()
    if exists and registration is not None:
        status = read_status(git("status", "--porcelain", cwd=path, check=False))
        unlanded = count_unlanded(path)
    elif exists:
        entries = tuple(sorted(p.name for p in path.iterdir())[:HOW_MANY_SHOWN])
    return Holder(registration, exists, subject, status, unlanded, entries)


def count_unlanded(path: Path) -> int | None:
    """How many commits this worktree's HEAD carries that `origin/main` does not."""
    counted = git("rev-list", "--count", f"{BASE}..HEAD", cwd=path, check=False).strip()
    return int(counted) if counted.isdigit() else None


def remote_ref_sha(root: Path, ref: str) -> str | None:
    """Return the exact SHA a remote ref resolves to on `origin`, else None.

    `git ls-remote` reads the remote's own ref table, so a ref that lives only
    locally (never pushed) answers None — the #170 incident's check, used
    verbatim. A reachable remote with no such ref exits zero and empty, so None
    is distinct from a network failure, which raises `GitError` (and lands as
    ``git_failed`` at the caller). That separation is what makes "local-only
    ref refuses" and "unreadable remote refuses" two different classes.
    """
    out = git("ls-remote", "origin", ref, cwd=root).strip()
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

    git("fetch", "origin", cwd=root)
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
    if not holder.exists or holder.status is None:
        return Report.refused(
            Refusal(
                "stale_registration",
                (f"worktree={path}", "registered=yes", "directory=missing"),
                "Run `git worktree prune` yourself once you are sure nothing is using it — "
                "this recipe never prunes for you.",
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
        dirty = "clean" if status is not None and status.clean else "DIRTY"
        if status is not None and not status.clean:
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


def done(root: Path, name: str) -> Report:
    """Verify clean and landed, then remove. Never `--force`, never on a refusal."""
    bad_name = classify_name(name)
    if bad_name is not None:
        return Report.refused(bad_name)
    path = root / WORKTREES / name
    git("fetch", "origin", cwd=root, check=False)
    registrations = parse_registrations(git("worktree", "list", "--porcelain", cwd=root))
    holder = gather(root, path, registrations)
    refusal = classify_done(path, holder)
    if refusal is not None:
        return Report.refused(refusal)
    git("worktree", "remove", str(path), cwd=root)
    return Report(("ok=worktree_removed", f"worktree={path}", "unlanded=0"), 0)


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
    refusal = classify_archive(path, holder, ref, remote_sha)
    if refusal is not None:
        return Report.refused(refusal)
    git("worktree", "remove", str(path), cwd=root)
    head = holder.registration.head
    return Report(
        (
            "ok=worktree_archived",
            f"worktree={path}",
            f"head={head}",
            f"ref={ref} resolved={remote_sha}",
            "preserved=yes (remote ref, not origin/main)",
        ),
        0,
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
    git("fetch", "origin", ref, cwd=root)
    git("worktree", "add", str(path), sha, "--detach", cwd=root)
    dirty = classify_preflight(path, read_status(git("status", "--porcelain", cwd=path)))
    if dirty is not None:
        return Report.refused(dirty)
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
