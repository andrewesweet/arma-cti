# What an ending agent should write down, and what a continuation should read

**Researched**: 2026-08-05
**Question** (#208): #203 recommended ending an agent before a long wait. That leaves the other half open — what the ending agent persists, what its successor reads, and whether the orchestrator's dispatch briefings should be generated from it. The gates hold; a continuation that loses correctness to save tokens fails.
**Answer in one line**: a **structured handoff of about 1,500 characters, written by the ending agent as a comment on the issue it was working**, because the successor's problem is not the diff — git already holds that — but the predecessor's *judgement*, which today survives 29% of the time; and because in this project's economics anything a successor reads is paid **12.55 times over**, which prices the two obvious alternatives (dump the final report, dump the transcript) out of the running.

---

## 0. Method and limits

**Primary data.** Every Claude Code transcript for this project under `~/.claude/projects/**/*.jsonl` — **212 files, 191 subagent and 21 main**, to 2026-08-05. Same telemetry as #195 and #203, four files more than #203 had. Aggregation was done by script; no transcript body was read into the analysing agent's context.

**Cost model.** #203's corrected model throughout: cache write 1.25× at the five-minute TTL, 2.0× at the one hour, cache read 0.1×, output 5×, fresh input 1×. Project total **447.1 M input-equivalents**. Percentages are shares of the historical bill.

**Tokens per character is measured here, not assumed.** Across all assistant prose in the corpus, 504,922 billed `output_tokens` over 1,623,758 characters gives **0.3110 tokens/char**. Every char→token conversion below uses that figure. It is 24% above the chars/4 proxy #195 flagged as rough, and using the proxy would have understated every cost in this document by a fifth.

**Limits.**
- Costs of *reading* are modelled, not billed line-by-line: the transcripts bill a whole turn, not a passage within it. The amplification model in §1 is arithmetic over documented cache rates, and it assumes the token stays in context for the agent's remaining turns, which is true unless the agent compacts.
- The classification of a briefing as "continuation-shaped" is regex over its text (§3). It is a proxy, and it is confounded with task type — continuation-shaped work is also longer work.
- §5's evidence is web research with an evidence class on every claim. Nothing there is measured on this machine.

---

## 1. The fact that decides the format question: context is paid 12.55 times

A subagent runs a **median 114 turns** (mean 154, p90 281, max 1,145). Every turn re-sends the whole conversation, and the prefix is read from cache at 0.1×. So a token placed in context on turn 1 is billed once as a write at 1.25× and then re-read on each of the remaining turns at 0.1×:

| agent length | cost of one token of context placed at turn 1 |
|---:|---:|
| 10 turns | 2.15× |
| 25 turns | 3.65× |
| 50 turns | 6.15× |
| **114 turns (median)** | **12.55×** |
| 281 turns (p90) | 29.25× |

This is the whole of the format question. It says that what a continuation reads matters roughly an order of magnitude more than what it costs to write, and it converts "which handoff format" from a stylistic choice into arithmetic.

**A corollary that removes a distractor.** Regressing each subagent's cold start on its briefing length gives `cold_tokens = 0.457 × brief_chars + 18,032` (r = 0.129, n = 191) against a mean measured cold start of 19,370 tokens. The correlation is weak and that is the finding: **about 93% of a cold start is fixed** — system prompt, tool schemas, the CLAUDE.md hierarchy — and only ~7% is the briefing. Making briefings terser is not a lever. Making them *right* is free.

---

## 2. What a continuation actually spends its opening on

Classifying every `Bash` call whose command reconstructs prior state — git history, issue threads, verdict files — and attributing the result bytes back:

| category | calls | result chars | % | of which in the agent's first 10 turns | % |
|---|---:|---:|---:|---:|---:|
| `gh issue view` | 575 | 1,401,859 | 35.0% | 549,372 | 53.8% |
| `gh api` | 289 | 736,955 | 18.4% | 219,312 | 21.5% |
| `gh issue list` | 63 | 237,669 | 5.9% | 106,113 | 10.4% |
| verdict / runs tree | 961 | 525,403 | 13.1% | 4,773 | 0.5% |
| `git log` | 812 | 437,663 | 10.9% | 84,515 | 8.3% |
| `git diff` | 144 | 330,888 | 8.3% | 1,069 | 0.1% |
| `git show` | 101 | 203,159 | 5.1% | 5,925 | 0.6% |
| `git status` | 176 | 121,040 | 3.0% | 49,654 | 4.9% |
| `git rev-parse`/`reflog`/`blame` | 17 | 7,250 | 0.2% | 911 | 0.1% |
| **total** | **3,138** | **4,001,886** | | **1,021,644** | |

With per-agent amplification applied, state reconstruction costs a **median 75,888 input-equivalents per agent** and **26.7 M across the project — 5.98% of the bill**. The first-ten-turn slice alone is 6.09 M, **1.36%**.

Two things fall out.

**Reading the issue thread is the opening move, overwhelmingly.** GitHub-thread reading is 59.4% of all state reconstruction and **85.6% of the first-ten-turn slice**. Git archaeology is a *later* activity — `git diff` and `git show` are 13.4% of the total but 0.7% of the opening. A successor does not begin by studying the code its predecessor wrote. It begins by reading the *narrative*: the issue body and every comment on it.

**That tells you where a handoff belongs.** The one place a continuation is already guaranteed to look, at its own expense, is the issue thread. A handoff written there is found for free. This is not a new convention so much as the generalisation of one CLAUDE.md already carries for the regression tier — "the durable record is the verdict plus evidence path plus SHA quoted into the issue the run gated".

---

## 3. Three measured facts about the artifacts we already produce

**(a) The final report is a completion report, not a continuation document.** Taking the last assistant message of all 191 subagents (mean 6,706 chars, median 3,194, p90 20,710, max 59,078) and asking what each carries:

| field | present |
|---|---:|
| issue reference | 85% |
| commit SHA | 84% |
| landed/pushed statement | 76% |
| gate result quoted | 72% |
| worktree or branch named | 64% |
| **open risk / caveat** | **51%** |
| explicit blocker | 46% |
| **what was ruled out (elimination)** | **32%** |
| **next action / what remains** | **29%** |
| evidence path under `~/.arma-cti/runs` | 23% |
| **SHA + next action + risk, together** | **15%** |

The retrospective half is reliable; the prospective half is not. Reports answer "what I did", addressed to an orchestrator receiving a finished job. They do not answer "what you need", addressed to a successor. Only 15% carry the three fields a continuation cannot proceed without. **This is the measured case against option (b), handing on the report as-is** — not that it is too expensive, though §4 shows it is, but that it is the wrong document.

**(b) The orchestrator's briefings are already hand-authored handoffs, and they are strong on process and weak on state.** Across 191 dispatch briefings (mean 2,929 chars, median 2,720):

| field | in briefings | in resumption prods (n=175) |
|---|---:|---:|
| worktree path | 87% | 52% |
| issue reference | 81% | 46% |
| explicit gate instruction | 71% | 25% |
| report instruction | 61% | 7% |
| commit SHA | 51% | 69% |
| next action stated | 43% | 2% |
| open risks / blockers | 36% | 6% |
| prior-agent reference | 8% | 2% |
| evidence path | 10% | 18% |

Briefings reliably transmit the *orchestrator's* half — protocol, gates, landing, worktree. They transmit the *predecessor's* half rarely: risks 36%, evidence 10%, any reference to a prior agent 8%. And they are almost entirely bespoke: only **4.5% of briefing text is lines repeated across two or more briefings**, so this is 559,358 characters of hand-authored context, written 191 times.

**(c) A pointer does not displace archaeology.** The naive hypothesis is that putting a SHA in the briefing saves the successor from looking it up. Measured, the opposite correlation holds: agents whose briefing carried a SHA did a **median 26,209 characters of state reconstruction against 9,938 for those without**. The honest reading is confounded — a briefing carries a SHA precisely when there *is* prior state, so this is a marker of continuation work rather than proof that pointers backfire. But it is decisive against the stronger claim, that a reference is a substitute for content. It is not. A pointer says *go and look*, and looking is billed at 12.55×.

This is where agent→agent handoff parts company with the `/handoff` skill (`~/.agents/skills/handoff/SKILL.md`), whose instruction is "Do not duplicate content already captured in other artifacts (specs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead." For a session handoff to a human-attended successor sharing the machine, that is right. For an agent successor billed 12.55× on everything it reads, the rule inverts: **carry the conclusion inline and the pointer beside it**, so the path is followed only when detail is actually needed. One line saying `corpus 22/22 green at 5c407c6` costs 12 tokens; the path that proves it costs a directory listing, a verdict read, and the amplification on both.

Continuation-shaped briefings also correlate with more reconstruction overall (median 19,904 chars vs 11,222 for fresh work) but **not** more in the opening (3,636 vs 3,240). Continuations do not front-load archaeology; they do it throughout. That bounds what a handoff can displace, and §4 prices it honestly.

---

## 4. The four options, priced

Marginal cost per continuation, over and above the successor's cold start (measured mean 19,370 tokens → 24,213 input-equivalents at 1.25×), for a median 114-turn successor at 12.55× amplification:

| option | what the successor reads | tokens | **marginal input-equivalents** |
|---|---|---:|---:|
| **(c) nothing beyond the repo** — commits + issue comments | nothing extra; reconstructs | 0 | **0**, plus up to 14,648 of opening archaeology |
| **(a) structured handoff, ≤1,500 chars** | the handoff | 466 | **8,180** (5,848 read + 2,332 to write it) |
| (b) final report verbatim, mean 6,706 chars | the report | 2,086 | 26,179 |
| (b) final report verbatim, p90 20,710 chars | the report | 6,441 | 80,835 |
| (d) raw transcript, 87,000 chars | the trace | 27,057 | 339,565 |

Against #203's measured alternatives — a stalled agent resumed after its cache expires costs **201,326**, a fresh cold start **24,554** — the reading is:

- **(d) raw transcript is unaffordable here and this is a local inversion worth flagging.** The one controlled experiment on this question (§5, *Handoff Debt*) found the raw trace gave the *best* successor solve rate, at ~87k-character prompts. In this project's economics that same 87k costs 339,565 input-equivalents — **more than the 201,326 that never ending the agent costs in the first place**. The correctness-best option is the one option that defeats the purpose of the exercise. Amplification, not the paper, is what rules it out.
- **(b) report-as-is loses twice.** It costs 3.2× the handoff at the mean and 9.9× at p90, and §3(a) shows it carries the wrong fields — 29% next action, 32% eliminations. Paying more for a document optimised for someone else's question is the worst row available that is not (d).
- **(a) versus (c) is close, and the honest statement is a break-even, not a saving.** The handoff costs 8,180. The opening archaeology it could displace is a median 14,648, of which 85.6% is exactly the issue-thread reading a handoff comment is placed inside. **So it pays for itself if it displaces 56% of a successor's first-ten-turn state reconstruction** (8,180 / 14,648), and costs a few thousand input-equivalents if it does not. Project-wide, applying it to the 83 continuation-shaped dispatches costs **~0.15% of the bill**.

**The recommendation therefore does not rest on tokens, and should not be sold as if it did.** It rests on this: #204 proposes ending agents before long waits for a measured ~6% of the bill, and that rule *increases* the number of continuations. A handoff is the correctness insurance on that 6%, priced at 0.15%, at worst token-neutral. That is the whole argument.

---

## 5. What the outside evidence says

Classified per #195's standard: **vendor** (Anthropic), **community-replicated**, **independent**, **anecdote**.

**The one direct experiment.** *Handoff Debt* interrupts coding agents at deterministic points, freezes the repo, and runs successors under four views — repo-only, raw trace, summary notes, structured notes: 75 source tasks → 181 handoff scenarios → 724 takeover runs per model, three successor model pairs. Context-bearing views cut successor prompt tokens **42–63%** against repo-only. Solve rates (Qwen→Qwen): repo-only 46.4%, raw trace 52.5%, summary notes 51.4%, structured notes 50.8%; Qwen→Devstral 34.3 / 49.2 / 43.6 / 44.8. Raw trace won solve rate in all three pairs (+6.1 to +14.9 pp) on ~87k-char prompts against ~10k for notes; note-based gains were **not significant at α = 0.05 for two of three successors**, and structured-vs-summary was mixed. The authors' own summary: "Solved-rate gains are positive but less consistent than the efficiency reductions." — *independent*, https://arxiv.org/abs/2606.02875. **This is the single most important citation for #208, and it is a moderating one**: a handoff buys efficiency reliably and correctness only sometimes. Its schema — deterministic fields auto-populated from logs, plus model-filled fields for understanding, evidence, failures, remaining uncertainty and recommended next action — is the direct ancestor of §6's template.

**The strongest warning.** SWE-ContextBench (1,476 tasks, 51 repos, 9 languages; Lite = 99 tasks, Claude Sonnet 4.5): no context 26.26%, full trajectories 26.26%, oracle trajectories 27.27%, **agent-selected summaries 22.22%**, **oracle summaries 34.34%**. Summaries averaged 217 tokens against 25,634 for full trajectories — 118× compression, roughly flat cost. The 12.12 pp spread between agent-chosen and ground-truth summaries is the finding: **a summary of the wrong thing is worse than no summary at all**. — *independent*, https://arxiv.org/html/2602.08316v3. This is why §6 constrains the fields rather than saying "summarise your session".

**What compression reliably loses.** A probe-based evaluation over 36,611 messages from production sessions scored three production compaction methods on six dimensions: instruction-following ~4.95/5 and completeness ~4.37/5, but **artifact trail was worst for every method — 2.45, 2.33, 2.19 out of 5**, with the note that "those lost details eventually require re-fetching, which can exceed the token savings". — *anecdote / vendor-adjacent* (single self-favouring source evaluating a competitor's method; the ranking is marketing, the dimension profile is the signal), https://factory.ai/news/evaluating-compression. Independent corroboration on *what* summaries get wrong: FABLES, 3,158 human-annotated claims, finds "most unfaithful claims relate to events and character states", plus systematic over-weighting of material near the end of the source — *independent*, https://arxiv.org/abs/2404.01261. And baseline summarisation faithfulness is poor enough to matter — roughly 24–39% of summaries carry at least one factual inconsistency, model-dependent — *independent*, https://arxiv.org/pdf/2402.13249.

Together these three say a handoff's file/state/verdict claims are precisely the claims most likely to be wrong, and that a report written at the end over-weights the end. Hence §6's hard rule that deterministic fields are **quoted from a command, never from memory**.

**How much of multi-agent failure is actually handoff failure — less than you would think.** MAST (NeurIPS 2025 D&B), 1,600+ annotated traces across 7 frameworks, κ = 0.88: loss of conversation history **2.80%**, conversation reset 2.20%, information withholding 0.85%, ignored other agent's input 1.90%. Category totals: system design 43.8%, inter-agent misalignment 32.15%, **task verification 23.5%** (no/incomplete verification 8.20%, incorrect verification 9.10%, premature termination 6.20%). — *independent*, https://arxiv.org/abs/2503.13657. Read against this project: pure context-transfer failure is a small minority and verification failure dominates, which argues for keeping `just fast` and `just regress` exactly as they are and against any handoff ceremony that competes with them for an agent's attention. It is also a caution against over-investing here.

**Position effects argue for short.** "Lost in the Middle": accuracy degrades **>30%** when relevant information sits mid-context versus at either end, U-shaped, replicated across six model families — *independent*, https://cs.stanford.edu/~nfliu/papers/lost-in-the-middle.arxiv2023.pdf. Extended to 18 models with non-uniform, non-linear degradation by input length even on trivial retrieval — *independent*, https://www.trychroma.com/research/context-rot. A 1,500-character handoff read at turn 1 stays near an edge; a 20,000-character report does not.

**Externalised state does help where tasks genuinely span steps.** Ablating the note-taking component of Mobile-Agent-RAG drops success to 20% — *independent* but single-system, https://arxiv.org/pdf/2511.12254. Reflexion's persisted verbal lessons give 91% vs 80% pass@1 on HumanEval — *independent*, https://arxiv.org/abs/2303.11366, though that is within-task retry with an external failure signal, not handoff to a fresh agent. Against these, "Anatomy of Agentic Memory" finds most memory benchmarks do not require memory at all and that gains are inconsistent and backbone-dependent, with an independent replication ranking plain full context highest — *independent*, https://arxiv.org/html/2602.19320v1. The balance of evidence supports a *small, structured* artifact and does not support building a memory system.

**Vendor.** Anthropic documents the mechanism and endorses the practice. A subagent "starts with a fresh, isolated context window. It doesn't see your conversation history, the skills you've already invoked, or the files Claude has already read", and "the subagent does that work in its own context and returns only the summary" — https://code.claude.com/docs/en/sub-agents.md. There is **no documented mechanism for a subagent to return structured state to its caller**; the final text report and an agent ID are the whole channel. On practice: "Structured note-taking, or agentic memory, is a technique where the agent regularly writes notes persisted to memory outside of the context window… this simple pattern allows the agent to track progress across complex tasks" — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents; and, describing exactly this issue's pattern, "When context limits approach, agents can spawn fresh subagents with clean contexts while maintaining continuity through careful handoffs… Subagents call tools to store their work in external systems, then pass lightweight references back" — https://www.anthropic.com/engineering/multi-agent-research-system. Subagent reports are sized at "often 1,000–2,000 tokens" in the context-engineering post; this project's are a mean 2,086.

**Vendor mechanisms this project is not using, recorded for the adoption list.** `SendMessage` resumption "retain[s] the full conversation history, including all previous tool calls, results, and reasoning" — which is option (d), and §4 prices it out. `SessionStart` and `SubagentStart` hooks accept `hookSpecificOutput.additionalContext`, which Claude Code "wraps in a system reminder and inserts into the conversation at the point where the hook fired" — a supported way to inject a handoff into a successor without the orchestrator restating it (https://code.claude.com/docs/en/hooks.md). Subagents also support a `memory` field giving "a persistent directory that survives across conversations", with the first 200 lines or 25 KB of `MEMORY.md` loaded into the system prompt (https://code.claude.com/docs/en/sub-agents.md) — noted and **not** recommended, because a always-loaded per-agent memory file is a fixed tax on every dispatch where the issue thread is paid only when relevant.

**Community practice, adopted widely and measured nowhere.** `AGENTS.md` is read by 30+ tools across 60,000+ repositories with Linux Foundation stewardship — *community-replicated for adoption*, https://agents.md — and carries **no measurement of effect whatsoever**; the academic study of the practice is explicitly descriptive (https://arxiv.org/abs/2602.14690). Independent handoff-document implementations converge on near-identical section lists — current state, work completed, decisions and reasoning, next steps, blockers, do-not-touch, paths and commit hashes — and **not one of them measures anything**. The loudest architectural claim against the whole approach, Cognition's "Don't Build Multi-Agents" (agents must share full traces, never summarised messages), is a single essay with no experiment — *anecdote*, https://cognition.com/blog/dont-build-multi-agents — and is only partially supported by MAST, where pure context-loss modes total under 8%.

**Net.** Outside *Handoff Debt* and SWE-ContextBench, the practitioner literature on handoff documents is assertion. The two studies that do measure agree on a narrow conclusion: a structured handoff makes the successor cheaper and about as correct, and a badly-chosen one is worse than nothing. That is the conclusion §4 reached independently on our own telemetry, by a different route.

---

## 6. Recommendation

**Adopt option (a): the ending agent writes a structured handoff, ≤1,500 characters, as a comment on the issue it was working.** The template and its rules are in `docs/agents/handoff.md`, which is where agents read it. Its shape:

- **Deterministic fields — SHA, gate verdict, evidence path — are quoted from a command, never recalled.** This is the direct answer to the 24–39% summary-fabrication rate and to the artifact-trail dimension being the worst in every compaction method measured. An agent that cannot quote a gate result says so.
- **Judgement fields — state, next action, what was ruled out, risks, do-not — are what only the ending agent knows**, and are the fields today's reports carry 29–51% of the time.
- **Eliminations are mandatory**, because CLAUDE.md's own elimination-context rule — nine recorded validations at the time of writing — says a measurement holds only in the context it was tested, and an elimination that does not travel with its context is re-run by the successor at full price.
- **The issue comment is the location** because 85.6% of a successor's opening state reconstruction is already issue-thread reading, and because a worktree is removed while an issue is durable — the same reasoning ADR-0022 applies to evidence.

**On question 2: no, dispatch briefings should not be generated from the handoff — they should cite it.** Generating them saves nothing worth having: briefing authorship is 559,358 characters of orchestrator output across the whole project, about 0.19% of the bill, and 93% of a cold start is fixed regardless. The reason to change the division of labour is fidelity, not cost. The briefing's reliable half is the orchestrator's own (worktree 87%, gates 71%, protocol); its unreliable half is the predecessor's state (risks 36%, evidence 10%), which the orchestrator can only relay second-hand — and FABLES says state claims are exactly what a summary of a summary gets wrong. So: **the ending agent writes its state once, at first hand, into the issue; the briefing keeps the orchestrator's half and points at the handoff comment by URL.** That also removes the orchestrator's incentive to restate context it holds only in a context window that may itself have compacted.

**On whether the `/handoff` skill's shape transfers: partly, and the two divergences are principled.** Its compaction instinct, redaction rule and "suggested skills" section all transfer — the last as the template's *Next action* field. Two do not. It says to save to the OS temporary directory rather than the workspace, which is right for a session handoff and wrong here, where the artifact must outlive a removed worktree and a dead agent; and its reference-don't-duplicate rule inverts under 12.55× amplification, as §3(c) measured. The skill is global and shared across projects, so nothing here proposes editing it; `docs/agents/handoff.md` records the divergence and its reason instead.

**What would falsify this.** The break-even is stated and testable: the handoff pays for itself if it displaces 56% of a successor's first-ten-turn state reconstruction. That is measurable on the same telemetry after adoption — first-ten-turn archaeology chars for continuations dispatched with a handoff versus the 3,636-character median without. ACON's method is the right shape for the correctness half: run the same takeover both ways and diff the *failures*, rather than arguing about format (https://arxiv.org/abs/2510.00615, *independent*).

---

## 7. Where the uncertainty is

- **The 56% break-even is a forecast, not a measurement.** No continuation has yet run off a handoff comment. If handoffs turn out to displace little archaeology, the cost is ~0.15% of the bill and the correctness argument still stands on its own; if they displace most of it, the saving is around 1% on top.
- **Whether structured beats prose.** *Handoff Debt* found structured-vs-summary notes mixed, neither consistently ahead. The template is structured because deterministic fields need to be machine-checkable, not because structure is proven better.
- **The amplification model assumes no compaction.** A subagent that compacts mid-run re-prices everything before the compaction point. 3 of 191 subagents exceeded 500 turns, where this matters most.
- **`SubagentStart` `additionalContext` injection is documented and untried here.** It would let a handoff reach a successor without the orchestrator relaying it at all. Filed as an adoption issue rather than recommended, because it should not be wired before the manual convention has any track record.
