# Process log

Audit trail of how the development process evolved. One entry per retro. See ADR-0009.

## 2026-07-30 — bootstrap (not a retro)

Initial process written during the founding grilling session, before any practical use. All artefacts stamped `unproven`: `CLAUDE.md`, `.claude/skills/{playtest-brief,playtest-ingest,retro}`, `docs/agents/*`. First real retro due at end of Phase 0.

## 2026-07-30 — user-directed amendment: versioning standards (not a retro)

Adopted Conventional Commits 1.0.0, Keep a Changelog 1.1.0, SemVer 2.0.0 (ADR-0010). Enforcement: cocogitto 7.0.0 installed, `commit-msg` hook active and verified rejecting bad messages, existing history checked clean, `CHANGELOG.md` seeded, CLAUDE.md contract updated, `cog check` earmarked for `just check`.

## 2026-07-30 — user-directed amendment: prompting-guide alignment (not a retro)

Agent guidance reviewed against Anthropic's official Opus 5 and Fable 5 prompting guides, at the user's direction, optimising each document for its likelier consumer (opus[1m] for day-to-day surfaces). Changes: `CLAUDE.md` gained a Working style section (scope discipline, verification capped at the project gates, subagent-delegation limits, evidence-grounded progress claims, report-everything review passes, deliverable-length calibration); `retro` gained a bias-toward-removal rule (current models degrade under over-prescription); `playtest-brief` gained document-length calibration. `docs/agents/*` (mechanical command reference) and `CONTEXT.md`/ADRs (domain facts, not behavioural prompts) reviewed, unchanged. No existing instruction conflicted with the guides; notably nothing instructs reasoning reproduction (a Fable 5 refusal trigger).
