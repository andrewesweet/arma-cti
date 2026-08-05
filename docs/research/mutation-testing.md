# What it takes to make mutation testing a gate rather than a habit

**Researched**: 2026-08-05
**Question** (#239): nothing mechanical stops a vacuous green test. Can mutation testing be made to run, scoped to every landing, cheap enough to sit in `just fast`, and lane-blind?
**Answer in one line**: yes, but not with an off-the-shelf engine — a general mutation tool mutates a whole file, runs a whole suite per mutant, and reports an equivalent-mutant rate too high to set a floor against, so what lands is a bespoke bounded mutator whose operator set is chosen for precision and whose subject is chosen by coverage evidence.

---

## 0. Method and limits

Everything below was measured on this machine on 2026-08-05, against the tree at `8e0c751`. Where a number is a single observation it says so.

The corpus sweep ran in a `--shared` clone of the repo under `/tmp`, not in an agent worktree, and that is a finding rather than tidiness: the smoke mutates the real tree in place and runs pytest against it, and this suite takes real `flock`s and binds real ports. The first attempt ran beside an ordinary `uv run pytest` in another checkout and produced a spurious red in `tests/unit/test_client_lock.py` — #124's collision, where a sibling `just unit` swept the tier's ports. The reading stood; the story built on it did not, and the test passes on its own.

**What this note does not establish.** Nothing here says the floor is right for a corpus this project does not yet have. It says every test module this project has today clears it, by the margin tabulated in §6.

---

## 1. mutmut 3.6.0: it runs, and what it reports cannot be a gate

CLAUDE.md has named `mutmut` since Phase 0, "scoped to snapshot save/load and the planner". #172's close found that scope naming modules that do not exist — there is no snapshot yet — and reported that it did not run against our pytest config. Both halves were checked.

**It does run.** The configuration that works:

```toml
[tool.mutmut]
source_paths = ["src/cti_daemon"]
only_mutate = ["*/dedupe.py"]
also_copy = ["tests/", "tools/", "config/", "addons/", "pyproject.toml", "uv.lock"]
pytest_add_cli_args = ["-n0", "tests/unit/test_dedupe.py"]
```

The failure that reads as an xdist incompatibility is not one. mutmut copies `source_paths` into a `mutants/` tree and runs pytest there; a `source_paths` naming a single **file** leaves `cti_daemon` a directory with one module in it, so `from cti_daemon import campaign` fails with `ImportError: cannot import name 'campaign' from 'cti_daemon' (unknown location)`, and mutmut reports that as `BadTestExecutionCommandsException` printing the whole argv — which is where `-n auto` is visible and gets the blame. Pointed at the package, with the trees the tests read in `also_copy`, it completed: **8 mutants on `dedupe.py`, 5 killed, 3 survived, 80.76 mutations/second**.

**What it reports cannot carry a floor.** The three survivors, verbatim from `mutmut show`:

| Mutant | Original | Mutated |
|---|---|---|
| `x__key__mutmut_4` | `blake2b(line.encode("utf-8"), digest_size=16)` | `blake2b(line.encode("utf-8"), )` |
| `x__key__mutmut_7` | `blake2b(line.encode("utf-8"), …)` | `blake2b(line.encode("UTF-8"), …)` |
| `x__key__mutmut_8` | `… digest_size=16)` | `… digest_size=17)` |

All three are **equivalent mutants**. `Answered` keys on an opaque digest and never compares one to a stored constant, so no assertion can distinguish a 16-byte digest from a 17-byte one, or `"utf-8"` from `"UTF-8"`. `dedupe.py` is 75 lines with a test module its author wrote first; it is about as far from a vacuous suite as this repo gets, and mutmut scores it **62.5%**.

A gate over that operator set would have to put its floor below 62.5% to keep the tree green. §5 measures a deliberately weak module at 30% and a vacuous one at no-subject, so the separation is not hopeless — but the margin would be eaten entirely by noise the tool generates and the project cannot fix. That is the objection: not that mutmut is wrong, but that an engine tuned for a survivor list a human reads is not tuned for a number a gate compares.

Two further mismatches, recorded because they would have to be solved as well:

- **Granularity.** mutmut's unit of work is a file and a suite. `pytest_add_cli_args` narrows the suite by hand, but pairing *which mutant* with *which tests* is mutmut's own stats pass, and this gate needs it per mutant to stay inside a `just fast` budget.
- **Sampling.** "A bounded mutant sample" has no first-class expression; `mutmut run <name>` selects, but the names exist only after a full generate-and-stat pass over the file.

## 2. cosmic-ray 8.4.6: the right generality, the wrong unit of work

It installs cleanly (`uv run --with cosmic-ray`, 29 packages, SQLAlchemy among them; one observation). Its architecture is a session database, a distributed executor and resumable sweeps — built for "mutate this module overnight and let me browse the survivors". Adopting it would mean carrying a database and an executor to obtain a bounded sample this project would still have to define, and adding SQLAlchemy to a project whose only runtime dependency is `networkx`. Declined on that, not on any measured failure: it was not run to completion here, and this note does not claim it fails.

## 3. What a bespoke mutator buys, and what it costs to own

ADR-0049's spend-tokens-once principle asks whether the thing is small enough to own. It is: an `ast` walk producing byte-span replacements, guarded by a `compile()` of the result. What the project buys is per-mutant test selection, a sample it controls, and the operator set.

**Operators are chosen for precision, and every exclusion has a name.**

| Planted | Why it is high-signal |
|---|---|
| comparison negation (`==`↔`!=`, `<`↔`>=`, `is`↔`is not`, `in`↔`not in`) | negating a comparison that ran changes a decision that was taken |
| comparison **boundary shift** (`>`→`>=`, `<=`→`<`, …) | the edge case, which is the one weak assertions miss — see below |
| `and`↔`or` | the joining |
| `not x` → `x` | the sense |
| `True`↔`False` | a constant decision, inverted |
| numeric literal `n` → `n+1` | thresholds, offsets, sizes |
| `return <expr>` → `return None` | what the function hands back |

| Never planted | Why |
|---|---|
| string literals | mutmut's `"utf-8"` → `"UTF-8"`: unkillable and unavoidable |
| keyword-argument values | mutmut's `digest_size=16` → `17`: opaque configuration |
| parameter defaults | the same class, one level up |
| anything inside an f-string | a replacement in a format expression is a span this mutator has no business trusting |
| one link of a chained comparison | a mutant whose meaning cannot be stated in a report |

Every row of the second table is a regression test in `tests/unit/test_mutation_smoke.py`, named after the mutmut survivor that motivated it, because every equivalent mutant that reaches the real tree has to be paid for out of the floor.

**The boundary shift is not decoration.** Negation alone was measured and found blunt: on `dedupe.py`, `while len(self._answers) > self.window` negated becomes `<=`, which pops from an empty `OrderedDict` and raises, so *any* suite that runs the line kills it. A deliberately weak module over that class scored 5/5. The shift to `>=` leaves the code running and moves the edge by one, which only a test that pinned the edge notices. With it, the same weak module's rate falls — and the throwaway subject in §5 separates 100% from 30%.

**How the subject is chosen.** Not by the `test_x.py` → `x.py` convention: `tests/unit/test_land.py` → `tools/land.py` already only half obeys it, and the sweep found `tests/unit/test_budget.py` spending most of its lines in `manifest.py` rather than `budget.py`. The module is run once under `coverage.py` with `dynamic_context = test_function`, and the subject is the product file with the most lines executed **inside a test**. Import-time lines carry an empty context and do not count — which is what makes an `assert True` module subject-less rather than the accidental owner of everything `tests/unit/conftest.py` imported.

## 4. Three bugs that made the gate score everything 100%, and how they were caught

All three are worth writing down, because each is invisible from inside a green run and each would have shipped a gate that could not fail.

**A coverage context is not a pytest node id.** `dynamic_context = test_function` names a test by its *importable* name — `test_dedupe.test_a_window_can_be_filled` — while pytest selects by path and `::`. Handed the coverage spelling, pytest exits **4**, "file or directory not found". The first draft read any non-zero exit as "the tests noticed", so every mutant was killed by a run that never happened, and the first corpus sweep came back 100% on 47 of 50 modules. The durable half of the fix is not the conversion but the reading: only exit 0 (survived), exit 1 (killed) and a timeout (killed) are verdicts, and every other code is a refusal — CLAUDE.md's #41 rule, that a check which could not run is not a check that passed.

It was caught by asking a question the passing tests could not answer: *which tests does this mutant actually run?* The printed answer was `test_zz_weak_dedupe.test_a_window_can_be_filled`, which is not a node id. `tests/unit/test_mutation_smoke.py` now carries the end-to-end that would have caught it — a weak module that must be **red** — because a suite in which nothing can survive passes every "sound module is green" test ever written.

**A coverage context is not always a test at all.** `dynamic_context = test_function` names *any* function called `test_function`, and `hypothesis` has one: `hypothesis.internal.conjecture.engine.ConjectureRunner.test_function`. Every module in this repo that uses hypothesis therefore recorded a context that converts to a node id pytest cannot select — the same exit 4 as above, now correctly a refusal rather than a kill, so `tests/unit/test_loadouts.py` could not be judged at all. Requiring the module's own name as the context's first part is exact, because `dynamic_context` always writes `module.qualname`. The five affected modules then scored 100%, 100%, 100%, 100% and 80%.

**Two mutants of the same length in the same second share a bytecode cache.** After the first fix the gate flaked: 13/20, 13/20, 12/20 over an unchanged tree. CPython validates a cached `.pyc` against its source's mtime in **whole seconds** and its size in **bytes**, and the two mutants this gate plants on one comparison are the negation and the shift — `(missing < 0)` and `(missing > 0)`, identical length, same file, same second. The second run imported the first one's bytecode. The two survivors that moved between runs were exactly such a pair.

Reproduction baseline, per CLAUDE.md's flake rule: **pre-fix, 5 runs of `--paths tests/unit/test_economy.py` gave 13/20, 13/20, 12/20, 13/20, 14/20; post-fix, 3 runs gave 14/20 three times, and 3 runs of `test_economy.py` + `test_campaign.py` together gave 14/20 and 14/20 every time.** A private `PYTHONPYCACHEPREFIX` per mutant also fixes it and was measured first: correct, and 10 s → 38 s per module in recompiles. Stepping the file's mtime two seconds forward on every write costs nothing.

## 5. Separation: what a sound, a weak and a vacuous module score

Against one throwaway subject with three decisions in it, built in `tmp_path` by `tests/unit/test_mutation_smoke.py` and run as part of `just unit`:

| Test module | Kill rate | What it asserts |
|---|---:|---|
| sound | **100%** (10/10) | exact prices, including at and either side of the threshold |
| weak | **30%** (3/10) | only `is not None` and `isinstance(..., int)` |
| vacuous | **no subject** | `assert True` and `1 + 1 == 2` |

The seven survivors of the weak module are the whole boundary and arithmetic of the subject: the threshold constant, the comparison, its boundary, the `and`, the `not`, and both return arithmetic constants. That is the gate working as intended.

## 6. The corpus sweep, and where the floor comes from

Every test module in `tests/unit/`, `--report`, defaults (`--cap 20`), in the isolated clone. **68 modules, all of them.**

| | |
|---|---|
| judged against a Python subject | 56 |
| exempt, subject is shell or a document (`NO_PYTHON_SUBJECT`) | 11 |
| no decision to plant on the lines reached (`telemetry.py`) | 1 |
| **lowest kill rate** | **62%** (`test_budget.py` → `budget.py`) |
| median | 85% |
| at 100% | 16 |
| total wall | 1,039 s over 66 measured modules; mean 15.7 s |
| slowest module | 188.1 s (`test_pool_slots.py`, whose whole cost is its own coverage pass) |

Distribution, kill rate → modules: 62→1, 65→2, 67→1, 69→1, 70→5, 72→1, 75→5, 80→8, 83→1, 85→4, 90→5, 92→2, 95→4, 100→16.

The eleven below 75% are not a finding about the gate; they are a finding about the corpus, and a fair one. Six of them are the `test_daemon_*` family sharing `daemon.py`, each asserting about its own slice and traversing the rest; the survivors they leave are real gaps — a wire-limit constant nothing pins, a `1_000` nothing checks, an `isinstance(claimed, str) and claimed` whose second half no test exercises. None of that is this issue's to fix.

**Where the floor comes from.** 50%, which is 12 points below the weakest module in the tree and 20 above the deliberately weak module of §5. It is deliberately below what most modules already reach: a gate whose first act is to red a tree it did not write is exactly #137/#186's false red, and the way this number goes up is by strengthening the modules under it — never by a landing lowering it. #244 proposes the ratchet that would replace one global number with each module's own recorded rate.

**Eleven exemptions is a lot, and it is a fact about this repo.** Ten of the eleven are test modules whose subject is `spike/*.sh` — the tier lock, the host guard, the slot pool, the verdict typing, probe selection — driven as shell and asserted by exit code and output. The eleventh reads two documents. That is a real shape here, not an escape being abused, and the list is greppable in one file so it stays checkable.

## 7. Cost

| | |
|---|---|
| one module, mean over the 66 measured | **15.7 s** |
| this landing's own module (`test_mutation_smoke.py` → `tools/mutation_smoke.py`, 178 planted, 20 run) | **36.2 s** |
| slowest in the corpus | 188.1 s (`test_pool_slots.py`, essentially all of it that module's own coverage pass) |
| a landing that adds or rewrites no test module | **0 s** — the recipe says so and exits |

The rung costs `just fast` nothing on a landing that touches no test module, and of order fifteen seconds per module that it does. Against #197's budget — `just fast` at about 2 min 10 s, under a five-minute prompt-cache cliff — a landing adding three test modules pays about 45 s and stays well inside it. The per-module `BUDGET_S` of 90 s is what bounds the tail rather than the mean.

## 8. What the gate does not catch

Stated plainly, because a gate whose limits are unwritten gets trusted past them.

- **It measures change-detection, not assertion quality.** A mutant that makes the subject *crash* is killed by any test that runs the line. That is an honest detection in the mutation-testing sense — the suite went red when the code changed — and it is counted. It means a module that exercises a subject full of guards and asserts only `is not None` can score higher than its assertions deserve. Measured: a purpose-built weak module over `economy.Ledger` scored 9/9 under the negation-only operator set, because flipping `_account`'s `held is None` guard raises and flipping `can_afford`'s comparison makes `spend` refuse. The boundary shift narrows this; it does not close it.
- **The subject is one file.** A test module spending most of its lines in shared arrangement gets that arrangement as its subject — `tests/unit/test_budget.py` → `manifest.py`. The verdict is still a real one about tests that really run those lines; it is just not the file the module's name suggests.
- **It is a bounded sample.** Twenty mutants out of, in one case, 199. A landing can be unlucky; it cannot be unlucky *repeatably*, because the sample is seeded from the test module's path.

## 9. What this changes

Recorded as ADR-0064. `tools/mutation_smoke.py` and `just mutation`, wired into `just fast` and therefore into `tools/land.py`'s gate, which is where lane-blindness comes from — a z.ai or Codex landing runs the same rung. `mutmut` leaves the dev dependency group, and the CLAUDE.md line naming it is proposed for the human's amendment rather than edited.
