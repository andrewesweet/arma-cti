#!/usr/bin/env python3
"""PreToolUse hook (Bash): deny commit-hook bypass flags.

They would skip the cog commit-msg hook that enforces Conventional Commits.
"""

import json
import re
import sys

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")
if re.search(r"\bgit\b[^|;&]*\bcommit\b", cmd) and re.search(r"(\s--no-verify\b|\s-n\b)", cmd):
    print(
        "Bypassing the commit-msg hook is blocked: it defeats the Conventional"
        " Commits gate (ADR-0010). Fix the commit message instead.",
        file=sys.stderr,
    )
    sys.exit(2)
sys.exit(0)
