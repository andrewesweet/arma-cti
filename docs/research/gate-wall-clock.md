# Reducing the verification gate's wall clock

Status: landed investigation. This record landed through #450; its adopted recommendations landed through #442 (`--dist worksteal`) and #446 (gate-duration recording, anchor/reporting and changelog fragment). #442 and #446 cite this record. #447 remains open but does not cite it. This document itself changes no gate.

**Revised 2026-08-20** after the adversarial review on #442 (`d-20260820-044246-a8b21d`,
opus/high). Corrections applied here: the headline ratio is a range rather than a number (§1.4),
the module-dating regression attribution is withdrawn (§2), the savings model lost its false
precision (§3.1), the causal claim is restated as "never rebalances" rather than "smaller
blocks" (§1.4), the load range in §1 and §7 was understated against the document's own §3.1a,
and every wall figure is labelled by clock. What each correction replaced is stated in place
rather than deleted silently.

Investigated 2026-08-20 against `70c6070` in an independent worktree. Every number below
was taken on this box during that session, and each run states the machine load it ran
under. Where a figure is inherited rather than measured here it says so.

**Outcome first.** The gate's Python tier does not need to lose a single assertion to run
substantially faster. `pytest-xdist`'s default `--dist load` scheduler **never rebalances**:
once a test index is assigned to a worker there is no path back, so the wall clock is set by the
unluckiest worker's assigned share, and that share is a consecutive block of the collection
chosen before any timing exists. The block is a fixed fraction of the test **count**, and this
suite's count has grown 2.4x since 2026-08-05. Switching to `--dist worksteal` took the full
suite from 209.7 s to 77.7 s with the same 5,022 tests passing — **roughly 1.6x to 2.7x
depending on box load**, the low end from the one interleaved round that controlled for load and
the high end from the cleanest same-tree pairing. The saving is of the order of ten to twenty
hours over fifteen days, bounded above by the fact that the change moves no CPU work.

Two things the first draft of this document got wrong, corrected below and worth stating here
because they are the parts most likely to be quoted: block size is **not** the mechanism
(`worksteal`'s initial block is four times *larger*), and "test work grew 11%" was an artefact of
dating modules rather than tests. Measured against serial wall at both dates, work grew **1.23x**
while the test count grew 2.43x and the shipped scheduler's wall grew 2.27x.

## 0. A blocking finding that is not about wall clock

`~/.gitconfig` — a symlink to `~/ghq/github.com/andrewesweet/setup/macos-dev/git/.gitconfig` —
gained an uncommitted stanza at **2026-08-20 03:25:02 BST**:

```
[rerere]
	enabled = true.
```

The trailing full stop makes the value unparseable as a git boolean. `git commit` writes the
commit object and *then* exits 128 with `fatal: bad boolean config value 'true.' for
'rerere.enabled'`, so interactive commits look like failures that in fact landed, and every
test that shells out to `git commit` under `check=True` fails.

Measured effect on the gate at `70c6070`: **306 failed, 4,639 passed, 77 errors** across
`test_dispatch_review.py` (88), `test_dispatch.py` (78), `test_land.py` (50), `test_worktree.py`
(24), `test_dispatch_seat.py` (22), `test_review_exchange.py` (20), `test_discard.py` (20),
`test_ledger.py` (17) and nine other modules. With the stanza corrected in a private copy and
nothing else changed, the same tree is **5,022 passed**. The correction is deleting one
character.

This is out of scope for the wall-clock question and was reported because it blocked every agent
on this box. Editing the file was refused by this session's permission classifier, so it was left
untouched; every measurement below was taken with `GIT_CONFIG_GLOBAL` pointed at a corrected
private copy at `/tmp/gateprof/gitconfig.fixed`, which differs from `~/.gitconfig` by that one
character.

**Corrected since, re-verified 2026-08-20**: `rerere.enabled` now reads `true` and `git commit`
exits 0 in a fresh repository. Kept here because it invalidated every gate run on this box for
some hours, and because the file is outside the repository and nothing in it prevents a
recurrence.

## 1. Current profile

**Machine.** WSL2 on Linux 6.6.87.2, 12 logical cores, 11,961 MB RAM. Runs between 03:56 and
05:15 BST on 2026-08-20. This box was **not** quiet: other agents' gates were running in
`.claude/worktrees/issue-370` and `.claude/worktrees/issue-439` throughout, contributing 0–24
foreign `pytest` worker processes and a 1-minute load average between 0.75 and 22.15 — the
extremes are in §3.1a, where one run carried 24 foreign workers at load 21.07. Each run below
carries the load and foreign-worker count it was taken under. Every wall figure in this document
is `/usr/bin/time`'s unless the table says otherwise; pytest's self-reported time runs a
consistent ~0.4 s lower and both are quoted side by side in §1.4 and Appendix A. No Arma slot was taken;
`~/.arma-cti/slots/*.lock` was never opened, and the suite's own lock tests redirect to
`tmp_path` through `CTI_TIER_STATE`, so they contend with nothing.

### 1.1 Recipe composition, warm caches

| Stage | Wall | User CPU | Note |
|---|---:|---:|---|
| `just check` (whole) | 9.77 s | 22.80 s | 14 sub-recipes |
| `just unit-python` | see 1.2 | see 1.2 | 5,022 tests, 119 modules |
| `just unit-rust` | 1.75 s | 0.04 s | 17 tests; 5.30 s when the crate must relink |
| `just mutation` | 0.08 s | 0.04 s | no new test module against `origin/main` |

`just check`, timed sub-recipe by sub-recipe under load 2.15 / 2 foreign workers:

| Sub-recipe | Wall | User |
|---|---:|---:|
| `check-machine-b` | 4.87 s | 4.78 s |
| `check-secrets` | 1.99 s | 14.69 s |
| `check-arbiter` | 1.85 s | 1.78 s |
| `check-sqf` | 0.36 s | 0.58 s |
| `check-python` | 0.32 s | 1.66 s |
| `check-generated` | 0.23 s | 0.18 s |
| the other eight | 0.59 s total | — |

`uv run` process startup, measured over ten no-op invocations: **median 0.06 s, mean 0.072 s,
max 0.19 s** (bare `.venv/bin/python` is 0.01 s). Fourteen sub-recipes therefore carry about
**1 s** of `uv run` overhead in total. The brief's suspicion that per-sub-check `uv run`
startup is a cost does not survive measurement.

### 1.2 The Python tier is the whole problem

Full suite, `-n auto` (12 workers), `--dist load` exactly as `pyproject.toml` ships it:

| Run | Load at start | Foreign workers | Wall | User | Sys | Result |
|---|---:|---:|---:|---:|---:|---|
| with `--durations=0` | 1.56 | 4 | 271.08 s | 391.53 s | 174.22 s | 5022 passed |
| without | 6.80 | 4 | 209.73 s | 412.92 s | 157.19 s | 5022 passed |
| `--dist loadfile` | 4.63 | 4 | 267.59 s | 405.65 s | 148.61 s | 5022 passed |

**Serial baseline**, taken detached on the quietest window of the session (load 4.89 falling
to 1.1, 0 foreign workers at start):

```
5022 passed in 592.32s (0:09:52)
WALL=593.06 USER=223.03 SYS=72.05 MAXRSS_KB=148952
```

**Parallelism ratio, three ways.**

| Measure | #195/#197, 2026-08-05 | This session, 2026-08-20 |
|---|---:|---:|
| serial wall | 6 min 17 s | 9 min 53 s |
| serial user CPU | 1 min 02 s | 3 min 43 s |
| serial wall / user CPU | **6.1x** | **2.66x** |
| serial wall / (user + sys) | — | **2.01x** |
| speedup in parallel, as shipped | 3.6x at `-n 8` (6:17 to 1:44) | **2.83x** at `-n auto` (593.1 to 209.7) |
| speedup in parallel, `worksteal` | — | **7.63x** at `-n auto` (593.1 to 77.7) |

The premise carried in `pyproject.toml`'s comment and taken from #195 — "the tier's wall clock
is six times its user CPU — it waits on `flock`, on bash subprocesses and on stub bring-ups
rather than computing" — measured 6.1x then and measures **2.66x** now. The suite has moved
from overwhelmingly wait-bound to roughly half-and-half: 223 s of user CPU inside 593 s of
serial wall. The brief's suspicion is confirmed, and CLAUDE.md's elimination-context rule
applies — the sentence no longer describes the tier it justifies.

Note also that parallelism costs CPU here: 295 s of CPU serial becomes 566 s at `-n auto`,
about 23 s per worker of import and collection overhead. That is why `-n 16` shows 426 s of
user CPU (run 11) and why raising the worker count buys progressively less.

Under `--dist load` the tier occupies **2.7 of 12 cores**. It is not oversubscribed, as #197
argued; it is **starved**, for the reason in 1.4.

### 1.3 Where the test-seconds are

From `--durations=0` on the 271 s run — that is Appendix A run 2, `-n auto --dist load`:
**955.4 s** of recorded `call`/`setup`/`teardown` across 1,479 entries, with 13,587 entries below
the 0.005 s display floor.

**This is a sum of per-test wall durations under twelve-way parallelism and foreign load, not the
suite's work, and an earlier draft of this document used it as though it were.** The proof is in
this document: the serial baseline is 592.32 s, and 955.4 s cannot be the work in a suite that
completes serially in 592.32 s. The inflation factor is 955.4 / 592.32 = 1.61, about what the CPU
figures predict (295 s of CPU serial against ~570 s at `-n auto`). Every per-module figure below
inherits the same inflation, including the 421.7 s quoted for the two heaviest modules in 3.4.
Read them as *relative* weights, which is what they are good for, and never as seconds of work.

Per module, top of the list:

| Test-seconds | Tests timed | Module | Module first added |
|---:|---:|---|---|
| 251.9 | 59 | `tests/unit/test_pool_slots.py` | 2026-08-02 |
| 169.8 | 42 | `tests/unit/test_client_lock.py` | 2026-08-02 |
| 131.2 | 26 | `tests/unit/test_run_verdict.py` | 2026-08-01 |
| 88.9 | 95 | `tests/unit/test_regress_selection.py` | 2026-08-01 |
| 65.8 | 14 | `tests/unit/test_mutation_smoke.py` | 2026-08-05 |
| 35.3 | 7 | `tests/unit/test_playtest_observer_staging.py` | 2026-08-04 |
| 18.2 | 7 | `tests/unit/test_bringup_guards.py` | 2026-08-01 |
| 17.7 | 96 | `tests/unit/test_dispatch_review.py` | 2026-08-12 |

The top five hold **74% of the measured total, from 236 of 5,022 tests (4.7%)** — a share, which
is contention-independent, rather than the 707.6 s of "work" an earlier draft called it.
They are the `flock`, bash-subprocess and daemon-bring-up modules: `test_pool_slots.py` alone
carries 28 `sleep` sites and 14 `subprocess.run`/`Popen` sites. Slowest single tests are
`test_a_dead_slot_leaves_the_lock_free_for_the_next_holder` (22.37 s),
`test_the_gate_reds_when_a_module_falls_below_its_recorded_rate` (18.76 s) and
`test_an_orphan_that_inherited_the_lock_is_named_and_reclaimed` (16.55 s).

### 1.4 The scheduler, not the suite

Running the heavy five and the rest as two separate invocations, both at `-n auto`:

| Selection | Tests | Load / foreign | Wall | User | Sys |
|---|---:|---:|---:|---:|---:|
| the heavy five alone | 335 | 5.35 / 7 | **67.91 s** | 242.74 s | 94.42 s |
| everything else alone | 4,687 | 5.65 / 4 | **30.86 s** | 118.27 s | 34.84 s |
| both together, one run | 5,022 | 6.80 / 4 | **209.73 s** | 412.92 s | 157.19 s |

98.8 s of work split in two takes 209.7 s when run as one. The heavy modules parallelise
perfectly well *on their own* (242.7 s of user CPU in 67.9 s of wall is 5.0 cores). The
combination is what starves.

The cause is in `pytest-xdist` 3.8.0's default scheduler,
`.venv/lib/python3.13/site-packages/xdist/scheduler/load.py`:

```python
# load.py:288-294 — initial distribution
items_per_node = len(self.collection) // len(self.node2pending)
node_chunksize = min(items_per_node // 4, self.maxschedchunk)
node_chunksize = max(node_chunksize, 2)
for node in self.nodes:
    self._send_tests(node, node_chunksize)
```

`_send_tests` pops from the front of `self.pending`, so each worker is handed a **consecutive
block of the collection in collection order**, chosen before any timing information exists.
The block size is `total_tests / workers / 4`:

* at 2026-08-05, 2,071 tests / 12 / 4 = **43 tests** per worker up front;
* at 2026-08-20, 5,022 tests / 12 / 4 = **104 tests** per worker up front.

Refills (`load.py:195-207`) are also consecutive, and explicitly *decline* to refill a worker
that is running long tests (`if duration >= 0.1 and len(node_pending) >= 2: return`). `load`
has no path by which an idle worker can take work from a busy one. Whichever worker draws the
`test_pool_slots.py` block runs all of it while the others finish and idle.

`--dist worksteal` (`xdist/scheduler/worksteal.py`) distributes evenly and then lets an idle
worker steal from a busy one. Same collection, same isolation assumption — any test may run on
any worker, which `--dist load` already assumes.

**Block size is not the mechanism, and this document's first draft said it was.** `worksteal`
hands the first idle worker `len(self.pending) // nodes_remaining` = `5022 // 12` = **418**
consecutive tests (`worksteal.py:212-216`) — four times *larger* than `load`'s 104. If block size
were the cause, `worksteal` would be the slower of the two. What saves it is rebalancing after
assignment (`worksteal.py:230-244`), and the correct statement of the mechanism is that **`load`
has no path from a busy worker back to an idle one**, so its wall is the unluckiest worker's
share and a growing count grows that share. A reader who takes "smaller blocks" as the lesson
will mis-tune the next scheduler decision.

That advantage is not unconditional either: `worksteal.py:222-224` permits only one outstanding
steal request across the whole run (`if self.steal_requested_from_node is not None: return`), so
rebalancing is materially weaker near the end of a run when several workers idle at once.

Walls in this table are **pytest's self-report** (Appendix A carries the `/usr/bin/time` figure
for the same runs, a consistent ~0.4 s higher).

| Run | Load at start | Foreign workers | Wall | User | Sys | Result |
|---|---:|---:|---:|---:|---:|---|
| `worksteal`, `-n auto` | 7.27 | 8 | **76.31 s** | 390.52 s | 141.94 s | 5022 passed |
| `worksteal`, `-n auto` | 2.39 | 2 | **98.04 s** | 398.62 s | 142.92 s | 5022 passed |
| `worksteal`, `-n auto` | 14.90 | 5 | **77.65 s** | 389.53 s | 139.27 s | 5022 passed |
| `worksteal`, `-n 16` | 10.31 | 5 | **68.44 s** | 426.24 s | 154.96 s | 5022 passed |
| `worksteal`, `-n 8` | 12.47 | 4 | **93.49 s** | 322.22 s | 114.70 s | 5022 passed |

Five consecutive green runs, all 5,022 passed, the same count the shipped configuration
collects and passes. Effective occupancy rises from 2.7 cores to **6.9 of 12** — which is the
benefit and, per 3.1, also the risk: every wall-clock bound in the suite is now evaluated under
about 2.5x the local contention. Five greens is the evidence this document has, not the evidence
this change needs; 3.1 says why 20 plus a control arm is the bar.

## 2. The regression, 2026-08-05 to 2026-08-19

Three historical commits were checked out into scratch worktrees under `/tmp/gateprof/` and
timed under both schedulers, back to back, on the same box in the same session:

All figures `/usr/bin/time` wall. The `70c6070` row's `worksteal` cell is **78.09 s**; an earlier
draft used 77.65 s there, which is pytest's self-report for the same run, so that row's ratio was
computed across two clocks under a heading declaring one.

| SHA | Date | Tests | `--dist load` | `--dist worksteal` | ratio | Load / foreign, load arm | Load / foreign, worksteal arm |
|---|---|---:|---:|---:|---:|---:|---:|
| `32b5c97` | 2026-08-05 | 2,071 | 92.45 s | 48.14 s | 1.92x | 2.27 / 3 | not recorded |
| `16e08bf` | 2026-08-08 | — | 105.93 s | 66.72 s | 1.59x | 3.53 / 3 | not recorded |
| `0527f1b` | 2026-08-13 | — | 172.78 s | 67.11 s | 2.57x | 8.34 / 6 | not recorded |
| `70c6070` | 2026-08-20 | 5,022 | 209.73 s | 78.09 s | 2.69x | 6.80 / 4 | 7.27 / 8 |

This table is no longer what carries the regression finding — §2's serial baselines at the two
dates are — and the reasons are below. It is kept because it is the only same-tree back-to-back
comparison of the two schedulers across the window.

**The last two columns are why this table cannot carry a strong claim on its own.** The `worksteal` arm's
machine load was not recorded on three of four rows, which fails this document's own rule that a
benchmark not saying what else was running is not a benchmark. Every cell is n=1 in arms that vary
±30%, so each ratio carries roughly ±40%; 1.59x and 2.69x are not distinguishable at that spread.
The column is **not monotone** — 08-08 sits below 08-05 — and only two of four rows carry a test
count. Box load is confounded with date and is not eliminated as the driver: `load`'s tail is one
worker holding a queue nothing can take, so a descheduled worker costs `load` more than it costs
`worksteal`, and foreign load would inflate the ratio directly.

Under the shipped scheduler the tier grew **2.27x**. Under work stealing it grew **1.61x**, and
most of that is the 08-05 to 08-08 step. `16e08bf` and `0527f1b` exited non-zero when run
against today's environment — old code, current tree state — so their pass counts are not
comparable; their wall times are, because both schedulers ran the same tests on the same tree
minutes apart.

**What actually grew — a withdrawn claim and its replacement.** This document's first draft
attributed each module's measured test-seconds to the commit that first added the *module*, got
848.0 s pre-window against 107.2 s in-window, and concluded that "89% of the suite's test work
was already present on 2026-08-05" and that test work grew about 11%. **Both claims are
withdrawn.** The method has a hole the conclusion cannot survive: every test added later to a
module that already existed is counted in the pre-window bucket, and the window's 40,113 added
lines across 257 commits went substantially into old modules — `test_land.py` and
`test_dispatch.py` are the two largest in the tree and both predate it. What the method actually
measures is "89% of today's test-seconds sit in modules that existed", which is a different and
much weaker statement.

A replacement figure of "about 1.6x" was then inferred from `worksteal` wall as a proxy for
work. **That was wrong too**, and for the same species of reason: `worksteal` wall carries a
per-worker import-and-collection term that scales with module count, so it is not a proxy for
work either. Round two of the review caught it and proposed 1.6x–2.2x. Rather than pick a point
in that range, the question was **settled by the one measurement that answers it directly** —
serial wall, which is contention-tolerant and clock-independent where every parallel figure here
is not.

**Serial baseline at `32b5c97`, taken 2026-08-20** (start load 4.53, 5 foreign workers):
`WALL=483.12 USER=154.27 SYS=71.71`. Two of 2,071 tests fail at that SHA against today's
environment — `test_breaker.py::test_watch_report_prints_the_verdicts_and_stays_silent_when_nothing_is_tripped`
and one flaky `test_client_lock.py` parametrisation that reds in one run of two — so the red-run
discount on that wall is negligible.

| Quantity | 2026-08-05 | 2026-08-20 | Growth |
|---|---:|---:|---:|
| test count | 2,071 | 5,022 | **2.43x** |
| work, as serial wall | 483.12 s | 593.06 s | **1.23x** |
| work, as serial CPU | 225.98 s | 295.08 s | 1.31x |
| `--dist load` wall | 92.45 s | 209.73 s | **2.27x** |
| `--dist worksteal` wall | 48.14 s | 78.09 s | 1.62x |

Two independent proxies for work — serial wall and serial CPU — agree at **1.23x to 1.31x**. So
the suite does about a quarter more work than it did, spread over two and a half times as many
tests, and:

- the **shipped scheduler's wall grew 1.85x faster than the work did**;
- `worksteal`'s grew only **1.32x faster**, and that residual is the per-worker import and
  collection term scaling with 68 modules to 119.

**That is the finding, and it is now measured rather than inferred.** The suite's character did
not change: it does modestly more work, in many more, mostly fast, tests. What changed is that
`--dist load` charges a penalty that grows with the count, and about 1.85/1.32 of the growth in
gate wall clock is recoverable by changing nothing but the scheduler. No single commit is
responsible, bisecting would have found nothing, and every commit made it slightly worse — which
is why it went unnoticed for two weeks.

For the record of how this number moved: the first draft said work grew **1.11x** (module-dating,
method invalid); round one's correction implied **1.6x** (`worksteal` wall as proxy, also
invalid); round two proposed **1.6x-2.2x** (correcting for a fixed term, right in form); the
measurement says **1.23x**. Three inferences, three wrong, one run of a few minutes to settle it.

**Does `-n auto` still earn its place?** Yes — and the argument written above it does not.
The wait-bound premise is half gone: serially the tier spends 295 s of CPU inside 593 s of
wall, where #197 measured 62 s inside 377 s. But a suite that takes 593 s on one core still
takes 593 s on one core, and work stealing at twelve workers returns it in 77.7 s — a 7.63x
speedup, against the 2.83x the shipped configuration currently gets. The number stays; the
sentence justifying it should be rewritten to the ratio that holds, because under the
elimination-context rule a justification left standing after its context has moved is what
gets inherited next time.

**A stale denial, on the same principle.** `.claude/hooks/deny-subagent-waits.py` denies a
"known-long gate: a command whose measured p90 wall exceeds the TTL", with `THRESHOLD = 240`,
and its docstring records that `just fast` came off that shortlist when #197 took it to 1:02.
Measured over strictly-matched invocations in this project's session transcripts since
2026-08-13: `just fast` **p50 206 s, p90 314 s, p95 389 s, with 28% of runs at or over 240 s**.
By the hook's own stated rule `just fast` re-qualifies today. The hook says such changes are a
retro's to make, not an agent's in the moment, so this is filed as an observation rather than
acted on — and if the scheduler change lands, the p90 falls back under the threshold and the
question closes itself.

## 3. Candidate reductions, ranked

Ranking is by measured saving per unit of risk. Every candidate here was measured; the ones
that failed measurement are in section 4 rather than being argued down.

### 3.1 Switch the xdist scheduler to `--dist worksteal` — *adopt*

**Change.** One line in `pyproject.toml`:
`addopts = "-q --strict-markers --strict-config -n auto --dist worksteal"`, with the comment
above it rewritten to state the measured ratio rather than the retired one.

**Measured saving, stated as a range.** Full suite 209.7 s to 77.7 s in the cleanest same-tree
pairing — 2.70x — but run-to-run variance on this box is about ±30% in *both* arms (shipped
209.73 and 271.08 s; worksteal 76.69, 98.46 and 78.09 s), and the one interleaved round that
controlled for load gives about **1.6x**. The defensible claim is **roughly 1.6x to 2.7x
depending on box load**. Note the selection bias runs in the proposal's favour on the `load`
side: quoting 209.73 rather than 271.08 understates the gain.

An earlier draft of this section defended the comparison on the ground that "the worksteal runs
were taken under heavier foreign load". **That does not follow from this data** and is withdrawn:
the worksteal series is *inversely* ordered by load (load 2.39 gave 98.46 s, load 14.90 gave
78.09 s). What supports the comparison is the interleaved round in 3.1a and the four-SHA table in
§2, both of which vary load across arms rather than between them.

**Modelled saving: the bound, and where on it this box actually sat.** Applying per-SHA ratios to
1,032 strictly-matched `just fast` and `just unit` invocations since 2026-08-05 (44.74 h
observed) models a 23.55 h saving. That number is too precise for what it knows, and it has a
ceiling the model cannot see. **The change moves no CPU work** — 412.9 s user under `load`
against 390.5 s under `worksteal`; it compresses the same CPU-seconds into a shorter window. In
the fully CPU-bound limit the ratio collapses: at 570.11 CPU-seconds per `load` gate and 532.46
per `worksteal` gate on 12 cores, three concurrent gates floor at 142 s and 132 s respectively —
a **7%** saving, not 1.6x. In the solo limit it is about 60%. Across the 44.74 h observed, the
span is therefore roughly **3 h to 27 h**, and picking a point in the middle measures nothing.

**So it was measured.** Re-pairing every `tool_use` with its `tool_result` across the 1,012
transcripts and keeping absolute timestamps gives, for each of 1,058 gate spans since 2026-08-05,
how many gate spans *in other sessions* overlapped it:

| Concurrent other gate runs | Share of runs |
|---:|---:|
| 0 | **73.4%** |
| 1 | 13.9% |
| 2 | 6.7% |
| 3 | 3.6% |
| 4 or more | 2.4% |

Mean concurrency **0.50**, median 0, and **67.1% of the 46.24 gate-hours were spent with no other
gate overlapping at all**. The CPU ceiling binds only from three concurrent gates upward, which
is 6.0% of runs. So the population sat much nearer the solo end of the span than the CPU-bound
end, and the earlier assumption — that the box "routinely carries two to four agents' gates at
once" during a gate run — is wrong as a description of the *typical* run, however true it is of
the busiest hours. The defensible claim is **towards the upper part of a 3 h to 27 h span**, with
the model's remaining blind spots stated: it cannot see runs that red early (and run 1 shows a
red suite is *faster*), ran a subset, or were interrupted.

**Risk to verification strength: the isolation claim holds; the timing claim does not.**
Checked and true: `worksteal` and `load` both hand any index to any worker, neither offers an
ordering or affinity guarantee, `worksteal` reuses `load`'s collection-identity check, and a test
depending on which worker or what order is already broken today. But "nothing a test can observe
changes" is false.

**Why, stated correctly.** An earlier draft here said occupancy rises 2.7 → 6.9 of 12 cores and
therefore every bound is evaluated under "roughly 2.5x the local contention". That is circular:
570.11 CPU-s / 209.73 s = 2.72 and 532.46 / 76.69 = 6.94 are *mean* CPU-seconds per wall-second,
so their ratio is arithmetically the wall speedup itself, restated. It is also not a *peak* —
both arms run twelve workers, so the instantaneous worst case is identical; what changes is how
much of the run looks like it. The correct argument follows from the mechanism this document
already establishes: **under `load` the heavy modules run in the tail, when the other eleven
workers have finished and the box is at its quietest.** The most timing-exposed tests in the
suite currently execute in the least contended part of the run, and `worksteal` moves them into
the middle of everything. That is the real reason the risk rises, and it needs no multiplier.

**The exposed set, re-derived rather than hand-picked.** An earlier draft named six sites and
called that "about half a dozen". The sweep that produces the set:

```
grep -rn "assert .*elapsed\s*<\|assert time\.monotonic() - .* <" tests/unit/*.py
```

At `70c6070` it returns **17 sites across 9 modules** — `test_client_lock.py` alone carries seven,
not the two named — and at `95848ad` it returns 19 across 10, because `test_bounded_request.py`
landed in between with two more. A lander should re-derive it at the implementation commit rather
than inherit a list that was stale within hours. `test_coordinator.py:273`'s `assert elapsed < 0.2`
behind a blocked writer is the tightest and is worth singling out. Two exposures the grep does not
find: `test_run_verdict.py:60`'s `free_port_block()`, a bind-then-close TOCTOU window that widens
as its 26 tests are more likely to be split across workers, and `conftest.py:39`'s
`settings(deadline=None)`, which switches off hypothesis's per-example deadline but **not**
`HealthCheck.too_slow`, which is suppressed nowhere. The precedents: `conftest.py:29-38` records a
property that "red once in four full-suite runs while 5,500 isolated examples found nothing";
`test_client_lock.py:441` records an arrangement that produced "about one red per full
`just unit` under `-n auto`"; #428 is open now.

**Cost of being wrong.** Reverting is deleting the flag. A parallel-only red is a synchronisation
bug to fix, never a reason to drop back silently.

**What to require before landing.** Five green runs is *not* enough here — five runs miss a
1-in-4 event about 24% of the time and a 1-in-20 event about 77% of the time, and #197's five-run
bar was set against a 2,071-test suite with less concurrency machinery in it. Require at least
**20 consecutive runs under `worksteal` with reds counted, plus a control arm of the same size
under `load`**, because a bare green cannot distinguish "worksteal is clean" from "this suite
reds occasionally either way" — which is what CLAUDE.md's `flake_quarantine` row demands be
stated. Also require peak system-wide RSS and process count (the quantity 3.2 rejects `-n 16`
over, left unmeasured here), three `just fast` end-to-end timings, and the `-n0` path.

### 3.1a `--maxschedchunk=1` — the same fix without changing scheduler

`--maxschedchunk` caps the consecutive block `--dist load` hands out, both in the initial
distribution (`load.py:290`, `node_chunksize = min(items_per_node // 4, self.maxschedchunk)`)
and in every refill (`load.py:206`). Setting it to 1 shrinks the blind block from 104 tests to
the floor of 2 and dispatches one at a time thereafter, which addresses the same cause as 3.1
from the other side.

**Measured**, first on the quietest window of the session (load 0.90, 2 foreign workers):
**63.07 s**, 5022 passed — the fastest single figure this investigation produced, but on the
quietest box, so not comparable to anything else here. An interleaved A/B/C/C/B/A round was then
run to control for load drift. Every arm 5022 passed:

| Arm | Load | Foreign | Wall |
|---|---:|---:|---:|
| A shipped (`load`) | 13.05 | 9 | 173.81 s |
| B `--maxschedchunk=1` | 3.94 | 1 | 125.40 s |
| C `worksteal` | 21.07 | **24** | 130.13 s |
| C `worksteal` | 17.50 | 6 | 90.21 s |
| B `--maxschedchunk=1` | 11.78 | 2 | 79.89 s |
| A shipped (`load`) | 9.81 | 2 | killed before finishing |

B and C are **indistinguishable** under this box's load variance (B mean 102.6 s, C mean
110.2 s, and C's slower run carried 24 foreign workers against B's 1). The round was stopped
after one pass because the box reached load 22 with another agent's gate and further rounds
would have measured that rather than the schedulers.

**Which to prefer.** The numbers do not separate them, so the choice is on mechanism.
Work stealing is the more robust of the two on *this* box, because it
rebalances after assignment: a worker descheduled by another agent's gate gives its remaining
tests up, where `--maxschedchunk=1` can only avoid handing it too many in the first place. It
also keeps two tests queued per worker (`worksteal.py:20`, `MIN_PENDING = 2`) rather than paying
a controller round trip between every one of 5,022 tests. Both are one flag and both are
revertible by deleting it.

### 3.1b The paired runs round two asked for, and what they show

Round two's R2-19 was right that no clear-box `worksteal` figure existed. Three alternating pairs
were taken on 2026-08-20 in response, each arm's machine load recorded before it started — the
thing three of the four SHA comparisons failed to do. All arms 5,022 passed.

| Pair | `--dist load` | foreign / load | `--dist worksteal` | foreign / load | ratio | arms matched? |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 188.55 s | 1 / 3.58 | 77.76 s | 2 / 3.44 | **2.42x** | yes |
| 2 | 251.22 s | 5 / 11.33 | 69.13 s | 0 / 1.96 | 3.63x | no — favours `worksteal` |
| 3 | 231.84 s | 0 / 6.54 | 76.84 s | 1 / 3.28 | 3.02x | no — favours `worksteal` |

**Only pair 1 is a fair comparison**, and it gives **2.42x**. Pairs 2 and 3 ran their `load` arm
under materially heavier load than their `worksteal` arm, so their ratios are inflated and are
recorded rather than used. Taken with 3.1a's interleaved round — whose mismatches ran the other
way — the defensible range stays **roughly 1.6x to 2.7x**, with 2.42x the best single estimate
from the one pair where both arms saw the same box.

**A finding these runs produce that no earlier measurement could.** Across every full-suite run in
this investigation:

| Arm | n | min | max | mean | sd | spread |
|---|---:|---:|---:|---:|---:|---:|
| `--dist load` | 7 | 168.8 s | 271.1 s | 213.6 s | 39.3 s | **102 s** |
| `--dist worksteal` | 7 | 69.1 s | 98.5 s | 81.0 s | 9.9 s | **29 s** |

`load`'s wall swings by 102 seconds across the runs recorded here; `worksteal`'s by 29. That is
not only a smaller proportion, it is a third of the absolute variation, and it follows directly
from the mechanism: when a worker is descheduled by another agent's gate, `load` has no way to
move the queue it is sitting on, so foreign load lands entirely on the critical path. `worksteal`
can move the work. **The scheduler change buys predictability as well as speed**, which matters on
a box that carries other agents' gates 27% of the time, and neither artefact claimed it before
these runs.

**What is still open.** `worksteal`'s 69.13 s at 0 foreign workers against `--maxschedchunk=1`'s
63.07 s at 2 foreign workers and a quieter load average does not separate the two options, which
is the same answer 3.1a gave. The choice stays on mechanism, and the settling measurement named in
3.1a — alternating pairs with `pgrep -fc pytest` at 0 on both arms — has still not been taken for
that pair.

### 3.2 Raise the worker count from 12 to 16 — *do not adopt yet*

**Measured.** `worksteal -n 16` returned 68.44 s against `worksteal -n auto` at 76.31 / 98.04 /
77.65 s. That is inside the run-to-run spread this box produces under other agents' load, so
the measurement does not separate a real 10% from noise.

**Risk.** The box has 11,961 MB of RAM and the tier peaked at 326 MB RSS for the parent under
`-n auto`; 16 workers plus another agent's 12 is the shape that produced #164's memory
exhaustion. Not worth 8 s.

**Recommendation.** Leave `-n auto`. Re-open only with a repeated measurement on a quiet box.

### 3.3 Split the `flock`-serialised modules from the fast suite — *do not adopt*

**Measured.** The heavy five alone take 67.91 s; the remaining 4,687 tests take 30.86 s. A split
tier in which in-flight edits run only the fast half would return in about 31 s.

**Why not.** It buys 46 s over 3.1 and costs 335 tests of in-flight coverage — including every
test of the slot pool, the client lock and the probe verdict ladder, which are exactly the
surfaces CLAUDE.md's failure-class table says must not be guessed at. That is buying wall clock
by removing assertions, which the brief rules out and which this project's own record
(`docs/process-log.md`, the twenty-ninth retro: "the full gate twice caught what a targeted
green missed") argues against directly. With 3.1 in place the whole suite costs 77 s, and the
split's remaining margin does not justify a two-tier gate anyone can get wrong.

### 3.4 Make the heavy modules cheaper — *file, do not do now*

`test_pool_slots.py` and `test_client_lock.py` hold 421.7 s of the suite's 955.4 s of test time
across 101 tests, and carry 43 `sleep` sites between them. Some of those waits are the subject
(a lock's queueing behaviour is a real wait) and some are synchronisation. CLAUDE.md forbids
extending a timeout to make a test pass and says nothing against replacing a fixed settle with
an event-driven exit — a conversion this project has already run once, on the probe corpus
(#43, #46), keeping a measured extremum where one existed.

**Not now, because** 3.1 makes the whole suite cheaper than these two modules currently cost,
and every second spent here is a second spent on a real risk of weakening a concurrency test.
Worth an issue with the module-level numbers above attached, so whoever takes it starts from
measurement.

### 3.5 Per-sub-check `uv run` startup — *closed, no saving exists*

Measured at a **median of 0.06 s** per invocation over ten no-op runs. Fourteen sub-recipes
carry about 1 s in total, against a `just check` that costs 9.77 s and a gate that costs 200 s.
Consolidating them would save under half a second and would cost `just check`'s property of
naming which rung failed. No further work.

### 3.6 Run `just check` and `just unit` in full after every edit, or only before landing — *no change*

**Measured.** `just check` is 9.77 s warm. `just unit`'s Rust half is 1.75 s. `just mutation` is
0.08 s when the diff adds no test module. With 3.1 in place the entire gate is about 90 s.

The brief asks whether the in-flight and pre-landing tiers should differ. On these numbers they
should not. The multiplier is real — 2,025 strictly-matched gate invocations against 660 commits
on `origin/main` is **3.1 gate runs per landed commit**, and `tools/land.py:209` re-runs
`just fast` inside the landing protocol, so a landing pays for at least one more — but 3.1
turns that multiplier from 200 s into 90 s a run, which is a bigger reduction than any tiering
scheme would yield and costs nothing in coverage. Splitting the tiers would put a judgement call
("is this edit big enough for the full gate?") in front of every agent, and this project's
record on judgement calls in front of gates is the equivalence argument recorded against #145.

One measured observation for the retro rather than a proposal: **529 of 551 `just unit`
invocations ran the whole suite with no `-k` and no path filter.** Narrowing while iterating is
already available, already free, and essentially unused. That is a briefing question, not a
recipe change.

## 4. Looked at, found nothing

Recorded so the next reader does not repeat them.

* **`just check`'s fan-out.** 14 sub-recipes, 9.77 s wall total, 4.87 s of it one Ansible
  syntax check. Parallelising the fan-out could save at most about 5 s of a 200 s gate, and
  would cost the per-rung failure attribution. The brief's prior that `just check` is not the
  problem is confirmed rather than merely repeated.
* **`uv run` startup.** Median 0.06 s. See 3.5.
* **The Rust half.** The brief noted it was unmeasured because `cargo` was off the measuring
  shell's PATH; it is at `~/.cargo/bin`. `just unit-rust` is **17 tests, 1.75 s warm**, 5.30 s
  when the crate relinks. It is 0.9% of `just unit` and not worth touching.
* **`--dist loadfile`.** 267.59 s, worse than `--dist load`'s 209.73 s. Grouping by file pins
  each heavy module to one worker, which is the failure mode 1.4 describes, made mandatory.
* **Test collection.** 1.8 s warm, serial, and it is not re-paid per worker in a way that
  shows: `--collect-only` under `-n auto` is 1.77 s. Not a cost.
* **The mutation gate.** 0.08 s at this HEAD, because the diff against `origin/main` adds no
  test module; transcript median 0.2 s over 213 strictly-matched invocations, p90 115.5 s. It
  is bounded by `BUDGET_S = 180.0` in `tools/mutation_smoke.py` and is paid only by landings
  that add a test module. It is not a standing cost and #435 is open on its determinism, so its
  timings were treated as noisy and nothing here rests on them.
* **Bisecting for a slow commit.** There is not one, and the reason is in section 2: measured
  against serial wall at both dates the suite's work grew 1.23x while the shipped scheduler's
  wall grew 2.27x, so the scheduler's penalty grew 1.85x faster than the work and every commit
  made it slightly worse. The first draft argued this from a module-dating attribution, and a
  second attempt argued it from `worksteal` wall as a proxy for work; both are withdrawn, and
  the serial baselines at the two dates are the evidence that survives.
* **A memory ceiling — and this one is genuinely unmeasured, not cleared.** The only figure is
  326,732 KB RSS for the **parent** process under `--dist load`. That says nothing about peak
  system-wide RSS, and `worksteal` runs the heavy subprocess and daemon-bring-up tests
  concurrently rather than clumped on one worker, so the peak should be expected to rise. 3.2
  rejects `-n 16` citing #164's memory exhaustion, so leaving the same quantity unmeasured under
  the change being adopted is an inconsistency this document did not notice; it is now an
  acceptance criterion in 3.1 rather than a cleared line here.

## 5. Reproducing this

```bash
# profile: where the test-seconds are
uv run pytest --durations=0 -p no:cacheprovider | grep -E '^[0-9]+\.[0-9]+s (call|setup|teardown)'

# the comparison that matters, back to back on the same tree
/usr/bin/time -f "WALL=%e USER=%U SYS=%S" uv run pytest -p no:cacheprovider
/usr/bin/time -f "WALL=%e USER=%U SYS=%S" uv run pytest -p no:cacheprovider --dist worksteal

# state the load with every number
cat /proc/loadavg; pgrep -fc pytest
```

The transcript figures come from pairing each `Bash` `tool_use` with its `tool_result` by
`tool_use_id` across `~/.claude/projects/*arma-cti*/**/*.jsonl` (1,012 files), discarding gaps
over 1800 s and background invocations, and matching a recipe only where a shell segment
*begins* with `just <recipe>` — a looser regex counts mentions inside quotes and `grep`
arguments and moves the `just fast` median from 168 s to 5 s. Scripts are in `/tmp/gateprof/`;
they read only and are not proposed for landing.

## 6. What landed, and what remains

This investigation landed through #450. Its adopted ordinary work landed through #442 and #446, both
closed. #442 and #446 cite `docs/research/gate-wall-clock.md`; #447 remains open but does not cite
this record, although it uses figures from it without a provenance line. Splitting its standing by
gate:

**Ordinary work, no sign-off gate — landed.**

1. `pyproject.toml`: add `--dist worksteal` to `addopts`, and rewrite the comment above it. The
   present comment states an inherited ratio ("wall clock is six times its user CPU") that this
   session measured to be inverted; leaving it in place is what lets the next reader inherit it
   again, which is exactly the failure CLAUDE.md's elimination-context rule names. The
   replacement should say what holds: the tier is CPU-heavy, `-n auto` is kept because **593 s of
   serial wall** does not fit in one core, and the scheduler is `worksteal` because **`load` never
   rebalances** — once an index is assigned there is no path back, so the wall is the unluckiest
   worker's share. It should also say that `-n0` forces `dist=no` (`xdist/plugin.py:326-327`), so
   the documented serial debugging path is unchanged. *(This item carried both of the claims the
   revision withdrew — "955 s of test time" and "the blind initial chunk scales with the count" —
   until round two of the review found them here, in the one section that dictates the words a
   reader will find in `pyproject.toml`. Accepted in prose and not discharged in the artefact is
   the exact failure that finding names.)* Landed through #442.
2. A changelog fragment under `changelog.d/`, category Changed, per ADR-0010. Landed through #446.

**Human sign-off, not adopted.**

3. `.claude/hooks/deny-subagent-waits.py` — no change proposed. The p90 observation in section 2
   was put to the next retro, which is where that file's own docstring says the list moves. Item 1
   landed through #442, so the observation expired.
4. `docs/process-log.md` — a retro's to write, not this document's.

**Filed separately, not done here.**

5. The heavy-module conversion of section 3.4, with the per-module numbers attached, remains open
   under #447. #447 uses these measurements but does not cite this record.
6. The `~/.gitconfig` typo of section 0, which is not a repository change at all, was corrected and
   committed in the human's dotfiles repository.

**Explicitly not proposed:** any change that reduces what the gate proves. No test is skipped,
no module is excluded, no timeout is widened, no tier is split, and the collected and passed
count is 5,022 before and after.

## 7. What this does not establish

* **No quiet-box numbers exist for the headline comparison.** This box carried other agents'
  gates throughout — between 0 and 24 foreign `pytest` workers, 1-minute load between 0.75 and
  22.15. An earlier draft of this bullet gave that range as 0–12 and 0.75–17.26, which
  undercounted against §3.1a's own table; a caveat section that undercounts the caveat is the
  section least able to afford it. The same draft defended the comparison on the ground that the
  worksteal runs ran under heavier foreign load; that is withdrawn (see 3.1). What supports it is
  the interleaved round and the four-SHA table. No single number here is a clean-room figure.
* **The savings figure is an order of magnitude, not an accounting**, and it is bounded above by
  a mechanism the model cannot see: the change moves no CPU work, so on a box carrying
  concurrent gates aggregate throughput stays CPU-bound. See 3.1.
* **Flakiness under a different scheduler is only five runs deep, and five is too few.** Five
  runs miss a 1-in-4 event about 24% of the time. #197's five-run bar was set against a
  2,071-test suite; this one is 5,022 with materially more concurrency machinery and a documented
  ~1-in-4 flake precedent. 20 runs plus a same-size control arm is the bar this needs.
* **The quiet-box gap is now closed on one arm and still open on the comparison.** Round two
  observed that no quiet-box `worksteal` figure existed anywhere here — the only clear-box run was
  `--maxschedchunk=1`'s 63.07 s, the *rejected* alternative. Three paired runs were taken on
  2026-08-20 in response (3.1b). `worksteal` now has a genuine clear-box figure — **69.13 s at 0
  foreign workers, load 1.96** — but only one of the three pairs had matched arms, so the
  comparison is better evidenced than before and still not clean. The interleaved round in 3.1a
  controls for load *drift* by alternating; it does not hold load constant, and its arms ran at 9,
  24, 6, 1 and 2 foreign workers, which biases its 1.6x endpoint down in the same way the 2.7x
  pairing is biased up.
* **The scheduler in force is not directly assertable from a test.** `xdist/remote.py:392-397`
  sets `config.option.dist = "no"` in every worker and `xdist/plugin.py:326-327` does the same at
  `-n0`, so `pytestconfig.getoption("dist")` is `'no'` everywhere a test can run — confirmed
  empirically. Only the parsed ini value (`getini("addopts")`) survives both, and it cannot see a
  command-line override.
* **Nothing here was run through `just fast` end to end** except the sub-recipe breakdown; the
  scheduler comparisons were run at the `uv run pytest` level, which is what `just unit-python`
  invokes.
* **The Arma tiers are untouched.** `just regress` and `just probe` were not run, not measured
  and are not in scope; their duration is their subject's.

## Appendix A — every timing taken, in order

All on `70c6070` unless a SHA is given. `foreign` is the count of `pytest` processes belonging
to other agents at the moment the run started. **Wall here is `/usr/bin/time`'s**; §1.4's tables
quote pytest's self-reported figure, which runs a consistent ~0.4 s lower (76.31/76.69,
98.04/98.46, 77.65/78.09, 68.44/68.84, 93.49/93.88). Nothing turns on the difference, but the
issue quotes 77.65 s where this table says 78.09 s and they are the same run.

| # | What | Load | Foreign | Wall | User | Sys | Result |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `pytest --durations=0` (shipped, **broken gitconfig**) | 2.24 | 2 | 221.10 | 320.33 | 95.12 | 306 failed, 4639 passed, 77 errors |
| 2 | `pytest --durations=0` (shipped) | 1.56 | 4 | 271.08 | 391.53 | 174.22 | 5022 passed |
| 3 | heavy five only | 5.35 | 7 | 67.91 | 242.74 | 94.42 | 335 passed |
| 4 | everything except the heavy five | 5.65 | 4 | 30.86 | 118.27 | 34.84 | 4687 passed |
| 5 | `pytest` (shipped, no durations) | 6.80 | 4 | 209.73 | 412.92 | 157.19 | 5022 passed |
| 6 | `--dist loadfile` | 4.63 | 4 | 267.59 | 405.65 | 148.61 | 5022 passed |
| 7 | `--dist worksteal` | 7.27 | 8 | 76.69 | 390.52 | 141.94 | 5022 passed |
| 8 | `-n 8` (`load`) | 9.59 | 4 | 259.60 | 325.18 | 121.87 | 5022 passed |
| 9 | `--dist worksteal` | 2.39 | 2 | 98.46 | 398.62 | 142.92 | 5022 passed |
| 10 | `--dist worksteal` | 14.90 | 5 | 78.09 | 389.53 | 139.27 | 5022 passed |
| 11 | `--dist worksteal -n 16` | 10.31 | 5 | 68.84 | 426.24 | 154.96 | 5022 passed |
| 12 | `--dist worksteal -n 8` | 12.47 | 4 | 93.88 | 322.22 | 114.70 | 5022 passed |
| 13 | `32b5c97` shipped | 2.27 | 3 | 92.45 | 182.38 | 51.83 | green |
| 14 | `32b5c97` worksteal | — | — | 48.14 | 150.08 | 51.18 | green |
| 15 | `16e08bf` shipped | 3.53 | 3 | 105.93 | 221.79 | 56.31 | non-zero (old code, current tree) |
| 16 | `16e08bf` worksteal | — | — | 66.72 | 202.50 | 76.25 | non-zero |
| 17 | `0527f1b` shipped | 8.34 | 6 | 172.78 | 391.64 | 111.44 | non-zero |
| 18 | `0527f1b` worksteal | — | — | 67.11 | 329.29 | 117.38 | non-zero |

Run 1 is kept because it is the evidence for section 0, and because a red suite is *faster*
than a green one — the shipped-configuration figures in this document are therefore the green
ones, runs 2 and 5.

Filed as **#442** with the seam, acceptance evidence and out-of-scope boundaries.

## Appendix B — what the first adversarial review changed

Reviewed 2026-08-20 by dispatch `d-20260820-044246-a8b21d` (`review` seat, opus/high, read-only),
posted in full on #442. Its verdict: the change is sound and it would land it; the spec was not
fit as written. What it overturned in this document, all accepted:

| Finding | What it overturned | Where |
|---|---|---|
| F1 | The proposed test seam. `getoption("dist")` is `'no'` in every worker and at `-n0`, so the assertion would have red on every run | §7, and #442's Testing Decisions |
| F3 | "Risk to verification strength: none identifiable". The isolation claim holds; the contention claim does not — occupancy 2.7 → 6.9 cores widens every wall-clock bound in the suite | 3.1 |
| F4 | "Smaller blocks" as the mechanism. `worksteal`'s initial block is 418 against `load`'s 104; the mechanism is that `load` never rebalances | 1.4 |
| F5 | "89% of the test work predates 2026-08-05" and "work grew about 11%", both artefacts of dating modules rather than tests. Its own replacement figure was then overturned by round two — see Appendix C | §2 |
| F6 | The 2.7x headline, which is the most favourable pairing available, and a defence from foreign load that the data contradict | 3.1, §7 |
| F7 | The 23.55 h saving's precision. The change moves no CPU, so concurrent gates stay CPU-bound | 3.1, §7 |
| F9 | This document's own load range, understated in two places against its §3.1a | §1, §7 |
| F10 | Two unlabelled clocks | Appendix A |

It also confirmed, against source: the `load.py` arithmetic at both dates, the refill
decline-to-refill branch, that both schedulers share one isolation assumption, that `-n auto` is
12 here (no `psutil`), that `just mutation` is provably unaffected because `-n0` forces
`dist=no`, that no test spawns pytest without `-n0`, and the 955.4/12 = 79.6 s against 77.65 s
balance check — which it noted is the strongest single piece of evidence here and was under-used.

## Appendix C — what the second adversarial review changed

Reviewed 2026-08-20 by dispatch `d-20260820-050616-ecf8f6` (`review` seat, opus/high, read-only,
tree at `95848ad`), a different instance from Appendix B's with no memory of it, posted in full on
#442. Its verdict: the change is sound and it would land it; the spec was not fit as it then
stood. It raised 24 findings and audited whether round one's fourteen had actually been
discharged, finding four that had not.

| Finding | What it overturned | Where |
|---|---|---|
| R2-1 | **"955.4 s of test time"** used as the suite's work. It is the sum of per-test *wall* durations under `-n auto --dist load`, and it exceeds the suite's own 592.32 s serial wall — so the balance check built on it, which round one called "the strongest single piece of evidence", is invalid, and so is the 1.6x work-growth figure | §1.3, §2, 3.1 |
| R2-2 | "The penalty climbs with the count" as carried by the four-SHA ratio column: non-monotone (08-08 below 08-05), two of four rows without a test count, n=1 per cell in arms varying ±30%, and the `worksteal` arm's load unrecorded on three of four rows | §2 |
| R2-3 | A clock contradiction introduced by Appendix B's own F10 fix: the four-SHA table mixed `/usr/bin/time` and pytest walls inside one row under a heading declaring one | §2 |
| R2-4 | "Roughly 2.5x the local contention" — an occupancy ratio relabelled, arithmetically the wall speedup restated; and "peak", where both arms peak at twelve busy workers | 3.1 |
| R2-5 | Six named wall-clock-bounded assertions where the grep returns 17 at `70c6070` and 19 at `95848ad` | 3.1 |
| R2-6 | The savings bound, computed for one arm only. Both floors and the resulting 7%-to-60% span are now stated, and the position within it **measured** rather than assumed | 3.1 |
| R2-16 | §6 still instructing the implementer to write **both** withdrawn claims into `pyproject.toml`'s comment — accepted in prose, not discharged in the artefact | §6 |
| R2-17 | §1's foreign-worker range, corrected for load but not for workers, so it stated a range and its own counter-example in one sentence | §1 |
| R2-19 | "Load-controlled" for the interleaved round, which controls for drift rather than load; and the observation that **no quiet-box `worksteal` figure exists anywhere in this investigation** | 3.1, 3.1a |
| R2-20 | The restated mechanism recruiting `load`'s decline-to-refill branch as a cause, when it is `load`'s own partial defence against the imbalance | 1.4 |
| R2-21 | `test_coordinator.py:272`, which is 273 at both `e4a403b` and `95848ad` — wrong in both artefacts, in the one site round one asked to be named in the landing's evidence | 3.1 |

**Two findings were settled by measurement rather than by weakening the claim**, per CLAUDE.md's
measure-before-building rule:

- **R2-1's work-growth question**, by one serial run at `32b5c97`: `WALL=483.12 USER=154.27
  SYS=71.71`. Work grew **1.23x** (1.31x by CPU), against a first-draft claim of 1.11x, round
  one's implied 1.6x and round two's proposed 1.6x–2.2x. Three inferences, three wrong, one run
  of eight minutes to settle it. The finding it supports is *stronger* than the one it replaced:
  the shipped scheduler's wall grew 1.85x faster than the work.
- **R2-6's concurrency assumption**, by re-pairing the transcripts with absolute timestamps:
  73.4% of 1,058 gate runs had no other gate overlapping, and 67.1% of gate-hours were solo. The
  CPU ceiling is real but binds on 6.0% of runs, so the population sat near the solo end of the
  span rather than the middle — which contradicts the review's own premise while confirming its
  arithmetic.

It also confirmed, against source: the `load.py` arithmetic at both dates and that `maxschedchunk`
defaults to the collection length so the `min` is inert; `worksteal`'s 418-test initial block and
its single-outstanding-steal limit; the whole test-seam diagnosis; routing class 6's path list
against `config/dispatch-routing-policy.json`; the mutation-scope claim at
`tools/mutation_smoke.py:1793-1806` and that `tools/mutation-baseline.json` is `{}`; that nothing
in the repository sets `PYTEST_ADDOPTS`; that `-n0` forces `dist=no`; the `~/.gitconfig`
diagnosis; all four rejected alternatives; and that `worksteal` carries no experimental caveat in
`xdist` 3.8.0.

**Its closing observation is the one worth keeping.** Both of its largest findings were places
where a round-one *correction* was adopted faithfully and the number inside it was never checked.
Two rounds agreeing reads as two confirmations; here it was one unchecked number propagating.
