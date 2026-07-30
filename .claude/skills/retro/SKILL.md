---
name: retro
description: Review how the development process itself performed and propose amendments. Use after completing a phase, after a playtest ingest, or when the user asks for a retro.
---

# Retro

> Status: unproven — written before first practical use. This skill amends itself only through its own procedure.

Subject is the **process**, not the code: commands, failure classes, gates, skills, conventions in `CLAUDE.md` and `.claude/skills/`. Code defects belong in issues, not here.

1. **Evidence sweep** — from this session (or the named phase): where did an agent fight the process? Wrong or missing `just` command, failure class that didn't fit, gate that blocked without value or was bypassed, skill step that didn't survive contact, convention nobody followed.
2. **Propose diffs** — concrete edits to project-owned surfaces only: `CLAUDE.md`, `.claude/skills/*`, `docs/agents/*`. **Never** the global (Matt Pocock) skills — they are shared across projects. Each diff: one-line rationale grounded in evidence from step 1, not taste.
3. **Sign-off** — all process changes are human-gated. Present the diffs; apply only what is approved.
4. **Journal** — append to `docs/process-log.md`: date, trigger (phase/playtest/ad-hoc), findings, changes applied, changes rejected. One entry per retro, terse.
5. **Status upgrades** — any process artefact marked `unproven` that survived real use unchanged: propose upgrading its marker (`validated ×N`). Downgrade or amend ones that failed.
