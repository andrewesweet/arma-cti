### Added

- **A dispatch record and `just watch-report` now name the dispatching session's own copy
  of the project's command machinery (#676).** `just dispatch` runs `tools/dispatch.py`
  from the dispatching session's worktree, so a landing that changes the dispatch path did
  not govern the session that landed it, silently. Every dispatch record now carries
  `dispatcher_copy`: the dispatching tree's `HEAD`, `origin/main`'s head, and both blob
  sides of every governed path whose bytes differ, where the governed set is the `tools/`
  files the justfile names, the `.claude/hooks/` surface and its `.claude/settings.json`
  wiring, and the justfile itself. `just watch-report` gained a `tools/tool_copy.py
  report` rung: one line per governed path that a landing has superseded — a tree whose
  `HEAD` is an ancestor of `origin/main` with differing bytes — silent while current,
  silent about a tree carrying its own commits, and loud where git cannot answer rather
  than silently current. It reports and never rebases.
