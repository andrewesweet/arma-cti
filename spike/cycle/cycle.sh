#!/usr/bin/env bash
# Exploration scaffolding for issue #45: run two missions in one server process
# and measure what the cycle costs against a cold start, asserting that the
# second mission is as fresh as ADR-0023 requires.
#
#   spike/cycle/cycle.sh [--no-daemon-restart]
#
# Not part of the tier. It borrows spike/run.sh's staging rather than calling
# it, because run.sh brings up exactly one mission and the whole question here
# is what a second one costs. If multiplexing is adopted, this is thrown away
# and the behaviour lands in the runner with a recipe; if it is declined, this
# is the evidence for declining.
#
# The cycle, and why each step is where it is:
#   1. stage both legs as separate missions (ctycle0.Stratis, ctycle1.Stratis)
#   2. daemon up, server up with -autoInit -> leg A runs
#   3. leg A dirties Campaign, roster, telemetry and draws the PRNG, then calls
#      `serverCommand "#mission ctycle1.Stratis"` from inside the world
#   4. on seeing `cycle_switch_requested`, this script restarts the daemon,
#      because the Campaign lives in the daemon process and nothing in the
#      protocol resets it — a cycled mission against a surviving daemon is a
#      resumed Campaign, which ADR-0023 forbids
#   5. leg B asserts freshness on five axes — the two the runner owns (PRNG and
#      telemetry) gate here, at the bottom of this file, and the rest gate in
#      the leg itself
#
# `-e` is deliberately absent (#83): this script's product is a typed verdict,
# and exit-on-error would abandon a run at the failing line with the trap's
# status and no class — the untyped red the failure-class table calls a harness
# bug. Everything whose failure ends the run is checked and routed through
# `fail`, which records the class first.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=spike/host-guard.sh
source "$REPO/spike/host-guard.sh"

SERVER_DIR="${CTI_SERVER_DIR:-$HOME/arma3server}"
OUT="${CTI_CYCLE_OUT:-$HOME/.arma-cti/cycle/$(date -u +%Y%m%dT%H%M%SZ)}"
PORT="${CTI_SERVER_PORT:-2402}"
DAEMON_PORT="${CTI_DAEMON_PORT:-9099}"
export CTI_DAEMON_ADDR="127.0.0.1:$DAEMON_PORT"
CONFIG="$REPO/spike/cycle/cycle.cfg"
LEGS=("$REPO/spike/cycle/leg-a-dirty.sqf" "$REPO/spike/cycle/leg-b-fresh.sqf")
MISSIONS=(ctycle0.Stratis ctycle1.Stratis)
RESTART_DAEMON=1
# Three of the fourteen probes want a headless client, and 13.5 s of their
# bring-up is its join. Whether it survives a mission change decides whether
# cycling helps them at all, so it is a switch here rather than an assumption.
WITH_HC=0
for arg in "$@"; do
    case "$arg" in
    --no-daemon-restart) RESTART_DAEMON=0 ;;
    --hc) WITH_HC=1 ;;
    *)
        printf '[cycle] unknown argument: %s\n' "$arg" >&2
        exit 2
        ;;
    esac
done

mkdir -p "$OUT"
RESULTS="$OUT/results.env"
: >"$RESULTS"
log() { printf '[cycle] %s\n' "$*" >&2; }
# One line per record: results.env is read a line at a time, so a newline inside
# a value would forge a record nobody wrote (#83).
record() {
    local value="${2//$'\n'/ }"
    printf '%s=%s\n' "$1" "$value" >>"$RESULTS"
    log "$1=$value"
}
now() { date +%s.%N; }
since() { echo "scale=3; $(now) - $1" | bc; }

daemon_pid=""
server_pid=""
hc_pid=""
cleanup() {
    local code=$?
    for pid in "$hc_pid" "$server_pid" "$daemon_pid"; do
        [[ -n "$pid" ]] && kill "$pid" 2>/dev/null
    done
    sleep 2
    for pid in "$hc_pid" "$server_pid" "$daemon_pid"; do
        [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null
    done
    exit "$code"
}
trap cleanup EXIT INT TERM

fail() {
    record "verdict" "FAIL"
    record "failure_class" "$1"
    record "failure_detail" "$2"
    log "FAILED: $1 — $2"
    exit 1
}

# Wait for the Nth occurrence of a pattern in a growing log.
wait_for_nth() {
    local file="$1" pattern="$2" want="$3" timeout="$4" pid="${5:-}"
    local deadline
    deadline=$(echo "$(now) + $timeout" | bc)
    while :; do
        # grep -c prints its count and *also* exits 1 when the count is zero, so
        # a `|| echo 0` fallback appends a second number and the arithmetic below
        # sees "0\n0". The count alone is the answer; the exit status is noise.
        local seen
        seen=$(grep -acE "$pattern" "$file" 2>/dev/null)
        if [[ -f "$file" ]] && ((${seen:-0} >= want)); then
            return 0
        fi
        if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then return 2; fi
        if (($(echo "$(now) > $deadline" | bc))); then return 1; fi
        sleep 0.1
    done
}

start_daemon() {
    local tag="$1"
    DAEMON_LOG="$OUT/daemon-$tag.log"
    DAEMON_TELEMETRY="$OUT/telemetry-$tag.jsonl"
    : >"$DAEMON_LOG"
    : >"$DAEMON_TELEMETRY"
    local t
    t=$(now)
    (cd "$REPO" && exec uv run --quiet cti-daemon \
        --host 127.0.0.1 --port "$DAEMON_PORT" --telemetry "$DAEMON_TELEMETRY") \
        >"$DAEMON_LOG" 2>&1 &
    daemon_pid=$!
    local deadline
    deadline=$(echo "$(now) + 90" | bc)
    while ! grep -q CTI_DAEMON_READY "$DAEMON_LOG" 2>/dev/null; do
        kill -0 "$daemon_pid" 2>/dev/null || fail "infra_unavailable" "daemon $tag died; see $DAEMON_LOG"
        (($(echo "$(now) > $deadline" | bc))) && fail "infra_unavailable" "daemon $tag never ready"
        sleep 0.1
    done
    record "daemon_${tag}_ready_secs" "$(since "$t")"
}

# ------------------------------------------------------------------ pre-flight
cti_host_guard_main || fail "infra_unavailable" "host guard refused"
[[ -x "$SERVER_DIR/arma3server_x64" ]] || fail "infra_unavailable" "no server at $SERVER_DIR"
# Overridable for the same reason CTI_SERVER_DIR is: it is what lets the no-Arma
# tier drive this script's own freshness gates against a stub server
# (tests/unit/test_cycle_freshness.py).
SO="${CTI_SHIM_SO:-$REPO/extension/target/release/libcti_shim.so}"
[[ -f "$SO" ]] || fail "infra_unavailable" "shim not built"
BUILT_MOD="${CTI_BUILT_MOD:-$REPO/.hemttout/build}"
[[ -d "$BUILT_MOD/addons" ]] || fail "infra_unavailable" "addon not built"
PRELUDE="$REPO/spike/probe-prelude.sqf"
[[ -f "$PRELUDE" ]] || fail "infra_unavailable" "probe prelude missing: $PRELUDE"

# ------------------------------------------------------------------ staging
mkdir -p "$HOME/.local/share/Arma 3" "$HOME/.local/share/Arma 3 - Other Profiles"
t_stage=$(now)
for i in 0 1; do
    stage="$OUT/mission/${MISSIONS[$i]}"
    rm -rf "$stage"
    mkdir -p "$stage"
    cp -r "$REPO/missions/cti.Stratis/." "$stage/"
    {
        echo "// Generated by spike/cycle/cycle.sh. Do not edit."
        printf 'CTI_SPIKE_DAEMON_ADDRS = ["127.0.0.1:%s"];\n' "$DAEMON_PORT"
    } >"$stage/daemon_addrs.sqf"
    {
        echo "// Generated by spike/cycle/cycle.sh. Do not edit."
        printf 'CTI_DESYNC_WATCH_SECS = 0;\nCTI_DESYNC_LOAD = 0;\n'
        printf 'CTI_PROBE_SOAK = 0;\nCTI_PROBE_CLIENT = 0;\n'
        # Staged ahead of the leg, exactly as spike/run.sh stages it ahead of a
        # probe. Without it `cti_probe_fnc_worldReady` was undefined here, which
        # is why both legs carried the raw 20 s settle #46 eliminated everywhere
        # else (#81).
        cat "$PRELUDE"
        cat "${LEGS[$i]}"
    } >"$stage/harness.sqf"
    rm -rf "${SERVER_DIR:?}/mpmissions/${MISSIONS[$i]}" \
        "${SERVER_DIR:?}/mpmissions/${MISSIONS[$i]}.pbo"
    (cd "$REPO" && uv run --quiet python tools/pack_pbo.py "$stage" \
        "$SERVER_DIR/mpmissions/${MISSIONS[$i]}.pbo") >/dev/null ||
        fail "infra_unavailable" "pack failed for ${MISSIONS[$i]}"
done
rm -f "$SERVER_DIR/cti_shim.so"
install -m 0755 "$SO" "$SERVER_DIR/cti_shim_x64.so"
rm -rf "${SERVER_DIR:?}/@cti"
mkdir -p "$SERVER_DIR/@cti"
cp -r "$BUILT_MOD/addons" "$SERVER_DIR/@cti/"
record "stage_secs" "$(since "$t_stage")"

# ------------------------------------------------------------------ leg A
start_daemon a

SERVER_LOG="$OUT/server.stdout.log"
: >"$SERVER_LOG"
t_boot=$(now)
(
    cd "$SERVER_DIR" || exit 1
    exec ./arma3server_x64 -config="$CONFIG" -cfg="$REPO/spike/basic.cfg" \
        -mod=@cti -port="$PORT" -name=ctispike -world=empty -autoInit \
        -noSound -limitFPS=100
) >"$SERVER_LOG" 2>&1 &
server_pid=$!

case "$(
    wait_for_nth "$SERVER_LOG" "Host identity created|Dedicated host created" 1 120 "$server_pid"
    echo $?
)" in
1) fail "timeout" "no host in 120s" ;;
2) fail "node_crashed" "server exited during boot" ;;
esac
record "server_host_up_secs" "$(since "$t_boot")"

case "$(
    wait_for_nth "$SERVER_LOG" 'CTI\|mission_running' 1 240 "$server_pid"
    echo $?
)" in
1) fail "timeout" "leg A never reached mission_running" ;;
2) fail "node_crashed" "server exited loading leg A" ;;
esac
record "cold_start_mission_running_secs" "$(since "$t_boot")"
record "server_version" "$(grep -aoE 'Arma 3 Console version [0-9.]+' "$SERVER_LOG" | head -1 | awk '{print $NF}')"

if ((WITH_HC == 1)); then
    HC_LOG="$OUT/hc.stdout.log"
    : >"$HC_LOG"
    t_hc=$(now)
    (
        cd "$SERVER_DIR" || exit 1
        exec ./arma3server_x64 -client -connect=127.0.0.1 -mod=@cti -port="$PORT" \
            -password=ctispike -name=ctihc1 -world=empty -noSound -limitFPS=50
    ) >"$HC_LOG" 2>&1 &
    hc_pid=$!
    case "$(
        wait_for_nth "$SERVER_LOG" 'Player headlessclient connected \(id=HC' 1 90 "$hc_pid"
        echo $?
    )" in
    1 | 2) fail "infra_unavailable" "headless client never joined; see $HC_LOG" ;;
    esac
    record "hc_join_secs" "$(since "$t_hc")"
fi

# ------------------------------------------------------------------ the switch
case "$(
    wait_for_nth "$SERVER_LOG" 'CTI\|(cycle_switch_requested|FAIL)' 1 420 "$server_pid"
    echo $?
)" in
1) fail "timeout" "leg A never asked for the switch" ;;
2) fail "node_crashed" "server exited during leg A" ;;
esac
t_switch=$(now)
if grep -qa 'CTI|FAIL' "$SERVER_LOG"; then
    fail "assertion_failed" "$(grep -a 'CTI|FAIL' "$SERVER_LOG" | head -1)"
fi
record "leg_a_secs" "$(since "$t_boot")"

# The Campaign lives in the daemon and the protocol has no reset verb, so a
# cycled mission is only as fresh as the daemon behind it. Restarting here is
# the honest version; --no-daemon-restart runs the dishonest one on purpose, to
# show what a cycle without it actually inherits.
if ((RESTART_DAEMON == 1)); then
    kill "$daemon_pid" 2>/dev/null
    wait "$daemon_pid" 2>/dev/null
    start_daemon b
else
    record "daemon_b_ready_secs" "reused-daemon-a"
    cp "$OUT/telemetry-a.jsonl" "$OUT/telemetry-b.jsonl" 2>/dev/null || true
fi

# ------------------------------------------------------------------ leg B
case "$(
    wait_for_nth "$SERVER_LOG" 'CTI\|mission_running' 2 300 "$server_pid"
    echo $?
)" in
1) fail "timeout" "the server never loaded leg B; see $SERVER_LOG" ;;
2) fail "node_crashed" "server exited during the switch" ;;
esac
record "cycle_secs_wall" "$(since "$t_switch")"
# The wall figure above starts when this script noticed the switch line, which
# is up to one poll late. The engine's own log timestamps are the authority for
# what the cycle cost, so both are recorded and the log-derived one is the
# number to quote.
record "cycle_switch_at" "$(grep -a 'cycle_switch_requested' "$SERVER_LOG" | head -1 | awk '{print $1}')"
record "cycle_mission_running_at" "$(grep -a 'CTI|mission_running' "$SERVER_LOG" | sed -n 2p | awk '{print $1}')"
record "cycle_mission_read_at" "$(grep -a "Mission ${MISSIONS[1]} read from bank" "$SERVER_LOG" | head -1 | awk '{print $1}')"

case "$(
    wait_for_nth "$SERVER_LOG" 'CTI\|(cycle_b_probe_done|FAIL)' 1 420 "$server_pid"
    echo $?
)" in
1) fail "timeout" "leg B never finished" ;;
2) fail "node_crashed" "server exited during leg B" ;;
esac

grep -aoE 'CTI\|.*' "$SERVER_LOG" | sed 's/^CTI|//; s/"$//' >"$OUT/cycle-lines.txt"

# ------------------------------------------------------------------ assertions
# The two freshness axes the runner owns. leg-b-fresh.sqf's header says every
# axis is an assertion and a missing reading fails rather than being skipped —
# and these two were *recorded* and never gated, so a run whose PRNG stream had
# carried over reported PASS with the evidence of its own failure sitting in
# results.env. That is the #44 false-green shape, and #81 is it living here.
#
# Collected rather than exited on, one at a time: a cycle that failed two axes
# should say so once, in the same pass, the way the tier reports every probe.
freshness_failures=()

a_prng="$(grep -a 'cycle_prng leg=a' "$OUT/cycle-lines.txt" | head -1 | sed 's/.*draws=//')"
b_prng="$(grep -a 'cycle_prng leg=b' "$OUT/cycle-lines.txt" | head -1 | sed 's/.*draws=//')"
record "prng_leg_a" "${a_prng:-missing}"
record "prng_leg_b" "${b_prng:-missing}"
if [[ -z "$a_prng" || -z "$b_prng" ]]; then
    record "prng_streams_match" "unread"
    freshness_failures+=("PRNG unread (leg a: ${a_prng:-missing}, leg b: ${b_prng:-missing}) — an axis that was not read is not an axis that passed")
elif [[ "$a_prng" == "$b_prng" ]]; then
    record "prng_streams_match" "true"
else
    record "prng_streams_match" "false"
    freshness_failures+=("PRNG stream carried over: the same seed drew $a_prng in leg A and $b_prng in leg B")
fi

record "state_leg_a" "$(grep -a 'cycle_state leg=a' "$OUT/cycle-lines.txt" | head -1)"
record "state_leg_b" "$(grep -a 'cycle_state leg=b' "$OUT/cycle-lines.txt" | head -1)"

# Telemetry: leg B's file must carry no row leg A wrote. Asserted off the
# daemon's own file rather than off the world's memory of what it staged.
a_rows=$(wc -l <"$OUT/telemetry-a.jsonl" 2>/dev/null || echo 0)
b_rows=$(wc -l <"$OUT/telemetry-b.jsonl" 2>/dev/null || echo 0)
record "telemetry_leg_a_rows" "$a_rows"
record "telemetry_leg_b_rows" "$b_rows"
# `grep -ac` on a file that is not there prints nothing, so this used to record a
# blank and carry on — a reading nobody took, written down where a reading goes.
carried="$(grep -ac 'cycle-a-' "$OUT/telemetry-b.jsonl" 2>/dev/null)"
if [[ -z "$carried" ]]; then
    record "telemetry_leg_b_carries_leg_a_ids" "unread"
    freshness_failures+=("no telemetry to read at $OUT/telemetry-b.jsonl — a missing reading fails rather than recording a blank")
else
    record "telemetry_leg_b_carries_leg_a_ids" "$carried"
    # Gated only when the daemon was restarted, because that is when the axis
    # means anything: --no-daemon-restart runs the dishonest cycle on purpose and
    # its leg B is served by leg A's own daemon and leg A's own telemetry file.
    # Carry-over there is the finding, not the failure.
    if ((RESTART_DAEMON == 1)) && ((carried > 0)); then
        freshness_failures+=("leg B telemetry carries $carried row(s) leg A wrote, across a daemon restart that should have left none")
    fi
fi

# Did the headless client live through the mission change, or did the engine
# drop it and does it come back by itself? 13.5 s of three probes' bring-up is
# its join, so the answer decides whether cycling helps them.
if ((WITH_HC == 1)); then
    record "hc_connects_total" "$(grep -ac 'Player headlessclient connected' "$SERVER_LOG")"
    record "hc_disconnects_total" "$(grep -ac 'Player headlessclient disconnected' "$SERVER_LOG")"
    record "hc_alive_at_end" "$(kill -0 "$hc_pid" 2>/dev/null && echo true || echo false)"
fi

if grep -qa '^FAIL' "$OUT/cycle-lines.txt"; then
    fail "assertion_failed" "$(grep -a '^FAIL' "$OUT/cycle-lines.txt" | head -1)"
fi
if ((${#freshness_failures[@]} > 0)); then
    for i in "${!freshness_failures[@]}"; do
        record "freshness_failure_$((i + 1))" "${freshness_failures[$i]}"
    done
    fail "assertion_failed" \
        "${#freshness_failures[@]} freshness axis(es) failed: ${freshness_failures[*]}"
fi
record "verdict" "PASS"
log "evidence: $OUT"
