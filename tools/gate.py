"""The gate-derivation functions: pure readers of an issue body and a checkout.

`derive_gate` decides which gate an issue is owed from the paths and domain terms its body
names, and `read_vocabulary` reads CONTEXT.md for those terms. These are the inputs both the
brief composer (`tools/brief.py`) and the dispatch record's strata (`tools/dispatch.py`,
#323) need, and they live here rather than in either of those modules because `brief`
imports `dispatch` at module level. A `capture_strata` that reached them through `brief`
would close that ring and load a second dispatcher under the production `__main__` shape,
so the functions were lifted to this owner, which imports neither (#323 review finding 3).
Nothing here depends on a lane, a profile, a seat or an outcome — only on a body and a
repository root.

**The in-world surface list lives here too, since #328.** It was `tools/admission.py`'s,
and that module's bar was dropped; the list is a property of what an in-world surface *is*
rather than of the bar that once read it, and the gate derivation is its heaviest reader.
`tools/trial.py`'s corpus check reads it from here rather than keeping a second copy.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `dispatch.py` uses.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes this importable.
import routing_policy

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# The checkout this script is running out of, which is where CONTEXT.md lives. A worktree's
# own copy is the right one to read: a session is governed by the tree it is working in
# (ADR-0042's stale-hook lesson, applied to the documents).
REPO: Final = Path(__file__).resolve().parents[1]

# ------------------------------------------------------------- the in-world surface list

# The in-world surfaces, from CLAUDE.md's `just regress` row and docs/regression-tier.md's
# cost-control section. The daemon's world-facing half is named there as "anything that
# builds, validates, serialises or hands over what crosses the extension wire — the port's
# dispatch and refusals, the outbox, the command/effect codec", which is those modules.
#
# **Read, not written.** The list itself is class 5 of the routing policy since #302,
# because `just land`'s corpus rung needs the same answer out of fetched `origin/main` —
# where only data can be read. An unreadable policy raises rather than defaults: a reader
# would otherwise compute "nothing is in-world" and waive the very gate the list protects.
#
# It is used in one direction only: to say that a surface *is* in-world. It is never read
# as "this landing touched nothing, so the corpus was not needed" — that judgement stays a
# person's, because a list of paths cannot know what a change means.


def _in_world_prefixes() -> tuple[str, ...]:
    """Read the one authority once, at import, and fail loudly rather than guess."""
    read = routing_policy.read_policy(REPO / routing_policy.POLICY_RELATIVE)
    if read.policy is None:
        raise routing_policy.PolicyError(read.error)
    return routing_policy.in_world_prefixes(read.policy)


IN_WORLD_PREFIXES: Final = _in_world_prefixes()


def touches_in_world(paths: Iterable[str]) -> tuple[str, ...]:
    """Name the in-world surfaces a landing touched, empty when it touched none."""
    return tuple(path for path in paths if path.startswith(IN_WORLD_PREFIXES))


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
    """Name the in-world surfaces among these paths, using this module's list and no other."""
    return touches_in_world(paths)


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
