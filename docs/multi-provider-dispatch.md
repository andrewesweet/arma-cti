# Dispatching work to another provider

The design behind `just dispatch` and `just breaker`. `CLAUDE.md` carries the rules an
agent must not get wrong in the moment — what each seat is for and the two refusals that
survive ruling 1, the credential handling, the prohibition on exporting a lane variable, the
prohibition on inventing a breaker's wait. Not *eligibility*: ruling 1 withdrew that word
along with the ladder it graded, as the paragraph below records.
Everything here is the reasoning under those rules, moved out of the always-loaded prefix
by the human's ruling on #228 (2026-08-05, Decision 2) so that the prefix carries the rule
and this document carries why it is the rule.

Binding decisions: **ADR-0071**, and what it leaves of ADR-0061. Ruling 1 rescinds
ADR-0061 decisions 2, 3 and 4 and decision 1's quality-floor clause, and ruling 6 withdraws
decision 6's admission bar; what survives and governs this document is **decision 5** — a
profile is an opaque token and no cross-provider effort scale exists — together with
decision 1's metering requirement and decisions 7 and 8, which the breaker below implements.
Implementation: `tools/dispatch.py`, `tools/breaker.py`. The ledger that records what a
dispatch cost is a separate document, `docs/telemetry-ledger.md`. The **review** seat has a
shape of its own — what it is handed and the claims-cite-code contract it hands back — and
that is `docs/review-dispatch.md`. Ruling 6 rehomes where a confirmed claim then goes, from
the withdrawn bar onto the observatory; #328 has already removed the bar from the code, and
that rehoming is #335's rather than done — the observatory itself is #336 and is not built —
so a confirmed claim currently reaches nothing.

## Lanes and profiles

A **lane** is a provider and the environment that reaches it. A **profile** is one opaque
`(lane, model, effort)` token in `tools/dispatch.py`'s registry, which now carries
`claude-native`, `zai` and `codex`. Read the registry — `just dispatch --list` — rather than
a count in a document.

The recipe has no `--model` and no `--effort`, and that absence is the design (ADR-0061
Decision 5, which ADR-0071 ruling 1 strengthens by removing its neighbours: with provenance
gone, decision 5 is the only thing standing between this project and an invented ranking of
providers). Effort vocabularies do not commensurate across providers: GLM Max and Opus high
are not the same quantity, and the mapping between them is not monotonic, so a dispatcher
offered both dimensions separately would be inviting an agent to compose a pair no one has
ever measured. A level joins a preference list by being named, never by an ordering inferred
in code.

**Registration on measurement was withdrawn as a rule, by name.** This document used to say
"a profile is measured or it is not registered". ADR-0071 ruling 2 registers three profiles
that fail that test — Luna at maximum effort, Luna at its published default, and Opus at low
effort — with Luna entering **on publication rather than measurement**, at the human's
ruling, and the ADR records it as a named exception to `AGENTS.md`'s validated
measure-before-building rule rather than presenting it as consistent with one. The upfront
bar that would otherwise have judged the new entrants is withdrawn with it, so a new profile
now enters on judgement and the retrospective observatory is what may later contradict that
judgement. On the `recon` seat the exception has **no expiry** and the ADR says so: no gate
reads that seat's output, it lands nothing, and nothing in the design will ever check it —
which is why a recon claim that decides a routing choice is cited.

"It lands nothing" is a property of the harness since #407 and was a sentence about the seat
before it. `SEATS` forced a read-only `permission_mode` on `review` and nothing on `recon`, so
a recon dispatch inherited the writable default and one of them edited `tools/` and its tests
with nothing refusing it. The row now forces `plan` the way `review`'s does — rendered
`--permission-mode plan` on the `claude` family and `--sandbox read-only` on `codex`, with no
writable root and no network access — because an argument that rests on a seat writing nothing
needs the seat to be unable to write, not merely described as not doing so.

The z.ai lane made the argument concrete rather than abstract (#225). Claude Code's five
effort levels differ in the `thinking.budget_tokens` they send, and that endpoint ignores
that field — a hard prompt at budget 1,024 and at budget 32,000 both thought past nine
thousand tokens and both stopped on `max_tokens`. On that measurement all five efforts
are one configuration, and the registry carried one profile per model rather than five.

**A human ruling on 2026-08-19 (#433) overrode that conclusion, not the measurement.**
#432's codex-absence substitution table names GLM 5.3 at High, so `zai-glm53-high` is
registered beside `zai-glm53-max` and the lane no longer carries one profile per model.
The reasoning above was right about what it measured — §2's requests were hand-sent
`curl`s varying `thinking.budget_tokens` alone — but its step to "one configuration" also
rested on the runner sending nothing else for effort, which was asserted from `--help`
and never measured. The installed runner (2.1.235) sends the effort level as its own
request field, `output_config.effort`, unmeasured on this lane; the registry comment in
`tools/dispatch.py` states what is known and the arrangement that would settle it.

**A rename retires a name, and the retired name stays readable (#413).** The registry above
is what a dispatch may take; `RETIRED_PROFILES`, beside it, is what a dispatch *record* may
carry — old name, replacing profile, date. #399 renamed `zai-glm52-max` to `zai-glm53-max`
and every branch authored before that moment kept records the registry no longer resolves,
which stranded them: `--reviewing` refused the old name against the registry and the new
name against the records, with no third answer. The one resolution is read-only — the
review subject check, the candidate ordering and the never-alone exclusion set place a
retired name through its successor — while `--profile` reads `PROFILES` alone and still
refuses the dead name. The successor joins the exclusion set beside the name it replaced,
which is the conservative side of that set's own trade.

## The environment is assembled per invocation

`ANTHROPIC_BASE_URL` in a shell profile, in a `~/.claude/settings.json`, or exported into
a session redirects **every** Claude Code process that inherits it, the orchestrator's own
session included. There is no scope on it smaller than the process tree, which is why the
rule in `CLAUDE.md` is a `Never` rather than a preference.

The dispatcher therefore builds the child's environment for each invocation and exports it
nowhere. Assembly **strips every lane-owned variable from the inherited environment before
adding this lane's**, so a shell that is already carrying one produces the same child as a
clean shell. That property is what makes a dispatch reproducible from its record: without
the strip, the plan in `dispatch.json` would describe the variables the dispatcher added
and be silent about the ones it did not remove.

A lane may also declare what its runner cannot work out for itself. Claude Code recognises
its own model names and knows their windows; it does not recognise `glm-5.3`, assumes
200,000 tokens for it, and auto-compacts against that assumption — which on the `zai` lane
compacted a quarter of sessions against a provider measured at about 1.05M (#444,
`docs/research/zai-lane-live-findings.md` §7). `Lane.context_window` is the one place that
figure is written; a lane that declares one exports it as `CLAUDE_CODE_MAX_CONTEXT_TOKENS`,
and zero means the runner already knows. The variable is lane-owned and stripped like the
rest, for a base URL's reason: it decides when a child compacts, so inheriting it would make
that a property of the shell that dispatched.

Credentials come from `~/.arma-cti/credentials.env` at mode 0600, by environment only.
Never on argv, so never in `ps`; never echoed; and the dispatch record names the key it
used and not its value. `just prereqs credentials` is the only writer of that file, it
reads the value off the terminal with echo off, and it refuses if the path ever resolves
inside a git work tree.

### Codex instruction delivery

Before a Codex child is forked, `just dispatch` runs a synchronous instruction-delivery
preflight. It asks the same Codex CLI that will run the child for `codex debug prompt-input`,
using the planned worktree and child environment, and refuses before writing a dispatch
record when the preflight cannot establish the proof. A mismatch is
`instruction_delivery_mismatch`; an unavailable, malformed or incomplete preflight is
`instruction_preflight_unavailable`. Both carry `class=infra_unavailable`, because no
agent work has started and neither condition is a result about the code under test.

The preflight captures the delivered instruction wrapper twice. The normal capture uses
the scoped loader settings that the child receives: the repository marker is `.git`, the
fallback filename list is empty, and `project_doc_max_bytes` is 96 KiB. The second capture
sets only `project_doc_max_bytes=0` to identify the global prefix. The expected project
chain is discovered from the Git root to the launch directory, choosing
`AGENTS.override.md` before `AGENTS.md` at each directory, and is read as complete strict
UTF-8 files. Expected and delivered text use the recorded `lf-v1` newline normalization;
the comparison measures UTF-8 bytes, while inter-file separators are outside the loader's
source-byte budget.

The 96 KiB value is passed as per-invocation Codex configuration to both `debug
prompt-input` and `codex exec`. It is not exported as a global setting, so interactive
Codex sessions do not inherit the containment. A permanent current-checkout tripwire runs
the real Codex binary and checks the delivery pair: the default 32 KiB setting must still
mismatch this checkout, while the 96 KiB setting must match it. The tripwire also keeps the
24 KiB retirement threshold visible. When every supported chain falls below that threshold,
the scoped override retires, but the delivery check stays and changes to assert that the
default setting delivers the complete chain; silent truncation must not return with the
containment.

A successful dispatch record stores the proof schema, CLI version, launch directory,
selected source paths and hashes, expected and delivered byte counts and hashes, the
global-capture measurements, the configured limit, and a combined delivered hash. It
stores no instruction body, global body, brief, child environment, or credential value.
The proof establishes exact delivered text plus independently recorded expected source
identities, but it cannot distinguish two source chains that render byte-identical text:
`LoadedAgentsMd.sources()` exists internally, and no bounded non-interactive command emits
it. The source identities in the proof are therefore recorded by the dispatcher rather
than recovered from Codex's capture.

## The worktree assertion

The dispatched process asserts `git rev-parse --show-toplevel` against its assignment
before the runner starts, and refuses loudly on a mismatch.

This exists because of #105: worktree assignment handed two agents one tree five times in
one evening, and the failure is silent at the moment it happens — two agents in one tree
both see a clean `git status` and both believe the tree is theirs. A check inside the
dispatcher catches the assignment error while it is still an assignment error, rather than
after one agent's routine reset has destroyed the other's work.

A lane that cannot be reached — no credentials file, no key, no worktree — is
`infra_unavailable`, and `infra_unavailable` is not a result.

**The assertion answers "am I where I was sent"; two further rungs answer "is anyone else
here" and "how do I make them leave".** #105's sixth instance (2026-08-10) was neither an
assignment collision nor a mismatch: the seat killed a dispatch, believed it, and
re-dispatched into the same tree while the original session worked on. So a dispatch whose
assigned tree already carries a dispatch record with no `result.json` is refused
`worktree_occupied_by_dispatch`, naming the holder — the record directory is the authority,
because no result means live or dead-without-writing-one and neither justifies a second
agent in the tree — and `just dispatch --stop <id>` is how a holder is removed. The stop
resolves the dispatch to its worktree and then to every process whose `/proc/<pid>/cwd` is
inside it, because *the worktree, not a pid, is the handle that identifies a dispatch's
processes*: the pid the seam knows is the launcher, and the session reparents away from it.
It verifies by re-scanning, and reports what it killed. `tools/dispatch_stop.py` carries the
predicate, its exclusions and its refusals; `docs/agents/recovery.md` carries the procedure.

## The breaker, and why it never invents a wait

`just breaker` carries two trip families, and the whole design falls out of their
difference.

**Availability.** The lane cannot serve right now; quota exhaustion is the common case. It
is foreseeable, and its wait is *computed from a provider's published window boundary,
never guessed*. That is ADR-0061 Decision 7's requirement, and it is why
`quota_exhausted` earned a failure-class row of its own rather than routing to
`infra_unavailable`. A quota trip auto-resets: at the reset time one dispatch probes the
lane and an ordinary outcome restores it.

**Quality.** The lane is serving, and what it serves is wrong: N consecutive gate failures
or refusals on one profile. This is the only thing that catches a provider swapping the
model behind a name with no announcement. It does not auto-reset, because time does not
fix it. It escalates, and a human clears it with `just breaker reset --lane L --force`.

A third case looks like the first and must not behave like it: N consecutive provider
errors with **no** published reset. That holds the lane rather than scheduling a retry.

### The measured derivation

Inventing a cooldown in that third case is the exact defect that disqualified LiteLLM as
this project's breaker: a five-second reactive damper measured against five-hour and
weekly windows (`docs/research/multi-provider-routing-substrates.md` §3.2). Five seconds
is not a wrong number that could be tuned to a right one — it is the wrong *kind* of
number, a damper for a transient against a window whose boundary is published and
knowable. Against a five-hour window a guessed wait burns the window it was guessing
about.

That is where `CLAUDE.md`'s `Never extend, invent or guess a breaker's wait` comes from,
and it is the `timeout` failure-class row's discipline — *never extend the timeout to
pass* — transposed onto quota. The parenthetical citation stays in the prefix on purpose:
it is what stops the rule being re-derived from first principles by someone who thinks
five seconds sounds reasonable.

## `open` and `closed`, and why the verdict line says neither

`tools/breaker.py` uses the electrical convention internally — a **closed** circuit
conducts, so a closed breaker dispatches — because that is the convention the pattern is
named for and every reference on circuit breakers uses.

Every human-facing line avoids both words, printing `dispatch=refused` or
`dispatch=allowed`. The words mean opposite things to an electrician and to a shopkeeper,
and #226's own issue text used both senses in one document — its acceptance criterion says
an *open* lane proceeds, its scope section says `quota_exhausted` *opens* the lane until
reset — so nothing in that issue settles it. A verdict line that needs its convention
explained is a verdict line that gets misread.

Ratified as implemented by the human's ruling on #228 (Decision 6), and recorded here so
it is not re-litigated at the next breaker change.

## What a dispatched session may do, stated per lane

The human ruled on 2026-08-06 (#221 decision 1 and 2, implemented as #259) that a
dispatched session gets the gate and the commit, so that a lane stops needing a
Claude-side finisher to turn its work into a landing. The ruling was taken with an explicit
caution attached, and this section exists to honour it: **the two lanes are widened by
different mechanisms of different granularity, and nothing here claims they are equivalent.**
ADR-0061 decision 5 makes the same point about effort levels; it applies to permission just
as well.

### Reserved on every lane: everything under `.claude/`

A dispatched session cannot write anywhere under `.claude/`, whatever lane it is on and
whatever the project allowlist says. This is a property of the harness rather than of a
lane, so it is stated once here rather than twice below.

Measured on `claude-native` on 2026-08-10 (#294), from a dispatched session in its own
worktree, reproducing the two refusals #273's Codex dispatch reported three days earlier:

| Attempt | Result |
|---|---|
| `Write` to `.claude/hooks/PERMISSION-PROBE.md` | refused — *"which is a sensitive file"* |
| `Write` to `.claude/notes/PERMISSION-PROBE.md` | refused — *"which is a sensitive file"* |
| `Write` to `.claude/skills/retro/PERMISSION-PROBE.md` | refused — *"you haven't granted it yet"* |
| `Write` to `.claude/agents/PERMISSION-PROBE.md` | refused — *"you haven't granted it yet"* |
| `printf … > .claude/skills/retro/PERMISSION-PROBE.md` | refused — *"you haven't granted it yet"*, naming the path |
| `cp docs/…  .claude/skills/retro/PERMISSION-PROBE.md` | refused — the same, naming the destination |
| `printf … >> .claude/skills/retro/…` | refused — the same, naming the path |
| `printf … \| tee .claude/skills/retro/…` | refused — as a compound part: *"the following part requires approval: tee …"* |
| `Write` to `.claude/settings.local.json` | refused — *"you haven't granted it yet"* |
| `Write` to `.claude/commands/…` (directory does not exist) | refused — *"you haven't granted it yet"* |
| **`Edit`** of the existing `.claude/skills/playtest-ingest/SKILL.md` | refused — *"you haven't granted it yet"* |
| `Write` to `docs/PERMISSION-PROBE.md` | written |
| `Write` to an unlisted path at the worktree root | written |

The last six rows were added by a second `claude-native` dispatch the same day; the first
eight reproduced exactly.

Five readings, in the order they matter:

- **The two refusals are two mechanisms, and the split is not the one the allowlist
  predicts.** `.claude/hooks/` and an invented `.claude/notes/` are classified sensitive;
  `.claude/skills/`, `.claude/agents/`, `.claude/commands/` and `.claude/settings.local.json`
  are not, and fall to an ordinary permission ask. `.claude/commands/` refines the earlier
  reading that the sensitive class is the directory's *default*: it did not exist in the
  tree and was still only asked for, so the exemption tracks paths the harness knows —
  the content and configuration ones — while `hooks/`, which it also knows, is classified
  sensitive because a hook executes on the agent's behalf. An invented path is sensitive
  because it is unrecognised, not because it is under `.claude/`.
- **The project allowlist does not reach it, and one half of the grant was never live.**
  Every dispatched session's `dispatch.log` opens with two warnings from Claude Code itself,
  identical across both #294 dispatches:

  ```
  Permission allow rule (.claude/settings.json): Write(.claude/skills/**) is not matched by file permission checks — only Edit(path) rules are. Use Edit(.claude/skills/**) instead (Edit rules cover all file-editing tools).
  Permission allow rule (.claude/settings.json): Write(docs/**) is not matched by file permission checks — only Edit(path) rules are. Use Edit(docs/**) instead (Edit rules cover all file-editing tools).
  ```

  So `Write(.claude/skills/**)` never did anything, and the allowlist's apparent grant was
  half a no-op. That does not rescue the case, because the `Edit(.claude/skills/**)` twin
  **is** live and the Edit tool on an existing skill file was refused anyway. The allowlist
  is loaded and in force — `just land --dry-run` runs on its grant while the ungranted
  `just probe-contract` is refused — so this is an override for these paths, not a settings
  file that failed to load.
- **One hypothesis is still open, and it is cheap to close.** Relative path patterns may
  resolve against the repository root rather than the assigned worktree. Agent worktrees
  live at `.claude/worktrees/<name>/`, so a file at
  `.claude/worktrees/issue-294/.claude/skills/retro/x.md` is under `.claude/worktrees/` and
  is matched by no relative pattern the allowlist could hold. If that is the cause, the wall
  is an accident of where worktrees live rather than a harness reservation. The experiment
  is a single absolute-form rule, and adding it is the human's under #248:

  ```
  "Edit(//home/andre/code/github.com/andrewesweet/arma-cti/.claude/worktrees/*/.claude/skills/**)"
  ```

  It grants exactly the surface the project already believed it had granted, so it is a
  test rather than a widening. If a dispatched session can then edit a skill, the constraint
  was path resolution; if it still cannot, the harness reserves `.claude/` and that is the
  end of the question.
- **An ask is a refusal here.** A dispatched session is `claude --print` with nobody to
  answer a prompt, which is why the orchestrator's own interactive session lands these
  edits by hand and a dispatch cannot. The barrier is "a human must answer", not "nobody
  may write".
- **The shell is not a way round it.** The harness reads a Bash command's write targets:
  the redirect and the `cp` destination were refused by path, with the same wording as the
  tool call. #265's "re-express it as a shell append" does not reproduce here.

**The routing consequence.** No route a dispatched session can reach exists today. A `just`
recipe that promotes a reviewed file into `.claude/` would need its own `Bash(just …)` grant
in `.claude/settings.json`, which is a permissions decision and therefore the human's
(#248); it is proposed on #294 rather than landed. Meanwhile the wall costs ergonomics
rather than authority: every surface under `.claude/` is spoken for by something other than
this wall — the project skills by CLAUDE.md's own sign-off list, the seat definitions by
`just check`'s generated-file check, and the settings file by #248's ruling that a permissions
change is the human's — so no dispatched session was ever entitled to land one of these
unilaterally. Routing class 6 was a fourth support here and is not one any more: ADR-0073
(#406) retired its keep-on-Claude bar, so the row refuses nothing at dispatch and nothing at
landing. It still names `.claude/hooks/` and `.claude/settings.json`, and what that naming now
buys is a constraint on the *review* that clears such a landing — the never-alone rung's
cross-lane check, a strong preference carried by a mandatory `gate_review=` record since
ADR-0073 Amendment A2 (#426) — never a bar on which session may land. The three supports above
carry the conclusion on their own; this is a correction to its fourth leg rather than a
retraction of it. The
route that works is the one #299 already mandates for a gated edit: the dispatched seat
authors the exact replacement text as a proposal, and the orchestrator transcribes it.
`tools/brief.py` says so in the brief when an issue names such a path, so the next dispatch
learns it at composition time instead of spending itself finding out.

**The routing policy half-caught up, and the gap this section named is now two gaps.** This
paragraph used to record that `config/dispatch-routing-policy.json` carried `.claude/skills/`,
`.claude/agents/`, `.claude/settings.json` and `.claude/hooks/` inside class 1,
`gated_semantic_surfaces`, whose remedy routed on provider where the constraint is
dispatched-versus-interactive — so it sent the work to a lane that would refuse it. #326 killed
class 1 outright: ADR-0071's re-founding table found its basis was provenance and its human
sign-off gate was never this file. Two of the four prefixes survived the deletion by moving to
class 6, because `.claude/settings.json` and `.claude/hooks/` are the permission allowlist and
the denial layer, i.e. gates, and class 1's list was the only routing rule that named them. The
other two, `.claude/skills/` and `.claude/agents/`, are named by no routing class at all now.
That is not an oversight to fix here, but the two are not covered by the same thing and this
paragraph used to say they were (review round 1 claim 7). `.claude/skills/` is human sign-off
gated by CLAUDE.md, whose list ends "changes to this file or the project skills".
`.claude/agents/` appears nowhere in that list, and nowhere in
the shared `tools/gated_paths.py` catalogue's `deny_at_write` entries either, which cover
generated paths and `tests/specs/` only; what covers it is `just check`'s generated-file check, since every seat
file is written from `tools/dispatch.py`'s registry by `tools/generate_seats.py` and a
hand-edit reds the gate. The ground both share is the second one: the wall this section
documents refuses a dispatched write to either regardless of lane. What
is lost is the *advisory* — an issue declaring one of those paths no longer learns at dispatch
that it cannot land it, and learns instead from `tools/brief.py`'s composition-time note.

**The policy file carried two class tables for one transition window, and that window is
closed.** A parser is imported by a *running process*: `just land` in a worktree branched
before #326 landed reads the trusted policy out of fetched `origin/main` with the
`tools/routing_policy.py` that process started with, and the rebase brings the new module
into the tree but not into the process. That older parser demanded the ordered table 1..7
and cannot read a table whose retired ids leave gaps, so a file carrying only the re-founded
table refused every in-flight landing and dispatch until each worktree rebased — on a remedy
telling the reader to repair a policy that is not broken, which sends them at a class-6 gated
file (#326, review round 3 claim 1). So the re-founded document lived under `routing_classes`,
`routing_issue_exceptions` and `routing_route_exceptions` while the unprefixed `classes`,
`issue_exceptions` and `route_exceptions` kept the pre-#326 document frozen as `bbb6ade`
carried it, with `routing_policy.View` picking one set on the presence of the re-founded
table so the two were never mixed.

The arbiter set the deletion at 2026-08-21 as a decision rather than a measurement — the
condition that stood before it, "once no worktree predating that landing is still in flight",
was withdrawn as not computable, since `just worktree list` sweeps registrations and this box
carries over 150 of them, most long abandoned, so it would never have read true. The human
shortened that date to 2026-08-16 on 2026-08-14, and #365 deleted the frozen half on it. The
`View`/`LEGACY` machinery went with the data: `origin/main` has carried the re-founded keys
since #326 landed, so neither of this parser's two sources — the working tree's copy and
`origin/main`'s — can hand it a pre-#326 document any more, and one that spelled the
unprefixed keys is now refused rather than read.

**A subprocess is a way round the parser, and that is why a grant must be narrow.** The
harness classifies the Bash *command*, not the writes a child process goes on to perform:
`just land --dry-run` runs on its `Bash(just land --dry-run)` grant and its `uv run` created
a `.venv` in passing, which no permission check saw. So the `just`-recipe route proposed
above would work — a recipe that promotes a reviewed file into `.claude/` needs only its own
`Bash(just …)` grant — and equally, any *broad* recipe grant is an unbounded write channel.
That is the reasoning `tools/discard.py` already records: allowlist a command constrained
until it can do nothing except the case it was authorised for.

**What is not established.** Whether a *user-level* or enterprise settings grant would be
honoured where the project one is not; whether the absolute-form worktree rule above is
honoured, which is the one open hypothesis and needs a settings change to test; and whether
`bypassPermissions` reaches `.claude/` — the Remote Control server runs with it, which is
consistent with the orchestrator landing these files by hand, but nothing here was probed
and nothing here recommends that mode for a dispatch.

**Its sibling constraint is what a dispatched session may *run*.** That is measured
separately in `docs/agents/dispatched-session-commands.md`, and it is the larger of the two
in day-to-day cost. Four of the seven commands #294 recorded as refused on 2026-08-10 were
refused only because RTK rewrote them before the permission decision was taken; RTK was
removed from this host on 2026-08-16 and those four re-measured as clearing bare. The other
three were refused on their own merits and are unaffected.

### `zai` — a list of named commands

The lane rides the `claude` binary, so it inherits `.claude/settings.json`'s allowlist.
`--permission-mode` is unchanged at `acceptEdits`. The grant is eight entries and it is
exhaustive: `just check`, `just unit`, `just fast`, `git add`, `git commit`, and read-only
`git status`, `git diff` and `git log`. `just land` and `just land --dry-run` were already
there and remain the only push path — `tools/land.py`'s refspec is a constant no argument
reaches. Bare `git push` and `git commit --no-verify` are deliberately absent.

Measured live by dispatches `d-20260806-163123-e8bed7` and `d-20260806-165934-de5015`, which
between them ran every one of those commands, committed their own work at `73a0d5c`, gated
it and landed it at `a609127` with no Claude-side involvement. Two readings from the same
runs are worth keeping:

- `git commit --no-verify` was **refused**, by the hook rather than by the allowlist. That
  is the whole safety argument for widening: `PreToolUse` fires before any permission-mode
  check, in every permission mode (vendor, `code.claude.com/docs/en/hooks-guide.md`), so
  enforcement sits upstream of permission and a wider allowlist cannot reach it.
- `git push --dry-run origin HEAD:main` was **permitted**, although this repository grants
  no `git push` in any form. The grant came from a user-level `Bash(git push *)` entry on
  this box. So the project allowlist describes what this repository asks for; it does not by
  itself bound what a session on this machine can do.

### `codex` — a filesystem and network policy

The lane does not read `.claude/settings.json`'s allowlist at all. `tools/dispatch.py` maps
the permission mode to a sandbox policy, and `acceptEdits` is `--sandbox workspace-write`
plus, on that mode only, writable roots — the tool caches named in
`dispatch._codex_writable_roots` — and network access. Every
command the session runs inherits all of it; there is no per-command list to consult.

What that buys, measured rather than inferred, over five dispatches and four probes:

- Plain `workspace-write` grants the session's own worktree and nothing above it. `git
  status`, `git log` and `git diff` worked; `git add` did not.
- The gate runs. `cog check` returns `No errored commits` and `just fast` executes, which
  is the capability that matters, because a profile that cannot run its own gate is not an
  implementer.
- The gate additionally needs two tool caches outside every worktree, each measured red:
  `~/.cache/uv`, where `uv` takes a lock before any test runs; and `~/.ansible/tmp`,
  where `ansible-playbook --syntax-check` puts its per-run directory — the proving
  dispatch `d-20260818-185929-ae5491` died there, because `check-machine-b` joined the
  gate on 2026-08-13, a week *after* the root set was measured. `~/.cache/ansible-lint`
  was granted once on a derivation from the linter's source and dropped on review: the
  installed copy reports `INSTALLER=uv`, returns before reaching the version check the
  derivation rested on, and the directory does not exist. **The two locations are
  constants, computed once from `Path.home()` and resolved to absolute paths** (#405
  review round four): no environment variable reaches them, so `UV_CACHE_DIR`,
  `ANSIBLE_LOCAL_TEMP`, `XDG_CACHE_HOME` and `ANSIBLE_HOME` neither widen the grant nor
  refuse a dispatch — they are simply not read. Three rounds of validating a path the
  environment supplied each found the same defect somewhere new (a value checked here and
  resolved differently there), so nothing external is admitted and there is nothing left
  to validate; the one refusal that remains, `writable_root_refused`, is a `HOME` this box
  will not canonicalise. A box that genuinely keeps a cache elsewhere edits the constants,
  which is a diff under review. `~/.cargo` looked as likely and was measured unnecessary,
  so it is not granted.
- `network_access` defaults off while the gate reads `gh` and `uv` may fetch, so it is
  enabled.

Read-only seats keep the sandbox they always had, and
`--dangerously-bypass-approvals-and-sandbox` was put to the human, declined, and is unused.

**The session cannot commit, and that is Codex's policy rather than a gap in this
configuration.** Codex enforces `<root>/.git` as a read-only path inside every writable
root: it is protecting git history from the agent. Where the named root *is* a git
directory there is no `.git` to protect, so the sandbox creates one, and libgit2 — which
`cog` reads the repository through — opens that empty directory instead of the real layout.
Naming a git directory therefore buys the commit and costs the gate, in that order and
always. The sandbox states the policy in its own words when the path it wants to enforce is
already occupied (`d-20260818-111104-5138a7`, a symlink pre-created at that path):

```
error building bubblewrap command: Fatal error: cannot enforce sandbox read-only path
…/issue-405c.gitdir/.git because it crosses writable symlink …/issue-405c.gitdir/.git
```

Six arrangements are measured and refuted, and the list is closed rather than open — a
seventh is not worth a dispatch:

| arrangement | `git commit` | `cog check`, the gate's first step |
|---|---|---|
| linked worktree; main checkout, `<main>/.git`, `~/.cache/uv` writable | refused, `index.lock` read-only | `No errored commits` |
| the same plus `<main>/.git/worktrees/<name>` | exit 0, no escalation | `could not find repository at '<main>/.git/worktrees/<name>/'` |
| the same with `<name>` replaced by its parent `<main>/.git/worktrees` | refused, `index.lock` read-only (`d-20260808-075346-f27564`) | not reached |
| standalone clone, its `.git` writable (`d-20260818-080724-50f2be`) | exit 0 | `could not find repository`, `.git/.git` present |
| `--separate-git-dir` to `<cwd>/_gitdir`, no git directory writable (`issue-405b`) | refused, `_gitdir/index.lock` read-only | `No errored commits` |
| `<gitdir>/.git` pre-created as a symlink to `.` (`d-20260818-111104-5138a7`) | not reached | the sandbox refused to start |

The fifth row is the one that settles the cause. The git directory was not called `.git`
and its `index.lock` was read-only all the same, so the carve-out is keyed on the
repository Codex *discovers* rather than on a name. The second row's mechanism is measured
too: a read-only strace over `cog check` in the sandbox (`d-20260807-222221-1a2c7e`) found
an empty `<main>/.git/worktrees/<name>/.git` directory (mode 0555) — the read-only mount
point for that writable root — which libgit2 stats during discovery, mistakes for a
repository, and reports missing when its `commondir` and `HEAD` are absent. The refusals
read `Read-only file system` (EROFS), not the `EACCES` a Landlock denial produces, so the
sandbox is mount-based (Codex bundles `bwrap`) rather than Landlock-based; #265's "Landlock
composition" first-suspect is refuted by its own recorded evidence.

**So the session gates and the harness commits** (#405). The session edits in its worktree,
runs `just check` and `just fast` there as any implementer does, and writes its Conventional
Commits message to `.dispatch-commit-message` in the worktree root —
`dispatch.CODEX_COMMIT_MESSAGE`, named once in code and stated to the session in the brief
the dispatcher appends for this lane. After the session exits, `dispatch.harness_finish`
runs on the unsandboxed side: it moves that message beside the dispatch record, commits
everything in the tree with it, and pushes the branch to the issue's review ref through
`review_exchange.exchange`. A tree the session edited with no message file in it refuses
`commit_message_absent` and is left untouched, because a commit nobody wrote a message for
is worse than none. The commit is subject to the repository's own `commit-msg` hook, so a
Codex session's message meets `cog verify` exactly as any other session's does, and
authorship stays what it was: the box's git identity on the commit, the dispatch record for
the profile that did the work.

This is not a workaround for the sandbox — it accepts the sandbox's policy and puts the
commit where this project already performs unsandboxed git acts. It also ends the
Claude-side finisher that #265 forced: the ceiling is lifted, `SEAT_PROFILE_BLOCKS` ships
empty, and `codex-luna-max` heads the implementer seat's preference list for real. What is
*not* claimed: **landing is still the orchestrator's**, on this lane as on the day the
sandbox was first widened — `just land` writes the git directory and the main checkout, and
neither is reachable from inside the sandbox. And the end-to-end evidence #405 asks for —
one real Codex implementer dispatch that edits, gates green inside the session and reaches a
pushed commit through the harness — **has not been recorded yet**; the design is landed and
unit-proven, and until that dispatch's id is on #405 this paragraph is describing something
built rather than something demonstrated.

### Where they are not comparable

Network access is the clearest case. On `codex` it is a property of the sandbox, so every
command the session runs can reach the network. On `zai` nothing grants network capability
as such; only the commands on the list run at all, and of those only `just land` and `gh`
talk to anything remote. The same intent, delivered by mechanisms whose blast radius does
not match — which is why this section states them separately rather than as one table.

One more asymmetry, and it is a property of this box rather than of either ruling: Codex's
`approvals_reviewer = "auto_review"` can approve a command's escalation *out* of the
sandbox, and dispatch `d-20260806-165944-1b31e5` reached a green landing that way while the
sandbox was still refusing its `git add`. A sandbox that a reviewer model can be asked to
step outside is not a containment boundary in the way an allowlist is.

## The seat surfaces are generated, and only one harness has a surface

ADR-0071 ruling 7: both harnesses' surfaces are generated from `tools/dispatch.py`'s
registry **wherever the target surface exists**, and the pattern is `tools/hook_parity.py`'s
— translate, never reimplement. `tools/generate_seats.py` is the seat half of that, run by
`just generate` and checked by `just check` (#324).

What it removes is a class of drift rather than a single mistake. A seat's `(model, effort)`
pair was typed out wherever a surface wanted it: the agent definition, the skill frontmatter
that ADR-0068 added, and the always-loaded prefix's own description of the mapping. The
interlocutor's pair reached five places that way, and `cti-implementer`'s came to disagree
with ruling 2's table with nothing to notice. The registry already held each pair once,
behind a seat's ordered preference list (#320, #321), so the surfaces are written from it.

**A Claude seat file declares the first `claude-native` profile in the seat's preference
list**, and that lane filter is the whole of the derivation. A `.claude/agents/` definition
cannot pin a lane — it names a Claude-vocabulary model, and which provider that reaches is
a property of the session that spawns the subagent — so a head on another lane has no
expression here. `zai-glm53-max` is the trap rather than `codex-luna-max`: its Claude vocabulary is
`opus`/`max`, which a native session would read as a native pair the registry never chose.

**The check matters more here than for the schema export, because both declaration surfaces
fail open** (ADR-0068). A misspelled key, an indented line, a value nobody regenerated —
none of them refuse. The seat answers, the work lands, and the only trace is a tier nobody
ratified. `just check-seats` asserts that a pair is declared and valid; the generated-file
check asserts that it is the registry's, which is the half that was missing. Writing also
*converges* the directory rather than adding to it: a file for a seat the registry has
retired is removed and named, so every failure `--check` can report is one `just generate`
would fix.

**Codex has no seat-definition surface, and that is an accepted gap with a named failure
mode.** There is nothing to generate into, so generation is not a claim this project can
make for both harnesses. The consequence: a subagent a Codex session spawns on its own
judgement runs at whatever model that session was started with, and nothing refuses — on
the lane ruling 2 intends as the primary implementation lane, which means the seat concept
the map is built from is unenforceable there. Instructions in `AGENTS.md` were rejected as
the remedy, because they fail open in exactly the way they would exist to prevent. The gap
is carried as data in `generate_seats.UNGENERATED_HARNESSES` and printed by `just generate`,
so it is met by whoever touches the surfaces rather than filed somewhere they will not look.
**Do not invent a surface**; when one exists, it is a translation and this module is where
it goes.

**Running the generator is the orchestrator's, not a dispatch's**, and for the reason the
permission section above already records: a dispatched session cannot write under `.claude/`
at all, so it can author this module and its check but cannot materialise the output. That
is not the #299 proposal-and-transcribe shape — there is no wording to transcribe, only one
deterministic command to run. A `Bash(just generate)` grant in `.claude/settings.json` would
close it, and that is a permissions decision and therefore the human's (#248).
