# What it takes to make mutation testing a gate rather than a habit

**Researched**: 2026-08-05
**Question** (#239): nothing mechanical stops a vacuous green test. Can mutation testing be made to run, scoped to every landing, cheap enough to sit in `just fast`, and lane-blind?
**Answer in one line**: yes, but not with an off-the-shelf mutation engine — the cost is not the mutating, it is that a general engine mutates a whole file and runs a whole suite per mutant and hands back an equivalent-mutant rate too high to set a floor against, so what lands is a bespoke bounded mutator whose operator set is chosen for precision and whose subject is chosen by coverage evidence.

---

## 0. Method and limits

Everything below was measured on this machine on 2026-08-05, against the tree at `8e0c751`, not inherited from documentation. Where a number is a single observation it says so.

The corpus sweep ran in a `--shared` clone of the repo under `/tmp`, not in an agent worktree, for one reason and it is a finding in its own right: the mutation smoke mutates the real tree in place and runs pytest against it, and this suite takes real `flock`s and binds real ports. The first sweep attempt ran beside an ordinary `uv run pytest` in another checkout and produced a spurious red in `tests/unit/test_client_lock.py` — the same collision #124 diagnosed, where a sibling `just unit` swept the tier's ports. The reading stood as a reading; the story built on it did not, and the test passes on its own.

**What this note does not establish.** Nothing here says the floor is right for a corpus this project does not yet have. It says every test module this project has today clears it, by the margin tabulated in §4.

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

The failure that reads as an xdist incompatibility is not one. mutmut copies `source_paths` into a `mutants/` tree and runs pytest there; a `source_paths` naming a single **file** leaves `cti_daemon` as a directory with one module in it, so `from cti_daemon import campaign` fails with `ImportError: cannot import name 'campaign' from 'cti_daemon' (unknown location)` and mutmut reports it as `BadTestExecutionCommandsException`, naming the argv, which is where `-n auto` is visible and gets blamed. Pointed at the package, with the trees the tests read in `also_copy`, it completed: **8 mutants on `dedupe.py`, 5 killed, 3 survived, 80.76 mutations/second**.

**What it reports cannot carry a floor.** The three survivors, verbatim from `mutmut show`:

| Mutant | Original | Mutated |
|---|---|---|
| `x__key__mutmut_4` | `blake2b(line.encode("utf-8"), digest_size=16)` | `blake2b(line.encode("utf-8"), )` |
| `x__key__mutmut_7` | `blake2b(line.encode("utf-8"), …)` | `blake2b(line.encode("UTF-8"), …)` |
| `x__key__mutmut_8` | `… digest_size=16)` | `… digest_size=17)` |

All three are **equivalent mutants**. `RequestWindow` keys on an opaque digest and never compares one to a stored constant, so no assertion can distinguish a 16-byte digest from a 17-byte one, or `"utf-8"` from `"UTF-8"`, and no test ever will. `dedupe.py` is 75 lines with a test module its author wrote first; it is about as far from a vacuous suite as this repo gets, and mutmut scores it **62.5%**.

A gate over that operator set would have to put its floor below 62.5% to keep the tree green. A vacuous suite that runs the code at all clears 62.5% comfortably — §3 shows one doing exactly that. So the floor and the threat cannot be separated, which is the whole of the objection: it is not that mutmut is wrong, it is that a mutation engine tuned for a survivor list a human reads is not tuned for a number a gate compares.

Two further mismatches, recorded because they would have to be solved as well:

- **Granularity.** mutmut's unit of work is a file and a suite. `pytest_add_cli_args` can narrow the suite by hand, but the pairing of *which mutant* with *which tests* is mutmut's own stats pass, and the gate needs it per mutant to stay inside a `just fast` budget.
- **Sampling.** "A bounded mutant sample" has no first-class expression. `mutmut run <name>` selects, but the names only exist after a full generate-and-stat pass over the file.

## 2. cosmic-ray 8.4.6: the right generality, the wrong unit of work

It installs cleanly (`uv run --with cosmic-ray`, 29 packages, SQLAlchemy among them, one observation). Its architecture is a session database, a distributed executor and resumable sweeps — built for "mutate this module overnight and let me browse the survivors". Adopting it would mean carrying a database and an executor to obtain a bounded sample this project would then have to define itself, and adding SQLAlchemy to a dependency set whose only runtime dependency today is `networkx`. Declined on that, not on any measured failure: it was not run to completion here, and this note does not claim it fails.

## 3. Why a bespoke mutator is cheap here

ADR-0049's spend-tokens-once principle asks whether the thing is small enough to own. It is: the mutator is an `ast` walk producing byte-span replacements, guarded by a `compile()` of the result, and the entire engine is under 200 lines of `tools/mutation_smoke.py`. What the project buys for that is the two things above — per-mutant test selection, and a sample it controls — plus the operator set.

**The operator set is chosen for precision, and each exclusion has a name.**

| Planted | Why it is high-signal |
|---|---|
| comparison negation (`==`↔`!=`, `<`↔`>=`, `is`↔`is not`, `in`↔`not in`) | negating a comparison that ran changes a decision that was taken |
| `and`↔`or` | ditto, on the joining |
| `not x` → `x` | ditto, on the sense |
| `True`↔`False` | a constant decision, inverted |
| numeric literal `n` → `n+1` | thresholds, offsets, sizes: the arithmetic tests exist to pin |
| `return <expr>` → `return None` | what the function hands back |

| Never planted | Why |
|---|---|
| string literals | mutmut's `"utf-8"` → `"UTF-8"`: unkillable and unavoidable |
| keyword-argument values | mutmut's `digest_size=16` → `17`: opaque configuration |
| parameter defaults | the same class, one level up |
| anything inside an f-string | a replacement in a format expression is a span this mutator has no business trusting |
| one link of a chained comparison | a mutant whose meaning cannot be stated in a report |

Each row of the second table is a regression test in `tests/unit/test_mutation_smoke.py`, named after the mutmut survivor that motivated it, because every equivalent mutant that reaches the real tree has to be paid for out of the floor.

**How the subject is chosen.** Not by the `test_x.py` → `x.py` convention: `tests/unit/test_land.py` → `tools/land.py` already only half obeys it, and a data-driven module does not obey it at all. The module is run once under `coverage.py` with `dynamic_context = test_function`, and the subject is the product file with the most lines executed **inside a test**. Import-time lines carry an empty context and do not count — which is what makes an `assert True` module subject-less rather than the accidental owner of everything `conftest.py` imported.

The sweep shows the convention would have been wrong at least once anyway: `tests/unit/test_budget.py`'s evidence-chosen subject is `src/cti_daemon/manifest.py`, not `budget.py`, because that is where its tests spend their lines.

**What the gate does and does not catch.** Stated plainly, because a gate whose limits are not written down gets trusted past them:

- An `assert True` module — the shape #239's acceptance names — is caught hard, as `no subject`.
- A module that wraps every call in `try/except Exception: pass` is caught: nothing goes red, so nothing is killed.
- A module that genuinely exercises its subject and asserts only `is not None` is caught **partially**. Measured: a purpose-built vacuous module over `economy.Ledger` — four tests, every assertion `is not None` or `in (True, False)` — scored **9/9**. Its mutants were killed by *crashes*, not by assertions: flipping `_account`'s `held is None` guard raises `UnknownSideError`, and flipping `can_afford`'s comparison makes `spend` refuse. Those are honest detections in the mutation-testing sense — the suite went red when the code changed — and this gate measures change-detection, so it counts them. It is not a vacuity oracle, and no bounded mutation smoke is.

## 4. The corpus sweep, and where the floor comes from

Every test module in `tests/unit/`, `--report`, defaults (`--cap 20`), in the isolated clone.

<!-- SWEEP TABLE -->

## 5. Cost

<!-- COST -->

## 6. What this changes

Recorded as ADR-0064. In short: `tools/mutation_smoke.py` and `just mutation`, wired into `just fast` and therefore into `tools/land.py`'s gate, which is where lane-blindness comes from — a z.ai or Codex landing runs the same rung. `mutmut` leaves the dev dependency group, and the CLAUDE.md line naming it is proposed for the human's amendment rather than edited.
