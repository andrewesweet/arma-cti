"""`record_audit` itself — the `gh` seam that creates close provenance (#499).

`tests/unit/test_land.py` exercises the close ladder with an audit-post stand-in.
No stand-in for `record_audit` lives here: these tests call the real function and
stand in one seam farther down, at `subprocess.run`, so no test reaches GitHub.

What this module pins is deliberately narrower than audit quality. One supplied
body becomes one `gh issue comment --body-file -` call; a successful call returns
a receipt. Existing issue comments are never read, so a review quoting recipe names,
an assertion that gate evidence is absent, and a split real audit have no route into
that receipt. The caller must supply the complete audit as one body. Neither this
function nor its tests decide whether that body is a good audit.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
from conftest import load_tool

land = load_tool("land")

if TYPE_CHECKING:
    from pathlib import Path

_AUDIT_BODY = """## Criterion audit

- Acceptance checked against the landed diff.
- Gate evidence appears in the implementer's report.
"""


class _Ran:
    """Stand in for `subprocess.run`, recording the call and answering as told."""

    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        raises: Exception | None = None,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.raises = raises
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        self.calls.append((args, kwargs))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(args[0], self.returncode, self.stdout, self.stderr)


def test_one_supplied_body_is_one_bounded_comment_and_its_success_is_the_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provenance comes from the write this invocation made, never a thread scan."""
    ran = _Ran(stdout="https://github.com/andrewesweet/arma-cti/issues/499#issuecomment-1\n")
    monkeypatch.setattr(land.subprocess, "run", ran)

    receipt = land.record_audit(499, "abc1234", _AUDIT_BODY)

    assert receipt == land.AuditRecord(
        reference="https://github.com/andrewesweet/arma-cti/issues/499#issuecomment-1",
        reason=None,
    )
    assert len(ran.calls) == 1
    (argv,), kwargs = ran.calls[0]
    assert argv == ["gh", "issue", "comment", "499", "--body-file", "-"]
    assert kwargs["timeout"] == land.GH_CALL_TIMEOUT_S
    assert kwargs["input"].startswith(_AUDIT_BODY.rstrip())
    assert "abc1234" in kwargs["input"]
    assert "does not inspect the supplied content or judge audit quality" in kwargs["input"]


def test_no_supplied_body_records_nothing_and_never_reaches_the_tracker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran = _Ran()
    monkeypatch.setattr(land.subprocess, "run", ran)

    assert land.record_audit(499, "abc1234") == land.AuditRecord(
        reference="", reason="audit_file_missing"
    )
    assert ran.calls == []


def test_the_audit_file_is_read_before_landing_without_interpreting_its_body(
    tmp_path: Path,
) -> None:
    body = "No recipe-name sentinel is required here.\n"
    audit_file = tmp_path / "audit.md"
    audit_file.write_text(body, encoding="utf-8")

    assert land.read_audit_body(audit_file) == body


@pytest.mark.parametrize("contents", [None, b"\xff"])
def test_a_missing_or_non_utf8_audit_file_is_a_named_pre_landing_refusal(
    tmp_path: Path,
    contents: bytes | None,
) -> None:
    audit_file = tmp_path / "audit.md"
    if contents is not None:
        audit_file.write_bytes(contents)

    refusal = land.read_audit_body(audit_file)

    assert isinstance(refusal, land.Refusal)
    assert refusal.kind == "audit_file_unreadable"
    assert refusal.action.endswith("Nothing was pushed.")


def test_an_unreadable_audit_file_refuses_before_repository_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def repository_was_touched(*_args: object, **_kwargs: object) -> str:
        raise AssertionError

    monkeypatch.setattr(land, "git", repository_was_touched)

    code = land.main(["--audit-file", str(tmp_path / "missing.md")])

    assert code == land.EXIT_REFUSED
    assert "refusal=audit_file_unreadable" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [[], ["--resume"]], ids=["landing", "resume"])
def test_a_missing_audit_argument_is_a_named_pre_landing_refusal(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing transport is exit 1, never argparse's landed-but-incomplete exit 2."""

    def repository_was_touched(*_args: object, **_kwargs: object) -> str:
        raise AssertionError

    monkeypatch.setattr(land, "git", repository_was_touched)

    code = land.main(argv)

    captured = capsys.readouterr()
    assert code == land.EXIT_REFUSED
    assert captured.out == ""
    assert "refusal=audit_file_unreadable" in captured.err.splitlines()
    assert "audit_file=missing" in captured.err.splitlines()


@pytest.mark.parametrize(
    "unowned_comments",
    [
        ("Before trusting this branch, re-run `just check`, `just unit` and `just mutation`.",),
        (
            (
                "No implementer's `just check`, `just unit`, `just mutation` counts or verbatim"
                " mutation line are available."
            ),
        ),
        ("just check green", "just unit green", "just mutation sampled"),
    ],
    ids=["quoted_recipe_names", "asserted_absence", "real_audit_split_across_comments"],
)
def test_unowned_thread_comments_cannot_replace_a_failed_rung_post(
    unowned_comments: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive production receipt decision with historical comments at tracker seam.

    Fake tracker would return each historical thread if production requested it. New audit
    post refuses. Only correct decision: no thread read, no close, one failed post call.
    """
    calls: list[list[str]] = []

    def tracker(*args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:  # noqa: ANN401
        argv = args[0]
        calls.append(argv)
        if argv[:3] == ["gh", "issue", "view"]:
            body = json.dumps({"comments": [{"body": text} for text in unowned_comments]})
            return subprocess.CompletedProcess(argv, 0, body, "")
        if argv[:3] == ["gh", "issue", "comment"]:
            return subprocess.CompletedProcess(argv, 1, "", "audit post refused")
        if argv[:3] == ["gh", "issue", "close"]:
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(argv)

    monkeypatch.setattr(land.subprocess, "run", tracker)

    result = land._close_lines(  # noqa: SLF001 — production close decision is the subject
        499,
        "abc1234",
        land.close_issue,
        lambda issue, sha: land.record_audit(issue, sha, _AUDIT_BODY),
    )

    assert result.lines[0].startswith("audit_recorded=no issue=499 reason=gh_refused")
    assert result.lines[1].startswith("issue_closed=no issue=499 reason=audit_not_recorded")
    assert not result.audit_recorded
    assert calls == [["gh", "issue", "comment", "499", "--body-file", "-"]]


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (FileNotFoundError("gh"), "gh_not_on_path"),
        (subprocess.TimeoutExpired(["gh"], 20), "gh_timeout"),
        (PermissionError("blocked by the sandbox"), "gh_unrunnable"),
    ],
    ids=["absent", "stalled", "unrunnable"],
)
def test_every_way_gh_cannot_run_comes_back_as_a_reason(
    failure: Exception,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returned, never raised: the caller has already pushed when this seam runs."""
    monkeypatch.setattr(land.subprocess, "run", _Ran(raises=failure))

    receipt = land.record_audit(499, "abc1234", _AUDIT_BODY)

    assert receipt.reference == ""
    assert receipt.reason is not None
    assert receipt.reason.startswith(expected)


def test_a_gh_refusal_carries_its_own_words_on_one_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        land.subprocess,
        "run",
        _Ran(
            returncode=1,
            stderr="gh: To get started with GitHub CLI,\nplease run: gh auth login\n",
        ),
    )

    receipt = land.record_audit(499, "abc1234", _AUDIT_BODY)

    assert receipt.reason is not None
    assert "\n" not in receipt.reason
    assert receipt.reason.startswith("gh_refused gh: To get started with GitHub CLI, please run:")


def test_a_gh_success_without_a_returned_url_is_still_its_own_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not replace GitHub's successful write with a URL-shape parser (#471's class)."""
    monkeypatch.setattr(land.subprocess, "run", _Ran(stdout=""))

    assert land.record_audit(499, "abc1234", _AUDIT_BODY) == land.AuditRecord(
        reference="not_returned", reason=None
    )
