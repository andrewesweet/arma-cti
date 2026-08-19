### Added

- **`just check-arbiter` now keeps arbiter-rule copies derived instead of hand-counted
  (#390).** The check scans every tracked file as part of `just check`, reports restatements
  outside `tools/arbiter.py`, and treats each comment run, string paragraph, list item, and
  table row as a separate site even when nested or indented. A reasoned
  `arbiter-rule: stated` marker preserves dated records that must repeat the rule, and
  `--report` enumerates those exceptions.

### Fixed

- **Mutation smoke now scores a mutant-caused import failure as a kill (#338).** After the
  unmutated test module passes its existing preflight, a pytest collection diagnostic from a
  planted mutant is scored as an ordinary test failure. Invalid test node ids remain usage
  errors and still refuse the gate; a module red before mutation still refuses unchanged.

- **A worktree status command that fails no longer reads as a clean tree (#375).**
  `tools/worktree.py`'s `gather` read `git status --porcelain` with `check=False`, so a status
  that failed printed nothing, and nothing parsed as a clean `Preflight` — `just worktree check`
  then answered `ok=preflight_clean` and exit 0 without having established anything, which is
  the one unsafe answer to the question the pre-flight exists to ask (#105). The read now lives
  in `read_preflight`, which returns `None` where the command itself failed: `check` refuses
  `unverified` naming `status=unreadable` rather than the tree's contents, `done` and `archive`
  reach their existing `git_failed` rung, and `just worktree list` prints `unreadable` for that
  tree instead of a dirt count it never read. The remaining `check=False` reads in the module are
  named where they sit, each with why its absence decides nothing.

- **The Codex writable roots are two constants the environment cannot reach, and a stale
  predecessor can no longer be committed with the current work (#405).** Four review rounds
  on the harness-commit path. The sandbox's writable roots — `~/.cache/uv` and
  `~/.ansible/tmp`, each measured red — are now computed once from the box's home directory
  as absolute resolved constants, and `UV_CACHE_DIR`, `ANSIBLE_LOCAL_TEMP`, `XDG_CACHE_HOME`
  and `ANSIBLE_HOME` are not read at all: `UV_CACHE_DIR=/` and `ANSIBLE_LOCAL_TEMP=<gitdir>`
  were once silently granted, and each of the three schemes that validated such a value in
  turn was defeated somewhere else — most recently by a relative root that passed validation
  as canonical and was then reinterpreted from the child's working directory. Nothing
  external is admitted, so there is nothing left to validate; the sole remaining refusal,
  `writable_root_refused`, is a home directory this box will not canonicalise, and a box
  that genuinely keeps a cache elsewhere changes the constants in a reviewed diff. Before a
  session launches, a worktree holding a surviving
  `.dispatch-commit-message` refuses `dispatch_message_present` and a dirty one
  refuses `dirty_tree` — `git add --all` would have swept a finished predecessor's message
  and edits into this run's commit and pushed them under its issue. A non-UTF-8 message is
  now the `commit_message_unreadable` refusal with a written record rather than an uncaught
  `UnicodeDecodeError` that left the worktree occupied; `git add` and `git commit` are
  asked separately, so each `git_failed` refusal is true of the command that refused — the
  add's claims no staging state a failed add cannot vouch for, the commit's names the
  staging the add left and preserves the message beside the record. The unevidenced
  `~/.cache/ansible-lint` grant is dropped (the installed copy returns before creating it),
  and ADR-0071 is swept with Amendment A6: the #265 ceiling is lifted, the Codex implementer
  head is live, and every paragraph that said otherwise now says so.

- **Every surface that states the cross-lane gate rule now states its exhaustion case too
  (#416, ADR-0073 Amendment A1).** `AGENTS.md`, the class-6 remedy in
  `config/dispatch-routing-policy.json` and ADR-0071's row 6 each still said a gate landing
  needs a different-lane verdict in absolute terms, which the `lane_exhausted` degradation
  had already qualified — an agent reading any of them was told something the code no
  longer does. Each now states the rule first and the degradation second, so the ordering
  is read rather than implied: the refusal stands unchanged wherever a cross-lane reviewer
  exists. ADR-0073's A1 gains the `Amended:` header entry the A1/A2 precedent prescribes
  beside its inline marking, its fallback's false "never empty while more than one profile
  exists" is replaced with the true bound — empty where the records place every registered
  profile on the work, and there the rung above refuses `review_same_profile` before the
  lane question is reached — and `tools/land_review.py`'s decision helper is named for what
  it returns rather than for the refusal it used to be.

- **The review seat's resolution reads the declared authorship record, not only the dispatch
  records (#402).** #398 gave the author set a second source — the interactive declaration,
  because #294 bars a dispatched session from writing under `.claude/` and such a change
  leaves no dispatch record at all — and `just land`'s never-alone rung reads both.
  `just dispatch --seat review` read only the first, so for an interactively authored
  change the seat could resolve the very profile that authored it: the dispatch was spent,
  the review ran, and `review_same_profile` refused at the landing on a record the
  dispatcher had never seen, while the dispatch's own `reviewing_checked` mark answered
  over a set missing an author sitting on disk. The two consumers of the author set now
  perform the same merge — `review_authorship` calls `with_declared_authors` over
  `recorded_authors`, exactly as the landing rung does — so they cannot disagree, and the
  route's mark and `potential_authors` reflect the merged set. Two fail-closed companions
  ride with it, reusing the landing's names for the same facts: a declared record that
  will not read refuses the dispatch `authorship_unreadable` rather than crashing or
  overstating the set, and a record removed after a declaration refuses
  `authorship_lost` — the silent narrowing `just review-loop escalate` already refuses,
  one door along. The same-user limit ADR-0071 ruling 4 states is unchanged: a declared
  author is the recording session's own word, which is why the route still says
  `checked` and never `verified`.

- **A brief no longer promises a clean tree the flake filter never established (#360).**
  `just brief`'s empty flake section told a seat "None open. Any red is yours." on the
  strength of a name-based filter — a title naming a `test_` that says it flakes, or a
  body opening `Class: flake_quarantine` — that cannot see an open issue phrased any
  other way. Three briefs on one day carried the claim while #341's deterministic
  four-hours-a-day red sat open, so two seats met reds the brief had just told them were
  theirs. The zero branch now states what was searched and that the filter may miss, and
  tells the seat to check the tracker before treating a red as its own; the non-empty
  branch's "any other red is yours" tail, which made the same claim one filter-miss away,
  carries the same qualification, as does the orchestration seat's copy of the rule.

### Changed

- **Cross-lane review of a gate change is a strong preference carried by a mandatory record,
  not a refusal (#426).** On the human's ruling of 2026-08-19 ("Same lane review is a strong
  preference, not a rule"), `just land` no longer refuses `review_same_lane` when a routing
  class 6 landing's reviewer shares a lane with an author. The refusal is deleted, and every
  gate landing now prints exactly one `gate_review=` line naming which of four things
  happened: `cross_lane`, where the preferred check ran; `lane_exhausted`, where every lane
  the registry carries is a lane the issue's records place on the work; `lane_barred`, where
  a free lane existed and every one of them was unreachable, each named with the bar that
  says so — its off-peak window, its breaker, or a provider quota; and `same_lane_chosen`,
  where a free lane was reachable and a same-lane verdict cleared the landing anyway. Those
  last three are three different facts about a downgrade and a reader must be able to tell
  them apart, so the record is not optional and no flag suppresses it. Every cause is derived
  at landing time — exhaustion from `tools/dispatch.py`'s registry against the records, a bar
  from that module's new `lane_bar`, which is the breaker, off-peak and credential rungs
  `candidate_refusal` already asked, read live through the one function so the landing's
  account cannot drift from what a dispatch would have done. `review_same_profile` is
  untouched and still absolute: no instance reviews its own work. `review_lane_unknown` and
  `gate_class_undetermined` also stand, because each refuses a landing whose record cannot be
  computed rather than one whose lanes coincide. ADR-0073 carries the reasoning as Amendment
  A2, with #416's exhaustion rule folded into the new shape rather than left beside it.

- **A review verdict binds the diff it reviewed, not only the commit, so a clean rebase no
  longer orphans it (#417).** `just review record` now writes the exact identity of the
  reviewed diff into the verdict — a SHA-256 over `git diff --unified=0` of the same
  merge-base-relative range `just land` will land, with only the line-number ranges inside a
  hunk header normalised away (the section anchor after them is content and stays) and an
  `index` line flattened for textual files but kept for a binary change, whose blob hashes
  are its only content, so a sibling's landing cannot move it while a change of function,
  bytes or whitespace still does — fetched first, never typed — and the
  landing's never-alone rung accepts a verdict whose SHA has moved only where **both** halves
  hold: the rebase was recorded as clean by the tool that ran it (`just land` and `just land
  --stage` append to `rebases.json` under the review root), and the identity computed over the
  rebased tree still matches. The first build carried the review on `git patch-id` alone, and
  its own review disproved both halves of that: patch-id strips whitespace, so a conflict
  resolved with trailing whitespace the reviewer never saw cleared as "unchanged"; and
  patch-id hashes context, so an upstream edit inside the surrounding lines refused the very
  carry the mechanism existed to grant. Hashing the output cannot prove whether conflict
  resolution occurred at all — only the rebase knows that, which is why its own record is one
  of the two halves. A moved SHA with no recorded clean-rebase chain refuses `rebase_unproven`
  — the verdict never rides a rebase a hand resolved, even one that reproduced the diff
  exactly, because the provenance is missing rather than the content changed —
  an absent or malformed identity on either side is `diff_id_unreadable` and never a pass
  (#41) — which is also the one-time re-review a verdict recorded before this change takes —
  and the limit is stated in the docs and the rung's own prose: a matching identity plus
  recorded clean rebases proves the diff is unchanged and was mechanically replayed, not that
  its meaning survived the move onto the new base — the gate's tests at landing are what catch
  that difference, and they still run.

- **A gate landing whose authors span every registry lane clears as
  `lane_exhausted` rather than refusing forever (#416, ADR-0073 Amendment A1).**
  The cross-lane rung #406 landed had no answer for a branch whose potential-author
  set covers every lane: the admissible reviewer-lane set is empty, so no dispatch
  could ever satisfy it and the landing refused permanently — #405 sat green at the
  gate and unlandable, because the project had deliberately spread its work across
  all three lanes. Where every lane the registry carries is a lane the issue's
  records place on the work, the requirement now degrades to ADR-0071 ruling 4's
  own different-profile rule — already enforced one rung up, so the fallback holds
  by construction — and the landing records the degradation in its own key:
  `gate_review=lane_exhausted`, beside the reviewer lane and the author lanes, so a
  reader sees that the stronger check could not run and what ran instead.
  Exhaustion is the only trigger, derived at landing time from
  `tools/dispatch.py`'s registry and the issue's records and never declared by a
  caller, so a lane joining or leaving the registry moves it in both directions;
  every landing with a cross-lane reviewer still available refuses
  `review_same_lane` exactly as before.

- **A review is judgement-only by construction: no review brief asks for a gate run
  (#353, human ruling 2026-08-14).** Five consecutive reviews had reported `gate=not_run`
  while every review brief asked them to run one — the request was made, the capability
  was absent, and the honesty ritual absorbed the difference. The ruling reversed the
  2026-08-13 decision to build an executable read-only mode and adopted the alternative:
  the reviewer reads the implementer's pasted gate output and triggers no test itself —
  no checkout, no gate, no `just mutation`. `just brief --seat review` now carries
  read-the-paste sections in place of the gate ask, the flake re-run instruction and the
  landing protocol; the dispatcher's default brief derives its gate line from the seat's
  forced permission mode; and the implementer's own brief now asks its close audit to
  quote `just check`, `just unit` and `just mutation`, stating whether any quoted kill
  rate was sampled or exhaustive — the distinction #344's review found hiding an
  exhaustive 91% behind a reported 100%. `docs/review-dispatch.md` carries the ruling,
  the paste contract and the statement that the `codex` sandbox ceiling (#265) is moot
  for reviews rather than blocking them; the remaining independent check is `just land`'s
  re-gate after rebase, which no flag skips.

- **The arbiter walk reads the routing policy itself, and `--routing-refusal` is gone
  (#391).** The never-alone arbiter's routing rung was only as good as the flags a caller
  passed to `just review-loop escalate --routing-refusal` — and no caller ever passed
  them, so an escalation walked past a head the policy would refuse, a check that did not
  run reading as one that passed. `arbiter._walk_first` now runs
  `routing_policy.enforcing_match` per candidate — the landing read, the same one
  `just land` runs — on inputs the escalation derives and no caller declares: the policy
  read off fetched `origin/main`, the branch under review read off the review exchange's
  own `refs/heads/issue-<n>`, merge-base-relative. An escalation with no exchange ref, or
  whose policy will not parse, now refuses by name rather than resolving past a rung whose
  inputs are absent; git that cannot be reached is not a result. Against the shipped
  policy the rung excludes nobody, because since ADR-0073 no row refuses a landing — it
  runs anyway. Ruled on #391 under the human's standing order of 2026-08-16, recorded as a
  delegated decision in ADR-0075 and as ADR-0071 amendment A8.

- **A Codex implementer runs its own gate: the session gates, the harness commits (#405).**
  Three probes replaced the cause recorded as #265. Codex enforces `<root>/.git` as a
  read-only path inside every writable root — deliberate policy, protecting git history from
  the agent — so where the named root *is* a git directory the sandbox creates the `.git` it
  means to protect and libgit2 opens that instead of the real layout. Six arrangements are
  measured and refuted, and the list is closed. The half that is green settles the design: a
  session whose git directory is not a writable root returns `No errored commits` and runs
  `just fast`. So `_codex_writable_roots` names no git directory and no checkout containing
  one — exactly the tool caches the gate was measured or derived to need (`~/.cache/uv`,
  `~/.ansible/tmp`, `~/.cache/ansible-lint`; the proving dispatch
  `d-20260818-185929-ae5491` committed and pushed through the harness but died at
  `check-machine-b`, which had joined the gate a week after the root set was measured), with
  an exact-list test so the next gate stage that grows a cache is a diff rather than a
  discovery — the session writes its Conventional Commits message to
  `.dispatch-commit-message` in its worktree, and after it exits the unsandboxed dispatcher
  commits with that message and pushes the branch to the issue's review ref. A tree edited
  with no message file refuses `commit_message_absent` and is left untouched; the commit meets
  the repository's `commit-msg` hook like any other; authorship is unchanged, the box's
  identity on the commit and the dispatch record for the profile. With the ceiling lifted,
  `SEAT_PROFILE_BLOCKS` ships empty and `codex-luna-max` heads the implementer seat's
  preference list for real — `just dispatch --seat implementer` now resolves to it. Landing
  stays the orchestrator's on this lane, and the end-to-end dispatch #405 asks for as evidence
  has not been recorded yet.

- **The fourth adjudication route, accepted and filed, reaches the surfaces a seat
  reads (#372, ADR-0071 ruling 4 amendment A7).** The human ruled on 2026-08-14 (#334) that a
  finding at Medium or below may be adjudicated **accepted and filed** — the implementer
  agrees it is real, states why the fix does not belong in this diff, and files it as an
  issue on the originating item before landing — not available above Medium and not where the
  defect is in the diff under review rather than conditional on named work outside it. The
  ruling named four surfaces; `just land`'s refusal and `just review-loop`'s writer already
  carried the route (#334, #333). This lands the other two and reaches a third: ADR-0071
  ruling 4's adjudication list gains the route with its restrictions and the Medium ceiling,
  `docs/agents/review-severity.md` carries the rule and its worked example, and the dispatch
  brief's landing section now enumerates all four routes, so an implementer meets the fourth
  before the `finding_unadjudicated` refusal names it at `just land`.
