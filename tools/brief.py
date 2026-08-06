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

The **invariant half**: seat, worktree protocol, gate line, flake lines, landing protocol,
paste rule. The **variable half** — the task statement, the scope boundary, the ground
truth to read, and the reason for a non-default seat — is the orchestrator's, is the
actual work of the turn, and is emitted here as a visible placeholder so that an unedited
brief is obviously unfinished rather than plausibly complete.

## Inlined or cited, and why each line is where it is

#208 measured that a pointer does not displace archaeology: an agent handed a reference
goes and reads the thing, and pays for the read. So the split is by *kind*, not by length.

- **Inlined** — the imperative, in the words that make it obeyable without a read: the two
  worktree calls, the gate command, the commit trailer, `just land` and its paste
  instruction, the flake test names, the `flake_quarantine` required response, and the one
  sentence of the verdict paste rule. An agent must be able to comply having read only the
  brief.
- **Cited** — the evidence and the reasoning behind each imperative: CLAUDE.md's Contract
  and failure-class table, #219's A/B, #105, the ADRs. That read is optional, and it is
  only wanted by an agent that means to argue with the rule rather than follow it.

Nothing from CLAUDE.md is copied wholesale. A second copy of a governing document is a
second home for a rule, and two homes can disagree.

## The gate line is derived, not chosen

CLAUDE.md's `just regress` row owes the full corpus to any change reaching an in-world
surface, and a briefing that names `just fast` for an in-world change is the defect this
table exists to prevent. The in-world list is **not restated here**: it is
`tools/admission.py`'s `IN_WORLD_PREFIXES`, which the landing-time cross-check already
uses, so the composition-time prediction and the landing-time audit cannot disagree about
what "in-world" means.

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
implementation discovers more. This is a prediction; `just admission audit`'s cross-check
against the landed commit is the ground truth, and it runs later on the same list.

## The flake lines are read, never remembered

An open flake is an issue whose **title** names a `test_` identifier and says it flakes, or
whose body opens a line with ``Class: `flake_quarantine` ``. Both of the two live ones
match on title. The read asks GitHub for open issues only, so a closed flake leaves the
next briefing by itself — which is the whole reason the list is fetched rather than typed.

A flake whose title says neither is missed, and the remedy is a title edit rather than a
looser rule: "mentions `flake_quarantine` anywhere" also matches every issue that merely
cites the class table, which on the live tracker is two issues out of four.

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
import admission
import dispatch
import readiness

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

# ------------------------------------------------------------------ the gate derivation

GATE_REGRESS: Final = "regress"
GATE_FAST: Final = "fast"
GATE_UNDETERMINED: Final = "undetermined"

# A path token: at least one separator with a non-empty segment either side. The shape is
# what distinguishes a surface (`addons/main/functions/fn_effectApply.sqf`) from the rule
# being quoted (`addons/`), and that distinction is the whole first signal.
PATH_TOKEN: Final = re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+")

# How CONTEXT.md spells a term it is defining: a bold label opening a line, colon-closed.
CONTEXT_TERM: Final = re.compile(r"^\*\*([A-Z][A-Za-z ]*)\*\*:", re.MULTILINE)

# Two words that name the world without being domain nouns, so CONTEXT.md has no entry for
# them and never will. Everything else in the vocabulary is read from that document.
ENGINE_WORDS: Final = ("SQF", "in-world")


class Gate(NamedTuple):
    """Which gate a briefing must name, and the derivation that reached it."""

    kind: str
    line: str
    because: tuple[str, ...]

    @property
    def reads_a_verdict(self) -> bool:
        """Whether this gate produces a verdict, which is what the paste rule attaches to."""
        return self.kind == GATE_REGRESS


def domain_vocabulary(context: str) -> tuple[str, ...]:
    """Return CONTEXT.md's Language terms plus the two engine words, longest first.

    Longest first so that `Command Port` is matched before `Command` and the alternation
    cannot report the shorter term for a mention of the longer one.
    """
    terms = set(CONTEXT_TERM.findall(context)) | set(ENGINE_WORDS)
    return tuple(sorted(terms, key=lambda term: (-len(term), term)))


def read_vocabulary(repo: Path = REPO) -> tuple[str, ...]:
    """Read the domain vocabulary out of the checkout, or return empty if it cannot be read.

    An unreadable CONTEXT.md leaves the vocabulary signal silent, and a silent signal must
    not become a `just fast`: `derive_gate` takes the empty tuple as a reason to refuse to
    decide, on #41's shape — a check that could not run is not a check that passed.
    """
    document = repo / "CONTEXT.md"
    try:
        return domain_vocabulary(document.read_text(encoding="utf-8"))
    except OSError:
        return ()


def named_paths(body: str) -> tuple[str, ...]:
    """Every path token the body names, deduplicated and sorted."""
    return tuple(sorted(set(PATH_TOKEN.findall(body))))


def in_world(paths: Sequence[str]) -> tuple[str, ...]:
    """Name the in-world surfaces among these paths, using admission's list and no other."""
    return tuple(path for path in paths if path.startswith(admission.IN_WORLD_PREFIXES))


def domain_mentions(body: str, vocabulary: Sequence[str]) -> tuple[str, ...]:
    """Name the domain terms the body uses, case-sensitively and on word boundaries.

    Case matters: CONTEXT.md asks for its vocabulary capitalised, and a lower-case "base"
    or "order" is ordinary English rather than a claim about the world.
    """
    if not vocabulary:
        return ()
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(term) for term in vocabulary) + r")\b")
    return tuple(sorted({found.group(0) for found in pattern.finditer(body)}))


REGRESS_LINE: Final = "`just regress` — the full corpus, no filter, no `--issues`."
FAST_LINE: Final = "`just fast`"
UNDETERMINED_LINE: Final = "**GATE UNDETERMINED — the orchestrator names it.**"

WHY_REGRESS: Final = (
    "CLAUDE.md's `just regress` row owes the full corpus to any change reaching an in-world"
    " surface."
)
WHY_NO_VOCABULARY: Final = (
    "CONTEXT.md could not be read, so the domain-vocabulary signal did not run, and a signal"
    " that did not run is not a signal that cleared."
)
WHY_NO_PATHS: Final = (
    "The body names no path at all, so its surface cannot be read off it. Undetermined never"
    " resolves to the cheaper gate."
)
WHY_DOMAIN_LANGUAGE: Final = (
    "No path reaches an in-world surface, but the body speaks the domain language, and four"
    " of fourteen measured in-world issues named only evidence paths. Undetermined never"
    " resolves to the cheaper gate."
)
WHY_FAST: Final = (
    "No named path reaches `addons/`, `missions/`, `extension/` or the daemon's world-facing"
    " half, and the body uses no CONTEXT.md domain term. The corpus is not owed; state that"
    " reasoning in the close."
)


def derive_gate(body: str, vocabulary: Sequence[str]) -> Gate:
    """Decide which gate this issue is owed, or say plainly that it cannot be decided."""
    paths = named_paths(body)
    reached = in_world(paths)
    if reached:
        return Gate(GATE_REGRESS, REGRESS_LINE, (f"in_world={','.join(reached[:4])}", WHY_REGRESS))
    if not vocabulary:
        return Gate(
            GATE_UNDETERMINED, UNDETERMINED_LINE, ("vocabulary=unreadable", WHY_NO_VOCABULARY)
        )
    if not paths:
        return Gate(GATE_UNDETERMINED, UNDETERMINED_LINE, ("named_paths=none", WHY_NO_PATHS))
    mentions = domain_mentions(body, vocabulary)
    if mentions:
        return Gate(
            GATE_UNDETERMINED,
            UNDETERMINED_LINE,
            (
                f"named_paths=none-in-world domain_terms={','.join(mentions[:4])}",
                WHY_DOMAIN_LANGUAGE,
            ),
        )
    return Gate(GATE_FAST, FAST_LINE, (f"named_paths={','.join(paths[:4])}", WHY_FAST))


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

# CLAUDE.md's Model roles mapping, one reason per seat `tools/dispatch.py` registers.
# Keyed off that registry rather than beside it: `test_brief.py` asserts the two agree, so
# a seat cannot join the registry without a reason to state in a briefing.
SEAT_REASON: Final[dict[str, str]] = {
    "implementer": "CLAUDE.md Model roles: implementation and day-to-day review.",
    "mechanical": "CLAUDE.md Model roles: mechanical one-commit executions.",
    "recon": "CLAUDE.md Model roles: read-only reconnaissance; never edits or lands.",
    "review": "CLAUDE.md Model roles: review; a review lands nothing (ADR-0061 decision 3).",
    "fable": (
        "CLAUDE.md Model roles: ADRs, CONTEXT.md, schema semantics and process docs — "
        "anything no mechanical gate catches."
    ),
    "orchestrator": "CLAUDE.md Model roles: the dispatching seat itself.",
}

DEFAULT_SEAT: Final = "implementer"


class Seat(NamedTuple):
    """Which seat the brief names, and whether the orchestrator still owes a reason."""

    name: str
    reason: str
    owes_reason: bool


def derive_seat(override: str) -> Seat:
    """Name the seat and quote the mapping's reason, or ask for the orchestrator's.

    A non-default seat is a judgement the design leaves with the orchestrator, so the
    mapping's line is printed *and* a placeholder is opened beside it: the mapping says
    what the seat is for, and only the orchestrator knows why this issue wants it.
    """
    name = override or DEFAULT_SEAT
    return Seat(
        name, SEAT_REASON.get(name, ""), owes_reason=bool(override) and name != DEFAULT_SEAT
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
FLAKE_RESPONSE: Final = (
    "`flake_quarantine`: do not act. If one of those exact tests is your only red, quote its"
    " issue number and re-run once; a second red, or any other red, is yours."
)
PASTE_RULE: Final = (
    "Quote `just verdict`'s rendered body verbatim; never retype the SHA or the evidence"
    " path (CLAUDE.md; #219's A/B — all four failures were retyping)."
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


def compose(briefing: Briefing) -> str:
    """Render the invariant half, with the variable half left as visible placeholders."""
    issue, seat, tree, gate = briefing.issue, briefing.seat, briefing.tree, briefing.gate
    lines = [
        f"# Dispatch brief — #{issue}: {briefing.title}",
        "",
        "## Task, scope, ground truth",
        _placeholder(TASK_PLACEHOLDER),
        "",
        f"## Seat: {seat.name}",
        seat.reason,
    ]
    if seat.owes_reason:
        lines.append(_placeholder(SEAT_PLACEHOLDER))
    lines += [
        "",
        "## Worktree",
        (
            f"`just worktree add issue-{issue}` → `{tree.path}`,"
            f" base `{tree.base or 'printed by that call'}` ({tree.source})."
        ),
        "Work only there. Files you did not write mean stop and report, never reset (#105).",
        f"Finish with `just worktree done issue-{issue}`.",
        "",
        f"## Gate: {gate.line}",
        *gate.because,
        "",
        f"## Open flakes ({len(briefing.flakes)}, read live at composition)",
    ]
    if briefing.flakes:
        lines += [flake.line() for flake in briefing.flakes]
        lines.append(FLAKE_RESPONSE)
    else:
        lines.append("None open. Any red is yours.")
    lines += [
        "",
        "## Landing",
        f"Conventional Commits, `refs #{issue}`, commit early.",
        "Land via `just land` and paste its output verbatim — never retype it.",
        f"Close #{issue} with a criterion-by-criterion audit.",
    ]
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
    parser.add_argument("--out", default="", help="write the brief here instead of stdout")
    parser.add_argument(
        "--base-sha",
        default="",
        help="the base SHA `just worktree add` printed, when it is not this box's",
    )
    parser.add_argument("--repo", default=REPO_SLUG, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    read_issue: Callable[[int, str], dict[str, object]] = fetch_issue,
    read_open: Callable[[str], list[dict[str, object]]] = fetch_open_issues,
    repo: Path = REPO,
) -> int:
    """Compose the brief, or refuse loudly. Never a silent empty brief."""
    args = parse_args(argv)
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
    rendered = compose(
        Briefing(
            issue=args.issue,
            title=str(document.get("title") or ""),
            gate=gate,
            flakes=select_flakes(open_issues),
            seat=derive_seat(args.seat),
            tree=resolve_tree(args.issue, args.base_sha, repo),
            assessment=readiness.assess(body),
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
    if args.out:
        Path(args.out).expanduser().write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")  # noqa: T201 — the brief IS this script's output
    return 0


if __name__ == "__main__":
    sys.exit(main())
