### Fixed

- **The review-loop suite no longer parses Git to predict what a command will dial (#458).** Its
  autouse fixture defaults Git's own `GIT_ALLOW_PROTOCOL` policy to `file`. For tests that leave
  that process environment intact, Git resolves argv, config, URL rewrites, multi-valued remote
  URLs and initialised submodule state before refusing non-file transports. This prevents the
  accidental network case; it is not a sandbox, because a determined test can unset or replace
  the variable. The partial `_repository_tokens` parser, its surrounding destination model and
  their arrangement table are removed. The two routing fetches still receive the existing 60 s
  deadline through `_routing_remote_git`, while `remote_ref_sha` retains its own deadline. Tests
  exercise the residual shapes named on #458 — `push --repo=<url>`, `fetch --multiple`, both
  multi-valued `url` and `pushurl`, and an initialised submodule URL from `.git/config` — plus an
  `insteadOf` rewrite hidden behind a harmless-looking token; under the default policy, each fails
  with Git's own `transport 'https' not allowed` refusal. No destination check remains, so the
  fail-closed-check criterion is irrelevant rather than silently skipped.
- **The smaller, defeatable claim was chosen over a new isolation mechanism (#458).** Moving the
  environment default into the test runner would not make it immutable: a test can still alter its
  own environment before spawning Git. Checking the value inside `review_loop.git` would compare
  exact policy state rather than parse a destination, but it would still be a check that tests can
  bypass or replace, and it would miss Git calls made outside that helper. Even a read-only system
  Git configuration can be ignored or superseded by the invoking process, so it is not an
  isolation boundary. A process network namespace would enforce the larger claim, but would add a
  broad Linux-specific runtime boundary for this Git-only test module. A stand-in `git` or retained
  fail-closed parser would return to predicting Git's resolution rules.
  The cheap policy therefore stays as an accidental-network guard, with its deliberate escape
  stated instead of defended by more machinery. This is the escape from the parser class, not a
  claim that the test process cannot reach the network.
- **Filesystem containment remains explicitly outside this guard (#458).** A file remote outside
  a test's `tmp_path`, including `push --repo=/foreign/repo.git`, remains reachable because the
  suite needs file transport for its scratch repositories. Closing that limit selectively would
  require another destination model or a broader filesystem sandbox. This remains the escape after
  twelve recorded instances of comparing a token rather than the thing, not a thirteenth parser
  repair.
