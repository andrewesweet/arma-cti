#!/usr/bin/env bash
# The Arma tier's harness: bring up daemon -> dedicated server -> headless client
# inside WSL2, stage the world, run what the caller asked of it, tear it all down
# and leave one typed verdict behind.
#
# Built as Phase-0 measurement scaffolding (issue #2) and never replaced. Every
# way into the Arma tier ends here — the justfile's Arma-tier recipes and
# `spike/regress.sh`'s per-probe launch all exec this file, which is the honest
# way to read who runs it — so this is the runner every landing's in-world gate
# goes through, not scaffolding standing beside one. Its own defaults are still
# the Phase-0 world (see MISSION below); the Phase-1 callers override them.
# ADR-0011 owns the acceptance harness that replaces it and ADR-0016 reserves the
# `just accept` names for Phase 3. Until those exist, there is nothing else.
#
# `-e` is deliberately absent, and that is a decision rather than an omission
# (#83): a harness whose product is a *typed* verdict cannot afford to die at the
# failing line, because the trap would then exit with a bare status and no class
# — the untyped red the failure-class table calls a harness bug. Every command
# whose failure ends the run is checked here and routed through `fail`, which
# records the class before exiting. Adding `-e` would not make this file safer;
# it would make its failures anonymous.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Which machine this run is on (ADR-0032, #51), and with it the guard that
# protects the human rather than another agent (#41) — per host and gated on the
# host's role since #51. `spike/hosts.sh` sources `spike/host-guard.sh`, so the
# absolute-path resolution of the Windows interop binaries comes with it.
# Slot cleanup and the final resource pre-flight share one port/install
# observation in `slots.sh`; that file sources `hosts.sh`, so the host seam and
# exit-code vocabulary still enter through one source graph.
# shellcheck source=spike/slots.sh
source "$REPO/spike/slots.sh"
# The headed Windows client is one machine-wide thing and this run may be one of
# several agents wanting it (#127). Sourced always, taken only on the client path.
# shellcheck source=spike/client-lock.sh
source "$REPO/spike/client-lock.sh"
# The addon this run stages goes into the human's own Arma install, and a run
# that dies mid-copy used to leave it broken for the next play session (#153).
# shellcheck source=spike/play-install.sh
source "$REPO/spike/play-install.sh"
# The headed client is a host capability. Its Linux implementation owns Steam,
# Proton and Arma through one user-service cgroup.
# shellcheck source=spike/headed-client.sh
source "$REPO/spike/headed-client.sh"
SERVER_DIR="${CTI_SERVER_DIR:-$HOME/arma3server}"
SERVER_BIN="$SERVER_DIR/arma3server_x64"
OUT="${CTI_SPIKE_OUT:-$REPO/.spike-out}"
# NOT 2302. WSL2 mirrored networking shares the port space with Windows, and the
# Windows Arma client owns 2302-2306 plus its Steam query ports. BI wants >=100
# between server port sets, so the test tier lives at 2402-2406.
PORT="${CTI_SERVER_PORT:-2402}"
DAEMON_PORT="${CTI_DAEMON_PORT:-9099}"
# CTI_DAEMON_PORT moves the daemon; this is what moves the *world* with it. The
# shim resolves its daemon once per process from CTI_DAEMON_ADDR, defaulting to
# 127.0.0.1:9099 (extension/src/lib.rs), and nothing here used to set it — so a
# run on a non-default daemon port brought up a daemon nobody talked to and a
# world talking to whatever else held 9099. Measured on #44: two concurrent
# runs, isolated ports and dirs and daemons, and one daemon received both
# worlds' telemetry while the run that was not asserting on it reported PASS.
# Identical to the old behaviour at the default port, by construction.
export CTI_DAEMON_ADDR="${CTI_DAEMON_ADDR:-127.0.0.1:$DAEMON_PORT}"
SERVER_PASSWORD="${CTI_SERVER_PASSWORD:-ctispike}"
# The engine profile name, and with it where the engine writes `logFile` and its
# `.rpt`: `-profiles=` is broken on Linux, so `-name=` is the only lever there is.
# Per slot in a pool run (spike/slots.sh), because two engines writing one
# profile directory is a bulkhead with a shared wall — #58's reading of #44's
# doubled host creation, and a path by which one slot's crash corrupts state
# another slot reads.
SERVER_NAME="${CTI_SERVER_NAME:-ctispike}"
HC_NAME="${CTI_HC_NAME:-ctihc1}"
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
HEADED_CLIENT="${CTI_HEADED_CLIENT:-${CTI_WINDOWS_CLIENT:-0}}"
HEADED_CLIENT_DRIVER="${CTI_HEADED_CLIENT_DRIVER:-windows}"
WINDOWS_CLIENT_PROFILE="${CTI_WINDOWS_CLIENT_PROFILE:-ctitest}"
# How long teardown waits for a Windows process this run launched to leave the
# host's process list before it releases the tier (#119). A deadline on a
# shutdown, not a window sized until something passes: the engine took under ten
# seconds to go in every run observed, and a run that blows this reports it.
WINDOWS_EXIT_TIMEOUT="${CTI_WINDOWS_EXIT_TIMEOUT:-90}"
# How long this run will queue behind another run's hold on the machine-wide
# Windows client before calling it infra_unavailable (#127). Zero — refuse
# immediately, naming the holder — is the default, because a hand run's operator
# would rather be told than left waiting. `just regress --wait` sets it, for
# every probe rather than only the tail (#196).
#
# It is the budget for both places this run can meet somebody else's client: the
# lock acquire below, on the path that drives one, and the host guard after it,
# on every path. One deadline covers both (CLIENT_DEADLINE), so the two cannot
# spend it twice over. That is a guarantee rather than a saving — a run that
# took the lock has nothing left to queue behind at the guard, so the two are
# mutually exclusive by construction — and the point of writing it as one
# deadline is that it stays true if that ever stops being so.
CLIENT_LOCK_WAIT="${CTI_CLIENT_LOCK_WAIT:-0}"

BOOT_TIMEOUT="${CTI_BOOT_TIMEOUT:-240}"
HC_TIMEOUT="${CTI_HC_TIMEOUT:-90}"
HARNESS_TIMEOUT="${CTI_HARNESS_TIMEOUT:-300}"
# How long teardown will wait for a child it has just SIGKILLed before giving up
# on reaping it. `wait` has no deadline of its own, and a process wedged in
# uninterruptible sleep made teardown unbounded — with this run's slot lock and
# the machine-wide client lock still held (#144).
REAP_TIMEOUT="${CTI_REAP_TIMEOUT:-30}"
# The deadline on every `uv run` this harness makes. These are bounds on
# infrastructure — packing a mission, reading telemetry back — and never on a
# probe's subject: none of them runs while the world is being measured. A cold
# `uv` cache or a stalled index used to hang the run mid-slot-hold with nothing
# said about it.
UV_TIMEOUT="${CTI_UV_TIMEOUT:-300}"

SKIP_HC=0
HOLD=0
NO_CLIENT_WAIT=0
HOLD_TIMEOUT="${CTI_HOLD_TIMEOUT:-900}"
# One mode flag at most. A second argument used to be read by nobody and
# silently dropped, which is how a mistyped invocation runs in a mode the
# caller did not ask for. A usage error exits CTI_EXIT_USAGE, like regress.sh's
# `die` — nothing was brought up, so there is no verdict to type, and the code
# is one no class row claims (#147).
if (($# > 1)); then
    printf '[spike] too many arguments: %s — one mode flag at most (--no-hc | --hold | --regress)\n' "$*" >&2
    exit "$CTI_EXIT_USAGE"
fi
case "${1:-}" in
--no-hc) SKIP_HC=1 ;;
# --hold brings everything up and keeps it up so a human client can join, then
# reports what that client did — the Windows-client join and .dll load test.
# --regress is the regression tier's mode (issue #23): everything --hold does,
# minus the two things that only make sense when a human is joining — the
# direct-connect banner, and the wait for a client that a regression run never
# sends and would otherwise cost every quick probe its whole window. One arm,
# because that one difference is NO_CLIENT_WAIT and the shared SKIP_HC line had
# already been copied apart once (#161).
--hold | --regress)
    # The headless client is off by default because hold mode was built for a
    # human joining. CTI_HOLD_HC=1 brings it back: #17's unattended run has to
    # happen on the dedicated-server-plus-headless-client topology the MVP
    # names, and a probe cannot assert a node the harness never started.
    SKIP_HC=$((1 - ${CTI_HOLD_HC:-0}))
    HOLD=1
    [[ "$1" == --regress ]] && NO_CLIENT_WAIT=1
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
proton_client_started=""
# Set once this run has begun writing into the human's Arma install, which only
# happens under the machine-wide client lock. Teardown reads it to decide whether
# the swap window is this run's to close (#153); a run that never staged must not
# touch those paths, because a concurrent client run's rename is exactly what it
# would be racing.
play_install_staged=""

log() { printf '[spike] %s\n' "$*" >&2; }
# results.env is read a line at a time — `sed -n 's/^verdict=//p'` in regress.sh
# — so a newline inside a value would forge a record nobody wrote. Flattened
# rather than escaped: no reader of this file unescapes anything, and one line
# per record is what every one of them already assumes (#83).
record() {
    local value="${2//$'\n'/ }"
    printf '%s=%s\n' "$1" "$value" >>"$RESULTS"
    log "$1=$value"
}
# The clock every deadline in this file is built on, in whole milliseconds, and
# integer arithmetic all the way down.
#
# This used to be `date +%s.%N` compared through `bc`, which made `bc` a
# load-bearing dependency of the timeout mechanism itself — and one that failed
# *open* (#144). `(($(echo "$(now) > $deadline" | bc)))` with no `bc` on PATH
# evaluates an empty operand, which is false, so the deadline never fired and
# every wait in this harness ran until the process it watched happened to die.
# That is #41's shape (a check that could not run reported as a check that
# passed) inside the thing that enforces deadlines. Bash carries its own clock
# and its own arithmetic, and neither of those can go missing.
now() {
    local t="${EPOCHREALTIME:-}"
    t="${t/,/.}" # some locales put a comma there
    if [[ "$t" =~ ^([0-9]+)\.([0-9]+)$ ]]; then
        local frac="${BASH_REMATCH[2]}000"
        printf '%s%s' "${BASH_REMATCH[1]}" "${frac:0:3}"
        return 0
    fi
    # bash before 5.0 has no EPOCHREALTIME. `date` is still not `bc`: a failure
    # here is reported rather than swallowed, and the pre-flight below refuses
    # the run outright if this cannot produce a number.
    t="$(date +%s%3N 2>/dev/null)"
    [[ "$t" =~ ^[0-9]+$ ]] || return 1
    printf '%s' "$t"
}
# Whole seconds and milliseconds, the shape `scale=3` used to print.
since() {
    local start="$1" end delta
    end="$(now)" || {
        printf 'unknown'
        return 1
    }
    delta=$((end - start))
    ((delta < 0)) && delta=0
    printf '%d.%03d' $((delta / 1000)) $((delta % 1000))
}

# `wait` with a deadline, which bash does not have (#144). A child that has
# exited — vanished, or a zombie this shell has not collected — is reaped
# immediately, because `wait` on it returns at once. One that has not is polled
# to the bound and then reported rather than waited on: the state comes from
# `/proc/<pid>/stat`, whose comm field can contain anything including spaces and
# brackets, so it is read after the last `)` rather than as field three.
reap_bounded() {
    local pid="$1" deadline=$((SECONDS + REAP_TIMEOUT)) state
    while :; do
        state="$(sed -e 's/^.*) //' -e 's/ .*//' "/proc/$pid/stat" 2>/dev/null)"
        if [[ -z "$state" || "$state" == Z ]]; then
            wait "$pid" 2>/dev/null
            return 0
        fi
        ((SECONDS >= deadline)) && break
        sleep 0.25
    done
    log "teardown: pid $pid was still alive (state ${state:-unknown}) ${REAP_TIMEOUT}s after SIGKILL; not waiting on it"
    return 1
}

cleanup() {
    local code=$?
    if [[ -n "$proton_client_started" ]]; then
        cti_proton_client_stop "$OUT/headed-client" ||
            log "teardown: Proton client service did not become cleanly inactive; see $OUT/headed-client"
    fi
    for pid in "$win_client_pid" "$win_hc_pid" "$hc_pid" "$server_pid" "$daemon_pid"; do
        [[ -n "$pid" ]] && kill "$pid" 2>/dev/null
    done
    sleep 2
    for pid in "$win_client_pid" "$win_hc_pid" "$hc_pid" "$server_pid" "$daemon_pid"; do
        [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null
    done
    # Reaped, not merely signalled. A pid this shell launched and has not reaped
    # is a process that may still be holding what it held, and the next thing to
    # happen after this trap is another run taking the tier (#119).
    #
    # And reaped under a deadline (#144). A bare `wait` on a process that will
    # not die — D state, a stuck driver — is teardown hanging while this run
    # holds its slot lock and the machine-wide client lock, which is the one
    # thing teardown must never do. A pid that survives the bound is reported and
    # left: teardown cannot fix it, and the next holder of this slot recovers it
    # as stale state (ADR-0022).
    for pid in "$win_client_pid" "$win_hc_pid" "$hc_pid" "$server_pid" "$daemon_pid"; do
        [[ -n "$pid" ]] && reap_bounded "$pid"
    done
    # The server's own .rpt, now that the engine has stopped writing it. Here
    # rather than on the happy path so that a run which failed — the run whose
    # scripting errors are worth reading — carries it too.
    collect_server_rpt
    # Windows processes are children of WSL interop, not of this shell, so a
    # kill on the interop wrapper does not always reach them. By absolute path:
    # `taskkill.exe` by name was not on the agent's PATH either, so this
    # silently left a Windows process alive after every run that launched one
    # (#41). Whether the bare name resolves varies by session (#180), which is
    # more reason for the absolute path, not less.
    #
    # Keyed on having launched one, not on having been asked to: a run that
    # refuses at the pre-flight below exits through here, and killing
    # arma3_x64.exe on the way out would be this harness doing the exact thing
    # the pre-flight just refused to do.
    #
    # The return is read rather than discarded: teardown cannot change a verdict
    # already recorded, but a Windows process this run launched and could not
    # kill is the next run's infra_unavailable, and it should be in this run's
    # evidence rather than in nobody's (#83).
    #
    # And waited for, not just asked. `taskkill /F` returns when the request has
    # been made, not when the process is gone, so a run used to release the tier
    # with its own client still in the Windows process list — where the next
    # run's host guard read it as a play session and stopped the corpus on its
    # own leavings (#119). The guard cannot be taught to recognise ours without
    # also being able to excuse the human's, so the wait belongs here, in the run
    # that owns the process.
    if [[ -n "$win_hc_pid" ]]; then
        cti_windows_taskkill arma3server_x64.exe ||
            log "teardown: arma3server_x64.exe may still be running on the Windows host"
        cti_windows_wait_gone arma3server_x64.exe "$WINDOWS_EXIT_TIMEOUT" ||
            log "teardown: arma3server_x64.exe had not left the Windows process list"
    fi
    if [[ -n "$win_client_pid" ]]; then
        cti_windows_taskkill arma3_x64.exe ||
            log "teardown: arma3_x64.exe may still be running on the Windows host"
        cti_windows_wait_gone arma3_x64.exe "$WINDOWS_EXIT_TIMEOUT" ||
            log "teardown: arma3_x64.exe had not left the Windows process list"
    fi
    # The one instant in which the human's Arma install has no `@cti` is between
    # the two renames of the swap, and this is what closes it for a run that was
    # interrupted inside it (#153). Under the client lock, before it is dropped,
    # and only for a run that staged: the paths this touches are ones a
    # concurrent client run renames, and the lock is what makes "the previous
    # copy is mine to put back" true.
    if [[ -n "$play_install_staged" ]]; then
        cti_play_install_repair "$WINDOWS_ARMA_DIR" "$MOD_NAME" ||
            log "teardown: the play install at $WINDOWS_ARMA_DIR may have no $MOD_NAME — restage before playing"
    fi
    # Last, and after that wait rather than before it (#127). The whole value of
    # the client lock is the ordering it guarantees: while a run holds it, no
    # other run's client is in the process list. Releasing before the wait would
    # hand the next run a lock whose promise had already been broken, and it
    # would read our still-exiting client as the human's play session — which is
    # exactly the #119 collision, moved rather than fixed.
    cti_client_lock_release
    exit "$code"
}
trap cleanup EXIT INT TERM

# Wait for a regex to appear in a growing log. Returns 1 on timeout, 2 if the
# process being waited on died first — a distinct failure class, never a pass —
# and 3 if no deadline could be computed at all, which is a harness bug and is
# never allowed to become a wait without an end (#144). Every caller types all
# three, because a wait whose bound could not be set has measured nothing.
wait_for() {
    local file="$1" pattern="$2" timeout="$3" pid="${4:-}"
    local deadline start t
    [[ "$timeout" =~ ^[0-9]+$ ]] || return 3
    start="$(now)" || return 3
    deadline=$((start + timeout * 1000))
    while :; do
        if [[ -f "$file" ]] && grep -qE "$pattern" "$file" 2>/dev/null; then return 0; fi
        if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then return 2; fi
        t="$(now)" || return 3
        ((t > deadline)) && return 1
        sleep 0.25
    done
}

# wait_for's status ladder, applied: 1 is the subject outrunning its deadline,
# 2 is the process dying first, 3 is a bound that could not be set (#144). The
# classes are the failure-class table's and identical at every site — only the
# words differ, so the words are the arguments. This idiom was eight inline
# copies of the same case block before it was one function (#161).
await_or_fail() {
    local file="$1" pattern="$2" timeout="$3" pid="$4"
    local on_timeout="$5" on_died="$6" on_unbounded="$7"
    case "$(
        wait_for "$file" "$pattern" "$timeout" "$pid"
        echo $?
    )" in
    1) fail "timeout" "$on_timeout" ;;
    2) fail "node_crashed" "$on_died" ;;
    3) fail "infra_unavailable" "$on_unbounded" ;;
    esac
}

# The optional headless-client legs, Linux and Windows, record rather than fail:
# an HC that did not join is a fact about the run that the verdict names through
# the legs convention (#116), not a stop. Only the third rung fails, because a
# wait that could not be bounded has measured nothing (#144). One body for the
# two legs — they were verbatim copies but for the record prefix (#161).
await_hc_join() {
    local prefix="$1" pid="$2" t0="$3" hclog="$4" required="${5:-0}"
    case "$(
        # The HC's player name is "headlessclient" regardless of -name=, and it
        # is assigned an id=HC… rather than a numeric slot id.
        wait_for "$SERVER_LOG" "Player headlessclient connected \(id=HC" "$HC_TIMEOUT" "$pid"
        echo $?
    )" in
    1)
        record "${prefix}joined" "false"
        record "${prefix}failure" "timeout after ${HC_TIMEOUT}s; see $hclog"
        ((required == 1)) &&
            fail "infra_unavailable" "demanded headless client did not join within ${HC_TIMEOUT}s; see $hclog"
        ;;
    2)
        record "${prefix}joined" "false"
        record "${prefix}failure" "process exited; see $hclog"
        ((required == 1)) &&
            fail "infra_unavailable" "demanded headless client exited before joining; see $hclog"
        ;;
    3) fail "infra_unavailable" "CTI_HC_TIMEOUT is not a whole number of seconds: $HC_TIMEOUT" ;;
    *)
        record "${prefix}joined" "true"
        record "${prefix}join_secs" "$(since "$t0")"
        ;;
    esac
}

# Fail with the class an in-mission FAIL line declared, decided in the class
# table's own Python home (tools/pool_merge.py `class-of` — #147, joining the
# home #161's routing named). In-world code writes `FAIL class=timeout ...` as
# well as plain assertions, and calling every red assertion_failed sends the
# reader to fix code when the table says investigate synchronisation; while a
# class the table has never heard of (`class=timout`), or one no FAIL line may
# claim (`class=pass` would invert the verdict downstream), used to flow
# through the whole tier as an unknown class — it is caught here, where the
# line is first read, as the harness bug it is.
#
# Fails closed at this site per ADR-0049's mechanics: a mapper `timeout`
# killed is infra_unavailable — a check that could not run is not a check that
# passed (#41) — and a mapper that ran and failed leaves the red it was typing
# untyped, which is a harness bug and reported as one.
fail_with_mission_class() {
    local line="$1" typed status class detail
    typed="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python tools/pool_merge.py \
        class-of --line "$line")"
    status=$?
    if ((status == 124)); then
        fail "infra_unavailable" \
            "the in-mission class mapper did not finish within ${UV_TIMEOUT}s (uv run tools/pool_merge.py class-of); the line it was typing: $line"
    elif ((status != 0)); then
        fail "untyped_harness_failure" \
            "the in-mission class mapper failed (exit $status) — harness bug; the line it was typing: $line"
    fi
    class="$(sed -n 's/^class=//p' <<<"$typed" | head -1)"
    detail="$(sed -n 's/^detail=//p' <<<"$typed" | head -1)"
    [[ -n "$class" ]] ||
        fail "untyped_harness_failure" \
            "the in-mission class mapper answered no class= line — harness bug; the line it was typing: $line"
    fail "$class" "$detail"
}

# The vacuity convention, mechanically (#116, ADR-0037). A probe with an
# optional leg — a half of its subject that needs something the world alone
# cannot supply, a headed client above all — says what became of that leg in one
# line per leg:
#
#     CTI|LEG name=<leg> status=ran
#     CTI|LEG name=<leg> status=unverified reason=<why>
#
# and the verdict names them. A leg that did not run is not a pass: it routes to
# infra_unavailable, which this tier already refuses to read as a result, rather
# than being counted green. Before this, `human-commander` finished green in
# every corpus run with the only leg that crosses the machine boundary switched
# off by an environment default, and said so in a log line nothing scored.
#
# Asked after the FAIL sweep on both verdict paths, so a red keeps its own class:
# a probe that failed produced a result, and an unverified leg is only the story
# when there is no other one.
assert_legs_ran() {
    local lines_file="$1" seen unverified
    seen="$(sed -n 's/^LEG name=\([^ ]*\) status=\([^ ]*\).*/\1:\2/p' "$lines_file" | paste -sd' ' -)"
    [[ -n "$seen" ]] && record "legs" "$seen"
    unverified="$(grep -a '^LEG .*status=unverified' "$lines_file" | sed 's/^LEG //' | paste -sd'; ' -)"
    if [[ -n "$unverified" ]]; then
        fail "infra_unavailable" "a leg of this probe did not run: $unverified"
    fi
    return 0
}

# Both verdict paths end their sweep here: the first FAIL line keeps the class
# the world declared (#23), then the legs convention is asked — after the sweep,
# so a red keeps its own class (#116). One function, because the two paths
# carrying parallel copies of this block is the exact structure that let #23's
# fix survive on one path and rot on the other (#83, #161).
assert_clean_run() {
    local lines_file="$1" first_fail
    if grep -q '^FAIL' "$lines_file"; then
        first_fail="$(grep '^FAIL' "$lines_file" | head -1)"
        fail_with_mission_class "$first_fail"
    fi
    assert_legs_ran "$lines_file"
}

# The headed client's own log, off the Windows host. The Linux server's stdout
# is the only log this harness has otherwise, and there are things only the
# client's RPT says — a remoteExec its whitelist refused is written there and
# nowhere else, because the sender is where the engine checks first.
#
# The newest .rpt in the client's log directory is this run's: the engine opens
# a fresh one per launch, and this is called while that client is still alive.
collect_client_rpt() {
    local report status line
    local -a configured_dir=()
    if [[ -n "${CTI_WINDOWS_CLIENT_RPT_DIR:-}" ]]; then
        configured_dir=(--configured-dir "$CTI_WINDOWS_CLIENT_RPT_DIR")
    fi
    report="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python tools/client_rpt.py \
        --users-dir "${CTI_WINDOWS_USERS_DIR:-/mnt/c/Users}" \
        "${configured_dir[@]}" --out "$OUT/windows-client.rpt")" 2>"$OUT/client-rpt-error.txt"
    status=$?
    if ((status != 0)); then
        if ((status == 124)); then
            record "windows_client_rpt" \
                "unavailable: client_rpt.py did not finish within ${UV_TIMEOUT}s"
        else
            record "windows_client_rpt" \
                "unavailable: client_rpt.py failed: $(tail -3 "$OUT/client-rpt-error.txt" | tr '\n' ' ')"
        fi
        return 0
    fi
    if [[ -z "$report" ]]; then
        record "windows_client_rpt" "unavailable: client_rpt.py returned no result"
        return 0
    fi
    while IFS= read -r line; do
        if [[ "$line" != *=* ]]; then
            record "windows_client_rpt" "unavailable: client_rpt.py returned an invalid result"
            return 0
        fi
        record "${line%%=*}" "${line#*=}"
    done <<<"$report"
}

# The dedicated server's own `.rpt`, which is where the engine writes scripting
# errors it never puts on stdout. It lands in the profile directory `-name=`
# chooses, so it is only *this run's* rpt once the profile is per slot — before
# that, three concurrent slots wrote one file and the newest-file rule would have
# handed a run somebody else's errors (#47). Called from teardown so that every
# exit path, including a `fail`, carries it.
collect_server_rpt() {
    local dir newest
    dir="$HOME/.local/share/Arma 3 - Other Profiles/$SERVER_NAME"
    [[ -d "$dir" ]] || return 0
    newest="$(ls -t "$dir"/*.rpt 2>/dev/null | head -1)"
    [[ -n "$newest" ]] || return 0
    cp "$newest" "$OUT/server.rpt" 2>/dev/null || return 0
    record "server_rpt" "$OUT/server.rpt"
    record "server_rpt_source" "$newest"
}

fail() {
    record "verdict" "FAIL"
    record "failure_class" "$1"
    record "failure_detail" "$2"
    log "FAILED: $1 — $2"
    exit 1
}

# The machine's global IPv4 addresses, one per line — the shared source for the
# three places this run reads them. The LAN-IP filter and the wsl_lan_ip record
# each used to carry their own `ip -4 -o addr` pipeline, and a fourth copy would
# have been the place a divergence landed (#92).
global_ipv4s() {
    ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1
}

# The first RFC1918 address — the daemon address a Windows client crossing the
# WSL2 boundary is told. Staging writes it into daemon_addrs.sqf and the hold
# banner prints it, so the pipeline behind it has one home (#92).
lan_ip() {
    printf '%s\n' "${LAN_IP:-}"
}

# The in-mission lines this run reads back, stripped of the log prefix. Both
# verdict paths end their sweep on this extraction, so the grep/sed pair has one
# home rather than a copy each (#92).
extract_spike_lines() {
    grep -aoE "$LOG_PREFIX\|.*" "$SERVER_LOG" | sed "s/^$LOG_PREFIX|//; s/\"$//" >"$OUT/spike-lines.txt"
}

# --------------------------------------------------------------------- the stages
# Each node this run brings up is one named function, so the main flow below reads
# as the sequence it is — stage, daemon, server, headless client, the Windows
# legs — rather than as banner comments over straight-line script (#92).
# `start_daemon`, already a function for its mid-run restart (#96), is the model.

stage_mission() {
    # Profiles: -profiles= is broken on Linux, the engine insists on these paths.
    # Every staging step below is checked: an unchecked `cp` that failed used to
    # surface as a confusing engine-side failure three steps later, when what
    # happened was a full disk or a directory somebody else's run had removed (#83).
    mkdir -p "$HOME/.local/share/Arma 3" "$HOME/.local/share/Arma 3 - Other Profiles" ||
        fail "infra_unavailable" "could not create the engine's profile directories under $HOME/.local/share"

    # A joining Windows client has to be told where the daemon is, and whether
    # mirrored-mode loopback carries it is exactly what the hold test measures — so
    # stage the mission with both candidates and let the client try them in order.
    LAN_IP="$(lan_ip)"
    STAGE="$OUT/mission/$MISSION"
    rm -rf "$OUT/mission"
    mkdir -p "$STAGE" || fail "infra_unavailable" "could not create the staging directory $STAGE"
    [[ -d "$REPO/missions/$MISSION" ]] || fail "infra_unavailable" "no such mission: missions/$MISSION"
    cp -r "$REPO/missions/$MISSION/." "$STAGE/" ||
        fail "infra_unavailable" "could not stage missions/$MISSION into $STAGE"
    {
        echo "// Generated by spike/run.sh at bring-up. Do not edit."
        printf 'CTI_SPIKE_DAEMON_ADDRS = ["127.0.0.1:%s"' "$DAEMON_PORT"
        [[ -n "$LAN_IP" ]] && printf ', "%s:%s"' "$LAN_IP" "$DAEMON_PORT"
        printf '];\n'
    } >"$STAGE/daemon_addrs.sqf"

    # Issue #8: hold mode is the only mode a real client joins in, so it is the
    # only mode that watches desync by default; zero elsewhere keeps the sampling
    # off. CTI_DESYNC_WINDOW forces it on elsewhere, which is how the watcher
    # itself gets exercised without waiting for a human.
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
    # asked. Opt-in now decides whether the tool is *staged* rather than whether a
    # shipped one runs (#128, ADR-0045): a build a human plays does not contain it.
    DESYNC_LOAD="${CTI_DESYNC_LOAD:-0}"
    {
        echo "// Generated by spike/run.sh at bring-up. Do not edit."
        printf 'CTI_DESYNC_WATCH_SECS = %s;\n' "$DESYNC_WINDOW"
        # How long a probe leaves the world alone before reading it. A probe's
        # assertions are sized to its own default; this is for soaking a longer
        # unattended run to see what the Campaign does, not for stretching a window
        # until something passes.
        printf 'CTI_PROBE_SOAK = %s;\n' "${CTI_PROBE_SOAK:-0}"
        # How long a probe waits for a person to reach a Commander slot, when the run
        # is sending one (#18). Zero means no client is coming and a probe must not
        # wait for one: a probe that waited out a client the run never launched would
        # spend its window on nothing.
        #
        # This is the script's default and no longer the corpus's. A probe whose
        # subject includes the client leg declares the client in its own `env:`
        # header and gets a non-zero value there — optional legs default on in the
        # corpus (ADR-0037, #116) — so zero now means "run by hand without one", and
        # such a probe reports its client leg unverified rather than green.
        printf 'CTI_PROBE_CLIENT = %s;\n' "${CTI_PROBE_CLIENT:-0}"
    } >"$STAGE/harness.sqf"
    # Shared probe scaffolding, ahead of the probe that uses it. Unconditional: it
    # defines functions and asserts nothing, and staging it always means the staged
    # harness.sqf in the evidence is the whole of what ran (#46).
    PRELUDE="$REPO/spike/probe-prelude.sqf"
    [[ -f "$PRELUDE" ]] || fail "infra_unavailable" "probe prelude missing: $PRELUDE"
    cat "$PRELUDE" >>"$STAGE/harness.sqf"
    # #8's load generator, staged only when this run asked for it (#128, ADR-0045).
    # It lived in the addon and was switched on by a variable in the file above,
    # which meant every build a human could play carried it; the switch now decides
    # whether the tool is here at all. It goes after the prelude because it waits on
    # `cti_probe_fnc_worldReady`, and before any probe because a probe that wanted
    # the load would want it already going.
    if ((DESYNC_LOAD > 0)); then
        DESYNC_TOOL="$REPO/spike/desync-load.sqf"
        [[ -f "$DESYNC_TOOL" ]] || fail "infra_unavailable" "desync load generator missing: $DESYNC_TOOL"
        cat "$DESYNC_TOOL" >>"$STAGE/harness.sqf"
        record "desync_load" "staged"
    fi
    # One-off in-world probes go here rather than into the mission: the mission is
    # the thing under test, and a probe that lives in it is one that ships. Named by
    # CTI_HARNESS_EXTRA and appended to the generated harness.
    if [[ -n "${CTI_HARNESS_EXTRA:-}" ]]; then
        [[ -f "$CTI_HARNESS_EXTRA" ]] || fail "infra_unavailable" "no such harness extra: $CTI_HARNESS_EXTRA"
        cat "$CTI_HARNESS_EXTRA" >>"$STAGE/harness.sqf"
        record "harness_extra" "$CTI_HARNESS_EXTRA"
        # A fixture under spike/playtest/ is what marks a session as a human one
        # (session-hold.sqf's header), and a human session gets the Zeus-style
        # observer (#178) — staged with the fixture rather than switched by another
        # boot-line knob, so the affordance rides the boot lines briefs already
        # quote. The corpus never stages a file from that directory, which is the
        # boundary #178 draws: a curator must not be present in anything the
        # regression corpus boots. observer.sqf itself guards against being staged
        # twice, so naming it as the fixture stays harmless.
        case "$CTI_HARNESS_EXTRA" in
        *spike/playtest/*)
            OBSERVER="$REPO/spike/playtest/observer.sqf"
            [[ -f "$OBSERVER" ]] || fail "infra_unavailable" "playtest observer missing: $OBSERVER"
            cat "$OBSERVER" >>"$STAGE/harness.sqf"
            record "playtest_observer" "staged"
            ;;
        esac
    fi

    # Pack rather than copy the folder: an unpacked mission cannot be transmitted to
    # a joining client, and a client without file patching never finishes loading one.
    rm -rf "${SERVER_DIR:?}/mpmissions/$MISSION" "${SERVER_DIR:?}/mpmissions/$MISSION.pbo"
    (cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python tools/pack_pbo.py "$STAGE" \
        "$SERVER_DIR/mpmissions/$MISSION.pbo") >/dev/null
    pack_status=$?
    if ((pack_status == 124)); then
        fail "infra_unavailable" "mission pack did not finish within ${UV_TIMEOUT}s (uv run tools/pack_pbo.py)"
    elif ((pack_status != 0)); then
        fail "infra_unavailable" "mission pack failed"
    fi

    # The Linux server appends _x64 exactly as the Windows one does: SQF says
    # "cti_shim", the engine opens cti_shim_x64.so.
    rm -f "$SERVER_DIR/cti_shim.so"
    install -m 0755 "$SO" "$SERVER_DIR/cti_shim_x64.so" ||
        fail "infra_unavailable" "could not install the shim into $SERVER_DIR"
    record "shim_size_bytes" "$(stat -c %s "$SO")"

    rm -rf "${SERVER_DIR:?}/$MOD_NAME"
    mkdir -p "$SERVER_DIR/$MOD_NAME" ||
        fail "infra_unavailable" "could not create $SERVER_DIR/$MOD_NAME"
    cp -r "$BUILT_MOD/addons" "$SERVER_DIR/$MOD_NAME/" ||
        fail "infra_unavailable" "could not stage the addon into $SERVER_DIR/$MOD_NAME"
    record "addon_pbos" "$(find "$SERVER_DIR/$MOD_NAME/addons" -name '*.pbo' | wc -l)"
}

start_server() {
    SERVER_LOG="$OUT/server.stdout.log"
    : >"$SERVER_LOG"
    t_boot=$(now)
    (
        cti_client_lock_disown
        cd "$SERVER_DIR" || exit 1
        args=(-config="$SERVER_CONFIG" -mod="$MOD_NAME" -port="$PORT" -name="$SERVER_NAME"
            -world=empty -autoInit -noSound -limitFPS=100)
        [[ -n "$BASIC_CFG" ]] && args+=(-cfg="$BASIC_CFG")
        exec ./arma3server_x64 "${args[@]}"
    ) >"$SERVER_LOG" 2>&1 &
    server_pid=$!

    await_or_fail "$SERVER_LOG" "Host identity created|Dedicated host created" 120 "$server_pid" \
        "server never created a host in 120s; see $SERVER_LOG" \
        "server process exited during boot; see $SERVER_LOG" \
        "no deadline could be set for the server-boot wait"
    record "server_host_up_secs" "$(since "$t_boot")"

    await_or_fail "$SERVER_LOG" "$LOG_PREFIX\|mission_running" "$BOOT_TIMEOUT" "$server_pid" \
        "mission did not reach running state in ${BOOT_TIMEOUT}s; see $SERVER_LOG" \
        "server process exited while loading the mission; see $SERVER_LOG" \
        "CTI_BOOT_TIMEOUT is not a whole number of seconds: $BOOT_TIMEOUT"
    record "server_mission_running_secs" "$(since "$t_boot")"
    record "server_version" "$(grep -aoE 'Arma 3 Console version [0-9.]+' "$SERVER_LOG" | head -1 | awk '{print $NF}')"
}

start_hc() {
    HC_LOG="$OUT/hc.stdout.log"
    : >"$HC_LOG"
    t_hc=$(now)
    (
        cti_client_lock_disown
        cd "$SERVER_DIR" || exit 1
        # The password must match server.cfg or the client never gets past connect.
        exec ./arma3server_x64 -client \
            -connect=127.0.0.1 \
            -mod="$MOD_NAME" \
            -port="$PORT" \
            -password="$SERVER_PASSWORD" \
            -name="$HC_NAME" \
            -world=empty \
            -noSound \
            -limitFPS=50
    ) >"$HC_LOG" 2>&1 &
    hc_pid=$!

    await_hc_join "hc_" "$hc_pid" "$t_hc" "$HC_LOG" "${CTI_HOLD_HC:-0}"
}

start_windows_hc() {
    # A Windows-side headless client. No window, no focus, no role selection: it
    # takes the HC1 slot the same way the Linux one does, but its traffic crosses
    # the WSL2/Windows boundary, which is candidate cause 3 on #8.
    win_hc_pid=""
    ((WINDOWS_HC == 1)) || return 0
    WIN_BIN="$WINDOWS_ARMA_DIR/arma3server_x64.exe"
    if [[ ! -f "$WIN_BIN" ]]; then
        fail "infra_unavailable" "Windows Arma not found at $WIN_BIN"
    fi
    WIN_LOG="$OUT/windows-hc.log"
    : >"$WIN_LOG"
    t_win=$(now)
    (
        cti_client_lock_disown
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
    await_hc_join "windows_hc_" "$win_hc_pid" "$t_win" "$WIN_LOG"
}

start_windows_client() {
    win_client_pid=""
    ((HEADED_CLIENT == 1)) || return 0
    WIN_GAME="$WINDOWS_ARMA_DIR/arma3_x64.exe"
    [[ -f "$WIN_GAME" ]] || fail "infra_unavailable" "Windows Arma 3 not found at $WIN_GAME"
    # The client needs the addon too: client-side SQF is the only lever we have
    # inside the engine, and CfgFunctions compiles per machine.
    #
    # And it goes into the *human's* Steam install, which is why this is not a
    # bare `rm -rf` and `cp` any more (#153). Staged beside the live folder,
    # checked against its source, swapped in by rename: a run killed anywhere in
    # here leaves the play install either previous-good or verified-new, never
    # the half-staged mod somebody finds at the start of an evening.
    play_install_staged=1
    if ! stage_detail="$(cti_play_install_stage "$WINDOWS_ARMA_DIR" "$MOD_NAME" "$BUILT_MOD/addons")"; then
        fail "infra_unavailable" \
            "${stage_detail:-could not stage the addon onto the Windows host at $WINDOWS_ARMA_DIR/$MOD_NAME}"
    fi
    WIN_CLIENT_LOG="$OUT/windows-client.log"
    : >"$WIN_CLIENT_LOG"
    t_wc=$(now)
    (
        cti_client_lock_disown
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
    record "headed_client_launched" "true"
    record "headed_client_driver" "windows"
}

start_proton_client() {
    proton_client_started=""
    ((HEADED_CLIENT == 1)) || return 0
    if ! cti_proton_client_start "$OUT/headed-client" "$WINDOWS_CONNECT" "$PORT" \
        "$SERVER_PASSWORD" "$WINDOWS_CLIENT_PROFILE" "$SERVER_DIR/$MOD_NAME"; then
        fail "infra_unavailable" \
            "could not start the owned Proton client service; see $OUT/headed-client"
    fi
    proton_client_started=1
    record "headed_client_launched" "true"
    record "headed_client_driver" "proton"
    record "headed_client_connect" "$WINDOWS_CONNECT:$PORT"
}

start_headed_client() {
    case "$HEADED_CLIENT_DRIVER" in
    windows) start_windows_client ;;
    proton) start_proton_client ;;
    none)
        ((HEADED_CLIENT == 0)) || fail "infra_unavailable" \
            "headed client requested but this host declares no client driver"
        ;;
    *) fail "infra_unavailable" "unknown headed-client driver: $HEADED_CLIENT_DRIVER" ;;
    esac
}

# ---------------------------------------------------------------- preconditions
# The slot and the host this run is on, written down before the first thing that
# can refuse. ADR-0028's rule is that a slot boundary is only real where
# something reads it, and the corollary is that a reader of the evidence should
# be able to see which side of it a run was on — including a run that got no
# further than the guard, because "which machine refused?" is the first question
# asked of an `infra_unavailable` and it used to be the one the record could not
# answer (#51).
record "tier_slot" "${CTI_TIER_SLOT:-0}"

# What every deadline in this file is made of, checked before the first one is
# set (#144). The old arithmetic's failure mode was that a missing dependency
# made the timeouts silently never fire, so these fail *closed*, here, with the
# class the table gives a run that measured nothing. A harness that cannot bound
# its own waits has not run a probe; it has started one.
now >/dev/null 2>&1 ||
    fail "infra_unavailable" "no usable clock: neither bash's EPOCHREALTIME nor date +%s%3N returned a number"
command -v timeout >/dev/null 2>&1 ||
    fail "infra_unavailable" "timeout(1) is missing, so every external call this run makes would be unbounded"
[[ "$UV_TIMEOUT" =~ ^[1-9][0-9]*$ ]] ||
    fail "infra_unavailable" "CTI_UV_TIMEOUT must be a positive whole number of seconds, got: $UV_TIMEOUT"
# A queue's budget, checked with the deadlines because it is one. Left unchecked,
# a malformed wait is refused by `cti_client_lock_acquire` with the status it
# gives a busy lock, and this run would report somebody else holding a client
# nobody holds (#196).
[[ "$CLIENT_LOCK_WAIT" =~ ^[0-9]+$ ]] ||
    fail "infra_unavailable" "CTI_CLIENT_LOCK_WAIT must be a whole number of seconds, got: $CLIENT_LOCK_WAIT"

HOST="$(cti_host_resolve)" ||
    fail "infra_unavailable" "CTI_TIER_HOST names a host the tier does not know: ${CTI_TIER_HOST:-local}"
record "tier_host" "$HOST"

# Asked before anything is launched, on every path into this script: an
# arma3_x64.exe already up is the human's, the teardown above cannot tell theirs
# from ours, and the answer is stop rather than kill (#41).
#
# It used to be asked only by a run that meant to *drive* the Windows host
# (CTI_WINDOWS_CLIENT=1) — the loading-the-host case went unguarded, so `just
# probe` and `just spike` brought a daemon, a dedicated server and a staged world
# up on the shared machine without ever asking whether a play session was live
# (#68). The guard belongs where the launching happens, which is here.
#
# regress.sh asks the same question again before it queues, on purpose: that copy
# is the cheap refusal that costs a caller no place in the lock queue.
# Before the guard, not after, when this run means to drive the headed client
# (#127). There is one client on one Windows host, and the pool's serial tail
# only orders the probes *inside* one run — two agents gating at once each drove
# it and each read the other's client as a play session. The lock is machine-
# scoped, so the second taker either queues for a bounded time or is told whose
# run it is behind; and because a holder does not let go until its own client has
# left the process list, a client still visible once we hold the lock is the
# human's and the guard below is right to refuse for it.
#
# CTI_CLIENT_LOCK_HELD is the pool's tail saying it already holds it: flock from
# a child on a file its parent holds would wait for a lock that cannot be freed
# until the child returns.
#
# The one deadline this run's patience is spent from, set before the first thing
# that can spend it. Both queue points below read what is left of it rather than
# the budget itself, so a caller who said `--wait 60` waits at most 60s for the
# machine however many ways this run can meet it (#196).
CLIENT_DEADLINE=$((SECONDS + CLIENT_LOCK_WAIT))
client_wait_left() {
    local left=$((CLIENT_DEADLINE - SECONDS))
    ((left > 0)) || left=0
    printf '%s\n' "$left"
}
if ((HEADED_CLIENT == 1)) && [[ "${CTI_CLIENT_LOCK_HELD:-0}" != 1 ]]; then
    if cti_client_lock_acquire "$(client_wait_left)" "run.sh ${CTI_HARNESS_EXTRA:-hold} on $HOST"; then
        record "windows_client_lock" "held"
    else
        log "the machine-wide Windows client lock is held; holder:"
        cti_client_lock_holder | sed 's/^/[spike]   /' >&2
        waited=""
        ((CLIENT_LOCK_WAIT > 0)) && waited=" after waiting ${CLIENT_LOCK_WAIT}s"
        # The holder's own words rather than a path to them (#153). The `.info`
        # file is deleted the moment the holder releases, so a durable record
        # pointing at it names a path that stops existing minutes later — #147's
        # finding, which was fixed in regress.sh and left standing here. And it
        # carries the holder's age, which is what separates a run doing its work
        # from one that is wedged and needs a person.
        fail "infra_unavailable" \
            "another run holds the Windows client${waited}; holder: $(cti_client_lock_summary)"
    fi
fi

# The answer mapped onto this run's verdict in the ladder's one home (#161,
# ADR-0049), env rendering: on a stop, the mapped failure_detail is what `fail`
# records. The wrapper fails closed, so a mapper that could not run stops this
# run exactly as a process list that could not be read does.
#
# And with the queue the entry-time guard has had since #127 (#196). This ask is
# the one a pool meets twenty times, and a stop here is not one probe's — the
# pool reads `infra_unavailable` as "stop taking new work", so the first probe to
# meet a sibling agent's client threw away every probe the pool had left. What is
# queueable here is exactly what is queueable there: a client in the list while
# somebody else holds the machine-wide lock is that run's, not a person's. The
# guard is told none of this and refuses as it always did; the patience is the
# caller's, out of the deadline set above, and at the default of zero this line
# behaves exactly as the single ask it replaces.
if ! guard_env="$(cti_host_guard_or_queue "$HOST" env "$(client_wait_left)" log)"; then
    guard_detail="$(sed -n 's/^failure_detail=//p' <<<"$guard_env" | head -1)"
    fail "infra_unavailable" "${guard_detail:-the host guard refused and named no detail (harness bug)}"
fi
record "windows_host_free" "true"

[[ -x "$SERVER_BIN" ]] || fail "infra_unavailable" "server binary missing at $SERVER_BIN"

# Mirrored WSL2 networking is a precondition only when this run crosses the
# Windows boundary: a Windows HC, a driven Windows client, or a human joining a
# hand-held world. Server-only and Linux-HC regression runs use loopback and do
# not acquire a dependency they never exercise. LAN selection is decided beside
# it from every RFC1918 range, replacing the silent 192.168-only assumption.
NETWORKING_MODE="$(wslinfo --networking-mode 2>/dev/null)" || NETWORKING_MODE="unknown"
[[ -n "$NETWORKING_MODE" ]] || NETWORKING_MODE="unknown"
NEEDS_WINDOWS_BOUNDARY=0
if ((WINDOWS_HC == 1)) ||
    [[ "$HEADED_CLIENT" == "1" && "$HEADED_CLIENT_DRIVER" == "windows" ]] ||
    ((HOLD == 1 && NO_CLIENT_WAIT == 0)); then
    NEEDS_WINDOWS_BOUNDARY=1
fi
address_inspection="readable"
if ! global_addresses="$(global_ipv4s)"; then
    global_addresses=""
    address_inspection="failed"
fi
preflight_args=(--networking-mode "$NETWORKING_MODE" --address-inspection "$address_inspection")
((NEEDS_WINDOWS_BOUNDARY == 1)) && preflight_args+=(--needs-windows-boundary)
while IFS= read -r address; do
    [[ -n "$address" ]] && preflight_args+=(--address "$address")
done <<<"$global_addresses"
preflight_env="$(cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python \
    tools/harness_preflight.py "${preflight_args[@]}")"
preflight_status=$?
if ((preflight_status == 124)); then
    fail "infra_unavailable" \
        "the harness environment pre-flight did not finish within ${UV_TIMEOUT}s (uv run tools/harness_preflight.py)"
elif ((preflight_status != 0 && preflight_status != CTI_EXIT_INFRA_UNAVAILABLE)); then
    fail "untyped_harness_failure" \
        "the harness environment pre-flight failed (exit $preflight_status) — harness bug"
fi
LAN_IP="$(sed -n 's/^lan_ip=//p' <<<"$preflight_env" | head -1)"
lan_status="$(sed -n 's/^lan_status=//p' <<<"$preflight_env" | head -1)"
record "wsl_networking_mode" "$NETWORKING_MODE"
record "wsl_lan_ip" "$LAN_IP"
record "wsl_lan_ip_status" "${lan_status:-unavailable: pre-flight returned no LAN status}"
if ((preflight_status == CTI_EXIT_INFRA_UNAVAILABLE)); then
    preflight_detail="$(sed -n 's/^failure_detail=//p' <<<"$preflight_env" | head -1)"
    fail "infra_unavailable" \
        "${preflight_detail:-the harness environment pre-flight refused without detail}"
fi

# Acquisition already reclaims a dead holder through this same shared resource
# observation (`cti_slot_reclaim`, ADR-0022/ADR-0028). Ask once more at the
# launch boundary: a process can appear after acquisition, and `run.sh` is also
# directly invokable. A port or install holder here means no world has run; it
# is infrastructure, named now rather than misreported two minutes later as a
# server-boot timeout. Detection never kills: only a slot holder may reclaim,
# and the acquisition layer is where that authority lives.
if ! resource_port_rows="$(cti_resource_port_rows "$PORT" "$CTI_SLOT_PORT_SPAN" "$DAEMON_PORT")"; then
    fail "infra_unavailable" \
        "could not inspect server ports $PORT-$((PORT + CTI_SLOT_PORT_SPAN - 1)) and daemon port $DAEMON_PORT"
fi
resource_port_pids="$(grep -oE 'pid=[0-9]+' <<<"$resource_port_rows" | cut -d= -f2 | sort -u || true)"
if ! resource_install_pids="$(cti_resource_install_pids "$SERVER_DIR")"; then
    fail "infra_unavailable" "could not inspect processes running from server install $SERVER_DIR"
fi
mapfile -t resource_pids < <(
    printf '%s\n%s\n' "$resource_port_pids" "$resource_install_pids" |
        grep -E '^[0-9]+$' | sort -u
)
if [[ -n "$resource_port_rows" ]] || ((${#resource_pids[@]} > 0)); then
    resource_squatters="unidentified process (ss exposed no PID)"
    ((${#resource_pids[@]} > 0)) &&
        resource_squatters="$(cti_resource_pid_summary "${resource_pids[@]}")"
    fail "infra_unavailable" \
        "resource squatter(s) on server ports $PORT-$((PORT + CTI_SLOT_PORT_SPAN - 1)), daemon port $DAEMON_PORT, or install $SERVER_DIR: $resource_squatters"
fi

# Overridable for the same reason CTI_SERVER_DIR is: it lets the no-Arma tier
# drive this script's own verdict path against a stub server, which is where the
# classification of an in-mission FAIL is asserted (tests/unit/test_run_verdict.py).
SO="${CTI_SHIM_SO:-$REPO/extension/target/release/libcti_shim.so}"
[[ -f "$SO" ]] || fail "infra_unavailable" "shim not built: $SO (run: cargo build --release --manifest-path extension/Cargo.toml)"
# HEMTT's build output is already a mod folder (<dir>/addons/*.pbo). Every
# machine that runs mission scripts needs it loaded: CfgFunctions compiles per
# machine, so an unloaded addon means no cti_fnc_*.
BUILT_MOD="${CTI_BUILT_MOD:-$REPO/.hemttout/build}"
[[ -d "$BUILT_MOD/addons" ]] || fail "infra_unavailable" "addon not built: $BUILT_MOD/addons (run: just build-addon)"
# -mod= resolves against the game directory, not the working directory: an
# absolute path outside it lands in the mod table as "GAME DIR (Empty)" and
# silently loads nothing. Stage it inside the server instead.
MOD_NAME="@cti"

record "mission" "$MISSION"
# The rest of the slot boundary, beside the two rows recorded above the guard.
# #44's merged runs were only diagnosable because somebody went looking for the
# daemon address by hand.
record "server_port" "$PORT"
record "daemon_port" "$DAEMON_PORT"
record "daemon_addr" "$CTI_DAEMON_ADDR"
record "server_dir" "$SERVER_DIR"
record "server_profile" "$SERVER_NAME"

# ---------------------------------------------------------------- staging
stage_mission

# ---------------------------------------------------------------- daemon
DAEMON_LOG="$OUT/daemon.log"
DAEMON_TELEMETRY="$OUT/daemon-telemetry.jsonl"
: >"$DAEMON_LOG"
# Truncate: telemetry is per-run evidence, and appending across runs turns it
# into a pile nobody can attribute.
: >"$DAEMON_TELEMETRY"
t_daemon=$(now)
# Loopback, in every mode (ADR-0044). Hold mode used to bind every interface, on
# the Phase-0 reasoning that the Windows host had to reach the daemon: that was
# `missions/spike.Stratis`, whose clients call the shim themselves through
# CTI_SPIKE_DAEMON_ADDRS. The shipped mission has no such caller — ADR-0018 is
# that a client never speaks to the daemon — and `just probe` runs the shipped
# mission, so the widening outlived its reason and left the socket on the LAN
# for exactly the sessions a human joins. The daemon refuses a non-loopback bind
# now, so this line and that refusal have to agree.
DAEMON_HOST=127.0.0.1
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
# A function rather than a straight line, because CTI_DAEMON_RESTART_ON needs to
# do this a second time mid-run (#96). Appends to the same log and the same
# telemetry file: what a restart costs is a thing to read afterwards, and
# truncating either would take the first daemon's half of the evidence with it.
# The epoch is read back off the readiness line so the run records which process
# answered which half.
daemon_starts=0
# Why the wait ended, when the words the caller has ready would be the wrong
# ones. Both callers type every failure infra_unavailable, but "the daemon never
# said it was ready" and "the harness could not read its own log" send a reader
# somewhere different, and only this function knows which happened (#192).
daemon_wait_detail=""
start_daemon() {
    daemon_starts=$((daemon_starts + 1))
    daemon_wait_detail=""
    (
        cti_client_lock_disown
        cd "$REPO" && exec uv run --quiet cti-daemon \
        --host "$DAEMON_HOST" --port "$DAEMON_PORT" --telemetry "$DAEMON_TELEMETRY" \
        "${AI_ARGS[@]}") \
        >>"$DAEMON_LOG" 2>&1 &
    daemon_pid=$!
    # Counted rather than pattern-matched: the first daemon's readiness line is
    # still in the log, so `wait_for` would find it and call a second daemon
    # ready before it had bound anything.
    # Ninety seconds, in integer milliseconds off the same clock `wait_for` uses.
    # Any failure to compute or hold the deadline returns non-zero, and every
    # caller of this function types that infra_unavailable (#144). The ladder: 1
    # is the deadline or the clock, 2 is the daemon dying first, 3 is the log
    # this loop reads being unreadable — all three the same class, and only the
    # third needs words the caller does not already have.
    local deadline start t seen status
    start="$(now)" || return 1
    deadline=$((start + 90000))
    while :; do
        # The count lands in a variable before anything reads it. `grep -c`
        # prints its count *and* exits 1 when it matches nothing, so the
        # `$(grep -c … || echo 0)` this replaces put a second line after a
        # substitution that already held one, and handed bash's arithmetic
        # `0\n0` — an untyped syntax error on stderr for every turn of this loop
        # before the daemon was up, which is the failure-class table's own
        # definition of a harness bug (#192).
        seen="$(grep -c CTI_DAEMON_READY "$DAEMON_LOG" 2>/dev/null)"
        status=$?
        # Status 1 is "matched nothing", which is a real count of zero. Above it
        # is grep failing to read the file at all — and a count that came back
        # non-numeric is the same thing said differently, since which of the two
        # a given grep chooses for an unreadable path varies. Neither is a zero,
        # and the discarded `|| echo 0` made both into one: #41's shape, a check
        # that could not run reported as a check that passed. Left that way, an
        # unreadable log spun this loop out to its 90 s deadline and was then
        # reported as a daemon that never said it was ready.
        if ((status > 1)) || [[ ! "$seen" =~ ^[0-9]+$ ]]; then
            daemon_wait_detail="the harness could not read its own daemon log"
            return 3
        fi
        ((seen >= daemon_starts)) && return 0
        kill -0 "$daemon_pid" 2>/dev/null || return 2
        t="$(now)" || return 1
        ((t > deadline)) && return 1
        sleep 0.25
    done
}

if ! start_daemon; then
    fail "infra_unavailable" "${daemon_wait_detail:-daemon did not report ready}; see $DAEMON_LOG"
fi
record "daemon_ready_secs" "$(since "$t_daemon")"
record "daemon_epoch" "$(sed -n 's/.*CTI_DAEMON_READY .* epoch=//p' "$DAEMON_LOG" | tail -1)"

# ---------------------------------------------------------------- dedicated server
start_server

# ---------------------------------------------------------------- headless client
if ((SKIP_HC == 0)); then
    start_hc
else
    record "hc_joined" "skipped"
fi

# ---------------------------------------------------------------- windows client
start_windows_hc

# ---------------------------------------------------------------- headed client
start_headed_client

# ---------------------------------------------------------------- human client
if ((HOLD == 1)); then
    # Skipped under --regress: a regression run sends no client, so the banner is
    # noise and the wait is the whole window burned before the probe wait starts.
    if ((NO_CLIENT_WAIT == 0)); then
        lan_ip="$(lan_ip)"
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
        # The one wait_for site not folded into await_or_fail (#161): a human
        # who never joined is a recorded fact about a hold run, not a failure,
        # so its first rung records where every other site's fails.
        #
        # `[^_]` keeps the wait honest: the dedicated server's own player entry
        # fires onPlayerConnected as `__SERVER__` the moment the mission
        # starts, and without it this matched the server greeting itself. The
        # optional `""` accepts a client that connects before the engine has
        # resolved its name.
        case "$(
            wait_for "$SERVER_LOG" "$LOG_PREFIX\|player_connected name=(\"\")?[^_]" "$HOLD_TIMEOUT" "$server_pid"
            echo $?
        )" in
        1)
            record "windows_client_joined" "false"
            record "windows_client_failure" "no client connected within ${HOLD_TIMEOUT}s"
            ;;
        2) fail "node_crashed" "server exited while waiting for a client; see $SERVER_LOG" ;;
        3) fail "infra_unavailable" "CTI_HOLD_TIMEOUT is not a whole number of seconds: $HOLD_TIMEOUT" ;;
        *)
            record "windows_client_connected_secs" "$(since "$t_client")"
            # Entering the mission is the thing in doubt, not connecting: the
            # client report only fires once init.sqf has actually run on that
            # machine.
            #
            # Two lines, because there are two missions. `client_report` is
            # spike.Stratis's, and the Phase-1 mission does not have one — so a
            # client that joined cti.Stratis, took a Commander slot and played
            # was recorded as "connected-but-never-entered-mission" after burning
            # 180 s waiting for a line that mission cannot write.
            # `commander_assigned` is the Phase-1 equivalent and says strictly
            # more: the sweep only sees a player whose unit occupies the slot and
            # carries a UID, which is a person in the mission rather than merely
            # on the socket.
            if wait_for "$SERVER_LOG" \
                "$LOG_PREFIX\|(client_report|commander_assigned)" 180 "$server_pid"; then
                record "windows_client_joined" "true"
                record "windows_client_in_mission_secs" "$(since "$t_client")"
            else
                record "windows_client_joined" "connected-but-never-entered-mission"
            fi
            ;;
        esac
    fi

    # Fault injection: kill the daemon and start a fresh one, mid-run (#96). The
    # daemon holds the whole Campaign in memory, so the new process is a
    # factory-fresh one, and the world's job is to notice rather than to play on
    # against a stranger's Campaign.
    #
    # Triggered on a line the probe writes rather than on a clock: the probe
    # decides when it has a baseline worth losing, and a restart timed by a sleep
    # would be a restart that sometimes lands before the world has read anything.
    if [[ -n "${CTI_DAEMON_RESTART_ON:-}" ]]; then
        await_or_fail "$SERVER_LOG" "$LOG_PREFIX\|($CTI_DAEMON_RESTART_ON|FAIL)" \
            "${CTI_PROBE_TIMEOUT:-$HOLD_TIMEOUT}" "$server_pid" \
            "probe never logged $CTI_DAEMON_RESTART_ON; see $SERVER_LOG" \
            "server exited before the daemon restart; see $SERVER_LOG" \
            "no deadline could be set for the daemon-restart trigger wait"
        t_restart=$(now)
        kill "$daemon_pid" 2>/dev/null || true
        wait "$daemon_pid" 2>/dev/null || true
        if ! start_daemon; then
            fail "infra_unavailable" \
                "${daemon_wait_detail:-daemon did not come back up}; see $DAEMON_LOG"
        fi
        record "daemon_restart_secs" "$(since "$t_restart")"
        record "daemon_epoch_after_restart" \
            "$(sed -n 's/.*CTI_DAEMON_READY .* epoch=//p' "$DAEMON_LOG" | tail -1)"
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
        # FAIL ends the wait too: a probe that gave up short-circuits rather
        # than running out the clock, so the sweep below classifies it instead
        # of this timing out and calling an assertion a timeout.
        await_or_fail "$SERVER_LOG" "$LOG_PREFIX\|(.*$CTI_HARNESS_AWAIT|FAIL)" \
            "$PROBE_TIMEOUT" "$server_pid" \
            "probe never logged $CTI_HARNESS_AWAIT; see $SERVER_LOG" \
            "server exited while the probe ran; see $SERVER_LOG" \
            "the probe window is not a whole number of seconds: $PROBE_TIMEOUT"
    fi

    # Fetched while the client is still up, because teardown ends it: the
    # engine writes a client's own refusals to the client's RPT on the Windows
    # host and nothing crosses to this side unless it is copied. A remoteExec
    # the whitelist blocks is observed here or not at all (#21).
    [[ -n "$win_client_pid" ]] && collect_client_rpt

    extract_spike_lines
    log "--- in-mission results ---"
    cat "$OUT/spike-lines.txt" >&2
    # Hold mode used to exit here, before the assertion check below — so a run
    # in which an in-mission assertion fired still reported HOLD-COMPLETE. An
    # untyped green is worse than an untyped red: it is a pass nobody earned.
    # The push-path budget, off the run's own telemetry (#17). Recorded whatever
    # the verdict, and before it: a run that failed is exactly when the numbers
    # are worth having.
    #
    # Run into a file rather than through `< <(...)`: pipefail does not cover a
    # process substitution, so a report that died recorded nothing at all and
    # read back as a run with no push path rather than as a report that failed
    # (#83).
    PUSH_REPORT="$OUT/push-path.env"
    PUSH_REPORT_ERR="$OUT/push-path.err"
    (cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python tools/push_path_report.py \
        "$DAEMON_TELEMETRY") >"$PUSH_REPORT" 2>"$PUSH_REPORT_ERR"
    push_status=$?
    if ((push_status == 0)); then
        while read -r line; do record "${line%%=*}" "${line#*=}"; done <"$PUSH_REPORT"
    elif ((push_status == 124)); then
        record "push_path_report" \
            "unavailable: push_path_report.py did not finish within ${UV_TIMEOUT}s"
    else
        record "push_path_report" \
            "unavailable: push_path_report.py failed: $(tail -3 "$PUSH_REPORT_ERR" | tr '\n' ' ')"
    fi

    # The run read back as a sequence, always: it costs nothing and it is the
    # artefact #35's timeout went without — a Squad at three of eight and no
    # account of the other five (#39).
    (cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python tools/timeline.py \
        "$DAEMON_TELEMETRY") >"$OUT/timeline.txt" 2>"$OUT/timeline-error.txt"
    timeline_status=$?
    if ((timeline_status == 0)); then
        record "timeline" "$OUT/timeline.txt"
    elif ((timeline_status == 124)); then
        record "timeline" "unavailable: timeline.py did not finish within ${UV_TIMEOUT}s"
    else
        timeline_detail="$(tail -3 "$OUT/timeline-error.txt" | tr '\n' ' ')"
        record "timeline" "unavailable: timeline.py failed: ${timeline_detail% }"
    fi

    assert_clean_run "$OUT/spike-lines.txt"

    # A probe that says it staged deaths is checked against the daemon's own
    # file rather than against its own memory of doing so. This is the crossing:
    # the world claims, the record answers, and neither is asked to vouch for
    # itself. Silent for every probe that stages nothing.
    if grep -q 'casualty_staged' "$OUT/spike-lines.txt"; then
        (cd "$REPO" && timeout "$UV_TIMEOUT" uv run --quiet python tools/timeline.py \
            "$DAEMON_TELEMETRY" --expect "$OUT/spike-lines.txt") \
            >"$OUT/timeline.txt" 2>"$OUT/timeline-unmatched.txt"
        expect_status=$?
        # The cross-check not *finishing* is not the cross-check disagreeing. A
        # deadline here typed assertion_failed would send the reader to fix world
        # code over a tool that never ran (#144, and the table's own rule).
        if ((expect_status == 124)); then
            fail "infra_unavailable" \
                "the telemetry cross-check did not finish within ${UV_TIMEOUT}s (uv run tools/timeline.py --expect)"
        elif ((expect_status != 0)); then
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
await_or_fail "$SERVER_LOG" "$LOG_PREFIX\|done" "$HARNESS_TIMEOUT" "$server_pid" \
    "in-mission harness never logged done; see $SERVER_LOG" \
    "server exited during the harness; see $SERVER_LOG" \
    "CTI_HARNESS_TIMEOUT is not a whole number of seconds: $HARNESS_TIMEOUT"

extract_spike_lines
log "--- in-mission results ---"
cat "$OUT/spike-lines.txt" >&2

assert_clean_run "$OUT/spike-lines.txt"

record "server_peak_rss_kb" "$(awk '/VmHWM/{print $2}' "/proc/$server_pid/status" 2>/dev/null || echo unknown)"
if [[ -n "$hc_pid" ]]; then
    record "hc_peak_rss_kb" "$(awk '/VmHWM/{print $2}' "/proc/$hc_pid/status" 2>/dev/null || echo unknown)"
fi
record "verdict" "PASS"
log "results: $RESULTS"
