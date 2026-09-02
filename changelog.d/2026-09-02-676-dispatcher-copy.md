### Added

- **A dispatch record and `just watch-report` now name the dispatching session's own copy
  of the project's command machinery (#676).** `just dispatch` runs `tools/dispatch.py`
  from the dispatching session's worktree, so a landing that changes the dispatch path did
  not govern the session that landed it, silently. Every dispatch record now carries
  `dispatcher_copy`: the dispatching tree's `HEAD`, `origin/main`'s head, `behind_origin_main`
  as `true`/`false`/`null` — `null` where git could not answer — and the blob shas the
  working tree, `HEAD` and `origin/main` each hold for every governed path whose bytes
  differ across the **union** of the two governed sets. The governed set is the `tools/`
  files the justfile names, the `.claude/hooks/` surface and its `.claude/settings.json`
  wiring, and the justfile itself, derived on each side from that side's own justfile, so
  a path a landing added or deleted is carried like any other drift. `just watch-report`
  gained a `tools/tool_copy.py report` rung: one line per governed path a landing has
  superseded — a tree whose `HEAD` is an ancestor of `origin/main` whose bytes differ —
  silent while current, silent about a tree carrying its own commits, silent about a path
  only the working tree holds, and loud where git cannot answer rather than silently
  current. It reports and never rebases.
