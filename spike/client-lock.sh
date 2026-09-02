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
#   cti_client_lock_holder          what the holder wrote beside it, plus its age
#   cti_client_lock_summary         the same, on one line, for a failure_detail
#   cti_client_lock_busy            0 if somebody *else* holds it right now
#   cti_client_lock_wait_free S     bounded wait for nobody to hold it
#   cti_host_guard_or_queue H F W L the host guard, with a queue behind that lock
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
# The guard this file's queue is a queue *for*, and the host it is asked of. An
# explicit source rather than a debt owed to whoever sources this file: the
# queue below needs both halves — the lock, and the guard's answer — and a
# function that reads a name its own file never pulled in works only for as long
# as every caller happens to source both (spike/hosts.sh sources
# spike/host-guard.sh, and neither sources this file, so there is no cycle).
# shellcheck source=spike/hosts.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/hosts.sh"

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

# What the holder wrote, plus how long ago and whether it still has the lock
# (#153). A queuer that can only say "somebody holds the client" leaves a wedged
# holder to be found by a human; the same block with `age=` and `holder=` beside
# it is a one-line read — a corpus takes tens of minutes, so a holder four hours
# in with the lock still in its hand is stuck, and one whose pid has gone has
# left its metadata behind over a lock somebody else's orphan is keeping open.
# Derived on the way out rather than refreshed on a timer; the reasoning is in
# spike/lock-info.sh, and it is about this lock's own leaked-descriptor history.
cti_client_lock_holder() { cti_lock_info_render "$(cti_client_lock_info_path)"; }

# The same on one line, for a `failure_detail=` (#153). What a run records when
# it is refused has to outlive the holder that refused it, and the `.info` file
# does not: the holder deletes it on release.
cti_client_lock_summary() { cti_lock_info_summary "$(cti_client_lock_info_path)"; }

# 0 when somebody *else* holds it. A lock this shell holds is not busy: flock
# conflicts between two open file descriptions of the same process exactly as it
# does between two processes, so a naive probe would report our own lock as
# somebody else's and queue us behind ourselves.
#
# Nor is one our *parent* holds. The pool's tail exports CTI_CLIENT_LOCK_HELD to
# the `run.sh` it launches, and a child's flock probe on a file its parent holds
# conflicts exactly as a stranger's does — so without this line a probe in the
# tail would read its own pool's lock as a sibling agent's and queue behind
# itself, holding the machine-wide client for the whole of `--wait` while it
# waited for the thing it was inside of to let go (#196). The variable is the
# same one that stops that child taking the lock twice, read here for the same
# reason: "somebody else" is a property of the run, not of the file descriptor.
cti_client_lock_busy() {
    local lock fd
    [[ -z "$CTI_CLIENT_LOCK_FD" ]] || return 1
    [[ "${CTI_CLIENT_LOCK_HELD:-0}" != 1 ]] || return 1
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

# ------------------------------------------------------ the guard, with a queue
# Ask the host guard, and while the client it refuses for belongs to another
# *run* rather than to a person, wait for that run's client leg to end and ask
# again. 0 to proceed, the guard's own stop code otherwise.
#
#   $1  host handle             which machine's process list is being read
#   $2  rendering               `block` for a guard's stderr lines, `env` for
#                               the key=value lines a harness folds into a
#                               `failure_detail`
#   $3  patience, whole seconds 0 — the default everywhere — refuses exactly as
#                               an unqueued guard always did
#   $4  the caller's logger     `log`, so the queue's lines carry [regress] or
#                               [spike] rather than a prefix of this file's own
#
# The mapper's chosen rendering is echoed on **stdout** for the caller to place:
# to stderr in `block`, into a `failure_detail` in `env`. Only the final ask's,
# because a queue that narrated every refusal it decided not to act on would
# bury the one line the caller is going to act on under its own patience.
#
# One home for both askers (#196). `spike/regress.sh` grew this at entry (#127,
# reshaped by #151) and `spike/run.sh`'s per-probe bring-up did not have it: a
# pool already running when a sibling agent's client probe started met the
# ownership-blind guard, took the `infra_unavailable` stop, and abandoned every
# probe it had left — nineteen of them on 2026-08-05, nineteen seconds into
# somebody else's client. Two asks of one question deserve one implementation
# rather than a second near-verbatim copy of a decision (#161's shape); the
# verdict class vocabulary is unchanged by this, and only the patience and its
# host-guard reason detail are new.
#
# Every pass re-derives the two facts that make queueing legitimate rather than
# establishing them once (#151): a client is in the list, and somebody else
# holds the lock. A wait proves only that the lock was free at the instant it
# was read, and a third agent's tail can take the client in the gap.
cti_host_guard_or_queue() {
    local host="${1:-local}" format="${2:-block}" wait_secs="${3:-0}" say="${4:-cti_client_lock_log}"
    local deadline said=0 answer mapped status line
    # A patience that is not a number is not a patience. Refusing to queue is
    # the fail-closed half: the guard still runs and still decides, and the
    # caller is told why it got no queue rather than left to read a malformed
    # budget as an empty one.
    [[ "$wait_secs" =~ ^[0-9]+$ ]] || {
        "$say" "a queue takes whole seconds, got: $wait_secs — asking the guard once"
        wait_secs=0
    }
    deadline=$((SECONDS + wait_secs))
    while :; do
        # One read of the process list per pass, and the same one the verdict is
        # mapped from: asking twice would let the queue's precondition and the
        # guard's refusal come from two different answers.
        answer="$(cti_host_client_state "$host")"
        mapped="$(cti_guard_verdict "$format" "$answer" "$host")"
        status=$?
        ((status == 0)) && break
        # Only a client *in* the list is a thing another run can own. A list that
        # could not be read is not: queueing on it would be waiting out a broken
        # check rather than a sibling's client leg, and the answer to a check
        # that could not run is the same stop it has always been.
        [[ "$answer" == running* ]] || break
        # And only while somebody else holds the machine-wide client. A lock this
        # run already holds — this shell's, or its pool parent's — means no other
        # run's client can be in the list, so what is in it is the human's and
        # the guard's refusal is the right one.
        cti_client_lock_busy || break
        if ((wait_secs == 0)); then
            "$say" "another run holds the Windows client; a wait would queue behind it (--wait, or CTI_CLIENT_LOCK_WAIT for a hand run)"
            cti_client_lock_holder | while IFS= read -r line; do "$say" "  $line"; done
            break
        fi
        ((SECONDS < deadline)) || {
            "$say" "waited ${wait_secs}s and the Windows client was still held"
            break
        }
        # Said once, however many runs we queue behind: the holder named below
        # is the one we are waiting on now, and a line per contender would bury
        # the caller's own log under somebody else's schedule.
        ((said)) || "$say" "that client belongs to another run, not to a play session — queueing up to ${wait_secs}s:"
        said=1
        cti_client_lock_holder | while IFS= read -r line; do "$say" "  $line"; done
        cti_client_lock_wait_free $((deadline - SECONDS)) || {
            "$say" "waited ${wait_secs}s and the Windows client was still held"
            break
        }
    done
    printf '%s\n' "$mapped"
    return "$status"
}
