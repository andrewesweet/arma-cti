### Changed

- **`/orchestrator-tick` is reduced towards steps, commands and pointers, and its
  landing section is corrected (#643).** After `just land` exits 2 the file now says to
  run the `merge_command=` line and then rerun `just land --audit-file FILE`, noting
  that the rerun is what records the audit and closes the issue, and that the issue is
  never closed by hand from exit 2. Other step changes: the review dispatch is preceded
  by `just brief N --seat review --reviewing P --out FILE` and passes `--brief-file`,
  with #647 named for the worktree path that composer gets wrong; the gated-path line
  names all three routes `AGENTS.md` and `tools/gated_paths.py` allow, rather than human
  approval alone; the global `zai, then codex, then claude-native` lane order is
  replaced by a pointer to `tools/dispatch.py`'s per-seat `SEATS` and `just dispatch
  --list`; the turn top asks `just queue next --count N` so the priority section has
  candidates to rank; and the `cti.dispatch-plan/1` paragraph becomes one step with a
  bare `#463` pointer. Rationale and code-assertion prose elsewhere in the file is cut
  in favour of the pointer that owns the rule.
