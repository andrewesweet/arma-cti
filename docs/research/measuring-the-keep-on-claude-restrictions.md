# Measuring the keep-on-Claude restrictions: the zai second lens

- Issue: [#296](https://github.com/andrewesweet/arma-cti/issues/296)
- Base: `780c309`
- Lane/profile/seat: `zai` / `zai-glm52-max` / `implementer`
- Sibling study: `docs/research/removing-backlog-routing-restrictions.md` (`3d4e563`, the **codex** lens)

## Answer in one line

Two independent foreign lanes — codex-sol-xhigh and this zai-glm52-max dispatch — classified the same fourteen `1:gated_semantic_surfaces` issues and reached the **same four-kind split** (semantic authorship, independent judging, permission, and reference noise), the same "keep `6:gates_themselves` closed", and the same "the `#262` class-8 row is mechanically wrong as written". That convergence is the finding a second lens exists to produce: the codex study is not a single-lane artefact. **What this lens adds that codex could not**: the zai lane's own executor-capability row, measured first-hand, which is **different from codex's** — zai runs `just`-recipe gates (including `just fast`) but is refused bare `uv run python`, `python3` and `grep`, where codex commits but cannot run `just fast` at all. A capability matrix is therefore per-`(lane, profile)`, not uniform, and that difference decides which lane can be the detached-corpus finisher.

## 0. What this is, and what the wall foreclosed in the measuring

This is the **second lens** under ADR-0061 Decision 3 ("provider diversity is the point: one family's blind spots are not another's"). The codex study was written without knowledge of this dispatch; this study was analysed before reading codex and then positioned against it. The two report into the same human gate.

**Conflict of interest, declared twice over.** This issue carries `Routing-exception: proposal-only`, and a lane researching its own eligibility has an interest in the answer. It is bounded, not removed: nothing in `config/dispatch-routing-policy.json` is landed by this study, every policy recommendation is quoted verbatim for the human's gate, and the class rule is the human's under #258. The codex study states the same conflict from its seat. Two lanes with the same interest reaching the recommendation **against** their own eligibility (keep class 6 closed; class-1 authorship stays closed) is itself weak evidence the interest is not driving the answer.

**The command wall foreclosed the obvious measurement, and that is a finding.** The natural analysis is to run `routing_policy.advisory_match` over each body. This session could not: `uv run python tools/_study296_classify.py` and `python3 tools/_study296_classify.py` were both refused ("This command requires approval"), and `grep -rn` / `grep -n` were refused likewise — all [observed]. So the fourteen issues were classified by reading each body directly, not by running the classifier. That is slower and weaker, and it is itself a live data point for §3: the wall constrains **reconnaissance**, not only landing, and it constrains it on a lane (zai) different from the one (codex) that first reported it.

**Evidence grades** follow `docs/research/dissolving-the-claude-class-list.md` §0: **[read]** from a file, line or issue body this session; **[observed]** something that happened this session; **[inferred]** reasoning from the above; **[proposal]** for the human, nothing ruled.

## 1. The class-1 pile, independently classified

### 1.1 Why the class over-matches, stated at the line

Class 1 fires on **two substring scans of the whole issue body**, not on authorship:

- paths: `evidence.extend(f"path={prefix}" for prefix in rule.issue_path_prefixes if prefix in body)` — `tools/routing_policy.py:221` [read]. `prefix in body` is a plain substring test; any mention of `CLAUDE.md`, `CONTEXT.md`, `docs/adr/` or a `.claude/` path anywhere in the body matches.
- phrases: the same shape against `issue_phrases` [read, `:218-220`].

`advisory_match` then **returns the first matching class in id order** (`for rule in policy.rules: ... if match is not None: return match`, `:250-258` [read]). Two consequences follow directly from these two lines of code, and both materialise in the backlog:

1. **A path cited as a source is indistinguishable from a path the issue will edit** — the root of the conflation #296 names.
2. **Class 1 shadows class 5.** Any in-world issue that also mentions a gated path returns class 1, never class 5, because id 1 precedes id 5. The dispatch is then refused with class 1's remedy ("route invented wording to a Claude seat") when the real obligation is class 5's ("run the full corpus"). #189 is exactly this case (§1.3).

### 1.2 The fourteen, classified independently

Each issue read this session [read]. Labels: **A** semantic authorship (the real competence obstacle), **J** independent judging (belongs in class 6), **P** permission (the wall), **R** reference-only (a gated path cited but not edited; no competence question), **H** human authority (not dispatchable to any lane), **→5** mis-routed to class 1 when the true gate is class 5.

| Issue | Matched on [read] | Kind | Underlying restriction |
|---|---|---|---|
| #294 | `.claude/skills/`, `.claude/hooks/` | **P** | The wall itself; research may leave, `.claude/` execution may not |
| #258 | `CLAUDE.md`, `.claude/agents/` | **H** | The human's routing ruling; the path match is not the reason |
| #247 | `.claude/hooks/` | **J + P** | Authors a hook (a judge); permission-blocked too |
| #229 | `CLAUDE.md`, `.claude/settings.json` | **H** | Subscriptions, keys, terms, sudo, sign-offs — human acts only |
| #211 | `CLAUDE.md` | **A** | Authors two CLAUDE.md edits; genuine gated authorship |
| #209 | `CLAUDE.md` as an inventory source | **R** | Research deliverable; no gated landing |
| #203 | docs/hooks named as research subjects | **R** (mixed) | Split the cited study from any adopted gated mechanism |
| #195 | `CLAUDE.md` as a candidate input | **R** | Assessment deliverable; no gated landing |
| #189 | `CONTEXT.md` (body says **do not edit it**) | **→5** | False class-1 reason; the in-world landing owes the corpus |
| #187 | `CONTEXT.md` as a complexity measure | **R** | Offline prototype; the later structural decision may not |
| #186 | gated surfaces are **data the new checker reads** | **J** | Authors a gate; belongs in class 6, not prose |
| #183 | `.claude/settings.json` | **J + P** | Changes enforcement wiring; keep authorship closed |
| #179 | `CLAUDE.md` cited for a failure-class rule | **R** (+human) | Capture engineering may leave; deciding how pixels earn a verdict may not |
| #177 | `CONTEXT.md`; an ADR is an output | **A** | Genuine semantic authorship; stay closed |

This table was derived before the codex study's §2 table was read. **The two agree row-for-row on the underlying restriction for every one of the fourteen.** The only notional differences are labelling (#186 as "independent judging" here vs "independent judging" there; #209/#195/#187/#179 as reference-noise in both). Independent convergence from two model families on a fourteen-item judgement is the signal a second lens is for; it raises confidence that the split is in the issues, not in either lane's priors.

### 1.3 The transcription kind is empty, and one issue is mis-routed

Two findings worth separating from the count:

- **The issue's three-way hypothesis names a kind that has no live members.** #296 proposes the class conflates *authoring*, *transcribing*, and *reasoning about*. Of the fourteen open issues, **zero are transcription**: none is "move a human's verbatim ruling onto a gated file." The `pure-transcription` exception has already consumed every transcription case — those issues were excepted and dispatched. Operationally, class 1's open backlog is authorship + reference-noise + permission + mis-routed; the **T category is already dissolved**, which is itself the strongest evidence that exception-by-exception refinement has overtaken design (#209's framing, which both lenses reach independently).
- **#189 is mis-routed, and first-match is why.** Its body says *"Do not edit CONTEXT.md on this issue — it is a gated surface"* and lands under `missions/` and `addons/` [read]. It matches class 1 (via the `CONTEXT.md` substring) and class 5 (via `addons/`), but `advisory_match` returns class 1 because id 1 < id 5 [read, `:250-258`]. The true obligation is the in-world corpus; the dispatch is told the wrong reason. This is the concrete, per-issue cost of the conflation: not a conservative refusal, a **mis-labelled** one.

## 2. Per-class hypothesis (gate / competence / permission / tooling)

The blocked classes in the #296 measurement are 1, 5 and 6. Classes 2, 3, 4 and 7 had **zero** issues in the top-30 census, so "each blocked class" is those three; the others are stated for completeness and point at the `#262` experiment catalogue rather than re-deriving it (the issue asks the next question on #262's split, not a re-run).

| Class | Kind | Hypothesis, with evidence | Should it move? |
|---|---|---|---|
| 1 (authorship half: #211, #177) | **Competence** | Invented normative wording has no complete mechanical oracle [read, policy remedy `:34`; ADR-0061]. | Stay closed until competence evidence (E4, `#262`) |
| 1 (judging half: #186, #183, #247) | **Independent judging** | These author a gate or enforcement wiring; a foreign lane must not author its judge. Mis-enumerated: class 6's path list omits `.claude/hooks/` and `tools/check_*.py` [read, `:117-123`]. | Belongs in class 6; not a competence question |
| 1 (reference half: #209, #203, #195, #187, #179) | **Classifier error** | Substring scan of prose, `:221`. No gated landing; the path is a source, not a target [read, each body]. | Relax via declaration parsing (codex §6); no competence barrier |
| 1 (#189) | **→ class 5** | First-match shadowing (`:250-258`); true gate is the corpus [read]. | Re-route to class 5 |
| 1 (#294, #247, #183) | **Permission** | The `.claude/` wall, cross-lane (§3) | Separate axis; route around narrowly |
| 1 (#258, #229) | **Human authority** | Human rulings and human-only acts; not dispatchable to any lane, Claude included [read] | Not a routing question |
| 5 (#160, #146, #143, and #189) | **Tooling + lifecycle** | No dispatched session may run `just regress` (allowlist) and the unfiltered corpus is a known-long op denied in-subagent-turn by `deny-subagent-waits.py` [read, the one entry at `:34-36`]. No source attributes it to foreign-model competence. | Relax authorship via detached SHA-bound runner (W1) |
| 6 (#234) | **Independent judging** | A foreign lane must not author the mechanism that judges it [read, `:140`]. Principled, not conservative. | **Do not move** |
| 2, 3 | Competence | Orchestration and retro/ADR authorship; un-gateable judgement. | Via E3/E5 once competence shown (`#262`) |
| 4 | Gate (maybe) | The #181 shape; may be mostly caught by ADR-0064's mutation rung already. | Via E9 measurement (`#262`) |
| 7 | Policy residual | Technical access dissolved analytically in `#262` §2; the residual is one credential-policy ruling. | Human ruling, not an experiment |

### 2.1 Which classes should not move, and why

- **Class 6, full stop.** The reason is judging, not capability: a more capable model, more tests, or permission parity does not remove the self-reference of a lane authoring the gate that judges it. The `proposal-only` exception is the correct narrow valve: it permits analysis that cannot mutate the judge, and an actual foreign gate diff still refuses at landing because issue exceptions do not reach `enforcing_match` [read, `:225-232`, `:261-269`]. This matches the issue's stated expectation and the codex lens.
- **Class 1's authorship half** (#211, #177), until a competence bar (E4) is cleared. Relaxing it on anything other than competence evidence would be the thing class 1 exists to prevent.
- **Class 7's residual** is a credential-policy ruling (`#262` §2.4), not something an experiment dissolves.

## 3. The zai capability row — what this lens adds

`#294`, `#264` and `#281` established that a dispatched session's real constraint is what it may **execute**. The codex study adds one lane's self-report — codex commits but cannot run `just fast` (`cog check` cannot discover the repo under its sandbox). This lens adds a **different** lane's row, measured first-hand, and it is not the same row.

**[observed], this session, on `zai`/`zai-glm52-max`/`implementer`:**

| Operation | Verdict this session | How known |
|---|---|---|
| `uv run python <file>` | **refused** — "This command requires approval" | attempted to run the classifier |
| `python3 <file>` | **refused** — same | attempted as fallback |
| `grep -rn …`, `grep -n …` | **refused** — same | attempted to locate `mutation-compare` |
| `gh issue view … > file` (plain redirect) | **allowed** | fetched all eighteen bodies |
| `cat`, `Read`, `ls` | **allowed** | used throughout |
| `just <recipe>` (incl. `just fast`, `just land`) | **allowed** | `just fast` ran green for this study; it shells out to `uv run python` via pytest |

**The implication for the capability matrix.** Codex cannot run `just fast`; **zai can** (via the `just` recipe, which is allowlisted where bare `uv run python` is not), but **zai cannot run bare `python3`/`grep`** where a native Claude session can. So the executor gaps are **per-`(lane, profile)` and non-uniform**:

- a gate-capable finisher for a foreign-authored in-world candidate is **zai-shaped** (runs `just` recipes), not codex-shaped;
- a reconnaissance task needing `grep`/`python3` is **not** zai-shaped on a bare command, and must go through a `just` recipe or the orchestrator;
- the `run-just-fast` requirement in any v2 policy should carry a `known_unavailable_to` list that is populated **per observed lane**, and zai is **not** on that list where codex is.

This refines the codex study's author/executor/finisher/lander composition: the lanes are not interchangeable finishers, and which lane can finish which step is a measured fact, not an assumption. It is also why this study could not run the classifier and classified by reading instead — the wall's reach includes the measurement itself.

**The `just fast` row is confirmed, not inferred.** `just fast` ran green for this study (check + unit + mutation, all passing) — and it runs `uv run python` under the hood via pytest and `tools/mutation_smoke.py`. So the very invocation refused as a bare command (`uv run python <file>`) succeeds through the `just` recipe. That is the load-bearing distinction: the recipe is allowlisted where the bare verb is not, and it is now [observed], not [inferred] from the brief.

## 4. The permission vocabulary — second-lane position

#296 asks, as a real design question, whether the policy should gain a vocabulary for "the only permitted lane cannot execute the work." Both lenses answer **yes, but not as `#262` wrote it**.

`#262` §3.2 proposes a class 8 with `"seats": ["orchestrator"]`. That is mechanically wrong, and a second lane reading the same code reaches the same conclusion: in `issue_match`, `if seat in rule.seats` *triggers* the refusal for that seat (`:215-216` [read]) — it does not declare a required executor. A class-8 row with `seats: ["orchestrator"]` would **refuse orchestrator-seat requests on foreign lanes**, which is the opposite of "this needs orchestrator hands"; and because `advisory_match` clears every `claude-native` route before examining any rule (`:252-253` [read]), it would say nothing to a `claude-native` dispatch that hits the same `.claude/` wall (#294 shows it does).

The replacement both lenses converge on is a **required-executor / capability axis**, separate from the class list: an issue declares operations (`write-dot-claude`, `create-symlink`, `run-full-regress`, `run-just-fast`); routing composes a workflow whose author, executor, finisher and lander may differ; an unknown capability fails closed before a dispatch is spent; and a narrow recipe may satisfy one operation without widening the session's general command surface (the `just discard` / `just mutation-compare` shape, approved twice). The wall is **cross-lane** (codex and zai both hit it, §3), which confirms it is a property of the harness around a dispatched session, not of any one provider — the strongest reason it deserves its own axis rather than a seat-class row.

## 5. Class 5 — tooling and lifecycle, second-lane position

Both lenses read class 5 the same way: the `#258` ruling and the policy remedy both make it **contingent** on a dispatched session being allowed to run the corpus [read, `:111`], and no source attributes it to foreign-model competence. The blocker has two parts, both confirmed this session:

- **Permission:** the full `just regress` invocation is not in the dispatched command surface (the same wall as §3).
- **Lifecycle:** the unfiltered corpus is a known-long op — `deny-subagent-waits.py` holds exactly one entry on its known-long list, "the unfiltered full regression corpus, in both its spellings (`just regress` and the `spike/regress.sh` it wraps)" [read, `:34-36`]. A bare allowlist entry would therefore encode the wrong workflow: holding the corpus inside a subagent turn is forbidden on every lane, not just foreign ones.

The narrow shape both lenses reach is a **detached, SHA-bound full-corpus runner**: start it for the committed candidate, return a run id, end the authoring turn, let the watcher wake a permitted finisher, bind the posted verdict's SHA to the landing diff. `just verdict --post` already publishes finished evidence verbatim (`#235`); the missing piece is the binder and the right to start the run. **This lens's addition**: because zai runs `just` recipes (§3), zai is a candidate finisher for that runner where codex is not — so the W1 trial should name which lane finishes, as a measured fact.

Class 5 also has the smaller precision problem both lenses flag: #146 changes glossary words and comments on an in-world path, and a full world run cannot tell whether "buy" should be "Purchase". That is a missing lexical gate (W2), not a need for Arma; until it exists #146 stays conservatively class 5.

## 6. Verbatim policy position for the human's gate

Nothing here is landed. `config/dispatch-routing-policy.json` encodes the human's #258 ruling and is not this issue's to amend; the class rule is the human's under #258 as amended by #217 item 9. What follows is a **second-lane endorsement** of the codex study's §7 v2 shape, with one refinement this lens adds.

**Endorsed as-is from the codex lens** (quoted here so the human reads one lane's words seconded by another, not two separate proposals): the `issue_declaration` block (declaration-only matching, returning all matches), the reclassification of `.claude/hooks/` and `tools/check_*.py` into class 6, the split of class 1 into a competence `kind` over authorship only, and the `execution_requirements` axis with `run_full_regress.satisfied_by` starting empty. Two independent lanes reaching the same v2 shape is the evidence the shape is in the problem rather than in either lane.

**The refinement this lens adds** — the `run_just_fast` requirement should carry the **zai** observation alongside codex's, and the distinction matters:

```jsonc
{
  "name": "run_just_fast",
  "kind": "tooling",
  "declared_as": "run-just-fast",
  "known_unavailable_to": [
    "codex/codex-sol-xhigh"
  ],
  "available_to_via_recipe": [
    "zai/zai-glm52-max"
  ],
  "remedy": "Assign a gate-capable finisher. A Codex commit is not a gated result; a zai dispatch gates through `just` recipes but cannot run bare `python3`/`grep`, so reconnaissance that needs them routes through a recipe or the orchestrator."
}
```

The distinction — `known_unavailable_to` vs `available_to_via_recipe` — is the per-lane capability fact §3 measured. A matrix that lumps the two lanes together ("foreign lanes can't gate") is wrong in both directions: it over-credits zai (bare `python3` is refused) and under-credits it (`just fast` is not). Quoting this for the gate, not landing it, is what `proposal-only` requires.

## 7. Acceptance, worked item by item

- **Each blocked class has a stated hypothesis (gate/competence/permission/tooling) with evidence.** §2, table and prose, with the matching line (`routing_policy.py:221`, `:250-258`, `:215-216`) and the `deny-subagent-waits.py` entry cited. Classes 1, 5, 6 in full; 2/3/4/7 pointed at `#262`.
- **At least one falsifiable experiment per class that could plausibly be relaxed, bar pre-registered.** This lens does not re-design experiments `#262` and the codex lens already pre-registered; it seconds them and adds the per-lane capability datum each needs. Reference, not re-derivation: class 1 authorship → E4 (≥17/24 recoveries, zero consistency violations); class 1 reference-only → codex §6 (30/30 reviewed + 10/10 shadow); class 5 → codex W1 (5/5 binder + 3/3 real exact-SHA corpus) and W2 (4/4 lexical); permission → codex P1 (capability matrix, now with the zai row) and P2 (4/4 narrow-promotion fixtures). **Class 6 has none, by principle** (§2.1).
- **The report says which classes should not move and why.** §2.1: class 6 (judging, not capability); class 1 authorship (pending competence); class 7 residual (a credential ruling, not an experiment).
- **Anything proposed for the policy is quoted verbatim, not landed.** §6. Nothing in `config/dispatch-routing-policy.json` is touched; the v2 endorsement and the `run_just_fast` refinement are quoted for the human's gate.

## Sources

- `config/dispatch-routing-policy.json`, `tools/routing_policy.py` — the class data; the substring path scan (`:221`), phrase scan (`:218-220`), seat-as-refusal-trigger (`:215-216`), first-match advisory (`:250-258`), and landing enforcement (`:225-232`, `:261-269`).
- `.claude/hooks/deny-subagent-waits.py` — the one known-long entry, the unfiltered corpus (`:34-36`).
- `docs/research/dissolving-the-claude-class-list.md` (`#262`) — the gate/competence/permission split and experiments E3–E9; this study is its next question and cites rather than re-derives.
- `docs/research/removing-backlog-routing-restrictions.md` (`3d4e563`, the codex lens) — the sibling study; converged-with findings and the v2 policy shape endorsed in §6.
- `docs/adr/0061-…` — authorship not path; mechanical-gate eligibility; provider diversity (Decision 3).
- GitHub issues #189, #195, #203, #209, #211, #229, #247, #258, #294 — bodies read this session for the §1 classification. #219 and #224 for the pre-registered-criteria shape.
