#!/usr/bin/env bash
# The headed Windows client, as a machine-wide resource (issue #127). Sourced,
# never executed.
#
# There is one Windows host, one Arma install on it, and one headed client. The
# pool already serialises its own client probes into a tail with every other slot
# drained (#47) — which probes those are is derived rather than listed, by
# `spike/regress.sh`'s `host_probe` off each probe's `env:` header, because this
# comment said "two" until #157 found six — but a tail is a schedule inside one
# run, and the thing that collides is not two probes — it is two *runs*. Two
# agents in sibling worktrees gating at the same time each drain their own pool
# and then both drive the same client: at best each trips the other's host guard
# and reports `infra_unavailable`, at worst two clients join two worlds through
# one profile. Both were seen on 2026-08-02 while #125 was landing.
#
# So the client gets the same treatment the tier itself got in ADR-0016: one
# flock(2) on one path outside every worktree, with the holder's metadata beside
# it. `~/.arma-cti/windows-client.lock` rather than a repo path, because agent
# worktrees are many and short-lived and a repo-scoped lock serialises nobody.
#
#   cti_client_lock_path            where it lives
#   cti_client_lock_acquire W L     bounded-wait acquire; 0 held, 1 busy
#   cti_client_lock_release         drop it, and its metadata with it
#   cti_client_lock_holder          what the holder wrote beside it
#   cti_client_lock_busy            0 if somebody *else* holds it right now
#   cti_client_lock_wait_free S     bounded wait for nobody to hold it
#
# What this lock does that the guard cannot
# -----------------------------------------
# `spike/host-guard.sh` is ownership-blind on purpose and stays that way (#119):
# a guard that can excuse a client it thinks is ours can be talked into excusing
# the human's, so "a client in the process list is a stop" has to stay absolute.
# That leaves "ours just exited" and "theirs is still running" indistinguishable
# to the guard — and this lock is what makes them distinguishable to the
# *caller*, without the guard learning anything.
#
# The property that buys it is an ordering one, and it is the reason release is
# where it is: a holder does not let go until `cti_windows_wait_gone` has watched
# its client leave the list. So while we hold the lock, no other run's client is
# in the process list; a client that is there anyway is the human's, and the
# guard's refusal is the correct one. And a client in the list while somebody
# else holds the lock is theirs, which is a thing to queue behind rather than a
# play session to refuse for.
#
# Waiting is bounded and it is queueing, not synchronisation. `--wait` on
# `just regress` is #125's precedent: waiting on a resource somebody else holds
# is what a queue is, and the Contract's ban is on sleeping until a *test*
# passes. Nothing here is ever extended to make a probe green.

# The holder-metadata block every tier lock writes, in its one home (#161).
# shellcheck source=spike/lock-info.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lock-info.sh"

CTI_CLIENT_LOCK_STATE="${CTI_TIER_STATE:-$HOME/.arma-cti}"
# The fd this shell holds it on, empty when we do not hold it. Inherited by
# children, which is deliberate: `spike/run.sh` under the pool's tail must not
# take a second lock on a file its parent already holds.
CTI_CLIENT_LOCK_FD=""

cti_client_lock_path() { printf '%s/windows-client.lock\n' "$CTI_CLIENT_LOCK_STATE"; }
cti_client_lock_info_path() { printf '%s.info\n' "$(cti_client_lock_path)"; }

cti_client_lock_log() { printf '[client-lock] %s\n' "$*" >&2; }

# Bounded-wait acquire. 0 held by us, 1 held by somebody else, 2 unusable path.
# A wait of 0 is a non-blocking try, which is the default everywhere: an agent
# that would wait forever should be doing other work.
cti_client_lock_acquire() {
    local wait_secs="${1:-0}" label="${2:-unstated}" lock fd
    [[ "$wait_secs" =~ ^[0-9]+$ ]] || {
        cti_client_lock_log "wait takes whole seconds, got: $wait_secs"
        return 2
    }
    [[ -z "$CTI_CLIENT_LOCK_FD" ]] || return 0 # already ours; acquiring twice deadlocks
    lock="$(cti_client_lock_path)"
    mkdir -p "$(dirname "$lock")" || return 2
    exec {fd}>"$lock" || return 2
    if ((wait_secs > 0)); then
        flock -x -w "$wait_secs" "$fd" 2>/dev/null
    else
        flock -x -n "$fd" 2>/dev/null
    fi || {
        exec {fd}>&-
        return 1
    }
    CTI_CLIENT_LOCK_FD=$fd
    # Holder metadata from its one home (#161, spike/lock-info.sh). No slot:
    # this lock is machine-scoped.
    cti_lock_info_write "$lock.info" "$label"
    return 0
}

# Idempotent, because it is called from a trap that also runs on the path where
# the lock was never taken.
cti_client_lock_release() {
    [[ -n "$CTI_CLIENT_LOCK_FD" ]] || return 0
    rm -f "$(cti_client_lock_info_path)"
    exec {CTI_CLIENT_LOCK_FD}>&-
    CTI_CLIENT_LOCK_FD=""
}

# Drop this shell's handle without touching the metadata, for a child that must
# not keep the lock alive.
#
# `flock` frees a lock only when the *last* open file description on it closes,
# and a background subshell inherits every descriptor its parent had. So a
# server, daemon or client this run launched holds the client lock too, and one
# that outlives the run — killed with -9, or a stub that ignores signals — holds
# it forever, against a `.info` file the dead parent already deleted. Which is a
# permanent machine-wide stop with no holder to name: caught by
# `tests/unit/test_run_verdict.py`'s teardown test on the first run of this
# lock, where a leaked child had made every later run infra_unavailable.
#
# Every background launch in `spike/run.sh` calls this before its `exec`.
# spike/slots.sh's `cti_slot_close` is the same wall for the same reason.
cti_client_lock_disown() {
    [[ -n "$CTI_CLIENT_LOCK_FD" ]] || return 0
    exec {CTI_CLIENT_LOCK_FD}>&-
    CTI_CLIENT_LOCK_FD=""
}

cti_client_lock_holder() {
    local info
    info="$(cti_client_lock_info_path)"
    if [[ -r "$info" ]]; then
        cat "$info"
    else
        printf 'no metadata beside the lock (holder died, or predates this file)\n'
    fi
}

# 0 when somebody *else* holds it. A lock this shell holds is not busy: flock
# conflicts between two open file descriptions of the same process exactly as it
# does between two processes, so a naive probe would report our own lock as
# somebody else's and queue us behind ourselves.
cti_client_lock_busy() {
    local lock fd
    [[ -z "$CTI_CLIENT_LOCK_FD" ]] || return 1
    lock="$(cti_client_lock_path)"
    [[ -e "$lock" ]] || return 1
    exec {fd}<"$lock" || return 1
    if flock -x -n "$fd" 2>/dev/null; then
        flock -u "$fd" 2>/dev/null
        exec {fd}<&-
        return 1
    fi
    exec {fd}<&-
    return 0
}

# Bounded wait for nobody to be holding it, without taking it. Used by the
# pool's pre-flight, which must not hold the client for the whole of a pass that
# only needs it in the tail.
cti_client_lock_wait_free() {
    local secs="${1:-0}" deadline
    [[ "$secs" =~ ^[0-9]+$ ]] || return 2
    deadline=$((SECONDS + secs))
    while cti_client_lock_busy; do
        ((SECONDS < deadline)) || return 1
        # A queue's poll interval, not a synchronisation wait: this sleeps until
        # somebody else's client leg ends, which is the whole of what it is for.
        sleep 5
    done
    return 0
}
