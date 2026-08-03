---
name: playtest-brief
description: Author a playtest brief for the human before a play session. Use when a milestone's automated tiers are green, or when the user asks what to playtest.
---

# Playtest Brief

> Status: validated ×2 — first use (brief 0001, 2026-08-01) delivered the session it was written for; four frictions found in that use are amended below (2026-08-01 retro, ADR-0026). Second use is the same brief played end to end (2026-08-03): the boot line ran verbatim and its own honesty note discharged — the half hour nothing had ever soaked held at 1813 s — and the session produced five issues plus evidence for two of #18's acceptance criteria. Three further frictions from that use are amended below. Amend via /retro only.

Playtests are scarce; spend them only on what automation cannot see (feel, pacing, UI legibility, AI believability — the perceptual ceiling). Read `CONTEXT.md` and use its vocabulary throughout.

Write `docs/playtest/NNNN-<slug>.md` (NNNN = next number in the directory):

1. **Boot line** — the exact command to launch, booting a committed fixture that lands the player directly in the interesting state. Run it before handing the brief over — the tier being busy defers delivery, not verification. Brief 0001's boot line was authored blind and honestly flagged, and verification still found two wrong instructions (a lobby that does not exist; a build step the session never loads) and a harness bug filing a joined Commander as never-arrived. A fixture that asserts nothing lives in `spike/playtest/`, never `spike/probes/` — `just regress` runs everything there (docs/regression-tier.md). Never a fresh campaign unless the brief is about the opening, or no staged-state fixture can yet express the state (#42); say which in the brief.
2. **Scenarios** — 2–5, numbered. Each: what to do, what *should* happen, expected duration. Every scenario must target a question automation cannot answer; if a scenario could be an acceptance spec instead, write the spec and drop the scenario. Order them so a scenario discharging an acceptance criterion comes first: brief 0001 put #18's two eyes-only criteria third, behind twelve minutes of other scenarios, and they were reached only by re-prioritising in the seat.
3. **Questions** — closed-form wherever possible (y/n, pick-one, 1–5 scale), plus exactly one open "what felt wrong?" per scenario.
4. **Response template** — pre-generate `docs/playtest/NNNN-response.md` with the questions as a fill-in form. Terse answers must suffice. A brief amended after its template exists amends the template in the same commit: brief 0001 grew scenario 5 — the Reinforce discount, held for playtest by the human's own decision — and its template did not, so the one number the brief was extended to judge had nowhere to be answered.

Constraints:

- The perceptual checklist (standing look/feel/sound items included in every brief) is capped at ~10 items and grows only with human sign-off. While it is empty, ask for candidate items at the bottom of the response form instead of inventing entries — brief 0001's resolution of the first-use deadlock.
- Total brief must be playable in under 45 minutes, and the document itself sized to what the playtest needs — no padding, no boilerplate sections.
- Tell the user the brief is ready and where it is; do not chase them to play it.
- A session an agent attends live is the stronger form. Findings arrive dictated and land verbatim, and a claim the wire can settle gets settled while the human is still in the seat — brief 0001's "I think they were killed" was refuted mid-session (all three Squads alive at size 8) and the real defect was the larger one. Expect the written questions to go unanswered in exchange, and treat them as the agent's list of what the session still owes.
