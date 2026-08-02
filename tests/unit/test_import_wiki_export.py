"""Tests for the wiki-export splitter.

Three behaviours are load-bearing. `--expect` guards against a short snapshot,
because an export silently omits a page it could not resolve. Slugging must keep
BIKI's operator pages apart, since nine of them ("a != b", "a / b", ...) collapse
onto one filename under a naive rule. And filenames must stay unique when
case-folded, or a checkout on Windows or macOS overwrites one page with another.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

wiki = load_tool("import_wiki_export")

EXPORT = """<?xml version="1.0"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" version="0.11">
  <siteinfo><sitename>Bohemia Interactive Community</sitename></siteinfo>
  <page>
    <title>Arma 3: Named Pipe</title>
    <ns>0</ns>
    <revision>
      <id>378557</id>
      <timestamp>2026-05-06T22:27:03Z</timestamp>
      <sha1>rluqmiyyurxweig0rd65f0ufgpyyabg</sha1>
      <text>pipe docs here</text>
    </revision>
  </page>
  <page>
    <title>setDamage</title>
    <ns>0</ns>
    <revision>
      <id>1234</id>
      <timestamp>2025-06-11T00:00:00Z</timestamp>
      <sha1>abc</sha1>
      <text>{{RV|type=command}}</text>
    </revision>
  </page>
  <page>
    <title>setdamage</title>
    <ns>0</ns>
    <redirect title="setDamage" />
    <revision>
      <id>99</id>
      <timestamp>2020-01-01T00:00:00Z</timestamp>
      <sha1>def</sha1>
      <text>#REDIRECT [[setDamage]]</text>
    </revision>
  </page>
</mediawiki>
"""

CATEGORIES = {"setDamage": {"categories": ["Category:Arma 3: Scripting Commands"]}}


@pytest.fixture
def export_file(tmp_path: Path) -> Path:
    path = tmp_path / "export.xml"
    path.write_text(EXPORT)
    return path


@pytest.fixture
def categories_file(tmp_path: Path) -> Path:
    path = tmp_path / "categories.json"
    path.write_text(json.dumps(CATEGORIES))
    return path


def test_every_page_is_parsed() -> None:
    assert [p.title for p in wiki.parse_export(EXPORT)] == [
        "Arma 3: Named Pipe",
        "setDamage",
        "setdamage",
    ]


def test_slug_and_url_survive_the_colon_and_spaces() -> None:
    page = wiki.parse_export(EXPORT)[0]
    assert page.slug == "Arma_3_Named_Pipe"
    assert page.url == "https://community.bistudio.com/wiki/Arma_3:_Named_Pipe"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("a != b", "a_ne_b"),
        ("a == b", "a_eq_b"),
        ("a = b", "a_assign_b"),
        ("a / b", "a_div_b"),
        ("a : b", "a_colon_b"),
        ("a % b", "a_mod_b"),
        ("a && b", "a_and_b"),
        ("a ^ b", "a_pow_b"),
        ("a greater= b", "a_greater_eq_b"),
        ("a greater b", "a_greater_b"),
        ("+", "plus"),
        ("-", "minus"),
        ("Array+=", "Array_plus_eq"),
        # ":" and "/" inside a token are structural, not arithmetic.
        ("Arma 3: Dedicated Server", "Arma_3_Dedicated_Server"),
        ("6thSense.eu/EG", "6thSense_eu_EG"),
    ],
)
def test_operator_pages_slug_apart(title: str, expected: str) -> None:
    assert wiki.slugify(title) == expected


def test_every_operator_page_gets_its_own_filename() -> None:
    operators = ["a != b", "a % b", "a && b", "a * b", "a / b", "a : b", "a == b", "a = b", "a ^ b"]
    assert len({wiki.slugify(title) for title in operators}) == len(operators)


def test_pages_are_bucketed_by_subject(categories_file: Path) -> None:
    pages = wiki.parse_export(EXPORT, wiki.load_categories(categories_file))
    assert {p.title: p.bucket for p in pages if not p.is_redirect} == {
        "Arma 3: Named Pipe": "topics",
        "setDamage": "commands",
    }


def test_bulk_class_name_tables_are_segregated() -> None:
    page = wiki.Page("Arma 3: CfgVehicles WEST", 0, "", "1", "", "")
    assert page.bucket == "classnames"


def test_namespace_pages_drop_their_prefix() -> None:
    page = wiki.Page("Template:RV", 10, "", "1", "", "")
    assert (page.bucket, page.slug) == ("templates", "RV")


def test_rendered_page_carries_provenance_and_the_body() -> None:
    rendered = wiki.parse_export(EXPORT)[0].render()
    assert "https://community.bistudio.com/wiki/Arma_3:_Named_Pipe" in rendered
    assert "378557 (2026-05-06T22:27:03Z)" in rendered
    assert "rluqmiyyurxweig0rd65f0ufgpyyabg" in rendered
    assert rendered.endswith("pipe docs here\n")


def test_categories_are_stamped_into_the_header(categories_file: Path) -> None:
    """They are template-generated, so nothing in the wikitext reveals them."""
    pages = wiki.parse_export(EXPORT, wiki.load_categories(categories_file))
    rendered = next(p for p in pages if p.title == "setDamage").render()
    assert "// categories: Category:Arma 3: Scripting Commands" in rendered


def test_clashing_filenames_are_disambiguated() -> None:
    pages = [wiki.Page(t, 10, "", "1", "", "") for t in ("Template:Warning", "Template:warning")]
    assert wiki.assign_paths(pages) == {
        "Template:Warning": "templates/Warning.wiki",
        "Template:warning": "templates/warning~2.wiki",
    }


def test_writes_bucketed_pages_an_index_and_a_manifest(
    export_file: Path, categories_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "arma-wiki"
    assert wiki.main([str(export_file), str(out), "--categories", str(categories_file)]) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "INDEX.md",
        "MANIFEST.json",
        "commands",
        "topics",
    ]
    assert (out / "commands" / "setDamage.wiki").exists()
    assert (out / "topics" / "Arma_3_Named_Pipe.wiki").exists()
    assert "Arma 3: Named Pipe" in (out / "topics" / "INDEX.md").read_text()


def test_redirects_become_aliases_rather_than_files(
    export_file: Path, categories_file: Path, tmp_path: Path
) -> None:
    """2,638 one-line stub files buy nothing the manifest cannot carry."""
    out = tmp_path / "arma-wiki"
    wiki.main([str(export_file), str(out), "--categories", str(categories_file)])
    manifest = json.loads((out / "MANIFEST.json").read_text())
    assert not (out / "commands" / "setdamage.wiki").exists()
    assert manifest["redirects"] == {"setdamage": "setDamage"}
    assert manifest["pages"]["setDamage"]["path"] == "commands/setDamage.wiki"


def test_aliases_onto_excluded_pages_are_dropped(export_file: Path, tmp_path: Path) -> None:
    """An alias to a page this snapshot excluded sends a reader to a file that is not there."""
    manifest_path = tmp_path / "arma3-manifest.json"
    manifest_path.write_text(json.dumps({"pages": {"setDamage": {"tier": "D"}}}))
    out = tmp_path / "arma-wiki"
    wiki.main([str(export_file), str(out), "--manifest", str(manifest_path)])
    manifest = json.loads((out / "MANIFEST.json").read_text())
    assert "setDamage" not in manifest["pages"]
    assert manifest["redirects"] == {}


def test_a_directory_of_chunks_is_read_whole(tmp_path: Path) -> None:
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    (chunks / "a.xml").write_text(EXPORT)
    (chunks / "b.xml").write_text(EXPORT.replace("setDamage", "setFuel"))
    out = tmp_path / "arma-wiki"
    assert wiki.main([str(chunks), str(out)]) == 0
    assert (out / "topics" / "setFuel.wiki").exists()


def test_tier_filtering_drops_pages_outside_the_wanted_tiers(
    export_file: Path, tmp_path: Path
) -> None:
    manifest = tmp_path / "arma3-manifest.json"
    manifest.write_text(
        json.dumps({"pages": {"setDamage": {"tier": "A"}, "Arma 3: Named Pipe": {"tier": "D"}}})
    )
    out = tmp_path / "arma-wiki"
    assert wiki.main([str(export_file), str(out), "--manifest", str(manifest)]) == 0
    assert (out / "topics" / "setDamage.wiki").exists()
    assert not (out / "topics" / "Arma_3_Named_Pipe.wiki").exists()


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


def test_an_empty_export_directory_is_an_error(tmp_path: Path) -> None:
    empty = tmp_path / "chunks"
    empty.mkdir()
    assert wiki.main([str(empty), str(tmp_path / "out")]) == 1
