"""Merge N slots' worth of claims into the pool's one verdict set (#185, ADR-0049).

`spike/regress.sh` forks the workers, holds the locks and owns the flag files;
what their leftovers *mean* is a decision, so it is decided here, where pytest
can reach it (`tests/unit/test_pool_merge.py` pins the contracts). The merge
reads the claim directories back rather than any parent's memory, because the
case it must report honestly is a worker that died: its verdict was never
written, and an array in the parent would simply have no row for it.

What one claim means, in the order the shell applied it:

1. No claim directory: the probe never started. A Windows-host probe the
   client lock kept out is typed `infra_unavailable` rather than dropped —
   `not_run` carries no class, and a corpus that quietly dropped the two
   probes about the client would exit green having measured neither (#127).
   Anything else unclaimed is `not_run`.
2. A claim with no `verdict.json` is the dead-slot rule (ADR-0022): the worker
   died mid-probe, nothing was measured under conditions anyone can interpret,
   and reading the absence of evidence as a failure of the probe would be the
   untyped green this tier exists to refuse. The shell releases and reclaims
   the slot this home names — the merge decides, the shell acts.
3. Otherwise the verdict is what `verdict.json` says. A document that cannot
   be read, or reads without a class, is an untyped red — a harness bug, per
   the failure-class table's preamble.

The worst class ranks by *severity*, never by exit code: the exit codes in
`regress.sh`'s CLASS_RANK are stable names for table rows (#162), and the
classes added since #83 took the next free numbers. The mem-stop overlay
(#125) raises `infra_unavailable` at the pool level, because the whole point
of that stop is that no probe launched to carry the class.

Six riders travel with the merge because they read and write the same files
or the same table: `stop-decision` reads the workers' completion record and
asks `breaker.py` whether the pool's consecutive-crash rule trips (#72) — the
shell asks after every verdict and writes the stop flag it is told, while this
module owns only the record parsing and explanation — `prune-passes` decides
which old green evidence has outlived the retention convention (the shell does
the deleting),
`prune-pools` decides the same for pool directories off the `worst_class`
the merge itself records — verdict-aware because the count-only prune kept
`prune-interrupted` names verdict-less evidence beyond its recovery horizon,
no failed pools and the starvation episodes' RAM traces went with it (#182),
`fallback-verdict` writes the minimal `verdict.json` for a probe whose typer
failed (#171's call site) — the least the merge reads, so a slot that is fine
is not reclaimed as dead — and `class-of` validates the class an in-mission
FAIL line declared against the table below, where `run.sh` reads the line
(#147; the mapping was `class_of`, a bash sed with no notion of which classes
exist, and #161's routing sent it here rather than minting a parallel table).

Severity and the in-mission mapping are the class table's Python halves. Its
exit half (CLASS_RANK in `regress.sh`) stays in bash deliberately: the paths
that exit through it include the ones where `uv` itself is what broke, and an
exit code that must be produced when Python cannot run cannot be asked of
Python. Any further consolidation is #92's.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path.
sys.path.insert(0, str(Path(__file__).parent))

import breaker

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# The failure-class table, by how bad each row is. The summary sorts by this
# and the pool's exit is the worst class present; the numbers are ranks, not
# exit codes (#162 — CLASS_RANK's numbers stopped being an order when
# engine_drift and schema_stale took the next free codes).
CLASS_SEVERITY: Final[dict[str, int]] = {
    # The table preamble's "untyped red = harness bug", as a row of its own
    # (ADR-0050): worst of all, because a class nobody typed is a class nobody
    # can act on.
    "untyped_harness_failure": 90,
    "infra_unavailable": 80,
    "node_crashed": 70,
    "engine_drift": 60,
    "oracle_disagreement": 50,
    "schema_stale": 40,
    "timeout": 30,
    "assertion_failed": 20,
    "flake_quarantine": 0,  # runs, reports, does not gate
    "pass": 0,
}
UNTYPED_SEVERITY: Final = 90

# The classes an in-mission FAIL line may declare (#147): the table's rows
# minus the three no world code may claim. `pass` on a FAIL line would invert
# the verdict downstream; `untyped_harness_failure` is the harness's own word
# for a red nobody typed, never the world's; `flake_quarantine` is applied by
# the probe header's `quarantined:` line, and a world that could claim it
# would be a probe that quarantines itself past the open-issue policy.
MISSION_CLASSES: Final[frozenset[str]] = frozenset(CLASS_SEVERITY) - {
    "pass",
    "untyped_harness_failure",
    "flake_quarantine",
}


def severity(class_: str) -> int:
    """Rank one class; a class the table has never heard of is an untyped red."""
    return CLASS_SEVERITY.get(class_, UNTYPED_SEVERITY)


def mission_class(line: str) -> tuple[str, str]:
    """Validate the class an in-mission FAIL line declared, where it is read (#147).

    No declared class is still an assertion — the behaviour #23 kept — and the
    last `class=` token wins, as the old sed's greedy prefix read it. A class
    the table has never heard of (`class=timout`), or one no FAIL line may
    claim, is caught at this boundary as the harness bug it is rather than
    flowing to the far end of the tier as an unknown class.
    """
    declared = re.findall(r"class=([a-z_]+)", line)
    if not declared:
        return "assertion_failed", line
    if declared[-1] in MISSION_CLASSES:
        return declared[-1], line
    detail = (
        f"in-mission FAIL line declares class '{declared[-1]}', which no FAIL line "
        f"may carry — a wrong class is a harness bug (#83); line: {line}"
    )
    return "untyped_harness_failure", detail


def read_completion_record(record: Path) -> tuple[list[tuple[str, str]], str]:
    """Read the completion stream, or return the reason it cannot be trusted."""
    try:
        lines = record.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return (
            [],
            f"no completion record readable at {record} — stopping rather than running past it",
        )

    completions: list[tuple[str, str]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        name, separator, class_ = line.partition("\t")
        if not separator or not name.strip() or not class_.strip():
            return [], (
                f"the completion record is corrupt at line {number} ({line!r}) — "
                "stopping rather than reading past it"
            )
        completions.append((name.strip(), class_.strip()))
    return completions, ""


def crash_stop_line(names: Sequence[str], not_run: int | None = None) -> str:
    """Explain a corpus crash trip, optionally with its final not-run count."""
    line = (
        f"{breaker.CORPUS_CRASH_CLASS} in {', then '.join(names)} — abandoned after "
        f"{breaker.CORPUS_CRASH_RULE.consecutive} consecutive {breaker.CORPUS_CRASH_CLASS}"
    )
    if not_run is not None:
        line += f", {not_run} probe(s) not run"
    return line


def finalize_stop_line(stop_line: str, not_run: int) -> str:
    """Add the merged pool's final not-run count to a crash stop explanation."""
    line = flattened(stop_line)
    prefix = f"{breaker.CORPUS_CRASH_CLASS} in "
    if not line.startswith(prefix):
        return line
    line = re.sub(r", \d+ probe\(s\) not run$", "", line)
    return f"{line}, {not_run} probe(s) not run"


def read_stop_decision_failure(pool_out: Path) -> str | None:
    """Read the caller's typed stop-decision failure marker, if one exists."""
    marker = pool_out / "stop-decision-failure"
    if not marker.is_file():
        return None
    try:
        failure_class = marker.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return "untyped_harness_failure"
    if failure_class in {"infra_unavailable", "untyped_harness_failure"}:
        return failure_class
    return "untyped_harness_failure"


def crash_stop(record: Path, corpus_size: int, *, include_not_run: bool = True) -> tuple[bool, str]:
    """Answer whether the pool's consecutive-crash breaker trips, and say so how.

    The record is the workers' completion log — one `name<TAB>class` line per
    finished verdict, in completion order, which is the only order a pool has.
    The trip is any adjacent run of `breaker.py`'s corpus crash rule reaching
    its threshold; a verdict of any other class ends that run, but cannot hide
    a pair already found earlier in the record.

    Every answer the decision cannot read trips rather than runs on: a record
    that is missing or carries a line this module did not write is a harness
    fault at the one place that stands between the machine and the hammering,
    and the pool stopping is the readable direction (the caller writes the line
    it is given, so the reason is spelled where a reader acts on it). This is
    the same fail-closed shape ADR-0049 gives every call site it lands.

    The second half of the answer is the sentence for the stop flag, in the
    `infra_unavailable` break's own voice — the class named and the run that
    tripped it. The live decision can omit the not-run count because in-flight
    probes may still land; `run_merge` adds the final count after they drain.
    """
    completions, error = read_completion_record(record)
    if error:
        return True, error
    names = breaker.crash_stop(completions)
    if names is None:
        return False, ""
    left = corpus_size - len(completions) if include_not_run else None
    return True, crash_stop_line(names, left)


class ProbeRow(NamedTuple):
    """One probe's line in the merged verdict set."""

    probe: str
    class_: str
    slot: str
    elapsed_secs: int
    evidence: str


class MergedPool(NamedTuple):
    """The merge's whole answer: the rows, the leftovers, and what the shell does."""

    rows: list[ProbeRow]
    not_run: list[str]
    reclaim_slots: list[str]
    notices: list[str]
    worst_class: str


def read_verdict(path: Path) -> tuple[str, int]:
    """Read the class and elapsed seconds one `verdict.json` carries.

    A document that cannot be read or parsed, or whose fields are not the
    expected shapes, answers an empty class and zero seconds — the caller's
    untyped-red fallback, exactly where the old `sed` readers landed when
    nothing matched.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "", 0
    if not isinstance(document, dict):
        return "", 0
    class_ = document.get("class")
    elapsed = document.get("elapsed_secs")
    return (
        class_ if isinstance(class_, str) else "",
        elapsed if isinstance(elapsed, int) and not isinstance(elapsed, bool) else 0,
    )


def read_claim_line(path: Path, default: str) -> str:
    """One line a worker wrote into its claim, or the default the shell used."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return default


def merge_claims(  # noqa: PLR0913 — the pool facts the shell owns, one parameter apiece.
    corpus: list[str],
    claims_dir: Path,
    *,
    host_probes: frozenset[str],
    client_lock_blocked: bool,
    client_lock_evidence: str,
    mem_stopped: bool,
) -> MergedPool:
    """Apply the module docstring's reading to every probe of the corpus, in order."""
    rows: list[ProbeRow] = []
    not_run: list[str] = []
    reclaim_slots: list[str] = []
    notices: list[str] = []

    for name in corpus:
        claim = claims_dir / name
        if not claim.is_dir():
            if client_lock_blocked and name in host_probes:
                slot, class_, elapsed = "-", "infra_unavailable", 0
                evidence = client_lock_evidence
                notices.append(
                    f"{name} never ran: another run held the Windows client; not a result"
                )
            else:
                not_run.append(name)
                continue
        else:
            slot = read_claim_line(claim / "slot", default="?")
            evidence = read_claim_line(claim / "evidence", default="")
            if (
                not (claim / "done").is_file()
                or not evidence
                or not (Path(evidence) / "verdict.json").is_file()
            ):
                class_, elapsed = "infra_unavailable", 0
                notices.append(
                    f"slot {slot} claimed {name} and wrote no verdict — "
                    f"the worker died mid-probe; not a result (ADR-0022)"
                )
                if slot.isdigit():
                    reclaim_slots.append(slot)
            else:
                class_, elapsed = read_verdict(Path(evidence) / "verdict.json")
        rows.append(
            ProbeRow(
                name, class_ or "untyped_harness_failure", slot, elapsed, evidence or str(claim)
            )
        )

    worst_class = worst_of(rows)
    if mem_stopped and severity("infra_unavailable") > severity(worst_class):
        worst_class = "infra_unavailable"

    return MergedPool(rows, not_run, reclaim_slots, notices, worst_class)


def merged_from_pool(document: dict[str, object]) -> MergedPool:
    """Rebuild the merge's own answer from a `pool.json` written earlier.

    The one reader of the document this module writes, so that everything
    quoting a finished pool — the stall watcher's prod (#198), the issue
    comment a close carries (#199) — goes back through `render_summary` here
    rather than through a renderer of its own. Two readers of one schema is how
    two tables drift, and this is the schema's own module.

    The rows are believed as written. A record with no `worst_class` is left
    empty rather than derived, because what an empty one *means* differs by
    caller: a watcher refuses to guess, a renderer of an old record derives and
    says it derived. `worst_of` is that derivation, for the callers that want it.
    """
    verdicts = document.get("verdicts")
    rows = [
        ProbeRow(
            str(entry.get("probe", "")),
            str(entry.get("class", "")),
            str(entry.get("slot", "?")),
            int(entry.get("elapsed_secs", 0) or 0),
            str(entry.get("evidence", "")),
        )
        for entry in (verdicts if isinstance(verdicts, list) else [])
        if isinstance(entry, dict)
    ]
    not_run = document.get("not_run")
    return MergedPool(
        rows,
        [str(name) for name in not_run] if isinstance(not_run, list) else [],
        [],
        [],
        str(document.get("worst_class", "")),
    )


def worst_of(rows: Iterable[ProbeRow]) -> str:
    """Rank these rows by severity and answer the worst class present, `pass` over none."""
    worst = "pass"
    for row in rows:
        if severity(row.class_) > severity(worst):
            worst = row.class_
    return worst


def render_summary(
    merged: MergedPool, *, started_at: str, git_sha: str, slot_count: int
) -> list[str]:
    """Render the runner's own stderr summary, byte for byte: worst class first.

    Ties keep corpus order, which is the stable sort's answer and one the old
    `sort -rn` never promised anything better than.
    """
    lines = ["", f"[regress] ==== verdicts ({started_at}, sha {git_sha[:12]}, N={slot_count}) ===="]
    lines.extend(
        f"[regress] {row.probe:<20} {row.class_:<18} {row.elapsed_secs!s:>4}s  "
        f"slot {row.slot}  {row.evidence}"
        for row in sorted(merged.rows, key=lambda row: severity(row.class_), reverse=True)
    )
    if merged.not_run:
        lines.append(
            f"[regress] {len(merged.not_run)} probe(s) not run: {' '.join(merged.not_run)}"
        )
    return lines


def flattened(text: str) -> str:
    """One line out of maybe-many, the way the shell's `json_string` read them."""
    return text.rstrip("\n").replace("\t", " ").replace("\n", " ")


def pool_document(  # noqa: PLR0913 — pool.json's fields, one parameter apiece.
    merged: MergedPool,
    *,
    started_at: str,
    git_sha: str,
    slots: list[int],
    host: str,
    wall_secs: int,
    peak_mem_used_kb: int,
    peak_tier_rss_kb: int,
    peak_pool_rss_kb: int,
    least_mem_available_kb: int,
    stopped_early: str,
    dirty_slots: list[tuple[int, str]],
) -> dict[str, object]:
    """Build the `pool.json` document, keys in the order the shell always wrote them.

    A verdict's `slot` is a string here — it can be `-` (never ran) or `?`
    (nobody recorded it) — where each probe's own `verdict.json` carries a
    number; both suites read the two shapes as they are.
    """
    return {
        "started_at": started_at,
        "git_sha": git_sha,
        "slots": slots,
        "host": host,
        # The merge's own answer, mem-stop overlay included, recorded so the
        # run's outcome survives in its evidence rather than only in an exit
        # code nobody kept — and so the pool pruner can tell a green pool from
        # one an open issue still needs (#182).
        "worst_class": merged.worst_class,
        "wall_secs": wall_secs,
        "peak_mem_used_kb": peak_mem_used_kb,
        "peak_tier_rss_kb": peak_tier_rss_kb,
        # The tier figure is machine-wide by design — the right scope for a
        # ceiling question — and this is the pool's own share of it (#182,
        # #125's open box), so a peak can be read without reconstructing which
        # sibling pools shared the night.
        "peak_pool_rss_kb": peak_pool_rss_kb,
        "least_mem_available_kb": least_mem_available_kb,
        "stopped_early": flattened(stopped_early),
        # A slot this run held, could not clear, and therefore never used.
        # Typed, because "the pool ran at N=2" and "the pool ran at N=2 because
        # slot 1 still had a dead run's server on its ports" are different
        # facts and only the second one is actionable.
        "dirty_slots": [
            {"slot": slot, "class": "infra_unavailable", "detail": flattened(detail)}
            for slot, detail in dirty_slots
        ],
        "not_run": merged.not_run,
        "verdicts": [
            {
                "probe": row.probe,
                "class": row.class_,
                "slot": row.slot,
                "elapsed_secs": row.elapsed_secs,
                "evidence": row.evidence,
            }
            for row in merged.rows
        ],
    }


def prune_candidates(runs_dir: Path, probe: str, keep: int) -> list[Path]:
    """Name the old green evidence directories that have outlived retention.

    Room is left for the pass the caller's run is about to write, which is
    what makes "the last `keep` passes" the count a reader finds afterwards.
    Only a directory whose `verdict.json` reads as a PASS is ever a candidate:
    failures are kept until the issue that consumed them closes, and a verdict
    that cannot be read is evidence the pruner has no business deciding on.
    The shell does the deleting — this only decides.
    """
    passes: list[Path] = []
    evidence_name = re.compile(rf"^\d{{8}}T\d{{6}}Z-{re.escape(probe)}$")
    for verdict_json in sorted(runs_dir.glob(f"*-{probe}/verdict.json")):
        if evidence_name.fullmatch(verdict_json.parent.name) is None:
            continue
        try:
            document = json.loads(verdict_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (
            isinstance(document, dict)
            and document.get("probe") == probe
            and document.get("verdict") == "PASS"
        ):
            passes.append(verdict_json.parent)
    room = keep - 1
    if len(passes) <= room:
        return []
    return passes[: len(passes) - room]


def prune_interrupted_candidates(
    runs_dir: Path, *, older_than: timedelta, now: datetime
) -> list[Path]:
    """Name interrupted run directories older than a recovery horizon.

    ADR-0022 gives a directory without a verdict no result semantics. The
    timestamped directory name proves its age without trusting mutable file
    metadata; recent holders and unrelated directories are never candidates.
    """
    interrupted: list[Path] = []
    run_name = re.compile(r"^(?P<stamp>\d{8}T\d{6}Z)-.+$")
    deadline = now - older_than
    for directory in sorted(runs_dir.iterdir()):
        match = run_name.fullmatch(directory.name)
        if (
            not directory.is_dir()
            or match is None
            or (directory / "verdict.json").exists()
            or (directory / "pool.json").exists()
        ):
            continue
        started = datetime.strptime(match.group("stamp"), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if started <= deadline:
            interrupted.append(directory)
    return interrupted


def pool_reads_green(document: object) -> bool:
    """Decide whether this `pool.json` records a run whose worst class was `pass`.

    Documents since #182 carry `worst_class` — the merge's own answer, mem-stop
    overlay included — and it is believed as written. Older ones are derived
    from their verdicts, with a non-empty `stopped_early` read as not green:
    those runs' mem-stop overlay lived only in the exit code, and a pool that
    stopped early is not a pool whose record says green. Anything unreadable or
    shapeless is not green, because the pruner fails closed on it.
    """
    if not isinstance(document, dict):
        return False
    worst = document.get("worst_class")
    if isinstance(worst, str) and worst:
        return worst == "pass"
    if document.get("stopped_early"):
        return False
    verdicts = document.get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        return False
    classes = [row.get("class") for row in verdicts if isinstance(row, dict)]
    if len(classes) != len(verdicts) or not all(isinstance(c, str) for c in classes):
        return False
    return all(severity(c) <= CLASS_SEVERITY["pass"] for c in classes)


def prune_pool_candidates(runs_dir: Path, keep: int) -> list[Path]:
    """Name the green pool directories that have outlived retention (#182).

    The old prune was count-only, so it kept no failed pools: the starvation
    episodes' primary RAM traces were pruned while the issues that needed them
    were still open (#182's filing, finding 3). Only a pool whose own record
    reads green is ever a candidate — a failure is kept until the issue that
    consumed it closes, and a directory whose `pool.json` cannot be read, or
    that never got one (a run that died before its merge), is evidence the
    pruner has no business deciding on. Room is left for the pool the caller's
    run is about to record, as `prune_candidates` leaves it for the pass.
    """
    greens: list[Path] = []
    for pool_json in sorted(runs_dir.glob("*-pool/pool.json")):
        try:
            document = json.loads(pool_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if pool_reads_green(document):
            greens.append(pool_json.parent)
    room = keep - 1
    if len(greens) <= room:
        return []
    return greens[: len(greens) - room]


def fallback_document(
    probe: str, class_: str, detail: str, elapsed_secs: int, evidence: str
) -> dict[str, object]:
    """Build the least the merge reads, for a probe whose typer failed (#171).

    Without it the merge would read the probe as a dead worker and reclaim a
    slot that is fine. The class itself is decided at the shell's call site —
    ADR-0049's own mechanics: a typer `timeout` killed is `infra_unavailable`,
    a typer that ran and failed is `untyped_harness_failure`.
    """
    return {
        "probe": probe,
        "verdict": "FAIL",
        "class": class_,
        "detail": detail,
        "elapsed_secs": elapsed_secs,
        "evidence": evidence,
    }


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Six doors: the merge, and the riders that share its files or its table."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    merge = commands.add_parser("merge", help="one verdict set out of N slots' claims")
    merge.add_argument("--pool-out", required=True, type=Path)
    merge.add_argument("--corpus", required=True, nargs="+")
    merge.add_argument("--host-probes", nargs="*", default=[])
    merge.add_argument("--client-lock-blocked", choices=("0", "1"), default="0")
    merge.add_argument("--client-lock-evidence", default="")
    merge.add_argument("--started-at", required=True)
    merge.add_argument("--git-sha", required=True)
    merge.add_argument("--host", required=True)
    merge.add_argument("--slots", required=True, nargs="+", type=int)
    merge.add_argument("--wall-secs", required=True, type=int)
    merge.add_argument("--peak-mem-used-kb", required=True, type=int)
    merge.add_argument("--peak-tier-rss-kb", required=True, type=int)
    merge.add_argument("--peak-pool-rss-kb", required=True, type=int)
    merge.add_argument("--least-mem-available-kb", required=True, type=int)
    merge.add_argument("--dirty-slot", action="append", default=[], metavar="SLOT:DETAIL")

    prune = commands.add_parser("prune-passes", help="name the green evidence past retention")
    prune.add_argument("--runs-dir", required=True, type=Path)
    prune.add_argument("--probe", required=True)
    prune.add_argument("--keep", required=True, type=int)

    prune_pools = commands.add_parser(
        "prune-pools", help="name the green pool directories past retention"
    )
    prune_pools.add_argument("--runs-dir", required=True, type=Path)
    prune_pools.add_argument("--keep", required=True, type=int)

    prune_interrupted = commands.add_parser(
        "prune-interrupted", help="name interrupted evidence past its recovery horizon"
    )
    prune_interrupted.add_argument("--runs-dir", required=True, type=Path)
    prune_interrupted.add_argument("--older-than-days", required=True, type=int)

    fallback = commands.add_parser(
        "fallback-verdict", help="write the minimal verdict.json for a failed typer"
    )
    fallback.add_argument("--probe", required=True)
    fallback.add_argument("--class", dest="class_", required=True)
    fallback.add_argument("--detail", required=True)
    fallback.add_argument("--elapsed", required=True, type=int)
    fallback.add_argument("--evidence", required=True)
    fallback.add_argument("--verdict-json", required=True, type=Path)

    class_of = commands.add_parser(
        "class-of", help="validate the class an in-mission FAIL line declared"
    )
    class_of.add_argument("--line", required=True)

    stop = commands.add_parser(
        "stop-decision",
        help="whether the pool's consecutive-crash breaker trips (#72)",
    )
    stop.add_argument("--record", required=True, type=Path)
    stop.add_argument("--corpus-size", required=True, type=int)

    return parser.parse_args(argv)


def split_dirty(values: list[str]) -> list[tuple[int, str]]:
    """Parse `SLOT:DETAIL` pairs as the shell passes them.

    A slot that is not a number is plumbing that lost a fact, and fails loudly
    rather than landing in the record with a hole in it.
    """
    dirty: list[tuple[int, str]] = []
    for value in values:
        slot, sep, detail = value.partition(":")
        if not sep or not slot.isdigit():
            message = f"--dirty-slot takes SLOT:DETAIL with a numeric slot, got: {value!r}"
            raise SystemExit(message)
        dirty.append((int(slot), detail))
    return dirty


def run_merge(args: argparse.Namespace) -> int:
    """Merge, write `pool.json`, print the lines the shell acts on."""
    pool_out: Path = args.pool_out
    claims_dir = pool_out / "claims"
    if not claims_dir.is_dir():
        # A merge pointed somewhere the pool never wrote would read every probe
        # as not_run and hand back a green worst class — the one wrong
        # invocation that must stop instead (the call site fails closed).
        print(f"[pool-merge] no claims directory at {claims_dir}", file=sys.stderr)  # noqa: T201
        return 2
    merged = merge_claims(
        args.corpus,
        claims_dir,
        host_probes=frozenset(args.host_probes),
        client_lock_blocked=args.client_lock_blocked == "1",
        client_lock_evidence=args.client_lock_evidence,
        mem_stopped=(pool_out / "mem-stop").is_file(),
    )
    stop_failure = read_stop_decision_failure(pool_out)
    if stop_failure:
        merged = merged._replace(
            notices=[
                *merged.notices,
                f"the stop decision failed as {stop_failure} — the pool is not a result",
            ],
            worst_class=(
                stop_failure
                if severity(stop_failure) >= severity(merged.worst_class)
                else merged.worst_class
            ),
        )
    for notice in merged.notices:
        print(f"[regress] {notice}", file=sys.stderr)  # noqa: T201
    for line in render_summary(
        merged, started_at=args.started_at, git_sha=args.git_sha, slot_count=len(args.slots)
    ):
        print(line, file=sys.stderr)  # noqa: T201

    try:
        stopped_early = (pool_out / "stop").read_text(encoding="utf-8")
    except OSError:
        stopped_early = ""
    final_stopped_early = finalize_stop_line(stopped_early, len(merged.not_run))
    if final_stopped_early != flattened(stopped_early):
        (pool_out / "stop").write_text(final_stopped_early + "\n", encoding="utf-8")
    stopped_early = final_stopped_early
    document = pool_document(
        merged,
        started_at=args.started_at,
        git_sha=args.git_sha,
        slots=args.slots,
        host=args.host,
        wall_secs=args.wall_secs,
        peak_mem_used_kb=args.peak_mem_used_kb,
        peak_tier_rss_kb=args.peak_tier_rss_kb,
        peak_pool_rss_kb=args.peak_pool_rss_kb,
        least_mem_available_kb=args.least_mem_available_kb,
        stopped_early=stopped_early,
        dirty_slots=split_dirty(args.dirty_slot),
    )
    (pool_out / "pool.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    if stopped_early:
        print(f"stopped_early={stopped_early}")  # noqa: T201 — the shell refreshes the stop flag
    print(f"worst_class={merged.worst_class}")  # noqa: T201 — the shell reads these lines
    for slot in merged.reclaim_slots:
        print(f"reclaim_slot={slot}")  # noqa: T201 — the shell releases and reclaims
    return 0


def run_prune(args: argparse.Namespace) -> int:
    """Print one doomed directory per line; the shell logs and deletes."""
    for directory in prune_candidates(args.runs_dir, args.probe, args.keep):
        print(directory)  # noqa: T201 — the shell reads these lines
    return 0


def run_prune_interrupted(args: argparse.Namespace) -> int:
    """Print interrupted directories old enough that no holder can still own them."""
    for directory in prune_interrupted_candidates(
        args.runs_dir,
        older_than=timedelta(days=args.older_than_days),
        now=datetime.now(UTC),
    ):
        print(directory)  # noqa: T201 — the shell reads these lines
    return 0


def run_prune_pools(args: argparse.Namespace) -> int:
    """Print one doomed pool directory per line; the shell logs and deletes."""
    for directory in prune_pool_candidates(args.runs_dir, args.keep):
        print(directory)  # noqa: T201 — the shell reads these lines
    return 0


def run_fallback(args: argparse.Namespace) -> int:
    """Write the fallback `verdict.json` — the heredoc's one home now."""
    document = fallback_document(args.probe, args.class_, args.detail, args.elapsed, args.evidence)
    args.verdict_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return 0


def run_class_of(args: argparse.Namespace) -> int:
    """Print the validated class and detail; `run.sh`'s `fail` records them."""
    class_, detail = mission_class(args.line)
    print(f"class={class_}")  # noqa: T201 — the shell reads these lines
    print(f"detail={flattened(detail)}")  # noqa: T201 — the shell reads these lines
    return 0


def run_stop_decision(args: argparse.Namespace) -> int:
    """Print the breaker's answer; the worker writes the stop flag it is told."""
    trip, stop_line = crash_stop(args.record, args.corpus_size, include_not_run=False)
    print(f"trip={'yes' if trip else 'no'}")  # noqa: T201 — the shell reads these lines
    if stop_line:
        print(f"stop_line={flattened(stop_line)}")  # noqa: T201 — the shell reads a line
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch on the subcommand."""
    args = parse_args(argv)
    handlers = {
        "merge": run_merge,
        "prune-passes": run_prune,
        "prune-interrupted": run_prune_interrupted,
        "prune-pools": run_prune_pools,
        "fallback-verdict": run_fallback,
        "class-of": run_class_of,
        "stop-decision": run_stop_decision,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
