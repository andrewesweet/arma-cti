# A probe declares the world it needs, and bareworld is a probe like any other

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on process-doc changes — three conventions the `just regress` runner needed that ADR-0016's design did not settle (issue #23, implementation)
Reviewed-by-human: pending

Decided while building the runner ADR-0016 authorised. Everything here is a detail
the design left open and the code could not; the design's own decisions are
unchanged, and where this document departs from it, it says so.

## The probe declares the world it needs: an `env:` header line

ADR-0016 asks for a command surface with "no bespoke environment variables". Two
probes in the corpus cannot run without them: `ai-commander` is meaningless
without `CTI_AI_SIDE=WEST` (the daemon comes up under nobody's command and the
probe correctly finds nothing), and `two-commanders` needs three, one of which
brings up the headless client its topology names. That requirement belongs to the
probe, not to whoever types the command — and being written in the probe's prose
rather than its header is exactly how it became something a later session had to
reconstruct from a comment.

So the header block gains `// env: KEY=VALUE ...`, alongside the `probe:`,
`issues:` and `window:` lines ADR-0016 specifies and the `expect:` line ADR-0019
added. The runner reads it and brings the world up with it. `just regress` itself
still takes no environment variables, which is the property the acceptance
criterion actually asks for.

**What would overturn this.** A probe needing bring-up state that is not
expressible as environment — a staged file, a corrupted manifest variant (the
follow-on negative probe the design already names as needing "the runner's
staging hook") — makes `env:` the first half of a convention rather than the
whole of one. When that probe is written, the honest move is a general
`setup:` hook and `env:` folded into it, not a second special case beside it.

## Bareworld is a probe file, not a bare mission run

The design describes bareworld as "the Phase-1 mission brought up with no probe
appended". It is `spike/probes/bareworld.sqf` instead.

A mission with nothing appended has no completion line to wait on. The only
candidate is the mission's own `CTI|done`, which fires *before* the loops it has
just started — the effect pump, the presence report — have polled once, so the
assertions those loops carry could not have fired yet. Waiting on `done` therefore
means a fixed sleep after it, sized by guess, and CLAUDE.md's Contract will not
take a sleep. A probe can instead wait on the loops' own observable state: three
polls on the pump's running counter, and an owner for every Objective, which
proves the whole presence leg ran — report out, judgement back, marker repainted.
That is synchronisation on evidence, which is what the `timeout` row asks for.

Being a real file bought two more things. The probe carries a `window:` header
like every other corpus member, so the runner has one code path rather than a
special case. And it moved three of #23's listed properties into Phase 1 that
otherwise sat only in `spike.Stratis`, the Phase-0 measurement mission that
nothing runs per issue: the addon resolving by name on a dedicated server, the
seeded PRNG against the real engine, and the daemon echoing a request id back
through `callExtension`. Those were listed on the ticket as things this tier must
cover, and until this probe existed no Phase-1 run covered them.

**What would overturn this.** If a later mission grows an explicit "the world is
settled" line — one logged after the loops have cycled rather than after they are
started — bareworld's synchronisation half becomes redundant and the probe should
shrink to its assertions or disappear into the mission's own.

## The exit code names the class, and infra_unavailable stops the run

The design says "worst-class exit code" without saying which class is worst or
what the code is. Both are now fixed, because an agent reading an exit code needs
it to mean the same thing next week:

| class | exit | severity order |
|---|---|---|
| pass, flake_quarantine | 0 | does not gate |
| assertion_failed | 1 | least |
| timeout | 2 | |
| oracle_disagreement | 3 | |
| node_crashed | 4 | |
| infra_unavailable | 5 | worst |
| engine_drift | 6 | (by severity, above oracle_disagreement) |
| schema_stale | 7 | (by severity, above timeout) |
| an unrecognised class | 9 | worst of all |

The numbers are stable identifiers, not the ranking; the ranking is the severity
column, and the summary sorts by it so the first line printed is the one to read.
`infra_unavailable` outranks everything because the failure-class table says it is
not a result: nothing measured alongside it was measured under conditions anyone
can interpret. For the same reason it is the one class that **stops the run**
rather than letting the corpus finish — the general rule is report everything and
filter later, but carrying on past a stop produces more non-results and takes the
machine with it. An unrecognised class ranks worst because CLAUDE.md's rule is
that untyped red is a harness bug, to be fixed before anything else.

**What would overturn this.** If `engine_drift` or `schema_stale` ever actually
fires — nothing in the world emits either today, so their placement in the order
is reasoned rather than observed — its real severity relative to
`oracle_disagreement` is worth re-deciding against that run rather than against
this table.
