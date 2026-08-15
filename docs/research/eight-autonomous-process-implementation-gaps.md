# Eight implementation gaps on the path to product-curator-only development

**Research date:** 2026-08-14  
**Scope:** the eight gaps identified after comparing the desired process with the
post-#317 `arma-cti` system of work  
**Method:** each gap was investigated in the stated order against the current repository
and primary sources: official specifications, documentation, repositories, and papers

**Status:** Target-state research informing
[specification #376](https://github.com/andrewesweet/arma-cti/issues/376). Its integrated
build sequence deliberately exceeds the walking skeleton; the MVP scope and delivery order are
governed by [#377](https://github.com/andrewesweet/arma-cti/issues/377) and #378–#388.

## Executive conclusion

No single product should be adopted to fill these gaps. The strongest architecture is a
small set of project-owned domain controllers built on standard, replaceable primitives:

```text
human product outcome
       │
       ▼
initiative compiler ─────── writes ──────▶ initiative manifest
       │                                          │
       ▼                                          ▼
outer/inner delivery loops ◀──────────── initiative audit
       │
       └── canonical events ──▶ improvement controller ──▶ evaluator
                                      │                       │
                                      └── rollout/deployer ◀──┘
                                                │
                                     exact process release
                                                │
                                      constitutional kernel
```

The recommended decisions are:

| # | Gap | Recommended implementation direction |
|---|---|---|
| 1 | Durable initiative compiler | Build a repository-owned state machine; borrow GitHub Spec Kit's artifact stages and Gas City's formula semantics. Start file-backed; use the same durable-workflow substrate as gap 4 once proven. |
| 2 | Initiative manifest and traceability | Build a small JSON/YAML manifest validated with JSON Schema. Preserve Markdown as the authored experience. Borrow StrictDoc/OpenFastTrace coverage semantics and W3C PROV vocabulary, but do not adopt their storage model as authoritative. |
| 3 | Initiative acceptance/architecture audit | Build a project-owned composite runner: deterministic traceability and acceptance adapters plus independent semantic audit. Borrow Spec Kit `analyze`/`converge`; optionally use CUE for rich structural constraints. |
| 4 | Improvement controller | Build it in Python on DBOS durable workflows, initially using SQLite and later PostgreSQL. MLflow remains its experiment/evaluation projection, not its state machine or authority. |
| 5 | Protected evaluator and holdout | Build a separate evaluator service and identity. Use OS/container isolation, a store unavailable to candidate workers, digest-pinned datasets, and signed in-toto-style verdicts. MLflow workspaces are not the security boundary. |
| 6 | Shadow/canary and activation | Build a project-specific policy deployer behind an OpenFeature-shaped evaluation API. Assign once, deterministically and stickily, at claim time; record the result. Borrow Argo Rollouts' outcome semantics; do not deploy Argo for this non-Kubernetes problem. |
| 7 | Process-manifest digest and bundle | Build a canonical `process-release` manifest using OCI-style descriptors, SHA-256 content addressing, and an in-toto/DSSE attestation. Git remains authoring history; the release digest identifies effective behavior. |
| 8 | Constitutional kernel and identities | Build a deliberately small authorization/promotion service using distinct OS workload identities, OPA policy, signed bundles, and append-only decision evidence. Adopt SPIFFE/SPIRE only when the control plane spans hosts. |

This ordering is also the dependency order. Items 1–3 produce and judge product work;
items 4–6 improve and release the process; items 7–8 make the released process and its
authority trustworthy.

## Current foundation and constraints

The project already has more delivery-control machinery than most candidate platforms:

- `just queue`, dispatch, worktree, watcher, recovery, breaker, admission, ledger, and
  landing surfaces provide typed operational ports;
- [ADR-0071](../adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md)
  defines seat/profile resolution, author-distinct exact-candidate review, bounded
  adjudication, and a reporting-only quality observatory;
- [the issue-tracker contract](../agents/issue-tracker.md) already defines decision
  tickets, dependency-ordered implementation issues, criterion-by-criterion close
  evidence, and GitHub-native dependency edges;
- [the telemetry ledger](../telemetry-ledger.md) retains project-specific dispatch,
  outcome, cost, gate, and landing meanings which a generic experiment system cannot
  infer; and
- [the existing continuous-improvement study](autonomous-system-of-work-continuous-improvement.md)
  established the separation between managed delivery, an improvement controller, and
  a human-ratified constitutional envelope.

The designs below therefore integrate with these ports. They do not create another issue
scheduler, review loop, failure taxonomy, or canonical telemetry writer.

---

## 1. Durable initiative compiler around the existing skill sequence

### The required contract

The compiler turns one human-curated product outcome into a reviewed, dispatchable
initiative without relying on one conversation's context or memory. Its public state
machine should be:

```text
intake
  → outcome_interview
  → spec_draft
  → spec_review
  → design_needed?
      ├─ no ───────────────────────┐
      └─ yes → architecture → architecture_review
                                    │
  ┌─────────────────────────────────┘
  → ticket_graph_draft
  → cross_artifact_readiness
  → published
```

Every transition must be idempotent and resumable. Each stage consumes exact artifact
versions and emits a typed result:

- `pass` with output artifact descriptors;
- `revise(stage, findings)` returning to the stage that owns the defect;
- `blocked(reason, required_authority)`;
- `not_applicable(reason)`, for architecture on a genuinely trivial initiative; or
- `abandoned` by an explicit product-curator decision.

The compiler owns stage order, artifact identity, review independence, resumption, and
publication. It does **not** own implementation planning or execution. The initiative
specification remains product-facing **what/why**; the architecture records the
cross-ticket implementation shape; each inner runner derives its local **how**.

A durable run record needs at least:

```yaml
initiative_id: init-...
desired_outcome_ref: ...
state: spec_review
stage_attempt: 2
input_digests: {...}
output_digests: {...}
review_dispatch_ids: [...]
open_findings: [...]
decision_log: [...]
manifest_ref: ...
```

Artifacts, not the agent session, are the handoff. A rerun recomputes which stage is
complete from artifacts and signed/typed verdicts; a mutable `status: done` flag alone
is insufficient.

### Concrete candidates

#### GitHub Spec Kit: best artifact vocabulary, not a durable controller

Spec Kit's official flow is now
`constitution → specify → clarify → plan → checklist → tasks → analyze → implement → converge`.
It explicitly locates what/why in `specify`, technical design in `plan`, dependency-ordered
work in `tasks`, read-only cross-artifact checking in `analyze`, and post-implementation
gap detection in `converge`. Its large-feature guidance adds a durable roadmap with
immutable IDs and bidirectional links to sub-specs.
([agentic SDD reference](https://github.github.com/spec-kit/reference/agentic-sdd.html),
[spec-of-specs](https://github.github.com/spec-kit/concepts/spec-of-specs.html))

That is remarkably close to the desired artifact sequence. But Spec Kit's core is an
agent harness and collection of commands, not an authoritative crash-recovering state
machine. The commands are intended to be driven step by step or through an automated
workflow; their state is primarily the files they produce. It also includes work-item
implementation in the same conceptual pipeline, while this architecture deliberately
hands off to the outer coordinator after tickets are published.

Use its templates and stage ownership as source material. Do not make `.specify` the
new system of record or import its whole implementation loop.

#### Gas City formulas: best declarative workflow candidate, but overlapping control plane

Gas City describes a formula as the durable method an orchestrator runs over agents;
beads are tracked units that survive crashes; independent legs run in parallel and
dependent ones wait. Its packs include `build-basic` and BMAD-derived flows which go
from requirements/PRD through plan or architecture, decomposition, readiness, build,
review, and gap filling.
([Gas City overview](https://github.com/gastownhall/gascity/blob/main/docs/index.mdx),
[official packs](https://github.com/gastownhall/gascity-packs))

This is the closest off-the-shelf declarative representation. The problem is the seam:
adopting Gas City's whole run/agent/bead control plane would duplicate the planned
Symphony-like coordinator and much of the existing dispatch/worktree/review surface.
Formula semantics are useful; its execution authority is too broad for this repository.

#### Temporal: strongest general durability, highest operating and evolution cost

Temporal persists a complete workflow event history and replays code after failure so
execution resumes from the previous state. Signals, Queries, and Updates provide
asynchronous writes, reads, and tracked synchronous writes. Pinned worker deployments
can keep a long-running workflow on one code version; auto-upgrade workflows require
replay-safe patching. Continue-As-New checkpoints state into a fresh execution and can
support effectively permanent entity workflows.
([event history](https://docs.temporal.io/encyclopedia/event-history),
[message passing](https://docs.temporal.io/encyclopedia/workflow-message-passing),
[worker versioning](https://docs.temporal.io/worker-versioning),
[Continue-As-New](https://docs.temporal.io/workflow-execution/continue-as-new))

Temporal would solve durability thoroughly, but a self-improving workflow changes its
own orchestration code frequently. Temporal's deterministic replay and worker-version
compatibility become a permanent engineering obligation, while operating the service is
substantial for one local project.

#### DBOS: lighter durable execution, considered with gap 4

DBOS adds durable Python workflows and steps to an existing application, checkpoints
completed step results, uses workflow IDs as idempotency keys, offers durable queues,
messages, timeouts, scheduling, resume, cancellation, and forking, and can start with a
local SQLite database. PostgreSQL is recommended once execution is distributed.
([workflow contract](https://docs.dbos.dev/python/tutorials/workflow-tutorial),
[incremental integration](https://docs.dbos.dev/python/integrating-dbos),
[workflow management](https://docs.dbos.dev/python/tutorials/workflow-management))

It matches the existing Python toolchain and can be introduced around a single workflow
without replacing the surrounding application. Its smaller ecosystem and newer codebase
are risks, and durable steps still require careful idempotency around GitHub writes.

### Recommendation

**Build a repository-owned initiative compiler and borrow Spec Kit's artifact semantics.**
Define its stages and artifacts now as a pure state reducer over the initiative manifest.
Initially, retain state in Git plus an append-only run journal so the contract can be
exercised before choosing a workflow engine. When gap 4 introduces DBOS, host the
compiler as a separate DBOS workflow using the same durability substrate.

Do not adopt Gas City as another control plane. Its formula/packs remain excellent
worked examples for stage descriptions, composition, readiness, and gap filling. Do not
start with Temporal unless multiple repositories, many simultaneous initiatives, or
multi-host high availability make the service and replay-version discipline worthwhile.

**Dependencies:** gap 2 is required before stage outputs can be authoritative; gap 3 is
the readiness transition; gap 7 later pins the compiler version that produced a run.

---

## 2. Initiative manifest and traceability model

### The required contract

The manifest is the machine-readable spine, not a replacement for readable product and
architecture documents. It must answer both forward and backward questions:

- Which desired outcome and product requirement does this ticket serve?
- Which architecture decision constrains it?
- Which acceptance case proves the requirement?
- Which landed SHA and evidence satisfied that case?
- What is unimplemented, untested, orphaned, contradicted, or superseded?

The graph needs stable typed nodes and edges. A minimum model is:

```text
Node kinds
  outcome, requirement, constraint, architecture_decision,
  work_item, acceptance_case, evidence, release

Edge kinds
  refines, depends_on, constrained_by, allocated_to,
  verified_by, evidenced_by, supersedes
```

Every node has an immutable initiative-scoped ID, a content/ref descriptor, lifecycle
state, and provenance. Edge direction and cardinality are schema-defined. The core
invariants include:

- every in-scope requirement is allocated to at least one work item or explicitly
  discharged without implementation;
- every requirement has at least one acceptance case;
- every architecture decision constrains at least one relevant work item, or is marked
  contextual;
- every work item traces back to a requirement or an explicitly classified enabling
  constraint;
- every completed acceptance case carries evidence tied to an exact release/SHA;
- dependency edges are acyclic where they govern dispatch; and
- supersession never destroys historical identity.

The manifest should reference documents and tracker objects; it should not copy their
full prose. A reference carries URI/path, immutable revision or digest, and optional
anchor. Mutable GitHub issue numbers are identity, while body snapshots/digests establish
what version the compiler or auditor actually read.

### Concrete candidates

#### StrictDoc: strongest authoring and graph UI, intrusive canonical format

StrictDoc stores human-readable text, builds a requirements/document graph, supports
deep traceability and traceability matrices, and can connect requirements to source
files or exact line ranges. It exports HTML, PDF, JSON, Excel, and ReqIF and includes a
web editor.
([StrictDoc traceability guide](https://strictdoc.readthedocs.io/en/stable/stable/docs/strictdoc_01_user_guide-TRACE.html))

It could replace much of the desired viewer and reporting surface. But authoritative
`.sdoc` nodes would impose a second document language on a project whose product intent,
ADRs, acceptance specifications, and tracker conventions already live in Markdown,
GitHub, and code. Its source-line traceability is also lower-level than the initiative
contract needs.

Treat StrictDoc as an optional generated view or future editor, not the canonical store.

#### OpenFastTrace: focused coverage engine, Java/GPL and marker model

OpenFastTrace scans requirement markers across artifacts and reports whether planned
requirements are implemented, along with obsolete/uncovered product elements. It can
run from the CLI or build tooling and generates HTML tracing reports.
([official repository](https://github.com/itsallcode/openfasttrace))

Its bidirectional coverage questions are exactly right, and it is simpler than a full
requirements-management product. The Java runtime, GPL-3.0 licensing implications for
integration, and marker-centric input model are poor fits for a Python project-owned
control surface. Its semantics are worth copying in tests: missing coverage, orphan
coverage, duplicate identity, and invalid direction.

#### W3C PROV: useful vocabulary, excessive serialization for the primary format

W3C PROV models entities, activities, and agents and relates generation, use,
derivation, association, and attribution. Its explicit purpose is to represent
responsibility and derivation so quality, reliability, or trustworthiness can be
assessed.
([PROV-DM recommendation](https://www.w3.org/TR/prov-dm/))

This is a strong semantic foundation for answering “which compiler/reviewer activity
generated this artifact from which inputs?” It does not define product requirements,
architecture, issue dependencies, or acceptance coverage. A full RDF/PROV-O graph would
add complexity without resolving those project-specific meanings.

Use a small PROV-compatible provenance subobject—entity digests, activity/run ID, agent
identity, generation time—rather than adopting RDF as the initiative file format.

#### JSON Schema 2020-12: appropriate validation foundation

JSON Schema 2020-12 provides standard structural validation, reusable schemas, `$id`,
`$ref`, and location-independent `$anchor` identifiers.
([official specification index](https://json-schema.org/specification),
[core specification](https://github.com/json-schema-org/json-schema-spec/blob/main/specs/jsonschema-core.md))

It cannot enforce all graph invariants, but it cleanly owns syntax, enums, required
fields, and local shapes. A second graph-validation pass can enforce reachability,
cardinality, cycles, and repository existence.

### Recommendation

**Build a small project-owned `initiative.schema.json` and manifest.** Author it as YAML
if that materially improves review, but parse to the JSON data model and validate
against JSON Schema 2020-12. Keep specs, architecture, and acceptance documents in their
native Markdown/code forms and reference them by digest and stable anchor.

Use immutable IDs such as `OUT-001`, `REQ-004`, `AD-002`, and `ACC-007`; do not use
array position or headings as identity. Map GitHub issues into `work_item` nodes and
native issue dependency edges into `depends_on`. Export the graph to DOT/HTML and, if a
richer UI becomes valuable, generate StrictDoc/OpenFastTrace-compatible material rather
than switching canonical formats.

The first implementation should provide three commands behind the repository command
surface:

```text
initiative validate     schema + graph invariants
initiative coverage     missing/orphan/superseded matrix
initiative snapshot     resolve refs and freeze exact input digests
```

**Dependencies:** item 1 writes the manifest; item 3 reads it; items 4–7 reuse its
descriptor and provenance conventions.

---

## 3. Initiative acceptance and architecture audit runner

### The required contract

This runner decides whether the integrated initiative has converged on the desired
outcome and the agreed cross-item design. It must not collapse four different questions
into one agent opinion:

1. **Traceability completeness:** is every in-scope requirement allocated and verified?
2. **Behavioural acceptance:** did each acceptance case produce acceptable evidence on
   an exact integrated release?
3. **Architecture conformance:** does the integrated implementation respect the initial
   design plus its explicit superseding decisions?
4. **Semantic gap search:** is there behaviour required by the product intent that the
   manifest/tests/tickets failed to encode?

The runner consumes an immutable initiative snapshot and exact candidate release. Its
output is a typed `InitiativeAuditVerdict`:

```yaml
initiative_id: ...
manifest_digest: sha256:...
candidate_release: <git sha/process release>
auditor_identity: ...
checks:
  traceability: pass|fail|inconclusive
  acceptance: pass|fail|inconclusive|infra_unavailable
  architecture: pass|fail|inconclusive
  semantic_gap: pass|fail|inconclusive
findings:
  - id: ...
    source_node_ids: [...]
    severity: ...
    disposition: gap_ticket|architecture_decision|required_evidence|dismissed
evidence: [...]
```

`inconclusive` must not become a pass. A failed audit creates gap work through the
normal ticket graph; it never edits the product specification or acceptance oracle to
make the implementation pass. Architecture conflict returns to an architecture decision
stage and then updates affected work, rather than being patched independently by one
ticket.

The auditor must be author-distinct from implementation and review the integrated SHA,
not a set of issue-close summaries.

### Concrete candidates

#### Spec Kit `analyze` and `converge`: closest semantic behavior

Spec Kit's `analyze` performs read-only cross-artifact consistency analysis across
specification, plan, and tasks and sends each problem back to the artifact-owning stage.
Its `converge` assesses the codebase against spec, plan, and tasks, leaves a converged
task list byte-for-byte unchanged, or appends gap tasks for another implement/converge
cycle.
([official agentic SDD reference](https://github.github.com/spec-kit/reference/agentic-sdd.html))

This is the closest direct prior art for the gap-filling loop. Its weakness is that the
checks are primarily agent-prompt semantics over conventional Markdown, without the
typed manifest, exact evidence joins, independent reviewer identity, or acceptance
tiers this project requires.

Reuse the prompts/checklists as one semantic auditor implementation, wrapped in the
typed contract above.

#### CUE: strong structural and cross-field validation

CUE unifies data with constraints and can validate, query, combine, and export JSON or
YAML. Its constraints can express relationships beyond simple type checking, and its
unification model rejects conflicting stakeholder constraints instead of allowing
last-writer override.
([CUE documentation](https://cuelang.org/docs/),
[validation model](https://cuelang.org/docs/concept/how-cue-enables-validation/),
[configuration constraints](https://cuelang.org/docs/concept/how-cue-enables-configuration/))

CUE is attractive if the manifest accumulates many conditional/cardinality rules. It
adds a language and Go binary to a project that can implement the initial graph checks
clearly in Python. It also cannot judge whether product meaning is absent or whether an
architectural decision is semantically violated.

Use it only after JSON Schema plus explicit graph code becomes cumbersome; do not adopt
it merely to validate required fields.

#### OPA: correct for policy decisions, not the whole audit

OPA accepts arbitrary structured input and evaluates declarative Rego policies,
separating policy decision from enforcement. It includes policy tests.
([OPA overview](https://www.openpolicyagent.org/docs),
[policy testing](https://www.openpolicyagent.org/docs/policy-testing))

OPA is valuable for constitutional authorization in item 8, where the question is
“may this identity perform this transition?” Here, most checks are graph coverage,
evidence adapter execution, or semantic review. Encoding all audit logic in Rego would
obscure rather than simplify it.

### Recommendation

**Build a project-owned composite audit runner.** It should orchestrate three kinds of
adapter without confusing their authority:

1. deterministic manifest/graph rules in Python;
2. registered acceptance adapters that return the project's existing typed verdicts
   and evidence references; and
3. an author-distinct semantic audit seat, using a versioned rubric derived initially
   from Spec Kit `analyze`/`converge` and the initiative architecture.

Run two semantic lenses independently—product-gap and architecture-conformance—and use
#317's adjudication mechanics if they disagree. Gap tickets are deterministic products
of accepted findings, carry source node IDs and acceptance criteria, and re-enter the
outer loop. The audit reruns until `pass` or an explicit product-authority decision
supersedes scope.

The future reserved `just accept <spec-id>` / `accept-all` names can be the acceptance
adapter layer; the initiative audit is a higher-level composition over them, not their
replacement.

**Dependencies:** item 2 is mandatory. Item 7 later binds the runner/rubric version, and
item 8 prevents the candidate from altering its own audit authority.

---

## 4. Improvement controller that freezes evidence and manages experiments

### The required contract

The controller is a slower durable state machine around delivery. It owns experiment
protocol, not scientific judgment or delivery implementation:

```text
triggered
 → evidence_frozen
 → diagnosed
 → proposal_reviewed
 → protocol_preregistered
 → candidate_built
 → replayed
 → shadowed
 → canarying
 → decided
 → promoted | rolled_back | rejected | inconclusive
 → post_promotion_monitoring
```

Before any candidate sees an evaluation, the controller freezes:

- evidence-window bounds and source digests;
- hypothesis and changed mechanism;
- baseline and candidate process-release digests;
- eligibility and assignment unit;
- dataset/evaluator digests;
- one primary measure, guardrail vector, hard invariants;
- sample/time bounds and stopping rule; and
- pass, fail, inconclusive, rollback, and authority-escalation semantics.

The protocol itself becomes immutable after preregistration. Corrections create a new
protocol version and invalidate—not silently reinterpret—results from the previous one.
External effects are idempotent and correlation-keyed: tracker issue creation,
dispatch, MLflow run creation, assignment, and policy activation must survive a crash
without duplication.

MLflow receives runs, datasets, traces, scores, and artifacts. The controller retains
the authoritative transition journal and reconciles every experiment result against
canonical dispatch/gate/git evidence before deciding.

### Concrete candidates

#### MLflow: experiment workbench, explicitly not the controller

MLflow Tracking persists experiments, runs, parameters, metrics, tags, datasets, and
artifacts and provides search/comparison APIs and UI. Its REST API also permits updating
and deleting metadata, runs, and experiments.
([Tracking architecture](https://mlflow.org/docs/latest/ml/tracking),
[REST API](https://mlflow.org/docs/latest/api_reference/rest-api.html))

That makes it the correct laboratory and a poor transition authority. It does not
preregister protocols, assign issues, protect holdouts, or implement policy-aware
shadow/canary/promotion. Its mutable records cannot be the sole experiment verdict.
The detailed split remains the one in
[the MLflow role study](mlflow-role-in-system-of-work-improvement.md).

#### Temporal: strongest mature durable workflow service

Temporal's durable event history, tracked Updates, Queries, timers, schedules,
versioned workers, and long-lived entity-workflow pattern fit the controller exactly.
([Temporal documentation](https://docs.temporal.io/))

It is the safest choice at organization/multi-repository scale. For this project it
would add a separate service and substantial operational/versioning machinery before
the domain protocol itself has been exercised. More importantly, its replay-safe code
evolution is a sharp edge for a controller whose subject is changing workflow policy.

#### DBOS: best initial implementation substrate

DBOS is an MIT-licensed Python library which checkpoints workflow/step state, resumes
after interruption, treats workflow IDs as idempotency keys, provides durable queues,
notifications, schedules, timeouts, cancellation, resume, and forking, and can use
SQLite before moving to PostgreSQL.
([official repository](https://github.com/dbos-inc/dbos-transact-py),
[database choices](https://docs.dbos.dev/python/tutorials/database-connection),
[management API](https://docs.dbos.dev/python/tutorials/workflow-management),
[workflow communication](https://docs.dbos.dev/python/tutorials/workflow-communication))

It embeds into the current Python control surface instead of asking the project to run
another platform. Forking from a chosen step is especially useful when evaluator
infrastructure, rather than the candidate, invalidated a trial. Risks are its relative
youth, the need to version workflow code carefully, and the distinction between a
checkpointed step and an exactly-once external side effect. Every GitHub/dispatch/
activation call still needs a stable idempotency key and read-before-write reconciliation.

#### Plain SQLite/event reducer: smallest dependency, most bespoke durability

A hand-built append-only transition table and pure reducer would be easy to inspect and
could reuse existing project patterns. It would also require implementing timers,
leases, recovery, notification, cancellation, fork/resume, concurrency, and operational
query surfaces—the generic mechanics DBOS already provides.

### Recommendation

**Build the improvement controller in Python on DBOS, with project-owned state and
transition types.** Begin single-process with SQLite. Move DBOS and MLflow to separate
PostgreSQL databases when simultaneous controllers or multi-host workers become real;
never share their schema or transactional authority.

Each experiment is one durable workflow identified by the protocol digest. Each phase
is a separately checkpointed step. MLflow run IDs and trace IDs are outputs/projected
references. The controller emits a canonical `ExperimentVerdict`, reconciled against
the local evidence journal and later signed by the evaluator/promotion path.

Do not use DBOS Conductor as constitutional authority; it is optional operations UI.
Do not let a workflow `fork` revise a preregistered protocol in place—forking creates a
new protocol identity.

**Dependencies:** item 5 supplies trustworthy evaluation; item 6 supplies assignment
and activation; item 7 gives baseline/candidate identity; item 8 authorizes transitions.

---

## 5. Protected evaluator and locked holdout service

### The required contract

The evaluator exists to prevent a candidate from improving its score by reading,
rewriting, or impersonating the thing that judges it. Its threat model must include a
candidate process that intentionally explores every file, environment variable, socket,
credential, trace, and API available to it.

Required properties:

- candidate authors cannot list, read, modify, or delete locked cases, scorer code,
  scorer prompts, answer keys, assignment secrets, or signing keys;
- evaluator identity and credentials are not inherited by candidate or ordinary
  delivery workers;
- each dataset snapshot, evaluator, rubric, and scorer has an immutable digest;
- the evaluator receives an exact candidate process release and a preregistered
  protocol, and cannot substitute either silently;
- deterministic checks and LLM judges report separately;
- an LLM judge records model/profile/prompt version, rationale, confidence, and source
  type; it is never mislabelled human;
- the result distinguishes `pass`, `fail`, `inconclusive`, evaluator error, and
  infrastructure unavailability; and
- a verifier can validate the verdict without access to mutable MLflow state.

Protection and immutability are distinct. Encryption/access control prevents
disclosure; WORM/content digests prevent replacement; sandboxing prevents the candidate
from reaching the evaluator's authority.

### Concrete candidates

#### MLflow workspaces/RBAC: useful inner control, explicitly not hard isolation

MLflow 3.13+ has role-based permissions over experiments, prompts, scorers, and other
resources, with workspace-scoped roles. But the documentation says workspaces are a
logical authorization layer, **not a hard isolation boundary**, and recommends separate
deployments for strict data-plane isolation. The permission resolver also has important
defaults: default permission is `READ` unless configured otherwise, roles combine by
maximum privilege, and there is no explicit-deny override.
([RBAC](https://mlflow.org/docs/latest/self-hosting/security/role-based-access-control/),
[workspace isolation warning](https://mlflow.org/docs/latest/self-hosting/workspaces/))

Use a separate evaluator MLflow deployment or keep protected cases out of MLflow
entirely. The ordinary trace/experiment workspace may contain public/regression datasets
and derived results; it must not be the sole holdout vault.

#### gVisor: appropriate candidate-workload isolation

gVisor provides an OCI runtime which interposes a userspace application kernel between
the workload and host kernel. Its own documentation stresses that ordinary containers
are not a sandbox for untrusted code, while gVisor reduces the host-kernel surface. It
also states the boundary correctly: the workload can access everything intentionally
mounted or configured into its sandbox, so isolation cannot repair a leaked holdout
mount or credential.
([official repository](https://github.com/google/gvisor),
[security architecture](https://github.com/google/gvisor/blob/master/g3doc/architecture_guide/intro_to_gvisor.md))

Run candidate and evaluation-agent code in distinct sandboxes, with no holdout mounts,
no host Docker socket, controlled egress, and separate scratch roots. The evaluator
service remains outside the candidate sandbox and sends only the case input the
protocol permits.

#### S3-compatible WORM/object lock: strong immutability, optional infrastructure

S3 Object Lock stores versioned objects under a write-once-read-many model and can
prevent overwrite or deletion for a retention period or legal hold.
([AWS S3 Object Lock documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html))

This is a clean answer for frozen datasets and verdict artifacts if an object store is
already acceptable. It does not prevent a broadly credentialed candidate from reading
the cases. IAM/credential separation remains the security boundary. For one local
project, a service-owned directory plus append-only snapshots and offline backup may be
proportionate initially; WORM storage becomes valuable once autonomous promotion is
trusted for long periods.

#### in-toto: strong verdict provenance, not a holdout store

in-toto layouts name authorized functionaries, expected steps, artifact rules, and
signature thresholds. Functionaries produce signed link metadata over materials and
products; verification checks signatures, commands, artifact flow, and inspections.
([official repository and model](https://github.com/in-toto/in-toto),
[specification](https://github.com/in-toto/docs/blob/master/in-toto-spec.md))

The attestation framework's Statement binds a predicate to immutable subjects by
digest, while DSSE supports multiple signatures over typed payloads.
([Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md),
[envelope specification](https://github.com/in-toto/attestation/blob/main/spec/v1/envelope.md))

Use this model for `EvaluationVerdict`: subjects are the candidate process release,
dataset snapshot, evaluator, and protocol; the predicate contains measures, integrity
checks, and result. It does not store or conceal cases.

### Recommendation

**Build a small evaluator daemon with a separate service identity and storage root.**

Initial single-host shape:

```text
candidate sandbox (gVisor, no evaluator creds/network path)
       │ opaque invocation/result boundary
       ▼
evaluator daemon (separate Unix UID)
       ├── read-only protected dataset snapshots
       ├── exact evaluator/scorer release
       ├── optional isolated MLflow deployment/projection
       └── DSSE/in-toto-shaped signed EvaluationVerdict
```

Use blinded partitions: public regression cases for candidate development; locked
historical holdout; future-production cohort as the strongest final test. A dataset
manifest can reveal strata/counts/digest without paths or content. The evaluator samples
only according to the preregistered protocol and never returns raw hidden cases,
expected answers, or per-case diagnostics until the protocol permits unblinding.

Do not call Linux file permissions sufficient while every agent runs as the same user.
Do not mount the repository, home directory, telemetry archive, or MLflow database
wholesale into candidate sandboxes. Store signed verdicts in the canonical journal and
project only safe summaries to MLflow.

**Dependencies:** item 7 supplies digest identities; item 8 supplies real evaluator
identity and prevents candidate credential inheritance.

---

## 6. Shadow/canary assignment and policy activation/rollback

### The required contract

This subsystem separates four states often conflated as “deploying a process change”:

```text
installed: candidate bundle is available by digest
shadow:    candidate decisions are computed but never acted on
canary:    bounded eligible work is actually governed by candidate
active:    candidate is the default stable process
```

Assignment happens once at the outer coordinator's claim boundary, before an outcome is
known. The assignment record includes eligibility snapshot, unit, arm, stable and
candidate digest, algorithm/version, cohort, exposure phase, timestamp, and reason. It
is sticky across retries/resumption; a failed worker does not get reassigned to a more
favourable arm.

The controller needs:

- deterministic, auditable selection with no silent random fallback;
- targeting by pre-work strata and exclusions;
- cohort/sample/exposure caps;
- a stable control running concurrently where possible;
- invariant-triggered immediate abort;
- `pass`, `fail`, `inconclusive`, `error`, and `not_a_result` semantics;
- atomic activation of an exact release digest;
- last-known-good retention and atomic rollback; and
- a kill switch independent of the candidate policy.

Shadow output must be tagged counterfactual and kept away from the acting coordinator.
It can reveal disagreement, not causal outcome. Canary comparison must account for task
strata and the preregistered design; a feature-flag percentage alone is not an experiment.

### Concrete candidates

#### OpenFeature: best interface boundary, not an assignment engine

OpenFeature is a vendor-neutral feature-flag evaluation specification. Evaluation
context carries a targeting key for deterministic fractional evaluation, providers own
resolution, hooks can add validation/telemetry at defined lifecycle points, and the
tracking API associates flag evaluation with later outcomes.
([specification](https://openfeature.dev/specification/),
[evaluation context](https://openfeature.dev/docs/reference/concepts/evaluation-context/),
[hooks](https://openfeature.dev/docs/reference/concepts/hooks),
[tracking](https://openfeature.dev/specification/sections/tracking/))

This is an excellent seam between the outer coordinator and a project-owned policy
assignment provider. OpenFeature explicitly does not implement evaluation logic itself.
That is desirable here: eligibility, trial protocol, and typed outcomes remain local.

#### Flipt: lightweight OSS evaluation, insufficient experiment record

Flipt supports boolean rollouts, segments, variants, and deterministic sticky evaluation
from flag key and entity ID. It explicitly does not persist entities, contexts, or the
variant returned for an evaluation.
([Flipt concepts](https://docs.flipt.io/v2/concepts))

It could provide an admin UI and remote evaluation service, but the missing durable
assignment record is exactly what this design cannot tolerate. The project would still
need to record and reconcile every assignment. Its CRC32 bucket algorithm is adequate
for ordinary rollout consistency, but an HMAC-based assignment owned by the controller
is preferable when candidate agents should not predict or influence future assignments.

#### Unleash: mature rollout mechanics, broader service than needed

Unleash provides gradual percentage rollouts, constraints, variants, segments,
deterministic stickiness, impression data, metrics, and fast rollback. Its official docs
explain that stickiness hashes an identifier and group ID so the same subject receives
the same result as exposure grows.
([gradual rollout](https://docs.getunleash.io/guides/gradual-rollout),
[stickiness](https://docs.getunleash.io/concepts/stickiness),
[activation strategies](https://docs.getunleash.io/concepts/activation-strategies))

It is a credible adopt option if a general feature-management service is wanted across
many repositories. For this one coordinator, it introduces another mutable control
plane and still lacks project-specific preregistration, exact process-bundle activation,
failure classes, and promotion authorization.

#### Argo Rollouts: best state semantics, wrong runtime target

Argo Rollouts defines baseline/canary experiments, background or inline analysis,
retained measurements, dry-run metrics, and completed outcomes of Successful, Failed,
or Inconclusive. Failure aborts; inconclusive pauses; dry-run measurements do not affect
progression. It also retains stable ReplicaSets for rollback.
([analysis and progressive delivery](https://argo-rollouts.readthedocs.io/en/stable/features/analysis/),
[canary strategy](https://argo-rollouts.readthedocs.io/en/stable/features/canary/),
[rollback window](https://argo-rollouts.readthedocs.io/en/stable/features/rollback/))

These are the right semantics to copy. Argo is a Kubernetes deployment controller over
ReplicaSets and traffic routing, not an issue/process-policy deployer. Running process
workflows as Kubernetes workloads merely to use Argo would be architectural inversion.

### Recommendation

**Build a project-specific assignment and policy-deployment service behind an
OpenFeature-shaped provider.** Use `issue_id` or a durable `work_unit_id` as targeting
key and an evaluator-held keyed HMAC over `experiment_id || unit_id` for unbiased sticky
assignment. Persist the result before dispatch. Never fall back to random when identity
or policy is missing; return a typed refusal.

Represent rollout as a durable state machine with Argo-inspired outcomes:

```text
replay → shadow(dry-run) → canary(1/N) → canary(k/N) → active
                  │              │             │
                  └──── fail/error/invariant ──┴──▶ rollback(last-known-good)
                         inconclusive ─────────────▶ hold
```

Activation changes one service-owned pointer from `stable_digest` to
`candidate_digest` only after item 8 authorizes it. All in-flight work remains pinned to
the digest assigned at claim time. Rollback changes the default for new work and
explicitly governs whether safe in-flight work drains or is cancelled; it never silently
changes a running issue's process underneath it.

Start with an in-process provider and append-only assignment journal. Adopt Flipt or
Unleash later only if multi-project flag administration becomes a real requirement.

**Dependencies:** item 4 owns the trial lifecycle; item 7 supplies exact releases; item
8 owns the privileged activation pointer.

---

## 7. Operative process-manifest digest and policy bundle

### The required contract

A Git commit is necessary provenance but is not the operative process identity. It also
includes unrelated product code and omits external runtime inputs. Conversely, hashing
only prompts misses executable queue, routing, hook, gate, and adapter behavior.

The process release must describe the complete **effective** policy:

- initiative compiler/auditor templates and rubrics;
- outer coordinator workflow/configuration;
- seat/profile registry and generated seat surfaces;
- queue, admission, routing, breaker, review, adjudication, recovery, and landing code;
- hooks and relevant settings;
- project skills and process instructions loaded by workers;
- schemas, generators, and generated outputs;
- evaluator and assignment/promotion policy references;
- dependency lockfiles and executable/container digests; and
- explicit references to the separate constitutional and evaluator-root releases.

It must exclude mutable run inputs such as current issues, queue contents, evidence,
credentials, and current quota. Those are invocation state and are separately recorded.

Every entry needs normalized path/name, media type, byte size, SHA-256 digest,
executable mode where relevant, and provenance. The manifest also records schema,
release parent, Git source revision, builder identity/version, creation time, and
compatibility declarations. Paths are labels; digests establish identity.

### Concrete standards and candidates

#### Git tree/commit: excellent source history, incomplete effective identity

Git already provides immutable object identity and history, and all process sources
should remain reviewed there. But `git rev-parse HEAD` changes when unrelated mod code
changes and does not identify model/runtime versions, external dependencies, generated
equivalence, or protected constitutional/evaluator inputs. It should be a resolved
dependency in the manifest, not the manifest itself.

#### OCI descriptors and manifests: right content-addressing model

An OCI descriptor carries media type, digest, and byte size. Its digest is a content
identifier verified by independently hashing retrieved bytes; OCI recommends SHA-256.
OCI manifests form a Merkle DAG of content-addressed components and can represent
non-container artifacts with artifact types and subject links.
([descriptor specification](https://specs.opencontainers.org/image-spec/descriptor/),
[manifest specification](https://specs.opencontainers.org/image-spec/manifest/))

This is the right model for file/component descriptors and, later, distribution through
an OCI registry. Packaging the first implementation as an OCI artifact is optional;
using its descriptor semantics is valuable immediately.

#### RFC 8785 JCS: deterministic JSON bytes

RFC 8785 defines an invariant JSON serialization suitable for repeatable hashing and
signing through constrained primitives and deterministic property sorting.
([RFC 8785](https://www.rfc-editor.org/info/rfc8785/))

Use JCS for the manifest if the digest is computed over JSON. The builder must also sort
semantically unordered arrays before canonicalization; JCS does not choose array order.
Do not embed a self-referential digest inside the bytes being digested.

#### in-toto/DSSE and SLSA provenance: right attestation envelope

An in-toto Statement binds typed predicate metadata to immutable subjects by digest.
DSSE signs both payload and payload type, supports multiple signatures, and avoids
message-type confusion. SLSA provenance separates the declared build definition and
resolved dependencies from run details and builder identity.
([in-toto Statement](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md),
[DSSE](https://github.com/secure-systems-lab/dsse),
[SLSA v1.2 provenance](https://slsa.dev/spec/v1.2/provenance),
[build-provenance model](https://slsa.dev/spec/v1.2-rc2/build-provenance))

A custom `ProcessRelease/v1` predicate is justified because the artifact is not a
compiled binary, but it should reuse the standard Statement/resource descriptor and
envelope rather than inventing signing wire formats.

### Recommendation

**Build `process-release.json` as a canonical, content-addressed manifest and emit a
DSSE-wrapped in-toto attestation.** Suggested skeleton:

```json
{
  "schema": "https://arma-cti.example/process-release/v1",
  "releaseId": "pr-...",
  "parent": {"sha256": "..."},
  "source": {"gitCommit": "...", "dirty": false},
  "components": [
    {
      "name": "tools/dispatch.py",
      "mediaType": "text/x-python",
      "size": 123,
      "digest": {"sha256": "..."},
      "role": "dispatch-policy"
    }
  ],
  "externalDependencies": [...],
  "generatedRelationships": [...],
  "compatibility": {...},
  "constitution": {"sha256": "..."},
  "evaluatorRoot": {"sha256": "..."}
}
```

The authoritative `process_manifest_digest` is
`sha256(JCS(process-release.json))`. The DSSE/in-toto subject is that exact artifact.
The promoter signs it; the build agent cannot. Store the release and attestation in Git
or the canonical evidence store first. Add OCI artifact publication only when another
host needs to fetch/verify releases.

The builder should compute the effective file set from one reviewed declarative include
manifest plus explicit generated/external relationships. A hard-coded list in Python is
too easy to leave stale; hashing the whole repository hides policy scope and destroys
useful release identity. A verification command should explain which effective
component changed between two process digests.

Aliases such as `stable`, `candidate`, or MLflow prompt aliases remain mutable UX
pointers. Every dispatch, evaluation, and verdict records the exact digest.

**Dependencies:** item 8 controls signing/activation. Items 4–6 use this identity in
protocols and assignments.

---

## 8. Machine-enforced constitutional kernel and identity separation

### The required contract

The constitutional kernel is the smallest component allowed to say **who may change
which authority**. It must be much smaller and slower-changing than the operational
process bundle. It is not another prompt and cannot depend on an agent voluntarily
reading a rule.

The minimum protected authorities are:

- product outcome/scope and supersession;
- constitution amendment and trusted-key/identity registration;
- evaluator root, holdout release, and scorer authority;
- process promotion/rollback;
- permission or credential expansion;
- audit/provenance retention; and
- emergency freeze/kill switch.

The kernel mediates privileged actions through APIs; workers never receive direct
write credentials for the underlying GitHub repository, activation store, holdout,
MLflow evaluator deployment, or signing service.

A minimum identity and permission matrix is:

| Identity | May | Must not |
|---|---|---|
| Product curator | Ratify product outcomes and constitutional amendments; emergency freeze | Be required for routine implementation/process experiments |
| Candidate author | Read public policy/evidence; write candidate worktree and proposal | Read holdout/evaluator secrets; sign verdict; activate policy |
| Independent reviewer | Read exact candidate; issue signed review/adjudication evidence | Modify reviewed candidate; activate it |
| Evaluator | Read locked cases and exact candidate; issue evaluation verdict | Modify candidate/protocol after freeze; activate policy |
| Improvement controller | Schedule protocol phases; assign cohorts; request evaluation/promotion | Amend constitution/evaluator; forge reviewer/evaluator evidence |
| Promoter | Verify complete proof and atomically move activation pointer | Author candidate, change protocol, waive missing proof |

At least evaluator and promoter must be distinct security principals from candidate
workers. “Different agent session” is useful epistemic independence but not identity
separation when every session shares one Unix account and credential set.

Every privileged decision returns a typed allow/deny result with policy revision,
request identity, subject digest, rationale/rule IDs, and decision ID. Deny by default;
an unavailable or undefined decision never permits mutation.

### Concrete candidates

#### OPA: best operational authorization engine, not enforcement by itself

OPA evaluates arbitrary structured inputs against Rego policy through local APIs,
separating policy decision from the application that enforces it. Signed bundles list
file hashes and are activated only after signature verification; a failed update leaves
the existing bundle active. Decision logs include input, result, decision ID, bundle
revision, and masking support for secrets.
([OPA integration](https://www.openpolicyagent.org/docs/integration),
[signed bundles](https://www.openpolicyagent.org/docs/management-bundles),
[decision logs](https://www.openpolicyagent.org/docs/management-decision-logs),
[security guidance](https://www.openpolicyagent.org/docs/security))

OPA is the preferred decision engine. It is not the reference monitor: if agents retain
direct filesystem, GitHub, or credential access, they can bypass the query. The kernel
service must be the only principal able to perform the protected mutations.

#### SPIFFE/SPIRE: strong distributed workload identity, excessive for phase one

SPIRE registration entries map a SPIFFE ID to selectors which workload attestors verify
from the actual process/node environment. A workload obtains an SVID after the agent
identifies its process and matches those selectors. Unix UID/GID/path, container, or
Kubernetes service-account properties can participate.
([SPIRE concepts](https://spiffe.io/docs/latest/spire-about/spire-concepts/),
[workload registration](https://spiffe.io/docs/latest/deploying/registering/),
[Workload API](https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/))

This is the right evolution when coordinator, evaluator, promoter, and workers span
machines or Kubernetes. For a single Linux host it introduces an identity control plane
before simpler kernel-verifiable identities have been exhausted.

#### Unix service identities and peer credentials: best single-host starting point

Linux Unix-domain sockets expose the connected peer's credentials through read-only
`SO_PEERCRED`, captured at connection time.
([`unix(7)`](https://man7.org/linux/man-pages/man7/unix.7.html))

Separate service UIDs, restrictive directory/socket ownership, systemd hardening, and
gVisor worker sandboxes create a real boundary without distributing static bearer
tokens. The boundary fails if a candidate can control service unit/sandbox
configuration or escalate to host root, so those surfaces belong to the protected
kernel deployment.

#### in-toto thresholds and TUF root roles: useful trust-pattern implementations

in-toto layouts authorize functionary keys per step and can require threshold evidence
from distinct functionaries which agree on materials/products.
([in-toto specification](https://github.com/in-toto/docs/blob/master/in-toto-spec.md))

TUF root metadata assigns keys and signature thresholds to roles; root-key rotation
must satisfy both the old and new root thresholds, and clients reject rollback and
expired/frozen metadata. TUF recommends protecting root keys offline.
([TUF specification](https://theupdateframework.github.io/specification/))

Do not implement a package-update repository just to use these ideas. Apply them to
constitutional amendments and trust-root rotation: the current human root authorizes
the next root; ordinary process promoters cannot rewrite their own key set; high-impact
changes can require more than one independent attestation even if the human is normally
absent from operational work.

### Recommendation

**Build a small local constitutional gateway, not a sprawling governance platform.**

Phase-one deployment:

```text
candidate/reviewer sandboxes ── Unix socket/API requests ──▶ constitutional gateway
          distinct UIDs                                  │
                                                        ├─ OPA signed policy bundle
evaluator service UID ──────────────────────────────────▶├─ verify DSSE/in-toto evidence
                                                        ├─ promotion/rollback pointer
promoter service UID ───────────────────────────────────▶├─ append-only decision journal
                                                        └─ scoped GitHub/secret broker
```

The gateway authenticates local peers from OS credentials, asks OPA for an authorization
decision, verifies exact subject/process/protocol/verdict digests, performs the bounded
mutation itself, and appends the decision. Candidate workers receive narrow
issue/worktree capabilities, not the gateway's GitHub token or filesystem ownership.

Keep the constitutional policy in a separately signed bundle with a human-controlled
root key. Operational process experiments may change ordinary OPA data/policy only
inside a delegated namespace and through the normal process-release path. They cannot
change root identities, holdout/evaluator authority, promotion predicates, log masking
for protected decisions, or the gateway binary.

When a second trusted machine arrives, replace UID-only authentication with
SPIFFE/SPIRE SVIDs and mutual TLS while preserving the same role/action policy. Do not
make SPIRE a prerequisite for proving the single-host API and authority graph.

Most importantly, move secrets and mutation behind the gateway before claiming machine
enforcement. The current post-#317 exact-SHA review record prevents ordinary shortcuts
but, as ADR-0071 itself acknowledges, same-user evidence remains forgeable. Identity
separation is the step that turns the convention into a security property.

---

## Integrated build sequence

The eight designs should land as thin vertical slices, not eight platforms built in
isolation:

### Slice A — one initiative can compile and audit durably

1. Define `initiative.schema.json`, stable IDs, descriptors, and graph validation
   (item 2).
2. Implement the initiative compiler's pure state machine and artifact stages, using
   the existing interactive skills as stage adapters (item 1).
3. Add deterministic coverage plus one author-distinct product/architecture audit that
   emits gap tickets (item 3).

At this point a crash must not lose stage state, but a simple file journal is acceptable.

### Slice B — one process hypothesis can be evaluated end to end

4. Define `process-release.json` and compute exact digests without signing yet (item 7).
5. Add a DBOS-backed controller for evidence freeze, preregistration, replay, and typed
   experiment verdicts; project results to MLflow (item 4).
6. Stand up the separate evaluator UID/service with one public and one locked dataset
   snapshot; emit signed/digest-bound verdicts (item 5).

### Slice C — one safe live canary can promote and roll back

7. Add sticky claim-time assignment, shadow results, a one-issue canary, atomic
   last-known-good pointer, and forced rollback test (item 6).
8. Put activation, evaluator access, signatures, and tracker mutation behind the local
   constitutional gateway and distinct identities (item 8).
9. Only then allow the controller to promote without a routine human ruling.

### Acceptance demonstration

The first end-to-end trial should be deliberately adversarial. It should prove that:

- compiler or controller death resumes without duplicate issues, dispatches, MLflow
  runs, assignments, or promotions;
- a candidate cannot read a locked case, evaluator prompt/key, or activation credential;
- an author cannot provide the clearing reviewer/evaluator signature;
- a protocol cannot change after preregistration without acquiring a new identity;
- MLflow deletion or outage cannot erase canonical evidence or block delivery;
- an inconclusive evaluator result does not promote;
- an invariant violation aborts the canary and restores the exact last-known-good
  digest; and
- a constitutional amendment is impossible without the human root authority.

## What not to build

This research eliminates several tempting duplications:

- no second issue scheduler inside the initiative compiler;
- no custom experiment UI, trace database, prompt registry, or judge runner already
  provided by MLflow;
- no requirements-management platform replacing readable Markdown and GitHub;
- no Kubernetes deployment merely to gain Argo's state names;
- no RDF provenance graph as the primary authoring format;
- no OCI registry until policy artifacts genuinely cross hosts;
- no SPIFFE control plane while every trusted service is on one host; and
- no “constitutional prompt” which relies on the candidate choosing to obey it.

The project-specific code should remain narrow: initiative semantics, evidence joins,
experiment protocol, assignment, exact process identity, and privileged authority
transitions. Durability, experiment exploration, content descriptors, signatures,
sandboxing, workload identity, and policy evaluation should be borrowed from the
specialized systems above.
