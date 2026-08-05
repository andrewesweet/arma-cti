# Abstract process complexity behind interfaces: replace agent-read usage guides with callable services where a rule-table already decides

Posted to #209 on 2026-08-05; landed verbatim for durability — the two exchange rates are reusable.

---

## Answer in one line

Measured on this project's own transcripts, **every usage guide an agent reads to operate the process, added together, is 0.40% of the bill** — so the premise that agents are spending real money reading procedure does not survive measurement; what they are actually spending it on is **turns**, at a measured 13,911 input-equivalents each, and **prose that sits in the always-loaded prefix**, at 2,137 input-equivalents per token. Those two exchange rates, not the guides, decide which interfaces are worth building — and they rank the candidates differently from the way the issue poses them.

---

## 0. Method and limits

**Primary data.** Every Claude Code transcript for this project under `~/.claude/projects/*arma-cti*/**/*.jsonl` — **214 files, 18,909 assistant turns**, to 2026-08-05, de-duplicated by message id. Same telemetry as #195, #203 and #208. No transcript body was read into context; everything below is script output.

**Cost model.** #195/#208's throughout: fresh input 1×, cache write 1.25×, cache read 0.1×, output 5×. Project total by this script: **438.4 M input-equivalents** (#208 measured 447.1 M over 212 files; the 2% gap is dedup and file-set drift, and it cannot move a ranking). Chars→tokens uses #208's measured **0.3110 tokens/char** for prose; document token counts use `o200k_base` via `tiktoken` as a proxy, per #195.

**Amplification is measured per load, not assumed.** For every load I take the turn it landed on and the transcript's total turns, and price it at `1.25 + 0.1 × (turns remaining)`. Measured average multiplier on process-prose loads: **7.97× to 17.55×**, bracketing #208's 12.55× median-subagent figure.

**Limits worth stating.**
- Attribution is by tool-call inspection: a `Bash` call counts against a surface if its command names it. A command naming two surfaces counts against both, so the per-surface figures are slightly generous and the total is not a sum.
- The prefix exchange rate assumes all 214 agents carry `CLAUDE.md`. Non-fork subagents load the hierarchy cold; forks inherit it and still pay the 0.1× re-read; built-in `Explore`/`Plan` skip it (#195 §6 item 5). So 2,137 is an **upper bound** on the rate.
- The turn-collapse estimates in §4 are modelled, not measured: they assume a procedure that today takes N calls takes one after a recipe exists. I give a ceiling and a conservative figure for each, because some of those calls are genuinely iterative (a rebase conflict needs turns).
- §5's evidence is web research with an evidence class on every claim. Nothing there is measured here.

---

## 1. The two exchange rates

Everything in this study reduces to two numbers.

| Lever | Measured cost | As % of the 438.4 M bill |
|---|---:|---:|
| One token added to `CLAUDE.md` (the always-loaded prefix) | **2,137 input-equivalents** | 0.00049% |
| — per 1,000 tokens | 2.14 M | **0.487%** |
| One extra agent turn (cache-warm, median 139,113-token prefix re-read at 0.1×) | **13,911 input-equivalents** | 0.00317% |
| — per 100 turns | 1.39 M | **0.317%** |

Derivation of the first: summed over the 214 agents, `Σ (1.25 + 0.1 × (Nᵢ − 1)) = 2,137`. The second is the median cache read per turn × 0.1.

The ratio matters: **1,000 tokens of prefix prose costs the same as 154 agent turns.** Prose in the prefix is expensive per unit; tool calls are cheap per unit but numerous. An interface proposal has to win on one of these two, and most of the obvious ones win on neither.

---

## 2. Inventory: what agents actually read to operate the process

Every read-like load (`Read`, or a `Bash` doing `cat`/`head`/`tail`/`sed -n`/`grep`/`jq`/`wc`), priced at its own measured amplification.

| Surface | tokens on disk | loads | chars arrived | input-eq | % bill | sessions | avg mult |
|---|---:|---:|---:|---:|---:|---:|---:|
| `spike/regress.sh` + `run.sh` + `tier-lock.sh` | 36,832 | 221 | 884,251 | 4.83 M | **1.101** | 67 | 17.55 |
| `docs/regression-tier.md` | 23,514 | 96 | 414,290 | 2.24 M | 0.512 | 42 | 17.41 |
| `spike/probes/*` (25 probes) | 94,874 | 153 | 389,067 | 2.11 M | 0.481 | 47 | 17.44 |
| `CLAUDE.md` (re-reads, on top of the prefix) | 7,542 | 86 | 118,974 | 0.39 M | 0.089 | 44 | 10.51 |
| `justfile` | 2,970 | 46 | 68,977 | 0.35 M | 0.081 | 37 | 16.52 |
| `docs/agents/*` (5 files) | 8,887 | 35 | 74,875 | 0.19 M | 0.042 | 22 | 7.97 |

**And now the control that changes the reading.** Split each load by whether that same agent also *edited* the file. Only the half that never edits it is a usage-guide cost an interface could absorb; the other half is an agent working on the thing, which no interface removes.

| Surface | consuming loads | consuming input-eq | **% bill** | sessions | authoring loads | authoring % bill |
|---|---:|---:|---:|---:|---:|---:|
| harness scripts | 48 | 0.99 M | **0.225** | 26 | 172 | 0.876 |
| `spike/probes/*` | 20 | 0.28 M | **0.065** | 13 | 129 | 0.416 |
| `justfile` | 23 | 0.23 M | **0.052** | 21 | 23 | 0.029 |
| `docs/regression-tier.md` | 10 | 0.13 M | **0.030** | 9 | 85 | 0.481 |
| `CLAUDE.md` re-reads | 7 | 0.06 M | **0.013** | 6 | 78 | 0.075 |
| `docs/agents/*` | 7 | 0.05 M | **0.012** | 5 | 28 | 0.030 |
| **total** | **115** | **1.74 M** | **0.397** | | | |

**0.397% is the entire ceiling for the issue as literally posed** — and it is a ceiling, assuming an interface absorbs every one of those reads and costs nothing itself. Three quarters of what looked like guide-reading is agents editing the guide. `docs/regression-tier.md` in particular: 85 of its 96 loads are agents who also wrote to it, and the top `grep` patterns against it are `<<<<<<<` (merge-conflict markers) and `^Reviewed-by-human: pending`. That is authoring, not consulting.

### Judgement versus mechanics, by section

| Piece | tokens | Class | Note |
|---|---:|---|---|
| `CLAUDE.md` failure-class **table** | 367 | **judgement — never abstract** | The required-response column is the contract. #209 says so and it is right |
| `CLAUDE.md` failure-class preamble, net of its `validated ×9` list | 31 | judgement | The rule is one sentence; the rest is exemplars |
| `CLAUDE.md` command-surface **table** | 740 | judgement (which tier, when) | Table rows are the cheapest form this can take |
| `CLAUDE.md` slot/contention ¶ (l.50) | 446 | **mixed** | Mechanics (ports, `flock` path, stride) already executed by `just regress`; the judgement residue is #44's "a slot boundary is only real where something reads it" |
| `CLAUDE.md` hold/window ¶ (l.52), net of exemplars | 299 | judgement | "Size the window to the subject, never to make it pass" is exactly the thing a service must not decide |
| `CLAUDE.md` Model roles | 436 | judgement, orchestrator-scoped | Every non-orchestrator agent carries it and never uses it |
| `CLAUDE.md` ADR-numbering ¶, net of exemplars | 118 | **mechanics** | "Take the next number above origin/main and every open-issue mention" is a scan |
| `CLAUDE.md` landing ¶ (in Commits) | ~120 | **mechanics** | fetch → rebase → re-gate → `push origin HEAD:main` → `merge --ff-only` |
| `CLAUDE.md` worktree pre-flight (l.104) | 106 | **mechanics** | clean `git status` ∧ no foreign files |
| `CLAUDE.md` `validated ×N` exemplar blocks (5 of them) | **2,246** | evidence, prunable | 29.8% of the file — see §6 |
| `regression-tier.md` Serialisation (slots, host seam) | 8,539 | **mixed, mostly design rationale** | Read by 9 non-authoring agents in the project's life |
| `regression-tier.md` Waiting for the subject | 4,184 | judgement | The honesty rule, observable/pollable/neither |
| probe↔harness contract (undocumented; lives in `regress.sh`) | — | **mechanics** | Headers `probe:`/`issues:`/`window:`/`env:`/`expect:`/`quarantined:`, the `probe_done` line, the log markers |

---

## 3. Where the money actually is: mechanical loops, counted as turns

Each of these is a procedure an agent executes by hand, one `Bash` call at a time. Priced two ways: the text that arrives, and the turns it takes.

| Loop | calls | sessions | text (% bill) | turns saved if it collapses to 1/session | **turn value** |
|---|---:|---:|---:|---:|---:|
| `gh issue`/`gh api` thread reading | 191 | 87 | 0.540 | 104 | 0.330% |
| probe file reading | 179 | 54 | 0.503 | 125 | 0.396% |
| `~/.arma-cti/runs` evidence crawl | 538 | 54 | 0.201 | 484 | 1.535% |
| worktree pre-flight / hygiene | 212 | 106 | 0.077 | 106 | 0.336% |
| landing: rebase / push / ff-merge | 220 | 117 | 0.061 | 103 | 0.327% |
| arma process & port sweep | 49 | 18 | 0.040 | 31 | 0.098% |
| `verdict.json` / `pool.json` reading | 87 | 35 | 0.038 | 52 | 0.165% |
| ADR number claim scan | 14 | 14 | 0.017 | 0–7 | ≤0.022% |
| slot / `flock` / port inspection | 39 | 26 | 0.015 | 13 | 0.041% |

**Two of these are already recovered and must not be counted again.** The evidence crawl's top command shapes are `date -u; ls -1t ~/.arma-cti/runs | head -1` (×59) and `ps -p <pid> …; ls -t ~/.arma-cti/runs` (×49) — those are poll loops, and #198's `just watch`, #199's `just verdict` and #205's `deny-subagent-waits.py` hook already took them out. The `verdict.json` row is `just verdict`'s territory, likewise closed. The `gh issue` row is #210's, filed.

What is left unbuilt and worth something: **worktree pre-flight (0.34% ceiling) and landing (0.33% ceiling)**, which are also the two loops with the widest reach — 106 and 117 of 214 agents run them.

---

## 4. Ranked candidates

Prize = prefix prose removed × 2,137, plus turns collapsed × 13,911, minus what the interface's own documentation costs (a `CLAUDE.md` table row measures 60–100 tokens, i.e. 0.03–0.05%), minus its output arriving per call. Conservative figures assume half the collapse.

### 1. `just land` — the landing protocol as one call, with typed refusals

**Prize: 0.15–0.33% (turns) + 0.06% (prose).** 220 calls across 117 sessions today.

Sketch: `just land [--no-gate]` does `git fetch origin` → rebase → re-gate (`just fast`) → `git push origin HEAD:main` → `git -C <main> merge --ff-only origin/main`, and **refuses with a named class** rather than a shell error: `dirty_tree`, `gate_red` (with the failing output, not a summary), `rebase_conflict` (stops, hands back — CHANGELOG conflicts are the only class 264 landings have produced), `not_fast_forward`, `merge_blocked_by_sandbox` (the case CLAUDE.md already says must be handed to the orchestrator, never skipped silently).

Correctness argument, which is the stronger one: `git push origin main` is documented in `CLAUDE.md` **because agents kept typing it**, and a stale main checkout is where ADR-0042's stale-hook window comes from (#130). A recipe cannot forget the `HEAD:main` form; prose can. The `merge_blocked_by_sandbox` refusal is the one that matters most — today that failure is silent-by-omission.

Risk: the gate must stay inside the recipe, not beside it. A `just land` that skips `just fast` is a gate bypass wearing a convenience wrapper, which is why `--no-gate` should probably not exist. **Filed as #213.**

### 2. `just worktree <name>` — create and prove exclusivity in one call

**Prize: 0.15–0.34% (turns) + 0.05% (prose).** 212 calls across 106 sessions — the widest reach of any loop measured.

Sketch: `just worktree add <name>` = `git fetch origin` → `git worktree add .claude/worktrees/<name> origin/main --detach` → pre-flight (clean `git status`, no foreign untracked files, no other live registration on the same path) → print the path and the base SHA. Typed refusals: `worktree_occupied` (naming the other holder, per #105's shape), `dirty_tree`, `stale_registration`. Plus `just worktree list` for the hygiene sweep — there are 85 live registrations on record.

Correctness argument: #105 is open, five destructive collisions landed in one evening, and `CLAUDE.md`'s standing mitigation is a *prose* pre-flight an agent must remember. The measured 212 calls show agents do run it; the collisions show prose is not enough. **This does not close #105** — assignment is the orchestrator's, and a recipe only makes the pre-flight cheap and uniform. **Filed as #214.**

### 3. `just probe-contract` — print the probe↔harness contract from the runner itself

**Prize: 0.09% (turns) + 0 prose** — because the contract is currently documented **nowhere**, which is the finding.

The largest consuming-read line in the whole study is agents reading `spike/regress.sh` / `run.sh` / `tier-lock.sh` (0.225%, 26 sessions that never edit them). What they grep for is not design rationale: `CTI_DAEMON_READY`, `hc_joined`, `probe_done`, `PASS in`, `worst class`, `^OUT=`. That is the probe↔harness interface being reverse-engineered out of 1,000 lines of bash, once per agent.

Sketch: `just probe-contract` prints, derived from the runner rather than restated beside it — the header keys `regress.sh` actually parses and validates (`probe:`, `issues:`, `window:`, `env:`, `expect:`, `quarantined:`, at `regress.sh:210-320`), the completion line the run waits on (`probe_done`), the log markers, the environment the world provides a probe, and the verdict classes the runner can emit. Single source of truth, so it cannot drift; #92 is open on `run.sh`'s structure and this rides with it.

Correctness argument: a contract read wrong out of bash is a probe that tests the wrong thing. #150/#191 is the recorded instance — staging read the board through `view`, which refuses an AI-commanded side, and the probe timed out in its own scaffold. **Filed as #215.**

### 4. Situational `CLAUDE.md` paragraphs → project skills (progressive disclosure)

**Prize: 0.43% ceiling, ~0.35% realistic. Human-gated: this is a proposal, not filed work.**

The three blocks every agent carries and only some agents use: slot/contention ¶ (446 tokens, 0.217%), hold/window ¶ net of exemplars (299, 0.146%), Model roles (436, 0.213%) = **1,181 tokens = 0.575%**, less three skill descriptions at Anthropic's documented **~100 tokens standing each** (§5) = 0.146%, netting **0.43%** — larger than any recipe above.

**And the correctness risk is the reason I am not filing it.** A skill's body loads only when triggered. The hold/window rule's entire purpose is to bind an agent who has *not* thought to look it up — an agent who does not know the rule exists is precisely the agent who extends a window until a flaky probe passes. Mitigation is a one-line trigger pointer left in `CLAUDE.md` (~25 tokens each), which keeps the trip-wire in the prefix and cuts the saving to ~0.39%. Model roles is the safest of the three (it binds the orchestrator seat, which is the seat that would invoke it); the other two are genuine judgement rules and the vendor's own guidance cuts against moving them (§5). **Proposed on #216, `ready-for-human`.**

### 5. Slot allocation — the issue's illustrative example. **Declined, with the arithmetic.**

The issue asks whether agents need the regression-tier doc's slot/contention prose or could live with an acquire/run/report/release API with typed refusals. Measured:

- **The API already exists.** `just regress --slots n --wait s` is acquire-and-run; per-slot `flock` at `~/.arma-cti/slots/N.lock` is the lock; `pool.json` + `just verdict` is report; kernel `flock` on holder death is release. The typed refusal is already there and already correct: no slot free is `infra_unavailable` with every holder's metadata, and it is already documented as not-a-result.
- **The prose is not what agents read.** Hand slot inspection across the project's whole life: **39 calls, 26 sessions, 0.015% of the bill.** Non-authoring reads of `docs/regression-tier.md` — the entire document, not just Serialisation — total **0.030%**. Serialisation is 36% of the doc, so its consulting cost is on the order of **0.011%**.
- **What the prose carries is the judgement half**, and it is the half that would be lost: #44's two-slot run had isolated ports, dirs, installs and daemons, the worlds still merged on a `CTI_DAEMON_ADDR` nobody set, and the run went green *because nothing asserted on it*. "A slot boundary is only real where something reads it" is not a rule-table; it is the reason the rule-table is not sufficient.

Building a slot service would be re-wrapping a service that exists, to displace 0.011–0.015% of the bill, at the cost of hiding the one sentence that caught a false green. **Do not build.**

### 6. Also declined

- **Compressing or servicing `docs/agents/*`**: 0.012% of the bill, 5 non-authoring sessions in the project's life. Nothing there.
- **A broader `just issue <n>` beyond #210's handoff fetch**: trimming a thread means deciding what a successor does not need, and SWE-ContextBench (#208 §5) measured agent-selected summaries at 22.22% against 26.26% for no context at all — a summary of the wrong thing is worse than none. #210's shape is right precisely because the selector is mechanical (`^Handoff-for:`), not judgement.
- **An MCP tool for any of this**: §5 — official guidance is explicit that CLI beats MCP for exactly this case.

---

## 5. What the official documentation says about the three shapes

Checked against `code.claude.com/docs` and Anthropic engineering, with an evidence class per claim.

**Skills / progressive disclosure — three levels, with a vendor token figure.** "Level 1: Metadata | Always (at startup) | **~100 tokens per Skill** … Level 2: Instructions | When Skill is triggered | **Under 5k tokens** … Level 3+: Resources | As needed | **None until accessed**" — *vendor*, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview.md. "Until a Skill is triggered, only its name and description occupy context" — same. Claude Code adds: the listing "always contains every skill name", budgeted at **1% of the model's context window**, degrading by dropping least-used descriptions rather than failing; an invoked SKILL.md "enters the conversation as a single message and stays there for the rest of the session"; authoring guidance is **under 500 lines**, references one level deep — *vendor*, https://code.claude.com/docs/en/skills.md.

**CLI beats MCP, stated outright.** "Prefer CLI tools when available: Tools like `gh`, `aws`, `gcloud` … are still more context-efficient than MCP servers because they don't add any per-tool listing." — *vendor*, https://code.claude.com/docs/en/costs.md. Tool search defers MCP schemas by default so a whole server costs ~120 tokens of names (illustrative figure, the doc labels it so) — https://code.claude.com/docs/en/mcp.md — but every call still round-trips results through the model, which the code-execution post frames as the deeper cost: "every intermediate result must pass through the model", with a worked case going "from 150,000 tokens to 2,000 tokens" by moving to code APIs — *vendor*, https://www.anthropic.com/engineering/code-execution-with-mcp. **This project already sits on the recommended side** (`gh` not an MCP, `just` recipes, evidence on disk), which is why §4 proposes recipes and not tools.

**Hooks — and a vendor caution that cuts against half of what #209 might want.** Hooks give "deterministic control: certain actions always happen rather than relying on the LLM to choose to run them", and `PreToolUse` fires "before any permission-mode check, in every permission mode" — *vendor*, https://code.claude.com/docs/en/hooks-guide.md, hooks.md. `SessionStart`/`SubagentStart` can inject `additionalContext`, capped at **10,000 characters**. But the same page says plainly: **"For instructions that never change, prefer CLAUDE.md. It loads without running a script and is the standard place for static project conventions"**, reserving `additionalContext` for *dynamic* state. So moving static process rules into a SessionStart hook is contra-indicated by the vendor; moving them into a skill is the supported shape, and enforcing them at the moment of action with `PreToolUse` is the supported shape for the mechanical ones. That is exactly the split §4 lands on.

**Typed refusals survive the abstraction — and the vendor argues for them.** "You can prompt-engineer your error responses to clearly communicate specific and actionable improvements, rather than opaque error codes or tracebacks", and agents "grapple with natural language names, terms, or identifiers significantly more successfully than … cryptic identifiers" — *vendor*, https://www.anthropic.com/engineering/writing-tools-for-agents. The skill best-practices page's rule is "Solve, don't defer" — a script handles what it can and hands back something actionable. There is **no official framing of "typed failure classes"** — that vocabulary is this project's — but the guidance points the same way, and it is why every recipe sketched in §4 carries named refusals rather than exit codes.

**Independent evidence on the specific trade is thin, and I will not inflate it.** No independent study of "usage prose read every session" versus "callable interface" exists that I could find. The nearest are two individual practitioners with disclosed method: an agent config converting always-loaded rule prose into trigger-phrase routing plus on-demand skills, measured at 7,584 → 3,434 startup tokens (**54%**) with individual rule files down 70–82% — *independent, single practitioner*, https://gist.github.com/johnlindquist/849b813e76039a908d962b2f0923dc9a; and MCP tool consolidation measured through `/context` at 14,214 → 5,663 tokens (**60%**) — *independent, single practitioner*, https://scottspence.com/posts/optimising-mcp-server-context-usage-in-claude-code. Both agree in direction with the vendor's qualitative claim. Widely circulated figures like "85% off tool schemas" or "50,000–70,000 tokens of MCP overhead" trace to no primary source and should be treated as **unsourced folklore**.

---

## 6. The number that dwarfs every interface in this study, and it is not an interface

`CLAUDE.md`'s five `validated ×N` exemplar blocks are **2,246 tokens — 29.8% of the file — 1.095% of the bill.** Every rule's own text, net of its exemplars, is small: the failure-class preamble is 31 tokens, the ADR-numbering rule 118, elimination-context 70, land-a-convention 60.

This is #195's recommendation 4, now priced exactly (#195 estimated ~0.87% against a smaller file), and the human approved the mechanism at `4287d63` — the retro skill's incremental pass prunes to a threshold of five with `docs/process-log.md` keeping the record. **Nothing here proposes touching it**; it is reported because it sets the scale: the single largest lever on "prose agents load every session" is deleting expired evidence, not wrapping current rules in a service, and it is already approved and already owned.

It also means the §4 candidates must be counted **net of the prune**, which I have done — the ADR-numbering paragraph looks like 463 tokens and is 118 once its `validated ×7` list is charged to the prune instead. That is why `just adr-next` is **not** in the ranked list: its prose prize falls to ~0.03% and its loop is 14 calls in the project's entire history. Its only surviving argument is correctness — #171's recorded blind window, where the competing claim sat on an issue that had closed ten minutes earlier and the prose scan reads open issues. That is a real hole and a scan could close it for free, but it does not clear #195's bar on its own; I have noted it on #215's thread rather than filing it, so it can ride along if that agent finds it cheap.

---

## 7. What is filed

| # | Title | Label | Prize |
|---|---|---|---|
| #213 | `just land` | `ready-for-agent` | 0.15–0.33% + correctness |
| #214 | `just worktree <name>` | `ready-for-agent` | 0.15–0.34% + #105 |
| #215 | `just probe-contract` | `ready-for-agent` | 0.09% + correctness |
| #216 | Proposal: three situational `CLAUDE.md` blocks → skills | `ready-for-human` | 0.35–0.43%, gated |

Declined with arithmetic: a slot service (§4.5), `docs/agents/*` compression, thread trimming beyond #210, MCP for anything.

**Honest total.** Everything filed here is worth roughly **0.4–0.8% of the bill**, and the correctness arguments are stronger than the token arguments in all three cases. That is the same shape #208 reported and it should be sold the same way: these are not savings that pay for themselves in tokens, they are procedures that stop being remembered and start being executed, at a price that is at worst neutral. The issue's own principle — "spend tokens once to produce software that consumes none" — holds; what the measurement adds is that the software worth writing is the one that removes **turns and prefix**, not the one that removes **reading**.

---

## 8. Where the uncertainty is

- **The turn-collapse model is a forecast.** It assumes a recipe turns N calls into one. Falsifiable on the same telemetry after adoption: count `git push origin HEAD:main` / `git worktree add` call sites per session before and after.
- **The 2,137 prefix rate is an upper bound**, since `Explore`/`Plan` subagents skip the CLAUDE.md hierarchy. I did not measure what share of the 214 agents are those; if it is large the §4.4 proposal shrinks proportionally.
- **The consuming/authoring split is a proxy.** An agent that edits `regress.sh` also genuinely consults it, so the 0.397% ceiling is if anything an under-count of the consulting share — but not by enough to change the ranking, since the whole read-like surface is 2.3%.
- **No independent evidence exists for the central trade** (§5). The three filed recipes rest on this project's own measurement and on correctness arguments from its own recorded failures, not on outside replication.
