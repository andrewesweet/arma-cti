# Durable snapshots retain a verified last-known-good, checkpoint thirty seconds after the first dirty change, and resume behind a fail-closed barrier

Delegated-decision: no — the human ruled the three decisions this records in the
2026-08-08 guided human-input review on #4; this document is their durable home,
not a decision taken on the human's behalf
Date: 2026-08-09
Reviewed-by-human: pending
Claimed: against `origin/main` at `3d4e563`, whose `docs/adr/` tops at 0068, plus
a lexical search of every issue and its comments for ADR-0069, ADR-0070 and
ADR-0071 finding none. The worktree was created by `just worktree add`, which
fetches; `git fetch origin` was not re-run in this session, so the rebase inside
`just land` is the backstop the standing rule provides for exactly that gap

#4 is Phase 2 — snapshot persistence and resume fidelity — and it carried three
open questions through Phase 1: what happens when a save cannot be loaded, how
often the Campaign is durably checkpointed, and how a resumed Campaign is
projected back into a fresh world. The human ruled all three on 2026-08-08, in a
guided review whose three rulings are cited verbatim in substance below; a
fourth comment the same evening exploded the phase into the dependency-ordered
tickets #289–#293 (`#issuecomment-5228402199`). This ADR is the decision record
those tickets were blocked on, and it closes with no production code: #289 has
already landed the versioned document this record governs (`e299d06`,
`src/cti_daemon/snapshot.py`), and the rulings it left open — crash-consistency,
cadence, load-failure behaviour, the resume barrier — are what is settled here.

Snapshot schema semantics are a human sign-off gate, so the choices a reader
might expect this document to take — exact filenames and module placement, the
byte threshold at which an Effect is "oversized", how many generations are
retained — are stated as the implementation tickets' choices, not decided in
prose. Every decision below traces to a human ruling or to a #288 acceptance
criterion the human wrote; nothing here is taken on the human's behalf.

## Ruling 1 — a save retains a verified last-known-good; load failure never starts a fresh Campaign

*(Human ruling on #4, 2026-08-08T21:36:54Z, `#issuecomment-5228289491`.)*

Saving retains a verified last-known-good snapshot. On boot, if the newest
snapshot cannot pass integrity, validation or a supported migration, it is
preserved for diagnosis and the previous verified snapshot is loaded with a
prominent rollback warning. If no valid previous snapshot exists, Campaign start
is refused. A schema version with no supported migration follows the same rule.
A fresh Campaign begins only through an explicit human action, never as
load-failure recovery — because a silent fresh start is the corrupted-world
outcome durability exists to prevent (ADR-0003).

This is the decision ADR-0008 and ADR-0003 were silent on: both bound the loss
window to one autosave interval but neither said what a boot does with a
snapshot that fails to load. The resilience note on #4 (2026-08-01,
`#issuecomment-5153715434`) named the gap — "load-failure behaviour is
undecided" — and this ruling closes it on the side that cannot lose a Campaign
by forgetting it.

### The five cases the implementation must keep distinguishable

A load path that folds these together reads as one behaviour and is four, plus
the one path that is not a failure at all:

- **Corruption** — the newest snapshot fails integrity (a torn write, a bad
  checksum). Preserve it; load the previous verified snapshot with a rollback
  warning; refuse if none is valid.
- **Unsupported schema** — the snapshot's version has no registered migration
  path to the current one. Same rule: preserve, fall back, or refuse; never read
  as-is, never start fresh. (#289's `restore` already returns this as a typed
  refusal rather than a fresh Campaign.)
- **Failed migration** — a version *with* a registered path whose migration
  cannot complete (a field that takes no safe default). A typed refusal under
  the same rule, distinguished from unsupported because the path existed and the
  execution failed, not the version.
- **Rollback** — the recovery action itself: loading the previous verified
  snapshot. It is *visible* — a prominent warning — never a silent substitute,
  so an operator knows a generation was skipped.
- **Explicit fresh-Campaign** — a new Campaign begun by an explicit human
  action. Distinguished from all of the above, each of which refuses rather than
  fresh-starts; fresh is reachable only through this one path.

## Ruling 2 — a persistent change marks the Campaign dirty; a checkpoint lands within thirty seconds of the first one

*(Human ruling on #4, 2026-08-08T21:51:14Z, `#issuecomment-5228365346`.)*

Any persistent strategic change marks the Campaign dirty: accepted Commands,
income, Objective ownership, Squad state, Contacts, Base destruction, and player
role/loadout choices. Bursts are coalesced, but a durable checkpoint lands
within thirty seconds of the **first** unsaved change — not the last change of
an indefinitely extended burst — and a final checkpoint is forced on clean
teardown. The writer snapshots a consistent copy and never holds Command
handling across disk I/O. Crash loss is therefore bounded to at most thirty
seconds of dirty strategic progress rather than the whole Play Session.

The anchor is the first dirty change, deliberately. A burst that keeps arriving
changes cannot push the checkpoint later by arriving: once the Campaign is dirty
the thirty-second clock is running, and a checkpoint taken within it satisfies
the bound regardless of what arrived in between. This is what makes "coalesce
bursts" and "bounded loss window" compatible rather than contradictory —
coalescing reduces write frequency, the first-change anchor bounds the window
that reduction is allowed to buy.

ADR-0008 said the snapshot is "autosaved periodically during a Play Session and
at session end"; "periodically" is what this ruling makes concrete, and the
concrete number is recorded against the only measure that chose it: a play
session's tolerance for lost progress, set by the human at the review. It is not
a measured cost, and a later reader who re-measures disk or frame cost and finds
thirty seconds loose should know the bound was set for tolerance, not tuned for
cost — re-measuring is due only if playtest tolerance moves (CLAUDE.md's
elimination-context rule).

## Ruling 3 — a resumed Campaign is projected through the ordered Effect outbox behind a fail-closed barrier

*(Human ruling on #4, 2026-08-08T21:57:32Z, `#issuecomment-5228386677`.)*

The Campaign is restored through the ordinary ordered Effect outbox. During boot
the Play Session is visibly resuming: it serves no Commander view as live and
accepts no Commands until the world has applied and acknowledged the complete
reconstruction sequence. Only then do normal reporting, planning and play begin.
No bulk world-change carrier is added and no progressive reconstruction is
exposed.

The barrier is fail-closed. Its reconstruction sequence is the full set a resume
must re-establish — Squads spawned, their standing Orders, Objective and Base
public state, player role/Squad, and chosen loadouts — and it stays red on a
missing acknowledgement or an oversized Effect that the outbox cannot drain. It
does not open on a timeout. Current sizing supports the ordered-Effect path: one
drain carries 72 measured `squad_spawned` Effects, Stratis's normal planner cap
is eight Squads per side, and even the much higher wire ceiling drains spawn
reconstruction over a small bounded number of two-second polls (ADR-0018). The
implementation must measure the complete spawn/Order/role/loadout sequence and
keep the barrier closed if it does not drain — the ruling names the principle,
#292 owns the measured threshold.

This is why the snapshot is never returned through `view`, `observe`, a debug
verb or the independent oracle: a snapshot carries both sides (#27 made "no
document carries both sides" structural everywhere else), so a save/load reply
is an acknowledgement only — a path, a version, a checksum, a rollback warning —
never the document. #289's `snapshot.py` is already the mechanical form of that:
its parser refuses an Observation and an Observation's parser refuses a save, so
a view cannot be loaded as a save and a save cannot be served as a view.

## The durability ordering

A crash between any two steps of the write must leave either the new snapshot or
the previous verified one intact, never torn data and never nothing. The
ordering the writer follows is:

1. **Write a temporary file** in the destination filesystem.
2. **Make the file's bytes durable** (`fsync` the file).
3. **Atomically replace** the current snapshot (`rename` over it).
4. **Make the directory entry durable** (`fsync` the directory).
5. **Promote the verified snapshot to last-known-good** — only after the new
   generation is fully durable and independently revalidated does it become the
   fallback a future failed load recovers to.

The previous verified snapshot is retained until step 5 completes, so a failed
save never destroys both generations. Exact names, the directory layout and how
many generations are kept are implementation choices for #290; the ordering
itself is the decision, because it is what makes Ruling 1's "verified
last-known-good" recoverable and Ruling 2's "consistent copy without blocking"
possible on a POSIX filesystem.

## What is not decided here

These are the choices the rulings leave to the implementation tickets, recorded
as choices rather than taken:

- **Filenames, directory layout, generation count, checksum algorithm.** #290.
  The ordering and the verified-last-known-good retention are decided; the names
  are not.
- **The "oversized Effect" threshold.** #292. Ruling 3 names the principle
  (fail-closed if the sequence does not drain); the measured byte/poll threshold
  is #292's, against the 72-Effects-per-drain and eight-Squads-per-side figures
  the ruling carries.
- **Serialise-under-lock vs copy-then-serialise.** #290. Ruling 2 requires a
  consistent copy with Command handling released for I/O; the mechanism is
  #290's.
- **The reply vocabulary of the save/load handlers.** #291. Ruling 3 fixes that
  the reply is an acknowledgement, never the document; which operational facts
  (version, checksum, generation, rollback warning) it carries is #291's.

## The dependency-ordered tickets, checked against this record

#288's acceptance requires that #289–#293 be checked against the final record
and amended if it exposes a missing criterion. Each ticket's criteria already
trace to a ruling or the durability ordering; the record exposes no missing
criterion in any of them, and no amendment is needed.

- **#289 — versioned snapshot schema and migrations (closed, `e299d06`).** Its
  criteria are the pure document: the version integer, the closed typed field
  set, the additive golden-fixture migration, the typed refusal for an
  unsupported version, the privacy of the whole-Campaign document, loadout
  catalogue IDs, and the refusal of a completed-Campaign record. Ruling 1's
  typed-refusal half is already its criterion; the load-failure *recovery*
  behaviour (last-known-good, rollback) is #290's, not the pure document's.
- **#290 — atomic store, last-known-good recovery, checkpoint coordinator.**
  Carries Ruling 1 (invalid-newest preserved, fallback warning, refuse if none
  valid, explicit-fresh-only), Ruling 2 (dirty-on-mutation, thirty-seconds-from
  -first even as mutations continue, teardown checkpoint, consistent-copy-under
  -lock with I/O after releasing Command handling), and the durability ordering
  (temp file, durable bytes, atomic replace, durable directory; previous
  verified retained until the replacement is durable and revalidated).
- **#291 — acknowledgement-only save/load on an own connection.** Carries the
  privacy ruling (no view/observe/debug/oracle retrieval; ack-only replies),
  ADR-0018's own-connection requirement, the typed refusal on failed load with
  unsupported and no-valid-generation distinguished, epoch identity and replay
  idempotency.
- **#292 — world reconstruction behind the readiness barrier.** Carries Ruling 3
  in full: the complete ordered sequence, the visible resuming state with no
  Commands/planning/reports/live-view until final acknowledgement, fail-closed
  on missing/out-of-order/duplicated/rejected/oversized Effects, the existing
  poll/ack carrier with no bulk path, and the measurement at the eight-Squads
  planner cap and the wire ceiling.
- **#293 — explicit boot, fixtures, teardown, resume-fidelity, audit.** Carries
  the explicit-fresh-only boot, the teardown checkpoint with the thirty-second
  window, the fixture-boot path, end-to-end resume fidelity, completed-Campaign
  retirement to ADR-0023's record, and the snapshot-never-crosses-to-views
  audit.

## What would reopen this

These are human rulings, so the question is what would move the human to reopen
them, not what evidence overturns an agent's guess. Each ruling carries its own:

- **Ruling 1** reopens if a playtest finds the verified-last-known-good
  retention too aggressive — a Campaign that rolls back on a recoverable
  transient the preservation-for-diagnosis kept — or if operator diagnosis shows
  the preserved-for-diagnosis snapshot is never actually usable, making
  preservation dead weight. It does not reopen on "a fresh Campaign would be
  more convenient": that convenience is the corrupted-world outcome the ruling
  refuses.
- **Ruling 2** reopens if playtest finds thirty seconds of lost progress
  unacceptable on one side (tighten) or the checkpoint cost perceptible on the
  other (loosen). The number is a tolerance, not a measurement; re-measuring is
  due only if tolerance moves.
- **Ruling 3** reopens if the measured reconstruction sequence cannot drain
  over bounded polls at the wire ceiling — i.e., if the sizing assumption the
  ruling carries (72 Effects/drain, eight Squads/side) does not hold and the
  barrier would either stall indefinitely or truncate. That is the one case that
  would reopen the "no bulk carrier" clause; a playtest that merely finds resume
  slow does not, because the barrier is fail-closed by design, not fast by
  design.

## Consequences

The phase's dependency order — #289 → #290 → #291 → #292 → #293 — puts the
human-approved semantics (this record) ahead of the schema (#289, already
landed), the schema ahead of durability (#290), durability ahead of control
(#291), control ahead of world projection (#292), and all of them ahead of the
acceptance audit (#293). #25 is named where persisted player-Squad state and
world projection depend on its decision record, and arrives as an additive
migration rather than a redesign (ADR-0008). A completed Campaign retires the
resumable snapshot and writes ADR-0023's non-loadable record, so the two
artefacts keep separate schemas and separate lifetimes.

This ADR amends none of ADR-0003, ADR-0008, ADR-0018 or ADR-0023: each is either
consistent with the rulings (ADR-0003's "crash loses at most one autosave
interval" is the thirty-second window; ADR-0018's reserved `rpc_async`
own-connection is #291's transport) or silent where this fills the silence
(ADR-0008 on crash-consistency, cadence and load-failure). Where a reader of
ADR-0008 looks for what a boot does with a snapshot that will not load, the
answer is here.

Refs #4, #25, #95, #289, #290, #291, #292, #293, ADR-0003, ADR-0008, ADR-0018,
ADR-0023, ADR-0025, ADR-0056.
