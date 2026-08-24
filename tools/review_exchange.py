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
commit (`docs/review-dispatch.md`), and which defaults to the reviewer
worktree's own HEAD, so the dispatcher records it without trusting anyone's
transcription. What the derivation supports is that a review dispatch was bound to
this commit and completed; it is not evidence the reviewer examined the code well,
and nothing here says `verified`.

**Fail-closed where #322's scan fails open on purpose.** `potential_authors`
returns the profiles a partial read *did* see, because an incomplete superset still
excludes. A binding cannot borrow that move: it must be *the* answer, and a record
that would not open could be the binding one, so any unreadable record refuses
(`records_unreadable`) rather than degrading to the records that happened to parse.

**A verdict satisfies the commit it names, or a rebase the tooling ran clean over a
diff the record identifies exactly (#417, reworked).** The record carries the full
reviewed SHA **and** the exact diff identity of the diff it was recorded over —
merge-base relative to `origin/main`, the same range `just land` lands, hashed with
`--unified=0` so no context line enters it and with hunk offsets normalised away and
the section anchors after them kept, so whitespace is exact and an upstream edit
beside the branch's own lines moves neither half. `satisfies` clears the named SHA
first; where the SHA has moved, the verdict
carries **only** when two independent facts both hold: the move is a chain of clean
rebases this project's tools ran and recorded (`just land --stage` and `just land`
write each one as a link under the review state, so a rebase a hand resolved —
conflicts or not — is unproven by construction), **and** the landing diff's identity
equals the recorded one. Either alone is insufficient, and that is the lesson of the
review that disproved the first build: `git patch-id --stable` strips whitespace, so
a resolution the reviewer never saw could hash equal, and hashing an output can
never prove whether conflict resolution occurred at all — only the rebase's own
record can, because only it knows whether a hand touched the replay. Where the SHA
and the diff both fail, `sha_mismatch` names both; where the recorded or the landing
identity could not be read, `diff_id_unreadable` refuses rather than passes (#41);
where no recorded clean-rebase chain connects the reviewed commit to the landing
one, `rebase_unproven` refuses and a fresh review is owed; and where the diff changes
a file git compares as bytes, `binary_diff_uncarried` refuses whatever the other two
say, because such a diff is nothing but blob hashes that name the base and
`.gitattributes` can make a same-file binary edit replay clean over them (#419). The
identity and the
provenance together prove the diff is unchanged and mechanically replayed, not that
its meaning survived the move onto the new base — the gate's tests at landing are
what catch that difference, and they still run.
`show --satisfies` re-derives the identity as well, refusing `identity_mismatch`
where the record the verdict names is not the one the dispatch records support, so a
verdict is never taken on its own word.

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
import hashlib
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

import attribute_registry
import dispatch_stop
import review_loop
import worktree
from worktree import Refusal, Report

VERDICT_NAME: Final = "verdict.json"
REVIEW_SEAT: Final = "review"
BOUND: Final = "bound"


# Where a review's recognised waits are journalled (#484): beside the loop's per-issue
# state, so the wait family adds a file to an existing directory and no new one. A
# function rather than a parameter because `exchange` takes none, and resolved at call
# time through `review_loop.review_root()` — an import-time constant bound
# `Path.home()` and left hermeticity to every success-path test remembering a
# `monkeypatch.setattr` (#484 round 2, finding 3); the root now reads
# `CTI_REVIEW_DIR` the way the queue reads `CTI_QUEUE_DIR`.
def wait_journal() -> Path:
    """Return the review root's wait journal, resolved where the emission happens."""
    return review_loop.review_root() / "waits.jsonl"


# Mirrors `dispatch.DISPATCH_ROOT` (`tools/dispatch.py` owns the shape); stated here so a
# reader of this module needs no second file to know where records live. The CLI takes
# `--dispatch-dir` for the tests and for reading a preserved evidence tree.
DISPATCH_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"
# A commit is named in full or not at all: a shortened SHA names several commits, and a
# binding that could mean two commits satisfies neither.
FULL_SHA: Final = worktree.FULL_COMMIT_SHA
# The diff identity is a sha256 hexdigest (64 lowercase hex), so the binding's second
# half is spelled as strictly as its first — tagged `binary:` where the diff it hashes
# changes a binary file, which is the fact `satisfies` refuses a carry on (#419).
BINARY_DIFF_TAG: Final = "binary:"
DIFF_ID: Final = re.compile(rf"\A(?:{BINARY_DIFF_TAG})?[0-9a-f]{{64}}\Z")
# `breaker.OK`, mirrored rather than imported so the completion ladder stays a local
# decision over the records it reads (`tools/breaker.py` owns the vocabulary, and
# `classify_run` is what ties `ok` to a zero exit behind `write_result`).
OUTCOME_OK: Final = "ok"
SHA_ERROR: Final = worktree.COMMIT_SHA_ERROR
DIFF_ID_ERROR: Final = (
    "a verdict carries the 64-hex exact diff identity of the reviewed diff, tagged"
    " `binary:` where that diff changes a binary file"
)
ISSUE_ERROR: Final = "the issue is named by its number, greater than zero"
VERSION_ERROR: Final = "a verdict must be a version 1 object"
WALK_WITHOUT_REFUSAL_ERROR: Final = "the candidate walk ended without a refusal or a verdict"

SAME_USER_LIMIT: Final = (
    "limit=every dispatch runs as the same user, so this record protects against the"
    " accident and the shortcut, not against a deceptive agent — a convention with a"
    " mechanical floor, not a guarantee (ADR-0071 ruling 4)"
)
SHA_BINDING_NOTE: Final = (
    "binding=this verdict satisfies the SHA it names, or a moved SHA where the move"
    " is a chain of clean rebases the tools recorded and the diff's exact identity"
    " still matches — a hand-resolved replay is unproven and needs a new review"
)
DIFF_ID_LIMIT: Final = (
    "limit=matching identity plus recorded clean rebases proves the diff is unchanged"
    " and mechanically replayed, not that its meaning survived the move onto the new"
    " base — the gate's tests at landing are what catch that difference, and they"
    " still run (#417)"
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
        # Bounded (#434): the push dials before the already-bounded `remote_ref_sha`
        # on the next line, so a wedged remote hung the push the read was bounded
        # against. A timeout lands in the `git_failed` refusal below like any other.
        worktree.git(
            "push",
            "--force",
            "origin",
            f"HEAD:{ref}",
            cwd=cwd,
            timeout=worktree.REMOTE_READ_TIMEOUT_S,
        )
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
    # The wait the handover opens (#484): from here until the verdict is recorded, the
    # work is waiting on its reviewer, and that interval starts at this success — the
    # one moment the loop is the writer of the fact. Fail-open like every family.
    attribute_registry.emit_wait(
        attribute_registry.wait_event(
            attribute_registry.REASON_WAITING_REVIEWER,
            "review",
            datetime.now(tz=UTC).timestamp(),
            issue=issue,
        ),
        journal=wait_journal(),
    )
    # The same success is the pipeline's exchange stage reached (#490), recorded with its
    # first-pass status against the issue's own stage journal. The dispatch id names the
    # implementer's session where the environment carries one, so a re-run inside that
    # session is the same arrival rather than rework; an exchange by hand has none and
    # counts, which is the journal's honest reading of the act. The seat filter is the
    # one the gate and land seams carry (#552, #490 round 2's F2): `CTI_DISPATCH_SEAT`
    # is exported to every dispatched child, and a dispatched non-pipeline seat running
    # an exchange is not the item's exchange arrival — unlikely to be reached is a
    # weaker guarantee than the filter, and the three seams read alike.
    seat = os.environ.get("CTI_DISPATCH_SEAT", "")
    if not seat or attribute_registry.STAGE_OF_SEAT.get(seat) == "implementation":
        attribute_registry.record_stage_arrival(
            "exchange",
            issue,
            review_loop.review_root(),
            datetime.now(tz=UTC).timestamp(),
            dispatch_id=os.environ.get("CTI_DISPATCH_ID", ""),
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


# ------------------------------------------------------------------ the diff identity

# What names the base inside a unified diff is narrower than a line: the line-number
# ranges of a hunk header (`@@ -12,3 +14,3 @@ def anchor()`) shift whenever a sibling
# lands above the change, while everything after them — the function or section
# anchor — is content, and erasing the whole header made the same edit in two
# different functions hash equal (round 3's Critical, one half). So only the ranges
# are flattened and the anchor is kept. An `index` line's base-side blob hash is
# rewritten by any sibling edit of the same textual file, so it is flattened there —
# but a binary change's `index` line is the only content its diff carries at all, and
# it stays byte for byte, because erasing the line made different binary changes to
# one path hash equal (round 3's Critical, other half). A kept line is base-naming,
# and the argument that it was safe anyway — git will not merge binaries, so a
# same-file binary edit cannot replay clean — is false: `.gitattributes` decides both
# halves, and `*.bin -diff merge=union` gives a diff git calls binary and a same-file
# edit git replays clean, moving both blob hashes (#419). So the identity of a diff
# carrying a binary change is tagged `BINARY_DIFF_TAG` and never carries across a
# moved SHA at all: `satisfies` refuses it by name and a fresh review is owed.
# Everything else —
# content lines with their whitespace exact, file order, hunk order, mode lines — is
# hashed byte for byte. One limit, fail-closed: a clean rebase can still shift the
# anchor itself where a sibling lands a function-like line between the old anchor and
# the change, and that refuses a carry rather than granting one.
HUNK_RANGES: Final = re.compile(r"\A@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
INDEX_LINE: Final = re.compile(r"\Aindex [^\n]*")
BINARY_FOLLOWS: Final = ("Binary files ", "GIT binary patch")


def _has_binary_change(diff: str) -> bool:
    """Whether any file in this diff changed as bytes rather than as lines."""
    return any(line.startswith(BINARY_FOLLOWS) for line in diff.splitlines())


def _normalised_diff(diff: str) -> str:
    """Return the diff with base-naming numbers flattened, keeping content byte-exact."""
    lines: list[str] = []
    pending_index: str | None = None
    for line in diff.splitlines(keepends=True):
        if pending_index is not None:
            # What follows decides: a binary change keeps its `index` line (the only
            # content it has); a textual or mode-only one flattens it.
            lines.append(pending_index if line.startswith(BINARY_FOLLOWS) else "index\n")
            pending_index = None
        if INDEX_LINE.match(line):
            pending_index = line
        else:
            lines.append(HUNK_RANGES.sub("@@", line))
    if pending_index is not None:  # a diff ending on an index line flattens it too
        lines.append("index\n")
    return "".join(lines)


def diff_id_of(cwd: Path, sha: str) -> str | Refusal:
    """Return the exact diff identity of `origin/main...<sha>` — the range `just land` lands.

    The one home of the range and of the normalisation, so the record at `record`
    time and the comparison at landing cannot each keep a version of either:
    merge-base relative, like the landing's own path and gate inputs, so a candidate
    diff cannot widen what is hashed; `--unified=0`, so no context line enters it and
    an upstream edit beside the branch's own lines cannot change the identity — the
    disproof of the first #417 build, whose stable patch-id hashed context and so
    re-reviewed every branch a sibling had landed near; and sha256 of the exact
    bytes, so whitespace is significant — the other disproof, where `git patch-id
    --stable` stripped trailing whitespace and a resolution the reviewer never saw
    hashed equal to the reviewed diff. Hunk offsets are normalised away and the
    section anchor after them kept, and an `index` line is flattened for a textual
    file and kept whole for a binary one (`_normalised_diff`), because offsets and a
    textual file's base-side blob hash name the base, which a clean rebase moves by
    construction — while a binary change's `index` line is the only content it has.
    That kept line is itself base-naming, and `.gitattributes` can make a same-file
    binary edit replay clean and move it (#419), so the identity of a diff carrying
    a binary change is returned tagged `BINARY_DIFF_TAG` and `satisfies` refuses to
    carry it across a moved SHA. A diff identity is a claim about the change, never
    about whether the rebase that produced it was clean — that half is the recorded
    links' (`carried_by_clean_rebase`), and the two are checked together. The limit
    is `DIFF_ID_LIMIT`'s and is printed wherever a clearance rides it.

    Fail-closed on the one way this could not run — git's own failure — as
    `diff_id_unreadable`, because a check that could not run is not a check that
    passed (#41).
    """
    try:
        diff = worktree.git("diff", "--unified=0", f"{worktree.BASE}...{sha}", cwd=cwd)
    except worktree.GitError as failure:
        return Refusal(
            "diff_id_unreadable",
            (
                f"worktree={cwd}",
                f"command=git {' '.join(failure.args_run)}",
                f"stderr={failure.stderr}",
            ),
            "The diff this identity would hash could not be read. Read git's words"
            " above — a commit this tree does not hold arrives with `git fetch origin"
            " refs/heads/issue-<n>` — and a check that could not run is not a check"
            " that passed (#41).",
        )
    digest = hashlib.sha256(_normalised_diff(diff).encode("utf-8")).hexdigest()
    return BINARY_DIFF_TAG + digest if _has_binary_change(diff) else digest


# ------------------------------------------------------------- the clean-rebase links


class RebaseLink(NamedTuple):
    """One clean rebase this project's tooling ran: from `before` onto `base`, giving `after`.

    The provenance half of #417's binding. `just land --stage` and `just land` write
    one after each rebase they run to completion without conflict, because the rebase
    is the only party that knows its own outcome: hashing the output — patch-id,
    diff identity, anything — cannot prove whether conflict resolution occurred, and
    the record at the source can. A rebase a hand ran, however faithfully, leaves no
    link, and a verdict therefore never carries across it.
    """

    before: str
    after: str
    base: str
    at: str


REBASES_FILE: Final = "rebases.json"
REBASES_ERROR: Final = "a rebase link carries full SHAs as before, after and base, and an instant"


def rebase_links_path(review_root: Path, issue: int) -> Path:
    """Return where an issue's recorded clean rebases live — per issue, beside the loop state."""
    return review_root.expanduser() / str(issue) / REBASES_FILE


def _rebase_link(raw: object) -> RebaseLink:
    """Validate one link record, refusing any shape a walk could misread."""
    if not isinstance(raw, dict):
        raise ReviewExchangeError(REBASES_ERROR)
    link = RebaseLink(
        before=str(raw.get("before", "")),
        after=str(raw.get("after", "")),
        base=str(raw.get("base", "")),
        at=str(raw.get("at", "")),
    )
    if not all(FULL_SHA.fullmatch(sha) for sha in (link.before, link.after, link.base)):
        raise ReviewExchangeError(REBASES_ERROR)
    if not link.at:
        raise ReviewExchangeError(REBASES_ERROR)
    return link


def _parsed_rebases(text: str) -> tuple[RebaseLink, ...]:
    """Parse a whole links document, raising on any shape a walk could misread."""
    document = json.loads(text)
    if not isinstance(document, list):
        raise ReviewExchangeError(REBASES_ERROR)
    return tuple(_rebase_link(item) for item in document)


def read_rebases(review_root: Path, issue: int) -> tuple[RebaseLink, ...] | Refusal:
    """Read an issue's recorded clean rebases; absent is no links, unreadable refuses.

    The absent file is the common case — no tooling rebase has run for this issue —
    and answers an empty tuple, not a refusal: emptiness is a fact the walk turns
    into "unproven" only where a carry would have ridden it. A file that exists and
    will not parse is the one `rebase_unproven` with the reason on it, because the
    link that would prove the carry could be the entry that will not open (#41).
    """
    path = rebase_links_path(review_root, issue)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except OSError as failure:
        return Refusal(
            "rebase_unproven",
            (f"links={path}", f"reason={type(failure).__name__}: {failure}"),
            "The recorded clean rebases could not be read, so the provenance a verdict"
            " would carry across on is not an answer any record can give. A check that"
            " could not run is not a check that passed (#41).",
        )
    try:
        return _parsed_rebases(text)
    except (ValueError, ReviewExchangeError) as failure:
        return Refusal(
            "rebase_unproven",
            (f"links={path}", f"reason={type(failure).__name__}: {failure}"),
            "The recorded clean rebases will not parse, so the provenance a verdict"
            " would carry across on is not an answer any record can give. Repair the"
            " record or re-stage — a check that could not run is not a check that"
            " passed (#41).",
        )


def record_rebase(
    review_root: Path,
    issue: int,
    link: RebaseLink,
) -> None:
    """Append one clean-rebase link, atomically. Raises `OSError` where it cannot write.

    The caller is the rebase that just ran clean (`just land --stage`, `just land`);
    the link states what it replayed, onto what, and what that produced. Nothing is
    derived here — the tool that ran the rebase is the only writer there can be, and
    `at` is the instant it records. A write that fails leaves the chain unproven, and
    the landing's rung refuses the carry on its own; the caller prints why.
    """
    path = rebase_links_path(review_root, issue)
    read = read_rebases(review_root, issue)
    if isinstance(read, Refusal):
        # An unreadable links file is never appended to silently: writing over it
        # would replace provenance the walk might have needed. Refuse by raising the
        # same fact the walk will raise; the caller turns it into a printed line.
        message = f"{path}: {read.action}"
        raise OSError(message)
    existing = read
    document = [*existing, link]
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f"{REBASES_FILE}.staging")
    payload = [
        {"before": item.before, "after": item.after, "base": item.base, "at": item.at}
        for item in document
    ]
    staged.write_text(json.dumps(payload), encoding="utf-8")
    staged.replace(path)


def carried_by_clean_rebase(links: tuple[RebaseLink, ...], from_sha: str, to_sha: str) -> bool:
    """Whether recorded clean rebases connect `from_sha` to `to_sha`, by any chain of them.

    Reachability, not a single link: a branch can be staged, land-refused, and
    re-rebased by the next `just land`, and the verdict binds the first of those
    commits — every hop the tooling ran clean must count, and every hop anything else
    produced (a hand's rebase, a new commit, an amend) breaks the chain by leaving no
    link with its `after` to walk through. `from_sha == to_sha` needs no link: that
    is the SHA match `satisfies` has already cleared on.
    """
    reached = {from_sha}
    grew = True
    while grew:
        grew = False
        for link in links:
            if link.before in reached and link.after not in reached:
                reached.add(link.after)
                grew = True
    return to_sha in reached


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
    entry: Path, issue: int, reviewed_sha: str | None
) -> _Record | str:
    """Classify one dispatch directory against the binding being derived.

    `"past"` for a record this scan walks past — another seat, another issue, and
    another SHA where one was named — and a `_Record` for a candidate.
    `reviewed_sha=None` widens the scan to every review this issue has had, which is
    what the carry half of #417 needs: the binding dispatch of a carried verdict
    names the pre-rebase SHA, not the one landing. Every way of not being able to
    read a review-seat record on this issue returns `"unreadable"` instead, because
    the record that would not open could be the binding one: an exclusion can
    continue on a partial read (#322), an answer cannot.
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
    if reviewed_sha is not None and base_sha != reviewed_sha:
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


def _binding_result_document(  # noqa: PLR0911 — one return per named result state in this ladder
    document: dict[str, object],
) -> _Result | str:
    """Classify one parsed result document for binding purposes."""
    # The stop closeout has one shape-home, `dispatch_stop.is_stop_closeout`,
    # shared with `occupancy.py` and `observatory.py` (#558).
    if dispatch_stop.is_stop_closeout(document):
        return _Result(completed=False, state="result=not_a_result:stopped")
    refused = "refusal" in document
    ended = isinstance(document.get("ended_at"), str) and bool(document["ended_at"])
    ran = "returncode" in document
    outcome = document.get("outcome")
    if refused and ran:
        return "unreadable"
    if refused:
        return _Result(completed=False, state="result=refusal")
    if not ran or not isinstance(outcome, str) or not outcome:
        # A result beside a returncode carries a typed outcome, always — this is
        # not a shape `write_result` produces, so it is not a fact this scan reads.
        return "unreadable"
    if outcome != OUTCOME_OK:
        return _Result(completed=False, state=f"result=not_a_result:{outcome}")
    if not ended:
        return "unreadable"
    return _Result(completed=True, state="result=completed")


def _binding_result(entry: Path) -> _Result | str:
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
    document = entry / "result.json"
    if not document.is_file():
        return _Result(completed=False, state="result=absent")
    try:
        read = json.loads(document.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return "unreadable"
    if not isinstance(read, dict):
        return "unreadable"
    return _binding_result_document(read)


def _completed_candidates(
    dispatch_root: Path, issue: int, reviewed_sha: str | None
) -> tuple[_Record, ...] | Refusal:
    """Every completed review dispatch on this issue, in latest-first order.

    The scan half of `derive_binding` and of `bound_verdict`, so the two readers
    cannot grow different ideas of what a candidate is. `reviewed_sha` narrows the
    candidates to the reviews of one commit; `None` takes the issue's reviews whole,
    which is what a landing whose SHA moved needs (#417). Ordered latest-first by
    plan time (ties by id, so the order is one order).
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
    return tuple(
        sorted(candidates, key=lambda record: (record.planned_at, record.dispatch_id), reverse=True)
    )


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
    scanned = _completed_candidates(dispatch_root, issue, reviewed_sha)
    if isinstance(scanned, Refusal):
        return scanned
    candidates = scanned
    if not candidates:
        return Refusal(
            "no_review_dispatch",
            (f"issue={issue}", f"reviewed_sha={reviewed_sha}"),
            "No completed review dispatch record binds this commit — seat=review,"
            f" issue={issue}, base_sha=this SHA. Dispatch the reviewer first"
            " (`just dispatch --seat review --reviewing <profile> --base-sha <sha>`)",
        )
    chosen = candidates[0]
    return Bound(
        dispatch_id=chosen.dispatch_id,
        profile=chosen.profile,
        lane=chosen.lane,
        planned_at=chosen.planned_at,
        # Latest-first candidates reversed back to chronological, so `alternates` stays
        # oldest-first as it was when the sort ran the other way.
        alternates=tuple(record.dispatch_id for record in reversed(candidates[1:])),
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
    diff_id: str
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
        "diff_id": verdict.diff_id,
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
    diff_id = document.get("diff_id")
    dispatch = document.get("review_dispatch")
    profile = document.get("reviewer_profile")
    lane = document.get("reviewer_lane")
    recorded_at = document.get("recorded_at")
    if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
        raise ReviewExchangeError(ISSUE_ERROR)
    if not isinstance(reviewed_sha, str) or not FULL_SHA.fullmatch(reviewed_sha):
        raise ReviewExchangeError(SHA_ERROR)
    if not isinstance(diff_id, str) or not DIFF_ID.fullmatch(diff_id):
        raise ReviewExchangeError(DIFF_ID_ERROR)
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
        diff_id=diff_id,
        review_dispatch=dispatch,
        reviewer_profile=profile,
        reviewer_lane=lane,
        findings=findings,
        recorded_at=recorded_at,
        alternates=tuple(alternates),
    )


def _lacks_diff_id(path: Path) -> bool:
    """Whether a verdict that failed to parse is a version-1 record with no diff identity.

    The migration discriminator: a record the rework predates carries a `patch_id`
    (the first #417 build) or no identity field at all, and either is the one-time
    `diff_id_unreadable` re-review rather than the generic corrupt-record refusal —
    so the reader is told to re-review under the rule that now governs instead of
    hunting a corruption that is not there. Anything that is not that shape — a
    broken JSON document, another missing field — answers `False` and keeps the
    `verdict_unreadable` it deserves.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(document, dict) or document.get("version") != 1:
        return False
    return not isinstance(document.get("diff_id"), str) or not DIFF_ID.fullmatch(
        document["diff_id"]
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


def record_verdict(  # noqa: PLR0911, PLR0913 — one refusal per way a record can be wrong, one parameter per fact the writer owns
    issue: int,
    reviewed_sha: str,
    findings_text: str,
    dispatch_root: Path,
    *,
    diff_id: str,
    now: str | None = None,
) -> Recorded | Refusal:
    """Derive the reviewing identity and write the verdict beside that dispatch.

    The caller supplies the four things it owns — the issue, the reviewed SHA, the
    findings, the diff identity of the reviewed diff as `diff_id_of` computes it — and
    nothing about who reviewed. The identity comes from `derive_binding`, the same
    derivation `show` re-runs later, so a verdict never carries an identity some
    caller typed. The diff identity is caller-supplied at this seam and forgeable, and
    that buys nothing: the landing computes its own identity from its own tree and
    compares, so a forged record only ever fails the comparison. Writing is once,
    atomically: the file is created exclusively (`_write_verdict_once`), so a verdict
    that already exists where this one would land refuses `verdict_exists`, because
    the finding list is the one field a re-record could quietly swap.
    """
    if issue <= 0:
        return Refusal(
            "invalid_issue", (f"issue={issue}",), "Name the issue the review was dispatched on."
        )
    if invalid := worktree.invalid_commit_sha(reviewed_sha, field="reviewed_sha"):
        return invalid
    if not isinstance(diff_id, str) or not DIFF_ID.fullmatch(diff_id):
        return Refusal(
            "invalid_diff_id",
            (f"diff_id={diff_id!r}", DIFF_ID_ERROR),
            f"Record the diff identity `diff_id_of` returns — {DIFF_ID_ERROR}. A verdict"
            " without one can never carry across a rebase, and an unreadable one is a"
            " refusal, never a pass (#41).",
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
        diff_id=diff_id,
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


def satisfies(  # noqa: PLR0911 — one return per way a binding can fail, so no refusal hides inside another
    verdict: Verdict,
    sha: str,
    diff_id: str | Refusal | None = None,
    *,
    clean_rebase: bool | Refusal | None = None,
) -> Refusal | None:
    """Whether this verdict binds the commit asked about — `None` when it does.

    The SHA first — a verdict always satisfies the commit it names — and where the
    SHA has moved, two facts that must **both** hold (#417, reworked): the move is a
    chain of clean rebases the tooling recorded (`clean_rebase`, the walk's answer
    over the recorded links, or the `Refusal` that says the links could not be
    read), and the landing diff's identity equals the recorded one (`diff_id`, the
    landing's own computation, or the `Refusal` that says it could not run). Either
    alone is insufficient: an identical diff reached by a hand-resolved rebase is
    unproven, and a tool-run clean rebase can still drop a commit as already
    upstream. **A diff carrying a binary change is not carried at all**, whatever
    those two say (`binary_diff_uncarried`, #419): its identity is nothing but blob
    hashes that name the base, and `.gitattributes` can make a same-file binary edit
    replay clean and move them, so both answers are uninformative rather than one of
    them wrong. Binary changes are rare here, so what that costs is one fresh review.
    The refusal names which half failed rather than returning a bare
    false, because the caller that needs it is a landing gate: "not this one" must
    say which one it is before anyone re-reviews, and a quiet miss is how an amended
    branch rides an earlier approval.

    **The record's own identity is validated before the SHA clears** (review round
    on the first build, Medium): a verdict whose `diff_id` is absent or malformed
    used to clear on the exact-SHA path without the field ever being read, so a
    missing identity passed. It refuses `diff_id_unreadable` whatever the SHA — the
    record is corrupt, and a verdict recorded before #417's rework (which carries a
    `patch_id`, or nothing) meets this refusal too: that is the one-time migration,
    a fail-closed re-review of every verdict the rework predates. An identity that
    could not be computed on the landing side is the same refusal, consulted only
    where the SHA has moved and it would have carried (#41).
    """
    if not isinstance(verdict.diff_id, str) or not DIFF_ID.fullmatch(verdict.diff_id):
        return Refusal(
            "diff_id_unreadable",
            (
                f"asked={sha}",
                f"reviewed={verdict.reviewed_sha}",
                f"dispatch={verdict.review_dispatch}",
                f"recorded_diff_id={verdict.diff_id!r}",
            ),
            "The verdict's diff identity is not an identity at all — "
            f"{DIFF_ID_ERROR}. A verdict recorded before #417's rework (a `patch_id`"
            " field, or none) meets this refusal: its one-time migration is a"
            " fail-closed re-review. Repair the record by re-recording the verdict;"
            " a check that could not run is not a check that passed (#41).",
        )
    if verdict.reviewed_sha == sha:
        return None
    if isinstance(diff_id, Refusal):
        return Refusal(
            "diff_id_unreadable",
            (
                f"asked={sha}",
                f"reviewed={verdict.reviewed_sha}",
                f"dispatch={verdict.review_dispatch}",
                *diff_id.found,
            ),
            "The SHA has moved and the landing diff's identity could not be computed,"
            " so the half of the binding that carries a review across a rebase could"
            " not run. "
            + diff_id.action
            + " A check that could not run is not a check that passed (#41).",
        )
    if not isinstance(diff_id, str) or not DIFF_ID.fullmatch(diff_id):
        return Refusal(
            "diff_id_unreadable",
            (
                f"asked={sha}",
                f"reviewed={verdict.reviewed_sha}",
                f"dispatch={verdict.review_dispatch}",
                f"landing_diff_id={diff_id!r}",
            ),
            "The SHA has moved and the landing diff's identity was not supplied, so"
            " the half of the binding that carries a review across a rebase could not"
            " run. Compute it where the landing tree is (`diff_id_of`) — a check that"
            " could not run is not a check that passed (#41).",
        )
    if diff_id.startswith(BINARY_DIFF_TAG) or verdict.diff_id.startswith(BINARY_DIFF_TAG):
        return Refusal(
            "binary_diff_uncarried",
            (
                f"asked={sha}",
                f"reviewed={verdict.reviewed_sha}",
                f"dispatch={verdict.review_dispatch}",
                f"binary=asked={diff_id} reviewed={verdict.diff_id}",
            ),
            "The SHA has moved and the diff changes a file git compares as bytes, so"
            " the verdict is not carried and a fresh review is owed. A binary change's"
            " diff has no content at all beyond the two blob hashes on its `index`"
            " line, and those name the base: `.gitattributes` decides both what git"
            " calls binary and how git merges it, so a same-file binary edit can"
            " replay clean and move them (#419). An identity that survived would prove"
            " nothing here, and one that moved would be base-dependence rather than a"
            " changed diff — so neither answer is read. Re-review at the commit being"
            " landed.",
        )
    if isinstance(clean_rebase, Refusal):
        return clean_rebase
    if clean_rebase is not True:
        return Refusal(
            "rebase_unproven",
            (
                f"asked={sha}",
                f"reviewed={verdict.reviewed_sha}",
                f"dispatch={verdict.review_dispatch}",
                (
                    f"diff_id={'match' if diff_id == verdict.diff_id else 'mismatch'}"
                    f" asked={diff_id} reviewed={verdict.diff_id}"
                ),
                "clean_rebase=no recorded chain connects the reviewed commit to this one",
            ),
            "The diff may be the diff reviewed, but nothing records that this"
            " commit reached here by rebases the tooling ran clean — and the rebase"
            " is the only party that knows whether a hand resolved anything, which is"
            " why the fact is recorded at the source and never inferred from the"
            " diff. Re-review what is being landed. " + SHA_BINDING_NOTE + ".",
        )
    if diff_id == verdict.diff_id:
        return None
    return Refusal(
        "sha_mismatch",
        (
            f"asked={sha}",
            f"reviewed={verdict.reviewed_sha}",
            f"dispatch={verdict.review_dispatch}",
            "sha=mismatch",
            f"diff_id=mismatch asked={diff_id} reviewed={verdict.diff_id}",
            (
                "clean_rebase=recorded (the diff changed under it — a commit dropped as"
                " already upstream, or content the replay reshaped)"
            ),
        ),
        "The commit is not the one reviewed and the diff is not the diff reviewed,"
        " though the rebases between them ran clean. "
        + SHA_BINDING_NOTE
        + ". Re-review what is being landed.",
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
    keeping a copy of how a verdict binds. `carried_by_diff` names which half of
    #417's binding cleared — `False` for the SHA the verdict names, `True` where the
    SHA had moved and the recorded clean rebases plus the diff's identity carried the
    review across — so a clearance prints the identity limit exactly where it applied
    and a SHA-matched one prints nothing it does not owe.
    """

    verdict: Verdict
    binding: Bound
    carried_by_diff: bool


def bound_verdict(  # noqa: C901, PLR0911, PLR0912 — one branch and one return per way a record can fail to bind, as the landing's own ladder has
    issue: int,
    sha: str,
    dispatch_root: Path,
    diff_id: str | Refusal | None = None,
    rebase_links: tuple[RebaseLink, ...] | Refusal | None = None,
) -> BoundVerdict | Refusal:
    """Read the verdict that binds one issue's commit, or the refusal that stops it.

    The whole derivation in one call, in the order the landing's rung climbs it: the
    candidates from the dispatch records, the record beside each, the item it names,
    the SHA or the diff-plus-provenance that satisfies it (#417), and the identity
    re-derived rather than believed. The candidates are this issue's completed
    reviews, latest first, not only the ones bound to `sha` — a landing whose rebase
    moved the SHA is bound to the review of the pre-rebase commit, and the recorded
    clean rebases plus the diff identity are what carry it — and the first verdict
    that satisfies wins, so the newest review that judged either this commit or this
    diff is the one that clears. `rebase_links` is the caller's read of the issue's
    recorded links (`read_rebases`), or the `Refusal` that says they could not be
    read; `None` — the `review-loop sync` shape — walks no chain, and a moved SHA
    therefore refuses `rebase_unproven` there, which is correct: a loop folds from
    the verdict's own commit or not at all. It lives here rather than beside either
    caller because both #334's landing rung and #333's `review-loop sync` need
    the *same* verdict — a loop opened from anything else would be a record of
    findings no verdict is on the hook for, and a landing cleared against a different
    one would be a landing cleared by a review of another commit.
    """
    scanned = _completed_candidates(dispatch_root, issue, None)
    if isinstance(scanned, Refusal):
        return scanned
    candidates = scanned
    if not candidates:
        return Refusal(
            "no_review_dispatch",
            (f"issue={issue}", f"sha={sha}"),
            "No completed review dispatch record binds this issue's work — seat=review,"
            f" issue={issue}. Dispatch the reviewer first (`just dispatch --seat review"
            " --reviewing <profile> --base-sha <sha>`)",
        )
    mismatch: Refusal | None = None
    for candidate in candidates:
        try:
            path = verdict_path(dispatch_root, candidate.dispatch_id)
        except ReviewExchangeError as error:
            return Refusal(
                "records_unreadable",
                (f"dispatch={candidate.dispatch_id}", f"reason={error}"),
                "The reviewing dispatch's id cannot name its own verdict record, and the"
                " record that would not open could be the binding one — so no verdict is"
                " read (#41).",
            )
        if not path.is_file():
            return Refusal(
                "no_verdict",
                (f"dispatch={candidate.dispatch_id}", f"expected={path}"),
                "The review dispatch completed but no verdict record sits beside its plan."
                " Record the verdict (`just review record`) — a completed review whose"
                " judgement no one can read clears nothing (#41).",
            )
        provenance: bool | Refusal | None = None
        try:
            verdict = parse_verdict(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            # A version-1 record whose identity field predates #417's rework — a
            # `patch_id`, or nothing — is named as what it is rather than folded into
            # "will not parse": the one-time migration, a fail-closed re-review.
            if isinstance(error, ReviewExchangeError) and _lacks_diff_id(path):
                return Refusal(
                    "diff_id_unreadable",
                    (f"verdict={path}", f"reason={error}"),
                    "The verdict record carries no diff identity — it predates #417's"
                    " rework (a `patch_id` field, or none), and its one-time migration"
                    " is a fail-closed re-review of the diff under the rule that now"
                    " governs (#41).",
                )
            return Refusal(
                "verdict_unreadable",
                (f"verdict={path}", f"reason={error}"),
                "The verdict record exists but will not parse. Repair or re-record it — a"
                " check that could not run is not a check that passed (#41).",
            )
        if verdict.issue != issue:
            return Refusal(
                "review_issue_mismatch",
                (f"asked_issue={issue}", f"verdict_issue={verdict.issue}", f"verdict={path}"),
                "This verdict judges another item's work. A verdict satisfies only the item"
                " and the diff it names, so record one for this item's commit.",
            )
        if isinstance(rebase_links, tuple):
            provenance = carried_by_clean_rebase(rebase_links, verdict.reviewed_sha, sha)
        else:
            provenance = rebase_links
        mismatch = satisfies(verdict, sha, diff_id, clean_rebase=provenance)
        if mismatch is None:
            # The identity is derived against the verdict's own commit, never the
            # landing's moved one: the dispatch records name what was reviewed, and
            # `derive_binding` over that SHA is the derivation that wrote the record.
            binding = derive_binding(issue, verdict.reviewed_sha, dispatch_root)
            if isinstance(binding, Refusal):
                return binding
            forged = identity_mismatch(verdict, binding)
            if forged is not None:
                return forged
            return BoundVerdict(verdict, binding, carried_by_diff=verdict.reviewed_sha != sha)
    if mismatch is None:
        # Unreachable in a walk that had candidates: every iteration either returns
        # or sets `mismatch`, and the empty-candidates case returned above. Stated as
        # a raise rather than an assert because this module runs outside pytest.
        raise ReviewExchangeError(WALK_WITHOUT_REFUSAL_ERROR)
    return mismatch


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
            f"diff_id={verdict.diff_id}",
            f"findings={len(verdict.findings)}",
            f"alternates={' '.join(verdict.alternates) or 'none'}",
            f"verdict={path}",
            SHA_BINDING_NOTE,
            DIFF_ID_LIMIT,
            SAME_USER_LIMIT,
        ),
        0,
    )


def _reviewed_commit_refusal(repo: Path, sha: str) -> Refusal | None:
    """Validate form before fetching, then ask whether the commit exists."""
    if invalid := worktree.invalid_commit_sha(sha, field="reviewed_sha"):
        return invalid
    # Bounded (#434), the same deadline every other read of `origin` in this protocol
    # carries; a wedged remote refuses as `git_failed` rather than hanging the record.
    worktree.git("fetch", "origin", cwd=repo, timeout=worktree.REMOTE_READ_TIMEOUT_S)
    return worktree.validate_commit(repo, sha)


def _show(  # noqa: PLR0911 — one return per refusal, so each stays a whole thought
    dispatch_id: str,
    dispatch_root: Path,
    review_root: Path,
    satisfies_sha: str,
    diff_id: str | None,
) -> Report:
    """Read one verdict, re-derive its identity, and answer any satisfaction question.

    `diff_id` is the asking side's own diff as `diff_id_of` computes it, and the
    recorded clean rebases are read from `review_root` — together they are what let
    `--satisfies` answer `yes` for a commit a rebase produced; without either, a
    moved SHA refuses (`diff_id_unreadable`, `rebase_unproven`), the honest "this
    comparison could not run" and "this move is not proven" respectively. A
    `binary:`-tagged identity on either side refuses `binary_diff_uncarried` (#419) —
    the tag rides the recorded value, so a paste answers as the landing gate does.
    """
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
        if isinstance(error, ReviewExchangeError) and _lacks_diff_id(path):
            return Report.refused(
                Refusal(
                    "diff_id_unreadable",
                    (f"verdict={path}", f"found={type(error).__name__}: {error}"),
                    "The verdict record carries no diff identity — it predates #417's"
                    " rework (a `patch_id` field, or none), and its one-time migration"
                    " is a fail-closed re-review (#41).",
                )
            )
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
        f"diff_id={verdict.diff_id}",
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
        links = read_rebases(review_root, verdict.issue)
        clean = (
            links
            if isinstance(links, Refusal)
            else carried_by_clean_rebase(links, verdict.reviewed_sha, satisfies_sha)
        )
        mismatch = satisfies(verdict, satisfies_sha, diff_id, clean_rebase=clean)
        if mismatch is not None:
            return Report.refused(mismatch)
        if verdict.reviewed_sha != satisfies_sha:
            lines.append(f"satisfies={satisfies_sha} yes carried_by=diff_id")
            lines.append(DIFF_ID_LIMIT)
        else:
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
        "--repo",
        default=str(Path.cwd()),
        help="a git repository holding the reviewed commit and `origin` (fetches first)",
    )
    write.add_argument(
        "--dispatch-dir", default=str(DISPATCH_ROOT), help="the dispatch records' root"
    )

    read = actions.add_parser("show", help="read a verdict and re-derive its identity")
    read.add_argument("dispatch_id", help="the review dispatch id")
    read.add_argument("--satisfies", metavar="SHA", help="ask whether it satisfies this commit")
    read.add_argument(
        "--diff-id",
        metavar="ID",
        help="the asked commit's diff identity as `diff_id_of` computes it, so a moved"
        " SHA can answer through the diff it shares with the review",
    )
    read.add_argument(
        "--review-root",
        default=str(review_loop.REVIEW_ROOT),
        help="the review state directory holding the recorded clean rebases",
    )
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
                # The diff identity is computed here rather than passed in, because a
                # flag is a hand that retypes what git can say — the same mistype #319
                # paid for. The fetch is what makes the range honest: without it a
                # stale `origin/main` puts main's own commits inside the
                # merge-base-relative diff and the record would bind a diff nobody
                # reviewed.
                repo = Path(args.repo)
                try:
                    commit = _reviewed_commit_refusal(repo, args.reviewed_sha)
                except worktree.GitError as failure:
                    report = _git_failed(repo, failure)
                else:
                    if commit is not None:
                        report = Report.refused(commit)
                    else:
                        identity = diff_id_of(repo, args.reviewed_sha)
                        report = (
                            _record_report(
                                record_verdict(
                                    issue,
                                    args.reviewed_sha,
                                    Path(args.findings).read_text(encoding="utf-8"),
                                    Path(args.dispatch_dir),
                                    diff_id=identity,
                                )
                            )
                            if isinstance(identity, str)
                            else Report.refused(identity)
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
            report = _show(
                args.dispatch_id,
                Path(args.dispatch_dir),
                Path(args.review_root),
                args.satisfies,
                args.diff_id,
            )
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
