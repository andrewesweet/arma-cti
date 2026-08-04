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
#   cti_slot_reclaim N         ADR-0022 per slot: clear a dead holder's leftovers,
#                              and confirm they are gone rather than assume it.
#                              Non-zero, with the survivors on stdout, when they
#                              are not — a caller has to act on that (#133)
#   cti_slot_install_ready N   the cp -al hard-link farm, made and kept honest
#
# Slot 0 is the single-occupancy tier as it has always been: ports 2402-2406,
# the install at ~/arma3server, and the lock `just probe` and `just spike` take.
# That is what makes a pool run and a hand run exclude each other rather than
# racing on one install — and what makes `just regress --slots 1` the serial
# tier, byte for byte.

# Which machine these slots are on (ADR-0032, #51). A pool run executes on one
# host, so the handle is a property of the run rather than of a slot, and it is
# what every operation in here that touches a machine — the port sweeps, the
# kills, the install farm — names instead of naming this one.
# shellcheck source=spike/hosts.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/hosts.sh"

CTI_SLOT_STATE="$(cti_host_state)"
# The same state root with nothing redirecting it, which is what makes
# "is this the machine's own tier?" answerable — see cti_slot_reclaim.
CTI_SLOT_REAL_STATE="$(CTI_TIER_STATE= cti_host_state)"
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
# The path is on the host the run executes on, whichever that is: `$HOME` here
# expands on the machine that owns the install, the same way `~/.arma-cti` does.
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

# ---------------------------------------------------------------------- memory
# How many slots the machine has room for *right now* (#125).
#
# A slot lock answers "is anyone else in slot 2?" and nothing else. It cannot
# answer "is there memory for a third world?", and on 2026-08-02 that gap became
# a red: two pools ran on one 12 GB machine, `20260802T141637Z-pool` on slots
# 0-2 and `20260802T141804Z-pool` on slots 3-5, six worlds between them. Both
# bottomed out at ~39 MiB available, and both watched a 2 s loop go silent for
# four minutes and typed it `node_crashed`. Neither had done anything wrong by
# the locks; the second simply started into a machine that was already full.
#
# So the pool asks the same question the host guard asks about the human, in the
# same fail-closed shape: a reading taken before anything is launched, and a
# refusal that costs the caller nothing because nothing was launched. The
# difference is that a pool has a middle answer — fewer slots — and it takes it,
# out loud, rather than refusing a run the machine could still have carried.
#
# The floor is measurement, not arithmetic. #44 measured a heavy slot (server
# 1.14-1.23 GB + headless client 1.16-1.20 GB + daemon 35 MB) at ~2.43 GB, and
# ADR-0028 warned its N=3 figure was extrapolated from that. Three clean N=3
# pool runs have since measured it: peak tier RSS 7,293 / 7,349 / 7,365 MiB, so
# 2,431-2,455 MiB a slot. The extrapolation held, and 2,500 is it rounded up.
CTI_SLOT_MEM_PER_SLOT_MB="${CTI_SLOT_MEM_PER_SLOT_MB:-2500}"
# What is left over when a healthy pool is at its heaviest. The same three runs
# bottomed out at 1,465 / 1,528 / 1,871 MiB available; 1,024 is under all three,
# so a run that would have been one of them is not refused, and the run that
# reached 39 MiB would have been.
CTI_SLOT_MEM_HEADROOM_MB="${CTI_SLOT_MEM_HEADROOM_MB:-1024}"
# The between-probes re-check, which is a different question: the pool is
# already up, N-1 worlds are already counted, and what is being asked is only
# whether the machine still has margin at all. Half the lowest healthy trough
# above, so it clears a good run by 2x and the starved one by 26x.
CTI_SLOT_MEM_RUNNING_FLOOR_MB="${CTI_SLOT_MEM_RUNNING_FLOOR_MB:-512}"

# MemAvailable on the host the run executes on, in MiB. The kernel's own
# estimate of what a new workload can have without swapping, which is the
# question being asked — MemFree is not, because the page cache is reclaimable
# and a machine with none free may still have room for a world.
#
# `CTI_SLOT_MEM_AVAILABLE_MB` overrides it, for a test that needs to stage a
# machine at a memory it does not have.
cti_slot_mem_available_mb() {
    local kb
    if [[ -n "${CTI_SLOT_MEM_AVAILABLE_MB:-}" ]]; then
        # Validated like the real reading, so a staged machine cannot be given a
        # memory the check would have refused to believe.
        [[ "$CTI_SLOT_MEM_AVAILABLE_MB" =~ ^[0-9]+$ ]] || {
            cti_slot_log "CTI_SLOT_MEM_AVAILABLE_MB is not a number of MiB: $CTI_SLOT_MEM_AVAILABLE_MB"
            return 1
        }
        printf '%s\n' "$CTI_SLOT_MEM_AVAILABLE_MB"
        return 0
    fi
    kb="$(cti_host_exec "$CTI_TIER_HOST" awk '/^MemAvailable:/ { print $2; exit }' /proc/meminfo 2>/dev/null)"
    [[ "$kb" =~ ^[0-9]+$ ]] || {
        # A reading that could not be taken is not a reading that passed — the
        # host guard's rule, and the same class comes out the other end.
        cti_slot_log "could not read MemAvailable on $CTI_TIER_HOST"
        return 1
    }
    printf '%s\n' $((kb / 1024))
}

# What N slots need, in MiB.
cti_slot_mem_floor_mb() {
    printf '%s\n' $(($1 * CTI_SLOT_MEM_PER_SLOT_MB + CTI_SLOT_MEM_HEADROOM_MB))
}

# The largest slot count at or below `$1` that fits in `$2` MiB. `0` means not
# even one slot fits, which is the refusal.
cti_slot_mem_fit() {
    local want="$1" avail="$2" n
    for ((n = want; n >= 1; n--)); do
        ((avail >= $(cti_slot_mem_floor_mb "$n"))) && {
            printf '%s\n' "$n"
            return 0
        }
    done
    printf '0\n'
}

# ------------------------------------------------------------------ allocation
# One flock(2) per slot, non-blocking, exactly as ADR-0016's single lock but N
# times. flock rather than a pidfile for the property that makes "which slot is
# free?" answerable without a reaper: the kernel releases a dead holder's lock.
# Proven in anger on 2026-08-01, when a session limit killed an agent mid-run.
#
# The file descriptor is held by *this* shell and inherited by every child, so a
# worker running in a slot keeps it held for as long as the pool lives.
#
# The kernel's release is prompt but it is not simultaneous with the holder's
# death: the lock goes when the last file description on it closes, and a dead
# holder's processes close theirs whenever the scheduler gets to them. Asking at
# t+0 therefore has a window, measured on this machine at up to 3.0 ms idle and
# 7.4 ms with the box saturated (#130). Acquire stays **non-blocking through it**
# rather than growing a grace: an acquirer only lands inside a window that short
# by asking at the instant of a death, which is what the *test* deliberately does
# and what no caller does — the pool's real case is an agent re-running minutes
# after its last one was killed. A grace would buy 7 ms of an edge nobody stands
# on, at the price of an instant refusal, and it would let the test that owns
# this property pass on the grace rather than on the kernel. `--wait` is where
# waiting for somebody else's run to end belongs, and it already exists.
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
    # Explicit, because without it this function's exit status is whatever the
    # last `[[ ]]` in the last process's last descriptor happened to be — which
    # is `1` on any machine whose highest-numbered pid is not a lock holder, i.e.
    # nearly always. It printed the right answer and returned failure with it,
    # and under load that was a red one full-suite run in three (#121). A finder
    # reports what it found; not finding one more thing is not an error.
    return 0
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
            cti_host_exec "$CTI_TIER_HOST" ss -lunpH "sport = :$port" 2>/dev/null
            cti_host_exec "$CTI_TIER_HOST" ss -ltnpH "sport = :$port" 2>/dev/null
        done
        cti_host_exec "$CTI_TIER_HOST" ss -lunpH "sport = :$(cti_slot_daemon_port "$n")" 2>/dev/null
        cti_host_exec "$CTI_TIER_HOST" ss -ltnpH "sport = :$(cti_slot_daemon_port "$n")" 2>/dev/null
    } | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
}

# Pids running a binary *out of* this slot's install. Catches a squatting engine
# that has not yet bound, or has already lost, its port — which is the case a
# port sweep alone reads as a clean slot.
#
# The walk itself is over this host's own `/proc`, and it stays a walk rather
# than becoming N calls through the handle: what crosses a transport is a
# command, and the remote form of this is `host-guard`-style — ship this file
# and run the function over there (#53). What the handle owns here are the
# commands the sweep spawns and the kills it issues.
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
    return 0 # a finder, not a test — see cti_slot_lock_holders
}

# Is this pid still holding anything? Alive, and not a zombie: a zombie answers
# `kill -0` but let go of its descriptors, its ports and its install at exit, and
# all that is left of it is a table entry nobody has read yet. Waiting on one
# would be waiting for a third party to call `wait`, which is not this slot's
# business and not a thing the deadline below could ever be long enough for.
cti_slot_pid_holds() {
    cti_host_exec "$CTI_TIER_HOST" kill -0 "$1" 2>/dev/null || return 1
    [[ "$(cti_host_exec "$CTI_TIER_HOST" ps -o stat= -p "$1" 2>/dev/null)" == *Z* ]] && return 1
    return 0
}

# Which of "$@" are still holding.
cti_slot_pids_alive() {
    local pid alive=()
    for pid in "$@"; do cti_slot_pid_holds "$pid" && alive+=("$pid"); done
    printf '%s' "${alive[*]-}"
    return 0 # a finder, not a test — see cti_slot_lock_holders
}

# Every pid in "$@" gone from the process table, or the deadline in $1 spent.
#
# A kill is a *request*. `kill` returns once the signal has been posted, and the
# process is still there — ports bound, descriptors open, install held — until
# the kernel gets round to tearing it down. The two events are ordered by the
# scheduler and nothing else, which on a loaded box is a gap wide enough to
# matter: #130 measured the same gap on the other side of a death, where an
# `flock` outlived by up to 7.4 ms the `waitpid` that was being read as proof it
# had been released. Reclamation had the identical bug and the worse consequence,
# because what follows a reclaim is `run.sh` binding this slot's ports.
#
# Bounded and then reported, never extended: a SIGKILL that has not landed inside
# the deadline is news about the machine, not something to keep waiting on.
cti_slot_pids_gone() {
    local deadline=$((SECONDS + $1)) pid alive
    shift
    while :; do
        alive=0
        for pid in "$@"; do cti_slot_pid_holds "$pid" && alive=1; done
        ((alive == 0)) && return 0
        ((SECONDS < deadline)) || return 1
        sleep 0.5
    done
}

#
# `$2 == holders` adds the processes still holding the slot's lock, which is only
# askable once this shell has closed its own descriptor — see
# `cti_slot_lock_holders`. On acquire it is neither wanted nor meaningful: a slot
# we just took exclusively has no other holder.
cti_slot_reclaim() {
    local n="$1" pid pids=() marker last_run survivors
    mapfile -t pids < <(
        # Only the real tier sweeps the real machine. Both sweeps read facts
        # nothing virtualises — `ss` sees the one port space, `/proc` sees the one
        # process table — so a caller pointed at another state directory is by
        # definition not this machine's tier and must kill nothing on it. Without
        # this clause the no-Arma tier was the external event in #124: every
        # `tests/unit/test_pool_slots.py` pool run drove the real `regress.sh`
        # with `CTI_TIER_STATE` and `CTI_SLOT_INSTALL_MASTER` redirected into
        # tmp — but the port block is derived arithmetic that no variable moves,
        # so acquiring "slots 0-2" swept 2402/2502/2602 and 9099-9101 and killed
        # a live pool's three servers and their daemons mid-probe. Three times:
        # 2026-08-02 10:38:15, 10:39:21-26 and 13:09:04 UTC, each within seconds
        # of a `pytest tests/unit` on the same machine.
        if [[ "$CTI_SLOT_STATE" == "$CTI_SLOT_REAL_STATE" ]]; then
            cti_slot_port_pids "$n"
            cti_slot_install_pids "$n"
        fi
        [[ "${2:-}" == holders ]] && cti_slot_lock_holders "$n"
    )
    if [[ "$CTI_SLOT_STATE" != "$CTI_SLOT_REAL_STATE" ]]; then
        cti_slot_log "slot $n: state is $CTI_SLOT_STATE, not the machine's tier — sweeping no ports and no installs"
    fi
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
    for pid in "${pids[@]}"; do cti_host_exec "$CTI_TIER_HOST" kill "$pid" 2>/dev/null; done
    # Bounded, then hard, then confirmed. Not a synchronisation wait on a test —
    # a shutdown deadline on processes we have already decided are stale.
    cti_slot_pids_gone 15 "${pids[@]}" && return 0
    for pid in "${pids[@]}"; do cti_host_exec "$CTI_TIER_HOST" kill -9 "$pid" 2>/dev/null; done
    # And SIGKILL is confirmed rather than assumed, for the reason in
    # `cti_slot_pids_gone`: what runs next binds this slot's ports and stages into
    # this slot's install, and a `kill -9` that has been *posted* leaves both
    # still taken. Returning here without looking is how a reclaim reports a slot
    # clear that is not, and the `infra_unavailable` that follows names a bind
    # failure rather than the dead holder that caused it.
    cti_slot_pids_gone 10 "${pids[@]}" && return 0
    survivors="$(cti_slot_pids_alive "${pids[@]}")"
    cti_slot_log "slot $n: SIGKILL sent and still in the process table 10s later: $survivors — this slot is not clear"
    # The survivors on stdout as well as in the log, because the return value says
    # only *that* a slot did not come back clear and the caller has to report
    # *which* processes are still on its ports (#133). stdout rather than a shell
    # global so the answer survives the caller being a different process — which
    # is how the no-Arma tier substitutes this command to exercise the response.
    printf '%s\n' "$survivors"
    return 1
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
        [[ "$(cti_host_exec "$CTI_TIER_HOST" stat -c %i "$master/arma3server_x64")" == \
            "$(cti_host_exec "$CTI_TIER_HOST" stat -c %i "$dst/arma3server_x64")" ]]; then
        return 0
    fi

    # The staging itself, on the host that owns the install. Every one of these
    # is a command rather than a shell builtin, which is what makes the handle
    # the only thing between them and a second machine (ADR-0032).
    cti_slot_log "slot $n: building the install farm at $dst"
    cti_host_exec "$CTI_TIER_HOST" rm -rf "${dst:?}" || return 1
    cti_host_exec "$CTI_TIER_HOST" cp -al "$master" "$dst" || {
        cti_slot_log "slot $n: cp -al of $master failed"
        return 1
    }
    # Out of the farm: everything run.sh writes into the install.
    cti_host_exec "$CTI_TIER_HOST" rm -rf "${dst:?}/mpmissions" "${dst:?}/@cti" || return 1
    cti_host_exec "$CTI_TIER_HOST" rm -f "${dst:?}/cti_shim_x64.so" "${dst:?}/cti_shim.so" || return 1
    cti_host_exec "$CTI_TIER_HOST" mkdir -p "$dst/mpmissions" || return 1
    return 0
}
