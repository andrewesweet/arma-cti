"""Check a measurement record against the dispatch transcript that produced it.

#698: a measurement record composed by the agent that produced it is a self-report,
and nothing attests it. #695's record silently substituted a corrected SHA for the
one its transcript shows being run, and omitted the invocation that returned
``fatal: invalid upstream``; the reviewer caught both only by reading the transcript
by hand. This module makes that reading mechanical:

- ``extract`` recovers every tool invocation and its output from a Claude Code
  session transcript (the JSONL under ``~/.claude/projects/<worktree-slug>/``),
  each row carrying the transcript line it came from, so a reader resolves a row
  with ``sed -n <line>p <file>`` rather than trusting the summary.
- ``render``/``emit`` produce the deterministic ``transcript-audit`` block a
  measurement record carries: generated from the transcript, never composed.
- ``verify`` regenerates that block from the transcript and refuses a record whose
  block was edited (``record_block_modified``), carries none (``record_block_missing``)
  or more than one (``record_block_ambiguous``), and scans the prose outside the
  block for claims -- full SHAs and backticked ``git`` invocations -- that no
  transcript row supports (``claim_not_in_transcript``).

Both #695 shapes are caught: omission, because the regenerated block carries every
row and a record missing one no longer matches; substitution, because the prose scan
refuses a SHA no invocation ran.

The transcript format is Claude Code's own, not this repository's contract; it is
read defensively and a transcript with no ``tool_use`` event refuses
``harness_unsupported`` rather than emitting an empty audit. Codex dispatches write
a different transcript shape and are unsupported here -- named, not guessed at.

Read access is dated: on 2026-09-03 a dispatched ``acceptEdits`` session could read
these transcripts (``wc``/``grep``/``head`` over the absolute path) but could not run
this module (``uv run python tools/…`` refused, on the measured ``docs/agents/
dispatched-session-commands.md`` list), so in a dispatched session the citation form
of the convention applies and ``emit``/``verify`` run where approvals exist -- the
review seat's session, the orchestrator's, or the human's. Read-only throughout:
nothing here writes a file or gates a landing.
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

import rc_health

DEFAULT_PROJECTS_ROOT = Path.home() / ".claude" / "projects"
COMMAND_HEAD = 200
OUTPUT_HEAD = 400
SHA_TOKEN: re.Pattern[str] = re.compile(r"\b[0-9a-f]{40}\b")
GIT_TICK: re.Pattern[str] = re.compile(r"`(git [^`]*)`")
BEGIN = "<!-- transcript-audit begin "
END = "<!-- transcript-audit end -->"


class AuditRefusal(Exception):
    """A typed refusal: the audit could not answer, so it says which rung stopped it."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class Invocation:
    """One tool invocation, with the transcript line each half came from."""

    line: int
    timestamp: str
    tool: str
    command: str
    command_truncated: bool
    output: str
    output_truncated: bool
    sidechain: bool

    def searchable(self) -> str:
        return f"{self.command}\n{self.output}"


def _head(text: str, limit: int) -> tuple[str, bool]:
    flat = text.replace("\n", "\\n").replace("|", "\\|")
    if len(flat) <= limit:
        return flat, False
    return flat[:limit] + "…", True


def _content_text(content: Any) -> str:
    """Read a tool_result's content, which is a string or a list of text parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def extract(transcript: Path) -> list[Invocation]:
    """Recover every invocation, in transcript order, from one session JSONL."""
    pending: dict[str, tuple[int, str, str, str, bool]] = {}
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
                bounded, truncated = _head(command, COMMAND_HEAD)
                pending[str(part.get("id"))] = (
                    number,
                    timestamp,
                    tool,
                    bounded,
                    truncated,
                )
        elif event.get("type") == "user":
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "tool_result":
                    continue
                use_id = str(part.get("tool_use_id"))
                if use_id not in pending:
                    continue
                line_no, when, tool, command, command_truncated = pending.pop(use_id)
                text = _content_text(part.get("content"))
                bounded_out, out_truncated = _head(text, OUTPUT_HEAD)
                rows[use_id] = Invocation(
                    line=line_no,
                    timestamp=when,
                    tool=tool,
                    command=command,
                    command_truncated=command_truncated,
                    output=bounded_out,
                    output_truncated=out_truncated,
                    sidechain=sidechain,
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

    One session holds a worktree at a time (the #105 protocol), so the newest
    transcript in the worktree's project directory is that session's. Derived,
    never declared: a caller naming a file is exactly the self-report this module
    exists to refuse.
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
    digest = hashlib.sha256(transcript.read_bytes()).hexdigest()[:16]
    lines = [
        f"{BEGIN}transcript={transcript.name} sha256={digest} rows={len(rows)} -->",
        "Generated from the transcript; regenerate, never edit. Resolve a row with"
        " `sed -n <line>p <transcript>`.",
        "| line | timestamp | tool | command | output |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        tag = " (sidechain)" if row.sidechain else ""
        lines.append(
            f"| {row.line} | {row.timestamp} | {row.tool}{tag} "
            f"| {row.command}{'…' if row.command_truncated else ''} "
            f"| {row.output}{'…' if row.output_truncated else ''} |"
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


def verify(record: Path, transcript: Path) -> tuple[list[tuple[str, str]], int]:
    """Check one record against one transcript.

    Returns the problem list and the row count; the list is empty when the record
    holds. A problem names its record line, so a reader resolves the claim without
    trusting this module's reading of it.
    """
    problems: list[tuple[str, str]] = []
    try:
        text = record.read_text(encoding="utf-8")
    except OSError as err:
        raise AuditRefusal("record_unreadable", f"{record}: {err}") from err
    span = _block_span(text)
    if span is None:
        return [("record_block_missing", f"{record}: no transcript-audit block")], 0
    begin, end = span
    if text.find(BEGIN, end) >= 0 or text.find(BEGIN, 0, begin) >= 0:
        return [("record_block_ambiguous", f"{record}: more than one block")], 0
    rows = extract(transcript)
    expected = render(rows, transcript)
    if text[begin:end] != expected:
        got = text[begin:end].splitlines()
        want = expected.splitlines()
        first = next(
            (n for n, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want))
        )
        return [
            (
                "record_block_modified",
                f"{record}: block differs from the regenerated audit at line {first + 1}"
                f" ({len(got)} recorded lines, {len(want)} generated)",
            )
        ], 0
    searchable = "\n".join(row.searchable() for row in rows)
    prose = text[:begin] + text[end:]
    for number, line in enumerate(prose.splitlines(), start=1):
        for token in SHA_TOKEN.findall(line):
            if token not in searchable:
                problems.append(("claim_not_in_transcript", f"{record}:{number}: SHA {token}"))
        for command in GIT_TICK.findall(line):
            if command not in searchable:
                problems.append(("claim_not_in_transcript", f"{record}:{number}: `{command}`"))
    return problems, len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    for name in ("emit", "verify"):
        child = sub.add_parser(name)
        child.add_argument("--worktree", required=True, type=Path)
        child.add_argument("--projects-root", type=Path, default=DEFAULT_PROJECTS_ROOT)
    verify_parser = sub.choices["verify"]
    verify_parser.add_argument("--record", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        transcript = find_transcript(args.worktree, args.projects_root)
        if args.verb == "emit":
            print(render(extract(transcript), transcript))
            return 0
        problems, rows = verify(args.record, transcript)
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
