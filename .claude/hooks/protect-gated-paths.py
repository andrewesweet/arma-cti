#!/usr/bin/env python3
"""PreToolUse hook (Edit|Write): deny edits to sign-off-gated or generated paths."""
import fnmatch
import json
import sys

GATED = [
    ("*/generated/*", "Generated file. Edit the schema source and regenerate; never hand-edit."),
    ("*tests/specs/*", "Acceptance spec. Specs encode human intent and are sign-off gated (CLAUDE.md); propose the change to the user instead of editing."),
]

data = json.load(sys.stdin)
path = data.get("tool_input", {}).get("file_path", "")
for pattern, reason in GATED:
    if fnmatch.fnmatch(path, pattern):
        print(reason, file=sys.stderr)
        sys.exit(2)
sys.exit(0)
