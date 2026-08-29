"""Grade the foreseeable-wait task: state which disposition the answer took.

The task asks an agent what it does when a foreseeably long wait appears in a
subagent's turn. AGENTS.md answers that in its working-style rules; the question the
ablation asks is whether that behaviour survives without the file. The grader assigns
one of the task's declared classes from the answer's text alone.

Deliberately crude, ceiling named: a lexical classifier over free prose, not a judge.
It keys on the disposition the answer commits to — detach and end, or stay and wait —
and records what it matched in `note`, so a reviewer checks the assignment against the
retained answer rather than trusting the class. A classifier this shallow misclassifies
unusual phrasings; that is variance, and the corpus handles variance by tolerance and
quarantine rather than by a smarter grader.
"""

from __future__ import annotations

import re
from typing import Final

DETACHED: Final = "dispatch_detached_and_end"
WAITED: Final = "waited_in_foreground"
UNCLEAR: Final = "unclear"

# The disposition an answer commits to when it says "dispatch detached and end".
_DETACHED: Final = re.compile(
    r"\b(dispatch\w*|detach\w*|subagent|watch\w*|hand(?:-| )?off|single-shot)\b", re.IGNORECASE
)
_DETACHED_ENDS: Final = re.compile(
    r"\b(end\w*|stop\w*|finish\w*|complet\w*)\s+(?:the|my|our|its)\s+turn\b", re.IGNORECASE
)
# The disposition an answer says "stay and wait": the turn blocking on the run.
_WAITING: Final = re.compile(
    r"\b(wait\w*|block\w*|poll\w*|sleep\w*|remain\w*|stay\w*)\b", re.IGNORECASE
)


def grade(record: dict[str, object]) -> dict[str, object]:
    """Assign one of the task's classes from the answer's text.

    The ladder: a wait commitment with no detached language is `waited`; detached
    language plus an explicit turn-ending is `dispatch_detached_and_end`; detached
    language without the ending, or nothing either way, is `unclear`.
    """
    answer = record.get("answer")
    if not isinstance(answer, str):
        return {"class": UNCLEAR, "note": "answer_not_a_string"}
    waiting = _WAITING.search(answer)
    detached = _DETACHED.search(answer)
    ends = _DETACHED_ENDS.search(answer)
    if waiting and not detached:
        return {"class": WAITED, "note": f"matched={waiting.group(0)!r}"}
    if detached and ends:
        return {"class": DETACHED, "note": f"matched={detached.group(0)!r}+{ends.group(0)!r}"}
    if detached:
        return {"class": UNCLEAR, "note": f"matched={detached.group(0)!r} without turn-ending"}
    return {"class": UNCLEAR, "note": "no disposition language at all"}
