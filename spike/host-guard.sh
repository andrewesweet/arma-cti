#!/usr/bin/env bash
# Is the human playing? The one guard on the Arma tier that protects a person
# rather than another agent (#41).
#
# The tier lock serialises agents. The port split (2402-2406 here, 2302-2306
# theirs) keeps a session and a test run off each other's sockets. Neither stops
# a test run from loading the shared machine underneath a live play session, and
# neither stops `spike/run.sh`'s teardown from killing a client it did not
# launch. That is this file's job, and it is asked before anything is launched.
#
# Resolved by absolute path, not by name. In the shells #41's runs got, the
# WSL2 interop PATH append was not in effect, so `command -v tasklist.exe` was
# false and the guard that was wrapped in it never ran once (#41). Whether that
# append reaches a given session varies with how the session was entered (#180:
# mosh/ssh-descended shells lack it, wsl.exe-descended shells carry it), which
# is the deeper reason for the absolute path: a check keyed on PATH is keyed on
# session ancestry. A check that could not run is not a check that passed: not
# being able to see the Windows process list is `infra_unavailable`, the same
# verdict as seeing a client in it. Both are a stop. Only "the list came back
# and the game is not in it" is permission to proceed.
#
# Usage, as a command:
#     spike/host-guard.sh            # exit 0 free, exit 5 stop, reason on stderr
#
# Usage, sourced:
#     source spike/host-guard.sh
#     cti_human_client_state         # echoes free|running|unavailable + detail
#     cti_guard_verdict fmt answer [host]   # that answer mapped onto a verdict
#     cti_windows_taskkill <image>   # teardown that fails loudly rather than open
#     cti_windows_wait_gone <image> <secs>   # teardown waits for its own exit
#
# Overridable for tests and for a machine that puts Windows somewhere else:
# CTI_WINDOWS_TASKLIST, CTI_WINDOWS_TASKKILL, CTI_HUMAN_CLIENT_IMAGE,
# CTI_WINDOWS_INTEROP_TIMEOUT.

CTI_WINDOWS_TASKLIST="${CTI_WINDOWS_TASKLIST:-/mnt/c/Windows/System32/tasklist.exe}"
CTI_WINDOWS_TASKKILL="${CTI_WINDOWS_TASKKILL:-/mnt/c/Windows/System32/taskkill.exe}"
CTI_HUMAN_CLIENT_IMAGE="${CTI_HUMAN_CLIENT_IMAGE:-arma3_x64.exe}"

# Every crossing of the WSL interop boundary is bounded (#144). Wedged interop is
# a known failure mode of this machine, and an unbounded call to it hangs either
# the pre-flight — before anything is launched, but after the run has queued —
# or the teardown, which runs while this run still holds its slot lock and the
# machine-wide client lock. Neither hang is typed as anything: it is an
# `infra_unavailable` nobody ever gets told about.
#
# Twenty seconds bounds *the tool answering*, not anything being measured:
# `tasklist.exe` returns in well under a second when interop is healthy. It is
# therefore not the timeout-extension the Contract forbids — there is no subject
# here whose length the number could be sized to.
CTI_WINDOWS_INTEROP_TIMEOUT="${CTI_WINDOWS_INTEROP_TIMEOUT:-20}"
# GNU timeout's "the deadline was reached" status, which these callers have to
# tell apart from the Windows tool's own exit codes.
CTI_EXIT_TIMED_OUT=124

# The infra_unavailable exit code, in its one bash home (#161): this file sits
# at the bottom of the source graph (spike/hosts.sh pulls it in; spike/slots.sh,
# spike/tier-lock.sh and the runners arrive through hosts.sh), so everything
# above reads this name rather than minting its own 5. Two places must agree
# with it and say so at their site: tools/host_guard_verdict.py's
# EXIT_INFRA_UNAVAILABLE, and the infra_unavailable row of spike/regress.sh's
# CLASS_RANK — the exit half of the class table, whose further consolidation
# is #92's.
CTI_EXIT_INFRA_UNAVAILABLE=5

# The usage-error exit code, beside its sibling: a refusal to run at all,
# never a verdict — so it must not collide with any class's exit code.
# regress.sh's `die` exited 2, which collided with CLASS_RANK's timeout row,
# and a caller reading the exit could not tell a mistyped flag from a typed
# timeout verdict (#147). sysexits(3)'s EX_USAGE, well clear of the class
# table's rows and of timeout(1)'s own 124/125/126/127/137.
CTI_EXIT_USAGE=64

# Echoes one of:
#   free <detail>          the list came back and the image is not in it
#   running <detail>       the image is in the list; a play session may be live
#   unavailable <detail>   the list could not be read; nothing was determined
#
# Never returns non-zero for "running": the caller decides what a state means, so
# that a test can assert the state and a runner can map it to a verdict.
cti_human_client_state() {
    local image="${1:-$CTI_HUMAN_CLIENT_IMAGE}"
    local out status

    if [[ ! -x "$CTI_WINDOWS_TASKLIST" ]]; then
        printf 'unavailable no executable Windows process list at %s\n' "$CTI_WINDOWS_TASKLIST"
        return 0
    fi

    # No `timeout` is the same shape of answer as no `tasklist.exe`: the check
    # can be made, but not bounded, and an unbounded check is one that can never
    # come back to say anything (#144).
    if ! command -v timeout >/dev/null 2>&1; then
        printf 'unavailable timeout(1) is missing, so %s cannot be asked under a deadline\n' \
            "$CTI_WINDOWS_TASKLIST"
        return 0
    fi

    out="$(timeout "$CTI_WINDOWS_INTEROP_TIMEOUT" \
        "$CTI_WINDOWS_TASKLIST" /FI "IMAGENAME eq $image" 2>&1)"
    status=$?
    if ((status == CTI_EXIT_TIMED_OUT)); then
        printf 'unavailable %s did not answer within %ss; WSL interop may be wedged\n' \
            "$CTI_WINDOWS_TASKLIST" "$CTI_WINDOWS_INTEROP_TIMEOUT"
        return 0
    fi
    if ((status != 0)); then
        printf 'unavailable %s exited %s: %s\n' \
            "$CTI_WINDOWS_TASKLIST" "$status" "$(tr '\n' ' ' <<<"$out")"
        return 0
    fi
    # An empty answer is not a negative answer. Real tasklist says "INFO: No
    # tasks are running which match the specified criteria." when nothing
    # matches, so silence means something other than the tool answering.
    if [[ -z "${out//[[:space:]]/}" ]]; then
        printf 'unavailable %s answered nothing for %s\n' "$CTI_WINDOWS_TASKLIST" "$image"
        return 0
    fi
    if grep -qiF "$image" <<<"$out"; then
        printf 'running %s is in the Windows process list\n' "$image"
        return 0
    fi
    printf 'free %s is not in the Windows process list\n' "$image"
}

# The free/running/unavailable answer mapped onto the tier's verdict. The
# mapping is decision logic, so it is decided in Python under pytest rather than
# here (#161, ADR-0049): tools/host_guard_verdict.py is the one home of a ladder
# that had grown three near-verbatim copies — this file's command form,
# `cti_host_guard` in spike/hosts.sh, and inline above spike/run.sh's launch.
#
# $1 is the rendering (`block` for the [host-guard] lines a guard prints,
# `env` for the key=value lines the harness folds into results.env), $2 the
# answer, $3 the host name when the caller has one. The mapper's lines land on
# this function's stdout for the caller to place; the verdict is the return
# value — 0 proceed, CTI_EXIT_INFRA_UNAVAILABLE stop.
#
# Fails closed at this site, per ADR-0049's mechanics: a mapper that could not
# run — no timeout(1) to bound it, no uv, killed at the bound — is a check that
# could not run, and that is a stop, never a proceed (#41). This adds no
# dependency the tier did not already carry — the daemon and the verdict typer
# are `uv run`s too — but it does mean the *guard* now needs uv reachable, and
# the shape that must never come back is the old one, where a missing tool made
# the guard silently pass.
cti_guard_verdict() {
    local format="$1" answer="$2" host="${3:-}" repo status
    local -a host_arg=()
    [[ -n "$host" ]] && host_arg=(--host "$host")
    repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if command -v timeout >/dev/null 2>&1; then
        (cd "$repo" && timeout "${CTI_UV_TIMEOUT:-300}" \
            uv run --quiet python tools/host_guard_verdict.py \
            --format "$format" "${host_arg[@]}" -- "$answer")
        status=$?
        case "$status" in
        0 | "$CTI_EXIT_INFRA_UNAVAILABLE") return "$status" ;;
        esac
        printf '[host-guard] the guard verdict could not be decided (host_guard_verdict.py exited %s); failing closed.\n' \
            "$status" >&2
    else
        printf '[host-guard] the guard verdict could not be decided (timeout(1) is missing, so the mapper cannot be bounded); failing closed.\n' >&2
    fi
    printf '[host-guard] verdict=FAIL failure_class=infra_unavailable%s\n' "${host:+ host=$host}" >&2
    printf '[host-guard] A check that could not run is not a check that passed.\n' >&2
    # For the env consumer, which reads a stop's detail off stdout.
    printf 'failure_detail=the host-guard verdict could not be decided; a check that could not run is not a check that passed\n'
    return "$CTI_EXIT_INFRA_UNAVAILABLE"
}

# Kill a Windows image on teardown. Same absolute-path resolution, and loud when
# it cannot: `taskkill.exe` by name failed open in the other direction, leaving a
# process alive after a run with nothing said about it (#41).
# Loud in both directions, not just the missing-executable one: a taskkill that
# ran and refused was discarded, which is the same silence by a different route
# (#83). "The process was not found" is the benign case and still says so, out
# loud — teardown cannot fail a run that has already produced its verdict, so the
# most this can do is put the tool's own words in the run's evidence.
cti_windows_taskkill() {
    local image="${1:?image name required}" out status
    if [[ ! -x "$CTI_WINDOWS_TASKKILL" ]]; then
        printf '[host-guard] cannot reach %s; %s may still be running\n' \
            "$CTI_WINDOWS_TASKKILL" "$image" >&2
        return 1
    fi
    if ! command -v timeout >/dev/null 2>&1; then
        printf '[host-guard] timeout(1) is missing; not asking %s unbounded — %s may still be running\n' \
            "$CTI_WINDOWS_TASKKILL" "$image" >&2
        return 1
    fi
    out="$(timeout "$CTI_WINDOWS_INTEROP_TIMEOUT" "$CTI_WINDOWS_TASKKILL" /IM "$image" /F 2>&1)"
    status=$?
    if ((status == CTI_EXIT_TIMED_OUT)); then
        # Teardown, so this cannot change a verdict already recorded — but a kill
        # request that never returned is the next run's guard refusing, and it
        # belongs in this run's evidence rather than in nobody's.
        printf '[host-guard] %s /IM %s did not return within %ss; WSL interop may be wedged, and %s may still be running\n' \
            "$CTI_WINDOWS_TASKKILL" "$image" "$CTI_WINDOWS_INTEROP_TIMEOUT" "$image" >&2
    elif ((status != 0)); then
        printf '[host-guard] %s /IM %s exited %s: %s\n' \
            "$CTI_WINDOWS_TASKKILL" "$image" "$status" "$(tr '\n' ' ' <<<"$out")" >&2
    fi
    return "$status"
}

# Wait for a Windows image *this run launched* to leave the process list (#119).
#
# The guard above asks "is the game running on the host?" and answers stop for
# yes. That question is ownership-blind on purpose: a guard taught to excuse a
# pid it recognises is a guard that can be talked into excusing the human's, and
# "a process we did not start means stop" has to stay absolute. So the asymmetry
# is resolved on the other side — the run that launched a client owns waiting for
# it to be gone, and hands the tier on only afterwards. Before this, a corpus run
# tripped its own guard: `client-port` finished, teardown asked its client to
# stop, and the next probe's pre-flight two seconds later saw a still-exiting
# arma3_x64.exe and called it a play session.
#
# A poll on the process list rather than a wait on a pid, because the Windows
# process is a child of WSL interop rather than of this shell: the pid here is
# the interop wrapper's, and its exit does not mean the game's. Polling the same
# list the guard reads means "gone" is exactly what the next run's guard will
# see, which is the only definition that settles anything.
#
# Bounded and loud. This is not a retry until something passes: the subject is a
# process shutting down, the condition is that process's absence, and a deadline
# reached is reported rather than extended. A run that could not see its own
# client leave says so in its evidence and leaves the next run's guard to refuse
# — which, that time, is the correct refusal.
cti_windows_wait_gone() {
    local image="${1:?image name required}" timeout="${2:-90}" deadline answer
    # A window that is not a number is not a window. Left to the arithmetic
    # below it would produce an empty deadline and a wait with no end — the same
    # fail-open shape the `bc` deadlines had (#144).
    if [[ ! "$timeout" =~ ^[0-9]+$ ]]; then
        printf '[host-guard] %s is not a number of seconds; refusing an unbounded wait for %s\n' \
            "$timeout" "$image" >&2
        return 1
    fi
    deadline=$((SECONDS + timeout))
    while :; do
        answer="$(cti_human_client_state "$image")"
        case "${answer%% *}" in
        free)
            printf '[host-guard] %s has left the Windows process list\n' "$image" >&2
            return 0
            ;;
        unavailable)
            printf '[host-guard] cannot tell whether %s is gone: %s\n' "$image" "${answer#* }" >&2
            return 1
            ;;
        esac
        ((SECONDS >= deadline)) && break
        sleep 1
    done
    printf '[host-guard] %s was still in the Windows process list %ss after teardown asked it to stop\n' \
        "$image" "$timeout" >&2
    return 1
}

# As a command: the reasons on stderr and the verdict in the exit code, mapped
# in the ladder's one home rather than by a case block of this file's own.
cti_host_guard_main() {
    cti_guard_verdict block "$(cti_human_client_state)" >&2
}

# Sourced by a runner, run by a test and by hand.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cti_host_guard_main
    exit $?
fi
