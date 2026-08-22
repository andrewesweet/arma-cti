### Fixed

- **The last unbounded git reads of `origin` in the worktree, review-exchange and landing
  protocols carry the shared 60 s deadline (#434).** `just worktree add`, `done` and `restore`
  `fetch` under `worktree.REMOTE_READ_TIMEOUT_S`; `done`'s fetch is `check=False`, and an expiry
  there is tolerated exactly as a failed fetch is — an older `origin/main` against which unlanded
  commits only over-count, the refusing direction — rather than refusing the teardown for a bound
  the protocol survives. `just review exchange` bounds the `--force` push that dials before its
  already-bounded `ls-remote`, so a wedged remote can no longer hang the push the read was bounded
  against, and `record`'s fetch is bounded the same way; both expiries land in each command's
  existing `git_failed` refusal. `just land` and its `--stage` form bound the fetch that starts
  each protocol — deliberately bounded rather than recorded as unbounded, because it runs before
  the rebase, the gate and the push, so expiring leaves nothing half-done, `main`'s catch refuses
  it as `git_failed` like any failed read, and a landing waiting on a wedged remote is the #168
  stall shape rather than patience the protocol owes anyone. The landing push itself was already
  finite, at `GATE_TIMEOUT_S`.
