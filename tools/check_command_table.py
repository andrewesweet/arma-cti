#!/usr/bin/env python3
"""Check the mechanically safe part of ADR-0013's command-table route (#544).

This module deliberately checks only two facts: changed AGENTS.md lines stay in
command-table data rows, and recipes named by those rows are present in the
candidate justfile.  It does not judge a row's prose description.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Final, NamedTuple

# tools/ contains standalone scripts; reuse just's parser through the sibling
# checker rather than maintaining a second recipe grammar here.
sys.path.insert(0, str(Path(__file__).parent))

import check_just_grants

BASE: Final = "origin/main"
AGENTS_PATH: Final = "AGENTS.md"
JUSTFILE_PATH: Final = "justfile"

COMMAND_TABLE_ESCAPE: Final = "command_table_escape"
COMMAND_TABLE_RECIPE_UNRESOLVED: Final = "command_table_recipe_unresolved"
COMMAND_TABLE_UNREADABLE: Final = "command_table_unreadable"

HUNK: Final = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
RECIPE: Final = re.compile(r"\bjust[ \t]+(?P<recipe>[A-Za-z_][A-Za-z0-9_-]*)\b")
SEPARATOR_CELL: Final = re.compile(r"\s*:?-+:?\s*\Z")


class GitError(RuntimeError):
    """A Git read needed to establish the candidate diff failed."""

    def __init__(self, args: tuple[str, ...], detail: str) -> None:
        """Keep the fixed Git command and its readable failure."""
        super().__init__(detail)
        self.args_run = args
        self.detail = detail


class TableError(RuntimeError):
    """AGENTS.md did not contain a readable command table."""

    def __init__(self, detail: str) -> None:
        """Keep the parser's typed detail available to the caller."""
        super().__init__(detail)


class Hunk(NamedTuple):
    """One zero-context text-diff hunk."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int


class Row(NamedTuple):
    """One command-table data row and its source line."""

    line: int
    command: str


class Failure(NamedTuple):
    """A typed refusal with the evidence and remedy it needs."""

    kind: str
    details: tuple[str, ...]
    action: str


class Result(NamedTuple):
    """The command-table result consumed by the gated-path checker."""

    applicable: bool
    lines: tuple[str, ...]
    failure: Failure | None
    recipe_resolution: bool


def _git_bytes(*args: str, cwd: Path) -> bytes:
    """Run one fixed local Git read."""
    completed = subprocess.run(  # noqa: S603 — fixed Git executable and arguments
        ["git", *args],  # noqa: S607 — Git is the repository authority
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(args, detail or f"exit {completed.returncode}")
    return completed.stdout


def _read_current(root: Path, path: str) -> str:
    """Read one current candidate file as UTF-8."""
    try:
        return (root / path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        detail = f"path={path} reason={error}"
        raise TableError(detail) from error


def _read_baseline(root: Path, path: str) -> str:
    """Read one baseline file from the same ref the gate compares against."""
    try:
        source = _git_bytes("show", f"{BASE}:{path}", cwd=root)
        return source.decode("utf-8")
    except (GitError, UnicodeError) as error:
        detail = f"baseline={BASE}:{path} reason={error}"
        raise TableError(detail) from error


def _cells(line: str) -> tuple[str, ...] | None:
    """Split one Markdown table row, respecting escaped pipe characters."""
    stripped = line.rstrip("\n")
    if not stripped.startswith("|") or not stripped.rstrip().endswith("|"):
        return None
    cells: list[str] = []
    cell: list[str] = []
    escaped = False
    for character in stripped[1:]:
        if character == "|" and not escaped:
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(character)
        escaped = character == "\\" and not escaped
    return tuple(cells)


def _is_separator(cells: tuple[str, ...]) -> bool:
    """Whether every cell is Markdown's separator syntax."""
    return bool(cells) and all(SEPARATOR_CELL.fullmatch(cell) for cell in cells)


def table_rows(source: str) -> tuple[Row, ...]:
    """Return command-table data rows, or raise when the table is unreadable."""
    lines = source.splitlines()
    header_index: int | None = None
    header_cells: tuple[str, ...] | None = None
    for index, line in enumerate(lines[:-1]):
        cells = _cells(line)
        next_cells = _cells(lines[index + 1])
        if cells and cells[0] == "Command" and next_cells and _is_separator(next_cells):
            header_index = index
            header_cells = cells
            break
    if header_index is None or header_cells is None:
        detail = "command table header and separator not found"
        raise TableError(detail)

    rows: list[Row] = []
    for offset, line in enumerate(lines[header_index + 2 :], header_index + 3):
        if not line.strip():
            break
        cells = _cells(line)
        if cells is None:
            break
        if len(cells) != len(header_cells):
            detail = f"line={offset} cells={len(cells)} expected={len(header_cells)}"
            raise TableError(detail)
        rows.append(Row(offset, cells[0]))
    return tuple(rows)


def _hunks(diff: bytes) -> tuple[Hunk, ...]:
    """Parse zero-context hunk ranges from a Git diff."""
    found: list[Hunk] = []
    for line in diff.splitlines():
        match = HUNK.match(line)
        if match is None:
            continue
        old_start, old_count, new_start, new_count = match.groups()
        found.append(
            Hunk(
                int(old_start),
                int(old_count or b"1"),
                int(new_start),
                int(new_count or b"1"),
            )
        )
    return tuple(found)


def _interval(start: int, count: int) -> tuple[int, int] | None:
    """Return an inclusive changed-line interval, or none for a pure insertion/deletion side."""
    return None if count == 0 else (start, start + count - 1)


def _covered(rows: tuple[Row, ...], interval: tuple[int, int] | None) -> bool:
    """Whether every line in a changed-line interval is a data-row line."""
    if interval is None:
        return True
    start, end = interval
    row_lines = {row.line for row in rows}
    return all(line in row_lines for line in range(start, end + 1))


def _changed_rows(rows: tuple[Row, ...], hunks: tuple[Hunk, ...]) -> tuple[Row, ...]:
    """Return current data rows touched by additions or replacements."""
    found: dict[int, Row] = {}
    for hunk in hunks:
        interval = _interval(hunk.new_start, hunk.new_count)
        if interval is None:
            continue
        start, end = interval
        for row in rows:
            if start <= row.line <= end:
                found[row.line] = row
    return tuple(found[line] for line in sorted(found))


def _recipes(command: str) -> tuple[str, ...]:
    """Extract recipe names from the command cell, preserving first occurrence."""
    return tuple(dict.fromkeys(match["recipe"] for match in RECIPE.finditer(command)))


def _failure(kind: str, details: tuple[str, ...], action: str) -> Result:
    """Build an applicable typed refusal."""
    return Result(
        applicable=True,
        lines=(),
        failure=Failure(kind, details, action),
        recipe_resolution=False,
    )


def _parse_tables(baseline: str, current: str) -> Result | tuple[tuple[Row, ...], tuple[Row, ...]]:
    """Parse both table versions, retaining non-table trees outside this route."""
    try:
        baseline_rows = table_rows(baseline)
        current_rows = table_rows(current)
    except TableError as error:
        # A repository whose two versions have no command table is outside this
        # route; existing direct approvals retain their broader human scope.
        baseline_has_table = "| Command |" in baseline
        current_has_table = "| Command |" in current
        if not baseline_has_table and not current_has_table:
            return Result(applicable=False, lines=(), failure=None, recipe_resolution=False)
        return _failure(
            COMMAND_TABLE_UNREADABLE,
            (f"path={AGENTS_PATH}", f"detail={error}"),
            "Restore the command-table header, separator and rows, then retry the gate.",
        )
    return baseline_rows, current_rows


def _read_hunks(root: Path) -> tuple[Hunk, ...] | Failure:
    """Read the candidate AGENTS.md text hunks."""
    try:
        diff = _git_bytes(
            "diff",
            "--unified=0",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            BASE,
            "--",
            AGENTS_PATH,
            cwd=root,
        )
    except GitError as error:
        return Failure(
            COMMAND_TABLE_UNREADABLE,
            (
                f"path={AGENTS_PATH}",
                f"command=git {' '.join(error.args_run)}",
                f"detail={error}",
            ),
            "Restore a readable origin/main and worktree, then retry the gate.",
        )
    hunks = _hunks(diff)
    if hunks:
        return hunks
    return Failure(
        COMMAND_TABLE_ESCAPE,
        (f"path={AGENTS_PATH}", "escaped=non_text_change"),
        "Keep the delegated AGENTS.md change to command-table data rows only.",
    )


def _confinement_failure(
    baseline_rows: tuple[Row, ...],
    current_rows: tuple[Row, ...],
    hunks: tuple[Hunk, ...],
) -> Failure | None:
    """Name the first hunk that reaches outside data rows."""
    for hunk in hunks:
        old_interval = _interval(hunk.old_start, hunk.old_count)
        new_interval = _interval(hunk.new_start, hunk.new_count)
        if not _covered(baseline_rows, old_interval) and old_interval is not None:
            return Failure(
                COMMAND_TABLE_ESCAPE,
                (
                    f"path={AGENTS_PATH}",
                    f"escaped=baseline:{old_interval[0]}-{old_interval[1]}",
                ),
                "Keep the delegated AGENTS.md change to command-table data rows only.",
            )
        if not _covered(current_rows, new_interval) and new_interval is not None:
            return Failure(
                COMMAND_TABLE_ESCAPE,
                (
                    f"path={AGENTS_PATH}",
                    f"escaped=candidate:{new_interval[0]}-{new_interval[1]}",
                ),
                "Keep the delegated AGENTS.md change to command-table data rows only.",
            )
    return None


def _resolution_failure(root: Path, changed: tuple[Row, ...]) -> Failure | None:
    """Name the first changed row whose command does not resolve in just."""
    justfile = root / JUSTFILE_PATH
    try:
        defined = check_just_grants.defined_recipes(justfile)
    except check_just_grants.JustDumpError as error:
        return Failure(
            COMMAND_TABLE_RECIPE_UNRESOLVED,
            (f"path={AGENTS_PATH}", f"justfile={justfile}", f"detail={error}"),
            "Make the candidate justfile parse and define every command-table recipe.",
        )
    for row in changed:
        recipes = _recipes(row.command)
        if not recipes:
            return Failure(
                COMMAND_TABLE_RECIPE_UNRESOLVED,
                (f"path={AGENTS_PATH}", f"row={row.line}", "recipe=<none>"),
                "Name a resolving `just` recipe in the command-table row.",
            )
        for recipe in recipes:
            if recipe not in defined:
                return Failure(
                    COMMAND_TABLE_RECIPE_UNRESOLVED,
                    (
                        f"path={AGENTS_PATH}",
                        f"row={row.line}",
                        f"recipe={recipe}",
                        f"justfile={justfile}",
                    ),
                    "Make the candidate justfile define the recipe named by the row.",
                )
    return None


def check(root: Path) -> Result:  # noqa: PLR0911 — each typed refusal names its failed claim
    """Check the current AGENTS.md diff for the delegated command-table route."""
    try:
        baseline = _read_baseline(root, AGENTS_PATH)
        current = _read_current(root, AGENTS_PATH)
    except TableError as error:
        return _failure(
            COMMAND_TABLE_UNREADABLE,
            (f"path={AGENTS_PATH}", f"detail={error}"),
            "Restore a readable AGENTS.md command table and retry the gate.",
        )

    if baseline == current:
        return Result(applicable=False, lines=(), failure=None, recipe_resolution=False)

    parsed = _parse_tables(baseline, current)
    if isinstance(parsed, Result):
        return parsed
    baseline_rows, current_rows = parsed

    hunk_result = _read_hunks(root)
    if isinstance(hunk_result, Failure):
        return Result(applicable=True, lines=(), failure=hunk_result, recipe_resolution=False)
    confinement = _confinement_failure(baseline_rows, current_rows, hunk_result)
    if confinement is not None:
        return Result(applicable=True, lines=(), failure=confinement, recipe_resolution=False)

    changed = _changed_rows(current_rows, hunk_result)
    if not changed:
        return Result(
            applicable=True,
            lines=("command_table=ok path=AGENTS.md rows=0",),
            failure=None,
            recipe_resolution=False,
        )

    resolution = _resolution_failure(root, changed)
    if resolution is not None:
        return Result(applicable=True, lines=(), failure=resolution, recipe_resolution=False)

    names = ",".join(recipe for row in changed for recipe in _recipes(row.command))
    return Result(
        applicable=True,
        lines=(f"command_table=ok path=AGENTS.md rows={len(changed)} recipes={names}",),
        failure=None,
        recipe_resolution=True,
    )


def _route_candidate(root: Path) -> tuple[bool, int | None]:
    """Return whether the diff carries exactly one delegated record, and the issue."""
    # The gated-path checker remains the authority for path and ADR-0013 marker
    # discovery; this CLI only needs the same eligibility to expose a named leg.
    import gated_paths  # noqa: PLC0415 — delayed to avoid the checker import cycle

    try:
        paths = gated_paths.changed_paths(root)
    except gated_paths.GitError as error:
        raise GitError(error.args_run, error.stderr) from error
    delegated = gated_paths.delegated_decisions(root, paths)
    issue, _issue_error = gated_paths.issue_of(root, os.environ)
    applicable = (
        "AGENTS.md" in paths
        and len(delegated) == 1
        and not gated_paths._has_current_approval_record(  # noqa: SLF001 — mirror the route precondition
            root,
            gated_paths.APPROVAL_ROOT,
            issue,
            AGENTS_PATH,
        )
    )
    return applicable, issue


def _refuse(kind: str, details: tuple[str, ...], action: str) -> int:
    """Print one typed refusal with its remedy; the CLI's only refusing exit (#583)."""
    print(f"refusal={kind}", file=sys.stderr)  # noqa: T201 — CLI contract
    if details:
        print("\n".join(details), file=sys.stderr)  # noqa: T201 — CLI contract
    print(f"action={action}", file=sys.stderr)  # noqa: T201 — CLI contract
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run the checker directly for diagnostics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        applicable, issue = _route_candidate(root)
    except (GitError, OSError) as error:
        # An unreadable repository is a repair problem, not an approval one:
        # the approval command needs a content_id no unreadable tree can give.
        return _refuse(
            COMMAND_TABLE_UNREADABLE,
            (f"detail={error}",),
            "Restore a readable origin/main and worktree, then retry the check.",
        )
    if not applicable:
        print("command_table=not_applicable")  # noqa: T201 — CLI contract
        return 0
    result = check(root)
    if not result.applicable:
        print("command_table=not_applicable")  # noqa: T201 — CLI contract
        return 0
    if result.failure is not None:
        import gated_paths  # noqa: PLC0415 — delayed to avoid the checker import cycle

        # The standalone documented path must name the same exit as the gate
        # route, or a human meeting it alone still dead-ends (#583).
        return _refuse(
            result.failure.kind,
            result.failure.details,
            gated_paths.direct_approval_remedy(root, issue, result.failure.action),
        )
    print("\n".join(result.lines))  # noqa: T201 — CLI contract
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
