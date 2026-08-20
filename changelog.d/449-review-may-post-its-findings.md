### Fixed

- **The review seat's rule now says what the human ruled: a reviewer is passed the
  implementer's gate report rather than re-running it, and posting its own findings was never
  barred (#449).** The ruling of 2026-08-14 on #353 was transcribed across the tree as *"the
  seat runs nothing"*, and the review brief spelled out a consequence nobody had ruled — *"do
  not file an issue or a comment"*. The human's clarification of 2026-08-20 states the bar and
  its reason: reviewers should be passed test reports to examine rather than re-run them, "so
  we avoid the significant wall time cost", and they may post their own findings. The cost of
  the wider reading is measured — fifteen verdicts were relayed by hand through the
  orchestrator in the session of 2026-08-19/20, each a plan read, an extraction and a `gh
  issue comment`. Every surface carrying the old wording moves together: `tools/brief.py`'s
  three review strings, `tools/dispatch.py`'s thin default brief, and `docs/review-dispatch.md`
  including its brief template. A sweep for the other spellings — "judgement-only", "runs
  nothing", "triggers no test", "must not trigger", "never executes" — is recorded as closed on
  the issue: every remaining hit belongs to `just regress --list`, to `recon`, or to the
  historical journal. The paste contract is untouched: `just check`, `just unit` and
  `just mutation` with their result counts, and sampled-or-exhaustive stated unconditionally
  (#344, #421).

- **The review seat's forced `plan` permission mode is deliberately unchanged, and what that
  costs is stated rather than glossed (#449).** The mode is not what states the test rule; it
  is what enforces ADR-0071 ruling 4's never-alone invariant, that a review neither edits nor
  lands the change it judges — an invariant this clarification leaves alone. The three
  alternatives weighed are recorded in `tools/dispatch.py` beside the registry row, each
  rejected for trading a mechanism for a sentence: a Bash deny-list any shell defeats, a
  `codex` sandbox widening whose writable root is the review's own worktree, and a seat-scoped
  allow rule resting on an unmeasured premise. Two consequences follow and both are written
  down. A `codex` review **cannot** post — `plan` renders `--sandbox read-only`, which is
  granted no network access — so its findings still travel through the orchestrator. On the
  `claude` family it is **unmeasured** whether a `plan`-mode session reaches the
  already-allowlisted `gh issue comment`; the brief now tells the reviewer to attempt the post
  and to report a refusal among its findings, so the first live review settles it at no extra
  cost. A review-specific gate still cannot be landed from inside a review dispatch; it is a
  change like any other and lands through an implementer dispatch on its own issue.
