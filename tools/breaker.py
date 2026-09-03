"""`just breaker`: one verdict per lane, read before a dispatch is planned (#226, ADR-0061).

A lane can stop being worth dispatching to for two unrelated reasons, and conflating
them is how a breaker becomes noise. So there are two trip *families*, and the whole
design falls out of the difference between them.

- **Availability.** The lane cannot serve right now. Quota exhaustion is the common
  case, it is foreseeable, and its wait is *computed from a published window boundary,
  never guessed* — ADR-0061 Decision 7's requirement, and the reason `quota_exhausted`
  earned a failure-class row of its own instead of routing to `infra_unavailable`. A
  quota trip auto-resets: at the reset time the circuit goes half-open, one dispatch
  probes it, and an ordinary outcome closes it. Nygard's caveat holds — this is expected
  output, not an incident.
- **Quality.** The lane is serving, and what it serves is wrong: N consecutive gate
  failures, or N consecutive refusals, on one profile. This is the only thing that
  catches a provider swapping the model behind a name with no announcement. It does
  **not** auto-reset, because time does not fix it; it escalates, and clearing it is a
  human act (`just breaker reset --lane L --force`).

There is a third case that looks like the first and must not behave like it: **N
consecutive provider errors** with no published reset. That opens the lane and *holds*
it. Inventing a cooldown there is exactly the defect that disqualified LiteLLM as the
breaker — a five-second reactive damper against five-hour windows — so this module
never invents one. A held lane reopens on evidence rather than on a timer: a fresh
first-party quota reading showing the lane answering, or an explicit reset.

## What is shared with #72

The pure core — `TripRule`, `Circuit`, `advance`, `settle`, `verdict` — knows nothing
about lanes, providers, quota or files. It is a consecutive-N trip policy over a stream
of typed outcome names, which is precisely what #72's first consumer needs: the corpus
loop wants `TripRule("systemic_crash", on={"node_crashed"}, consecutive=2)` and to
abandon the remaining probes when it opens. N lives on the rule, so that consumer picks
its own number without touching this one. #72's *second* consumer, the in-world effect
pump, cannot use it: the pump is SQF running inside the engine, `compileFinal`-ed by the
Functions Library, with no way to reach a Python module — its latch has to be written
again in SQF against the same rule shape.

## Feeds, and what each lane can actually know

| Lane | Source | May trip a lane? |
|---|---|---|
| Claude | `/api/oauth/usage`: active `limits[]` | yes, first-party |
| Codex | `account/rateLimits/read`: `usedPercent`, `resetsAt` | yes, first-party |
| z.ai | `GET /api/monitor/usage/quota/limit`: `percentage`, `nextResetTime` | yes, first-party |

The z.ai endpoint appeared after the original substrate sweep and is re-derived in #275.
Its official usage plugin is the published integration contract; the endpoint is absent
from z.ai's OpenAPI inventory and its response shape has already changed once, so any
unfamiliar or failed response is no evidence and leaves a held lane held. A held z.ai
lane reads it once on the next breaker read. Quota to spare closes an availability trip;
exhaustion may add only the endpoint's own `nextResetTime` boundary.

The z.ai ledger estimator remains deliberately barred from tripping or closing anything.
z.ai meters *prompt counts* and the ledger records *dispatches*; one dispatch is many
prompts, so the estimate is a lower bound in a unit the cap is not denominated in.

The Claude tap asks the first-party endpoint in a detached, single-flight refresh and
prefers the entry the provider marks `is_active`; `just breaker state` preserves its kind
and scope. A 429 schedules the next read at the endpoint's own `retry-after` boundary and
never at a duration invented here. The aggregate status-line pair remains a fallback
when the endpoint cannot answer. The governance weakness remains: the status line lives
in the human's global `~/.claude/settings.json`, which this repository cannot govern,
enforce or test, and status lines run only in interactive sessions. With the tap unwired
the Claude lane is 429-reactive — late, but not blind.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `stall_watch.py` uses to
# reach `pool_merge.py`.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes these importable.
import bounded_request
import otel_event

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

# ---------------------------------------------------------------- the pure core (#72)

CLOSED: Final = "closed"
OPEN: Final = "open"
HALF_OPEN: Final = "half_open"

# The two trip families. Availability is "the lane cannot serve"; quality is "the lane
# serves, and what it serves is wrong". They differ in what may close them, which is why
# this is a field on the rule rather than a name a reader has to recognise.
AVAILABILITY: Final = "availability"
QUALITY: Final = "quality"

# Outcome names. `OK` and `UNCLASSIFIED` are the two the rules never name: an ordinary
# outcome clears every streak, and an outcome nobody could classify moves nothing at
# all. A class we could not read is not evidence in either direction — the #41 shape,
# where a check that could not run was silently treated as a check that passed.
OK: Final = "ok"
UNCLASSIFIED: Final = "unclassified"
QUOTA_EXHAUSTED: Final = "quota_exhausted"
PROVIDER_ERROR: Final = "provider_error"
PROVIDER_REFUSED: Final = "provider_refused"
GATE_FAILED: Final = "gate_failed"

TRANSITION_EVENT: Final = "cti.breaker.transition"


class TripRule(NamedTuple):
    """One consecutive-N trip policy over a set of outcome names.

    `family` is the distinction the whole design turns on — whether this rule is about
    the lane being *able* to serve or about what it serves being *right* — and it is a
    field rather than a name comparison because the two families have different answers
    to "what evidence may close this". `auto_reset` says whether the open state ends at
    a reset time somebody published; nothing here ever invents a cooldown.
    """

    name: str
    on: frozenset[str]
    consecutive: int
    family: str
    auto_reset: bool
    escalates: bool
    failure_class: str
    # None is a pure consecutive count with no clock in it. A window makes N mean
    # "N within this many seconds": events older than the window fall out of the
    # count as they age, so sparse errors never accumulate into a trip.
    window: float | None = None


class Circuit(NamedTuple):
    """What one lane's breaker knows: its state, why, and how far each streak has run."""

    state: str = CLOSED
    rule: str = ""
    reason: str = ""
    opened_at: float = 0.0
    reset_at: float | None = None
    escalated: bool = False
    streaks: tuple[tuple[str, int], ...] = ()
    # Per-rule in-window event times, for rules that carry a `window`. Kept beside
    # `streaks` rather than inside it because a streak is a count and this is evidence.
    windows: tuple[tuple[str, tuple[float, ...]], ...] = ()

    def streak(self, rule: str) -> int:
        """How many consecutive counting outcomes this rule has seen."""
        return dict(self.streaks).get(rule, 0)

    def with_streak(self, rule: str, value: int) -> Circuit:
        """Return this circuit with one rule's streak replaced."""
        counts = dict(self.streaks)
        if value:
            counts[rule] = value
        else:
            counts.pop(rule, None)
        return self._replace(streaks=tuple(sorted(counts.items())))

    def window_times(self, rule: str) -> tuple[float, ...]:
        """Return the counting outcomes for this rule that are still inside its window."""
        return dict(self.windows).get(rule, ())

    def with_window(self, rule: str, times: tuple[float, ...]) -> Circuit:
        """Return this circuit with one rule's in-window event times replaced."""
        kept = dict(self.windows)
        if times:
            kept[rule] = times
        else:
            kept.pop(rule, None)
        return self._replace(windows=tuple(sorted(kept.items())))


class Outcome(NamedTuple):
    """One typed thing that happened on a lane, and what came with it.

    `reset_at` is only ever a boundary a provider published — the type carries it beside
    the outcome precisely so that there is nowhere for a *computed* backoff to enter.
    """

    name: str
    reset_at: float | None = None
    detail: str = ""


class Transition(NamedTuple):
    """One state change, which is the thing OTel is required to carry."""

    at: float
    from_state: str
    to_state: str
    rule: str
    reason: str
    reset_at: float | None
    escalates: bool
    streak: int


class Verdict(NamedTuple):
    """The pre-dispatch read: may this lane be dispatched to, and if not, what to say."""

    lane: str
    conducting: bool
    state: str
    rule: str
    reason: str
    failure_class: str
    reset_at: float | None
    escalates: bool


# The lane rules. N is 3 for both consecutive-N families: two is inside the range one
# bad afternoon produces on a healthy provider, and anything above three spends more of
# a scarce pool learning what the third failure already showed.
CONSECUTIVE_N: Final = 3

QUOTA_RULE: Final = TripRule(
    name="quota",
    on=frozenset({QUOTA_EXHAUSTED}),
    consecutive=1,
    family=AVAILABILITY,
    auto_reset=True,
    escalates=False,
    failure_class=QUOTA_EXHAUSTED,
)
PROVIDER_ERROR_RULE: Final = TripRule(
    # #420's decision, stated: the breaker does hold the lane on repeated 5xx, on this
    # rule rather than a new one. A single 529 is noise — the same brief re-dispatched
    # by hand landed immediately — so one is not enough to trip. Three consecutive
    # provider errors hold the lane whatever the interval between them (ADR-0066
    # Decision 3): no window prunes the count, because a pruning window is a timer
    # this project chose, and one spaced at minutes still leaves a lane that is down
    # reading as healthy. The only sanctioned reset is a classified outcome of another
    # kind — the lane answered, so the streak is not evidence any more.
    # `auto_reset=False` is load-bearing: no 5xx carries a boundary its provider
    # published, and CLAUDE.md forbids a wait this project chose, so the lane reopens
    # on the quota feed's evidence it is serving again, or by a human's hand after the
    # escalation, never on a timer.
    name="provider_errors",
    on=frozenset({PROVIDER_ERROR}),
    consecutive=CONSECUTIVE_N,
    family=AVAILABILITY,
    auto_reset=False,
    escalates=True,
    failure_class="infra_unavailable",
)
QUALITY_RULE: Final = TripRule(
    name="quality",
    on=frozenset({GATE_FAILED, PROVIDER_REFUSED}),
    consecutive=CONSECUTIVE_N,
    family=QUALITY,
    auto_reset=False,
    escalates=True,
    failure_class=PROVIDER_REFUSED,
)

# Order matters only for which rule names an outcome that two could claim; today no
# outcome appears in two rules, and the assertion below keeps it that way.
LANE_RULES: Final[tuple[TripRule, ...]] = (QUOTA_RULE, PROVIDER_ERROR_RULE, QUALITY_RULE)

# The pool's systemic-crash rule is the other consumer of this module's pure
# consecutive-N policy. It is not a lane circuit: the pool has no provider or
# reset state, only an ordered completion stream, so the rule carries the
# threshold and outcome without pretending that a pool is a lane.
CORPUS_CRASH_CLASS: Final = "node_crashed"
CORPUS_CRASH_RULE: Final = TripRule(
    name="systemic_crash",
    on=frozenset({CORPUS_CRASH_CLASS}),
    consecutive=2,
    family="pool",
    auto_reset=False,
    escalates=False,
    failure_class="infra_unavailable",
)


def crash_stop(completions: Iterable[tuple[str, str]]) -> tuple[str, ...] | None:
    """Return the first crash run that reaches the corpus stop threshold.

    Completion order is the pool's only order. A completion after the threshold
    may already be in the record when a competing worker reads it, so keep the
    whole contiguous run for the stop explanation; the first adjacent pair is
    still what makes the decision. A later non-crash ends that run, but cannot
    hide a pair that was already found.
    """
    run: list[str] = []
    tripped = False
    for name, class_ in completions:
        if class_ in CORPUS_CRASH_RULE.on:
            run.append(name)
            if len(run) >= CORPUS_CRASH_RULE.consecutive:
                tripped = True
        elif tripped:
            return tuple(run)
        else:
            run = []
    return tuple(run) if tripped else None


def rule_named(rules: Sequence[TripRule], name: str) -> TripRule | None:
    """Find a rule by name, which is how a stored circuit rejoins its policy."""
    for rule in rules:
        if rule.name == name:
            return rule
    return None


def _closed_by_probe(circuit: Circuit, outcome: Outcome, now: float) -> tuple[Circuit, Transition]:
    """Close a half-open circuit whose probe came back ordinary."""
    return Circuit(), Transition(
        at=now,
        from_state=HALF_OPEN,
        to_state=CLOSED,
        rule=circuit.rule,
        reason=outcome.detail or "the half-open probe came back ordinary",
        reset_at=None,
        escalates=False,
        streak=0,
    )


def _tripped(
    circuit: Circuit,
    moved: Circuit,
    rule: TripRule,
    outcome: Outcome,
    now: float,
) -> tuple[Circuit, Transition | None]:
    """Open a circuit on one rule reaching its N, or say why this trip changes nothing."""
    if circuit.state == OPEN and circuit.escalated and not rule.escalates:
        # An escalated lane is waiting on a human. A trip that auto-resets must not
        # overwrite that record and quietly turn an escalation into a timed wait — the
        # streak still counts, and the escalation still stands.
        return moved, None
    streak = moved.streak(rule.name)
    basis = (
        f"{streak} {outcome.name} within {int(rule.window)}s"
        if rule.window is not None
        else f"{streak} consecutive {outcome.name}"
    )
    opened = Circuit(
        state=OPEN,
        rule=rule.name,
        reason=outcome.detail or basis,
        opened_at=now,
        reset_at=outcome.reset_at if rule.auto_reset else None,
        escalated=rule.escalates,
        streaks=moved.streaks,
        windows=moved.windows,
    )
    already = (
        circuit.state == OPEN and circuit.rule == rule.name and circuit.reset_at == opened.reset_at
    )
    if already:
        return opened, None
    return opened, Transition(
        at=now,
        from_state=circuit.state,
        to_state=OPEN,
        rule=rule.name,
        reason=opened.reason,
        reset_at=opened.reset_at,
        escalates=rule.escalates,
        streak=streak,
    )


def advance(
    circuit: Circuit,
    rules: Sequence[TripRule],
    outcome: Outcome,
    now: float,
) -> tuple[Circuit, Transition | None]:
    """Feed one typed outcome to a circuit. Pure: no clock, no files, no lanes.

    This is the function #72's corpus loop wants. Three behaviours and nothing else:

    - `UNCLASSIFIED` changes nothing at all, streaks and windows included.
    - `OK` clears every streak and window, and closes a half-open circuit — the probe
      worked.
    - anything else advances the streak of every rule that counts it — pruning a
      windowed rule's events that have aged out first — resets the streak and window
      of every rule that does not, and trips the first rule to reach its N.
    """
    if outcome.name == UNCLASSIFIED:
        return circuit, None
    if outcome.name == OK:
        if circuit.state == HALF_OPEN:
            return _closed_by_probe(circuit, outcome, now)
        return circuit._replace(streaks=(), windows=()), None

    moved = circuit
    for rule in rules:
        counts = outcome.name in rule.on
        if counts and rule.window is not None:
            times = tuple(
                when for when in (*moved.window_times(rule.name), now) if when > now - rule.window
            )
            moved = moved.with_window(rule.name, times).with_streak(rule.name, len(times))
        else:
            moved = moved.with_streak(
                rule.name, moved.streak(rule.name) + 1 if counts else 0
            ).with_window(rule.name, ())

    for rule in rules:
        if outcome.name in rule.on and moved.streak(rule.name) >= rule.consecutive:
            return _tripped(circuit, moved, rule, outcome, now)
    return moved, None


def settle(
    circuit: Circuit,
    rules: Sequence[TripRule],
    now: float,
) -> tuple[Circuit, Transition | None]:
    """Move a circuit whose reset time has arrived to half-open. Pure.

    Only an auto-resetting rule has a reset time, and only a published one is ever
    stored, so this is the "computed, never guessed" wait actually elapsing.
    """
    if circuit.state != OPEN or circuit.reset_at is None or now < circuit.reset_at:
        return circuit, None
    rule = rule_named(rules, circuit.rule)
    if rule is None or not rule.auto_reset:  # pragma: no cover — only auto rules store one
        return circuit, None
    half = circuit._replace(state=HALF_OPEN, reason="the published window reset arrived")
    return half, Transition(
        at=now,
        from_state=OPEN,
        to_state=HALF_OPEN,
        rule=circuit.rule,
        reason=half.reason,
        reset_at=circuit.reset_at,
        escalates=False,
        streak=circuit.streak(circuit.rule),
    )


def verdict(lane: str, circuit: Circuit, rules: Sequence[TripRule]) -> Verdict:
    """Say whether this lane may be dispatched to. Pure, and taken on a settled circuit.

    Half-open conducts on purpose: that single dispatch is the probe, and a breaker that
    never let one through would need a human to tell it the window had reset — which is
    the thing the published reset time exists to avoid.
    """
    if circuit.state != OPEN:
        return Verdict(
            lane=lane,
            conducting=True,
            state=circuit.state,
            rule="",
            reason="",
            failure_class="",
            reset_at=None,
            escalates=False,
        )
    rule = rule_named(rules, circuit.rule)
    failure_class = rule.failure_class if rule else "infra_unavailable"
    return Verdict(
        lane=lane,
        conducting=False,
        state=OPEN,
        rule=circuit.rule,
        reason=circuit.reason,
        failure_class=failure_class,
        reset_at=circuit.reset_at,
        escalates=circuit.escalated,
    )


# ------------------------------------------------------------------------ quota feeds

# z.ai's GLM Coding Plan, from the plan documentation: prompt credits on a five-hour
# window and a seven-day window, per tier. Peak is Mon-Fri 14:00-18:00 SGT (UTC+8) and
# off-peak consumption is charged at half. The first-party usage endpoint now supplies
# the live numerator, but not the tier table this estimator needs; #230's
# `prereqs plan-tier` still supplies which row applies.
ZAI_TIERS: Final[dict[str, tuple[int, int]]] = {
    "lite": (2_000, 10_000),
    "pro": (12_000, 60_000),
    "max": (28_000, 140_000),
}
ZAI_PEAK_UTC_OFFSET_HOURS: Final = 8
ZAI_PEAK_START_HOUR: Final = 14
ZAI_PEAK_END_HOUR: Final = 18
ZAI_OFF_PEAK_MULTIPLIER: Final = 0.5

# The published window, in the form a human reads, and the page it was read from. Both
# live beside the constants above because a schedule stated in two places is a schedule
# that can say two things, and #238 makes this one load-bearing: it is no longer only a
# price, it is a dispatch-time refusal.
#
# Verified against the primary source on 2026-08-05 (#238): "Peak hours: Monday to
# Friday, 14:00-18:00 Singapore Standard Time (UTC+8)" and "During off-peak hours, model
# usage is charged at 50% of the standard credit rate". The timezone is unambiguous, and
# Singapore keeps UTC+8 year-round with no daylight saving, so a fixed offset is right
# rather than convenient. Two readings the source does not settle, taken here and flagged
# on #221 rather than guessed silently:
#
#   - **Boundaries are half-open**, [14:00, 18:00). 14:00:00 exactly is peak and 18:00:00
#     exactly is off-peak. The source writes "14:00-18:00" and says nothing about its
#     endpoints; a closed upper bound would make one second of every weekday belong to
#     both bands, which is the only reading that cannot be implemented.
#   - **The weekday is Singapore's**, not UTC's. "Monday to Friday" qualifies hours given
#     in SGT, so the day is read in the same clock as the hours.
ZAI_PEAK_WINDOW: Final = "Mon-Fri 14:00-18:00 SGT (UTC+8)"
ZAI_TERMS_URL: Final = "https://docs.z.ai/devpack/overview"
ZAI_USAGE_URL: Final = "https://api.z.ai/api/monitor/usage/quota/limit"
ZAI_USAGE_SOURCE: Final = "zai_usage"
ZAI_KEY_NAME: Final = "ZAI_API_KEY"
ZAI_USAGE_TIMEOUT_SECS: Final = 10
CLAUDE_USAGE_SOURCE: Final = "claude_usage"
CLAUDE_USAGE_URL: Final = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_USAGE_TIMEOUT_SECS: Final = 10
DEFAULT_CLAUDE_CREDENTIALS: Final = Path.home() / ".claude" / ".credentials.json"
HTTP_OK: Final = 200
HTTP_TOO_MANY_REQUESTS: Final = 429
CREDENTIALS_FILE_MODE: Final = 0o600
MINIMUM_MILLISECOND_EPOCH: Final = 1_000_000_000_000
DEFAULT_CREDENTIALS: Final = Path.home() / ".arma-cti" / "credentials.env"

FIVE_HOURS_SECS: Final = 5 * 3600
SEVEN_DAYS_SECS: Final = 7 * 24 * 3600

FIVE_HOUR: Final = "five_hour"
SEVEN_DAY: Final = "seven_day"

# Where the report starts saying something about an estimate. Below this a lane with an
# advisory-only feed is a lane that is fine, and the report is required to be silent
# about those.
ESTIMATE_ADVISORY_FRACTION: Final = 0.8


class QuotaWindow(NamedTuple):
    """One metering window's state: how much of it is gone, and when it comes back."""

    name: str
    used_fraction: float
    resets_at: float | None

    @property
    def exhausted(self) -> bool:
        """Whether this window has nothing left. Strictly at the cap, never near it."""
        return self.used_fraction >= 1.0


class QuotaReading(NamedTuple):
    """What one feed said about one lane, including its saying that it could not say."""

    lane: str
    source: str
    estimated: bool
    windows: tuple[QuotaWindow, ...]
    unavailable: str
    observed_at: float
    unit: str = "prompts"
    binding: str = ""
    scope: str = ""
    retry_at: float | None = None

    @property
    def available(self) -> bool:
        """Whether this reading carries state at all."""
        return not self.unavailable

    def exhausted_window(self) -> QuotaWindow | None:
        """Name the window that is out, preferring the one that comes back soonest."""
        out = [window for window in self.windows if window.exhausted]
        if not out:
            return None
        return min(out, key=lambda window: (window.resets_at is None, window.resets_at or 0.0))

    def document(self) -> dict[str, object]:
        """Render the reading for the store."""
        return {
            "lane": self.lane,
            "source": self.source,
            "estimated": self.estimated,
            "unavailable": self.unavailable,
            "observed_at": self.observed_at,
            "unit": self.unit,
            "binding": self.binding,
            "scope": self.scope,
            "retry_at": self.retry_at,
            "windows": [
                {"name": w.name, "used_fraction": w.used_fraction, "resets_at": w.resets_at}
                for w in self.windows
            ],
        }


def reading_from_document(document: Mapping[str, object]) -> QuotaReading:
    """Read a stored reading back."""
    windows = tuple(
        QuotaWindow(
            name=str(entry.get("name", "")),
            used_fraction=float(entry.get("used_fraction", 0.0) or 0.0),
            resets_at=None if entry.get("resets_at") is None else float(entry["resets_at"]),
        )
        for entry in document.get("windows", [])  # type: ignore[union-attr]
        if isinstance(entry, dict)
    )
    return QuotaReading(
        lane=str(document.get("lane", "")),
        source=str(document.get("source", "")),
        estimated=bool(document.get("estimated", False)),
        windows=windows,
        unavailable=str(document.get("unavailable", "")),
        observed_at=float(document.get("observed_at", 0.0) or 0.0),
        unit=str(document.get("unit", "prompts")),
        binding=str(document.get("binding", "")),
        scope=str(document.get("scope", "")),
        retry_at=None if document.get("retry_at") is None else float(document["retry_at"]),
    )


def as_epoch(value: object) -> float | None:
    """Read a reset time that a provider may spell as an epoch or as ISO-8601.

    Tolerant on purpose. The Codex field is documented as a Unix timestamp; the status
    line's is not documented as either, and a feed whose timestamp we misread would
    produce a *guessed* wait wearing a computed one's clothes. Anything unreadable
    becomes "no reset time", which the refusal then says out loud.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _window_from_status_line(name: str, block: object) -> QuotaWindow | None:
    """Read one `rate_limits.<window>` block, which is independently optional."""
    if not isinstance(block, dict):
        return None
    used = block.get("used_percentage")
    if not isinstance(used, (int, float)) or isinstance(used, bool):
        return None
    return QuotaWindow(
        name=name, used_fraction=float(used) / 100.0, resets_at=as_epoch(block.get("resets_at"))
    )


def _scope_name(value: object) -> str:
    """Render the provider's binding scope without discarding what kind of scope it is."""
    if not isinstance(value, dict):
        return "all"
    parts: list[str] = []
    model = value.get("model")
    if isinstance(model, dict):
        name = model.get("display_name") or model.get("id")
        if isinstance(name, str) and name:
            parts.append(f"model:{name}")
    surface = value.get("surface")
    if isinstance(surface, str) and surface:
        parts.append(f"surface:{surface}")
    return ",".join(parts) or "all"


def _active_claude_limit(payload: Mapping[str, object]) -> tuple[QuotaWindow, str] | None:
    """Read the one entry the provider marks active, preserving its published scope."""
    limits = payload.get("limits")
    if not isinstance(limits, list):
        return None
    for item in limits:
        if not isinstance(item, dict) or item.get("is_active") is not True:
            continue
        kind = item.get("kind")
        percent = item.get("percent")
        if (
            not isinstance(kind, str)
            or not kind
            or not isinstance(percent, (int, float))
            or isinstance(percent, bool)
        ):
            return None
        return (
            QuotaWindow(
                name=kind,
                used_fraction=float(percent) / 100.0,
                resets_at=as_epoch(item.get("resets_at")),
            ),
            _scope_name(item.get("scope")),
        )
    return None


def reading_from_claude_usage(payload: Mapping[str, object], lane: str, now: float) -> QuotaReading:
    """Read `/api/oauth/usage`, selecting the limit the provider marks as binding."""
    active = _active_claude_limit(payload)
    if active is None:
        return QuotaReading(
            lane=lane,
            source=CLAUDE_USAGE_SOURCE,
            estimated=False,
            windows=(),
            unavailable="active_limit_absent",
            observed_at=now,
        )
    window, scope = active
    return QuotaReading(
        lane=lane,
        source=CLAUDE_USAGE_SOURCE,
        estimated=False,
        windows=(window,),
        unavailable="",
        observed_at=now,
        binding=window.name,
        scope=scope,
    )


def _unavailable_claude_reading(
    lane: str, now: float, reason: str, retry_at: float | None = None
) -> QuotaReading:
    """Return a typed endpoint absence, including only a provider-published retry boundary."""
    return QuotaReading(
        lane=lane,
        source=CLAUDE_USAGE_SOURCE,
        estimated=False,
        windows=(),
        unavailable=reason,
        observed_at=now,
        retry_at=retry_at,
    )


def _claude_oauth_token(path: Path) -> tuple[str, str]:
    """Read Claude Code's OAuth token without ever putting it in output or on argv."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", "credentials_unreadable"
    oauth = document.get("claudeAiOauth") if isinstance(document, dict) else None
    token = oauth.get("accessToken") if isinstance(oauth, dict) else None
    if not isinstance(token, str) or not token:
        return "", "credential_absent"
    return token, ""


def _retry_after_epoch(value: object, now: float) -> float | None:
    """Turn the observed delta-seconds form into its boundary, never a fallback delay."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return now + seconds if seconds > 0 else None


def query_claude_usage(
    credentials: Path,
    now: float,
    lane: str = "claude-native",
) -> QuotaReading:
    """Query Claude's first-party usage endpoint once; Retry-After schedules the next read."""
    token, unavailable = _claude_oauth_token(credentials)
    if unavailable:
        return _unavailable_claude_reading(lane, now, unavailable)
    request = urllib.request.Request(
        CLAUDE_USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
        },
    )
    try:
        status, body = bounded_request.read(request, CLAUDE_USAGE_TIMEOUT_SECS)
        if status != HTTP_OK:
            return _unavailable_claude_reading(lane, now, f"http_{status}")
        payload = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as error:
        retry_at = (
            _retry_after_epoch(error.headers.get("retry-after"), now)
            if error.code == HTTP_TOO_MANY_REQUESTS and error.headers is not None
            else None
        )
        reason = (
            "http_429_retry_after_unreadable"
            if error.code == HTTP_TOO_MANY_REQUESTS and retry_at is None
            else f"http_{error.code}"
        )
        return _unavailable_claude_reading(lane, now, reason, retry_at)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _unavailable_claude_reading(lane, now, "request_failed")
    if not isinstance(payload, dict):
        return _unavailable_claude_reading(lane, now, "document_not_object")
    return reading_from_claude_usage(payload, lane, now)


def reading_from_status_line(payload: Mapping[str, object], lane: str, now: float) -> QuotaReading:
    """Read Claude Code's status-line stdin document.

    `rate_limits` appears on Pro/Max only and only after the first API response of a
    session, and each of the two windows is independently optional. Every one of those
    absences is the same typed state — the feed said nothing — never a zero.
    """
    active = _active_claude_limit(payload)
    if active is not None:
        window, scope = active
        return QuotaReading(
            lane=lane,
            source="status_line",
            estimated=False,
            windows=(window,),
            unavailable="",
            observed_at=now,
            binding=window.name,
            scope=scope,
        )

    limits = payload.get("rate_limits")
    if not isinstance(limits, dict):
        return QuotaReading(
            lane=lane,
            source="status_line",
            estimated=False,
            windows=(),
            unavailable="rate_limits_absent",
            observed_at=now,
        )
    windows = tuple(
        window
        for window in (
            _window_from_status_line(FIVE_HOUR, limits.get("five_hour")),
            _window_from_status_line(SEVEN_DAY, limits.get("seven_day")),
        )
        if window is not None
    )
    if not windows:
        return QuotaReading(
            lane=lane,
            source="status_line",
            estimated=False,
            windows=(),
            unavailable="rate_limits_empty",
            observed_at=now,
        )
    return QuotaReading(
        lane=lane,
        source="status_line",
        estimated=False,
        windows=windows,
        unavailable="",
        observed_at=now,
    )


def reading_from_codex_rate_limits(
    payload: Mapping[str, object],
    lane: str,
    now: float,
) -> QuotaReading:
    """Read `account/rateLimits/read`, accepting either the bare result or a JSON-RPC envelope.

    `rateLimitReachedType` is the provider's own statement that a limit has been reached,
    and it outranks the percentages: a backend that says it is out is out, whatever
    `usedPercent` last read.
    """
    body = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    limits = body.get("rateLimits") if isinstance(body, dict) else None
    if not isinstance(limits, dict):
        return QuotaReading(
            lane=lane,
            source="codex_rate_limits",
            estimated=False,
            windows=(),
            unavailable="rate_limits_absent",
            observed_at=now,
        )
    reached = limits.get("rateLimitReachedType")
    windows: list[QuotaWindow] = []
    for name in ("primary", "secondary"):
        block = limits.get(name)
        if not isinstance(block, dict):
            continue
        used = block.get("usedPercent")
        if not isinstance(used, (int, float)) or isinstance(used, bool):
            continue
        fraction = float(used) / 100.0
        if isinstance(reached, str) and reached.strip() and reached == name:
            fraction = max(fraction, 1.0)
        windows.append(
            QuotaWindow(
                name=name, used_fraction=fraction, resets_at=as_epoch(block.get("resetsAt"))
            )
        )
    if not windows:
        return QuotaReading(
            lane=lane,
            source="codex_rate_limits",
            estimated=False,
            windows=(),
            unavailable="rate_limits_empty",
            observed_at=now,
        )
    if isinstance(reached, str) and reached.strip() and reached not in ("primary", "secondary"):
        # The backend named a limit state we do not map to a window. Treat the soonest
        # window as reached rather than dropping the provider's own word for it.
        soonest = min(windows, key=lambda w: (w.resets_at is None, w.resets_at or 0.0))
        windows = [
            w._replace(used_fraction=max(w.used_fraction, 1.0)) if w is soonest else w
            for w in windows
        ]
    return QuotaReading(
        lane=lane,
        source="codex_rate_limits",
        estimated=False,
        windows=tuple(windows),
        unavailable="",
        observed_at=now,
    )


def _unavailable_zai_reading(lane: str, now: float, reason: str) -> QuotaReading:
    """Return a typed absence; an unreadable feed is never evidence either way."""
    return QuotaReading(
        lane=lane,
        source=ZAI_USAGE_SOURCE,
        estimated=False,
        windows=(),
        unavailable=reason,
        observed_at=now,
    )


def _future_epoch_milliseconds(value: object, now: float) -> float | None:
    """Read z.ai's observed epoch-millisecond boundary, refusing any other unit."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        milliseconds = float(value)
    except ValueError:
        return None
    epoch = milliseconds / 1000.0
    return epoch if milliseconds >= MINIMUM_MILLISECOND_EPOCH and epoch > now else None


def reading_from_zai_usage(payload: Mapping[str, object], lane: str, now: float) -> QuotaReading:
    """Read z.ai's first-party Coding Plan usage response.

    The official plugin is the integration contract, but its parser knows an older
    `TOKENS_LIMIT` shape while the live endpoint returned `CREDIT_LIMIT` on 2026-08-07.
    Both are accepted narrowly. Unknown limit types and fields remain unknown rather
    than being mapped to a window this project invented.
    """
    data = payload.get("data")
    limits = data.get("limits") if isinstance(data, dict) else None
    if not isinstance(limits, list):
        return _unavailable_zai_reading(lane, now, "limits_absent")

    windows: list[QuotaWindow] = []
    for item in limits:
        if not isinstance(item, dict) or item.get("type") not in {"CREDIT_LIMIT", "TOKENS_LIMIT"}:
            continue
        percentage = item.get("percentage")
        if not isinstance(percentage, (int, float)) or isinstance(percentage, bool):
            continue
        fraction = float(percentage) / 100.0
        if not 0.0 <= fraction <= 1.0:
            continue
        limit_type = str(item["type"]).lower()
        number = str(item.get("number", "unknown"))
        unit = str(item.get("unit", "unknown"))
        windows.append(
            QuotaWindow(
                name=f"{limit_type}_{number}_{unit}",
                used_fraction=fraction,
                resets_at=_future_epoch_milliseconds(item.get("nextResetTime"), now),
            )
        )
    if not windows:
        return _unavailable_zai_reading(lane, now, "limits_empty")
    return QuotaReading(
        lane=lane,
        source=ZAI_USAGE_SOURCE,
        estimated=False,
        windows=tuple(windows),
        unavailable="",
        observed_at=now,
    )


def _credential(path: Path, name: str) -> tuple[str, str]:
    """Read one named secret as data, only from the repository's required 0600 file."""
    try:
        if stat.S_IMODE(path.stat().st_mode) != CREDENTIALS_FILE_MODE:
            return "", "credentials_mode"
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "", "credentials_unreadable"
    for raw in lines:
        line = raw.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            token = value.strip().strip("'\"")
            return (token, "") if token else ("", "credential_absent")
    return "", "credential_absent"


def _read_zai_quota_response(
    request: urllib.request.Request, lane: str, now: float
) -> QuotaReading:
    """Translate the first-party response or its absence into one typed reading."""
    try:
        status, body = bounded_request.read(request, ZAI_USAGE_TIMEOUT_SECS)
        if status != HTTP_OK:
            return _unavailable_zai_reading(lane, now, f"http_{status}")
        payload = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as error:
        return _unavailable_zai_reading(lane, now, f"http_{error.code}")
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _unavailable_zai_reading(lane, now, "request_failed")
    if not isinstance(payload, dict):
        return _unavailable_zai_reading(lane, now, "document_not_object")
    return reading_from_zai_usage(payload, lane, now)


def query_first_party_quota(lane: str, credentials: Path, now: float) -> QuotaReading:
    """Query the first-party quota source once, with no retry and no model prompt."""
    if lane != "zai":
        return _unavailable_zai_reading(lane, now, "feed_absent")
    token, unavailable = _credential(credentials, ZAI_KEY_NAME)
    if unavailable:
        return _unavailable_zai_reading(lane, now, unavailable)
    request = urllib.request.Request(
        ZAI_USAGE_URL,
        headers={
            "Authorization": token,
            "Accept-Language": "en-US,en",
            "Content-Type": "application/json",
        },
    )
    return _read_zai_quota_response(request, lane, now)


def zai_is_peak(at: float) -> bool:
    """Whether a moment falls in z.ai's peak band: Mon-Fri 14:00-18:00 SGT."""
    local = datetime.fromtimestamp(at, tz=UTC) + timedelta(hours=ZAI_PEAK_UTC_OFFSET_HOURS)
    weekday_max = 5  # Monday is 0; Saturday is 5
    if local.weekday() >= weekday_max:
        return False
    return ZAI_PEAK_START_HOUR <= local.hour < ZAI_PEAK_END_HOUR


def zai_off_peak_opens_at(at: float) -> float:
    """When the off-peak band next begins, for a moment that is inside the peak band.

    Peak is one contiguous run of hours that always ends at 18:00 SGT on the day it
    started, so the answer is that day's own upper boundary — computed from the constants
    `zai_is_peak` reads, never from a second copy of the schedule. A moment already
    off-peak answers itself: the band is open now, and there is nothing to wait for.
    """
    if not zai_is_peak(at):
        return at
    # `local` carries SGT wall-clock time in a UTC-labelled datetime, which is what makes
    # `.hour` the right hour; shifting back before reading the epoch is what makes the
    # answer the right instant.
    local = datetime.fromtimestamp(at, tz=UTC) + timedelta(hours=ZAI_PEAK_UTC_OFFSET_HOURS)
    end = local.replace(hour=ZAI_PEAK_END_HOUR, minute=0, second=0, microsecond=0)
    return (end - timedelta(hours=ZAI_PEAK_UTC_OFFSET_HOURS)).timestamp()


class Schedule(NamedTuple):
    """A provider's published time-of-day band: who is in it, when it lifts, what it costs.

    One of these is the whole of what a lane's published plan says about the clock, so
    that everything reading a window — the dispatcher's price record, the dispatcher's
    off-peak refusal, and this module's own state print — reads the same one.
    """

    name: str
    meter: str
    is_peak: Callable[[float], bool]
    opens_at: Callable[[float], float]
    off_peak_multiplier: float
    window: str
    source: str


# Which published schedule prices which lane. `tools/dispatch.py` reads this rather than
# restating any of it: the lane registry there owns the lane's *wiring* and this repo's
# own policy, and a provider's published plan terms are owned here.
LANE_SCHEDULES: Final[dict[str, Schedule]] = {
    "zai": Schedule(
        name="zai-off-peak",
        meter="prompts",
        is_peak=zai_is_peak,
        opens_at=zai_off_peak_opens_at,
        off_peak_multiplier=ZAI_OFF_PEAK_MULTIPLIER,
        window=ZAI_PEAK_WINDOW,
        source=ZAI_TERMS_URL,
    ),
}


def _estimate_window(
    name: str, events: Sequence[float], now: float, span: float, cap: int
) -> QuotaWindow:
    """Charge the events inside one rolling window and say when the window turns over."""
    inside = [at for at in events if now - span <= at <= now]
    charged = sum(1.0 if zai_is_peak(at) else ZAI_OFF_PEAK_MULTIPLIER for at in inside)
    resets_at = min(inside) + span if inside else None
    return QuotaWindow(name=name, used_fraction=charged / cap if cap else 0.0, resets_at=resets_at)


def estimate_zai(events: Sequence[float], tier: str, now: float, lane: str = "zai") -> QuotaReading:
    """Estimate z.ai consumption from our own dispatch ledger. Advisory, never a trip.

    Two honest weaknesses, both carried in the reading itself rather than smoothed over:
    the caps are denominated in *prompt counts* and the ledger records *dispatches*, one
    of which is many prompts, so this is a lower bound in the wrong unit; and the tier
    has no machine-readable source, so an unknown tier is a typed state — the estimate
    is unavailable and says which recipe supplies the missing fact — never a guess at
    which plan the human bought.
    """
    caps = ZAI_TIERS.get(tier.strip().lower())
    if caps is None:
        return QuotaReading(
            lane=lane,
            source="ledger_estimate",
            estimated=True,
            windows=(),
            unavailable="plan_tier_unknown",
            observed_at=now,
            unit="dispatches",
        )
    five_hour_cap, seven_day_cap = caps
    windows = (
        _estimate_window(FIVE_HOUR, events, now, FIVE_HOURS_SECS, five_hour_cap),
        _estimate_window(SEVEN_DAY, events, now, SEVEN_DAYS_SECS, seven_day_cap),
    )
    return QuotaReading(
        lane=lane,
        source="ledger_estimate",
        estimated=True,
        windows=windows,
        unavailable="",
        observed_at=now,
        unit="dispatches",
    )


def apply_reading(
    circuit: Circuit,
    rules: Sequence[TripRule],
    reading: QuotaReading,
    now: float,
) -> tuple[Circuit, Transition | None]:
    """Let a first-party quota reading move the breaker. Pure.

    An estimate moves nothing, for the reason in the module docstring. A first-party
    reading does two things. An exhausted window is a `quota_exhausted` outcome carrying
    the published reset. A healthy one is evidence the lane both answers and has quota,
    which closes an availability trip — including the held one, whose rule has no timer
    and for which this is the only evidence short of a human it will ever get.

    A **quality** trip is deliberately immune to this. The provider having quota says
    nothing about whether what it returns is right, and letting a quota document clear a
    quality trip would make the one trip that catches a silent model swap self-healing.
    """
    if reading.estimated or not reading.available:
        return circuit, None
    out = reading.exhausted_window()
    if out is not None:
        exhausted = Outcome(
            QUOTA_EXHAUSTED,
            reset_at=out.resets_at,
            detail=f"{reading.source} reports the {out.name} window at or over its cap",
        )
        return advance(circuit, rules, exhausted, now)
    rule = rule_named(rules, circuit.rule)
    if circuit.state != OPEN or rule is None or rule.family == QUALITY:
        return circuit, None
    return Circuit(), Transition(
        at=now,
        from_state=OPEN,
        to_state=CLOSED,
        rule=circuit.rule,
        reason=f"{reading.source} answered with quota to spare, so the lane is serving",
        reset_at=None,
        escalates=False,
        streak=0,
    )


# ------------------------------------------------------------- classifying a lane's run

# What a dispatched runner's own output says happened. Deliberately narrow: an output
# this cannot place becomes `UNCLASSIFIED`, which moves nothing. Guessing a class from
# unfamiliar text would put a wrong class in the failure-class table, and CLAUDE.md
# makes a wrong class a harness bug by definition.
QUOTA_MARKERS: Final = (
    "usage limit reached",
    # Codex's own phrasing for the same wall — #489's live quota death ended on
    # exactly this sentence and no marker above caught it.
    "hit your usage limit",
    "rate limit exceeded",
    "quota exceeded",
    "insufficient quota",
    "out of credits",
)
PROVIDER_ERROR_MARKERS: Final = (
    "connection refused",
    "connection reset",
    "could not connect",
    "internal server error",
    # #420: the overload body `API Error: 529 [1305][The service may be temporarily
    # overloaded, please try again later]` matched none of the markers above and read
    # `unclassified` — a provider-side overload counted against the lane's work. The
    # code and the body phrase are both pinned so the mapping is not re-derived from a
    # log the next time z.ai has a bad ten minutes.
    "temporarily overloaded",
    "bad gateway",
    "service unavailable",
    "network error",
    "timed out",
)
# A status code the provider's own endpoint returned is *typed by what the status means*
# rather than left `unclassified` or collapsed into one class (#696's owner ruling on the
# original criterion, which had demanded the 529 be a refusal too). One decision site:
# the pattern parses the one explicit status the terminal line carries — anchored to the
# line's start, because `API Error: 404` is a provider shape only where a provider would
# have said it, and the child's own terminal failure quoting that shape (`FAILED ...
# expected "API Error: 404"`) is the child's work, not the provider's. Everything a
# bare-number search used to claim is decided from that parsed value instead, so a
# digit run inside an identifier (`resp_a429b`) can never outrank the status on the
# same line — round five's collision, where the two searches disagreed and the search
# that ran first won. The two prefixes are the only shapes observed, both from #696's
# two lanes (`ERROR: unexpected status 404 Not Found` from Codex; Claude Code's
# `API Error: <code>`, whose 529 shape the marker list also carries as free text).
# Checked *after* both marker lists on purpose, so a line the free text already types
# keeps that class; a 429 or a 5xx with none reaches the parse and is typed the same
# way here. An unanchored shape elsewhere on the line, a bare status code in the
# child's own output (a test count, a line number), a longer digit run where a status
# would sit, and a status outside the bands below all read `unclassified`, where
# somebody investigates. Every list above reads only the run's *terminal* line — see
# `_terminal_line` — so a provider-shaped line the run survived never types a failure
# the provider did not cause. Parsing the run's own output stays the mechanism rather
# than a per-adapter typed result: the runners are external binaries whose log is the
# only channel a headless dispatch has, so an adapter result would parse this same
# prose one layer earlier and add a surface for it (#696).
PROVIDER_STATUS_PATTERN: Final = re.compile(
    r"(?:error:\s*)?(?:unexpected status|api error):?\s+(?<!\d)(\d{3})(?!\d)"
)
# The bands that place a parsed status, named for the HTTP class each covers. Both
# close at each edge, so a code outside either — a 3xx redirect, a 600 — fits the
# shape but no band and stays `unclassified`; the lookarounds above refuse a longer
# digit run outright rather than reading its first three digits as a code.
CLIENT_ERROR_STATUS_RANGE: Final = range(400, 500)
QUOTA_STATUS: Final = 429
PROVIDER_ERROR_STATUS_RANGE: Final = range(500, 600)
# The client errors that are *not* refusals. 401 and 403 are the auth family: the
# token, not the request, is what failed, so the class is the availability one —
# ADR-0061 sends OAuth expiry to `infra_unavailable` unchanged, and the `provider_error`
# outcome is that family's outcome here (its rule's `failure_class` is
# `infra_unavailable`, and the ledger types it the same). Counting an expired token as
# a refusal would trip the quality rule — the family whose clearing is a human act —
# for a failure a re-auth fixes, on a lane that was serving fine. 402 is the account
# out of credit with no published boundary in the status alone; the quota family's wait
# is computed from a published window, so without one it is ADR-0066 Decision 3's
# unknowable case — held, never given an invented wait. 408 is the provider declaring
# the request timed out, the same transient the free-text `timed out` marker carries.
# Every other client error is the provider answering and refusing the request — the
# `provider_refused` row of AGENTS.md's table, not a result, re-dispatch elsewhere, a
# streak the quality rule counts; while a 5xx stays `provider_error`, a transient
# ordinary load produces repeatedly and never a refusal, because counting those would
# hold `claude-native` through a busy hour on a rule only a human clears.
NON_REFUSAL_CLIENT_STATUSES: Final = frozenset({401, 402, 403, 408})
# Claude Code prints its subscription limit as `Claude AI usage limit reached|<epoch>`,
# which is a published reset boundary arriving on the only channel a headless run has.
LIMIT_EPOCH_SEPARATOR: Final = "usage limit reached|"


def _terminal_line(output: str) -> str:
    """Return the last non-empty line of a run's output, lowercased for matching.

    The provider failure that killed a run is the last thing the run said; anything the
    child printed *after* a provider-shaped line means the run survived that line, so it
    is not the failure. Matching the whole tail instead let one `API Error: 404` inside
    the child's own failure output — or a non-terminal provider warning — take a
    child-owned failure over and read as a refusal nobody investigated (#696's round
    four). What follows a run's last word is unwritten, so a trailing empty line is
    skipped and an output of nothing classifies as nothing.
    """
    for line in reversed(output.splitlines()):
        if line.strip():
            return line.lower()
    return ""


def _status_outcome(code: int) -> str:
    """Place one parsed provider status in its class, per the bands and exceptions above.

    The one decision site the round-five refactor exists for: every status-based class
    is decided from the parsed value alone, so nothing else on the line — an identifier
    carrying a status-shaped digit run, most of all — can outrank it.
    """
    if code == QUOTA_STATUS:
        return QUOTA_EXHAUSTED
    if code in NON_REFUSAL_CLIENT_STATUSES or code in PROVIDER_ERROR_STATUS_RANGE:
        return PROVIDER_ERROR
    if code in CLIENT_ERROR_STATUS_RANGE:
        return PROVIDER_REFUSED
    return UNCLASSIFIED


def classify_run(returncode: int, output: str) -> tuple[str, float | None]:
    """Read a finished dispatch's exit code and output into an outcome and a reset time.

    Returns `(outcome, reset_at)`. This is the 429-reactive path the issue names as the
    degraded fallback: with no quota tap wired, this is how a lane's exhaustion is
    learned at all — late, because it costs a dispatch to find out, but not blind.

    Only the run's terminal line is classified (`_terminal_line`): a provider failure is
    the provider's death of the run, so a provider-shaped line anywhere earlier is a
    warning the run survived, and the child's own last word keeps its classification.
    A status the provider returned is parsed once, from an anchored provider shape, and
    every status-based class is decided from that one parsed value (`_status_outcome`).
    """
    if returncode == 0:
        return OK, None
    text = _terminal_line(output)
    if any(marker in text for marker in QUOTA_MARKERS):
        return QUOTA_EXHAUSTED, _limit_epoch(text)
    if any(marker in text for marker in PROVIDER_ERROR_MARKERS):
        return PROVIDER_ERROR, None
    match = PROVIDER_STATUS_PATTERN.match(text)
    if match is None:
        return UNCLASSIFIED, None
    code = int(match.group(1))
    return _status_outcome(code), (_limit_epoch(text) if code == QUOTA_STATUS else None)


def _limit_epoch(text: str) -> float | None:
    """Pull the reset epoch out of a `usage limit reached|<epoch>` line, if there is one."""
    index = text.find(LIMIT_EPOCH_SEPARATOR)
    if index < 0:
        return None
    tail = text[index + len(LIMIT_EPOCH_SEPARATOR) :]
    digits = ""
    for character in tail:
        if not character.isdigit():
            break
        digits += character
    return float(digits) if digits else None


# ------------------------------------------------------------------------- the store

# Outside every worktree, beside the tier's own evidence, for `stall_watch.py`'s reason:
# a lane's breaker state must outlive the worktree and the session that tripped it.
DEFAULT_BREAKER_DIR: Final = Path.home() / ".arma-cti" / "breaker"
DEFAULT_DISPATCH_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"

TRANSITION_JOURNAL: Final = "transitions.jsonl"

# The lanes this reports on. Kept here rather than imported from `tools/dispatch.py`
# because the breaker is read *by* the dispatcher, and a cycle between the two would
# make either one unloadable on its own.
KNOWN_LANES: Final[tuple[str, ...]] = ("claude-native", "zai")


class LaneState(NamedTuple):
    """One lane's persisted state: its circuit, and the last thing a feed said."""

    lane: str
    circuit: Circuit
    reading: QuotaReading | None
    updated_at: float

    def document(self) -> dict[str, object]:
        """Render the whole lane state for its file."""
        return {
            "lane": self.lane,
            "updated_at": self.updated_at,
            "circuit": {
                "state": self.circuit.state,
                "rule": self.circuit.rule,
                "reason": self.circuit.reason,
                "opened_at": self.circuit.opened_at,
                "reset_at": self.circuit.reset_at,
                "escalated": self.circuit.escalated,
                "streaks": dict(self.circuit.streaks),
                "windows": {rule: list(times) for rule, times in self.circuit.windows},
            },
            "quota": None if self.reading is None else self.reading.document(),
        }


def state_path(breaker_dir: Path, lane: str) -> Path:
    """Where one lane keeps its breaker state."""
    return breaker_dir / f"{lane}.json"


def read_state(breaker_dir: Path, lane: str) -> LaneState:
    """Read a lane's state, treating absent and unreadable alike as a fresh closed lane.

    A breaker with no file has never tripped, which is a closed circuit; a breaker whose
    file will not parse has lost its history, and the safe reading of lost history is
    not "refuse every dispatch forever" — the trip that mattered will happen again on
    the next N outcomes.
    """
    path = state_path(breaker_dir, lane)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LaneState(lane, Circuit(), None, 0.0)
    if not isinstance(document, dict):
        return LaneState(lane, Circuit(), None, 0.0)
    block = document.get("circuit")
    circuit = Circuit()
    if isinstance(block, dict):
        streaks = block.get("streaks")
        windows = block.get("windows", {})
        circuit = Circuit(
            state=str(block.get("state", CLOSED)),
            rule=str(block.get("rule", "")),
            reason=str(block.get("reason", "")),
            opened_at=float(block.get("opened_at", 0.0) or 0.0),
            reset_at=None if block.get("reset_at") is None else float(block["reset_at"]),
            escalated=bool(block.get("escalated", False)),
            streaks=tuple(sorted((str(k), int(v)) for k, v in streaks.items()))
            if isinstance(streaks, dict)
            else (),
            # A state file written before the window existed carries none, which is the
            # safe reading: no recorded times means no in-window evidence.
            windows=tuple(
                sorted(
                    (str(k), tuple(float(t) for t in times))
                    for k, times in windows.items()
                    if isinstance(times, list)
                )
            )
            if isinstance(windows, dict)
            else (),
        )
    quota = document.get("quota")
    reading = reading_from_document(quota) if isinstance(quota, dict) else None
    return LaneState(lane, circuit, reading, float(document.get("updated_at", 0.0) or 0.0))


def write_state(breaker_dir: Path, state: LaneState) -> None:
    """Write a lane's state, replacing the file rather than editing it in place."""
    breaker_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(breaker_dir, state.lane)
    scratch = path.with_suffix(".json.tmp")
    scratch.write_text(json.dumps(state.document(), indent=2) + "\n", encoding="utf-8")
    scratch.replace(path)


class Store(NamedTuple):
    """Where the breakers live, which policy they run, and where transitions are sent.

    Bundled rather than passed as three parameters everywhere because they only ever
    vary together: a test points all three somewhere temporary, and the recipe points
    all three at the box's real ones.
    """

    directory: Path = DEFAULT_BREAKER_DIR
    rules: Sequence[TripRule] = LANE_RULES
    endpoint: str = ""
    quota_reader: Callable[[str, Path, float], QuotaReading] = query_first_party_quota
    credentials: Path = DEFAULT_CREDENTIALS
    claude_reader: Callable[[Path, float, str], QuotaReading] = query_claude_usage
    claude_credentials: Path = DEFAULT_CLAUDE_CREDENTIALS

    @property
    def journal(self) -> Path:
        """Where every transition is written, whether or not the collector took it."""
        return self.directory / TRANSITION_JOURNAL


def emit_transition(store: Store, lane: str, transition: Transition) -> bool:
    """Put one transition in OTel and in the journal beside the lane's state."""
    return otel_event.emit(
        otel_event.Event(
            name=TRANSITION_EVENT,
            at=transition.at,
            attributes={
                "cti.lane": lane,
                "cti.breaker.from": transition.from_state,
                "cti.breaker.to": transition.to_state,
                "cti.breaker.rule": transition.rule,
                "cti.breaker.reason": transition.reason,
                "cti.breaker.streak": transition.streak,
                "cti.breaker.escalates": transition.escalates,
                "cti.breaker.reset_at": "" if transition.reset_at is None else transition.reset_at,
            },
            resource={"service.name": "arma-cti-breaker", "cti.lane": lane},
        ),
        journal=store.journal,
        endpoint=store.endpoint,
    )


def _read_lane(store: Store, lane: str, now: float) -> tuple[Verdict, Transition | None]:
    """Settle time and refresh a held z.ai lane from first-party evidence once.

    Settling here rather than at the moment of trip is what makes "state read before
    dispatch" sufficient — nothing has to be running for a window reset to take effect,
    because the next reader is the one that notices it.

    A z.ai availability trip with no boundary is the other self-healing case. The read
    asks the provider's quota endpoint once. The clock decides only when this observation
    is made; only the response may move the circuit.
    """
    state = read_state(store.directory, lane)
    settled, transition = settle(state.circuit, store.rules, now)
    if transition is not None:
        write_state(store.directory, state._replace(circuit=settled, updated_at=now))
        emit_transition(store, lane, transition)
    rule = rule_named(store.rules, settled.rule)
    held_availability = (
        lane == "zai"
        and settled.state == OPEN
        and settled.reset_at is None
        and rule is not None
        and rule.family == AVAILABILITY
    )
    if not held_availability:
        return verdict(lane, settled, store.rules), transition

    reading = store.quota_reader(lane, store.credentials, now)
    moved, evidence = apply_reading(settled, store.rules, reading, now)
    write_state(store.directory, LaneState(lane, moved, reading, now))
    if evidence is not None:
        emit_transition(store, lane, evidence)
    return verdict(lane, moved, store.rules), evidence


def lane_verdict(store: Store, lane: str, now: float) -> Verdict:
    """Take the pre-dispatch read, including any first-party recovery evidence."""
    result, _ = _read_lane(store, lane, now)
    return result


def record_outcome(
    store: Store,
    lane: str,
    outcome: Outcome,
    now: float,
) -> tuple[Circuit, Transition | None]:
    """Feed one outcome to a lane's breaker, persist it, and emit any transition."""
    state = read_state(store.directory, lane)
    settled, elapsed = settle(state.circuit, store.rules, now)
    if elapsed is not None:
        emit_transition(store, lane, elapsed)
    moved, transition = advance(settled, store.rules, outcome, now)
    if moved != state.circuit or elapsed is not None:
        write_state(store.directory, state._replace(circuit=moved, updated_at=now))
    if transition is not None:
        emit_transition(store, lane, transition)
    return moved, transition


def record_reading(
    store: Store,
    lane: str,
    reading: QuotaReading,
    now: float,
) -> tuple[Circuit, Transition | None]:
    """Store what a feed said and let it move the breaker if it is first-party."""
    state = read_state(store.directory, lane)
    settled, elapsed = settle(state.circuit, store.rules, now)
    if elapsed is not None:
        emit_transition(store, lane, elapsed)
    moved, transition = apply_reading(settled, store.rules, reading, now)
    write_state(store.directory, LaneState(lane, moved, reading, now))
    if transition is not None:
        emit_transition(store, lane, transition)
    return moved, transition


def refresh_claude_usage(
    store: Store,
    lane: str,
    now: float,
    fallback: Mapping[str, object] | None = None,
) -> QuotaReading:
    """Refresh the endpoint feed unless its last 429 says the boundary has not arrived."""
    previous = read_state(store.directory, lane).reading
    if previous is not None and previous.retry_at is not None and now < previous.retry_at:
        return previous

    reading = store.claude_reader(store.claude_credentials, now, lane)
    if reading.retry_at is not None and previous is not None and previous.windows:
        reading = reading._replace(
            windows=previous.windows,
            binding=previous.binding,
            scope=previous.scope,
        )
    elif not reading.available and fallback is not None:
        aggregate = reading_from_status_line(fallback, lane, now)
        if aggregate.available:
            reading = aggregate._replace(retry_at=reading.retry_at)
    record_reading(store, lane, reading, now)
    return reading


def clear_lane(store: Store, lane: str, now: float) -> Transition | None:
    """Close a lane by hand. This is what a quality trip's escalation is resolved by."""
    state = read_state(store.directory, lane)
    if state.circuit.state == CLOSED:
        return None
    transition = Transition(
        at=now,
        from_state=state.circuit.state,
        to_state=CLOSED,
        rule=state.circuit.rule,
        reason="cleared by hand",
        reset_at=None,
        escalates=False,
        streak=0,
    )
    write_state(store.directory, state._replace(circuit=Circuit(), updated_at=now))
    emit_transition(store, lane, transition)
    return transition


# ------------------------------------------------------------------------ the ledger


def zai_dispatch_events(dispatch_root: Path, lane: str = "zai") -> tuple[float, ...]:
    """Read the dispatch ledger for one lane's timestamps, newest last.

    `dispatch.json`'s `planned_at` is the moment the dispatch was armed, which is the
    closest thing the ledger has to when the provider was billed.
    """
    events: list[float] = []
    if not dispatch_root.is_dir():
        return ()
    for record in sorted(dispatch_root.glob("*/dispatch.json")):
        try:
            document = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict) or document.get("lane") != lane:
            continue
        at = as_epoch(document.get("planned_at"))
        if at is not None:
            events.append(at)
    return tuple(sorted(events))


# ------------------------------------------------------------------- rendering a line


def human_delta(seconds: float) -> str:
    """Render a wait the way an orchestrator reads it: `48m`, `3h 10m`, `now`."""
    remaining = int(seconds)
    if remaining <= 0:
        return "now"
    hours, minutes = divmod(remaining // 60, 60)
    if hours and minutes:
        return f"{hours}h {minutes:02d}m"
    if hours:
        return f"{hours}h"
    return f"{max(minutes, 1)}m"


def iso(at: float) -> str:
    """Render an epoch as the timestamp this project writes everywhere else."""
    return datetime.fromtimestamp(at, tz=UTC).isoformat()


def verdict_line(result: Verdict, now: float) -> str:
    """One line, for a lane that is not conducting. Never printed for a lane that is.

    A verdict, not three percentages: #209's rule is that where a rule-table already
    decides, an agent is not handed numbers to reason about. The words `open` and
    `closed` are deliberately absent from this line — they mean opposite things to an
    electrician and to a shopkeeper, and the orchestrator only needs the imperative.
    """
    parts = [
        f"lane={result.lane}",
        "dispatch=refused",
        f"class={result.failure_class}",
        f"rule={result.rule}",
    ]
    if result.reset_at is not None:
        parts.append(f"until={iso(result.reset_at)}")
        parts.append(f"in={human_delta(result.reset_at - now)}")
    else:
        parts.append("until=unknown")
    if result.escalates:
        parts.append("escalate=true")
        parts.append(f"clear=`just breaker reset --lane {result.lane} --force`")
    elif result.reset_at is None:
        if result.lane == "zai":
            parts.append("reason=quota_feed_unavailable")
            parts.append(f"evidence=`GET {ZAI_USAGE_URL}`")
        else:
            parts.append("reason=no_quota_feed")
            parts.append("degraded=reacting-to-429s")
            parts.append("wire=`just prereqs statusline`")
    parts.append(f"why={result.reason}")
    return " ".join(parts)


def advisory_line(reading: QuotaReading, now: float) -> str:
    """One line for an estimate worth knowing about, always labelled as an estimate."""
    window = max(reading.windows, key=lambda w: w.used_fraction)
    parts = [
        f"lane={reading.lane}",
        "dispatch=allowed",
        "quota=estimated",
        f"window={window.name}",
        f"used~={window.used_fraction * 100:.0f}%",
        f"unit={reading.unit}",
        f"source={reading.source}",
    ]
    if window.resets_at is not None:
        parts.append(f"window_reset={human_delta(window.resets_at - now)}")
    parts.append("note=a-dispatch-is-many-prompts-so-this-under-counts")
    return " ".join(parts)


def reopened_line(lane: str, transition: Transition, reading: QuotaReading) -> str:
    """Make an evidence-driven reopen visible in the same one-line verdict form."""
    return " ".join(
        (
            f"lane={lane}",
            "dispatch=allowed",
            "reopened=evidence",
            f"source={reading.source}",
            f"why={transition.reason}",
        )
    )


def report_lines(
    store: Store,
    now: float,
    lanes: Iterable[str] = KNOWN_LANES,
) -> tuple[str, ...]:
    """Render one verdict line per lane that needs one, and nothing for a lane that is fine."""
    lines: list[str] = []
    for lane in lanes:
        result, transition = _read_lane(store, lane, now)
        state = read_state(store.directory, lane)
        if (
            transition is not None
            and transition.from_state == OPEN
            and transition.to_state == CLOSED
            and state.reading is not None
        ):
            lines.append(reopened_line(lane, transition, state.reading))
            continue
        if not result.conducting:
            lines.append(verdict_line(result, now))
            continue
        reading = state.reading
        if reading is None or not reading.available or not reading.estimated:
            continue
        if any(w.used_fraction >= ESTIMATE_ADVISORY_FRACTION for w in reading.windows):
            lines.append(advisory_line(reading, now))
    return tuple(lines)


def _feed_parts(reading: QuotaReading | None, now: float) -> list[str]:
    """Say what this lane's feed is, including its being absent or unable to answer."""
    if reading is None:
        return ["feed=absent", "degraded=reacting-to-429s"]
    if not reading.available:
        fix = (
            "fix=`just prereqs plan-tier`"
            if reading.unavailable == "plan_tier_unknown"
            else "degraded=reacting-to-429s"
        )
        return [
            f"feed={reading.source}:{reading.unavailable}",
            fix,
            *([f"binding={reading.binding}"] if reading.binding else []),
            *([f"scope={reading.scope}"] if reading.scope else []),
            *([f"next_poll={iso(reading.retry_at)}"] if reading.retry_at is not None else []),
        ]
    return [
        f"feed={reading.source}",
        f"estimated={str(reading.estimated).lower()}",
        f"age={human_delta(now - reading.observed_at)}",
        *([f"binding={reading.binding}"] if reading.binding else []),
        *([f"scope={reading.scope}"] if reading.scope else []),
        *([f"next_poll={iso(reading.retry_at)}"] if reading.retry_at is not None else []),
        *(f"{window.name}={window.used_fraction * 100:.0f}%" for window in reading.windows),
    ]


def _window_parts(lane: str, now: float) -> list[str]:
    """State a lane's published time-of-day band, and when it next opens if it is shut.

    The breaker is the wrong home for #238's off-peak rule — this module trips on
    failures, and an off-peak refusal is policy rather than a failure — but a dispatcher
    refused by that rule reads this print next, so the window it was refused against is
    stated here. `dispatch=allowed` above therefore never means "and z.ai will take it";
    it means this breaker has nothing against the lane.
    """
    schedule = LANE_SCHEDULES.get(lane)
    if schedule is None:
        return []
    peak = schedule.is_peak(now)
    parts = [f"window={schedule.window}", f"band={'peak' if peak else 'off-peak'}"]
    if peak:
        opens = schedule.opens_at(now)
        parts.append(f"opens={iso(opens)}")
        parts.append(f"in={human_delta(opens - now)}")
    return parts


def state_lines(store: Store, now: float, lanes: Iterable[str] = KNOWN_LANES) -> tuple[str, ...]:
    """Render the full picture: the lanes that are fine, their streaks, and absent feeds.

    This is where the degradation is always stated. `just breaker report` is required to
    be silent about a healthy lane, so a lane whose feed has never delivered anything is
    named here instead, where somebody asked.
    """
    lines: list[str] = []
    for lane in lanes:
        result, transition = _read_lane(store, lane, now)
        state = read_state(store.directory, lane)
        settled = state.circuit
        parts = [
            f"lane={lane}",
            f"state={settled.state}",
            "dispatch=allowed" if result.conducting else "dispatch=refused",
        ]
        if (
            transition is not None
            and transition.from_state == OPEN
            and transition.to_state == CLOSED
            and state.reading is not None
        ):
            parts.extend(("reopened=evidence", f"source={state.reading.source}"))
        if not result.conducting:
            parts.append(f"class={result.failure_class}")
            parts.append(f"until={iso(result.reset_at)}" if result.reset_at else "until=unknown")
        parts.extend(
            f"streak.{rule.name}={settled.streak(rule.name)}/{rule.consecutive}"
            for rule in store.rules
        )
        parts.extend(_feed_parts(state.reading, now))
        parts.extend(_window_parts(lane, now))
        lines.append(" ".join(parts))
    return tuple(lines)


# ------------------------------------------------------------------------------- CLI


def emit_lines(lines: Iterable[str], code: int = 0) -> int:
    """Print to the stream the exit code implies, and return it."""
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Eight verbs: read a lane, read them all, feed one, and the status-line tap."""
    parser = argparse.ArgumentParser(prog="breaker", description=__doc__)
    # `CTI_BREAKER_DIR` lets a caller that cannot pass a flag — `just watch-report`,
    # which folds this in without forwarding its own arguments — point the read at a
    # different set of lanes, and lets a test exercise the recipe without writing to the
    # box's real breakers.
    parser.add_argument(
        "--breaker-dir",
        type=Path,
        default=Path(os.environ.get("CTI_BREAKER_DIR", str(DEFAULT_BREAKER_DIR))),
    )
    parser.add_argument("--dispatch-dir", type=Path, default=DEFAULT_DISPATCH_ROOT)
    parser.add_argument("--otlp-endpoint", default="")
    parser.add_argument("--now", type=float, default=0.0)
    verbs = parser.add_subparsers(dest="verb", required=True)

    verbs.add_parser("report", help="one verdict line per lane that needs one")
    verbs.add_parser("state", help="every lane, including the ones that are fine")

    check = verbs.add_parser("check", help="the pre-dispatch read for one lane")
    check.add_argument("--lane", required=True)

    record = verbs.add_parser("record", help="feed one typed outcome to a lane")
    record.add_argument("--lane", required=True)
    record.add_argument(
        "--outcome",
        required=True,
        choices=(OK, QUOTA_EXHAUSTED, PROVIDER_ERROR, PROVIDER_REFUSED, GATE_FAILED, UNCLASSIFIED),
    )
    record.add_argument("--reset-at", default="", help="a published reset; never a guess")
    record.add_argument("--detail", default="")

    quota = verbs.add_parser("quota", help="ingest a provider's own quota document")
    quota.add_argument("--lane", required=True)
    quota.add_argument(
        "--format",
        required=True,
        choices=("status-line", "codex-rate-limits", "zai-usage"),
    )
    quota.add_argument("--from-file", default="", help="default: stdin")

    estimate = verbs.add_parser("estimate", help="z.ai's ledger estimate, advisory only")
    estimate.add_argument("--lane", default="zai")
    estimate.add_argument("--tier", default=os.environ.get("CTI_ZAI_PLAN_TIER", ""))

    tap = verbs.add_parser("tap", help="status-line filter: read the quota, pass the line through")
    tap.add_argument("--lane", default="claude-native")
    tap.add_argument("--chain", default="", help="the status line this one sits in front of")
    tap.add_argument(
        "--oauth-usage",
        action="store_true",
        help="refresh /api/oauth/usage instead of reading the aggregate status-line pair",
    )
    tap.add_argument(
        "--oauth-credentials",
        type=Path,
        default=DEFAULT_CLAUDE_CREDENTIALS,
    )

    reset = verbs.add_parser("reset", help="close a lane by hand")
    reset.add_argument("--lane", required=True)
    reset.add_argument("--force", action="store_true", required=True)
    return parser.parse_args(argv)


def _now(args: argparse.Namespace) -> float:
    """Read the moment to reason about: the caller's, or the clock's."""
    return args.now or time.time()


def _store(args: argparse.Namespace) -> Store:
    """Bind the verb to the breakers it reads and the collector it reports to."""
    return Store(directory=args.breaker_dir, rules=LANE_RULES, endpoint=args.otlp_endpoint)


def run_report(args: argparse.Namespace) -> int:
    """Print the verdicts, and nothing when every lane is fine."""
    now = _now(args)
    return emit_lines(report_lines(_store(args), now))


def run_state(args: argparse.Namespace) -> int:
    """Print every lane's state, feeds and streaks included."""
    return emit_lines(state_lines(_store(args), _now(args)))


def run_check(args: argparse.Namespace) -> int:
    """Take the pre-dispatch read, as an exit code plus the line a caller quotes."""
    now = _now(args)
    result = lane_verdict(_store(args), args.lane, now)
    if result.conducting:
        return emit_lines((f"lane={result.lane}", "dispatch=allowed", f"state={result.state}"))
    return emit_lines((verdict_line(result, now),), 1)


def run_record(args: argparse.Namespace) -> int:
    """Feed one outcome and say what it did."""
    now = _now(args)
    outcome = Outcome(
        args.outcome,
        reset_at=as_epoch(args.reset_at) if args.reset_at else None,
        detail=args.detail,
    )
    circuit, transition = record_outcome(_store(args), args.lane, outcome, now)
    lines = [f"lane={args.lane}", f"outcome={args.outcome}", f"state={circuit.state}"]
    if transition is not None:
        lines.append(f"transition={transition.from_state}->{transition.to_state}")
        lines.append(f"rule={transition.rule}")
    return emit_lines(lines)


def _read_payload(path: str) -> Mapping[str, object]:
    text = Path(path).expanduser().read_text(encoding="utf-8") if path else sys.stdin.read()
    document = json.loads(text)
    return document if isinstance(document, dict) else {}


def run_quota(args: argparse.Namespace) -> int:
    """Ingest one provider quota document, from a file or from stdin."""
    now = _now(args)
    try:
        payload = _read_payload(args.from_file)
    except (OSError, json.JSONDecodeError) as error:
        return emit_lines((f"lane={args.lane}", f"quota=unreadable ({error})"), 1)
    parsers = {
        "status-line": reading_from_status_line,
        "codex-rate-limits": reading_from_codex_rate_limits,
        "zai-usage": reading_from_zai_usage,
    }
    parse = parsers[args.format]
    reading = parse(payload, args.lane, now)
    circuit, transition = record_reading(_store(args), args.lane, reading, now)
    lines = [f"lane={args.lane}", f"source={reading.source}", f"state={circuit.state}"]
    if not reading.available:
        lines.append(f"quota=unavailable:{reading.unavailable}")
    else:
        lines.extend(f"{w.name}={w.used_fraction * 100:.0f}%" for w in reading.windows)
    if transition is not None:
        lines.append(f"transition={transition.from_state}->{transition.to_state}")
    return emit_lines(lines)


def run_estimate(args: argparse.Namespace) -> int:
    """Compute and store the z.ai estimate. Advisory: it never moves the breaker."""
    now = _now(args)
    events = zai_dispatch_events(args.dispatch_dir, args.lane)
    reading = estimate_zai(events, args.tier, now, args.lane)
    record_reading(_store(args), args.lane, reading, now)
    lines = [f"lane={args.lane}", f"dispatches={len(events)}", "estimated=true"]
    if not reading.available:
        lines.append(f"quota=unavailable:{reading.unavailable}")
        if reading.unavailable == "plan_tier_unknown":
            lines.append("fix=`just prereqs plan-tier`")
        return emit_lines(lines, 1)
    lines.append(f"tier={args.tier.strip().lower()}")
    lines.extend(f"{w.name}~={w.used_fraction * 100:.0f}%" for w in reading.windows)
    lines.append(f"unit={reading.unit}")
    return emit_lines(lines)


def run_tap(args: argparse.Namespace) -> int:
    """Sit in front of the human's status line: read the quota out, pass the line through.

    Two rules, both absolute. It never alters the chained command's output, because the
    status line belongs to the human and this is a tap rather than a replacement. And it
    never fails: an exception here would break a status line on every render, which is a
    far worse outcome than a breaker that missed one reading — so the whole ingest is
    wrapped and the pass-through happens regardless.
    """
    payload = sys.stdin.read()
    try:
        now = _now(args)
        document = json.loads(payload)
        fallback = document if isinstance(document, dict) else None
        if args.oauth_usage:
            store = _store(args)._replace(claude_credentials=args.oauth_credentials)
            refresh_claude_usage(
                store,
                args.lane,
                now,
                fallback=fallback,
            )
        elif fallback is not None:
            reading = reading_from_status_line(fallback, args.lane, now)
            record_reading(_store(args), args.lane, reading, now)
    except Exception:  # noqa: BLE001, S110 — a tap must never break the human's status line
        pass
    if not args.chain:
        return 0
    # S602: the chained command is the human's own status line as they configured it in
    # their settings, which is a shell command line by Claude Code's contract.
    done = subprocess.run(  # noqa: S602
        args.chain,
        shell=True,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    return done.returncode


def run_reset(args: argparse.Namespace) -> int:
    """Clear a lane by hand, which is how a quality trip's escalation ends."""
    transition = clear_lane(_store(args), args.lane, _now(args))
    if transition is None:
        return emit_lines((f"lane={args.lane}", "state=closed", "cleared=nothing"))
    return emit_lines(
        (f"lane={args.lane}", "state=closed", f"cleared={transition.from_state}:{transition.rule}")
    )


def main(argv: list[str] | None = None) -> int:
    """Dispatch the verb; every one is a read, a small file write, or the tap."""
    args = parse_args(argv)
    verbs = {
        "report": run_report,
        "state": run_state,
        "check": run_check,
        "record": run_record,
        "quota": run_quota,
        "estimate": run_estimate,
        "tap": run_tap,
        "reset": run_reset,
    }
    return verbs[args.verb](args)


if __name__ == "__main__":
    sys.exit(main())
