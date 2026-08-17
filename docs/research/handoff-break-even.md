# The handoff break-even, five days after adoption

<!-- absent-path -->
<!-- A dated research record: the repository paths it cites are the tree as it stood when
     the research was done, and some belong to other projects entirely. Neither is a claim
     about this tree today, which is what the marker above tells `just check-doc-paths`. -->

**Researched**: 2026-08-10
**Question** (#212): #208 priced the structured handoff as a break-even — it pays for itself if it displaces 56% of a successor's first-ten-turn state reconstruction — and promised the falsification once continuations had run off handoffs. Run it, then weigh `SubagentStart` context injection on the result.
**Answer in one line**: **the measurement cannot be run, and the reason is not sampling noise** — in the five days since the convention landed, **five handoff events were written, three were read by a successor, and none was read by the cold-start dispatched subagent the 56% is defined over** — and separately, the 56% is denominated in input-equivalents, a currency #218/#220/#232 inverted on the same day #208 landed, so even at adequate N the measurement as specified would answer a question about the wrong currency.

---

## 0. Method and limits

**Discriminator.** #212 asked for the cleaner one, and this uses it: an issue that actually carries a comment opening a line with `Handoff-for:` — `tools/handoff_fetch.py`'s own `MARKER`, so this study and the retrieval tool agree on what a handoff is. #208's regex over the dispatch briefing is not reused, and its confound with task length does not arise here.

**Population.** Every issue on `andrewesweet/arma-cti`, searched through `gh issue list --search '"Handoff-for:" in:comments'` and then confirmed one issue at a time against the marker. Window: `ae79d12` (2026-08-05T07:45Z), the commit that landed `docs/agents/handoff.md`, to 2026-08-10T14:00Z. **102 issues were closed inside that window.**

**Cost model.** #208's, unchanged, so the figures are comparable: 0.3110 tokens per character measured over this project's assistant prose, read amplification 12.55× for a median 114-turn subagent placing a token in context at turn 1, output at 5×. Input-equivalents for a handoff of *n* characters are therefore `n × 0.3110 × (12.55 + 5) = 5.458 n`, which reproduces #208's 8,180 for 1,500 characters to within 0.1%. §5 then re-prices the same artefact in the currency this plan actually meters, and the two answers disagree.

**Limits, stated plainly.**

- **The token half of #212's method was not run.** It requires aggregating `~/.claude/projects/**/*.jsonl`, and this dispatched seat could execute no code: `python3`, `uv run`, `jq`, `awk`, `grep` and `gh api` were all refused to it, and the `Read` tool is refused outside the worktree. `docs/agents/dispatched-session-commands.md` (#294, landed during this study's own rebase) separates the causes — `grep` is refused only because RTK rewrites it before the permission decision, so `\grep` would have run, while `awk` and `python3 -c` are refused on their own merits. This is *not* `infra_unavailable`: the transcripts are readable by `cat` and the blocker is the seat, not the telemetry. Whoever runs the token half needs a seat that can run a script. It was not attempted here, because §1 makes it unrunnable regardless: the treatment arm is empty.
- **GitHub's search index is the sampling frame.** A handoff comment written in the last minutes before this study would not be indexed. The newest one found is 2026-08-09T23:34Z and was indexed, so the lag is under a day. Six issues with plausible continuations but no search hit (#260, #270, #272, #276, #302, #304) were checked directly against the marker and carry none, which is the frame's only cross-check.
- **"Read by a successor" is inferred from the issue thread**, not from a transcript: a later comment that acts on what the handoff says. That direction of inference is sound — a successor that acted on it read it — but it cannot see a successor that read one and said nothing.

---

## 1. The sample, which is the finding

Nine comments carry the marker, across five issues. Four of the nine supersede an earlier handoff on the same issue by the same agent, so there are **five distinct handoff events**:

| event | newest comment | chars | superseded | read by a successor? | by whom |
|---|---|---:|---:|---|---|
| #208 | 2026-08-05T07:50Z | 1,459 | — | no | the next comment is the human's ruling |
| #170 | 2026-08-05T17:24Z | 2,442 | ×2 | **yes**, 2026-08-06T22:12Z | the orchestration session |
| #221 | 2026-08-05T16:33Z | 2,400 | ×2 | no | issue de-queued as an initiative anchor |
| #287 | 2026-08-08T21:35Z | 9,404 | — | **yes**, 2026-08-08T21:38Z | the orchestrator |
| #290 | 2026-08-09T23:34Z | 6,028 | — | **yes**, 2026-08-10T13:51Z | the orchestrator |

**Cold-start dispatched subagents that read a handoff: zero.** All three reads were by an orchestrator session already holding the context — which is the one reader for whom the 12.55× first-turn amplification does not apply, and the one reader whose "first-ten-turn state reconstruction" is not a meaningful quantity. The population the 56% break-even is defined over is empty.

**Two facts about the denominator.** 102 issues closed in the window against five handoff events. That ratio understates adoption, because the convention explicitly excludes a finished, landed issue — a handoff is owed on an ending before a long gate, on an unclearable blocker, or on a wrap-up. But it also flatters it, because the continuation events this project actually generated in the window were mostly *involuntary*: #260 and #270 each took a typed `quota_exhausted` 429 mid-run and were re-dispatched to Codex, and neither issue carries a handoff — an agent killed by a 429 never gets the turn in which to write one. The convention serves the voluntary ending; the observed continuations were deaths. `just recover brief` (#253) is the tool for the other half, and it reconstructs rather than reads.

---

## 2. What the transcripts were not needed for: the artefact is four times its own cap

`docs/agents/handoff.md` sets ~1,500 characters, and the cap is load-bearing rather than stylistic — it is what #208's 8,180 was computed from. Measured against the nine comments:

| | chars | input-equivalents (5.458 n) | break-even displacement required |
|---|---:|---:|---:|
| the cap | 1,500 | 8,187 | 56% (#208's figure) |
| #208 | 1,459 | 7,963 | 54% |
| #221 | 2,400 | 13,099 | 89% |
| #170 | 2,442 | 13,329 | 91% |
| #290 | 6,028 | 32,901 | **225% — unreachable** |
| #287 | 9,404 | 51,326 | **350% — unreachable** |
| median of the five | 2,442 | 13,329 | **91%** |
| mean of the five | 4,347 | 23,726 | **162% — unreachable** |

**One of nine comments (11%) honoured the cap, and it is the one written by the agent that wrote the convention.** At the median size actually written, the break-even moves from 56% to 91% of a successor's entire opening state reconstruction. At the mean, and for the two most recent events individually, the handoff costs more than the *whole* of the median opening archaeology (14,648) it could displace, so no displacement rate breaks even.

The drift has a shape, not just a size. #208, #170 and #221 use the template's labelled fields (`State`, `SHA`, `Gates`, `Evidence`, `Next`, `Ruled out`, `Risks`, `Do not`). #287 and #290 use neither the fields nor the cap: both are completion reports — criterion-by-criterion audits, verbatim gate output, proposed diffs, "notes for whoever picks this up" — with a `Handoff-for:` line on top. That is **option (b), the final report verbatim**, which §4 of #208 priced at 26,179 mean input-equivalents and rejected on the grounds that it carries the wrong fields. #287's 51,326 and #290's 32,901 straddle that estimate. The convention has, in five days, drifted into the option it was chosen over.

Two subsidiary costs, both invisible to a break-even that counts only the newest comment:

- **Supersession is not free.** #170 and #221 each posted three handoffs, revising a `SHA` from unpushed to pushed and a blocker list. `just handoff` correctly returns the newest, so a successor pays only for that one — but the superseded pairs cost 4,021 and 3,912 characters of output, **12,336 input-equivalents** written to be ignored, comparable to one whole handoff's read cost.
- **The programme's total spend to date is negligible in absolute terms**: 46,131 to write all nine and at most 69,762 to read the three that were read, about **115,900 input-equivalents, 0.026% of #208's 447.1 M project bill**. The read half is an upper bound stated in this study's currency rather than a claim about what three orchestrator sessions were billed. Nothing here argues the convention is expensive. It argues that the artefact being written is not the artefact that was priced.

---

## 3. Why no cold-start continuation read one

The delivery path #208 §6 specified was never built. Its recommendation was that "the briefing keeps the orchestrator's half and points at the handoff comment by URL". `just brief` (#251) landed that briefing composer four days later and **composes no handoff line at all**: `tools/brief.py` reads the issue body, the open-issue list, the worktree and the readiness assessment, and never calls `handoff_fetch`, never asks whether the issue carries a handoff, and never tells the successor to look. The brief that dispatched *this* study is the evidence — it names `just handoff` nowhere.

CLAUDE.md's command table does carry the rule ("**First read of any continuation**, before the issue body and before `git log`"), and `docs/agents/handoff.md` repeats it. So the rule exists in two documents an agent may or may not have paged in, and does not exist in the one artefact every dispatched agent certainly reads. That is a sufficient explanation for zero cold-start reads without invoking anything about the format, and it is the thing to fix before re-running the measurement.

---

## 4. The correctness half

#212 asks for instances rather than a token table, and for the field to be named. Two, both from the thread record.

**A handoff prevented a wrong action, and the field was `SHA`'s pushed marker plus `Do not:` (#170, 2026-08-06T22:12Z).** `just worktree done issue-170` refused, correctly by its own rule:

```
refusal=unlanded_work
unlanded=3 commits not on origin/main
action=Land them first (`git push origin HEAD:main`) or say so in your report. Removing this tree now loses 3 commits.
```

The refusal's premise — that `origin/main` is the only durable home — was false on that tree, and the only record saying so was the handoff, whose `SHA` line read "`f4ce30f` … **pushed** as `origin/issue-170-parked` … this is a preservation ref, not a landing" and whose `Do not:` line read "Delete `origin/issue-170-parked` until this work lands or is abandoned — it is the only durable copy of ADR-0059's record." The successor verified rather than trusted (`git ls-remote origin issue-170-parked` returning that exact SHA, which is the convention's own rule), removed the tree under the human's word with the refusal read rather than bypassed, and kept the ref. The consequence was not cosmetic: the parked tree had been holding a surface and a WIP slot, and `just dispatch` had refused #260 with `surface_conflict holder=170`. Without those two fields the correct reading of `unlanded_work` is "do not remove", and #260 stays blocked. This is also the episode that produced #272's `archive`/`restore` verbs, so the handoff field exposed a tool defect as well as avoiding a loss.

**No instance was found of a continuation going wrong *because* it trusted a handoff.** The nearest candidate is #290, whose handoff says "do not archive or remove it until a Claude seat has landed it" and whose successor archived and restored the tree anyway — but the successor's comment records both acts explicitly and the work survived, so that is a judged override, not a failure.

**The instructive near-miss is in the briefing, not the handoff (#290, Finding 2).** That agent's own report records the dispatch brief's stated ground truth — "daemon store/transport are NOT in-world" — as contradicted by the enforcing copy: `config/dispatch-routing-policy.json` and `tools/admission.py`'s `IN_WORLD_PREFIXES` both list `src/cti_daemon/transport.py`, so the corpus was owed and the whole "lands unaided from this foreign lane" expectation rested on a mistaken classification. That error sat in the hand-written variable half of the brief; the *derived* half, `just brief`'s gate line, reads the same `IN_WORLD_PREFIXES` and could not have said it. This is the sharpest evidence available on #212's mechanism question and it is not about hooks: **relayed state is where errors enter, derived state is not.** It argues for a handoff line that a tool copies into the brief byte-for-byte, on exactly the reasoning behind the verdict paste rule.

---

## 5. The currency problem, which outranks the measurement

#208 landed on 2026-08-05 and priced everything in input-equivalents. Between 2026-08-05 and 2026-08-06, #218, #220 and #232 re-measured this project's costs against the meter the subscription plan actually uses and inverted that currency: on this plan an output token weighs **at least 3,462×** a cache-write token — 104.6 M cache-write tokens moved the five-hour meter zero points where 181,253 output tokens moved it six — which is **33.10 points of a five-hour window per Mtok of output against under 0.0096 for a cache write.**

Applied to a 1,500-character handoff (466 tokens):

| act | tokens | plan cost |
|---|---:|---:|
| **writing** it | 466 output | 0.0154 points |
| **reading** it — one cache write plus 113 re-reads | ~53,100 cache | 0.00051 points |

Writing the handoff costs roughly **thirty times** what reading it for a whole median agent's life costs. #208's model has the read at 71% of the 8,180 and the write at 29%; on this plan the ratio is about 3:97 the other way. Every conclusion #208 drew from amplification — that what a continuation reads matters an order of magnitude more than what it costs to write, that raw-transcript handoff is unaffordable, that "carry the conclusion inline and the pointer beside it" inverts the `/handoff` skill's rule — is priced in the currency that inverted.

**So the 56% break-even is not merely unmeasured; it is denominated wrongly**, and re-running #212's four steps as written would produce a number in input-equivalents that no longer maps to spend. This is CLAUDE.md's elimination-context rule turned on the study that motivated the rule's most recent validations: an inherited measurement holds only in the context it was tested, and #208's context lasted about a day.

**What the measurement should be instead.** On this plan the handoff cannot pay for itself by displacing *characters of tool result* — those are input, and input is close to free. It can only pay by displacing **turns**: every `gh issue view` a successor does not run is an assistant turn's worth of generation not emitted, and generation is what the meter charges. So the re-specified measurement is:

1. For continuation-shaped dispatches, count **turns spent on state reconstruction** in the first ten turns, and sum the `output_tokens` billed on those turns — both are in the same transcripts #212 already names.
2. Price the handoff at its **write** cost in output tokens, which is the dominant term, and which is why the ~1,500-character cap matters far more under this currency than under #208's.
3. Break even when output tokens saved by the successor exceed output tokens spent by the predecessor writing it.

That is a strictly easier bar for a short handoff to clear and a strictly harder one for the 9,404-character report in §2, which costs 2,925 output tokens to write — about six times what the cap allows, and more than most successors emit on archaeology in ten turns.

---

## 6. What sample size would be needed

Taking the re-specified measurement of §5 and the pre-adoption control arm #208 already has (83 continuation-shaped dispatches), by Noether's formula for a Wilcoxon–Mann–Whitney comparison at α = 0.05 two-sided and 80% power, with the control fixed at 83:

| effect, as P(a handoff-borne continuation reconstructs less than a random pre-adoption one) | equal-allocation n per group | required treatment n with control = 83 |
|---|---:|---:|
| 0.80 — large | 15 | **9** |
| 0.70 | 33 | **21** |
| 0.65 | 58 | **45** |
| 0.60 — small | 131 | **311** |

**The honest headline is ~21 handoff-borne cold-start continuations** if the effect is the size #208 hoped for, ~45 if it is moderate, and out of practical reach if it is the size *Handoff Debt* actually found — note-based gains not significant at α = 0.05 for two of three successor models, which lands in the bottom row of that table.

Which row applies cannot be pinned from #208, because it published medians without dispersion (3,636 and 3,240 characters, no spread), and a 56% shift in a median maps to a *p* anywhere in 0.65–0.80 depending on the tail. **Whoever re-runs this should publish the dispersion**, which costs a line and is what makes the next power calculation a calculation rather than a table of scenarios.

Against a current rate of five handoff events in 5.3 days, 21 is about three weeks of writing — but the binding constraint is not the write rate, it is the read rate, which is zero until §3's delivery gap is closed.

---

## 7. The mechanism, weighed on the result

**Recommendation: do not wire `SubagentStart` `additionalContext` injection.** Three reasons, in order of weight.

1. **It fixes a problem the evidence does not show.** #211's fidelity concern is real and #290's Finding 2 confirms it in the general — relayed state is where errors enter. But injection is a *delivery* mechanism, and what failed in five days of delivery was not fidelity of relay. It was that nothing in the successor's briefing mentioned the handoff at all (§3), and that the artefact written was four times its own cap and shaped like a completion report (§2). Automatic injection of an uncapped report is worse than no injection: it makes a 9,404-character artefact a fixed cost on every dispatch, which is precisely the objection #208 recorded against the `memory` field.
2. **The predecessor ruled it out and the elimination still holds.** #208's own handoff carries, in its `Do not:` field: "Do not wire `SubagentStart` injection before #212 has data." #212 has no data. The elimination's context — no track record for the manual convention — is unchanged, so it travels.
3. **The cheaper intervention is derivable and is not a hook.** `just brief` already derives its gate line from the enforcing copy rather than restating it, and already inlines the imperative while citing the reasoning. Composing the handoff into the brief — copied byte-for-byte from `handoff_fetch.select`, never retyped — closes §3's gap, costs nothing on the dispatches that carry no handoff, and beats injection on #208's own inline-versus-pointer finding, because the successor gets the conclusion rather than an instruction to go and read. It is the verdict paste rule applied to a second artefact, and it is testable under `just unit`, where a hook's failure mode is silent.

The second thing worth building, and the one §2 says is urgent, is a **size and shape check on the handoff at write time**. The cap is currently prose in a document, and prose in a document held it once in nine tries. Under §5's currency the write is the dominant cost, so a cap that binds is the single change with the clearest effect on spend.

---

## 8. Proposed changes, verbatim and not landed

Wiring anything under `.claude/hooks/` is refused to a dispatched session (#294), so all of this is a proposal for the orchestrator. Nothing below was landed by this study.

**(a) The recommended change — a handoff section in the composed brief.** In `tools/brief.py`, alongside the existing derived sections:

```python
# The handoff, copied rather than relayed. #208 §6 asked the briefing to point at the
# handoff comment; #212 measured that nothing in five days pointed at one, and that the
# hand-written half of a brief is where a wrong ground truth entered (#290, Finding 2).
# So this inlines the bytes `handoff_fetch.select` returns and retypes nothing.
def handoff_section(issue: int, fetch: Fetch = handoff_fetch.fetch_comments) -> list[str]:
    """Render the issue's newest handoff verbatim, or say plainly that there is none."""
    try:
        carried = handoff_fetch.select(handoff_fetch.bodies(fetch(issue)))
    except handoff_fetch.FetchError as failure:
        return ["## Handoff", f"**COULD NOT LOOK** — {failure}. Read `just handoff {issue}` yourself."]
    if carried is None:
        return ["## Handoff", f"None on #{issue}. This is a fresh dispatch, not a continuation."]
    return ["## Handoff — your first read, verbatim from `just handoff`", "", carried]
```

A `FetchError` must not render as "no handoff": that is the fail-open shape `handoff_fetch`'s own docstring exists to prevent, and the three states must stay distinguishable in the brief exactly as they are in the tool's three exit codes.

**(b) The size check.** A new rung in `just check`, or a `--check` mode on `handoff_fetch`, that reds when the newest handoff on an issue exceeds the cap. The threshold is a decision, not a derivation, so it is named here rather than chosen: **2,000 characters**, which passes all three template-shaped handoffs written so far and reds both completion reports. Under §5's currency this is the highest-value rung available, because the write is the metered half.

**(c) The `SubagentStart` hook, recorded and not recommended.** For the record, so a successor does not re-derive it:

```json
{
  "hooks": {
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/inject-handoff.py\""
          }
        ]
      }
    ]
  }
}
```

with the hook emitting `{"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": "<the handoff>"}}`. It is documented and it would work. Revisit it only once (a) has run long enough to produce the ~21 continuations §6 asks for, and only if the measured failure is then fidelity of relay rather than absence of delivery.

---

## 9. Where the uncertainty is

- **This is a null adoption result, not a null efficacy result.** Nothing here says a handoff fails to displace archaeology. It says no cold-start continuation has read one, so the question is still open, and §3 names the mechanical reason.
- **Three reads by an orchestrator are not nothing.** One of them (#170) is the clearest correctness instance the convention has, and it involved no cold start at all. If the handoff's value turns out to be mostly to a *warm* orchestrator resolving a tool refusal, then the whole break-even framing — built on a fresh successor's opening archaeology — is measuring the wrong reader, and #212's arithmetic never applied.
- **§5's plan-currency figures are #218/#220/#232's, inherited here.** They were measured on this account against the five-hour meter and this study did not re-derive them; by the same elimination-context rule it applies to #208, they hold only while the plan does. On an API key, #208's original arithmetic applies unchanged and the 56% stands as written.
- **The token half was never run**, and this seat could not have run it. Nothing in §§1–4 depends on it — the sample count, the size distribution, the delivery gap and both correctness instances come from the issue tracker and the checkout — but §5's re-specification is a design, not a measurement, and the first person with a script-capable seat should run it against the pre-adoption corpus to establish the control arm's dispersion before any treatment arm exists.
