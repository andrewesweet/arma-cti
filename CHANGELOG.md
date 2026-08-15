# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`just land` refuses an unreviewed or unadjudicated landing, by name (#334, ADR-0071 ruling
  4).** A review rung between routing and the gate enforces the ruling's three criteria: a
  completed review dispatch record bound to the landed SHA (the derivation and the binding
  #332 landed, enforced here rather than re-derived), a reviewer identity the dispatch records
  derive rather than one the verdict claims for itself, and every finding above Low closed
  through one of the four adjudication routes — `fixed`, `arbiter_upheld`, `arbiter_dismissed`
  and `accepted_and_filed` (Medium and below, naming its filed issue and the later work its
  harm is conditional on; human ruling 2026-08-14). Every absence refuses by its own kind —
  no dispatch records, an unreadable plan or result, no completed review bound to this SHA, no
  verdict, an unparseable verdict, a verdict for another issue or commit, a claimed identity
  the records do not derive, the reviewer the records place on the work, an authorship scan
  that could not read every record, and every shape a loop state can be in rather than
  governing — and a clearance states what was read: the dispatch, the identity, what the
  authorship scan did and did not read, and the loop's counts. A diff the trusted exemption
  table lists in full clears on the table alone, with its reasons; a table that will not read
  exempts nothing. Records that name no author at all refuse `authorship_unrecorded` rather
  than clearing: an empty set satisfies "the reviewer is not an author" only vacuously, and
  the arrangement the criterion exists to catch — an instance reviewing the diff it wrote in
  its own session — is exactly the one it would otherwise wave through. Every clearance
  carries both limits it is quoted under: the verdict's same-user limit, and the loop
  record's — it binds no dispatch, SHA or arbiter identity, so unlike the verdict beside it
  its routes are not re-derived at read time. An arbiter route above Low must be *authorised*
  as well as named: the escalation record `just review-loop escalate` wrote has to have fired
  and to name the same arbiter the adjudication carries, so a landing and the terminus over
  the same loop cannot give opposite answers — `arbiter_unresolved`, `arbiter_mismatch` and
  `escalation_unreadable` are the three ways that record refuses, and the clearance prints the
  arbiter, the evaluation and whether the resolution behind it was partial.

- **`just review-loop sync` — the loop folded from the verdict the landing will read (#334,
  #333's command surface, ADR-0071 ruling 4).** `sync --issue <n> --reviewed-sha <sha>` takes
  the verdict `just review record` wrote for that commit — same binding, same identity
  re-derived — and folds its findings into the issue's loop: severities from the record and
  never from a flag, so the seat under review cannot re-grade its own review on the way in,
  which is the one thing `open` and `round` cannot promise. The first call opens round zero, a
  later one carrying ids the loop does not hold records the next round, and a verdict that
  re-grades a finding the loop already holds is refused by name rather than reported as
  unchanged — that drift is what the landing refuses as `review_finding_mismatch`, and
  reporting it as a success left the landing wedged behind a remedy no command performed.

- **`just land --stage` — rebase onto `origin/main` and stop, printing the SHA a review must
  bind (#334).** A verdict binds the SHA it judged and the landing rebases before it reads one,
  so a branch behind `origin/main` previously obtained that commit only as the by-product of a
  refused landing. It runs strictly less than a landing — the rebase and nothing after it, no
  push on any path — and refuses a dirty tree, a conflict and a poisoned tree in the landing's
  own words. A `--dry-run` the rebase will reshape now plans the push as `would_not_run`
  instead of unqualified: with commits to replay, the review rung is not merely unconsultable
  but certain to refuse. A tree with no commit of its own refuses `nothing_to_land` before the
  rebase runs — staging `origin/main`'s tip points a lander at a SHA that is not theirs to have
  reviewed, and a refusal saying "Nothing was staged" is decided where that is still true.

- **`just review` — the review branch exchange and the verdict record (#332, ADR-0071 ruling
  4).** Three actions. `exchange <issue>` pushes a clean tree's HEAD to `refs/heads/issue-<n>`
  (force-moving the ref each round) and verifies the remote resolves it to that exact SHA, so an
  implementer hands a reviewer a branch and the two never share a worktree — the collision #105
  paid for. `record` derives the reviewing identity from the dispatch records the dispatcher
  wrote (seat=review, this issue, `base_sha` = the reviewed SHA, completed end state) and writes
  `verdict.json` beside that dispatch, outside every worktree: the identity is derived, never
  declared, the #322 reasoning one layer over, and it fails closed on any record the scan cannot
  read. `show <dispatch-id> [--satisfies <sha>]` re-derives the identity at read time and refuses
  `sha_mismatch` (naming both commits) rather than letting one commit's verdict satisfy another.
  Both `record` and `show` print the same-user limit beside the record: a convention with a
  mechanical floor, not a guarantee.

- **A typed degradation code on every stratum, so the observatory need not parse prose (#347).**
  `Stratum` carries a `code` beside its value and flag, and the record writes one per signal. The
  eight states — `checked`, `source_unavailable`, `pre_strata_absent`, `container_not_mapping`,
  `unchecked_with_value`, `record_malformed`, `value_fields_absent`, `value_malformed` — are
  derived from a record's raw structure, so records predating the field classify without being
  rewritten. `unchecked_why` stays diagnostic prose and is never a grouping key: #323 left the
  states apart only by their reasons, and an empty one collided exactly with pre-#323 absence.
  Plain strings rather than an `Enum`, for the reason `escalation.Evaluation` records — a module
  re-exec gives two class objects and `Enum` members from the two compare unequal. The flag and
  the code cannot disagree; the type refuses the pair.

### Added

- **`just review-loop` drives the never-alone loop end to end (#333, ADR-0072).** One
  command per act — `open`, `round`, `adjudicate`, `escalate`, `terminus`, `show` — over
  durable per-issue state under `~/.arma-cti/review/`, so a loop survives the turn that
  opened it and the terminus runs exactly once: it files every arbiter-upheld finding on
  the originating item and records every dismissal on the issue thread, and refuses its
  own second run by name rather than filing twice. Every act refuses by name rather than
  defaulting — an arbiter route before any escalation has fired one, a second `open`, an
  unregistered seat, a terminus the loop has not reached — with exit 1 for a named refusal
  and exit 3 for an act that could not be performed.

### Removed

- **The pre-registered admission bar is dropped, and the departure is recorded as one (#328,
  ADR-0071 ruling 6).** No dispatch is refused by an admission verdict: the rung is gone from
  `just dispatch` rather than made permissive, and the dispatcher exposes no standing to read,
  no `admission_escalated` refusal and no `--admission-dir`. **What actually breaks at the
  parser, stated here because a landed commit message cannot be amended and `9afa5ff`'s
  `BREAKING CHANGE` footer got it wrong twice:** the bar had **six** verbs — `bar`, `status`,
  `check`, `audit`, `record` and `reset`, counted off that revision's own parser
  (`9afa5ff^:tools/admission.py:2477-2489`) rather than off the footer. Only `just admission
  check` is gone as a spelling. The other **five** are live verbs of `just trial` meaning
  something else, so a caller typing any of them reaches a working command rather than an
  error, which is the more dangerous half of the break — and the footer's "four" names only
  three of those five, understating that half by `bar` and `audit`. And the second break is
  `just dispatch --admission-dir`, which that footer mentioned only in its body. The bar was
  pre-registered
  precisely so that observed lane behaviour could not move it, and it **never adjudicated once
  across any of its routes** — every one still on probation at the drop, none admitted and none
  failed, four with any record at all and the fullest of those eight assessments against an `N`
  of ten. Dropping it after the observations were in is the move
  pre-registration exists to prevent, taken knowingly on the human's ruling and written down as
  a departure rather than left to be discovered as a silence. Nothing upfront replaces it; what
  replaces it is retrospective (#336) and is not built, so a route's quality is now unchecked
  before its work runs. **ADR-0061 Decision 6 still reads "built and live", and ADR-0071's
  ruling-6 rationale still carries two counts that have moved; both are knowingly left
  standing**: ADRs are a human sign-off gate and the supersession trailer only points forward,
  so the corrections are proposed as `Amended:` trailers and replacement passages, in full, at
  <https://github.com/andrewesweet/arma-cti/issues/328#issuecomment-5304405904> — five blocks
  over three sites, the third of which (ADR-0061's amendment index) was in no finding's list and
  was found by grepping the tree for the counts. Until they land, a reader arriving at either
  decision meets a claim this change falsified.

### Changed

- **An arbiter route names the arbiter that ruled (#334, ADR-0071 ruling 4).** `arbiter_upheld`
  and `arbiter_dismissed` carry the profile the escalation transferred to, read from the
  escalation record rather than from a flag, and both the writer and `just land` refuse a route
  that names none. The same-user limit is unchanged and unclaimed — the name is written by the
  same user, not derived — but an unarbitrated dismissal is now distinguishable from an
  arbitrated one on the record a lander quotes.

- **One loop record, one reader (#334, #333).** The landing rung read `loop.json` through a
  local parser it carried while #333 was unlanded, and a local `just review-loop` beside
  #333's own. Both are deleted: the rung calls `review_loop.load_loop`, and the loop's acts are
  #333's command surface throughout. The loop's store is now guarded and atomic — an unwritable
  review root leaves as a named refusal rather than a traceback, and an interrupted write leaves
  the loop as it stood rather than a truncated record the landing would then refuse. The
  landing still checks the fourth route's three restrictions on read, which the canonical
  parser deliberately leaves to the act of adjudicating.

- **`just land --stage` refuses a tree with nothing of its own to replay (#334).** Staging
  `origin/main`'s tip offered a lander a SHA that is not their work to have reviewed, and hid
  an outstanding merge behind an `ok=` on the re-run after `merge_blocked_by_sandbox`.

- **The arbiter routes are admissible only where the escalation has fired on the finding
  itself (#333).** Round 1's precondition was a property of the loop — the three-round
  wall, or any arbiter verdict already recorded — and round 2's Critical walked through
  that door: once an arbiter closed the wall-held findings, a finding raised in a later
  round inherited the historical verdict as its licence, which is the reopening #333's
  own body forbids. The precondition is now decided **per finding** — the wall holds and
  this finding is one of the held-across findings it read — so a later round's finding
  earns an arbiter only through its own wall, a finding the round itself introduced
  (#356's shape) takes another fix round, and a Low, which never blocks and never feeds
  the wall, takes no arbiter route at all. Held-across siblings stay admissible in either
  order without any sibling clause, because the finding under adjudication is itself open
  and keeping the wall true. Storage still does not re-derive the precondition on read:
  it governs the act, not records written before it existed.
- **The terminus refuses verdicts no arbiter resolution chose (#333).** `adjudicate` at
  the wall needs no `escalate` first, and the round-1 terminus read the missing escalation
  record as an empty arbiter, letting the landing proceed with `arbiter: null`. A loop
  carrying arbiter verdicts now reaches a terminus only through an escalation record whose
  evaluation actually fired — a record that resolved a profile below the wall authorises
  nothing, because nothing transferred to it.
- **The terminus is once by construction, not by an exists-check two acts too early
  (#333).** The landing record's side effects — issues filed on the originating item,
  dismissal comments — plus two local writes are not a transaction: two concurrent
  terminus calls could both pass the check-then-write, and a call that died mid-post would
  repeat its filings on retry. The run now claims a `terminus.pending` marker with
  `O_CREAT | O_EXCL` before its first side effect — exactly one concurrent caller wins —
  and the claim file itself becomes the landing record; a marker left behind names what the
  run was about to post, and the retry refuses by name until it is accounted and cleared
  by hand.
- **The landing record cannot disagree with the claim that wrote it (#333).** The
  marker-plus-record pair left an uncovered mutator race: a crash between the record's
  write and the marker's removal left both files, and a crash inside the write left a
  partial record the retry's first check read as a completed terminus. The record is now
  written into the claimed marker itself and moved onto `landing.json` by one atomic
  rename — the terminal state is the rename, not two files kept in step, so the record is
  never partial and no reachable state carries both files.
- **A malformed escalation record is a named no-result (#333).** JSON that decodes to
  something other than an object raised a bare `AttributeError` out of the command — the
  one failure in the module with no name. It is now the same answer as a record that will
  not decode: an unperformable read, exit 3, never a silent empty arbiter.
- **The record that authorises the terminus is validated, never coerced (#333, the
  arbiter's ruling).** The three deciding fields were read through `str()`/`bool()` over
  `.get` defaults, and there was no malformed `arbiter` the read rejected: `str(None)` is
  `"None"`, which is truthy, so a record naming no arbiter at all authorised the terminus
  and the landing record then carried `"arbiter": "None"` for a later reader to mistake for
  an absence marker. `unchecked` failed open in the same read — an absent key or a JSON
  null both read as *checked*, inverting the one property that field exists to carry. All
  three fields must now be present and exactly the right type — `unchecked` a boolean, so
  `0`/`1` are refused — and anything else is an unperformable read, exit 3, naming the
  field and its value so the file can be repaired.
- **The landing record carries every finding's final verdict (#333).** `fixed` findings
  above Low were absent from `landing.json` — their only trace was the diff under review,
  which post-landing review does not re-read — and a Low left open at the terminus was a
  fact the record could not say. The record now lists each finding with its route (fixed,
  filed, upheld, dismissed, or open), and the fourth route's issue and named condition.
- **A stored loop that will not decode is a named refusal (#333).** A truncated or
  malformed `loop.json` reached the command surface as an unclassified `JSONDecodeError`
  traceback; it is now this module's own refusal, exit 1, like every other state that
  cannot govern.
- **An escalation event claims an arbiter only where a firing transferred to one
  (#333).** A `no_firing` or `unreadable` evaluation carried the resolved profile's name
  regardless — a count of arbitrations that never happened. Only a firing carries it now.
- **The arbiter's exclusions read the production inputs (#333, #361).** The reviewer set
  comes from the issue's own dispatch records through the new
  `dispatch.potential_authors_and_reviewers` scan — authors *and* reviewers, because
  #318's real reviewer reached the records as a review dispatch and nowhere else — and
  `arbiter.resolve_dispatchable` walks the live `(lane, profile, seat)` rungs
  `just dispatch`'s ladder judges by, so a profile resolved here cannot be one the ladder
  refuses two lines later. Every incomplete read (an absent dispatch directory, an issue
  no dispatch worked on, an unreadable record) now leaves the resolution `unchecked`, not
  only the unreadable one.
- **The loop's telemetry carries identities, not counts (#333).** An escalation event
  carries its evaluation kind — firing, silence, unreadable — and terminus events carry
  `finding:severity` identities for every filing and dismissal, so the observatory can
  tell which finding was upheld and which state an escalation was in, not only how many.

- **The review loop's ending is now rules rather than judgement in the moment (#333).** The
  round budget counts only findings *held across* rounds — a finding the re-review round
  itself introduced (#356's shape) takes another fix round, while one an earlier round
  raised and the third re-review still holds (#326's) fires the transferring escalation;
  the stop condition that blocks a landing is deliberately not narrowed to match. A new
  arbiter rule (`tools/arbiter.py`, per the human ruling on #361 of 2026-08-14) resolves
  who arbitrates from the seat registry's escalation entry — head first, falling through
  the entry tail (#326's routing-refused head) and on into the preference list (#318's
  conflicted head), excluding the profiles the issue's own dispatch records place on the
  work and any the routing policy refuses on the branch's paths, recording every exclusion,
  and refusing by name when the walk is exhausted or the column is empty — the blanket
  `fable-high` default is struck, and the `retro` and `orchestrator` cells the ruling
  filled are transcribed into the registry. The terminus computes what the pre-declared
  default owes before it may apply: the gate itself (nothing above Low unadjudicated), a
  filing owed on the originating item for every finding an arbiter upheld, and a recorded
  trace for every dismissal. Rounds, escalations, dispute outcomes, terminuses and arbiter
  resolutions now emit OTel events journaled under `~/.arma-cti/review/` — rounds leave no
  trace in a diff, so a loop shipped without them is a loop whose cost cannot be recovered.

- **`just admission` is `just trial`, carrying the pre-registration harness and the close audit
  that outlived the bar (#328).** `tools/admission.py` became `tools/trial.py`: verbs are
  `bar`, `status`, `report`, `start`, `audit`, `close-audit`, `record` and `reset`. The bar is a
  judgement about a profile and the harness is a mechanism with no opinion about what is
  trialled, so the harness stays — clock started by an explicit act, criteria immutable once the
  first assessment lands, an unrun check never rendering as a pass — and `close-audit` keeps
  #252's six checks reachable, minus the one function that used to read two of their verdicts
  into criteria. The in-world surface list moved to `tools/gate.py`, which every reader of it now
  calls. The store stays `~/.arma-cti/admission/` under `CTI_ADMISSION_DIR`: the name is wrong
  and is kept, because renaming it would orphan the records kept as history. The store's flag
  follows the module: `--trial-dir` is the primary spelling and `--admission-dir` stays as an
  alias, so the flag reads like the tool without adding a second CLI break.
- **`just trial record` refuses a closed trial at the CLI, before it builds the cycle (#328).**
  The library check inside `record_trial_cycle` fires only after the cycle is built, so against
  a closed trial the command used to run a `gh` fetch and a git walk and then refuse
  `trial_criteria_missing` — the wrong name for why nothing can accrue to it. It now refuses
  `trial_closed` at the top, and the library check is kept, so the person and the caller get the
  same answer.
- **#242's orchestration-seat trial is closed as inconclusive (#328, ADR-0071 ruling 2).** Its
  cycles judge a seat at opus/high and the ruling sets that seat at opus/xhigh, so they cannot
  validate the new pair. The records are kept as history; `start`, `record` and `reset` all
  refuse a closed trial by name, so it is closed rather than restarted. The observatory does not
  subsume it: the trial measured five orchestration-process criteria and the observatory measures
  rework, so those five now go unmeasured — a loss, not a substitution. `just trial bar` prints
  them by name rather than as a count, so a reader meets the list.

- **ADR-0071 is amended twice: every dispatchable seat now names its arbiter, and the class 2
  row describes the code (#361, #368).** *A1* fills ruling 2's escalation column — `retro` gets
  `opus-max`, `fable-max`, `orchestrator` gets `opus-max`, `fable-xhigh`, and `recon` and the
  interlocutor are marked not-applicable rather than left blank — and strikes ruling 4's blanket
  *"a seat whose escalation column is empty arbitrates at `fable-high`"*. That default was not
  missing when retro 30's loop escalated; it resolved to `fable-high`, **which had authored every
  round**, so the orchestrator declined it and chose an arbiter by hand. In its place ruling 4
  gains the conflict-of-interest exclusion it never had: where the tabled head is a profile the
  work's own dispatch records place on it, the tool falls through the seat's preference list,
  records what it excluded and why, and refuses by name when the list is exhausted. A seat added
  with no escalation entry now refuses rather than defaulting — adding a seat means deciding its
  arbiter. *A2* replaces the re-founding table's *"class 2 survives unchanged, provisional —
  ruling 1's carve-out, and the only provenance rule left"*, false on both halves since #327: the
  row carries no lane rule, is founded on the route's seats (`orchestrator`, `planner`,
  `implementer`, `review`, `recon`) and refuses `retro` and `fable` on every lane including
  Claude's. The carve-out it was confused with is `orchestrator_claude_only` in the seat table,
  and the policy's surviving keep-on-Claude bar is class 6's. The ADR text moves; the code stays
  as landed.

- **The seat registry carries A1's escalation entries, and the arbiter is resolved from the seat
  that did the work (#361, review round 1).** For one commit the ADR named `retro`'s and
  `orchestrator`'s arbiters and the registry gave them none, so `just dispatch --seat retro
  --list` printed `escalation=none` while the ADR printed `opus-max`. `tools/dispatch.py` now
  carries both entries, and a new `escalation_head(seat)` answers ruling 4's *implementing*
  seat — whichever one did the work — where four copies of the rule said "the implementer's
  seat's" and `tools/brief.py` emitted the implementer's head, `codex-sol-high`, as the arbiter
  for every brief including a retro's. `docs/agents/review-severity.md`,
  `config/escalation-conditions.json` and `tools/escalation.py` are swept to the same wording. A
  seat with no entry resolves to no arbiter and condition 1 stays silent, which is the struck
  fallback's accepted consequence.

- **ADR-0071 and four other surfaces are corrected to what the arbiter code actually does (#361,
  review round 2).** Round 1 closed three findings by recording gaps that were already closed:
  `tools/arbiter.py` had landed under #333 seven hours earlier, and the ADR went on to tell an
  orchestrator meeting an escalation that no tool resolves the arbiter and a human carries the
  exclusion by hand — the very act this issue exists to end, with `just review-loop escalate`
  sitting there resolving it. The three notes are replaced by what is in the tree, cited by file
  and line: the walk is `arbiter._walk`, entry head then entry **tail** then preference list — so
  an entry's second profile is reachable and the "unreachable tail" gap never existed; routing
  refusals are an exclusion rung of their own, fed by `just review-loop escalate
  --routing-refusal`, and a tripped breaker, an exhausted quota and an off-peak window are covered
  by `dispatch.candidate_refusal`, so the trigger is not conflict of interest alone; and #333
  landed the refusal rather than the fallback its own stale criterion demanded. What is genuinely
  not covered is stated instead: the routing policy is read by neither module, so those exclusions
  are only as good as the caller's flags (#326 owns folding it in). Two docstrings that outlived
  their sequencing — `tools/escalation.py` and `tools/brief.py` on "the review loop is sequenced
  work, so rounds are not recorded" — now say where the facts live and why a *brief* still has
  none. `docs/agents/review-severity.md` and `config/escalation-conditions.json` describe the
  resolution rather than only its head. The one live decision left is the class 6 keep-on-Claude
  bar, whose retirement condition #331 spent ten hours before it was written down: #389 owns it,
  replacing an owner (#333) that had closed.

- **The fifth copy of the arbiter rule is corrected and counted, and two false owners are
  replaced by filed issues (#361, review round 3).** `dispatch.escalation_head`'s docstring said
  the conflicted-head fall-through was unbuilt and cited the ADR passage for it — the same
  passage round 2 had rewritten to say the rule is implemented, so the file cited as its
  authority a passage that contradicted it. It is replaced by where the fall-through lives
  (`tools/arbiter.py`, landed `d351a3f`), keeping the true half: this function returns the
  tabled head alone, which is the walk's input and the briefing's field. The copy is added to
  ADR-0071's enumeration, now six; deriving that set instead of counting it is #390's, on the
  arbitration's own finding that a hand-derived enumeration passes its blindness to the sweep
  that reads it. Two owners named a closed issue: the arbiter walk's uncovered routing-policy
  rung was owned by #326, closed the day before the line was written and pointed at from
  `candidate_refusal`'s docstring too — the rung is now stated as uncovered and unowned with
  #391 filed for the ownership question, no owner invented; and the ADR-versus-registry gate
  is #392's rather than an unowned assertion analogised to #354, a different pair of surfaces.
  Three smaller corrections: `just dispatch --list` marked the escalation entry "not resolved
  into" when the arbiter walk starts at it, and now says which resolution passes it by; the
  ADR's only worked example put `codex-sol-xhigh` third in the walk where it is fifth (third is
  its preference-list position, the confusion that paragraph exists to correct); and
  `docs/agents/review-severity.md` and `config/escalation-conditions.json` each listed fewer
  exclusion rungs than `_walk_first` runs — all four are named now.

- **ADR-0071 stops claiming its arbiter-copy enumeration was derived, and four smaller copies are
  corrected (#361, the human's ruling of 2026-08-15).** Round 3's paragraph justified a
  **site**-level enumeration with two **file**-level `git grep` invocations — a claim stronger
  than its method, and the evidence is a sixth in-repo site 140 lines above the fifth in the same
  file. The claim is deleted rather than repaired, and the paragraph no longer asserts the set is
  complete: it is what successive passes recalled, and deriving it instead of counting it stays
  **#390's**. The count is deliberately not corrected here, because a corrected count is the same
  unsupported act one number along. Alongside it: `docs/agents/review-severity.md` had an orphan
  `A` leaving a sentence fragment; `just dispatch --list` told a seat that registers no escalation
  entry that its entry is "walked first by the arbiter", and now says that seat has no arbiter and
  escalation refuses by name; `dispatch.escalation_head`'s docstring described the fall-through as
  walking the preference list, where the code walks the entry **tail** first (held across all three
  review rounds); and `AGENTS.md` and the `justfile` listed `escalate`'s exclusion rungs without
  the registry rung.

- **The routing policy is re-founded class by class on capability and conflict of interest, and
  is no longer the keep-on-Claude policy.** ADR-0071 ruling 1 withdrew provenance as a reason to
  route work, and its re-founding table separates what each class actually rested on. Two classes
  die. *Gated semantic surfaces* rested on provenance and the human sign-off gate on those
  surfaces was never this file — but `.claude/hooks/` and `.claude/settings.json` are the denial
  layer and the permission allowlist, i.e. gates, and this was the only routing rule naming them,
  so those two paths move to the conflict-of-interest class rather than falling out. *The
  Anthropic plan meter* dies because the meter is read over plain HTTP at a fixed URL with no
  Claude session involved. Of the five survivors: *retros and ADR authorship* splits, the retro
  half dying with ruling 3 (a retro lands nothing, so it needs no routing rule) and the surviving
  ADR-authorship half being re-founded on the **seat** — the class admits the whole route ADR-0071
  rulings 2 and 4 require between them (`planner` authors, `implementer` lands because the planner
  neither gates nor lands, `review` reviews that landing because no change lands alone), on any
  lane including a non-Claude one, and refuses every other seat on every lane including Claude's,
  because ADR authorship rests on seats rather than on which provider answered; *the #181 shape*
  survives with a capability remedy — route to the planner seat and escalate — matched to the
  transferring-escalation condition of the same name, which fires on the class the same issue
  body classifies into; *in-world landings* narrows to a rule about subagents, because a subagent
  cannot hold the corpus's foreground wait but the top-level session `just dispatch` launches
  can, so the class bars no dispatch route while remaining the one authority for what an in-world
  surface is; and *the gates themselves* now carries two rules that are not the same rule, and
  says which one refused you — the conflict-of-interest invariant, which binds every instance
  including Claude's and which **no refusal enforces** until the exemption list lands, and the
  older keep-on-Claude bar, still lane-selected and kept because retiring it first would leave
  the gates with neither. The invariant's enforceable half is enforced: the class carries no
  exception at all, the withdrawn `proposal-only` marker included. Class ids are now stable
  historical handles rather than positions: the two retired ids leave gaps rather than
  renumbering the rows other modules address by id, and a table dropping one of those rows is
  refused instead of governing silently, the ADR-authorship class among them — at that landing
  the only row that refused on the Claude lane, so dropping it would have returned that lane to
  exempt-from-everything; #327's second round gave the lane a second refusing row, the
  orchestration class below.
  The policy states its own incomplete coverage, and `just land` and `just dispatch` print that
  statement on every routing verdict — refusal, clear read, and the reads that did not happen
  alike. A Claude landing is told it was *exempted* rather than cleared, and a Claude dispatch
  that ran on an unreadable policy is told the check did not run and that a seat-bound class
  binding that lane escaped through the bootstrap unchecked. The one refusal that follows a push
  that already happened keeps the lines the landing earned rather than replacing them, because
  that lander is the only one whose work is on `origin/main` regardless.

  **One conflict is flagged rather than resolved.** ADR-0071's re-founding table prescribes
  `docs/adr/` as the ADR-authorship class's landing path, and the class carries none: a
  seat-bound row is enforceable only where a seat exists, and `just land` is handed a lane and a
  diff and no seat, so such a row carrying landing prefixes would clear at dispatch for a seat it
  admits and refuse the same route at landing. The row states the departure and its reasoning;
  amending the ADR, or covering the departure with an ADR-0013 record, is the human's. A second
  departure is labelled rather than left to be spotted: the table binds the class "to the
  planner's list", and read literally that is the deadlock, so the row admits the seats rulings
  2 and 4 name and says that this clause is a synthesis rather than a conflict. The row also
  admits `recon`, which is not part of that route: a seat that authors, lands and reviews
  nothing cannot author an ADR, so refusing it barred a read-only sweep without protecting
  anything. And the row flags its conflict with `AGENTS.md`'s Model roles paragraph, which
  still sends "anything touching ADRs" to a `fable` seat this class refuses; ADR-0071 ruling 2
  supersedes that mapping in substance, and closing the overlap is #329's and #330's.

  **The policy file carries the pre-#326 document beside the new one for one transition
  window.** A parser is imported by a running process, so an in-flight worktree's `just land`
  reads the fetched policy with the module it started with — and the pre-#326 parser demanded
  the ordered class table 1..7, which retiring two ids breaks. Shipping only the new table would
  have refused every in-flight landing and dispatch until each worktree rebased, on a remedy
  telling the reader to repair a policy that is not broken and pointing them at a gated file.
  So the re-founded document lives under `routing_classes` and its two sibling keys, the
  unprefixed `classes`, `issue_exceptions` and `route_exceptions` keep the pre-#326 document
  frozen, and a parser reads one set whole and never mixes them: an old process is governed
  exactly as it was, and a new parser handed `origin/main`'s older copy still reads it.
  Deleting the frozen half is owned by #365, not before 2026-08-21; the condition that stood
  here before — "once no worktree predating this landing is in flight" — was withdrawn on
  arbitration because it is not computable, `just worktree list` sweeping registrations and
  this box carrying over 150 of them, most long abandoned.

  **Two lines a reader used to be told wrongly.** A dispatch whose class was lifted by an
  exception is now told `routing=excepted` with the class named, instead of `routing=clear`,
  which reads as "no class applies"; and the `just land` re-run that finishes a blocked merge
  names its skipped routing and corpus rungs, because that run is the one that prints
  `ok=landed` and the one a lander quotes into an issue.

- **The `foreign` concept is gone from the lane and seat model, and the eligibility ladder it
  hung from is gone with it (#327, ADR-0071 ruling 1).** The seat table's `foreign_eligible`
  column is replaced by `claude_only`, which exactly one seat carries: `orchestrator`, the
  carve-out. Every other seat dispatches on every lane — `fable` included, which ADR-0061
  Decision 2 had barred from every non-Claude lane — and the refusal a dispatcher meets for
  the carve-out is now `orchestrator_claude_only` where it was `seat_not_eligible`. The
  standing retro allowance of 2026-08-09 (#300) is deleted with the ladder it suspended:
  ADR-0071's trailer supersedes that ruling, so `just dispatch --list` loses `foreign=`,
  `seats_eligible_on_foreign_lanes=`, `seats_claude_native_only=`, `seat_allowance=` and
  `retro_approved_profiles=`, and gains `seats_claude_only=`. `fable` joins the admission
  bar under the citation bar, for the same reason `planner` and `retro` carry it — its
  output is claims, and no gate runs over a claim — so a fable route off Claude accrues a
  record and can spend its two attempts rather than running unjudged; the seat-bar test
  asserts equality against the carve-out again, after review round 1 caught its replacement
  asserting only the containment that hid the gap. One provenance refusal deliberately
  survives outside the seat table — routing class 6's keep-on-Claude bridge, owned by #331
  — and the prose that claimed no second rule existed now names it, its owner and what
  retires it.

  **Round 2: the count round 1 wrote was wrong, and the fix went into the table rather
  than the prose.** The paragraph above said one provenance refusal survives outside the
  seat table; two did. Routing class 2 `orchestration` was lane-selected by the identical
  mechanism as class 6's bridge — no `required_seats`, so it refused every seat on every
  non-Claude lane for an issue declaring `Routing-class: orchestration` and cleared the same
  declaration on Claude — because its `seats: ["orchestrator"]` reads as scoping and `seats`
  is one evidence term, never a filter (#366 files the semantic; the fix here does not wait
  on it). Class 2 was re-founded on its seat: from that landing it refused an orchestration
  declaration taken by any seat but `orchestrator` **on every lane including Claude's**,
  admitted the orchestrator seat itself, and — being seat-bound — carried no landing
  prefixes, so an orchestration-docs diff was no longer refused at `just land` off Claude;
  the keep-on-Claude half of the rule was the seat table's carve-out, unchanged. A test
  walked the table and pinned class 6 as the one lane-selected refusing row, so the count
  was measured rather than asserted in prose. Class 6's bridge is also described whole for the first time — its issue
  half refuses a dispatch naming the gates, its landing half refuses a non-Claude `just
  land` touching them — #331 is named in the remedy a refused reader actually sees, the
  withdrawn word is retired from the live remedies that print on every refusal (the frozen
  pre-#326 half keeps its copy until #365 deletes it), and `fable`'s citation bar is
  recorded as an interval measure for the window between this issue and #328, which deletes
  the module — not a decision about how the seat is judged in perpetuity.

  **Round 3: the re-founded orchestration row admits the whole route, not the one seat.**
  Round 2's `required_seats` appointed `orchestrator` alone, which repeated on class 2 the
  exact deadlock #326's review had fixed on class 3 — an issue declaring
  `Routing-class: orchestration` could be planned by no seat, landed by none, reviewed by
  none (ruling 4's review dispatch was refused on every lane) and reconnoitred by none, so
  such an issue was dispatchable only to the one seat that must not review its own landing;
  #331, filed with that marker, was the concrete victim. The row now admits the route —
  `orchestrator` to perform the act, `planner` to plan it, `implementer` to land it,
  `review` to review that landing, `recon` on the read-only ground class 3 already admits —
  and refuses `retro` and `fable` and nothing else, a thinness named in the row's remedy
  because whether the row should be widened no further but deleted outright is the human's.
  The round also walks the row: a test now exercises every seat on two lanes through the
  dispatch rung itself; the lane-selected-row count is measured by differencing the refusing
  set across lanes rather than by re-deriving it from field shapes; and the counting prose
  that still said one row binds the Claude lane — in `just dispatch`'s clearance docstring
  and in this file's own re-founding entry — now says two.

  **Round 4: the walk could not red on a re-narrowing, and a pin now can.** Round 3
  credited its walk with an ability it never had — the walk's expectations are literals in
  the same file as the row, so a round that narrows the row and moves the literals together
  stays green — so the claim, made here and in the walk test's own docstring, that the walk
  "would have caught round 2's appointment" is corrected: review caught it, and what reds
  on such a round now is a structural pin asserting the route against the seat registry and
  the two rulings the row carries, while the walk keeps the job it is fit for — making a
  re-founding loud in the diff. The class 2 remedy now flags, as class 3's already did,
  that `AGENTS.md` still sends "process docs" — among them `docs/agents/orchestration.md` —
  to a `fable` seat the row refuses: a stale sentence rather than a wrong row, the overlap
  #329 and #330 own. Review citations across the routing surface now name their issue and,
  where known, the reviewing dispatch, because #326 and #327 each had a "review round 3"
  and the bare ordinals collided; the lane-selected row count is described as the symmetric
  difference that measures it; and the measurement test's `noqa` is bare with its
  justification above the line, where the length gate can still read it.

### Fixed

- **`just review` round 1: five review findings on the verdict machinery (#332).** Completion of
  a reviewing dispatch is now read from the dispatcher's own typed outcome — only `outcome=ok`
  completed — because a refused run (`quota_exhausted`, `provider_error`, an unclassified crash)
  still carries a returncode and an `ended_at`, and reading those as completion let a verdict be
  recorded against a review that never happened. The exchange's clean-tree check fails closed: a
  `git status` that fails and prints nothing now refuses as `git_failed` instead of reading as an
  empty — clean — tree and force-pushing on the strength of an absence it manufactured itself.
  `show`'s identity re-derivation checks the profile and the lane as well as the dispatch id, so
  a hand-edited identity field refuses `identity_mismatch` instead of being printed. Writing a
  verdict is one atomic act (`O_EXCL`), so concurrent `record` calls cannot overwrite each
  other's findings; a partial file occupying the slot refuses `verdict_unreadable` with its
  recovery named, and a failed write leaves nothing behind (`verdict_unwritten`). The recipe's
  refusal vocabulary now lists every class the tool emits.

- **`just review` round 2: two review findings on the verdict machinery (#332).** Recording a
  verdict into a dispatch directory that is unwritable, or that was removed between the binding
  read and the write, now refuses `verdict_unwritten` like every other write failure instead of
  escaping as a traceback — staging is the first act that needs the directory writable, and it now
  sits inside the failure boundary. The clean-tree fix carries the test it lacked: a corrupted
  index makes the real `git status --porcelain` fail with empty stdout, and the test is proven by
  reverting the fix and watching it red — the exchange force-pushing on the strength of a failed
  status it had read as a clean tree — where the first test's stub passed against both.

### Added

- **The never-alone decision surface is one module, and the exemption list is inverted: every
  landing is reviewed except what a named list exempts (#331, ADR-0071 ruling 4).**
  `tools/review_loop.py` owns the whole surface — exemption evaluation, the round budget,
  per-finding adjudication — and bridges into `tools/escalation.py` for the transferring
  conditions built earlier. The list ships empty in `config/review-exemptions.json`, because
  nothing has earned off it: what may grow it is ruling 6's pre-registered question, and that
  answer arrives as evidence at a retro, never as an agent's convenience in the moment. A diff
  touching the list is never exempt under it, whatever the list says — and the refusal is
  proven the way the issue demanded, by constructing the touching diff with a live entry
  covering its other paths and watching the refusal fire, not by reading the guard; a list
  entry naming the list itself is refused at parse. The same refusal settles which copy judges
  a landing: a diff not touching the list sees identical copies in a worktree and on
  `origin/main`, and one touching it is exempt under neither, so the choice cannot change a
  verdict. The loop models four adjudication routes — fixed, arbiter upheld, arbiter
  dismissed, and the human ruling of 2026-08-14's *accepted and filed*, available at Medium
  and below only, where the implementer agrees the finding is real, names the work outside the
  diff its harm is conditional on, and files the issue before landing. Each finding takes
  exactly one adjudication; a finding raised in a later round is a new item with its own id,
  not a reopening. Rounds are stamped and validated, never rewritten. The escalation bridge is
  a material change the sequencing banked on (#348): it records the two wall facts — review
  rounds and a finding above Low — that nothing recorded until this module, and that is what
  makes **condition one** fireable for the first time, its arbiter staying a caller-resolved
  fact. Conditions two and three read the same wall but wait on more: two on a recorded
  `prior` history, three on recorded `attempts` — neither fact a loop carries — so both still
  emit nothing, and #348's sequencing of them remains open rather than complete.
- **Transferring-escalation conditions are data, emitted to an agent only when one fires.**
  Escalation splits in two: *consultative* escalation borrows judgement and keeps control, so it
  needs no condition; *transferring* escalation hands the task to a higher profile and fires only
  on a named condition. ADR-0071 ruling 5 seeds four such conditions, each stated as something a
  tool decides from recorded facts rather than something an agent judges — a review cycle holding
  a finding above Low after three fix rounds; two consecutive items of one routing class each
  reaching that state; an item whose second attempt from a clean base on a different profile also
  reaches it; and an issue declaring the #181 shape. They live as data in
  `config/escalation-conditions.json`, and `tools/escalation.py` decides each and emits the fired
  condition with its remedy, or nothing at all when none fire — never as prose a memory file loads
  every session. An input a condition needs that could not be read is a third state, distinct from
  "nothing fired": it is a typed outcome — `Unreadable`, alongside `Firing` and `NoFiring` — that a
  consumer narrows to by a `kind` value rather than by type, because the loader re-executes the
  module on each call and two copies are not one type to `isinstance`; so it cannot be mistaken for
  the silence reserved for "nothing fired". A `Firing` that also has an unreadable input carries
  both — its fired emission is not lost to the third state — and a condition table missing a row
  the code decides is rejected rather than governing silently as "nothing fired". Neither the
  combining step nor the renderer falls through to that silence for a kind it does not recognise —
  both match it and refuse the rest, because the fall-through is where value discrimination could
  lose a distinction in its turn. In the brief the unreadable inputs render under their own heading
  rather than announced as a firing (#323, #347 — the source-unavailable code). The list grows only
  at a retro. Of the four, only the #181-shape condition is
  decidable from the dispatch record today (its routing class); the other three are decided by the
  tool but wait on the review loop and observatory to record their inputs, and a fact no record
  carries is `None` and emits nothing rather than being guessed. A fired condition reaches the
  agent through `just brief`'s new `## Escalation` section.
- **A Remote Control session the bridge kills is now said once, at the top of the next
  orchestrator turn.** The RC servers spawn every worktree session this project runs from a
  phone, and when the bridge cannot refresh one's session token it kills that session's process
  and records the fact nowhere durable: the transcript simply stops, telemetry goes quiet at the
  last completed turn with no error event, and the only account of it is three lines in a tmux
  pane whose 2,000-line scrollback a reconnect storm evicts within seconds. On 2026-08-12 a
  session died at 07:13 and the loss was noticed at 22:44; two earlier instances on 2026-08-06
  were never noticed at all. The RC wrappers now watch their pane log for those lines and record
  what they saw, and `just watch-report` prints one line per unread crash — naming the kept
  worktree and the `claude --resume` command that reopens it, derived from the transcript rather
  than typed. It only notices: nothing restarts a session, because those servers run at
  `--permission-mode bypassPermissions` and a process that resurrects such a session on a
  transport fault is a worse failure than the one it repairs. A refresh warning is kept distinct
  from a crash, so a warning that stands alone does not read as a lost session, and a crash
  arriving after an acknowledged warning still surfaces.
- **The dispatch record carries the pre-work strata the observatory needs to compare profiles
  fairly.** ADR-0071's observatory attributes outcomes to profiles, and assignment is not random
  — an in-world issue reaches a different seat than a tools-only one — so a comparison that
  ignores that is a comparison of the router wearing a profile's clothes. The record now carries
  three signals knowable *before* the seat starts work — the gate tier, the routing class and the
  issue's labels — captured at dispatch and never reconstructed afterwards, because an
  outcome-shaped field is exactly the confound the strata exist to keep out, and the record
  carries none. Each signal carries #322's `checked` flag beside its value: a confident value
  standing alone cannot tell 'the issue has none' from 'nobody could look', and reading the two
  the same is the stratification error #323 was filed to prevent. So `--issue-body` arms a
  dispatch where `gh` cannot reach GitHub and labels are *unchecked* rather than empty; an
  unreadable CONTEXT.md leaves the gate tier unchecked rather than guessed; an unreadable policy
  leaves the routing class the same; and a genuine absence — no labels, no class — is a checked
  stratum, the third value never collapsed with 'could not look'. The routing class is lane-blind:
  `classify_issue` walks the policy's `issue_match` without the lane gate that exempts
  `claude-native`, so a Claude-native dispatch carries the class a dispatch on any other lane
  would, and a body that declares no class is the empty string rather than a blank that hides a
  failure to look. A pre-#323 record reads
  back honestly as nothing-recorded-nothing-checked rather than a guess dressed as a value.

- **A review can no longer be dispatched onto the profile it is reviewing, and can no longer
  edit.** ADR-0071 ruling 4's never-alone rests entirely on the reviewing instance being a
  different one, and until now it was not: the `review` seat shares the implementer's preference
  list and resolution took the head, so both resolved to the same profile and every review was
  same-model. A review dispatch now declares its subject — `just dispatch --seat review
  --reviewing <profile> …` — and resolution removes that profile before walking the list, along
  with **every other profile the issue's own dispatch records place on the work**, preferring an
  entry on a different lane among what is left. Removing the declaration alone would enforce the
  narrower "not the one you named": on a branch two dispatches touched, declaring one left the
  other eligible to review work it may have coauthored, through a field the proposer controls.
  Preferring is an ordering and not a filter: where the only remaining entries share the reviewed
  lane, one is used, because the invariant is about the instance producing the verdict and provider
  diversity is the preference. Where the exclusion leaves nothing, or a caller names the reviewed
  profile — or any other profile the records carry — with `--profile`, `review_same_profile`
  refuses rather than proceeding same-model; a dispatch that declares no subject at all is refused
  too, since resolving it anyway would take exactly the head the implementer took. The subject is
  named by the caller and **checked against the issue's own dispatch records** rather than
  believed: a declaration alone settles nothing, since `--profile opus-high --reviewing
  codex-luna-max` names two registered profiles and passes every check while the implementing
  instance clears its own work. What those records support is stated exactly rather than
  overclaimed — nothing on a dispatch record names the commits a run produced, so a planner, a
  recon, a stopped run and a successful no-op are indistinguishable from the implementer that
  wrote the diff, and the result is a *potential*-author set: right for an exclusion, wrong for a
  claim of authorship, so the route reads `reviewing_checked` and never `reviewing_verified`. A
  declaration a **complete** read contradicts is refused `review_subject_contradicted`; one
  unreadable record anywhere leaves the route `reviewing_checked: false` with its reason — while
  everything that *was* read is still excluded — so ruling 4's landing check meets the truth rather
  than an optimistic summary. A record that cannot name its profile counts as unread for this
  purpose even though it parses: its dispatch ran on an unknown profile, which is therefore
  excluded nowhere, and a scan that accepted it would report itself complete with an unknown
  potential author still eligible to review. `just brief --seat review --reviewing <profile>`
  carries the same relationship into a composed briefing, and refuses the option on a seat that
  reviews nothing in `just dispatch`'s own typed refusal shape — the same
  `refusal=reviewing_without_review_seat` lines, rendered from the dispatcher's refusal rather
  than paraphrased. Separately, the seat now
  **forces** its permission mode instead of inheriting the writable `acceptEdits` default: `plan`
  on the `claude` family and `--sandbox read-only` on `codex`, over whatever the caller passed,
  printed as `route_permission_mode=plan forced_by_seat=review` rather than applied silently.
  `just dispatch --list` states both rules, and the dispatch record names the profile under
  review so ruling 4's landing check can ask later.

- **The Claude seat surfaces are generated from the dispatch registry, and `just check` catches a
  drifted one.** A seat's `(model, effort)` pair was typed out wherever a surface wanted it — the
  `.claude/agents/` definition, the interlocutor skill's frontmatter, and the always-loaded
  prefix's own description of the mapping — which is how the interlocutor's pair came to exist in
  five places and how `cti-implementer`'s came to disagree with ADR-0071 ruling 2's table with
  nothing to notice. `tools/generate_seats.py` writes every surface from `tools/dispatch.py`'s
  registry instead, each seat declaring the first `claude-native` profile in its own preference
  list, and `just generate` runs it. Nothing decides a pair any more; the registry does, once.
  The check earns its place on the way these surfaces fail: both of them fail **open** (ADR-0068),
  so a hand edit or an un-regenerated registry change means a seat that answers at a tier nobody
  ratified and says nothing about it. `just check-seats` still asserts a pair is declared and
  valid; the generated-file check now asserts it is the registry's. Writing converges the
  directory rather than adding to it, so a retired seat's file is removed and named rather than
  left to be obeyed. Two consequences of reading ruling 2's table mechanically: `cti-implementer`
  is opus/low, the native tail of that seat's list, and `cti-recon` is haiku/medium. The
  interlocutor's row governs both its surfaces without becoming a dispatch route — it is
  registered as `DECLARED_ONLY_SEATS`, which nothing resolves through, so `--seat interlocutor`
  stays unknown (ADR-0068 stands). A pair narrated in prose is a declaration surface too, so the
  interlocutor skill's description, its opening sentence and the `/model` and `/effort` commands
  it tells the human to type are all checked against the registry as well — three notations of
  one fact, one written and two guarded. Guarded rather than rewritten on purpose: a generator
  that owned every matching string in a file a human wrote would silently turn a sentence
  comparing two seats' tiers into one comparing a tier with itself, and `just generate` — the
  remedy the gate itself prescribes — is what would do it. So a disagreeing sentence is a
  `pair_drift` finding a human fixes, and `just generate` reports it and ends non-zero rather
  than editing prose it did not author. Naming one of those two commands without the other is a
  finding too, because a session set to half a seat's tier runs the other half at whatever it
  already had. And the wiring itself is pinned by its effect rather than by its text: a test
  drifts a seat file, runs the repository's own `just check` with every other rung stubbed, and
  requires it to go red — with two negative controls showing the routes a text assertion could
  not see, an orphaned recipe and a command in a branch that never executes.

- **`just dispatch --seat S --issue N` now resolves its own profile, and the record says which and
  why.** Naming a seat is the ordinary way to dispatch. Each seat carries ADR-0071 ruling 2's
  ordered preference, head first, and the planner walks it to the first entry dispatchable *right
  now* — reading the `(profile, seat)` block, the profile's admission standing, the lane's breaker,
  the human's off-peak rule and the lane's credential, each by calling the same function the refusal
  ladder calls rather than keeping a second copy. So the `implementer` head `codex-luna-max` is
  stepped past on #265's gate ceiling, and what was walked past — with each refusal's own name and
  failure class — lands on the dispatch record beside what was chosen, which is what attributing an
  outcome to a profile later needs. A whole list unavailable is `seat_list_exhausted`: named, never
  a silent fall back to something the seat's table does not carry, and never into the escalation
  entry, which is a judgement about the work rather than a fallback for a busy head. `--profile`
  keeps working and stays subject to every `(profile, seat)` refusal — a way of choosing, never a
  way around one — and now requires `--lane` beside it or neither. The exhaustion refusal's remedy
  is written to be typed: it names the lane-and-profile pair rather than `--profile` alone, and a
  seat that registers no escalation entry is told so rather than offered one.

- **The seat table is the ADR's, and `mechanical` is retired.** `planner` and `retro` join as seats
  of their own; `mechanical` leaves the dispatcher's roster, the ledger's lands-or-not map and the
  admission bar together, because it named a cheaper tier rather than a different job. The
  admission bar's one inheritance route went with it and the map is now empty, with a test holding
  "no seat inherits" as the invariant. `just dispatch --list` prints each seat's preference and
  marks the escalation entry as one resolution does not walk.

- **The dispatch registry carries three new profile tokens and the first `(profile, seat)` block.**
  `codex-luna-max` and `codex-luna-medium` name Luna (`gpt-5.6-luna`), read from the authenticated
  Codex CLI's own model cache alongside sol and terra; `opus-low` is the native tail of the
  `implementer` preference list. Luna enters on publication — a named exception to the
  measure-before-building rule, not an application of it. ADR-0071 ruling 2 also blocks
  `codex-luna-max` from the `implementer` seat: #265's measured gate ceiling holds it below the
  binary capability rule, because no `writable_roots` set lets a Codex dispatch both commit and run
  its own gate. The block is the one home a future seat resolver (#321) will consult, not a second
  copy; the same profile dispatches normally on the read-only `recon` seat, which needs neither.
  `just dispatch --list` renders the block beside the profiles it touches, naming the ceiling each
  pair waits on, so a reader does not discover the exception only by attempting the dispatch.

- **ADR-0071 records the rescission of the foreign lane and the arrival of never-alone review.**
  ADR-0061's decisions 2, 3 and 4 are withdrawn: eligibility stops being a property of provenance,
  the graded authority ladder goes, and the word *foreign* leaves the vocabulary. Decision 5
  survives and is strengthened, since it is now the only thing between this project and an invented
  ranking of providers. One carve-out remains and it is provisional — the orchestrator stays on
  Claude until a Codex backup exists. Alongside it: seats carry ordered profile preferences rather
  than one `(model, effort)` pair; retros become their own kind of work that files backlog items and
  lands nothing; no change lands without review by a different session, with per-finding
  adjudication and a pre-declared default at three rounds; the admission bar gives way to a
  retrospective observatory that ranks on rework and never combines three incommensurable spend
  meters. Every decision is the human's, taken in session on 2026-08-11.

- **`Supersedes:` is a checked field-block trailer**, not a convention on paper. Every ADR from
  0071 carries one line per superseded ruling, or the single line `Supersedes: none`, and
  `just check` refuses one that does not. It reads no prose: three drafts tried to detect
  supersession from the body and three independent reviews defeated each in turn — a narrow
  `rescind|supersede` pair missed every one of ADR-0071's own withdrawals because they say
  "withdrawn"; widening it still missed "deleted", which the same ADR uses; requiring a governance
  noun on the line broke on wrapping; a negation guard then discarded "withdrawn *without*
  changing decision 5". One line per target rather than a wrapped list, so `rg '^Supersedes:'`
  returns the whole amended set. The convention starts at 0071 and its gap — an older ADR amended
  later — is recorded in the code (ADR-0071 ruling 8).

- **`docs/agents/review-severity.md` anchors Critical/High/Medium/Low** against four worked
  examples from this repository's history, so the never-alone loop's stop condition means the same
  thing to instances from different model families. The four definitions are kept as the
  independent reviewer of ADR-0071 wrote them, rather than replaced by the author's.

- **The squad-leader role is playable.** The Phase-1 Stratis mission authors one slot per side at
  that side's Base (`cti_squad_leader_west` / `cti_squad_leader_east`, `maxPlayers` 3 → 5), a new
  server sweep reports who is standing in one, and the daemon folds that claim into ADR-0070's
  lifecycle: taking a slot mints the shell, leaving suspends it if the Commander has not filled it
  yet, and returning hands back the same Squad with its minted id — and, for a Squad that was
  filled, with the standing Order it kept while an AI led it. Unlike a Commander's, the assignment
  is deliberately not latched for the Play Session, because the whole of rulings 6 and 7 is that
  the sweep sees the player leave and come back. The world's half of the two Effects #310 declared
  now exists too: `squad_enrolled` pairs the player's group with the minted id — and, for a
  returning player, joins him into the Squad that carried on without him and seats him at its head
  — while `squad_filled` spawns the composition's men through the staging-group route a Reinforce
  already uses, because a player-led group is not the server's to write into (#312, ADR-0070
  rulings 1, 5, 6 and 7).
- **A player squad leader leads a roster Squad, and it begins as a
  composition-unassigned shell** (ADR-0070, #310). Taking the role mints a dedicated Squad at own
  Base with the player as its sole member — one man, no composition, no Funds spent — and it is a
  roster Squad in every other respect: ordered, sampled for presence, snapshot-persisted, counted
  against the force a side may field. The Commander assigns its composition exactly once, through a
  second catalogue entry (`reinforce_composition`, naming the Squad and the type) at ordinary
  Reinforce pricing — 70 Funds for the authored eight-man rifle Squad whose player is already
  standing — and the composition is fixed from then on. A squad leader may not choose his own
  Squad's first composition; ADR-0040's existing principal rule refuses him without a new branch.
  Disconnecting before the first fill **suspends** the same shell: it keeps its minted id,
  contributes no presence, is ineligible for filling, and comes back at own Base still unassigned
  with no Funds moved. Two Effects carry the world's half — `squad_enrolled` (which group answers
  to the minted id; it creates nobody and spends nothing) and `squad_filled` (the Squad, the
  composition type and the size). Three typed refusals arrive with them, each because an existing
  code would have lied: `composition_unassigned`, `composition_fixed` and `squad_suspended`.
- **The AI Commander fills an eligible player shell rather than buying a net-new Squad**
  (ADR-0070 ruling 2, #311). When it decides a composition is needed it now looks first for one of
  its own active, composition-unassigned Squads standing at own Base, and fills that with the very
  composition the Purchase would have bought — 70 Funds against 100 for the authored rifle Squad,
  so the ruled route is the cheaper one too. An allocation priority rather than a new way to spend:
  the existing Reinforce-or-Purchase choice is settled first and only a Purchase is ever stood in
  for, so a refill that already won keeps the cycle's one spend. The map's one-Squad-per-Objective
  cap and the wire's force limit bar a Purchase and not this — filling a shell adds no Squad — so a
  Commander at its ceiling now fills the shell where it used to spend nothing. The funds row names
  the shell it preferred and the Purchase it stood in for.
- **A planner decision that substituted something for its ranking's winner now says so in the
  structured trace** (#315). The shell fill above is chosen after the ranking rather than inside
  it, so it appears in no candidate and only the row's prose explained it — invisible to anything
  reading the trace mechanically, the independent oracle of Phase 3 included. Each decision may now
  carry a substitution record beside its candidates, naming what was displaced and at what price,
  and telemetry carries it on the rows that have one. The candidates themselves are untouched:
  pricing the fill onto that ranking is what would have sorted a cheaper also-ran above a refill
  that won outright. The contract the record sits under is now written down where a consumer reads
  it — the candidates are the ranking, the choice is the decision, and the two need not agree.
- **Snapshot version 2**, an additive migration whose safe default is what every Squad written
  before this decision was — composition-assigned, active, unowned. A saved Squad now carries its
  player's UID, whether its composition is assigned, and whether it is suspended (#310, ADR-0070,
  ADR-0008).

- **`just dispatch --stop <id>`, the supported way to stop a dispatch**, and a
  `worktree_occupied_by_dispatch` refusal that stops a second one entering an occupied tree.
  Both come from #105's sixth instance, where a seat killed a dispatch, saw `ps -p <pid>` return
  nothing, pre-flighted the tree clean and re-dispatched into it — while the session it thought it
  had killed worked in that tree for another half hour. `--stop` resolves the dispatch id to its
  worktree and then to every process whose `/proc/<pid>/cwd` is inside it (the session **plus** the
  MCP servers it spawned — four processes in the incident), signals, and **verifies by re-scanning**;
  a tree still occupied after `SIGKILL` is `finding=stop_unverified`, never a success. It never keys
  on a pid, every refusal writes nothing and kills nothing, and a stop on a dispatch that already
  ended is a named outcome (`already_finished` / `already_stopped`) rather than a refusal or a silent
  success. The dispatch-time rung reads the record directory as the authority — no `result.json`
  means live or dead-without-writing-one — and names the holder (#308).

### Changed

- **The validated-marker gate now counts inline exemplar lists, closing #186's second violation
  shape.** Every `_(validated ×N — …)_` exemplar opens reference-and-colon (`#NN: `,
  `ADR-NNNN: `, `Phase N: `) under the convention the human ruled on #186 (Option A), and
  `just check` reds when a list's openers disagree with its ×N — an unpruned list must open
  exactly N exemplars, a pruned one exactly the newest five with ×N above five. AGENTS.md's six
  lists are normalised to the convention in the same commit; no exemplar's meaning moved. What
  stays unproven is named at the checker: a pruned tail's count rests on the process log's prune
  record, and status headers stay a lower bound.
- **An Order now reaches a Squad that is not the server's.** `cti_fnc_orderApply` finished by
  making the Order's own waypoint the group's current one, on the server — and that command takes
  local arguments, while a group leaves the server the moment a player leads it and does not come
  back (#189). From the day the squad-leader slot ships, an Order to a player-led Squad would have
  recorded on the group, displayed as a task, and never become what the group was doing: a defect
  every test the project has would pass. The call is now made where the group is. The mission's
  remote-execution whitelist is untouched and stays one function long — the rules it carries bind
  clients, and this is the server (#312, ADR-0070).
- **The map UI and the force-limit refusal say Purchase where they used to say buy** (#146,
  #139). The three surfaces a human Commander actually reads — the Tab hint with no Squads to
  cycle, the map legend's suffix on every Squad type, and the port's `force_limit` detail for a
  map whose Observation fits no Squads at all — used the word CONTEXT.md's Purchase entry tells
  us to avoid. Wording only: no code, no wire format and no rejection code moved. The same sweep
  put the glossary's terms into the comments and docstrings #139's second DDD pass named, and
  three comments now say Objective rather than town.
- **`Roster.reconcile` no longer deletes a Squad with no living members by construction.** It
  removed any fielded Squad a report did not name, and `fn_squadSample` omits a Squad at zero
  living members — which a composition-unassigned shell reaches without anything having gone
  wrong: suspended it has no members at all, and active its only member is the player, whose death
  ADR-0052 makes a thirty-second certainty. Either way the Squad was silently deleted, which is
  exactly the failure a player-led Squad exists to avoid. The exemption is the unassigned Squads
  and nothing wider: a Squad with a composition has AI members and is still deleted when the world
  has genuinely lost it (#310, ADR-0070).
- **A Commander's own Squad now carries `suspended` in its Observation**, so an eligible shell and
  one whose player has gone are distinguishable; the measured Squad ceiling re-measures with it and
  falls from 59 to 52 on Stratis, still far clear of what that map's economy can fund (#310).

- **`just dispatch` no longer prints a `pid=` line**, and the record's `runner_pid` is now
  `launcher_pid`. The value was always the launcher the seam forks rather than the session it
  starts, and the session reparents away from it — so a published pid that does not identify the
  work invites exactly the `ps -p <pid>` check that produced two agents in one worktree. What the
  recipe prints in its place is `stop=just dispatch --stop <id>`, which is the handle that does
  identify the work (#308, #105).

- **`.claude/agents/cti-mechanical.md` and `.claude/agents/cti-implementer-xhigh.md` are gone**, and
  `.claude/agents/cti-planner.md` replaces the second (#324, ADR-0071 ruling 2). `mechanical` is
  retired — it named a cheaper tier rather than a different job — and `planner` absorbs the xhigh
  seat's tier and not its contract: a planner works out what to do, and neither gates nor lands.
  A file for a seat the registry does not carry still declares a pair and is still enumerated at
  session start, so it is removed rather than left, and `just check` now names one that grows back.
  AGENTS.md's Model roles bullets still describe the superseded mapping; that rewrite is #329's.

### Fixed

- **A dispatch record is now stamped with the instant its caller injected, not the one the
  record happened to be written at.** `just dispatch` threads a `now` through every rung that
  decides anything — the breaker's reset times, z.ai's peak band, the id it mints — and then
  `Plan.document()` asked the wall clock again, so the argument decided the routing and the clock
  decided the record. Two consequences. The landing gate was red for the four hours a day z.ai
  sits in its published peak band, for a reason belonging to no change being landed, which
  teaches the opposite of the honest response to a red gate. And at a band boundary the two
  instants could disagree outright: an off-peak refusal filed against a record saying it was
  peak, or the reverse, in the one field a later reader cannot recompute. The instant is now
  carried on the plan and written from there, a record read back recovers it from the record
  rather than from the clock, and the command line takes the same injection the planner already
  did, so a test making a claim about `just dispatch`'s output can be clock-free as its
  neighbours already were. The read is strict: `planned_at` has been written on every record
  since `dispatch.json` first existed, so a record without it is not an older shape but one this
  code did not write. A detached child that cannot read its record back now refuses by name —
  `dispatch_unreadable`, class `infra_unavailable`, the name `just dispatch --stop` already used
  for a record that will not parse — instead of raising where nobody is listening. That covers
  the whole read-back: an instant that will not parse, an `issue` or `argv` of the wrong JSON
  type, a since-retired profile or an unregistered lane, and an absent `dispatch.json` or
  `brief.md`. A record whose assigned worktree has been removed — which `just worktree done`
  makes routine — now refuses `worktree_unreadable` rather than dying on a `cwd` that is not
  there. Either refusal is recorded beside the record where there is a record to record it
  beside, so the ledger sees a dispatch that ended rather than one still running.
- **`just land --dry-run` consults the routing gate instead of planning a push the real landing
  refuses.** The dry run returned before `_rebase_and_gate`, so the one rung that decides whether a
  lane may land this diff at all was never asked, and its silence read as a clearance: on #323 a
  `zai` seat briefed that its `tools/dispatch.py` diff would be refused ran the dry run, met
  `would_run=git push origin HEAD:main`, and reported the brief's premise wrong. The error ran in
  the worst direction — most optimistic exactly where the surface is most gated. The rung needs no
  rebase, only the policy on fetched `origin/main` and the branch's own diff, so it now runs there:
  the plan carries `routing=would_refuse` with the refusal's own evidence and turns the push and
  merge steps into `would_not_run=… reason=<class>`, `routing=would_pass` when it clears, and
  `routing=not_applicable` where the gate does not apply. What a dry run genuinely cannot reach —
  the rebase itself, markers in the rebased tree, `just fast`, the push race, and whether the push
  and the ff-only merge can be run at all — is now named in a `not_checked=` line rather than left
  to be inferred. Because the plan now decides something, its exit code carries the decision: a dry
  run lands nothing whatever it finds, so 0 means no rung it could consult refused and 1 means some
  refusal fired — the routing gate's, but equally the dirty tree and the nothing-to-land that
  `just land` decides before it reaches the plan — with the body naming which. **Everything a dry
  run prints now goes to stdout**, the plan and those earlier refusals alike: `just land` sends a
  landing's refusal to stderr, and a dry run whose exit is now non-zero exactly when it has the most
  to say would otherwise leave a foreign-lane seat with an empty stdout and a bare `recipe … failed`
  banner. A run that lands nothing has no error output to separate, so the split is on `--dry-run`
  rather than on whether the output happens to be a plan (#344).

  Two things had to be right for that to be an improvement rather than the same defect pointing the
  other way. **The diff is merge-base relative.** `git diff A..B` is a symmetric tree comparison
  rather than a commit range, so before a rebase — and `just land` has already fetched by then — it
  named this branch's paths *and* every path the incoming commits touched; since a match on any path
  refuses, a sibling landing an ADR was enough to tell a `zai` seat working on one ungated doc that
  its work would be refused, when the real landing rebases first and lands it. It was wrong in the
  other direction too, and that half was fail-open: a tree comparison lists only paths where the two
  trees *differ*, so a gated path a sibling had already landed patch-identically fell out of the set
  altogether and a foreign landing of it would have been told `would_pass`. Both call sites now
  use `origin/main...HEAD`, so the enforcing rung's answer is right by construction rather than by
  accident of where it is called from — with one narrow exception, stated where the code is: a
  commit of this branch's that the rebase discards as already upstream is in the merge-base set and
  gone from the rebased tree, so a plan can still be pessimistic about a patch a sibling landed
  first. **And the plan mirrors the landing's own control flow,
  including where that flow skips the gate**: with nothing to push — the re-run after
  `merge_blocked_by_sandbox` — the landing never enters the rebase-and-gate rung at all, so the plan
  now names each skipped rung with the landing's own reason instead of refusing the one outstanding
  merge for a check that does not run.

  One home for which lane the gate never judges, and the policy is it. `land.py` read the lane name
  from a constant while `routing_policy.enforcing_match` read it from the policy document, so a
  policy that moved `claude_lane` would have left the landing gate exempting the old name silently —
  fail-open, on the class that keeps the gates themselves on Claude. The policy now **replaces** the
  constant rather than joining it, and the constant is what remains only when the policy could not be
  read at all, which is the order the gate needs: the Claude lane must not be refused for an
  unreadable policy it is the remedy for.

- **The mutation gate's shell tracing no longer kills a test that shells into a `set -u` bash.**
  Its `BASH_ENV` preamble named `${BASH_SOURCE}` in `PS4`, and `BASH_SOURCE` has no element 0 in a
  `bash -c` body — which is exactly `just`'s recipe shell, `["bash", "-euo", "pipefail", "-c"]`. So
  under tracing every `just` recipe aborted with `BASH_SOURCE: unbound variable` before running a
  command, and any test module that drives `just` failed its baseline collect pass. The gate then
  reported `?? could not run` rather than refusing, which is how `tools/generate_seats.py` came to
  be measured by nothing at all while `just fast` looked merely noisy. The default form
  `${BASH_SOURCE:-}` traces identically for every real script and yields an empty source for a
  `bash -c` body, which `read_traces` already drops as not one of this repository's scripts.

- **A just-respawned Commander is no longer told he commands nothing.** Respawn hands the player a
  new unit and the server sees it living before it can read whose it is, so for that window
  `getPlayerUID` answers nothing and the Command Port typed a latched Commander `wrong_side` — "this
  machine commands no side and leads no Squad", which is false of him at one frame and at fifty.
  He now gets a distinct, retryable refusal, **`identity_pending`**: the server has not read who he
  is yet, nothing was judged and nothing was spent, and the answer is to issue the Command again in
  a moment. His latch is untouched — nothing is cached, re-keyed or re-latched — and a caller who
  genuinely commands nothing, whose UID the server *can* read, still earns `wrong_side` exactly as
  before. A dead caller still earns `caller_dead`, and a dead Commander's `view` still arrives
  (#194, ADR-0052 as amended).

- **The Windows client-leg host stall is typed `infra_unavailable`, not `timeout`.** When the six
  `CTI_WINDOWS_CLIENT=1` probes red as a set because the client RPT reached the SimulWeather cloud
  renderer and stopped — never loading move types — that is a host-state stop cleared by restarting
  Windows, not the synchronisation defect the `timeout` class sends a reader to chase. The verdict
  ladder now keys on that content transition (deliberately not a line count, which moves with the
  engine build) and re-types only a probe-recorded `timeout`, so a real client-leg timeout or an
  `assertion_failed` wearing the same probe name keeps its own class. Asserted over two archived
  failing RPTs and two passing ones (#304).

### Added

- **`just brief` composes the issue's handoff into the briefing, byte-for-byte.** #212 found the
  treatment arm of the handoff break-even empty with a mechanical cause: `tools/brief.py` never
  called `handoff_fetch`, so zero cold-start dispatched subagents had read a handoff. The newest
  `Handoff-for:` comment now reaches every brief verbatim from `handoff_fetch.select` — the verdict
  paste rule applied to a second artefact (#219). Three states stay distinguishable: a carried
  handoff is composed verbatim, a cleanly determined absence renders nothing, and a fetch failure is
  a loud `HANDOFF UNAVAILABLE` line, never an absence (modelled on the gate line's `GATE
  UNDETERMINED`). A 2,000-character size check reports oversize without blocking; under the corrected
  currency the write is the metered half (#212 §5). The `just brief` AGENTS.md row is proposed, not
  landed (#309).

- **`docs/research/measuring-the-keep-on-claude-restrictions.md`**, the **zai second lens** on #296
  (ADR-0061 Decision 3, provider diversity). Independently classifies the same fourteen
  `gated_semantic_surfaces` issues and reaches the same four-kind split — semantic authorship,
  independent judging, permission, and reference noise — that the codex lens did, so the split is in
  the issues rather than in either lane's priors. Adds what the codex lane could not: the zai
  executor-capability row measured first-hand (zai runs `just`-recipe gates including `just fast` but
  is refused bare `uv run python`, `python3` and `grep`), a *different* gap from codex's, which
  decides which lane can be a detached-corpus finisher. Keeps `6:gates_themselves` closed, seconds the
  codex v2 policy shape, and refines `run_just_fast` to a per-`(lane, profile)` fact. Nothing in the
  routing policy is landed; every recommendation is quoted for the human's gate (#296).

- **`docs/research/handoff-break-even.md`** — #208's promised falsification, run against the adoption
  record rather than against the transcripts, because the transcripts have nothing to say yet. Five
  days after the convention landed there are five handoff events, three read by a successor and
  **none by the cold-start dispatched subagent the 56% break-even is defined over**. Two things fall
  out that needed no telemetry: one of nine handoff comments honoured the ~1,500-character cap, and
  at the median size actually written the break-even moves from 56% to 91% (at the mean it is
  unreachable); and `just brief` composes no handoff line, which is a sufficient mechanical
  explanation for zero reads. The study also re-denominates the question — #208's input-equivalents
  were inverted by #218/#220/#232 a day later, so the handoff's dominant cost on this plan is
  **writing** it, not reading it. `SubagentStart` injection is weighed and **not** recommended;
  the proposed alternatives (a handoff section in `just brief`, a size check) are stated verbatim
  and not landed (#212).

- **`/interlocutor`, the human interface seat**, now reachable: the two files ADR-0068 designed —
  `.claude/agents/cti-interlocutor.md` and `.claude/skills/interlocutor/SKILL.md`, both opus/xhigh —
  land verbatim as #255 published them. They could not land from the dispatch that wrote them,
  because a dispatched session cannot write under `.claude/` (#294), so the orchestrator landed them
  by hand. `AGENTS.md` has listed the command since `275da82`; until now it named a command that
  missed. Note the harness enumerates `.claude/agents/` once at session start, so both become
  available only in sessions started after this lands (#255, ADR-0068).

- **A dispatched session's refused-command list re-derived: three causes, and the largest is
  ours.** `grep`, `rg`, `find` and `wc` are refused only because RTK rewrites them before the
  permission decision is taken — the harness is asked to approve `rtk grep …`, which nobody typed
  and no `--print` session can answer for — so `\grep` runs where `grep` does not. `awk`,
  `python3 -c` and `uv run python -c` are refused on their own merits, escaped or not. And a
  compound command is decomposed, each part permitted separately, so a read that runs alone can be
  refused inside an `&&` chain. Measured from inside a dispatched session and written up in
  `docs/agents/dispatched-session-commands.md`; nothing was widened (#294, refs #248).

- **A dispatch brief names the surfaces the dispatched session cannot write.** A dispatched session
  is refused every write under `.claude/` — `.claude/hooks/` and any unlisted subdirectory as a
  "sensitive file", `.claude/skills/` and `.claude/agents/` as a permission ask nobody is there to
  answer — above the project allowlist that grants `Write(.claude/skills/**)`, and through the shell
  as well as the tool call. Measured on `claude-native`, reproducing what a Codex dispatch reported,
  after the wall had blocked four human-approved landings. `just brief` now opens a **Reserved
  surfaces** section when the issue names such a path, telling the agent to author the replacement
  text for the orchestrator to transcribe rather than to attempt the edit or route around it. The
  measurement and the routing consequence are in `docs/multi-provider-dispatch.md` (#294).

- **`just land` refuses `corpus_owed` when the diff reaches an in-world surface.** The obligation
  was stated in `AGENTS.md`, quoted in the dispatch's own brief, and still broken: `85dfb1b` landed
  181 changed lines of `src/cti_daemon/transport.py` with no `just regress` run, found three
  landings later. Nothing read the rule at landing time; now the landing does, off the real diff
  against `origin/main` rather than off the issue body.

  A run clears the landing only if it is about the landing: whole corpus (a filtered run and a probe
  left unrun both count as gaps), taken over a tree whose in-world surfaces match the one being
  pushed, on a clean tree, and green. Coverage is a tree comparison rather than commit ancestry,
  because `just land` rebases — an ancestry rule would make the gate unclearable whenever a sibling
  lands first, while a tree comparison still refuses a rebase over somebody else's in-world commit.

  A run that is red or stopped is the separate `corpus_not_pass`, which quotes the pool's own class
  for the failure-class table to answer. It is deliberately not called `corpus_red`: an
  `infra_unavailable` pool is a stop, not a result. `corpus_check_unreadable` is the fail-closed
  third, in `gate_blocked`'s tradition.

  `--corpus <pool>` names the evidence and excuses nothing — every claim it makes is verified
  against the pool's own record, so there is no `--no-corpus` and no way to point it at a
  convenient green run. `just land --dry-run` now says whether the corpus is owed before any of it
  is spent, since a dispatched session cannot run the corpus and needs to know that early (#302).

- **Five profiles the retro ruling names but the registry lacked**: `opus-max`, `fable-medium`,
  `fable-xhigh`, `fable-max` and `codex-sol-max`. Verified against the runners rather than assumed —
  `claude --effort` accepts `low medium high xhigh max`, and a live `codex exec -c
  model_reasoning_effort="max" --model gpt-5.6-sol` answered — because a ruling that names an
  unregistered profile names a route nobody can take (#300).

### Changed

- **The `.claude/` measurement sharpened by a second dispatch.** The Edit tool is refused on an
  existing skill file even though `Edit(.claude/skills/**)` is granted, so the allowlist is
  overridden rather than mis-spelled — though Claude Code's own startup warning shows
  `Write(.claude/skills/**)` and `Write(docs/**)` were never consulted at all, since only
  `Edit(path)` rules are. One hypothesis stays open and is cheap to close: relative patterns may
  resolve against the repository root, which no worktree's own `.claude/` can ever match; the
  one-line absolute-form experiment is written down for the human. Also recorded: a subprocess's
  writes are invisible to the permission check, which is what makes the `just`-recipe route work
  and why such a grant must stay narrow; and `config/dispatch-routing-policy.json` still routes
  these paths to "a Claude seat" when the constraint is dispatched-versus-interactive, with the
  replacement class proposed on the issue rather than landed (#294).

- **The retro allowance is a ruled list, not a single route.** The human enumerated nine approved
  profiles on 2026-08-09 after "or above" proved to be a comparison the code must not make:
  profiles are opaque `(lane, model, effort)` tokens and no cross-provider effort scale exists
  (ADR-0061 decision 5). Only the two `codex` routes need an allowance — `claude-native` already
  permits the `fable` seat — so Decision 2 is suspended for `fable` on `codex-sol-xhigh` and
  `codex-sol-max` and for nothing else. `codex-sol-high` stays barred, which is the case a careless
  "or above" reading would have admitted, and there is a test for exactly that.

  `just dispatch --list` prints both the allowance routes and the full approved list. Nothing tells
  the dispatcher that an issue is a retro, so the list beyond the two foreign routes is honoured by
  whoever dispatches rather than enforced — stated in `AGENTS.md` rather than implied (#300).

- **`codex-sol-max` joins the admission bar's foreign routes.** The bar governs a *profile* on a
  seat, not a lane on a seat, so a newly registered foreign profile is a dispatchable route with no
  admission record until it is listed. `tests/unit/test_admission.py` asserts that equivalence
  against the dispatch registry and is what caught the omission (#300).

- **The in-world surface list has one authority: class 5 of `config/dispatch-routing-policy.json`.**
  It had two homes and was about to have three. `tools/admission.py`'s `IN_WORLD_PREFIXES` — which
  `tools/brief.py`'s gate prediction also reads — is now a read of that row rather than a copy of
  it, and an unreadable policy raises rather than defaulting to an empty list, because an empty list
  reads as "nothing is in-world" and would waive the criterion it exists to protect. The landing
  rung reads the same row out of fetched `origin/main`, so a diff cannot widen the list that judges
  it. `parse_policy` now refuses a document whose class 5 carries no landing prefixes (#302).

### Changed

- **Retros run every five completed issues again, and may be conducted on `codex-sol-xhigh`.**
  Human ruling, 2026-08-09. The cadence returns to the interval that stood before 2026-08-04; the
  ten-close interval ran from the twenty-second retro to the twenty-seventh. The retro seat
  allowance — `fable` on `codex`/`codex-sol-xhigh` — was time-boxed on 2026-08-06 and would have
  lapsed on 2026-08-10; it is now standing, so `tools/dispatch.py` no longer consults a clock for
  it and `just dispatch --list` prints `seat_allowance=standing` rather than a countdown.

  "Or above" is deliberately not a comparison the code makes: profiles are opaque
  `(lane, model, effort)` tokens and no cross-provider effort scale exists (ADR-0061 decision 5), so
  a higher profile joins by the human naming it. Every other fable-on-foreign route, and
  `orchestrator` everywhere, stay barred (#299, superseding #217 and #270).

- **A routing route-exception now carries exactly one of `expires_at` or `standing: true`.** They
  were built time-boxed on purpose; the retro allowance is the first the human has made standing, so
  the schema admits an undated widening **only when the document says so**, never by omission. A
  document with neither, or with both, is refused and the policy fails closed (#299).

### Added

- **ADR-0069**, the Phase-2 decision record for durable snapshots, the thirty-second checkpoint
  bound, and the fail-closed resume barrier (#288). Records the three human rulings of 2026-08-08 on
  #4 — load failure retains a verified last-known-good and never silently starts a fresh Campaign; a
  persistent change marks the Campaign dirty and a durable checkpoint lands within thirty seconds of
  the first one; a resumed Campaign projects through the ordered Effect outbox behind a barrier that
  stays red until the full reconstruction is acknowledged — together with the crash-safe durability
  ordering and the five distinguished load-failure cases (corruption, unsupported schema, failed
  migration, rollback, explicit fresh-Campaign). Closes #288 with no production code; the versioned
  snapshot document it governs already landed in #289 (`e299d06`).

- **`docs/research/removing-backlog-routing-restrictions.md`**, the proposal-only audit of why 18
  of #296's top 30 ready issues cannot currently leave Claude. The 12/18 measurement reproduces,
  but its fourteen-item `gated_semantic_surfaces` pile mixes semantic authorship, gate authorship,
  executor permission and incidental path citations. The report keeps gate and oracle authorship
  closed, proposes a declaration-only/all-matches classifier, separates required executor
  capabilities from keep-on-Claude classes, and pre-registers experiments for reference-only
  routing, narrow `.claude/` promotion, SHA-bound detached corpus runs and lexical-only in-world
  edits. It also records this Codex lane's conflict and preserves its commit-without-gate ceiling.
  Every proposed routing-policy byte is quoted for the human's gate; no policy code or data changes
  here (#296).

- **`Routing-exception: proposal-only`**, a declared exception to the routing policy's
  `gates_themselves` class. That class keeps a foreign lane from **authoring** the mechanism that
  judges it. An issue that may only *propose* — with the human ruling on whatever it recommends,
  and landing nothing in the policy itself — does not author, so it may declare the exception and
  run on a foreign lane.

  Ruled by the human on 2026-08-09 against #296, which asks a foreign lane to study why most of the
  backlog cannot leave Claude. Like the other two exceptions it is **declared per issue and visible
  in the body**; it excepts that one class only, and `just dispatch` still has no flag that skips
  the class rule (#296, #266).

- **A human interlocutor seat at opus/xhigh, reached as `/interlocutor`** (#255, ADR-0068).
  The human's ruling of 2026-08-06 on #242 separated the human interface — rulings intake,
  status, observations, raising issues — from the orchestration standing loop and put it at
  opus/xhigh. It lands as a slash command rather than a dispatch: Claude Code's skill
  frontmatter carries `model` and `effort`, so invoking `/interlocutor` sets the human's own
  session to the seat's tier without spawning an agent that would end and could not then be
  talked to. Reachability from Remote Control on iOS is inherited rather than built — a
  Remote Control session is an ordinary session in a worktree of this repository, so a project
  skill on `main` is the same `/interlocutor` from the phone. One invocation buys one turn;
  for a conversation the human sets `/model opus` and `/effort xhigh`, both of which take an
  argument from mobile. The two `.claude/` files are published on #255 rather than committed
  here: a dispatched session cannot write under `.claude/` (#294), and this landing confirmed
  `.claude/agents/` refuses with the same ordinary permission ask already recorded for
  `.claude/skills/`.

- **`just check-seats`: a declared seat's `(model, effort)` pair is asserted, not trusted**
  (#255, ADR-0068 decision 3). Both places the pair can be declared fail open — a level that
  does not exist, or a key that has drifted below the top level of the frontmatter, leaves the
  seat running at the session's tier with nothing refused and nothing warned. That is the same
  invisible failure that put every implementation agent of 2026-08-04 on fable. Every
  `.claude/agents/` definition must now declare a model and an effort from the ratified sets,
  and a skill must declare neither or both; `inherit` is accepted as a skill's model and refused
  as an agent's, where inheriting is the defect rather than the intent.

- **The versioned whole-Campaign snapshot schema, with its pure serialise/restore boundary**
  (#289; ADR-0003, ADR-0008). A Phase-2 `save`/`load` is a daemon handler and bytes on disk,
  both landing later; what lands now is the document they inherit — one versioned snapshot of the
  strategic state for both sides, with a closed typed field set and forward-only additive
  migrations. `restore(serialise(s)) == s` is held by a hypothesis property test over representative
  both-sides state; a save written by an older version is walked forward through registered
  migrations, absent fields filled with documented safe defaults, and a version with no path to the
  current one is a typed refusal — never a fresh Campaign, because a silent fresh start is the
  corrupted-world outcome durability exists to prevent. The snapshot is not exposed by any daemon
  handler, wire schema, debug path or test helper: it reuses the Observation's and the Order's value
  types but is a distinct document, refused by the other's parser, and a completed-Campaign record
  (ADR-0023) cannot be parsed as one. Contacts and map positions are excluded — both regenerated at
  boot — and player role/Squad is deferred to #25.

- **The durable snapshot store and the checkpoint coordinator: atomic save,
  last-known-good load, and a 30-second checkpoint bound** (#290; ADR-0003, #288).
  The pure snapshot document #289 landed is now bytes on disk. A save writes a
  temp file, fsyncs its bytes, atomically renames it into a staging slot, fsyncs
  the directory, independently revalidates the candidate through the same
  checksum-and-`restore` gate boot uses, and only then rotates it into the trusted
  slot — with the prior trusted generation kept as the fallback, so a failed save
  destroys neither generation. Two generations are kept on purpose: boot reads
  newest-first, falls back to the previous verified snapshot when the newest is
  corrupt, torn or at an unsupported version, preserves the invalid one for
  diagnosis, and refuses — creating nothing — when none validates, so a fresh
  Campaign is the caller's explicit act, never an error fallback. Integrity is a
  SHA-256 over the canonical payload, recomputed on read, so a torn write or a
  byte-rotted field refuses before `restore` sees it. The coordinator decides
  *when*: a persistent mutations marks the Campaign dirty and a checkpoint becomes
  durable within 30 seconds of the **first** unsaved mutation — measured from the
  first, not the last — clean teardown forces a final checkpoint, the snapshot
  copy is taken under the daemon's narrow request lock with encoding and disk I/O
  off it, and concurrent save requests coalesce on a generation counter. Refusals
  are typed (`empty`, `corrupt`, `unsupported_version`, `malformed`) and observable
  through the outcome records and telemetry without the snapshot's contents
  leaving the file. No daemon handler exposes save/load yet — that is the next
  layer; what lands is the store, the coordinator, and the wiring that runs a
  checkpoint on clean teardown.

- **Ordered reconstruction of a resumed Campaign behind a fail-closed barrier**
  (#292; ADR-0008, ADR-0018, ADR-0023). A restored snapshot projects into a factory-fresh world
  through the same ordered Effect outbox every other world change rides: `resume.reconstruct` emits
  the Effects in domain order — the scoreboard (Objective ownership), then the Squads spawned onto
  it, then the standing Orders issued to those Squads — never dictionary iteration, because a
  snapshot is a set of facts whose application order changes the result. `resume.Barrier` holds that
  world closed until every reconstruction Effect is acknowledged, opening only on a complete,
  unfailed acknowledgement and staying shut, with a typed reason, on a rejected or oversized Effect.
  Projection is atomic: a snapshot that cannot be projected whole is refused with nothing emitted,
  tested at several points in the order. A full reconstruction drains across bounded polls at both
  the planner's eight-Squads-a-side cap and the seventy-one-Squads-a-side wire ceiling without loss.
  Three things ADR-0008 regenerates are absent by refusal rather than gap: a destroyed HQ (a
  completed Campaign, archived not resumed), a Contested Objective (whose prior owner the snapshot
  does not carry — a question named for the save side), and all tactical state. Funds, the clock and
  loadouts are daemon state projected by no Effect here; player role/Squad stays deferred to #25.
  This is the mechanism only: #288 fixes the barrier's exact refusal set, and #291 wires it into the
  live daemon and its epoch. No in-world surface is touched, so the regression corpus is owed and
  unrun.

- **Phase 2 save/load control: an acknowledgement-only lane on its own connection**
  (#291; ADR-0005, ADR-0018, ADR-0022, ADR-0034, #289's schema, #290's store). Save and load are
  daemon handlers, but behind their own dispatch (`CONTROL_HANDLERS`) rather than the transport verb
  table (`HANDLERS`) — so the snapshot #289 closed stays off every wire path: no view, observe, debug,
  telemetry or oracle reply returns it, and the command port has no `save`/`load` verb. What a save or
  load returns is acknowledgement alone — accepted, the schema version, a checksum, the selected
  generation, a rollback warning, and the loadouts a load dropped — never the document. The lane runs
  on a second listener of its own so the slow durability work (serialise, store read/write) cannot
  head-of-line block a synchronous Command Judgement: the command lock is held only long enough to
  photograph or apply a consistent Campaign, and released before the bytes move. A load validates and
  migrates against #289 before it touches live state, and a failed load leaves the running Campaign
  untouched with one of three typed refusals — `no_valid_generation`, `unsupported_schema`, `corrupt`
  — each raised before the apply, so a refused save is distinguishable from a lost one. A successful
  load mints a new epoch, so a world attached to one daemon Campaign cannot resume against the replaced
  state silently; the reply carries it. Replay is idempotent (ADR-0034) on a window of its own, and a
  `busy` refusal — the lock held past its bound — is not remembered, so a resend is carried out rather
  than answered from the record. The durability layer is the `Store` protocol seam (a `FakeStore` until
  #290 lands its atomic store), so the control lane is exercised against a stand-in and #290 supplies
  the concrete implementation. No in-world corpus: save/load are daemon-internal, the world speaks
  neither, and the issue's criterion 9 defers the corpus to the world-facing ticket.

### Fixed

- **`just dispatch-follow` takes several ids and wakes on the first of them, not the last** (#295).
  The seat had been following a refill cohort by looping one follower per id inside a single
  background task, which is a barrier: the wake fires when the *slowest* member finishes, so slots
  freed by the faster ones sit empty with nobody awake to refill them. Measured over four days of
  real dispatches, that barrier delayed the seat's wake by 292 agent-minutes, once by 115 minutes on
  one cohort — and over the 191-minute block of 2026-08-09, 596 of the 669 lost agent-minutes (89%)
  fell while the seat was asleep behind it, against at most 5 attributable to writing briefs. One
  invocation now follows the whole cohort, prints `pending=` for the members still running, and
  keeps every existing single-id ending unchanged.

- **The gated-path guard and the format/lint hooks now read a Codex edit.** Claude Code's editing
  tools name their target in `file_path`; Codex's carries a V4A patch envelope whose written paths
  are inside the patch text, so the guard could not see them and failed closed — correctly, but it
  meant a Codex session was refused on edits it should have been allowed, and the formatter never
  fired at all. `tools/edit_payload.py` reads both shapes, returning `None` for a call it cannot
  read and an empty tuple only for one that writes nothing; the guard's fail-closed direction
  depends on that distinction. Verified in vivo in both directions: a spec write through a patch
  envelope is denied, an ordinary path through the same envelope passes, and an unreadable envelope
  still fails closed (#273).

### Changed

- **`CLAUDE.md` points at the orchestration seat's operating rules** (#242 ruling 6, human decision
  2026-08-06; sentence proposed verbatim by #267). The ruling put the pointer in the Agent-skills
  section in the same commit as `docs/agents/orchestration.md`; the document landed at `d53eebe`
  and the pointer, being a gated surface, was left as a proposal. It lands here under the ruling
  that approved it. `docs/orchestration-design.md` gains a status block: which of its proposals
  were ruled, where each now lives, and the two that remain — #255's interlocutor seat and #295's
  `just occupancy` row. Closes #242.

- **Cache reads measured at ≤ 0.0095 pp₅ₕ/Mtok on this plan** (#237, ratified 2026-08-06): a
  multi-turn read arm moved the five-hour meter +1.0 point net of wall-clock-matched idle controls
  over 105.08 Mtok of reads — ≥ 3,477× lighter than output and indistinguishable from zero at the
  instrument's integer resolution. `docs/research/token-efficiency-plan-currency.md`'s cache-read row
  moves from `unresolved`/`[unmeasured]` to **≤ 0.0095 pp₅ₕ/Mtok [measured/bounded]**; the §3 band
  collapses 0–62% → 0–~10%; and all four §4.3 suspended items resolve as non-spend (context size in
  general, and #216, are worth ≤ ~4% of the meter, not "up to 31%"). The ledger's
  `cap_fraction.excludes` is discharged — `excludes` becomes empty — and the calibration advances to
  `claude/237-2026-08-06`, carrying #218's output weight plus #237's cache-read bound; a pre-#237 row
  keeps `claude/218-2026-08-05` and its exclusion so the two regimes stay distinguishable. Output is
  essentially the whole of what this plan charges; reads join writes in the near-free class.

- **`AGENTS.md`'s `just dispatch` row now states the `zai` off-peak refusal, and the pointer
  paragraph now names `docs/review-dispatch.md`** (#248). Two verbatim prose amendments ruled
  2026-08-06: the `zai` lane dispatches only outside z.ai's published peak band, refusing with
  no failure class inside it since nothing was found about a provider or the code under test;
  and the three-document pointer paragraph now also credits `docs/review-dispatch.md` with the
  review seat's dispatch shape, claims-cite-code contract, and routing. The failure-class table
  is unchanged by design.

- **`AGENTS.md` is the source; `CLAUDE.md` is a committed symlink to it** (`ln -s AGENTS.md
  CLAUDE.md`, mode `120000` in the index). Human ruling on #221, 2026-08-05, Decision 2. Hook
  configuration stays hand-written per target and no compiler is introduced. The symlink was chosen
  over an `@AGENTS.md` import on a documented gap rather than a preference: a project-root
  `CLAUDE.md` is re-read from disk after `/compact`, and nothing documents whether that re-read
  re-expands imports — the symlink has no such question (#264).

### Added

- **`tools/occupancy.py`, the seat's occupancy instrument** (#295). `just queue state` answers how
  many dispatches are in flight *now*, which cannot show a sawtooth. This reads the dispatch records
  and reports one window in agent-minutes — capacity under the ruled WIP limit, used, lost, and the
  per-minute series — so an intervention aimed at occupancy has a before and an after over real
  dispatches rather than a simulation. It reads and never writes, carries no verdict (it cannot see
  the queue, so a short block may simply have been short of eligible work), and names the
  still-running dispatches it counted rather than leaving them to be inferred. Recipe proposed for
  the CLAUDE.md command table; the row follows through the sign-off gate.

- **The mutation gate reaches shell and Rust, and SQF's non-goal is written down** (#246,
  ADR-0067). `just mutation` gained two arms. The **shell arm** (`tools/mutation_shell.py`)
  reads which line of which `spike/*.sh` each test executed out of a bash xtrace — `$BASH_ENV`
  plus `BASH_XTRACEFD`, measured free at 14.75 s against 14.88 s — plants a bounded sample
  there, and judges it against `SHELL_FLOOR = 20%`, set from a corpus sweep (100%, 80% ×4,
  30% ×2) against a 0% weak fixture. Mutants go into a hardlinked stage and never into
  `spike/` itself, because a live Arma tier reads those scripts. The **Rust rung**
  (`tools/mutation_rust.py`) runs `cargo-mutants` over the shim when and only when
  `extension/` changes — 52.7 s at four jobs, on 1.4% of landings — and reds on any viable
  survivor. The escape list is renamed `NO_MUTABLE_SUBJECT` and falls from eleven rows to
  four, two of which are now cost exemptions quoting their measured seconds. There is no SQF
  arm and the reason is recorded beside the list: a per-mutant verdict is a fresh Arma world.
  Measurements in `docs/research/mutation-shell-arm.md`.

- **ADR-0066**, the multi-provider dispatch initiative's second decision record (#263, human ruling on
  #221 of 2026-08-05T21:14Z, Decision 1). Eight rulings that already govern landed code — substrate,
  dispatch granularity, the lane breaker, telemetry, durability, secrets, sequencing and quota
  feedback — existed only as comments on #221; each is now recorded with the date it was ruled and
  the instance that landed it. Portability joins them as the one ruling that changed shape:
  `AGENTS.md` as the source with `CLAUDE.md` a symlink, not an import. Two post-ratification
  corrections to ADR-0061, which is immutable, get their own entries — substrate was settled by
  Anthropic's Consumer Terms rather than by a spike, and the breaker halved because Codex publishes
  quota first-party. The ADR also carries the full reasoning behind two of ADR-0061's 2026-08-06
  amendments, so no fact argues itself twice. `Reviewed-by-human: pending`: a new ADR is a sign-off
  gate and only the human flips that field.

- **`tools/edit_payload.py`**, one reader for the paths a file-editing tool call writes, on either
  harness (#273). Claude Code's `Edit`/`Write` name a `file_path`; Codex's editing tool hands the
  hook a V4A patch envelope instead, and three hooks that read `file_path` directly break on it —
  the PostToolUse formatter and linter silently no-op, and `protect-gated-paths.py` fails closed and
  denies the edit outright. The reader returns the paths, or `None` for a call it cannot read, and
  never an empty tuple for one it could not tell about.

  **The issue's title records a matcher defect and this is not one.** Dispatch
  `d-20260807-204151-09d57f` was refused by `protect-gated-paths.py`'s fail-closed branch on a Codex
  edit, and a hook cannot refuse a call it was never selected for — so the `Edit|Write` matcher
  fires on a Codex edit, and the PostToolUse pair wired on the same matcher fired too, read `""` for
  the path and formatted nothing. One root, two symptoms; widening the matcher fixes neither. The
  reader keys on the patch format's own `*** Begin Patch` sentinel rather than on a tool name,
  because no live Codex edit payload has been captured on this box and a guessed `tool_name` would
  stack a second assumption on the first.

  The three hooks that must consume it are **not** in this change: `.claude/hooks/**` is refused to
  a dispatched session as a sensitive file, which is #273's own second wall. The patches are
  published on the issue for the orchestration seat, and `docs/research/codex-lane-live-findings.md`
  §4.1 carries the diagnosis with each claim's evidence class and what is still unmeasured.

- **The mutation smoke gate keeps a per-module ratchet** (`tools/mutation-baseline.json`, #244).
  Each test module's measured kill rate is recorded against its subject, and a module reds when it
  falls below its *own* recorded rate rather than below the global floor alone — turning a floor set
  by the weakest module into a direction every strengthening raises. The baseline ships empty, so no
  floor moves on landing; `just mutation --record` populates a module's rate, raises it on stronger
  tests, and never lowers one silently (lowering is a hand-edit, diff-visible, like
  `NO_PYTHON_SUBJECT`). A rate is bound to the subject's bytes, so a legitimate refactor releases the
  ratchet to the global floor automatically rather than blocking. One kill of slack tolerates a
  neutral test rename; two lost kills is the weakening the ratchet names.

- **`docs/research/dissolving-the-claude-class-list.md`**, the analysis commissioned on #262 against the
  keep-on-Claude class list ruled on #258. Three findings. **The gate-versus-competence split is
  incomplete**: there is a third kind of obstacle — *permission*, what a dispatched session may execute
  and write — which is neither a gate question nor a competence one, and which this week blocked #281,
  #264 and five pieces of human-approved work under `.claude/` (#294). **Class 7 dissolves**: the plan
  meter's primary feed is `tools/breaker.py`'s call to a hard-coded `api.anthropic.com/api/oauth/usage`
  with an on-disk OAuth token, so it never consults `ANTHROPIC_BASE_URL` and a base-URL redirect cannot
  reach it; the status-line half is only the fallback. What remains of class 7 is a policy question
  about where that credential is used, not a technical barrier. **The programme is cheap in the
  currency that binds**: all nine experiments together cost about 2.2 seven-day points of Claude plan
  cap, roughly 2% of one week, so quota is not what is sequencing this work — permission and wall-clock
  are. The file carries a filing-ready design for E3, E4, E5, E7, E8 and E9, the decision-replay corpus
  with its packet cut and a runnable contamination check, and a per-experiment cost table. Nothing lands
  on a gated surface; the routing-policy change is a proposal for the human.

- **`docs/research/mutation-engine-comparison.md`**, the build-on-top comparison the human asked for
  before ratifying ADR-0064 (#281). Cosmic Ray 8.4.6 and mutmut 3.6.0 were each given the smallest
  adapter that attempts `tools/mutation_smoke.py`'s behaviour, and measured against it on the same
  modules. **No arm qualifies** against the issue's decision rule, so the decision returns to the
  human and this is not automatic ratification. Cosmic Ray needs no private API and no fork, but
  scores a sound module 17% where the gate scores it 67% — a false red at the current floor — and
  its adapter is *larger* than the tool it would replace (1,029 lines against 1,116). mutmut is the
  fastest arm and never touches the real tree, but its operator set is a module-level list with no
  configuration surface at all, which is the issue's stop condition. Runtime disqualifies neither.
  The throwaway prototype is attached to #281 rather than landed.

- **`Routing-exception: no-gated-landing`**, a second declared exception to the routing policy's
  gated-semantic class. An issue whose body merely *mentions* a gated path — an ADR under
  discussion, a settings file being reasoned about — while landing nothing there may declare it and
  dispatch to a foreign lane. Like the existing transcription exception it is **per-issue and
  visible in the body**; `just dispatch` still has no flag that skips the class rule, and the
  exception excepts that one class only, so an in-world landing still refuses with it declared.

  Filed against a live false positive: #281 is a throwaway prototype that lands nothing on `main`,
  was classified `1:gated_semantic_surfaces` on its ADR-ratification language, and was thereby
  routed to the one lane whose command vocabulary cannot run it — undispatchable in both directions
  at once (#266, #281, human instruction 2026-08-09).

- **`just discard <path> <ruling>` is allowlisted for dispatched sessions**, in place of the broad
  `git checkout --` grant that was proposed and declined (human ruling, 2026-08-08, on #248). The
  command restores one named tracked file's unstaged working-tree change from the index and refuses
  everything else by name — globs, directories, untracked, conflicted or staged paths, a path
  outside the worktree it was run in, and any run where another dirty path exists, which is what
  stops it decaying into a habitual reset. It requires a ruling reference and prints it, so the
  record says what was discarded and on whose authority (#287).

- **`just discard` — a guarded single-file discard, in place of a `git checkout` grant.**
  Two dispatches on 2026-08-08 each ended their turn asking permission to run
  `git checkout -- <path>` on residue an orchestrator-run probe had left, and both produced
  nothing while `main` stayed regressed: there was no allowlisted way for a dispatched session
  to discard a working-tree change at all. The blanket grant was declined — discarding a
  working-tree change is exactly what the standing foreign-files rule forbids (#105) — so the
  command is constrained until it can do nothing but the case it was authorised for. It takes
  exactly one normalised repository-relative tracked file plus a required ruling reference
  naming the decision that authorises the discard, prints both in its result, and restores only
  that file's unstaged working-tree change from the index. It refuses globs, directories,
  untracked files, conflicted files, staged changes, paths outside the worktree it was run in
  (including a nested worktree belonging to another agent) — and any run where another dirty
  path exists, which is the rung that makes it useless as a general cleaner and so keeps it from
  decaying into a habitual `git reset`. Nothing is discarded on any refusal path, and every
  refusal is proven with the working tree asserted unchanged afterwards. A file belongs to the
  **most specific** registered worktree containing it, which is what makes the command usable at
  all: this project's agent worktrees live at `<main>/.claude/worktrees/<name>`, so every file in
  every one of them is contained by the main checkout too, and reading ownership as "any
  containing registration" refused the whole permitted case everywhere the command exists to be
  used. A genuine sibling tree is deeper than the worktree in hand rather than an ancestor of it,
  so it still refuses. The orchestrator-clears-residue path remains the fallback whenever the
  guard refuses (#287).

- **`just wip-trial` pre-registers and instruments the stepwise WIP experiment.** It fixes the
  3→5→7→10 treatment ladder, SHA-derived balanced block order, 15% material-throughput bar,
  occupancy fidelity, quality/rework guardrails, 72-hour stop and seven-day maturation before
  observations arrive. Immutable manifests and hash-chained sourced events feed reproducible JSON
  and paste-ready Markdown verdicts. The command cannot dispatch or edit queue policy: it reports
  the lowest passing limit and the exact ruling command, leaving adoption to the human (#284).

- **Foreign dispatches now obey a repository-owned keep-on-Claude class policy.**
  `just dispatch` reads the seven-row policy from the main checkout for every dispatch and
  refuses a declared keep-class by name, with its remedy and no failure class. There is no
  override. The issue-body read is explicitly advisory because planned surfaces can be
  understated; `just land` is the enforcing half and refuses a foreign lane when the real
  rebased diff touches a class path, failing closed when the trusted policy or diff cannot be
  read. The routing policy stays separate from queue policy because class eligibility and
  freeze/WIP/package state carry different human rulings and amendment lifecycles (#266).

- **A dispatched session is refused when it tries to background work.** `CTI_DISPATCH_ID` is in
  every dispatched child's environment, and a new `PreToolUse` hook uses it to tell a dispatched
  top-level session from the orchestrator: inside one, a Bash call carrying `run_in_background` is
  denied with the instruction to run the work in the foreground. It refuses **backgrounding, never
  waiting** — holding a long foreground wait is exactly what a sanctioned dispatched session is for
  (#218), and the ordinary subagent long-wait denial is deliberately not applied. The orchestrator,
  which has no marker, keeps backgrounding freely; that is what drives the dispatch completion edge.

  Two dispatches were lost to this shape on 2026-08-08: one ended "Awaiting completion notification
  to continue" with its work uncommitted, and a detached `claude -p` has no second turn in which to
  receive that notification. On Codex the guard is inert rather than parity-claimed — that runner's
  Bash payload carries no `run_in_background` field and `codex exec` is single-shot by construction
  — and the inert direction is asserted in test rather than in prose (#279).

- **`docs/agents/orchestration.md` is the orchestrator seat's runbook.** It records
  the seat's operating rules as they now stand — opus/high with fable dispatched for
  the named acts, the duty cycle and its arithmetic, the top-of-turn read sequence,
  what the seat holds versus dispatches, the claim-only review function, when each
  tool is reached for, and what the seat must not do. Every rule carries a landed
  instance or a cited ruling; the document cites `docs/orchestration-design.md`
  rather than restating it. Ruled into existence on #217, sequenced to now because
  #250–#253 landed the first applied instances the convention requires (#267).

- **`just dispatch-follow <id>` restores a within-session completion edge for detached
  dispatches.** The follower remains attached to the tool harness until the dispatch's recorded
  runner exits, then prints the dispatch id and authoritative result path from `dispatch.json`.
  A runner that disappears without writing its result is reported as
  `finding=runner_disappeared`, never as a completion or an inferred failure class. The wait has
  no timeout or polling interval, and leaves stall classification with `just watch` (#280).

- **Every dispatch brief now states the single-shot contract.** A detached session has no
  second turn for a background completion or a question — two dispatches on 2026-08-08 ended
  that way, one leaving its gate uncommitted (`just land` refused `dirty_tree`), one asking
  whether to run `git checkout --` with no caller listening and main broken another cycle.
  `just brief`'s composed invariant half and `just dispatch`'s default brief both carry the
  verbatim instruction, from one constant (`dispatch.SINGLE_SHOT_CONTRACT`) so the two briefs
  cannot drift (#279).

- **`just watch-report` now calls out underfilled WIP before the orchestrator starts a landing.**
  The one-line verdict reads the queue's ruled limit, derived in-flight list, freeze and package
  policy, and live eligible candidates, then reports occupancy, room, eligible count, the next
  candidate, and `action=refill-before-landing`. It stays silent when capacity is full or no
  candidate survives, fails closed when GitHub cannot be read, and only reports and selects — it
  never dispatches or rewrites the human's limit (#278).

- **`just worktree` gains an explicit preservation path: `archive` and `restore`.** A worktree
  whose work is parked but cannot land was removable only by overriding `done`'s refusal,
  because `done` treats "not on `origin/main`" as "not durable". `archive <name> --ref
  <remote-ref>` now verifies the tree is clean and the named remote ref resolves to its exact
  HEAD — `git ls-remote`, the check the #170 incident used — then removes the worktree; it
  never creates or moves the ref. `restore <name> --ref <remote-ref>` recreates a detached
  worktree from that exact ref and runs the same exclusivity pre-flight as `add`, so recovery
  stays in the protocol. `done` is unchanged: an archive is not a landing, and durability stays
  explicit through the archive call (#272).

- **`just probe-contract` prints the probe↔harness contract by reading it off the runner.** What a
  probe owes the harness — the header keys, the completion line, the window — was written down nowhere
  outside ~1,000 lines of bash, and a contract misread out of bash is a probe that tests the wrong
  thing (#150/#191 timed out in its own scaffold while the decision under test had already fired). The
  command derives the contract from `spike/regress.sh` and `spike/run.sh` rather than restating a
  second copy beside them, so it cannot drift: header keys come from the `header_of` call sites, the
  required set from the validation block, the completion sentinel and the window binding from the
  runner's own assignments, and the emitted classes from its `fail`/`failure_class=` sites. A drift
  test plants a new header key in `regress.sh` and asserts it surfaces in the output, which a
  hand-maintained restatement could not. Verdict semantics are pointed at CLAUDE.md's failure-class
  table and restated nowhere here (#209, #215; ADR-0049 for the Python home under pytest).

- **`just dispatch` can now run a fable act on `claude-native`.** A `fable-high` profile joins the
  registry, giving the fable seat the `(model, effort)` token #242 ruling 1 kept it for — retros;
  ADR, `CONTEXT.md` and schema semantics; retro evidence banking; the #181-shaped diagnosis call.
  The ruling said these acts are *dispatched* rather than resident, but the seat drop that moved the
  orchestration seat to opus/high removed the subagent inheritance that had been silently supplying
  fable, and the "dispatched" it relied on had no profile to dispatch through. The seat was always
  expressible (`SEATS` bars it on a foreign lane only); only the profile was missing, and `build_argv`
  passes `model` straight through, so the runner's own `--model fable` alias needed no new plumbing.
  A unit test now fails if the fable seat is ever left without a claude-native profile that runs the
  fable model (#269).

- **`just verdict --post <issue>` posts a pool's rendered record to an issue, so no reader retypes a
  SHA or an evidence path.** The bytes posted are the bytes `just verdict` renders — one rendering,
  not two — and the refusals are named and atomic: no pool, an unreadable pool, a missing or
  non-existent issue, a `gh` failure, none of which may leave a partial comment behind. `--post`
  requires the pool directory explicitly rather than defaulting to the newest pool on the box, since
  a plausible record posted against the wrong run is worse than no record.

  #219's A/B scored 40 verdict readings across five arms: no arm at any price misread a class,
  treated `infra_unavailable` as a result, or would have landed on a red — and all four failures
  were the same act of retyping the tool's output, twice producing an evidence path that resolves to
  nothing. A reader that never types the path cannot corrupt it (#235).

- **A dispatched session may now run the gate and make its own commit.** `.claude/settings.json`'s
  allowlist gains eight entries — `just check`, `just unit`, `just fast`, `git add`, `git commit`,
  and read-only `git status`, `git diff` and `git log` — on the human's ruling of 2026-08-06 on
  #221. The permission mode is unchanged (`acceptEdits`), and the push path is unchanged: `just
  land` was already allowlisted and remains the only way anything reaches `origin/main`. Bare `git
  push` and `git commit --no-verify` are deliberately absent.

  The first live foreign dispatch could do the work but not commit it or gate it, so every foreign
  dispatch needed a Claude-side finisher — spending exactly the tokens the foreign lane exists to
  save. Widening is safe because the hooks are not permissions: `PreToolUse` fires before any
  permission-mode check, in every permission mode, so what the allowlist grants the hooks can still
  deny, and the hook-parity suite proves the denials on Codex payloads unchanged.

- **A dispatched Codex session's sandbox reaches the git metadata and the network its commit and
  landing need.** Measured before changed, as the ruling asked: dispatch
  `d-20260806-163129-479a57` ran under plain `--sandbox workspace-write` and got as far as `git
  add`, which died on `Unable to create '<main checkout>/.git/worktrees/issue-259-codex/index.lock':
  Read-only file system`. This project dispatches into linked worktrees, so a session's git metadata
  lives above the one directory `workspace-write` makes writable, and every commit was out of reach.

  `codex exec` now carries two `-c` overrides on `acceptEdits` only: three `writable_roots` and
  `network_access`. The roots are the main checkout (`just land`'s ff-only merge writes it), **both**
  git directories as git itself names them, and `~/.cache/uv`. The git pair is the finding worth
  keeping: Codex refuses a write under a `.git` directory unless that exact directory is a writable
  root, and naming an ancestor does not lift the refusal for a nested one. Granting the repository
  left `.git/p2` refused; granting `.git` left the linked worktree's own
  `.git/worktrees/<name>/` refused — which is where its index, `HEAD` and `FETCH_HEAD` live, so a
  session had `git log` and nothing else. Granting both made `git add`, `git commit` and `just land`
  work. Without `~/.cache/uv` every gate recipe died at `check-generated` before a test ran. `~/.cargo` was measured *not* necessary and is not granted. Read-only seats are
  untouched, and `--dangerously-bypass-approvals-and-sandbox` was put to the human, declined, and
  remains unused.

  This is not parity with the `zai` lane and is not described as one: that lane's grant is a list of
  named commands, this one a filesystem and network policy every command inherits. Network access in
  particular is strictly more than the `zai` half has, where only `just land` and `gh` reach the
  network at all. `docs/multi-provider-dispatch.md` now states the two lanes' capabilities separately,
  with what was measured on each — including that the Codex lane can commit **or** gate and not yet
  both: granting the per-worktree git directory as a writable root is exactly what stops libgit2, and
  so `cog check`, opening it. The `zai` lane reaches a landing today; the Codex lane's remaining step
  is carried as its own issue.

- **`just admission audit --issue N` computes the close audit the bar today asks an agent to
  assert.** `just admission record` demands a choice on every Part A criterion and cross-checks two
  of them against git in the refusing direction only; everything else is asserted by whoever runs
  it, which for a Claude-lane issue means the orchestrator reading a close against a landing by
  hand. Most of that is now computed: six checks over the issue's closing comment, printed as
  evidence for a `record` invocation that stays a deliberate act.

  The checks are whether the close names a commit on `origin/main`; whether that commit falls inside
  its dispatch's window; whether the landing touched an in-world surface and so owes a pool verdict;
  whether every evidence path quoted exists and its `pool.json` reads green; whether a gate block is
  quoted at all; and the changelog. The window tests are `tools/ledger.py`'s — descends from the
  dispatch's base, postdates the dispatch's own start — and are called rather than copied, with a
  unit test that reds if a second implementation appears. `pool.json`'s green reading is
  `tools/pool_merge.py`'s for the same reason.

  Two answers are deliberately weak, and both are refusals to overclaim. A quoted gate block is
  reported `quoted` and never as proof the gate ran green: the paste is the evidence and no tool can
  re-run history. The changelog check reports `undecidable` and has no input that makes it report
  `ok`, because whether a commit had user-visible effect is not decidable from its diff — a check
  that could not run is not a check that passed.

  The audit records nothing and exits zero whatever it found, since a verdict here is a finding to
  read rather than a gate. `record --from-audit` fills the two criteria the audit computes and
  leaves every other one a required choice with no default, so the bar's no-default discipline
  survives the automation. A `--close-file` seam reads a close from disk instead of from `gh`.

  Which comment is "the close" is decided by distance from GitHub's own close event rather than by
  reading the prose, and symmetrically: this repo writes the close on both sides of it — #92's
  comment landed on the event to the second, #118's 2m47s after — so a rule taking only the earlier
  side refused #118 outright, and one taking only the later side would have taken #92's
  cross-provider review, posted the next day. The offset is printed beside the comment id, because
  a thread whose nearest comment is nowhere near its close is a case a reader must see rather than
  one the tool should guess at.

- **`just admission trial` records the orchestration seat's pre-registered trial (#242 ruling 1, on
  #260).** The opus/high orchestration loop was adopted on the gate argument, not the budget one, and
  adopted as a pre-registered trial in #219's and #224's shape — a bar settled in advance so the
  numbers cannot move once they are in. Ten consecutive dispatch cycles, failing on any one of five
  criteria the human pre-registered; the first miss ends it, with no allowance.

  It rides the admission machinery's shape but is **not the route bar and not a dispatch gate**.
  `just dispatch` does not consult it and does not refuse on it. A failed trial records and reports
  but never auto-reverts the seat and carries no failure class — it is a finding for the human, who
  rules on whether the seat reverts, so the verdict names no provider, lane or code under test.

  The clock starts at an explicit `trial-start --date YYYY-MM-DD` act, not at the tool's existence,
  so `not_started` is a state distinct from `0/10`. Three of the five criteria are computed against
  artefacts that exist — a freeze the queue policy recorded, a landing inside its dispatch's window,
  a gated sign-off surface edited without approval or an ADR-0013 record — and two are the human's
  alone, never filled from an audit. The bar is immutable once the first assessment lands: amending
  the criteria means minting a new bar id, clearing the trial and starting fresh.

  `just watch-report` carries the trial's one line when it has failed and is silent while it is
  clean, the same tradition as the lane breakers. `trial-audit` computes the mechanical three a
  recorder reads before asserting the two hand ones; `trial-record --from-audit` fills those three
  where the artefacts decide and leaves the rest a required choice with no default.

- The ledger's landing answer now carries every commit in a dispatch's window alongside the tip it
  already named, so a caller asking whether one quoted SHA belongs to a dispatch can be answered
  without re-deriving the window. The ledger's own row is unchanged.

### Changed

- **Retro 26's amendments are on the process surfaces the human approved them for.** CLAUDE.md's
  Model roles no longer call fable the orchestration seat and say that the opus/high tier carries
  the orchestration standing loop for #242's ten-cycle trial; the command table gains rows for `just
  queue`, `just brief` and `just recover`, and its `just admission` row is replaced by one covering
  the `audit` and `trial-*` surfaces rather than joined by a second home. The process banner reads
  twenty-six retros.

  The temporary route is stated in three places and expires by clock rather than by revocation:
  until `2026-08-10T14:00Z`, retros may run as the `fable` seat on the `codex` lane at profile
  `codex-sol-xhigh`. CLAUDE.md's foreign-lane paragraph, the `just dispatch` row's *Run when* column
  and ADR-0061 Decision 2 all name that instant, and `tools/dispatch.py` is what reapplies the
  standing bar at it.

  Four validated markers move on the exemplars retro 26 named: failure classes ×10 → ×11 on
  #260/#270's two typed `quota_exhausted` reroutes, elimination-context ×12 → ×13 on #254's
  re-derived diagnosis, and the recovery runbook ×17 → ×18 on the same two lane-changing resumption
  briefings. Both CLAUDE.md lists stay at five exemplars, with the dropped #83 and #147 entries
  archived verbatim in `docs/process-log.md` per #201/ADR-0060. The retro skill's approved ×25 → ×26
  is not in this landing and remains outstanding; every other count is unchanged.

- **Retro 27's amendments are on the process surfaces the human approved them for.** The process
  banner reads twenty-seven retros. The `just verdict` row now documents `--post <issue>`, posting
  a finished pool's rendered bytes straight to the issue (#235). The `just worktree` row gains
  `archive` and `restore`, the named refusals `invalid_ref`, `not_on_remote` and `ref_mismatch`, and
  the explicit rule that an archive is not a landing (#272). A new `just probe-contract` row sits
  beside the regression/probe rows (#215). The working-style bullet sanctioning a dispatched session
  as the irreducible-wait fallback gains its single-shot sentence: no second turn for a background
  completion or a question, decide routine ambiguities and record the reasoning, and state exactly
  what remains when a choice is genuinely the human's (#279).

  Elimination-context moves ×13 → ×14 on one combined exemplar — #90's caller set bounded before a
  rename batch, #73's filed daemon read-timeout found already fixed, and #215's contract found
  scattered rather than absent — the three applications earning one marker move, not three; #275
  remains corroboration only. #189 is pruned from the inline newest-five list, its verbatim archive
  already standing in `docs/process-log.md`. Failure classes stays ×11, recovery stays ×18,
  probe-window stays ×8, convention-lands stays ×5, ADR-claiming stays ×7. The retro skill's approved
  ×26 → ×27 is not in this landing and remains outstanding.

- **Reverted: routing the Codex per-worktree git directory through its parent regressed the
  lane from commit-only to neither.** The prior entry's candidate fix was live-tested at
  `d-20260808-075346-f27564` and refuted: `git add` itself was refused, `index.lock`
  read-only, under the parent-grant root set — worse than the four-root set it replaced,
  which at least commits. `tools/dispatch.py`'s `_codex_writable_roots` is restored to
  naming both git directories directly, the set proven to commit and not to gate
  (`d-20260806-172045-9a0a0e`: commit exit 0, `cog check` red). The "next candidate" this
  entry first held — granting `<main>/.git/worktrees` as an ancestor grant — is the same
  path `d12a27f` already named (`--absolute-git-dir` for a linked worktree is
  `<main>/.git/worktrees/<name>`, whose `.parent` is `<main>/.git/worktrees`), so it is the
  set `f27564` refuted, not an untested one. A read-only strace over `cog check` in the
  sandbox (`d-20260807-222221-1a2c7e`) found why: naming the per-worktree directory makes
  the sandbox inject an empty `<dir>/.git` mount point that libgit2 trips over, while naming
  its ancestor leaves `index.lock` read-only. The commit needs the directory named; the gate
  needs it not named; no `writable_roots` set satisfies both. The gate half of #265 is
  therefore a recorded ceiling — the lane commits and lands by a hand finish, not unaided —
  rather than an open question. Stated once in `docs/multi-provider-dispatch.md` and §10 of
  `docs/research/codex-lane-live-findings.md`.

### Fixed

- **The client lock's age no longer flakes about one gate in every full `just unit`.** A holder
  block's `started_at` is written to a whole second and the reader took its own clock afterwards,
  so an age was right only while no second boundary fell between the two — and a subprocess spawn
  under `-n auto` is wide enough to cross one, which is why eight recorded arrangements never named
  the same duration twice and none reproduced on a quiet re-run. `CTI_LOCK_NOW` now lets a caller
  state the instant an age is measured against, so a test states both ends of the subtraction and no
  clock runs between them; unset — everywhere but a test — it is the wall clock, as before. A value
  that is not whole seconds is refused rather than quietly taken from the clock, and an age that
  cannot be computed now says which end it could not read. No assertion was weakened: the age is
  still asserted to the second (#222).

- **Engine updates now stop the regression tier as `engine_drift`.** Each probe verdict compares
  the server version recorded by the runner with a checked-in pin before trusting any result. A
  readable mismatch records both versions; a missing or malformed observation fails closed as
  `infra_unavailable`. The pin documents the deliberate update path beside its current value
  (#71).

- **The Arma tier no longer loses small-fry evidence failures in steady state.** Pass pruning
  validates both the timestamped directory shape and `verdict.json`'s exact probe, so a future
  `assault` probe cannot delete `base-assault` evidence; interrupted evidence is retained for a
  seven-day recovery horizon and then pruned. Timeline-rendering failures are recorded in
  `results.env`, and headed-client RPT collection chooses the freshest log across Windows user
  profiles instead of the lexically last profile. Each Python decision runs under a bounded `uv`
  call whose shell caller deletes or records nothing when that decision cannot run (#73).

- **The Claude breaker now sees the limit that actually binds the account.** The quota tap polls
  `/api/oauth/usage` without delaying the human's status line, selects the `limits[]` entry the
  provider marks active, and persists its kind and scope so `just breaker state` distinguishes
  `weekly_scoped` from `weekly_all`. A 429 suppresses another poll until the endpoint's exact
  `retry-after` boundary; an absent or unreadable header creates no project-chosen wait. The old
  five-hour and seven-day status-line aggregates remain a fallback when endpoint evidence is
  unavailable (#261).

- **A `zai` dispatch's own credential no longer reds the gate it was just granted.**
  `test_a_zai_dispatch_leaks_into_neither_the_parent_nor_the_next_lane` asserted
  `os.environ.get("ANTHROPIC_AUTH_TOKEN") is None` — a precondition of the box rather than anything
  the dispatcher had done. Widening the allowlist made the suite runnable inside a `zai` dispatch for
  the first time, and there the dispatcher has legitimately put that variable in the environment
  before pytest starts, so the assertion red on an ambient value while the seam had exported nothing
  at all. It now snapshots the environment and asserts it unchanged across the seam, plus that the
  lane's credential never appears in this process under any name: true in both arrangements, and
  strictly stronger, since "unchanged from clean" implies "absent" and also catches an export of any
  other variable the single-key check would have missed.

- **A denial that could not read a command no longer accuses it of bypassing a hook.** The commit
  bypass guard fails closed on any Bash command it cannot parse, which is right, but it said so in
  the words it reserves for a real bypass: an ADR-0010 accusation, with no hint of what had actually
  happened or what to do instead. That cost a diagnosis. Three denials of long `gh` and `git`
  bodies were reported as false positives of the guard's short-flag pattern; the pattern had matched
  nothing in any of them, and all three were parse failures in a stale worktree copy of the guard
  predating the fix that taught it to read a heredoc inside a quoted substitution.

  The two findings now carry two messages. A command that could not be read is told that, told why
  it is still denied, and pointed at the shapes that work — a file passed as `gh ... --body-file` or
  `git commit -F` — with no accusation attached. A real bypass keeps the wording it always had.

  The short-flag pattern is narrowed at the same time. It read any hyphen-led run of letters
  containing an `n` as a cluster of `--no-verify`, which is true of `-an` and equally true of
  `-anchored` and `-agent`; it now matches only clusters built from the short options `git commit`
  actually takes. No real spelling is lost, since a cluster carrying a letter git does not take is a
  command git itself refuses. The three reported commands are vendored verbatim as test fixtures.

- **A unit gate no longer reds on what the box happens to be carrying.** The test of
  `just watch-report` injected a temporary directory for the recipe's breaker half but not for its
  watcher half, so the read went to the machine's live `~/.arma-cti/watch/` and any unacknowledged
  watcher finding turned `just fast` red for every landing, whatever the diff. A docs-only landing
  hit exactly that, on two findings left by a crash cluster that had nothing to do with it, and the
  only way past was to acknowledge them — state mutation a unit gate should never require.

  The watch tooling now takes its directory from `CTI_WATCH_DIR` when no flag names one, the twin
  of `CTI_BREAKER_DIR` and for the same reason: the recipe folds two reads into one line and
  forwards its arguments to one of them, so the other half has no flag a caller could pass. Both
  halves of the tooling honour it — the reporting half and the arming shell — because a read moved
  out of the machine's tree while the write stays in it has relocated the coupling rather than
  removed it. A tripwire beside the one guarding the tier's locks now fails the suite if a future
  test drives the watch tooling without pointing it somewhere it owns.

### Added

- **`just recover`: the recovery runbook's by-hand look and its resumption briefing, as a tool that
  prints only what it read.** Two procedures in `docs/agents/recovery.md` had each been run by hand
  twice, which is the codification threshold that document sets for itself.

  `just recover check <name>` resolves a BLIND watcher finding — the watcher saying it could not
  read a worktree's HEAD, which is deliberately not "still running". It reads worktree presence,
  git's registration, HEAD from whichever of three sources still holds one, whether that HEAD is on
  `origin/main`, the dispatch record over the same worktree, and what reached `origin/main` while
  the watch was live, and answers `lost_work` (naming the commits and the files they touch),
  `still_live`, `finished_and_cleaned`, or `unproven`. It replays the twenty-fourth retro's four
  BLIND findings and the twenty-fifth's two dead assessors to the verdicts those retros reached by
  hand, off their records vendored as fixtures. `unproven` exists because an absent worktree with
  nothing attributable to it has no unlanded commits *because it has no commits anything can see*,
  and calling that clean would be the vacuity `just prereqs` was corrected for; the cleared verdict
  needs positive evidence and prints, in the same breath, that a tree deleted while carrying
  unlanded commits reads identically from outside. It acknowledges nothing: `just watch-report
  --ack` stays a judgement.

  `just recover brief <issue|worktree>` computes the two reconstructions a resumption briefing owes
  that are computable — what moved on `origin/main` since the dead agent's last commit, and what of
  its own environment died — and prints the third, which is judgement, as an empty labelled
  heading that no input fills. `just handoff`'s own output goes beside them, including its "no
  handoff" message, which is an answer rather than a blank space. Two words appear nowhere in what
  it writes: a commit is on `origin/main` or is not, and which of those the *work* is stays the
  resumed agent's to verify on wake — the 2026-08-02 briefing that read "clean, zero ahead" as lost
  work is the error the omission is built against.

- **`just brief`: a dispatch briefing's invariant half, composed from data, with the gate line
  derived rather than chosen.** The seat and the Model roles line behind it, the worktree protocol
  as the two calls it now is, the landing protocol, the verdict paste rule where the gate produces
  a verdict, and the open flake lines read from the tracker at composition time so a fixed flake
  leaves the next briefing without anybody remembering to remove it. The gate is derived from two
  signals in the issue body — the file paths it names, and whether it speaks `CONTEXT.md`'s domain
  language — against the same in-world list `just admission audit` cross-checks a landing with, so
  a composition-time prediction and a landing-time audit cannot disagree about what in-world means.
  An issue whose surface cannot be read comes back **undetermined** and says so; it never resolves
  to the cheaper gate, because a briefing naming `just fast` for an in-world change is the defect
  the table exists to prevent. Measured on two vendored populations — the fourteen issues in the
  last four hundred commits whose landings touched an in-world path, and the twenty that did not —
  at zero under-gates and zero over-gates, with the whole error budget spent on saying "I cannot
  tell". What the tool refuses to write is the actual work of the turn: the task statement, the
  scope boundary, the ground truth to read and the reason for a non-default seat are emitted as
  visible placeholders, so an unedited brief is obviously unfinished rather than plausibly
  complete. Its token effect is deliberately **unclaimed** and unmeasured.

- **`just queue`: the dispatch queue as data, and the freeze as a rung a running session reads.**
  The human's freeze, the ruled WIP limit, the carve-out packages and their reservations now live
  in `~/.arma-cti/queue/policy.json` with a `transitions.jsonl` beside it, outside every worktree,
  on the same state-document-plus-journal pattern the breaker and the admission bar already use.
  `just dispatch` reads it **per dispatch**, below the readiness rung and above the admission bar,
  the breaker and the off-peak rule.

  That per-dispatch read is the whole point. A freeze recorded in an issue comment and in session
  memory does not reach an orchestrator session already running; a freeze in a file read at
  dispatch time does. The refusal follows the off-peak rule's precedent exactly, including the part
  that is easy to get wrong: **it carries no failure class**, because nothing was found about any
  provider, any lane or any code. There is no flag and no environment variable that dispatches
  through it, because the freeze is the human's and only they amend it.

  The file carries only what GitHub cannot, and **every entry quotes the ruling it came from** — a
  write without `--ruling` is refused, and a read that finds an entry without one refuses
  `policy_invalid` rather than reading as permission. An absent policy refuses too: a box where
  nobody has recorded a freeze state is not a box where dispatch is open.

  Reading it: `just queue state` prints every entry with its ruling and the in-flight list;
  `just queue next` prints the next candidate with its whole derivation or a named refusal;
  `just queue check --issue N` is the pre-dispatch read as an exit code. The in-flight set is
  derived from the box — `issue-<N>` worktrees plus dispatch records with no result — never
  counted by hand, and because an agent can start work without touching either, the count is a
  **floor** and the tool says so by printing the list it derived. The harness's own `agent-<hex>`
  trees are excluded by name: 93 registrations against 6 dispatch records, measured on this box.

  It selects and prints; it never dispatches.

- **A design for taking rule-based coordination out of the orchestrator's head and into files.**
  `docs/orchestration-design.md` factors dispatch routing, claim verification, stall handling and
  crash recovery into four tool halves — a queue the scheduler reads, a composed dispatch briefing,
  a computed close audit, and the recovery runbook's two computable procedures — then sizes what is
  left and proposes a seat for it.

  The smallest piece is the one that closes a hole. A freeze recorded in an issue comment and in
  session memory does not reach an orchestrator session already running; a freeze in a policy file
  that `just dispatch` reads per dispatch does. That is the same conversion the off-peak rule
  already made — a human's standing rule enforced by refusal, with no override — and the refusal
  carries no failure class for the same reason: nothing was found about any provider or any code.

  The study is a design and builds nothing. Its rulings list is on #242 and on the human's pile
  (#217); the four tool halves are filed as their own issues.

- **A dispatch is refused against an issue that states no criteria.** Definition of ready,
  mechanically: `just dispatch` now reads the issue body before it plans anything, and refuses
  when nothing there says what to do, or when nothing names the gate, test, verdict or artefact
  that would settle it. The refusal carries no failure class — the provider is up and the lane
  is fine, this project simply will not spend a lane on an issue nobody has finished writing —
  and the remedy is always an edit to the issue by a human or by triage. The tool never rewrites
  the body it is judging, and there is no override flag. Like every rung, it is lane-blind.

  How strict it is was measured rather than chosen. The check's definitions were written down
  first, then run against the twenty most recently dispatched issues, vendored verbatim under
  `tests/fixtures/readiness-corpus/`. Every one of those twenty was dispatched and landed, so
  every refusal on that corpus is a false positive by construction. Two of the three sub-checks
  refused none of them and now refuse a dispatch. The third — can the criteria be counted off? —
  refused three, and all three are the same shape: a ruling execution or a defect repair, whose
  criteria *are* the ruling and arrive as prose to be transcribed rather than paraphrased into a
  checklist. Feature issues and experiments: 0 of 16. Ruling executions: 2 of 3. So that
  sub-check reports on every issue and blocks none, and its verdict is kept on the dispatch
  record so the rate can be counted again once the corpus has grown.

  `just dispatch --readiness --issue N` is the same verdict without a dispatch, which is the
  surface triage and the human need, since they are the only parties who can fix an unready
  issue. `--issue-body <path>` reads a body from a file instead of from `gh`, for a draft that
  has not been filed yet.

- **The Codex lane is registered, and its substrate was chosen on evidence rather than on the
  expectation ADR-0061 recorded.** `just dispatch --lane codex` reaches the ChatGPT Plus
  subscription through OpenAI's own Codex CLI, with four profiles over the two agentic coding
  models the authenticated catalogue actually lists — `gpt-5.6-sol` and `gpt-5.6-terra`, read
  from the CLI's own model cache rather than assumed from the shorthand the models are usually
  called by.

  The spike that chose it is in `docs/research/codex-lane-live-findings.md`. Three findings
  decided it, and two of them invert what was expected. Effort is a **real dimension** on this
  lane — one non-memorised counting problem produced 484 reasoning tokens at `low` and 2,393 at
  `xhigh`, a factor of 4.9 — which is the exact opposite of z.ai, where two budgets a factor of
  thirty apart were indistinguishable and five effort levels collapsed to one profile. Telemetry
  parity turned out to need **no engineering at all**: Codex's OTel resource block honours
  `OTEL_RESOURCE_ATTRIBUTES`, the same mechanism every other lane already uses, so a dispatch's
  six `cti.*` attributes reach the collector's `cti.dispatch_id` filter unchanged. And hook
  parity is **proven rather than reachable**: Codex sends Claude Code's own payload shape, down
  to reporting `tool_name: "Bash"` rather than its internal `shell`, so not one of the eight
  committed hooks in `.claude/hooks/` needed editing.

  `tools/hook_parity.py` carries `.claude/settings.json`'s hook table onto the lane per
  invocation, and `tests/unit/test_hook_parity.py` is ADR-0061 Decision 4's parity suite —
  which runs the real committed hook scripts against the payload a live Codex turn was observed
  to send, because the ADR names "asserting on its own mock" as the way such a suite lies.

  Two settings are deliberately per-invocation rather than written to the box. The metrics
  exporter is overridden on argv, so `~/.codex/config.toml` keeps `metrics_exporter = "none"`
  and a Codex session the human starts by hand still exports nothing anywhere. The hook table
  travels the same way, so a hook landed on `main` reaches this lane by being landed, with no
  second copy to drift. The ledger prices the pool `no-estimator`, typed like z.ai's — but for
  the opposite reason, recorded as such: Codex supplies the numerator and withholds the
  denominator, z.ai the reverse. #243, refs #221, #229, #234, #225, ADR-0061.

- **The cross-provider review seat now has a shape, and it is a shape a machine can count.**
  `tools/dispatch.py` has carried `"review": True` since #223 without ever being dispatched.
  `docs/review-dispatch.md` says what a review dispatch is handed (a landed SHA, its issue,
  its close audit, a worktree at `origin/main`), what it must hand back (claims, each naming a
  file, a line, the convention it is checked against, the failure scenario, and the cited lines
  pasted rather than retyped), and where each claim goes — a defect to a new issue, an
  observation to a comment on the reviewed issue, and a claim that does not survive checking
  recorded as checked and not upheld rather than quietly dropped.

  Two consequences worth naming. The permission mode is `plan`, which is the mechanical face
  of the #228 ruling that a review lands nothing; the brief says so too, but the mode is the
  part that cannot be talked out of. And a confirmed defect raised on the reviewed issue
  inside the bar's seven-day window is `finding` in `tools/admission.py`'s `UNCLEAN_REASONS`
  exactly as it already stands — no code change was owed — with four qualifications recorded
  in the doc, of which the load-bearing one is that only a *confirmed* claim counts, since a
  noisy reviewer must not be able to fail another lane's attempt without ever being right.
  #240.

- **A landing's new tests now have to notice the code changing, mechanically.** `just fast`
  grows a rung, `just mutation`: for every test module a landing adds or rewrites, a bounded
  sample of mutants is planted in the source those tests actually execute, and each is judged
  by only the tests that reach its line. A module whose tests kill fewer than half of them is red,
  and so is one none of whose tests executes a line of this repo's source at all — which is
  what a suite of `assert True` earns. The floor comes from measuring all 68 of this repo's
  test modules: the weakest scores 62%, the median 85%, and a purpose-built module that runs
  every branch of its subject while asserting only `is not None` scores 30%.

  Until now nothing mechanical stopped a vacuous green test. The defences were red-first
  discipline in a dispatch briefing, a habit visible in closing comments, a vacuity rule that
  governs probes only, and `mutmut` — scoped to modules that do not exist and, per #172's
  close, not running. Because the new rung sits inside the recipe `tools/land.py` uses as its
  landing gate, it is lane-blind: a z.ai or Codex landing meets the identical red without
  knowing the gate is there.

  The subject each module is judged against comes from one `coverage.py` pass with per-test
  contexts: the name where the name fits — `test_budget.py` → `budget.py`, and
  `test_daemon_casualties.py` → `daemon.py` — and otherwise the file whose lines this module's
  tests tell *apart* rather than merely load. Import-time lines never count, which is what
  leaves an `assert True` module with no subject at all rather than the accidental owner of
  everything the shared arrangement imported.

  There is one escape and it is a named list — `NO_PYTHON_SUBJECT` in
  `tools/mutation_smoke.py`, a module and its reason, in the diff — for the test modules whose
  subject is a shell script or an authored document. No flag lowers the floor, no marker in a
  test file excuses it, and lowering the floor is not an alternative to strengthening an
  assertion. ADR-0064 records the decision; `docs/research/mutation-testing.md` carries the
  evaluation of mutmut and cosmic-ray, the corpus sweep the floor comes from, and a plain
  statement of what the gate does not catch.

- **The z.ai lane now dispatches only in off-peak hours, and says so when it will not.**
  The human ruled that on 2026-08-05 as a hard rule rather than as guidance, so it is a
  rung in `just dispatch`'s ladder beside the admission and breaker reads: inside z.ai's
  published peak band every dispatch to the lane is refused, naming the window, the
  published terms it came from, and the time it next opens. There is no override on this
  surface — no flag, no environment variable, no per-dispatch exemption — because the
  rule is the human's and only they amend it.

  The refusal carries **no failure class**, for the same reason `admission_escalated`
  carries none: the failure-class table types what a run found, and this one found
  nothing. The provider is up, the credential is good, and the project simply declined to
  spend on that lane now — `infra_unavailable` would assert an outage that is not
  happening.

  The window has one home. It is the lane's published schedule in `tools/breaker.py`, the
  same object that prices a dispatch's `plan_charge` block, so what refuses a dispatch and
  what a dispatch records cannot disagree; the dispatcher restates no part of it, and a
  test holds it to that. `just breaker state` now shows each lane's window and which band
  the clock is in, so a refused dispatcher sees why in the place it looks next, and
  `just dispatch --list` shows which lanes carry the ruling. The window was re-read
  against z.ai's published terms while landing this, and matches; the one reading those
  terms do not settle — that the band is half-open, so 18:00 SGT exactly is already
  off-peak — is recorded beside the constants and flagged on #221. #238.

- **The admission bar for a foreign lane is now the thing that decides, rather than a
  number somebody has to remember.** `just admission` carries the human's ruling of
  2026-08-05T20:00Z on #224 — Part A's four process criteria on every one of ten issues
  with no allowance, Part B's at-most-one unclean in ten, one re-run and then a human,
  and the recon substitute of ninety per cent of cited file-and-line references
  resolving, pooled over ten dispatches. `just admission bar` prints all of it, including
  the pre-registered operating characteristics, so what the bar does and does not
  discriminate is quotable rather than recalled. Nothing in the tool derives a number:
  the derivation was #230's read of 131 eligible closed issues, and a bar that moved once
  a lane's own numbers arrived would not be pre-registered at all — a unit test guards
  every constant against exactly that.

  **Every foreign route starts at zero**, and `just admission status` says so until the
  first record: the 131 issues behind the bar are Claude's history, Decision 6's question
  is absolute rather than comparative, and nothing is back-filled. The counters accrue
  only as foreign lanes run, one `just admission record` per issue, and that command
  invents nothing — each Part A criterion is a required choice with no default, because a
  criterion nobody passed is a criterion nobody checked. Two of them are cross-checked
  against git in the refusing direction only: a landing that touched an in-world surface
  cannot have its corpus criterion waived, and one that edited an acceptance spec or a
  generated file cannot record the hooks as clean.

  `just dispatch` reads the standing before it plans anything and refuses only the
  ruling's far end — a profile that has spent both attempts, which is a human's to clear
  and not a third attempt to improvise. A profile still on probation dispatches normally,
  since the record the bar judges accrues only by running, and `claude-native` is exempt
  throughout because nothing leaves Claude there. #224, ADR-0061 Decision 6.

  The recipe's command-table row and the two rules an agent would otherwise get wrong from
  first principles — probation is dispatchable, and `reset --force` is the human's — now
  sit in `CLAUDE.md` alongside it, which is where ADR-0057 says a landed recipe's gated row
  belongs rather than lagging. The admission refusal stays deliberately classless, and the
  file now says why.

- **The multi-provider initiative's first week is now written down where an agent reads
  it.** `CLAUDE.md` gains the five recipes the week built — `just dispatch`, `just land`,
  `just breaker`, `just ledger-sync`, `just prereqs` — two failure classes for work that
  never reached a provider (`quota_exhausted` and `provider_refused`, the second widened
  to cover this project's own breaker refusing a dispatch as well as a provider refusing
  a request), and the three rules that decide what may leave Claude at all: a dispatch
  names an opaque `(lane, model, effort)` profile rather than a model and an effort chosen
  separately, work leaves Claude only where a mechanical gate catches a wrong answer, and
  a lane's authority is the enforcement it demonstrably runs rather than what its provider
  claims. Two new prohibitions come with them: never export a lane variable into a shell
  or a settings file, because `ANTHROPIC_BASE_URL` has no scope smaller than the process
  tree and would silently redirect every session on the box; and never extend, invent or
  guess a breaker's wait, which is the `timeout` row's discipline transposed onto a
  five-hour quota window. The reasoning behind each — the lane and profile model,
  per-invocation environment assembly, the worktree assertion, and why the breaker refuses
  to invent a cooldown — is in the new `docs/multi-provider-dispatch.md`, one hop from the
  rule rather than resident in every context window.

- **The z.ai lane is now a real lane rather than a registry entry, and four things
  believed about it were put to the endpoint.** `docs/research/zai-lane-live-findings.md`
  records the first live measurements: the key reaches eight GLM models, prefix caching
  happens automatically and identically whether or not `cache_control` is sent, and
  `thinking.budget_tokens` is ignored — a hard prompt at budget 1,024 and at budget
  32,000 both thought past nine thousand tokens and both stopped on `max_tokens`. Two
  consequences land in the dispatcher. Claude Code's five effort levels differ only in
  the budget they send, so on this lane all five are one configuration: ADR-0061
  predicted a partial collapse and the measurement makes it total, leaving one profile
  per model — `zai-glm52-max` and the new, cheaper `zai-glm47-max`. And
  `ENABLE_PROMPT_CACHING_1H` is not set here and cannot be inherited from a shell, since
  it only rewrites a TTL that decides nothing measurable and a token saving would not be
  a plan saving under a prompt meter.
- **Every dispatch on a lane whose plan discounts by time of day now records which band
  it was charged in.** `dispatch.json` carries a `plan_charge` block — the meter, the
  band, the multiplier, and the published window that produced them. The band is a
  function of the timestamp today, but of a schedule that can move, and a record carrying
  only the timestamp would silently re-price its own history the first time it did. This
  records the discount; nothing yet chases it.

- **The project now knows which currency it is optimising, and it is not the one it was
  ranking in.** `docs/research/token-efficiency-plan-currency.md` reconciles the
  token-efficiency corpus with what this Max subscription's plan meter actually charges,
  measured by #218: an output token weighs at least 3,462 times a cache-write token,
  where the published price list says two and a half. Two cost models now sit side by
  side, each labelled for what it measures — a **token-flow view** in input-equivalents,
  correct on an API key and a sound proxy for latency and context pressure, and a
  **plan-currency view** in percentage points of the binding plan window, which is the
  only currency in which "we ran out" is a sentence. In plan currency the older
  document's headline inverts: everything the model writes is not a twentieth of the
  bill but something like a third of it, and the entire cache-cliff family it ranks
  first, second and third is worth under 0.7% of the plan meter combined. Six days of
  work generated 132 five-hour-windows' worth of points in output alone; the same six
  days' 86 million cache-write tokens are bounded under one point in total. Three of
  those top recommendations survive anyway, on wall clock and on correctness rather than
  on tokens, and they are re-argued rather than re-priced. What the correction promotes
  has never been ranked at all: reasoning effort as an output-volume multiplier, fan-out
  and retry discipline, and CLAUDE.md's ban on verification passes, which turns out to
  be a first-order cost rule that happens also to be a quality one. The document is
  honest about the hole in the middle — cache reads were never measured, they are
  somewhere between nothing and 62% of the meter, and one cheap unrun experiment decides
  whether shrinking context is worth a third of the plan or nothing at all. It also
  defines the metric the multi-provider dispatch ledger records for ADR-0061's first
  decision: fraction-of-cap per pool, an estimator and an observed meter delta side by
  side, with the Claude estimator's basis settled as output tokens on a named
  calibration. #220.

- **The landing protocol is one call that cannot forget a step.** `just land` runs the
  whole of CLAUDE.md's Commits-section procedure — fetch, rebase onto `origin/main`,
  re-gate, `git push origin HEAD:main`, fast-forward the main checkout — and refuses by
  name rather than by shell error. #209 measured 220 hand calls doing exactly this
  across 117 of 214 agents, and each of the procedure's documented traps exists because
  agents kept falling into it. Three of them are now mechanisms rather than prose. The
  refspec is a constant no argument reaches, so `git push origin main` — which pushes
  the local `main` branch that a detached worktree is not on — cannot be typed through
  this recipe. The gate is *inside* the protocol: `just fast` runs after the rebase on
  every landing that pushes anything, with no flag to skip it and no heuristic deciding
  it is unnecessary, and its output is never captured, so a red gate hands back the
  gate's own words. And the fast-forward into the main checkout can no longer be skipped
  in silence: when it does not run the exit is non-zero and one line, `merge_command=`,
  names the exact command the orchestrator must run — CLAUDE.md's "never skip it
  silently" with a mechanism behind it at last, against the stale-hook window ADR-0042
  and #130 describe. Refusals are the recipe's own vocabulary rather than the harness
  failure-class table (a landing is not a corpus verdict), and the exit code separates
  "nothing landed" from "the work IS on origin/main and a step is outstanding". Logic is
  Python under pytest with the justfile keeping only the seam (ADR-0049); the ladder is
  asserted class by class and the end-to-end tests drive real `git` over a bare
  repository, a main checkout and a linked worktree, never the real remote. #213.
- **A lane stops being dispatched to when it runs out of quota or starts serving the
  wrong thing, and the two are kept apart.** `just breaker` keeps one circuit per lane,
  and `just dispatch` reads it before it plans anything, so a lane that cannot help
  costs nothing to discover. An **availability** trip is quota exhaustion: the lane
  reopens at the provider's own published window boundary — computed, never guessed,
  which is why ADR-0061 gave `quota_exhausted` a failure-class row rather than routing
  it to `infra_unavailable` — and at that boundary the circuit goes half-open, one
  dispatch probes it, and an ordinary outcome closes it. A **quality** trip is three
  consecutive gate failures or refusals on one lane: it refuses with `provider_refused`
  and does not reset on a timer at all, because time does not fix a provider that
  swapped the model behind a name, so it escalates and a human clears it with `just
  breaker reset --lane L --force`. Three consecutive provider errors with no published
  reset open the lane and *hold* it; inventing a cooldown there is the measured defect
  that disqualified LiteLLM as this breaker, so nothing here invents one, and a held
  lane reopens on a fresh first-party quota reading or on an explicit reset. Feeds are
  per provider and honest about what each can know: Claude's is a status-line tap that
  passes the human's own status line through untouched, Codex's is
  `account/rateLimits/read`, and z.ai publishes nothing machine-readable, so its
  consumption is *estimated* from our own dispatch ledger against the documented
  five-hour and seven-day caps and the peak multiplier — labelled estimated, and
  deliberately unable to trip anything, because the ledger counts dispatches and the cap
  counts prompts. With no tap wired the lane is 429-reactive: a finished run's own log
  is classified and fed back, which is late but not blind, and the refusal says so.
  `just watch-report` now prints one verdict line per lane that is not dispatchable and
  stays silent about every lane that is fine — a verdict, never three percentages — and
  `just breaker state` names the lanes whose feed has never said anything. Every
  transition goes to OTel and to a journal beside the state, so a collector that is down
  loses nothing. #226.

- **`just ledger-sync` materialises one durable row per dispatch, from the telemetry bus
  and nothing else.** ADR-0061 makes OTel the single capture bus and the ledger a
  materialised view over it, so the collector stays the only writer: this reads what it
  wrote and lays down `~/.arma-cti/dispatches/<id>/ledger.json` beside the plan, never
  appending to a telemetry file and never filling a row in from a plan it could see all
  along — a dispatch that put nothing on the bus gets a row that says zero records. It
  does the three readings configuration cannot. **Cross-lane normalisation**: Claude
  Code's `claude_code.token.usage` datapoints keyed by `type`, opencode's AI SDK spans
  carrying `gen_ai.usage.*` *and* its own `ai.usage.*` copy of the same numbers on the
  same span (first key per bucket wins; adding both would double every opencode
  dispatch), Codex's `codex.turn.token_usage` read at whichever temporality the metric
  declares, because summing a cumulative counter multiplies a dispatch's spend by how
  often the collector scraped it. A lane that reports tokens and no list price is
  `list_priced: false`, not a free dispatch. **End-state typing** in ADR-0061's
  vocabulary from
  provider records only — `provider_refused` from a refusal event, `quota_exhausted` from
  a rate-limited error carrying whatever `reset_at` the record held *verbatim*, and
  `infra_unavailable` for a dispatch that reached no provider at all; what a closed lane
  then waits for is #226's breaker and is deliberately not computed here. **The join** to
  the issue, the landed SHA — the newest commit on `origin/main` after the dispatch's
  base SHA referencing the issue — and a gate outcome derived from that landing rather
  than from the child's exit code, because the gates run inside the dispatched process
  and a coding agent's exit code is not a gate result. Source preference is stated in
  every row and every line: the durable per-dispatch export the #230 root script creates
  is preferred, the rotating capture is a **degradation** that warns, and a dispatch with
  no records read from a rotating source is typed `unknown` rather than
  `infra_unavailable`, because absence there is a fact about the view. With neither
  source present the sync refuses `infra_unavailable` and is not a result. Content
  logging stays off and cannot leak through the view: attribute *values* are copied from
  an allowlist of codes, categories and timestamps, so a capture that one day carried
  prompt text still would not put it in a row. Retention is stated and mechanical — rows
  kept indefinitely, the raw export pruned after 30 days and only where a row was
  materialised from that same durable file, `--apply` required to delete. Full policy in
  `docs/telemetry-ledger.md`. #227.

- **The ledger prices a dispatch in the currency the plan charges, not in dollars it
  never bills.** ADR-0061's first decision optimises Claude spend, and the row's only
  spend-shaped number was Claude Code's client-side cost figure — which is API list
  pricing, recovered rate card and all by #218, and modelled $849.76 for a run that moved
  the plan meter zero. Every row now carries `cap_fraction`: percentage points of a
  pool's window cap, per #220's definition. The Claude estimator is output tokens over a
  measured constant — one five-hour point is 30,209 output tokens, one seven-day point
  181,253 — with the calibration id, the per-window rate and `excludes: ["cache_read"]`
  carried on the row, so a re-measured rate re-prices history rather than invalidating
  it. Both windows are estimated and neither is named binding, because which one binds is
  the meter's answer and no meter reaches this view. Every claim it cannot make is typed
  rather than defaulted to a number: the observed half is `null` with its reason, since
  the quota feed is a status-line spool and not a record on the bus, and a `0.0` there
  would say the meter reported free — the exact inference #218's third confound
  disproved. A lane's pool comes from the plan and never from the counters, so a z.ai
  dispatch is priced against z.ai's pool, an unrecognised lane is priced against none,
  and neither is ever booked Claude at zero, which is the entry that would make routing
  work off Claude look free by construction. `attribution: "dispatch_only"` states the
  remaining gap in the open: the orchestrator's own turns share their parent's resource
  block and reach no row, so every row is short by a known term rather than complete.
  The list-price figure survives only as `usage.list_price_usd`, labelled in the row,
  absent from the summary line and ranked on by nothing. #232.

- **A logical subagent is dispatched onto a named lane, and the lane's environment goes
  nowhere else.** `just dispatch --lane claude-native --profile opus-high --seat
  implementer --issue 223` starts a separate process and returns a dispatch id at once,
  per CLAUDE.md's rule that a turn does not block for five minutes. Week one registers
  two lanes, both on the `claude` binary: `claude-native`, which reaches the Anthropic
  subscription the one compliant way ADR-0061 records, and `zai`, the permitted mirror
  against z.ai's own published Anthropic-shaped endpoint. A **profile** is one opaque
  `(lane, model, effort)` token in a registry — `opus-high`, `zai-glm52-max` — because
  effort vocabularies do not commensurate across providers (ADR-0061 Decision 5), so
  there is deliberately no `--model` and no `--effort` on the recipe. A **seat** carries
  Decision 2: a foreign lane refuses the seats no mechanical gate covers, so
  `--lane zai --seat fable` comes back `seat_not_eligible` rather than being trusted to
  the caller's memory. The **environment is assembled per invocation and exported
  nowhere** — `ANTHROPIC_BASE_URL` set globally would redirect every Claude Code session
  on this box, the orchestrator included — and assembly strips every lane-owned variable
  from the inherited environment before adding this lane's, so a parent that already
  carries a foreign base URL produces exactly the same child as a clean one. Credentials
  come from `~/.arma-cti/credentials.env` at mode 0600, by environment only: never on
  argv, so never in `ps`, and the dispatch record names the key it used and not its
  value. Identity rides on `OTEL_RESOURCE_ATTRIBUTES` as `cti.dispatch_id`, `cti.lane`,
  `cti.profile`, `cti.seat`, `cti.issue` and `cti.base_sha`, which is what makes a
  dispatch's telemetry self-identifying and Decision 1's per-pool metering a query. The
  dispatched process asserts `git rev-parse --show-toplevel` against its assignment
  before the runner starts and refuses loudly on a mismatch (#105's fourth instance),
  and a lane that cannot be reached — no credentials file, no key, no worktree — is
  `infra_unavailable` and not a result. Logic is Python under pytest with bash keeping
  only the fork (ADR-0049); the end-to-end tests run the real seam against a real git
  worktree and a fake `claude` on `PATH`, so the negative claims are made about an
  actual child environment rather than a mock. #223.

- **`just check` refuses a committed credential.** `check-secrets` runs `gitleaks` over
  the working tree on every static-tier run — #221's secrets ruling, landed with the
  first thing that has a credential to protect. `dir` rather than `git`, because on a
  detached worktree `gitleaks git` reports "0 commits scanned" and a gate that quietly
  scans nothing is the #41 shape; `--redact`, because a secrets gate that prints the
  secret has moved it rather than caught it. The stated limit is unchanged: this
  protects against git, not against the agent, which runs as the same user. #223.

- **`just prereqs` performs the multi-provider setup that does not need a human.** #229
  was written as a fifteen-item checklist; six items genuinely need a human and the rest
  were mislabelled, so they became one recipe with six subcommands. `check` reports every
  item's true state one line at a time and exits non-zero on a missing week-one
  prerequisite — a check that could not run reports `unknown` and is never a pass (#41's
  shape), and the Codex-lane items are reported but do not gate the week. `credentials`
  creates `~/.arma-cti/credentials.env` at 0600 outside every worktree and takes one
  pasted key off the terminal with echo off, so the value reaches no argv, no log, no
  shell history and no committed file; it refuses to overwrite a recorded name without
  `--force`. `sudo-script` **generates** the initiative's only root script and prints the
  path — three root acts (the collector's `traces` pipeline and filtered per-dispatch
  `group_by` export, the restart, the durable export directory) in one file written to be
  read, which backs up before writing, validates before restarting, is idempotent, and
  refuses outright unless `/etc/otelcol-contrib/config.yaml` is byte-identical to what the
  generation was computed from. `statusline` chains a quota tap **ahead of** the existing
  status line rather than replacing it, preserving the configured command verbatim and
  never touching its stdout; the recipe states in its own output that the file is outside
  this repository and nothing here can hold the tap in place. `tools` installs `gitleaks`
  user-local against its published checksum — no sudo — and writes the Codex config
  disabling the `metrics_exporter` that otherwise defaults to Statsig →
  `https://ab.chatgpt.com/otlp/v1/metrics`, **before** first use, since afterwards means
  telemetry has already left the box. `plan-tier` records the z.ai tier and its published
  caps, and refuses by name rather than guessing one, because no machine-readable source
  for it exists. Logic in Python under pytest (ADR-0049), bash only at the tap's stdin
  seam. #230.

- **The worktree protocol is one call, and it refuses by name.** `just worktree add
  issue-214` fetches, creates `.claude/worktrees/issue-214` off `origin/main` detached,
  runs CLAUDE.md's pre-flight on the result and prints the absolute path and the base SHA
  — the four steps every dispatch briefing used to narrate, and #209 measured as the
  widest hand loop in the project (212 calls across 106 of 214 agents). `check` re-runs
  the pre-flight alone mid-task, `list` sweeps all 86 registrations, and `done` verifies a
  tree is clean and landed before removing it. The correctness case is #105's: worktree
  assignment handed two agents one tree five times in one evening and a routine reset
  destroyed one of them, so `worktree_occupied` names the other holder's HEAD, state,
  uncommitted count and unlanded commits, and **nothing on a refusal path resets, cleans,
  prunes or removes** — the tests assert the other holder's files survive, not merely that
  the call refused. `done`'s `unlanded_work` is the refusal git does not give you: `git
  worktree remove` allows a clean tree carrying commits `origin/main` has never seen.
  `check` answers `unverified` rather than `dirty_tree` on a dirty tree, because a file
  you wrote and a file another agent wrote are the same two lines of `git status`; the
  list comes back and the judgement stays the agent's. The ladder is Python under pytest
  (ADR-0049) with the recipe as the process seam. #214.

- **A continuation fetches its predecessor's handoff without reading the thread.**
  `just handoff <issue>` prints the newest comment on that issue whose body opens a line
  with `Handoff-for:`, and nothing else — no thread, no metadata beyond what the handoff
  carries. #208 measured why: 85.6% of a successor's first-ten-turn state reconstruction
  is issue-thread reading, and everything read on turn 1 is billed about 12.55× over a
  median 114-turn agent's life, so reaching a 1,500-character handoff through a
  40,000-character thread defeats the point of having written one. Against #208's own
  thread it prints 1,475 characters where the thread is 16,411. A thread carrying no
  handoff is a non-zero exit with a message rather than a silent empty print, which would
  read as "no state to carry" when it may mean "wrong issue number" (#168/#183), and the
  two failures are told apart by exit code the way the failure-class table tells a result
  from a stop: 1 is "this issue carries no handoff", 3 is "I could not look". The
  selection, the newest-wins rule and both refusals are Python under pytest
  (`tools/handoff_fetch.py`, ADR-0049) rather than the `--jq` filter #210 sketched,
  because that filter answers an empty thread with an empty line and exit 0 — and a jq
  predicate is not something the no-Arma tier can assert at all (#83). #210.
- **A whole-file read of something enormous is refused, and told where the pieces are.**
  A new PreToolUse hook, `.claude/hooks/deny-oversized-reads.py`, denies a `Read` whose
  window would deliver more than 40,000 characters and names the size, the file and the
  remedy — `offset`/`limit` with a line count that fits, `Grep`, or `mcp__semble__search`.
  A tool result is not paid once: it joins the prefix and is re-read on every later turn,
  and #203 measured 28 reads carrying 5.0% of every tool-result byte in this project's
  history, all of them `Read`. The threshold is the 98th percentile of the 2,549 reads
  behind that measurement — 6.4× the mean and 12.6× the median — so ordinary working reads
  never see it. What the hook measures is the payload the call would deliver rather than
  the file's size on disk, because `Read` stops at 2,000 lines: one vendored wiki page is
  572,976 bytes and delivers 39,256 of them, and a gate that denied it would also have
  named a number six times larger than the agent would have paid. Screenshots and PDFs are
  exempt, having no `offset`/`limit` to be redirected to, and the vendored wiki gets no
  exemption because it never needed one. Both directions are pinned in the no-Arma tier
  along with the `|| exit 2` wiring itself, run verbatim with an empty PATH (#168, #183).
  #207.

- **A subagent can no longer hold its turn open on a long wait.** A new PreToolUse hook,
  `.claude/hooks/deny-subagent-waits.py`, denies a `sleep` of 240 s or more and any
  `while`/`until` poll loop with a `sleep` in it — but only inside a subagent, which the
  hook tells by the `agent_id` field the harness sends there and nowhere else. #203
  measured why on this project's own transcripts: every subagent cache write is on the
  five-minute TTL and every main-session one is on the hour, so a turn held past five
  minutes pays ~201,000 input-equivalents to rebuild its prefix where ending the turn and
  starting a successor cold costs ~24,000. The orchestrator, where waiting is nearly free
  and is the recommended pattern, is left entirely alone. The denial names the alternatives
  rather than only refusing: end the turn, arm `just watch`, or run the thing detached with
  `run_in_background` — which the hook also permits, since a detached run holds nothing
  open. A bounded short sleep, a `timeout`-wrapped gate command, a `for` loop and prose
  about any of them all pass, and both directions are pinned in the no-Arma tier along with
  the `|| exit 2` wiring itself, run verbatim with an empty PATH (#168, #183). #205.

- **A Commander can see his own Squads on the march.** Playtest 0001 lost sight of two
  Squads for the length of a march and read the absence as death — they were alive at
  eight men apiece. The Observation's `SquadView` now carries `pos`, the Squad's map
  position in whole metres, beside the Place-grained `at` it has always had, and
  `cti_fnc_mapRender` draws an own-Squad marker wherever the Squad is rather than only
  where it is standing still. A Squad the world has not yet reported has no position
  rather than a false one, and falls back to its Place exactly as before. `at` is
  untouched, so the fog rule, Contacts and every existing reader are untouched with it;
  the AI Commander deliberately does not read the new field at MVP, which its module
  docstring says out loud. The marker is up to one 5 s push behind its Squad, accepted
  and stated where the rate is set. Human ruling of 2026-08-04 on #175; shape recorded
  in ADR-0058. The wire cost is a fifth of a Squad record: Stratis's worst-case Squad
  ceiling falls from 71 a side to 59, and ADR-0030's per-map trigger is unmoved.

- **A corpus verdict is rendered from its own record now, not read off 25 lines by hand.**
  `just verdict [pool-dir]` reads a finished pool run's `pool.json` and the per-probe
  `verdict.json`s and prints the lines a close quotes into the issue the run gated: worst class,
  counts, wall, SHA and whether the tree was dirty, the runner's own per-probe block verbatim,
  and a detail line per non-pass probe with its evidence path. No argument reads the newest pool.
  It closes a correctness hole as well as a token one — #134 once quoted a "full corpus 20/20"
  banner before any tool result contained one, every figure matching by luck, and since the prune
  deletes passes, pass evidence outlives its own directory only in the quote. A record it cannot
  believe is refused rather than half-rendered: a pool directory with no `pool.json` is a run that
  died before its merge and is not a result (ADR-0022), and a `worst_class` sitting below its own
  worst verdict is quoted at the worse of the two with the disagreement named. `infra_unavailable`
  renders as the stop it is, nothing is interpreted, and nothing is posted. #199.

- **The orchestrator's stall watch is a tool now, and it waits outside the turn.** Six agent
  stalls in one cycle were each caught by an orchestrator polling from inside a turn, and
  ADR-0053 ruled the harness defect underneath out of this repo's scope, so that watching is a
  standing cost — 4.24% of the whole token bill, because a turn that blocks past five minutes
  throws away its prompt cache and a waiting turn is about 110× a working one (#195).
  `just watch <name> <worktree> [subject]` now arms a detached watcher and returns at once;
  `just watch-report [--ack]` prints one actionable line per finding and nothing while every
  watched agent is still working. The stall predicate is mechanical — a completion artefact
  exists, no activity inside a grace window, and the worktree's HEAD has not moved — and it
  distinguishes the two escalations the record separates: a stall on a clean tree is a lost
  dispatch, a stall on uncommitted work is work at risk, so that line names the files and orders
  the commit first. The watcher never messages an agent (prodding stays a judgement), never
  retries an `infra_unavailable` run, and reports "could not observe" as blindness rather than
  health. Orchestrator-facing usage: `docs/agents/recovery.md`. #198.

- **The development process's token bill has been measured, and it is mostly cache traffic.**
  `docs/research/token-efficiency.md` reads the four token classes off all 194 of this project's
  Claude Code session transcripts (17,515 turns) and prices #195's four seed ideas against them.
  What the model writes is 4.6% of the bill; a token that enters the context is re-read 35.7 times,
  so context size is a recurring per-turn cost. The largest recoverable waste is that a turn which
  blocks for more than five minutes loses the prompt cache and pays to rebuild it — 13.6% of
  everything spent so far, split between agents deliberately waiting (4.2%) and test recipes
  outliving the cache (2.8%). `just fast` is now 6 min 30 s, past that line on every invocation;
  the same suite runs in 1 min 44 s under `pytest-xdist`. Compressing agent documentation, the
  seed idea with the most intuitive appeal, measures at 25.6% on a real sample and ~1% of the
  bill, and it deletes the rationale this project has four validated instances of needing. #195.

- **Players choose a kit at their own Base, and keep it.** Under the human's ruling on #172
  (2026-08-04, recorded in ADR-0056), a player standing in his own side's Base is offered a curated
  menu of six kits — rifleman, grenadier, autorifleman, anti-tank, marksman, medic — and may take
  any of them whatever his squad type. It is free, it is players only (AI units keep their default
  loadouts), and it is refused anywhere but at Base. The kit survives death: a respawned player is
  dressed again in what he chose, as is one who joins in progress. The menu is one authored
  document, `addons/main/catalogue/loadouts.json`, read by the world that applies a kit and by the
  daemon that records which one — and what the daemon records is the *choice*, not the engine's
  loadout array, so a session save carries one word per player rather than a photograph of his
  magazines. #172, ADR-0056.

- **A `validated ×N` marker can no longer narrate a use its own count does not reach.** The count
  has lagged what its marker narrates twice: `docs/agents/recovery.md`'s ninth use landed with the
  count still ×8, and convention-lands' #131 exemplar with it still ×3 — that one rode three
  retros' status lines before anyone read the file. The retro skill's same-edit clause pre-priced
  the second violation as escalating to a mechanical check, and `just check` now runs
  `tools/check_validated_markers.py`: it reads the numbered uses in the four `> Status:` headers
  and reds when a header names a use its count does not reach. CLAUDE.md's five exemplar
  parentheticals are out of scope with the reason at the checker — no rule derived from the prose
  counts them, and every candidate miscounts at least two of the five in opposite directions. The
  list-format convention that would make them countable is a proposal on #186, for the human. #186.

- **A dead Commander watches but cannot act.** Under the human's rulings on #169 (ADR-0052), a
  Command issued from a machine whose player unit is dead is refused at the Command Port's door
  with a new judgement, `caller_dead`: "you are dead ... but issues no Command until he is back on
  his feet". The refusal covers both of the port's principals with one code and no asymmetry — a
  Commander's Purchase and a squad leader's Reinforce are turned away alike — because the check is
  asked of the calling machine before the gateway resolves which principal is asking. A dead
  Commander's `view` keeps arriving: watching is not acting. #188, ADR-0052.

- **The playtest observer's body leaves the world while he flies.** Under the human ruling on
  #190 (2026-08-04, the flag #178 left open), entering the Zeus-style observer camera in a
  playtest session now hides the human's own body and stops simulating it, and leaving the camera
  puts both back where he left them. Neither of the alternatives: a body that stays killable is
  what the old debug-console workaround cost him, and an invulnerable visible one is a target the
  AI can see and shoot at forever. Playtest path only, on the same boundary as the observer
  itself — nothing the regression corpus boots contains any of it. #190.

- **The AI Commander Reinforces.** Under the human ruling on #150 (2026-08-04), an understrength
  Squad standing at its own Base is now refilled by an AI-commanded side: when the side is at the
  force limit — where a Purchase is refused and Reinforce is the only way to add men — or when the
  discounted pro-rata refill undercuts the fresh Squad the Commander would otherwise buy. One
  spend per cycle, ties to the fresh Squad, and the funds trace carries both ways to add men with
  the trigger named in its sentence. Nothing about ADR-0040's two-principal port changes: a squad
  leader's own refill works exactly as before. #150, #191.

- **The pool's RAM trace attributes its own share.** The sampler's tier figure is machine-wide by
  `comm` on purpose — the right scope for a memory-ceiling question — but a peak could not be
  read without reconstructing which sibling pools shared the night (the unattributed 9.6 GiB of
  2026-08-02 took exactly that reconstruction). `ram.tsv` and `pool.json` now carry both figures:
  the machine-wide tier RSS and this pool's own, attributed by the values its slots already own —
  engine profiles and daemon ports. The healthy-box re-measure this enabled held the admission
  floor where it was: 2,439–2,463 MiB a slot across the 2026-08-04 full-corpus runs, against the
  2,500 MiB figure. #182, #125.

### Fixed

- **The ledger could lose a whole dispatch's token usage and report nothing wrong.** Its
  docstring promises that a metric whose shape it does not recognise is reported in
  `unclassified`, never silently dropped. That held for an unrecognised *attribute* and not
  for an unrecognised *body*: a body shape the reader did not know yielded no datapoints at
  all, so the metric never reached the net meant to catch it. The first Codex dispatch read
  `in=0 out=0` beside 49 records with `unclassified` empty. Found because Codex reports token
  usage as a histogram keyed by `token_type`, where every earlier lane used a sum keyed by
  `type` — but the silent-drop half was never specific to Codex, and would have hidden any
  future lane's usage the same way. A token metric in a body the reader cannot parse is now
  reported by name and body shape. #243.

- **The ledger no longer credits a dispatch with a landing that predates it.** The review
  dispatch `d-20260805-221743-8957c3`, armed at 22:17:43Z, had a row naming `e066b3c` as its
  landed SHA — committed at 21:01:17Z, seventy-six minutes before the dispatch existed, by
  somebody else. The window `tools/ledger.py` computed was `base_sha..origin/main` and nothing
  more, and on a review dispatch `base_sha` is the *reviewed* commit, so the range reached back
  to whatever was under review. A landing now has to clear two further tests before it is
  credited: descend from the dispatch's base, and postdate the dispatch's own start — the
  `started_at` in `result.json` once the run has ended, the plan's `planned_at` until then. A
  record carrying neither timestamp is credited with nothing, because a window the view cannot
  bound is not a window that admits everything. Where nothing survives, the row's `reason` names
  which test answered, as every other field in it already did.

  The seat's part is now said rather than left to arithmetic. `review` and `recon` land nothing
  by construction — ADR-0061 Decision 3 admits review to a foreign lane *because* its output is
  claims — so their rows carry the new gate outcome `lands_nothing` and name no commit at all,
  where `not_landed` would have read as a gate they were running for and failed. `running` and
  `not_a_result` still take precedence, being facts about the dispatch rather than about the
  seat. A unit test holds the ledger's seat table in step with `tools/dispatch.py`'s roster, so
  a seat added there cannot arrive here unclassified and inherit the same defect. Found by the
  #240 review exercise, which is the first thing it caught. #245.

- **A git conflict marker can no longer reach a tracked file, after one ate 1,669 lines of this
  changelog.** A stray common-ancestor line landed in 2b4f99b, and the next landing resolved its
  own rebase against the corrupted file and cut every release before this cycle; a885306 restored
  it. A marker in the base is not untidiness — git's merge machinery reads the region as
  structure, so the agent who springs the trap is never the agent who set it, and nothing in the
  tier could see it because a marker is ordinary text to every lint the project runs. `just check`
  now reds on any of the four marker forms in a tracked file, and `just land` carries the same
  finding as a named `conflict_markers` refusal judged on the rebased tree — so it also refuses a
  marker inherited from `origin/main`, which is the half that did the damage. The diff3
  common-ancestor line is covered explicitly, being the form that slipped and the shape every
  conflict on this box has. The separator is judged only in marker position, because six vendored
  wiki pages carry a bare run of `=` today and an unconditional rule would red the tree the gate
  protects. `merge=union` for the changelog was weighed and declined on a measurement rather than
  a hunch: it resolves concurrent landings silently but files entries under the wrong heading and
  duplicates the heading, trading a loud failure that is now caught for a silent one that is not.
  ADR-0062, #231.

- **A sibling agent's client no longer throws away a corpus that was already running.** The pool
  asks the play-session guard twice — once at the door, where it recognises another run's client
  and queues behind it, and once per probe on the bring-up, where it did not. The second one had
  no queue and `infra_unavailable` stops the pool taking new work, so a pass four probes in was
  abandoned nineteen seconds into another worktree's client probe, nineteen probes unrun and
  twenty minutes of world bring-ups thrown away. The per-probe guard now queues on exactly what
  the entry one queues on — a client in the process list while somebody else holds the
  machine-wide client lock is that run's, not a person's — bounded by the same `--wait` the caller
  gave the pool, which is handed to every probe rather than kept at the door. Nothing about the
  guard's verdicts changed; only its patience, and at the default of no wait every refusal is the
  one it gave before. #196.

- **A harness run can no longer leave the human's Arma install carrying half a mod.** Staging
  `@cti` for the headed client writes into the real Steam install, and it used to do it by
  deleting the live folder and then copying into it — so the play install had no mod for the
  length of the delete and half a mod for the length of the copy, and a run killed inside that
  window left the damage there for whoever launched Arma next to find. The new copy is now built
  beside the live one, checked file for file against its source, and moved into place by rename;
  the old copy is moved aside first and deleted only once the new one is in. That leaves one
  interruptible instant, between two renames rather than inside a copy, and a run repairs it
  automatically on the way out and again on the way in — so the folder is the previous good copy
  or a verified new one at every instant, with exactly one copy of the mod in it and nothing
  beside it. #153.

- **A queuer blocked on the Windows client is told the holder's age, not just its name.** `flock`
  handles a holder that dies; one that is *wedged* holds the one headed client indefinitely, and
  the metadata beside the lock said only when it started — so a refusal at 3 a.m. named a run and
  left "is it working or stuck?" to a human going and finding the process. Every refusal and every
  queue notice now carries two lines derived at the instant of asking: `age=`, how long the holder
  has had it, and `holder=`, whether the pid in the block still has the lock open. Where the block
  cannot name a holder — its pid has gone, or a child inherited the descriptor and outlived the
  parent that deleted the metadata — a `lock_held_by=` line sweeps `/proc` and names the pids that
  actually have the file open, which is the process to kill. The durable records carry the same on
  one line: `run.sh`'s `failure_detail` and the pool's `refusals.log` now quote the holder's own
  words rather than a path to a file the holder deletes on release. Derived rather than refreshed
  on a timer, deliberately — a heartbeat on this lock would be a background process writing about
  the liveness of the thing that spawned it, and would keep the timestamp fresh for a holder that
  no longer exists. The slot locks got the same lines from the same code. #153.

- **The slot pool's last four bulkhead leaks are walled.** A `kill` aimed at `just regress` —
  unlike a Ctrl-C, which the terminal delivers to the whole tree — used to reach the worker
  subshells and stop there, leaving up to N engines bound to the run's slot ports with nobody
  owning them, and then to *resume* the interrupted wait and go on scheduling probes onto slots
  it had just released; a signal now ends every flight through its watchdog, so each `run.sh`
  tears its own world down, and the pass exits `infra_unavailable` with a durable refusal line,
  because a run stopped from outside measured nothing. The reclaim's kills aim at a process
  rather than at a pid: each swept number is bound to the process's start time and re-checked
  immediately before every signal, so a number recycled between the sweep and the kill is left
  alone instead of `kill -9`-ing whatever inherited it. The install farm no longer reads the
  paths a hand run stages — it skips `mpmissions`, `@cti` and the shim at the copy instead of
  breaking them back out afterwards, so an unrelated `just probe` rewriting slot 0's install can
  no longer turn a pool's bring-up into `infra_unavailable`. And `--wait` queues in a loop: the
  wait establishes only that the client lock was free when it looked, and a third agent taking
  it in the gap used to turn a caller who had asked to queue into a refusal on the second
  contender it met. #151, from #140.
- **A starved machine can no longer forge a probe's class.** Twice, memory starvation arriving
  *after* admission — another agent's corpus, or the OS itself sickening — typed its verdicts
  `timeout` and `node_crashed`: false reds about the code under test, wearing classes whose table
  rows send the reader to the wrong response. A starvation watch now polls the same substitutable
  memory reader as the admission and between-probes readings, and a reading under the 512 MiB
  running floor with a probe in flight stops the pool and the flight: the probe is typed
  `infra_unavailable` — stop, not a result — above every other reading of its run, including a
  recorded pass. Completed verdicts stand. The one sanctioned interruption of work in flight,
  because a starved flight's result is already a non-result wearing a plausible class. #182,
  ADR-0055.
- **Failed pool evidence outlives the run that produced it.** Pool-directory pruning was
  count-only, so the starvation episodes' primary RAM traces were pruned while the issues that
  needed them were still open — only the numbers quoted into the issues survived. `pool.json` now
  records the run's `worst_class`, and the runner prunes only pools whose record reads green, to
  the last five; a failed pool, a torn record, or a run that died before its merge is kept. #182.
- **The regression tier's residual failure paths are typed, and its exit codes stop lying.** A
  `run.sh` the machine killed (an OOM kill above all) is now `infra_unavailable` with the signal
  named, not a "fix the harness" red; an in-mission class typo (`class=timout` — or a smuggled
  `class=pass`, which would have read back as a green verdict) is caught where the line is first
  read, in the class table's Python home; a mistyped flag exits 64 instead of `timeout`'s exit
  code; an unknown worst class exits as the harness bug it is instead of an undocumented 9; a
  failure after slots are acquired (a failed install prep, an evidence directory that cannot be
  created) emits a typed verdict and runs teardown instead of dying untyped with `.info` files
  left behind; a memory reading that fails mid-run says so instead of recording "0 MiB
  available"; a client-lock-blocked tail's evidence outlives the holder that caused it; and every
  pre-flight refusal leaves one durable line under `~/.arma-cti/runs/refusals.log`. #147.

- **The AI Commander no longer unpicks a Squad from a committed assault when its picture of the
  Base flickers.** The force an Assault had to bring was re-derived from the Contact's band every
  cycle, and in-world the band flickers — a leader standing on the Base can lose sight of the
  garrison for one sample — so a committed Squad was re-tasked to a defend twenty seconds after
  being ordered in. A committed assault now carries hysteresis (human ruling, 2026-08-04): the
  Squads already standing under an Assault floor its demanded mass, so the picture may raise what
  an Assault brings and never shed force the Commander committed. Still releasable — a genuinely
  lost assault declines and retreats exactly as before, and a materially better plan clears the
  standing-Order margin as ever. The Commander's trace says when the floor held the number up:
  "1 wanted, 2 committed". #181.

- **The daemon readiness poll stops writing bash errors into the run it is timing.** `grep -c`
  prints its count *and* exits 1 when it matches nothing, so `$(grep -c … || echo 0)` put a second
  line after a substitution that already held one and handed the arithmetic `0\n0` — an untyped
  `syntax error in expression` on stderr for every turn of the poll before the daemon came up, in
  the harness whose own failure-class table calls an untyped red a harness bug. The count now
  lands in a variable before anything reads it, and the fallback it replaces no longer folds "the
  log could not be read" into "the count is zero": that case is `infra_unavailable` naming the log
  it could not read, rather than 90 seconds of spinning reported as a daemon that never said it
  was ready. The restart path's counting is unchanged — it is what tells the second daemon's
  readiness line from the first's. #192.

- **An empty probes directory is a refusal, not a phantom corpus.** Without `nullglob`,
  `spike/regress.sh` read an empty `spike/probes/` as one probe named `*` and the "no probes"
  refusal never fired; it fires now. #162.

- **A keepalive RPC that fails twice reports both failures.** The shim discarded the cached
  connection's error the moment it decided to reconnect, so when the reconnect also failed the
  caller saw only the second error and lost what the cached socket actually died of. Both now
  arrive in the one error payload. #162.

### Changed

- **Two standing rules keep their behaviour and gain the reason the plan-currency
  measurement gives them.** The ban on extra verification passes was a quality rule; it
  is now also a first-order cost rule, because an extra pass is pure generation and
  generation is the act this plan meters. And the implementer seat's effort default,
  lowered from xhigh to high on 2026-08-05, gets its rationale recorded after the fact:
  effort multiplies output volume, output weighs 33.10 points of a five-hour window per
  Mtok against under 0.0096 for a cache write, so it is plausibly the largest single
  spend intervention this project has made — and one that registers as approximately
  nothing in the input-equivalent currency the older ranking used. No new rule was added
  to `CLAUDE.md` from this ruling: the file is itself read as cache, and cache reads are
  precisely the term the measurement leaves unresolved between nothing and most of the
  meter.

- **Reading a finished corpus verdict is no longer tied to a seat, and the thing that
  decides whether a reader is any good is now written down: paste, never retype.**
  #219's A/B put five seats from haiku/low to fable over eight replayed pools weighted
  toward reds and not-a-result stops, and across 40 scored readings not one worst class
  was misread, not one `infra_unavailable` was taken for a result, and no arm would have
  landed on a red. Every failure was the same mechanical act — retyping `just verdict`'s
  output instead of quoting it, twice producing an evidence path that looks right and
  resolves to nothing. So no fifth seat was ratified, the rule lands instead, and it
  lands in both places a reader meets it: `CLAUDE.md` and `just verdict`'s own recipe
  comment. The orchestrator reading is not deprecated, and `cti-recon` stays out of the
  landing branch by being read-only.

- **A wait that genuinely cannot be decomposed now has one sanctioned route, and the
  rule around it stopped arguing from a price this plan does not charge.** An agent
  facing such a wait may dispatch it as a session on `claude-native`, with `just watch`
  armed at dispatch and the result read from the ledger — a detached session that nobody
  is watching is explicitly not the sanctioned shape, because the monitoring burden moves
  rather than vanishing. The interim that forbade any fallback is lifted. The rule's
  stated reason changes with it: #218's A/B pushed 104.6 M cache-write tokens through 128
  byte-identical sessions and moved the plan meter zero points, so the cache arithmetic
  the rule used to rest on is worth about 0.0015 points of a five-hour window, and what
  survives is that an agent which has ended cannot stall — 226 measured subagent stalls,
  eleven caught only by an external watcher. The retired figures are kept as history in
  `docs/research/token-efficiency.md` §2, where they are still correct on an API key.
  Keepalive turns stay barred, now on the same correctness ground rather than on cost: a
  keepalive is the stall shape wearing a timer. `.claude/hooks/deny-subagent-waits.py`
  keeps its 240-second threshold and its measured corpus p90, and rewrites the remedy it
  offers — four routes now, the fourth being the dispatched session with its condition
  stated, because a denial is read at the moment of the decision and one arguing from a
  retired cost model teaches the wrong model to every agent it denies.

- **`just land` is now the only pre-approved way to push.** `.claude/settings.json`
  allowlists `just land` and `just land --dry-run`, and the raw `git push origin HEAD:main`
  entry is gone. The trap the old prose warned about — pushing the local `main` branch a
  detached worktree is not on — is unreachable through the recipe, whose refspec is a
  constant no argument reaches, so removing the raw entry makes that unreachability real
  rather than advisory. `CLAUDE.md`'s landing bullet shrinks to a pointer; the reasoning
  survives verbatim in `tools/land.py`'s module docstring and the justfile comment, which
  is where someone asking why the recipe exists will be. When `just land` itself is broken
  a raw push now needs a permission prompt, which is the right moment for a human to see
  it.

- **An agent that would wait more than five minutes now ends instead, and the machine stops it
  from doing otherwise.** The rule that a turn does not block for five minutes was seat-blind; it
  now splits, because the two seats do not have the same cache. A subagent requests the
  five-minute TTL on 100% of its writes and a main session the one-hour one, measured across
  18,712 turns, so a subagent facing a foreseeably long gate commits, dispatches it detached, arms
  the watcher, writes a handoff and *stops* — being woken later is the single most expensive
  pattern in the measurement, 201,326 input-equivalents against 24,554 for a successor starting
  cold — while the orchestrator, whose cache read is still 302,183 after half an hour, holds the
  wait. "Foreseeably long" is not left to the agent, which cannot see its own cache economics: it
  is a measured list in `.claude/hooks/deny-subagent-waits.py`, which now denies the unfiltered
  regression corpus in a subagent's foreground alongside the sleeps and poll loops it already
  denied. The corpus measured a p90 of about 1,230 s over the runs recorded on 2026-08-04/05, with
  its fastest unfiltered pool at 793 s. `just regress --list` runs nothing and passes, a named or
  `--issues` selection passes, and the same run dispatched detached passes — the denial names each
  of those. The exception list ships empty and grows only at a retro. No gate moved, no window
  widened, no assertion changed: this changes when a result is read, not what it says. Human
  ruling 2026-08-05 on #204, on #203's measurement; #200, #205.

- **Two surfaces stopped introducing themselves as throwaway Phase-0 scaffolding, and the spike
  world's stay of execution is written on the world itself.** `spike/run.sh` called itself
  "throwaway measurement scaffolding" that "Phase 1 replaces", having since become the runner every
  in-world gate goes through; its header now says so and points at where the callers can be read off
  rather than listing them. `missions/spike.Stratis` was recorded in two places as "run by nothing",
  which the command-port audit's own last exit-criteria bullet already contradicted — `just spike`
  boots it through `spike/run.sh`'s defaults, so deleting it would have broken a live recipe. It
  stays, its `description.ext` now carries why and when it goes (ADR-0011, Phase 3), and both stale
  claims are corrected to point at the derivation. No behaviour changed anywhere. #165, #158 (F8).

- **`just fast` returns in about a minute and a half instead of seven.** The Python tier runs
  under `pytest-xdist` at one worker per logical CPU, and the same 1,410 tests that took 6 min 22 s
  serially take 56 s. Nothing about what they assert changed: the tier's wall clock was six times
  its user CPU, so it was waiting on locks and bash subprocesses rather than computing, and the
  workers take up that slack. The one test that could not be shared out — a background child that
  had to outlive its run — turned out to be waiting sixty seconds on a descriptor its claim was
  never about, and now settles in a third of a second while still catching the bug it was written
  for. This is the change #195 measured as the largest recoverable waste on the recipe side: a gate
  that outlives the five-minute prompt-cache TTL makes the next agent turn pay to rebuild its whole
  context, and `just fast` had crossed that line on every invocation. #197, #195.

- **Dying costs 30 seconds, at your own Base.** The played mission's respawn timer moves from 5 s
  to 30 s (ADR-0052, ruling 6) — a playtest-tuned placeholder in ADR-0020's sense, documented at
  the line that sets it, so play can move the number without reopening the decision. Where you
  come back was already settled and unchanged: your own Base, no Funds cost, no location choice.
  The phase-0 spike world keeps its 5 s; it is not the mission anyone plays. #189.

- **The pool's merge is decided in Python, not bash.** The regression runner's merge — the
  dead-slot rule, client-lock-blocked typing, the mem-stop overlay, worst-class ranking — and the
  `pool.json` it writes were hand-rolled JSON on both sides: a `printf` writer, an
  indentation-dependent `sed` reader, and a byte-grep pruner, each coupled to the other's exact
  rendering. They are now `tools/pool_merge.py` under `just unit` (ADR-0049's third migration),
  the fallback `verdict.json` a failed typer implies has one writer, and the shell keeps the
  acting: releasing dead slots, deleting pruned passes, exiting the worst class. A merge that
  cannot run fails closed to `infra_unavailable` rather than open to a green pool. #185.

- **The daemon's domain seams tightened along the second DDD pass's low-severity findings.** The
  port now asks the Campaign the two Squad questions it used to read off the roster directly, and
  its test-only `ledger`/`outbox` pass-throughs are gone, so its surface is judgement only. A
  Campaign refuses a Ledger opened at any figure other than its table's `starting_funds`. What a
  Command or an Effect carries is fixed at construction, so an Effect on the outbox can no longer
  be edited between push and delivery. The telemetry `side` column now carries its provenance
  beside it — `side_source` says whether the row holds the gateway's stamp or the payload's own
  claim. And the wire budget's worst case takes the widest side name from `SIDES` rather than
  hardcoding `WEST`, so a longer side name widens the budget by itself. No wire change anywhere.
  #152.

- **`spike/run.sh` refuses a second command-line argument instead of silently dropping it.** A
  mistyped invocation used to run in a mode the caller did not ask for; it is a usage error now,
  exit 2, with nothing brought up. #162.

- **`just regress --slots 1` is the serial tier byte for byte, as its header always claimed.**
  Pool slot 0 wrote engine profile `ctispike0` and headless-client profile `ctihc0` where a hand
  run writes `ctispike` and `ctihc1`; slot 0 now keeps the hand tier's own names, the way it
  already keeps `~/arma3server` and ports 2402–2406. Slots 1+ renumber their headless-client
  profiles to `ctihc2`… with them. #162.

- **Each seam the pool libraries had triplicated has one home.** The host guard's
  free/running/unavailable → verdict ladder ran as three near-verbatim bash copies across the pool
  libraries; it is decided in `tools/host_guard_verdict.py` under `just unit` now (ADR-0049's
  second migration), and a guard whose mapper cannot run fails closed to a stop rather than open to
  a pass. The lock holder's `.info` block and the `infra_unavailable` exit code — each defined in
  three files — have one sourced home each, the hand-run tier lock takes slot 0 through the same
  acquire the pool uses, and `run.sh`'s duplicated verdict sweep — the two-copy structure behind
  #83's misclassification — is one function on both paths. #161.

- **Two daemon hot paths shed rebuilt work.** Dispatch looked its handler up in a verb table
  rebuilt on every request — the shape #90 already removed from the port — and a `poll` re-encoded
  the whole candidate reply once per pending Effect, so pricing one drain read the backlog
  quadratically. The table is now built once, and a drain is priced incrementally, to the byte the
  full encoding gives. The wire is byte-for-byte what it was. #156.

- **The daemon now reads its own Command catalogue instead of restating it.** The catalogue claims
  a Command the game can build and one the daemon accepts cannot drift apart, but the daemon's own
  validation never read it: the handler table restated the verb set, each handler restated its
  Command's arguments, and the five Effects the daemon pushes were held to the declared effect
  schema entirely by hand — so a verb or argument changed on one side landed as an in-world
  discovery. The handler table and every handler's argument reads are now pinned to the catalogue
  by unit tests, and the outbox refuses any Effect whose name or arguments the catalogue does not
  declare, at the one door every world effect leaves through. The wire format is byte-for-byte what
  it was. #145.

- **What a probe's outcome means is now decided in Python, not bash.** The regression runner's
  typing ladder — the watchdog rule, the untyped-red rule, `expect:` inversion, quarantine — and
  its hand-rolled `verdict.json` heredoc were sixty lines of shell, testable only by a bring-up;
  they are now `tools/probe_verdict.py` under `just unit`, so a wrong class is a red unit test
  rather than an in-world discovery. First instance of the standing policy (ADR-0049): non-trivial
  logic lives in Python under pytest, bash keeps the process seams — launching, `flock`,
  environment, timeouts — where the shell is the actual subject. #171.

- **The addon's side vocabulary has one home.** The side-name↔engine-side pairing was restated by
  hand five times across the addon — two switches, a hand-built enemy-of table, a `str` respelling,
  and a membership literal in the presence sampler that was fail-silent: presence on a side the
  literal did not list was simply never reported, and nothing asserted on the gap.
  `cti_fnc_sideVocabulary` now owns the pairing — the names come from the exported schema's
  `sides`, the engine objects are the one half SQF must own — and derives both directions and the
  enemy-of relation once, refusing whole rather than translating in part; the five sites read it,
  as does a sixth born since the finding (`fn_baseAssault`'s destroyed-by attribution). What the
  daemon sees on the wire is unchanged. #149.

### Fixed

- **A squad effect short of a declared argument is refused instead of guessed at.** The world's
  effect receiver used to answer a `squad_spawned` or `squad_reinforced` arriving without `size` by
  inventing an 8-man strength — a number appearing nowhere in the economy the daemon charged
  against, on a fact the daemon owns. The receiver now holds a squad effect's arguments to the
  declared catalogue the daemon's own door already enforces, read from the exported schema rather
  than restated in SQF, and refuses the malformed document with a typed verdict the pump
  dead-letters. #159.

- **The Commander's map picture is readable in the three ways playtest 0001 said it was not.**
  Clicking the map now draws a yellow selection marker on the Place the click named — the answer
  used to live only in the hint's `Place:` line — and a click on open country removes it, because
  open ground deliberately selects nothing. A Squad's marker text and a Contact's no longer print at
  the town centre, which is exactly where the engine prints its own town name, so all three stacked
  into one unreadable pile at every Place: Squads now sit north of the label, Contacts south, and a
  second Squad at the same Place steps further north instead of overprinting the first. And a
  Squad's strength finally has a denominator — `rifle 4/8` instead of `rifle/8`, where the 8 is the
  establishment strength read from the same catalogue the price comes from rather than a number
  written down again in SQF. All of it is presentation on `cti_fnc_mapRender`; the Observation on
  the wire is untouched. #174.

### Added

- **The Commander is now told when ground changes hands and when one of his Squads is wiped.**
  Playtest 0001's summary judgement on the seat: orders went out and nothing came back until the
  map's picture silently differed. Both moments now raise a notification on the Commander's screen
  in the shape Arma's own singleplayer task notifications take, visible with or without the map
  open — an Objective changing hands is named with its new owner (going CONTESTED announces itself
  the same way), and a Squad reaching zero men is named once, not re-announced on every 5 s push.
  Read client-side off the difference between consecutive Observations, so the wire, the mode=1
  whitelist and the AI Commander's inputs are all untouched. Wording and look are a playtest-tuned
  placeholder. #176.

- **A playtest session now has an observer mode: press Y to fly free, press Y to come back.**
  Playtest 0001's feedback stopped at what the Commander's map shows, and the live workaround — a
  camera typed into the debug console — left the map unreachable and the incantation to remember.
  Any session booted on a `spike/playtest/` fixture now assigns the human a Zeus-style curator: the
  engine's own keybind toggles a free-fly camera that spawns no unit and changes nothing the AI can
  perceive, and leaving it lands back in the body the Commander's map is one keypress from. A camera
  with no edit rights, deliberately — no addons, nothing editable, every curator action disabled;
  map markers are the one power the engine keeps free. The regression corpus stages none of it. #178.

- **The Observation a Commander plans against is now a declared wire shape rather than a
  convention.** It was the last family whose two sides were mirrored by hand: the daemon named the
  document's keys as literals in `serialise` and read them back as literals in `parse`, and the map
  UI read them as a third set of literals in SQF — so renaming a Squad's `type` or a Contact's
  `echelon` failed nowhere until a Play Session, on the human's own path. The names are declared
  once in `cti_daemon.observation`, exported into `command-schema.json` beside the inbound report's
  shapes, and the map functions' literals are held to that export by `just unit`. The wire itself is
  byte-for-byte what it was. #163.

- **The daemon can be booted on hand-authored files without editing its source.** Which economy
  table, which manifests directory and which map a daemon plays on have been arguments since #76,
  and nothing could reach them from a command line, so booting a fixture Campaign meant editing the
  composition root. `--economy`, `--manifests` and `--map` now say so directly, defaulting to
  today's authored files, and a map id no manifest in the directory describes is refused in words
  naming both the id and where it looked, rather than a traceback. #164.

- **A delegated decision can no longer land without saying what would overturn it.** ADR-0019 has
  required that section since the day it retrofitted ADR-0015 for missing one, and nothing checked:
  three ADRs reached a guided review of all twenty-nine delegated decisions without it, found only
  because one sitting read every one of them. `just check` now runs `tools/check_adr_form.py`, which
  asks of every ADR carrying `Delegated-decision: yes` that it name its overturning evidence and
  carry the human's `Reviewed-by-human:` review-state line. The three — 0016 on pulling the
  regression tier forward, 0030 on charging the Observation's budget to the map, 0036 on freezing
  the world when the daemon's identity changes — now state theirs. #137.

- **The recall a human signed off is now something the world has been seen to do.** ADR-0031 grew
  the recall radius from 160 m to 1.15 km and named what keeping your own ground is worth; both
  numbers were approved on a 200-seed sweep and neither had ever happened in a running world,
  because no company had ever stood on ground a side held. A new probe stages exactly that — WEST
  holding three Objectives, its Squads marching, and enemy riflemen appearing on the held ground in
  numbers its own leaders have to acquire — and watches the Order that comes back. A platoon is
  ignored for forty-five continuous seconds; a company turns a marching Squad round inside two, from
  a Squad measured a kilometre off the ground it is recalled to. Nothing tells the daemon the men
  are there and nothing asks for the Order. #104.

- **A playtest can start in the middle of a Campaign instead of at its opening.** Half of the first
  playtest's half hour went on reaching a board rather than playing one, because a fresh Campaign
  was the only thing that could be booted. A committed fixture now plays the Campaign into a named
  mid-Campaign state before handing it over — WEST holding three Objectives with a Squad standing on
  each and EAST massing a kilometre off the front — and every part of that state is reached through
  the door the game uses: Squads Purchased through the Command Port, ground captured by standing on
  it, Orders issued through the port, Funds whatever the Campaign says they are. It refuses to open
  the play window on a board it did not actually reach, so a brief that names it is naming something
  that was true. Staging costs about forty seconds and the session clock starts after it. #42.

- **A Squad that has taken losses can be brought back to strength, and its own leader can ask for
  it.** Reinforce joins Purchase and Order as a Command: name a Squad standing at your own Base and
  the men who are missing arrive there, costing the missing fraction of what that Squad cost new,
  discounted. The discount, 0.8, is a playtest-tuned placeholder in the authored economy table and
  wants a session behind it before anybody calls it balanced. Ammunition and equipment restock is
  unaffected: it stays free at Base and is not a Command at all. With it, the Command Port gains a
  second principal — until now every Command came from a side's Commander, and a squad leader may
  now issue Reinforce for the Squad he actually leads, checked on the server against who the engine
  says is leading which group rather than against anything the client sends. Reaching for another
  Squad is refused `not_your_squad`, and Purchase and Order stay the Commander's. A leader can do
  this while both sides are under AI command, which is the MVP's second mode. ADR-0040.

- **The world is now proven to see the enemy standing on your ground.** Every in-game run so far
  had put NATO units on the ground and nothing else, so that the presence sampler reports a CSAT
  squad at all — and reports it as CSAT rather than as nobody — was assumed. If it had been wrong,
  an Objective held by the enemy would have read as empty, never contested, never changed hands and
  kept paying its old owner, with every unit test still green. The in-world probe that already
  watches an Objective change hands now watches it go Contested with both sides inside the radius,
  and then fall to the side left standing there.

- **The audit that Phase 1 exists to produce: no path outside the Command Port.** Every way an
  Order, a Purchase or any other change to strategic state can reach the world is now enumerated in
  `docs/command-port-audit.md`, each with the gate that holds it — one whitelisted function for a
  client, one extension call for the server, one dispatch and one lock in the daemon, one root for
  human and AI Commands alike, and one applier for effects coming back. Three things outside that
  envelope are named and justified rather than left to be discovered, and the holes the audit found
  are written down beside them.

- **The integration demo runs as one thing.** The probe that drives a real client in a Commander
  seat now does it in a world where the other side is being played by the AI Commander, so a single
  world holds both kinds of Commander for the first time. Recorded with it: taking over a side means
  bringing the world up with that side free, because one side has one Commander whichever kind it
  is — there is no handover, and the probe asserts the refusal rather than describing it.

- **The in-world regression tier runs three worlds at once, and a full pass costs eleven minutes
  instead of twenty-six.** `just regress` now schedules the corpus across a pool of slots — a slot
  being a port block, a daemon, a server install, an engine profile and a world that agree — with
  the longest probe started first so no slot idles behind the tail. `--slots 1` is the serial tier,
  unchanged and still correct: slot 0 is the install and the port block the tier has always used, so
  the fast path and the known-correct path are one code path at different N. The two probes that
  drive the Windows client run last and one at a time, because there is one Windows host and the
  guard that protects a live play session cannot tell our client from the human's. A probe that
  fails is a verdict rather than a stop for its siblings; a slot whose worker dies is reported as
  not-a-result and cleared rather than read as a red. Measured: seventeen probes, seventeen passes,
  646 s against 1,599 s serial, peaking at 7.3 GB of tier processes with 1.0 GB still free.

- **A daemon that restarts mid-session can no longer reset your Campaign behind your back.** The
  daemon holds the whole Campaign in memory, so a restart is a factory-fresh Campaign; the shim
  reconnects without saying anything, and nothing in the protocol distinguished one daemon from the
  next. So a mid-session restart repainted every Objective NEUTRAL, put Funds back to the starting
  balance, restarted the Domination clock and turned every Squad you had bought into an orphan that
  kept fighting and would not take Orders — with nothing on screen and one line in a log nobody
  watches. Every reply now carries the identity of the process that gave it, the world latches the
  first one it sees, and a change stops the world rather than letting it play on: the map is left
  showing the last thing that was true, no Command spends Funds that no longer exist, and every
  screen says CAMPAIGN LOST and to restart the mission. Surviving a restart is a later thing
  (Phase 2); being told about one is not. ADR-0036.

### Fixed

- **A Squad bought once is spawned once, even when the wire hiccups.** The game applies an effect
  and only then tells the daemon it has, so an acknowledgement lost on the way back leaves the
  daemon holding the effect and handing it over again on the next poll — which is the design, and
  every effect but one survived it. A repeated Squad spawn did not: it stood a second full Squad on
  the map, pointed the roster at the new one, and left the first group's men on the ground answering
  to nobody — alive, still fighting, reachable by no Order, counted by neither the world nor the
  daemon, and there for the rest of the session. The Campaign said nothing about any of it. The game
  now recognises a Squad it has already spawned and treats the repeat as the redelivery it is,
  saying so once in the log with the sequence and the Squad id. #141.

- **A wedged Arma-tier run now frees its slot instead of holding the pool until a human notices.**
  The tier's own timeout mechanism could fail open. Every deadline in `spike/run.sh` was computed
  through `bc`, and without it `(($(echo … | bc)))` compares an empty operand, which is false — so
  the deadline never fired and each wait ran until the process it watched happened to die. The
  deadlines are bash integer arithmetic now, over bash's own clock, and a run that cannot compute a
  bound refuses at the pre-flight as `infra_unavailable` rather than running without one. The three
  unbounded calls around them are bounded too: the WSL interop calls the play-session guard and
  teardown make, whose wedging is a known failure mode of this machine; every `uv run` the harness
  makes; and teardown's wait for a child it has just killed. Above all of it, `just regress` now
  runs each probe under a watchdog — the probe's own window plus ten minutes for bring-up and
  teardown — and kills the process tree of a run that blows it, typed `infra_unavailable`, which is
  not a result and gates nothing. The watchdog sits above the window and never inside it: a probe
  that outran what it measures is still the `timeout` its own harness typed. #144.

- **Four validators now refuse in their own words rather than through whatever exception fell out
  first.** A manifest whose `position` was not two numbers, or whose `adjacent` was not a list of
  ids, passed the key checks and then raised a bare `IndexError` or `TypeError` from deep inside the
  loader — past the one error type every caller of that module catches — so an authoring slip read
  as a crash rather than as a sentence naming the field and what it costs. `--ai WEST:--5` slipped
  through a sign-stripping digit check and drew argparse's generic complaint instead of the seed
  refusal written for it. Two Campaigns ending on the same condition in the same in-game second
  wrote the same archive filename, and the second silently replaced the first — the record of a
  played Campaign lost to a name; the name is now claimed rather than assumed, and a taken one steps
  aside. And banding an empty sighting returned an empty echelon, a valid-looking band that would
  have put a place on a Commander's picture with nothing standing at it. #155.

- **A wedged daemon now says no instead of quietly collecting a blocked thread per retry.** The
  daemon answers one request at a time and waited on that lock forever, while the transport gave
  every connection a thread of its own with no bound — so a handler stuck on anything, a filesystem
  stall or a planner bug, gathered one more parked thread roughly every two seconds for the rest of
  the session, none of them going anywhere and nothing on disk saying so. A request that cannot be
  reached within 250 ms is now refused with a typed `busy` error, which is inside the shim's own
  500 ms budget, so the world learns the daemon said no rather than guessing it had died. Nothing
  was judged and nothing spent, so asking again carries the request out. Connections that go silent
  for two minutes are closed as well, which is the same pile-up arriving through a half-open peer.
  A healthy daemon is untouched: its requests are three orders of magnitude inside the bound, and
  the wire is unchanged. #142.

- **An outbox that stops draining is visible before it is a session's problem.** Undelivered Effects
  were counted only on a successful poll, which is exactly the row that goes missing in the failure
  that matters: the effect pump dies while income keeps paying and both AI Commanders keep buying,
  and the backlog accumulates in memory all session with nothing written down — a starvation that
  had to be diagnosed from outside the daemon when it happened. Depth is now recorded whenever it
  crosses a band of 25, on the way down as well as up, from the request path rather than the poll.
  #142.

- **A finished regression run hands its slots back the moment it exits, instead of a few seconds
  later.** The pool measures the machine's memory while it works, and the sampler that does it
  sleeps three seconds between readings. Every child of the run inherits the slot locks, so when
  teardown killed the sampler the sleep it had forked survived it holding all three — and a run
  queued behind this one was told the slots were busy by a process that no longer had any business
  with them. The sampler now lets go of every slot before it takes its first reading, since it never
  needed one; nothing else about it changed. An ask for a slot in the first second after a run
  returns was refused five times in five before, and granted five times in five after. #138.

- **An error out of the shim is now always valid JSON, and asking the shim for its address always
  answers an address.** The shim's only escape was rewriting a `"` to a `'`, so any detail carrying
  a backslash — a Windows path out of an io error, most plausibly — or a newline produced a line
  the receiving side could not parse: it would have failed to read the error rather than reporting
  it. Escaping now follows RFC 8259 and leaves everything else alone. Separately, retargeting the
  shim answered `{"error":...}` if a panic elsewhere had poisoned a lock, where the call's contract
  is the address in force and no caller can tell one from the other; the address is a whole string
  replaced in one assignment, so that poison described a panic somewhere else and nothing about the
  address, and it is now recovered rather than propagated. The cached connection is dropped on
  retarget unconditionally, which it was not: a poisoned connection cell used to skip the drop and
  leave the shim answering over a socket to the daemon it had just been moved off. #93.

- **The no-Arma test suite no longer competes with the Arma tier for the machine.** One test that
  drives the harness end to end sends a Windows client, and a run that sends one takes the
  machine-wide lock on the one headed client — for real, because that test alone never moved its
  state directory into a temporary one. So `just unit` quietly took the client away from live
  regression runs for a few seconds at a time, and was refused by them: the refusal is a stop before
  anything launches, and the test then died reading a record the refused run had never written. That
  is the one red in twenty-six suite runs nobody could explain; two suites started at once reproduce
  it every time, with no Arma anywhere. The test now owns its own lock, reports the harness's stated
  reason instead of a bare missing key when a run refuses, and a tripwire fails the suite if another
  test ever reaches for the real one. The pool tests in the same file got the same treatment for
  memory, having gone red about free RAM while a sibling agent's world was up. #132.

- **A regression run no longer launches a world into a slot it failed to clear.** The tier confirms
  that a dead run's leftovers are really gone before reusing a slot, and then the runner threw the
  answer away: a slot whose server and daemon had survived the kill went straight into a bring-up
  that binds those same ports, and the failure came back reading as the world's fault instead of the
  dead holder's. A slot that does not come back clear is now typed `infra_unavailable`, named
  together with the survivors and the ports and install they are still holding, and skipped — the
  run carries on in the slots that were clean, since one dirty slot should cost a slot rather than
  everybody else's results, and the slot's lock is held for the rest of the run so nothing else is
  handed it either. When every slot a run holds fails to clear, nothing was measured and the run
  says so rather than reporting a result. The same applied to a hand run, where slot 0 is the only
  slot there is. #133.

- **A Command now has to say who is issuing it, and the daemon refuses one that does not.** The
  Command Port's audit found that the acting side fell back to whatever side the payload named, so
  anything that reached the daemon's socket without passing the gateway commanded for the side it
  wrote down. The gateway stamps the caller's side alongside his Squad now, and a Command carrying
  no stamp is refused `unknown_caller` — a new refusal in the same vocabulary every other one comes
  back in. Nothing a player does changes: a Commander's Command was always stamped from the
  server's own assignment state. What changes is that the stamp, rather than the socket, is the
  door. #128, ADR-0044.

- **The daemon no longer puts its socket on the LAN for the sessions a human joins.** It bound
  every interface whenever the world was held up for a client, on a Phase-0 reason — the
  measurement mission's clients called the daemon themselves — that the shipped mission has never
  had. The daemon now refuses to listen anywhere but this machine's own loopback, and says so and
  exits rather than starting somewhere it should not be. The socket stays unauthenticated by
  decision, with the reasoning and the evidence that would overturn it written down. #128, ADR-0044.

- **The build no longer carries the tool that can hand WEST half the island.** The desync
  investigation's load generator spawned thirty-two soldiers onto the first four Objectives; it was
  off unless asked for, and present in every build regardless, including one a person could play.
  It now lives beside the harness and is copied in only by a run that asks for it, so a build a
  human plays does not contain it at all. The tool itself is unchanged and the investigation still
  has it. #128, ADR-0045.

- **Clearing a dead run's leftovers now waits for them to actually go.** `kill` returns when the
  signal has been posted, not when the process is gone — it still holds its ports and its install
  until the kernel tears it down — so reclamation sending `SIGKILL` and returning reported a slot
  clear that was not, and the next thing to run was `run.sh` binding those very ports. It now
  confirms the hard kill the way it already waited out the polite one, names anything still in the
  process table afterwards, and reports a failed reclaim rather than a cleared slot. The same
  misreading, on the other side of a death, is what made `test_a_dead_holders_lock_frees_itself`
  flaky twice over: `flock` frees on the *last* descriptor closing, which is not the event
  `proc.wait()` returns on. Measured here at up to 7.4 ms of daylight between them on a loaded box.
  The test now waits for the observable it means — every descriptor on the lock closed — and then
  asserts the kernel's promise in a single non-blocking ask. Acquire is deliberately left
  non-blocking through that window: a grace would let the test pass on the grace rather than on the
  kernel. #130.

- **A regression run no longer starts into a machine that has no room for it.** The slot locks
  serialise agents but say nothing about memory, so two three-slot pool runs took six worlds onto
  one 12 GB machine, drove it to 39 MiB available, and came back twenty minutes later with two
  worlds alive but starved — a loop silent for four minutes, reported as a crashed node, which
  reads like the code's fault and is not. The pool now takes a memory reading before it takes a
  lock, in the same fail-closed shape as the guard that protects a live play session, and answers
  in one of three ways: run, run in fewer slots and say so, or refuse with the reading and launch
  nothing. The floor is `N × 2,500 MiB + 1,024 MiB`, and both numbers come from what the tier has
  actually been measured using rather than from arithmetic. It is re-asked between probes too, so
  somebody else arriving at minute eight stops the pool taking new work instead of starving what is
  already running, and `--wait` queues on the machine the way it already queued on the locks — a
  full machine is somebody else's run as surely as a held lock is. #125.

- **The Arma tier's own test suite no longer fails one full run in two.** The test for the property
  the whole slot design rests on — the kernel frees a dead holder's lock, with no reaper and no
  pidfile — killed only the top of the holder's process tree and then raced its own child. It was
  the test that was wrong, but the thing it was wrong about is real: half a dead holder keeps the
  slot, because the lock is freed by the last descriptor and not the first. So the case is now
  asserted rather than raced, and a run that finds every slot busy prints the pids actually holding
  each lock beside the metadata — which otherwise names the dead parent and sends the reader after
  a process that no longer exists. #121.

- **The Campaign's end-to-end probe no longer stages its own ambush.** `campaign-end` shortens a
  4.4 km march by putting the assaulting Squad 250 m from the enemy HQ, after waiting for the
  defenders to leave. The wait watched a 400 m ring around the HQ and the Squad lands at 250 m on
  the one road out — so "clear" could mean an enemy Squad standing 150 m in front of where eight
  men were about to appear. On one run in six they appeared, turned round, spent three minutes
  winning a firefight the probe had created, never reached the HQ, and the run timed out on an
  assault it had itself prevented. The wait now covers the approach as well as the HQ, and the
  timeout reports the closest range the Squad reached, which is the number that tells "it never
  set off" apart from "it arrived and the assault failed". #106.

- **Two agents testing at once no longer fight over the one Windows client.** The regression pool
  ran its two client probes last and one at a time, which ordered them against the rest of its own
  run and against nothing outside it — so two runs starting from sibling worktrees each drained
  their own pool and then both drove the single headed client on the single Windows host. Each read
  the other's client as a live play session and stopped, and on a tighter race they would have
  joined two worlds through one engine profile. The client leg now takes a machine-wide lock for as
  long as it holds the client, and a second run either queues for the time it was told it may wait
  or is refused and shown whose run it is behind. The guard that protects a real play session is
  unchanged and still refuses to tell one client from another; what the lock adds is that a client
  nobody has claimed is the human's, which is the only case worth stopping for.

- **Running the no-Arma tests no longer kills whatever the Arma tier is running.** The pool's own
  unit tests drive the real `spike/regress.sh`, which reclaims each slot it acquires by killing
  whatever holds that slot's ports or runs out of its install. The tests moved the locks and the
  install into a temporary directory, but a slot's port block is arithmetic no variable moves — so
  a `just unit` on this machine swept 2402/2502/2602 and 9099-9101 and killed a live pool's three
  worlds and their daemons mid-probe, leaving no error line, no dump and a green re-run. Reclaiming
  now asks first whether it is the machine's tier at all, and a run pointed at another state
  directory kills nothing on it. #124.

- **A Campaign can no longer buy its way past what the wire carries.** Nothing bounded a side's
  roster, so a long Campaign with hoarded income could legally buy the Squad whose arrival takes the
  Commander's view past the engine's 10,240-byte return — after which the engine truncates in
  silence, the view stops repainting, and the session degrades every cycle with the cause hours
  behind it. A Purchase that would cross the limit is now refused at the port like any other rule,
  in words a Commander can act on. The number is measured rather than chosen: it is the point at
  which this map's worst-case Observation stops fitting one reply, so a bigger island — which pays
  for its own size in Contacts — gets a smaller one without anybody deciding.

- **One effect the world can never carry out no longer stops the Campaign.** The pump stopped at the
  first effect that failed to apply and retried it every two seconds forever — correct for something
  a later poll could clear, wrong for an effect name this world does not know, a side that is not
  playing, or a side with no Base, none of which any amount of waiting fixes. Everything behind it —
  Squad spawns, Orders, the end of the Campaign itself — never arrived, with both sides' Funds
  already spent and nothing on screen to say why. A refusal is now classified where it happens: a
  permanent one is dead-lettered — a typed failure line in the world's log and a row in the
  Campaign's telemetry — and the queue moves on, while a transient one still waits, and a queue that
  has not moved in three minutes says so whatever the classification claimed.

### Changed

- **What a Squad is made of is now authored data rather than a classname buried in the addon.**
  Every Squad spawned into the world was eight copies of one of two hardcoded soldier classnames,
  and the `squad_type` the Commander had paid for was written to the log and then ignored — a rifle
  Squad and a weapons Squad were the same eight men. Composition is now an ordered roster of unit
  classnames per side, authored in `config/economy.json` beside the price it was set against,
  validated by the schema source, and exported into `command-schema.json` on the route ADR-0017
  lays down for authored data. `fn_effectApply` reads the roster and holds no classnames, so a
  Reinforce refills a Squad from its own composition instead of from a literal, and the men the
  world puts on the ground cannot drift from the table the daemon charged for them. The values are
  deliberately today's: the same classnames in the same numbers, so in-world behaviour is unchanged
  and this is the seam and not a balance change. Filling it in is gameplay content and stays behind
  the human's feel gate. #79, #82.

- **Three decisions from the human, recorded where they bind.** Mid-session Commander takeover is
  out of MVP — a desired long-term feature, up to hot-swap with elections and evictions, but a
  session is still joined as Commander at bring-up (docs/mvp-scope.md, #126). N=3 is confirmed as
  the regression pool's default now that its RAM extrapolation has been measured true (ADR-0028,
  #125). And the Reinforce discount of 0.8 is explicitly held for playtest judgement: the first
  playtest brief gains a scenario for feeling it out from the Commander's chair (#123).

- **A machine-locality check now exists only where it can fire, and can no longer refuse in
  silence.** The addon carried twenty-nine of them — "this function runs on the server, not on your
  machine" — and on the evidence of every call path in the repo only two of them could ever fire,
  because the rest start in the mission's own server-side init. Worse, they refused by handing back
  an empty reading:
  an empty presence map is indistinguishable from "nobody stands anywhere", so a report assembled
  on the wrong machine would have been accepted as a truthful picture of an empty island with
  nothing in any log. Nineteen unreachable checks are gone, each replaced by a sentence in the
  function's header saying why the caller already decides the machine. The ten that remain sit at
  the three real boundaries — the Command Port's door, the two things the server pushes to a
  player's machine, and the seven long-running loops — and every one of them now writes a typed
  failure line naming the function and the machine before it refuses. `just check` rejects the
  hand-rolled form, so the next one written has to be a real boundary or not exist. ADR-0041.

- **Squads are owned by the server for their whole life, and the build now says so.** An Order is
  issued through nine engine calls, one of which — `setCurrentWaypoint` — is documented to work only
  on the machine that owns the group, with four more declaring nothing at all. Handing a Squad to a
  headless client would therefore write its Order and never switch the Squad onto it: an Order that
  looks issued and is not. That every Squad is server-owned was true already but unwritten; it is now
  a rule (ADR-0039), stated under **Squad** in the glossary and enforced by `just check`, which
  rejects `setGroupOwner` anywhere but the headless-client desync diagnostic that predates it.

- **The AI Commander's decision trace says Purchase, the word the rest of the game uses.** Its
  spending rows read `purchase rifle` and "300 Funds purchase no Squad this map sells" where they
  used to say "buy" — the one artefact that exists for a human to read and argue with was written in
  vocabulary the glossary tells everything else to avoid.

- **The rest of the regression corpus now ends when its subject does, and the settles that stayed
  say why in their own probe.** Nine more fixed settles converted to waits on the condition being
  asserted, each keeping its old number as the deadline: eight identical "let the world build" holds
  became one shared wait on the world's own counters and returned in **5.0 s against 20 s, on all
  eight**; the `contacts` probe waits for the overlap between two leaders it needs (1.0 s against
  30 s); `contact-decay` waits for the sighting to actually leave the sample, which records our 120 s
  ageing bound instead of assuming it; `casualties` waits for the men to land, the deaths to
  register and the buffer to reach the daemon. **The first measured full passes of all fourteen
  probes are 23m46s and 23m58s**, against the 26m40s that had only ever been arithmetic — two
  consecutive greens rather than one, because a conversion is the change most likely to introduce a
  flake and this tier never averages runs. Four settles were kept and
  argued for rather than converted — `two-commanders` most importantly, because its 180 s soak is
  the window the largest-observed drain is measured in and an extremum shrinks with its window.
  Converting it would have reported a smaller maximum under the same name, which is worse than the
  settle. The per-probe decisions are in `docs/regression-tier.md`.

- **The AI Commander decides by multiplying considerations through response curves rather than by
  summing eight weights, and a consideration can now veto an option outright.** Each candidate Order
  is normalised to [0, 1] on eight axes, remapped by an authored curve and multiplied, so a zero
  propagates and the evaluator abandons the option — the pattern every serious utility system in
  `docs/research/commander-prior-art.md` uses, and the answer to a scorer where `threat` could make
  ground expensive but never impossible and every axis added diluted the rest. What it plays like is
  meant to be the same: the opening move is still income-bearing ground on every seed, an undefended
  enemy Base is still raided by one Squad, a company at our own Base still turns a Squad round and a
  platoon still does not, and the massing table still sends four Squads at a company and declines
  when it has three. The one behaviour that changed in degree is that a Squad will now be recalled
  to its threatened Base from up to 1.15 km away rather than only from the Base itself. ADR-0031
  carries the reasoning; ADR-0014's four calls survive it and ADR-0027's massing rule is untouched.

- **The decision trace reads differently.** A candidate's `terms` are now the eight considerations
  as factors in [0, 1] rather than signed contributions that sum to the score, `score` is their
  compensated product in [0, 1] rather than a total in income units, margins in `because` carry
  three decimals rather than one, and each decision carries a new `vetoed` count beside `scored` —
  how much of the option space was refused before it was weighed.

- **A map that could never fit its Observation into one `callExtension` return now fails
  `just unit` when it is authored, instead of truncating in silence in a Play Session.** #26 pinned
  the ceiling at about 35 Squads a side and blamed the Squad count; re-measured after the enemy
  roster left a Commander's view (#27) and Contacts took its place (#28), the binding term has
  inverted. Contacts are keyed by place, so an island's size is charged before either side has
  bought anything: Stratis costs 1,611 bytes of a 9,216-byte budget and carries 71 Squads a side,
  a forty-Objective island carries 24, and a sixty-Objective one does not fit **empty**. The budget
  is therefore checked per map rather than per roster (ADR-0030). Nothing in MVP changes — one map
  ships, and it has five and a half times the headroom it needs.

- **A Contact's age is reported in whole seconds.** It was arriving as `47.29999999999927`,
  seventeen characters of binary-subtraction noise on a field carried once per place, read
  downstream as a freshness ratio against a window of minutes — no precision anything could use.
  Truncated rather than rounded, so a sighting can never read fresher than it was.

### Fixed

- **A crashed background loop no longer takes half the game down in silence.** The world runs on six
  long-running threads — effects, income and captures, Commander assignment, the Commander's own
  view, standing Orders, Base assaults — and one scripting error kills the thread it happens in and
  nothing else. Until now the mission carried on looking healthy with effects never spawning, or
  income and captures stopped, or Squads drifting off their Orders, for the rest of the session, and
  the only recovery was the human guessing that something was wrong and restarting. Each loop now
  stamps a heartbeat every turn and one small watchdog reads them: a loop that has gone quiet for
  three of its own cadences, or half a minute, whichever is longer, is named in a typed
  `node_crashed` line and captioned on every screen with what has stopped and that a restart is the
  fix. Nothing is restarted automatically, deliberately: a loop that died on the state it met would
  die again on the next turn, and its counters — which probes and reports read as evidence — would
  silently start again from zero. Being told is the fix; pretending to have recovered is not.

- **An unusable Command Port schema is refused rather than crashing the two callers that read it.**
  `cti_fnc_commandSchema` answers an empty schema when its export is missing or unreadable and says
  callers must treat that as fatal; the Command builder and the Command Port's gateway both read
  straight through it instead. So a broken build met a raw script error — in the gateway's case
  while it was deciding whether a client may command a side at all, and a script error there kills
  the script it happens in — rather than the typed `schema_stale` refusal its siblings already gave.
  Both now ask whether the part they need is present, which covers a missing export and a malformed
  one alike, and a new red-by-design probe (`schema-stale`) asks each guard the question in-world
  and lives to tell.

- **A report the daemon cannot read no longer leaves half of itself behind.** The observe report was
  folded into the Campaign field by field as it was read, so a batch of casualties whose fourth row
  was malformed had already written the first three when the refusal was raised — a timeline that
  looks complete and is not. The whole report is now read before any of it is acted on, so a refusal
  leaves the Campaign and its record exactly as they were. The refusal also names the field that was
  wrong, by its path in the document (`casualties.deaths[3].by_side`), rather than saying that
  something in the report was.

- **A dead daemon is no longer indistinguishable from a quiet one.** The shim reports a transport
  failure as `{"error": "..."}`, which is a JSON object — so it passed every loop's only check and
  read as *success with nothing in it*. The map froze, income stopped, the AI opponent went quiet,
  Commands came back as `? — ?`, and no line anywhere said the daemon was down. Every call now goes
  through one place that tells the four outcomes apart, says so once when the daemon stops answering
  and once when it comes back, refuses a Command it could not get judged rather than showing you a
  transport error as a verdict, and counts a report as completed only when it actually completed.
  The last of those also fixes a counter that several tests and probes had been reading as proof the
  world was healthy.

- **The daemon answers one request at a time, whoever is asking.** Every connection got its own
  thread and the Campaign — ownership, the Ledger, the Roster, Contacts, the outbox — was written
  under no lock at all, so two connections could interleave a mutation and quietly corrupt Funds or
  the outbox sequence. Two connections is not hypothetical: the shim's resend after a failed
  exchange arrives on a fresh connection while the request it duplicates may still be running on the
  old one, which is exactly the moment the duplicate has to meet the record rather than race it. One
  lock around the whole request, rather than a lock per field or a serial server: a request is 746 µs
  at p50 with both planners inside it, and a serial server would have made the resend wait for the
  stuck connection it exists to escape.

- **A stalled daemon can no longer freeze the server frame for ten seconds at a time, and a slow
  call can no longer queue a human Commander's click behind it.** The shim's read and write timeouts
  were 5 s each — five times the engine's own 1000 ms frame-stall budget — and a call that
  reconnects and resends spent that twice, so every loop turn against a hung daemon was a
  multi-second hitch the player felt. A synchronous call now carries a single 500 ms budget for the
  whole round trip — connect, write, read and resend together — which is half the engine's cap and
  still 57× the slowest call ever measured, so a call that gives up does so without the engine
  complaining on our behalf. And `rpc_async` — the path defined as the slow one — now takes its own connection
  instead of the shared one every synchronous judgement queues on, as ADR-0005 required of it before
  it carries production work.

- **A probe can no longer pass green with half of its subject switched off.** `human-commander`'s
  client leg — the only half of it that crosses the machine boundary, a Command built on a real
  client and judged on the server — was gated on an environment variable that defaulted to off, so
  every corpus run of it finished green having tested the server side alone and logged one line
  about it that nothing scored. Optional legs now default **on** in the corpus, declared in the
  probe's own `env:` header, and a leg that did not run reports `unverified` and makes the run
  `infra_unavailable` — which this tier already refuses to read as a result — instead of passing.
  Every verdict now names its legs: `legs: client_port_caller:ran client_port_accepted:ran …` in the
  run summary and in `verdict.json`. `client-port`'s six step exits, which short-circuited to a bare
  completion line, name themselves too. The rule is written down in `docs/regression-tier.md`.

- **A full-corpus run no longer stops itself on its own Windows client.** `taskkill /F` returns when
  the request has been made rather than when the process is gone, so a client probe would pass, the
  run would move on, and the next probe's pre-flight two seconds later would see the still-exiting
  `arma3_x64.exe`, read it as a live play session and abandon the rest of the corpus — reproduced
  twice, on two shas. The host guard was right and is unchanged: it cannot be taught to excuse a
  process it recognises without also being able to excuse the human's, and "a process we did not
  start means stop" stays absolute. Instead the run that launched a client now waits for it to leave
  the host's process list before releasing the tier, and says so in its evidence if it never does.

- **A Campaign that has been won no longer accepts Commands.** The Campaign already refused the
  world's reports after victory and the AI Commanders already stood down, but the Command Port never
  asked: a Purchase arriving after the end screen spent a finished Campaign's Funds, minted a Squad
  and queued a spawn onto an outbox the world may still drain, and an Order rewrote a Squad's
  standing instruction. Both are now refused with a new rejection code, `campaign_over`, which the
  game learns from the generated command schema like every other code — a human Commander whose map
  screen is still open is told why rather than being quietly obeyed. The invariant is stated once,
  at the Campaign itself: buying a Squad, issuing an Order, folding in the world's account of the
  Squads and folding in what a side's leaders saw are now the Campaign's own verbs rather than
  things the port and daemon did to its parts, so a rule about what a won Campaign will not take
  cannot be missed by a caller that never asked.

- **Every way of bringing the Arma tier up now asks whether the human is playing, and waits its turn
  for the machine.** The guard that refuses to load the shared host underneath a live play session
  ran in one place, and `spike/run.sh` asked it only when a run meant to *drive* the Windows host —
  so `just probe` and `just spike` started a daemon, a dedicated server and a staged world on the
  human's machine without ever asking. `just spike` also took no tier lock, so it could stage over a
  locked `just regress` run's server install mid-pass. The guard is now asked by `run.sh` itself,
  before anything is launched, and the `spike` recipe serialises on the same lock as everything else.

- **An in-mission `FAIL class=timeout` is no longer reported as a failed assertion.** `spike/run.sh`
  has two verdict paths, and only the hold/regress one read the class the world declared; the other
  called every red an `assertion_failed`, sending the reader to fix the code under test when the
  failure-class table says investigate synchronisation. Both paths now type the failure off the
  line the world wrote. Alongside it, the harness's staging steps are checked rather than assumed
  (a failed copy is a clean `infra_unavailable` instead of a confusing engine error three steps
  later), a push-path report that dies is recorded instead of silently producing nothing, a value
  containing a newline can no longer forge a second record in `results.env`, a probe header
  containing a quote can no longer break the run's `verdict.json`, and a Windows process the
  harness could not kill on teardown says so.

- **The mission-cycle spike now fails on the freshness axes it was only writing down.** Its own leg
  header promises that every axis is an assertion and that a missing reading fails rather than being
  skipped, but a PRNG stream that carried over into the second mission, and second-mission telemetry
  carrying rows the first mission wrote, were recorded and then reported `verdict=PASS` — the same
  false-green shape #44 found. Both gate now, the telemetry one only where the daemon was restarted
  and carry-over therefore means something, and a reading that could not be taken is a failure
  rather than a blank. Both legs also wait on the world's own counters instead of a flat 20-second
  dwell, which the cycle runner had made impossible by staging them without the shared probe
  prelude.

- **A busy outbox no longer hands the world more effects than one `callExtension` return can
  carry.** The engine truncates a return past 10,240 bytes in silence, and the effects poll handed
  over every pending entry in one reply — so a world polling slowly, or two Commanders in a burst,
  would eventually get broken JSON with the effects past the cut lost and nothing said. A drain is
  now bounded at nine tenths of the cap, the same figure the Commander's view already guards itself
  at, and the acknowledgement cursor delivers the remainder on the next poll. Measured: 72
  `squad_spawned` effects in one drain, against the largest drain two AI Commanders have ever
  produced (4) and the engine's own 100-per-frame limit. A single effect too large to cross one
  return now fails the poll loudly and stays on the outbox instead of being cut in half.

- **A Command the shim had to send twice is no longer carried out twice.** The shim resends a
  request when an exchange fails on its cached connection, and a write that succeeded before the
  read failed had already been executed — so one transport hiccup could spend a side's Funds twice
  on one Purchase, or give both AI Commanders a second turn on one report. The retry stays, because
  losing a Command is worse; the daemon now answers a request line identical to one it has already
  answered from its record rather than acting on it again, and writes the duplicate down. ADR-0034.

- **An unreachable daemon address no longer freezes the client for twenty seconds.** The shim's
  connect had no timeout of its own, so a LAN candidate a joining client cannot reach blocked for
  the OS default — about 21 s on Windows, inside a blocking call that stalls the frame for its whole
  duration. It now gives up after one second, which is a hundred times what a handshake on loopback
  or the same LAN takes.

- **A test run pointed at a different daemon port now actually talks to that daemon.** The shim
  reads its daemon address from `CTI_DAEMON_ADDR` and defaults to port 9099, and the harness set
  only `CTI_DAEMON_PORT` — so moving the daemon moved the daemon and left the world talking to
  whatever still held 9099. The two agreed only because both defaulted to the same number. Found by
  running two worlds side by side for #44: one daemon received both of them, and the run that was
  not checking its telemetry passed. Unchanged at the default port.

### Added

- **`just cycle-spike` runs two test missions in one server process, and proves the second one
  starts clean.** The dedicated server can be made to change mission unattended with nobody
  connected — mission rotation cannot, because it waits for a player, but `serverCommand` with a
  `serverCommandPassword` can — and the switch costs under a second against an eleven-second cold
  start. It is not part of `just regress` and is not being adopted: behind the parallel pool #47
  proposes it would save about half a minute a pass, and the port allocation that pool was waiting
  on has since been granted. It stays only as the fallback if three slots turn out not to fit. The
  measurements, the corpus classified for whether probes could share one world (one of fourteen
  can), and the recommendation across all three speed-up levers are in
  `docs/research/multiplexing-the-arma-tier.md`.

- **The in-world regression tier can now be asked for the probes an earlier issue produced.**
  `just regress --issues 28` runs everything whose `issues:` header names #28; `just regress --list`
  prints what a selection would run — names, and the deadlines they add up to — without taking the
  lock, opening a port or bringing a world up. Two things deliberately did not change. The full
  corpus is still what runs with no arguments and still what gates anything touching an in-world
  surface, because a probe's header records what motivated it rather than what it covers, and
  filtering your own change by your own issue number selects only the probes you just wrote. And a
  filter that matches no probe is an error rather than a very fast green pass — the one way this
  tier could lie is by being narrowed to nothing.

### Changed

- **A probe now ends when its subject has finished, not when a clock says it probably has.**
  Half of a full regression pass — 705 s of 1,405 s — was probes watching a fixed clock rather than
  the world. The `ai-commander` probe, whose 150 s settle was the worst of them, now reads the claim
  it is about to assert continuously and stops the moment it becomes true: **179 s to 44 s**, same
  verdict, three green runs over. A full pass is 21m10s where it was 23m25s. The 150 s survives as the deadline it always was, so a run in which nothing
  moves still fails at the same instant in the same class. The rule this is allowed under, the audit
  behind it, and which of our waits the engine can signal versus which must be polled are in
  `docs/regression-tier.md`.

- **The AI Commander now judges how much force a Base needs, instead of always sending one Squad.**
  It could name the enemy HQ as a target but not take one anybody was standing on: assignment gave
  every Place one Squad, so a raid arrived eight men strong however much of the enemy was reported
  on it, and against a defended Base it died there. The Commander now reads the band of what its
  own men have seen — a team, a squad, a platoon, a company — and details that many Squads to the
  Assault, or, if it cannot find them, calls the Assault off and puts everyone back on the ground
  they were second-best at. An undefended Base is still raided by one Squad exactly as before, and
  the raid still arrives late in a Campaign rather than opening it.

  Two things follow that are worth knowing at the table. Concentration is visible: half the force
  peeling off a held island for one Place is a Commander going for the throat, and the ground it
  leaves stays held. And an old sighting still deters less than a fresh one but never excuses a
  smaller force — a company seen ten minutes ago stops making the Base look expensive, and does not
  stop four Squads being sent, because the only way to find out that it left is to go and look.

### Fixed

- **A client that joined and took the Commander seat is no longer recorded as one that never
  arrived.** The hold harness waited three minutes for a log line only the Phase-0 mission writes,
  then filed the run's evidence as `connected-but-never-entered-mission` — of a client that had
  connected, entered, been assigned a side and been playing for two of those three minutes. It now
  also accepts the Phase-1 mission's own signal, which says strictly more: a player whose unit
  occupies a Commander slot and carries a UID is a person in the mission, not merely a socket.

- **The guard that protects a live play session now actually runs.** The Arma tier asks whether
  Arma 3 is open on the Windows host before it takes the shared machine, and refuses if it is —
  but it asked for `tasklist.exe` by name, which is not on an agent's `PATH` here, so the check
  was skipped in silence and every run proceeded on a question nobody had answered. It now
  resolves the tool by absolute path and fails *closed*: not being able to read the Windows
  process list is `infra_unavailable`, the same stop as seeing the game in it. A run that means
  to drive a client on the Windows host asks the same question before launching anything, so a
  client already open is left alone rather than killed on teardown by a harness that cannot tell
  yours from its own.

### Added

- **The leg between a person's client and the Command Port is now exercised unattended, failures
  and all.** A regression probe launches a real headed client, waits for it to be assigned a side,
  and drives six Commands across the network from it: an accepted Purchase whose judgement comes
  back to that client, a Command whose `side` the client filled in with the enemy's — the Squad
  arrives on the caller's own side and the side it asked for is untouched, which is the server's
  stamp shown rather than asserted — a Command from a machine the server has not assigned, refused
  `wrong_side` by the gateway in its own words without the daemon being asked, and two payloads
  that are not Commands, refused as judgements rather than as silence. Last, the client calls two
  things the mission does not whitelist, having just proved through the gateway that it can call
  the one it does: neither lands, and the engine writes both refusals in its own words to the
  client's log, which the harness now copies back across the WSL2 boundary as evidence.

- **A world can now be held open for a play session.** `spike/playtest/session-hold.sqf` keeps the
  Phase-1 world standing for as long as the boot line asks, or until somebody wins, instead of
  tearing it down the moment a client finishes joining. It lives outside the regression corpus
  because it asserts nothing and waits for a person. The first brief that uses it is
  `docs/playtest/0001-commander-seat.md`: half an hour in the WEST Commander seat against the EAST
  AI, looking at the things automation cannot see.

- **A human can now command a side from the map.** Take a Commander slot, open the map, click a
  Place and press a number: Purchase a Squad, or Order one to Capture, Defend, Assault or Reserve.
  It is crude on purpose — a hint for a panel, local markers for your own Squads and the Contacts
  you have, the number row for verbs — and every visual choice in it is a playtest-tuned
  placeholder that Phase 4 replaces wholesale. What is not crude is where the click goes: the same
  Command Port entry function, the same wire format and the same `remoteExec` whitelist the AI
  Commander's Commands travel through. The verb list is read out of the port's schema rather than
  written down in the UI, so a human cannot express an Order the AI cannot, and the port's typed
  refusals reach the player in the port's own words — `already_held`, `wrong_ground`,
  `insufficient_funds` — rather than as a dead click. A click never waits: it hands the Command to
  `remoteExec` and the judgement arrives on its own.

- **Each Commander now sees its own strategic picture on its own map.** The server asks the daemon
  for the view belonging to the side it has assigned, under a new `view` transport verb, and
  forwards it to that Commander's client alone. It is the same `Campaign.observation(side)` call
  the AI planner reads in-process, so Commander symmetry covers knowing as well as commanding: own
  Funds, own Squads, Contacts for the enemy, and Objective ownership plus Base HQ status as the
  public scoreboard. The server never reads it, and there is no unprojected picture to ask for.

- **The project has a black box.** Every death in the world is now written down as it happens:
  who died — the Squad and side, not an engine id nobody recognises — where, on the authored
  place *and* to the metre, at the death's own clock reading rather than the report's, and by
  whom, naming the killer's Squad and side and the vehicle where one was involved. Deaths with no
  Squad behind them are recorded too, and so are deaths nobody can be blamed for. The rows join
  the daemon's existing telemetry stream rather than opening a second log, and no Commander ever
  reads them: this is the operator's record, not intelligence. The motivating case is a probe that
  timed out with a Squad at three of eight and nothing in the evidence saying where the other five
  went.

- **`tools/timeline.py`** reads a run back out of its telemetry as a sequence a person can follow,
  and every Arma-tier run now leaves one in its evidence directory. Pointed at a probe's own log
  with `--expect`, it also checks that every death the world says it staged is actually in the
  record — which is what lets an in-world casualty test be an assertion instead of a screenshot.

- A `casualties` probe: three staged deaths on two Objectives, each a different shape of row, with
  the harness failing the run when the daemon's file does not account for all three.

- **A Campaign can now be won.** Both conditions the MVP decided are live. **Domination**: one
  side owns every Objective at once and holds the lot for ten sustained in-game minutes — losing
  one Objective, or having it contested, restarts the ten minutes rather than pausing them, and
  the timer is not persisted, so it starts again on every boot. **Decapitation**: a side's Base HQ
  structure is destroyed and the other side wins, whoever brought it down; two HQs falling in the
  same report are resolved by whichever the world reported first, deterministically. There is no
  draw. Until now a Campaign ran until somebody stopped watching.

- **An end screen, and an archive.** On victory the Campaign is marked complete, both AI
  Commanders stand down, income stops and ground stops changing hands. The world is told once,
  through the same outbox every other effect rides, and carries a summary read back off the run's
  own telemetry — the winner, the condition, the board as it finally stood, income paid and
  Commands accepted per side, Squads lost, and the HQ that fell. A headed client sees that as a
  caption; the mission does not end itself, and the laid-out end screen is #18's map UI. The
  completed Campaign is archived as a JSON record beside the telemetry, and the next session
  starts a fresh Campaign — because the archive is a record of what happened rather than a state
  to resume (ADR-0023), so there is nothing to load and the freshness is not a rule anyone has to
  remember.

- **Each Base's HQ, intact or destroyed, is now in every strategic picture** — including the
  public one the server paints markers from. The two win conditions are the scoreboard rather than
  intelligence, so this is the one enemy-shaped fact that crosses the fog boundary, and it was
  decided that way with the fog itself. It costs 54 bytes on the wire and does not grow with the
  Campaign: the map has one Base per side.

- `domination_seconds` in `config/economy.json` (600, a playtest-tuned placeholder like the rest of
  that table).

- A `campaign-end` probe: an unattended two-AI Campaign on the real topology that actually ends, by
  Decapitation. It engineers two things about *position* and nothing about a rule — the island, so
  the Campaign reaches the state in which a Commander plays for the enemy HQ, and the march, so
  nobody waits out the four and a half kilometres between the Bases. The Assault itself is the
  Commander's own decision through the port, and the probe refuses the run if it never comes.

- `just regress` — the in-game regression tier. It runs the probe corpus in `spike/probes/`
  against a fresh Phase-1 world per probe and returns one typed verdict each, mapped onto the
  documented failure classes, with the worst class as the exit code; `just regress <name>...` runs
  a subset while iterating. Before this, every in-world check was a hand-typed invocation with
  five bespoke environment variables that nobody who had not typed it could reproduce, and a
  property proven the day it was built was unprotected the day after. Each probe now declares its
  own deadline, the issues that motivated it, and any world it needs, in a header block the runner
  reads — so the command itself takes no environment variables, and a probe that finishes early
  ends early instead of burning a hold window waiting for a client that a regression run never
  sends.

- A `bareworld` probe, carrying the properties that had no Phase-1 home: the addon resolving by
  name on a dedicated server, the seeded PRNG against the real engine, the daemon echoing a
  request id back through `callExtension`, and the effect pump and presence report actually
  turning. Three of those existed only in the Phase-0 measurement mission, which nothing runs.

- Serialisation of the Arma tier on a machine-scoped lock at `~/.arma-cti/tier.lock`, wrapped
  around `just probe` as well as `just regress`. The tier is single-occupancy — one server
  install, one port range, one machine the human also plays on — while agent worktrees are many
  and short-lived, so a lock inside any worktree would serialise nobody. A held lock reports
  `infra_unavailable` with the holder's metadata and launches nothing; `--wait <secs>` bounds a
  queue. A run also refuses outright if the game is up on the Windows host.

- Evidence directories under `~/.arma-cti/runs/<UTC>-<probe>/`, outside every worktree, carrying
  the verdict, the logs, the daemon telemetry and the probe exactly as it was staged. Passes are
  pruned to the last three per probe.

- **Assault**, the fourth Order kind: close with the enemy Base and destroy its HQ structure —
  Decapitation as an Order (ADR-0020). Until now an Order could only name an Objective, so one of
  the two win conditions the MVP decided was unreachable through the only order path there is, by
  a human Commander and an AI alike. The Command Port accepts an Assault and rides it out on the
  outbox as an `order_issued` effect like any other Order; what the world does with one, and the
  AI Commander that scores a Base worth assaulting, are both below.

- **The AI Commander plays for both win conditions.** It now scores both Bases alongside the
  Objectives: the enemy's as an Assault, and its own as ground to garrison under the same fog rule
  that already had it covering its rear. Where it used to run out of ideas once the island was
  held, it now finishes the Campaign — and it will turn a Squad round for a company reported at
  its own HQ rather than march on and lose the game behind its back. The raid arrives late without
  any rule saying so: what defers it is the four and a half kilometres between the two Bases, so a
  Commander still opens by taking the ground that pays. What a Base is worth is one new number
  (`decapitation`), a playtest-tuned placeholder awaiting feel sign-off like the rest of them; no
  existing weight moved to make room for it.

- Defend now takes the side's **own Base** as well as any Objective, so rear security is something
  a Commander can order rather than hope for.

- **The world now acts on both**: an Assault sends the Squad at the enemy Base's HQ structure and
  the building comes down; a Defend on a side's own Base garrisons it. Until now an Order naming a
  Base was looked up among the Objectives alone, found no ground, and was logged and dropped. The
  Squad walks onto the HQ and is then set on it with the engine's Destroy waypoint, and a Squad
  standing at the HQ under an Assault brings it down in ninety seconds. **The means of destruction
  and the HQ's durability are playtest-tuned placeholders** in the sense ADR-0020 gives the word —
  the structure is the contract, and the numbers are the first thing a playtest will move. They
  are set, with their alternatives, in `addons/main/functions/fn_baseAssault.sqf`.

- An HQ that falls is recorded once, as an `hq_destroyed` telemetry row naming the Base, the side
  that lost it and the side that brought it down. Once per Base, deliberately: the MVP resolves a
  mutual Decapitation by which destruction came first in telemetry, and a second row for the same
  Base would make that a question of which report arrived rather than which HQ died. Any HQ death
  counts, not only an ordered one — the world reports the building's state rather than the
  Assault's outcome.

- One new rejection code, `wrong_ground`: ground the map has that this Order may not name —
  Capture(Base), Assault(Objective), Assault(own Base), Defend(enemy Base). An id the map does not
  have at all stays `malformed_command`, so a typo is not reported as a rules mistake.

- A manifest is refused if an Objective id collides with a Base id, naming the id. An Order names
  a Place of either kind, so one id answering to both is ground the port could not tell apart.

### Changed

- **Commanding authority is now an assignment rather than a uniform.** The gateway used to stamp
  the acting side from the side of the caller's own unit, which would have handed the Command Port
  to every rifleman on the island once players lead squads. It now reads the server's
  commander-assignment state: the person occupying a side's authored Commander slot, latched by
  player UID once per Play Session so respawn and reconnection do not change who commands. A
  machine with no assignment is refused `wrong_side` and told why.

- **A side has one Commander, whichever kind it is.** A Command arriving over the wire for a side
  already under an AI Commander is refused `wrong_side`, and that side's view is not handed out at
  all — the same rule that already refused a second AI brain on one side, arriving through the
  other door. Bring the world up without an AI on the side you mean to play.

- **The Order's ground field is `place`, not `objective`** — in the Command a Commander sends, in
  the `order_issued` effect, in the observation each Commander receives, and in the exported
  Command schema the game reads (`orders_needing_objective` is now `orders_needing_place`). It can
  hold an Objective id or a Base id, and a field named `objective` carrying a Base id would have
  been term drift baked into the wire — and, from Phase 2, into the campaign snapshot. Anything
  built against the old field name will need updating; nothing persisted holds it yet, which is
  why the rename is now.

- An in-world `FAIL` line's own `class=` is now believed. The harness called every in-mission
  failure `assertion_failed`, including the ones the world had explicitly typed `timeout` or
  `oracle_disagreement` — which sent the reader to fix code when the table said investigate
  synchronisation or suspect the capture layer.

- The game reads the authored map manifest itself, instead of a generated SQF copy of it. The
  engine has had a JSON parser since 2.18 and the server runs 2.20, so the addon ships
  `manifests/stratis.json` verbatim in its own PBO and parses it at mission start with `loadFile`
  and `fromJSON`. The generator, the generated file, its Functions Library entry and its freshness
  check are all gone. Before, the same eight Objectives existed twice and a check kept the copies
  honest; now there is one document, and them disagreeing is not a thing that can be expressed.
  The addon resolves its manifest from the world's name — world `Stratis` is `stratis.json` — and
  Python refuses a manifest whose filename the game could never find. See ADR-0017, which amends
  ADR-0012's generated-SQF clause and records what would overturn the decision.

- The Command Port schema is exported as JSON rather than rendered as SQF. The Command catalogue,
  the effect catalogue and the rejection codes live in Python and have no authored file to ship, so
  `just generate` and the `schema_stale` gate survive for that one export — but the hand-rolled SQF
  literals, quoting and all, do not.

### Fixed

- A Squad the world has never held is no longer treated as one it has lost. A Purchase is judged in
  the daemon and carried out in the game, and a report arriving between the two says nothing about
  the Squad on its way — reading that silence as a loss deleted it from the roster, so the group
  that spawned a moment later answered to an id nobody knew: a Squad no Commander could order and
  none counted, and a Commander short of its intended force bought another. A human Commander buys
  a few times a session and would have met this rarely; the AI Commander buys every five seconds.

- None of `targetsQuery`'s arguments can be relied on to select anything, and the Contact design
  was written as though all of them could. Three separate findings, each from an in-world probe
  run and none reachable from a unit test:
  - **The side argument ranks rather than filters.** Asking a NATO leader for east came back with
    seven of its own riflemen at accuracy 0.01 and no enemy on the list at all. The wiki says so
    in its first line — "targets, known to the enquirer (including own troops), where the accuracy
    coefficient reflects how close the result matches the query" — the arguments are query terms
    scored into the accuracy the results are sorted by, not a filter.
  - **The engine does not decay knowledge out of the query.** What decays after 120 s without
    sight is `knowsAbout`; `targetsQuery` goes on returning the memory with a growing age, 132 s
    after the observers had withdrawn 3 km. Unbounded, a leader standing on a place would report a
    ten-minute-old memory of men who had left, and observed absence — the only rule that clears a
    Contact — could never be observed.
  - **The max-age argument filters away targets in plain sight.** The obvious fix for the above
    broke it the other way: a target's age is documented as possibly negative, and a negative age
    does not survive the bound, so six men at 100 m came back as one — the only one the engine
    happened to report at a positive age.
  - So the query asks for the widest answer available and side and age are both selected again on
    what it actually returned. Sightings stay perceptions rather than ground truth: the side is the
    one the observer believes, so a man wrongly taken for the enemy is reported as one.

- The desync load generator is now asked for explicitly (`CTI_DESYNC_LOAD=1`) rather than running
  whenever a client turns up. It spawns thirty-two WEST soldiers standing on the first four
  Objectives, and capture is by presence — so with a headless client brought up on purpose for
  #17's topology it would hand WEST half the island on every run. #8's investigation asks for it;
  a Campaign never does.

- A probe is now waited for over the window the caller asked for, rather than a fixed three
  minutes. The client wait ends the moment a client connects, so a run with a headless client left
  the probe 180 s however long a window was requested — and a probe measuring a Squad marching
  does not fit in three minutes.

- The desync load generator no longer runs when no client turned up. It exists to give a joining
  client traffic to carry (issue #8), and it does that by spawning thirty-two WEST soldiers
  standing on the first four Objectives — which is fine as traffic and is not fine as a Campaign,
  because capture is by presence. Unattended, it was quietly handing WEST half the island four
  minutes into every held run. Found by the first probe to care what the map said it owned.

- None of `targetsQuery`'s arguments can be relied on to select anything, and the Contact design
  was written as though all of them could. Three separate findings, each from an in-world probe
  run and none reachable from a unit test:
  - **The side argument ranks rather than filters.** Asking a NATO leader for east came back with
    seven of its own riflemen at accuracy 0.01 and no enemy on the list at all. The wiki says so
    in its first line — "targets, known to the enquirer (including own troops), where the accuracy
    coefficient reflects how close the result matches the query" — the arguments are query terms
    scored into the accuracy the results are sorted by, not a filter.
  - **The engine does not decay knowledge out of the query.** What decays after 120 s without
    sight is `knowsAbout`; `targetsQuery` goes on returning the memory with a growing age, 132 s
    after the observers had withdrawn 3 km. Unbounded, a leader standing on a place would report a
    ten-minute-old memory of men who had left, and observed absence — the only rule that clears a
    Contact — could never be observed.
  - **The max-age argument filters away targets in plain sight.** The obvious fix for the above
    broke it the other way: a target's age is documented as possibly negative, and a negative age
    does not survive the bound, so six men at 100 m came back as one — the only one the engine
    happened to report at a positive age.
  - So the query asks for the widest answer available and side and age are both selected again on
    what it actually returned. Sightings stay perceptions rather than ground truth: the side is the
    one the observer believes, so a man wrongly taken for the enemy is reported as one.

### Added

- Founding decisions: domain glossary, ADRs, MVP scope, and the agent development process.
- `just` command surface: `check`, `unit`, `build`, `spike`, `probe`, `fast`. The no-Arma gate
  (`just check` + `just unit`) runs in under a second. `just probe <file>` brings the Phase-1
  world up and holds it with a probe from `spike/probes/` appended to its harness, and waits for
  that probe to finish — a probe still working when the hold window closes is a timeout rather
  than a pass nobody earned.
- Pinned toolchain: HEMTT, `just`, Rust with `cargo-xwin` for the Windows shim, and a
  `uv`-managed Python environment.
- HEMTT addon skeleton, with the "no bare `random` or `sleep` in SQF" contract enforced as a
  `banned_commands` lint rather than a grep.
- Rust extension shim on `arma-rs`, round-tripping opaque payloads to the Python daemon over TCP
  loopback and returning replies through `ExtensionCallback`.
- Mission PBO packer (`tools/pack_pbo.py`), since HEMTT packs addons but not missions.
- Phase-0 spike harness and its measurements: `docs/spikes/0001-phase0.md`.
- ADR-0011: the acceptance-harness architecture — Python orchestrator, in-game gtest-style SQF
  asserts, verdict returned through the extension as structured JSON. Bohemia's `-autotest` and
  SQF-VM are rejected as test tiers, with reasons recorded.
- ADR-0012: the Command Port wire format — a domain protocol carried inside the daemon's
  transport envelope, not the envelope itself. The daemon judges Commands against the Funds
  ledger, one whitelisted server-side gateway admits the human UI, and every world effect rides
  the outbox for both Commanders. `CONTEXT.md` gains **Command**.
- `CONTEXT.md` gains **Observation**: the whole strategic picture at one moment, as a Commander
  may know it. Distinct from the Campaign snapshot, which carries the same set of facts durably;
  an Observation is momentary and in memory.
- Fog of war is in the MVP, and `CONTEXT.md` gains **Contact** to name what a Commander learns
  through it. A Commander knows its own side in full; Objective ownership and Base HQ status are
  public, because the win conditions are the scoreboard rather than intelligence; everything else
  about the enemy arrives as Contacts — what that side's squad leaders actually saw, aggregated per
  place, carrying an echelon band, a posture, notable assets and an age. Enemy Funds, force count,
  Squad identity and standing Orders never cross. ADR-0012 amended: Commander symmetry covers
  knowing as well as commanding, and the AI Commander plays under the same fog, enforced by there
  being no unprojected picture for an in-process planner to read. Perfect information as a
  difficulty lever was considered and rejected — it makes "is the scorer any good" unanswerable.
- The return leg: every report the world makes is answered on the same call, so there is no second
  channel, no second cadence and no callback — which is why at-most-once callback delivery never
  arises for it. An **Observation** is what one Commander may know at one moment: which side holds
  each Objective including Contested, what that Commander has to spend, and each of its own Squads
  with its type, head count, standing Order and the Objective or Base it is standing on.
  Deliberately the set ADR-0008 persists and nothing it regenerates, so the Phase-2 snapshot
  schema is this shape rather than a second one. No exact positions, health, ammo or AI knowledge:
  a Commander reasons about places, not coordinates. Held in memory only.
  - Assembled rather than reported wholesale. Ownership, Funds and Orders are the daemon's own;
    the world contributes only the two facts nothing else can see — how many of a Squad are still
    standing, and where it is. A Squad the world stops reporting has been wiped out, and the
    roster says so rather than letting it linger.
  - One side only, and structurally so: Funds are a number rather than a table keyed by side, a
    Squad view carries no side, and no call hands out the whole map's Squads. There is no
    unprojected picture to obtain, which is what makes the fog hold against a planner that reads
    campaign state in-process rather than over the wire. The server, which is not a Commander,
    takes ownership alone — enough to paint its markers and nothing else.
  - A crowded Stratis (every Objective owned, sixteen Squads a side) encodes to 1,932 bytes
    against the engine's 10,240-byte `callExtension` return cap — 8,308 bytes of headroom, about
    107 bytes a Squad, so roughly 90 Squads a side would fit. The server's own reply is 222 bytes.
    Every reply's size is recorded in telemetry, and the game fails the run at nine tenths of the
    cap, because the engine truncates a longer return in silence and the fix is a smaller
    observation rather than a chunking protocol invented in passing.
  - Telemetry carries each side's picture whenever it moves and not otherwise, so tailing it shows
    the moment ownership or Funds changed instead of a hundred rows saying they had not. A row per
    side, because there is no picture carrying both to write.
- **Contacts**: a Commander now learns something of the enemy, and only what its own squad
  leaders saw. One Contact per place rather than per enemy Squad — an Objective or Base, carrying
  an echelon band (`team` 1–3, `squad` 4–8, `platoon` 9–24, `company` 25+) read off the *observed*
  count, a posture from the heaviest vehicle seen, any notable assets, and how long ago it was
  seen. Seeing three of eight reports a team, so a Commander is left under-informed rather than
  over-, and several Squads in one place read as a platoon without naming which ones. A Contact
  carries no enemy Squad id and no Order, and cannot: the sighting it is made of never had one.
  - The engine's own knowledge model is the source, through `targetsQuery` — shared instantly
    within a group, decaying to nothing after 120 s without sight. No visibility rule of ours, and
    no correcting it against ground truth: what a leader made out is what gets reported, so an
    unrecognised contact is honestly unidentified. Classification is `BIS_fnc_objectType`'s own
    vocabulary rather than a table of ours. Armour and air are out of MVP, so `foot` and
    `motorised`, `AT` and `MG` are what the game can currently produce; the rest of the vocabulary
    is defined so the schema does not churn when Phase 4 adds vehicles.
  - Memory is keyed by place, so it is bounded by the island — ten entries on Stratis — and needs
    no ageing rule: a newer sighting supersedes an older one. The one removal rule is that
    **observing a place and finding no enemy clears its Contact**. Absence of contact is not
    evidence; observed absence is. So a Contact outlives the engine forgetting it, with its age
    growing, which is what a Commander planning at the strategic level needs.
  - A crowded Stratis now encodes to 2,939 bytes against the 10,240-byte cap — 7,301 bytes of
    headroom, about 99 bytes a Contact. Contacts are bounded by the map rather than by enemy force
    size, so ten is the ceiling however much the enemy buys. The server's public reply is
    unchanged at 222 bytes and carries no Contacts at all.
  - Measured in-world at the cadence it runs: one `targetsQuery` per squad leader costs 0.0097 ms
    with 13 targets known, or 0.31 ms across the 32 leaders a full Campaign fields, against a
    report every 5 s. The whole sampler is 0.35 ms with two leaders. The wiki's CPU-intensive
    warning is real but nowhere near this scale, so the cadence stands as designed and no
    sampling-versus-frequency trade needed making.
- An **AI Commander** for one side: start the daemon with `--ai-side WEST` and leave it, and that
  side buys Squads, sends them at ground it does not hold, garrisons what is coming under attack,
  and reacts as Objectives change hands. It plays through the same Command Port a human does and
  has no other way in, so the port stays the one thing #19 has to audit.
  - A seeded deterministic utility scorer over the Objective adjacency graph, as a pure function of
    one Observation and the authored map and price table. It returns the Commands it would issue
    and the trace explaining them; writing that trace is the daemon's job, because a function that
    logs is no longer a pure one. The same seed and the same reports produce the same Orders, which
    is property-tested rather than asserted.
  - It plans under the fog, structurally: an Observation is the only input, and there is no
    unprojected one to reach for. So it sees banded, aged Contacts and no enemy roster, and weighs
    staleness — a company seen ten minutes ago stops deciding anything. Ground nobody is looking at
    is scored as holding a team rather than as empty, and a Contact nobody has refreshed decays to
    that same floor rather than to nothing, so old knowledge becomes ignorance instead of good
    news.
  - Every decision reaches telemetry with what was scored, what won and why, each candidate broken
    into its named terms — income, contested, threat, travel, commitment, jitter. Observability
    only (ADR-0003): taking the log away entirely changes nothing about the Campaign, which is how
    that is tested.
  - A Squad keeps going where it was sent unless something beats it by a margin, so two Objectives
    whose scores cross and recross do not turn into countermarching. An unchanged world produces no
    second round of Orders at all.
  - It presses. Two Commanders both sitting on what they hold is not a Campaign worth playing, so
    the weights advance by preference and consolidate only against a real massed incursion: a Squad
    on the line attacks a fresh Contact of any echelon across it, and turns round only for a
    company standing on ground behind it. The first set of weights held at every echelon — and
    went on holding with the threat terms set to zero, because the turtle was never the threat
    terms. Marching cost more per kilometre than an Objective was worth, and a standing Order was
    worth half an Objective on its own, so a Squad that reached the line stopped there.
  - It buys the cheapest Squad it can afford, up to one per Objective the map has: ground is taken
    by standing in a capture radius, so what wins is the number of Squads rather than what each
    carries. A threat-aware purchase is left for when the scorer has a threat model worth spending
    against.
  - The interface is one method — an Observation in, a Plan out — so the HTN escalation ADR-0004
    names, or a post-MVP LLM Commander, changes neither the port nor the trace format. Held by a
    test that drives the daemon with a planner that scores nothing at all.
  - It plays for Domination and not Decapitation: an Order names an Objective and a Base is not
    one, so the port has no way to say "go for the enemy HQ" and neither has this. That is the
    port's vocabulary to widen rather than something for a scorer to route around.
- **Both sides under an AI Commander at once**: start the daemon with `--ai WEST:1 --ai EAST:4`,
  walk away, and come back to two AI sides having fought over Stratis. One planner instance per
  side, each seeded separately, on the dedicated-server-plus-headless-client topology.
  - Neither Commander can see or spend the other's state, and structurally rather than by a guard:
    the only input a planner has is its own side's Observation, there is no call that assembles one
    carrying both sides, and the ledger is keyed by side.
  - Every Command reaching the port is written down against the Commander that issued it, accepted
    ones included, carrying both the issuer and the side the Command named — the pair `wrong_side`
    exists to distinguish. A Command issued for the other side is refused and attributed. Requests
    arriving over the wire carry the same column, so a human Commander's Command is attributable
    the same way an AI's is.
  - Two decision traces share one log and stay separable: every Commander-caused row carries its
    side, and filtering to one side never turns up the other's Squads.
  - The same pair of seeds replays the same Campaign — ownership, Funds, rosters, standing Orders,
    the outbox and the whole decision trace. Commanders play in a fixed side order rather than in
    the order a session registered them, so the replay does not depend on bring-up order.
  - `just probe spike/probes/two-commanders.sqf` with `CTI_HOLD_HC=1` runs it unattended in-world
    and asserts what only appears at two: both sides fielding a force nobody ordered, neither side
    sending two Squads to one Objective, neither side sitting still, neither side's force growing
    without a ceiling, and the push path never reaching the engine's hundred-drains-a-frame cap.
- The push path's budget is measured and recorded by the run itself rather than estimated. The
  effect pump counts what each drain carried and how many frames it spanned, and
  `tools/push_path_report.py` turns a run's telemetry into `results.env` numbers: the largest
  single handover against the 100-per-frame drain cap, and the worst blocking `observe` — which is
  where both planners run — against ADR-0005's 1000 ms stall cap. Measurements from the first
  two-sided unattended run are in `docs/spikes/0002-two-commanders.md`.
- ADR-0015: two Commanders in one daemon — a planner apiece, a fixed turn order, and a pair of
  seeds as the Campaign's identity. Both sides run the same weights, differing only by seed;
  asymmetric weights as a difficulty lever are rejected for the MVP, because they make "is the
  scorer any good" unanswerable in the same way perfect information does.
- Squads take **Orders**, and an Order is standing rather than a waypoint consumed and forgotten.
  A Commander tells one Squad to Capture an Objective, Defend one, or fall back into Reserve, and
  the three are distinct in the world: Capture searches the ground it is sent to, Defend goes
  there and stays, Reserve walks home and holds its fire. The Order outlives the leader who was
  carrying it — waypoints belong to the group, so the engine promotes a replacement and the Squad
  carries on — and a sweep re-asserts it once the engine considers the waypoint finished, so a
  Squad that chased a contact off its Objective goes back. Ordering a Capture on ground your own
  side already holds is refused with a reason rather than accepted as a no-op.
- A bought Squad gets an id its Commander can say out loud (`WEST-1`), counted up per side so a
  resumed campaign mints the same ids in the same order. The Purchase reply carries it, so a
  Squad can be ordered the moment it is bought.
- A player-led Squad is told its Order rather than made to follow it: the engine's own task
  framework puts it in the diary of whoever is in that group, with the ground as its destination.
  Compliance stays voluntary.
- `tools/port_demo.py` issues Orders as well as Purchases, and the Arma tier can boot the Phase-1
  world against `spike/phase1.cfg` with a one-off in-world probe appended to its harness.
- Objectives change hands by presence and pay income. A side alone in the capture radius takes an
  Objective after a held interval; both sides present makes it **Contested**, which is a real
  state that interrupts a capture, shows its own colour on the map and pays nobody. Every 60
  in-game seconds each side is paid the sum over the Objectives it owns plus a flat stipend, so no
  side can be economically locked out. The rules live in the daemon and are unit-tested there; the
  world only reports who is standing where.
- Income accrues in in-game seconds, so it stops when the Play Session does without anything
  having to know what a session is. A report arriving late still pays every tick it covers, and
  time stepping backwards is a mission restart rather than a refund.
- Command Port, in-world side: a single server-side gateway is the only function a client may
  `remoteExec`, with `CfgRemoteExec` locked to mode 1 on **both** `Functions` and `Commands` —
  a mission that locks only `Functions` leaves the whole scripting-command surface open. The
  gateway stamps the commanding side from the caller's own identity and overwrites whatever the
  client claimed. Accepted effects ride the outbox and a server-side pump applies them and
  acknowledges only what it carried out, so a failed effect is redelivered rather than lost.
- SQF speaks the Command format through constructors generated from the same Python source the
  daemon validates with, so the two cannot drift. `toJSON`/`fromJSON` (engine-native since 2.18)
  carry it, which means no hand-rolled JSON encoder and no escaping bugs.
- `tools/port_demo.py` issues Commands to a running daemon the way the AI Commander will.
- Command Port, daemon side: one schema source defines Commands and the effects they produce, the
  daemon is the sole validator, and a single entry function is the only thing that moves strategic
  state. Purchase spends Funds from a per-side ledger, queues its Squad-spawn effect on the outbox
  rather than returning it, and reports only the remaining balance. Insufficient Funds, an unknown
  Command, a malformed Command and commanding a side that is not yours are four distinct typed
  rejections — as against an unknown *transport* verb or an unparseable line, which stay errors.
- Squad prices, the starting balance and the stipend are authored in `config/economy.json`, so
  playtest tuning is an edit rather than a code change.
- Addon functions are declared in `CfgFunctions` and resolve by name as `cti_fnc_*` — from the
  mission, from `remoteExec` and from the addon itself. Verified on the dedicated server, which
  now loads the addon during the Arma tier.
- The Arma tier can drive a real player client end to end with nobody at the keyboard: it
  connects, takes a role and enters the mission by itself. `skipLobby = 1` does the work, because
  the server initialises its own mission before any client connects and there is therefore a
  running mission to be dropped into. No input injection, and no focus taken from other windows.
- Mechanical desync oracle for the open Windows-client desync (#8). The server samples every
  connected client's `networkInfo` and reports the worst reading over a window, so "a client stays
  responsive for a sustained period" is a number rather than a recollection. No client in the
  window is reported as `no_client`, never as steady. The Arma tier can also launch on engine
  defaults instead of the hand-written `basic.cfg`, which is candidate cause 2 on that issue.
- Stratis map manifest: eight Objectives with stable authored IDs, capture radii and an adjacency
  graph, plus both Bases and the HQ structure each would lose to Decapitation. Positions are the
  engine's own, read out of `CfgWorlds`, not eyeballed off the map. Authored once as JSON, read by
  Python directly and by SQF through a generated HashMap, so the two cannot drift.
- Manifests are validated before they can reach a Play Session: ID shape, capture radius, income,
  one Base per side, distinct HQ structures, and the adjacency graph the AI Commander will reason
  over — every edge mutual, every Objective reachable from a Base. A stale generated file fails
  `just check` as `schema_stale`.
- Phase-1 Stratis mission, thin per ADR-0007: two Commander slots, the named `HeadlessClient_F`
  slot, the two Base HQ structures, and nothing else. The addon builds the world from the
  manifest — every Objective marked with its owner, Neutral at boot, both Bases visible — and
  refuses to build at all rather than booting a half-built world.
- The Arma tier takes a mission, a server config and a log prefix, so it can boot the Phase-1
  world as well as the phase-0 spike. The Phase-1 server config keeps `localClient[]` to loopback:
  the LAN address the spike config carries there is candidate cause 1 on the open desync (#8).
- Real daemon (`cti-daemon`), replacing the phase-0 echo stub. Same transport the spike measured —
  newline-delimited JSON on TCP loopback, one connection reused across calls — with an envelope
  worth relying on: every request carries an id and every reply echoes it, and success, a
  domain-level rejection and an error are three outcomes the caller can tell apart. A malformed
  line costs one reply, never the connection.
- Acknowledged delivery for messages the daemon pushes to the game. Callback delivery is
  at-most-once across mission boundaries (ADR-0005), so the daemon holds each pushed message until
  the game acknowledges its sequence number and replays anything unacknowledged. Acknowledging
  twice is ordinary; acknowledging a sequence that was never issued is refused.
- Structured daemon telemetry as JSON lines, per request. Observability only, never read back as
  campaign state (ADR-0003) — which is why a failure to write it is swallowed rather than raised.
- Seeded PRNG adapter: the only sanctioned source of randomness in SQF. It wraps the engine's own
  `seed random x` rather than a hand-rolled generator, and hides both of that command's silent
  footguns — a seed truncated towards zero, and an upper bound that is included where plain
  `random`'s is excluded. A stream is `[seed, draw count]`, so it survives a snapshot and resumes
  where it left off. Determinism, both footguns, the integer range and serial independence are
  asserted against the live engine, not assumed.

### Changed

- ADR-0006 is now accepted unconditionally: the phase-0 contingency is discharged, and the ADR
  absorbs the spike's constraints (port range 2402–2406, missions as PBOs, no RPT file on a Linux
  server) plus a version-parity policy for when Arma 2.22 ships.
- ADR-0004 and ADR-0005 amended with measured constraints: the shim keeps one persistent TCP
  connection (~3× faster than per-call connects), and nothing in the Command Port may require
  sub-frame push latency, because `ExtensionCallback` is frame-bound at 8–17 ms.
- ADR-0005 and ADR-0008 amended with the Observation's delivery decision: the strategic picture is
  pull-only on the synchronous path, because an Observation is *state* — losing one costs nothing,
  since the next report supersedes it — where an effect is an *event* and must ride the outbox's
  acknowledgement and replay. Consequences recorded: the daemon can never volunteer a picture, so
  freshness is the report interval; the whole picture must fit one 10,240-byte return; and delta
  observations are rejected, because a delta is an event and would drag the callback path back in.
  ADR-0008 records that the Observation is the snapshot's set minus the save-only fields, so a
  planner is tested against the schema that survives a resume.
- ADR-0004, ADR-0005 and ADR-0006 amended with engine limits found by cross-referencing phase 0
  against the full wiki snapshot: a `callExtension` return is capped at 10,240 bytes (chunking
  needed before snapshot save/load), a blocking call stalls the frame and warns at 1000 ms, the
  callback path drains at most 100 messages per frame and is at-most-once across mission
  boundaries, and 2.22 changes the extension error surface — prime `engine_drift` suspect on
  update.

- `just` command table in `CLAUDE.md` now lists the recipes that exist; the acceptance tiers are
  marked as Phase 1 work.
- *Read first* in `CLAUDE.md` now explains how to navigate the wiki snapshot: guessable paths,
  `MANIFEST.json` as the lookup, per-directory `INDEX.md` instead of listing a 2,672-file
  directory, and the two traps — categories live in the file header rather than the wikitext, and
  pre-Arma-3-only pages are excluded, so a miss is not proof the wiki lacks the page.
- Vendored snapshot of the Bohemia wiki (`docs/reference/arma-wiki/`), because the live wiki is
  unreachable from this project's environment and Arma 3 has been static at 2.20 for over a year.
  Now the whole wiki rather than nine hand-picked pages: 6,690 pages across scripting commands,
  functions, engine topics, class-name tables and the templates needed to read `{{RV}}` markup.
  Pages are bucketed by subject at predictable paths (`commands/setDamage.wiki`), each carries its
  categories in the header — they are template-generated, so grepping the wikitext finds none —
  and `MANIFEST.json` is the authoritative title-to-file lookup plus the redirect alias map.
- Lint-after-edit hook enabled for SQF, config and Rust edits — advisory only; `just check`
  remains the gate.
- The "no bare `random`" contract is now enforced by `tools/check_sqf_bans.py`, which allows the
  command in the seeded PRNG adapter and nowhere else. HEMTT's `banned_commands` lint is
  all-or-nothing and HEMTT 1.20.1 has no file-scoped suppression, so `random` is exempted there
  and re-banned here with the scope the contract actually wants. `sleep` and `uiSleep` stay banned
  by both.

### Removed

- Phase-0 stub daemon and its test. It echoed requests with timestamps and had no request
  identity, error vocabulary or delivery guarantees; the real daemon supersedes it.

### Fixed

- The shim's round-trip benchmark was timing requests the daemon never understood: it built its
  own payload, left over from when the daemon was an echo stub that accepted anything, and every
  spike run left about a hundred `malformed_request` records in telemetry. The payload now comes
  from the caller, which is also the shape ADR-0005 asks for — the shim has no business knowing
  what the daemon accepts.
- A headless client never entered the mission: its `HeadlessClient_F` slot had no `name`, and an
  unnamed slot is never assigned.
- The auto-format hook ran `rustfmt` at edition 2021 against an edition 2024 crate, so it wrote
  files that `cargo fmt --check` then rejected.
- The scoped SQF ban gate descended into nested agent worktrees under `.claude/worktrees/`,
  where every copy of the PRNG adapter fails the path-based allowlist, so `just check` broke in
  the main checkout whenever a worktree existed. `.claude` is now excluded; each worktree runs
  the gate on its own tree.
