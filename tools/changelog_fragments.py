"""Per-branch changelog fragments, folded into `CHANGELOG.md` at staging and landing (#358).

A branch records its changelog entry as a file of its own — `changelog.d/<issue>-<slug>.md`
— and `CHANGELOG.md` stops being a write surface every branch contends on. The contention
was not hypothetical: `tools/queue_policy.py`'s `surface_conflict` rung refuses two in-flight
trees writing the same paths, every branch edited `CHANGELOG.md`, so any two implementations
in flight refused (#355 recommendation 8), and the `05e478f` class of hand-resolved diff3
mis-merge was the cost the rung existed to price.

The fold is the half that has to be mechanical. It runs inside the landing protocol
(`tools/land.py`), after the rebase and before the review rung reads a SHA, so the commit
it makes is part of what a verdict binds — `just land --stage` folds first and prints the
post-fold SHA for exactly that reason. Two branches landing minutes apart cannot produce a
hand mis-resolution because neither hand touches `CHANGELOG.md` at all: each branch's own
fragment is a path unique to its issue, the rebase never conflicts on it, and the fold
appends into `[Unreleased]` under headings that already exist.

Determinism is filename order, not timestamps or directory enumeration: fragments sort by
their leading issue number and then by name, and the merged `[Unreleased]` is a pure
function of the fragment set plus the changelog it was handed. A fold removes every
fragment it merged in the same commit, so `origin/main` never carries one and the next
landing's rebase inherits nothing stale.

Failures refuse by name and write nothing: a fragment that does not parse, or a
`CHANGELOG.md` with no `[Unreleased]` heading, is refused before the first write, and a
git step that fails leaves the tree for the lander rather than tidying it — the same rule
`tools/land.py` keeps on every other refusal path.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path — the same device
# `tools/land.py` uses to reach `worktree`. Placed before the import it enables.
sys.path.insert(0, str(Path(__file__).parent))

from worktree import GitError, Refusal, git

if TYPE_CHECKING:
    from collections.abc import Sequence

# Keep a Changelog 1.1.0's category set, in the order the spec lists them. The
# order is the insertion order for a category `[Unreleased]` does not carry yet;
# where the heading already exists the fold appends under it and moves nothing.
CATEGORIES: Final = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

# `## [Unreleased]`, the section every fold lands in (ADR-0010). Matched on the
# stripped line so trailing whitespace in a hand-edited file is not a refusal.
UNRELEASED: Final = "## [Unreleased]"

# `changelog.d/<issue>-<slug>.md`. The leading number is the fragment's sort key
# and the reason two branches' entries are two paths, and it must be an issue
# number for that: a slug without one sorts opaquely and collides by name. The
# slug is lowercase kebab, the shape the repository's issue titles already use.
FRAGMENT_NAME: Final = re.compile(r"^(\d+)-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")

# `### <Category>` — a level-three heading inside a fragment or the changelog.
# Deeper headings belong to an entry's own body and are content, not structure.
HEADING: Final = re.compile(r"^###\s+(\w+)\s*$")

# The refusal kinds, as constants for the same reason every other literal here
# is one: a kind a test or a caller spells should have one spelling.
MALFORMED: Final = "changelog_fragment_malformed"
UNRELEASED_MISSING: Final = "changelog_unreleased_missing"
MISSING: Final = "changelog_missing"
COMMIT_FAILED: Final = "changelog_commit_failed"

# What the fold commit says. `chore(changelog)` passes `cog verify` and carries
# no user-visible effect of its own: the entries inside it are the effect, and
# they name their issues in their own bold leads, as every entry in this file does.
FOLD_SUBJECT: Final = "chore(changelog): fold {count} fragment(s) into [Unreleased]"


class FragmentError(Exception):
    """A reason the fold cannot run, with the refusal kind it becomes.

    Raised by the read-only half so `check_changelog` can report the same defect
    a landing would refuse on, and carried into a `Refusal` at the boundary.
    """

    def __init__(self, kind: str, found: tuple[str, ...], action: str) -> None:
        """Keep the refusal's three faces, exactly as `worktree.Refusal` holds them."""
        super().__init__(action)
        self.kind = kind
        self.found = found
        self.action = action


class Fragment(NamedTuple):
    """One fragment file: where it sits, and the `### <Category>` sections it carries."""

    path: Path
    sections: tuple[tuple[str, str], ...]


class Fold(NamedTuple):
    """What one fold pass found: how many fragments, its report line, or its refusal."""

    merged: int
    line: str
    refusal: Refusal | None


def sort_key(path: Path) -> tuple[int, str]:
    """Return the deterministic order: issue number first, then the whole filename."""
    found = FRAGMENT_NAME.match(path.name)
    if found is None:
        message = f"sort_key called on unvalidated name {path.name}"
        raise FragmentError(MALFORMED, (f"fragment={path.name}",), message)
    return (int(found.group(1)), path.name)


def parse_fragment(path: Path) -> Fragment:  # noqa: C901 — a ladder of named refusals, one per shape
    """Parse one fragment into its `(category, entry text)` sections.

    The text between two headings is kept verbatim — an entry's own wrapping is
    its author's — with only the blank runs around it normalised, and a category
    may appear once per fragment so the merge order is the file order. Anything
    before the first heading is refused rather than silently dropped: a fold that
    loses a line the author wrote is the mis-merge this module replaces, inline.
    """
    sections: list[tuple[str, str]] = []
    category: str | None = None
    body: list[str] = []
    relative = path.relative_to(path.parents[1]).as_posix()

    def _close(name: str) -> None:
        nonlocal body
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        if not body:
            raise FragmentError(
                MALFORMED,
                (f"fragment={relative}", f"section={name}"),
                f"The `{name}` section of `{relative}` is empty. A fragment section "
                "carries at least one entry, or it is not an entry.",
            )
        sections.append((name, "\n".join(body)))
        body = []

    def _checked(line: str) -> re.Match[str] | None:
        return HEADING.match(line.strip()) if line.startswith("###") else None

    for line in path.read_text(encoding="utf-8").splitlines():
        found = _checked(line)
        if found is not None:
            if category is not None:
                _close(category)
            _open_section(found.group(1), line, relative, sections)
            category = found.group(1)
        elif category is not None:
            body.append(line)
        elif line.strip():
            raise FragmentError(
                MALFORMED,
                (f"fragment={relative}", f"line={line.strip()}"),
                f"`{relative}` carries prose above its first `### <Category>` heading. A "
                "fragment is sections and nothing before them — that line would be "
                "dropped at the fold, so it is refused here instead.",
            )
    if category is not None:
        _close(category)
    if not sections:
        raise FragmentError(
            MALFORMED,
            (f"fragment={relative}",),
            f"`{relative}` carries no `### <Category>` section. A fragment is one or more "
            "of those, each holding the entries that category gains — the shape "
            "`tools/check_changelog.py` refuses to let reach a landing.",
        )
    return Fragment(path, tuple(sections))


def _open_section(name: str, line: str, relative: str, sections: list[tuple[str, str]]) -> None:
    """Validate one `### <Category>` heading a fragment opens, or refuse it."""
    if name not in CATEGORIES:
        raise FragmentError(
            MALFORMED,
            (f"fragment={relative}", f"heading={line.strip()}"),
            f"`{relative}` opens a section `{name}` that Keep a Changelog does not "
            f"carry. The category set is {', '.join(CATEGORIES)} (ADR-0010).",
        )
    if any(name == seen for seen, _ in sections):
        raise FragmentError(
            MALFORMED,
            (f"fragment={relative}", f"section={name}"),
            f"`{relative}` carries two `{name}` sections. One section per category "
            "per fragment, so the fold's order is the file's order.",
        )


def collect(root: Path) -> list[Fragment]:
    """Return every parseable fragment under `root`, in the deterministic order.

    Read-only, so the check recipe and a dry run can hold a landing to the same
    standard the fold enforces without writing anything. A `changelog.d/` that is
    absent is no fragments rather than an error: a branch with no entry to record
    has nothing to fold, and the directory itself only exists where an entry does.
    """
    directory = root / "changelog.d"
    if not directory.is_dir():
        return []
    found: list[Path] = []
    stray: list[str] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if FRAGMENT_NAME.match(path.name):
            found.append(path)
        else:
            stray.append(path.name)
    if stray:
        names = " ".join(stray)
        raise FragmentError(
            MALFORMED,
            *(f"stray={name}" for name in stray),
            "`changelog.d/` holds a file the fold would never merge: "
            f"{names}. Every file there is `/<issue>-<slug>.md`, so a name outside that "
            "shape is either a misnamed fragment or a note that belongs in the issue, "
            "and both are fixed here rather than survived at landing.",
        )
    return [parse_fragment(path) for path in sorted(found, key=sort_key)]


def _unreleased(changelog: str) -> tuple[list[str], int, int, list[str]]:
    """Split the changelog around its `[Unreleased]` body, or refuse.

    Returns the whole line list, the heading's index, the index one past the
    body's last line, and the body's own lines — the pieces `merge_text` splices
    back together after the insertions land.
    """
    lines = changelog.splitlines()
    head = next((i for i, line in enumerate(lines) if line.strip() == UNRELEASED), None)
    if head is None:
        raise FragmentError(
            UNRELEASED_MISSING,
            (),
            "`CHANGELOG.md` carries no `## [Unreleased]` section, so there is nowhere a "
            "fragment can land. A release rolled it into a version heading without "
            "opening a fresh one — restore the empty section and fold again.",
        )
    end = head + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    return lines, head, end, lines[head + 1 : end]


def _section_edge(body: list[str], at: int) -> int:
    """Return the body index a block lands at: the section's end, before its trailing blanks.

    `at` is the heading's own index; the block splices in above the blank run
    that separates the section's last entry from whatever follows it, which is
    what keeps existing spacing untouched rather than renormalised.
    """
    stop = at + 1
    while stop < len(body) and not body[stop].startswith("###"):
        stop += 1
    edge = stop
    while edge > at + 1 and not body[edge - 1].strip():
        edge -= 1
    return edge


def _body_edge(body: list[str]) -> int:
    """Return the `[Unreleased]` body's end, before its trailing blank run."""
    edge = len(body)
    while edge > 0 and not body[edge - 1].strip():
        edge -= 1
    return edge


def _first_headings(body: list[str]) -> dict[str, int]:
    """Return each category's first `###` heading index within the body.

    First only: the changelog's `[Unreleased]` repeats a category heading when
    a release pass left it that way, and the fold appends under the first while
    leaving the repeats exactly where they stand.
    """
    first: dict[str, int] = {}
    for index, line in enumerate(body):
        if not line.startswith("###"):
            continue
        found = HEADING.match(line.strip())
        if found is not None and found.group(1) not in first:
            first[found.group(1)] = index
    return first


def merge_text(changelog: str, fragments: Sequence[Fragment]) -> str:
    """Return the new `CHANGELOG.md` text, with every fragment folded into `[Unreleased]`.

    Surgical by design: existing sections keep their text and their spacing, and
    the fold touches only the lines where a fragment's entries land — the blank
    line that separates them from what was there, and the entries themselves. A
    whole-file normalisation would put the diff of every landing over the whole
    `[Unreleased]` section, which is the shared-write cost this module exists to
    remove, paid a second time in review noise.

    A category the section already carries appends under its first heading; one
    it does not carry gains a heading at the section's end, in the canonical
    order. Repeated headings later in the section are left exactly as they are.
    """
    lines, head, end, body = _unreleased(changelog)
    first = _first_headings(body)

    # Sorted here rather than trusted from the caller: the merged text is a
    # function of the fragment *set* whatever order it arrived in, which is the
    # determinism the fold exists to guarantee (#358's own criterion).
    grouped: dict[str, list[str]] = {}
    for fragment in sorted(fragments, key=lambda each: sort_key(each.path)):
        for category, text in fragment.sections:
            grouped.setdefault(category, []).append(text)

    insertions: list[tuple[int, list[str]]] = []
    for category in CATEGORIES:
        blocks = grouped.get(category)
        if not blocks:
            continue
        joined = "\n\n".join(blocks)
        at = first.get(category)
        if at is None:
            insertions.append((_body_edge(body), ["", f"### {category}", "", joined]))
        else:
            insertions.append((_section_edge(body, at), ["", joined]))

    # Grouped by index so blocks aimed at one position — two categories the
    # section does not carry yet both land at its end — keep the canonical order
    # they were built in, and spliced highest-first so earlier indices hold.
    at: dict[int, list[str]] = {}
    for edge, block in insertions:
        at.setdefault(edge, []).extend(block)
    for edge in sorted(at, reverse=True):
        body[edge:edge] = at[edge]

    merged = [*lines[: head + 1], *body, *lines[end:]]
    text = "\n".join(merged)
    # The trailing newline is the file's own state before the fold, kept rather
    # than normalised: the landing's diff is the fragment's entries and nothing.
    return text + "\n" if changelog.endswith("\n") else text


def _refusal(error: FragmentError) -> Refusal:
    return Refusal(error.kind, error.found, error.action)


def inspect(root: Path) -> Fold:
    """Count and validate the fragments a fold would merge, writing nothing.

    The dry run's half of the contract: the fold's own pre-flight, consulted
    where the rebase has not run and nothing may be written, so a plan's silence
    about a malformed fragment stops reading as a clearance (#41's line).
    """
    try:
        fragments = collect(root)
    except FragmentError as error:
        return Fold(0, "", _refusal(error))
    return Fold(len(fragments), f"changelog=would_fold {len(fragments)} fragment(s)", None)


def fold(here: Path) -> Fold:
    """Merge every fragment into `CHANGELOG.md`, commit, and remove them.

    Return the count and the report line on success, or the named refusal and
    a tree exactly as it was — every write happens after every parse, and a git
    step that fails is reported with git's own words rather than retried.
    """
    try:
        fragments = collect(here)
    except FragmentError as error:
        return Fold(0, "", _refusal(error))
    if not fragments:
        return Fold(0, "changelog=not_needed reason=no_fragments", None)

    target = here / "CHANGELOG.md"
    if not target.is_file():
        return Fold(
            0,
            "",
            Refusal(
                MISSING,
                (f"worktree={here}",),
                "`CHANGELOG.md` is not here to fold into. This tree has fragments and no "
                "changelog, which no landing should meet — check what moved it before "
                "running anything else.",
            ),
        )
    try:
        text = merge_text(target.read_text(encoding="utf-8"), fragments)
    except FragmentError as error:
        return Fold(0, "", _refusal(error))

    target.write_text(text, encoding="utf-8")
    for fragment in fragments:
        fragment.path.unlink()
    try:
        git("add", "-A", "--", "CHANGELOG.md", "changelog.d", cwd=here)
        git("commit", "-m", FOLD_SUBJECT.format(count=len(fragments)), cwd=here)
    except GitError as failure:  # pragma: no cover — git's own failure path
        return Fold(
            0,
            "",
            Refusal(
                COMMIT_FAILED,
                (
                    f"worktree={here}",
                    f"command=git {' '.join(failure.args_run)}",
                    f"detail={failure.stderr}",
                ),
                "The fragments are folded in the working tree and the commit that carries "
                "them did not run. Read git's own words above; nothing here retried or "
                "tidied, and the tree is the lander's to judge.",
            ),
        )
    short = git("rev-parse", "--short", "HEAD", cwd=here).strip()
    return Fold(len(fragments), f"changelog=merged {len(fragments)} fragment(s) as {short}", None)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin CLI over `fold`
    """Fold this tree's fragments now, outside the landing protocol.

    The landing protocol is the fold's home and needs no help from here; this
    entry point exists for the one-off — recovering a tree whose fragments a
    refused run left behind — and refuses in the same words `just land` would.
    """
    parser = argparse.ArgumentParser(
        prog="changelog-fragments", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="the tree to fold")
    args = parser.parse_args(argv)
    result = fold(args.root.resolve())
    if result.refusal is not None:
        print(result.refusal.kind, " ".join(result.refusal.lines), file=sys.stderr)  # noqa: T201
        print(result.refusal.action, file=sys.stderr)  # noqa: T201
        return 1
    print(result.line)  # noqa: T201 — the fold's one-line result IS this script's output
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
