# Dispatching a review

The shape of the review seat: what a review dispatch is handed, what it must hand back, where
its claims go, and what now happens to a confirmed claim. Binding decisions: ADR-0061
Decision 3 (review is eligible on a foreign lane, and provider diversity is the point), the
human's ruling on #228 (a review lands nothing — its output is claims, each checkable
against the code it cites), the human's ruling on #353 (2026-08-14: a review **is passed the
implementer's gate report rather than re-running it**, as clarified on 2026-08-20 in #449),
and, until #328, the admission bar.

**ADR-0071 supersedes the first and third of those**, and this document has not yet been
fully re-based on it: ruling 1 rescinds the foreign-lane concept Decision 3 rests on. Ruling
6 withdrew the admission bar, and #328 dropped it: the two operations this document's closing
section used to route into it — a confirmed post-close finding marking the reviewed issue
unclean, and a reviewer's citations counted against its own seat's bar — **now have no home
at all**, and the sections below say so where they used to say where. Their intended home is
the observatory (#336), which is not built. What ruling 4 *has* changed here is the
permission-mode paragraph and the resolution rule below it, both of which are now mechanism
rather than instruction (#322).

The lane and profile machinery is `docs/multi-provider-dispatch.md`; nothing here restates it.

## Why the seat exists at all

`tools/dispatch.py`'s `SEATS` has carried `"review": True` since #223 and had never been
dispatched. Meanwhile every other quality signal this project has is a gate: `just fast`, the
regression corpus, the hooks, `cog verify`. Those catch a wrong answer. None of them catches
a diff that is right and badly built, cites an ADR it contradicts, or grows a convention
sideways — and that is the gap the seat fills.

Two providers over one diff is **one review pass with two lenses**, not a second pass
(`CLAUDE.md`, Working style). A single lens is a complete review; the second lens is the
diversity ADR-0061 Decision 3 wants, because one model family's blind spots are not another's.

## What the seat is handed

Six things, and the dispatch record carries four of them by construction:

- **the landed SHA** — `--base-sha <sha>`, which lands in `cti.base_sha` on the run's
  telemetry, so the review's ledger row names the commit it reviewed;
- **the issue** — `--issue <n>`, the issue that landing closed, which is also the issue a
  confirmed defect gets raised on, and — since #322 — the key the reviewed profile is derived
  through;
- **the profile under review** — `--reviewing <profile>`, which resolution removes from the
  seat's preference list before walking it — along with every other profile the issue's own
  records place on the work, dispatch records and declared authorship both (#402) — and which
  the dispatcher checks against those records rather than taking on the caller's word;
- **the close audit** — read by the reviewer from the issue thread, because the audit is what
  states which criteria the landing claimed to meet and a review that does not read it can
  only check the code against itself;
- **the implementer's pasted gate output** — the gate record the 2026-08-14 ruling puts in
  the review's hands in place of a gate run (#353). The paste must carry `just check`,
  `just unit` **and** `just mutation` **with their result counts**, including `just
  mutation`'s own `mutation smoke: run was sampled` or `mutation smoke: run was exhaustive`
  line verbatim — unconditionally, not only where a kill rate is quoted (#421): #344's
  round-2 review found an exhaustive 91% hiding behind a
  reported `rate=100%`, because the sample missed both survivors on the line the round had
  just added. A paste that is absent, thinner than that, silent on counts, or silent on
  sampled-or-exhaustive is a finding — the reviewer reports it as an observation rather
  than running anything;
- **a worktree at `origin/main`** — `just worktree add issue-<n>`. The reviewed SHA is reached
  with `git show`, and the tree's own head is recorded, because a citation into a landing that
  a later commit has moved is stale rather than wrong and the two must be distinguishable.

The permission mode is **`plan`**, and since #322 the seat forces it rather than asking the
caller for it. That is the mechanical face of "a review lands nothing": read-only tools and
read-only Bash work in it headless, and no edit can be applied. Verified before first use — a
`plan`-mode headless run executed `git rev-parse --short HEAD` and returned its output. The
brief forbids landing as well, but the brief is an instruction and the mode is a mechanism.

**What that mode is for, after #449.** The clarification of 2026-08-20 narrowed the test rule
and left this one alone: the mode enforces that a review neither edits nor lands the change it
judges — ADR-0071 ruling 4's never-alone invariant — and it is *not* the statement of what a
reviewer may run or file. The three replacements weighed against keeping it are recorded in
`tools/dispatch.py` beside the registry row, with why each trades a mechanism for a sentence.
The consequence is stated plainly rather than glossed: under `plan` a review dispatch cannot
land a **review-specific gate**, which the ruling permits it to do. That is not a bar the
ruling meets, because a review-specific gate is a change like any other and lands through an
implementer dispatch on its own issue; the seat's containment never blocked that route, and a
review that wants such a gate proposes it as a finding.

Forced, because a default is not a containment. `--permission-mode` defaults to `acceptEdits`,
which is writable on both runner families, so until #322 a review dispatched without the flag
could edit — and the sentence above described what a careful caller would type rather than what
the dispatcher would do. `tools/dispatch.py`'s `review` seat now carries the mode in the
registry and `routed` writes it over whatever the caller passed; on the `claude` family that is
`--permission-mode plan`, and on `codex` the sandbox mapping renders it `--sandbox read-only`.
The override is printed, in the dry run and on the record, as
`route_permission_mode=plan forced_by_seat=review`.

**Since the human's ruling of 2026-08-14 (#353), the mode is not the whole of the rule — the
seat does not re-run the implementer's tests.** The ruling reversed the 2026-08-13 ruling
recorded in #353's body, which would have given the seat an executable read-only mode: its own
worktree, `git checkout`/`git fetch`, `just fast`. The answer given instead was
*"reviewer must not trigger tests themselves"*, so the review does not check out the branch
under review, does not run `just fast` or any rung of it, and — the question #353 left open,
now decided — **does not run `just mutation`**, whose mutants touch tracked files in place
even though the sidecar restores them. The gate record a review reads is the implementer's
paste, above. What this leaves the verdict resting on is stated rather than glossed over:
judgement on the diff plus trust in a paste, with `just land`'s re-gate after rebase — which
no flag skips — as the one independent re-execution. The `codex` lane's inability to run the
gate (#265's sandbox ceiling) is therefore **moot for this seat rather than blocking it**: no
review runs a gate on any lane, so a `codex` review reports no `gate=not_run` shortfall
against its peers. The ceiling still bites `codex` as an *implementer*, where
`docs/agents/orchestration.md` states it.

**The human's clarification of 2026-08-20 (#449) says what that ruling never said.** In their
own words: *"#393 ruling was intended to prevent reviewers from re-running tests. They should
be passed test reports to examine, not rerun them (so we avoid the significant wall time
cost). They can of course land review-specific gates and post their own findings."* Three
things follow, and the first is the correction.

- **The bar is re-running the implementer's suite, and its reason is wall time.** Everything
  the paragraph above states about `just fast`, its rungs and `just mutation` survives intact.
- **The seat was never told to run *nothing*.** That was this document's transcription, and
  the brief template below carried it as *"A review also runs nothing"* alongside *"do not
  file an issue or a comment"* — a consequence nobody had ruled. Both are gone.
- **Posting its own findings is the reviewer's, not a favour from the orchestrator.** The
  cost of the wider reading is measured: in the session of 2026-08-19/20, fifteen verdicts
  (#421, #427, #422, #419, #433, #425, #410, #424, #370, #438, #437, #443, #441, #440, #436)
  were relayed by hand, each a plan read, an extraction and a `gh issue comment`, and every
  extraction was a retyping risk the paste discipline below exists to remove.

**Both runner families have been observed posting from `plan` mode, and the mode is
unchanged.** On `codex`, dispatch `d-20260820-110847-f9b197` — `seat=review`, `lane=codex`,
`permission_mode=plan`, argv ending `--sandbox read-only` — ran `gh issue comment 434` from
inside its own sandboxed session and created comment `5355112577` at 2026-08-20T11:14:56Z,
seconds before the run ended. On the `claude` family, dispatch `d-20260820-113736-1c53a4` — the
`zai` review of the commit that first drafted this section — posted its findings to #449 as
comment `5355396609` at 11:44:10Z.
Neither was relayed. The fifteen relays above measured the instruction rather than the
mechanism: every one of those reviews had been told its findings were not its to file.

**The first draft of this section said the opposite about `codex`, and it was false.** It
read: *"`plan` renders `--sandbox read-only`, and `_codex_sandbox_argv` grants that branch
neither `writable_roots` nor `network_access`. `gh issue comment` needs the network, so a
`codex` review cannot post."* The dispatch record disproving it was on disk an hour before
that commit. The error is kept on the page rather than silently replaced, because #449 exists
over an unverified sentence surviving under a green suite, and this was the same move inside
its own correction. Its mechanism is worth knowing: `network_access` is a
**`sandbox_workspace_write`** setting, so the grant attaches to the `acceptEdits` branch
alone. *`_codex_sandbox_argv` grants nothing on the read-only branch* is a fact about that
function; *the sandbox blocks the network* is a claim about Codex's own read-only policy,
which nobody here had measured. CLAUDE.md decides between the two — a lane's enforcement is
what it demonstrably runs, never what its provider claims.

**What is still not claimed.** Two runs are an observation, not an invariant: nothing here
says every `plan`-mode review will be permitted to post. The brief tells the reviewer to
attempt the post and to report a refusal among its findings, so a family, mode or runner
version that does refuse is recorded the first time it happens rather than assumed away, and
the orchestrator relay stays available for that case. Whether the relay can be retired as a
standing step is #393's question, not this document's.

### The reviewer is never the reviewed profile

A review dispatch declares the profile whose work it reviews — `just dispatch --seat review
--reviewing <profile> …` — and resolution removes that profile from the seat's preference list
before walking it, preferring an entry on a different lane among what is left. Without the
rule both seats resolve to the head of one shared list and every review is same-model, which
makes ADR-0071 ruling 4's never-alone a ritual: the whole argument for a second instance rests
on it being genuinely different.

Each of the following was a choice:

- **Every potential author is removed, not only the declared one.** The invariant is that no
  profile that worked on the change produces the verdict clearing it; removing the declaration
  alone enforces the narrower "not the one you named", and on a branch two dispatches touched,
  declaring one left the other eligible to review work it may have coauthored — through a
  field the proposer controls. So the whole set comes out of the candidate list. Over-excluding
  costs a resolution step down the seat's list; under-excluding costs the invariant, and those
  prices are not comparable.
- **What the records support is a *potential*-author set, and the vocabulary says so.** A
  dispatch record is written at plan time and carries the issue, the seat, the profile and the
  lane. Two narrowings can be read off it honestly: a dispatch on a seat marked `reviews` was
  judging rather than doing, and a dispatch whose `result.json` carries a refusal never reached
  a lane. Nothing else — a planner, a recon, a stopped run, a successful no-op and a dispatch
  against a superseded branch are indistinguishable here from the implementer that wrote the
  diff, because **nothing on the record names the commits a run produced**. A superset is the
  right shape for an exclusion and the wrong shape for a claim of authorship, so the route says
  `reviewing_checked` and never `reviewing_verified`. Putting the produced commits on the
  record would make the stronger word available; that is a change to what a dispatch writes,
  and it belongs with #333 rather than here.
- **The subject is named by the caller and checked against the records.** A declaration on its
  own settles nothing: `--profile opus-high --reviewing codex-luna-max` names two registered
  profiles, passes every check, and lets the implementing instance clear its own work while
  the record misstates the subject. So the dispatcher reads this box's dispatch records for
  the issue and refuses `review_subject_contradicted` where a **complete** read carries
  profiles and the declaration is none of them. A dispatch that declares nothing at all is
  refused `review_subject_unknown` rather than quietly resolved.
- **A read that could not complete is not a read that passed.** One unreadable plan, one
  dispatch directory with no plan in it, one plan that does not name its profile, one
  `result.json` that will not parse: any of them
  leaves the route `reviewing_checked: false` with `reviewing_unchecked_why`
  (`no_dispatch_records`, `no_authoring_dispatch`, `records_unreadable`), which is what ruling
  4's landing check (#334) refuses on. The two halves are kept apart deliberately — the
  profiles that *were* read are still excluded, because an incomplete superset is still a
  superset — and a partial read does **not** refuse the declaration, because the record that
  would not open could be the one naming it. Deciding *which* of several profiles a
  multi-dispatch branch should be reviewed past is #333's adjudication and is not done here.

  **The dispatch records are not the only source of authors** (#398). A change under
  `.claude/` is authored interactively by construction — #294 bars a dispatched session from
  writing there — so the scan reads no record at all and the landing rung's empty-set refusal
  (`authorship_unrecorded`) had no route out: #330 sat reviewed and green at `c380689` with
  nowhere to go. An interactive session declares its authorship with `just review-loop author
  --issue <n> --profile <p>`, which writes `authorship.json` beside that issue's loop, and the
  landing rung merges those profiles into the scan's before it checks the reviewer against
  them. The merge only ever *adds*, so nothing about the check above is loosened: it clears
  `no_dispatch_records` and `no_authoring_dispatch` because the set is no longer empty and
  nothing went unread, it never clears `records_unreadable`, and a declared record that will
  not parse refuses `authorship_unreadable` rather than reading as no declaration. The
  declaration is a *declaration*: nothing in an interactive session's environment says which
  model is reading it, so the profile is the session's own word, every entry carries
  `source=declared`, and the clearance prints it with that limit beside it — ADR-0071 ruling
  4's same-user limit, arriving by one more door. What it does not do is claim a dispatch: it
  is its own file in the review root, never a record among the dispatch records, because a
  record of a run that never ran would be a worse answer than the deadlock and every reader of
  that root would meet it.

  **The dispatcher performs the same merge, not only the landing** (#402). Until #402 the
  sentence above described one consumer: the landing rung read both sources and this seat's
  resolution read only the dispatch records, so for an interactively authored change the walk
  could resolve the very profile that authored it — the dispatch spent, the review run, and
  `review_same_profile` refused at the landing on a record the dispatcher never saw, while
  the dispatch's own `reviewing_checked` mark answered over a set missing an author sitting
  on disk. Resolution now merges through the same two functions the landing rung calls, so
  the two consumers cannot disagree, and the mark and `potential_authors` on the dispatch
  record reflect the merged set. The same merge brings the same two fail-closed refusals to
  this surface, under the landing's own names: a declared record that will not read refuses
  the dispatch `authorship_unreadable`, and a record removed after a declaration refuses
  `authorship_lost` — the absence `just review-loop escalate` already refuses, one door
  along.

  Three properties of the record follow from the one direction it must not fail in — an author
  it loses is a reviewer the check stops refusing. **Declaring is one locked act**: the read,
  the append and the write are serialised on the issue's own `flock`, because two sessions
  racing would each write what they read and the loser's author would simply be gone from a
  set whose whole job is exclusion. **The claim is the `(profile, sha)` pair**, so re-running
  the identical command is idempotent and a re-declaration after a rebase is *appended* rather
  than dropped or overwritten — dropping it leaves the trail naming a commit that is not the
  one landed, overwriting erases a declaration that was made, and appending costs the check
  nothing because the set deduplicates on profile. And **the `CTI_DISPATCH_ID` refusal is not
  a barrier**: it reads one environment variable, and a dispatched session running the command
  under `env -u` writes the record — constructed and confirmed on #398's first review round.
  That is recorded at the guard rather than chased, because detecting a session that edits its
  own environment is an arms race and winning a round of it would imply a guarantee this
  cannot give. The limit is ruling 4's own: the accident and the shortcut, not a deceptive
  agent.

  A record can stop answering in three ways, and only two of them were closed above. Bytes
  that will not parse and a document of the wrong shape both refuse `authorship_unreadable`
  and name the fault. A record **removed** does not: an absent record is a legitimate answer,
  because most issues are authored through a dispatch and declare nothing. That reading is
  right in general and wrong where a declaration was made — the profiles it named drop out of
  the exclusion set with no trace, which is the same author-losing failure one door along.
  Where nothing else places a profile on the work, `authorship_unrecorded` still fires and
  already names the repair; where the dispatch records *do* name somebody, that refusal cannot
  fire and the landing cleared with the declared author simply missing, measured on #398's
  second round. It now refuses `authorship_lost`, and `just review-loop escalate` refuses the
  arbiter's walk on the same fact, because that walk takes the same absence for an answer. The
  evidence is the `authorship.lock` beside the missing record: only the writer creates it,
  every reader here is deliberately lock-free, so lock-without-record says a declaration
  reached the writer and its result is gone. Two limits stated rather than engineered around —
  a landing racing a live declaration reads the in-flight window as a loss and refuses, which
  is the safe direction and is cured by running it again; and removing the issue's whole
  review directory takes the lock with the record, leaving nothing to detect, which is the
  `env -u` limit above in another costume and is declined for the same reason.

  The profile-less plan is the one that does not look like a gap: it parses, it carries the
  issue, and it answers a different question from the one being asked. Beside one good record
  a scan that accepted it would report itself complete while that dispatch's profile —
  unknown, therefore possibly the author — was excluded nowhere. A profile the registry has
  since dropped is **not** that case and stays a completed read: it names itself, it is
  excluded like any other name, and calling a retired profile unread would make every later
  scan of that issue partial over a fact its record states perfectly well.
- **A different lane is preferred, not required.** Where the only remaining entries share the
  reviewed profile's lane, one of them is used. The invariant is about the instance producing
  the verdict; provider diversity is the preference, and refusing there would turn away a
  genuinely different model for sharing an endpoint.
- **`review_same_profile` refuses** where the exclusion leaves nothing, and meets a caller who
  names the reviewed profile with `--profile` — or names any other profile the records carry,
  which is `why=named_author`. One refusal kind rather than three, because it is one finding
  reached three ways. It carries no failure class: nothing was found about a provider or about
  the code under test.

**The residual, stated rather than left to be discovered.** These are this box's records. Work
dispatched from another box, or done outside `just dispatch` altogether, leaves nothing here to
read, so a profile that never appears in the records is never excluded and a complete read that
does not carry it will refuse the declaration naming it. The refusal names the remedy — say so
on the issue, or dispatch from a box that holds the record — and closing it properly is the
same missing fact as above: what a run produced, on the record.

## What the seat hands back

A report, in the tier's `key=value` telegraphic form, made of **claims**. Nothing else in the
report can be acted on, and a review with no claims is a complete review, not a failed one.

Every claim is one block:

    claim=<n> route=<defect|observation> file=<path>:<line>[-<line>] sha=<sha>
      against=<the convention, ADR, acceptance criterion or invariant it is checked against>
      scenario=<what goes wrong, concretely — an input, a sequence, a reader>
      quote=|
        <the cited lines, pasted from the tool that printed them>

`route` is the reviewer's **proposal**, not a decision. `CLAUDE.md` requires a review to report
everything it finds and to leave severity filtering to a separate pass, so the reviewer never
withholds a claim on the grounds that it is minor — it proposes `observation` and moves on.
The orchestrator routes.

**The paste discipline binds a review harder than it binds a verdict reader.** `CLAUDE.md`'s
rule — quote the tool's rendered output verbatim, never retype a SHA or a path — exists because
retyping produced a plausible evidence path that resolved to nothing, which is worse than
none. A review is nothing *but* paths, line numbers and SHAs, so every one of them is pasted
from `git show`, `rg -n` or a `Read`, never retyped from memory of what was read.

### The verdict binds the diff, not only the commit

The verdict record beside the review's dispatch names the commit it judged and the exact
identity of the diff it judged (#417): a SHA-256 over `git diff --unified=0 origin/main...<sha>`
with only the line-number ranges inside a hunk header normalised away — the section anchor
after them is content and stays — and an `index` line flattened for a textual file but kept
whole for a binary change, where its blob hashes are the only content the diff carries. So
line offsets a sibling's landing shifts and a textual file's base-side blob hash cannot move
it, while every added and removed byte, which function the change sits in, and a binary
change's actual bytes still do.

**A diff that changes a binary file is not carried across a moved SHA at all** (#419). Its
identity is tagged `binary:` where it is computed, and the landing refuses
`binary_diff_uncarried` whatever the two halves below say. The exemption it replaces rested on
"git will not merge binaries, so a same-file binary edit cannot replay clean", and that is
false: `.gitattributes` decides what git compares as bytes and how git merges it independently,
so `*.bin -diff merge=union` gives a diff git calls binary and a same-file edit git replays
clean, rewriting both blob hashes of the kept `index` line. Binary changes are rare here, so the
refusal costs one fresh review and buys a premise that is true rather than nearly true.

A landing whose rebase moved the SHA carries the review across only where **both** halves hold:

1. **the rebase's own outcome, recorded as a fact.** Only the tool that ran the rebase knows
   whether a hand resolved anything, and hashing the result cannot recover that — a conflict
   resolved with trailing whitespace the reviewer never saw hashed identical under the first
   build's `git patch-id`, which is why #417 was reworked. `just land --stage` and `just land`
   append what they ran to `<review-root>/<issue>/rebases.json` when the replay is clean and
   moved HEAD, and the carry is a reachability walk over those links: any hand-run rebase, any
   commit or amend after a recorded one, breaks the chain and owes a fresh review
   (`rebase_unproven`).
2. **the exact diff identity, matching on both sides** — computed the same way at `just review
   record` over the reviewed commit and at the landing rung over the rebased tree.

The limit, stated once here and in the landing rung's own prose: a matching identity plus
recorded clean rebases proves the diff is unchanged and was mechanically replayed, not that its
meaning survived the move onto the new base — the gate's tests at landing are what catch that
difference, and they still run.

**Verdicts recorded before the rework carry no identity and take a one-time re-review.** The
first build recorded a `patch_id` (or nothing); such a verdict parses to no valid `diff_id` and
the rung refuses `diff_id_unreadable` rather than passing on a hash the rework has retired.
Nothing is migrated — re-run the review dispatch over the same branch and `just review record`
writes a verdict that carries the identity.

### Citations are countable, and since #328 nobody counts them

A citation **resolves** when the quoted text is present at `file:line` at the named SHA. That
is a mechanical check, one `git show <sha>:<path>` per claim, and it was the whole of what the
admission bar's citation floor measured for this seat: at least 90% of a lane's review and
recon citations resolving, pooled over ten dispatches. 90% and not 100% because a citation can
go stale under a concurrent landing through no fault of the reviewer.

**That bar is dropped, and no tool takes the two numbers.** The requirement on the report is
unchanged and is worth keeping for its own sake — every claim carries a `file:line` and a
quote, so a reader can check it in one command — but there is no longer a record it accrues
into, no floor it is held against, and nothing that notices a lane whose citations stop
resolving. The known weakness was already stated rather than fixed (this measures the
citations a reviewer gave and is silent about the findings it failed to raise); what is new is
that even the half it did measure is now unmeasured.

## Scope: grain and structure, not taste

The review checks the diff against **this repo's own written conventions and the ADRs the diff
touches**. Concretely, and in this order:

1. **The issue's acceptance criteria against the code** — does the landing do what the close
   says it does, at the code the close cites?
2. **`CLAUDE.md`'s Contract and Never list** — a bare `sleep` or `random` in SQF, a
   `setGroupOwner`, an edited acceptance spec, a timeout extended to make something pass, a
   failure class that types a failure as something other than what the world said it was.
3. **The ADRs the diff touches** — a diff under `tools/` touching process seams meets
   ADR-0049; one adding a recipe meets ADR-0057's gated-row rule; one adding a probe meets
   ADR-0016's header. The reviewer names the ADR and quotes the clause.
4. **Grain and structure** — a module's seams, a duplicated rule with two homes that can
   disagree, a test asserting on its own mock, a convention landed without its first applied
   instance. This is where a second lens earns its place, and it is bounded by the same rule
   as the rest: a claim cites the line and names the scenario, or it is not a claim.

Out of scope, deliberately: **taste**. Naming preferences, formatting the linters already
decide, and "I would have written this differently" are not claims, because they cite no
convention and describe no failure. Also out of scope: the periodic deep architecture and
design passes, which stay separate (#139). A per-issue review is proportionate to one diff.

## Routing

The orchestrator receives the report and routes each claim:

- **defect** — a new issue, `needs-triage`, naming the reviewed issue, the reviewed SHA, the
  cited `file:line`, and the review's dispatch id. A defect gets its own issue rather than a
  comment because it needs a lifecycle: triage, an assignee, a close.
- **observation** — a comment on the reviewed issue, carrying the same citation. An
  observation is a fact the next reader of that issue should have; it needs no lifecycle.
- **not upheld** — a claim whose citation does not resolve, or whose scenario does not
  survive checking, is recorded on the reviewed issue as checked and not upheld. It is still
  counted in the citation denominator. Silently dropping it would make the seat's bar
  unmeasurable in exactly the direction that flatters the reviewer.

Either route is the reviewer's own to take (human ruling 2026-08-20, #449: *"they can of
course … post their own findings"*), and the seat's contract is still the report — a review
that files nothing has not failed, it has produced its claims. The orchestrator relays where
the reviewer's tool call was refused — a case neither family has been observed to hit, so a
fallback rather than a standing division of labour.

## What a confirmed claim now reaches: nothing

This section used to say how a confirmed post-close finding reached the admission bar's Part
B, whose `unclean` vocabulary — `("rework", "finding", "reopen")`, §3 of #230's derivation —
had "a post-close finding raised on the issue" in it, so a review dispatched after a landing
produced exactly that object with no change needed anywhere.

**#328 dropped that bar, so the object is produced and nothing receives it.** A confirmed
defect is still filed, and it is still worth filing; it simply marks no record. The four
qualifications below are kept because they are how the finding is *judged*, which is a
reader's question whether or not anything counts it, and because #336's observatory will need
exactly these distinctions rather than have to re-derive them:

- **Only a confirmed defect counts.** A claim is confirmed when its citation resolves *and*
  the orchestrator upholds the scenario. An unconfirmed or withdrawn claim is not an unclean
  mark, because otherwise a noisy reviewer could fail another lane's attempt without ever
  being right about anything — the false-positive asymmetry ADR-0061 Decision 3 states would
  turn from cheap into expensive.
- **Observations are never unclean marks.** They carry no defect claim.
- **The filing route does not decide it.** A defect filed as a *new* issue still marks the
  *reviewed* issue unclean: §3 is about the finding's subject, not about where it was typed.
  This is why the routing rule above requires a defect issue to name the reviewed issue.
- **A claim about code the reviewed landing did not touch is not that landing's finding.**
  It is a finding about the repo, and it routes as an ordinary issue against nobody's record.

The window was the bar's own: within seven days of the close, because Part B needed seven days
of rework history. A review dispatched promptly after a landing sat inside it by construction;
one dispatched later produced a real issue and no unclean mark. The window survives only as a
distinction worth keeping, not as a rule anything enforces.

The reviewer's own dispatch was accounted **separately**, against the review seat's citation
bar on the reviewer's lane and profile. One dispatch touched two records that must not be
confused: the reviewed lane's Part B, and the reviewing lane's citation count. Neither record
exists now; the distinction is recorded here so that whoever builds the observatory does not
collapse them.

**The gap, stated rather than papered over — and now wider.** Part B counted findings raised;
it could not distinguish an issue reviewed and found clean from an issue nobody reviewed. That
is the #41 shape — a check that could not run is not a check that passed — and Part A avoided
it by making an unrun criterion `UNKNOWN`. Part B had no equivalent, and creating one would
have meant making a review mandatory per issue, a policy the human had not ruled.

Since #328 the gap is not that a lane could be admitted on a weaker signal than it appeared
to have. It is that **there is no signal and no admission**. A route's quality is unchecked
before its work runs, and read afterwards only by whoever chooses to look, until #336 exists.
Ruling 4's never-alone review is what stands in that place today, and it is a different kind
of thing: it checks a change, not a profile.

## The brief template

Copied, filled and passed as `--brief-file`. The dispatcher's built-in default brief is
deliberately thin and is wrong for this seat — it tells the agent to do the issue's work.

    You are the review seat, reviewing a landed change to the arma-cti project
    (repo andrewesweet/arma-cti, via gh). You are NOT implementing anything.

    Under review: issue #<N>, landed on main as <SHA>.
    Your worktree: <path>, at origin/main. Work only there.

    A review lands nothing. Do not edit a file, do not commit, do not push, do not
    run `just land`. Your permission mode is `plan`, which enforces this; the rule
    is stated as well because a mechanism you understand is one you do not fight.
    Filing is not landing: post your findings on the issue thread yourself with
    `gh issue comment` (human ruling 2026-08-20, #449). If that call is refused,
    say so in your report and let your final message stand as the record.

    A review re-runs none of the implementer's gate. Do not check out the branch
    under review, do not run `just fast` or any rung of it, do not run
    `just mutation` — you are passed their report and the wall time is the reason
    (human ruling 2026-08-14 on #353, as clarified 2026-08-20 on #449). The
    implementer's pasted gate output on the issue thread is your gate record: it
    must carry `just check`, `just unit` and `just mutation` with their result
    counts, including `just mutation`'s own sampled-or-exhaustive line verbatim —
    unconditionally, not only where a kill rate is quoted (#421). A paste absent,
    thinner than that, silent on counts, or silent on sampled-or-exhaustive is a
    finding — report it as an observation rather than running the gate yourself.

    Read, in this order: CLAUDE.md in your worktree; `gh issue view <N>` including
    every comment, and its close audit in particular; `git show <SHA>`; then the
    files the diff touches, whole, where the hunk is not enough. Read the ADRs the
    diff touches — `docs/adr/` — and quote the clause you check against.

    What you check, in this order:
      1. the issue's acceptance criteria against the code the close cites;
      2. CLAUDE.md's Contract and its Never list;
      3. the ADRs the diff touches;
      4. grain and structure — seams, duplicated rules with two homes that can
         disagree, tests asserting on their own mocks, a convention landed with no
         applied instance.
    Not in scope: taste. Naming preferences, formatting the linters decide, and "I
    would have written it differently" are not claims. Not in scope either: the
    periodic deep architecture pass, which is separate work.

    Report everything you find. Do not filter by severity — that happens in a later
    pass, not in yours. Propose a route per claim and let the orchestrator decide it.

    Output contract. Your final message is telegraphic key=value prose and is made
    of claims. Each claim is exactly this block:

      claim=<n> route=<defect|observation> file=<path>:<line>[-<line>] sha=<SHA>
        against=<convention, ADR clause, acceptance criterion or invariant>
        scenario=<what goes wrong, concretely: an input, a sequence, a reader>
        quote=|
          <the cited lines>

    PASTE DISCIPLINE, and it is the rule this seat is most exposed to: every path,
    line number, SHA and quoted line is pasted from the output of the tool that
    printed it — `git show`, `rg -n`, a file read — and never retyped from memory.
    A plausible citation that resolves to nothing is worse than no citation: your
    claims are counted, and a quote nobody can find at that file and line counts
    against your lane's record whether or not the point behind it was right.

    Open with one header block: reviewed=<SHA> issue=<N> tree=<head sha of your
    worktree> read=<what you read> claims=<count>. Close with a scope statement
    naming what you did not review and why. No claims is a complete review; say so
    and stop.

    Report once, at the end. No waits inside your turns.
