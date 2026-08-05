"""Red a landing whose new tests do not notice the code changing (issue #239).

Every other gate in `just fast` asks whether the code is right. None of them asks
whether the *tests* are. A suite of `assert True` passes `just check`, passes
`just unit`, and lands — the defences against that were red-first discipline in a
briefing (prose, unenforced for a foreign session), a habit visible in closing
comments (#214, #196: "six planted mutants, all six killed" — by hand, every
time), and `mutmut`, which #172's close found scoped to modules that did not
exist and which does not run against this repo's pytest config as shipped.

This is that habit mechanised: for every test module a landing adds or rewrites,
plant a bounded sample of mutants in the source those tests actually execute and
require the tests to notice. Lane-blind by construction — it is a rung in
`just fast`, which `tools/land.py` runs as the landing gate, so a z.ai or Codex
landing meets exactly the same red as a native one.

## Why a bespoke mutator rather than mutmut or cosmic-ray

Measured on this tree, 2026-08-05, not inherited (see `docs/research/mutation-testing.md`):

- **mutmut 3.6.0 can be made to run** — `source_paths` at package level, the
  tests/tools/config trees in `also_copy`, `-n0` in `pytest_add_cli_args` — but
  what it then reports is unusable as a gate. On `src/cti_daemon/dedupe.py`, a
  module whose tests are sound, it generated 8 mutants and 3 survived: dropping
  `digest_size=16`, spelling `"utf-8"` as `"UTF-8"`, and `digest_size=17`. All
  three are *equivalent* — the dedupe window keys on an opaque digest, so no
  test can tell. A kill-rate floor over that operator set would have to sit below
  62.5% to keep the tree green, which is a floor no vacuous suite would trip.
- **cosmic-ray 8.4.6 installs** (29 packages, SQLAlchemy among them) and is built
  around a session database and a distributed executor. Its unit of work is a
  full sweep to be resumed, not a bounded sample judged inside a gate.
- Both mutate a whole file or a whole tree and run the whole suite per mutant.
  This gate needs the opposite shape: a handful of mutants on the lines *one new
  test module* executes, each judged by *only the tests that reach that line*.

So the operator set here is chosen for a low equivalent-mutant rate rather than
for coverage of the mutation-testing literature — string literals are never
touched, keyword-argument and default-argument values are never touched, and
what remains is the arithmetic of decisions: which way a comparison points,
which way a boolean joins, whether a `not` is there, what a function hands back.

## How a subject is chosen

Not by the `test_x.py` → `x.py` naming convention, which `tests/unit/test_land.py`
→ `tools/land.py` already only half obeys and which a data-driven test module
does not obey at all. By evidence: the module is run once under `coverage.py`
with `dynamic_context = test_function`, and the subject is the product file with
the most lines executed *inside a test* — import-time lines do not count, so a
module that imports the world and asserts nothing has no subject at all.

That is the second red this gate can give, and it is the one an `assert True`
module earns: a test module that executes none of this repo's source under any
of its tests has, mechanically, tested nothing.

## Safety

Mutants are applied in place, to the real tree, because that is the only way the
tests run exactly as `just unit` runs them — `tests/unit/conftest.py` loads a
`tools/` script by absolute path and several tests shell out to `git` in the
worktree, so a copied tree is a different subject. In-place means a crash could
leave a mutant behind, so every mutation writes `RESTORE` first, restores in a
`finally` and on SIGINT/SIGTERM, and refuses to start while a stale `RESTORE`
exists — it prints how to undo it instead of guessing.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, NamedTuple

# Where this repo's own source lives. A file outside these is somebody else's
# code and is never mutated, however much of it a test happens to execute.
PRODUCT_ROOTS: Final = ("src/", "tools/", ".claude/hooks/")

# The sidecar that makes an in-place mutation recoverable. Held in the worktree
# root rather than under ~/.arma-cti, because the thing it repairs is this tree.
RESTORE: Final = ".mutation-smoke-restore.json"

# Mutants planted per test module. Bounded on purpose: this is a smoke, not a
# proof. Twenty is enough that a suite asserting nothing cannot pass by luck
# (see `docs/research/mutation-testing.md` for the arithmetic) and few enough
# that the tier's cost stays inside the budget `just fast` can afford.
CAP: Final = 20

# The kill rate a module must reach. Not 100%: an equivalent mutant survives no
# matter how good the tests are, and this operator set does not eliminate them,
# only makes them rare. Set from the corpus sweep in the research note — every
# one of the repo's own test modules clears it, with the margin recorded there.
FLOOR: Final = 0.75

# A module's smoke gives up after this long and judges what it managed to run.
# A smoke that ran fewer mutants is a weaker claim, never a pass by default: a
# module that reached no verdict at all is a red.
BUDGET_S: Final = 90.0

# The coverage pass has its own bound, because it is the test module's own cost
# rather than this gate's: `tests/unit/test_client_lock.py` carries a deliberate
# 60 s soak (#197 criterion 6) and one run of it is one run of it. Sharing a
# single budget between the two phases would red exactly the modules whose tests
# are slowest, which is a bound on the harness masquerading as a verdict.
COLLECT_S: Final = 600.0

# Tests to run per mutant, cheapest first. Deliberately generous: `-x` stops at
# the first red, so a line reached by half a suite of millisecond tests costs
# about what one of them costs, and leaving the killing test out of the selection
# is a false survivor the floor then has to be lowered to accommodate.
TESTS_PER_MUTANT: Final = 200
# ...and the wall clock those tests may cost between them, before the selection
# stops adding. Cheapest-first ordering is what makes this bound cheap rather
# than arbitrary: a 60 s soak is never chosen while a 0.01 s test reaches the
# same line.
TEST_SECONDS_PER_MUTANT: Final = 8.0
# The grain durations are rounded to before anything is ordered or summed by
# them. Coarser than the run-to-run jitter of a millisecond test, finer than the
# difference between a test worth waiting for and one that is not.
COST_GRAIN: Final = 0.1

# How long one mutant's tests get before the run is abandoned. A mutant that
# makes the subject loop forever is detected only this way, so a timeout counts
# as a kill — it is the tests noticing, slowly. Derived from what the same tests
# cost unmutated, so it never bounds an honestly slow test out of a verdict.
TIMEOUT_FLOOR_S: Final = 20.0
TIMEOUT_FACTOR: Final = 4.0

# `0.12s call tests/unit/test_x.py::test_y` — three fields, and a line with any
# other shape is not one of pytest's duration rows.
DURATION_FIELDS: Final = 3

# The test modules whose subject is not Python, each with the reason. Mutating
# Python has nothing to say about a module that asserts on `spike/*.sh`, on the
# justfile, or on an authored JSON document, and a gate that red them anyway
# would be #137/#186's false red on the tree it exists to protect.
#
# This list is the escape, and it is deliberately the *only* one: there is no
# flag, no marker in a test file and no environment variable, so a module that
# tests nothing can be excused only by a line here, in the diff, with its reason
# next to it. `grep -n '"tests/' tools/mutation_smoke.py` answers "which modules
# claim to have no Python subject" completely. Adding a row is a reviewable act;
# lowering `FLOOR` is not an alternative to it.
NO_PYTHON_SUBJECT: Final[dict[str, str]] = {}

# Negating a comparison: the strongest single change to a decision that was
# taken, and the one a suite which asserts nothing at all fails to notice.
_FLIP: Final = {
    ast.Eq: "!=",
    ast.NotEq: "==",
    ast.Lt: ">=",
    ast.GtE: "<",
    ast.Gt: "<=",
    ast.LtE: ">",
    ast.Is: "is not",
    ast.IsNot: "is",
    ast.In: "not in",
    ast.NotIn: "in",
}

# Shifting a comparison by one: `>` still points the same way, the boundary moves.
# A negated `>` usually blows the code up somewhere and any red suite kills it,
# so negation alone measures "does anything go red"; this measures whether the
# tests pinned the *edge*, which is what a suite of `assert x is not None`
# reaches over. Only the four ordering operators have such a neighbour — there is
# nothing one step from `==` or from `is`.
_SHIFT: Final = {
    ast.Lt: "<=",
    ast.LtE: "<",
    ast.Gt: ">=",
    ast.GtE: ">",
}


class Mutant(NamedTuple):
    """One planted change: where it goes, what it replaces, and what with."""

    path: str
    line: int
    operator: str
    start: int
    end: int
    before: str
    after: str

    def __str__(self) -> str:
        """Render as an editor-clickable location and the edit itself."""
        return f"{self.path}:{self.line}: {self.operator}: {self.before} -> {self.after}"


def _line_starts(text: str) -> list[int]:
    """Byte offset of each line's first character.

    `ast` reports columns in UTF-8 bytes, so spans are computed in bytes and the
    slice is decoded back. A source with a non-ASCII character before a mutation
    site would otherwise be cut in the wrong place.
    """
    starts = [0]
    for line in text.encode("utf-8").splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _span(node: ast.AST, starts: list[int]) -> tuple[int, int] | None:
    """Byte span of a node, or None when the node carries no position."""
    line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", None)
    col = getattr(node, "col_offset", None)
    end_col = getattr(node, "end_col_offset", None)
    if line is None or end_line is None or col is None or end_col is None:
        return None
    if end_line >= len(starts):
        return None
    return starts[line - 1] + col, starts[end_line - 1] + end_col


def _segment(raw: bytes, span: tuple[int, int]) -> str:
    """Return the source text a span covers."""
    return raw[span[0] : span[1]].decode("utf-8")


def _frozen(tree: ast.AST) -> set[int]:
    """Return the ids of nodes this mutator deliberately leaves alone.

    Keyword-argument values and parameter defaults, because that is where opaque
    configuration lives — `blake2b(..., digest_size=16)` is the mutant mutmut
    planted on `dedupe.py` that no test could ever kill, and every such literal
    that survives here would have to be paid for by lowering the floor.

    Everything inside an f-string, because a replacement there would be grafted
    into a format expression whose reported span this mutator has no business
    trusting; the `graft` compile check would drop most of them anyway, and a
    dropped mutant is budget spent on nothing.
    """
    frozen: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            frozen.add(id(node.value))
        elif isinstance(node, ast.arguments):
            for default in [*node.defaults, *node.kw_defaults]:
                if default is not None:
                    frozen.add(id(default))
        elif isinstance(node, ast.JoinedStr):
            frozen.update(id(child) for child in ast.walk(node))
    return frozen


@dataclass
class _Planter:
    """Walks one file's tree and collects the mutants its covered lines allow."""

    path: str
    raw: bytes
    starts: list[int]
    lines: frozenset[int]
    frozen: set[int]
    found: list[Mutant] = field(default_factory=list)

    def _add(self, node: ast.AST, operator: str, after: str) -> None:
        span = _span(node, self.starts)
        line = getattr(node, "lineno", 0)
        if span is None or line not in self.lines or id(node) in self.frozen:
            return
        self.found.append(
            Mutant(self.path, line, operator, span[0], span[1], _segment(self.raw, span), after),
        )

    def _text(self, node: ast.AST) -> str | None:
        span = _span(node, self.starts)
        return None if span is None else _segment(self.raw, span)

    def visit(self, node: ast.AST) -> None:
        """Collect every mutant this node offers."""
        if isinstance(node, ast.Compare):
            self._compare(node)
        elif isinstance(node, ast.BoolOp):
            self._boolop(node)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            self._negation(node)
        elif isinstance(node, ast.Constant):
            self._constant(node)
        elif isinstance(node, ast.Return):
            self._return(node)

    def _compare(self, node: ast.Compare) -> None:
        # Chained comparisons (`a < b < c`) are left alone: rewriting one link of
        # a chain is a mutant whose meaning is hard to state in a report.
        if len(node.ops) != 1:
            return
        left, right = self._text(node.left), self._text(node.comparators[0])
        if left is None or right is None:
            return
        for operator, table in (("compare", _FLIP), ("boundary", _SHIFT)):
            symbol = table.get(type(node.ops[0]))
            if symbol is not None:
                self._add(node, operator, f"({left} {symbol} {right})")

    def _boolop(self, node: ast.BoolOp) -> None:
        symbol = "or" if isinstance(node.op, ast.And) else "and"
        parts = [self._text(value) for value in node.values]
        if any(part is None for part in parts):
            return
        self._add(node, "boolop", "(" + f" {symbol} ".join(part or "" for part in parts) + ")")

    def _negation(self, node: ast.UnaryOp) -> None:
        operand = self._text(node.operand)
        if operand is not None:
            self._add(node, "not", f"({operand})")

    def _constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, bool):
            self._add(node, "bool", "False" if node.value else "True")
        elif isinstance(node.value, int | float) and not isinstance(node.value, complex):
            self._add(node, "number", repr(node.value + 1))

    def _return(self, node: ast.Return) -> None:
        # `return None` is what a mutated function hands back; a function that
        # already returns nothing has no mutant here.
        if node.value is None or (
            isinstance(node.value, ast.Constant) and node.value.value is None
        ):
            return
        self._add(node.value, "return", "None")


def plant(source: str, *, path: str, lines: frozenset[int]) -> list[Mutant]:
    """Every mutant this mutator will plant in `source`, on the given lines.

    Deterministic and pure: the same file and the same covered lines give the
    same list in the same order, which is what makes the sample below repeatable
    and this gate incapable of flaking.
    """
    tree = ast.parse(source)
    planter = _Planter(
        path=path,
        raw=source.encode("utf-8"),
        starts=_line_starts(source),
        lines=lines,
        frozen=_frozen(tree),
    )
    for node in ast.walk(tree):
        planter.visit(node)
    planter.found.sort(key=lambda mutant: (mutant.line, mutant.start, mutant.operator))
    return planter.found


def graft(source: str, mutant: Mutant) -> str | None:
    """`source` with `mutant` applied, or None when the result will not compile.

    The compile check is the cheap guard that makes textual grafting safe: any
    span this mutator misreads produces a `SyntaxError` here and the mutant is
    dropped, rather than reaching the tests as a red that means nothing.
    """
    raw = source.encode("utf-8")
    grafted = (raw[: mutant.start] + mutant.after.encode("utf-8") + raw[mutant.end :]).decode(
        "utf-8",
    )
    try:
        compile(grafted, mutant.path, "exec")
    except SyntaxError:
        return None
    return grafted


def sample(mutants: list[Mutant], *, seed: str, cap: int) -> list[Mutant]:
    """Choose a bounded, reproducible sample of `mutants`.

    Seeded from the test module's path, so the same tree always plants the same
    mutants — a gate that picked afresh each run would be a coin toss dressed as
    a verdict, and CLAUDE.md's flake rules would be right to call it one.
    """
    if len(mutants) <= cap:
        return list(mutants)
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    chosen = random.Random(int.from_bytes(digest, "big")).sample(range(len(mutants)), cap)  # noqa: S311 — reproducible sampling, not cryptography
    return [mutants[index] for index in sorted(chosen)]


def node_id(test_module: str, context: str) -> str:
    """Turn one coverage context into the pytest node id that selects that test.

    They are not the same string and assuming they were is how the first draft of
    this gate scored every module 100%. `dynamic_context = test_function` names a
    test by its *importable* name — `test_dedupe.test_a_window_can_be_filled`, or
    `test_x.Suite.test_y` for a class — while pytest selects by path and `::`.
    Handed the coverage spelling, pytest exits 4 with "file or directory not
    found", and a runner that reads any non-zero exit as a kill reads that as the
    tests noticing. They noticed nothing; they never ran.

    Parametrised tests carry no case in the coverage name, so the node id here
    selects every case of them, which is the safe direction: more tests get their
    chance to kill the mutant, never fewer.
    """
    parts = [part for part in context.split(".") if part]
    stem = Path(test_module).stem
    if parts and parts[0] == stem:
        parts = parts[1:]
    return f"{test_module}::{'::'.join(parts)}" if parts else test_module


class Reach(NamedTuple):
    """Which product lines a test module executes, which tests reach each, at what cost."""

    lines: dict[str, dict[int, tuple[str, ...]]]
    costs: dict[str, float] = {}  # noqa: RUF012 — a NamedTuple field default, not shared mutable state

    def subject(self) -> str | None:
        """Name the product file this test module exercises most, or None.

        None is a finding, not a shrug: a test module none of whose tests reach
        a line of this repo's source has asserted nothing about it.
        """
        if not self.lines:
            return None
        return max(sorted(self.lines), key=lambda path: len(self.lines[path]))

    def cost(self, node: str) -> float:
        """Seconds one node id costs, rounded to `COST_GRAIN`, over all its cases.

        Rounded, and that is the whole point of this method rather than a dict
        lookup. Ordering the selection below by raw measured durations made this
        gate **flake**: the same tree, the same mutants, 13/20 then 14/20, because
        a suite whose tests all cost about a millisecond reorders on jitter and a
        different set of them gets picked. A grain coarser than the jitter and a
        tie-break on the name make the selection a function of the tree.
        """
        exact = self.costs.get(node)
        if exact is None:
            exact = sum(spent for name, spent in self.costs.items() if name.startswith(f"{node}["))
        return round(exact / COST_GRAIN) * COST_GRAIN

    def cheapest(self, tests: tuple[str, ...]) -> list[str]:
        """Choose the tests to run against one mutant: cheapest first, twice bounded.

        A test whose duration was never recorded is assumed free rather than
        expensive, so an unmeasured test is still tried; the wall-clock bound
        stops the selection whatever the assumption was worth.

        A test that rounds to free costs nothing against that bound, so a module
        of millisecond tests runs **all** of them against every mutant — which is
        what keeps a mutant from surviving merely because the test that would have
        killed it was left out of the selection.
        """
        ordered = sorted(tests, key=lambda name: (self.cost(name), name))
        chosen: list[str] = []
        spent = 0.0
        for name in ordered[:TESTS_PER_MUTANT]:
            if chosen and spent + self.cost(name) > TEST_SECONDS_PER_MUTANT:
                break
            chosen.append(name)
            spent += self.cost(name)
        return chosen

    def timeout(self, tests: list[str]) -> float:
        """How long those tests get before the mutant is called killed by timeout."""
        return max(TIMEOUT_FLOOR_S, TIMEOUT_FACTOR * sum(self.cost(name) for name in tests))


def _is_product(path: str) -> bool:
    """Whether a covered file is this repo's own source rather than a test or a dependency."""
    normalised = path.replace(os.sep, "/").removeprefix("./")
    return normalised.startswith(PRODUCT_ROOTS) and not normalised.startswith("tests/")


def read_durations(output: str) -> dict[str, float]:
    """Seconds per test id, from pytest's own `--durations=0` report.

    Read rather than measured: the coverage pass already runs every test once,
    and pytest already knows what each one cost. A line is `0.12s call
    tests/unit/test_x.py::test_y`; setup and teardown are summed in with the
    call, because a mutant run pays all three.
    """
    costs: dict[str, float] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != DURATION_FIELDS or not parts[0].endswith("s"):
            continue
        seconds, phase, name = parts
        if phase not in ("call", "setup", "teardown") or "::" not in name:
            continue
        try:
            costs[name] = costs.get(name, 0.0) + float(seconds.removesuffix("s"))
        except ValueError:
            continue
    return costs


def read_reach(report: dict[str, object], costs: dict[str, float] | None = None) -> Reach:
    """Turn a `coverage json --show-contexts` report into a `Reach`.

    Only lines carrying a non-empty context count. An empty context is
    import time — the module body ran because something imported it, not because
    a test exercised it — and counting those is exactly how an `assert True`
    module would acquire a subject it never touched.
    """
    lines: dict[str, dict[int, tuple[str, ...]]] = {}
    files = report.get("files")
    if not isinstance(files, dict):
        return Reach({}, costs or {})
    for path, entry in files.items():
        if not _is_product(str(path)) or not isinstance(entry, dict):
            continue
        contexts = entry.get("contexts")
        if not isinstance(contexts, dict):
            continue
        reached: dict[int, tuple[str, ...]] = {}
        for number, names in contexts.items():
            if not isinstance(names, list):
                continue
            tests = tuple(sorted(str(name).split("|")[0] for name in names if name))
            if tests:
                reached[int(str(number))] = tests
        if reached:
            lines[str(path).replace(os.sep, "/").removeprefix("./")] = reached
    return Reach(lines, costs or {})


class Verdict(NamedTuple):
    """What one test module's smoke found."""

    test_module: str
    subject: str | None
    planted: int
    run: int
    killed: int
    survivors: tuple[Mutant, ...]
    seconds: float
    floor: float

    @property
    def kill_rate(self) -> float:
        """Share of the mutants run that the tests noticed."""
        return 1.0 if self.run == 0 else self.killed / self.run

    @property
    def undecided(self) -> bool:
        """Whether the subject offered nothing to plant on the lines the tests reach.

        Not a pass by luck and not a failure either: `src/cti_daemon/telemetry.py`
        has no comparison, no boolean and no bare number on any line its tests
        execute, so there is no decision for a mutant to invert. A module cannot
        reach this state by writing weaker assertions — it is a property of the
        subject — so reding it would be a false red on a sound test module, which
        is the corpus sweep's one finding this rule exists for (#239).
        """
        return self.subject is not None and self.planted == 0

    @property
    def ok(self) -> bool:
        """Whether this module met the bar."""
        if self.subject is None:
            return False
        if self.undecided:
            return True
        return self.run > 0 and self.kill_rate >= self.floor

    @property
    def reason(self) -> str:
        """Why it failed, in the terms the remedy is written in."""
        if self.subject is None:
            return (
                "no subject: none of this module's tests executed a line of this repo's source, "
                "so there is nothing it can be said to have tested. If its subject is a shell "
                "script or an authored document, add it to NO_PYTHON_SUBJECT with the reason"
            )
        if self.undecided:
            return f"nothing to plant: no decision on the lines reached in {self.subject}"
        if self.run == 0:
            return f"no mutant reached a verdict in {self.seconds:.0f}s against {self.subject}"
        return (
            f"kill rate {self.kill_rate:.0%} against {self.subject} "
            f"({self.killed}/{self.run}) is below the {self.floor:.0%} floor"
        )

    def __str__(self) -> str:
        """One line per module, the shape a gate's reader scans."""
        mark = "ok" if self.ok else "RED"
        if self.undecided:
            return f"ok {self.test_module} subject={self.subject} {self.reason} {self.seconds:.1f}s"
        where = self.subject or "-"
        return (
            f"{mark} {self.test_module} subject={where} "
            f"killed={self.killed}/{self.run} planted={self.planted} "
            f"rate={self.kill_rate:.0%} floor={self.floor:.0%} {self.seconds:.1f}s"
        )


class Refusal(Exception):  # noqa: N818 — the repo names this shape `Refusal` (tools/worktree.py), and a refusal is not an error
    """The smoke could not run, which is not the same as a module failing it."""


# Every write this gate makes to a subject gets its own modification time, and
# this counter is what makes them distinct.
#
# Not tidiness. CPython validates a cached `.pyc` against its source's **mtime in
# whole seconds and its size in bytes**, and the two mutants this gate plants on
# one comparison — the negation and the boundary shift — differ by no bytes at
# all: `(missing < 0)` and `(missing > 0)` are the same length, written to the
# same file inside the same second. So the second run imported the first one's
# bytecode and delivered a verdict on a mutant that never executed. That is this
# gate flaking 13/20, 13/20, 12/20 over an unchanged tree, and the two survivors
# that moved were exactly such a pair. Stepping the clock forward two seconds per
# write makes a stale hit impossible rather than unlikely, and unlike a private
# `PYTHONPYCACHEPREFIX` per mutant — which also fixes it — it does not make every
# run recompile the whole import graph, measured at 10 s to 38 s per module.
_written = 0


def _stamp(target: Path) -> None:
    """Give `target` a modification time no other write in this run shares."""
    global _written  # noqa: PLW0603 — one counter for the process, and its scope is the point
    _written += 1
    when = time.time() + 2 * _written
    os.utime(target, (when, when))


# pytest's own exit codes, and the only two a mutant's fate may be read from.
# Everything else — interrupted, internal error, usage error, nothing collected —
# is a run that did not happen, and CLAUDE.md's rule for those is the #41 one: a
# check that could not run is not a check that passed, and here it would be worse
# than that, because "non-zero means the tests noticed" reads a usage error as a
# kill. That is exactly what the first draft of this gate did, and it scored every
# module in the repo 100%.
PYTEST_PASSED: Final = 0
PYTEST_FAILED: Final = 1


@contextlib.contextmanager
def grafted(root: Path, path: str, text: str):  # noqa: ANN201 — a context manager's own type adds nothing here
    """Hold `path` at `text` for the body, and put the original back whatever happens.

    The sidecar is written before the file is, so an interrupted run leaves the
    original recoverable by hand; the signal handlers cover the two ways an agent
    harness ends a run that a `finally` does not.
    """
    target = root / path
    original = target.read_text(encoding="utf-8")
    sidecar = root / RESTORE
    sidecar.write_text(json.dumps({"path": path, "text": original}), encoding="utf-8")
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}

    def _restore(number: int, frame: object) -> None:  # noqa: ARG001 — signal handler signature
        target.write_text(original, encoding="utf-8")
        sidecar.unlink(missing_ok=True)
        raise KeyboardInterrupt

    for number in previous:
        with contextlib.suppress(ValueError):
            signal.signal(number, _restore)
    try:
        target.write_text(text, encoding="utf-8")
        _stamp(target)
        yield
    finally:
        target.write_text(original, encoding="utf-8")
        _stamp(target)
        sidecar.unlink(missing_ok=True)
        for number, handler in previous.items():
            with contextlib.suppress(ValueError, TypeError):
                signal.signal(number, handler)


def _pytest(root: Path, argv: list[str], *, timeout: float) -> int | None:
    """Run pytest in `root` and return its exit code, or None if it did not finish."""
    try:
        done = subprocess.run(  # noqa: S603 — argv is built here from paths and constants
            [sys.executable, "-m", "pytest", *argv],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    return done.returncode


def measure(root: Path, test_module: str, *, timeout: float) -> Reach:
    """Run one test module under coverage and report which product lines its tests reached."""
    with tempfile.TemporaryDirectory() as workspace:
        rcfile = Path(workspace) / "coveragerc"
        rcfile.write_text(
            "[run]\nbranch = false\ndynamic_context = test_function\n"
            "source =\n    " + "\n    ".join(PRODUCT_ROOTS) + "\n",
            encoding="utf-8",
        )
        data = Path(workspace) / "cov.db"
        report = Path(workspace) / "cov.json"
        environment = {**os.environ, "COVERAGE_RCFILE": str(rcfile)}
        argv = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--data-file={data}",
            "-m",
            "pytest",
            "-n0",
            "-q",
            "-p",
            "no:cacheprovider",
            "--durations=0",
            "--durations-min=0",
            test_module,
        ]
        try:
            done = subprocess.run(  # noqa: S603 — argv built here from paths and constants
                argv,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as expired:
            message = f"{test_module} did not finish under coverage within {timeout:.0f}s"
            raise Refusal(message) from expired
        if done.returncode != 0:
            message = (
                f"{test_module} is not green on its own — mutation says nothing about a red "
                f"suite. pytest exit {done.returncode}:\n{done.stdout[-2000:]}"
            )
            raise Refusal(message)
        exported = subprocess.run(  # noqa: S603 — argv built here from paths and constants
            [
                sys.executable,
                "-m",
                "coverage",
                "json",
                f"--data-file={data}",
                "-o",
                str(report),
                "--show-contexts",
                "-q",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        if exported.returncode != 0 or not report.exists():
            message = f"coverage json failed for {test_module}: {exported.stderr.strip()}"
            raise Refusal(message)
        return read_reach(
            json.loads(report.read_text(encoding="utf-8")),
            read_durations(done.stdout),
        )


def smoke(  # noqa: PLR0913 — every bound this gate applies is a caller-visible knob
    root: Path,
    test_module: str,
    *,
    cap: int = CAP,
    floor: float = FLOOR,
    budget: float = BUDGET_S,
    collect: float = COLLECT_S,
) -> Verdict:
    """Plant a bounded sample of mutants in what `test_module` exercises, and judge it."""
    started = time.monotonic()
    reach = measure(root, test_module, timeout=collect)
    subject = reach.subject()
    if subject is None:
        return Verdict(test_module, None, 0, 0, 0, (), time.monotonic() - started, floor)

    covered = {
        line: tuple(node_id(test_module, context) for context in contexts)
        for line, contexts in reach.lines[subject].items()
    }
    source = (root / subject).read_text(encoding="utf-8")
    planted = plant(source, path=subject, lines=frozenset(covered))
    chosen = sample(planted, seed=test_module, cap=cap)

    deadline = time.monotonic() + budget
    killed = 0
    run = 0
    survivors: list[Mutant] = []
    for mutant in chosen:
        if time.monotonic() > deadline and run:
            break
        text = graft(source, mutant)
        if text is None:
            continue
        tests = reach.cheapest(covered[mutant.line])
        if not tests:
            continue
        with grafted(root, subject, text):
            code = _pytest(
                root,
                ["-n0", "-q", "-x", "-p", "no:cacheprovider", "--no-header", *tests],
                timeout=reach.timeout(tests),
            )
        run += 1
        # A timeout is a kill: the mutant changed what the code does so plainly
        # that the tests could not finish saying so. Every other non-zero code is
        # a run that did not happen, and reading it as a kill is how a gate scores
        # a vacuous suite full marks.
        if code is not None and code not in (PYTEST_PASSED, PYTEST_FAILED):
            message = (
                f"pytest exited {code} on {mutant} — that is not a verdict on the mutant. "
                f"The node ids it was given were: {tests}"
            )
            raise Refusal(message)
        if code == PYTEST_PASSED:
            survivors.append(mutant)
        else:
            killed += 1
    return Verdict(
        test_module,
        subject,
        len(planted),
        run,
        killed,
        tuple(survivors),
        time.monotonic() - started,
        floor,
    )


def _git(root: Path, argv: list[str]) -> str:
    done = subprocess.run(  # noqa: S603 — argv built here from constants and a ref
        ["git", *argv],  # noqa: S607 — git is resolved off PATH on purpose, as elsewhere in tools/
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout if done.returncode == 0 else ""


def is_test_module(path: str) -> bool:
    """Whether a path is one of this repo's test modules."""
    normalised = path.replace(os.sep, "/")
    return (
        normalised.startswith("tests/")
        and normalised.endswith(".py")
        and Path(normalised).name.startswith("test_")
    )


def in_scope(root: Path, base: str) -> list[str]:
    """List the test modules this landing adds or rewrites, committed and uncommitted.

    Both halves matter. The committed half is what `tools/land.py` will push; the
    uncommitted half is what an agent has in the tree while running `just fast`
    after an edit, which is where the gate is meant to be met first.
    """
    merge_base = _git(root, ["merge-base", "HEAD", base]).strip()
    found: set[str] = set()
    if merge_base:
        found.update(_git(root, ["diff", "--name-only", merge_base, "HEAD"]).split())
    for line in _git(root, ["status", "--porcelain", "--untracked-files=all"]).splitlines():
        entry = line[3:].strip()
        # A rename's porcelain line is `old -> new`; the new name is the subject.
        found.add(entry.split(" -> ")[-1] if " -> " in entry else entry)
    return sorted(name for name in found if is_test_module(name) and (root / name).exists())


def restore(root: Path) -> int:
    """Put back the file the sidecar names, and say what was done.

    The recovery half of the in-place mutation. An agent whose run was killed
    mid-mutant — a harness timeout, a `pkill`, a machine going down — has a
    modified tracked file it did not write, which is the one thing CLAUDE.md says
    to stop and report rather than reset. This is the mechanism that makes the
    difference: the sidecar names one file and carries its exact original bytes,
    so putting it back is not a guess.
    """
    sidecar = root / RESTORE
    if not sidecar.exists():
        print(f"nothing to restore: no {RESTORE}")  # noqa: T201
        return 0
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    path, text = record.get("path"), record.get("text")
    if not isinstance(path, str) or not isinstance(text, str):
        print(f"{RESTORE} is not a restore record; leaving it alone", file=sys.stderr)  # noqa: T201
        return 2
    target = root / path
    already = target.exists() and target.read_text(encoding="utf-8") == text
    target.write_text(text, encoding="utf-8")
    _stamp(target)
    sidecar.unlink()
    print(f"restored {path}" + (" (it was already intact)" if already else " from a live mutant"))  # noqa: T201
    return 0


def _judge(root: Path, targets: list[str], args: argparse.Namespace) -> tuple[int, int]:
    """Smoke each target, print its verdict, and count the reds and the refusals."""
    red = 0
    refused = 0
    for target in targets:
        if target in NO_PYTHON_SUBJECT:
            print(f"-- {target} exempt: {NO_PYTHON_SUBJECT[target]}", flush=True)  # noqa: T201
            continue
        try:
            verdict = smoke(
                root,
                target,
                cap=args.cap,
                floor=args.floor,
                budget=args.budget,
                collect=args.collect,
            )
        except Refusal as refusal:
            # One module's refusal is not the others': every target still gets a
            # verdict, and the exit code says a refusal happened at the end.
            refused += 1
            print(f"?? {target} could not run: {refusal}", file=sys.stderr)  # noqa: T201
            continue
        print(verdict, flush=True)  # noqa: T201 — stdout text IS this gate's output
        if not verdict.ok:
            red += 1
            print(f"    {verdict.reason}", file=sys.stderr)  # noqa: T201
            for survivor in verdict.survivors:
                print(f"    survived: {survivor}", file=sys.stderr)  # noqa: T201
    return red, refused


def main(argv: list[str] | None = None) -> int:
    """Smoke every test module in scope and print one line per module."""
    parser = argparse.ArgumentParser(
        description="Red a landing whose new tests do not notice the code changing.",
    )
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--base", default="origin/main", help="ref the landing is measured against")
    parser.add_argument("--paths", nargs="*", help="smoke these test modules instead of the diff")
    parser.add_argument("--cap", type=int, default=CAP)
    parser.add_argument("--floor", type=float, default=FLOOR)
    parser.add_argument("--budget", type=float, default=BUDGET_S)
    parser.add_argument("--collect", type=float, default=COLLECT_S)
    parser.add_argument(
        "--report",
        action="store_true",
        help="survey only: print every verdict and always exit 0",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help=f"put back the file {RESTORE} names, after an interrupted run",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    sidecar = root / RESTORE
    if args.restore:
        return restore(root)
    if sidecar.exists():
        print(  # noqa: T201 — stdout text IS this gate's output
            f"{RESTORE} is present: another smoke is running in this tree, or one was "
            f"interrupted mid-mutant and left a mutant in it. Wait, or run "
            f"`just mutation --restore` to put the file it names back, then run again.",
            file=sys.stderr,
        )
        return 2

    targets = args.paths or in_scope(root, args.base)
    if not targets:
        print(f"mutation smoke: no test module added or changed against {args.base}")  # noqa: T201
        return 0

    red, refused = _judge(root, targets, args)
    if refused and not args.report:
        return 2
    if red and not args.report:
        print(  # noqa: T201
            f"{red} test module(s) did not notice the code changing. Strengthen the "
            f"assertions that let the survivors above through — never weaken the floor.",
            file=sys.stderr,
        )
    return 1 if red and not args.report else 0


if __name__ == "__main__":
    raise SystemExit(main())
