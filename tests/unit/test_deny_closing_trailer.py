"""Tests for the closing-keyword gate, `.claude/hooks/deny-closing-trailer.py`.

The hook exists to stop a commit message closing an issue behind the audit's
back (#89, #24, #127). Its scope is deliberately GitHub's: every spelling
GitHub acts on is denied wherever it sits in the message, and everything that
merely *refers* to an issue passes. Both directions are pinned here, because the
lesson of #120 is that an over-eager hook costs more than the rule it guards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from conftest import load_hook

if TYPE_CHECKING:
    from pathlib import Path

hook = load_hook("deny-closing-trailer")

KEYWORDS = [
    "close",
    "closes",
    "closed",
    "fix",
    "fixes",
    "fixed",
    "resolve",
    "resolves",
    "resolved",
]


# --- every keyword GitHub documents, in every case ---------------------------


@pytest.mark.parametrize("keyword", KEYWORDS)
def test_each_documented_keyword_is_denied(keyword: str) -> None:
    """GitHub's list verbatim: close/closes/closed, fix/fixes/fixed, resolve/-s/-d."""
    assert hook.closing_reference(f"fix: land the thing\n\n{keyword} #129") is not None


@pytest.mark.parametrize("keyword", KEYWORDS)
def test_each_keyword_is_denied_capitalised(keyword: str) -> None:
    assert hook.closing_reference(f"feat: x\n\n{keyword.upper()} #7") is not None


def test_the_documented_colon_form_is_denied() -> None:
    """`Closes: #10` is GitHub's own example."""
    assert hook.closing_reference("feat: x\n\nCloses: #10") is not None


# --- every reference form a keyword can close through ------------------------


def test_a_cross_repository_reference_is_denied() -> None:
    assert hook.closing_reference("feat: x\n\nCloses andrewesweet/arma-cti#129") is not None


def test_a_gh_dash_reference_is_denied() -> None:
    assert hook.closing_reference("feat: x\n\nFixes GH-129") is not None


def test_a_full_issue_url_is_denied() -> None:
    url = "https://github.com/andrewesweet/arma-cti/issues/129"
    assert hook.closing_reference(f"feat: x\n\nResolves {url}") is not None


def test_a_keyword_wrapped_onto_the_next_line_is_denied() -> None:
    """A wrapped trailer is still a trailer to GitHub."""
    assert hook.closing_reference("feat: x\n\nCloses\n  #129") is not None


# --- position: GitHub matches anywhere, so the hook must too -----------------


def test_a_keyword_in_the_middle_of_a_body_is_denied() -> None:
    """Not a false positive: this really does close #129 on push."""
    body = "fix: stop the drift\n\nThe guard fixes #129 in passing, which is the point."
    assert hook.closing_reference(body) is not None


def test_a_keyword_in_the_subject_is_denied() -> None:
    assert hook.closing_reference("fix: closes #129 for good") is not None


def test_a_conventional_commits_type_followed_by_a_reference_is_denied() -> None:
    """`fix: #129 ...` is GitHub's documented colon form wearing a type's clothes."""
    assert hook.closing_reference("fix: #129 stop the pool guessing") is not None


# --- referencing without closing must stay writable --------------------------


def test_a_parenthesised_reference_passes() -> None:
    assert hook.closing_reference("fix: stop the drift (#129)") is None


def test_refs_passes() -> None:
    assert hook.closing_reference("fix: stop the drift\n\nrefs #129") is None


def test_a_bare_reference_passes() -> None:
    assert hook.closing_reference("fix: x\n\nFiled as #129, audited by hand.") is None


def test_a_keyword_with_prose_between_it_and_the_reference_passes() -> None:
    """GitHub needs the reference straight after the keyword; so does this."""
    assert hook.closing_reference("fix: x\n\nFixes the flake #129 reported.") is None


def test_a_keyword_naming_the_rule_passes() -> None:
    """Writing about the ban is not doing it — #120's lesson, applied ahead of time."""
    body = "docs: name the ban\n\nThe closes/fixes/resolves keywords are denied at commit time."
    assert hook.closing_reference(body) is None


def test_a_word_ending_in_a_keyword_passes() -> None:
    assert hook.closing_reference("fix: x\n\nThe suffixes #129 lists are unchanged.") is None


def test_a_hyphenated_word_ending_in_a_keyword_passes() -> None:
    assert hook.closing_reference("fix: x\n\nThe hotfix-#129 branch is gone.") is None


def test_a_blank_line_between_keyword_and_reference_passes() -> None:
    body = "fix: x\n\nThe thing is fixed\n\n#129 covers the rest."
    assert hook.closing_reference(body) is None


# --- what git strips before GitHub ever sees it ------------------------------


def test_a_comment_line_is_not_part_of_the_message() -> None:
    """Git's own template block, which git drops after this hook runs."""
    assert hook.closing_reference("fix: x\n\n# On branch main\n# Closes #129 (a path)") is None


def test_a_verbose_commits_diff_is_not_part_of_the_message() -> None:
    """`git commit -v` puts the diff below the scissors, and here it quotes the rule."""
    body = (
        "test: pin the gate\n\n"
        "# ------------------------ >8 ------------------------\n"
        "diff --git a/t.py b/t.py\n"
        "+    assert hook.closing_reference('Closes #129') is not None\n"
    )
    assert hook.closing_reference(body) is None


def test_a_reference_alone_on_a_comment_line_is_the_accepted_gap() -> None:
    """The one direction the comment rule loses: `-m` keeps this line, git's editor drops it.

    Reachable only by writing a wrapped trailer through `-m`, where the `#N`
    lands in column one. Recorded on #129 rather than fixed, because the
    alternative is reading `git commit -v`'s diff as message text.
    """
    assert hook.closing_reference("fix: x\n\nCloses\n#129") is None


def test_the_reference_is_reported_for_the_denial_message() -> None:
    """The denial quotes what it found, so the fix is obvious without a re-read."""
    assert hook.closing_reference("fix: x\n\nCloses\n  #129") == "Closes #129"


# --- the commit-msg contract -------------------------------------------------


def call(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, message: str) -> int:
    """Run the hook's argv contract over a commit message file."""
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["deny-closing-trailer.py", str(path)])
    return hook.main()


def test_a_closing_message_is_rejected_and_cites_the_rule(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert call(monkeypatch, tmp_path, "fix: x\n\nCloses #129\n") == 1
    assert "docs/agents/issue-tracker.md" in capsys.readouterr().err


def test_a_referencing_message_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert call(monkeypatch, tmp_path, "fix: stop the drift (#129)\n") == 0


def test_a_message_that_cannot_be_read_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Fail closed: an unchecked message is not a checked one (#94 finding 2)."""
    monkeypatch.setattr("sys.argv", ["deny-closing-trailer.py", str(tmp_path / "absent")])
    assert hook.main() == 1


def test_a_call_without_a_file_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["deny-closing-trailer.py"])
    assert hook.main() == 1
