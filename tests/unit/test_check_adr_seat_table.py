# ruff: noqa: E501
# The suppression is for the fixture table's rows alone: markdown table rows
# cannot wrap, and the fixture mirrors the live table's shape line for line.
"""Tests for the ADR-0071 seat-table comparison: #392's gate.

Pinned in both directions, because a comparator that only ever passes is
indistinguishable from one that reads nothing. Each drift kind the issue was
filed over gets a red fixture — preference, escalation (the A1 shape at
`eaabf9f`: the ADR tabling an entry the registry did not carry), row-set drift
in both directions, and the Claude-only carve-out — plus the parse failures a
blank or ambiguous cell must become.

The live repository is checked too, and the live drift this check was built on
is replayed against it: the `zai-glm52-max` the table carried while the
registry had already renamed to `zai-glm53-max` (`e19410e`) must be exactly
one finding naming `implementer`. Without that replay the green test could
not tell a comparator from a rubber stamp.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

check = load_tool("check_adr_seat_table")
dispatch = load_tool("dispatch")

PREF = ("codex-luna-max", "zai-glm53-max", "opus-low")
ESC = ("codex-sol-high", "opus-high")

# The live table's shape, post-A5: two prose cells, two not-applicable markers,
# one Claude-only cell, and the interlocutor's unbackticked row. The ground
# sentence for `fable` rides in the surrounding prose, as it does in the ADR.
TABLE = """### 2. Seats carry ordered profile preferences

| seat | preference, head first | escalation |
|---|---|---|
| `planner` (new; absorbs `cti-implementer-xhigh`) | `codex-sol-xhigh`, `opus-xhigh` | `fable-high` |
| `implementer` | `codex-luna-max`, `zai-glm53-max` (A5), `opus-low` | `codex-sol-high`, `opus-high` |
| `recon` (read-only) | `codex-luna-medium`, `haiku-medium` | — never escalates (A1) |
| `review` | the implementer's list, resolved to the first profile that is not the one being reviewed | the implementer's escalation head |
| `retro` (ruling 3) | `fable-high`, `opus-xhigh`, `codex-sol-xhigh` | `opus-max`, `fable-max` (A1) |
| `orchestrator` | `opus-xhigh`; Claude only, provisional per ruling 1 | `opus-max`, `fable-xhigh` (A1) |
| interlocutor — **not dispatched** | `opus-xhigh`, `codex-sol-xhigh` | — not dispatched (A1) |

One seat `tools/dispatch.py` registers is deliberately absent from this table
and stays absent: `fable`, whose preference is `fable-high` alone.
"""


def registry(**overrides: dispatch.Seat) -> check.Registry:
    """Return the registry the fixture table mirrors, with seats replaced."""
    return check.Registry(
        seats={
            "planner": dispatch.Seat(
                "planner",
                claude_only=False,
                preference=("codex-sol-xhigh", "opus-xhigh"),
                escalation=("fable-high",),
            ),
            "implementer": dispatch.Seat(
                "implementer", claude_only=False, preference=PREF, escalation=ESC
            ),
            "recon": dispatch.Seat(
                "recon",
                claude_only=False,
                preference=("codex-luna-medium", "haiku-medium"),
            ),
            "review": dispatch.Seat(
                "review",
                claude_only=False,
                preference=PREF,
                escalation=ESC[:1],
            ),
            "retro": dispatch.Seat(
                "retro",
                claude_only=False,
                preference=("fable-high", "opus-xhigh", "codex-sol-xhigh"),
                escalation=("opus-max", "fable-max"),
            ),
            "fable": dispatch.Seat("fable", claude_only=False, preference=("fable-high",)),
            "orchestrator": dispatch.Seat(
                "orchestrator",
                claude_only=True,
                preference=("opus-xhigh",),
                escalation=("opus-max", "fable-xhigh"),
            ),
            **overrides,
        },
        declared_only={
            "interlocutor": dispatch.Seat(
                "interlocutor",
                claude_only=False,
                preference=("opus-xhigh", "codex-sol-xhigh"),
            )
        },
        implementer_preference=PREF,
        implementer_escalation=ESC,
    )


def scan(source: str, reg: check.Registry | None = None) -> list[str]:
    """Scan the fixture source against a registry, rendered as problem lines."""
    findings = check.scan_source(
        source, "docs/adr/0071-x.md", reg if reg is not None else registry()
    )
    return [f.problem for f in findings]


def test_the_mirrored_table_and_registry_agree() -> None:
    assert scan(TABLE) == []


def test_a_preference_drift_is_named_with_both_sides() -> None:
    drifted = TABLE.replace("`zai-glm53-max` (A5)", "`zai-glm52-max` (A5)")
    assert scan(drifted) == [
        (
            "`implementer` preference: ADR ['codex-luna-max', 'zai-glm52-max', 'opus-low'] "
            "!= registry ['codex-luna-max', 'zai-glm53-max', 'opus-low']"
        )
    ]


def test_the_a1_shape_tables_an_entry_the_registry_lacks() -> None:
    # eaabf9f: the ADR carried retro's escalation while SEATS carried ().
    emptied = registry(
        retro=dispatch.Seat(
            "retro",
            claude_only=False,
            preference=("fable-high", "opus-xhigh", "codex-sol-xhigh"),
        )
    )
    assert scan(TABLE, emptied) == [
        "`retro` escalation: ADR ['opus-max', 'fable-max'] != registry []"
    ]


def test_an_escalation_drift_in_the_other_direction_is_found() -> None:
    drifted = TABLE.replace("`fable-high` |\n| `implementer`", "`fable-low` |\n| `implementer`")
    assert scan(drifted) == ["`planner` escalation: ADR ['fable-low'] != registry ['fable-high']"]


def test_a_seated_carveout_drift_is_found_in_both_directions() -> None:
    unmarked = TABLE.replace("Claude only, provisional per ruling 1", "provisional per ruling 1")
    assert scan(unmarked) == ["`orchestrator` claude-only: ADR False != registry True"]
    unrestrained = registry(
        orchestrator=dispatch.Seat(
            "orchestrator",
            claude_only=False,
            preference=("opus-xhigh",),
            escalation=("opus-max", "fable-xhigh"),
        )
    )
    assert scan(TABLE, unrestrained) == ["`orchestrator` claude-only: ADR True != registry False"]


def test_a_tabled_seat_the_registry_lacks_is_a_finding() -> None:
    extra = TABLE.replace(
        "| interlocutor —",
        "| `mechanical` | `codex-sol-high` | `fable-high` |\n| interlocutor —",
    )
    assert scan(extra) == [
        "`mechanical` is tabled here but `tools/dispatch.py` registers no such seat"
    ]


def test_a_registry_seat_the_table_lacks_needs_a_stated_absence() -> None:
    doubled = registry(
        auditor=dispatch.Seat("auditor", claude_only=False, preference=("opus-high",))
    )
    assert scan(TABLE, doubled) == [
        "`tools/dispatch.py` registers `auditor` with no row in the table and no stated absence"
    ]


def test_a_stated_absence_keeps_an_untabled_seat_quiet() -> None:
    seated = registry(fable=dispatch.Seat("fable", claude_only=False, preference=("fable-high",)))
    assert scan(TABLE, seated) == []


def test_the_absence_ground_is_read_out_of_the_document() -> None:
    ungrounded = TABLE.replace(
        "deliberately absent from this table\nand stays absent: `fable`, whose preference",
        "gone from this table\ntoo, whose preference",
    )
    assert scan(ungrounded) == [
        (
            "`fable`'s deliberate absence from the table is no longer stated in the ADR, "
            "so this check's exception for it has lost its ground"
        )
    ]


def test_the_reviews_phrases_resolve_through_the_shared_objects() -> None:
    # The phrase cells resolve through the shared tuples, not through the seat's
    # own lists, so a seat-side retune fires only the seat whose row names data.
    retuned = registry(
        implementer=dispatch.Seat(
            "implementer",
            claude_only=False,
            preference=("codex-luna-max", "opus-low"),
            escalation=ESC,
        ),
    )
    assert scan(TABLE, retuned) == [
        (
            "`implementer` preference: ADR ['codex-luna-max', 'zai-glm53-max', 'opus-low'] "
            "!= registry ['codex-luna-max', 'opus-low']"
        )
    ]
    # And the mirror: review's seat list moving off what the phrase names fires
    # review's row, because the shared tuple still stands behind the phrase.
    detached = registry(
        review=dispatch.Seat(
            "review", claude_only=False, preference=("opus-low",), escalation=ESC[:1]
        )
    )
    assert scan(TABLE, detached) == [
        (
            "`review` preference: ADR ['codex-luna-max', 'zai-glm53-max', 'opus-low'] "
            "!= registry ['opus-low']"
        )
    ]
    widened = registry(
        review=dispatch.Seat("review", claude_only=False, preference=PREF, escalation=ESC)
    )
    assert scan(TABLE, widened) == [
        "`review` escalation: ADR ['codex-sol-high'] != registry ['codex-sol-high', 'opus-high']"
    ]


def test_a_blank_escalation_cell_is_a_finding_not_a_pass() -> None:
    blanked = TABLE.replace("| `opus-max`, `fable-max` (A1) |", "|  |")
    assert scan(blanked) == [
        (
            "`retro` escalation cell carries neither an entry nor a not-applicable "
            "marker — a blank escalation cell is a refusal since A1"
        )
    ]


def test_a_cell_with_two_answers_is_rejected_rather_than_resolved() -> None:
    ambiguous = TABLE.replace(
        "| the implementer's list, resolved",
        "| the implementer's list, `opus-low`, resolved",
    )
    assert scan(ambiguous) == [
        "`review` preference cell states the implementer's list and also names ['opus-low']"
    ]
    head_and_more = TABLE.replace(
        "| the implementer's escalation head |",
        "| the implementer's escalation head, `opus-max` |",
    )
    assert scan(head_and_more) == [
        (
            "`review` escalation cell states the implementer's escalation head and "
            "also names ['opus-max']"
        )
    ]
    marked_and_filled = TABLE.replace(
        "| — never escalates (A1) |", "| — never escalates, `fable-high` (A1) |"
    )
    assert scan(marked_and_filled) == [
        "`recon` escalation cell marked not-applicable and also names ['fable-high']"
    ]


def test_a_cell_that_names_nothing_is_a_finding() -> None:
    emptied = TABLE.replace("`codex-luna-medium`, `haiku-medium`", "resolved as the lane permits")
    assert scan(emptied) == ["`recon` preference cell names no profiles"]


def test_a_malformed_row_is_a_finding() -> None:
    # The row also stops counting as `retro`'s, so the absence finding rides
    # with the parse finding: a row that cannot be parsed is a row that does
    # not table the seat it was carrying.
    broken = TABLE.replace("| `retro` (ruling 3) |", "| `retro` | (ruling 3) |")
    assert scan(broken) == [
        "row carries 4 cells, expected seat, preference, escalation",
        "`tools/dispatch.py` registers `retro` with no row in the table and no stated absence",
    ]


def test_a_row_that_names_no_seat_is_a_finding() -> None:
    unnamed = TABLE.replace("| `retro` (ruling 3) |", "| — |")
    assert scan(unnamed) == [
        "row names no seat",
        "`tools/dispatch.py` registers `retro` with no row in the table and no stated absence",
    ]


def test_no_table_is_a_finding_not_a_pass() -> None:
    assert scan("### 2. Seats\n\nNo table here.\n") == [
        "ruling 2's seat table not found — no line opens '| seat |'"
    ]


def test_a_stray_later_block_is_not_the_table() -> None:
    # The body ends at the first line that is not a table row, so a block after
    # intervening prose is never compared — pinned as the *absence* of findings
    # from its rows.
    twice = TABLE + "\nProse between.\n\n| seat | elsewhere | |\n| `x` | `y` | `z` |\n"
    assert scan(twice) == []


def test_seat_name_reads_the_first_backticked_token_or_first_word() -> None:
    assert check.seat_name("`planner` (new; absorbs `cti-implementer-xhigh`)") == "planner"
    assert check.seat_name("interlocutor — **not dispatched**") == "interlocutor"
    # The word fallback is honest about what it does: a cell that lost its
    # backticked name tables a bogus seat rather than passing silently.
    assert check.seat_name("(ruling 3)") == "ruling"
    assert check.seat_name("—") == ""


def test_the_separator_row_is_recognised() -> None:
    assert check.is_separator(["---", "---", "---"]) is True
    assert check.is_separator(["— never escalates (A1)"]) is False
    assert check.is_separator([]) is False


def test_the_live_table_matches_the_live_registry() -> None:
    findings = check.scan_tree(REPO)
    assert findings == [], "\n".join(str(f) for f in findings)


def test_the_live_drift_this_check_was_built_on_is_replayed() -> None:
    # e19410e renamed zai-glm52-max to zai-glm53-max in the registry and left
    # the ADR's table behind; replaying that tree must name exactly one seat,
    # one column, both surfaces' values.
    adr = next((REPO / "docs" / "adr").glob("0071-*.md"))
    source = adr.read_text(encoding="utf-8")
    stale = source.replace("`zai-glm53-max`", "`zai-glm52-max`")
    assert stale != source, "expected the live ADR to name zai-glm53-max"
    findings = check.scan_source(
        stale,
        "docs/adr/0071-x.md",
        check.Registry(
            seats=dict(dispatch.SEATS),
            declared_only=dict(dispatch.DECLARED_ONLY_SEATS),
            implementer_preference=dispatch.IMPLEMENTER_PREFERENCE,
            implementer_escalation=dispatch.IMPLEMENTER_ESCALATION,
        ),
    )
    assert [f.problem for f in findings] == [
        (
            "`implementer` preference: ADR ['codex-luna-max', 'zai-glm52-max', 'opus-low'] "
            "!= registry ['codex-luna-max', 'zai-glm53-max', 'opus-low']"
        )
    ]


def test_a_tree_without_exactly_one_0071_file_refuses(tmp_path: Path) -> None:
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    findings = check.scan_tree(tmp_path)
    assert [f.problem for f in findings] == ["expected exactly one 0071-*.md file, found 0"]
    (tmp_path / "docs" / "adr" / "0071-a.md").write_text(TABLE, encoding="utf-8")
    (tmp_path / "docs" / "adr" / "0071-b.md").write_text(TABLE, encoding="utf-8")
    findings = check.scan_tree(tmp_path)
    assert [f.problem for f in findings] == ["expected exactly one 0071-*.md file, found 2"]
    # And one copy alone is checked, not merely counted.
    (tmp_path / "docs" / "adr" / "0071-b.md").unlink()
    assert check.scan_tree(tmp_path) == []
