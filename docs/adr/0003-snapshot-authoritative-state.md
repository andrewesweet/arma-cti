# Snapshot-authoritative campaign state, telemetry log non-authoritative

The original design doc made an append-only event log the source of truth, with campaign state derived by a pure fold. After ADR-0001 (session-based campaign) removed the always-on-server justification, we decided: campaign state is a single versioned snapshot document, autosaved periodically during a Play Session and at session end. An append-only telemetry/event log is kept for observability only — flight recorder, test assertions, coverage, AI Commander decision traces — and is never an input to campaign state, so a telemetry bug cannot corrupt the campaign.

Considered: full event sourcing (fold, upcasters, idempotency, cross-process determinism tests). Rejected as the highest-complexity option whose remaining benefits (sub-autosave durability, historical replay) are weak for a personal game. Fixtures improve under snapshots: a fixture is a hand-authored, schema-validated state file.

Consequences: property tests target `load(save(s)) == s` and state-schema migrations; chaos testing reduces to kill-mid-write; crash loses at most one autosave interval.
