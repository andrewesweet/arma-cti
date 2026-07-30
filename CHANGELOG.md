# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Founding decisions: domain glossary, ADRs, MVP scope, and the agent development process.
- `just` command surface: `check`, `unit`, `build`, `spike`, `fast`. The no-Arma gate
  (`just check` + `just unit`) runs in under a second.
- Pinned toolchain: HEMTT, `just`, Rust with `cargo-xwin` for the Windows shim, and a
  `uv`-managed Python environment.
- HEMTT addon skeleton, with the "no bare `random` or `sleep` in SQF" contract enforced as a
  `banned_commands` lint rather than a grep.
- Rust extension shim on `arma-rs`, round-tripping opaque payloads to the Python daemon over TCP
  loopback and returning replies through `ExtensionCallback`.
- Mission PBO packer (`tools/pack_pbo.py`), since HEMTT packs addons but not missions.
- Phase-0 spike harness and its measurements: `docs/spikes/0001-phase0.md`.
- ADR-0011: the acceptance-harness architecture — Python orchestrator, in-game gtest-style SQF
  asserts, verdict returned through the extension as structured JSON. Bohemia's `-autotest` and
  SQF-VM are rejected as test tiers, with reasons recorded.
- Addon functions are declared in `CfgFunctions` and resolve by name as `cti_fnc_*` — from the
  mission, from `remoteExec` and from the addon itself. Verified on the dedicated server, which
  now loads the addon during the Arma tier.
- Real daemon (`cti-daemon`), replacing the phase-0 echo stub. Same transport the spike measured —
  newline-delimited JSON on TCP loopback, one connection reused across calls — with an envelope
  worth relying on: every request carries an id and every reply echoes it, and success, a
  domain-level rejection and an error are three outcomes the caller can tell apart. A malformed
  line costs one reply, never the connection.
- Acknowledged delivery for messages the daemon pushes to the game. Callback delivery is
  at-most-once across mission boundaries (ADR-0005), so the daemon holds each pushed message until
  the game acknowledges its sequence number and replays anything unacknowledged. Acknowledging
  twice is ordinary; acknowledging a sequence that was never issued is refused.
- Structured daemon telemetry as JSON lines, per request. Observability only, never read back as
  campaign state (ADR-0003) — which is why a failure to write it is swallowed rather than raised.
- Seeded PRNG adapter: the only sanctioned source of randomness in SQF. It wraps the engine's own
  `seed random x` rather than a hand-rolled generator, and hides both of that command's silent
  footguns — a seed truncated towards zero, and an upper bound that is included where plain
  `random`'s is excluded. A stream is `[seed, draw count]`, so it survives a snapshot and resumes
  where it left off. Determinism, both footguns, the integer range and serial independence are
  asserted against the live engine, not assumed.

### Changed

- ADR-0006 is now accepted unconditionally: the phase-0 contingency is discharged, and the ADR
  absorbs the spike's constraints (port range 2402–2406, missions as PBOs, no RPT file on a Linux
  server) plus a version-parity policy for when Arma 2.22 ships.
- ADR-0004 and ADR-0005 amended with measured constraints: the shim keeps one persistent TCP
  connection (~3× faster than per-call connects), and nothing in the Command Port may require
  sub-frame push latency, because `ExtensionCallback` is frame-bound at 8–17 ms.
- ADR-0004, ADR-0005 and ADR-0006 amended with engine limits found by cross-referencing phase 0
  against the full wiki snapshot: a `callExtension` return is capped at 10,240 bytes (chunking
  needed before snapshot save/load), a blocking call stalls the frame and warns at 1000 ms, the
  callback path drains at most 100 messages per frame and is at-most-once across mission
  boundaries, and 2.22 changes the extension error surface — prime `engine_drift` suspect on
  update.

- `just` command table in `CLAUDE.md` now lists the recipes that exist; the acceptance tiers are
  marked as Phase 1 work.
- *Read first* in `CLAUDE.md` now explains how to navigate the wiki snapshot: guessable paths,
  `MANIFEST.json` as the lookup, per-directory `INDEX.md` instead of listing a 2,672-file
  directory, and the two traps — categories live in the file header rather than the wikitext, and
  pre-Arma-3-only pages are excluded, so a miss is not proof the wiki lacks the page.
- Vendored snapshot of the Bohemia wiki (`docs/reference/arma-wiki/`), because the live wiki is
  unreachable from this project's environment and Arma 3 has been static at 2.20 for over a year.
  Now the whole wiki rather than nine hand-picked pages: 6,690 pages across scripting commands,
  functions, engine topics, class-name tables and the templates needed to read `{{RV}}` markup.
  Pages are bucketed by subject at predictable paths (`commands/setDamage.wiki`), each carries its
  categories in the header — they are template-generated, so grepping the wikitext finds none —
  and `MANIFEST.json` is the authoritative title-to-file lookup plus the redirect alias map.
- Lint-after-edit hook enabled for SQF, config and Rust edits — advisory only; `just check`
  remains the gate.
- The "no bare `random`" contract is now enforced by `tools/check_sqf_bans.py`, which allows the
  command in the seeded PRNG adapter and nowhere else. HEMTT's `banned_commands` lint is
  all-or-nothing and HEMTT 1.20.1 has no file-scoped suppression, so `random` is exempted there
  and re-banned here with the scope the contract actually wants. `sleep` and `uiSleep` stay banned
  by both.

### Removed

- Phase-0 stub daemon and its test. It echoed requests with timestamps and had no request
  identity, error vocabulary or delivery guarantees; the real daemon supersedes it.

### Fixed

- A headless client never entered the mission: its `HeadlessClient_F` slot had no `name`, and an
  unnamed slot is never assigned.
- The auto-format hook ran `rustfmt` at edition 2021 against an edition 2024 crate, so it wrote
  files that `cargo fmt --check` then rejected.
