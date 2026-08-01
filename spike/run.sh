#!/usr/bin/env bash
# Phase-0 spike harness: bring up stub daemon -> dedicated server -> headless
# client inside WSL2, run the in-mission measurements, tear everything down.
#
# Throwaway measurement scaffolding (issue #2). Phase 1 replaces it with the
# real `just accept` harness.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Absolute-path resolution for the Windows interop binaries, and the one guard
# that protects the human rather than another agent (#41).
# shellcheck source=spike/host-guard.sh
source "$REPO/spike/host-guard.sh"
SERVER_DIR="${CTI_SERVER_DIR:-$HOME/arma3server}"
SERVER_BIN="$SERVER_DIR/arma3server_x64"
OUT="${CTI_SPIKE_OUT:-$REPO/.spike-out}"
# NOT 2302. WSL2 mirrored networking shares the port space with Windows, and the
# Windows Arma client owns 2302-2306 plus its Steam query ports. BI wants >=100
# between server port sets, so the test tier lives at 2402-2406.
PORT="${CTI_SERVER_PORT:-2402}"
DAEMON_PORT="${CTI_DAEMON_PORT:-9099}"
SERVER_PASSWORD="${CTI_SERVER_PASSWORD:-ctispike}"
# Which world to bring up. The phase-0 measurement mission is the default; a
# Phase-1 mission needs its own server config (its Missions class names the
# template) and its own log prefix, because the harness greps for that prefix.
MISSION="${CTI_MISSION:-spike.Stratis}"
SERVER_CONFIG="${CTI_SERVER_CONFIG:-$REPO/spike/server.cfg}"
LOG_PREFIX="${CTI_LOG_PREFIX:-SPIKE}"
# Issue #8 candidate cause 2: spike/basic.cfg is hand-written and unvalidated.
# Set CTI_BASIC_CFG empty to launch on engine defaults instead.
BASIC_CFG="${CTI_BASIC_CFG-$REPO/spike/basic.cfg}"
# Issue #8: a headless client launched on the Windows host crosses the same
# mirrored-network boundary a human client does, and needs no role selection —
# so the desync question can be asked without anyone clicking a slot. Set
# CTI_WINDOWS_HC=1 to launch one. Empty ARMA_WINDOWS_DIR disables it.
WINDOWS_HC="${CTI_WINDOWS_HC:-0}"
WINDOWS_ARMA_DIR="${CTI_WINDOWS_ARMA_DIR:-/mnt/d/Apps/Steam/steamapps/common/Arma 3}"
WINDOWS_CONNECT="${CTI_WINDOWS_CONNECT:-127.0.0.1}"
# A *headed* Windows client — the thing #8 still needs and the thing that cannot
# yet get past role selection unattended. Windowed and -noPause so it keeps
# simulating when it does not have focus.
WINDOWS_CLIENT="${CTI_WINDOWS_CLIENT:-0}"
WINDOWS_CLIENT_PROFILE="${CTI_WINDOWS_CLIENT_PROFILE:-ctitest}"

BOOT_TIMEOUT="${CTI_BOOT_TIMEOUT:-240}"
HC_TIMEOUT="${CTI_HC_TIMEOUT:-90}"
HARNESS_TIMEOUT="${CTI_HARNESS_TIMEOUT:-300}"

SKIP_HC=0
HOLD=0
NO_CLIENT_WAIT=0
HOLD_TIMEOUT="${CTI_HOLD_TIMEOUT:-900}"
case "${1:-}" in
--no-hc) SKIP_HC=1 ;;
# The regression tier's mode (issue #23). Everything --hold does, minus the two
# things that only make sense when a human is joining: the direct-connect banner
# and the wait for a client that a regression run never sends. Without this, a
# probe that finished in forty seconds still costs its whole window, because the
# client wait runs to the end before the probe wait begins.
--regress)
    SKIP_HC=$((1 - ${CTI_HOLD_HC:-0}))
    HOLD=1
    NO_CLIENT_WAIT=1
    ;;
# Bring everything up and keep it up so a human client can join, then report
# what that client did. Used for the Windows-client join and .dll load test.
--hold)
    # The headless client is off by default here because hold mode was built
    # for a human joining. CTI_HOLD_HC=1 brings it back: #17's unattended run
    # has to happen on the dedicated-server-plus-headless-client topology the
    # MVP names, and a probe cannot assert a node the harness never started.
    SKIP_HC=$((1 - ${CTI_HOLD_HC:-0}))
    HOLD=1
    ;;
esac

mkdir -p "$OUT"
RESULTS="$OUT/results.env"
: >"$RESULTS"

daemon_pid=""
server_pid=""
hc_pid=""
win_hc_pid=""
win_client_pid=""

log() { printf '[spike] %s\n' "$*" >&2; }
record() { printf '%s=%s\n' "$1" "$2" >>"$RESULTS"; log "$1=$2"; }
now() { date +%s.%N; }
since() { echo "scale=3; $(now) - $1" | bc; }

cleanup() {
    local code=$?
    for pid in "$win_client_pid" "$win_hc_pid" "$hc_pid" "$server_pid" "$daemon_pid"; do
        [[ -n "$pid" ]] && kill "$pid" 2>/dev/null
    done
    sleep 2
    for pid in "$win_client_pid" "$win_hc_pid" "$hc_pid" "$server_pid" "$daemon_pid"; do
        [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null
    done
    # Windows processes are children of WSL interop, not of this shell, so a
    # kill on the interop wrapper does not always reach them. By absolute path:
    # `taskkill.exe` by name is not on an agent's PATH either, so this silently
    # left a Windows process alive after every run that launched one (#41).
    #
    # Keyed on having launched one, not on having been asked to: a run that
    # refuses at the pre-flight below exits through here, and killing
    # arma3_x64.exe on the way out would be this harness doing the exact thing
    # the pre-flight just refused to do.
    [[ -n "$win_hc_pid" ]] && cti_windows_taskkill arma3server_x64.exe
    [[ -n "$win_client_pid" ]] && cti_windows_taskkill arma3_x64.exe
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

# The class an in-mission FAIL line declared, or assertion_failed if it declared
# none. In-world code writes `FAIL class=timeout ...` and `FAIL
# class=oracle_disagreement ...` as well as plain assertions, and calling all of
# them assertion_failed sends the reader to fix code when the failure-class table
# says investigate synchronisation or suspect the capture layer.
class_of() {
    local line="$1" declared
    declared="$(sed -n 's/.*class=\([a-z_]\+\).*/\1/p' <<<"$line")"
    printf '%s' "${declared:-assertion_failed}"
}

fail() {
    record "verdict" "FAIL"
    record "failure_class" "$1"
    record "failure_detail" "$2"
    log "FAILED: $1 — $2"
    exit 1
}

# ---------------------------------------------------------------- preconditions
# Asked before anything is launched, and only by a run that means to drive the
# Windows host: an arma3_x64.exe already up is the human's, the teardown above
# cannot tell theirs from ours, and the answer is stop rather than kill (#41).
if ((WINDOWS_CLIENT == 1)); then
    guard="$(cti_human_client_state)"
    case "${guard%% *}" in
    running) fail "infra_unavailable" "${guard#* } — that is a play session, not ours" ;;
    unavailable) fail "infra_unavailable" "${guard#* }; refusing to take a machine I cannot check" ;;
    esac
    record "windows_host_free" "true"
fi

[[ -x "$SERVER_BIN" ]] || fail "infra_unavailable" "server binary missing at $SERVER_BIN"
SO="$REPO/extension/target/release/libcti_shim.so"
[[ -f "$SO" ]] || fail "infra_unavailable" "shim not built: $SO (run: cargo build --release --manifest-path extension/Cargo.toml)"
# HEMTT's build output is already a mod folder (<dir>/addons/*.pbo). Every
# machine that runs mission scripts needs it loaded: CfgFunctions compiles per
# machine, so an unloaded addon means no cti_fnc_*.
BUILT_MOD="$REPO/.hemttout/build"
[[ -d "$BUILT_MOD/addons" ]] || fail "infra_unavailable" "addon not built: $BUILT_MOD/addons (run: just build-addon)"
# -mod= resolves against the game directory, not the working directory: an
# absolute path outside it lands in the mod table as "GAME DIR (Empty)" and
# silently loads nothing. Stage it inside the server instead.
MOD_NAME="@cti"

record "mission" "$MISSION"
record "wsl_networking_mode" "$(wslinfo --networking-mode 2>/dev/null || echo unknown)"
record "wsl_lan_ip" "$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | paste -sd, -)"

# ---------------------------------------------------------------- staging
# Profiles: -profiles= is broken on Linux, the engine insists on these paths.
mkdir -p "$HOME/.local/share/Arma 3" "$HOME/.local/share/Arma 3 - Other Profiles"

# A joining Windows client has to be told where the daemon is, and whether
# mirrored-mode loopback carries it is exactly what the hold test measures — so
# stage the mission with both candidates and let the client try them in order.
LAN_IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 |
    grep -E '^192\.168\.' | head -1)"
STAGE="$OUT/mission/$MISSION"
rm -rf "$OUT/mission"
mkdir -p "$STAGE"
[[ -d "$REPO/missions/$MISSION" ]] || fail "infra_unavailable" "no such mission: missions/$MISSION"
cp -r "$REPO/missions/$MISSION/." "$STAGE/"
{
    echo "// Generated by spike/run.sh at bring-up. Do not edit."
    printf 'CTI_SPIKE_DAEMON_ADDRS = ["127.0.0.1:%s"' "$DAEMON_PORT"
    [[ -n "$LAN_IP" ]] && printf ', "%s:%s"' "$LAN_IP" "$DAEMON_PORT"
    printf '];\n'
} >"$STAGE/daemon_addrs.sqf"

# Issue #8: hold mode is the only mode a real client joins in, so that is the
# only mode worth watching desync in. Zero elsewhere keeps the sampling off.
# Hold mode is the only mode a real client joins in, so it watches by default.
# CTI_DESYNC_WINDOW forces it on elsewhere, which is how the watcher itself gets
# exercised without waiting for a human.
DESYNC_WINDOW="${CTI_DESYNC_WINDOW:-0}"
# Not in --regress: nobody joins, so there is no link to watch, and the watcher
# would only add noise to every probe's evidence.
((HOLD == 1 && NO_CLIENT_WAIT == 0)) && DESYNC_WINDOW="${CTI_DESYNC_WINDOW:-$HOLD_TIMEOUT}"
# The load generator that gives a joining client something to simulate is #8's
# scaffolding, and it is mutually exclusive with a Campaign: it spawns
# thirty-two WEST soldiers standing on the first four Objectives, and capture is
# by presence, so it hands WEST half the island. #16 stopped it running with no
# client at all; with a headless client on purpose (#17) it would run every
# time, so it is opt-in and off unless the desync question is the one being
# asked.
DESYNC_LOAD="${CTI_DESYNC_LOAD:-0}"
{
    echo "// Generated by spike/run.sh at bring-up. Do not edit."
    printf 'CTI_DESYNC_WATCH_SECS = %s;\n' "$DESYNC_WINDOW"
    printf 'CTI_DESYNC_LOAD = %s;\n' "$DESYNC_LOAD"
    # How long a probe leaves the world alone before reading it. A probe's
    # assertions are sized to its own default; this is for soaking a longer
    # unattended run to see what the Campaign does, not for stretching a window
    # until something passes.
    printf 'CTI_PROBE_SOAK = %s;\n' "${CTI_PROBE_SOAK:-0}"
    # How long a probe waits for a person to reach a Commander slot, when the run
    # is sending one (#18). Zero — the corpus default — means no client is coming
    # and a probe must not wait for one: a probe that waited out a client the run
    # never launched would spend its window on nothing every unattended pass.
    printf 'CTI_PROBE_CLIENT = %s;\n' "${CTI_PROBE_CLIENT:-0}"
} >"$STAGE/harness.sqf"
# One-off in-world probes go here rather than into the mission: the mission is
# the thing under test, and a probe that lives in it is one that ships. Named by
# CTI_HARNESS_EXTRA and appended to the generated harness.
if [[ -n "${CTI_HARNESS_EXTRA:-}" ]]; then
    [[ -f "$CTI_HARNESS_EXTRA" ]] || fail "infra_unavailable" "no such harness extra: $CTI_HARNESS_EXTRA"
    cat "$CTI_HARNESS_EXTRA" >>"$STAGE/harness.sqf"
    record "harness_extra" "$CTI_HARNESS_EXTRA"
fi

# Pack rather than copy the folder: an unpacked mission cannot be transmitted to
# a joining client, and a client without file patching never finishes loading one.
rm -rf "${SERVER_DIR:?}/mpmissions/$MISSION" "${SERVER_DIR:?}/mpmissions/$MISSION.pbo"
(cd "$REPO" && uv run --quiet python tools/pack_pbo.py "$STAGE" \
    "$SERVER_DIR/mpmissions/$MISSION.pbo") >/dev/null ||
    fail "infra_unavailable" "mission pack failed"

# The Linux server appends _x64 exactly as the Windows one does: SQF says
# "cti_shim", the engine opens cti_shim_x64.so.
rm -f "$SERVER_DIR/cti_shim.so"
install -m 0755 "$SO" "$SERVER_DIR/cti_shim_x64.so"
record "shim_size_bytes" "$(stat -c %s "$SO")"

rm -rf "${SERVER_DIR:?}/$MOD_NAME"
mkdir -p "$SERVER_DIR/$MOD_NAME"
cp -r "$BUILT_MOD/addons" "$SERVER_DIR/$MOD_NAME/"
record "addon_pbos" "$(find "$SERVER_DIR/$MOD_NAME/addons" -name '*.pbo' | wc -l)"

# ---------------------------------------------------------------- daemon
DAEMON_LOG="$OUT/daemon.log"
DAEMON_TELEMETRY="$OUT/daemon-telemetry.jsonl"
: >"$DAEMON_LOG"
# Truncate: telemetry is per-run evidence, and appending across runs turns it
# into a pile nobody can attribute.
: >"$DAEMON_TELEMETRY"
t=$(now)
# Hold mode has to be reachable from the Windows host, so bind every interface
# for the duration of that test only. Otherwise stay on loopback.
DAEMON_HOST=127.0.0.1
((HOLD == 1 && NO_CLIENT_WAIT == 0)) && DAEMON_HOST=0.0.0.0
# Which sides, if any, an AI Commander plays (#16, #17). Off unless asked for,
# so a world brought up for a human Commander is not quietly being played by one.
# A comma list, one seed per side in the same order: CTI_AI_SIDE=WEST,EAST with
# CTI_AI_SEED=1,4 is the unattended two-sided run, and the pair of seeds is what
# that Campaign replays from. A short seed list pads with 0.
AI_ARGS=()
if [[ -n "${CTI_AI_SIDE:-}" ]]; then
    IFS=',' read -ra AI_SIDES <<<"$CTI_AI_SIDE"
    IFS=',' read -ra AI_SEEDS <<<"${CTI_AI_SEED:-}"
    for i in "${!AI_SIDES[@]}"; do
        AI_ARGS+=(--ai "${AI_SIDES[$i]}:${AI_SEEDS[$i]:-0}")
    done
    record "ai_sides" "$CTI_AI_SIDE"
    record "ai_seeds" "${CTI_AI_SEED:-}"
fi
(cd "$REPO" && exec uv run --quiet cti-daemon \
    --host "$DAEMON_HOST" --port "$DAEMON_PORT" --telemetry "$DAEMON_TELEMETRY" \
    "${AI_ARGS[@]}") \
    >"$DAEMON_LOG" 2>&1 &
daemon_pid=$!
if ! wait_for "$DAEMON_LOG" "CTI_DAEMON_READY" 90 "$daemon_pid"; then
    fail "infra_unavailable" "daemon did not report ready; see $DAEMON_LOG"
fi
record "daemon_ready_secs" "$(since "$t")"

# ---------------------------------------------------------------- dedicated server
SERVER_LOG="$OUT/server.stdout.log"
: >"$SERVER_LOG"
t_boot=$(now)
(
    cd "$SERVER_DIR" || exit 1
    args=(-config="$SERVER_CONFIG" -mod="$MOD_NAME" -port="$PORT" -name=ctispike
        -world=empty -autoInit -noSound -limitFPS=100)
    [[ -n "$BASIC_CFG" ]] && args+=(-cfg="$BASIC_CFG")
    exec ./arma3server_x64 "${args[@]}"
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
    wait_for "$SERVER_LOG" "$LOG_PREFIX\|mission_running" "$BOOT_TIMEOUT" "$server_pid"
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
            -mod="$MOD_NAME" \
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

# ---------------------------------------------------------------- windows client
# A Windows-side headless client. No window, no focus, no role selection: it
# takes the HC1 slot the same way the Linux one does, but its traffic crosses
# the WSL2/Windows boundary, which is candidate cause 3 on #8.
win_hc_pid=""
if ((WINDOWS_HC == 1)); then
    WIN_BIN="$WINDOWS_ARMA_DIR/arma3server_x64.exe"
    if [[ ! -f "$WIN_BIN" ]]; then
        fail "infra_unavailable" "Windows Arma not found at $WIN_BIN"
    fi
    WIN_LOG="$OUT/windows-hc.log"
    : >"$WIN_LOG"
    t_win=$(now)
    (
        cd "$WINDOWS_ARMA_DIR" || exit 1
        exec ./arma3server_x64.exe -client \
            -connect="$WINDOWS_CONNECT" \
            -port="$PORT" \
            -password="$SERVER_PASSWORD" \
            -name=ctiwinhc \
            -world=empty \
            -noSound
    ) >"$WIN_LOG" 2>&1 &
    win_hc_pid=$!
    case "$(
        wait_for "$SERVER_LOG" "Player headlessclient connected \(id=HC" "$HC_TIMEOUT" "$win_hc_pid"
        echo $?
    )" in
    1)
        record "windows_hc_joined" "false"
        record "windows_hc_failure" "timeout after ${HC_TIMEOUT}s; see $WIN_LOG"
        ;;
    2)
        record "windows_hc_joined" "false"
        record "windows_hc_failure" "process exited; see $WIN_LOG"
        ;;
    *)
        record "windows_hc_joined" "true"
        record "windows_hc_join_secs" "$(since "$t_win")"
        ;;
    esac
fi

# ---------------------------------------------------------------- windows headed client
win_client_pid=""
if ((WINDOWS_CLIENT == 1)); then
    WIN_GAME="$WINDOWS_ARMA_DIR/arma3_x64.exe"
    [[ -f "$WIN_GAME" ]] || fail "infra_unavailable" "Windows Arma 3 not found at $WIN_GAME"
    # The client needs the addon too: client-side SQF is the only lever we have
    # inside the engine, and CfgFunctions compiles per machine.
    rm -rf "${WINDOWS_ARMA_DIR:?}/$MOD_NAME"
    mkdir -p "$WINDOWS_ARMA_DIR/$MOD_NAME"
    cp -r "$BUILT_MOD/addons" "$WINDOWS_ARMA_DIR/$MOD_NAME/"
    WIN_CLIENT_LOG="$OUT/windows-client.log"
    : >"$WIN_CLIENT_LOG"
    t_wc=$(now)
    (
        cd "$WINDOWS_ARMA_DIR" || exit 1
        exec ./arma3_x64.exe \
            -connect="$WINDOWS_CONNECT" \
            -port="$PORT" \
            -password="$SERVER_PASSWORD" \
            -mod="$MOD_NAME" \
            -name="$WINDOWS_CLIENT_PROFILE" \
            -window \
            -noSplash \
            -skipIntro \
            -noPause
    ) >"$WIN_CLIENT_LOG" 2>&1 &
    win_client_pid=$!
    record "windows_client_launched" "true"
    record "windows_client_connect" "$WINDOWS_CONNECT:$PORT"
fi

# ---------------------------------------------------------------- human client
if ((HOLD == 1)); then
    # Skipped under --regress: a regression run sends no client, so the banner is
    # noise and the wait is the whole window burned before the probe wait starts.
    if ((NO_CLIENT_WAIT == 0)); then
        lan_ip="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -E '^192\.168\.' | head -1)"
        cat >&2 <<EOF

  ================ ready for a client ================
  Arma 3 -> MULTIPLAYER -> DIRECT CONNECT
      address   127.0.0.1     (or ${lan_ip:-the LAN IP})
      port      $PORT
      password  $SERVER_PASSWORD
  Then pick the one slot and hit OK.
  Waiting up to $((HOLD_TIMEOUT / 60)) minutes. Ctrl-C to stop.
  ====================================================

EOF
        t_client=$(now)
        case "$(
            wait_for "$SERVER_LOG" "$LOG_PREFIX\|player_connected name=(\"\")?[^_]" "$HOLD_TIMEOUT" "$server_pid"
            echo $?
        )" in
        1)
            record "windows_client_joined" "false"
            record "windows_client_failure" "no client connected within ${HOLD_TIMEOUT}s"
            ;;
        2) fail "node_crashed" "server exited while waiting for a client; see $SERVER_LOG" ;;
        *)
            record "windows_client_connected_secs" "$(since "$t_client")"
            # Entering the mission is the thing in doubt, not connecting: the client
            # report only fires once init.sqf has actually run on that machine.
            if wait_for "$SERVER_LOG" "$LOG_PREFIX\|client_report" 180 "$server_pid"; then
                record "windows_client_joined" "true"
                record "windows_client_in_mission_secs" "$(since "$t_client")"
            else
                record "windows_client_joined" "connected-but-never-entered-mission"
            fi
            ;;
        esac
    fi

    # A probe that never finished is not a pass either. Waiting for its own
    # completion line means a probe outliving the hold window is a timeout,
    # rather than a HOLD-COMPLETE read off a log it had not finished writing.
    if [[ -n "${CTI_HARNESS_AWAIT:-}" ]]; then
        # The probe's own window, not a fixed 180 s. The client wait above ends
        # the moment a client connects, so a run with a headless client used to
        # leave the probe 180 s whatever window the caller asked for — and a
        # probe measuring a Squad marching does not fit in three minutes. This
        # is the hold window the caller sized to the subject, applied to the
        # subject; it is not a timeout stretched until something passes.
        PROBE_TIMEOUT="${CTI_PROBE_TIMEOUT:-$HOLD_TIMEOUT}"
        case "$(
            # FAIL ends the wait too: a probe that gave up short-circuits rather
            # than running out the clock, so the assertion below classifies it
            # instead of this timing out and calling an assertion a timeout.
            wait_for "$SERVER_LOG" "$LOG_PREFIX\|(.*$CTI_HARNESS_AWAIT|FAIL)" "$PROBE_TIMEOUT" "$server_pid"
            echo $?
        )" in
        1) fail "timeout" "probe never logged $CTI_HARNESS_AWAIT; see $SERVER_LOG" ;;
        2) fail "node_crashed" "server exited while the probe ran; see $SERVER_LOG" ;;
        esac
    fi

    grep -aoE "$LOG_PREFIX\|.*" "$SERVER_LOG" | sed "s/^$LOG_PREFIX|//; s/\"$//" >"$OUT/spike-lines.txt"
    log "--- in-mission results ---"
    cat "$OUT/spike-lines.txt" >&2
    # Hold mode used to exit here, before the assertion check below — so a run
    # in which an in-mission assertion fired still reported HOLD-COMPLETE. An
    # untyped green is worse than an untyped red: it is a pass nobody earned.
    # The push-path budget, off the run's own telemetry (#17). Recorded whatever
    # the verdict, and before it: a run that failed is exactly when the numbers
    # are worth having.
    while read -r line; do record "${line%%=*}" "${line#*=}"; done < <(
        cd "$REPO" && uv run --quiet python tools/push_path_report.py "$DAEMON_TELEMETRY"
    )

    # The run read back as a sequence, always: it costs nothing and it is the
    # artefact #35's timeout went without — a Squad at three of eight and no
    # account of the other five (#39).
    (cd "$REPO" && uv run --quiet python tools/timeline.py "$DAEMON_TELEMETRY") \
        >"$OUT/timeline.txt" 2>/dev/null || true

    if grep -q '^FAIL' "$OUT/spike-lines.txt"; then
        first_fail="$(grep '^FAIL' "$OUT/spike-lines.txt" | head -1)"
        fail "$(class_of "$first_fail")" "$first_fail"
    fi

    # A probe that says it staged deaths is checked against the daemon's own
    # file rather than against its own memory of doing so. This is the crossing:
    # the world claims, the record answers, and neither is asked to vouch for
    # itself. Silent for every probe that stages nothing.
    if grep -q 'casualty_staged' "$OUT/spike-lines.txt"; then
        if ! (cd "$REPO" && uv run --quiet python tools/timeline.py \
            "$DAEMON_TELEMETRY" --expect "$OUT/spike-lines.txt") \
            >"$OUT/timeline.txt" 2>"$OUT/timeline-unmatched.txt"; then
            fail "assertion_failed" \
                "staged deaths missing from telemetry: $(tr '\n' ' ' <"$OUT/timeline-unmatched.txt")"
        fi
    fi
    # HOLD-COMPLETE says "the window closed and nothing failed", which is the
    # right word for a run whose subject was a human joining. A regression run
    # has no window to close: it ended because the probe said so, so it gets the
    # verdict the corpus loop reads.
    if ((NO_CLIENT_WAIT == 1)); then
        record "verdict" "PASS"
    else
        record "verdict" "HOLD-COMPLETE"
    fi
    log "results: $RESULTS"
    exit 0
fi

# ---------------------------------------------------------------- harness verdict
case "$(
    wait_for "$SERVER_LOG" "$LOG_PREFIX\|done" "$HARNESS_TIMEOUT" "$server_pid"
    echo $?
)" in
1) fail "timeout" "in-mission harness never logged done; see $SERVER_LOG" ;;
2) fail "node_crashed" "server exited during the harness; see $SERVER_LOG" ;;
esac

grep -aoE "$LOG_PREFIX\|.*" "$SERVER_LOG" | sed "s/^$LOG_PREFIX|//; s/\"$//" >"$OUT/spike-lines.txt"
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
