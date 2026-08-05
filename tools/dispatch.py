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

**The lane's breaker is read before anything is planned** (#226). That is the one place
ADR-0061's other two classes reach this file: a lane out of quota refuses with
`quota_exhausted` and the published reset time, and a lane whose quality trip has fired
refuses with `provider_refused` and escalates. Neither is invented here — both come from
`tools/breaker.py`'s verdict, which is a state file this module reads and never writes
by itself. What it does write is the other direction: when a dispatched run ends, its
own log is classified and fed back to the breaker, which is how a 429 trips a lane on a
provider that publishes no quota state.
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

# The path insert above is what makes this importable.
import breaker

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
            "~/.arma-cti/credentials.env, which is #229's human item."
        ),
    ),
}

PROFILES: Final[dict[str, Profile]] = {
    "opus-xhigh": Profile("opus-xhigh", "claude-native", "opus", "xhigh"),
    "opus-high": Profile("opus-high", "claude-native", "opus", "high"),
    "sonnet-high": Profile("sonnet-high", "claude-native", "sonnet", "high"),
    "haiku-medium": Profile("haiku-medium", "claude-native", "haiku", "medium"),
    # The opus slot on this lane resolves to glm-5.2 through the lane's model slots, and
    # `max` is where ADR-0061 records GLM's top thinking level landing. Both facts are
    # the registry's business alone.
    "zai-glm52-max": Profile("zai-glm52-max", "zai", "opus", "max"),
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
            "resource_attributes": dict(self.identity.attributes()),
            "planned_at": datetime.now(tz=UTC).isoformat(),
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


def resolve_selection(lane_name: str, profile_name: str, seat: str) -> Refusal | None:
    """Check lane, profile and seat against the registry and against Decision 2."""
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
    if LANES[lane_name].foreign and not SEATS[seat]:
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


def build_argv(lane: Lane, profile: Profile, permission_mode: str) -> tuple[str, ...]:
    """Build the runner's argv, which carries no secret, because a secret on argv is in `ps`.

    The brief goes in on stdin for the same reason it is not a positional prompt: argv
    is world-readable on this box, and a brief quoting an issue is not something to
    publish to every process table reader either.
    """
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


def plan_dispatch(
    args: argparse.Namespace,
    root: Path,
    now: datetime,
) -> tuple[Plan | None, str, Refusal | None]:
    """Validate the request and mint the plan and the brief, writing nothing."""
    refusal = resolve_selection(args.lane, args.profile, args.seat)
    if refusal is not None:
        return None, "", refusal

    breaker_dir = Path(args.breaker_dir).expanduser()
    refusal = breaker_refusal(args.lane, breaker_dir, now.timestamp())
    if refusal is not None:
        return None, "", refusal

    profile = PROFILES[args.profile]
    lane = LANES[profile.lane]

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
        argv=build_argv(lane, profile, args.permission_mode),
        credentials=credentials,
        permission_mode=args.permission_mode,
        breaker_dir=breaker_dir,
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


def registry_lines() -> tuple[str, ...]:
    """Render every lane and profile: the answer to "what can I dispatch?"."""
    lines: list[str] = []
    for lane in sorted(LANES.values()):
        lines.append(f"lane={lane.name} runner={lane.runner} foreign={str(lane.foreign).lower()}")
        if lane.base_url:
            lines.append(f"  base_url={lane.base_url}")
        if lane.credential:
            lines.append(f"  credential={lane.credential}")
        lines.extend(
            f"  profile={profile.name} model={profile.model} effort={profile.effort}"
            for profile in sorted(PROFILES.values())
            if profile.lane == lane.name
        )
    eligible = " ".join(sorted(seat for seat, ok in SEATS.items() if ok))
    barred = " ".join(sorted(seat for seat, ok in SEATS.items() if not ok))
    lines.append(f"seats_eligible_on_foreign_lanes={eligible}")
    lines.append(f"seats_claude_native_only={barred}")
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
    parser.add_argument("--breaker-dir", default=str(breaker.DEFAULT_BREAKER_DIR))
    parser.add_argument("--list", action="store_true", help="print the registry and exit")
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


def emit(lines: Iterable[str], code: int) -> int:
    """Print to the stream the exit code implies, and return it."""
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def main(argv: list[str] | None = None) -> int:
    """Plan a dispatch, or run one the seam already planned."""
    args = parse_args(argv)
    if args.list:
        return emit(registry_lines(), 0)
    if args.run:
        code, lines = run_dispatch(Path(args.run), os.environ)
        return emit(lines, code)

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
        ),
        0,
    )


if __name__ == "__main__":
    sys.exit(main())
