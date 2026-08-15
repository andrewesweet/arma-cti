// Non-normative architecture model for GitHub issue #377. The issue and #378-#388 govern scope.
workspace "Autonomous Development MVP" "C4 model for the breadth-first autonomous system-of-work walking skeleton." {

    model {
        productCurator = person "Product Curator" "Chooses desired product outcomes and answers irreducible product questions."

        github = softwareSystem "GitHub" "Holds the visible Initiative, Work Item graph, dependencies, integrated repository, and close evidence." "External"
        agentProviders = softwareSystem "Agent Providers" "Run Claude Code or Codex sessions for semantic planning, implementation, review, audit, and improvement work." "External"

        autonomousDevelopment = softwareSystem "Autonomous Development System" "Turns a curated Desired Outcome into integrated, audited product work and improves its own low-risk process surfaces." {
            controller = container "System-of-Work Controller" "Single scheduling authority that reconciles Control Facts into idempotent Control Actions." "Python 3.13 CLI and systemd user service" {
                factCollector = component "Control Fact Collector" "Reads tracker, repository, dispatch, worktree, gate, and ledger facts through anti-corruption adapters." "Python"
                reconciliationKernel = component "Reconciliation Kernel" "Pure reducer that derives lifecycle state and legal Control Actions from normalized Control Facts." "Python"
                initiativePolicy = component "Initiative Policy" "Enforces Initiative publication, design-disposition, traceability, and replanning invariants." "Python"
                coordinationPolicy = component "Coordination Policy" "Enforces dependency, WIP, active-run exclusion, freshness, and dispatch invariants." "Python"
                assurancePolicy = component "Outcome Assurance Policy" "Freezes audit subjects and routes delivery gaps, planning gaps, and product questions differently." "Python"
                improvementPolicy = component "Process Improvement Policy" "Freezes evidence windows and limits autonomous changes to one allowlisted proposal per cycle." "Python"
                stageGateway = component "Semantic Stage Gateway" "Builds stage briefs, invokes the existing dispatcher, and normalizes provider-specific structured output into Stage Verdicts." "Python and JSON Schema"
                actionExecutor = component "Control Action Executor" "Applies validated actions through GitHub and existing delivery-tool adapters, then records what actually happened." "Python"
            }

            deliveryToolchain = container "Delivery Toolchain" "Existing queue, worktree, dispatch, watcher, recovery, post-#317 review/adjudication, gate, and landing commands." "Python, just, Git, Claude Code, Codex"
            repositoryWorkspaces = container "Repository and Worktrees" "Holds the integrated tree and isolated per-Work-Item workspaces." "Git filesystem" "Database"
            controlStore = container "Local Control Store" "Rebuildable transition journal, materialized runtime view, dispatch records, and structured Stage Verdicts outside worktrees." "JSON and JSONL filesystem with flock" "Database"
            evidencePlane = container "Evidence Plane" "Collects OpenTelemetry and materializes the project ledger without becoming scheduling authority." "OpenTelemetry Collector and Python ledger"
            mlflowLab = container "MLflow Lab" "Optional, non-authoritative trace and improvement-window comparison UI." "MLflow with SQLite and local artifacts" "Optional"
        }

        productCurator -> github "Records Desired Outcome and answers Product Questions in" "GitHub issue"

        controller -> github "Reads the visible graph and idempotently publishes Initiatives, Work Items, relationships, and audit records to" "gh CLI / GitHub REST JSON"
        controller -> repositoryWorkspaces "Reads integrated SHA and operative process revision from" "Git"
        controller -> controlStore "Reads and appends control records in" "Filesystem"
        controller -> deliveryToolchain "Invokes bounded semantic stages and eligible Work Runs through" "Python/CLI"
        controller -> evidencePlane "Emits lifecycle, stage, and process-revision telemetry to" "OTLP"

        deliveryToolchain -> agentProviders "Runs semantic work using" "Provider CLI"
        deliveryToolchain -> repositoryWorkspaces "Creates, changes, reviews, gates, and lands exact candidates in" "Git and filesystem"
        deliveryToolchain -> github "Reads Work Items and publishes workpads and close evidence to" "gh CLI / GitHub REST JSON"
        deliveryToolchain -> controlStore "Writes dispatch records and structured Stage Verdicts to" "Filesystem"
        deliveryToolchain -> evidencePlane "Exports dispatch and tool telemetry to" "OTLP"
        evidencePlane -> mlflowLab "Projects selected traces and improvement comparisons into" "OTLP/HTTP or MLflow API" "Optional"

        factCollector -> github "Reads tracker facts from" "REST JSON"
        factCollector -> repositoryWorkspaces "Reads Git and worktree facts from" "Git/filesystem"
        factCollector -> controlStore "Reads prior transitions, dispatches, and Stage Verdicts from" "JSON/JSONL"
        factCollector -> evidencePlane "Reads materialized delivery evidence from" "Ledger JSON"
        factCollector -> reconciliationKernel "Supplies normalized Control Facts to" "In-process values"

        reconciliationKernel -> initiativePolicy "Asks for Initiative transitions and invariants from" "In-process call"
        reconciliationKernel -> coordinationPolicy "Asks for eligibility and dispatch actions from" "In-process call"
        reconciliationKernel -> assurancePolicy "Asks for audit and gap-routing actions from" "In-process call"
        reconciliationKernel -> improvementPolicy "Asks for improvement-cycle actions from" "In-process call"
        reconciliationKernel -> stageGateway "Requests semantic stages through" "Typed stage request"
        reconciliationKernel -> actionExecutor "Hands an ordered Control Action plan to" "In-process values"
        stageGateway -> deliveryToolchain "Dispatches schema-constrained agent stages through" "Existing dispatch port"
        actionExecutor -> github "Applies tracker mutations through" "Idempotent publisher adapter"
        actionExecutor -> deliveryToolchain "Applies worktree, dispatch, review, and landing actions through" "Existing command adapters"
        actionExecutor -> controlStore "Appends planned, applied, and confirmed transitions to" "JSONL"

        deploymentEnvironment "MVP" {
            deploymentNode "Development Host" "Single trusted Linux/WSL host" "Linux" {
                infrastructureNode "systemd User Manager" "Runs one controller instance and restarts it after failure." "systemd"
                infrastructureNode "Git and gh" "Provides repository and GitHub command-line integration." "Git / GitHub CLI"
                containerInstance controller
                containerInstance deliveryToolchain
                containerInstance repositoryWorkspaces
                containerInstance controlStore
                containerInstance evidencePlane
                containerInstance mlflowLab
            }
            deploymentNode "Provider Clouds" "External hosted systems" "SaaS" {
                softwareSystemInstance github
                softwareSystemInstance agentProviders
            }
        }
    }

    views {
        systemContext autonomousDevelopment "SystemContext" "Product curation and external-system boundary for the autonomous-development MVP." {
            include *
            autoLayout lr
        }

        container autonomousDevelopment "Containers" "Deployable/runtime units of the single-host MVP." {
            include *
            autoLayout lr
        }

        component controller "ControllerComponents" "Components of the deterministic System-of-Work Controller." {
            include *
            autoLayout lr
        }

        dynamic autonomousDevelopment "InitiativeFlow" "One Initiative from product curation through delivery, audit, and satisfaction." {
            productCurator -> github "Records Desired Outcome"
            controller -> github "Reads curated Initiative"
            controller -> deliveryToolchain "Dispatches Initiative Planning stage"
            deliveryToolchain -> agentProviders "Derives Product Specification, Design Disposition, and Work Graph"
            controller -> github "Publishes Initiative and Work Graph"
            controller -> deliveryToolchain "Dispatches eligible Work Run"
            deliveryToolchain -> agentProviders "Runs implementation and review"
            deliveryToolchain -> repositoryWorkspaces "Lands exact candidate"
            controller -> deliveryToolchain "Dispatches Initiative Audit"
            controller -> github "Publishes audit or classified gaps"
            autoLayout lr
        }

        dynamic autonomousDevelopment "ImprovementFlow" "One primitive autonomous process-improvement cycle." {
            deliveryToolchain -> evidencePlane "Emits delivery evidence"
            controller -> evidencePlane "Freezes evidence window"
            controller -> deliveryToolchain "Dispatches retrospective stage"
            controller -> github "Publishes one allowlisted Process Change as a Work Item"
            controller -> deliveryToolchain "Dispatches ordinary delivery loop"
            deliveryToolchain -> repositoryWorkspaces "Lands Process Revision"
            evidencePlane -> mlflowLab "Projects comparison evidence"
            autoLayout lr
        }

        deployment autonomousDevelopment "MVP" "Deployment" "Single-host deployment with external GitHub and agent providers." {
            include *
            autoLayout lr
        }

        styles {
            element "Person" {
                shape Person
                background #08427B
                color #ffffff
            }
            element "Software System" {
                background #1168BD
                color #ffffff
            }
            element "Container" {
                background #438DD5
                color #ffffff
            }
            element "Component" {
                background #85BBF0
                color #000000
            }
            element "Database" {
                shape Cylinder
            }
            element "External" {
                background #999999
                color #ffffff
            }
            element "Optional" {
                background #7A6FA8
                color #ffffff
                border dashed
            }
            relationship "Optional" {
                style dashed
                color #7A6FA8
            }
        }
    }
}
