#!/usr/bin/env bash
# The Phase-1 in-game regression tier (issue #23, ADR-0016; a pool of slots since
# #47, ADR-0028). Design: docs/regression-tier.md. Invoked as
# `just regress [--host <name>] [--slots <n>] [--wait <secs>] [--issues <n,...>] [--list] [name...]`.
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
# Which machine this pass executes on (ADR-0032, #51). One value today, `local`,
# reached with no transport; the point of naming it at all is that every
# host-touching operation below goes through the handle rather than through this
# machine, so a second host is a row in `spike/hosts.sh` and not a rewrite here.
# Validated before anything is launched — see the pre-flight.
# shellcheck source=spike/hosts.sh
source "$REPO/spike/hosts.sh"
# The headed Windows client, machine-scoped rather than pool-scoped (#127): the
# tail below serialises this pool's two client probes, and this serialises the
# tail against every other pool on the machine.
# shellcheck source=spike/client-lock.sh
source "$REPO/spike/client-lock.sh"
# HOST is born once, at the pre-flight's `cti_host_resolve` below: an
# unvalidated copy used to be taken here too, and two birth-points for one name
# is how a refused host still gets read somewhere (#162). The evidence root
# does not wait for it because it does not depend on it: the path is
# host-invariant by construction (#161) — `~/.arma-cti` on whichever host owns
# the state.
RUNS_DIR="$(cti_host_runs)"
KEEP_PASSES=3
KEEP_POOLS=5
INTERRUPTED_RETENTION_DAYS=7
# ADR-0028 recommends three, and #47 measured that three fit. Changing this
# number is a measurement, not a preference: the RAM figure is in
# docs/regression-tier.md and the pool records its own peak in every run.
DEFAULT_SLOTS=3
# Overridable so the no-Arma tier can drive the pool's scheduling, bulkheads and
# merge against a stub that prints what the engine would have printed
# (tests/unit/test_pool_scheduling.py). Nothing else sets it.
RUN_SH="${CTI_RUN_SH:-$REPO/spike/run.sh}"
# Overridable so the no-Arma tier can exercise the caller's fail-closed parsing
# without changing the merge used by the live tier.
POOL_MERGE_TOOL="${CTI_POOL_MERGE:-$REPO/tools/pool_merge.py}"
# Overridable for the same reason and by the same tier. Reclamation is the one
# part of a slot's bring-up that touches the real machine's port space and
# process table, so the no-Arma tier cannot produce a *failed* reclaim to test
# the response to one: `cti_slot_reclaim` refuses to sweep anything from a
# redirected state directory, and a test that made it sweep would be #124 — the
# unit suite killing the live tier — on purpose. So the command is substitutable
# and the response is what gets tested (#133). Nothing but the tests sets it.
SLOT_RECLAIM="${CTI_SLOT_RECLAIM:-cti_slot_reclaim}"
# Overridable for the same reason and by the same tier (#133's pattern, #147):
# the real reading is /proc/meminfo on the live host, and the no-Arma tier
# cannot make that fail mid-run to test the response to a reading that could
# not be taken. Both the pre-flight and the between-probes re-check go through
# this one name, so the two readings cannot drift apart. Nothing but the tests
# sets it.
SLOT_MEM_READER="${CTI_SLOT_MEM_READER:-cti_slot_mem_available_mb}"

# The watchdog above `run.sh`, one per probe (#144). Nothing used to bound a
# probe at all: `run.sh` has deadlines on the things it waits *for*, and a hang
# anywhere else — a wedged WSL interop call, a stalled `uv`, a child that would
# not be reaped — wedged this worker with its slot lock held until a human
# noticed. A pool of three turns that into three slots nobody can take.
#
# It sits ABOVE the probe's own window, with headroom, and it bounds
# infrastructure rather than the subject. The window is what the probe's header
# sized to what it measures; the margin is everything around it — a 240 s server
# boot, a 90 s daemon, a mission pack, a 90 s wait for a Windows client to leave
# the process list. So expiry is never "the probe was too slow": a probe that
# outran its own window is a `timeout` typed by `run.sh` minutes earlier. It is
# `infra_unavailable`, which this tier already refuses to read as a result.
#
# CTI_PROBE_WATCHDOG_SECS replaces the sum outright, which is how the no-Arma
# tier drives this. It cannot manufacture a green: a watchdog under a probe's
# window turns that probe into `infra_unavailable`, which is not a result and
# gates nothing.
WATCHDOG_MARGIN="${CTI_PROBE_WATCHDOG_MARGIN:-600}"
# SIGTERM first, so `run.sh`'s own trap tears its world down and releases the
# machine-wide client lock; SIGKILL this long after, for the case where the trap
# is itself what is wedged.
WATCHDOG_KILL_AFTER="${CTI_PROBE_WATCHDOG_KILL_AFTER:-60}"
# GNU timeout's two statuses for "the deadline was reached": the second is what a
# process killed by the follow-up SIGKILL reports.
EXIT_TIMED_OUT=124
EXIT_KILLED=137
# The deadline on every `uv run` this runner makes — the pass pruner and the
# verdict typer per probe, the pool merge once at the end. A bound on
# infrastructure, never on the probe's subject, which has already finished by
# the time any of them runs. `run.sh` bounds its own `uv run`s for the same
# reason and under the same variable (#144).
UV_TIMEOUT="${CTI_UV_TIMEOUT:-300}"
# The starvation watch's cadence (#182, ADR-0055) — the floor *under* a granted
# run. Admission (#125) reads the machine before a lock is taken; the
# between-probes re-check reads it before each launch; neither can see the
# machine sicken while a world is in flight, and a starved world does not fail
# honestly — it forges a plausible class. `base-assault` timed out at 458 s on a
# box at 19 MiB; `campaign-end` and `two-commanders` crashed nodes at 20 MiB;
# all three reds were about the machine and none wore its class. The watch
# polls the same substitutable reader the other two readings use, on the lock
# queue's own cadence. What a trip does is beside the watch itself, below.
MEM_WATCH_SECS="${CTI_SLOT_MEM_WATCH_SECS:-5}"

# One stable exit code per class, and nothing more: the exit code of a run
# says which class to read the table row for. The numbers 1-5 were once also
# the severity order, and the classes added since — engine_drift, schema_stale,
# untyped_harness_failure — took the next free codes rather than renumbering a
# meaning callers already read, so severity now lives only in
# tools/pool_merge.py's CLASS_SEVERITY (#185), which is what the merge's
# summary and its choice of worst class sort by. The in-mission mapping run.sh
# applied joined the same home under #147 (`class-of`), so this exit table is
# the class table's one remaining bash half — deliberately: the paths that
# exit through it include the ones where uv itself is what broke, and an exit
# code that must be produced when Python cannot run cannot be asked of Python.
# Any further consolidation is #92's.
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
log() { printf '[regress] %s\n' "$*" >&2; }

# A usage or setup refusal, before anything is measured: not a verdict, so its
# exit code must not collide with a class's. `exit 2` here used to read as
# `timeout` to any caller of the exit-code table above (#147); CTI_EXIT_USAGE
# (spike/host-guard.sh, the exit codes' one bash home) is sysexits' EX_USAGE.
die() {
    log "$*"
    exit "$CTI_EXIT_USAGE"
}

# ------------------------------------------------------------------ arguments
ORIGINAL_ARGS=("$@")
WAIT_SECS=0
SELECTED=()
WANT_ISSUES=()
LIST_ONLY=0
WANT_SLOTS="$DEFAULT_SLOTS"
# A function so the parse's temporaries are locals rather than script state
# that outlives the parse; everything assigned above stays global on purpose.
parse_args() {
    local spec n
    while (($# > 0)); do
        case "$1" in
        --host)
            CTI_TIER_HOST="${2:-}"
            shift 2
            ;;
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
}
parse_args "$@"

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
# nullglob, or an empty probes directory hands the loop the literal pattern:
# basename would strip it to `*`, ALL would hold one phantom probe, and the
# "no probes" die below would never fire. The process substitution inherits the
# option; it is turned back off before anything else globs.
shopt -s nullglob
mapfile -t ALL < <(for f in "$PROBE_DIR"/*.sqf; do basename "$f" .sqf; done | sort)
shopt -u nullglob
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

CORPUS_NEEDS_HEADED=0
for name in "${CORPUS[@]}"; do
    [[ "$(header_of "$PROBE_DIR/$name.sqf" env)" == *CTI_WINDOWS_CLIENT=1* || \
        "$(header_of "$PROBE_DIR/$name.sqf" env)" == *CTI_HEADED_CLIENT=1* ]] &&
        CORPUS_NEEDS_HEADED=1
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

# One line per refusal, under the tier's own evidence root: a typed refusal
# that went only to stderr survives exactly as long as the invoker keeps its
# captured output (#147), and "why did my run refuse last night?" deserves a
# better answer than scrollback. Best-effort by design — a refusal that cannot
# be recorded still refuses, which is the right half of fail-closed — and
# bounded, because unbounded is unbounded: the newest 200 lines are kept once
# the file passes 400.
record_refusal() {
    local class="$1" detail="${2//$'\n'/ }" file="$RUNS_DIR/refusals.log" lines
    {
        mkdir -p "$RUNS_DIR" &&
            printf '%s\t%s\t%s\t%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$class" "$detail" "$POOL_LABEL" >>"$file"
    } 2>/dev/null || return 0
    lines="$(wc -l <"$file" 2>/dev/null)" || return 0
    if ((lines > 400)); then
        tail -n 200 "$file" >"$file.tmp" 2>/dev/null && mv "$file.tmp" "$file" 2>/dev/null
    fi
    return 0
}

# ------------------------------------------------------------------ pre-flight
# The host this pass is aimed at, checked before anything is launched. A name the
# tier does not know is `infra_unavailable` rather than a fallback to this
# machine: a run that silently executed here and reported itself as machine B's
# would be the one failure the host seam exists to make impossible.
if ! HOST="$(cti_host_resolve)"; then
    {
        printf '\n[regress] no such host: %s. Not a result.\n' "${CTI_TIER_HOST:-local}"
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=CTI_TIER_HOST names a host the tier does not know\n'
        printf 'host=%s\n' "${CTI_TIER_HOST:-local}"
    } >&2
    record_refusal infra_unavailable "CTI_TIER_HOST names a host the tier does not know: ${CTI_TIER_HOST:-local}"
    exit "${CLASS_RANK[infra_unavailable]}"
fi

# An SSH host executes the entire pass below one remote channel. Nothing after
# this branch may acquire a local slot for remote work: a missing transport is
# infra_unavailable, never permission to continue on the initiating machine.
if [[ "${CTI_REMOTE_ACTIVE:-0}" != 1 && "$(cti_host_transport "$HOST")" == ssh ]]; then
    cti_host_remote_regress "$HOST" "$REPO" "${ORIGINAL_ARGS[@]}"
    remote_status=$?
    if [[ "$remote_status" == "${CLASS_RANK[infra_unavailable]}" ]]; then
        record_refusal infra_unavailable "remote pass on $HOST did not produce an interpretable result"
        printf 'verdict=FAIL\nfailure_class=infra_unavailable\n' >&2
        printf 'failure_detail=remote pass on %s did not produce an interpretable result\n' "$HOST" >&2
    fi
    exit "$remote_status"
fi

HOST_SLOTS="$(cti_host_slots "$HOST")"
((WANT_SLOTS <= HOST_SLOTS)) ||
    die "--slots $WANT_SLOTS exceeds host $HOST's declared $HOST_SLOTS server slot(s)"
if ((CORPUS_NEEDS_HEADED == 1)) && ! cti_host_headed_client "$HOST"; then
    record_refusal infra_unavailable "selected corpus requires a headed client; host $HOST declares none"
    exit "${CLASS_RANK[infra_unavailable]}"
fi

# The watchdog's own dependency, checked before a lock is taken and refused
# rather than skipped (#144). A pool that could not bound its probes is a pool
# whose first hang costs every slot it holds, and "the bound could not be set" is
# the same non-result as "the machine is busy" — #41's rule, applied to the thing
# that enforces deadlines rather than to a guard.
if ! command -v timeout >/dev/null 2>&1; then
    {
        printf '\n[regress] timeout(1) is missing, so no watchdog can be set above run.sh. Not a result.\n'
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=timeout(1) is not on PATH; the per-probe watchdog cannot be set\n'
    } >&2
    record_refusal infra_unavailable "timeout(1) is not on PATH; the per-probe watchdog cannot be set"
    exit "${CLASS_RANK[infra_unavailable]}"
fi

# The host guard covers the whole machine and therefore the whole pool: what it
# protects is not a port block but a person. `arma3_x64.exe` on the Windows host
# means a play session may be live, and no number of slots makes it acceptable to
# load the machine underneath one. Asked before a single lock is taken, so a
# refusal costs the caller no place in any queue (#41; it fails closed by design).
#
# Per host and gated on the role since #51: this one is `human`, so it is asked
# exactly as before. A host the tier owns is not asked, because guarding the
# tier's own client against the tier would stop every run that used it (ADR-0032).
#
# The one thing that changed with #127 is what happens on a refusal, and it
# changed in the caller rather than in the guard. A client in the process list
# while *another run holds the machine-wide client lock* is that run's client,
# not a play session — the holder does not release until its own client has left
# the list — so it is something to queue behind for the bounded `--wait` this
# pool was given, exactly as a busy slot is. With no wait asked for, or with the
# lock free, the refusal stands unchanged: an unheld client in the list is the
# human's, and the guard is still the only thing that decides that.
#
# And it queues in a loop rather than asking twice (#151). The wait establishes
# only that the lock was free at the instant it was read; a third agent's tail
# can take the client in the gap between that and the guard being re-asked, and
# a single re-ask turned a caller who asked to queue for `--wait` seconds into a
# refusal on the second contender it met. The loop re-enters with what is left of
# the deadline, so the queue is still bounded by exactly the wait that was asked
# for, and every pass re-derives the two facts that make queueing legitimate: a
# client is in the list, and somebody else holds the lock.
#
# The loop itself lives in spike/client-lock.sh (#196), because this is not the
# only place that asks: `run.sh` asks again per probe, on the bring-up, and did
# not queue — which is how a pool four probes in abandoned the other nineteen
# when a sibling agent's client probe started. Same question, same code; the
# rendering and the log prefix are this caller's, the decision is not.
#
# `block` and stderr: the guard's lines are read by whoever is watching the pool,
# and the durable line below is what the refusal log gets.
guard_block=""
if guard_block="$(cti_host_guard_or_queue "$HOST" block "$WAIT_SECS" log)"; then
    printf '%s\n' "$guard_block" >&2
else
    # The guard's own words went to stderr above; this is the durable line. Which
    # of the three it was, where the box can still tell us: a busy client lock
    # names its holder and its age here rather than only in output the invoker
    # has to have kept, so a refusal that turns out to be somebody's wedged run
    # is diagnosable from the refusal log alone (#153).
    printf '%s\n' "$guard_block" >&2
    guard_reason="$(sed -n 's/.*failure_reason=\([^ ]*\).*/\1/p' <<<"$guard_block" | head -1)"
    refusal="the host guard refused $HOST — a play session may be live, another run held the Windows client, or the check could not run"
    [[ -n "$guard_reason" ]] && refusal="$refusal; failure_reason=$guard_reason"
    cti_client_lock_busy && refusal="$refusal; the client lock was held — $(cti_client_lock_summary)"
    record_refusal infra_unavailable "$refusal"
    exit "${CLASS_RANK[infra_unavailable]}"
fi

# ------------------------------------------------------------- memory pre-flight
# The second guard on the whole pool, and the same shape as the first: asked
# before a lock is taken, answered from a reading, and fail-closed (#125). A
# slot lock cannot tell a run that the machine is already full, and on
# 2026-08-02 a second pool started into one that was and produced two
# `node_crashed` non-results twenty minutes later. The reading is logged whether
# it refuses or not, because "how close was that?" is a question every pool run
# should be able to answer from its own log.
#
# `--wait` queues on this exactly as it queues on the locks, and for the same
# stated reason: it "sleeps until somebody else's run ends, which is the whole of
# what --wait is for". A full machine is somebody else's run as surely as a held
# lock is — met on 2026-08-02, when a `--wait 1800` was refused in two seconds
# because a sibling agent's three worlds were up. Refusing a caller who asked to
# queue, on a condition that clears when the thing it is queueing behind
# finishes, is the wrong half of fail-closed.
memory_preflight() {
    local deadline=$((SECONDS + WAIT_SECS)) said=0
    while :; do
        MEM_AVAILABLE_MB="$("$SLOT_MEM_READER")" || return 2
        MEM_FIT="$(cti_slot_mem_fit "$WANT_SLOTS" "$MEM_AVAILABLE_MB")"
        ((MEM_FIT > 0)) && return 0
        ((SECONDS < deadline)) || return 1
        ((said == 0)) && {
            log "memory: ${MEM_AVAILABLE_MB} MiB available on $HOST, under the $(cti_slot_mem_floor_mb 1) MiB one slot needs — waiting up to ${WAIT_SECS}s for the machine"
            said=1
        }
        sleep 5
    done
}
memory_preflight
case $? in
2)
    {
        printf '\n[regress] the memory pre-flight could not read %s'"'"'s memory.\n' "$HOST"
        printf '[regress] A check that could not run is not a check that passed.\n'
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=could not read MemAvailable on %s\n' "$HOST"
    } >&2
    record_refusal infra_unavailable "could not read MemAvailable on $HOST"
    exit "${CLASS_RANK[infra_unavailable]}"
    ;;
esac
log "memory: ${MEM_AVAILABLE_MB} MiB available on $HOST; $WANT_SLOTS slot(s) want $(cti_slot_mem_floor_mb "$WANT_SLOTS") MiB (${CTI_SLOT_MEM_PER_SLOT_MB} MiB a slot + ${CTI_SLOT_MEM_HEADROOM_MB} MiB headroom)"
if ((MEM_FIT == 0)); then
    {
        printf '\n[regress] %s has %s MiB available and one slot needs %s MiB — this is infra_unavailable, not a result.\n' \
            "$HOST" "$MEM_AVAILABLE_MB" "$(cti_slot_mem_floor_mb 1)"
        printf '[regress] Nothing was launched. A pool started under the floor produces non-results N at a time (#125).\n'
        ((WAIT_SECS > 0)) && printf '[regress] waited %ss for the machine and gave up.\n' "$WAIT_SECS"
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=%s MiB available, floor for one slot is %s MiB\n' \
            "$MEM_AVAILABLE_MB" "$(cti_slot_mem_floor_mb 1)"
        printf 'host=%s\n' "$HOST"
        printf 'mem_available_mb=%s\n' "$MEM_AVAILABLE_MB"
    } >&2
    record_refusal infra_unavailable "$MEM_AVAILABLE_MB MiB available on $HOST, floor for one slot is $(cti_slot_mem_floor_mb 1) MiB"
    exit "${CLASS_RANK[infra_unavailable]}"
fi
if ((MEM_FIT < WANT_SLOTS)); then
    # The middle answer. A smaller pool is a slower run, not a wrong one, and it
    # is a great deal better than N worlds sharing a machine that fits N-1.
    log "asked for $WANT_SLOTS slot(s) but $MEM_AVAILABLE_MB MiB fits $MEM_FIT — running at N=$MEM_FIT"
    WANT_SLOTS="$MEM_FIT"
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
        printf '\n[regress] every slot of the Arma tier on %s is busy — this is infra_unavailable, not a result.\n' "$HOST"
        for ((n = 0; n <= CTI_SLOT_MAX; n++)); do
            printf '[regress] slot %s holder:\n' "$n"
            cti_slot_holder "$n"
            # And who is actually holding the descriptor, which is not always who
            # the metadata says. A dead pool's server, headless client or `run.sh`
            # keeps the lock its worker inherited it from (#121), and then the
            # `pid=` beside the lock names a process that no longer exists while
            # the slot stays taken. Reported, not swept: killing a lock holder we
            # do not own is how the no-Arma tier killed the real one (#124), and a
            # human reading this needs the live pids to decide.
            live="$(cti_slot_lock_holders "$n" | tr '\n' ' ' | sed 's/ *$//')"
            printf '    live holders: %s\n' "${live:-none — the lock is free and something else refused it}"
        done
        ((WAIT_SECS > 0)) && printf '[regress] waited %ss and gave up.\n' "$WAIT_SECS"
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=no slot free; see %s\n' "$CTI_SLOT_LOCK_DIR"
        printf 'host=%s\n' "$HOST"
    } >&2
    record_refusal infra_unavailable "no slot free on $HOST; see $CTI_SLOT_LOCK_DIR"
    exit "${CLASS_RANK[infra_unavailable]}"
fi

((${#SLOTS[@]} < WANT_SLOTS)) &&
    log "asked for $WANT_SLOTS slot(s), ${#SLOTS[@]} free — running at N=${#SLOTS[@]}"
log "slots: ${SLOTS[*]}"

# Teardown, installed the moment this run holds anything worth tearing down.
# It used to be installed just before the workers forked, which left every
# failure path between acquisition and there — a failed reclaim of every slot,
# a failed install prep, an evidence directory that could not be created —
# exiting with locks freed only by the kernel and each slot's `.info` file
# left beside a free lock for the next holder to misread (#147).
ram_sampler_pid=""
starve_watch_pid=""
WORKER_PIDS=()

# TERM one launched probe through its watchdog. The pid a worker records is the
# host-seam subshell — `cti_host_exec` is a function call, so `$!` is a bash
# between us and the launch — and signalling it would kill the wrapper while the
# probe ran on. The GNU `timeout` under it is the process that can end the
# flight: it leads the probe's own process group and forwards a received TERM to
# the whole group (run.sh, server, headless client, daemon), so run.sh's own trap
# still tears its world down and releases what it holds, while the subshell
# survives to reap the status the verdict typer reads. The walk is bounded:
# anything deeper than the watchdog is run.sh's own business.
#
# Two consumers: the starvation watch, which stops one starved flight (#182),
# and the teardown below, which stops all of them (#151).
starve_signal() {
    local generation="$1" next pid child comm depth
    for depth in 1 2 3; do
        next=""
        for pid in $generation; do
            for child in $(ps -o pid= --ppid "$pid" 2>/dev/null); do
                comm="$(ps -o comm= -p "$child" 2>/dev/null)"
                if [[ "$comm" == timeout ]]; then
                    kill -TERM "$child" 2>/dev/null
                    return 0
                fi
                next+=" $child"
            done
        done
        generation="$next"
        [[ -n "${generation// /}" ]] || return 1
    done
    return 1
}

pool_teardown() {
    local pid slot
    [[ -n "$ram_sampler_pid" ]] && kill "$ram_sampler_pid" 2>/dev/null
    [[ -n "$starve_watch_pid" ]] && kill "$starve_watch_pid" 2>/dev/null
    # The flights first, and through the watchdog rather than at the worker
    # (#151). Killing a worker subshell ends the `wait` that was holding its
    # probe, not the probe: `run.sh`, its server, its headless client and its
    # daemon are the worker's *descendants*, and a `kill` aimed at this script —
    # unlike Ctrl-C, which the terminal delivers to the whole process group —
    # reached none of them. What that left was up to N engines still bound to
    # this run's slot ports with nobody owning them, recovered only whenever
    # somebody next acquired those slots (ADR-0022) — an unowned-load window
    # with no bound.
    #
    # Nothing is waited on afterwards, and that is not an omission: `run.sh`
    # inherited its worker's slot descriptor, so the slot's lock stays held for
    # as long as its teardown runs however promptly this script exits (#121).
    # A concurrent run is refused the slot rather than handed one still binding.
    for pid in ${WORKER_PIDS[@]+"${WORKER_PIDS[@]}"}; do starve_signal "$pid"; done
    for pid in ${WORKER_PIDS[@]+"${WORKER_PIDS[@]}"}; do kill "$pid" 2>/dev/null; done
    # The slots that failed to reclaim are released here too. They ran nothing,
    # but this run has held their locks all the way through on purpose (#133):
    # a slot proved not clear is one no concurrent run should be handed while we
    # are still here to say so, and the lock is the only way to say it.
    for slot in ${SLOTS[@]+"${SLOTS[@]}"} ${DIRTY_SLOTS[@]+"${DIRTY_SLOTS[@]}"}; do cti_slot_release "$slot"; done
}

# A signal is not a result, and it has to end the run rather than merely be
# noticed by it. `trap … INT TERM` resumes the interrupted `wait` when the
# handler returns, so the pool used to tear itself down — locks released,
# workers killed — and then carry on scheduling probes onto slots it no longer
# held. Typed `infra_unavailable` because a pass stopped from outside measured
# nothing, and recorded, so the refusal outlives the invoker's captured output
# (#147 item 7).
pool_signalled() {
    trap - EXIT INT TERM
    log "SIG$1 stopped this pass — tearing down; a run that was signalled measured nothing"
    pool_teardown
    record_refusal infra_unavailable "SIG$1 stopped the pool before it could report"
    exit "${CLASS_RANK[infra_unavailable]}"
}
trap pool_teardown EXIT
trap 'pool_signalled INT' INT
trap 'pool_signalled TERM' TERM

# Stale state, per slot, on acquire rather than on release (ADR-0022, #58, #70).
# The lock frees itself when its holder dies; the holder's server, headless
# client and daemon do not, and they are still on this slot's ports and in this
# slot's install. The next holder clears them, and the next holder is us.
#
# And the reclaim's answer is acted on rather than logged past (#133). #130 taught
# `cti_slot_reclaim` to confirm its SIGKILL, so a non-zero return means a dead
# run's processes are *still* on this slot's ports and in its install — and the
# very next thing this script does with the slot is hand it to `run.sh` to bind
# those ports. Proceeding turns a known dead holder into a bind failure blamed on
# the world: the early clear #130 closed inside the reclaim, still open here.
#
# The slot is dropped and the run goes on, for ADR-0028's reason: fewer slots than
# asked for is a smaller pool, not a failure, so one dirty slot costs a slot
# rather than every other slot's results. Its lock is *kept* — released with the
# others by `pool_teardown` — so no concurrent run walks into a slot we have just
# proved is not clear. When every requested slot fails to reclaim there is no
# smaller pool left and nothing was measured, so the run exits infra_unavailable:
# not a result, per the failure-class table.
#
# What is not done here is poison this run's class when other slots came back
# clear. Every probe still gets a verdict, on a slot whose conditions are
# interpretable, so the corpus is a result; the dirty slot contributed no verdict
# to misread. It is recorded instead — in the log and in `pool.json`'s
# `dirty_slots` — so a smaller pool is never silent.
READY_SLOTS=()
DIRTY_SLOTS=()
DIRTY_DETAIL=()
for slot in "${SLOTS[@]}"; do
    if ! survivors="$("$SLOT_RECLAIM" "$slot")"; then
        first_port="$(cti_slot_port "$slot")"
        DIRTY_SLOTS+=("$slot")
        DIRTY_DETAIL+=("survivors still on ports $first_port-$((first_port + CTI_SLOT_PORT_SPAN - 1))/$(cti_slot_daemon_port "$slot") or in $(cti_slot_install "$slot"): ${survivors:-unnamed}")
        log "slot $slot: reclaim did not come back clear — ${survivors:-survivors unnamed} still holding it; dropping the slot from this pool (infra_unavailable for that slot, not a result from it)"
        continue
    fi
    # Typed, not `die`: slots are held, so this is a failure path out of a run
    # that has taken something — an untyped red on an infra condition, exiting
    # on a code that read as `timeout`, was #147's worst case. The trap above
    # runs the teardown on the way out.
    cti_slot_install_ready "$slot" || {
        {
            printf '\n[regress] could not prepare the install for slot %s — this is infra_unavailable, not a result.\n' "$slot"
            printf '[regress] Nothing was launched.\n'
            printf 'verdict=FAIL\n'
            printf 'failure_class=infra_unavailable\n'
            printf 'failure_detail=install prep failed for slot %s (cti_slot_install_ready); master or clone at fault\n' "$slot"
            printf 'host=%s\n' "$HOST"
        } >&2
        record_refusal infra_unavailable "install prep failed for slot $slot (cti_slot_install_ready)"
        exit "${CLASS_RANK[infra_unavailable]}"
    }
    READY_SLOTS+=("$slot")
done

if ((${#READY_SLOTS[@]} == 0)); then
    {
        printf '\n[regress] every slot this run holds failed to reclaim — this is infra_unavailable, not a result.\n'
        for i in "${!DIRTY_SLOTS[@]}"; do
            printf '[regress] slot %s: %s\n' "${DIRTY_SLOTS[$i]}" "${DIRTY_DETAIL[$i]}"
        done
        printf '[regress] Nothing was launched. A run that binds a surviving holder'"'"'s ports reports the bind, not the holder (#130, #133).\n'
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=slot(s) %s not clear after SIGKILL\n' "${DIRTY_SLOTS[*]}"
        printf 'host=%s\n' "$HOST"
    } >&2
    record_refusal infra_unavailable "slot(s) ${DIRTY_SLOTS[*]} not clear after SIGKILL"
    exit "${CLASS_RANK[infra_unavailable]}"
fi

if ((${#DIRTY_SLOTS[@]} > 0)); then
    log "${#DIRTY_SLOTS[@]} slot(s) not clear (${DIRTY_SLOTS[*]}) — running smaller, at N=${#READY_SLOTS[@]} over slots ${READY_SLOTS[*]}"
fi
SLOTS=("${READY_SLOTS[@]}")

# ------------------------------------------------------------------ evidence
# ADR-0022: a timestamped directory with no verdict is an interrupted holder,
# not a result. Keep it through a generous recovery window, then bound the
# accumulation. Python decides; this process-owning shell deletes, and a
# decision that cannot run deletes nothing (ADR-0049).
prune_interrupted() {
    local doomed status dir
    doomed="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$POOL_MERGE_TOOL" prune-interrupted \
        --runs-dir "$RUNS_DIR" --older-than-days "$INTERRUPTED_RETENTION_DAYS")"
    status=$?
    if ((status != 0)); then
        log "prune-interrupted could not run (exit $status) — deleting nothing"
        return 0
    fi
    while IFS= read -r dir; do
        [[ -n "$dir" && "$dir" == "$RUNS_DIR"/* ]] || continue
        log "pruning old interrupted evidence: $dir"
        rm -rf "$dir"
    done <<<"$doomed"
}

mkdir -p "$RUNS_DIR"
prune_interrupted
RUN_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
# The pid is in the name because two pools are a thing that happens (#127) and
# `date` has one-second resolution: two agents starting inside the same second
# would otherwise share one evidence directory, and with it one `claims/`, and
# each would silently take probes off the other's corpus.
POOL_STAMP="${CTI_REMOTE_RUN_ID:+${CTI_REMOTE_RUN_ID}-}$(date -u +%Y%m%dT%H%M%SZ)-$$"
POOL_OUT="$RUNS_DIR/$POOL_STAMP-pool"
CLAIMS="$POOL_OUT/claims"
STOP_FLAG="$POOL_OUT/stop"
# Typed for the same reason as the install prep above: slots are held, so an
# exit here is a failure path out of a run in flight, not a usage refusal.
mkdir -p "$CLAIMS" || {
    {
        printf '\n[regress] could not create the pool'"'"'s evidence directory %s — this is infra_unavailable, not a result.\n' "$POOL_OUT"
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=could not create %s\n' "$CLAIMS"
        printf 'host=%s\n' "$HOST"
    } >&2
    record_refusal infra_unavailable "could not create the pool evidence directory $CLAIMS"
    exit "${CLASS_RANK[infra_unavailable]}"
}

# The pool's own evidence is bounded the way a probe's passes are — green runs
# to the last KEEP_POOLS, failures kept until the issue that consumed them
# closes. The old prune was count-only, so the starvation episodes' primary RAM
# traces were pruned while their issues were still open (#182, finding 3 of the
# filing); which pools read green is decided in the merge's Python home off the
# `worst_class` pool.json now records, and this shell does the deleting.
# Failing closed here means deleting nothing: a pool kept an extra run is
# recoverable, evidence deleted by a pruner that could not read is not.
prune_pools() {
    local doomed status dir
    doomed="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$POOL_MERGE_TOOL" prune-pools \
        --runs-dir "$RUNS_DIR" --keep "$KEEP_POOLS")"
    status=$?
    if ((status != 0)); then
        log "prune-pools could not run (exit $status) — deleting nothing"
        return 0
    fi
    while IFS= read -r dir; do
        # Structural, as prune_passes' check is: the pruner can only ever name
        # pool directories under the runs directory, never this run's own.
        [[ -n "$dir" && "$dir" == "$RUNS_DIR"/*-pool ]] || continue
        [[ "$dir" == "$POOL_OUT" ]] && continue
        log "pruning old green pool: $dir"
        rm -rf "$dir"
    done <<<"$doomed"
}
prune_pools

# Passes pruned before the probe runs rather than after, so a run that dies
# halfway still leaves the directory bounded, and so a failure's evidence is
# never pruned by the run that produced it. Which directories have outlived
# retention is decided in the merge's Python home (#185, ADR-0049) — room left
# for the pass this run is about to write, failures kept, a verdict that
# cannot be read never decided on — and this shell does the deleting. Failing
# closed here means deleting nothing: a pass kept an extra run is recoverable,
# evidence deleted by a pruner that could not read is not.
prune_passes() {
    local name="$1" doomed status dir
    # Nothing to decide without at least one earlier run of this probe; the
    # no-Arma pool suite would otherwise pay one uv start-up per probe to be
    # told an empty directory is empty.
    compgen -G "$RUNS_DIR/*-$name" >/dev/null || return 0
    doomed="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$POOL_MERGE_TOOL" prune-passes \
        --runs-dir "$RUNS_DIR" --probe "$name" --keep "$KEEP_PASSES")"
    status=$?
    if ((status != 0)); then
        log "prune-passes could not run for $name (exit $status) — deleting nothing"
        return 0
    fi
    while IFS= read -r dir; do
        # Structural, as the old glob was: the pruner can only ever name
        # children of the runs directory, and rm -rf holds it to that.
        [[ -n "$dir" && "$dir" == "$RUNS_DIR"/* ]] || continue
        log "pruning old pass: $dir"
        rm -rf "$dir"
    done <<<"$doomed"
}

# ------------------------------------------------------------------ RAM
# ADR-0028's N=3 figure was arithmetic from a measured N=2, and its own
# overturning conditions say the third slot is not trusted until the number has
# been measured. So every pool run measures it, and the number lands in the run's
# evidence rather than in a session's memory. (`ram_sampler_pid` is initialised
# beside the trap, which has to be able to read it from the moment it exists.)
start_ram_sampler() {
    (
        # The same wall the worker builds below, for the same reason and one
        # step earlier (#138). This subshell inherits every slot's lock
        # descriptor, and so does the `sleep` it forks between samples — which
        # teardown's `kill` does not reach, so the lock stayed held for up to the
        # sample interval after `regress.sh` had exited. Measured: an ask for a
        # released slot in the first three seconds after teardown was refused,
        # with descriptors surviving 3.6–4.4 s.
        #
        # The fix is not to hold rather than to kill and confirm (#121 over
        # #130): a sampler needs no lock at all, and a descriptor never held
        # cannot outlive anything. Closing here also covers the `awk` and `ps`
        # children, which inherit from this subshell rather than from the pool.
        for slot in ${SLOTS[@]+"${SLOTS[@]}"} ${DIRTY_SLOTS[@]+"${DIRTY_SLOTS[@]}"}; do
            cti_slot_close "$slot"
        done
        # What of the tier is *ours*, by the values this pool's slots already
        # own (#182): the tier column stays machine-wide — the right scope for
        # a ceiling question — and the own column is what lets a peak be read
        # without reconstructing the night's schedule of sibling pools.
        local pool_pattern
        pool_pattern="$(cti_slot_pool_ps_pattern ${SLOTS[@]+"${SLOTS[@]}"})"
        printf 'epoch\tmem_used_kb\tmem_available_kb\ttier_rss_kb\tpool_rss_kb\n'
        while :; do
            # Read on the host under load, through the handle: the number that
            # matters is that machine's memory, and the file the answer lands in
            # is on the machine that started the run. Redirections stay on this
            # side on purpose — for a remote host that is evidence pull-back,
            # which ADR-0032 defers to the metal.
            cti_host_exec "$HOST" awk -v now="$(date +%s)" '
                /^MemTotal:/     { total = $2 }
                /^MemAvailable:/ { avail = $2 }
                END { printf "%s\t%s\t%s\t", now, total - avail, avail }
            ' /proc/meminfo
            # The tier's share, so a peak can be attributed rather than only
            # observed — twice over since #182: machine-wide (the engine by
            # its comm, the daemon by its command line, because it runs as a
            # python interpreter under `uv`) and this pool's own, by the
            # pattern above. The listing is read on the host; the arithmetic
            # is ours.
            #
            # cti_slot_rss_kb finishes the row the awk above deliberately left
            # open: the meminfo printf ends on a tab with no newline, and its
            # "\n" is the row's only one. Two commands, one TSV line — reorder
            # them, or "fix" either printf, and every row breaks in the reader.
            cti_host_exec "$HOST" ps -eo rss=,comm=,args= 2>/dev/null |
                cti_slot_rss_kb "$pool_pattern"
            sleep 3
        done
    ) >"$POOL_OUT/ram.tsv" 2>/dev/null &
    ram_sampler_pid=$!
}

# ------------------------------------------------------------ the starvation watch
# The floor under a granted run (#182, ADR-0055), watching for what neither the
# admission reading nor the between-probes re-check can see: the machine
# sickening while a world is in flight — another agent's pool arriving, or the
# OS itself (the #164 cluster was Windows OS-drive exhaustion). The reading is
# the same substitutable reader and the same running floor as the re-check,
# because the question is the same — is any margin left at all? — and 512 MiB
# separates every healthy trough on record (1,014 MiB at its lowest) from both
# starvation episodes (19–40 MiB) by an order of magnitude each way.
#
# A trip stops the pool AND its flights. Stopping work in flight is the
# bulkhead rule's one sanctioned exception, and the reasoning is the rule's
# own: interrupting a healthy world would manufacture a non-result, but a
# starved world's result is already a non-result wearing a plausible class,
# and letting it run to term only launders the forgery into `timeout` or
# `node_crashed`. Each stopped claim gains a `starved` marker, which the
# verdict typer reads above every other rung — the probe is
# `infra_unavailable`, stop, not a result. Verdicts that completed before the
# trip stand: their flights ran on the machine the between-probes reading
# admitted them to.
#
# Two deliberate asymmetries. A reader failure is logged and NOT acted on:
# killing granted work on a reading never taken would fabricate the very
# measurement #147 removed, and the between-probes re-check already stops new
# work on an unreadable machine. And a trip needs a flight to stop — a claim
# with a launch pid and no `done` — so a reading that collapses with nothing
# in flight is the between-probes re-check's to answer at the next launch,
# never a post-hoc stop over a corpus that finished measuring.
start_starvation_watch() {
    (
        # No lock is the watch's to hold — #138's sampler rule, one process over.
        for slot in ${SLOTS[@]+"${SLOTS[@]}"} ${DIRTY_SLOTS[@]+"${DIRTY_SLOTS[@]}"}; do
            cti_slot_close "$slot"
        done
        local avail said_unreadable=0 tripped=0 claim name in_flight
        while :; do
            sleep "$MEM_WATCH_SECS"
            if ! avail="$("$SLOT_MEM_READER")"; then
                ((said_unreadable)) || log "the starvation watch could not read the machine's memory — watching on; the between-probes re-check stops new work on an unreadable machine"
                said_unreadable=1
                continue
            fi
            said_unreadable=0
            in_flight=()
            for claim in "$CLAIMS"/*/pid; do
                [[ -f "$claim" && ! -f "${claim%/pid}/done" ]] || continue
                in_flight+=("${claim%/pid}")
            done
            if ((avail >= CTI_SLOT_MEM_RUNNING_FLOOR_MB || ${#in_flight[@]} == 0)); then
                # Nothing left to stop after a trip: the watch's work is done.
                ((tripped)) && exit 0
                continue
            fi
            if ((tripped == 0)); then
                tripped=1
                log "starvation: $avail MiB available, under the ${CTI_SLOT_MEM_RUNNING_FLOOR_MB} MiB running floor, with ${#in_flight[@]} probe(s) in flight — stopping the pool and its flights (#182, ADR-0055)"
                # Read by the merge, as the between-probes stop's is: the
                # pool-level class rides this file. An existing stop flag is
                # not clobbered — the first story is the story.
                printf '%s\n' "$avail" >"$POOL_OUT/mem-stop"
                if [[ ! -f "$STOP_FLAG" ]]; then
                    printf 'only %s MiB available with %s probe(s) in flight; the running floor is %s MiB — the pool and its flights were stopped (#182, ADR-0055)\n' \
                        "$avail" "${#in_flight[@]}" "$CTI_SLOT_MEM_RUNNING_FLOOR_MB" >"$STOP_FLAG"
                fi
            fi
            for claim in "${in_flight[@]}"; do
                name="$(basename "$claim")"
                if [[ ! -f "$claim/starved" ]]; then
                    printf '%s MiB available, under the %s MiB running floor\n' \
                        "$avail" "$CTI_SLOT_MEM_RUNNING_FLOOR_MB" >"$claim/starved"
                    log "starvation: stopping $name mid-flight — its verdict is infra_unavailable, not a result"
                fi
                # Re-sent every sweep until the flight is gone: a TERM that
                # raced the launch has the next cadence to land, and run.sh's
                # trap is idempotent. A flight that will not die is bounded by
                # its own watchdog either way.
                starve_signal "$(cat "$claim/pid")"
            done
        done
    ) &
    starve_watch_pid=$!
}

# ------------------------------------------------------------------ scheduling
# Longest-job-first, on the probe's own declared window. A window is a deadline
# rather than a measurement, so it is only an estimate of cost — but it is the
# estimate that already lives in the probe, and a table of measured times inside
# the runner would be a second place to forget. What LJF has to get right is the
# tail: `campaign-end` is ~390 s of a ~1,550 s corpus, so a pool that starts it
# late idles every other slot waiting for it. Its 750 s window puts it first.
#
# The headed-client probes are not in that schedule. Every probe declaring
# `CTI_HEADED_CLIENT=1` drives the one headed client on the selected host. On a
# human host the guard is ownership-blind on purpose (#119), so a second slot
# starting while one slot's client is up would stop the corpus. They run
# **serially, in a tail, with the rest of the pool drained**, on the lowest slot
# held. Last rather than first: a human who sits down to play at minute eight
# then costs us the tail rather than the pass.
host_probe() { [[ "$(header_of "$PROBE_DIR/$1.sqf" env)" == *CTI_HEADED_CLIENT=1* ]]; }

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
GIT_SHA="${CTI_REMOTE_GIT_SHA:-$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)}"
if [[ -n "${CTI_REMOTE_GIT_DIRTY:-}" ]]; then
    GIT_DIRTY="$CTI_REMOTE_GIT_DIRTY"
else
    GIT_DIRTY="$(git -C "$REPO" status --porcelain 2>/dev/null | head -1)"
    [[ -n "$GIT_DIRTY" ]] && GIT_DIRTY=true || GIT_DIRTY=false
fi

# One probe, in one slot. This runs inside a worker subshell, so it writes its
# result where the parent can find it and never into a shell variable: a verdict
# that lived in a worker's memory would die with the worker, which is exactly the
# case the dead-slot rule in the merge has to report.
run_probe() {
    local name="$1" slot="$2"
    local file="$PROBE_DIR/$name.sqf"
    local window expect quarantine probe_env stamp out t0 elapsed run_status watchdog
    local typed typer_status detail legs class probe_pid
    local decided decision_status decision_line trip stop_line decision_failure_class
    local -a decision_lines=()
    decision_failure_class=""
    window="$(header_of "$file" window)"
    expect="$(header_of "$file" expect)"
    quarantine="$(header_of "$file" quarantined)"
    probe_env="$(header_of "$file" env)"

    prune_passes "$name"
    stamp="${CTI_REMOTE_RUN_ID:+${CTI_REMOTE_RUN_ID}-}$(date -u +%Y%m%dT%H%M%SZ)"
    out="$RUNS_DIR/$stamp-$name"
    mkdir -p "$out"
    printf '%s\n' "$out" >"$CLAIMS/$name/evidence"
    # Which evidence directory this slot is writing, for the *next* holder of
    # this slot to apply ADR-0022 to: a directory with no verdict.json means the
    # holder was interrupted, and its leftovers are stale state to clear.
    cti_slot_mark_run "$slot" "$out"

    # The bound above `run.sh` for this probe, and the window it sits above, in
    # the pool's own log: a reader asking "was that a hang or a slow probe?"
    # should be able to tell the two deadlines apart without opening this file.
    # See CTI_PROBE_WATCHDOG_SECS at the head of the script for the override.
    watchdog="${CTI_PROBE_WATCHDOG_SECS:-$((window + WATCHDOG_MARGIN))}"
    log "[slot $slot] ---- $name (window ${window}s, watchdog ${watchdog}s${expect:+, expects $expect}${quarantine:+, quarantined $quarantine})"
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

    # The launch, through the host handle: this is the operation that becomes
    # `ssh <host> env …` when a second machine exists (ADR-0032, #53), and the
    # handle travels with it so the run records the host it ran on rather than
    # the host that started it.
    # The watchdog, inside `cti_host_exec` rather than around it: it has to run on
    # the host the probe runs on, or a second machine's hang would be bounded from
    # here and its process tree left alive over there (ADR-0032's seam, #53).
    #
    # The pool's own `--wait`, handed to the probe rather than kept at the door
    # (#196). `run.sh` asks the host guard again on its bring-up, and a queue it
    # cannot reach is the same abandonment the entry guard was given a queue to
    # avoid. The same number, not a share of it: `--wait` is what the caller is
    # prepared to spend waiting for the machine, and the pool already applies it
    # whole at each place it queues — entry, memory, slot, tail — rather than
    # dividing it among them. What the probe does with it is draw down one
    # deadline of its own making, shared between its client-lock acquire and its
    # guard, so the per-probe queue adds no patience of its own to the pool's; at
    # `--wait 0`, the default, it adds none at all and the guard refuses today's
    # refusal.
    cti_host_exec "$HOST" \
        timeout --kill-after="$WATCHDOG_KILL_AFTER" "$watchdog" \
        env ${env_args[@]+"${env_args[@]}"} "${slot_args[@]}" \
        CTI_TIER_HOST="$HOST" \
        CTI_HEADED_CLIENT_DRIVER="$(cti_host_client_driver "$HOST")" \
        CTI_CLIENT_LOCK_WAIT="$WAIT_SECS" \
        CTI_SPIKE_OUT="$out" \
        CTI_MISSION=cti.Stratis \
        CTI_SERVER_CONFIG="$REPO/spike/phase1.cfg" \
        CTI_LOG_PREFIX=CTI \
        CTI_HARNESS_EXTRA="$file" \
        CTI_HARNESS_AWAIT=probe_done \
        CTI_HOLD_TIMEOUT="$window" \
        CTI_PROBE_TIMEOUT="$window" \
        "$RUN_SH" --regress >"$out/regress.log" 2>&1 &
    probe_pid=$!
    # The launch pid, beside the claim, for the starvation watch (#182): a
    # flight the watch has to stop is found here, and signalled through the
    # `timeout` under this pid rather than at it — see starve_signal.
    printf '%s\n' "$probe_pid" >"$CLAIMS/$name/pid"
    wait "$probe_pid"
    run_status=$?
    elapsed=$(($(date +%s) - t0))

    # What happened is now a decision rather than a process, so it is decided in
    # Python under pytest rather than here (#171, ADR-0049): the watchdog rule,
    # the untyped-red rule, `expect:` inversion and quarantine live in
    # `tools/probe_verdict.py`, which reads `results.env`, writes `verdict.json`
    # and hands back the class this loop acts on. A wrong class is by definition
    # a harness bug (#83), and this is what makes one a red `just unit` rather
    # than an in-world discovery. Bounded like every `uv run` `run.sh` makes
    # (#144), and checked at its site per the `-e` note up top.
    typed="$(
        cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python tools/probe_verdict.py \
            --probe "$name" \
            --results "$out/results.env" \
            --verdict-json "$out/verdict.json" \
            --run-status "$run_status" \
            --window "$window" \
            --watchdog "$watchdog" \
            --margin "$WATCHDOG_MARGIN" \
            --elapsed "$elapsed" \
            --expect "$expect" \
            --quarantined "$quarantine" \
            --starved "$(cat "$CLAIMS/$name/starved" 2>/dev/null)" \
            --issues "$(header_of "$file" issues)" \
            --stamp "$stamp" \
            --git-sha "$GIT_SHA" \
            --git-dirty "$GIT_DIRTY" \
            --slot "$slot" \
            --host "$HOST" \
            --evidence "$out" \
            2>>"$out/regress.log"
    )"
    typer_status=$?
    if ((typer_status == 0)); then
        class="$(sed -n 's/^class=//p' <<<"$typed" | tail -1)"
        detail="$(sed -n 's/^detail=//p' <<<"$typed" | tail -1)"
        legs="$(sed -n 's/^legs=//p' <<<"$typed" | tail -1)"
    else
        # The typer itself could not run, so this probe's outcome was never
        # read. A typer `timeout` killed is the #41 shape — a check that could
        # not run is not a check that passed — and infra_unavailable; a typer
        # that ran and failed left the red untyped, which is a harness bug and
        # reported as one. That call is this site's to make (ADR-0049's own
        # mechanics); the fallback verdict.json it implies — the least the
        # merge reads, so a slot that is fine is not reclaimed as dead — has
        # one writer, the merge's own home (#185). If that writer cannot run
        # either, uv is broken beyond this probe: the merge will not run
        # either, and the run fails closed there rather than green here.
        if ((typer_status == EXIT_TIMED_OUT || typer_status == EXIT_KILLED)); then
            class=infra_unavailable
            detail="the verdict typer did not finish within ${UV_TIMEOUT}s (uv run tools/probe_verdict.py); see $out/regress.log"
        else
            class=untyped_harness_failure
            detail="the verdict typer failed (exit $typer_status) — harness bug; see $out/regress.log"
        fi
        legs=""
        (cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$POOL_MERGE_TOOL" fallback-verdict \
            --probe "$name" --class "$class" --detail "$detail" --elapsed "$elapsed" \
            --evidence "$out" --verdict-json "$out/verdict.json") 2>>"$out/regress.log" ||
            log "[slot $slot]      the fallback verdict writer failed too — the merge will read $name as not a result"
    fi

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
    # non-results N at a time. And two consecutive `node_crashed` verdicts are a
    # world failing systemically — one bad `.so`, one broken `CfgFunctions` —
    # which a pool hammers N times as hard as a serial run did (#72, #58's
    # reading of it). The decision is made in Python (a threshold and a run of
    # classes is past ADR-0049's line) and only the flag is written here, because
    # flag files coordinating workers are the shell's half of that line. Neither
    # stop kills a probe already in flight: interrupting a running world would
    # itself manufacture the non-result being avoided.
    # First writer wins on the stop flag: a probe the starvation watch stopped
    # types infra_unavailable here too, and its generic line overwriting the
    # watch's — which names the reading and the floor — would bury the story a
    # reader acts on (#182).
    if [[ "$class" == infra_unavailable ]]; then
        [[ -f "$STOP_FLAG" ]] ||
            printf 'infra_unavailable in slot %s on %s\n' "$slot" "$name" >"$STOP_FLAG"
    else
        # The completion record the crash breaker reads (#72): one `name<TAB>class`
        # line per finished verdict, in completion order — the only order a pool
        # has. A verdict of any other class between two crashes means the crash
        # is not carrying every world, so the run restarts rather than trips.
        printf '%s\t%s\n' "$name" "$class" >>"$POOL_OUT/completions.tsv"
        decided="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$POOL_MERGE_TOOL" \
            stop-decision --record "$POOL_OUT/completions.tsv" 2>>"$out/regress.log")"
        decision_status=$?
        decision_lines=()
        if ((decision_status == 0)); then
            while IFS= read -r decision_line || [[ -n "$decision_line" ]]; do
                decision_lines+=("$decision_line")
            done <<<"$decided"
            if ((${#decision_lines[@]} == 1)) && [[ "${decision_lines[0]}" == "trip=no" ]]; then
                trip=no
                stop_line=""
            elif ((${#decision_lines[@]} == 2)) && [[ "${decision_lines[0]}" == "trip=yes" ]] &&
                [[ "${decision_lines[1]}" == stop_line=* ]]; then
                stop_line="${decision_lines[1]#stop_line=}"
                if [[ -n "$stop_line" ]]; then
                    trip=yes
                else
                    trip=yes
                    decision_failure_class=untyped_harness_failure
                    stop_line="the stop decision output was malformed — stopping rather than running past it"
                fi
            elif ((${#decision_lines[@]} == 3)) && [[ "${decision_lines[0]}" == "trip=yes" ]] &&
                [[ "${decision_lines[1]}" == stop_line=* ]] &&
                [[ "${decision_lines[2]}" == failure_class=* ]]; then
                stop_line="${decision_lines[1]#stop_line=}"
                decision_failure_class="${decision_lines[2]#failure_class=}"
                if [[ -n "$stop_line" ]] &&
                    [[ "$decision_failure_class" == infra_unavailable ||
                        "$decision_failure_class" == untyped_harness_failure ]]; then
                    trip=yes
                else
                    trip=yes
                    decision_failure_class=untyped_harness_failure
                    stop_line="the stop decision output was malformed — stopping rather than running past it"
                fi
            else
                trip=yes
                decision_failure_class=untyped_harness_failure
                stop_line="the stop decision output was malformed — stopping rather than running past it"
            fi
        else
            # Fail closed in the protective direction (ADR-0049's caller rule):
            # an unread stop decision stops the pool with the failure named,
            # rather than leaving it to hammer a world that may be crashing
            # every time. The same reading the verdict typer's failure gets.
            trip=yes
            decision_failure_class=infra_unavailable
            stop_line="the stop decision could not be read (tools/pool_merge.py stop-decision exited $decision_status) — stopping rather than running past it"
        fi
        if [[ -n "$decision_failure_class" ]]; then
            # A stop caused by an unreadable decision is itself a result-class
            # failure; otherwise an all-pass pool could stop safely but still
            # exit green after the merge.
            printf '%s\n' "$decision_failure_class" >"$POOL_OUT/stop-decision-failure"
        fi
        if [[ "$trip" == yes && ! -f "$STOP_FLAG" ]]; then
            printf '%s\n' "$stop_line" >"$STOP_FLAG"
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
    local cand name sibling avail
    # A worker inherits every slot's lock descriptor from the pool that forked
    # it, and `flock` frees a lock only when the last descriptor closes. Holding
    # a sibling's lock would make a dead slot look occupied by us — so a worker
    # keeps its own slot's descriptor and lets go of the rest. Bulkheads are
    # walls, and an inherited descriptor is a hole in one.
    # The slots that failed to reclaim are in this list too: a worker has no
    # business holding one, and the pool parent's own descriptor is what keeps
    # that slot out of a concurrent run's hands (#133).
    for sibling in "${SLOTS[@]}" ${DIRTY_SLOTS[@]+"${DIRTY_SLOTS[@]}"}; do
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
        # Re-read the machine's memory between probes, not only at bring-up
        # (#125). It costs one `awk` over `/proc/meminfo` per probe against a
        # world that takes minutes, and the thing it catches is the case the
        # bring-up reading cannot: somebody else — another pool, a build, a
        # browser — arriving after we started. The floor here is the running one
        # rather than the bring-up one, because N-1 worlds are already up and
        # counted; what is being asked is whether any margin is left at all.
        #
        # It stops the pool taking *new* work rather than interrupting the work
        # in flight, which is exactly what `infra_unavailable` already means to
        # this loop: interrupting a running world would manufacture the
        # non-result being avoided.
        # Read, never fabricated (#147): `|| echo 0` here used to conflate
        # "the reading failed" with "0 MiB available", so the stop was right
        # and the recorded detail invented a measurement never taken. A
        # reading that could not be taken stops the pool the same way — a
        # check that could not run is not a check that passed (#41) — and the
        # record says which of the two happened.
        if ! avail="$("$SLOT_MEM_READER")"; then
            log "[slot $slot] the memory reading could not be taken before $name — stopping new work rather than launching blind"
            printf 'the memory reading could not be taken before %s in slot %s — a check that could not run is not a check that passed\n' \
                "$name" "$slot" >"$STOP_FLAG"
            printf 'unreadable\n' >"$POOL_OUT/mem-stop"
            rmdir "$CLAIMS/$name" 2>/dev/null
            break
        fi
        if ((avail < CTI_SLOT_MEM_RUNNING_FLOOR_MB)); then
            log "[slot $slot] $avail MiB available, under the ${CTI_SLOT_MEM_RUNNING_FLOOR_MB} MiB running floor — not launching $name into a machine with no margin"
            printf 'only %s MiB available before %s in slot %s; the running floor is %s MiB\n' \
                "$avail" "$name" "$slot" "$CTI_SLOT_MEM_RUNNING_FLOOR_MB" >"$STOP_FLAG"
            # Read by the merge. No probe will carry this class in a verdict —
            # the whole point is that none launched — so the pool has to raise it
            # itself, or a run that stopped for the machine exits green.
            printf '%s\n' "$avail" >"$POOL_OUT/mem-stop"
            rmdir "$CLAIMS/$name" 2>/dev/null
            break
        fi
        printf '%s\n' "$slot" >"$CLAIMS/$name/slot"
        run_probe "$name" "$slot"
    done
}

log "corpus: ${CORPUS[*]}"
log "sha: $GIT_SHA dirty: $GIT_DIRTY started: $RUN_STARTED"
((${#PARALLEL_JOBS[@]} > 0)) && log "schedule: ${PARALLEL_JOBS[*]}"
((${#HOST_JOBS[@]} > 0)) && log "headed-client tail (serial, pool drained): ${HOST_JOBS[*]}"

POOL_T0=$(date +%s)
start_ram_sampler
start_starvation_watch

if ((${#PARALLEL_JOBS[@]} > 0)); then
    for slot in "${SLOTS[@]}"; do
        worker "$slot" "${PARALLEL_JOBS[@]}" &
        WORKER_PIDS+=($!)
    done
    # Unbounded on purpose, and bounded in fact: a worker's only long-running
    # step is a probe, and every probe now runs under the watchdog above. Putting
    # a second deadline here would be a bound on "the pool's remaining work",
    # which is the sum of windows the corpus declared — a number no one can size
    # without sizing it to the subject (#144).
    for pid in "${WORKER_PIDS[@]}"; do wait "$pid"; done
    WORKER_PIDS=()
fi

# The tail, with every other slot idle: one Windows host, one headed client, one
# guard that is ownership-blind on purpose.
#
# And now under one machine-wide lock (#127). Draining the pool orders these two
# probes against the rest of *this* run; it does nothing about the sibling agent
# whose tail is running at the same time in another worktree. The lock is taken
# here rather than at pre-flight so that the parallel phase of two pools still
# overlaps — the client is only contended for the length of the tail — and
# released as soon as the tail is done, before the merge.
CLIENT_LOCK_BLOCKED=0
CLIENT_LOCK_EVIDENCE=""
if ((${#HOST_JOBS[@]} > 0)) && [[ ! -f "$STOP_FLAG" ]]; then
    if cti_client_lock_acquire "$WAIT_SECS" "$POOL_LABEL"; then
        log "headed-client tail holds the machine-wide client lock: $(cti_client_lock_path)"
        # Told to the tail's children so `run.sh` does not queue for a lock its
        # own parent is holding.
        export CTI_CLIENT_LOCK_HELD=1
        worker "${SLOTS[0]}" "${HOST_JOBS[@]}"
        unset CTI_CLIENT_LOCK_HELD
        cti_client_lock_release
    else
        CLIENT_LOCK_BLOCKED=1
        log "another run holds the Windows client — the host tail is not a result:"
        cti_client_lock_holder | sed 's/^/[regress]   /' >&2
        # The holder's metadata, copied into this pool's own evidence: the
        # `.info` beside the lock is deleted when the holder releases, so a
        # pool.json that referenced it would durably name a path that stops
        # existing minutes later (#147). What the blocked verdicts point at
        # has to outlive the holder that caused them.
        CLIENT_LOCK_EVIDENCE="$POOL_OUT/client-lock-holder.info"
        cti_client_lock_holder >"$CLIENT_LOCK_EVIDENCE" 2>/dev/null ||
            CLIENT_LOCK_EVIDENCE=""
    fi
fi

POOL_ELAPSED=$(($(date +%s) - POOL_T0))
[[ -n "$ram_sampler_pid" ]] && kill "$ram_sampler_pid" 2>/dev/null
ram_sampler_pid=""
[[ -n "$starve_watch_pid" ]] && kill "$starve_watch_pid" 2>/dev/null
starve_watch_pid=""

# ------------------------------------------------------------------ RAM verdict
PEAK_USED_KB=0
MIN_AVAIL_KB=0
PEAK_TIER_KB=0
PEAK_POOL_KB=0
if [[ -s "$POOL_OUT/ram.tsv" ]]; then
    read -r PEAK_USED_KB MIN_AVAIL_KB PEAK_TIER_KB PEAK_POOL_KB < <(
        awk -F'\t' 'NR > 1 {
            if ($2 > used) used = $2
            if (min == 0 || $3 < min) min = $3
            if ($4 > tier) tier = $4
            if ($5 > own) own = $5
        } END { printf "%d %d %d %d\n", used, min, tier, own }' "$POOL_OUT/ram.tsv"
    )
fi

# ------------------------------------------------------------------ the merge
# One verdict set out of N slots, decided in Python where pytest can reach it
# (#185, ADR-0049): the dead-slot rule (ADR-0022), client-lock-blocked typing
# (#127), the mem-stop overlay (#125) and the worst-class ranking live in
# tools/pool_merge.py, which reads the claim directories back off disk — the
# case it has to report honestly is a worker that died, whose verdict was
# never written and would have no row in any parent's array — writes
# pool.json, prints the summary, and hands back the key=value lines this
# shell acts on. Bounded like every uv run the tier makes (#144), and checked
# at its site per ADR-0049's mechanics: a merge that could not run has read no
# verdict anyone can act on, so the run is infra_unavailable — never a green
# exit over verdicts nobody merged.
merge_args=(
    --pool-out "$POOL_OUT"
    --corpus "${CORPUS[@]}"
    --client-lock-blocked "$CLIENT_LOCK_BLOCKED"
    --client-lock-evidence "$CLIENT_LOCK_EVIDENCE"
    --started-at "$RUN_STARTED"
    --git-sha "$GIT_SHA"
    --host "$HOST"
    --slots "${SLOTS[@]}"
    --wall-secs "$POOL_ELAPSED"
    --peak-mem-used-kb "$PEAK_USED_KB"
    --peak-tier-rss-kb "$PEAK_TIER_KB"
    --peak-pool-rss-kb "$PEAK_POOL_KB"
    --least-mem-available-kb "$MIN_AVAIL_KB"
)
((${#HOST_JOBS[@]} > 0)) && merge_args+=(--host-probes "${HOST_JOBS[@]}")
for i in "${!DIRTY_SLOTS[@]}"; do
    merge_args+=(--dirty-slot "${DIRTY_SLOTS[$i]}:${DIRTY_DETAIL[$i]}")
done
merged="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python "$POOL_MERGE_TOOL" merge "${merge_args[@]}")"
merge_status=$?
worst_class="$(sed -n 's/^worst_class=//p' <<<"$merged" | tail -1)"
if ((merge_status != 0)) || [[ -z "$worst_class" ]]; then
    {
        printf '\n[regress] the merge could not run (uv run tools/pool_merge.py exited %s) — no verdict was read. Not a result.\n' "$merge_status"
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=the pool merge exited %s; the workers'"'"' evidence is under %s\n' "$merge_status" "$POOL_OUT"
    } >&2
    record_refusal infra_unavailable "the pool merge exited $merge_status; the workers' evidence is under $POOL_OUT"
    exit "${CLASS_RANK[infra_unavailable]}"
fi

# The merge has now seen every in-flight claim. Refresh the stop flag from its
# final rendering so the durable pool record and the file workers acted on name
# the same not-run count.
final_stop_line="$(sed -n 's/^stopped_early=//p' <<<"$merged" | tail -1)"
if [[ -n "$final_stop_line" ]]; then
    printf '%s\n' "$final_stop_line" >"$STOP_FLAG"
fi

# The merge decides, this shell acts (ADR-0049): a dead worker's slot is
# cleared here rather than left for whoever comes next. The worker's children
# outlive it — `run.sh`, a server, a headless client — still on this slot's
# ports and still holding the descriptor they inherited, so the lock the
# kernel is supposed to free stays held. We still own the slot, so clearing it
# is ours to do; the next holder's cleanup-on-acquire is the backstop for the
# case where nobody did. Whether it comes back clear changes nothing we could
# act on: the probe is already typed infra_unavailable, no bring-up follows on
# this slot in this run, and the slot's next holder reclaims on acquire and
# refuses itself there if it still cannot (#133). The log line the reclaim
# writes is the record.
while IFS= read -r dead_slot; do
    [[ "$dead_slot" =~ ^[0-9]+$ ]] || continue
    cti_slot_release "$dead_slot"
    cti_slot_reclaim "$dead_slot" holders >/dev/null
done < <(sed -n 's/^reclaim_slot=//p' <<<"$merged")

[[ -f "$STOP_FLAG" ]] && log "pool stopped early: $(cat "$STOP_FLAG")"
log "wall: ${POOL_ELAPSED}s across ${#SLOTS[@]} slot(s) — slots ${SLOTS[*]}"
for i in "${!DIRTY_SLOTS[@]}"; do
    log "slot ${DIRTY_SLOTS[$i]}: infra_unavailable, never used — ${DIRTY_DETAIL[$i]}"
done
log "peak memory in use: $((PEAK_USED_KB / 1024)) MiB (tier processes $((PEAK_TIER_KB / 1024)) MiB, this pool's own $((PEAK_POOL_KB / 1024)) MiB, least available $((MIN_AVAIL_KB / 1024)) MiB)"
log "pool evidence: $POOL_OUT"

exit_code="${CLASS_RANK[$worst_class]:-}"
if [[ -z "$exit_code" ]]; then
    # A worst class this table has never heard of is, by the failure-class
    # table's own preamble, an untyped red: a harness bug, and the merge
    # already ranks it at that severity (#185). The exit says the same thing
    # rather than the undocumented 9 it used to fall to (#147) — the row to
    # read is untyped_harness_failure, and the row says fix the harness first.
    log "worst class '$worst_class' is not in the exit table — exiting as untyped_harness_failure (a class nobody can read is a harness bug)"
    exit_code="${CLASS_RANK[untyped_harness_failure]}"
fi
log "worst class: $worst_class (exit $exit_code)"
exit "$exit_code"
