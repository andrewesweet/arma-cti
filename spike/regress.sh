#!/usr/bin/env bash
# The Phase-1 in-game regression tier (issue #23, ADR-0016). Design:
# docs/regression-tier.md. Invoked as
# `just regress [--wait <secs>] [--issues <n,...>] [--list] [name...]`.
#
# One loop over the probe corpus in spike/probes/. Per probe: a fresh Phase-1
# world, the probe appended to the generated harness, and a wait on that probe's
# own completion line under the deadline its own header declares. One typed
# verdict per probe, mapped onto the CLAUDE.md failure classes; the whole run's
# exit code is the worst class any probe reported.
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
while (($# > 0)); do
    case "$1" in
    --wait)
        WAIT_SECS="${2:-}"
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

# ------------------------------------------------------------------ the lock
# Everything above this line reads files and touches no port, which is why it
# runs before queueing: a corpus that does not parse should cost seconds rather
# than a place in the queue. Everything below needs the tier to itself.
if [[ -z "${CTI_TIER_LOCK_HELD:-}" ]]; then
    [[ "$WAIT_SECS" =~ ^[0-9]+$ ]] || die "--wait takes whole seconds, got: $WAIT_SECS"
    lock_args=()
    ((WAIT_SECS > 0)) && lock_args=(--wait "$WAIT_SECS")
    export CTI_TIER_LOCK_HELD=1
    exec "$REPO/spike/tier-lock.sh" "${lock_args[@]+"${lock_args[@]}"}" \
        --label "just regress ${CORPUS[*]}" -- "${BASH_SOURCE[0]}" "${CORPUS[@]}"
fi

# ------------------------------------------------------------------ evidence
mkdir -p "$RUNS_DIR"
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

# ------------------------------------------------------------------ pre-flight
# The lock covers agents, not the human. They are protected first by the port
# split (their sessions own 2302-2306, this tier 2402-2406) and second by this:
# if the game is up on the Windows host a play session may be live, and loading
# the shared machine underneath it is not something to do for a test.
#
# This used to be wrapped in `command -v tasklist.exe`, which is false in an
# agent's shell, so the guard never ran and failed open every time (#41). It now
# lives in spike/host-guard.sh, resolves the tool by absolute path, and treats
# "could not read the process list" as the same stop as "a client is in it".
# shellcheck source=spike/host-guard.sh
source "$REPO/spike/host-guard.sh"
if ! cti_host_guard_main; then
    exit "${CLASS_RANK[infra_unavailable]}"
fi

# ------------------------------------------------------------------ the loop
GIT_SHA="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
GIT_DIRTY="$(git -C "$REPO" status --porcelain 2>/dev/null | head -1)"
[[ -n "$GIT_DIRTY" ]] && GIT_DIRTY=true || GIT_DIRTY=false

RUN_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "corpus: ${CORPUS[*]}"
log "sha: $GIT_SHA dirty: $GIT_DIRTY started: $RUN_STARTED"

VERDICT_NAMES=()
VERDICT_CLASSES=()
VERDICT_PATHS=()
VERDICT_SECS=()
VERDICT_DETAILS=()
worst_severity=0
worst_class=pass

for name in "${CORPUS[@]}"; do
    file="$PROBE_DIR/$name.sqf"
    window="$(header_of "$file" window)"
    expect="$(header_of "$file" expect)"
    quarantine="$(header_of "$file" quarantined)"
    probe_env="$(header_of "$file" env)"

    prune_passes "$name"
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    out="$RUNS_DIR/$stamp-$name"
    mkdir -p "$out"

    log "---- $name (window ${window}s${expect:+, expects $expect}${quarantine:+, quarantined $quarantine})"
    t0=$(date +%s)

    # The env: header is the probe's own bring-up requirement, not the caller's
    # to remember. `just regress` takes no environment variables of its own.
    env_args=()
    if [[ -n "$probe_env" ]]; then
        read -r -a env_args <<<"$probe_env"
        log "     env: ${env_args[*]}"
    fi

    env ${env_args[@]+"${env_args[@]}"} \
        CTI_SPIKE_OUT="$out" \
        CTI_MISSION=cti.Stratis \
        CTI_SERVER_CONFIG="$REPO/spike/phase1.cfg" \
        CTI_LOG_PREFIX=CTI \
        CTI_HARNESS_EXTRA="$file" \
        CTI_HARNESS_AWAIT=probe_done \
        CTI_HOLD_TIMEOUT="$window" \
        CTI_PROBE_TIMEOUT="$window" \
        "$REPO/spike/run.sh" --regress >"$out/regress.log" 2>&1
    run_status=$?
    elapsed=$(($(date +%s) - t0))

    verdict="$(sed -n 's/^verdict=//p' "$out/results.env" 2>/dev/null | tail -1)"
    raw_class="$(sed -n 's/^failure_class=//p' "$out/results.env" 2>/dev/null | tail -1)"
    detail="$(sed -n 's/^failure_detail=//p' "$out/results.env" 2>/dev/null | tail -1)"

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
            log "     expected $expect and got it — inverted to a pass"
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
  "detail": $(json_string "${detail:-}"),
  "window_secs": $window,
  "elapsed_secs": $elapsed,
  "issues": $(json_string "$(header_of "$file" issues)"),
  "started_at": "$stamp",
  "git_sha": "$GIT_SHA",
  "git_dirty": $GIT_DIRTY,
  "arma_version": $(json_string "$(sed -n 's/^server_version=//p' "$out/results.env" 2>/dev/null | tail -1)"),
  "evidence": "$out"
}
JSON

    VERDICT_NAMES+=("$name")
    VERDICT_CLASSES+=("$class")
    VERDICT_PATHS+=("$out")
    VERDICT_SECS+=("$elapsed")
    VERDICT_DETAILS+=("${detail:-}")

    severity="$(class_severity "$class")"
    if ((severity > worst_severity)); then
        worst_severity=$severity
        worst_class="$class"
    fi

    if [[ "$class" == pass ]]; then
        log "     PASS in ${elapsed}s — $out"
    else
        log "     FAIL class=$class in ${elapsed}s — $out"
        log "     $detail"
    fi

    # A failing probe fails the run, and the run finishes anyway: report
    # everything, filter in a separate pass. The one exception is
    # infra_unavailable, which is not a result — carrying on would produce more
    # of the same non-results and take the machine with it.
    if [[ "$class" == infra_unavailable ]]; then
        log "infra_unavailable is a stop, not a result. Abandoning the remaining probes."
        break
    fi
done

# ------------------------------------------------------------------ summary
printf '\n' >&2
log "==== verdicts (${RUN_STARTED}, sha ${GIT_SHA:0:12}) ===="
# Worst class first, so the thing to read is the first line.
for i in "${!VERDICT_NAMES[@]}"; do
    printf '%s\t%s\t%s\t%s\t%s\n' \
        "$(class_severity "${VERDICT_CLASSES[$i]}")" "${VERDICT_CLASSES[$i]}" \
        "${VERDICT_NAMES[$i]}" "${VERDICT_SECS[$i]}" "${VERDICT_PATHS[$i]}"
done | sort -rn -k1,1 | while IFS=$'\t' read -r _sev cls nm secs path; do
    printf '[regress] %-20s %-18s %4ss  %s\n' "$nm" "$cls" "$secs" "$path" >&2
done

skipped=$((${#CORPUS[@]} - ${#VERDICT_NAMES[@]}))
((skipped > 0)) && log "$skipped probe(s) not run"

exit_code="${CLASS_RANK[$worst_class]:-9}"
log "worst class: $worst_class (exit $exit_code)"
exit "$exit_code"
