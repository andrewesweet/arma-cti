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
  the issue: no spelling of the review ruling survives, and every remaining hit is one of a
  command flag that runs nothing (`just regress --list`, `just land --dry-run`,
  `machine-b steam-library-script`), a shell file's sourced-not-executed header, a mutation
  vacuity or never-executed-code statement, an unrelated "judgement only" domain (ADR-0012's
  Command Port reply), `recon`'s own separately cited ground, this correction's own quoted
  history, or the historical journal. The paste contract is untouched: `just check`, `just unit` and
  `just mutation` with their result counts, and sampled-or-exhaustive stated unconditionally
  (#344, #421).

- **The review seat's forced `plan` permission mode is deliberately unchanged, and what that
  costs is stated rather than glossed (#449).** The mode is not what states the test rule; it
  is what enforces ADR-0071 ruling 4's never-alone invariant, that a review neither edits nor
  lands the change it judges — an invariant this clarification leaves alone. The three
  alternatives weighed are recorded in `tools/dispatch.py` beside the registry row: a Bash
  deny-list any shell defeats, and a `codex` sandbox widening whose writable root is the
  review's own worktree, both rejected for trading a mechanism for a sentence; and a
  seat-scoped `gh issue comment` allow rule, now moot rather than rejected, because both
  runner families have been observed posting from `plan` mode without one. Those two runs are
  named in the row and in `docs/review-dispatch.md`: on `codex`, dispatch
  `d-20260820-110847-f9b197` posted comment `5355112577` to #434 from inside its own
  `--sandbox read-only` session; on the `claude` family, dispatch `d-20260820-113736-1c53a4`,
  a `zai` review, posted comment `5355396609` to #449. What those runs measure is that both
  families *can* post from `plan`, so the fifteen relays were a consequence of the instruction
  rather than of the mechanism. They do not establish that the relay is gone: whether it can be
  retired as a standing step is #393's question, and nothing here answers it. A
  review-specific gate still cannot be landed from inside a review dispatch; it is a change
  like any other and lands through an implementer dispatch on its own issue.

- **A `codex` review can post its own findings; the first draft of this change said it could
  not, and that was false (#449).** The claim — that `--sandbox read-only` leaves the session
  no network because `_codex_sandbox_argv` grants that branch no `network_access` — was
  written as "known from the code, not guessed" and disproved by a dispatch record already on
  disk an hour earlier. `network_access` is a `sandbox_workspace_write` setting, so the grant
  attaches to the `acceptEdits` branch alone: *the function grants nothing here* is a fact
  about the function, while *the sandbox blocks the network* is a claim about Codex's own
  read-only policy that had never been measured. The correction and its cause are kept on the
  page in `docs/review-dispatch.md` rather than silently replaced, because #449 was filed over
  an unverified sentence surviving under a green suite and this was the same move inside its
  own fix.
