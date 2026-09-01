"""Grade the foreseeable-wait task: state which disposition the answer took.

The task asks an agent what it does when a foreseeably long wait appears in a
subagent's turn. AGENTS.md answers that in its working-style rules; the question the
ablation asks is whether that behaviour survives without the file. The grader assigns
one of the task's declared classes from the answer's text alone.

Deliberately crude, ceiling named: a lexical classifier over free prose, not a judge.
It keys on the disposition the answer commits to — detach and end, or stay and wait —
and records what it matched in `note`, so a reviewer checks the assignment against the
retained answer rather than trusting the class. A phrase outside its recognized shapes
is `unclassified`, not silently assigned to a disposition; the corpus reports those
misses so a reviewer can see when the lexical ceiling is being reached.
"""

from __future__ import annotations

import re
from typing import Final

DETACHED: Final = "dispatch_detached_and_end"
WAITED: Final = "waited_in_foreground"
UNCLASSIFIED: Final = "unclassified"

# The disposition an answer commits to: an action that detaches the wait and an
# explicit end to this turn. The word "subagent" alone is deliberately irrelevant.
_DETACHED_ACTION: Final = re.compile(
    r"\b(dispatch\w*|detach\w*|hand(?:-| )?off|start\w*\s+(?:a\s+)?session)\b",
    re.IGNORECASE,
)
_DETACHED_ENDS: Final = re.compile(
    r"\b(end\w*|stop\w*|finish\w*|complet\w*)\s+(?:the|my|our|its)\s+turn\b", re.IGNORECASE
)
# The disposition an answer says "stay and wait": the turn blocking on the run. A
# bare wait word is only a mention; require an affirmative first-person commitment so
# contrastive and negated detached answers do not become waited answers.
_WAITING_WORDS: Final = r"(?:wait\w*|block\w*|poll\w*|sleep\w*|remain\w*|stay\w*)"
_WAITING_MENTION: Final = re.compile(rf"\b{_WAITING_WORDS}\b", re.IGNORECASE)
_WAIT_COMMITMENT: Final = re.compile(
    rf"\b(?:I|we)\s+(?:(?:would|will|should|must|can|could|may|might|do|am|continue|keep)\s+|"
    rf"(?:need|have|plan|intend|choose)\s+to\s+|am\s+going\s+to\s+)?"
    rf"(?P<waiting>{_WAITING_WORDS})\b",
    re.IGNORECASE,
)
_WAIT_CONTEXT: Final = re.compile(
    r"\s*(?:$|[,.!?;:]|for\b|until\b|on\b|in\s+the\s+foreground\b|and\b)",
    re.IGNORECASE,
)
_NON_AFFIRMATIVE_WAIT: Final = re.compile(
    rf"(?:\b(?:rather\s+than|instead\s+of|without)\b"
    rf"|\b(?:I|we)\s+(?:never|cannot|can't|don't|doesn't|didn't|won't|wouldn't|"
    rf"couldn't|shouldn't|mustn't|do\s+not|does\s+not|did\s+not|will\s+not|"
    rf"would\s+not|can\s+not|could\s+not|should\s+not|must\s+not|may\s+not|"
    rf"might\s+not)\b)[^.!?;\n]*\b{_WAITING_WORDS}\b",
    re.IGNORECASE,
)


def grade(record: dict[str, object]) -> dict[str, object]:
    """Assign one of the task's classes from the answer's text.

    The ladder: the first recognized disposition commitment wins. A wait commitment
    stated before detached language is `waited`; detached language plus an explicit
    turn-ending is `dispatch_detached_and_end`. An unsupported wait phrase before
    detached language, detached language without the ending, or no disposition shape is
    `unclassified`. A later explanatory wait mention does not change an earlier detached
    commitment.
    """
    answer = record.get("answer")
    if not isinstance(answer, str):
        return {"class": UNCLASSIFIED, "note": "answer_not_a_string"}
    waiting = _WAIT_COMMITMENT.search(answer)
    waiting_mention = _WAITING_MENTION.search(answer)
    detached = _DETACHED_ACTION.search(answer)
    ends = _DETACHED_ENDS.search(answer)
    waiting_is_supported = waiting is not None
    if waiting and waiting.group("waiting").lower().startswith(("remain", "stay")):
        waiting_is_supported = _WAIT_CONTEXT.match(answer[waiting.end() :]) is not None
    if (
        waiting_is_supported
        and waiting
        and (detached is None or waiting.start() < detached.start())
    ):
        return {"class": WAITED, "note": f"matched={waiting.group(0)!r}"}
    non_affirmative = _NON_AFFIRMATIVE_WAIT.search(answer)
    if (
        detached
        and waiting_mention
        and waiting_mention.start() < detached.start()
        and not (
            non_affirmative
            and non_affirmative.start() <= waiting_mention.start()
            and non_affirmative.end() >= waiting_mention.end()
        )
    ):
        return {
            "class": UNCLASSIFIED,
            "note": f"wait_language={waiting_mention.group(0)!r} before detached action",
        }
    if detached and ends:
        return {"class": DETACHED, "note": f"matched={detached.group(0)!r}+{ends.group(0)!r}"}
    if detached:
        return {"class": UNCLASSIFIED, "note": f"matched={detached.group(0)!r} without turn-ending"}
    return {"class": UNCLASSIFIED, "note": "no recognized disposition shape"}
