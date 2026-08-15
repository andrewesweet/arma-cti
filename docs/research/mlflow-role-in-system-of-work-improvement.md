# MLflow's role in autonomous improvement of the system of work

**Assessed:** 2026-08-14  
**MLflow version:** 3.15.1, released 2026-08-03  
**Sources:** first-party MLflow documentation, source/release history, and the current
`arma-cti` implementation

**Status:** Supporting rationale for the derived-evidence boundary adopted by
[target-state specification #376](https://github.com/andrewesweet/arma-cti/issues/376)
and [MVP specification #377](https://github.com/andrewesweet/arma-cti/issues/377).
The cited feature set is versioned research, not an authorization for MLflow to control work.

## Verdict

**Yes. MLflow should have a substantial role, but it should be the derived evidence,
evaluation, and experiment workbench—not the improvement controller or the source of
governance truth.**

MLflow 3.15.1 already supplies most of the generic product surface that would otherwise
be expensive to build: agent traces and trace search, production dashboards, experiment
and run comparison, evaluation datasets, code and LLM scorers, versioned judges,
feedback records, prompt and application lineage, offline evaluation, regression-test
reporting, and prompt optimization. ([3.15.1 release](https://github.com/mlflow/mlflow/releases/tag/v3.15.1),
[GenAI overview](https://mlflow.org/docs/latest/genai/overview/))

It does **not** supply the parts that make a self-improvement loop trustworthy:

- a frozen, preregistered protocol;
- randomized or otherwise controlled assignment of real work to stable and candidate arms;
- a holdout that candidate agents cannot inspect or mutate;
- policy-aware shadowing and canary activation;
- hard-invariant, rollback, and inconclusive semantics;
- author-distinct review and promotion authority; or
- tamper-resistant historical provenance.

Those remain responsibilities of the project-owned improvement controller and policy
deployer. MLflow records and helps evaluate what they do.

```text
delivery system
    │
    ├─ canonical OTel logs/metrics/traces + dispatch/gate/git records
    │       │
    │       ├─ durable local evidence and project ledger  ← source of truth
    │       │
    │       └─ MLflow projection                         ← explore/evaluate/compare
    │
    ▼
improvement controller
freeze evidence → retro → independent review → preregister experiment
       → replay → shadow → assign canary → evaluate → promote/rollback
         │          │          │              │
         └──────────┴──────────┴──────────────┴─ logs runs/results to MLflow
```

The short boundary is:

> **MLflow may measure a candidate and generate candidates. It may not choose who receives
> the candidate, declare it authoritative, or activate it.**

## What the current project already owns

The current implementation is not an empty observability surface waiting for MLflow.

- Every dispatched process receives six project identities through OpenTelemetry:
  dispatch, lane, profile, seat, issue, and base SHA.
  ([`Identity`](../../tools/dispatch.py#L909-L928))
- Dispatch records already preserve pre-work strata—gate tier, stable routing-class ID,
  and issue labels—without reconstructing them from outcomes later.
  ([`Strata`](../../tools/dispatch.py#L995-L1035))
- The ledger is deliberately a materialized view over a collector-owned bus. It prefers
  a non-rotating per-dispatch export, names degraded evidence, never invents missing
  observations, retains rows indefinitely, and keeps prompt content out of the normalized
  view. ([ledger implementation](../../tools/ledger.py#L1-L30),
  [ledger design](../telemetry-ledger.md))
- The ledger understands project semantics that MLflow does not: typed non-results,
  subscription-plan capacity rather than API list price, issue/base/time-bounded landing,
  seat-specific landing expectations, and exact evidence-source degradation.
- Codex dispatch currently exports only metrics to the loopback collector. The project has
  no live MLflow integration, and existing inspection found no operational cross-lane trace
  plane. ([Codex exporter](../../tools/dispatch.py#L2579-L2590),
  [existing gap analysis](claude-codex-mlflow-observability-gap-analysis.md))
- The current retrospective skill still performs a manual evidence sweep and asks for human
  sign-off, while ADR-0071 has already decided the target split: a retro investigates and
  files backlog work but lands nothing. ([current skill](../../.claude/skills/retro/SKILL.md#L12-L18),
  [ADR-0071](../adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md#L235-L267))
- ADR-0071's observatory is intentionally descriptive: it reports rework, stratifies on
  pre-work facts, and never routes. Its retained trial harness is explicitly
  orchestration-specific rather than a general experiment engine.
  ([observatory ruling](../adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md#L456-L525))

This establishes the integration rule: **the existing evidence plane is canonical;
MLflow is a projection and workbench over it.** Wholesale replacement would discard
stronger domain semantics and append-only evidence in exchange for a better UI.

## Feature assessment

| MLflow surface | What it contributes to system-of-work improvement | Boundary or limitation |
|---|---|---|
| **GenAI tracing** | Nested LLM/tool/agent spans, inputs and outputs, latency, token usage, sessions, tags, search, and trace UI. It can instrument frameworks directly or ingest OpenTelemetry GenAI semantic conventions. ([Tracing](https://mlflow.org/docs/latest/genai/tracing/), [GenAI conventions](https://mlflow.org/docs/latest/genai/tracing/opentelemetry/genai-semconv/)) | MLflow's OTLP server endpoint is `/v1/traces`, HTTP only; it is not the arbitrary OTel metrics-and-logs bus the ledger needs. Keep the collector in front and fan out traces. ([OTLP ingestion](https://mlflow.org/docs/latest/genai/tracing/opentelemetry/ingest/)) |
| **Trace search and dashboards** | UI/API filtering plus usage, latency, errors, token, quality, tool-call success and tool-latency views. This is an excellent observatory front end. ([Dashboard](https://mlflow.org/docs/latest/genai/tracing/observe-with-traces/dashboard/), [REST API](https://mlflow.org/docs/latest/api_reference/rest-api.html)) | Dashboard facts are derived observations, not dispatch or promotion decisions. SQL storage is required for the full dashboards. |
| **Tracking experiments and runs** | Mature APIs/UI for parameters, metrics, artifacts, code versions, nested runs, search, and side-by-side comparison. One process-improvement experiment can group replay, shadow, canary, and post-promotion runs. ([Tracking](https://mlflow.org/docs/latest/ml/tracking/)) | An MLflow “experiment” is an organizational container. It does not preregister a causal design, assign treatments, prevent peeking, or implement stopping rules. |
| **Offline evaluation** | `mlflow.genai.evaluate()` executes sync or async candidate functions across records, runs code scorers and judges, records row-level traces/assessments and aggregate metrics, and can re-score existing traces without rerunning the candidate. ([Agent evaluation](https://mlflow.org/docs/latest/genai/eval-monitor/running-evaluation/agents/), [trace evaluation](https://mlflow.org/docs/latest/genai/eval-monitor/running-evaluation/traces/)) | Strong for replay and held evaluation execution. It is not a sandbox and does not stop a candidate from reading the data it is passed. The protected evaluator must invoke it outside candidate workspaces. |
| **Regression testing** | `@mlflow.test` integrates evaluation with ordinary pytest, makes scorer failures fail CI, and records the complete session in an Evaluation Run UI. ([Regression testing](https://mlflow.org/docs/latest/genai/eval-monitor/regression-testing/)) | Useful for deterministic process-protocol regressions. Existing project oracles and typed verdicts remain authoritative; a judge does not replace them. |
| **Scorers and judges** | Built-in judges, guideline judges, custom LLM judges, and arbitrary code scorers; feedback may be boolean, numeric, categorical, or structured with rationale. ([Scorers](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/)) | Judge bias remains real and the docs recommend alignment to human feedback. Registered versioning does not cover code scorers or Guidelines judges, so scorer code and all promotion thresholds must remain Git-versioned. ([Scorer versioning](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/versioning/)) |
| **Automatic evaluation** | Runs registered LLM judges asynchronously against sampled/filtered incoming traces for continuous quality monitoring. ([Automatic evaluation](https://mlflow.org/docs/latest/genai/eval-monitor/automatic-evaluations/)) | It supports LLM judges, not code scorers. It is suitable for anomaly signals and retro triggers, not hard invariants or promotion. |
| **Automatic issue detection** | LLM analysis clusters trace failures and summarizes possible recurring causes across correctness, latency, execution, adherence, relevance, and safety. ([Issue detection](https://mlflow.org/docs/latest/genai/eval-monitor/ai-insights/detect-issues/)) | This is hypothesis generation. A cluster or generated “root cause” has not passed the retro's evidence re-derivation or independent review. |
| **Evaluation datasets** | Central living datasets with inputs, expectations, outputs, trace provenance, tags, experiment associations, schema/profile, and a content digest; production traces can be promoted into them. ([Dataset concepts](https://mlflow.org/docs/latest/genai/concepts/evaluation-datasets/)) | They are expressly living collections: records are merged and updated, schema evolves, and `last_update_time` is first-class. They are not a frozen preregistered holdout. Keep the authoritative manifest and digest in protected Git/object storage, and mirror a snapshot into MLflow for execution/UI. |
| **Feedback and labeling** | Assessments unify CODE, LLM_JUDGE and HUMAN sources, rationales and metadata. Review Queues assign structured trace questions and return answers to traces. ([Feedback](https://mlflow.org/docs/latest/genai/concepts/feedback/), [Review Queues](https://mlflow.org/docs/latest/genai/assessments/review-queues/)) | Feedback can be updated and deleted; override history is preserved only when the override API is used. Review Queues are experimental and would duplicate the project's issue/review scheduler. Use assessments as analytical records, not never-alone enforcement. ([feedback management](https://mlflow.org/docs/latest/genai/assessments/feedback/)) |
| **Prompt Registry** | Immutable sequential prompt versions, diffs, commit messages, prompt/run/trace lineage, structured outputs, model configuration, and mutable environment aliases. ([Prompt Registry](https://mlflow.org/docs/latest/genai/prompt-registry/), [lifecycle aliases](https://mlflow.org/docs/latest/genai/prompt-registry/manage-prompt-lifecycles-with-aliases/)) | Excellent for experimental wrapper prompts and judge rubrics. Operational process policy also includes skills, hooks, permissions, schemas, commands and ADRs, so Git remains authoritative. Evidence pins an exact version; aliases such as `production` are mutable deployment pointers and must never identify a treatment. Prompt versions can also be deleted. |
| **Prompt optimization** | `optimize_prompts()` connects registered prompts, training data, prediction, and scoring. Current optimizers include GEPA and MetaPrompting. ([Prompt optimization](https://mlflow.org/docs/latest/genai/prompt-registry/optimize-prompts)) | Candidate generator only. It searches the scorer supplied to it and can amplify evaluator weaknesses. No generated prompt reviews, promotes, or aliases itself. Evaluate on an untouched holdout through the ordinary process-change lifecycle. |
| **Application/model versioning** | LoggedModels can associate traces, evaluations, prompts, code/configuration and performance. Experimental Git versioning records branch, commit, dirty state and diff. Model Registry provides version/alias lineage for packaged models. ([Application versioning](https://mlflow.org/docs/latest/genai/version-tracking/), [Git versioning](https://mlflow.org/docs/latest/genai/version-tracking/track-application-versions-with-mlflow/), [Model Registry](https://mlflow.org/docs/latest/ml/model-registry/)) | A LoggedModel ID is a useful foreign key, not the policy identity. The project must compute one exact `process_manifest_digest` over all operative surfaces; Git-based app versioning is experimental and repository state alone does not identify which policy was active for a dispatch. |
| **Production retention and security** | Self-hosted SQL/artifact stores, authentication, RBAC, workspaces, client-side redaction, and trace archival are substantial operational capabilities. ([RBAC](https://mlflow.org/docs/latest/self-hosting/security/role-based-access-control/), [redaction](https://mlflow.org/docs/latest/genai/tracing/observe-with-traces/masking/), [trace archival](https://mlflow.org/docs/latest/genai/tracing/observe-with-traces/archive-traces/)) | MLflow is not an append-only audit log. Traces can be irreversibly deleted; runs can be soft-deleted then garbage-collected; tags and assessments are mutable; archive payload search is reduced and archival cannot be reversed. ([Tracing FAQ](https://mlflow.org/docs/latest/genai/tracing/faq/), [backend deletion](https://mlflow.org/docs/latest/self-hosting/architecture/backend-store/#deletion-behavior)) |

## Recommended target boundary

### MLflow should own the derived evidence and experiment workbench

Use MLflow for:

1. **Trace exploration.** Project normalized agent, tool, review, adjudication and
   initiative spans into MLflow; use its trace/session UI and API instead of building a
   bespoke trace browser.
2. **Experiment catalog and execution.** Represent each accepted process hypothesis as an
   MLflow experiment or stable experiment tag, and each replay/shadow/canary cohort as a
   run carrying the frozen protocol digest and treatment identity.
3. **Offline replay.** Run candidate prompts or bounded workflow functions through
   `mlflow.genai.evaluate()` against diagnostic and evaluator-supplied snapshot datasets.
4. **Result comparison.** Store primary measure, every guardrail, missing-data counts,
   exact per-case assessments and evidence artifacts. Use the UI to compare arms and
   versions.
5. **Secondary semantic evaluation.** Use versioned, author-distinct judges for qualities
   that deterministic code cannot assess, with their model, prompt, output, rationale and
   cost retained. Treat judge results as evidence unless the constitution explicitly
   authorizes a calibrated judge for a narrow decision.
6. **Working datasets.** Curate diagnostic failures and regression examples from production
   traces. The locked evaluator imports an exact snapshot; the live collection itself is
   not the holdout.
7. **Experimental prompt lifecycle.** Register wrapper prompts, retro-analysis prompts and
   judge rubrics; compare and optimize them; export an accepted exact version into the
   Git-owned policy bundle.
8. **Observatory presentation and triggers.** Use dashboards, automatic evaluations and
   issue detection to surface candidate patterns. A project-owned trigger records an
   immutable evidence boundary before starting a retro.

### MLflow should not own control or authority

Keep outside MLflow:

| Concern | Authoritative owner |
|---|---|
| Issue graph, WIP, eligibility and dispatch | outer coordinator and existing queue/dispatch surfaces |
| Stable/candidate assignment and contamination controls | improvement controller |
| Frozen experiment protocol and stopping rule | signed/Git-owned experiment manifest |
| Locked holdout content and access | evaluator service under a separate credential and storage boundary |
| Mechanical gates, Arma oracle and typed failure classes | existing project harnesses |
| Policy bundle and exact active version | Git plus `process_manifest_digest` |
| Shadowing, canary scope and exposure accounting | policy deployer/improvement controller |
| Promotion, rollback and `inconclusive` semantics | promotion controller inside the constitutional kernel |
| Author-distinct review/adjudication | #317-family review machinery |
| Tamper-resistant provenance | durable local evidence/export plus repository/tracker history |
| Constitutional permissions and human product authority | fixed project kernel |

MLflow Prompt Registry aliases, Model Registry aliases and ordinary run tags must not be
reused as the activation authority. They are mutable pointers and labels. After the
promotion controller commits an exact decision, it may update an MLflow alias as a
convenience projection; the alias does not cause or prove activation.

## Correlation and lineage contract

Before sending traces to MLflow, expand the current six-field identity with:

```text
cti.initiative_id
cti.work_item_id
cti.process_manifest_digest
cti.policy_release_id
cti.improvement_proposal_id
cti.experiment_protocol_digest
cti.experiment_id
cti.arm                  stable | candidate
cti.phase                replay | shadow | canary | post_promotion
cti.cohort_id
cti.assignment_id
cti.evaluator_digest
cti.dataset_snapshot_digest
cti.dispatch_id / lane / profile / seat / issue / base_sha
```

The controller mints these identities. MLflow run, trace, dataset, prompt and model IDs are
stored as foreign keys in the canonical record, never substituted for project identities.

At completion, a projector attaches project-computed facts to the MLflow run:

- typed end state and whether it was a result;
- gate verdict and exact landed SHA;
- review/fix rounds, findings and adjudications;
- initiative acceptance and architecture-audit outcomes;
- plan-cap consumption and its calibration ID;
- protocol violations, containment and human `process_rescue` events; and
- evidence completeness/degradation.

Do not calculate these independently in MLflow. Two implementations of “landed,” “result,”
or “plan cost” would create two control truths.

## Isolation and security requirements

Self-hosting is attractive because traces contain source, issue text, prompts, tool inputs,
tool results and possibly credentials. MLflow supports client-side span processors for
redaction, but the project must define the content policy before rich traces are enabled.
Structural full-coverage events should remain local; rich-content MLflow traces may be
sampled or redacted without weakening the canonical record.

More importantly, the actors need different credentials:

- ordinary candidate and implementation agents: append traces/runs only to their assigned
  experiment; no dataset-management, scorer-management, alias, delete, or promotion rights;
- retro/reviewer agents: read the frozen evidence window and append findings, but cannot
  activate candidates;
- evaluator service: can read the protected snapshot and log evaluation results, but the
  candidate cannot obtain its credential or storage path;
- promotion controller: read-only over evidence plus the narrow ability to activate an
  exact policy hash; and
- MLflow administrator: operational role outside every evaluated agent session.

RBAC helps express resource access, but if every dispatched agent receives one shared
MLflow credential, RBAC does not establish author distinction or holdout secrecy. The
current same-user execution model also means MLflow alone cannot be treated as protection
against a deceptive candidate. That is why promotion consumes a separately retained,
exact evaluation verdict rather than trusting a mutable dashboard row.

## Adoption sequence

1. **Add process-version identity first.** Compute the operative policy manifest/digest and
   attach it to all dispatches, review events, verdicts and initiative audits. MLflow cannot
   recover exposure attribution after the fact.
2. **Finish the canonical event contract.** Add review rounds, findings, adjudications,
   initiative outcomes, human product decisions versus process rescues, and completeness
   signals to the local evidence plane.
3. **Deploy pinned MLflow 3.15.1 as a non-blocking sidecar.** Use a SQL backend, auth/RBAC,
   backup, explicit trace retention, client-side redaction and no hard dependency from
   dispatch correctness to MLflow availability.
4. **Fan out traces from the collector.** Preserve the current all-signal capture; add MLflow
   only as a trace destination and mirror project outcomes after ledger materialization.
5. **Pilot one historical replay experiment.** Use an existing process question with a
   frozen Git-owned manifest, code-based project scorers and one secondary judge. Reconcile
   every MLflow result to canonical evidence.
6. **Adopt datasets and Prompt Registry at the experiment seam.** Pin exact dataset snapshot
   and prompt digests. Keep live policy in Git.
7. **Add the protected evaluator.** Its service account and holdout are inaccessible from
   candidate workspaces. Log results to MLflow and separately emit the exact signed/hashed
   verdict the promotion controller consumes.
8. **Add shadow and canary externally.** The improvement controller assigns work through the
   existing queue and dispatch surfaces; MLflow records arms and compares outcomes.
9. **Try prompt optimization last.** Only after a scorer is discriminating and a holdout is
   real; optimizer output enters as an ordinary untrusted process-change candidate.

## Final judgment

MLflow should become the **laboratory and observatory for the meta-loop**. It can remove the
need to build a trace database, evaluation runner, experiment comparison UI, feedback model,
working dataset service, experimental prompt registry, judge runner and prompt optimizer.

It should not become the **governor of the meta-loop**. The project still needs a small
improvement controller that freezes evidence, preregisters the experiment, assigns stable
and candidate work, protects the evaluator, interprets hard constraints, and promotes or
rolls back an exact policy artifact. The local OTel/ledger/git/tracker record remains the
evidence source from which MLflow is reconciled.

In the target-state diagram, MLflow therefore belongs inside the slower system-of-work
improvement loop as its evidence/evaluation/experiment plane—not around that loop as its
authority:

```text
observe ──MLflow──> diagnose → review → preregister
   ▲                                      │
   │                            evaluate/replay with MLflow
   │                                      │
   └── canonical outcomes ← canary ← external controller → promote/rollback
```
