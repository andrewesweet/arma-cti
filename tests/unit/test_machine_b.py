"""Repository-side Machine B commissioning contract (issues #52-#54)."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import runpy
import subprocess
from typing import TYPE_CHECKING, cast

import pytest
from conftest import REPO, load_tool

machine_b = load_tool("machine_b")
client_supervisor = runpy.run_path(str(REPO / "ops/machine-b/files/cti_arma_client.py"))

if TYPE_CHECKING:
    from pathlib import Path

ADMIN_USER = "commissioner"
MACHINE_B_LAN = "192.0.2.167"
LAPTOP_LAN = "192.0.2.36"
LAN_BROADCAST = "192.0.2.255"
STEAM_LIBRARY_UUID = "11111111-2222-4333-8444-555555555555"


def config_text(tmp_path: Path) -> str:
    return f"""
wake_broadcast = "{LAN_BROADCAST}"

[host]
logical_name = "bravo"
system_hostname = "arma-cti-b"
lan_address = "{MACHINE_B_LAN}"
tailscale_address = "100.64.0.2"
wired_mac = "00:11:22:33:44:55"
wired_interface = "enp3s0"
network_connection = "Wired connection 1"
ssh_alias_lan = "bravo-lan"
ssh_alias_tail = "bravo-tail"
admin_ssh_target = "{MACHINE_B_LAN}"
admin_user = "{ADMIN_USER}"
slots = 3
headed_client = true
human = false

[laptop]
lan_address = "{LAPTOP_LAN}"
tailscale_address = "100.64.0.1"
wsl_proxy_source = "10.2.0.1"
wired_mac = "aa:bb:cc:dd:ee:ff"
ssh_port = 22
tailscale_ssh_port = 22
peer_user = "cti-peer"
identity_to_bravo = "{tmp_path}/id_ed25519_bravo"

[onepassword]
vault = "Automation"
item = "arma-cti machine-b bootstrap"
trust_file = "{tmp_path}/machine-b-trust.json"
known_hosts_file = "{tmp_path}/known_hosts.machine-b"

[steam]
server_app_id = 233780
client_app_id = 107410
proton_version = "10.0-4"
server_install = "/home/cti/arma3server"
library_uuid = "{STEAM_LIBRARY_UUID}"
library_mount = "/home/cti/SteamLibrary"
library_root = "/home/cti/SteamLibrary/SteamLibrary"
client_install = "/home/cti/SteamLibrary/SteamLibrary/steamapps/common/Arma 3"
"""


def public_key(seed: int, comment: str) -> tuple[str, str]:
    kind = b"ssh-ed25519"
    key_bytes = bytes([seed]) * 32
    blob = len(kind).to_bytes(4, "big") + kind + len(key_bytes).to_bytes(4, "big") + key_bytes
    encoded = base64.b64encode(blob).decode("ascii")
    fingerprint = base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")
    return f"ssh-ed25519 {encoded} {comment}", f"SHA256:{fingerprint}"


def write_config(tmp_path: Path) -> Path:
    path = tmp_path / "machine-b.toml"
    path.write_text(config_text(tmp_path), encoding="utf-8")
    bravo_key, bravo_fingerprint = public_key(1, "bravo")
    laptop_key, laptop_fingerprint = public_key(2, "laptop")
    forward_key, _ = public_key(3, "laptop-to-bravo")
    (tmp_path / "id_ed25519_bravo").write_text("private-placeholder\n", encoding="utf-8")
    (tmp_path / "id_ed25519_bravo.pub").write_text(f"{forward_key}\n", encoding="utf-8")
    trust = {
        "schema": 1,
        "account": "",
        "vault": "Automation",
        "item": "arma-cti machine-b bootstrap",
        "item_id": "item-id",
        "bravo_host_public_key": bravo_key,
        "bravo_host_fingerprint": bravo_fingerprint,
        "laptop_host_public_key": laptop_key,
        "laptop_host_fingerprint": laptop_fingerprint,
        "laptop_to_bravo_public_key": forward_key,
    }
    trust_path = tmp_path / "machine-b-trust.json"
    trust_path.write_text(json.dumps(trust), encoding="utf-8")
    trust_path.chmod(0o600)
    return path


def inventory(**values: str) -> dict[str, object]:
    facts = {key: {"status": 0, "value": value} for key, value in values.items()}
    return {"transport": {"status": 0}, "facts": facts}


def healthy_inventory(config: machine_b.MachineBConfig) -> dict[str, object]:
    assert config.trust is not None
    ufw = "\n".join(
        [
            "Status: active",
            "Default: deny (incoming), allow (outgoing), disabled (routed)",
            f"22/tcp ALLOW IN {config.laptop.lan_address}",
            f"22/tcp ALLOW IN {config.laptop.tailscale_address}",
            *(
                f"{port}:{port + 4}/udp ALLOW IN {config.laptop.lan_address}"
                for port in (2402, 2502, 2602)
            ),
        ]
    )
    result = inventory(
        os_version="24.04",
        hostname="arma-cti-b",
        audit_identity="cti",
        runtime_identity="uid=1001(cti) gid=1001(cti) groups=1001(cti),44(video),109(render)",
        admin_identity=(
            f"uid=1000({config.host.admin_user}) gid=1000({config.host.admin_user}) "
            f"groups=1000({config.host.admin_user}),27(sudo)"
        ),
        sshd_dropin=(
            "AuthenticationMethods publickey\n"
            "PasswordAuthentication no\n"
            "KbdInteractiveAuthentication no\n"
            "PermitRootLogin no\n"
            "AllowTcpForwarding no\n"
            "AllowStreamLocalForwarding no\n"
            "X11Forwarding no\n"
            "AllowAgentForwarding no\n"
            f"AllowUsers {config.host.admin_user} {config.host.runtime_user}"
        ),
        sshd_effective=(
            "authenticationmethods publickey\n"
            "passwordauthentication no\n"
            "kbdinteractiveauthentication no\n"
            "permitrootlogin no\n"
            "allowtcpforwarding no\n"
            "allowstreamlocalforwarding no\n"
            "x11forwarding no\n"
            "allowagentforwarding no\n"
            f"allowusers {config.host.admin_user} {config.host.runtime_user}\n"
            "listenaddress 0.0.0.0:22\n"
            "listenaddress [::]:22"
        ),
        host_ed25519_fingerprint=config.trust.bravo_host_fingerprint,
        ufw=ufw,
        ethtool="Supports Wake-on: pumbg\nWake-on: g",
        nm_wol="magic",
        suspend_targets="masked\nmasked\nmasked\nmasked",
        gdm=(
            "[daemon]\nWaylandEnable=false\nAutomaticLoginEnable=true\nAutomaticLogin=cti\n"
            "[security]"
        ),
        gdm_config_loaded="loaded",
        graphical_session="3 x11",
        gpu="NVIDIA GeForce GTX 1650, 595.84",
        vulkan="GPU0: device NVIDIA GeForce GTX 1650",
        steamcmd="/usr/games/steamcmd",
        steam="/usr/games/steam",
        steam_library=(
            f"uuid={config.steam.library_uuid} "
            "mount=/home/cti/SteamLibrary type=ext4 owner=cti:cti "
            "options=rw,relatime,nosuid,nodev"
        ),
        steam_library_root=(
            "mount=/home/cti/SteamLibrary root=/home/cti/SteamLibrary/SteamLibrary"
        ),
        server_binary="present",
        server_manifest='"appid"\t\t"233780"',
        listeners="",
        client_manifest='"appid"\t\t"107410"',
        client_binary="present",
        proton_version="Proton 10.0-4",
        steam_compat_config="107410=proton_10",
        client_service="installed",
    )
    result["paths"] = {
        "laptop_to_bravo_lan": 0,
        "laptop_to_bravo_tail": 0,
        "bravo_to_laptop_lan": 0,
        "bravo_to_laptop_tail": 0,
    }
    result["laptop_firewall"] = {
        "status": 0,
        "value": (
            "Status: active\n"
            "Default: deny (incoming), allow (outgoing), disabled (routed)\n"
            f"22/tcp ALLOW IN {config.host.lan_address}\n"
            f"22/tcp ALLOW IN {config.host.tailscale_address}\n"
            f"22/tcp ALLOW IN {config.laptop.wsl_proxy_source}"
        ),
    }
    return result


def test_configuration_renders_only_validated_non_secret_values(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    rendered = machine_b.ansible_vars(config)
    assert rendered["ansible_python_interpreter"] == "/usr/bin/python3"
    assert rendered["cti_logical_host"] == "bravo"
    assert rendered["cti_admin_user"] == ADMIN_USER
    assert rendered["cti_laptop_ssh_port"] == 22
    assert rendered["cti_laptop_tail_port"] == 22
    assert rendered["cti_laptop_wsl_proxy_source"] == "10.2.0.1"
    assert rendered["cti_laptop_known_host_lan"] == LAPTOP_LAN
    assert rendered["cti_laptop_known_host_tail"] == "100.64.0.1"
    assert rendered["cti_slots"] == 3
    assert rendered["cti_proton_version"] == "10.0-4"
    assert rendered["cti_steam_library_mount"] == "/home/cti/SteamLibrary"
    assert rendered["cti_steam_library_root"] == "/home/cti/SteamLibrary/SteamLibrary"
    assert rendered["cti_client_install"] == (
        "/home/cti/SteamLibrary/SteamLibrary/steamapps/common/Arma 3"
    )
    assert rendered["cti_laptop_to_bravo_public_key"].startswith("ssh-ed25519 ")
    assert rendered["cti_laptop_known_hosts_file"] == str(tmp_path / "known_hosts.machine-b")
    assert not any("password" in key.casefold() for key in rendered)


def test_admin_user_is_required(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    configured = path.read_text(encoding="utf-8")
    path.write_text(
        configured.replace(f'admin_user = "{ADMIN_USER}"\n', "", 1),
        encoding="utf-8",
    )
    with pytest.raises(machine_b.ConfigurationError, match="admin_user must be"):
        machine_b.load_config(path)


def test_configured_admin_flows_through_audit_and_sshd_expectations(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    assert f"emit admin_identity 'id {ADMIN_USER}'" in machine_b.remote_audit_script(config)
    assert machine_b.verify_inventory(config, healthy_inventory(config)) == []

    broken = healthy_inventory(config)
    facts = cast("dict[str, object]", broken["facts"])
    dropin = cast("dict[str, object]", facts["sshd_dropin"])
    dropin["value"] = str(dropin["value"]).replace(
        f"AllowUsers {ADMIN_USER} cti", "AllowUsers legacy-admin cti"
    )
    assert machine_b.Failure(
        machine_b.FailureCode.SSH,
        "OpenSSH hardening drop-in is missing or incomplete",
    ) in machine_b.verify_inventory(config, broken)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("slots = 3", "slots = 7", "slot geometry"),
        (f'lan_address = "{MACHINE_B_LAN}"', 'lan_address = "not-an-ip"', "IP address"),
        ('wsl_proxy_source = "10.2.0.1"', 'wsl_proxy_source = "broad"', "IP address"),
        ('ssh_alias_lan = "bravo-lan"', 'ssh_alias_lan = "bravo lan"', "SSH alias"),
        ('proton_version = "10.0-4"', 'proton_version = "Experimental"', "pinned"),
        (
            f'library_uuid = "{STEAM_LIBRARY_UUID}"',
            'library_uuid = "not-a-uuid"',
            "filesystem UUID",
        ),
        (
            'library_mount = "/home/cti/SteamLibrary"',
            'library_mount = "/mnt/anything"',
            "Steam paths are fixed",
        ),
        (
            'library_root = "/home/cti/SteamLibrary/SteamLibrary"',
            'library_root = "/home/cti/SteamLibrary"',
            "Steam paths are fixed",
        ),
        (
            'client_install = "/home/cti/SteamLibrary/SteamLibrary/steamapps/common/Arma 3"',
            'client_install = "/home/cti/SteamLibrary/steamapps/common/Arma 3"',
            "Steam paths are fixed",
        ),
        ("ssh_port = 22", "ssh_port = 70000", "outside"),
    ],
)
def test_invalid_address_port_slot_alias_and_proton_values_are_refused(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    path = write_config(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
    with pytest.raises(machine_b.ConfigurationError, match=message):
        machine_b.load_config(path)


def test_unknown_configuration_key_is_refused(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + "surprise = true\n", encoding="utf-8")
    with pytest.raises(machine_b.ConfigurationError, match=r"unknown .*steam.*surprise"):
        machine_b.load_config(path)


def test_missing_or_broad_trust_cache_is_refused(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    trust_path = tmp_path / "machine-b-trust.json"
    trust_path.chmod(0o644)
    with pytest.raises(machine_b.ConfigurationError, match="mode 0600"):
        machine_b.load_config(path)
    trust_path.unlink()
    with pytest.raises(machine_b.ConfigurationError, match="bootstrap pull"):
        machine_b.load_config(path)


def test_public_key_fingerprint_is_derived_and_mismatch_is_refused(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    trust_path = tmp_path / "machine-b-trust.json"
    payload = json.loads(trust_path.read_text(encoding="utf-8"))
    payload["bravo_host_fingerprint"] = payload["laptop_host_fingerprint"]
    trust_path.write_text(json.dumps(payload), encoding="utf-8")
    trust_path.chmod(0o600)
    with pytest.raises(machine_b.ConfigurationError, match="does not match"):
        machine_b.load_config(path)


def test_redaction_is_recursive_and_does_not_emit_private_key_material() -> None:
    value = {
        "password": "hunter2",
        "nested": [{"token": "abc"}, "-----BEGIN OPENSSH PRIVATE KEY-----"],
        "public": "safe",
    }
    redacted = machine_b.redact(value)
    encoded = json.dumps(redacted)
    assert "hunter2" not in encoded
    assert '"abc"' not in encoded
    assert "OPENSSH PRIVATE KEY" not in encoded
    assert redacted["public"] == "safe"


def test_healthy_inventory_has_no_typed_failures(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    assert machine_b.verify_inventory(config, healthy_inventory(config)) == []


@pytest.mark.parametrize(
    ("fact", "value", "code"),
    [
        ("os_version", "22.04", machine_b.FailureCode.OS),
        ("hostname", "ubuntu", machine_b.FailureCode.IDENTITY),
        ("audit_identity", "unexpected-user", machine_b.FailureCode.IDENTITY),
        ("admin_identity", "", machine_b.FailureCode.IDENTITY),
        ("sshd_dropin", "PasswordAuthentication yes", machine_b.FailureCode.SSH),
        ("ufw", "Status: inactive", machine_b.FailureCode.FIREWALL),
        ("ethtool", "Supports Wake-on: d\nWake-on: d", machine_b.FailureCode.POWER),
        ("gpu", "", machine_b.FailureCode.GPU),
        ("steamcmd", "", machine_b.FailureCode.STEAM),
        ("steam_library", "", machine_b.FailureCode.STEAM),
        ("steam_library_root", "", machine_b.FailureCode.STEAM),
        ("server_binary", "", machine_b.FailureCode.ENGINE),
        ("listeners", "udp UNCONN 0 0 0.0.0.0:2302", machine_b.FailureCode.PORT),
        ("proton_version", "Proton Experimental", machine_b.FailureCode.CLIENT),
        ("client_binary", "", machine_b.FailureCode.CLIENT),
    ],
)
def test_each_audit_surface_has_a_typed_failure(
    tmp_path: Path, fact: str, value: str, code: machine_b.FailureCode
) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    broken = healthy_inventory(config)
    facts = cast("dict[str, object]", broken["facts"])
    facts[fact] = {"status": 0, "value": value}
    assert code in {failure.code for failure in machine_b.verify_inventory(config, broken)}


def test_transport_failure_is_ssh_only(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    got = machine_b.verify_inventory(config, {"transport": {"status": 255}, "facts": {}})
    assert got == [
        machine_b.Failure(
            machine_b.FailureCode.SSH,
            "primary LAN SSH transport is unavailable",
        )
    ]


def test_a_failed_secondary_or_reverse_path_is_typed_ssh(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    broken = healthy_inventory(config)
    paths = cast("dict[str, object]", broken["paths"])
    paths["bravo_to_laptop_tail"] = 255
    failures = machine_b.verify_inventory(config, broken)
    assert failures == [
        machine_b.Failure(
            machine_b.FailureCode.SSH,
            "non-interactive SSH path failed: bravo_to_laptop_tail",
        )
    ]


def test_an_effective_tailscale_only_ssh_override_is_typed_ssh(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    broken = healthy_inventory(config)
    facts = cast("dict[str, object]", broken["facts"])
    facts["sshd_effective"] = {
        "status": 0,
        "value": "passwordauthentication yes\nallowusers legacy-admin\nlistenaddress 100.64.0.2:22",
    }
    assert machine_b.Failure(
        machine_b.FailureCode.SSH,
        "effective OpenSSH policy is overridden or does not listen on LAN and Tailscale paths",
    ) in machine_b.verify_inventory(config, broken)


def test_conflicting_admin_autologin_is_typed_client(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    broken = healthy_inventory(config)
    facts = cast("dict[str, object]", broken["facts"])
    facts["gdm"] = {
        "status": 0,
        "value": f"AutomaticLogin=cti\nAutomaticLogin={ADMIN_USER}",
    }
    assert machine_b.Failure(
        machine_b.FailureCode.CLIENT,
        "GDM is not unambiguously configured for cti X11 autologin",
    ) in machine_b.verify_inventory(config, broken)


@pytest.mark.parametrize(
    ("fact", "value", "detail"),
    [
        (
            "gdm_config_loaded",
            "stale",
            "GDM has not loaded the commissioned autologin configuration",
        ),
        (
            "graphical_session",
            "",
            "cti does not have an active X11 graphical session",
        ),
        (
            "graphical_session",
            "882 wayland",
            "cti does not have an active X11 graphical session",
        ),
    ],
)
def test_graphical_identity_runtime_failures_are_typed_client(
    tmp_path: Path, fact: str, value: str, detail: str
) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    broken = healthy_inventory(config)
    facts = cast("dict[str, object]", broken["facts"])
    facts[fact] = {"status": 0, "value": value}
    assert machine_b.Failure(machine_b.FailureCode.CLIENT, detail) in machine_b.verify_inventory(
        config, broken
    )


def test_playbook_restarts_gdm_only_when_the_autologin_policy_changes() -> None:
    playbook = (machine_b.REPO / "ops/machine-b/apply.yml").read_text(encoding="utf-8")
    assert "password_lock: true" in playbook
    assert "Restart GDM after an explicit autologin change" in playbook
    assert playbook.count("notify: Activate GDM autologin") == 1
    configure = playbook.index("- name: Configure an unambiguous X11 autologin identity")
    notify = playbook.index("notify: Activate GDM autologin")
    assert configure < notify


def test_a_broad_inbound_firewall_rule_is_typed_firewall(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    broken = healthy_inventory(config)
    facts = cast("dict[str, object]", broken["facts"])
    row = cast("dict[str, object]", facts["ufw"])
    row["value"] = f"{row['value']}\n22/tcp ALLOW IN Anywhere"
    failures = machine_b.verify_inventory(config, broken)
    assert (
        machine_b.Failure(
            machine_b.FailureCode.FIREWALL,
            "UFW has inbound allowances outside the commissioned source/port set",
        )
        in failures
    )


def test_ansible_render_is_stable(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    first = machine_b.ansible_vars(config, "ssh-ed25519 reverse")
    second = machine_b.ansible_vars(dataclasses.replace(config), "ssh-ed25519 reverse")
    assert first == second


def test_native_server_installer_uses_explicit_steamcmd_path_with_restricted_path(
    tmp_path: Path,
) -> None:
    fake_steamcmd = tmp_path / "steamcmd"
    captured_arguments = tmp_path / "steamcmd-arguments"
    fake_steamcmd.write_text(
        '#!/bin/bash\nprintf \'%s\\n\' "$@" > "$CTI_CAPTURE"\n',
        encoding="utf-8",
    )
    fake_steamcmd.chmod(0o755)
    install_dir = tmp_path / "arma3server"
    installer = machine_b.REPO / "ops/machine-b/files/install-arma-server"
    result = subprocess.run(  # noqa: S603 — executes the repository installer at its shell seam.
        ["/bin/bash", str(installer)],
        input="no-purchase-account\n",
        text=True,
        capture_output=True,
        check=False,
        env={
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": str(tmp_path / "cti"),
            "CTI_STEAMCMD": str(fake_steamcmd),
            "CTI_SERVER_INSTALL": str(install_dir),
            "CTI_CAPTURE": str(captured_arguments),
        },
    )
    assert result.returncode == 0
    assert captured_arguments.read_text(encoding="utf-8").splitlines() == [
        "+force_install_dir",
        str(install_dir),
        "+login",
        "no-purchase-account",
        "+app_update",
        "233780",
        "validate",
        "+quit",
    ]


def test_generated_steam_library_handoff_is_bounded_non_destructive_and_stable(
    tmp_path: Path,
) -> None:
    filesystem_uuid = STEAM_LIBRARY_UUID
    first = machine_b.render_steam_library_script(filesystem_uuid)
    second = machine_b.render_steam_library_script(filesystem_uuid)
    assert first == second
    assert "/dev/disk/by-uuid/${filesystem_uuid}" in first
    assert "UUID=${filesystem_uuid} ${mount_point} ext4 rw,exec,nosuid,nodev 0 2" in first
    assert "findmnt --verify --tab-file" in first
    assert "steam-library=rolled-back" in first
    assert "steam-library=ready" in first
    assert "for required_option in rw nosuid nodev" in first
    assert "*,noexec,*)" in first
    assert "for required_option in rw exec" not in first
    assert not any(
        forbidden in first
        for forbidden in ("mkfs", "parted", "resize2fs", "wipefs", "fdisk", "sfdisk", " dd ")
    )
    syntax = subprocess.run(
        ["/bin/bash", "-n"],
        input=first,
        text=True,
        capture_output=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    output = tmp_path / "mount-steam-library.sh"
    assert machine_b.steam_library_script(filesystem_uuid, output) == 0
    assert output.read_text(encoding="utf-8") == first
    assert output.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize(
    ("options", "verdict"),
    [
        ("rw,relatime,nosuid,nodev", "accepted"),
        ("rw,relatime,exec,nosuid,nodev", "accepted"),
        ("rw,relatime,nosuid,nodev,noexec", "refused"),
        ("rw,relatime,nosuid", "refused"),
    ],
)
def test_steam_library_accepts_implicit_exec_but_rejects_noexec(
    tmp_path: Path, options: str, verdict: str
) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    candidate = healthy_inventory(config)
    facts = cast("dict[str, object]", candidate["facts"])
    fact = cast("dict[str, object]", facts["steam_library"])
    fact["value"] = (
        f"uuid={config.steam.library_uuid} mount={config.steam.library_mount} "
        f"type=ext4 owner=cti:cti options={options}"
    )
    failures = machine_b.verify_inventory(config, candidate)
    storage_failure = machine_b.Failure(
        machine_b.FailureCode.STEAM,
        "Steam library is not the configured persistent ext4 mount owned by cti",
    )
    assert (storage_failure not in failures) is (verdict == "accepted")


def test_steam_library_uuid_and_paths_reach_audit_and_client_service(tmp_path: Path) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    audit_script = machine_b.remote_audit_script(config)
    assert config.steam.library_uuid in audit_script
    assert str(config.steam.library_mount) in audit_script
    assert str(config.steam.library_root) in audit_script
    assert str(config.steam.client_install) in audit_script
    assert "__STEAM_LIBRARY_" not in audit_script
    assert "/home/cti/.steam/steam/steamapps/appmanifest_107410.acf" not in audit_script
    assert (
        'cat "/home/cti/SteamLibrary/SteamLibrary/steamapps/appmanifest_107410.acf"' in audit_script
    )
    assert (
        'cat "/home/cti/SteamLibrary/SteamLibrary/steamapps/common/Proton 10.0/version"'
        in audit_script
    )
    assert 'case ",$live_options," in *,noexec,*) exit 1' in audit_script
    assert 'case ",$live_options," in *,exec,*)' not in audit_script
    assert "test -w /home/cti/SteamLibrary" in audit_script

    service = (machine_b.REPO / "ops/machine-b/templates/cti-arma-client.service.j2").read_text(
        encoding="utf-8"
    )
    supervisor = (machine_b.REPO / "ops/machine-b/files/cti_arma_client.py").read_text(
        encoding="utf-8"
    )
    assert 'Environment="CTI_STEAM_LIBRARY_ROOT={{ cti_steam_library_root }}"' in service
    assert 'Environment="CTI_CLIENT_INSTALL={{ cti_client_install }}"' in service
    assert 'steam_library_root / "steamapps/appmanifest_107410.acf"' in supervisor
    assert 'steam_library_root / "steamapps/compatdata/107410' in supervisor


def test_rendered_storage_audit_executes_both_comparisons_as_single_commands(
    tmp_path: Path,
) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    controlled_commands = f"""
test() {{ return 0; }}
findmnt() {{
    case "$*" in
        *"--output UUID"*) printf '%s' '{config.steam.library_uuid}' ;;
        *"--output FSTYPE"*) printf '%s' ext4 ;;
        *"--output OPTIONS"*) printf '%s' rw,relatime,nosuid,nodev ;;
        *"--output SOURCE"*) printf '%s' 'UUID={config.steam.library_uuid}' ;;
        *"--output TARGET"*) printf '%s' '{config.steam.library_mount}' ;;
        *) return 1 ;;
    esac
}}
stat() {{ printf '%s' cti:cti; }}
export -f test findmnt stat
"""
    result = subprocess.run(
        ["/bin/bash", "-s"],
        input=controlled_commands + machine_b.remote_audit_script(config),
        capture_output=True,
        text=True,
        check=False,
        env={key: value for key, value in os.environ.items() if not key.startswith("SSH_")},
    )
    assert result.returncode == 0, result.stderr
    facts: dict[str, tuple[int, str]] = {}
    for row in result.stdout.splitlines():
        key, status, encoded = row.split("\t", 2)
        if key in {"steam_library", "steam_library_root"}:
            facts[key] = (int(status), base64.b64decode(encoded).decode())
    assert facts == {
        "steam_library": (
            0,
            (
                f"uuid={config.steam.library_uuid} mount={config.steam.library_mount} "
                "type=ext4 owner=cti:cti options=rw,relatime,nosuid,nodev"
            ),
        ),
        "steam_library_root": (
            0,
            f"mount={config.steam.library_mount} root={config.steam.library_root}",
        ),
    }


def test_client_supervisor_uses_registered_root_and_refuses_a_misaligned_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library_mount = tmp_path / "mount"
    library_root = library_mount / "SteamLibrary"
    client_install = library_root / "steamapps/common/Arma 3"
    client_install.mkdir(parents=True)
    (client_install / "arma3_x64.exe").write_bytes(b"client")
    manifest = library_root / "steamapps/appmanifest_107410.acf"
    manifest.write_text('"appid"\t\t"107410"\n', encoding="utf-8")
    proton = library_root / "steamapps/common/Proton 10.0/version"
    proton.parent.mkdir(parents=True)
    proton.write_text("1785139158 proton-10.0-4b\n", encoding="utf-8")

    layout_error = client_supervisor["_install_layout_error"]
    assert layout_error(library_root, client_install) == ""
    assert layout_error(library_mount, client_install) == (
        "CTI_CLIENT_INSTALL is not beneath the configured Steam library root"
    )

    commands: list[list[str]] = []

    def complete(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "fact\n", "")

    monkeypatch.setattr(client_supervisor["subprocess"], "run", complete)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    facts = client_supervisor["_facts"]
    facts(evidence, library_root, client_install)
    assert (evidence / "appmanifest_107410.acf").read_text(encoding="utf-8") == (
        '"appid"\t\t"107410"\n'
    )
    assert (evidence / "proton-version.txt").read_text(encoding="utf-8") == (
        "1785139158 proton-10.0-4b\n"
    )
    assert json.loads((evidence / "install-layout.json").read_text(encoding="utf-8")) == {
        "client_install": str(client_install),
        "steam_library_root": str(library_root),
    }
    assert ["steam", "--version"] not in commands
    assert commands[-1] == [
        "dpkg-query",
        "--show",
        "--showformat=${binary:Package}\t${Version}\n",
        "steam-installer",
    ]


def test_client_supervisor_waits_for_arma_after_steam_launcher_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Steam's short-lived launcher is not the owned client's lifetime."""
    library_root = tmp_path / "SteamLibrary"
    client_install = library_root / "steamapps/common/Arma 3"
    client_install.mkdir(parents=True)
    (client_install / "arma3_x64.exe").write_bytes(b"client")
    evidence = tmp_path / "evidence"
    monkeypatch.setenv("CTI_CLIENT_SERVER", MACHINE_B_LAN)
    monkeypatch.setenv("CTI_CLIENT_PORT", "2402")
    monkeypatch.setenv("CTI_CLIENT_EVIDENCE", str(evidence))
    monkeypatch.setenv("CTI_CLIENT_PROFILE", "cti")
    monkeypatch.setenv("CTI_STEAM_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("CTI_CLIENT_INSTALL", str(client_install))
    monkeypatch.setenv("CTI_CLIENT_MOD", "/home/cti/arma3server/@cti")

    class ExitedSteamLauncher:
        pid = 4242

        @staticmethod
        def poll() -> int:
            return 0

    supervisor_globals = client_supervisor["main"].__globals__
    arma_samples = iter([[], [4343], [4343], []])
    launch_commands: list[list[str]] = []
    monkeypatch.setitem(supervisor_globals, "_facts", lambda *_args: None)
    monkeypatch.setitem(supervisor_globals, "_wait_for_server", lambda *_args: True)
    monkeypatch.setitem(supervisor_globals, "_arma_pids", lambda: next(arma_samples))
    monkeypatch.setitem(supervisor_globals, "_write_process_tree", lambda *_args: None)
    monkeypatch.setitem(supervisor_globals, "_terminate_group", lambda *_args: None)
    monkeypatch.setattr(client_supervisor["shutil"], "which", lambda _name: "/usr/games/steam")

    def launch(command: list[str], **_kwargs: object) -> ExitedSteamLauncher:
        launch_commands.append(command)
        return ExitedSteamLauncher()

    monkeypatch.setattr(client_supervisor["subprocess"], "Popen", launch)
    monkeypatch.setattr(client_supervisor["signal"], "signal", lambda *_args: None)
    monkeypatch.setattr(client_supervisor["time"], "sleep", lambda *_args: None)

    assert client_supervisor["main"]() == 0
    assert launch_commands == [
        [
            "/usr/games/steam",
            "-silent",
            "-applaunch",
            "107410",
            "-noLauncher",
            f"-connect={MACHINE_B_LAN}",
            "-port=2402",
            "-password=",
            r"-mod=Z:\home\cti\arma3server\@cti",
            "-name=cti",
            "-window",
            "-noSplash",
            "-skipIntro",
            "-noPause",
        ]
    ]


@pytest.mark.parametrize("value", ["@cti", r"Z:\home\cti\@cti", "/one;/two"])
def test_client_supervisor_rejects_mod_paths_that_are_not_one_absolute_linux_root(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="one absolute Linux path"):
        client_supervisor["_windows_mod_path"](value)


def test_apply_reloads_the_user_manager_only_when_the_client_unit_changes() -> None:
    playbook = (machine_b.REPO / "ops/machine-b/apply.yml").read_text(encoding="utf-8")
    assert "listen: Reload cti client service" in playbook
    assert playbook.count("notify: Reload cti client service") == 1
    assert "daemon_reload: true\n        scope: user" in playbook
    assert 'XDG_RUNTIME_DIR: "/run/user/{{ cti_runtime_uid.stdout }}"' in playbook


def test_inventory_pins_every_bravo_connection_to_cti(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    targets: list[str] = []

    def fake_ssh(
        target: str, *_arguments: str, **_options: object
    ) -> subprocess.CompletedProcess[str]:
        targets.append(target)
        return subprocess.CompletedProcess(["ssh"], 0, "", "")

    monkeypatch.setattr(machine_b, "_ssh", fake_ssh)
    result = machine_b.collect_inventory(config)
    assert targets == [
        "cti@bravo-lan",
        "cti@bravo-lan",
        "cti@bravo-tail",
        "cti@bravo-lan",
        "cti@bravo-tail",
    ]
    transport = cast("dict[str, object]", result["transport"])
    assert transport["target"] == "cti@bravo-lan"


def test_logind_dropin_directory_is_created_before_policy_install() -> None:
    playbook = (machine_b.REPO / "ops/machine-b/apply.yml").read_text(encoding="utf-8")
    read = playbook.index("- name: Read the logind drop-in directory state")
    create = playbook.index("- name: Create the logind drop-in directory")
    install = playbook.index("- name: Install the no-idle-action logind policy")
    assert read < create < install
    assert "path: /etc/systemd/logind.conf.d\n        state: directory" in playbook
    assert "(cti_logind_dropin_directory.stat.isdir | default(false))" in playbook


def test_dconf_directories_and_profile_are_managed_before_power_policy() -> None:
    playbook = (machine_b.REPO / "ops/machine-b/apply.yml").read_text(encoding="utf-8")
    create = playbook.index("- name: Create the dconf policy directories")
    profile = playbook.index("- name: Select the managed local dconf database")
    power = playbook.index("- name: Install GNOME power and locking defaults")
    assert create < profile < power
    assert "- /etc/dconf/db/local.d\n        - /etc/dconf/profile" in playbook
    assert "user-db:user\n          system-db:local" in playbook
    assert "(cti_dconf_profile_directory.stat.isdir | default(false))" in playbook
    assert "(cti_dconf_local_directory.stat.isdir | default(false))" in playbook
    assert "- dconf-cli" in playbook


def test_playbooks_do_not_use_deprecated_injected_fact_variables() -> None:
    apply = (machine_b.REPO / "ops/machine-b/apply.yml").read_text(encoding="utf-8")
    laptop = (machine_b.REPO / "ops/machine-b/laptop.yml").read_text(encoding="utf-8")
    for deprecated in (
        "ansible_distribution",
        "ansible_distribution_version",
        "ansible_architecture",
        "ansible_kernel",
    ):
        assert deprecated not in apply
        assert deprecated not in laptop


def test_reverse_public_key_is_fetched_through_the_commissioning_session() -> None:
    playbook = (machine_b.REPO / "ops/machine-b/apply.yml").read_text(encoding="utf-8")
    source = (machine_b.REPO / "tools/machine_b.py").read_text(encoding="utf-8")
    generate = playbook.index("- name: Generate bravo's independent reverse automation key")
    fetch = playbook.index(
        "- name: Fetch bravo's reverse public key through the commissioning session"
    )
    assert generate < fetch
    assert 'dest: "{{ cti_reverse_public_key_fetch }}"\n        flat: true' in playbook
    assert 'variables["cti_reverse_public_key_fetch"] = str(reverse_public_key)' in source
    assert "reverse_public_key.read_text" in source
    apply_source = source[source.index("def apply(") : source.index("\ndef audit(")]
    assert "_ssh(" not in apply_source


def test_machine_b_plays_force_handlers_after_partial_failure() -> None:
    for name in ("apply.yml", "laptop.yml"):
        playbook = (machine_b.REPO / "ops/machine-b" / name).read_text(encoding="utf-8")
        assert "  force_handlers: true\n" in playbook


def test_laptop_play_migrates_obsolete_wsl_port_2222_rules() -> None:
    playbook = (machine_b.REPO / "ops/machine-b/laptop.yml").read_text(encoding="utf-8")
    read = playbook.index("- name: Read laptop UFW policy before rule migration")
    remove = playbook.index("- name: Remove obsolete WSL port 2222 allowances")
    permit = playbook.index("- name: Permit reverse SSH only from bravo")
    assert read < remove < permit
    assert "cti_laptop_ssh_port | int != 2222" in playbook
    assert "ufw --force delete allow proto tcp from {{ item }} to any port 2222" in playbook
    assert "from {{ cti_laptop_wsl_proxy_source }}" in playbook
    assert "comment 'arma-cti Windows LAN proxy'" in playbook


def test_laptop_play_removes_superseded_listener_address_restrictions() -> None:
    playbook = (machine_b.REPO / "ops/machine-b/laptop.yml").read_text(encoding="utf-8")
    assert "/etc/ssh/sshd_config.d/10-tailnet-hardening.conf" in playbook
    assert "/etc/ssh/sshd_config.d/99-codex-wsl.conf" in playbook
    assert "regexp: '^\\s*ListenAddress\\s'" in playbook
    assert "state: absent" in playbook


def test_non_default_known_host_port_uses_bracketed_target(
    tmp_path: Path,
) -> None:
    path = write_config(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "tailscale_ssh_port = 22", "tailscale_ssh_port = 2223"
        ),
        encoding="utf-8",
    )
    rendered = machine_b.ansible_vars(machine_b.load_config(path))
    assert rendered["cti_laptop_known_host_tail"] == "[100.64.0.1]:2223"


def test_windows_firewall_script_is_source_restricted_and_leaves_windows_ssh() -> None:
    script = (machine_b.REPO / "ops/machine-b/files/configure-windows-wsl-firewall.ps1").read_text(
        encoding="utf-8"
    )
    assert "[Parameter(Mandatory = $true)]" in script
    assert "-RemoteAddress $allowedSources" in script
    assert "-RemoteAddresses $allowedSources" in script
    assert "-LocalAddress $LaptopLanAddress" in script
    assert "-LocalPort 22" in script
    assert "-LocalPorts 22" in script
    assert "{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}" in script
    assert "Get-NetFirewallRule -Name $windowsRuleName" in script
    assert "Get-NetFirewallHyperVRule -Name $hyperVRuleName" in script
    assert "listenaddress=$LaptopLanAddress listenport=22" in script
    assert "connectaddress=$proxyTarget connectport=22" in script
    assert "@('127.0.0.1', $LaptopTailscaleAddress)" in script
    assert "wsl.exe -e sh -lc 'hostname -I'" in script
    assert "status=1" in script
    assert "Set-Content -LiteralPath $LogPath" in script
    assert "Windows OpenSSH port 2222 was not changed." in script


def test_windows_firewall_passes_validated_config_addresses_to_powershell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    monkeypatch.setattr(
        machine_b.shutil,
        "which",
        lambda name: f"/usr/bin/{name}",
    )
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0].endswith("wslpath"):
            return subprocess.CompletedProcess(command, 0, "C:\\commissioner\\firewall.ps1\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(machine_b.subprocess, "run", run)
    assert machine_b.windows_firewall(config) == 0
    assert calls[1][-8:] == [
        "-LaptopLanAddress",
        LAPTOP_LAN,
        "-LaptopTailscaleAddress",
        "100.64.0.1",
        "-MachineBLanAddress",
        MACHINE_B_LAN,
        "-MachineBTailscaleAddress",
        "100.64.0.2",
    ]


def test_legacy_tailscale_only_policy_is_removed_after_firewall_is_established() -> None:
    playbook = (machine_b.REPO / "ops/machine-b/apply.yml").read_text(encoding="utf-8")
    firewall = playbook.index("- name: Enable UFW")
    remove = playbook.index("- name: Remove the superseded Tailscale-only SSH policy")
    assert firewall < remove
    assert "path: /etc/ssh/sshd_config.d/00-tailscale-only.conf\n        state: absent" in playbook
    assert (
        "path: /etc/systemd/system/ssh.socket.d/tailscale-only.conf\n        state: absent"
        in playbook
    )
    assert "daemon_reload: true" in playbook
    assert "name: ssh.socket\n        state: restarted" in playbook
    assert "sudo -n /usr/sbin/sshd -T" in machine_b.REMOTE_AUDIT


def test_bootstrap_pull_exchanges_only_public_material_and_installs_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_config(tmp_path)
    (tmp_path / "machine-b-trust.json").unlink()
    bravo_key, bravo_fingerprint = public_key(1, "bravo")
    laptop_key, _ = public_key(2, "laptop")
    monkeypatch.setattr(machine_b, "LOCAL_HOST_PUBLIC_KEY", tmp_path / "laptop-host.pub")
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "laptop-host.pub").write_text(f"{laptop_key}\n", encoding="utf-8")
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_CLIENT", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    monkeypatch.setattr(
        machine_b,
        "_op_fields",
        lambda _config: (
            "item-id",
            {
                "schema_version": "1",
                "bravo_host_public_key": bravo_key,
                "bravo_host_fingerprint": bravo_fingerprint,
            },
        ),
    )
    published: list[dict[str, str]] = []

    def capture(_config: object, fields: dict[str, str], *, item_id: str | None = None) -> str:
        published.append(fields)
        return item_id or "item-id"

    monkeypatch.setattr(machine_b, "_op_upsert", capture)
    config = machine_b.load_config(path, require_trust=False)
    assert machine_b.bootstrap_pull(config) == 0
    assert set(published[0]) == {
        "schema_version",
        "laptop_host_public_key",
        "laptop_host_fingerprint",
        "laptop_to_bravo_public_key",
    }
    assert "PRIVATE KEY" not in json.dumps(published)
    loaded = machine_b.load_config(path)
    assert loaded.trust is not None
    assert loaded.trust.bravo_host_fingerprint == bravo_fingerprint
    known_hosts = (tmp_path / "known_hosts.machine-b").read_text(encoding="utf-8")
    assert f"bravo-lan,{MACHINE_B_LAN},bravo-tail,100.64.0.2" in known_hosts
    assert "StrictHostKeyChecking yes" in (
        tmp_path / ".ssh" / "config.d" / "arma-cti-machine-b"
    ).read_text(encoding="utf-8")


def test_bootstrap_pull_refuses_a_remote_session_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_config(tmp_path)
    (tmp_path / "machine-b-trust.json").unlink()
    monkeypatch.setenv("SSH_CONNECTION", "source destination")
    config = machine_b.load_config(path, require_trust=False)
    with pytest.raises(machine_b.BootstrapError, match="local console"):
        machine_b.bootstrap_pull(config)
    assert not (tmp_path / "known_hosts.machine-b").exists()


def test_bootstrap_publish_creates_then_idempotently_updates_public_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bravo_key, bravo_fingerprint = public_key(4, "bravo")
    host_key = tmp_path / "host.pub"
    host_key.write_text(f"{bravo_key}\n", encoding="utf-8")
    monkeypatch.setattr(machine_b, "LOCAL_HOST_PUBLIC_KEY", host_key)
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_CLIENT", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    item_ids: list[str | None] = [None, "created-item"]
    calls: list[list[str]] = []

    def item_id(_vault: str, _item: str, _account: str) -> str | None:
        return item_ids.pop(0)

    def run(_account: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        output = '{"id":"created-item"}' if arguments[1] == "create" else ""
        return subprocess.CompletedProcess(arguments, 0, output, "")

    monkeypatch.setattr(machine_b, "_op_item_id", item_id)
    monkeypatch.setattr(machine_b, "_op_run", run)
    assert machine_b.bootstrap_publish("Automation", "bootstrap", "") == 0
    assert machine_b.bootstrap_publish("Automation", "bootstrap", "") == 0
    assert calls[0][0:2] == ["item", "create"]
    assert calls[1][0:3] == ["item", "edit", "created-item"]
    for call in calls:
        joined = " ".join(call)
        assert f"bravo_host_public_key[text]={bravo_key}" in joined
        assert f"bravo_host_fingerprint[text]={bravo_fingerprint}" in joined
        assert "PRIVATE KEY" not in joined


def test_known_op_item_id_bypasses_vault_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = machine_b.load_config(write_config(tmp_path)).onepassword
    monkeypatch.setattr(
        machine_b,
        "_op_item_id",
        lambda *_args: pytest.fail("known item ID must bypass item list"),
    )
    calls: list[list[str]] = []

    def run(_account: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(machine_b, "_op_run", run)
    result = machine_b._op_upsert(  # noqa: SLF001 — directly tests the op argv boundary.
        config, {"schema_version": "1"}, item_id="known-id"
    )
    assert result == "known-id"
    assert calls == [
        [
            "item",
            "edit",
            "known-id",
            "--vault",
            "Automation",
            "schema_version[text]=1",
        ]
    ]


def test_op_timeout_is_reported_as_a_bootstrap_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(machine_b, "_op_base", lambda _account: ["/usr/bin/op"])

    def timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(["/usr/bin/op"], 30)

    monkeypatch.setattr(machine_b.subprocess, "run", timeout)
    with pytest.raises(machine_b.BootstrapError, match="unlock the laptop desktop app"):
        machine_b._op_run(  # noqa: SLF001 — directly tests the op timeout translation.
            "", ["item", "edit", "known-id"]
        )


def test_reverse_public_key_mirror_defers_an_op_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = machine_b.load_config(write_config(tmp_path))
    assert config.trust is not None

    def fail(*_args: object, **_kwargs: object) -> str:
        message = "desktop integration unavailable"
        raise machine_b.BootstrapError(message)

    monkeypatch.setattr(machine_b, "_op_upsert", fail)
    assert not machine_b._mirror_reverse_public_key(  # noqa: SLF001 — tests deferred mirror.
        config.onepassword,
        config.trust,
        "ssh-ed25519 public",
    )
    assert "1Password public-key mirror deferred" in capsys.readouterr().err


def test_bootstrap_authorize_installs_one_bounded_public_key_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_config(tmp_path)
    (tmp_path / "machine-b-trust.json").unlink()
    bravo_key, bravo_fingerprint = public_key(4, "bravo")
    laptop_host_key, laptop_host_fingerprint = public_key(5, "laptop")
    automation_key, _ = public_key(6, "arma-cti laptop to bravo")
    host_key = tmp_path / "host.pub"
    host_key.write_text(f"{bravo_key}\n", encoding="utf-8")
    monkeypatch.setattr(machine_b, "LOCAL_HOST_PUBLIC_KEY", host_key)
    home = tmp_path / ADMIN_USER
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_CLIENT", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    monkeypatch.setattr(
        machine_b,
        "_op_fields",
        lambda _config: (
            "item-id",
            {
                "schema_version": "1",
                "bravo_host_public_key": bravo_key,
                "bravo_host_fingerprint": bravo_fingerprint,
                "laptop_host_public_key": laptop_host_key,
                "laptop_host_fingerprint": laptop_host_fingerprint,
                "laptop_to_bravo_public_key": automation_key,
            },
        ),
    )
    ssh_directory = home / ".ssh"
    ssh_directory.mkdir()
    authorized_keys = ssh_directory / "authorized_keys"
    authorized_keys.write_text("# existing recovery material\n", encoding="utf-8")
    config = machine_b.load_config(path, require_trust=False)

    assert machine_b.bootstrap_authorize(config) == 0
    assert machine_b.bootstrap_authorize(config) == 0

    rendered = authorized_keys.read_text(encoding="utf-8")
    assert rendered.count(machine_b.ADMIN_KEY_BLOCK_BEGIN) == 1
    assert rendered.count(machine_b.ADMIN_KEY_BLOCK_END) == 1
    assert rendered.startswith("# existing recovery material\n# BEGIN")
    assert f'from="{LAPTOP_LAN},100.64.0.1",restrict ssh-ed25519 ' in rendered
    assert automation_key in rendered
    assert "PRIVATE KEY" not in rendered
    assert authorized_keys.stat().st_mode & 0o777 == 0o600


def test_bootstrap_authorize_rejects_a_different_local_bravo_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_config(tmp_path)
    (tmp_path / "machine-b-trust.json").unlink()
    local_key, _ = public_key(3, "local")
    published_key, published_fingerprint = public_key(4, "published")
    laptop_key, laptop_fingerprint = public_key(5, "laptop")
    automation_key, _ = public_key(6, "automation")
    host_key = tmp_path / "host.pub"
    host_key.write_text(f"{local_key}\n", encoding="utf-8")
    monkeypatch.setattr(machine_b, "LOCAL_HOST_PUBLIC_KEY", host_key)
    home = tmp_path / ADMIN_USER
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_CLIENT", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    monkeypatch.setattr(
        machine_b,
        "_op_fields",
        lambda _config: (
            "item-id",
            {
                "schema_version": "1",
                "bravo_host_public_key": published_key,
                "bravo_host_fingerprint": published_fingerprint,
                "laptop_host_public_key": laptop_key,
                "laptop_host_fingerprint": laptop_fingerprint,
                "laptop_to_bravo_public_key": automation_key,
            },
        ),
    )
    config = machine_b.load_config(path, require_trust=False)

    with pytest.raises(machine_b.BootstrapError, match="does not match this local console"):
        machine_b.bootstrap_authorize(config)
    assert not (home / ".ssh" / "authorized_keys").exists()


def test_native_op_is_preferred_inside_wsl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(machine_b, "_is_wsl", lambda: True)
    monkeypatch.setattr(
        machine_b.shutil,
        "which",
        lambda command: f"/mnt/c/Windows/{command}" if command in {"op", "op.exe"} else None,
    )
    assert machine_b.op_executable() == "/mnt/c/Windows/op"
