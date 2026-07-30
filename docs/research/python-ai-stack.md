# Python AI stack for the AI Commander daemon

Research date: **2026-07-30**. All facts verified against primary sources (GitHub REST API, PyPI JSON API, official docs) on that date. Where a fact is time-sensitive the retrieval date is given inline.

Context: [ADR-0004](../adr/0004-ai-commander-in-python-daemon.md) puts the Commander brain in a Python daemon as a pure function `(campaign state, world observations) -> orders`, property-tested with pytest + hypothesis, with decision traces in telemetry. MVP planner is a seeded deterministic utility scorer over the Objective adjacency graph; HTN is the named escalation path. That ADR names GTPyhop, py_trees, networkx and OR-Tools as the ecosystem justification — this document checks whether those names still hold up.

---

## 1. GTPyhop (HTN / GTN planner)

### Upstream repo is dead but not rotten

`dananau/GTPyhop` has had **zero commits since 2021-07-29**. Latest commit is `1ca7773` "Added some related work.", authored `2021-07-29T18:28:52Z`. The repo is not archived, has 93 stars / 25 forks, 356 KB total size, and 2 open issues — the older (`#1` "Action durations", opened 2022-07-09) still unanswered.
Source: <https://api.github.com/repos/dananau/GTPyhop>, <https://api.github.com/repos/dananau/GTPyhop/commits>, <https://api.github.com/repos/dananau/GTPyhop/issues?state=all>

There are **no tags and no GitHub releases**, and upstream ships no `setup.py` / `pyproject.toml` — it is a source drop, not a package.
Source: <https://api.github.com/repos/dananau/GTPyhop/tags>, <https://api.github.com/repos/dananau/GTPyhop/contents>

"Dead but not rotten" is the right read: HTN planning is a settled 1990s-vintage algorithm and the code is a reference implementation attached to a 2021 HPlan workshop paper. There is no upstream bug backlog to worry about because there is essentially no upstream surface area.
Paper: <http://www.cs.umd.edu/~nau/papers/nau2021gtpyhop.pdf>

### Licence

**The Clear BSD License** (SPDX `BSD-3-Clause-Clear`), © 2021 University of Maryland. This is BSD-3-Clause plus an explicit statement that no patent rights are granted. Permissive; vendoring only requires retaining the copyright notice and licence text.
Source: <https://github.com/dananau/GTPyhop/blob/main/LICENSE.txt>, `license.spdx_id` in <https://api.github.com/repos/dananau/GTPyhop>

### Python version support

The source header states only: *"It requires Python 3."* No upper bound, no CI, no version matrix.
Source: <https://raw.githubusercontent.com/dananau/GTPyhop/main/gtpyhop.py> (line 9)

Nothing in the file constrains it: `gtpyhop.py` is **964 lines** and imports **`copy, sys, pprint, re` only** — four stdlib modules, zero third-party dependencies. There is no `random`, no `shuffle`, and no `set()`-ordering dependence in the module. That matters for this project: search order comes from method-declaration order and dict insertion order, both deterministic on CPython ≥ 3.7, so GTPyhop is compatible with the project's seeded-determinism rule without adapters.
Source (verified by inspection of the raw file): <https://raw.githubusercontent.com/dananau/GTPyhop/main/gtpyhop.py>

### Library dependency vs vendoring

**Vendor it.** The entire planner is one 964-line / 37 KB file plus a 2.2 KB `test_harness.py`; the remaining 356 KB of repo is the `Examples/` directory and `additional_information.md` (23 KB of docs worth reading but not shipping). A permissively-licensed, zero-dependency, unmaintained single file is the textbook vendoring case: pinning a PyPI release buys nothing, and vendoring gives full control over instrumentation (GTPyhop's verbosity is a module-global `print`-based affair that will need replacing with the project's telemetry logger anyway).
Source: file sizes from <https://api.github.com/repos/dananau/GTPyhop/contents>

### There IS a maintained fork, and it is on PyPI

`gtpyhop` on PyPI is at **1.9.7, uploaded 2026-05-21**, with 16 releases between 2025-07-12 and 2026-05-21 — a genuinely active cadence. Metadata: `requires_python >=3.8`, `requires_dist ["psutil>=5.8.0"]`, licence "Clear BSD License", `Development Status :: 5 - Production/Stable`, pure-Python wheel `gtpyhop-1.9.7-py3-none-any.whl`. Author emails list **Eric Jacopin \<eric.jacopin@protonmail.com\>** and **Dana Nau \<nau@umd.edu\>**; the declared Homepage is `https://github.com/PCfVW/GTPyhop/tree/pip`.
Source: <https://pypi.org/pypi/gtpyhop/json>

The fork `PCfVW/GTPyhop` (default branch `pip`, pushed 2026-05-21) describes itself as *"a refactoring of Dana Nau's GTPyhop to pip install gtpyhop; iterative seek_plan added (greedy and fully bactracking), thread-safe sessions, (psutil) memory monitoring and tracking, unified new examples"*. Its README claims 100% backward compatibility with the original module API, adds session-based concurrency, structured logging, and regression tests runnable via `python -m gtpyhop.examples.regression_tests`.
Source: <https://api.github.com/repos/PCfVW/GTPyhop>, <https://github.com/PCfVW/GTPyhop/tree/pip>

Honest caveat: the fork has **2 stars and 0 open issues** — bus factor 1, effectively no external users, no adversarial bug-finding. It also adds a `psutil` dependency for memory instrumentation the daemon does not need. Its recursion-avoiding iterative `seek_plan` is a real improvement over upstream if plan depth ever grows, and its regression tests are a useful oracle to run once against a vendored copy.

### Better-maintained HTN alternatives in Python: essentially none

| Candidate | State (2026-07-30) | Verdict |
|---|---|---|
| Pyhop (Nau, Bitbucket) | GTPyhop's ancestor, explicitly superseded by GTPyhop per upstream README | Ignore |
| PyPI `pyhop` | **Not an HTN planner** — v0.0.6 (2023-06-03) is a `traceroute` wrapper utility | Name trap; do not `pip install pyhop` |
| `pyperplan` (aibasel) | Classical STRIPS/PDDL, not HTN. **GPL-3+**, v2.1 last released 2022-01-17 | Wrong paradigm + copyleft |
| `unified-planning` (AIPlan4EU) | Apache-2.0, v1.3.0 (2025-12-17). Planner-agnostic *modelling layer*; classifiers stop at Python 3.11 | Heavy abstraction; engines are separate binaries |
| `up-aries` | MIT, v0.5.0 (2026-01-16). Aries is the credible modern hierarchical planner, shipped as a compiled engine behind unified-planning | The serious escalation if HTN-via-GTPyhop ever proves inadequate; far heavier than a vendored file |
| `ipyhop`, `htn-planner` | Not published on PyPI (HTTP 404) | Unavailable |
| InductorHtn (C++ + ctypes), fluid-htn (C#) | Non-Python cores | FFI cost not justified |

Sources: <https://pypi.org/pypi/pyhop/json>, <https://pypi.org/pypi/pyperplan/json>, <https://pypi.org/pypi/unified-planning/json>, <https://pypi.org/pypi/up-aries/json>, <https://pypi.org/pypi/ipyhop/json> (404), <https://github.com/dananau/GTPyhop#readme>

---

## 2. py_trees (behaviour trees)

**Current release: 2.5.0**, PyPI upload `2026-07-14T00:40:32Z`; GitHub release `v2.5.0` published 2026-07-14; repo last pushed 2026-07-16.
Source: <https://pypi.org/pypi/py_trees/json>, <https://api.github.com/repos/splintered-reality/py_trees/releases>

**Maintenance: alive, slow, thin.** Release history 2.2.2 (2023-01-28) → 2.3.0 (2025-01-13) → 2.4.0 (2025-11-13) → 2.5.0 (2026-07-14). A two-year gap 2023→2025 followed by three releases in 18 months. 627 stars, 189 forks, 28 open issues. Two named maintainers (Daniel Stonier, Sebastian Castro). 2.5.0 modernised the project onto `uv`/`hatchling` and added typed input/output ports for behaviours.
Source: <https://api.github.com/repos/splintered-reality/py_trees>, <https://pypi.org/pypi/py_trees/json> (release index), <https://github.com/splintered-reality/py_trees/blob/devel/pyproject.toml>

**Licence: BSD-3-Clause.** `pyproject.toml` declares `license = { text = "BSD-3-Clause" }`; `LICENSE` is a "Software License Agreement (BSD License)", © 2020 Daniel Stonier. Note the GitHub API reports `NOASSERTION` — that is a licence-file-header detection artefact, not a licence problem.
Source: <https://github.com/splintered-reality/py_trees/blob/devel/LICENSE>, <https://github.com/splintered-reality/py_trees/blob/devel/pyproject.toml>

**Python support: 3.10+.** `requires-python` is deliberately commented out in `pyproject.toml` (a documented `colcon build` workaround), but the comment reads `">=3.10,<4.0"`, `[tool.ruff] target-version = "py310"`, `[tool.ty.environment] python-version = "3.10"`, and the README CI matrix covers 3.10 / 3.12 / 3.14.
Source: <https://github.com/splintered-reality/py_trees/blob/devel/pyproject.toml>, <https://github.com/splintered-reality/py_trees/blob/devel/README.md>

**Not ROS-coupled.** The only runtime dependency is `pydot>=1.4`. ROS integration lives in the separate `py_trees_ros` / `py_trees_ros_viewer` packages; the core library "functions independently of ROS".
Source: `requires_dist` in <https://pypi.org/pypi/py_trees/json>, <https://github.com/splintered-reality/py_trees/blob/devel/README.md>

### Fit for a tick-based strategic planner

Good on mechanics, questionable on value.

Arguments for:
- The execution model is exactly tick-based and caller-driven. `BehaviourTree.tick()` lets you "create your own loop and tick at your own leisure"; `tick_tock(period_ms, number_of_iterations, pre_tick_handler, post_tick_handler)` with `CONTINUOUS_TICK_TOCK` is the *opt-in* timer path, not the only path. A 60-second income tick driving one `tick()` is idiomatic use, not a workaround.
  Source: <https://py-trees.readthedocs.io/en/devel/trees.html>
- Visitors (`SnapshotVisitor`, `DebugVisitor`) plus pre/post-tick handlers are a first-class hook for exactly the decision-trace telemetry ADR-0004 requires, with the documented use case "introspection on the tree to make reports".
  Source: <https://py-trees.readthedocs.io/en/devel/trees.html>
- Self-declared target is "medium scale decision engines that do not need to be real time reactive", scaling to "maximally in the order of hundreds of behaviours" — comfortably above 6–10 Objectives. The docs explicitly call behaviour trees "a decision making engine often used in the gaming and robotics industries".
  Source: <https://py-trees.readthedocs.io/en/devel/introduction.html>

Arguments against, for the MVP:
- A behaviour tree is a **reactive execution formalism, not an allocator**. It sequences, guards and prioritises; it will not decide *which* squad goes to *which* Objective. The MVP's decision content is a utility score over Objectives — a BT wraps that in a tree-authoring layer while contributing no decision logic.
- The Blackboard is process-global keyed state with namespacing. That is in direct tension with ADR-0004's "planner is a pure function" contract and with clean hypothesis property tests; you would need discipline (or a per-tick blackboard reset harness) to keep tests hermetic.
- `pydot` is a dependency you inherit for graph rendering you may never use.

Verdict for py_trees: correct library if and when the Commander grows *modes* (opening / attrition / defend-the-base / endgame push) that need reactive arbitration and interruption. Premature for a utility scorer.

---

## 3. networkx (graph reasoning)

**Current version: 3.6.1**, released 2025-12-08. Docs "stable" header reads `Release: 3.6.1, Date: Dec 08, 2025`. Current major series is **3.x**; there is no 4.x. Repo last pushed 2026-07-24 (17.1k stars, 3.6k forks), so 3.7 is in development on `main`.
Source: <https://pypi.org/pypi/networkx/json>, <https://networkx.org/documentation/stable/>, <https://api.github.com/repos/networkx/networkx>

**Licence: BSD-3-Clause** (`license_expression` in PyPI metadata). **`requires_python = ">=3.11,!=3.14.1"`** — note the 3.11 floor (SPEC-0 deprecation policy); a 3.12 daemon is fine.
Source: <https://pypi.org/pypi/networkx/json>

Zero-dependency pure-Python wheel (`networkx-3.6.1-py3-none-any.whl`). SciPy and NumPy are optional extras that some algorithms require — see the matching note below.

### Relevant algorithms for weighted adjacency-graph reasoning

Objective adjacency with `weight` = travel cost / distance / risk.

**Shortest paths — reachability, approach routing, "how far is the front"**
- Index: <https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html>
- `dijkstra_path(G, source, target, weight="weight")` — single weighted route: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.weighted.dijkstra_path.html>
- `all_pairs_dijkstra_path_length(G, weight="weight")` — precompute the full Objective×Objective cost matrix once per campaign; this is the input to any assignment cost function: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.weighted.all_pairs_dijkstra_path_length.html>
- `astar_path(G, source, target, heuristic, weight="weight")` — if map-distance heuristics are wanted: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.astar.astar_path.html>

**Centrality — which Objectives are strategically worth more than their income value**
- Index: <https://networkx.org/documentation/stable/reference/algorithms/centrality.html>
- `betweenness_centrality(G, weight="weight")` — identifies chokepoints; a high-betweenness town is the one whose loss splits your territory: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.betweenness_centrality.html>
- `closeness_centrality(G, distance="weight")` — how quickly a held Objective can project force everywhere: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.closeness_centrality.html>

**Cuts — "which single Objective severs the enemy's map", front-line detection**
- `stoer_wagner(G, weight="weight")` — global minimum cut of an undirected weighted graph, returns `(cut_value, partition)`. The natural way to ask "where is the natural front line on Stratis": <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.connectivity.stoerwagner.stoer_wagner.html>
- `minimum_cut(flowG, s, t, capacity="capacity")` — s-t min cut / max-flow, for "what is the narrowest corridor between my Base and theirs": <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.flow.minimum_cut.html>

**Matching — squads to Objectives without leaving networkx**
- `bipartite.minimum_weight_full_matching(G, top_nodes, weight="weight")` — solves the rectangular m×n linear assignment problem, "allow[s] |U| and |V| to differ", returns a dict of matched nodes. **This implementation "defers the calculation of the assignment to SciPy" and raises `ImportError` without it.** For 10 squads × 10 Objectives this is the whole assignment problem, solved: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.bipartite.matching.minimum_weight_full_matching.html>
- `max_weight_matching(G, maxcardinality=False, weight="weight")` — general (non-bipartite) weighted matching, pure Python: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.matching.max_weight_matching.html>

**Territory / frontier bookkeeping**
- `connected_components(G)` on the owned-Objective subgraph — detects a cut-off pocket: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.components.connected_components.html>
- `boundary_expansion(G, S)` — the node boundary of a held set, i.e. the contact surface with the enemy: <https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.cuts.boundary_expansion.html>

No maintenance doubt, as stipulated. The one genuine decision here is whether to accept SciPy as a dependency to get `minimum_weight_full_matching`.

---

## 4. Google OR-Tools

**Current version: `ortools` 9.15.6755**, uploaded to PyPI 2026-01-14; upstream tag `v9.15` published 2026-01-12. The repo is very much alive — `google/or-tools` last pushed **2026-07-30** (the day of this research), 13.8k stars, default branch `stable`.
Source: <https://pypi.org/pypi/ortools/json>, <https://api.github.com/repos/google/or-tools/releases>, <https://api.github.com/repos/google/or-tools>

**Licence: Apache-2.0** — the repo's SPDX id, and PyPI classifier `License :: OSI Approved :: Apache Software License`. Note this is the only non-BSD/MPL licence in the candidate stack; Apache-2.0 carries a NOTICE-file obligation on redistribution.
Source: <https://api.github.com/repos/google/or-tools>, <https://pypi.org/pypi/ortools/json>

**Python bindings: healthy and current.** `requires_python = ">=3.9"`, classifiers cover **3.9, 3.10, 3.11, 3.12, 3.13, 3.14** plus free-threaded `cp313t`/`cp314t` builds. v9.15 dropped Python 3.8 and added 3.14. The bindings are SWIG/pybind11-generated over the C++ core, published as per-interpreter binary wheels.
Source: <https://pypi.org/pypi/ortools/json>, <https://github.com/google/or-tools/releases/tag/v9.15>

### Python 3.12 Linux wheel availability — yes

Published for 9.15.6755:

```
ortools-9.15.6755-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl   (29,838,435 bytes)
ortools-9.15.6755-cp312-cp312-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl
```
Source: `urls[]` in <https://pypi.org/pypi/ortools/json>

So `pip install ortools` on x86-64 Linux / Python 3.12 gets a **~30 MB prebuilt wheel**, no compilation. The `manylinux_2_28` tag implies **glibc ≥ 2.28** (RHEL 8 / Ubuntu 20.04 and newer) — satisfied by any WSL2 Ubuntu image relevant to [ADR-0006](../adr/0006-wsl2-linux-server-test-tier.md).

**Dependency weight is the real cost:** `absl-py>=2.0.0`, `numpy>=2.0.2`, `pandas>=2.0.0`, `protobuf>=6.33.1,<6.34`, `typing-extensions>=4.12`, `immutabledict>=3.0.0`. The **narrow `protobuf<6.34` pin** is the one to watch — it is a live source of resolver conflicts in any daemon that also talks protobuf/gRPC.
Source: `requires_dist` in <https://pypi.org/pypi/ortools/json>

### Solvers for squads-to-objectives allocation

Ranked by fit to the actual problem shape.

**1. `SimpleLinearSumAssignment` — the exact one-squad-one-objective case**
```python
from ortools.graph.python import linear_sum_assignment
```
Class `SimpleLinearSumAssignment`; API `add_arcs_with_cost(start_nodes, end_nodes, arc_costs)`, `solve()`, `optimal_cost()`, `right_mate(worker_index)`, `assignment_cost(worker_index)`. Solves square *or* rectangular bipartite minimum-cost matching. Status codes `OPTIMAL`, `INFEASIBLE`, `POSSIBLE_OVERFLOW`. **Integer weights only** — "the linear sum assignment solver only accepts integer values for the weights and values", so a float utility score must be quantised (which is arguably a feature given the determinism requirement).
Source: <https://developers.google.com/optimization/assignment/linear_assignment>

**2. `min_cost_flow` — the shape CTI actually has**
```python
from ortools.graph.python import min_cost_flow
```
Objectives are not one-to-one sinks: an Objective may want 2 squads, a Base may want 1 defender, and squads are fungible. Modelling squads as supply nodes and Objectives as demand nodes with capacities is a min-cost-flow problem, and OR-Tools' `SimpleMinCostFlow` handles it directly. This is the recommended generalisation once "how many squads does this town need" enters the model.
Source: <https://developers.google.com/optimization/flow/mincostflow>

**3. CP-SAT — once side constraints appear**
```python
from ortools.sat.python import cp_model
```
`cp_model.CpModel()`. This is where Funds budget limits, "never leave the Base undefended", group/team constraints and reachability restrictions go. Google's own assignment docs present CP-SAT (and the MIP wrapper) as the two recommended assignment solvers, with a dedicated page for grouped/team-constrained assignment. CP-SAT is also where v9.15's engineering effort went.
Sources: <https://developers.google.com/optimization/assignment/assignment_example>, <https://developers.google.com/optimization/assignment/assignment_teams>, <https://developers.google.com/optimization/cp/cp_solver>

**4. MIP wrapper**
```python
from ortools.linear_solver import pywraplp
```
`pywraplp.Solver` with the SCIP backend — the LP/MIP formulation of assignment. Rarely the right first choice here.
Source: <https://developers.google.com/optimization/assignment/assignment_example>

**Honest sizing note:** at MVP scale (6–10 Objectives, on the order of 10 squads) the assignment problem is trivially small. `networkx.bipartite.minimum_weight_full_matching` (SciPy-backed Hungarian) or `scipy.optimize.linear_sum_assignment` solves it in microseconds with a dependency you may already want. OR-Tools earns its 30 MB and its protobuf pin only when the model gains real constraints — budget coupling, per-Objective capacities, multi-tick sequencing — at which point CP-SAT has no Python competitor.

---

## 5. Open-source RTS-commander / wargame-AI Python frameworks

Short answer: **there is no reusable RTS-commander library.** Everything in this space is a *game environment* (you plug an agent into their game) or a *research harness* (you reproduce their paper). The transferable assets are algorithms and ideas, not importable code. Detail, worst-to-best on reusability:

| Project | Language / licence | State (2026-07-30) | Reusable as a library? |
|---|---|---|---|
| **microRTS** `santiontanon/microrts` | Java, **GPL-3.0** | **Deprecated 2025-08-11**: "deprecated due to a lack of wide spread community use, and is no longer planned to receive any additional updates or support". 357 stars | No. Wrong language, copyleft, dead |
| **MicroRTS-Py** `Farama-Foundation/MicroRTS-Py` | Python, MIT | **Deprecated 2025-08-11** (same notice). Last push 2025-08-11, 289 stars. Requires **Java 8+ JVM** and Poetry | Technically importable, but it is a JVM-backed RL env for *their* grid RTS. The abstraction is a `(observation tensor, action tensor)` gym interface — nothing about commanders or objectives |
| **pysc2** `google-deepmind/pysc2` | Python, Apache-2.0 | Dormant: last push 2024-07-23, PyPI 4.0.0 released 2022-07-14. 8.3k stars | No. It is a protobuf wrapper around the *commercial* StarCraft II binary. Zero planner content — the AI is entirely yours |
| **Deep RTS** `cair/deep-rts` | C++, MIT | Dormant: last push 2023-05-16, 249 stars, build from source | No |
| **Griddly** `Bam4d/Griddly` | C++, MIT | Dormant: last push 2024-04-09; PyPI 1.6.7 released 2023-03-15 | No. Grid-world engine, not adjacency-graph strategy |
| **Stratega** `GAIGResearch/Stratega` | C++ + pybind, no licence file detected | Semi-active: last push 2025-06-10, 55 stars; PyPI `stratega` 0.3.1 released 2022-07-07 | Conceptually the closest thing that exists — an academic turn-based/real-time strategy framework with units, objectives and portfolio/MCTS agents. But you adopt *their* game engine and rules, not their AI as a library. Missing licence file is a blocker on its own |
| **CivRealm** | Python, **GPL-3.0** | PyPI 0.1.2 released 2024-01-26 | No. Welded to Freeciv-web |
| **`diplomacy`** (SHADE/DipNet engine) | Python, **AGPL-3.0+** | **Abandoned**: PyPI 1.1.2 released 2020-04-13, `requires_python >=3.5` | No, and the AGPL rules it out anyway. Noted only because it is the closest *data model* to "objectives on an adjacency graph with per-province ownership" — read it for modelling ideas, never copy code |
| **python-sc2 / `burnysc2`** | Python, MIT | **Maintained**: 7.3.0 released 2026-04-24, `>=3.9,<3.15`, last push 2026-04-25, 629 stars | Well-maintained, but it is an SC2 protocol client. Its bot-authoring ergonomics (unit-group abstractions, `on_step` tick loop) are worth reading as design precedent |
| **OpenSpiel** `google-deepmind/open_spiel` | C++ + Python, Apache-2.0 | **Actively maintained**: last push 2026-07-17, PyPI `open-spiel` 2.0.1 released 2026-07-17, `requires_python >=3.11`, 5.4k stars | The one genuine candidate. Its MCTS / IS-MCTS / CFR implementations are usable against *your* game — but only if you implement OpenSpiel's `Game`/`State` interface (legal-action enumeration, cloneable state, terminal/returns). That is real work and demands a fully enumerable action space. Credible **post-MVP** route to adversarial search; wrong for MVP |

Sources: <https://github.com/santiontanon/microrts>, <https://github.com/Farama-Foundation/MicroRTS-Py>, <https://api.github.com/repos/google-deepmind/pysc2>, <https://api.github.com/repos/cair/deep-rts>, <https://api.github.com/repos/Bam4d/Griddly>, <https://api.github.com/repos/GAIGResearch/Stratega>, <https://pypi.org/pypi/stratega/json>, <https://pypi.org/pypi/civrealm/json>, <https://pypi.org/pypi/diplomacy/json> (AGPLv3+ classifier), <https://pypi.org/pypi/burnysc2/json>, <https://api.github.com/repos/google-deepmind/open_spiel>, <https://pypi.org/pypi/open-spiel/json>

**The uncomfortable conclusion, stated plainly:** the two projects closest to this problem (microRTS and MicroRTS-Py) were both deprecated on the same day in August 2025 for lack of community use. This corner of game-AI research has consolidated into the general RL-environment ecosystem (Gymnasium 1.3.0 / PettingZoo 1.26.1, both MIT and actively released in April 2026), which offers interfaces for *training* agents, not for *commanding* armies. The genuinely reusable pieces of RTS AI — influence maps, potential fields, portfolio search, hierarchical task decomposition — are a few dozen lines each on top of networkx, which is why nobody packages them.
Sources: <https://pypi.org/pypi/gymnasium/json>, <https://pypi.org/pypi/pettingzoo/json>

---

## 6. hypothesis (property-based testing)

**6.163.1, released 2026-07-30** (the day of this research — releases land near-daily; the repo was pushed 2026-07-30 and 6.161.7 → 6.163.1 all shipped within four days), **MPL-2.0**, `requires_python >=3.10`, classifiers include Python 3.12/3.13/3.14, and `cp312` manylinux/musllinux/win/macOS wheels are published. Zero maintenance risk.
Source: <https://pypi.org/pypi/hypothesis/json>, <https://api.github.com/repos/HypothesisWorks/hypothesis/releases>

---

## Compatibility summary for a Python 3.12 daemon

| Package | Version | Licence | Py 3.12 | Runtime deps | Verdict |
|---|---|---|---|---|---|
| `networkx` | 3.6.1 (2025-12-08) | BSD-3-Clause | yes (`>=3.11`) | none (SciPy optional) | **Adopt now** |
| `hypothesis` | 6.163.1 (2026-07-30) | MPL-2.0 | yes | few | **Adopt now** |
| GTPyhop | upstream frozen 2021-07-29 / PyPI `gtpyhop` 1.9.7 (2026-05-21) | Clear BSD | yes (stdlib only) | none if vendored | **Vendor when HTN is needed** |
| `ortools` | 9.15.6755 (2026-01-14) | Apache-2.0 | yes, 30 MB wheel | absl-py, numpy, pandas, protobuf<6.34, immutabledict | **Defer until constraints are real** |
| `py_trees` | 2.5.0 (2026-07-14) | BSD-3-Clause | yes (`>=3.10`) | pydot | **Defer until Commander has modes** |
| OpenSpiel | 2.0.1 (2026-07-17) | Apache-2.0 | yes (`>=3.11`) | heavy | **Post-MVP adversarial search only** |

---

## VERDICT

**MVP stack: `networkx` 3.6.1 + `hypothesis` 6.163.1 + the standard library, and nothing else.** ADR-0004's four-library shortlist survives scrutiny on maintenance grounds — every one of GTPyhop, py_trees, networkx and OR-Tools is licence-clean, Python 3.12-clean, and either actively maintained or so small and frozen that maintenance is moot — but three of the four are answers to questions the MVP has not yet asked. The MVP planner is a seeded deterministic utility scorer over 6–10 Objectives: networkx supplies literally every graph primitive that scorer needs (`all_pairs_dijkstra_path_length` for the cost matrix, `betweenness_centrality` for chokepoint valuation, `stoer_wagner` for front-line detection, `boundary_expansion` for contact surface) with zero runtime dependencies and no determinism hazards, and `bipartite.minimum_weight_full_matching` solves squads-to-objectives optimally at this scale — accept SciPy as the one extra dependency rather than 30 MB of OR-Tools plus a `protobuf<6.34` pin that will eventually fight something else in the daemon. Hold OR-Tools until the allocation genuinely acquires constraints the Hungarian algorithm cannot express (Funds budget coupled to assignment, per-Objective squad capacities, multi-tick sequencing), at which point go straight to `min_cost_flow` for capacities and CP-SAT for everything harder. Hold py_trees until the Commander needs reactive *modes* rather than a single scoring pass, and be aware its process-global Blackboard is in tension with ADR-0004's pure-function contract. When HTN escalation arrives, **vendor** the upstream 964-line `gtpyhop.py` under its Clear BSD notice rather than depending on the PyPI package: it imports only four stdlib modules, contains no randomness, and the sole maintained fork (`PCfVW/GTPyhop`, PyPI `gtpyhop` 1.9.7) is a two-star single-maintainer effort whose regression suite is more valuable to you as a one-off oracle than as a supply-chain dependency. Finally, abandon any hope of reusing an existing RTS-commander framework — microRTS and MicroRTS-Py were both deprecated on 2025-08-11 for lack of use, pysc2 has been dormant since 2024, and the only live option (OpenSpiel) demands you implement its `Game`/`State` interface before it gives you anything; the reusable content in that literature is ideas, and those cost a few dozen lines on top of networkx.
