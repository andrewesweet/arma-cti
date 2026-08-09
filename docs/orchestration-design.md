# Disentangling the orchestrator

Design study for #242, commissioned by the human 2026-08-06. The question, in substance: the
orchestrator is notionally a pure coordination layer, but it interfaces with the human, verifies
other agents' claims, orders the dependency graph, schedules, banks retro evidence, files issues
and more — all on fable capacity. Which of those need fable, which can move to a cheaper seat,
which to a foreign lane, and which should stop being model work entirely.

**This is not `docs/agents/orchestration.md`.** That document was ruled into existence by the
human on #217 (decision 5, 2026-08-05T21:50Z) and landed at `d53eebe` on 2026-08-08 (#267); it is
the *operating* half — the rules a dispatching seat must not get wrong in the moment. This
document is that one's input: what the mechanism should be, and what is left over once it exists.
The two should not be merged, for the reason #220 measured — the always-loaded prefix is read by
every agent on every lane, so a rule only the dispatching seat can act on is a candidate for not
being resident, and a design study is not a rule at all.

## Status, as of 2026-08-09 (#242 closed)

This is a study, not a live rule; read it for reasoning, and read the operating doc for what to do.
Every proposal below was ruled by the human on 2026-08-06 (rulings and follow-ups on #242) and
every ruling that created work has been executed, except where named:

| §  | Proposal | Where it now lives |
|---|---|---|
| 2 | The queue as data, the freeze as a dispatch rung | `just queue` (#250); the routing policy generalised to a file `just dispatch` reads per dispatch (#266) |
| 3 | The computed close audit | `just admission audit` (#252) |
| 4 | The runbook's two computable procedures | `just recover` (#253) |
| 5 | Composed briefings | `just brief` (#251), which now also carries the single-shot contract (#279) |
| 6 | The seat inverts to opus/high, fable dispatched | Ruled and in effect since 2026-08-06; running as the pre-registered trial `cti.admission.orchestration-trial/242`, **1 of 10 cycles recorded** at the time of writing |
| 7 | The review function | Confirmed unchanged, not altered |
| 8 | Context hygiene | `docs/agents/orchestration.md` (#267), which carries the one-line rule §8 yields |

Landed since, and not proposals of this study: the underfill verdict in `just watch-report` (#278),
the dispatch completion edge (#280), and the dispatch's measured cost and the cohort barrier behind
the seat's idle time (#295, `docs/research/dispatch-cost-and-occupancy.md`) — which is the first
measurement of the §6 "unpriced" gap, on the dispatch rather than on the seat's whole session.
Outstanding: #255, the human-interlocutor seat at opus/xhigh (ruling 2, filed and open), and #295's
`just occupancy` command-table row, which waits on the sign-off gate.

## Outcome

Four tool halves absorb what is today rule-based orchestration held in a fable context: a queue
the scheduler reads (`just queue`), a composed dispatch briefing (`just brief`), a computed close
audit (`just admission audit`), and the recovery runbook's two computable procedures
(`just recover`). Together they take the freeze, the WIP limit, the in-flight set, the gate
choice, the landing-to-issue join and the resumption briefing's first two reconstructions out of
an orchestrator's head and into files that a session already running can read.

What is left is smaller than the eight-role inventory suggests, and it splits cleanly in two. The
**standing loop** — read the watchers, pick the next issue, write the variable half of a briefing,
dispatch, read a verdict, judge a close — is opus-grade throughout. The **episodic acts** that
genuinely need fable — retros, ADR and `CONTEXT.md` semantics, evidence banking, the #181-shaped
diagnosis call — are, with one exception, *already dispatched away from the orchestrator seat*.
The exception is the seat itself. The proposal is therefore to invert the present arrangement: run
the loop at opus/high and dispatch fable for the named acts, rather than holding the scarcest seat
all day and delegating everything else out of it.

Nothing here claims a token saving. Every mechanism below is justified as a correctness or
consistency win, on the same honesty `just watch` records in its own header — it is a correctness
mechanism, not a token one — and the one measurement that would price this design does not exist
yet (see §7).

## 1. Where the eight roles stand today

The inventory is the sitting orchestrator's, from one session's evidence (#242's body). The
middle column is what already carries the role; the right column is what this design proposes.

| Role | Carried today by | Proposed |
|---|---|---|
| (a) Human interface — rulings intake, status, questions | Nothing mechanical. Continuity and judgement | Unchanged. Seat is the human's preference, not a mechanical question (§6) |
| (b) Dispatch routing — queue scan, WIP and reservation enforcement, sequencing-by-surface, briefing composition | Orchestrator memory, `just dispatch`'s ladder (breaker, admission, off-peak), the worktree protocol | `just queue` (§2) and `just brief` (§5). The freeze and the WIP limit become dispatch rungs |
| (c) Claim verification — closes against landings | `just verdict` and the paste rule, `just land`'s pasted output, `just admission record`, `just ledger-sync`'s landing join (7bc3f72) | `just admission audit` computes what `record` today asks an agent to assert (§3) |
| (d) Stall handling | `just watch`, `just watch-report`, ADR-0053's noticing/prodding split | `just recover check` for the BLIND by-hand look; the prod stays judgement (§4) |
| (e) Retro evidence banking | Judgement. The retro is already a dispatched agent | Unchanged, and fable (§6) |
| (f) Triage and same-session filing | Light judgement | Unchanged; mechanical or implementer seat |
| (g) Crash recovery | `docs/agents/recovery.md`, hand-run | `just recover brief` computes reconstructions 1 and 2 of three (§4) |
| (h) Process-instruction execution and memory | Judgement plus gated-surface care | Already ruled: drafting slack on a gated semantic surface dispatches to `cti-implementer` or above (#217 decision 4). Memory state moves into §2's policy file |

Two roles are already further along than the inventory implies. (c) has shrunk twice this week —
`just verdict` renders what a close quotes, and 7bc3f72 bound a landing to the dispatch that could
have made it, which is exactly the "did this close's SHA come from this work" question an
orchestrator used to answer by reading. (e) and the fable-shaped diagnosis calls are dispatched,
not held: the twenty-fifth retro ran unattended from its own `retro-25` tree.

## 2. The queue as data

### What the file is not

It is not a copy of the issue list. GitHub Issues is the tracker (`docs/agents/issue-tracker.md`),
a second copy would drift, and drift on a coordination surface is the failure #186 exists to catch
one level down. The queue is a **derived view** over three sources, only one of which is a file
this project writes:

1. **Candidate work** — `gh issue list --label ready-for-agent`, read live, never copied.
2. **Policy** — the freeze, the carve-outs, the WIP limit, the reservations. These are the human's
   rulings and exist in no machine-readable place at all today; they live in orchestrator memory
   and in issue comments. This is the file.
3. **In-flight** — derived from the box, never counted by hand (below).

### The policy file

`~/.arma-cti/queue/policy.json`, with `~/.arma-cti/queue/transitions.jsonl` beside it. JSON,
because ADR-0049 already names JSON as the structured format the tools speak and because the
breaker, the admission bar and the ledger all use exactly this pairing — a state document plus an
append-only transition journal, both outside every worktree.

Outside the repository rather than in it, for the reason every other piece of orchestration state
is: `~/.arma-cti/runs/`, `~/.arma-cti/dispatches/`, `~/.arma-cti/watch/`, `~/.arma-cti/slots/` and
`~/.arma-cti/breaker/` are all there. A tracked file would put a gate cycle between a human's
ruling and its taking effect, and would collide across the concurrent worktrees that make this
project's ADR-numbering rule necessary. The durable *record* of a ruling stays where it already
is — an issue comment, quoted into the policy entry.

```json
{
  "version": 1,
  "wip_limit": {"value": 3, "ruling": "human, 2026-08-04; see wip memory + #217", "since": "..."},
  "freeze": {
    "state": "frozen",
    "since": "2026-08-05T10:15:47Z",
    "ruling": "human, orchestrator session ~10:15Z; recorded #217 2026-08-05T17:12Z"
  },
  "packages": [
    {
      "name": "multi-provider dispatch",
      "issues": [221, 222, 223, 224, 225, 226, 227, 228, 229, 230],
      "exempt_from_freeze": true,
      "wip_reserved": 2,
      "since": "2026-08-05T17:12Z",
      "ruling": "human at close-down 2026-08-05; scope to be confirmed with the human, not inferred"
    }
  ]
}
```

**Every entry carries a `ruling`, and a write without one is refused.** That is admission's
discipline — every Part A criterion is a required choice with no default, because a criterion
nobody passed is a criterion nobody checked — applied to the one surface where the project's
scheduling rules currently have no provenance at all. The carve-out above is the worked case: the
human's own words say confirm the package's scope rather than infer it from what is landing, and a
policy entry that cannot quote a ruling is exactly the inference that instruction forbids.

### Who writes it

The **orchestrator transcribes**, and the transcription is the judgement. Rulings intake stays a
human-facing act; what changes is that its output is a validated write rather than a memory:

```
just queue freeze  --ruling "<quote or issue-comment URL>"
just queue open    --ruling "..."
just queue wip     --limit 3 --ruling "..."
just queue package add --name "..." --issues 221-230 --exempt-freeze --reserve 2 --ruling "..."
just queue package drop --name "..." --ruling "..."
```

Every write appends to `transitions.jsonl`. The file is never hand-edited; a read that finds an
unknown key, a missing `ruling` or a malformed entry refuses `policy_invalid` and is not a result,
because a policy nobody can parse is not a policy that permits.

### Who reads it

```
just queue state              every policy entry with its ruling, the in-flight list, the derived count
just queue next [--count N]   the next dispatchable issue(s), with the derivation — or a named refusal
just queue check --issue N    one issue, as an exit code — the pre-dispatch read
```

`just queue check` joins the dispatch ladder beside the breaker, the admission bar and the off-peak
rule, which is where #241 also puts its readiness rung. `just dispatch` reads it before it plans
anything, on the pattern `just breaker check` already set.

### The freeze becomes a rung, and that is the point

The strongest single item in this design is the smallest. The human recorded a caveat on #217 at
2026-08-05T17:12Z and the twenty-fifth retro deliberately declined to land it, because the seat
holding the retro could not read orchestrator memory: *a freeze recorded on an issue and in memory
does not reach an orchestrator session already running — the same shape as ADR-0042's stale-copy
window.*

A freeze in `policy.json`, read by `just dispatch` at dispatch time, **does** reach a session
already running, because the read happens per dispatch rather than per session. That converts a
propagation hole into a mechanism, and it is the same conversion #238 already made for the
off-peak window: a human's standing rule, enforced by refusal, with no override flag and no
environment variable, because the rule is the human's and only they amend it.

The refusal follows #238's precedent exactly, including the part that is easy to get wrong: it
**carries no failure class**. Nothing was found about any provider, any lane or any code; this
project simply declined to spend now. Refusal names:

| Refusal | What it says |
|---|---|
| `dispatch_frozen` | The freeze, its ruling, and every carve-out package by name |
| `wip_reached` | The limit, and the in-flight list it was derived from — never a bare number |
| `surface_conflict` | The in-flight issue already holding the surface, and which paths |
| `no_ready_issue` | Nothing labelled `ready-for-agent` survives the filters |
| `policy_invalid` | What in the file could not be read. Not a result |

### Deriving in-flight, and a measurement that constrains it

An issue is in flight from dispatch until close. Counting that by hand is what the WIP rule asks
an orchestrator to do today, and a hand count is the shape ADR-0051 already ruled against: the
count follows the list.

Measured on this box during this study: `just worktree list` reports **93 registrations**, of which
all but a handful are harness-created `agent-<hex>` isolation trees, against **6** records under
`~/.arma-cti/dispatches/`. So neither source alone is a WIP signal — the harness makes a tree per
session including read-only ones, and `just dispatch` is not yet the only door onto work.

The sound derivation is the union of two things that *do* name an issue:

1. `.claude/worktrees/issue-<N>` trees present in `tools/worktree.py list` — the shape
   `just worktree add issue-<N>` makes, which every dispatch briefing already calls for;
2. `~/.arma-cti/dispatches/<id>/dispatch.json` carrying an `issue` and having no `result.json`.

Union by issue number; drop any whose GitHub state is closed, and report those separately as
`just worktree done` owed rather than silently. `agent-<hex>` trees are excluded by name, and the
93-against-6 measurement is why that exclusion is stated rather than assumed.

**Stated limit, not papered over:** an agent dispatched against an issue that neither runs
`just worktree add` nor goes through `just dispatch` is invisible to this count, so the count is a
**floor**. The mitigation is that `just queue next` prints the list it derived the count from, so
an undercount is visible to the reader rather than hidden inside a number — #209's rule read in the
right direction, since here the list *is* the evidence and the number is the summary.

### What the queue deliberately does not decide

- **Readiness** — whether an issue's acceptance criteria exist and name an evidence shape is #241,
  already filed, already scoped as a ladder rung. The queue consumes its verdict and does not
  invent a second one.
- **Lane and profile** — the breaker and the admission bar own that, and `just dispatch` already
  reads both.
- **Semantic dependency order** — that issue X's design decides issue Y is not computable. Proposal:
  the queue reads an optional `Blocked-by: #N` line from the issue body, the same convention shape
  as `Handoff-for:`, and where it is absent the ordering stays the orchestrator's judgement and is
  reported as such. Surface conflicts between *in-flight* trees are computable
  (`git diff --name-only origin/main...HEAD` plus uncommitted) and are; a candidate's surface before
  work starts is not, and an optional `Surfaces:` declaration belongs to #241's readiness criteria
  rather than to a second gate here.
- **Dispatching.** The scheduler selects and prints; a human or an orchestrator dispatches. That
  is ADR-0053's split — the machine's half ends at noticing — and it is the same reason
  `just watch` never messages the agent it watched.

## 3. Claim verification: compute what the bar already asks

`just admission record` today requires a choice on every Part A criterion with no default, and
cross-checks two of them against git in the refusing direction only: a landing that touched an
in-world surface may not have its corpus criterion waived, and one that edited an acceptance spec
or a generated file may not record the hooks as clean. Everything else is asserted by whoever runs
it — which, for a Claude-lane issue, is the orchestrator reading a close against a landing.

**`just admission audit --issue N`** computes what can be computed, as a subcommand of the tool
that already owns the criteria rather than as a new tool with a second copy of them:

| Check | How | Verdict |
|---|---|---|
| The close quotes a SHA that is on `origin/main` | `git merge-base --is-ancestor` | `ok` / `absent` / `not_on_main` |
| That SHA belongs to this issue's dispatch | `tools/ledger.py`'s two tests from 7bc3f72 — descends from the dispatch base, postdates the dispatch's own start — called, not reimplemented | `ok` / `outside_window` / `unbounded` |
| An in-world surface was touched, so a pool verdict is owed | diff paths against the `just regress` row's surface list | `owed` / `not_owed` |
| The quoted evidence path exists and its `pool.json` reads green | read the path; render nothing the path does not contain | `ok` / `path_missing` / `red` / `absent` |
| A gate block is quoted in the close | textual presence of `just fast` / `just land` output | `quoted` / `absent` |
| `CHANGELOG.md` moved with a user-visible commit | not decidable from a diff | `undecidable`, never `ok` |

Two properties matter more than the list. A quoted gate block is reported as **quoted**, never as
proof the gate ran green: the paste *is* the evidence, and a tool cannot re-run history. And the
changelog row reports `undecidable` rather than passing, because a check that could not run is not
a check that passed (#41's shape, and the same reason `just prereqs` reports `unknown`).

The output feeds `just admission record --from-audit`, which fills the criteria the audit
computed and still demands an explicit choice on the rest, so the bar's no-default discipline
survives the automation.

**This is not an added verification pass.** CLAUDE.md bars adding passes, and #220 re-based that
from a quality rule to a first-order cost rule because an extra pass is pure generation and
generation is what this plan meters. What the audit does is move a pass the orchestrator already
runs out of generation entirely and into a tool, which is the right side of that ruling rather
than an exception to it. #235 — `just verdict --post <issue>` — is the adjacent already-filed
piece and is not duplicated here.

## 4. Stalls and crash recovery: the runbook's two computable procedures

`just watch` and `just watch-report` already carry the noticing. Two procedures around them are
still hand-run, and both have now been run by hand twice, which is the codification threshold
`docs/agents/recovery.md` sets for itself ("Two identical saves is this document's codification
threshold").

**`just recover check <name>`** — the BLIND by-hand look. A BLIND finding means the watcher could
not read a worktree's HEAD, which is deliberately not "still running". Resolving it means asking
whether the tree is absent and its output landed (a finished, cleaned agent) or absent with work
unlanded (a lost one). Both the twenty-fourth and twenty-fifth retros resolved BLIND findings this
exact way — four findings across removed prior-art worktrees at the twenty-fourth, two dead
review-watcher assessors at the twenty-fifth. Inputs: worktree presence, registration, HEAD, and
whether that name's commits are reachable from `origin/main`. Verdicts:
`finished_and_cleaned` (naming the landed SHAs), `lost_work` (naming files and unlanded commits),
`still_live`. It **never acks** — `just watch-report --ack` stays the judgement, per ADR-0053.

**`just recover brief <issue|worktree>`** — the resumption briefing's computable halves. The
runbook names three reconstructions the briefing must carry, and omitting any one silently
corrupts the resumed work:

1. what moved on `main` since the dead agent's last commit — commits, ADR numbers landed, issues
   opened and closed in that window. **Computable.**
2. what of its own environment died — worktree state, evidence directories carrying no
   `verdict.json` (ADR-0022: not a result), locks now free. **Computable.**
3. which of its assumptions no longer hold. **Judgement**, and the tool prints the heading with
   nothing under it rather than guessing.

It prints `just handoff <issue>`'s output beside its own, so the predecessor's own account and the
computed delta arrive together — the composition #208 and #210 already built the halves for.

The property worth having is not the saved reading. It is that a tool prints only what it read.
The runbook records a briefing that asserted from "clean, zero ahead" that announced work had died
uncommitted, when the same evidence meant landed; the rule it wrote in response — state what the
evidence shows, not what it implies — is enforced by construction here in a way prose cannot
enforce it, and enforced hardest in the case the runbook says binds hardest, where the briefer is
the party that lost its memory.

## 5. Briefing composition

The twenty-fourth retro measured what dispatch briefings still restate after the handoff template
landed: the #222 re-run instruction, once per briefing, and the worktree protocol paragraph until
#214's recipe deleted it mid-cycle. Its own diagnosis: *operational instruction restated per
dispatch because no mechanism carries it.*

**`just brief <issue> [--seat S] [--out FILE]`** composes the invariant half from data:

- the worktree protocol as the two calls it now is — `just worktree add issue-<N>`, `just worktree done`;
- **the gate line, derived rather than chosen**: an issue whose surfaces reach `addons/`,
  `missions/`, `extension/`, the daemon's world-facing half or the manifests gets `just regress`,
  full corpus, no filter; everything else gets `just fast`. This is a rule-table decision an
  orchestrator makes per briefing today, and a briefing that names `just fast` for an in-world
  change is a defect the table can prevent;
- the landing protocol — `just land`, output pasted — and the Conventional Commits plus `refs #N` line;
- the base SHA and worktree path, as `just worktree add` printed them;
- the live flake lines, read from the tracker rather than remembered — today #222 and #233 — carrying
  the `flake_quarantine` row's required response;
- the paste rule, when the dispatch will read a verdict (CLAUDE.md carries it, and #219's ruling
  says to carry it into any briefing that dispatches a verdict reader);
- the seat and its reason, from the Model roles mapping.

What stays the orchestrator's, and is the actual work: the task statement, the scope boundary, the
ground truth to read, and the reason for a non-default seat. Output is markdown on stdout, or a
file for `just dispatch --brief-file`, which already exists and needs no new plumbing.

**The honest claim.** The composed section is on the order of fifteen to twenty-five lines, and its
token effect is *unmeasured* — #212 owns that measurement, and #208's finding that briefings
carrying a SHA correlate with more state reconstruction rather than less is a warning against
assuming the sign. The value claimed here is correctness and consistency: a derived gate line, a
flake list that cannot go stale, and a protocol that reaches every dispatch without depending on
whether the composing session's memory is current. Anything else would repeat the error #206
corrected when `just watch` was first described as a token mechanism.

## 6. The residue, sized, and the seat

A steady-state orchestrator turn, after the four halves above land:

1. `just watch-report` — silent, or one line per finding;
2. `just queue next` — a candidate with its derivation, or a named refusal;
3. **judgement**: is that candidate the right next thing, given the human's live intent;
4. `just brief N`, then write the variable half — **the real work of the turn**;
5. dispatch;
6. on completion: paste `just verdict`, run `just admission audit`, **judge the close**;
7. episodically: the retro, the rulings intake, the evidence banking.

Steps 1, 2, 5 and the mechanical part of 6 are tool calls. Steps 3, 4 and the judgement in 6 are
model work with a gate behind them — a wrong dispatch is recoverable, a wrong briefing produces a
red, a wrong close judgement is what the admission bar and #240's review lens are for. That is
ADR-0061 decision 2's test read at home: work may leave the scarcest seat where a mechanical gate
catches a wrong answer.

Step 7 is where fable earns its place — and step 7, *with one exception, already runs somewhere
else*. The twenty-fifth retro ran unattended as a dispatched agent from its own tree. Ruling
transcriptions with drafting slack on a gated semantic surface route to `cti-implementer` or above
by the human's own decision (#217 decision 4). The #181-shaped diagnosis call is dispatched. The
exception is the orchestration seat itself, which is fable/high all day.

**Proposal: invert it.** The standing loop runs at opus/high; fable is *dispatched by* the loop for
the named episodic acts — retros, ADR and `CONTEXT.md` semantics, schema semantics, evidence
banking, the #181-shaped diagnosis call — and for the human interface if the human wants a fable
interlocutor, which is a preference and not a mechanical question. This touches CLAUDE.md's Model
roles, a standing human decision of 2026-08-04, so it is a proposal and lands only with sign-off.

Evidence for, and against, stated plainly:

- **For.** The loop's judgement steps all sit behind gates. #219 found that across 40 scored
  readings on the one orchestrator act anybody has A/B'd, every arm at every price read every class
  correctly and every failure was transcription rather than reasoning — the variable was the
  instruction, not the seat.
- **Against, and it is the only real evidence pointing the other way.** #219's discarded pilot: the
  opus/high control cross-checked its reconstructed handoffs against the live repo, found the
  fiction, and declined to write false gate records. That is evidence that a stronger seat verifies
  its inputs unprompted — evidence *for* opus over haiku, and evidence that the handoff-forensics
  half of orchestration has never been priced at any seat. It argues against dropping below opus,
  which this proposal does not do.
- **Unpriced.** Nobody knows what the orchestrator seat consumes. The ledger prices dispatches; the
  orchestrator is a session and has no row. The API's `weekly_scoped` entry showed the fable weekly
  cap at 86% with an active warning (#237, and item 5 of the current #217 pile) — the currently
  binding limit, priced by neither #218 nor #220 and not recorded by the statusline tap. So the
  budget argument for this proposal is directionally obvious and numerically absent, and it should
  be adopted on the gate argument rather than the budget one.

**Pre-registered trial**, in the shape #219 and #224 established — pre-register the criterion, then
measure, and do not move the bar once the numbers are in. Ten consecutive dispatch cycles from an
opus/high orchestration seat. Any one of these fails it:

1. a dispatch launched against a freeze or reservation the policy file recorded;
2. an `infra_unavailable`, `quota_exhausted`, `provider_refused` or `untyped_harness_failure`
   treated as a result;
3. a landing recorded against an issue its dispatch could not have made (7bc3f72's two tests);
4. a gated surface edited without the human's approval or an ADR-0013 record;
5. a ruling with drafting slack transcribed onto a gated semantic surface from the orchestration
   seat rather than dispatched (#217 decision 4).

Plus the human's own read of the interaction quality, which is not mechanisable and is theirs alone.

## 7. The review function (ADR-0061 decision 3, routed here)

Stated explicitly, as #242 asks.

**Fable does not review implementer work today, and no one assigned it that job.** The gates do it
— `just fast`, the corpus, `just mutation`, the criterion audits — and ADR-0061 decision 3 made
review eligible on foreign lanes precisely because provider diversity is the point: one pass with
two lenses, not two passes. #240 stood that seat up and exercised it in both directions.
`tools/dispatch.py`'s `SEATS` admits `review` on a foreign lane and bars `fable` and `orchestrator`
from every foreign lane. So the answer to the commissioning question — does fable need to review
opus work, or can a Codex-plan model — is that a foreign lane already can, it is the ruled design,
and fable reviewing implementer work is a function that exists in nobody's mapping.

**What the orchestrator retains is claim spot-checks, and after §3 the residue is narrow:** whether
a close's reasoning matches what the diff actually did. The mechanical half — SHA on main, SHA in
the dispatch's window, corpus owed and quoted, evidence path resolvable — is computed. What is left
is semantic and is not gate-catchable, which is why it stays with a model rather than a tool.

Three constraints on it:

- **Sampled, never standing.** CLAUDE.md bars adding a verification pass, and #220 re-based that as
  a cost rule. A spot-check on every close is a standing second pass wearing another name.
- **Opus/high**, under the §6 proposal — it is a judgement behind gates, and #240's lens is the
  designed depth review.
- **It reviews claims, not code.** Architecture and design quality are #240's per-issue lens and
  #139's periodic deep pass. An orchestrator reading a diff for taste is scope the review dispatch
  already owns.

## 8. Context hygiene

What the orchestrator stops holding once the tools carry it:

- **the queue ordering** — `just queue next` re-derives it;
- **the freeze, the carve-out, the WIP limit and the reservations** — `policy.json`, which is the
  whole point of §2, since the thing an orchestrator held in memory is the thing that failed to
  propagate;
- **the in-flight set** — derived from trees and dispatch records, never tallied;
- **per-agent chatter and progress narration** — agent reports are already telegraphic; the durable
  record is the issue comment and the commit;
- **watcher plumbing** — `just watch-report` is one line per finding and the full verdict block sits
  in `~/.arma-cti/watch/<name>.finding.json`, outside every worktree;
- **briefing boilerplate** — composed;
- **pool details, dispatch ids, evidence paths** — rendered and pasted, never carried.

What it must still hold, and no tool should try to: the human's live intent this session; the
cycle's shape, because banking retro evidence is judgement about what mattered; the open rulings;
and which issues are *about* the same thing, where no `Blocked-by:` line has been written.

The one-line rule this yields, for `docs/agents/orchestration.md` when it is written: **an
orchestrator's turn opens with `just watch-report` and `just queue next`, and holds nothing between
turns that either would re-derive.**

## 9. Build order, and what is filed

Four implementation issues, filed `ready-for-agent` against #242. Build order:

1. **`just queue`** — the keystone. It is the only one of the four that closes a hole rather than
   moving work: the freeze-propagation caveat has no mechanical answer without it.
2. **`just brief`** — independent of the rest and the cheapest; its gate-line derivation is the
   piece with real defect-prevention value.
3. **`just admission audit`** — depends on nothing new, reuses `tools/ledger.py`'s window tests.
4. **`just recover`** — two subcommands over one shared computation (worktree presence, HEAD,
   landed-ness), so one issue and one `tools/recovery.py`, not two of each.

Each lands under ADR-0049 as Python with pytest, with `just` keeping the process seam. Each new
recipe owes a CLAUDE.md command-table row, which is a gated surface: under ADR-0057's
reconciliation clause the row follows through the sign-off gate rather than lagging silently. These
are ordinary process currency and not multi-provider initiative work, so they route through a retro
under ADR-0063 decision 1's split, **not** onto #248.

## 10. What would overturn this

- **A measured cost that inverts the arithmetic.** If pricing the orchestrator seat (which nothing
  does today) showed the loop's spend to be negligible against the episodic fable acts, §6's
  inversion buys nothing and should not be paid for in disruption.
- **The trial's criterion firing.** Any of §6's five clauses at opus/high sends the seat back to
  fable, and the clause that fired says which capability the cheaper seat lacked.
- **`just dispatch` becoming the only door.** If every dispatch eventually flows through it, §2's
  two-source in-flight derivation collapses to one source and the worktree-name heuristic — and its
  93-against-6 justification — should be deleted rather than maintained.
- **A false gate record landing on the wrong issue.** CLAUDE.md names this as the first thing to
  reopen if it happens: whether a dispatch names the right issue, branch and SHA stays with whoever
  wrote the handoff, not with the reader. §3's audit would then need to move upstream of the close
  rather than sit at it.
- **The human wanting a fable interlocutor.** That is a preference about the interface, not a
  finding about the mechanism, and it settles role (a) on its own terms without disturbing §2–§5.
