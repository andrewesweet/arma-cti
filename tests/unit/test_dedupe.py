"""The window of answers the daemon can give a second time (#69, ADR-0034)."""

from __future__ import annotations

from cti_daemon.dedupe import Answered


def test_a_line_never_seen_has_no_answer() -> None:
    assert Answered().recall('{"id":"a"}') is None


def test_an_identical_line_is_answered_from_the_answer_it_was_given() -> None:
    answered = Answered()
    answered.remember('{"id":"a"}', request_id="a", verb="command", reply='{"status":"ok"}')
    recalled = answered.recall('{"id":"a"}')
    assert recalled is not None
    assert (recalled.id, recalled.verb, recalled.reply) == ("a", "command", '{"status":"ok"}')


def test_a_line_differing_anywhere_is_a_different_request() -> None:
    # The key is the request as it arrived. A resend is byte-identical by
    # construction, so anything that is not is work to carry out.
    answered = Answered()
    answered.remember('{"id":"a","payload":{"n":1}}', request_id="a", verb="command", reply="{}")
    assert answered.recall('{"id":"a","payload":{"n":2}}') is None


def test_the_oldest_answer_is_forgotten_once_the_window_is_full() -> None:
    answered = Answered(window=2)
    for index in range(3):
        answered.remember(f"line-{index}", request_id=str(index), verb="ping", reply="{}")
    assert answered.recall("line-0") is None
    assert answered.recall("line-1") is not None
    assert answered.recall("line-2") is not None
    assert len(answered) == 2


def test_remembering_the_same_line_twice_does_not_grow_the_window() -> None:
    answered = Answered()
    for _ in range(5):
        answered.remember("line", request_id="a", verb="ping", reply="{}")
    assert len(answered) == 1
