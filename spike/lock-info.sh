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
#   cti_lock_info_write <info-path> <label> [slot]
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
