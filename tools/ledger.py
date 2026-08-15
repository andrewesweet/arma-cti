"""`just ledger-sync`: the per-dispatch ledger, a materialised view over the OTel bus (#227).

ADR-0061's telemetry ruling makes OTel the single capture bus for every lane, and its
durability ruling makes the ledger a **materialised view** over that bus rather than a
second writer. Everything here follows from those two sentences:

- **One writer, and it is not this file.** The collector writes the records. This reads
  them and materialises a row per dispatch under `~/.arma-cti/dispatches/<id>/`, beside
  the plan and brief `just dispatch` already left there. Nothing here appends to a
  telemetry file, and nothing here invents a record that the bus did not carry: a
  dispatch with no records gets a row saying so, never a row filled in from the plan.
- **Two sources, and the row always names which one it read.** Once the human has run
  the generated root script (#230), the collector exports every record carrying
  `cti.dispatch_id` to a non-rotating, `group_by`-split file per dispatch under
  `/var/log/claude-otel/dispatches/`, and that file is the preferred source: durable,
  already filtered, already keyed. Until then the only source is the rotating capture at
  `/var/log/claude-otel/claude-telemetry.jsonl`, which carries the same records — the
  live `metrics` and `logs` pipelines are unfiltered, so a dispatch's `cti.*` resource
  block reaches it too — but rotates at 50 MB × 5 and so **loses records without
  saying so**. Reading it is therefore a *degradation*, and it is typed and loud: the
  row carries `degraded: true`, every printed line carries `source=`, and a dispatch
  with no records read from a degraded source is typed `unknown`, never
  `infra_unavailable`, because an absent record there says nothing about the dispatch.
  With neither source present the sync itself refuses `infra_unavailable` — a view whose
  bus it cannot reach is not a view that found nothing.
- **Content logging stays off, and this file is written so that turning it on would not
  leak through the view.** The row carries counts, token and cost numbers, and evidence
  built from an allowlist of non-free-text attribute keys. No record body, no attribute
  value outside that allowlist, ever reaches `ledger.json` — so a capture that one day
  carried prompt text would still not put it in the ledger.
- **The row's spend column is fraction-of-cap, and the currency figure is not spend.**
  ADR-0061 Decision 1 optimises Claude spend, and on a subscription with no bill the
  quantity that means "how close is this to the wall we hit" is percentage points of a
  plan window, never dollars. `claude_code.cost.usage` reproduces API list pricing
  exactly — #218 recovered the whole rate card from it, and it modelled $849.76 for a run
  that moved the plan meter zero — so it survives here only under the name
  `usage.list_price_usd`, and nothing ranks decisions on it. `cap_fraction` is the
  ledgerable number, per #220's §6: see the plan-currency section below.

Three readings the view performs, none of which the bus can do for itself:

**Cross-lane normalisation.** Three lanes carry the same fact three ways: Claude Code as
`claude_code.token.usage` metric datapoints keyed by a `type` attribute, opencode as AI
SDK spans carrying `gen_ai.usage.*` (and its own `ai.usage.*` copy of the same numbers on
the same span, which is why the reader takes the first key per bucket and not the sum of
both), Codex as a `codex.turn.token_usage` metric. The reader is rename-tolerant across
the `gen_ai` vintages because the lanes disagree about which one they emit, and it
respects each metric's own `aggregationTemporality` — delta sums, cumulative takes the
series maximum — because summing a cumulative counter would over-count by its own
history. A metric or attribute whose shape it does not recognise is reported in
`unclassified`, never silently dropped.

**End-state typing**, in ADR-0061's vocabulary, from provider records only:
`provider_refused` from a refusal event, `quota_exhausted` from a rate-limited provider
error, `infra_unavailable` from a dispatch that never reached a provider at all. The
window a `quota_exhausted` lane waits for, and the breaker state that follows from it,
are #226's ground and are deliberately not computed here — the view reports a `reset_at`
only where a record carried one, verbatim.

**The join** to issue, gate outcome and landed SHA. The issue comes from the dispatch
record. The landed SHA is git's answer, bounded so that the answer is about *this*
dispatch: the newest commit on `origin/main` that references the issue, descends from the
dispatch's base SHA, and was committed after the dispatch's own start. Both bounds are
load-bearing and neither was there at first — a review dispatch armed at 22:17Z was
credited with a commit made at 21:01Z, because the range was `base_sha..origin/main` and
nothing else, and on a review dispatch `base_sha` is the *reviewed* commit and so reaches
arbitrarily far back (#245). Seats that land nothing by construction — `review`, `recon`
— are not asked the question at all; their rows say the seat lands nothing, which is a
fact about ADR-0061 Decision 3 rather than a weak reading of git. Gate outcome is derived
from that landing rather than from the child's exit code, and the reason is that the exit
code of a coding agent is not a gate result — the gates run *inside* the dispatched
process, and `result.json` is deliberately facts-only (#223). What is mechanical is that a
commit on `origin/main` cleared `cog verify` and the repo hooks, and that CLAUDE.md's
contract binds landing to a green `just fast`. So `landed` is the gate evidence and the
SHA is where to look; a green gate run that never landed is invisible here, which is
stated rather than papered over.

**Retention.** The materialised rows are kept indefinitely — they are the evidence quoted
into an issue months later, and they are a few kilobytes each. The raw per-dispatch export
grows without bound by construction, so `prune` deletes raw files older than
`RETENTION_DAYS` **and only once a row materialised from that same durable file exists**.
A raw file with no row, or a row read from the degraded source, is never deleted: pruning
the bus ahead of the view would destroy the only copy. `prune` reports and deletes nothing
without `--apply`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path, as `timeline.py` does.
sys.path.insert(0, str(Path(__file__).parent))

from telemetry_log import rows

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

EXIT_REFUSED: Final = 1

SCHEMA: Final = "cti.ledger/2"

DISPATCH_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"
LEDGER_EXPORT: Final = Path("/var/log/claude-otel/dispatches")
ROTATING_CAPTURE: Final = Path("/var/log/claude-otel/claude-telemetry.jsonl")

# The retention horizon for the raw per-dispatch export, in days. The materialised rows
# have no horizon; see the module docstring and docs/telemetry-ledger.md.
RETENTION_DAYS: Final = 30

SECONDS_PER_DAY: Final = 86400

SOURCE_EXPORT: Final = "ledger_export"
SOURCE_CAPTURE: Final = "rotating_capture"
SOURCE_ABSENT: Final = "absent"

# OTLP's own temporality enum: 1 is DELTA, 2 is CUMULATIVE.
TEMPORALITY_CUMULATIVE: Final = 2

STOP_NOT_A_RESULT: Final = (
    "Stop. A view that cannot reach its bus found nothing about nothing "
    "(CLAUDE.md's failure-class table, infra_unavailable)."
)

# The only attribute keys whose *values* may be copied into a row. Content logging is
# off, and the way it would come back on through the ledger is a view that copied
# whatever a record happened to carry. Every key here holds a code, a category or a
# timestamp — never free text, and never anything a model wrote.
EVIDENCE_KEYS: Final = ("status_code", "refusal_category", "reset_at", "model", "error_type")

# Claude Code's `type` attribute on `claude_code.token.usage`, and the spellings the
# other two lanes might use for the same buckets. An unrecognised value is reported.
TOKEN_BUCKETS: Final = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cacheRead": "cache_read_tokens",
    "cache_read": "cache_read_tokens",
    # Codex's spellings for the same two cache halves (#243). Note it reports the write
    # half, which z.ai does not — a zero here from the Codex lane is a measurement, where
    # the same zero from the z.ai lane is a silence (#225).
    "cached_input": "cache_read_tokens",
    "cacheCreation": "cache_creation_tokens",
    "cache_creation": "cache_creation_tokens",
    "cache_write_input": "cache_creation_tokens",
}

# Token types that are real, reported, and must not be added to any column, because they
# are not disjoint from the ones that are. Codex emits six `token_type` values per turn and
# only four of them partition the turn: `total` is input plus output, and
# `reasoning_output` is a *subset* of `output` (a turn reporting 27 output and 20 reasoning
# spent 27, not 47). Bucketing either would have inflated every Codex row — `total` alone
# would have doubled it — and nothing downstream would have noticed, because there is no
# independent figure to disagree with. Listed rather than merely absent from
# `TOKEN_BUCKETS` so that this is a decision a reader can find, not an omission they must
# infer; `_metric_bucket` checks it before the lookup, and the unclassified net is
# therefore not tripped by a type we deliberately drop.
NON_DISJOINT_TOKEN_TYPES: Final = frozenset({"total", "reasoning_output"})

TOKEN_METRICS: Final = ("claude_code.token.usage", "codex.turn.token_usage")

# Claude Code's client-side currency figure. It is read, and it is named `list_price_usd`
# everywhere it appears, because it is API list pricing and this account has no bill.
LIST_PRICE_METRICS: Final = ("claude_code.cost.usage",)

# Span attribute keys per bucket, in preference order. The AI SDK puts *both*
# `gen_ai.usage.input_tokens` and `ai.usage.inputTokens` on one span with the same
# number in each, so the reader takes the first key present per bucket. Adding them
# would double every opencode dispatch's token count.
SPAN_TOKEN_KEYS: Final = {
    "input_tokens": (
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.prompt_tokens",
        "ai.usage.inputTokens",
    ),
    "output_tokens": (
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.completion_tokens",
        "ai.usage.outputTokens",
    ),
    "cache_read_tokens": ("ai.usage.cachedInputTokens",),
}

REFUSAL_EVENTS: Final = ("claude_code.api_refusal", "api_refusal")
ERROR_EVENTS: Final = ("claude_code.api_error", "api_error")

# What a provider says when the pool is out. Matched against a record's status code and
# its error-type attribute, never against free text.
RATE_LIMIT_STATUS: Final = ("429", "529")
RATE_LIMIT_TYPES: Final = ("rate_limit_error", "rate_limit", "quota_exceeded", "insufficient_quota")

# ------------------------------------------------------------------- plan currency
#
# What a dispatch costs, in the only currency in which "we ran out" is a sentence:
# percentage points of a pool's window cap (#220, docs/research/token-efficiency-plan-
# currency.md §6). Two numbers per pool and never one — the estimator is the per-dispatch
# number and the meter is what makes it falsifiable — and every input the estimator ran on
# is carried so a recalibration re-derives history rather than invalidating it.

# Output tokens per one percentage point of each Claude window's cap, measured in #218:
# six five-hour points and one seven-day point on 181,253 output tokens. A Claude
# dispatch's plan cost is its output token count over one of these. Input volume, context
# size and cache behaviour do not enter it — not because they are free in principle, but
# because they are measured at under 1/450th the weight. Cache reads were the one residual
# that could have changed that; #237 measured them at ≤ 0.0095 pp₅ₕ/Mtok (≥ 3,477× lighter
# than output, +1.0 point net of wall-clock-matched controls over 105,080,000 tokens), so
# the term `CAP_FRACTION_EXCLUDES` once held as unmeasured is now measured-and-negligible
# and the list is empty.
CLAUDE_TOKENS_PER_POINT: Final = {"five_hour": 30209, "seven_day": 181253}

# Which conversion produced a number. Without it the first plan change silently rewrites
# every past row; with it, a re-measured rate re-prices history. `claude/237-2026-08-06`
# carries #218's measured output weight unchanged (30,209 / 181,253 tokens per point) and
# adds #237's cache-read bound; a row dated before #237 keeps `claude/218-2026-08-05` and
# its `cache_read` exclusion, so the two regimes stay distinguishable under re-pricing.
CALIBRATION_ID: Final = "claude/237-2026-08-06"

CAP_FRACTION_UNIT: Final = "percentage_points"
CAP_FRACTION_BASIS: Final = "output_tokens"
# Empty since #237: cache reads are measured at ≤ 0.0095 pp₅ₕ/Mtok and no longer an
# unmeasured exclusion. Kept as a field so the row still says "nothing is excluded" rather
# than dropping the question.
CAP_FRACTION_EXCLUDES: Final = ()
CAP_FRACTION_ATTRIBUTION: Final = "dispatch_only"

# Which pool a lane's dispatch spends against. A lane absent from this map gets no pool
# and no estimate: booking an unrecognised lane against Claude at zero is exactly the
# under-count that would make routing work off Claude look free.
LANE_POOLS: Final = {"claude-native": "claude", "zai": "zai", "codex": "codex"}

# Every pool has at least two windows and the row records all of them, because scarcity
# routing — when ADR-0061 Decision 1's greedy rule is replaced — routes on whichever one
# binds and not on an average.
POOL_WINDOWS: Final = {
    "claude": ("five_hour", "seven_day"),
    "zai": ("five_hour", "seven_day"),
    # Codex's own vocabulary for its two windows is `primary` and `secondary`
    # (`tools/breaker.py`'s `reading_from_codex_rate_limits`), and it is deliberately not
    # used here. The names in this table are the *view's* names for "the short window" and
    # "the long one", shared across pools so scarcity routing can compare them; the
    # provider's names for the same two windows are its own. ChatGPT Plus meters a
    # five-hour and a weekly window, so the shapes line up.
    "codex": ("five_hour", "seven_day"),
}

EST_FROM_COUNTERS: Final = (
    "output_tokens / the window's measured tokens-per-point (#218's control arm)"
)

NO_ESTIMATOR: Final = {
    "zai": (
        "the z.ai pool meters prompt counts against a time-of-day multiplier rather than "
        "tokens, and publishes no machine-readable state (#221, #226), so no estimator is "
        "derivable from this dispatch's own counters. The denominator and the multiplier "
        "are both known — the held tier is recorded in ~/.arma-cti/plan-tier.json and the "
        "band this dispatch fell in is recorded in its own dispatch.json `plan_charge` "
        "block (#225) — and the numerator is not: a prompt count. #226 owns supplying it"
    ),
    "codex": (
        "no calibration experiment has been run for the Codex pool. #218's method — move a "
        "known token volume and read the meter's displacement — is the precedent and it "
        "applies unchanged here, but #243 deliberately did not spend one: a lane's first "
        "day is the worst time to calibrate it, because the arm mix that will actually run "
        "on it is not yet known. What is already available and what is still missing are "
        "different from z.ai's case and worth stating separately. The **numerator is "
        "present**: Codex reports `codex.turn.token_usage` with an `output_tokens` bucket "
        "per turn, on the same OTel bus every other lane uses, so this dispatch's own "
        "counters would feed an estimator the moment one existed. The **denominator is "
        "missing**: how many output tokens make one percentage point of a ChatGPT Plus "
        "five-hour or weekly window is unpublished and unmeasured. Until it is measured, "
        "an estimate here would be a number with no unit. Note the asymmetry with the z.ai "
        "pool, which has the denominator and lacks the numerator — the two pools are "
        "unpriced for opposite reasons, and a single 'no estimator' would hide that"
    ),
}

UNKNOWN_POOL: Final = (
    "lane {lane!r} maps to no pool this view knows, so no pool is charged for this "
    "dispatch — an unrecognised lane is unpriced, never Claude at zero"
)

# The observed half, today. It is absent rather than zero, and the difference is #218's
# third confound: 28.6 M tokens moved the meter zero on a verified four-minute poll, so
# meter silence is never evidence of a free dispatch.
OBSERVED_ABSENT: Final = (
    "no meter record reaches this view for this dispatch: the quota feed is a status-line "
    "spool read by #226's breaker, not an OTel record carrying cti.dispatch_id. Absent, "
    "not zero — and at the meter's integer-point resolution (one five-hour point is "
    "30,209 output tokens) a single dispatch would read 0 even where one existed"
)

BINDING_UNKNOWN: Final = (
    "the binding window is whichever is nearest exhaustion, which only the meter knows; "
    "with no observed half this row names none rather than guessing one"
)

ATTRIBUTION_NOTE: Final = (
    "dispatch_only: the orchestrator's own Claude turns — composing the briefing, reading "
    "the report, quoting the verdict — share their parent's resource block, carry no "
    "cti.dispatch_id and so reach no row (#227). Every row is therefore a known "
    "under-attribution and never a complete one; on a non-Claude lane that missing term "
    "is precisely the one that decides whether routing off Claude saved anything"
)


class Refusal(NamedTuple):
    """One refusal: its name, what was found, and what the caller should do."""

    kind: str
    found: tuple[str, ...]
    action: str
    failure_class: str = ""

    def lines(self) -> tuple[str, ...]:
        """Render the refusal as the lines the caller reads."""
        classed = (f"class={self.failure_class}",) if self.failure_class else ()
        return (f"refused={self.kind}", *classed, *self.found, f"action={self.action}")


class Source(NamedTuple):
    """Where a dispatch's records were read from, and whether that source can lose them."""

    kind: str
    path: Path | None

    @property
    def degraded(self) -> bool:
        """True when the source rotates, and so cannot be read as a complete record."""
        return self.kind != SOURCE_EXPORT

    def document(self) -> dict[str, Any]:
        """Render the row's own account of what it read."""
        return {
            "kind": self.kind,
            "path": str(self.path) if self.path is not None else None,
            "degraded": self.degraded,
        }


class Item(NamedTuple):
    """One datapoint, log record or span, flattened out of an OTLP batch."""

    kind: str
    name: str
    attrs: Mapping[str, Any]
    value: float | None = None
    temporality: int = 0
    series: str = ""


class Usage(NamedTuple):
    """What a dispatch consumed, normalised across whichever lane reported it."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    list_price_usd: float = 0.0
    list_priced: bool = False
    unclassified: tuple[str, ...] = ()

    def document(self) -> dict[str, Any]:
        """Render the row's usage block: raw counters, and list price under its own name.

        `list_price_usd` is what Claude Code's client-side cost figure says the same
        traffic would have cost at API list prices. It is **not** this dispatch's spend
        and nothing may rank on it (#220 §6.5): the plan charges generation against a
        window cap, and `cap_fraction` is where that lands. It is kept because it is the
        one independent arithmetic check on the token counters, and it is `None` rather
        than 0.0 on a lane that reports no money, since a zero would read as free.
        """
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "list_price_usd": round(self.list_price_usd, 6) if self.list_priced else None,
            "list_priced": self.list_priced,
            "list_price_note": "API list price, not plan spend. Never a decision input.",
            "unclassified": list(self.unclassified),
        }


class CapFraction(NamedTuple):
    """A dispatch's share of its pool's window caps: the estimator and the meter, together.

    Recording only `observed` gives a ledger of zeroes, because one Claude point is
    several median agent runs and a single dispatch reads below the instrument. Recording
    only `est` gives a ledger nobody can check. So the row carries both per window, and
    where a half cannot exist it says which half and why rather than defaulting it to a
    number — a view that filled either one in would be synthesising a record (#227).
    """

    pool: str | None
    est: Mapping[str, float]
    observed: Mapping[str, float]
    est_reason: str

    def document(self) -> dict[str, Any]:
        """Render the row's spend block, both halves per window and every calibration input."""
        return {
            "pool": self.pool,
            "unit": CAP_FRACTION_UNIT,
            "basis": CAP_FRACTION_BASIS,
            "excludes": list(CAP_FRACTION_EXCLUDES),
            "attribution": CAP_FRACTION_ATTRIBUTION,
            "attribution_note": ATTRIBUTION_NOTE,
            "calibration_id": CALIBRATION_ID if self.pool == "claude" else None,
            "windows": {
                window: {
                    "est": self.est.get(window),
                    "observed": self.observed.get(window),
                    "tokens_per_point": CLAUDE_TOKENS_PER_POINT.get(window)
                    if self.pool == "claude"
                    else None,
                }
                for window in POOL_WINDOWS.get(self.pool or "", ())
            },
            "est_reason": self.est_reason,
            "observed_reason": OBSERVED_ABSENT,
            "binding_window": None,
            "binding_reason": BINDING_UNKNOWN,
        }


class EndState(NamedTuple):
    """How the dispatch ended, in ADR-0061's vocabulary, and what record says so."""

    class_: str
    reason: str
    evidence: tuple[str, ...] = ()

    def document(self) -> dict[str, Any]:
        """Render the row's end-state block."""
        return {"class": self.class_, "reason": self.reason, "evidence": list(self.evidence)}


class ReferencingCommit(NamedTuple):
    """One commit whose message names the issue a caller asked about."""

    sha: str
    committed_at: str
    subject: str
    message: str


class Landing(NamedTuple):
    """What git says about the dispatch's issue landing on `origin/main`.

    `shas` is every commit that cleared all three tests, newest first, where `sha` is
    only the newest of them. The row names the tip because that is what a reader wants
    to `git show`; the list exists for a caller asking *membership* rather than "which
    one" — `just trial close-audit` holds a SHA quoted in a close against this window, and
    a caller that had only the tip would have to re-derive the window to answer it
    (#252). Deliberately absent from `document()`: the row's schema names the tip and
    the count, and widening it here would change the ledger's shape for a question the
    row does not ask.
    """

    sha: str | None
    commits: int
    reason: str
    shas: tuple[str, ...] = ()

    def document(self) -> dict[str, Any]:
        """Render the row's landing block."""
        return {"sha": self.sha, "commits": self.commits, "reason": self.reason}


# ------------------------------------------------------------------- reading records


def scalar(value: Mapping[str, Any]) -> str | int | float | bool | None:
    """Unwrap one OTLP `AnyValue`, or `None` for a shape this reader does not carry."""
    if "stringValue" in value:
        return str(value["stringValue"])
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "boolValue" in value:
        return bool(value["boolValue"])
    return None


def attributes(carrier: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten an OTLP attribute list into a mapping."""
    found: dict[str, Any] = {}
    for entry in carrier.get("attributes", []):
        if isinstance(entry, dict) and isinstance(entry.get("key"), str):
            found[entry["key"]] = scalar(entry.get("value", {}))
    return found


# The OTLP metric bodies this view can total. `histogram` is here because Codex reports
# token usage as one — `codex.turn.token_usage` is a histogram whose `sum` over a single
# turn is the count (#243). Reading only `sum` and `gauge` did not merely miss it, it
# missed it *silently*: a body shape the reader did not know yielded no datapoints at all,
# so the metric never reached the unclassified net that exists to catch exactly this. That
# is why `_metric_items` now reports an unreadable body rather than skipping it.
METRIC_BODIES: Final = ("sum", "gauge", "histogram")

UNREADABLE_SHAPE: Final = "__unreadable_body__"


def _datapoints(metric: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], int]:
    """Return a metric's datapoints and the temporality they carry, whatever its body shape."""
    for shape in METRIC_BODIES:
        body = metric.get(shape)
        if isinstance(body, dict):
            points = [point for point in body.get("dataPoints", []) if isinstance(point, dict)]
            return points, int(body.get("aggregationTemporality", 0) or 0)
    return [], 0


def _point_value(point: Mapping[str, Any]) -> float | None:
    """Read a datapoint's scalar value, for a counter point or a histogram point.

    A histogram datapoint carries no `asInt`/`asDouble`; what stands in for "how much" is
    its `sum`, which over a single turn's single observation is the count itself. Buckets
    and bounds are deliberately ignored — this view wants the total, not the distribution.
    """
    if "asDouble" in point:
        return float(point["asDouble"])
    if "asInt" in point:
        return float(point["asInt"])
    if "sum" in point:
        return float(point["sum"])
    return None


def _metric_items(resource_block: Mapping[str, Any]) -> list[Item]:
    found: list[Item] = []
    for scope in resource_block.get("scopeMetrics", []):
        for metric in scope.get("metrics", []) if isinstance(scope, dict) else []:
            if not isinstance(metric, dict):
                continue
            name = str(metric.get("name", ""))
            points, temporality = _datapoints(metric)
            if not points and name in (*TOKEN_METRICS, *LIST_PRICE_METRICS):
                # A metric this view is supposed to read, in a body it cannot. Reported
                # rather than skipped, because a token metric contributing nothing is
                # indistinguishable from a dispatch that spent nothing (#243).
                shape = next(
                    (key for key in metric if key not in ("name", "unit", "description")), ""
                )
                found.append(Item("metric", name, {UNREADABLE_SHAPE: shape}, None, 0, name))
                continue
            for point in points:
                value = _point_value(point)
                if value is None:
                    continue
                attrs = attributes(point)
                series = name + "|" + json.dumps(dict(sorted(attrs.items())), sort_keys=True)
                found.append(Item("metric", name, attrs, value, temporality, series))
    return found


def _log_items(resource_block: Mapping[str, Any]) -> list[Item]:
    found: list[Item] = []
    for scope in resource_block.get("scopeLogs", []):
        for record in scope.get("logRecords", []) if isinstance(scope, dict) else []:
            if not isinstance(record, dict):
                continue
            attrs = attributes(record)
            body = record.get("body", {})
            name = str(attrs.get("event.name") or (scalar(body) if isinstance(body, dict) else ""))
            found.append(Item("log", name, attrs))
    return found


def _span_items(resource_block: Mapping[str, Any]) -> list[Item]:
    found: list[Item] = []
    for scope in resource_block.get("scopeSpans", []):
        for span in scope.get("spans", []) if isinstance(scope, dict) else []:
            if not isinstance(span, dict):
                continue
            found.append(Item("span", str(span.get("name", "")), attributes(span)))
    return found


SIGNALS: Final = (
    ("resourceMetrics", _metric_items),
    ("resourceLogs", _log_items),
    ("resourceSpans", _span_items),
)


def items_for(batch: Mapping[str, Any], dispatch_id: str) -> list[Item]:
    """Flatten one OTLP batch into items, keeping only blocks tagged for this dispatch.

    The resource attribute is re-checked even when the records came from the collector's
    per-dispatch file. `group_by` turns a hostile id into a path rather than an error, so
    a filename is a weaker claim about whose records these are than the record itself.
    """
    found: list[Item] = []
    for key, reader in SIGNALS:
        for block in batch.get(key, []):
            if not isinstance(block, dict):
                continue
            resource = block.get("resource", {})
            tagged = attributes(resource) if isinstance(resource, dict) else {}
            if tagged.get("cti.dispatch_id") != dispatch_id:
                continue
            found.extend(reader(block))
    return found


def choose_source(dispatch_id: str, export_dir: Path, capture: Path) -> Source:
    """Pick the durable per-dispatch export if it exists, else the rotating capture."""
    exported = export_dir / f"dispatch-{dispatch_id}.jsonl"
    if exported.is_file():
        return Source(SOURCE_EXPORT, exported)
    if capture.is_file():
        return Source(SOURCE_CAPTURE, capture)
    return Source(SOURCE_ABSENT, None)


def read_items(source: Source, dispatch_id: str) -> list[Item]:
    """Read every item this dispatch put on the bus, from whichever source was chosen."""
    if source.path is None:
        return []
    found: list[Item] = []
    for batch in rows(source.path):
        found.extend(items_for(batch, dispatch_id))
    return found


# -------------------------------------------------------------- cross-lane normalising


def _metric_totals(items: Iterable[Item]) -> tuple[dict[str, float], list[str]]:
    """Total each metric series, respecting the temporality it was aggregated at.

    Delta datapoints are summed; a cumulative counter reports its running total on every
    export, so its series contributes its maximum and nothing more. Summing a cumulative
    series would multiply a dispatch's spend by how often the collector scraped it.
    """
    delta: dict[str, float] = {}
    cumulative: dict[str, dict[str, float]] = {}
    unclassified: list[str] = []
    for item in items:
        if item.kind != "metric":
            continue
        bucket = _metric_bucket(item)
        if bucket is None:
            if UNREADABLE_SHAPE in item.attrs:
                unclassified.append(f"{item.name}:body={item.attrs[UNREADABLE_SHAPE]!r}")
            elif item.name in (*TOKEN_METRICS, *LIST_PRICE_METRICS):
                kind = item.attrs.get("type", item.attrs.get("token_type"))
                if kind not in NON_DISJOINT_TOKEN_TYPES:
                    unclassified.append(f"{item.name}:type={kind!r}")
            continue
        if item.temporality == TEMPORALITY_CUMULATIVE:
            series = cumulative.setdefault(bucket, {})
            series[item.series] = max(series.get(item.series, 0.0), item.value or 0.0)
        else:
            delta[bucket] = delta.get(bucket, 0.0) + (item.value or 0.0)
    for bucket, series in cumulative.items():
        delta[bucket] = delta.get(bucket, 0.0) + sum(series.values())
    return delta, unclassified


def _metric_bucket(item: Item) -> str | None:
    """Which usage column a token datapoint belongs in, or `None` if it belongs in none.

    Two lanes spell the discriminating attribute differently — Claude Code says `type`,
    Codex says `token_type` — so both are read. `TOKEN_BUCKETS` then decides, and the
    entries that map to nothing are as load-bearing as the ones that map to something:
    see `NON_DISJOINT_TOKEN_TYPES`.
    """
    if item.name in LIST_PRICE_METRICS:
        return "list_price_usd"
    if item.name in TOKEN_METRICS:
        kind = str(item.attrs.get("type", item.attrs.get("token_type", "")))
        if kind in NON_DISJOINT_TOKEN_TYPES:
            return None
        return TOKEN_BUCKETS.get(kind)
    return None


def _span_totals(items: Iterable[Item]) -> dict[str, float]:
    """Total the AI SDK's per-span token counts, one key per bucket per span."""
    totals: dict[str, float] = {}
    for item in items:
        if item.kind != "span":
            continue
        for bucket, keys in SPAN_TOKEN_KEYS.items():
            for key in keys:
                value = item.attrs.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    totals[bucket] = totals.get(bucket, 0.0) + float(value)
                    break
    return totals


def normalise_usage(items: Iterable[Item]) -> Usage:
    """Read one dispatch's consumption, whichever lane and whichever signal carried it."""
    collected = list(items)
    totals, unclassified = _metric_totals(collected)
    for bucket, value in _span_totals(collected).items():
        totals[bucket] = totals.get(bucket, 0.0) + value
    list_price = totals.get("list_price_usd")
    return Usage(
        input_tokens=int(totals.get("input_tokens", 0.0)),
        output_tokens=int(totals.get("output_tokens", 0.0)),
        cache_read_tokens=int(totals.get("cache_read_tokens", 0.0)),
        cache_creation_tokens=int(totals.get("cache_creation_tokens", 0.0)),
        list_price_usd=list_price or 0.0,
        list_priced=list_price is not None,
        unclassified=tuple(sorted(set(unclassified))),
    )


def cap_fraction(lane: str | None, usage: Usage) -> CapFraction:
    """Price one dispatch in its pool's currency: percentage points of a window cap.

    The pool comes from the lane, never from what the records happen to contain, because
    the counters on a non-Claude lane's row are that provider's tokens and dividing them
    by a Claude calibration would charge the wrong pool. A lane with no pool, and a pool
    with no measured estimator, are both typed rather than defaulted — the third of #220's
    prohibitions is that a non-Claude dispatch must not be booked a Claude cost of zero
    by construction, and a zero is exactly what a defaulted estimator would produce.

    The observed half is empty and stays empty here. The meter is a status-line spool
    read by #226's breaker; no record on this bus carries a meter delta keyed to a
    dispatch, and inventing one would be this view writing #226's schema for it.

    The estimate is stored as the exact quotient, unrounded. Its accuracy is the
    calibration's — ±8% on the five-hour weight, #218's integer-resolution readings — and
    rounding it to some shorter decimal would assert a resolution of the ledger's own
    that it does not have, while making a small dispatch's number 0.0.
    """
    pool = LANE_POOLS.get(str(lane or ""))
    if pool is None:
        return CapFraction(None, {}, {}, UNKNOWN_POOL.format(lane=lane))
    if pool != "claude":
        return CapFraction(pool, {}, {}, NO_ESTIMATOR.get(pool, "no estimator for this pool"))
    est = {
        window: usage.output_tokens / per_point
        for window, per_point in CLAUDE_TOKENS_PER_POINT.items()
    }
    return CapFraction(pool, est, {}, EST_FROM_COUNTERS)


# ------------------------------------------------------------------ end-state typing


def _evidence(item: Item) -> str:
    """Render one record as evidence, from the allowlist only — never a body, never text."""
    parts = [item.name]
    parts.extend(
        f"{key}={item.attrs[key]}" for key in EVIDENCE_KEYS if item.attrs.get(key) not in (None, "")
    )
    return " ".join(parts)


def _rate_limited(item: Item) -> bool:
    status = str(item.attrs.get("status_code", ""))
    error_type = str(item.attrs.get("error_type", ""))
    return status in RATE_LIMIT_STATUS or error_type in RATE_LIMIT_TYPES


def _provider_end_state(items: Iterable[Item]) -> EndState | None:
    """Type what the provider's own records say, or `None` when they say nothing bad.

    Refusal outranks quota, because a refused request is not a rationed one: the two have
    different required responses in ADR-0061 and reading a refusal as exhaustion would
    send the dispatch to a queue instead of to another lane.
    """
    collected = list(items)
    for item in collected:
        if item.kind == "log" and item.name in REFUSAL_EVENTS:
            return EndState(
                "provider_refused", "the provider refused the request", (_evidence(item),)
            )
    for item in collected:
        if item.kind == "log" and item.name in ERROR_EVENTS and _rate_limited(item):
            return EndState(
                "quota_exhausted", "the provider reported the pool exhausted", (_evidence(item),)
            )
    return None


def _silent_end_state(source: Source) -> EndState:
    """Type a dispatch that put nothing on the bus, by how much its source can be trusted.

    The two absences are deliberately not the same answer: no records in the durable
    export means the dispatch never reached a provider, and no records in a source that
    rotates means the view cannot see, which is a fact about the view and not about the
    dispatch.
    """
    if source.degraded:
        return EndState(
            "unknown",
            f"no records, and the source ({source.kind}) rotates — absence proves nothing here",
        )
    return EndState(
        "infra_unavailable",
        "the durable export holds no record: the dispatch never reached a provider",
    )


def type_end_state(
    items: Iterable[Item], result: Mapping[str, Any] | None, source: Source
) -> EndState:
    """Type how a dispatch ended, from provider records and the dispatcher's own refusal.

    Order matters. A dispatcher refusal is decisive because it means the run never
    started; after that the provider's own records speak; only then does silence get read.

    What a `quota_exhausted` lane must then wait for is #226's, not this function's. The
    `reset_at` here is whatever the record carried, copied verbatim and never computed.
    """
    collected = list(items)
    if result is not None and result.get("refusal"):
        kind = str(result["refusal"])
        return EndState(
            str(result.get("failure_class") or "infra_unavailable"),
            f"the dispatcher refused before the lane was reached ({kind})",
            (f"result.json refusal={kind}",),
        )
    from_provider = _provider_end_state(collected)
    if from_provider is not None:
        return from_provider
    if result is None:
        return EndState("unknown", "the run has not ended: no result.json beside the plan")
    if not collected:
        return _silent_end_state(source)
    return EndState("ok", "the run ended and its records carry no refusal or quota failure")


# ------------------------------------------------------------------------- the join


def git(*args: str, cwd: Path) -> str:
    """Run one git command and return its stdout, or the empty string if git refused."""
    # S603/S607: fixed literals plus paths this tool computed, and `git` resolves off
    # PATH on purpose — the checkout's toolchain is the caller's.
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout if done.returncode == 0 else ""


def dispatch_start(plan: Mapping[str, Any], result: Mapping[str, Any] | None) -> datetime | None:
    """When this dispatch began, read from the record and never computed.

    `result.json`'s `started_at` is the tightest answer and exists once the run has
    ended; until then the plan's `planned_at`, written before the child exists, is the
    only one there is. A record carrying neither yields `None`, and the caller's job is
    then to say it cannot bound the window rather than to leave it unbounded (#245).
    """
    for candidate in ((result or {}).get("started_at"), plan.get("planned_at")):
        if not isinstance(candidate, str):
            continue
        try:
            when = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return when if when.tzinfo else when.replace(tzinfo=UTC)
    return None


# Both consumers ask git for the same four fields per commit — SHA, committer date in
# strict ISO 8601, subject and whole message — separated by the two record characters no
# commit message can carry. The dispatch-window audit needs the first, second and fourth;
# `just brief`'s prior-work report also renders the subject. One parser keeps their issue
# boundary and accepted commit-message forms identical (#305).
COMMIT_REFERENCE_FORMAT: Final = "%H%x1f%cI%x1f%s%x1f%B%x1e"
COMMIT_REFERENCE_FIELDS: Final = 4


def issue_reference_pattern(issue: int) -> re.Pattern[str]:
    """Match an issue reference without borrowing a prefix from another issue number."""
    return re.compile(rf"(?<![\w#])#{issue}(?![0-9])")


def referencing_commits(log: str, issue: int) -> tuple[ReferencingCommit, ...]:
    """Select commits referencing `issue` from a log in `COMMIT_REFERENCE_FORMAT`.

    This deliberately recognises the issue token rather than interpreting the verb around
    it. The project's `refs #N`, GitHub closing keywords and a squash subject's `(#N)` all
    carry the same reference; whether any one means the issue is complete is not git's
    decision and is not this parser's.
    """
    pattern = issue_reference_pattern(issue)
    found: list[ReferencingCommit] = []
    for entry in log.split("\x1e"):
        fields = entry.split("\x1f", COMMIT_REFERENCE_FIELDS - 1)
        if len(fields) != COMMIT_REFERENCE_FIELDS or not pattern.search(fields[3]):
            continue
        found.append(ReferencingCommit(*(field.strip() for field in fields)))
    return tuple(found)


def _landing_preflight(repo: Path, base_sha: str, ref: str) -> Landing | None:
    """Refuse, naming the reason, where the query cannot be asked at all."""
    if not base_sha:
        return Landing(None, 0, "the dispatch record carries no base SHA")
    if not git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=repo).strip():
        return Landing(None, 0, f"{ref} is not in this checkout")
    return None


def landed(
    repo: Path, issue: int, base_sha: str, since: datetime | None, ref: str = "origin/main"
) -> Landing:
    """Find the commits on `ref` that this dispatch could have landed.

    Three tests, and a commit must clear all of them. Its message must reference the
    issue. It must **descend from the dispatch's base**, since a commit on another line
    of the history is not this dispatch's tree plus a change — `base..ref` alone lists
    everything reachable from the tip, which on a review dispatch reaches back to
    whatever SHA was under review, because `docs/review-dispatch.md` prescribes passing
    the *reviewed* commit as `--base-sha`. And it must **postdate the dispatch's own
    start**, since a commit that existed before the dispatch was armed cannot be its
    work: the row that provoked this credited a review dispatch with a commit made
    seventy-six minutes earlier (#245).

    The floor is the start truncated to the second, because git records committer dates
    at second resolution and a start carrying microseconds must not exclude the very
    second it began in.

    The newest survivor is reported as the landed SHA, because an issue may land in
    several commits and the tip is what a reader wants to `git show`. The count is
    carried so that "several" is visible rather than lost behind one SHA, and every
    refusal names which of the three tests answered.
    """
    refusal = _landing_preflight(repo, base_sha, ref)
    if refusal is not None:
        return refusal
    if since is None:
        return Landing(None, 0, "the dispatch record carries no start time")
    log = git(
        "log",
        "--ancestry-path",
        f"--format={COMMIT_REFERENCE_FORMAT}",
        f"{base_sha}..{ref}",
        cwd=repo,
    )
    if not log.strip():
        return Landing(None, 0, f"nothing on {ref} descends from {base_sha[:8]}")
    referencing = referencing_commits(log, issue)
    if not referencing:
        return Landing(
            None, 0, f"no commit on {ref} descending from {base_sha[:8]} references #{issue}"
        )
    floor = since.replace(microsecond=0)
    matched = [
        commit.sha for commit in referencing if datetime.fromisoformat(commit.committed_at) >= floor
    ]
    if not matched:
        return Landing(
            None,
            0,
            f"{len(referencing)} commit(s) on {ref} reference #{issue} but predate "
            f"this dispatch's start ({floor.isoformat()})",
        )
    return Landing(
        matched[0],
        len(matched),
        f"referenced by {len(matched)} commit(s) on {ref} after {floor.isoformat()}",
        tuple(matched),
    )


# A review seat's output is claims, which land nothing on their own — the reason
# ADR-0071 ruling 2 gives it a preference list at all — and `recon` is read-only by
# construction. For
# those two seats `landed` is not a weak answer but a category error, so the row says the
# seat lands nothing and names no commit at all (#245). A seat this table does not know
# is assumed to land: the view reads what the record carries and does not invent a claim
# about a seat it has never met. `tools/dispatch.py`'s `SEATS` is the roster, and a unit
# test holds the two in step so a new seat cannot arrive here unclassified.
SEAT_LANDS: Final[dict[str, bool]] = {
    # ADR-0071 ruling 2 says it in as many words: the planner works out what to do and
    # neither gates nor lands, so `landed` is the same category error here as on `review`.
    "planner": False,
    "implementer": True,
    "recon": False,
    "review": False,
    # Ruling 3: a retro identifies, researches and files backlog items, and lands nothing.
    "retro": False,
    "fable": True,
    "orchestrator": True,
}


def seat_lands(seat: object) -> bool:
    """Say whether this seat can land a commit at all."""
    if not isinstance(seat, str):
        return True
    return SEAT_LANDS.get(seat, True)


def gate_outcome(
    landing: Landing, result: Mapping[str, Any] | None, end_state: EndState, seat: object
) -> str:
    """Name what the gates say about this dispatch, from the evidence that exists.

    `landed` is the strong answer and the only mechanical one: a commit on `origin/main`
    cleared `cog verify` and the repo hooks, and CLAUDE.md binds landing to a green
    `just fast`. The child's exit code is deliberately not read as a gate result — the
    gates run inside the dispatched process and a coding agent exits zero for reasons of
    its own.

    A seat that lands nothing by construction gets `lands_nothing` where an implementer
    would get `not_landed`, because `not_landed` reads as a gate this dispatch was
    running for and did not clear. The typings that say the run was never a result, or is
    not over, still win — they are facts about this dispatch, and the seat rule is a fact
    about the seat.
    """
    lands = seat_lands(seat)
    if landing.sha and lands:
        return "landed"
    if result is None:
        return "running"
    if end_state.class_ in ("provider_refused", "quota_exhausted", "infra_unavailable"):
        return "not_a_result"
    if not lands:
        return "lands_nothing"
    return "not_landed"


# ---------------------------------------------------------------------- materialising


def read_json(path: Path) -> dict[str, Any] | None:
    """Read one JSON document, or `None` when it is absent or not a document."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


def count_kinds(items: Iterable[Item]) -> dict[str, int]:
    """Count what was read, per signal, so a row says how much it stands on."""
    counts = {"metrics": 0, "logs": 0, "spans": 0}
    for item in items:
        counts[{"metric": "metrics", "log": "logs", "span": "spans"}[item.kind]] += 1
    return {"total": sum(counts.values()), **counts}


def materialise(
    record: Path,
    *,
    export_dir: Path,
    capture: Path,
    repo: Path,
    now: datetime,
) -> dict[str, Any]:
    """Build one dispatch's row: what it consumed, how it ended, and where it landed.

    Reads the plan the dispatcher wrote, the records the collector wrote, and git. Writes
    nothing but the row — no record is edited, appended to, or moved.
    """
    plan = read_json(record / "dispatch.json") or {}
    result = read_json(record / "result.json")
    dispatch_id = str(plan.get("dispatch_id") or record.name)
    source = choose_source(dispatch_id, export_dir, capture)
    items = read_items(source, dispatch_id)
    issue = int(plan.get("issue") or 0)
    base_sha = str(plan.get("base_sha") or "")
    seat = plan.get("seat")
    if not seat_lands(seat):
        landing = Landing(None, 0, f"the {seat} seat lands nothing")
    elif not issue:
        landing = Landing(None, 0, "the dispatch names no issue")
    else:
        landing = landed(repo, issue, base_sha, dispatch_start(plan, result))
    end_state = type_end_state(items, result, source)
    usage = normalise_usage(items)
    lane = plan.get("lane")
    return {
        "schema": SCHEMA,
        "materialised_at": now.isoformat(),
        "dispatch_id": dispatch_id,
        "lane": lane,
        "profile": plan.get("profile"),
        "seat": seat,
        "issue": issue or None,
        "base_sha": base_sha or None,
        "source": source.document(),
        "records": count_kinds(items),
        "usage": usage.document(),
        "cap_fraction": cap_fraction(lane if isinstance(lane, str) else None, usage).document(),
        "end_state": end_state.document(),
        "gate": {
            "outcome": gate_outcome(landing, result, end_state, seat),
            "landed": landing.document(),
            "returncode": result.get("returncode") if result else None,
            "started_at": result.get("started_at") if result else None,
            "ended_at": result.get("ended_at") if result else None,
        },
    }


def _points(value: object) -> str:
    """Render one cap-fraction half: the number, or `none` where that half does not exist."""
    return f"{value:.6f}" if isinstance(value, (int, float)) else "none"


def row_line(row: Mapping[str, Any]) -> str:
    """One dispatch, in the tier's `key=value` form.

    The spend fields are the five-hour window's two halves. Five-hour because it is the
    tighter window per dispatch and the one #218 measured to ±8%; both halves because a
    line showing only the estimator would put back the unfalsifiable number the schema
    exists to prevent. List price is deliberately absent from the summary line and lives
    in the row under its own name — it is a token-flow figure, not this dispatch's spend.
    """
    usage = row["usage"]
    five_hour = row["cap_fraction"]["windows"].get("five_hour", {})
    return " ".join(
        (
            f"dispatch={row['dispatch_id']}",
            f"lane={row['lane']}",
            f"issue={row['issue']}",
            f"source={row['source']['kind']}",
            f"degraded={str(row['source']['degraded']).lower()}",
            f"records={row['records']['total']}",
            f"in={usage['input_tokens']}",
            f"out={usage['output_tokens']}",
            f"pool={row['cap_fraction']['pool'] or 'none'}",
            f"cap5h_est={_points(five_hour.get('est'))}",
            f"cap5h_obs={_points(five_hour.get('observed'))}",
            f"class={row['end_state']['class']}",
            f"gate={row['gate']['outcome']}",
            f"landed={row['gate']['landed']['sha'] or 'none'}",
        )
    )


# ---------------------------------------------------------------------------- actions


class Options(NamedTuple):
    """Every path an action touches, so a test can put them all in a tmp_path."""

    dispatch_root: Path
    export_dir: Path
    capture: Path
    repo: Path
    days: int
    apply: bool
    dispatch: str


def records_under(root: Path, only: str) -> list[Path]:
    """Return the dispatch records to read: one if named, else every one there is."""
    if only:
        return [root / only]
    if not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if (path / "dispatch.json").is_file())


def sync(options: Options, now: datetime) -> tuple[tuple[str, ...], int]:
    """Materialise a row per dispatch, and say which source every one of them read."""
    if not options.export_dir.is_dir() and not options.capture.is_file():
        return (
            Refusal(
                "telemetry_source_absent",
                (
                    f"export_dir={options.export_dir} (absent)",
                    f"capture={options.capture} (absent)",
                    "Neither the durable per-dispatch export nor the rotating capture exists.",
                    (
                        "The export appears once the human runs what `just prereqs "
                        "sudo-script` generated (#230)."
                    ),
                ),
                STOP_NOT_A_RESULT,
                failure_class="infra_unavailable",
            ).lines(),
            EXIT_REFUSED,
        )

    records = records_under(options.dispatch_root, options.dispatch)
    if not records:
        where = options.dispatch or str(options.dispatch_root)
        return (f"ok=no_dispatches where={where}",), 0

    lines: list[str] = []
    degraded = 0
    for record in records:
        if not (record / "dispatch.json").is_file():
            lines.append(f"skipped={record.name} reason=no_dispatch_json")
            continue
        row = materialise(
            record,
            export_dir=options.export_dir,
            capture=options.capture,
            repo=options.repo,
            now=now,
        )
        (record / "ledger.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        degraded += int(bool(row["source"]["degraded"]))
        lines.append(row_line(row))
    if degraded:
        lines.append(
            f"warning=degraded_source rows={degraded} "
            f"detail=read from {options.capture}, which rotates at 50MB x 5 and loses records; "
            "run the #230 root script for the durable per-dispatch export"
        )
    lines.append(f"ok=synced rows={len(records)} degraded={degraded}")
    return tuple(lines), 0


def show(options: Options) -> tuple[tuple[str, ...], int]:
    """Print one materialised row in full, or say plainly that it has not been synced."""
    record = options.dispatch_root / options.dispatch
    row = read_json(record / "ledger.json")
    if row is None:
        return (
            Refusal(
                "not_materialised",
                (f"dispatch={options.dispatch}", f"expected={record / 'ledger.json'}"),
                "Run `just ledger-sync` first.",
            ).lines(),
            EXIT_REFUSED,
        )
    return tuple(json.dumps(row, indent=2).splitlines()), 0


class Verdict(NamedTuple):
    """What `prune` decided about one raw export file."""

    path: Path
    prunable: bool
    reason: str


def prunable(options: Options, now: float) -> list[Verdict]:
    """Decide, per raw export file, whether the view has already taken what it holds.

    A raw file is prunable only when a row exists that was materialised **from the
    durable export** and read at least one record out of it. Pruning ahead of the view,
    or on the strength of a row read from the rotating capture, would delete the only
    copy of records the ledger never saw.
    """
    if not options.export_dir.is_dir():
        return []
    horizon = now - options.days * SECONDS_PER_DAY
    verdicts: list[Verdict] = []
    for path in sorted(options.export_dir.glob("dispatch-*.jsonl")):
        dispatch_id = path.name[len("dispatch-") : -len(".jsonl")]
        row = read_json(options.dispatch_root / dispatch_id / "ledger.json")
        if path.stat().st_mtime > horizon:
            kept = f"newer than the {options.days}-day horizon"
        elif row is None:
            kept = "no materialised row: run `just ledger-sync` first"
        elif row.get("source", {}).get("kind") != SOURCE_EXPORT:
            kept = "the row was read from the rotating capture, not this file"
        elif int(row.get("records", {}).get("total", 0)) <= 0:
            kept = "the row read no records out of this file"
        else:
            verdicts.append(Verdict(path, prunable=True, reason="materialised from this file"))
            continue
        verdicts.append(Verdict(path, prunable=False, reason=kept))
    return verdicts


def prune(options: Options, now: float) -> tuple[tuple[str, ...], int]:
    """Report, and with `--apply` delete, the raw export files the view no longer needs."""
    verdicts = prunable(options, now)
    lines = [
        f"{'prune' if verdict.prunable else 'keep'}={verdict.path.name} reason={verdict.reason}"
        for verdict in verdicts
    ]
    doomed = [verdict for verdict in verdicts if verdict.prunable]
    if options.apply:
        for verdict in doomed:
            verdict.path.unlink()
    lines.append(
        f"ok={'pruned' if options.apply else 'dry_run'} "
        f"files={len(verdicts)} prunable={len(doomed)} days={options.days}"
    )
    if doomed and not options.apply:
        lines.append("action=re-run with --apply to delete them")
    return tuple(lines), 0


def parse_args(argv: list[str]) -> tuple[str, Options]:
    """Read the command line into an action and the paths it touches."""
    parser = argparse.ArgumentParser(description="The per-dispatch ledger: a view over OTel.")
    parser.add_argument("action", nargs="?", default="sync", choices=("sync", "show", "prune"))
    parser.add_argument("--dispatch", default="", help="one dispatch id, else every record")
    parser.add_argument("--dispatch-dir", default=str(DISPATCH_ROOT))
    parser.add_argument("--export-dir", default=str(LEDGER_EXPORT))
    parser.add_argument("--capture", default=str(ROTATING_CAPTURE))
    parser.add_argument("--repo", default=".")
    parser.add_argument("--days", type=int, default=RETENTION_DAYS)
    parser.add_argument("--apply", action="store_true", help="prune: actually delete")
    args = parser.parse_args(argv)
    return args.action, Options(
        dispatch_root=Path(args.dispatch_dir).expanduser(),
        export_dir=Path(args.export_dir).expanduser(),
        capture=Path(args.capture).expanduser(),
        repo=Path(args.repo).expanduser().resolve(),
        days=args.days,
        apply=args.apply,
        dispatch=args.dispatch,
    )


def emit(lines: Iterable[str], code: int) -> int:
    """Print to the stream the exit code implies, and return it."""
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def main(argv: list[str]) -> int:
    """Run one action and print what it decided."""
    action, options = parse_args(argv)
    if action == "show" and not options.dispatch:
        return emit(("refused=no_dispatch", "action=Pass --dispatch <id>."), EXIT_REFUSED)
    if action == "sync":
        lines, code = sync(options, datetime.now(tz=UTC))
    elif action == "show":
        lines, code = show(options)
    else:
        lines, code = prune(options, time.time())
    return emit(lines, code)


if __name__ == "__main__":  # pragma: no cover - the seam
    raise SystemExit(main(sys.argv[1:]))
