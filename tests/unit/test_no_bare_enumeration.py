"""Permanent AST guard for the pure controller policy."""

from __future__ import annotations

import ast
from pathlib import Path

POLICY = Path(__file__).resolve().parents[2] / "tools" / "controller_policy.py"
FORBIDDEN_MODULES = {
    "http",
    "httpx",
    "pathlib",
    "requests",
    "socket",
    "subprocess",
    "time",
    "urllib",
    "urllib.request",
}
FORBIDDEN_ROOTS = {"datetime", "os", "provider", "providers"}


def test_controller_policy_imports_no_external_capability() -> None:
    tree = ast.parse(POLICY.read_text(encoding="utf-8"), filename=str(POLICY))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)

    forbidden = {
        name
        for name in imported
        if name in FORBIDDEN_MODULES or name.split(".", 1)[0] in FORBIDDEN_ROOTS
    }
    assert forbidden == set()
