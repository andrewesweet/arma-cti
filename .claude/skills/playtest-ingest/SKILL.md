---
name: playtest-ingest
description: Convert a filled-in playtest response into tests, issues, and follow-ups. Use when the user says they have played a brief or a playtest response file has been filled in.
---

# Playtest Ingest

> Status: unproven — written before first practical use. Amend via /retro only.

Read the brief `docs/playtest/NNNN-<slug>.md` and its filled `docs/playtest/NNNN-response.md`. For every finding, classify into exactly one of:

1. **Automatable** — the failure can be expressed as an acceptance spec or lower-tier test. Write the failing test (spec changes are sign-off gated: propose, don't merge). This is the preferred outcome; push hard for it.
2. **Not automatable, actionable** — perceptual or feel issue needing code change. Create a GitHub issue (see `docs/agents/issue-tracker.md`), labelled per `docs/agents/triage-labels.md`, quoting the response verbatim and linking the brief.
3. **Ambiguous** — the response doesn't pin down what was wrong. Collect into at most a handful of short follow-up questions for the user; never guess.

Then:

- Summarise the mapping (finding, classification, artefact) back to the user in one table.
- If any finding suggests a domain term is missing or misused, note it for `/domain-modeling` — do not edit `CONTEXT.md` yourself.
- After ingest completes, run `/retro` on the playtest *process* itself (was the brief answerable? were questions wrong-shaped?).
