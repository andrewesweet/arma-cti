"""`just dispatch`: the lane-parameterised dispatcher for logical subagents (#223, ADR-0061).

One recipe starts a logical subagent as a **separate process** on a named lane and
returns at once with a dispatch id. Everything that decides anything lives here, where
`tests/unit/test_dispatch.py` can reach it; `tools/dispatch.sh` keeps only the seam it
owns — detaching the child from the turn that armed it (ADR-0049).

Four ideas, and each is a ruling made mechanical:

- **Lane** selects the runner and the environment that reaches a provider. Week one has
  two, both on the `claude` binary: `claude-native`, which reaches the Anthropic
  subscription the only compliant way there is (ADR-0061's substrate finding), and
  `zai`, the permitted mirror — the same binary pointed at a non-Anthropic endpoint,
  consuming no Anthropic quota, credential or traffic.
- **Profile** is one opaque token, not three commensurable dimensions (Decision 5).
  `opus-high` and `zai-glm53-max` are names in a registry; nothing outside the registry
  knows that one of them means `--effort high`. Effort vocabularies do not commensurate
  across providers, so the registry is the only place the mapping is allowed to exist.
- **Seat** carries ADR-0071 ruling 1's one survivor: the orchestrator carve-out. Ruling 1
  rescinds the graded authority ladder ADR-0061 built, so the seat table no longer
  encodes provenance and no seat is refused on it at this registry — every seat
  dispatches on every lane. The carve-out is the exception and it is provisional:
  orchestration runs on Claude with a Claude model until a tested alternative exists.
  It is now the **only** provenance refusal the project holds. Routing class 6's
  #326 bridge was the second — it refused a dispatch naming the gates themselves on
  every lane but `claude-native`, and a `just land` on any lane but this one whose diff
  touched them — and ADR-0073 retired it on the human's instruction of 2026-08-18
  (#406). What enforces that row's invariant now is `tools/land_review.py`'s never-alone
  rung: a landing touching those paths needs a review verdict from a different **lane**
  than the author's, which is a rule about the review rather than about who may dispatch.
  Nothing in this module refuses a gate path any more. Routing class 2, orchestration, is not a
  second one: #327 re-founded it on its seats, so it refuses an orchestration declaration
  taken by any seat outside the route that finishes that work — `orchestrator` to perform
  it, `planner`, `implementer` and `review` to plan, land and review it, `recon` to
  reconnoitre it — on every lane, including Claude's, and consults nothing a lane could
  exempt.
- **Identity** is `OTEL_RESOURCE_ATTRIBUTES`, which is what makes a dispatch's telemetry
  self-identifying downstream: `cti.dispatch_id`, `cti.lane`, `cti.profile`, `cti.seat`,
  `cti.issue`, `cti.base_sha`. Decision 1 wants fraction-of-cap for all three pools from
  the first dispatch, and `cti.lane` on the record is what makes that a query.

**The environment is assembled per invocation and never exported globally.**
`ANTHROPIC_BASE_URL` set in a shell profile or in `~/.claude/settings.json` would
silently redirect every Claude Code session on this box, the orchestrator included. So
`assemble_environment` starts from a copy of the parent's environment, *strips every
lane-owned variable whatever its value*, and then adds back only the ones this lane
owns. A parent carrying a stale base URL cannot poison a `claude-native` child, and a
`zai` child cannot leave one behind: the parent mapping is never mutated, and the child
gets a fresh dict.

**Credentials arrive by environment and only by environment.** They are read from
`~/.arma-cti/credentials.env` at mode 0600, put in the child's environment, and put
nowhere else: not on argv (so not in `ps`), not in `dispatch.json`, not in the brief,
not in the log. The dispatch record names the *key* it used, never its value. The stated
limit from #221 stands unchanged — this protects against git, not against the agent,
which runs as the same user.

**The worktree is asserted by the dispatched process, in its own cwd, before the runner
starts.** #105's fourth instance is a harness that hands two agents one tree; an agent
that merely believes its assignment discovers the collision by destroying work. So
`git rev-parse --show-toplevel` is run inside the assigned path and compared to it, and
a mismatch refuses loudly rather than working somewhere else.

Refusals are named, in the tier's `key=value` form, and a refusal that means "this
dispatch never happened" carries a failure class from CLAUDE.md's table. The refusals
this module owns are all `infra_unavailable`: a lane that could not be reached says
nothing about the code under test, which is exactly what that row means.

**The `zai` lane's economics are the inverse of Claude's, and that changes one setting
rather than the design.** Measured live against the endpoint (#225,
`docs/research/zai-lane-live-findings.md`): the plan meters prompt counts, prefix caching
is automatic and identical whether or not `cache_control` is sent, and
`thinking.budget_tokens` is ignored. So `ENABLE_PROMPT_CACHING_1H` is **not set on this
lane** — it only rewrites a `cache_control` TTL that measurably decides nothing here, and
even a real token saving would not be a plan saving under a prompt meter. The ignored
budget used to be read here as collapsing the five effort levels into one profile per
model; the runner in use does not support that step, because effort travels as a request
field of its own that nothing has measured on this lane (#433) — the `zai` profiles
below, and their comment, are the statement of record.

**No admission standing is read, and nothing here refuses on one** (#328). ADR-0061
Decision 6 pre-registered a bar that admitted a profile to a seat against the Claude
history, and this file used to read its far end before it planned anything. ADR-0071 ruling
6 dropped that bar and withdrew Decision 6. The rung is gone rather than made permissive:
there is no standing to consult, no `admission_escalated` refusal to hit, and no directory
of records for a dispatcher to point at.

That is a deliberate departure from a pre-registration rather than a conclusion its data
reached — the bar never adjudicated once across its routes, every one still on probation at
the drop with none admitted and none failed — and it is
recorded as one in `tools/trial.py`, which is what the module became. What replaces it is
retrospective (#336's observatory), and it is not built yet, so for now a route is judged by
nothing upfront at all.

**The `zai` lane dispatches only in off-peak hours** (#238). The human ruled that on
2026-08-05 as a hard rule, so it is a rung here rather than guidance: outside z.ai's
published peak band the lane dispatches normally, and inside it every dispatch is refused
with the window, the terms it came from, and when it next opens. There is no override on
this surface — no flag, no environment variable, no exemption — because the rule is the
human's and only they amend it. The window itself is not restated here; it is the lane's
published schedule in `tools/breaker.py`, the same object `plan_charge` prices a dispatch
with, so what refuses a dispatch and what a dispatch records can never disagree.

**The issue is read before anything is planned, and an unready one is refused** (#241).
Definition of ready, mechanically: `tools/readiness.py` judges the body for criteria that
exist, that can be counted off, and that name the evidence which would settle them. Two of
those three sub-checks refuse, because measured against the last twenty dispatched issues
they refused none of them; enumerability does not, because it refuses 15% of that corpus
and 67% of its ruling executions — whose criteria *are* the ruling, arriving as prose that
must be transcribed rather than paraphrased into a checklist. So it reports on every issue
and blocks none, and the report is kept on the dispatch record so the rate can be counted
again later. The remedy on a refusal is always an edit to the issue by a human or triage,
never a rewrite by this tool, and the rung is lane-blind: nothing about the lane, the
profile or the seat reaches it.

**The lane's breaker is read before anything is planned** (#226). That is the one place
ADR-0061's other two classes reach this file: a lane out of quota refuses with
`quota_exhausted` and the published reset time, and a lane whose quality trip has fired
refuses with `provider_refused` and escalates. Neither is invented here — both come from
`tools/breaker.py`'s verdict, which is a state file this module reads and never writes
by itself. What it does write is the other direction: when a dispatched run ends, its
own log is classified and fed back to the breaker, which is how a 429 trips a lane on a
provider that publishes no quota state.

**The dispatch policy is read before anything is planned** (#250). The human's freeze, the
carve-out packages, the ruled WIP limit and its reservations live in
`~/.arma-cti/queue/policy.json` and are read *per dispatch* by `tools/queue.py`, which is
what makes a freeze reach a session already running rather than only a session that starts
after it — ADR-0042's stale-copy window, closed one level up. The refusal follows the
off-peak rung's precedent exactly, override and failure class included: there is no flag and
no environment variable that dispatches through a freeze, and the refusal **carries no
failure class**, because nothing was found about any provider, any lane or any code.

**A dispatch can be stopped, and a tree that already holds one refuses a second** (#308).
Both halves come from #105's sixth instance, where a seat killed a dispatch, saw `ps -p
<pid>` return nothing, pre-flighted the tree clean and re-dispatched into it — while the
session it thought it had killed worked on for half an hour. `--stop <id>` resolves the
dispatch to its worktree and then to every process whose `/proc/<pid>/cwd` is inside that
tree, signals, and **verifies by re-scanning**; `tools/dispatch_stop.py` owns the scan and
its refusals, and this file owns the surface. The occupancy rung below is the other half:
a tree already carrying a dispatch with no `result.json` refuses
`worktree_occupied_by_dispatch` and names the holder, because the pre-flight answers "is
this tree clean now" and the question that produced two agents in one worktree was "is
anyone still working in it".

**A seat resolves its own profile, and the record says which and why** (#321, ADR-0071
ruling 2). Naming a seat is the ordinary way to dispatch: each seat carries an ordered
preference over profiles, head first, and `resolve_seat` walks it to the first entry that
is dispatchable *right now* — reading the `(profile, seat)` block, the lane's breaker, the
human's off-peak rule and the lane's credential, each by
calling the same function the ladder calls rather than by keeping a second copy of it. The
resolved route is written into the request, so every rung below climbs a complete one and
none of them can tell how it was arrived at, which is the ruling's point that a refusal
attaches to a `(profile, seat)` pair rather than to a path. What was walked past,
and on which refusal, goes on the dispatch record beside what was chosen, because an
outcome attributed to a profile nobody chose deliberately is an outcome nobody can read
later. A whole list unavailable is `seat_list_exhausted` — named, never a silent fallback
to something the seat's table does not carry. Naming `--profile` still works and is still
subject to every `(profile, seat)` refusal: it is a way of choosing, never a way around.

**The review seat cannot review its own profile, and cannot affect the reviewed ref** (#322,
ADR-0071 ruling 4).
Both halves come from one invariant: no single model instance may both propose a change and
produce the verdict that clears it. So a review dispatch names the profile whose work it
reviews — `--reviewing` — and resolution *removes* that profile from the list before walking
it, putting a different lane first among what is left. The author set resolution removes
against is both sources #398 named — the dispatch records and the interactive declaration,
merged here exactly as `just land` merges them — because a dispatcher that read only the
first could spend a review on the profile that authored the change and learn it from the
landing's refusal (#402). A declaration that will not read, or has been lost, refuses the
dispatch by name rather than resolving against a set it cannot trust.

**The subject is derived where it is derivable, and the declaration is checked against the
derivation.** A declaration on its own is controlled by whoever proposes the review: `--profile
opus-high --reviewing codex-luna-max` names two registered profiles, satisfies every check, and
lets the implementing instance clear its own work while the record misstates the subject. So
`authoring_dispatches` reads this box's dispatch records for the issue under review — every
dispatch on that issue which was not itself a review and did not refuse before it ran — and a
declaration those records contradict is refused `review_subject_contradicted`. Where nothing
can be derived, the declaration stands and the route is recorded as **unverified** with the
reason, so ruling 4's landing check (#334) has a fact to refuse on rather than a field the
proposer controls. Which of several authoring profiles a multi-dispatch branch should be
reviewed past is #333's adjudication and is deliberately not decided here.
Preferring is an ordering and not a second filter: an entry that shares the reviewed lane is
still walked, because the invariant is about the instance producing the verdict and provider
diversity is what is merely preferred. Where removal leaves nothing, `review_same_profile`
refuses rather than proceeding same-model, and the same refusal meets a caller who names the
reviewed profile with `--profile`. The absent declaration refuses too: without it nothing
could resolve past anything, so it refuses before the walk rather than resolving a
reviewer nobody has checked against the work.
The second half is containment. `--permission-mode` defaults to `acceptEdits`, which is
writable on both runner families, so a review dispatched at the default could edit the
persistent tree; the seat now *forces* `plan` in `routed`. Claude receives that as a
permission policy and can execute gates in its disposable tree. Codex receives it as an OS
sandbox policy, which the same disposable tree maps to `workspace-write` plus the measured
cache grants. The tree is removed when the dispatch ends, and the verdict's reviewed SHA is
checked independently at landing.

**Review delivery crosses that containment at the harness boundary** (#496, widened #599).
The review's
stdout is written through a file descriptor the unsandboxed dispatcher opened, so the session
needs neither a writable body-file path nor GitHub credentials. Exact marker lines bound the
report within that stream; the dispatcher posts only their contents with a capture notice.
After a successful child exit it makes one bounded `gh issue comment --body-file -` call before
outcome classification and breaker journaling. Missing or ambiguous markers, an empty bounded
report, or a refused call ends in `review_delivery_failed`, while the child's own return code
remains on `result.json`. If its prescribed markers are absent, the host may post bounded,
explicitly unverified text from stdout and from regular files in the dispatch-scoped plan
directory whose modification time falls inside the child's own window.
Multiple regular-file candidates fail closed: no plan file is posted, and the refusal names the
count without exposing paths or contents. That is transport only: the refusal, return code,
missing verdict and review-loop state remain.

**`recon` forces the same mode, for a reason of its own** (#407). ADR-0071 does not merely
describe that seat as non-landing; it reasons from the unranked profile head, the routing
class 2 admission and the absent escalation entry. The seat authors no landing, but its
disposable tree may execute gates and collect evidence without changing the reviewed ref.
The same explicit worktree boundary protects it from the persistent-tree edit that prompted
#407.

**The routing class policy is a separate, per-dispatch read** (#266). Queue policy answers
whether work may start now; `config/dispatch-routing-policy.json` answers which class the
declared work is in and what that class asks for. It was the keep-on-Claude policy until
#326 re-founded it class by class on capability and conflict of interest, so a match no
longer implies a refusal: two of the five classes classify without barring a route. The main
checkout is read on every dispatch, never at startup, so a policy edit landed after an
orchestrator session began reaches its next call. A refusing match refuses by class name and
remedy with no override and no failure class, and carries the policy's own statement that
its class list does not cover everything it asserts an invariant over. This first
read is explicitly advisory because an issue can understate its eventual surface; `just
land` is the enforcing half and checks the actual rebased diff against the trusted policy.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import secrets as secrets_module
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple
from urllib.parse import quote

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `stall_watch.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes these importable.
import attribute_registry
import breaker
import codex_guidance
import dispatch_stop
import gate
import gate_clock
import gate_report
import hook_parity
import queue_policy
import readiness

# `review_exchange` is imported for its push half alone (#405): a harness-side commit is
# handed over on exactly the ref the review loop already reads, rather than on a second
# convention. It imports this module only lazily, so there is no cycle through it.
import review_exchange

# `review_loop` is read here for the landing's author-set merge, so the dispatcher and
# `just land` cannot disagree about who authored a change (#402). The cycle runs one way
# at module level only: `review_loop` imports this module lazily in its `escalate` and
# `author` handlers — `escalate` also names `arbiter` for the same reason — so this import
# is safe today and those edges cannot move up without cycling them back.
import review_loop
import routing_policy
import worktree as worktree_tool

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

EXIT_REFUSED: Final = 1

RECON_DEFAULT_REF: Final = "refs/heads/main"

DISPATCH_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"
CREDENTIALS: Final = Path.home() / ".arma-cti" / "credentials.env"
CHILD_STATE_UNKNOWN_ACTION: Final = (
    "Do not re-dispatch yet. Inspect dispatch.log, the child process, and the assigned "
    "worktree. Reconcile any work found, then re-dispatch only after verifying the child "
    "has stopped and another run cannot duplicate that work."
)

# How much of a finished run's log the breaker's classifier reads. A provider's own
# refusal or limit message is the last thing a run says, and a whole log of an agent's
# work would be a haystack full of the words this looks for.
LOG_TAIL_BYTES: Final = 8192

# Claude Code documents `OTEL_RESOURCE_ATTRIBUTES` as strict: US-ASCII, no spaces,
# percent-encode anything exotic. The collector's `group_by` file export also turns a
# dispatch id into a path segment. Both reasons point at the same narrow alphabet, so
# the id is minted inside it and checked rather than hoped for.
ID_ALPHABET: Final = re.compile(r"\A[a-z0-9][a-z0-9-]*\Z")

REVIEW_PLAN_DIRECTORY_ENV: Final = "CTI_REVIEW_PLAN_DIRECTORY"

# Stripped from the child's environment whatever the parent had in them, before this
# lane's own values go back. The list is the union of every variable that can move a
# Claude Code session onto a different endpoint or credential; leaving any one of them
# inherited would make a lane's identity a property of the shell that dispatched it.
LANE_OWNED: Final = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "CLAUDE_CODE_OAUTH_TOKEN",
    # Cache TTL is lane-owned for the same reason a base URL is: it changes what the
    # child sends to a provider, so inheriting it would make a lane's behaviour a
    # property of the shell. No lane sets it. On `claude-native` it is not needed — a
    # dispatched `claude -p` is a main session and already carries the one-hour TTL
    # (#218) — and on `zai` it is measured inert; see `zai_cache_ttl` below.
    "ENABLE_PROMPT_CACHING_1H",
    # A declared context window is lane-owned for a base URL's reason: it changes what the
    # child assumes about its provider, so inheriting it would make auto-compaction a
    # property of the shell that dispatched. Set from `Lane.context_window` and nowhere
    # else (#444).
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
    # Review plan capture is scoped per child worktree. Never inherit a caller's path:
    # doing so could make this dispatch publish another session's plans.
    REVIEW_PLAN_DIRECTORY_ENV,
)

STOP_NOT_A_RESULT: Final = (
    "Stop. A lane that could not be reached is not a result about the code under test "
    "(CLAUDE.md's failure-class table, infra_unavailable)."
)


class Refusal(NamedTuple):
    """One refusal: its class, what was found, and what the caller should do."""

    kind: str
    found: tuple[str, ...]
    action: str
    failure_class: str = ""

    def lines(self) -> tuple[str, ...]:
        """Render the refusal as the lines the caller reads."""
        classed = (f"class={self.failure_class}",) if self.failure_class else ()
        return (f"refusal={self.kind}", *classed, *self.found, f"action={self.action}")


class Lane(NamedTuple):
    """A provider reached by a runner binary under a named environment."""

    name: str
    runner: str
    base_url: str
    credential: str
    model_slots: tuple[tuple[str, str], ...]
    note: str
    # Whether the human has ruled this lane off-peak-only. This is *policy*, which is why
    # it lives in the registry beside the lane's wiring and not in `tools/breaker.py`
    # beside the published schedule: the schedule states when the band is, and this states
    # that we have chosen to dispatch only inside it. A lane with no ruling dispatches at
    # any hour and is still priced by its schedule if it has one.
    off_peak_only: bool = False
    # Which command line the runner speaks. Two lanes can share a binary (`claude-native`
    # and `zai` both drive `claude`) and two binaries do not share a flag vocabulary, so
    # the family — not the binary name — is what `build_argv` dispatches on. Adding a
    # third Claude-shaped lane changes nothing here; adding a differently-shaped runner
    # adds one builder and one family name, which is the only place the difference lives.
    runner_family: codex_guidance.GuidanceHarness = codex_guidance.GuidanceHarness.CLAUDE_CODE
    # The provider's real context window, in tokens, where the runner cannot learn it.
    # Claude Code assumes 200,000 for a model name it does not recognise and auto-compacts
    # against that assumption, which on `zai` compacted 34 of 129 sessions against a
    # provider that would have held five times as much (#444). Zero means the runner
    # already knows and nothing is declared — never "unmeasured", which is why the one
    # non-zero value below carries its measurement rather than a round guess.
    context_window: int = 0


class Profile(NamedTuple):
    """One opaque `(lane, model, effort)` token (ADR-0061 Decision 5)."""

    name: str
    lane: str
    model: str
    effort: str


# The lane the routing policy exempts, as one literal in this module — `tools/land.py`'s
# `CLAUDE_LANE`, for the reason that module's own comment gives (#344, review round 1
# claim 6): a second copy is how renaming the lane, or moving `claude_lane` in the policy,
# would silently move only one of the places that reads it. The two routing sites below
# take it from here; the ones that *can* consult a parsed policy prefer `policy.claude_lane`
# and reach this only where there is no policy to ask (#326 review round 3 claim 6).
CLAUDE_LANE: Final = "claude-native"

# The registry. Adding a lane or a profile is an edit here and nowhere else, which is
# the whole point of Decision 5: no caller anywhere gets to compose a model with an
# effort, because across providers those two do not compose.
LANES: Final[dict[str, Lane]] = {
    CLAUDE_LANE: Lane(
        name=CLAUDE_LANE,
        runner="claude",
        base_url="",
        credential="",
        model_slots=(),
        note=(
            "The Anthropic subscription through Claude Code, which ADR-0061 records as "
            "the one compliant configuration. No credential of ours: the binary uses "
            "the box's own login. A dispatched `claude -p` is a main session, so it "
            "carries the one-hour cache TTL (#218)."
        ),
    ),
    "zai": Lane(
        name="zai",
        runner="claude",
        base_url="https://api.z.ai/api/anthropic",
        credential="ZAI_API_KEY",
        model_slots=(
            ("ANTHROPIC_DEFAULT_OPUS_MODEL", "glm-5.3"),
            ("ANTHROPIC_DEFAULT_SONNET_MODEL", "glm-5.3-flash"),
            ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "glm-4.7"),
        ),
        note=(
            "The permitted mirror: the `claude` binary against z.ai's Anthropic-shaped "
            "endpoint, which consumes no Anthropic quota, credential or traffic. The "
            "base URL and the three model-slot variables are z.ai's own published "
            "integration (docs.z.ai/devpack/tool/claude). Needs ZAI_API_KEY in "
            "~/.arma-cti/credentials.env, which is #229's human item. The three slots "
            "now name three different models: the sonnet slot was the opus slot's "
            "synonym until the human's ruling of 2026-08-27 seated glm-5.3-flash, so it "
            "is a third arm rather than a spare name. The slug was read back from the "
            "endpoint's own model list that day (GET /api/paas/v4/models returns ten "
            "models, glm-5.3-flash among them); z.ai's Claude Code integration page does "
            "not document a default mapping for it, and this lane sets its own slots "
            "rather than taking the published defaults, so nothing here rests on one."
        ),
        # The human's hard rule, 2026-08-05 (#238): this lane is used only off-peak, as a
        # dispatch-time refusal rather than as guidance. Only the human amends it.
        off_peak_only=True,
        # Measured against the live endpoint on 2026-08-20 (#444), `/count_tokens` as the
        # ruler: `glm-5.3` accepted 1,049,169 input tokens and refused 1,052,969, so the
        # window is about 1.05M against the 200,000 Claude Code assumes. A round million
        # sits below the accepted floor with margin for a serving tokeniser that counts a
        # request slightly differently from `/count_tokens`.
        #
        # The ceiling this does not cover: the variable is session-wide rather than
        # per-model — measured, by running the same treatment on `--model haiku` and
        # watching the `glm-4.7` warning go quiet too — and the haiku slot's own window is
        # smaller, accepting 200,729 and refusing 256,467. A haiku-slot subagent is
        # therefore told it has a million tokens and would be refused at about 256k, with
        # z.ai's refusal arriving as an HTTP 200 carrying `model_context_window_exceeded`
        # and an empty content block rather than as an error. Measured exposure is 3
        # transcripts peaking at 74,567 tokens, so this is a named ceiling rather than a
        # mechanism; the fix, if it is ever spent, is to point the haiku slot at `glm-5.3`
        # so the session has one window.
        context_window=1_000_000,
    ),
    "codex": Lane(
        name="codex",
        runner="codex",
        base_url="",
        credential="",
        model_slots=(),
        runner_family=codex_guidance.GuidanceHarness.CODEX,
        note=(
            "OpenAI's Codex CLI against the ChatGPT Plus subscription, permitted by the "
            "human's 2026-08-06 ruling on #229. **No credential of ours and none on the "
            "environment**: the CLI reads its own `~/.codex/auth.json` at mode 0600, so "
            "this lane's credential column is empty for a different reason than "
            "`claude-native`'s — there it is the box's Claude login, here it is the box's "
            "ChatGPT login, and in neither case does `just dispatch` handle a secret. "
            "The models are the three the authenticated catalogue lists as agentic coding "
            "arms, verified from the CLI's own model cache rather than assumed (#243). "
            "Not off-peak-ruled: OpenAI publishes no time-of-day discount, so there is no "
            "band to price against and `plan_charge` is `None` here — an absence of terms, "
            "never a multiplier of 1.0."
        ),
    ),
}

PROFILES: Final[dict[str, Profile]] = {
    "opus-xhigh": Profile("opus-xhigh", "claude-native", "opus", "xhigh"),
    "opus-high": Profile("opus-high", "claude-native", "opus", "high"),
    "opus-max": Profile("opus-max", "claude-native", "opus", "max"),
    "sonnet-high": Profile("sonnet-high", "claude-native", "sonnet", "high"),
    "haiku-medium": Profile("haiku-medium", "claude-native", "haiku", "medium"),
    # The fable seat's route to a fable session (#269). #242 ruling 1's surviving half is that
    # fable is *dispatched* rather than resident: while the orchestration seat was itself fable
    # a subagent inherited it from its dispatcher, which is how the twenty-fifth retro ran
    # unattended, and dropping the seat removed that inheritance without leaving anything to
    # dispatch through. The seat was always expressible (`SEATS` has `fable`, and since
    # ADR-0071 ruling 1 no bar reaches it); only the profile was missing.
    #
    # **What the seat is for is not enumerated here** (#329 review round 2, F2). The list this
    # comment used to carry — retros; ADR, CONTEXT.md and schema semantics; retro evidence
    # banking — was the withdrawn mapping's scope, and it outlived it: live
    # `config/dispatch-routing-policy.json` refuses `fable` on both the ADR-authorship class
    # and the orchestration class, so the copy contradicted the policy in the very file the
    # briefing composer names as its authority. The live scope is routing class 4 and
    # `config/escalation-conditions.json`'s fourth condition, which orders the transfer; a
    # second copy here would drift again.
    #
    # Four efforts and not one, because no effort is privileged: the profiles are named so a
    # dispatcher can pick, not so a paragraph can. The model is `fable`, the alias the `claude`
    # runner documents for `--model` alongside `opus` and `sonnet` (verified against the
    # binary's own `--help`, not assumed from its siblings — `build_argv` passes `model`
    # straight through, so nothing else needed changing).
    "fable-medium": Profile("fable-medium", "claude-native", "fable", "medium"),
    "fable-high": Profile("fable-high", "claude-native", "fable", "high"),
    "fable-xhigh": Profile("fable-xhigh", "claude-native", "fable", "xhigh"),
    "fable-max": Profile("fable-max", "claude-native", "fable", "max"),
    # What #225 measured on this lane is narrow and still stands
    # (docs/research/zai-lane-live-findings.md §2): z.ai's endpoint honours
    # `thinking.type` and ignores `thinking.budget_tokens` — one hard prompt at budget
    # 1,024 and at budget 32,000 both thought past 9,000 tokens and both stopped on
    # `max_tokens`, not on the budget. That measured the thinking budget and nothing
    # else: the requests were hand-sent `curl`s with Claude Code deliberately out of the
    # loop. What it did not measure is what the runner sends for `--effort`. In the
    # installed 2.1.235 the effort level travels as its own request field,
    # `output_config.effort`, and the thinking budget comes from the model's own upper
    # limit, not from the effort level — so §2's step from "the budget is ignored" to
    # "all five efforts are one configuration" was an assertion about the runner, never
    # a measurement, and the runner that dispatches today does not match it. It is why
    # no model here carries five names; it is not proof that two names are one arm.
    #
    # A human ruling on 2026-08-19 (#433, for #432's codex-absence substitution table)
    # overruled the one-name-per-model conclusion that used to stand here and named
    # `zai-glm53-high` beside `-max`. The two names produce different request bodies —
    # `output_config.effort` high against max — in a field nobody has measured on this
    # lane: whether z.ai honours, ignores or rejects it is open, and on a 400 the runner
    # latches the field unsupported and retries without it. The arrangement that would
    # settle it is §2's shape widened by one field — the same body twice at two effort
    # levels, the `usage` blocks compared. It has not been run, and the orchestrator
    # declined it deliberately: it spends lane quota and sends a prompt to an external
    # provider to settle a comment's wording. A reader choosing between the two names
    # follows the ruling's table, not a measured distinction.
    #
    # What remains genuinely distinct is the *model*, and each name still selects
    # through the lane's slots: `--model opus` resolves to glm-5.3 and `--model haiku`
    # to glm-4.7.
    "zai-glm53-max": Profile("zai-glm53-max", "zai", "opus", "max"),
    "zai-glm53-high": Profile("zai-glm53-high", "zai", "opus", "high"),
    "zai-glm47-max": Profile("zai-glm47-max", "zai", "haiku", "max"),
    # The human's ruling of 2026-08-27 heads `implementer` and `recon` with GLM-5.3-Flash,
    # which no profile named. It reaches the endpoint through the sonnet slot, which this
    # lane had been pointing at glm-5.3 as a synonym for the opus slot — so seating Flash
    # there costs no arm. What the two names are worth against each other is the same
    # open question the comment above records for `zai-glm53-max` against `-high`:
    # `output_config.effort` differs in the request body and z.ai's handling of it is
    # unmeasured on this lane. They follow the ruling's table, not a measured distinction.
    "zai-glm53flash-max": Profile("zai-glm53flash-max", "zai", "sonnet", "max"),
    "zai-glm53flash-high": Profile("zai-glm53flash-high", "zai", "sonnet", "high"),
    # Four profiles on this lane, and the reason they are not one is the exact inverse of
    # z.ai's. There, the thinking budget made no difference: two budgets a factor of
    # thirty apart were indistinguishable, so names differing only in that budget would
    # be names for one arm. Here effort
    # is a real dimension, measured the same way (#243,
    # docs/research/codex-lane-live-findings.md §3): one non-memorised counting problem at
    # `low` produced 484 reasoning tokens and at `xhigh` produced 2,393, a factor of 4.9 on
    # identical input. So the registry carries levels, because levels decide something.
    #
    # The model slugs are the authenticated catalogue's own, read from the CLI's model
    # cache rather than assumed from the human's shorthand: `gpt-5.6-sol` is the frontier
    # agentic arm (catalogue default effort `low`), `gpt-5.6-terra` the balanced one
    # (default `medium`). The catalogue publishes six levels for both — `low`, `medium`,
    # `high`, `xhigh`, `max`, `ultra`.
    #
    # Two of the six are deliberately unregistered rather than forgotten. `ultra` is
    # described by the provider as "maximum reasoning with automatic task delegation",
    # which is a different execution model and not merely a deeper one — an arm that may
    # spawn its own work is not something to hand a seat before it is understood. `max` is
    # simply unmeasured here. Both remain one registry line away.
    #
    # Stated limit: the factor of 4.9 was measured on `terra`. `sol` inherits the same six
    # published levels, and its profiles rest on that publication rather than on a second
    # measurement.
    "codex-sol-xhigh": Profile("codex-sol-xhigh", "codex", "gpt-5.6-sol", "xhigh"),
    "codex-sol-max": Profile("codex-sol-max", "codex", "gpt-5.6-sol", "max"),
    "codex-sol-high": Profile("codex-sol-high", "codex", "gpt-5.6-sol", "high"),
    "codex-terra-medium": Profile("codex-terra-medium", "codex", "gpt-5.6-terra", "medium"),
    "codex-terra-low": Profile("codex-terra-low", "codex", "gpt-5.6-terra", "low"),
    # Luna, the catalogue's third agentic arm, and Opus at low effort (ADR-0071 ruling 2).
    # Luna's slug and published default effort are read from the authenticated CLI's own
    # model cache at `~/.codex/models_cache.json` — the same source the `gpt-5.6-sol` and
    # `gpt-5.6-terra` slugs above came from — not assumed from the human's shorthand. The
    # cache fetched 2026-08-11 carries `slug=gpt-5.6-luna`, `default_reasoning_level=medium`
    # and the description "Fast and affordable agentic coding model", and publishes five
    # effort levels (`low`, `medium`, `high`, `xhigh`, `max`); `max` is the catalogue's top
    # for Luna, so there is no `codex-luna-ultra` for this registry to name.
    #
    # Luna is a NAMED EXCEPTION to the validated measure-before-building rule (AGENTS.md),
    # not an application of it. The sol/terra entries above rest on a measurement — one
    # counting problem, 484 reasoning tokens at `low` and 2,393 at `xhigh`, the factor of
    # 4.9 the comment block above carries — and Luna rests on publication alone, at the
    # human's ruling. Neither "fast" nor "affordable" has been measured in this project,
    # and the entry is recorded as an exception rather than presented as consistent with a
    # rule it is an exception to. The exception is stated here, beside the act it covers,
    # because the measure-before-building rule is what every other entry in this registry
    # was checked against before it joined.
    "codex-luna-max": Profile("codex-luna-max", "codex", "gpt-5.6-luna", "max"),
    "codex-luna-medium": Profile("codex-luna-medium", "codex", "gpt-5.6-luna", "medium"),
    # Opus at low effort: the native tail of the `implementer` preference list and a
    # dispatch arm in its own right (ADR-0071 ruling 2). `low` was unregistered until now
    # for no reason deeper than that no seat named it; the seat map names it, so it joins.
    "opus-low": Profile("opus-low", "claude-native", "opus", "low"),
    # Opus at medium: #433, human ruling 2026-08-19, for #432's codex-absence
    # substitution table, whose Terra row asks for "Opus/medium" as zai's fallback and
    # found no name to resolve to. Unlike `low`, `medium` was already in this lane's
    # vocabulary for other models (`haiku-medium`, `fable-medium`); only the opus pair
    # was missing it.
    "opus-medium": Profile("opus-medium", "claude-native", "opus", "medium"),
}


class RetiredProfile(NamedTuple):
    """One retired profile name: the profile a rename replaced it with, and when (#413)."""

    successor: str
    retired_on: str


# A renamed profile's old name (#413). `PROFILES` above is what a dispatch may take; this
# table is what a dispatch *record* may carry — two tables, because the distinction is the
# whole fix. #399's rename argument was that no per-name record exists for a rename to
# lose, which was true of the admission bar #328 dropped and false of the dispatch
# records, which name `zai-glm52-max` for as long as they are read: `--reviewing` checked
# the declaration against the registry and the records against the declaration, and after
# a rename those two never agree — `unknown_reviewed_profile` for the old name,
# `review_subject_contradicted` for the new one, and no third answer to give. Resolving a
# retired name through `resolved_profile` reads its successor's lane, and
# `excluded_from_review` resolves the successor into the set a review must not run on —
# the conservative side of that function's own trade, a resolution step against the
# invariant. Naming a retired name in `--profile` still refuses `unknown_profile`,
# because `resolve_selection` reads `PROFILES` and never this table.
RETIRED_PROFILES: Final[dict[str, RetiredProfile]] = {
    # #399, landed 2026-08-18: the zai endpoint moved glm-5.2 to glm-5.3 at the same cost
    # per token, so the profile was renamed rather than paralleled. The retired date is
    # `e19410e`'s, the rename's own commit.
    "zai-glm52-max": RetiredProfile("zai-glm53-max", "2026-08-18"),
}


class Seat(NamedTuple):
    """One seat: which profiles it prefers, and the one provenance rule that reaches it."""

    name: str
    # ADR-0071 ruling 1 rescinds ADR-0061's graded eligibility ladder, so a seat's
    # provenance is no longer a property this table encodes: every seat dispatches on
    # every lane. One rule survives the rescission — the orchestrator carve-out, which
    # runs orchestration on Claude with a Claude model until a tested alternative exists.
    # It is a column on the table for the same reason `reviews` and `permission_mode`
    # are: "which seats the carve-out reaches" is a fact about the seat table, and the
    # table is where every other such fact lives. The ADR names it the only provenance
    # rule the project holds, and it ends when a Codex orchestrator backup exists. Since
    # ADR-0073 (#406) it is the only one in fact as well as in the ADR's words: routing
    # class 6's bridge refused a dispatch naming the gates themselves on every lane but
    # `claude-native`, and a `just land` on the same row's paths off it, and the human
    # retired both halves on 2026-08-18. That row's invariant is enforced at the landing
    # instead, as a requirement on the review rather than a bar on a route: a gate
    # landing's verdict must come from a different lane than the author's
    # (`tools/land_review.py`).
    claude_only: bool
    # ADR-0071 ruling 2's preference column, head first. `resolve_seat` walks exactly this
    # and nothing else, so a seat gains a route by being written here.
    preference: tuple[str, ...]
    # The ADR's escalation column, and deliberately **not** part of seat resolution. An
    # escalation is a judgement that the work is harder than the seat's tier, so for
    # `resolve_seat` it is not a fallback for a head the breaker happens to be refusing;
    # resolving into it would answer "this seat is out of profiles" by silently spending a
    # dearer one, and would make the exhaustion refusal unreachable for every seat that has
    # an entry. So `resolve_seat` never walks it. What does read it is #333's arbiter walk,
    # in `tools/arbiter.py`, and **what that walk does is stated there and nowhere else,
    # this comment included** (#390). Everything above is therefore scoped to `resolve_seat`
    # and states no property of the escalation column itself: the version of this comment
    # that also described the walk got it wrong twice, once by narrowing its trigger to
    # conflict of interest and once by leaving a rung out. Adding a seat still requires
    # deciding its arbiter — the human ruling on #361, 2026-08-14 — and `tools/arbiter.py`
    # is where the empty column's answer is.
    escalation: tuple[str, ...] = ()
    # ADR-0071 ruling 4 (#322): this seat judges work another profile produced, so its
    # resolution takes that profile as an input and never returns it. The column is on the
    # registry rather than a name this module tests for, because "which seats review" is a
    # fact about the seat table and the table is where every other such fact lives.
    reviews: bool = False
    # The permission mode this seat *forces*, whatever the caller asked for, or the empty
    # string where the seat leaves the mode to the caller. ADR-0071 ruling 4: the review
    # seat's containment must be forced, not defaulted — `--permission-mode` defaults to
    # `acceptEdits`, which is writable, so a review dispatched at the default could edit.
    #
    # `recon` joined the column on #407, which is the "somebody does ask" this comment used
    # to anticipate. It was left off on #322 on the ground that forcing a mode on a seat
    # nobody had asked about was a behaviour change outside that issue's criteria; what #407
    # found is that the ground was wrong in the other direction. ADR-0071 states `recon` is
    # read-only in its ruling-2 table and *reasons from* that property — the unranked profile
    # head, the class-2 admission, the absent escalation entry all rest on a seat that
    # authors, lands and reviews nothing — while the registry left it inheriting the writable
    # default. Dispatch `d-20260818-080132-cc45d2` (`codex-luna-medium`, seat `recon`, #374)
    # then wrote `tools/brief.py` and its tests with nothing refusing it. A property an ADR
    # reasons from is not a description, so the seat forces the mode.
    #
    # **Overridden rather than refused**, on both seats that carry the column. A refusal
    # would be a second mechanism for one property, and it would refuse the ordinary
    # dispatch besides: `--permission-mode` *defaults* to `acceptEdits`, so every caller
    # who types nothing arrives here carrying a writable mode, and "refuse a caller who
    # passed one" cannot tell that caller from one who typed it. Overriding contains both
    # and is never silent — `Resolution.containment_lines` names the seat that forced it.
    permission_mode: str = ""

    # #345: whether this seat is ADR-0071 ruling 4's lander — the role that "executes
    # `just land`". The composed brief's Landing section branches on it through
    # `brief.Seat.lands`, which delegates here, exactly as its three protocol sections
    # branch on `judgement_only` (#421): an instruction to land and to close is an ask
    # only the rulings' lander can act on, and every other seat met the close as a
    # standing order for an act ruling 4 had left with nobody — it defines proposer,
    # reviewer and lander and assigns the close to none of them, the correction #345's
    # own first follow-up records — until #439 made it the landing rung's (#323 closed
    # its issue on this line alone). Two rows carry `True`, each on its ruling's own
    # words: `implementer` because ruling 2 says it "carries the work out … and lands
    # it", and `retro` because A4 makes the journal entry "land under ruling 4 like any
    # other change" — one artefact, scoped in the seat's own reason. The planner's
    # `False` is ruling 2's "neither gates nor lands"; `recon` and `review` land
    # nothing by their own rulings and get disposable trees when they force `plan`; no ruling
    # names `fable`
    # or the `orchestrator` as any route's lander, so they are `False`. Every row
    # spells its answer, because the column has no working default: `None` is the
    # undecided state and `refuse_undecided_lands` below fails this module's import on
    # every spelling but the two booleans, so a new seat arrives decided or not at
    # all — never silently in either arm.
    # This is not `tools/ledger.py`'s `SEAT_LANDS`, which classifies what a finished
    # run's record reads as having landed — a view over records, not a fact a brief is
    # composed from, and the two are held in step by name-set only.
    lands: bool | None = None

    # A seat that may write while it runs but must never affect a landing gets a fresh
    # worktree for the dispatch. The flag is explicit rather than inferred from
    # `permission_mode`: forced `plan` is a runner-specific policy, while disposal is the
    # filesystem boundary that makes a writable review safe.
    disposable_worktree: bool = False

    # #681's one predicate: the seats whose briefing carries the fix-round report rule
    # (#374). A column rather than a name a brief path tests for, for the same reason
    # `reviews` is: which seats owe the report is a fact about the seat table, and the
    # table is where every other such fact lives. It stood as a string compare at each
    # brief path for one round — the two-expression shape #421 closed for
    # `judgement_only`, agreed today and drifted the day a seat-scope change moved one
    # path and left the other behind.
    owes_fix_round_report: bool = False

    # #421's one predicate, stated where the column it reads lives so no caller rederives it.
    # Both brief paths branch on this — the composed brief's three sections through
    # `brief.Seat.judgement_only`, which delegates here, and `default_brief` below — and the
    # queue's writes-nothing surface derivation (#339) reads it too. The round that named the
    # predicate left this module's own gate line rederiving the column beside it, which is the
    # shape this property exists to make impossible: an expression typed at a call site agrees
    # with the predicate today and drifts the day one of them changes.
    @property
    def judgement_only(self) -> bool:
        """Whether this seat forces `plan`; runner semantics decide what that permits.

        Claude receives `plan` as a permission policy and can execute commands, including
        commands that write. Codex receives a sandbox policy; a disposable review or recon
        tree widens that policy to `workspace-write` for the tree and measured tool caches.
        This predicate therefore does not mean that the seat cannot run a gate.
        """
        return self.permission_mode == "plan"

    @property
    def runs_gate(self) -> bool:
        """Whether the seat is expected to execute its gate in its assigned tree."""
        return not self.judgement_only or self.disposable_worktree


# The two seats no longer share a list. ADR-0071 ruling 2 gave `review` "the
# implementer's list" and the implementer's escalation *head*, and one shared object was
# how that stayed a fact rather than a copy that drifts. The human's ruling of 2026-08-27
# gives `review` its own preference and its own escalation entry, so the sharing is gone
# and four constants stand where two did. What did not change is where `review`'s
# resolution differs — never the profile under review, preferring a different lane — which
# is #322's and lives in `review_candidates`: it reorders whichever list the seat carries
# rather than holding a second one, so the seat still prefers exactly these profiles in
# exactly this order, and what the reviewed profile changes is which of them are reachable
# and which goes first.
IMPLEMENTER_PREFERENCE: Final = ("zai-glm53flash-max", "codex-luna-max", "opus-low")
IMPLEMENTER_ESCALATION: Final = ("codex-sol-high", "zai-glm53-max", "opus-high")
REVIEW_PREFERENCE: Final = ("codex-sol-xhigh", "zai-glm53-max", "opus-medium")
REVIEW_ESCALATION: Final = ("codex-sol-max", "opus-xhigh")

# ADR-0071 ruling 2's seat table, transcribed. `mechanical` is **retired** by that ruling
# and is absent rather than kept for compatibility: it named a cheaper tier rather than a
# different job, and two names for one choice is what the retirement removes. `fable`
# survives the table because it is not in it — ADR-0071's ruling 3 hands retros to `retro`
# without deleting it. #329 closed the documentation half of that overlap: `AGENTS.md`'s
# Seats and profiles section gives `fable` the #181 shape and nothing wider, and gives
# retros to `retro`. The `/retro` skill's own half is #330's.
SEATS: Final[dict[str, Seat]] = {
    # New in ruling 2, absorbing `cti-implementer-xhigh`'s tier and not its contract: a
    # planner works out what to do and neither gates nor lands. A Codex profile heads its
    # list because ruling 2 is the newer human-signed decision; ruling 1 had already
    # withdrawn the question of whether a gate catches a wrong plan.
    "planner": Seat(
        "planner",
        claude_only=False,
        preference=("codex-sol-xhigh", "opus-xhigh"),
        escalation=("fable-high",),
        lands=False,
    ),
    "implementer": Seat(
        "implementer",
        claude_only=False,
        preference=IMPLEMENTER_PREFERENCE,
        escalation=IMPLEMENTER_ESCALATION,
        lands=True,
    ),
    # No escalation entry, and ADR-0071 ruling 2 as A1 amends it means that as *never
    # applicable* rather than *not yet decided*: `recon` is read-only and lands nothing, so no
    # never-alone loop runs over its output and there is nothing for an arbiter to adjudicate.
    # The registry spells both states `()`, which is why the ADR marks the cell rather than
    # leaving it blank; a reader who needs the distinction reads it there.
    #
    # `permission_mode` is #407's forced `plan`: the ADR's no-landing contract is not a
    # filesystem claim. The disposable flag gives both runner families a tree in which to
    # execute gates; Codex maps the mode to `workspace-write` and the measured cache grants.
    # #392 — nothing compares the ADR's seat table to this registry — is the check that would
    # have caught the missing filesystem boundary; this is its first live instance.
    "recon": Seat(
        "recon",
        claude_only=False,
        preference=("zai-glm53flash-high", "codex-luna-medium", "haiku-medium"),
        permission_mode="plan",
        lands=False,
        disposable_worktree=True,
    ),
    # ADR-0071 ruling 4 (#322) adds the two columns that make never-alone real. `reviews`
    # is what makes this seat's resolution take the profile under review as an input and
    # never return it; `permission_mode` forces `plan` while the disposable worktree keeps
    # the runner's executable edits away from the reviewed ref.
    #
    # **`plan` stays after #449 and #496.** The mode is forced as the runner-specific policy;
    # the disposable worktree, not the word `plan`, keeps executable review edits away from
    # the change it judges (ADR-0071 ruling 4). Findings should never be silent. Configuration
    # originally expected the session itself to post: project settings
    # allowlisted `Bash(gh issue:*)`, the brief ordered `gh issue comment`, and two 2026-08-20
    # runs demonstrated that both runner families could do it from `plan`.
    #
    # That capability was not reliable. Eleven reviews on 2026-08-21 completed without a
    # comment through four observed paths: Claude plan mode lacking `ExitPlanMode`, cancelled
    # Codex connector calls, invalid sandbox-side `gh` authentication, and network failure.
    # The containment remains correct; direct delivery was the broken half.
    #
    # #496 moves only transport. The reviewer bounds its report with the exact marker lines
    # the brief supplies; `_run_child_with_gate_clock` captures stdout through an anonymous
    # host-opened temporary file, then `deliver_review` posts only that section with a notice
    # stating what was captured. A failed, unbounded or empty delivery is
    # `review_delivery_failed`; bounded unmarked stdout and regular files in the dispatch's
    # scoped plan directory may also be posted as explicitly unverified recovery. Multiple
    # in-window plan candidates fail closed and post no plan file. There is no retry, verdict
    # recovery, lock, quarantine or dedupe. Abrupt dispatcher death and findings outside the
    # two attributed sources remain outside the mechanism, stated in the changelog rather
    # than promoted to guarantees.
    "review": Seat(
        "review",
        claude_only=False,
        preference=REVIEW_PREFERENCE,
        escalation=REVIEW_ESCALATION,
        reviews=True,
        permission_mode="plan",
        lands=False,
        disposable_worktree=True,
    ),
    # Ruling 3's own kind of work: the retro seat, on the preference order the ADR's own
    # table carries. That order is not the human's enumerated retro list of 2026-08-09
    # (#300) written out — the list named nine profiles, this names three, and the ADR's
    # trailer supersedes that ruling wholesale, which is why #327 could delete
    # `RETRO_APPROVED_PROFILES` and its guards (review round 1, claim 5). Profiles are
    # opaque tokens and no cross-provider ordering exists, so a profile joins by being
    # named, never "or above".
    #
    # The escalation cell was the human ruling on #361 (2026-08-14), amending ruling 2:
    # arbitration is retro work, so the arbiter is drawn from #300's approved nine — and
    # deliberately not `fable-high`, the seat's own preference head and therefore the
    # profile most likely to have authored the rounds the arbiter would judge (#318: it
    # authored every one). The human's ruling of 2026-08-27 re-orders both cells and moves
    # the escalation head to `fable-xhigh`. That still satisfies ruling 4 — `fable-xhigh`
    # and `fable-high` are different profiles, and `review_same_profile` is about the
    # instance producing the verdict — but it is a narrower separation than #361's cell
    # had: the arbiter and the likely author now share a model, where A1's pair did not.
    # Both pairs are on `claude-native`, so no lane separation is lost and none existed;
    # what A1's cell avoided was the exact likely-author profile. Recorded rather than
    # argued, because the cell is the human's.
    "retro": Seat(
        "retro",
        claude_only=False,
        preference=("fable-high", "opus-xhigh", "codex-sol-max"),
        escalation=("fable-xhigh", "opus-max"),
        lands=True,
        owes_fix_round_report=True,
    ),
    # Absent from ADR-0071 ruling 2's table and therefore carrying no escalation entry, which
    # after A1 struck the blanket `fable-high` fallback means an escalation from this seat
    # resolves to nothing and refuses. That is the consequence the human accepted at the time
    # of ruling, not an oversight. The documentation half of the `fable`/`retro` overlap is
    # closed above by #329; the `/retro` skill's half is #330's.
    "fable": Seat("fable", claude_only=False, preference=("fable-high",), lands=False),
    # ADR-0071 ruling 1's one survivor, and the only `claude_only=True` row the table
    # carries: orchestration runs on Claude with a Claude model until a tested
    # alternative exists. The ADR calls it the only provenance rule the project holds.
    # The escalation cell is the human ruling on #361 (2026-08-14), amending ruling 2 —
    # and is not `opus-xhigh`, which is the seat itself: an orchestrator must not
    # arbitrate its own instruction, which is the #318 shape this cell exists to end.
    "orchestrator": Seat(
        "orchestrator",
        claude_only=True,
        preference=("opus-xhigh",),
        escalation=("opus-max", "fable-xhigh"),
        lands=False,
    ),
}

# ADR-0071 ruling 2's last row, which is **not a dispatch route**. ADR-0068 makes the
# interlocutor a slash command the human invokes in their own session, and ruling 2 does
# not reverse it — so the row is deliberately not in `SEATS`, where `resolve_seat` would
# walk it and `--seat interlocutor` would become a way of dispatching a seat nobody
# dispatches. It is registered here because the same table "governs the pair the seat's
# own surfaces declare", and `tools/generate_seats.py` needs one registry to read rather
# than a second copy of the row (#324). Nothing in this module resolves through it.
#
# `claude_only` is unread for a seat nothing dispatches; it is `False` because the row's
# own Codex entry is reachable by the human opening a Codex session by hand, and no
# refusal of this module's ever reaches this registry.
DECLARED_ONLY_SEATS: Final[dict[str, Seat]] = {
    # `lands=False` on the same ground as every undispatched judgement: ADR-0068 makes
    # the seat the human's own invocation, and nothing in this module resolves through
    # the row, so no brief is ever composed from it either.
    "interlocutor": Seat(
        "interlocutor",
        claude_only=False,
        preference=("opus-xhigh", "codex-sol-xhigh"),
        lands=False,
    ),
}


# #345's arrival guard. The exact-set pin in `tests/unit/test_dispatch_seat.py` cannot
# see an omitted `lands` column: a `bool = False` default would answer `False` before
# any assertion ran, which is the gap the cross-lane review found in the
# re-implementation — the banked branch had spelled the column on every row, and the
# persisted claim ("a new seat arrives decided") was written as if spelling were
# enforcement. It is not, and neither is the annotation: `bool | None` checks nothing
# at runtime, and this guard's first spelling refused only `is None`, so a truthy
# `1` passed it into a registry whose set pin reads truthiness while `brief.Seat.lands`
# composes `is True` — two surfaces disagreeing over a value the registry admitted,
# the fresh cross-lane review's blocker. `isinstance` admits exactly the two decided
# spellings (`bool` has no other instances and cannot be subclassed) and refuses
# everything else, `None` the omitted column included, and failing this module's
# import is the refusal, because every gate and every test run reaches it. A new seat
# spelling neither `True` nor `False` never reaches a brief.
def refuse_undecided_lands(seats: Mapping[str, Seat]) -> None:
    """Refuse a registry whose rows leave `lands` undecided, rather than defaulting it.

    Undecided is both spellings the column forbids: omitted (`None`, the default) and
    any value that is not exactly a boolean, which the annotation never checks.
    """
    undecided = [name for name, seat in seats.items() if not isinstance(seat.lands, bool)]
    if undecided:
        raise TypeError("seat(s) without a decided `lands` column: " + " ".join(undecided))


refuse_undecided_lands(SEATS)
refuse_undecided_lands(DECLARED_ONLY_SEATS)


# The standing retro allowance lived here until #327: two `(fable, codex, …)` routes
# suspending ADR-0061 Decision 2's seat bar for #300's ruled retro profiles. ADR-0071
# ruling 1 rescinds that bar, and its trailer supersedes #300's ruling outright — #326
# already deleted the policy half (the two standing `route_exceptions`). Nothing
# consults an allowance once no bar exists to suspend, so the constant, its source line
# and its predicate are deleted here rather than kept as data nothing reads. Of the
# `fable`/`retro` seat overlap that ruling 3 leaves behind, #329 closed the documentation
# half and #330 owns the `/retro` skill's.


def escalation_head(seat_name: str) -> str | None:
    """Return the arbiter ADR-0071 ruling 4 names for work done at `seat_name`, or `None`.

    Ruling 4 as amendment A1 leaves it: *the head of the **implementing** seat's escalation
    entry* — whichever seat did the work, not the `implementer` row specifically. Callers that
    need an arbiter ask here rather than reading `IMPLEMENTER_ESCALATION[0]`, which was the
    reading A1 reversed and which answers every seat with the implementer's head.

    `None` where the seat registers no entry, and deliberately no fallback: A1 struck the
    blanket `fable-high` default, so a seat with no entry resolves to nothing and refuses
    rather than reaching a profile nobody chose. `None` is also the answer for an unknown seat
    — a name that resolves to no row cannot have an arbiter derived for it, and inventing one
    is the act the amendment exists to stop.

    What this does **not** do is resolve an arbiter. That is ruling 4's walk over the records,
    which needs records a caller here does not hold, and it is **built**, in `tools/arbiter.py`
    — **the one place what it does is stated, this docstring included** (#390). The version of
    this paragraph that described the walk instead said it was unbuilt and cited, as its
    authority, the ADR passage the same round had rewritten to say the opposite; it stood
    outside two sweeps' enumerations, which is the arbitration of 2026-08-15 on #361 and this
    pointer's whole reason. This function returns
    the tabled head alone, which is that walk's input and `tools/brief.py`'s briefing field:
    a briefing states who the table names, which is not the same act as resolving an arbiter
    at an escalation (ADR-0071 ruling 4, amendment A1's third pass, closing sentence).
    """
    seat = SEATS.get(seat_name)
    if seat is None or not seat.escalation:
        return None
    return seat.escalation[0]


def plan_charge(lane: Lane, at: datetime) -> dict[str, object] | None:
    """Record what this dispatch is charged at, in the unit its provider's plan meters.

    z.ai meters *prompt counts*, not tokens, and halves them outside its published peak
    band — the arbitrage ADR-0061 names and #226's estimator is meant to exploit. The
    band is `tools/breaker.py`'s to state and is not restated here, because the schedule
    that prices a dispatch and the one that refuses it (#238) must be one object. Two
    things a later reader cannot recover are written down here:
    which band this dispatch fell in, and what multiplier that band carried. Both are
    functions of `planned_at` *today*, but they are functions of a published schedule
    that can move, and a record carrying only the timestamp would silently re-price its
    own history the first time it did.

    This records the discount. It does not chase it: nothing here delays, queues or
    reorders a dispatch to land off-peak, which is #226's scheduler and deliberately
    not #225's.

    `None` on a lane whose plan is not metered this way, because a lane with no
    time-of-day term must not carry a block asserting a multiplier of 1.0 — that would
    read as "measured, and it was peak" rather than "the question does not arise".
    """
    schedule = breaker.LANE_SCHEDULES.get(lane.name)
    if schedule is None:
        return None
    peak = schedule.is_peak(at.timestamp())
    return {
        "meter": schedule.meter,
        "peak": peak,
        "multiplier": 1.0 if peak else schedule.off_peak_multiplier,
        "schedule": schedule.name,
        "window": schedule.window,
        "window_source": schedule.source,
    }


class PassedOver(NamedTuple):
    """One preference entry a seat's resolution walked past, and what refused it."""

    profile: str
    refusal: str
    failure_class: str = ""

    def line(self, key: str) -> str:
        """Render the entry under a caller's key, carrying its own class where it had one."""
        classed = f" class={self.failure_class}" if self.failure_class else ""
        return f"{key}={self.profile} refusal={self.refusal}{classed}"


class Authorship(NamedTuple):
    """Which profiles an issue's records place on its work: a *potential* author set (#322).

    Never a finding that any of them wrote a line of it.

    `potential_authors` below is what fills this in and carries the reasoning; it lives here,
    above `Resolution`, only because `Resolution` carries one as a default.

    **`potential` is not "the authors".** A dispatch record is written at plan time and says
    which profile was sent at which issue on which seat. Nothing on it says whether that run
    produced a commit, so a planner, a recon, a run stopped before it edited anything, a
    successful no-op and a dispatch against a branch this one supersedes all leave the same
    record as the implementer that wrote the diff. What this set is, therefore, is the set
    the records cannot rule out — which is exactly the right shape for the one thing it
    decides: every entry is removed from the review seat's candidate list, because
    over-excluding costs a resolution step and under-excluding costs ruling 4's invariant.

    `why` is why the set may not be treated as the whole answer — the directory is absent, no
    record on this issue could have authored anything, or a record could not be read. It is
    populated **alongside** `potential` rather than instead of it: a scan that read four
    records and could not read a fifth still excludes those four, and still must not report
    itself as checked (#41 — a check that could not run is not a check that passed).

    `records` names where each profile was read, in the order they were read, so a reader
    shown `potential_authors=` can go and look at the same records rather than take this
    scan's word for it. An entry is a dispatch id for a profile the dispatch records placed
    on the work, and the path of an issue's `authorship.json` for one an interactive session
    declared (#398) — the two sources assert different things, and the entry beside the
    profile is what says which one this name came from.
    """

    potential: tuple[str, ...] = ()
    records: tuple[str, ...] = ()
    why: str = ""

    @property
    def complete(self) -> bool:
        """Whether every record read cleanly and at least one of them names a profile.

        The only state in which the declared subject can be *checked* against the records at
        all. Every other state is unchecked, and is recorded as unchecked rather than
        allowed to read as a pass.
        """
        return bool(self.potential) and not self.why


# The empty read, named once so it can be a default argument without being rebuilt at every
# call — and so that "this seat has no subject to check" is one object rather than a literal
# repeated at four signatures.
NO_AUTHORSHIP: Final = Authorship()

# The three states a scan of the records can leave behind, named because a second module now
# reads them (#398). The first two mean "no record placed anybody on this work"; the third
# means a record would not open, which is a different fact and stays a refusal wherever it
# appears — a declared author adds to what was read and never repairs what could not be.
NO_DISPATCH_RECORDS: Final = "no_dispatch_records"
NO_AUTHORING_DISPATCH: Final = "no_authoring_dispatch"
RECORDS_UNREADABLE: Final = "records_unreadable"


def with_declared_authors(
    authorship: Authorship, declared: tuple[str, ...], record: str
) -> Authorship:
    """Add the authors an interactive session declared to what the dispatch records said (#398).

    **Why there is a second source at all.** #294 bars a dispatched session from writing
    under `.claude/`, so a change there can only be authored interactively — and an
    interactive session writes no dispatch record, so `potential_authors` returned an empty
    set for every one of them and the landing's never-alone rung refused it
    (`authorship_unrecorded`, correctly: an empty set clears the very arrangement the
    criterion exists to catch). The rung's logic is unchanged. What this supplies is the
    non-empty set for the one case the records genuinely cannot speak to.

    **It asserts less than a dispatch record, and the difference is carried rather than
    erased.** A dispatch record's profile is what the dispatcher resolved and exported into
    the child's environment; a declared one is the recording session's own word. So the
    merge only ever *adds* names — every added name is one more profile a reviewer may not
    be — and the caller prints the declared ones as declared beside the clearance.

    **`why` is cleared for the two empty states and never for the unreadable one.** With a
    declared author the set is no longer empty and nothing went unread, so the scan is
    complete; a record that would not open is still a record that would not open, and #41's
    rule holds over it whatever anybody declares.
    """
    added = tuple(profile for profile in declared if profile not in authorship.potential)
    if not added:
        return authorship
    empty = authorship.why in (NO_DISPATCH_RECORDS, NO_AUTHORING_DISPATCH)
    return Authorship(
        potential=authorship.potential + added,
        records=authorship.records + tuple(record for _ in added),
        why="" if empty else authorship.why,
    )


def _authorship_record_source(record: str) -> str:
    """Name the source kind encoded by one entry in ``Authorship.records``."""
    if Path(record).name == review_loop.AUTHORSHIP_FILE:
        return review_loop.DECLARED
    return "dispatch"


def potential_author_provenance(authorship: Authorship) -> str:
    """Render each potential profile beside the record that put it in the set."""
    return " ".join(
        f"{profile} source={_authorship_record_source(record)} record={record}"
        for profile, record in zip(authorship.potential, authorship.records, strict=True)
    )


class Resolution(NamedTuple):
    """Which profile this dispatch runs on, and why that one (ADR-0071 ruling 2, #321).

    Two shapes, and the difference is recorded rather than erased: a caller who named a
    profile chose it, and a caller who named only a seat had it chosen for them from the
    seat's ordered preference. Both are routes and both are subject to every
    `(profile, seat)` refusal — naming a profile is a way of choosing and never a way
    around a block — so the distinction the record keeps is *provenance of the choice*,
    which is what attributing an outcome later needs.
    """

    seat: str
    profile: str
    lane: str
    named: bool
    passed_over: tuple[PassedOver, ...] = ()
    # The profile whose work this dispatch reviews, empty on every seat that reviews none
    # (#322). On the route rather than only on the command line because ADR-0071 ruling 4's
    # landing check has to be able to ask, later and from the record alone, whether the
    # instance that produced a verdict was the instance that produced the change.
    reviewed: str = ""
    # What the issue's dispatch records could say about who worked on it (#322). A potential
    # author set and never a finding of authorship: every entry is excluded from the
    # candidate list, and the declared subject is *checked* against the set rather than
    # verified by it. The empty default is every seat that reviews nothing.
    authorship: Authorship = NO_AUTHORSHIP

    def lines(self) -> tuple[str, ...]:
        """Render the route as the lines a reader gets: the profile, and why this one."""
        if self.named:
            head = (f"route=profile profile={self.profile} lane={self.lane}",)
        else:
            head = (
                f"route=seat seat={self.seat}",
                # The list *this* dispatch walks, which on the review seat is the seat's
                # preference with every potential author removed and a different lane put
                # first. Printing the raw preference here would show a reader an order
                # resolution did not use, and one containing a profile it refused to use.
                "route_preference="
                + " ".join(review_candidates(SEATS[self.seat], self.reviewed, self.authorship)),
                *(entry.line("route_passed_over") for entry in self.passed_over),
                f"route_chosen={self.profile} lane={self.lane}",
            )
        return (*head, *self.containment_lines())

    def containment_lines(self) -> tuple[str, ...]:
        """Render what the seat forced on this dispatch, on both routes and never silently.

        Forcing a caller's permission mode is the right mechanism and a bad thing to do
        quietly: a reader who typed `--permission-mode acceptEdits` and got a read-only run
        should be able to see, in the dispatch's own output, that a seat overrode them and
        which seat it was.
        """
        seat = SEATS[self.seat]
        lines = []
        if self.reviewed:
            lines.append(f"route_reviewing={self.reviewed} (never resolved to)")
            lines.append(self.subject_line())
        if seat.permission_mode:
            lines.append(
                f"route_permission_mode={seat.permission_mode}"
                f" forced_by_seat={seat.name} (no caller override)"
            )
        return tuple(lines)

    def subject_line(self) -> str:
        """Say whether the declared subject was checked against the records, or why it was not.

        Printed on every review dispatch, both routes, because "the caller said so" and "the
        records do not contradict it" are different facts and a reader who cannot tell them
        apart has the same guarantee the declaration alone gave, which is none.

        **`checked`, deliberately, and never `verified`.** What a complete read supports is
        that the declared subject is among the profiles the records place on this issue's
        work, and that every one of those profiles was removed from the candidate list. It
        does not support "this profile wrote the commits", which is not on the record at all
        — `potential_authors` states the gap and where closing it belongs.

        **The printed set is `excluded_from_review`'s, not a second derivation of it.** The
        line a reader gets and the exclusion resolution performed have to be the same set, or
        they can drift; the declared subject was missing from this line for exactly that
        reason. On a complete read the two are equal anyway — `contradicted_refusal` fires
        above here unless the declaration is among the potential authors — so what the fix
        actually changes is the unchecked route, where the declaration is excluded and used
        to say so. Sorted, matching `same_profile_refusal`'s rendering of the same set, so
        one set has one spelling wherever it is printed.
        """
        excluded = " ".join(sorted(excluded_from_review(self.reviewed, self.authorship))) or "none"
        if self.authorship.complete:
            return (
                f"route_reviewing_checked=yes potential_authors={excluded}"
                f" records={' '.join(self.authorship.records)}"
                " (all excluded from the candidate list; not a finding that any of them"
                " wrote the diff)"
            )
        return (
            f"route_reviewing_checked=no why={self.authorship.why or 'not_checked'}"
            f" excluded_anyway={excluded}"
            " (the caller's declaration, unchecked; ADR-0071 ruling 4's landing check"
            " refuses on this)"
        )

    def document(self) -> dict[str, object]:
        """Render the route for the dispatch record, passed-over entries and all."""
        return {
            "named": self.named,
            "seat": self.seat,
            "chosen": self.profile,
            "lane": self.lane,
            "reviewing": self.reviewed,
            # Written as its own boolean rather than left for a reader to infer from an empty
            # list: #334's landing check greps a record for "was this review's subject
            # checked", and an absence is what a record written before #322 also has. It says
            # *checked* and not *verified* — `subject_line` for the difference, which is the
            # difference between what the records support and what a reader would assume.
            "reviewing_checked": self.authorship.complete,
            "reviewing_potential_authors": list(self.authorship.potential),
            "reviewing_potential_author_records": list(self.authorship.records),
            "reviewing_unchecked_why": self.authorship.why,
            "passed_over": [
                {
                    "profile": entry.profile,
                    "refusal": entry.refusal,
                    "failure_class": entry.failure_class,
                }
                for entry in self.passed_over
            ],
        }


def read_route(document: Mapping[str, object]) -> Resolution:
    """Read a route back off a dispatch record, so a reloaded plan is the plan that was written.

    A record written before this field existed reads back as the named route it was: the
    seat, profile and lane it already carries, with nothing passed over. That is what those
    dispatches were — every one of them named its profile, because naming it was the only
    way to dispatch — so the fallback states a fact rather than papering over a gap.

    A record written before #322 carries no reviewed profile, and reads back with none. It
    is a fact about those dispatches too: no review before this landed declared its subject,
    which is why the ADR calls same-model review the finding it does.
    """
    found = document.get("route")
    route = found if isinstance(found, dict) else {}
    entries = route.get("passed_over", ())
    return Resolution(
        seat=str(route.get("seat", document["seat"])),
        profile=str(route.get("chosen", document["profile"])),
        lane=str(route.get("lane", document["lane"])),
        named=bool(route.get("named", True)),
        reviewed=str(route.get("reviewing", "")),
        # `reviewing_checked` is not read back: it is `potential` being non-empty with no
        # `why`, and one fact stored twice is one fact that can disagree with itself. A record
        # written before this landed reads back as unchecked with no reason, which is what it
        # was.
        authorship=Authorship(
            potential=tuple(str(name) for name in route.get("reviewing_potential_authors", ())),
            records=tuple(
                str(name) for name in route.get("reviewing_potential_author_records", ())
            ),
            why=str(route.get("reviewing_unchecked_why", "")),
        ),
        passed_over=tuple(
            PassedOver(
                str(entry["profile"]), str(entry["refusal"]), str(entry.get("failure_class", ""))
            )
            for entry in entries
        ),
    )


class Identity(NamedTuple):
    """What a dispatch is, as the six attributes that make its telemetry self-describing."""

    dispatch_id: str
    lane: str
    profile: str
    seat: str
    issue: int
    base_sha: str

    def attributes(self) -> tuple[tuple[str, str], ...]:
        """Return the `cti.*` pairs, in the order they are written."""
        return (
            ("cti.dispatch_id", self.dispatch_id),
            ("cti.lane", self.lane),
            ("cti.profile", self.profile),
            ("cti.seat", self.seat),
            ("cti.issue", str(self.issue)),
            ("cti.base_sha", self.base_sha),
        )


# A record written before #323 carries none of these, so the default is the honest reading
# of that: nothing recorded, nothing checked. Named once so the Plan default and `read_strata`
# share one object, the way `NO_AUTHORSHIP` does for the route.


class RoutingClass(NamedTuple):
    """A policy class the issue matched at dispatch time: its stable id and its name.

    Recorded as two fields rather than an `id:name` string (#323 review finding 6): the id
    is stable and the name is mutable, so flattening them would fragment the stratification
    history the observatory (#336) reads across a class rename. The matched-no-rule case is
    `RoutingClass("", "")` — a checked absence, kept distinct from `None`, which means the
    policy could not be read at all.
    """

    rule_id: str
    name: str


# --------------------------------------------------------- the strata degradation codes (#347)
#
# The typed discriminator #336 stratifies on. Plain module-level strings rather than an `Enum`,
# for the reason `escalation.Evaluation` records: a module re-exec (the production `__main__`
# shape beside a test's `load_tool` copy) gives two class objects, so an `Enum` member from one
# copy compares unequal to the same member from the other, while `"pre_strata_absent"` is
# `"pre_strata_absent"` in every copy. A consumer narrows on the string.
#
# Every degradation state gets its own code, and `unchecked_why` stays diagnostic prose — never a
# grouping key. That is the whole of #347: #323 left the states apart only by their reasons, which
# is four examples that happen not to collide rather than a contract, and `Stratum.unknown("")`
# collided exactly with pre-#323 absence.
STRATUM_CHECKED: Final = "checked"
STRATUM_SOURCE_UNAVAILABLE: Final = "source_unavailable"
STRATUM_PRE_STRATA_ABSENT: Final = "pre_strata_absent"
STRATUM_CONTAINER_NOT_MAPPING: Final = "container_not_mapping"
STRATUM_UNCHECKED_WITH_VALUE: Final = "unchecked_with_value"
STRATUM_RECORD_MALFORMED: Final = "record_malformed"
STRATUM_VALUE_FIELDS_ABSENT: Final = "value_fields_absent"
STRATUM_VALUE_MALFORMED: Final = "value_malformed"

# Every code this recorder writes, and the ones legal beside `checked=False`. `checked` is the
# only code a checked stratum may carry, and it is the only one an unchecked stratum may not:
# the flag and the code cannot disagree, because `__post_init__` refuses the pair.
STRATUM_CODES: Final = (
    STRATUM_CHECKED,
    STRATUM_SOURCE_UNAVAILABLE,
    STRATUM_PRE_STRATA_ABSENT,
    STRATUM_CONTAINER_NOT_MAPPING,
    STRATUM_UNCHECKED_WITH_VALUE,
    STRATUM_RECORD_MALFORMED,
    STRATUM_VALUE_FIELDS_ABSENT,
    STRATUM_VALUE_MALFORMED,
)
STRATUM_UNCHECKED_CODES: Final = tuple(code for code in STRATUM_CODES if code != STRATUM_CHECKED)


@dataclass(frozen=True)
class Stratum:
    """One pre-work signal: its value, whether that value was checked, and why not if not.

    The value is `None` when the signal did not run (#323 review finding 1): a consumer that
    ignores `checked` and reads `value` then gets no answer rather than a plausible wrong one,
    and `unchecked_why` still says why. The three signals below each carry one of these, so the
    three-part invariant — a value beside a flag beside a reason — lives in one type rather
    than being rebuilt at every layer (#323 review finding 5), and `read_strata` has one reader
    that validates it rather than three readers that coerce (#323 review finding 2).
    """

    value: object
    checked: bool
    unchecked_why: str
    code: str

    def __post_init__(self) -> None:
        """Refuse an unchecked stratum that carries a value, or a code the flag contradicts.

        A signal that did not run carries no value, so an unchecked stratum cannot be built
        with one (#323 review round 2 finding 1). The record boundary does not have to
        re-assert this — `document()` can write `value` unconditionally because nothing can
        put a real value beside `checked=False`. A frozen dataclass refuses the bad shape at
        construction; `known`, `unknown` and the reader all build through this, so the
        invariant is the type's, not a guard's.

        The code is held to the same standard (#347). It must be one this recorder writes, and
        it must agree with the flag: `checked` exactly when `checked=True`, one of the
        degradation codes exactly when `checked=False`. A discriminator a writer could set to
        anything would be no better a grouping key than the prose it replaces.
        """
        if not self.checked and self.value is not None:
            message = "an unchecked Stratum carries no value (F1)"
            raise ValueError(message)
        if self.code not in STRATUM_CODES:
            message = f"unknown Stratum code {self.code!r} (#347)"
            raise ValueError(message)
        if self.checked != (self.code == STRATUM_CHECKED):
            message = f"Stratum code {self.code!r} contradicts checked={self.checked} (#347)"
            raise ValueError(message)

    @classmethod
    def known(cls, value: object) -> Stratum:
        """Build the stratum for a signal that ran: checked, with its value and no reason.

        The empty value is a value, not an absence — an empty label tuple means the issue
        carries no labels, and is checked-True where 'could not look' is checked-False.
        """
        return cls(value=value, checked=True, unchecked_why="", code=STRATUM_CHECKED)

    @classmethod
    def unknown(cls, why: str, code: str = STRATUM_SOURCE_UNAVAILABLE) -> Stratum:
        """Build the stratum for a signal that could not run: unchecked, value None, reason kept.

        The code defaults to `source_unavailable`, which is what every capture-time unchecked
        signal is: a source the check needed — CONTEXT.md, the routing policy, `gh` — could not
        be read. The reader passes the degradation code it derived instead.
        """
        return cls(value=None, checked=False, unchecked_why=why, code=code)


class Strata(NamedTuple):
    """The pre-work signals the observatory stratifies on (#323).

    Each signal is a `Stratum` carrying #322's checked flag beside its value. The observatory
    compares profiles on assignment that is not random, so a confident value standing alone
    cannot tell 'the issue has none' from 'nobody could look' — and an unstratified comparison
    that read the two the same would measure the router and report it as a profile finding.
    Everything here is knowable before the seat starts work: the gate tier off the issue body
    and CONTEXT.md, the routing class off the body and the policy, the labels off GitHub.
    Nothing on this record is an outcome (diff size, review rounds, result), and #323 criterion
    3 is satisfied by that absence rather than by a marking — there is no outcome-shaped field
    here to mark as description.
    """

    gate_tier: Stratum
    routing_class: Stratum
    labels: Stratum

    def document(self) -> dict[str, object]:
        """Render each signal with its flag, reason, and a null value when it did not run.

        An unchecked signal writes `None` for its value, never a value a checked run could have
        written, so the absent-versus-unchecked distinction cannot collapse for a consumer that
        reads only the value (#323 review finding 1). The routing class records its stable id
        and its mutable name as separate fields, so a class rename cannot fragment the history
        the observatory reads (#323 review finding 6).
        """
        routing = self.routing_class.value
        labels = self.labels.value
        return {
            "gate_tier": self.gate_tier.value,
            "gate_tier_checked": self.gate_tier.checked,
            "gate_tier_unchecked_why": self.gate_tier.unchecked_why,
            "gate_tier_code": self.gate_tier.code,
            "routing_class_id": routing.rule_id if isinstance(routing, RoutingClass) else None,
            "routing_class_name": routing.name if isinstance(routing, RoutingClass) else None,
            "routing_class_checked": self.routing_class.checked,
            "routing_class_unchecked_why": self.routing_class.unchecked_why,
            "routing_class_code": self.routing_class.code,
            "labels": list(labels) if isinstance(labels, tuple) else None,
            "labels_checked": self.labels.checked,
            "labels_unchecked_why": self.labels.unchecked_why,
            "labels_code": self.labels.code,
        }


def _valueless_stratum(why: str, code: str) -> Stratum:
    """Build the value-less unchecked stratum without running the validator.

    `NO_STRATA`'s signals are unchecked by definition and carry no value, so the validator has
    nothing to check — and running it at import would make the type's own invariant un-testable:
    a mutant that inverts `__post_init__`'s check raises while `NO_STRATA` is still being built,
    crashing collection before any test can score the mutant as a kill. This private path skips
    the validator. It takes no value, so it cannot build the shape F1 refuses; its fields are
    identical to `Stratum.unknown(why, code)`. It bypasses `__init__` with `object.__new__` plus
    direct field setting because a frozen dataclass refuses ordinary assignment.
    """
    obj = object.__new__(Stratum)
    object.__setattr__(obj, "value", None)
    object.__setattr__(obj, "checked", False)
    object.__setattr__(obj, "unchecked_why", why)
    object.__setattr__(obj, "code", code)
    return obj


# `NO_STRATA` is built at import through `_valueless_stratum`, not `Stratum.unknown`: the
# constant is constructed while the module loads, and a mutant inverting `__post_init__`'s
# check would raise inside `unknown` while this line ran — crashing collection before any test
# could score the mutant. `_valueless_stratum` skips the validator (it takes no value, so it
# cannot build the shape F1 refuses), so the module imports under every mutant and the
# validator stays scoreable. Its fields are identical to `unknown("", STRATUM_PRE_STRATA_ABSENT)`,
# and that code is what makes the pre-#323 absence tell itself apart from an ordinary unchecked
# signal whose reason happens to be empty — the exact collision #347 was filed for.
NO_STRATA: Final = Strata(
    gate_tier=_valueless_stratum("", STRATUM_PRE_STRATA_ABSENT),
    routing_class=_valueless_stratum("", STRATUM_PRE_STRATA_ABSENT),
    labels=_valueless_stratum("", STRATUM_PRE_STRATA_ABSENT),
)


# A value the reader cannot make sense of. A sentinel rather than `None`, because `None` is
# the legitimate value of an unchecked signal and a validator must tell 'wrong shape' from
# 'no value'.
_MALFORMED: Final = object()


def _read_signal(  # noqa: PLR0913 — keyword-only validator mirroring the per-signal value/checked/why triple
    row: Mapping[str, object],
    *,
    value_keys: tuple[str, ...],
    checked_key: str,
    why_key: str,
    code_key: str,
    decode_value: Callable[[tuple[object, ...]], object],
    label: str,
) -> Stratum:
    """Read one signal back off a record, validating rather than coercing (#323 review finding 2).

    `decode_value` receives the raw values at `value_keys` and returns the decoded value, or
    `_MALFORMED` if they are not the shape this signal writes. A record the reader cannot make
    sense of — a checked flag that is not a bool, a checked signal whose value is missing or the
    wrong type, a reason that is not a string — comes back unchecked with a reason, never as a
    confident value and never as an exception. That is the property `str(None)` giving `"None"`,
    `bool("false")` giving `True`, `"labels": "bug"` giving `("b","u","g")` and a null label list
    raising `TypeError` all break, and one reader holds it for all three signals.

    Two shapes that are not corruption get their own reasons. A record that contradicts itself —
    a value beside `checked: false`, which F1 never writes — reads back unchecked *and names what
    it saw*, so the contradiction leaves a trace rather than a silent empty reason (review round 2
    finding 2). That naming is done before the reason's type is inspected, so a missing or
    non-string reason beside a carried value still names the value — otherwise the very thing F2
    exists to surface is lost to a generic "malformed" (review round 3 finding 2). And a record
    whose value fields this reader does not carry at all is told apart
    from a broken one: the only records in that shape are this branch's own earlier format, never
    a landed one, so it says the fields are absent rather than that the record is malformed (review
    round 2 finding 4 — no migration, because nothing landed in that shape).
    """
    checked = row.get(checked_key)
    why = row.get(why_key)
    raw_values = tuple(row.get(key) for key in value_keys)
    # An unchecked signal carrying a value contradicts F1, which writes `None` for an unchecked
    # value. Name the carried value so the contradiction leaves a trace — and do it before the
    # reason's type is inspected: a record carrying a value beside `checked: false` with a
    # missing or non-string reason must still name what it saw, or the value F2 exists to
    # surface is lost to a generic "malformed" (review round 3 finding 2). The reason is now
    # diagnostic only: what keeps this state apart from a present non-mapping container, a
    # record carrying none of the value fields, and the plain pre-#323 absence is the typed
    # `code`, not the English (#347). The value is still named because a reader debugging a
    # contradicted record wants to see what was there.
    if checked is False and any(part is not None for part in raw_values):
        seen = raw_values[0] if len(raw_values) == 1 else raw_values
        return Stratum.unknown(
            f"the recorded {label} stratum was unchecked but carried {seen!r}",
            STRATUM_UNCHECKED_WITH_VALUE,
        )
    if not isinstance(checked, bool) or not isinstance(why, str):
        return Stratum.unknown(
            f"the recorded {label} stratum was malformed", STRATUM_RECORD_MALFORMED
        )
    if not checked:
        # F1 writes `None` for an unchecked value; the reason is the thing to keep — as prose,
        # never as the key. The *code* is the key, and this is the one branch that takes it off
        # the record rather than deriving it: an ordinary unchecked signal and a record written
        # from `NO_STRATA` are structurally identical here (unchecked, no value, and a reason
        # that may be empty on both), so the recorded discriminator is the only thing that tells
        # them apart, and honouring it is what makes the record round-trip. A record predating
        # the field, or carrying a code this recorder does not write, falls back to the derived
        # `source_unavailable` — never to the reason's text (#347).
        recorded = row.get(code_key)
        code = recorded if recorded in STRATUM_UNCHECKED_CODES else STRATUM_SOURCE_UNAVAILABLE
        return Stratum.unknown(why, str(code))
    decoded = decode_value(raw_values)
    if decoded is _MALFORMED:
        if all(key not in row for key in value_keys):
            # None of the value fields this reader expects are present: the record was written
            # in an earlier shape (the flattened `routing_class` string before the split). Say
            # the fields are absent, not that the record is broken — it was valid in the shape
            # it was written in (review round 2 finding 4).
            return Stratum.unknown(
                f"the recorded {label} stratum carries none of the value fields this reader reads",
                STRATUM_VALUE_FIELDS_ABSENT,
            )
        return Stratum.unknown(
            f"the recorded {label} stratum's value was not in the shape this reader expects",
            STRATUM_VALUE_MALFORMED,
        )
    return Stratum.known(decoded)


def _gate_tier_value(raw: tuple[object, ...]) -> object:
    value = raw[0]
    return value if isinstance(value, str) else _MALFORMED


def _routing_class_value(raw: tuple[object, ...]) -> object:
    rule_id = raw[0]
    name = raw[1]
    if isinstance(rule_id, str) and isinstance(name, str):
        return RoutingClass(rule_id, name)
    return _MALFORMED


def _labels_value(raw: tuple[object, ...]) -> object:
    value = raw[0]
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return _MALFORMED


def read_strata(document: Mapping[str, object]) -> Strata:
    """Read the strata back off a record, so a reloaded plan is the plan that was written.

    Every stratum this returns carries a typed `code` (#347): the discriminator #336 stratifies
    on, distinct per degradation state and derived from the record's raw structure, so a record
    predating the field classifies without being rewritten. `unchecked_why` is diagnostic prose
    beside it and must never be a grouping key — #323 left the states apart only by their
    reasons, and `Stratum.unknown("")` then collided exactly with pre-#323 absence.

    A record written before #323 carries none of these fields and reads back unchecked:
    nothing was recorded, so nothing was checked — the fact those dispatches carry about every
    field #323 added, rather than a guess dressed as one. A record that carries them in a shape
    this reader cannot make sense of degrades the same way, to unchecked with a reason, rather
    than coercing a confident value out of malformed data.
    """
    if "strata" not in document:
        # No strata field at all is the pre-#323 record: the field did not exist, so nothing
        # was recorded and nothing was checked, with no reason to give. This is the only case
        # that reads back as `NO_STRATA`.
        return NO_STRATA
    found = document["strata"]
    if not isinstance(found, dict):
        # Present but not a mapping — `[]`, `null`, `"x"` — is a malformed container, not a
        # pre-#323 record, and it never reaches the per-field reader below. Give every signal
        # the same reason so 'nobody recorded anything' (no field) stays distinct from 'the
        # recording was broken' (a present non-mapping) (review round 2 finding 3).
        reason = "the recorded strata object was present but not a mapping"
        return Strata(
            gate_tier=Stratum.unknown(reason, STRATUM_CONTAINER_NOT_MAPPING),
            routing_class=Stratum.unknown(reason, STRATUM_CONTAINER_NOT_MAPPING),
            labels=Stratum.unknown(reason, STRATUM_CONTAINER_NOT_MAPPING),
        )
    row = found
    return Strata(
        gate_tier=_read_signal(
            row,
            value_keys=("gate_tier",),
            checked_key="gate_tier_checked",
            why_key="gate_tier_unchecked_why",
            code_key="gate_tier_code",
            decode_value=_gate_tier_value,
            label="gate_tier",
        ),
        routing_class=_read_signal(
            row,
            value_keys=("routing_class_id", "routing_class_name"),
            checked_key="routing_class_checked",
            why_key="routing_class_unchecked_why",
            code_key="routing_class_code",
            decode_value=_routing_class_value,
            label="routing_class",
        ),
        labels=_read_signal(
            row,
            value_keys=("labels",),
            checked_key="labels_checked",
            why_key="labels_unchecked_why",
            code_key="labels_code",
            decode_value=_labels_value,
            label="labels",
        ),
    )


class Plan(NamedTuple):
    """Everything the detached child needs, and nothing it must not write down."""

    identity: Identity
    worktree: Path
    record: Path
    argv: tuple[str, ...]
    credentials: Path
    permission_mode: str
    # Which profile this dispatch runs on and how that was decided (#321). On the record
    # rather than only on stdout for the reason the advisories below are: an attribution
    # nobody kept is one nobody can make later, and "which entries did this seat walk past,
    # and on what refusal" is exactly what the ledger cannot reconstruct from an outcome.
    route: Resolution
    # The instant this dispatch was planned at, carried rather than re-read (#341). The
    # caller already injects `now` and the whole ladder above decides on it, so a record
    # that asked the wall clock a second time could disagree with the decision it records
    # — an off-peak refusal filed against a record claiming peak, at a band boundary. It
    # is also what made `just fast` red for the four hours a day z.ai is in peak, because
    # the routing argument and the recorded charge were two different instants.
    planned_at: datetime
    breaker_dir: Path = breaker.DEFAULT_BREAKER_DIR
    # What the readiness rung said about the issue without refusing it (#241). On the
    # record rather than only on stdout, because an advisory nobody kept is an advisory
    # nobody can count later — and counting them is how this project will know whether
    # the enumerability sub-check ever earns a hard refusal.
    advisories: tuple[str, ...] = ()
    # What the routing rung said when it did *not* refuse (#326, review round 2 claim 5).
    # Deliberately its own field rather than more `advisories`: an advisory is a readiness
    # finding about the issue, and this is a verdict about the route — folding them together
    # would file it under `readiness_advisories` on the record, where a later reader counting
    # readiness advisories would count routing lines among them.
    routing: tuple[str, ...] = ()
    # The pre-work strata the observatory compares profiles on (#323). On the record
    # rather than reconstructed afterwards, because reconstruction from an outcome is the
    # confound the observatory exists to remove: a gate tier read off the diff would put
    # the router's assignment back into a profile finding in a subtler form.
    strata: Strata = NO_STRATA
    # A successful Codex instruction-delivery preflight, recorded before the child is
    # forked. Claude has no equivalent bounded prompt-capture surface, so this is absent
    # for its lanes rather than a claim that the two providers expose the same proof.
    guidance: codex_guidance.GuidanceProof | None = None
    # Review and recon plans own their tree for exactly one dispatch. This is recorded
    # rather than inferred during cleanup: missing proof refuses instead of risking a
    # different holder's worktree.
    disposable_worktree: bool = False
    worktree_ref: str = ""

    def document(self) -> dict[str, object]:
        """Render the dispatch record, which names the credential key and never its value."""
        lane = LANES[self.identity.lane]
        document: dict[str, object] = {
            "dispatch_id": self.identity.dispatch_id,
            "lane": self.identity.lane,
            "profile": self.identity.profile,
            "seat": self.identity.seat,
            "issue": self.identity.issue,
            "base_sha": self.identity.base_sha,
            "worktree": str(self.worktree),
            "disposable_worktree": self.disposable_worktree,
            "worktree_ref": self.worktree_ref,
            "worktree_owner": self.identity.dispatch_id if self.disposable_worktree else "",
            "argv": list(self.argv),
            "permission_mode": self.permission_mode,
            "credential": lane.credential,
            "credentials_file": str(self.credentials),
            "breaker_dir": str(self.breaker_dir),
            "route": self.route.document(),
            "readiness_advisories": list(self.advisories),
            "routing_clearance": list(self.routing),
            "strata": self.strata.document(),
            "resource_attributes": dict(self.identity.attributes()),
            "plan_charge": plan_charge(lane, self.planned_at),
            "planned_at": self.planned_at.isoformat(),
        }
        launch_directory = codex_guidance.ResolvedLaunchDirectory.in_repository(
            self.worktree, self.worktree
        )
        if launch_directory is None:
            message = "dispatch worktree cannot construct a resolved launch directory"
            raise ValueError(message)
        if self.guidance is not None:
            if lane.runner_family is not codex_guidance.GuidanceHarness.CODEX:
                message = "a Codex proof cannot construct a Claude Code manifest"
                raise ValueError(message)
            # The manifest is derived from #502's one Codex capture. Keep the proof under
            # its landed key as a compatibility alias; neither field starts a second capture.
            delivery = self.guidance.document()
            document["instruction_delivery"] = delivery
            manifest: codex_guidance.GuidanceManifest = self.guidance.manifest()
        elif lane.runner_family is codex_guidance.GuidanceHarness.CODEX:
            # `write_record` follows successful preflight, so this branch is a typed impossible
            # state rather than an empty successful manifest if another caller bypasses it.
            manifest = codex_guidance.MissingGuidanceManifest(launch_directory)
        else:
            manifest = codex_guidance.UnattributableGuidanceManifest(launch_directory)
        document["guidance_manifest"] = manifest.document()
        return document


def mint_dispatch_id(now: datetime, entropy: str) -> str:
    """Mint a dispatch id inside the alphabet the collector and Claude Code both require."""
    return f"d-{now.strftime('%Y%m%d-%H%M%S')}-{entropy}"


def resource_attributes(identity: Identity, inherited: str) -> str:
    """Build `OTEL_RESOURCE_ATTRIBUTES`, keeping the parent's own keys and dropping its `cti.*`.

    A parent's `cti.*` must never survive into a child: two dispatches carrying one
    dispatch id is a ledger that cannot be joined. Anything else the box sets — a team
    or cost-centre attribute — is the operator's and is preserved ahead of ours.
    """
    kept = [
        pair
        for pair in inherited.split(",")
        if pair.strip() and not pair.split("=", 1)[0].strip().startswith("cti.")
    ]
    mine = [f"{key}={quote(value, safe='')}" for key, value in identity.attributes()]
    return ",".join([*kept, *mine])


def assemble_environment(
    parent: Mapping[str, str],
    profile: Profile,
    identity: Identity,
    token: str,
    *,
    project_dir: Path | None = None,
) -> dict[str, str]:
    """Build the child's environment: strip every lane-owned key, then add this lane's.

    Never mutates `parent`. Stripping first is what makes the answer a function of the
    lane rather than of the shell — a parent that already has `ANTHROPIC_BASE_URL` set,
    which is the accident this whole design exists to prevent, produces exactly the same
    child as a clean one.
    """
    lane = LANES[profile.lane]
    child = {key: value for key, value in parent.items() if key not in LANE_OWNED}

    if lane.base_url:
        child["ANTHROPIC_BASE_URL"] = lane.base_url
    # Only when there is one. An empty `ANTHROPIC_AUTH_TOKEN` is not "no credential":
    # it sits above the subscription OAuth in Claude Code's credential ladder, so
    # exporting a blank one would break a run in a way that reads as a provider fault.
    if lane.credential and token:
        child["ANTHROPIC_AUTH_TOKEN"] = token
    child.update(dict(lane.model_slots))
    if lane.context_window:
        child["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(lane.context_window)

    child["OTEL_RESOURCE_ATTRIBUTES"] = resource_attributes(
        identity, parent.get("OTEL_RESOURCE_ATTRIBUTES", "")
    )

    # The dispatched process's own copy of its assignment, so anything downstream of the
    # runner can re-assert what this process was told to be.
    child["CTI_DISPATCH_ID"] = identity.dispatch_id
    child["CTI_DISPATCH_LANE"] = identity.lane
    child["CTI_DISPATCH_PROFILE"] = identity.profile
    child["CTI_DISPATCH_SEAT"] = identity.seat
    child["CTI_DISPATCH_ISSUE"] = str(identity.issue)
    if (
        project_dir is not None
        and SEATS[identity.seat].reviews
        and lane.runner_family is codex_guidance.GuidanceHarness.CLAUDE_CODE
    ):
        child[REVIEW_PLAN_DIRECTORY_ENV] = str(
            project_dir / ".claude" / "plans" / identity.dispatch_id
        )
    return child


def redacted(child: Mapping[str, str], token: str) -> dict[str, str]:
    """Render the child environment for a human: the token replaced, never printed."""
    if not token:
        return dict(child)
    return {key: ("<redacted>" if value == token else value) for key, value in child.items()}


def read_credentials(path: Path) -> tuple[dict[str, str], Refusal | None]:
    """Read `credentials.env`, refusing a missing file or a mode anyone else can read.

    The format is the least a shell would accept: `KEY=value` a line, an optional
    `export` prefix, `#` comments, and quotes stripped. Nothing is executed — a
    credentials file is data, and sourcing it would make it code.
    """
    if not path.exists():
        return {}, Refusal(
            "credentials_missing",
            (f"path={path}",),
            (
                "Create it at mode 0600 and put the lane's key in it (#229's human item, "
                "automated by `just prereqs credentials` in #230). Nothing was dispatched."
            ),
            failure_class="infra_unavailable",
        )

    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return {}, Refusal(
            "credentials_mode",
            (f"path={path}", f"mode={mode:04o}", "want=0600"),
            "Run `chmod 600` on it and dispatch again. Nothing was dispatched.",
            failure_class="infra_unavailable",
        )

    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values, None


def lane_credential(lane: Lane, path: Path) -> tuple[str, Refusal | None]:
    """Resolve this lane's credential, or say precisely which half is missing."""
    if not lane.credential:
        return "", None
    values, refusal = read_credentials(path)
    if refusal is not None:
        return "", refusal
    token = values.get(lane.credential, "")
    if not token:
        return "", Refusal(
            "credential_absent",
            (f"lane={lane.name}", f"key={lane.credential}", f"path={path}"),
            (
                f"The file exists but carries no {lane.credential}. Add it (#229), or "
                "dispatch on a lane that needs no credential. Nothing was dispatched."
            ),
            failure_class="infra_unavailable",
        )
    return token, None


def unknown_seat_refusal(seat: str) -> Refusal | None:
    """Refuse a seat the registry does not carry, and be the one home for that refusal.

    Two callers reach it: `resolve_selection`, for a route the caller named in full, and
    `resolve_seat`, which has no lane and no profile to check first because resolving is
    what it is about to do. A second copy of this refusal is how the two paths would come
    to disagree about which seats exist.
    """
    if seat in SEATS:
        return None
    return Refusal(
        "unknown_seat",
        (f"seat={seat}", f"known={' '.join(sorted(SEATS))}"),
        "Name a known seat: the seat is a telemetry attribute and a typo mis-attributes.",
    )


def resolve_selection(lane_name: str, profile_name: str, seat: str) -> Refusal | None:
    """Check lane, profile and seat against the registry and the carve-out.

    Three registry rungs — lane, profile, seat — then ADR-0071 ruling 1's one survivor:
    the orchestrator carve-out, which keeps orchestration on Claude until a tested
    alternative exists. #327 deleted the eligibility ladder ADR-0061 built and the retro
    allowance that suspended it, and ADR-0073 (#406) retired the one further provenance
    refusal that outlived them — routing class 6's keep-on-Claude bridge, which refused a
    dispatch whose issue named the gates themselves on every lane but `claude-native`, and
    a non-Claude `just land` whose diff touched them. That row's invariant is enforced at
    the landing now, as a requirement on the review rather than a bar on a route, so the
    carve-out below is the only provenance refusal left anywhere.
    Routing class 2 was a second until #327 re-founded it on its seats (#327 review round
    2, claim 1; widened from the one seat to the whole route in #327 review round 3, claim
    1): an
    orchestration declaration now refuses on seating grounds — any seat outside its route,
    every lane — and no longer on a lane. The pair block after the carve-out is a
    capability ceiling, not a provenance one.
    """
    if lane_name not in LANES:
        return Refusal(
            "unknown_lane",
            (f"lane={lane_name}", f"known={' '.join(sorted(LANES))}"),
            "Name a registered lane, or register a new one in tools/dispatch.py.",
        )
    if profile_name not in PROFILES:
        return Refusal(
            "unknown_profile",
            (f"profile={profile_name}", f"known={' '.join(sorted(PROFILES))}"),
            "Name a registered profile. A profile is one opaque token (ADR-0061 D5).",
        )
    profile = PROFILES[profile_name]
    if profile.lane != lane_name:
        return Refusal(
            "profile_lane_mismatch",
            (f"lane={lane_name}", f"profile={profile_name}", f"profile_lane={profile.lane}"),
            (
                "A profile belongs to exactly one lane. Dispatch it on its own lane, or "
                "pick a profile registered for the lane you asked for."
            ),
        )
    refusal = unknown_seat_refusal(seat)
    if refusal is not None:
        return refusal
    if SEATS[seat].claude_only and lane_name != CLAUDE_LANE:
        return Refusal(
            "orchestrator_claude_only",
            (f"seat={seat}", f"lane={lane_name}"),
            (
                "ADR-0071 ruling 1: the orchestrator carve-out. Orchestration runs on "
                "Claude with a Claude model until a tested alternative exists — the only "
                "provenance rule the project holds, and every other seat dispatches on "
                "every lane. Dispatch it on claude-native."
            ),
        )
    # ADR-0071 ruling 2: a refusal can attach to a (profile, seat) pair. Checked after the
    # carve-out, so it only reaches a seat the carve-out already admits, and it is
    # the one home the block list below is consulted — `pair_block` for the reason.
    return pair_block(seat, profile_name)


# ADR-0071 ruling 2: a profile that a measured ceiling holds below a seat's contract is
# blocked for the seat that needs the contract and open for a read-only seat that does
# not. The block is on the pair, so naming the profile directly with `--profile` is a way
# of choosing it and never a way around the block: whether the profile reached the check by
# `--profile` or by a future seat resolver (#321), the same refusal fires from this one
# home. A resolver that hits a blocked pair skips to its next preference rather than failing
# the dispatch, which is why `pair_block` is the function a resolver calls and not a private
# branch of `resolve_selection`.
#
# **It ships empty**, on `config/review-exemptions.json`'s shape: the mechanism is the
# ruling's and the entries are evidence's. Its one entry — `("implementer",
# "codex-luna-max")`, held below the seat by #265's gate ceiling — is gone with the ceiling
# (#405, the human's instruction of 2026-08-18): a Codex session runs its own gate, so the
# binary capability rule no longer holds any Codex profile below the implementer seat.
# An entry carries its own ceiling rather than the refusal naming one, because the entry is
# the only thing that knows which measurement is holding it.
SEAT_PROFILE_BLOCKS: Final[Mapping[tuple[str, str], str]] = {}


def pair_block(seat: str, profile_name: str) -> Refusal | None:
    """Return the refusal for a (profile, seat) pair blocked by ADR-0071 ruling 2, or `None`.

    This is the one home `SEAT_PROFILE_BLOCKS` is consulted, so `resolve_selection` calls it
    for a profile named directly and a future seat resolver (#321) calls it to skip a
    blocked preference — never a second copy of the list. With the list empty it clears
    every pair, which is the honest answer and not a disabled check: a mechanism that is
    kept while its evidence is gone reads as a rule waiting for its next entry, and one
    deleted with its evidence has to be argued back through the ADR that requires it.

    No failure class, for `off_peak_refusal`'s reason exactly: this refusal found nothing
    about a provider or about code under test. The provider is up, the lane is reachable,
    the profile is registered, and this project declines to head a seat with a profile a
    measured ceiling holds below the seat's contract. `infra_unavailable` would assert an
    outage that is not happening and `provider_refused` a refusal the provider never made; a
    wrong class is a harness bug by CLAUDE.md's table, so this carries none.
    """
    ceiling = SEAT_PROFILE_BLOCKS.get((seat, profile_name))
    if ceiling is None:
        return None
    return Refusal(
        "profile_blocked_for_seat",
        (f"profile={profile_name}", f"seat={seat}", f"ceiling={ceiling}"),
        (
            "ADR-0071 ruling 2: this (profile, seat) pair is blocked, because a measured "
            f"ceiling ({ceiling}) holds the profile below what the seat's contract requires. "
            "The block is on the pair, so the same profile on a seat that needs less of it "
            "dispatches normally, and naming the profile with `--profile` is a way of "
            "choosing it and never a way around this. What would clear it: the ceiling's own "
            "issue, and nothing here. Nothing was dispatched."
        ),
    )


# ADR-0071 ruling 4's invariant, in one string because the three refusals that enforce it
# all quote it: the absent-subject one, and both arrivals at `review_same_profile`. Writing
# it out three times is how a rule and the refusals that enforce it come to disagree.
NEVER_ALONE: Final = (
    "ADR-0071 ruling 4: no single model instance may both propose a change and produce the "
    "review verdict that clears it, and the whole argument for that rests on the second "
    "instance being genuinely different — a same-model review makes never-alone a ritual."
)


def reviewed_profile_refusal(seat_name: str, reviewed: str) -> Refusal | None:
    """Check `--reviewing` against the seat that needs it, before any list is walked (#322).

    **The flag names the subject; it does not settle it.** This function checks the name
    against the registry, which is the cheap half — a typo would resolve past nothing and
    produce exactly the same-model review the check exists to prevent. The expensive half is
    `potential_authors` below, which reads the issue's own dispatch records for every profile
    that may have worked on it, excludes all of them from the candidate list and refuses a
    declaration a complete read contradicts — because a check that only compares a caller's
    `--profile` against the caller's `--reviewing` is satisfied by naming any two registered
    profiles and enforces nothing.

    **The absent case refuses**, which is the whole point: with no declared subject there
    is nothing for the exclusion to remove, so any resolution here would be choosing a
    reviewer nobody has checked against the work. The refusal comes before the walk, so no
    candidate is considered at all — the silent same-model review this ticket exists to
    make impossible is prevented by never resolving, not by resolving carefully.

    The flag is refused on a seat that does not review, because an option that silently
    decides nothing is one a caller will believe did something.

    **A retired name passes here and only here** (#413). The check resolves through
    `resolved_profile`, so a name a rename left still names a subject while never naming a
    route: after #399 the records for already-authored work carry `zai-glm52-max` forever,
    and a review of that work has no other subject to declare. The name is still refused
    by `--profile`, which reads `PROFILES` and never the retirement table.

    No failure class, for `pair_block`'s reason: nothing was found about a provider, a lane
    or the code under test. This is an incomplete or contradictory request.
    """
    seat = SEATS[seat_name]
    if not seat.reviews:
        if not reviewed:
            return None
        return Refusal(
            "reviewing_without_review_seat",
            (f"seat={seat_name}", f"reviewing={reviewed}"),
            (
                "`--reviewing` declares the profile whose work is under review and only the "
                "review seat resolves against it. Drop the option, or dispatch `--seat "
                "review`. Nothing was dispatched."
            ),
        )
    if not reviewed:
        return Refusal(
            "review_subject_unknown",
            (f"seat={seat_name}", "reviewing=<absent>"),
            (
                "A review dispatch declares the profile whose work it is reviewing: "
                "`--reviewing <profile>`. Without it there is nothing for the exclusion to "
                "remove, so this refuses before any candidate is walked rather than "
                f"resolving a reviewer nobody checked against the work. {NEVER_ALONE} "
                "Nothing was dispatched."
            ),
        )
    if resolved_profile(reviewed) is None:
        return Refusal(
            "unknown_reviewed_profile",
            (f"reviewing={reviewed}", f"known={' '.join(sorted(PROFILES))}"),
            (
                "The profile under review is checked against the registry rather than "
                "taken as a string, because a typo would resolve past nothing and produce "
                "exactly the same-model review the check exists to prevent. Name a "
                "registered profile. Nothing was dispatched."
            ),
        )
    return None


def _refused_before_running(directory: Path) -> bool | None:
    """Whether this dispatch's own result says it refused before the lane was reached.

    `write_result`'s refusal path is written *instead of* a run, so such a record produced
    nothing and counting its profile as a potential author would invent an implementer out of
    a dispatch that never reached a lane. The key is the same one `tools/ledger.py` reads as
    decisive proof of a pre-lane refusal.

    **`None` where the question could not be answered** — a `result.json` that is there and
    will not parse. The caller keeps the profile, which is the safe direction for an
    exclusion, *and* marks the scan incomplete, because a record it could not read is a
    record it did not check.

    A stop's result deliberately carries no refusal, so a stopped run is `False` here and
    stays in the potential set. That is one of the cases `potential_authors` cannot narrow,
    and it says so rather than guessing.
    """
    result = directory / "result.json"
    if not result.is_file():
        return False
    try:
        document = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    return bool(document.get("refusal"))


class _Read(NamedTuple):
    """What one dispatch directory contributed to the scan, in the two facts it can carry.

    A record can be both at once — a plan that read cleanly beside a `result.json` that did
    not — so these are two fields rather than one verdict. Keeping the profile is the safe
    direction for an exclusion; setting `unreadable` is the safe direction for the record.
    """

    profile: str = ""
    record: str = ""
    unreadable: bool = False


_UNREADABLE: Final = _Read(unreadable=True)
_NOT_THIS_ISSUE: Final = _Read()


def _read_plan(entry: Path) -> dict[str, object] | None:
    """Return this dispatch directory's plan, or `None` where it could not be read.

    Four ways of not having a plan — no file, unreadable bytes, JSON that is not an object,
    an object carrying no issue — and one answer, because the caller acts on all four
    identically: it could not read this record, so it has not checked the issue.
    """
    plan = entry / "dispatch.json"
    if not plan.is_file():
        return None
    try:
        document = json.loads(plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(document, dict) or "issue" not in document:
        return None
    return document


def _named_profile(document: dict[str, object]) -> str:
    """Return the profile this plan names, or empty where it names none this scan can use.

    Absent, blank, whitespace-only and non-string collapse to one answer because the caller
    acts on all four identically: this record did not say which profile ran. `str()` over the
    field would instead have turned a number or a list into a plausible-looking token that
    matches no preference entry and silently clears the check.
    """
    profile = document.get("profile")
    return profile.strip() if isinstance(profile, str) else ""


def _read_record(entry: Path, issue: int, *, include_reviews: bool = False) -> _Read:
    """Classify one dispatch directory against the issue under review.

    Every way of failing to read it lands on `_UNREADABLE` rather than being passed over,
    because with the issue as the only key an unopened record cannot be shown to be about
    some other issue — and a scan that skipped it would report itself complete having not
    looked (#41).

    **A record that cannot name its profile has not been read for this purpose**, and that
    is the narrower door round 2 left open. A plan that parses, carries this issue and
    carries no usable `profile` is *readable* in every sense except the one this scan wants:
    whichever profile that dispatch ran on is unknown, so it is excluded nowhere, and beside
    one good record the scan would have reported itself complete with an unknown potential
    author outside the never-alone floor. Absent, blank, whitespace and non-string all land
    here together, because the caller acts on them identically.

    **A profile the registry no longer carries is deliberately not that case.** It names
    itself, so it is excluded like any other name — `excluded_from_review` is a set of
    strings and a name outside `PROFILES` simply matches no preference entry — and treating
    a retired profile as an unread record would make every later scan of that issue read as
    partial for a fact the record states perfectly well.

    `include_reviews` is the arbiter's door (#333, #361). The default walk skips
    review-seat records because a review is not authorship (#322), and a *review* seat's
    candidate list must not exclude its own judges. The arbiter's question is the wider
    one — *authored or reviewed* — so its scan opens that door: a review record's `profile`
    names the profile that judged the work, which is exactly the name #361's criterion
    removes from the arbiter walk, and which the authorship scan by design cannot carry.
    """
    document = _read_plan(entry)
    if document is None:
        return _UNREADABLE
    try:
        same_issue = int(str(document["issue"])) == issue
    except (ValueError, TypeError):
        return _UNREADABLE
    # Two conditions, one answer: a record about another issue and a record of a dispatch on
    # a seat that judges rather than does are both records this scan walks past, neither of
    # them a gap in it — the second only where the caller is asking who *authored*, which is
    # every caller but the arbiter's scan.
    seat = SEATS.get(str(document.get("seat", "")))
    if not same_issue or (seat is not None and seat.reviews and not include_reviews):
        return _NOT_THIS_ISSUE
    refused = _refused_before_running(entry)
    if refused:
        return _NOT_THIS_ISSUE
    # Below both narrowings on purpose. A review dispatch and a dispatch that refused before
    # reaching a lane authored nothing whichever profile they named, so a missing profile
    # there is genuinely irrelevant rather than a gap in the scan.
    profile = _named_profile(document)
    if not profile:
        return _UNREADABLE
    return _Read(
        profile=profile,
        record=str(document.get("dispatch_id", entry.name)),
        unreadable=refused is None,
    )


def potential_authors(issue: int, dispatch_dir: Path) -> Authorship:
    """Read this issue's dispatch records for the profiles a review must not run on (#322).

    **The issue is the key, and it is the only one available.** A review dispatch is handed
    `--issue <n>`, `--base-sha <sha>` and a worktree of its own; the SHA on an earlier record
    is where that dispatch *started*, not what it produced, and the review's tree is a
    different tree from the implementer's, so neither joins. The issue does: it is required
    on every dispatch, it is on every record, and it is the thing the work and the review of
    the work have in common.

    **What the record supports, and what it does not.** Two narrowings can be read off a
    record honestly. A dispatch on a seat the registry marks `reviews` was judging the work
    rather than doing it, so a second review of the same issue never becomes its own subject.
    A dispatch whose `result.json` carries a refusal never reached a lane and so edited
    nothing. Everything else is out of reach: a planner, a recon, a stopped run, a successful
    no-op and a dispatch against a branch a later one supersedes are all indistinguishable
    here from the implementer that wrote the diff, because **nothing on the record names the
    commits a run produced**. Putting that on the record is a change to what a dispatch
    writes, and it belongs with #333's adjudication rather than here.

    So this returns a **potential**-author set, not an author set, and the caller uses it for
    the one thing a superset is right for: removing every entry from the review seat's
    candidate list. It is never evidence that a named profile did the work, and the route it
    feeds says `checked` rather than `verified` for that reason.

    **A partial read is never a complete one.** An unreadable plan, a dispatch directory with
    no plan in it, a plan carrying no issue, a plan that does not name its profile, a
    `result.json` that will not parse: each leaves `why=records_unreadable`, and the profiles
    that *were* read are still returned and still excluded. That is #41's rule with its two
    halves kept apart — the check did not run, so it must not report as passed; the exclusion
    is a superset, so an incomplete read still narrows it. The profile-less plan is the one
    that reads as an answer rather than as a gap, which is why `_read_record` states its case
    separately.
    """
    return _scan_records(issue, dispatch_dir, include_reviews=False)


def _scan_records(issue: int, dispatch_dir: Path, *, include_reviews: bool) -> Authorship:
    """Walk the records both scans share, so the two cannot drift apart.

    One directory iteration, one accumulation of the `why` states, one ordering — differing
    only in the `include_reviews` door `_read_record` documents. `potential_authors` and
    `potential_authors_and_reviewers` are two questions over one record format; giving each
    its own loop would be a second copy of the #41 discipline where a drift between the
    copies is exactly the defect (one scan marking a state partial the other reads clean).
    """
    directory = dispatch_dir.expanduser()
    if not directory.is_dir():
        return Authorship(why=NO_DISPATCH_RECORDS)
    found: list[str] = []
    records: list[str] = []
    unreadable = 0
    for entry in sorted(directory.iterdir()):
        if not entry.is_dir():
            # Not a record at all. A stray file beside the records is not a record this scan
            # failed to read, so it does not make the read partial.
            continue
        read = _read_record(entry, issue, include_reviews=include_reviews)
        unreadable += int(read.unreadable)
        if read.profile and read.profile not in found:
            found.append(read.profile)
            records.append(read.record)
    if unreadable:
        return Authorship(tuple(found), tuple(records), why=RECORDS_UNREADABLE)
    if found:
        return Authorship(tuple(found), tuple(records))
    return Authorship(why=NO_AUTHORING_DISPATCH)


def potential_authors_and_reviewers(issue: int, dispatch_dir: Path) -> Authorship:
    """Read this issue's dispatch records for the profiles an arbiter must not be (#333, #361).

    A sibling of `potential_authors`, not a change to it, because the two answer different
    questions and each has callers that depend on its answer. The review seat asks *who may
    have authored the work* and deliberately walks past review records — a review is not
    authorship, and a reviewer excluded from its own candidate list would strand the seat
    (#322). The arbiter asks #361's wider question — *who authored or reviewed the work* —
    and a prior reviewer is precisely the instance the walk must not select: #318's real
    `opus-xhigh` reviewer is on the records as a review dispatch and nowhere else, so a
    resolver fed only the authorship scan cannot see the one profile its criterion exists
    to exclude. That was #333 round 1's High 2: the production input could not carry a
    reviewer, and the test injected one by hand through a seam production never takes.

    Same states, same `records` spelling, same `why` vocabulary as the authorship scan, so
    the arbiter's `unchecked` mark (every state that is not a complete read) reads off
    `Authorship.complete` for both.
    """
    return _scan_records(issue, dispatch_dir, include_reviews=True)


def review_authorship(seat: Seat, args: argparse.Namespace) -> tuple[Authorship, Refusal | None]:
    """Read the records, on the one seat and the one dispatch that has a subject to check.

    **Two sources, the same merge the landing rung performs** (#402). #398 gave the author
    set a second source — the interactive declaration under `~/.arma-cti/review/`, read
    through `with_declared_authors` — because #294 bars a dispatched session from writing
    under `.claude/`, so such a change leaves no dispatch record at all. `just land`'s rung
    reads both; this, the other consumer of the same set, read only the dispatch records,
    so a review could be dispatched onto the very profile that authored the change and be
    refused at the landing the record the dispatcher never saw. The two consumers now
    cannot disagree, because both call the same merge.

    **A declaration that will not read is a refusal, not a silence.** `recorded_authors`
    raises on a record this tool did not write, and swallowing that would return a set
    missing a name that could be the reviewer's own — the exact overstatement #402 was
    filed about. A *lost* declaration — the record gone, the lock it alone creates still
    there — is the same narrowing one door along, and `declaration_lost` names it. Both
    refuse rather than resolve, matching the landing's vocabulary for the same facts
    (`authorship_unreadable`, `authorship_lost`) so a reader meets one name per fact.
    """
    if not seat.reviews or not args.reviewing:
        return Authorship(), None
    review_root = Path(args.review_root)
    record = review_loop.authorship_path(review_root, args.issue)
    if review_loop.declaration_lost(review_root, args.issue):
        return Authorship(), Refusal(
            "authorship_lost",
            (
                f"issue={args.issue}",
                f"record={record}",
                f"lock={record.with_name(review_loop.AUTHORSHIP_LOCK)}",
            ),
            (
                "A declaration was written for this issue and its record is gone, so the "
                "profiles it named are absent from the set this review's candidates are "
                "checked against — and one of them could be the profile that would have "
                "resolved. The lock beside the missing record is what says a declaration "
                "reached the writer; only the writer creates it. Re-declare every "
                "interactive author with `just review-loop author --issue <n> --profile "
                "<profile>` and dispatch again. A check that could not run is not a check "
                f"that passed (#41). {NEVER_ALONE} Nothing was dispatched."
            ),
        )
    try:
        declared = review_loop.recorded_authors(review_root, args.issue)
    except review_loop.ExternalError as error:
        return Authorship(), Refusal(
            "authorship_unreadable",
            (f"issue={args.issue}", f"record={record}", f"reason={error}"),
            (
                "An interactive authorship record for this issue exists and could not be "
                "read, so who authored this work is not an answer any record can give — "
                "and the entry that would not open could name the profile this dispatch "
                "would have resolved. Repair the record at the path above, or remove it "
                "and re-declare with `just review-loop author --issue <n> --profile "
                "<profile>`. A check that could not run is not a check that passed (#41). "
                f"{NEVER_ALONE} Nothing was dispatched."
            ),
        )
    return (
        with_declared_authors(
            potential_authors(args.issue, Path(args.dispatch_dir)),
            declared,
            str(record),
        ),
        None,
    )


def contradicted_refusal(seat: Seat, reviewed: str, issue: int, authorship: Authorship) -> Refusal:
    """Refuse a declared subject the issue's own dispatch records contradict (#322).

    The Critical this closes: with the subject declared and nothing else, `--profile
    opus-high --reviewing codex-luna-max` passes — both are registered, the equality check
    compares the profile against the declaration rather than against anything read off the
    box, and the implementing instance produces the verdict on its own work while the record
    names somebody else. The records know better, so they are asked.

    **Only ever reached on a complete read.** Where any record could not be read the subject
    is recorded unchecked instead of refused, because the profile this declaration names
    could be sitting in the record that would not open — refusing there would turn a gap in
    the scan into an accusation about the caller.

    **A declaration alone is a complete read** (#423). `with_declared_authors` clears `why`
    for the two empty states, so on a change the dispatch records cannot speak to — a
    `.claude/` edit's shape — the merged set is complete with only the declared names in it.
    A subject none of them names is refused here on that set, exactly as a record-placed one
    would be: the caller controls both halves, the `records=` line shows which names came
    from the declaration record, and the remedy — declare the subject's own session too with
    `just review-loop author` — is real. Before #402 this arrangement dispatched with the
    subject recorded unchecked; the landing's rung would have refused it there anyway, so
    failing here spends no dispatch on a route the landing would not clear.

    **No failure class**, for `pair_block`'s reason: the provider is up, the lane is
    reachable, both profiles are registered, and this is an incorrect request. Nothing was
    found about any code under test.
    """
    return Refusal(
        "review_subject_contradicted",
        (
            f"seat={seat.name}",
            f"reviewing={reviewed}",
            f"issue={issue}",
            f"potential_authors={' '.join(authorship.potential)}",
            f"records={' '.join(authorship.records)}",
        ),
        (
            f"The dispatch records and any declared authorship for #{issue} place its work on "
            f"{' and '.join(authorship.potential)}, and this dispatch declares it is reviewing "
            f"{reviewed}, which is none of them. One of the two is wrong, and the declaration "
            "is the half a caller controls, so it is the half that is refused. This merged "
            "read is complete even when the declaration is its only record. Nothing was "
            "dispatched. Name a profile the records carry, or — if the work was done somewhere "
            "these records cannot see — declare the subject's own session too with `just "
            "review-loop author`, because a subject nobody can check is the hole this refusal "
            f"exists to close. {NEVER_ALONE}"
        ),
    )


def profile_lineage(name: str) -> tuple[str, ...]:
    """Return the name and every name the rename chain replaced it with, newest last (#413).

    The result spans the whole chain, not the retired half of it: the name itself (live or
    retired), every retired name on the way, and the live name the chain ends at. That span
    is why this is `profile_lineage` and not `retired_names` (#414) — a reader who took the
    old name at its word would treat the live end of the chain as retired, which it is not.

    One entry is all the table has ever carried; the walk is for the second rename of the
    same profile, which a single hop would resolve one step short of the live name. A cycle
    in the table is a registry bug, and it stops the walk rather than looping on it.
    """
    chain = [name]
    while chain[-1] in RETIRED_PROFILES:
        successor = RETIRED_PROFILES[chain[-1]].successor
        if successor in chain:
            break
        chain.append(successor)
    return tuple(chain)


def resolved_profile(name: str) -> Profile | None:
    """Return the registry entry a name resolves to for reading records (#413).

    The name itself where it is registered, else the successor a rename left.

    Reading is the only direction. `--profile` and every seat's preference list read
    `PROFILES` directly and never resolve through here, so a retired name names a review's
    subject and never a route — the distinction criterion 2 asks the mechanism to make. A
    name whose chain resolves to nothing registered returns `None`, which every caller
    treats as unplaceable rather than as empty.
    """
    for candidate in reversed(profile_lineage(name)):
        if candidate in PROFILES:
            return PROFILES[candidate]
    return None


def never_alone_exclusions(authorship: Authorship) -> frozenset[str]:
    """Every profile name a reviewer must not be, taken from the authorship set alone (#413).

    `excluded_from_review` minus the declared subject, which the landing does not have —
    the verdict's own dispatch already refused that route. Both read `profile_lineage`, so a
    rename cannot make dispatch refuse a reviewer the landing then clears, which is the
    disagreement the retired name would otherwise open between the two rungs.
    """
    return frozenset(name for profile in authorship.potential for name in profile_lineage(profile))


def excluded_from_review(reviewed: str, authorship: Authorship) -> frozenset[str]:
    """Every profile a review must not run on: the declared subject and every potential author.

    The Critical this closes: excluding the declared subject alone enforces "not the one you
    named", where ruling 4's invariant is "no profile that worked on the change produces the
    verdict that clears it". On a branch two dispatches touched, declaring one of them left
    the other free to review work it may have coauthored — and the declaration is the half a
    caller controls, so that is a hole a caller can walk through on purpose.

    The set is deliberately a **superset** of the profiles that actually wrote commits,
    because the record cannot narrow it further (`potential_authors` states why). Excluding
    too much costs a resolution step down the seat's list; excluding too little costs the
    invariant. Those prices are not comparable, so the conservative side is the only one —
    and since #413 that includes each retired name's successor, resolved through
    `profile_lineage` rather than left as a string no preference list carries.

    One home, so that resolution, the refusal text and the printed route cannot disagree
    about which profiles this dispatch was never going to take.
    """
    return frozenset(
        name for source in (reviewed, *authorship.potential) for name in profile_lineage(source)
    )


def review_candidates(
    seat: Seat, reviewed: str, authorship: Authorship = NO_AUTHORSHIP
) -> tuple[str, ...]:
    """Order a seat's preference for reviewing work done on `reviewed` (ADR-0071 ruling 4).

    Two rules, and only the first is absolute. The profile under review is **removed**, and
    so is every other profile the issue's dispatch records place on the work — the whole of
    `excluded_from_review`, none of which is ever a candidate whatever the rest of the world
    says about it. A different lane is **preferred**, which is an ordering and not a second
    filter — the entries that share the reviewed profile's lane keep their places behind the
    ones that do not, and are still walked.

    Being explicit about the case the ADR's one word leaves open: **when the only
    non-matching entries share the lane, they are used.** Making the lane a filter would
    refuse a genuinely different model — GLM-5.3 reviewing Luna's work is a different
    instance of a different family, and z.ai and Codex are separate providers anyway — and
    it would confuse ruling 4's invariant, which is about the *instance* producing the
    verdict, with the provider it is reached through. Provider diversity is preferred
    because one family's blind spots are not another's; it is not the invariant.

    Within each half the seat's own head-first order survives, because that order is the
    ADR's ranking of the work and nothing here re-ranks it.

    A seat that does not review is returned unchanged, so this is the one function every
    caller can ask for "the list this dispatch walks" without knowing which seat it has.
    """
    if not seat.reviews:
        return seat.preference
    subject = resolved_profile(reviewed)
    if subject is None:
        # `reviewed_profile_refusal` refuses an absent or unregistered subject above every
        # resolution, so this is the rendering path only: a dispatch record read back off
        # disk can name a profile the registry has since dropped, and printing what that
        # dispatch could walk must not raise. Empty is also the fail-closed answer if this
        # were ever reached while deciding — no candidate resolves. A retired name resolves
        # through the successor (#413), so the lane the ordering prefers is the live one.
        return ()
    excluded = excluded_from_review(reviewed, authorship)
    other_lane = tuple(
        name
        for name in seat.preference
        if name not in excluded and PROFILES[name].lane != subject.lane
    )
    same_lane = tuple(
        name
        for name in seat.preference
        if name not in excluded and PROFILES[name].lane == subject.lane
    )
    return (*other_lane, *same_lane)


def same_profile_refusal(
    seat: Seat,
    reviewed: str,
    why: str,
    authorship: Authorship = NO_AUTHORSHIP,
    named: str = "",
) -> Refusal:
    """Refuse a review that would run on a profile that worked on what it reviews (#322).

    One refusal kind reached three ways, because it is one fact: this dispatch would have a
    profile the records place on the change produce the verdict that clears it. `why=` says
    which way — `named`, a caller who typed the declared subject into `--profile`;
    `named_author`, a caller who typed a *different* profile the issue's records also carry;
    and `list_offers_nothing_else`, a seat whose list is empty once every one of them is
    removed. The remedies differ and the finding does not, and giving the finding three names
    would mean three strings to grep for the thing the ticket is about.

    `named_author` reuses this kind rather than opening a second refusal on the adjudicated
    ground that the finding is the same one. What differs is which profile a reader has to
    stop using, so the action names it and `excluded=` prints the whole set.

    Naming `--profile` is a way of choosing and never a way around, exactly as ADR-0071
    ruling 2 says of every other `(profile, seat)` refusal, so the named route meets this
    check too.

    **No failure class**, for `pair_block`'s and `exhausted_refusal`'s reason: nothing was
    found about a provider, a lane, or the code under test. The provider is up and the
    profile is registered; this project declines to let one instance clear its own change.
    """
    candidates = review_candidates(seat, reviewed, authorship)
    excluded = excluded_from_review(reviewed, authorship)
    resolves_to = " ".join(candidates) or "nothing else"
    if why == "named":
        action = (
            f"You named {reviewed}, which is the profile whose work is under review. Name a "
            "different one, or leave --lane and --profile out and let the seat resolve: it "
            f"walks {resolves_to} for this subject. Nothing was dispatched. {NEVER_ALONE}"
        )
    elif why == "named_author":
        action = (
            f"You named {named}, which is not the declared subject but is a profile this "
            "issue's authorship records place on the work ("
            f"{potential_author_provenance(authorship)})"
            " — so it may have coauthored the change it would be clearing. The invariant is "
            "about every profile that worked on the change, not the one a caller chose to "
            "declare. Name a "
            "different one, or leave --lane and --profile out and let the seat resolve: it "
            f"walks {resolves_to} for this subject. Nothing was dispatched. {NEVER_ALONE}"
        )
    else:
        action = (
            f"The {seat.name} seat's preference is {' '.join(seat.preference)}, and removing "
            f"{' and '.join(sorted(excluded))} leaves it with nothing. None of those profiles "
            "can be ruled out as an author of this change, so this seat has no route it can "
            "offer. Nothing was dispatched, and this refusal is the point rather than an "
            "obstacle to route around: register another profile for this seat, or have the "
            f"change reviewed from a seat whose list offers one. {NEVER_ALONE}"
        )
    return Refusal(
        "review_same_profile",
        (
            f"seat={seat.name}",
            f"reviewing={reviewed}",
            f"why={why}",
            *((f"profile={named}",) if named else ()),
            f"potential_authors={' '.join(authorship.potential)}",
            f"records={' '.join(authorship.records)}",
            f"excluded={' '.join(sorted(excluded))}",
            f"candidates={' '.join(candidates) or 'none'}",
        ),
        action,
    )


class Readiness(NamedTuple):
    """What the readiness rung learned: an assessment of the issue, or why there is none."""

    assessment: readiness.Assessment | None
    unreadable: str = ""
    body: str = ""


REMEDY_IS_AN_EDIT: Final = (
    "The remedy is an edit to the issue, by a human or by triage — add the criteria, or "
    "make the existing ones countable and name what would settle each. Nothing here will "
    "rewrite the issue for you and nothing should: a tool that repaired the body it was "
    "judging would be marking its own homework, and the value of this rung is that "
    "somebody decided what done means before a lane was spent. There is no override flag."
)


def read_issue(issue: int, body_file: str) -> Readiness:
    """Read the issue's body — from a named file if given, otherwise from `gh` — and judge it.

    `--issue-body` is not a test seam. It is how triage checks a *draft* before filing one,
    and how a dispatch is armed on a box where `gh` cannot reach GitHub; the tier uses it
    for the same reason it points `--breaker-dir` at a scratch path, which is that the real
    seam forks a fresh process no in-process patch reaches.
    """
    if body_file:
        path = Path(body_file).expanduser()
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as error:
            return Readiness(None, f"{path}: {error.strerror or error}")
        if not body.strip():
            return Readiness(None, f"{path} is empty")
        return Readiness(readiness.assess(body), body=body)
    body, why = readiness.fetch_body(issue)
    if why:
        return Readiness(None, why)
    return Readiness(readiness.assess(body), body=body)


def readiness_refusal(issue: int, found: Readiness) -> Refusal | None:
    """Refuse an issue that is not ready to be dispatched against (#241).

    Definition of ready, mechanically. `tools/readiness.py` carries the sub-checks, the
    definitions they were pre-registered with, and the corpus measurement that decided
    which of them refuse: two that refused none of the last twenty dispatched issues do,
    and enumerability — 15% overall, 67% of ruling executions — does not, because a ruling
    execution's criteria *are* the ruling and enumerating them would mean paraphrasing it.

    **No failure class**, for `off_peak_refusal`'s reason exactly:
    CLAUDE.md's table types what a run *found*, and this found nothing about any code. The
    provider is up, the lane is reachable, and the issue is not ready to be worked. An
    unreadable body is different and does carry one — `infra_unavailable` — because a check
    that could not run is not a check that passed (#41), and a dispatched agent whose first
    act is `gh issue view` would meet the same outage three seconds later somewhere nobody
    is looking.

    **Lane-blind.** Nothing about the lane, the profile or the seat reaches this function,
    so every lane meets exactly the refusal every other lane meets.
    """
    if found.assessment is None:
        return Refusal(
            "issue_unreadable",
            (f"issue={issue}", f"why={found.unreadable}"),
            (
                "The issue body could not be read, so its readiness could not be checked, "
                "and a check that could not run is not a check that passed (#41). Nothing "
                "was dispatched. Fix the reason above, or pass the body with "
                "`--issue-body <path>` if GitHub is unreachable from here."
            ),
            failure_class="infra_unavailable",
        )
    blocking = found.assessment.blocking
    if not blocking:
        return None
    return Refusal(
        "issue_not_ready",
        (
            f"issue={issue}",
            *(f"{finding.kind}: {finding.detail}" for finding in blocking),
            *found.assessment.lines(),
        ),
        REMEDY_IS_AN_EDIT,
    )


def readiness_advisories(issue: int, found: Readiness) -> tuple[str, ...]:
    """Render the readiness findings that report and never refuse."""
    if found.assessment is None:
        return ()
    return tuple(
        f"advisory={finding.kind} issue={issue} {finding.detail}"
        for finding in found.assessment.advisory
    )


type QuotaReader = Callable[[str, Path, float], breaker.QuotaReading]


def breaker_refusal(
    lane_name: str,
    breaker_dir: Path,
    now: float,
    quota_reader: QuotaReader = breaker.query_first_party_quota,
) -> Refusal | None:
    """Read this lane's breaker before anything is planned, and refuse a tripped one (#226).

    This is the integration point ADR-0061 Decision 7 asks for: the state is read
    *before* dispatch, so a lane whose quota is gone costs nothing to discover, and the
    wait it hands back is a published window boundary rather than a guess. A quality
    trip refuses with `provider_refused` instead — waiting does not fix a lane that is
    serving the wrong thing, and that row's response is exactly the right one: not a
    result, re-dispatch elsewhere, and escalate.

    `quota_reader` is the one seam through which this read can reach the network:
    `breaker.lane_verdict` asks the provider's own quota endpoint for a z.ai lane held
    open on availability with no published boundary, which is how that lane heals itself
    without a dispatch. The live reader is bounded — one request, no retry, a 10 s timeout
    on every socket operation, every failure a typed unavailable reading — and it stays the
    default, so that what this refusal says is what a dispatch would have met. It is a
    parameter because a second caller arrived that is not a dispatch (#427): `tools/land_review.py`
    asks this rung inside `just land`, and a test of a landing record must be able to
    stage that lane's state without a socket.
    """
    store = breaker.Store(directory=breaker_dir, quota_reader=quota_reader)
    result = breaker.lane_verdict(store, lane_name, now)
    if result.conducting:
        return None
    found = [f"lane={lane_name}", f"rule={result.rule}", f"why={result.reason}"]
    if result.reset_at is not None:
        found.append(f"until={breaker.iso(result.reset_at)}")
        found.append(f"in={breaker.human_delta(result.reset_at - now)}")
    else:
        found.append("until=unknown")
    if result.escalates:
        action = (
            "The lane's breaker is tripped and escalates rather than resetting on a "
            "timer. Re-dispatch to another lane; this one reopens only when a human "
            f"runs `just breaker reset --lane {lane_name} --force`."
        )
    elif result.reset_at is None:
        action = (
            "The lane is out of quota and no reset time was published to us, because no "
            "quota feed is wired — the breaker is reacting to 429s. Re-dispatch to "
            "another lane, or wire the feed with `just prereqs statusline` (#230)."
        )
    else:
        action = (
            "Not a result: nothing was dispatched and nothing is known about the code "
            "under test. Re-dispatch to another lane, or queue until the reset above. "
            "The wait is the provider's own window boundary, not a backoff."
        )
    return Refusal("lane_breaker_open", tuple(found), action, failure_class=result.failure_class)


def off_peak_refusal(lane: Lane, at: datetime) -> Refusal | None:
    """Refuse a lane the human has ruled off-peak-only, outside its window (#238).

    The human's ruling of 2026-08-05: the z.ai lane is used only in off-peak times, as a
    hard rule — a dispatch-time refusal, not guidance. So this is a rung and not a
    warning, and there is deliberately **no override on this surface**: no flag, no
    environment variable, no per-dispatch exemption. `plan_dispatch` is handed the clock
    by `main`, which reads it, and an agent that wants this lane in peak hours has one
    move, which is to dispatch somewhere else. Amending the rule is the human's.

    The window is not restated here. It comes from the lane's published schedule in
    `tools/breaker.py` — the same object `plan_charge` prices the dispatch with — so the
    band this refuses against and the band a dispatch records cannot disagree.

    **No failure class**, and the reasoning is `readiness_refusal`'s exactly. CLAUDE.md's
    table types what a run *found*, and this refusal found nothing: the provider is up,
    the credential is good, the lane is reachable, and this project chose not to spend on
    it now. `infra_unavailable` would assert an outage that is not happening,
    `quota_exhausted` a cap that has not been reached, and `provider_refused` a refusal
    z.ai never made. A wrong class is a harness bug by that table's own rule, so this
    carries none — which is also what makes it unmistakable in a verdict: the dispatch
    did not happen and nothing about any code under test was learned or claimed.
    """
    if not lane.off_peak_only:
        return None
    schedule = breaker.LANE_SCHEDULES.get(lane.name)
    if schedule is None:
        # Fail closed. A lane ruled off-peak-only whose window nobody registered cannot be
        # checked, and a rule that cannot be checked must not be assumed satisfied.
        return Refusal(
            "off_peak_window_unknown",
            (f"lane={lane.name}", "rule=off-peak-only", "window=unregistered"),
            (
                "Harness bug: this lane is ruled off-peak-only and no published schedule "
                "is registered for it in tools/breaker.py's LANE_SCHEDULES, so the rule "
                "could not be evaluated. Nothing was dispatched. Fix the registry."
            ),
        )
    now = at.timestamp()
    if not schedule.is_peak(now):
        return None
    opens = schedule.opens_at(now)
    return Refusal(
        "lane_peak_hours",
        (
            f"lane={lane.name}",
            "rule=off-peak-only",
            f"band=peak window={schedule.window}",
            f"window_source={schedule.source}",
            f"opens={breaker.iso(opens)}",
            f"in={breaker.human_delta(opens - now)}",
        ),
        (
            "The human ruled this lane off-peak-only on 2026-08-05 (#238) and the clock "
            "is inside the peak band above. Nothing was dispatched and nothing is known "
            "about the code under test. Dispatch on claude-native, or re-arm after the "
            "time above. There is no override here and asking for one is not the move: "
            "the rule is the human's and only they amend it."
        ),
    )


def lane_bar(
    lane: Lane,
    breaker_dir: Path,
    credentials: Path,
    at: datetime,
    quota_reader: QuotaReader = breaker.query_first_party_quota,
) -> Refusal | None:
    """Whether this lane can be reached at all at that moment, and what bars it if not.

    The half of `candidate_refusal` that is a function of the lane and the clock alone —
    the lane's breaker, the human's off-peak rule and the lane's credential, in the order
    the resolver has always asked them. Split out rather than copied because a second
    reader arrived (#426): `tools/land_review.py`'s never-alone rung asks whether a *free*
    reviewer lane was reachable at landing time, so that the record it writes about a
    same-lane review names the same bar a dispatch would have hit. A second copy of these
    three rungs is exactly how the landing's account and the dispatcher's answer would
    come to disagree.

    No profile is involved and none is asked for. The `(profile, seat)` block and the
    registry rungs stay with `candidate_refusal`, which is where a profile exists to
    judge; a caller holding only a lane name gets the lane's own answer and nothing
    borrowed from a profile it did not name.

    **The order below is the answer, not an implementation detail**, and it is pinned by a
    test (#427). A lane can be barred by more than one of the three at once — a tripped
    breaker on a lane that is also off-peak and also missing its key — and this returns the
    first, so the order decides which single bar a dispatch names and which one a landing
    record carries. Breaker first because it is the only one that says something happened to
    the provider; off-peak next because it is the human's policy on a lane that is otherwise
    working; the credential last because a lane already refused for a reason of its own does
    not need this box's configuration reported as its problem.

    `quota_reader` is `breaker_refusal`'s seam and is passed through unchanged: it is the
    only path from here to the network, its default is the live bounded reader, and a caller
    that must not reach the provider — a test, or a landing rung staging a lane's state —
    hands in its own.
    """
    refusal = breaker_refusal(lane.name, breaker_dir, at.timestamp(), quota_reader)
    if refusal is not None:
        return refusal
    refusal = off_peak_refusal(lane, at)
    if refusal is not None:
        return refusal
    _, refusal = lane_credential(lane, credentials)
    return refusal


def candidate_refusal(
    args: argparse.Namespace, seat: str, profile_name: str, now: datetime
) -> Refusal | None:
    """Judge one preference entry with the same rungs the ladder judges a named route by.

    Which rungs, and the rule that decides: **a rung belongs here when it is a function of
    `(lane, profile, seat)` and of nothing else.** Those are the registry, the carve-out,
    the `(profile, seat)` block, the lane's breaker and the human's off-peak rule — each
    one the ladder's own function, called here rather than restated, because a second copy
    is how a profile comes to be dispatchable to a resolver and refused by the ladder two
    lines later. The last three of those arrive together as `lane_bar`, which is the same
    three rungs in the same order under one name so that a caller holding only a lane can
    ask them (#426). The profile's admission standing was one of these until #328 dropped
    the bar; nothing replaced it here, and a route is now judged by nothing upfront.

    Readiness and the queue policy are deliberately absent: each reads the *issue*, so each
    judges the dispatch rather than the candidate, and no change of profile could ever clear
    one. The routing policy is a function of both and is **owned by the arbiter walk, not
    here** (#391, on the orchestrator's ruling of 2026-08-19): it reads the branch under
    review's own paths, which this resolver is never handed, so folding it in would mean a
    caller-supplied trust seam rather than a derived read. `arbiter._walk_first` runs
    `enforcing_match` per candidate on inputs the escalation derives itself; leaving it out
    here means a resolved route can still be refused by the ladder below, which is the
    honest outcome — the alternative is this resolver quietly re-deciding a policy question.

    The lane's credential is here for the same reason the breaker is, and it is the one
    rung this resolver reads that `ladder_refusal` does not: a lane with no key on this box
    cannot be reached at all, which is the plainest form of "not dispatchable right now".
    Left out, a seat whose live head sits on an unconfigured lane would refuse every
    dispatch instead of resolving past it, which is the seat unusable rather than the lane
    unreachable. It is not silent — the entry is recorded as passed over with the
    credential refusal's own name and `infra_unavailable` class beside it.
    """
    profile = PROFILES[profile_name]
    lane = LANES[profile.lane]
    refusal = resolve_selection(lane.name, profile_name, seat)
    if refusal is not None:
        return refusal
    return lane_bar(
        lane,
        Path(args.breaker_dir).expanduser(),
        Path(args.credentials).expanduser(),
        now,
    )


def exhausted_refusal(
    seat: Seat,
    passed: tuple[PassedOver, ...],
    reviewed: str = "",
    authorship: Authorship = NO_AUTHORSHIP,
) -> Refusal:
    """Refuse by name when a seat's whole preference list is unavailable (#321).

    Named rather than quietly escalated or defaulted, because the story this serves is "I
    never discover exhaustion by watching a dispatch fail" — and a fallback to a profile the
    seat's table does not name is that discovery deferred to whoever reads the ledger.

    **No failure class of its own**, and the reasoning is `pair_block`'s. This refusal found
    nothing its constituents had not already found, and each constituent's own class travels
    with it in the lines below. A class here would either flatten a mixed set — one entry out
    of quota, one blocked for this seat — into a single wrong answer, or copy whichever class
    happened to come last, and a wrong class is a harness bug by CLAUDE.md's table.

    The remedy is written to be **typed rather than paraphrased**, which is the one part of a
    refusal a reader acts on verbatim. Two ways of getting that wrong were found by #321's
    review and are closed here: naming `--profile` alone, which `missing_required` refuses
    with `incomplete_request missing=--lane` because the pair travels together; and offering
    to dispatch an escalation entry for a seat that registers none, where the old text
    interpolated the phrase `none registered` into the position a profile name goes.

    On the review seat the list that was walked is not the seat's raw preference — every
    profile the issue's records place on the work was removed before anything was tried
    (#322) — so both are printed and the removed ones are named. A reader shown only
    `preference=` would count the entries, count the refusals, find one unaccounted for, and
    reasonably conclude the resolver had skipped a live route.
    """
    escalation = " ".join(seat.escalation)
    walked = review_candidates(seat, reviewed, authorship)
    if seat.escalation:
        head = seat.escalation[0]
        alternative = (
            f"This seat's escalation entry is {escalation}, reached the same way "
            f"(--lane {PROFILES[head].lane} --profile {head}); spending one is a judgement "
            "about the work and is deliberately not resolved into automatically *here*. "
            "`tools/arbiter.py`'s walk is a different resolution and starts at this entry."
        )
    else:
        alternative = (
            f"The {seat.name} seat registers no escalation entry, so there is no dearer "
            "route above its list for this refusal to point at."
        )
    excluded = (
        (
            f"reviewing={reviewed} (removed before the walk)",
            f"excluded={' '.join(sorted(excluded_from_review(reviewed, authorship)))}",
            f"walked={' '.join(walked)}",
        )
        if reviewed
        else ()
    )
    return Refusal(
        "seat_list_exhausted",
        (
            f"seat={seat.name}",
            f"preference={' '.join(seat.preference)}",
            *excluded,
            *(entry.line("refused") for entry in passed),
            f"escalation={escalation or 'none'}",
        ),
        (
            "Every profile in this seat's preference list refused, each for the reason above, "
            "so no route was resolved and nothing was dispatched. Read each refusal's own "
            "class: a lane out of quota reopens at its published window, a quality trip needs "
            "a human, and a blocked (profile, seat) pair reopens when the ceiling that blocks "
            "it lifts. To dispatch anyway, name a route this list does not know — --lane and "
            "--profile travel together, and one without the other is refused: "
            f"`just dispatch --lane <lane> --profile <profile> --seat {seat.name} "
            f"--issue <n>`. {alternative}"
        ),
    )


def resolve_seat(
    args: argparse.Namespace, now: datetime
) -> tuple[Resolution | None, Refusal | None]:
    """Resolve the route: the profile the caller named, or the seat's first dispatchable one.

    This runs above every other rung for a mechanical reason rather than a re-ranking of
    `ladder_refusal`'s order: each rung below consumes a lane and a profile, and until this
    returns there is no route for them to climb with. It reports nothing at all unless the
    whole list refuses — a breaker-refused head is a *skip*, not a refusal — so the only
    order this changes is the one case where the seat has no route to offer, and there the
    ladder below could not have run anyway.

    On a seat that reviews, the profile under review is an input and the list walked is
    `review_candidates`' — never the raw preference (#322). The check on that input runs
    above the named route as well as above the resolved one, because ADR-0071 ruling 4's
    invariant is about which instance produces the verdict and `--profile` chooses an
    instance just as resolution does.

    The subject is then checked against the issue's dispatch records, above both routes for
    the same reason and above the block on naming it: a caller who declares the wrong subject
    has already defeated that block, since it compares two strings the caller typed. The
    contradiction is refused only on a **complete** read of those records — a partial read
    marks the subject unchecked and still excludes everything it did read. The records are
    both kinds #398 named: dispatch records and the interactive declaration, merged in
    `review_authorship` (#402), which also refuses by name a declaration that will not read
    or has been lost rather than resolving against a set it cannot trust.
    """
    refusal = unknown_seat_refusal(args.seat)
    if refusal is not None:
        return None, refusal
    refusal = reviewed_profile_refusal(args.seat, args.reviewing)
    if refusal is not None:
        return None, refusal
    seat = SEATS[args.seat]
    authorship, refusal = review_authorship(seat, args)
    if refusal is not None:
        return None, refusal
    if authorship.complete and args.reviewing not in authorship.potential:
        return None, contradicted_refusal(seat, args.reviewing, args.issue, authorship)
    if args.profile:
        return _named_route(seat, args, authorship)
    return _walk_preference(seat, args, now, authorship)


def _named_route(
    seat: Seat, args: argparse.Namespace, authorship: Authorship
) -> tuple[Resolution | None, Refusal | None]:
    """Take the route the caller typed, after the one check the ladder below cannot make.

    Everything else about a named route is validated by `resolve_selection` on the ladder
    exactly as it always was, block included: this function chooses, and never clears. The
    same-profile check is here because the ladder judges `(lane, profile, seat)` and the
    profile under review is none of those three, so a caller naming it would otherwise reach
    a rung that has no way to know it is the wrong instance.

    The check is against `excluded_from_review` and not against `--reviewing` alone, so a
    caller who declares one author and names another is refused too. Comparing only the two
    strings the caller typed is what let a coauthor review its own work.
    """
    if seat.reviews and args.profile in excluded_from_review(args.reviewing, authorship):
        why = "named" if args.profile == args.reviewing else "named_author"
        return None, same_profile_refusal(seat, args.reviewing, why, authorship, named=args.profile)
    return (
        Resolution(
            seat.name,
            args.profile,
            args.lane,
            named=True,
            reviewed=args.reviewing,
            authorship=authorship,
        ),
        None,
    )


def _walk_preference(
    seat: Seat, args: argparse.Namespace, now: datetime, authorship: Authorship
) -> tuple[Resolution | None, Refusal | None]:
    """Walk this dispatch's candidate list to the first entry that is dispatchable right now.

    The list is `review_candidates`', not the seat's raw preference: on every seat that
    reviews nothing the two are the same object, and on the review seat every profile the
    issue's records place on the work has been removed and a different lane put first (#322).
    """
    reviewed = args.reviewing
    candidates = review_candidates(seat, reviewed, authorship)
    if not candidates:
        return None, same_profile_refusal(seat, reviewed, "list_offers_nothing_else", authorship)
    passed: list[PassedOver] = []
    for name in candidates:
        found = candidate_refusal(args, seat.name, name, now)
        if found is None:
            return (
                Resolution(
                    seat.name,
                    name,
                    PROFILES[name].lane,
                    named=False,
                    passed_over=tuple(passed),
                    reviewed=reviewed,
                    authorship=authorship,
                ),
                None,
            )
        passed.append(PassedOver(name, found.kind, found.failure_class))
    return None, exhausted_refusal(seat, tuple(passed), reviewed, authorship)


def routed(args: argparse.Namespace, route: Resolution) -> argparse.Namespace:
    """Return the request with the resolved route written into it, mutating nothing.

    Every rung below resolution reads the request, and none of them may care *how* the
    route was arrived at — that is ADR-0071 ruling 2's rule that a refusal attaches to a
    `(profile, seat)` pair rather than to the resolution path, expressed as an argument
    they are not given rather than as a discipline they are asked to keep. So resolution
    completes the request and the ladder climbs one that is complete, exactly as it did
    when every caller typed the pair by hand.

    A copy, because the caller's namespace is `main`'s parsed argv and a rung that read a
    lane the caller never typed would make `--dry-run` print a request nobody made.

    **The seat's permission mode is completed here too, and that is a force rather than a
    default** (ADR-0071 ruling 4, #322). `--permission-mode` defaults to `acceptEdits`,
    which is writable on both runner families, so a review dispatched with the caller
    passing nothing could edit the persistent tree. Overwriting whatever the caller passed
    is deliberate: the seat must always enter its runner-specific `plan` policy, while the
    disposable worktree is the filesystem boundary that prevents those edits from reaching
    the reviewed ref. It is never silent — `Resolution.containment_lines` names the seat
    that forced it, in the dry run and in the record's own argv.

    Here rather than in `build_argv`, because a seat is a property of the *route* and
    `build_argv` is handed a lane and a profile: putting it there would mean the record's
    `permission_mode` field and the runner's own flags could disagree, since both are read
    from this namespace afterwards.
    """
    chosen = copy.copy(args)
    chosen.lane = route.lane
    chosen.profile = route.profile
    forced = SEATS[route.seat].permission_mode
    if forced:
        chosen.permission_mode = forced
    return chosen


def assert_worktree(assigned: Path, observed: str) -> Refusal | None:
    """Refuse unless the assigned path is its own git top level (#105's fourth instance).

    `observed` is what `git rev-parse --show-toplevel` printed inside `assigned`, or the
    empty string when git gave no answer — which is both git refusing and git never
    starting, an absent directory being the latter (see `git`). Both halves are failures
    worth naming: a path that is not a worktree root at all, and a path that resolves into
    somebody else's tree.
    """
    if not observed:
        return Refusal(
            "worktree_unreadable",
            (f"assigned={assigned}",),
            (
                "git could not name a top level there, so the assignment cannot be "
                "verified. Nothing was run. Create the worktree with `just worktree add`."
            ),
            failure_class="infra_unavailable",
        )
    actual = Path(observed).resolve()
    if actual != assigned.resolve():
        return Refusal(
            "worktree_mismatch",
            (f"assigned={assigned}", f"actual={actual}"),
            (
                "The dispatched process was placed somewhere other than its assignment "
                "and refused rather than working there (#105). Nothing was run. Report "
                "both paths; never reset either tree."
            ),
        )
    return None


# The single-shot contract every dispatch carries (#279). A detached session gets no
# second turn: a background completion's notification wakes nobody (the #279 dispatch that
# armed its gate in the background ended uncommitted, and `just land` refused `dirty_tree`),
# and a question ends the run with no caller listening (the revert dispatch that asked
# whether to run `git checkout --` left main broken another cycle). `default_brief` below
# carries this verbatim, and `tools/brief.py` imports the same constant so the composed
# brief and the default brief are one rule in one home and cannot drift apart.
SINGLE_SHOT_CONTRACT: Final = (
    "A dispatched session is single-shot: it has no second turn for a background completion"
    " or a question. Run awaited work in the foreground; decide routine ambiguities, act,"
    " and record the reasoning. If a choice is genuinely the human's, finish the unambiguous"
    " part and state exactly what remains and why."
)

# The retro fix-round rule (#374, #681). One wording reaches both briefing paths, so the
# home is here rather than in `tools/brief.py`: `brief` imports `dispatch`, never the
# reverse, so a constant the default brief must read cannot live there without a cycle —
# the same import direction that puts SINGLE_SHOT_CONTRACT above. The third home, the retro
# skill file, was already rejected on #374: it is human sign-off gated, so a rule landing
# there would govern no pass until signed. `default_brief` emits it under the registry's
# `owes_fix_round_report` column, as `tools/brief.py` does — one predicate for both brief
# paths (#681), because a retro dispatched without `--brief-file` takes that path, and an
# unswept issue is silent by construction — the failure #374 exists to prevent.
FIX_ROUND_RULE: Final = (
    "Fix-round report: list every issue this pass filed with one verdict — `unchanged` or"
    " `corrected`; state what changed for `corrected`, or why `unchanged`. Derive each verdict"
    " from this round's own sweep, or transcribe a deriver's with attribution; never inherit"
    " a prior report wholesale. A landing takes one review round, and findings `medium` and"
    " below are filed rather than fixed (ruled 2026-08-18, #217) — so the issues this pass"
    " filed are the main product of a review, and an issue missing from this list is a"
    " defect in that product, not leftover tidying."
)

# The report is the reviewer's judgement; only its transport belongs to the harness. One
# wording reaches both briefing paths: `default_brief` below and `tools/brief.py`'s composed
# review protocol. Keeping `gh` out of the session removes all four #496 failure paths without
# widening the non-landing seat. Exact markers keep runner output outside the final response out
# of the comment; the visible notice says which stream and section the harness actually saw.
# The dispatcher still makes only one attempt, so this promises visibility on failure rather
# than reliable GitHub availability.
REVIEW_REPORT_BEGIN: Final = "<!-- arma-cti-review-report:begin -->"
REVIEW_REPORT_END: Final = "<!-- arma-cti-review-report:end -->"
REVIEW_CAPTURE_NOTICE: Final = (
    "> Review delivery captured only the bounded final-response section from child stdout. "
    "Output outside its markers and output on other streams were not posted; the harness "
    "cannot verify findings omitted from that section."
)
# GitHub's issue-comment limit is characters, not encoded bytes. Count Python's decoded
# characters after assembling the body so a bounded multi-byte report is not refused.
REVIEW_COMMENT_MAX_CHARS: Final = 65_536
# A valid UTF-8 character uses at most four bytes. This read cap lets a plan remain eligible
# for the character-bound check while still bounding the recovery read.
REVIEW_PLAN_READ_MAX_BYTES: Final = REVIEW_COMMENT_MAX_CHARS * 4
REVIEW_UNBOUNDED_NOTICE: Final = (
    "> **UNMARKED STDOUT — extent unverified.** This review produced no prescribed report "
    "boundary, "
    "so the harness cannot tell which part of the stream is the report or whether any of it is "
    "complete. Nothing here is a recorded verdict. Read it as raw output, not as a review."
)
REVIEW_OVERSIZE_NOTICE: Final = (
    "> **UNVERIFIED RECOVERY — content not posted.** Recovered review text exceeded the issue-"
    "comment size limit. The dispatcher did not truncate it, because a shortened review could "
    "look complete. Nothing here is a recorded verdict, and no review loop advanced."
)


class ReviewWindow(NamedTuple):
    """The child lifetime used to attribute a plan-file write to one dispatch."""

    started_ns: int
    ended_ns: int
    started_at: datetime
    ended_at: datetime


REVIEW_DELIVERY_PROTOCOL: Final = (
    "Put your review report, including an explicit clean verdict when you find nothing,"
    f" between exact lines `{REVIEW_REPORT_BEGIN}` and `{REVIEW_REPORT_END}` in your final"
    " response. Put no finding outside those lines or on another stream: the harness cannot"
    " identify it there. Do not call `gh` and do not write a body file. After you exit, the"
    " unsandboxed dispatcher posts only that bounded stdout section, prefaced by an explicit"
    " capture notice, using exactly one `gh issue comment` call with the host's credentials."
    " A marker counts only as an exact whole line of that captured stdout — a styled,"
    " prefixed or indented rendering of one is ordinary text — and the pair must appear"
    " exactly once across everything you print, not only in the final response."
    " Missing, duplicated or reversed markers, an empty bounded section, or a refused post"
    " ends the dispatch with `review_delivery_failed`. On that refusal the host may post"
    " bounded unmarked stdout and regular files in this dispatch's scoped plan directory"
    " whose modification time falls within this child's window, each labelled as unverified"
    " text. If more than one candidate falls in that window, no plan file is posted and the"
    " refusal carries `plan_reason=plan_ambiguous` and its count without their contents. A"
    " plan filename is never an attribution method. The refusal remains, with no verdict,"
    " loop advance or retry (#496, #599)."
)

POST_LANDING_REVIEW_PROTOCOL: Final = (
    "This is the post-landing review, not a duplicate dispatch. The change is already on"
    " `origin/main`, so no landing decision rides on this pass. It is retained as the only"
    " remaining catch for a real finding an arbiter dismissed. Route findings as follows: a"
    " defect becomes a new `needs-triage` issue naming the reviewed issue and SHA; an"
    " observation becomes a comment on the reviewed issue; a claim not upheld is recorded on"
    " the reviewed issue as checked and not upheld."
)


def default_brief(
    identity: Identity,
    worktree: Path,
    thread_report: gate_report.GateReport | None = None,
) -> str:
    """Compose the brief a dispatch sends when the caller named no file.

    Deliberately thin: it states the assignment and points at the issue, because a
    default that invented instructions would be a second, untracked copy of the seat's
    contract. The single-shot contract is the one operational rule a thin brief cannot
    omit, because a dispatched session has no second turn to recover from missing it.

    The gate line varies by seat, and a review brief additionally carries a dispatcher-derived
    post-landing paragraph when its reviewed SHA is already on ``origin/main``. A forced
    `plan` seat still cannot affect a landing, and the dated human ruling says that review and
    recon do not re-run the implementer's gate; the disposable tree is a containment
    capability, not a revision of that instruction. `Seat.judgement_only` is the predicate for
    the no-gate arm.

    A retro brief also carries the fix-round rule (#681). That widening is deliberate and
    costs none of the thinness above: the text is FIX_ROUND_RULE's, one home that
    `tools/brief.py` imports too, so the default path carries no copy of its own to drift.
    """
    judgement_only = SEATS[identity.seat].judgement_only
    gate_line = (
        (
            "Run no gate and re-run none of the implementer's tests — you are passed their"
            " report instead, and the wall time is the reason (human ruling 2026-08-14 on #353,"
            " as clarified 2026-08-20 on #449); read what the issue thread and the repository"
            " carry. "
            + (
                "The dispatcher-supplied gate-report section below is the record; do not call"
                " `gh` to obtain that report. Reading the supplied record is this seat's work,"
                " not a breach of that (#421)."
                if SEATS[identity.seat].reviews
                else "Reading is this seat's work, not a breach of that (#421)."
            )
        )
        if judgement_only
        else (
            f"Run `just fast` after every edit. Before review, post the implementer's gate report"
            f" on #{identity.issue}'s issue thread. Begin its first line with the marker"
            f" `{gate_report.MARKER}`; an optional suffix may follow after a space."
        )
    )
    post_landing = (
        POST_LANDING_REVIEW_PROTOCOL if is_post_landing_review(identity, worktree) else ""
    )
    post_landing_spacing = "\n\n" if post_landing else ""
    rendered = (
        f"You are the {identity.seat} seat, dispatched as {identity.dispatch_id} on the "
        f"{identity.lane} lane under profile {identity.profile}.\n\n"
        f"{SINGLE_SHOT_CONTRACT}\n\n"
        f"Worktree: {worktree}\n"
        f"Base SHA: {identity.base_sha}\n"
        f"Issue: #{identity.issue}\n\n"
        f"{post_landing}{post_landing_spacing}"
        f"Read CLAUDE.md, then `gh issue view {identity.issue}`, and do that issue's "
        f"work in the worktree above and nowhere else. The issue's acceptance criteria "
        f"are the contract. {gate_line}\n"
    )
    if SEATS[identity.seat].owes_fix_round_report:
        rendered += "\n" + FIX_ROUND_RULE + "\n"
    if SEATS[identity.seat].reviews:
        if thread_report is None:
            thread_report = gate_report.GateReport(
                gate_report.UNAVAILABLE,
                detail="the planner did not obtain an issue-thread report",
            )
        rendered += "\n" + "\n".join(gate_report.render(identity.issue, thread_report)) + "\n"
        rendered += f"\n{REVIEW_DELIVERY_PROTOCOL}\n"
    return rendered


def git(*args: str, cwd: Path) -> str:
    """Run one git command and return its stdout, or the empty string if it gave no answer.

    "No answer" covers git refusing *and* git never starting. A `cwd` that does not exist
    raises `FileNotFoundError` out of `subprocess.run` before git runs at all, and that is
    the commonest shape here rather than an exotic one: `plan.worktree` comes off the
    record, `just worktree done` removes trees as a matter of routine, and a record naming
    a tree this box no longer has is exactly the record a detached child is handed. Left
    raising, it reached nobody — no `result.json`, so the ledger and `occupancy` saw a
    dispatch that started and never ended — and it made `assert_worktree`'s own
    `worktree_unreadable` branch unreachable for the case that branch most names.

    Both halves collapse to the empty string on purpose: every caller here already reads
    that as "git could not tell me", and no caller can act differently on the difference.
    """
    # S603/S607: fixed literals plus paths this tool computed, and `git` resolves off
    # PATH on purpose — the checkout's toolchain is the caller's.
    try:
        done = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def is_post_landing_review(identity: Identity, worktree: Path) -> bool:
    """Derive a review's post-landing phase from its SHA and ``origin/main`` (#670).

    The caller supplies the reviewed SHA, not a phase declaration. A review is the
    post-landing pass when that SHA is reachable from the dispatcher's ``origin/main``;
    pre-landing review commits are still ahead of that ref. An unreadable ref or commit
    returns ``False`` rather than inventing a phase, keeping the pre-landing brief unchanged.
    """
    seat = SEATS.get(identity.seat)
    if seat is None or not seat.reviews or not identity.base_sha:
        return False
    reviewed_sha = git("rev-parse", identity.base_sha, cwd=worktree)
    if not reviewed_sha:
        return False
    return git("merge-base", reviewed_sha, "origin/main", cwd=worktree) == reviewed_sha


def _every_worktree(cwd: Path) -> tuple[Path, ...]:
    """Every worktree the repository reports, main checkout first; empty where git gave no answer.

    One home for the porcelain read, because two readers of the same listing are two
    chances to disagree about what a worktree is. Empty is git's own "could not tell me"
    (`git` collapses refusal and never-starting to the empty string) and every caller must
    treat it as that, never as "one worktree".
    """
    return tuple(
        Path(line.removeprefix("worktree ").strip())
        for line in git("worktree", "list", "--porcelain", cwd=cwd).splitlines()
        if line.startswith("worktree ")
    )


def main_checkout(cwd: Path) -> Path:
    """Return the main checkout, which is where `.claude/worktrees` lives.

    `git worktree list` puts the main worktree first from any of them, which is
    `tools/worktree.py`'s reasoning and matters here for the same reason: a dispatch
    armed *from inside* a worktree must default its assignment to a sibling under the
    main checkout, not to `<this worktree>/.claude/worktrees/…`, which is nowhere.
    """
    trees = _every_worktree(cwd)
    return trees[0] if trees else cwd


# Where a `codex` dispatch sends its telemetry. This is on **argv, per invocation**, and
# not in `~/.codex/config.toml`, for the same reason `ANTHROPIC_BASE_URL` is not in a shell
# profile: a box-wide setting makes a lane's behaviour a property of the machine. The
# landed config file keeps `metrics_exporter = "none"` (#230), so a Codex run the human
# starts by hand exports nothing anywhere — off-box or on — and only a dispatched one
# exports, to loopback. Verified live (#243): all seven OTLP batches of the first Codex
# turn arrived at a loopback sink and none reached the Statsig endpoint's host.
#
# The signal path is spelled out because Codex POSTs to the endpoint **verbatim** rather
# than appending `/v1/metrics` to a base — measured by watching a sink receive every batch
# on `/`, which the collector's OTLP receiver would have refused.
CODEX_OTLP_METRICS: Final = "http://127.0.0.1:4318/v1/metrics"

# How a Claude permission mode reads in Codex's vocabulary. `codex exec` has no
# `--ask-for-approval` at all — it is non-interactive by construction — so the whole of the
# mapping is the sandbox policy. `bypassPermissions` is the one mode that must name the
# dangerous flag, because nothing milder in Codex's vocabulary means it.
CODEX_SANDBOX: Final = {
    "acceptEdits": ("--sandbox", "workspace-write"),
    "plan": ("--sandbox", "read-only"),
    "default": ("--sandbox", "read-only"),
    "bypassPermissions": ("--dangerously-bypass-approvals-and-sandbox",),
}


def _codex_sandbox_argv(
    permission_mode: str,
    granted: tuple[Path, ...] | None,
    *,
    disposable_worktree: bool = False,
) -> tuple[str, ...]:
    """Return Codex's per-runner sandbox policy, with no git directory in its grants.

    The human ruled on 2026-08-06 (#221 decision 2, #259) that a dispatched Codex session
    gets the same *intent* as the widened `zai` allowlist — run the gate, make its own
    commit, land it — and left the mechanism to be worked out, with one option ruled out by
    name: `--dangerously-bypass-approvals-and-sandbox`, which disables the sandbox rather
    than widening it. The ruling also said to **measure before changing**.

    Six arrangements were measured, and the commit half is not reachable from any of them.
    **Codex deliberately enforces `<root>/.git` as a read-only path inside every writable
    root**: it is protecting git history from the agent, which is a defensible thing for a
    coding sandbox to do, and it is a policy rather than a bookkeeping accident. Where the
    root *is* a git directory there is no `.git` to protect, so one is created, and libgit2
    opens that empty directory instead of the real layout — which is why naming a git
    directory buys the commit and loses `cog check`. The sandbox says so in its own words
    when the path it wants to enforce is already occupied (`d-20260818-111104-5138a7`)::

        error building bubblewrap command: Fatal error: cannot enforce sandbox read-only
        path …/issue-405c.gitdir/.git because it crosses writable symlink
        …/issue-405c.gitdir/.git

    Refuted, each by measurement rather than by argument: the linked worktree with both git
    directories named (`d-20260806-172045-9a0a0e`, `cog check` red on `could not find
    repository`, mechanism confirmed by strace in `d-20260807-222221-1a2c7e`); the parent
    `<main>/.git/worktrees` named instead (`d-20260808-075346-f27564`, `index.lock` still
    read-only — the carve-out confers nothing on a nested directory); the standalone clone,
    which removed this project's worktree layout as a variable and did not move the failure
    (`d-20260818-080724-50f2be`); `--separate-git-dir` outward and inward; and the symlink
    above. The name `.git` is not the key either — probe `issue-405b` put the git directory
    at `<cwd>/_gitdir` and its `index.lock` was read-only all the same, because Codex
    discovers the repository's git directory rather than matching a name.

    **The green half is what this function is built on.** Under that same probe, with no
    git directory a writable root, `cog check` returned `No errored commits`: a Codex
    session runs the gate. So the division of labour is *the session gates, the harness
    commits* — `harness_finish` is the other half, and `CODEX_COMMIT_MESSAGE` is the seam
    between them. Accepting the sandbox's policy rather than fighting it is what makes an
    implementer on this lane real: it runs its own gate, which is the binary capability
    rule's whole demand, and the commit happens where this project already performs
    unsandboxed git acts.

    What is granted, and why each:

    - **The two tool caches `_codex_writable_roots` returns** — `~/.cache/uv` and
      `~/.ansible/tmp` — each measured red, each carrying the walk that found it there,
      and both absolute resolved constants no environment variable reaches, so what goes
      into this argv is what was granted (#405 round four). `~/.cargo` stays
      ungranted: measured unnecessary on 2026-08-06 against a warm registry, unchanged
      since, and the proving dispatch never reached `check-rust` to re-ask the question.
    - **`network_access`**, which defaults off while the gate reads `gh` and `uv` may fetch.
      Proven reachable at `NET_HTTP_200` under the 2026-08-06 probe.

    The main checkout was granted while the session was expected to land: `just land`'s
    final step is `git -C <main checkout> merge --ff-only origin/main`, which writes that
    checkout's working tree. It is not granted now — the session does not land — and its
    removal is a narrowing worth having in its own right, since that root reaches every
    sibling worktree on the box, which is #105's collision surface.

    **This is not parity with the `zai` lane and must not be described as one.** That lane's
    grant is a list of named commands; this one is a filesystem and network policy that every
    command the session runs inherits. Network access in particular is strictly more than the
    `zai` half has: there, only the allowlisted `just land` and `gh` reach the network at all.
    ADR-0061 decision 5's non-commensurability point is the reason the two are stated
    separately in `docs/multi-provider-dispatch.md` rather than claimed equal.

    The forced `plan` mode is not one containment meaning across runners. Claude receives it
    as a permission policy and may execute the gate; Codex receives it as an OS sandbox. For
    a review or recon dispatch, the dispatcher creates a disposable worktree first, so Codex
    maps that mode to `workspace-write` with the measured cache and network grants. The
    worktree is the runner's cwd and the only project path made writable; the verdict binds
    to the reviewed SHA and the dispatcher destroys this tree afterwards. A non-disposable
    Codex plan stays `read-only` and carries no writable-root override.

    **Adding no override on that branch is not the same as the sandbox refusing what the
    override would have granted**, and reading it as such is what shipped a false sentence
    about the `review` seat in #449. Both keys here live under `sandbox_workspace_write`, so
    they describe the `acceptEdits` branch and say nothing about `read-only`'s own policy.
    Measured on 2026-08-20: dispatch `d-20260820-110847-f9b197`, a `review` seat on this
    lane under `--sandbox read-only`, reached the network and posted `gh issue comment 434`
    (comment `5355112577`). What a read-only Codex session may *write* is untested here and
    stays unclaimed.
    """
    effective_mode = (
        "acceptEdits" if disposable_worktree and permission_mode == "plan" else permission_mode
    )
    flags = CODEX_SANDBOX.get(effective_mode, CODEX_SANDBOX["default"])
    if flags != CODEX_SANDBOX["acceptEdits"]:
        return flags
    if granted is None:
        # Unreachable from `plan_dispatch`, which refuses on this same value before it mints
        # an argv. Granting nothing rather than guessing keeps the fallback fail-closed.
        return flags
    roots = ", ".join(hook_parity.toml_string(str(path)) for path in granted)
    return (
        "--config",
        f"sandbox_workspace_write.writable_roots=[{roots}]",
        "--config",
        "sandbox_workspace_write.network_access=true",
        *flags,
    )


def _codex_writable_roots() -> tuple[Path, ...] | None:
    """Return the tool caches a Codex session must write to run the gate — never a git one.

    The grant principle, in one sentence: a tool cache or temp directory outside every
    worktree, writing no project file and no git state, is granted; a git directory never
    is. The second half is #405's finding and the three probes that established it — the
    first half is why everything here is a cache.

    The session's own worktree is already writable and so is not listed — Codex's
    `workspace-write` grants cwd, and `writable_roots` is documented as "additional folders
    (beyond cwd and possibly TMPDIR)".

    **No git directory is ever named here, and that is the whole of #405's finding.** Codex
    enforces `<root>/.git` read-only inside every writable root to protect git history from
    the agent; where the named root *is* a git directory there is no `.git` to protect, so
    the sandbox creates one and libgit2 opens the empty directory instead of the real
    layout. Naming a git directory therefore buys `git commit` and costs `cog check`, and no
    arrangement of paths escapes that — `_codex_sandbox_argv` lists the six that were
    measured and refuted. With no git directory named, the gate runs; the commit is
    `harness_finish`'s, on the unsandboxed side.

    The list is a walk of every stage `just check` and `just fast` shell out to, each entry
    measured red or derived from the tool's own source:

    - **`~/.cache/uv`** — `uv` locks there before any test runs; measured red
      `d-20260806-164224-c3591c`, green since granted.
    - **`~/.ansible/tmp`** — `ansible-playbook --syntax-check` (`check-machine-b`) creates
      its per-run directory there; measured red `d-20260818-185929-ae5491`,
      ``[Errno 30] Read-only file system: '/home/andre/.ansible/tmp/ansible-local-…'``.
      The stage joined `just check` on 2026-08-13 (`178bef4`), a week *after* the
      2026-08-06 measurement that set the uv root — which is why the gate could grow a
      need the root list had already been measured without.

    `~/.cache/ansible-lint` was granted here once, on a derivation from `ansiblelint`'s
    source that the box contradicted: the installed copy reports `INSTALLER=uv`, returns
    before reaching the version check the derivation rested on, and the directory did not
    exist after a gate run. A grant nothing on this box exercises is not containment but
    unreviewed surface, so it is dropped — to return only with a measured red, the way the
    two above each carry theirs.

    What the walk found **not** to need a grant: `cog`, `hemtt`, `gitleaks`, `ruff` and `ty`
    all ran green in-sandbox on `d-20260818-185929-ae5491` with the uv root alone; pytest,
    hypothesis and the mutation smoke ran green in-sandbox on `d-20260806-164858-905eb2`
    (hypothesis tolerates a read-only example database, coverage writes cwd, pytest's
    temporaries live in TMPDIR, which `workspace-write` grants); and `~/.cargo` stays
    ungranted — measured unnecessary on 2026-08-06 against a warm registry, and nothing has
    changed cargo's writes since. That last one is the one entry whose re-proof is still
    outstanding: the proving dispatch died before `check-rust`, so the next writable
    dispatch that reaches it carries the re-measurement.

    Nothing here is derived from the tree any more, which is why this function takes no
    argument: the two roots it used to ask git for were the two it must never name, and a
    parameter that exists only to be discarded invites a future edit to name them again.

    **No environment variable reaches this list** (#405 review round four, human
    instruction). The two locations were read from `UV_CACHE_DIR`, `ANSIBLE_LOCAL_TEMP`,
    `XDG_CACHE_HOME` and `ANSIBLE_HOME` for three rounds, and each round found the same
    defect in a new place: a value validated here was resolved differently somewhere else —
    a relative root frozen into argv and reinterpreted from the child's cwd being the last
    of them. Nothing external is admitted now, so there is nothing left to validate: the
    grant is two absolute resolved constants under `Path.home()`, and a box that genuinely
    keeps a cache elsewhere changes these lines, in a diff, under review. `HOME` is the one
    anchor, because a `HOME` that lies has already won `~/.arma-cti/credentials.env`.

    Resolved here, where the paths are made, so the grant, the record and the sandbox all
    read the same absolute path — an argv entry that could still be relative was High 1's
    whole mechanism. A root that does not exist is not an error: Codex logs it and carries
    on, and `resolve()` is non-strict for exactly that. `None` where the box will not
    canonicalise them, which `writable_root_refusal` turns into a refusal: a path this box
    cannot name absolutely is not one to widen a sandbox with.
    """
    home = Path.home()
    try:
        return ((home / ".cache" / "uv").resolve(), (home / ".ansible" / "tmp").resolve())
    except OSError:
        return None


def writable_root_refusal(project_root: Path, granted: tuple[Path, ...] | None) -> Refusal | None:
    """Refuse where the two granted cache roots will not canonicalise (#405, round four).

    Three rounds of this function validated an environment-supplied path, and each round's
    review found the same defect in a new place: the check resolved one path and something
    downstream resolved another. Round four removes the environment from the grant
    entirely — `_codex_writable_roots` is two absolute resolved constants under
    `Path.home()` — so `UV_CACHE_DIR=/`, a git directory, a relative root reinterpreted
    from the child's cwd, and an honest relocation all reach the sandbox alike: not at all.
    Nothing external is admitted, so no allowlist, no containment walk and no path
    reasoning survives here; a box that keeps a cache elsewhere edits the constants, in a
    diff, under review.

    What is left is the one thing that can still fail: a `HOME` this box will not
    canonicalise. That refuses, and never falls back to an uncanonicalised path — the
    fallback the round-three review named. It runs where the argv is minted, because the
    roots are frozen into the record then and nothing re-derives them later.

    No failure class, for `pair_block`'s reason: the provider is up and nothing was asked
    of the code under test — this project declines to widen a sandbox around a path it
    cannot name absolutely.
    """
    if granted is not None:
        return None
    return Refusal(
        "writable_root_refused",
        (
            f"home={Path.home()}",
            "reason=the granted cache roots would not canonicalise on this box",
            f"project={project_root}",
        ),
        "The sandbox's writable roots are two constants under this box's home directory, "
        "and they would not resolve to absolute paths, so no root is granted and nothing "
        "was dispatched. This is the box's to fix.",
    )


# The seam between a session that cannot commit and a harness that can (#405). Named once
# here: the brief tells the session this path, `harness_finish` reads it, and nothing else
# spells it. It lives in the worktree root because the worktree is the one directory the
# sandbox grants, so there is nowhere else a sandboxed session could put it.
CODEX_COMMIT_MESSAGE: Final = ".dispatch-commit-message"
GATE_CLOCK_DIR_ENV: Final = "CTI_GATE_CLOCK_DIR"
REVIEW_DELIVERY_TIMEOUT_S: Final = 30
REVIEW_DELIVERY_DETAIL_LIMIT: Final = 500

# What a sandboxed session is told about the division of labour, appended to whatever brief
# the dispatch carries. Appended rather than composed into `tools/brief.py`, because the lane
# is resolved here and not there: a seat resolves its profile at dispatch time, so the
# composer cannot know whether its brief will be sent to a sandboxed runner, and a rule the
# orchestrator has to remember to include is a rule that will one day be missing.
CODEX_COMMIT_PROTOCOL: Final = f"""
## Committing on this lane: you gate, the harness commits

Codex's sandbox holds this repository's git directory read-only. That is deliberate policy
on Codex's side — it protects git history from the agent — and #405 measured six
arrangements of writable roots without finding one that lifts it and still lets `cog check`
open the repository. So `git add` and `git commit` will refuse here, `just check` and
`just fast` will run, and looking for a way round the refusal is a spent dispatch: do not.

Work as any implementer does — edit in your worktree, gate it there — and instead of
committing, write your Conventional Commits message (subject, body, `refs #<issue>`) to
`{CODEX_COMMIT_MESSAGE}` in the worktree root. When you exit, the dispatcher — which is not
sandboxed — reads that file, commits everything in the tree with it as the message, and
pushes the branch for review. Write the file before you finish: a tree you edited with no
message file in it is a refusal rather than a commit, because a commit nobody wrote a
message for is worse than none. The message goes through `cog verify` like any other, so a
message that is not Conventional Commits fails the commit.

`just land` on the Landing section above is the orchestrator's on this lane, not yours.
"""


def harness_commits(lane: Lane, permission_mode: str, *, disposable_worktree: bool = False) -> bool:
    """Say whether this dispatch's commit is the harness's to make rather than the session's.

    True exactly where the harness must commit a persistent Codex worktree. A disposable
    review or recon tree is deliberately never committed by the harness: its edits are
    evidence for one run and the tree is removed. The mode is compared through
    `CODEX_SANDBOX` rather than against the string `acceptEdits`, so this predicate and
    `_codex_sandbox_argv` cannot disagree about which non-disposable mode is writable.
    """
    if lane.runner_family is not codex_guidance.GuidanceHarness.CODEX:
        return False
    if disposable_worktree:
        return False
    flags = CODEX_SANDBOX.get(permission_mode, CODEX_SANDBOX["default"])
    return flags == CODEX_SANDBOX["acceptEdits"]


def collect_gate_clock(session_directory: Path, canonical: Path) -> tuple[str, ...]:
    """Append one session-local gate-clock file once, separating an unterminated tail."""
    source = gate_clock.records_path(session_directory)
    try:
        payload = source.read_bytes()
    except FileNotFoundError:
        return ()
    except OSError as error:
        return (f"gate_clock_collection=failed cause={error} canonical={canonical}",)
    try:
        if not payload:
            return ()
        destination = gate_clock.records_path(canonical)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("ab+") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell():
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":
                    payload = b"\n" + payload
            handle.write(payload)
    except OSError as error:
        return (f"gate_clock_collection=failed cause={error} canonical={canonical}",)
    return ()


def _run_child_with_gate_clock(
    plan: Plan,
    child: Mapping[str, str],
    brief: str,
    child_launch_attempted: Callable[[], None],
    child_finished: Callable[[int], None],
) -> tuple[subprocess.CompletedProcess[str], tuple[str, ...]]:
    """Launch the child, capture review stdout, then collect gate-clock rows.

    The review outbox is opened by this unsandboxed process and inherited as stdout. The
    child writes a file descriptor, not a path, so a read-only filesystem cannot strand the
    report. It is anonymous and lives only for this call: delivery gets one later attempt,
    with no stdout orphan to scan; plan-file recovery is separately bounded by the child's
    environment and launch-to-finish window.
    """
    canonical = gate_clock.DEFAULT_GATE_CLOCK_DIR.absolute()
    child_environment = dict(child)
    prefix = f"arma-cti-gate-clock-{plan.identity.dispatch_id}-"
    with tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True) as temporary:
        session_directory = Path(temporary)
        child_environment[GATE_CLOCK_DIR_ENV] = temporary
        with (
            tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
            if SEATS[plan.identity.seat].reviews
            else nullcontext(None)
        ) as review_outbox:
            # S603: argv is the registry's runner plus registry values; the brief is on stdin
            # so nothing a dispatch carries reaches the process table.
            child_launch_attempted()
            done = subprocess.run(  # noqa: S603
                list(plan.argv),
                cwd=plan.worktree,
                env=child_environment,
                input=brief,
                stdout=review_outbox,
                text=True,
                check=False,
            )
            # End the attribution window at the child boundary, before the host reads or
            # echoes captured stdout. A plan written by another process during host-side
            # bookkeeping must not enter this dispatch's recovery set.
            child_finished(done.returncode)
            if review_outbox is not None:
                review_outbox.seek(0)
                done.stdout = review_outbox.read()
                # Keep captured stdout in the ordinary dispatch log too. If delivery fails,
                # the named refusal points at evidence rather than claiming an empty stream.
                if done.stdout:
                    sys.stdout.write(done.stdout)
                    if not done.stdout.endswith("\n"):
                        sys.stdout.write("\n")
                    sys.stdout.flush()
        # A BaseException during collection is a harness failure after the child, never a
        # launch failure; the child boundary was recorded immediately after it returned above.
        collection = collect_gate_clock(session_directory, canonical)
    return done, collection


def commit_carries_dispatch_message(tree: Path, commit: str) -> bool:
    """Say whether a commit's own tree holds `CODEX_COMMIT_MESSAGE` as a tracked path (#550).

    The pre-launch guard asks the working tree, which is the wrong half once a commit
    exists: a file that went *into* the commit leaves `git status` clean, and that is how
    `984a740` reached a review branch with nothing catching it. Whether the path exists in
    the commit's tree is the one question that answers both shapes, and `ls-tree` answers
    it in a single object lookup — cheap enough to sit on the harness's commit path
    permanently rather than only where a route was once observed.

    `ls-tree` rather than `cat-file -e`, because the vet must tell "absent" from "git
    did not answer" and `cat-file -e` cannot: it exits 128 both for a path missing from
    a resolvable tree and for a ref that resolves to nothing, so a guard that swallowed
    its `GitError` answered "no message file committed" on a git that had merely failed
    — the absence-reads-as-healthy shape this store keeps closing (#560). `ls-tree`
    exits 0 with empty output only for the path absent from a tree it read, so every
    `GitError` it raises here — unresolvable ref, broken object store, the timeout that
    killed git before it answered — is re-raised to the caller rather than answered.
    """
    listing = worktree_tool.git("ls-tree", commit, "--", CODEX_COMMIT_MESSAGE, cwd=tree)
    return bool(listing.strip())


def harness_start_refusal(worktree: Path) -> Refusal | None:
    """Refuse before the session launches where the tree is not provably empty (#405).

    Review's High 2: `harness_finish` commits everything in the tree with `git add --all`,
    so a finished predecessor's `.dispatch-commit-message` and its edits — surviving in a
    worktree because nothing refused — would be swept into this run's commit and pushed
    under this run's issue. The exact-list test missed it because the tree was clean. This
    rung is #105's rule at the new place the failure moved to: files you did not write are
    evidence, so refuse and report rather than absorb them.

    The message file is asked about first, because the two findings say different things
    to a reader: a surviving `CODEX_COMMIT_MESSAGE` is a predecessor's uncommitted
    handover — the recovery runbook's, not a collision in progress — while a dirty tree
    without one is the ordinary foreign-files shape, and reuses `classify_preflight`'s
    `dirty_tree` refusal with an action written for this caller.

    It runs in `run_dispatch` rather than at plan time, beside the credential re-check:
    the child is what launches, and a refusal here writes a `result.json`, so the worktree
    stops being occupied the moment the refusal lands rather than after a full run.
    """
    message_path = worktree / CODEX_COMMIT_MESSAGE
    if message_path.exists():
        return Refusal(
            "dispatch_message_present",
            (f"worktree={worktree}", f"file={message_path}"),
            "A dispatch-commit message is already in this worktree, so a predecessor's "
            "uncommitted handover is sitting in the tree this run was assigned — its "
            "message and its edits belong to that run, and a harness that committed them "
            "here would attribute them to this one. Nothing was launched. Follow "
            "`docs/agents/recovery.md` for the predecessor's run, and never reset the "
            "tree (#105).",
        )
    try:
        status = worktree_tool.read_status(worktree_tool.git("status", "--porcelain", cwd=worktree))
    except worktree_tool.GitError as failure:
        return Refusal(
            "git_failed",
            (
                f"worktree={worktree}",
                f"command=git {' '.join(failure.args_run)}",
                f"stderr={failure.stderr}",
            ),
            "Git would not answer for this worktree, so nothing about its contents could "
            "be checked before launching. Nothing was dispatched.",
        )
    found = worktree_tool.classify_preflight(
        worktree,
        status,
        "The worktree this dispatch was assigned is not clean, so every file in it is "
        "evidence of work this run did not do — and a harness commit sweeps all of it "
        "into this run's push (#105). Nothing was launched. Find whose work it is and "
        "land or recover it first; never reset the tree.",
    )
    if found is None:
        return None
    # The worktree module's refusal carries no failure class, and this is a conversion
    # rather than a restatement: `_from_stop`'s reason, for the third module it holds.
    return Refusal(found.kind, found.found, found.action)


def harness_finish(  # noqa: PLR0911 — one return per end state, so no refusal hides inside another
    tree: Path, issue: int, record: Path
) -> tuple[tuple[str, ...], int]:
    """Commit what a sandboxed session edited, with the message it left, and push it (#405).

    The unsandboxed half of the division of labour `_codex_sandbox_argv` records. It runs
    in the dispatcher after the session has exited, so it is subject to nothing the sandbox
    holds — and to everything else: `git commit` here fires the repository's own
    `commit-msg` hook, so a session's message meets `cog verify` exactly as a Claude-side
    session's would.

    Four states, and each is a distinct answer rather than a shade of the same one:

    - **A clean tree** is `nothing_to_commit` and not a refusal. A dispatch that read,
      searched or found nothing to change is a legitimate run, and a harness that invented
      an empty commit for it would be recording an act nobody performed.
    - **Edits with a message** is the commit, followed by the push to the issue's review
      ref, which is `review_exchange.exchange`'s — the same ref, the same verification that
      the remote resolves this exact HEAD, and no second convention for a reviewer to learn.
    - **Edits with no message** is `commit_message_absent`, and it leaves the tree exactly
      as the session left it. The alternative is a commit with a message the harness made
      up, which is unreviewable and unattributable; a named refusal over an untouched tree
      can be finished by hand from the transcript, which nothing else can.
    - **git refusing** is `git_failed` with git's own words, which is where a message that
      is not Conventional Commits arrives. The add and the commit are asked separately
      (review round three's Medium), so each refusal is true of the command that refused:
      the add's claims no staging state it cannot know, the commit's names the staging
      the add left behind.
    - **A commit carrying the message file** is `dispatch_message_committed`, asked of the
      commit's tree between the commit and the push (#550): the artefact must be refused
      where a reviewer would otherwise find it, downstream, reading a diff stat. A git
      that will not answer that vet is `git_failed` with the push held, never a clean
      negative (#560).

    The message file is moved out of the tree before anything is staged — read, written
    beside the dispatch record where the run's other evidence lives, then unlinked — so it
    can never enter the commit it describes, and so a reader of the record can see what the
    session asked for even when the commit was refused.

    Authorship is untouched: the commit carries the box's git identity, as a hand-finished
    Codex commit did, and what attributes the work to a profile is the dispatch record. A
    `--author` invented from a profile name would be a claim about a person.
    """
    message_path = tree / CODEX_COMMIT_MESSAGE
    try:
        message = message_path.read_text(encoding="utf-8") if message_path.is_file() else ""
        if message_path.is_file():
            kept = record / "commit-message.txt"
            kept.write_text(message, encoding="utf-8")
            message_path.unlink()
        status = worktree_tool.read_status(worktree_tool.git("status", "--porcelain", cwd=tree))
    except UnicodeDecodeError as undecodable:
        return _harness_refusal(
            "commit_message_unreadable",
            (f"worktree={tree}", f"file={message_path}", f"found={undecodable}"),
            "The session's message is not UTF-8 text, so the harness has nothing to commit "
            "with and has committed nothing. The file is untouched in the tree and the tree "
            "is as the session left it. Read the run's log, recover the message it meant, "
            "and commit by hand — never reset the tree (#105).",
        )
    except OSError as unreachable:
        return _harness_refusal(
            "commit_message_unreadable",
            (f"worktree={tree}", f"file={message_path}", f"found={unreachable}"),
            "The session's message could not be moved out of the tree, so nothing was "
            "committed and the tree is as the session left it. This is the box's to fix.",
        )
    except worktree_tool.GitError as failure:
        return _harness_git_failed(tree, failure, record)
    if status.clean:
        return (("harness_commit=nothing_to_commit", f"worktree={tree}"), 0)
    if not message.strip():
        return _harness_refusal(
            "commit_message_absent",
            (f"worktree={tree}", f"expected={message_path}", *_harness_found(status)),
            "The session edited this tree and left no commit message at the path above, so "
            "the harness has nothing to commit with and has committed nothing. The edits "
            "are untouched. Read the run's log for what it did, write the message, and "
            "commit by hand — never reset the tree (#105).",
        )
    try:
        worktree_tool.git("add", "--all", cwd=tree)
    except worktree_tool.GitError as failure:
        # Review round three's Medium: the add's refusal must not carry the commit's
        # text. `git add` can stage part of a tree and still refuse, so this says what is
        # known — nothing was committed, nothing pushed — and sends the reader to the
        # tree's own status rather than asserting a staging state it cannot know.
        return _harness_refusal(
            "git_failed",
            (
                f"worktree={tree}",
                f"command=git {' '.join(failure.args_run)}",
                f"stderr={failure.stderr}",
            ),
            "`git add --all` itself was refused, so the commit was never attempted and "
            "nothing was pushed. Read git's own error above, and read the tree's status "
            "before acting — the add may have staged part of the tree before refusing. "
            "The edits are untouched, and the message the session left is beside the "
            "record as commit-message.txt; finish by hand from there — never reset the "
            "tree (#105).",
        )
    try:
        worktree_tool.git("commit", "--file", str(record / "commit-message.txt"), cwd=tree)
    except worktree_tool.GitError as failure:
        # The refusal cannot claim the tree is as the session left it, because `git add
        # --all` ran first: every edit is staged and the message file is already gone.
        # #105's rule stops this from resetting the staging away: what the harness did to
        # the tree is named rather than undone, so the reader judges the evidence as found.
        return _harness_refusal(
            "git_failed",
            (
                f"worktree={tree}",
                f"command=git {' '.join(failure.args_run)}",
                f"stderr={failure.stderr}",
            ),
            "Read git's own error above, and read the tree before acting: `git add --all` "
            "ran before the commit was refused, so every edit is staged and nothing is "
            "committed. The tree is not as the session left it. The message is preserved "
            "beside the record as commit-message.txt; finish by hand from there — never "
            "reset the tree (#105).",
        )
    return _harness_publish(tree, issue)


def _harness_publish(tree: Path, issue: int) -> tuple[tuple[str, ...], int]:
    """Publish the commit `harness_finish` just made: read it back, vet it, push it.

    Everything that is owed once the commit exists. The SHA is read back rather than
    assumed; the commit's own tree is asked whether it carries `CODEX_COMMIT_MESSAGE`
    (#550), because a file that went *into* a commit leaves `git status` clean and that
    is how `984a740` reached a review branch; and only then does the push run, so both
    refusals hold it. This tail is a function because `harness_finish` sat at the
    complexity limit and #550's vet crossed it — the publish half is a nameable unit,
    and cutting there rather than suppressing the lint keeps every refusal visible as
    its own return in whichever function renders it.
    """
    try:
        committed = worktree_tool.git("rev-parse", "HEAD", cwd=tree).strip()
    except worktree_tool.GitError as failure:
        return _harness_refusal(
            "git_failed",
            (
                f"worktree={tree}",
                f"command=git {' '.join(failure.args_run)}",
                f"stderr={failure.stderr}",
            ),
            "The commit was made and its SHA could not be read back, so the push was not "
            "attempted. Read git's own error above; the message the session asked for is "
            "beside the record as commit-message.txt.",
        )
    try:
        carried = commit_carries_dispatch_message(tree, committed)
    except worktree_tool.GitError as failure:
        return _harness_refusal(
            "git_failed",
            (
                f"worktree={tree}",
                f"command=git {' '.join(failure.args_run)}",
                f"stderr={failure.stderr}",
            ),
            "The commit was made and the vet that asks whether its tree carries "
            "`.dispatch-commit-message` could not be answered, so the push was not "
            "attempted. This refusal is not a clean answer: the guard did not run, and "
            "it must not be read as 'no message file committed'. Read git's own error "
            "above and re-ask it by hand before pushing — the commit is real and local, "
            "and the message the session asked for is beside the record as "
            "commit-message.txt.",
        )
    if carried:
        return _harness_refusal(
            "dispatch_message_committed",
            (f"worktree={tree}", f"commit={committed}", f"file={CODEX_COMMIT_MESSAGE}"),
            "The commit the harness just made carries `.dispatch-commit-message` as a "
            "tracked path, so the artefact reached a commit rather than only the tree "
            "(#550) — a clean `git status` cannot see this, because the file went into "
            "the commit instead of being left in it. The push was held, so it has not "
            "reached a review ref. Strip it and amend — `git rm --cached "
            ".dispatch-commit-message` then `git commit --amend --no-edit` — never reset "
            "the tree (#105); the message is preserved beside the record as "
            "commit-message.txt. The amend leaves the working-tree copy of the file "
            "behind as untracked, and `.gitignore` hides it from `git status`, so delete "
            "it as well: the next dispatch into this tree refuses "
            "`dispatch_message_present` until it is gone (#560).",
        )
    pushed = review_exchange.exchange(tree, issue)
    return (
        ("harness_commit=committed", f"commit={committed}", *pushed.lines),
        pushed.code,
    )


def _harness_refusal(kind: str, found: tuple[str, ...], action: str) -> tuple[tuple[str, ...], int]:
    """Render one post-child harness refusal in the dispatcher's own shape."""
    return (Refusal(kind, found, action).lines(), EXIT_REFUSED)


def _review_delivery_detail(detail: str) -> str:
    """Keep a process failure on one bounded result line, never the report body."""
    return " ".join(detail.split())[:REVIEW_DELIVERY_DETAIL_LIMIT]


def _bounded_review_report(captured_stdout: str) -> tuple[str, str, str]:
    """Extract one exact report-marker pair, or explain why stdout is not postable.

    Exactness is the whole rule (#584): only a line byte-identical to a marker is one, so
    a transcript's styled, prefixed or indented re-rendering of the pair is ordinary text.
    The triple pairs read off #581's dispatch log lived on that other surface — the log
    interleaves the child's stderr with this dispatcher's echo of captured stdout, so one
    emitted pair can appear there several times — while the captured stream this function
    judged held exactly one exact pair, proven by the posted comment existing at all:
    every other count refuses below and posts nothing.
    """
    if not captured_stdout.strip():
        return "", "report_empty", "captured stdout is empty"
    lines = captured_stdout.splitlines()
    begins = [index for index, line in enumerate(lines) if line == REVIEW_REPORT_BEGIN]
    ends = [index for index, line in enumerate(lines) if line == REVIEW_REPORT_END]
    if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
        detail = f"expected one ordered marker pair; found begin={len(begins)} end={len(ends)}"
        return "", "report_unbounded", detail
    report = "\n".join(lines[begins[0] + 1 : ends[0]]).strip("\r\n")
    if not report.strip():
        return "", "report_empty", "bounded report section is empty"
    return report, "", ""


class _PlanCapture(NamedTuple):
    """One plan-file candidate and the text the host could safely read from it."""

    path: Path
    content: str | None
    size_bytes: int
    reason: str = ""


class _ReviewRecovery(NamedTuple):
    """Raw review text that can be posted without making a judgement about it."""

    body: str
    source_labels: tuple[str, ...]
    source_sizes: tuple[tuple[str, int], ...]
    plan_paths: tuple[Path, ...]
    oversized_sources: tuple[str, ...]
    plan_candidate_count: int


class _ReviewPlanScan(NamedTuple):
    """Scoped plan candidates and captures, with ambiguity retained without file contents."""

    captures: tuple[_PlanCapture, ...]
    candidate_count: int


def _review_plan_directory(environment: Mapping[str, str]) -> Path | None:
    """Resolve only the dispatch-scoped plan directory explicitly passed to the child."""
    value = environment.get(REVIEW_PLAN_DIRECTORY_ENV, "")
    if not value:
        return None
    directory = Path(value)
    return directory if directory.is_absolute() else None


def _read_review_plan_candidate(  # noqa: PLR0911 — each refusal is a distinct attribution/read boundary
    path: Path,
    expected_mtime_ns: int,
) -> _PlanCapture | None:
    """Read one stable regular file, refusing a candidate that changes while read."""
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_mtime_ns != expected_mtime_ns:
            return None
        if before.st_size > REVIEW_PLAN_READ_MAX_BYTES:
            after = path.lstat()
            if (
                after.st_mode != before.st_mode
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_size != before.st_size
            ):
                return None
            return _PlanCapture(path, None, after.st_size, "oversize")
        with path.open("rb") as source:
            payload = source.read(REVIEW_PLAN_READ_MAX_BYTES + 1)
        after = path.lstat()
    except OSError:
        return None
    if (
        after.st_mode != before.st_mode
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_size != before.st_size
        or len(payload) != after.st_size
    ):
        return None
    if len(payload) > REVIEW_PLAN_READ_MAX_BYTES:
        return _PlanCapture(path, None, after.st_size, "oversize")
    try:
        content = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return _PlanCapture(path, content, len(payload))


def _review_plan_candidate(
    path: Path,
    window: ReviewWindow,
) -> tuple[Path, int] | None:
    """Return one regular in-window path without following symlinks."""
    try:
        metadata = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        return None
    if not (window.started_ns <= metadata.st_mtime_ns <= window.ended_ns):
        return None
    return path, metadata.st_mtime_ns


def _review_plan_captures(
    environment: Mapping[str, str],
    window: ReviewWindow,
) -> _ReviewPlanScan:
    """Find scoped regular files in-window, refusing to choose among multiple candidates."""
    if window.started_ns > window.ended_ns:
        return _ReviewPlanScan((), 0)
    directory = _review_plan_directory(environment)
    if directory is None:
        return _ReviewPlanScan((), 0)
    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name)
    except OSError:
        return _ReviewPlanScan((), 0)
    candidates = tuple(
        candidate
        for path in entries
        if (candidate := _review_plan_candidate(path, window)) is not None
    )
    if len(candidates) > 1:
        return _ReviewPlanScan((), len(candidates))
    captures: list[_PlanCapture] = []
    for path, mtime_ns in candidates:
        capture = _read_review_plan_candidate(path, mtime_ns)
        if capture is not None:
            captures.append(capture)
    return _ReviewPlanScan(tuple(captures), len(candidates))


def _review_comment_text(content: str) -> str:
    """Keep recovered text intact while giving each section one terminal newline."""
    return content if content.endswith("\n") else f"{content}\n"


def _review_plan_notice(record: Path, path: Path, window: ReviewWindow) -> str:
    """Explain the time-window attribution on every posted plan-file section."""
    return (
        f"> **PLAN FILE — content unverified.** Dispatch `{record.name}` selected `{path}` "
        "because its regular-file modification time fell within the dispatch's child window "
        f"({window.started_at.isoformat()} through {window.ended_at.isoformat()}); filename "
        "matching was not used. This transports text only; it does not establish completeness "
        "or judgement. Nothing here is a recorded verdict."
    )


def _review_recovery(
    captured_stdout: str,
    record: Path,
    environment: Mapping[str, str],
    window: ReviewWindow | None,
) -> _ReviewRecovery | None:
    """Compose raw unbounded stdout and time-attributed plan text, never choosing between them."""
    parts: list[str] = []
    labels: list[str] = []
    sizes: list[tuple[str, int]] = []
    plan_paths: list[Path] = []
    oversized_sources: list[str] = []
    stdout_bytes = len(captured_stdout.encode("utf-8")) if captured_stdout.strip() else 0
    stdout_chars = len(captured_stdout) if captured_stdout.strip() else 0
    if stdout_bytes:
        labels.append("stdout")
        sizes.append(("stdout", stdout_bytes))
        if stdout_chars <= REVIEW_COMMENT_MAX_CHARS:
            parts.extend(
                (
                    REVIEW_UNBOUNDED_NOTICE,
                    _review_comment_text(captured_stdout),
                )
            )
        else:
            oversized_sources.append("stdout")

    scan = (
        _review_plan_captures(environment, window) if window is not None else _ReviewPlanScan((), 0)
    )
    for index, capture in enumerate(scan.captures, start=1):
        label = f"plan_file_{index}"
        if capture.content is None:
            if capture.reason == "oversize":
                labels.append(label)
                sizes.append((label, capture.size_bytes))
                plan_paths.append(capture.path)
                oversized_sources.append(label)
            continue
        if not capture.content.strip():
            continue
        content_bytes = len(capture.content.encode("utf-8"))
        labels.append(label)
        sizes.append((label, content_bytes))
        plan_paths.append(capture.path)
        if len(capture.content) <= REVIEW_COMMENT_MAX_CHARS and window is not None:
            parts.extend(
                (
                    _review_plan_notice(record, capture.path, window),
                    _review_comment_text(capture.content),
                )
            )
        else:
            oversized_sources.append(label)

    if not labels and scan.candidate_count <= 1:
        return None
    body = "\n\n".join(parts)
    if body and not body.endswith("\n"):
        body += "\n"
    return _ReviewRecovery(
        body,
        tuple(labels),
        tuple(sizes),
        tuple(plan_paths),
        tuple(oversized_sources),
        scan.candidate_count,
    )


def _review_oversize_body(
    record: Path,
    source_sizes: tuple[tuple[str, int], ...],
    attempted_body_bytes: int,
    attempted_body_chars: int,
    *,
    plan_method: bool = False,
) -> str:
    """Render a bounded refusal comment without truncating any recovered text."""
    sizes = " ".join(f"{label}_bytes={size}" for label, size in source_sizes)
    method = (
        " Plan candidates use only regular-file modification times within the dispatch "
        "child window; filename matching was not used."
        if plan_method
        else ""
    )
    return (
        f"{REVIEW_OVERSIZE_NOTICE}\n\n"
        f"dispatch={record.name} limit_chars={REVIEW_COMMENT_MAX_CHARS} "
        f"attempted_body_bytes={attempted_body_bytes} attempted_body_chars={attempted_body_chars} "
        f"{sizes}."
        f"{method}"
    )


def _review_recovery_action() -> str:
    """State that a posted recovery remains refusal, not a verdict."""
    return (
        "The completed review's text was posted only as unverified recovery. The marker "
        "refusal remains: nothing is a recorded verdict, no review loop advanced, and the "
        "dispatcher did not infer completeness or retry (#496). Dispatch a fresh review "
        "before treating any recovered text as a review."
    )


def _review_oversize_action() -> str:
    """State that only a bounded size notice was posted, never a truncated report."""
    return (
        "The completed review exceeded the issue-comment bound. Only an unverified size notice "
        "was posted; content was not truncated. The marker refusal remains: nothing is a "
        "recorded verdict, no review loop advanced, and the dispatcher did not infer or retry "
        "(#496)."
    )


def _review_stdout_has_exact_marker(captured_stdout: str) -> bool:
    """Tell empty-output handling apart from an empty marked section."""
    return any(
        line in (REVIEW_REPORT_BEGIN, REVIEW_REPORT_END) for line in captured_stdout.splitlines()
    )


def _post_review_comment(
    issue: int,
    body: str,
    record: Path,
    parent: Mapping[str, str],
    action: str,
) -> tuple[tuple[str, ...], int]:
    """Make the one bounded host-side post attempt for any review body."""
    log = record / "dispatch.log"
    argv = ["gh", "issue", "comment", str(issue), "--body-file", "-"]
    try:
        posted = subprocess.run(  # noqa: S603 — fixed gh argv plus a validated integer
            argv,
            input=body,
            capture_output=True,
            text=True,
            check=False,
            timeout=REVIEW_DELIVERY_TIMEOUT_S,
            env=dict(parent),
        )
    except subprocess.TimeoutExpired as failure:
        return _harness_refusal(
            "review_delivery_failed",
            (
                f"issue={issue}",
                "reason=gh_timeout",
                f"detail=no answer within {REVIEW_DELIVERY_TIMEOUT_S}s: {failure}",
                f"log={log}",
            ),
            action,
        )
    except (OSError, subprocess.SubprocessError) as failure:
        return _harness_refusal(
            "review_delivery_failed",
            (
                f"issue={issue}",
                "reason=gh_unrunnable",
                f"detail={type(failure).__name__}: {failure}",
                f"log={log}",
            ),
            action,
        )
    if posted.returncode != 0:
        detail = _review_delivery_detail(posted.stderr) or f"exit {posted.returncode}"
        return _harness_refusal(
            "review_delivery_failed",
            (f"issue={issue}", "reason=gh_refused", f"detail={detail}", f"log={log}"),
            action,
        )
    return ((f"review_delivery=posted issue={issue}",), 0)


def deliver_review(  # noqa: PLR0911, PLR0913 — each typed transport exit preserves its refusal
    issue: int,
    captured_stdout: str,
    record: Path,
    parent: Mapping[str, str],
    *,
    child_environment: Mapping[str, str] | None = None,
    review_window: ReviewWindow | None = None,
) -> tuple[tuple[str, ...], int]:
    """Post one bounded review body from the host, or refuse once and stop.

    No GitHub validation read precedes the mutation and no retry follows it. `--body-file -`
    keeps arbitrary findings off argv and removes the child-side body-file requirement that
    failed live on #496. The environment is the dispatcher's parent, not the lane environment,
    so provider credentials and sandbox-injected GitHub state do not decide this call. Both the
    child's environment and `review_window` are required before any plan file can be attributed
    to this dispatch.
    """
    log = record / "dispatch.log"
    report, boundary_refusal, boundary_detail = _bounded_review_report(captured_stdout)
    if boundary_refusal:
        can_recover = boundary_refusal == "report_unbounded" or (
            boundary_refusal == "report_empty"
            and not _review_stdout_has_exact_marker(captured_stdout)
        )
        recovery = (
            _review_recovery(
                captured_stdout,
                record,
                child_environment if child_environment is not None else {},
                review_window if child_environment is not None else None,
            )
            if can_recover
            else None
        )
        if recovery is not None:
            attempted_body_bytes = len(recovery.body.encode("utf-8"))
            oversized = (
                bool(recovery.oversized_sources) or len(recovery.body) > REVIEW_COMMENT_MAX_CHARS
            )
            body = (
                _review_oversize_body(
                    record,
                    recovery.source_sizes,
                    attempted_body_bytes,
                    len(recovery.body),
                    plan_method=bool(recovery.plan_paths),
                )
                if oversized
                else recovery.body
            )
            action = _review_oversize_action() if oversized else _review_recovery_action()
            ambiguity = recovery.plan_candidate_count > 1
            ambiguity_fields = (
                ("plan_reason=plan_ambiguous", f"plan_candidates={recovery.plan_candidate_count}")
                if ambiguity
                else ()
            )
            if ambiguity:
                action = (
                    f"The dispatcher found {recovery.plan_candidate_count} regular plan-file "
                    "candidates in this dispatch's scoped directory during the child window; "
                    "no candidate plan file was posted. "
                    f"{action}"
                )
            if not body:
                return _harness_refusal(
                    "review_delivery_failed",
                    (
                        f"issue={issue}",
                        f"reason={boundary_refusal}",
                        f"detail={boundary_detail}",
                        *ambiguity_fields,
                        f"log={log}",
                    ),
                    action,
                )
            posted_lines, posted_code = _post_review_comment(
                issue,
                body,
                record,
                parent,
                action,
            )
            if posted_code:
                return posted_lines, posted_code
            return _harness_refusal(
                "review_delivery_failed",
                (
                    f"issue={issue}",
                    f"reason={boundary_refusal}",
                    f"detail={boundary_detail}",
                    *ambiguity_fields,
                    "recovery=posted_unverified",
                    f"sources={','.join(recovery.source_labels)}",
                    *(
                        ("plan_method=regular_file_mtime_in_dispatch_window",)
                        if recovery.plan_paths
                        else ()
                    ),
                    f"log={log}",
                ),
                action,
            )
        if boundary_refusal == "report_empty":
            action = (
                "The completed review produced no bounded report. Do not read the missing"
                " comment as a clean review; dispatch a fresh review. The dispatcher will"
                " not retry or recover one automatically (#496)."
            )
        else:
            action = (
                "The completed review's stdout did not contain exactly one ordered report"
                f" boundary. Nothing was posted. Inspect {log}; dispatch a fresh review or"
                " relay only after identifying the report deliberately. The dispatcher will"
                " not infer, retry or recover it automatically (#496)."
            )
        return _harness_refusal(
            "review_delivery_failed",
            (
                f"issue={issue}",
                f"reason={boundary_refusal}",
                f"detail={boundary_detail}",
                f"log={log}",
            ),
            action,
        )
    action = (
        "The completed review was not delivered. Do not read the missing comment as a clean"
        f" review. Its bounded stdout report is in {log}; relay it deliberately after fixing"
        " the host failure. The dispatcher will not retry or recover it automatically (#496)."
    )
    body = f"{REVIEW_CAPTURE_NOTICE}\n\n{report}\n"
    body_bytes = len(body.encode("utf-8"))
    body_chars = len(body)
    if body_chars > REVIEW_COMMENT_MAX_CHARS:
        body = _review_oversize_body(
            record,
            (("bounded_report", len(report.encode("utf-8"))),),
            body_bytes,
            body_chars,
        )
        action = _review_oversize_action()
        posted_lines, posted_code = _post_review_comment(
            issue,
            body,
            record,
            parent,
            action,
        )
        if posted_code:
            return posted_lines, posted_code
        return _harness_refusal(
            "review_delivery_failed",
            (
                f"issue={issue}",
                "reason=report_oversize",
                (
                    f"detail=comment body would be {body_chars} characters; limit is "
                    f"{REVIEW_COMMENT_MAX_CHARS}"
                ),
                "recovery=posted_unverified_size_notice",
                f"log={log}",
            ),
            action,
        )
    return _post_review_comment(issue, body, record, parent, action)


def _harness_git_failed(
    tree: Path, failure: worktree_tool.GitError, record: Path
) -> tuple[tuple[str, ...], int]:
    """Render git's own failure, argv and stderr quoted, the way the exchange renders it.

    The one site left on this helper is the `git status` read, which runs before anything
    is staged: nothing was committed, and the message — if the session left one — has
    already been moved beside the record, which the action names so the reader is not sent
    looking for a file that is no longer in the tree.
    """
    return _harness_refusal(
        "git_failed",
        (
            f"worktree={tree}",
            f"command=git {' '.join(failure.args_run)}",
            f"stderr={failure.stderr}",
        ),
        "Read git's own error above. Nothing was staged and nothing committed; the edits "
        "are untouched, and the message the session left, if any, is beside the record as "
        f"{record / 'commit-message.txt'}.",
    )


def _harness_found(status: worktree_tool.Preflight) -> tuple[str, ...]:
    """Name the edits a refusal is about, capped the way every other ladder caps them."""
    shown = worktree_tool.HOW_MANY_SHOWN
    found = [f"tracked={line}" for line in status.tracked[:shown]]
    found += [f"untracked={line}" for line in status.untracked[:shown]]
    total = len(status.tracked) + len(status.untracked)
    if total > len(found):
        found.append(f"and={total - len(found)} more")
    return tuple(found)


def build_argv(  # noqa: PLR0913 — one complete runner contract
    lane: Lane,
    profile: Profile,
    permission_mode: str,
    project_dir: Path,
    writable_roots: tuple[Path, ...] | None,
    # The builder keeps the lane/profile/mode/path/cache tuple together because it is the
    # exact runner contract; the sixth value is the one issue-specific filesystem boundary.
    *,
    disposable_worktree: bool = False,
    review_plan_dispatch_id: str = "",
) -> tuple[str, ...]:
    """Build the runner's argv, which carries no secret, because a secret on argv is in `ps`.

    The brief goes in on stdin for the same reason it is not a positional prompt: argv
    is world-readable on this box, and a brief quoting an issue is not something to
    publish to every process table reader either. Both families read it there: `claude
    --print` and `codex exec` with no positional prompt both take the task on stdin.

    Dispatching on `lane.runner_family` rather than on `lane.runner` is what keeps two
    lanes that share the `claude` binary sharing one builder.
    """
    if lane.runner_family is codex_guidance.GuidanceHarness.CODEX:
        return _codex_argv(
            lane,
            profile,
            permission_mode,
            project_dir,
            writable_roots,
            disposable_worktree=disposable_worktree,
        )
    argv = (
        lane.runner,
        "--print",
        "--model",
        profile.model,
        "--effort",
        profile.effort,
        "--permission-mode",
        permission_mode,
    )
    if review_plan_dispatch_id:
        argv += (
            "--settings",
            json.dumps(
                {"plansDirectory": f".claude/plans/{review_plan_dispatch_id}"},
                separators=(",", ":"),
            ),
        )
    return argv


def _codex_argv(  # noqa: PLR0913 — policy and cache grants stay together
    lane: Lane,
    profile: Profile,
    permission_mode: str,
    project_dir: Path,
    writable_roots: tuple[Path, ...] | None,
    # See `build_argv`: this is the Codex half of the same complete runner contract.
    *,
    disposable_worktree: bool = False,
) -> tuple[str, ...]:
    """Build `codex exec`'s argv: model, reasoning effort, sandbox, and loopback telemetry.

    Four things differ from the Claude family beyond flag spelling, and each is a
    measured property of the CLI rather than a preference. The fourth — what the sandbox
    has to be widened to before a session can commit and land its own work — is
    `_codex_sandbox_argv`'s, where the measurement that forced it is recorded:

    - Effort is a **config override**, not a flag. There is no `--effort` on `codex exec`;
      the level is `model_reasoning_effort`, set through `-c`.
    - The metrics exporter is overridden here rather than configured on the box, so the
      lane's telemetry travels with the dispatch. See `CODEX_OTLP_METRICS`.
    - Hook trust is bypassed **for this invocation only**. Codex gates a newly seen or
      edited hook behind an interactive "review required" prompt keyed on a stored hash,
      which is the right default for a human at a terminal and a hang for a detached
      child. The flag does not disable hooks — it declines to re-prompt for them — and the
      hooks it then runs are this repository's own committed `.claude/hooks/`, already
      governed by the gate that no session may edit them. Running *without* it would mean
      a dispatch whose enforcement silently did not load, which is the failure ADR-0061
      Decision 4 exists to prevent.

    The hooks themselves ride on `-c` too, translated from `.claude/settings.json` by
    `tools/hook_parity.py` — so a hook landed on `main` reaches this lane by being landed,
    with no second copy to drift. A worktree whose settings carry no hooks contributes no
    overrides, and `--dry-run` is where a caller sees what would be sent.
    """
    return (
        lane.runner,
        "exec",
        "--skip-git-repo-check",
        "--dangerously-bypass-hook-trust",
        "--model",
        profile.model,
        *tuple(
            part
            for override in codex_guidance.loader_overrides()
            for part in ("--config", override)
        ),
        "--config",
        f'model_reasoning_effort="{profile.effort}"',
        "--config",
        _codex_metrics_override(),
        *_codex_hook_argv(project_dir),
        *_codex_sandbox_argv(
            permission_mode, writable_roots, disposable_worktree=disposable_worktree
        ),
    )


def _codex_metrics_override() -> str:
    """Render the `-c` value that sends this dispatch's metrics to the loopback collector."""
    exporter = f'{{ endpoint = "{CODEX_OTLP_METRICS}", protocol = "binary" }}'
    return f"otel.metrics_exporter={{ otlp-http = {exporter} }}"


def _codex_hook_argv(project_dir: Path) -> tuple[str, ...]:
    """Translate this worktree's hook settings into `-c` overrides, or nothing if absent.

    Absent settings are not an error here: `just dispatch --dry-run` is run against
    scratch trees in the unit tier, and a tree with no `.claude/settings.json` has no
    enforcement to carry rather than a broken one. What *would* be an error — a hook
    configured but pointing at a script that is not there — is `Translation`'s to name,
    and `prereqs` is where it is asked.
    """
    settings_path = project_dir / ".claude" / "settings.json"
    if not settings_path.exists():
        return ()
    overrides = hook_parity.config_overrides(hook_parity.read_settings(settings_path), project_dir)
    return tuple(part for override in overrides for part in ("--config", override))


def queue_refusal(args: argparse.Namespace, root: Path) -> Refusal | None:
    """Read the human's dispatch policy before anything is planned (#250).

    The freeze, the ruled WIP limit and the carve-out reservations live in a file outside
    every worktree and are read **per dispatch**, which is what makes a freeze reach a session
    already running — ADR-0042's stale-copy window, closed one level up (`docs/orchestration-
    design.md` §2). An absent or unparseable policy refuses too: a policy nobody can read is
    not a policy that permits, on #41's shape.

    **No override of any kind**, exactly as `off_peak_refusal` has none: no flag, no
    environment variable, no per-dispatch exemption. The two directory options this reads are
    test seams for *where the state lives*, the same seam `CTI_BREAKER_DIR` already is, and
    neither can turn a recorded freeze into a dispatch. (`CTI_ADMISSION_DIR` was a third such
    seam here until #328; it survives as `just trial`'s, and this file reads it no longer.)

    **No failure class**, and the reasoning is the off-peak rung's: CLAUDE.md's table types
    what a run *found*, and this found nothing about any provider, any lane or any code. This
    project declined to start work now.
    """
    store = queue_policy.Store(directory=Path(args.queue_dir).expanduser())
    policy, refusal = queue_policy.read_policy(store)
    if refusal is not None or policy is None:
        return _as_refusal(refusal)
    scan_root = Path(args.queue_root).expanduser() if args.queue_root else root
    in_flight = queue_policy.gather(scan_root, Path(args.dispatch_dir).expanduser())
    # A forced `plan` review or recon dispatch is isolated in its dispatch-owned disposable
    # tree. It therefore contributes no candidate surface to this queue's persistent-tree
    # scan; using the issue's registered surface would attribute the implementer's writes to
    # the reviewer (#339). Derive that boundary from the registry rather than the runner's
    # argv.
    writes_nothing = SEATS[args.seat].judgement_only
    return _as_refusal(
        queue_policy.check_refusal(
            policy,
            args.issue,
            in_flight,
            queue_policy.surfaces_of(in_flight),
            candidate=() if writes_nothing else None,
        )
    )


def _as_refusal(found: queue_policy.Refusal | None) -> Refusal | None:
    """Carry the queue's refusal across, class and all, without restating any of its words."""
    if found is None:
        return None
    return Refusal(found.kind, found.found, found.action, failure_class=found.failure_class)


def _from_stop(found: dispatch_stop.Refusal | None) -> Refusal | None:
    """Carry the stop module's refusal across, for `_as_refusal`'s reason exactly."""
    if found is None:
        return None
    return Refusal(found.kind, found.found, found.action, failure_class=found.failure_class)


def _policy_path(root: Path) -> Path:
    """Resolve the routing policy file the dispatch and the strata read from the same place.

    The bootstrap fallback is #266's own first-landing window: while the policy file is
    being introduced, origin/main cannot yet contain it, so the in-tree candidate is read
    when its main checkout is the one this dispatch runs from. `routing_refusal` and
    `capture_strata` share this so a class refused on and a class recorded cannot be read
    off two different files.
    """
    policy_path = root / routing_policy.POLICY_RELATIVE
    if policy_path.exists():
        return policy_path
    candidate = Path(__file__).resolve().parents[1] / routing_policy.POLICY_RELATIVE
    if candidate.exists() and main_checkout(candidate.parent) == root:
        return candidate
    return policy_path


def _read_routing_policy(root: Path) -> routing_policy.ReadResult:
    """Read the policy on every call — the same no-cache rule `routing_refusal` keeps."""
    return routing_policy.read_policy(_policy_path(root))


def capture_strata(body: str, issue: int, root: Path, *, body_from_file: bool) -> Strata:
    """Compute the three pre-work strata at dispatch time (#323).

    Pure of the request's mutable state: nothing here depends on the lane, the profile or
    any outcome, because the observatory stratifies to keep those out of the comparison.
    The reads are the same ones the brief and the routing rung make — CONTEXT.md for the
    gate, the policy for the class, `gh` for the labels — so a stratum and the line a brief
    prints cannot quietly disagree.

    Gate tier: `derive_gate` is unchecked only when it is undetermined *because* CONTEXT.md
    could not be read. An in-world path decides `regress` without the vocabulary, and a
    readable vocabulary decides everything else — including a genuine `undetermined`, which
    is a stratum and not a failure.

    Routing class: lane-blind `classify_issue`, and seat-blind since #366 deleted `seats` —
    the seat this took could only have added a class the body never declared — so a
    Claude-native dispatch carries the class any other lane would. A body that declares no
    class is the empty string and is distinct from an unreadable policy, which is the
    unchecked state — the third value #323 names, never collapsed with 'no class'.

    Labels: skipped when the body came from `--issue-body`, because that mode arms a
    dispatch where `gh` cannot reach GitHub — there are no labels to fetch, not 'no
    labels'. A `gh` that fails for its own reasons is unchecked for the same reason, with
    its reason recorded.

    The body-reading functions live in `gate`, not `brief`: `brief` imports this module at
    load time, so importing it back here is the cycle that loads a second dispatcher under
    the production `__main__` shape (#323 review finding 3). `gate` owns them and imports
    neither module, so reaching them costs no cycle.
    """
    vocabulary = gate.read_vocabulary(root)
    reached = gate.in_world(gate.named_paths(body))
    derived = gate.derive_gate(body, vocabulary)
    gate_unreadable = not vocabulary and not reached
    gate_tier = (
        Stratum.unknown("CONTEXT.md could not be read, so the vocabulary signal did not run")
        if gate_unreadable
        else Stratum.known(derived.kind)
    )

    read = _read_routing_policy(root)
    if read.policy is None:
        routing_class = Stratum.unknown(read.error)
    else:
        match = routing_policy.classify_issue(read.policy, body)
        # The stable id and the mutable name are recorded as two fields, not an `id:name`
        # string, so renaming a class cannot fragment the history the observatory reads
        # (#323 review finding 6). No match is `RoutingClass("", "")` — a checked absence.
        # The id is coerced to str because the policy holds it as an int and the record's
        # reader validates str: an int on the wire would read back malformed, and the
        # observatory wants one stable spelling across every dispatch either way.
        routing_class = Stratum.known(
            RoutingClass(str(match.rule.id), match.rule.name) if match else RoutingClass("", "")
        )

    if body_from_file:
        labels = Stratum.unknown(
            "body came from --issue-body; labels live on GitHub, which this mode bypasses"
        )
    else:
        fetched, why = readiness.fetch_labels(issue)
        labels = Stratum.unknown(why) if why else Stratum.known(fetched)

    return Strata(gate_tier=gate_tier, routing_class=routing_class, labels=labels)


def routing_refusal(
    args: argparse.Namespace, found: Readiness, root: Path, now: datetime
) -> Refusal | None:
    """Refuse a route the issue declaration's class rules out — the advisory enforcement point.

    The policy is read from the main checkout on every call, never at import or process
    startup. That is how a rule landed after an orchestrator session started reaches its
    next dispatch. A declaration is still only a prediction; `just land` independently
    checks the real diff and is the enforcing gate.

    There is no failure class. Refusing to produce a dispatch found nothing about a
    provider and nothing about code under test, exactly like the spent-attempt refusal.
    """
    # `_read_routing_policy` carries the bootstrap fallback (#266's first landing) and is
    # shared with `capture_strata`, so the class this refuses on and the class the record
    # carries are read off one file and cannot quietly disagree.
    read = _read_routing_policy(root)
    if read.policy is None:
        if args.lane == CLAUDE_LANE:
            return None
        return Refusal(
            "routing_policy_unreadable",
            (f"policy={read.error}", "check=advisory issue declaration"),
            "Keep this dispatch on claude-native until the routing policy can be read. A "
            "policy check that did not run is not a policy clearance (#41).",
        )
    match = routing_policy.advisory_match(
        read.policy,
        found.body,
        routing_policy.Route(args.lane, args.profile, args.seat, now),
    )
    if match is None:
        return None
    return Refusal(
        "routing_policy_advisory",
        (
            "check=advisory issue declaration",
            f"routing_class={match.rule.id}:{match.rule.name}",
            f"class_label={match.rule.label}",
            *match.evidence,
            f"source={read.policy.source}",
            # The class list does not cover every surface it asserts an invariant over, and
            # since #326 the refusal says so rather than leaving it to a docstring: the
            # reader being routed by the table is the reader forming a belief about what it
            # checks. `just land`'s enforcing refusal carries the same line.
            f"coverage={read.policy.coverage}",
        ),
        match.rule.remedy,
    )


def routing_clearance(
    args: argparse.Namespace, root: Path, found: Readiness, now: datetime
) -> tuple[str, ...]:
    """Say what a *clear* dispatch routing read did and did not establish (round 2 claim 5).

    `just land`'s counterpart, and the argument is round 1 claim 3's own, applied on the side
    it was not: the reader told nothing is wrong is the reader forming a belief about what
    was checked. It matters more here than there, because since #326 dispatch is the **only**
    rung that checks the seat-bound classes — 2 and 3, a landing has no seat — so a
    dispatcher cleared here is cleared by the one check that could have caught an ADR or an
    orchestration issue taken by an unadmitted seat, and hears nothing about classes 4, 5 and
    — since ADR-0073 (#406) — 6 refusing no route, class 6 naming a minority of the gates, or
    the landing rung not re-checking any of it. Class 6 is the one whose silence here means
    most: it refuses no dispatch at all now, and what it asks for lands on `just land`'s
    never-alone rung as a cross-lane review the dispatcher has not been told about.

    **The unreadable-policy fallback is stated rather than silent (#326 round 2, claim 7).** The
    Claude lane dispatches on an unreadable policy so the policy can be repaired on Claude,
    and before #326 that cost nothing, because Claude was exempt from every row anyway.
    Classes 2 and 3 are now lane-blind, so the fallback silently reverses both rows made to
    bind Claude (#327 review round 3, claim 3: two rows escape through it, not one — the
    label names the issue, as every citation here now does, because #326's own review
    round 3 used the same ordinals for different findings). The
    bootstrap still holds; what changes is that the hole says so.

    **An excepted route is told so, and is not told it is clear (#326 round 3, claim 2).** This
    function computes no match of its own — it re-reads the walk `routing_refusal` already
    made, through `advisory_read`, which returns the lifted match as a third value. Without
    it, a route matching class 3 and lifted by a standing human allowance read
    `routing=clear`, which says no class applies; the truth is that one applies and an
    allowance lifted it. That is round 1 claim 3's "exempted is not cleared" on this rung,
    and the landing rung already says it in its own words.
    """
    read = _read_routing_policy(root)
    if read.policy is None:
        if args.lane != CLAUDE_LANE:  # pragma: no cover - `routing_refusal` refused it
            return ()
        return (
            "routing=not_checked reason=policy_unreadable",
            f"policy={read.error}",
            (
                "fallback=claude-native dispatches anyway so the policy can be repaired on"
                " Claude — a seat-bound class binding this lane escapes through it unchecked"
            ),
        )
    where = f"check=advisory issue declaration seat={args.seat} lane={args.lane}"
    lifted = routing_policy.advisory_read(
        read.policy,
        found.body,
        routing_policy.Route(args.lane, args.profile, args.seat, now),
    ).exemption
    if lifted is not None:
        return (
            f"routing=excepted {where}",
            f"routing_class={lifted.rule.id}:{lifted.rule.name}",
            f"class_label={lifted.rule.label}",
            *lifted.evidence,
            (
                "excepted=this class applies to this route and an exception in the policy"
                " lifted it, so the class was not cleared and nothing about it was checked"
            ),
            f"coverage={read.policy.coverage}",
        )
    return (f"routing=clear {where}", f"coverage={read.policy.coverage}")


def ladder_refusal(
    args: argparse.Namespace, now: datetime, found: Readiness, root: Path
) -> Refusal | None:
    """Climb the rungs a dispatch must clear before anything is planned, and stop at the first.

    The order is one idea: **the refusal that lasts longest is the one worth hearing.**
    The registry's own rungs come first because a typo is not a state of the world at all.
    Readiness comes next, on both halves of that reasoning: an unready issue is a property
    of the request rather than of the world, and it is the only rung here that no clock and
    no provider will ever clear — it reopens when a person edits the issue, and not before.
    Then the queue policy, whose refusals are the only others no change of lane, profile or
    seat can clear — a dispatcher told to pick another lane and then met by a freeze has been
    sent on an errand that could not have worked. It sits *below* readiness on readiness's
    own criterion rather than above it: an unready issue can be made ready this minute, and a
    freeze is the one refusal here whose remedy nobody but the human can start. Then the
    breaker, which reopens on a published window boundary or on evidence; then the off-peak
    rule,
    which reopens on a clock within four hours with nothing for anyone to do meanwhile.
    Told about the clock first, a dispatcher would come back when the band lifted to meet
    a trip it was never told about.

    Readiness is also the one rung that costs a network call, and it is deliberately not
    demoted for it: the whole point of hearing it first is that its remedy can start now,
    while every rung below it either fixes itself or waits on the same human anyway.
    """
    refusal = resolve_selection(args.lane, args.profile, args.seat)
    if refusal is not None:
        if refusal.kind == "orchestrator_claude_only":
            policy_refusal = routing_refusal(args, found, root, now)
            if policy_refusal is not None:
                return policy_refusal
        return refusal
    return _state_refusal(args, now, found, root)


def _state_refusal(
    args: argparse.Namespace, now: datetime, found: Readiness, root: Path
) -> Refusal | None:
    """Climb the request and mutable-state rungs after registry validation."""
    refusal = readiness_refusal(args.issue, found)
    if refusal is not None:
        return refusal
    refusal = queue_refusal(args, root)
    if refusal is not None:
        return refusal
    refusal = routing_refusal(args, found, root, now)
    if refusal is not None:
        return refusal
    refusal = breaker_refusal(args.lane, Path(args.breaker_dir).expanduser(), now.timestamp())
    if refusal is not None:
        return refusal
    return off_peak_refusal(LANES[PROFILES[args.profile].lane], now)


def _write_disposable_owner(record: Path, owner: dispatch_stop.Record) -> None:
    """Publish the minimum stop-readable owner proof before creating the tree."""
    record.mkdir(parents=True, exist_ok=False)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": owner.dispatch_id,
                "worktree": str(owner.worktree),
                "disposable_worktree": True,
                "worktree_ref": owner.worktree_ref,
                "worktree_owner": owner.worktree_owner,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _remove_provisional_owner(record: Path) -> None:
    """Remove only the provisional record this planner created after clean teardown."""
    try:
        (record / "dispatch.json").unlink(missing_ok=True)
        record.rmdir()
    except OSError:
        # A surviving record is safer than guessing that a concurrent writer is ours.
        return


def _materialize_disposable_plan(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0915 — setup owns the complete plan, its source fallback and one refusal per proof rung
    plan: Plan,
    brief: str,
    root: Path,
    requested_base_sha: str,
    review_root: Path,
    *,
    custom_brief: bool,
    thread_report: gate_report.GateReport | None,
    writable_roots: tuple[Path, ...] | None,
) -> tuple[Plan | None, str, Refusal | None]:
    """Restore the selected review/recon base into an id-owned tree, failing closed."""
    review_ref = review_exchange.review_ref(plan.identity.issue)
    ref = review_ref
    path = root / worktree_tool.WORKTREES / f"dispatch-{plan.identity.dispatch_id}"
    restore_from_commit = False
    exchanged_sha: str | None = None
    if plan.record.exists():
        return (
            None,
            "",
            Refusal(
                "dispatch_record_collision",
                (f"dispatch={plan.identity.dispatch_id}", f"record={plan.record}"),
                "The dispatch id already has a record. Nothing was created; choose no "
                "replacement and inspect the existing dispatch.",
                failure_class="infra_unavailable",
            ),
        )

    try:
        registrations = worktree_tool.parse_registrations(
            worktree_tool.git("worktree", "list", "--porcelain", cwd=root)
        )
        registered = tuple(
            entry for entry in registrations if entry.path.resolve() == path.resolve()
        )
    except (OSError, worktree_tool.GitError) as failure:
        return (
            None,
            "",
            Refusal(
                "disposable_worktree_unproven",
                (f"worktree={path}", f"reason=registration_read_failed:{failure}"),
                "The dispatch cannot prove that its derived tree is free. Nothing was created; "
                "inspect the worktree registrations before retrying.",
                failure_class="infra_unavailable",
            ),
        )
    if path.exists() or registered:
        return (
            None,
            "",
            Refusal(
                "disposable_worktree_unproven",
                (
                    f"worktree={path}",
                    "reason=derived_path_already_exists",
                    f"registrations={len(registered)}",
                ),
                "The dispatch cannot prove that its derived tree is free. Nothing was removed; "
                "inspect the existing holder rather than guessing (#105).",
                failure_class="infra_unavailable",
            ),
        )
    if plan.identity.seat == "review" and requested_base_sha:
        try:
            exchanged_sha = worktree_tool.remote_ref_sha(root, review_ref)
        except worktree_tool.GitError as failure:
            return (
                None,
                "",
                Refusal(
                    "disposable_worktree_create_failed",
                    (
                        f"worktree={path}",
                        f"ref={review_ref}",
                        f"command=git {' '.join(failure.args_run)}",
                        f"stderr={failure.stderr}",
                    ),
                    "The review ref could not be read. Nothing was dispatched; inspect the git "
                    "error and retry only after the ref is readable.",
                    failure_class="infra_unavailable",
                ),
            )
        if exchanged_sha is not None and requested_base_sha != exchanged_sha:
            carry_refusal = review_exchange.review_ref_carry_refusal(
                root,
                plan.identity.issue,
                exchanged_sha,
                requested_base_sha,
                review_root,
            )
            if carry_refusal is not None:
                return (
                    None,
                    "",
                    Refusal(
                        carry_refusal.kind,
                        (f"worktree={path}", f"ref={review_ref}", *carry_refusal.found),
                        carry_refusal.action,
                        failure_class="infra_unavailable",
                    ),
                )
            ref = requested_base_sha
            restore_from_commit = True
    if plan.identity.seat == "recon":
        try:
            review_sha = worktree_tool.remote_ref_sha(root, ref)
        except worktree_tool.GitError as failure:
            return (
                None,
                "",
                Refusal(
                    "disposable_worktree_create_failed",
                    (
                        f"worktree={path}",
                        f"ref={ref}",
                        f"command=git {' '.join(failure.args_run)}",
                        f"stderr={failure.stderr}",
                    ),
                    "The recon base could not be read. Nothing was dispatched; inspect the git "
                    "error and retry only after the base is readable.",
                    failure_class="infra_unavailable",
                ),
            )
        if review_sha is None:
            if requested_base_sha:
                ref = requested_base_sha
                restore_from_commit = True
            else:
                ref = RECON_DEFAULT_REF
    owner = dispatch_stop.Record(
        dispatch_id=plan.identity.dispatch_id,
        worktree=path,
        directory=plan.record,
        disposable_worktree=True,
        worktree_ref=ref,
        worktree_owner=plan.identity.dispatch_id,
    )
    owner_written = False
    created = False

    def failed(kind: str, found: tuple[str, ...], action: str) -> tuple[None, str, Refusal]:
        nonlocal created, owner_written
        if owner_written:
            if created:
                cleanup_refusal, cleanup_lines = dispatch_stop.cleanup_disposable_worktree(owner)
                if cleanup_refusal is None:
                    _remove_provisional_owner(plan.record)
                else:
                    found = (*found, *cleanup_refusal.lines())
                if cleanup_lines:
                    found = (*found, *cleanup_lines)
            else:
                _remove_provisional_owner(plan.record)
        return None, "", Refusal(kind, found, action, failure_class="infra_unavailable")

    try:
        _write_disposable_owner(plan.record, owner)
        owner_written = True
        restored = (
            worktree_tool.restore_commit(root, path.name, ref)
            if restore_from_commit
            else worktree_tool.restore(root, path.name, ref)
        )
    except worktree_tool.GitError as failure:
        return failed(
            "disposable_worktree_create_failed",
            (
                f"worktree={path}",
                f"ref={ref}",
                f"command=git {' '.join(failure.args_run)}",
                f"stderr={failure.stderr}",
            ),
            "The review tree could not be created. Nothing was dispatched; inspect the git "
            "error and retry only after the tree is proven gone.",
        )
    except (OSError, ValueError) as failure:
        return failed(
            "disposable_worktree_create_failed",
            (f"worktree={path}", f"ref={ref}", f"reason={failure}"),
            "The review tree could not be created. Nothing was dispatched; inspect the "
            "record and tree before retrying.",
        )
    if restored.code != 0:
        return failed(
            "disposable_worktree_create_failed",
            (f"worktree={path}", f"ref={ref}", *restored.lines),
            "The disposable tree could not be restored from its selected base. Read the refusal "
            "above; nothing was dispatched.",
        )
    created = True

    if restore_from_commit and exchanged_sha is not None:
        try:
            current_exchanged_sha = worktree_tool.remote_ref_sha(root, review_ref)
        except worktree_tool.GitError as failure:
            return failed(
                "review_ref_sha_mismatch",
                (
                    f"worktree={path}",
                    f"ref={review_ref}",
                    f"reviewed_sha={exchanged_sha}",
                    f"requested_sha={requested_base_sha}",
                    f"command=git {' '.join(failure.args_run)}",
                    f"stderr={failure.stderr}",
                ),
                "The review ref changed while its clean-rebase carry was being checked. "
                "Do not dispatch a reviewer against a different commit; re-run the exchange.",
            )
        if current_exchanged_sha != exchanged_sha:
            return failed(
                "review_ref_sha_mismatch",
                (
                    f"worktree={path}",
                    f"ref={review_ref}",
                    f"reviewed_sha={exchanged_sha}",
                    f"requested_sha={requested_base_sha}",
                    f"resolved={current_exchanged_sha or 'no'}",
                ),
                "The review ref changed while its clean-rebase carry was being checked. "
                "Do not dispatch a reviewer against a different commit; re-run the exchange.",
            )

    try:
        ref_sha = worktree_tool.git("rev-parse", "HEAD", cwd=path).strip()
    except worktree_tool.GitError as failure:
        return failed(
            "disposable_worktree_create_failed",
            (
                f"worktree={path}",
                f"ref={ref}",
                f"command=git {' '.join(failure.args_run)}",
                f"stderr={failure.stderr}",
            ),
            "The restored tree's reviewed SHA could not be read. Nothing was dispatched.",
        )
    if not ref_sha:
        return failed(
            "disposable_worktree_create_failed",
            (f"worktree={path}", f"ref={ref}", "reviewed_sha=<empty>"),
            "The restored tree did not name a reviewed SHA. Nothing was dispatched.",
        )
    if requested_base_sha and requested_base_sha != ref_sha:
        return failed(
            "review_ref_sha_mismatch",
            (
                f"worktree={path}",
                f"ref={ref}",
                f"reviewed_sha={ref_sha}",
                f"requested_sha={requested_base_sha}",
            ),
            "The review ref does not hold the requested reviewed SHA. Do not dispatch a "
            "reviewer against a different commit.",
        )

    identity = plan.identity._replace(base_sha=ref_sha)
    materialized = plan._replace(
        identity=identity,
        worktree=path,
        argv=build_argv(
            LANES[identity.lane],
            PROFILES[identity.profile],
            plan.permission_mode,
            path,
            writable_roots,
            disposable_worktree=True,
            review_plan_dispatch_id=(identity.dispatch_id if SEATS[identity.seat].reviews else ""),
        ),
        disposable_worktree=True,
        worktree_ref=ref,
    )
    rendered_brief = brief if custom_brief else default_brief(identity, path, thread_report)
    return materialized, rendered_brief, None


def _cleanup_plan_worktree(plan: Plan) -> tuple[Refusal | None, tuple[str, ...]]:
    """Run the same ownership-checked teardown before a child record can launch."""
    if not plan.disposable_worktree:
        return None, ()
    owner = dispatch_stop.Record(
        dispatch_id=plan.identity.dispatch_id,
        worktree=plan.worktree,
        directory=plan.record,
        disposable_worktree=True,
        worktree_ref=plan.worktree_ref,
        worktree_owner=plan.identity.dispatch_id,
    )
    return dispatch_stop.cleanup_disposable_worktree(owner)


def resolve_worktree_request(root: Path, requested: str) -> tuple[Path, Path | None]:
    """Read `--worktree` as a worktree name or as a path, whichever its text is (#431).

    A bare name — one segment by `worktree_tool.classify_name`'s rule — is a worktree
    name, read the way `just worktree restore` reads the same string: under
    `.claude/worktrees/`. The default branch below always built its path there, so before
    #431 only the flag's branch disagreed with the sibling command. Anything else —
    absolute, `~`-led, dot-led, or carrying a separator — is a path and resolves exactly
    as it did before. The second return is a bare name's other reading, its cwd-relative
    path, so `worktree_missing` can be refused only once both readings are genuinely
    absent and can name where it looked.
    """
    if worktree_tool.classify_name(requested) is None:
        return root / worktree_tool.WORKTREES / requested, Path.cwd() / requested
    return Path(requested).expanduser(), None


def assigned_worktree(
    args: argparse.Namespace, root: Path, *, disposable: bool
) -> tuple[Path, Refusal | None]:
    """Resolve the tree this dispatch is assigned, refusing where it is absent (#431).

    A bare `--worktree` name is read the way `just worktree restore` reads the same
    string — under `.claude/worktrees/` (`worktree_tool.classify_name` decides which
    strings are names); anything else is a path, exactly as before. A `worktree_missing`
    refusal fires only once the tree is absent under every reading the argument supports,
    and its action names every path that was looked at, so the reader checks the argument
    rather than doubting a tree `just worktree list` shows as live.
    """
    worktree, path_reading = (
        resolve_worktree_request(root, args.worktree)
        if args.worktree
        else (root / ".claude" / "worktrees" / f"issue-{args.issue}", None)
    )
    if disposable or worktree.is_dir():
        return worktree, None
    if path_reading is not None and path_reading.is_dir():
        # The bare name's other reading — the cwd-relative path the old code resolved —
        # is the one reading that worked from inside `.claude/worktrees/`, so a caller
        # standing there keeps the tree they asked for (#431).
        return path_reading, None
    # The advice names a tree that would satisfy the request: a bare name can be created
    # under that name, but a path argument was a location, not a name, so the issue's
    # registered surface is the one worth creating (#431).
    create = args.worktree if path_reading is not None else f"issue-{args.issue}"
    looked = f"Looked for the tree at {worktree}"
    if path_reading is not None:
        looked += f", then at the path {path_reading}, and it is absent at both"
    else:
        looked += ", and it is absent there"
    return worktree, Refusal(
        "worktree_missing",
        (f"worktree={worktree}",)
        if path_reading is None
        else (f"worktree={worktree}", f"path_reading={path_reading}"),
        (
            f"{looked}. Create it first: `just worktree add {create}`. A dispatch "
            "does not create the tree it assigns, because creating one it cannot prove "
            "is exclusive is exactly #105's failure."
        ),
        failure_class="infra_unavailable",
    )


def plan_dispatch(  # noqa: C901, PLR0911, PLR0912 — planning owns the ordered refusal ladder
    args: argparse.Namespace,
    root: Path,
    now: datetime,
    *,
    materialize_worktree: bool | None = None,
) -> tuple[Plan | None, str, Refusal | None]:
    """Validate the request and mint a plan, materializing only an owned review tree."""
    if materialize_worktree is None:
        materialize_worktree = bool(getattr(args, "materialize_worktree", False))
    found = read_issue(args.issue, args.issue_body)
    route, refusal = resolve_seat(args, now)
    if refusal is not None or route is None:
        return None, "", refusal
    args = routed(args, route)
    refusal = ladder_refusal(args, now, found, root)
    if refusal is not None:
        return None, "", refusal

    profile = PROFILES[args.profile]
    lane = LANES[profile.lane]
    breaker_dir = Path(args.breaker_dir).expanduser()
    seat = SEATS[args.seat]
    preview = bool(getattr(args, "dry_run", False))
    disposable = seat.disposable_worktree and (materialize_worktree or preview)

    worktree, missing = assigned_worktree(args, root, disposable=disposable)
    if missing is not None:
        return None, "", missing

    # #105's sixth instance: a tree is not free merely because it is clean. The pre-flight
    # answers "is this tree clean now" and the question that produced two agents in one
    # worktree was "is anyone still working in it", which nothing asked. The dispatch
    # record directory answers it — a record with no `result.json` is live, or dead
    # without having written one — and this rung sits directly below the existence check
    # because both are properties of the assigned tree rather than of the request (#308).
    if not disposable:
        refusal = _from_stop(
            dispatch_stop.occupancy_refusal(worktree, Path(args.dispatch_dir).expanduser())
        )
        if refusal is not None:
            return None, "", refusal
    else:
        # The real tree is created from the review ref after the id is minted. The main
        # checkout is only a temporary cwd for planning; it is never handed to the child.
        worktree = root

    # The credential is checked here as well as in the child, and the order matters: a
    # dispatch that cannot start should refuse at the recipe rather than hand back an id
    # for a run that will die three seconds later somewhere the caller is not looking.
    # The child re-checks anyway, because the file can go between plan and launch.
    credentials = Path(args.credentials).expanduser()
    _, refusal = lane_credential(lane, credentials)
    if refusal is not None:
        return None, "", refusal

    base_sha = args.base_sha or git("rev-parse", "HEAD", cwd=worktree)
    dispatch_id = mint_dispatch_id(now, secrets_module.token_hex(3))
    if not ID_ALPHABET.fullmatch(dispatch_id):  # pragma: no cover - the minter's own guard
        message = f"minted an id outside the alphabet: {dispatch_id}"
        raise ValueError(message)

    if disposable:
        # A dry run does not create this path, but it must describe the same dispatch-owned
        # cwd that the real invocation would create rather than the caller's persistent tree.
        worktree = root / worktree_tool.WORKTREES / f"dispatch-{dispatch_id}"

    identity = Identity(
        dispatch_id=dispatch_id,
        lane=lane.name,
        profile=profile.name,
        seat=args.seat,
        issue=args.issue,
        base_sha=base_sha,
    )
    thread_report = getattr(args, "gate_report", None)
    if thread_report is None and seat.reviews:
        read_gate_report = getattr(args, "gate_report_fetch", None)
        thread_report = (
            read_gate_report(args.issue)
            if read_gate_report is not None
            else gate_report.GateReport(
                gate_report.UNAVAILABLE,
                detail="the planner was called without a thread-read result",
            )
        )
    brief = (
        Path(args.brief_file).expanduser().read_text(encoding="utf-8")
        if args.brief_file
        else default_brief(identity, worktree, thread_report)
    )
    sandbox_disposable = seat.disposable_worktree
    writable_roots = None
    needs_codex_roots = lane.runner_family is codex_guidance.GuidanceHarness.CODEX and (
        sandbox_disposable
        or harness_commits(lane, args.permission_mode, disposable_worktree=disposable)
    )
    if needs_codex_roots:
        # High 1's rung: the roots are minted into the argv below, so the environment is
        # checked here or not at all — the record freezes them for the child.
        writable_roots = _codex_writable_roots()
        refusal = writable_root_refusal(root, writable_roots)
        if refusal is not None:
            return None, "", refusal
    if harness_commits(lane, args.permission_mode, disposable_worktree=disposable):
        brief += CODEX_COMMIT_PROTOCOL
    plan = Plan(
        identity=identity,
        worktree=worktree,
        record=Path(args.dispatch_dir).expanduser() / dispatch_id,
        argv=build_argv(
            lane,
            profile,
            args.permission_mode,
            worktree,
            writable_roots,
            disposable_worktree=sandbox_disposable,
            review_plan_dispatch_id=(dispatch_id if seat.reviews else ""),
        ),
        credentials=credentials,
        permission_mode=args.permission_mode,
        route=route,
        planned_at=now,
        breaker_dir=breaker_dir,
        advisories=readiness_advisories(args.issue, found),
        routing=routing_clearance(args, root, found, now),
        strata=capture_strata(found.body, args.issue, root, body_from_file=bool(args.issue_body)),
        disposable_worktree=disposable,
    )
    if disposable and materialize_worktree:
        return _materialize_disposable_plan(
            plan,
            brief,
            root,
            args.base_sha,
            Path(args.review_root).expanduser(),
            custom_brief=bool(args.brief_file),
            thread_report=thread_report,
            writable_roots=writable_roots,
        )
    return plan, brief, None


def write_record(plan: Plan, brief: str) -> None:
    """Lay down the dispatch record: the plan, and the brief exactly as it will be sent.

    Writing the record is also the stage transition it records (#490): the dispatch
    exists from here even where the child then refuses or dies, so an implementer
    dispatch arrives at `implementation` and a review dispatch at `review` at this
    moment, fail-open over the arrival the way every family is over its emission.
    Seats that are not pipeline stages — planner, recon, retro, orchestrator — record
    no arrival, because their dispatches are not passes through the work-item
    pipeline.
    """
    plan.record.mkdir(parents=True, exist_ok=True)
    (plan.record / "dispatch.json").write_text(
        json.dumps(plan.document(), indent=2) + "\n", encoding="utf-8"
    )
    (plan.record / "brief.md").write_text(brief, encoding="utf-8")
    stage = attribute_registry.STAGE_OF_SEAT.get(plan.identity.seat)
    if stage is not None:
        attribute_registry.record_stage_arrival(
            stage,
            plan.identity.issue,
            review_loop.review_root(),
            plan.planned_at.timestamp(),
            dispatch_id=plan.identity.dispatch_id,
        )


def load_record(record: Path) -> Plan:
    """Read back a plan the seam wrote, which is how the detached child learns its job."""
    document = json.loads((record / "dispatch.json").read_text(encoding="utf-8"))
    identity = Identity(
        dispatch_id=str(document["dispatch_id"]),
        lane=str(document["lane"]),
        profile=str(document["profile"]),
        seat=str(document["seat"]),
        issue=int(document["issue"]),
        base_sha=str(document["base_sha"]),
    )
    return Plan(
        identity=identity,
        worktree=Path(str(document["worktree"])),
        record=record,
        argv=tuple(str(part) for part in document["argv"]),
        credentials=Path(str(document["credentials_file"])),
        permission_mode=str(document["permission_mode"]),
        route=read_route(document),
        # Strict, with no fallback (#341). `planned_at` has been written on every record
        # since `b4be003` created `dispatch.json` at all, so there is no older shape to
        # fall back for, and a record without the key is one this code did not write — a
        # `KeyError` `run_dispatch` refuses on, because a plausible instant a consumer
        # cannot tell from a real one is the expensive kind of wrong.
        planned_at=datetime.fromisoformat(str(document["planned_at"])),
        breaker_dir=Path(str(document.get("breaker_dir", breaker.DEFAULT_BREAKER_DIR))),
        advisories=tuple(str(line) for line in document.get("readiness_advisories", ())),
        routing=tuple(str(line) for line in document.get("routing_clearance", ())),
        strata=read_strata(document),
        disposable_worktree=document.get("disposable_worktree") is True,
        worktree_ref=str(document.get("worktree_ref", "")),
    )


def write_result(record: Path, **fields: object) -> None:
    """Atomically publish the run's own outcome beside its plan.

    A returncode is not a failure class. What a dispatched run's exit code means about
    the code under test is the gates' business, and inventing a class here would be a
    second, untested opinion about it.

    The complete document is staged in the record directory, flushed, and renamed onto
    `result.json`. On a filesystem that honours atomic same-directory replacement, a
    reader therefore sees the complete result or no result; a write or rename failure
    never publishes the staged bytes as a finished dispatch. No retry follows a failure.
    """
    target = record / "result.json"
    document = json.dumps(fields, indent=2) + "\n"
    handle, staged_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".staged", dir=record)
    staged = Path(staged_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as writing:
            writing.write(document)
            writing.flush()
            os.fsync(writing.fileno())
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)


def unreadable_record_refusal(record: Path, unreadable: Exception) -> Refusal:
    """Refuse a record that cannot be read back.

    The name is `dispatch_stop.find_record`'s, deliberately, and not a second one for the
    same condition: `tools/dispatch_stop.py` already refuses a dispatch record that will
    not read back as `dispatch_unreadable`, and one vocabulary across the two tools is
    worth more than two precise ones. Not, however, for the reason it is tempting to give:
    the stop side's refusal is *printed* and never written — `find_record` returns it to
    `tools/dispatch_stop.py:548`, which puts its lines on the terminal, and by construction
    there is no record to write it beside — so this site is the only one that puts the
    string under `~/.arma-cti/dispatches/`. Sharing the name buys a reader one thing to
    look up, not one place to grep.

    The evidence fields are `dispatch_stop`'s too, and for the grep to work they have to
    be: `dispatch=` the id and `record=` the `dispatch.json` itself, matching
    `tools/dispatch_stop.py:258` rather than pointing one key at the file and the other at
    its parent. The two do not cover the same conditions even so — an absent
    `dispatch.json` is `unknown_dispatch` there and `dispatch_unreadable` here, because
    there it means "no such dispatch" and here the child was handed one.
    """
    return Refusal(
        "dispatch_unreadable",
        (
            f"dispatch={record.name}",
            f"record={record / 'dispatch.json'}",
            f"found={type(unreadable).__name__}: {unreadable}",
        ),
        (
            "The record this child was pointed at could not be read back as one this "
            "version wrote — it may be foreign, or merely unreachable, and `found=` above "
            "says which. Nothing ran. Re-plan the dispatch; a permission bit or a full "
            "disk is the box's to fix, not the record's."
        ),
        failure_class="infra_unavailable",
    )


def _clock_point() -> tuple[int, datetime]:
    """Capture one nanosecond stamp and its UTC rendering."""
    stamp = time.time_ns()
    return stamp, datetime.fromtimestamp(stamp / 1_000_000_000, tz=UTC)


def _review_window(
    started: tuple[int, datetime] | None,
    ended: tuple[int, datetime] | None,
) -> ReviewWindow | None:
    """Return a complete child window, or no attribution authority."""
    if started is None or ended is None:
        return None
    return ReviewWindow(
        started_ns=started[0],
        ended_ns=ended[0],
        started_at=started[1],
        ended_at=ended[1],
    )


@dataclass
class _DispatchProgress:
    dispatch_id: str
    failure_phase: str = "record_read"
    started: datetime | None = None
    review_window_started: tuple[int, datetime] | None = None
    review_window_ended: tuple[int, datetime] | None = None
    child_launch_attempted: bool = False
    returncode: int | None = None
    review_delivery: tuple[str, ...] = ()


def _not_launched_result(dispatch_id: str, refusal: Refusal) -> dict[str, object]:
    return {
        "dispatch_id": dispatch_id,
        "status": "child_not_launched",
        "refusal": refusal.kind,
        "failure_class": refusal.failure_class,
        "ended_at": datetime.now(tz=UTC).isoformat(),
    }


def _failed_result(progress: _DispatchProgress, failure: BaseException) -> dict[str, object]:
    if progress.returncode is not None:
        status = "harness_failed_after_child"
    elif progress.child_launch_attempted:
        # `subprocess.run` covers both process creation and communication. Until it
        # returns, an exception cannot reliably say whether the child did no work or ran
        # before the harness lost track of it. Preserve that uncertainty: asserting the
        # child never launched would make a duplicate dispatch look safe.
        status = "child_state_unknown"
    else:
        status = "child_not_launched"
    result: dict[str, object] = {
        "dispatch_id": progress.dispatch_id,
        "status": status,
        "failure_phase": progress.failure_phase,
        "failure": {"type": type(failure).__name__, "message": str(failure)},
        "ended_at": datetime.now(tz=UTC).isoformat(),
    }
    if status == "child_state_unknown":
        result["action"] = CHILD_STATE_UNKNOWN_ACTION
    if progress.returncode is not None:
        result["returncode"] = progress.returncode
    if progress.started is not None and progress.returncode is not None:
        result["started_at"] = progress.started.isoformat()
    if progress.review_delivery:
        result["review_delivery"] = list(progress.review_delivery)
    return result


def _write_result_once(record: Path, result: Mapping[str, object]) -> None:
    """Attempt the one closeout write, reporting failure without adding recovery machinery."""
    try:
        write_result(record, **result)
    except BaseException as failure:  # noqa: BLE001 — BaseException is the boundary's subject
        emit(
            (
                (
                    "result_write=failed"
                    f" cause={type(failure).__name__}: {failure}"
                    f" record={record / 'result.json'}"
                ),
            ),
            EXIT_REFUSED,
        )


def _run_dispatch_body(
    record: Path,
    parent: Mapping[str, str],
    progress: _DispatchProgress,
) -> tuple[int, tuple[str, ...], dict[str, object]]:
    """Run one child and return the result document the outer boundary must write."""
    try:
        plan = load_record(record)
        progress.dispatch_id = plan.identity.dispatch_id
        profile = PROFILES[plan.identity.profile]
        lane = LANES[plan.identity.lane]
        brief = (record / "brief.md").read_text(encoding="utf-8")
    except (KeyError, TypeError, ValueError, OSError) as unreadable:
        refusal = unreadable_record_refusal(record, unreadable)
        return (
            EXIT_REFUSED,
            refusal.lines(),
            _not_launched_result(progress.dispatch_id, refusal),
        )

    progress.failure_phase = "pre_launch"
    refusal = assert_worktree(plan.worktree, git("rev-parse", "--show-toplevel", cwd=plan.worktree))
    if refusal is None:
        token, refusal = lane_credential(lane, plan.credentials)
    if refusal is None and harness_commits(
        lane, plan.permission_mode, disposable_worktree=plan.disposable_worktree
    ):
        refusal = harness_start_refusal(plan.worktree)
    if refusal is not None:
        return (
            EXIT_REFUSED,
            refusal.lines(),
            _not_launched_result(plan.identity.dispatch_id, refusal),
        )

    child = assemble_environment(parent, profile, plan.identity, token, project_dir=plan.worktree)
    progress.started = datetime.now(tz=UTC)
    progress.failure_phase = "child_setup"

    def mark_child_launch_attempted() -> None:
        progress.child_launch_attempted = True
        progress.failure_phase = "child_launch_or_wait"
        progress.review_window_started = _clock_point()

    def mark_child_finished(code: int) -> None:
        progress.returncode = code
        progress.failure_phase = "gate_clock_collection"
        progress.review_window_ended = _clock_point()

    done, gate_clock_collection = _run_child_with_gate_clock(
        plan, child, brief, mark_child_launch_attempted, mark_child_finished
    )
    progress.returncode = done.returncode
    review_delivery: tuple[str, ...] = ()
    review_delivery_code = 0
    if SEATS[plan.identity.seat].reviews:
        if done.returncode == 0:
            progress.failure_phase = "review_delivery"
            review_delivery, review_delivery_code = deliver_review(
                plan.identity.issue,
                done.stdout or "",
                record,
                parent,
                child_environment=child,
                review_window=_review_window(
                    progress.review_window_started,
                    progress.review_window_ended,
                ),
            )
        else:
            review_delivery = (f"review_delivery=not_attempted child_exit={done.returncode}",)
        progress.review_delivery = review_delivery
    # Review transport depends only on the completed child's bounded report. Outcome
    # classification and breaker journaling are bookkeeping; neither may prevent the one post
    # attempt or erase its verdict if that later bookkeeping raises (#496, #495's boundary).
    progress.failure_phase = "child_result"
    outcome, reset_at = classify_finished_run(record, done.returncode)
    progress.failure_phase = "breaker_journal"
    breaker.record_outcome(
        breaker.Store(directory=plan.breaker_dir),
        plan.identity.lane,
        breaker.Outcome(
            outcome,
            reset_at=reset_at,
            detail=f"dispatch {plan.identity.dispatch_id} exited {done.returncode}",
        ),
        datetime.now(tz=UTC).timestamp(),
    )
    finish: tuple[str, ...] = ()
    finish_code = 0
    progress.failure_phase = "harness_finish"
    if harness_commits(lane, plan.permission_mode, disposable_worktree=plan.disposable_worktree):
        finish, finish_code = harness_finish(plan.worktree, plan.identity.issue, record)
    harness_code = review_delivery_code or finish_code
    result = {
        "dispatch_id": plan.identity.dispatch_id,
        "status": "harness_failed_after_child" if harness_code else "child_finished",
        "returncode": done.returncode,
        "outcome": outcome,
        "started_at": progress.started.isoformat(),
        "ended_at": datetime.now(tz=UTC).isoformat(),
        "gate_clock_collection": list(gate_clock_collection),
        "review_delivery": list(review_delivery),
        "harness_finish": list(finish),
    }
    lines = (
        f"dispatch={plan.identity.dispatch_id}",
        f"exit={done.returncode}",
        *gate_clock_collection,
        *review_delivery,
        *finish,
    )
    return harness_code or done.returncode, lines, result


def run_dispatch(record: Path, parent: Mapping[str, str]) -> tuple[int, tuple[str, ...]]:
    """Run a detached child and make one result write attempt however the body exits."""
    progress = _DispatchProgress(record.name)
    result: dict[str, object] = {}
    code = EXIT_REFUSED
    lines: tuple[str, ...] = ()
    cleanup_refusal: Refusal | None = None
    cleanup_lines: tuple[str, ...] = ()
    try:
        code, lines, result = _run_dispatch_body(record, parent, progress)
    except BaseException as failure:
        result = _failed_result(progress, failure)
        raise
    finally:
        recorded = dispatch_stop.read_record(record)
        if recorded is not None:
            cleanup_refusal, cleanup_lines = dispatch_stop.cleanup_disposable_worktree(recorded)
            if cleanup_refusal is not None:
                result["worktree_cleanup"] = list(cleanup_refusal.lines())
            elif cleanup_lines:
                result["worktree_cleanup"] = list(cleanup_lines)
        _write_result_once(record, result)
    if cleanup_refusal is not None:
        return EXIT_REFUSED, (*lines, *cleanup_refusal.lines())
    return code, (*lines, *cleanup_lines)


def classify_finished_run(record: Path, returncode: int) -> tuple[str, float | None]:
    """Read what the run's own log says happened, and feed the breaker that (#226).

    This is the degraded fallback the issue names: with no quota tap wired, a lane's
    exhaustion is learned from the 429 the dispatch itself provoked. Late, because it
    cost a dispatch to find out, but not blind.

    The log is read rather than the child's pipes captured, because the seam already
    redirects everything the run says into `dispatch.log` and putting a second copy in
    memory would change what a live `tail -f` on that file shows. An unreadable log is
    the same as an unfamiliar one: `unclassified`, which moves no streak.
    """
    log = record / "dispatch.log"
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return breaker.classify_run(returncode, text[-LOG_TAIL_BYTES:])


def seat_listing(seat: Seat) -> tuple[str, ...]:
    """Render one seat for the registry: what `--seat S` alone resolves to, and its rules.

    ADR-0071 ruling 2's other half. The escalation entry is printed beside the preference
    and marked, because it is registry data *this* resolution deliberately does not walk — a
    reader who saw only the preference would have no way to tell whether an absent
    escalation meant "none" or "not shown". The mark says which resolution: `resolve_seat`
    never walks the entry, and `tools/arbiter.py`'s walk starts at it — that module being the
    one place what the walk does is stated (#390). An earlier mark read "not resolved into"
    flat, which was false the moment that walk landed at `d351a3f`.

    Ruling 4's two columns (#322) print only where they apply: a `reviews=false` line on
    every other seat would be noise, and a reader asking "which seat is the one that cannot
    review its own profile" gets the answer by their absence everywhere else. Ruling 1's
    carve-out column (#327) follows the same rule for the same reason — one `claude_only`
    seat, named where it applies and absent everywhere else. The preference
    line stays the seat's *registered* order — what a review dispatch actually walks depends
    on its subject, which the registry does not know, so the rule is stated rather than a
    resolved order invented for a dispatch nobody has asked for.
    """
    lines = [
        f"seat={seat.name}",
        f"  preference={' '.join(seat.preference)}",
        (
            f"  escalation={' '.join(seat.escalation)}"
            " (not a dispatch route; walked first by the arbiter)"
            if seat.escalation
            else "  escalation=none (no arbiter; escalation refuses by name)"
        ),
    ]
    if seat.claude_only:
        lines.append(
            "  claude_only=true refusal=orchestrator_claude_only (ADR-0071 ruling 1's"
            " one survivor, ends when a tested alternative exists)"
        )
    if seat.reviews:
        lines.append(
            "  reviews=true resolves_past=--reviewing-and-every-potential-author"
            " prefers=a-different-lane refusal=review_same_profile"
        )
        lines.append(
            "  review_subject=checked-against-dispatch-records"
            " refusal=review_subject_contradicted unchecked=recorded-unchecked"
        )
    if seat.permission_mode:
        lines.append(f"  permission_mode={seat.permission_mode} forced=true (no caller override)")
    if seat.disposable_worktree:
        lines.append("  disposable_worktree=true creates-from=review-ref removes-on=dispatch-end")
    return tuple(lines)


def registry_lines() -> tuple[str, ...]:
    """Render every lane and profile: the answer to "what can I dispatch?"."""
    lines: list[str] = []
    for lane in sorted(LANES.values()):
        lines.append(f"lane={lane.name} runner={lane.runner}")
        if lane.base_url:
            lines.append(f"  base_url={lane.base_url}")
        if lane.credential:
            lines.append(f"  credential={lane.credential}")
        schedule = breaker.LANE_SCHEDULES.get(lane.name)
        if schedule is not None:
            lines.append(f"  plan_meter={schedule.meter} discount={schedule.name}")
            lines.append(f"  window={schedule.window}")
        if lane.off_peak_only:
            lines.append("  off_peak_only=true rule=human 2026-08-05 (#238), no override")
        lines.extend(
            f"  profile={profile.name} model={profile.model} effort={profile.effort}"
            for profile in sorted(PROFILES.values())
            if profile.lane == lane.name
        )
    carve_out = " ".join(sorted(seat.name for seat in SEATS.values() if seat.claude_only))
    lines.append(f"seats_claude_only={carve_out} (ADR-0071 ruling 1: the only provenance rule)")
    for seat in sorted(SEATS.values()):
        lines.extend(seat_listing(seat))
    # ADR-0071 ruling 2: a (profile, seat) pair held below a seat's contract is blocked,
    # and the block is stated wherever the registry is read — a blocked pair renders as an
    # available profile and an eligible seat, so a reader who paired them would otherwise
    # discover the exception only by attempting the dispatch. The list ships empty since
    # #405, so this loop normally emits nothing; that is the registry saying there is no
    # such pair, which is exactly what it should say.
    lines.extend(
        f"seat_profile_block=adr0071 seat={seat} profile={profile_name} ceiling={ceiling}"
        for (seat, profile_name), ceiling in sorted(SEAT_PROFILE_BLOCKS.items())
    )
    return tuple(lines)


def dry_run_lines(plan: Plan, brief: str, parent: Mapping[str, str]) -> tuple[str, ...]:
    """Render what would be launched, credential redacted and the difference shown.

    The two `env_` sections are the readable form of the rule this module exists for: a
    lane's variables appear on the child and nowhere else.
    """
    profile = PROFILES[plan.identity.profile]
    # Planning already refused if this lane's credential is absent, so the token is
    # either present or the lane needs none; either way it is redacted before printing.
    token, _ = lane_credential(LANES[plan.identity.lane], plan.credentials)
    child = redacted(
        assemble_environment(parent, profile, plan.identity, token, project_dir=plan.worktree),
        token,
    )
    lines = [
        f"dispatch={plan.identity.dispatch_id}",
        f"lane={plan.identity.lane}",
        f"profile={plan.identity.profile}",
        f"seat={plan.identity.seat}",
        *plan.route.lines(),
        f"issue={plan.identity.issue}",
        f"worktree={plan.worktree}",
        f"base_sha={plan.identity.base_sha}",
        f"argv={' '.join(plan.argv)}",
        f"brief_bytes={len(brief.encode('utf-8'))}",
        *plan.advisories,
        *plan.routing,
    ]
    if LANES[plan.identity.lane].runner_family is codex_guidance.GuidanceHarness.CODEX:
        lines.extend(
            (
                f"instruction_preflight=pending scope={codex_guidance.CODEX_GUIDANCE_SCOPE}",
                f"instruction_project_doc_max_bytes={codex_guidance.CODEX_PROJECT_DOC_CONTAINMENT_BYTES}",
                f"instruction_retirement_bytes={codex_guidance.CODEX_PROJECT_CHAIN_RETIREMENT_BYTES}",
            )
        )
    lines += [f"env_child.{key}={child[key]}" for key in sorted(child) if key not in parent]
    lines += [
        f"env_child.{key}={child[key]}"
        for key in sorted(child)
        if key in parent and child[key] != parent[key]
    ]
    lines += [f"env_stripped.{key}" for key in LANE_OWNED if key in parent and key not in child]
    return tuple(lines)


def instruction_preflight(
    plan: Plan, parent: Mapping[str, str]
) -> tuple[Plan | None, Refusal | None]:
    """Verify Codex delivery synchronously, before the record and child fork exist."""
    lane = LANES[plan.identity.lane]
    if lane.runner_family is not codex_guidance.GuidanceHarness.CODEX:
        return plan, None
    profile = PROFILES[plan.identity.profile]
    token, refusal = lane_credential(lane, plan.credentials)
    if refusal is not None:
        return None, refusal
    child = assemble_environment(parent, profile, plan.identity, token)
    result = codex_guidance.verify_delivery(
        codex_guidance.LaunchContext(
            executable=plan.argv[0],
            cwd=plan.worktree,
            environment=child,
            loader_config=codex_guidance.loader_overrides(),
        )
    )
    if isinstance(result, codex_guidance.GuidanceFailure):
        kind = (
            "instruction_delivery_mismatch"
            if result.reason == "instruction_delivery_mismatch"
            else "instruction_preflight_unavailable"
        )
        return None, Refusal(
            kind,
            result.lines(),
            result.action,
            failure_class="infra_unavailable",
        )
    return plan._replace(guidance=result), None


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the dispatch request, as the seam passes it through."""
    parser = argparse.ArgumentParser(prog="dispatch", description=__doc__)
    parser.add_argument("--lane", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--seat", default="")
    parser.add_argument("--issue", type=int, default=0)
    parser.add_argument("--worktree", default="")
    parser.add_argument("--brief-file", default="")
    parser.add_argument("--base-sha", default="")
    # The writable default, and the reason it is still the default (#322). Most seats commit
    # and gate, so `acceptEdits` is right for them; what was wrong was that the review seat
    # inherited it. A seat that must not write now forces its own mode through `routed`,
    # which is where a seat's properties belong — flipping this default instead would have
    # left every other seat needing a flag to get back the mode its contract requires.
    parser.add_argument("--permission-mode", default="acceptEdits")
    # Which profile's work this dispatch reviews (#322, ADR-0071 ruling 4). Required by the
    # review seat and refused on every other. The flag names the subject and does not settle
    # it: `authoring_dispatches` derives it from the issue's own dispatch records and refuses
    # a name they contradict, because a check over two strings the caller typed enforces
    # nothing. Where they cannot answer, the route is recorded unverified.
    parser.add_argument(
        "--reviewing",
        default="",
        metavar="PROFILE",
        help="the profile whose work is under review; required by --seat review",
    )
    parser.add_argument("--dispatch-dir", default=str(DISPATCH_ROOT))
    # Where the interactive authorship declarations live (#402): the review seat's author
    # set reads them beside the dispatch records, the same merge the landing rung performs,
    # so the two consumers of that set cannot disagree. A flag rather than a constant so a
    # test can stage its own declarations, exactly as `--dispatch-dir` stages its own records.
    parser.add_argument("--review-root", default=str(review_loop.REVIEW_ROOT))
    parser.add_argument("--credentials", default=str(CREDENTIALS))
    # `CTI_BREAKER_DIR` exists so that a test can run the real seam — `tools/dispatch.sh`
    # forks a fresh process, which no in-process patch reaches — against its own breaker
    # rather than against whatever this box's lanes happen to be doing today.
    parser.add_argument(
        "--breaker-dir",
        default=os.environ.get("CTI_BREAKER_DIR", str(breaker.DEFAULT_BREAKER_DIR)),
    )
    # Where the readiness rung reads the issue from when GitHub is not the answer: a draft
    # body triage wants checked before filing, or a box `gh` cannot reach. `CTI_READINESS_
    # BODY` is its environment twin for the same reason `CTI_BREAKER_DIR` has one — the
    # seam forks a fresh process, which no in-process patch reaches.
    parser.add_argument(
        "--issue-body",
        default=os.environ.get("CTI_READINESS_BODY", ""),
        help="read the issue body from this file instead of asking gh",
    )
    # `CTI_QUEUE_DIR` and `CTI_QUEUE_ROOT` are the same seam again (#250): the recorded policy
    # and the tree scan the in-flight count is derived from. They move *where the state is
    # read*, which is what a forked seam test needs; neither is an override, and there is no
    # option anywhere here that dispatches through a recorded freeze.
    parser.add_argument(
        "--queue-dir",
        default=os.environ.get("CTI_QUEUE_DIR", str(queue_policy.DEFAULT_QUEUE_DIR)),
    )
    parser.add_argument("--queue-root", default=os.environ.get("CTI_QUEUE_ROOT", ""))
    # The supported way to stop a dispatch (#308, from #105). It takes a dispatch id and
    # nothing else, because the id is all a caller reliably has and everything else — the
    # worktree, and through it the processes — is derived from the record rather than
    # retyped. There is no `--stop-pid`, and there is no flag that skips the verifying
    # re-scan: a stop that does not verify is the guess that produced the incident.
    parser.add_argument(
        "--stop",
        default="",
        metavar="ID",
        help="stop this dispatch's processes and verify by re-scanning its worktree",
    )
    parser.add_argument("--list", action="store_true", help="print the registry and exit")
    parser.add_argument(
        "--readiness",
        action="store_true",
        help="audit an issue's readiness and exit, dispatching nothing",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan, launch nothing")
    parser.add_argument("--run", default="", help="internal: run the record at this path")
    return parser.parse_args(argv)


def missing_required(args: argparse.Namespace) -> tuple[str, ...]:
    """Name what the caller left out. A dispatch names a seat and an issue, and may name a route.

    `--lane` and `--profile` stopped being required together when ADR-0071 ruling 2 made the
    seat the ordinary way to dispatch (#321): named neither, the seat's preference list
    resolves one; named both, they are the caller's own choice and every `(profile, seat)`
    refusal still applies to it.

    One without the other is refused rather than completed, and deliberately: deriving the
    lane from the profile's registry entry would make `profile_lane_mismatch` unreachable,
    which is the rung that catches a caller who believed a profile lived somewhere else.
    """
    absent = []
    if not args.seat:
        absent.append("--seat")
    if args.issue <= 0:
        absent.append("--issue")
    if args.profile and not args.lane:
        absent.append("--lane")
    if args.lane and not args.profile:
        absent.append("--profile")
    return tuple(absent)


def readiness_audit(args: argparse.Namespace) -> int:
    """Judge one issue's readiness and print it, dispatching nothing (#241).

    This is the rung's other face, and the one the remedy loop needs: triage and the human
    are the only parties who can fix an unready issue, so they need to see the same verdict
    the dispatcher would, before a dispatch is armed rather than after one is refused. It
    takes no lane, no profile and no seat — there is nothing lane-shaped to pass — and it
    exits non-zero on exactly what would refuse a dispatch, so it is usable as a gate.
    """
    if args.issue <= 0 and not args.issue_body:
        return emit(
            Refusal(
                "incomplete_request",
                ("missing=--issue or --issue-body",),
                "A readiness audit needs an issue number or a body file. Nothing was read.",
            ).lines(),
            EXIT_REFUSED,
        )
    found = read_issue(args.issue, args.issue_body)
    refusal = readiness_refusal(args.issue, found)
    if refusal is not None:
        return emit((*refusal.lines(), *readiness_advisories(args.issue, found)), EXIT_REFUSED)
    assessment = found.assessment
    if assessment is None:  # pragma: no cover - readiness_refusal already refused this
        message = "an unreadable body reached the audit's clear path"
        raise ValueError(message)
    return emit(
        (
            f"readiness=ready issue={args.issue}",
            *assessment.lines(),
            *readiness_advisories(args.issue, found),
        ),
        0,
    )


def emit(lines: Iterable[str], code: int) -> int:
    """Print to the stream the exit code implies, and return it."""
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


# Where a dispatch's recognised waits are journalled (#484): a file beside the dispatch
# records, so the wait family adds no directory of its own.
WAIT_JOURNAL: Final = "waits.jsonl"


def note_plan_wait(
    refusal: Refusal | None, dispatch_dir: Path, at: float, *, issue: int | None = None
) -> None:
    """Journal one wait-shaped planning refusal with its cause (#484), fail-open.

    Only the planning choke calls this, so a refusal that a candidate entry collected
    internally is not a wait — the ladder skipped it and went on. The cause is never
    spelled here: `attribute_registry.block_reason_for` maps the refusal, and a kind it
    does not know is not a wait at all, except a `lane_breaker_open` on an unnamed
    failure class, which is one and reads `undetermined`. The issue rides along
    wherever the caller holds one (#492): the queue-depth sampler reads these lines
    back to say which work a peak band holds, and a wait that names no issue cannot
    say.
    """
    if refusal is None:
        return
    reason = attribute_registry.block_reason_for(refusal)
    if reason is None:
        return
    attribute_registry.emit_wait(
        attribute_registry.wait_event(reason, "dispatch", at, refusal=refusal.kind, issue=issue),
        journal=dispatch_dir / WAIT_JOURNAL,
    )


def answer_directly(args: argparse.Namespace) -> int | None:
    """Serve the modes that dispatch nothing, or return `None` to plan a dispatch.

    Four requests are not dispatches — the registry, a readiness audit, a stop, and the
    detached child asking to run a record the seam already wrote — and each is answered
    here so that `main` stays one path: plan, refuse, or launch.

    `--stop` is served before the four required options are checked, because a stop names
    no lane, profile, seat or issue: it names a dispatch that already exists and takes
    everything else from that dispatch's own record.
    """
    if args.list:
        return emit(registry_lines(), 0)
    if args.stop:
        code, lines = dispatch_stop.stop_by_id(Path(args.dispatch_dir).expanduser(), args.stop)
        return emit(lines, code)
    if args.readiness:
        return readiness_audit(args)
    if args.run:
        code, lines = run_dispatch(Path(args.run), os.environ)
        return emit(lines, code)
    return None


def prepare_gate_report_read(args: argparse.Namespace) -> None:
    """Give review planning a host-side thread reader for the default brief.

    A dry run intentionally performs this same bounded, read-only fetch: its output promises
    the brief that a real dispatch would send, including the report available to the child.
    """
    seat = SEATS.get(args.seat)
    if not args.brief_file and seat is not None and seat.reviews:
        args.gate_report_fetch = gate_report.fetch


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    """Plan a dispatch, or run one the seam already planned.

    `now` is the same seam `plan_dispatch` already takes, lifted to the command line so a
    test making a claim about the argv can be clock-free (#341). No flag reaches it: the
    off-peak rule has no override and this must not become one, which is why it is a
    keyword argument of the function rather than an option of the parser.
    """
    args = parse_args(argv)
    answered = answer_directly(args)
    if answered is not None:
        return answered

    absent = missing_required(args)
    if absent:
        return emit(
            Refusal(
                "incomplete_request",
                (f"missing={' '.join(absent)}",),
                (
                    "A dispatch names a seat and an issue, and either both of --lane and "
                    "--profile or neither: name neither and the seat's preference list "
                    "resolves one. Nothing was dispatched."
                ),
            ).lines(),
            EXIT_REFUSED,
        )

    when = datetime.now(tz=UTC) if now is None else now
    args.materialize_worktree = not args.dry_run
    # A review child cannot read the issue thread under its forced `plan` containment. The
    # The host reads the gate report and lets `plan_dispatch` carry the result into the default
    # brief. This is intentional under `--dry-run` too: the preview is the brief that would be
    # sent, so it must include the same report or the preview would describe a different request.
    # The callable is attached to the namespace rather than fetched here so refusal tests that
    # replace the planner do not make a network call; the real planner invokes it only after
    # the route has cleared its own refusal ladder.
    prepare_gate_report_read(args)
    plan, brief, refusal = plan_dispatch(args, main_checkout(Path.cwd()), when)
    if refusal is not None or plan is None:
        # A peak-band rehearsal is read-only: unlike a real attempt, it must not make the
        # lane-window queue look deeper merely because somebody inspected the refusal.
        if not (args.dry_run and refusal is not None and refusal.kind == "lane_peak_hours"):
            note_plan_wait(
                refusal,
                Path(args.dispatch_dir).expanduser(),
                when.timestamp(),
                # `--issue` defaults to 0, which names no issue at all.
                issue=args.issue or None,
            )
        return emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    if args.dry_run:
        return emit(dry_run_lines(plan, brief, os.environ), 0)

    planned_plan = plan
    plan, refusal = instruction_preflight(plan, os.environ)
    if refusal is not None or plan is None:
        cleanup_refusal, cleanup_lines = _cleanup_plan_worktree(planned_plan)
        if cleanup_refusal is None:
            _remove_provisional_owner(planned_plan.record)
        else:
            cleanup_lines = (*cleanup_refusal.lines(), *cleanup_lines)
        refusal_lines = refusal.lines() if refusal else ()
        return emit((*refusal_lines, *cleanup_lines), EXIT_REFUSED)

    try:
        write_record(plan, brief)
    except BaseException:
        cleanup_refusal, _ = _cleanup_plan_worktree(plan)
        if cleanup_refusal is not None:
            emit(cleanup_refusal.lines(), EXIT_REFUSED)
        else:
            _remove_provisional_owner(plan.record)
        raise
    return emit(
        (
            f"dispatch={plan.identity.dispatch_id}",
            f"record={plan.record}",
            f"worktree={plan.worktree}",
            *plan.route.lines(),
            *plan.advisories,
            *plan.routing,
        ),
        0,
    )


if __name__ == "__main__":
    sys.exit(main())
