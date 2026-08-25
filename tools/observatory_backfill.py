"""Historical landing reconciliation for ``just observatory backfill`` (#572).

The observatory's Git fallback is deliberately constrained by a one-sided floor, but
a bare issue list in a commit message can still be either prose or a landing attribution.
This command
reconciles the old rows once, using two independent records of a real landing:

* the audit comment posted by ``just land``, which names the pushed SHA; and
* a landing-capable dispatch record whose base supplies an ancestry floor and whose
  start supplies a committer-date floor for that SHA. There is deliberately no end
  ceiling; this inherits the one-sided landing bound used by ``ledger.landed``.

Only an exact landing line from the audit is accepted. A current projection row is
never evidence of its own landing: that is how #575's false row could otherwise
converge into a seemingly successful backfill. A closed issue with no recoverable
evidence gets a subject-only landing journal event, which makes the observatory keep
the unresolved reason instead of asking Git's prose derivation again. An open issue is
reported as not landed and is left alone.

The command writes only the review journal. It never writes the committed projection;
the normal ``just observatory`` rebuild does that only in the orchestrator's checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

import attribute_registry
import ledger
import observatory
import otel_event

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence


GH_TIMEOUT_SECONDS: Final = 60
EXIT_REFUSED: Final = 1
BACKFILL_RESOURCE: Final = "arma-cti-observatory-backfill"
BACKFILL_DETAIL_PREFIX: Final = observatory.BACKFILL_DETAIL_PREFIX
TRACKER_STATE_CLOSED: Final = "CLOSED"

# These are the two exact success forms emitted by ``just land``. The patterns are
# line-anchored and reject blockquotes, so a later review quoting an earlier landing
# output is not silently promoted to a new audit. The short SHA is resolved against
# this checkout before it enters a journal.
AUDIT_NOTE_PATTERN: Final = re.compile(
    r"^Landed on `origin/main` as `(?P<sha>[0-9a-fA-F]{7,40})`\.$", re.MULTILINE
)
AUDIT_PUSH_PATTERN: Final = re.compile(
    r"^pushed=(?P<sha>[0-9a-fA-F]{7,40}) origin/main$", re.MULTILINE
)
FULL_SHA_PATTERN: Final = re.compile(r"^[0-9a-f]{40}$")


class BackfillError(RuntimeError):
    """A source or write boundary that cannot answer safely."""


class AuditCandidate(NamedTuple):
    """One exact SHA line from one tracker comment, without carrying comment prose."""

    abbreviated_sha: str
    comment_id: str
    comment_at: datetime | None
    order: int


class ResolvedCandidate(NamedTuple):
    """An audit candidate accepted under origin and dispatch ancestry/start floors."""

    sha: str
    at: float
    evidence: str


class DispatchWindow(NamedTuple):
    """The dispatch's ancestry floor and committer-date floor, with no end ceiling."""

    dispatch_id: str
    base_sha: str
    started_at: datetime


class BackfillPaths(NamedTuple):
    """The source roots a reconciliation reads and the review root it writes."""

    dispatch_root: Path
    export_dir: Path
    review_root: Path
    spool: Path
    repo: Path
    queue_root: Path


class TrackerSnapshot(NamedTuple):
    """The one tracker read used by a backfill: issue state and all comments."""

    states: Mapping[int, str]
    comments: Mapping[int, tuple[Mapping[str, object], ...]]


class BackfillOutcome(NamedTuple):
    """One issue's reconciliation result, rendered without tracker comment prose."""

    issue: int
    status: str
    reason: str
    shas: tuple[str, ...] = ()


FetchTracker = Callable[[Path], TrackerSnapshot]


def _timestamp(value: object) -> datetime | None:
    """Parse a tracker timestamp, or leave the audit candidate without one."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def audit_candidates(comments: Iterable[Mapping[str, object]]) -> tuple[AuditCandidate, ...]:
    """Extract only the two exact ``just land`` success lines from comments.

    The body is deliberately not returned. The source proves a SHA through its
    production marker; surrounding audit prose is content for review, not an input to
    a parser. A comment with no usable timestamp remains a candidate and is ordered by
    the API's order; the commit date supplies the journal event's instant later.
    """
    found: list[AuditCandidate] = []
    for order, comment in enumerate(comments):
        body = comment.get("body")
        if not isinstance(body, str):
            continue
        comment_id = str(comment.get("id") or order)
        comment_at = _timestamp(comment.get("created_at"))
        found.extend(
            AuditCandidate(match.group("sha").lower(), comment_id, comment_at, order)
            for pattern in (AUDIT_NOTE_PATTERN, AUDIT_PUSH_PATTERN)
            for match in pattern.finditer(body)
        )
    return tuple(found)


def _json_lines(repo: Path, endpoint: str) -> tuple[Mapping[str, object], ...]:
    """Read one paginated GitHub JSON collection, refusing malformed transport output."""
    try:
        completed = subprocess.run(  # noqa: S603 — fixed gh argv, no shell, repo is cwd
            [  # noqa: S607 — gh resolves from PATH as the repository command surface requires
                "gh",
                "api",
                endpoint,
                "--paginate",
                "--jq",
                ".[] | @json",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as missing:
        message = "gh is not on PATH"
        raise BackfillError(message) from missing
    except subprocess.TimeoutExpired as slow:
        message = f"gh did not answer within {GH_TIMEOUT_SECONDS}s"
        raise BackfillError(message) from slow
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"gh exited {completed.returncode}"
        message = f"gh could not read {endpoint}: {detail.splitlines()[0]}"
        raise BackfillError(message)
    documents: list[Mapping[str, object]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as broken:
            message = f"gh returned malformed JSON Lines: {broken}"
            raise BackfillError(message) from broken
        if not isinstance(value, dict):
            message = "gh returned a collection member that was not an object"
            raise BackfillError(message)
        documents.append(value)
    return tuple(documents)


def fetch_tracker(repo: Path) -> TrackerSnapshot:
    """Read all issue states and comments in two bounded, paginated calls."""
    issue_documents = _json_lines(
        repo,
        "repos/{owner}/{repo}/issues?state=all&per_page=100",
    )
    states: dict[int, str] = {}
    for document in issue_documents:
        number = document.get("number")
        state = document.get("state")
        if isinstance(number, int) and not isinstance(number, bool) and isinstance(state, str):
            states[number] = state.upper()

    comments_by_issue: dict[int, list[Mapping[str, object]]] = defaultdict(list)
    comment_documents = _json_lines(repo, "repos/{owner}/{repo}/issues/comments?per_page=100")
    for document in comment_documents:
        issue_url = document.get("issue_url")
        if not isinstance(issue_url, str):
            message = "gh returned a comment without its issue URL"
            raise BackfillError(message)
        raw_issue = issue_url.rstrip("/").rsplit("/", 1)[-1]
        if not raw_issue.isdecimal():
            message = f"gh returned an issue URL without a number: {issue_url}"
            raise BackfillError(message)
        comments_by_issue[int(raw_issue)].append(document)
    return TrackerSnapshot(
        states, {issue: tuple(rows) for issue, rows in comments_by_issue.items()}
    )


def _issue_number(plan: Mapping[str, object]) -> int | None:
    """Read a dispatch plan's issue without turning untrusted input into an exception."""
    value = plan.get("issue")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def dispatch_windows(dispatch_root: Path, issue: int) -> tuple[DispatchWindow, ...]:
    """Read every landing-capable dispatch window for one issue."""
    try:
        entries = sorted(dispatch_root.iterdir(), key=lambda path: path.name)
    except OSError as failure:
        message = f"dispatch root could not be read: {failure}"
        raise BackfillError(message) from failure
    windows: list[DispatchWindow] = []
    for entry in entries:
        if not entry.is_dir():
            continue
        record = entry / "dispatch.json"
        if not record.is_file():
            continue
        parsed = ledger.parse_dispatch_record(record)
        plan = parsed.plan
        if _issue_number(plan) != issue or ledger.seat_shape(plan.get("seat")) != "work":
            continue
        result, _ = ledger.read_json(entry / "result.json")
        started_at = ledger.dispatch_start(plan, result)
        base_sha = plan.get("base_sha")
        if not isinstance(base_sha, str) or not base_sha or started_at is None:
            continue
        windows.append(
            DispatchWindow(str(plan.get("dispatch_id") or entry.name), base_sha, started_at)
        )
    return tuple(windows)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one local Git read, keeping its refusal at the reconciliation boundary."""
    try:
        return subprocess.run(  # noqa: S603 — fixed git executable, no shell
            ["git", *args],  # noqa: S607 — git resolves from PATH as the repository authority
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as failure:
        message = f"git could not run: {failure}"
        raise BackfillError(message) from failure


def _resolve_commit(repo: Path, abbreviated_sha: str) -> str | None:
    """Resolve an audit SHA only as a commit object in this checkout."""
    completed = _git(repo, "rev-parse", "--verify", "--quiet", f"{abbreviated_sha}^{{commit}}")
    resolved = completed.stdout.strip().lower()
    return resolved if completed.returncode == 0 and FULL_SHA_PATTERN.fullmatch(resolved) else None


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    """Ask Git whether one commit is an ancestor, without reading its prose."""
    return _git(repo, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0


def _commit_time(repo: Path, sha: str) -> datetime | None:
    """Read the commit's committer instant in Git's strict ISO form."""
    completed = _git(repo, "show", "-s", "--format=%cI", sha)
    if completed.returncode != 0:
        return None
    return _timestamp(completed.stdout.strip())


def resolve_candidate(  # noqa: PLR0911 — one return per rung of the evidence ladder
    repo: Path,
    issue: int,
    candidate: AuditCandidate,
    windows: Sequence[DispatchWindow],
) -> tuple[ResolvedCandidate | None, str]:
    """Accept an audit SHA only when origin and one dispatch window's floors attest it."""
    resolved = _resolve_commit(repo, candidate.abbreviated_sha)
    if resolved is None:
        return None, f"audit SHA {candidate.abbreviated_sha} is not an unambiguous commit"
    origin = _git(repo, "rev-parse", "--verify", "--quiet", "origin/main^{commit}")
    origin_sha = origin.stdout.strip().lower()
    if origin.returncode != 0 or not FULL_SHA_PATTERN.fullmatch(origin_sha):
        return None, "origin/main is not a readable commit in this checkout"
    if not _is_ancestor(repo, resolved, origin_sha):
        return None, f"audit SHA {resolved} is not on origin/main"
    committed_at = _commit_time(repo, resolved)
    if committed_at is None:
        return None, f"committer date for audit SHA {resolved} is unreadable"
    if not windows:
        return None, f"issue #{issue} has no landing-capable dispatch window"
    for window in windows:
        if _is_ancestor(
            repo, window.base_sha, resolved
        ) and committed_at >= window.started_at.replace(microsecond=0):
            at = (
                candidate.comment_at.timestamp()
                if candidate.comment_at
                else committed_at.timestamp()
            )
            return ResolvedCandidate(
                resolved,
                at,
                f"comment={candidate.comment_id} dispatch={window.dispatch_id}",
            ), ""
    return None, f"audit SHA {resolved} is outside every dispatch base/start floor"


def _journal_state(path: Path, issue: int) -> tuple[set[str], bool]:
    """Read valid existing produced relations and whether this issue has any event."""
    if not path.is_file():
        return set(), False
    produced: set[str] = set()
    has_event = False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as failure:
        message = f"landing journal {path} could not be read: {failure}"
        raise BackfillError(message) from failure
    for line in lines:
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            not isinstance(document, dict)
            or document.get("event") != attribute_registry.LANDING_EVENT
        ):
            continue
        attributes = document.get("attributes")
        if not isinstance(attributes, dict):
            continue
        relations = attribute_registry.relations_from_attributes(attributes)
        if relations is None or attributes.get("cti.issue") != issue:
            continue
        has_event = True
        produced.update(
            named.object_id
            for named in relations
            if named.qualifier == "produced" and named.object_type == "commit"
        )
    return produced, has_event


def _append_event(
    review_root: Path,
    issue: int,
    relations: Sequence[attribute_registry.Relation],
    at: float,
    reason: str,
) -> None:
    """Append one backfill event without exporting a historical landing as a new event."""
    event = attribute_registry.landing_event(relations, at)._replace(
        resource={"service.name": BACKFILL_RESOURCE}
    )
    journal = attribute_registry.landing_journal(issue, review_root)
    line = otel_event.journal_line(
        event,
        exported=False,
        detail=BACKFILL_DETAIL_PREFIX + reason,
    )
    try:
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as failure:
        message = f"landing journal {journal} could not be written: {failure}"
        raise BackfillError(message) from failure


def _candidate_issues(store: Mapping[str, object], review_root: Path) -> tuple[int, ...]:
    """Choose current projection rows whose journal has no produced relation."""
    read = observatory.read_landings(review_root)
    produced = {int(row["issue"]) for row in read.landings if row["produced_commit"] is not None}
    summary_rows = store.get("issue_summary")
    if not isinstance(summary_rows, list):
        message = "observatory projection has no readable issue_summary list"
        raise BackfillError(message)
    issues: list[int] = []
    for row in summary_rows:
        issue_value = row.get("issue") if isinstance(row, dict) else None
        if not isinstance(issue_value, int) or isinstance(issue_value, bool):
            message = "observatory projection has a malformed issue_summary row"
            raise BackfillError(message)
        issue = issue_value
        if issue not in produced:
            issues.append(issue)
    return tuple(sorted(issues))


def _candidate_store(paths: BackfillPaths) -> Mapping[str, object]:
    """Build the current projection view without writing its generated Markdown."""
    with tempfile.TemporaryDirectory(prefix="cti-observatory-backfill-") as directory:
        return observatory.rebuild(
            paths.dispatch_root,
            paths.export_dir,
            paths.review_root,
            paths.spool,
            paths.repo,
            Path(directory),
            paths.queue_root,
            write_summary_file=False,
        )


def _resolved_candidates(
    repo: Path,
    issue: int,
    candidates: Iterable[AuditCandidate],
    windows: Sequence[DispatchWindow],
) -> tuple[tuple[ResolvedCandidate, ...], tuple[str, ...]]:
    """Keep only audit SHAs that clear the complete Git and dispatch ladder."""
    resolved: dict[str, ResolvedCandidate] = {}
    rejected: list[str] = []
    for candidate in candidates:
        found, reason = resolve_candidate(repo, issue, candidate, windows)
        if found is not None:
            resolved[found.sha] = found
        else:
            rejected.append(reason)
    return (
        tuple(sorted(resolved.values(), key=lambda value: (value.at, value.sha))),
        tuple(sorted(set(rejected))),
    )


def _reconcile_issue(
    paths: BackfillPaths,
    issue: int,
    snapshot: TrackerSnapshot,
    *,
    now: Callable[[], float],
) -> BackfillOutcome:
    """Reconcile one candidate issue, with no prose-derived fallback branch."""
    journal = attribute_registry.landing_journal(issue, paths.review_root)
    existing, has_event = _journal_state(journal, issue)
    if existing:
        return BackfillOutcome(
            issue, "already_recovered", "a produced relation is already journalled", ()
        )
    windows = dispatch_windows(paths.dispatch_root, issue)
    candidates = audit_candidates(snapshot.comments.get(issue, ()))
    resolved, rejected = _resolved_candidates(
        paths.repo,
        issue,
        candidates,
        windows,
    )
    if resolved:
        for found in resolved:
            relations = (
                attribute_registry.relation("subject", "issue", str(issue)),
                attribute_registry.relation("produced", "commit", found.sha),
            )
            _append_event(paths.review_root, issue, relations, found.at, found.evidence)
        return BackfillOutcome(
            issue,
            "recovered",
            "audit SHA validated against origin/main and a dispatch window",
            tuple(found.sha for found in resolved),
        )

    state = snapshot.states[issue]
    if state != TRACKER_STATE_CLOSED:
        return BackfillOutcome(
            issue,
            "not_landed",
            f"tracker state is {state.lower()}, so no landing is reconciled",
        )
    reason = (
        "no exact just-land SHA was found in the landing audit comments"
        if not candidates
        else "; ".join(rejected)
    )
    if not has_event:
        relations = (attribute_registry.relation("subject", "issue", str(issue)),)
        _append_event(paths.review_root, issue, relations, now(), reason)
    return BackfillOutcome(issue, "unrecoverable", reason)


def reconcile(
    paths: BackfillPaths,
    *,
    fetch: FetchTracker,
    now: Callable[[], float] = time.time,
) -> tuple[BackfillOutcome, ...]:
    """Backfill all current projection rows that lack a produced relation."""
    store = _candidate_store(paths)
    issues = _candidate_issues(store, paths.review_root)
    if not issues:
        return ()
    snapshot = fetch(paths.repo)
    missing_states = sorted(set(issues) - set(snapshot.states))
    if missing_states:
        raise BackfillError(
            "tracker returned no state for issue(s) " + ",".join(map(str, missing_states))
        )

    return tuple(_reconcile_issue(paths, issue, snapshot, now=now) for issue in issues)


def _path_argument(parser: argparse.ArgumentParser, name: str, env: str, default: Path) -> None:
    """Add one source path with the observatory's environment spelling."""
    parser.add_argument(f"--{name}", type=Path, default=Path(os.environ.get(env, str(default))))


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse the backfill's source paths; the action itself is selected by observatory."""
    parser = argparse.ArgumentParser(description="Backfill journalled observatory landings.")
    _path_argument(parser, "dispatch-root", "CTI_DISPATCH_DIR", observatory.DEFAULT_DISPATCH_ROOT)
    _path_argument(parser, "export-dir", "CTI_OTEL_EXPORT_DIR", observatory.DEFAULT_EXPORT_DIR)
    _path_argument(parser, "review-root", "CTI_REVIEW_DIR", observatory.DEFAULT_REVIEW_ROOT)
    _path_argument(parser, "queue-dir", "CTI_QUEUE_DIR", observatory.DEFAULT_QUEUE_ROOT)
    _path_argument(parser, "spool", "CTI_QUOTA_SPOOL", observatory.DEFAULT_SPOOL)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def render(outcomes: Sequence[BackfillOutcome]) -> tuple[str, ...]:
    """Render statuses and reasons without retyping any source SHA or path."""
    counts: dict[str, int] = defaultdict(int)
    for outcome in outcomes:
        counts[outcome.status] += 1
    lines = [
        " ".join(
            (
                "backfill",
                f"issues={len(outcomes)}",
                f"recovered={counts['recovered']}",
                f"unrecoverable={counts['unrecoverable']}",
                f"not_landed={counts['not_landed']}",
                f"already_recovered={counts['already_recovered']}",
            )
        )
    ]
    for outcome in outcomes:
        fields = [f"backfill_issue={outcome.issue}", f"status={outcome.status}"]
        if outcome.shas:
            fields.append(f"produced={','.join(outcome.shas)}")
        fields.append(f"reason={outcome.reason}")
        lines.append(" ".join(fields))
    return tuple(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the write-once reconciliation, or refuse without partial interpretation."""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        outcomes = reconcile(
            BackfillPaths(
                args.dispatch_root,
                args.export_dir,
                args.review_root,
                args.spool,
                args.repo,
                args.queue_dir,
            ),
            fetch=fetch_tracker,
        )
    except (BackfillError, observatory._RefusedError) as failure:  # noqa: SLF001 — rebuild's typed refusal boundary
        print(f"refused=observatory_backfill reason={failure}", file=sys.stderr)  # noqa: T201
        return EXIT_REFUSED
    for line in render(outcomes):
        print(line)  # noqa: T201 — this is the reconciliation record
    return 0


if __name__ == "__main__":  # pragma: no cover - the seam
    raise SystemExit(main())
