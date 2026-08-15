# Autonomous development research map

**Status:** Wayfinding only. GitHub issues are the specification and delivery authority; the
documents below preserve evidence and design rationale without changing operative process policy.

## Governing artifacts

| Artifact | Authority |
|---|---|
| [Target-state specification #376](https://github.com/andrewesweet/arma-cti/issues/376) | Desired end state and enduring product obligations. |
| [MVP specification #377](https://github.com/andrewesweet/arma-cti/issues/377) | Walking-skeleton scope and MVP decisions. |
| [Implementation tickets #378–#388](https://github.com/andrewesweet/arma-cti/issues/377) | Delivery acceptance criteria and dependency graph. |

## Current non-normative design

| Document | Role |
|---|---|
| [MVP implementation design](autonomous-mvp-implementation-stack.md) | Domain boundaries, authority, consistency, technology choices, deferral triggers, and published ticket map. |
| [C4 workspace](autonomous-mvp-workspace.dsl) | System context, containers, controller components, dynamic flows, and single-host deployment model. |

## Research evidence

| Document | What it preserves | Current standing |
|---|---|---|
| [Symphony and issue #317](symphony-and-issue-317.md) | Source-level comparison of the outer coordinator with the post-#317 inner delivery constitution. | Background rationale for the nested-orchestrator boundary. |
| [Symphony OSS alternatives](symphony-oss-alternatives.md) | Survey of direct and adjacent open-source coordination systems. | Prior art; no surveyed runtime is selected for the MVP. |
| [Closest OSS system](autonomous-agentic-development-alternative.md) | Why Gas City was the closest outcome-to-delivery candidate. | Candidate assessment retained; adoption recommendation superseded by #377. |
| [Eight implementation gaps](eight-autonomous-process-implementation-gaps.md) | Detailed target-state capability and build-versus-buy research. | Target-state input; its build sequence is not the MVP plan. |
| [Autonomous continuous improvement](autonomous-system-of-work-continuous-improvement.md) | Evidence-to-retro-to-experiment-to-activation architecture and authority constraints. | Supporting rationale for #376/#377. |
| [MLflow's improvement role](mlflow-role-in-system-of-work-improvement.md) | MLflow feature assessment and evidence-versus-authority boundary. | Supporting rationale for #376/#377. |
| [Claude/Codex/MLflow observability gap](claude-codex-mlflow-observability-gap-analysis.md) | Dated local-system and product-capability comparison. | Supporting snapshot; version-specific claims require revalidation. |

## Quarantined adoption research

| Document | Standing |
|---|---|
| [Omnigent dispatch-platform analysis](omnigent-dispatch-platform-analysis.md) | Background execution-substrate assessment; authorizes no adoption. |
| [Omnigent and MLflow adoption](omnigent-mlflow-adoption.md) | Broader bounded-adoption hypothesis; separate from and subordinate to #377. |

Research snapshots should be updated by a new dated assessment rather than silently edited to
look current. A later decision may cite them, but it must be recorded in the repository's normal
decision or specification surface.
