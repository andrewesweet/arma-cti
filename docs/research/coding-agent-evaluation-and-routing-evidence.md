# How to tell which coding-agent profile suits which task, and whether this repo can measure it

**Researched**: 2026-08-05
**Question** (R3): the project is building infrastructure to dispatch logical subagents onto non-Anthropic coding subscriptions (OpenAI Codex, z.ai GLM Coding Plan). Two rulings from the 2026-08-05 grilling govern how the resulting guidance gets evidence behind it — ruling 9 (no eval corpus, no LLM-as-judge; randomise lane assignment and read the project's existing gates) and ruling 17 (`(lane, model, effort)` is one opaque categorical arm). Do they survive contact with the literature, and does Inspect change the answer?
**Answer in one line**: **both rulings survive, but ruling 9's design as written cannot produce a signal at this repo's landing rate** — an unpaired randomised comparison of two profiles on a binary gate outcome needs roughly 160–700 landed issues, which is one to three years here; the fix is not a benchmark or an eval harness but a **change of design to paired dual-run**, where both profiles attempt the same issue and only the sign of the difference is recorded, cutting the requirement to about **30 issues**.

Inspect is real, it is a genuinely good fit for the *mechanics* of what ruling 9 declined to build, and it still does not rescue the corpus idea — its agent bridge routes the CLI agent's model calls through Inspect's own model provider, which bills the API rather than the coding subscription that is the entire point of the exercise.

---

## 0. Method and evidence classes

Every claim below carries one of three markers:

- **[primary]** — read from the owning source: official documentation, the paper itself, or the project's own repository files.
- **[documented]** — stated by a primary source but not verified against a running system here. Nothing in this document was executed.
- **[inferred]** — my reasoning over primary facts, including all arithmetic in §4. Not a citation.

Nothing here was measured on this machine. The arithmetic in §4 is standard power analysis, shown in full so it can be checked rather than trusted.

---

## 1. Inspect (UK AISI) — what it actually is

### 1.1 The unit of work

Inspect is "a framework for frontier AI evaluations developed by the UK AI Security Institute and Meridian Labs" **[primary**, https://inspect.aisi.org.uk/**]**. The organising unit is a **Task**, composed of three parts **[primary]**:

- a **Dataset**, which "provides labelled samples—typically a table with `input` and `target` columns";
- a **Solver**, which "produces an answer for each sample";
- a **Scorer**, which "evaluates the output—using text comparisons, model grading, or other custom schemes".

The `Sample` class carries `input`, `choices`, `target`, `id`, `metadata`, `sandbox`, `files`, `setup`, and `checkpoint`. Only `input` is genuinely required; **`target` defaults to an empty string** and every other field admits `None` **[primary**, https://inspect.aisi.org.uk/reference/inspect_ai.dataset.html**]**.

That last detail matters more than it looks. A framework whose sample type demands a ground-truth answer would be structurally unable to score a live repository task, where no target exists. Because `target` is optional, a scorer is free to be a pure gate-runner — run `just fast` in the sandbox, return pass or fail — with no reference answer anywhere. **Inspect does not require an answer key.** [primary for the field, inferred for the consequence]

### 1.2 Can it evaluate an agent on a real repository?

Yes, and more directly than expected. Sandboxing provisions "dedicated environments for running tool code", typically Docker, and "Each sample gets its own sandbox instance, even if the sandbox is defined at Task level. So samples do not interfere with each other's sandboxes" **[primary**, https://inspect.aisi.org.uk/sandboxing.html**]**. Sample metadata interpolates into the compose file under a `SAMPLE_METADATA_` prefix, so a per-sample repository checkout is a supported shape **[primary]**.

More to the point, the agent-bridge documentation states outright that you can "use CLI based agents that run within sandboxes (e.g. Claude Code, Codex CLI, or Gemini CLI)" **[primary**, https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/main/docs/agent-bridge.qmd**]**. That is precisely this project's shape: a coding CLI, in a container, on a checkout.

### 1.3 The bridge is the problem

The mechanism defeats the purpose. "The sandbox bridge works via running a proxy server inside the sandbox container which receives requests for the OpenAI, Anthropic, and Google APIs. This proxy server in turn relays requests to the current Inspect model provider" **[primary]**. Agents are configured with `OPENAI_BASE_URL=http://localhost:13131/v1`, `ANTHROPIC_BASE_URL=http://localhost:13131`, `GOOGLE_GEMINI_BASE_URL=http://localhost:13131/v1beta` **[primary]**.

A bridged Codex CLI is therefore not running on the Codex subscription. It is running on whatever provider Inspect is configured with, billed per token. The project's whole premise is that a subscription's included capacity is cheaper than metered API access; bridging converts every eval run back into API spend. [inferred, but the inference is short]

The bridge also drops client generation parameters by default — `max_tokens`, `temperature`, `top_p` — because "Those values are therefore targeted for the wrong model, and forwarding them can produce incorrect or even failing requests" **[primary]**. Only structural parameters (system prompt, tools, tool choice, response format, stop sequences, seed) are forwarded **[primary]**. This is honest engineering, and it is also an admission that the bridged agent is not the agent you deployed: its own generation settings are discarded, and effort settings — the very thing ruling 17 declines to compare across providers — are among the parameters the bridge is not designed to carry faithfully.

**The bridge is optional.** Nothing stops a solver from calling `sandbox().exec()` on a CLI that authenticates with its own credentials, using Inspect purely as a dataset iterator, sandbox provisioner, scorer, and log store. That path keeps the subscription economics intact and loses only Inspect's model-call transcript. [inferred from the documented `sandbox()` interface; not documented as a supported pattern]

### 1.4 Can it score a run that happened elsewhere?

Partly, and the honest answer is narrower than the marketing.

Deferred scoring is real: `inspect eval … --no-score` produces unscored logs, and `inspect score ./logs/….eval` applies scorers afterward, with `--scorer` to name an alternative, `-S` for scorer arguments, `--overwrite`, and `--action append|overwrite` to control how new scores meet old ones **[primary**, https://inspect.aisi.org.uk/scoring-workflow.html**]**. The documentation says "Any evaluation log can be scored using this approach, including logs originally created without scoring" **[primary]** — but "any evaluation log" means any *Inspect* log.

For a run that Inspect never drove, you would have to synthesise the log. `EvalLog` and `EvalSample` are Pydantic `BaseModel` classes, and `write_eval_log(log, location, format, …)` is public API **[primary**, https://inspect.aisi.org.uk/reference/inspect_ai.log.html**]**, so construction is mechanically possible. But the documentation provides no guidance on building `EvalLog` objects from scratch, and warns that "The variability in underlying file format makes it especially important that you use the Python Log File API for reading and writing log files" **[primary**, https://inspect.aisi.org.uk/eval-logs.html**]**. Treating a public dataclass as a stable ingestion contract, against a binary format explicitly flagged as variable, is a maintenance liability. **[inferred]**

**Verdict on ingestion: Inspect wants to drive the run.** Post-hoc scoring of an externally produced dispatch is not a supported path.

### 1.5 Fit for continuous evaluation on live work

No. Inspect is a batch runner over a fixed dataset: you write a dataset, run the task, read the log. There is no documented facility for observing production traffic, and the `Task` abstraction assumes a set of samples known in advance.

That is not a defect — it is what an eval framework is. But it means Inspect's honest role here is **to make building an eval corpus cheaper, not to make one unnecessary**. And a corpus is exactly what ruling 9 declined.

### 1.6 What Inspect costs to adopt

For a handful of task classes: Docker on the host; one compose file per task class; a dataset module; a solver that shells out to each lane's CLI; a scorer that runs the repo's gates in the sandbox and maps the exit code to a score. `max_sandboxes` bounds parallelism and "effectively creates a global `max_samples` limit that is equal to the `max_sandboxes`" **[primary]**.

Two costs are specific to this repo and are not small. First, the in-world half of the gates cannot go in a container: `just regress` needs an Arma server, a slot lock at `~/.arma-cti/slots/N.lock`, and a p90 wall of about 1,230 s. Only the no-Arma tier (`just check`, `just unit`) is containerisable, so an Inspect scorer would grade against a strictly weaker gate than the one the project actually trusts. Second, **an eval task is burned the first time it is solved** — its fix lands in git, and thereafter every lane can read the answer. [inferred; the slot and wall figures are primary, from `CLAUDE.md` and `.claude/hooks/deny-subagent-waits.py`]

---

## 2. Coding-agent benchmarks — none substitutes for measuring here

| Benchmark | What it measures | Scale | Transfer to this repo |
|---|---|---|---|
| SWE-bench | "Given a codebase along with a description of an issue to be resolved, a language model is tasked with editing the codebase to address the issue" **[primary**, arXiv 2310.06770**]** | "2,294 software engineering problems drawn from real GitHub issues and corresponding pull requests across 12 popular Python repositories" **[primary]** | Poor, and contaminated (§2.1) |
| SWE-bench Pro | Same task shape, "explicitly designed to capture realistic, complex, enterprise-level problems beyond the scope of SWE-BENCH"; "long-horizon tasks that may require hours to days for a professional software engineer" **[primary**, arXiv 2509.16941**]** | 1,865 problems, 41 repositories, split public (11 repos) / held-out (12) / commercial (18) **[primary]** | Better methodology, same domain mismatch |
| Terminal-Bench | "a collection of harbor-native benchmarks to help agent makers quantify their agents' terminal mastery"; Docker per task with test criteria **[primary**, https://www.tbench.ai/**]** | 89 tasks at v2.0/2.1 (80 at 1.0) **[primary]** | Closest in shape to the harness work (`spike/`, `tools/`), still not the domain |
| Aider polyglot | "225 challenging Exercism coding exercises across C++, Go, Java, JavaScript, Python, and Rust"; scores pass rate, percent correct, and edit-format compliance **[primary**, https://aider.chat/docs/leaderboards/**]** | 225 self-contained exercises | Weakest — self-contained puzzles, no repository context |
| METR time horizon | "50%-task-completion time horizon" against timed human baselines, over "RE-Bench, HCAST, and 66 novel shorter tasks" **[primary**, arXiv 2503.14499**]** | Frontier horizon "doubling approximately every seven months since 2019" **[primary]** | Useful as a capability prior; not a per-task predictor |

### 2.1 Contamination is documented, not speculative

The SWE-Bench Illusion study is the sharpest evidence. Models were asked to identify buggy file paths **from the issue description alone**, with repository structure and code withheld. State-of-the-art models reached **up to 76% accuracy on SWE-Bench-Verified instances**, against **53% on tasks from repositories not in SWE-Bench** **[primary**, arXiv 2506.12286**]**. The authors conclude that "These findings raise concerns about the validity of existing results and underscore the need for more robust, contamination-resistant benchmarks to reliably evaluate LLMs' coding abilities" **[primary]**.

Independent work reports that on SWE-bench, 32.67% of successful patches involve direct solution leakage and 31.08% pass because of inadequate tests **[documented** — reported in the SWE-MERA/SWE-rebench line of work surfaced by search, not read at the owning source**]**.

SWE-bench Pro's three-way partition (public / held-out / commercial) exists precisely to answer this, producing "a contamination-resistant testbed" **[primary]**. That makes it the most trustworthy published ranking of the five — and it still does not measure what this project needs.

### 2.2 Why no published ranking substitutes for measuring here

Four independent reasons, each sufficient on its own **[inferred]**:

1. **Wrong languages.** Every benchmark above is Python, or Python plus mainstream compiled languages. This repo's largest correctness surface is SQF against the Arma engine, plus a Python daemon, a Rust shim, and bash harness code. No public benchmark contains SQF.
2. **Wrong verification.** The gates that decide whether work is good here include a twenty-minute in-world regression corpus with a typed failure class per probe. No benchmark's pass criterion resembles that.
3. **Wrong unit.** Published leaderboards rank *models*. Ruling 17's arm is a `(lane, model, effort)` profile — the same model at a different effort, reached through a different lane's CLI and its own harness, is a different arm, and no leaderboard reports that cell.
4. **Wrong constraints.** A large share of what makes work good in this repo is compliance with `CLAUDE.md` — the worktree protocol, the failure-class table, the five-minute rule, ADR number claiming. A benchmark score says nothing about whether a profile follows a project's own written process.

**Rankings are worth exactly one thing: a prior for seeding the initial static profile→seat table.** Start GLM or Codex where its published standing suggests, then let local evidence move it. That is a legitimate and cheap use, and it is not measurement.

---

## 3. Learned routing — the literature does not support it at this scale

**RouteLLM** trained four routers (similarity-weighted ranking, matrix factorization, a BERT classifier, and a causal LLM classifier on Llama 3 8B) on **80k battles from the online Chatbot Arena platform**, pruned to **65k pairwise comparisons between 64 different models**, with 5k held out for validation **[primary**, arXiv 2406.18665v3**]**. Data augmentation added roughly **1,500 golden-labelled questions** from the MMLU validation split and roughly **120K LLM-judge-labelled samples at a cost of around $700 USD** **[primary]**. Reported cost reductions at the 50% call-performance threshold: 13.40% (matrix factorization) and 19.58% (BERT) on MT Bench; approximately 35.40%–41.30% across routers on MMLU; 33.64% (causal LLM) on GSM8K; "up to 3.66x" cost savings overall **[primary]**.

**RouterBench** assembles "over 405,000 inference outcomes" as "a novel evaluation framework designed to systematically assess the efficacy of LLM routing systems" **[primary**, arXiv 2403.12031**]**.

The scale gap is not close. The smallest labelled set in RouteLLM's pipeline is ~1,500 examples; the preference corpus is 65,000; RouterBench is 405,000 outcomes. This project lands **a handful of issues per week**. Even three years of perfect telemetry would not reach RouteLLM's *smallest* augmentation set.

I found no peer-reviewed work training a cost-quality router for code tasks at n in the tens or low hundreds, and no work claiming a learned router beats a static policy in that regime. **[inferred from absence — treat as weaker than a positive finding]**

**Ruling 17 survives, and the literature gives it a second justification the ruling did not claim.** The stated reason was that effort scales are not commensurable across providers, which is true and sufficient. The stronger reason is statistical: treating `(lane, model, effort)` as a factorial design multiplies arms, and §4 shows that arm count is the binding constraint on whether this project can measure anything at all. Collapsing three factors into one categorical label is the only choice that keeps the arm count low enough to be measurable. Marginal effects of "effort" or "lane" independently are not estimable here and will not become estimable.

---

## 4. Experimental method — ruling 9's design, costed

This section is arithmetic over the project's own landing rate. All of it is **[inferred]**; the inputs are stated so it can be rechecked.

### 4.1 What comparable studies needed

- **METR's developer RCT**: 16 experienced open-source developers, **246 tasks**, randomised **per issue** to allow or disallow AI tooling. Result: "When developers are allowed to use AI tools, they take 19% longer to complete issues", with clustered standard errors accounting for the 16 developers **[primary**, https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ and arXiv 2507.09089**]**. Developers forecast a 24% speedup and, afterwards, still believed they had been sped up by 20% **[primary]**.
- **Peng et al.'s Copilot RCT**: a single controlled task ("implement an HTTP server in JavaScript as quickly as possible"), treatment group "completed the task 55.6% faster than the control group" **[primary**, arXiv 2302.06590**]**.

The METR figure is the relevant precedent, because its design is the one ruling 9 proposes: randomise at the task level, measure an outcome the existing workflow already produces. It needed **246 tasks to characterise a 19% effect** — and 19% is a large effect for developer tooling.

The Peng result is the cautionary contrast: a much larger apparent effect (55.6%) from a *single, homogeneous* task. The gap between the two is task heterogeneity, and this project's issues are far more heterogeneous than either — a CHANGELOG sweep and a planner defect are not the same experiment.

### 4.2 What ruling 9's design needs here

Assume 5 landed issues per week, which is a generous reading of "a handful". Standard two-sided test, α = 0.05, power 0.80, so `(z_{α/2} + z_β)² = (1.96 + 0.84)² = 7.85`.

**Binary outcome** (e.g. "first gate cycle green"), two arms, per-arm n = `7.85 × [p₁(1−p₁) + p₂(1−p₂)] / (p₁−p₂)²`:

| Effect | Per arm | Total issues | Weeks at 5/wk |
|---|---:|---:|---:|
| 0.60 → 0.70 (10 pp) | 353 | 706 | 141 (≈2.7 yr) |
| 0.60 → 0.80 (20 pp) | 79 | 158 | 32 (≈7 mo) |

**Continuous or count outcome** (e.g. gate cycles to first green), per-arm n = `2 × 7.85 / d²` for Cohen's d:

| Effect size | Per arm | Total issues | Weeks at 5/wk |
|---|---:|---:|---:|
| d = 0.5 (medium) | 63 | 126 | 25 (≈6 mo) |
| d = 0.8 (large) | 25 | 50 | 10 (≈2.5 mo) |

Three profiles rather than two multiply the total and add a multiple-comparison penalty. Task heterogeneity inflates the variance further, pushing every row upward — the tables are optimistic.

**Conclusion: ruling 9's design as written will detect only a large effect on a count-like outcome, over about a quarter, with two arms.** For anything subtler, or for three arms, or on a binary gate outcome, the answer arrives in years. This is a finding, not a failure — but the ruling should not be read as promising a profile ranking on any useful timescale.

### 4.3 Interleaving does not transfer

The obvious rescue from the information-retrieval literature is interleaving, and its sensitivity gains are large and well attested. Airbnb reports that its combined approach "increased the sensitivity of experiments by a factor of up to 100 (depending on the approach and metrics) compared to traditional A/B testing", with "about 50X speedup from A/B" for interleaving specifically, and cites Amazon's Bi et al. (2022) reporting "60X speedup based on a corpus size of 10" **[primary**, arXiv 2508.00751v1**]**. The foundational validation is Chapelle, Joachims, Radlinski and Yue (2012), whose PDF I could not parse — the 10–100× characterisation attributed to that line of work here is **[documented]**, resting on the Airbnb paper's citation rather than on the 2012 text itself.

**Interleaving requires merging two systems' outputs into one response and attributing user actions back to each.** Two coding agents cannot have their diffs merged into one landed commit and then have credit attributed per agent. **The technique does not transfer.** [inferred]

### 4.4 What does transfer: paired dual-run

The transferable idea underneath interleaving is not the merge — it is **removing between-item variance by comparing within an item**. That is available here: dispatch two profiles onto the *same* issue in separate worktrees, and record only which one produced the better outcome by the gates.

This converts the analysis to a sign test on paired outcomes. To detect a consistent 75% win rate against a null of 50%, at α = 0.05 two-sided and power 0.80:

`n = [(1.96 × √0.25 + 0.84 × √(0.75 × 0.25)) / 0.25]² = [(0.980 + 0.364)/0.25]² ≈ 29`

**About 30 paired issues — six weeks at 5 per week.** [inferred]

The properties that make this the right design here:

- Between-issue variance, the dominant term when a docs sweep and a planner fix are in the same sample, is eliminated by construction.
- It needs no eval corpus, no held-out tasks, and no judge — the gates remain the only quality signal, exactly as ruling 9 requires.
- Nothing is burned: only one arm's work lands, and the issue was going to be done anyway.
- The marginal cost is one extra agent run per issue on a subscription with included capacity — which is the resource the project is trying to exploit rather than the one it is trying to conserve.
- A tie is informative and cheap to record; the sign test handles ties by exclusion, which slightly raises n and is worth stating up front.

Its costs are equally real: two worktrees per issue, a rule for which arm lands (pre-register it — "the arm that goes green first" is a defensible and unbiased rule only if the comparison is blind to it), and the possibility that the losing run's artefacts confuse a later reader.

**This is the one substantive change I would propose to ruling 9.** Its evidence regime — gates only, no corpus, no judge — is correct and should stand. Its *design* — unpaired randomisation across issues — should become paired dual-run on the same issue.

---

## 5. Prompt-cache-aware scheduling — the literature is one layer down from #218

**What is published.** SGLang's runtime "accelerates execution with novel optimizations like RadixAttention for KV cache reuse and compressed finite state machines for faster structured output decoding", reporting "up to 6.4x higher throughput compared to state-of-the-art inference systems" **[primary**, arXiv 2312.07104**]**. Preble targets the same problem across replicas: "many parts of prompts are repetitive across requests", addressed by "a new scheduling algorithm and a hierarchical scheduling mechanism" that "co-optimizes KV state reuse and computation load-balancing", improving average latency 1.5×–14.5× and p99 latency 2×–10× over state-of-the-art serving systems **[primary**, arXiv 2407.00023**]**. Secondary descriptions add that SGLang prioritises requests by shared-prefix length against a radix tree, and that Preble does longest-prefix-match routing across replicas with a load-balance fallback **[documented]**.

**Why it is not directly applicable.** All of this concerns a **server-side KV cache in a self-hosted inference stack**, where the scheduler owns the cache, can inspect its contents, and evicts by its own policy. Anthropic's prompt cache is a different object: client-visible, explicitly priced, with a chosen TTL. Cache writes bill at **1.25× base input at the five-minute TTL and 2× at the one hour**; cache reads bill at roughly **0.1×**; the minimum cacheable prefix is model-dependent **[primary**, Anthropic prompt-caching documentation via the `claude-api` skill**]**. Break-even differs accordingly: two requests at the 5m TTL (1.25 + 0.1 = 1.35 against 2.0 uncached), at least three at 1h (2.0 + 0.2 = 2.2 against 3.0) **[primary]**.

**I found no published work on scheduling against a client-side, priced cache with an operator-selected TTL.** [inferred from absence] #218's measurement of the true plan-limit multiplier for the one-hour TTL against the five-minute one is therefore not replicating anything in the literature — it is measuring something the literature has not addressed, on a cost surface that does not exist in the self-hosted setting the papers study.

**Two things do transfer, as principles rather than results** [inferred]:

1. **Cache state is a legitimate scheduling input.** Both systems treat "where is this prefix already resident" as a first-class routing signal rather than an invisible optimisation. The project already does this implicitly — the five-minute rule is a scheduling policy derived from cache economics — and the literature supports promoting it to an explicit input rather than a rule of thumb.
2. **Preble's specific finding is the one to carry over**: co-optimising cache reuse *and* load balancing beats either alone. That maps directly onto this project's live tension between keeping the orchestrator's one-hour cache warm (favouring a single long-lived session) and fanning out to subagents (favouring parallelism, at five-minute TTLs). Preble's result says the answer is neither pole; it is a scheduler that weighs both. Whether that is worth building here at this volume is a separate question, and on §4's evidence the honest answer is that the project could not measure the difference if it did.

The break-even arithmetic above also bears on #218 directly: the 1h TTL's doubled write cost means it pays off only from the third read, so its advantage is entirely about **surviving gaps longer than five minutes**, not about being cheaper per read. Any measured plan-limit multiplier should be interpreted against that structure. **[inferred from primary pricing]**

---

## 6. What this means for the two rulings

**Ruling 9 (evidence regime) — survives, with one design change and one correction to its reasoning.**

- The regime is right. Gates as the quality signal, no separate corpus, no LLM-as-judge: the contamination evidence (§2.1) and the domain-mismatch argument (§2.2) both independently support refusing a benchmark, and the burned-task problem (§1.6) independently supports refusing a bespoke corpus.
- **One of its three stated reasons is now weaker.** "Building an eval harness is a large cost before any saving lands" was true when written and is less true now: Inspect exists, is documented, handles per-sample Docker sandboxes, and explicitly supports CLI agents including Codex CLI. The ruling should rest on the two reasons that Inspect does not touch — benchmark drift from the live repo, and the fact that a solved task is burned — rather than on harness-building cost.
- **The design needs changing.** Unpaired randomisation across issues needs 50–706 landed issues depending on outcome type and effect size (§4.2). Paired dual-run on the same issue needs about 30 (§4.4). Same evidence regime, same gates, roughly a fifth to a twentieth of the time.
- **State the honest limit either way.** Even the paired design detects only a *consistent* winner. If two profiles differ by task class rather than uniformly, 30 pairs will show a muddle, and the correct response is to say so rather than to keep collecting.

**Ruling 17 (opaque profiles) — survives, with a stronger justification available.**

- Nothing in the routing literature supports learning a router at this scale. RouteLLM's smallest labelled set is ~1,500 examples and its preference corpus 65,000; RouterBench holds 405,000 outcomes (§3). A static profile→seat table is the only defensible policy here, and will remain so.
- The ruling's stated reason (effort scales are not commensurable across providers) is correct and sufficient. The stronger reason is that arm count is the binding constraint on measurability (§4.2), so collapsing three factors into one categorical label is what makes any measurement possible at all. Worth recording alongside the original reasoning.
- Corollary the ruling should make explicit: **marginal effects are not estimable.** "Does higher effort help?" and "is this lane better?" are not questions this project can answer independently of the specific profile. Guidance should never claim otherwise.

**One thing neither ruling covers, which the evidence recommends.** Use published rankings — SWE-bench Pro for its contamination controls, Terminal-Bench for shape proximity to harness work — as a **prior for the initial profile→seat assignment**, explicitly labelled as a prior. That is cheap, honest, and strictly better than assigning arbitrarily while the paired evidence accumulates.

---

## 7. Limits of this document

- Nothing here was executed. No Inspect task was written or run; the adoption cost in §1.6 is reasoning over documentation, not experience.
- The Chapelle et al. (2012) interleaving figures are second-hand via the Airbnb paper; the original PDF did not parse.
- The 32.67% solution-leakage figure for SWE-bench comes from search results summarising the SWE-MERA / SWE-rebench line of work, not from reading the owning paper.
- All of §4 is arithmetic on an assumed rate of 5 landed issues per week. If the real rate is 3, every duration extends by two-thirds; if 10, they halve. The rate is the single input most worth replacing with a measured figure from `gh` issue history before acting on any of it.
- Power calculations assume independence between issues. Successive issues in this repo are not independent — they share a codebase that is moving, and a process that is being amended by retros. That correlation pushes the true requirement above the tabulated figures, in an amount I have not estimated.
