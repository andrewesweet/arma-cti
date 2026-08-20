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
  one stopped doing so. Round 2 (the cross-lane review) rebuilt the derivation around git's own
  resolution rather than heuristics standing in for it: the leading global options are kept as a
  context the guard's own config reads run through — so `git -C <repo> fetch origin` and `git -c
  remote.origin.url=<url> fetch origin` are checked against the repository and the override the
  command itself will read, not the cwd's — the dialled repository is the first non-option word of
  the argv (a token that names no configured remote *is* the location git dials, so scp-style and
  URL tokens need no dot-in-host rule to be caught), a bare `push` walks git's documented ladder
  (`branch.<name>.pushRemote`, `remote.pushDefault`, `branch.<name>.remote`, `origin` — measured
  on this box before being written), `fetch --all` and a bare `remote update` check every
  configured remote, `archive --remote` is read in both spellings (the split one was refused as a
  non-absolute path — the option's own word, miscounted as its value), and what the guard cannot
  resolve refuses: an `url.*.insteadOf` rewrite dials a location no config read answers, so any
  rewrite in the context's config refuses the call rather than blessing the unrewritten URL. The
  arrangement suite is parametrised one assertion per shape, and the before/after ran each of the
  22 arrangements under both restored guards: the #425 guard blessed all 22, the round-1 #434 guard
  blessed exactly the seven round 2 filed (the three global-option context shapes, the two bare-push
  ladder rungs, `fetch --all`, and the dotless scp endpoint) and wrongly refused the legitimate
  split `--remote` — so each red names its shape rather than a containing function.
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
