"""`close_issue` itself — the `gh` seam a landing closes its issue through (#439, #440).

These tests live apart from `tests/unit/test_land.py` for one reason: that module
stands in for this seam on every test it has, autouse, because a suite that reached
the real `gh` would post to `andrewesweet/arma-cti` from whatever credentials the
runner holds. A test *of* `close_issue` written in that module reads the same patched
attribute, so it asserts against the stand-in and passes whatever the function does.

#439 shipped seven such tests and they were loud — the stand-in's `reason` defaults
to `None` and five assertions wanted a string — but loudness was the coincidence, not
the protection. A seam test whose expectations happen to match the stand-in's defaults
passes, proves nothing, and no gate notices: `tools/mutation_smoke.py` plants only in
the lines a module's tests execute, so a vacuous seam test plants nothing and reds
nothing.

The remedy is arrangement rather than policing. There is no `closer` fixture here and
no stand-in for `close_issue` in this module, so `land.close_issue` *is* the function
under test and a test written the wrong way — patching the module attribute and then
calling through it — asserts against its own stand-in and fails against the real
behaviour rather than agreeing with it. Nothing is checked; the mistake has nowhere
to live. The rejected alternative was a meta-test inspecting other tests' patch
targets, which asserts on how tests are written rather than on what the code does.

Hermetic by standing in one seam further down, at `subprocess.run`: the seam under
test is what `close_issue` does with `gh`'s answers, and no test here runs `gh`.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
from conftest import load_tool

land = load_tool("land")


class _Ran:
    """Stand in for `subprocess.run`, recording the call and answering as told."""

    def __init__(
        self, returncode: int = 0, stderr: str = "", raises: Exception | None = None
    ) -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.raises = raises
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        self.calls.append((args, kwargs))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(args[0], self.returncode, "", self.stderr)


def test_the_close_is_bounded_by_a_deadline_that_kills_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound is the whole call's, which is the only kind that survives a stalled resolver.

    A socket timeout does not reach `getaddrinfo` (#427), so what makes this safe on the
    serial landing path is `subprocess.run`'s deadline killing the `gh` child (#425's
    shape). Asserted on the argument rather than by waiting on a real stall.
    """
    ran = _Ran()
    monkeypatch.setattr(land.subprocess, "run", ran)

    assert land.close_issue(439, "landed as abc1234") is None

    (argv,), kwargs = ran.calls[0]
    assert argv == ["gh", "issue", "close", "439", "--comment", "landed as abc1234"]
    assert kwargs["timeout"] == land.CLOSE_TIMEOUT_S


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
    """Returned, never raised: the caller has already pushed and has no red to spend."""
    monkeypatch.setattr(land.subprocess, "run", _Ran(raises=failure))

    reason = land.close_issue(439, "landed")

    assert reason is not None
    assert reason.startswith(expected)


def test_a_gh_that_answers_with_a_refusal_carries_its_own_words_on_one_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unauthenticated or rate-limited `gh` is this: a non-zero exit and something to say.

    Collapsed to one line and capped, because a reason is the tail of one output line and a
    proxy's error page must not become the last thing a successful landing says.
    """
    monkeypatch.setattr(
        land.subprocess,
        "run",
        _Ran(
            returncode=1, stderr="gh: To get started with GitHub CLI,\nplease run: gh auth login\n"
        ),
    )

    reason = land.close_issue(439, "landed")

    assert reason is not None
    assert "\n" not in reason
    assert reason.startswith("gh_refused gh: To get started with GitHub CLI, please run:")


def test_a_gh_that_refuses_without_a_word_still_names_its_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(land.subprocess, "run", _Ran(returncode=3))

    assert land.close_issue(439, "landed") == "gh_refused exit 3"


def test_a_reason_is_capped_so_a_page_of_html_cannot_be_the_landings_last_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(land.subprocess, "run", _Ran(returncode=1, stderr="x " * 5000))

    reason = land.close_issue(439, "landed")

    assert reason is not None
    assert len(reason) <= len("gh_refused ") + land.REASON_LIMIT


def test_the_closing_comment_names_the_sha_that_landed() -> None:
    """The one thing a reader of the closed issue needs: which commit is the work."""
    assert "abc1234" in land.CLOSE_COMMENT.format(sha="abc1234")
