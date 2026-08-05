#!/usr/bin/env bash
# The holder's metadata beside a tier lock (#161). Sourced, never executed.
#
# Three locks publish who holds them — the slot locks (spike/slots.sh), the
# machine-wide Windows client lock (spike/client-lock.sh), and slot 0 taken as
# the hand-run tier lock (spike/tier-lock.sh, through `cti_slot_acquire`) — and
# each used to write its own near-copy of the same block, so a field added to
# one drifted from the others. This is the block's one home, and a tripwire in
# tests/unit/test_client_lock.py holds spike/*.sh to that.
#
# It stays bash on purpose (ADR-0049): the block's whole job is to name the
# holder *process* — `$$` at the instant the kernel hands over the flock — so
# the lock and its metadata are one process seam. There is no decision in it,
# and the key=value line format is the tier's own.
#
#   cti_lock_info_write   <info-path> <label> [slot]   what the holder publishes
#   cti_lock_info_render  <info-path> [indent]         that block, read back live
#   cti_lock_info_summary <info-path>                  the same, on one line
#   cti_lock_holder_pids  <lock-path>                  who actually has it open
#
# Reading it back is not `cat`, and that is #153's half of this file. A holder
# that is *wedged* rather than dead blocks the machine-wide client lock for as
# long as it likes, and the block as written says only when it started — so a
# queuer at 3 a.m. could tell you a run held the client and nothing about whether
# that run was working or stuck, and recovery meant a human going and finding the
# process. `cti_lock_info_render` derives the two facts that answer it from what
# is already written down: how long the holder has held it, and whether the pid
# in the block still has the lock open.
#
# Derived rather than refreshed, deliberately. The obvious alternative is a
# heartbeat — the holder touching a timestamp on a timer — and on this lock in
# particular that would be a background process writing about the liveness of the
# thing that spawned it. This lock's entire failure history is background
# processes outliving their parent while holding an inherited descriptor
# (`cti_client_lock_disown` exists for nothing else), and such a writer would go
# on refreshing the timestamp of a holder that no longer exists: the staleness
# signal would lie in precisely the case it was built to catch. A pid read out of
# `/proc` at the instant somebody asks cannot be forged by anything.
#
# Truncates rather than creates: a holder killed with -9 leaves its metadata
# behind, and the kernel has already handed the next holder the lock over the
# top of it. The slot line is written only for a lock that has one — the client
# lock is machine-scoped and carries none.
cti_lock_info_write() {
    local info="$1" label="$2" slot="${3:-}"
    {
        printf 'pid=%s\n' "$$"
        [[ -n "$slot" ]] && printf 'slot=%s\n' "$slot"
        printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'worktree=%s\n' "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
        printf 'branch=%s\n' "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
        printf 'issue=%s\n' "${CTI_TIER_ISSUE:-unstated}"
        printf 'label=%s\n' "$label"
    } >"$info"
}

# ------------------------------------------------------------ reading it back

# Whole seconds since an ISO-8601 instant, or non-zero if that is not one.
cti_lock_info_age_seconds() {
    local started="$1" then
    [[ -n "$started" ]] || return 1
    then="$(date -u -d "$started" +%s 2>/dev/null)" || return 1
    [[ "$then" =~ ^-?[0-9]+$ ]] || return 1
    printf '%s' "$(($(date -u +%s) - then))"
}

# Seconds as something a human reads at a glance, which is the whole point: the
# question a queuer is answering is "has this been held longer than the work it
# claims to be doing takes", and `15120` is not an answer to it.
cti_lock_info_duration() {
    local secs="$1"
    ((secs < 0)) && secs=0
    if ((secs >= 86400)); then
        printf '%dd %dh' $((secs / 86400)) $(((secs % 86400) / 3600))
    elif ((secs >= 3600)); then
        printf '%dh %02dm' $((secs / 3600)) $(((secs % 3600) / 60))
    elif ((secs >= 60)); then
        printf '%dm %02ds' $((secs / 60)) $((secs % 60))
    else
        printf '%ds' "$secs"
    fi
}

# Every pid with this lock file open, which is the only thing that knows who
# holds a lock whose metadata is missing or stale. The lock is a `flock(2)` on an
# open descriptor, so the descriptor table is where the answer is.
#
# Lifted here from `spike/slots.sh` unchanged (#153): the client lock needed the
# same finder, and a second copy of a /proc sweep is exactly the drift this file
# exists to stop.
cti_lock_holder_pids() {
    local lock="$1" pid fd target
    [[ -n "$lock" ]] || return 0
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

# Does that pid still have this lock open? One process's descriptors rather than
# every process's, so it is cheap enough to ask on the common refusal path — and
# exact, which `[[ -d /proc/$pid ]]` is not: a pid the kernel has recycled is
# alive and is not the holder.
cti_lock_pid_holds() {
    local pid="$1" lock="$2" fd
    [[ "$pid" =~ ^[0-9]+$ && -n "$lock" ]] || return 1
    for fd in "/proc/$pid/fd/"*; do
        [[ "$(readlink "$fd" 2>/dev/null)" == "$lock" ]] && return 0
    done
    return 1
}

# The holder block as it stands right now: what was written, plus how long ago it
# was written and whether the process that wrote it still has the lock.
cti_lock_info_block() {
    local info="$1" lock pid started secs holders
    lock="${info%.info}"
    if [[ -r "$info" ]]; then
        cat "$info"
        pid="$(sed -n 's/^pid=//p' "$info" | head -1)"
        started="$(sed -n 's/^started_at=//p' "$info" | head -1)"
        if secs="$(cti_lock_info_age_seconds "$started")"; then
            printf 'age=%s\n' "$(cti_lock_info_duration "$secs")"
            printf 'age_seconds=%s\n' "$secs"
        else
            printf 'age=unknown (started_at=%s is not an instant this box can read)\n' "${started:-}"
        fi
        if [[ -z "$pid" ]]; then
            printf 'holder=unknown (the metadata names no pid)\n'
        elif cti_lock_pid_holds "$pid" "$lock"; then
            # The ordinary case, and the one worth being cheap: pid alive, lock
            # in its hand, age above. Nothing else to say and no /proc sweep.
            printf 'holder=holding (pid %s)\n' "$pid"
            return 0
        elif [[ -d "/proc/$pid" ]]; then
            printf 'holder=stale (pid %s is alive but does not have this lock open; it was recycled, or the holder released without clearing its metadata)\n' "$pid"
        else
            printf 'holder=gone (pid %s has left the process list; this metadata outlived the run that wrote it)\n' "$pid"
        fi
    else
        printf 'holder=unnamed (no metadata beside the lock: it was deleted on release, or a child inherited the descriptor and outlived its parent)\n'
    fi
    # Only reached when the block cannot name the holder, which is when it is
    # worth sweeping every descriptor table on the box to find one. These are the
    # pids to kill, and naming them is the difference between a diagnosis and an
    # investigation.
    holders="$(cti_lock_holder_pids "$lock" | tr '\n' ' ' | sed 's/ *$//')"
    printf 'lock_held_by=%s\n' "${holders:-nobody — the lock is free, and whatever refused you was not this}"
    return 0
}

cti_lock_info_render() {
    local indent="${2:-}" line
    while IFS= read -r line; do
        printf '%s%s\n' "$indent" "$line"
    done < <(cti_lock_info_block "$1")
    return 0
}

# The same block folded onto one line, for a `failure_detail=` — which is a
# single key=value record and cannot carry a paragraph. It carries the holder's
# own words rather than a path to them: the `.info` file is deleted when the
# holder releases, so a durable record pointing at it names a path that stops
# existing minutes later (#147's finding, in the two places it survived).
cti_lock_info_summary() {
    local info="$1" block field value out=""
    block="$(cti_lock_info_block "$info")"
    for field in holder age issue label lock_held_by; do
        value="$(sed -n "s/^$field=//p" <<<"$block" | head -1)"
        [[ -n "$value" ]] || continue
        out+="${out:+; }$field $value"
    done
    # Newlines would forge a second record in a file every reader takes a line at
    # a time (#83's rule, and `record` in spike/run.sh applies the same one).
    printf '%s\n' "${out//$'\n'/ }"
    return 0
}
