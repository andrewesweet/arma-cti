"""`just observatory`: the observatory store (#482, spec #478, ADR-0071 ruling 6).

A derived store over the work system, rebuilt in full from the immutable sources on
every run, answering one question end to end: **what a landed issue cost, per lane,
in that lane's own meter.** It reads and never writes the OTel bus, and it reports
rather than routes — nothing here excludes a profile, reroutes work or trips a
breaker.

- **The store is a cache and never a source of truth.** Every run rebuilds it from
  the durable per-dispatch OTel export and the dispatch records, whole, with no
  incremental append and no migration path. A schema change is a re-run. The output
  is deterministic: no wall-clock, no ordering but the sorted one, no mtimes — two
  runs over the same inputs produce the same bytes (#504).
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
  marked **uncalibrated** — absent and cheap are different facts, and a lane at zero
  must be impossible to confuse with a lane that is cheap.
- **Every null carries a reason.** A column that cannot be derived says why, in a
  sibling `<column>_reason` key that is non-null exactly when its column is null —
  the `cap_fraction` pattern, applied store-wide.
- **Malformed input is counted and named, not swallowed and not fatal.** A truncated
  JSON line in the export increments a counter naming its file, the rebuild
  completes, and the count appears in the output (#496, #503).

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
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path — the device `ledger.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

import ledger

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

SCHEMA: Final = "cti.observatory/1"
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

NO_TELEMETRY_REASON: Final = "no per-dispatch OTel export file exists for this dispatch"
NO_TOKEN_RECORDS_REASON: Final = (
    "the export file carries no token records in either encoding — no token metric "  # noqa: S105 — a reason string, not a secret; the name carries "token" because the absence it names is of token records
    "and no token-bearing log record"
)

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
)

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
    if export_path.is_file():
        batches = read_export(export_path)
        malformed = batches.malformed
        items = [item for batch in batches.batches for item in ledger.items_for(batch, dispatch_id)]
        spend = read_spend(items)
        telemetry_path: str | None = export_path.name
        telemetry_path_reason: str | None = None
    else:
        spend = Spend(None, None, None, None, None, NO_TELEMETRY_REASON)
        telemetry_path = None
        telemetry_path_reason = NO_TELEMETRY_REASON
    issue = _issue_of(plan)
    landing = _landing_for(plan, issue, result, repo)
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
        "telemetry_source": SOURCE_EXPORT if telemetry_path else SOURCE_ABSENT,
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
        encoding_reason = (
            with_spend[0]["spend_encoding_reason"]
            if with_spend and with_spend[0]["spend_encoding_reason"]
            else "no dispatch of this issue on this lane carried spend records"
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
            "dispatches_with_spend": sum(1 for row in rows if row["spend_encoding"]),
            "dispatches_without_telemetry": [
                str(row["dispatch_id"]) for row in rows if row["telemetry_source"] == SOURCE_ABSENT
            ],
            "issues": len({row["issue"] for row in rows if row["issue"]}),
            "issues_with_landings": len(landed_issues),
            "malformed_lines": sum(malformed_files.values()),
        },
        "malformed": [
            {"file": name, "lines": malformed_files[name]} for name in sorted(malformed_files)
        ],
        "dispatches": rows,
        "issue_cost": issue_cost,
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
    for row in store["issue_cost"]:
        cost = row["cost"]
        rendered = f"{cost:.4f}" if isinstance(cost, (int, float)) else "uncalibrated"
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
    ):
        names = ", ".join(columns)
        connection.execute(f"CREATE TABLE {table} ({names})")
        placeholders = ", ".join("?" * len(columns))
        loaded = [tuple(row.get(column) for column in columns) for row in document[table]]
        connection.executemany(
            f"INSERT INTO {table} ({names}) VALUES ({placeholders})",  # noqa: S608 — table and columns are this module's own constants, never input
            loaded,
        )
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
