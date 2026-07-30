# AI Commander brain lives in the Python daemon, not in SQF

The AI Commander planner runs outside the game process, in the Python daemon, reached via extension RPC. Planner is a pure function `(campaign state, world observations) -> orders`, testable with pytest and hypothesis at millisecond speed, hot-reloadable without an Arma restart, and its decision traces land in the telemetry log. SQF-in-game was the alternative (no runtime RPC needed) but loses property testing, slows agent iteration, and puts two planners on the server scheduler.

Consequence: the Command Port has one wire format consumed identically by the human UI (SQF side) and the AI planner (Python side) — commander symmetry is enforced by construction. The extension must support bidirectional runtime RPC during play, not just save/load.

The game-AI ecosystem reinforces Python: HTN planning (GTPyhop), behaviour trees (py_trees), graph reasoning (networkx), assignment optimisation (OR-tools) all have their best tooling there. MVP planner is a seeded deterministic utility scorer over the Objective adjacency graph; HTN is the escalation path. An LLM-as-commander experiment is deliberately post-MVP (nondeterministic, property-untestable) but the planner interface and decision-trace telemetry accommodate it unchanged.
