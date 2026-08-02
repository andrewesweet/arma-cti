#!/usr/bin/env bash
# The Arma tier's slot geometry, allocation and stale-state reclamation
# (ADR-0028, issue #47). Sourced, never executed.
#
# A slot is a port block, a daemon, a server install, an engine profile and a
# world that agree. ADR-0028's rule for everything in here is one line:
# **a slot boundary is only real where something reads it** — #44's first
# two-slot run had isolated ports, dirs, installs and daemons and the two worlds
# still merged, because the shim resolved its daemon from a `CTI_DAEMON_ADDR`
# nobody set. So every value this file derives names its consumer in a comment,
# and a value with no consumer is decoration whose failure mode is a green run.
#
#   cti_slot_port N            game port; the engine also binds +1 and +2
#   cti_slot_daemon_port N     the daemon this slot's world talks to
#   cti_slot_install N         the server install this slot stages into
#   cti_slot_profile N         the engine profile name (-name=), and with it the RPT
#   cti_slot_env N             the whole per-slot environment, as NAME=VALUE lines
#   cti_slot_acquire N         non-blocking flock; 0 held, 1 taken by someone else
#   cti_slot_release N         drop it (the kernel does this anyway on death)
#   cti_slot_holder N          what the holder wrote beside the lock
#   cti_slot_reclaim N         ADR-0022 per slot: clear a dead holder's leftovers
#   cti_slot_install_ready N   the cp -al hard-link farm, made and kept honest
#
# Slot 0 is the single-occupancy tier as it has always been: ports 2402-2406,
# the install at ~/arma3server, and the lock `just probe` and `just spike` take.
# That is what makes a pool run and a hand run exclude each other rather than
# racing on one install — and what makes `just regress --slots 1` the serial
# tier, byte for byte.

CTI_SLOT_STATE="${CTI_TIER_STATE:-$HOME/.arma-cti}"
CTI_SLOT_LOCK_DIR="$CTI_SLOT_STATE/slots"

# CLAUDE.md's Contract grants [2400, 3000) and reserves 2302-2306 for the human.
# The stride is BI's own: `topics/Arma_3_Server_Config_File.wiki` asks for at
# least 100 ports between consecutive server port sets, and the engine derives
# the Steam query (+1) and Steam master (+2) ports from the game port with no
# config override to pack them (ADR-0028).
CTI_SLOT_PORT_BASE=2402
CTI_SLOT_PORT_STRIDE=100
CTI_SLOT_PORT_SPAN=5 # 3 bound today; 5 reserved for BattlEye and VoN
CTI_SLOT_DAEMON_BASE=9099
# 2402 + 100*5 = 2902, whose +4 is 2906, still inside the grant. A slot index
# past this is a bug rather than a configuration, and is refused as one.
CTI_SLOT_MAX=5

CTI_SLOT_GRANT_LOW=2400
CTI_SLOT_GRANT_HIGH=3000 # exclusive
CTI_SLOT_HUMAN_LOW=2302
CTI_SLOT_HUMAN_HIGH=2306

# The exit code every part of this tier uses for "not a result".
CTI_SLOT_EXIT_INFRA=5

cti_slot_log() { printf '[slots] %s\n' "$*" >&2; }

# Refuse an index whose port block would leave the grant or touch the human's
# range. Both are unreachable from the arithmetic above; they are asserted
# because the arithmetic is the kind that gets edited.
cti_slot_valid() {
    local n="$1" low high
    [[ "$n" =~ ^[0-9]+$ ]] || {
        cti_slot_log "slot index must be a whole number, got: $n"
        return 1
    }
    ((n <= CTI_SLOT_MAX)) || {
        cti_slot_log "slot $n is past the last index the port grant fits ($CTI_SLOT_MAX)"
        return 1
    }
    low=$((CTI_SLOT_PORT_BASE + CTI_SLOT_PORT_STRIDE * n))
    high=$((low + CTI_SLOT_PORT_SPAN - 1))
    ((low >= CTI_SLOT_GRANT_LOW && high < CTI_SLOT_GRANT_HIGH)) || {
        cti_slot_log "slot $n would bind $low-$high, outside the granted [$CTI_SLOT_GRANT_LOW, $CTI_SLOT_GRANT_HIGH)"
        return 1
    }
    ((high < CTI_SLOT_HUMAN_LOW || low > CTI_SLOT_HUMAN_HIGH)) || {
        cti_slot_log "slot $n would bind $low-$high, which reaches the human's $CTI_SLOT_HUMAN_LOW-$CTI_SLOT_HUMAN_HIGH"
        return 1
    }
    return 0
}

# Consumer: `run.sh`'s CTI_SERVER_PORT, and with it -port= on both the server and
# the headless client, and the Windows client's -connect port.
cti_slot_port() { echo $((CTI_SLOT_PORT_BASE + CTI_SLOT_PORT_STRIDE * $1)); }

# Consumer: `cti-daemon --port`, and CTI_DAEMON_ADDR below.
cti_slot_daemon_port() { echo $((CTI_SLOT_DAEMON_BASE + $1)); }

# Consumer: `run.sh`'s CTI_SERVER_DIR — the directory it stages the mission PBO,
# `@cti` and the shim into with `rm -rf`, which is why two slots cannot share one.
cti_slot_install() {
    local n="$1"
    if ((n == 0)); then
        echo "${CTI_SLOT_INSTALL_MASTER:-$HOME/arma3server}"
    else
        echo "${CTI_SLOT_INSTALL_MASTER:-$HOME/arma3server}-slot$n"
    fi
}

# Consumer: `run.sh`'s CTI_SERVER_NAME → the engine's `-name=`. `-profiles=` is
# broken on Linux, so `-name=` is the only lever on where the engine writes its
# profile — and the profile directory is where `logFile` and the `.rpt` land.
# Every slot ran as `ctispike` during #44's exploration, which #58 called a
# bulkhead with a shared wall: one slot's crash corrupting state another reads.
cti_slot_profile() { echo "ctispike$1"; }
cti_slot_hc_profile() { echo "ctihc$1"; }

cti_slot_lock_path() { echo "$CTI_SLOT_LOCK_DIR/$1.lock"; }

# The whole per-slot environment in one place, as NAME=VALUE lines. This is the
# list ADR-0028's "what a slot owns" table names, and every line in it has a
# consumer named above.
cti_slot_env() {
    local n="$1"
    printf 'CTI_SERVER_PORT=%s\n' "$(cti_slot_port "$n")"
    printf 'CTI_DAEMON_PORT=%s\n' "$(cti_slot_daemon_port "$n")"
    # The one #44 proved inert without: CTI_DAEMON_PORT moves the daemon, this
    # moves the world with it. `run.sh` derives the same value when it is unset,
    # so this is belt and braces rather than the mechanism — but the mechanism
    # being invisible is exactly how it went missing the first time.
    printf 'CTI_DAEMON_ADDR=127.0.0.1:%s\n' "$(cti_slot_daemon_port "$n")"
    printf 'CTI_SERVER_DIR=%s\n' "$(cti_slot_install "$n")"
    printf 'CTI_SERVER_NAME=%s\n' "$(cti_slot_profile "$n")"
    printf 'CTI_HC_NAME=%s\n' "$(cti_slot_hc_profile "$n")"
    printf 'CTI_TIER_SLOT=%s\n' "$n"
}

# ------------------------------------------------------------------ allocation
# One flock(2) per slot, non-blocking, exactly as ADR-0016's single lock but N
# times. flock rather than a pidfile for the property that makes "which slot is
# free?" answerable without a reaper: the kernel releases a dead holder's lock.
# Proven in anger on 2026-08-01, when a session limit killed an agent mid-run.
#
# The file descriptor is held by *this* shell and inherited by every child, so a
# worker running in a slot keeps it held for as long as the pool lives.
declare -A CTI_SLOT_FD=()

cti_slot_acquire() {
    local n="$1" label="${2:-}" lock fd
    cti_slot_valid "$n" || return 2
    mkdir -p "$CTI_SLOT_LOCK_DIR" || return 2
    lock="$(cti_slot_lock_path "$n")"
    exec {fd}>"$lock" || return 2
    if ! flock -x -n "$fd" 2>/dev/null; then
        exec {fd}>&-
        return 1
    fi
    CTI_SLOT_FD[$n]=$fd
    # Holder metadata, per slot, exactly as tier.lock.info is written today.
    # Truncated rather than created: a holder killed with -9 leaves its metadata
    # behind and the kernel has already handed us the lock over the top of it.
    {
        printf 'pid=%s\n' "$$"
        printf 'slot=%s\n' "$n"
        printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'worktree=%s\n' "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
        printf 'branch=%s\n' "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
        printf 'issue=%s\n' "${CTI_TIER_ISSUE:-unstated}"
        printf 'label=%s\n' "${label:-unstated}"
    } >"$lock.info"
    return 0
}

cti_slot_release() {
    local n="$1"
    [[ -n "${CTI_SLOT_FD[$1]:-}" ]] || return 0
    rm -f "$(cti_slot_lock_path "$n").info"
    cti_slot_close "$n"
}

# Drop this shell's handle on a slot without touching its metadata. A worker
# inherits every slot's descriptor from the pool that forked it, and an inherited
# descriptor is a shared wall: `flock` frees a lock only when the last descriptor
# on it closes, so a worker holding its siblings' locks would keep a dead slot's
# lock alive and make "who is still in slot 2?" unanswerable. Each worker closes
# every slot but its own.
cti_slot_close() {
    local n="$1" fd="${CTI_SLOT_FD[$1]:-}"
    [[ -n "$fd" ]] || return 0
    exec {fd}>&-
    unset "CTI_SLOT_FD[$n]"
}

# Who else still has this slot's lock open. Only meaningful once *we* have let go
# of it: a slot we hold exclusively has no other holder by definition, and the
# case this exists for is the other one — a worker that died leaving `run.sh`,
# a server or a headless client alive with the descriptor it inherited.
cti_slot_lock_holders() {
    local lock pid fd target
    lock="$(cti_slot_lock_path "$1")"
    for pid in /proc/[0-9]*; do
        pid="${pid#/proc/}"
        [[ "$pid" == "$$" ]] && continue
        for fd in "/proc/$pid/fd/"*; do
            target="$(readlink "$fd" 2>/dev/null)" || continue
            [[ "$target" == "$lock" ]] && {
                printf '%s\n' "$pid"
                break
            }
        done
    done
}

cti_slot_holder() {
    local info
    info="$(cti_slot_lock_path "$1").info"
    if [[ -r "$info" ]]; then
        sed 's/^/    /' "$info"
    else
        printf '    no metadata beside the lock (holder died, or predates this file)\n'
    fi
}

# ------------------------------------------------------------------ reclamation
# ADR-0022's rule scoped per slot rather than per run, and #58's "build this
# first, not last": lock release frees the lock, never the dead holder's
# processes. So the *next* holder of a slot clears what the last one left, and it
# does so by the two things that are slot-scoped and observable from outside —
# the ports the slot binds and the install path it stages into.
#
# `$1` is the slot. Anything it kills is logged, because a slot that had to
# reclaim something is evidence that a previous run died, and that belongs in
# this run's record rather than in nobody's.

# Pids holding any of this slot's ports, UDP or TCP.
cti_slot_port_pids() {
    local n="$1" port first last
    first="$(cti_slot_port "$n")"
    last=$((first + CTI_SLOT_PORT_SPAN - 1))
    {
        for ((port = first; port <= last; port++)); do
            ss -lunpH "sport = :$port" 2>/dev/null
            ss -ltnpH "sport = :$port" 2>/dev/null
        done
        ss -lunpH "sport = :$(cti_slot_daemon_port "$n")" 2>/dev/null
        ss -ltnpH "sport = :$(cti_slot_daemon_port "$n")" 2>/dev/null
    } | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
}

# Pids running a binary *out of* this slot's install. Catches a squatting engine
# that has not yet bound, or has already lost, its port — which is the case a
# port sweep alone reads as a clean slot.
#
# Read off `/proc/<pid>/exe` rather than off the command line, because the engine
# is launched as `./arma3server_x64` from inside the install and its argv names
# the install nowhere. A command-line match would have found nothing and reported
# a squatted slot as clean, which is the failure mode this whole file is about.
cti_slot_install_pids() {
    local install pid exe
    install="$(cti_slot_install "$1")/"
    for pid in /proc/[0-9]*; do
        pid="${pid#/proc/}"
        [[ "$pid" == "$$" ]] && continue
        exe="$(readlink "/proc/$pid/exe" 2>/dev/null)" || continue
        [[ "$exe" == "$install"* ]] && printf '%s\n' "$pid"
    done
}

#
# `$2 == holders` adds the processes still holding the slot's lock, which is only
# askable once this shell has closed its own descriptor — see
# `cti_slot_lock_holders`. On acquire it is neither wanted nor meaningful: a slot
# we just took exclusively has no other holder.
cti_slot_reclaim() {
    local n="$1" pid pids=() marker last_run
    mapfile -t pids < <(
        cti_slot_port_pids "$n"
        cti_slot_install_pids "$n"
        [[ "${2:-}" == holders ]] && cti_slot_lock_holders "$n"
    )
    # Deduplicate; the two sweeps overlap on a live server.
    mapfile -t pids < <(printf '%s\n' "${pids[@]+"${pids[@]}"}" | grep -E '^[0-9]+$' | sort -u)

    # The interrupted-run marker, ADR-0022 per slot: the last evidence directory
    # this slot wrote, and whether it ever got a verdict. Read before killing, so
    # the reason is in the log beside the killing.
    marker="$CTI_SLOT_LOCK_DIR/$n.last"
    if [[ -r "$marker" ]]; then
        last_run="$(cat "$marker")"
        if [[ -n "$last_run" && ! -f "$last_run/verdict.json" ]]; then
            cti_slot_log "slot $n: previous holder was interrupted — $last_run has no verdict.json, so it is not a result (ADR-0022)"
        fi
    fi

    ((${#pids[@]} > 0)) || return 0
    cti_slot_log "slot $n: clearing a previous holder's leftovers: pids ${pids[*]}"
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null; done
    # Bounded, then hard. Not a synchronisation wait on a test — a shutdown
    # deadline on processes we have already decided are stale.
    local deadline=$((SECONDS + 15))
    while ((SECONDS < deadline)); do
        local alive=0
        for pid in "${pids[@]}"; do kill -0 "$pid" 2>/dev/null && alive=1; done
        ((alive == 0)) && break
        sleep 0.5
    done
    for pid in "${pids[@]}"; do kill -9 "$pid" 2>/dev/null; done
    return 0
}

# Record which evidence directory a slot is currently writing, so the next holder
# can apply the rule above. Consumer: cti_slot_reclaim.
cti_slot_mark_run() {
    mkdir -p "$CTI_SLOT_LOCK_DIR"
    printf '%s\n' "$2" >"$CTI_SLOT_LOCK_DIR/$1.last"
}

# ------------------------------------------------------------------ the install
# `run.sh` stages the mission PBO, `@cti` and the shim *into* the install with
# `rm -rf` and `install`, so two slots sharing one install race on the world
# under test. A `cp -al` hard-link farm of the 5.1 GB master costs no disk and
# about a fiftieth of a second (#44) — but the three staged paths must be broken
# out of the farm afterwards, because `install -m 0755` truncates through a hard
# link and would write one slot's shim into the master and every other clone.
cti_slot_install_ready() {
    local n="$1" master dst
    master="$(cti_slot_install 0)"
    dst="$(cti_slot_install "$n")"
    ((n == 0)) && return 0

    [[ -x "$master/arma3server_x64" ]] || {
        cti_slot_log "no master install to clone at $master"
        return 1
    }

    # Rebuild when the master's binary is a different inode from the clone's:
    # a Steam update replaces the file rather than writing through it, so a
    # stale farm would run last month's engine and report it as this month's.
    # That is `engine_drift` waiting to happen, and it is cheap to preclude.
    if [[ -x "$dst/arma3server_x64" ]] &&
        [[ "$(stat -c %i "$master/arma3server_x64")" == "$(stat -c %i "$dst/arma3server_x64")" ]]; then
        return 0
    fi

    cti_slot_log "slot $n: building the install farm at $dst"
    rm -rf "${dst:?}" || return 1
    cp -al "$master" "$dst" || {
        cti_slot_log "slot $n: cp -al of $master failed"
        return 1
    }
    # Out of the farm: everything run.sh writes into the install.
    rm -rf "${dst:?}/mpmissions" "${dst:?}/@cti" || return 1
    rm -f "${dst:?}/cti_shim_x64.so" "${dst:?}/cti_shim.so" || return 1
    mkdir -p "$dst/mpmissions" || return 1
    return 0
}
