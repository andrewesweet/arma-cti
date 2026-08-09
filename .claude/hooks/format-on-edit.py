#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write): auto-format the edited file.

Never blocks; silently no-ops if the formatter is absent.

The paths come from `tools/edit_payload.py` rather than straight out of
`tool_input["file_path"]`: Codex's editing tool sends a patch envelope and no
`file_path` at all, which read as the empty string, matched no extension, and
cost two Codex dispatches a hand-run `ruff format` before their gate went green
(#273). One patch may touch several files, so this is a loop.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# `edit_payload` is shared with `tools/`, which is not on a hook's script path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from edit_payload import edited_paths

data = json.load(sys.stdin)
for path in edited_paths(data.get("tool_input")) or ():
    try:
        if path.endswith(".py") and shutil.which("ruff"):
            subprocess.run(["ruff", "format", "-q", path], timeout=30)
        elif path.endswith(".rs") and shutil.which("rustfmt"):
            # Must match extension/Cargo.toml, else `cargo fmt --check` disagrees
            # with whatever this hook just wrote.
            subprocess.run(["rustfmt", "--edition", "2024", path], timeout=30)
    except Exception:
        pass
sys.exit(0)
