"""Check a measurement record against the dispatch transcript that produced it.

#698: a measurement record composed by the agent that produced it is a self-report,
and nothing attests it. #695's record silently substituted a corrected SHA for the
one its transcript shows being run, and omitted the invocation that returned
``fatal: invalid upstream``; the reviewer caught both only by reading the transcript
by hand. This module makes that reading mechanical:

- ``extract`` recovers every tool invocation from a Claude Code session transcript
  (the JSONL under ``~/.claude/projects/<worktree-slug>/``), each row carrying the
  transcript line it came from. An invocation whose ``tool_result`` never arrives —
  the omission #695's record committed — is recovered too, as a row with no output,
  rather than dropped: a trailing unmatched ``tool_use`` renders a missing-output
  row, because silence is the one response this checker may not give.
- ``render``/``emit`` produce the deterministic ``transcript-audit`` block a
  measurement record carries: generated from the transcript, never composed. The
  block's header binds the record to its producer — the transcript file's name and
  its full SHA-256 — so the row cells are pointers, and command and output cells
  are truncated for the table only; ``verify`` searches the full text.
- ``verify`` resolves the transcript the block names, refuses where its content no
  longer matches the recorded digest (``transcript_changed``), regenerates the block
  and refuses a record whose block was edited (``record_block_modified``), carries
  none (``record_block_missing``) or more than one (``record_block_ambiguous``),
  and scans the prose outside the block for claims — full SHAs and backticked
  ``git`` invocations — that no transcript row supports
  (``claim_not_in_transcript``).

Both #695 shapes are caught: omission, because an unmatched invocation renders a
row and a record missing one no longer matches; substitution, because the prose
scan refuses a SHA no invocation ran.

The transcript format is Claude Code's own, not this repository's contract; it is
read defensively and a transcript with no ``tool_use`` event refuses
``harness_unsupported`` rather than emitting an empty audit. Codex dispatches write
a different transcript shape and are unsupported here -- named, not guessed at.

Read access is dated: on 2026-09-03 a dispatched ``acceptEdits`` session could read
these transcripts (``wc``/``grep``/``head`` over the absolute path) but could not run
this module directly (``uv run python tools/…`` refused, on the measured ``docs/
agents/dispatched-session-commands.md`` list), so the module's surface is the
``just transcript-audit`` recipe and in a dispatched session the citation form of
the convention applies; ``emit``/``verify`` run where approvals exist -- the review
seat's session, the orchestrator's, or the human's. Read-only throughout: nothing
here writes a file or gates a landing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import rc_health  # the tools/ dir is the import root for sibling scripts

DEFAULT_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
COMMAND_HEAD = 200
OUTPUT_HEAD = 400
SHA_TOKEN: re.Pattern[str] = re.compile(r"\b[0-9a-f]{40}\b")
GIT_TICK: re.Pattern[str] = re.compile(r"`(git [^`]*)`")
BEGIN = "<!-- transcript-audit begin "
END = "<!-- transcript-audit end -->"
BINDING: re.Pattern[str] = re.compile(r"transcript=(\S+) sha256=([0-9a-f]{64})")
MISSING_OUTPUT = "(no tool_result recovered)"


class AuditRefusal(Exception):  # noqa: N818 — the repo names this shape `Refusal`, and a refusal is not an error
    """A typed refusal: the audit could not answer, so it says which rung stopped it."""

    def __init__(self, code: str, detail: str) -> None:
        """Carry the machine-readable code and the human-readable rung."""
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class Pending:
    """An invocation seen before its output: what one ``tool_use`` event carries."""

    line: int
    timestamp: str
    tool: str
    command: str


@dataclass
class Invocation:
    """One tool invocation, with the transcript line it came from.

    ``command`` and ``output`` are the raw transcript text, untruncated — the
    evidence ``verify`` searches. Truncation happens in ``render``, for the
    table's cells only, so a claim in a rendered row's tail is still found.
    ``output`` is ``None`` where no ``tool_result`` was ever recovered.
    """

    line: int
    timestamp: str
    tool: str
    command: str
    output: str | None
    sidechain: bool

    def searchable(self) -> str:
        """Return the row text the prose claim-scan searches: command plus output."""
        return f"{self.command}\n{self.output or ''}"


def _cell(text: str, limit: int) -> str:
    """One table cell: flattened, bounded at ``limit``, truncation marked."""
    flat = text.replace("\n", "\\n").replace("|", "\\|")
    if len(flat) <= limit:
        return flat
    return flat[:limit] + "…"


def _content_text(content: Any) -> str:
    """Read a tool_result's content, which is a string or a list of text parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def extract(transcript: Path) -> list[Invocation]:
    """Recover every invocation, in transcript order, from one session JSONL.

    An invocation whose output never arrived keeps its place as a row with no
    output — dropping it would re-create the omission this module exists to catch.
    """
    pending: dict[str, Pending] = {}
    rows: dict[str, Invocation] = {}
    try:
        lines = transcript.read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise AuditRefusal("transcript_unreadable", f"{transcript}: {err}") from err
    for number, raw in enumerate(lines, start=1):
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as err:
            raise AuditRefusal("transcript_malformed", f"{transcript}:{number}: {err}") from err
        if not isinstance(event, dict):
            continue
        sidechain = bool(event.get("isSidechain"))
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        timestamp = str(event.get("timestamp", ""))
        if event.get("type") == "assistant":
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "tool_use":
                    continue
                tool = str(part.get("name", ""))
                payload = part.get("input")
                if isinstance(payload, dict) and isinstance(payload.get("command"), str):
                    command = payload["command"]
                else:
                    command = json.dumps(payload, sort_keys=True)
                pending[str(part.get("id"))] = Pending(number, timestamp, tool, command)
        elif event.get("type") == "user":
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "tool_result":
                    continue
                use_id = str(part.get("tool_use_id"))
                if use_id not in pending:
                    continue
                seen = pending.pop(use_id)
                rows[use_id] = Invocation(
                    line=seen.line,
                    timestamp=seen.timestamp,
                    tool=seen.tool,
                    command=seen.command,
                    output=_content_text(part.get("content")),
                    sidechain=sidechain,
                )
    # Whatever is still pending had no tool_result in this transcript: a row with
    # no output, not a silent drop.
    rows.update(
        (
            use_id,
            Invocation(seen.line, seen.timestamp, seen.tool, seen.command, None, sidechain=False),
        )
        for use_id, seen in pending.items()
    )
    ordered = sorted(rows.values(), key=lambda row: row.line)
    if not ordered:
        raise AuditRefusal(
            "harness_unsupported",
            f"{transcript}: no tool_use event recovered — not a Claude Code transcript",
        )
    return ordered


def find_transcript(worktree: Path, projects_root: Path = DEFAULT_PROJECTS_ROOT) -> Path:
    """Derive the session transcript from the worktree, newest JSONL winning.

    ``emit``'s derivation only. ``verify`` never runs it: the record's block names
    its own transcript, and the newest file here could be a later session's. The
    newest-file choice can still name the wrong session where two sessions overlap
    one worktree, which the #105 protocol forbids; that residual gap is stated in
    ``docs/agents/measurement-records.md`` rather than claimed away.
    """
    directory = projects_root / rc_health.project_dir_name(str(worktree))
    try:
        candidates = [path for path in directory.glob("*.jsonl") if path.is_file()]
    except OSError as err:
        raise AuditRefusal("transcript_unreadable", f"{directory}: {err}") from err
    if not candidates:
        raise AuditRefusal("transcript_not_found", f"no *.jsonl under {directory}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def render(rows: list[Invocation], transcript: Path) -> str:
    """Render the deterministic transcript-audit block for one transcript."""
    digest = hashlib.sha256(transcript.read_bytes()).hexdigest()
    lines = [
        f"{BEGIN}transcript={transcript.name} sha256={digest} rows={len(rows)} -->",
        (
            "Generated from the transcript; regenerate, never edit. Resolve a row with"
            " `sed -n <line>p <transcript>`."
        ),
        "| line | timestamp | tool | command | output |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        tag = " (sidechain)" if row.sidechain else ""
        output = MISSING_OUTPUT if row.output is None else _cell(row.output, OUTPUT_HEAD)
        lines.append(
            f"| {row.line} | {row.timestamp} | {row.tool}{tag} "
            f"| {_cell(row.command, COMMAND_HEAD)} "
            f"| {output} |"
        )
    lines.append(END)
    return "\n".join(lines)


def _block_span(text: str) -> tuple[int, int] | None:
    """Return the character span of the one transcript-audit block, if there is one."""
    start = text.find(BEGIN)
    if start < 0:
        return None
    end = text.find(END, start)
    if end < 0:
        return None
    return start, end + len(END)


def bound_transcript(text: str, worktree: Path, projects_root: Path) -> Path | None:
    """Resolve the transcript a record's block binds itself to, and hold it to its digest.

    The binding is the record's own header — file name plus full SHA-256 — so a
    session that ran later in the same worktree cannot become the producer
    ``verify`` reads. A transcript whose content moved since the record was
    rendered refuses ``transcript_changed``: the evidence base is not the one the
    block was generated from, and re-emitting is the remedy. ``None`` where the
    record carries no block at all — a red the caller emits, not a refusal, since
    the record is the thing that fails.
    """
    span = _block_span(text)
    if span is None:
        return None
    header = text[span[0] : text.find("-->", span[0])]
    found = BINDING.search(header)
    if found is None:
        raise AuditRefusal(
            "record_block_modified",
            "block header carries no transcript=…/sha256=… binding",
        )
    name, digest = found.group(1), found.group(2)
    if "/" in name or "\\" in name or name in (".", ".."):
        raise AuditRefusal(
            "record_block_modified",
            f"block names {name!r}, which is not a transcript file in its project directory",
        )
    transcript = projects_root / rc_health.project_dir_name(str(worktree)) / name
    if not transcript.is_file():
        raise AuditRefusal("transcript_not_found", f"{transcript}: the recorded transcript is gone")
    actual = hashlib.sha256(transcript.read_bytes()).hexdigest()
    if actual != digest:
        raise AuditRefusal(
            "transcript_changed",
            f"{name}: recorded sha256={digest[:16]}…, actual {actual[:16]}… — re-emit over"
            " the current transcript",
        )
    return transcript


def verify(text: str, transcript: Path, label: str) -> tuple[list[tuple[str, str]], int]:
    """Check one record's text against one transcript.

    Returns the problem list and the row count; the list is empty when the record
    holds. A problem names its record line, so a reader resolves the claim without
    trusting this module's reading of it.
    """
    problems: list[tuple[str, str]] = []
    span = _block_span(text)
    if span is None:
        return [("record_block_missing", f"{label}: no transcript-audit block")], 0
    begin, end = span
    if text.find(BEGIN, end) >= 0 or text.find(BEGIN, 0, begin) >= 0:
        return [("record_block_ambiguous", f"{label}: more than one block")], 0
    rows = extract(transcript)
    expected = render(rows, transcript)
    if text[begin:end] != expected:
        got = text[begin:end].splitlines()
        want = expected.splitlines()
        first = next(
            (n for n, (a, b) in enumerate(zip(got, want, strict=False)) if a != b),
            min(len(got), len(want)),
        )
        return [
            (
                "record_block_modified",
                (
                    f"{label}: block differs from the regenerated audit at line {first + 1}"
                    f" ({len(got)} recorded lines, {len(want)} generated)"
                ),
            )
        ], 0
    searchable = "\n".join(row.searchable() for row in rows)
    prose = text[:begin] + text[end:]
    for number, line in enumerate(prose.splitlines(), start=1):
        problems.extend(
            ("claim_not_in_transcript", f"{label}:{number}: SHA {token}")
            for token in SHA_TOKEN.findall(line)
            if token not in searchable
        )
        problems.extend(
            ("claim_not_in_transcript", f"{label}:{number}: `{command}`")
            for command in GIT_TICK.findall(line)
            if command not in searchable
        )
    return problems, len(rows)


def _record_text(record: str) -> tuple[str, str]:
    """Read the record from a path, or from stdin where the path is ``-``."""
    if record == "-":
        return sys.stdin.read(), "-"
    path = Path(record)
    try:
        return path.read_text(encoding="utf-8"), str(path)
    except OSError as err:
        raise AuditRefusal("record_unreadable", f"{path}: {err}") from err


def main(argv: list[str] | None = None) -> int:
    """Print the emit block or the verify verdict; exit 0 only when the record holds."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    for name in ("emit", "verify"):
        child = sub.add_parser(name)
        child.add_argument("--worktree", required=True, type=Path)
        child.add_argument("--projects-root", type=Path, default=DEFAULT_PROJECTS_ROOT)
    verify_parser = sub.choices["verify"]
    verify_parser.add_argument(
        "--record",
        required=True,
        help="path to the record, or - to read it from stdin",
    )
    args = parser.parse_args(argv)
    try:
        if args.verb == "emit":
            transcript = find_transcript(args.worktree, args.projects_root)
            print(render(extract(transcript), transcript))
            return 0
        text, label = _record_text(args.record)
        transcript = bound_transcript(text, args.worktree, args.projects_root)
        if transcript is None:
            detail = f"{label}: no transcript-audit block"
            print(f"record_audit=red code=record_block_missing detail={detail}")
            return 1
        problems, rows = verify(text, transcript, label)
    except AuditRefusal as refusal:
        print(f"record_audit=refused code={refusal.code} detail={refusal.detail}")
        return 1
    if problems:
        for code, detail in problems:
            print(f"record_audit=red code={code} {detail}")
        return 1
    print(f"record_audit=ok transcript={transcript.name} rows={rows}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
