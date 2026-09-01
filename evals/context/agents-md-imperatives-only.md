# arma-cti working rules — imperatives only

Derived from `AGENTS.md` at commit `f83f8c03` (2026-09-01), sha256
`484d24cc09f3ca8350e51b1581487f47717134458d278d512bbcaf22ada0e067`. The rule of
derivation: directive sentences only, taken from the **Contract** and **Working style**
sections; the `_(validated ×N …)_` evidence annotations, every table, and narrative
rationale are dropped. Refresh by hand when the underlying rules move materially. This
file is an experimental stimulus for the `AGENTS.md` ablation task, not a copy of the
file.

## Contract

**Always**: run `just check` + `just unit` after every edit; read the failure bundle
before modifying code when one exists.

**Never**: edit an acceptance spec to make it pass; add a sleep, retry, or timeout
extension to make a test pass; introduce a bare `random` or bare `sleep` in SQF (use a
seeded PRNG and the `cti_fnc_everyInterval` scheduler adapter only, deliberately not
CBA); call `setGroupOwner` outside `spike/desync-load.sqf`; treat `infra_unavailable` as a
result.

**Never** `export ANTHROPIC_BASE_URL` (or any lane variable) into a shell, a profile, or
`~/.claude/settings.json`.

**Never** extend, invent or guess a breaker's wait. A lane reopens at a boundary its
provider published, on evidence that it is serving again, or by a human's hand — never
on a timer this project chose.

The Arma tier may allocate ports within **[2400, 3000)** and must never take 2302–2306.

## Working style

- A turn does not block for five minutes, and which seat it is decides what happens next;
  an agent that has ended cannot stall.
- In a subagent, foreseeably long work is dispatched detached and the agent then ends:
  commit, arm `just watch`, write a handoff, and stop. In the orchestrator, waiting is
  what the seat is for.
- Foreseeable work follows the measured denial list in
  `.claude/hooks/deny-subagent-waits.py`; carry on if a gate overruns an expectation
  outside that list.
- A wait that genuinely cannot be decomposed has one sanctioned fallback: dispatch it as
  a session with `just dispatch --lane claude-native`, arm `just watch` at dispatch, and
  read the result from the ledger.
- A dispatched session is detached; do not start one and forget the monitoring burden.
- Keepalive turns are unsanctioned. The exception list is empty and grows only at a retro.
- Do not shorten a gate; let it finish with its assertions.
- A dispatched session is single-shot. Run awaited work in the foreground. Decide routine
  ambiguities, act, and record the reasoning. If a choice is genuinely the human's,
  finish the unambiguous part and state what remains and why.
- Reading a finished verdict is not seat-gated. Quote `just verdict`'s rendered body
  verbatim; never retype the SHA or evidence path. Carry the paste rule into any briefing
  that dispatches a verdict reader. `cti-recon` may read and report a verdict but never
  lands or dispatches.
- Deliver what was asked, at the scope intended. Make routine judgement calls yourself;
  check in only when different readings would lead to materially different work. If the
  request seems mistaken, say so in a sentence and continue as asked.
- No single model instance may both propose a change and produce the review verdict that
  clears it; every landing is reviewed in a different session, except entries in
  `config/review-exemptions.json`, and a diff touching that file cannot be exempted.
- Retain the post-landing review. An implementer may run a bounded self-review in its
  Work Run before handover, with no dispatch or subagent; it never substitutes for the
  independent review. Beyond those and never-alone, do not add verification passes,
  re-checks, or verifier subagents.
- Two providers over one diff are one review pass with two lenses, not a second pass.
- Delegate to subagents only for sizeable, genuinely independent tracks; never delegate
  to double-check your own work.
- Ground progress claims in tool results from this session; quote failing output, name
  skipped steps, and mark unverified work as unverified.
- An agent watching a run watches it from inside its turn. A turn that ends with a parked
  monitor or gate is a wait; use `just watch` for sanctioned detached monitoring and read
  its finding in a later turn.
- Before work in a worktree, verify it is exclusively yours — clean `git status`, no
  foreign uncommitted files — and commit early and often. Foreign files mean stop and
  report, never reset.
- Measure before building: a rule proposed on cost or threshold grounds is checked by
  running the measurement, not settled by intuition.
- An elimination or inherited measurement holds only in the context it was tested;
  re-derive before inheriting.
- In any review pass, report everything found; filter by severity separately.
- Match written documents to what the task needs — no filler, boilerplate, or redundant
  summaries. Lead every summary with the outcome.
- Land a convention together with its first applied instance.
