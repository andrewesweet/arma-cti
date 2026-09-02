"""Tests for `tools/module_cost.py` — one test module's serial wall and CPU (#685).

The staged-process end-to-end tests run real pytest children in `tmp_path`, so
they are the slower half of the module's coverage; everything they prove about
the serial flag is proven against a `pyproject.toml` that sets `-n auto`, which
is the exact arrangement the recipe must override.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

load_tool("gate_clock")  # the sibling `module_cost` imports, registered first
module_cost = load_tool("module_cost")

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
        "collected": 47,
        "failed": 0,
        "errored": 0,
        "skipped": 0,
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
    assert "tests=47 failed=0 errored=0 skipped=0 exit=0" in row


def test_row_shows_null_for_a_reading_it_could_not_take() -> None:
    """An unreadable load is `null`, never a guess or a crash."""
    row = module_cost.format_row(make_sample(load_start=None, load_end=None))
    assert "load_1m=null -> null" in row


def test_argv_is_serial_and_counts_through_junit(tmp_path: Path) -> None:
    """`-n0` is in the child's argv after the module, with a junit path beside it."""
    argv = module_cost.build_pytest_argv("python", "tests/unit/test_x.py", tmp_path / "j.xml")
    assert argv[:4] == ["python", "-m", "pytest", "tests/unit/test_x.py"]
    assert "-n0" in argv
    assert "--junit-xml=" + str(tmp_path / "j.xml") in argv


def test_junit_counts_read_the_suite(tmp_path: Path) -> None:
    """Collected, failed, errored and skipped come from the suite's attributes.

    pytest's xunit2 nests the suite inside `<testsuites>`; the counts live on
    the `<testsuite>` element, which is where the reader looks.
    """
    root = ET.Element("testsuites")
    ET.SubElement(
        root,
        "testsuite",
        {"tests": "4", "failures": "1", "errors": "1", "skipped": "1"},
    )
    path = tmp_path / "junit.xml"
    ET.ElementTree(root).write(path)
    assert module_cost.junit_counts(path) == (4, 1, 1, 1)


def test_junit_counts_read_a_bare_suite_root(tmp_path: Path) -> None:
    """The xunit1 shape, with the counts on the root element, reads the same."""
    path = tmp_path / "junit.xml"
    path.write_text('<testsuite tests="4" failures="1" errors="1" skipped="1"></testsuite>')
    assert module_cost.junit_counts(path) == (4, 1, 1, 1)


@pytest.mark.parametrize(
    "content",
    [
        None,
        "<not-xml",
        "<testsuites></testsuites>",
        '<testsuite tests="oops"></testsuite>',
    ],
)
def test_junit_counts_unknown_is_zero_not_a_crash(tmp_path: Path, content: str | None) -> None:
    """A report the child did not write leaves the counts unknown at zero."""
    path = tmp_path / "junit.xml"
    if content is not None:
        path.write_text(content)
    assert module_cost.junit_counts(path) == (0, 0, 0, 0)


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
    assert sample.collected == 1
    assert sample.failed == 0
    assert out.read_text() == "serial"
    assert sample.wall_s > 0.0
    assert sample.cpu_user_s + sample.cpu_sys_s > 0.0


def test_measure_counts_a_red_module_and_propagates_its_exit(tmp_path: Path) -> None:
    """A red module is still a measurement: counts named, exit code carried."""
    module = stage_module(
        tmp_path,
        "def test_pass():\n    assert True\n\n\ndef test_fail():\n    assert False\n",
    )
    sample = module_cost.measure(module, root=tmp_path)
    assert (sample.collected, sample.failed) == (2, 1)
    assert sample.exit_code == 1


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


def test_main_green_prints_no_red_note(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(module_cost, "measure", lambda *_: make_sample())
    assert module_cost.main(["tests/unit/test_example.py"]) == 0
    assert "the module is red" not in capsys.readouterr().out
