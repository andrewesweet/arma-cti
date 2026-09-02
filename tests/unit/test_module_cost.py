"""Tests for `tools/module_cost.py` — one test module's serial wall and CPU (#685).

The staged-process end-to-end tests run real pytest children in `tmp_path`, so
they are the slower half of the module's coverage; everything they prove about
the serial flag is proven against a `pyproject.toml` that sets `-n auto`, which
is the exact arrangement the recipe must override.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

load_tool("gate_clock")  # the sibling `module_cost` imports, registered first
module_cost = load_tool("module_cost")

# A module whose one test records whether it ran under an xdist worker. With
# `-n0` winning over addopts, no worker exists and the marker is absent.
WORKER_PROBE = """
import os, pathlib

def test_worker():
    pathlib.Path(os.environ["MODULE_COST_WORKER_OUT"]).write_text(
        os.environ.get("PYTEST_XDIST_WORKER", "serial")
    )
"""


# A module whose one test spawns a grandchild then blocks: the holder shape
# the tool's own subjects (`test_pool_slots`, `test_client_lock`) take. The
# grandchild's pid is recorded where the outer test can read it, and both it
# and the staged test sleep far past the deadline, so only a kill that reaches
# the whole process group can stop the grandchild — a direct-child kill
# strands it running and this test red.
GRANDCHILD_PROBE = """
import os, pathlib, subprocess, sys, time

def test_staged_holder():
    grandchild = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"]
    )
    pathlib.Path(os.environ["MODULE_COST_GRANDCHILD_OUT"]).write_text(str(grandchild.pid))
    time.sleep(120)
"""


def make_sample(**overrides: object) -> module_cost.Sample:
    """One green-looking sample, with the caller's fields replaced."""
    fields: dict[str, object] = {
        "module": "tests/unit/test_example.py",
        "wall_s": 54.04,
        "cpu_user_s": 10.13,
        "cpu_sys_s": 3.41,
        "load_start": 1.13,
        "load_end": 1.30,
        "foreign_start": 0,
        "foreign_end": 0,
        "exit_code": 0,
    }
    fields.update(overrides)
    return module_cost.Sample(**fields)  # type: ignore[arg-type]


def test_row_names_serial_and_every_figure() -> None:
    """The row carries the serial statement and each figure a reader quotes."""
    row = module_cost.format_row(make_sample())
    assert "mode=serial pytest -n0 (xdist workers disabled)" in row
    assert "module=tests/unit/test_example.py" in row
    assert "wall=54.04s" in row
    assert "cpu=13.54s (user 10.13s + sys 3.41s)" in row
    assert "load_1m=1.13 -> 1.30" in row
    assert "foreign_gate_processes=0 -> 0" in row
    assert "exit=0" in row


def test_row_shows_null_for_a_reading_it_could_not_take() -> None:
    """An unreadable load is `null`, never a guess or a crash."""
    row = module_cost.format_row(make_sample(load_start=None, load_end=None))
    assert "load_1m=null -> null" in row


def test_row_shows_null_for_a_foreign_count_it_could_not_take() -> None:
    """An unreadable `/proc` renders `null`, never Python's `None`."""
    row = module_cost.format_row(make_sample(foreign_start=None, foreign_end=None))
    assert "foreign_gate_processes=null -> null" in row


def test_argv_is_serial() -> None:
    """`-n0` is in the child's argv after the module, and nothing counted."""
    argv = module_cost.build_pytest_argv("python", "tests/unit/test_x.py")
    assert argv[:4] == ["python", "-m", "pytest", "tests/unit/test_x.py"]
    assert "-n0" in argv
    assert not any(arg.startswith("--junit-xml") for arg in argv)


def stage_module(root: Path, body: str, name: str = "test_staged.py") -> str:
    """Write one staged test module (and an `-n auto` pyproject) under `root`."""
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\naddopts = "-n auto"\n')
    (root / name).write_text(body)
    return name


def test_measure_runs_serial_against_a_parallel_addopts(tmp_path: Path) -> None:
    """`-n0` beats the staged `-n auto`, so no xdist worker ran the test."""
    module = stage_module(tmp_path, WORKER_PROBE)
    out = tmp_path / "worker.txt"
    out.write_text("untouched")
    os.environ["MODULE_COST_WORKER_OUT"] = str(out)
    try:
        sample = module_cost.measure(module, root=tmp_path)
    finally:
        os.environ.pop("MODULE_COST_WORKER_OUT", None)
    assert sample.exit_code == 0
    assert out.read_text() == "serial"
    assert sample.wall_s > 0.0
    assert sample.cpu_user_s + sample.cpu_sys_s > 0.0


def test_measure_propagates_a_red_modules_exit(tmp_path: Path) -> None:
    """A red module is still a measurement: the child's exit code is carried."""
    module = stage_module(
        tmp_path,
        "def test_pass():\n    assert True\n\n\ndef test_fail():\n    assert False\n",
    )
    sample = module_cost.measure(module, root=tmp_path)
    assert sample.exit_code == 1
    assert sample.timed_out is False


def test_measure_kills_a_child_at_its_deadline(tmp_path: Path) -> None:
    """A child still running at the deadline is killed, typed, and not a measurement.

    The staged module sleeps well past the one-second deadline, so the kill is
    the run's own path — wall and CPU up to the kill are real readings, the
    exit is 124 and `timed_out` is set, because a run that never finished is
    not a measurement.
    """
    module = stage_module(tmp_path, "import time\n\ndef test_hangs():\n    time.sleep(60)\n")
    sample = module_cost.measure(module, root=tmp_path, child_timeout_s=1.0)
    assert sample.timed_out is True
    assert sample.exit_code == 124
    assert sample.wall_s >= 1.0
    assert sample.cpu_user_s + sample.cpu_sys_s > 0.0


def _pid_alive(pid: int) -> bool:
    """Whether `pid` still exists — `kill(pid, 0)` probes without signalling."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover — a live pid outside our ownership
        return True
    return True


def test_measure_kills_the_grandchild_of_a_timed_out_child(tmp_path: Path) -> None:
    """The deadline kill reaches the whole process group, not just the direct child.

    `subprocess.run`'s timeout terminates the direct pytest only, so a module
    whose tests spawn holders of their own — the exact shape of this tool's
    own subjects, `test_pool_slots` and `test_client_lock` — would leave those
    holders alive. The staged module's test spawns a grandchild of its own
    session that sleeps far past the deadline and records its pid where this
    test reads it, so the pid surviving the run is the leak the finding names.
    """
    module = stage_module(tmp_path, GRANDCHILD_PROBE)
    out = tmp_path / "grandchild.txt"
    out.write_text("unwritten")
    os.environ["MODULE_COST_GRANDCHILD_OUT"] = str(out)
    try:
        sample = module_cost.measure(module, root=tmp_path, child_timeout_s=5.0)
    finally:
        os.environ.pop("MODULE_COST_GRANDCHILD_OUT", None)
    assert sample.timed_out is True
    assert sample.exit_code == 124
    pid_text = out.read_text()
    assert pid_text != "unwritten", "the staged test never ran; the deadline was too short"
    pid = int(pid_text)
    deadline = time.monotonic() + 10.0
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _pid_alive(pid), f"grandchild {pid} survived the deadline kill"


def test_measure_reads_staged_kernel_files(tmp_path: Path) -> None:
    """Load and the foreign count come from the staged `/proc`, exactly."""
    module = stage_module(tmp_path, "def test_one():\n    assert True\n")
    proc = tmp_path / "proc"
    (proc / "123").mkdir(parents=True)
    (proc / "loadavg").write_text("0.42 0.10 0.05 1/100 1234\n")
    (proc / "123" / "cmdline").write_bytes(b"python -m pytest\x00-n0\x00")
    sample = module_cost.measure(module, root=tmp_path, proc=proc)
    assert sample.load_start == 0.42
    assert sample.load_end == 0.42
    # The staged pytest-named process is the only one the staged `/proc` holds.
    assert sample.foreign_start == 1
    assert sample.foreign_end == 1


def test_main_prints_one_row_and_propagates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main` prints the row for the module it was given and returns the exit."""
    seen: dict[str, object] = {}

    def fake_measure(module: str, **_: object) -> module_cost.Sample:
        seen["module"] = module
        return make_sample(exit_code=1)

    monkeypatch.setattr(module_cost, "measure", fake_measure)
    assert module_cost.main(["tests/unit/test_example.py"]) == 1
    assert seen["module"] == "tests/unit/test_example.py"
    out = capsys.readouterr().out
    assert "mode=serial" in out
    assert "the module is red" in out


def test_main_prints_a_timeout_note_not_a_red_note(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A killed child reads as a timeout, never as a red module."""
    monkeypatch.setattr(
        module_cost,
        "measure",
        lambda *_, **__: make_sample(timed_out=True, exit_code=124),
    )
    assert module_cost.main(["tests/unit/test_example.py"]) == 124
    out = capsys.readouterr().out
    assert "timed-out run is not a measurement" in out
    assert "the module is red" not in out


def test_main_green_prints_no_red_note(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(module_cost, "measure", lambda *_, **__: make_sample())
    assert module_cost.main(["tests/unit/test_example.py"]) == 0
    assert "the module is red" not in capsys.readouterr().out
