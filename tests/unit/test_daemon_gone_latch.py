"""The pump's dead-daemon noise is latched, not hammered (#72).

A daemon that died mid-run used to earn an identical `CTI|daemon_unreachable`
line at every loop's poll cadence for the rest of a probe's window. `#72`'s
second half is the latch: after a bounded run of consecutive transport errors,
the per-call line goes quiet and the fact is said once — legible, not loud.

What can be asserted at this tier is the document: SQF has no mutation arm and
the latch's only in-world reader is the evidence a corpus run writes, which is
why the world-facing half of this change is owed the full corpus at landing and
why these assertions read the source rather than execute it. The in-world
behaviour the latch must not break — a restarted daemon still being noticed, a
recovery still being said — is pinned by `spike/probes/daemon-restart.sqf`,
which pings through the outage and expects the epoch change to freeze the world.

`#684` adds the behavioural half the substring tests cannot give: the call's
exit graph is derived from the source — every `call _answer` exit, every
run-reset statement, every `exitWith` block's span — and the run's reset is
asserted **on the straight-line path to each exit**, not merely present
somewhere in the file. A regression that keeps every string intact but moves an
exit ahead of the reset reddens, which is the gap #72's round-four review
recorded.
"""

from __future__ import annotations

import re

from conftest import REPO

DAEMON_CALL = REPO / "addons" / "main" / "functions" / "fn_daemonCall.sqf"
EFFECT_PUMP = REPO / "addons" / "main" / "functions" / "fn_effectPump.sqf"


def source() -> str:
    """Read the one file the latch lives in."""
    return DAEMON_CALL.read_text(encoding="utf-8")


def pump_source() -> str:
    """Read the pump's cadence gate, which decides when to ask again."""
    return EFFECT_PUMP.read_text(encoding="utf-8")


_CODE_TOKEN = re.compile(r'"(?:[^"]|"")*"|//[^\n]*|/\*.*?\*/', re.DOTALL)


def _code_only(body: str) -> str:
    """Blank out comments, preserving every offset.

    The exits and the reset are matched on code, not on prose — a comment that
    names an outcome or quotes the reset line must not look like one. String
    literals are left intact — the outcome names live in them — and stand first
    in the alternation, so a `//` or `/*` inside one is consumed by the literal
    and never read as a comment. Offsets are preserved, so the result can be
    ordered against the original text.
    """
    return _CODE_TOKEN.sub(
        lambda match: (
            match.group(0)
            if match.group(0).startswith('"')
            else re.sub(r"[^\n]", " ", match.group(0))
        ),
        body,
    )


def _code_shell(body: str) -> str:
    """Blank comments *and* string contents, preserving every offset.

    The brace matcher reads this: a brace inside a string literal or a comment
    is prose, not scope, and would desynchronise an exitWith span.
    """

    def _blank(match: re.Match[str]) -> str:
        text = match.group(0)
        if text.startswith('"'):
            # Keep the quotes and the offsets; blank what the literal says.
            return '"' + re.sub(r"[^\n]", " ", text[1:-1]) + '"'
        return re.sub(r"[^\n]", " ", text)

    return _CODE_TOKEN.sub(_blank, body)


def _matching_brace(shell: str, opening: int) -> int:
    """Offset of the brace matching `shell[opening]`, or -1 when none does."""
    depth = 0
    for i in range(opening, len(shell)):
        if shell[i] == "{":
            depth += 1
        elif shell[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _exit_with_spans(shell: str) -> list[tuple[int, int]]:
    """Span of every `exitWith { ... }` block: open keyword to matching brace."""
    spans = []
    for match in re.finditer(r"\bexitWith\b", shell):
        opening = shell.index("{", match.end())
        close = _matching_brace(shell, opening)
        assert close >= 0, "an exitWith block is never closed"
        spans.append((match.start(), close))
    return spans


def _reaches(resets: list[int], exits_at: int, spans: list[tuple[int, int]], wire: int) -> bool:
    """Whether a run-reset statement is on the straight-line path to `exits_at`.

    A reset at an offset before the exit is not on that path when it sits
    inside an exitWith block ending before the exit — that block has already
    returned by the time the exit is reached. This is what puts the recovery
    reset, which sits outside every block, on every reply exit's path, and
    keeps the reset inside the unreadable exit's own block off the
    transport-failure exit's path.
    """
    return any(
        wire < reset < exits_at and not any(start < reset < end < exits_at for start, end in spans)
        for reset in resets
    )


def _call_events() -> tuple[int, list[tuple[int, str]], list[int], list[tuple[int, int]], int]:
    """Derive the call's exit graph from the source.

    Returns the wire call's offset, every `call _answer` exit as
    (offset, outcome), every run-reset statement's offset, every exitWith
    block's span, and the latch threshold. Exits are matched on the
    comment-blanked text because a comment naming an outcome must not look like
    one; string literals stay intact because the outcome names live in them.
    """
    body = source()
    code = _code_only(body)
    wire = code.index("_extension callExtension")
    exits = [
        (match.start(), match.group(1))
        for match in re.finditer(r'\[\s*"([a-z_]+)"[^]]*\]\s*call\s+_answer\b', code)
    ]
    resets = [
        match.start() for match in re.finditer(r'_tally\s+set\s+\[\s*"[^"]*"\s*,\s*0\s*\]', code)
    ]
    latch = re.search(r"\b_latchAfter\s*=\s*(\d+)", code)
    assert latch is not None, "the latch threshold is not in the source"
    return wire, exits, resets, _exit_with_spans(_code_shell(body)), int(latch.group(1))


def test_a_reply_that_cannot_be_parsed_resets_the_run_so_a_second_outage_is_audible() -> None:
    """#684: an unreadable reply must end the transport-error run like any other.

    The failure this pins is an *ordering*, not a string: the unreadable exit
    returned before any reset, so a reply that arrived could not clear the
    latch it inherited, and the outage after it was silent — no per-call line
    (quiet above the threshold), no second latch line (said only at the
    threshold), no `CTI|daemon_down` (already true). Derived from the exit
    graph rather than pinned to the fix's wording, so a semantic regression
    that keeps the file's strings intact still reddens — the gap #72's
    round-four review named in the substring tests below.
    """
    wire, exits, resets, spans, latch = _call_events()
    post_wire = [(offset, name) for offset, name in exits if offset > wire]

    # Every exit the wire can reach is one of: a transport failure (the latch
    # applies, so it must return *before* any reset) or a reply the world
    # received (which must have passed a reset, whatever it went on to say).
    # An exit added later lands here unclassified and is refused, rather than
    # silently counting as either.
    reply_outcomes = {"ok", "rejected", "error", "unreadable", "campaign_lost"}
    for offset, name in post_wire:
        if name == "unreachable":
            assert not _reaches(resets, offset, spans, wire), (
                "the transport-failure exit passes a reset, which would end the latch"
            )
        else:
            assert name in reply_outcomes, f"unclassified exit outcome {name!r}"
            assert _reaches(resets, offset, spans, wire), (
                f"the {name!r} exit reaches no reset of the transport-error run"
            )

    # The scenario, as arithmetic over the derived facts: `latch` transport
    # errors reach the threshold — the latch line is said once and the per-call
    # lines go quiet — then the daemon returns and its first reply cannot be
    # parsed. That exit's reset (asserted above) returns the run to zero, so
    # the next outage's run of 1 sits below the threshold and its per-call line
    # writes again. Against the unfixed ordering the run was still at the
    # threshold, every `CTI|` transport line stayed unwritten, and the second
    # outage was never announced.
    names = {name for _offset, name in post_wire}
    assert latch > 1, "a threshold of one cannot distinguish latch from per-call"
    assert "unreadable" in names, "no exit carries the unreadable outcome"


def test_the_run_is_counted_in_the_one_place_every_failure_passes_through() -> None:
    body = source()
    # Counted on the tally the file already broadcasts, so a probe reading
    # `cti_daemonCall` sees the run the log is being quieted against.
    assert 'getOrDefault ["consecutive_unreachable", 0]' in body
    assert '_tally set ["consecutive_unreachable", _run]' in body


def test_the_per_call_line_goes_quiet_past_the_threshold() -> None:
    body = source()
    # The noisy line is emitted only inside the below-threshold guard.
    assert "if (_run < _latchAfter) then {" in body
    assert "CTI|daemon_unreachable verb=%1 detail=%2" in body


def test_the_latch_is_said_once_at_the_threshold() -> None:
    body = source()
    assert "if (_run isEqualTo _latchAfter) then {" in body
    assert "CTI|daemon_gone_latched consecutive=%1 detail=%2 " in body
    assert "— daemon_unreachable lines quiet until the daemon answers" in body


def test_the_threshold_is_five_consecutive_transport_errors() -> None:
    assert "private _latchAfter = 5;" in source()


def test_daemon_call_still_reaches_the_wire_and_resets_on_recovery() -> None:
    """The cadence gate belongs to the pump; daemonCall still observes recovery (#96).

    Revised by #684: the run now has two reset sites — the unreadable exit's,
    added by the fix, and the recovery reset below the transport-failure branch
    — so the recovery reset is asserted on the reply exits' path through the
    derived graph rather than pinned as the file's only reset line.
    """
    wire, exits, resets, spans, _latch = _call_events()
    # The wire call still precedes the branch that counts the failure.
    branch_at = next(offset for offset, name in exits if name == "unreachable")
    assert wire < branch_at
    # The recovery reset still sits beyond the transport-failure branch's
    # closing brace, so a latched run still ends on the first readable reply.
    branch_end = max(end for start, end in spans if start < branch_at)
    assert any(reset > branch_end for reset in resets)


def test_the_effect_pump_skips_wire_calls_until_its_half_open_probe() -> None:
    body = pump_source()
    gate_at = body.index('if (diag_tickTime < (_transport get "next_poll_at")) exitWith {};')
    call_at = body.index('private _answer = [["poll"] call cti_fnc_requestId')
    assert gate_at < call_at
    assert '["next_poll_at", 0]' in body
    assert "private _halfOpenInterval = _interval max 10;" in body
    assert "if (_failures >= _latchAfter) then {" in body
    assert '_transport set ["next_poll_at", diag_tickTime + _halfOpenInterval];' in body


def test_the_half_open_cadence_fits_daemon_restart_probe_window() -> None:
    body = pump_source()
    restart = (REPO / "spike" / "probes" / "daemon-restart.sqf").read_text(encoding="utf-8")
    assert "private _halfOpenInterval = _interval max 10;" in body
    assert "_deadline = diag_tickTime + 90;" in restart
