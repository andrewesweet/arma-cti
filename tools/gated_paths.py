#!/usr/bin/env python3
"""Guard path-identifiable sign-off gates at ``just check`` (#500).

Claude Code's ``protect-gated-paths.py`` hook still gives immediate feedback for
the write classes it has always denied.  This module owns that hook's path data
and the broader path-identifiable subset of AGENTS.md's human sign-off gates, so
the hook and the lane-neutral gate cannot drift onto separate lists.

An explicit human approval is one versioned record below
``~/.arma-cti/gated-path-approvals/``.  It names the issue and one path, and is
bound to the exact change at that path.  Textual hunk bytes, section anchors,
paths and modes remain exact; only hunk line ranges and textual whole-file blob
IDs are discarded, because those name a moved baseline rather than the change.
That normalised identity only nominates an earlier record: carrying it also
requires the recorded baseline to be an ancestor and a clean three-way replay
of the recorded approved result onto the current baseline to equal the current
bytes.  This keeps an unrelated textual baseline edit without letting an
identical hunk moved elsewhere reuse approval.  Another branch-side hunk or an
altered approved hunk cannot carry.  Binary and non-regular diffs need fresh
approval after a same-path baseline change.  A changed ADR carrying ADR-0013's
exact ``Delegated-decision: yes`` line in the field block parsed by
``check_adr_form.py`` remains the standing-authorisation route AGENTS.md defines,
for that record alone (#548): every other gated path in the same diff still needs
its own approval or its own marker.

The approval command refuses a dispatched session.  Like #398's interactive
authorship record, that is a mechanical floor rather than an identity proof: a
same-user process can strip ``CTI_DISPATCH_ID`` or forge local bytes.  Every
verdict states that limit, plus the semantic sign-off gates a path scan cannot
recognise and the content/quality judgement it never performs.
"""

from __future__ import annotations

import argparse
import base64
import binascii
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
from typing import TYPE_CHECKING, Final, NamedTuple, cast

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `trial.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# ADR form owns the field-block boundary.  The authorisation gate asks it whether the
# marker is there rather than growing a second parser for the same document shape.
import check_adr_form
import check_command_table

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

BASE: Final = "origin/main"
APPROVAL_VERSION: Final = 2
RECORD_MODE: Final = 0o600
APPROVAL_SOURCE: Final = "declared_human"
APPROVER_SOURCE: Final = "os_user"
CONTENT_ID: Final = re.compile(r"\A[0-9a-f]{64}\Z")
COMMIT_SHA: Final = re.compile(r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
ISSUE_WORKTREE: Final = re.compile(r"\Aissue-(\d+)\Z")
APPROVAL_ROOT: Final = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".arma-cti" / "gated-path-approvals"

FILE: Final = "file"
TREE: Final = "tree"
SEGMENT: Final = "segment"

HUNK_RANGES: Final = re.compile(rb"\A@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
INDEX_LINE: Final = re.compile(rb"\Aindex [^\n]*")
BINARY_FOLLOWS: Final = (b"Binary files ", b"GIT binary patch")

APPROVAL_UNREADABLE: Final = "approval_unreadable"
APPROVAL_FROM_DISPATCH: Final = "approval_from_dispatch"
INVALID_ISSUE: Final = "invalid_issue"
APPROVAL_ISSUE_MISMATCH: Final = "approval_issue_mismatch"
PATH_NOT_GATED: Final = "path_not_gated"
GATED_PATHS_UNREADABLE: Final = "gated_paths_unreadable"
PATH_NOT_CHANGED: Final = "path_not_changed"
INVALID_CONTENT_ID: Final = "invalid_content_id"
INVALID_CHANGE_ID: Final = "invalid_change_id"
GATED_CONTENT_UNREADABLE: Final = "gated_content_unreadable"
CONTENT_CHANGED: Final = "content_changed"
CHANGE_ID_MISMATCH: Final = "change_id_mismatch"
APPROVAL_IDENTIFIER_MISSING: Final = "approval_identifier_missing"
APPROVAL_IDENTIFIERS_BOTH: Final = "approval_identifiers_both"
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
    generated: bool = False

    def matches(self, path: str) -> bool:
        """Whether a normalised repository-relative path meets this rule."""
        parts = tuple(part for part in path.split("/") if part)
        if self.shape == FILE:
            return path == self.target
        if self.shape == TREE:
            return path == self.target or path.startswith(f"{self.target}/")
        return self.target in parts


ADR_SIGNOFF_GATE: Final = PathGate(
    "docs/adr",
    TREE,
    "New and changed ADRs are a human sign-off gate.",
    requires_approval=True,
    deny_at_write=False,
)

OBSERVATORY_SUMMARY_PATH: Final = "docs/observatory/landed-issues.md"


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
    ADR_SIGNOFF_GATE,
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
        generated=True,
    ),
    PathGate(
        OBSERVATORY_SUMMARY_PATH,
        FILE,
        "Generated observatory projection. Regenerate from live sources; never hand-edit.",
        requires_approval=False,
        deny_at_write=True,
        generated=True,
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
    """One validated, change-bound direct approval."""

    issue: int
    path: str
    content_id: str
    change_id: str
    base_sha: str
    result_payload: bytes
    binary: bool
    approved_at: str
    approved_by: str


class ChangeBinding(NamedTuple):
    """Current exact state plus baseline-independent identity used for replay."""

    content_id: str
    change_id: str
    base_sha: str
    result_payload: bytes
    binary: bool


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


def is_generated_path(path: str, *, root: Path | None = None) -> bool:
    """Return whether the shared path authority classifies ``path`` as generated."""
    return any(gate.generated for gate in gates_for_path(path, root=root))


def is_delegated_decision_record(
    path: str,
    source: str,
    *,
    root: Path | None = None,
) -> bool:
    """Whether ``path`` and ``source`` form ADR-0013's changed record."""
    normalised = _normalise_path(path, root)
    return bool(
        normalised
        and ADR_SIGNOFF_GATE.matches(normalised)
        and check_adr_form.has_delegated_marker(source)
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


def _normalised_diff(diff: bytes) -> bytes:
    """Keep exact change bytes while discarding textual baseline-only names."""
    lines: list[bytes] = []
    pending_index: bytes | None = None
    for line in diff.splitlines(keepends=True):
        if pending_index is not None:
            # Binary patches carry no textual hunk bytes, so their full before/after
            # blob IDs stay. Text diffs carry their change below; whole-file blob IDs
            # would invalidate an unchanged hunk after any same-path baseline edit.
            lines.append(pending_index if line.startswith(BINARY_FOLLOWS) else b"index\n")
            pending_index = None
        if INDEX_LINE.match(line):
            pending_index = line
        else:
            lines.append(HUNK_RANGES.sub(b"@@", line))
    if pending_index is not None:
        lines.append(b"index\n")
    return b"".join(lines)


def _path_diff(root: Path, path: str) -> bytes:
    """Return deterministic full-index diff bytes for one current path."""
    return _git_bytes(
        "diff",
        "--unified=0",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        "--ignore-submodules=none",
        "--full-index",
        "--binary",
        "--diff-algorithm=myers",
        "--no-indent-heuristic",
        BASE,
        "--",
        path,
        cwd=root,
    )


def _state_id(path: str, base_sha: str, baseline: bytes, current: bytes) -> str:
    """Identify exact baseline and result bytes for one path."""
    payload = b"gated-path-content-v2\0" + path.encode("utf-8") + b"\0"
    payload += base_sha.encode("ascii") + b"\0" + baseline
    payload += b"current\0" + current
    return hashlib.sha256(payload).hexdigest()


def _change_id(path: str, baseline: bytes, current: bytes, diff: bytes) -> str:
    """Identify the change while excluding only textual baseline movement."""
    if not baseline:
        # Git does not include an untracked file in `git diff`. Its whole content
        # is the addition, and this form stays identical before and after commit.
        change = b"addition\0" + current
    elif current == b"absent\0":
        # Deleting a file approves deleting those exact baseline bytes. A baseline
        # edit changes the deletion itself, so it must not inherit approval.
        change = b"deletion\0" + baseline
    else:
        if not diff:
            raise GitError(("diff", BASE, "--", path), "path has no diff to bind")
        change = b"diff\0" + _normalised_diff(diff)
    payload = b"gated-path-change-v2\0" + path.encode("utf-8") + b"\0" + change
    return hashlib.sha256(payload).hexdigest()


def binding_of(root: Path, path: str) -> ChangeBinding:
    """Compute exact state and replayable change identities for one path."""
    baseline = _git_bytes("ls-tree", "-z", BASE, "--", path, cwd=root)
    current = _current_payload(root, path)
    diff = b"" if not baseline or current == b"absent\0" else _path_diff(root, path)
    base_sha = _git_bytes("rev-parse", "--verify", f"{BASE}^{{commit}}", cwd=root)
    try:
        decoded_base = base_sha.decode("ascii").strip()
    except UnicodeDecodeError as unreadable:
        raise GitError(("rev-parse", BASE), f"non-ASCII commit id: {unreadable}") from unreadable
    if not COMMIT_SHA.fullmatch(decoded_base):
        raise GitError(("rev-parse", BASE), f"invalid commit id: {decoded_base!r}")
    binary = any(line.startswith(BINARY_FOLLOWS) for line in diff.splitlines())
    return ChangeBinding(
        _state_id(path, decoded_base, baseline, current),
        _change_id(path, baseline, current, diff),
        decoded_base,
        current,
        binary,
    )


def content_id_of(root: Path, path: str) -> str:
    """Return exact-state ID presented to the approval writer."""
    return binding_of(root, path).content_id


def approval_path(root: Path, issue: int, content_id: str) -> Path:
    """Return the content-addressed record path for one issue."""
    return root / str(issue) / f"{content_id}.json"


def _record_header_fault(document: dict[str, object]) -> str:
    """Validate fixed record fields plus issue and path."""
    expected_keys = {
        "version",
        "issue",
        "path",
        "content_id",
        "change_id",
        "base_sha",
        "result_payload",
        "binary",
        "base",
        "approved_at",
        "approved_by",
        "approved_by_source",
        "source",
    }
    if set(document) != expected_keys:
        return f"keys={sorted(document)} expected={sorted(expected_keys)}"
    expected_values = {
        "version": APPROVAL_VERSION,
        "base": BASE,
        "approved_by_source": APPROVER_SOURCE,
        "source": APPROVAL_SOURCE,
    }
    for key, value in expected_values.items():
        if document.get(key) != value:
            return f"{key}={document.get(key)!r} expected={value!r}"
    issue = document.get("issue")
    if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
        return f"issue={issue!r}"
    record_path = document.get("path")
    if (
        not isinstance(record_path, str)
        or _normalise_path(record_path) != record_path
        or signoff_gate(record_path) is None
    ):
        return f"path={record_path!r}"
    return ""


def _record_binding_fault(document: dict[str, object]) -> str:
    """Validate binding IDs and replay metadata."""
    for key in ("content_id", "change_id"):
        value = document.get(key)
        if not isinstance(value, str) or CONTENT_ID.fullmatch(value) is None:
            return f"{key}={value!r}"
    base_sha = document.get("base_sha")
    if not isinstance(base_sha, str) or COMMIT_SHA.fullmatch(base_sha) is None:
        return f"base_sha={base_sha!r}"
    if not isinstance(document.get("binary"), bool):
        return f"binary={document.get('binary')!r}"
    return ""


def _record_payload_fault(document: dict[str, object]) -> str:
    """Validate encoded result and human-owned metadata."""
    encoded = document.get("result_payload")
    if not isinstance(encoded, str):
        return f"result_payload={encoded!r}"
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return "result_payload is not canonical base64"
    if base64.b64encode(decoded).decode("ascii") != encoded:
        return "result_payload is not canonical base64"
    for key in ("approved_at", "approved_by"):
        value = document.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"{key}={value!r}"
    return ""


def _record_fault(document: object) -> str:
    """Say why stored bytes are not the record this tool writes."""
    if not isinstance(document, dict):
        return f"record is not an object: {document!r}"
    typed = cast("dict[str, object]", document)
    return (
        _record_header_fault(typed) or _record_binding_fault(typed) or _record_payload_fault(typed)
    )


def read_approval(path: Path, expected: Approval | None = None) -> Approval:
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
    fault = _record_fault(document)
    if fault:
        raise ApprovalError(
            APPROVAL_UNREADABLE,
            f"record={path} reason={fault}",
            (
                "Re-record this exact approval through `just gated-paths approve`;"
                " hand-shaped bytes do not clear the gate."
            ),
        )
    document = cast("dict[str, object]", document)
    approval = Approval(
        int(document["issue"]),
        str(document["path"]),
        str(document["content_id"]),
        str(document["change_id"]),
        str(document["base_sha"]),
        base64.b64decode(str(document["result_payload"]), validate=True),
        bool(document["binary"]),
        str(document["approved_at"]),
        str(document["approved_by"]),
    )
    if path.stem != approval.content_id:
        fault = f"filename={path.name!r} content_id={approval.content_id!r}"
    elif expected is not None:
        compared = (
            "issue",
            "path",
            "content_id",
            "change_id",
            "base_sha",
            "result_payload",
            "binary",
        )
        fault = next(
            (
                f"{field} does not match current binding"
                for field in compared
                if getattr(approval, field) != getattr(expected, field)
            ),
            "",
        )
    else:
        fault = ""
    if fault:
        raise ApprovalError(
            APPROVAL_UNREADABLE,
            f"record={path} reason={fault}",
            (
                "Re-record this exact approval through `just gated-paths approve`;"
                " a record that does not match its path and binding cannot clear the gate."
            ),
        )
    return approval


def _approval_for(
    issue: int,
    path: str,
    binding: ChangeBinding,
    approved_at: str,
    approved_by: str,
) -> Approval:
    """Join caller-owned approval facts to tool-computed binding facts."""
    return Approval(
        issue,
        path,
        binding.content_id,
        binding.change_id,
        binding.base_sha,
        binding.result_payload,
        binding.binary,
        approved_at,
        approved_by,
    )


def _tree_entry_and_payload(root: Path, ref: str, path: str) -> tuple[bytes, bytes]:
    """Read one exact tree entry and its file payload at ``ref``."""
    entry = _git_bytes("ls-tree", "-z", ref, "--", path, cwd=root)
    if not entry:
        return b"", b"absent\0"
    try:
        metadata, named = entry.removesuffix(b"\0").split(b"\t", 1)
        mode, kind, object_id = metadata.split(b" ", 2)
    except ValueError as malformed:
        raise GitError(("ls-tree", ref, "--", path), "malformed tree entry") from malformed
    if named != path.encode("utf-8") or kind != b"blob":
        raise GitError(
            ("ls-tree", ref, "--", path),
            f"unexpected entry path={named!r} kind={kind!r}",
        )
    content = _git_bytes("cat-file", "blob", object_id.decode("ascii"), cwd=root)
    return entry, mode + b"\0" + content


def _regular_payload(payload: bytes) -> tuple[bytes, bytes] | None:
    """Split one ordinary Git file payload into mode and bytes."""
    mode, separator, content = payload.partition(b"\0")
    if separator and mode in (b"100644", b"100755"):
        return mode, content
    return None


def _is_ancestor(root: Path, earlier: str, later: str) -> bool:
    """Whether ``earlier`` is an ancestor, distinguishing false from unreadable."""
    args = ("merge-base", "--is-ancestor", earlier, later)
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=root,
        capture_output=True,
        check=False,
    )
    if done.returncode == 0:
        return True
    if done.returncode == 1:
        return False
    raise GitError(args, done.stderr.decode("utf-8", errors="replace"))


def _merge_file(current_base: bytes, old_base: bytes, approved: bytes) -> bytes | None:
    """Replay approved text onto current baseline; ``None`` means it did not merge cleanly."""
    with tempfile.TemporaryDirectory(prefix="gated-path-replay-") as temporary_name:
        directory = Path(temporary_name)
        current_path = directory / "current"
        base_path = directory / "base"
        approved_path = directory / "approved"
        current_path.write_bytes(current_base)
        base_path.write_bytes(old_base)
        approved_path.write_bytes(approved)
        done = subprocess.run(  # noqa: S603
            ["git", "merge-file", "-p", current_path, base_path, approved_path],  # noqa: S607
            capture_output=True,
            check=False,
        )
    return done.stdout if done.returncode == 0 else None


def _approval_carries(  # noqa: PLR0911 — each unsupported replay shape is named
    root: Path,
    path: str,
    approval: Approval,
    current: ChangeBinding,
) -> tuple[bool, str]:
    """Prove exact approved text replays onto a descendant baseline."""
    if approval.binary or current.binary:
        return False, "binary_same_path_baseline"
    if not _is_ancestor(root, approval.base_sha, current.base_sha):
        return False, "baseline_not_descendant"
    old_entry, old_payload = _tree_entry_and_payload(root, approval.base_sha, path)
    if (
        _state_id(path, approval.base_sha, old_entry, approval.result_payload)
        != approval.content_id
    ):
        raise ApprovalError(
            APPROVAL_UNREADABLE,
            f"content_id={approval.content_id} does not bind its recorded baseline and result",
            "Re-record this approval; its replay material does not match its identity.",
        )
    _new_entry, new_payload = _tree_entry_and_payload(root, current.base_sha, path)
    old_parts = _regular_payload(old_payload)
    approved_parts = _regular_payload(approval.result_payload)
    new_parts = _regular_payload(new_payload)
    current_parts = _regular_payload(current.result_payload)
    if old_parts is None or approved_parts is None or new_parts is None or current_parts is None:
        return False, "non_regular_same_path_baseline"
    modes = {old_parts[0], approved_parts[0], new_parts[0], current_parts[0]}
    if len(modes) != 1:
        return False, "mode_changed"
    merged = _merge_file(new_parts[1], old_parts[1], approved_parts[1])
    if merged is None:
        return False, "approved_change_did_not_replay_cleanly"
    if merged != current_parts[1]:
        return False, "replayed_result_differs"
    return True, "exact_three_way_replay"


def _stored_approvals(root: Path, issue: int) -> tuple[tuple[Path, Approval], ...]:
    """Read every versioned record for one issue, failing closed on corrupt bytes."""
    directory = root / str(issue)
    if not directory.exists():
        return ()
    try:
        records = tuple(sorted(directory.glob("*.json")))
    except OSError as unreadable:
        raise ApprovalError(
            APPROVAL_UNREADABLE,
            f"directory={directory} reason={unreadable}",
            "Restore the readable approval directory and retry.",
        ) from unreadable
    return tuple((record, read_approval(record)) for record in records)


def delegated_decisions(root: Path, paths: Sequence[str]) -> tuple[str, ...]:
    """Return changed ADRs carrying ADR-0013's marker in their field block."""
    found: list[str] = []
    for path in paths:
        try:
            source = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if is_delegated_decision_record(path, source):
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


def _has_current_approval_record(
    root: Path,
    approvals: Path,
    issue: int | None,
    path: str,
) -> bool:
    """Keep a separately recorded direct approval ahead of the standing route."""
    if issue is None:
        return False
    try:
        binding = binding_of(root, path)
    except GitError:
        return False
    return approval_path(approvals, issue, binding.content_id).exists()


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


def direct_approval_remedy(root: Path, issue: int | None, action: str) -> str:
    """Append the human's direct-approval exit to a command-table refusal.

    Shared by the gate route and `check_command_table`'s standalone CLI so the
    documented `just check-command-table` path cannot dead-end either (#583).
    """
    try:
        binding = binding_of(root, "AGENTS.md")
    except GitError:
        return action
    change_command = "just gated-paths approve"
    content_command = "just gated-paths approve"
    if issue is None:
        # `approve` requires --issue and this checkout names none, so a printed
        # placeholder would be a usage error, not a remedy (#583 round 4). The
        # human supplies the number the tool refuses to guess.
        return (
            f"{action} The direct-approval exit is `{change_command}"
            f" --issue N --path AGENTS.md --change-id {binding.change_id}` (default),"
            f" or `{content_command} --issue N --path AGENTS.md"
            f" --content-id {binding.content_id}`, run by the"
            " human after reviewing this exact path diff, with N the issue this"
            " change lands under — this checkout names none, so N was not"
            " guessed. A session must not run it."
        )
    change_command = (
        f"{change_command} --issue {issue} --path AGENTS.md --change-id {binding.change_id}"
    )
    content_command = (
        f"{content_command} --issue {issue} --path AGENTS.md --content-id {binding.content_id}"
    )
    return (
        f"{action} Or, after the human reviews this exact path diff, they run"
        f" `{change_command}` (default), or `{content_command}`. A session must not run it."
    )


class CommandTableRoute(NamedTuple):
    """The optional command-table authorisation result."""

    lines: tuple[str, ...]
    authorized: bool
    recipe_resolution: bool
    refusal: Report | None


class CommandTableInputs(NamedTuple):
    """Inputs for the optional command-table route."""

    root: Path
    approvals: Path
    issue: int | None
    gated: tuple[str, ...]
    delegated: tuple[str, ...]
    covered: tuple[str, ...]


def _command_table_route(inputs: CommandTableInputs) -> CommandTableRoute:
    """Evaluate the narrow ADR-0013 route without changing other gate paths."""
    if (
        "AGENTS.md" not in inputs.gated
        or len(inputs.delegated) != 1
        or _has_current_approval_record(inputs.root, inputs.approvals, inputs.issue, "AGENTS.md")
    ):
        return CommandTableRoute(lines=(), authorized=False, recipe_resolution=False, refusal=None)
    result = check_command_table.check(inputs.root)
    if not result.applicable:
        return CommandTableRoute(lines=(), authorized=False, recipe_resolution=False, refusal=None)
    if result.failure is not None:
        failure = result.failure
        # Every route refusal returns before the per-path walk, so this is the
        # last surface that can name the direct-approval exit (#575, #583).
        refusal = _refused(
            failure.kind,
            (*inputs.covered, *failure.details),
            direct_approval_remedy(inputs.root, inputs.issue, failure.action),
        )
        return CommandTableRoute(
            lines=(), authorized=False, recipe_resolution=False, refusal=refusal
        )
    return CommandTableRoute(
        lines=result.lines,
        authorized=True,
        recipe_resolution=result.recipe_resolution,
        refusal=None,
    )


def check(  # noqa: C901, PLR0911, PLR0912, PLR0915 — one report per fail-closed read and carry shape
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

    # ADR-0013's marker authorises the record that carries it, not the paths
    # travelling beside it (#548): drop the delegated records from the gated set
    # and hold every remaining path to its own approval or its own marker.
    delegated = delegated_decisions(root, paths)
    covered = tuple(f"delegated_record={path}" for path in delegated)
    command_table_route = _command_table_route(
        CommandTableInputs(root, approvals, issue, gated, delegated, covered)
    )
    if command_table_route.refusal is not None:
        return command_table_route.refusal
    command_table_lines = command_table_route.lines
    command_table_authorized = command_table_route.authorized
    command_table_verification = ""
    if command_table_authorized:
        command_table_verification = ",command_table_confinement"
        if command_table_route.recipe_resolution:
            command_table_verification += ",recipe_resolution"
    gated = tuple(path for path in gated if path not in delegated)
    if command_table_authorized:
        gated = tuple(path for path in gated if path != "AGENTS.md")
    if not gated:
        authorization = "command_table" if command_table_authorized else "delegated_decision"
        verified = f"verified=path_scan{command_table_verification},delegated_marker"
        authorized_count = 1 if command_table_authorized else 0
        changed_count = len(delegated) + authorized_count
        return Report(
            (
                (f"gated_paths=ok changed={changed_count} authorization={authorization}"),
                *command_table_lines,
                *covered,
                verified,
                LIMIT_LINE,
                SAME_USER_LIMIT,
            ),
            0,
        )

    def refused(kind: str, found: Sequence[str], action: str) -> Report:
        """Refuse while still naming the delegated records the diff did cover."""
        return _refused(kind, (*covered, *found), action)

    if issue is None:
        return refused(
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
            binding = binding_of(root, path)
        except GitError as failure:
            return refused(
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
        content_id = binding.content_id
        record = approval_path(approvals, issue, content_id)
        expected = _approval_for(issue, path, binding, "expected", "expected")
        if record.exists():
            try:
                read_approval(record, expected)
            except ApprovalError as refusal:
                return refused(refusal.kind, (f"path={path}", refusal.detail), refusal.action)
            approved.append(
                f"approval=recorded issue={issue} path={path} content_id={content_id}"
                f" record={record}"
            )
            continue

        not_carried: list[str] = []
        try:
            stored = _stored_approvals(approvals, issue)
        except ApprovalError as refusal:
            return refused(refusal.kind, (f"path={path}", refusal.detail), refusal.action)
        for prior_path, prior in stored:
            if prior.issue != issue or prior.path != path or prior.change_id != binding.change_id:
                continue
            try:
                carries, reason = _approval_carries(root, path, prior, binding)
            except GitError as failure:
                return refused(
                    GATED_CONTENT_UNREADABLE,
                    (
                        f"path={path}",
                        f"record={prior_path}",
                        f"command={' '.join(failure.args_run)}",
                        f"stderr={failure.stderr}",
                    ),
                    "Restore readable approval and baseline history; an unproven replay fails.",
                )
            except ApprovalError as refusal:
                return refused(refusal.kind, (f"path={path}", refusal.detail), refusal.action)
            if carries:
                approved.append(
                    f"approval=carried issue={issue} path={path}"
                    f" change_id={binding.change_id} record={prior_path} proof={reason}"
                )
                break
            not_carried.append(f"prior_approval={prior_path} not_carried={reason}")
        else:
            command = (
                "just gated-paths approve"
                f" --issue {issue} --path {shlex.quote(path)} --change-id {binding.change_id}"
            )
            content_command = (
                "just gated-paths approve"
                f" --issue {issue} --path {shlex.quote(path)} --content-id {content_id}"
            )
            return refused(
                "approval_missing",
                (
                    f"issue={issue}",
                    f"path={path}",
                    f"content_id={content_id}",
                    f"change_id={binding.change_id}",
                    f"record={record}",
                    *not_carried,
                ),
                (
                    f"After the human reviews this exact path diff, they run `{command}`"
                    f" (default), or `{content_command}`."
                    " A session must not run it."
                ),
            )
    verified = "verified=path_scan,record_shape,change_binding"
    if delegated:
        verified += ",delegated_marker"
    authorized_count = 1 if command_table_authorized else 0
    changed_count = len(gated) + len(delegated) + authorized_count
    return Report(
        (
            (f"gated_paths=ok changed={changed_count} authorization=recorded"),
            *approved,
            *command_table_lines,
            *covered,
            verified + command_table_verification,
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


def record_approval(  # noqa: C901, PLR0912, PLR0913 — validation ladder; one input per recorded fact
    root: Path,
    approvals: Path,
    *,
    issue: int,
    path: str,
    expected_content_id: str | None = None,
    expected_change_id: str | None = None,
    approved_at: str,
    approved_by: str,
    environ: Mapping[str, str],
) -> tuple[Approval, Path, bool]:
    """Write a direct approval after recomputing its exact change binding."""
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
    has_content_id = expected_content_id is not None
    has_change_id = expected_change_id is not None
    if not has_content_id and not has_change_id:
        raise ApprovalError(
            APPROVAL_IDENTIFIER_MISSING,
            "content_id=missing change_id=missing",
            "Provide exactly one of --change-id or --content-id.",
        )
    if has_content_id and has_change_id:
        raise ApprovalError(
            APPROVAL_IDENTIFIERS_BOTH,
            "content_id=provided change_id=provided",
            "Provide exactly one of --change-id or --content-id, not both.",
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
    identifier_name = "content_id" if has_content_id else "change_id"
    identifier_kind = INVALID_CONTENT_ID if has_content_id else INVALID_CHANGE_ID
    expected_identifier = expected_content_id if has_content_id else cast("str", expected_change_id)
    if not CONTENT_ID.fullmatch(expected_identifier):
        raise ApprovalError(
            identifier_kind,
            f"{identifier_name}={expected_identifier!r}",
            f"Paste the 64-character {identifier_name} from the gate refusal.",
        )
    try:
        binding = binding_of(root, normalised)
    except GitError as failure:
        raise ApprovalError(
            GATED_CONTENT_UNREADABLE,
            (f"path={normalised} command={' '.join(failure.args_run)} stderr={failure.stderr}"),
            "Restore the readable path and baseline, then retry.",
        ) from failure
    actual_identifier = binding.content_id if has_content_id else binding.change_id
    if actual_identifier != expected_identifier:
        if has_content_id:
            raise ApprovalError(
                CONTENT_CHANGED,
                f"path={normalised} asked={expected_identifier} actual={actual_identifier}",
                (
                    "Run `just check` again. It may carry a prior text approval by exact replay;"
                    " otherwise review the current path diff and use the new content_id it prints."
                ),
            )
        raise ApprovalError(
            CHANGE_ID_MISMATCH,
            f"path={normalised} asked={expected_identifier} actual={actual_identifier}",
            "Run `just check` again. Review the current path diff and use the change_id it prints.",
        )

    approval = _approval_for(issue, normalised, binding, approved_at, approved_by)
    target = approval_path(approvals, issue, binding.content_id)
    with _approval_lock(approvals, issue):
        if target.exists():
            read_approval(target, approval)
            return approval, target, False
        document = {
            "version": APPROVAL_VERSION,
            "issue": issue,
            "path": normalised,
            "content_id": binding.content_id,
            "change_id": binding.change_id,
            "base_sha": binding.base_sha,
            "result_payload": base64.b64encode(binding.result_payload).decode("ascii"),
            "binary": binding.binary,
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
    approve.add_argument("--content-id")
    approve.add_argument("--change-id")
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
            expected_change_id=args.change_id,
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
                f"change_id={approval.change_id}",
                f"base_sha={approval.base_sha}",
                f"record={target}",
                f"approved_by={approval.approved_by} source={APPROVAL_SOURCE}",
                "verified=record_write,change_binding",
                LIMIT_LINE,
                SAME_USER_LIMIT,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
