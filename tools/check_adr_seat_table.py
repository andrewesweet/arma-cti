"""`just check-adr`'s content half: ADR-0071's seat table equals the registry.

`tools/check_adr_form.py` reads every ADR and asks whether the required words are
there. This reads one table in one ADR and asks whether its *data* still says
what `tools/dispatch.py`'s `SEATS` and `DECLARED_ONLY_SEATS` say — the preference
and escalation columns ruling 2 tables, plus the one provenance fact that
survives ruling 1, `orchestrator`'s Claude-only carve-out. #392 filed the gap
after it had already bitten once: amendment A1 landed at `eaabf9f` filling
`retro`'s and `orchestrator`'s escalation cells while the registry still carried
neither, so for one commit the ADR said what no live surface said (#361 review
round 1, claim 1). The second instance was the mirror image — `e19410e` renamed
`zai-glm52-max` to `zai-glm53-max` in the registry and left the ADR's table
naming the retired profile — and this check's first run on the #392 tree found
exactly that drift, which amendment A5 reconciles in the same commit that lands
this file.

Comparison is exact and string-wise, deliberately. Profiles are opaque
`(lane, model, effort)` tokens (ADR-0061 decision 5): no cross-provider ordering
exists, so "close enough" names nothing here, and a comparator that tolerated
near-misses would read as coverage while clearing the typo it exists to catch.
Every cell must parse or be a finding: a blank escalation cell is a refusal
since A1 struck the blanket fallback, so a cell that is neither an entry nor a
not-applicable marker is precisely the ambiguity that amendment closed in prose
and this closes in data.

Two cells are prose by design and parsed as phrases rather than lists:
`review`'s preference is "the implementer's list" and its escalation is "the
implementer's escalation head". The shared `IMPLEMENTER_PREFERENCE` and
`IMPLEMENTER_ESCALATION` objects are what keep those facts rather than copies
that drift, and this check resolves the phrases through them, so the sharing is
asserted rather than assumed. The interlocutor row is marked "not dispatched"
and resolves through `DECLARED_ONLY_SEATS`, where ruling 2's last paragraph
parks it.

One seat the registry carries is legitimately missing from the table: the ADR
names `fable`'s deliberate absence in prose, and this check requires that prose
to still say so — the exception's ground is read out of the document it
exceptions, never asserted by this file. A second registry seat with no row and
no such sentence is a finding, because that is exactly how an unrulled seat
would look.

Failure output names both surfaces, the seat and the column that drifted, so
the remedy is an edit on either side — amend ADR-0071 under its sign-off gate,
or move `SEATS` — in the same commit, never one without the other.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes this importable.
import dispatch

# The table is located by its header rather than by a heading number so a
# renumbered ruling still checks — and so a deleted table is a finding about
# the missing table, not a silent pass over zero rows.
ADR_GLOB: Final = "0071-*.md"
HEADER_PREFIX: Final = "| seat |"
BACKTICKED: Final = re.compile(r"`([^`]+)`")
SEAT_WORD: Final = re.compile(r"[a-z]+")
NOT_DISPATCHED: Final = "not dispatched"
NEVER_ESCALATES: Final = "never escalates"
IMPLEMENTERS_LIST: Final = "the implementer's list"
IMPLEMENTERS_HEAD: Final = "the implementer's escalation head"
CLAUDE_ONLY: Final = "Claude only"
EXPECTED_CELLS: Final = 3

# Registry seats with no row in the table, each mapped to the sentence fragment
# the ADR must still carry for the absence to stand. Derived from the document
# rather than asserted here: if the prose goes, the exception's ground goes with
# it and the finding says so. Matched against whitespace-normalised source,
# because the ADR is hard-wrapped prose and the sentence breaks mid-fragment.
ABSENT_GROUNDS: Final[dict[str, str]] = {
    "fable": "deliberately absent from this table and stays absent: `fable`",
}

SAME_COMMIT_REMEDY: Final = (
    "amend ADR-0071's ruling-2 table (a human sign-off gate) and "
    "`tools/dispatch.py`'s registry in the same commit — one without the other "
    "is the drift this check exists to refuse"
)
PARSE_REMEDY: Final = (
    "a row this check cannot parse is a row nothing compares — restore the "
    "cell's shape or teach this check the new one"
)


class Registry(NamedTuple):
    """The registry-side surfaces the table is compared against."""

    seats: dict[str, dispatch.Seat]
    declared_only: dict[str, dispatch.Seat]
    implementer_preference: tuple[str, ...]
    implementer_escalation: tuple[str, ...]


class Finding(NamedTuple):
    """One way the table and the registry disagree, or the table stopped parsing."""

    path: str
    line: int
    problem: str
    remedy: str

    def __str__(self) -> str:
        """Render as an editor-clickable location."""
        return f"{self.path}:{self.line}: {self.problem}. {self.remedy}"


def split_row(line: str) -> list[str]:
    """Return a table line's cells, stripped."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table_rows(source: str) -> list[tuple[int, list[str]]]:
    """Return `(line number, cells)` for the header and body of ruling 2's table.

    The body runs from the header to the first line that is not a table row, so
    a paragraph after the table ends it and prose elsewhere that opens with
    `| seat |` cannot extend it.
    """
    lines = source.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(HEADER_PREFIX)), None)
    if start is None:
        return []
    rows = [(start + 1, split_row(lines[start]))]
    for i in range(start + 1, len(lines)):
        if not lines[i].startswith("|"):
            break
        rows.append((i + 1, split_row(lines[i])))
    return rows


def is_separator(cells: list[str]) -> bool:
    """Return whether a row is the markdown separator (`---`)."""
    return bool(cells) and all(set(cell) <= {"-"} for cell in cells)


def seat_name(cell: str) -> str:
    """Return the seat a row names: its first backticked token, or its first word.

    The interlocutor row is the one that arrives unbackticked, so the word
    fallback is its path and not an ornament — `planner`'s cell backticks the
    seat and also `cti-implementer-xhigh`, and only the first token is the
    seat.
    """
    found = BACKTICKED.search(cell)
    if found:
        return found.group(1)
    word = SEAT_WORD.search(cell)
    return word.group(0) if word else ""


def expected_preference(cell: str, implementer_preference: tuple[str, ...]) -> tuple[str, ...]:
    """Return the preference list a cell states, raising for a cell that states none.

    A cell that both names the implementer's list and lists profiles is
    rejected rather than resolved: the phrase and a list are two answers, and
    which one holds is the ADR's to say, not this parser's.
    """
    tokens = tuple(BACKTICKED.findall(cell))
    if IMPLEMENTERS_LIST in cell:
        if tokens:
            message = f"states the implementer's list and also names {list(tokens)}"
            raise ValueError(message)
        return tuple(implementer_preference)
    if not tokens:
        message = "names no profiles"
        raise ValueError(message)
    return tokens


def expected_escalation(cell: str, implementer_escalation: tuple[str, ...]) -> tuple[str, ...]:
    """Return the escalation entry a cell states, raising for a cell that states none.

    The two not-applicable markers — `recon`'s "never escalates" and the
    interlocutor's "not dispatched" — are the ADR's own spellings for the empty
    entry the registry records as `()`. Anything else that is not an entry is a
    finding, because a blank cell has been a refusal since A1 struck the
    blanket `fable-high` fallback.
    """
    tokens = tuple(BACKTICKED.findall(cell))
    if IMPLEMENTERS_HEAD in cell:
        if tokens:
            message = f"states the implementer's escalation head and also names {list(tokens)}"
            raise ValueError(message)
        return (implementer_escalation[0],)
    if NEVER_ESCALATES in cell or NOT_DISPATCHED in cell:
        if tokens:
            message = f"marked not-applicable and also names {list(tokens)}"
            raise ValueError(message)
        return ()
    if not tokens:
        message = (
            "carries neither an entry nor a not-applicable marker — a blank "
            "escalation cell is a refusal since A1"
        )
        raise ValueError(message)
    return tokens


def _comparison_finding(
    path: str, line: int, seat: str, column: str, sides: tuple[tuple[str, ...], tuple[str, ...]]
) -> Finding:
    """Return the finding for one column whose two surfaces disagree."""
    adr, registry = sides
    return Finding(
        path,
        line,
        f"`{seat}` {column}: ADR {list(adr)} != registry {list(registry)}",
        SAME_COMMIT_REMEDY,
    )


def _row_findings(
    path: str, line: int, cells: list[str], registry: Registry
) -> tuple[str, list[Finding]]:
    """Return the row's seat name and its findings, comparison and parse alike."""
    findings: list[Finding] = []
    name = seat_name(cells[0])
    if not name:
        return name, [Finding(path, line, "row names no seat", PARSE_REMEDY)]
    seat = {**registry.seats, **registry.declared_only}.get(name)
    if seat is None:
        problem = f"`{name}` is tabled here but `tools/dispatch.py` registers no such seat"
        return name, [Finding(path, line, problem, SAME_COMMIT_REMEDY)]
    try:
        preference = expected_preference(cells[1], registry.implementer_preference)
    except ValueError as exc:
        findings.append(Finding(path, line, f"`{name}` preference cell {exc}", PARSE_REMEDY))
    else:
        if tuple(seat.preference) != preference:
            findings.append(
                _comparison_finding(
                    path, line, name, "preference", (preference, tuple(seat.preference))
                )
            )
    try:
        escalation = expected_escalation(cells[2], registry.implementer_escalation)
    except ValueError as exc:
        findings.append(Finding(path, line, f"`{name}` escalation cell {exc}", PARSE_REMEDY))
    else:
        if tuple(seat.escalation) != escalation:
            findings.append(
                _comparison_finding(
                    path, line, name, "escalation", (escalation, tuple(seat.escalation))
                )
            )
    if (CLAUDE_ONLY in cells[1]) != seat.claude_only:
        marked = CLAUDE_ONLY in cells[1]
        findings.append(
            Finding(
                path,
                line,
                f"`{name}` claude-only: ADR {marked} != registry {seat.claude_only}",
                SAME_COMMIT_REMEDY,
            )
        )
    return name, findings


def _absence_findings(
    path: str, source: str, registry: Registry, tabled: set[str]
) -> list[Finding]:
    """Return findings for registry seats the table carries no row for."""
    findings: list[Finding] = []
    normalised = " ".join(source.split())
    for name in sorted({**registry.seats, **registry.declared_only}):
        if name in tabled:
            continue
        ground = ABSENT_GROUNDS.get(name)
        if ground is None:
            problem = (
                f"`tools/dispatch.py` registers `{name}` with no row in the table "
                "and no stated absence"
            )
            findings.append(Finding(path, 1, problem, SAME_COMMIT_REMEDY))
        elif ground not in normalised:
            problem = (
                f"`{name}`'s deliberate absence from the table is no longer stated "
                "in the ADR, so this check's exception for it has lost its ground"
            )
            findings.append(Finding(path, 1, problem, SAME_COMMIT_REMEDY))
    return findings


def scan_source(source: str, path: str, registry: Registry) -> list[Finding]:
    """Compare ruling 2's table in `source` against a seat registry."""
    rows = table_rows(source)
    if not rows:
        return [
            Finding(
                path,
                1,
                "ruling 2's seat table not found — no line opens '| seat |'",
                "restore the table or teach this check the new shape; a table "
                "this check cannot find is a table nothing compares",
            )
        ]

    findings: list[Finding] = []
    tabled: set[str] = set()
    for line, cells in rows[1:]:  # rows[0] is the header
        if is_separator(cells):
            continue
        if len(cells) != EXPECTED_CELLS:
            problem = f"row carries {len(cells)} cells, expected seat, preference, escalation"
            findings.append(Finding(path, line, problem, PARSE_REMEDY))
            continue
        name, row_findings = _row_findings(path, line, cells, registry)
        tabled.add(name)
        findings.extend(row_findings)
    findings.extend(_absence_findings(path, source, registry, tabled))
    return findings


def scan_tree(root: Path) -> list[Finding]:
    """Compare the live ADR-0071 against the live registry."""
    matches = sorted((root / "docs" / "adr").glob(ADR_GLOB))
    if len(matches) != 1:
        problem = f"expected exactly one {ADR_GLOB} file, found {len(matches)}"
        return [
            Finding(
                "docs/adr/",
                1,
                problem,
                "this check compares that file; a tree without exactly one is a "
                "tree where the comparison cannot run",
            )
        ]
    path = matches[0].relative_to(root).as_posix()
    return scan_source(
        matches[0].read_text(encoding="utf-8"),
        path,
        Registry(
            seats=dict(dispatch.SEATS),
            declared_only=dict(dispatch.DECLARED_ONLY_SEATS),
            implementer_preference=dispatch.IMPLEMENTER_PREFERENCE,
            implementer_escalation=dispatch.IMPLEMENTER_ESCALATION,
        ),
    )


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
