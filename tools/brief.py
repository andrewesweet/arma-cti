"""The invariant half of a dispatch briefing, composed from data (#251, orchestration §5).

The twenty-fourth retro measured what a dispatch briefing still restates after #208's
handoff template landed: the #222 re-run instruction, once per briefing, and the worktree
protocol paragraph until #214's recipe deleted it mid-cycle. Its own diagnosis was
*operational instruction restated per dispatch because no mechanism carries it*. This is
the mechanism.

**What is claimed, and what is not.** A derived gate line, a flake list that cannot go
stale, and a protocol that reaches every dispatch whether or not the composing session's
memory is current. The token effect is **unmeasured** — #212 owns that measurement, and
#208's finding that briefings carrying a SHA correlate with *more* state reconstruction
rather than less is a warning against assuming its sign. Nothing here is a token
mechanism, and describing it as one is the error #206 corrected on `just watch`.

## What this composes, and what it refuses to compose

The **invariant half**: prior work already on `origin/main`, seat, worktree protocol, gate
line, flake lines, landing protocol, paste rule. The **variable half** — the task
statement, the scope boundary, the ground truth to read, and the reason for a non-default
seat — is the orchestrator's, is the actual work of the turn, and is emitted here as a
visible placeholder so that an unedited brief is obviously unfinished rather than
plausibly complete.

## Inlined or cited, and why each line is where it is

#208 measured that a pointer does not displace archaeology: an agent handed a reference
goes and reads the thing, and pays for the read. So the split is by *kind*, not by length.

- **Inlined** — the imperative, in the words that make it obeyable without a read: the two
  worktree calls, the gate command, the commit trailer, `just land` and its paste
  instruction, the flake test names, the `flake_quarantine` required response, the one
  sentence of the verdict paste rule, and the single-shot contract (#279 — a detached
  session has no second turn, and learning that by ending is exactly what it exists to
  prevent). An agent must be able to comply having read only the brief.
- **Cited** — the evidence and the reasoning behind each imperative: CLAUDE.md's Contract
  and failure-class table, #219's A/B, #105, the ADRs. That read is optional, and it is
  only wanted by an agent that means to argue with the rule rather than follow it.

Nothing from CLAUDE.md is copied wholesale. A second copy of a governing document is a
second home for a rule, and two homes can disagree.

## The gate line is derived, not chosen

CLAUDE.md's `just regress` row owes the full corpus to any change reaching an in-world
surface, and a briefing that names `just fast` for an in-world change is the defect this
table exists to prevent. The in-world list is **not restated here**: it is
`tools/gate.py`'s `IN_WORLD_PREFIXES`, which every other reader of that list also calls, so
no two of them can disagree about what "in-world" means.

Two signals, both read off the issue body:

1. **Named paths.** Every token with a separator and a non-empty next segment — so
   `addons/main/functions/fn_effectApply.sqf` is a surface and a bare `addons/` is the rule
   being quoted rather than a surface being claimed. #251's own body names all three
   in-world directories while touching none of them, which is why the bare form cannot
   count. Fenced blocks are **not** stripped, unlike `readiness.py`'s unit count: a code
   block in an issue is where the real paths usually are.
2. **The domain vocabulary**, read out of `CONTEXT.md`'s Language section at run time
   rather than copied — the project's own ubiquitous language, maintained in one place —
   plus `SQF` and `in-world`, which name the world without being domain nouns.

The table:

| Named paths | Domain vocabulary | Gate |
|---|---|---|
| at least one in-world | either | `just regress`, full corpus, no filter |
| none in-world | absent | `just fast` |
| none in-world | present | **undetermined** |
| none at all | either | **undetermined** |

Undetermined is a real outcome and it is loud. It never resolves to the cheaper gate,
because the direction of the error is not symmetric: over-gating costs Arma tier time,
under-gating lands an in-world change on a gate that never saw the world.

## What the table measured

Two populations, both from this repository, both vendored so the measurement re-runs under
`just unit` rather than being remembered.

- **Negatives** — `tests/fixtures/readiness-corpus/`, the twenty most recently dispatched
  issues at #241's landing. Every one landed touching **no** in-world path, so every
  `regress` verdict on that population is over-gating by construction.
- **Positives** — `tests/fixtures/gate-corpus/`, every issue in the last 400 commits whose
  landing touched an in-world prefix: 145, 149, 152, 156, 159, 162, 164, 165, 172, 174,
  175, 176, 188, 189. A complete sweep rather than a sample. Every `fast` verdict on that
  population is under-gating by construction — the defect the design names.

| Population | n | `regress` | `fast` | undetermined |
|---|---:|---:|---:|---:|
| positives (landed in-world) | 14 | 8 | **0** | 6 |
| negatives (landed elsewhere) | 20 | **0** | 17 | 3 |

Zero under-gating and zero over-gating; the whole error budget is spent on saying "I
cannot tell", which is the outcome the design asked for.

**Honestly stated limits.** The six undetermined positives are issues whose bodies name
only evidence paths — #172 and #174 to #176 are playtest ingests naming `docs/playtest/*.md`
while the work landed in `addons/` — so the first signal alone would have under-gated four
of fourteen, which is why the vocabulary signal exists at all. The vocabulary is
CONTEXT.md's list and was not tuned; a wider one carrying tier words (`Arma`, `engine`,
`probe`, `corpus`) was measured first and dropped, because it turned nine of the twenty
negatives undetermined without moving a single positive. That drop was a choice made after
seeing numbers, and #224's rule says to say so rather than present the final list as
pre-registered. The three undetermined negatives are two bodies naming no path at all and
one (#228) using the word `Command` in its ordinary English sense.

**What it cannot see.** A body's paths are what its author expected to touch, and an
implementation discovers more. This is a prediction; `just trial close-audit`'s corpus check
against the landed commit is the ground truth, and it runs later on the same list.

## The reserved-surface section, and why it is a section rather than a refusal

A dispatched session cannot write under `.claude/` on any lane: the harness classifies most
of that directory as sensitive and asks a permission for the rest, above the project
allowlist that grants `Write(.claude/skills/**)` and through the shell as well as the tool
call. Measured on #294 and tabulated in `docs/multi-provider-dispatch.md`; four human-approved
landings had already been blocked by it, each one costing a dispatch to rediscover.

So when the body names such a path, the brief says so and says what to do instead — author
the replacement text, let the orchestrator transcribe it. It is a section and not a refusal
because proposal-only work on those surfaces is legitimate and common: refusing the dispatch
would block the very route this section is pointing at. `.claude/worktrees/` is exempt, being
a location rather than a surface — every brief already quotes a worktree path.

## The flake lines are read, never remembered

An open flake is an issue whose **title** names a `test_` identifier and says it flakes, or
whose body opens a line with ``Class: `flake_quarantine` ``. Both of the two live ones
match on title. The read asks GitHub for open issues only, so a closed flake leaves the
next briefing by itself — which is the whole reason the list is fetched rather than typed.

A flake whose title says neither is missed, and the remedy is a title edit rather than a
looser rule: "mentions `flake_quarantine` anywhere" also matches every issue that merely
cites the class table, which on the live tracker is two issues out of four.

A miss is therefore not a finding about the tree, and the zero branch says so: it states
the filter and what to do on a red, never "None open. Any red is yours.", which asserted
an absence the filter never established while #341's deterministic red sat open — the
claim three briefs carried on one day (#360). `FLAKE_RESPONSE`'s tail carries the same
qualification for the same reason: "any other red is yours" promised the identical
absence one filter-miss away.

## What this does not do

It does not judge readiness. `readiness.assess` runs and its findings are reported in the
footer, because a ruling execution's criteria are prose to be transcribed rather than a
checklist to tick and an orchestrator should see that before writing the variable half —
but `just dispatch` is the rung that refuses, and a second refusing rung would be a second
place to disagree. It writes nothing to the tracker and edits no issue.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `dispatch.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes these importable.
import dispatch
import escalation
import handoff_fetch
import ledger
import readiness
import routing_policy

# The gate derivation lives in `gate`, the owner neither this module nor the dispatcher imports
# the other to reach (#323 review finding 3). Re-exported under the names this module has always
# surfaced so `brief.derive_gate` and every other `brief.<name>` call site — `test_brief.py`
# above all — read exactly as they did. F401 is the point here: these are the public surface,
# not local uses, and `gate` is reached by name rather than as a module so the local `gate`
# variable a brief composer holds (the `Gate` decision) is not shadowed.
from gate import (  # noqa: F401
    CONTEXT_TERM,
    ENGINE_WORDS,
    FAST_LINE,
    GATE_FAST,
    GATE_REGRESS,
    GATE_UNDETERMINED,
    PATH_TOKEN,
    REGRESS_LINE,
    UNDETERMINED_LINE,
    WHY_DOMAIN_LANGUAGE,
    WHY_FAST,
    WHY_NO_PATHS,
    WHY_NO_VOCABULARY,
    WHY_REGRESS,
    Gate,
    derive_gate,
    domain_mentions,
    domain_vocabulary,
    in_world,
    named_paths,
    read_vocabulary,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

REPO_SLUG: Final = "andrewesweet/arma-cti"

# The checkout this script is running out of, which is where CONTEXT.md and the worktrees
# live. A worktree's own copy is the right one to read: a session is governed by the tree
# it is working in (ADR-0042's stale-hook lesson, applied to the documents).
REPO: Final = Path(__file__).resolve().parents[1]

# `gh` is a network call, bounded like every other subprocess a seam makes (#144).
GH_TIMEOUT_S: Final = 30

# "I could not look" — not a result, and distinct from any composed brief. Spelled the
# same as `handoff_fetch.NO_RESULT` because it means the same thing there.
NO_RESULT: Final = 3

# What a dispatched session cannot write, measured rather than assumed (#294,
# `docs/multi-provider-dispatch.md`). One prefix, not four: `.claude/hooks/` and an invented
# `.claude/notes/` both refused as sensitive files, and `.claude/skills/` and
# `.claude/agents/` both asked a permission nobody is there to grant — so the directory is
# reserved and its named subdirectories are not a list to keep in step with.
RESERVED_PREFIXES: Final = (".claude/",)
# The one thing under `.claude/` that is not a reserved surface. Every worktree lives at
# `.claude/worktrees/issue-N`, so an issue quoting its own tree names a *location* whose
# files are ordinary repo paths — and the write that proved it is this brief's own doc edit.
RESERVED_EXEMPT: Final = (".claude/worktrees/",)


def reserved_surfaces(paths: Sequence[str]) -> tuple[str, ...]:
    """Name the paths a dispatched session cannot write, in the caller's order."""
    return tuple(
        path
        for path in paths
        if path.startswith(RESERVED_PREFIXES) and not path.startswith(RESERVED_EXEMPT)
    )


# ---------------------------------------------------- prior work already on origin/main

# The branch a landing has to be on to count as prior work. Spelled here rather than
# imported since #328: it used to come from the admission module's `AUDIT_REF`, and that
# module is now the trial harness, which this one has no other reason to load.
PRIOR_WORK_REF: Final = "origin/main"
PRIOR_WORK_RULE: Final = (
    "This report states what commit messages on `origin/main` reference; it does not decide whether"
)


class PriorWorkError(RuntimeError):
    """Git could not answer the prior-work question; absence must not be inferred."""


class PriorWork(NamedTuple):
    """One commit on `origin/main` whose message references the issue."""

    sha: str
    date: str
    subject: str

    def line(self) -> str:
        """Render the SHA, date and subject without interpreting the reference."""
        return f"- `{self.sha[:7]}` {self.date} — {self.subject}"


def prior_work(issue: int, repo: Path = REPO, ref: str = PRIOR_WORK_REF) -> tuple[PriorWork, ...]:
    """Read commits on `ref` whose messages reference `issue`, newest first.

    The parser is `ledger.referencing_commits`, which is also what admission's dispatch-
    window check reaches. A failed `git log` is not an empty history: like `just handoff`'s
    "I could not look" result, it refuses separately so a dispatcher cannot mistake an
    unavailable check for evidence that no work landed.
    """
    try:
        done = subprocess.run(  # noqa: S603
            ["git", "log", f"--format={ledger.COMMIT_REFERENCE_FORMAT}", ref],  # noqa: S607
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as missing:
        message = f"`git log` could not inspect {ref}: `git` is not on PATH"
        raise PriorWorkError(message) from missing
    if done.returncode != 0:
        detail = (done.stderr.strip() or f"exit {done.returncode}").splitlines()[0]
        message = f"`git log` could not inspect {ref}: {detail}"
        raise PriorWorkError(message)
    return tuple(
        PriorWork(commit.sha, commit.committed_at[:10], commit.subject)
        for commit in ledger.referencing_commits(done.stdout, issue)
    )


def render_prior_work(issue: int, work: Sequence[PriorWork]) -> str:
    """Render a prominent, non-judgmental report, or nothing when there are no hits."""
    if not work:
        return ""
    return "\n".join(
        (
            f"## PRIOR WORK ALREADY ON `origin/main` — READ BEFORE DISPATCH ({len(work)})",
            *(item.line() for item in work),
            (
                f"{PRIOR_WORK_RULE} #{issue} is done, superseded, or wants another lens."
                " That judgement belongs to the dispatching seat."
            ),
        )
    )


# ---------------------------------------------------------------------------- the handoff

# #212's study (fd9dc29) found the treatment arm empty: `tools/brief.py` never called
# `handoff_fetch`, so zero cold-start dispatched subagents had read a handoff in five days.
# #309 wires the fetch in and composes the result — copied byte-for-byte, never retyped —
# applying the verdict paste rule (#219) to a second artefact. #208 §6 asked the briefing to
# point at the handoff comment; #212 §3 measured that nothing pointed at one, and #290
# Finding 2 measured that the hand-written half of a brief is where a wrong ground truth
# entered. So this inlines the bytes `handoff_fetch.select` returns.

# The three states a brief's handoff can be in, kept as distinguishable as
# `handoff_fetch`'s three exit codes: a carried handoff, a cleanly determined absence, and a
# fetch that could not look. A `FetchError` must never collapse into "no handoff" — one says
# a successor has nothing to read, the other says nobody could look, and the brief must not
# let a reader mistake one for the other.
HANDOFF_CARRIED: Final = "carried"
HANDOFF_ABSENT: Final = "absent"
HANDOFF_UNAVAILABLE: Final = "unavailable"

# The cap is a named decision, not a discovered constant (#212 §8b). It reds both
# completion-report-shaped handoffs written to date (#287 at 9,404, #290 at 6,028) and sits
# above #208 (1,459), the one template handoff that honoured the document's ~1,500-character
# guidance. The study's §8b claim that it "passes all three template-shaped handoffs" does
# not hold against its own §1/§2 tables — #170 (2,442) and #221 (2,400) both exceed it — so
# this states the measured boundary honestly rather than the propagated claim. The check
# informs and does not block; whether it hardens into a refusal is the human's later call
# (#309), and under the corrected currency the write is the metered half (#212 §5).
HANDOFF_CAP: Final = 2000


class Handoff(NamedTuple):
    """The issue's newest handoff, or why the brief cannot say which it is."""

    state: str
    body: str = ""
    detail: str = ""


def fetch_handoff(issue: int, fetch: handoff_fetch.Fetch = handoff_fetch.fetch_comments) -> Handoff:
    """Return the issue's handoff as carried, cleanly absent, or could-not-look.

    A fetch failure is encoded as a state rather than raised: the handoff is one section of
    the brief, not the whole of it, so a handoff that cannot be looked for does not refuse
    the dispatch — it says so in its own section, the way the gate line carries `GATE
    UNDETERMINED` rather than defaulting to the cheaper answer.
    """
    try:
        carried = handoff_fetch.select(handoff_fetch.bodies(fetch(issue)))
    except handoff_fetch.FetchError as failure:
        return Handoff(HANDOFF_UNAVAILABLE, detail=str(failure))
    if carried is None:
        return Handoff(HANDOFF_ABSENT)
    return Handoff(HANDOFF_CARRIED, body=carried)


HANDOFF_HEADING: Final = "## Handoff — your first read, verbatim from `just handoff`"
HANDOFF_UNAVAILABLE_RULE: Final = (
    "A fetch failure is not an absence: this brief could not look, not confirm there is"
    " none. Read `just handoff {issue}` yourself before continuing."
)


def handoff_oversize(body: str, cap: int = HANDOFF_CAP) -> str:
    """Return the size-report line when a carried handoff exceeds the cap, else nothing."""
    if len(body) <= cap:
        return ""
    return (
        f"**Size: {len(body):,} characters — over the {cap:,}-character cap.** Under the"
        " corrected currency the write is the metered half (#212 §5). This check informs and"
        " does not block; whether it hardens into a refusal is the human's call (#309)."
    )


def render_handoff(issue: int, handoff: Handoff) -> list[str]:
    """Render the handoff section, or nothing when one is cleanly absent.

    Three states, three renderings, never collapsed: a carried handoff is composed verbatim;
    a cleanly determined absence renders nothing — it is a fresh dispatch, not a
    continuation with nothing to say; a fetch failure is a loud line, never an absence.
    """
    if handoff.state == HANDOFF_ABSENT:
        return []
    if handoff.state == HANDOFF_UNAVAILABLE:
        return [
            "## Handoff",
            f"**HANDOFF UNAVAILABLE — could not look.** {handoff.detail}",
            HANDOFF_UNAVAILABLE_RULE.format(issue=issue),
        ]
    lines = [HANDOFF_HEADING, "", handoff.body]
    oversize = handoff_oversize(handoff.body)
    if oversize:
        lines += ["", oversize]
    return lines


# ----------------------------------------------------------------------- the flake lines

# A title that names a test and says it flakes. Both live flakes match here.
FLAKE_TEST: Final = re.compile(r"\btest_[a-z0-9_]{4,}")
FLAKE_WORD: Final = re.compile(r"\bflak(?:e|es|ed|ing|y)\b", re.IGNORECASE)
# The other shape: a body whose first line types the issue with the class.
FLAKE_CLASS: Final = re.compile(r"^Class:\s*`?flake_quarantine`?", re.MULTILINE)
# Where the flaking test lives, so a briefing can name the module and not only the test.
TEST_MODULE: Final = re.compile(r"tests/[A-Za-z0-9_./\-]+\.py")


class Flake(NamedTuple):
    """One open flake, as a briefing names it."""

    issue: int
    test: str
    module: str

    def line(self) -> str:
        """Render the one line a briefing carries for this flake."""
        where = f"{self.module}::{self.test}" if self.module else self.test
        return f"- #{self.issue} `{where}`"


def is_flake(title: str, body: str) -> bool:
    """Whether this issue is an open flake quarantine record."""
    named = FLAKE_TEST.search(title)
    return bool(named and FLAKE_WORD.search(title)) or bool(FLAKE_CLASS.search(body))


def select_flakes(rows: Sequence[Mapping[str, object]]) -> tuple[Flake, ...]:
    """Pick the flakes out of a list of open issues, newest issue number last."""
    found: list[Flake] = []
    for row in rows:
        title = str(row.get("title") or "")
        body = str(row.get("body") or "")
        if not is_flake(title, body):
            continue
        named = FLAKE_TEST.search(title) or FLAKE_TEST.search(body)
        module = TEST_MODULE.search(body)
        found.append(
            Flake(
                issue=int(row.get("number") or 0),
                test=named.group(0) if named else "",
                module=module.group(0) if module else "",
            )
        )
    return tuple(sorted(found))


# ----------------------------------------------------------------------- the seat, cited

# What each seat is *for*, one reason per seat `tools/dispatch.py` registers. Keyed off that
# registry rather than beside it: `test_brief.py` asserts the two agree, so a seat cannot join
# the registry without a reason to state in a briefing.
#
# The source is ADR-0071's rulings as `SEATS` and `config/dispatch-routing-policy.json`
# actually implement them, never the Model roles mapping these lines used to quote (#329
# review round 1, claim 1). That mapping was ruling 2's own casualty, and every one of these
# lines outlived it: a brief went on telling the `fable` seat it owned "process docs" that
# routing class 2 refuses it, and the `review` seat that "a review lands nothing (ADR-0061
# decision 3)" after ruling 1 rescinded that decision. A brief is the one surface every
# dispatched agent reads first, and nothing here is asserted against the code, so the stale
# instruction reached every dispatch in silence.
SEAT_REASON: Final[dict[str, str]] = {
    "planner": "ADR-0071 ruling 2: works out what to do; neither gates nor lands.",
    "implementer": (
        "ADR-0071 ruling 2: carries the work out, runs its own gate and lands it — a profile "
        "that cannot run its own gate is not an implementer."
    ),
    "recon": (
        "ADR-0071 ruling 2: read-only search, triage sweeps and state checks. A recon claim "
        "that decides a routing choice is cited; no gate reads recon output."
    ),
    "retro": (
        "ADR-0071 ruling 3 as amended by A4: finds, researches and files backlog items; "
        "lands nothing but its own journal entry in `docs/process-log.md`, which is "
        "reviewed under ruling 4 like any other landing."
    ),
    "review": (
        "ADR-0071 ruling 4: judges work another profile produced, never its own. Resolution "
        "excludes that profile and the seat forces a read-only permission mode "
        "(`reviews` and `permission_mode` in `tools/dispatch.py`'s `SEATS`)."
    ),
    "fable": (
        "The #181 shape: a diagnosis whose plausible wrong fix would also have gone green, "
        "where no mechanical gate catches the wrong answer. Routing class 4 declares that "
        "shape and routes it to `planner`; `config/escalation-conditions.json`'s fourth "
        "condition is what orders the transfer here (#329 review round 2, F6 — the class "
        "alone does not route to this seat)."
    ),
    "orchestrator": (
        "The standing dispatch loop, and ADR-0071 ruling 1's one surviving provenance rule — "
        "`claude_only` in `SEATS`, provisional until a tested alternative exists."
    ),
}

DEFAULT_SEAT: Final = "implementer"


class Seat(NamedTuple):
    """Which seat the brief names, and whether the orchestrator still owes a reason."""

    name: str
    reason: str
    owes_reason: bool
    # The profile whose work a review dispatch judges (#322, ADR-0071 ruling 4). Empty on
    # every other seat, and empty on a review the composer was not told about — which is a
    # placeholder in the rendered brief rather than a silence, because a review dispatched
    # without it meets `review_subject_unknown` at dispatch time instead.
    reviewing: str = ""

    @property
    def reviews(self) -> bool:
        """Whether the dispatcher's registry says this seat reviews another profile's work."""
        registered = dispatch.SEATS.get(self.name)
        return registered is not None and registered.reviews

    # The predicate both briefs branch on (#421). The composed brief branched its three
    # sections on `reviews` while the default brief branched its gate line on the forced
    # `permission_mode`, so a fix landed on one arm and missed the other twice in a row
    # (#360's qualified flake wording reached only the branch that touched it) — and the
    # round that named this predicate left the default brief rederiving the column beside
    # it, which is why the derivation now lives on the registry row itself
    # (`dispatch.Seat.judgement_only`) and this property delegates rather than rederives:
    # one home, and neither brief path can disagree with the other. A seat that forces
    # `plan` writes nothing, so it is told to run no gate, commit or landing — `review`
    # because it judges, `recon` because it reads. What still follows `reviews` is the
    # content *within* that arm: only a reviewer is handed the paste contract.
    @property
    def judgement_only(self) -> bool:
        """Whether the registry forces this seat read-only (`Seat.judgement_only` there)."""
        registered = dispatch.SEATS.get(self.name)
        return registered is not None and registered.judgement_only

    # #345's predicate, in the same shape as the one above it: the derivation lives on
    # the registry row (`dispatch.Seat.lands`) and this delegates rather than rederives,
    # so the composed brief cannot disagree with the table. A seat absent from the
    # registry lands nothing — the arm that refuses the close, which is the safe side
    # for a name the parser should never have accepted.
    @property
    def lands(self) -> bool:
        """Whether the registry names this seat ADR-0071 ruling 4's lander."""
        registered = dispatch.SEATS.get(self.name)
        # `is True`, not truthiness: the registry column is `bool | None`, `None` the
        # undecided state `dispatch.refuse_undecided_lands` refuses, so this names the
        # one decided answer that composes a lander's brief.
        return registered is not None and registered.lands is True


def derive_seat(override: str, reviewing: str = "") -> Seat:
    """Name the seat and quote the mapping's reason, or ask for the orchestrator's.

    A non-default seat is a judgement the design leaves with the orchestrator, so the
    mapping's line is printed *and* a placeholder is opened beside it: the mapping says
    what the seat is for, and only the orchestrator knows why this issue wants it.

    The reviewed profile is carried through unvalidated. `tools/dispatch.py` checks it
    against the registry and against the issue's own dispatch records, and a second, weaker
    copy of that check here would be a place for the two to disagree.
    """
    name = override or DEFAULT_SEAT
    return Seat(
        name,
        SEAT_REASON.get(name, ""),
        owes_reason=bool(override) and name != DEFAULT_SEAT,
        reviewing=reviewing,
    )


# ------------------------------------------------------------- the worktree and its base


class Tree(NamedTuple):
    """The worktree a dispatch is assigned, its base SHA, and where the SHA came from."""

    path: Path
    base: str
    source: str


def git(*args: str, cwd: Path) -> str:
    """Run one git command and return its stdout, or the empty string if git refused."""
    # S603/S607: fixed literals plus paths this tool computed, and `git` resolves off PATH
    # on purpose — the checkout's toolchain is the caller's.
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def resolve_tree(issue: int, override: str = "", repo: Path = REPO) -> Tree:
    """Name the worktree and its base SHA, saying which of three sources answered.

    `just worktree add` prints both, and it is the authority; this reads the same values
    where it can and otherwise names the source honestly rather than inventing a SHA.

    The path hangs off the **main checkout**, not off this script's own tree, and
    `dispatch.main_checkout` is what answers so the two tools cannot disagree. Composing a
    brief from inside a worktree otherwise names `<this worktree>/.claude/worktrees/…`,
    which is nowhere — the accident `just dispatch` already carries a comment about, and
    the one this tool made on its own first live run.
    """
    path = dispatch.main_checkout(repo) / ".claude" / "worktrees" / f"issue-{issue}"
    if override:
        return Tree(path, override, "given")
    if path.is_dir():
        head = git("rev-parse", "--short", "HEAD", cwd=path)
        if head:
            return Tree(path, head, "worktree")
    base = git("rev-parse", "--short", "origin/main", cwd=repo)
    if base:
        return Tree(path, base, "origin/main")
    return Tree(path, "", "unresolved")


# --------------------------------------------------------------------------- the reading


class FetchError(RuntimeError):
    """`gh` could not be run, refused the request, or answered unreadably."""


def _gh(args: Sequence[str]) -> str:
    """Run one `gh` call and return its stdout, or raise `FetchError`."""
    try:
        done = subprocess.run(  # noqa: S603
            ["gh", *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=GH_TIMEOUT_S,
        )
    except FileNotFoundError as missing:
        message = "`gh` is not on PATH, so no issue could be read."
        raise FetchError(message) from missing
    except subprocess.TimeoutExpired as slow:
        message = f"`gh` did not answer within {GH_TIMEOUT_S}s."
        raise FetchError(message) from slow
    if done.returncode != 0:
        detail = (done.stderr.strip() or f"exit {done.returncode}").splitlines()[0]
        raise FetchError(detail)
    return done.stdout


def fetch_issue(issue: int, repo: str = REPO_SLUG) -> dict[str, object]:
    """Read one issue's number, title, body and state, or raise `FetchError`.

    An issue that does not exist and a `gh` that cannot be reached both raise, because a
    brief composed around neither is the silent-empty-output shape #168 and #183 named.
    """
    payload = _gh(
        ["issue", "view", str(issue), "--repo", repo, "--json", "number,title,body,state"]
    )
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, ValueError) as broken:
        message = f"`gh` answered with something that is not JSON: {broken}"
        raise FetchError(message) from broken
    if not isinstance(document, dict) or not document.get("title"):
        message = f"`gh` returned no readable issue for #{issue}."
        raise FetchError(message)
    return document


def fetch_open_issues(repo: str = REPO_SLUG) -> list[dict[str, object]]:
    """Read every open issue's number, title and body, or raise `FetchError`.

    `--state open` is the whole of criterion 2's mechanism: a closed flake is never in the
    answer, so it leaves the next briefing without anybody remembering to remove it.
    """
    payload = _gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,title,body",
        ]
    )
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, ValueError) as broken:
        message = f"`gh` answered with something that is not JSON: {broken}"
        raise FetchError(message) from broken
    if not isinstance(document, list):
        message = "`gh issue list` returned nothing this could parse."
        raise FetchError(message)
    return [row for row in document if isinstance(row, dict)]


# ------------------------------------------------------------------------- the rendering

# The one string that makes an unedited brief obviously unfinished (criterion 5). Spelled
# once so a test can assert on it and a reader can grep for it.
PLACEHOLDER: Final = "TO BE WRITTEN BY THE ORCHESTRATOR"


def _placeholder(what: str) -> str:
    """Render one placeholder block for a part of the variable half."""
    return f"> **{PLACEHOLDER}.** {what}"


TASK_PLACEHOLDER: Final = (
    "The task statement, the scope boundary, and the ground truth to read."
    " `just brief` composes none of it, and an unedited brief is not a brief."
)
SEAT_PLACEHOLDER: Final = "Why this issue wants a non-default seat."
# ADR-0071 ruling 4 (#322). A review seat's briefing has to carry the relationship the
# dispatch itself now requires, or the orchestrator meets the refusal at dispatch time
# instead of the instruction at composition time.
REVIEW_SUBJECT_RULE: Final = (
    "Dispatch this seat with `--reviewing <profile>`, the profile whose work is under review."
    " Resolution returns neither that profile nor any other one the issue's own dispatch"
    " records place on the work, prefers an entry on a different lane among what is left, and"
    " the seat forces a read-only permission mode over whatever is passed. A declaration a"
    " complete read of those records contradicts is refused `review_subject_contradicted`;"
    " where they cannot answer, the route is recorded unchecked rather than passed off as"
    " checked (ADR-0071 ruling 4)."
)
REVIEW_SUBJECT_PLACEHOLDER: Final = (
    "Which profile's work this review judges. Compose with `--reviewing <profile>` and pass"
    " the same one to `just dispatch`; a review that declares none is refused."
)
FLAKE_RESPONSE: Final = (
    "`flake_quarantine`: do not act. If one of those exact tests is your only red, quote its"
    " issue number and re-run once; a second red, or a red in any other test, is yours unless"
    " an open issue the flake filter missed names it — check the tracker before owning a red"
    " (#360)."
)
# The zero branch states the filter, never a clean tree: "None open. Any red is yours."
# claimed an absence the name filter never established, and three briefs carried it on one
# day while #341's deterministic red sat open (#360). FLAKE_RESPONSE's tail carries the
# same qualification because "any other red is yours" made the identical claim one
# filter-miss away.
FLAKE_NONE: Final = (
    "None matched the flake filter. The filter is name-based — a title naming a `test_`"
    " that says it flakes, or a body opening `Class: flake_quarantine` — so an open issue"
    " whose red shows in your gate can sit outside it. Before treating a red as yours,"
    " check the tracker for an open issue naming your failing test."
)
# The review seat's halves of the same three sections. The human ruled on 2026-08-14 (#353,
# reversing the 2026-08-13 ruling in that issue's body) that a reviewer is passed the
# implementer's gate report rather than running the gate itself — "reviewer must not trigger
# tests themselves". Until that ruling every review brief asked for a gate run and every
# review spent effort explaining why it could not, which produced nothing except the honest
# sentence; these sections stop asking. The mutation question the issue left open is decided
# by the same ruling, so the sampled-or-exhaustive distinction (#344: an exhaustive 91% hid
# behind a reported 100%, because `just mutation` plants at most twenty of a module's
# candidates) is a thing the *implementer* states in the paste, not a thing the reviewer
# measures.
#
# **The clarification of 2026-08-20 (#449) narrows what that ruling ever said**, and these
# strings carry the narrower rule. It was transcribed here as "this seat runs no gate and
# triggers no test", which reads as *the seat runs nothing* — and the landing rule below
# then spelled out one consequence nobody had ruled, "do not file an issue or a comment".
# The human's words: "#393 ruling was intended to prevent reviewers from re-running tests.
# They should be passed test reports to examine, not rerun them (so we avoid the significant
# wall time cost). They can of course land review-specific gates and post their own
# findings." So the bar is **re-running the implementer's suite**, its stated reason is wall
# time, and posting is permitted. The cost of the wider transcription is measured: in the
# session of 2026-08-19/20 fifteen verdicts were relayed by hand through the orchestrator,
# each a plan read, an extraction and a `gh issue comment`, because every review had been
# told its findings were not its to file.
#
# #421 finding 2 tightens what the paste owes: the counts were never required, and the
# sampled-or-exhaustive classification was owed only "where a kill rate is quoted" — so the
# brief that carried #353's own review demonstrated the gap, arriving with no current-SHA
# mutation output and no sampled-versus-exhaustive statement. A reviewer told the gate is
# not theirs and given no numbers has been disarmed rather than redirected: the counts and
# the classification are required unconditionally. That requirement is untouched by #449.
MUTATION_SAMPLING_PASTE_RULE: Final = (
    "`just mutation`'s own `mutation smoke: run was sampled` (fewer than every planted"
    " candidate reached a verdict) or `mutation smoke: run was exhaustive` (every planted"
    " candidate reached a verdict) line verbatim"
)
REVIEW_GATE_RULE: Final = (
    "You re-run none of the implementer's gate. It has already run; its wall time is the"
    " cost this rule exists to avoid, and you are passed its report instead (human ruling"
    " 2026-08-14 on #353, as clarified 2026-08-20 on #449). The implementer's pasted gate"
    " output on the issue thread is your gate record: it must carry `just check`,"
    " `just unit` and `just mutation` with their result counts, including "
    f"{MUTATION_SAMPLING_PASTE_RULE} (#344) — unconditionally, not only where a kill rate"
    " is quoted."
    " A paste that is absent, thinner than that, silent on counts, or silent on"
    " sampled-or-exhaustive is a finding — report it as an observation rather than running"
    " the gate yourself (#421)."
)
REVIEW_FLAKE_RESPONSE: Final = (
    "You re-run none of these: a flake named in the implementer's paste is context for"
    " reading it, never a red of yours to retry (human ruling 2026-08-14 on #353, as"
    " clarified 2026-08-20 on #449)."
)
# The posting half is written as an instruction to *attempt and report*, not as a promise
# that the call will land. The seat's containment is a forced read-only permission mode
# (`dispatch.SEATS["review"]`, where #449's mechanism decision and the two runs that measure
# it are recorded): both runner families were observed posting from `plan` mode on
# 2026-08-20, so this asks the reviewer for nothing unproven. It stays an attempt rather
# than a promise because two runs are an observation and not an invariant, and a family,
# mode or runner version that does refuse should be recorded the first time it happens
# rather than assumed away. The fifteen relayed verdicts of 2026-08-19/20 measured the
# instruction rather than the mechanism, because none of those reviews was permitted to try.
REVIEW_LANDING_RULE: Final = (
    "A review lands nothing: do not commit, do not push, do not run `just land`, and edit no"
    " file — ADR-0071 ruling 4's never-alone invariant, which this ruling leaves untouched."
    " Filing is not landing. Post your findings on the issue thread yourself with"
    " `gh issue comment`; if that tool call is refused, say so in your report and let your"
    " final message stand as the record for the orchestrator to relay (human ruling"
    " 2026-08-20, #449; `docs/review-dispatch.md`)."
)
# The same three sections for a forced-read-only seat that is not the reviewer (#421
# criterion 1). `recon` is that seat today: the same containment #407 forced on it, a
# different job — it reads the repository and the thread rather than judging an
# implementer's paste, so it gets the prohibitions without the paste contract.
READONLY_GATE_RULE: Final = (
    "This seat runs no gate and triggers no test — read-only by construction (ADR-0071"
    " ruling 2; the forced `permission_mode` column, #407). Read the repository and the"
    " issue thread; report what you find, never an edit."
)
# Cited to `recon`'s own ground rather than to #353. The 2026-08-14 ruling is about a
# reviewer re-running an implementer's suite, and #449 narrowed it to exactly that; a seat
# that judges no implementer's work never had that rule to inherit. `recon` triggers no test
# because ADR-0071 ruling 2 makes it read-only, which is a different reason for the same
# sentence, and a mis-citation is how a rule ends up wider than the ruling behind it.
READONLY_FLAKE_RESPONSE: Final = (
    "You re-run none of these: a read-only seat triggers no test (ADR-0071 ruling 2; the"
    " forced `permission_mode` column, #407). They are context for what you read."
)
READONLY_LANDING_RULE: Final = (
    "A read-only seat lands nothing. Do not commit, do not push, do not run `just land`,"
    " do not file an issue or a comment; your entire output is your final message"
    " (ADR-0071 ruling 2)."
)
# #345, re-derived after #439. The Landing section's close sentence used to be the
# only mechanism that closed an issue, and before ADR-0071 telling every seat to run
# it was right. Ruling 4 then assigned the close to nobody — it defines proposer,
# reviewer and lander and allows the proposer to land, the correction #345's own first
# follow-up records — so the sentence stayed every seat's standing order, and #323's
# seat closed its issue on the composed line alone, before any review existed. #439
# made the close the landing rung's act instead: `just land` itself performs it on
# the success path. So the sentence is not softened but replaced: a seat obeying the
# old wording walks a second mechanism onto ground the rung already covered and finds
# the issue closed. What survives of it is the audit, moved to the thread report
# below, because #449's review reads exactly that paste as its gate record — the
# audit was never the close's private form, it is the record both the review and the
# rung's close rest on.
RUNG_CLOSE_RULE: Final = (
    "`just land` closes #{issue} itself, on its success path and nowhere else (#439):"
    " do not close the issue by hand and do not close it early. The landing's own"
    " `issue_closed=` line is part of the verbatim paste; where it reads"
    " `issue_closed=no reason=…` the work is already on `origin/main` and the tracker"
    " state is bookkeeping — report the line, never retry the close. One reason is"
    " different (#461): `reason=audit_absent` means the thread carried no criterion"
    " audit, so post it and close by hand with the criterion comment"
    " (docs/agents/issue-tracker.md) — a re-run has nothing left to land and will not"
    " close."
)
THREAD_AUDIT_RULE: Final = (
    "Post on #{issue}'s thread a criterion-by-criterion audit quoting the gate's output"
    " — `just check`, `just unit`, `just mutation`, each with its result counts —"
    f" including {MUTATION_SAMPLING_PASTE_RULE} (#344, #421:"
    " unconditionally, never only where a kill rate is quoted). That paste is the"
    " review's gate record (#449), so it is owed before the branch is handed over, not"
    " only once the landing has closed the issue — and the landing's close reads its"
    " presence on the thread (#461), so a landing without it leaves the issue open."
)
# The writable arm's other half (#345): a seat that may write but is not the lander.
# `planner` is today's clearest row — ruling 2's "neither gates nor lands" — with
# `fable` and the `orchestrator` beside it on the same ground: no ruling names them
# as any route's lander. The section states what the seat's role permits rather than
# a softened implementer's: committing and reporting are its acts, and both the
# landing and the close belong to the rung that performs them.
NONLANDING_LANDING_RULE: Final = (
    "This seat is not the lander (ADR-0071 ruling 4): do not run `just land`, and leave"
    " #{issue} open — never close it. Commit your work and report it; the review that"
    " gates the landing has not happened when this seat finishes, so whether the work"
    " reached `main` is not this seat's to know. The issue closes with the landing"
    " itself — `just land`'s own success path (#439) — and the one hand close is the"
    " lander's own recovery, where that rung withheld for `reason=audit_absent`"
    " (#461); it is never this seat's."
)
PASTE_RULE: Final = (
    "Quote `just verdict`'s rendered body verbatim; never retype the SHA or the evidence"
    " path (CLAUDE.md; #219's A/B — all four failures were retyping)."
)
# ADR-0071 ruling 4 as amended by A7 (human ruling of 2026-08-14 on #334). Inlined
# rather than cited because it is an imperative: an implementer must be able to
# close its findings having read only the brief, and the fourth route is the one a
# brief never mentioned — `just land`'s `finding_unadjudicated` refusal names all
# four, at the point where re-reading this document costs another round.
ADJUDICATION_RULE: Final = (
    "A review finding above Low closes through exactly one route before `just land`"
    " accepts the branch: `fixed`; `arbiter_upheld` or `arbiter_dismissed`; or"
    " `accepted_and_filed` — Medium or below, harm conditional on named work outside"
    " the diff, filed as an issue on the originating item first. Each route is"
    " recorded by `just review-loop adjudicate` (ADR-0071 ruling 4; the fourth route"
    " is the human ruling of 2026-08-14 on #334)."
)
# The human's ruling of 2026-08-20 (#460, recorded by ADR-0077). Spelled once and read by
# every surface that states it: `AGENTS.md` carries this text, `docs/review-dispatch.md`
# carries it twice, and both arms of the composed brief render it. Three hand-typed copies
# is exactly #445's finding 3 — the sampling rule was built here, retyped in the document
# and retyped again in the template, so changing one redded one test while the others went
# on asking for a line that no longer existed. The rule reaches the implementer's brief and
# not only the review contract for the other half of that issue's lesson: a rule only
# reviewers know produces findings, and #445's own fragment was a revision behind its code.
CHANGELOG_CLAIM_RULE: Final = (
    "A `changelog.d/` fragment is reviewed as a claim, not as prose: every sentence is checked"
    " against the diff exactly as a code comment is, and a fragment claiming more than landed"
    " blocks the landing rather than being filed as a follow-up. `scriv collect` folds a"
    " fragment verbatim into `CHANGELOG.md` at the next `cog bump`, and `just check`'s"
    " fragment leg is content-blind — it verifies that a fragment exists, never that it is"
    " true (#429) — so a false sentence there is the one claim in this repository that ships"
    " without ever being checked again (human ruling 2026-08-20, #460)."
)
RESERVED_RULE: Final = (
    "You cannot write these, and neither can any dispatched session on any lane: `.claude/`"
    " is reserved by the harness above the project allowlist, through the tool call and"
    " through the shell alike. Do not attempt the edit and do not route around it. Author"
    " the exact replacement text in your close comment; the orchestrator transcribes it."
    " These surfaces are human sign-off gated in any case (CLAUDE.md; measured on #294,"
    " `docs/multi-provider-dispatch.md`)."
)
ESCALATION_RULE: Final = (
    "A transferring-escalation condition has fired — the task moves to a higher profile only on a"
    " named condition, never by an agent's judgement in the moment (ADR-0071 ruling 5). Each"
    " emission below names the condition, the recorded facts that fired it, and the remedy; act"
    " on it before landing. A condition that has not fired emits nothing, so a brief without this"
    " section has no escalation due."
)


class Briefing(NamedTuple):
    """Everything the invariant half is composed from, gathered before anything is rendered."""

    issue: int
    title: str
    gate: Gate
    flakes: tuple[Flake, ...]
    seat: Seat
    tree: Tree
    assessment: readiness.Assessment
    # The paths this issue names that no dispatched session can write. Defaulted so that a
    # caller composing a brief about anything else says nothing about reserved surfaces,
    # which is the whole point: the section appears only where it applies.
    reserved: tuple[str, ...] = ()
    # The other silent-default section: hits are made prominent; no hits add no heading.
    prior_work: tuple[PriorWork, ...] = ()
    # The handoff the issue carries, or why the brief cannot say. Defaulted to a clean
    # absence so a brief composed about anything else opens no handoff section — the section
    # appears only where one applies, like prior work and reserved surfaces.
    handoff: Handoff = Handoff(HANDOFF_ABSENT)
    # A transferring-escalation condition that has fired for this item, an input that could not be
    # read, or nothing. Defaulted so a brief about an item with no condition due opens no
    # escalation section — the section appears only where one applies, like reserved surfaces and
    # the handoff (ADR-0071 ruling 5, #325). The default is the confident silence, `NoFiring`, the
    # one outcome that renders no section; `Firing` renders the firing and `Unreadable` renders the
    # gap, each under its own heading.
    escalation: escalation.Evaluation = escalation.NoFiring()


def escalation_for(body: str, seat_name: str, repo: Path) -> escalation.Evaluation:
    """Decide the transferring-escalation conditions for an item from what the brief can read.

    The escalation tool decides from facts in a `Context`; this assembles that context from the
    data a composition-time read actually has. `routing_class` is recorded — derived lane-blind
    from the body through `routing_policy.classify_issue` — so condition 4 fires for a #181-shape
    item for real. `review_rounds`, `finding_above_low` and `attempts` are `None` here, and the
    reason is the composition point rather than a missing mechanism: #333 landed the review loop,
    so rounds and findings **are** recorded — in the per-issue state under `~/.arma-cti/review/`,
    which `review_loop._cmd_escalate` reads and evaluates conditions 1 and 2 from — but a brief is
    composed at dispatch, before any loop for that issue exists. Conditions 1, 2 and 3 therefore
    stay silent in a *brief*, and fire where their facts live. The arbiter condition 1 would name
    is resolved here from **this brief's own seat**'s escalation head and supplied anyway, so the
    briefing states who the table names; the escalation path resolves the arbiter for real through
    `arbiter.resolve_dispatchable`, which is a walk with exclusions and not this field.

    That seat, and not the `implementer` row, is what ADR-0071 ruling 4 means by "the implementing
    seat's escalation entry" as amendment A1 (#361) leaves it. Reading `IMPLEMENTER_ESCALATION[0]`
    — which this did until #361 — emitted `codex-sol-high` as the arbiter for a retro brief, whose
    tabled arbiter is `opus-max`, and made every other row's entry unreachable. A seat with no
    entry resolves to `None` and condition 1 stays silent, which is the struck blanket fallback's
    accepted consequence rather than a gap: it must not fire naming an arbiter nobody chose.

    Two inputs can fail to read — the routing policy, which alone decides condition 4's class,
    and the condition table — and each is the third state, not silence: an unreadable policy is
    not "this item has no class" and an unreadable table is not "nothing fired". They are combined
    with the evaluation by `escalation.with_unreadable`, which keeps them independent of whether a
    condition fired: an unreadable input cannot turn a confident `NoFiring` honest (so it becomes
    `Unreadable`), but neither may it displace a `Firing` — a class-4 item whose policy cannot be
    read while condition 1 fires on recorded review facts is a real state once those facts are
    wired, and its emission reaches the agent with the gap named after it, not in its place
    (#325 round 3, claim 3; the #323 distinction, #347).
    """
    policy_read = routing_policy.read_policy(repo / routing_policy.POLICY_RELATIVE)
    routing_class: int | None = None
    if policy_read.policy is not None:
        match = routing_policy.classify_issue(policy_read.policy, body)
        if match is not None:
            routing_class = match.rule.id
    conditions_read = escalation.read_conditions(repo / escalation.CONDITIONS_RELATIVE)
    context = escalation.Context(
        item=escalation.ItemState(routing_class=routing_class),
        prior=None,
        arbiter=dispatch.escalation_head(seat_name),
    )
    outcome = escalation.evaluate(conditions_read, context)
    # The table's own unreadable reason is already inside `outcome` (evaluate returns Unreadable
    # for it). The policy is a separate input the conditions need, combined here so a firing
    # survives it and a no-firing does not claim the confident silence (#325 round 3, claim 3).
    return escalation.with_unreadable(outcome, (policy_read.error,) if policy_read.error else ())


def _escalation_lines(outcome: escalation.Evaluation) -> list[str]:
    """Return the escalation section for an outcome, or nothing for the confident silence.

    Narrows on the `kind` value, never `isinstance`: `load_tool` re-execs the escalation module, so
    the outcome a brief carries can be an instance of a different copy's class than the one this
    copy holds, and `isinstance` is False across them. A `kind` read off the object returns the
    value the creating copy wrote, so it agrees across copies where identity does not (#325 round 3,
    claim 1). A firing that also carries an unreadable input renders the fired condition first and
    the gap after it — never the gap in the firing's place (#325 round 3, claim 3).

    The confident silence is matched, never fallen through to. This renderer is the last place a
    distinction can be lost before a human reads the brief, so an `else` that rendered nothing for
    an unrecognised kind would be this branch's own failure shape one representation later: an
    outcome that is not the confident silence, presented as it. An unknown kind raises.
    """
    if outcome.kind == escalation.FIRING:
        lines = ["", "## Escalation", ESCALATION_RULE, *escalation.render(outcome.emissions)]
        if outcome.unreadable:
            lines += escalation.render_unreadable(outcome.unreadable)
        return lines
    if outcome.kind == escalation.UNREADABLE:
        # A distinct heading, never the "has fired" preamble above: an unreadable input is the
        # third state, not a firing and not the silence of nothing fired (#325 round 2, claim 1).
        return ["", "## Escalation", *escalation.render_unreadable(outcome.reasons)]
    if outcome.kind == escalation.NO_FIRING:
        # The confident silence, the only outcome a brief renders nothing for.
        return []
    raise escalation.EscalationError(escalation.unknown_kind_error(outcome.kind))


def _worktree_lines(issue: int, seat: Seat, tree: Tree) -> list[str]:
    """Render the worktree section: the assignment, and whose the two commands are.

    A forced-read-only seat cannot run either call — `just worktree add` writes a tree,
    `just worktree done` verifies and removes one — so commanding them contradicts the
    same brief's "no checkout, no mutation". Dispatch already requires the worktree to
    exist before launch (`assert_worktree`), so for these seats the section names the
    assignment and says the commands are not theirs (#421 finding 3).
    """
    work_only = "Work only there. Files you did not write mean stop and report, never reset (#105)."
    if seat.judgement_only:
        return [
            "",
            "## Worktree",
            (
                f"`{tree.path}`, base `{tree.base or 'unresolved'}` ({tree.source})."
                " Dispatch verified this tree before launch — run no worktree command:"
                " no `just worktree add`, no `just worktree done` (#421)."
            ),
            work_only,
        ]
    return [
        "",
        "## Worktree",
        (
            f"`just worktree add issue-{issue}` → `{tree.path}`,"
            f" base `{tree.base or 'printed by that call'}` ({tree.source})."
        ),
        work_only,
        f"Finish with `just worktree done issue-{issue}`.",
    ]


def _protocol_lines(briefing: Briefing) -> list[str]:
    """Render the gate, flake and landing sections for whichever arm the seat is in.

    The three sections are the implementer's until the registry forces the seat read-only:
    a forced-`plan` seat runs no gate, retries no flake and lands nothing — the review by
    the human ruling of 2026-08-14 (#353) as clarified on 2026-08-20 (#449), every other
    such seat (`recon`, #407) by the same construction — so the gate ask, the re-run
    instruction and the landing protocol would each demand something the seat is forbidden
    to do. What the read-only arm does *not* say is that the seat may not file: #449 puts
    posting its own findings back inside the reviewer's contract, and only landing,
    editing and re-running the implementer's gate stay out. The arm follows
    `Seat.judgement_only`, the same predicate the default brief branches on and #339
    derived surfaces from, because `reviews` reached only the reviewer and left `recon`
    carrying the implementer's asks (#421): one predicate, both paths. The derived gate is still
    composed — these seats meet the same headings and never a silence — and within the arm
    the paste contract is the reviewer's alone, because `recon` judges no implementer's
    work.
    `CHANGELOG_CLAIM_RULE` reaches both arms: the implementer writes the fragment and the
    reviewer judges it, so each meets it where it works (#460). `recon` writes no fragment
    and judges none, so it is the one seat the rule is silent for.

    The writable arm splits once more, on `Seat.lands` (#345): a seat the registry does
    not name as ruling 4's lander keeps the gate and the commit instruction but is left
    off the landing protocol, and neither half carries a close instruction, because
    `just land` closes the issue itself on its success path (#439) — a composed order
    to close would be a second mechanism for an act the rung had already performed.
    """
    issue, seat, gate, flakes = briefing.issue, briefing.seat, briefing.gate, briefing.flakes
    if seat.judgement_only:
        lines = [
            "",
            "## Gate: none — this seat runs none",
            REVIEW_GATE_RULE if seat.reviews else READONLY_GATE_RULE,
            *([CHANGELOG_CLAIM_RULE] if seat.reviews else []),
            "",
            f"## Open flakes ({len(flakes)}, read live at composition)",
        ]
        if flakes:
            lines += [flake.line() for flake in flakes]
            lines.append(REVIEW_FLAKE_RESPONSE if seat.reviews else READONLY_FLAKE_RESPONSE)
        else:
            lines.append("None open.")
        return [
            *lines,
            "",
            "## Landing: none — this seat lands nothing",
            REVIEW_LANDING_RULE if seat.reviews else READONLY_LANDING_RULE,
        ]
    lines = [
        "",
        f"## Gate: {gate.line}",
        *gate.because,
        "",
        f"## Open flakes ({len(flakes)}, read live at composition)",
    ]
    if flakes:
        lines += [flake.line() for flake in flakes]
        lines.append(FLAKE_RESPONSE)
    else:
        lines.append(FLAKE_NONE)
    # The writable arm's own split (#345): only the registry's lander is handed the
    # landing protocol, and no seat at all is handed the close — that is `just land`'s
    # own act on its success path (#439), so the branch that remains is over whether
    # the seat runs the rung, never over who closes. The commit line stays in both
    # halves: a non-lander's commits reach `main` through the lander, and Conventional
    # Commits and the `refs` trailer bind them the same. `CHANGELOG_CLAIM_RULE` rides
    # beside it for the same reason — a non-lander's commits carry fragments, so the
    # claim rule binds them exactly as the lander's do (#460).
    if not seat.lands:
        return [
            *lines,
            "",
            "## Landing: none — this seat is not the lander",
            f"Conventional Commits, `refs #{issue}`, commit early.",
            CHANGELOG_CLAIM_RULE,
            NONLANDING_LANDING_RULE.format(issue=issue),
        ]
    return [
        *lines,
        "",
        "## Landing",
        f"Conventional Commits, `refs #{issue}`, commit early.",
        CHANGELOG_CLAIM_RULE,
        "Land via `just land` and paste its output verbatim — never retype it.",
        ADJUDICATION_RULE,
        RUNG_CLOSE_RULE.format(issue=issue),
        THREAD_AUDIT_RULE.format(issue=issue),
    ]


def compose(briefing: Briefing) -> str:
    """Render the invariant half, with the variable half left as visible placeholders."""
    issue, seat, gate = briefing.issue, briefing.seat, briefing.gate
    lines = [
        f"# Dispatch brief — #{issue}: {briefing.title}",
    ]
    prior = render_prior_work(issue, briefing.prior_work)
    if prior:
        lines += ["", *prior.splitlines()]
    handoff_lines = render_handoff(issue, briefing.handoff)
    if handoff_lines:
        lines += ["", *handoff_lines]
    lines += _escalation_lines(briefing.escalation)
    lines += [
        "",
        "## Task, scope, ground truth",
        _placeholder(TASK_PLACEHOLDER),
        "",
        f"## Seat: {seat.name}",
        seat.reason,
    ]
    if seat.owes_reason:
        lines.append(_placeholder(SEAT_PLACEHOLDER))
    if seat.reviews:
        lines.append(REVIEW_SUBJECT_RULE)
        lines.append(
            f"Reviewing: `{seat.reviewing}`."
            if seat.reviewing
            else _placeholder(REVIEW_SUBJECT_PLACEHOLDER)
        )
    # The single-shot contract, verbatim from `dispatch.SINGLE_SHOT_CONTRACT` — one home,
    # shared with `default_brief`, so the composed brief and the default brief cannot
    # disagree. A detached session has no second turn, which is the one fact a briefing
    # cannot let an agent learn the hard way (#279).
    lines += [
        "",
        "## Single-shot",
        dispatch.SINGLE_SHOT_CONTRACT,
    ]
    if briefing.reserved:
        lines += [
            "",
            f"## Reserved surfaces ({len(briefing.reserved)})",
            ", ".join(f"`{path}`" for path in briefing.reserved),
            RESERVED_RULE,
        ]
    lines += _worktree_lines(issue, seat, briefing.tree)
    lines += _protocol_lines(briefing)
    if gate.reads_a_verdict:
        lines += ["", "## Paste rule", PASTE_RULE]
    findings = ",".join(found.kind for found in briefing.assessment.findings) or "none"
    lines += [
        "",
        "---",
        (
            f"Composed by `just brief {issue}`: the invariant half only."
            f" Readiness findings: {findings}. Token effect unmeasured (#212)."
        ),
        "",
    ]
    return "\n".join(lines)


# -------------------------------------------------------------------------------- the CLI


def issue_number(raw: str) -> int:
    """Parse an issue reference, with or without the `#` an agent types."""
    text = raw.strip().removeprefix("#")
    if not text.isdigit() or int(text) <= 0:
        message = f"not an issue number: {raw!r}"
        raise argparse.ArgumentTypeError(message)
    return int(text)


def reviewing_refusal(seat_name: str, reviewing: str) -> dispatch.Refusal | None:
    """Refuse `--reviewing` on a seat that reviews nothing, in the dispatcher's own shape.

    The two adjacent surfaces answer the same question the same way (#322), and round 2
    made them agree in *wording* while leaving them disagreeing in *form*: `just dispatch`
    emits a typed refusal — `refusal=<kind>`, the `found=` fields, `action=` — and this
    composer emitted an argparse usage error that merely mentioned the kind in prose. A
    reader or a script that can parse one and not the other has two surfaces, not one, so
    the refusal is not restated here at all: `dispatch.reviewed_profile_refusal` builds it
    and `Refusal.lines()` renders it, exactly as the dispatcher renders its own.

    Only this one pair is borrowed. A review briefing composed with no subject is
    legitimate — it opens a placeholder, where a dispatch meets `review_subject_unknown` —
    and the profile name stays unvalidated for `derive_seat`'s stated reason, so the
    dispatcher's other two answers are deliberately not reached from here.

    An unregistered seat name cannot be reached through the parser, whose `--seat` choices
    are the registry's own keys; it is answered anyway, and fail-closed, because the one way
    to arrive is this module's default drifting out of that registry — a check that could not
    run is not a check that passed (#41).
    """
    if not reviewing:
        return None
    seat = dispatch.SEATS.get(seat_name)
    if seat is None:
        return dispatch.Refusal(
            "reviewing_without_review_seat",
            (f"seat={seat_name}", f"reviewing={reviewing}", "registry=absent"),
            (
                "This composer's seat is not in `just dispatch`'s registry, so whether it "
                "reviews could not be read, and a check that could not run is not a check "
                "that passed (#41). Nothing was composed."
            ),
        )
    if seat.reviews:
        return None
    return dispatch.reviewed_profile_refusal(seat_name, reviewing)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """One door: which issue, which seat, where the output goes."""
    parser = argparse.ArgumentParser(
        prog="just brief",
        description="Compose the invariant half of a dispatch briefing.",
    )
    parser.add_argument("issue", type=issue_number, help="issue number, e.g. 251")
    parser.add_argument(
        "--seat",
        default="",
        choices=("", *sorted(dispatch.SEATS)),
        help="the seat this dispatch is for (default: implementer)",
    )
    # The profile name itself is unvalidated on purpose: `tools/dispatch.py` owns what a legal
    # subject is, and a `choices=` list built from its registry would be a second copy that
    # drifts (#322). Whether the *seat* takes the option at all is a different question, and
    # it is answered below rather than left to render as silence.
    parser.add_argument(
        "--reviewing",
        default="",
        metavar="PROFILE",
        help="the profile whose work is under review; carried into a --seat review briefing",
    )
    parser.add_argument("--out", default="", help="write the brief here instead of stdout")
    parser.add_argument(
        "--prior-work",
        action="store_true",
        help="print only commits on origin/main that reference the issue",
    )
    parser.add_argument(
        "--base-sha",
        default="",
        help="the base SHA `just worktree add` printed, when it is not this box's",
    )
    parser.add_argument("--repo", default=REPO_SLUG, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    refusal = reviewing_refusal(args.seat or DEFAULT_SEAT, args.reviewing)
    if refusal is not None:
        for line in refusal.lines():
            print(f"[brief] {line}", file=sys.stderr)  # noqa: T201 — a CLI's refusal channel
        raise SystemExit(dispatch.EXIT_REFUSED)
    return args


def main(  # noqa: PLR0913 — one keyword seam per external read, each injected independently in tests
    argv: Sequence[str] | None = None,
    *,
    read_issue: Callable[[int, str], dict[str, object]] = fetch_issue,
    read_open: Callable[[str], list[dict[str, object]]] = fetch_open_issues,
    read_prior: Callable[[int, Path], tuple[PriorWork, ...]] = prior_work,
    read_handoff: Callable[[int], Handoff] = fetch_handoff,
    repo: Path = REPO,
) -> int:
    """Compose the brief, or refuse loudly. Never a silent empty brief."""
    args = parse_args(argv)
    try:
        work = read_prior(args.issue, repo)
    except PriorWorkError as failure:
        print(f"[brief] {failure}", file=sys.stderr)  # noqa: T201 — a CLI's refusal channel
        print(  # noqa: T201 — a CLI's refusal channel
            f"[brief] No report was produced for #{args.issue}. Nothing was written.",
            file=sys.stderr,
        )
        return NO_RESULT

    if args.prior_work:
        report = render_prior_work(args.issue, work)
        if args.out and report:
            Path(args.out).expanduser().write_text(report + "\n", encoding="utf-8")
        elif report:
            print(report)  # noqa: T201 — the report IS this script's output
        return 0

    try:
        document = read_issue(args.issue, args.repo)
        open_issues = read_open(args.repo)
    except FetchError as failure:
        print(f"[brief] {failure}", file=sys.stderr)  # noqa: T201 — a CLI's refusal channel
        print(  # noqa: T201 — a CLI's refusal channel
            f"[brief] No brief was composed for #{args.issue}. Nothing was written.",
            file=sys.stderr,
        )
        return NO_RESULT

    body = str(document.get("body") or "")
    gate = derive_gate(body, read_vocabulary(repo))
    handoff = read_handoff(args.issue)
    seat = derive_seat(args.seat, args.reviewing)
    rendered = compose(
        Briefing(
            issue=args.issue,
            title=str(document.get("title") or ""),
            gate=gate,
            flakes=select_flakes(open_issues),
            seat=seat,
            tree=resolve_tree(args.issue, args.base_sha, repo),
            assessment=readiness.assess(body),
            reserved=reserved_surfaces(named_paths(body)),
            prior_work=work,
            handoff=handoff,
            escalation=escalation_for(body, seat.name, repo),
        )
    )
    if str(document.get("state") or "").upper() == "CLOSED":
        print(  # noqa: T201 — a CLI's refusal channel
            f"[brief] #{args.issue} is CLOSED. Composed anyway; check the assignment.",
            file=sys.stderr,
        )
    if gate.kind == GATE_UNDETERMINED:
        print(  # noqa: T201 — a CLI's refusal channel
            f"[brief] gate=undetermined for #{args.issue}: {gate.because[0]}."
            " The brief says so; it does not default to the cheaper gate.",
            file=sys.stderr,
        )
    if handoff.state == HANDOFF_UNAVAILABLE:
        print(  # noqa: T201 — a CLI's refusal channel
            f"[brief] handoff=unavailable for #{args.issue}: {handoff.detail}"
            " The brief says so; it does not render the absence.",
            file=sys.stderr,
        )
    if args.out:
        Path(args.out).expanduser().write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")  # noqa: T201 — the brief IS this script's output
    return 0


if __name__ == "__main__":
    sys.exit(main())
