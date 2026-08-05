# Dispatching work to another provider

The design behind `just dispatch` and `just breaker`. `CLAUDE.md` carries the rules an
agent must not get wrong in the moment — the eligible seats, the credential handling, the
prohibition on exporting a lane variable, the prohibition on inventing a breaker's wait.
Everything here is the reasoning under those rules, moved out of the always-loaded prefix
by the human's ruling on #228 (2026-08-05, Decision 2) so that the prefix carries the rule
and this document carries why it is the rule.

Binding decision: ADR-0061. Implementation: `tools/dispatch.py`, `tools/breaker.py`. The
ledger that records what a dispatch cost is a separate document, `docs/telemetry-ledger.md`.

## Lanes and profiles

A **lane** is a provider and the environment that reaches it. A **profile** is one opaque
`(lane, model, effort)` token in `tools/dispatch.py`'s registry. Week one registers
`claude-native` and `zai`.

The recipe has no `--model` and no `--effort`, and that absence is the design (ADR-0061
Decision 5). Effort vocabularies do not commensurate across providers: GLM Max and Opus
high are not the same quantity, and the mapping between them is not monotonic, so a
dispatcher offered both dimensions separately would be inviting an agent to compose a
pair no one has ever measured. A profile is measured or it is not registered.

The z.ai lane made the argument concrete rather than abstract (#225). Claude Code's five
effort levels differ only in the `thinking.budget_tokens` they send, and that endpoint
ignores the field — a hard prompt at budget 1,024 and at budget 32,000 both thought past
nine thousand tokens and both stopped on `max_tokens`. So on that lane all five efforts
are one configuration, and there is one profile per model rather than five.

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

Credentials come from `~/.arma-cti/credentials.env` at mode 0600, by environment only.
Never on argv, so never in `ps`; never echoed; and the dispatch record names the key it
used and not its value. `just prereqs credentials` is the only writer of that file, it
reads the value off the terminal with echo off, and it refuses if the path ever resolves
inside a git work tree.

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
