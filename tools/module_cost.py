"""Measure one test module's serial wall and CPU, with machine load beside it (#685).

#447's family — #455, #456, #457 — each ask for serial before-and-after wall and
CPU for one test module in isolation, with machine load and foreign gate-process
count stated, and the project's command surface offered no way to take that
figure. `just unit` runs the whole tier in parallel, and `gate_clock` records
only its whole-tier wall, so one module's own serial wall and CPU had no
reading anywhere; a dispatched session's permission surface refuses bare
`uv run pytest` and
`/usr/bin/time`, which is how #457's implementer could not take the figure at
all and then claimed the cost anyway. This is the measurement as a recipe, so
the figure is reproducible by name rather than by remembering an invocation —
#351's argument for minting the ADR review-queue count.

Serial is the point, not an option: `-n auto` durations are inflated by
contention badly enough that #456's issue warns they "will send you to the wrong
tests". The pytest invocation carries `-n0` explicitly, which overrides the
`-n auto` in pyproject's addopts (addopts are prepended, so a later `-n` wins),
and the row says `mode=serial` so a reader cannot mistake a contended figure for
an isolated one.

Every number is a real reading, and a reading that cannot be taken is `null`
rather than a guess — the same rule `gate_clock`'s recorder holds. That rule
reaches the test counts too: a junit report the child did not write, or wrote
in a form that will not parse, leaves every count `null` with `readable_junit`
naming the absence in the row, never four zeroes that read as a fact. Load and
the foreign gate-process count are read before the child starts and after it
exits: `/proc/loadavg` for the 1-minute load, and `gate_clock`'s
`foreign_gate_processes` for the `pytest|cargo test` count. Read outside the
child's lifetime because this tool's own child is itself a pytest — inside that
window the tool would count itself. CPU is the child's own `getrusage
RUSAGE_CHILDREN` delta, user and system split, so no `/usr/bin/time` is
involved and no shell arrives between.

The run is bounded at both seams. The recipe's `timeout` is the outer bound
ADR-0049 requires of every `uv run`; inside it, the child pytest carries its
own shorter deadline, and a child that reaches it is killed and reported as
`timed_out` — exit 124, counts `null` — because a timed-out run is not a
measurement, and never becomes one by waiting longer.

The module path is the only argument. A red module is still a measurement: the
row prints whatever the run produced and the child's exit code is propagated,
so a red is visible without the figure being withheld.
"""

from __future__ import annotations

import argparse
import os
import resource
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# tools/ holds standalone scripts rather than an importable package, so a
# sibling import needs the script's own directory on the path — the same device
# `timeline.py` uses to reach `telemetry_log`. Placed before the import it
# enables, which is why the import below sits apart from the block above.
sys.path.insert(0, str(Path(__file__).parent))

from gate_clock import foreign_gate_processes, read_loadavg

REPO = Path(__file__).resolve().parents[1]

SERIAL_FLAG = "-n0"

# The child's own deadline, inside the recipe's shell `timeout` (default 1800s
# there): a whole `just unit` tier records 103s, so 1500s is several whole
# tiers and every legitimate module is far inside it, while a hung module is
# killed instead of holding the caller. `--child-timeout-seconds` overrides.
CHILD_TIMEOUT_S = 1500.0


@dataclass(frozen=True)
class Sample:
    """One serial run's figures. A reading that could not be taken is `None`.

    The test counts are `None` as a set when the junit report is absent,
    malformed or unreadable — `junit_readable` is the row's name for that —
    because a zero there would read as a fact. `timed_out` marks a child
    killed at its deadline: the wall and CPU up to the kill are real, but the
    run is not a measurement and nothing downstream may read it as one.
    """

    module: str
    wall_s: float
    cpu_user_s: float
    cpu_sys_s: float
    load_start: float | None
    load_end: float | None
    foreign_start: int | None
    foreign_end: int | None
    collected: int | None
    failed: int | None
    errored: int | None
    skipped: int | None
    junit_readable: bool
    exit_code: int
    timed_out: bool = False


def build_pytest_argv(python: str, module: str, junit_xml: Path) -> list[str]:
    """Build the child's argv: serial, and counted through junit.

    `-n0` comes after pyproject's addopts, so it wins over `-n auto` — the
    serial guarantee lives here and nowhere else. junit-xml carries the
    collected and failed counts, which pytest's summary line would have to be
    parsed to get and which a passing run with zero tests must still be able
    to distinguish.
    """
    return [
        python,
        "-m",
        "pytest",
        module,
        SERIAL_FLAG,
        f"--junit-xml={junit_xml}",
        "-p",
        "no:cacheprovider",
    ]


def junit_counts(xml_path: Path) -> tuple[int, int, int, int] | None:
    """Read `(collected, failed, errored, skipped)`, or `None` when the report is unreadable.

    The child writes the file itself; a missing, malformed or truncated report
    means the counts are unknown, and unknown is `None` — never four zeroes,
    which would read as a fact a reader could quote. The row's
    `readable_junit` field carries this answer beside the counts.
    """
    try:
        root = ET.parse(xml_path).getroot()  # noqa: S314 — the child's own report, not untrusted input
    except (OSError, ET.ParseError):
        return None
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return None
    try:
        return (
            int(suite.get("tests", "0")),
            int(suite.get("failures", "0")),
            int(suite.get("errors", "0")),
            int(suite.get("skipped", "0")),
        )
    except ValueError:
        return None


def format_load(load: float | None) -> str:
    """Format one load reading, `null` when it could not be taken."""
    return "null" if load is None else f"{load:.2f}"


def format_count(count: int | None) -> str:
    """Format one whole-number reading, `null` when it could not be taken."""
    return "null" if count is None else str(count)


def format_row(sample: Sample) -> str:
    """Render the row a reader quotes into an issue: one figure per line, serial named.

    The `mode=serial` line is criterion 2's own statement — a figure pasted
    without it cannot prove it was taken in isolation — and `readable_junit`
    says whether the counts are readings or an absence.
    """
    return (
        f"module={sample.module}\n"
        f"mode=serial pytest {SERIAL_FLAG} (xdist workers disabled)\n"
        f"wall={sample.wall_s:.2f}s cpu={sample.cpu_user_s + sample.cpu_sys_s:.2f}s"
        f" (user {sample.cpu_user_s:.2f}s + sys {sample.cpu_sys_s:.2f}s)\n"
        f"load_1m={format_load(sample.load_start)} -> {format_load(sample.load_end)}\n"
        f"foreign_gate_processes={format_count(sample.foreign_start)}"
        f" -> {format_count(sample.foreign_end)}\n"
        f"tests={format_count(sample.collected)} failed={format_count(sample.failed)}"
        f" errored={format_count(sample.errored)} skipped={format_count(sample.skipped)}"
        f" exit={sample.exit_code} readable_junit={'yes' if sample.junit_readable else 'no'}"
    )


def measure(
    module: str,
    *,
    root: Path = REPO,
    python: str = sys.executable,
    proc: Path = Path("/proc"),
    child_timeout_s: float = CHILD_TIMEOUT_S,
) -> Sample:
    """Run `module` serially once and return its figures.

    Load and the foreign count are read outside the child's lifetime at both
    ends, because this tool's own child is a pytest and would otherwise count
    itself; wall is `time.monotonic`, the kernel's monotonic clock, which does
    not step under NTP the way a realtime reading would; CPU is the waited-for
    children's `getrusage` delta, which is exactly the child's own user and
    system time when this call is the only thing spawning between the two reads.
    `proc` resolves where the kernel's files are read from, so a test can stage
    them — the same shape `gate_clock`'s readers expose. A child still running
    at `child_timeout_s` is killed: the returned sample is `timed_out` with
    exit 124 and no counts, because a hung module is a synchronisation finding,
    not a longer wait.
    """
    fd, junit_name = tempfile.mkstemp(suffix="-module-cost-junit.xml")
    os.close(fd)
    junit_xml = Path(junit_name)
    # This tool is usually launched from inside a pytest run — a gate, a suite —
    # whose own pytest coordination variables (`PYTEST_XDIST_WORKER` among them)
    # would otherwise reach the child through the inherited environment and put
    # a module that is not running under xdist into a worker it did not ask
    # for. The child's arrangement is this tool's `-n0`, nothing inherited.
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    try:
        argv = build_pytest_argv(python, module, junit_xml)
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        load_start = read_loadavg(proc / "loadavg")
        foreign_start = foreign_gate_processes(proc)
        started = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 — argv is built here, no shell
                argv,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=child_timeout_s,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            return_code = 124
        else:
            timed_out = False
            return_code = completed.returncode
        wall_s = time.monotonic() - started
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        load_end = read_loadavg(proc / "loadavg")
        foreign_end = foreign_gate_processes(proc)
        # A killed child's report is at best a partial record of a run that
        # never finished, so it is not read at all: the counts stay unknown.
        counts = None if timed_out else junit_counts(junit_xml)
    finally:
        junit_xml.unlink(missing_ok=True)
    collected, failed, errored, skipped = counts if counts is not None else (None, None, None, None)
    return Sample(
        module=module,
        wall_s=wall_s,
        cpu_user_s=after.ru_utime - before.ru_utime,
        cpu_sys_s=after.ru_stime - before.ru_stime,
        load_start=load_start,
        load_end=load_end,
        foreign_start=foreign_start,
        foreign_end=foreign_end,
        collected=collected,
        failed=failed,
        errored=errored,
        skipped=skipped,
        junit_readable=counts is not None,
        exit_code=return_code,
        timed_out=timed_out,
    )


def main(argv: list[str] | None = None) -> int:
    """Print one row for one module and propagate the child's exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("module", help="the test module's path, as pytest takes it")
    parser.add_argument(
        "--child-timeout-seconds",
        type=float,
        default=CHILD_TIMEOUT_S,
        help="deadline for the child pytest; a child still running at it is killed",
    )
    args = parser.parse_args(argv)
    sample = measure(args.module, child_timeout_s=args.child_timeout_seconds)
    print(format_row(sample))  # noqa: T201 — the row is this CLI's public result
    if sample.timed_out:
        print(  # noqa: T201 — the timeout note is this CLI's public result
            f"note: the child was killed at its {args.child_timeout_seconds:g}s deadline;"
            " a timed-out run is not a measurement"
        )
    elif sample.exit_code != 0:
        print(  # noqa: T201 — the red note is this CLI's public result
            "note: the module is red; a red module is still a measurement,"
            " but the figure is not an isolated green baseline"
        )
    return sample.exit_code


if __name__ == "__main__":
    sys.exit(main())
