"""The Claude seat surfaces are the dispatch registry's, and drift is caught (#324).

Both declaration surfaces fail open (ADR-0068): a drifted pair does not refuse, the seat
answers at whatever tier the session had, and the only trace is a cheaper arm than the one
the map ratified. `tools/check_seat_config.py` already asserts that a pair is *declared and
valid*; what is tested here is the half that was missing — that it is the *registry's*, and
that a hand edit, a retired seat's file, or an un-regenerated registry change is a
`schema_stale` red rather than a silently obeyed file.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Final

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

dispatch = load_tool("dispatch")
generate_seats = load_tool("generate_seats")
check_seat_config = load_tool("check_seat_config")

SKILL = ".claude/skills/interlocutor/SKILL.md"
JUSTFILE = REPO / "justfile"

MODEL_ROLES = "## Model roles"


def model_roles_section(prefix: str) -> str:
    """AGENTS.md's ratified mapping, from its heading to the next one.

    The one region of the always-loaded prefix that narrates tiers by hand on purpose. It is
    #329's surface; excising it is how the pair check over the rest of the file can be as
    wide as the notations a human writes without this issue reaching into that section.
    """
    start = prefix.index(MODEL_ROLES)
    end = prefix.index("\n## ", start + len(MODEL_ROLES))
    return prefix[start:end]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Build a repository root carrying only what the generator reads and writes."""
    skill = tmp_path / SKILL
    skill.parent.mkdir(parents=True)
    shutil.copy(REPO / SKILL, skill)
    (tmp_path / ".claude" / "agents").mkdir()
    return tmp_path


def agent(root: Path, stem: str) -> Path:
    """Resolve the seat file `stem` names under this root."""
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


def test_the_non_native_head_of_a_preference_list_is_not_what_a_claude_seat_declares() -> None:
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
    non_native = dispatch.SEATS["planner"]._replace(preference=("codex-sol-xhigh",))
    monkeypatch.setitem(dispatch.SEATS, "planner", non_native)
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


def test_retuning_the_skill_to_another_profile_and_regenerating_restores_its_bytes(
    root: Path,
) -> None:
    """A round trip, which is what this asserts (#324, review round 2, claim 4).

    The old name said the prose was left exactly as authored, which the round trip cannot
    show: it drifts the frontmatter and puts it back. What it does show is that the write
    path is the inverse of a retune to any other profile — nothing accumulates, and no byte
    outside the declared pair moves in either direction.
    """
    path = root / SKILL
    before = path.read_text(encoding="utf-8")
    path.write_text(
        generate_seats.retune(SKILL, before, dispatch.PROFILES["haiku-medium"]), encoding="utf-8"
    )
    assert path.read_text(encoding="utf-8") != before
    assert generate_seats.main(["--root", str(root)]) == 0
    assert path.read_text(encoding="utf-8") == before


def hand_edit_the_skill(root: Path, was: str, now: str) -> None:
    """Write the surfaces, then drift one string in the skill and nothing else.

    Writing first is the part that matters: a bare fixture has no agent files at all, so
    `--check` reds on the four missing ones whatever the skill says, and a drift test that
    skips this step asserts nothing (#324, review round 1 — found while proving these tests
    fail on the defect they name).
    """
    assert generate_seats.main(["--root", str(root)]) == 0
    assert generate_seats.main(["--root", str(root), "--check"]) == 0
    path = root / SKILL
    before = path.read_text(encoding="utf-8")
    drifted = before.replace(was, now)
    assert drifted != before, f"nothing in the skill said {was!r}"
    path.write_text(drifted, encoding="utf-8")


def test_a_hand_edited_skill_pair_is_caught(root: Path) -> None:
    hand_edit_the_skill(root, "effort: xhigh", "effort: low")
    assert generate_seats.main(["--root", str(root), "--check"]) == 1


def test_a_hand_edited_session_command_in_the_skill_is_caught(root: Path) -> None:
    """`/effort xhigh` is the pair in a second vocabulary, so it drifts like the first."""
    profile = generate_seats.native_profile("interlocutor")
    hand_edit_the_skill(root, f"`/effort {profile.effort}`", "`/effort low`")
    assert generate_seats.main(["--root", str(root), "--check"]) == 1


def test_a_hand_edited_narrated_pair_in_the_skill_is_caught(root: Path) -> None:
    """The third notation: `at opus/xhigh` in a sentence, which used to be maintained by hand."""
    profile = generate_seats.native_profile("interlocutor")
    hand_edit_the_skill(root, f"{profile.model}/{profile.effort}", f"{profile.model}/high")
    assert generate_seats.main(["--root", str(root), "--check"]) == 1


def test_a_drifted_sentence_is_reported_and_not_rewritten(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#324, review round 2, claim 2: the gate's remedy must not edit a human's sentence.

    `just generate` is what `--check` sends the reader to run, so the writing path is where
    a rewriting generator would do its damage. It writes the frontmatter it owns, reports
    the sentence it does not, and ends non-zero — and the sentence is on disk unchanged.
    """
    profile = generate_seats.native_profile("interlocutor")
    hand_edit_the_skill(root, f"{profile.model}/{profile.effort}", f"{profile.model}/high")
    drifted = (root / SKILL).read_text(encoding="utf-8")
    assert generate_seats.main(["--root", str(root)]) == 1
    assert (root / SKILL).read_text(encoding="utf-8") == drifted
    assert f"pair_drift: {SKILL} states `{profile.model}/high`" in capsys.readouterr().err


def test_a_sentence_comparing_two_seats_reds_rather_than_being_rewritten_to_compare_one(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reviewer's own example, as the regression test for the design that replaced it.

    A generator owning every matching string turns this sentence into one comparing
    `opus/xhigh` with itself, silently, when the human runs the remedy the gate told them to
    run. Now it is a finding, the bytes do not move, and the stated cost of the choice is
    visible here too: the check cannot tell whose tier a narrated pair is, so a skill that
    mentions another seat's must expect this red.
    """
    path = root / SKILL
    assert generate_seats.main(["--root", str(root)]) == 0
    sentence = "\nCompare recon at haiku/medium with the interlocutor at opus/xhigh.\n"
    path.write_text(path.read_text(encoding="utf-8") + sentence, encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    assert generate_seats.main(["--root", str(root), "--check"]) == 1
    assert generate_seats.main(["--root", str(root)]) == 1
    assert path.read_text(encoding="utf-8") == before
    assert "states `haiku/medium`" in capsys.readouterr().err


def test_a_skill_naming_one_session_command_and_not_the_other_is_a_finding() -> None:
    """Half a tier set by advice is ADR-0068's fail-open reached without touching frontmatter."""
    text = "---\nmodel: opus\neffort: xhigh\n---\n\nRun `/model opus` to set the session.\n"
    found = generate_seats.prose_findings("x", text, dispatch.PROFILES["opus-xhigh"])
    assert [line for line in found if "`/model` without `/effort`" in line] != []


def test_a_skill_that_names_no_session_command_states_no_pair_to_check() -> None:
    """Not every skill talks about setting a session; the commands are optional, not implied."""
    text = "---\nmodel: haiku\neffort: low\n---\n\nBody with no commands.\n"
    assert generate_seats.prose_findings("x", text, dispatch.PROFILES["opus-xhigh"]) == []
    moved = generate_seats.retune("x", text, dispatch.PROFILES["opus-xhigh"])
    assert moved == "---\nmodel: opus\neffort: xhigh\n---\n\nBody with no commands.\n"


def test_retune_moves_the_declared_pair_and_leaves_every_narrated_one_for_a_human() -> None:
    """The division of labour, in one file: the frontmatter is written, the sentence is not."""
    text = (
        "---\nmodel: haiku\neffort: low\n---\n\n"
        "The seat runs at haiku/low; `/model haiku` and `/effort low` set the session.\n"
    )
    moved = generate_seats.retune("x", text, dispatch.PROFILES["opus-xhigh"])
    assert moved.endswith(
        "The seat runs at haiku/low; `/model haiku` and `/effort low` set the session.\n"
    )
    assert check_seat_config.frontmatter(moved) == {"model": "opus", "effort": "xhigh"}
    found = generate_seats.prose_findings("x", moved, dispatch.PROFILES["opus-xhigh"])
    assert [line for line in found if "states `haiku/low`" in line] != []
    assert [line for line in found if "type `/model haiku`" in line] != []
    assert [line for line in found if "type `/effort low`" in line] != []


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


def test_the_pair_vocabulary_reads_every_notation_this_repository_writes() -> None:
    """#324, review round 2, claim 3: a property that sees one notation is a substring check.

    So the notations are enumerated, each one taken from prose that exists here — the slash
    pair, `describe`'s own rendering, the bare form the Model roles bullets use after "run
    at", and the comma form those bullets lead with. The positive controls come first,
    because an assertion that finds nothing is worth what its pattern is worth.

    The limit is stated rather than implied, and it is a real one: this reads notations, not
    meanings. `opus-xhigh` is a profile name and legitimate; "the top effort on opus" is a
    paraphrase no pattern catches; a tier split across two sentences is invisible. What the
    check buys is that the shapes a human actually types cannot be written by hand beside a
    derived one and go unnoticed. For a live pair a reader is still sent to the generated
    seat files and `just dispatch --list`.
    """
    assert ("opus", "xhigh") in generate_seats.stated_pairs("the seat runs at opus/xhigh today")
    assert ("opus", "low") in generate_seats.stated_pairs("cti-implementer uses opus at low effort")
    assert ("opus", "xhigh") in generate_seats.stated_pairs("decision sessions run at opus xhigh")
    assert ("fable", "high") in generate_seats.stated_pairs("- **fable[1m], effort high** — retros")
    assert generate_seats.SESSION_COMMAND.findall("type `/model opus` first") == [("model", "opus")]
    assert generate_seats.stated_pairs("dispatched on `opus-xhigh`, the top effort on opus") == []


def test_no_seat_pair_is_maintained_by_hand_in_the_always_loaded_prefix() -> None:
    """#324's fourth criterion, on the surface that carried the second copy.

    AGENTS.md used to enumerate every seat file beside its pair, so a registry change had
    to be mirrored into a paragraph nothing checked. The pairs are gone; the sentence that
    replaced them points at the generator.

    Asserted as the property rather than as two known-stale strings, which is what let the
    workflow paragraph go on calling the interlocutor `opus/xhigh` with this test green
    (#324, review round 1, claim 3). The vocabulary is the registry's own native pairs, so
    a profile added there widens the check without anyone remembering to.

    Scoped by region, not by notation (#324, review round 2, claim 3). The slash notation is
    checked over the whole file, because it can only ever be a pair. The three prose
    notations are checked everywhere *except* the Model roles section, which narrates the
    ratified mapping by hand — `opus[1m], effort xhigh`, `/model opus`, `run at opus
    xhigh` — and is #329's surface, not this issue's. Excluding the section rather than the
    notations is what keeps "cti-implementer uses opus at low effort" a red anywhere else in
    the file.
    """
    prefix = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "tools/generate_seats.py" in prefix
    assert generate_seats.SLASH_PAIR.findall(prefix) == []
    narrated = model_roles_section(prefix)
    assert generate_seats.stated_pairs(narrated) != []
    assert generate_seats.SESSION_COMMAND.findall(narrated) != []
    elsewhere = prefix.replace(narrated, "")
    assert generate_seats.stated_pairs(elsewhere) == []
    assert generate_seats.SESSION_COMMAND.findall(elsewhere) == []


def test_no_hand_written_pair_in_a_skill_survives_a_registry_move_unreported() -> None:
    """Criterion 4 on the other surface, restated for a check that does not rewrite.

    Only the frontmatter used to be derived, so the interlocutor's description, its opening
    sentence and its `/model` and `/effort` commands all went on saying `opus/xhigh` while
    `--check` passed. Since round 2 those sentences are not rewritten either — so the
    property is not that the old pair is gone from the bytes, which would be the rewriting
    design, but that every copy of it is *named*: move the registry under the shipped file
    and each stated pair and each session command turns into its own finding.
    """
    for surface in generate_seats.SKILL_SURFACES:
        was = generate_seats.native_profile(surface.seat)
        other = dispatch.PROFILES["haiku-medium"]
        assert (other.model, other.effort) != (was.model, was.effort)
        text = (REPO / surface.path).read_text(encoding="utf-8")
        stated = generate_seats.stated_pairs(text)
        commands = generate_seats.SESSION_COMMAND.findall(text)
        assert stated != []
        assert commands != []
        found = generate_seats.prose_findings(surface.path, text, other)
        assert len(found) == len(stated) + len(commands)
        assert all(line.startswith(f"pair_drift: {surface.path} ") for line in found)


def test_no_authored_agent_surface_text_carries_a_pair() -> None:
    """The wholly generated files have the same hazard in the halves a human writes.

    `describe` derives the tier into each description; a blurb or a body that also stated
    one would be a second copy inside the generator itself, and `--check` could not see it.
    Every notation, not just the slash one: "recon runs on haiku at low effort" in a body is
    the same duplicate wearing different punctuation (#324, review round 2, claim 3).
    """
    assert generate_seats.stated_pairs("recon runs on haiku at low effort") != []
    assert generate_seats.SESSION_COMMAND.search("type `/model opus` first") is not None
    for surface in generate_seats.AGENT_SURFACES:
        authored = f"{surface.blurb}\n{surface.body}"
        assert generate_seats.stated_pairs(authored) == []
        assert generate_seats.SESSION_COMMAND.findall(authored) == []


# --------------------------------------------------------------------- the gate is wired
#
# #324, review rounds 1 and 2, claim 1. The first attempt asserted that `check:` mentions
# `check-generated` and that the recipe body contains the command. Both survive every way of
# taking the checker out of the gate while leaving its name in the file — point `check:` at
# a no-op `check-generated-disabled` and orphan the real recipe, or keep the recipe and put
# the command in a shebang branch that never runs. So the assertion moved from the text of
# the wiring to its effect: drift a seat file, run the repository's own `just check`, and
# require it to go red.
#
# Every rung but this one is stubbed on PATH. That is not a weaker gate, it is a smaller
# subject: `cog`, `hemtt`, `gitleaks`, `cargo` and the other `uv` steps are gates with their
# own tests, and running them here would test them a second time instead of testing whether
# this one is reachable. What is not stubbed is `just` itself, the repository's real
# justfile, and `tools/generate_seats.py --check` — the whole chain under test.

STUB: Final = "#!/usr/bin/env bash\nexit 0\n"

# `uv run python tools/generate_seats.py --check` is the one command allowed through to a
# real interpreter; `${@:3}` is the argument list with `run python` stripped. The
# interpreter is this test run's own, so no environment is resolved and nothing is installed.
UV_STUB: Final = """#!/usr/bin/env bash
case "$*" in
  *tools/generate_seats.py*) exec {python} "${{@:3}}" ;;
  *) exit 0 ;;
esac
"""


def gate(root: Path, justfile: str) -> subprocess.CompletedProcess[str]:
    """Run `just check` over this root, against this justfile, with the other rungs stubbed."""
    just = shutil.which("just")
    # Not a skip: `just` is the project's whole command surface (CLAUDE.md), so a run
    # without it is a run that could not check the thing, which is not a pass.
    assert just is not None, "`just` is absent; this gate could not run, so it is not green"
    (root / "justfile").write_text(justfile, encoding="utf-8")
    stubs = root / "stub-bin"
    stubs.mkdir(exist_ok=True)
    for name in ("cog", "hemtt", "gitleaks", "cargo"):
        (stubs / name).write_text(STUB, encoding="utf-8")
    (stubs / "uv").write_text(UV_STUB.format(python=shlex.quote(sys.executable)), encoding="utf-8")
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    tools = root / "tools"
    if not tools.exists():
        tools.symlink_to(REPO / "tools")
    return subprocess.run(  # noqa: S603 — fixed argv, no shell, no interpolation
        [just, "check"],
        cwd=root,
        env={**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )


def evade(justfile: str, recipe: str) -> str:
    """Replace `check-generated`'s recipe block, keeping every line before and after it."""
    lines = justfile.split("\n")
    start = lines.index("check-generated:")
    end = lines.index("", start)
    return "\n".join([*lines[:start], *recipe.split("\n"), *lines[end:]])


def drift_a_seat(root: Path) -> None:
    """Put a cheaper tier in a generated seat file — the drift the whole module is about."""
    path = agent(root, "cti-recon")
    path.write_text(
        path.read_text(encoding="utf-8").replace("effort: medium", "effort: max"), encoding="utf-8"
    )


def test_a_drifted_seat_file_turns_just_check_red(root: Path) -> None:
    """The effect, not the wiring's text: run the chain and require the verdict."""
    assert generate_seats.main(["--root", str(root)]) == 0
    clean = gate(root, JUSTFILE.read_text(encoding="utf-8"))
    assert clean.returncode == 0, clean.stderr
    drift_a_seat(root)
    red = gate(root, JUSTFILE.read_text(encoding="utf-8"))
    assert red.returncode != 0
    assert "schema_stale: .claude/agents/cti-recon.md" in red.stderr


def test_orphaning_the_recipe_takes_the_check_off_the_gate_with_its_name_intact(
    root: Path,
) -> None:
    """Negative control: the route the previous assertion could not see.

    `check:` names `check-generated-disabled`, which no-ops, and the real recipe is left in
    the file for anyone reading it. Both of round 1's assertions still hold on this text —
    asserted here, so the control states exactly what it is a control for — and the drifted
    seat sails through.
    """
    assert generate_seats.main(["--root", str(root)]) == 0
    drift_a_seat(root)
    text = JUSTFILE.read_text(encoding="utf-8")
    orphaned = (
        text.replace(
            "check: check-commits check-generated ",
            "check: check-commits check-generated-disabled ",
            1,
        )
        + "\ncheck-generated-disabled:\n    @true\n"
    )
    assert orphaned != text
    assert "check-generated" in next(
        line for line in orphaned.splitlines() if line.startswith("check:")
    )
    assert "uv run python tools/generate_seats.py --check" in orphaned
    assert gate(root, orphaned).returncode == 0


def test_a_command_in_an_unreachable_branch_takes_the_check_off_the_gate_too(
    root: Path,
) -> None:
    """Negative control, second route: a shebang recipe whose branch never executes."""
    assert generate_seats.main(["--root", str(root)]) == 0
    drift_a_seat(root)
    text = JUSTFILE.read_text(encoding="utf-8")
    unreachable = evade(
        text,
        "check-generated:\n"
        "    #!/usr/bin/env bash\n"
        "    if false; then\n"
        "        uv run python tools/export_command_schema.py --check\n"
        "        uv run python tools/generate_seats.py --check\n"
        "    fi",
    )
    assert unreachable != text
    assert "uv run python tools/generate_seats.py --check" in unreachable
    assert gate(root, unreachable).returncode == 0
