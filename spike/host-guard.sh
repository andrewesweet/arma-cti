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
# Resolved by absolute path, not by name. In an agent's shell on this machine
# the WSL2 interop PATH append is not in effect, so `command -v tasklist.exe` is
# false and the guard that was wrapped in it never ran once (#41). A check that
# could not run is not a check that passed: not being able to see the Windows
# process list is `infra_unavailable`, the same verdict as seeing a client in
# it. Both are a stop. Only "the list came back and the game is not in it" is
# permission to proceed.
#
# Usage, as a command:
#     spike/host-guard.sh            # exit 0 free, exit 5 stop, reason on stderr
#
# Usage, sourced:
#     source spike/host-guard.sh
#     cti_human_client_state         # echoes free|running|unavailable + detail
#     cti_windows_taskkill <image>   # teardown that fails loudly rather than open
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
