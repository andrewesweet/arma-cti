# Dispatching a review

The shape of the review seat: what a review dispatch is handed, what it must hand back, where
its claims go, and what now happens to a confirmed claim. Binding decisions: ADR-0061
Decision 3 (review is eligible on a foreign lane, and provider diversity is the point), the
human's ruling on #228 (a review lands nothing — its output is claims, each checkable
against the code it cites), and, until #328, the admission bar.

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

Five things, and the dispatch record carries four of them by construction:

- **the landed SHA** — `--base-sha <sha>`, which lands in `cti.base_sha` on the run's
  telemetry, so the review's ledger row names the commit it reviewed;
- **the issue** — `--issue <n>`, the issue that landing closed, which is also the issue a
  confirmed defect gets raised on, and — since #322 — the key the reviewed profile is derived
  through;
- **the profile under review** — `--reviewing <profile>`, which resolution removes from the
  seat's preference list before walking it — along with every other profile the issue's own
  dispatch records place on the work — and which the dispatcher checks against those records
  rather than taking on the caller's word;
- **the close audit** — read by the reviewer from the issue thread, because the audit is what
  states which criteria the landing claimed to meet and a review that does not read it can
  only check the code against itself;
- **a worktree at `origin/main`** — `just worktree add issue-<n>`. The reviewed SHA is reached
  with `git show`, and the tree's own head is recorded, because a citation into a landing that
  a later commit has moved is stale rather than wrong and the two must be distinguishable.

The permission mode is **`plan`**, and since #322 the seat forces it rather than asking the
caller for it. That is the mechanical face of "a review lands nothing": read-only tools and
read-only Bash work in it headless, and no edit can be applied. Verified before first use — a
`plan`-mode headless run executed `git rev-parse --short HEAD` and returned its output. The
brief forbids landing as well, but the brief is an instruction and the mode is a mechanism.

Forced, because a default is not a containment. `--permission-mode` defaults to `acceptEdits`,
which is writable on both runner families, so until #322 a review dispatched without the flag
could edit — and the sentence above described what a careful caller would type rather than what
the dispatcher would do. `tools/dispatch.py`'s `review` seat now carries the mode in the
registry and `routed` writes it over whatever the caller passed; on the `claude` family that is
`--permission-mode plan`, and on `codex` the sandbox mapping renders it `--sandbox read-only`.
The override is printed, in the dry run and on the record, as
`route_permission_mode=plan forced_by_seat=review`.

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

Either route may be taken by the reviewer itself where its permissions allow it. Neither is
assumed: the seat's contract is the report, and the filing is the orchestrator's by default.

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
    run `just land`, do not file an issue or a comment. Your entire output is your
    final message. Your permission mode is `plan`, which enforces this; the rule is
    stated as well because a mechanism you understand is one you do not fight.

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
