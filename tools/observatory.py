"""`just observatory`: the observatory store (#482, spec #478, ADR-0071 ruling 6).

A derived store over the work system, rebuilt in full from its sources on every run,
answering one question end to end: **what a landed issue cost, per lane, in that
lane's own meter.** It reads and never writes the OTel bus, and it reports rather
than routes — nothing here excludes a profile, reroutes work or trips a breaker.

- **The store is a cache and never a source of truth.** Every run rebuilds it from
  the per-dispatch OTel export, the dispatch records and git, whole, with no
  incremental append and no migration path. A schema change is a re-run. The output
  is deterministic: no wall-clock, no ordering but the sorted one, no mtimes — two
  runs over the same inputs produce the same bytes (#504).
- **The raw export is not immutable, and the store says so.** `ledger prune` deletes
  an export file after `RETENTION_DAYS` once a materialised row exists, so a rebuild
  after a prune reads a different world from a rebuild before one. Where the file is
  gone the row is read from the dispatch's own `ledger.json`, visibly: the
  `telemetry_source` column names it and the coverage line counts it. The row carries
  the metric and span encodings' numbers, so a pruned dispatch's spend survives —
  except where the row cannot answer. A row that reads zero cannot distinguish a true
  zero from a silence, and it cannot carry the log-record encoding at all, so there
  the spend is absent with a reason naming the ceiling, never zero: silent loss over
  a pruned source is this ticket's own trap in a different disguise.
- **Both spend encodings are read, and this is the ticket's whole point.** Claude
  emits per-request token counts as attributes on `claude_code.api_request` log
  records; Codex emits `codex.turn.token_usage` as a histogram metric carrying a
  `token_type` attribute. A reader that models only one returns rows, looks correct,
  and books an entire lane at zero — #458's most-repeated defect in a new place, and
  the reason `spend.encoding` names which of the two a row actually read. The metric
  half is `tools/ledger.py`'s own reader, reused rather than re-derived; the
  log-record half is read here because no reader of it existed.
- **Spend is per lane and never summed.** Three meters that do not convert into one
  another (ADR-0061 Decision 5, reaffirmed by #478) can have no total column, so the
  store's shape has nowhere to put one: one row per (issue, lane), each in its own
  meter. The Claude lane is expressed in five-hour-window points via `ledger`'s
  calibration; every other lane reports its provider's own token counters and is
  marked **uncalibrated** — and on every lane an absent cost renders as `absent`,
  because absent, uncalibrated and zero are three different facts and a lane at zero
  must be impossible to confuse with a lane that is cheap or a lane whose spend could
  not be derived.
- **Every null carries a reason.** A column that cannot be derived says why, in a
  sibling `<column>_reason` key that is non-null exactly when its column is null —
  the `cap_fraction` pattern, applied store-wide.
- **Malformed input is counted and named, not swallowed and not fatal.** A truncated
  JSON line in the export increments a counter naming its file, the rebuild
  completes, and the count appears in the output (#496, #503).
- **The flow view (#486) rides the same store and never a second one.** One `work_items`
  row per issue — its state, and the clock its lead time runs on — over the same dispatch
  rows the cost view reads. Lead time renders as nearest-rank percentiles through the one
  view `flow_lead_time`, whose column list is percentiles and a sample size and nothing
  else, because the distribution is right-skewed and its mean would sit above its own 70th
  percentile. Abandoned work is typed by `tools/ledger.py`'s own `gate_outcome`
  vocabulary — `not_a_result` — read from the records at rebuild time; #489's recorded
  terminal state will widen that derivation, and `stopped` holds the terminal residue
  until it does.

Sources, all outside every worktree: the dispatch records at `~/.arma-cti/dispatches/`
(`CTI_DISPATCH_DIR`), the per-dispatch OTel export at `/var/log/claude-otel/dispatches/`
(`CTI_OTEL_EXPORT_DIR`), the store's own home `~/.arma-cti/observatory/`
(`CTI_OBSERVATORY_DIR`), and the repository for the landing join (`--repo`).

A source directory this process cannot see is a **named refusal**, never a partial
rebuild presented as complete. A dispatch whose export file is absent is a row with a
reason, never a dropped row: the store's coverage block carries its own denominators
so every number a reader quotes can carry its own.

The analyst's contract — schema reference, query cookbook and hazards list — lives in
`docs/observatory/`, and the cookbook's queries run against the shipped store in a
test: documentation that does not run is worse than none. The query engine is the
standard library's `sqlite3` over the materialised store. #478 named DuckDB over
`read_json` views; adding that dependency needs an approval a dispatched session does
not carry, and the contract the analyst reads — SQL over these tables — is unchanged
by the engine, so the swap, if ever wanted, touches only the cookbook.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path — the device `ledger.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

import ledger

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

SCHEMA: Final = "cti.observatory/2"
STORE_NAME: Final = "store.json"

EXIT_REFUSED: Final = 1

DEFAULT_DISPATCH_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"
DEFAULT_EXPORT_DIR: Final = Path("/var/log/claude-otel/dispatches")
# Outside every worktree, like every other evidence store: a worktree removal must
# not be able to destroy it (#478, user story 39).
DEFAULT_STORE_DIR: Final = Path.home() / ".arma-cti" / "observatory"

DISPATCH_FILE: Final = "dispatch.json"
RESULT_FILE: Final = "result.json"
EXPORT_PREFIX: Final = "dispatch-"
EXPORT_SUFFIX: Final = ".jsonl"

SOURCE_EXPORT: Final = "ledger_export"
SOURCE_LEDGER_ROW: Final = "ledger_row"
SOURCE_ABSENT: Final = "absent"

ENCODING_METRIC: Final = "metric"
ENCODING_LOG_RECORDS: Final = "log_records"
ENCODING_MIXED: Final = "mixed"

# The Claude lane's meter: five-hour-window points, the window #218 measured to ±8%
# and the currency #220 found the plan actually charges. Every other lane reports its
# provider's own counters.
METER_CLAUDE: Final = "claude_five_hour_window_points"
METER_UNCALIBRATED: Final = "uncalibrated_provider_tokens"
CLAUDE_LANE: Final = "claude-native"

UNCALIBRATED_REASON: Final = (
    "uncalibrated: no calibration experiment has been run for this lane's meter, so "
    "its counters are reported in the provider's own units and no conversion to any "
    "other lane's meter exists (ADR-0061 Decision 5; `tools/ledger.py`'s "
    "NO_ESTIMATOR carries the per-lane detail)"
)

NO_TELEMETRY_REASON: Final = (
    "no per-dispatch OTel export file exists for this dispatch, and no materialised "
    "ledger row survives it"
)
NO_TOKEN_RECORDS_REASON: Final = (
    "the export file carries no token records in either encoding — no token metric "  # noqa: S105 — a reason string, not a secret; the name carries "token" because the absence it names is of token records
    "and no token-bearing log record"
)

# The fallback's own account of itself. `ledger prune` deletes an export file only
# once a row materialised from that same file exists (`prunable`, RETENTION_DAYS), so
# where the file is gone the row is the surviving record — but only of the encodings
# `normalise_usage` reads. A row's zeros cannot distinguish a measurement from a
# silence, and a log-record-only dispatch's numbers never reached the row at all.
LEDGER_FILE: Final = "ledger.json"
PRUNED_EXPORT_REASON: Final = (
    "the raw export file is gone — `ledger prune` deletes it once a materialised row "
    "exists (`tools/ledger.py`, RETENTION_DAYS) — so this row is read from the "
    "dispatch's own ledger.json"
)
ROW_SPEND_NOT_DERIVABLE: Final = (
    "the raw export file is gone and the surviving ledger row reads zero, which cannot "
    "distinguish a true zero from a silence and never carried the log-record encoding, "
    "so whether this dispatch spent is not derivable from what survives"
)
ROW_UNREADABLE: Final = "a ledger.json exists beside the dispatch record but would not parse"
ROW_NO_END_STATE: Final = (
    "the pruned source's ledger row carries no end_state block, so how this dispatch "
    "ended is not derivable from what survives"
)
NO_START_REASON: Final = "neither the result nor the plan carries a start time"

# Attribute keys a log record may carry its token counts under. `claude_code.api_request`
# carries exactly these (docs/research/agent-observability-and-cost-ledgers.md); the
# reader is name-tolerant because a log record's body name and its `event.name`
# attribute disagree on some vintages, and what identifies a spend record is the
# attribute, not the event name.
LOG_TOKEN_KEYS: Final = {
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_read_tokens": "cache_read_tokens",
    "cache_creation_tokens": "cache_creation_tokens",
}

# The sqlite projection of the store: table name to ordered columns. Declared once so
# the schema reference, the loader and the tests cannot drift apart.
DISPATCH_COLUMNS: Final = (
    "dispatch_id",
    "lane",
    "lane_reason",
    "profile",
    "profile_reason",
    "seat",
    "seat_reason",
    "issue",
    "issue_reason",
    "telemetry_source",
    "telemetry_path",
    "telemetry_path_reason",
    "spend_encoding",
    "spend_encoding_reason",
    "input_tokens",
    "input_tokens_reason",
    "output_tokens",
    "output_tokens_reason",
    "cache_read_tokens",
    "cache_read_tokens_reason",
    "cache_creation_tokens",
    "cache_creation_tokens_reason",
    "landed_sha",
    "landed_sha_reason",
    "started_at",
    "started_at_reason",
    "end_state_class",
    "end_state_class_reason",
    "gate_outcome",
    "gate_outcome_reason",
)

WORK_ITEM_COLUMNS: Final = (
    "issue",
    "state",
    "clock_start",
    "clock_start_reason",
    "clock_end",
    "clock_end_reason",
    "lead_time_seconds",
    "lead_time_seconds_reason",
)

# One work item's state, in preference order. `abandoned` reuses `gate_outcome`'s
# `not_a_result` — the classes `tools/ledger.py`'s own vocabulary already names — and is
# derived at read time from the records, because #489's recorded terminal state does not
# exist yet; when it lands it widens this derivation rather than competing with it.
# `stopped` is the terminal residue: every dispatch ended, none landed, none carried a
# not-a-result class. An issue whose dispatches are all review or recon seats lands in
# the same residue, because a seat that lands nothing is a fact about the seat and not
# about this issue's completion.
STATE_LANDED: Final = "landed"
STATE_OPEN: Final = "open"
STATE_ABANDONED: Final = "abandoned"
STATE_STOPPED: Final = "stopped"

# Lead time's percentiles, nearest-rank: the p-th percentile is the value at rank
# ceil(p·n/100) in the ascending sort, one member of the sample, never an interpolation
# between two. Nearest-rank because it is exact integer arithmetic and expressible in
# the standard library's SQL, so the shipped store answers it without a custom function
# — and because a percentile whose method is unstated is not a reproducible number.
# This view is the one rendering path for lead time and its column list is the whole
# slot: percentiles and the sample size, no mean, so a skewed distribution cannot be
# summarised by a number above its own 70th percentile. The tests pin the column list
# and pin the values on a sample where nearest-rank and linear interpolation disagree.
FLOW_LEAD_TIME_VIEW: Final = """
CREATE VIEW flow_lead_time AS
WITH ranked AS (
    SELECT lead_time_seconds AS v,
           ROW_NUMBER() OVER (ORDER BY lead_time_seconds) AS r,
           COUNT(*) OVER () AS n
    FROM work_items
    WHERE state = 'landed' AND lead_time_seconds IS NOT NULL
)
SELECT MAX(CASE WHEN r = (n * 50 + 99) / 100 THEN v END) AS p50_seconds,
       MAX(CASE WHEN r = (n * 70 + 99) / 100 THEN v END) AS p70_seconds,
       MAX(CASE WHEN r = (n * 85 + 99) / 100 THEN v END) AS p85_seconds,
       MAX(CASE WHEN r = (n * 95 + 99) / 100 THEN v END) AS p95_seconds,
       MAX(n) AS items
FROM ranked
"""

ISSUE_COST_COLUMNS: Final = (
    "issue",
    "lane",
    "landed",
    "landed_sha",
    "landed_sha_reason",
    "dispatches",
    "spend_dispatches",
    "spend_encoding",
    "spend_encoding_reason",
    "input_tokens",
    "input_tokens_reason",
    "output_tokens",
    "output_tokens_reason",
    "cache_read_tokens",
    "cache_read_tokens_reason",
    "cache_creation_tokens",
    "cache_creation_tokens_reason",
    "meter",
    "calibration_id",
    "calibration_id_reason",
    "cost",
    "cost_reason",
)


class Refusal(NamedTuple):
    """One refusal: its name, what was found, and what the caller should do."""

    kind: str
    found: tuple[str, ...]
    action: str

    def lines(self) -> tuple[str, ...]:
        """Render the refusal as the lines the caller reads."""
        return (f"refused={self.kind}", *self.found, f"action={self.action}")


class ExportRead(NamedTuple):
    """One dispatch's export file: its batches, and the lines that would not parse."""

    batches: tuple[Mapping[str, Any], ...]
    malformed: int


class Spend(NamedTuple):
    """One dispatch's consumption, and which of the two encodings carried it."""

    encoding: str | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    reason: str | None


# ---------------------------------------------------------------------- reading sources


def read_export(path: Path) -> ExportRead:
    """Read one per-dispatch export file, counting rather than swallowing bad lines.

    A truncated line is ordinary in an appended file whose writer can be killed
    mid-line, and four exist in the current archive. Skipping one silently is what
    #496 exists to prevent: a parse boundary must report. So each bad line increments
    a counter its caller names the file for, and the rebuild continues.
    """
    batches: list[Mapping[str, Any]] = []
    malformed = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            batch = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(batch, dict):
            batches.append(batch)
        else:
            malformed += 1
    return ExportRead(tuple(batches), malformed)


def _log_record_spend(items: Sequence[ledger.Item]) -> dict[str, int]:
    """Total the token counts log records carry as attributes, per bucket.

    The encoding Claude Code actually emits per request: `claude_code.api_request`
    records with `input_tokens` / `output_tokens` and the two cache halves. Counted
    only when no metric or span carried the same dispatch's spend — a lane that emits
    both encodings for one dispatch would be double-booked by a reader that summed
    them, and the selection lives at the caller.
    """
    totals: dict[str, int] = {}
    for item in items:
        if item.kind != "log":
            continue
        for source, bucket in LOG_TOKEN_KEYS.items():
            value = item.attrs.get(source)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[bucket] = totals.get(bucket, 0) + int(value)
    return totals


def _has_metric_or_span_spend(items: Sequence[ledger.Item]) -> bool:
    """Say whether any token metric or token-bearing span exists among the items.

    Presence, not value: a metric that reports a true zero must still select the
    metric encoding rather than falling through to the log-record half, because the
    zero is a measurement and not a silence (#225's distinction, applied here).
    """
    for item in items:
        if item.kind == "metric" and item.name in ledger.TOKEN_METRICS:
            return True
        if item.kind == "span" and any(
            key in item.attrs for keys in ledger.SPAN_TOKEN_KEYS.values() for key in keys
        ):
            return True
    return False


def read_spend(items: Sequence[ledger.Item]) -> Spend:
    """Read one dispatch's spend in whichever encoding its records actually carry.

    The two encodings are selected, never summed: a dispatch whose metrics reported
    the spend is priced from its metrics, and only a dispatch with no metric or span
    carrying spend falls to the log-record half. A dispatch with neither gets a
    reason and no number — an absence is never a zero.
    """
    if _has_metric_or_span_spend(items):
        usage = ledger.normalise_usage(items)
        return Spend(
            ENCODING_METRIC,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_creation_tokens,
            None,
        )
    log_totals = _log_record_spend(items)
    if log_totals:
        return Spend(
            ENCODING_LOG_RECORDS,
            log_totals.get("input_tokens", 0),
            log_totals.get("output_tokens", 0),
            log_totals.get("cache_read_tokens", 0),
            log_totals.get("cache_creation_tokens", 0),
            None,
        )
    return Spend(None, None, None, None, None, NO_TOKEN_RECORDS_REASON)


def _row_spend(row: Mapping[str, Any] | None) -> Spend:
    """Read one dispatch's spend from its materialised ledger row, or say it cannot.

    The fallback for a pruned export file. A row with token numbers carries the metric
    and span encodings' figures verbatim — `normalise_usage` is the same reader the
    metric half above uses — so a pruned dispatch's spend survives except where the row
    cannot answer: all-zero usage is ambiguous (a true zero, a silence, or a
    log-record-only dispatch whose numbers never reached the row), and an absence is
    never resolved to a zero.
    """
    if row is None:
        return Spend(None, None, None, None, None, ROW_UNREADABLE)
    usage = row.get("usage")
    buckets = (
        {bucket: usage.get(bucket) for bucket in LOG_TOKEN_KEYS.values()}
        if isinstance(usage, dict)
        else {}
    )
    if not any(isinstance(value, int) and value for value in buckets.values()):
        return Spend(None, None, None, None, None, ROW_SPEND_NOT_DERIVABLE)
    return Spend(
        ENCODING_METRIC,
        int(buckets.get("input_tokens") or 0),
        int(buckets.get("output_tokens") or 0),
        int(buckets.get("cache_read_tokens") or 0),
        int(buckets.get("cache_creation_tokens") or 0),
        None,
    )


def _landing_for(
    plan: Mapping[str, Any], issue: int | None, result: Mapping[str, Any] | None, repo: Path
) -> ledger.Landing:
    """Return what git says this one dispatch landed, bounded as #245 bounds it.

    The seat test comes first, as it does in `ledger.materialise`: asking a `review`
    dispatch what it landed is a category error, and the row must say the seat lands
    nothing rather than reading as a weak git answer.
    """
    seat = plan.get("seat")
    base_sha = str(plan.get("base_sha") or "")
    if not ledger.seat_lands(seat):
        return ledger.Landing(None, 0, f"the {seat} seat lands nothing")
    if not issue:
        return ledger.Landing(None, 0, "the dispatch names no issue")
    return ledger.landed(repo, issue, base_sha, ledger.dispatch_start(plan, result))


def _issue_of(plan: Mapping[str, Any]) -> int | None:
    """Narrow the record's issue to a positive int, refusing nothing and crashing never.

    A record is untrusted input: `issue` can be absent, a string, a bool or a float,
    and every one of those is a null with a reason rather than a raised ValueError
    that would take the whole rebuild down with one malformed record.
    """
    value = plan.get("issue")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


# ------------------------------------------------------------------------ the rebuild


def _end_state_for(
    items: Sequence[ledger.Item],
    result: Mapping[str, Any] | None,
    ledger_row: Mapping[str, Any] | None,
    telemetry_source: str,
    export_path: Path,
) -> ledger.EndState | None:
    """Type how this dispatch ended, reusing `ledger`'s reader wherever one applies.

    The export-present case is `ledger.type_end_state` itself — the existing vocabulary
    and the existing order of tests. A pruned dispatch is typed from the surviving row's
    own `end_state` block, because the records the typing would have read are gone; a
    row without the block is a null with a reason, never a guessed class. A dispatch with
    no telemetry at all keeps the same reader over no records, which is what that reader
    already says about silence: nothing, by name.
    """
    if telemetry_source == SOURCE_EXPORT:
        return ledger.type_end_state(items, result, ledger.Source(SOURCE_EXPORT, export_path))
    if telemetry_source == SOURCE_LEDGER_ROW:
        block = ledger_row.get("end_state") if ledger_row is not None else None
        state = block.get("class") if isinstance(block, dict) else None
        if isinstance(state, str) and state:
            return ledger.EndState(state, "read from the materialised ledger row", ())
        return None
    return ledger.type_end_state([], result, ledger.Source(SOURCE_ABSENT, None))


def _dispatch_row(record_dir: Path, export_dir: Path, repo: Path) -> tuple[dict[str, Any], int]:
    """Build one dispatch's row: identity, telemetry source, spend and landing.

    Returns the row and the malformed-line count its export file produced, so the
    caller can name the file without re-reading it.
    """
    plan = ledger.parse_dispatch_record(record_dir / DISPATCH_FILE).plan
    result = ledger.read_json(record_dir / RESULT_FILE)
    dispatch_id = str(plan.get("dispatch_id") or record_dir.name)
    export_path = export_dir / f"{EXPORT_PREFIX}{dispatch_id}{EXPORT_SUFFIX}"
    malformed = 0
    items: list[ledger.Item] = []
    ledger_row: Mapping[str, Any] | None = None
    if export_path.is_file():
        batches = read_export(export_path)
        malformed = batches.malformed
        items = [item for batch in batches.batches for item in ledger.items_for(batch, dispatch_id)]
        spend = read_spend(items)
        telemetry_source: str = SOURCE_EXPORT
        telemetry_path: str | None = export_path.name
        telemetry_path_reason: str | None = None
    elif (record_dir / LEDGER_FILE).is_file():
        # The pruned-source read: `ledger prune` only deletes a file a row was
        # materialised from, so where the file is gone the row is the surviving
        # record, taken visibly rather than silently.
        ledger_row = ledger.read_json(record_dir / LEDGER_FILE)
        spend = _row_spend(ledger_row)
        telemetry_source = SOURCE_LEDGER_ROW
        telemetry_path = None
        telemetry_path_reason = PRUNED_EXPORT_REASON
    else:
        spend = Spend(None, None, None, None, None, NO_TELEMETRY_REASON)
        telemetry_source = SOURCE_ABSENT
        telemetry_path = None
        telemetry_path_reason = NO_TELEMETRY_REASON
    issue = _issue_of(plan)
    landing = _landing_for(plan, issue, result, repo)
    started = ledger.dispatch_start(plan, result)
    end_state = _end_state_for(items, result, ledger_row, telemetry_source, export_path)
    outcome = (
        ledger.gate_outcome(landing, result, end_state, plan.get("seat")) if end_state else None
    )
    end_state_reason = None if end_state else ROW_NO_END_STATE
    lane = plan.get("lane") if isinstance(plan.get("lane"), str) else None
    profile = plan.get("profile") if isinstance(plan.get("profile"), str) else None
    seat = plan.get("seat") if isinstance(plan.get("seat"), str) else None
    row = {
        "dispatch_id": dispatch_id,
        "lane": lane,
        "lane_reason": None if lane else "the dispatch record carries no lane",
        "profile": profile,
        "profile_reason": None if profile else "the dispatch record carries no profile",
        "seat": seat,
        "seat_reason": None if seat else "the dispatch record carries no seat",
        "issue": issue,
        "issue_reason": None if issue else "the dispatch record names no usable issue number",
        "telemetry_source": telemetry_source,
        "telemetry_path": telemetry_path,
        "telemetry_path_reason": telemetry_path_reason,
        "spend_encoding": spend.encoding,
        "spend_encoding_reason": spend.reason,
        "input_tokens": spend.input_tokens,
        "input_tokens_reason": None if spend.input_tokens is not None else spend.reason,
        "output_tokens": spend.output_tokens,
        "output_tokens_reason": None if spend.output_tokens is not None else spend.reason,
        "cache_read_tokens": spend.cache_read_tokens,
        "cache_read_tokens_reason": (None if spend.cache_read_tokens is not None else spend.reason),
        "cache_creation_tokens": spend.cache_creation_tokens,
        "cache_creation_tokens_reason": (
            None if spend.cache_creation_tokens is not None else spend.reason
        ),
        "landed_sha": landing.sha,
        "landed_sha_reason": None if landing.sha else landing.reason,
        "started_at": started.isoformat() if started else None,
        "started_at_reason": None if started else NO_START_REASON,
        "end_state_class": end_state.class_ if end_state else None,
        "end_state_class_reason": end_state_reason,
        "gate_outcome": outcome,
        "gate_outcome_reason": None if outcome else end_state_reason,
    }
    return row, malformed


def _issue_cost_row(issue: int, lane: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate one (issue, lane) pair's dispatch rows into its cost row.

    Summing within a lane is the one sum the store performs — one meter, one issue,
    one currency — and it is the only one its shape can express. `spend_dispatches`
    beside `dispatches` keeps a partial read visible as partial rather than as
    small. The landing is whichever dispatch of the pair landed, newest named where
    one did, and the reason is the first dispatch's own when none did, because a
    ledger refusal already names which of the three tests answered.
    """
    shas = [str(row["landed_sha"]) for row in rows if row["landed_sha"]]
    with_spend = [row for row in rows if row["spend_encoding"] is not None]
    encodings = sorted({str(row["spend_encoding"]) for row in with_spend})
    encoding: str | None = None
    encoding_reason: str | None = None
    if len(encodings) == 1:
        encoding = encodings[0]
    elif len(encodings) > 1:
        encoding = ENCODING_MIXED
    else:
        # No dispatch of the pair carried derivable spend, so the row quotes the first
        # dispatch's own reason — a pruned log-record dispatch names the prune here,
        # where the generic string would falsely say no spend records ever existed.
        encoding_reason = str(
            next(
                (row["spend_encoding_reason"] for row in rows if row["spend_encoding_reason"]),
                "no dispatch of this issue on this lane carried spend records",
            )
        )
    row: dict[str, Any] = {
        "issue": issue,
        "lane": lane,
        "landed": bool(shas),
        "landed_sha": shas[0] if shas else None,
        "landed_sha_reason": (
            None
            if shas
            else str(rows[0]["landed_sha_reason"] or "no landing could be derived for this issue")
        ),
        "dispatches": len(rows),
        "spend_dispatches": len(with_spend),
        "spend_encoding": encoding,
        "spend_encoding_reason": encoding_reason,
    }
    for bucket in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
    ):
        if with_spend:
            row[bucket] = sum(int(r[bucket] or 0) for r in with_spend)
            row[f"{bucket}_reason"] = None
        else:
            row[bucket] = None
            row[f"{bucket}_reason"] = encoding_reason
    if lane == CLAUDE_LANE:
        row["meter"] = METER_CLAUDE
        row["calibration_id"] = ledger.CALIBRATION_ID
        row["calibration_id_reason"] = None
        if with_spend:
            row["cost"] = row["output_tokens"] / ledger.CLAUDE_TOKENS_PER_POINT["five_hour"]
            row["cost_reason"] = None
        else:
            row["cost"] = None
            row["cost_reason"] = encoding_reason
    else:
        row["meter"] = METER_UNCALIBRATED
        row["calibration_id"] = None
        row["calibration_id_reason"] = UNCALIBRATED_REASON
        row["cost"] = None
        row["cost_reason"] = UNCALIBRATED_REASON
    return row


def _commit_date(repo: Path, sha: str) -> str | None:
    """Read one landing commit's committer date, strictly ISO, or say nothing.

    Git owns commit dates; `ledger`'s runner is the project's one way to ask it. The
    empty string it returns on refusal becomes a null with a reason at the caller.
    """
    return ledger.git("show", "-s", "--format=%cI", sha, cwd=repo).strip() or None


def _work_item_state(outcomes: Sequence[str | None]) -> str:
    """Reduce one issue's dispatch outcomes to its work-item state, in preference order.

    A landing answers first; short of that, a dispatch still running keeps the item
    open however its siblings ended, because re-dispatched work is work in flight. Only
    with nothing running and nothing landed does a not-a-result outcome make the item
    abandoned, and the residue — every dispatch terminal, none landed, none a not-a-result
    — is `stopped`. An outcome the row could not derive counts as terminal here, and the
    dispatch row's own reason is where a reader learns why.
    """
    if STATE_LANDED in outcomes:
        return STATE_LANDED
    if "running" in outcomes:
        return STATE_OPEN
    if "not_a_result" in outcomes:
        return STATE_ABANDONED
    return STATE_STOPPED


def _work_item_row(issue: int, rows: Sequence[Mapping[str, Any]], repo: Path) -> dict[str, Any]:
    """Build one work item's row: its state, and the clock its lead time runs on.

    The clock's two points are named, not implied. It starts at the issue's earliest
    dispatch start — `ledger.dispatch_start`'s rule, the result's `started_at` where the
    run ended, else the plan's `planned_at` — and it ends at the committer date of the
    newest commit any dispatch of the issue landed. Time is the one quantity that is
    commensurable across lanes, so this is a per-issue row and never a per-lane one.
    """
    starts = sorted(str(row["started_at"]) for row in rows if row["started_at"])
    shas = {str(row["landed_sha"]) for row in rows if row["landed_sha"]}
    ends = sorted(filter(None, (_commit_date(repo, sha) for sha in shas)))
    clock_start = starts[0] if starts else None
    clock_end = ends[-1] if ends else None
    lead_time: int | None = None
    if clock_start is not None and clock_end is not None:
        lead_time = int(
            (
                datetime.fromisoformat(clock_end) - datetime.fromisoformat(clock_start)
            ).total_seconds()
        )
    return {
        "issue": issue,
        "state": _work_item_state([row["gate_outcome"] for row in rows]),
        "clock_start": clock_start,
        "clock_start_reason": None
        if clock_start
        else "no dispatch of this issue carries a start time",
        "clock_end": clock_end,
        "clock_end_reason": (
            None
            if clock_end
            else (
                "the landing commit's date could not be read from this checkout"
                if shas
                else "no dispatch of this issue landed a commit"
            )
        ),
        "lead_time_seconds": lead_time,
        "lead_time_seconds_reason": (
            None
            if lead_time is not None
            else "lead time needs both clock points and at least one is missing"
        ),
    }


def _iter_source_dir(root: Path, kind: str) -> tuple[Path, list[Path]] | Refusal:
    """Read one source directory's entries, or refuse naming it.

    The refusal criterion's whole body: a root that is not a readable directory is a
    named refusal and nothing is rebuilt, because a store built over an unseen source
    would be a partial rebuild presented as complete.
    """
    flag = f"--{kind.replace('_', '-')}"
    remedy = f"Point {flag} at the {kind} this process can read, or run from a session that can."
    if not root.is_dir():
        return Refusal(
            f"{kind}_unreadable",
            (f"path={root}", "not a readable directory"),
            remedy,
        )
    try:
        entries = sorted(root.iterdir())
    except OSError as error:
        return Refusal(f"{kind}_unreadable", (f"path={root}", f"error={error.strerror}"), remedy)
    return root, entries


def _work_items(
    rows: Sequence[Mapping[str, Any]], repo: Path
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Group the dispatch rows into one work item per issue, with the state counts.

    A work item is an issue, and its members are every dispatch row that names it,
    across every lane — time is the one quantity that commutes across lanes, so the
    group key is the issue alone.
    """
    by_issue: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if row["issue"] is not None:
            by_issue.setdefault(int(row["issue"]), []).append(row)
    items = [_work_item_row(issue, members, repo) for issue, members in sorted(by_issue.items())]
    counts = dict.fromkeys((STATE_LANDED, STATE_OPEN, STATE_ABANDONED, STATE_STOPPED), 0)
    for item in items:
        counts[str(item["state"])] += 1
    return items, counts


def rebuild(dispatch_root: Path, export_dir: Path, repo: Path, store_dir: Path) -> dict[str, Any]:
    """Rebuild the whole store from the sources, deterministically, in one pass.

    Every ordering in the output is a sorted ordering, nothing in it reads the wall
    clock, and the store file is rewritten whole — so two runs over the same inputs
    produce the same bytes. Refuses by name before writing anything if either source
    directory cannot be read.
    """
    dispatches_read = _iter_source_dir(dispatch_root, "dispatch_root")
    if isinstance(dispatches_read, Refusal):
        raise _RefusedError(dispatches_read)
    _, entries = dispatches_read
    export_read = _iter_source_dir(export_dir, "export_dir")
    if isinstance(export_read, Refusal):
        raise _RefusedError(export_read)

    rows: list[dict[str, Any]] = []
    malformed_files: dict[str, int] = {}
    for entry in entries:
        if not (entry / DISPATCH_FILE).is_file():
            continue
        row, malformed = _dispatch_row(entry, export_dir, repo)
        rows.append(row)
        if malformed:
            malformed_files[row["telemetry_path"] or entry.name] = malformed
    rows.sort(key=lambda row: str(row["dispatch_id"]))

    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in rows:
        issue, lane = row["issue"], row["lane"]
        if issue is None or lane is None:
            continue
        grouped.setdefault((issue, lane), []).append(row)
    issue_cost = [
        _issue_cost_row(issue, lane, members) for (issue, lane), members in grouped.items()
    ]
    issue_cost.sort(key=lambda row: (int(row["issue"]), str(row["lane"])))

    landed_issues = sorted(
        {int(row["issue"]) for row in issue_cost if row["landed"]}  # type: ignore[arg-type]
    )
    work_items, state_counts = _work_items(rows, repo)
    store = {
        "schema": SCHEMA,
        "inputs": {
            "dispatch_root": str(dispatch_root),
            "export_dir": str(export_dir),
            "repo": str(repo),
        },
        "coverage": {
            "dispatches": len(rows),
            "dispatches_with_telemetry": sum(
                1 for row in rows if row["telemetry_source"] == SOURCE_EXPORT
            ),
            "dispatches_from_ledger_rows": sum(
                1 for row in rows if row["telemetry_source"] == SOURCE_LEDGER_ROW
            ),
            "dispatches_with_spend": sum(1 for row in rows if row["spend_encoding"]),
            "dispatches_without_telemetry": [
                str(row["dispatch_id"]) for row in rows if row["telemetry_source"] == SOURCE_ABSENT
            ],
            "issues": len({row["issue"] for row in rows if row["issue"]}),
            "issues_with_landings": len(landed_issues),
            "work_items": len(work_items),
            "work_items_landed": state_counts[STATE_LANDED],
            "work_items_open": state_counts[STATE_OPEN],
            "work_items_abandoned": state_counts[STATE_ABANDONED],
            "work_items_stopped": state_counts[STATE_STOPPED],
            "malformed_lines": sum(malformed_files.values()),
        },
        "malformed": [
            {"file": name, "lines": malformed_files[name]} for name in sorted(malformed_files)
        ],
        "dispatches": rows,
        "issue_cost": issue_cost,
        "work_items": work_items,
    }
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / STORE_NAME).write_text(
        json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return store


class _RefusedError(Exception):
    """Carries a Refusal out of `rebuild` to the CLI boundary that prints it."""

    def __init__(self, refusal: Refusal) -> None:
        super().__init__(refusal.kind)
        self.refusal = refusal


# -------------------------------------------------------------------------- rendering


def summary_lines(store: Mapping[str, Any], store_dir: Path) -> tuple[str, ...]:
    """Render the rebuild's own account of itself: coverage, damage, and the answer.

    Deterministic by construction — the lines derive only from the store, in sorted
    order, so the idempotence claim covers stdout as well as the file.
    """
    coverage = store["coverage"]
    lines = [
        f"observatory store={store_dir / STORE_NAME}",
        " ".join(
            (
                "coverage",
                f"dispatches={coverage['dispatches']}",
                f"with_telemetry={coverage['dispatches_with_telemetry']}",
                f"from_ledger_rows={coverage['dispatches_from_ledger_rows']}",
                f"with_spend={coverage['dispatches_with_spend']}",
                f"issues={coverage['issues']}",
                f"issues_with_landings={coverage['issues_with_landings']}",
                f"malformed_lines={coverage['malformed_lines']}",
            )
        ),
    ]
    lines.extend(
        f"malformed file={entry['file']} lines={entry['lines']}" for entry in store["malformed"]
    )
    # The flow line carries counts only. Lead time's percentiles are a query against
    # `flow_lead_time` — the one rendering path for them — and this line cannot emit a
    # mean in their place because it emits no lead-time figure at all.
    lines.append(
        " ".join(
            (
                "flow",
                f"work_items={coverage['work_items']}",
                f"landed={coverage['work_items_landed']}",
                f"open={coverage['work_items_open']}",
                f"abandoned={coverage['work_items_abandoned']}",
                f"stopped={coverage['work_items_stopped']}",
            )
        )
    )
    for row in store["issue_cost"]:
        cost = row["cost"]
        # Three facts, three renderings: a number is a cost, `uncalibrated` names a
        # meter no calibration exists for, `absent` names a calibrated meter whose
        # spend could not be derived — a pruned source renders absent, never cheap and
        # never uncalibrated (#146's live row did exactly this).
        if isinstance(cost, (int, float)):
            rendered = f"{cost:.4f}"
        elif row["meter"] == METER_CLAUDE:
            rendered = "absent"
        else:
            rendered = "uncalibrated"
        lines.append(
            " ".join(
                (
                    f"issue={row['issue']}",
                    f"lane={row['lane']}",
                    f"landed={str(bool(row['landed'])).lower()}",
                    f"dispatches={row['dispatches']}",
                    f"spend_dispatches={row['spend_dispatches']}",
                    f"out={row['output_tokens'] if row['output_tokens'] is not None else 'none'}",
                    f"meter={row['meter']}",
                    f"cost={rendered}",
                )
            )
        )
    lines.append(f"ok=rebuilt dispatches={coverage['dispatches']}")
    return tuple(lines)


# ---------------------------------------------------------------------------- querying


def connect(store_dir: Path) -> sqlite3.Connection:
    """Open the shipped store as SQL, via the standard library.

    The tables are the store's own tables with their own column names, so the
    cookbook's queries are queries against the store and not against a translation of
    it. Nulls keep their reason siblings, because SQL is where an absence is most
    easily misread as a zero.
    """
    document = json.loads((store_dir / STORE_NAME).read_text(encoding="utf-8"))
    connection = sqlite3.connect(":memory:")
    for table, columns in (
        ("dispatches", DISPATCH_COLUMNS),
        ("issue_cost", ISSUE_COST_COLUMNS),
        ("work_items", WORK_ITEM_COLUMNS),
    ):
        names = ", ".join(columns)
        connection.execute(f"CREATE TABLE {table} ({names})")
        placeholders = ", ".join("?" * len(columns))
        loaded = [tuple(row.get(column) for column in columns) for row in document[table]]
        connection.executemany(
            f"INSERT INTO {table} ({names}) VALUES ({placeholders})",  # noqa: S608 — table and columns are this module's own constants, never input
            loaded,
        )
    connection.execute(FLOW_LEAD_TIME_VIEW)
    return connection


def query(store_dir: Path, sql: str) -> tuple[tuple[Any, ...], ...]:
    """Run one SQL statement against the shipped store and return its rows."""
    with connect(store_dir) as connection:
        return tuple(connection.execute(sql).fetchall())


# ------------------------------------------------------------------------------- main


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Read the command line, with the environment's twin for every path."""
    parser = argparse.ArgumentParser(description="The observatory store: rebuild and query.")
    parser.add_argument("action", nargs="?", default="rebuild", choices=("rebuild", "query"))
    parser.add_argument("sql", nargs="*", help="query: one SQL statement")
    parser.add_argument(
        "--dispatch-root",
        type=Path,
        default=Path(os.environ.get("CTI_DISPATCH_DIR", str(DEFAULT_DISPATCH_ROOT))),
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=Path(os.environ.get("CTI_OTEL_EXPORT_DIR", str(DEFAULT_EXPORT_DIR))),
    )
    parser.add_argument(
        "--store-dir",
        type=Path,
        default=Path(os.environ.get("CTI_OBSERVATORY_DIR", str(DEFAULT_STORE_DIR))),
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one action: rebuild the store, or query the one already shipped."""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.action == "query":
        if not args.sql:
            print("refused=no_sql action=Pass one SQL statement.")  # noqa: T201
            return EXIT_REFUSED
        try:
            rows = query(args.store_dir, " ".join(args.sql))
        except (OSError, ValueError, sqlite3.Error) as error:
            print(f"refused=query_failed error={error}")  # noqa: T201
            return EXIT_REFUSED
        for row in rows:
            print("|".join(str(value) for value in row))  # noqa: T201
        return 0
    try:
        store = rebuild(args.dispatch_root, args.export_dir, args.repo, args.store_dir)
    except _RefusedError as refused:
        for line in refused.refusal.lines():
            print(line, file=sys.stderr)  # noqa: T201
        return EXIT_REFUSED
    for line in summary_lines(store, args.store_dir):
        print(line)  # noqa: T201
    return 0


if __name__ == "__main__":  # pragma: no cover - the seam
    raise SystemExit(main())
