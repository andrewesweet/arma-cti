"""Tests for the review-queue report (issue #351).

The whole point of the tool is one distinction: a `Reviewed-by-human: pending`
field line counts, a prose mention of the same string does not. So the prose
shapes are pinned as tightly as the field shape — the two 6-for-1 reports were
both a grep that could not tell them apart, and a report that only ever
counted field lines proves nothing about the trap it exists to close.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

review_queue = load_tool("review_queue")

FIELDS = "Date: 2026-08-02\nDelegated-decision: yes\nReviewed-by-human: pending\n"
PROSE = "The `Reviewed-by-human: pending` count.\n"


def test_a_field_line_is_counted_with_its_line_number() -> None:
    assert review_queue.pending_lines(f"# A decision\n\n{FIELDS}\n## Body\n") == [5]


def test_a_backticked_prose_mention_is_not_counted() -> None:
    # The corpus's most common shape: ADR-0029 narrates "the
    # `Reviewed-by-human: pending` count" mid-sentence.
    source = f"# A decision\n\nReviewed-by-human: 2026-08-02\n\n{PROSE}"
    assert review_queue.pending_lines(source) == []


def test_a_quoted_grep_line_is_not_counted() -> None:
    # ADR-0019's shape: the line that documents the very grep, opening with a
    # backtick so the marker never starts the line.
    source = (
        "# A decision\n\nReviewed-by-human: 2026-08-02\n\n"
        '`grep -rl "^Reviewed-by-human: pending" docs/adr/` is the worklist.\n'
    )
    assert review_queue.pending_lines(source) == []


def test_the_fixture_tree_counts_the_field_adr_and_not_the_prose_one(tmp_path: Path) -> None:
    # The acceptance criterion as one arrangement: two fixture ADRs, one with
    # the field line and one quoting the marker in prose, and the prose one
    # carries the unanchored string — so a queue that held both would be the
    # 6-for-1 report again, proven rather than assumed.
    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "0001-genuine.md").write_text(f"# Real\n\n{FIELDS}\n", encoding="utf-8")
    (adr / "0002-prose.md").write_text(
        f"# Prose\n\nReviewed-by-human: 2026-08-02\n\n{PROSE}", encoding="utf-8"
    )
    queue = review_queue.pending_adrs(tmp_path)
    assert queue == [("docs/adr/0001-genuine.md", [5])]
    assert "Reviewed-by-human: pending" in (adr / "0002-prose.md").read_text(
        encoding="utf-8"
    )  # the trap is really planted


def test_render_prints_the_count_then_the_file_list() -> None:
    queue = [("docs/adr/0001-x.md", [4]), ("docs/adr/0002-y.md", [6])]
    assert review_queue.render(queue).splitlines() == [
        "2 ADRs await human review",
        "docs/adr/0001-x.md:4",
        "docs/adr/0002-y.md:6",
    ]


def test_render_spells_the_singular_once() -> None:
    assert review_queue.render([]).splitlines() == ["0 ADRs await human review"]
    assert review_queue.render([("docs/adr/0001-x.md", [4])]).splitlines() == [
        "1 ADR awaits human review",
        "docs/adr/0001-x.md:4",
    ]


def test_main_prints_the_queue_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "0001-x.md").write_text(f"# Real\n\n{FIELDS}\n", encoding="utf-8")
    assert review_queue.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "1 ADR awaits human review"
    assert out[1] == "docs/adr/0001-x.md:5"


def test_the_live_queue_is_what_a_line_start_scan_says_it_is() -> None:
    # Recomputed by a different mechanism than the tool's MULTILINE regex —
    # splitlines and startswith — so a regex that drifted loose or tight fails
    # here rather than agreeing with itself.
    adr_dir = REPO / "docs" / "adr"
    expected = sorted(
        path.relative_to(REPO).as_posix()
        for path in adr_dir.glob("*.md")
        if any(
            line.startswith("Reviewed-by-human: pending")
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    )
    queue = review_queue.pending_adrs(REPO)
    assert [path for path, _ in queue] == expected
    assert queue, "expected the live review queue to be non-empty"
