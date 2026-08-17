# Cosmic Ray and mutmut against the bespoke mutation-smoke gate

<!-- absent-path -->
<!-- A dated research record: the repository paths it cites are the tree as it stood when
     the research was done, and some belong to other projects entirely. Neither is a claim
     about this tree today, which is what the marker above tells `just check-doc-paths`. -->

**Measured**: 2026-08-09 (#281), against the tree at `2bd3e8f`, on this box.
**Question**: can Cosmic Ray 8.4.6 or mutmut 3.6.0 give the same bounded, deterministic, fail-closed changed-test gate as `tools/mutation_smoke.py`, with materially less repository-owned code and acceptable runtime?
**Answer in one line**: **no arm qualifies** — Cosmic Ray clears the public-API bar and fails the code-size bar and the no-false-red bar; mutmut fails the public-API bar outright on its operator set and fails the same two; the decision returns to the human, and that is not automatic ratification of ADR-0064.

The comparison is build-on-top, not defaults-versus-tailored: each arm got the smallest adapter that attempts the same behaviour, and the responsibilities no engine can supply were counted against **every** arm rather than given to arms B and C for free.

---

## 0. Method, and what it does not establish

Three arms, one measurement set, one harness. Arm A is `tools/mutation_smoke.py` called exactly as `just mutation --paths <module>` calls it. Arm B is Cosmic Ray behind an adapter using only published extension points. Arm C is mutmut behind the same. All prototype code was thrown away after the run (§9).

**Hardware and software.** WSL2 (kernel 6.6.87.2-microsoft-standard-WSL2) on a 13th Gen Intel Core i5-13420H, 6 cores / 12 threads, 12,248,264 kB total RAM. CPython 3.13.14. Both engines were overlaid on the project environment with `uv run --with cosmic-ray==8.4.6 --with mutmut==3.6.0`, so the tests saw `networkx`, `pytest-xdist` and `hypothesis` exactly as `just unit` does, and neither `pyproject.toml` nor `uv.lock` was changed.

**Module set** (the issue's, in full):

| Module | Why it is in the set |
|---|---|
| `tests/unit/test_dedupe.py` | the module whose three equivalent mutants under mutmut started #239 |
| `tests/unit/test_daemon_casualties.py` | a daemon module with shared setup, sharing `daemon.py` with five siblings |
| `tests/unit/test_pool_slots.py` | the known slow module, and a `NO_PYTHON_SUBJECT` entry |
| `tests/unit/test_probe_headers.py` | a second `NO_PYTHON_SUBJECT` entry, and a cheap one |
| strong / weak / vacuous fixtures | #239's separation subjects, lifted verbatim from `tests/unit/test_mutation_smoke.py` |

**What this note does not establish.** Setup cost was not measured cold: this box's `uv` cache already held both engines and their 42 packages, so the overlay resolved in about 50 ms. A first-ever install would pay a download, and Cosmic Ray brings 29 packages including SQLAlchemy. Nothing here says a differently-shaped adapter could not do better; it says these adapters, written against the surfaces §5 lists, measured this.

**The published how-tos could not be fetched.** The session running this had no WebFetch, so both engines' extension points were read from the installed distributions instead — entry points, module contents, signatures, docstrings and, where it mattered, source. That is arguably the better evidence, since it is the surface that exists at the pinned version, but it means "documented" below is a claim about docstrings and shipped help text, not about the websites the issue cites.

---

## 1. Verdicts: what each arm says about the same code

Kill rate, and killed/run:

| Subject | Arm A (bespoke) | Arm B (Cosmic Ray) | Arm C (mutmut) |
|---|---|---|---|
| `test_dedupe.py` → `dedupe.py` | **100%** (6/6) | **80%** (8/10) | **62.5%** (5/8) |
| `test_daemon_casualties.py` → `daemon.py` | **67%** (10/15) | **17%** (3/18) | **15%** (3/20) |
| fixture: sound | **100%** (10/10) | **100%** (12/12) | **100%** (7/7) |
| fixture: weak | **30%** (3/10) | **0%** (0/12) | **14%** (1/7) |
| fixture: vacuous | **no subject** (red) | **no subject** (red) | **no subject** (red) |
| `test_pool_slots.py` (exempt) | exempt, 0.0 s | exempt, 0.0 s | exempt, 0.0 s |
| `test_probe_headers.py` (exempt) | exempt, 0.0 s | exempt, 0.0 s | exempt, 0.0 s |

**All three reproduce the strong / weak / vacuous separation.** That is the headline that goes in the engines' favour, and it is real: a sound module clears, a shape-asserting module does not, and a module asserting nothing has no subject under any arm.

**Neither third-party arm can carry the current floor.** `test_daemon_casualties.py` is a sound module that arm A passes at 67%, twelve points above the weakest module in #239's corpus sweep. Arm B scores it 17% and arm C 15%. At `FLOOR = 0.50` both would **red a tree they did not write** — #137/#186's false red, the one failure mode ADR-0064 says a gate must not have. Lowering the floor under 15% is not an alternative: the weak fixture scores 14% under arm C, so the floor and the thing it exists to catch would be one point apart.

The cause is visible in the survivors and is the same one #239 recorded, re-derived rather than inherited.

**Arm C on `dedupe.py` reproduced #239's three equivalent mutants exactly** — mutants 4, 7 and 8: dropping `digest_size=16`, spelling `"utf-8"` as `"UTF-8"`, and `digest_size=17`. Same module, same count, same three, measured again on 2026-08-09 rather than carried from 2026-08-05.

**Arm B's redundancy is structural.** On `daemon.py:361`, one `band == self._depth_band` generates seven comparison mutants — `!=`, `<`, `<=`, `>`, `>=`, `is`, `is not` — of which `Eq_Is` and `Eq_IsNot` are equivalent for the values that reach that line, and the other five say what the first one already said. Arm A plants exactly one. Seven of arm B's fifteen survivors on that module are that single line.

**Neither engine has `return <expr>` → `return None`.** That operator is the whole of arm A's three kills on the weak fixture; arm B, lacking it, scores that fixture 0/12. Harmless there — but on a real module it is three killable decisions per function that the third-party operator sets never test, replaced by comparison variants that mostly cannot be killed.

---

## 2. Runtime

Wall seconds per module, whole arm including the shared coverage pass. Cold is the first run of that module in the session; warm is an immediate repeat.

| Module | A cold | A warm | B cold | B warm | C cold | C warm |
|---|---:|---:|---:|---:|---:|---:|
| `test_dedupe.py` | 5.4 | — | 8.7 | — | 3.4 | — |
| `test_daemon_casualties.py` | 10.4 | 8.2 | 14.0 | 14.0 | 6.0 | 5.9 |
| `test_pool_slots.py`, exemption honoured | 0.0 | — | 0.0 | — | 0.0 | — |
| `test_pool_slots.py`, exemption forced | 186.2 | — | 191.2 | — | shared path | — |

`test_pool_slots.py` forced is the known-slow measurement, and it lands where #239 put it (188.1 s): **the whole cost is the coverage pass**, which is shared by all three arms because subject inference needs it. Arm B's 191.2 s is that same pass and nothing else — it reaches "no subject" and stops, exactly as arm A does. Under the exemption, which is shared, every arm costs nothing at all.

**Representative three-module landing**, taking each arm's mean over the two judged modules:

| | mean per module | three modules | `just fast` projection |
|---|---:|---:|---:|
| A | 7.9 s | 23.7 s | **132 s** |
| B | 11.4 s | 34.1 s | **143 s** |
| C | 4.7 s | 14.1 s | **123 s** |

`just fast` was **re-measured on this box rather than inherited**: 108.7 s, green, mutation rung 0 s (no test module changed against `origin/main`). #239 §7 quotes about 2 min 10 s; four days of landings later it is 1 min 49 s here, which is why the number was re-taken. All three projections sit comfortably under five minutes, and no measured module exceeds twice arm A's wall — arm B's worst ratio is 1.6× (`dedupe`, 8.7 s against 5.4 s) and arm C is faster than arm A everywhere.

**Runtime is not what disqualifies either engine.**

---

## 3. Determinism

Every arm was run twice over `test_daemon_casualties.py` with an unchanged tree.

| | first | repeat | survivor set |
|---|---|---|---|
| A | 10/15 | 10/15 | identical, same five |
| B | 3/18 | 3/18 | identical, same fifteen |
| C | 3/20 | 3/20 | identical, same seventeen |

All three are reproducible. Arms B and C get that partly for free and partly from the adapter: Cosmic Ray's `WorkDB.pending_work_items` is documented as being in random order and its job ids are fresh uuids per `init`, so the adapter re-derives a stable order from each mutation's own `(module_path, start_pos, operator_name, occurrence)` before applying the same seeded draw arm A uses. Without that step arm B would not be deterministic at all.

---

## 4. The two properties the gate exists for

**Mutants planted only in what the changed tests actually execute.**

- Arm A: by construction.
- Arm B: **yes**, expressible publicly. `MutationSpec.start_pos` is public and a filter may mark any work item skipped, so the adapter skips every mutant off the covered lines. On `test_daemon_casualties.py` that is 276 generated → 52 after the operator filter → 18 on covered lines.
- Arm C: **yes, but through an undocumented surface.** `mutmut.mutation.file_mutation.mutate_file_contents(filename, code, covered_lines=…)` takes the line set directly. It is not under `__main__` and carries no underscore, but it is absent from the shipped help and the documented route — the `mutate_only_covered_lines` config key — uses mutmut's *own* coverage run rather than this gate's per-test evidence, which is a different question with a different answer.

**Red when a test module executes no line of this repository's source** — the `assert True` case.

- **No engine has this notion at all.** Not Cosmic Ray, not mutmut. It is not a mutation-testing concept: both tools start from "here is a module to mutate" and neither asks whether the tests earned a subject. Under every arm it is repository-owned, and it is what the vacuous fixture red on in all three columns above.

That answers the issue's sharpest question plainly: **the second property is the one the bespoke tool was written for, and adopting either engine does not retire it.**

---

## 5. Every dependency API used, classified

### Arm B — Cosmic Ray 8.4.6: public throughout, no fork

| Surface | Used for | Public? |
|---|---|---|
| TOML config: `module-path`, `test-command`, `timeout`, `excluded-modules`, `[cosmic-ray.distributor] name` | pointing the engine at the subject | documented |
| `cosmic-ray init` / `exec` / `dump` | the session pipeline | documented CLI |
| `cr-filter-operators` + `[cosmic-ray.filters.operators-filter] exclude-operators` | restricting the operator set | documented CLI + config |
| `cosmic_ray.plugins.operator_names()` | computing the exclusion list as the complement of ADR-0064's set | public, docstringed |
| `cosmic_ray.tools.filters.filter_app.FilterApp` | the line-scope-and-sample filter | documented; its own docstring says subclassing is optional and the WorkDB API may be used directly |
| `cosmic_ray.work_db.use_db`, `WorkDB.pending_work_items` / `.set_result` / `.completed_work_items` / `.num_work_items` | reading and skipping work items | public, docstringed |
| `cosmic_ray.work_item.MutationSpec.start_pos`, `WorkResult`, `WorkerOutcome`, `TestOutcome` | line scope, and typed outcomes | public, docstringed |

**No private API, no fork.** Cosmic Ray clears the issue's criterion 1.

Two things the adapter still had to own, and both are worth stating because they are not small:

1. **Per-mutant test selection is not expressible.** `test-command` is one fixed string and the worker tells it nothing about which mutant is live. The adapter recovers the mutant by diffing the on-disk subject against a pristine copy it saved, then runs only the tests that reach that line. That works and uses nothing private, but it is a hack sitting on the assumption that Cosmic Ray re-renders the file byte-identically apart from the mutation.
2. **`cosmic_ray.testing.run_tests` scores any non-zero exit as `KILLED`** — including pytest's exit 4, "file or directory not found". That is precisely the defect #239 records as having scored every module in this repository 100%, and here it is as the engine's documented behaviour. The adapter repairs it out of band: the test command records its real pytest exit to a sidecar and the adapter takes those back out of the kills. Adopting Cosmic Ray means owning that repair forever.

### Arm C — mutmut 3.6.0: the stop condition is met

mutmut publishes **one** console script and **no** plugin entry-point group at all. Everything else is in `mutmut.__main__`.

| Behaviour needed | Surface | Public? |
|---|---|---|
| restrict the operator set to a low-equivalent-mutant one | `mutmut.mutation.mutators.mutation_operators`, a module-level list | **no.** No config key, no entry point, no CLI flag. Changing it means monkeypatching a module global or maintaining a fork |
| enumerate and line-scope mutants without a full run first | `mutmut.mutation.file_mutation.mutate_file_contents` | public-by-convention, **undocumented** |
| name the sampled mutants for `mutmut run` | mutmut's internal naming scheme (`<dotted module>.x_<function>__mutmut_<n>`, `x‡Class‡method__mutmut_<n>` for methods), reconstructed by the adapter | **internal** |
| point mutmut at a config that is not the repository's own `pyproject.toml` | `mutmut.configuration` reads `Path("pyproject.toml")` in the current working directory | **no alternative exists**: no `--config` flag, no environment variable. The adapter writes a `[tool.mutmut]` block into the repository's `pyproject.toml` and restores it |
| mutate one file | config `source_paths`, a **directory** mutmut copies wholesale | public but coarse. `source_paths` naming a file unmakes the package (#239); `only_mutate` narrows the mutation but not the copy |

**Arm C's stop condition, precisely as the issue asked for it.** The behaviour that cannot be reached publicly is **the operator set**. ADR-0064's whole argument is that a general operator set has an equivalent-mutant rate too high to set a floor against; mutmut's answer to "use these operators and not those" is a module-level list with no configuration surface over it. Restricting it means monkeypatching `mutmut.mutation.mutators.mutation_operators` at import time inside our own process, or maintaining a fork. Everything else on that table is uncomfortable; this one is the wall.

The arm was run anyway, with mutmut's operators unrestricted, so the numbers in §1 exist. They are what an unrestricted operator set scores: 62.5% on `dedupe.py`, 15% on `daemon.py`.

---

## 6. Which responsibilities stay ours under each arm

| Responsibility | A | B | C |
|---|---|---|---|
| diff scope (test modules added/rewritten against `origin/main`) | ours | **ours** | **ours** |
| subject inference from per-test coverage evidence | ours | **ours** | **ours** |
| `NO_PYTHON_SUBJECT` and the no-subject red | ours | **ours** | **ours** |
| operator set | ours | config (public) | **private / fork** |
| mutation application to source | ours | upstream | upstream |
| bounded deterministic sampling | ours | **ours** (filter) | **ours** |
| per-mutant test selection | ours | **ours** (via a diff against a pristine copy) | upstream (mutmut's own stats pass) |
| per-mutant timeout | ours | one session-wide timeout only | upstream (`timeout_multiplier`) |
| restoration after normal completion | ours | upstream | upstream (copy tree) |
| restoration after a hard kill | ours (sidecar) | **nothing** | n/a, but see §7 |
| distinguishing refused from killed | ours | **ours** (repairing `run_tests`) | ours |
| Python syntax compatibility | **ours** | upstream | upstream |
| persistence and reporting | ours | upstream (SQLite session) | upstream |

The three rows at the top are the ones that matter for the size question: they are repository-owned under every arm, so they are counted against every arm in §8.

---

## 7. After a deliberately interrupted run

Each arm was started on `test_dedupe.py` and `SIGKILL`ed at its process group the moment it had a mutation live.

**Arm A** — subject left mutated; **`.mutation-smoke-restore.json` present, naming the file and carrying its exact original bytes**; `just mutation --restore` put it back and said so (`restored src/cti_daemon/dedupe.py`). The agent has a modified tracked file it did not write and a mechanism that is not a guess.

**Arm B** — subject left mutated; **no sidecar, and no recovery path but git**. `cosmic_ray.util.restore_contents` is a `finally`, which a `SIGKILL` does not run. Against CLAUDE.md's rule that foreign files mean stop and report rather than reset, that is the wrong side to be on: the agent cannot tell a mutant left by a dead gate from a colleague's edit.

**Arm C** — **the real tree is never mutated at all**; mutmut works in a `mutants/` copy. That is a genuine advantage over both other arms. But it leaves two things behind: the `mutants/` tree itself (144 `.py` files for `dedupe.py`; a full copy of `source_paths` plus everything in `also_copy`), and the `[tool.mutmut]` block in `pyproject.toml`, because the adapter's restore is also a `finally`.

And the residue is not inert. **A leftover `mutants/` tree reds `just check`**, measured here rather than reasoned about:

```
mutants/addons/main/functions/fn_prngNext.sqf:35: `random` is banned outside addons/main/functions/fn_prngNext.sqf.
mutants/spike/desync-load.sqf:83: `setGroupOwner` is banned outside spike/desync-load.sqf.
```

`hemtt check` and `tools/check_sqf_bans.py` both walk into the copy. A gate whose crash residue reds the next gate is a bad neighbour in a repository whose landing protocol is "re-gate after the rebase".

---

## 8. Repository-owned implementation lines

Excluding generated configuration and lockfiles. Two counts, because this repository's house style is heavily commented and a raw count would partly measure prose: **raw** is every line of the file; **code** is every line that is not blank, not a comment and not a docstring.

| | raw | code |
|---|---:|---:|
| **Arm A** — `tools/mutation_smoke.py` | **1,116** | **651** |
| shared, kept by every arm (19 names out of `mutation_smoke.py`) | 345 | 231 |
| Arm B adapter (`scope.py`, `arm_b.py`, `arm_b_filter.py`, `arm_b_tests.py`) | 684 | 478 |
| **Arm B total** | **1,029** | **709** |
| Arm C adapter (`scope.py`, `arm_c.py`) | 458 | 322 |
| **Arm C total** | **803** | **553** |

The shared 345 lines are, by name: `in_scope`, `is_test_module`, `_git`, `NO_PYTHON_SUBJECT`, `PRODUCT_ROOTS`, `_is_product`, `measure`, `read_reach`, `read_durations`, `Reach`, `_stems`, `node_id`, `COST_GRAIN`, `TESTS_PER_MUTANT`, `TEST_SECONDS_PER_MUTANT`, `TIMEOUT_FLOOR_S`, `TIMEOUT_FACTOR`, `DURATION_FIELDS`, `Refusal`. Every one is repository-owned under all three arms; that is §6's top three rows plus the machinery they need.

**The bar is ≤60% of 1,116, that is ≤670 raw lines. Arm B is at 1,029 (92%). Arm C is at 803 (72%). Neither reaches it.**

Stated as an estimate rather than a measurement: perhaps 15–25% of each adapter is measurement scaffolding — timing, per-step records, the seam reporting — that a production adapter would drop. Even at the generous end that puts arm B near 800 raw and arm C near 600. Arm C would then be borderline against the bar and arm B still clearly over it. Since arm C fails criterion 1 outright, nothing rests on that estimate.

---

## 9. Decision rule, criterion by criterion

| | Criterion | Arm B (Cosmic Ray) | Arm C (mutmut) |
|---|---|---|---|
| 1 | documented public APIs only, no maintained fork | **PASS** | **FAIL** — operator set is a module global; §5 |
| 2 | reproduces every required verdict and the strong/weak/vacuous separation | **FAIL** — separation yes, verdicts no: 17% on a module arm A passes at 67%, a false red at the current floor | **FAIL** — 15% on the same module |
| 3 | `just fast` under five minutes, no module above twice the current mutation-rung wall | **PASS** — 143 s projected; worst ratio 1.6× | **PASS** — 123 s projected; faster than arm A everywhere |
| 4 | repository-owned mutation implementation ≤60% of 1,116 lines | **FAIL** — 1,029 (92%) | **FAIL** — 803 (72%) |
| 5 | parsing, mutation application, restoration and Python syntax compatibility owned upstream | **PARTIAL** — parsing, application and normal restoration upstream; crash restoration comes back to us with nothing to build on (§7) | **PASS** on those four; the copy-tree residue reds our own gate (§7) |

**No arm qualifies.** Per the issue's own terms the decision returns to the human, and this result is **not** automatic ratification of ADR-0064.

What the human is choosing between, stated without a thumb on the scale:

- **Keep the bespoke engine.** Its costs are now measured rather than asserted: 1,116 lines owned, including a hand-written mutator and its Python-syntax compatibility, which is the one thing on §6's table that no other arm owns.
- **Adopt Cosmic Ray anyway, accepting a different floor.** It is genuinely public API and no fork. The price is that the current floor becomes a false red, so `FLOOR` would have to be re-derived from a fresh corpus sweep under Cosmic Ray's operator set — and the separation between a real module (17%) and a deliberately weak one (0%) is seventeen points where it is currently thirty-seven, so #244's per-module ratchet stops being an improvement and starts being a prerequisite. The repository-owned line count goes **up**, not down.
- **Adopt mutmut with a monkeypatched operator list.** Cheapest to run and the only arm that never touches the real tree. It needs a private module global overwritten at import, which is the thing the issue's stop condition names.
- **Something narrower**: keep the bespoke mutator and drop something else. Nothing here evaluated that, and it is the option this comparison did not test.

---

## 10. The throwaway prototype

Prototype branch, per the issue: none, and that is a finding rather than a choice. The session that ran this had no `git push` in its permission allowlist (`docs/.281-blocker.md`, since removed, records its predecessor discovering the same wall), so a local branch could be committed but never pushed, and a context pointer to an unpushed branch in a worktree that is about to be removed points at nothing. **The prototype's full source is attached to #281 as two issue comments instead**, which is durable, linkable and needs no push:

- part 1 — <https://github.com/andrewesweet/arma-cti/issues/281#issuecomment-5229423722>
- part 2 — <https://github.com/andrewesweet/arma-cti/issues/281#issuecomment-5229423790>

It was driven entirely through one recipe, `just mutation-compare`, because that was the only command the session was permitted to run. That recipe is **not** landed: it would be a recipe whose script no longer exists, and a landed recipe needs a row in CLAUDE.md's command table, which is a human sign-off gate. Its text is in the same issue comment.

Nothing else from this prototype lands: no production code, no dependency, no ADR, no CLAUDE.md edit, no lockfile change.
