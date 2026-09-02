### Added

- **A dispatch record and `just watch-report` now name the dispatching session's own copy
  of the project's command machinery (#676).** `just dispatch` runs `tools/dispatch.py`
  from the dispatching session's worktree, so a landing that changes the dispatch path did
  not govern the session that landed it, silently. Every dispatch record now carries
  `dispatcher_copy`: the dispatching tree's `HEAD`, `origin/main`'s head, `behind_origin_main`
  as `true`/`false`/`null` — `null` where git could not answer — and the blob shas the
  working tree, `HEAD` and `origin/main` each hold for every governed path whose bytes
  differ across the **union** of the two governed sets. `just watch-report` gained a
  `tools/tool_copy.py report` rung: one line per governed path a landing has superseded —
  a tree whose `HEAD` is an ancestor of `origin/main` whose bytes differ — silent while
  current, silent about a tree carrying its own commits, silent about a path only the
  working tree holds, and loud where git cannot answer rather than silently current. It
  reports and never rebases.

### Changed

- **The governed set is the whole of `tools/`, and the survey reads the tree whose copy
  of `tools/dispatch.py` actually ran (#676, round three).** The set was the `tools/`
  files the justfile names, which left the helpers `tools/dispatch.py` imports and runs —
  `codex_guidance.py`, `dispatch_stop.py`, `gate_report.py`, `hook_parity.py`,
  `readiness.py`, `routing_policy.py` among them — silently ungoverned. Both sides of the
  walk now derive the same definition — all of `tools/`, the `.claude/hooks/` surface and
  its `.claude/settings.json` wiring, and the justfile — so it over-reports on purpose:
  it names a landed change to a tool the session never invoked, the correct direction of
  error, stated in `tools/tool_copy.py` where the set is defined. And the survey reads
  the tree whose copy of the dispatching module is running rather than the main checkout
  the entrypoint converted `cwd` to, so a dispatch from a linked session worktree can no
  longer record a fresh main checkout while a stale worktree's own `tools/dispatch.py`
  produced it. A path a landing newly governs is hashed on demand rather than read as
  absent, so a byte-identical file is no longer reported superseded.
- **The `just watch-report` tool-copy rung is bounded and its failure typed (ADR-0049).**
  Every git read inside `tools/tool_copy.py` carries a 30-second timeout that reports
  "cannot tell" where git hangs, and the rung itself runs under a 60-second `timeout`
  whose failure prints one typed line — `tool-copy: rung did not answer` — instead of
  stalling the turn-top read or passing as silence.
