"""The Claude seat surfaces are the dispatch registry's, and drift is caught (#324).

Both declaration surfaces fail open (ADR-0068): a drifted pair does not refuse, the seat
answers at whatever tier the session had, and the only trace is a cheaper arm than the one
the map ratified. `tools/check_seat_config.py` already asserts that a pair is *declared and
valid*; what is tested here is the half that was missing — that it is the *registry's*, and
that a hand edit, a retired seat's file, or an un-regenerated registry change is a
`schema_stale` red rather than a silently obeyed file.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

dispatch = load_tool("dispatch")
generate_seats = load_tool("generate_seats")
check_seat_config = load_tool("check_seat_config")

SKILL = ".claude/skills/interlocutor/SKILL.md"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A repository root carrying only what the generator reads and writes."""
    skill = tmp_path / SKILL
    skill.parent.mkdir(parents=True)
    shutil.copy(REPO / SKILL, skill)
    (tmp_path / ".claude" / "agents").mkdir()
    return tmp_path


def agent(root: Path, stem: str) -> Path:
    """The seat file `stem` names under this root."""
    return root / ".claude" / "agents" / f"{stem}.md"


# --------------------------------------------------------------- the pair is the registry's


def test_every_seats_pair_is_the_first_native_profile_in_its_preference_list() -> None:
    """The one derivation this module performs, asserted against the registry itself."""
    for surface in generate_seats.AGENT_SURFACES:
        preference = generate_seats.seat(surface.seat).preference
        native = [name for name in preference if dispatch.PROFILES[name].lane == "claude-native"]
        profile = dispatch.PROFILES[native[0]]
        front = check_seat_config.frontmatter(generate_seats.render(surface))
        assert front["name"] == surface.stem
        assert (front["model"], front["effort"]) == (profile.model, profile.effort)


def test_the_foreign_head_of_a_preference_list_is_not_what_a_claude_seat_declares() -> None:
    """#324's one judgement call, pinned.

    `implementer` prefers a Codex profile and then a z.ai one, and neither is a pair a
    `.claude/agents/` file can mean: the file declares a Claude-vocabulary model, and which
    provider that reaches belongs to the session that spawns the subagent. z.ai is the
    trap — its profile's Claude vocabulary is `opus`/`max`, which a native session would
    read as a native pair nobody chose.
    """
    preference = dispatch.SEATS["implementer"].preference
    assert dispatch.PROFILES[preference[0]].lane == "codex"
    assert dispatch.PROFILES[preference[1]].lane == "zai"
    assert generate_seats.native_profile("implementer") == dispatch.PROFILES["opus-low"]


def test_a_seat_with_no_native_profile_refuses_rather_than_inventing_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_only = dispatch.SEATS["planner"]._replace(preference=("codex-sol-xhigh",))
    monkeypatch.setitem(dispatch.SEATS, "planner", foreign_only)
    with pytest.raises(generate_seats.SeatSurfaceError, match="none of them on `claude-native`"):
        generate_seats.native_profile("planner")


def test_a_seat_in_no_registry_is_named() -> None:
    with pytest.raises(generate_seats.SeatSurfaceError, match="is in no registry"):
        generate_seats.seat("mechanical")


def test_the_declared_only_row_is_readable_but_not_dispatchable() -> None:
    """ADR-0068: the interlocutor is a slash command, so `--seat interlocutor` stays unknown."""
    assert "interlocutor" not in dispatch.SEATS
    assert generate_seats.seat("interlocutor") is dispatch.DECLARED_ONLY_SEATS["interlocutor"]
    assert generate_seats.native_profile("interlocutor") == dispatch.PROFILES["opus-xhigh"]


def test_the_rendered_description_carries_the_registrys_tier_and_not_an_authored_one() -> None:
    """The pair was narrated in prose as well as declared; the narration is derived now."""
    surface = next(s for s in generate_seats.AGENT_SURFACES if s.seat == "recon")
    profile = generate_seats.native_profile("recon")
    assert f"{profile.model} at {profile.effort} effort" in generate_seats.describe(
        surface, profile
    )


def test_every_generated_seat_passes_the_declaration_check(root: Path) -> None:
    """The two gates agree: what this writes is what `just check-seats` accepts."""
    assert generate_seats.main(["--root", str(root)]) == 0
    assert check_seat_config.failures(root) == []


def test_a_read_only_seat_keeps_its_tool_list(root: Path) -> None:
    """`recon` is read-only by definition, and the definition is the `tools:` line."""
    assert generate_seats.main(["--root", str(root)]) == 0
    front = check_seat_config.frontmatter(agent(root, "cti-recon").read_text(encoding="utf-8"))
    assert front["tools"] == "Read, Grep, Glob, Bash"
    assert "tools" not in check_seat_config.frontmatter(
        agent(root, "cti-implementer").read_text(encoding="utf-8")
    )


# ------------------------------------------------------------------------ drift is caught


def test_writing_makes_the_check_pass(root: Path) -> None:
    assert generate_seats.main(["--root", str(root)]) == 0
    assert generate_seats.main(["--root", str(root), "--check"]) == 0


def test_a_hand_edited_pair_in_a_seat_file_is_caught(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole point: the harness would obey this file silently."""
    assert generate_seats.main(["--root", str(root)]) == 0
    path = agent(root, "cti-recon")
    path.write_text(
        path.read_text(encoding="utf-8").replace("effort: medium", "effort: max"),
        encoding="utf-8",
    )
    assert generate_seats.main(["--root", str(root), "--check"]) == 1
    assert "schema_stale: .claude/agents/cti-recon.md" in capsys.readouterr().err


def test_a_hand_edited_body_is_caught_too(root: Path) -> None:
    """A seat file is wholly generated, so its instructions drift the way its pair does."""
    assert generate_seats.main(["--root", str(root)]) == 0
    path = agent(root, "cti-implementer")
    path.write_text(path.read_text(encoding="utf-8") + "\nAlso, skip the gate.\n", encoding="utf-8")
    assert generate_seats.main(["--root", str(root), "--check"]) == 1


def test_a_missing_seat_file_is_caught(root: Path) -> None:
    assert generate_seats.main(["--root", str(root)]) == 0
    agent(root, "cti-planner").unlink()
    assert generate_seats.main(["--root", str(root), "--check"]) == 1


def test_a_registry_change_with_no_regeneration_is_caught(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The direction the schema export taught: the source moved and the surface did not."""
    assert generate_seats.main(["--root", str(root)]) == 0
    cheaper = dispatch.PROFILES["haiku-medium"]._replace(effort="low")
    monkeypatch.setitem(dispatch.PROFILES, "haiku-medium", cheaper)
    assert generate_seats.main(["--root", str(root), "--check"]) == 1


def test_a_seat_the_registry_does_not_carry_is_named_as_a_stray(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mechanical` is retired by ADR-0071 ruling 2; a file for it is stale, not extra."""
    assert generate_seats.main(["--root", str(root)]) == 0
    agent(root, "cti-mechanical").write_text(
        "---\nmodel: sonnet\neffort: medium\n---\n", encoding="utf-8"
    )
    assert generate_seats.main(["--root", str(root), "--check"]) == 1
    assert "cti-mechanical.md is a seat the registry does not carry" in capsys.readouterr().err


def test_writing_removes_a_stray_so_the_check_names_nothing_it_cannot_fix(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert generate_seats.main(["--root", str(root)]) == 0
    agent(root, "cti-mechanical").write_text(
        "---\nmodel: sonnet\neffort: medium\n---\n", encoding="utf-8"
    )
    assert generate_seats.main(["--root", str(root)]) == 0
    assert not agent(root, "cti-mechanical").exists()
    assert "retired: .claude/agents/cti-mechanical.md" in capsys.readouterr().out


# ------------------------------------------------- the skill: the pair moves, nothing else


def test_the_skills_pair_is_retuned_and_its_prose_is_left_exactly_as_authored(
    root: Path,
) -> None:
    path = root / SKILL
    before = path.read_text(encoding="utf-8")
    drifted = before.replace("model: opus", "model: haiku").replace("effort: xhigh", "effort: low")
    path.write_text(drifted, encoding="utf-8")
    assert generate_seats.main(["--root", str(root)]) == 0
    assert path.read_text(encoding="utf-8") == before


def test_a_hand_edited_skill_pair_is_caught(root: Path) -> None:
    path = root / SKILL
    path.write_text(
        path.read_text(encoding="utf-8").replace("effort: xhigh", "effort: low"), encoding="utf-8"
    )
    assert generate_seats.main(["--root", str(root), "--check"]) == 1


def test_retune_refuses_a_file_with_no_frontmatter() -> None:
    with pytest.raises(generate_seats.SeatSurfaceError, match="no `---` frontmatter block"):
        generate_seats.retune("x", "Body only.\n", dispatch.PROFILES["opus-xhigh"])


def test_retune_refuses_an_unterminated_frontmatter_block() -> None:
    with pytest.raises(generate_seats.SeatSurfaceError, match="never closed"):
        generate_seats.retune("x", "---\nmodel: opus\n", dispatch.PROFILES["opus-xhigh"])


def test_retune_refuses_a_half_declared_pair_rather_than_adding_the_other_half() -> None:
    """A skill declares both halves or neither; inventing the missing one hides the defect."""
    text = "---\nname: s\nmodel: opus\n---\n\nBody.\n"
    with pytest.raises(generate_seats.SeatSurfaceError, match="`effort:` to rewrite"):
        generate_seats.retune("x", text, dispatch.PROFILES["opus-xhigh"])


def test_retune_ignores_an_indented_key_because_the_loader_does() -> None:
    """The same reading `check_seat_config` does: an indented key is not the declaration."""
    text = "---\n  model: opus\neffort: low\n---\n\nBody.\n"
    with pytest.raises(generate_seats.SeatSurfaceError, match="`model:` to rewrite"):
        generate_seats.retune("x", text, dispatch.PROFILES["opus-xhigh"])


def test_retune_moves_both_halves_and_touches_no_other_key() -> None:
    text = "---\nname: s\nmodel: haiku\neffort: low\nargument-hint: [x]\n---\n\nBody.\n"
    moved = generate_seats.retune("x", text, dispatch.PROFILES["opus-xhigh"])
    assert check_seat_config.frontmatter(moved) == {
        "name": "s",
        "model": "opus",
        "effort": "xhigh",
        "argument-hint": "[x]",
    }
    assert moved.endswith("---\n\nBody.\n")


def test_an_absent_skill_refuses_rather_than_being_written_from_nothing(root: Path) -> None:
    (root / SKILL).unlink()
    assert generate_seats.main(["--root", str(root)]) == 1
    assert not agent(root, "cti-implementer").exists()


# --------------------------------------------------------------------- the recorded gap


def test_the_other_harnesses_absent_surface_is_recorded_with_its_failure_mode() -> None:
    """ADR-0071 ruling 7, as data rather than as prose that can rot away from the code."""
    recorded = dict(generate_seats.UNGENERATED_HARNESSES)
    assert set(recorded) == {"codex"}
    assert "unenforced" in recorded["codex"]
    assert "fail open silently" in recorded["codex"]


def test_the_gap_is_reported_when_the_surfaces_are_written(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Where a reader meets it: the terminal of whoever regenerates the surfaces."""
    assert generate_seats.main(["--root", str(root)]) == 0
    assert "ungenerated: codex:" in capsys.readouterr().out


def test_the_gap_is_recorded_where_a_reader_will_meet_it() -> None:
    """Not instructions in a file that fails open — a section of the design document."""
    doc = (REPO / "docs" / "multi-provider-dispatch.md").read_text(encoding="utf-8")
    assert "no seat-definition surface" in doc


# ------------------------------------------------------------------ the repository itself


def test_the_surfaces_the_repository_ships_are_the_registrys() -> None:
    """The one thing no fixture can check: the registry moved and the surfaces did not."""
    assert generate_seats.main(["--check"]) == 0


def test_no_seat_pair_is_maintained_by_hand_in_the_always_loaded_prefix() -> None:
    """#324's fourth criterion, on the surface that carried the second copy.

    AGENTS.md used to enumerate every seat file beside its pair, so a registry change had
    to be mirrored into a paragraph nothing checked. The pairs are gone; the sentence that
    replaced them points at the generator.
    """
    prefix = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "tools/generate_seats.py" in prefix
    for stale_pair in ("`cti-implementer` opus/high", "`cti-recon` haiku/low"):
        assert stale_pair not in prefix
