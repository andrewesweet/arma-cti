"""Permanent AST guard for the pure controller policy."""

from __future__ import annotations

import ast
from pathlib import Path

POLICY = Path(__file__).resolve().parents[2] / "tools" / "controller_policy.py"
ALLOWED_MODULES = {"__future__", "dataclasses", "typing"}
FORBIDDEN_BUILTINS = {"__import__", "open"}


def imported_modules(tree: ast.AST) -> set[str]:
    """Collect absolute and relative imports from one module AST."""
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(
                node.module if node.level == 0 and node.module is not None else "<relative>"
            )
    return imported


def forbidden_builtin_calls(tree: ast.AST) -> set[str]:
    """Collect direct calls to builtins that escape the pure policy seam."""
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_BUILTINS:
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_BUILTINS:
            called.add(node.func.attr)
    return called


def test_controller_policy_imports_only_allowlisted_modules() -> None:
    tree = ast.parse(POLICY.read_text(encoding="utf-8"), filename=str(POLICY))
    assert imported_modules(tree) <= ALLOWED_MODULES


def test_controller_policy_has_no_builtin_capability_calls() -> None:
    tree = ast.parse(POLICY.read_text(encoding="utf-8"), filename=str(POLICY))

    assert forbidden_builtin_calls(tree) == set()


def test_new_import_and_builtin_call_fail_closed() -> None:
    tree = ast.parse("from random import seed\nimport random\nopen('state.json')\n")

    assert imported_modules(tree) - ALLOWED_MODULES == {"random"}
    assert forbidden_builtin_calls(tree) == {"open"}
