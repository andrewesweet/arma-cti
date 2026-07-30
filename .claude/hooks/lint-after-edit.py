#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write): surface lint failures at the edit, not at the gate.

Advisory only. It never blocks — `just check` remains the gate — but it puts the
finding in front of the agent while the edit is still in mind.

Deferred at the 2026-07-30 process amendment pending latency measurement, then
enabled by the Phase 0 retro: HEMTT checks the whole project in 0.10-0.13 s and
warm clippy costs 13 ms, against 20-56 ms for the hooks already running.

Python is deliberately excluded: `uv run ruff check` on one file costs 183 ms,
nearly all of it `uv run` resolving the environment rather than ruff working, and
format-on-edit already covers the common case.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT_SECONDS = 60

data = json.load(sys.stdin)
path = data.get("tool_input", {}).get("file_path", "")
project = Path(data.get("cwd") or ".")

if path.endswith((".sqf", ".cpp", ".hpp")) and shutil.which("hemtt"):
    command = ["hemtt", "check", "-p", "-e", "--no-color"]
elif path.endswith(".rs") and shutil.which("cargo"):
    command = [
        "cargo",
        "clippy",
        "--manifest-path",
        "extension/Cargo.toml",
        "--all-targets",
        "--",
        "-D",
        "warnings",
    ]
else:
    sys.exit(0)

try:
    result = subprocess.run(
        command, check=False, cwd=project, capture_output=True, text=True, timeout=TIMEOUT_SECONDS
    )
except (OSError, subprocess.SubprocessError):
    sys.exit(0)  # A broken linter must never stand between the agent and its edit.

if result.returncode != 0:
    output = (result.stdout + result.stderr).strip()
    print(f"Lint failed after editing {path}:\n{output[-4000:]}", file=sys.stderr)

sys.exit(0)
