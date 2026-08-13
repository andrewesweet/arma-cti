#!/usr/bin/env python3
"""Own one Steam/Proton/Arma process tree inside a systemd user cgroup."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path, PureWindowsPath
from typing import Final

APP_ID: Final = "107410"
PORT_PATTERN: Final = re.compile(r"^[0-9]{1,5}$")
HOST_PATTERN: Final = re.compile(r"^[A-Za-z0-9_.:-]+$")
START_TIMEOUT: Final = 180
STOP_TIMEOUT: Final = 30
POLL_SECONDS: Final = 0.5
MAX_PORT: Final = 65535
stopping = False


def _stop(_signum: int, _frame: object) -> None:
    """Ask the owned process group to stop at the next bounded poll."""
    global stopping  # noqa: PLW0603 — signal handlers communicate through one flag
    stopping = True


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        msg = f"missing required environment: {name}"
        raise ValueError(msg)
    return value


def _windows_mod_path(value: str) -> str:
    """Map one absolute Linux mod root through Proton's Wine Z: drive."""
    path = Path(value)
    if not path.is_absolute() or any(character in value for character in "\\;:\r\n"):
        msg = "CTI_CLIENT_MOD must be one absolute Linux path"
        raise ValueError(msg)
    return str(PureWindowsPath("Z:/", *path.parts[1:]))


def _cgroup_pids() -> list[int]:
    relative = Path("/proc/self/cgroup").read_text(encoding="utf-8").split("::", 1)[-1].strip()
    path = Path("/sys/fs/cgroup") / relative.lstrip("/") / "cgroup.procs"
    return [int(value) for value in path.read_text(encoding="utf-8").split()]


def _command_line(pid: int) -> str:
    try:
        command = (
            Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        )
        return re.sub(r"-password=[^ ]*", "-password=<redacted>", command)
    except OSError:
        return ""


def _arma_pids() -> list[int]:
    return [pid for pid in _cgroup_pids() if "arma3_x64" in _command_line(pid).casefold()]


def _write_process_tree(path: Path) -> None:
    rows = [
        {"pid": pid, "command": _command_line(pid), "cgroup": "owned"} for pid in _cgroup_pids()
    ]
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _wait_for_server(port: int, deadline: float) -> bool:
    ss_binary = shutil.which("ss")
    if ss_binary is None:
        return False
    while time.monotonic() < deadline:
        result = subprocess.run(  # noqa: S603 — fixed local socket inspector
            [ss_binary, "-H", "-lun", f"sport = :{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
        time.sleep(POLL_SECONDS)
    return False


def _copy_if_present(source: Path, destination: Path) -> None:
    try:
        if source.is_file():
            shutil.copy2(source, destination)
    except OSError:
        return


def _redact_file(path: Path, secret: str) -> None:
    if not secret or not path.is_file():
        return
    try:
        path.write_text(
            path.read_text(encoding="utf-8", errors="replace").replace(secret, "<redacted>"),
            encoding="utf-8",
        )
    except OSError:
        return


def _facts(evidence: Path, steam_library_root: Path, client_install: Path) -> None:
    commands = {
        "gpu.txt": ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
        "vulkan.txt": ["vulkaninfo", "--summary"],
        "os.txt": ["uname", "-a"],
        # Steam's executable is a launcher, including for --version: invoking it
        # can start the long-lived client this service is about to own. The
        # Ubuntu launcher package is passive evidence and cannot seed a client.
        "steam.txt": [
            "dpkg-query",
            "--show",
            "--showformat=${binary:Package}\t${Version}\n",
            "steam-installer",
        ],
    }
    for name, command in commands.items():
        try:
            result = subprocess.run(  # noqa: S603 — fixed evidence commands
                command,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            (evidence / name).write_text(result.stdout + result.stderr, encoding="utf-8")
        except (OSError, subprocess.TimeoutExpired) as exc:
            (evidence / name).write_text(f"unavailable: {exc}\n", encoding="utf-8")
    _copy_if_present(
        steam_library_root / "steamapps/appmanifest_107410.acf",
        evidence / "appmanifest_107410.acf",
    )
    _copy_if_present(
        steam_library_root / "steamapps/common/Proton 10.0/version",
        evidence / "proton-version.txt",
    )
    (evidence / "install-layout.json").write_text(
        json.dumps(
            {
                "client_install": str(client_install),
                "steam_library_root": str(steam_library_root),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _install_layout_error(steam_library_root: Path, client_install: Path) -> str:
    expected_install = steam_library_root / "steamapps/common/Arma 3"
    if client_install != expected_install:
        return "CTI_CLIENT_INSTALL is not beneath the configured Steam library root"
    if not steam_library_root.is_dir():
        return "configured Steam library root is absent"
    if not (client_install / "arma3_x64.exe").is_file():
        return "configured Arma 3 client executable is absent"
    return ""


def _preflight_error(port: int, steam_library_root: Path, client_install: Path) -> tuple[int, str]:
    if not 1 <= port <= MAX_PORT:
        return 64, "invalid client port"
    detail = _install_layout_error(steam_library_root, client_install)
    return (5, detail) if detail else (0, "")


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + STOP_TIMEOUT
    while time.monotonic() < deadline and _cgroup_pids() != [os.getpid()]:
        time.sleep(POLL_SECONDS)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def main() -> int:
    """Launch, observe, and tear down only this service's owned process group."""
    try:
        server = _required("CTI_CLIENT_SERVER")
        port_text = _required("CTI_CLIENT_PORT")
        evidence = Path(_required("CTI_CLIENT_EVIDENCE")).resolve()
        profile = _required("CTI_CLIENT_PROFILE")
        steam_library_root = Path(_required("CTI_STEAM_LIBRARY_ROOT")).resolve()
        client_install = Path(_required("CTI_CLIENT_INSTALL")).resolve()
        windows_mod = _windows_mod_path(_required("CTI_CLIENT_MOD"))
    except ValueError as exc:
        print(exc, file=sys.stderr)  # noqa: T201 — systemd journal contract
        return 64
    if not HOST_PATTERN.fullmatch(server) or not PORT_PATTERN.fullmatch(port_text):
        print("invalid server or port", file=sys.stderr)  # noqa: T201 — systemd journal contract
        return 64
    port = int(port_text)
    preflight_status, preflight_detail = _preflight_error(port, steam_library_root, client_install)
    if preflight_status:
        print(preflight_detail, file=sys.stderr)  # noqa: T201 — systemd journal contract
        return preflight_status
    evidence.mkdir(parents=True, exist_ok=True)
    _facts(evidence, steam_library_root, client_install)
    if not _wait_for_server(port, time.monotonic() + START_TIMEOUT):
        print(f"server UDP port {port} was not listening", file=sys.stderr)  # noqa: T201
        return 5
    steam = shutil.which("steam")
    if steam is None:
        return 5
    password = os.environ.get("CTI_CLIENT_PASSWORD", "")
    command = [
        steam,
        "-silent",
        "-applaunch",
        APP_ID,
        "-noLauncher",
        f"-connect={server}",
        f"-port={port}",
        f"-password={password}",
        f"-mod={windows_mod}",
        f"-name={profile}",
        "-window",
        "-noSplash",
        "-skipIntro",
        "-noPause",
    ]
    steam_log = evidence / "steam-client.log"
    log = steam_log.open("wb")
    process = subprocess.Popen(  # noqa: S603 — fixed Steam binary and validated run data
        command,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    deadline = time.monotonic() + START_TIMEOUT
    seen = False
    status = 0
    try:
        while time.monotonic() < deadline and not stopping:
            if _arma_pids():
                seen = True
                break
            time.sleep(POLL_SECONDS)
        if not seen:
            status = 5
        while seen and not stopping and _arma_pids():
            _write_process_tree(evidence / "process-tree.json")
            time.sleep(POLL_SECONDS)
    finally:
        _write_process_tree(evidence / "process-tree-final.json")
        _terminate_group(process)
        log.close()
        _copy_if_present(Path.home() / "steam-107410.log", evidence / "proton.log")
        for root in (
            Path.home() / ".local/share/Arma 3",
            steam_library_root / "steamapps/compatdata/107410/pfx/drive_c/"
            "users/steamuser/AppData/Local/Arma 3",
        ):
            candidates = sorted(root.glob("*.rpt"), key=lambda path: path.stat().st_mtime_ns)
            if candidates:
                _copy_if_present(candidates[-1], evidence / "client.rpt")
        for path in (steam_log, evidence / "proton.log", evidence / "client.rpt"):
            _redact_file(path, password)
        (evidence / "exit-status.txt").write_text(f"{status}\n", encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
