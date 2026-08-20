"""The Claude Bash allowlist names real just recipes or aliases (#448)."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

check = load_tool("check_just_grants")


def fixture(root: Path, grants: list[str]) -> tuple[Path, Path]:
    """Write the smallest settings and justfile pair that exercises both name kinds."""
    settings = root / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": grants}}), encoding="utf-8")
    justfile = root / "justfile"
    justfile.write_text(
        "mutation *args:\n"
        "    @true\n\n"
        "alias mutation-compare := mutation\n\n"
        "orchestrator-only:\n"
        "    @true\n",
        encoding="utf-8",
    )
    return settings, justfile


def test_recipes_and_aliases_resolve_without_granting_every_recipe(tmp_path: Path) -> None:
    settings, justfile = fixture(
        tmp_path,
        ["Bash(just mutation --report)", "Bash(just mutation-compare:*)"],
    )

    assert check.failures(settings, justfile) == []


def test_a_broken_settings_grant_reds_and_names_both_sides(tmp_path: Path) -> None:
    settings, justfile = fixture(tmp_path, ["Bash(just missing-recipe:*)"])

    completed = subprocess.run(  # noqa: S603 — fixed interpreter and repository script
        [
            sys.executable,
            str(REPO / "tools" / "check_just_grants.py"),
            "--settings",
            str(settings),
            "--justfile",
            str(justfile),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert completed.stderr.strip() == (
        "`Bash(just missing-recipe:*)` grants `missing-recipe`, which `justfile` does not define"
    )


def test_repository_grants_are_live_and_the_checker_is_on_check() -> None:
    assert check.failures(REPO / ".claude" / "settings.json", REPO / "justfile") == []

    completed = subprocess.run(
        [  # noqa: S607 — the repository's required `just` binary resolves from PATH
            "just",
            "--dump",
            "--dump-format",
            "json",
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    recipes = json.loads(completed.stdout)["recipes"]
    dependencies = {dependency["recipe"] for dependency in recipes["check"]["dependencies"]}
    assert "check-just-grants" in dependencies
    assert "tools/check_just_grants.py" in str(recipes["check-just-grants"]["body"])
