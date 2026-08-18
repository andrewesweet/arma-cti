"""`just trial`: the pre-registration trial harness, and the close audit it reads (#328).

This module was `tools/admission.py`, and the bar it was named for is gone. What is left is
the machinery that pre-registers a question, accrues assessments against it one cycle at a
time, and refuses to read an absent check as a passing one — plus the close audit, which
exists because the trial's third criterion is a question about a landing's window.

## The bar was dropped, and that is a departure from a pre-registration

ADR-0071 ruling 6 drops the pre-registered admission bar and withdraws ADR-0061 Decision 6.
It is recorded here rather than only in the ADR because this is the file a reader arrives at
looking for the bar.

The bar was pre-registered **precisely so that observed lane behaviour could not move it**.
Every constant in it was quoted from the human's ruling of 2026-08-05T20:00Z and nothing in
it was derived, on the reasoning that a number which moves once the numbers are in is not a
pre-registration at all. It then **never adjudicated once across any of its routes**: every
route was still on probation when it was dropped, none admitted and none failed. Four routes
had a record at all, the fullest of them eight assessments against an `N` of ten; the rest
had none. No count of routes or of dispatches is quoted here on purpose — both moved
throughout the bar's life, so any figure would need a date beside it to be true, and the
durable fact does not.

Dropping a pre-registration after the observations are in is the move pre-registration
exists to prevent. It was taken knowingly, by the human's ruling, and it is written down as
a departure rather than left to be discovered as a silence. What was traded is an ex-ante
check that never ran for a retrospective one (#336's observatory) that cannot run yet.

## The orchestration trial is closed as inconclusive, and five criteria go unmeasured

#242 ruling 1's trial judged an orchestration seat at opus/high; ADR-0071 ruling 2 sets that
seat at opus/xhigh, so the accrued cycles cannot validate the new pair. `TRIAL_CLOSURE`
carries that closure, and the records are kept as history rather than cleared.

It is **not** restarted, and the observatory does not subsume it. The observatory measures
rework; the trial measured five orchestration-process criteria — honouring a freeze or a
reservation, refusing to treat a non-result as a result, a landing inside its dispatch's
window, a gated surface edited with approval or an ADR-0013 record, and a slack-carrying
ruling dispatched rather than transcribed — and it sees none of them. Those five now go
unmeasured. A criterion nobody measures is not a criterion nobody violates, and this is a
loss rather than a substitution. `just trial bar` prints the five by name so a reader meets
the list rather than the count.

## What the harness is, and what it still refuses

This is one closed trial's harness, with its bar id and criteria as code constants by
design, kept because its records are history. The harness itself has no opinion about
profiles or verdicts. It holds three properties, and each was a design constraint of the
ruling that created it — they survive the closure because they belong to pre-registration
rather than to the orchestration seat:

- **A failed trial never auto-reverts anything and never carries a failure class.** It is a
  finding for the human. `just dispatch` does not consult this module at all, so nothing
  here is found about a provider, a lane or the code under test.
- **The clock starts at an explicit act, not at this tool's existence.** `not_started` is a
  distinct state from `0/10`: a tool that began counting the moment it landed would quietly
  start its own clock.
- **The bar is immutable once the first assessment lands.** The criteria are code constants
  and the record carries the `bar_id` it was started under; a record under a different
  `bar_id` is refused, so amending the criteria means minting a new id and starting fresh —
  a human-only act, visible in the record and in git.

Three of the five criteria are mechanically checkable against artefacts; two are not, and
the tool says which. A criterion the tool cannot check must not display as passing, and the
count follows the list (ADR-0051): the standing prints what was tool-checked and what was
hand-asserted, separately.

## Names kept deliberately

The store is still `~/.arma-cti/admission/`, still reached through `CTI_ADMISSION_DIR`, and
the telemetry is still `cti.admission.trial.*` on `arma-cti-admission`. Those names are
wrong for what this module now is, and they are kept anyway: the trial's records are history
and renaming their home would orphan them, which is the one thing "kept as history" must not
mean. The wart is cheaper than the loss.

Generality is declined too, not deferred. A generic harness would parameterise the criteria,
contradicting the immutable code constants above, and no second consumer exists:
`tools/wip_trial.py` chose its own bar id, criteria, store and verdicts. Copying the pattern
again is the accepted cost; do not extract this closed trial's harness without a new ruling.

## The audit (#252)

`audit` computes what a close's landing claims can be: six checks over the closing comment,
each with its own verdict vocabulary, printed for a human to read and to quote. It lives
here because the trial's mechanical criterion 3 is exactly its `dispatch_window` check, and
a second tool would hold a second copy of it. It reimplements nothing it can call: the
window tests are `tools/ledger.py`'s from 7bc3f72 and are called, and `pool.json`'s green
reading is `tools/pool_merge.py`'s.

Two of its properties are refusals to overclaim, and they matter more than the list:

- a quoted gate block is reported `quoted` and never as proof the gate ran green. The paste
  **is** the evidence, and a tool cannot re-run history;
- the changelog check reports `undecidable` and has no input that makes it report `ok`,
  because whether a commit had user-visible effect is not decidable from its diff. #41's
  shape, and the same reason `just prereqs` reports `unknown`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from datetime import date as calendar_date
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `breaker.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes these importable. `ledger` carries the window tests
# the audit holds a quoted SHA against and `pool_merge` carries `pool.json`'s green
# reading; both are called rather than copied, and `tests/unit/test_trial_audit.py`
# fails if a second implementation of either appears here (#252). Neither imports this
# module, so there is no cycle to break. `queue_policy` carries the freeze the
# orchestration trial's first criterion reads, and it imports only `otel_event`, so the
# cycle argument holds for it too (#260). `gate` carries the in-world surface list this
# module's corpus check reads — its home since #328 — and imports only `routing_policy`.
import gate
import ledger
import otel_event
import pool_merge
import queue_policy

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

EXIT_REFUSED: Final = 1

# --------------------------------------------------- the vocabulary a criterion is judged in

# A criterion is met or it is not. There is no third state that passes: a criterion nobody
# judged is absent, and an absent criterion is refused rather than read as a pass (#41's
# shape — a check that could not run is not a check that passed).
MET: Final = "met"
NOT_MET: Final = "not_met"

# What a whole pre-registration amounts to. `RUNNING` is carried by the trial's own state
# below, because "not yet decided" is a property of the trial and not of a criterion.
CLEARED: Final = "cleared"
FAILED: Final = "failed"


# ----------------------------------------------------- what git can be asked about a landing

# The checkout this module reads commits out of. The in-world surface list used to live
# beside it; it moved to `tools/gate.py` with #328, because it is a property of what an
# in-world surface is rather than of the bar that once read it, and the gate derivation is
# its heaviest reader. This module calls `gate.touches_in_world` rather than keeping a
# second copy.
REPO: Final = Path(__file__).resolve().parents[1]


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


def landing_paths(repo: Path, sha: str) -> tuple[str, ...] | None:
    """Every path one commit touched, or `None` when git cannot answer for that commit.

    `None` and `()` are deliberately different answers. An empty tuple is a commit that
    touched nothing; `None` is a check that could not run, and every caller here refuses
    rather than reading that as a pass (#41).
    """
    if not sha:
        return None
    if (
        not git("cat-file", "-e", f"{sha}^{{commit}}", cwd=repo).strip()
        and not git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}", cwd=repo).strip()
    ):
        return None
    listed = git("show", "--name-only", "--pretty=format:", sha, cwd=repo)
    return tuple(line.strip() for line in listed.splitlines() if line.strip())


def touches_in_world(paths: Iterable[str]) -> tuple[str, ...]:
    """Name the in-world surfaces a landing touched, empty when it touched none.

    Delegated to `tools/gate.py`, which owns the list. Kept as a name here because the
    corpus check reads it and a reader of this module should not have to know where the
    list moved to follow that check.
    """
    return gate.touches_in_world(paths)


# --------------------------------------------------------------------------- the audit

# What one check answers. Every vocabulary below is its own check's, and no verdict is
# shared between two checks that mean different things by it — `absent` on `sha_on_main`
# is "the close names no commit", `absent` on `evidence` is "the close quotes no run
# directory", and reading either as the other would be the overclaim this exists to stop.
AUDIT_OK: Final = "ok"
AUDIT_ABSENT: Final = "absent"
AUDIT_NOT_ON_MAIN: Final = "not_on_main"
AUDIT_OUTSIDE_WINDOW: Final = "outside_window"
AUDIT_UNBOUNDED: Final = "unbounded"
AUDIT_OWED: Final = "owed"
AUDIT_NOT_OWED: Final = "not_owed"
AUDIT_PATH_MISSING: Final = "path_missing"
AUDIT_RED: Final = "red"
AUDIT_QUOTED: Final = "quoted"

# The one verdict every check may reach: this check could not run. It is never a pass (#41).
# Its sole non-test reader is `trial_window_verdict`, which asks the audit for
# `dispatch_window` and returns `""` rather than a verdict on anything it does not recognise,
# `undecidable` included. `trial_policy_verdict` and `trial_gated_verdict` read no `Audit` at
# all, and reach the same `""` from their own artefacts — so no criterion is ever met by a
# check that could not run, whichever of the three produced it. (The reader that used to be
# named here, `criteria_from_audit`, went with the bar.)
AUDIT_UNDECIDABLE: Final = "undecidable"

AUDIT_REF: Final = "origin/main"

AUDIT_CHECKS: Final = (
    "sha_on_main",
    "dispatch_window",
    "corpus_owed",
    "evidence",
    "gate_quoted",
    "changelog",
)

# A commit as a close writes one: abbreviated to seven or spelt in full, and never inside
# a longer word. Whether a token *is* a commit is then asked of git rather than of the
# sentence around it — an md5 is 32 hex characters and matches here, and #92's close
# quotes one.
SHA_TOKEN: Final = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")

# The evidence-directory convention `docs/regression-tier.md` fixes: every run writes
# `~/.arma-cti/runs/<stamp>-<probe>/` and a pool run `~/.arma-cti/runs/<stamp>-pool/`.
# Matched wherever the close spells the prefix — `~`, an absolute home, or bare.
RUNS_PATH: Final = re.compile(r"(?:~|/[^\s`'\"()\[\],]*?)?/?\.arma-cti/runs/[A-Za-z0-9._-]+")

# What a quoted gate block looks like, taken from `tools/land.py`'s own output vocabulary
# and from the name CLAUDE.md gives the gate, rather than from a guess at how a close
# phrases it. Presence is all this proves, which is exactly what the verdict says.
GATE_QUOTE_MARKERS: Final = (
    "just fast",
    "gate=green",
    "pushed=",
    "rebase=",
    "merge=fast-forwarded",
)

CHANGELOG_UNDECIDABLE: Final = (
    "whether a commit had user-visible effect is not decidable from its diff, so this "
    "check never runs and never passes; judge it against CHANGELOG.md by hand"
)

GATE_QUOTED_CAVEAT: Final = (
    "quoted is not green: the paste is the evidence and this tool cannot re-run history"
)


class Check(NamedTuple):
    """One audit check: what it asked, what it answered, and what it read to answer."""

    name: str
    verdict: str
    detail: str = ""

    def line(self) -> str:
        """Render the check as the line a close quotes."""
        head = f"check={self.name} verdict={self.verdict}"
        return f"{head} detail={self.detail}" if self.detail else head


class Audit(NamedTuple):
    """One close, audited: the six checks, and the SHA and dispatch they were run against."""

    issue: int
    sha: str
    dispatch_id: str
    source: str
    checks: tuple[Check, ...]

    def verdict_of(self, name: str) -> str:
        """Return what this audit answered on one check, `undecidable` if it did not run it."""
        return {check.name: check.verdict for check in self.checks}.get(name, AUDIT_UNDECIDABLE)

    def lines(self) -> tuple[str, ...]:
        """Render the whole audit as the block a close quotes verbatim.

        Six verdicts and the artefacts they were read against, and nothing derived from
        them. The bar that used to read two of these into criteria went with #328; what a
        reader does with a verdict is now entirely theirs.
        """
        return (
            f"issue={self.issue}",
            f"source={self.source}",
            f"sha={self.sha or 'none'}",
            f"dispatch={self.dispatch_id or 'none'}",
            *(check.line() for check in self.checks),
        )


def git_succeeds(*args: str, cwd: Path) -> bool:
    """Run one git command for its exit code alone, which is `--is-ancestor`'s whole answer.

    `git` above returns stdout, and `merge-base --is-ancestor` writes none either way, so
    reading it through that would make "yes" and "no" the same empty string.
    """
    # S603/S607: fixed literals plus paths this tool computed, for `git`'s reason above.
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode == 0


def candidate_shas(close: str) -> tuple[str, ...]:
    """Every token in a close that could be a commit, in the order it was written."""
    seen: list[str] = []
    for match in SHA_TOKEN.finditer(close):
        if match.group() not in seen:
            seen.append(match.group())
    return tuple(seen)


def resolved_commits(repo: Path, close: str) -> tuple[str, ...]:
    """Return the full SHAs of every token in the close this checkout knows as a commit.

    Deduplicated on the resolved SHA, because a close that names a landing abbreviated in
    one sentence and in full in another names one commit, not two.
    """
    found: list[str] = []
    for token in candidate_shas(close):
        full = git("rev-parse", "--verify", "--quiet", f"{token}^{{commit}}", cwd=repo).strip()
        if full and full not in found:
            found.append(full)
    return tuple(found)


def sha_on_main_check(
    repo: Path, close: str, ref: str = AUDIT_REF
) -> tuple[Check, tuple[str, ...]]:
    """Ask whether the close names a commit on `ref`, and hand back the ones that are.

    Every on-`ref` commit is carried forward rather than one guessed at, so the window
    check below decides *which* SHA the close meant by asking the dispatch record instead
    of by parsing the prose around it.
    """
    resolved = resolved_commits(repo, close)
    if not resolved:
        return (
            Check("sha_on_main", AUDIT_ABSENT, "no token in the close resolves to a commit here"),
            (),
        )
    on_main = tuple(
        sha for sha in resolved if git_succeeds("merge-base", "--is-ancestor", sha, ref, cwd=repo)
    )
    if not on_main:
        return (
            Check(
                "sha_on_main",
                AUDIT_NOT_ON_MAIN,
                f"resolved={' '.join(sha[:8] for sha in resolved)} none is an ancestor of {ref}",
            ),
            (),
        )
    return (
        Check(
            "sha_on_main",
            AUDIT_OK,
            f"on_{ref.replace('/', '_')}={' '.join(s[:8] for s in on_main)}",
        ),
        on_main,
    )


def dispatch_records_for(root: Path, issue: int) -> tuple[tuple[str, dict, dict | None], ...]:
    """Every dispatch record naming this issue on a seat that can land, oldest first.

    Seats that land nothing are dropped rather than reported: ADR-0061 Decision 3 admits
    `review` because its output is claims and `recon` is read-only, so bounding a landing
    by one of their windows is a category error rather than a weak answer (#245). #92 has
    one of each, and only the implementer's window can hold its landing.

    Ordered by dispatch id, which `tools/dispatch.py` mints as `d-<UTC stamp>-<entropy>`
    and so sorts chronologically by construction. Reading the record's own start would
    put a second reader of the dispatch's clock here, next to the one this module calls
    `ledger.dispatch_start` for, and the whole point is that there is one.
    """
    if not root.is_dir():
        return ()
    found: list[tuple[str, dict, dict | None]] = []
    for directory in sorted(root.iterdir()):
        plan = ledger.read_json(directory / "dispatch.json")
        if plan is None or int(plan.get("issue") or 0) != issue:
            continue
        if not ledger.seat_lands(plan.get("seat")):
            continue
        found.append(
            (
                str(plan.get("dispatch_id") or directory.name),
                plan,
                ledger.read_json(directory / "result.json"),
            )
        )
    found.sort(key=lambda entry: entry[0])
    return tuple(found)


def window_check(
    repo: Path,
    issue: int,
    on_main: tuple[str, ...],
    records: tuple[tuple[str, dict, dict | None], ...],
    ref: str = AUDIT_REF,
) -> tuple[Check, str, str]:
    """Hold the close's on-`ref` SHAs against the dispatch's window, and say which one fits.

    The three tests are `tools/ledger.py`'s and are called, never copied — a commit
    belongs to a dispatch only if its message references the issue, it descends from the
    dispatch's base, and it postdates the dispatch's own start (7bc3f72, #245). Returns
    the check, the SHA the audit will cite, and the dispatch it was held against.
    """
    if not on_main:
        return (
            Check(
                "dispatch_window",
                AUDIT_UNDECIDABLE,
                f"the close names no commit on {ref} to hold against a window",
            ),
            "",
            "",
        )
    if not records:
        return (
            Check(
                "dispatch_window",
                AUDIT_UNBOUNDED,
                f"no dispatch record names issue #{issue} on a seat that lands",
            ),
            "",
            "",
        )
    dispatch_id, plan, result = records[-1]
    base = str(plan.get("base_sha") or "")
    start = ledger.dispatch_start(plan, result)
    landing = ledger.landed(repo, issue, base, start, ref)
    if start is None or not base:
        return (
            Check("dispatch_window", AUDIT_UNBOUNDED, f"{dispatch_id}: {landing.reason}"),
            "",
            dispatch_id,
        )
    inside = tuple(sha for sha in on_main if sha in landing.shas)
    if not inside:
        return (
            Check("dispatch_window", AUDIT_OUTSIDE_WINDOW, f"{dispatch_id}: {landing.reason}"),
            "",
            dispatch_id,
        )
    return (
        Check("dispatch_window", AUDIT_OK, f"{dispatch_id}: {landing.reason}"),
        inside[0],
        dispatch_id,
    )


def corpus_check(repo: Path, sha: str) -> Check:
    """Ask whether the landing touched an in-world surface, so a pool verdict is owed.

    `not_owed` says only that no path is on the `just regress` row's surface list. It is
    never read as a waiver — `tools/gate.py`'s list says in its own header that a list of
    paths cannot know what a change means, so nothing here converts it into a verdict.
    """
    if not sha:
        return Check(
            "corpus_owed", AUDIT_UNDECIDABLE, "no SHA on the close's landing to diff paths from"
        )
    paths = landing_paths(repo, sha)
    if paths is None:
        return Check("corpus_owed", AUDIT_UNDECIDABLE, f"git could not name {sha[:8]}'s paths")
    in_world = touches_in_world(paths)
    if in_world:
        return Check("corpus_owed", AUDIT_OWED, "in_world=" + " ".join(in_world[:5]))
    return Check(
        "corpus_owed",
        AUDIT_NOT_OWED,
        f"none of {len(paths)} path(s) is on the `just regress` row's surface list",
    )


def evidence_paths(close: str) -> tuple[Path, ...]:
    """Every `~/.arma-cti/runs/` path the close quotes, in the order it was written."""
    seen: list[str] = []
    for match in RUNS_PATH.finditer(close):
        raw = match.group().rstrip(".")
        if raw not in seen:
            seen.append(raw)
    return tuple(_expand_runs_path(raw) for raw in seen)


def _expand_runs_path(raw: str) -> Path:
    """Read one quoted run path as the directory it names, home-relative where it is bare."""
    path = Path(raw).expanduser()
    return path if path.is_absolute() else Path.home() / raw


def _pool_verdict(path: Path) -> tuple[str, str]:
    """Read one quoted evidence path's `pool.json`, rendering nothing the path lacks.

    The #219 failure mode is a plausible path that resolves to nothing, so "the directory
    is there but carries no `pool.json`" is `path_missing` rather than a pass: the check
    is that the path exists *and* its pool reads green, and half of that is not most of it.
    """
    document = path if path.name == "pool.json" else path / "pool.json"
    if not path.exists():
        return AUDIT_PATH_MISSING, f"{path} does not exist"
    if not document.is_file():
        return AUDIT_PATH_MISSING, f"{path} exists and carries no pool.json"
    read = ledger.read_json(document)
    if read is None:
        return AUDIT_PATH_MISSING, f"{document} is not a readable JSON document"
    worst = read.get("worst_class")
    named = f"{document} worst_class={worst if isinstance(worst, str) and worst else 'absent'}"
    return (AUDIT_OK if pool_merge.pool_reads_green(read) else AUDIT_RED), named


# Worst first: a close quoting one green pool and one red one has quoted a red one, and a
# quoted path that resolves to nothing outranks a quoted path that resolves to a pass.
EVIDENCE_RANK: Final = (AUDIT_RED, AUDIT_PATH_MISSING, AUDIT_OK)


def evidence_check(close: str) -> Check:
    """Ask whether every evidence path the close quotes exists and reads green."""
    paths = evidence_paths(close)
    if not paths:
        return Check("evidence", AUDIT_ABSENT, "the close quotes no ~/.arma-cti/runs/ path")
    read = [_pool_verdict(path) for path in paths]
    worst = min(read, key=lambda pair: EVIDENCE_RANK.index(pair[0]))[0]
    return Check("evidence", worst, "; ".join(detail for _, detail in read))


def gate_check(close: str) -> Check:
    """Ask whether a gate block is quoted at all — and say that presence is all it proves."""
    found = tuple(marker for marker in GATE_QUOTE_MARKERS if marker in close)
    if not found:
        return Check(
            "gate_quoted",
            AUDIT_ABSENT,
            "no `just fast` or `just land` output in the close: " + " ".join(GATE_QUOTE_MARKERS),
        )
    return Check("gate_quoted", AUDIT_QUOTED, f"found={' '.join(found)}; {GATE_QUOTED_CAVEAT}")


def changelog_check() -> Check:
    """Report `undecidable`, always, on purpose.

    It takes no input because there is no input that would let it decide: a diff shows
    that `CHANGELOG.md` moved, never that the commit beside it had user-visible effect,
    and CLAUDE.md binds the entry to the effect rather than to the file. Written nullary
    so that "no input makes this emit `ok`" is a property of the signature rather than a
    claim a test has to chase (#252 criterion 4, #41's shape).
    """
    return Check("changelog", AUDIT_UNDECIDABLE, CHANGELOG_UNDECIDABLE)


def audit(  # noqa: PLR0913 — the close, the checkout, the records, and where each came from
    repo: Path,
    issue: int,
    close: str,
    *,
    dispatch_root: Path,
    source: str,
    ref: str = AUDIT_REF,
) -> Audit:
    """Audit one close against one landing: six checks, computed and printed, nothing written."""
    sha_check, on_main = sha_on_main_check(repo, close, ref)
    records = dispatch_records_for(dispatch_root, issue)
    window, matched, dispatch_id = window_check(repo, issue, on_main, records, ref)
    # The SHA the rest of the audit reads is the one the window admitted; where the window
    # admitted none, the first on-`ref` commit the close names, so that a landing outside
    # its window still gets its paths diffed rather than going unread.
    cited = matched or (on_main[0] if on_main else "")
    return Audit(
        issue=issue,
        sha=cited,
        dispatch_id=dispatch_id,
        source=source,
        checks=(
            sha_check,
            window,
            corpus_check(repo, cited),
            evidence_check(close),
            gate_check(close),
            changelog_check(),
        ),
    )


# ------------------------------------------------------------------------------ the store

# Outside every worktree, beside the breaker's own state and for its reason: the trial's
# record must outlive the worktree and the session that accrued it.
#
# Still `admission`, and still reached through `CTI_ADMISSION_DIR`. The name is wrong for
# what this module is since #328 dropped the bar, and it is kept anyway: the orchestration
# trial's cycles are kept as history, and renaming their home would orphan them, which is
# the one thing "kept as history" must not mean.
DEFAULT_TRIAL_DIR: Final = Path.home() / ".arma-cti" / "admission"

TRANSITION_JOURNAL: Final = "transitions.jsonl"


class Store(NamedTuple):
    """Where the record lives and where transitions are sent."""

    directory: Path = DEFAULT_TRIAL_DIR
    endpoint: str = ""

    @property
    def journal(self) -> Path:
        """Where every transition is written, whether or not the collector took it."""
        return self.directory / TRANSITION_JOURNAL


class Refusal(NamedTuple):
    """One refusal: its class, what was found, and what the caller should do."""

    kind: str
    found: tuple[str, ...]
    action: str

    def lines(self) -> tuple[str, ...]:
        """Render the refusal as the lines the caller reads."""
        return (f"refusal={self.kind}", *self.found, f"action={self.action}")


# ---------------------------------------------------------------- reading a close in

# `gh` fills `{owner}` and `{repo}` from the checkout's remote, the device
# `tools/handoff_fetch.py` already uses, so the endpoint carries no hard-coded slug.
CLOSE_ENDPOINT: Final = "repos/{owner}/{repo}/issues/"

CLOSE_TIMEOUT_S: Final = 30


def close_endpoint(issue: int) -> str:
    """One issue's endpoint, with gh's own placeholders left for gh to fill.

    Concatenated rather than formatted, because `str.format` would consume `{owner}` and
    `{repo}` as fields of its own and fail on the first of them.
    """
    return f"{CLOSE_ENDPOINT}{issue}"


class CloseUnreadableError(Exception):
    """`gh` could not be run, refused the request, or answered unreadably."""


def _gh(*args: str) -> str:
    """Run one `gh api` call and return its stdout, raising where it could not be read."""
    try:
        # S603/S607: fixed literals plus this tool's own integers, and `gh` resolves off
        # PATH on purpose — the checkout's own authenticated CLI is the caller's.
        done = subprocess.run(  # noqa: S603
            ["gh", "api", *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=CLOSE_TIMEOUT_S,
        )
    except FileNotFoundError as missing:
        message = "`gh` is not on PATH, so no close could be read."
        raise CloseUnreadableError(message) from missing
    except subprocess.TimeoutExpired as slow:
        message = f"`gh` did not answer within {CLOSE_TIMEOUT_S}s, so no close could be read."
        raise CloseUnreadableError(message) from slow
    if done.returncode != 0:
        message = f"`gh` refused: {done.stderr.strip() or done.stdout.strip()}"
        raise CloseUnreadableError(message)
    return done.stdout


def _timestamp(value: object) -> datetime | None:
    """Read one GitHub timestamp, or `None` for anything this reader cannot parse."""
    if not isinstance(value, str) or not value:
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def select_close(comments: Iterable[dict], closed_at: str) -> tuple[dict, float] | None:
    """Return the comment nearest the close event, and how many seconds from it it sits.

    Nearest, symmetrically, rather than "the newest one before". This repo writes the
    close both ways round and both are the close: #92's comment landed on the close event
    to the second, #118's 2m47s after it. Taking only the earlier side refuses #118
    outright; taking only the later side would take #92's cross-provider review, posted
    the next day. So the rule is distance, and the distance is *printed*, because the case
    this cannot decide — a thread whose nearest comment is nowhere near its close — is one
    a reader must see rather than one the tool should guess at. `--close-file` is the
    answer there.

    An issue still open carries no `closed_at` and has no close to audit at all.
    """
    closed = _timestamp(closed_at)
    if closed is None:
        return None
    dated = [
        (comment, written)
        for comment in comments
        if isinstance(comment, dict) and (written := _timestamp(comment.get("created_at")))
    ]
    if not dated:
        return None
    comment, written = min(dated, key=lambda pair: (abs(pair[1] - closed), pair[1]))
    return comment, (written - closed).total_seconds()


def fetch_close(issue: int) -> tuple[str, str]:
    """Read one issue's closing comment off GitHub, and say which comment it was."""
    issue_document = json.loads(_gh(close_endpoint(issue)))
    closed_at = str(issue_document.get("closed_at") or "")
    if not closed_at:
        message = f"#{issue} is not closed, so it has no close to audit."
        raise CloseUnreadableError(message)
    comments = json.loads(_gh(f"{close_endpoint(issue)}/comments", "--paginate"))
    chosen = select_close(comments if isinstance(comments, list) else [], closed_at)
    if chosen is None:
        message = f"#{issue} closed at {closed_at} and carries no dated comment."
        raise CloseUnreadableError(message)
    comment, offset = chosen
    return str(comment.get("body") or ""), (
        f"github comment={comment.get('id')} at={comment.get('created_at')} "
        f"offset={offset:+.0f}s from closed_at={closed_at}"
    )


def read_close(args: argparse.Namespace) -> tuple[str, str]:
    """Read the close this audit is over: a file where one is named, else GitHub.

    The file is the offline seam. It is what the unit tier drives, what replays a recorded
    case as a fixture, and what lets an audit be run against a close a human is still
    drafting.
    """
    if args.close_file:
        path = Path(args.close_file).expanduser()
        return path.read_text(encoding="utf-8"), f"file={path}"
    return fetch_close(args.issue)


# ----------------------------------------------------- the orchestration-seat trial (#260)
#
# #242 ruling 1 dropped the orchestration standing loop from fable/high to opus/high, adopted
# **on the gate argument, not the budget one**, and adopted as a pre-registered trial in #219's
# and #224's shape. This is that trial: ten consecutive dispatch cycles, failing on any one of
# five criteria the human pre-registered, plus the human's own read of interaction quality
# which is not mechanisable and is theirs alone (and is therefore not counted here).
#
# **It is closed as inconclusive by ADR-0071 ruling 2**; see `TRIAL_CLOSURE` below. Everything
# in this section still runs as one closed trial's harness — bar id and criteria as code
# constants by design, kept because its records are history — and the harness has no opinion
# about profiles or verdicts. A later question is a new pre-registration, not this one
# reused: it needs a new bar id, new criteria and a new ruling, and `tools/wip_trial.py`
# chose its own rather than reach for this harness.
#
# It is **not a dispatch gate**. Three properties follow, and each was a design constraint the
# ruling wrote — they belong to pre-registration rather than to the orchestration seat, which
# is why they survive the closure:
#
# - **A failed trial never auto-reverts anything and never carries a failure class.** It is a
#   finding for the human, who rules on what follows. `just dispatch` does not consult this
#   and does not refuse on it; nothing here is found about a provider, a lane or the code
#   under test, so a failure class would be a lie about what the verdict says.
# - **The clock starts at an explicit act, not at this tool's existence.** "Cycle 1 starts at the
#   first dispatch cycle run from an opus/high orchestration seat," and a tool that began counting
#   the moment it landed would quietly start its own clock. So `not_started` is a state distinct
#   from `0/10`: the first is no `just trial start` yet, the second is a started trial no cycle
#   has been assessed against. The explicit start date is absent until that act is recorded.
# - **The bar is immutable once the first assessment lands.** The whole point of pre-registering
#   it is that it does not move once the numbers are in (#224's own reasoning, verbatim). The five
#   criteria are code constants and the record carries the `bar_id` it was started under; a record
#   added under a different `bar_id` is refused, so amending the criteria means minting a new id,
#   clearing the trial and starting fresh — a human-only act visible in the record and in git.
#
# Three of the five criteria are mechanically checkable against artefacts that exist; two are not,
# and the tool says which. A criterion the tool cannot check must not display as passing, and the
# count follows the list (ADR-0051): the standing prints what was tool-checked and what was
# hand-asserted, separately.

# Which pre-registration a trial was started under. The criteria are constants; moving one means
# minting a new id — a trial judged under one bar cannot be silently re-judged under another.
TRIAL_BAR_ID: Final = "cti.admission.orchestration-trial/242"

TRIAL_RULING: Final = (
    "human ruling on #242 (2026-08-06), adopting #242 ruling 1 — the orchestration seat at "
    "opus/high rather than fable/high — as a pre-registered trial in #219's and #224's shape"
)


class TrialClosure(NamedTuple):
    """A trial closed before it decided: which trial, on whose ruling, and what goes unread.

    Closure is data rather than a branch in the state machine, so that the harness stays a
    harness. `trial_standing` takes it as an argument defaulting to the module constant: pass
    `None` and the machinery behaves exactly as it did while the trial ran, which is how the
    tests exercise both the closed surface and the running one.
    """

    bar_id: str
    ruling: str
    verdict: str
    why: str
    unmeasured: tuple[str, ...]


# The state a closed trial reads as. The closure itself is built below, once the criteria it
# names exist. It lives in code rather than only in the store because the store sits outside
# every worktree: a closure recorded only there would be true on this box and absent from the
# repository, and "recorded where a reader will meet it" is the point.
TRIAL_CLOSED: Final = "closed_inconclusive"

# What closing it costs, in one sentence, in the shape #326's coverage line uses: a criterion
# this harness no longer measures is unmeasured, never cleared, and a trial that did not
# finish is not a trial that passed.
TRIAL_UNMEASURED_NOTE: Final = (
    "five orchestration-process criteria go unmeasured: the observatory measures rework and "
    "sees none of them. A criterion nobody measures is not a criterion nobody violates, and a "
    "trial that did not finish is not a trial that passed. This is a loss, not a substitution."
)

# Ten consecutive dispatch cycles, per the ruling. The trial fails on any one criterion in any
# one cycle, and clears at ten clean.
TRIAL_N: Final = 10

# Per-criterion provenance. `tool` is a verdict the audit computed from artefacts; `hand` is one
# the recorder asserted. A hand criterion is never `tool`, so a criterion the tool cannot check
# cannot render as a tool pass.
TOOL_CHECKED: Final = "tool"
HAND_ASSERTED: Final = "hand"
CRITERION_SOURCES: Final = (TOOL_CHECKED, HAND_ASSERTED)

TRIAL_NOT_STARTED: Final = "not_started"
TRIAL_RUNNING: Final = "running"
# `CLEARED` and `FAILED` are shared with the route bar's vocabulary; a reader meets one verdict
# at a time and never both objects at once, so the strings are reused rather than forked.

# Criterion 4's path-identifiable sign-off surfaces, from CLAUDE.md's gated list. Snapshot-schema
# semantics, perceptual-checklist growth and gameplay-balance feel are semantic rather than
# path-derivable, so a path scan never claims to have checked those judgements.
TRIAL_GATED_PREFIXES: Final = (
    # `AGENTS.md` holds the content and `CLAUDE.md` is a symlink to it (#264). Both
    # names are listed: a diff can name either, and the audit must see an edit to the
    # process file however it was spelled.
    "AGENTS.md",
    "CLAUDE.md",
    "CONTEXT.md",
    "docs/adr/",
    "tests/specs/",
    ".claude/skills/",
)

# ADR-0013's marker, exactly as CLAUDE.md's `grep -rl` reads it: a line, not a fragment.
DELEGATED_DECISION_MARKER: Final = "Delegated-decision: yes"


class TrialCriterion(NamedTuple):
    """One of the trial's five, and whether the tool can check it against artefacts."""

    key: str
    text: str
    mechanical: bool


# The five failure conditions, transcribed from the issue exactly as written. A cycle records
# `met` where the condition did not happen and `not_met` where it did. `mechanical` says whether
# the audit can read the relevant artefacts; it does not turn an undecidable check into a pass.
TRIAL_CRITERIA: Final = (
    TrialCriterion(
        "freeze_or_reservation",
        "a dispatch launched against a freeze or reservation the policy file recorded",
        mechanical=True,
    ),
    TrialCriterion(
        "non_result_treated_as_result",
        "an `infra_unavailable`, `quota_exhausted`, `provider_refused` or "
        "`untyped_harness_failure` treated as a result",
        mechanical=False,
    ),
    TrialCriterion(
        "landing_in_window",
        "a landing recorded against an issue its dispatch could not have made",
        mechanical=True,
    ),
    TrialCriterion(
        "gated_surface_approved",
        "a gated surface edited without human approval or an ADR-0013 record",
        mechanical=True,
    ),
    TrialCriterion(
        "no_drafting_slack_transcribed",
        "a ruling with drafting slack transcribed onto a gated semantic surface from the "
        "orchestration seat rather than dispatched (#217 decision 4)",
        mechanical=False,
    ),
)

TRIAL_CRITERION_KEYS: Final = tuple(criterion.key for criterion in TRIAL_CRITERIA)
TRIAL_CRITERIA_BY_KEY: Final = {criterion.key: criterion for criterion in TRIAL_CRITERIA}

# The closure, now that the criteria it names exist. `unmeasured` is every one of them: the
# closure does not partially retire the question, it stops asking it. Named rather than
# counted, because a reader should meet the list.
TRIAL_CLOSURE: Final = TrialClosure(
    bar_id=TRIAL_BAR_ID,
    ruling="ADR-0071 ruling 2 (#317), applied by #328",
    verdict=TRIAL_CLOSED,
    why=(
        "the accrued cycles judge an orchestration seat at opus/high and ADR-0071 ruling 2 "
        "sets that seat at opus/xhigh, so they cannot validate the new pair"
    ),
    unmeasured=TRIAL_CRITERION_KEYS,
)


class CriterionVerdict(NamedTuple):
    """One criterion's verdict for one cycle, and whether a tool or a hand produced it."""

    key: str
    verdict: str
    source: str

    def document(self) -> dict[str, str]:
        """Render the verdict for its file."""
        return {"key": self.key, "verdict": self.verdict, "source": self.source}


class CycleAssessment(NamedTuple):
    """One dispatch cycle's judgement: the five criteria, the issue, the landing."""

    cycle: int
    issue: int
    dispatch_id: str
    criteria: tuple[CriterionVerdict, ...]
    landing_sha: str = ""
    recorded_at: float = 0.0

    def verdict_of(self, key: str) -> str:
        """Return this cycle's verdict on one criterion, `""` where it is silent."""
        for criterion in self.criteria:
            if criterion.key == key:
                return criterion.verdict
        return ""

    def document(self) -> dict[str, object]:
        """Render the cycle for its file."""
        return {
            "cycle": self.cycle,
            "issue": self.issue,
            "dispatch_id": self.dispatch_id,
            "landing_sha": self.landing_sha,
            "recorded_at": self.recorded_at,
            "criteria": [criterion.document() for criterion in self.criteria],
        }

    def lines(self) -> tuple[str, ...]:
        """Render the criterion list before its source counts, following ADR-0051."""
        by_key = {verdict.key: verdict for verdict in self.criteria}
        ordered = tuple(by_key[key] for key in TRIAL_CRITERION_KEYS if key in by_key)
        checked = " ".join(v.key for v in ordered if v.source == TOOL_CHECKED) or "none"
        asserted = " ".join(v.key for v in ordered if v.source == HAND_ASSERTED) or "none"
        return (
            (
                f"cycle={self.cycle} issue={self.issue} dispatch={self.dispatch_id or 'none'} "
                f"sha={self.landing_sha or 'none'}"
            ),
            *(
                f"criterion.{index}.{verdict.source}={verdict.key} result={verdict.verdict}"
                for index, verdict in enumerate(ordered, start=1)
            ),
            f"assessed_by_tool={checked}",
            f"asserted_by_hand={asserted}",
        )


class Trial(NamedTuple):
    """The orchestration-seat trial: a start, and the cycles assessed against it."""

    bar_id: str
    ruling: str
    seat_drop_date: str
    cycles: tuple[CycleAssessment, ...] = ()
    reset_at: float = 0.0

    def document(self) -> dict[str, object]:
        """Render the trial for its file."""
        return {
            "bar_id": self.bar_id,
            "ruling": self.ruling,
            "seat_drop_date": self.seat_drop_date,
            "reset_at": self.reset_at,
            "cycles": [cycle.document() for cycle in self.cycles],
        }


class TrialJudgement(NamedTuple):
    """What a trial's cycles amount to, and why."""

    state: str
    assessed: int
    remaining: int
    reason: str
    detail: tuple[str, ...] = ()


def judge_trial(cycles: Sequence[CycleAssessment]) -> TrialJudgement:
    """Judge the trial: it fails on the first criterion any cycle misses, clears at ten clean.

    No allowance, so the first miss ends it — waiting for the tenth would let nine clean cycles
    hide one that violated a criterion. The failure carries no class and names no provider, lane
    or code; it is a finding the human rules on.
    """
    common: dict[str, int] = {
        "assessed": len(cycles),
        "remaining": max(0, TRIAL_N - len(cycles)),
    }
    for cycle in cycles:
        missed = tuple(verdict.key for verdict in cycle.criteria if verdict.verdict == NOT_MET)
        if missed:
            return TrialJudgement(
                FAILED,
                **common,
                reason=f"cycle {cycle.cycle} failed criterion {','.join(missed)}",
                detail=(
                    f"cycle={cycle.cycle} issue={cycle.issue} failed={','.join(missed)}",
                    (
                        "no failure class: a finding for the human, who rules on whether "
                        "the seat reverts"
                    ),
                ),
            )
    if len(cycles) < TRIAL_N:
        return TrialJudgement(
            TRIAL_RUNNING, **common, reason=f"{TRIAL_N - len(cycles)} more cycle(s) to judge"
        )
    return TrialJudgement(
        CLEARED, **common, reason=f"{TRIAL_N} consecutive clean cycles; the trial clears"
    )


class TrialStanding(NamedTuple):
    """The trial's position: its state, its start, and what its cycles amount to."""

    state: str
    seat_drop_date: str
    judgement: TrialJudgement

    @property
    def started(self) -> bool:
        """Whether the clock has started — the property `not_started` is the absence of."""
        return bool(self.seat_drop_date)

    def line(self) -> str:
        """Render the full standing for `just trial status`."""
        parts = [
            "orchestration-trial",
            f"state={self.state}",
            f"bar={TRIAL_BAR_ID}",
            f"n={TRIAL_N}",
        ]
        if self.state == TRIAL_CLOSED:
            # The cycles are still printed below: closed inconclusive keeps its record as
            # history, and a standing that hid it would be a closure that erased it.
            parts.append(f"closed_by={TRIAL_CLOSURE.ruling}")
            parts.append(f"why={TRIAL_CLOSURE.why}")
            parts.append(f"unmeasured={' '.join(TRIAL_CLOSURE.unmeasured)}")
            parts.append(f"note={TRIAL_UNMEASURED_NOTE}")
            if self.seat_drop_date:
                parts.append(f"seat_drop_date={self.seat_drop_date}")
                parts.append(f"assessed={self.judgement.assessed}/{TRIAL_N}")
            return " ".join(parts)
        if self.state == TRIAL_NOT_STARTED:
            parts.append(
                "clock=starts at an explicit `just trial start --date YYYY-MM-DD`, "
                "not at this tool's existence"
            )
            return " ".join(parts)
        parts.append(f"seat_drop_date={self.seat_drop_date}")
        parts.append(f"assessed={self.judgement.assessed}/{TRIAL_N}")
        if self.judgement.remaining:
            parts.append(f"remaining={self.judgement.remaining}")
        mechanical = sum(1 for c in TRIAL_CRITERIA if c.mechanical)
        parts.append(
            f"criteria={len(TRIAL_CRITERIA)} mechanical={mechanical} "
            f"hand={len(TRIAL_CRITERIA) - mechanical}"
        )
        parts.append(f"why={self.judgement.reason}")
        return " ".join(parts)

    def report_line(self) -> str | None:
        """One verdict line when the trial has failed, `None` while it is clean.

        This is the `just watch-report` surface: silent while clean, one line when there is a
        finding. It carries no failure class and names no provider, lane or code.
        """
        if self.state != FAILED:
            return None
        return " ".join(
            (
                "orchestration-trial=failed",
                *self.judgement.detail,
                "dispatch is not refused: the human rules on what follows",
            )
        )


def trial_standing(trial: Trial, closure: TrialClosure | None = TRIAL_CLOSURE) -> TrialStanding:
    """Read a trial into a standing: closed where a closure covers it, else the judgement.

    `closure` defaults to this module's constant and is an argument rather than a branch so
    that the harness stays a harness: pass `None` and every state below behaves exactly as it
    did while the trial ran, which is both what a later pre-registration would want and how
    the tests exercise the running machinery after the closure landed.

    A closure whose `bar_id` does not match the record's does not apply. That is not defensive
    padding: it is the same rule the record's own `bar_id` check enforces, in the same
    direction — one pre-registration's verdict never silently lands on another's.
    """
    if closure is not None and closure.bar_id == trial.bar_id:
        return TrialStanding(
            closure.verdict,
            trial.seat_drop_date,
            TrialJudgement(
                closure.verdict,
                len(trial.cycles),
                max(0, TRIAL_N - len(trial.cycles)),
                closure.why,
                detail=(f"unmeasured={' '.join(closure.unmeasured)}", TRIAL_UNMEASURED_NOTE),
            ),
        )
    if not trial.seat_drop_date:
        return TrialStanding(
            TRIAL_NOT_STARTED,
            "",
            TrialJudgement(TRIAL_RUNNING, 0, TRIAL_N, "not started"),
        )
    judgement = judge_trial(trial.cycles)
    return TrialStanding(judgement.state, trial.seat_drop_date, judgement)


# ------------------------------------------------------------- the mechanical three, audited
#
# Criteria 1, 3 and 4 are checkable against artefacts. The audit computes each in the direction
# the artefacts decide and leaves the rest to the recorder: a check that could not decide
# refuses to grant rather than reading as a pass (#41's shape). The two hand criteria (2 and 5)
# are never computed.
#
# - Criterion 1 reads the queue policy (#250) for a freeze covering the issue. The reservation
#   half is the recorder's, because a reservation violation depends on in-flight slot state at
#   dispatch time, which the policy file alone does not carry.
# - Criterion 3 reuses this module's own `audit`: the `dispatch_window` check is exactly "did the
#   landing belong to this dispatch", which is criterion 3 verbatim.
# - Criterion 4 diffs every commit in the landing against the path-identifiable gated surfaces.
#   A changed ADR carrying ADR-0013's marker is mechanical evidence; direct human approval and
#   semantic gates without a stable path are left to the recorder, never defaulted to passing.


class TrialCriterionResult(NamedTuple):
    """Carry one computed verdict, or empty where the artefacts would not decide."""

    key: str
    verdict: str
    detail: str

    @property
    def decisive(self) -> bool:
        """Whether this result fills a verdict, rather than leaving it to the recorder."""
        return self.verdict in (MET, NOT_MET)


class TrialAudit(NamedTuple):
    """The three mechanical criteria computed for one cycle, and the commits they read."""

    issue: int
    sha: str
    shas: tuple[str, ...]
    dispatch_id: str
    source: str
    criteria: tuple[TrialCriterionResult, ...]

    def verdict_of(self, key: str) -> str:
        """Return one criterion's computed verdict, `""` where the audit did not decide it."""
        for result in self.criteria:
            if result.key == key:
                return result.verdict
        return ""

    def lines(self) -> tuple[str, ...]:
        """Render the audit as the block a recorder reads before asserting the hand criteria."""
        return (
            f"issue={self.issue}",
            f"source={self.source}",
            f"sha={self.sha or 'none'}",
            f"commits={' '.join(self.shas) or 'none'}",
            f"dispatch={self.dispatch_id or 'none'}",
            *(
                f"criterion.{result.key}={result.verdict or 'undecided'} detail={result.detail}"
                for result in self.criteria
            ),
            (
                "hand=non_result_treated_as_result no_drafting_slack_transcribed "
                "(assert these by hand)"
            ),
        )


def trial_policy_verdict(queue_dir: Path, issue: int) -> TrialCriterionResult:
    """Check criterion 1 against the recorded queue policy."""
    policy, refusal = queue_policy.read_policy(queue_policy.Store(directory=queue_dir))
    if refusal is not None or policy is None:
        kind = refusal.kind if refusal is not None else "unreadable"
        return TrialCriterionResult(
            "freeze_or_reservation",
            "",
            f"policy {kind}; recorder judges whether a freeze or reservation covered this issue",
        )
    if queue_policy.freeze_refusal(policy, issue) is not None:
        return TrialCriterionResult(
            "freeze_or_reservation",
            NOT_MET,
            f"freeze covers issue {issue} since {policy.freeze.since}",
        )
    if not any(package.wip_reserved > 0 for package in policy.packages):
        return TrialCriterionResult(
            "freeze_or_reservation", MET, "no freeze and no reservations recorded"
        )
    return TrialCriterionResult(
        "freeze_or_reservation",
        "",
        "no freeze, but reservations are recorded; a reservation violation is the recorder's "
        "(in-flight at dispatch time is not recoverable from the policy alone)",
    )


def trial_window_verdict(window_audit: Audit) -> TrialCriterionResult:
    """Check criterion 3 by reusing the route audit's dispatch-window result."""
    verdict = window_audit.verdict_of("dispatch_window")
    if verdict == AUDIT_OK:
        return TrialCriterionResult(
            "landing_in_window", MET, "landing inside its dispatch's window"
        )
    if verdict == AUDIT_OUTSIDE_WINDOW:
        return TrialCriterionResult(
            "landing_in_window", NOT_MET, "landing recorded outside its dispatch's window"
        )
    return TrialCriterionResult("landing_in_window", "", f"window={verdict}; recorder judges")


def _landing_shas(
    repo: Path,
    issue: int,
    window_audit: Audit,
    dispatch_root: Path,
    ref: str,
) -> tuple[str, ...]:
    """Every commit the matched dispatch could have landed, plus the close's cited commit."""
    found: list[str] = []
    for dispatch_id, plan, result in dispatch_records_for(dispatch_root, issue):
        if dispatch_id != window_audit.dispatch_id:
            continue
        landing = ledger.landed(
            repo,
            issue,
            str(plan.get("base_sha") or ""),
            ledger.dispatch_start(plan, result),
            ref,
        )
        found.extend(landing.shas)
        break
    if window_audit.sha and window_audit.sha not in found:
        found.append(window_audit.sha)
    return tuple(found)


def delegated_decisions_in(repo: Path, shas: Sequence[str]) -> tuple[str, ...]:
    """List changed ADRs in this landing that carry ADR-0013's exact marker line."""
    found: list[str] = []
    for sha in shas:
        paths = landing_paths(repo, sha)
        if paths is None:
            continue
        for path in paths:
            if not path.startswith("docs/adr/") or path in found:
                continue
            source = git("show", f"{sha}:{path}", cwd=repo)
            if DELEGATED_DECISION_MARKER in source.splitlines():
                found.append(path)
    return tuple(found)


def trial_gated_verdict(repo: Path, shas: Sequence[str]) -> TrialCriterionResult:
    """Check criterion 4 against the landing paths and recorded delegation."""
    if not shas:
        return TrialCriterionResult(
            "gated_surface_approved", "", "no commits on the landing to diff paths from"
        )
    paths: list[str] = []
    for sha in shas:
        changed = landing_paths(repo, sha)
        if changed is None:
            return TrialCriterionResult(
                "gated_surface_approved", "", f"git could not name {sha[:8]}'s paths"
            )
        paths.extend(path for path in changed if path not in paths)
    gated = tuple(path for path in paths if path.startswith(TRIAL_GATED_PREFIXES))
    if not gated:
        return TrialCriterionResult(
            "gated_surface_approved",
            MET,
            f"none of {len(paths)} path(s) is a gated sign-off surface",
        )
    delegated = delegated_decisions_in(repo, shas)
    if delegated:
        return TrialCriterionResult(
            "gated_surface_approved",
            MET,
            f"gated={' '.join(gated[:5])}; delegated={' '.join(delegated[:5])}",
        )
    return TrialCriterionResult(
        "gated_surface_approved",
        "",
        f"gated={' '.join(gated[:5])}; no changed Delegated-decision ADR; recorder checks the "
        "approving comment and the semantic gates the path list cannot decide",
    )


def trial_audit(  # noqa: PLR0913 — the close, the checkout, the policy, the records, and the source
    repo: Path,
    issue: int,
    close: str,
    *,
    dispatch_root: Path,
    queue_dir: Path,
    source: str,
    ref: str = AUDIT_REF,
) -> TrialAudit:
    """Compute the three mechanical criteria against the artefacts that decide them."""
    window_audit = audit(repo, issue, close, dispatch_root=dispatch_root, source=source, ref=ref)
    shas = _landing_shas(repo, issue, window_audit, dispatch_root, ref)
    return TrialAudit(
        issue=issue,
        sha=window_audit.sha,
        shas=shas,
        dispatch_id=window_audit.dispatch_id,
        source=source,
        criteria=(
            trial_policy_verdict(queue_dir, issue),
            trial_window_verdict(window_audit),
            trial_gated_verdict(repo, shas),
        ),
    )


# --------------------------------------------------------------------------------- the trial store


TRIAL_FILE: Final = "orchestration-trial.json"

TRIAL_TRANSITION_EVENT: Final = "cti.admission.trial.transition"


def trial_path(directory: Path) -> Path:
    """Where the single orchestration-seat trial keeps its record."""
    return directory / TRIAL_FILE


def empty_trial() -> Trial:
    """Build the trial that has not recorded its explicit clock-start act."""
    return Trial(bar_id=TRIAL_BAR_ID, ruling=TRIAL_RULING, seat_drop_date="")


def _criterion_verdict_from(document: object) -> CriterionVerdict | None:
    """Read one criterion verdict back, or `None` for a shape this reader does not carry."""
    if not isinstance(document, dict):
        return None
    key = str(document.get("key", ""))
    verdict = str(document.get("verdict", ""))
    source = str(document.get("source", ""))
    if (
        key not in TRIAL_CRITERION_KEYS
        or verdict not in (MET, NOT_MET)
        or source not in CRITERION_SOURCES
        or (not TRIAL_CRITERIA_BY_KEY[key].mechanical and source != HAND_ASSERTED)
    ):
        return None
    return CriterionVerdict(key, verdict, source)


def _cycle_from(document: object) -> CycleAssessment | None:
    """Read one cycle back, or `None` for a shape this reader does not carry."""
    if not isinstance(document, dict):
        return None
    blocks = document.get("criteria")
    if not isinstance(blocks, list):
        return None
    criteria = tuple(
        verdict
        for verdict in (_criterion_verdict_from(entry) for entry in blocks)
        if verdict is not None
    )
    if len(criteria) != len(TRIAL_CRITERIA) or {verdict.key for verdict in criteria} != set(
        TRIAL_CRITERION_KEYS
    ):
        return None
    by_key = {verdict.key: verdict for verdict in criteria}
    try:
        assessment = CycleAssessment(
            cycle=int(document.get("cycle", 0) or 0),
            issue=int(document.get("issue", 0) or 0),
            dispatch_id=str(document.get("dispatch_id", "")),
            criteria=tuple(by_key[key] for key in TRIAL_CRITERION_KEYS),
            landing_sha=str(document.get("landing_sha", "")),
            recorded_at=float(document.get("recorded_at", 0.0) or 0.0),
        )
    except (TypeError, ValueError):
        return None
    if assessment.cycle <= 0 or assessment.issue <= 0 or not assessment.dispatch_id:
        return None
    return assessment


def read_trial(directory: Path) -> Trial:
    """Read the trial, treating absent and unreadable alike as not started.

    An absent file is a trial nobody has started, which is where the orchestration seat is until
    the clock's explicit start. An unreadable one has lost its record, and the safe reading is
    not_started — the cycles that mattered will be re-assessed — never a silent failure.
    """
    try:
        document = json.loads(trial_path(directory).read_text("utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return empty_trial()
    if not isinstance(document, dict):
        return empty_trial()
    cycles = tuple(
        cycle
        for cycle in (_cycle_from(block) for block in document.get("cycles", []) or [])
        if cycle is not None
    )
    return Trial(
        bar_id=str(document.get("bar_id", TRIAL_BAR_ID)),
        ruling=str(document.get("ruling", TRIAL_RULING)),
        seat_drop_date=str(document.get("seat_drop_date", "")),
        cycles=cycles,
        reset_at=float(document.get("reset_at", 0.0) or 0.0),
    )


def write_trial(directory: Path, trial: Trial) -> None:
    """Write the trial, replacing the file rather than editing it in place."""
    directory.mkdir(parents=True, exist_ok=True)
    path = trial_path(directory)
    scratch = path.with_suffix(".json.tmp")
    scratch.write_text(json.dumps(trial.document(), indent=2) + "\n", encoding="utf-8")
    scratch.replace(path)


def _trial_stamp(at: float) -> str:
    """Render a trial timestamp in UTC, or `never` for the sentinel."""
    if not at:
        return "never"
    return datetime.fromtimestamp(at, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_trial_transition(
    store: Store, before: TrialStanding, after: TrialStanding, at: float
) -> bool:
    """Put one trial standing change in OTel and in the journal beside the records."""
    return otel_event.emit(
        otel_event.Event(
            name=TRIAL_TRANSITION_EVENT,
            at=at,
            attributes={
                "cti.admission.trial.bar_id": TRIAL_BAR_ID,
                "cti.admission.trial.from": before.state,
                "cti.admission.trial.to": after.state,
                "cti.admission.trial.assessed": after.judgement.assessed,
                "cti.admission.trial.reason": after.judgement.reason,
            },
            resource={"service.name": "arma-cti-admission"},
        ),
        journal=store.journal,
        endpoint=store.endpoint,
    )


def _is_iso_date(value: str) -> bool:
    """Whether the explicit seat-drop date is exactly YYYY-MM-DD."""
    try:
        return calendar_date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _closure_refusal(standing: TrialStanding, act: str) -> Refusal | None:
    """Refuse any act that would run a trial its own closure has ended."""
    if standing.state != TRIAL_CLOSED:
        return None
    return Refusal(
        "trial_closed",
        (
            f"bar={TRIAL_CLOSURE.bar_id}",
            f"closed_by={TRIAL_CLOSURE.ruling}",
            f"why={TRIAL_CLOSURE.why}",
            f"unmeasured={' '.join(TRIAL_CLOSURE.unmeasured)}",
            TRIAL_UNMEASURED_NOTE,
        ),
        (
            f"This trial is closed as inconclusive and is not restarted, so {act} would "
            "re-open a question its own ruling ended. Its cycles are kept as history. A "
            "different question needs a new bar_id, not this one's clock."
        ),
    )


def start_trial(
    store: Store,
    date: str,
    at: float,
    closure: TrialClosure | None = TRIAL_CLOSURE,
) -> tuple[TrialStanding, Refusal | None]:
    """Start the clock on the named start date; the command never infers it.

    `closure` is `trial_standing`'s, threaded rather than looked up, for that argument's
    reason: the harness has to stay runnable to be a harness, and the tests exercise the
    running machinery by passing `None`.
    """
    trial = read_trial(store.directory)
    before = trial_standing(trial, closure)
    closed = _closure_refusal(before, "starting its clock")
    if closed is not None:
        return before, closed
    if not _is_iso_date(date):
        return before, Refusal(
            "trial_start_date_invalid",
            (f"date={date or 'absent'}", "want=YYYY-MM-DD"),
            "Name the date the trialled change took effect explicitly; the tool never infers it.",
        )
    if trial.seat_drop_date:
        return before, Refusal(
            "trial_already_started",
            (f"seat_drop_date={trial.seat_drop_date}",),
            "The clock starts once. To re-start, clear the trial by hand: "
            "`just trial reset --force`, then `just trial start` again.",
        )
    started = trial._replace(seat_drop_date=date)
    write_trial(store.directory, started)
    after = trial_standing(started, closure)
    emit_trial_transition(store, trial_standing(empty_trial(), closure), after, at)
    return after, None


def _trial_state_refusal(trial: Trial, standing: TrialStanding) -> Refusal | None:
    """Refuse a record the trial's current lifecycle cannot accept."""
    closed = _closure_refusal(standing, "recording a cycle against it")
    if closed is not None:
        return closed
    if not trial.seat_drop_date:
        return Refusal(
            "trial_not_started",
            ("state=not_started",),
            "Start the clock first: `just trial start --date YYYY-MM-DD`. "
            "A trial that has not started accrues no cycles.",
        )
    if trial.bar_id != TRIAL_BAR_ID:
        return Refusal(
            "trial_bar_amended",
            (f"recorded={trial.bar_id}", f"current={TRIAL_BAR_ID}"),
            "The trial was started under a different bar. The criteria are immutable once the "
            "first assessment lands; amending them means clearing and starting fresh, which is "
            "a human-only act visible here and in git.",
        )
    if standing.state == FAILED:
        return Refusal(
            "trial_failed",
            (f"assessed={standing.judgement.assessed}/{TRIAL_N}", *standing.judgement.detail),
            "The trial has failed and is a finding for the human. Further cycles do not "
            "accrue until they rule — clear it with `just trial reset --force` "
            "to begin again.",
        )
    if standing.state == CLEARED:
        return Refusal(
            "trial_cleared",
            (
                f"assessed={standing.judgement.assessed}/{TRIAL_N}",
                f"why={standing.judgement.reason}",
            ),
            "The trial has cleared: ten consecutive clean cycles. The question is settled "
            "and no further cycle is owed.",
        )
    return None


def _trial_assessment_refusal(trial: Trial, assessment: CycleAssessment) -> Refusal | None:
    """Refuse a cycle that is not the next complete, fresh-issue assessment."""
    expected = len(trial.cycles) + 1
    if assessment.cycle != expected:
        return Refusal(
            "trial_cycle_out_of_sequence",
            (f"cycle={assessment.cycle}", f"expected={expected}"),
            "Record each dispatch cycle once, in order; the ten are consecutive.",
        )
    if any(cycle.issue == assessment.issue for cycle in trial.cycles):
        return Refusal(
            "trial_issue_repeated",
            (f"issue={assessment.issue}",),
            "Each cycle accrues against one fresh issue.",
        )
    if _cycle_from(assessment.document()) is None:
        return Refusal(
            "trial_cycle_invalid",
            (f"cycle={assessment.cycle}", f"issue={assessment.issue}"),
            "Record a positive issue, a dispatch id, and all five criteria with provenance.",
        )
    return None


def record_trial_cycle(
    store: Store,
    assessment: CycleAssessment,
    closure: TrialClosure | None = TRIAL_CLOSURE,
) -> tuple[TrialStanding, TrialStanding, Refusal | None]:
    """Add the next cycle unless the lifecycle or assessment refuses it."""
    trial = read_trial(store.directory)
    before = trial_standing(trial, closure)
    refusal = _trial_state_refusal(trial, before) or _trial_assessment_refusal(trial, assessment)
    if refusal is not None:
        return before, before, refusal
    opened = trial._replace(cycles=(*trial.cycles, assessment))
    write_trial(store.directory, opened)
    after = trial_standing(opened, closure)
    if after.state != before.state:
        emit_trial_transition(store, before, after, assessment.recorded_at or time.time())
    return before, after, None


def reset_trial(
    store: Store, at: float, closure: TrialClosure | None = TRIAL_CLOSURE
) -> tuple[TrialStanding, Refusal | None]:
    """Clear the trial after the human's ruling so that a fresh start may follow.

    A closed trial refuses this outright. `reset` is what makes a trial startable again, and
    ADR-0071 ruling 2 closed this one rather than restarting it: a clear that put the record
    back to `not_started` would both discard the cycles kept as history and re-open a
    question the ruling ended. Clearing it is a new pre-registration's job, under a new
    `bar_id`, not this clock's.
    """
    before = trial_standing(read_trial(store.directory), closure)
    closed = _closure_refusal(before, "clearing it")
    if closed is not None:
        return before, closed
    write_trial(store.directory, empty_trial()._replace(reset_at=at))
    after = trial_standing(empty_trial(), closure)
    if after.state != before.state:
        emit_trial_transition(store, before, after, at)
    return after, None


def add_audit_arguments(verb: argparse.ArgumentParser) -> None:
    """Add the seams an audit reads through, shared by `audit` and `record --from-audit`.

    One definition rather than two, because `record --from-audit` runs the same audit and
    must be pointable at the same close, the same checkout and the same dispatch records.
    A drift between the two would make the record fill from an audit nobody printed.
    """
    verb.add_argument("--close-file", default="", help="the close to audit; else read from gh")
    verb.add_argument(
        "--dispatch-dir",
        type=Path,
        default=Path(os.environ.get("CTI_DISPATCH_DIR", str(ledger.DISPATCH_ROOT))),
    )
    verb.add_argument("--ref", default=AUDIT_REF, help="the branch a landing must be on")


def add_trial_audit_arguments(verb: argparse.ArgumentParser) -> None:
    """Add the seams a trial audit reads through, on top of the route audit's.

    The trial's mechanical criteria read one more source than the route audit: the queue policy
    (`~/.arma-cti/queue/policy.json`) for criterion 1's freeze. `CTI_QUEUE_DIR` lets a unit test
    point this at a fixture policy the way `CTI_ADMISSION_DIR` points the store at a fixture dir.
    """
    add_audit_arguments(verb)
    verb.add_argument(
        "--queue-dir",
        type=Path,
        default=Path(os.environ.get("CTI_QUEUE_DIR", str(queue_policy.DEFAULT_QUEUE_DIR))),
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the trial's verbs. There are no others: the route bar's went with the bar."""
    parser = argparse.ArgumentParser(prog="trial", description=__doc__)
    # `CTI_ADMISSION_DIR` lets a test exercise the recipe without writing to this box's
    # real records. The *variable* and the *store path* keep their names for the reason
    # `DEFAULT_TRIAL_DIR` records — existing records read them, so renaming orphans history.
    # A flag is read by nobody but its caller, so it is renamed to match the module and
    # `--admission-dir` stays only as an alias, which keeps this rename off the break list.
    parser.add_argument(
        "--trial-dir",
        "--admission-dir",
        dest="trial_dir",
        type=Path,
        default=Path(os.environ.get("CTI_ADMISSION_DIR", str(DEFAULT_TRIAL_DIR))),
    )
    parser.add_argument("--otlp-endpoint", default="")
    parser.add_argument("--now", type=float, default=0.0)
    verbs = parser.add_subparsers(dest="verb", required=True)

    # `bar` prints the pre-registration, the closure and the five criteria by name;
    # `status` adds the standing and the cycles; `start` is the explicit clock-start act;
    # `audit` computes the three mechanical criteria a recorder reads before asserting the
    # two hand ones; `record` adds a cycle; `reset` is the human's clear; `report` is the
    # silent-while-clean line `just watch-report` carries.
    verbs.add_parser("bar", help="the pre-registration as ruled, and its closure")
    verbs.add_parser("status", help="the trial's bar, its standing and its cycles")
    verbs.add_parser("report", help="one line when the trial has failed; silent otherwise")

    start = verbs.add_parser("start", help="start the trial's clock: the explicit act")
    start.add_argument(
        "--date",
        required=True,
        help="the YYYY-MM-DD date the trialled change took effect",
    )

    reset = verbs.add_parser("reset", help="clear the trial: the human act after a failure")
    reset.add_argument("--force", action="store_true", required=True)

    audit_verb = verbs.add_parser(
        "audit", help="compute the trial's three mechanical criteria for one cycle"
    )
    audit_verb.add_argument("--issue", type=int, required=True)
    audit_verb.add_argument("--repo", type=Path, default=Path.cwd())
    add_trial_audit_arguments(audit_verb)

    # The six-check close audit on its own. It is the trial audit's own first step, and it
    # is separately reachable because #252's tool outlives the bar that commissioned it:
    # a close quoting `check=sha_on_main verdict=…` is readable evidence whether or not
    # anything is being trialled.
    close_audit = verbs.add_parser(
        "close-audit", help="the six checks over one issue's closing comment"
    )
    close_audit.add_argument("--issue", type=int, required=True)
    close_audit.add_argument("--repo", type=Path, default=Path.cwd())
    add_audit_arguments(close_audit)

    record = verbs.add_parser("record", help="add one dispatch cycle to the trial")
    record.add_argument("--cycle", type=int, required=True)
    record.add_argument("--issue", type=int, required=True)
    record.add_argument("--dispatch", default="", help="the dispatch id this cycle ran under")
    record.add_argument("--sha", default="", help="the landing SHA the cycle's close names")
    record.add_argument("--repo", type=Path, default=Path.cwd())
    record.add_argument(
        "--from-audit",
        action="store_true",
        required=True,
        help=(
            "run the trial audit and fill the three mechanical criteria; the two hand stay required"
        ),
    )
    # No defaults, on purpose: a criterion nobody passed is a criterion nobody checked.
    # `--from-audit` fills the mechanical three where the artefacts decide; the rest — the
    # two hand criteria always, and any mechanical one the audit could not decide — stay
    # required, so a hand criterion can never be recorded by defaulting to a pass.
    for criterion in TRIAL_CRITERIA:
        record.add_argument(
            f"--{criterion.key.replace('_', '-')}",
            dest=criterion.key,
            choices=(MET, NOT_MET),
            default="",
        )
    add_trial_audit_arguments(record)
    return parser.parse_args(argv)


def emit_lines(lines: Iterable[str], code: int = 0) -> int:
    """Print to the stream the exit code implies, and return it."""
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def _store(args: argparse.Namespace) -> Store:
    """Bind the verb to the records it reads and the collector it reports to."""
    return Store(directory=args.trial_dir, endpoint=args.otlp_endpoint)


def _now(args: argparse.Namespace) -> float:
    """Read the moment to reason about: the caller's, or the clock's."""
    return args.now or time.time()


# ---------------------------------------------------------------- the orchestration-seat trial


def trial_bar_lines() -> tuple[str, ...]:
    """Print the trial's bar as ruled, so the pre-registration lives in data rather than prose."""
    mechanical = sum(1 for criterion in TRIAL_CRITERIA if criterion.mechanical)
    lines = [
        f"bar_id={TRIAL_BAR_ID}",
        f"ruling={TRIAL_RULING}",
        f"n={TRIAL_N} consecutive dispatch cycles; the trial fails on any one criterion in any one",
        "fails_on=any criterion not met, in any cycle; the first miss ends it",
        "failure=recorded and reported; never auto-reverts anything; carries no failure class",
        (
            "clock=starts at `just trial start`, not at this tool's existence; "
            "not_started is distinct from 0/10"
        ),
        (
            "immutable=the criteria are fixed once the first assessment lands; "
            "amending means a new bar_id"
        ),
        "not_a_gate=`just dispatch` does not consult this and does not refuse on it",
        "interaction_quality=the human's alone; not mechanised and not counted here",
        (
            f"criteria={len(TRIAL_CRITERIA)} mechanical={mechanical} "
            f"hand={len(TRIAL_CRITERIA) - mechanical}"
        ),
    ]
    lines += [
        f"  criterion.{index}.{'mechanical' if criterion.mechanical else 'hand'}={criterion.key} "
        f"— {criterion.text}"
        for index, criterion in enumerate(TRIAL_CRITERIA, start=1)
    ]
    lines += list(closure_lines(closure_in_force()))
    return tuple(lines)


def closure_lines(closure: TrialClosure | None = TRIAL_CLOSURE) -> tuple[str, ...]:
    """Print the closure and what it leaves unread, or nothing where a trial still runs.

    The five criteria are printed **by name**, one line each, rather than as a count. A
    count reads as an accounting entry; the list is the loss, and a reader who meets it
    can tell which questions nobody is asking any more.
    """
    if closure is None:
        return ()
    return (
        f"closed={closure.verdict}",
        f"closed_by={closure.ruling}",
        f"closed_why={closure.why}",
        "restarted=no; the cycles already recorded are kept as history",
        f"unmeasured={len(closure.unmeasured)} criteria, named below",
        *(
            f"  unmeasured.{index}={key} — {TRIAL_CRITERIA_BY_KEY[key].text}"
            for index, key in enumerate(closure.unmeasured, start=1)
        ),
        "loss=" + TRIAL_UNMEASURED_NOTE,
    )


def closure_in_force() -> TrialClosure | None:
    """Return the closure every CLI verb applies.

    A function rather than a direct read of the constant so that the CLI, and not only the
    library beneath it, can be exercised as a live harness — the same reason `trial_standing`
    takes `closure` as an argument. A default argument would be bound at definition time and
    could not be swapped at all.
    """
    return TRIAL_CLOSURE


def run_trial_bar(_args: argparse.Namespace) -> int:
    """Print the pre-registration, its closure, and the criteria the closure leaves unread."""
    return emit_lines(trial_bar_lines())


def run_trial(args: argparse.Namespace) -> int:
    """Print the trial's bar, its standing and every cycle it recorded."""
    trial = read_trial(_store(args).directory)
    standing = trial_standing(trial, closure_in_force())
    cycles = tuple(line for cycle in trial.cycles for line in cycle.lines())
    return emit_lines((*trial_bar_lines(), standing.line(), *cycles))


def run_trial_report(args: argparse.Namespace) -> int:
    """Print one line when the trial has failed, nothing while it is clean.

    The `just watch-report` surface: silent while clean. It exits zero either way, because a
    clean trial is not a finding, and a failed one is a finding to read rather than a gate.

    A **closed** trial is silent here too, and that is the right answer rather than an
    oversight: a closure is a record, not a finding, and there is nothing for a reader of
    the top of an orchestrator's turn to do about it. `just trial bar` is where it is met.
    """
    line = trial_standing(read_trial(_store(args).directory), closure_in_force()).report_line()
    return emit_lines((line,) if line is not None else ())


def run_trial_start(args: argparse.Namespace) -> int:
    """Start the clock: the explicit act that begins accruing cycles."""
    after, refusal = start_trial(_store(args), args.date, _now(args), closure_in_force())
    if refusal is not None:
        return emit_lines(refusal.lines(), EXIT_REFUSED)
    return emit_lines(("started=true", after.line()))


def run_trial_reset(args: argparse.Namespace) -> int:
    """Clear the trial by hand: the act after a failure or a ruling, refused once closed."""
    at = _now(args)
    _, refusal = reset_trial(_store(args), at, closure_in_force())
    if refusal is not None:
        return emit_lines(refusal.lines(), EXIT_REFUSED)
    return emit_lines(("cleared=true", "state=not_started", f"reset_at={_trial_stamp(at)}"))


def run_trial_audit_for(args: argparse.Namespace) -> tuple[TrialAudit | None, Refusal | None]:
    """Run the trial audit over the close `args` points at, refusing where it cannot be read."""
    try:
        close, source = read_close(args)
    except (CloseUnreadableError, OSError) as unreadable:
        return None, Refusal(
            "close_unreadable",
            (f"issue={args.issue}", f"detail={unreadable}"),
            (
                "Pass --close-file with the close to audit, or make `gh` able to read it. "
                "An audit over a close nobody read is not an audit."
            ),
        )
    return trial_audit(
        Path(args.repo).expanduser(),
        args.issue,
        close,
        dispatch_root=Path(args.dispatch_dir).expanduser(),
        queue_dir=Path(args.queue_dir).expanduser(),
        source=source,
        ref=args.ref,
    ), None


def run_close_audit(args: argparse.Namespace) -> int:
    """Compute the six-check close audit and print it. Nothing is written and nothing recorded.

    Exit zero whatever the verdicts are: an audit that found `outside_window` ran correctly,
    and an exit code would turn its findings into a gate nobody asked for.
    """
    try:
        close, source = read_close(args)
    except (CloseUnreadableError, OSError) as unreadable:
        return emit_lines(
            Refusal(
                "close_unreadable",
                (f"issue={args.issue}", f"detail={unreadable}"),
                (
                    "Pass --close-file with the close to audit, or make `gh` able to read it. "
                    "An audit over a close nobody read is not an audit."
                ),
            ).lines(),
            EXIT_REFUSED,
        )
    return emit_lines(
        audit(
            Path(args.repo).expanduser(),
            args.issue,
            close,
            dispatch_root=Path(args.dispatch_dir).expanduser(),
            source=source,
            ref=args.ref,
        ).lines()
    )


def run_trial_audit(args: argparse.Namespace) -> int:
    """Compute the three mechanical criteria and print them. Nothing is recorded."""
    result, refusal = run_trial_audit_for(args)
    if refusal is not None or result is None:
        return emit_lines(refusal.lines() if refusal else (), EXIT_REFUSED)
    return emit_lines(result.lines())


def _apply_trial_audit(
    args: argparse.Namespace,
) -> tuple[list[str], set[str], Refusal | None]:
    """Fill decisive mechanical results, refusing a contradictory assertion."""
    filled: list[str] = []
    tool_filled: set[str] = set()
    if not args.from_audit:
        return filled, tool_filled, None
    result, refusal = run_trial_audit_for(args)
    if refusal is not None or result is None:
        return filled, tool_filled, refusal
    filled.append(f"audit={result.source}")
    for criterion in result.criteria:
        if not criterion.decisive:
            continue
        explicit = getattr(args, criterion.key)
        if explicit and explicit != criterion.verdict:
            return (
                filled,
                tool_filled,
                Refusal(
                    "trial_audit_conflict",
                    (
                        f"criterion={criterion.key}",
                        f"audit={criterion.verdict}",
                        f"asserted={explicit}",
                    ),
                    "The recorded artefact decides this criterion; resolve the evidence "
                    "instead of overriding it.",
                ),
            )
        setattr(args, criterion.key, criterion.verdict)
        tool_filled.add(criterion.key)
        filled.append(f"from_audit={criterion.key}={criterion.verdict}")
    if result.sha and not args.sha:
        args.sha = result.sha
        filled.append(f"from_audit=sha={result.sha}")
    if result.dispatch_id and not args.dispatch:
        args.dispatch = result.dispatch_id
        filled.append(f"from_audit=dispatch={result.dispatch_id}")
    return filled, tool_filled, None


def _build_trial_cycle(
    args: argparse.Namespace, at: float
) -> tuple[CycleAssessment | None, tuple[str, ...], Refusal | None]:
    """Build a complete cycle from audit results and explicit hand assertions."""
    filled, tool_filled, refusal = _apply_trial_audit(args)
    if refusal is not None:
        return None, tuple(filled), refusal
    verdicts: list[CriterionVerdict] = []
    missing: list[str] = []
    for criterion in TRIAL_CRITERIA:
        value = getattr(args, criterion.key)
        if value not in (MET, NOT_MET):
            missing.append(criterion.key)
            continue
        # `tool` only where the audit decided this criterion and the recorder let it stand;
        # everything else — an explicit flag, a hand criterion, or a mechanical one the audit left
        # undecided — is a hand assertion, so a hand criterion can never render as a tool pass.
        source = TOOL_CHECKED if criterion.key in tool_filled else HAND_ASSERTED
        verdicts.append(CriterionVerdict(criterion.key, value, source))
    if missing:
        return (
            None,
            tuple(filled),
            Refusal(
                "trial_criteria_missing",
                (f"missing={' '.join(sorted(missing))}",),
                "Every criterion is judged explicitly. A criterion nobody passed is a criterion "
                "nobody checked, and the two hand criteria can never be filled from an audit.",
            ),
        )
    return (
        CycleAssessment(
            cycle=args.cycle,
            issue=args.issue,
            dispatch_id=args.dispatch,
            criteria=tuple(verdicts),
            landing_sha=args.sha,
            recorded_at=at,
        ),
        tuple(filled),
        None,
    )


def run_trial_record(args: argparse.Namespace) -> int:
    """Add one cycle to the trial, refusing a criterion the harness will not invent.

    The closure is read **before** the cycle is built, not only inside `record_trial_cycle`:
    building it runs the full audit — a `gh` fetch and a git walk over the landing's commits
    — and where a criterion is unsupplied it refuses `trial_criteria_missing`. Against a
    closed trial that is both wasted work and the wrong refusal, since nothing can accrue to
    it either way. The library keeps its own check; this one is the CLI's, so the person and
    the caller get the same `trial_closed` answer.
    """
    store = _store(args)
    closed = _closure_refusal(
        trial_standing(read_trial(store.directory), closure_in_force()),
        "recording a cycle against it",
    )
    if closed is not None:
        return emit_lines(closed.lines(), EXIT_REFUSED)
    assessment, filled, refusal = _build_trial_cycle(args, _now(args))
    if refusal is not None or assessment is None:
        return emit_lines((*filled, *(refusal.lines() if refusal else ())), EXIT_REFUSED)
    before, after, refusal = record_trial_cycle(store, assessment, closure_in_force())
    if refusal is not None:
        return emit_lines((*filled, *(refusal.lines() if refusal else ())), EXIT_REFUSED)
    lines = [*filled, *assessment.lines(), after.line()]
    if after.state != before.state:
        lines.append(f"transition={before.state}->{after.state}")
    lines.extend(after.judgement.detail)
    return emit_lines(lines)


def main(argv: list[str] | None = None) -> int:
    """Dispatch the verb; every one is a read or a small file write."""
    args = parse_args(argv)
    verbs = {
        "bar": run_trial_bar,
        "status": run_trial,
        "start": run_trial_start,
        "audit": run_trial_audit,
        "close-audit": run_close_audit,
        "record": run_trial_record,
        "reset": run_trial_reset,
        "report": run_trial_report,
    }
    return verbs[args.verb](args)


if __name__ == "__main__":
    sys.exit(main())
