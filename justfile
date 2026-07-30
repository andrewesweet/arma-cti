# arma-cti task surface. See CLAUDE.md for when to run which tier.
# Strictness principle: every tool runs in its strictest practical mode and
# warnings are errors.

set shell := ["bash", "-euo", "pipefail", "-c"]

shim := "--manifest-path extension/Cargo.toml"

_default:
    @just --list

# No-Arma static tier: commit hygiene, lints, types, formatting.
check: check-commits check-sqf check-python check-rust

# Conventional Commits (ADR-0010).
check-commits:
    cog check

# -p adds the pedantic lints; -e makes findings fatal (without it the gate is a no-op).
check-sqf:
    hemtt check -p -e

# Python lint, format check and type check.
check-python:
    uv run ruff check .
    uv run ruff format --check .
    uv run ty check

# Rust format check and clippy.
check-rust:
    cargo fmt {{shim}} --check
    cargo clippy {{shim}} --all-targets --all-features -- -D warnings

# No-Arma unit tier.
unit: unit-python unit-rust

# pytest over the daemon and tooling.
unit-python:
    uv run pytest

# cargo test over the extension shim.
unit-rust:
    cargo test {{shim}}

# Build every artefact the Arma tiers need. A green check does not imply a green build.
build: build-addon build-shim build-missions

# HEMTT addon PBOs.
build-addon:
    hemtt build

# Linux shim .so.
build-shim:
    cargo build {{shim}} --release

# Cross-compiled Windows shim .dll for play sessions. Needs clang and cargo-xwin.
build-shim-windows:
    XWIN_ACCEPT_LICENSE=1 cargo xwin build {{shim}} --release --target x86_64-pc-windows-msvc

# Pack each mission folder into a PBO.
build-missions:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p .hemttout/missions
    for m in missions/*/; do
        name="$(basename "$m")"
        uv run python tools/pack_pbo.py "$m" ".hemttout/missions/${name}.pbo"
    done

# Arma tier: server + headless client + stub daemon, running the phase-0 measurements.
spike: build-shim
    ./spike/run.sh

# Everything that does not need Arma.
fast: check unit
