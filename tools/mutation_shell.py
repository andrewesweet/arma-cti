"""The mutation smoke's shell arm: the same gate, for the tests whose subject is bash (#246).

`tools/mutation_smoke.py` asks whether a landing's new tests notice their subject
changing. It could only ask it of Python. Eleven test modules sat on
`NO_PYTHON_SUBJECT` — the named escape ADR-0064 decision 4 built — and eight of
them are not documents at all: they drive `spike/*.sh` as subprocesses and assert
on what the scripts do. Those eight were the largest ungated surface in the
repository's own tooling, and this is the arm that gates them.

Three things had to be solved that the Python arm gets for free.

## Which lines the tests executed

`coverage.py` has no bash. Bash has `set -x`, and bash reads `$BASH_ENV` before
running any non-interactive script — so a preamble in that file can turn xtrace
on for every script a test spawns, without editing one line of any of them.
`BASH_XTRACEFD` sends the trace to a private descriptor rather than to stderr,
which is what makes this invisible to tests that assert on a script's stderr, and
`PS4` carries `$BASH_SOURCE` and `$LINENO` so each traced line says which file and
which line ran. `BASH_ENV` is inherited, so a script that sources or spawns
another is traced through both.

Measured cost of the tracing, on this box: `tests/unit/test_bringup_guards.py`
14.88 s untraced against 14.75 s traced, `tests/unit/test_host_guard.py` 10.12 s
against 10.09 s, `tests/unit/test_pool_slots.py` 190.80 s against 190.64 s. It is
free, which is why it is switched on for **every** collect pass rather than only
for the modules expected to need it: a module that turns out to drive shell is
then already measured.

Attribution to individual tests — which the Python arm needs to run only the tests
that reach a mutant's line — comes from a one-hook pytest plugin that points
`CTI_SHELL_TRACE` at a per-test file in `pytest_runtest_setup`. The tests build
their subprocess environments with `dict(os.environ, ...)`, so the variable
reaches the script. A test that builds an environment from scratch instead is
simply not traced, and contributes no coverage; that direction is safe, because it
can only make this arm plant fewer mutants, never attribute a line to a test that
did not run it.

## Where a mutant may be written

Not in `spike/`. The Python arm mutates the real tree in place and defends the
window with a restore sidecar, and that is right for `src/` — but `spike/*.sh` is
read by a live Arma tier, and `just regress` from this same worktree may be
holding a slot while `just land` runs `just fast`. A mutant in `spike/run.sh` for
the two seconds a mutant run lasts is a corrupted in-world verdict, and no
sidecar repairs that after the fact.

So the shell arm works in a hardlinked stage: every tracked and every
not-ignored file gets an `os.link` into a temporary tree, which costs about a
tenth of a second for this repository's 7,168 files and no disk at all. A mutant
is written by **unlinking and re-creating** the staged file, never by writing
through the link, so the real file's inode is never touched — asserted in
`tests/unit/test_mutation_shell.py` rather than assumed. `Path.resolve()` on a
hardlink returns the path it was reached by, which is what makes
`tests/unit/conftest.py`'s `REPO = Path(__file__).resolve().parents[2]` name the
stage when pytest runs there, and therefore what makes the tests drive the staged
scripts.

The stage is also what proves the arm's own arrangement: before any mutant is
planted, the tests that reach the subject are run in the stage unmutated. A stage
that broke them would otherwise make every mutant look killed and score the
module 100% — a false green, which is the exact defect #239 records as having
scored every module in this repository full marks.

## What to change

The operator set is chosen the way ADR-0064 chose the Python one: for a low
equivalent-mutant rate rather than for coverage of the mutation-testing
literature. Strings are never touched, and neither is anything outside a
`[[ ]]`, `[ ]` or `(( ))` for the operators whose spelling is ambiguous — `=`
is assignment outside a test and `<` is a redirection, and mutating either is a
mutant about nothing. What remains is the arithmetic of decisions: which way a
test points, which way a list joins, whether a `!` is there, and what exit status
a script hands back.

`exit N` → `exit 0` is this arm's `return <expr>` → `return None`: a shell
script's return value *is* its exit status, and every one of these modules
asserts on it. `bash -n` over the grafted text is this arm's `compile()` — any
span this mutator misreads is a syntax error there and the mutant is dropped
rather than reaching the tests as a red that means nothing.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterator

# Where this repository's shell lives. A traced script outside these — a stub
# `tasklist.sh` a test wrote into `tmp_path`, most often — is somebody else's
# code and is never a subject, however much of it a test executed.
SHELL_ROOTS: Final = ("spike/", "tools/", ".claude/hooks/")

# The preamble bash reads before any non-interactive script, and the whole of
# this arm's instrumentation. Guarded on the variable so that a bash started for
# any other reason — a test's own stub, `git`'s hooks, the harness — pays
# nothing and writes nothing.
#
# `exec {fd}>>` asks bash for a free descriptor rather than naming one: the
# scripts under test open their own (`exec 9>` for `flock` in `spike/slots.sh`),
# and a fixed number here would fight them.
#
# `${BASH_SOURCE:-}` and not `${BASH_SOURCE}`: `BASH_SOURCE` has no element 0 in
# a `bash -c` body, so under `set -u` — which is what `just`'s recipe shell is,
# `["bash", "-euo", "pipefail", "-c"]` — expanding `PS4` aborts the shell with
# `BASH_SOURCE: unbound variable` before the recipe runs a command. Tracing then
# reds every test that shells into a `set -u` bash, for a reason belonging to
# this harness rather than to the module under measurement (#324: it took
# `tools/generate_seats.py` off the mutation gate entirely, with the gate
# reporting `?? could not run` rather than refusing). The empty source that the
# default yields is dropped by `read_traces`, which only keeps this repository's
# own scripts.
TRACE_PREAMBLE: Final = """\
if [ -n "${CTI_SHELL_TRACE:-}" ]; then
  exec {__cti_trace_fd}>>"$CTI_SHELL_TRACE"
  BASH_XTRACEFD=$__cti_trace_fd
  PS4='+@${BASH_SOURCE:-}@${LINENO}@ '
  set -x
fi
"""

# One hook, and the reason it is a plugin rather than a `conftest.py` addition:
# the collect pass runs the repository's own test module unchanged, and a
# `conftest.py` edit would be a change to the tree under measurement.
TRACE_PLUGIN: Final = '''\
"""Point each test's shell trace at a file of its own (mutation smoke, #246)."""

import hashlib
import os
import pathlib

DIR = pathlib.Path(os.environ["CTI_SHELL_TRACE_DIR"])


def pytest_runtest_setup(item):
    """Name this test's trace file, and record which test it belongs to."""
    name = hashlib.blake2b(item.nodeid.encode("utf-8"), digest_size=8).hexdigest()
    with (DIR / "index.txt").open("a", encoding="utf-8") as index:
        index.write(f"{name}\\t{item.nodeid}\\n")
    os.environ["CTI_SHELL_TRACE"] = str(DIR / f"{name}.trace")
'''

# `+@/abs/path/spike/run.sh@528@ exit 1`. Bash replicates PS4's *first*
# character once per level of indirection, so the leading `+` repeats and the
# rest of the prompt does not.
TRACED: Final = re.compile(r"^\++@(?P<source>[^@]*)@(?P<line>\d+)@ ")

# Negating a test: the strongest single change to a decision that was taken.
_FLIP: Final = {
    "-eq": "-ne",
    "-ne": "-eq",
    "-lt": "-ge",
    "-le": "-gt",
    "-gt": "-le",
    "-ge": "-lt",
    "-z": "-n",
    "-n": "-z",
    "==": "!=",
    "!=": "==",
    "=": "!=",
    "<": ">=",
    ">": "<=",
    "<=": ">",
    ">=": "<",
}

# Shifting a test by one: the operator still points the same way, the boundary
# moves. A negated `-gt` usually blows the script up and any assertion at all
# kills it; this measures whether the tests pinned the *edge*. Only the ordering
# operators have such a neighbour — there is nothing one step from `-eq`.
_SHIFT: Final = {
    "-lt": "-le",
    "-le": "-lt",
    "-gt": "-ge",
    "-ge": "-gt",
    "<": "<=",
    "<=": "<",
    ">": ">=",
    ">=": ">",
}

# The operators that mean a comparison only inside a test or an arithmetic
# expression. `=` is assignment and `<` is a redirection everywhere else, and a
# mutant on either of those is a mutant about nothing — or a syntax error, which
# `bash -n` would drop after the budget had already been spent on it.
_BRACKETED_ONLY: Final = frozenset({"=", "==", "!=", "<", ">", "<=", ">="})

# Longest first, so `<=` is never read as `<` and `-ne` never as `-n`.
_OPERATORS: Final = tuple(sorted(set(_FLIP) | set(_SHIFT), key=len, reverse=True))

_EXIT: Final = re.compile(r"\b(exit|return)[ \t]+([1-9][0-9]*)(?![0-9])")
_NEGATION: Final = re.compile(r"(?:(?<=^)|(?<=[\s(]))![ \t]+")
_INTEGER: Final = re.compile(r"(?<![\w$.-])([0-9]+)(?![\w.])")

# Where a bracketed context opens and closes. `[` is deliberately absent from the
# openers as a bare character: it is matched as a word so that a glob or an array
# subscript is not read as a test.
_OPENERS: Final = (("((", "))"), ("[[", "]]"), ("[ ", " ]"))


class Edit(NamedTuple):
    """One byte-span replacement this mutator offers, before it is a `Mutant`.

    The record type stays in `tools/mutation_smoke.py`, which owns the verdict
    and the report; this module owns spans and operators. `Mutant(subject, *edit)`
    is the whole of the seam.
    """

    line: int
    operator: str
    start: int
    end: int
    before: str
    after: str


def code_mask(text: str) -> list[bool]:
    """Mark every character of one line that is shell code rather than data.

    False inside single or double quotes, at an escaped character, and from an
    unquoted `#` to the end. A comparison operator inside a message is not a
    decision the script takes — mutating one changes what a script *says* and
    nothing about what it *does*, and every such mutant would survive and have to
    be paid for out of the floor.
    """
    mask = [True] * len(text)
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            mask[index] = False
            if char == "\\" and quote == '"' and index + 1 < len(text):
                mask[index + 1] = False
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char == "\\" and index + 1 < len(text):
            mask[index] = mask[index + 1] = False
            index += 2
            continue
        if char in "'\"":
            quote = char
            mask[index] = False
            index += 1
            continue
        if char == "#" and (index == 0 or text[index - 1].isspace()):
            for rest in range(index, len(text)):
                mask[rest] = False
            return mask
        index += 1
    return mask


def bracketed(text: str, mask: list[bool]) -> list[tuple[int, int]]:
    """Span of every `[[ ]]`, `[ ]` and `(( ))` that opens and closes on this line.

    A test spanning more than one line contributes nothing, which is the safe
    direction: this arm plants fewer mutants rather than mutants it cannot place.
    """
    spans: list[tuple[int, int]] = []
    for opener, closer in _OPENERS:
        start = 0
        while True:
            at = text.find(opener, start)
            if at < 0 or not mask[at]:
                if at < 0:
                    break
                start = at + 1
                continue
            end = text.find(closer, at + len(opener))
            if end < 0 or not mask[end]:
                break
            spans.append((at + len(opener), end))
            start = end + len(closer)
    return spans


def _inside(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(low <= start and end <= high for low, high in spans)


def _word(text: str, start: int, end: int) -> bool:
    """Whether the span stands alone rather than being part of a longer token."""
    before = text[start - 1] if start else " "
    after = text[end] if end < len(text) else " "
    return before in " \t(" and after in " \t)"


class _Planter:
    """Collects the mutants one executed line of one script offers."""

    def __init__(self, text: str, offset: int, line: int) -> None:
        self.text = text
        self.offset = offset
        self.line = line
        self.mask = code_mask(text)
        self.spans = bracketed(text, self.mask)
        self.found: list[Edit] = []

    def _add(self, start: int, end: int, operator: str, after: str) -> None:
        self.found.append(
            Edit(
                self.line,
                operator,
                self.offset + start,
                self.offset + end,
                self.text[start:end],
                after,
            ),
        )

    def _spans_of(self, token: str) -> Iterator[tuple[int, int]]:
        start = 0
        while True:
            at = self.text.find(token, start)
            if at < 0:
                return
            end = at + len(token)
            start = at + 1
            if not all(self.mask[at:end]):
                continue
            if not _word(self.text, at, end):
                continue
            if token in _BRACKETED_ONLY and not _inside(self.spans, at, end):
                continue
            # `-eq` and friends are only a comparison inside a test either; a
            # bare `-n` is `sed -n`, and mutating that says nothing.
            if token.startswith("-") and not _inside(self.spans, at, end):
                continue
            yield at, end

    def comparisons(self) -> None:
        """Flip every test operator, and shift the ordering ones by one."""
        taken: list[tuple[int, int]] = []
        for token in _OPERATORS:
            for at, end in self._spans_of(token):
                # Longest-first means `<=` is claimed before `<` is looked at.
                if any(low < end and at < high for low, high in taken):
                    continue
                taken.append((at, end))
                for operator, table in (("compare", _FLIP), ("boundary", _SHIFT)):
                    replacement = table.get(token)
                    if replacement is not None:
                        self._add(at, end, operator, replacement)

    def lists(self) -> None:
        """`&&` becomes `||` and `||` becomes `&&`.

        Valid both between commands and inside `[[ ]]`, and a decision either
        way: `[[ -n "$pid" ]] && kill "$pid"` becomes a script that kills what is
        not there, and `cmd || fail ...` becomes one that fails when it worked.
        """
        for token, replacement in (("&&", "||"), ("||", "&&")):
            start = 0
            while True:
                at = self.text.find(token, start)
                if at < 0:
                    break
                end = at + len(token)
                start = end
                if all(self.mask[at:end]):
                    self._add(at, end, "boolop", replacement)

    def negations(self) -> None:
        """Drop a `!` that negates a command or a test."""
        for match in _NEGATION.finditer(self.text):
            if all(self.mask[match.start() : match.end()]):
                self._add(match.start(), match.end(), "not", "")

    def statuses(self) -> None:
        """`exit 1` becomes `exit 0`, and so does `return 1`.

        This arm's strongest operator, and the reason is the same one ADR-0064
        gives for `return <expr>` → `None`: a script's exit status is its return
        value, and every module on this arm asserts on one.
        """
        for match in _EXIT.finditer(self.text):
            if all(self.mask[match.start() : match.end()]):
                self._add(match.start(), match.end(), "status", f"{match.group(1)} 0")

    def numbers(self) -> None:
        """Offset an integer inside a test or an arithmetic expression by one.

        Two freezes, and both are ADR-0064's rule about opaque configuration in
        bash's spelling. A number inside `${...}` is a parameter default —
        `${CTI_HOLD_HC:-0}` is `def f(hold_hc=0)`, and the Python arm has never
        touched one — and every such mutant measured here survived. A line
        carrying `=~` has its integers inside a regular expression, where `[0-9]`
        becoming `[1-9]` is not a decision the script takes.
        """
        if "=~" in self.text:
            return
        for match in _INTEGER.finditer(self.text):
            at, end = match.span(1)
            if all(self.mask[at:end]) and _inside(self.spans, at, end) and not self._expanded(at):
                self._add(at, end, "number", str(int(match.group(1)) + 1))

    def _expanded(self, at: int) -> bool:
        """Whether this position sits inside a `${...}` parameter expansion."""
        opened = self.text.rfind("${", 0, at)
        return opened >= 0 and self.text.find("}", opened) > at

    def collect(self) -> list[Edit]:
        """Every mutant this line offers, in a stable order."""
        self.comparisons()
        self.lists()
        self.negations()
        self.statuses()
        self.numbers()
        return sorted(self.found, key=lambda edit: (edit.start, edit.operator))


def plant(source: str, *, lines: frozenset[int]) -> list[Edit]:
    """Every mutant this mutator will plant in `source`, on the given lines.

    Deterministic and pure, for `tools/mutation_smoke.py`'s reason: the same
    script and the same executed lines give the same list in the same order,
    which is what makes the bounded sample above it repeatable and this gate
    incapable of flaking.
    """
    found: list[Edit] = []
    offset = 0
    for number, text in enumerate(source.splitlines(keepends=True), start=1):
        if number in lines:
            found.extend(_Planter(text.rstrip("\n"), offset, number).collect())
        offset += len(text.encode("utf-8"))
    return sorted(found, key=lambda edit: (edit.line, edit.start, edit.operator))


def parses(text: str) -> bool:
    """Whether bash will accept the grafted script.

    `bash -n` is this arm's `compile()`: it reads the script and reports syntax
    errors without running a line of it, so any span this mutator misreads is
    dropped here rather than reaching the tests as a red that means nothing.
    """
    bash = shutil.which("bash") or "/bin/bash"
    done = subprocess.run(  # noqa: S603 — a fixed argv, with the script on stdin
        [bash, "-n"],
        input=text,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return done.returncode == 0


def is_shell_subject(path: str) -> bool:
    """Whether a traced script is one of this repository's own."""
    normalised = path.replace(os.sep, "/").removeprefix("./")
    return normalised.startswith(SHELL_ROOTS) and normalised.endswith(".sh")


def trace_environment(directory: Path) -> dict[str, str]:
    """Write the tracing assets into `directory` and return the environment for them.

    `PYTHONPATH` carries the plugin rather than the repository's `conftest.py`,
    because the collect pass runs the module under measurement unchanged.
    """
    preamble = directory / "bash-env.sh"
    preamble.write_text(TRACE_PREAMBLE, encoding="utf-8")
    (directory / "cti_shell_trace.py").write_text(TRACE_PLUGIN, encoding="utf-8")
    traces = directory / "traces"
    traces.mkdir(exist_ok=True)
    existing = os.environ.get("PYTHONPATH")
    return {
        "BASH_ENV": str(preamble),
        "CTI_SHELL_TRACE_DIR": str(traces),
        "PYTHONPATH": f"{directory}{os.pathsep}{existing}" if existing else str(directory),
    }


def read_traces(directory: Path, root: Path) -> dict[str, dict[int, tuple[str, ...]]]:
    """Which line of which script each test executed, out of the xtrace files.

    The index the plugin wrote is what turns a trace file back into the pytest
    node id that selects the test — the same job `node_id` does for a coverage
    context in the Python arm, and this one needs no translation because the
    plugin recorded the node id itself.
    """
    traces = directory / "traces"
    index = traces / "index.txt"
    if not index.exists():
        return {}
    names: dict[str, str] = {}
    for row in index.read_text(encoding="utf-8").splitlines():
        digest, _, node = row.partition("\t")
        if node:
            names[digest] = node
    reached: dict[str, dict[int, set[str]]] = {}
    for digest, node in names.items():
        trace = traces / f"{digest}.trace"
        if not trace.exists():
            continue
        for row in trace.read_text(encoding="utf-8", errors="replace").splitlines():
            match = TRACED.match(row)
            if match is None:
                continue
            source = Path(match.group("source"))
            try:
                relative = source.resolve().relative_to(root).as_posix()
            except (ValueError, OSError):
                continue
            if not is_shell_subject(relative):
                continue
            reached.setdefault(relative, {}).setdefault(int(match.group("line")), set()).add(node)
    return {
        path: {line: tuple(sorted(nodes)) for line, nodes in sorted(lines.items())}
        for path, lines in sorted(reached.items())
    }


def _staged_paths(root: Path) -> list[str]:
    """Every file `git` will admit to: tracked, plus untracked and not ignored.

    Not `cp -al` of the whole tree, because that would carry `.git`, the virtual
    environment and every build artefact — and an untracked *new* test module is
    exactly what a landing has in the tree when it first meets this gate, so
    "tracked only" is not the right set either.
    """
    done = subprocess.run(
        ["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"],  # noqa: S607 — git off PATH, as elsewhere in tools/
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return []
    return [name for name in done.stdout.split("\0") if name]


@contextlib.contextmanager
def staged(root: Path) -> Iterator[Path]:
    """Hardlink the tree into a temporary stage, where a mutant can be written safely.

    Hardlinks rather than copies for two reasons, and only the first is cost.
    The second is `Path.resolve()`: a symlink farm would resolve back to the real
    tree and `tests/unit/conftest.py` would compute `REPO` as the real
    repository, so the tests would drive the real scripts and the stage would be
    an expensive no-op. A hardlink has no target to resolve.

    Writing *through* a hardlink would edit the real file, so nothing here ever
    does; `graft` unlinks first. That is the whole safety argument, and
    `tests/unit/test_mutation_shell.py` asserts it against the real inode.
    """
    with tempfile.TemporaryDirectory(prefix="cti-mutation-stage-") as workspace:
        stage = Path(workspace) / "tree"
        made: set[Path] = set()
        for name in _staged_paths(root):
            source = root / name
            if not source.is_file():
                continue
            target = stage / name
            if target.parent not in made:
                target.parent.mkdir(parents=True, exist_ok=True)
                made.add(target.parent)
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
        yield stage


@contextlib.contextmanager
def graft(stage: Path, path: str, text: str) -> Iterator[None]:
    """Hold the staged `path` at `text` for the body, then put the staged original back.

    Unlink and re-create, never a write through the link: the staged file shares
    its inode with the real one, and writing into it would edit `spike/run.sh`
    under a live tier — the thing this arm exists to avoid.
    """
    target = stage / path
    original = target.read_text(encoding="utf-8")
    mode = target.stat().st_mode

    def _write(body: str) -> None:
        target.unlink()
        target.write_text(body, encoding="utf-8")
        target.chmod(mode)

    _write(text)
    try:
        yield
    finally:
        _write(original)
