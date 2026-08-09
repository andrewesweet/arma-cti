"""Tests for the cross-harness edit-payload reader, `tools/edit_payload.py` (#273).

Two properties carry the module, and they pull in opposite directions, which is why both
are pinned here. A **read** must find every path the call writes, whatever key the payload
carries it under and whichever of the four V4A actions names it — a path missed by the
reader is a gated write the guard never sees. An **unreadable** call must come back `None`
and never an empty tuple, because a caller that denies reads the empty tuple as "writes
nothing" and approves. That is the #94 findings 1-2 shape, one layer in from where it was
first found.

The Claude Code leg is here too, unglamorous but load-bearing: this reader replaces a
direct `tool_input["file_path"]` in three hooks, so the payload those hooks have always
handled has to come back out of it unchanged.
"""

from __future__ import annotations

from conftest import load_tool

edit_payload = load_tool("edit_payload")

GENERATED = "addons/main/generated/commands.hpp"
SPEC = "tests/specs/campaign.yaml"


def envelope(*body: str) -> str:
    """Wrap patch action lines in the V4A envelope Codex sends."""
    return "\n".join(("*** Begin Patch", *body, "*** End Patch"))


# --- the Claude Code leg, unchanged -----------------------------------------


def test_an_edit_names_its_file_path() -> None:
    assert edit_payload.edited_paths({"file_path": SPEC}) == (SPEC,)


def test_a_write_names_its_file_path_beside_its_content() -> None:
    call = {"file_path": "src/cti_daemon/port.py", "content": "x = 1\n"}
    assert edit_payload.edited_paths(call) == ("src/cti_daemon/port.py",)


def test_an_empty_file_path_is_not_a_path() -> None:
    """An empty `file_path` is the absence this whole issue is about, not a target."""
    assert edit_payload.edited_paths({"file_path": ""}) is None


def test_a_call_with_no_recognisable_key_is_unreadable() -> None:
    assert edit_payload.edited_paths({}) is None


def test_a_non_mapping_call_is_unreadable() -> None:
    assert edit_payload.edited_paths("*** Begin Patch") is None


def test_a_non_string_file_path_is_not_taken_as_a_path() -> None:
    assert edit_payload.edited_paths({"file_path": 7}) is None


# --- the patch leg: every action names a written path ------------------------


def test_an_update_names_the_file_it_rewrites() -> None:
    call = {"command": envelope(f"*** Update File: {GENERATED}", "@@", "-a", "+b")}
    assert edit_payload.edited_paths(call) == (GENERATED,)


def test_an_add_names_the_file_it_creates() -> None:
    call = {"command": envelope("*** Add File: docs/new.md", "+hello")}
    assert edit_payload.edited_paths(call) == ("docs/new.md",)


def test_a_delete_names_the_file_it_removes() -> None:
    call = {"command": envelope(f"*** Delete File: {SPEC}")}
    assert edit_payload.edited_paths(call) == (SPEC,)


def test_a_move_names_both_ends_because_both_are_written() -> None:
    call = {
        "command": envelope(
            "*** Update File: tools/old.py",
            f"*** Move to: {SPEC}",
            "@@",
            "-a",
            "+b",
        )
    }
    assert edit_payload.edited_paths(call) == ("tools/old.py", SPEC)


def test_one_patch_touching_several_files_names_all_of_them() -> None:
    call = {
        "command": envelope(
            "*** Update File: tools/one.py",
            "@@",
            "-a",
            "+b",
            "*** Add File: tools/two.py",
            "+x = 1",
        )
    }
    assert edit_payload.edited_paths(call) == ("tools/one.py", "tools/two.py")


# --- the envelope is found wherever the payload puts it ----------------------


def test_a_patch_under_input_is_found() -> None:
    call = {"input": envelope("*** Add File: docs/new.md", "+hello")}
    assert edit_payload.edited_paths(call) == ("docs/new.md",)


def test_a_patch_in_a_shell_style_argument_list_is_found() -> None:
    """Codex's shell form hands the patch as the second element of an argv list."""
    call = {"command": ["apply_patch", envelope(f"*** Update File: {SPEC}", "@@", "-a", "+b")]}
    assert edit_payload.edited_paths(call) == (SPEC,)


def test_a_patch_under_an_unlisted_key_is_still_found() -> None:
    """The likely-key list is an optimisation; an unforeseen key must not hide a write."""
    call = {"unforeseen_key": envelope(f"*** Delete File: {GENERATED}")}
    assert edit_payload.edited_paths(call) == (GENERATED,)


def test_the_first_string_carrying_a_patch_wins_over_a_later_one() -> None:
    call = {
        "note": envelope("*** Add File: decoy.md", "+x"),
        "command": envelope("*** Add File: real.md", "+x"),
    }
    assert edit_payload.edited_paths(call) == ("real.md",)


# --- unreadable is not empty -------------------------------------------------


def test_an_envelope_naming_nothing_is_unreadable_rather_than_empty() -> None:
    """The distinction the guard's fail-closed branch rests on."""
    assert edit_payload.patch_targets(envelope("@@", "-a", "+b")) is None


def test_a_marker_with_no_path_after_it_names_nothing() -> None:
    assert edit_payload.patch_targets(envelope("*** Update File:")) is None


def test_a_string_without_the_sentinel_is_not_a_patch() -> None:
    assert edit_payload.patch_targets("*** Update File: tools/one.py") is None


def test_a_command_that_is_not_a_patch_is_unreadable() -> None:
    assert edit_payload.edited_paths({"command": "git status"}) is None


def test_a_marker_quoted_inside_the_patch_body_is_content_not_an_action() -> None:
    """Body lines carry a prefix; an unprefixed marker is the action line."""
    call = {
        "command": envelope(
            "*** Update File: docs/hooks.md",
            "@@",
            "+quoting the format: *** Add File: not/a/real/path.py",
            "-*** Delete File: also/not/real.py",
            " *** Move to: nor/this.py",
        )
    }
    assert edit_payload.edited_paths(call) == ("docs/hooks.md",)


def test_a_deeply_nested_patch_is_unreadable_rather_than_guessed_at() -> None:
    call = {"command": [["apply_patch", envelope(f"*** Update File: {SPEC}")]]}
    assert edit_payload.edited_paths(call) is None
