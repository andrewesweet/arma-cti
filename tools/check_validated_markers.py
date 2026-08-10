"""Count checks for `validated ×N` markers (issue #186).

A marker's count can drift from what it narrates with nothing noticing, and it
has now done so twice: the fourteenth retro's commit added `docs/agents/`
`recovery.md`'s ninth use with the count still ×8, and the fifteenth's own
commit appended convention-lands' #131 exemplar with the count still ×3, which
then rode three retros' status lines before anyone read the file. The second
violation is what the retro skill's same-edit clause pre-priced as escalating to
a mechanical check per ADR-0038's shape. This is that check.

Two marker shapes exist, and both are countable — each against its own unit.

**Status headers** (`> Status: validated ×N — …`, in `docs/agents/recovery.md`
and three skills) narrate *uses*, and number them as they go: "Eighth use
(2026-08-02): …", "Sixth and seventh uses (2026-08-02): …". So the count has an
arithmetic relation to the prose that a machine can read: a header must not
narrate a use its own count does not reach. That is a lower bound, not an
equality, and deliberately so — see `narrated_uses`.

**Inline parentheticals** (`_(validated ×N — …)_`, CLAUDE.md's) list
*exemplars*, under the convention the human ruled on #186 (Option A,
2026-08-07): every exemplar opens with its reference and a colon — `#NN: `,
`#80/#96/#102: `, `ADR-0039/0040/0041: `, `Phase 0: ` — at the start of the
list or after a sentence or semicolon boundary, and a continuation sentence
inside an exemplar never opens reference-and-colon. Counting those openers is
counting the exemplars, so an unpruned list's ×N must equal its openers. A
pruned list (the #201 convention: past five exemplars, the inline list keeps
only the newest five, announced by its prelude) must keep exactly five, with
×N above five. See `UNVERIFIED` for what that deliberately leaves unproven.

The gate also inventories every `validated ×N` it sees, because a marker in a
shape this file does not recognise is a marker nothing checks — so an
unrecognised shape is itself a finding.

`docs/adr/` and `docs/process-log.md` are not scanned. They narrate counts as
history — "Failure classes `×3` → `×4`", "Marker: `unproven` → `validated ×1`" —
which is a record of a marker, not a marker.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

UNVERIFIED: Final = """\
Two claims stay deliberately unproven here. A pruned list's count above its \
inline five rests on docs/process-log.md's prune record (#201), not on a \
recount — so an exemplar pruned in the same edit that forgot the count bump \
is invisible to this gate, and stays the retro skill's step-5 discipline. \
And a status header's count is a lower bound over the uses its prose numbers \
with an ordinal-qualified noun, never an equality — see `narrated_uses`.\
"""

SAME_EDIT: Final = "The ×N and its appended exemplar move in the same edit (retro skill, step 5)."

MARKER: Final = re.compile(r"validated ×(\d+)")
STATUS: Final = re.compile(r"^> Status: validated ×(\d+) — ", re.MULTILINE)
# `(.*?)\)_` and not `\)`: the bodies contain parentheses of their own.
INLINE: Final = re.compile(r"_\(validated ×(\d+) — (.*?)\)_", re.DOTALL)
# An exemplar's opener under #186's ruling: a reference run and a colon, at the
# list's start or after a sentence or semicolon boundary. The reference grammar
# is the corpus's own: slash-joined issue refs (`#80/#96/#102`), an ADR number
# run spelt once (`ADR-0039/0040/0041`), or a phase (`Phase 0`). A mid-sentence
# reference, a possessive (`#37's`), or a sentence-initial reference without
# its colon is prose, not an opener — anchoring on the colon is what keeps a
# sentence *about* an exemplar from counting as one.
OPENER: Final = re.compile(r"(?:^|(?<=[.;] ))(?:#\d+(?:/#\d+)*|ADR-\d{4}(?:/\d{4})*|Phase \d+): ")
# The #201 prune convention, announced in the list itself: past five exemplars
# the inline list keeps only the newest five, and the rest live in the process
# log. The prelude is matched exactly so a list cannot half-claim it.
PRUNE_PRELUDE: Final = re.compile(
    r"^newest five exemplars, the rest pruned to docs/process-log\.md per #201: "
)
PRUNE_KEEPS: Final = 5

UNITS: Final = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
    "thirteenth",
    "fourteenth",
    "fifteenth",
    "sixteenth",
    "seventeenth",
    "eighteenth",
    "nineteenth",
)
TENS: Final = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
ROUND: Final = {f"{tens[:-1]}ieth": (index + 2) * 10 for index, tens in enumerate(TENS)}
ORDINALS: Final = {word: value for value, word in enumerate(UNITS, start=1)} | ROUND
# "Twenty-first use", as the retro skill's twenty-first entry spells it.
COMPOUND: Final = {
    f"{tens}-{unit}": (index + 2) * 10 + ORDINALS[unit]
    for index, tens in enumerate(TENS)
    for unit in UNITS[:9]
}
ORDINAL_VALUES: Final = ORDINALS | COMPOUND
# Longest first, so "twenty-first" is not read as "first".
USE: Final = re.compile(
    r"\b(" + "|".join(sorted(ORDINAL_VALUES, key=len, reverse=True)) + r")\s+uses?\b",
    re.IGNORECASE,
)


class Marker(NamedTuple):
    """One `validated ×N` marker, with the text it is a count of."""

    path: str
    line: int
    shape: str
    count: int
    body: str
    span: tuple[int, int]


class Finding(NamedTuple):
    """One marker whose count does not survive reading what it narrates."""

    path: str
    line: int
    problem: str
    remedy: str

    def __str__(self) -> str:
        """Render as an editor-clickable location."""
        return f"{self.path}:{self.line}: {self.problem}. {self.remedy}"


def narrated_uses(body: str) -> list[tuple[str, int]]:
    """Every "Nth use" the prose names, as (word, value).

    A lower bound on the uses narrated, on purpose. The retro skill's header
    numbers most of its uses as bare ordinals — "The twenty-first ran
    attended-by-instruction" — and reading every ordinal instead would red the
    live tree, because `recovery.md` ×13 also says "the eighteenth retro left
    open" and "(The fourteenth retro's edit". Anchoring on the noun is what
    makes the gate's one rule zero-false-positive against the real prose; the
    price is that a bare-ordinal narration is not read at all.

    The conjunction form — "Sixth and seventh uses" — yields the second ordinal
    only, which is the larger one in English, and the larger is what binds.
    """
    return [(m.group(1), ORDINAL_VALUES[m.group(1).lower()]) for m in USE.finditer(body)]


def _line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _quoted_block(source: str, start: int) -> tuple[str, int]:
    """Return the blockquote beginning at `start`, unwrapped, and its end offset."""
    lines: list[str] = []
    end = start
    for line in source[start:].splitlines(keepends=True):
        if not line.startswith(">"):
            break
        lines.append(line.removeprefix(">").strip())
        end += len(line)
    return " ".join(lines), end


def markers_in(source: str, path: str) -> list[Marker]:
    """Every marker in `source`, in the shapes this gate recognises."""
    markers = []
    for match in STATUS.finditer(source):
        body, end = _quoted_block(source, match.start())
        markers.append(
            Marker(
                path,
                _line_of(source, match.start()),
                "status header",
                int(match.group(1)),
                body,
                (match.start(), end),
            )
        )
    markers.extend(
        Marker(
            path,
            _line_of(source, match.start()),
            "inline parenthetical",
            int(match.group(1)),
            match.group(2),
            match.span(),
        )
        for match in INLINE.finditer(source)
    )
    return sorted(markers, key=lambda marker: marker.span)


def scan_source(source: str, path: str) -> list[Finding]:
    """Report every marker in `source` whose count fails what it narrates."""
    markers = markers_in(source, path)
    findings = [
        Finding(
            path,
            _line_of(source, match.start()),
            f"`validated ×{match.group(1)}` in a shape this gate does not recognise, "
            f"so nothing checks it",
            "Write it as a `> Status:` header or an inline `_(validated ×N — …)_`, "
            "or teach tools/check_validated_markers.py the shape.",
        )
        for match in MARKER.finditer(source)
        if not any(marker.span[0] <= match.start() < marker.span[1] for marker in markers)
    ]
    for marker in markers:
        if marker.shape == "status header":
            uses = narrated_uses(marker.body)
            beyond = [(word, value) for word, value in uses if value > marker.count]
            findings.extend(
                Finding(
                    marker.path,
                    marker.line,
                    f"status header says ×{marker.count} but narrates a {word.lower()} "
                    f"use ({value})",
                    SAME_EDIT,
                )
                for word, value in beyond
            )
        else:
            findings.extend(inline_findings(marker))
    return sorted(findings, key=lambda finding: (finding.line, finding.problem))


def inline_findings(marker: Marker) -> list[Finding]:
    """Count an inline list's reference-and-colon exemplars against its ×N."""
    body = re.sub(r"\s+", " ", marker.body.strip())
    prelude = PRUNE_PRELUDE.match(body)
    entries_text = body[prelude.end() :] if prelude else body
    openers = list(OPENER.finditer(entries_text))
    if not openers or openers[0].start() != 0:
        return [
            Finding(
                marker.path,
                marker.line,
                f"inline list under ×{marker.count} does not open with a "
                f"reference-and-colon exemplar",
                "Open every exemplar `#NN: ` (or `ADR-NNNN: `, `Phase N: `) at a sentence "
                "or semicolon boundary — #186's ruling — and never open a continuation "
                "sentence reference-and-colon.",
            )
        ]
    entries = len(openers)
    if prelude is None:
        if entries != marker.count:
            return [
                Finding(
                    marker.path,
                    marker.line,
                    f"inline list says ×{marker.count} but opens {entries} exemplars",
                    SAME_EDIT,
                )
            ]
    elif marker.count <= PRUNE_KEEPS:
        return [
            Finding(
                marker.path,
                marker.line,
                f"a pruned list says ×{marker.count}, but pruning starts past {PRUNE_KEEPS}",
                "Drop the prune prelude and list every exemplar, or move the count to what "
                "docs/process-log.md's prune record vouches for (#201).",
            )
        ]
    elif entries != PRUNE_KEEPS:
        return [
            Finding(
                marker.path,
                marker.line,
                f"a pruned list keeps {entries} exemplars where the convention keeps "
                f"the newest {PRUNE_KEEPS}",
                f"{SAME_EDIT} Past {PRUNE_KEEPS}, prune the oldest to docs/process-log.md "
                "and bump ×N in that same edit (#201).",
            )
        ]
    return []


def marker_files(root: Path) -> list[Path]:
    """Every file that carries, or could carry, a live marker.

    `docs/reference/` is the vendored wiki, `docs/adr/` and the process log
    narrate counts as history rather than carrying them, and the glob over
    `.claude/` is deliberately the skills only: a recursive walk would pick up
    the nested agent worktrees, which run this gate on their own trees.
    `docs/research/process-interfaces.md` is a verbatim landing of an issue
    comment (#209) that cites CLAUDE.md's own `validated ×9` and `validated
    ×7` counts by digit as evidence in its analysis — a citation, not a
    marker this file carries — so it is excluded by exact path rather than
    edited to fit a shape this gate recognises.
    """
    excluded = {
        root / "docs" / "process-log.md",
        root / "docs" / "research" / "process-interfaces.md",
    }
    files = [root / "CLAUDE.md", *sorted((root / ".claude" / "skills").glob("*/SKILL.md"))]
    files.extend(
        path
        for path in sorted((root / "docs").rglob("*.md"))
        if not path.is_relative_to(root / "docs" / "reference")
        and not path.is_relative_to(root / "docs" / "adr")
        and path not in excluded
    )
    return [path for path in files if path.is_file()]


def tree_markers(root: Path) -> list[Marker]:
    """Every marker in the tree, whatever its shape."""
    markers: list[Marker] = []
    for path in marker_files(root):
        relative = path.relative_to(root).as_posix()
        markers.extend(markers_in(path.read_text(encoding="utf-8"), relative))
    return markers


def scan_tree(root: Path) -> list[Finding]:
    """Report every marker under `root` whose count fails what it narrates."""
    findings: list[Finding] = []
    for path in marker_files(root):
        relative = path.relative_to(root).as_posix()
        findings.extend(scan_source(path.read_text(encoding="utf-8"), relative))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Check the tree and print one line per finding."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)

    findings = scan_tree(args.root.resolve())
    for finding in findings:
        print(finding, file=sys.stderr)  # noqa: T201
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
