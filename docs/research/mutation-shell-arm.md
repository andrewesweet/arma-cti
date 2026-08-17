# The mutation gate beyond Python: a shell arm, a Rust rung, and no SQF arm

<!-- absent-path -->
<!-- A dated research record: the repository paths it cites are the tree as it stood when
     the research was done, and some belong to other projects entirely. Neither is a claim
     about this tree today, which is what the marker above tells `just check-doc-paths`. -->

**Measured**: 2026-08-09 (#246), against the tree at `576eead`, on this box.
**Question**: can `just mutation` ask of `spike/*.sh` and of the Rust shim what #239 taught it to ask of `src/` and `tools/`, and what should it do about SQF?
**Answer in one line**: **yes for both, and no for SQF on economics rather than difficulty** — the shell arm gates seven of the eleven modules that used to sit on the escape list, the Rust rung costs nothing on 98.6% of landings and reds a gutted shim test, and a per-mutant SQF verdict is a fresh Arma world, which is hours per module on a machine the human also plays on.

**Hardware and software.** WSL2 (kernel 6.6.87.2-microsoft-standard-WSL2) on a 13th Gen Intel Core i5-13420H, 6 cores / 12 threads, 12,248,264 kB total RAM. CPython 3.13.14, bash 5.2, `cargo-mutants` 27.1.0, Rust 1.97.1.

---

## 1. What the eleven exempt modules actually are

`NO_PYTHON_SUBJECT` carried eleven rows when this started. Reading each one against the tree rather than against its own reason:

| Module | tests | drives shell | reads documents |
|---|---:|---|---|
| `test_bringup_guards.py` | 7 | yes, 6 subprocess sites | also reads the justfile |
| `test_client_lock.py` | 39 | yes, 11 | yes |
| `test_host_guard.py` | 19 | yes, 11 | |
| `test_host_seam.py` | 9 | yes, 4 | |
| `test_play_install.py` | 12 | yes, 5 | |
| `test_pool_slots.py` | 54 | yes, 20 | yes |
| `test_regress_selection.py` | 12 | yes, 2 | |
| `test_run_verdict.py` | 17 | yes, 1 | |
| `test_playtest_observer_staging.py` | 6 | **no** | reads `spike/run.sh` and probe headers |
| `test_probe_headers.py` | 11 | **no** | reads `spike/probes/*.sqf` |
| `test_report_schema.py` | 3 | **no** | reads `report.SHAPES` and the SQF samplers |

Eight of eleven run the scripts. "Its subject is shell" was never a reason those eight could not be measured — only a reason the tool could not measure them yet.

---

## 2. How the shell arm sees what a test executed

`coverage.py` has no bash, so the coverage comes from bash itself: `$BASH_ENV` is read before any non-interactive script, so a preamble there turns `set -x` on for every script a test spawns; `BASH_XTRACEFD` sends the trace to a private descriptor rather than to stderr; `PS4` carries `$BASH_SOURCE` and `$LINENO`. Attribution to individual tests comes from a one-hook pytest plugin that points `CTI_SHELL_TRACE` at a per-test file.

**The tracing is free.** Same module, same box, immediately consecutive:

| Module | untraced | traced | under coverage |
|---|---:|---:|---:|
| `test_bringup_guards.py` | 14.88 s | 14.75 s | 15.03 s |
| `test_host_guard.py` | 10.12 s | 10.09 s | 10.36 s |
| `test_pool_slots.py` | 190.80 s | 190.64 s | — |

That is why it is switched on for **every** collect pass rather than only for modules expected to need it: a module that turns out to drive shell is already measured when it gets there, and no module pays for the possibility.

**It also corrects an inherited attribution.** #239 recorded `test_pool_slots.py` at 188.1 s and said "the whole cost is the coverage pass"; #281 repeated the figure. Measured here, the module's own serial run is 190.80 s and coverage adds about 1%. The 188 s was never the coverage pass — it is what those 54 tests cost with `-n0`.

**Two properties had to be asserted rather than assumed**, and both are tests in `tests/unit/test_mutation_shell.py`:

- the preamble writes nothing at all when `CTI_SHELL_TRACE` is unset, because every bash this repository starts for any other reason reads that file;
- the trace never reaches stderr, because several of these modules assert on a script's stderr and an xtrace there would red every one of them.

---

## 3. The corpus sweep, and where `SHELL_FLOOR` comes from

Every measurable shell-subject module, at the landed bounds (`SHELL_CAP` 10, 5 s of tests per mutant), before any floor was enforced:

| Module | subject | killed | rate | wall |
|---|---|---:|---:|---:|
| `test_host_seam.py` | `spike/hosts.sh` | 3/3 | **100%** | 18.5 s |
| `test_host_guard.py` | `spike/host-guard.sh` | 8/10 | **80%** | 32.3 s |
| `test_play_install.py` | `spike/play-install.sh` | 8/10 | **80%** | 23.7 s |
| `test_regress_selection.py` | `spike/regress.sh` | 8/10 | **80%** | 30.9 s |
| `test_client_lock.py` | `spike/client-lock.sh` | 8/10 | **80%** | 216.6 s |
| `test_bringup_guards.py` | `spike/run.sh` | 3/10 | **30%** | 78.0 s |
| `test_run_verdict.py` | `spike/run.sh` | 3/10 | **30%** | 193.7 s |

**The spread is not noise, and it has one cause: `spike/run.sh`.** Every module on a focused script scores 80–100%. Both modules on the 1,278-line `run.sh` score 30%, and their survivors are all in ground the module crosses without claiming anything about — the cleanup trap, the RPT collection, the client-lock arithmetic. That is a true statement about those two modules, and it is also ADR-0049's un-migrated remainder showing up in a measurement for the first time.

The other end of the range is the throwaway corpus in `tests/unit/test_mutation_shell.py`, a `spike/toll.sh` with four decisions in it and three modules over it:

| Fixture | rate |
|---|---:|
| sound — asserts the output and the exit status of every branch | **100%** (8/8) |
| weak — runs every branch, asserts only that something came back | **0%** (0/8) |
| vacuous — asserts nothing, runs nothing | **no subject**, red |

So `SHELL_FLOOR = 0.20` sits twenty points above the shape it exists to stop and one kill below the weakest thing it must not stop. That is the same structure `FLOOR = 0.50` has (30% weak fixture, 62% weakest module), with a narrower margin at the top because the shell corpus is more spread.

---

## 4. Two refinements, one kept and one disproved

**Weighting the evidence rule by reach — kept.** `spike/run.sh` sources `hosts.sh`, `client-lock.sh` and `play-install.sh`, and `tier-lock.sh` sources `slots.sh`, so one test that takes a lock executes a whole script nobody was testing. The Python arm's discrimination score *rewards* that script for being incidental: on `test_bringup_guards.py` it scored `spike/slots.sh` at 33 against `spike/run.sh`'s 14, chose it, and the module killed **0 of 12**. Multiplying discrimination by the share of the module's tests that reached the file at all puts `run.sh` back in front, and the same module then scored 25%. Applied to the shell arm only: the Python corpus sweep that set `FLOOR` was taken under the unweighted rule, and changing the rule under sixty modules would move rates no landing touched.

**Restricting mutants to the discriminating lines — disproved, again.** ADR-0064 records this measured and rejected for Python. Re-derived here rather than inherited, over the whole shell corpus:

| Module | all executed lines | discriminating lines only |
|---|---:|---:|
| `test_host_guard.py` | 83% (10/12) | 92% (11/12) |
| `test_regress_selection.py` | 75% (9/12) | 83% (10/12) |
| `test_play_install.py` | 83% (10/12) | 83% (10/12) |
| `test_run_verdict.py` | 33% (4/12) | 38% (3/8) |
| `test_bringup_guards.py` | 25% (3/12) | 25% (**1/4**) |
| `test_host_seam.py` | 42% (5/12) | **8%** (1/12) |

It raises three modules by a little and destroys two: `test_bringup_guards.py` collapses from twelve mutants to four — the same rate on a third of the evidence, which is a weaker claim at the same number — and `test_host_seam.py` loses 34 points. Off, and the switch (`--shell-discriminating-lines`) stays so the next person can re-measure rather than re-argue.

---

## 5. The operator set, and what it refuses to touch

Chosen the way ADR-0064 chose the Python one: for a low equivalent-mutant rate, not for coverage of the literature. `bash -n` over the grafted text stands in for `compile()`.

Kept: flipping a test operator (`-eq`↔`-ne`, `-lt`→`-ge`, `-n`↔`-z`, `==`→`!=`, …); shifting an ordering operator by one; `&&`↔`||`; dropping a `!`; `exit N` → `exit 0` and `return N` → `return 0`; offsetting an integer.

Refused, each because it was measured surviving or because it is not a decision the script takes:

- **anything inside quotes.** A comparison in a log message changes what the script *says*.
- **`=`, `<`, `>` outside a `[[ ]]`, `[ ]` or `(( ))`.** `=` is assignment and `<` is a redirection; `SERVER_DIR="$HOME/arma3server"` and `cmd <in >out` offer nothing.
- **`-n`, `-eq` and friends outside those brackets.** `sed -n` is not a test and `head -1` is not a comparison.
- **an integer inside `${...}`.** `${CTI_HOLD_HC:-0}` is bash's spelling of `def f(hold_hc=0)`, which the Python arm has never touched; every one of these measured here survived. The `1` beside it in `$(( 1 - ${CTI_HOLD_HC:-0} ))` is a real constant and is still offered.
- **an integer on a line carrying `=~`.** `[0-9]` becoming `[1-9]` is a regular expression, not a decision.

Freezing the `${...}` numbers alone moved `test_bringup_guards.py` from 25% to 33% at cap 12 and `test_host_seam.py` from 42% to 100% (with the declared subject).

---

## 6. `cargo-mutants` over the shim

Whole crate, current tree, `cargo-mutants` 27.1.0:

| | value |
|---|---|
| mutants generated | 53 |
| caught | 34 |
| timeout (counted here as a kill) | 1 — `replace Connection::arm -> Result<(), String> with Ok(())` |
| unviable (does not compile) | 18 |
| **missed** | **0** |
| wall, serial | **124.5 s** |
| wall, `--jobs 4` | **52.7 s** |
| `cargo test` alone, warm | 1.22 s, 17 tests |

**It does catch a real weakening.** Replacing the two `assert_eq!` calls in `error_json_survives_a_detail_that_is_not_plain_text` and `error_json_leaves_ordinary_text_alone` with bare calls — the calls still run, nothing is asserted — leaves `src/lib.rs:266:18: replace match guard (c as u32) < 0x20 with false in escape_json` alive. `cargo-mutants` reports 1 missed of 9 and exits 2. Note that only *one* of nine survives: the other tests reach `escape_json` indirectly and kill the rest, which is what a whole-crate run buys over a diff-scoped one.

**Does it earn its runtime?** `extension/` has been touched by **6 of the 418 commits** on `main` — 1.4%. Gated on the diff, the rung costs nothing on 98.6% of landings and 52.7 s on the rest, against a `just fast` that is 111 s of pytest alone. That is worth having. Ungated it would be a 48% tax on every edit for a crate that changes six times a year, which is why it is gated.

Two places where the reading deliberately disagrees with the engine, both in `tools/mutation_rust.py`:

- **the exit code is not read.** `cargo-mutants` exits 3 for a timeout and calls it a problem; this project has counted a timeout as a kill since #239 — "the tests noticing, slowly" — and the shim has exactly one. The verdict comes out of `missed.txt`.
- **`unviable` is excluded from the count**, not scored either way. 18 of 53 do not compile; scoring them as kills would inflate the verdict and scoring them as survivors would red a tree nobody weakened.

**No sample and no floor**, because both are answers to a corpus too big to run whole and this one is not: 53 is the whole population, so the verdict is simply whether any viable mutant survived. The escape is `SURVIVES_BY_DESIGN`, a named mutant with its reason beside it, and it ships **empty** — which is a measurement, not an aspiration.

---

## 7. Why there is no SQF arm

Not difficulty. An SQF mutator would be about as hard as the bash one. There is nowhere to run a mutant.

- SQF executes inside the Arma engine and nowhere else; SQF-VM is optional in this project's gates (`docs/research/arma-toolchain.md`), so a mutant's only verdict comes from a world.
- `just regress` is about 20 minutes end to end on three slots, and its unit is a **fresh world per probe** rather than a process. A twenty-mutant sample against one addon function is hours per module, on a machine the human also plays on and which the tier already holds single-occupancy.
- `compileFinal` closes the cheap route: the Functions Library `compileFinal`s every `cti_fnc_`, so a probe cannot stub one and a mutant cannot be swapped in at run time. It would have to go into the addon source with a `hemtt build` inside the per-mutant loop (#80 records the same constraint from the other side).

What stands in its place is not nothing: the three red-by-design probes (`schema-stale`, `daemon-restart`, `loop-watch`, #80/#96/#102) each *demand* the failure class they expect; the expected-class machinery turns a silently-changed decision into the wrong class rather than a pass; and the probe vacuity rule (#116, ADR-0016) requires a probe to assert that its staging took effect, which is the property mutation testing buys, obtained by construction instead of by sampling.

**What would overturn this.** An in-process SQF runner this project is willing to gate on — SQF-VM reaching the point where a `cti_fnc_` runs under it with the addon's own arrangement — would make a mutant cost milliseconds instead of a world, and the arithmetic above would stop applying. That is the evidence to bring.

---

## 8. Cost, end to end

`just fast` on this tree, green, with the three test modules this landing adds or rewrites in the mutation rung's scope: **111.1 s of pytest**, **130.8 s of mutation** (`test_mutation_rust.py` 8.2 s, `test_mutation_shell.py` 60.3 s, `test_mutation_smoke.py` 62.3 s), and the static tier around them.

The shell arm's own worst case is what a reader should hold on to: a landing that rewrites `tests/unit/test_run_verdict.py` pays **193.7 s**, which puts `just fast` at roughly **five minutes** — ADR-0064 decision 3's ceiling, reached rather than crossed. Two modules are therefore measured and recorded rather than enforced, each with its number in `NO_MUTABLE_SUBJECT`:

- `test_client_lock.py` — 80% (8/10), **216.6 s**, of which 112.8 s is one serial run of the module (#197's 60 s soak is in it);
- `test_pool_slots.py` — **190.8 s** for the collect pass alone, before a single mutant.

If `run.sh` migrates to Python under ADR-0049, both of those numbers and both 30% rates move together, and this section is the one to re-measure.

---

## 9. What this note does not establish

- **The shell mutator's operator set is not proven complete.** It was chosen against this corpus and validated against a four-decision fixture; a construct these nine scripts do not use has never been mutated.
- **The stage's isolation is asserted on inodes, not on a concurrent run.** `tests/unit/test_mutation_shell.py` proves a graft creates a new inode and leaves the real file's bytes alone. Nobody ran `just regress` and `just mutation` at the same time to watch it hold, because that costs a pool.
- **`cargo-mutants` was measured at one version.** Its operator set is not configured here, so an upgrade can move the verdict under a rung that requires zero survivors. `tools/mutation_rust.py` names the version it was measured against for exactly that reason.
- **The Rust rung is not in `just prereqs tools`.** That installer verifies every download against a published checksums file and `cargo-mutants` ships none, so the rung refuses by name with the pinned `cargo install` line instead. Folding it in properly is follow-up work.
