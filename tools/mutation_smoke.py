"""Red a landing whose new tests do not notice the code changing (issue #239).

Every other gate in `just fast` asks whether the code is right. None of them asks
whether the *tests* are. A suite of `assert True` passes `just check`, passes
`just unit`, and lands — the defences against that were red-first discipline in a
briefing (prose, unenforced for a session on another lane), a habit visible in closing
comments (#214, #196: "six planted mutants, all six killed" — by hand, every
time), and `mutmut`, which #172's close found scoped to modules that did not
exist and which does not run against this repo's pytest config as shipped.

This is that habit mechanised: for every test module a landing adds or rewrites,
plant a bounded sample of mutants in the source those tests actually execute and
require the tests to notice. Lane-blind by construction — it is a rung in
`just fast`, which `tools/land.py` runs as the landing gate, so a z.ai or Codex
landing meets exactly the same red as a native one.

## Why a bespoke mutator rather than mutmut or cosmic-ray

Measured on this tree, 2026-08-05, not inherited (see `docs/research/mutation-testing.md`):

- **mutmut 3.6.0 can be made to run** — `source_paths` at package level, the
  tests/tools/config trees in `also_copy`, `-n0` in `pytest_add_cli_args` — but
  what it then reports is unusable as a gate. On `src/cti_daemon/dedupe.py`, a
  module whose tests are sound, it generated 8 mutants and 3 survived: dropping
  `digest_size=16`, spelling `"utf-8"` as `"UTF-8"`, and `digest_size=17`. All
  three are *equivalent* — the dedupe window keys on an opaque digest, so no
  test can tell. A kill-rate floor over that operator set would have to sit below
  62.5% to keep the tree green, which is a floor no vacuous suite would trip.
- **cosmic-ray 8.4.6 installs** (29 packages, SQLAlchemy among them) and is built
  around a session database and a distributed executor. Its unit of work is a
  full sweep to be resumed, not a bounded sample judged inside a gate.
- Both mutate a whole file or a whole tree and run the whole suite per mutant.
  This gate needs the opposite shape: a handful of mutants on the lines *one new
  test module* executes, each judged by *only the tests that reach that line*.

So the operator set here is chosen for a low equivalent-mutant rate rather than
for coverage of the mutation-testing literature — string literals are never
touched, keyword-argument and default-argument values are never touched, and
what remains is the arithmetic of decisions: which way a comparison points,
which way a boolean joins, whether a `not` is there, what a function hands back.

## How a subject is chosen

The module is run once under `coverage.py` with `dynamic_context =
test_function`, and only lines executed *inside a test* count — import-time lines
carry an empty context, so a module that imports the world and asserts nothing
has no subject at all. That is the second red this gate can give, and it is the
one an `assert True` module earns: a test module executing none of this repo's
source under any of its tests has, mechanically, tested nothing.

Among the files that do qualify, two rules in order. **The name first**, when the
tests reach it: `test_budget.py` → `budget.py` is a statement of intent by whoever
wrote the file, and it beats any inference. A qualified name falls back to what it
qualifies, longest match first — `test_daemon_casualties.py` → `daemon.py`, a shape
this repo writes a dozen times. **Then the evidence**, for the modules no name
reaches, such as `tests/unit/test_composition_root.py`. The evidence is not a line
count: a line *every* test in the module executes is arrangement, so each line is
worth the share of the module's tests that did not reach it. Counting lines alone
made `manifest.py` the subject of `test_budget.py` — 94 lines reached, 88 of them
by all four tests, because the shared arrangement loads a manifest first — and
scored a sound module 50% for not asserting about a file it never meant to test.

The obvious next step, restricting the *mutants* to those same discriminating
lines, was tried and is **not** here: it moved `test_daemon_casualties.py` from
40% to 25%, because the lines its tests share are the ones its assertions do
reach. Measured, disproved, recorded in the research note rather than carried as
an untested intuition.

## The selection rung: a module nothing was written for

Everything above measures a *test* module, which leaves one thing it cannot see.
A landing that adds `tools/x.py` and no `tests/unit/test_x.py` puts nothing in
scope at all, so there is no subject, no verdict and no floor — and the gate goes
green on a module it has never looked at. The silence is structural rather than
lenient: no rung ever learns the module exists. Three instances in one cycle
(#370, filed by retro 31): #324, whose `tools/generate_seats.py` landed unmeasured
and surfaced only when an unrelated harness defect turned its test module red;
#338; and #346, where production grew a private constructor purely to stay
scoreable.

So the diff is read a second way. Every product module this landing *introduces*
— added, or renamed to a name that was not there at the base — must come out of
the run as a verdict's subject, mutants planted in it and judged, and one that
does not is a red carrying the class `no_test_module`. A test file's name is not
the evidence (#370's own review): a `test_new_cases.py` that exercises only
existing code clears any filename check while its smoke plants every mutant in
some other file, so the check is bound to what the run measured, never to what
the files are called. Introduced rather than edited, measured before it was
written: eleven modules in this tree are tested under a name that does not reach
them, so asking the same of an edit would red a docstring fix. The escape is
`NO_TEST_MODULE`, the same named-list shape as everything else here — and a
blank reason on any entry of either list refuses the gate outright, because an
escape whose reason can be left blank is an escape with its cost removed.

One false red survives this and cannot be computed away in-repo, so it is
written where the rung is met rather than left to be inferred (#441). What
counts as introduced is measured against `origin/main` as this tree holds it, so
a stale ref names another landing's module as an introduction here. `just land`
fetches before it gates, which makes the landing gate right twice over; `just
fast` mid-work does not fetch, and that is exactly where the surviving false red
lives. The red's own text is the whole mitigation — it names the fetch first and
says which gate fetches for you — and the cost of putting it first is accepted
rather than absent: a reader whose module genuinely is new runs one fetch and
learns nothing from it. That is the cheaper error, because the fetch writes
nothing while both other remedies write code against a diagnosis that may be
wrong. Adding a fetch to `just fast` is not the fix: it would put a network call
into the loop an agent runs after every edit, and a gate that cannot run offline
is a worse gate than one that occasionally names a stale ref.

## The per-module ratchet

`FLOOR` is one number every module clears, set below the corpus minimum so the
tree stays green — which means it is decided by the weakest module and every
stronger one is gated far below what it already achieves (#244: weakest 62%,
median 85%, sixteen at 100%, floor 50%). The ratchet turns that into a
direction. Each module's measured kill rate is recorded in a committed baseline
against the subject it was measured on, and the gate reds when a module falls
below its *own* recorded rate. A new module meets `FLOOR`; an existing one may
never get worse; every strengthening of a test module becomes its new floor.

Three things a ratchet gets wrong, and how this one answers each:

- **A floor set from a single observation can lock in a lucky high.** This gate
  is deterministic where it can be and states the bound where it cannot (#435):
  the mutant sample is seeded, the subject's bytes are pinned, every Python
  subprocess runs under one pinned hash seed, and a mutant's selection takes every
  reaching test under a per-test ceiling rather than a clock-derived cumulative
  cut — the cut it replaced selected different tests for 532 of 874 covered
  lines between two fresh measurements of one unchanged module, and a kill
  moved with it about one run in six, at the same rate with the hash seed
  pinned as without. What still reads the clock, all three named by `SLACK`'s
  comment: the timeout that scores a hanging mutant as a kill (a loaded box
  can award that kill to a survivor), the straddle case of a duration crossing
  the per-test ceiling, and the over-ceiling fallback's single cheapest pick.
  The module budget does not read the clock into a verdict at all — when it
  fires the run refuses rather than reporting a rate on a denominator the
  clock moved (#435 round 2). A rate is therefore a fixed function of the
  (test module, subject) pair up to those three reads — which compound rather
  than each costing one kill, so no bound on how many kills they can move
  between them has been derived. `SLACK` is one because that is what the
  measured jitter moved, taken as a pragmatic tolerance and stated as that
  choice; beyond those reads, the only way the rate stops applying is a change
  to the tests or the subject, which is what the ratchet exists to notice.
- **A legitimate refactor that lowers a module's achievable rate must not be
  blocked.** Editing the subject changes which mutants exist, so the recorded
  rate is about a *pair*, not a module. The row pins the subject's bytes, and
  the gate releases the ratchet — back to `FLOOR` — the moment they diverge,
  then `--record` re-baselines against the new code. The ratchet never locks a
  module out of its own refactor.
- **Lowering a row must be visible.** `--record` raises a same-subject row and
  re-baselines a changed one, but it never lowers a same-subject row silently:
  it reports "held" and leaves it. Lowering is a hand-edit to the baseline, in
  the diff, with the same reviewability `NO_MUTABLE_SUBJECT` has.

`SLACK` is one kill: a module may lose one kill to its own recorded rate without
redding, and two lost kills is the weakening the ratchet names. That one is a
pragmatic tolerance, not a bound derived from the three clock-reads a verdict
still rests on (a duration straddling the per-test ceiling, the over-ceiling
fallback's cheapest pick, a timeout scored under machine load) — none of them is
bounded to a single kill, and nothing stops them firing together, so no bound on
how many kills they can move between them has been derived; one is taken because
the measured jitter (#435) moved a single kill at a time, and because a tolerance
wide enough to absorb every combination would absorb a real two-kill weakening
too. The baseline ships empty — landing the
mechanism without moving any number, so a first red is unambiguously a
mechanism failure rather than a threshold one — and is populated by
`--record`, never by the gate.

## Safety

Mutants are applied in place, to the real tree, because that is the only way the
tests run exactly as `just unit` runs them — `tests/unit/conftest.py` loads a
`tools/` script by absolute path and several tests shell out to `git` in the
worktree, so a copied tree is a different subject. In-place means a crash could
leave a mutant behind, so every mutation writes `RESTORE` first, restores in a
`finally` and on SIGINT/SIGTERM, and refuses to start while a stale `RESTORE`
exists — it prints how to undo it instead of guessing.

## The shell arm

A module whose tests execute no Python of this repository's own may still be
driving `spike/*.sh` as subprocesses and asserting on what those scripts do, and
eight of them were (#246). Those go to `tools/mutation_shell.py`, which reads
which line of which script each test executed out of a bash xtrace, plants the
same shape of bounded sample there, and judges it the same way. The routing is
mechanical rather than declared: the Python subject is tried first and wins where
it exists, the shell subject is only reached when there is no Python one, and
having neither is still the red it always was.

Two things differ, and both are in that module's own docstring: a shell mutant is
written into a hardlinked stage rather than in place, because `spike/*.sh` is read
by a live Arma tier; and `bash -n` stands in for `compile()`.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

import mutation_rust
import mutation_shell

if TYPE_CHECKING:
    from collections.abc import Callable

# Where this repo's own source lives. A file outside these is somebody else's
# code and is never mutated, however much of it a test happens to execute.
PRODUCT_ROOTS: Final = ("src/", "tools/", ".claude/hooks/")

# The sidecar that makes an in-place mutation recoverable. Held in the worktree
# root rather than under ~/.arma-cti, because the thing it repairs is this tree.
RESTORE: Final = ".mutation-smoke-restore.json"

# The per-module ratchet baseline (#244): a committed JSON the gate reads and
# `--record` writes. Each row is one test module's measured kill rate bound to
# the subject it was measured against, and the gate reds when a module falls
# below its own recorded rate rather than below `FLOOR` alone. Ships empty: no
# row is populated by landing the mechanism, so no floor moves and a first red is
# a mechanism failure rather than a threshold one. Populated by `--record`.
#
# Still empty, and not by drift (#363 is the first reader to ask). `--record`
# is a deliberate act outside `just fast` — the gate never writes — and no
# session has performed it for any module, so until one does the only floors
# enforced are `FLOOR` and `SHELL_FLOOR`, and a module's measured rate lives in
# the landing's gate output rather than here: a rate can fall to the floor
# without a red. A row is one `just mutation --record --paths <module>` away
# for any session whose allowlist reaches that recipe; #363's dispatch had no
# such allowlist, which is why this comment and not a row for
# `tests/unit/test_host_seam.py` (measured 10/10 against `spike/hosts.sh`
# there) is the close.
BASELINE: Final = "tools/mutation-baseline.json"

# Mutants planted per test module. Bounded on purpose: this is a smoke, not a
# proof. Twenty is enough that a suite asserting nothing cannot pass by luck
# (see `docs/research/mutation-testing.md` for the arithmetic) and few enough
# that the tier's cost stays inside the budget `just fast` can afford.
CAP: Final = 20

# The kill rate a module must reach. Set from the corpus sweep, not from taste:
# all 68 of this repo's test modules were measured (docs/research/mutation-testing.md
# §6), the weakest scored 62% and the median 85%, so a floor of 50% clears the
# whole tree by 12 points. It is deliberately below what most modules already
# reach — a gate whose first act is to red a tree it did not write is #137/#186's
# false red, and the way this number goes up is by strengthening the modules
# under it, never by a landing lowering it.
#
# The other end of the range is what it must still catch. A purpose-built module
# that runs every branch of its subject and asserts only `is not None` measures
# **30%** (the throwaway subject in tests/unit/test_mutation_smoke.py), and one
# that asserts nothing at all has no subject and is red whatever this number is.
# So 50% sits 20 points above the shape it exists to stop and 12 below the
# weakest thing it must not stop.
FLOOR: Final = 0.50

# How many kills a module may lose to its own recorded rate before the ratchet
# reds. The sample is seeded, the subject is pinned, every Python subprocess
# shares one hash seed, and selection membership no longer takes a clock-derived
# cumulative cut (#435) — but "no jitter" was a premise the instrument did not
# satisfy, so what still reads the clock is named rather than assumed away.
# Three places a measured duration still reaches a verdict: a test whose
# duration straddles the per-test ceiling leaves the selection of every line it
# reached, since the ceiling filters on the test's cost and not on the line's; a
# line every one of whose tests is over the ceiling falls back to its single
# cheapest, which a jittering duration can pick differently, and that fallback
# runs per line; and a timeout scored under machine load can award a kill to a
# survivor, load being a condition of the whole run rather than of one mutant.
# None of the three is bounded to a single kill and nothing stops them firing
# together, so no bound on how many kills they can move between them has been
# derived. This is one: a pragmatic tolerance sized to what the measured jitter
# (#435) actually produced — a single flip at a time — because a tolerance wide
# enough to absorb every combination would absorb a real two-kill weakening too.
# Two lost kills is the weakening the ratchet names.
SLACK: Final = 1

# The kill rate a module on the **shell** arm must reach, and its own number
# rather than `FLOOR` because it is a different mutator over a different corpus
# (#246). Set the way `FLOOR` was: every measurable shell-subject module was
# swept before anything was enforced, and this sits below the weakest of them.
#
# Measured, 2026-08-09, in `docs/research/mutation-shell-arm.md` §3:
# `test_host_seam` 100%, `test_host_guard` / `test_play_install` /
# `test_regress_selection` 80%, and `test_bringup_guards` and `test_run_verdict`
# 30% each — both of those on `spike/run.sh`, whose 1,278 lines mean any module
# testing one of its behaviours walks a great deal it never claims anything
# about. The weakest is therefore 3/10.
#
# The other end is what it must still catch. The throwaway module in
# `tests/unit/test_mutation_shell.py` that runs every branch of its subject and
# asserts only that something came back measures **0%**, and one that asserts
# nothing at all has no subject and is red whatever this number is. So 20% sits
# twenty points above the shape it exists to stop and one kill below the weakest
# thing it must not stop — the same one-kill margin `SLACK` gives the ratchet,
# and the same shape `FLOOR` has (50%, against a 30% weak fixture and a 62%
# weakest module).
SHELL_FLOOR: Final = 0.20

# Mutants planted per shell-subject module. Lower than `CAP` on purpose: a shell
# test costs a subprocess and a script bring-up rather than a function call, so
# the same twenty mutants buy the same claim at several times the wall clock.
SHELL_CAP: Final = 10

# What one shell-subject module's mutants may cost between them. Larger than
# `BUDGET_S` because the unit is larger: the cheapest test that reaches a line of
# `spike/run.sh` still boots a script, where the cheapest test reaching a line of
# `src/cti_daemon/daemon.py` is a function call. It is deliberately above what
# the measured worst module spends, so the **cap** decides how many mutants run
# and the clock does not: a denominator that moved with machine load would
# release the per-module ratchet at random (#244 keys a row on `run`).
SHELL_BUDGET_S: Final = 150.0

# ...and what one shell mutant's test selection may cost. Tighter than
# `TEST_SECONDS_PER_MUTANT` because a shell test is seconds rather than
# milliseconds: at 8 s the selection took five tests of
# `tests/unit/test_run_verdict.py` per mutant and the module cost 257 s, which is
# ADR-0064 decision 3's ceiling on its own. `-x` means only *survivors* pay this
# in full, so it bounds the bad case rather than the common one.
SHELL_TEST_SECONDS_PER_MUTANT: Final = 5.0

# Whether a shell mutant may be planted on a line every one of the module's
# tests walked. **False**, measured both ways over the whole shell corpus before
# it was set: narrowing raised three modules a little and destroyed two, taking
# `tests/unit/test_bringup_guards.py` from twelve mutants to four — a weaker
# claim at the same rate — and `tests/unit/test_host_seam.py` from 42% to 8%.
# ADR-0064 records the identical refinement measured and disproved for the Python
# arm; this is that finding re-derived rather than inherited, and it lands the
# same way. The switch stays so the next person can re-measure rather than
# re-argue (`--shell-all-lines` inverts it).
SHELL_DISCRIMINATING: Final = False

# A module's smoke gives up after this long. The size is a survey measurement,
# written down in `docs/research/mutation-testing.md` §7: the dearest loop this
# arm runs is this gate's own module at 60-75 s of mutants (bisected with
# `--budget`, #435 round 2; the next module, `tests/unit/test_dispatch_review.py`,
# spends 71 s end to end including its collect), so 180 sits at 2.4× the worst
# measured loop — deliberately above it, so the **cap** decides how many mutants
# run and the clock does not: a denominator that moved with machine load would
# release the per-module ratchet at random (#244 keys a row on `run`).
#
# When the clock wins anyway — a box loaded past that margin — the run refuses
# rather than reporting a rate on the denominator the clock chose, which is
# never a pass by default; a module that reached no verdict at all is a red.
BUDGET_S: Final = 180.0

# The coverage pass has its own bound, because it is the test module's own cost
# rather than this gate's: `tests/unit/test_client_lock.py` carries a deliberate
# 60 s soak (#197 criterion 6) and one run of it is one run of it. Sharing a
# single budget between the two phases would red exactly the modules whose tests
# are slowest, which is a bound on the harness masquerading as a verdict.
COLLECT_S: Final = 600.0

# Tests to run per mutant, cheapest first. Deliberately generous: `-x` stops at
# the first red, so a line reached by half a suite of millisecond tests costs
# about what one of them costs, and leaving the killing test out of the selection
# is a false survivor the floor then has to be lowered to accommodate. This cap
# bounds membership, not cost — the cumulative bound on the whole sample is
# `BUDGET_S`, which refuses rather than truncating (#435 round 2).
TESTS_PER_MUTANT: Final = 200
# ...and the cost one test may carry and still be selected at all. A ceiling on
# the single test, not a cumulative wall clock for the selection: a cumulative
# cut reads the measured durations, which jitter far more than `COST_GRAIN`
# removes, and it cut inside that jitter — on `tests/unit/test_dispatch_review.py`
# two fresh measurements of the same tree selected different tests for 532 of
# 874 covered lines, and one kill moved with them about one run in six (#435).
# Membership is what a verdict is a function of (under `-x` a red anywhere is a
# kill, wherever it sits in the order), so membership must not read the clock:
# every reaching test at or under the ceiling runs, and only a line reached by
# nothing cheaper falls back to its single cheapest test. The ceiling still
# keeps the 60 s soak out while a 0.01 s test reaches the same line. Its
# headroom over the corpus is not uniform and is not claimed as "far": the
# dearest test of `tests/unit/test_dispatch_review.py` costs 0.690 s, but this
# gate's own module's dearest costs 6.28 s — 22% below the ceiling, with two
# of its tests in the 6-10 s band (measured, round-2 review of #435) — so a
# duration there does not have to jitter far to flip membership, which is the
# boundary case `SLACK` names.
TEST_SECONDS_PER_MUTANT: Final = 8.0
# The grain durations are rounded to before anything is ordered or summed by
# them. Coarser than the run-to-run jitter of a millisecond test, finer than the
# difference between a test worth waiting for and one that is not.
COST_GRAIN: Final = 0.1

# How long one mutant's tests get before the run is abandoned. A mutant that
# makes the subject loop forever is detected only this way, so a timeout counts
# as a kill — it is the tests noticing, slowly. Derived from what the same tests
# cost unmutated, so it never bounds an honestly slow test out of a verdict.
# The one verdict that still reads the wall clock rather than the tree (#435):
# a box loaded enough to overrun the bound awards this kill to a survivor, in
# the generous direction, and `SLACK` is the stated tolerance for exactly that.
TIMEOUT_FLOOR_S: Final = 20.0
TIMEOUT_FACTOR: Final = 4.0

# `0.12s call tests/unit/test_x.py::test_y` — three fields, and a line with any
# other shape is not one of pytest's duration rows.
DURATION_FIELDS: Final = 3

# The one hash seed every Python subprocess this gate spawns runs under (#435).
# Not for this gate's own arithmetic — it sorts, or keys on names — but for the
# code under judgement: a subject whose behaviour depends on set or dict
# iteration order is a coin toss across the twenty mutant runs when each
# subprocess picks its own seed, and a coin toss is not a verdict. Measured on
# `tests/unit/test_dispatch_review.py` the flip traced to test selection rather
# than hash order, so this pin is not the whole of #435's fix — it is the half
# that costs one line and removes a whole class of coin toss the measurement
# could not have ruled out on another module.
HASH_SEED: Final = "0"


def _env() -> dict[str, str]:
    """Return the environment every spawned judge runs under: the caller's, seed pinned.

    The gate-clock collection export is dropped: a judge's pytest run of one
    module is not a suite collection, and inside `just fast` it would overwrite
    the suite count the unit leg wrote, handing the fast row the last module's
    count instead (#446). The failed-test export goes with it (#576): a judge
    kills mutants by failing tests, so leaving it would write every kill's node
    id into the mutation leg's evidence file as if the suite had failed them.
    """
    dropped = ("CTI_GATE_CLOCK_COLLECTED_FILE", "CTI_GATE_CLOCK_FAILED_FILE")
    env = {key: value for key, value in os.environ.items() if key not in dropped}
    return {**env, "PYTHONHASHSEED": HASH_SEED}


# The test modules no arm of this gate can measure, each with the reason.
#
# This list is the escape, and it is deliberately the *only* one: there is no
# flag, no marker in a test file and no environment variable, so a module that
# tests nothing can be excused only by a line here, in the diff, with its reason
# next to it. `grep -n '"tests/' tools/mutation_smoke.py` answers "which modules
# claim to have no measurable subject" completely. Adding a row is a reviewable
# act; lowering `FLOOR` is not an alternative to it.
#
# It was eleven rows and is four (#246). The eight that named a `spike/*.sh`
# subject now have one: `tools/mutation_shell.py` mutates the scripts a module
# drives, so "its subject is shell" stopped being a reason not to measure it. The
# rows that remain are of three kinds, and only the third is a judgement.
#
# ## Why there is no SQF arm, and what stands in its place
#
# Written here rather than left to be rediscovered, because the question comes
# back every time somebody reads this list (#246). It is not that SQF is hard to
# mutate — the mutator would be about as difficult as the bash one above it. It
# is that there is nowhere to run a mutant.
#
# * **No in-process runner.** SQF executes inside the Arma engine and nowhere
#   else. There is no SQF-VM in this project's gates (docs/research/
#   arma-toolchain.md ruled it optional), so a mutant's only verdict comes from
#   a world: `just regress`, which is a pool of slots, a server install and an
#   engine profile per probe.
# * **The arithmetic that closes it.** The corpus is about 20 minutes end to end
#   on three slots, and a mutant is a fresh world per probe rather than a
#   process. A twenty-mutant sample against one addon function is therefore
#   measured in hours per module, on a machine the human also plays on and which
#   the tier already holds single-occupancy. Nothing about the sample size
#   rescues that: even one mutant per landing is the whole corpus again.
# * **`compileFinal` closes the cheaper route.** The Functions Library
#   `compileFinal`s every `cti_fnc_`, so a probe cannot stub one and a mutant
#   cannot be swapped in at runtime — it would have to be planted in the addon
#   source and the PBO rebuilt, which puts a `hemtt build` inside the per-mutant
#   loop as well (#80 records the same constraint from the other side).
#
# So the non-goal is economic, and it is deliberate rather than deferred. What
# stands in its place is not nothing:
#
# * **The red-by-design probes** (#80, #96, #102): `schema-stale`, `daemon-restart`
#   and `loop-watch` each *demand* the failure class they expect, which is a probe
#   asserting that the harness still notices a break rather than hoping it would.
# * **The expected-class machinery** in the failure-class table: a probe that
#   names its class fails when the class it receives is a different one, so a
#   silently-changed decision surfaces as the wrong class rather than as a pass.
# * **The probe vacuity rule** (#116, ADR-0016): a probe asserts that its staging
#   took effect, because the world can refuse it silently — which is the same
#   property mutation testing buys, obtained by construction instead of by
#   sampling.
#
# **What would overturn this.** An in-process SQF runner this project is willing
# to gate on — SQF-VM reaching the point where a `cti_fnc_` runs under it with the
# addon's own arrangement — would make a mutant cost milliseconds instead of a
# world, and the arithmetic above would simply stop applying. That is the
# evidence to bring; "we should mutate SQF too" is not.
# The shell script a module drives, where neither its name nor the evidence
# reaches it. ADR-0064 decision 2's own escape hatch, taken for the first time:
# "a sound test module whose subject the rule picks so badly that its mutants are
# unkillable by design — the fix would then be per-module subject declaration,
# not a lower floor."
#
# It is a tie-break and not a nomination. The declared script must be one the
# module's tests actually executed, exactly as the naming convention "can never
# point at code nothing ran"; a row naming a script the tests never touched is a
# refusal, not a subject. So this cannot be used to point the gate at something
# inert, and like every other list here it is one line in the diff with its
# reason beside it.
SHELL_SUBJECT: Final[dict[str, str]] = {
    "tests/unit/test_host_seam.py": (
        # spike/hosts.sh, and the name misses it by a plural: the module is
        # `test_host_seam` and the script is `hosts.sh`. The evidence rule then
        # picked spike/regress.sh — reached because the seam's callers live
        # there — and scored the module 42% against a script it is not about.
        "spike/hosts.sh"
    ),
}

# The modules this landing may introduce without a test module naming them, each
# with the reason.
#
# `NO_MUTABLE_SUBJECT`'s sibling on the other side of the selection (#370). That
# list excuses a test module with no measurable subject; this one excuses a
# product module with no test module at all — the gap that list could not see,
# because a landing that adds `tools/x.py` and no `tests/unit/test_x.py` puts
# nothing in scope, so no verdict is reached, no floor is applied and every rung
# of `just fast` stays green. Three instances in one cycle before it was closed:
# #324 (`tools/generate_seats.py`, landed unmeasured and surfaced only by an
# unrelated harness defect), #338 and #346.
#
# Same shape and the same reviewability as every other escape here — one line in
# the diff with its reason beside it, no flag, no marker in the file, no
# environment variable. Ships empty: the rule is enforced from its first landing
# and no module in this tree claims it.
#
# The reason is load-bearing on both this list and `NO_MUTABLE_SUBJECT`: an entry
# whose reason is empty or whitespace is refused by name (`escape_problems`)
# rather than honoured, because entering an escape is meant to cost an argument.
NO_TEST_MODULE: Final[dict[str, str]] = {}

NO_MUTABLE_SUBJECT: Final[dict[str, str]] = {
    # --- reads a document rather than executing anything ---
    "tests/unit/test_daemon_gone_latch.py": (
        "its subject is the SQF latch in addons/main/functions/fn_daemonCall.sqf (#72), "
        "read as a document; SQF has no mutation arm and the reasoning is above; the "
        "in-world path it guards is exercised by spike/probes/daemon-restart.sqf, owed "
        "the full corpus at landing"
    ),
    "tests/unit/test_controller_policy_purity.py": (
        "its subject is the AST import policy in tools/controller_policy.py, read as a "
        "document rather than executing product code; controller policy behaviour is "
        "covered by tests/unit/test_controller_policy.py"
    ),
    "tests/unit/test_playtest_observer_staging.py": (
        "it reads spike/run.sh and the probe headers as documents (#178) rather than "
        "running either, so no arm of this gate has a line of it to plant on"
    ),
    "tests/unit/test_probe_headers.py": (
        "its subject is the probe corpus's headers in spike/probes/*.sqf (#23, ADR-0016), "
        "read as documents; SQF has no mutation arm and the reasoning is above"
    ),
    "tests/unit/test_report_schema.py": (
        "its subject is the agreement between cti_daemon.report.SHAPES and the SQF "
        "samplers (#74): it reads both as documents rather than executing either"
    ),
    "tests/unit/test_pool_slots.py": (
        "cost, not shape: its subject is the slot pool in spike/regress.sh (#47, "
        "ADR-0028) and the shell arm measures it — 40%, 4/10 sampled, measured twice "
        "at #457 — but one serial run of the module was 199.33 s at the same re-measure, "
        "of which #457's conversion pass could remove only 6 s (two 3 s no-respawn "
        "confirms, cut to 1 s each; the paired sampled runs moved 325.8 s to 317.0 s at "
        "an unchanged 4/10). With the shell arm's own 150 s mutant budget on top, a "
        "landing that touches this module spends ADR-0064 decision 3's five-minute "
        "ceiling on `just fast`. Re-measure and remove this row if the module or its "
        "subject get materially cheaper, or gate it somewhere other than `just fast`"
    ),
}


def _format_paths(paths: tuple[str, ...]) -> str:
    """Render a source-root tuple without keeping a second copy of its values."""
    return ", ".join(f"`{path}`" for path in paths) or "(none)"


def _format_rate(rate: float) -> str:
    """Render the stored rate and its reader-facing percentage from one value."""
    return f"{rate:g} ({rate:.0%})"


def _format_seconds(seconds: float) -> str:
    """Render a seconds value without rounding the policy source first."""
    return f"{seconds:g}s"


def _append_reasoned_entries(lines: list[str], name: str, entries: dict[str, str]) -> None:
    """Append a named escape map, including the reason stored beside each entry."""
    lines.append(f"  `{name}`:")
    if not entries:
        lines.append("    (none)")
        return
    lines.extend(f"    {path} — {reason}" for path, reason in entries.items())


# Gate-level output classes. Keep exact output and meaning beside the code that emits them;
# `render_contract()` is the reader-facing export used by documents and briefings.
MUTATION_CLASSIFICATIONS: Final[dict[str, tuple[str, str]]] = {
    "sampled": (
        "mutation smoke: run was sampled",
        "fewer than every planted candidate reached a verdict",
    ),
    "exhaustive": (
        "mutation smoke: run was exhaustive",
        "every planted candidate reached a verdict",
    ),
    "no-target": (
        "mutation smoke: nothing added or changed against {base}",
        "no mutation target was selected for this diff",
    ),
}


def render_contract() -> str:
    """Render the mutation-smoke policy from the constants that enforce it."""
    lines = [
        "just mutation --rules — the mutation-smoke contract",
        "",
        "Derived from tools/mutation_smoke.py and the mutation arms it invokes.",
        "The values below are read from the enforcing constants; this output has",
        "no separately maintained policy figures. The command only reads and",
        "renders: it does not run the smoke, gate a landing, or write anything.",
        "",
        "=== Run classifications (derived) ===",
        *(
            f"  `{name}`: `{output.format(base='<base>')}` — {meaning}"
            for name, (output, meaning) in MUTATION_CLASSIFICATIONS.items()
        ),
        "  A completed gate run with valid selection emits exactly one classification.",
        "  Missing classification is not `no-target`; it means the run was skipped,",
        "  refused, or failed to classify.",
        "",
        "=== Mutable source roots (derived) ===",
        f"  Python  `PRODUCT_ROOTS`: {_format_paths(PRODUCT_ROOTS)}",
        f"  Shell   `SHELL_ROOTS` (mutation_shell): {_format_paths(mutation_shell.SHELL_ROOTS)}",
        f"  Rust    `SCOPE` (mutation_rust): `{mutation_rust.SCOPE}`",
        "",
        "=== Python arm (derived) ===",
        f"  mutants per test module  `CAP`: {CAP}",
        f"  kill-rate floor          `FLOOR`: {_format_rate(FLOOR)}",
        f"  module budget            `BUDGET_S`: {_format_seconds(BUDGET_S)}",
        f"  collection budget        `COLLECT_S`: {_format_seconds(COLLECT_S)}",
        f"  tests selected per mutant `TESTS_PER_MUTANT`: {TESTS_PER_MUTANT}",
        (
            "  test-selection ceiling   `TEST_SECONDS_PER_MUTANT`: "
            f"{_format_seconds(TEST_SECONDS_PER_MUTANT)}"
        ),
        f"  duration rounding        `COST_GRAIN`: {_format_seconds(COST_GRAIN)}",
        f"  timeout minimum           `TIMEOUT_FLOOR_S`: {_format_seconds(TIMEOUT_FLOOR_S)}",
        f"  timeout multiplier        `TIMEOUT_FACTOR`: {TIMEOUT_FACTOR:g}",
        "",
        "=== Shell arm (derived) ===",
        f"  mutants per shell module `SHELL_CAP`: {SHELL_CAP}",
        f"  kill-rate floor          `SHELL_FLOOR`: {_format_rate(SHELL_FLOOR)}",
        f"  module budget            `SHELL_BUDGET_S`: {_format_seconds(SHELL_BUDGET_S)}",
        (
            "  test-selection ceiling   `SHELL_TEST_SECONDS_PER_MUTANT`: "
            f"{_format_seconds(SHELL_TEST_SECONDS_PER_MUTANT)}"
        ),
        f"  discriminating lines     `SHELL_DISCRIMINATING`: {SHELL_DISCRIMINATING}",
        "",
        "=== Rust arm (derived) ===",
        f"  manifest                 `MANIFEST` (mutation_rust): `{mutation_rust.MANIFEST}`",
        f"  engine version           `VERSION` (mutation_rust): `{mutation_rust.VERSION}`",
        f"  parallel jobs            `JOBS` (mutation_rust): {mutation_rust.JOBS}",
        (
            "  rung budget              `BUDGET_S` (mutation_rust): "
            f"{_format_seconds(mutation_rust.BUDGET_S)}"
        ),
        "",
        "=== Ratchet and determinism (derived) ===",
        f"  baseline                 `BASELINE`: `{BASELINE}`",
        f"  allowed recorded loss   `SLACK`: {SLACK} kill(s)",
        f"  subprocess hash seed    `HASH_SEED`: `{HASH_SEED}` (`PYTHONHASHSEED`)",
        "  sample seed              `sample(..., seed=test_module)`: the test-module path",
        "",
        "=== Subject declarations and exemptions (derived) ===",
        "  `SHELL_SUBJECT` declarations (test module → shell subject):",
    ]
    if SHELL_SUBJECT:
        lines.extend(f"    {module} → {subject}" for module, subject in SHELL_SUBJECT.items())
    else:
        lines.append("    (none)")
    _append_reasoned_entries(lines, "NO_MUTABLE_SUBJECT", NO_MUTABLE_SUBJECT)
    _append_reasoned_entries(lines, "NO_TEST_MODULE", NO_TEST_MODULE)
    lines.extend(
        [
            "  Rust survivor exemptions (`SURVIVES_BY_DESIGN`, from `mutation_rust`):",
        ]
    )
    if mutation_rust.SURVIVES_BY_DESIGN:
        lines.extend(
            f"    {mutant} — {reason}"
            for mutant, reason in mutation_rust.SURVIVES_BY_DESIGN.items()
        )
    else:
        lines.append("    (none)")
    lines.extend(
        [
            "",
            "=== Narration (not additional policy) ===",
            "  Narration: `TIMEOUT_FLOOR_S` is a per-mutant timeout bound, not a third",
            "  kill-rate floor. A mutant that times out counts as killed, not as a survivor.",
            "  Narration: the ratchet holds a matching recorded module rate, less `SLACK`",
            "  kills; a changed subject or sample releases it to the arm's shared floor.",
            "  Narration: no flag in `just fast` lowers either kill-rate floor; a red calls",
            "  for stronger tests or an explicitly reviewed policy change.",
            "",
            "=== Failure-class reference ===",
            '  See CLAUDE.md\'s "Failure classes" table for class semantics; this contract',
            "  restates none of them.",
            "",
        ]
    )
    return "\n".join(lines)


# Negating a comparison: the strongest single change to a decision that was
# taken, and the one a suite which asserts nothing at all fails to notice.
_FLIP: Final = {
    ast.Eq: "!=",
    ast.NotEq: "==",
    ast.Lt: ">=",
    ast.GtE: "<",
    ast.Gt: "<=",
    ast.LtE: ">",
    ast.Is: "is not",
    ast.IsNot: "is",
    ast.In: "not in",
    ast.NotIn: "in",
}

# Shifting a comparison by one: `>` still points the same way, the boundary moves.
# A negated `>` usually blows the code up somewhere and any red suite kills it,
# so negation alone measures "does anything go red"; this measures whether the
# tests pinned the *edge*, which is what a suite of `assert x is not None`
# reaches over. Only the four ordering operators have such a neighbour — there is
# nothing one step from `==` or from `is`.
_SHIFT: Final = {
    ast.Lt: "<=",
    ast.LtE: "<",
    ast.Gt: ">=",
    ast.GtE: ">",
}


class Mutant(NamedTuple):
    """One planted change: where it goes, what it replaces, and what with."""

    path: str
    line: int
    operator: str
    start: int
    end: int
    before: str
    after: str

    def __str__(self) -> str:
        """Render as an editor-clickable location and the edit itself."""
        return f"{self.path}:{self.line}: {self.operator}: {self.before} -> {self.after}"


def _line_starts(text: str) -> list[int]:
    """Byte offset of each line's first character.

    `ast` reports columns in UTF-8 bytes, so spans are computed in bytes and the
    slice is decoded back. A source with a non-ASCII character before a mutation
    site would otherwise be cut in the wrong place.
    """
    starts = [0]
    for line in text.encode("utf-8").splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _span(node: ast.AST, starts: list[int]) -> tuple[int, int] | None:
    """Byte span of a node, or None when the node carries no position."""
    line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", None)
    col = getattr(node, "col_offset", None)
    end_col = getattr(node, "end_col_offset", None)
    if line is None or end_line is None or col is None or end_col is None:
        return None
    if end_line >= len(starts):
        return None
    return starts[line - 1] + col, starts[end_line - 1] + end_col


def _segment(raw: bytes, span: tuple[int, int]) -> str:
    """Return the source text a span covers."""
    return raw[span[0] : span[1]].decode("utf-8")


def _frozen(tree: ast.AST) -> set[int]:
    """Return the ids of nodes this mutator deliberately leaves alone.

    Keyword-argument values and parameter defaults, because that is where opaque
    configuration lives — `blake2b(..., digest_size=16)` is the mutant mutmut
    planted on `dedupe.py` that no test could ever kill, and every such literal
    that survives here would have to be paid for by lowering the floor.

    Everything inside an f-string, because a replacement there would be grafted
    into a format expression whose reported span this mutator has no business
    trusting; the `graft` compile check would drop most of them anyway, and a
    dropped mutant is budget spent on nothing.
    """
    frozen: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            frozen.add(id(node.value))
        elif isinstance(node, ast.arguments):
            for default in [*node.defaults, *node.kw_defaults]:
                if default is not None:
                    frozen.add(id(default))
        elif isinstance(node, ast.JoinedStr):
            frozen.update(id(child) for child in ast.walk(node))
    return frozen


@dataclass
class _Planter:
    """Walks one file's tree and collects the mutants its covered lines allow."""

    path: str
    raw: bytes
    starts: list[int]
    lines: frozenset[int]
    frozen: set[int]
    found: list[Mutant] = field(default_factory=list)

    def _add(self, node: ast.AST, operator: str, after: str) -> None:
        span = _span(node, self.starts)
        line = getattr(node, "lineno", 0)
        if span is None or line not in self.lines or id(node) in self.frozen:
            return
        self.found.append(
            Mutant(self.path, line, operator, span[0], span[1], _segment(self.raw, span), after),
        )

    def _text(self, node: ast.AST) -> str | None:
        span = _span(node, self.starts)
        return None if span is None else _segment(self.raw, span)

    def visit(self, node: ast.AST) -> None:
        """Collect every mutant this node offers."""
        if isinstance(node, ast.Compare):
            self._compare(node)
        elif isinstance(node, ast.BoolOp):
            self._boolop(node)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            self._negation(node)
        elif isinstance(node, ast.Constant):
            self._constant(node)
        elif isinstance(node, ast.Return):
            self._return(node)

    def _compare(self, node: ast.Compare) -> None:
        # Chained comparisons (`a < b < c`) are left alone: rewriting one link of
        # a chain is a mutant whose meaning is hard to state in a report.
        if len(node.ops) != 1:
            return
        left, right = self._text(node.left), self._text(node.comparators[0])
        if left is None or right is None:
            return
        for operator, table in (("compare", _FLIP), ("boundary", _SHIFT)):
            symbol = table.get(type(node.ops[0]))
            if symbol is not None:
                self._add(node, operator, f"({left} {symbol} {right})")

    def _boolop(self, node: ast.BoolOp) -> None:
        symbol = "or" if isinstance(node.op, ast.And) else "and"
        parts = [self._text(value) for value in node.values]
        if any(part is None for part in parts):
            return
        self._add(node, "boolop", "(" + f" {symbol} ".join(part or "" for part in parts) + ")")

    def _negation(self, node: ast.UnaryOp) -> None:
        operand = self._text(node.operand)
        if operand is not None:
            self._add(node, "not", f"({operand})")

    def _constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, bool):
            self._add(node, "bool", "False" if node.value else "True")
        elif isinstance(node.value, int | float) and not isinstance(node.value, complex):
            self._add(node, "number", repr(node.value + 1))

    def _return(self, node: ast.Return) -> None:
        # `return None` is what a mutated function hands back; a function that
        # already returns nothing has no mutant here.
        if node.value is None or (
            isinstance(node.value, ast.Constant) and node.value.value is None
        ):
            return
        self._add(node.value, "return", "None")


def plant(source: str, *, path: str, lines: frozenset[int]) -> list[Mutant]:
    """Every mutant this mutator will plant in `source`, on the given lines.

    Deterministic and pure: the same file and the same covered lines give the
    same list in the same order, which is what makes the sample below repeatable.
    The verdict's other input, the test selection, is deterministic only up to
    the boundary `cheapest` states (#435) — purity here pins the sample, not
    the whole gate.
    """
    tree = ast.parse(source)
    planter = _Planter(
        path=path,
        raw=source.encode("utf-8"),
        starts=_line_starts(source),
        lines=lines,
        frozen=_frozen(tree),
    )
    for node in ast.walk(tree):
        planter.visit(node)
    planter.found.sort(key=lambda mutant: (mutant.line, mutant.start, mutant.operator))
    return planter.found


def apply_edit(source: str, mutant: Mutant) -> str:
    """`source` with `mutant`'s byte span replaced, unchecked."""
    raw = source.encode("utf-8")
    return (raw[: mutant.start] + mutant.after.encode("utf-8") + raw[mutant.end :]).decode("utf-8")


def graft(source: str, mutant: Mutant) -> str | None:
    """`source` with `mutant` applied, or None when the result will not compile.

    The compile check is the cheap guard that makes textual grafting safe: any
    span this mutator misreads produces a `SyntaxError` here and the mutant is
    dropped, rather than reaching the tests as a red that means nothing.
    """
    grafted = apply_edit(source, mutant)
    try:
        compile(grafted, mutant.path, "exec")
    except SyntaxError:
        return None
    return grafted


def graft_shell(source: str, mutant: Mutant) -> str | None:
    """Do the same for a shell subject, with `bash -n` standing in for `compile`."""
    grafted = apply_edit(source, mutant)
    return grafted if mutation_shell.parses(grafted) else None


def sample(mutants: list[Mutant], *, seed: str, cap: int) -> list[Mutant]:
    """Choose a bounded, reproducible sample of `mutants`.

    Seeded from the test module's path, so the same tree always plants the same
    mutants — a gate that picked afresh each run would be a coin toss dressed as
    a verdict, and CLAUDE.md's flake rules would be right to call it one.
    """
    if len(mutants) <= cap:
        return list(mutants)
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    chosen = random.Random(int.from_bytes(digest, "big")).sample(range(len(mutants)), cap)  # noqa: S311 — reproducible sampling, not cryptography
    return [mutants[index] for index in sorted(chosen)]


def _stems(test_module: str) -> list[str]:
    """List the module names `test_module` might be named after, longest first.

    `test_budget.py` names one thing and `test_daemon_casualties.py` names two —
    the module and the part of it under test — and this repo writes the second
    shape a dozen times: `test_daemon_dispatch`, `test_daemon_epoch`,
    `test_daemon_victory`, all about `src/cti_daemon/daemon.py`. Dropping one
    trailing `_word` at a time finds the file the author meant, and the caller
    takes the first that the tests actually reached, so a shortened stem can
    never name code nothing ran.
    """
    parts = Path(test_module).stem.removeprefix("test_").split("_")
    return ["_".join(parts[: len(parts) - dropped]) for dropped in range(len(parts))]


def _stem_key(path: str) -> str:
    """Spell a file's stem the way a test module's name would have to spell it.

    `spike/host-guard.sh` is what `tests/unit/test_host_guard.py` is named after,
    and no Python module name can carry that hyphen. Nothing under `src/` or
    `tools/` spells a `.py` stem with one, so this only ever changes the shell
    arm's answer — the Python arm sees the same stems it always did.
    """
    return Path(path).stem.replace("-", "_")


def node_id(test_module: str, context: str) -> str | None:
    """Turn one coverage context into the pytest node id that selects that test.

    They are not the same string and assuming they were is how the first draft of
    this gate scored every module 100%. `dynamic_context = test_function` names a
    test by its *importable* name — `test_dedupe.test_a_window_can_be_filled`, or
    `test_x.Suite.test_y` for a class — while pytest selects by path and `::`.
    Handed the coverage spelling, pytest exits 4 with "file or directory not
    found", and a runner that reads any non-zero exit as a kill reads that as the
    tests noticing. They noticed nothing; they never ran.

    Parametrised tests carry no case in the coverage name, so the node id here
    selects every case of them, which is the safe direction: more tests get their
    chance to kill the mutant, never fewer.

    None when the context is not a test of this module at all. `coverage`'s
    `test_function` context names *any* function called `test_function`, and
    `hypothesis.internal.conjecture.engine.ConjectureRunner.test_function` is one
    — so every module using `hypothesis` recorded a context that turns into a node
    id pytest cannot select, exits 4 on, and this gate then refuses over. Requiring
    the module's own name as the first part is exact: `dynamic_context` always
    writes `module.qualname`.
    """
    parts = [part for part in context.split(".") if part]
    stem = Path(test_module).stem
    if len(parts) < 2 or parts[0] != stem:  # noqa: PLR2004 — a module and a name is two parts
        return None
    return f"{test_module}::{'::'.join(parts[1:])}"


class Reach(NamedTuple):
    """Which product lines a test module executes, which tests reach each, at what cost."""

    lines: dict[str, dict[int, tuple[str, ...]]]
    costs: dict[str, float] = {}  # noqa: RUF012 — a NamedTuple field default, not shared mutable state

    def tests(self) -> frozenset[str]:
        """Every test of the module under smoke that reached any product line."""
        return frozenset(
            name for reached in self.lines.values() for names in reached.values() for name in names
        )

    def discrimination(self, path: str) -> float:
        """How much of `path` this module's tests tell apart rather than merely load.

        A line every test in the module executes is arrangement: `test_budget.py`
        reaches 94 lines of `manifest.py` and 88 of them from all four of its
        tests, because the shared arrangement in `tests/unit/conftest.py` loads a
        manifest before anything else happens. Counting lines alone made that the
        subject, and the module then scored 50% for not asserting about a file it
        never meant to test — a false red on a sound module, which is the one
        thing #137/#186 say a gate must not do.

        So each line is worth the share of the module's tests that did *not*
        reach it. A line one test in four touches is worth 0.75; a line all four
        touch is worth nothing at all.
        """
        total = len(self.tests())
        if not total:
            return 0.0
        return sum(1.0 - len(set(names)) / total for names in self.lines.get(path, {}).values())

    def share(self, path: str) -> float:
        """How much of this module's tests reached `path` at all.

        The shell arm's correction, and it exists because of a structure the
        Python corpus does not have: `spike/run.sh` sources `hosts.sh`,
        `client-lock.sh` and `play-install.sh`, and `tier-lock.sh` sources
        `slots.sh`, so one test that takes a lock executes a whole helper nobody
        was testing. Discrimination alone then *rewards* that helper for being
        incidental — measured, on `tests/unit/test_bringup_guards.py`:
        `spike/slots.sh` scored 33 against `spike/run.sh`'s 14 on one test out of
        seven, was chosen, and killed 0 of 12 mutants. Weighting by the share of
        the module's tests that reached the file at all puts `run.sh` back in
        front, and it is the file the module's name and its docstring both say it
        is about.
        """
        total = len(self.tests())
        if not total:
            return 0.0
        reached = {name for names in self.lines.get(path, {}).values() for name in names}
        return len(reached) / total

    def subject(self, test_module: str = "", *, weighted: bool = False) -> str | None:
        """Name the product file this test module is testing, or None.

        Two rules in order. First the name, because `test_budget.py` → `budget.py`
        is a statement of intent by the person who wrote the file and it is worth
        more than any inference — but only when the tests actually reach that
        file, so the convention can never point at code nothing executed. Then the
        evidence, scored as above, for the many modules whose subject the naming
        convention does not reach: `tests/unit/test_land.py` → `tools/land.py`,
        `tests/unit/test_daemon_casualties.py` → nothing of that name at all.

        None is a finding, not a shrug: a test module none of whose tests reach a
        line of this repo's source has asserted nothing about it.

        `weighted` is the shell arm's evidence rule and only its own: see
        `share`. The Python arm is left exactly as #239 measured it, because the
        corpus sweep that set `FLOOR` was taken under the unweighted rule and
        changing the rule under sixty modules would move rates a landing did not
        touch.
        """
        if not self.lines:
            return None
        for stem in _stems(test_module):
            named = [path for path in sorted(self.lines) if _stem_key(path) == stem]
            if named:
                return named[0]
        if weighted:
            return max(
                sorted(self.lines), key=lambda path: self.discrimination(path) * self.share(path)
            )
        return max(sorted(self.lines), key=self.discrimination)

    def cost(self, node: str) -> float:
        """Seconds one node id costs, rounded to `COST_GRAIN`, over all its cases.

        Rounded, and that is the whole point of this method rather than a dict
        lookup. Ordering the selection by raw measured durations made this gate
        **flake**: the same tree, the same mutants, 13/20 then 14/20, because
        a suite whose tests all cost about a millisecond reorders on jitter and
        a different set of them gets picked. The grain and the name tie-break
        coarsen that; they do not remove it — a second measured flake (#435)
        had 33 of 65 costs moving a grain or more between two runs — so the
        selection's *membership* no longer reads cost at all, only the ceiling,
        and cost orders the run and sizes the timeout.
        """
        exact = self.costs.get(node)
        if exact is None:
            exact = sum(spent for name, spent in self.costs.items() if name.startswith(f"{node}["))
        return round(exact / COST_GRAIN) * COST_GRAIN

    def cheapest(self, tests: tuple[str, ...], bound: float = TEST_SECONDS_PER_MUTANT) -> list[str]:
        """Choose the tests to run against one mutant: every one under the per-test ceiling.

        Membership is all that a verdict is a function of — under `-x` a red
        anywhere in the order is a kill, and an all-green run survives — so the
        order below changes only wall clock, and the membership must not read
        the clock: durations are measured afresh every run, they jitter past
        what `COST_GRAIN` quantises away, and the cumulative wall-clock bound
        this replaced cut inside that jitter and moved 532 of 874 lines'
        selections between two measurements of one unchanged module, taking a
        kill with it about one run in six (#435).

        So a reaching test is a member iff its rounded cost is at or under
        `bound`, capped at `TESTS_PER_MUTANT` in name order (a cap that bites
        past two hundred tests, where name order is the only order that cannot
        reorder on a measurement). A test whose duration was never recorded is
        assumed free rather than expensive, so an unmeasured test is still
        tried. A line every one of whose tests is over the ceiling keeps its
        single cheapest one — the gate still asks something about that line —
        and that fallback, plus a duration straddling the ceiling itself, are
        the two places left in the *selection* where a measurement can flip a
        verdict; the timeout is the third, and `SLACK`'s comment names all
        three. An empty reaching set selects nothing rather than raising, so
        `_tally`'s guard can still skip a mutant no test reaches.
        """
        if not tests:
            return []
        members = sorted(name for name in tests if self.cost(name) <= bound)[:TESTS_PER_MUTANT]
        if not members:
            members = [min(tests, key=lambda name: (self.cost(name), name))]
        return sorted(members, key=lambda name: (self.cost(name), name))

    def timeout(self, tests: list[str]) -> float:
        """How long those tests get before the mutant is called killed by timeout."""
        return max(TIMEOUT_FLOOR_S, TIMEOUT_FACTOR * sum(self.cost(name) for name in tests))


def _is_product(path: str) -> bool:
    """Whether a covered file is this repo's own source rather than a test or a dependency."""
    normalised = path.replace(os.sep, "/").removeprefix("./")
    return normalised.startswith(PRODUCT_ROOTS) and not normalised.startswith("tests/")


def read_durations(output: str) -> dict[str, float]:
    """Seconds per test id, from pytest's own `--durations=0` report.

    Read rather than measured: the coverage pass already runs every test once,
    and pytest already knows what each one cost. A line is `0.12s call
    tests/unit/test_x.py::test_y`; setup and teardown are summed in with the
    call, because a mutant run pays all three.
    """
    costs: dict[str, float] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != DURATION_FIELDS or not parts[0].endswith("s"):
            continue
        seconds, phase, name = parts
        if phase not in ("call", "setup", "teardown") or "::" not in name:
            continue
        try:
            costs[name] = costs.get(name, 0.0) + float(seconds.removesuffix("s"))
        except ValueError:
            continue
    return costs


def read_reach(report: dict[str, object], costs: dict[str, float] | None = None) -> Reach:
    """Turn a `coverage json --show-contexts` report into a `Reach`.

    Only lines carrying a non-empty context count. An empty context is
    import time — the module body ran because something imported it, not because
    a test exercised it — and counting those is exactly how an `assert True`
    module would acquire a subject it never touched.
    """
    lines: dict[str, dict[int, tuple[str, ...]]] = {}
    files = report.get("files")
    if not isinstance(files, dict):
        return Reach({}, costs or {})
    for path, entry in files.items():
        if not _is_product(str(path)) or not isinstance(entry, dict):
            continue
        contexts = entry.get("contexts")
        if not isinstance(contexts, dict):
            continue
        reached: dict[int, tuple[str, ...]] = {}
        for number, names in contexts.items():
            if not isinstance(names, list):
                continue
            tests = tuple(sorted(str(name).split("|")[0] for name in names if name))
            if tests:
                reached[int(str(number))] = tests
        if reached:
            lines[str(path).replace(os.sep, "/").removeprefix("./")] = reached
    return Reach(lines, costs or {})


class Verdict(NamedTuple):
    """What one test module's smoke found."""

    test_module: str
    subject: str | None
    planted: int
    run: int
    killed: int
    survivors: tuple[Mutant, ...]
    seconds: float
    floor: float
    ratcheted: bool = False
    # Which mutator measured it. A reader scanning the gate's output needs to
    # know that `killed=8/10` on a `spike/*.sh` subject is a different mutator
    # over a different corpus with a floor of its own (#246).
    arm: str = "python"
    sampled: bool = True

    @property
    def kill_rate(self) -> float:
        """Share of the mutants run that the tests noticed."""
        return 1.0 if self.run == 0 else self.killed / self.run

    @property
    def undecided(self) -> bool:
        """Whether the subject offered nothing to plant on the lines the tests reach.

        Not a pass by luck and not a failure either: `src/cti_daemon/telemetry.py`
        has no comparison, no boolean and no bare number on any line its tests
        execute, so there is no decision for a mutant to invert. A module cannot
        reach this state by writing weaker assertions — it is a property of the
        subject — so reding it would be a false red on a sound test module, which
        is the corpus sweep's one finding this rule exists for (#239).
        """
        return self.subject is not None and self.planted == 0

    @property
    def ok(self) -> bool:
        """Whether this module met the bar."""
        if self.subject is None:
            return False
        if self.undecided:
            return True
        return self.run > 0 and self.kill_rate >= self.floor

    @property
    def reason(self) -> str:
        """Why it failed, in the terms the remedy is written in."""
        if self.subject is None:
            return (
                "no subject: none of this module's tests executed a line of this repo's Python "
                "or of its shell, so there is nothing it can be said to have tested. If it reads "
                "an authored document rather than running anything, add it to NO_MUTABLE_SUBJECT "
                "with the reason"
            )
        if self.undecided:
            return f"nothing to plant: no decision on the lines reached in {self.subject}"
        if self.run == 0:
            return f"no mutant reached a verdict in {self.seconds:.0f}s against {self.subject}"
        return (
            f"kill rate {self.kill_rate:.0%} against {self.subject} "
            f"({self.killed}/{self.run}) is below the {self.floor:.0%} floor"
        )

    def __str__(self) -> str:
        """One line per module, the shape a gate's reader scans."""
        mark = "ok" if self.ok else "RED"
        if self.undecided:
            return f"ok {self.test_module} subject={self.subject} {self.reason} {self.seconds:.1f}s"
        where = self.subject or "-"
        floor = f"{self.floor:.0%}" + (" (ratchet)" if self.ratcheted else "")
        sampling = "sampled" if self.sampled else "exhaustive"
        return (
            f"{mark} {self.test_module} subject={where} arm={self.arm} "
            f"killed={self.killed}/{self.run} planted={self.planted} "
            f"rate={self.kill_rate:.0%} floor={floor} sampling={sampling} {self.seconds:.1f}s"
        )


class Refusal(Exception):  # noqa: N818 — the repo names this shape `Refusal` (tools/worktree.py), and a refusal is not an error
    """The smoke could not run, which is not the same as a module failing it."""


# Every write this gate makes to a subject gets its own modification time, and
# this counter is what makes them distinct.
#
# Not tidiness. CPython validates a cached `.pyc` against its source's **mtime in
# whole seconds and its size in bytes**, and the two mutants this gate plants on
# one comparison — the negation and the boundary shift — differ by no bytes at
# all: `(missing < 0)` and `(missing > 0)` are the same length, written to the
# same file inside the same second. So the second run imported the first one's
# bytecode and delivered a verdict on a mutant that never executed. That is this
# gate flaking 13/20, 13/20, 12/20 over an unchanged tree, and the two survivors
# that moved were exactly such a pair. Stepping the clock forward two seconds per
# write makes a stale hit impossible rather than unlikely, and unlike a private
# `PYTHONPYCACHEPREFIX` per mutant — which also fixes it — it does not make every
# run recompile the whole import graph, measured at 10 s to 38 s per module.
_written = 0


def _stamp(target: Path) -> None:
    """Give `target` a modification time no other write in this run shares."""
    global _written  # noqa: PLW0603 — one counter for the process, and its scope is the point
    _written += 1
    when = time.time() + 2 * _written
    os.utime(target, (when, when))


# pytest's own exit codes, and the only two a mutant's fate may be read from.
# Everything else — interrupted, internal error, usage error, nothing collected —
# is a run that did not happen, and CLAUDE.md's rule for those is the #41 one: a
# check that could not run is not a check that passed, and here it would be worse
# than that, because "non-zero means the tests noticed" reads a usage error as a
# kill. That is exactly what the first draft of this gate did, and it scored every
# module in the repo 100%.
PYTEST_PASSED: Final = 0
PYTEST_FAILED: Final = 1


@contextlib.contextmanager
def grafted(root: Path, path: str, text: str):  # noqa: ANN201 — a context manager's own type adds nothing here
    """Hold `path` at `text` for the body, and put the original back whatever happens.

    The sidecar is written before the file is, so an interrupted run leaves the
    original recoverable by hand; the signal handlers cover the two ways an agent
    harness ends a run that a `finally` does not.
    """
    target = root / path
    original = target.read_text(encoding="utf-8")
    sidecar = root / RESTORE
    sidecar.write_text(json.dumps({"path": path, "text": original}), encoding="utf-8")
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}

    def _restore(number: int, frame: object) -> None:  # noqa: ARG001 — signal handler signature
        target.write_text(original, encoding="utf-8")
        sidecar.unlink(missing_ok=True)
        raise KeyboardInterrupt

    for number in previous:
        with contextlib.suppress(ValueError):
            signal.signal(number, _restore)
    try:
        target.write_text(text, encoding="utf-8")
        _stamp(target)
        yield
    finally:
        target.write_text(original, encoding="utf-8")
        _stamp(target)
        sidecar.unlink(missing_ok=True)
        for number, handler in previous.items():
            with contextlib.suppress(ValueError, TypeError):
                signal.signal(number, handler)


def _collects(root: Path, test_module: str, *, timeout: float) -> bool | None:
    """Whether `test_module` imports and collects under the tree as it stands right now.

    Asked of a process whose only subject is that module: a `--collect-only` run
    of the bare path runs no tests, so it cannot quote captured output, and its
    exit code is about collecting `test_module` and nothing else — 0 when it
    collects, and non-zero for every way of not collecting (2 is an import
    error pytest reports at collection, and the suite pins that one and the
    node-id run's 4; a `conftest.py` that fails to import exits 4 and a module
    that collects nothing exits 5, and the question this answers does not care
    which). None when even this run did not finish, which is no answer at all.

    The answer is only ever asked under a mutant, and that is what makes every
    non-zero a kill downstream rather than an error read as a verdict: `measure`
    refused this module unless a bare-path run of it exited 0, so a conftest
    that cannot import, a usage error and an empty collection were all ruled
    out before any mutant was planted (#424 round 2). Whatever stopped the
    collect-only run now, the mutant caused.
    """
    try:
        done = subprocess.run(  # noqa: S603 — argv is built here from paths and constants
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-n0",
                "-p",
                "no:cacheprovider",
                "--no-header",
                test_module,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=_env(),
        )
    except subprocess.TimeoutExpired:
        return None
    return done.returncode == PYTEST_PASSED


def _pytest(
    root: Path,
    argv: list[str],
    *,
    timeout: float,
    test_module: str,
    mutant: bool = False,
) -> int | None:
    """Run pytest in `root` and return its exit code, or None if it did not finish.

    Score a mutant-caused collection error for `test_module` as a test failure,
    asked of collection itself rather than of the run's output. An exit outside
    {0, 1} is not a verdict — except one: a mutant that makes a module-level
    call of the subject raise turns the run into a collection error (#338), and
    that is the tests noticing in the strongest sense. With node ids on the
    command line that error exits 4, the same code as a bad-node-id usage
    error, and the output stream cannot tell them apart honestly: this repo
    runs pytest inside pytest, and the captured output of a failing test can
    quote a collection banner naming this very module from a run that is not
    this one (#424) — a token matched in a mixed stream, right for the wrong
    reason whenever it agrees. So the question goes to `_collects`, a process
    that can only answer it: the module does not collect under the mutant, or
    it does. A "collects" answer returns the odd exit code and `_tally` refuses
    loudly. A "does not collect" answer scores a kill — the generous direction,
    not the blind one — and what makes that safe is not this branch but
    `measure`'s green proof: the unmutated bare-path run exited 0, so any
    collection failure now was caused by the mutant (#424 round 2).
    """
    try:
        done = subprocess.run(  # noqa: S603 — argv is built here from paths and constants
            [sys.executable, "-m", "pytest", *argv],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=_env(),
        )
    except subprocess.TimeoutExpired:
        return None
    if (
        mutant
        and done.returncode not in (PYTEST_PASSED, PYTEST_FAILED)
        and _collects(root, test_module, timeout=timeout) is False
    ):
        return PYTEST_FAILED
    return done.returncode


class Collected(NamedTuple):
    """What one collect pass found, one `Reach` per arm.

    Both come out of the same run. The bash tracing costs nothing measurable —
    14.88 s against 14.75 s on `tests/unit/test_bringup_guards.py`, 190.80 s
    against 190.64 s on the slowest module in the corpus — so it is switched on
    for every module rather than only for the ones expected to need it, and a
    module that turns out to drive shell is already measured when it gets here.
    """

    python: Reach
    shell: Reach


def measure(root: Path, test_module: str, *, timeout: float) -> Collected:
    """Run one test module once, and report what its tests reached in Python and in bash."""
    with tempfile.TemporaryDirectory() as workspace:
        rcfile = Path(workspace) / "coveragerc"
        rcfile.write_text(
            "[run]\nbranch = false\ndynamic_context = test_function\n"
            "source =\n    " + "\n    ".join(PRODUCT_ROOTS) + "\n",
            encoding="utf-8",
        )
        data = Path(workspace) / "cov.db"
        report = Path(workspace) / "cov.json"
        tracing = mutation_shell.trace_environment(Path(workspace))
        environment = {**_env(), "COVERAGE_RCFILE": str(rcfile), **tracing}
        argv = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--data-file={data}",
            "-m",
            "pytest",
            "-n0",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            "cti_shell_trace",
            "--durations=0",
            "--durations-min=0",
            test_module,
        ]
        try:
            done = subprocess.run(  # noqa: S603 — argv built here from paths and constants
                argv,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as expired:
            message = f"{test_module} did not finish under coverage within {timeout:.0f}s"
            raise Refusal(message) from expired
        if done.returncode != 0:
            message = (
                f"{test_module} is not green on its own — mutation says nothing about a red "
                f"suite. pytest exit {done.returncode}:\n{done.stdout[-2000:]}"
            )
            raise Refusal(message)
        exported = subprocess.run(  # noqa: S603 — argv built here from paths and constants
            [
                sys.executable,
                "-m",
                "coverage",
                "json",
                f"--data-file={data}",
                "-o",
                str(report),
                "--show-contexts",
                "-q",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        if exported.returncode != 0 or not report.exists():
            message = f"coverage json failed for {test_module}: {exported.stderr.strip()}"
            raise Refusal(message)
        costs = read_durations(done.stdout)
        return Collected(
            read_reach(json.loads(report.read_text(encoding="utf-8")), costs),
            Reach(mutation_shell.read_traces(Path(workspace), root), costs),
        )


# A mutant the graft check dropped: no verdict, and not a run either. Distinct
# from `None`, which is a timeout and therefore a kill.
_DROPPED: Final = object()


class _Tally(NamedTuple):
    """What the mutants that reached a verdict came to."""

    run: int
    killed: int
    survivors: tuple[Mutant, ...]


def _tally(  # noqa: PLR0913 — the loop's inputs, and every one of them is a bound
    chosen: list[Mutant],
    reach: Reach,
    covered: dict[int, tuple[str, ...]],
    deadline: float,
    run_one: Callable[[Mutant, list[str]], object],
    *,
    bound: float = TEST_SECONDS_PER_MUTANT,
) -> _Tally:
    """Run each mutant against the tests that reach it, and count what the tests noticed.

    Shared by both arms, because the arithmetic of a kill is not what differs
    between them: only where the mutant is written and what checks its syntax.
    """
    killed = 0
    run = 0
    survivors: list[Mutant] = []
    for mutant in chosen:
        if time.monotonic() > deadline and run:
            # The clock moved the denominator once already (#435 round 2: `ok`,
            # 16/19, rate 84%, exit 0, ratchet released by `row.run != run`).
            # A sample the budget cut is not a result on a smaller denominator
            # — it is no result at all, which is a refusal.
            message = (
                f"the module budget ran out after {run} of {len(chosen)} chosen mutants "
                f"reached a verdict — a denominator the clock moved is not a rate. "
                f"Re-run on an idle box; a larger --budget is for a subject that "
                f"genuinely grew, never the remedy for a refusal"
            )
            raise Refusal(message)
        tests = reach.cheapest(covered[mutant.line], bound)
        if not tests:
            continue
        code = run_one(mutant, tests)
        if code is _DROPPED:
            continue
        run += 1
        # A timeout is a kill: the mutant changed what the code does so plainly
        # that the tests could not finish saying so. Every other non-zero code is
        # a run that did not happen, and reading it as a kill is how a gate scores
        # a vacuous suite full marks.
        if code is not None and code not in (PYTEST_PASSED, PYTEST_FAILED):
            message = (
                f"pytest exited {code} on {mutant} — that is not a verdict on the mutant. "
                f"The node ids it was given were: {tests}"
            )
            raise Refusal(message)
        if code == PYTEST_PASSED:
            survivors.append(mutant)
        else:
            killed += 1
    return _Tally(run, killed, tuple(survivors))


def _selected(reach: Reach, subject: str, test_module: str) -> dict[int, tuple[str, ...]]:
    """Which pytest node ids reached each line of the Python subject.

    A coverage context is not a node id, and the shell arm needs no equivalent of
    this at all — its plugin recorded the node id itself.
    """
    covered: dict[int, tuple[str, ...]] = {}
    for line, contexts in reach.lines[subject].items():
        nodes = tuple(
            node for node in (node_id(test_module, context) for context in contexts) if node
        )
        if nodes:
            covered[line] = nodes
    return covered


def _python_smoke(  # noqa: PLR0913 — every bound this gate applies is a caller-visible knob
    root: Path,
    test_module: str,
    reach: Reach,
    subject: str,
    *,
    cap: int,
    floor: float,
    budget: float,
    rows: dict[str, Row],
    started: float,
) -> Verdict:
    """Run the original arm: mutants in the real tree, under the restore sidecar."""
    covered = _selected(reach, subject, test_module)
    source = (root / subject).read_text(encoding="utf-8")
    planted = plant(source, path=subject, lines=frozenset(covered))
    chosen = sample(planted, seed=test_module, cap=cap)

    def run_one(mutant: Mutant, tests: list[str]) -> object:
        text = graft(source, mutant)
        if text is None:
            return _DROPPED
        with grafted(root, subject, text):
            return _pytest(
                root,
                ["-n0", "-q", "-x", "-p", "no:cacheprovider", "--no-header", *tests],
                timeout=reach.timeout(tests),
                # `measure` proved the unmutated module green. A collection error now is
                # mutant-caused and therefore a kill; bad node ids remain usage errors.
                mutant=True,
                test_module=test_module,
            )

    tally = _tally(chosen, reach, covered, time.monotonic() + budget, run_one)
    sampled = tally.run < len(planted)
    return _verdict_for(
        root,
        test_module,
        subject,
        len(planted),
        tally,
        floor=floor,
        rows=rows,
        started=started,
        arm="python",
        sampled=sampled,
    )


def _declared_shell_subject(reach: Reach, test_module: str) -> str | None:
    """Choose a module's shell subject: the declaration where there is one, else the evidence.

    A declaration naming a script the module's tests never executed is a refusal
    rather than a subject, which is what keeps `SHELL_SUBJECT` a tie-break and
    stops it being a way to point the gate at something inert.
    """
    declared = SHELL_SUBJECT.get(test_module)
    if declared is None:
        return reach.subject(test_module, weighted=True)
    if declared not in reach.lines:
        message = (
            f"SHELL_SUBJECT names {declared} for {test_module}, but none of its tests executed "
            f"a line of it. The declaration is a tie-break among the scripts the tests ran, "
            f"never a way to nominate one they did not"
        )
        raise Refusal(message)
    return declared


def _shell_lines(
    reach: Reach,
    subject: str,
    *,
    discriminating: bool,
) -> dict[int, tuple[str, ...]]:
    """Which lines of the shell subject a mutant may be planted on.

    `discriminating` drops the lines every test that reached the script executed:
    on a 1,278-line `spike/run.sh` those are the linear path each test walks on
    its way to the branch it is about — argument defaults, the cleanup trap, the
    client-lock arithmetic — and a module is not weak for failing to assert about
    ground it merely crossed.

    ADR-0064 records the same refinement measured and **disproved** for the Python
    arm, so it is re-derived here rather than inherited either way; the numbers
    for both settings are in `docs/research/mutation-shell-arm.md` §4.
    """
    lines = reach.lines[subject]
    if not discriminating:
        return dict(lines)
    reached = len({name for names in lines.values() for name in names})
    narrowed = {line: names for line, names in lines.items() if len(set(names)) < reached}
    # Never narrow to nothing: a script every one of its tests walks identically
    # still has decisions in it, and an empty plant would read as "nothing to
    # plant" — a pass — which is a strictly worse answer than the wide one.
    return narrowed or dict(lines)


def _shell_smoke(  # noqa: PLR0913 — every bound this gate applies is a caller-visible knob
    root: Path,
    test_module: str,
    reach: Reach,
    subject: str,
    *,
    cap: int,
    floor: float,
    budget: float,
    rows: dict[str, Row],
    started: float,
    discriminating: bool,
    bound: float = SHELL_TEST_SECONDS_PER_MUTANT,
) -> Verdict:
    """Run the shell arm: mutants in a hardlinked stage, never in `spike/` itself.

    The unmutated run inside the stage is not tidiness. Every mutant is judged by
    whether its tests went red, so a stage that broke them would score the module
    100% — a false green, and the exact defect #239 records as having scored every
    module in this repository full marks. It is bounded to the tests a mutant can
    select, which is the honest claim: every test this arm will run is green here
    before any of them is asked about a mutant.
    """
    covered = _shell_lines(reach, subject, discriminating=discriminating)
    source = (root / subject).read_text(encoding="utf-8")
    planted = [
        Mutant(subject, *edit) for edit in mutation_shell.plant(source, lines=frozenset(covered))
    ]
    chosen = sample(planted, seed=test_module, cap=cap)
    # Exactly the tests the mutant runs below will select, and nothing wider. The
    # union of every test that merely *reached* the script is most of the module
    # — 50 s of `tests/unit/test_run_verdict.py` — and running it would be paying
    # for a claim this arm does not make.
    arrangement = sorted(
        {test for mutant in chosen for test in reach.cheapest(covered[mutant.line], bound)},
    )

    with mutation_shell.staged(root) as stage:
        code = _pytest(
            stage,
            ["-n0", "-q", "-p", "no:cacheprovider", "--no-header", *arrangement],
            timeout=reach.timeout(arrangement),
            test_module=test_module,
        )
        if code != PYTEST_PASSED:
            message = (
                f"{test_module} is not green in the staged tree (pytest exit {code}), so no "
                f"mutant planted there would mean anything. The stage is a hardlinked copy of "
                f"every tracked and unignored file; a module that only passes in the real tree "
                f"is reading something git does not know about"
            )
            raise Refusal(message)

        def run_one(mutant: Mutant, tests: list[str]) -> object:
            text = graft_shell(source, mutant)
            if text is None:
                return _DROPPED
            with mutation_shell.graft(stage, subject, text):
                return _pytest(
                    stage,
                    ["-n0", "-q", "-x", "-p", "no:cacheprovider", "--no-header", *tests],
                    timeout=reach.timeout(tests),
                    test_module=test_module,
                )

        tally = _tally(chosen, reach, covered, time.monotonic() + budget, run_one, bound=bound)
    sampled = tally.run < len(planted)
    return _verdict_for(
        root,
        test_module,
        subject,
        len(planted),
        tally,
        floor=floor,
        rows=rows,
        started=started,
        arm="shell",
        sampled=sampled,
    )


def _verdict_for(  # noqa: PLR0913 — a verdict is made of exactly these
    root: Path,
    test_module: str,
    subject: str,
    planted: int,
    tally: _Tally,
    *,
    floor: float,
    rows: dict[str, Row],
    started: float,
    arm: str,
    sampled: bool,
) -> Verdict:
    """Apply the per-module ratchet to what an arm measured and render the verdict."""
    effective, ratcheted = _clamped_floor(
        ratchet_floor(rows, test_module, subject, subject_sha(root, subject), tally.run),
        floor,
    )
    return Verdict(
        test_module,
        subject,
        planted,
        tally.run,
        tally.killed,
        tally.survivors,
        time.monotonic() - started,
        effective,
        ratcheted=ratcheted,
        arm=arm,
        sampled=sampled,
    )


def smoke(  # noqa: PLR0913 — every bound this gate applies is a caller-visible knob
    root: Path,
    test_module: str,
    *,
    cap: int = CAP,
    floor: float = FLOOR,
    budget: float = BUDGET_S,
    collect: float = COLLECT_S,
    shell_cap: int = SHELL_CAP,
    shell_floor: float = SHELL_FLOOR,
    shell_budget: float = SHELL_BUDGET_S,
    shell_discriminating: bool = SHELL_DISCRIMINATING,
    rows: dict[str, Row],
) -> Verdict:
    """Plant a bounded sample of mutants in what `test_module` exercises, and judge it.

    One collect pass, then whichever arm has a subject. Python first and always
    where it exists, so nothing about the sixty modules already under this gate
    changes; the shell arm is reached only where the Python one found nothing,
    which used to be the end of it (#246).
    """
    started = time.monotonic()
    collected = measure(root, test_module, timeout=collect)
    subject = collected.python.subject(test_module)
    if subject is not None:
        return _python_smoke(
            root,
            test_module,
            collected.python,
            subject,
            cap=cap,
            floor=floor,
            budget=budget,
            rows=rows,
            started=started,
        )
    shell_subject = _declared_shell_subject(collected.shell, test_module)
    if shell_subject is not None:
        return _shell_smoke(
            root,
            test_module,
            collected.shell,
            shell_subject,
            cap=shell_cap,
            floor=shell_floor,
            budget=shell_budget,
            rows=rows,
            started=started,
            discriminating=shell_discriminating,
        )
    return Verdict(test_module, None, 0, 0, 0, (), time.monotonic() - started, floor)


def _git(root: Path, argv: list[str]) -> str:
    done = subprocess.run(  # noqa: S603 — argv built here from constants and a ref
        ["git", *argv],  # noqa: S607 — git is resolved off PATH on purpose, as elsewhere in tools/
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout if done.returncode == 0 else ""


def is_test_module(path: str) -> bool:
    """Whether a path is one of this repo's test modules."""
    normalised = path.replace(os.sep, "/")
    return (
        normalised.startswith("tests/")
        and normalised.endswith(".py")
        and Path(normalised).name.startswith("test_")
    )


def changed(root: Path, base: str) -> list[str]:
    """List every path this landing adds or rewrites, committed and uncommitted.

    Both halves matter. The committed half is what `tools/land.py` will push; the
    uncommitted half is what an agent has in the tree while running `just fast`
    after an edit, which is where the gate is meant to be met first.
    """
    merge_base = _git(root, ["merge-base", "HEAD", base]).strip()
    found: set[str] = set()
    if merge_base:
        found.update(_git(root, ["diff", "--name-only", merge_base, "HEAD"]).split())
    for line in _git(root, ["status", "--porcelain", "--untracked-files=all"]).splitlines():
        entry = line[3:].strip()
        # A rename's porcelain line is `old -> new`; the new name is the subject.
        found.add(entry.split(" -> ")[-1] if " -> " in entry else entry)
    return sorted(found)


def in_scope(root: Path, base: str) -> list[str]:
    """List the test modules this landing adds or rewrites."""
    return [name for name in changed(root, base) if is_test_module(name) and (root / name).exists()]


def added(root: Path, base: str) -> list[str]:
    """List every path this landing introduces, committed and uncommitted.

    `changed` cannot answer this: it merges its two halves into one set and the
    status letter is gone by the time it returns. The distinction is needed here
    and nowhere else in this gate. A module this landing *edits* keeps whatever
    test module it always had, so demanding one in the same diff would red a
    docstring fix — and eleven of this tree's modules are tested under a name
    that does not reach them (`src/cti_daemon/outbox.py` by
    `tests/unit/test_daemon_outbox.py`, `tools/queue_policy.py` by
    `tests/unit/test_queue.py`), so the rule would red them too, measured before
    it was written. A module this landing *introduces* has whatever this diff
    gives it and nothing else.

    A rename counts as an introduction: the destination is a path that was not
    there at the base, and a module renamed away from its test module's name is
    measured by nothing exactly as a new one is.

    The committed half is the merge-base diff minus every path the base tree
    holds. A branch can carry a module origin/main already has without main's
    commit for it — cherry-picked, or a squash of main carried in — and the
    merge-base diff alone would then name another landing's module as this
    one's introduction (#370 round 2), so a path the base ref's own tree holds
    is on main and never this landing's. Diffing the two refs outright would
    subtract it too, but it would also count everything main deleted or renamed
    after this branch's point as introduced here, which is the same
    wrong-remedy red this subtraction exists to kill. The subtraction's limit
    is the ref itself: a stale origin/main predates a module the remote already
    holds, the base tree therefore lacks it, and the red stands until the fetch
    the refusal names — which is why the refusal names it.
    """
    merge_base = _git(root, ["merge-base", "HEAD", base]).strip()
    found: set[str] = set()
    if merge_base:
        found.update(
            _git(root, ["diff", "--name-only", "--diff-filter=AR", merge_base, "HEAD"]).split(),
        )
    found -= set(_git(root, ["ls-tree", "-r", "--name-only", base]).split())
    for line in _git(root, ["status", "--porcelain", "--untracked-files=all"]).splitlines():
        # The index half of the porcelain code, or `??` for an untracked file.
        if line[:1] not in {"A", "R"} and line[:2] != "??":
            continue
        entry = line[3:].strip()
        found.add(entry.split(" -> ")[-1] if " -> " in entry else entry)
    return sorted(found)


def is_product_module(path: str) -> bool:
    """Whether a path is one of this repo's own Python modules.

    `PRODUCT_ROOTS` is the same set a mutant may be planted in, so the question
    "does this landing measure it?" is asked about exactly the files this gate
    could have had something to say about. Dunder modules are left out:
    `__init__.py` is a package marker and `test___init__.py` is not a file
    anybody means.
    """
    normalised = path.replace(os.sep, "/")
    return (
        normalised.endswith(".py")
        and not Path(normalised).name.startswith("__")
        and normalised.startswith(PRODUCT_ROOTS)
    )


def unmeasured(introduced: list[str], subjects: set[str]) -> list[str]:
    """List the modules this landing introduces that no verdict in the run measured.

    What this asserts about reality is that a smoke selected each survivor as a
    subject — read its bytes, judged mutants against the module's tests. A test
    file's *name* asserts nothing: #370's own review cleared `tools/new.py` on a
    `test_new_cases.py` whose tests exercised only existing code, so every mutant
    went to some other file and the name still satisfied a filename check. The
    subjects the run actually selected are already computed by the time this is
    asked, so they are the evidence, and a module no verdict names is measured by
    nothing — not by a low kill rate, not by a refusal, by nothing at all: no
    rung of `just fast` ever learns it exists.

    An undecided verdict counts: a subject whose reached lines carry no decision
    was still selected and examined, and reding it would be the #239 false red.
    """
    return [
        path
        for path in introduced
        if is_product_module(path) and path not in subjects and path not in NO_TEST_MODULE
    ]


def escape_problems() -> list[str]:
    """Every escape entry whose reason is blank, spelled as the refusal it causes.

    Entering an escape is designed to cost an argument: the reason sits beside the
    path in the diff, and that visibility is the whole design of the lists. An
    entry whose reason is empty or whitespace is the hatch with its cost taken
    out (#370), so `main` refuses the gate over one — by name, before anything
    runs — rather than honouring it. Both lists share the contract, so both are
    held to it.
    """
    return [
        f"blank_escape_reason: {name}[{path}] carries no reason. An escape is argued "
        "beside its path in tools/mutation_smoke.py, or it is not an escape"
        for name, entries in (
            ("NO_MUTABLE_SUBJECT", NO_MUTABLE_SUBJECT),
            ("NO_TEST_MODULE", NO_TEST_MODULE),
        )
        for path, reason in entries.items()
        if not reason.strip()
    ]


def restore(root: Path) -> int:
    """Put back the file the sidecar names, and say what was done.

    The recovery half of the in-place mutation. An agent whose run was killed
    mid-mutant — a harness timeout, a `pkill`, a machine going down — has a
    modified tracked file it did not write, which is the one thing CLAUDE.md says
    to stop and report rather than reset. This is the mechanism that makes the
    difference: the sidecar names one file and carries its exact original bytes,
    so putting it back is not a guess.
    """
    sidecar = root / RESTORE
    if not sidecar.exists():
        print(f"nothing to restore: no {RESTORE}")  # noqa: T201
        return 0
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    path, text = record.get("path"), record.get("text")
    if not isinstance(path, str) or not isinstance(text, str):
        print(f"{RESTORE} is not a restore record; leaving it alone", file=sys.stderr)  # noqa: T201
        return 2
    target = root / path
    already = target.exists() and target.read_text(encoding="utf-8") == text
    target.write_text(text, encoding="utf-8")
    _stamp(target)
    sidecar.unlink()
    print(f"restored {path}" + (" (it was already intact)" if already else " from a live mutant"))  # noqa: T201
    return 0


class Row(NamedTuple):
    """One module's recorded rate, bound to the subject it was measured against.

    `subject_sha` is what makes the rate about a *pair* rather than a module: a
    rate recorded against one body of `daemon.py` is meaningless against another,
    because the mutants that set it no longer exist. The gate releases the
    ratchet — falls back to `FLOOR` — the moment the subject's bytes diverge, so
    a legitimate refactor that lowers a module's achievable rate is never blocked
    by a number its old code earned.
    """

    subject: str
    subject_sha: str
    killed: int
    run: int


def subject_sha(root: Path, subject: str) -> str:
    """Hash the subject file's bytes to a short, stable id for the ratchet's pair key."""
    return hashlib.blake2b((root / subject).read_bytes(), digest_size=4).hexdigest()


def read_baseline(root: Path) -> dict[str, Row]:
    """Read the committed per-module ratchet, keyed by test module path.

    A missing or unreadable baseline is empty, never a red: a gate that refused
    over its own unreadable state would be #137/#186's false red from the gate's
    own side. A row missing any field — or carrying a bool where an int belongs —
    is dropped rather than trusted.
    """
    path = root / BASELINE
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    rows: dict[str, Row] = {}
    for name, entry in raw.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        subject = entry.get("subject")
        sha = entry.get("subject_sha")
        killed = entry.get("killed")
        run = entry.get("run")
        if (
            isinstance(subject, str)
            and isinstance(sha, str)
            and isinstance(killed, int)
            and not isinstance(killed, bool)
            and isinstance(run, int)
            and not isinstance(run, bool)
        ):
            rows[name] = Row(subject, sha, killed, run)
    return rows


def ratchet_floor(
    rows: dict[str, Row],
    test_module: str,
    subject: str,
    subject_sha: str,
    run: int,
) -> float | None:
    """Compute the per-module floor the ratchet sets, or None to fall back to `FLOOR`.

    None is a release, not a gap, in five cases: no row for this module (a new
    module meets `FLOOR`); a row with no sample (`row.run == 0`, a hand-edit —
    see the comment on the condition itself); the row's subject differs (the test
    now exercises a different file); the subject's bytes differ (the file
    changed, so the recorded rate is about a different mutant set — #244's "the
    number is about a pair, not a module"); or the number of mutants that reached
    a verdict is not the row's — a dropped mutant (one whose graft will not
    compile, or on the shell arm will not parse), a moved `--cap`, or a changed
    coverage set each put the rate on a denominator other than the row's, and the
    comparison would be across them. The clock is not among these causes: a
    budget-cut run refuses before any verdict exists (#435 round 2). In every
    release the gate still applies `FLOOR` — the ratchet only ever raises the
    bar.

    The floor takes `SLACK` kills off the recorded rate. With the subject pinned
    and the run matching, `kill_rate >= this` is integer-exact: it is
    `killed >= row.killed - SLACK` over one shared denominator.
    """
    row = rows.get(test_module)
    # `row.run == 0` is a hand-edited row with no sample: there is no rate to
    # enforce and no denominator to divide by, so release rather than crash.
    if (
        row is None
        or row.run == 0
        or row.subject != subject
        or row.subject_sha != subject_sha
        or row.run != run
    ):
        return None
    return (row.killed - SLACK) / row.run


def _clamped_floor(ratchet: float | None, floor: float) -> tuple[float, bool]:
    """Return the effective floor and whether the ratchet raised it above `floor`.

    A release (`ratchet is None`) leaves the bar at `floor` and is not a
    ratcheted verdict; otherwise the ratchet only ever tightens, so a recorded
    rate under `floor` is clamped back to `floor` rather than lowering the bar.
    """
    if ratchet is None:
        return floor, False
    return max(floor, ratchet), ratchet > floor


def write_baseline(root: Path, rows: dict[str, Row]) -> None:
    """Write the ratchet, sorted by module for a stable diff.

    The parent directory is created so a first `--record` in a tree without
    `tools/` (a throwaway repo under test) does not fail on the write.
    """
    path = root / BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    serialised = {
        name: {
            "subject": row.subject,
            "subject_sha": row.subject_sha,
            "killed": row.killed,
            "run": row.run,
        }
        for name, row in sorted(rows.items())
    }
    path.write_text(json.dumps(serialised, indent=2) + "\n", encoding="utf-8")


def _judge(
    root: Path,
    targets: list[str],
    args: argparse.Namespace,
) -> tuple[int, int, set[str], bool]:
    """Smoke each target, print its verdict, and count the reds and the refusals.

    The subjects come back too, because the selection rung's evidence is what the
    run measured rather than any name (#370): a module no verdict here selected
    is what `unmeasured` names.
    """
    rows = read_baseline(root)
    red = 0
    refused = 0
    subjects: set[str] = set()
    # A non-empty target set that reaches no verdict measured nothing, so it
    # must not make the stronger exhaustive claim. Mixed runs still aggregate
    # only the verdicts they reached; an exempt target planted no candidate.
    sampled = bool(targets) and all(target in NO_MUTABLE_SUBJECT for target in targets)
    for target in targets:
        if target in NO_MUTABLE_SUBJECT:
            print(f"-- {target} exempt: {NO_MUTABLE_SUBJECT[target]}", flush=True)  # noqa: T201
            continue
        try:
            verdict = smoke(
                root,
                target,
                cap=args.cap,
                floor=args.floor,
                budget=args.budget,
                collect=args.collect,
                shell_cap=args.shell_cap,
                shell_floor=args.shell_floor,
                shell_budget=args.shell_budget,
                shell_discriminating=args.shell_discriminating_lines,
                rows=rows,
            )
        except Refusal as refusal:
            # One module's refusal is not the others': every target still gets a
            # verdict, and the exit code says a refusal happened at the end.
            refused += 1
            print(f"?? {target} could not run: {refusal}", file=sys.stderr)  # noqa: T201
            continue
        if verdict.subject is not None:
            subjects.add(verdict.subject)
        sampled |= verdict.sampled
        print(verdict, flush=True)  # noqa: T201 — stdout text IS this gate's output
        if not verdict.ok:
            red += 1
            print(f"    {verdict.reason}", file=sys.stderr)  # noqa: T201
            for survivor in verdict.survivors:
                print(f"    survived: {survivor}", file=sys.stderr)  # noqa: T201
    return red, refused, subjects, sampled


def _report_selection(
    introduced: list[str],
    unnamed: list[str],
    *,
    survey: bool,
    refused: bool,
) -> None:
    """Print the escapes this landing takes and the modules it measures by nothing.

    A red of its own kind: there is no verdict to print, because the thing that
    went wrong is that nothing was selected to reach one. So the line names the
    class — `no_test_module` — and its remedies in the order they should be
    reached for. The fetch comes first, because a stale origin/main is the one
    cause no choice of diff basis can rule out and the fetch is the remedy that
    writes nothing. Then the test module's name, which is what `Reach.subject`
    leans on: a test module that reaches the code it names makes it the subject,
    which is the measurement this red demands. The escape comes last.

    RED is a gate's voice, so a survey never hears it — `--report` never reds.
    It still names the module, in the survey's own `--` voice, because `--report`
    is the one non-gating way to see a landing's selection and a survey that
    named every excused module and no accused one would preview everything except
    the rung most likely to red the reader (#441).

    A refusal keeps the `-- exempt:` lines and drops the unmeasured ones, in
    either voice. The exemptions are statements about the diff, true whatever the
    run did; `unnamed` is computed from the subjects the verdicts selected, and a
    refused run has only some of them — so a module named there may be one a
    completed run would have measured.
    """
    for path in introduced:
        if path in NO_TEST_MODULE:
            print(f"-- {path} exempt: {NO_TEST_MODULE[path]}", flush=True)  # noqa: T201
    if refused:
        return
    for path in unnamed:
        if survey:
            print(  # noqa: T201 — stdout text IS this gate's output
                f"-- {path} unmeasured: this landing introduces it and no verdict in "
                f"this run selected it as a subject, so the gate reds here with the "
                f"class no_test_module and its remedies. A survey reports; it never reds.",
                flush=True,
            )
            continue
        print(  # noqa: T201 — stdout text IS this gate's output
            f"RED {path} no_test_module: this landing introduces it and no verdict in "
            f"this run selected it as a subject — the diff's test modules name other "
            f"code, or none ran it at all — so no rung of `just fast` measures it. A "
            f"stale origin/main ref names another landing's module as introduced here, "
            f"so `git fetch origin` is the first thing to try — `just fast` never "
            f"fetches, and the landing gate always does. If it is this landing's "
            f"work, add tests/unit/test_{_stem_key(path)}.py whose tests execute it, or "
            f"add {path} to NO_TEST_MODULE in tools/mutation_smoke.py with the reason.",
            flush=True,
        )


def _report_sampling(*, sampled: bool, refused: bool) -> None:
    """State the completed run's coverage without calling a refusal a result."""
    if not refused:
        classification = "sampled" if sampled else "exhaustive"
        print(MUTATION_CLASSIFICATIONS[classification][0], flush=True)  # noqa: T201 — stdout text IS this gate's output


def _record(root: Path, targets: list[str], args: argparse.Namespace) -> int:
    """Measure each target and write its rate into the ratchet baseline.

    Not a gate: it always exits 0, records what it could measure, and reports
    every row's fate. Three fates, each diff-visible:

    * **recorded** — a new row, or a module whose subject changed (the old rate
      was about a different pair, so the new one replaces it; reported as a
      re-baseline);
    * **raised** — same subject, stronger tests, more kills: the number goes up;
    * **held** — same subject, fewer kills: the ratchet never lowers a row
      silently. Lowering is deliberate, so `--record` leaves the row and names
      it, and the row is lowered by editing the baseline by hand — visible in the
      diff, the same reviewability `NO_MUTABLE_SUBJECT` has.

    A module with no subject, nothing to plant, or no verdict is skipped: there
    is no rate to record. A refusal (a module not green on its own) is reported
    and skipped, because a measurement that did not happen cannot populate a row.
    """
    rows = read_baseline(root)
    updated = dict(rows)
    for target in targets:
        if target in NO_MUTABLE_SUBJECT:
            continue
        try:
            verdict = smoke(
                root,
                target,
                cap=args.cap,
                floor=args.floor,
                budget=args.budget,
                collect=args.collect,
                shell_cap=args.shell_cap,
                shell_floor=args.shell_floor,
                shell_budget=args.shell_budget,
                shell_discriminating=args.shell_discriminating_lines,
                rows=rows,
            )
        except Refusal as refusal:
            print(f"?? {target} not recorded: {refusal}", file=sys.stderr)  # noqa: T201
            continue
        if verdict.subject is None or verdict.run == 0:
            continue
        sha = subject_sha(root, verdict.subject)
        measured = Row(verdict.subject, sha, verdict.killed, verdict.run)
        existing = rows.get(target)
        if existing is None:
            updated[target] = measured
            print(  # noqa: T201
                f"recorded {target}: {verdict.killed}/{verdict.run} against {verdict.subject}",
            )
        elif existing.subject_sha != sha:
            updated[target] = measured
            print(  # noqa: T201
                f"re-baselined {target}: subject changed, "
                f"{existing.killed}/{existing.run} -> {verdict.killed}/{verdict.run} "
                f"against {verdict.subject}",
            )
        elif verdict.killed > existing.killed:
            updated[target] = measured
            print(  # noqa: T201
                f"raised {target}: {existing.killed}/{existing.run} -> "
                f"{verdict.killed}/{verdict.run}",
            )
        elif verdict.killed < existing.killed:
            print(  # noqa: T201
                f"held {target}: would lower {existing.killed}/{existing.run} -> "
                f"{verdict.killed}/{verdict.run} (same subject). Lowering is deliberate: "
                f"edit {BASELINE} by hand.",
            )
        else:
            print(f"unchanged {target}: {verdict.killed}/{verdict.run}")  # noqa: T201
    write_baseline(root, updated)
    return 0


def _judge_rust(root: Path) -> tuple[int, int]:
    """Run the Rust rung and print its verdict, counting the red and the refusal.

    A rung rather than a per-module smoke, because the shim is one crate of 53
    mutants: there is nothing to sample and no rate to compare, only whether any
    viable mutant survived (`tools/mutation_rust.py`).
    """
    try:
        outcome = mutation_rust.run(root)
    except mutation_rust.Refusal as refusal:
        print(f"?? {mutation_rust.MANIFEST} could not run: {refusal}", file=sys.stderr)  # noqa: T201
        return 0, 1
    print(outcome, flush=True)  # noqa: T201 — stdout text IS this gate's output
    if outcome.ok:
        return 0, 0
    print(mutation_rust.report(outcome), file=sys.stderr)  # noqa: T201
    return 1, 0


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0911 — the rules action must bypass every gate-state read, while each refusal keeps its own exit
    """Smoke every test module in scope and print one line per module."""
    parser = argparse.ArgumentParser(
        description="Red a landing whose new tests do not notice the code changing.",
    )
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--base", default="origin/main", help="ref the landing is measured against")
    parser.add_argument("--paths", nargs="*", help="smoke these test modules instead of the diff")
    parser.add_argument(
        "--rules",
        action="store_true",
        help="print the derived mutation-smoke contract and do nothing else",
    )
    parser.add_argument("--cap", type=int, default=CAP)
    parser.add_argument("--floor", type=float, default=FLOOR)
    parser.add_argument("--budget", type=float, default=BUDGET_S)
    parser.add_argument("--collect", type=float, default=COLLECT_S)
    parser.add_argument("--shell-cap", type=int, default=SHELL_CAP)
    parser.add_argument("--shell-floor", type=float, default=SHELL_FLOOR)
    parser.add_argument("--shell-budget", type=float, default=SHELL_BUDGET_S)
    parser.add_argument(
        "--rust",
        action="store_true",
        help="run the Rust rung whatever the diff says (default: only when extension/ changed)",
    )
    parser.add_argument(
        "--no-rust",
        action="store_true",
        help="skip the Rust rung even when the shim changed",
    )
    parser.add_argument(
        "--shell-discriminating-lines",
        action="store_true",
        default=SHELL_DISCRIMINATING,
        help="plant only on the shell lines the module's tests tell apart (measured worse)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="survey only: print every verdict and always exit 0",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help=f"put back the file {RESTORE} names, after an interrupted run",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help=(
            "measure each in-scope module and write its rate into the ratchet "
            f"baseline ({BASELINE}), then exit 0; never lowers a same-subject row"
        ),
    )
    args = parser.parse_args(argv)

    if args.rules:
        sys.stdout.write(render_contract())
        return 0

    root = args.root.resolve()
    sidecar = root / RESTORE
    if args.restore:
        return restore(root)
    problems = escape_problems()
    if problems:
        for problem in problems:
            print(f"?? {problem}", file=sys.stderr)  # noqa: T201
        return 2
    if sidecar.exists():
        print(  # noqa: T201 — stdout text IS this gate's output
            f"{RESTORE} is present: another smoke is running in this tree, or one was "
            f"interrupted mid-mutant and left a mutant in it. Wait, or run "
            f"`just mutation --restore` to put the file it names back, then run again.",
            file=sys.stderr,
        )
        return 2

    touched = [] if args.paths else changed(root, args.base)
    targets = args.paths or [
        name for name in touched if is_test_module(name) and (root / name).exists()
    ]
    # `--paths` names the modules to smoke, so the diff is not what is being
    # judged and the selection rung has nothing to say about it.
    introduced = [] if args.paths else added(root, args.base)
    rust = args.rust or (mutation_rust.in_scope(touched) and not args.no_rust)
    # No targets means nothing will run, so no subject can appear later: the
    # empty set is the run's whole answer, and this exit stays as cheap as it was.
    if not targets and not rust and not unmeasured(introduced, set()):
        print(  # noqa: T201 — stdout text IS this gate's output
            MUTATION_CLASSIFICATIONS["no-target"][0].format(base=args.base),
            flush=True,
        )
        return 0

    if args.record:
        return _record(root, targets, args)

    # The selection rung's evidence is what the run measured, so a module
    # nothing selected is known only after the verdicts and is reported after
    # them (#370) — the red-before-any-mutant ordering a name check allowed
    # cannot survive binding the check to the measurement. A landing with no
    # test modules at all still reds before a single mutant is planted, because
    # nothing then runs to measure anything.
    red, refused, subjects, sampled = _judge(root, targets, args)
    unnamed = unmeasured(introduced, subjects)
    if rust:
        rust_red, rust_refused = _judge_rust(root)
        red += rust_red
        refused += rust_refused
    # The report comes before the refusal exit, because the `-- exempt:` half is
    # a statement about the diff rather than a verdict about the run (#441). The
    # unmeasured half is a verdict, in either voice, so a refusal drops it.
    _report_selection(introduced, unnamed, survey=args.report, refused=bool(refused))
    if refused and not args.report:
        return 2
    # An unmeasured product module can leave target set empty while still reding the gate.
    # That is not an exhaustive mutation run: no classification is the finding in this case.
    if targets or rust:
        _report_sampling(sampled=sampled, refused=bool(refused))
    if (red or unnamed) and not args.report:
        print(  # noqa: T201
            f"{red} subject(s) did not notice the code changing. Strengthen the "
            f"assertions that let the survivors above through — never weaken the floor.",
            file=sys.stderr,
        )
    return 1 if (red or unnamed) and not args.report else 0


if __name__ == "__main__":
    raise SystemExit(main())
