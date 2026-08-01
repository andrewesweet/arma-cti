#!/usr/bin/env bash
# Serialise the Arma tier on a machine-scoped lock (ADR-0016).
#
#   spike/tier-lock.sh [--wait <secs>] [--label <text>] -- <command> [args...]
#
# The tier is single-occupancy per machine: one server install, one port range
# (2402-2406), one machine the human also plays on. Agent worktrees are many and
# short-lived, so the lock lives at ~/.arma-cti/tier.lock rather than inside any
# of them — a repo-scoped lock serialises nobody, because two agents in sibling
# worktrees each hold their own copy of it.
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
LOCK="$STATE_DIR/tier.lock"
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

mkdir -p "$STATE_DIR"
exec 9>"$LOCK"

acquired=0
if ((WAIT_SECS > 0)); then
    flock -x -w "$WAIT_SECS" 9 && acquired=1
else
    flock -x -n 9 && acquired=1
fi
if ((acquired == 0)); then
    {
        printf '\n[tier-lock] the Arma tier is busy — this is infra_unavailable, not a result.\n'
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
    printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'worktree=%s\n' "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    printf 'branch=%s\n' "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    printf 'issue=%s\n' "${CTI_TIER_ISSUE:-unstated}"
    printf 'label=%s\n' "${LABEL:-$*}"
} >"$INFO"

"$@"
status=$?

rm -f "$INFO"
exit "$status"
