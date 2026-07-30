# Session-based persistent campaign, not always-on server

The original design doc assumed a continuously running dedicated server with restart invisibility as a first-class feature. This is a personal-use project: we decided the campaign is session-based — Arma runs only during a Play Session, and the Campaign persists between sessions via durable external state. This removes the drain protocol, the restart-invisibility acceptance tier, and most of the chaos surface, while keeping campaign state external to the Arma process so an always-on upgrade path remains open.

Consequences: "restart invisibility" reduces to "resume fidelity" (a session boot from persisted state must reproduce the world); chaos testing reduces to kill-mid-write recovery.
