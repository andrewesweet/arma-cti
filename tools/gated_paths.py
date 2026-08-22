#!/usr/bin/env python3
"""Guard path-identifiable sign-off gates at ``just check`` (#500).

Claude Code's ``protect-gated-paths.py`` hook still gives immediate feedback for
the write classes it has always denied.  This module owns that hook's path data
and the broader path-identifiable subset of AGENTS.md's human sign-off gates, so
the hook and the lane-neutral gate cannot drift onto separate lists.

An explicit human approval is one versioned record below
``~/.arma-cti/gated-path-approvals/``.  It names the issue and one path, and is
bound to that path's baseline and exact resulting bytes.  Another edit to the
same path therefore computes another identity and cannot reuse the record.  A
changed ADR carrying ADR-0013's exact ``Delegated-decision: yes`` line remains
the standing-authorisation route AGENTS.md defines.

The approval command refuses a dispatched session.  Like #398's interactive
authorship record, that is a mechanical floor rather than an identity proof: a
same-user process can strip ``CTI_DISPATCH_ID`` or forge local bytes.  Every
verdict states that limit, plus the semantic sign-off gates a path scan cannot
recognise and the content/quality judgement it never performs.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import posixpath
import pwd
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

BASE: Final = "origin/main"
APPROVAL_VERSION: Final = 1
RECORD_MODE: Final = 0o600
APPROVAL_SOURCE: Final = "declared_human"
APPROVER_SOURCE: Final = "os_user"
DELEGATED_DECISION_MARKER: Final = "Delegated-decision: yes"
CONTENT_ID: Final = re.compile(r"\A[0-9a-f]{64}\Z")
ISSUE_WORKTREE: Final = re.compile(r"\Aissue-(\d+)\Z")
APPROVAL_ROOT: Final = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".arma-cti" / "gated-path-approvals"

FILE: Final = "file"
TREE: Final = "tree"
SEGMENT: Final = "segment"

APPROVAL_UNREADABLE: Final = "approval_unreadable"
APPROVAL_FROM_DISPATCH: Final = "approval_from_dispatch"
INVALID_ISSUE: Final = "invalid_issue"
APPROVAL_ISSUE_MISMATCH: Final = "approval_issue_mismatch"
PATH_NOT_GATED: Final = "path_not_gated"
GATED_PATHS_UNREADABLE: Final = "gated_paths_unreadable"
PATH_NOT_CHANGED: Final = "path_not_changed"
INVALID_CONTENT_ID: Final = "invalid_content_id"
GATED_CONTENT_UNREADABLE: Final = "gated_content_unreadable"
CONTENT_CHANGED: Final = "content_changed"
APPROVAL_UNWRITTEN: Final = "approval_unwritten"

LIMIT_LINE: Final = "not_verified=content_or_quality,human_identity,semantic_gates"
SAME_USER_LIMIT: Final = (
    "limit=approval command refuses CTI_DISPATCH_ID, but every session runs as the same user; "
    "this protects against the accident and shortcut, not a deceptive agent"
)


class PathGate(NamedTuple):
    """One path rule and the two controls that consume it."""

    target: str
    shape: str
    reason: str
    requires_approval: bool
    deny_at_write: bool

    def matches(self, path: str) -> bool:
        """Whether a normalised repository-relative path meets this rule."""
        parts = tuple(part for part in path.split("/") if part)
        if self.shape == FILE:
            return path == self.target
        if self.shape == TREE:
            return path == self.target or path.startswith(f"{self.target}/")
        return self.target in parts


# One path authority. ``deny_at_write`` preserves the hook contract AGENTS.md states:
# generated files and acceptance specs get immediate Claude feedback.  The approval
# gate also covers every stable path in the human sign-off paragraph.  Snapshot-schema
# semantics, perceptual-checklist growth and gameplay balance/feel are semantic, so no
# path entry pretends to recognise them; LIMIT_LINE names that remainder on every run.
PATH_GATES: Final = (
    PathGate(
        "tests/specs",
        TREE,
        (
            "Acceptance spec. Specs encode human intent and are sign-off gated"
            " (AGENTS.md); propose the change to the user instead of editing."
        ),
        requires_approval=True,
        deny_at_write=True,
    ),
    PathGate(
        "AGENTS.md",
        FILE,
        "Project instructions are a human sign-off gate.",
        requires_approval=True,
        deny_at_write=False,
    ),
    PathGate(
        "CLAUDE.md",
        FILE,
        "Project instructions are a human sign-off gate.",
        requires_approval=True,
        deny_at_write=False,
    ),
    PathGate(
        "CONTEXT.md",
        FILE,
        "Domain-term changes are a human sign-off gate.",
        requires_approval=True,
        deny_at_write=False,
    ),
    PathGate(
        "docs/adr",
        TREE,
        "New and changed ADRs are a human sign-off gate.",
        requires_approval=True,
        deny_at_write=False,
    ),
    PathGate(
        ".claude/skills",
        TREE,
        "Project skills are a human sign-off gate.",
        requires_approval=True,
        deny_at_write=False,
    ),
    PathGate(
        "generated",
        SEGMENT,
        "Generated file. Edit the schema source and regenerate; never hand-edit.",
        requires_approval=False,
        deny_at_write=True,
    ),
)


class GitError(RuntimeError):
    """A Git read the verdict needs failed."""

    def __init__(self, args: tuple[str, ...], stderr: str) -> None:
        """Keep Git's argv and stderr for the typed refusal."""
        super().__init__(f"git {' '.join(args)}: {stderr.strip()}")
        self.args_run = args
        self.stderr = stderr.strip()


class ApprovalError(RuntimeError):
    """A typed refusal from the approval writer."""

    def __init__(self, kind: str, detail: str, action: str) -> None:
        """Keep the refusal class, evidence and remedy together."""
        super().__init__(detail)
        self.kind = kind
        self.detail = detail
        self.action = action


class Report(NamedTuple):
    """Rendered gate output and its process exit."""

    lines: tuple[str, ...]
    exit_code: int


class Approval(NamedTuple):
    """One validated, content-bound direct approval."""

    issue: int
    path: str
    content_id: str
    approved_at: str
    approved_by: str


def _normalise_path(path: str, root: Path | None = None) -> str:
    """Return a repository-shaped path for hook and Git callers."""
    candidate = Path(path)
    if candidate.is_absolute() and root is not None:
        try:
            path = candidate.resolve(strict=False).relative_to(root.resolve()).as_posix()
        except ValueError:
            return ""
    else:
        path = path.replace(os.sep, "/")
    normalised = posixpath.normpath(path)
    while normalised.startswith("../"):
        # The Bash reader does not model ``cd``.  The old ``*tests/specs/*`` glob
        # nevertheless caught a target spelled from a child directory; retain that
        # safe-side reading without making an absolute path outside ``root`` match.
        normalised = normalised.removeprefix("../")
    return normalised.removeprefix("./")


def gates_for_path(path: str, *, root: Path | None = None) -> tuple[PathGate, ...]:
    """Return every authoritative rule matching ``path``."""
    normalised = _normalise_path(path, root)
    if not normalised:
        return ()
    return tuple(gate for gate in PATH_GATES if gate.matches(normalised))


def signoff_gate(path: str, *, root: Path | None = None) -> PathGate | None:
    """Return the sign-off rule for ``path``, or ``None``."""
    return next(
        (gate for gate in gates_for_path(path, root=root) if gate.requires_approval),
        None,
    )


def hook_denial(path: str, *, root: Path | None = None) -> str | None:
    """Return the immediate hook denial for ``path``, or ``None``."""
    return next(
        (gate.reason for gate in gates_for_path(path, root=root) if gate.deny_at_write),
        None,
    )


def _git_bytes(*args: str, cwd: Path) -> bytes:
    """Run one local Git read without decoding path or content bytes."""
    # S603/S607: fixed executable; arguments are fixed literals or paths Git named.
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        raise GitError(args, done.stderr.decode("utf-8", errors="replace"))
    return done.stdout


def changed_paths(root: Path) -> tuple[str, ...]:
    """Return committed, staged, unstaged and untracked paths against ``origin/main``."""
    changed = _git_bytes(
        "diff",
        "--name-only",
        "--no-renames",
        "--no-ext-diff",
        "-z",
        BASE,
        "--",
        cwd=root,
    )
    untracked = _git_bytes(
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        cwd=root,
    )
    try:
        decoded = [item.decode("utf-8") for item in (changed + untracked).split(b"\0") if item]
    except UnicodeDecodeError as unreadable:
        raise GitError(
            ("diff", "--name-only", BASE), f"non-UTF-8 path: {unreadable}"
        ) from unreadable
    return tuple(dict.fromkeys(decoded))


def _current_payload(root: Path, path: str) -> bytes:
    """Describe exact current bytes and Git-relevant mode for one path."""
    target = root / path
    try:
        mode = target.lstat().st_mode
    except FileNotFoundError:
        return b"absent\0"
    if stat.S_ISLNK(mode):
        return b"120000\0" + os.fsencode(target.readlink())
    if stat.S_ISREG(mode):
        git_mode = b"100755" if mode & stat.S_IXUSR else b"100644"
        try:
            return git_mode + b"\0" + target.read_bytes()
        except OSError as unreadable:
            raise GitError(("read", path), str(unreadable)) from unreadable
    raise GitError(("read", path), "path is neither a regular file, symlink, nor deletion")


def content_id_of(root: Path, path: str) -> str:
    """Bind one path to its baseline entry and exact resulting bytes."""
    baseline = _git_bytes("ls-tree", "-z", BASE, "--", path, cwd=root)
    payload = b"gated-path-content-v1\0" + path.encode("utf-8") + b"\0" + baseline
    payload += b"current\0" + _current_payload(root, path)
    return hashlib.sha256(payload).hexdigest()


def approval_path(root: Path, issue: int, content_id: str) -> Path:
    """Return the content-addressed record path for one issue."""
    return root / str(issue) / f"{content_id}.json"


def _record_fault(document: object, expected: Approval) -> str:
    """Say why stored bytes are not the record this tool writes."""
    if not isinstance(document, dict):
        return f"record is not an object: {document!r}"
    expected_keys = {
        "version",
        "issue",
        "path",
        "content_id",
        "base",
        "approved_at",
        "approved_by",
        "approved_by_source",
        "source",
    }
    if set(document) != expected_keys:
        return f"keys={sorted(document)} expected={sorted(expected_keys)}"
    expected_values: dict[str, object] = {
        "version": APPROVAL_VERSION,
        "issue": expected.issue,
        "path": expected.path,
        "content_id": expected.content_id,
        "base": BASE,
        "approved_by_source": APPROVER_SOURCE,
        "source": APPROVAL_SOURCE,
    }
    for key, value in expected_values.items():
        if document.get(key) != value:
            return f"{key}={document.get(key)!r} expected={value!r}"
    for key in ("approved_at", "approved_by"):
        value = document.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"{key}={value!r}"
    return ""


def read_approval(path: Path, expected: Approval) -> Approval:
    """Read and validate one record; absence is handled by the caller."""
    try:
        details = path.stat()
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as unreadable:
        raise ApprovalError(
            APPROVAL_UNREADABLE,
            f"record={path} reason={unreadable}",
            "Repair or re-record this exact approval. An unreadable record is not approval.",
        ) from unreadable
    mode = stat.S_IMODE(details.st_mode)
    if not stat.S_ISREG(details.st_mode) or mode != RECORD_MODE or details.st_uid != os.getuid():
        raise ApprovalError(
            APPROVAL_UNREADABLE,
            (
                f"record={path} regular={stat.S_ISREG(details.st_mode)}"
                f" mode={mode:04o} owner={details.st_uid}"
            ),
            "Restore a regular 0600 record owned by the current user, or re-record it.",
        )
    fault = _record_fault(document, expected)
    if fault:
        raise ApprovalError(
            APPROVAL_UNREADABLE,
            f"record={path} reason={fault}",
            (
                "Re-record this exact approval through `just gated-paths approve`;"
                " hand-shaped bytes do not clear the gate."
            ),
        )
    return Approval(
        int(document["issue"]),
        str(document["path"]),
        str(document["content_id"]),
        str(document["approved_at"]),
        str(document["approved_by"]),
    )


def delegated_decisions(root: Path, paths: Sequence[str]) -> tuple[str, ...]:
    """Return changed ADRs carrying ADR-0013's exact marker line."""
    found: list[str] = []
    for path in paths:
        gate = signoff_gate(path)
        if gate is None or gate.target != "docs/adr":
            continue
        try:
            lines = (root / path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        if DELEGATED_DECISION_MARKER in lines:
            found.append(path)
    return tuple(found)


def issue_of(root: Path, environ: Mapping[str, str]) -> tuple[int | None, str]:
    """Resolve the issue from worktree name and dispatch environment, refusing disagreement."""
    named_match = ISSUE_WORKTREE.fullmatch(root.name)
    named = int(named_match.group(1)) if named_match else None
    raw = environ.get("CTI_DISPATCH_ISSUE", "").strip()
    dispatched = int(raw) if raw.isdigit() and int(raw) > 0 else None
    if raw and dispatched is None:
        return None, f"CTI_DISPATCH_ISSUE={raw!r} is not a positive issue number"
    if named is not None and dispatched is not None and named != dispatched:
        return None, f"worktree_issue={named} dispatch_issue={dispatched} disagree"
    return named or dispatched, ""


def _refused(kind: str, found: Sequence[str], action: str) -> Report:
    return Report(
        (
            "gated_paths=refused",
            f"refusal={kind}",
            *found,
            f"action={action}",
            LIMIT_LINE,
            SAME_USER_LIMIT,
        ),
        1,
    )


def check(  # noqa: PLR0911 — one complete report per fail-closed read
    root: Path,
    approvals: Path,
    *,
    issue: int | None,
) -> Report:
    """Check every path-identifiable sign-off change against its authorisation."""
    try:
        paths = changed_paths(root)
    except GitError as failure:
        return _refused(
            GATED_PATHS_UNREADABLE,
            (f"command=git {' '.join(failure.args_run)}", f"stderr={failure.stderr}"),
            (
                "Restore a readable origin/main and worktree; a path scan that did"
                " not run is not a pass."
            ),
        )
    gated = tuple(path for path in paths if signoff_gate(path) is not None)
    if not gated:
        return Report(
            ("gated_paths=ok changed=0", "verified=path_scan", LIMIT_LINE, SAME_USER_LIMIT),
            0,
        )

    delegated = delegated_decisions(root, paths)
    if delegated:
        return Report(
            (
                f"gated_paths=ok changed={len(gated)} authorization=delegated_decision",
                *(f"delegated_record={path}" for path in delegated),
                "verified=path_scan,delegated_marker",
                LIMIT_LINE,
                SAME_USER_LIMIT,
            ),
            0,
        )
    if issue is None:
        return _refused(
            "approval_issue_unknown",
            tuple(f"path={path}" for path in gated),
            (
                "Run from an issue-N worktree or its dispatch. Approval records are"
                " issue-bound and the issue was not guessed."
            ),
        )

    approved: list[str] = []
    for path in gated:
        try:
            content_id = content_id_of(root, path)
        except GitError as failure:
            return _refused(
                GATED_CONTENT_UNREADABLE,
                (
                    f"path={path}",
                    f"command={' '.join(failure.args_run)}",
                    f"stderr={failure.stderr}",
                ),
                (
                    "Restore a readable baseline and path; content that could not be"
                    " bound cannot be approved."
                ),
            )
        record = approval_path(approvals, issue, content_id)
        expected = Approval(issue, path, content_id, "expected", "expected")
        if not record.exists():
            command = (
                "just gated-paths approve"
                f" --issue {issue} --path {shlex.quote(path)} --content-id {content_id}"
            )
            return _refused(
                "approval_missing",
                (
                    f"issue={issue}",
                    f"path={path}",
                    f"content_id={content_id}",
                    f"record={record}",
                ),
                (
                    f"After the human reviews this exact change, they run `{command}`."
                    " A session must not run it."
                ),
            )
        try:
            read_approval(record, expected)
        except ApprovalError as refusal:
            return _refused(refusal.kind, (f"path={path}", refusal.detail), refusal.action)
        approved.append(
            f"approval=recorded issue={issue} path={path} content_id={content_id} record={record}"
        )
    return Report(
        (
            f"gated_paths=ok changed={len(gated)} authorization=recorded",
            *approved,
            "verified=path_scan,record_shape,content_binding",
            LIMIT_LINE,
            SAME_USER_LIMIT,
        ),
        0,
    )


@contextmanager
def _approval_lock(root: Path, issue: int) -> Iterator[None]:
    """Serialise record creation for one issue."""
    directory = root / str(issue)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = directory / "approval.lock"
    handle = os.open(lock, os.O_CREAT | os.O_WRONLY, RECORD_MODE)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        os.close(handle)


def _write_record(target: Path, document: str) -> None:
    """Atomically write one 0600 record beside its final name."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=".approval-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, RECORD_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(document)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def record_approval(  # noqa: C901, PLR0913 — validation ladder; one input per recorded fact
    root: Path,
    approvals: Path,
    *,
    issue: int,
    path: str,
    expected_content_id: str,
    approved_at: str,
    approved_by: str,
    environ: Mapping[str, str],
) -> tuple[Approval, Path, bool]:
    """Write a direct approval after recomputing its exact content binding."""
    dispatch_id = environ.get("CTI_DISPATCH_ID", "").strip()
    if dispatch_id:
        raise ApprovalError(
            APPROVAL_FROM_DISPATCH,
            f"dispatch={dispatch_id}",
            (
                "A dispatched session cannot approve its own change. Ask the human"
                " to run the exact command from the refusal."
            ),
        )
    if issue <= 0:
        raise ApprovalError(INVALID_ISSUE, f"issue={issue}", "Name a positive issue number.")
    named, mismatch = issue_of(root, {})
    if mismatch or (named is not None and named != issue):
        detail = mismatch or f"worktree_issue={named} asked_issue={issue}"
        raise ApprovalError(
            APPROVAL_ISSUE_MISMATCH,
            detail,
            "Run the command in the worktree for the issue whose content was approved.",
        )
    normalised = _normalise_path(path)
    if not normalised or signoff_gate(normalised) is None:
        raise ApprovalError(
            PATH_NOT_GATED,
            f"path={path!r}",
            "Name one changed path from the gate's approval_missing refusal.",
        )
    try:
        paths = changed_paths(root)
    except GitError as failure:
        raise ApprovalError(
            GATED_PATHS_UNREADABLE,
            f"command=git {' '.join(failure.args_run)} stderr={failure.stderr}",
            "Restore a readable origin/main and worktree, then retry.",
        ) from failure
    if normalised not in paths:
        raise ApprovalError(
            PATH_NOT_CHANGED,
            f"path={normalised}",
            "Approve only a path in the current diff; a standing path approval is forbidden.",
        )
    if not CONTENT_ID.fullmatch(expected_content_id):
        raise ApprovalError(
            INVALID_CONTENT_ID,
            f"content_id={expected_content_id!r}",
            "Paste the 64-character content_id from the gate refusal.",
        )
    try:
        actual = content_id_of(root, normalised)
    except GitError as failure:
        raise ApprovalError(
            GATED_CONTENT_UNREADABLE,
            (f"path={normalised} command={' '.join(failure.args_run)} stderr={failure.stderr}"),
            "Restore the readable path and baseline, then retry.",
        ) from failure
    if actual != expected_content_id:
        raise ApprovalError(
            CONTENT_CHANGED,
            f"path={normalised} asked={expected_content_id} actual={actual}",
            (
                "Review the changed content and use its new content_id. The earlier"
                " approval cannot carry."
            ),
        )

    approval = Approval(issue, normalised, actual, approved_at, approved_by)
    target = approval_path(approvals, issue, actual)
    with _approval_lock(approvals, issue):
        if target.exists():
            read_approval(target, approval)
            return approval, target, False
        document = {
            "version": APPROVAL_VERSION,
            "issue": issue,
            "path": normalised,
            "content_id": actual,
            "base": BASE,
            "approved_at": approved_at,
            "approved_by": approved_by,
            "approved_by_source": APPROVER_SOURCE,
            "source": APPROVAL_SOURCE,
        }
        try:
            _write_record(target, json.dumps(document, indent=2, sort_keys=True) + "\n")
        except OSError as unwritable:
            raise ApprovalError(
                APPROVAL_UNWRITTEN,
                f"record={target} reason={unwritable}",
                "Nothing was recorded. Restore the approval store and retry.",
            ) from unwritable
    return approval, target, True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gated-paths", description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    check_parser = commands.add_parser("check", help="check the current tree")
    check_parser.add_argument("--root", type=Path, default=Path.cwd())
    approve = commands.add_parser("approve", help="record one human approval")
    approve.add_argument("--root", type=Path, default=Path.cwd())
    approve.add_argument("--issue", type=int, required=True)
    approve.add_argument("--path", required=True)
    approve.add_argument("--content-id", required=True)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    approval_root: Path = APPROVAL_ROOT,
    clock: Callable[[], datetime] | None = None,
    environ: Mapping[str, str] | None = None,
    approved_by: str | None = None,
) -> int:
    """Run the lane-neutral check or the human-only approval writer."""
    args = _parser().parse_args(argv)
    environment = os.environ if environ is None else environ
    root = args.root.resolve()
    if args.action == "check":
        issue, issue_error = issue_of(root, environment)
        if issue_error:
            report = _refused(
                "approval_issue_unknown",
                (issue_error,),
                "Run from the issue worktree with its unmodified dispatch environment.",
            )
        else:
            report = check(root, approval_root, issue=issue)
        print("\n".join(report.lines))  # noqa: T201 — CLI contract
        return report.exit_code

    now = (clock or (lambda: datetime.now(UTC)))().isoformat()
    actor = approved_by or pwd.getpwuid(os.getuid()).pw_name
    try:
        approval, target, added = record_approval(
            root,
            approval_root,
            issue=args.issue,
            path=args.path,
            expected_content_id=args.content_id,
            approved_at=now,
            approved_by=actor,
            environ=environment,
        )
    except ApprovalError as refusal:
        print(  # noqa: T201 — CLI contract
            "\n".join(
                (
                    "approval_recorded=no",
                    f"refusal={refusal.kind}",
                    refusal.detail,
                    f"action={refusal.action}",
                    LIMIT_LINE,
                    SAME_USER_LIMIT,
                )
            ),
            file=sys.stderr,
        )
        return 1
    print(  # noqa: T201 — CLI contract
        "\n".join(
            (
                f"approval_recorded={'yes' if added else 'already'}",
                f"issue={approval.issue}",
                f"path={approval.path}",
                f"content_id={approval.content_id}",
                f"record={target}",
                f"approved_by={approval.approved_by} source={APPROVAL_SOURCE}",
                "verified=record_write,content_binding",
                LIMIT_LINE,
                SAME_USER_LIMIT,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
