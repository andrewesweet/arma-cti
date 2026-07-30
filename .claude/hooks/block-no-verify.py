#!/usr/bin/env python3
"""PreToolUse hook (Bash): deny git commit --no-verify / -n, which bypasses the cog commit-msg hook."""
import json
import re
import sys

data = json.load(sys.stdin)
cmd = data.get("tool_input", {}).get("command", "")
if re.search(r"\bgit\b[^|;&]*\bcommit\b", cmd) and re.search(r"(\s--no-verify\b|\s-n\b)", cmd):
    print("git commit --no-verify (-n) is blocked: it bypasses the Conventional Commits hook (ADR-0010). Fix the commit message instead.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
