"""Transferring-escalation conditions as data, emitted when one fires (ADR-0071 ruling 5, #325).

Escalation has two kinds. *Consultative* escalation borrows judgement and keeps control — a
running model asking a stronger one for advice — and because it transfers no accountability it
needs no condition and lives nowhere here. *Transferring* escalation hands the task to a higher
profile and fires only on a **named condition**. This module is the four conditions ADR-0071
ruling 5 seeds, each stated as something a tool decides from recorded facts rather than something
an agent judges — which is what "data" means here.

The conditions live as data in `config/escalation-conditions.json`, read on every call with no
module cache. That is the same discipline `tools/routing_policy.py` runs under, and the row
shape — id, name, remedy — mirrors its `Rule`. The decision logic is code rather than data,
because each condition's predicate is structurally different: a routing class matches by path or
phrase uniformly, so its matcher can be one walk over data rows, whereas these four ask four
different questions of four different facts. So the *rows* are data and the list grows only at a
retro, while each row's `predicate` names the Python function that decides it.

Emission, not resident prose (#209, ADR-0071 ruling 5). Where a rule-table already decides, an
agent is not handed numbers to reason about, so this tool decides and what reaches the agent is
the fired condition and its remedy. A condition that has not fired emits nothing at all — but a
table that could not be read is not "nothing fired": `evaluate` carries that as a third state in
its `unreadable`, which a brief surfaces rather than rendering as the empty section a brief with
no escalation due carries. The difference between a condition and a rule written into a memory
file every session loads is that the condition is silent until it is true — and silent only then,
not when the table that holds it could not be read.

What is decidable today, and what is not. A condition fires only on facts the caller supplies in
a `Context`, and each fact is either recorded or it is not:

- `routing_class` is recorded on every dispatch record (#323), reachable from an issue body
  through `routing_policy.classify_issue`. A caller reading the body can supply it, and condition
  4 fires for real.
- `review_rounds`, `finding_above_low` and `attempts` are **not** mechanically recorded today. The
  review loop, the observatory and the arbiter are sequenced work (ADR-0071 rulings 4 and 6,
  #333), so a caller that has none of these supplies `None`, and conditions 1, 2 and 3 do not
  fire.

`None` is a third value. It is "this fact is not recorded", distinct from "this fact is recorded
false", and a condition that lacks a fact it needs emits nothing rather than guessing. That is
the "say so plainly rather than invent a heuristic" of #325: the tool never fires on missing
data, and the gap is documented in this docstring rather than papered over with a default. When
the review loop records rounds and findings, the same caller supplies them as integers and
booleans and the conditions light up unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

CONDITIONS_RELATIVE: Final = Path("config/escalation-conditions.json")

# ADR-0071 ruling 4: "Three fix rounds, then escalate." A round is one fix-and-re-review cycle;
# the first review is round zero, so this fires after the third re-review. Stated as a constant
# because "three rounds" was ambiguous by one and a tool has to decide it.
THREE_ROUND_THRESHOLD: Final = 3

# Condition 2 reads the two most recent prior items; condition 3 needs at least two attempts.
# Named because the ADR counts both, and a tool that decides them holds the count as a constant
# rather than a bare integer a reader has to map back to the ruling.
CONSECUTIVE_ITEMS: Final = 2
RETRY_MIN_ATTEMPTS: Final = 2

# Routing class 4, `plausible_wrong_fix_goes_green` — the #181 shape. A constant rather than a
# read of the policy so this module does not couple to `routing_policy` to recognise its own
# fourth condition; the class id is stable (validated as the ordered 1..7 in routing_policy).
CLASS_FOUR: Final = 4


class Attempt(NamedTuple):
    """One implementation attempt of an item, in the facts a condition reads.

    `clean_base` is `None` when that fact is not recorded, distinct from a recorded `False`: a
    retry whose clean-base status is unknown is not a retry condition 3 can fire on.
    """

    profile: str
    clean_base: bool | None


class ItemState(NamedTuple):
    """One item's escalation-relevant facts. Each is recorded or it is `None`.

    `None` is "not recorded" and never "recorded as false": a condition that needs a fact it does
    not have emits nothing, so missing data can never manufacture a firing.
    """

    routing_class: int | None
    # Completed fix-and-re-review cycles; 0 is the first review alone. `None` until the review
    # loop records it (ADR-0071 ruling 4, sequenced).
    review_rounds: int | None = None
    # A live review finding above Low exists. `None` until findings carry severity (ruling 4).
    finding_above_low: bool | None = None
    # Implementation attempts of this item, oldest first. `None` until attempts are recorded;
    # an empty tuple is recorded-zero, distinct from not-recorded the way every other fact is.
    attempts: tuple[Attempt, ...] | None = None


class Context(NamedTuple):
    """The facts the four conditions are decided from.

    `item` is the item the emission would reach (conditions 1, 3, 4 read it). `prior` is the
    ordered history of recently-resolved items, most-recent-last, which condition 2 reads. The
    `arbiter` is the implementer seat's escalation head that condition 1 names; the caller
    resolves it so this module never carries a profile that drifts.
    """

    item: ItemState
    prior: tuple[ItemState, ...] = ()
    arbiter: str | None = None


class Condition(NamedTuple):
    """One escalation condition row: its identity, its deciding predicate, and its remedy."""

    id: int
    name: str
    predicate: str
    remedy: str


class Conditions(NamedTuple):
    """The parsed condition table."""

    source: str
    conditions: tuple[Condition, ...]


class ReadResult(NamedTuple):
    """A parsed condition table or the reason reading it failed."""

    conditions: Conditions | None
    error: str = ""


class EscalationError(ValueError):
    """An escalation condition table whose shape cannot safely govern emissions."""


class Emission(NamedTuple):
    """One fired condition and the recorded facts that fired it."""

    condition: Condition
    evidence: tuple[str, ...]


class Evaluation(NamedTuple):
    """The evaluation outcome: fired emissions, or inputs no evaluation could read.

    The third state (#323's distinction; #347): an input the conditions need that could not be
    read is neither "fired" nor "did not fire", and it reaches the caller in `unreadable` rather
    than as the empty `emissions` a brief with no escalation due carries. Each `unreadable` entry
    names an input and why it could not be read — prose diagnostic, never a grouping key. Silence
    — empty `emissions` with nothing `unreadable` — is reserved for "nothing fired", never for
    "nobody could look": escalation is advisory, which is exactly why a lost emission costs
    nothing to report and everything to hide (#41 — a check that could not run is not a check
    that passed).
    """

    emissions: tuple[Emission, ...]
    unreadable: tuple[str, ...] = ()


VERSION_ERROR: Final = "conditions must be a version 1 object"
CONDITIONS_LIST_ERROR: Final = "conditions must be a list"
CONDITION_OBJECT_ERROR: Final = "each condition must be an object"
CONDITION_FIELDS_ERROR: Final = "each condition must carry id, name, predicate and remedy"
PREDICATE_ERROR: Final = (
    "each condition's predicate must name a decided predicate; an unknown one cannot fire and"
    " must be corrected in the data rather than silently skipped"
)
REMEDY_ERROR: Final = "every condition must name its remedy"
IDS_UNIQUE_ERROR: Final = "condition ids must be unique"


def at_three_round_wall(item: ItemState) -> bool:
    """Return whether the item sits at the wall conditions 1, 2 and 3 share.

    That wall is three fix rounds with a finding above Low still open. Both facts must be
    recorded — a wall read off missing data is a guess, and the tool does not guess.
    `finding_above_low is True` rather than truthy so `None` (not recorded) is distinct from
    `False` (recorded: no such finding).
    """
    return (
        item.review_rounds is not None
        and item.review_rounds >= THREE_ROUND_THRESHOLD
        and item.finding_above_low is True
    )


def _three_round_wall(context: Context) -> tuple[str, ...] | None:
    """Condition 1: a review cycle holding a finding above Low after three fix rounds.

    The arbiter is the implementer seat's escalation head (ADR-0071 ruling 4) — the profile the
    transfer reaches, and a fact this condition needs: its remedy orders a transfer to "the
    arbiter named in the emission", so a caller that resolved none must not fire, the same way a
    missing wall fact must not. The arbiter is recorded in the seat table and reaches a real
    dispatch resolved, so this guards the unresolvable case rather than a common one.
    """
    item = context.item
    if not at_three_round_wall(item):
        return None
    if not context.arbiter:
        return None
    evidence = [f"review_rounds={item.review_rounds}", "finding_above_low=true"]
    # The arbiter the transfer reaches; recorded as a fact so the emission names a profile the
    # caller resolved rather than one this module hard-codes.
    evidence.append(f"arbiter={context.arbiter}")
    return tuple(evidence)


def _consecutive_same_class_wall(context: Context) -> tuple[str, ...] | None:
    """Condition 2: two consecutive prior items of one routing class each at the three-round wall.

    A fact about the history, read off the two most recent prior items: they must be consecutive
    (which `prior[-2]`, `prior[-1]` are by construction), share a recorded routing class, and
    each be at the wall. Ruling 5 reads this as evidence that the *class* is under-specified and
    "the next one is re-planned rather than re-fixed", so the current item the remedy re-plans
    must be of that same class — a class-6 current item is not "the next one" of two stuck
    class-5 items, and re-planning it would answer a question the history did not ask.

    The pair is read from `prior` because the next item exists only once the two before it have
    each reached the wall and moved on: the current item is the one dispatched against that
    history, not the second of the pair, so the condition fires for it. Firing the moment a
    second item reaches the wall would re-plan an item already at the wall — which is the re-fix
    the remedy exists to replace — so it deliberately does not.
    """
    shared = context.item.routing_class
    prior = context.prior
    if shared is None or len(prior) < CONSECUTIVE_ITEMS:
        return None
    first, second = prior[-2], prior[-1]
    if first.routing_class != shared or second.routing_class != shared:
        return None
    if not (at_three_round_wall(first) and at_three_round_wall(second)):
        return None
    return (f"routing_class={shared}", f"consecutive_items={CONSECUTIVE_ITEMS}")


def _retry_wall(context: Context) -> tuple[str, ...] | None:
    """Condition 3: a second attempt from a clean base on a different profile itself at the wall.

    The retry's outcome is the signal, not the retry itself: the current attempt must have
    reached the three-round wall, and the attempt before it must differ in profile and have been
    from a clean base. Ruling 5 names the **second** attempt — a third or later attempt is not
    this condition, because the transfer it triggers should have fired on the second and a third
    is what the remedy says not to dispatch. So this fires at exactly two attempts, not two or
    more. `clean_base is not True` so a not-recorded base (`None`, distinct from a recorded
    `False`) does not manufacture a firing, and `attempts is None` is the not-recorded case.
    """
    item = context.item
    if not at_three_round_wall(item):
        return None
    attempts = item.attempts
    if attempts is None or len(attempts) != RETRY_MIN_ATTEMPTS:
        return None
    previous, latest = attempts[0], attempts[1]
    if latest.clean_base is not True or latest.profile == previous.profile:
        return None
    return (
        f"attempts={len(attempts)}",
        f"prior_profile={previous.profile}",
        f"retry_profile={latest.profile}",
        "retry_clean_base=true",
    )


def _routing_class_four(context: Context) -> tuple[str, ...] | None:
    """Condition 4: an item declaring routing class 4, the #181 shape."""
    if context.item.routing_class == CLASS_FOUR:
        return (f"routing_class={CLASS_FOUR}",)
    return None


# Each condition's `predicate` names one entry. A key not here is rejected at parse time rather
# than silently skipped, so a condition the code cannot decide is fixed in the data.
PREDICATES: Final[dict[str, Callable[[Context], tuple[str, ...] | None]]] = {
    "three_round_wall": _three_round_wall,
    "consecutive_same_class_wall": _consecutive_same_class_wall,
    "retry_wall": _retry_wall,
    "routing_class_four": _routing_class_four,
}


def _condition(entry: object) -> Condition:
    if not isinstance(entry, dict):
        raise EscalationError(CONDITION_OBJECT_ERROR)
    try:
        identifier = int(entry["id"])
        name = str(entry["name"])
        predicate = str(entry["predicate"])
        remedy = str(entry["remedy"])
    except (KeyError, TypeError, ValueError) as error:
        raise EscalationError(CONDITION_FIELDS_ERROR) from error
    if predicate not in PREDICATES:
        raise EscalationError(PREDICATE_ERROR)
    if not remedy:
        raise EscalationError(REMEDY_ERROR)
    return Condition(identifier, name, predicate, remedy)


def parse_conditions(text: str) -> Conditions:
    """Validate enough shape that a partial condition table can never govern silently."""
    document = json.loads(text)
    if not isinstance(document, dict) or document.get("version") != 1:
        raise EscalationError(VERSION_ERROR)
    raw = document.get("conditions")
    if not isinstance(raw, list):
        raise EscalationError(CONDITIONS_LIST_ERROR)
    conditions = tuple(_condition(entry) for entry in raw)
    ids = [condition.id for condition in conditions]
    if len(set(ids)) != len(ids):
        raise EscalationError(IDS_UNIQUE_ERROR)
    return Conditions(source=str(document.get("source", "")), conditions=conditions)


def read_conditions(path: Path) -> ReadResult:
    """Read on every call. There is intentionally no module cache or startup load."""
    try:
        return ReadResult(parse_conditions(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
        return ReadResult(None, f"{path}: {error}")


def evaluate(read: ReadResult, context: Context) -> Evaluation:
    """Return fired conditions as emissions in id order; an unreadable table is a third state.

    Three outcomes a caller must not conflate (ADR-0071 ruling 5; the #323 distinction, #347): a
    condition fired (`emissions` non-empty); the table read and none fired (`emissions` empty,
    `unreadable` empty); and the table could not be read (`emissions` empty, `unreadable` names
    why). A predicate returning `None` is the unfired case and contributes no emission. The read
    result — parsed table or the reason it failed — is the input, so the unreadable case carries
    its reason to the caller rather than collapsing into the silence reserved for nothing fired.
    """
    if read.conditions is None:
        return Evaluation((), (read.error or "the condition table could not be read",))
    fired = []
    for condition in read.conditions.conditions:
        evidence = PREDICATES[condition.predicate](context)
        if evidence is not None:
            fired.append(Emission(condition, evidence))
    return Evaluation(tuple(sorted(fired, key=lambda emission: emission.condition.id)))


def render(emissions: tuple[Emission, ...]) -> tuple[str, ...]:
    """Render fired emissions as the lines a briefing carries to the agent.

    Each emission names its condition, the facts that fired it, and its remedy — the data a
    transferring escalation hands over. Mirrors the `refusal=<kind>` / evidence / `action=` shape
    a routing advisory carries, so an agent reads both the same way.
    """
    lines: list[str] = []
    for emission in emissions:
        condition = emission.condition
        lines.append(f"escalation={condition.id}:{condition.name}")
        lines.extend(f"  {fact}" for fact in emission.evidence)
        lines.extend(f"  {line}" for line in condition.remedy.splitlines())
    return tuple(lines)


def render_unreadable(unreadable: tuple[str, ...]) -> tuple[str, ...]:
    """Render inputs an evaluation could not read, so the third state is not mistaken for silence.

    Pairs with `render`: fired emissions become `escalation=N:...` lines and an unreadable input
    becomes these, so a reader who sees the section can tell "nothing fired" (no section at all)
    from "nobody could look" (this notice). Each entry is the `path: reason` a read returned.
    """
    lines = [
        (
            "  unreadable — an input a condition needs could not be read, so this is not the"
            " silence of a condition that has not fired:"
        )
    ]
    lines.extend(f"  could not read {reason}" for reason in unreadable)
    return tuple(lines)
