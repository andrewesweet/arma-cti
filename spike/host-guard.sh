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
#     cti_windows_taskkill <image>   # teardown that fails loudly rather than open
#     cti_windows_wait_gone <image> <secs>   # teardown waits for its own exit
#
# Overridable for tests and for a machine that puts Windows somewhere else:
# CTI_WINDOWS_TASKLIST, CTI_WINDOWS_TASKKILL, CTI_HUMAN_CLIENT_IMAGE.

CTI_WINDOWS_TASKLIST="${CTI_WINDOWS_TASKLIST:-/mnt/c/Windows/System32/tasklist.exe}"
CTI_WINDOWS_TASKKILL="${CTI_WINDOWS_TASKKILL:-/mnt/c/Windows/System32/taskkill.exe}"
CTI_HUMAN_CLIENT_IMAGE="${CTI_HUMAN_CLIENT_IMAGE:-arma3_x64.exe}"

# The infra_unavailable exit code, kept the same number spike/tier-lock.sh and
# spike/regress.sh use so a caller reads one value for "not a result".
CTI_EXIT_INFRA_UNAVAILABLE=5

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

    out="$("$CTI_WINDOWS_TASKLIST" /FI "IMAGENAME eq $image" 2>&1)"
    status=$?
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
    out="$("$CTI_WINDOWS_TASKKILL" /IM "$image" /F 2>&1)"
    status=$?
    if ((status != 0)); then
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

# As a command: one line of reason on stderr and a verdict in the exit code.
cti_host_guard_main() {
    local state detail answer
    answer="$(cti_human_client_state)"
    state="${answer%% *}"
    detail="${answer#* }"
    case "$state" in
    free)
        printf '[host-guard] %s\n' "$detail" >&2
        return 0
        ;;
    running)
        printf '[host-guard] %s — a play session may be live.\n' "$detail" >&2
        printf '[host-guard] verdict=FAIL failure_class=infra_unavailable\n' >&2
        printf '[host-guard] This is a stop, not a result. Nothing was launched.\n' >&2
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
        ;;
    *)
        printf '[host-guard] %s\n' "$detail" >&2
        printf '[host-guard] verdict=FAIL failure_class=infra_unavailable\n' >&2
        printf '[host-guard] A check that could not run is not a check that passed.\n' >&2
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
        ;;
    esac
}

# Sourced by a runner, run by a test and by hand.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    cti_host_guard_main
    exit $?
fi
