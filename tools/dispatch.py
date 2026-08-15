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
  `opus-high` and `zai-glm52-max` are names in a registry; nothing outside the registry
  knows that one of them means `--effort high`. Effort vocabularies do not commensurate
  across providers, so the registry is the only place the mapping is allowed to exist.
- **Seat** carries ADR-0071 ruling 1's one survivor: the orchestrator carve-out. Ruling 1
  rescinds the graded authority ladder ADR-0061 built, so the seat table no longer
  encodes provenance and no seat is refused on it at this registry — every seat
  dispatches on every lane. The carve-out is the exception and it is provisional:
  orchestration runs on Claude with a Claude model until a tested alternative exists.
  One second provenance refusal survives outside the seat table: routing class 6's
  #326 bridge, which refuses on every lane but `claude-native` — a dispatch whose
  issue names the gates themselves, and, on the same row's landing half, a `just land`
  on any lane but this one whose diff touches them. #331 owns it — when that issue's
  never-alone exemption list lands, the invariant the bridge is kept in lieu of, and
  not evidence for, is enforced and the bridge retires, because deleting it first
  would leave the gates with neither rule. Routing class 2, orchestration, is not a
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

**The `zai` lane's economics are the inverse of Claude's, and that changes two settings
rather than the design.** Measured live against the endpoint (#225,
`docs/research/zai-lane-live-findings.md`): the plan meters prompt counts, prefix caching
is automatic and identical whether or not `cache_control` is sent, and
`thinking.budget_tokens` is ignored. So `ENABLE_PROMPT_CACHING_1H` is **not set on this
lane** — it only rewrites a `cache_control` TTL that measurably decides nothing here, and
even a real token saving would not be a plan saving under a prompt meter — and the five
Claude Code effort levels collapse to one profile per model rather than five.

**No admission standing is read, and nothing here refuses on one** (#328). ADR-0061
Decision 6 pre-registered a bar that admitted a profile to a seat against the Claude
history, and this file used to read its far end before it planned anything. ADR-0071 ruling
6 dropped that bar and withdrew Decision 6. The rung is gone rather than made permissive:
there is no standing to consult, no `admission_escalated` refusal to hit, and no directory
of records for a dispatcher to point at.

That is a deliberate departure from a pre-registration rather than a conclusion its data
reached — the bar never adjudicated once across its routes in 112 dispatches — and it is
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

**The review seat cannot review its own profile, and cannot edit** (#322, ADR-0071 ruling 4).
Both halves come from one invariant: no single model instance may both propose a change and
produce the verdict that clears it. So a review dispatch names the profile whose work it
reviews — `--reviewing` — and resolution *removes* that profile from the list before walking
it, putting a different lane first among what is left.

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
could resolve past anything, and resolving anyway would take the head the implementer took.
The second half is containment. `--permission-mode` defaults to `acceptEdits`, which is
writable on both runner families, so a review dispatched at the default could edit; the seat
now *forces* `plan` in `routed`, which `build_argv` renders as `--permission-mode plan` on
the `claude` family and `--sandbox read-only` on `codex`.

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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple
from urllib.parse import quote

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `stall_watch.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes these importable.
import breaker
import dispatch_stop
import gate
import hook_parity
import queue_policy
import readiness
import routing_policy

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

EXIT_REFUSED: Final = 1

DISPATCH_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"
CREDENTIALS: Final = Path.home() / ".arma-cti" / "credentials.env"

# How much of a finished run's log the breaker's classifier reads. A provider's own
# refusal or limit message is the last thing a run says, and a whole log of an agent's
# work would be a haystack full of the words this looks for.
LOG_TAIL_BYTES: Final = 8192

# Claude Code documents `OTEL_RESOURCE_ATTRIBUTES` as strict: US-ASCII, no spaces,
# percent-encode anything exotic. The collector's `group_by` file export also turns a
# dispatch id into a path segment. Both reasons point at the same narrow alphabet, so
# the id is minted inside it and checked rather than hoped for.
ID_ALPHABET: Final = re.compile(r"\A[a-z0-9][a-z0-9-]*\Z")

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
    runner_family: str = "claude"


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
            ("ANTHROPIC_DEFAULT_OPUS_MODEL", "glm-5.2"),
            ("ANTHROPIC_DEFAULT_SONNET_MODEL", "glm-5.2"),
            ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "glm-4.7"),
        ),
        note=(
            "The permitted mirror: the `claude` binary against z.ai's Anthropic-shaped "
            "endpoint, which consumes no Anthropic quota, credential or traffic. The "
            "base URL and the three model-slot variables are z.ai's own published "
            "integration (docs.z.ai/devpack/tool/claude). Needs ZAI_API_KEY in "
            "~/.arma-cti/credentials.env, which is #229's human item. Both slots that "
            "resolve to glm-5.2 are deliberate: the endpoint's live model list carries "
            "eight GLMs and only two of them are worth reaching from here, so the sonnet "
            "slot is the opus slot's synonym rather than a third arm nothing distinguishes."
        ),
        # The human's hard rule, 2026-08-05 (#238): this lane is used only off-peak, as a
        # dispatch-time refusal rather than as guidance. Only the human amends it.
        off_peak_only=True,
    ),
    "codex": Lane(
        name="codex",
        runner="codex",
        base_url="",
        credential="",
        model_slots=(),
        runner_family="codex",
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
    # The fable seat's route to a fable session (#269). #242 ruling 1 keeps fable for named
    # acts — retros; ADR, CONTEXT.md and schema semantics; retro evidence banking; the
    # #181-shaped diagnosis call — and says they are *dispatched* rather than resident. While
    # the orchestration seat was itself fable a subagent inherited it from its dispatcher,
    # which is how the twenty-fifth retro ran unattended; the seat drop to opus/high removed
    # that inheritance, and the ruling's "dispatched" had no `(model, effort)` token to
    # dispatch through. The seat was always expressible (`SEATS` has `fable`, and since
    # ADR-0071 ruling 1 no bar reaches it); only the profile was missing. Effort is `high`
    # per the Model roles
    # mapping, the effort fable acts run at; the model is `fable`, the alias the `claude`
    # runner documents for `--model` alongside `opus` and `sonnet` (verified against the
    # binary's own `--help`, not assumed from its siblings — `build_argv` passes `model`
    # straight through, so nothing else needed changing).
    "fable-medium": Profile("fable-medium", "claude-native", "fable", "medium"),
    "fable-high": Profile("fable-high", "claude-native", "fable", "high"),
    "fable-xhigh": Profile("fable-xhigh", "claude-native", "fable", "xhigh"),
    "fable-max": Profile("fable-max", "claude-native", "fable", "max"),
    # Two profiles on this lane and not ten, because effort collapses to a single arm
    # here — measured, not assumed (#225, docs/research/zai-lane-live-findings.md §2).
    # z.ai's endpoint honours `thinking.type` and ignores `thinking.budget_tokens`: one
    # hard prompt at budget 1,024 and at budget 32,000 both thought past 9,000 tokens and
    # both stopped on `max_tokens`, not on the budget. Claude Code's five effort levels
    # differ only in the budget they send, so on this lane all five are one configuration
    # and registering `-high` or `-xhigh` beside `-max` would be four names for one arm.
    # ADR-0061 predicted a partial collapse; the measurement makes it total.
    #
    # What remains genuinely distinct is the *model*, so the two profiles are the two
    # models worth reaching, named for the model and selected through the lane's slots:
    # `--model opus` resolves to glm-5.2 and `--model haiku` to glm-4.7.
    "zai-glm52-max": Profile("zai-glm52-max", "zai", "opus", "max"),
    "zai-glm47-max": Profile("zai-glm47-max", "zai", "haiku", "max"),
    # Four profiles on this lane, and the reason they are not one is the exact inverse of
    # z.ai's. There, effort collapsed: two thinking budgets a factor of thirty apart were
    # indistinguishable, so five names would have been five names for one arm. Here effort
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
    # rule the project holds, and it ends when a Codex orchestrator backup exists. That
    # "every seat" is a statement about seats, not a promise that nothing else refuses:
    # routing class 6's bridge still refuses a dispatch naming the gates themselves on
    # every lane but `claude-native`, and its landing half refuses the same row's paths
    # on a non-Claude `just land`, until #331's exemption list retires the row.
    claude_only: bool
    # ADR-0071 ruling 2's preference column, head first. `resolve_seat` walks exactly this
    # and nothing else, so a seat gains a route by being written here.
    preference: tuple[str, ...]
    # The ADR's escalation column, and deliberately **not** part of resolution. An
    # escalation is a judgement that the work is harder than the seat's tier, not a
    # fallback for a head the breaker happens to be refusing; resolving into it would
    # answer "this seat is out of profiles" by silently spending a dearer one, and would
    # make the exhaustion refusal unreachable for every seat that has an entry. It is
    # registry data — printed by `--list`, and what #333's arbiter rule reads — and
    # nothing resolves through it.
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
    # `recon` is read-only by description and deliberately does **not** carry a mode here.
    # #322 is the review seat's ticket, and forcing a mode on a seat nobody asked about
    # would be a behaviour change nothing in this issue's criteria covers. The column is
    # what makes joining a one-line edit when somebody does ask.
    permission_mode: str = ""


# Named once because two seats share it: ADR-0071 ruling 2 gives `review` "the
# implementer's list" and the implementer's escalation *head*. Sharing the object is what
# keeps that a fact rather than a copy that drifts. The rule that makes `review`'s
# resolution differ — never the profile under review, preferring a different lane — is
# #322's and lives in `review_candidates`, which reorders this list rather than holding a
# second one: the seat still prefers exactly these profiles in exactly this order, and what
# the reviewed profile changes is which of them are reachable and which goes first.
IMPLEMENTER_PREFERENCE: Final = ("codex-luna-max", "zai-glm52-max", "opus-low")
IMPLEMENTER_ESCALATION: Final = ("codex-sol-high", "opus-high")

# ADR-0071 ruling 2's seat table, transcribed. `mechanical` is **retired** by that ruling
# and is absent rather than kept for compatibility: it named a cheaper tier rather than a
# different job, and two names for one choice is what the retirement removes. `fable`
# survives the table because it is not in it — ADR-0071's ruling 3 hands retros to `retro`
# without deleting it; closing that overlap is #329's and #330's.
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
    ),
    "implementer": Seat(
        "implementer",
        claude_only=False,
        preference=IMPLEMENTER_PREFERENCE,
        escalation=IMPLEMENTER_ESCALATION,
    ),
    "recon": Seat("recon", claude_only=False, preference=("codex-luna-medium", "haiku-medium")),
    # ADR-0071 ruling 4 (#322) adds the two columns that make never-alone real. `reviews`
    # is what makes this seat's resolution take the profile under review as an input and
    # never return it; `permission_mode` forces the containment `--permission-mode`'s
    # writable default would otherwise have left to whoever typed the command.
    "review": Seat(
        "review",
        claude_only=False,
        preference=IMPLEMENTER_PREFERENCE,
        escalation=IMPLEMENTER_ESCALATION[:1],
        reviews=True,
        permission_mode="plan",
    ),
    # Ruling 3's own kind of work: the retro seat, on the preference order the ADR's own
    # table carries. That order is not the human's enumerated retro list of 2026-08-09
    # (#300) written out — the list named nine profiles, this names three, and the ADR's
    # trailer supersedes that ruling wholesale, which is why #327 could delete
    # `RETRO_APPROVED_PROFILES` and its guards (review round 1, claim 5). Profiles are
    # opaque tokens and no cross-provider ordering exists, so a profile joins by being
    # named, never "or above".
    "retro": Seat(
        "retro",
        claude_only=False,
        preference=("fable-high", "opus-xhigh", "codex-sol-xhigh"),
    ),
    "fable": Seat("fable", claude_only=False, preference=("fable-high",)),
    # ADR-0071 ruling 1's one survivor, and the only `claude_only=True` row the table
    # carries: orchestration runs on Claude with a Claude model until a tested
    # alternative exists. The ADR calls it the only provenance rule the project holds.
    "orchestrator": Seat("orchestrator", claude_only=True, preference=("opus-xhigh",)),
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
    "interlocutor": Seat(
        "interlocutor",
        claude_only=False,
        preference=("opus-xhigh", "codex-sol-xhigh"),
    ),
}


# The standing retro allowance lived here until #327: two `(fable, codex, …)` routes
# suspending ADR-0061 Decision 2's seat bar for #300's ruled retro profiles. ADR-0071
# ruling 1 rescinds that bar, and its trailer supersedes #300's ruling outright — #326
# already deleted the policy half (the two standing `route_exceptions`). Nothing
# consults an allowance once no bar exists to suspend, so the constant, its source line
# and its predicate are deleted here rather than kept as data nothing reads. The
# fable/`retro` seat overlap that ruling 3 leaves behind is #329's and #330's.


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

    `records` names the dispatch ids the profiles came from, in the order they were read, so
    a reader shown `potential_authors=` can go and look at the same records rather than take
    this scan's word for it.
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

    def __post_init__(self) -> None:
        """Refuse an unchecked stratum that carries a value — F1, made structural.

        A signal that did not run carries no value, so an unchecked stratum cannot be built
        with one (#323 review round 2 finding 1). The record boundary does not have to
        re-assert this — `document()` can write `value` unconditionally because nothing can
        put a real value beside `checked=False`. A frozen dataclass refuses the bad shape at
        construction; `known`, `unknown` and the reader all build through this, so the
        invariant is the type's, not a guard's.
        """
        if not self.checked and self.value is not None:
            message = "an unchecked Stratum carries no value (F1)"
            raise ValueError(message)

    @classmethod
    def known(cls, value: object) -> Stratum:
        """Build the stratum for a signal that ran: checked, with its value and no reason.

        The empty value is a value, not an absence — an empty label tuple means the issue
        carries no labels, and is checked-True where 'could not look' is checked-False.
        """
        return cls(value=value, checked=True, unchecked_why="")

    @classmethod
    def unknown(cls, why: str) -> Stratum:
        """Build the stratum for a signal that could not run: unchecked, value None, reason kept."""
        return cls(value=None, checked=False, unchecked_why=why)


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
            "routing_class_id": routing.rule_id if isinstance(routing, RoutingClass) else None,
            "routing_class_name": routing.name if isinstance(routing, RoutingClass) else None,
            "routing_class_checked": self.routing_class.checked,
            "routing_class_unchecked_why": self.routing_class.unchecked_why,
            "labels": list(labels) if isinstance(labels, tuple) else None,
            "labels_checked": self.labels.checked,
            "labels_unchecked_why": self.labels.unchecked_why,
        }


def _valueless_stratum(why: str) -> Stratum:
    """Build the value-less unchecked stratum without running the validator.

    `NO_STRATA`'s signals are unchecked by definition and carry no value, so the validator has
    nothing to check — and running it at import would make the type's own invariant un-testable:
    a mutant that inverts `__post_init__`'s check raises while `NO_STRATA` is still being built,
    crashing collection before any test can score the mutant as a kill. This private path skips
    the validator. It takes no value, so it cannot build the shape F1 refuses; its fields are
    identical to `Stratum.unknown(why)`. It bypasses `__init__` with `object.__new__` plus
    direct field setting because a frozen dataclass refuses ordinary assignment.
    """
    obj = object.__new__(Stratum)
    object.__setattr__(obj, "value", None)
    object.__setattr__(obj, "checked", False)
    object.__setattr__(obj, "unchecked_why", why)
    return obj


# `NO_STRATA` is built at import through `_valueless_stratum`, not `Stratum.unknown`: the
# constant is constructed while the module loads, and a mutant inverting `__post_init__`'s
# check would raise inside `unknown` while this line ran — crashing collection before any test
# could score the mutant. `_valueless_stratum` skips the validator (it takes no value, so it
# cannot build the shape F1 refuses), so the module imports under every mutant and the
# validator stays scoreable. Its fields are identical to `unknown("")`.
NO_STRATA: Final = Strata(
    gate_tier=_valueless_stratum(""),
    routing_class=_valueless_stratum(""),
    labels=_valueless_stratum(""),
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
    # surface is lost to a generic "malformed" (review round 3 finding 2). This is the one
    # state whose reason carries the value, keeping the four degradation states — a value
    # beside `checked: false`, a present non-mapping container, a record carrying none of the
    # value fields, and the plain pre-#323 absence — mechanically apart, so #336 can tell them
    # apart by reason without reading English.
    if checked is False and any(part is not None for part in raw_values):
        seen = raw_values[0] if len(raw_values) == 1 else raw_values
        return Stratum.unknown(f"the recorded {label} stratum was unchecked but carried {seen!r}")
    if not isinstance(checked, bool) or not isinstance(why, str):
        return Stratum.unknown(f"the recorded {label} stratum was malformed")
    if not checked:
        # F1 writes `None` for an unchecked value; the reason is the thing to keep.
        return Stratum.unknown(why)
    decoded = decode_value(raw_values)
    if decoded is _MALFORMED:
        if all(key not in row for key in value_keys):
            # None of the value fields this reader expects are present: the record was written
            # in an earlier shape (the flattened `routing_class` string before the split). Say
            # the fields are absent, not that the record is broken — it was valid in the shape
            # it was written in (review round 2 finding 4).
            return Stratum.unknown(
                f"the recorded {label} stratum carries none of the value fields this reader reads"
            )
        return Stratum.unknown(
            f"the recorded {label} stratum's value was not in the shape this reader expects"
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
            gate_tier=Stratum.unknown(reason),
            routing_class=Stratum.unknown(reason),
            labels=Stratum.unknown(reason),
        )
    row = found
    return Strata(
        gate_tier=_read_signal(
            row,
            value_keys=("gate_tier",),
            checked_key="gate_tier_checked",
            why_key="gate_tier_unchecked_why",
            decode_value=_gate_tier_value,
            label="gate_tier",
        ),
        routing_class=_read_signal(
            row,
            value_keys=("routing_class_id", "routing_class_name"),
            checked_key="routing_class_checked",
            why_key="routing_class_unchecked_why",
            decode_value=_routing_class_value,
            label="routing_class",
        ),
        labels=_read_signal(
            row,
            value_keys=("labels",),
            checked_key="labels_checked",
            why_key="labels_unchecked_why",
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

    def document(self) -> dict[str, object]:
        """Render the dispatch record, which names the credential key and never its value."""
        lane = LANES[self.identity.lane]
        return {
            "dispatch_id": self.identity.dispatch_id,
            "lane": self.identity.lane,
            "profile": self.identity.profile,
            "seat": self.identity.seat,
            "issue": self.identity.issue,
            "base_sha": self.identity.base_sha,
            "worktree": str(self.worktree),
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
    allowance that suspended it, but one further provenance refusal survives, outside
    this function: routing class 6's keep-on-Claude bridge, which refuses a dispatch
    whose issue names the gates themselves on every lane but `claude-native` — and,
    on the same row's landing half, a non-Claude `just land` whose diff touches them.
    It is #331's — retired when that issue's never-alone exemption list lands, because
    deleting it first would leave the gates with neither rule (review round 1, claim 1).
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
SEAT_PROFILE_BLOCKS: Final = frozenset(
    {
        # `codex-luna-max` heads the implementer preference list in the ADR but cannot take
        # the seat: #265's measured gate ceiling holds it below the binary capability rule.
        # `pair_block` states the ceiling in full; the measurement lives in
        # `_codex_sandbox_argv`.
        ("implementer", "codex-luna-max"),
    }
)


def pair_block(seat: str, profile_name: str) -> Refusal | None:
    """Return the refusal for a (profile, seat) pair blocked by ADR-0071 ruling 2, or `None`.

    This is the one home `SEAT_PROFILE_BLOCKS` is consulted, so `resolve_selection` calls it
    for a profile named directly and a future seat resolver (#321) calls it to skip a
    blocked preference — never a second copy of the list.

    No failure class, for `off_peak_refusal`'s reason exactly: this refusal found nothing
    about a provider or about code under test. The provider is up, the lane is reachable,
    the profile is registered, and this project declines to head a seat with a profile a
    measured ceiling holds below the seat's contract. `infra_unavailable` would assert an
    outage that is not happening and `provider_refused` a refusal Codex never made; a wrong
    class is a harness bug by CLAUDE.md's table, so this carries none.
    """
    if (seat, profile_name) not in SEAT_PROFILE_BLOCKS:
        return None
    return Refusal(
        "profile_blocked_for_seat",
        (f"profile={profile_name}", f"seat={seat}", "ceiling=#265"),
        (
            "ADR-0071 ruling 2: this (profile, seat) pair is blocked. #265's measured gate "
            "ceiling holds it below the seat's contract — no `writable_roots` set lets a "
            "Codex dispatch both commit and run its own gate, because the commit needs the "
            "per-worktree git directory named directly and the gate needs that same directory "
            "not named (see `_codex_sandbox_argv`), and an implementer that cannot run its "
            "own gate is not an implementer under the binary capability rule. The same "
            "profile on a read-only seat dispatches normally, because a read-only seat needs "
            "neither commit nor gate. What would clear it: #265 — a Codex discovery path "
            "that lets the gate run under the same roots that let the commit through. "
            "Nothing was dispatched."
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

    **The absent case refuses**, which is the whole point: a review seat with no declared
    subject cannot be resolved past anything, and resolving it anyway would take the head of
    the implementer's list — the same profile the implementer took — and call it a review.
    That is the silent same-model review this ticket exists to make impossible, so it is a
    named refusal rather than a default.

    The flag is refused on a seat that does not review, because an option that silently
    decides nothing is one a caller will believe did something.

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
                "`--reviewing <profile>`. Without it nothing here can resolve past that "
                f"profile, and resolving anyway would take the same head the implementer "
                f"took. {NEVER_ALONE} Nothing was dispatched."
            ),
        )
    if reviewed not in PROFILES:
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


def _read_record(entry: Path, issue: int) -> _Read:
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
    # them a gap in it.
    seat = SEATS.get(str(document.get("seat", "")))
    if not same_issue or (seat is not None and seat.reviews):
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
    directory = dispatch_dir.expanduser()
    if not directory.is_dir():
        return Authorship(why="no_dispatch_records")
    found: list[str] = []
    records: list[str] = []
    unreadable = 0
    for entry in sorted(directory.iterdir()):
        if not entry.is_dir():
            # Not a record at all. A stray file beside the records is not a record this scan
            # failed to read, so it does not make the read partial.
            continue
        read = _read_record(entry, issue)
        unreadable += int(read.unreadable)
        if read.profile and read.profile not in found:
            found.append(read.profile)
            records.append(read.record)
    if unreadable:
        return Authorship(tuple(found), tuple(records), why="records_unreadable")
    if found:
        return Authorship(tuple(found), tuple(records))
    return Authorship(why="no_authoring_dispatch")


def review_authorship(seat: Seat, args: argparse.Namespace) -> Authorship:
    """Read the records, on the one seat and the one dispatch that has a subject to check."""
    if not seat.reviews or not args.reviewing:
        return Authorship()
    return potential_authors(args.issue, Path(args.dispatch_dir))


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
            f"The dispatch records for #{issue} place its work on "
            f"{' and '.join(authorship.potential)}, and this dispatch declares it is reviewing "
            f"{reviewed}, which is none of them. One of the two is wrong, and the declaration "
            "is the half a caller controls, so it is the half that is refused. Nothing was "
            "dispatched. Name a profile the records carry, or — if the work was done somewhere "
            "these records cannot see — say so on the issue and dispatch from a box that holds "
            "the record, because a subject nobody can check is the hole this refusal exists to "
            f"close. {NEVER_ALONE}"
        ),
    )


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
    invariant. Those prices are not comparable, so the conservative side is the only one.

    One home, so that resolution, the refusal text and the printed route cannot disagree
    about which profiles this dispatch was never going to take.
    """
    return frozenset({reviewed, *authorship.potential})


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
    refuse a genuinely different model — GLM-5.2 reviewing Luna's work is a different
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
    subject = PROFILES.get(reviewed)
    if subject is None:
        # `reviewed_profile_refusal` refuses an absent or unregistered subject above every
        # resolution, so this is the rendering path only: a dispatch record read back off
        # disk can name a profile the registry has since dropped, and printing what that
        # dispatch could walk must not raise. Empty is also the fail-closed answer if this
        # were ever reached while deciding — no candidate resolves.
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
            f"issue's own dispatch records carry ({' '.join(authorship.records)}) — so it may "
            "have coauthored the change it would be clearing. The invariant is about every "
            "profile that worked on the change, not the one a caller chose to declare. Name a "
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


def breaker_refusal(lane_name: str, breaker_dir: Path, now: float) -> Refusal | None:
    """Read this lane's breaker before anything is planned, and refuse a tripped one (#226).

    This is the integration point ADR-0061 Decision 7 asks for: the state is read
    *before* dispatch, so a lane whose quota is gone costs nothing to discover, and the
    wait it hands back is a published window boundary rather than a guess. A quality
    trip refuses with `provider_refused` instead — waiting does not fix a lane that is
    serving the wrong thing, and that row's response is exactly the right one: not a
    result, re-dispatch elsewhere, and escalate.
    """
    result = breaker.lane_verdict(breaker.Store(directory=breaker_dir), lane_name, now)
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


def candidate_refusal(
    args: argparse.Namespace, seat: str, profile_name: str, now: datetime
) -> Refusal | None:
    """Judge one preference entry with the same rungs the ladder judges a named route by.

    Which rungs, and the rule that decides: **a rung belongs here when it is a function of
    `(lane, profile, seat)` and of nothing else.** Those are the registry, the carve-out,
    the `(profile, seat)` block, the lane's breaker and the human's off-peak rule — each
    one the ladder's own function, called here rather than restated, because a second copy
    is how a profile comes to be dispatchable to a resolver and refused by the ladder two
    lines later. The profile's admission standing was one of these until #328 dropped the
    bar; nothing replaced it here, and a route is now judged by nothing upfront.

    Readiness and the queue policy are deliberately absent: each reads the *issue*, so each
    judges the dispatch rather than the candidate, and no change of profile could ever clear
    one. The routing policy is a function of both and is #326's to fold in; leaving it out
    means a resolved route can still be refused by the ladder below, which is the honest
    outcome — the alternative is this resolver quietly re-deciding a policy question.

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
    refusal = breaker_refusal(lane.name, Path(args.breaker_dir).expanduser(), now.timestamp())
    if refusal is not None:
        return refusal
    refusal = off_peak_refusal(lane, now)
    if refusal is not None:
        return refusal
    _, refusal = lane_credential(lane, Path(args.credentials).expanduser())
    return refusal


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
            "about the work and is deliberately not resolved into automatically."
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
    marks the subject unchecked and still excludes everything it did read.
    """
    refusal = unknown_seat_refusal(args.seat)
    if refusal is not None:
        return None, refusal
    refusal = reviewed_profile_refusal(args.seat, args.reviewing)
    if refusal is not None:
        return None, refusal
    seat = SEATS[args.seat]
    authorship = review_authorship(seat, args)
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
    passing nothing could edit — and a review that can edit is a review that can land its
    own findings, which is the containment `docs/review-dispatch.md` says the mode is the
    mechanism for. Overwriting whatever the caller passed is deliberate: a containment a
    caller can switch off by typing a flag is a default, and this ruling asked for the other
    thing. It is never silent — `Resolution.containment_lines` names the seat that forced
    it, in the dry run and in the record's own argv.

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


def default_brief(identity: Identity, worktree: Path) -> str:
    """Compose the brief a dispatch sends when the caller named no file.

    Deliberately thin: it states the assignment and points at the issue, because a
    default that invented instructions would be a second, untracked copy of the seat's
    contract. The single-shot contract is the one operational rule a thin brief cannot
    omit, because a dispatched session has no second turn to recover from missing it.
    """
    return (
        f"You are the {identity.seat} seat, dispatched as {identity.dispatch_id} on the "
        f"{identity.lane} lane under profile {identity.profile}.\n\n"
        f"{SINGLE_SHOT_CONTRACT}\n\n"
        f"Worktree: {worktree}\n"
        f"Base SHA: {identity.base_sha}\n"
        f"Issue: #{identity.issue}\n\n"
        f"Read CLAUDE.md, then `gh issue view {identity.issue}`, and do that issue's "
        f"work in the worktree above and nowhere else. The issue's acceptance criteria "
        f"are the contract. Run `just fast` after every edit.\n"
    )


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


def main_checkout(cwd: Path) -> Path:
    """Return the main checkout, which is where `.claude/worktrees` lives.

    `git worktree list` puts the main worktree first from any of them, which is
    `tools/worktree.py`'s reasoning and matters here for the same reason: a dispatch
    armed *from inside* a worktree must default its assignment to a sibling under the
    main checkout, not to `<this worktree>/.claude/worktrees/…`, which is nowhere.
    """
    for line in git("worktree", "list", "--porcelain", cwd=cwd).splitlines():
        if line.startswith("worktree "):
            return Path(line.removeprefix("worktree ").strip())
    return cwd


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


def _codex_sandbox_argv(permission_mode: str, project_dir: Path) -> tuple[str, ...]:
    """Return the sandbox flags, widened where `workspace-write` alone withheld the intent.

    The human ruled on 2026-08-06 (#221 decision 2, #259) that a dispatched Codex session
    gets the same *intent* as the widened `zai` allowlist — run the gate, make its own
    commit, land it — and left the mechanism to be worked out, with one option ruled out by
    name: `--dangerously-bypass-approvals-and-sandbox`, which disables the sandbox rather
    than widening it. The ruling also said to **measure before changing**, because
    `workspace-write` might already have delivered it.

    It did not, and the measurement is why this function exists. Dispatch
    `d-20260806-163129-479a57`, base `873a0c8`, ran under plain `--sandbox workspace-write`
    and got as far as `git add`::

        fatal: Unable to create '/home/andre/code/github.com/andrewesweet/arma-cti/.git/
        worktrees/issue-259-codex/index.lock': Read-only file system

    `git status`, `git log` and `git diff` had all succeeded — reads. The refusal is
    structural rather than incidental: this project dispatches into **linked worktrees**, so
    the session's cwd is `<main checkout>/.claude/worktrees/issue-<N>` while its git metadata
    lives in `<main checkout>/.git/worktrees/issue-<N>`, above the one root
    `workspace-write` makes writable. Every commit was therefore out of reach, and with it
    the gate and the landing that follow it.

    Three roots and one flag, each measured necessary and none inferred:

    - **The main checkout**, because `just land`'s final step is `git -C <main checkout>
      merge --ff-only origin/main`, which writes that checkout's working tree. A grant that
      stopped short of it would push and then refuse `merge_blocked_by_sandbox` — the
      Claude-side finisher again, smaller but still there. Derived per invocation rather
      than written down, so a dispatch from a second checkout widens to that one.
    - **Both git directories, each named in its own right**, which is the finding worth
      carrying forward: *Codex refuses a write under a `.git` directory unless that exact
      directory is a writable root, and naming an ancestor does not lift the refusal for a
      nested one.* Measured in two steps rather than argued. Probe
      `d-20260806-164858-905eb2` wrote a file beside `.git` (`MAINROOT_OK`) while `.git/p2`
      refused, so the repository root had applied and `.git` was carved out of it. Naming
      `.git` then made `.git/topA` succeed while
      `.git/worktrees/issue-259-codex/subB` — the linked worktree's own directory, where its
      index, `HEAD` and `FETCH_HEAD` live — refused in the same command; naming that
      directory too made both succeed. `_codex_writable_roots` asks git for both.
    - **`~/.cache/uv`**, because `uv` acquires a lock there before any test runs: without it
      `just check`, `just unit` and `just fast` all died at `check-generated` on
      ``Could not create temporary file … Read-only file system``. `~/.cargo` was measured
      *not* necessary — the gate ran green without it — though that was against a warm cargo
      registry, and a cold one may want writing.
    - **`network_access`**, which defaults off while `just land` fetches and pushes. Proven
      reachable at `NET_HTTP_200` under the same probe.

    Both readings come from the same box on 2026-08-06. This set buys the commit, not the
    gate: `cog check` went red under it (`d-20260806-172045-9a0a0e`, `could not find
    repository`), which is #265. The mechanism is now measured, not open: read-only probe
    `d-20260807-222221-1a2c7e` (`codex-terra-low`) ran `strace -f -e
    trace=openat,stat,statx,newfstatat` over `cog check` inside the sandbox and found the
    sandbox had created an empty directory at `<main>/.git/worktrees/<name>/.git` (mode
    0555, size 40) — a mount point injected for that writable root, where no real git
    layout puts a `.git`. libgit2 stats it during repository discovery, mistakes it for a
    repository, probes for its `commondir` and `HEAD`, gets `ENOENT` for both, and reports
    `could not find repository`: it found too many repositories, not none. Outside the
    sandbox that directory does not exist and `cog check` is green at the same commit.

    The one alternative a `writable_roots` list admits — naming the parent
    `<main>/.git/worktrees` instead of the per-worktree directory itself — is the set
    `d12a27f` ran (`--absolute-git-dir`'s `.parent` resolves to exactly that path), and it
    is refuted: probe `d-20260808-075346-f27564` found `git add` itself refused under it,
    `index.lock` read-only, because Codex's `.git` carve-out does not confer write on a
    nested directory merely by naming an ancestor. The dichotomy is structural, not a pair
    of unlucky tries: a commit needs the exact per-worktree directory named, else the
    carve-out holds its `index.lock` read-only (#259); the gate needs that same directory
    *not* named, else the injected `.git` defeats libgit2 (#265). No `writable_roots` set
    satisfies both, and `--dangerously-bypass-approvals-and-sandbox` was declined on #221.
    So this four-root set, both git directories named directly, stands as the known-good
    commit baseline, and the gate half of #265 is a recorded ceiling rather than an open
    question. The consequence — a hand-finished landing for any Codex route — is stated
    once in `docs/multi-provider-dispatch.md` and §10 of
    `docs/research/codex-lane-live-findings.md`.

    **This is not parity with the `zai` lane and must not be described as one.** That lane's
    grant is a list of named commands; this one is a filesystem and network policy that every
    command the session runs inherits. Network access in particular is strictly more than the
    `zai` half has: there, only the allowlisted `just land` and `gh` reach the network at all.
    ADR-0061 decision 5's non-commensurability point is the reason the two are stated
    separately in `docs/multi-provider-dispatch.md` rather than claimed equal.

    Read-only modes are left exactly as they were. A review seat has nothing to commit and
    nothing to land, so neither override has anything to buy there, and a sandbox that stays
    narrow when nothing needs it wider is the point of mapping per mode at all.
    """
    flags = CODEX_SANDBOX.get(permission_mode, CODEX_SANDBOX["default"])
    if flags != CODEX_SANDBOX["acceptEdits"]:
        return flags
    roots = ", ".join(
        hook_parity.toml_string(str(path)) for path in _codex_writable_roots(project_dir)
    )
    return (
        "--config",
        f"sandbox_workspace_write.writable_roots=[{roots}]",
        "--config",
        "sandbox_workspace_write.network_access=true",
        *flags,
    )


def _codex_writable_roots(project_dir: Path) -> tuple[Path, ...]:
    """Return the directories a Codex session must write to commit, gate and land.

    The session's own worktree is already writable and so is not listed — Codex's
    `workspace-write` grants cwd, and `writable_roots` is documented as "additional folders
    (beyond cwd and possibly TMPDIR)".

    **Both git directories are named, and that is not belt and braces.** Measured on
    2026-08-06: Codex refuses a write under a `.git` directory unless *that exact directory*
    is a writable root, and naming an ancestor does not lift the refusal for a nested one.
    With `<main>/.git` granted, `<main>/.git/topA` was created and
    `<main>/.git/worktrees/issue-259-codex/subB` was still "Read-only file system"; adding
    the per-worktree directory made both succeed. This project dispatches into linked
    worktrees, where the index, `HEAD` and `FETCH_HEAD` all live in the second one — so
    granting only the common directory buys a session `git log` and nothing it needs.

    That exact-name requirement is also the gate's undoing, which is #265 and is a
    recorded ceiling, not a fix to chase here. Naming the per-worktree directory directly
    makes Codex's sandbox inject an empty `<dir>/.git` mount point that libgit2 — and so
    `cog check` — trips over during discovery; the alternative of naming its parent
    `<main>/.git/worktrees` instead is refuted (the carve-out keeps `index.lock` read-only).
    So "name both exactly" buys the commit and loses the gate, and no `writable_roots` set
    buys both. The measurement and the consequence are carried in `_codex_sandbox_argv`'s
    docstring; this function keeps assembling the set that commits.

    Asked of git rather than assembled from strings, because git is the authority on where
    its own metadata is: in a plain checkout the two answers coincide and the duplicate is
    dropped, and a `--git-common-dir` that comes back relative is resolved against the tree
    it was asked about. A tree git cannot read yields neither, and the caller is left with
    the roots it can still name — a dispatch into a non-repository has no commit to make.

    `uv`'s cache is read from the environment the way `uv` reads it, so a box that relocates
    it does not silently lose the gate. A root that does not exist is not an error: Codex
    logs it and carries on, which is the right shape for a path that follows a convention
    rather than a fact.
    """
    roots = [main_checkout(project_dir)]
    for spelling in ("--absolute-git-dir", "--git-common-dir"):
        answer = git("rev-parse", spelling, cwd=project_dir)
        if answer:
            roots.append(Path(answer) if Path(answer).is_absolute() else project_dir / answer)
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    roots.append(Path(os.environ.get("UV_CACHE_DIR") or cache / "uv"))
    return tuple(dict.fromkeys(roots))


def build_argv(
    lane: Lane, profile: Profile, permission_mode: str, project_dir: Path
) -> tuple[str, ...]:
    """Build the runner's argv, which carries no secret, because a secret on argv is in `ps`.

    The brief goes in on stdin for the same reason it is not a positional prompt: argv
    is world-readable on this box, and a brief quoting an issue is not something to
    publish to every process table reader either. Both families read it there: `claude
    --print` and `codex exec` with no positional prompt both take the task on stdin.

    Dispatching on `lane.runner_family` rather than on `lane.runner` is what keeps two
    lanes that share the `claude` binary sharing one builder.
    """
    if lane.runner_family == "codex":
        return _codex_argv(lane, profile, permission_mode, project_dir)
    return (
        lane.runner,
        "--print",
        "--model",
        profile.model,
        "--effort",
        profile.effort,
        "--permission-mode",
        permission_mode,
    )


def _codex_argv(
    lane: Lane, profile: Profile, permission_mode: str, project_dir: Path
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
        "--config",
        f'model_reasoning_effort="{profile.effort}"',
        "--config",
        _codex_metrics_override(),
        *_codex_hook_argv(project_dir),
        *_codex_sandbox_argv(permission_mode, project_dir),
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
    return _as_refusal(
        queue_policy.check_refusal(
            policy, args.issue, in_flight, queue_policy.surfaces_of(in_flight)
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


def capture_strata(body: str, issue: int, seat: str, root: Path, *, body_from_file: bool) -> Strata:
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

    Routing class: lane-blind `classify_issue`, so a Claude-native dispatch carries the
    class any other lane would. A body that declares no class is the empty string and is
    distinct from an unreadable policy, which is the unchecked state — the third value
    #323 names, never collapsed with 'no class'.

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
        match = routing_policy.classify_issue(read.policy, body, seat)
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
    orchestration issue taken by an unadmitted seat, and hears nothing about classes 4 and 5
    refusing no route, class 6 naming a minority of the gates, or the landing rung not
    re-checking any of it.

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


def plan_dispatch(
    args: argparse.Namespace,
    root: Path,
    now: datetime,
) -> tuple[Plan | None, str, Refusal | None]:
    """Validate the request and mint the plan and the brief, writing nothing."""
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

    worktree = (
        Path(args.worktree).expanduser()
        if args.worktree
        else root / ".claude" / "worktrees" / f"issue-{args.issue}"
    )
    if not worktree.is_dir():
        return (
            None,
            "",
            Refusal(
                "worktree_missing",
                (f"worktree={worktree}",),
                (
                    f"Create it first: `just worktree add issue-{args.issue}`. A dispatch "
                    "does not create the tree it assigns, because creating one it cannot "
                    "prove is exclusive is exactly #105's failure."
                ),
                failure_class="infra_unavailable",
            ),
        )

    # #105's sixth instance: a tree is not free merely because it is clean. The pre-flight
    # answers "is this tree clean now" and the question that produced two agents in one
    # worktree was "is anyone still working in it", which nothing asked. The dispatch
    # record directory answers it — a record with no `result.json` is live, or dead
    # without having written one — and this rung sits directly below the existence check
    # because both are properties of the assigned tree rather than of the request (#308).
    refusal = _from_stop(
        dispatch_stop.occupancy_refusal(worktree, Path(args.dispatch_dir).expanduser())
    )
    if refusal is not None:
        return None, "", refusal

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

    identity = Identity(
        dispatch_id=dispatch_id,
        lane=lane.name,
        profile=profile.name,
        seat=args.seat,
        issue=args.issue,
        base_sha=base_sha,
    )
    brief = (
        Path(args.brief_file).expanduser().read_text(encoding="utf-8")
        if args.brief_file
        else default_brief(identity, worktree)
    )
    plan = Plan(
        identity=identity,
        worktree=worktree,
        record=Path(args.dispatch_dir).expanduser() / dispatch_id,
        argv=build_argv(lane, profile, args.permission_mode, worktree),
        credentials=credentials,
        permission_mode=args.permission_mode,
        route=route,
        planned_at=now,
        breaker_dir=breaker_dir,
        advisories=readiness_advisories(args.issue, found),
        routing=routing_clearance(args, root, found, now),
        strata=capture_strata(
            found.body, args.issue, route.seat, root, body_from_file=bool(args.issue_body)
        ),
    )
    return plan, brief, None


def write_record(plan: Plan, brief: str) -> None:
    """Lay down the dispatch record: the plan, and the brief exactly as it will be sent."""
    plan.record.mkdir(parents=True, exist_ok=True)
    (plan.record / "dispatch.json").write_text(
        json.dumps(plan.document(), indent=2) + "\n", encoding="utf-8"
    )
    (plan.record / "brief.md").write_text(brief, encoding="utf-8")


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
    )


def write_result(record: Path, **fields: object) -> None:
    """Write the run's own outcome beside its plan — facts only, never a verdict.

    A returncode is not a failure class. What a dispatched run's exit code means about
    the code under test is the gates' business, and inventing a class here would be a
    second, untested opinion about it.
    """
    (record / "result.json").write_text(json.dumps(fields, indent=2) + "\n", encoding="utf-8")


def unreadable_record_refusal(record: Path, unreadable: Exception) -> tuple[str, ...]:
    """Refuse a record that cannot be read back, and leave the refusal beside it.

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
    refusal = Refusal(
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
    # A record directory that does not exist at all reaches here — `FileNotFoundError` out
    # of `load_record` is one of the ways a pointed-at record fails — and there is nowhere
    # to leave the refusal then. The refusal still goes back to the caller either way.
    if record.is_dir():
        write_result(
            record,
            dispatch_id=record.name,
            refusal=refusal.kind,
            failure_class=refusal.failure_class,
            ended_at=datetime.now(tz=UTC).isoformat(),
        )
    return refusal.lines()


def run_dispatch(record: Path, parent: Mapping[str, str]) -> tuple[int, tuple[str, ...]]:
    """Run the detached child: assert the worktree, assemble the environment, start the runner.

    An unreadable record refuses rather than raising into the seam. The child is detached,
    so an uncaught exception here reaches nobody but `dispatch.log`; a named refusal with a
    failure class reaches whoever reads `result.json`, and `infra_unavailable` is the right
    one — a record this code did not write says nothing about the code under test.

    The whole read-back is inside that guard, not only the JSON parse, because the record
    fails in more ways than one and every one of them lands in the same place. Measured:
    a `planned_at` that is not an instant raises `ValueError`, an `issue` or `argv` of the
    wrong JSON type raises `TypeError`, a since-retired profile or an unregistered lane
    raises `KeyError` out of the registries, and an absent `dispatch.json` or `brief.md`
    raises `OSError`. Registry churn makes the two `KeyError`s the likely ones in
    practice — a record naming a profile this version no longer has is precisely "a
    record this code did not write" — and they used to sit one and two lines outside the
    guard, which meant no `result.json` and a dispatch the ledger and `occupancy` see as
    started and never ended. The same consequence used to reach past the guard through the
    worktree, which comes off the record too: `subprocess.run(cwd=…)` raises before git
    runs when the assigned tree is gone, which `just worktree done` makes routine. `git`
    now answers the empty string there, so that record refuses `worktree_unreadable` with
    a `result.json` beside it — the branch that names the case can now reach it.

    The brief is read here rather than at its point of use for the same reason and no
    other: it is part of the record, so an unreadable one is this refusal and not a
    traceback. It is not inert, and the cost is worth stating: a record whose worktree is
    also gone now refuses `dispatch_unreadable` where it used to refuse
    `worktree_unreadable`, and the worktree diagnosis is the more actionable of the two —
    it names `just worktree add`. Read-back before assignment is still the right order,
    because a record that will not read back cannot be trusted to name a worktree at all.
    """
    try:
        plan = load_record(record)
        profile = PROFILES[plan.identity.profile]
        lane = LANES[plan.identity.lane]
        brief = (record / "brief.md").read_text(encoding="utf-8")
    except (KeyError, TypeError, ValueError, OSError) as unreadable:
        return EXIT_REFUSED, unreadable_record_refusal(record, unreadable)

    refusal = assert_worktree(plan.worktree, git("rev-parse", "--show-toplevel", cwd=plan.worktree))
    if refusal is None:
        token, refusal = lane_credential(lane, plan.credentials)
    if refusal is not None:
        write_result(
            record,
            dispatch_id=plan.identity.dispatch_id,
            refusal=refusal.kind,
            failure_class=refusal.failure_class,
            ended_at=datetime.now(tz=UTC).isoformat(),
        )
        return EXIT_REFUSED, refusal.lines()

    child = assemble_environment(parent, profile, plan.identity, token)
    started = datetime.now(tz=UTC)
    # S603: argv is the registry's runner plus registry values; the brief is on stdin so
    # that nothing a dispatch carries reaches the process table.
    done = subprocess.run(  # noqa: S603
        list(plan.argv),
        cwd=plan.worktree,
        env=child,
        input=brief,
        text=True,
        check=False,
    )
    outcome, reset_at = classify_finished_run(record, done.returncode)
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
    write_result(
        record,
        dispatch_id=plan.identity.dispatch_id,
        returncode=done.returncode,
        outcome=outcome,
        started_at=started.isoformat(),
        ended_at=datetime.now(tz=UTC).isoformat(),
    )
    return done.returncode, (f"dispatch={plan.identity.dispatch_id}", f"exit={done.returncode}")


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
    and marked, because it is registry data that resolution deliberately does not walk — a
    reader who saw only the preference would have no way to tell whether an absent
    escalation meant "none" or "not shown".

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
        f"  escalation={' '.join(seat.escalation) or 'none'} (not resolved into)",
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
    # and the block is stated wherever the registry is read. `codex-luna-max` renders as a
    # profile and `implementer` renders as an eligible seat, so a reader who paired them
    # would discover the exception only by attempting the dispatch; the line names the
    # ceiling so they do not have to. The ceiling is taken from `pair_block` rather than
    # named a second time here, so the registry and the refusal cannot drift apart.
    for seat, profile_name in sorted(SEAT_PROFILE_BLOCKS):
        block = pair_block(seat, profile_name)
        if block is None:  # pragma: no cover - a member that does not block is a registry bug
            # #320's review found this branch skipping where the assertion it replaced failed
            # loudly. A member of `SEAT_PROFILE_BLOCKS` that `pair_block` clears is the two
            # halves of one fact disagreeing, and the registry listing's job is to state that
            # fact; printing the listing without the block would be the quiet wrong answer.
            message = (
                f"SEAT_PROFILE_BLOCKS carries ({seat}, {profile_name}) and pair_block cleared it"
            )
            raise ValueError(message)
        ceiling = next(line for line in block.found if line.startswith("ceiling="))
        lines.append(f"seat_profile_block=adr0071 seat={seat} profile={profile_name} {ceiling}")
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
    child = redacted(assemble_environment(parent, profile, plan.identity, token), token)
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
    lines += [f"env_child.{key}={child[key]}" for key in sorted(child) if key not in parent]
    lines += [
        f"env_child.{key}={child[key]}"
        for key in sorted(child)
        if key in parent and child[key] != parent[key]
    ]
    lines += [f"env_stripped.{key}" for key in LANE_OWNED if key in parent and key not in child]
    return tuple(lines)


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

    plan, brief, refusal = plan_dispatch(
        args, main_checkout(Path.cwd()), datetime.now(tz=UTC) if now is None else now
    )
    if refusal is not None or plan is None:
        return emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    if args.dry_run:
        return emit(dry_run_lines(plan, brief, os.environ), 0)

    write_record(plan, brief)
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
