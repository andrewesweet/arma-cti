# The keep-on-Claude bar on the gates retires, and a gate landing is reviewed from another lane

Delegated-decision: no
Date: 2026-08-18
Supersedes: ADR-0071's disposition of routing class 6 — the row's keep-on-Claude bar, which
that table recorded as kept because retiring it before an enforcement existed "would leave
the gates with neither rule", is retired here and the enforcement lands with it. ADR-0071
row 6 is amended in place as Amendment A3 rather than left to disagree with this record
Supersedes: none otherwise — ADR-0071 rulings 1 through 7 stand unchanged, including the
`orchestrator_claude_only` carve-out of ruling 1, which this decision does not reach
Reviewed-by-human: the human's instruction of 2026-08-18, given on being told that routing
class 6 refused every non-Claude lane on the gate paths: "Codex only being allowed to take
read only work was definitely not my intent. It should be a full peer to the Claude on CC
and Zai on CC paths, subject to model appropriateness rules." Followed by the instruction to
implement the orchestrator's recommendation, which is what #406 carried and what this record
states. This is the human's own decision, not one taken in their stead
Claimed: 0073, after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0072, at
`be3d846`) and a scan of the comment threads of #389, #394, #402 and #405 — the open issues
whose subject could carry a claim — which mention no ADR above 0071. **Stated limit:** the
exhaustive open-issue scan CLAUDE.md prescribes could not be run from this session, because
`gh search issues` was permission-blocked; the rebase backstop is what covers the gap, and a
collision found there is renumbered on the rebase as prescribed

## How this landed, because it landed in two pieces

**This decision reached `origin/main` as two commits, minutes apart.** The first retired the
bar — the policy row, this record, and the prose on every surface that describes the row —
and the second added the enforcement: the cross-lane predicate on `tools/land_review.py`'s
never-alone rung, `tools/land.py`'s wiring of it, and the tests that hold both. Everything
below is true of the pair, and was written in that tense while only the first was landed;
each surface said so in its own words for the length of the window.

The order was forced rather than chosen, and #364 is why: `just land` reads the routing
policy from `origin/main`, never from the branch it is landing. A single commit carrying
both halves would have run its own new rung against the pre-#406 policy, which still refused
a non-Claude lane the gate paths — so the rung would have demanded a cross-lane review that
the policy judging it would not let anyone dispatch. The human ruled the split on 2026-08-18
and accepted the window: never-alone (ADR-0071 ruling 4) was enforced throughout it, and what
was briefly absent was only this class's cross-lane requirement, which nothing enforced
before this decision either.

## The decision

**Routing class 6's keep-on-Claude bar is retired, and the invariant it stood in for is
enforced in its place.** Two rules lived on that row and they were not the same rule:

- The **invariant** — no instance authors the gate that judges it. It binds every instance,
  Claude's included, and nothing enforced it.
- The **refusal that actually fired** — the older keep-on-Claude bar, selected by lane: a
  non-Claude lane was refused the gate paths and the Claude lane was exempt.

From today the row refuses nothing. `config/dispatch-routing-policy.json` class 6 carries
`refuses: false`, so a `codex` or `zai` dispatch naming those paths is admitted exactly as a
`claude-native` one is, and so is a `just land` from any lane. What enforces the invariant is
one predicate added to the never-alone rung ADR-0071 ruling 4 already runs at every landing
(`tools/land_review.py`): **for a landing whose diff touches a class-6 path, the review
verdict clearing it must come from a different lane than the author's**, not merely a
different profile.

Three refusals carry it, all fail-closed:

| kind | fires when |
|---|---|
| `review_same_lane` | the diff touches a gate path and the verdict's reviewer lane is a lane the issue's records place on the work |
| `review_lane_unknown` | it touches one and either the reviewer's lane or an author profile is not in `tools/dispatch.py`'s registry, so the two cannot be compared |
| `gate_class_undetermined` | the trusted policy or the diff could not be read, so whether it touches one is unknown |

Two consequences are recorded rather than left to be discovered. First, class 6's
`landing_path_prefixes` is now the **one authority** for what a gate path is — the position
class 5's list holds for in-world surfaces since #302 — so `parse_policy` refuses that row an
empty list: a row that emptied would compute "nothing is a gate" and clear every same-lane
review in silence. Second, a diff touching a gate path is **not** exemptible by
`config/review-exemptions.json`. That table is not the routing policy's own exception list, so
`binds_every_instance` does not reach it, and an entry there covering a gate path would clear a
gate change with no review at all — worse than the same-lane review this decision is about. The
table ships empty, so this changes nothing today; the ordering is what stops filling it from
reopening the hole.

`tools/land_review.py` joins the class-6 path list, because a row that names its own
enforcement and leaves that enforcement outside its coverage is the self-exemption the class
exists to forbid. Its neighbours `tools/review_loop.py` and `tools/review_exchange.py` do not
join: they are records and readers rather than the rung, and the coverage question generally
is the one ADR-0071 filed and this decision does not answer.

*(Amendment A1, 2026-08-18, #416 — the human's instruction carried by that issue, whose body
names the degradation, its visibility and exhaustion as the only trigger; the wording of this
note is the implementer's rendering of it, posted to the issue before anything landed, and the
human may amend it there.)* *The rule this record states had no answer for the branch whose
authors span every lane: the admissible reviewer-lane set is then empty, no dispatch can ever
satisfy the predicate, and the landing refuses forever. #405 sat in exactly that state — green
at the gate and unlandable by construction — because the project had deliberately spread its
work across all three lanes, which is the outcome this decision's own retirement of the
provenance bar exists to enable; the rung punished the goal rather than a breach of it.*

***The requirement degrades rather than refusing forever.** Where every lane the registry
carries is a lane the issue's records place on the work, the cross-lane predicate falls back
to ruling 4's own rule — a verdict from a **different profile** than any author, which is
never empty while more than one profile exists — and the rung has already enforced that rule
by the time it reaches the lane question, so the fallback holds by construction. The landing
records the degradation in its own key rather than by omission: `gate_review=lane_exhausted`,
printed beside the reviewer lane and the author lanes, so a reader sees that the stronger
check could not run and what ran instead. A rung that silently downgrades is worse than one
that refuses; a rung that refuses forever is worse than both.*

***Exhaustion is the only trigger, and it is derived, never declared.** The comparison is
computed at landing time from `tools/dispatch.py`'s registry and the issue's dispatch records
and declared authorship — no flag, no exemption entry, no record of a past exhaustion — so a
lane joining or leaving the registry moves the degradation with it, in both directions: a
landing that cleared as exhausted refuses again the day a fourth lane registers, and a
landing that refused clears the day a lane retires with its authors' records still in place.
Every case where a cross-lane reviewer **is** available refuses `review_same_lane` exactly as
this record first stated it. This is not the escape hatch the cost section below refused: an
escape hatch is a caller's declaration, and this fires only on an empty set that no caller
can write into being.*

## Why

The bar was provenance, not protection, and the record already said so. Class 6's own remedy
conceded that a Claude landing on the gate paths "has cleared nothing" — so the surface most
at risk, a gate edited by the lane that authors nearly every gate change, was the one the rule
exempted. A rule that clears the arrangement it exists to catch, and refuses the arrangements
it does not, is not a weak version of the invariant; it is a different rule wearing its label.

The reason recorded for keeping it — that retiring it before ADR-0071's sequencing step 7
landed "would leave the gates with neither rule" — is spent. Ruling 4's never-alone check has
been mechanically enforced at the landing since #334, and since #398 it reads the declared
authorship record too. It is lane-blind and it runs on every landing, so the rung the
invariant needs already exists; what it lacked was one predicate.

That the predicate is a **lane** and not merely a profile is ruling 4's own argument taken one
step further. Ruling 4 rests on the second instance being genuinely different — a same-model
review makes never-alone a ritual — and same-provider models share failure modes, which is why
the review seat's resolution already prefers a different lane. On the gates themselves, where a
missed defect disables the check that would have caught the next one, that preference is worth
promoting to a requirement.

Finally, the human's instruction is the decision's own ground: a non-Claude lane restricted to
read-only work on the gate paths was never the intent, and "subject to model appropriateness
rules" is a capability qualifier, which is what seats and `SEAT_PROFILE_BLOCKS` already encode.
It is not a provenance qualifier, and nothing here reintroduces one.

## What this costs

**Some gate landings now need three instances rather than two.** Where every dispatch on an
issue sits on one lane, the reviewer must come from another; where dispatches on an issue span
two lanes, only the third is left. The author set the rung compares against is the
*potential*-author set — every profile a dispatch record or a declaration places on the issue,
whether or not that run wrote a line — so it over-excludes by construction, on the trade
ADR-0071 ruling 4 already made: over-excluding costs a resolution step, under-excluding costs
the invariant. The clearance says so in its own bytes rather than leaving the qualification two
tools upstream.

**A gate landing can now be blocked by a lane being down.** With three lanes and two excluded,
a breaker trip on the third stops gate work until it clears. That is a real availability cost
and it is accepted rather than mitigated here; the mitigation, if one is wanted, is a fourth
lane rather than an escape hatch, because an escape hatch on this class is the self-exemption
the class forbids. *(Amendment A1 names the floor this paragraph stopped short of: with three
lanes and three excluded there is no lane left to trip, and the answer there is the derived
degradation above, not a refusal with no end. A fourth lane remains the real mitigation — it
re-arms the refusal — and the degradation remains the opposite of an escape hatch, because it
fires on an empty set no caller can declare into being.)*

**No routing class refuses a landing any more.** Class 6 was the last row that both refused and
carried landing prefixes, so `routing_policy.enforcing_match` returns `None` for every input
against the live table and `just land`'s routing rung is left refusing only an unreadable
policy or an unreadable diff. The rung is kept rather than deleted — a refusing row is one
table edit away — and the policy's `coverage` sentence now says what a `routing=clear` line
does and does not mean.

## What would overturn this

**A class-6 defect that a cross-lane review passed and a Claude-only review would have
caught.** That is the finding the retired bar's argument predicted and this decision denies: a
gate change landed from any lane, cleared by a reviewer on a different lane, that turns out to
disable or weaken a gate in a way a `claude-native` reviewer would have refused. One such case
is evidence that the bar was protection after all and that provenance carried information the
lane predicate does not.

Two nearby findings would **not** overturn it, and are named so they are not mistaken for it. A
gate defect that a cross-lane review passed and a Claude-only review would *also* have passed
is evidence about review depth, not about lanes. A gate defect landing on a path class 6 does
not name is evidence about coverage, which is #331's open half, and would have gone uncaught
under the bar equally.

## Cross-references

- **#331** is **narrowed**, not closed and not unaffected: its substance is discharged for this
  one class, and what it still owns is the coverage question — the gates class 6's path list
  does not name.
- **#389** asked whether the bar survived deliberately or was forgotten, on the ground that its
  stated retirement condition was already spent. The answer is neither: it was never the
  human's intent. This record answers that issue.
- **#364** records that a branch changing the routing policy cannot be gated against its own
  change, because the landing reads the policy from `origin/main` rather than from the branch.
  #406 was therefore authored on `claude-native` under the bar as it stood, and the first
  non-Claude landing on a gate path comes after it. #364 is unaffected and stays open.
- **#405** carries the sandbox half of the same instruction: a Codex implementer that cannot
  run the gate it must run. Policy parity without that is parity on paper.
