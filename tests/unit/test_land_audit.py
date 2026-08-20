"""`read_audit` itself — the `gh` seam a landing reads its issue's thread through (#461).

`tests/unit/test_land_close.py`'s arrangement, pointed at the second `gh` call a
successful landing makes: no stand-in for `read_audit` lives here, so the function
under test is the real one and a test written the wrong way — patching the module
attribute and calling through it — asserts against its own stand-in and fails
against the real behaviour rather than agreeing with it. Hermetic by standing in
one seam further down, at `subprocess.run`: the seam under test is what
`read_audit` does with `gh`'s answers, and no test here runs `gh`.

What these tests pin that nowhere else can: what "an audit is present" mechanically
means, which is `AUDIT_MARKERS` and not a judgement, and the boundary of that —
one comment carrying all three gate names, and nothing split across comments.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest
from conftest import load_tool

land = load_tool("land")

_AUDIT_BODY = "Audit: `just check` green, `just unit` green, `just mutation` sampled."


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


def _thread(*bodies: str) -> str:
    return json.dumps({"comments": [{"body": body} for body in bodies]})


def test_the_read_is_bounded_by_a_deadline_that_kills_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bound is the whole call's, which is the only kind that survives a stalled resolver.

    A socket timeout does not reach `getaddrinfo` (#427), so what makes this safe on
    the serial landing path is `subprocess.run`'s deadline killing the `gh` child
    (#425's shape) — the same bound the close carries, because it is the same call
    shape. Asserted on the argument rather than by waiting on a real stall.
    """
    ran = _Ran(stdout=_thread(_AUDIT_BODY))
    monkeypatch.setattr(land.subprocess, "run", ran)

    assert land.read_audit(461) == land.AuditRead(present=True, reason=None)

    (argv,), kwargs = ran.calls[0]
    assert argv == ["gh", "issue", "view", "461", "--json", "comments"]
    assert kwargs["timeout"] == land.GH_CALL_TIMEOUT_S


@pytest.mark.parametrize(
    ("bodies", "expected"),
    [
        ((_AUDIT_BODY,), True),
        (("noise first", _AUDIT_BODY), True),
        ((_AUDIT_BODY.upper(),), False),
        (("just check green, just unit green",), False),
        (("just check green", "just unit green, just mutation sampled"), False),
        ((), False),
        (("",), False),
    ],
    ids=[
        "the_audit_alone",
        "noise_around_it",
        "uppercased_gate_names_do_not_match",
        "one_gate_short",
        "split_across_comments",
        "no_comments",
        "an_empty_body",
    ],
)
def test_presence_is_one_comment_naming_all_three_gates(
    bodies: tuple[str, ...],
    *,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mechanical property stated where a reader meets it (`AUDIT_MARKERS`).

    Not a judgement (#458's class): a comment quoting the three gate names passes
    whether or not it is a good audit, one naming only two fails, and an audit
    split across comments fails too — every blind spot failing toward the issue
    staying open, which is the safe side of a presence check.
    """
    monkeypatch.setattr(land.subprocess, "run", _Ran(stdout=_thread(*bodies)))

    assert land.read_audit(461) == land.AuditRead(present=expected, reason=None)


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
    """Returned, never raised, and never as `present`: the caller has already pushed."""
    monkeypatch.setattr(land.subprocess, "run", _Ran(raises=failure))

    read = land.read_audit(461)

    assert read.present is False
    assert read.reason is not None
    assert read.reason.startswith(expected)


def test_a_gh_that_answers_with_a_refusal_carries_its_own_words_on_one_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unauthenticated or rate-limited `gh` is this: a non-zero exit and something to say.

    `close_issue`'s cap and collapse, unchanged: a reason is the tail of one output
    line, and a proxy's error page must not become the last thing a successful
    landing says.
    """
    monkeypatch.setattr(
        land.subprocess,
        "run",
        _Ran(
            returncode=1, stderr="gh: To get started with GitHub CLI,\nplease run: gh auth login\n"
        ),
    )

    read = land.read_audit(461)

    assert read.reason is not None
    assert "\n" not in read.reason
    assert read.reason.startswith("gh_refused gh: To get started with GitHub CLI, please run:")


@pytest.mark.parametrize(
    "stdout",
    ["not json at all", '{"issues": []}', '{"comments": "not a list"}'],
    ids=["invalid", "wrong_key", "wrong_shape"],
)
def test_a_gh_whose_answer_cannot_be_parsed_is_a_reason_not_an_absence(
    stdout: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero exit whose body is unreadable could not look, and must not read as "no audit".

    Owing an audit and being unable to look are different facts (#461), and this is
    the one path where a broken read could have collapsed them into `present=False`
    with no reason.
    """
    monkeypatch.setattr(land.subprocess, "run", _Ran(stdout=stdout))

    read = land.read_audit(461)

    assert read.present is False
    assert read.reason is not None
    assert read.reason.startswith("gh_unreadable_output")
