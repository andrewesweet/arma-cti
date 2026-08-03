---
name: playtest-ingest
description: Convert a filled-in playtest response into tests, issues, and follow-ups. Use when the user says they have played a brief or a playtest response file has been filled in.
---

# Playtest Ingest

> Status: validated ×1 — first use (playtest 0001, 2026-08-03) turned a played brief into five issues (#174–#178) and evidence for two of #18's acceptance criteria, and the three-way classification held. One friction found in that use is amended below (class 1). Amend via /retro only.

Read the brief `docs/playtest/NNNN-<slug>.md` and its filled `docs/playtest/NNNN-response.md`. For every finding, classify into exactly one of:

1. **Automatable** — the failure can be expressed as an acceptance spec or lower-tier test. Write the failing test (spec changes are sign-off gated: propose, don't merge). This is the preferred outcome; push hard for it. Write it where a red costs nothing — an acceptance spec or a unit test. Never a probe: `just regress` gates every landing, so a red probe in the corpus blocks unrelated issues until the finding is fixed. The probe lands with the fix; the ingest writes its assertion into the issue as an acceptance criterion instead.
2. **Not automatable, actionable** — perceptual or feel issue needing code change. Create a GitHub issue (see `docs/agents/issue-tracker.md`), labelled per `docs/agents/triage-labels.md`, quoting the response verbatim and linking the brief.
3. **Ambiguous** — the response doesn't pin down what was wrong. Collect into at most a handful of short follow-up questions for the user; never guess.

Then:

- Summarise the mapping (finding, classification, artefact) back to the user in one table.
- If any finding suggests a domain term is missing or misused, note it for `/domain-modeling` — do not edit `CONTEXT.md` yourself.
- After ingest completes, run `/retro` on the playtest *process* itself (was the brief answerable? were questions wrong-shaped?).
