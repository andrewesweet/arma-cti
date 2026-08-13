#!/usr/bin/env bash
# Host-neutral headed-client driver. Sourced by spike/run.sh, never executed.
# Windows remains the local compatibility driver; Machine B uses the Proton
# service provisioned under the non-admin cti graphical session.

cti_proton_client_start() {
    local out="$1" server="$2" port="$3" password="$4" profile="$5" mod="$6"
    local runtime env_dir env_file
    runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    env_dir="$runtime/arma-cti"
    env_file="$env_dir/client.env"
    [[ "$server" != *$'\n'* && "$password" != *$'\n'* && "$profile" != *$'\n'* && "$mod" != *$'\n'* ]] || return 64
    mkdir -p "$env_dir" "$out" || return 1
    (
        umask 077
        {
            printf 'CTI_CLIENT_SERVER=%s\n' "$server"
            printf 'CTI_CLIENT_PORT=%s\n' "$port"
            printf 'CTI_CLIENT_PASSWORD=%s\n' "$password"
            printf 'CTI_CLIENT_PROFILE=%s\n' "$profile"
            printf 'CTI_CLIENT_MOD=%s\n' "$mod"
            printf 'CTI_CLIENT_EVIDENCE=%s\n' "$out"
        } >"$env_file"
    ) || return 1
    XDG_RUNTIME_DIR="$runtime" timeout 30 systemctl --user reset-failed cti-arma-client.service \
        >/dev/null 2>&1 || true
    XDG_RUNTIME_DIR="$runtime" timeout 30 systemctl --user start cti-arma-client.service
}

cti_proton_client_stop() {
    local out="$1" runtime unit_status cgroup cgroup_path
    runtime="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    mkdir -p "$out" || return 1
    XDG_RUNTIME_DIR="$runtime" timeout 60 systemctl --user stop cti-arma-client.service \
        >"$out/service-stop.txt" 2>&1
    unit_status=$?
    XDG_RUNTIME_DIR="$runtime" timeout 30 journalctl --user-unit cti-arma-client.service \
        --no-pager -o short-iso >"$out/service.journal" 2>&1 || true
    XDG_RUNTIME_DIR="$runtime" timeout 10 systemctl --user show cti-arma-client.service \
        --property=ActiveState,SubState,Result,ExecMainStatus,ControlGroup \
        >"$out/service-status.txt" 2>&1 || return 1
    cgroup="$(sed -n 's/^ControlGroup=//p' "$out/service-status.txt")"
    cgroup_path="/sys/fs/cgroup/${cgroup#/}"
    rm -f "$runtime/arma-cti/client.env"
    if [[ -n "$cgroup" && -s "$cgroup_path/cgroup.procs" ]]; then
        printf 'owned client cgroup still has processes: %s\n' \
            "$(tr '\n' ' ' <"$cgroup_path/cgroup.procs")" >>"$out/service-stop.txt"
        return 1
    fi
    grep -q '^ActiveState=inactive$' "$out/service-status.txt" || return 1
    return "$unit_status"
}
