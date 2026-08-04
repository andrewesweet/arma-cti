# A granted run has a floor, and a starved flight is not a result

Delegated-decision: no — the human ruled the direction in session
Date: 2026-08-04
Reviewed-by-human: 2026-08-04 — the guided decision-capture session's routing
comment on #182 ruled the direction verbatim: "Design the floor under a
*granted* run: tripping it should type the probe `infra_unavailable` rather
than letting a starved world forge a plausible `timeout`/`node_crashed`", and
pre-approved the design "without reserving the floor semantics for a second
review". The four resolutions that comment left open are flagged below.
Claimed: comment on #182, 2026-08-04, after `git fetch origin` (`docs/adr/` on
origin/main topping at 0053) and a scan of every open issue's comments finding
no claim above 0053

## Context

The memory pre-flight (#125) floors *admission*: a reading before any lock is
taken, and a between-probes re-check that stops the pool taking new work. Both
were passed, twice, by starvation that arrived while worlds were already in
flight — another agent's corpus loading the box mid-run (the 2026-08-03
serial-grant episode: `base-assault` `timeout` at 458 s on a box at 19 MiB,
158 s pass on re-run), and the OS itself sickening (#164's cluster:
`node_crashed` at ~20 MiB, root-caused to Windows OS-drive exhaustion). The
common shape: **a starved world does not fail honestly**. It types `timeout`
or `node_crashed` — false reds about the code under test, wearing classes
whose table rows send the reader to fix the probe or escalate a crash.

The bulkhead rule to date said stops never interrupt work in flight, "because
killing a running world would manufacture the non-result being avoided". A
starved flight is the case where that reasoning inverts: its result is
*already* a non-result wearing a plausible class, and letting it run to term
only launders the forgery.

## Decision

**The pool watches the machine while flights are up, and a reading under the
running floor with a probe in flight stops the pool and its flights.** The
watch polls the same substitutable reader as the admission reading and the
between-probes re-check (`CTI_SLOT_MEM_READER`, #133's pattern), on the lock
queue's 5 s cadence. A trip writes the pool's `mem-stop` (the merge's
pool-level `infra_unavailable`, as the between-probes stop already does),
marks each in-flight claim `starved` with the reading and the floor, and TERMs
each flight through its own watchdog `timeout` — the leader of the probe's
process group — so `run.sh`'s own trap tears its world down and releases what
it holds.

**A marked flight is `infra_unavailable`, above every other reading of the
run.** The verdict typer's new top rung outranks the class the world declared,
the watchdog story, and even a recorded PASS: whatever a flight measured while
the box was under the floor was measured under conditions nobody can
interpret, and fail-closed picks the discarded pass over the forged one.
**Verdicts that completed before the trip stand** — their flights ran on the
machine the between-probes reading admitted them to.

The contract sentence gains its floor: fewer slots free is a smaller pool, not
a failure — *and a granted run has a floor beneath it*; below the running
floor there is no smaller pool, only a stop.

## What the ruling fixed, and what this ADR resolves

The session ruling fixed that the floor exists under granted runs and that
tripping it types the probe `infra_unavailable`. Four resolutions were left to
this ADR, flagged for review:

1. **Tripping stops the flight rather than waiting it out and retyping.** The
   class is the same either way; stopping answers minutes earlier, stops a
   starved world thrashing a box somebody else is also on, and is the only
   reading under which the ruling's "rather than letting a starved world
   forge" is literal.
2. **The floor is the existing 512 MiB running floor, not a new number.** The
   question is the between-probes re-check's own — is any margin left at
   all? — and 512 separates every healthy trough on record (1,014 MiB at its
   lowest) from both starvation episodes (19–40 MiB) by an order of magnitude
   each way. One floor, one meaning; a second number would be a second thing
   to re-measure.
3. **The marker outranks even a recorded pass.** A pass squeaked out under the
   floor is the same uninterpretable measurement as the forged reds; a
   discarded pass costs a re-run, a forged pass costs a false green.
4. **Two fail-closed asymmetries.** A reader failure is logged and not acted
   on — killing granted work on a reading never taken would fabricate the
   measurement #147 removed, and the between-probes re-check already stops new
   work on an unreadable machine. And a trip needs a flight to stop: a
   collapse with nothing in flight is the re-check's to answer at the next
   launch, never a post-hoc stop over a corpus that finished measuring.

## What would overturn this

A healthy run tripping the watch — a genuine reading under 512 MiB that a
world then passed honestly under re-run scrutiny — would mean the floor is set
inside healthy variance and must drop, or the one-floor resolution (2) was
wrong. A starvation episode that forges a class *without* crossing 512 MiB
would mean the floor is too low to catch what it exists for. Either is a
re-measure first, per the elimination-context rule; the mechanism stands
unless the separation itself collapses.

## Not this ADR

The RAM sampler's per-pool attribution and the verdict-aware pool prune ride
the same #182 track but change no tier contract; the healthy-box RSS
re-measure (2,439–2,463 MiB a slot across the 2026-08-04 full-corpus runs)
confirmed the admission figures rather than moving them, so no threshold
moved. Cross-agent contention beyond the floor — a machine-wide memory
reservation — stays deliberately unbuilt (#125's reasoning, re-affirmed).
