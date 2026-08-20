### Fixed

- **The escalate suite's hermeticity guard blesses what a call will dial, not the cwd's `origin`
  (#434).** The #425 guard read `git remote get-url origin` for the call's cwd and blessed that —
  a proxy. It passed while `git fetch <url> <ref>` dialled the URL in the argv, while a `push`
  dialled a `pushurl` the read without `--push` never answers, and while a `clone` — in the
  trigger set, its remote an argument, its cwd usually no repository at all — was checked against
  something unrelated to what it dialled. The trigger also keyed on `args[0]`, so a leading global
  option (`-C`, `-c`, `--git-dir`) or a two-word subcommand (`remote update`, `remote show`,
  `submodule update`, `archive --remote`) escaped it entirely. Nothing reachable from `escalate`
  was exposed — its verbs all name `origin` — but the guard would have passed silently the moment
  one stopped doing so. It now derives the dialled location from the argv and the config together:
  global options are consumed before the verb is read, the two-word shapes are recognised, a bare
  token naming a configured remote resolves through `remote.<name>.url` — through `pushurl` first
  for a push — a `fetch <url>` checks the URL itself, a `submodule update` checks the URLs
  `.gitmodules` carries, a verb dialling implicitly derives its default from the branch's config
  rather than assuming `origin`, and a network-shaped argv no location can be derived from refuses
  rather than bless. Five tests drive the arrangements that passed before, each red against the
  old proxy.
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
