#!/usr/bin/env bash
# Take slot 0 of the Arma tier for a single-occupancy run (ADR-0016, ADR-0028).
#
#   spike/tier-lock.sh [--wait <secs>] [--label <text>] -- <command> [args...]
#
# A hand run — `just probe`, `just spike`, `just cycle-spike` — uses the one
# install at ~/arma3server and the port block 2402-2406, which is slot 0 and
# nothing else. So this takes **slot 0's lock**, `~/.arma-cti/slots/0.lock`,
# rather than a lock of its own: a pool run holds every slot it is using, and the
# two exclude each other on slot 0 exactly where they would otherwise collide.
# A pool that cannot get slot 0 runs in the slots it can get, which is the
# graceful half of the same property.
#
# Agent worktrees are many and short-lived, so the lock lives under
# ~/.arma-cti/ rather than inside any of them — a repo-scoped lock serialises
# nobody, because two agents in sibling worktrees each hold their own copy of it.
#
# flock(2) rather than a pidfile because the kernel releases it when the holder
# dies. The stale-holder failure this avoids is one Phase 0 actually met: a
# daemon nobody had killed still holding a port, reported as infra_unavailable.
#
# Acquisition is non-blocking by default. A held lock is a stop, not a result:
# nothing is launched, no port is touched, no evidence is written, and the exit
# code is the infra_unavailable one, with the holder's metadata printed so the
# queued caller knows what it is behind. `--wait <secs>` bounds a blocking
# acquire. Unbounded waiting is deliberately not offered — an agent that would
# wait forever should be doing other work.
set -uo pipefail

STATE_DIR="${CTI_TIER_STATE:-$HOME/.arma-cti}"
LOCK="$STATE_DIR/slots/0.lock"
INFO="$LOCK.info"
EXIT_INFRA_UNAVAILABLE=5

WAIT_SECS=0
LABEL=""
while (($# > 0)); do
    case "$1" in
    --wait)
        WAIT_SECS="${2:-}"
        shift 2
        ;;
    --label)
        LABEL="${2:-}"
        shift 2
        ;;
    --)
        shift
        break
        ;;
    *)
        printf '[tier-lock] unknown argument: %s\n' "$1" >&2
        exit 2
        ;;
    esac
done

if (($# == 0)); then
    printf '[tier-lock] nothing to run; usage: tier-lock.sh [--wait secs] -- cmd...\n' >&2
    exit 2
fi

if [[ ! "$WAIT_SECS" =~ ^[0-9]+$ ]]; then
    printf '[tier-lock] --wait takes whole seconds, got: %s\n' "$WAIT_SECS" >&2
    exit 2
fi

mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"

acquired=0
if ((WAIT_SECS > 0)); then
    flock -x -w "$WAIT_SECS" 9 && acquired=1
else
    flock -x -n 9 && acquired=1
fi
if ((acquired == 0)); then
    {
        printf '\n[tier-lock] slot 0 of the Arma tier is busy — this is infra_unavailable, not a result.\n'
        printf '[tier-lock] lock: %s\n' "$LOCK"
        if [[ -r "$INFO" ]]; then
            printf '[tier-lock] holder:\n'
            sed 's/^/[tier-lock]   /' "$INFO"
        else
            printf '[tier-lock] holder: no metadata beside the lock (holder died, or predates this file)\n'
        fi
        ((WAIT_SECS > 0)) && printf '[tier-lock] waited %ss and gave up.\n' "$WAIT_SECS"
        printf 'verdict=FAIL\n'
        printf 'failure_class=infra_unavailable\n'
        printf 'failure_detail=tier lock held; see %s\n' "$INFO"
    } >&2
    exit "$EXIT_INFRA_UNAVAILABLE"
fi

# Held. Publish who by, for whoever queues behind us. Truncate rather than
# create: a previous holder killed with -9 leaves its metadata behind, and the
# kernel has already handed us the lock over the top of it.
{
    printf 'pid=%s\n' "$$"
    printf 'slot=0\n'
    printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'worktree=%s\n' "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    printf 'branch=%s\n' "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    printf 'issue=%s\n' "${CTI_TIER_ISSUE:-unstated}"
    printf 'label=%s\n' "${LABEL:-$*}"
} >"$INFO"

# ADR-0022, on acquire rather than on release: the lock frees itself when its
# holder dies, and the holder's *processes* do not. A server or daemon a dead run
# left on slot 0's ports or in slot 0's install is stale state for us to clear
# before we launch, never state to inherit or to report as somebody else's
# `infra_unavailable` (#58, #70).
# shellcheck source=spike/slots.sh
source "$(dirname "${BASH_SOURCE[0]}")/slots.sh"
cti_slot_reclaim 0

"$@"
status=$?

rm -f "$INFO"
exit "$status"
