"""Tests for the scoped SQF command bans and the locality-guard rule.

The gate exists because HEMTT can only ban a command everywhere or nowhere.
Its whole value is the scoping, so that is what these tests pin: the adapter
may use the command, nothing else may, and prose about the command is not a
use of it.

The locality-guard rule (ADR-0040) is pinned in both directions, because a rule
that only ever passes is indistinguishable from one that does not run: the
hand-rolled guard is a finding, and the two shapes that are *not* a hand-rolled
guard — the macro, and `isServer` used to branch rather than to refuse — are not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

check_sqf_bans = load_tool("check_sqf_bans")

ADAPTER = "addons/main/functions/fn_prngNext.sqf"
DESYNC_LOAD = "addons/main/functions/fn_desyncLoad.sqf"
OTHER = "addons/main/functions/fn_other.sqf"


def test_the_adapter_may_use_the_banned_command() -> None:
    assert check_sqf_bans.scan_source("_seed random 1", ADAPTER) == []


def test_any_other_file_may_not() -> None:
    findings = check_sqf_bans.scan_source("private _x = random 1;", OTHER)
    assert [(f.line, f.command) for f in findings] == [(1, "random")]


def test_the_message_names_the_file_line_and_adapter() -> None:
    (finding,) = check_sqf_bans.scan_source("\n\nprivate _x = random 1;", OTHER)
    rendered = str(finding)
    assert rendered.startswith(f"{OTHER}:3: `random` is banned outside {ADAPTER}")


def test_line_comments_are_not_uses() -> None:
    assert check_sqf_bans.scan_source("// never call random here\n", OTHER) == []


def test_block_comments_are_not_uses() -> None:
    source = "/*\n * Draws through random.\n */\nprivate _x = 1;\n"
    assert check_sqf_bans.scan_source(source, OTHER) == []


def test_string_literals_are_not_uses() -> None:
    assert check_sqf_bans.scan_source('diag_log "random draw";', OTHER) == []


def test_a_doubled_quote_escape_does_not_end_the_literal() -> None:
    # The closing "" is an escaped quote, so `random` is still inside the string.
    source = 'private _s = "he said ""random"" loudly";'
    assert check_sqf_bans.scan_source(source, OTHER) == []


def test_an_unterminated_comment_swallows_the_rest_of_the_file() -> None:
    assert check_sqf_bans.scan_source("/* random\nrandom\n", OTHER) == []


def test_line_numbers_survive_stripped_blocks() -> None:
    source = '/*\n random\n*/\n"random"\nrandom 1;\n'
    (finding,) = check_sqf_bans.scan_source(source, OTHER)
    assert finding.line == 5


def test_matching_is_case_insensitive_because_sqf_is() -> None:
    findings = check_sqf_bans.scan_source("RaNdOm 1;", OTHER)
    assert [f.command for f in findings] == ["random"]


def test_a_longer_identifier_is_not_the_banned_command() -> None:
    source = "private _random = selectRandom _list; _list call cti_fnc_randomish;"
    assert check_sqf_bans.scan_source(source, OTHER) == []


def test_the_order_path_may_not_transfer_a_squad_off_the_server() -> None:
    # ADR-0039. setCurrentWaypoint is documented arg=local, so an Order issued
    # to a group the server does not own is written and never taken up.
    findings = check_sqf_bans.scan_source("_group setGroupOwner _target;", OTHER)
    assert [(f.line, f.command) for f in findings] == [(1, "setGroupOwner")]


def test_the_desync_diagnostic_keeps_its_exemption() -> None:
    assert check_sqf_bans.scan_source("_group setGroupOwner _target;", DESYNC_LOAD) == []


def test_the_desync_exemption_does_not_extend_to_the_prng_adapter() -> None:
    # Each ban carries its own allowed set; being exempt from one is not
    # being exempt from the other.
    findings = check_sqf_bans.scan_source("_group setGroupOwner _target;", ADAPTER)
    assert [f.command for f in findings] == ["setGroupOwner"]


def test_the_ownership_message_cites_the_rule_rather_than_an_adapter() -> None:
    (finding,) = check_sqf_bans.scan_source("_group setGroupOwner 3;", OTHER)
    rendered = str(finding)
    assert rendered.startswith(f"{OTHER}:1: `setGroupOwner` is banned outside {DESYNC_LOAD}")
    assert rendered.endswith("Squads are never transferred off the server (ADR-0039).")


def test_prose_about_ownership_transfer_is_not_a_transfer() -> None:
    source = '// setGroupOwner hands the group over\ndiag_log "setGroupOwner";\n'
    assert check_sqf_bans.scan_source(source, OTHER) == []


def test_a_hand_rolled_server_guard_is_a_finding() -> None:
    findings = check_sqf_bans.scan_source("if (!isServer) exitWith { false };", OTHER)
    assert [(f.line, f.command) for f in findings] == [(1, "isServer")]


def test_a_hand_rolled_interface_guard_is_a_finding() -> None:
    findings = check_sqf_bans.scan_source("if (!hasInterface) exitWith {};", OTHER)
    assert [(f.line, f.command) for f in findings] == [(1, "hasInterface")]


def test_the_other_spelling_of_the_negation_is_the_same_guard() -> None:
    findings = check_sqf_bans.scan_source("if !(isServer) exitWith { 0 };", OTHER)
    assert [f.command for f in findings] == ["isServer"]


def test_the_guard_message_names_the_macros_and_the_alternative() -> None:
    (finding,) = check_sqf_bans.scan_source("\nif (!isServer) exitWith { 0 };", OTHER)
    rendered = str(finding)
    assert rendered.startswith(f"{OTHER}:2: a bare `isServer` guard")
    assert "SERVER_ONLY / INTERFACE_ONLY" in rendered
    assert "delete the guard" in rendered


def test_the_macro_is_not_a_hand_rolled_guard() -> None:
    # What every kept guard now looks like. The expansion lives in the .hpp,
    # which is not SQF and is not scanned.
    assert check_sqf_bans.scan_source("SERVER_ONLY(scriptNull);", OTHER) == []
    assert check_sqf_bans.scan_source("INTERFACE_ONLY(nil);", OTHER) == []


def test_asking_the_machine_role_to_branch_is_not_a_guard() -> None:
    # missions/spike.Stratis/init.sqf finds the headless client this way. It
    # refuses nothing and returns no sentinel, so there is nothing to log.
    source = "if (!isServer && {!hasInterface}) then { cti_hc = clientOwner; };"
    assert check_sqf_bans.scan_source(source, OTHER) == []
    assert check_sqf_bans.scan_source("if (hasInterface) then { x = 1; };", OTHER) == []


def test_a_guard_in_a_comment_is_not_a_guard() -> None:
    assert check_sqf_bans.scan_source("// if (!isServer) exitWith {};\n", OTHER) == []


def test_the_repository_is_clean() -> None:
    assert check_sqf_bans.scan_tree(REPO) == []


def test_the_vendored_wiki_is_not_scanned() -> None:
    scanned = {p.relative_to(REPO).as_posix() for p in check_sqf_bans.sqf_files(REPO)}
    assert scanned, "expected to find our own SQF"
    assert not any(path.startswith("docs/") for path in scanned)


def test_nested_agent_worktrees_are_not_scanned(tmp_path: Path) -> None:
    # A worktree under .claude/worktrees/ is a whole checkout: its files match
    # the allowlist only with the worktree prefix stripped, so scanning it from
    # the outer root reports the adapter itself as a violation. Each worktree
    # runs this gate on its own tree; the outer run must not descend into it.
    ours = tmp_path / "addons" / "main" / "functions" / "fn_other.sqf"
    nested = tmp_path / ".claude" / "worktrees" / "wt" / ADAPTER
    for path in (ours, nested):
        path.parent.mkdir(parents=True)
        path.write_text("random 1;\n", encoding="utf-8")
    scanned = {p.relative_to(tmp_path).as_posix() for p in check_sqf_bans.sqf_files(tmp_path)}
    assert scanned == {"addons/main/functions/fn_other.sqf"}
