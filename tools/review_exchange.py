"""The review branch exchange and the verdict record (ADR-0071 ruling 4, #332).

Two halves of one handover, and the issue asked for them together because each is
half a proof: the **exchange** puts the reviewed work where a second instance can
reach it without ever entering the first instance's tree, and the **verdict
record** is what that second instance's judgement becomes — a durable fact outside
the diff it judged, bound to the commit it judged and to the dispatch that judged
it.

## The exchange: a branch, never a tree

Pointing a second agent at a live worktree is the collision shape this project has
already paid for: #105's worktree assignment handed two agents one tree five times
in one evening and an agent's uncommitted work was destroyed. So the implementer
hands over a **remote ref**, pushed from its own tree, and the reviewer materialises
a tree of its own from that ref — `just worktree restore <name> --ref <ref>` — so
the two instances never share a directory at any point in the loop.

The ref is `refs/heads/issue-<n>`, the branch the dispatch protocol already names,
and it is **force-moved each round**: a fix round amends or rebases, and the verdict
record binds the SHA rather than the ref precisely so a moved ref cannot satisfy
anything. Durability of *parked* work stays where it was — the `-parked` suffix and
`just worktree archive` — because the exchange ref is the live flight's slot, not a
preservation act. `exchange` verifies after pushing (`git ls-remote`) that the
remote resolves to this tree's exact HEAD, because a handover that names a SHA the
remote does not hold hands the reviewer nothing.

## The verdict record: derived identity, bound SHA

The verdict lives in `verdict.json` **beside the dispatch that produced it**, under
`~/.arma-cti/dispatches/<id>/` — outside every worktree, because a record inside the
tree changes the commit being reviewed.

**The reviewing identity is derived, not declared** — #322's reasoning, one layer
over. There, a declaration the caller controlled settled nothing, so the dispatch
records were read for a potential-author set and the route says `checked` rather
than `verified`. Here, the half a reviewed agent controls is any field it might
write into a verdict, so `derive_binding` reads the records the **dispatcher**
wrote: a binding dispatch is one whose record carries `seat=review`, this issue and
this reviewed SHA as its `base_sha` — which on the review seat is the reviewed
commit (`docs/agents/review-dispatch.md`), and which defaults to the reviewer
worktree's own HEAD, so the dispatcher records it without trusting anyone's
transcription. What the derivation supports is that a review dispatch was bound to
this commit and completed; it is not evidence the reviewer examined the code well,
and nothing here says `verified`.

**Fail-closed where #322's scan fails open on purpose.** `potential_authors`
returns the profiles a partial read *did* see, because an incomplete superset still
excludes. A binding cannot borrow that move: it must be *the* answer, and a record
that would not open could be the binding one, so any unreadable record refuses
(`records_unreadable`) rather than degrading to the records that happened to parse.

**A verdict satisfies exactly the commit it names.** The record carries the full
reviewed SHA; `satisfies` refuses a different SHA (`sha_mismatch`) rather than
passing quietly — an amended or rebased branch lands on no earlier approval, which
is the failure the binding exists to close. `show --satisfies` re-derives the
identity as well, refusing `identity_mismatch` where the record the verdict names is
not the one the dispatch records support, so a verdict is never taken on its own
word.

## The limit, stated where the reader meets it

Every dispatch runs as the same user, so an agent determined to forge an evidence
directory can. This is the same limit the credentials design records: it protects
against the accident and the shortcut, not against a deceptive agent. The
never-alone invariant is therefore a **convention with a mechanical floor, not a
guarantee**, and both `record` and `show` print that limit beside the record they
produce rather than leaving it in this docstring.

## Boundaries, so the three consumers do not re-derive halves of this

The authoring-profile exclusion is #322's at dispatch time and #334's at landing;
this module provides the binding facts both read. Adjudication of the findings a
verdict carries is #333's, over `tools/review_loop.py`'s state — this module only
validates that each finding names a severity of the severity document and an id
unique within the verdict.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `dispatch.py`, `brief.py` and
# `review_loop.py` all use.
sys.path.insert(0, str(Path(__file__).parent))

import review_loop
import worktree
from worktree import Refusal, Report

VERDICT_NAME: Final = "verdict.json"
REVIEW_SEAT: Final = "review"
BOUND: Final = "bound"
# Mirrors `dispatch.DISPATCH_ROOT` (`tools/dispatch.py` owns the shape); stated here so a
# reader of this module needs no second file to know where records live. The CLI takes
# `--dispatch-dir` for the tests and for reading a preserved evidence tree.
DISPATCH_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"
# A commit is named in full or not at all: a shortened SHA names several commits, and a
# binding that could mean two commits satisfies neither.
FULL_SHA: Final = re.compile(r"\A[0-9a-f]{40}\Z")
# `breaker.OK`, mirrored rather than imported so the completion ladder stays a local
# decision over the records it reads (`tools/breaker.py` owns the vocabulary, and
# `classify_run` is what ties `ok` to a zero exit behind `write_result`).
OUTCOME_OK: Final = "ok"
SHA_ERROR: Final = "a commit is named by its full 40-character SHA, never a shortened form"
ISSUE_ERROR: Final = "the issue is named by its number, greater than zero"
VERSION_ERROR: Final = "a verdict must be a version 1 object"

SAME_USER_LIMIT: Final = (
    "limit=every dispatch runs as the same user, so this record protects against the"
    " accident and the shortcut, not against a deceptive agent — a convention with a"
    " mechanical floor, not a guarantee (ADR-0071 ruling 4)"
)
SHA_BINDING_NOTE: Final = (
    "binding=this verdict satisfies only the SHA it names — a different commit, this"
    " branch after a rebase included, needs a new review"
)


class ReviewExchangeError(ValueError):
    """Input whose shape cannot become part of a verdict record."""


# ------------------------------------------------------------------ the exchange ref


def review_ref(issue: int) -> str:
    """Return the remote ref an issue's review branch lives on.

    The branch the dispatch protocol already names — the worktree is `issue-<n>`, the
    brief says "push `issue-<n>`" — rather than a second convention to keep in step.
    Force-moved each round by `exchange`; preservation stays on the `-parked` suffix
    with `just worktree archive`.
    """
    if issue <= 0:
        raise ReviewExchangeError(ISSUE_ERROR)
    return f"refs/heads/issue-{issue}"


def _git_failed(cwd: Path, failure: worktree.GitError) -> Report:
    """Render git's own failure as the named refusal it is, argv and stderr quoted.

    An action, not a library call: the reader of `exchange` output meets the failure
    as `git_failed` with git's words in `found`, never as a traceback.
    """
    return Report.refused(
        Refusal(
            "git_failed",
            (
                f"worktree={cwd}",
                f"command=git {' '.join(failure.args_run)}",
                f"stderr={failure.stderr}",
            ),
            "Read git's own error above. Nothing was pushed.",
        )
    )


def exchange(  # noqa: PLR0911 — one return per refusal, so each stays a whole thought
    cwd: Path, issue: int
) -> Report:
    """Push this tree's HEAD to the issue's review ref and verify the remote holds it.

    The whole of the implementer's half of the handover: a clean tree (what is handed
    over is committed work), one push, one `ls-remote` confirmation that the ref now
    resolves to this exact HEAD. The reviewer's half is `just worktree restore` from
    the ref, so no step of the loop ever has two instances in one directory.
    """
    if issue <= 0:
        return Report.refused(
            Refusal(
                "invalid_issue",
                (f"issue={issue}",),
                "Name the issue whose review branch this is, e.g. `exchange 332`.",
            )
        )
    try:
        head = worktree.git("rev-parse", "HEAD", cwd=cwd).strip()
        # `check` stays on: a status command that fails and prints nothing must
        # refuse as `git_failed`, never read as an empty — that is, clean — tree.
        # A filter or a crash that removes every line turns presence into absence
        # (#105's invariant), and this path exists to stop two
        # agents sharing one tree, so an unestablished clean is a refusal.
        status = worktree.read_status(worktree.git("status", "--porcelain", cwd=cwd))
    except worktree.GitError as failure:
        return _git_failed(cwd, failure)
    if not status.clean:
        return Report.refused(
            Refusal(
                "dirty_tree",
                (f"worktree={cwd}", f"head={head[:7]}", *_exchange_found(status)),
                "Commit first: the exchange hands over committed work, and a dirty tree"
                " is either yours unfinished or another agent's — never hand over either.",
            )
        )
    try:
        ref = review_ref(issue)
        worktree.git("push", "--force", "origin", f"HEAD:{ref}", cwd=cwd)
        remote_sha = worktree.remote_ref_sha(cwd, ref)
    except worktree.GitError as failure:
        return _git_failed(cwd, failure)
    if remote_sha is None:
        return Report.refused(
            Refusal(
                "not_on_remote",
                (f"worktree={cwd}", f"head={head}", f"ref={ref}", "resolved=no"),
                "The push reported success but the remote does not resolve the ref to"
                " this HEAD. Read the remote's own state before handing anything over.",
            )
        )
    if remote_sha != head:
        return Report.refused(
            Refusal(
                "ref_mismatch",
                (f"worktree={cwd}", f"head={head}", f"ref={ref}", f"resolved={remote_sha}"),
                "Another push moved the ref between this push and the check. Re-run the"
                " exchange, or stop and report: two implementers on one issue is the"
                " collision this protocol exists to prevent.",
            )
        )
    return Report(
        (
            "ok=review_branch_exchanged",
            f"issue={issue}",
            f"review_ref={ref}",
            f"reviewed_sha={head}",
            SHA_BINDING_NOTE,
            (
                "Dispatch the reviewer at this SHA with `--base-sha <sha>` (pasted,"
                " never retyped); its tree comes from `just worktree restore <name>"
                f" --ref {ref}`, never from this worktree."
            ),
        ),
        0,
    )


def _exchange_found(status: worktree.Preflight) -> tuple[str, ...]:
    """Render the dirt the exchange refused on, capped the way the ladders render it."""
    found = [f"tracked={line}" for line in status.tracked[: worktree.HOW_MANY_SHOWN]]
    found += [f"untracked={line}" for line in status.untracked[: worktree.HOW_MANY_SHOWN]]
    total = len(status.tracked) + len(status.untracked)
    shown = min(len(status.tracked), worktree.HOW_MANY_SHOWN) + min(
        len(status.untracked), worktree.HOW_MANY_SHOWN
    )
    if total > shown:
        found.append(f"and={total - shown} more")
    return tuple(found)


# --------------------------------------------------------------------- the findings


class ReportedFinding(NamedTuple):
    """One finding as the verdict records it: an identity and the severity assigned.

    `docs/agents/review-severity.md`'s four levels, spelled and ordered by
    `tools/review_loop.py` so the two modules cannot grow different vocabularies. The
    id is the reviewer's own handle for the claim; uniqueness within one verdict is
    enforced here, while uniqueness across rounds — the re-report the ruling makes a
    new finding — is #333's loop state, not this record.
    """

    id: str
    severity: str


FINDINGS_LIST_ERROR: Final = "findings must be a list of objects"
FINDING_FIELDS_ERROR: Final = "each finding must carry a non-empty id and a severity"
FINDING_SEVERITY_ERROR: Final = review_loop.SEVERITY_ERROR
FINDING_UNIQUE_ERROR: Final = "a finding id may appear once in a verdict"
DISPATCH_NAMED_ERROR: Final = "a verdict names the dispatch that produced it"
PROFILE_NAMED_ERROR: Final = "a verdict names the reviewer profile derived for it"
LANE_NAMED_ERROR: Final = "a verdict names the reviewer lane derived for it"
RECORDED_AT_ERROR: Final = "a verdict carries the instant it was recorded"
ALTERNATES_ERROR: Final = "a verdict's alternates are dispatch ids"
DISPATCH_ID_ERROR: Final = "a dispatch id is a directory name, never a path"


def _finding(raw: object) -> ReportedFinding:
    if not isinstance(raw, dict):
        raise ReviewExchangeError(FINDINGS_LIST_ERROR)
    identifier = raw.get("id")
    severity = raw.get("severity")
    if not isinstance(identifier, str) or not identifier:
        raise ReviewExchangeError(FINDING_FIELDS_ERROR)
    if not isinstance(severity, str) or severity not in review_loop.SEVERITY_RANK:
        raise ReviewExchangeError(FINDING_SEVERITY_ERROR)
    return ReportedFinding(identifier, severity)


def parse_findings(text: str) -> tuple[ReportedFinding, ...]:
    """Validate the findings a report distils to, refusing any shape that cannot govern.

    The reviewer's claims arrive as prose; this is the moment they become data — a
    list of objects, each an id and one of the four severities, ids unique within the
    verdict. A severity outside the four cannot reach `review_loop`'s stop condition,
    and a duplicated id would let two findings share one adjudication (#333).
    """
    document = json.loads(text)
    if not isinstance(document, list):
        raise ReviewExchangeError(FINDINGS_LIST_ERROR)
    findings = tuple(_finding(item) for item in document)
    identifiers = [finding.id for finding in findings]
    if len(set(identifiers)) != len(identifiers):
        raise ReviewExchangeError(FINDING_UNIQUE_ERROR)
    return findings


# ------------------------------------------------------------------ the derived identity


class Bound(NamedTuple):
    """The reviewing dispatch the records support for one (issue, reviewed SHA).

    `dispatch_id`, `profile` and `lane` are read off that record — written by the
    dispatcher, never by the reviewed agent. `alternates` names any other completed
    review dispatch bound to the same commit, so a reader can see the choice the
    latest-first rule made. Consumers narrow on `kind`, by value rather than
    `isinstance`, for the re-exec reason `review_loop` documents.
    """

    dispatch_id: str
    profile: str
    lane: str
    planned_at: str
    alternates: tuple[str, ...]

    @property
    def kind(self) -> str:
        """The value a consumer narrows on; a module re-exec cannot change it."""
        return BOUND


class _Record(NamedTuple):
    """What one dispatch directory contributed to the binding scan.

    A record can be a candidate and still not be readable for this purpose — a plan
    that parses beside a `result.json` that does not — so the two facts stay separate
    the way `dispatch._Read` keeps them, with the same safe directions: a candidate
    is kept, an unreadable anything refuses the scan.
    """

    dispatch_id: str
    profile: str
    lane: str
    planned_at: str


def _binding_plan(  # noqa: PLR0911 — one return per way a record can be read, so no branch hides inside another
    entry: Path, issue: int, reviewed_sha: str
) -> _Record | str:
    """Classify one dispatch directory against the binding being derived.

    `"past"` for a record this scan walks past — another seat, another issue, another
    SHA — and a `_Record` for a candidate. Every way of not being able to read a
    review-seat record on this issue returns `"unreadable"` instead, because the
    record that would not open could be the binding one: an exclusion can continue
    on a partial read (#322), an answer cannot.
    """
    plan = entry / "dispatch.json"
    try:
        document = json.loads(plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return "unreadable"
    if not isinstance(document, dict):
        return "unreadable"
    if str(document.get("seat", "")) != REVIEW_SEAT:
        return "past"
    try:
        same_issue = int(str(document["issue"])) == issue
    except (KeyError, ValueError, TypeError):
        return "unreadable"
    if not same_issue:
        return "past"
    base_sha = document.get("base_sha")
    if not isinstance(base_sha, str) or not base_sha:
        # `tools/dispatch.py` writes `base_sha` unconditionally, so a review record
        # without one is not a shape this version's dispatcher produces — and a review
        # dispatch that names no commit binds none, visibly.
        return "unreadable"
    if base_sha != reviewed_sha:
        return "past"
    profile = document.get("profile")
    planned_at = document.get("planned_at")
    if not isinstance(profile, str) or not profile:
        return "unreadable"
    if not isinstance(planned_at, str) or not planned_at:
        return "unreadable"
    return _Record(
        dispatch_id=str(document.get("dispatch_id", entry.name)),
        profile=profile,
        lane=str(document.get("lane", "")),
        planned_at=planned_at,
    )


class _Result(NamedTuple):
    """One candidate's end state: completed, or the fact that it is not."""

    completed: bool
    state: str


def _binding_result(entry: Path) -> _Result | str:  # noqa: PLR0911 — the end-state ladder, one return per state
    """Read one candidate's `result.json`, or the reason it could not be read.

    Completed is read from the **outcome**, never from the timestamps a refusal
    also carries: `write_result` types every finished run, and only `outcome=ok`
    completed. A run that ended quota-dead, provider-dead or unclassified did end
    — it carries a returncode and an `ended_at` like any other — and it is
    explicitly not a result, which is the failure-class table's own line; reading
    its timestamps as completion is how a verdict gets recorded against a review
    that never happened. A result that carries a `refusal` is a dispatch that
    never reached a lane; no result at all is a dispatch still live or stopped
    without one; both are named facts, not gaps.
    """

    def result(state: str, *, completed: bool = False) -> _Result:
        return _Result(completed, state)

    document = entry / "result.json"
    if not document.is_file():
        return result("result=absent")
    try:
        read = json.loads(document.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return "unreadable"
    if not isinstance(read, dict):
        return "unreadable"
    refused = "refusal" in read
    ended = isinstance(read.get("ended_at"), str) and bool(read["ended_at"])
    ran = "returncode" in read
    outcome = read.get("outcome")
    if refused and ran:
        return "unreadable"
    if refused:
        return result("result=refusal")
    if not ran or not isinstance(outcome, str) or not outcome:
        # A result beside a returncode carries a typed outcome, always — this is
        # not a shape `write_result` produces, so it is not a fact this scan reads.
        return "unreadable"
    if outcome != OUTCOME_OK:
        return result(f"result=not_a_result:{outcome}")
    if not ended:
        return "unreadable"
    return result(completed=True, state="result=completed")


def derive_binding(issue: int, reviewed_sha: str, dispatch_root: Path) -> Bound | Refusal:
    """Derive the reviewing dispatch for one commit from the records the dispatcher wrote.

    The #322 move one layer over: a field an agent might have written settles nothing,
    so nothing here is taken from the verdict's own claims — the scan reads
    `dispatch.json` records for `seat=review` on this issue whose `base_sha` is this
    commit, requires a completed end state, and picks the latest such dispatch by
    plan time (ties by id, so the answer is one answer). Where more than one
    completed dispatch is bound, the earlier ones are `alternates` on the answer
    rather than silently discarded.

    **Refuses closed on anything it could not read.** An unreadable plan or result —
    including one belonging to a record on another issue, which cannot be shown to be
    another issue's — is `records_unreadable`, because the binding one could be it.
    """
    root = dispatch_root.expanduser()
    if not root.is_dir():
        return Refusal(
            "no_dispatch_records",
            (f"dispatch_root={root}",),
            "There is no dispatch record directory to derive a reviewing identity"
            " from. A review nobody can attribute clears nothing.",
        )
    candidates: list[_Record] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            # Not a record at all. A stray file beside the records is not a record
            # this scan failed to read, so it does not refuse the scan.
            continue
        plan = _binding_plan(entry, issue, reviewed_sha)
        if plan == "past":
            continue
        if isinstance(plan, str):
            return Refusal(
                "records_unreadable",
                (f"dispatch_root={root}", f"record={entry.name}", f"plan={plan}"),
                "A dispatch record could not be read for this binding, and the record"
                " that would not open could be the binding one — so no binding is"
                " derived. Nothing was written.",
            )
        outcome = _binding_result(entry)
        if isinstance(outcome, str):
            return Refusal(
                "records_unreadable",
                (f"dispatch_root={root}", f"record={entry.name}", f"result={outcome}"),
                "The binding candidate's own end state could not be read, so whether"
                " the review completed is not an answer this scan can give. Nothing"
                " was written.",
            )
        if outcome.completed:
            candidates.append(plan)
    if not candidates:
        return Refusal(
            "no_review_dispatch",
            (f"issue={issue}", f"reviewed_sha={reviewed_sha}"),
            "No completed review dispatch record binds this commit — seat=review,"
            f" issue={issue}, base_sha=this SHA. Dispatch the reviewer first"
            " (`just dispatch --seat review --reviewing <profile> --base-sha <sha>`)",
        )
    ordered = sorted(candidates, key=lambda record: (record.planned_at, record.dispatch_id))
    chosen = ordered[-1]
    return Bound(
        dispatch_id=chosen.dispatch_id,
        profile=chosen.profile,
        lane=chosen.lane,
        planned_at=chosen.planned_at,
        alternates=tuple(record.dispatch_id for record in ordered[:-1]),
    )


# ---------------------------------------------------------------------- the verdict


class Verdict(NamedTuple):
    """One review's judgement as a durable record: what commit, who derived, what found.

    Every identity field is written by `record_verdict` from a `Bound` — never
    supplied by the caller — so the only hands between the dispatch records and this
    record are the tool's.
    """

    issue: int
    reviewed_sha: str
    review_dispatch: str
    reviewer_profile: str
    reviewer_lane: str
    findings: tuple[ReportedFinding, ...]
    recorded_at: str
    alternates: tuple[str, ...]


def verdict_document(verdict: Verdict) -> dict[str, object]:
    """Render the verdict as the JSON the record carries."""
    return {
        "version": 1,
        "issue": verdict.issue,
        "reviewed_sha": verdict.reviewed_sha,
        "review_dispatch": verdict.review_dispatch,
        "reviewer_profile": verdict.reviewer_profile,
        "reviewer_lane": verdict.reviewer_lane,
        "findings": [
            {"id": finding.id, "severity": finding.severity} for finding in verdict.findings
        ],
        "recorded_at": verdict.recorded_at,
        "alternates": list(verdict.alternates),
    }


def parse_verdict(text: str) -> Verdict:
    """Validate a verdict record's shape, refusing anything that cannot be trusted as one.

    The same validation `record_verdict` applies on the way in, applied on the way
    out — a record this module did not write, or a hand-edit of one it did, meets the
    same floor before any consumer narrows on it.
    """
    document = json.loads(text)
    version = document.get("version") if isinstance(document, dict) else None
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise ReviewExchangeError(VERSION_ERROR)
    issue = document.get("issue")
    reviewed_sha = document.get("reviewed_sha")
    dispatch = document.get("review_dispatch")
    profile = document.get("reviewer_profile")
    lane = document.get("reviewer_lane")
    recorded_at = document.get("recorded_at")
    if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
        raise ReviewExchangeError(ISSUE_ERROR)
    if not isinstance(reviewed_sha, str) or not FULL_SHA.fullmatch(reviewed_sha):
        raise ReviewExchangeError(SHA_ERROR)
    if not isinstance(dispatch, str) or not dispatch:
        raise ReviewExchangeError(DISPATCH_NAMED_ERROR)
    if not isinstance(profile, str) or not profile:
        raise ReviewExchangeError(PROFILE_NAMED_ERROR)
    if not isinstance(lane, str):
        raise ReviewExchangeError(LANE_NAMED_ERROR)
    if not isinstance(recorded_at, str) or not recorded_at:
        raise ReviewExchangeError(RECORDED_AT_ERROR)
    findings = parse_findings(json.dumps(document.get("findings", [])))
    alternates = document.get("alternates", [])
    if not isinstance(alternates, list) or not all(isinstance(item, str) for item in alternates):
        raise ReviewExchangeError(ALTERNATES_ERROR)
    return Verdict(
        issue=issue,
        reviewed_sha=reviewed_sha,
        review_dispatch=dispatch,
        reviewer_profile=profile,
        reviewer_lane=lane,
        findings=findings,
        recorded_at=recorded_at,
        alternates=tuple(alternates),
    )


def verdict_path(dispatch_root: Path, dispatch_id: str) -> Path:
    """Return where one dispatch's verdict record lives — beside its own plan.

    A dispatch id is a directory name, never a path: one carrying a separator would
    move the record outside the dispatch it belongs to, which is the same quiet
    relocation `worktree.classify_target` refuses on names.
    """
    if not dispatch_id or "/" in dispatch_id or dispatch_id in {".", ".."}:
        message = f"{DISPATCH_ID_ERROR}: {dispatch_id!r}"
        raise ReviewExchangeError(message)
    return dispatch_root.expanduser() / dispatch_id / VERDICT_NAME


class Recorded(NamedTuple):
    """A verdict this call wrote, and where."""

    verdict: Verdict
    path: Path


def _unwritten(path: Path, failure: OSError) -> Refusal:
    """Return the one refusal every way of failing to write this verdict becomes."""
    return Refusal(
        "verdict_unwritten",
        (f"verdict={path}", f"found={type(failure).__name__}: {failure}"),
        "The verdict could not be written, and nothing was left behind. Read the"
        " error above — a full disk is the box's to fix, not the record's — then"
        " re-record.",
    )


def _write_verdict_once(path: Path, document: dict[str, object]) -> Refusal | None:
    """Publish the verdict's file atomically, so that writing is once under concurrency too.

    The record is written to a private staged file and then moved into place by
    `os.link`, which is atomic and refuses a name that already exists: two
    concurrent `record` calls cannot both pass a check-then-write window and
    overwrite each other's findings, and the loser loses against a file that is
    already whole — the target name never resolves to a half-written verdict, so
    a concurrent reader (`show`) never meets a partial either. A file that does
    occupy the slot is read back before it is answered, because the two ways to
    be occupied want different hands: a verdict that parses is the once-written
    record (`verdict_exists`), and one that does not is a corruption
    (`verdict_unreadable`), refused with its recovery named rather than as an
    unwritable slot. Nothing is ever overwritten; a write of this call's own
    that fails anywhere — before the staging even opens, a dispatch directory
    missing, unwritable or removed under the write, or anywhere short of the
    link — is the same `verdict_unwritten`, and leaves at most its staged file,
    removed.
    """
    text = json.dumps(document, indent=2) + "\n"
    try:
        staged_fd, staged_name = tempfile.mkstemp(
            prefix=f"{path.name}.", suffix=".staged", dir=path.parent
        )
    except OSError as failure:
        # Staging is the first act that needs the directory to be there and
        # writable — the binding derivation only reads it — so this is where a
        # missing, unwritable or concurrently removed dispatch directory lands.
        return _unwritten(path, failure)
    staged = Path(staged_name)
    try:
        try:
            with os.fdopen(staged_fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(staged, path)
        except FileExistsError:
            try:
                parse_verdict(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                return Refusal(
                    "verdict_unreadable",
                    (f"verdict={path}",),
                    "The file occupying this verdict's place does not read back as one —"
                    " a corruption, not a recorded verdict. Nothing was overwritten."
                    " Read it; if it is no verdict of this dispatch's, remove it by"
                    " hand and re-record from the dispatch records.",
                )
            return Refusal(
                "verdict_exists",
                (f"verdict={path}", f"reviewed_sha={document['reviewed_sha']}"),
                "A verdict already exists for this dispatch. A re-review of the same SHA"
                " is a new dispatch with its own record; editing findings into an existing"
                " verdict is the swap this refusal exists to prevent.",
            )
        except OSError as failure:
            return _unwritten(path, failure)
        return None
    finally:
        # On success the link holds the same inode, so removing the staged name
        # removes only the staging; on every failure it removes the attempt.
        staged.unlink(missing_ok=True)


def record_verdict(
    issue: int,
    reviewed_sha: str,
    findings_text: str,
    dispatch_root: Path,
    *,
    now: str | None = None,
) -> Recorded | Refusal:
    """Derive the reviewing identity and write the verdict beside that dispatch.

    The caller supplies the three things it owns — the issue, the reviewed SHA, the
    findings — and nothing about who reviewed. The identity comes from
    `derive_binding`, the same derivation `show` re-runs later, so a verdict never
    carries an identity some caller typed. Writing is once, atomically: the file is
    created exclusively (`_write_verdict_once`), so a verdict that already exists
    where this one would land refuses `verdict_exists`, because the finding list is
    the one field a re-record could quietly swap.
    """
    if issue <= 0:
        return Refusal(
            "invalid_issue", (f"issue={issue}",), "Name the issue the review was dispatched on."
        )
    if not FULL_SHA.fullmatch(reviewed_sha):
        return Refusal(
            "invalid_sha",
            (f"reviewed_sha={reviewed_sha}", SHA_ERROR),
            f"Name the reviewed commit in full — {SHA_ERROR}.",
        )
    try:
        findings = parse_findings(findings_text)
    except (ValueError, json.JSONDecodeError) as error:
        return Refusal(
            "invalid_findings",
            (f"findings={type(error).__name__}: {error}",),
            "The findings must be a JSON list of objects carrying an id and one of the"
            f" four severities ({', '.join(review_loop.SEVERITIES)}).",
        )
    binding = derive_binding(issue, reviewed_sha, dispatch_root)
    if isinstance(binding, Refusal):
        return binding
    verdict = Verdict(
        issue=issue,
        reviewed_sha=reviewed_sha,
        review_dispatch=binding.dispatch_id,
        reviewer_profile=binding.profile,
        reviewer_lane=binding.lane,
        findings=findings,
        recorded_at=now or datetime.now(tz=UTC).isoformat(),
        alternates=binding.alternates,
    )
    path = verdict_path(dispatch_root, binding.dispatch_id)
    written = _write_verdict_once(path, verdict_document(verdict))
    if written is not None:
        return written
    return Recorded(verdict, path)


def satisfies(verdict: Verdict, sha: str) -> Refusal | None:
    """Whether this verdict's commit is the commit asked about — `None` when it is.

    The refusal names both SHAs rather than returning a bare false, because the
    caller that needs it is a landing gate: "not this one" must say which one it is
    before anyone re-reviews, and a quiet miss is how an amended branch rides an
    earlier approval.
    """
    if verdict.reviewed_sha == sha:
        return None
    return Refusal(
        "sha_mismatch",
        (f"asked={sha}", f"reviewed={verdict.reviewed_sha}", f"dispatch={verdict.review_dispatch}"),
        SHA_BINDING_NOTE
        + ". Re-review the commit being landed — the verdict names the one it judged.",
    )


def identity_mismatch(verdict: Verdict, binding: Bound) -> Refusal | None:
    """Whether a verdict's claimed identity is the one derived — `None` when it is.

    The comparison half of `verify`, named on its own for the caller that has already
    derived the binding over the same issue and SHA: re-deriving it there is a second
    full scan of every dispatch directory for an answer already in hand (#334 round 1
    claim 11). Every identity field is checked, not only the dispatch id — the profile
    and the lane are as much the derivation's to say, and a hand-edit of either is the
    same forged identity wearing two of its three names correctly.
    """
    if (binding.dispatch_id, binding.profile, binding.lane) == (
        verdict.review_dispatch,
        verdict.reviewer_profile,
        verdict.reviewer_lane,
    ):
        return None
    return Refusal(
        "identity_mismatch",
        (
            (
                f"claimed={verdict.review_dispatch}"
                f" profile={verdict.reviewer_profile} lane={verdict.reviewer_lane}"
            ),
            f"derived={binding.dispatch_id} profile={binding.profile} lane={binding.lane}",
            f"reviewed_sha={verdict.reviewed_sha}",
        ),
        "The dispatch records do not place this verdict's claimed reviewing"
        " identity on this commit — the dispatch, the profile and the lane are"
        " the derivation's to say. A verdict is taken on the records, never on"
        " its own word — re-derive before trusting it.",
    )


def verify(verdict: Verdict, dispatch_root: Path) -> Bound | Refusal:
    """Re-derive a verdict's reviewing identity from the dispatch records, now.

    The check that makes criterion three mechanical rather than declared: the record
    may claim any dispatch, and what settles the claim is the same derivation that
    wrote it, run again at read time over the records as they stand. Every identity
    field is checked, not only the dispatch id — the profile and the lane are as
    much the derivation's to say, and a hand-edit of either is the same forged
    identity wearing two of its three names correctly. A verdict whose named
    identity no longer derives — because the records changed, or because the name
    was never derived — refuses `identity_mismatch`.
    """
    binding = derive_binding(verdict.issue, verdict.reviewed_sha, dispatch_root)
    if isinstance(binding, Refusal):
        return binding
    forged = identity_mismatch(verdict, binding)
    return forged if forged is not None else binding


class BoundVerdict(NamedTuple):
    """A verdict and the binding it was read through — the pair both callers need.

    The return was `Verdict` alone while `review-loop sync` was its only caller, and
    #334's landing rung went on inlining the same six steps because it also needs the
    `Bound` — the dispatch, the profile and the lane it prints on the clearance (#334
    round 2 re-review, Medium 2). Two copies of one derivation agree only until one of
    them grows a check, so the return is widened to carry both rather than the landing
    keeping a copy of how a verdict binds.
    """

    verdict: Verdict
    binding: Bound


def bound_verdict(  # noqa: PLR0911 — one return per way a record can fail to bind, as the landing's own ladder has
    issue: int, sha: str, dispatch_root: Path
) -> BoundVerdict | Refusal:
    """Read the verdict bound to one issue's commit, or the refusal that stops it.

    The whole derivation in one call, in the order the landing's rung climbs it: the
    binding from the dispatch records, the record beside it, the item and the SHA it names,
    and the identity re-derived rather than believed. It lives here rather than beside
    either caller because both #334's landing rung and #333's `review-loop sync` need the
    *same* verdict — a loop opened from anything else would be a record of findings no
    verdict is on the hook for, and a landing cleared against a different one would be a
    landing cleared by a review of another commit. Both callers reach it: the landing rung
    reads its `binding` for the identity it prints, which is the fact that used to keep a
    second copy of these six steps alive in `land_review` (round 2 re-review, Medium 2).
    """
    binding = derive_binding(issue, sha, dispatch_root)
    if isinstance(binding, Refusal):
        return binding
    try:
        path = verdict_path(dispatch_root, binding.dispatch_id)
    except ReviewExchangeError as error:
        return Refusal(
            "records_unreadable",
            (f"dispatch={binding.dispatch_id}", f"reason={error}"),
            "The reviewing dispatch's id cannot name its own verdict record, and the record"
            " that would not open could be the binding one — so no verdict is read (#41).",
        )
    if not path.is_file():
        return Refusal(
            "no_verdict",
            (f"dispatch={binding.dispatch_id}", f"expected={path}"),
            "The review dispatch completed but no verdict record sits beside its plan."
            " Record the verdict (`just review record`) — a completed review whose judgement"
            " no one can read clears nothing (#41).",
        )
    try:
        verdict = parse_verdict(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return Refusal(
            "verdict_unreadable",
            (f"verdict={path}", f"reason={error}"),
            "The verdict record exists but will not parse. Repair or re-record it — a check"
            " that could not run is not a check that passed (#41).",
        )
    if verdict.issue != issue:
        return Refusal(
            "review_issue_mismatch",
            (f"asked_issue={issue}", f"verdict_issue={verdict.issue}", f"verdict={path}"),
            "This verdict judges another item's work. A verdict satisfies only the item and"
            " the SHA it names, so record one for this item's commit.",
        )
    mismatch = satisfies(verdict, sha)
    if mismatch is not None:
        return mismatch
    forged = identity_mismatch(verdict, binding)
    return forged if forged is not None else BoundVerdict(verdict, binding)


class Scanned(NamedTuple):
    """Every verdict record under a dispatch root, parseable and otherwise.

    `unreadable` carries the paths, not the contents: a verdict that will not parse
    is a fact a consumer must refuse on (#41 — a check that could not run is not a
    check that passed), and the path is where the reader looks to see why.
    """

    verdicts: tuple[tuple[str, Verdict], ...]
    unreadable: tuple[Path, ...]


def scan_verdicts(dispatch_root: Path) -> Scanned:
    """Collect every verdict record under the root, separating the unreadable by name."""
    root = dispatch_root.expanduser()
    found: list[tuple[str, Verdict]] = []
    unreadable: list[Path] = []
    if not root.is_dir():
        return Scanned((), ())
    for entry in sorted(root.iterdir()):
        path = entry / VERDICT_NAME
        if not path.is_file():
            continue
        try:
            found.append((entry.name, parse_verdict(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, json.JSONDecodeError):
            unreadable.append(path)
    return Scanned(tuple(found), tuple(unreadable))


# ---------------------------------------------------------------------- invocation


def _record_report(outcome: Recorded | Refusal) -> Report:
    """Render a record call's outcome; a written verdict answers with the limit beside it."""
    if isinstance(outcome, Refusal):
        return Report.refused(outcome)
    verdict, path = outcome.verdict, outcome.path
    return Report(
        (
            "ok=verdict_recorded",
            f"dispatch={verdict.review_dispatch}",
            f"reviewer_profile={verdict.reviewer_profile}",
            f"reviewer_lane={verdict.reviewer_lane}",
            f"issue={verdict.issue}",
            f"reviewed_sha={verdict.reviewed_sha}",
            f"findings={len(verdict.findings)}",
            f"alternates={' '.join(verdict.alternates) or 'none'}",
            f"verdict={path}",
            SHA_BINDING_NOTE,
            SAME_USER_LIMIT,
        ),
        0,
    )


def _show(  # noqa: PLR0911 — one return per refusal, so each stays a whole thought
    dispatch_id: str, dispatch_root: Path, satisfies_sha: str
) -> Report:
    """Read one verdict, re-derive its identity, and answer any satisfaction question."""
    try:
        path = verdict_path(dispatch_root, dispatch_id)
    except ReviewExchangeError as error:
        return Report.refused(Refusal("unknown_dispatch", (f"dispatch={dispatch_id}",), str(error)))
    if not path.is_file():
        return Report.refused(
            Refusal(
                "no_verdict",
                (f"verdict={path}",),
                "No verdict record lives beside that dispatch. `record` writes one"
                " after a completed review dispatch.",
            )
        )
    try:
        verdict = parse_verdict(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return Report.refused(
            Refusal(
                "verdict_unreadable",
                (f"verdict={path}", f"found={type(error).__name__}: {error}"),
                "A verdict that cannot be read back clears nothing. Read the file and"
                " re-record from the dispatch records if it should exist.",
            )
        )
    binding = verify(verdict, dispatch_root)
    if isinstance(binding, Refusal):
        return Report.refused(binding)
    lines = [
        "ok=verdict",
        f"dispatch={verdict.review_dispatch}",
        f"reviewer_profile={verdict.reviewer_profile}",
        f"reviewer_lane={verdict.reviewer_lane}",
        f"issue={verdict.issue}",
        f"reviewed_sha={verdict.reviewed_sha}",
        f"findings={len(verdict.findings)}",
        f"alternates={' '.join(verdict.alternates) or 'none'}",
        f"derived=yes identity_checked-not-verified records={binding.dispatch_id}",
        f"recorded_at={verdict.recorded_at}",
        f"verdict={path}",
        SHA_BINDING_NOTE,
        SAME_USER_LIMIT,
    ]
    if satisfies_sha:
        if not FULL_SHA.fullmatch(satisfies_sha):
            return Report.refused(
                Refusal("invalid_sha", (f"asked={satisfies_sha}",), SHA_ERROR + ".")
            )
        mismatch = satisfies(verdict, satisfies_sha)
        if mismatch is not None:
            return Report.refused(mismatch)
        lines.append(f"satisfies={satisfies_sha} yes")
    return Report(tuple(lines), 0)


def _issue_arg(text: str) -> int | None:
    """Read an issue argument, `None` when it is not a positive integer."""
    try:
        issue = int(text)
    except ValueError:
        return None
    return issue if issue > 0 else None


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """One of three actions: the implementer's push, the orchestrator's record, the read."""
    parser = argparse.ArgumentParser(
        prog="just review",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    actions = parser.add_subparsers(dest="action", required=True)

    push = actions.add_parser("exchange", help="push this tree as the issue's review branch")
    push.add_argument("issue", type=str, help="the issue number, e.g. 332")

    write = actions.add_parser("record", help="derive the identity and write the verdict")
    write.add_argument("--issue", required=True, type=str, help="the issue reviewed")
    write.add_argument(
        "--reviewed-sha", required=True, help="the reviewed commit, full 40-character SHA"
    )
    write.add_argument(
        "--findings", required=True, help="a JSON file of findings, each an id and a severity"
    )
    write.add_argument(
        "--dispatch-dir", default=str(DISPATCH_ROOT), help="the dispatch records' root"
    )

    read = actions.add_parser("show", help="read a verdict and re-derive its identity")
    read.add_argument("dispatch_id", help="the review dispatch id")
    read.add_argument("--satisfies", metavar="SHA", help="ask whether it satisfies this commit")
    read.add_argument(
        "--dispatch-dir", default=str(DISPATCH_ROOT), help="the dispatch records' root"
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one action, print its lines, exit what it decided."""
    args = parse_args(argv)
    report: Report
    try:
        if args.action == "exchange":
            issue = _issue_arg(args.issue)
            report = (
                exchange(Path.cwd(), issue)
                if issue is not None
                else Report.refused(
                    Refusal(
                        "invalid_issue",
                        (f"issue={args.issue}",),
                        "Name the issue whose review branch this is, e.g. `exchange 332`.",
                    )
                )
            )
        elif args.action == "record":
            issue = _issue_arg(args.issue)
            if issue is None:
                report = Report.refused(
                    Refusal(
                        "invalid_issue",
                        (f"issue={args.issue}",),
                        "Name the issue the review was dispatched on, e.g. `--issue 332`.",
                    )
                )
            else:
                report = _record_report(
                    record_verdict(
                        issue,
                        args.reviewed_sha,
                        Path(args.findings).read_text(encoding="utf-8"),
                        Path(args.dispatch_dir),
                    )
                )
        elif not args.dispatch_id:
            report = Report.refused(
                Refusal(
                    "unknown_dispatch",
                    ("dispatch=<absent>",),
                    "show names the review dispatch whose verdict it reads.",
                )
            )
        else:
            report = _show(args.dispatch_id, Path(args.dispatch_dir), args.satisfies)
    except (OSError, ValueError) as failure:
        report = Report.refused(
            Refusal(
                "input_unreadable",
                (f"found={type(failure).__name__}: {failure}",),
                "An input this action needed could not be read. Nothing was written.",
            )
        )
    stream = sys.stdout if report.code == 0 else sys.stderr
    for line in report.lines:
        print(line, file=stream)
    return report.code


if __name__ == "__main__":
    sys.exit(main())
