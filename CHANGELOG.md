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

### Fixed

- The auto-format hook ran `rustfmt` at edition 2021 against an edition 2024 crate, so it wrote
  files that `cargo fmt --check` then rejected.
