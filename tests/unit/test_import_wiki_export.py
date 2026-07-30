"""Tests for the wiki-export splitter.

The load-bearing behaviour is `--expect`: Special:Export silently ignores a
misspelled page title, so a missing page must be an error rather than a quietly
short snapshot.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SPEC = importlib.util.spec_from_file_location(
    "import_wiki_export", Path(__file__).parents[2] / "tools" / "import_wiki_export.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
wiki: ModuleType = importlib.util.module_from_spec(_SPEC)
sys.modules["import_wiki_export"] = wiki
_SPEC.loader.exec_module(wiki)

EXPORT = """<?xml version="1.0"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" version="0.11">
  <siteinfo><sitename>Bohemia Interactive Community</sitename></siteinfo>
  <page>
    <title>Arma 3: Named Pipe</title>
    <revision>
      <id>378557</id>
      <timestamp>2026-05-06T22:27:03Z</timestamp>
      <sha1>rluqmiyyurxweig0rd65f0ufgpyyabg</sha1>
      <text>pipe docs here</text>
    </revision>
  </page>
  <page>
    <title>Multiplayer Server Commands</title>
    <revision>
      <id>373679</id>
      <timestamp>2025-06-11T00:00:00Z</timestamp>
      <sha1>abc</sha1>
      <text>#login etc</text>
    </revision>
  </page>
</mediawiki>
"""


@pytest.fixture
def export_file(tmp_path: Path) -> Path:
    path = tmp_path / "export.xml"
    path.write_text(EXPORT)
    return path


def test_every_page_is_parsed() -> None:
    assert [p.title for p in wiki.parse_export(EXPORT)] == [
        "Arma 3: Named Pipe",
        "Multiplayer Server Commands",
    ]


def test_slug_and_url_survive_the_colon_and_spaces() -> None:
    page = wiki.parse_export(EXPORT)[0]
    assert page.slug == "Arma_3_Named_Pipe"
    assert page.url == "https://community.bistudio.com/wiki/Arma_3:_Named_Pipe"


def test_rendered_page_carries_provenance_and_the_body() -> None:
    rendered = wiki.parse_export(EXPORT)[0].render()
    assert "https://community.bistudio.com/wiki/Arma_3:_Named_Pipe" in rendered
    assert "378557 (2026-05-06T22:27:03Z)" in rendered
    assert "rluqmiyyurxweig0rd65f0ufgpyyabg" in rendered
    assert rendered.endswith("pipe docs here\n")


def test_writes_one_file_per_page_plus_an_index(export_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "arma-wiki"
    assert wiki.main([str(export_file), str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "Arma_3_Named_Pipe.wiki",
        "INDEX.md",
        "Multiplayer_Server_Commands.wiki",
    ]
    assert "Arma 3: Named Pipe" in (out / "INDEX.md").read_text()


def test_a_missing_expected_page_is_an_error(export_file: Path, tmp_path: Path) -> None:
    code = wiki.main([str(export_file), str(tmp_path / "out"), "--expect", "Arma 3: Typoed Page"])
    assert code == 1


def test_expected_pages_that_are_present_pass(export_file: Path, tmp_path: Path) -> None:
    code = wiki.main([str(export_file), str(tmp_path / "out"), "--expect", "Arma 3: Named Pipe"])
    assert code == 0


def test_an_export_with_no_pages_is_rejected() -> None:
    empty = EXPORT[: EXPORT.index("<page>")] + "</mediawiki>\n"
    with pytest.raises(ValueError, match="no pages"):
        wiki.parse_export(empty)
