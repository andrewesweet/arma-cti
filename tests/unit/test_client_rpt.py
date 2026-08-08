"""Select the headed Windows client's RPT without guessing a user profile (#73)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

client_rpt = load_tool("client_rpt")


def rpt(directory: Path, name: str, mtime_ns: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("log\n", encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


def test_the_newest_rpt_wins_across_windows_user_profiles(tmp_path: Path) -> None:
    rpt(tmp_path / "alice/AppData/Local/Arma 3", "older.rpt", 100)
    newest = rpt(tmp_path / "zoe/AppData/Local/Arma 3", "newest.rpt", 200)

    assert client_rpt.newest_client_rpt(users_dir=tmp_path, configured_dir=None) == newest


def test_an_explicit_directory_does_not_search_other_profiles(tmp_path: Path) -> None:
    configured = tmp_path / "chosen"
    chosen = rpt(configured, "chosen.rpt", 100)
    rpt(tmp_path / "alice/AppData/Local/Arma 3", "newer.rpt", 200)

    assert client_rpt.newest_client_rpt(users_dir=tmp_path, configured_dir=configured) == chosen


def test_cli_copies_the_selected_rpt_and_reports_its_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = rpt(tmp_path / "alice/AppData/Local/Arma 3", "client.rpt", 200)
    source.write_text("remoteExec is not allowed to be remotely executed\n", encoding="utf-8")
    destination = tmp_path / "evidence/client.rpt"

    status = client_rpt.main(["--users-dir", str(tmp_path), "--out", str(destination)])

    assert status == 0
    assert destination.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    records = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines())
    assert records == {
        "windows_client_rpt": str(destination),
        "windows_client_rpt_source": str(source),
        "windows_client_remoteexec_denied": "1",
    }
