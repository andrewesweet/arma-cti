# Process log

Audit trail of how the development process evolved. One entry per retro. See ADR-0009.

## 2026-07-30 — bootstrap (not a retro)

Initial process written during the founding grilling session, before any practical use. All artefacts stamped `unproven`: `CLAUDE.md`, `.claude/skills/{playtest-brief,playtest-ingest,retro}`, `docs/agents/*`. First real retro due at end of Phase 0.

## 2026-07-30 — user-directed amendment: hooks and language toolchains (not a retro)

Claude Code hooks added (`.claude/hooks/` + `.claude/settings.json`, all tested): deny edits to generated files and acceptance specs (mechanises the F1 oracle mitigation), deny `git commit --no-verify`, auto-format `.py`/`.rs` on edit. A fourth (lint-after-edit) deferred pending Phase 0 latency measurement. Python toolchain decided: uv, ruff, ty (Astral, user's explicit choice over pyright), pytest/hypothesis, coverage.py, mutmut. Rust: pinned toolchain, clippy `-D warnings`, rustfmt. Blanket strictness principle: warnings are errors; suppressions need inline justification.

## 2026-07-30 — user-directed amendment: versioning standards (not a retro)

Adopted Conventional Commits 1.0.0, Keep a Changelog 1.1.0, SemVer 2.0.0 (ADR-0010). Enforcement: cocogitto 7.0.0 installed, `commit-msg` hook active and verified rejecting bad messages, existing history checked clean, `CHANGELOG.md` seeded, CLAUDE.md contract updated, `cog check` earmarked for `just check`.

## 2026-07-30 — user-directed amendment: prompting-guide alignment (not a retro)

Agent guidance reviewed against Anthropic's official Opus 5 and Fable 5 prompting guides, at the user's direction, optimising each document for its likelier consumer (opus[1m] for day-to-day surfaces). Changes: `CLAUDE.md` gained a Working style section (scope discipline, verification capped at the project gates, subagent-delegation limits, evidence-grounded progress claims, report-everything review passes, deliverable-length calibration); `retro` gained a bias-toward-removal rule (current models degrade under over-prescription); `playtest-brief` gained document-length calibration. `docs/agents/*` (mechanical command reference) and `CONTEXT.md`/ADRs (domain facts, not behavioural prompts) reviewed, unchanged. No existing instruction conflicted with the guides; notably nothing instructs reasoning reproduction (a Fable 5 refusal trigger).

## 2026-07-30 — user-directed amendment: full wiki snapshot (not a retro)

The Phase 0 retro added `docs/reference/arma-wiki/` to *Read first* on the strength of a research failure; it held nine hand-picked pages, which is thin cover for "consult the wiki first". A full BIKI export became available and is now vendored: 6,690 pages, tier A + B plus the non-article namespaces. *Read first* gained the navigation an agent needs to use it — guessable paths, `MANIFEST.json` as the lookup, per-directory `INDEX.md` instead of listing a 2,672-file directory — and two traps worth naming. Game applicability is in each file's `// categories:` header and never in the wikitext, because BIKI generates categories from templates, so grepping page source for `Arma 3` finds nothing. And pre-Arma-3-only pages are excluded, so a miss is not proof the wiki lacks the page.

## 2026-07-30 — retro: Phase 0 spike (#2)

First real retro. Trigger: phase completion.

**Findings.** The dominant one is a research failure, not an execution failure: eleven configuration hypotheses were tested and eliminated over most of a day before the headless-client blocker turned out to be one sentence of first-party documentation ("Don't forget to set NAME property"). The wiki was Cloudflare-blocked from this environment throughout, so the source holding the answer was the one source not consulted. Secondary: the `just` command table listed recipes that did not exist and omitted every recipe that did; the failure-class table earned its keep when `infra_unavailable` fired on a stale daemon holding a port and correctly refused to be interpreted as a result; the lint-after-edit hook deferred on 2026-07-30 became decidable once latency was measured.

**Applied** (all human-approved): command-surface table replaced with the recipes that exist, with the acceptance tiers marked as Phase 1 work; `docs/reference/arma-wiki/` added to *Read first* with an instruction to consult it before experimenting on engine behaviour; failure-class table marked `validated ×1`; a port-collision line added to *Contract*, since the Arma tier shares this machine with the human's play sessions under WSL2 mirrored networking; `lint-after-edit.py` enabled for `.sqf`/`.cpp`/`.rs` (132 ms and 121 ms measured, against 20–56 ms for the hooks already running), advisory-only so `just check` remains the gate.

**Rejected / no change.** `block-no-verify.py` false-positived on a Bash call whose heredoc *contained* the blocked phrase as text; it fails safe and the workaround (use Edit/Write) is obvious, so no change. The Contract's "never extend a timeout to make a test pass" was briefly ambiguous when a harness timeout was extended to fix a harness race rather than to pass a test; judged not worth extra words. Python left out of the lint hook: `uv run ruff check` on one file costs 183 ms, almost entirely `uv run` resolving the environment.

**Defects fixed in passing.** `format-on-edit.py` ran `rustfmt --edition 2021` against an edition-2024 crate, so it wrote files `cargo fmt --check` then rejected — an auto-formatter that disagrees with the gate is worse than no formatter. `ruff` 0.16 formats Python inside Markdown, which would silently rewrite third-party code quoted verbatim in research documents; `docs/` is now excluded, and the general rule is that a formatter must never rewrite a quotation.

**Status.** `CLAUDE.md` failure classes: `unproven` → `validated ×1`. The rest of `CLAUDE.md` survived the phase unchanged apart from the amendments above. `playtest-brief`, `playtest-ingest` and `retro` remain `unproven` — `retro` has now had one use, this entry.
