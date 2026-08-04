#!/usr/bin/env bash
# Which machine a tier run executes on (ADR-0032, issue #51). Sourced, never
# executed.
#
# ADR-0032 adopts a second machine whose plumbing cannot be built or tested
# before the hardware exists (#52 is the rebuild, #53 the transport). What can
# be built today is the **seam**: every host-touching operation the runner
# performs — launch, wait, kill, stat, guard, stage, evidence path, cleanup —
# names a host handle rather than this machine, and the handle has exactly one
# value, `local`, reached with no transport at all. Machine B then becomes a
# second row in the table below rather than a rewrite of the runner.
#
# A pool run executes on **one** host. That is ADR-0032's scheduling policy, not
# a simplification: "splitting one corpus pass across machines is explicitly not
# built", and concurrent full passes take a whole host each. So the handle is a
# property of the run, carried in `CTI_TIER_HOST`, and not a property of a slot.
#
#   cti_host_valid NAME          is this a host the tier knows?
#   cti_host_role NAME           human | tier — whose machine it is
#   cti_host_transport NAME      null today; the ssh row is #53's
#   cti_host_resolve             validate CTI_TIER_HOST and echo it, or refuse
#   cti_host_state               the tier state root (host-invariant; see below)
#   cti_host_runs                the evidence root, under it
#   cti_host_exec NAME cmd...    run a command on that host
#   cti_host_client_state NAME   the play-session question, per host and role
#   cti_host_guard NAME          ask it, and map the answer onto a verdict
#
# What this file is **not**: a registry file, an SSH transport, remote cleanup
# or evidence pull-back. ADR-0032 defers every one of them to the metal, because
# none can be tested before it exists, and untestable infrastructure built ahead
# of its hardware arrives wrong.

# The Windows process list, `taskkill`, and the play-session question itself.
# shellcheck source=spike/host-guard.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/host-guard.sh"

# The hosts the tier knows. One today: the machine this repository is checked
# out on, which is also the machine the human plays on — hence `human`, hence
# the play-session guard applies to it. Machine B arrives as
#   CTI_HOST_ROLE[bravo]=tier ; CTI_HOST_TRANSPORT[bravo]=ssh
# and nothing above this line changes.
#
# The role is what the guard is gated on. Guarding the tier's own client against
# the tier would be guarding it against itself (ADR-0032, second-machine.md §5).
declare -A CTI_HOST_ROLE=([local]=human)
declare -A CTI_HOST_TRANSPORT=([local]=null)

# The handle this run executes on. One value resolves today; an unknown name is
# refused rather than quietly treated as this machine, because the failure mode
# of a host boundary nothing reads is the same as a slot boundary nothing reads
# — a green run on the wrong machine (ADR-0028's rule, one level up).
CTI_TIER_HOST="${CTI_TIER_HOST:-local}"

cti_host_log() { printf '[hosts] %s\n' "$*" >&2; }

cti_host_valid() { [[ -n "${CTI_HOST_ROLE[${1:-}]:-}" ]]; }
cti_host_role() { printf '%s\n' "${CTI_HOST_ROLE[${1:-}]:-unknown}"; }
cti_host_transport() { printf '%s\n' "${CTI_HOST_TRANSPORT[${1:-}]:-none}"; }

# Echo the host this run is for, having checked the tier knows it. Refusing is
# `infra_unavailable`: a run aimed at a machine we have no way to reach measured
# nothing, and the caller must not read the absence as a result.
cti_host_resolve() {
    local host="${CTI_TIER_HOST:-local}"
    if ! cti_host_valid "$host"; then
        cti_host_log "no host named '$host' — the tier knows: ${!CTI_HOST_ROLE[*]}"
        cti_host_log "a second host is #52 (the metal) and #53 (the transport); neither exists yet"
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
    fi
    printf '%s\n' "$host"
}

# Where a host keeps its tier state — locks, run evidence. Machine-scoped
# rather than repo-scoped (ADR-0016): agent worktrees are siblings, and a lock
# inside any of them serialises nobody. `CTI_TIER_STATE` overrides it for tests.
#
# No host parameter, on purpose (#161): the path is the same on every host by
# construction — `~/.arma-cti` on the host that owns the state, which is where
# ADR-0032 puts a remote slot's lock so that the kernel freeing it is the kernel
# that owns it. What differs for a remote host is *whose* `$HOME` expands, and
# that is resolved on that host by the transport rather than here. These used to
# document and accept a host argument they ignored, and callers passed one
# believing it mattered — a boundary nothing reads, this file's own
# header-warning shape.
cti_host_state() { printf '%s\n' "${CTI_TIER_STATE:-$HOME/.arma-cti}"; }
cti_host_runs() { printf '%s/runs\n' "$(cti_host_state)"; }

# Run a command on a host. This is the seam: the one place that decides how a
# host is reached, and therefore the one place an SSH transport lands (#53).
#
# The local transport is `null` in the literal sense — the command runs here,
# with this shell's environment and this shell's file descriptors, so wrapping
# an operation in it costs a function call and changes nothing about what it
# does. That is the point: the seam has to be free today or it would not have
# been worth building before its second implementation exists (ADR-0032's
# restraint clause).
#
# Redirections stay on the caller's side. For a remote host that makes them
# writes on the *initiating* machine, which is exactly the evidence pull-back
# ADR-0032 defers — a distinction worth having in the shape now rather than
# discovering later.
cti_host_exec() {
    local host="$1"
    shift
    case "$(cti_host_transport "$host")" in
    null) "$@" ;;
    *)
        # Unreachable while `local` is the only row: cti_host_resolve refuses an
        # unknown host before anything is launched. Asserted anyway, because
        # failing *open* here would run machine B's work on this machine and
        # report it as machine B's — the one failure this seam exists to make
        # impossible.
        cti_host_log "no transport to '$host' is built (ADR-0032 defers it to #53); refusing to run: $*"
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
        ;;
    esac
}

# Is the human playing on this host? Per host and gated on the role, which is
# ADR-0032's rule: `human` hosts carry a person's play session and are guarded;
# a `tier` host's client belongs to the tier, and guarding it against the tier
# would stop every run that used it.
#
# Echoes the same free|running|unavailable triple `cti_human_client_state` does,
# so a caller that already reads that vocabulary reads this one unchanged.
#
# Not routed through `cti_host_exec`: the question is answered by reading the
# host's own process list, and a shell function does not cross a transport. A
# remote host answers it by running `host-guard.sh` over there, which is #53's
# to build and cannot be written honestly before there is a there.
cti_host_client_state() {
    local host="${1:-local}"
    if [[ "$(cti_host_role "$host")" != human ]]; then
        printf 'free %s is the tier'"'"'s own host; no play session to protect\n' "$host"
        return 0
    fi
    cti_human_client_state "${2:-$CTI_HUMAN_CLIENT_IMAGE}"
}

# The guard as a verdict: 0 to proceed, the infra_unavailable exit code to stop.
# `cti_host_guard_main`'s wording, per host — the difference is only that a host
# the tier owns is not asked, and says so.
cti_host_guard() {
    local host="${1:-local}" answer state detail
    answer="$(cti_host_client_state "$host")"
    state="${answer%% *}"
    detail="${answer#* }"
    case "$state" in
    free)
        printf '[host-guard] %s: %s\n' "$host" "$detail" >&2
        return 0
        ;;
    running)
        printf '[host-guard] %s: %s — a play session may be live.\n' "$host" "$detail" >&2
        printf '[host-guard] verdict=FAIL failure_class=infra_unavailable host=%s\n' "$host" >&2
        printf '[host-guard] This is a stop, not a result. Nothing was launched.\n' >&2
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
        ;;
    *)
        printf '[host-guard] %s: %s\n' "$host" "$detail" >&2
        printf '[host-guard] verdict=FAIL failure_class=infra_unavailable host=%s\n' "$host" >&2
        printf '[host-guard] A check that could not run is not a check that passed.\n' >&2
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
        ;;
    esac
}
