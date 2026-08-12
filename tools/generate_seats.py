"""`just generate`: the Claude seat surfaces, written from the dispatch registry (#324).

A seat's `(model, effort)` pair used to be typed out wherever a surface wanted it — the
agent definition, the skill frontmatter, and the prose describing the mapping — which is
how the interlocutor's pair came to exist in five places, and how `cti-implementer`'s came
to disagree with ADR-0071 ruling 2's table without anything noticing. `tools/dispatch.py`'s
registry already holds the pair once, as a profile behind each seat's ordered preference
list (#320, #321), so the surfaces are written *from* it rather than beside it.

ADR-0071 ruling 7 is the rule this implements, and the ruling names its pattern:
**translate, never reimplement**. Nothing here decides a pair. The registry decides which
profiles a seat prefers; this module takes the first of them that means anything on this
surface and renders it.

**Which profile a Claude seat file declares is the first `claude-native` one in the seat's
preference list**, and the lane filter is the whole of the judgement. A `.claude/agents/`
definition cannot pin a lane: it declares a Claude-vocabulary model, and which provider
that reaches is a property of the session that spawns the subagent, not of the file. So the
foreign heads of a preference list have no expression here — `codex-luna-max` is not a
model the Claude harness can be handed — and neither does `zai-glm52-max`, whose Claude
vocabulary (`opus`, `max`) would be read by a native session as a native pair the registry
never chose. The native entry is the one that is true wherever the file is read.

`--check` compares every surface against what the registry would write, so a hand edit, or
a registry change with no regeneration, is a `schema_stale` failure in `just check` rather
than a silently cheaper seat. That matters more here than for a schema export: **both
declaration surfaces fail open** (ADR-0068). A misspelled key or a drifted value does not
refuse — the seat answers, the work lands, and the only trace is a tier nobody ratified.
`just check-seats` asserts that a pair is *declared and valid*; this asserts that it is the
*registry's*, which is the half that was missing.

**What a surface declares is generated; what a human narrates is checked.** A skill states
its seat's tier in sentences too, and those go stale the same way — but rewriting them would
make this tool the author of prose it did not write, so a disagreeing sentence is a
`pair_drift` finding for a human to fix rather than an edit `just generate` performs behind
one (#324, review round 2).

**One harness has no surface to generate into.** That is recorded as a gap with its failure
mode named, in `UNGENERATED_HARNESSES` below and in `docs/multi-provider-dispatch.md`,
rather than papered over with instructions in a file that fails open the same way.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `dispatch.py` itself uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes this importable.
import dispatch

# The one lane whose `(model, effort)` a Claude seat file can declare. See the module
# docstring: the file names a Claude-vocabulary model, so a foreign profile has no
# expression here and a Claude-vocabulary foreign profile has a misleading one.
NATIVE_LANE: Final = "claude-native"

FENCE: Final = "---"

# The pair's other notations, all of them prose. `just check` stayed green while the
# interlocutor's pair lived in three places, because only its frontmatter was derived (#324,
# review round 1) — so a restatement in prose is a declaration surface too, and drift in it
# has to be *caught*.
#
# Caught, not rewritten (#324, review round 2, claim 2). A generator that owned every
# matching string in a human-authored skill would silently rewrite sentences it did not
# write: "compare recon at haiku/medium with the interlocutor at opus/xhigh" becomes a
# sentence comparing one tier with itself, and the gate's own prescribed remedy — run
# `just generate` — is what does it. So the frontmatter, which is a declared field, stays
# generated, and prose that disagrees with the registry reds for a human to fix. The cost is
# stated where it falls: a skill in `SKILL_SURFACES` is *that seat's* declaration surface,
# so every pair narrated in it must be that seat's, and a sentence about another seat's tier
# is a red rather than a silent rewrite.
#
# `SESSION_COMMAND` is the operative notation: `/model opus` and `/effort xhigh` are the
# commands the human types to set a whole session to this seat's tier, so the argument is
# the pair in a second vocabulary. The backticks are part of the match because that is how a
# skill writes a command meant to be typed, and they keep the pattern off ordinary prose.
SESSION_COMMAND: Final = re.compile(r"`/(model|effort) ([^`\s]+)`")

COMMANDS: Final = ("model", "effort")


def _notations() -> tuple[re.Pattern[str], ...]:
    """Build the pair's prose notations out of the registry's own native vocabulary.

    Nothing here is a second copy of a pair: the models and the efforts come from the
    registry, and only the *shapes* a human writes them in are stated. Longest alternative
    first, so `xhigh` cannot be read as `high`.

    Four shapes, each one a human has actually written in this repository: `opus/xhigh`,
    `opus at xhigh effort` (which is what `describe` renders), `run at opus xhigh`, and
    `opus[1m], effort xhigh` (AGENTS.md's Model roles bullets). Every pattern captures the
    model and then the effort, so a caller reads a stated pair without knowing the shape.
    """
    native = [profile for profile in dispatch.PROFILES.values() if profile.lane == NATIVE_LANE]
    models = sorted({profile.model for profile in native}, key=len, reverse=True)
    efforts = sorted({profile.effort for profile in native}, key=len, reverse=True)
    model = "(?:{})".format("|".join(re.escape(name) for name in models))
    effort = "(?:{})".format("|".join(re.escape(level) for level in efforts))
    return (
        re.compile(rf"\b({model})/({effort})\b"),
        re.compile(rf"\b({model}) at ({effort}) effort\b"),
        re.compile(rf"\bat ({model}) ({effort})\b"),
        re.compile(rf"\b({model})(?:\[1m\])?, effort ({effort})\b"),
    )


PAIR_NOTATIONS: Final = _notations()

# The slash notation on its own, because it is the one shape that can only ever be a pair.
# The other three are prose, so a surface that narrates tiers by hand — AGENTS.md's Model
# roles section, which is #329's — states them legitimately, and a check over that surface
# scopes itself by region rather than by notation.
SLASH_PAIR: Final = PAIR_NOTATIONS[0]


def stated_pairs(text: str) -> list[tuple[str, str]]:
    """Every `(model, effort)` this text states, in any notation the vocabulary reads.

    Its limit, stated rather than implied: this reads notations, not meanings. A profile
    name (`opus-xhigh`), a paraphrase ("the top effort on opus") and a tier named across two
    sentences are all invisible to it, and no pattern makes them visible. What it buys is
    that the shapes a human actually types are enumerable, so a hand-written pair in one of
    them cannot sit beside a derived one unnoticed.
    """
    return [(match[1], match[2]) for pattern in PAIR_NOTATIONS for match in pattern.finditer(text)]


# Written into every generated agent file, where the next hand to open one meets it. Not a
# substitute for the check — an instruction in a file is exactly the fail-open remedy
# ADR-0071 ruling 7 rejects — but the check names a remedy and this names it at the site.
BANNER: Final = (
    "<!-- Generated by tools/generate_seats.py from tools/dispatch.py's registry.\n"
    "     Do not edit by hand: change the registry or the generator, then run"
    " `just generate`. -->"
)

# ADR-0071 ruling 7, as data rather than as prose that can rot away from the thing it
# describes. Codex is this map's intended primary implementation lane and has no
# seat-definition surface at all, so there is nothing for this module to translate into and
# generation is not a claim the project can make for both harnesses.
UNGENERATED_HARNESSES: Final[tuple[tuple[str, str], ...]] = (
    (
        "codex",
        (
            "No seat-definition surface exists, so a self-spawned subagent's model is "
            "unenforced there: it runs at whatever model that session was started with, and "
            "nothing refuses. Instructions in AGENTS.md were rejected as the remedy because "
            "they fail open silently — the same failure they would be there to prevent. This "
            "is the map's intended primary implementation lane, so the seat concept the map "
            "is built from is unenforceable on it. Accepted gap until such a surface exists; "
            "do not invent one."
        ),
    ),
)


class SeatSurfaceError(Exception):
    """A surface the registry cannot supply, or a file with nothing to rewrite."""


class AgentSurface(NamedTuple):
    """One wholly generated `.claude/agents/` seat file."""

    seat: str
    stem: str
    blurb: str
    body: str
    tools: tuple[str, ...] = ()


class SkillSurface(NamedTuple):
    """A partly authored file whose declared pair is rewritten and nothing else is.

    A skill is prose the human invokes, with frontmatter keys this module has no opinion
    about; generating the whole file would move a skill into Python to own a handful of its
    lines. So the declared pair — the top-level `model:` and `effort:` keys — is retuned in
    place, and the rest of the file is left exactly as authored.

    The same fact is also stated in the file's sentences and in the `/model` and `/effort`
    commands it tells the human to type. Those are **checked, not written**: three notations
    of one fact, one of them generated and the other two guarded (#324).
    """

    seat: str
    path: str


# The Claude seat surfaces, one per row of ADR-0071 ruling 2's table that this repository
# actually has a surface for. The list is deliberately explicit rather than derived from
# `SEATS`: `.claude/agents/` holds definitions for subagents an agent spawns on its own
# judgement, which ruling 2 exempts from the dispatch map, so which seats want a file here
# is a decision and not a consequence. `review`, `retro`, `fable` and `orchestrator` are
# dispatch routes with no subagent surface today and are absent for that reason; giving one
# a file is one entry below.
#
# `mechanical` is **retired** by ruling 2 and has no entry, so `--check` names its old file
# as a stray if it ever comes back. `cti-implementer-xhigh` is gone the other way: ruling 2
# folds its tier into the new `planner` seat, and a file named for a seat the registry does
# not carry is the drift this module exists to remove.
AGENT_SURFACES: Final[tuple[AgentSurface, ...]] = (
    AgentSurface(
        seat="planner",
        stem="cti-planner",
        blurb=(
            "Planning for arma-cti — works out what to do and hands back a plan; neither "
            "gates nor lands (ADR-0071 ruling 2). Absorbs the tier of the retired "
            "`cti-implementer-xhigh` seat, and not its contract."
        ),
        body=(
            "Planning seat for arma-cti. A planner reads the ground, settles the approach,"
            " and hands back a plan an implementer carries out. It does **not** run the"
            " gate and it does **not** land: absorbing `cti-implementer-xhigh` means"
            " inheriting that seat's tier, not its contract (ADR-0071 ruling 2).\n"
            "\n"
            "The dispatch briefing carries the task, the worktree protocol, and the gates;"
            " the repo's CLAUDE.md governs. Name what you could not settle and why, rather"
            " than settling it by assumption — an unresolved question in a plan is cheaper"
            " than a wrong answer an implementer builds on.\n"
            "\n"
            "Report to the orchestrator in compressed telegraphic prose — drop articles and"
            " filler, keep every SHA, verdict, path and number exact. Persisted artefacts"
            " (issues, commits, ADRs, docs, CHANGELOG) remain normal prose."
        ),
    ),
    AgentSurface(
        seat="implementer",
        stem="cti-implementer",
        blurb=(
            "Implementation and day-to-day review for arma-cti — carries out the work, "
            "runs the gate, and lands it."
        ),
        body=(
            "Implementation seat for arma-cti. The dispatch briefing carries the task, the"
            " worktree protocol, and the gates; the repo's CLAUDE.md governs. Deliver the"
            " work, run the gates, land per the briefing.\n"
            "\n"
            "Report to the orchestrator in compressed telegraphic prose — drop articles and"
            " filler, keep every SHA, verdict, path and number exact. Persisted artefacts"
            " (issues, commits, ADRs, docs, CHANGELOG) remain normal prose."
        ),
    ),
    AgentSurface(
        seat="recon",
        stem="cti-recon",
        blurb=(
            "Read-only reconnaissance for arma-cti — search, triage sweeps, state checks. "
            "Never edits, commits, or changes state."
        ),
        tools=("Read", "Grep", "Glob", "Bash"),
        body=(
            "Read-only seat for arma-cti: gather and report, never modify. No edits, no"
            " commits, no label flips, no state changes; Bash is for inspection commands"
            " (git, gh, rg, ls) only.\n"
            "\n"
            "**Cite any claim that could decide a routing choice** — the file and line, the"
            " issue and comment, the command and its output — so the orchestrator can check"
            " the citation rather than trust the summary. ADR-0071 ruling 2 adopts this"
            " because nothing else in the design ever checks this seat: no gate reads its"
            " output, it lands nothing, and a wrong answer here propagates into decisions"
            " rather than into a diff.\n"
            "\n"
            "Report to the orchestrator in compressed telegraphic prose — drop articles and"
            " filler, keep every SHA, verdict, path and number exact. Persisted artefacts"
            " you are asked to draft (issue text, comments) remain normal prose."
        ),
    ),
    AgentSurface(
        seat="interlocutor",
        stem="cti-interlocutor",
        blurb=(
            "The human interface seat for arma-cti — rulings intake, status of the "
            "orchestration loop, observations on existing work, raising issues. Talks to "
            "the human; does not implement."
        ),
        body=(
            "The human interface seat for arma-cti. The human is talking to you, and the"
            " conversation is the work: taking their observations about existing work,"
            " answering what the orchestration loop is doing, raising issues on their"
            " behalf, and recording the decisions they give.\n"
            "\n"
            "Answer from tool results, never from memory of the repository:"
            " `just watch-report` for the lane breakers and watcher findings,"
            " `just queue state` for the freeze, WIP limit and reservations,"
            " `gh issue list` and `just handoff <issue>` for where a piece of work stands,"
            " `just verdict` for a finished pool. Quote a rendered verdict verbatim; never"
            " retype a SHA or an evidence path.\n"
            "\n"
            "You do not implement. Work the human asks for is dispatched —"
            " `just brief <issue>`, then `just dispatch` — and you tell them what you"
            " dispatched and where its evidence will land.\n"
            "\n"
            "A decision the human gives you is recorded, not executed past its gate. The"
            " human sign-off gates in CLAUDE.md still bind, and a gated change lands only"
            " with their approval in session or an ADR-0013 record; mechanical permission"
            " discharges nothing.\n"
            "\n"
            "Report in normal prose — this seat's whole output is for the human, so the"
            " telegraphic register the other seats use does not apply. Persisted artefacts"
            " (issues, commits, ADRs, docs, CHANGELOG) are normal prose too."
        ),
    ),
)

# ADR-0068's second declaration surface: the interlocutor is reached as `/interlocutor`, a
# slash command whose own frontmatter carries the pair. Both surfaces now read the one row.
SKILL_SURFACES: Final[tuple[SkillSurface, ...]] = (
    SkillSurface(seat="interlocutor", path=".claude/skills/interlocutor/SKILL.md"),
)


def seat(name: str) -> dispatch.Seat:
    """Look up the registry's entry for this seat, dispatchable or declared-only."""
    found = dispatch.SEATS.get(name) or dispatch.DECLARED_ONLY_SEATS.get(name)
    if found is None:
        message = f"`{name}` is in no registry: neither SEATS nor DECLARED_ONLY_SEATS"
        raise SeatSurfaceError(message)
    return found


def native_profile(name: str) -> dispatch.Profile:
    """Resolve the first profile in this seat's list a Claude seat file can declare."""
    for entry in seat(name).preference:
        profile = dispatch.PROFILES[entry]
        if profile.lane == NATIVE_LANE:
            return profile
    message = (
        f"seat `{name}` prefers {list(seat(name).preference)}, none of them on"
        f" `{NATIVE_LANE}` — a Claude seat file has no pair to declare. Register a native"
        " profile in the seat's preference list, or drop the seat's surface."
    )
    raise SeatSurfaceError(message)


def describe(surface: AgentSurface, profile: dispatch.Profile) -> str:
    """Append the seat's tier to its blurb — derived, so it cannot disagree."""
    return (
        f"{surface.blurb} {profile.model} at {profile.effort} effort, resolved from the"
        f" `{surface.seat}` seat's preference list in tools/dispatch.py (ADR-0071 ruling 2)."
    )


def render(surface: AgentSurface) -> str:
    """Render the whole seat file the registry would write."""
    profile = native_profile(surface.seat)
    front = [
        FENCE,
        f"name: {surface.stem}",
        f"description: {describe(surface, profile)}",
        f"model: {profile.model}",
        f"effort: {profile.effort}",
    ]
    if surface.tools:
        front.append(f"tools: {', '.join(surface.tools)}")
    front.append(FENCE)
    return "\n".join([*front, "", BANNER, "", surface.body, ""])


def retune(where: str, text: str, profile: dispatch.Profile) -> str:
    """Rewrite every pair a partly authored surface declares, leaving everything else alone.

    Deliberately not a YAML round-trip: the file is authored prose with authored
    frontmatter, and a reformat would be this tool editing lines it has no opinion about.
    Only the values move, and in the frontmatter only where they are already top-level
    scalars — which is the same reading `tools/check_seat_config.py` does, for the same
    reason.

    Only the frontmatter moves. The pair is *also* stated in the file's prose — narrated in
    sentences, and typed as `/model` and `/effort` commands — and those are checked rather
    than rewritten (`prose_findings`), because a generator that edits sentences it did not
    author is how the gate's own remedy comes to change what a human meant (#324, review
    round 2, claim 2).
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != FENCE:
        message = f"{where}: no `---` frontmatter block to rewrite"
        raise SeatSurfaceError(message)
    try:
        end = lines.index(FENCE, 1)
    except ValueError:
        message = f"{where}: frontmatter block is never closed"
        raise SeatSurfaceError(message) from None
    wanted = {"model": profile.model, "effort": profile.effort}
    rewritten: set[str] = set()
    for index in range(1, end):
        line = lines[index]
        if not line or line[0].isspace() or ":" not in line:
            continue
        key = line.partition(":")[0].strip()
        if key in wanted:
            lines[index] = f"{key}: {wanted[key]}"
            rewritten.add(key)
    missing = sorted(set(wanted) - rewritten)
    if missing:
        message = (
            f"{where}: no top-level {', '.join(f'`{key}:`' for key in missing)} to rewrite."
            " A seat's skill declares both halves of the pair or neither"
            " (tools/check_seat_config.py); this one declares part of it."
        )
        raise SeatSurfaceError(message)
    return "\n".join(lines)


def prose_findings(where: str, text: str, profile: dispatch.Profile) -> list[str]:
    """Every pair this file states in prose that is not the one the registry chose.

    A finding, never an edit. The narrated pair and the `/model` and `/effort` commands are
    the same fact in other vocabularies, so they go stale the way the frontmatter does — but
    they live in sentences a human wrote, and the remedy for a stale sentence is a human
    rewriting it. What this buys is that the staleness cannot be silent; what it costs is
    that a sentence about *another* seat's tier reds here, because a notation check cannot
    tell whose tier a narrated pair is.

    The half-named commands case is a finding for the same reason it used to be a refusal: a
    human who sets the model and not the effort gets a session running the other half at
    whatever tier it already had, silently, which is ADR-0068's fail-open failure reached by
    advice instead of by frontmatter. A skill naming neither command is fine — the commands
    are how a skill talks about a whole session, and not every skill needs to.

    Not classed `schema_stale`: that class prescribes regenerating, and regenerating is
    exactly what must not happen to these lines. The class tells its reader what to do.
    """
    wanted = {"model": profile.model, "effort": profile.effort}
    found = [
        f"pair_drift: {where} states `{model}/{effort}` where the registry chose"
        f" `{profile.model}/{profile.effort}`. Fix the sentence by hand — `just generate`"
        " writes the frontmatter and deliberately leaves authored prose alone."
        for model, effort in stated_pairs(text)
        if (model, effort) != (profile.model, profile.effort)
    ]
    commands = SESSION_COMMAND.findall(text)
    named = {command for command, _ in commands}
    if named and named != set(COMMANDS):
        absent = sorted(set(COMMANDS) - named)
        found.append(
            f"pair_drift: {where} runs {', '.join(f'`/{key}`' for key in sorted(named))}"
            f" without {', '.join(f'`/{key}`' for key in absent)}. A session set to half a"
            " seat's tier runs the other half at whatever it already had, silently"
            " (ADR-0068), so a skill names both commands or neither."
        )
    found.extend(
        f"pair_drift: {where} tells the human to type `/{command} {argument}` where the"
        f" registry chose `{wanted[command]}`. Fix the command by hand."
        for command, argument in commands
        if argument != wanted[command]
    )
    return found


def prose_drift(root: Path) -> list[str]:
    """Report the prose findings across every skill surface this root carries."""
    found: list[str] = []
    for surface in SKILL_SURFACES:
        path = root / surface.path
        if path.exists():
            text = path.read_text(encoding="utf-8")
            found.extend(prose_findings(surface.path, text, native_profile(surface.seat)))
    return found


def plan(root: Path) -> list[tuple[Path, str]]:
    """Every seat surface and the exact text the registry would put in it."""
    planned = [
        (root / ".claude" / "agents" / f"{surface.stem}.md", render(surface))
        for surface in AGENT_SURFACES
    ]
    for surface in SKILL_SURFACES:
        path = root / surface.path
        if not path.exists():
            message = f"{surface.path}: the skill this seat declares its pair in is absent"
            raise SeatSurfaceError(message)
        text = path.read_text(encoding="utf-8")
        planned.append((path, retune(surface.path, text, native_profile(surface.seat))))
    return planned


def strays(root: Path) -> list[str]:
    """Agent seat files the registry does not carry — a retirement that grew back.

    `.claude/agents/` is wholly this module's, so a file for a seat the registry dropped is
    a stale surface and not a contribution: it still declares a pair, it is still enumerated
    at session start, and nothing about it is checked. `tools/check_seat_config.py` states
    the scope this rests on — a personal seat lives under `~/.claude/agents/` and no gate of
    this project's reaches it.
    """
    wanted = {f"{surface.stem}.md" for surface in AGENT_SURFACES}
    directory = root / ".claude" / "agents"
    return sorted(path.name for path in directory.glob("*.md") if path.name not in wanted)


def stale(root: Path, planned: list[tuple[Path, str]]) -> list[str]:
    """Every way a surface on disk is not the surface the registry describes.

    Each finding carries its own remedy, because they do not share one: a generated file is
    regenerated, and a sentence a human wrote is rewritten by a human.
    """
    found = [
        f"schema_stale: {path.relative_to(root).as_posix()} is not what the seat registry"
        " would write. Run `just generate`."
        for path, text in planned
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]
    found.extend(
        f"schema_stale: .claude/agents/{name} is a seat the registry does not carry."
        " Run `just generate`."
        for name in strays(root)
    )
    found.extend(prose_drift(root))
    return found


def gap_report() -> list[str]:
    """Report the harnesses with no surface to generate into, and what that costs."""
    return [
        f"ungenerated: {harness}: {consequence}" for harness, consequence in UNGENERATED_HARNESSES
    ]


def main(argv: list[str] | None = None) -> int:
    """Write the seat surfaces, or check the ones on disk are the registry's."""
    parser = argparse.ArgumentParser(description="Write the Claude seat surfaces.")
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        planned = plan(args.root)
    except SeatSurfaceError as refusal:
        print(f"seat_surface: {refusal}", file=sys.stderr)  # noqa: T201 — the gate's channel
        return 1

    if args.check:
        found = stale(args.root, planned)
        for line in found:
            print(line, file=sys.stderr)  # noqa: T201 — ditto
        return 1 if found else 0

    for path, text in planned:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    # Writing converges the directory rather than adding to it, on two merits of its own.
    # First, it is what makes `--check` a check and not a to-do list: every failure that
    # branch can name is one this branch would fix, so the two halves agree on what a
    # correct directory is. Second, a retired seat's file is not inert — it still declares
    # a pair and the harness still enumerates it at session start — so leaving it behind
    # leaves a dispatchable seat the registry has dropped. The removal is named in the
    # output, so it is visible in the runner's terminal as well as in the diff.
    for name in strays(args.root):
        (args.root / ".claude" / "agents" / name).unlink()
        retired = f"retired: .claude/agents/{name} — the registry no longer carries this seat"
        print(retired)  # noqa: T201 — the removal is named rather than silent
    for line in gap_report():
        print(line)  # noqa: T201 — what `just generate` tells its runner
    # The half this command cannot write. A drifted sentence is a human's to fix, so writing
    # ends non-zero rather than reporting the finding into a scroll-back nobody reads: the
    # runner came here because `--check` sent them, and leaving with an unfixed finding and
    # an exit code of 0 would read as done.
    drifted = prose_drift(args.root)
    for line in drifted:
        print(line, file=sys.stderr)  # noqa: T201 — the gate's channel
    return 1 if drifted else 0


if __name__ == "__main__":
    sys.exit(main())
