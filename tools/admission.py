"""`just admission`: the pre-registered admission bar, where a dispatch reads it (#224, D6).

Decision 6 admits a profile to a seat when its own gate record over N issues clears a bar
**pre-registered before that lane's numbers are seen**. #230's derivation proposed one from
the 131 eligible closed issues in this repo's own history; the human ruled on it in an
orchestrator session at **2026-08-05T20:00Z**, on #224, approving both parts and adding the
retry rule. That ruling is the sign-off, and this module is the ruling — not a paraphrase of
it. A bar that lives only in an issue comment is prose an agent has to remember, and the one
thing pre-registration cannot survive is a number that moves once the numbers are in.

So every constant below is quoted from the ruling and nothing here derives one. The
derivation is history; this is policy.

## The bar

**Part A — process, four criteria, every issue, no allowance (10/10).** Applicability is
per criterion — criterion 3 only bites where the landing touched an in-world surface — but
an *applicable* criterion that is not met fails the whole attempt at once, on the first
issue it fails on. The ruling's reasoning for the 10/10, against the 67.2% the Claude
history actually ran at: Part B measures outcomes *conditional on the gates having run*, so
an issue that skipped the corpus contributes an absent signal rather than a clean one, and
scoring absence as a pass would hollow out Part B. That is the #41 shape — a check that
could not run is not a check that passed — and it is why `UNKNOWN` is a distinct state here
and never passes.

**Part B — outcome: at most one unclean issue in ten.** `unclean` is §3 of the derivation:
a corrective rework commit on `main` within seven days of the close, a post-close finding
raised on the issue, or a reopen. The pre-registered operating characteristics are carried
in `OPERATING_CHARACTERISTICS` as the record of what this bar does and does not
discriminate — a Claude-equivalent lane clears roughly two attempts in three, a lane clean
60% of the time clears one in twenty.

**N = 10**, and **one retry**. The retry rule is the ruling's own addition, and it exists
because the 5% figure assumes a single attempt: unlimited retries multiply it, and the
pre-registered number silently stops meaning what it says. Two attempts take a 60%-clean
lane's effective false admission from 5% to about 9% while taking a Claude-equivalent
lane's eventual admission from 68% to about 90% — the asymmetry wanted, because a wrongly
rejected good lane costs only free-pool dispatches whereas a wrongly admitted bad lane
costs landed code. **Attempts do not pool.** A failed attempt's ten issues are gone; the
next attempt starts empty, which is why `Record` keeps attempts as a list rather than one
running tally.

## Per seat

- **implementer** — the bar above. This is the seat the 131-issue baseline describes.
- **mechanical** — two routes, either sufficient. A profile that cleared the implementer
  bar is admitted here too, because mechanical work is the strictly easier and fully
  gate-covered class and an implementer-derived bar cannot be too soft for it. A profile
  may also earn it directly on ten mechanical dispatches under the same rule. No lighter
  mechanical bar was created, and the derivation's refusal to invent a mechanical number
  is upheld.
- **recon** and **review** — the citation bar: over ten dispatches, at least 90% of the
  findings' file-and-line citations resolve to the code they name. This rests on Decision
  3's argument and on no baseline at all, and the record should keep saying so: all 26
  historical recon issues sit outside the eligible population by construction, so the seat
  has zero gate signal in the entire history and Decision 6's mechanism does not reach it.
  90% rather than 100% is deliberate — a citation can go stale under a concurrent landing
  through no fault of the reviewer, which this repo produces routinely. The inherited
  weakness stands unfixed: the check is silent about findings the lane failed to raise.

## What this binds, and what it does not

A profile on probation **is dispatchable**, because a record that only accrues as the lane
runs cannot accrue otherwise. What the bar binds mechanically is the far end: a profile
whose second attempt has failed is refused by `just dispatch` until a human clears it, and
there is no third attempt to be improvised. `claude-native` is `exempt` throughout —
nothing is leaving Claude there, and Decision 6's question does not arise.

## What starts at zero

**Everything.** No foreign profile carries a single assessment today: the 131-issue
population behind the bar is Claude's history, the bar is absolute rather than comparative,
and none of that history is any lane's record but Claude's. The store is empty until the
first `just admission record`, and `just admission status` prints `assessed=0/10 attempt=1`
for every foreign route until then. Nothing is back-filled, and the z.ai lane's one live
run to date — dispatch `d-20260805-191540-8c663f`, deliberately inert in a throwaway tree
outside this checkout — is not an assessment and is not recorded here.

## Where the counters come from

An assessment is not derivable from a dispatch alone: Part B needs seven days of rework
history and any post-close finding, which arrive long after the run ends. So `record` takes
the judgement and refuses to invent any part of it — every Part A criterion is a required
argument with no default, because a defaulted criterion is a criterion nobody checked.

Two of them are cross-checked against git, and the cross-check can only ever *refuse*:

- a landing whose paths touch an in-world surface may not be recorded with criterion 3
  waived as `n/a`;
- a landing that edited an acceptance spec or a generated file may not be recorded with
  criterion 4 met.

The cross-check never grants — it cannot see whether a corpus run was really quoted, only
whether waiving it was honest — and a cross-check that could not run refuses the record
rather than passing it.

## The audit (#252)

Everything `record` does not cross-check is *asserted* by whoever runs it, which for a
Claude-lane issue is the orchestrator reading a close against a landing by hand. Most of
that is computable, so `just admission audit --issue N` computes it: six checks over the
close, each with its own verdict vocabulary, printed for a human to read and to quote.

It lives here rather than in a tool of its own because the criteria live here, and a
second tool would hold a second copy of them. It reimplements nothing it can call: the
window tests — descends from the dispatch's base, postdates the dispatch's own start —
are `tools/ledger.py`'s from 7bc3f72 and are called, and `pool.json`'s green reading is
`tools/pool_merge.py`'s.

Two of its properties are refusals to overclaim, and they matter more than the list:

- a quoted gate block is reported `quoted` and never as proof the gate ran green. The
  paste **is** the evidence, and a tool cannot re-run history;
- the changelog check reports `undecidable` and has no input that makes it report `ok`,
  because whether a commit had user-visible effect is not decidable from its diff. #41's
  shape again, and the same reason `just prereqs` reports `unknown`.

`record --from-audit` fills the criteria the audit computed — two, both narrowly — and
leaves every other one required with no default, so the no-default discipline above
survives the automation.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `breaker.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes these importable. `ledger` carries the window tests
# the audit holds a quoted SHA against and `pool_merge` carries `pool.json`'s green
# reading; both are called rather than copied, and `tests/unit/test_admission_audit.py`
# fails if a second implementation of either appears here (#252). Neither imports this
# module, so there is no cycle to break.
import ledger
import otel_event
import pool_merge

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

EXIT_REFUSED: Final = 1

# ------------------------------------------------------------------ the bar, as ruled

# Which pre-registration a record was judged under. A bar that changed without this
# changing would silently re-judge its own history, which is the failure `ledger.py`'s
# calibration id exists to prevent. Moving a number below means minting a new id.
BAR_ID: Final = "cti.admission/224"

RULING: Final = "human ruling on #224, 2026-08-05T20:00Z, on #230's derivation of 2026-08-05T17:44Z"

# Ten dispatched implementation issues with a gate record, per §5 of the derivation: at
# eight the same rule clears a 60%-clean lane 11% of the time against 5% at ten, and below
# that admission is noise; above it the WIP freeze holds longer than it needs to.
N: Final = 10

# Part B. At most one unclean issue in N.
MAX_UNCLEAN: Final = 1

# The ruling's addition. One re-run, then a human.
MAX_ATTEMPTS: Final = 2

# The recon/review substitute, pooled across the attempt's dispatches — "its findings'
# citations" is one population over the ten, not ten populations of one.
CITATION_FLOOR: Final = 0.90

# What the bar discriminates, pre-registered so the number is not a preference. Pairs of
# (a lane's true clean rate, its probability of clearing "at most 1 unclean in 10").
OPERATING_CHARACTERISTICS: Final = ((0.885, 0.68), (0.75, 0.24), (0.60, 0.05))

# The Claude implementer seat's measured clean rate over the 131 eligible issues: 116 clean,
# 15 unclean. Carried as the baseline the bar was pre-registered against, and never used as
# a threshold — Decision 6's question is absolute, not comparative.
CLAUDE_BASELINE: Final = (116, 131)

MET: Final = "met"
NOT_MET: Final = "not_met"
NOT_APPLICABLE: Final = "n/a"
UNKNOWN: Final = "unknown"

# Only these two pass. `UNKNOWN` is here to have somewhere for "nobody checked" to go that
# is not a pass, and an absent criterion reads as `UNKNOWN` for the same reason.
# `MET` always passes; `NOT_APPLICABLE` passes only on the one criterion the ruling writes
# conditionally. `NOT_MET` and `UNKNOWN` never pass, and `UNKNOWN` is here so that "nobody
# checked" has somewhere to go that is not a pass.
CRITERION_STATES: Final = (MET, NOT_MET, NOT_APPLICABLE, UNKNOWN)


class Criterion(NamedTuple):
    """One of Part A's four, and whether it may be waived as not applicable."""

    key: str
    text: str
    waivable: bool


PART_A: Final = (
    Criterion("close_names_sha", "the close names the landing SHA on `main`", waivable=False),
    Criterion("fast_green", "`just fast` is quoted green on the landed tree", waivable=False),
    Criterion(
        "corpus_verdict",
        "where the landing touches an in-world surface, a full-corpus `just regress` "
        "verdict is quoted with its evidence path",
        waivable=True,
    ),
    Criterion(
        "hooks_clean",
        "`cog verify` passed and no acceptance spec or generated file was edited",
        waivable=False,
    ),
)

PART_A_KEYS: Final = tuple(criterion.key for criterion in PART_A)

# §3 of the derivation, verbatim: the three things any one of which makes an issue unclean.
UNCLEAN_REASONS: Final = ("rework", "finding", "reopen")

# ------------------------------------------------------------------------ the routes

GATE_BAR: Final = "gate"
CITATION_BAR: Final = "citations"

# Which bar a seat is judged under. Seats absent from this map are the ones Decision 2
# keeps off foreign lanes entirely; `just dispatch` refuses them before admission is
# consulted, so naming a bar for them here would be a second copy of that rule.
SEAT_BARS: Final[dict[str, str]] = {
    "implementer": GATE_BAR,
    "mechanical": GATE_BAR,
    "recon": CITATION_BAR,
    "review": CITATION_BAR,
}

# The ruling's first mechanical route: clearing this seat's bar admits the profile to the
# key's seat as well, without a second ten.
INHERITS_FROM: Final[dict[str, str]] = {"mechanical": "implementer"}

# The lanes and profiles this bar governs. Kept here rather than imported from
# `tools/dispatch.py` for `breaker.py`'s reason: admission is read *by* the dispatcher, and
# a cycle between the two would make either one unloadable on its own. The duplication is
# guarded — `tests/unit/test_admission.py` asserts these agree with the dispatch registry,
# so a lane or profile registered there without appearing here is a red unit tier.
FOREIGN_LANES: Final[tuple[str, ...]] = ("codex", "zai")
FOREIGN_PROFILES: Final[tuple[tuple[str, str], ...]] = (
    ("zai", "zai-glm52-max"),
    ("zai", "zai-glm47-max"),
    # #243. Four arms rather than z.ai's two, because effort is a real dimension on this
    # lane and a collapsed one there — each is a route the bar judges separately, since
    # Decision 6 admits a *profile* to a seat and not a lane to a seat.
    ("codex", "codex-sol-xhigh"),
    ("codex", "codex-sol-high"),
    ("codex", "codex-terra-medium"),
    ("codex", "codex-terra-low"),
)

EXEMPT: Final = "exempt"
PROBATION: Final = "probation"
ADMITTED: Final = "admitted"
ESCALATED: Final = "escalated"
NO_ROUTE: Final = "no_route"

OPEN: Final = "open"
CLEARED: Final = "cleared"
FAILED: Final = "failed"

TRANSITION_EVENT: Final = "cti.admission.transition"

# ------------------------------------------------------------------------ the pure core


class Assessment(NamedTuple):
    """One issue's judgement of a profile on a seat: Part A's four, and Part B's one bit.

    `citations` carries the recon/review substitute's two numbers and is zero on a gate
    route; `criteria` carries Part A's and is empty on a citation route. One type rather
    than two because an attempt is a list of these and the store would otherwise need to
    know which kind of list it was reading before it could read it.
    """

    issue: int
    dispatch_id: str
    criteria: tuple[tuple[str, str], ...] = ()
    unclean: tuple[str, ...] = ()
    citations_resolved: int = 0
    citations_total: int = 0
    landing_sha: str = ""
    recorded_at: float = 0.0

    def state_of(self, key: str) -> str:
        """Return what this assessment says about one Part A criterion, `unknown` if silent."""
        return dict(self.criteria).get(key, UNKNOWN)

    def part_a_missed(self) -> tuple[str, ...]:
        """Name every Part A criterion this issue did not clear, absent ones included.

        Waivability is per criterion and is checked here rather than only at the CLI's
        `choices`, because a record on disk can carry anything: `n/a` on a criterion the
        ruling makes unconditional is a waiver nobody was granted, and it is refused in
        the same breath as one nobody judged at all.
        """
        return tuple(
            criterion.key
            for criterion in PART_A
            if self.state_of(criterion.key) != MET
            and not (criterion.waivable and self.state_of(criterion.key) == NOT_APPLICABLE)
        )

    def document(self) -> dict[str, object]:
        """Render the assessment for its file."""
        return {
            "issue": self.issue,
            "dispatch_id": self.dispatch_id,
            "criteria": dict(self.criteria),
            "unclean": list(self.unclean),
            "citations_resolved": self.citations_resolved,
            "citations_total": self.citations_total,
            "landing_sha": self.landing_sha,
            "recorded_at": self.recorded_at,
        }


class Attempt(NamedTuple):
    """One run at the bar: its number, and the assessments it has accumulated."""

    number: int
    assessments: tuple[Assessment, ...] = ()

    def document(self) -> dict[str, object]:
        """Render the attempt for its file."""
        return {
            "number": self.number,
            "assessments": [assessment.document() for assessment in self.assessments],
        }


class Judgement(NamedTuple):
    """What one attempt's assessments amount to, and why."""

    state: str
    assessed: int
    unclean: int
    remaining: int
    reason: str
    detail: tuple[str, ...] = ()
    citations_resolved: int = 0
    citations_total: int = 0

    @property
    def citation_rate(self) -> float | None:
        """The pooled resolve rate, or `None` where nothing has been counted yet."""
        if not self.citations_total:
            return None
        return self.citations_resolved / self.citations_total


def judge_gate_attempt(assessments: Sequence[Assessment]) -> Judgement:
    """Judge one attempt at the implementer/mechanical bar: Part A, then Part B, then N.

    Part A is checked first and decides immediately, because "no allowance" means an
    attempt is over on the first issue that misses an applicable criterion — waiting for
    the tenth would let a lane accumulate nine clean issues behind a gate it never ran.
    """
    unclean = [assessment for assessment in assessments if assessment.unclean]
    missed = [
        f"issue={assessment.issue} missed={','.join(assessment.part_a_missed())}"
        for assessment in assessments
        if assessment.part_a_missed()
    ]
    common = {
        "assessed": len(assessments),
        "unclean": len(unclean),
        "remaining": max(0, N - len(assessments)),
    }
    if missed:
        return Judgement(
            FAILED,
            **common,
            reason=f"Part A allows no failure in {N}",
            detail=tuple(missed),
        )
    if len(unclean) > MAX_UNCLEAN:
        return Judgement(
            FAILED,
            **common,
            reason=f"Part B allows at most {MAX_UNCLEAN} unclean in {N}",
            detail=tuple(
                f"issue={assessment.issue} unclean={','.join(assessment.unclean)}"
                for assessment in unclean
            ),
        )
    if len(assessments) < N:
        return Judgement(OPEN, **common, reason=f"{N - len(assessments)} more to judge")
    return Judgement(
        CLEARED,
        **common,
        reason=f"Part A clean on all {N}; {len(unclean)} unclean, at most {MAX_UNCLEAN} allowed",
    )


def judge_citation_attempt(assessments: Sequence[Assessment]) -> Judgement:
    """Judge one attempt at the recon/review bar: pooled citation resolution over N dispatches.

    Pooled, because the ruling's population is "its findings' file-and-line citations"
    across the ten — one dispatch raising thirty citations and another raising two are not
    two equally weighted samples of the same thing.

    No early failure. A gate attempt can be over on its first issue, but a citation attempt
    cannot: how many citations remain to be counted is unknown until the dispatches are run,
    so a rate below the floor at dispatch three says nothing about the rate at ten.
    """
    resolved = sum(assessment.citations_resolved for assessment in assessments)
    total = sum(assessment.citations_total for assessment in assessments)
    common = {
        "assessed": len(assessments),
        "unclean": 0,
        "remaining": max(0, N - len(assessments)),
        "citations_resolved": resolved,
        "citations_total": total,
    }
    if len(assessments) < N:
        return Judgement(OPEN, **common, reason=f"{N - len(assessments)} more to judge")
    if not total:
        # Absence is not a pass — the same reasoning that put Part A's criterion 3 at 10/10.
        return Judgement(
            FAILED,
            **common,
            reason=f"no citations to check across {N} dispatches: absence is not a pass",
        )
    rate = resolved / total
    if rate < CITATION_FLOOR:
        return Judgement(
            FAILED,
            **common,
            reason=f"{resolved}/{total} citations resolve ({rate:.1%}), floor {CITATION_FLOOR:.0%}",
        )
    return Judgement(
        CLEARED,
        **common,
        reason=f"{resolved}/{total} citations resolve ({rate:.1%}), floor {CITATION_FLOOR:.0%}",
    )


def judge(bar: str, assessments: Sequence[Assessment]) -> Judgement:
    """Judge one attempt under the bar its seat is on."""
    if bar == CITATION_BAR:
        return judge_citation_attempt(assessments)
    return judge_gate_attempt(assessments)


class Standing(NamedTuple):
    """A profile's position on one seat: whether it may be dispatched, and what is left."""

    lane: str
    profile: str
    seat: str
    bar: str
    state: str
    attempt: int
    judgement: Judgement
    reason: str
    detail: tuple[str, ...] = ()

    @property
    def dispatchable(self) -> bool:
        """Whether `just dispatch` may plan this profile onto this seat.

        Probation is dispatchable on purpose: the record the bar judges only accrues as the
        lane runs, so refusing a profile that has not yet cleared would make the bar
        unclearable. What is refused is the far end — a second failed attempt, which is
        the ruling's escalation and is a human's to clear.
        """
        return self.state != ESCALATED

    @property
    def admitted(self) -> bool:
        """Whether Decision 6 has admitted this profile to this seat."""
        return self.state == ADMITTED

    def line(self) -> str:
        """One standing, in the tier's `key=value` form."""
        parts = [
            f"lane={self.lane}",
            f"profile={self.profile}",
            f"seat={self.seat}",
            f"bar={self.bar}",
            f"state={self.state}",
        ]
        if self.state in (PROBATION, ADMITTED, ESCALATED):
            parts.append(f"attempt={self.attempt}/{MAX_ATTEMPTS}")
            parts.append(f"assessed={self.judgement.assessed}/{N}")
            if self.bar == GATE_BAR:
                parts.append(f"unclean={self.judgement.unclean}/{MAX_UNCLEAN}")
            else:
                rate = self.judgement.citation_rate
                parts.append(
                    f"citations={self.judgement.citations_resolved}/"
                    f"{self.judgement.citations_total}"
                )
                parts.append(f"rate={'none' if rate is None else f'{rate:.1%}'}")
        parts.append("dispatch=" + ("allowed" if self.dispatchable else "refused"))
        parts.append(f"why={self.reason}")
        return " ".join(parts)


class Record(NamedTuple):
    """One route's whole history: every attempt it has made at its bar."""

    lane: str
    profile: str
    seat: str
    attempts: tuple[Attempt, ...] = ()
    reset_at: float = 0.0

    def document(self) -> dict[str, object]:
        """Render the record for its file."""
        return {
            "bar_id": BAR_ID,
            "ruling": RULING,
            "lane": self.lane,
            "profile": self.profile,
            "seat": self.seat,
            "reset_at": self.reset_at,
            "attempts": [attempt.document() for attempt in self.attempts],
        }

    @property
    def current(self) -> Attempt:
        """The attempt assessments are being added to, which is a fresh one when there is none."""
        return self.attempts[-1] if self.attempts else Attempt(1)


def stand(record: Record, inherited: Standing | None = None) -> Standing:
    """Read a record into a standing: the state machine the retry rule describes.

    `inherited` is the ruling's first mechanical route — a profile that cleared the
    implementer bar is admitted to mechanical without a second ten. It wins over this
    seat's own record whatever that record says, because the ruling makes it unconditional:
    an implementer-derived bar cannot be too soft for the strictly easier class.
    """
    bar = SEAT_BARS.get(record.seat, "")
    if not bar:
        return _outside(
            record,
            "none",
            NO_ROUTE,
            "ADR-0061 Decision 2 keeps this seat off foreign lanes entirely, so no "
            "admission bar reaches it; `just dispatch` refuses it first",
        )
    if record.lane not in FOREIGN_LANES:
        return _outside(
            record,
            bar,
            EXEMPT,
            "nothing leaves Claude on this lane, so Decision 6's question does not arise",
        )

    verdict = judge(bar, record.current.assessments)
    number = record.current.number
    cleared_before = any(
        judge(bar, attempt.assessments).state == CLEARED for attempt in record.attempts
    )

    if inherited is not None and inherited.admitted:
        state, attempt, judgement = ADMITTED, number, verdict
        reason = (
            f"cleared the {inherited.seat} bar, which the ruling makes sufficient for "
            f"the {record.seat} seat"
        )
        detail: tuple[str, ...] = (f"inherited_from={inherited.seat} {inherited.reason}",)
    elif cleared_before:
        state, attempt, judgement = ADMITTED, number, verdict
        reason, detail = verdict.reason, verdict.detail
    elif verdict.state == FAILED and number >= MAX_ATTEMPTS:
        state, attempt, judgement = ESCALATED, number, verdict
        reason = (
            f"attempt {number} of {MAX_ATTEMPTS} failed: {verdict.reason}. The ruling "
            "allows one re-run and no more"
        )
        detail = verdict.detail
    elif verdict.state == FAILED:
        # The next attempt starts empty, which is the whole of "attempts do not pool":
        # the failed ten are history and the standing already reads as the fresh attempt.
        state, attempt = PROBATION, number + 1
        judgement = Judgement(OPEN, 0, 0, N, f"attempt {number + 1} starts empty")
        reason = (
            f"attempt {number} failed ({verdict.reason}); attempt {number + 1} starts "
            "empty — attempts do not pool"
        )
        detail = verdict.detail
    else:
        state, attempt, judgement = PROBATION, number, verdict
        reason, detail = verdict.reason, verdict.detail

    return Standing(
        record.lane,
        record.profile,
        record.seat,
        bar=bar,
        state=state,
        attempt=attempt,
        judgement=judgement,
        reason=reason,
        detail=detail,
    )


def _outside(record: Record, bar: str, state: str, reason: str) -> Standing:
    """Render a route the bar does not judge: no foreign lane, or no route at all."""
    return Standing(
        record.lane,
        record.profile,
        record.seat,
        bar=bar,
        state=state,
        attempt=0,
        judgement=Judgement(OPEN, 0, 0, N, reason),
        reason=reason,
    )


# ------------------------------------------------------- what git can cross-check, and how

# The in-world surfaces, from CLAUDE.md's `just regress` row and docs/regression-tier.md's
# cost-control section. The daemon's world-facing half is named there as "anything that
# builds, validates, serialises or hands over what crosses the extension wire — the port's
# dispatch and refusals, the outbox, the command/effect codec", which is these modules.
#
# This list is used in one direction only: to refuse a landing that touched one of these
# while waiving criterion 3. It is never read as "this landing touched nothing, so the
# corpus was not needed" — that judgement stays the recorder's, because a list of paths
# cannot know what a change means.
IN_WORLD_PREFIXES: Final = (
    "addons/",
    "missions/",
    "extension/",
    "src/cti_daemon/port.py",
    "src/cti_daemon/outbox.py",
    "src/cti_daemon/commands.py",
    "src/cti_daemon/protocol.py",
    "src/cti_daemon/transport.py",
    "src/cti_daemon/manifest.py",
)

# The globs `.claude/hooks/protect-gated-paths.py` denies writes to. A landing carrying one
# of these did something the hooks exist to prevent, so criterion 4 cannot be met on it.
GATED_GLOBS: Final = ("*/generated/*", "*tests/specs/*")


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
    touched nothing; `None` is a cross-check that could not run, and this module refuses a
    record rather than reading that as a pass (#41).
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
    """Name the in-world surfaces a landing touched, empty when it touched none."""
    return tuple(path for path in paths if path.startswith(IN_WORLD_PREFIXES))


def touches_gated(paths: Iterable[str]) -> tuple[str, ...]:
    """Name the acceptance specs and generated files a landing edited, empty when none."""
    return tuple(path for path in paths if any(fnmatch.fnmatch(path, glob) for glob in GATED_GLOBS))


def crosscheck(assessment: Assessment, paths: tuple[str, ...] | None) -> tuple[str, ...]:
    """Name every contradiction between what was attested and what git shows.

    Refusals only. A clean cross-check grants nothing: it cannot see whether a corpus
    verdict was really quoted into the issue, only whether waiving one was honest.
    """
    if paths is None:
        return (
            "crosscheck=unavailable",
            f"sha={assessment.landing_sha or 'none'}",
            "git could not name that commit's paths, so the cross-check did not run",
        )
    found: list[str] = []
    in_world = touches_in_world(paths)
    if assessment.state_of("corpus_verdict") == NOT_APPLICABLE and in_world:
        found.append(
            "corpus_verdict waived as n/a, but the landing touched an in-world surface: "
            + " ".join(in_world[:5])
        )
    gated = touches_gated(paths)
    if assessment.state_of("hooks_clean") == MET and gated:
        found.append(
            "hooks_clean recorded as met, but the landing edited a gated path: "
            + " ".join(gated[:5])
        )
    return tuple(found)


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

# The one verdict every check may reach: this check could not run. It is never a pass and
# nothing in `criteria_from_audit` reads it as one (#41).
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
        """Render the whole audit as the block a close quotes verbatim."""
        computed = criteria_from_audit(self)
        named = {key for key, _ in computed}
        return (
            f"issue={self.issue}",
            f"source={self.source}",
            f"sha={self.sha or 'none'}",
            f"dispatch={self.dispatch_id or 'none'}",
            *(check.line() for check in self.checks),
            *(f"computed={key}={state}" for key, state in computed),
            "explicit=" + " ".join(key for key in PART_A_KEYS if key not in named),
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
    never read as a waiver — `IN_WORLD_PREFIXES`' own header says why, and
    `criteria_from_audit` accordingly fills nothing from it.
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


def criteria_from_audit(result: Audit) -> tuple[tuple[str, str], ...]:
    """Which Part A criteria this audit computed, and to what.

    Two, and both narrowly.

    `close_names_sha` is exactly what checks 1 and 2 decide between them: a commit the
    close names, on `main`, inside the dispatch's window. A window that could not be
    bounded fills nothing, because `unbounded` is not `not_met`.

    `corpus_verdict` is filled in the refusing direction only. A landing that owes a pool
    verdict and whose quoted evidence is red, missing or absent has not met the criterion,
    and that is computable. The other direction is not: `pool.json` records no filter, so
    a green pool cannot be shown to have been the *full* corpus, and `not_owed` is not a
    waiver — `IN_WORLD_PREFIXES` says in its own header that a list of paths cannot know
    what a change means.

    `fast_green` is never here at all, whatever the gate check found. Quoted is not green.

    `hooks_clean` is never here either: `crosscheck` already refuses a record that claims
    it over a gated-path edit, and computing it a second time here would be the second
    copy this module exists to avoid.
    """
    computed: list[tuple[str, str]] = []
    sha_verdict = result.verdict_of("sha_on_main")
    window = result.verdict_of("dispatch_window")
    if sha_verdict == AUDIT_OK and window == AUDIT_OK:
        computed.append(("close_names_sha", MET))
    elif sha_verdict in (AUDIT_ABSENT, AUDIT_NOT_ON_MAIN) or window == AUDIT_OUTSIDE_WINDOW:
        computed.append(("close_names_sha", NOT_MET))
    if result.verdict_of("corpus_owed") == AUDIT_OWED and result.verdict_of("evidence") in (
        AUDIT_RED,
        AUDIT_PATH_MISSING,
        AUDIT_ABSENT,
    ):
        computed.append(("corpus_verdict", NOT_MET))
    return tuple(computed)


# ------------------------------------------------------------------------------ the store

# Outside every worktree, beside the breaker's own state and for its reason: a profile's
# admission record must outlive the worktree and the session that earned it.
DEFAULT_ADMISSION_DIR: Final = Path.home() / ".arma-cti" / "admission"

TRANSITION_JOURNAL: Final = "transitions.jsonl"


class Store(NamedTuple):
    """Where the records live and where transitions are sent."""

    directory: Path = DEFAULT_ADMISSION_DIR
    endpoint: str = ""

    @property
    def journal(self) -> Path:
        """Where every transition is written, whether or not the collector took it."""
        return self.directory / TRANSITION_JOURNAL


def record_path(directory: Path, lane: str, profile: str, seat: str) -> Path:
    """Where one route keeps its record."""
    return directory / f"{lane}.{profile}.{seat}.json"


def _assessment_from(document: object) -> Assessment | None:
    """Read one assessment back, or `None` for a shape this reader does not carry."""
    if not isinstance(document, dict):
        return None
    criteria = document.get("criteria")
    return Assessment(
        issue=int(document.get("issue", 0) or 0),
        dispatch_id=str(document.get("dispatch_id", "")),
        criteria=tuple(sorted((str(k), str(v)) for k, v in criteria.items()))
        if isinstance(criteria, dict)
        else (),
        unclean=tuple(str(reason) for reason in document.get("unclean", []) or []),
        citations_resolved=int(document.get("citations_resolved", 0) or 0),
        citations_total=int(document.get("citations_total", 0) or 0),
        landing_sha=str(document.get("landing_sha", "")),
        recorded_at=float(document.get("recorded_at", 0.0) or 0.0),
    )


def read_record(directory: Path, lane: str, profile: str, seat: str) -> Record:
    """Read a route's record, treating absent and unreadable alike as a route at zero.

    An absent file is a profile that has never been assessed, which is where every foreign
    route starts. An unreadable one has lost its history, and the safe reading of lost
    history is not "escalate forever": the attempts that mattered will be run again.
    """
    empty = Record(lane, profile, seat)
    try:
        document = json.loads(record_path(directory, lane, profile, seat).read_text("utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return empty
    if not isinstance(document, dict):
        return empty
    attempts: list[Attempt] = []
    for block in document.get("attempts", []) or []:
        if not isinstance(block, dict):
            continue
        assessments = [_assessment_from(entry) for entry in block.get("assessments", []) or []]
        attempts.append(
            Attempt(
                number=int(block.get("number", len(attempts) + 1) or len(attempts) + 1),
                assessments=tuple(item for item in assessments if item is not None),
            )
        )
    return empty._replace(
        attempts=tuple(attempts), reset_at=float(document.get("reset_at", 0.0) or 0.0)
    )


def write_record(directory: Path, record: Record) -> None:
    """Write a route's record, replacing the file rather than editing it in place."""
    directory.mkdir(parents=True, exist_ok=True)
    path = record_path(directory, record.lane, record.profile, record.seat)
    scratch = path.with_suffix(".json.tmp")
    scratch.write_text(json.dumps(record.document(), indent=2) + "\n", encoding="utf-8")
    scratch.replace(path)


def emit_transition(store: Store, before: Standing, after: Standing, at: float) -> bool:
    """Put one standing change in OTel and in the journal beside the records."""
    return otel_event.emit(
        otel_event.Event(
            name=TRANSITION_EVENT,
            at=at,
            attributes={
                "cti.lane": after.lane,
                "cti.profile": after.profile,
                "cti.seat": after.seat,
                "cti.admission.bar_id": BAR_ID,
                "cti.admission.from": before.state,
                "cti.admission.to": after.state,
                "cti.admission.attempt": after.attempt,
                "cti.admission.assessed": after.judgement.assessed,
                "cti.admission.unclean": after.judgement.unclean,
                "cti.admission.reason": after.reason,
            },
            resource={"service.name": "arma-cti-admission", "cti.lane": after.lane},
        ),
        journal=store.journal,
        endpoint=store.endpoint,
    )


def standing_for(store: Store, lane: str, profile: str, seat: str) -> Standing:
    """Read one route's standing, following the ruling's inheritance where a seat has one."""
    inherited = None
    source = INHERITS_FROM.get(seat)
    if source is not None:
        inherited = stand(read_record(store.directory, lane, profile, source))
    return stand(read_record(store.directory, lane, profile, seat), inherited)


class Refusal(NamedTuple):
    """One refusal: its class, what was found, and what the caller should do."""

    kind: str
    found: tuple[str, ...]
    action: str

    def lines(self) -> tuple[str, ...]:
        """Render the refusal as the lines the caller reads."""
        return (f"refusal={self.kind}", *self.found, f"action={self.action}")


def append(
    store: Store,
    lane: str,
    profile: str,
    seat: str,
    assessment: Assessment,
) -> tuple[Standing, Standing, Refusal | None]:
    """Add one assessment to the open attempt, and say what it did to the standing.

    Returns `(before, after, refusal)`. Three states refuse an append and each for its own
    reason: an admitted route has discharged the bar and further evidence is the breaker's
    ground rather than admission's; an escalated route is a human's to clear; and a route
    Decision 2 keeps off foreign lanes has no bar to be assessed against at all.
    """
    before = standing_for(store, lane, profile, seat)
    if before.state == NO_ROUTE:
        return (
            before,
            before,
            Refusal(
                "seat_has_no_bar",
                (f"seat={seat}", f"known={' '.join(sorted(SEAT_BARS))}"),
                "ADR-0061 Decision 2 keeps this seat off foreign lanes; nothing to assess.",
            ),
        )
    if before.state == EXEMPT:
        return (
            before,
            before,
            Refusal(
                "lane_exempt",
                (f"lane={lane}", f"foreign={' '.join(FOREIGN_LANES)}"),
                "Nothing leaves Claude on this lane, so Decision 6 does not judge it.",
            ),
        )
    if before.state == ADMITTED:
        return (
            before,
            before,
            Refusal(
                "already_admitted",
                (f"lane={lane}", f"profile={profile}", f"seat={seat}", f"why={before.reason}"),
                (
                    "The bar is discharged for this route. Quality after admission is the "
                    "lane breaker's ground (#226), not a longer admission run."
                ),
            ),
        )
    if before.state == ESCALATED:
        return (
            before,
            before,
            Refusal(
                "admission_escalated",
                (f"lane={lane}", f"profile={profile}", f"seat={seat}", f"why={before.reason}"),
                (
                    f"Both attempts failed. The ruling allows {MAX_ATTEMPTS} and no more: this "
                    f"is a human's call. `just admission reset --lane {lane} --profile {profile} "
                    f"--seat {seat} --force` starts the record over once they have made it."
                ),
            ),
        )

    record = read_record(store.directory, lane, profile, seat)
    current = record.current
    # A failed attempt is never appended to: `stand` has already moved the standing on to
    # the next attempt number, and the next assessment opens that attempt empty.
    if before.attempt != current.number:
        attempts = (*record.attempts, Attempt(before.attempt, (assessment,)))
    else:
        opened = current._replace(assessments=(*current.assessments, assessment))
        attempts = (*record.attempts[:-1], opened) if record.attempts else (opened,)
    write_record(store.directory, record._replace(attempts=attempts))

    after = standing_for(store, lane, profile, seat)
    if after.state != before.state:
        emit_transition(store, before, after, assessment.recorded_at or time.time())
    return before, after, None


def clear(store: Store, lane: str, profile: str, seat: str, at: float) -> Standing:
    """Start a route's record over, which is how an escalation ends. A human act."""
    before = standing_for(store, lane, profile, seat)
    write_record(store.directory, Record(lane, profile, seat, (), reset_at=at))
    after = standing_for(store, lane, profile, seat)
    if after.state != before.state:
        emit_transition(store, before, after, at)
    return after


# ------------------------------------------------------- the read `just dispatch` takes


def dispatch_refusal(store: Store, lane: str, profile: str, seat: str) -> tuple[str, ...] | None:
    """Take the pre-dispatch read: `None` to proceed, or the lines a refusing dispatcher prints.

    Only an escalated route refuses. Everything else — exempt, no route, probation,
    admitted — proceeds here, because probation must be dispatchable for the record to
    accrue and because the seats with no route are refused by Decision 2 upstream of this.
    """
    standing = standing_for(store, lane, profile, seat)
    if standing.dispatchable:
        return None
    return (
        f"lane={lane}",
        f"profile={profile}",
        f"seat={seat}",
        f"attempt={standing.attempt}/{MAX_ATTEMPTS}",
        f"why={standing.reason}",
        *standing.detail,
    )


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


# ------------------------------------------------------------------------------------ CLI


def bar_lines() -> tuple[str, ...]:
    """Print the bar as ruled: the canonical statement, so nobody has to remember it."""
    lines = [
        f"bar_id={BAR_ID}",
        f"ruling={RULING}",
        f"n={N}",
        (
            f"attempts={MAX_ATTEMPTS} (one re-run; each attempt is {N} fresh issues, and "
            "they do not pool)"
        ),
        (
            f"baseline=claude implementer {CLAUDE_BASELINE[0]}/{CLAUDE_BASELINE[1]} clean "
            f"({CLAUDE_BASELINE[0] / CLAUDE_BASELINE[1]:.1%}), recorded, never a threshold"
        ),
        f"part_a=every criterion, every issue, {N}/{N}, no allowance",
    ]
    lines += [
        f"  criterion.{index}={criterion.key} waivable="
        f"{str(criterion.waivable).lower()} — {criterion.text}"
        for index, criterion in enumerate(PART_A, start=1)
    ]
    lines.append(f"part_b=at most {MAX_UNCLEAN} unclean in {N}")
    lines.append(f"  unclean={' '.join(UNCLEAN_REASONS)} (any one, per §3 of the derivation)")
    lines += [
        f"  oc.clean_rate={rate:.3f} p_clears={probability:.2f}"
        for rate, probability in OPERATING_CHARACTERISTICS
    ]
    lines.append(f"citation_bar=at least {CITATION_FLOOR:.0%} of cited file:line resolve, pooled")
    lines += [f"  seat.{seat}={bar}" for seat, bar in sorted(SEAT_BARS.items())]
    lines += [
        f"  inherits.{seat}={source} (clearing {source} admits {seat} with no second run)"
        for seat, source in sorted(INHERITS_FROM.items())
    ]
    return tuple(lines)


def routes() -> tuple[tuple[str, str, str], ...]:
    """Every foreign route this bar governs, which is what `status` enumerates."""
    return tuple(
        (lane, profile, seat) for lane, profile in FOREIGN_PROFILES for seat in sorted(SEAT_BARS)
    )


def status_lines(store: Store) -> tuple[str, ...]:
    """One line per foreign route, plus the sentence that says what starts at zero."""
    lines = [f"bar_id={BAR_ID}", f"store={store.directory}"]
    standings = [standing_for(store, *route) for route in routes()]
    assessed = sum(standing.judgement.assessed for standing in standings)
    if not assessed and not any(standing.admitted for standing in standings):
        lines.append(
            "baseline=zero — no foreign profile carries an assessment. The 131 issues "
            "behind this bar are Claude's history, the bar is absolute rather than "
            "comparative, and nothing is back-filled."
        )
    lines += [standing.line() for standing in standings]
    return tuple(lines)


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


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Six verbs: the bar, every route, one route, an audit, an assessment, a reset."""
    parser = argparse.ArgumentParser(prog="admission", description=__doc__)
    # `CTI_ADMISSION_DIR` lets a test exercise the recipe, and `just dispatch`'s own seam,
    # without writing to this box's real admission records.
    parser.add_argument(
        "--admission-dir",
        type=Path,
        default=Path(os.environ.get("CTI_ADMISSION_DIR", str(DEFAULT_ADMISSION_DIR))),
    )
    parser.add_argument("--otlp-endpoint", default="")
    parser.add_argument("--now", type=float, default=0.0)
    verbs = parser.add_subparsers(dest="verb", required=True)

    verbs.add_parser("bar", help="the bar as ruled, printed")
    verbs.add_parser("status", help="every foreign route and its standing")

    audit_verb = verbs.add_parser("audit", help="compute what a close's Part A claims can be")
    audit_verb.add_argument("--issue", type=int, required=True)
    audit_verb.add_argument("--repo", type=Path, default=Path.cwd())
    add_audit_arguments(audit_verb)

    for name, help_text in (
        ("check", "the pre-dispatch read for one route, as an exit code"),
        ("record", "add one issue's assessment to the open attempt"),
        ("reset", "start a route's record over: the human act after an escalation"),
    ):
        verb = verbs.add_parser(name, help=help_text)
        verb.add_argument("--lane", required=True)
        verb.add_argument("--profile", required=True)
        verb.add_argument("--seat", required=True)
        if name == "reset":
            verb.add_argument("--force", action="store_true", required=True)
        if name != "record":
            continue
        verb.add_argument("--issue", type=int, required=True)
        verb.add_argument("--dispatch", default="", help="the dispatch id this issue was run under")
        verb.add_argument("--sha", default="", help="the landing SHA the close names")
        verb.add_argument("--repo", type=Path, default=Path.cwd())
        # No defaults, on purpose: a Part A criterion nobody passed is a criterion nobody
        # checked, and this module has one state for that and it does not pass.
        for criterion in PART_A:
            verb.add_argument(
                f"--{criterion.key.replace('_', '-')}",
                dest=criterion.key,
                choices=(MET, NOT_MET, NOT_APPLICABLE) if criterion.waivable else (MET, NOT_MET),
                default="",
            )
        verb.add_argument(
            "--unclean",
            default="",
            help=f"comma-separated, any of {'/'.join(UNCLEAN_REASONS)}; empty means clean",
        )
        verb.add_argument("--citations-resolved", type=int, default=0)
        verb.add_argument("--citations-total", type=int, default=0)
        verb.add_argument(
            "--from-audit",
            action="store_true",
            help="run the audit and fill the criteria it computes; the rest stay required",
        )
        add_audit_arguments(verb)
    return parser.parse_args(argv)


def emit_lines(lines: Iterable[str], code: int = 0) -> int:
    """Print to the stream the exit code implies, and return it."""
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def _store(args: argparse.Namespace) -> Store:
    """Bind the verb to the records it reads and the collector it reports to."""
    return Store(directory=args.admission_dir, endpoint=args.otlp_endpoint)


def _now(args: argparse.Namespace) -> float:
    """Read the moment to reason about: the caller's, or the clock's."""
    return args.now or time.time()


def build_assessment(
    args: argparse.Namespace, bar: str, at: float
) -> tuple[Assessment | None, Refusal | None]:
    """Turn the recorder's arguments into an assessment, refusing anything it left out.

    The two bars want disjoint evidence, and passing one bar's evidence on the other's
    route is refused rather than ignored: a recon record carrying Part A flags means the
    recorder believed it was recording something this bar does not judge.
    """
    unclean = tuple(part.strip() for part in args.unclean.split(",") if part.strip())
    unknown = tuple(reason for reason in unclean if reason not in UNCLEAN_REASONS)
    if unknown:
        return None, Refusal(
            "unknown_unclean_reason",
            (f"given={' '.join(unknown)}", f"known={' '.join(UNCLEAN_REASONS)}"),
            "§3 of the derivation names three reasons and the bar judges those three.",
        )
    given = {criterion.key: getattr(args, criterion.key) for criterion in PART_A}
    if bar == CITATION_BAR:
        return _citation_assessment(args, given, at)
    return _gate_assessment(args, given, unclean, at)


def _citation_assessment(
    args: argparse.Namespace, given: dict[str, str], at: float
) -> tuple[Assessment | None, Refusal | None]:
    """Build a recon/review assessment: two counts, and no Part A evidence at all."""
    named = tuple(key for key, value in given.items() if value)
    if named:
        return None, Refusal(
            "wrong_bar_evidence",
            (f"seat={args.seat}", f"bar={CITATION_BAR}", f"given={' '.join(sorted(named))}"),
            "This seat is judged on citation resolution; Part A does not apply to it.",
        )
    if args.citations_total <= 0:
        return None, Refusal(
            "citations_missing",
            (f"resolved={args.citations_resolved}", f"total={args.citations_total}"),
            (
                "Pass --citations-total and --citations-resolved. A dispatch that cited "
                "nothing is recorded as total=0 only when that is what it did, and ten "
                "of those fail the bar rather than clearing it."
            ),
        )
    if args.citations_resolved > args.citations_total:
        return None, Refusal(
            "citations_impossible",
            (f"resolved={args.citations_resolved}", f"total={args.citations_total}"),
            "More citations resolved than were raised. Re-count and record again.",
        )
    return Assessment(
        issue=args.issue,
        dispatch_id=args.dispatch,
        citations_resolved=args.citations_resolved,
        citations_total=args.citations_total,
        recorded_at=at,
    ), None


def _gate_assessment(
    args: argparse.Namespace, given: dict[str, str], unclean: tuple[str, ...], at: float
) -> tuple[Assessment | None, Refusal | None]:
    """Build an implementer/mechanical assessment: Part A's four, judged explicitly."""
    absent = tuple(key for key, value in given.items() if not value)
    if absent:
        return None, Refusal(
            "criteria_missing",
            (f"missing={' '.join(sorted(absent))}",),
            (
                "Every Part A criterion is judged explicitly. A criterion nobody passed is "
                "a criterion nobody checked, and this bar does not read that as a pass."
            ),
        )
    if args.citations_total or args.citations_resolved:
        return None, Refusal(
            "wrong_bar_evidence",
            (f"seat={args.seat}", f"bar={GATE_BAR}", "given=citations"),
            "This seat is judged on Part A and Part B; citation counts do not apply to it.",
        )
    return Assessment(
        issue=args.issue,
        dispatch_id=args.dispatch,
        criteria=tuple(sorted(given.items())),
        unclean=unclean,
        landing_sha=args.sha,
        recorded_at=at,
    ), None


def run_bar(_args: argparse.Namespace) -> int:
    """Print the bar."""
    return emit_lines(bar_lines())


def run_status(args: argparse.Namespace) -> int:
    """Print every foreign route's standing."""
    return emit_lines(status_lines(_store(args)))


def run_check(args: argparse.Namespace) -> int:
    """Take the pre-dispatch read, as an exit code plus the line a caller quotes."""
    standing = standing_for(_store(args), args.lane, args.profile, args.seat)
    if standing.dispatchable:
        return emit_lines((standing.line(),))
    return emit_lines((standing.line(), *standing.detail), EXIT_REFUSED)


def _crosscheck_refusal(args: argparse.Namespace, assessment: Assessment) -> Refusal | None:
    """Run the git cross-check where criterion 1 says there is a SHA to check against."""
    if assessment.state_of("close_names_sha") != MET:
        # The attempt fails on Part A whatever git says, so there is nothing to contradict.
        return None
    if not assessment.landing_sha:
        return Refusal(
            "sha_missing",
            (f"issue={args.issue}", "close_names_sha=met"),
            "Pass --sha with the landing SHA the close names, so the cross-check can run.",
        )
    found = crosscheck(
        assessment, landing_paths(Path(args.repo).expanduser(), assessment.landing_sha)
    )
    if not found:
        return None
    return Refusal(
        "crosscheck_failed",
        (f"issue={args.issue}", f"sha={assessment.landing_sha}", *found),
        (
            "Nothing was recorded. Either the attestation is wrong, or the repo at --repo "
            "does not carry that commit. A cross-check that could not run is not one that "
            "passed."
        ),
    )


def run_audit_for(args: argparse.Namespace) -> tuple[Audit | None, Refusal | None]:
    """Run one audit over the close `args` points at, refusing where the close cannot be read."""
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
    return audit(
        Path(args.repo).expanduser(),
        args.issue,
        close,
        dispatch_root=Path(args.dispatch_dir).expanduser(),
        source=source,
        ref=args.ref,
    ), None


def run_audit(args: argparse.Namespace) -> int:
    """Compute the close audit and print it. Nothing is written and nothing is recorded.

    Its output is evidence *for* a `just admission record` invocation; the record stays a
    deliberate act by whoever is willing to assert the criteria this audit could not
    compute. Exit zero whatever the verdicts are — an audit that found `outside_window` ran
    correctly, and an exit code would turn its findings into a gate nobody asked for.
    """
    result, refusal = run_audit_for(args)
    if refusal is not None or result is None:
        return emit_lines(refusal.lines() if refusal else (), EXIT_REFUSED)
    return emit_lines(result.lines())


def _fill_from_audit(args: argparse.Namespace) -> tuple[tuple[str, ...], Refusal | None]:
    """Fill the criteria the audit computes onto `args`, and say which it filled.

    An explicit flag on the command line always wins: `--from-audit` is a convenience over
    the reading a human would otherwise do by hand, never an override of one they did. The
    SHA is filled the same way, so the cross-check runs against the commit the audit
    actually held against the window.
    """
    result, refusal = run_audit_for(args)
    if refusal is not None or result is None:
        return (), refusal
    filled: list[str] = []
    for key, state in criteria_from_audit(result):
        if getattr(args, key, ""):
            continue
        setattr(args, key, state)
        filled.append(f"{key}={state}")
    if result.sha and not args.sha:
        args.sha = result.sha
        filled.append(f"sha={result.sha}")
    if result.dispatch_id and not args.dispatch:
        args.dispatch = result.dispatch_id
        filled.append(f"dispatch={result.dispatch_id}")
    return (f"audit={result.source}", *(f"from_audit={item}" for item in filled)), None


def run_record(args: argparse.Namespace) -> int:
    """Add one assessment, refusing every part of it this bar will not invent."""
    bar = SEAT_BARS.get(args.seat, "")
    if not bar:
        return emit_lines(
            Refusal(
                "seat_has_no_bar",
                (f"seat={args.seat}", f"known={' '.join(sorted(SEAT_BARS))}"),
                "ADR-0061 Decision 2 keeps this seat off foreign lanes; nothing to assess.",
            ).lines(),
            EXIT_REFUSED,
        )
    filled: tuple[str, ...] = ()
    if args.from_audit:
        filled, refusal = _fill_from_audit(args)
        if refusal is not None:
            return emit_lines(refusal.lines(), EXIT_REFUSED)
    assessment, refusal = build_assessment(args, bar, _now(args))
    if refusal is not None or assessment is None:
        return emit_lines((*filled, *(refusal.lines() if refusal else ())), EXIT_REFUSED)
    if bar == GATE_BAR:
        refusal = _crosscheck_refusal(args, assessment)
        if refusal is not None:
            return emit_lines(refusal.lines(), EXIT_REFUSED)

    before, after, refusal = append(_store(args), args.lane, args.profile, args.seat, assessment)
    if refusal is not None:
        return emit_lines(refusal.lines(), EXIT_REFUSED)
    lines = [*filled, f"issue={args.issue}", after.line()]
    if after.state != before.state:
        lines.append(f"transition={before.state}->{after.state}")
    lines.extend(after.detail)
    return emit_lines(lines)


def run_reset(args: argparse.Namespace) -> int:
    """Clear a route by hand, which is how the ruling's escalation ends."""
    after = clear(_store(args), args.lane, args.profile, args.seat, _now(args))
    return emit_lines(("cleared=true", after.line()))


def main(argv: list[str] | None = None) -> int:
    """Dispatch the verb; every one is a read or a small file write."""
    args = parse_args(argv)
    verbs = {
        "bar": run_bar,
        "status": run_status,
        "check": run_check,
        "audit": run_audit,
        "record": run_record,
        "reset": run_reset,
    }
    return verbs[args.verb](args)


if __name__ == "__main__":
    sys.exit(main())
