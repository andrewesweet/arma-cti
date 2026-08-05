"""Count checks for `validated ×N` markers (issue #186).

A marker's count can drift from what it narrates with nothing noticing, and it
has now done so twice: the fourteenth retro's commit added `docs/agents/`
`recovery.md`'s ninth use with the count still ×8, and the fifteenth's own
commit appended convention-lands' #131 exemplar with the count still ×3, which
then rode three retros' status lines before anyone read the file. The second
violation is what the retro skill's same-edit clause pre-priced as escalating to
a mechanical check per ADR-0038's shape. This is that check.

Two marker shapes exist, and only one of them is countable.

**Status headers** (`> Status: validated ×N — …`, in `docs/agents/recovery.md`
and three skills) narrate *uses*, and number them as they go: "Eighth use
(2026-08-02): …", "Sixth and seventh uses (2026-08-02): …". So the count has an
arithmetic relation to the prose that a machine can read: a header must not
narrate a use its own count does not reach. That is a lower bound, not an
equality, and deliberately so — see `narrated_uses`.

**Inline parentheticals** (`_(validated ×N — …)_`, CLAUDE.md's five) list
*exemplars*, and are **not counted here**. See `UNCOUNTABLE`: no rule derived
from the corpus counts them, so the count for those five stays the retro skill's
step-5 discipline plus whatever list-format convention the human rules on (#186
carries the proposal). The gate still inventories them, because a marker in a
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

UNCOUNTABLE: Final = """\
CLAUDE.md's exemplar lists have no machine delimiter, and every rule derivable \
from the prose miscounts at least two of the five. Counting sentence-initial \
issue references reads probe-window as 9 against its ×8 (the #104 entry carries \
"#24 rode the same discipline the same day" as part of the same validation \
event) and ADR-claiming as 5 against its ×6 (one entry opens "The \
0039→0040→0041 renumber chains"). Requiring a colon after the reference reads \
convention-lands as 1 against its ×4, since three of its four entries open \
"#NN landed …" with no colon at all. The unit being counted is a validation \
event as narrated, which is a prose judgement.\
"""

MARKER: Final = re.compile(r"validated ×(\d+)")
STATUS: Final = re.compile(r"^> Status: validated ×(\d+) — ", re.MULTILINE)
# `(.*?)\)_` and not `\)`: the bodies contain parentheses of their own.
INLINE: Final = re.compile(r"_\(validated ×(\d+) — (.*?)\)_", re.DOTALL)

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
        if marker.shape != "status header":
            continue  # inline parentheticals are not countable — see UNCOUNTABLE.
        uses = narrated_uses(marker.body)
        beyond = [(word, value) for word, value in uses if value > marker.count]
        findings.extend(
            Finding(
                marker.path,
                marker.line,
                f"status header says ×{marker.count} but narrates a {word.lower()} use ({value})",
                "The ×N and its appended exemplar move in the same edit (retro skill, step 5).",
            )
            for word, value in beyond
        )
    return sorted(findings, key=lambda finding: (finding.line, finding.problem))


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
