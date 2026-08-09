# The mutation gate grows a shell arm and a Rust rung, and SQF's non-goal is written down

Delegated-decision: yes
Date: 2026-08-09
Stood-in-for: human sign-off on an ADR, and on amending ADR-0064 — #246 commissioned the two
buildable arms and asked for the SQF non-goal to be recorded "in ADR-0064's amendment style",
which is a decision about what this project's mutation gate is for
Reviewed-by-human: pending
Claimed: 0067, after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0066) and a
scan of every open issue's body and comments, whose highest claim was also 0066 (on #244)

## What happened

ADR-0064 built a mutation smoke that could only ask its question of Python. Eleven test
modules sat on `NO_PYTHON_SUBJECT`, its named escape, and reading each against the tree
(#246) found that **eight of them drive `spike/*.sh` as subprocesses and assert on what the
scripts do**. "Its subject is shell" was never a reason those eight could not be measured —
only a reason the tool could not measure them yet. The Rust shim had no mutation at all, and
the question of SQF came back every time somebody read the list.

`docs/research/mutation-shell-arm.md` is the measurement behind everything below.

## Decision 1: the shell arm is bash's own xtrace, and the escape list means what its name says

`tools/mutation_shell.py` owns a bash mutator on the same terms as ADR-0064's Python one: a
bounded deterministic sample, `bash -n` where that arm has `compile()`, an operator set
chosen for a low equivalent-mutant rate rather than for coverage of the literature.

Coverage comes from bash. `$BASH_ENV` is read before any non-interactive script, so a
preamble there turns `set -x` on for every script a test spawns; `BASH_XTRACEFD` keeps the
trace off stderr, which several of these modules assert on; `PS4` carries `$BASH_SOURCE` and
`$LINENO`. Attribution to individual tests is a one-hook pytest plugin. **Measured free** —
14.88 s against 14.75 s, 190.80 s against 190.64 s — which is why it runs on every collect
pass rather than only where it is expected to be needed.

Routing is mechanical rather than declared: the Python subject is tried first and wins where
it exists, so nothing about the sixty modules already under this gate changes; the shell
subject is reached only where the Python one found nothing, which used to be the end of it.

The escape list is renamed `NO_MUTABLE_SUBJECT` and is **four rows, not eleven**. Three read
documents rather than running anything. The fourth is `tests/unit/test_pool_slots.py`, and it
is the first row this project has written whose reason is **cost rather than shape**: the
shell arm can measure it, and one serial run of the module is 190.8 s before a mutant is
planted. `tests/unit/test_client_lock.py` joins it at 216.6 s. Both rows carry the number, so
a later reader can re-measure the claim rather than inherit it.

**What would overturn this.** The list growing back past four, which would mean the routing is
wrong rather than that more modules are special — ADR-0064's own tripwire, unchanged. Or a
cost row being added for a module that is merely slow rather than past the ceiling, which
would make "cost" the excuse "shell" used to be; the defence is that a cost row must quote its
measured seconds, and a row without one is not a reason.

## Decision 2: the shell arm's evidence rule is weighted, and its floor is its own number

Two departures from the Python arm, both measured before they were taken.

**The subject rule is weighted by reach.** `spike/run.sh` sources three helpers and
`tier-lock.sh` sources `slots.sh`, so one test that takes a lock executes a whole script
nobody was testing — and ADR-0064's discrimination score *rewards* that script for being
incidental. On `tests/unit/test_bringup_guards.py` it chose `spike/slots.sh` over
`spike/run.sh` and the module killed **0 of 12**. Multiplying discrimination by the share of
the module's tests that reached the file at all fixes it. Applied to the shell arm only,
because the corpus sweep that set `FLOOR` was taken under the unweighted rule.

**`SHELL_FLOOR` is 20%, and not `FLOOR`.** A different mutator over a different corpus needs
its own number, set the way `FLOOR` was: sweep first, enforce after. Measured — 100%, 80%,
80%, 80%, 80%, 30%, 30% — the spread has one cause, and it is that the two 30% modules are the
two on the 1,278-line `spike/run.sh`. The other end is a throwaway module that runs every
branch of its subject and asserts only that something came back: **0%**. So 20% sits twenty
points above the shape it exists to stop and one kill below the weakest thing it must not
stop, which is the shape `FLOOR` has.

ADR-0064 decision 2's own escape hatch is taken for the first time, once:
`tests/unit/test_host_seam.py` declares `spike/hosts.sh` in `SHELL_SUBJECT`, because its name
misses the script by a plural and the evidence rule then picked `spike/regress.sh` and scored
it 42% against a script it is not about. A declaration is a **tie-break among the scripts the
tests executed**, never a nomination: one naming a script the tests never ran is a refusal.

**What would overturn this.** `SHELL_SUBJECT` growing past a handful, which would say the
evidence rule is wrong for shell rather than that a few modules are awkwardly named. Or the
two 30% modules moving without their tests changing, which would mean the rate is measuring
`spike/run.sh`'s size rather than their assertions — the fix then is ADR-0049's migration, not
a lower floor. Lowering `SHELL_FLOOR` is not an alternative to either.

## Decision 3: a shell mutant is written into a hardlinked stage, never into `spike/`

ADR-0064 mutates the real tree in place and defends the window with a restore sidecar, and
that is right for `src/`. It is wrong for `spike/*.sh`: those are what a live Arma tier reads,
`just regress` from this same worktree may be holding a slot while `just land` runs
`just fast`, and a mutant in `spike/run.sh` for the two seconds a mutant run lasts is a
corrupted in-world verdict that no sidecar repairs afterwards.

So the shell arm hardlinks every tracked and not-ignored file into a temporary tree — about a
tenth of a second for 7,168 files, and no disk — and writes a mutant by **unlinking and
re-creating** the staged file. Hardlinks and not symlinks because `Path.resolve()` follows a
symlink: `tests/unit/conftest.py` computes `REPO` from its own resolved path, and a symlink
farm would send the tests back to the real scripts and make the stage an expensive no-op.

Before any mutant is planted, the tests the mutants will select are run in the stage
unmutated. That is not tidiness: every mutant is judged by whether its tests went red, so a
stage that broke them would score the module 100% — the exact defect #239 records as having
scored every module in this repository full marks.

**What would overturn this.** A `Path.resolve()` or filesystem change that makes a hardlinked
tree resolve to its origin, which would silently return the tests to the real scripts; the
assertion that stops that being silent is
`tests/unit/test_mutation_shell.py::test_a_graft_never_touches_the_real_script`, on inodes. Or
the staging cost rising with the repository until it is a material share of the rung, at which
point staging a subtree rather than the tree is the change to measure.

## Decision 4: the Rust rung is whole-crate, gated on the diff, and reds on any survivor

`cargo-mutants` 27.1.0 over `extension/`, run when and only when the diff touches
`extension/`. Measured: 53 mutants, 34 caught, 1 timeout, 18 unviable, **0 missed**; 124.5 s
serial and **52.7 s at four jobs**; and `extension/` has been touched by **6 of the 418
commits** on `main`. A rung that costs nothing on 98.6% of landings, 52.7 s on the rest, and
reds a gutted shim test earns its runtime. Ungated it would be a 48% tax on every edit for a
crate that changes six times a year.

Whole-crate rather than diff-scoped, because the weakening this rung exists to catch is a
gutted *test*, and a landing that guts a test changes no source line for `--in-diff` to find.

No sample and no floor: 53 is the whole population, so there is nothing to sample and no rate
to compare — only whether any viable mutant survived. The escape is `SURVIVES_BY_DESIGN`, a
named mutant with its reason beside it, and it ships **empty**, which is a measurement.

Two readings deliberately disagree with the engine. A **timeout is a kill** here, as it has
been since #239 — the shim has one, `Connection::arm` losing its read deadline — where
`cargo-mutants` exits 3 and calls it a problem; and **unviable is excluded from the count**
rather than scored either way. Both are why the verdict is read out of `missed.txt` and not
off the exit code.

**What would overturn this.** `extension/` growing until the whole-crate run stops fitting,
at which point the number to re-measure is the 52.7 s and the change is a scoped run with the
gutted-test hole closed some other way. Or `SURVIVES_BY_DESIGN` acquiring rows on an engine
upgrade rather than on a code change, which would say a zero-survivor rung is too strict for
an operator set this project does not configure — `tools/mutation_rust.py` names the version
it was measured against so that reading is available.

## Decision 5: there is no SQF arm, and the reason is economic and written down

Recorded beside the escape list and in the research note, because the question comes back
every time somebody reads the list.

It is not that SQF is hard to mutate. It is that there is nowhere to run a mutant: SQF
executes inside the Arma engine and nowhere else, SQF-VM is optional in this project's gates,
so a mutant's only verdict is a world. `just regress` is about 20 minutes on three slots and
its unit is a fresh world per probe, which makes a twenty-mutant sample against one addon
function hours per module, on a machine the human also plays on and which the tier holds
single-occupancy. `compileFinal` closes the cheap route: the Functions Library `compileFinal`s
every `cti_fnc_`, so a probe cannot stub one and a mutant cannot be swapped in at run time —
it would have to go into the addon source with a `hemtt build` inside the per-mutant loop.

What stands in its place is named rather than gestured at: the three red-by-design probes
(#80, #96, #102), which demand the failure class they expect; the expected-class machinery,
which turns a silently-changed decision into the wrong class rather than a pass; and the probe
vacuity rule (#116, ADR-0016), which requires a probe to assert that its staging took effect —
the property mutation testing buys, obtained by construction instead of by sampling.

**What would overturn this.** An in-process SQF runner this project is willing to gate on —
SQF-VM reaching the point where a `cti_fnc_` runs under it with the addon's own arrangement —
which would make a mutant cost milliseconds instead of a world and stop the arithmetic
applying. That is the evidence to bring; "we should mutate SQF too" is not.

## Consequences

- Seven test modules that were exempt are now measured, and the largest ungated surface in
  this repository's own tooling is gated.
- `just fast` grows a rung whose worst measured case — a landing that rewrites
  `tests/unit/test_run_verdict.py`, at 193.7 s — puts it at roughly five minutes. That is
  ADR-0064 decision 3's ceiling reached rather than crossed, and it is the number to watch.
- Two rows of the escape list are now cost exemptions carrying their seconds, which is a
  kind of row this project has not had before and which a reader should treat as a debt
  rather than as a ruling.
- The Rust rung is not in `just prereqs tools`: that installer verifies every download against
  a published checksums file and `cargo-mutants` ships none, so the rung refuses by name with
  the pinned `cargo install` line instead. That is unfinished, and it is stated in
  `docs/research/mutation-shell-arm.md` §9 rather than left to be discovered.
- The mutation gate is now three arms and one written-down non-goal, which is the whole of
  what #246 asked for. `CLAUDE.md`'s `just mutation` row no longer describes it, and the
  replacement is proposed in #246's closing comment rather than landed, because that file is
  a human sign-off gate.
