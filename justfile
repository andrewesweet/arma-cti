# arma-cti task surface. See CLAUDE.md for when to run which tier.
# Strictness principle: every tool runs in its strictest practical mode and
# warnings are errors.

set shell := ["bash", "-euo", "pipefail", "-c"]

# rustup installs to ~/.cargo/bin, which a non-login shell here does not have on
# PATH — so every `cargo` step failed unless the caller exported it first. Put it
# on the tail: a cargo already on PATH still wins, and the toolchain is pinned by
# rust-toolchain.toml either way.
export PATH := env_var('PATH') + ":" + env_var('HOME') + "/.cargo/bin"

shim := "--manifest-path extension/Cargo.toml"

_default:
    @just --list

# No-Arma static tier: commit hygiene, lints, types, formatting.
check: check-commits check-generated check-sqf check-python check-rust

# Regenerate everything derived from authored data.
generate:
    uv run python tools/generate_manifest_sqf.py
    uv run python tools/generate_command_sqf.py

# A stale generated file is a schema_stale failure, never a silent divergence.
check-generated:
    uv run python tools/generate_manifest_sqf.py --check
    uv run python tools/generate_command_sqf.py --check

# Conventional Commits (ADR-0010).
check-commits:
    cog check

# -p adds the pedantic lints; -e makes findings fatal (without it the gate is a no-op).
# The second step is the scoping HEMTT's banned_commands lint cannot express:
# `random` in the seeded PRNG adapter and nowhere else.
check-sqf:
    hemtt check -p -e
    uv run python tools/check_sqf_bans.py

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
# The addon is a launch dependency now that the mission resolves cti_fnc_* by name.
spike: build-shim build-addon
    ./spike/run.sh

# Arma tier: bring the Phase-1 world up and hold it, so a one-off probe or a
# human client can exercise it. The probe is appended to the generated harness
# rather than shipped in the mission — but it lives in spike/probes/ rather than
# in a session's scratchpad, so the evidence a verification rests on outlives the
# session that wrote it. No probe named: the world comes up bare.
#
# A probe must end by logging a line containing `probe_done`, because the run
# waits for it: a probe still working when the hold window closes is a timeout,
# not a pass.
#
# `CTI_AI_SIDE=WEST` brings the daemon up with that side under an AI Commander
# (#16), and `CTI_AI_SEED` fixes what it plays like. Off by default, so a world
# brought up for a human Commander is not quietly being played by one.
#
# `hold` is the window, and a probe whose subject genuinely takes longer than the
# default may raise it — `just probe spike/probes/contact-decay.sqf 300` waits out
# the engine's 120 s knowledge decay, which no shorter window can contain. State
# the reason in the probe's own header, because the distinction that matters is
# the one the failure-class table draws: sizing the window to what is being
# measured is not the same as extending a timeout until a flaky probe passes, and
# only the first is allowed. A probe that fails at 150 s and passes at 300 s
# without its subject having grown that long is a synchronisation bug to fix.
probe file="" hold="150": build-shim build-addon
    #!/usr/bin/env bash
    set -euo pipefail
    CTI_MISSION=cti.Stratis \
        CTI_SERVER_CONFIG="{{ justfile_directory() }}/spike/phase1.cfg" \
        CTI_LOG_PREFIX=CTI \
        CTI_HOLD_TIMEOUT="{{ hold }}" \
        CTI_HARNESS_EXTRA="{{ file }}" \
        CTI_HARNESS_AWAIT="$([[ -n "{{ file }}" ]] && echo probe_done || true)" \
        ./spike/run.sh --hold

# Everything that does not need Arma.
fast: check unit
