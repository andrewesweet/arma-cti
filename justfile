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
check: check-commits check-generated check-adr check-markers check-sqf check-python check-rust

# Export what SQF cannot read from an authored file. The map manifests are not
# here: the addon ships and parses the authored JSON itself (ADR-0017), so
# there is nothing to regenerate. The Command Port schema lives in Python, so
# it still has to be written out.
generate:
    uv run python tools/export_command_schema.py

# A stale export is a schema_stale failure, never a silent divergence.
check-generated:
    uv run python tools/export_command_schema.py --check

# Conventional Commits (ADR-0010).
check-commits:
    cog check

# ADR-0019's form requirements on a delegated decision: it states what evidence
# would overturn it, and it carries the human's review-state line (#137).
check-adr:
    uv run python tools/check_adr_form.py

# A `validated ×N` marker must not narrate a use its own count does not reach
# (#186). CLAUDE.md's exemplar lists are out of scope — the reason is at the
# checker, under UNCOUNTABLE.
check-markers:
    uv run python tools/check_validated_markers.py

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

# pytest over the daemon and tooling. Parallel by default: `-n auto` lives in
# pyproject's addopts (#197), because the number belongs to the suite rather than
# to this recipe — a bare `uv run pytest` gets it too. Nothing here changed but
# the wall clock; the assertions and their count are the same.
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
#
# Under the tier lock like every other recipe that brings the tier up: it stages
# with `rm -rf` into the one server install and binds the one port range, so a
# hand run beside a locked `just regress` is exactly the collision the lock
# exists to stop (#68).
spike: build-shim build-addon
    ./spike/tier-lock.sh --label "just spike" -- ./spike/run.sh

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
    # Under slot 0's lock, which tier-lock.sh takes (ADR-0028): a hand run uses
    # the install and port block that *are* slot 0, a pool run holds every slot
    # it is using, and so `just probe` and `just regress` exclude each other
    # exactly where they would collide.
    CTI_MISSION=cti.Stratis \
        CTI_SERVER_CONFIG="{{ justfile_directory() }}/spike/phase1.cfg" \
        CTI_LOG_PREFIX=CTI \
        CTI_HOLD_TIMEOUT="{{ hold }}" \
        CTI_HARNESS_EXTRA="{{ file }}" \
        CTI_HARNESS_AWAIT="$(if [[ -n "{{ file }}" ]]; then echo probe_done; fi)" \
        ./spike/tier-lock.sh --label "just probe {{ file }}" -- ./spike/run.sh --hold

# Arma tier: the in-game regression suite (#23, ADR-0016, docs/regression-tier.md).
# No arguments runs the whole corpus in spike/probes/; names run a subset while
# iterating. Fresh world per probe, one typed verdict per probe from the
# CLAUDE.md failure-class table, worst class as the exit code.
#
# `--issues 28` adds every probe whose `issues:` header names 28 — provenance,
# not blast radius, so it is not a gate for the issue you are on. A filter that
# matches no probe is an error, never an empty pass. `--list` prints the
# selection and runs nothing: no lock, no port, no world.
#
# Each probe declares its own deadline in a `window:` header and the run waits on
# that probe's own completion line, so a probe that finishes early ends early.
# The corpus takes no environment variables: what a probe's world needs is in its
# `env:` header.
#
# Runs across a pool of slots (#47, ADR-0028). A slot is a port block, a daemon,
# a server install, an engine profile and a world that agree; `--slots <n>`
# chooses how many and defaults to 3. `--slots 1` is the serial tier — slot 0 is
# ~/arma3server on 2402-2406, which is the install and the port block this tier
# has always used — so the fast path and the known-correct path are one code path
# at different N. Slots are taken non-blocking in index order and fewer than
# asked for is a smaller pool rather than a failure; no slot free at all is
# infra_unavailable and never a result, with `--wait <secs>` bounding a queue.
# `just probe` and `just spike` take slot 0, which is what
# makes a hand run and a pool run exclude each other where they would collide.
#
# The probes that drive the headed Windows client run last and serially, with
# the rest of the pool drained: there is one Windows host, and the guard that
# protects the human's play session cannot tell our client from theirs (#119).
#
# Evidence, including the probe as staged, lands in ~/.arma-cti/runs/ per probe,
# with the pool's own schedule, RAM trace and merged verdict set beside it in
# ~/.arma-cti/runs/<stamp>-pool/.
regress *args: build-shim build-addon
    ./spike/regress.sh {{ args }}

# Everything that does not need Arma.
fast: check unit

# The worktree protocol as one call (#214, ADR-0049): fetch, create off
# origin/main detached, and prove the tree is exclusively yours before you work
# in it — CLAUDE.md's pre-flight, run the same way every time rather than
# improvised from memory. #105 is why: worktree assignment handed two agents one
# tree five times in one evening, and a routine reset is what turns that
# collision into destroyed work.
#
#   just worktree add issue-214    fetch, create .claude/worktrees/issue-214,
#                                  pre-flight it, print the path and base SHA
#   just worktree check [name]     the pre-flight alone (default: this tree),
#                                  non-destructive, safe to run mid-task. Only a
#                                  clean tree proves exclusivity; a dirty one
#                                  comes back `unverified` with the files listed,
#                                  because your file and another agent's look
#                                  identical in `git status`
#   just worktree list             the hygiene sweep: every registration, its
#                                  state, its unlanded count, which are stale
#   just worktree done issue-214   verify clean and landed, then remove
#
# Refusals are named and each says what was found and what to do:
# worktree_occupied (naming the other holder), dirty_tree, unverified,
# stale_registration, unlanded_work, no_such_worktree, invalid_name, git_failed. Nothing here
# resets, cleans, prunes or removes on a refusal path — foreign files mean stop
# and report, and the judgement of what a refusal means stays the agent's.
worktree action="check" name="":
    uv run python tools/worktree.py {{ action }} "{{ name }}"

# Arm a detached watcher over a dispatched agent's run, and read what the
# watchers found (#198, ADR-0053). No Arma, no lock, no turn held open.
#
# This is a correctness mechanism, not a token fix (#195, #203,
# docs/research/token-efficiency.md): it stops a dispatch being lost. `just
# watch` returns at once, having forked a poll loop nobody is billed for —
# that part is real and it is the good part. But the agent it eventually
# prods still pays the measured ~161,000-token cache rebuild in full, because
# the five-minute subagent TTL has already expired by the time the prod
# lands; orchestrator prods measure 2.32% of everything this project has been
# billed, across 54 events, and watching does not save that.
# `just watch-report` is the whole of the read.
#
# `subject` is what finishing means: `pool` (the newest `pool.json` written
# after arming), `probe:<name>`, `process` with `--pid`, or `path` with
# `--await-path`. Options pass through to tools/stall-watch.sh: `--grace`
# (silence before a stall is called, default 600s), `--deadline`, `--issue`,
# `--interval`, `--runs-dir`, `--activity`. Write an issue as `--issue 198`,
# without the `#`: a recipe body is shell, where `#` opens a comment.
#
# The watcher never messages the agent. It writes one line under
# ~/.arma-cti/watch/ and stands down; prodding stays a judgement, and an
# `infra_unavailable` run is reported as the stop it is, never retried.
watch name worktree subject="pool" *args:
    ./tools/stall-watch.sh arm --name "{{ name }}" --worktree "{{ worktree }}" \
        --subject "{{ subject }}" {{ args }}

# One line per un-acknowledged finding, and nothing at all while every watched
# agent is still working. `--ack` marks what it prints as read so the same
# stall never resurfaces as news; `--all` re-reads the acknowledged ones.
watch-report *args:
    uv run python tools/stall_watch.py report {{ args }}

# Print an issue's newest handoff comment, and nothing else (#210,
# docs/agents/handoff.md). A continuation's first read.
#
# `gh issue view --comments` returns the whole thread, and everything a
# successor reads on turn 1 is billed about 12.55× over a median agent's life
# (#208, docs/research/continuation-economics.md): fetching a 1,500-character
# handoff by reading a 40,000-character thread defeats the point of having
# written one. This prints the matched comment body alone — no thread, no
# metadata beyond what the handoff itself carries.
#
# A thread with no handoff is a non-zero exit with a message, never a silent
# empty print, which would read as "no state to carry" when it may mean "wrong
# issue number" (#168/#183). Exit 1 is "this issue carries no handoff"; exit 3
# is "I could not look", which is not a result.
#
# It reads. There is no `just handoff-write`: authoring is prose against the
# template in docs/agents/handoff.md, and the fields worth having — what was
# ruled out, what is unverified — are the ones no form can fill in.
#
# `@`, alone among the recipes here: the echoed command line is one more thing
# the reader did not ask for, in the one recipe whose whole purpose is that
# nothing but the handoff reaches a context window.
handoff issue:
    @uv run python tools/handoff_fetch.py {{ issue }}

# Read a finished corpus run's own record as the lines a close quotes (#199).
# No Arma, no lock: it reads `pool.json` and the per-probe `verdict.json`s and
# renders. `just verdict` takes the newest pool on this machine; name a pool
# evidence directory (or its pool.json) to read an older one.
#
# What it prints is the whole of the read — worst class, counts, wall, sha and
# tree state, the runner's own per-probe block verbatim, and a detail line per
# non-pass probe — so reading a corpus result is one tool call on one file
# rather than a directory crawl, and quoting it verbatim is safe by
# construction. #134 once quoted a "full corpus 20/20" banner before any tool
# result contained one, every figure matching by luck; a rendered quote cannot
# be hallucinated. It matters because the prune deletes passes, so pass
# evidence outlives its own directory only in the quote.
#
# It reads and it renders. Nothing is posted: what a red means, and what the
# run gates, stay the agent's (the failure-class table's required-response
# column). `infra_unavailable` is printed as the stop it is, never interpreted.
verdict pool="":
    uv run python tools/pool_comment.py {{ pool }}
