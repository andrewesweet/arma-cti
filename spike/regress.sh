#!/usr/bin/env bash
# The Phase-1 in-game regression tier (issue #23, ADR-0016; a pool of slots since
# #47, ADR-0028). Design: docs/regression-tier.md. Invoked as
# `just regress [--slots <n>] [--wait <secs>] [--issues <n,...>] [--list] [name...]`.
#
# Per probe: a fresh Phase-1 world, the probe appended to the generated harness,
# and a wait on that probe's own completion line under the deadline its own
# header declares. One typed verdict per probe, mapped onto the CLAUDE.md failure
# classes; the whole run's exit code is the worst class any probe reported.
#
# Those probes run across N slots (`--slots`, default 3). A slot is a port block,
# a daemon, a server install, an engine profile and a world that agree —
# spike/slots.sh owns the geometry and the locks. `--slots 1` is the serial tier
# unchanged: slot 0 is ~/arma3server on 2402-2406, which is the install and the
# port block this tier has always used, so the fast path and the correct-by-
# construction path are the same code with a different N.
#
# Disposable by design. ADR-0011 assigns the real acceptance harness to Phase 3
# and issue #5 owns it; the names `just accept` / `just accept-all` stay
# reserved. What survives this script is the corpus, the lock, and the evidence
# convention.
#
# `-e` is deliberately absent (#83): every probe's failure is a *result* here,
# not an error — `run.sh` exiting non-zero is the normal path through this loop,
# and exit-on-error would abandon the corpus at the first red instead of
# reporting all of them and exiting on the worst class. The commands whose
# failure would be an error rather than a result are checked at their site.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROBE_DIR="$REPO/spike/probes"
STATE_DIR="${CTI_TIER_STATE:-$HOME/.arma-cti}"
RUNS_DIR="$STATE_DIR/runs"
KEEP_PASSES=3
KEEP_POOLS=5
# ADR-0028 recommends three, and #47 measured that three fit. Changing this
# number is a measurement, not a preference: the RAM figure is in
# docs/regression-tier.md and the pool records its own peak in every run.
DEFAULT_SLOTS=3
# Overridable so the no-Arma tier can drive the pool's scheduling, bulkheads and
# merge against a stub that prints what the engine would have printed
# (tests/unit/test_pool_scheduling.py). Nothing else sets it.
RUN_SH="${CTI_RUN_SH:-$REPO/spike/run.sh}"

# Worst-first. The number is both the rank and the process exit code, so the
# exit code of a run says which class to read the table row for. infra_unavailable
# outranks everything because it is not a result at all: nothing below it was
# measured under conditions anyone can interpret.
declare -A CLASS_RANK=(
    [infra_unavailable]=5
    [node_crashed]=4
    [engine_drift]=6
    [oracle_disagreement]=3
    [schema_stale]=7
    [timeout]=2
    [assertion_failed]=1
    [flake_quarantine]=0
    [pass]=0
    # Not one of the table's classes: it is what this script calls a run.sh that
    # exited without typing itself, which the table's preamble calls an untyped
    # red and a harness bug. It is here because it was reachable and missing —
    # `worst_class` could be this, miss the table and fall to an undocumented
    # exit 9 that read as "unknown class" rather than "fix the harness" (#83).
    [untyped_harness_failure]=8
)
# Ranking order is not the numeric one — the numbers are exit codes chosen to be
# stable, and this is the severity the summary and the exit code sort by.
class_severity() {
    case "$1" in
    infra_unavailable) echo 80 ;;
    node_crashed) echo 70 ;;
    engine_drift) echo 60 ;;
    oracle_disagreement) echo 50 ;;
    schema_stale) echo 40 ;;
    timeout) echo 30 ;;
    assertion_failed) echo 20 ;;
    flake_quarantine) echo 0 ;; # runs, reports, does not gate
    pass) echo 0 ;;
    *) echo 90 ;;               # an unknown class is an untyped red: worst of all
    esac
}

log() { printf '[regress] %s\n' "$*" >&2; }

# A JSON string literal from arbitrary text. `sed` alone eats the empty case —
# no input line, no output, and `"detail": ,` in the middle of verdict.json.
json_string() {
    local text="${1:-}"
    text="${text//\\/\\\\}"
    text="${text//\"/\\\"}"
    text="${text//$'\t'/ }"
    printf '"%s"' "${text//$'\n'/ }"
}
die() {
    log "$*"
    exit 2
}

# ------------------------------------------------------------------ arguments
WAIT_SECS=0
SELECTED=()
WANT_ISSUES=()
LIST_ONLY=0
WANT_SLOTS="$DEFAULT_SLOTS"
while (($# > 0)); do
    case "$1" in
    --wait)
        WAIT_SECS="${2:-}"
        shift 2
        ;;
    --slots)
        WANT_SLOTS="${2:-}"
        shift 2
        ;;
    --issues)
        spec="${2:-}"
        [[ -n "$spec" ]] || die "--issues takes one or more issue numbers"
        for n in ${spec//,/ }; do
            [[ "$n" =~ ^[0-9]+$ ]] || die "--issues takes issue numbers, got: $n"
            WANT_ISSUES+=("$n")
        done
        shift 2
        ;;
    --list)
        LIST_ONLY=1
        shift
        ;;
    -*) die "unknown option: $1" ;;
    *)
        SELECTED+=("$1")
        shift
        ;;
    esac
done

[[ "$WANT_SLOTS" =~ ^[1-9][0-9]*$ ]] || die "--slots takes a whole number of slots, got: $WANT_SLOTS"
# shellcheck source=spike/slots.sh
source "$REPO/spike/slots.sh"
((WANT_SLOTS <= CTI_SLOT_MAX + 1)) ||
    die "--slots $WANT_SLOTS is more slots than the port grant fits ($((CTI_SLOT_MAX + 1)))"

# ------------------------------------------------------------------ headers
# The probe is the unit of ownership, so its facts live in it. A manifest beside
# the corpus would be a second place to forget.
#
#   // probe: contacts          name, matched by `just regress <name>`
#   // issues: 28               what motivated it; makes selection buildable later
#   // window: 240              this probe's deadline in seconds
#   // env: CTI_AI_SIDE=WEST    what the world must be brought up with (optional)
#        — space-separated NAME=VALUE pairs, so a value containing a space is
#          inexpressible. No probe has needed one; if one does, the header has to
#          grow a quoting rule rather than the runner guessing at word breaks.
#   // expect: assertion_failed a probe that is red by design (optional)
#   // quarantined: #31         reports flake_quarantine, does not gate (optional)
header_of() {
    local file="$1" key="$2"
    # Leading comment block only: a `// window:` quoted deeper in the prose is
    # discussion, not declaration.
    awk -v key="$key" '
        !/^\/\// { exit }
        { sub(/^\/\/[ \t]*/, "") }
        index($0, key ":") == 1 {
            sub(/^[^:]*:[ \t]*/, "")
            print
            exit
        }
    ' "$file"
}

# ------------------------------------------------------------------ corpus
mapfile -t ALL < <(for f in "$PROBE_DIR"/*.sqf; do basename "$f" .sqf; done | sort)
((${#ALL[@]} > 0)) || die "no probes in $PROBE_DIR"

# Does this probe's `issues:` header name that issue? The header is a comma list
# ("16, 32, 43") and matching is on whole numbers, so `--issues 3` never selects
# a probe written for #32.
names_issue() {
    local file="$1" want="$2" raw tok
    raw="$(header_of "$file" issues)"
    for tok in ${raw//,/ }; do
        [[ "$tok" == "$want" ]] && return 0
    done
    return 1
}

if ((${#SELECTED[@]} == 0 && ${#WANT_ISSUES[@]} == 0)); then
    CORPUS=("${ALL[@]}")
else
    # Names keep the caller's order; `--issues` appends what it selects in corpus
    # order, minus anything already named. Both filters union, neither subtracts.
    declare -A PICKED=()
    CORPUS=()
    for want in "${SELECTED[@]}"; do
        found=""
        for have in "${ALL[@]}"; do [[ "$have" == "$want" ]] && found="$have"; done
        [[ -n "$found" ]] || die "no such probe: $want (have: ${ALL[*]})"
        [[ -n "${PICKED[$found]:-}" ]] && continue
        PICKED[$found]=1
        CORPUS+=("$found")
    done
    # An `--issues` filter that matches nothing is an error, never a green pass:
    # the one way this tier could lie is by silently running an empty corpus and
    # exiting 0. Reported per number, so a spec that matched three issues out of
    # four still names the fourth rather than passing on the strength of the rest.
    unmatched=()
    for n in "${WANT_ISSUES[@]}"; do
        matched=0
        for have in "${ALL[@]}"; do
            names_issue "$PROBE_DIR/$have.sqf" "$n" || continue
            matched=1
            [[ -n "${PICKED[$have]:-}" ]] && continue
            PICKED[$have]=1
            CORPUS+=("$have")
        done
        ((matched)) || unmatched+=("$n")
    done
    ((${#unmatched[@]} == 0)) ||
        die "no probe's 'issues:' header names: ${unmatched[*]} — an --issues filter that matches no probe is an error, not a pass. Run the full corpus, or name the probes."
fi

# The invariant the two branches above exist to hold. Selection may narrow the
# corpus; it may never empty it.
((${#CORPUS[@]} > 0)) || die "selection is empty"

# Validate every selected probe's header before bringing a single world up: a
# corpus that fails to parse should cost seconds, not a bring-up per probe.
for name in "${CORPUS[@]}"; do
    file="$PROBE_DIR/$name.sqf"
    declared="$(header_of "$file" probe)"
    [[ "$declared" == "$name" ]] ||
        die "$name.sqf declares 'probe: ${declared:-<missing>}' but is named $name.sqf"
    window="$(header_of "$file" window)"
    [[ "$window" =~ ^[0-9]+$ ]] || die "$name.sqf has no numeric 'window:' header"
    [[ -n "$(header_of "$file" issues)" ]] || die "$name.sqf has no 'issues:' header"
    quarantine="$(header_of "$file" quarantined)"
    if [[ -n "$quarantine" ]]; then
        # Quarantine without an open issue is out of policy, and the way that is
        # enforced is that the line without an issue number does not parse.
        [[ "$quarantine" =~ ^#[0-9]+$ ]] ||
            die "$name.sqf is quarantined without an issue number: 'quarantined: $quarantine'"
    fi
done

# ------------------------------------------------------------------ dry run
# `--list` is the whole selection path with nothing after it: it resolves the
# filters, validates the headers of what they chose, prints that and stops. It
# takes no lock, opens no port and brings no world up, which is what makes
# selection testable in the no-Arma tier — and what lets an agent see what a
# filter chose before spending the wall on it. Names to stdout one per line so
# the output composes; the cost estimate is commentary, on stderr.
if ((LIST_ONLY)); then
    budget=0
    for name in "${CORPUS[@]}"; do
        printf '%s\n' "$name"
        budget=$((budget + $(header_of "$PROBE_DIR/$name.sqf" window)))
    done
    log "${#CORPUS[@]} of ${#ALL[@]} probe(s); declared windows total ${budget}s (deadlines, not run time)"
    exit 0
fi

# ------------------------------------------------------------------ the pool
# Everything above this line reads files and touches no port, which is why it
# runs before queueing: a corpus that does not parse should cost seconds rather
# than a place in the queue. Everything below needs slots of the tier.
[[ "$WAIT_SECS" =~ ^[0-9]+$ ]] || die "--wait takes whole seconds, got: $WAIT_SECS"

POOL_LABEL="just regress --slots $WANT_SLOTS ${CORPUS[*]}"

# ------------------------------------------------------------------ pre-flight
# The host guard covers the whole machine and therefore the whole pool: what it
# protects is not a port block but a person. `arma3_x64.exe` on the Windows host
# means a play session may be live, and no number of slots makes it acceptable to
# load the machine underneath one. Asked before a single lock is taken, so a
# refusal costs the caller no place in any queue (#41; it fails closed by design).
# shellcheck source=spike/host-guard.sh
source "$REPO/spike/host-guard.sh"
if ! cti_host_guard_main; then
    exit "${CLASS_RANK[infra_unavailable]}"
fi

# ------------------------------------------------------------------ allocation
# One flock per slot, non-blocking, in index order until we have the N we asked
# for or the indices run out (ADR-0028). Fewer slots than asked for is a smaller
# pool, not a failure: another agent holding slot 0 should cost us a slot, not a
# run. **No** slot free is `infra_unavailable` with the holders printed — the
# same meaning the single lock has always had, N times over.
SLOTS=()
acquire_slots() {
    local deadline=$((SECONDS + WAIT_SECS)) n
    while :; do
        for ((n = 0; n <= CTI_SLOT_MAX; n++)); do
            ((${#SLOTS[@]} < WANT_SLOTS)) || break
            cti_slot_acquire "$n" "$POOL_LABEL" && SLOTS+=("$n")
        done
        ((${#SLOTS[@]} > 0)) && return 0
        ((SECONDS < deadline)) || return 1
        # A queue's poll interval, not a synchronisation wait. `flock -w` bounds
        # one lock and we are asking about several, so the wait is a loop. The
        # Contract bans sleeping until a test passes; this sleeps until somebody
        # else's run ends, which is the whole of what `--wait` is for.
        sleep 5
    done
}

if ! acquire_slots; then
    {
        printf '\n[regress] every slot of the Arma tier is busy — this is infra_unavailable, not a result.\n'
        for ((n = 0; n <= CTI_SLOT_MAX; n++)); do
            printf '[regress] slot %s holder:\n' "$n"
            cti_slot_holder "$n"
        done
        ((WAIT_SECS > 0)) && printf '[regress] waited %ss and gave up.\n' "$WAIT_SECS"
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=no slot free; see %s\n' "$CTI_SLOT_LOCK_DIR"
    } >&2
    exit "${CLASS_RANK[infra_unavailable]}"
fi

((${#SLOTS[@]} < WANT_SLOTS)) &&
    log "asked for $WANT_SLOTS slot(s), ${#SLOTS[@]} free — running at N=${#SLOTS[@]}"
log "slots: ${SLOTS[*]}"

# Stale state, per slot, on acquire rather than on release (ADR-0022, #58, #70).
# The lock frees itself when its holder dies; the holder's server, headless
# client and daemon do not, and they are still on this slot's ports and in this
# slot's install. The next holder clears them, and the next holder is us.
for slot in "${SLOTS[@]}"; do
    cti_slot_reclaim "$slot"
    cti_slot_install_ready "$slot" || die "could not prepare the install for slot $slot"
done

# ------------------------------------------------------------------ evidence
mkdir -p "$RUNS_DIR"
RUN_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
POOL_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
POOL_OUT="$RUNS_DIR/$POOL_STAMP-pool"
CLAIMS="$POOL_OUT/claims"
STOP_FLAG="$POOL_OUT/stop"
mkdir -p "$CLAIMS" || die "could not create the pool's evidence directory $POOL_OUT"

# The pool's own evidence is bounded the way a probe's passes are. It is small —
# a schedule, a RAM trace and the merged verdict set — but unbounded is unbounded.
mapfile -t old_pools < <(ls -d "$RUNS_DIR"/*-pool 2>/dev/null | sort)
if ((${#old_pools[@]} > KEEP_POOLS)); then
    for dir in "${old_pools[@]:0:$((${#old_pools[@]} - KEEP_POOLS))}"; do
        [[ "$dir" == "$POOL_OUT" ]] || rm -rf "$dir"
    done
fi

# Passes pruned before the probe runs rather than after, so a run that dies
# halfway still leaves the directory bounded, and so a failure's evidence is
# never pruned by the run that produced it. Room is left for the pass this run is
# about to write, which is what makes "the last three passes" the count a reader
# finds afterwards rather than four.
prune_passes() {
    local name="$1" dir keep room
    local -a dirs
    mapfile -t dirs < <(
        grep -l '"verdict": "PASS"' "$RUNS_DIR"/*-"$name"/verdict.json 2>/dev/null |
            xargs -r -n1 dirname | sort
    )
    keep=${#dirs[@]}
    room=$((KEEP_PASSES - 1))
    ((keep > room)) || return 0
    for dir in "${dirs[@]:0:$((keep - room))}"; do
        log "pruning old pass: $dir"
        rm -rf "$dir"
    done
}

# ------------------------------------------------------------------ RAM
# ADR-0028's N=3 figure was arithmetic from a measured N=2, and its own
# overturning conditions say the third slot is not trusted until the number has
# been measured. So every pool run measures it, and the number lands in the run's
# evidence rather than in a session's memory.
ram_sampler_pid=""
start_ram_sampler() {
    (
        printf 'epoch\tmem_used_kb\tmem_available_kb\ttier_rss_kb\n'
        while :; do
            awk -v now="$(date +%s)" '
                /^MemTotal:/     { total = $2 }
                /^MemAvailable:/ { avail = $2 }
                END { printf "%s\t%s\t%s\t", now, total - avail, avail }
            ' /proc/meminfo
            # The tier's own share, so a peak can be attributed rather than only
            # observed. The engine by its comm; the daemon by its command line,
            # because it runs as a python interpreter under `uv`.
            ps -eo rss=,comm=,args= 2>/dev/null | awk '
                $2 == "arma3server_x64" { sum += $1; next }
                /cti-daemon/            { sum += $1 }
                END { printf "%s\n", sum + 0 }
            '
            sleep 3
        done
    ) >"$POOL_OUT/ram.tsv" 2>/dev/null &
    ram_sampler_pid=$!
}

WORKER_PIDS=()
pool_teardown() {
    local pid
    [[ -n "$ram_sampler_pid" ]] && kill "$ram_sampler_pid" 2>/dev/null
    for pid in ${WORKER_PIDS[@]+"${WORKER_PIDS[@]}"}; do kill "$pid" 2>/dev/null; done
    for pid in ${SLOTS[@]+"${SLOTS[@]}"}; do cti_slot_release "$pid"; done
}
trap pool_teardown EXIT INT TERM

# ------------------------------------------------------------------ scheduling
# Longest-job-first, on the probe's own declared window. A window is a deadline
# rather than a measurement, so it is only an estimate of cost — but it is the
# estimate that already lives in the probe, and a table of measured times inside
# the runner would be a second place to forget. What LJF has to get right is the
# tail: `campaign-end` is ~390 s of a ~1,550 s corpus, so a pool that starts it
# late idles every other slot waiting for it. Its 750 s window puts it first.
#
# The Windows-host probes are not in that schedule. `client-port` and
# `human-commander` each drive the headed client on the Windows host, of which
# there is one, and the host guard that protects the human is ownership-blind on
# purpose (#119) — so a second slot starting a probe while one slot's client is
# up would read that client as a play session and stop the corpus. They run
# **serially, in a tail, with the rest of the pool drained**, on the lowest slot
# held. Last rather than first: a human who sits down to play at minute eight
# then costs us the tail rather than the pass.
host_probe() { [[ "$(header_of "$PROBE_DIR/$1.sqf" env)" == *CTI_WINDOWS_CLIENT=1* ]]; }

by_window_desc() {
    local name
    for name in "$@"; do
        printf '%s\t%s\n' "$(header_of "$PROBE_DIR/$name.sqf" window)" "$name"
    done | sort -rn -k1,1 -k2,2 | cut -f2
}

PARALLEL_JOBS=()
HOST_JOBS=()
for name in "${CORPUS[@]}"; do
    if host_probe "$name"; then HOST_JOBS+=("$name"); else PARALLEL_JOBS+=("$name"); fi
done
# With one slot there is nothing to schedule, and corpus order is the order a
# reader of the serial tier expects. With more than one, the order is the point.
if ((${#SLOTS[@]} > 1 && ${#PARALLEL_JOBS[@]} > 1)); then
    mapfile -t PARALLEL_JOBS < <(by_window_desc "${PARALLEL_JOBS[@]}")
fi

# ------------------------------------------------------------------ the probe
GIT_SHA="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
GIT_DIRTY="$(git -C "$REPO" status --porcelain 2>/dev/null | head -1)"
[[ -n "$GIT_DIRTY" ]] && GIT_DIRTY=true || GIT_DIRTY=false

# One probe, in one slot. This runs inside a worker subshell, so it writes its
# result where the parent can find it and never into a shell variable: a verdict
# that lived in a worker's memory would die with the worker, which is exactly the
# case the dead-slot rule in the merge has to report.
run_probe() {
    local name="$1" slot="$2"
    local file="$PROBE_DIR/$name.sqf"
    local window expect quarantine probe_env stamp out t0 elapsed run_status
    local verdict raw_class detail legs class
    window="$(header_of "$file" window)"
    expect="$(header_of "$file" expect)"
    quarantine="$(header_of "$file" quarantined)"
    probe_env="$(header_of "$file" env)"

    prune_passes "$name"
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    out="$RUNS_DIR/$stamp-$name"
    mkdir -p "$out"
    printf '%s\n' "$out" >"$CLAIMS/$name/evidence"
    # Which evidence directory this slot is writing, for the *next* holder of
    # this slot to apply ADR-0022 to: a directory with no verdict.json means the
    # holder was interrupted, and its leftovers are stale state to clear.
    cti_slot_mark_run "$slot" "$out"

    log "[slot $slot] ---- $name (window ${window}s${expect:+, expects $expect}${quarantine:+, quarantined $quarantine})"
    t0=$(date +%s)

    # The env: header is the probe's own bring-up requirement, not the caller's
    # to remember. `just regress` takes no environment variables of its own.
    local -a env_args=()
    if [[ -n "$probe_env" ]]; then
        read -r -a env_args <<<"$probe_env"
        log "[slot $slot]      env: ${env_args[*]}"
    fi
    # The slot's own environment goes last, after the probe's, so no probe header
    # can name a variable that moves it into another slot's ports or install.
    # Every line of it has a consumer named in spike/slots.sh, because ADR-0028's
    # rule is that a slot boundary is only real where something reads it.
    local -a slot_args=()
    mapfile -t slot_args < <(cti_slot_env "$slot")

    env ${env_args[@]+"${env_args[@]}"} "${slot_args[@]}" \
        CTI_SPIKE_OUT="$out" \
        CTI_MISSION=cti.Stratis \
        CTI_SERVER_CONFIG="$REPO/spike/phase1.cfg" \
        CTI_LOG_PREFIX=CTI \
        CTI_HARNESS_EXTRA="$file" \
        CTI_HARNESS_AWAIT=probe_done \
        CTI_HOLD_TIMEOUT="$window" \
        CTI_PROBE_TIMEOUT="$window" \
        "$RUN_SH" --regress >"$out/regress.log" 2>&1
    run_status=$?
    elapsed=$(($(date +%s) - t0))

    verdict="$(sed -n 's/^verdict=//p' "$out/results.env" 2>/dev/null | tail -1)"
    raw_class="$(sed -n 's/^failure_class=//p' "$out/results.env" 2>/dev/null | tail -1)"
    detail="$(sed -n 's/^failure_detail=//p' "$out/results.env" 2>/dev/null | tail -1)"
    class=""
    # What became of the probe's optional legs, in the verdict rather than in the
    # log (#116, ADR-0037). Empty for the probes that have none. `run.sh` has
    # already turned an unverified leg into infra_unavailable, so this is the
    # naming rather than the gating: it is what lets a reader of verdict.json see
    # that a green probe ran the leg it is mostly about.
    legs="$(sed -n 's/^legs=//p' "$out/results.env" 2>/dev/null | tail -1)"

    if [[ "$verdict" == "PASS" ]]; then
        raw_class=pass
    elif [[ -z "$raw_class" ]]; then
        # run.sh died without typing itself. An untyped red is a harness bug, and
        # the failure-class table says fix the harness first — so it is reported
        # as one rather than being folded into the nearest plausible class.
        raw_class="untyped_harness_failure"
        detail="${detail:-run.sh exited $run_status without recording a class; see $out/regress.log}"
        verdict=FAIL
    fi

    # `expect:` inverts the verdict for a probe that is red by design. The class
    # must be the declared one: a negative probe failing for the wrong reason is
    # still a failure, and reporting it green would be exactly the untyped pass
    # the harness exists to refuse.
    if [[ -n "$expect" ]]; then
        if [[ "$raw_class" == "$expect" ]]; then
            log "[slot $slot]      expected $expect and got it — inverted to a pass"
            detail="expected-red: $detail"
            class=pass
        elif [[ "$raw_class" == pass ]]; then
            class=assertion_failed
            detail="probe expects $expect and passed instead; a green run of this probe is the bug"
        else
            class="$raw_class"
            detail="probe expects $expect, got $raw_class: $detail"
        fi
    else
        class="$raw_class"
    fi

    # Quarantine is applied last, over whatever the run said: the point is that
    # the corpus keeps gathering evidence about the flake without the flake
    # gating anyone. The tier never retries — one run, one verdict.
    if [[ -n "$quarantine" && "$class" != pass ]]; then
        detail="quarantined $quarantine (not gating): $class — $detail"
        class=flake_quarantine
    fi

    cat >"$out/verdict.json" <<JSON
{
  "probe": "$name",
  "verdict": "$([[ "$class" == pass ]] && echo PASS || echo FAIL)",
  "class": "$class",
  "raw_class": "$raw_class",
  "expected": $(json_string "${expect:-}"),
  "quarantined": $(json_string "${quarantine:-}"),
  "legs": $(json_string "${legs:-}"),
  "detail": $(json_string "${detail:-}"),
  "window_secs": $window,
  "elapsed_secs": $elapsed,
  "issues": $(json_string "$(header_of "$file" issues)"),
  "started_at": "$stamp",
  "git_sha": "$GIT_SHA",
  "git_dirty": $GIT_DIRTY,
  "slot": $slot,
  "host": $(json_string "${CTI_TIER_HOST:-local}"),
  "arma_version": $(json_string "$(sed -n 's/^server_version=//p' "$out/results.env" 2>/dev/null | tail -1)"),
  "evidence": "$out"
}
JSON

    if [[ "$class" == pass ]]; then
        log "[slot $slot]      PASS in ${elapsed}s — $out"
    else
        log "[slot $slot]      FAIL class=$class in ${elapsed}s — $out"
        log "[slot $slot]      $detail"
    fi
    # Printed either way. A pass that names the legs it ran is the whole point of
    # the convention: the reader should not have to open the evidence to find out
    # whether the half that needed a client happened.
    [[ -n "$legs" ]] && log "[slot $slot]      legs: $legs"

    # A failing probe fails the run, and the pool carries on: report everything,
    # filter in a separate pass. That is the bulkhead — one slot's red is a
    # verdict, not a stop for its siblings.
    #
    # Two things do stop the pool taking *new* work. `infra_unavailable` is not a
    # result, and a pool that keeps launching worlds past one produces more
    # non-results N at a time. And a second `node_crashed` is a world failing
    # systemically, which a pool hammers N times as hard as a serial run did —
    # #58's reading of #72, whose effect-pump half is still #72's. Neither kills
    # a probe already in flight: interrupting a running world would itself
    # manufacture the non-result being avoided.
    if [[ "$class" == infra_unavailable ]]; then
        printf 'infra_unavailable in slot %s on %s\n' "$slot" "$name" >"$STOP_FLAG"
    elif [[ "$class" == node_crashed ]]; then
        printf '%s\n' "$name" >>"$POOL_OUT/crashes"
        if (($(wc -l <"$POOL_OUT/crashes") >= 2)); then
            printf 'two probes crashed a node (%s) — stopping rather than hammering it N slots at a time\n' \
                "$(tr '\n' ' ' <"$POOL_OUT/crashes")" >"$STOP_FLAG"
        fi
    fi
    printf 'done\n' >"$CLAIMS/$name/done"
}

# ------------------------------------------------------------------ the workers
# Dynamic longest-job-first: each worker takes the first job nobody has claimed,
# in the schedule's order. The claim is a `mkdir`, which is atomic, so no second
# lock is needed to arbitrate one. Dynamic rather than a static partition because
# the schedule's costs are declared windows and the real times are not them: a
# worker that finishes early should take the next job rather than idle beside a
# queue that belongs to somebody else.
worker() {
    local slot="$1"
    shift
    local -a jobs=("$@")
    local cand name sibling
    # A worker inherits every slot's lock descriptor from the pool that forked
    # it, and `flock` frees a lock only when the last descriptor closes. Holding
    # a sibling's lock would make a dead slot look occupied by us — so a worker
    # keeps its own slot's descriptor and lets go of the rest. Bulkheads are
    # walls, and an inherited descriptor is a hole in one.
    for sibling in "${SLOTS[@]}"; do
        [[ "$sibling" == "$slot" ]] || cti_slot_close "$sibling"
    done
    while :; do
        [[ -f "$STOP_FLAG" ]] && break
        name=""
        for cand in "${jobs[@]}"; do
            mkdir "$CLAIMS/$cand" 2>/dev/null || continue
            name="$cand"
            break
        done
        [[ -n "$name" ]] || break
        printf '%s\n' "$slot" >"$CLAIMS/$name/slot"
        run_probe "$name" "$slot"
    done
}

log "corpus: ${CORPUS[*]}"
log "sha: $GIT_SHA dirty: $GIT_DIRTY started: $RUN_STARTED"
((${#PARALLEL_JOBS[@]} > 0)) && log "schedule: ${PARALLEL_JOBS[*]}"
((${#HOST_JOBS[@]} > 0)) && log "windows-host tail (serial, pool drained): ${HOST_JOBS[*]}"

POOL_T0=$(date +%s)
start_ram_sampler

if ((${#PARALLEL_JOBS[@]} > 0)); then
    for slot in "${SLOTS[@]}"; do
        worker "$slot" "${PARALLEL_JOBS[@]}" &
        WORKER_PIDS+=($!)
    done
    for pid in "${WORKER_PIDS[@]}"; do wait "$pid"; done
    WORKER_PIDS=()
fi

# The tail, with every other slot idle: one Windows host, one headed client, one
# guard that is ownership-blind on purpose.
if ((${#HOST_JOBS[@]} > 0)) && [[ ! -f "$STOP_FLAG" ]]; then
    worker "${SLOTS[0]}" "${HOST_JOBS[@]}"
fi

POOL_ELAPSED=$(($(date +%s) - POOL_T0))
[[ -n "$ram_sampler_pid" ]] && kill "$ram_sampler_pid" 2>/dev/null
ram_sampler_pid=""

# ------------------------------------------------------------------ the merge
# One verdict set out of N slots. Read back off the claim directories rather than
# accumulated in memory, because the thing this has to report honestly is a
# worker that died: its verdict was never written, and a parent holding an array
# would simply have no row for it.
VERDICT_NAMES=()
VERDICT_CLASSES=()
VERDICT_PATHS=()
VERDICT_SECS=()
VERDICT_SLOTS=()
worst_severity=0
worst_class=pass
not_run=()

json_field() {
    sed -n "s/^  \"$2\": \"\\{0,1\\}\\(.*\\)/\\1/p" "$1" | head -1 | sed 's/,$//; s/^"//; s/"$//'
}

for name in "${CORPUS[@]}"; do
    claim="$CLAIMS/$name"
    if [[ ! -d "$claim" ]]; then
        not_run+=("$name")
        continue
    fi
    slot="$(cat "$claim/slot" 2>/dev/null || echo '?')"
    out="$(cat "$claim/evidence" 2>/dev/null || echo '')"
    if [[ ! -f "$claim/done" || -z "$out" || ! -f "$out/verdict.json" ]]; then
        # A claimed probe with no verdict is the dead-slot case, and ADR-0022
        # says what it is: not a result. The worker was killed, or the machine
        # took it; either way nothing was measured under conditions anyone can
        # interpret, and calling it a failure of the *probe* would be a reading
        # of evidence that does not exist.
        class=infra_unavailable
        elapsed=0
        log "slot $slot claimed $name and wrote no verdict — the worker died mid-probe; not a result (ADR-0022)"
        # And the slot is cleared here rather than left for whoever comes next.
        # A dead worker's *children* outlive it — `run.sh`, a server, a headless
        # client — still on this slot's ports and still holding the descriptor
        # they inherited, so the lock the kernel is supposed to free stays held.
        # We still own the slot, so clearing it is ours to do; the next holder's
        # cleanup-on-acquire is the backstop for the case where nobody did.
        if [[ "$slot" =~ ^[0-9]+$ ]]; then
            cti_slot_release "$slot"
            cti_slot_reclaim "$slot" holders
        fi
    else
        class="$(json_field "$out/verdict.json" class)"
        elapsed="$(sed -n 's/.*"elapsed_secs": \([0-9]*\).*/\1/p' "$out/verdict.json" | head -1)"
    fi
    VERDICT_NAMES+=("$name")
    VERDICT_CLASSES+=("${class:-untyped_harness_failure}")
    VERDICT_PATHS+=("${out:-$claim}")
    VERDICT_SECS+=("${elapsed:-0}")
    VERDICT_SLOTS+=("$slot")

    severity="$(class_severity "${class:-untyped_harness_failure}")"
    if ((severity > worst_severity)); then
        worst_severity=$severity
        worst_class="${class:-untyped_harness_failure}"
    fi
done

# ------------------------------------------------------------------ RAM verdict
PEAK_USED_KB=0
MIN_AVAIL_KB=0
PEAK_TIER_KB=0
if [[ -s "$POOL_OUT/ram.tsv" ]]; then
    read -r PEAK_USED_KB MIN_AVAIL_KB PEAK_TIER_KB < <(
        awk -F'\t' 'NR > 1 {
            if ($2 > used) used = $2
            if (min == 0 || $3 < min) min = $3
            if ($4 > tier) tier = $4
        } END { printf "%d %d %d\n", used, min, tier }' "$POOL_OUT/ram.tsv"
    )
fi

# ------------------------------------------------------------------ summary
printf '\n' >&2
log "==== verdicts (${RUN_STARTED}, sha ${GIT_SHA:0:12}, N=${#SLOTS[@]}) ===="
# Worst class first, so the thing to read is the first line.
for i in "${!VERDICT_NAMES[@]}"; do
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$(class_severity "${VERDICT_CLASSES[$i]}")" "${VERDICT_CLASSES[$i]}" \
        "${VERDICT_NAMES[$i]}" "${VERDICT_SECS[$i]}" "${VERDICT_SLOTS[$i]}" "${VERDICT_PATHS[$i]}"
done | sort -rn -k1,1 | while IFS=$'\t' read -r _sev cls nm secs slot path; do
    printf '[regress] %-20s %-18s %4ss  slot %s  %s\n' "$nm" "$cls" "$secs" "$slot" "$path" >&2
done

((${#not_run[@]} > 0)) && log "${#not_run[@]} probe(s) not run: ${not_run[*]}"
[[ -f "$STOP_FLAG" ]] && log "pool stopped early: $(cat "$STOP_FLAG")"
log "wall: ${POOL_ELAPSED}s across ${#SLOTS[@]} slot(s) — slots ${SLOTS[*]}"
log "peak memory in use: $((PEAK_USED_KB / 1024)) MiB (tier processes $((PEAK_TIER_KB / 1024)) MiB, least available $((MIN_AVAIL_KB / 1024)) MiB)"
log "pool evidence: $POOL_OUT"

{
    printf '{\n'
    printf '  "started_at": "%s",\n' "$RUN_STARTED"
    printf '  "git_sha": "%s",\n' "$GIT_SHA"
    printf '  "slots": [%s],\n' "$(
        IFS=,
        echo "${SLOTS[*]}"
    )"
    printf '  "host": %s,\n' "$(json_string "${CTI_TIER_HOST:-local}")"
    printf '  "wall_secs": %s,\n' "$POOL_ELAPSED"
    printf '  "peak_mem_used_kb": %s,\n' "$PEAK_USED_KB"
    printf '  "peak_tier_rss_kb": %s,\n' "$PEAK_TIER_KB"
    printf '  "least_mem_available_kb": %s,\n' "$MIN_AVAIL_KB"
    printf '  "stopped_early": %s,\n' "$(json_string "$(cat "$STOP_FLAG" 2>/dev/null || true)")"
    printf '  "not_run": [%s],\n' "$(
        sep=""
        for n in ${not_run[@]+"${not_run[@]}"}; do
            printf '%s%s' "$sep" "$(json_string "$n")"
            sep=", "
        done
    )"
    printf '  "verdicts": [\n'
    for i in "${!VERDICT_NAMES[@]}"; do
        comma=","
        ((i + 1 == ${#VERDICT_NAMES[@]})) && comma=""
        printf '    {"probe": %s, "class": %s, "slot": %s, "elapsed_secs": %s, "evidence": %s}%s\n' \
            "$(json_string "${VERDICT_NAMES[$i]}")" "$(json_string "${VERDICT_CLASSES[$i]}")" \
            "$(json_string "${VERDICT_SLOTS[$i]}")" "${VERDICT_SECS[$i]}" \
            "$(json_string "${VERDICT_PATHS[$i]}")" "$comma"
    done
    printf '  ]\n'
    printf '}\n'
} >"$POOL_OUT/pool.json"

exit_code="${CLASS_RANK[$worst_class]:-9}"
log "worst class: $worst_class (exit $exit_code)"
exit "$exit_code"
