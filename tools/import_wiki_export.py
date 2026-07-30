"""Split a MediaWiki XML export into one wikitext file per page.

The Bohemia Interactive Community wiki is the primary source for almost every
engine fact this project depends on, and it sits behind Cloudflare — direct
fetches, the MediaWiki API and even a browser user-agent all return 403 from
here. Arma 3 has meanwhile been static at 2.20 for over a year, so a vendored
snapshot is both necessary and cheap to keep current.

Produce a new export at https://community.bistudio.com/wiki/Special:Export
(current revision only, no history), then run this over the XML.

Each page becomes `<slug>.wiki` carrying a provenance header: title, source URL,
revision id, revision timestamp and the export's own sha1, so a stale page is
detectable without re-fetching. An INDEX.md lists everything.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

WIKI_BASE = "https://community.bistudio.com/wiki/"


@dataclass(frozen=True)
class Page:
    """One exported wiki page and the provenance needed to spot a stale copy."""

    title: str
    text: str
    revision_id: str
    timestamp: str
    sha1: str

    @property
    def slug(self) -> str:
        """Filesystem-safe stem, so `Arma 3: Named Pipe` becomes `Arma_3_Named_Pipe`."""
        return re.sub(r"[^A-Za-z0-9]+", "_", self.title).strip("_")

    @property
    def url(self) -> str:
        """Canonical wiki URL for this page."""
        return WIKI_BASE + self.title.replace(" ", "_")

    def render(self) -> str:
        """Render the vendored file: provenance header, then the wikitext verbatim."""
        return (
            f"// source: {self.url}\n"
            f"// revision: {self.revision_id} ({self.timestamp})\n"
            f"// export sha1: {self.sha1}\n"
            f"// Vendored snapshot. Do not edit — re-export instead.\n\n"
            f"{self.text.rstrip()}\n"
        )


def _child_text(element: ET.Element, uri: str, tag: str) -> str:
    found = element.find(f"{{{uri}}}{tag}")
    return "" if found is None or found.text is None else found.text


def parse_export(xml: str) -> list[Page]:
    """Read every page out of a MediaWiki export, newest revision only."""
    root = ET.fromstring(xml)  # noqa: S314 - trusted local export
    match = re.match(r"\{(.*)\}", root.tag)
    if match is None:
        msg = "not a MediaWiki export: root element carries no namespace"
        raise ValueError(msg)
    uri = match.group(1)

    pages: list[Page] = []
    for element in root.findall(f"{{{uri}}}page"):
        revision = element.find(f"{{{uri}}}revision")
        if revision is None:
            continue
        pages.append(
            Page(
                title=_child_text(element, uri, "title"),
                text=_child_text(revision, uri, "text"),
                revision_id=_child_text(revision, uri, "id"),
                timestamp=_child_text(revision, uri, "timestamp"),
                sha1=_child_text(revision, uri, "sha1"),
            )
        )
    if not pages:
        msg = "export contains no pages"
        raise ValueError(msg)
    return pages


def build_index(pages: list[Page]) -> str:
    """Render the INDEX.md that fronts the snapshot."""
    lines: list[str] = [
        "# Arma 3 wiki snapshot",
        "",
        "Vendored from the Bohemia Interactive Community wiki, which is unreachable",
        "from this project's environment (Cloudflare returns 403 to fetches, to the",
        "MediaWiki API, and to browser-like requests alike). Arma 3 has been static at",
        "2.20 since June 2025, so these pages change rarely.",
        "",
        "Content belongs to Bohemia Interactive and its wiki contributors. This is a",
        "verbatim snapshot for offline reference, not project documentation — cite the",
        "source URL in each file's header, never this directory.",
        "",
        "Refresh with `Special:Export` (current revision only), then:",
        "",
        "```sh",
        "uv run python tools/import_wiki_export.py <export.xml> docs/reference/arma-wiki",
        "```",
        "",
        "| Page | Revision | Last edited |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| [{page.title}]({page.slug}.wiki) | [{page.revision_id}]({page.url}) "
        f"| {page.timestamp[:10]} |"
        for page in sorted(pages, key=lambda p: p.title)
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Split `export` into one file per page under `output`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="MediaWiki Special:Export XML")
    parser.add_argument("output", type=Path, help="directory to write pages into")
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        help="page title that must be present; repeatable. Missing titles are an error, "
        "because Special:Export silently ignores misspelled names.",
    )
    args = parser.parse_args(argv)

    pages = parse_export(args.export.read_text(encoding="utf-8"))
    titles = {page.title for page in pages}
    missing = sorted(set(args.expect) - titles)
    if missing:
        print(f"missing from export: {', '.join(missing)}", file=sys.stderr)  # noqa: T201
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    for page in pages:
        (args.output / f"{page.slug}.wiki").write_text(page.render(), encoding="utf-8")
    (args.output / "INDEX.md").write_text(build_index(pages), encoding="utf-8")

    print(f"{len(pages)} pages -> {args.output}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
