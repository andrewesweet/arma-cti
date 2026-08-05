# Where the development process spends its token budget

**Researched**: 2026-08-05
**Question** (#195): what can the process change to achieve the same quality with fewer tokens? The existing gates — corpus, `just fast`, criterion audits, retro cadence — hold; a saving that degrades a gate is out of scope.
**Answer in one line**: the bill is not made of the things we write, it is made of the same context being re-read tens of thousands of times, and the largest recoverable waste is that **an agent turn which blocks for more than five minutes throws away the prompt cache and pays to rebuild it** — 13.6% of everything spent on this project so far.

---

## 0. Method and limits

**Primary data.** Every Claude Code session transcript for this project: `~/.claude/projects/**/*.jsonl`, 194 files, 17,515 assistant turns, 187 sessions with more than two turns, from project start to 2026-08-05. Each turn's `usage` block carries the four token classes Anthropic bills separately. Records were de-duplicated by message id, so a turn appearing in both a session file and its resume file is counted once. This is measured billing telemetry from this project, not an estimate.

**Cost model.** Raw token counts are misleading because the four classes bill at different rates. Everything below is expressed in **input-equivalents**, multiples of the base input rate:

| Class | Rate | Source |
|---|---|---|
| Fresh input | 1× | base |
| Cache write (5-minute TTL) | 1.25× | Anthropic prompt-caching pricing |
| Cache read | 0.1× | Anthropic prompt-caching pricing |
| Output | 5× | Opus input:output = $15:$75 per Mtok |

Weighted total for the project to date: **408.8 M input-equivalents**. Weighted spend splits opus-5 77.9% / fable-5 22.1% / sonnet-5 ~0%. Fable's published rates were not in hand; the table applies the Opus ratio throughout. That assumption cannot disturb the ranking, because output is 4.6% of the bill under any plausible ratio.

**Document token counts** use the `o200k_base` BPE via `tiktoken` as a proxy for Claude's tokeniser — stated as a proxy wherever used, and accurate to a few percent on English prose. **Tool-result sizes** are exact character counts from the transcripts; where converted to tokens, a chars/4 proxy is used and labelled.

**Limits worth stating.**
- The transcripts record what each request was billed, not why. The attribution in §2 links a cache re-write to the tool call that preceded it by wall-clock time. That is a strong inference where the gap is minutes long and the re-written prefix is six figures, but it is an inference.
- Idea 4's evidence is web research, summarised in §6 with an evidence class on every claim. Nothing there is measured on this machine except where §1–§4 say so.
- Savings percentages are shares of the *historical* bill. They are the right units for ranking; they are not a forecast, because the workload mix changes.

---

## 1. The finding that reorders every other idea

| Class | Raw tokens | % of raw | Input-equivalents | **% of bill** |
|---|---:|---:|---:|---:|
| Fresh input | 226,068 | 0.0% | 226,068 | 0.06% |
| Cache write | 80,930,895 | 2.7% | 101,163,619 | **24.74%** |
| Cache read | 2,886,205,002 | 97.1% | 288,620,500 | **70.60%** |
| Output | 3,764,964 | 0.1% | 18,824,820 | 4.60% |
| **Total** | 2,971,126,929 | | 408,835,007 | |

Two consequences, and they govern the rest of this document.

**Everything the model writes is 4.6% of the bill.** Terser prose, tighter summaries, shorter reports, lower verbosity — all of it competes for a twentieth of the spend. This is the ceiling on any output-side intervention, and it is worth knowing before optimising one.

**A token that enters the context is re-read 35.7 times.** Cache reads divided by cache writes is 2,886,205,002 / 80,930,895 = 35.7. So the marginal cost of putting one token into context is not 1×, it is

> 1.25 (write it once) + 35.7 × 0.1 (read it back on every later turn) = **4.82 input-equivalents**

and for a token that sits in the prefix from turn 0 of a mean-length 94-turn session, it is 1.25 + 9.4 = **10.65**. Context size is a *recurring* cost paid per turn, which is why sessions are expensive in proportion to how much they are carrying, not how much they are producing. Measured context per turn: mean 166,567 tokens, median 140,902, p90 319,815, max 667,423.

This reproduces, independently and on this project's own telemetry, the headline of arXiv 2607.12161 (2,908 Claude Code runs): cache traffic dominates, output does not.

---

## 2. The largest recoverable waste: turns that block past the cache TTL

Grouping every turn by the wall-clock gap since the previous turn in the same session:

| Gap since previous turn | Turns | Avg cache **write** per turn | Avg cache read per turn | Total cache writes | % of all writes |
|---|---:|---:|---:|---:|---:|
| < 30 s | 15,057 | **1,612** | 167,840 | 24,274,217 | 31.5% |
| 30–60 s | 920 | 3,808 | 155,093 | 3,503,463 | 4.5% |
| 1–2 min | 513 | 4,894 | 166,963 | 2,510,835 | 3.3% |
| 2–5 min | 420 | 5,970 | 183,414 | 2,507,455 | 3.3% |
| **5–10 min** | 195 | **97,237** | 126,399 | 18,961,242 | **24.6%** |
| **10–30 min** | 158 | **80,520** | 163,521 | 12,722,307 | **16.5%** |
| **30–60 min** | 23 | **91,154** | 145,070 | 2,096,551 | **2.7%** |
| > 60 min | 58 | 182,058 | 4,299 | 10,559,379 | 13.7% |

There is a cliff between "2–5 min" and "5–10 min": average cache creation per turn jumps from 5,970 to 97,237, a factor of 16. That is the 5-minute cache TTL expiring. The prefix dies, and the next turn pays 1.25× to write the whole ~150,000-token conversation back into the cache.

**434 turns — 2.5% of all turns — account for 57.5% of every cache write this project has ever paid for.**

| Effect | Cache writes | Input-equivalents | % of bill |
|---|---:|---:|---:|
| Mid-session TTL loss (gaps 5–60 min) | 33,780,100 | 42,225,125 | **10.33%** |
| Parked-session resumption (gaps > 60 min) | 10,559,379 | 13,199,224 | **3.23%** |
| **Total TTL loss** | 44,339,479 | 55,424,349 | **13.56%** |

The > 60 min row is distinguishable: its cache *read* averages 4,299, meaning the prefix was entirely gone. Those are sessions that parked and came back. CLAUDE.md's working-style rule "do not park work and go quiet" already forbids this; §2 prices it at 3.2% of the bill.

### What causes the blocking

Attributing each ≥ 5-minute tool call to the cache write on the turn that followed it:

| Blocking call | Occurrences ≥ 5 min | Avg duration | Cache writes caused | % of bill |
|---|---:|---:|---:|---:|
| `sleep` | 44 | 564 s | 7,877,483 | **2.41%** |
| `until` (poll loop) | 25 | 544 s | 5,995,690 | **1.83%** |
| `just fast` | 35 | 407 s | 6,374,863 | **1.95%** |
| `just regress` | 8 | 523 s | 1,297,612 | 0.40% |
| `just unit` | 7 | 438 s | 1,005,924 | 0.31% |
| `AskUserQuestion` | 12 | 2,635 s | 346,113 | 0.11% |
| `uv run pytest` | 2 | 519 s | 334,009 | 0.10% |
| `just probe` | 17 | 425 s | 228,602 | 0.07% |
| **Polling subtotal** (`sleep` + `until`) | 69 | | 13,873,173 | **4.24%** |
| **Recipe subtotal** (fast/unit/regress/pytest/probe) | 69 | | 9,241,010 | **2.83%** |

Two clean halves. Roughly 4.2% of the bill is agents deliberately waiting, and 2.8% is test and build recipes running longer than the cache lives.

### This is not a timeout extension in disguise

CLAUDE.md forbids extending a timeout to make a test pass. Nothing here asks for that, and the direction is opposite: the recommendation is that the gate should *finish sooner*, running exactly the same assertions. No window is widened, no probe's subject shrinks, no verdict changes.

### Measured fix for the recipe half

`just unit` is now 6 min 24 s, so `just fast` is about 6 min 30 s. **Every invocation from here on lands past the cliff.** The suite crossed the five-minute line recently, which is why the historical average `just fast` is only 128 s while today's is 390 s — the 1.95% above is a trailing figure and the forward rate is worse.

The cost is not compute. Measured on this machine:

| Run | Wall | User CPU |
|---|---:|---:|
| `uv run pytest` (serial, as shipped) | 6 min 17 s | 1 min 02 s |
| `uv run pytest -n 8` (pytest-xdist) | **1 min 44 s** | 1 min 20 s |

Wall clock is six times user CPU: the suite is overwhelmingly *waiting* — on real locks, real subprocesses, real slot bring-ups — not computing. That is the ideal shape for process-level parallelism. The `-n 8` run was green, same collection, exit 0. The single worst test is `test_a_child_that_outlives_the_run_does_not_keep_the_lock` at 60.01 s, an irreducible floor unless restructured; the next fourteen are 5–11 s each and parallelise cleanly.

`just fast` at `-n 8` becomes roughly 2 min 10 s, which is under the cliff. This is the single highest-value change identified by this assessment, and it touches no assertion.

---

## 3. The seed ideas, priced

### Idea 1 — compress agent-facing documentation

**What agents load.** Token counts via `o200k_base`:

| Surface | Tokens | When loaded |
|---|---:|---|
| `CLAUDE.md` | 6,957 | every session, every non-fork subagent, from turn 0 |
| `~/.claude/CLAUDE.md` + `RTK.md` | 629 | every session (global; the human's file) |
| `CONTEXT.md` | 1,635 | read-first |
| `docs/mvp-scope.md` | 881 | read-first |
| `docs/agents/*` (4 files) | 6,674 | on demand |
| `.claude/skills/*` (3) | 2,727 | on invocation |
| `docs/regression-tier.md` | 22,864 | on demand — the largest single agent-facing doc |
| `docs/process-log.md` | 29,542 | retros |
| `docs/adr/*` (56 files) | 73,901 | on demand |
| **Total corpus** | **145,181** | |

**Measured compression.** I compressed `docs/agents/issue-tracker.md` by hand in the register the issue describes — articles and connective prose dropped, every command, issue number, grep pattern, hook path and rule preserved exactly:

| | Chars | Tokens |
|---|---:|---:|
| Original | 11,130 | 2,733 |
| Compressed | 8,167 | 2,034 |
| **Delta** | | **699 (25.6%)** |

25.6%, not the 50–65% the register advertises, and the reason is visible in the diff: this document is already dense with load-bearing literal content — `gh` invocations, `#N` citations, the anchored grep, the regex the commit-msg hook enforces. None of that compresses. What compresses is the narrative that says *why* each rule exists.

**Value.** Applying 25.6% to `CLAUDE.md` removes 1,781 tokens from the prefix. At 10.65 input-equivalents per prefix token per session, over 187 sessions: **3.55 M input-equivalents, 0.87% of the bill.** Compressing the on-demand docs to the same ratio adds 0.09%. Call it **~1.0%**.

**Verdict: do not adopt as a compression pass.** It is real money but it is a twentieth of the TTL finding, and the thing it deletes is the thing this project has repeatedly found load-bearing. CLAUDE.md's own rule — an elimination or rationale holds only in the context it was tested, carrying four recorded validations — works *because* the rationale travels with the rule; #118 re-derived a surviving reason precisely because the expired one was written down. A register that drops "why" to save 1% would have made that impossible. The `validated ×N` markers are the same mechanism, and #186 built a gate to keep them honest.

There is a better-shaped version of the same 1%, and it is already project policy: **delete what has expired rather than compress what is current.** CLAUDE.md is 6,957 tokens largely because every validated marker accretes another exemplar. A periodic prune — oldest exemplars dropped once a rule has five, the process-log keeping the full record — takes the same tokens off the prefix without taking any reasoning out of the live document. Worth a retro's attention, not an engineering issue.

### Idea 2 — reduce test and build tool output

**As stated, the prize is small.** Observed tool-result sizes across all history:

| Command | Calls | Total chars | Avg chars | Avg tokens |
|---|---:|---:|---:|---:|
| `just check` | 331 | 225,260 | 680 | ~170 |
| `uv run pytest` | 343 | 188,893 | 550 | ~138 |
| `just fast` | 299 | 175,596 | 587 | ~147 |
| `just regress` | 161 | 96,155 | 597 | ~149 |
| `just unit` | 142 | 75,408 | 531 | ~133 |

Agents already pipe these through `tail`/`grep`, so the *observed* cost is ~150 tokens per invocation, not the 585 (`just check`) and 743 (`just unit`) a raw capture gives. The whole test-and-build tool-output surface is 190,328 tokens of arrival across the project's life. Cutting 85% of it and applying the 4.82× amplification yields **0.19% of the bill**.

**The right reframing is duration, not verbosity.** The same `just fast` costs 0.19%-scale tokens in output and **1.95%** in cache re-writes. The instruction "print one line on green" is worth a tenth of the instruction "finish in under five minutes". Adopt the second; the first is a nice-to-have that rides along free once someone is editing the recipes anyway.

**On RTK specifically.** RTK is installed and mandated by the global `~/.claude/CLAUDE.md`, and reports 28.0 M tokens saved at 76.9% on this machine. Two independent studies say that figure does not survive contact with the bill — see §6, item 9. RTK's counter estimates tokens as chars/4 over *raw* output that Claude Code already truncates, and never observes session context at all, which is precisely the 95% of the bill §1 measures. I make no recommendation about removing RTK — that file is the human's and the tool may earn its place on latency or ergonomics — but `rtk gain` should stop being read as evidence of money saved.

### Idea 3 — replace agentic reasoning with traditional automation

**This is the best-supported idea in the issue, and §2 gives it a number the seed did not have: 4.24% of the bill, from 69 tool calls.** Agents waiting — `sleep`, `until`-poll — is the single largest attributable cause of cache destruction, ahead of the test suite.

The mechanism is worth stating plainly, because it inverts the intuition. A polling loop looks cheap: `sleep 300` returns almost no text. Its measured cost is 179,033 tokens of cache re-write on the *following* turn, an average taken over 44 occurrences. A waiting agent is roughly **110× more expensive than a working one** per turn (179,033 vs the 1,612 baseline), and it is expensive precisely because it did nothing for five minutes.

That reframes the ADR-0049 vehicle. Moving a rule-based decision out of the model saves the tokens the reasoning would have cost — real, but small, since output is 4.6% of the bill. Moving a *wait* out of the agent's turn saves the entire prefix. The prize is in the second, and the design rule that follows is:

> Work that takes longer than the cache lives belongs outside an agent's turn. An orchestrator should be notified that something finished; it should not sit inside a turn watching for it.

**The loops, from the record.** Fifteen repeating orchestration loops are visible in `docs/process-log.md`, the ADRs and the issues. Classified by whether the decision each iteration makes is deterministic:

| # | Loop | Frequency, cited | Rule-based? | Already automated by |
|---|---|---|---|---|
| L1 | **Stall-watch-and-prod** — notice silence past a completion edge, read the pool evidence the agent never read, prod naming what finished | **6 stalls, 6 watcher catches, 0 text catches** (#168 ×2, #159, #162, #149 ×2; process-log 340/380/402/422) | **Yes** — detection is (run artefact exists) ∧ (no report in grace) ∧ (HEAD unmoved); payload is worst class + count + wall + evidence path + SHA, all in `pool.json` | **nothing.** Spec exists as prose only, `docs/agents/recovery.md:99-104` |
| L2 | Landing mechanics — fetch, rebase, re-gate, push, ff-only merge | ~264 landings; 2–3 main movements absorbed per landing | **Yes** — two decision points, both tables: in-world surface globs (`docs/regression-tier.md:401`), CHANGELOG conflicts | `just fast`; no landing recipe |
| L3 | Corpus-verdict reading and quoting | 22 probes/run, ~786 s; **~8 orchestrator wakes per corpus** (#181, process-log 402) | **Yes** for read + quote; judgement for what a red *means* | `tools/pool_merge.py::render_summary` renders it already; no `pool.json` → comment path |
| L4 | Worktree exclusivity pre-flight and hygiene sweep | **5 collisions in one evening** (#105); 85 live worktree registrations | **Yes** — three git commands and a comparison | nothing; no SessionStart hook wired |
| L5 | Review-queue depth grep + clearing mechanics | every one of 21 retros | Split — the grep is mechanical, the human verdict is not | `tools/check_adr_form.py` |
| L6 | ADR number claiming scan | 56 ADRs; renumber chains incl. 0039→0040→0041 in one cycle | **Yes, wholly** | nothing |
| L7 | Retro cycle | 21 in 6 days | Judgement for substance; trigger detection and marker upkeep are scripts | **`tools/check_validated_markers.py`** — idea 3 already executed once |
| L8 | Named-defect filing sweep | rule earned by 3 unfiled defects; 5 filed since | Detection yes, filing judgement | nothing; precedent `deny-closing-trailer.py` |
| L9 | Criterion audit at close | ~100+ closes | **No — judgement.** This is a gate; do not automate | guard only (`deny-closing-trailer.py`) |
| L10 | Dispatch briefing composition | dozens/day | Boilerplate yes, task/seat no | the four `.claude/agents/` seats already absorbed most |
| L11 | Scheduling: sequencing-by-surface, WIP cap, conservation window | held 3 cycles running; runs from orchestrator memory | Mostly yes — surface overlap is computable, WIP is a counter, the window is a clock | nothing; deliberately un-codified |
| L12 | Recovery-briefing composition | thirteen recorded validations; a 4-orchestrator-death cluster | Part 1 (what moved on main) is `git log`; part 3 is judgement | nothing |
| L13 | Elimination-context re-check | eight recorded validations | Trigger and diff mechanical; verdict judgement | nothing |
| L14 | **CHANGELOG conflict resolution** | *every* rebase over a concurrent landing; 3 cycles record it as the **only** conflict class | **Yes** — `merge=union` | **nothing; no `.gitattributes` in the tree** |
| L15 | Corpus re-run / flake triage | #164 took 5 corpus attempts | Dispatch yes (already built), response judgement | `tools/probe_verdict.py`, `pool_merge.py` ladder — **done, do not rebuild** |

L1 is the one that matters. ADR-0053 ruled the underlying harness behaviour out of this repo's scope, which makes the watcher **permanent compensation** — a forever cost. It is also the loop whose shape exactly matches the `sleep`/`until` measurement: an orchestrator sitting inside a turn waiting for a run it could be notified about. The 4.24% is what six stalls' worth of watching cost, and it recurs for as long as the project runs.

L14 is the cheapest item in this entire document: a two-line `.gitattributes` removing the only conflict class 264 landings have produced.

L9 and L15's response half must stay model work — they are the gates the issue says must hold.

### Idea 4 — community techniques

Full pass with evidence classes in §6. Three findings bear directly:

- The dominance of cache traffic over output is independently replicated (arXiv 2607.12161, 2,908 runs) and now independently replicated *here* on this project's own telemetry. Both agree that per-task tool-output reduction barely predicts cost change.
- Deferred tool loading — the biggest documented single win, ~85% off tool-schema overhead — **is already on** in this harness; the tool schemas in this very session arrived deferred. No action, but worth not disabling.
- Output-phrasing compression (the caveman register) is independently measured at 8.5% of *output* tokens against an advertised 65%. Against a bill where output is 4.6%, that is under 0.4%. Consistent with the 1.0% measured for idea 1 here, by a different route.

---

## 4. Ranked adoption list

Ranked by measured share of bill recovered, quality risk noted for each. The gates hold in every row.

| # | Change | Measured prize | Confidence | Risk to gates |
|---|---|---:|---|---|
| 1 | Parallelise the pytest tier (`pytest-xdist`, `-n auto`) so `just fast` returns inside the cache TTL | **~2.8%** and rising | Measured here: 6 m 17 s → 1 m 44 s, green | None to assertions; needs port/lock isolation confirmed under parallelism |
| 2 | Take agent waits out of the turn: no `sleep`/`until` poll loops inside an agent's turn; long work runs detached and notifies | **~4.2%** | Measured attribution; the mechanism is certain, the engineering is not yet designed | None — it changes when a result is read, not what it says |
| 3 | Process rule: never hold a turn open ≥ 5 min, and never park a session and return | 10.3% + 3.2% ceiling, overlapping 1 and 2 | Measured | None. CLAUDE.md already forbids the parking half |
| 4 | Prune expired exemplars from `CLAUDE.md` rather than compress it | ~0.9% | Measured compression ratio; prune ratio unmeasured | Real risk if it removes live rationale — hence prune, not compress |
| 5 | Batch human questions to session boundaries rather than mid-session | 0.11% | Measured | None |
| 6 | Single summary line on green from `just` recipes | 0.19% | Measured | None; do it while editing recipes for #1 |
| 7 | Stop reading `rtk gain` as evidence of cost saved | n/a — corrects a measurement, not a cost | Two independent studies | None |

**Secondary tier — rule-based, cheap, savings real but unmeasured.** These come out of the loop inventory rather than the telemetry, so none of them clears the measured-savings bar on its own. They are listed for a ruling, not filed as priced work: `.gitattributes` with `merge=union` on `CHANGELOG.md` (L14, two lines, removes the only conflict class 264 landings have produced); a `pool.json` → issue-comment renderer (L3, and it closes #134's quote-before-read hole); an ADR-number claim scanner (L6, and it would close for free the blind window the retro declined to widen *because of agent cost*); a worktree pre-flight/hygiene hook (L4, 85 live registrations, five destructive collisions).

Not adopted, with reasons in §5: doc compression as a register change; token-optimised serialisation; anything that compresses code context.

**What this does not claim.** Items 1–3 overlap: the 5-minute rule (3) is the general statement of which (1) and (2) are the two specific instances that the data attributes. The honest ceiling for the whole group is the 13.56% of §2, not the sum of the rows. And every figure is a share of the *historical* bill under this project's session shape; a different workload redistributes them.

---

## 5. Recommended against

**Compressing agent docs as a register change (idea 1 as posed).** ~1.0% of the bill, paid for by deleting the rationale this project has four validated instances of needing. Prune expired content instead.

**Semantic compression of code or context in the tool path.** An independent study measured SWE-bench-Go patch application falling 27/40 → 15/40 when compression destroyed verbatim edit anchors; an API-boundary compression proxy measured **+48.4%** cost. This project's edits go through `Edit` with exact-match `old_string`, which is exactly the failure mode. Deterministic, whitelisted truncation of genuinely huge logs is fine; nothing cleverer.

**Token-optimised serialisation formats** (TOON, TRON): independently measured at 18–27% token reduction for 9–14 percentage points of accuracy. Trading accuracy for tokens fails the issue's quality bar by construction.

**Chasing raw token counts.** §1 shows why: 97.1% of raw tokens are cache reads billed at a tenth. A change that cuts tokens and adds turns loses.

---

## 6. Community research, with evidence classes

Each claim is labelled **vendor** (Anthropic or the tool's author), **community-replicated** (several independent practitioners agreeing), **independent** (third-party benchmark or paper), or **anecdote** (single unreplicated report).

1. **Cache traffic dominates cost, output does not.** 2,908 Claude Code runs, 103 tasks, 7 repos: cache writes 44.3% + cache reads 35.4% ≈ 87% of reconstructed cost; output 10.4%. Per-task tool-output reduction barely predicted cost change (r = 0.154, CI crosses zero). — *independent*, https://arxiv.org/abs/2607.12161. **Replicated here** in §1 (writes 24.7%, reads 70.6%, output 4.6% — same conclusion, different mix because this project's sessions carry more context).

2. **Prompt-cache mechanics and invalidators.** Cache read ≈ 0.1×, write ≈ 1.25×. Invalidated by: switching model, **changing effort mid-session**, `/compact`, upgrading Claude Code, resuming after upgrade. Not invalidated by: editing files, output style, permission mode, invoking skills, `/rewind`, spawning a subagent. TTL 5 min on API keys, 1 h on subscription; **subagents use the 5-min TTL regardless**. — *vendor*, https://code.claude.com/docs/en/prompt-caching, https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything. The cliff measured in §2 sits exactly at 5 minutes, which is consistent with the 5-minute TTL being in force for this project's sessions.

3. **Cache scope is per-directory — every worktree is its own cache.** `--exclude-dynamic-system-prompt-sections` moves cwd/git/platform out of the system prompt so identical configs share one entry across directories, at the stated cost of that context being "marginally less" authoritative. — *vendor*, https://code.claude.com/docs/en/prompt-caching#cache-scope. Magnitude for a worktree-per-agent setup: **no published number**; unmeasured here.

4. **Simultaneous parallel spawn defeats caching** — a cache entry exists only after the first response begins, so N identical subagents fired at once are N writes, not 1 write + N−1 reads. — *vendor* mechanism; *community-replicated* symptom, https://news.ycombinator.com/item?id=48883275.

5. **Subagents save the parent's context; they do not save money.** Agents ≈ 4× chat tokens, multi-agent ≈ 15×; Anthropic lists "most coding work" as a poor fit. Agent teams ≈ 7× a standard session. A non-fork subagent starts cold and **loads the whole CLAUDE.md hierarchy**; only built-in `Explore`/`Plan` skip it. A **fork** reads the parent's cache and is cheaper. — *vendor*, https://www.anthropic.com/engineering/multi-agent-research-system, https://code.claude.com/docs/en/costs, https://code.claude.com/docs/en/sub-agents.

6. **CLAUDE.md size.** Vendor guidance: under 200 lines, workflow into skills which load on demand. Illustrative startup budget ≈ 7,850 tokens. — *vendor*, https://code.claude.com/docs/en/costs, https://code.claude.com/docs/en/context-window. The popular "5,000-token CLAUDE.md costs 5,000 tokens every turn" framing is *anecdote* and wrong on cost — after turn 1 it is a 0.1× read. §3 prices the correct version.

7. **Progressive disclosure via skills.** Name + description at startup, body on invocation; once loaded the body persists and recurs every turn. — *vendor*, https://code.claude.com/docs/en/skills. Measured 773 tokens of descriptions vs ~13,900 eager bodies — *anecdote*, https://www.newsletter.swirlai.com/p/agent-skills-progressive-disclosure. SkillReducer: 39% body compression at +2.8% functional quality across 5 models — *independent*, https://arxiv.org/html/2603.29919v1.

8. **Deferred tool loading (tool search).** On by default; only tool names load at start. ~77 K → ~8.7 K tokens with 50+ MCP tools. Anthropic's internal MCP evals improved 49%→74% (Opus 4) with it. — *vendor*, https://code.claude.com/docs/en/mcp. Independent measurement of the underlying problem: GitHub MCP at 93 tools ≈ 55,000 tokens — *anecdote but careful*, https://dev.to/kenimo49/your-mcp-server-eats-55000-tokens-before-your-agent-says-a-word-i-measured-the-real-cost-19l8. **Already on here** — no action beyond not disabling it, and preferring `gh` over an MCP equivalent, which this project already does.

9. **RTK, measured.** JetBrains, 86 SkillsBench tasks, 425 billed paired trials, RTK v0.43.0 as shipped: new input tokens **+3.2% (p = 0.23)**; cost **+7.6% at low effort (p = 0.004)**, **+0.1% at high effort (p = 0.99)**; turns **+13.8%**; cache reads **+14.3%**; task success indistinguishable. RTK's own analytics reported 96.2 M tokens saved while the bill rose, because it counts raw output the harness already truncates, estimates chars÷4, and never sees session context. — *independent*, https://blog.jetbrains.com/ai/2026/07/rtk-claude-code-token-savings/. Corroborated: RTK **−2.7% [−5.6, −0.1]** — *independent*, https://arxiv.org/abs/2607.12161.

10. **Output-phrasing compression (caveman register).** Best case, skill force-activated on all 86 tasks: **8.5% output-token saving**, not the advertised 65%; outcomes indistinguishable (sign test p = 1.0). The 65% was measured on 10 prose-heavy chat tasks. — *independent*, https://blog.jetbrains.com/ai/2026/07/speak-to-ai-agents-like-cavemen-tosave-tokens/, covered at https://www.infoworld.com/article/4193775/talk-like-a-caveman-prompts-save-tokens-but-far-less-than-promised.html.

11. **Compression that costs accuracy.** TRON −27% tokens at −14 pp accuracy; TOON −18% at −9 pp — *independent*, https://arxiv.org/abs/2605.29676. Context compression dropping SWE-bench-Go patch application 27/40 → 15/40 by destroying verbatim edit anchors — *independent*, via the JetBrains study above.

12. **Code execution instead of tool round-trips**: 150,000 → 2,000 tokens (98.7%) on a data-filtering workflow, with sandboxing caveats — *vendor*, https://www.anthropic.com/engineering/code-execution-with-mcp. This project already has the shape (`just` recipes, evidence on disk under `~/.arma-cti/runs/`); little headroom left.

13. **Compaction and resumption.** `/compact` while warm costs a fraction of the context size; after TTL it reprocesses the full history uncached — "`/compact` costs the most when you resume an old session". `/clear` is free; `/rewind` reuses a cached prefix. — *vendor*, https://code.claude.com/docs/en/costs. §2's > 60 min row (3.23% of bill) is this effect, measured.

14. **Redundant file re-reads: claimed 42% of agent tokens** — *anecdote*, by a vendor selling the fix, partly paywalled: https://gotcontext.ai/news/researcher-finds-42-of-coding-agent-tokens-are-wasted-on-repeated-file-reads. **This did not replicate here.** Measured over all 2,418 `Read` results in this project's transcripts: 721 reads (29.8%) were of a file already read in the same session, but they carry only **9.2% of read bytes** (1,328,262 of 14,460,355 chars ≈ 332 K tokens ≈ **0.39% of the bill**), because repeat reads are mostly small re-checks of a region rather than whole files. Not worth an intervention here; worth recording that the community figure is four-and-a-half times this project's reality.

15. **"Verify my own work" passes.** Widely repeated as waste, **no published measurement found**. CLAUDE.md already forbids extra verification passes and verifier subagents; keep the rule, do not attach a number to it.

16. **Disputed and open**: a GitHub issue claims Agent-SDK subagents send no `cache_control` breakpoints; an Anthropic collaborator replies the identified path is not the one subagents use. Unresolved — https://github.com/anthropics/claude-code/issues/29966.

---

## 7. Where the remaining uncertainty is

- **The cost of a subagent's cold CLAUDE.md load** in a heavy-fan-out setup is vendor-documented as a mechanism and unmeasured in magnitude anywhere, including here. This project made 181 `Agent` calls. If the fan-out grows, this becomes worth measuring directly.
- **Worktree cache fragmentation** (§6 item 3): mechanism certain, magnitude unknown, and this project runs one worktree per agent by design. `--exclude-dynamic-system-prompt-sections` is a one-flag experiment whenever someone wants the number.
- **Whether raising the cache TTL to one hour would help.** Arithmetic says mostly not: 1-hour writes bill at 2× rather than 1.25×, so eliminating the 33.8 M tokens of re-write saves ~42 M input-equivalents while the premium on the remaining 47 M writes costs ~35 M — a net ~1.7%, against the ~10.3% available from simply not blocking. Fix the durations first; the TTL setting is a distant second and its exact billing on this subscription was not verified.
