#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write): auto-format the edited file.

Never blocks; silently no-ops if the formatter is absent.
"""

import json
import shutil
import subprocess
import sys

data = json.load(sys.stdin)
path = data.get("tool_input", {}).get("file_path", "")
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
