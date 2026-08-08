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
- **Seat** carries Decision 2's eligibility. Work may leave Claude only where a
  mechanical gate catches a wrong answer, so a foreign lane refuses the seats the ADR
  excludes — the fable seat and orchestration — rather than trusting the caller to
  remember. On `claude-native` nothing is leaving Claude and every seat is dispatchable.
  One human ruling suspends the fable bar for `codex`/`codex-sol-xhigh` until its stated
  instant; the clock reapplies the standing bar without a later revocation (#217, #270).
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

**The profile's admission standing is read before anything is planned** (#224). ADR-0061
Decision 6 admits a profile to a seat on a bar pre-registered against the Claude history,
and the human ruled that bar on 2026-08-05T20:00Z; `tools/admission.py` is the ruling. What
reaches this file is its far end only: a profile whose second attempt at the bar has failed
is refused here, because the ruling allows one re-run and no more and a third attempt is
otherwise an improvisation nobody would notice. A profile still *on* probation dispatches
normally — the record the bar judges accrues only as the lane runs, so refusing probation
would make the bar unclearable — and `claude-native` is exempt throughout, since nothing is
leaving Claude there.

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
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets as secrets_module
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple
from urllib.parse import quote

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `stall_watch.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes these importable.
import admission
import breaker
import hook_parity
import queue_policy
import readiness

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

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
    foreign: bool
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


# The registry. Adding a lane or a profile is an edit here and nowhere else, which is
# the whole point of Decision 5: no caller anywhere gets to compose a model with an
# effort, because across providers those two do not compose.
LANES: Final[dict[str, Lane]] = {
    "claude-native": Lane(
        name="claude-native",
        runner="claude",
        base_url="",
        credential="",
        model_slots=(),
        foreign=False,
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
        foreign=True,
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
        foreign=True,
        runner_family="codex",
        note=(
            "OpenAI's Codex CLI against the ChatGPT Plus subscription, permitted by the "
            "human's 2026-08-06 ruling on #229. **No credential of ours and none on the "
            "environment**: the CLI reads its own `~/.codex/auth.json` at mode 0600, so "
            "this lane's credential column is empty for a different reason than "
            "`claude-native`'s — there it is the box's Claude login, here it is the box's "
            "ChatGPT login, and in neither case does `just dispatch` handle a secret. "
            "The models are the two the authenticated catalogue lists as agentic coding "
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
    "sonnet-high": Profile("sonnet-high", "claude-native", "sonnet", "high"),
    "haiku-medium": Profile("haiku-medium", "claude-native", "haiku", "medium"),
    # The fable seat's route to a fable session (#269). #242 ruling 1 keeps fable for named
    # acts — retros; ADR, CONTEXT.md and schema semantics; retro evidence banking; the
    # #181-shaped diagnosis call — and says they are *dispatched* rather than resident. While
    # the orchestration seat was itself fable a subagent inherited it from its dispatcher,
    # which is how the twenty-fifth retro ran unattended; the seat drop to opus/high removed
    # that inheritance, and the ruling's "dispatched" had no `(model, effort)` token to
    # dispatch through. The seat was always expressible (`SEATS` has `fable`, barred on a
    # foreign lane only); only the profile was missing. Effort is `high` per the Model roles
    # mapping, the effort fable acts run at; the model is `fable`, the alias the `claude`
    # runner documents for `--model` alongside `opus` and `sonnet` (verified against the
    # binary's own `--help`, not assumed from its siblings — `build_argv` passes `model`
    # straight through, so nothing else needed changing).
    "fable-high": Profile("fable-high", "claude-native", "fable", "high"),
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
    "codex-sol-high": Profile("codex-sol-high", "codex", "gpt-5.6-sol", "high"),
    "codex-terra-medium": Profile("codex-terra-medium", "codex", "gpt-5.6-terra", "medium"),
    "codex-terra-low": Profile("codex-terra-low", "codex", "gpt-5.6-terra", "low"),
}

# ADR-0061 Decision 2: eligibility is a property of the surface, not a per-task
# judgement. A seat is dispatchable to a foreign lane when a mechanical gate catches a
# wrong answer from it. Review is eligible on Decision 3 — its output is claims, which
# land nothing on their own.
SEATS: Final[dict[str, bool]] = {
    "implementer": True,
    "mechanical": True,
    "recon": True,
    "review": True,
    "fable": False,
    "orchestrator": False,
}


# The human's ruling of 2026-08-06T21:15Z (#217, #issuecomment-5209125413), verbatim:
# "Allow retros to be conducted by GPT 5.6 Sol xhigh until 1400 on Monday 10th Aug 2026."
# Retros are a fable act. The ruling routes that one act to exactly this triple until
# exactly this instant. These singular values deliberately are not a temporary-allowance
# registry: every other fable-on-foreign combination, and orchestrator everywhere, remain
# governed by `SEATS` throughout.
RETRO_FABLE_ALLOWANCE: Final = ("fable", "codex", "codex-sol-xhigh")
RETRO_FABLE_ALLOWANCE_EXPIRES_AT: Final = datetime(2026, 8, 10, 14, 0, tzinfo=UTC)
RETRO_FABLE_ALLOWANCE_SOURCE: Final = "#217 #issuecomment-5209125413"


def retro_fable_allowance_is_live(
    seat: str, lane_name: str, profile_name: str, now: datetime
) -> bool:
    """Whether #217's one ruled triple is still before its expiry instant."""
    return (
        seat,
        lane_name,
        profile_name,
    ) == RETRO_FABLE_ALLOWANCE and now < RETRO_FABLE_ALLOWANCE_EXPIRES_AT


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


class Plan(NamedTuple):
    """Everything the detached child needs, and nothing it must not write down."""

    identity: Identity
    worktree: Path
    record: Path
    argv: tuple[str, ...]
    credentials: Path
    permission_mode: str
    breaker_dir: Path = breaker.DEFAULT_BREAKER_DIR
    # What the readiness rung said about the issue without refusing it (#241). On the
    # record rather than only on stdout, because an advisory nobody kept is an advisory
    # nobody can count later — and counting them is how this project will know whether
    # the enumerability sub-check ever earns a hard refusal.
    advisories: tuple[str, ...] = ()

    def document(self) -> dict[str, object]:
        """Render the dispatch record, which names the credential key and never its value."""
        lane = LANES[self.identity.lane]
        planned_at = datetime.now(tz=UTC)
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
            "readiness_advisories": list(self.advisories),
            "resource_attributes": dict(self.identity.attributes()),
            "plan_charge": plan_charge(lane, planned_at),
            "planned_at": planned_at.isoformat(),
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


def resolve_selection(
    lane_name: str, profile_name: str, seat: str, now: datetime | None = None
) -> Refusal | None:
    """Check lane, profile and seat against the registry and against Decision 2.

    Decision 2's standing bar remains in `SEATS`. The only exception is #217's exact
    retro triple before its expiry instant; `now` alone decides whether it holds. The
    planning ladder passes the same clock it threads to the breaker and off-peak rungs.
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
    if seat not in SEATS:
        return Refusal(
            "unknown_seat",
            (f"seat={seat}", f"known={' '.join(sorted(SEATS))}"),
            "Name a known seat: the seat is a telemetry attribute and a typo mis-attributes.",
        )
    at = now or datetime.now(tz=UTC)
    if (
        LANES[lane_name].foreign
        and not SEATS[seat]
        and not retro_fable_allowance_is_live(seat, lane_name, profile_name, at)
    ):
        return Refusal(
            "seat_not_eligible",
            (f"seat={seat}", f"lane={lane_name}"),
            (
                "ADR-0061 Decision 2: work leaves Claude only where a mechanical gate "
                "catches a wrong answer, and this seat's output is not gate-covered. "
                "Dispatch it on claude-native."
            ),
        )
    return None


class Readiness(NamedTuple):
    """What the readiness rung learned: an assessment of the issue, or why there is none."""

    assessment: readiness.Assessment | None
    unreadable: str = ""


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
        return Readiness(readiness.assess(body))
    body, why = readiness.fetch_body(issue)
    if why:
        return Readiness(None, why)
    return Readiness(readiness.assess(body))


def readiness_refusal(issue: int, found: Readiness) -> Refusal | None:
    """Refuse an issue that is not ready to be dispatched against (#241).

    Definition of ready, mechanically. `tools/readiness.py` carries the sub-checks, the
    definitions they were pre-registered with, and the corpus measurement that decided
    which of them refuse: two that refused none of the last twenty dispatched issues do,
    and enumerability — 15% overall, 67% of ruling executions — does not, because a ruling
    execution's criteria *are* the ruling and enumerating them would mean paraphrasing it.

    **No failure class**, for `admission_refusal`'s and `off_peak_refusal`'s reason exactly:
    CLAUDE.md's table types what a run *found*, and this found nothing about any code. The
    provider is up, the lane is reachable, and the issue is not ready to be worked. An
    unreadable body is different and does carry one — `infra_unavailable` — because a check
    that could not run is not a check that passed (#41), and a dispatched agent whose first
    act is `gh issue view` would meet the same outage three seconds later somewhere nobody
    is looking.

    **Lane-blind.** Nothing about the lane, the profile or the seat reaches this function,
    so a foreign lane meets exactly the refusal `claude-native` meets.
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


def admission_refusal(
    lane_name: str, profile_name: str, seat: str, admission_dir: Path
) -> Refusal | None:
    """Read the profile's admission standing before anything is planned (#224, ADR-0061 D6).

    Only the ruling's far end refuses here. A profile on probation is dispatchable, because
    the ten-issue record the bar judges accrues only as the lane runs; a profile whose
    second attempt failed is not, because the ruling allows exactly one re-run and the
    whole point of pre-registering an operating characteristic is that unlimited retries
    silently multiply it.

    No failure class. A refusal here says nothing about a provider or about the code under
    test — it is this project declining to spend a seat on a profile it has twice judged —
    so borrowing `infra_unavailable` or `provider_refused` would put a wrong class in
    CLAUDE.md's table, which that table makes a harness bug by definition.
    """
    found = admission.dispatch_refusal(
        admission.Store(directory=admission_dir), lane_name, profile_name, seat
    )
    if found is None:
        return None
    return Refusal(
        "admission_escalated",
        found,
        (
            "The pre-registered admission bar (#224, human ruling 2026-08-05T20:00Z) allows "
            f"{admission.MAX_ATTEMPTS} attempts and this profile has spent both on this "
            "seat. Nothing was dispatched. Escalate to the human; `just admission reset "
            f"--lane {lane_name} --profile {profile_name} --seat {seat} --force` is theirs "
            "to run, not yours. Re-dispatch on claude-native meanwhile."
        ),
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

    **No failure class**, and the reasoning is `admission_refusal`'s exactly. CLAUDE.md's
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


def assert_worktree(assigned: Path, observed: str) -> Refusal | None:
    """Refuse unless the assigned path is its own git top level (#105's fourth instance).

    `observed` is what `git rev-parse --show-toplevel` printed inside `assigned`, or the
    empty string when git refused. Both halves are failures worth naming: a path that is
    not a worktree root at all, and a path that resolves into somebody else's tree.
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


def default_brief(identity: Identity, worktree: Path) -> str:
    """Compose the brief a dispatch sends when the caller named no file.

    Deliberately thin: it states the assignment and points at the issue, because a
    default that invented instructions would be a second, untracked copy of the seat's
    contract.
    """
    return (
        f"You are the {identity.seat} seat, dispatched as {identity.dispatch_id} on the "
        f"{identity.lane} lane under profile {identity.profile}.\n\n"
        f"Worktree: {worktree}\n"
        f"Base SHA: {identity.base_sha}\n"
        f"Issue: #{identity.issue}\n\n"
        f"Read CLAUDE.md, then `gh issue view {identity.issue}`, and do that issue's "
        f"work in the worktree above and nowhere else. The issue's acceptance criteria "
        f"are the contract. Run `just fast` after every edit.\n"
    )


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
    question. The consequence — a hand-finished landing and no admission assessment for any
    Codex route — is stated once in `docs/multi-provider-dispatch.md` and §10 of
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
    test seams for *where the state lives*, the same seams `CTI_BREAKER_DIR` and
    `CTI_ADMISSION_DIR` already are, and neither can turn a recorded freeze into a dispatch.

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
    freeze is the one refusal here whose remedy nobody but the human can start. Then
    admission, which reopens only when a human decides it should; then the breaker,
    which reopens on a published window boundary or on evidence; then the off-peak rule,
    which reopens on a clock within four hours with nothing for anyone to do meanwhile.
    Told about the clock first, a dispatcher would come back when the band lifted to meet
    a trip it was never told about.

    Readiness is also the one rung that costs a network call, and it is deliberately not
    demoted for it: the whole point of hearing it first is that its remedy can start now,
    while every rung below it either fixes itself or waits on the same human anyway.
    """
    refusal = resolve_selection(args.lane, args.profile, args.seat, now)
    if refusal is not None:
        return refusal
    refusal = readiness_refusal(args.issue, found)
    if refusal is not None:
        return refusal
    refusal = queue_refusal(args, root)
    if refusal is not None:
        return refusal
    refusal = admission_refusal(
        args.lane, args.profile, args.seat, Path(args.admission_dir).expanduser()
    )
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
        breaker_dir=breaker_dir,
        advisories=readiness_advisories(args.issue, found),
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
        breaker_dir=Path(str(document.get("breaker_dir", breaker.DEFAULT_BREAKER_DIR))),
        advisories=tuple(str(line) for line in document.get("readiness_advisories", ())),
    )


def write_result(record: Path, **fields: object) -> None:
    """Write the run's own outcome beside its plan — facts only, never a verdict.

    A returncode is not a failure class. What a dispatched run's exit code means about
    the code under test is the gates' business, and inventing a class here would be a
    second, untested opinion about it.
    """
    (record / "result.json").write_text(json.dumps(fields, indent=2) + "\n", encoding="utf-8")


def run_dispatch(record: Path, parent: Mapping[str, str]) -> tuple[int, tuple[str, ...]]:
    """Run the detached child: assert the worktree, assemble the environment, start the runner."""
    plan = load_record(record)
    profile = PROFILES[plan.identity.profile]
    lane = LANES[plan.identity.lane]

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
    brief = (record / "brief.md").read_text(encoding="utf-8")
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


def registry_lines(now: datetime | None = None) -> tuple[str, ...]:
    """Render every lane and profile: the answer to "what can I dispatch?"."""
    at = now or datetime.now(tz=UTC)
    lines: list[str] = []
    for lane in sorted(LANES.values()):
        lines.append(f"lane={lane.name} runner={lane.runner} foreign={str(lane.foreign).lower()}")
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
    eligible = " ".join(sorted(seat for seat, ok in SEATS.items() if ok))
    barred = " ".join(sorted(seat for seat, ok in SEATS.items() if not ok))
    lines.append(f"seats_eligible_on_foreign_lanes={eligible}")
    lines.append(f"seats_claude_native_only={barred}")
    # A suspended rule is visible while it holds and disappears when the clock reapplies
    # the standing bar. This is the one ruled exception, not a general allowance list.
    if at < RETRO_FABLE_ALLOWANCE_EXPIRES_AT:
        seat, lane_name, profile_name = RETRO_FABLE_ALLOWANCE
        remaining = (RETRO_FABLE_ALLOWANCE_EXPIRES_AT - at).total_seconds()
        lines.append(
            "seat_allowance=live"
            f" seat={seat}"
            f" lane={lane_name}"
            f" profile={profile_name}"
            f" expires_at={RETRO_FABLE_ALLOWANCE_EXPIRES_AT.isoformat()}"
            f" in={breaker.human_delta(remaining)}"
            f" source={RETRO_FABLE_ALLOWANCE_SOURCE}"
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
    child = redacted(assemble_environment(parent, profile, plan.identity, token), token)
    lines = [
        f"dispatch={plan.identity.dispatch_id}",
        f"lane={plan.identity.lane}",
        f"profile={plan.identity.profile}",
        f"seat={plan.identity.seat}",
        f"issue={plan.identity.issue}",
        f"worktree={plan.worktree}",
        f"base_sha={plan.identity.base_sha}",
        f"argv={' '.join(plan.argv)}",
        f"brief_bytes={len(brief.encode('utf-8'))}",
        *plan.advisories,
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
    parser.add_argument("--permission-mode", default="acceptEdits")
    parser.add_argument("--dispatch-dir", default=str(DISPATCH_ROOT))
    parser.add_argument("--credentials", default=str(CREDENTIALS))
    # `CTI_BREAKER_DIR` exists so that a test can run the real seam — `tools/dispatch.sh`
    # forks a fresh process, which no in-process patch reaches — against its own breaker
    # rather than against whatever this box's lanes happen to be doing today.
    parser.add_argument(
        "--breaker-dir",
        default=os.environ.get("CTI_BREAKER_DIR", str(breaker.DEFAULT_BREAKER_DIR)),
    )
    # `CTI_ADMISSION_DIR` is `CTI_BREAKER_DIR`'s twin and exists for the same reason: the
    # real seam forks a fresh process, which no in-process patch reaches, so a test needs
    # the recipe pointed at its own admission records rather than at this box's.
    parser.add_argument(
        "--admission-dir",
        default=os.environ.get("CTI_ADMISSION_DIR", str(admission.DEFAULT_ADMISSION_DIR)),
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
    """Name which of the four required options the caller left out."""
    required = (("--lane", args.lane), ("--profile", args.profile), ("--seat", args.seat))
    absent = [name for name, value in required if not value]
    if args.issue <= 0:
        absent.append("--issue")
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

    Three requests are questions rather than dispatches — the registry, a readiness audit,
    and the detached child asking to run a record the seam already wrote — and each is
    answered here so that `main` stays one path: plan, refuse, or launch.
    """
    if args.list:
        return emit(registry_lines(), 0)
    if args.readiness:
        return readiness_audit(args)
    if args.run:
        code, lines = run_dispatch(Path(args.run), os.environ)
        return emit(lines, code)
    return None


def main(argv: list[str] | None = None) -> int:
    """Plan a dispatch, or run one the seam already planned."""
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
                "A dispatch names its lane, profile, seat and issue. Nothing was dispatched.",
            ).lines(),
            EXIT_REFUSED,
        )

    plan, brief, refusal = plan_dispatch(args, main_checkout(Path.cwd()), datetime.now(tz=UTC))
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
            *plan.advisories,
        ),
        0,
    )


if __name__ == "__main__":
    sys.exit(main())
