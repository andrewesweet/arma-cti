"""Keep-on-Claude routing classes, read for every dispatch and landing (#266).

An issue body only declares the expected surface, so dispatch is an advisory read even
though a match refuses. Landing reads the real diff and is the enforcing gate. This is
separate from queue policy: queue state decides whether work may start now; this file
decides whether a class may leave Claude under ADR-0061 and #258.

Since #302 the document carries a second job. Class 5's `landing_path_prefixes` is the
**one authority** for what an in-world surface is: `just land`'s corpus rung, the
admission cross-check in `tools/admission.py` and the gate prediction in `tools/brief.py`
all read it from here rather than each holding a list. It lives in data rather than in
Python because `just land` reads it out of fetched `origin/main` — a candidate diff must
not be able to widen the list that judges it — and because three copies of a path list
rot, which is what #302 was filed about.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterable

POLICY_RELATIVE: Final = Path("config/dispatch-routing-policy.json")

# The class that carries the in-world surfaces. Looked up by **id**, because the id table
# is already validated as the ordered 1..7 below and is therefore the stable handle; the
# name is what the row is called today and is asserted against the id in
# `tests/unit/test_corpus_gate.py` rather than relied on here.
IN_WORLD_CLASS_ID: Final = 5
IN_WORLD_CLASS: Final = "in_world_landings"


class Route(NamedTuple):
    """The lane/profile/seat triple at one policy clock instant."""

    lane: str
    profile: str
    seat: str
    now: datetime


class Rule(NamedTuple):
    """One class; its matching remains data rather than a branch per class."""

    id: int
    name: str
    label: str
    issue_path_prefixes: tuple[str, ...]
    issue_phrases: tuple[str, ...]
    seats: tuple[str, ...]
    landing_path_prefixes: tuple[str, ...]
    remedy: str


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
    """The complete validated policy document."""

    source: str
    claude_lane: str
    rules: tuple[Rule, ...]
    issue_exceptions: tuple[IssueException, ...]
    route_exceptions: tuple[RouteException, ...]


class Match(NamedTuple):
    """One matching row and the data that matched it."""

    rule: Rule
    evidence: tuple[str, ...]


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
CLASS_IDS_ERROR: Final = "classes must be the ordered table 1..7"
CLASS_NAMES_ERROR: Final = "class names must be unique"
IN_WORLD_ERROR: Final = (
    f"class {IN_WORLD_CLASS_ID} must carry landing_path_prefixes — it is the one authority"
    " for what an in-world surface is, and three readers depend on it (#302)"
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
    )


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise PolicyError(TIMEZONE_ERROR)
    return parsed


def _rules(document: dict[object, object]) -> tuple[Rule, ...]:
    raw_classes = document.get("classes")
    if not isinstance(raw_classes, list):
        raise PolicyError(CLASSES_LIST_ERROR)
    rules = tuple(_rule(item) for item in raw_classes)
    if tuple(rule.id for rule in rules) != tuple(range(1, 8)):
        raise PolicyError(CLASS_IDS_ERROR)
    if len({rule.name for rule in rules}) != len(rules):
        raise PolicyError(CLASS_NAMES_ERROR)
    if any(not rule.remedy for rule in rules):
        raise PolicyError(REMEDY_ERROR)
    # Validated on parse rather than at each reader, so a policy that emptied the in-world
    # class cannot govern silently: the landing rung would then compute "nothing is
    # in-world" and let every in-world diff through, which is #302's own defect wearing
    # the fix's clothes. The index is safe because the ids were just proven to be 1..7.
    if not rules[IN_WORLD_CLASS_ID - 1].landing_path_prefixes:
        raise PolicyError(IN_WORLD_ERROR)
    return rules


def _issue_exceptions(document: dict[object, object]) -> tuple[IssueException, ...]:
    found: list[IssueException] = []
    for raw in document.get("issue_exceptions", []):
        if not isinstance(raw, dict):
            raise PolicyError(ISSUE_EXCEPTION_ERROR)
        classes = raw.get("classes")
        if not isinstance(classes, list) or not all(isinstance(item, int) for item in classes):
            raise PolicyError(ISSUE_CLASSES_ERROR)
        found.append(IssueException(str(raw["marker"]), tuple(classes)))
    return tuple(found)


def _route_exceptions(document: dict[object, object]) -> tuple[RouteException, ...]:
    found: list[RouteException] = []
    for raw in document.get("route_exceptions", []):
        if not isinstance(raw, dict):
            raise PolicyError(ROUTE_EXCEPTION_ERROR)
        standing = raw.get("standing") is True
        if standing == ("expires_at" in raw):
            raise PolicyError(STANDING_ERROR)
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
    return Policy(
        source=str(document["source"]),
        claude_lane=str(document["claude_lane"]),
        rules=_rules(document),
        issue_exceptions=_issue_exceptions(document),
        route_exceptions=_route_exceptions(document),
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
    cannot hand back a list that would read as "nothing is in-world".
    """
    return policy.rules[IN_WORLD_CLASS_ID - 1].landing_path_prefixes


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


def advisory_match(policy: Policy, body: str, route: Route) -> Match | None:
    """Return the first non-excepted declaration match for a foreign route."""
    if route.lane == policy.claude_lane:
        return None
    for rule in policy.rules:
        match = issue_match(rule, body, route.seat)
        if match is not None and not _excepted(policy, match, body, route):
            return match
    return None


def classify_issue(policy: Policy, body: str, seat: str) -> Match | None:
    """Return the routing class an issue's declaration puts it in, lane-blind (#323).

    `advisory_match` answers the enforcement question — may this *foreign* route take
    this class — and so returns `None` on the Claude lane before it looks. The
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
    """Return the first class the actual diff touches for a foreign landing."""
    if lane == policy.claude_lane:
        return None
    for rule in policy.rules:
        match = landing_match(rule, paths)
        if match is not None:
            return match
    return None
