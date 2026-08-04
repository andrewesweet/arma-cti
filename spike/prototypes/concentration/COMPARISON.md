# Concentrating force: three shapes compared (#187)

**Outcome.** Every arm that concentrates gets the same men onto the same ground at the same
moment; they differ in what they cost and in whether they hold. The efficacy numbers separate
the status quo from the rest and barely separate the rest from each other. The complexity
numbers separate them sharply, and one arm turned out to cost almost nothing: widening
ADR-0027's existing Base mass to every contested place is a **39-line planner change touching
no wire field, no SQF, and no CONTEXT.md term**, and it inherits #181's commitment hysteresis
for free. The scratch-echelon layer buys nothing extra in efficacy on these boards and costs a
new persisted object, ADR-0004's purity claim, and four CONTEXT.md entries.

Two premises in #177's own framing did not survive the measurement, and both matter to the
ruling:

1. **An echelon layer does not get synchronisation from the engine.** #177 hoped "the
   coordination lives inside the Platoon, where the engine's own group behaviour can carry a
   good deal of it." There is no cross-Squad wait, rally, or hold-until anywhere in the SQF
   today, and ADR-0039 forbids the group merging that would create one. Board B′ below is the
   measurement: with the rally switched off, the echelon arm arrives exactly as raggedly as the
   status quo — 361 s apart, 8 men at first contact. Synchronisation is a separate build, and
   arms (b) and (c) need the *same* one.
2. **"A term that can score two-on-one" is a capacity rule wearing a factor's clothes.** A
   multiplicative consideration can only discount, so it cannot make a second Squad worth more
   than the first; it works only where it is ≈1.0 while under-matched and collapses once
   matched, which is a threshold. Measured: the term arm concentrates at every exponent tried,
   but with the *wrong* Squads at the two non-degenerate ones, and it thrashes at **0.208**
   where the other two arms thrash at **0.000**.

MVP-or-post-MVP is still open, and so is the structural decision. This document is the
comparison it was to be taken with.

---

## What was measured, and how

The #104 and #181 pattern: the **real** `UtilityPlanner` and the **real** `CommandPort` over
staged Stratis boards, 30 seeds per arm per board, no Arma. What is a stand-in is the world.
Squads march at **2.0 m/s** along the same authored adjacency graph the planner scores over —
the speed the planner's own docstring records from `spike/probes/ai-commander.sqf` (1,076 m in
about nine minutes, 2,065 m in about seventeen). Nobody shoots.

Run it with:

```
uv run python spike/prototypes/concentration/compare.py
```

### The arms

| | what it is |
|---|---|
| **a** status quo | the shipped `UtilityPlanner`, imported unmodified. One Squad per Place, except ADR-0027's Base mass |
| **b1** term | the veto deleted, replaced by a concentration factor on the score. Swept at three curve exponents: `x²`, `x¹`, and the degenerate step |
| **b2** muster | ADR-0027's `_mass` asked about every contested place rather than the enemy Base alone. Everything downstream is the shipped `_muster`/`_detail`/`_Demand` |
| **c** detachment | the planner composes a scratch grouping from owned Squads, scores at that level, and orders it. The shipped scorer runs unmodified inside, over an echelon-level Observation |

"Detachment" is a **working label only**. `Platoon` is not available: CONTEXT.md's **Contact**
entry already spends the word as an echelon *band* and states that a band "is a size estimate,
never a unit of command", and both `ECHELON_THREAT` and `ASSAULT_MASS` are keyed on it —
`ASSAULT_MASS["platoon"] == 3` would read as "a Platoon is three Squads", which is not what it
says. The real term is the human's, through `/domain-modeling`.

### The boards

- **Board A — an Objective.** EAST holds Camp Rogain with a squad-banded Contact on it; WEST
  holds the rest of the island and has four Squads within reach. Doctrine (`ASSAULT_MASS`) wants
  two Squads against a squad band. This is the playtest's own case and the one the veto forbids
  outright.
- **Board B — the staged two-Squad Assault** the acceptance criteria name. #181's
  `massed_on_kamino` position: island held, squad-banded Contact on the enemy Base, doctrine
  wants two. Every arm sends two here, because ADR-0027 already masses on a Base. What differs
  is how the two travel.
- **Board B′ — Board B with synchronisation switched off**, isolating what the rally mechanism
  itself is worth from what the Squad count is worth.
- **Thrash** — 20 cycles × 30 seeds with the Contact on Camp Rogain flickering out and back on
  alternate cycles: #181's disturbance exactly, moved off the Base and onto the ground being
  concentrated against. Purse emptied, so a fresh Squad taking contested ground cannot re-task
  anyone for reasons unrelated to the picture.

---

## Efficacy

### Board A — an EAST-held Objective, squad band, doctrine wants 2

| arm | Squads sent | men at first contact | first contact (s) | separation (s) | all on target (s) | other places still held |
|---|---|---|---|---|---|---|
| a  status quo | **1** | **8** | 361 | 0 | 361 | 3 |
| b1 term x² | 2 | 16 | **1313** | 0 | 1313 | 2 |
| b1 term x¹ | 2 | 16 | **1313** | 0 | 1313 | 2 |
| b1 term step | 2 | 16 | 826 | 0 | 826 | 2 |
| b2 muster | 2 | 16 | 826 | 0 | 826 | 2 |
| c  detachment | 2 | 16 | 826 | 0 | 826 | 2 |

Identical across all 30 seeds in every cell.

The status quo cannot send two Squads at an Objective at all — that is the veto, and it is
#177's complaint restated as a number: eight men against a squad-banded garrison, with three
more Squads inside two kilometres.

Concentration costs 465 s of delayed first contact (361 → 826) and one place of dispersion
(3 → 2). The veto's legitimate job survives in every arm: none empties the island.

The two non-degenerate term curves cost a further **487 s** (826 → 1313) for the same two
Squads. The discount is steep enough that the second slot goes to whichever Squad had least to
lose elsewhere rather than to the nearest one — the term concentrates with the wrong Squads.
Only the degenerate step, which is a capacity rule, picks the same pair the assignment-rule arms
pick.

### Board B — the staged two-Squad Assault on the enemy Base

| arm | Squads sent | men at first contact | first contact (s) | separation (s) | all on target (s) |
|---|---|---|---|---|---|
| a  status quo | 2 | **8** | **801** | **361** | 1162 |
| b1 term (all three) | 2 | 16 | 1162 | 0 | 1162 |
| b2 muster | 2 | 16 | 1162 | 0 | 1162 |
| c  detachment | 2 | 16 | 1162 | 0 | 1162 |

Identical across all 30 seeds.

Every arm sends the same two Squads, because ADR-0027's mass already does this. The whole of the
difference is the rally, and it is the human's verbatim observation measured: **"they'll arrive
at different times and attack independently"** is 361 s — six minutes — of one Squad fighting
alone.

Note the last column. **`all on target` is unchanged at 1,162 s.** The rally optimiser puts the
form-up on the trailing Squad's route, so synchronisation costs nothing in time-to-full-strength;
it moves who waits where. The leading Squad spends its 361 s at the last covered place instead of
standing alone on the objective. On an Assault that is free. On a Capture it is not — the capture
clock does not start until somebody is in the radius, which is the `first contact` column, and
that is a real cost worth a gameplay-feel judgement.

### Board B′ — the same, synchronisation off

| arm | men at first contact | separation (s) |
|---|---|---|
| every arm, including c | 8 | 361 |

This is the measurement behind finding (1) above. Hold the Squad count fixed and remove the
rally, and the echelon layer is indistinguishable from the status quo. **A Detachment arrives as
a Detachment only if something makes its Squads move together, and nothing in this system does.**

### Thrash — committed Squads re-tasked under a flickering Contact

20 cycles × 30 seeds. A *committed* Squad is one standing under an offensive Order naming a
place; a *re-tasking* is that Squad being given a different Order in a later cycle.

| arm | re-tasked | committed Squad-cycles | rate |
|---|---|---|---|
| a  status quo | 0 | 1140 | **0.000** |
| b1 term x² | 300 | 1440 | **0.208** |
| b1 term x¹ | 300 | 1440 | **0.208** |
| b1 term step | 300 | 1440 | **0.208** |
| b2 muster | 0 | 1710 | **0.000** |
| c  detachment | 0 | 1710 | **0.000** |

300 re-taskings is exactly one per flicker per seed: **every time the Contact vanishes for one
sample, the term arm sheds a committed Squad, and re-commits it when the Contact returns.** That
is #181's failure mode reproduced on an Objective, and it is the same failure for the same
reason — a demand re-derived from the picture every cycle, with nothing flooring it.

The status quo scores 0.000 because it never concentrates, so it has nothing to shed. That is a
null, not a virtue.

`b2` scores 0.000 because `_Demand.committed` already exists: widening `_mass` widens #181's
hysteresis with it, at no extra cost. `c` scores 0.000 structurally — once composed, a
Detachment's membership does not move, so intra-Detachment thrash is impossible by construction
rather than by margin.

This is #181's corroboration the ticket asked for, from the other direction: the fix at 64e13f4
is not local to Bases, and any Squad-grained concentration built as a score needs it or
reproduces the bug.

---

## Complexity

Surfaces touched per arm. "rally" rows are the synchronisation work, which arms (b) and (c) need
**identically** — B′ is the evidence — so it is broken out rather than charged to one of them.

| surface | a | b1 term | b2 muster | c detachment |
|---|---|---|---|---|
| **planner.py** | — | +47 lines: `_assign` rewritten greedy → iterative best-first, `_concentration` added, 2 new tuning fields, a per-place demand map threaded through `plan` | **+39 lines**: `_mass` widened (20), `_detail` one-line safety fix (19) | +114-line stateful layer; ADR-0027's `_mass`/`_muster`/`_detail`/`_mustered`/`_Demand`/`_Muster` (218 lines, 92 of code) become dead at this level |
| **planner invariants** | — | the trace diverges: `Decision.candidates` carry the compensated product, the assignment uses a different number. A reader arguing from the trace is reading the wrong score | none. Same trace shape, same `_mustered` row, `"1 wanted, 2 committed"` already reads correctly | **ADR-0004's purity claim breaks** — the layer holds composition state across cycles, so `plan` is no longer a pure function of one Observation |
| **wire schema** | — | 0 for concentration | **0** | 0 if the layer is daemon-only, but then the human Commander cannot name a Detachment and ADR-0012's symmetry breaks. Otherwise: new verb in `commands.CATALOGUE` + `port.HANDLERS` + refusal codes, new Effects (formed/dissolved), a new Observation record type + `DOCUMENT_FIELDS`, a new `budget.worst_case()` term (which *lowers* `force_limit`), schema regen |
| **SQF** | — | 0 for concentration | **0** | echelon-aware `fn_mapVerbs`/`fn_mapIssue`/`fn_mapRender`/`fn_effectApply` if the wire grows; a sibling store beside `cti_squads` |
| **CONTEXT.md** | — | 0 for concentration | **0** — ADR-0027's own precedent: "`ASSAULT_MASS` is machinery, not vocabulary" | **Squad** ("The unit of command"), **Order** ("instruction to one Squad"), **Contact** (the echelon-band collision), plus one new term with an _Avoid_ list. Human sign-off gate |
| **ADRs** | — | 0027 revisited, 0031 touched (the score the trace shows is not the score used) | 0027 amended — its own overturn clause at line 142 anticipates exactly this ("a second thing that wants sizing rather than pricing") | a new ADR plus 0004, 0008, 0012, 0020, 0027, 0030 |
| **persistence** | — | 0 for concentration | **0** | a new persisted record type with an id-minting rule that must reproduce `Roster.add`'s resume determinism, plus a lifetime and a dissolution rule. **No precedent** — `Campaign` holds no other object with a lifetime |
| *rally (both arms need it)* | | `squads.Order` +1 field → `commands.CATALOGUE["order"]`, `port._order`, `Campaign.issue`, `EFFECTS["order_issued"]`, `SquadView` + `SQUAD_FIELDS`, `budget.worst_case()`, `export_command_schema.py` + regen; SQF `fn_orderApply`, `fn_orderEnforce`, `fn_command`, `fn_mapVerbs`, `fn_mapIssue`, `fn_effectApply`, `fn_mapRender`; CONTEXT.md **Order** and **Place** + one new term; ADR-0020 amended; +1 additive snapshot field (ADR-0008 permits) | | |

The single largest item is not in the table: **a cross-Squad wait does not exist anywhere in the
SQF.** Every `waitUntil` in the addon is loop pacing or display readiness. `fn_orderApply` sets
waypoints per group and `fn_orderEnforce` re-asserts them every 10 s, so a hold-until has to be
something `fn_orderEnforce` knows not to fight. That is new mechanism, not a new field, and it is
the same work whichever arm asks for it.

### Three defects found by building the arms

Each was a real bug in the extension, not a prototype artefact, and each is a cost the paper
design would not have shown:

1. **`_muster` is written for one massed place.** It details each wanted place in turn and merges
   with `detailed |= crew`; `_detail` seeds its crew from the bid without consulting
   `spoken_for`, so a second massed place silently reclaims a Squad the first was given. On
   Board A this produced a plan that issued one Order while its own trace said "massed 1,
   2 wanted". One line fixes it, and it is charged to `b2` above.
2. **The echelon layer double-counts doctrine.** Arm (c) put *three* Squads on a Base a squad
   band wants two for: the layer composed a two-Squad Detachment, then ADR-0027's mass inside
   the scorer demanded two *Detachments*. Concentration has to move out of the muster entirely
   when it moves into composition — which is #177's "the veto stops being wrong", made true
   rather than argued.
3. **The echelon layer silently breaks two Squad-grained counts.** `_spend`/`_fresh_barred` read
   `len(observation.squads)` for the map's one-per-Objective cap and the wire's `force_limit`;
   at echelon level that counts Detachments. And `_options`'s `watched` set — "ground one of ours
   is standing on is ground being looked at" — becomes the Detachments' muster places, so the fog
   floor changes meaning. Neither is hard to fix; both are invisible until something counts.

---

## What the offline harness cannot see

Stated plainly, because it bounds every number above.

- **No engine pathing.** The march model is straight graph distance at a constant 2.0 m/s. Real
  Squads take terrain, bunch at obstacles, and route around. Every separation figure is a **lower
  bound** on the real spread, and the rally's "free" consolidation time is the most optimistic
  reading available.
- **No firefights.** Nobody shoots. "Combined strength at first contact" counts men *present*,
  not men *effective*. The premise that 16 men together beat 8 + 8 arriving six minutes apart is
  assumed, not tested — it is the doctrine ADR-0027 was signed off on, and this prototype
  inherits it rather than confirming it.
- **No engine AI behaviour.** Whether a rally actually holds a Squad, whether `fn_orderEnforce`
  fights a hold-until, whether two Squads at one rally deconflict or shoot each other's flanks —
  all unobserved. This is exactly where the regression tier's rule bites: bet on the decision the
  code owns, never on a world-owned outcome.
- **The flicker is modelled, not measured.** Alternating cycles is the shape of #181's red run,
  not its frequency. `0.208` means "one re-tasking per flicker", not an in-world rate.
- **One map, one board shape each.** Stratis. A larger island changes every march and #28 makes
  the Contact set grow with it, so ADR-0030's budget reasoning would want re-measuring before an
  echelon record is promised on Altis.
- **No economy pressure in the thrash sweep.** The purse is emptied deliberately, per #181's own
  note. A Commander that is buying has another re-tasking source this measure excludes.

---

## What is being asked

The structural decision is the human's. The comparison says:

- **The cheapest thing that answers #177's AI half** is `b2` — 39 planner lines, no wire, no SQF,
  no vocabulary, ADR-0027 amended under its own overturn clause, hysteresis free. It does *not*
  answer the human half: the human Commander still has no way to say "these two, together".
- **The synchronisation primitive is a separate build from the concentration**, needed
  identically by `b` and `c`, and it is where the wire, the SQF and the vocabulary cost actually
  lives. It could be decided on its own.
- **The echelon layer's case is not efficacy.** On these boards it does what `b2` does, for a new
  persisted object, ADR-0004's purity, and four CONTEXT.md entries. Its case, if it has one, is
  the third seat #177 names — a human Platoon Commander where orders meet ground — and this
  prototype measures nothing about that.
- **If the wire is to grow an echelon at all, the choice is now, not later.** ADR-0008 permits
  additive field migrations, not new record types, and #177's own note stands: an echelon layer
  is either the shape the wire grows into or a later break.

## Provenance

Prototype branch `prototype/187-concentration`, commit trail under `refs #187`. Code:
`spike/prototypes/concentration/{harness,arms,compare}.py`. Throwaway per the `/prototype` skill
— nothing here is production code and none of it is imported by `src/` or the unit tier. The
one repo gate that applies is `just fast`, which is green (1296 passed, all checks passed);
nothing here touches an in-world surface, so no Arma tier was run and none was required.
