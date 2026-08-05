# Dispatching a review

The shape of the review seat: what a review dispatch is handed, what it must hand back, where
its claims go, and how a confirmed claim reaches the admission bar. Binding decisions:
ADR-0061 Decision 3 (review is eligible on a foreign lane, and provider diversity is the
point), the human's ruling on #228 (a review lands nothing — its output is claims, each
checkable against the code it cites), and the admission bar in `tools/admission.py`.

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

Four things, and the dispatch record carries three of them by construction:

- **the landed SHA** — `--base-sha <sha>`, which lands in `cti.base_sha` on the run's
  telemetry, so the review's ledger row names the commit it reviewed;
- **the issue** — `--issue <n>`, the issue that landing closed, which is also the issue a
  confirmed defect gets raised on;
- **the close audit** — read by the reviewer from the issue thread, because the audit is what
  states which criteria the landing claimed to meet and a review that does not read it can
  only check the code against itself;
- **a worktree at `origin/main`** — `just worktree add issue-<n>`. The reviewed SHA is reached
  with `git show`, and the tree's own head is recorded, because a citation into a landing that
  a later commit has moved is stale rather than wrong and the two must be distinguishable.

The permission mode is **`plan`**. That is the mechanical face of "a review lands nothing":
read-only tools and read-only Bash work in it headless, and no edit can be applied. Verified
before first use — a `plan`-mode headless run executed `git rev-parse --short HEAD` and
returned its output. The brief forbids landing as well, but the brief is an instruction and
the mode is a mechanism.

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

### Citations are counted, which is what makes the seat's bar real

A citation **resolves** when the quoted text is present at `file:line` at the named SHA. That
is a mechanical check, one `git show <sha>:<path>` per claim, and it is the whole of what
`tools/admission.py`'s citation bar measures for this seat: at least 90% of a lane's review and
recon citations resolve, pooled over ten dispatches (`CITATION_FLOOR`). 90% and not 100%
because a citation can go stale under a concurrent landing through no fault of the reviewer.

So a review report must be **countable**: the orchestrator checks each claim's citation and
feeds the two numbers to `just admission record --citations-resolved N --citations-total M`.
A claim with no `file:line`, or with a quote nobody can find, counts as a citation that did
not resolve — not as a claim that was never made. The known weakness is inherited and stated
rather than fixed: this measures the citations a reviewer gave, and is silent about the
findings it failed to raise.

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

## How a confirmed claim reaches the admission bar

`tools/admission.py` needs no change for this, and that is the finding rather than an
omission. Part B's `unclean` is §3 of #230's derivation, carried verbatim as
`UNCLEAN_REASONS = ("rework", "finding", "reopen")` — and **"a post-close finding raised on
the issue" is this**. A review dispatched after a landing produces exactly that object.

Four qualifications, which are what the alignment actually consists of:

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

The window is the bar's own: within seven days of the close (`tools/admission.py`'s module
docstring, "Part B needs seven days of rework history"). A review dispatched promptly after a
landing sits inside it by construction; one dispatched later produces a real issue and no
unclean mark, and the record should say which.

The reviewer's own dispatch is accounted **separately**, against the review seat's citation
bar on the reviewer's lane and profile. One dispatch therefore touches two records that must
not be confused: the reviewed lane's Part B, and the reviewing lane's citation count.

**The gap, stated rather than papered over.** Part B counts findings raised; it cannot
distinguish an issue that was reviewed and found clean from an issue nobody reviewed. That is
the #41 shape — a check that could not run is not a check that passed — and Part A avoids it
by making an unrun criterion `UNKNOWN`. Part B has no equivalent, and creating one would mean
making a review mandatory per issue, which is a policy the human has not ruled and this seat
does not assume. Recorded here so that a lane admitted without ever having been reviewed is
known to have cleared a weaker bar than one that was.

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
