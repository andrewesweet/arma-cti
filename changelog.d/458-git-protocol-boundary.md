### Fixed

- **The review-loop suite no longer parses Git to predict what a command will dial (#458).** Its
  autouse fixture sets Git's own `GIT_ALLOW_PROTOCOL=file` policy, so Git resolves argv, config,
  URL rewrites, multi-valued remote URLs and initialised submodule state before refusing every
  non-file transport. The partial `_repository_tokens` parser, its surrounding destination model
  and their arrangement table are removed. The two routing fetches still receive the existing
  60 s deadline through `_routing_remote_git`, while `remote_ref_sha` retains its own deadline.
  Tests exercise the residual shapes named on #458 — `push --repo=<url>`, `fetch --multiple`,
  both multi-valued `url` and `pushurl`, and an initialised submodule URL from `.git/config` — plus
  an `insteadOf` rewrite hidden behind a harmless-looking token; each fails with Git's own
  `transport 'https' not allowed` refusal. No destination check remains, so the fail-closed-check
  criterion is irrelevant rather than silently skipped.
- **Protocol denial was chosen over the two other candidate mechanisms (#458).** A stand-in `git`
  that records argv observes the same pre-resolution tokens the deleted parser read; observing the
  selected transport would require another protocol-aware proxy. A retained fail-closed parser
  would refuse more safely but would still duplicate Git's resolution rules, and its refusal would
  be invisible whenever the suite did not run. Git's own protocol policy is portable with Git and
  overrides command config, unlike a process network namespace that would add a Linux-specific
  runtime dependency to this module's Git-only boundary. The explicit limit is filesystem
  containment: file remotes outside a test's `tmp_path` remain reachable because the suite needs
  file transport for its scratch repositories. This is the escape after twelve recorded instances
  of comparing a token rather than the thing, not a thirteenth parser repair.
