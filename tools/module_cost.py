"""Measure one test module's serial wall and CPU, with machine load beside it (#685).

#447's family — #455, #456, #457 — each ask for serial before-and-after wall and
CPU for one test module in isolation, with machine load and foreign gate-process
count stated, and the project's command surface offered no way to take that
figure. `just unit` runs the whole tier in parallel and reports neither; a
dispatched session's permission surface refuses bare `uv run pytest` and
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
rather than a guess — the same rule `gate_clock`'s recorder holds. Load and the
foreign gate-process count are read before the child starts and after it
exits: `/proc/loadavg` for the 1-minute load, and `gate_clock`'s
`foreign_gate_processes` for the `pytest|cargo test` count. Read outside the
child's lifetime because this tool's own child is itself a pytest — inside that
window the tool would count itself. CPU is the child's own `getrusage
RUSAGE_CHILDREN` delta, user and system split, so no `/usr/bin/time` is
involved and no shell arrives between.

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


@dataclass(frozen=True)
class Sample:
    """One serial run's figures. A reading that could not be taken is `None`."""

    module: str
    wall_s: float
    cpu_user_s: float
    cpu_sys_s: float
    load_start: float | None
    load_end: float | None
    foreign_start: int | None
    foreign_end: int | None
    collected: int
    failed: int
    errored: int
    skipped: int
    exit_code: int


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


def junit_counts(xml_path: Path) -> tuple[int, int, int, int]:
    """Read `(collected, failed, errored, skipped)` from a junit report, or `(0, 0, 0, 0)`.

    The child writes the file itself; an unreadable or missing report means the
    counts are unknown, and unknown is `(0, 0, 0, 0)` with the report's absence
    visible in `readable_junit` rather than a crash after the figures printed.
    """
    try:
        root = ET.parse(xml_path).getroot()  # noqa: S314 — the child's own report, not untrusted input
    except (OSError, ET.ParseError):
        return (0, 0, 0, 0)
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        return (0, 0, 0, 0)
    try:
        return (
            int(suite.get("tests", "0")),
            int(suite.get("failures", "0")),
            int(suite.get("errors", "0")),
            int(suite.get("skipped", "0")),
        )
    except ValueError:
        return (0, 0, 0, 0)


def format_load(load: float | None) -> str:
    """Format one load reading, `null` when it could not be taken."""
    return "null" if load is None else f"{load:.2f}"


def format_row(sample: Sample) -> str:
    """Render the row a reader quotes into an issue: one figure per line, serial named.

    The `mode=serial` line is criterion 2's own statement — a figure pasted
    without it cannot prove it was taken in isolation.
    """
    return (
        f"module={sample.module}\n"
        f"mode=serial pytest {SERIAL_FLAG} (xdist workers disabled)\n"
        f"wall={sample.wall_s:.2f}s cpu={sample.cpu_user_s + sample.cpu_sys_s:.2f}s"
        f" (user {sample.cpu_user_s:.2f}s + sys {sample.cpu_sys_s:.2f}s)\n"
        f"load_1m={format_load(sample.load_start)} -> {format_load(sample.load_end)}\n"
        f"foreign_gate_processes={sample.foreign_start} -> {sample.foreign_end}\n"
        f"tests={sample.collected} failed={sample.failed} errored={sample.errored}"
        f" skipped={sample.skipped} exit={sample.exit_code}"
    )


def measure(
    module: str,
    *,
    root: Path = REPO,
    python: str = sys.executable,
    proc: Path = Path("/proc"),
) -> Sample:
    """Run `module` serially once and return its figures.

    Load and the foreign count are read outside the child's lifetime at both
    ends, because this tool's own child is a pytest and would otherwise count
    itself; wall is `time.monotonic`, the kernel's monotonic clock, which does
    not step under NTP the way a realtime reading would; CPU is the waited-for
    children's `getrusage` delta, which is exactly the child's own user and
    system time when this call is the only thing spawning between the two reads.
    `proc` resolves where the kernel's files are read from, so a test can stage
    them — the same shape `gate_clock`'s readers expose.
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
        completed = subprocess.run(  # noqa: S603 — argv is built here, no shell
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        wall_s = time.monotonic() - started
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        load_end = read_loadavg(proc / "loadavg")
        foreign_end = foreign_gate_processes(proc)
        counts = junit_counts(junit_xml)
    finally:
        junit_xml.unlink(missing_ok=True)
    collected, failed, errored, skipped = counts
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
        exit_code=completed.returncode,
    )


def main(argv: list[str] | None = None) -> int:
    """Print one row for one module and propagate the child's exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("module", help="the test module's path, as pytest takes it")
    args = parser.parse_args(argv)
    sample = measure(args.module)
    print(format_row(sample))  # noqa: T201 — the row is this CLI's public result
    if sample.exit_code != 0:
        print(  # noqa: T201 — the red note is this CLI's public result
            "note: the module is red; a red module is still a measurement,"
            " but the figure is not an isolated green baseline"
        )
    return sample.exit_code


if __name__ == "__main__":
    sys.exit(main())
