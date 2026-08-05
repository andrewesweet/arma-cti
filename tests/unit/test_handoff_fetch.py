"""What `just handoff <issue>` prints, and what it refuses to print (#210).

The fixture payloads are the shape `gh api ... --jq '.[] | .body | @json'`
actually writes — one JSON-encoded body per line — captured against #208's real
thread on 2026-08-05. The handoff body itself is the opening of the one #208's
research agent wrote, the first handoff this project has had.

The selection is asserted here rather than in jq for the reason the tool's own
docstring gives: the sketched `--jq` fails open, and a jq predicate is not
something the no-Arma tier can assert at all (#83, ADR-0049).
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

handoff_fetch = load_tool("handoff_fetch")

HANDOFF = (
    "Handoff-for: #208\n\n"
    "**State:**     Study, template and three adoption issues landed.\n"
    "**SHA:**       `ae79d12` on `main`, pushed.\n"
    "**Gates:**     `just fast` green at `ae79d12`.\n"
    "**Ruled out:** Raw transcript — 339,565 input-equivalents, more than never ending.\n"
)
OLDER_HANDOFF = "Handoff-for: #208\n\n**State:** superseded by the one below.\n"
PROSE = (
    "## Continuation economics\n\nA handoff opens with a `Handoff-for:` line, and this"
    " comment mentions one without being one.\n"
)
QUOTED = "> Handoff-for: #208\n>\n> Quoting a predecessor's handoff is not writing one.\n"


def payload(*bodies: str) -> str:
    """Render comment bodies the way `gh api --jq '.[] | .body | @json'` does."""
    return "".join(json.dumps(body) + "\n" for body in bodies)


def answering(*bodies: str) -> object:
    """Return a fetch that answers with these comments, in this order."""
    return lambda _issue: payload(*bodies)


def refusing(message: str) -> object:
    """Return a fetch that cannot look."""

    def fetch(_issue: int) -> str:
        raise handoff_fetch.FetchError(message)

    return fetch


# ------------------------------------------------------- what it prints (crit. 2)
def test_the_handoff_is_the_whole_of_the_output(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = handoff_fetch.main(["208"], fetch=answering(PROSE, HANDOFF, "Approved."))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == HANDOFF + "\n"
    assert captured.err == ""


def test_no_other_comment_reaches_the_output(capsys: pytest.CaptureFixture[str]) -> None:
    """The whole point: the thread stays out of the context window."""
    handoff_fetch.main(["208"], fetch=answering(PROSE, HANDOFF, "Approved."))

    captured = capsys.readouterr()
    assert "Continuation economics" not in captured.out
    assert "Approved." not in captured.out


def test_a_hash_prefixed_issue_is_the_same_issue(capsys: pytest.CaptureFixture[str]) -> None:
    assert handoff_fetch.main(["#208"], fetch=answering(HANDOFF)) == 0
    assert capsys.readouterr().out == HANDOFF + "\n"


def test_a_body_survives_the_markdown_it_carries(capsys: pytest.CaptureFixture[str]) -> None:
    body = 'Handoff-for: #24\n\n**Gates:** `just regress` 22/22, validated ×8, "quoted".\n'

    handoff_fetch.main(["24"], fetch=answering(body))

    assert capsys.readouterr().out == body + "\n"


# ----------------------------------------------------------- which one (crit. 3)
def test_the_newest_handoff_wins_when_a_thread_carries_several(
    capsys: pytest.CaptureFixture[str],
) -> None:
    handoff_fetch.main(["208"], fetch=answering(OLDER_HANDOFF, PROSE, HANDOFF))

    assert capsys.readouterr().out == HANDOFF + "\n"


def test_the_marker_has_to_open_a_line() -> None:
    assert handoff_fetch.select([PROSE, QUOTED]) is None


def test_the_marker_is_found_on_any_line_not_only_the_first() -> None:
    """`re.M`, which is what jq's `"m"` flag would have given."""
    prefixed = "Picking this up again.\n\n" + HANDOFF

    assert handoff_fetch.select([prefixed]) == prefixed


# ------------------------------------------------ absent is not silent (crit. 1)
def test_no_handoff_is_a_non_zero_exit_with_a_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A silent empty result reads as 'no state to carry' (#168/#183)."""
    exit_code = handoff_fetch.main(["210"], fetch=answering(PROSE, QUOTED))

    captured = capsys.readouterr()
    assert exit_code == handoff_fetch.NO_HANDOFF
    assert exit_code != 0
    assert captured.out == ""
    assert "#210" in captured.err
    assert "2 comment(s) scanned" in captured.err
    assert "docs/agents/handoff.md" in captured.err


def test_an_empty_thread_refuses_the_same_way(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = handoff_fetch.main(["210"], fetch=answering())

    captured = capsys.readouterr()
    assert exit_code == handoff_fetch.NO_HANDOFF
    assert captured.out == ""
    assert "0 comment(s) scanned" in captured.err


# ------------------------------------------- a stop is not a negative result
def test_gh_failing_is_told_apart_from_there_being_no_handoff(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = handoff_fetch.main(["999"], fetch=refusing("`gh` could not read #999: 404"))

    captured = capsys.readouterr()
    assert exit_code == handoff_fetch.NO_RESULT
    assert exit_code != handoff_fetch.NO_HANDOFF
    assert captured.out == ""
    assert "404" in captured.err


def test_an_unreadable_payload_is_a_stop_rather_than_a_wrong_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = handoff_fetch.main(["208"], fetch=lambda _issue: "not json at all\n")

    captured = capsys.readouterr()
    assert exit_code == handoff_fetch.NO_RESULT
    assert captured.out == ""
    assert "JSON Lines" in captured.err


def test_gh_missing_from_path_is_reported_as_a_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A check that could not run is not a check that passed (#41)."""

    def absent(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr(handoff_fetch.subprocess, "run", absent)

    with pytest.raises(handoff_fetch.FetchError, match="PATH"):
        handoff_fetch.fetch_comments(208)


def test_a_hanging_gh_is_bounded_rather_than_waited_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def hangs(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="gh", timeout=handoff_fetch.TIMEOUT_S)

    monkeypatch.setattr(handoff_fetch.subprocess, "run", hangs)

    with pytest.raises(handoff_fetch.FetchError, match="did not answer"):
        handoff_fetch.fetch_comments(208)


def test_a_non_zero_gh_carries_its_own_stderr_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_found(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gh"], returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)\n"
        )

    monkeypatch.setattr(handoff_fetch.subprocess, "run", not_found)

    with pytest.raises(handoff_fetch.FetchError, match="Not Found"):
        handoff_fetch.fetch_comments(999)


# --------------------------------------------------------------- the call itself
def test_the_fetch_reads_the_whole_thread_not_its_oldest_page() -> None:
    """Page one is the *oldest* thirty, so an unpaginated read answers backwards."""
    argv = handoff_fetch.command(210)

    assert "--paginate" in argv
    assert argv[:3] == ["gh", "api", "repos/{owner}/{repo}/issues/210/comments"]
    assert "@json" in argv[-1]


def test_the_endpoint_carries_no_hard_coded_repository() -> None:
    assert "arma-cti" not in handoff_fetch.endpoint(210)
    assert "{owner}/{repo}" in handoff_fetch.endpoint(210)


def test_the_tool_has_no_way_to_write_anything(tmp_path: Path) -> None:
    """It reads a thread and prints one comment. There is no `handoff-write`."""
    source = (REPO / "tools" / "handoff_fetch.py").read_text(encoding="utf-8")
    argv = handoff_fetch.command(210)

    assert "gh issue comment" not in source
    assert not {"-X", "--method", "-f", "--field", "--input", "--body"} & set(argv)
    assert not list(tmp_path.iterdir())


def test_the_recipe_is_the_seam_the_tool_hangs_off() -> None:
    """ADR-0049: the decision is Python, the recipe is the process seam."""
    justfile = (REPO / "justfile").read_text(encoding="utf-8")

    assert re.search(
        r"^handoff issue:\n +@uv run python tools/handoff_fetch\.py",
        justfile,
        re.MULTILINE,
    ), "the recipe must invoke the tool, and `@` keeps its own echo out of the output"


# ------------------------------------------------------------------ the payload
def test_the_payload_reader_ignores_blank_lines() -> None:
    assert handoff_fetch.bodies(payload(PROSE) + "\n" + payload(HANDOFF)) == [PROSE, HANDOFF]


@pytest.mark.parametrize("raw", ["", "abc", "-1", "0", "#", "12x"])
def test_a_non_issue_is_refused_by_the_parser(raw: str) -> None:
    with pytest.raises(SystemExit):
        handoff_fetch.main([raw], fetch=answering(HANDOFF))
