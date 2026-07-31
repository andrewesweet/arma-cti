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

## 2026-07-30 — retro: ad-hoc, Phase 1 (#9-#12)

Trigger: user-directed, on discovering `toJSON`/`fromJSON`.

**Findings.** *Read first* told an agent to consult the wiki "before experimenting on engine behaviour". That is a narrower trigger than it reads: the expensive miss this phase was not an experiment but an assumption. SQF was assumed to have no JSON parser, so `tools/generate_manifest_sqf.py` and `tools/generate_command_sqf.py` were built to render authored data into SQF literals — while `toJSON`/`fromJSON` had been engine-native since 2.18 and the server runs 2.20. The wiki was consulted repeatedly and correctly this phase (`random` syntax 3, `getUserInfo`, `CfgFunctions`, `loadFile`), so the instruction works when it fires; it simply did not fire for "does this already exist". Same shape, second instance: `skipLobby = 1` — the fix that made the headed client join unattended — was documented all along and sat on a closed issue's eliminated list.

**Applied** (human-requested): *Read first* now says to check the wiki before experimenting on engine behaviour **and before writing your own version of anything the engine might already do**, with the generator as the second worked example beside Phase 0's lost day.

**Also applied, on sign-off.** A *Working style* line that an elimination holds only in the context it was tested in — `skipLobby` was written off against a server whose mission was not initialised, and against one that was, it worked first time. And the failure-class table goes `validated ×1` → `×2`: a deliberately emptied manifest produced `assertion_failed` in-world and the harness refused to pass rather than booting an empty world, which is the second time the table earned its keep.

**Issues raised rather than fixed here.** #22 (replace the generated-SQF pipeline with `loadFile` + `fromJSON`; flagged ADR-0012-adjacent), #21 (exercise the client-to-gateway leg, blocked by #18).

**Status.** `retro` has now had two uses and has not needed amending; still `unproven` pending a use that tests it rather than exercising it.

## 2026-07-31 — retro: ad-hoc, after #27

Trigger: user-directed, after the per-side Observation projection landed.

**Findings.** The dominant one is a convention nobody followed, including the agent that wrote the convention's last amendment. `CLAUDE.md` says to interact with the project through `just` only, and the Phase-1 in-world tier has no recipe — `just spike` runs the phase-0 measurement mission. So both #15 and #27 were verified in-world by calling `./spike/run.sh --hold` directly with five environment variables. For #27 that invocation was reconstructed by reading the script and a *leftover* `.spike-out/mission/cti.Stratis/harness.sqf` staged by the previous session — a file the harness rewrites every run, so the reconstruction was luck. Second half of the same gap: #27's probe lived in the session scratchpad, so the issue carries its output and not its source, and re-verifying would mean rewriting it. Secondary: `git push origin main` from an agent worktree was rejected non-fast-forward, because it pushes the local `main` branch the worktree is not on; the correct sequence was undocumented. `cargo` is not on `PATH` in a default shell here, so every gate call this session carried a manual `export`, knowledge that travelled by handoff document rather than by the repo. And `/grill-me` was missing from the workflow backbone despite having driven both major design decisions to date.

**Applied** (all human-approved): `CLAUDE.md` gains `/grill-me` in the workflow backbone, a *Commits* bullet giving the worktree landing sequence, and a command-table row for `just probe` — added with the recipe rather than ahead of it, since a table listing recipes that do not exist is the defect the Phase 0 retro fixed. `.claude/skills/retro` goes `unproven` → `validated ×3`.

**Fixed rather than deferred** (#29, #30, both closed here): `just probe [file] [hold]` wraps the Phase-1 tier; `spike/probes/` holds probes in the repo, so the evidence a verification rests on outlives the session that wrote it; the justfile puts `~/.cargo/bin` on `PATH`. Building them turned up a false-green the retro had not: hold mode read its verdict when the hold window closed, so a probe still working at that moment reported `HOLD-COMPLETE` off a log it had not finished writing. `CTI_HARNESS_AWAIT` now waits for the probe's own completion line, with `FAIL` ending the wait too so an assertion is classified as one rather than timing out. Proven by running the #27 probe under a 60-second hold it outlives.

**Rejected / no change.** A rule about preserving probe source alongside its evidence: real, but it dissolves once `spike/probes/` exists, and a rule duplicating a tool is the over-prescription this skill warns against. A rule about editor diagnostics: `ty` in-editor contradicted the gate repeatedly this session (`EconomyTable has no attribute capture_seconds` and two others) while `just check` passed, and the gate was treated as authoritative without needing to be told — *"The gates above are this project's verification"* already covers it.

**Status.** `.claude/skills/retro`: `unproven` → `validated ×3`. Failure classes stay `validated ×2` — `assertion_failed` was wired into the #27 probe but never fired, so nothing new was earned. `playtest-brief` and `playtest-ingest` remain `unproven` and unused.
