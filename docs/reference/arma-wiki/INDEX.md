# Arma 3 wiki snapshot

Vendored from the Bohemia Interactive Community wiki (BIKI), which is
unreachable from this project's environment: Cloudflare returns 403 to plain
fetches, to the MediaWiki API and to browser-like requests alike. Arma 3 has
been static at 2.20 since June 2025, so these pages change rarely.

Content belongs to Bohemia Interactive and its wiki contributors. This is a
verbatim snapshot for offline reference, not project documentation — cite the
source URL in each file's header, never this directory.

## What is here

6690 pages, 33.4 MB of wikitext, taken 2026-07-30T15:22:01Z.

| Directory | Pages | Contents |
|---|---|---|
| [`categories/`](categories/INDEX.md) | 721 | Category description pages, not membership lists |
| [`classnames/`](classnames/INDEX.md) | 72 | Bulk class-name and asset tables. Large; look up, do not read |
| [`commands/`](commands/INDEX.md) | 2672 | SQF scripting commands, one page per command |
| [`functions/`](functions/INDEX.md) | 2056 | BIS functions (`BIS_fnc_*`) and other library functions |
| [`meta/`](meta/INDEX.md) | 15 | Wiki policy, help and extension pages |
| [`templates/`](templates/INDEX.md) | 148 | Wiki templates. Needed to interpret `{{RV}}` markup in page source |
| [`topics/`](topics/INDEX.md) | 1006 | Prose: engine topics, tutorials, config and editor reference |

## Finding a page

Paths are predictable: a scripting command lives at `commands/<name>.wiki`,
so `setDamage` is `commands/setDamage.wiki`. Titles carrying punctuation are
slugged — `:` and `/` become `_`, and operator pages spell their symbols out,
so `a != b` is `commands/a_ne_b.wiki`. Each directory has its own INDEX.md
listing every page it holds.

`MANIFEST.json` is the authoritative lookup. It maps every title to its path,
revision, timestamp and sha1, and carries the redirect alias map
(1106 aliases): redirect stubs are not written as files, so an
alternate spelling such as `AGLtoASL` resolves to the `AGLToASL` page through
the manifest rather than through a one-line file. Aliases whose target this
snapshot excludes are dropped, so every alias resolves to a file that exists.

## Scope

The snapshot covers the main, template, category, help, project and extension
namespaces. Within the main namespace it keeps two tiers:

| Tier | Rule | Pages |
|---|---|---|
| A | Carries an `Arma 3` or `Introduced with Arma 3` category | 5075 |
| B | Carries no game-specific category: engine-generic or shared | 731 |

Pages categorised only for earlier titles (Operation Flashpoint, ArmA, Arma 2,
Take On) or for other engines (Reforger, Arma 4, DayZ, Enfusion) are excluded,
as are File-namespace content, talk pages and edit history.

## Important: categories are not in the wikitext

BIKI generates category assignment from templates, so page source contains no
`[[Category:...]]` links and you cannot tell from the wikitext which games a
page applies to. Applicability is encoded as `{{RV}}` parameters (`game6=
arma3`). Each vendored file therefore carries a `// categories:` header line,
pulled from the API's `prop=categories` at snapshot time and stamped in at
import — so `grep -l 'Arma 3: Scripting Commands' commands/*.wiki` works,
where grepping the wikitext itself would find nothing.

## Refreshing

Cloudflare challenges plain HTTP clients, so the export is produced by driving
the MediaWiki API from a logged-in browser session, which inherits the
browser's TLS fingerprint and clearance cookie:

```
/wikidata/api.php?action=query&generator=allpages&export=1&gaplimit=500
```

Then re-derive this directory from the resulting chunks:

```sh
uv run python tools/import_wiki_export.py <export-dir> docs/reference/arma-wiki \
    --categories <export-dir>/categories.json \
    --manifest <export-dir>/arma3-manifest.json
```

The tool is idempotent: it rewrites every page, index and manifest from the
export, so a refresh reads as a clean diff rather than a merge.
