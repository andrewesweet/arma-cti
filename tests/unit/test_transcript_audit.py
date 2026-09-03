"""`tools/transcript_audit.py` — a measurement record checked against its transcript.

#698: a measurement record composed by the agent that produced it is a self-report.
#695's record substituted a corrected SHA for the one its transcript shows being
run and omitted the failed invocation entirely. These tests pin the two catches
the issue demands, using the issue's own SHAs, plus the refusals that keep the
checker honest.

Nothing here touches a live transcript: every fixture is staged under `tmp_path`,
so a test asserts a decision over a transcript it staged, never whatever this box
happened to hold.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import load_tool

transcript_audit = load_tool("transcript_audit")

# #695's own pair: what the transcript shows being run, and what the record claimed.
RAN = "d17598d3b04b6922ac35490e5c37c69da79b1c576"
SUBSTITUTED = "d17598d33283ee9b5ad5535c9780d7d4dc66c48c"

EVENT_TAIL = {
    "parentUuid": "p",
    "sessionId": "s",
    "uuid": "u",
    "timestamp": "2026-09-03T19:32:30.623Z",
    "cwd": "/stage/wt",
}


def _assistant(tool_use_id: str, command: str) -> str:
    return json.dumps(
        {
            **EVENT_TAIL,
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_use_id,
                        "name": "Bash",
                        "input": {"command": command},
                    }
                ],
            },
        }
    )


def _result(tool_use_id: str, text: str) -> str:
    return json.dumps(
        {
            **EVENT_TAIL,
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": [{"type": "text", "text": text}],
                    }
                ],
            },
        }
    )


def _stage(tmp_path: Path, lines: list[str]) -> tuple[Path, Path]:
    """Write one transcript into a staged project dir; return (root, transcript)."""
    directory = tmp_path / "projects" / "proj"
    directory.mkdir(parents=True)
    transcript = directory / "t.jsonl"
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return directory.parent, transcript


# What the transcript shows: two commands, the first refused by git itself.
TWO_COMMANDS = [
    _assistant("u1", f"git branch {RAN} wip"),
    _result("u1", "fatal: invalid upstream 'd17598d3b0…'"),
    _assistant("u2", f"git update-ref refs/heads/wip {RAN}"),
    _result("u2", f"Updated refs/heads/wip ({RAN[:7]}…)"),
]


def test_extract_pairs_invocation_and_output(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, TWO_COMMANDS)
    assert root.exists()
    rows = transcript_audit.extract(transcript)
    assert [(row.line, row.tool) for row in rows] == [(1, "Bash"), (3, "Bash")]
    assert rows[0].command == f"git branch {RAN} wip"
    assert rows[0].output == "fatal: invalid upstream 'd17598d3b0…'"
    assert not any(row.output_truncated for row in rows)


def test_extract_refuses_transcript_without_invocations(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, [json.dumps({"type": "queue-operation"})])
    assert root.exists()
    with pytest.raises(transcript_audit.AuditRefusal) as raised:
        transcript_audit.extract(transcript)
    assert raised.value.code == "harness_unsupported"


def test_extract_refuses_malformed_line(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, ["{not json", _assistant("u1", "git status")])
    assert root.exists()
    with pytest.raises(transcript_audit.AuditRefusal) as raised:
        transcript_audit.extract(transcript)
    assert raised.value.code == "transcript_malformed"


def test_render_is_deterministic(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, TWO_COMMANDS)
    assert root.exists()
    rows = transcript_audit.extract(transcript)
    first = transcript_audit.render(rows, transcript)
    second = transcript_audit.render(rows, transcript)
    assert first == second
    assert "transcript=t.jsonl" in first
    assert RAN in first
    assert "fatal: invalid upstream" in first


def _record_with_block(tmp_path: Path, block: str, prose: str) -> Path:
    record = tmp_path / "record.md"
    record.write_text(prose + "\n\n" + block + "\n", encoding="utf-8")
    return record


def test_verify_holds_when_record_matches_transcript(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, TWO_COMMANDS)
    assert root.exists()
    block = transcript_audit.render(transcript_audit.extract(transcript), transcript)
    prose = (
        "# A measurement\n\n"
        f"Ran `git update-ref` with `{RAN}`; git refused the branch: "
        "`git branch d17598d3b04b6922ac35490e5c37c69da79b1c576 wip`.\n"
    )
    record = _record_with_block(tmp_path, block, prose)
    problems, rows = transcript_audit.verify(record, transcript)
    assert problems == []
    assert rows == 2


def test_six_nine_five_substituted_sha_refuses(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, TWO_COMMANDS)
    assert root.exists()
    block = transcript_audit.render(transcript_audit.extract(transcript), transcript)
    prose = f"The collapse ran `{RAN}` — the correct SHA is `{SUBSTITUTED}`.\n"
    record = _record_with_block(tmp_path, block, prose)
    problems, rows = transcript_audit.verify(record, transcript)
    assert ("claim_not_in_transcript", f"{record}:1: SHA {SUBSTITUTED}") in problems
    assert rows == 2


def test_six_nine_five_omitted_invocation_refuses(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, TWO_COMMANDS)
    assert root.exists()
    block = transcript_audit.render(transcript_audit.extract(transcript), transcript)
    kept = "\n".join(line for line in block.splitlines() if "fatal" not in line)
    record = _record_with_block(tmp_path, kept, "Prose.\n")
    problems, _rows = transcript_audit.verify(record, transcript)
    assert problems
    assert problems[0][0] == "record_block_modified"


def test_verify_refuses_record_without_block(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, TWO_COMMANDS)
    assert root.exists()
    record = tmp_path / "record.md"
    record.write_text("# No audit block here\n", encoding="utf-8")
    problems, rows = transcript_audit.verify(record, transcript)
    assert problems[0][0] == "record_block_missing"
    assert rows == 0


def test_verify_refuses_ambiguous_blocks(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, TWO_COMMANDS)
    assert root.exists()
    block = transcript_audit.render(transcript_audit.extract(transcript), transcript)
    record = _record_with_block(tmp_path, block, "First\n\n" + block)
    problems, _rows = transcript_audit.verify(record, transcript)
    assert problems[0][0] == "record_block_ambiguous"


def test_verify_refuses_fabricated_git_command(tmp_path: Path) -> None:
    root, transcript = _stage(tmp_path, TWO_COMMANDS)
    assert root.exists()
    block = transcript_audit.render(transcript_audit.extract(transcript), transcript)
    prose = "Nothing here ran `git push --force origin main`.\n"
    record = _record_with_block(tmp_path, block, prose)
    problems, rows = transcript_audit.verify(record, transcript)
    assert problems
    assert problems[0][0] == "claim_not_in_transcript"
    assert rows == 2


def test_find_transcript_prefers_newest(tmp_path: Path) -> None:
    import os

    worktree = str(tmp_path / "wt")
    directory = tmp_path / transcript_audit.rc_health.project_dir_name(worktree)
    directory.mkdir()
    older = directory / "a.jsonl"
    newer = directory / "b.jsonl"
    older.write_text(_assistant("u1", "older"), encoding="utf-8")
    newer.write_text(_assistant("u2", "newer"), encoding="utf-8")
    os.utime(older, (1, 1))
    found = transcript_audit.find_transcript(transcript_audit.Path(worktree), tmp_path)
    assert found.name == "b.jsonl"


def test_find_transcript_refuses_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(transcript_audit.AuditRefusal) as raised:
        transcript_audit.find_transcript(transcript_audit.Path(str(tmp_path / "nowhere")), tmp_path)
    assert raised.value.code == "transcript_not_found"


def test_cli_emit_and_verify_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    worktree = str(tmp_path / "wt")
    directory = tmp_path / transcript_audit.rc_health.project_dir_name(worktree)
    directory.mkdir()
    transcript = directory / "t.jsonl"
    transcript.write_text("\n".join(TWO_COMMANDS) + "\n", encoding="utf-8")
    emitted = transcript_audit.main(
        ["emit", "--worktree", worktree, "--projects-root", str(tmp_path)]
    )
    assert emitted == 0
    captured = capsys.readouterr().out
    assert "transcript-audit begin" in captured
    record = tmp_path / "record.md"
    record.write_text("Prose.\n\n" + captured, encoding="utf-8")
    verdict = transcript_audit.main(
        [
            "verify",
            "--record",
            str(record),
            "--worktree",
            worktree,
            "--projects-root",
            str(tmp_path),
        ]
    )
    assert verdict == 0
    assert "record_audit=ok" in capsys.readouterr().out
