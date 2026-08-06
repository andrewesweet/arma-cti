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

# No-Arma static tier: commit hygiene, lints, types, formatting, secrets.
check: check-commits check-generated check-adr check-markers check-conflicts check-sqf check-secrets check-python check-rust

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

# No git conflict marker reaches a tracked file (#231, ADR-0062). One landed
# twice and the second landing cut 1,669 changelog lines resolving against it,
# so a marker in the base is a trap for the next agent rather than untidiness.
# `tools/land.py` refuses on the same finding by name, before the gate runs.
check-conflicts:
    uv run python tools/check_conflict_markers.py

# -p adds the pedantic lints; -e makes findings fatal (without it the gate is a no-op).
# The second step is the scoping HEMTT's banned_commands lint cannot express:
# `random` in the seeded PRNG adapter and nowhere else.
check-sqf:
    hemtt check -p -e
    uv run python tools/check_sqf_bans.py

# No credential reaches a committed file (#221's secrets ruling, #223).
#
# `dir` rather than `git`: the subject is the tree that is about to be
# committed, and on a detached worktree `gitleaks git` reports "0 commits
# scanned" — a gate that quietly scans nothing is the #41 shape, and a green
# from it would mean less than no gate at all. History is scanned by the same
# binary on demand when a leak is suspected, not on every edit.
#
# `--redact` because a finding is printed into whatever log the gate ran in,
# and a secrets gate that prints the secret has moved it rather than caught it.
#
# The stated limit from #221 is unchanged: this protects against git, not
# against the agent, which runs as the same user. Installed user-local by
# `just prereqs tools` (#230); a missing binary is a loud non-zero here, never
# a skip.
check-secrets:
    gitleaks dir . --no-banner --redact

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

# Every test module this landing adds or rewrites has to notice its subject
# changing (#239, ADR-0064). A bounded sample of mutants is planted in the source
# those tests actually execute — chosen by one `coverage.py` pass, not by the
# `test_x.py` -> `x.py` naming convention — and each is judged by only the tests
# that reach its line. A module whose tests kill fewer than the floor is red, and
# so is one none of whose tests execute a line of this repo's source at all,
# which is what an `assert True` module earns.
#
#   just mutation                          the diff against origin/main, as `fast` runs it
#   just mutation --paths tests/unit/x.py  one module, while writing it
#   just mutation --report                 survey: every verdict, never a red
#
# There is no flag that lowers the floor in `just fast`, and no marker a test
# file can carry to excuse itself. The one escape is `NO_PYTHON_SUBJECT` in
# `tools/mutation_smoke.py` — a named module with its reason beside it, visible
# in the diff — for the modules whose subject is a shell script or an authored
# document rather than Python.
mutation *args:
    uv run python tools/mutation_smoke.py {{ args }}

# Everything that does not need Arma. `mutation` runs last: a red suite says
# nothing about mutants, and the smoke refuses rather than guesses when the
# module it is asked about is not green on its own.
fast: check unit mutation

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

# The landing protocol as one call (#213, ADR-0049): fetch, rebase onto
# origin/main, re-gate, `git push origin HEAD:main`, then fast-forward the main
# checkout. The protocol CLAUDE.md's Commits section states in prose, run the
# same way every time — #209 measured 220 hand calls doing it across 117 of 214
# agents, and its documented traps exist because agents kept falling into them.
#
#   just land              the whole protocol, gate included
#   just land --dry-run    the plan, having run nothing at all
#
# Three things it does that prose could not. The refspec is a constant no
# argument reaches, so `git push origin main` — which pushes the local `main`
# branch a detached worktree is not on — cannot be typed here. The gate is
# *inside* the protocol: `just fast` runs after the rebase, on every landing
# that pushes anything, and there is no `--no-gate`, which would be a gate
# bypass wearing a convenience wrapper. And the ff-only merge into the main
# checkout is no longer skippable in silence: when it does not run, the exit is
# non-zero and one line names the exact command the orchestrator must run —
# `grep '^merge_command='`. A stale main checkout is where ADR-0042's stale-hook
# window comes from (#130).
#
# Refusals are named, each says what was found and what to do, and the exit code
# separates the two kinds: 1 is nothing landed (dirty_tree, nothing_to_land,
# rebase_conflict, gate_red, gate_blocked, not_fast_forward, git_failed), 2 is
# the work IS on origin/main and a step is outstanding
# (merge_blocked_by_sandbox, merge_not_fast_forward). Nothing here resolves,
# aborts, resets or tidies on a refusal path.
land *args:
    uv run python tools/land.py {{ args }}

# Start a logical subagent as a separate process on a named lane, and return at
# once with a dispatch id (#223, ADR-0061). No Arma, no lock, no turn held open.
#
#   just dispatch --lane claude-native --profile opus-high --seat implementer --issue 223
#   just dispatch --list                        the registry: lanes, profiles, seats
#   just dispatch --dry-run ...                 the plan and the child's environment,
#                                               credential redacted, nothing launched
#   just dispatch --readiness --issue 241       is this issue ready to be worked on?
#                                               nothing is dispatched either way
#
# `--lane` picks the runner and the environment that reaches a provider;
# `--profile` is one opaque `(lane, model, effort)` token, because effort
# vocabularies do not commensurate across providers (ADR-0061 Decision 5), so
# there is deliberately no `--model` and no `--effort` here. `--seat` carries
# Decision 2's eligibility: a foreign lane refuses the seats no mechanical gate
# covers. `--issue` is both the assignment and a telemetry attribute.
#
# Options: `--worktree` (default `.claude/worktrees/issue-<N>`, which is what
# `just worktree add` makes and which this recipe never creates for itself),
# `--brief-file`, `--base-sha`, `--permission-mode` (default `acceptEdits`; a
# seat that needs Bash passes something wider deliberately), `--dispatch-dir`,
# `--credentials`, `--issue-body` (read the body from a file rather than from
# `gh` — how triage checks a draft before filing one).
#
# The issue is read before anything is planned, and one that states no criteria
# is refused (#241). Definition of ready, mechanically: criteria must exist, and
# something in the body must name the gate, test, verdict or artefact that would
# settle them. Measured against the last twenty dispatched issues, both of those
# refused none of them. A third sub-check — can the criteria be counted off? —
# refused three, all ruling executions and defect repairs whose criteria are a
# ruling transcribed rather than a checklist, so it reports and never blocks.
# The remedy on a refusal is an edit to the issue by a human or by triage; the
# tool will not rewrite an issue it is judging, and there is no override flag.
# The rung is lane-blind: a foreign lane meets exactly what `claude-native` does.
#
# The environment is assembled per invocation and exported nowhere:
# `ANTHROPIC_BASE_URL` in a profile or in `~/.claude/settings.json` would
# redirect every Claude Code session on this box, the orchestrator included.
# Credentials come from `~/.arma-cti/credentials.env` at mode 0600, by
# environment only — never on argv, so never in `ps`, and never in the dispatch
# record, which names the key it used and not its value.
#
# The dispatched process asserts `git rev-parse --show-toplevel` against its
# assignment before the runner starts and refuses loudly on a mismatch (#105).
# A lane that cannot be reached — no credentials file, no key, no worktree — is
# `infra_unavailable` and is not a result.
#
# The `zai` lane dispatches only in off-peak hours, on the human's ruling of
# 2026-08-05 (#238). Inside z.ai's published peak band every dispatch to it is
# refused, with the window, the terms it came from, and when it next opens.
# The refusal carries no failure class: nothing was found about any provider or
# any code, this project simply declined to spend on that lane now. There is no
# override — no flag, no environment variable — because the rule is the human's
# and only they amend it; `just breaker state` shows the window, and
# `just dispatch --list` shows which lanes carry the ruling.
#
# Evidence lands in `~/.arma-cti/dispatches/<id>/`: `dispatch.json`, the brief
# as sent, `dispatch.log`, and `result.json` when the run ends.
dispatch *args:
    ./tools/dispatch.sh {{ args }}

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
#
# The lane breakers report here too (#226), ahead of the watchers, because this
# is the read CLAUDE.md already puts at the top of an orchestrator's turn. One
# verdict line per lane that is not dispatchable, and silence for every lane
# that is — a verdict, never three percentages (#209). `{{ args }}` is the
# watchers' alone; the breaker read takes none. Since neither half can be pointed
# by a flag the other would swallow, both take a directory from the environment
# instead — `CTI_BREAKER_DIR` and `CTI_WATCH_DIR` (#249), which is how a unit test
# exercises this recipe without its verdict depending on what the box is carrying.
watch-report *args:
    uv run python tools/breaker.py report
    uv run python tools/stall_watch.py report {{ args }}
    # The orchestration-seat trial (#260): one line when it has failed, silent while clean.
    # Not a gate — it reports — and it reads `CTI_ADMISSION_DIR`, the same seam the records use.
    uv run python tools/admission.py trial-report

# The recovery runbook's two computable procedures (#253, orchestration-design §4).
# No Arma, no lock, no turn held open; both verbs are reads and neither writes
# anything anywhere.
#
#   just recover check <name>        resolve one BLIND watcher finding
#   just recover brief <issue|name>  the resumption briefing's computable halves
#
# `check` mechanises the by-hand look `docs/agents/recovery.md` describes, which
# the twenty-fourth and twenty-fifth retros both ran by hand — the two identical
# saves that document sets as its own codification threshold. Verdicts:
# `lost_work` (naming the commits and their files), `still_live`,
# `finished_and_cleaned`, and `unproven` when the look did not resolve. Every one
# carries the reading that forced it, and `finished_and_cleaned` off an absent
# tree also prints what that evidence cannot exclude — a tree deleted while
# carrying unlanded commits reads identically from outside.
#
# **It acks nothing.** `just watch-report --ack` stays the judgement (ADR-0053:
# the machine's half ends at noticing), and nothing here resets, prunes or
# removes. It reads the watch findings through `CTI_WATCH_DIR`, the seam #249
# landed, so a unit test exercises it without touching what the box is carrying.
#
# `brief` computes reconstructions 1 and 2 of the three
# `docs/agents/recovery.md` requires — what moved on origin/main since the dead
# agent's last commit, and what of its own environment died — and prints
# reconstruction 3's heading with nothing under it, because which assumptions no
# longer hold is judgement. `just handoff <issue>`'s own output is printed
# beside them, including its "no handoff" message, which is an answer rather
# than silence. The words *landed* and *lost* appear nowhere in it: a commit is
# on origin/main or it is not, and which of those the work **is** is the resumed
# agent's to verify on wake.
recover *args:
    uv run python tools/recovery.py {{ args }}

# Read and feed the lane circuit breakers (#226, ADR-0061 Decisions 7 and 8).
# No Arma, no lock, no turn held open.
#
#   just breaker report      one line per lane that is not dispatchable; silent otherwise
#   just breaker state       every lane, with its streaks, its feed, and its window
#   just breaker check --lane zai            the pre-dispatch read, as an exit code
#   just breaker estimate --tier pro         z.ai's ledger estimate, advisory only
#   just breaker reset --lane zai --force    clear a quality trip by hand
#
# Two trip families, and they behave differently on purpose. **Availability**
# trips when a provider says it is out of quota, and reopens at that provider's
# own published window boundary — computed, never guessed, which is why
# `quota_exhausted` is its own failure class rather than `infra_unavailable`.
# **Quality** trips on three consecutive gate failures or refusals on a lane,
# refuses with `provider_refused`, and does not reset on a timer at all: time
# does not fix a provider that swapped the model behind a name, so it escalates
# and a human clears it. A third case — three consecutive provider errors with
# no published reset — opens the lane and *holds* it, because inventing a
# cooldown there is the defect that disqualified LiteLLM as this breaker.
#
# `just dispatch` reads the state before it plans anything, so a tripped lane
# costs nothing to discover. Feeds: the Claude status-line tap (`just prereqs
# statusline`, #230) and Codex's `account/rateLimits/read` are first-party and
# may trip a lane; z.ai publishes nothing machine-readable, so its estimate is
# advisory only and that lane is 429-reactive. `just breaker state` says which
# lanes are in that degraded mode.
#
# It also states each lane's published time-of-day window and which band the
# clock is in (#238). The breaker does not enforce that window — it trips on
# failures, and the off-peak rule is policy, refused by `just dispatch` — but a
# dispatcher refused by that rule reads this print next, so `dispatch=allowed`
# here means only that this breaker has nothing against the lane.
#
# Every transition goes to OTel and to `~/.arma-cti/breaker/transitions.jsonl`.
breaker *args:
    uv run python tools/breaker.py {{ args }}

# The dispatch queue as data: the human's freeze, WIP limit and carve-outs in a
# file a running session reads (#250, ADR-0049). No Arma, no lock, no turn held
# open. Design: docs/orchestration-design.md §2.
#
#   just queue state                     every entry with its ruling, the in-flight list, the count
#   just queue next [--count N]          the next dispatchable issue(s) with the derivation
#   just queue check --issue N           one issue, as an exit code — the pre-dispatch read
#   just queue freeze --ruling "..."     record a freeze
#   just queue open   --ruling "..."     record it lifting
#   just queue wip --limit 3 --ruling "..."
#   just queue package add --name "..." --issues 221-230 --exempt-freeze --reserve 2 --ruling "..."
#   just queue package drop --name "..." --ruling "..."
#
# The queue is a **derived view**, not a copy of the tracker: candidates come from
# `gh issue list --label ready-for-agent` live, in-flight is derived from the box,
# and the file carries only what GitHub cannot — the freeze, the carve-out
# packages, the WIP limit and the reservations, which are the human's rulings and
# live nowhere machine-readable today.
#
# **Every entry quotes the ruling it came from and a write without `--ruling` is
# refused**, which is `just admission record`'s no-default discipline applied to the
# one surface whose scheduling rules have no provenance. The file is never
# hand-edited: an unknown key, a missing ruling or a malformed entry refuses
# `policy_invalid`, and an absent file refuses `policy_absent` rather than reading
# as open — a policy nobody can read is not a policy that permits.
#
# `just dispatch` reads `check` before it plans anything, below the readiness
# rung and above the admission bar, the breaker and the off-peak rule — readiness
# first because an unready issue can be made ready this minute, and a freeze is
# the one refusal whose remedy only the human can start. That is the point of the
# whole file: a
# freeze read **per dispatch** reaches an orchestrator session already running,
# which a freeze recorded on an issue and in memory does not (ADR-0042's stale-copy
# window, one level up; the human's caveat on #217, 2026-08-05T17:12Z). There is no
# flag and no environment variable that dispatches through it, because the freeze is
# the human's and only they amend it, and the refusal **carries no failure class** —
# nothing was found about any provider, any lane or any code.
#
# The in-flight count is a **floor** and the tool says so by printing the list it
# derived: `issue-<N>` worktrees plus dispatch records with no `result.json`, union
# by issue, minus what GitHub reports closed (reported separately as `just worktree
# done` owed). `agent-<hex>` trees are excluded by name — 93 registrations against 6
# dispatch records, measured for #242 — so neither source alone is a WIP signal.
#
# **It selects and prints; it never dispatches** (ADR-0053), the same reason
# `just watch` never messages the agent it watched.
#
# Refusals: dispatch_frozen, wip_reached, surface_conflict, no_ready_issue,
# policy_invalid, policy_absent, ruling_required.
#
# `[positional-arguments]` rather than `{{ args }}`: a ruling is a sentence with
# spaces in it, and `{{ args }}` splices arguments into the shell line as bare
# text, so `--ruling "human, 2026-08-05"` would arrive as three arguments. `"$@"`
# carries each one across whole, which is the difference between a policy that
# quotes its ruling and one that quotes the first word of it.
[positional-arguments]
queue *args:
    uv run python tools/queue_policy.py "$@"

# The pre-registered admission bar, as the thing that decides rather than as prose
# (#224, ADR-0061 Decision 6). No Arma, no lock, no turn held open.
#
#   just admission bar                       the bar as ruled, printed
#   just admission status                    every foreign route, and what it has accrued
#   just admission check --lane zai --profile zai-glm52-max --seat implementer
#   just admission audit --issue N           compute what a close's Part A claims can be
#   just admission record --lane … --seat … --issue N …   one issue's assessment
#   just admission reset --lane … --seat … --force        the human act after an escalation
#
# The bar is the human's ruling of 2026-08-05T20:00Z on #224, over #230's derivation
# from the 131 eligible closed issues in this repo's own history. **Part A**: four
# process criteria, every issue, ten out of ten, no allowance. **Part B**: at most one
# unclean issue in ten, where unclean is a corrective rework commit within seven days,
# a post-close finding, or a reopen. **N = 10**, and one re-run — attempts do not pool,
# and a second failure is a human's call. Recon and review are judged instead on the
# ruling's substitute: at least 90% of their findings' file-and-line citations resolve,
# pooled over ten dispatches. `just admission bar` prints all of it; nothing here
# derives a number, because a bar that moves once the numbers are in is not
# pre-registered.
#
# **Every foreign route starts at zero.** The 131 issues behind the bar are Claude's
# history, the question Decision 6 asks is absolute rather than comparative, and
# nothing is back-filled — `just admission status` says so until the first record.
#
# `record` invents nothing. Every Part A criterion is a required choice with no
# default, because a criterion nobody passed is a criterion nobody checked, and two of
# them are cross-checked against git in the refusing direction only: a landing that
# touched an in-world surface may not have its corpus criterion waived, and one that
# edited an acceptance spec or a generated file may not record the hooks as clean.
#
# `audit` computes what the rest of that assertion can be (#252). Six checks over the
# issue's closing comment — that it names a commit on `origin/main`; that the commit
# falls inside its dispatch's window, by `tools/ledger.py`'s own tests rather than a
# second copy of them; whether the landing touched an in-world surface and so owes a
# pool verdict; whether every evidence path it quotes exists and reads green; whether a
# gate block is quoted at all; and the changelog, which it refuses to decide. It reads
# the close off `gh`, or off `--close-file`. It computes, prints and cites; it records
# nothing, and it exits zero whatever it found, because a verdict here is a finding to
# read rather than a gate. Two of its answers are deliberately weak: a quoted gate block
# is `quoted` and never proof the gate ran green, since the paste is the evidence and no
# tool can re-run history; and the changelog is `undecidable` and has no input that makes
# it `ok`, because a check that could not run is not a check that passed.
#
# `record --from-audit` runs that audit and fills the two criteria it computes, leaving
# every other one a required choice with no default — so the discipline above survives
# the automation rather than being replaced by it.
#
# `just dispatch` reads the standing before it plans anything, and refuses only the
# ruling's far end: a profile that has spent both attempts. Probation dispatches
# normally, or the record could never accrue. Every state change goes to OTel and to
# `~/.arma-cti/admission/transitions.jsonl`.
admission *args:
    uv run python tools/admission.py {{ args }}

# Materialise the per-dispatch ledger from the OTel bus (#227, ADR-0061). No
# Arma, no lock, no turn held open.
#
#   just ledger-sync                        a row per dispatch, one line each
#   just ledger-sync sync --dispatch <id>   one dispatch
#   just ledger-sync show --dispatch <id>   that dispatch's row in full
#   just ledger-sync prune                  what the retention policy would delete
#   just ledger-sync prune --apply          delete it
#
# The ledger is a **view**. The collector is the only writer; this reads what it
# wrote, normalises three lanes that report the same fact three ways, types the
# dispatch's end state in ADR-0061's vocabulary, joins it to its issue and to the
# commit that landed, and writes one `ledger.json` beside the plan in
# `~/.arma-cti/dispatches/<id>/`. It never appends to a telemetry file, and a
# dispatch that put nothing on the bus gets a row saying so rather than a row
# filled in from its plan.
#
# What a row says a dispatch cost is `cap_fraction`: percentage points of its
# pool's window cap (#220, #232), estimated as output tokens over a measured
# constant and carrying the calibration it ran on. Both halves are recorded per
# window — the estimator and the meter — and where a half cannot exist the row
# says which and why rather than writing a zero. `usage.list_price_usd` is API
# list pricing, is not this account's spend, and is a decision input for nothing.
#
# Source, and this is the part to read before believing a number: the durable
# per-dispatch export at /var/log/claude-otel/dispatches/ is preferred, and it
# exists only once the human has run the root script `just prereqs sudo-script`
# generates (#230). Until then the source is the rotating capture at
# /var/log/claude-otel/claude-telemetry.jsonl, which carries the same records and
# drops them at 50 MB × 5 — so every row names its source, a degraded sync warns
# on its last line, and a dispatch with no records read from a rotating source is
# typed `unknown` rather than `infra_unavailable`, because absence there is a
# fact about the view. With neither source present the sync refuses
# `infra_unavailable` and is not a result.
#
# Retention: rows are kept indefinitely; the raw export is pruned after 30 days
# and only where a row was materialised from that same durable file. Full policy
# and reasoning in docs/telemetry-ledger.md.
ledger-sync action="sync" *args:
    uv run python tools/ledger.py {{ action }} {{ args }}

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

# Compose the invariant half of a dispatch briefing from data (#251,
# docs/orchestration-design.md §5). No Arma, no lock: it reads the tracker and
# this checkout, and writes markdown.
#
#   just brief 251                       the brief on stdout
#   just brief 251 --seat review         a seat other than `implementer`
#   just brief 251 --out /tmp/b.md       a file for `just dispatch --brief-file`
#
# What it composes: the seat and the Model roles line behind it, the worktree
# protocol as the two calls it now is, the landing protocol, the live flake
# lines read from open issues, the verdict paste rule where the gate produces a
# verdict — and **the gate line, derived rather than chosen**. An issue whose
# named surfaces reach `addons/`, `missions/`, `extension/` or the daemon's
# world-facing half is owed the full corpus; one that names paths and none of
# them in-world, in a body speaking no domain language, gets `just fast`;
# anything else is **undetermined** and says so. Undetermined never resolves to
# the cheaper gate, because a briefing naming `just fast` for an in-world change
# is the defect the table exists to prevent. The in-world list is
# `tools/admission.py`'s, so this prediction and the landing-time audit cannot
# disagree about what in-world means. Measured on two vendored populations —
# 14 issues that landed in-world, 20 that did not — at zero under-gates and zero
# over-gates, with the whole error budget spent on saying "I cannot tell".
#
# What it does NOT compose, and emits as a visible placeholder instead: the task
# statement, the scope boundary, the ground truth to read, and the reason for a
# non-default seat. That is the orchestrator's work and the real work of the
# turn; an unedited brief is obviously unfinished by construction.
#
# **Its token effect is unmeasured** — #212 owns that, and #208 measured that
# briefings carrying a SHA correlate with *more* state reconstruction rather
# than less. What is claimed is correctness: a derived gate line, a flake list
# that cannot go stale, and a protocol that reaches every dispatch whether or
# not the composing session's memory is current.
#
# An issue that does not exist, or a `gh` that cannot be reached, is exit 3 with
# a message and nothing written — never a silent empty brief (#168/#183).
brief issue *args:
    @uv run python tools/brief.py {{ issue }} {{ args }}

# The multi-provider setup that does not need a human (#230, for #221/#229).
# No Arma, no lock: it reads this box, writes user-owned files, and generates —
# never runs — the one root script the initiative needs.
#
#   just prereqs                    same as `check`
#   just prereqs check              every item's true state, one line each, and a
#                                   non-zero exit if a week-one prerequisite is
#                                   absent. A check that could not run reports
#                                   `unknown` and is never a pass (#41's shape)
#   just prereqs credentials        create ~/.arma-cti/credentials.env at 0600,
#                                   outside every worktree, and take one pasted
#                                   key. The value is read off the terminal with
#                                   echo off — never argv, never stdout, never a
#                                   log. Refuses to overwrite a recorded name
#                                   without --force
#   just prereqs sudo-script        GENERATE the root script and print its path.
#                                   It is never run from here: it is the only
#                                   sudo in the initiative and it is generated to
#                                   be read, refusing unless the collector config
#                                   is byte-identical to what it was computed
#                                   from
#   just prereqs statusline         chain the quota tap ahead of the existing
#                                   status line in ~/.claude/settings.json,
#                                   passing its output through unchanged.
#                                   --dry-run prints and writes nothing
#   just prereqs tools              install gitleaks user-local (no sudo), and
#                                   write the Codex config that disables its
#                                   off-box metrics exporter BEFORE first use
#   just prereqs plan-tier          read the z.ai plan tier, or say plainly that
#                                   it could not be read. --set lite|pro|max
#                                   records the human's answer
#
# The status line is the one surface this repository cannot govern: the file is
# outside it, so no hook and no gate can hold the tap in place. The recipe says
# so in its own output every time it runs.
prereqs action="check" *args:
    uv run python tools/prereqs.py {{ action }} {{ args }}

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
# **Quote the rendered body verbatim; never retype the SHA or the evidence
# path.** #219's A/B is the reason it is written here rather than assumed: over
# 40 scored readings across five seats, not one worst class was misread and not
# one stop was taken for a result — and all four failures were retyping, twice
# producing a plausible-looking evidence path that resolves to nothing. That is
# worse than omitting one, and it is the record class #134 cost us. Pasting
# cannot fail that way, because the body carries the SHA and the path by
# construction.
#
# It reads and it renders. Nothing is posted: what a red means, and what the
# run gates, stay the agent's (the failure-class table's required-response
# column). `infra_unavailable` is printed as the stop it is, never interpreted.
verdict pool="":
    uv run python tools/pool_comment.py {{ pool }}
