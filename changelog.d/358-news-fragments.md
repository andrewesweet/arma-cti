### Changed

- **Branches now carry independent changelog fragments (#358).** User-visible changes add
  uniquely named Markdown files under `changelog.d/`, removing `CHANGELOG.md` from ordinary
  branch surfaces. `just check` refuses source changes without a fragment. At release,
  `cog bump --auto` runs Scriv to collect fragments deterministically into this changelog and
  remove them.
