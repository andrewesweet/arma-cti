# The observatory widens to the whole system of work, and still reports rather than routes

Delegated-decision: no
Date: 2026-08-21
Supersedes: after human sign-off, ADR-0071 ruling 6's input scope, which is limited to
rework over dispatched implementer work. This record does not amend ADR-0071 in place and
does not claim an amendment number; ADR-0071 already uses Amendment A8 for #391
Supersedes: nothing else — ADR-0061 Decision 5 and ADR-0071 rulings 1 through 5 and 7 stand
Reviewed-by-human: pending
Claimed: 0078 — baseline `origin/main` at `29cf0e8` tops out at ADR-0077. The original
2026-08-21 scan of sixty then-open issue comments found ADR-0071, ADR-0075 and ADR-0077 and
no number at or above 0078; that dated scan has the blind window `AGENTS.md` records

## Recorded rulings

### R1 — recorded ruling: widen the observatory's input scope

The observatory's input scope widens from rework over dispatched implementer work to the
**whole system of work**. This is the human's choice “(b)” from 2026-08-21: propose the
superset and supersede ruling 6's narrower scope, rather than build the narrow observatory
or keep a parallel layer.

This is an input-scope ruling only. It does not select event names, fields, storage,
analysis methods, retention, automation authority or implementation sequencing.

### R2 — recorded ruling: cost per landed issue is primary, per lane and never summed

Cost per landed issue is the system's primary metric. Rework, human minutes and wall-clock
are its drivers, not competing primary metrics.

Spend is reported once per lane, in that lane's own meter, and is never summed across
lanes. ADR-0061 Decision 5 and ADR-0071 ruling 6 refuse conversion between provider meters;
the human's 2026-08-21 choice explicitly said to honour that refusal, file calibration work
separately and **never overturn it here**. A calibration may improve one lane's own report;
it does not create or authorise a cross-lane total or ranking.

Therefore no single cross-lane cost-per-landed-issue number exists under this ruling. A
missing calibration is reported as missing, never as zero or cheap.

### R3 — recorded ruling: read-only authority, to its stated boundary

The human ruled “Read only”. The boundary already stated by ADR-0071 ruling 6 remains
binding: nothing derived from observatory telemetry excludes a profile, reroutes work or
trips a breaker.

That sentence does not answer every other way a reading could affect work. Those
capabilities were returned to the human and are ruled by R6 below; this record does
not extend “Read only” by guessing.

### R4 — recorded ruling: consumer order

Consumers are ordered as the human ruled them: first an analytical agent on demand, then
the in-loop orchestrator, then the human at retro time. Consumer order grants no consumer
more authority than R3 and the later scope ruling permit.

### R5 — existing ADR-0071 ruling 6 output carried forward

The earlier binding output contract remains unchanged:

- fix rounds per landing is the profile-ranking key; other rework measures are reported
  beside it, unranked;
- only implementer-seat profiles with a landing denominator are ranked; zero-denominator
  profiles remain visible and unranked, and other seats' rework is reported but unranked;
- the key says where rework appears, never who caused it;
- spend remains per lane and outside the ranking;
- comparisons stratify only on pre-work signals; outcome measures are description, not
  strata;
- the containment column is absent until a durable source exists, rather than present and
  falsely empty; and
- the “20 to 30 landings” sample-size statement remains an estimate, not a measurement.

R1 widens what can be observed. It does not change any item in this list.

## Research facts: current base and dated observation

### F1 — research fact: the headline figures are dated observations

The research's figures were computed on 2026-08-21 from mutable local files,
then-current `origin/main` and live GitHub results with discarded scripts. No input
snapshot, digest or executable extractor was committed. Its 372.7-hour window, 639
dispatches, 84.0% unused ruled capacity, 0.48 mean concurrency and 251.8 hours in idle gaps
are dated observations, not a reproducible baseline and not acceptance values.

Existing specialised readers already aggregate some history: `just occupancy` aggregates
dispatch intervals, `just gate-clock-history` aggregates gate-clock rows, and
`just ledger-sync` can materialise dispatch rows. What does not exist is one persisted,
general query layer joining dispatch telemetry, gates, reviews, landings, issues and cost.

### F2 — research fact: current custom telemetry has eight event names

Baseline `29cf0e8` emits eight repository-owned OTel log event names through
`tools/otel_event.py`: `cti.breaker.transition`, `cti.queue.transition`,
`cti.admission.trial.transition`, `cti.review.arbiter.resolved`, `cti.review.round`,
`cti.review.escalation`, `cti.review.dispute` and `cti.review.terminus`.

It emits no repository-owned OTel span or metric, and no `cti.dispatch.*`, `cti.gate.*` or
`cti.landing.*` event. Gate-clock separately records whole-recipe status for `unit` and
`fast`; no gate leg records its own pass or fail result.

### F3 — research fact: #464 has not landed and session history is discarded

On this base, `tools/quota_tap.sh:54-62` rolls the Claude Code status-line spool once from
`statusline.jsonl` to `statusline.jsonl.1`; the next roll overwrites the older backup.
Commit `4a48f96` for #464 is parked at `origin/issue-464-parked` and is not an ancestor of
`29cf0e8` or this branch.

The tap records Claude Code status-line render payloads, not every worker or every session.
Its available payloads contain useful session-grain fields but have no timestamp added by
the tap. Until #464 lands, older non-dispatched-session history is destroyed, so no sound
fully loaded period cost can claim the whole history. R1 places this source in scope; it
does not make the incomplete denominator complete.

## Research proposals — non-binding

### P1 — research proposal: preserve closeout states in lifecycle events

The research proposes lifecycle events, but current result files remain the authority and
their distinctions cannot be flattened.

A proposed `cti.dispatch.finished` projects the complete atomic `result.json` union. It
preserves `status={child_not_launched,child_state_unknown,child_finished,
harness_failed_after_child}` and, when applicable, `failure_phase`, exception detail,
unknown-child action, refusal and failure class, child return code, classified outcome,
timestamps, gate-clock collection, harness finish and review delivery.

`child_finished` is lifecycle completion, not a successful return code.
`harness_failed_after_child` does not identify review-delivery failure without the separate
`review_delivery` fact. Review delivery remains distinguishable as posted, not attempted,
or the typed `review_delivery_failed` refusal; a timeout cannot be rewritten as definitely
not posted because the remote call may have completed before the timeout was observed.
`child_state_unknown` retains #495's explicit inspect-and-reconcile action and must never
look safe to retry.

Dispatch closeout is currently atomic only within `result.json`: the writer stages,
flushes, `fsync`s and same-directory-replaces a complete document. A failed write publishes
no result. An independent OTel append cannot be atomic with that replace, so a dispatcher
death or result-write failure cannot honestly produce ordinary `cti.dispatch.finished`.
A later design must choose one atomic authority or a separate closeout-failure record; the
state is otherwise unrepresentable and stays unknown.

A proposed `cti.landing.finished` carries three independent dimensions:

- repository state: not landed; work on `origin/main` with the main-checkout merge
  outstanding (current exit 2); or repository landing complete (current exit 0);
- audit posting: yes, no or not attempted, with reference or reason and the exact limit
  `verified=posting_call not_verified=content_or_quality`; and
- issue closing: yes, no or not attempted, with SHA or reason.

An exit-0 landing remains a repository landing when audit posting or issue closing fails;
the event must preserve those failures rather than report full closeout. Exit 2 returns
before both tracker acts, so both are not attempted. Exit 1 means nothing landed. Proposed
field spellings may change; those distinctions may not.

The current `cti.review.round` event is a transition summary, not a paired lifecycle. No
current code defines a review-round start and finish boundary. Paired review-round events
remain an unresolved design problem, not a property of the current event.

### P2 — research proposal: additional capture

The research proposes, without binding later issues:

- per-leg gate outcome and duration for every landing gate recipe;
- `block_reason` on wait intervals, with an explicit undetermined value;
- an analytical `abandoned` terminal state that preserves, rather than replaces, dispatch
  closeout states and existing failure classes;
- qualified object relations;
- `first_pass` per stage, including undetermined; and
- periodic queue-depth and oldest-item-age samples.

Each item may be adopted, revised or rejected separately. R1 does not mandate it.

### P3 — research proposal: analysis method

The proposed statistical method is a per-stratum XmR chart using Rule One only, frozen
limits, separate strata and separate counts for not-a-result classes. No human ruling
selects SPC, Rule One, its constants or its alerting behaviour.

Dispatches per issue is proposed as an unranked companion to the ruled fix-round key
because the dated observation showed more variance. It does not replace or join the
ranking key without another ruling.

### P4 — research proposal: attribute and event policy

The proposed policy uses `gen_ai.*` semantic conventions where one exists, `cti.*` where
none does, a registry with requirement levels, deprecation rather than repurposing, and
events instead of project metrics until a live scan-free question exists. None of those
choices is a recorded human ruling.

Raw evidence is not a permanent archive on this base: ledger pruning removes retained raw
exports, and the current status-line spool overwrites its older backup. Any later attribute
compatibility promise must state the retention it actually covers.

### P5 — research proposal: store, summary and analyst contract

The research proposes a derived store rebuilt from available source files, a generated
committed per-issue summary, and three analyst artefacts: schema reference, query cookbook
and hazards list. DuckDB, one canonical flattening, the committed row, the attribute
registry and those three artefacts are design proposals. No ruling here mandates them.

The proposed non-dispatched-session cost input depends explicitly on #464 landing. Before
that dependency is satisfied, a rebuild may report available spool coverage but may not
call its denominator complete.

## R6 — recorded ruling: what a reading may influence

Each capability below carries one mode. The mode governs readings derived from observatory
telemetry only: existing mechanisms that consult live state — the breaker's own read, the
failure-class table's re-dispatch response, `config/escalation-conditions.json` — are
unaffected by every row.

| Capability | Mode |
|---|---|
| Reorder queue work | advise |
| Admit WIP | advise |
| Select an initial lane | observe |
| Select a reviewer | observe |
| Trigger watching | control |
| Trigger escalation | advise |
| Select an arbiter for an escalated finding | observe |
| Retry a dispatch | observe |
| Affect gate acceptance | observe |
| Affect repository landing acceptance | observe |
| Affect audit posting | observe |
| Affect issue closing | observe |
| Select which gate tier runs | observe |

The thirteenth row is added by this ruling and was not in the draft's table. `just brief`
derives the gate tier from the in-world surface list, so a reading that selects a cheaper
tier resembles scheduling and is acceptance.

Lane selection and reviewer selection are the rerouting R3 already forbids. They are ruled
`observe` here for completeness, and a future `control` on either is an amendment to R3
carrying its own record, never a scope choice made in this table.

Watching is the one live authority granted, and it is bounded: a telemetry-armed watcher may
report, and may not stop, retry or re-dispatch. Retry stays `observe` on its own row, and
`child_state_unknown` keeps #495's inspect-and-reconcile action and never looks safe to retry.

The three modes mean:

- **observe** — report facts only; neither a tool nor the in-loop orchestrator uses the
  reading to choose or cause the capability;
- **advise** — recommend an action to the human, but no tool or in-loop orchestrator acts
  from the reading; or
- **control** — a tool or the in-loop orchestrator may use the reading to choose or cause
  the capability, subject to every other existing safety and acceptance rule.

| Capability needing a ruling | What `control` would permit | What `observe` or `advise` would forbid | #478–#493 consequence | Human choice |
|---|---|---|---|---|
| Reorder queue work | Work-item age, queue depth or another reading may change which eligible item runs next. | #486 and #492 remain reports or human recommendations; they cannot reorder the queue. | Changes the authority of #478/#482's query layer and #486/#492's leading indicators. | advise |
| Admit WIP | Occupancy or queue readings may open capacity or admit another item. | #485 and #492 cannot change WIP state or admission. | Determines whether #485 occupancy and #492 depth are scheduler inputs or analysis only. | advise |
| Select an initial lane | Per-lane cost, failures or history may influence lane selection within whatever registry rules remain. | #481, #482 and #488 stay outside dispatch resolution. | Must clarify whether this is the “reroutes work” already forbidden by R3 or an amendment to it. | observe |
| Select a reviewer | Review-effectiveness or relation data may influence reviewer selection. | #487 and #491 cannot affect review dispatch. | Must clarify whether reviewer selection is routing under R3. | observe |
| Trigger watching | Age, block reason or depth may arm or intensify a watcher. | #486 and #492 cannot replace or trigger fixed watcher behaviour. | Decides whether their leading indicators are operational or reported. | control |
| Trigger escalation | Rework, age, abandonment or queue readings may start an escalation. | #484, #487, #489 and #492 cannot add escalation triggers. | Existing review-loop escalation conditions remain the only automatic ones unless this is allowed. | advise |
| Select an arbiter for an escalated finding | A reading may influence which otherwise eligible profile the existing arbiter walk resolves for the finding. | #487's rework and #491's relation data remain reports or human recommendations; they cannot alter the arbiter walk. | Determines whether #478/#482 may feed #487/#491 readings into arbiter routing or only report them. | observe |
| Retry a dispatch | A terminal reading may cause a re-dispatch when existing safety checks allow it. | #489 and any dispatch lifecycle event remain evidence only. | Any permission must still forbid automatic retry of `child_state_unknown` until #495's reconciliation completes. | observe |
| Affect gate acceptance | Historical or per-leg readings may contribute to a gate's green/red result. | #479/#483 recording stays advisory and fail-open. | `control` changes those issues' current acceptance contract; the other modes preserve it. | observe |
| Affect repository landing acceptance | Conformance, first-pass, relation or summary readings may add a rung or refusal governing whether work reaches `origin/main`. | #487, #490, #491 and #493 remain analytical outputs; `just land` keeps its existing repository-landing authorities. | `control` requires an explicit acceptance rule and tests; the other modes add none. | observe |
| Affect audit posting | After repository landing, a reading may influence whether or when the audit is posted. | Readings may describe or recommend audit posting, but no tool or in-loop orchestrator may cause, suppress or delay it from telemetry. | Determines whether readings exposed by #478/#482, including #490/#491/#493 outputs, may drive audit posting or remain analytical. | observe |
| Affect issue closing | After repository landing, a reading may influence whether or when the issue is closed. | Readings may describe or recommend issue closing, but no tool or in-loop orchestrator may cause, suppress or delay it from telemetry. | Determines whether readings exposed by #478/#482, including #490/#491/#493 outputs, may drive issue closing or remain analytical. | observe |
| Select which gate tier runs | A reading may choose which gate tier a change runs — for example, a cheaper tier than the in-world surface list implies. | `just brief` keeps deriving the gate tier from the in-world surface list; no reading selects or cheapens the tier. | A reading that selects a cheaper tier resembles scheduling and is acceptance; this row keeps #478/#482's readings analytical. | observe |

## R7 — recorded ruling: only a marked statement binds

Only a statement beneath a **Recorded ruling** heading in this record is binding. Every other
statement here, and the whole of `docs/research/system-of-work-observability.md`, is advisory
by default. Citing an unmarked sentence as policy is an error however that sentence is worded,
and a later issue adopting one adopts it by its own ruling rather than by citation.

This ruling replaces the completeness the draft could not establish. Three labelling passes each
found further unmarked normative text, and the terminal review recorded that inspection cannot
prove a fourth would be the last. A default that unmarked text does not bind removes the failure
class without anyone having to prove a negative.

## Orchestrator working convention pending human ruling: changing this draft

Pending sign-off, the orchestrator will change a recorded ruling only in response to another
human ruling. Calibration evidence alone will not overturn R2's refusal to combine lane
meters. A future human may revisit that refusal, but this human ruling said not to do so
here.

Research proposals need no overturning event because they are not adopted decisions. A
later issue may reject one on code facts, cost or a better design. #464 landing would
satisfy the named spool-retention dependency; it would not supply timestamps, recover
already discarded history or settle any authority choice above.
