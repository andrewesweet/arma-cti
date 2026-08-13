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
#   cti_host_transport NAME      null or the registry's one SSH target
#   cti_host_resolve             validate CTI_TIER_HOST and echo it, or refuse
#   cti_host_state               the tier state root (host-invariant; see below)
#   cti_host_runs                the evidence root, under it
#   cti_host_exec NAME cmd...    run a command on that host
#   cti_host_client_state NAME   the play-session question, per host and role
#   cti_host_guard NAME          ask it, and map the answer onto a verdict
#
# The registry stays outside Git. This file implements its null and SSH
# transports, remote whole-pass staging, and evidence pull-back.

# The Windows process list, `taskkill`, and the play-session question itself.
# shellcheck source=spike/host-guard.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/host-guard.sh"

# The machine-scoped registry is parsed in Python, where malformed TOML and a
# contradictory capability are unit-testable. An absent file preserves the
# original local-only row; a present unreadable file refuses the host seam.
#
# The role is what the guard is gated on. Guarding the tier's own client against
# the tier would be guarding it against itself (ADR-0032, second-machine.md §5).
declare -A CTI_HOST_ROLE=()
declare -A CTI_HOST_TRANSPORT=()
declare -A CTI_HOST_SSH_TARGET=()
declare -A CTI_HOST_SLOTS=()
declare -A CTI_HOST_HEADED=()
declare -A CTI_HOST_CLIENT_DRIVER=()
declare -A CTI_HOST_REMOTE_ROOT=()
CTI_HOST_REGISTRY_STATUS=0

cti_host_registry_load() {
    local registry="${CTI_HOSTS_FILE:-$HOME/.arma-cti/hosts.toml}"
    local name role transport ssh_target slots headed driver remote_root
    local rows status
    rows="$(python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tools/host_registry.py" \
        shell --config "$registry")"
    status=$?
    if ((status != 0)); then
        CTI_HOST_REGISTRY_STATUS=$status
        return 0
    fi
    while IFS=$'\t' read -r name role transport ssh_target slots headed driver remote_root; do
        [[ -n "$name" ]] || continue
        [[ "$ssh_target" == - ]] && ssh_target=""
        [[ "$remote_root" == - ]] && remote_root=""
        CTI_HOST_ROLE[$name]="$role"
        CTI_HOST_TRANSPORT[$name]="$transport"
        CTI_HOST_SSH_TARGET[$name]="$ssh_target"
        CTI_HOST_SLOTS[$name]="$slots"
        CTI_HOST_HEADED[$name]="$headed"
        CTI_HOST_CLIENT_DRIVER[$name]="$driver"
        CTI_HOST_REMOTE_ROOT[$name]="$remote_root"
    done <<<"$rows"

    # Once a pass has crossed SSH, this process is executing *as* that host. It
    # retains the reported host name while every operation becomes local to the
    # remote kernel. No secondary alias is copied or tried as a fallback.
    if [[ -n "${CTI_EXECUTION_HOST:-}" ]]; then
        CTI_HOST_ROLE[$CTI_EXECUTION_HOST]=tier
        CTI_HOST_TRANSPORT[$CTI_EXECUTION_HOST]=null
        CTI_HOST_SLOTS[$CTI_EXECUTION_HOST]="${CTI_REMOTE_SLOTS:-3}"
        CTI_HOST_HEADED[$CTI_EXECUTION_HOST]="${CTI_REMOTE_HEADED_CLIENT:-1}"
        CTI_HOST_CLIENT_DRIVER[$CTI_EXECUTION_HOST]="${CTI_REMOTE_CLIENT_DRIVER:-proton}"
    fi
}
cti_host_registry_load

# The handle this run executes on. One value resolves today; an unknown name is
# refused rather than quietly treated as this machine, because the failure mode
# of a host boundary nothing reads is the same as a slot boundary nothing reads
# — a green run on the wrong machine (ADR-0028's rule, one level up).
CTI_TIER_HOST="${CTI_TIER_HOST:-local}"

cti_host_log() { printf '[hosts] %s\n' "$*" >&2; }

cti_host_valid() { [[ -n "${CTI_HOST_ROLE[${1:-}]:-}" ]]; }
cti_host_role() { printf '%s\n' "${CTI_HOST_ROLE[${1:-}]:-unknown}"; }
cti_host_transport() { printf '%s\n' "${CTI_HOST_TRANSPORT[${1:-}]:-none}"; }
cti_host_ssh_target() { printf '%s\n' "${CTI_HOST_SSH_TARGET[${1:-}]:-}"; }
cti_host_slots() { printf '%s\n' "${CTI_HOST_SLOTS[${1:-}]:-0}"; }
cti_host_headed_client() { [[ "${CTI_HOST_HEADED[${1:-}]:-0}" == 1 ]]; }
cti_host_client_driver() { printf '%s\n' "${CTI_HOST_CLIENT_DRIVER[${1:-}]:-none}"; }
cti_host_remote_root() { printf '%s\n' "${CTI_HOST_REMOTE_ROOT[${1:-}]:-}"; }

# Echo the host this run is for, having checked the tier knows it. Refusing is
# `infra_unavailable`: a run aimed at a machine we have no way to reach measured
# nothing, and the caller must not read the absence as a result.
cti_host_resolve() {
    local host="${CTI_TIER_HOST:-local}"
    if ((CTI_HOST_REGISTRY_STATUS != 0)); then
        cti_host_log "the host registry could not be read; refusing every host"
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
    fi
    if ! cti_host_valid "$host"; then
        cti_host_log "no host named '$host' — the tier knows: ${!CTI_HOST_ROLE[*]}"
        cti_host_log "configure the host in ~/.arma-cti/hosts.toml; no local fallback is permitted"
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
# Redirections stay on the caller's side. Whole remote passes use the dedicated
# staging and pull-back operation below instead of composing this primitive.
cti_host_exec() {
    local host="$1"
    shift
    case "$(cti_host_transport "$host")" in
    null) "$@" ;;
    ssh)
        # OpenSSH sends its post-target argv as one command string for the
        # remote login shell. Quote each local word before that join so the
        # shell reconstructs the argv that this function received.
        local remote_command
        printf -v remote_command '%q ' "$@"
        ssh -T \
            -oBatchMode=yes \
            -oStrictHostKeyChecking=yes \
            -oConnectTimeout=8 \
            -oServerAliveInterval=5 \
            -oServerAliveCountMax=2 \
            -oClearAllForwardings=yes \
            "$(cti_host_ssh_target "$host")" -- "${remote_command% }"
        ;;
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

cti_host_rsync_shell() {
    printf '%s\n' \
        'ssh -T -oBatchMode=yes -oStrictHostKeyChecking=yes -oConnectTimeout=8 -oServerAliveInterval=5 -oServerAliveCountMax=2 -oClearAllForwardings=yes'
}

# Ship and run one whole pass. The unchanged pool executes below one SSH
# channel, so its slot descriptors, stale-state cleanup, ports and worlds all
# live on the remote kernel. A broken transport never returns into local work.
cti_host_remote_regress() {
    local host="$1" repo="$2"
    shift 2
    local target root run_id remote_repo local_build remote_build status pull_status git_sha git_dirty
    target="$(cti_host_ssh_target "$host")"
    root="$(cti_host_remote_root "$host")"
    run_id="remote-$(date -u +%Y%m%dT%H%M%SZ)-$$"
    remote_repo="$root/$run_id"
    git_sha="$(git -C "$repo" rev-parse HEAD 2>/dev/null || printf unknown)"
    if [[ -n "$(git -C "$repo" status --porcelain 2>/dev/null | head -1)" ]]; then
        git_dirty=true
    else
        git_dirty=false
    fi

    [[ -n "$target" && "$root" == /* ]] || {
        cti_host_log "$host has no bounded SSH target or absolute remote root"
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
    }

    local_build="$(sed -n 's/^[[:space:]]*"buildid"[[:space:]]*"\([0-9]*\)".*/\1/p' \
        "$HOME/arma3server/steamapps/appmanifest_233780.acf" 2>/dev/null | head -1)"
    remote_build="$(cti_host_exec "$host" sed -n \
        's/^[[:space:]]*"buildid"[[:space:]]*"\([0-9]*\)".*/\1/p' \
        /home/cti/arma3server/steamapps/appmanifest_233780.acf 2>/dev/null | head -1)"
    if [[ -z "$local_build" || -z "$remote_build" || "$local_build" != "$remote_build" ]]; then
        cti_host_log "engine build disagreement before launch: local=${local_build:-unreadable} $host=${remote_build:-unreadable}"
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
    fi

    cti_host_exec "$host" mkdir -p "$remote_repo" || return "$CTI_EXIT_INFRA_UNAVAILABLE"
    rsync -a --delete --timeout=60 \
        --exclude=.git/ --exclude=.venv/ --exclude=.pytest_cache/ \
        -e "$(cti_host_rsync_shell)" \
        "$repo/" "$target:$remote_repo/" || return "$CTI_EXIT_INFRA_UNAVAILABLE"

    cti_host_log "engine build $local_build agrees; running $run_id on $host"
    ssh -T \
        -oBatchMode=yes \
        -oStrictHostKeyChecking=yes \
        -oConnectTimeout=8 \
        -oServerAliveInterval=5 \
        -oServerAliveCountMax=2 \
        -oClearAllForwardings=yes \
        "$target" -- \
        env CTI_REMOTE_ACTIVE=1 CTI_EXECUTION_HOST="$host" CTI_TIER_HOST="$host" \
        CTI_REMOTE_GIT_SHA="$git_sha" CTI_REMOTE_GIT_DIRTY="$git_dirty" UV_NO_DEV=1 \
        CTI_REMOTE_RUN_ID="$run_id" CTI_REMOTE_SLOTS="$(cti_host_slots "$host")" \
        CTI_REMOTE_HEADED_CLIENT="${CTI_HOST_HEADED[$host]}" \
        CTI_REMOTE_CLIENT_DRIVER="$(cti_host_client_driver "$host")" \
        bash "$remote_repo/spike/regress.sh" "$@"
    status=$?

    mkdir -p "$HOME/.arma-cti/runs"
    rsync -a --timeout=60 \
        --include="${run_id}-*/" --include="${run_id}-*/**" --exclude='*' \
        -e "$(cti_host_rsync_shell)" \
        "$target:/home/cti/.arma-cti/runs/" "$HOME/.arma-cti/runs/"
    pull_status=$?
    cti_host_exec "$host" rm -rf "$remote_repo" || true
    ((pull_status == 0)) || {
        cti_host_log "evidence copy from $host failed; remote evidence remains in place"
        return "$CTI_EXIT_INFRA_UNAVAILABLE"
    }
    ((status == 255)) && return "$CTI_EXIT_INFRA_UNAVAILABLE"
    return "$status"
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
# Per host — a host the tier owns is not asked, and its answer says so — with
# the answer→verdict mapping decided in its one home, tools/host_guard_verdict.py
# (#161, ADR-0049), rather than by a third copy of the case ladder here.
cti_host_guard() {
    local host="${1:-local}"
    cti_guard_verdict block "$(cti_host_client_state "$host")" "$host" >&2
}
