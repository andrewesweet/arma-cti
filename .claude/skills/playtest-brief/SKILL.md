---
name: playtest-brief
description: Author a playtest brief for the human before a play session. Use when a milestone's automated tiers are green, or when the user asks what to playtest.
---

# Playtest Brief

> Status: unproven — written before first practical use. Amend via /retro only.

Playtests are scarce; spend them only on what automation cannot see (feel, pacing, UI legibility, AI believability — the perceptual ceiling). Read `CONTEXT.md` and use its vocabulary throughout.

Write `docs/playtest/NNNN-<slug>.md` (NNNN = next number in the directory):

1. **Boot line** — the exact command to launch, booting a committed fixture that lands the player directly in the interesting state. Never a fresh campaign unless the brief is about the opening.
2. **Scenarios** — 2–5, numbered. Each: what to do, what *should* happen, expected duration. Every scenario must target a question automation cannot answer; if a scenario could be an acceptance spec instead, write the spec and drop the scenario.
3. **Questions** — closed-form wherever possible (y/n, pick-one, 1–5 scale), plus exactly one open "what felt wrong?" per scenario.
4. **Response template** — pre-generate `docs/playtest/NNNN-response.md` with the questions as a fill-in form. Terse answers must suffice.

Constraints:

- The perceptual checklist (standing look/feel/sound items included in every brief) is capped at ~10 items and grows only with human sign-off.
- Total brief must be playable in under 45 minutes.
- Tell the user the brief is ready and where it is; do not chase them to play it.
