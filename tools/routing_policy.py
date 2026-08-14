"""The routing classes, read for every dispatch and landing (#266), re-founded by #326.

An issue body only declares the expected surface, so dispatch is an advisory read even
though a match refuses. Landing reads the real diff and is the enforcing gate. This is
separate from queue policy: queue state decides whether work may start now; this file
decides which class a piece of work is in and what that class asks for.

**The classes no longer share one basis, and that is ADR-0071's re-founding (#326).** The
document used to be the keep-on-Claude policy, every row resting on provenance under
ADR-0061 Decision 2. Ruling 1 withdrew provenance, and the table was re-founded class by
class on what each row actually rests on — capability, or conflict of interest, or in one
case a provisional carve-out. Two rows died: `gated_semantic_surfaces`, whose basis was
provenance and whose human sign-off gate was never this file, save its two gate paths
which moved to class 6; and `anthropic_plan_meter`, whose meter is read over plain HTTP
with no Claude session involved. Their ids, 1 and 7, are retired and never reused. The
third case did not outlive #327's second round: class 2's provisional carve-out is
re-founded on its seat there, and the carve-out itself lives in `tools/dispatch.py`'s seat
table, where the issue that deleted the provenance vocabulary could name it.

**An id is a stable historical handle, not a position.** Ids must be unique, positive and
strictly ascending, but need not be contiguous, because a retired class must be able to
leave without renumbering the rows two other modules address by id — class 5 here, class 4
in `tools/escalation.py`. `REQUIRED_CLASSES` is the fail-closed half: a table that dropped
one of the rows another module addresses would otherwise parse and govern silently.

**Four fields decide what a row does, and three of them are new.** `refuses` (default true)
says whether a match produces a refusal at all: classes 4 and 5 classify without refusing,
because their remedies are a capability route and a subagent prohibition rather than a bar
on a route. `binds_every_instance` (default false) does **not** touch the Claude-lane
exemption and never has — `_refusing_rules` does not consult it. What it does is forbid the
row any exception: class 6's conflict of interest — no instance authors the gate that judges
it — cannot be excepted by the instance it judges. Round 1 documented it here as the field
that binds Claude, which is the one false sentence a future row author would act on, so it
is corrected rather than softened (#326, review round 2 claim 2).

`required_seats` (default empty) is the third, and it is what re-founding a row on
**capability** actually takes, and it is also the only field that lifts the Claude-lane
exemption. A row that names it refuses every route whose seat is not on the list, **on every
lane including Claude's**, and refuses none whose seat is on it. Class 3 is the row: ADR
authorship rests on seats (ADR-0071 rulings 2 and 4) rather than on provenance, and a
lane-selected refusal there was a keep-on-Claude rule wearing a capability remedy — it
refused `codex`/`codex-sol-xhigh`/`planner`, the first entry in the very list its remedy
prescribes (#326, review round 1 claim 2). Class 2 joined it in #327's second round: the
row's `seats: ["orchestrator"]` read as scoping and never was, so the lane-selected refusal
it carried refused every seat on every non-Claude lane for an orchestration declaration —
a second provenance refusal the landing's prose had counted away — and `required_seats`
scoped it to the one seat that performs the act. The third round widened that appointment to
the whole route (review round 3 claim 1): a list of one refused `review`, the seat ruling 4
mandates, `implementer`, the seat ruling 2 leaves to land, and `recon`, the read-only seat —
the same deadlock the paragraph below rules on, one paragraph too late, caught by walking
the row rather than reading it.

**A row admits the whole route, not its first step.** Round 1 admitted `planner` alone, and
the planner is the seat ruling 2 defines as neither gating nor landing — so no route could
author *and* land an ADR, and ruling 4's reviewing instance could not be dispatched at all
(review round 2 claim 1). Class 3 therefore admits `planner`, `implementer` and `review`
together, and `recon` beside them. Class 2 has admitted the same shape plus its own seat
since #327's third round: `orchestrator` performs the act, `planner`, `implementer` and
`review` are the route, `recon` rides the same cannot-perform ground, and `retro` and
`fable` stay outside on the ground the caveat demanded a fixer pick — both seats can take
work and neither is a seat any landed ruling requires for the route, so refusing them
selects something, where refusing `recon` selected nothing. The rule this generalises has
two halves, and round 2 landed only the first: what a capability row admits is every seat
some landed ruling requires for that work to be finished, **and every seat that cannot
perform the act the row is about at all**. Applying the first half as a necessity rule is
what refused `recon` — a read-only sweep of prior ADRs, from a seat that authors, lands and
reviews nothing — and a bar on a seat that cannot do the thing defeats no purpose of the
class while routing cheap reconnaissance to a seat that gates and lands (review round 3
claim 4). A row is checked by walking every seat in `tools/dispatch.py`'s `SEATS` against it
rather than by reading it.
A seat-bound row is
therefore enforceable only where a seat exists, which is dispatch: `just land` has no seat
and never will, so such a row carries no `landing_path_prefixes` and `parse_policy` refuses
one that does, rather than letting the landing rung silently re-derive the lane bar.

**The document carries the pre-#326 one beside it for one transition window, and that is
review round 3's claim 1.** A parser is imported by a *running process*: `just land` in an
in-flight worktree reads the policy out of fetched `origin/main` with whatever
`tools/routing_policy.py` that process started with, and the rebase brings the new module
into the tree but not into the process. The pre-#326 parser demanded the ordered table
1..7, so a file carrying only the re-founded table is unreadable to it — measured, all four
ways — and every in-flight landing and dispatch would refuse until its worktree rebased, on
a remedy telling the reader to repair a policy that is not broken, which sends them at a
class-6 gated file. That is `COVERAGE_UNSTATED`'s own argument, which this module already
made about a newly-mandatory field and did not apply to the id shape. So the re-founded
document lives under `routing_classes`, `routing_issue_exceptions` and
`routing_route_exceptions`, and `classes`, `issue_exceptions` and `route_exceptions` keep
the pre-#326 document frozen for the older parser. A parser reads **one** view whole: this
one takes the re-founded keys when the table is there and the legacy keys otherwise, which
is also how it goes on reading `origin/main`'s pre-#326 copy. The frozen half is deleted
once no worktree predating that landing is still in flight.

Since #302 the document carries a second job. Class 5's `landing_path_prefixes` is the
**one authority** for what an in-world surface is: `just land`'s corpus rung, the
admission cross-check in `tools/admission.py` and the gate prediction in `tools/brief.py`
all read it from here rather than each holding a list. It lives in data rather than in
Python because `just land` reads it out of fetched `origin/main` — a candidate diff must
not be able to widen the list that judges it — and because three copies of a path list
rot, which is what #302 was filed about. Narrowing class 5 to a subagent rule leaves that
job untouched: `refuses` governs the routing gate, never `in_world_prefixes`.
"""

from __future__ import annotations

import json
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterable

POLICY_RELATIVE: Final = Path("config/dispatch-routing-policy.json")

# The class that carries the in-world surfaces. Looked up by **id** — a real lookup since
# #326, not an index, because the table is no longer contiguous — and the id is the stable
# handle; the name is what the row is called today and is asserted against the id in
# `tests/unit/test_corpus_gate.py` rather than relied on here.
IN_WORLD_CLASS_ID: Final = 5
IN_WORLD_CLASS: Final = "in_world_landings"

# The conflict-of-interest class. Named here because it is the one row whose invariant
# binds every instance, and because `tests/unit/test_routing_policy.py` asserts that the
# gate paths the withdrawn class 1 held arrived here rather than falling out.
CONFLICT_OF_INTEREST_CLASS_ID: Final = 6

# The orchestration class. Named for `REQUIRED_CLASSES` on class 3's ground rather than
# because another module addresses it by id: since #327 it is founded on its seats rather
# than on a lane, one of the two rows that refuse on the Claude lane, and its silent
# departure would withdraw the orchestration seating rule with nothing red.
ORCHESTRATION_CLASS_ID: Final = 2

# The ADR-authorship class. Named for `REQUIRED_CLASSES` rather than for a lookup: with
# class 2 it is one of the two rows that can refuse on the Claude lane, so its silent
# departure would have a consequence no other row's has (review round 2 claim 10).
ADR_AUTHORSHIP_CLASS_ID: Final = 3

# The rows that cannot leave silently, on either of two grounds. **Addressed by id
# elsewhere**: class 4 is `tools/escalation.py`'s `CLASS_FOUR`, deliberately a decoupled
# copy; class 5 is the in-world authority three readers depend on; class 6 is the
# conflict-of-interest rule ADR-0071 ruling 4's exemption list is bound by. **Load-bearing by
# absence**: classes 2 and 3 are the only rows that refuse on the Claude lane at all, so a
# table dropping either would not merely stop enforcing one class, and a table dropping both
# would return the Claude lane to exempt-from-everything, which is the state #326 was
# re-founded to end — and `parse_policy` would accept either table (review round 2 claim 10;
# class 2 joined the set in #327's second round, when it became the second seat-bound
# refusing row). A table missing one of these parses nowhere.
# Ids only, never names: the name is what a row is called today and a rename is not a removal
# — `tests/unit/test_corpus_gate.py` holds that the row's own name is not load-bearing, and
# pinning it here would quietly make it so.
REQUIRED_CLASSES: Final[frozenset[int]] = frozenset(
    {
        ORCHESTRATION_CLASS_ID,
        ADR_AUTHORSHIP_CLASS_ID,
        4,
        IN_WORLD_CLASS_ID,
        CONFLICT_OF_INTEREST_CLASS_ID,
    }
)


class View(NamedTuple):
    """The three document keys one parser vintage reads, taken together or not at all.

    Mixing them is the failure this shape forbids: reading the re-founded classes beside the
    legacy exceptions would hand a class-1 allowance to a table with no class 1, and reading
    the legacy classes beside the empty re-founded exceptions would silently withdraw #300's
    standing retro allowance from a document that still carries it. A view is chosen once,
    on the presence of the re-founded table, and everything below reads that view.
    """

    classes: str
    issue_exceptions: str
    route_exceptions: str


# The re-founded document (#326) and the pre-#326 one it is landing beside. The legacy names
# are the unprefixed keys because they are the ones the older parser reads by name and cannot
# be told to read anything else — the compatibility is entirely on this side of the fence.
REFOUNDED: Final = View("routing_classes", "routing_issue_exceptions", "routing_route_exceptions")
LEGACY: Final = View("classes", "issue_exceptions", "route_exceptions")


class Route(NamedTuple):
    """The lane/profile/seat triple at one policy clock instant."""

    lane: str
    profile: str
    seat: str
    now: datetime


class Rule(NamedTuple):
    """One class; its matching remains data rather than a branch per class.

    `refuses`, `binds_every_instance` and `required_seats` are what re-founding the table on
    capability and conflict of interest needed (#326), and all three default to the pre-#326
    behaviour so an older-shaped row still means what it used to. `refuses` false is a row
    that classifies and never bars a route — its remedy is addressed to whoever takes the
    work, not to the router. `binds_every_instance` true is a row that may carry **no
    exception**, and that is its whole live effect; the field a row uses to reach the Claude
    lane is `required_seats`, and only that (review round 2 claim 2).

    `seats` and `required_seats` are opposites and are deliberately not one field. `seats`
    lists the seats a row **matches** — it appends one evidence term and never filters, so it
    can only widen a match and never narrow one; #366 files the semantic, and since #327's
    second round no row in the live document carries the field (the frozen pre-#326 half
    still does, and this parser reads that view too, which is why the field survives here).
    `required_seats` lists the seats a row **admits**: the match is on the declaration, and
    the refusal fires for every seat that is not on the list, lane-blind. One is "this seat
    is the problem", the other is "only this seat is the answer", and collapsing them would
    have made class 3 unwritable without a lane bar — which is also why class 2's
    `seats: ["orchestrator"]`, read as scoping and never scoping, was replaced by
    `required_seats` in #327's second round rather than trusted.
    """

    id: int
    name: str
    label: str
    issue_path_prefixes: tuple[str, ...]
    issue_phrases: tuple[str, ...]
    seats: tuple[str, ...]
    landing_path_prefixes: tuple[str, ...]
    remedy: str
    refuses: bool = True
    binds_every_instance: bool = False
    required_seats: tuple[str, ...] = ()


class IssueException(NamedTuple):
    """One explicit body marker that excepts named class ids."""

    marker: str
    classes: tuple[int, ...]


class RouteException(NamedTuple):
    """One self-expiring human allowance for an exact route and class."""

    class_id: int
    lane: str
    profile: str
    seat: str
    # `None` is a **standing** widening, and it is deliberately not the default: a route
    # exception carries an expiry unless the human has ruled otherwise, so the absent
    # field must be accompanied by `"standing": true` and is refused on its own. The
    # first standing entry is the retro allowance (human ruling 2026-08-09, #299),
    # which superseded its own dated predecessor.
    expires_at: datetime | None


class Policy(NamedTuple):
    """The complete validated policy document.

    `coverage` is always a sentence and never empty: ADR-0071 records that this table's
    classes do not cover the surfaces they assert an invariant over, and a document that
    could drop that sentence would read as complete. A document that omits it gets
    `COVERAGE_UNSTATED`, the pessimistic reading. It is carried on the parsed policy so a
    consumer can put it where a reader meets it — `just land` and `just dispatch` both print
    it on a routing refusal.
    """

    source: str
    coverage: str
    claude_lane: str
    rules: tuple[Rule, ...]
    issue_exceptions: tuple[IssueException, ...]
    route_exceptions: tuple[RouteException, ...]


class Match(NamedTuple):
    """One matching row and the data that matched it."""

    rule: Rule
    evidence: tuple[str, ...]


class Advisory(NamedTuple):
    """What one declaration read found for one route: a refusal, an exemption, or neither.

    Three states rather than two, because "no row matched" and "a row matched and an
    exception lifted it" are different facts about a route and only one of them means the
    table had nothing to say. `refusal` is what the dispatch rung refuses on; `exemption` is
    what a cleared dispatcher is told instead of being told it is clear.
    """

    refusal: Match | None
    exemption: Match | None = None


class ReadResult(NamedTuple):
    """A parsed policy or the reason reading it failed."""

    policy: Policy | None
    error: str = ""


class PolicyError(ValueError):
    """A routing policy whose shape cannot safely govern dispatches."""


CLASS_OBJECT_ERROR: Final = "each class must be an object"
TIMEZONE_ERROR: Final = "expires_at must carry a timezone"
STANDING_ERROR: Final = (
    "a route exception carries exactly one of `expires_at` or `standing: true` —"
    " an undated widening must say so deliberately, and a dated one cannot also be standing"
)
CLASSES_LIST_ERROR: Final = "classes must be a list"
CLASS_IDS_ERROR: Final = (
    "class ids must be positive, unique and strictly ascending — an id is a stable handle other"
    " modules address a row by, so a retired class leaves a gap rather than renumbering its"
    " neighbours (#326)"
)
CLASS_NAMES_ERROR: Final = "class names must be unique"
REQUIRED_CLASSES_ERROR: Final = (
    "the table must carry every class another module addresses by id — dropping one would parse"
    " and govern silently, leaving that module matching against a row that is not there"
)
# A policy that states no coverage gets the honest default rather than silence, and the
# default is the pessimistic reading. Not a parse error, because the enforcing readers parse
# a copy they did not write: `just land` reads the policy out of fetched `origin/main` and
# `just dispatch` out of the main checkout, so making a newly-added field mandatory would
# make every pre-#326 copy unreadable and refuse every landing and dispatch for the whole
# window between this landing and that fetch. Fail-closed in the wrong place is still a
# break. The shipped file is held to stating its own coverage by
# `tests/unit/test_routing_policy.py` instead, which judges the copy this repo writes.
COVERAGE_UNSTATED: Final = (
    "This policy states no coverage of its own, so treat its class list as incomplete: a surface"
    " it does not name is uncovered, never cleared."
)
EXCEPTION_CLASS_ERROR: Final = (
    "an exception must name a class this table carries; one naming a retired or absent id excepts"
    " nothing and would sit in the file looking like a live allowance"
)
BINDING_EXCEPTION_ERROR: Final = (
    "a class that binds every instance may carry no exception: an instance that can except itself"
    " from the gate that judges it is the conflict of interest the class exists to forbid"
)
IN_WORLD_ERROR: Final = (
    f"class {IN_WORLD_CLASS_ID} must carry landing_path_prefixes — it is the one authority"
    " for what an in-world surface is, and three readers depend on it (#302)"
)
SEAT_BOUND_LANDING_ERROR: Final = (
    "a class bound to required_seats may carry no landing_path_prefixes — a seat-bound class is"
    " enforceable only where a seat exists, and `just land` has no seat, so landing prefixes on"
    " such a row would enforce something other than the rule the row states (#326)"
)
REMEDY_ERROR: Final = "every class must name its remedy"
ISSUE_EXCEPTION_ERROR: Final = "each issue exception must be an object"
ISSUE_CLASSES_ERROR: Final = "issue exception classes must be integers"
ROUTE_EXCEPTION_ERROR: Final = "each route exception must be an object"
VERSION_ERROR: Final = "policy must be a version 1 object"


def _strings(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        message = f"{field} must be a list of non-empty strings"
        raise PolicyError(message)
    return tuple(value)


def _rule(document: object) -> Rule:
    if not isinstance(document, dict):
        raise PolicyError(CLASS_OBJECT_ERROR)
    return Rule(
        id=int(document["id"]),
        name=str(document["name"]),
        label=str(document["label"]),
        issue_path_prefixes=_strings(document.get("issue_path_prefixes"), "issue_path_prefixes"),
        issue_phrases=_strings(document.get("issue_phrases"), "issue_phrases"),
        seats=_strings(document.get("seats"), "seats"),
        landing_path_prefixes=_strings(
            document.get("landing_path_prefixes"), "landing_path_prefixes"
        ),
        remedy=str(document["remedy"]),
        # Absent means the pre-#326 behaviour: a matched row refuses, and the Claude lane is
        # exempt from it. Only a row that says otherwise gets otherwise.
        refuses=document.get("refuses", True) is not False,
        binds_every_instance=document.get("binds_every_instance") is True,
        required_seats=_strings(document.get("required_seats"), "required_seats"),
    )


def _by_id(rules: tuple[Rule, ...], class_id: int) -> Rule:
    """Return the row with this id. A real lookup: since #326 the ids are not positions."""
    return next(rule for rule in rules if rule.id == class_id)


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise PolicyError(TIMEZONE_ERROR)
    return parsed


def _view(document: dict[object, object]) -> View:
    """Pick the document this parser reads, and read only that one.

    Presence of the re-founded table is the whole test. A copy that carries it is a #326 or
    later document and its exceptions are the re-founded ones — empty today; a copy that does
    not is `origin/main`'s pre-#326 document, which this parser still reads whole, because
    that is what a landing fetching a policy older than its own tree is handed.
    """
    return REFOUNDED if REFOUNDED.classes in document else LEGACY


def _rules(document: dict[object, object], view: View) -> tuple[Rule, ...]:
    raw_classes = document.get(view.classes)
    if not isinstance(raw_classes, list):
        raise PolicyError(CLASSES_LIST_ERROR)
    rules = tuple(_rule(item) for item in raw_classes)
    ids = [rule.id for rule in rules]
    # Ascending and unique, but no longer contiguous: #326 retired ids 1 and 7, and forcing
    # contiguity would have renumbered class 4, 5 and 6 out from under the two modules that
    # address them by id. `REQUIRED_CLASSES` is what contiguity used to buy — proof that the
    # rows other code depends on are actually here.
    if not ids or ids[0] < 1 or any(later <= earlier for earlier, later in pairwise(ids)):
        raise PolicyError(CLASS_IDS_ERROR)
    if len({rule.name for rule in rules}) != len(rules):
        raise PolicyError(CLASS_NAMES_ERROR)
    if any(not rule.remedy for rule in rules):
        raise PolicyError(REMEDY_ERROR)
    # Fail closed on the shape that would quietly reinstate the lane bar #326 removed: a
    # seat-bound row with landing prefixes would clear at dispatch for the seat it appoints
    # and then refuse that same route at landing, where no seat is knowable.
    if any(rule.required_seats and rule.landing_path_prefixes for rule in rules):
        raise PolicyError(SEAT_BOUND_LANDING_ERROR)
    if REQUIRED_CLASSES - set(ids):
        raise PolicyError(REQUIRED_CLASSES_ERROR)
    # Validated on parse rather than at each reader, so a policy that emptied the in-world
    # class cannot govern silently: the landing rung would then compute "nothing is
    # in-world" and let every in-world diff through, which is #302's own defect wearing
    # the fix's clothes. The row is present because `REQUIRED_CLASSES` just proved it.
    if not _by_id(rules, IN_WORLD_CLASS_ID).landing_path_prefixes:
        raise PolicyError(IN_WORLD_ERROR)
    return rules


def _check_exception_classes(named: set[int], rules: tuple[Rule, ...]) -> None:
    """Refuse an exception naming a retired class, or one naming a class that binds all."""
    if not named <= {rule.id for rule in rules}:
        raise PolicyError(EXCEPTION_CLASS_ERROR)
    if any(rule.id in named and rule.binds_every_instance for rule in rules):
        raise PolicyError(BINDING_EXCEPTION_ERROR)


def _issue_exceptions(
    document: dict[object, object], rules: tuple[Rule, ...], view: View
) -> tuple[IssueException, ...]:
    found: list[IssueException] = []
    for raw in document.get(view.issue_exceptions, []):
        if not isinstance(raw, dict):
            raise PolicyError(ISSUE_EXCEPTION_ERROR)
        classes = raw.get("classes")
        if not isinstance(classes, list) or not all(isinstance(item, int) for item in classes):
            raise PolicyError(ISSUE_CLASSES_ERROR)
        # Retiring a class in #326 orphaned three of these, and an orphan is worse than an
        # absence: it reads as a live allowance and excepts nothing at all.
        _check_exception_classes(set(classes), rules)
        found.append(IssueException(str(raw["marker"]), tuple(classes)))
    return tuple(found)


def _route_exceptions(
    document: dict[object, object], rules: tuple[Rule, ...], view: View
) -> tuple[RouteException, ...]:
    found: list[RouteException] = []
    for raw in document.get(view.route_exceptions, []):
        if not isinstance(raw, dict):
            raise PolicyError(ROUTE_EXCEPTION_ERROR)
        standing = raw.get("standing") is True
        if standing == ("expires_at" in raw):
            raise PolicyError(STANDING_ERROR)
        _check_exception_classes({int(raw["class"])}, rules)
        found.append(
            RouteException(
                int(raw["class"]),
                str(raw["lane"]),
                str(raw["profile"]),
                str(raw["seat"]),
                None if standing else _timestamp(raw["expires_at"]),
            )
        )
    return tuple(found)


def parse_policy(text: str) -> Policy:
    """Validate enough shape that a partial class table can never govern silently."""
    document = json.loads(text)
    if not isinstance(document, dict) or document.get("version") != 1:
        raise PolicyError(VERSION_ERROR)
    coverage = str(document.get("coverage") or COVERAGE_UNSTATED)
    view = _view(document)
    rules = _rules(document, view)
    return Policy(
        source=str(document["source"]),
        coverage=coverage,
        claude_lane=str(document["claude_lane"]),
        rules=rules,
        issue_exceptions=_issue_exceptions(document, rules, view),
        route_exceptions=_route_exceptions(document, rules, view),
    )


def read_policy(path: Path) -> ReadResult:
    """Read on every call. There is intentionally no module cache or startup load."""
    try:
        return ReadResult(parse_policy(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
        return ReadResult(None, f"{path}: {error}")


def path_matches(path: str, prefix: str) -> bool:
    """Match one diff path against one prefix: a directory prefix, or an exact file."""
    return path.startswith(prefix) if prefix.endswith("/") else path == prefix


def in_world_prefixes(policy: Policy) -> tuple[str, ...]:
    """Return the in-world surfaces, off the one class that carries them.

    `parse_policy` has already proven the row exists and is not empty, so this
    cannot hand back a list that would read as "nothing is in-world". Narrowing class 5
    to a subagent rule in #326 set its `refuses` false and left this untouched: the row
    stops barring routes and goes on being the one authority for the surface list.
    """
    return _by_id(policy.rules, IN_WORLD_CLASS_ID).landing_path_prefixes


def in_world_paths(policy: Policy, paths: Iterable[str]) -> tuple[str, ...]:
    """Name every in-world surface these paths reach, empty when they reach none.

    The filtering half of the one authority. `landing_match` answers the same
    question for the routing gate and this answers it for the corpus rung; both
    read the same row and the same `path_matches`, so they cannot disagree.
    """
    prefixes = in_world_prefixes(policy)
    return tuple(path for path in paths if any(path_matches(path, p) for p in prefixes))


def issue_match(rule: Rule, body: str, seat: str) -> Match | None:
    """Match one data row against the issue's declared surface and kind."""
    evidence: list[str] = []
    if seat in rule.seats:
        evidence.append(f"seat={seat}")
    lowered = body.casefold()
    evidence.extend(
        f"phrase={phrase}" for phrase in rule.issue_phrases if phrase.casefold() in lowered
    )
    evidence.extend(f"path={prefix}" for prefix in rule.issue_path_prefixes if prefix in body)
    return Match(rule, tuple(evidence)) if evidence else None


def landing_match(rule: Rule, paths: tuple[str, ...]) -> Match | None:
    """Match one data row against real diff paths, the enforcing read."""
    evidence = tuple(
        f"path={path}"
        for path in paths
        if any(path_matches(path, prefix) for prefix in rule.landing_path_prefixes)
    )
    return Match(rule, evidence) if evidence else None


def _excepted(policy: Policy, match: Match, body: str, route: Route) -> bool:
    declared = any(
        exception.marker in body and match.rule.id in exception.classes
        for exception in policy.issue_exceptions
    )
    routed = any(
        exception.class_id == match.rule.id
        and (exception.lane, exception.profile, exception.seat)
        == (route.lane, route.profile, route.seat)
        and (exception.expires_at is None or route.now < exception.expires_at)
        for exception in policy.route_exceptions
    )
    return declared or routed


def _refusing_rules(policy: Policy, lane: str) -> tuple[Rule, ...]:
    """Return the rows that can refuse this lane, in table order (#326).

    `refuses` is about the row and comes first: classes 4 and 5 rest on capability and on a
    subagent prohibition, so their remedies are addressed to whoever takes the work rather
    than to the router, and neither bars a route.

    **The Claude-lane exemption is per row, not per policy, and that is claim 2's fix.** A
    row founded on provenance is exempt on the Claude lane, because provenance is what it
    selects on — after #327's second round the live document's one such row is class 6's
    bridge, which #331 owns the retirement of; class 2 was the other until that round
    re-founded it on its seat. A row
    founded on a *seat* is not, because its basis has nothing to do with which provider is
    answering: class 3 refuses an ADR taken by a seat it does not admit on the Claude lane
    exactly as it does on `codex`, and class 2 refuses an orchestration declaration taken by
    a seat outside its route on the Claude lane exactly as it does on `zai`.
    Exempting it by lane was what made the class
    refuse `codex`/`codex-sol-xhigh`/`planner` — the head of the very list its own remedy
    prescribes — while clearing `claude-native` on any seat at all.

    **`binds_every_instance` deliberately does not appear here, and that is the honest
    reading of ADR-0071.** Class 6's conflict of interest — no instance authors the gate
    that judges it — binds Claude too, but the ADR records the class as *aspirational*: the
    invariant it asserts is not enforced, and is discharged by an independent review under
    ruling 4, which no refusal enforces until #331's exemption list lands. Enforcing it
    here instead would refuse every Claude landing that touches a gate, this project's own
    maintenance of its gates included, with no review record yet existing to lift it — a bar
    on all gate work rather than a conflict-of-interest rule. What the field does enforce is
    the half that is enforceable today and is the ADR's own reasoning: a class that binds
    every instance may carry no exception, because an instance that can except itself from
    the gate that judges it is exactly the shape being forbidden.
    """
    claude = lane == policy.claude_lane
    return tuple(
        rule for rule in policy.rules if rule.refuses and (rule.required_seats or not claude)
    )


def _appoints(rule: Rule, seat: str) -> bool:
    """Whether this row appoints seats *and* this is one of them — never vacuously true.

    A row appointing none is not satisfied by every seat, it is simply not about seats, and
    collapsing those two would clear every row for every route.
    """
    return bool(rule.required_seats) and seat in rule.required_seats


def _seat_evidence(rule: Rule, match: Match, route: Route) -> Match:
    """Add the seat and the seats a row wanted, once each, to a seat-bound row's evidence."""
    if not rule.required_seats:
        return match
    appointed = " ".join(rule.required_seats)
    # `issue_match` already appends `seat=` when the row *matches* on the seat, so a
    # future row carrying both `seats` and `required_seats` would otherwise print it
    # twice to the refused reader (review round 2 claim 11). No shipped row does today;
    # the de-duplication is by rule rather than by nobody having written that row yet.
    seat = f"seat={route.seat}"
    evidence = match.evidence if seat in match.evidence else (*match.evidence, seat)
    return Match(rule, (*evidence, f"required_seats={appointed}"))


def advisory_read(policy: Policy, body: str, route: Route) -> Advisory:
    """Walk the declaration once and tell a refusal apart from a lifted match (round 3 claim 2).

    A seat-bound row is skipped for the seats it appoints and refuses every other, which is
    where "route ADR authorship to the `planner` seat" stops being advice in a remedy string
    and becomes the thing the router does. The seat it was given rides on the evidence beside
    the seats it wanted, so the refusal a reader meets states the capability it is about
    rather than leaving them to infer it from the class name.

    `exemption` is the third value round 1 claim 3's rule asks for on this rung: a match a
    live exception lifted is **not** the absence of a match, and reporting both as
    `routing=clear` tells a dispatcher "no class applies" when the truth is "a class applies
    and a standing human allowance lifted it". Both are returned from one walk rather than
    from a second pass, so the two answers cannot be computed by different rules and disagree.
    A refusal wins where a row refuses and an earlier row was excepted: the refusal is the
    consequential half, and the exemption still rides beside it for the reader.
    """
    exemption: Match | None = None
    for rule in _refusing_rules(policy, route.lane):
        if _appoints(rule, route.seat):
            continue
        found = issue_match(rule, body, route.seat)
        if found is None:
            continue
        match = _seat_evidence(rule, found, route)
        if _excepted(policy, match, body, route):
            exemption = exemption or match
            continue
        return Advisory(match, exemption)
    return Advisory(None, exemption)


def advisory_match(policy: Policy, body: str, route: Route) -> Match | None:
    """Return the first non-excepted declaration match that can refuse this route."""
    return advisory_read(policy, body, route).refusal


def classify_issue(policy: Policy, body: str, seat: str) -> Match | None:
    """Return the routing class an issue's declaration puts it in, lane-blind (#323).

    `advisory_match` answers the enforcement question — may this *non-exempt* route
    take this class — and so returns `None` on the Claude lane before it looks. The
    observatory asks a different question: which class an issue belongs to, regardless of
    the lane that took it, so a comparison of profiles is not silently a comparison of
    the router. That needs the same `issue_match` walked without the lane gate.

    No exception filter, on purpose. `_excepted` widens a *route* past a class — a
    standing allowance or a body marker that lifts keep-on-Claude for one dispatch — and
    a route exemption does not reclassify the issue. The class an issue *is* is the first
    row its body declares, the stable signal a stratified comparison wants; the
    enforcement read in `advisory_match` is the one that honours exemptions, and the two
    answer different questions.

    `None` is a third value and not an empty string: a body that declares no class is a
    stratum, and a stratification that could not tell it from "could not look" (#323's
    trap) would bucket both as blank.
    """
    for rule in policy.rules:
        match = issue_match(rule, body, seat)
        if match is not None:
            return match
    return None


def enforcing_match(policy: Policy, paths: tuple[str, ...], lane: str) -> Match | None:
    """Return the first refusing class the actual diff touches for a non-exempt landing.

    **A seat-bound row is skipped here, and the skip is explicit rather than incidental.**
    There is no seat at landing — `just land` runs in a worktree and is handed a lane and a
    diff — so a row whose whole basis is which seat took the work has nothing to test, and
    testing it on the lane instead is the defect #326 was re-founded to remove. `parse_policy`
    already refuses such a row landing prefixes, so this loop would skip it for want of a
    match anyway; the guard is here so a future row carrying both is refused by the rule
    rather than by the accident of an empty list.
    """
    for rule in _refusing_rules(policy, lane):
        if rule.required_seats:
            continue
        match = landing_match(rule, paths)
        if match is not None:
            return match
    return None
