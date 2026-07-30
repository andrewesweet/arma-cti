"""Tests for the scoped SQF command bans.

The gate exists because HEMTT can only ban a command everywhere or nowhere.
Its whole value is the scoping, so that is what these tests pin: the adapter
may use the command, nothing else may, and prose about the command is not a
use of it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

_ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_sqf_bans", _ROOT / "tools" / "check_sqf_bans.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
check_sqf_bans: ModuleType = importlib.util.module_from_spec(_SPEC)
sys.modules["check_sqf_bans"] = check_sqf_bans
_SPEC.loader.exec_module(check_sqf_bans)

ADAPTER = "addons/main/functions/fn_prngNext.sqf"
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


def test_the_repository_is_clean() -> None:
    assert check_sqf_bans.scan_tree(_ROOT) == []


def test_the_vendored_wiki_is_not_scanned() -> None:
    scanned = {p.relative_to(_ROOT).as_posix() for p in check_sqf_bans.sqf_files(_ROOT)}
    assert scanned, "expected to find our own SQF"
    assert not any(path.startswith("docs/") for path in scanned)
