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

The paths come from `tools/edit_payload.py`, for #273's reason: Codex's editing
tool sends a patch envelope and no `file_path`. Both linters check the whole
project, so a patch touching several files of one kind runs its linter once.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# `edit_payload` is shared with `tools/`, which is not on a hook's script path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from edit_payload import edited_paths

TIMEOUT_SECONDS = 60

HEMTT = ["hemtt", "check", "-p", "-e", "--no-color"]
CLIPPY = [
    "cargo",
    "clippy",
    "--manifest-path",
    "extension/Cargo.toml",
    "--all-targets",
    "--",
    "-D",
    "warnings",
]

data = json.load(sys.stdin)
project = Path(data.get("cwd") or ".")

edited: dict[str, list[str]] = {}
for path in edited_paths(data.get("tool_input")) or ():
    if path.endswith((".sqf", ".cpp", ".hpp")) and shutil.which("hemtt"):
        edited.setdefault("hemtt", []).append(path)
    elif path.endswith(".rs") and shutil.which("cargo"):
        edited.setdefault("clippy", []).append(path)

for linter, paths in edited.items():
    try:
        result = subprocess.run(
            HEMTT if linter == "hemtt" else CLIPPY,
            check=False,
            cwd=project,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        continue  # A broken linter must never stand between the agent and its edit.
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        print(f"Lint failed after editing {', '.join(paths)}:\n{output[-4000:]}", file=sys.stderr)

sys.exit(0)
