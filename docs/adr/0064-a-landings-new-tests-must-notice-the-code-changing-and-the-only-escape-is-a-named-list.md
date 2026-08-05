# A landing's new tests must notice the code changing, and the only escape is a named list

Delegated-decision: yes
Date: 2026-08-05
Stood-in-for: human sign-off on a new ADR, and on which mutation engine this project carries —
#239 commissioned the gate and asked for the engine to be picked on evidence, which is a
choice with a dependency and a toolchain line behind it
Reviewed-by-human: pending
Claimed: comment on #239, 2026-08-05, after `git fetch origin` (`docs/adr/` on `origin/main`
topping at 0063) and a scan of every open issue's body and comments, whose highest claim was
also 0063

## What happened

From the lane-quality assessment the human commissioned #239 out of. Nothing mechanical
stops a vacuous green test. The defences were four, and none of them is a gate:

- **Red-first discipline**, which lives in a dispatch briefing. Prose, and unenforced for a
  session this project did not write the briefing for.
- **The non-vacuity-by-mutation habit**, visible in closing comments — #214 and #196 both
  quote planted mutants killed by hand — which is a habit, and a habit is what a tired agent
  drops.
- **The probe vacuity rule** (#116), which governs probes and only probes.
- **`mutmut`**, named in CLAUDE.md's toolchain since Phase 0 and scoped to "snapshot save/load
  and the planner". #172's close found that scope naming modules that do not exist, and
  reported it not running against this repo's pytest config.

So a suite of `assert True` passed `just check`, passed `just unit`, and landed. That is the
hole. `docs/research/mutation-testing.md` is the measurement behind everything below.

## Decision 1: mutation testing here is a bespoke bounded mutator, not mutmut and not cosmic-ray

`tools/mutation_smoke.py` owns the engine: an `ast` walk producing byte-span replacements,
guarded by a `compile()` of the result.

Not for want of trying the alternatives. **mutmut 3.6.0 does run here** once `source_paths`
points at the package rather than at a file and the trees the tests read are in `also_copy` —
the failure that reads as an xdist incompatibility is an `ImportError` in the copied tree,
with `-n auto` merely visible in the argv the exception prints. What it then reports is the
objection: on `src/cti_daemon/dedupe.py`, 75 lines with a test module written first, it
planted 8 mutants and 3 survived — `digest_size=16` dropped, `digest_size=17`, and `"utf-8"`
spelled `"UTF-8"`. All three are equivalent mutants against an opaque digest. **62.5%** on a
module whose tests are sound means a floor below 62.5%, and a vacuous suite that runs the code
at all clears that. The floor and the threat cannot be separated.

**cosmic-ray 8.4.6** installs but is built around a session database, a distributed executor
and resumable sweeps; its unit of work is the overnight sweep a human browses, not a bounded
sample a gate compares. Adopting it would add SQLAlchemy to a project whose only runtime
dependency is `networkx`, to obtain a bounded sample this project would still have to define.

The operator set that ships is chosen for a low equivalent-mutant rate rather than for
coverage of the literature: string literals, keyword-argument values, parameter defaults and
everything inside an f-string are never touched, and each of those exclusions is a regression
test named after the mutmut survivor that motivated it.

**What would overturn this.** A released mutation engine that (a) plants a caller-bounded
sample without a full generate-and-stat pass, (b) pairs each mutant with only the tests that
reach its line, and (c) scores this repo's sound modules high enough that a floor separating
them from a vacuous suite exists. Or the mutator here growing past the point where owning it
is cheaper than configuring one — the honest tripwire is when its own test module stops fitting
in one sitting's reading.

## Decision 2: the subject is chosen by coverage evidence, and having none is a red

The module under smoke is run once under `coverage.py` with `dynamic_context = test_function`,
and the subject is the product file with the most lines executed **inside a test**. Not the
`test_x.py` → `x.py` convention: `tests/unit/test_land.py` → `tools/land.py` already only half
obeys it, and the sweep found `tests/unit/test_budget.py` spending most of its lines in
`manifest.py` rather than `budget.py`.

Import-time lines carry an empty context and do not count. That is the load-bearing half: it
is what makes an `assert True` module subject-less rather than the accidental owner of
everything `tests/unit/conftest.py` imported, and "no subject" is therefore a red in its own
right — a test module none of whose tests executes a line of this repo's source has,
mechanically, tested nothing.

**What would overturn this.** A sound test module in this repo whose subject the rule picks so
badly that its mutants are unkillable by design — the fix would then be per-module subject
declaration, not a lower floor. Or a coverage release in which `dynamic_context` stops
distinguishing import time from test time, which would remove the distinction the rule rests on.

## Decision 3: the gate is a rung in `just fast`, scoped to the diff, and that is where lane-blindness comes from

`just mutation` runs `tools/mutation_smoke.py`; `fast: check unit mutation` puts it after the
suite, because a red suite says nothing about mutants. `tools/land.py` runs `just fast` as the
landing gate, so **every** landing meets it — a z.ai lane, a Codex lane and a native session
meet the identical red, without any of them knowing the gate exists.

Scope is the diff against `origin/main`, committed and uncommitted: every test module the
landing adds or rewrites. Not the whole corpus — that is a sweep, and a sweep does not belong
in a recipe run after every edit. Deletions are out of scope; a test module that is gone tests
nothing and there is nothing to plant in.

**What would overturn this.** The measured cost in §5 of the research note growing past what
`just fast` can carry — #197's cliff is five minutes for a subagent turn, and the mutation
rung eating that headroom would move it to `just land` alone, at the price of an agent meeting
it later.

## Decision 4: the only escape is `NO_PYTHON_SUBJECT`, a named list with reasons

Some test modules in this repo have no Python subject and are not vacuous:
`tests/unit/test_bringup_guards.py` asserts on `spike/run.sh`, `spike/tier-lock.sh` and the
justfile. Mutating Python has nothing to say about them, and reding them would be #137/#186's
false red on the tree the gate exists to protect.

So there is an escape, and it is deliberately the *only* one. There is **no** flag that lowers
the floor in `just fast`, **no** marker a test file can carry to excuse itself, and **no**
environment variable. A module that tests nothing can be excused only by a row in
`NO_PYTHON_SUBJECT` in `tools/mutation_smoke.py`, with its reason beside it, in the diff. The
reasoning is ADR-0016's and #116's: an escape that lives where the work lives is taken quietly,
and an escape that lives in one greppable list is taken visibly.

Lowering `FLOOR` is not an alternative to a row here, and is not an alternative to strengthening
an assertion.

**What would overturn this.** The list growing past the point where it reads as a list of
exceptions rather than a second corpus — a dozen rows would mean the subject rule is wrong for
this repo's shape, not that a dozen modules are special. Or a row being added in a landing
whose review did not notice, which would say the visibility this decision rests on is not real.

## Decision 5: `mutmut` leaves the dev dependency group, and CLAUDE.md's toolchain line is proposed rather than edited

The dependency goes, because a tool this project has decided not to use is a tool whose next
release is somebody's rebase problem. CLAUDE.md's Toolchains line still reads "`mutmut` scoped
to snapshot save/load and the planner", which is now false in both halves; that file is a human
sign-off gate, so the amendment is **proposed in #239's closing comment and not made here**.
The same goes for the command-table row for `just mutation`.

**What would overturn this.** The human preferring to keep `mutmut` available for a
hand-driven deep sweep of one module, which is a use this gate does not serve and does not
claim to; it would come back as a dev dependency with that sentence next to it.

## Consequences

- A landing that adds a test module now pays a few seconds per module and gets a mechanical
  answer to "do these tests notice anything".
- The habit in #214's and #196's closing comments has a machine behind it; the hand-planted
  six-mutant demonstration is no longer the only evidence a close can offer.
- The gate measures **change-detection**, not assertion quality. A module that exercises its
  subject and asserts only `is not None` can still clear the floor on crash-kills; the research
  note measures one doing so and says so. This is a floor under vacuity, not an oracle for it.
- `just fast` grows a rung whose cost is stated in the research note and in #239's close.
