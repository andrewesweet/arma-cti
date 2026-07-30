#!/usr/bin/env bash
# Phase-0 spike harness: bring up stub daemon -> dedicated server -> headless
# client inside WSL2, run the in-mission measurements, tear everything down.
#
# Throwaway measurement scaffolding (issue #2). Phase 1 replaces it with the
# real `just accept` harness.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="${CTI_SERVER_DIR:-$HOME/arma3server}"
SERVER_BIN="$SERVER_DIR/arma3server_x64"
OUT="${CTI_SPIKE_OUT:-$REPO/.spike-out}"
# NOT 2302. WSL2 mirrored networking shares the port space with Windows, and the
# Windows Arma client owns 2302-2306 plus its Steam query ports. BI wants >=100
# between server port sets, so the test tier lives at 2402-2406.
PORT="${CTI_SERVER_PORT:-2402}"
DAEMON_PORT="${CTI_DAEMON_PORT:-9099}"
SERVER_PASSWORD="${CTI_SERVER_PASSWORD:-ctispike}"

BOOT_TIMEOUT="${CTI_BOOT_TIMEOUT:-240}"
HC_TIMEOUT="${CTI_HC_TIMEOUT:-90}"
HARNESS_TIMEOUT="${CTI_HARNESS_TIMEOUT:-300}"

SKIP_HC=0
[[ "${1:-}" == "--no-hc" ]] && SKIP_HC=1

mkdir -p "$OUT"
RESULTS="$OUT/results.env"
: >"$RESULTS"

daemon_pid=""
server_pid=""
hc_pid=""

log() { printf '[spike] %s\n' "$*" >&2; }
record() { printf '%s=%s\n' "$1" "$2" >>"$RESULTS"; log "$1=$2"; }
now() { date +%s.%N; }
since() { echo "scale=3; $(now) - $1" | bc; }

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

# Wait for a regex to appear in a growing log. Returns 1 on timeout, and 2 if
# the process being waited on died first — a distinct failure class, never a pass.
wait_for() {
    local file="$1" pattern="$2" timeout="$3" pid="${4:-}"
    local deadline
    deadline=$(echo "$(now) + $timeout" | bc)
    while :; do
        if [[ -f "$file" ]] && grep -qE "$pattern" "$file" 2>/dev/null; then return 0; fi
        if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then return 2; fi
        if (($(echo "$(now) > $deadline" | bc))); then return 1; fi
        sleep 0.25
    done
}

fail() {
    record "verdict" "FAIL"
    record "failure_class" "$1"
    record "failure_detail" "$2"
    log "FAILED: $1 — $2"
    exit 1
}

# ---------------------------------------------------------------- preconditions
[[ -x "$SERVER_BIN" ]] || fail "infra_unavailable" "server binary missing at $SERVER_BIN"
SO="$REPO/extension/target/release/libcti_shim.so"
[[ -f "$SO" ]] || fail "infra_unavailable" "shim not built: $SO (run: cargo build --release --manifest-path extension/Cargo.toml)"

record "wsl_networking_mode" "$(wslinfo --networking-mode 2>/dev/null || echo unknown)"
record "wsl_lan_ip" "$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | paste -sd, -)"

# ---------------------------------------------------------------- staging
# Profiles: -profiles= is broken on Linux, the engine insists on these paths.
mkdir -p "$HOME/.local/share/Arma 3" "$HOME/.local/share/Arma 3 - Other Profiles"

# Pack rather than copy the folder: an unpacked mission cannot be transmitted to
# a joining client, and a client without file patching never finishes loading one.
rm -rf "$SERVER_DIR/mpmissions/spike.Stratis" "$SERVER_DIR/mpmissions/spike.Stratis.pbo"
(cd "$REPO" && uv run --quiet python tools/pack_pbo.py missions/spike.Stratis \
    "$SERVER_DIR/mpmissions/spike.Stratis.pbo") >/dev/null ||
    fail "infra_unavailable" "mission pack failed"

# The Linux server appends _x64 exactly as the Windows one does: SQF says
# "cti_shim", the engine opens cti_shim_x64.so.
rm -f "$SERVER_DIR/cti_shim.so"
install -m 0755 "$SO" "$SERVER_DIR/cti_shim_x64.so"
record "shim_size_bytes" "$(stat -c %s "$SO")"

# ---------------------------------------------------------------- stub daemon
DAEMON_LOG="$OUT/daemon.log"
: >"$DAEMON_LOG"
t=$(now)
(cd "$REPO" && exec uv run --quiet cti-stub-daemon --port "$DAEMON_PORT") >"$DAEMON_LOG" 2>&1 &
daemon_pid=$!
if ! wait_for "$DAEMON_LOG" "CTI_STUB_DAEMON_READY" 90 "$daemon_pid"; then
    fail "infra_unavailable" "stub daemon did not report ready; see $DAEMON_LOG"
fi
record "daemon_ready_secs" "$(since "$t")"

# ---------------------------------------------------------------- dedicated server
SERVER_LOG="$OUT/server.stdout.log"
: >"$SERVER_LOG"
t_boot=$(now)
(
    cd "$SERVER_DIR" || exit 1
    exec ./arma3server_x64 \
        -config="$REPO/spike/server.cfg" \
        -cfg="$REPO/spike/basic.cfg" \
        -port="$PORT" \
        -name=ctispike \
        -world=empty \
        -autoInit \
        -noSound \
        -limitFPS=100
) >"$SERVER_LOG" 2>&1 &
server_pid=$!

case "$(
    wait_for "$SERVER_LOG" "Host identity created|Dedicated host created" 120 "$server_pid"
    echo $?
)" in
1) fail "timeout" "server never created a host in 120s; see $SERVER_LOG" ;;
2) fail "node_crashed" "server process exited during boot; see $SERVER_LOG" ;;
esac
record "server_host_up_secs" "$(since "$t_boot")"

case "$(
    wait_for "$SERVER_LOG" "SPIKE\|mission_running" "$BOOT_TIMEOUT" "$server_pid"
    echo $?
)" in
1) fail "timeout" "mission did not reach running state in ${BOOT_TIMEOUT}s; see $SERVER_LOG" ;;
2) fail "node_crashed" "server process exited while loading the mission; see $SERVER_LOG" ;;
esac
record "server_mission_running_secs" "$(since "$t_boot")"
record "server_version" "$(grep -aoE 'Arma 3 Console version [0-9.]+' "$SERVER_LOG" | head -1 | awk '{print $NF}')"

# ---------------------------------------------------------------- headless client
if ((SKIP_HC == 0)); then
    HC_LOG="$OUT/hc.stdout.log"
    : >"$HC_LOG"
    t_hc=$(now)
    (
        cd "$SERVER_DIR" || exit 1
        # The password must match server.cfg or the client never gets past connect.
        exec ./arma3server_x64 -client \
            -connect=127.0.0.1 \
            -port="$PORT" \
            -password="$SERVER_PASSWORD" \
            -name=ctihc1 \
            -world=empty \
            -noSound \
            -limitFPS=50
    ) >"$HC_LOG" 2>&1 &
    hc_pid=$!

    case "$(
        # The HC's player name is "headlessclient" regardless of -name=, and it
        # is assigned an id=HC… rather than a numeric slot id.
        wait_for "$SERVER_LOG" "Player headlessclient connected \(id=HC" "$HC_TIMEOUT" "$hc_pid"
        echo $?
    )" in
    1)
        record "hc_joined" "false"
        record "hc_failure" "timeout after ${HC_TIMEOUT}s"
        ;;
    2)
        record "hc_joined" "false"
        record "hc_failure" "headless client process exited; see $HC_LOG"
        ;;
    *)
        record "hc_joined" "true"
        record "hc_join_secs" "$(since "$t_hc")"
        ;;
    esac
else
    record "hc_joined" "skipped"
fi

# ---------------------------------------------------------------- harness verdict
case "$(
    wait_for "$SERVER_LOG" "SPIKE\|done" "$HARNESS_TIMEOUT" "$server_pid"
    echo $?
)" in
1) fail "timeout" "in-mission harness never logged done; see $SERVER_LOG" ;;
2) fail "node_crashed" "server exited during the harness; see $SERVER_LOG" ;;
esac

grep -aoE 'SPIKE\|.*' "$SERVER_LOG" | sed 's/^SPIKE|//; s/"$//' >"$OUT/spike-lines.txt"
log "--- in-mission results ---"
cat "$OUT/spike-lines.txt" >&2

if grep -q '^FAIL' "$OUT/spike-lines.txt"; then
    fail "assertion_failed" "$(grep '^FAIL' "$OUT/spike-lines.txt" | head -1)"
fi

record "server_peak_rss_kb" "$(awk '/VmHWM/{print $2}' "/proc/$server_pid/status" 2>/dev/null || echo unknown)"
if [[ -n "$hc_pid" ]]; then
    record "hc_peak_rss_kb" "$(awk '/VmHWM/{print $2}' "/proc/$hc_pid/status" 2>/dev/null || echo unknown)"
fi
record "verdict" "PASS"
log "results: $RESULTS"
