# Implementation stack for the autonomous system-of-work MVP

<!-- absent-path -->
<!-- A dated research record: the repository paths it cites are the tree as it stood when
     the research was done, and some belong to other projects entirely. Neither is a claim
     about this tree today, which is what the marker above tells `just check-doc-paths`. -->

**Research date:** 2026-08-15  
**Scope:** the breadth-first walking skeleton: initiative planning, deterministic outer
coordination, the post-#317 work-item loop, initiative audit, and one primitive autonomous
continuous-improvement cycle

**Specification baseline:** [target state #376](https://github.com/andrewesweet/arma-cti/issues/376)
and [MVP #377](https://github.com/andrewesweet/arma-cti/issues/377). The issue bodies are the
published specifications; this document is their non-normative implementation design.

**Status:** Non-normative implementation design for #377. The specification and its child issues
#378–#388 govern scope and acceptance; implementation may refine this design without rewriting
their product obligations.

## Recommendation

Build the MVP as a small repository-owned Python control plane around the machinery this
repository already has. The recommended stack is intentionally uneventful:

- Python 3.13 for a pure reconciliation kernel and thin Control Action adapters;
- GitHub Issues for the visible initiative, sub-issue, dependency, and work-item graph;
- the existing `just queue`, worktree, dispatch, watcher, recovery, review-loop, ledger, and
  landing ports for execution;
- versioned Markdown for product artifacts and JSON Schema for agent/controller messages;
- the existing JSON/JSONL plus atomic-rewrite pattern for disposable local runtime state,
  protected by one singleton file lock;
- a polling `--once` reconciler, run continuously by a user service only after it works as a
  deterministic one-shot command;
- the existing OpenTelemetry and ledger path as canonical evidence; and
- optional local MLflow as a non-authoritative projection for trace exploration and primitive
  before/after experiment comparison.

Do not begin with Symphony, Temporal, DBOS, LangGraph, an agent-team framework, PostgreSQL,
Redis, a message broker, webhooks, Kubernetes, or a policy engine. Each may solve a later
problem, but each either duplicates existing control surfaces or hardens a scale/trust boundary
the walking skeleton has not exercised.

The specifications close five choices that the research draft had left implicit:

- the MVP configures one Product Curator and admits at most one active product Initiative;
- the controller invokes Initiative Planning after it observes a curated Desired Outcome;
- a valid agent-derived plan becomes operative without a human approval gate;
- only a Product Question returns to Product Curation; platform administration remains outside
  the development control loop; and
- a due Improvement Cycle runs between product-Initiative boundaries through a standing internal
  Improvement Initiative, initially changing only prompts, briefs, and non-authoritative
  observatory definitions.

```text
GitHub issue graph (desired and product-visible state)
                         │
                         ▼
              Python reconciler --once
     collect facts → reduce → plan actions → apply
             │              │             │
             │              │             └─ host-owned GitHub publisher
             │              └─ typed agent-stage dispatch
             └─ local journal, dispatch records, worktrees
                         │
                         ▼
       existing queue / dispatch / review / land machinery
                         │
                  OTel + project ledger
                         │
                         └──────── optional MLflow projection
```

The companion [C4 workspace](autonomous-mvp-workspace.dsl) models the system context,
containers, controller components, single-host deployment, Initiative flow, and improvement
flow.

## Refined domain model

### One new domain, several bounded contexts

The root [`CONTEXT.md`](../../CONTEXT.md) is the ubiquitous language of the Arma CTI product.
The system of work is a separate proposed domain. Its language belongs in this design until the
MVP is ratified; adding it to the gameplay glossary, or creating a repository-wide context map
now, would make a research proposal operative policy.

This separation also exposes two vocabulary collisions in the first draft:

- **Effect** already means an accepted world change delivered to Arma through the outbox.
- **Observation** already means the strategic picture available to one Commander.

The control plane therefore uses **Control Action** and **Control Fact**. It also uses **Stage
Verdict**, rather than overloading product outcome or the Command Port's Judgement.

| Term | Meaning in the system-of-work domain |
|---|---|
| **Product Curator** | The human authority that chooses a Desired Outcome and answers questions whose resolution would change product intent. |
| **Desired Outcome** | A versioned statement of product value supplied by the Product Curator. It is immutable within an Initiative revision and remains an audit input rather than being discarded after specification. |
| **Initiative** | One Desired Outcome together with the derived artefacts and delivery progress intended to satisfy it. |
| **Product Specification** | Agent-derived, product-facing obligations explaining what must be true and why; it contains no implementation plan. |
| **Implementation Design** | Optional cross-Work-Item technical decisions, shared invariants, interfaces, schemas, sequencing, and rollout constraints. It is not a collection of each Work Item's local plan. |
| **Design Disposition** | Either `provided(ref, reasons)` or `not_required(reasons)`. Every published Initiative has one, so absence never silently means “not needed.” |
| **Work Item** | One independently dispatchable and independently landable slice of delivery. A GitHub issue is its tracker representation, not the domain concept itself. |
| **Work Graph** | Stable Work Item keys plus dependency edges and explicit traceability to Product Specification obligations. |
| **Work Run** | One bounded attempt to advance one Work Item through implementation, exact-candidate review, gates, and landing. |
| **Initiative Audit** | A semantic assessment of one exact Initiative revision and integrated Git SHA against the Desired Outcome, Product Specification, and Implementation Design. |
| **Delivery Gap** | A valid product obligation or design constraint not satisfied by the integrated implementation; it becomes another Work Item. |
| **Planning Gap** | A Desired Outcome obligation missing or contradicted in the Product Specification, Implementation Design, or Work Graph; it returns the Initiative to planning. |
| **Product Question** | An ambiguity that cannot be resolved without changing or choosing product intent; it returns to the Product Curator and is not retried as agent failure. |
| **Improvement Cycle** | One frozen evidence window, at most one proposed Process Change, its resulting Process Revision, and a retain/amend/revert disposition. |
| **Process Change** | A proposed modification to the system of work. In the MVP it is publishable autonomously only when every touched surface is in the low-risk allowlist. |
| **Process Revision** | The exact Git revision of the operative system-of-work surfaces used by a run. |
| **Control Fact** | A normalized fact read from GitHub, Git, worktrees, dispatch records, gates, or the ledger. |
| **Control Action** | A deterministic, idempotent request to one external port, such as publishing a Work Item or starting a Work Run. |
| **Stage Verdict** | A schema-validated result from a bounded semantic agent stage. |

### Context map

These are module and ownership boundaries inside one Python modular monolith. They are **not**
microservices.

| Bounded context | Owns | Supplies to the next context |
|---|---|---|
| **Product Curation** | Desired Outcome and answers to Product Questions | Curated intent to Initiative Planning |
| **Initiative Planning** | Product Specification, Design Disposition, Implementation Design, Work Graph, plan revision | A publishable Initiative revision to Work Coordination |
| **Work Coordination** | Eligibility, WIP, active Work Run exclusion, dispatch ordering, reconciliation | One eligible Work Item reference to Work Delivery |
| **Work Delivery** | Work Run, candidate, review rounds, gate verdict, landing evidence | Integrated SHA and Work Item close evidence to Outcome Assurance |
| **Outcome Assurance** | Frozen Initiative Audit subject, Stage Verdict, classified gaps | Delivery Gaps to Coordination; Planning Gaps to Planning; Product Questions to Curation |
| **Process Improvement** | Evidence window, Process Change proposal, active/candidate Process Revision, disposition | A Process Change represented as an ordinary Work Item to Delivery |
| **Evidence/Observatory** | Append-only operational evidence and derived ledger/MLflow projections | A frozen evidence window; never a scheduling or activation decision |

```text
Product Curation → Initiative Planning → Work Coordination → Work Delivery
       ▲                   ▲                                      │
       │ Product Question  │ Planning Gap                         ▼
       └──────── Outcome Assurance ◀──────────────── integrated evidence
                              │
                              └─ Delivery Gap → Work Coordination

Work Delivery → Evidence/Observatory → Process Improvement → ordinary Work Item
```

### Aggregate boundaries and invariants

| Aggregate | Root and consistency boundary | MVP invariants |
|---|---|---|
| **Initiative** | Initiative ID, Desired Outcome revision, and plan revision | Desired Outcome is retained unchanged within the revision; publication requires a Product Specification, a Design Disposition, stable Work Item keys, an acyclic Work Graph, and every specification obligation referenced by at least one Work Item. A curator change creates a new Desired Outcome revision and returns to planning. |
| **Work Run** | Work Run ID for one Work Item | At most one live Work Run per Work Item; eligibility is rechecked at launch; a candidate is reviewed and gated by exact identity; a typed non-result never closes the run as success or failure. |
| **Initiative Audit** | Audit ID over one plan revision and integrated SHA | A `pass` applies only to the frozen subject; every non-pass finding is classified as Delivery Gap, Planning Gap, Product Question, or typed non-result. |
| **Improvement Cycle** | Cycle ID and frozen evidence-window identity | At most one proposed change; only allowlisted surfaces may change autonomously; the evaluated and activated Process Revision is exact; MLflow IDs are references, never authority. |

GitHub cannot atomically publish the whole Initiative aggregate. Publication is therefore an
idempotent process manager: stable Initiative and Work Item keys let repeated reconciliation
complete a partially published graph without creating a second logical aggregate.

### Initiative lifecycle

Lifecycle state is derived from Control Facts; it is not another mutable source of truth.

```text
curated → planning → publishable → delivering → audit_due
                 ▲                      ▲           ├─ pass ─────────→ satisfied
                 │                      └───────────┤ Delivery Gap
                 ├──────────────────────────────────┤ Planning Gap
                 │                                  └─ Product Question
                 └──── needs_product_input ◀────────────────────────┘
```

`blocked_external` and typed non-results suspend progress without changing the semantic state.
The controller retries only conditions already classified as transient.

## 1. Reconciliation, not an agentic scheduler

Use the controller pattern Symphony demonstrates, but implement it in the repository's existing
Python tool layer. One cycle should:

1. collect GitHub state, local dispatch records, worktrees, and completed results as Control
   Facts;
2. reduce those facts to the derived lifecycle model;
3. derive the next legal Control Actions without performing them;
4. execute each Control Action through a narrow adapter;
5. journal what was attempted and what facts resulted; and
6. start the next cycle from reality rather than trusting the previous cycle's memory.

Keep the reducer pure. Control Actions such as `PublishWorkItem`, `AttachWorkItem`,
`StartWorkRun`, `PublishAudit`, and `RequestProductInput` should be data. This makes dry runs,
replay, simulation, and crash-point tests natural. A claim is not an independent aggregate in
the MVP: it is the exclusion fact established by the live Work Run's dispatch record and
worktree.

Start with one coordinator process and enforce that fact with `flock`. Keep local state under
`~/.arma-cti/`, beside the current queue and dispatch records and outside every worktree. Use an
append-only JSONL transition journal plus atomically rewritten materialized JSON views, matching
the current repository. GitHub and Git remain authoritative, so the local view must be
rebuildable.

SQLite is the next step only if local state becomes authoritative, multiple writers are needed,
or querying the journal becomes painful. Python's `sqlite3` is serverless and part of the
standard library, so it is a low-cost migration target. DBOS becomes attractive later if durable
timers, queues, multi-step resumption, or multi-host execution become real requirements; its own
documentation starts on SQLite but recommends PostgreSQL for distributed operation.
([Python `sqlite3`](https://docs.python.org/3.13/library/sqlite3.html),
[DBOS database connections](https://docs.dbos.dev/python/tutorials/database-connection))

## 2. GitHub as the visible graph

Represent an Initiative as a parent issue. Represent Work Items, including later Delivery Gaps,
as sub-issues, and ordering as native issue dependencies. GitHub exposes both through REST and the
current CLI: sub-issues can be attached with `gh issue edit --add-sub-issue`, dependencies with
`--add-blocked-by`, and dependencies can be read as structured JSON.
([sub-issue API](https://docs.github.com/en/rest/issues/sub-issues),
[dependency CLI/API](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies))

For the first version, keep the Desired Outcome, Product Specification, Design Disposition, and
optional Implementation Design as Markdown sections on the parent issue, or as linked repository
Markdown when they become too large. Add stable machine markers for Initiative ID, plan revision,
specification-obligation IDs, and Work Item keys. Do not introduce GitHub Projects as another
state store; it can become a derived UI later.

Planning agents should not create a variable number of issues directly. They should emit a
declarative plan package with stable obligation and Work Item keys. Before publication, the
controller validates its schema, uniqueness, referential integrity, dependency acyclicity, Design
Disposition, and declared obligation coverage. A deterministic publisher then creates missing
issues, links existing ones, and safely resumes after partial failure. Every remote mutation needs
an idempotency key represented in the created artifact, because a local transaction cannot be
atomic with GitHub.

Use a narrow local intake port—working name `just initiative submit <plan.json>`—for the handoff
from the controller-invoked Initiative Planning stage. It validates and stores the exact package
bytes under the local control store, returns a plan-revision ID, and performs no tracker mutation.
The next reconciliation publishes that revision. The same port can bootstrap a package produced
by today's interactive workflow, but that compatibility path is not the MVP's steady-state human
interface.

For a published revision, use an append-only-by-policy, controller-authored **Plan Revision**
record on the parent issue containing the human-readable artefacts, machine block, and content
digest. The parent issue points at the active revision; a replan appends a new record instead of
editing the old one. This lets a lost local view be rebuilt from GitHub and gives the Initiative
Audit exact bytes to freeze. The MVP trusts the controller's GitHub credential not to rewrite an
old record; tamper-resistant storage belongs to later hardening.

Declared obligation coverage is structural traceability, not proof that a Work Item really
satisfies its obligation. Outcome Assurance remains responsible for that semantic question.

The trigger for Implementation Design is semantic, not “more than one ticket.” Multiple Work
Items are evidence that a design may be useful, but the actual question is whether they share an
invariant, interface, schema, migration, sequencing constraint, or cross-cutting technical
decision. In the MVP, the planning stage must return either the design or an explicit
`not_required` rationale; the controller validates that a disposition exists rather than trying
to reproduce the semantic decision.

Poll initially. It needs no inbound server, webhook secret, delivery queue, or redelivery
recovery. GitHub recommends polling only as often as needed and supports authenticated
conditional requests with ETags, where a `304` does not consume the primary rate limit.
([GitHub REST best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api))
Webhooks are a later latency optimization, not the source of truth.

## 3. Typed LLM stage boundaries

Use LLMs only for semantic stages: initiative planning, implementation, work-item review,
initiative audit, retrospective diagnosis, and process-change implementation. Give every bounded
stage a versioned result envelope:

```json
{
  "schema_version": 1,
  "stage": "initiative_audit",
  "initiative_id": "init-317",
  "input_revision": "...",
  "verdict": "findings",
  "findings": [
    {
      "finding_id": "gap-O3",
      "kind": "delivery_gap",
      "obligation_refs": ["O3"],
      "summary": "..."
    }
  ],
  "proposed_work_items": []
}
```

Use JSON Schema Draft 2020-12 for these envelopes and fail closed on unknown versions, missing
required fields, invalid enums, or unexpected properties. JSON Schema is specifically a
standard vocabulary for annotating and validating JSON documents.
([JSON Schema introduction](https://json-schema.org/learn/getting-started-step-by-step))

The installed runners already provide the transport mechanism: Claude Code supports
`--json-schema`; Codex `exec` supports `--output-schema` and writing the final answer to a file.
Hide those spellings behind one stage-runner adapter, then independently revalidate the saved
result before the controller acts. Provider-native structured generation reduces repair turns;
host validation remains the authority.

Keep prompts and schemas in the repository. Each dispatch should record the issue, initiative,
stage, base SHA, process Git SHA, prompt/schema revision, lane, profile, and dispatch ID. Prefer a
fresh session plus durable artifacts to opaque conversation resumption.

Do not adopt LangGraph, AutoGen, CrewAI, or another agent framework for the MVP. The project
already has agent execution, profiles, worktrees, review, recovery, and landing; another
framework would create a second inner orchestrator.

## 4. Compose the existing inner loop

The outer reconciler should call or import the existing typed ports, not reimplement them:

- queue policy and WIP eligibility;
- verified worktree creation and occupancy checks;
- profile/seat resolution and dispatch;
- watcher and recovery records;
- the post-#317 candidate review/adjudication state;
- typed gates and non-results; and
- landing.

Expose a new `just orchestrate --once` as the stable command. Internally, prefer Python calls or
machine-readable JSON modes over scraping human-oriented command output. Add `--dry-run` from the
first slice: it should print collected Control Facts, derived lifecycle, and planned Control
Actions while performing no mutation.

Run the stable one-shot command from a `systemd --user` service with bounded restart only after
the one-shot protocol is proven. Do not begin with a web server. Its initial operator surface can
be the existing tracker, transition journal, dispatch records, and `just watch-report`.

## 5. Modular-monolith architecture

Bounded contexts should become Python module boundaries inside the controller, while existing
delivery commands remain a separately runnable toolchain. The deployment stays one host and one
scheduling authority.

| Controller component | Owns | Explicitly does not own |
|---|---|---|
| **Control Fact Collector** | GitHub/Git/local-record adapters and normalization | Lifecycle decisions |
| **Reconciliation Kernel** | Pure derived state and ordered Control Action plan | Network, filesystem, model invocation |
| **Initiative Policy** | Publication readiness, Design Disposition, graph and traceability invariants | Work Item implementation plans |
| **Coordination Policy** | Dependency eligibility, WIP, active-run exclusion, launch-time freshness | Semantic prioritization invented at dispatch time |
| **Outcome Assurance Policy** | Exact audit subject and finding classification/routing | Tracker mutations or self-remediation |
| **Process Improvement Policy** | Due rule, frozen window, allowlist, one-change limit, Process Revision disposition | Evidence generation or MLflow administration |
| **Semantic Stage Gateway** | Brief construction, provider invocation, schema normalization and validation | Authority to apply the returned proposal |
| **Control Action Executor** | Ordered, idempotent application through narrow ports | Re-deciding the action plan |

Three anti-corruption layers keep external representations out of the domain kernel:

1. **GitHub adapter:** labels, assignees, issue JSON, sub-issue IDs, and API failures become
   normalized Initiative, Work Item, dependency, and availability facts.
2. **Agent-provider adapter:** Claude and Codex flags, stream formats, and exit behavior become one
   `StageRequest → StageVerdict` contract.
3. **Delivery-tool adapter:** queue, dispatch, worktree, review, gate, recovery, and landing output
   become typed Work Run facts; the controller does not infer meaning from prose.

MLflow is a one-way projection adapter. No component reads an MLflow alias or mutable run field to
decide eligibility, activation, or rollback.

### Proposed code shape

Keep system-of-work code out of `src/cti_daemon`, whose domain is the in-game AI Commander and
Campaign. A proposed layout consistent with the repository's existing process tooling is:

```text
tools/
  orchestrate.py                  # just-facing CLI: --once, --dry-run, serve
  system_of_work/
    domain/
      initiative.py               # Initiative aggregate and planning invariants
      coordination.py             # eligibility and active Work Run exclusion
      assurance.py                # exact audit subject and gap classification
      improvement.py              # Improvement Cycle and allowlist policy
    application/
      reconcile.py                # Control Facts → derived state → Control Actions
      stages.py                   # StageRequest / StageVerdict application service
    adapters/
      github.py                   # GitHub anti-corruption layer and publisher
      delivery.py                 # existing queue/worktree/dispatch/review/land ports
      control_store.py            # journal and materialized runtime view
      telemetry.py                # OTel emission and ledger reads
config/system-of-work/
  schemas/                        # versioned stage-result JSON Schemas
  prompts/                        # versioned semantic-stage prompt templates
```

The domain modules contain no subprocess, filesystem, clock, random-ID, GitHub, or model calls.
The application layer receives those capabilities as ports. `tools/orchestrate.py` performs CLI
translation only; ADR-0049's existing “non-trivial logic lives in Python” rule remains satisfied
without creating another shell workflow.

### Consistency and concurrency

- **One scheduling writer:** one controller process, protected by `flock`; concurrent Work Runs
  write only their own dispatch/evidence partitions and never schedule other work.
- **One external mutation per Control Action:** no action pretends GitHub plus local state is one
  transaction.
- **Intent marker before inference:** each published artefact carries its stable logical key. On
  restart, the executor queries for that key before retrying rather than trusting a local
  `applied` flag.
- **Plan/apply/confirm:** the transition journal records the planned action, the adapter result,
  and the subsequently confirmed Control Fact as separate records.
- **Reconcile after mutation:** after a state-changing external action, collect fresh Control
  Facts before applying another action whose preconditions could have changed. Initiative
  publication progresses one missing idempotent step at a time.
- **Serial tracker writes:** execute GitHub mutations serially and respect rate-limit/refusal
  responses; parallelism belongs in eligible Work Runs.
- **Launch-time freshness:** immediately before `StartWorkRun`, reread the Work Item's open,
  dependency, and active-run facts. A plan derived from an earlier poll is not launch authority.
- **No time lease in the MVP:** active-run exclusion derives from the dispatch record, process,
  and worktree. Recovery classifies an interrupted run; elapsed time alone never steals it.
- **Detached execution:** `StartWorkRun` records the dispatch ID and returns. No controller tick
  waits for a model session; later ticks reconcile its result.

### Authority matrix

| Decision | Authority |
|---|---|
| Choose or change Desired Outcome | Product Curator |
| Derive Product Specification, Design Disposition, Implementation Design, and Work Graph | Initiative Planning agent, constrained by schema and deterministic publication invariants |
| Select eligible Work Item and dispatch within WIP | Deterministic Coordination Policy |
| Derive a Work Item's local implementation plan and candidate | Work Delivery agent |
| Clear an exact candidate | Existing post-#317 review/adjudication and deterministic gates |
| Classify Initiative findings | Outcome Assurance agent, schema-constrained and read-only |
| Route a classified finding | Deterministic Outcome Assurance Policy |
| Propose one allowlisted Process Change | Retrospective agent |
| Recommend retain/amend/revert from a frozen follow-up window | Process-improvement evaluation agent |
| Apply, activate, and route the disposition of a Process Revision | Ordinary delivery plus deterministic Improvement Policy, while no product Initiative is active in the MVP |
| Change credentials, permissions, evaluator authority, landing authority, or the allowlist | Outside autonomous MVP authority |

## 6. Primitive Initiative Audit and improvement

The Initiative Audit collector deterministically assembles the exact Desired Outcome, plan
revision, Product Specification, Design Disposition, Implementation Design, Work Graph, close
evidence, landed SHAs, and integrated tree. A fresh read-only agent returns a Stage Verdict over
that frozen subject. A `pass` belongs only to that plan revision and integrated SHA.

Validated findings take different routes:

| Finding kind | Route |
|---|---|
| **Delivery Gap** | Publish an idempotent Work Item using the stable finding ID and return to delivery. |
| **Planning Gap** | Reopen Initiative Planning and publish a new plan revision before dispatching more delivery work. |
| **Product Question** | Enter `needs_product_input` and ask the Product Curator exactly the unresolved product choice. |
| **`inconclusive` / `infra_unavailable`** | Publish no gap and take no semantic transition; preserve the typed non-result. |

The auditor proposes findings but cannot mutate the Initiative or Work Graph. This preserves the
same propose/validate/apply separation used by planning.

The improvement trigger is deterministic: initially after every five completed production Work
Items, matching the current retro cadence, but evaluated only when a product Initiative reaches an
audit terminal. Process Work Items do not increment the cursor. The evidence collector freezes the
ledger window and computes ordinary counts. A retro agent may propose at most one allowlisted
Process Change.

The controller owns one standing internal Improvement Initiative. When a cycle is due, it admits
no next product Initiative until the cycle has either produced no proposal or recorded the active
Process Revision. An allowed proposal becomes a child Work Item of that standing Initiative and
passes through ordinary Work Delivery. A proposal outside the allowlist is recorded as
`outside_autonomous_authority` and does not become a Product Question. Landing activates the exact
Process Revision in the MVP; an improvement-evaluation stage reads the next eligible frozen window
and recommends `retain`, `amend`, `revert`, or `inconclusive`. The deterministic policy records
`retain`/`inconclusive` or publishes an ordinary amend/revert Work Item. The before/after evidence
is confounded, but it closes the loop without pretending to be a causal experiment platform.

Use the current ledger as the evidence authority. If MLflow is included early, run it locally
with SQLite and local artifacts, and treat export as best-effort. Project traces and one run per
improvement window are enough initially. MLflow officially supports a single-host SQLite/local
artifact setup and later migration to PostgreSQL/object storage.
([MLflow self-hosting](https://mlflow.org/docs/latest/self-hosting/index.html))
Do not use MLflow aliases, runs, feedback, or review queues to control dispatch, activation, or
rollback.

The current OpenTelemetry Collector can remain the fan-out point: Collector pipelines explicitly
support multiple named receivers, processors, and exporters.
([OpenTelemetry Collector configuration](https://opentelemetry.io/docs/collector/configuration/))

## 7. Test the controller as a protocol

The most valuable implementation technique is a ports-and-adapters test harness:

- an in-memory/fake GitHub adapter;
- a fake agent runner returning recorded valid, invalid, blocked, and missing results;
- a fake clock and deterministic IDs;
- a temporary journal/state directory;
- fault injection immediately before and after every external Control Action; and
- replay of the same Control Fact and transition-record history more than once.

Test invariants rather than examples alone: active Work Runs never exceed WIP, no blocked Work
Item dispatches, one Work Item has at most one live Work Run, repeated reconciliation does not
duplicate a remote artefact, an invalid Stage Verdict causes no mutation, and restart converges
to the same derived state.

The repository already depends on Hypothesis. Its rule-based state machines generate sequences
of actions and check invariants after transitions, making it a strong fit for Work Run start,
crash, retry, close, reopen, and dependency-order scenarios.
([Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html))

Keep LLMs out of the unit suite. Use recorded stage results for deterministic tests, then one
small live acceptance demonstration containing a planted product omission and a planted process
defect.

## Defer-until trigger table

| Candidate | Defer until |
|---|---|
| SQLite controller store | JSONL recovery/querying becomes materially awkward or there is more than one writer |
| DBOS | durable sleeps, queued workflows, or cross-process resumption are recurring problems |
| Temporal | multi-repository/multi-host scale justifies a service and replay-version discipline |
| GitHub webhooks/FastAPI | polling latency or API load is measured as a problem |
| PostgreSQL/Redis/broker | multiple coordinator instances or hosts are actually required |
| Symphony runtime | replacing, rather than extending, the existing queue/dispatch/worktree control plane becomes desirable |
| MLflow evaluation datasets/judges | a repeatable evaluation corpus and calibrated semantic measures exist |
| process bundles, signed attestations, OPA, protected evaluator | autonomous process changes cross the initial low-risk allowlist |
| canary/OpenFeature-shaped deployment | enough comparable concurrent work exists to support an exposure split |
| Kubernetes/Argo | the workload is deployed on Kubernetes for independent reasons |

## Smallest useful build sequence

1. Domain types, pure reconciliation kernel, Control Actions, schemas, fake ports, and
   `--dry-run`.
2. Product Curation/Initiative Planning slice: Desired Outcome through a validated plan package
   to idempotently published Initiative and Work Graph.
3. Coordination/Delivery slice: existing queue/worktree/dispatch/review/land composition,
   launch-time freshness, and restart reconciliation.
4. Outcome Assurance slice: exact Initiative Audit subject plus distinct Delivery Gap, Planning
   Gap, Product Question, and typed-non-result routes.
5. Process Improvement slice: boundary-evaluated five-production-Work-Item trigger, standing
   Improvement Initiative, frozen ledger window, one allowlisted Process Change, exact Process
   Revision, and retain/amend/revert/inconclusive disposition.
6. User service operation and optional non-blocking MLflow projection.

This sequence represents every control loop before hardening any one of them. The later target
architecture remains a roadmap driven by observed failures rather than an entry requirement.

## Published MVP ticket graph

The MVP specification is [#377](https://github.com/andrewesweet/arma-cti/issues/377), a native
child of target-state specification [#376](https://github.com/andrewesweet/arma-cti/issues/376).
Its implementation slices are native sub-issues with native dependency edges:

| Order | Ticket | Blocked by |
|---|---|---|
| 1 | [#378 — one-shot reconciliation and recoverable journal](https://github.com/andrewesweet/arma-cti/issues/378) | — |
| 2 | [#379 — Desired Outcome to published Plan Revision and Work Graph](https://github.com/andrewesweet/arma-cti/issues/379) | #378 |
| 3 | [#380 — deterministic eligible Work Item dispatch within WIP](https://github.com/andrewesweet/arma-cti/issues/380) | #379 |
| 4 | [#381 — observe exact-candidate delivery completion](https://github.com/andrewesweet/arma-cti/issues/381) | #380 |
| 5 | [#382 — Initiative Audit happy path](https://github.com/andrewesweet/arma-cti/issues/382) | #381 |
| 6 | [#383 — distinct audit-gap routes](https://github.com/andrewesweet/arma-cti/issues/383) | #382 |
| 7 | [#384 — canonical evidence and optional MLflow projection](https://github.com/andrewesweet/arma-cti/issues/384) | #381 |
| 8 | [#385 — bounded retrospective proposal](https://github.com/andrewesweet/arma-cti/issues/385) | #383, #384 |
| 9 | [#386 — allowlisted Process Revision delivery and activation](https://github.com/andrewesweet/arma-cti/issues/386) | #385 |
| 10 | [#387 — retain/amend/revert/inconclusive evaluation](https://github.com/andrewesweet/arma-cti/issues/387) | #386 |
| 11 | [#388 — unattended operation and end-to-end demonstration](https://github.com/andrewesweet/arma-cti/issues/388) | #383, #387 |

The initial frontier is #378. After #381, #382 and #384 can progress independently; the graph
rejoins at #385. The final operations slice is deliberately blocked by both complete product-gap
routing and the complete primitive improvement loop.
