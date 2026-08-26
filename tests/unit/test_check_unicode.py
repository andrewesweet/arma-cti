"""The Unicode guard refuses invisible and direction-controlling instructions (#601)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path


check_unicode = load_tool("check_unicode")


@pytest.mark.parametrize(
    ("label", "codepoint", "name", "kind"),
    [
        ("zero-width joiner", 0x200D, "ZERO WIDTH JOINER", "zero_width"),
        ("bidi RLO", 0x202E, "RIGHT-TO-LEFT OVERRIDE", "bidi_control"),
        ("homoglyph", 0x0430, "CYRILLIC SMALL LETTER A", "confusable"),
        ("tag character", 0xE0001, "LANGUAGE TAG", "tag_character"),
        ("mid-file byte-order mark", 0xFEFF, "ZERO WIDTH NO-BREAK SPACE", "zero_width"),
        ("zero-width space", 0x200B, "ZERO WIDTH SPACE", "zero_width"),
    ],
)
def test_each_seeded_character_in_a_gated_document_is_named_and_refused(
    tmp_path: Path,
    label: str,
    codepoint: int,
    name: str,
    kind: str,
) -> None:
    """A human-readable refusal carries each seeded character and its remedy."""
    (tmp_path / "AGENTS.md").write_text(
        "# Project instructions\nkeep this visible " + chr(codepoint) + " here\n",
        encoding="utf-8",
    )

    findings = check_unicode.scan_tree(tmp_path)

    assert len(findings) == 1, label
    finding = findings[0]
    assert finding.path == "AGENTS.md"
    assert finding.line == 2
    assert finding.codepoint == codepoint
    assert finding.name == name
    assert finding.kind == kind
    rendered = str(finding)
    assert f"U+{codepoint:04X}" in rendered
    assert name in rendered
    assert "Remove" in rendered


def test_ordinary_accented_and_typographic_prose_passes(tmp_path: Path) -> None:
    """Visible British-English prose is not treated as an attack."""
    (tmp_path / "README.md").write_text(
        "A naïve café — with “curly quotes”, an em dash, an ellipsis … and £5 — "
        "remains readable.\n",
        encoding="utf-8",
    )

    assert check_unicode.scan_tree(tmp_path) == []


def test_the_allowlist_is_explicit_and_every_entry_has_a_reason() -> None:
    """An intentional confusable cannot enter without a reviewable explanation."""
    assert check_unicode.CONFUSABLE_ALLOWLIST
    assert all(reason.strip() for reason in check_unicode.CONFUSABLE_ALLOWLIST.values())


def test_the_vendored_wiki_is_excluded_explicitly(tmp_path: Path) -> None:
    """The live third-party injection channel remains an open scope decision."""
    wiki = tmp_path / "docs" / "reference" / "arma-wiki"
    wiki.mkdir(parents=True)
    (wiki / "page.md").write_text("unsafe " + chr(0x202E) + " content\n", encoding="utf-8")

    assert check_unicode.scan_tree(tmp_path) == []
    assert "docs/reference/arma-wiki/page.md" not in check_unicode.candidates(tmp_path)
