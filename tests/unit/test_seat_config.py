"""A seat that does not declare its (model, effort) pair is refused (#255)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

check_seat_config = load_tool("check_seat_config")

AGENT = """---
name: cti-example
description: An example seat.
model: opus
effort: xhigh
---

Body.
"""

SKILL = """---
name: example
description: An example skill.
---

Body.
"""


def write_agent(root: Path, name: str, text: str) -> None:
    directory = root / ".claude" / "agents"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(text, encoding="utf-8")


def write_skill(root: Path, name: str, text: str) -> None:
    directory = root / ".claude" / "skills" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(text, encoding="utf-8")


def test_the_repository_as_it_stands_declares_every_seat() -> None:
    """The gate is green on the tree it ships with, not only on fixtures."""
    assert check_seat_config.failures(REPO) == []


def test_a_complete_agent_seat_passes(tmp_path: Path) -> None:
    write_agent(tmp_path, "cti-example", AGENT)
    assert check_seat_config.failures(tmp_path) == []


@pytest.mark.parametrize(
    ("dropped", "wanted"),
    [("model: opus\n", "no `model:`"), ("effort: xhigh\n", "no `effort:`")],
)
def test_a_missing_half_of_the_pair_is_named(tmp_path: Path, dropped: str, wanted: str) -> None:
    write_agent(tmp_path, "cti-example", AGENT.replace(dropped, ""))
    found = check_seat_config.failures(tmp_path)
    assert len(found) == 1
    assert wanted in found[0]
    assert ".claude/agents/cti-example.md" in found[0]


def test_an_effort_level_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    """`extreme` is not a level, and a seat carrying it runs at the session's."""
    write_agent(tmp_path, "cti-example", AGENT.replace("effort: xhigh", "effort: extreme"))
    found = check_seat_config.failures(tmp_path)
    assert len(found) == 1
    assert "effort `extreme` is not one of" in found[0]


def test_a_model_outside_the_ratified_set_is_refused(tmp_path: Path) -> None:
    write_agent(tmp_path, "cti-example", AGENT.replace("model: opus", "model: gpt-5"))
    found = check_seat_config.failures(tmp_path)
    assert len(found) == 1
    assert "model `gpt-5` is not one of" in found[0]


def test_an_agent_may_not_inherit_its_model(tmp_path: Path) -> None:
    """`inherit` is the skill spelling; in an agent seat, inheriting is the defect."""
    write_agent(tmp_path, "cti-example", AGENT.replace("model: opus", "model: inherit"))
    assert any("model `inherit`" in line for line in check_seat_config.failures(tmp_path))


def test_an_indented_key_is_not_top_level_and_does_not_count(tmp_path: Path) -> None:
    """The failure this gate exists for: the loader reads past it and says nothing."""
    write_agent(tmp_path, "cti-example", AGENT.replace("effort: xhigh", "  effort: xhigh"))
    found = check_seat_config.failures(tmp_path)
    assert len(found) == 1
    assert "no `effort:`" in found[0]


def test_a_file_with_no_frontmatter_fence_is_named_as_all_body(tmp_path: Path) -> None:
    write_agent(tmp_path, "cti-example", "model: opus\neffort: xhigh\n")
    found = check_seat_config.failures(tmp_path)
    assert len(found) == 1
    assert "no `---` frontmatter block" in found[0]


def test_an_unterminated_frontmatter_fence_is_named(tmp_path: Path) -> None:
    write_agent(tmp_path, "cti-example", "---\nmodel: opus\neffort: xhigh\n")
    assert any(
        "no `---` frontmatter block" in line for line in check_seat_config.failures(tmp_path)
    )


def test_a_skill_declaring_neither_half_inherits_and_is_left_alone(tmp_path: Path) -> None:
    """The project's three existing skills declare nothing and are not seats."""
    write_skill(tmp_path, "example", SKILL)
    assert check_seat_config.failures(tmp_path) == []


def test_a_skill_declaring_one_half_must_declare_the_other(tmp_path: Path) -> None:
    write_skill(tmp_path, "example", SKILL.replace("---\n\nBody", "model: opus\n---\n\nBody"))
    found = check_seat_config.failures(tmp_path)
    assert len(found) == 1
    assert "no `effort:`" in found[0]
    assert ".claude/skills/example/SKILL.md" in found[0]


def test_a_skill_may_declare_inherit_for_its_model(tmp_path: Path) -> None:
    """`inherit` keeps the active model, which is a thing a skill may legitimately want."""
    body = SKILL.replace("---\n\nBody", "model: inherit\neffort: high\n---\n\nBody")
    write_skill(tmp_path, "example", body)
    assert check_seat_config.failures(tmp_path) == []


def test_a_skill_carrying_a_bad_effort_is_refused(tmp_path: Path) -> None:
    body = SKILL.replace("---\n\nBody", "model: opus\neffort: XHIGH\n---\n\nBody")
    write_skill(tmp_path, "example", body)
    assert any("effort `XHIGH`" in line for line in check_seat_config.failures(tmp_path))


def test_every_failure_across_both_surfaces_is_reported_together(tmp_path: Path) -> None:
    """Filtering by severity happens elsewhere; the check reports what it found."""
    write_agent(tmp_path, "cti-a", AGENT.replace("effort: xhigh", "effort: extreme"))
    write_agent(tmp_path, "cti-b", AGENT.replace("model: opus\n", ""))
    write_skill(tmp_path, "example", SKILL.replace("---\n\nBody", "effort: high\n---\n\nBody"))
    found = check_seat_config.failures(tmp_path)
    assert len(found) == 3
    assert [".claude/agents/cti-a.md" in found[0], ".claude/agents/cti-b.md" in found[1]] == [
        True,
        True,
    ]
    assert ".claude/skills/example/SKILL.md" in found[2]


def test_main_returns_zero_on_the_repository(capsys: pytest.CaptureFixture[str]) -> None:
    assert check_seat_config.main() == 0
    assert capsys.readouterr().err == ""


def test_frontmatter_reads_a_well_formed_block() -> None:
    assert check_seat_config.frontmatter(AGENT) == {
        "name": "cti-example",
        "description": "An example seat.",
        "model": "opus",
        "effort": "xhigh",
    }


def test_frontmatter_refuses_a_body_that_merely_contains_a_fence() -> None:
    assert check_seat_config.frontmatter("Body.\n---\nmodel: opus\n---\n") is None
