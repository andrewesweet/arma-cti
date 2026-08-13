"""Commission and verify the dedicated Ubuntu Arma host (issues #52-#54)."""

from __future__ import annotations

import argparse
import base64
import binascii
import dataclasses
import enum
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from pathlib import Path
from typing import Final, cast

DEFAULT_CONFIG: Final = Path.home() / ".arma-cti" / "machine-b.toml"
REPO: Final = Path(__file__).resolve().parents[1]
LOCAL_HOST_PUBLIC_KEY: Final = Path("/etc/ssh/ssh_host_ed25519_key.pub")
MAC_PATTERN: Final = re.compile(r"^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
SSH_ALIAS_PATTERN: Final = re.compile(r"^[A-Za-z0-9_.-]+$")
INTERFACE_PATTERN: Final = re.compile(r"^[A-Za-z0-9_.:-]+$")
USER_PATTERN: Final = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
PROTON_VERSION: Final = "10.0-4"
SERVER_APP_ID: Final = 233780
CLIENT_APP_ID: Final = 107410
STEAM_LIBRARY_MOUNT: Final = Path("/home/cti/SteamLibrary")
STEAM_LIBRARY_ROOT: Final = STEAM_LIBRARY_MOUNT / "SteamLibrary"
SSH_DEFAULT_PORT: Final = 22
MAX_SLOTS: Final = 3
MAX_PORT: Final = 65535
SUSPEND_TARGET_COUNT: Final = 4
MAX_WAKE_WAIT: Final = 900
WINDOWS_FIREWALL_WAIT: Final = 300
AUDIT_ROW_FIELDS: Final = 3
PUBLIC_KEY_MIN_PARTS: Final = 2
PUBLIC_KEY_COMMENT_PARTS: Final = 3
ED25519_BLOB_BYTES: Final = 51
SENSITIVE_KEY: Final = re.compile(r"password|secret|token|credential|sentry", re.IGNORECASE)
PRIVATE_KEY_MARKER: Final = "PRIVATE KEY-----"
ADMIN_KEY_BLOCK_BEGIN: Final = "# BEGIN arma-cti machine-b bootstrap"
ADMIN_KEY_BLOCK_END: Final = "# END arma-cti machine-b bootstrap"


class ConfigurationError(ValueError):
    """The external, non-secret commissioning configuration is invalid."""


class BootstrapError(RuntimeError):
    """The authenticated public-material exchange could not be completed."""


@dataclasses.dataclass(frozen=True)
class HostConfig:
    """Non-secret identity, addressing, and capacity of bravo."""

    logical_name: str
    system_hostname: str
    lan_address: ipaddress.IPv4Address
    tailscale_address: ipaddress.IPv4Address
    wired_mac: str
    wired_interface: str
    network_connection: str
    ssh_alias_lan: str
    ssh_alias_tail: str
    admin_ssh_target: str
    admin_user: str
    runtime_user: str = "cti"
    slots: int = 3
    headed_client: bool = True
    human: bool = False


@dataclasses.dataclass(frozen=True)
class LaptopConfig:
    """Non-secret facts for the initiating laptop WSL endpoint."""

    lan_address: ipaddress.IPv4Address
    tailscale_address: ipaddress.IPv4Address
    wsl_proxy_source: ipaddress.IPv4Address
    wired_mac: str
    ssh_port: int
    tailscale_ssh_port: int
    peer_user: str
    identity_to_bravo: Path
    ssh_alias_lan: str = "cti-laptop-lan"
    ssh_alias_tail: str = "cti-laptop-tail"


@dataclasses.dataclass(frozen=True)
class OnePasswordConfig:
    """Location of public bootstrap material and its local verified cache."""

    vault: str
    item: str
    account: str
    trust_file: Path
    known_hosts_file: Path


@dataclasses.dataclass(frozen=True)
class TrustMaterial:
    """Public keys fetched from the pre-existing trusted 1Password channel."""

    item_id: str
    bravo_host_public_key: str
    bravo_host_fingerprint: str
    laptop_host_public_key: str
    laptop_host_fingerprint: str
    laptop_to_bravo_public_key: str


@dataclasses.dataclass(frozen=True)
class SteamConfig:
    """Fixed Steam applications, filesystem mount, and registered library root."""

    server_app_id: int = SERVER_APP_ID
    client_app_id: int = CLIENT_APP_ID
    proton_version: str = PROTON_VERSION
    server_install: Path = Path("/home/cti/arma3server")
    library_uuid: str = ""
    library_mount: Path = STEAM_LIBRARY_MOUNT
    library_root: Path = STEAM_LIBRARY_ROOT
    client_install: Path = STEAM_LIBRARY_ROOT / "steamapps/common/Arma 3"


@dataclasses.dataclass(frozen=True)
class MachineBConfig:
    """Complete external commissioning contract."""

    host: HostConfig
    laptop: LaptopConfig
    onepassword: OnePasswordConfig
    steam: SteamConfig
    wake_broadcast: ipaddress.IPv4Address
    trust: TrustMaterial | None


class FailureCode(enum.StrEnum):
    """Stable discrepancy classes emitted by ``verify``."""

    OS = "os"
    IDENTITY = "identity"
    SSH = "ssh"
    FIREWALL = "firewall"
    POWER = "power"
    GPU = "gpu"
    STEAM = "steam"
    ENGINE = "engine"
    PORT = "port"
    CLIENT = "client"


@dataclasses.dataclass(frozen=True)
class Failure:
    """One typed verification discrepancy."""

    code: FailureCode
    detail: str


def _table(raw: dict[str, object], name: str, allowed: set[str]) -> dict[str, object]:
    value = raw.get(name)
    if not isinstance(value, dict):
        msg = f"missing [{name}] table"
        raise ConfigurationError(msg)
    table = cast("dict[str, object]", value)
    unknown = set(table) - allowed
    if unknown:
        msg = f"unknown [{name}] key(s): {', '.join(sorted(unknown))}"
        raise ConfigurationError(msg)
    return table


def _text(table: dict[str, object], key: str, *, default: str | None = None) -> str:
    value = table.get(key, default)
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(character in value for character in ("\n", "\r", "\t", "\0"))
    ):
        msg = f"{key} must be a non-empty string"
        raise ConfigurationError(msg)
    return value.strip()


def _boolean(table: dict[str, object], key: str, *, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        msg = f"{key} must be true or false"
        raise ConfigurationError(msg)
    return value


def _optional_text(table: dict[str, object], key: str) -> str:
    if key not in table:
        return ""
    return _text(table, key)


def _integer(table: dict[str, object], key: str, *, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{key} must be an integer"
        raise ConfigurationError(msg)
    return value


def _ipv4(table: dict[str, object], key: str) -> ipaddress.IPv4Address:
    value = _text(table, key)
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        msg = f"{key} is not an IP address: {value}"
        raise ConfigurationError(msg) from exc
    if not isinstance(address, ipaddress.IPv4Address):
        msg = f"{key} must be IPv4: {value}"
        raise ConfigurationError(msg)
    return address


def _alias(value: str, key: str) -> str:
    if not SSH_ALIAS_PATTERN.fullmatch(value):
        msg = f"{key} is not a bounded SSH alias: {value}"
        raise ConfigurationError(msg)
    return value


def _path(value: str, key: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        msg = f"{key} must be an absolute path"
        raise ConfigurationError(msg)
    return path


def _filesystem_uuid(value: str, key: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        msg = f"{key} must be a canonical filesystem UUID"
        raise ConfigurationError(msg) from exc
    canonical = str(parsed)
    if value != canonical:
        msg = f"{key} must be the lowercase canonical UUID {canonical}"
        raise ConfigurationError(msg)
    return canonical


def load_config(path: Path = DEFAULT_CONFIG, *, require_trust: bool = True) -> MachineBConfig:
    """Load and strictly validate the external commissioning values."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"cannot read {path}: {exc}"
        raise ConfigurationError(msg) from exc
    except tomllib.TOMLDecodeError as exc:
        msg = f"invalid TOML in {path}: {exc}"
        raise ConfigurationError(msg) from exc
    allowed_top = {"host", "laptop", "onepassword", "steam", "wake_broadcast"}
    if set(raw) - allowed_top:
        unknown = set(raw) - allowed_top
        msg = f"unknown top-level key(s): {', '.join(sorted(unknown))}"
        raise ConfigurationError(msg)

    host_raw = _table(
        raw,
        "host",
        {
            "logical_name",
            "system_hostname",
            "lan_address",
            "tailscale_address",
            "wired_mac",
            "wired_interface",
            "network_connection",
            "ssh_alias_lan",
            "ssh_alias_tail",
            "admin_ssh_target",
            "admin_user",
            "runtime_user",
            "slots",
            "headed_client",
            "human",
        },
    )
    laptop_raw = _table(
        raw,
        "laptop",
        {
            "lan_address",
            "tailscale_address",
            "wsl_proxy_source",
            "wired_mac",
            "ssh_port",
            "tailscale_ssh_port",
            "peer_user",
            "identity_to_bravo",
            "ssh_alias_lan",
            "ssh_alias_tail",
        },
    )
    onepassword_raw = _table(
        raw,
        "onepassword",
        {"vault", "item", "account", "trust_file", "known_hosts_file"},
    )
    steam_raw = _table(
        raw,
        "steam",
        {
            "server_app_id",
            "client_app_id",
            "proton_version",
            "server_install",
            "library_uuid",
            "library_mount",
            "library_root",
            "client_install",
        },
    )

    wired_mac = _text(host_raw, "wired_mac").lower()
    laptop_mac = _text(laptop_raw, "wired_mac").lower()
    for key, value in (("host.wired_mac", wired_mac), ("laptop.wired_mac", laptop_mac)):
        if not MAC_PATTERN.fullmatch(value):
            msg = f"{key} is not a MAC address: {value}"
            raise ConfigurationError(msg)

    slots = _integer(host_raw, "slots", default=3)
    if not 1 <= slots <= MAX_SLOTS:
        msg = "host.slots must fit Machine B's measured slot geometry (1..3)"
        raise ConfigurationError(msg)
    ssh_port = _integer(laptop_raw, "ssh_port", default=2222)
    tail_port = _integer(laptop_raw, "tailscale_ssh_port", default=2222)
    for key, port in (("laptop.ssh_port", ssh_port), ("laptop.tailscale_ssh_port", tail_port)):
        if not 1 <= port <= MAX_PORT:
            msg = f"{key} is outside 1..65535"
            raise ConfigurationError(msg)

    proton = _text(steam_raw, "proton_version", default=PROTON_VERSION)
    if proton != PROTON_VERSION:
        msg = f"steam.proton_version must remain pinned to {PROTON_VERSION}, got {proton}"
        raise ConfigurationError(msg)

    host = HostConfig(
        logical_name=_text(host_raw, "logical_name"),
        system_hostname=_text(host_raw, "system_hostname"),
        lan_address=_ipv4(host_raw, "lan_address"),
        tailscale_address=_ipv4(host_raw, "tailscale_address"),
        wired_mac=wired_mac,
        wired_interface=_text(host_raw, "wired_interface"),
        network_connection=_text(host_raw, "network_connection"),
        ssh_alias_lan=_alias(_text(host_raw, "ssh_alias_lan"), "host.ssh_alias_lan"),
        ssh_alias_tail=_alias(_text(host_raw, "ssh_alias_tail"), "host.ssh_alias_tail"),
        admin_ssh_target=_text(host_raw, "admin_ssh_target"),
        admin_user=_text(host_raw, "admin_user"),
        runtime_user=_text(host_raw, "runtime_user", default="cti"),
        slots=slots,
        headed_client=_boolean(host_raw, "headed_client", default=True),
        human=_boolean(host_raw, "human", default=False),
    )
    if (
        host.logical_name != "bravo"
        or host.system_hostname != "arma-cti-b"
        or host.runtime_user != "cti"
        or not host.headed_client
        or host.human
    ):
        msg = "Machine B identity/capability is fixed: bravo, arma-cti-b, cti runtime, headed tier"
        raise ConfigurationError(msg)
    if not USER_PATTERN.fullmatch(host.admin_user) or host.admin_user in {
        "root",
        host.runtime_user,
    }:
        msg = "host.admin_user must name a distinct non-root POSIX account"
        raise ConfigurationError(msg)
    if not INTERFACE_PATTERN.fullmatch(host.wired_interface):
        msg = f"host.wired_interface is invalid: {host.wired_interface}"
        raise ConfigurationError(msg)
    if not SSH_ALIAS_PATTERN.fullmatch(host.admin_ssh_target):
        msg = f"host.admin_ssh_target is not a host or alias: {host.admin_ssh_target}"
        raise ConfigurationError(msg)
    laptop = LaptopConfig(
        lan_address=_ipv4(laptop_raw, "lan_address"),
        tailscale_address=_ipv4(laptop_raw, "tailscale_address"),
        wsl_proxy_source=_ipv4(laptop_raw, "wsl_proxy_source"),
        wired_mac=laptop_mac,
        ssh_port=ssh_port,
        tailscale_ssh_port=tail_port,
        peer_user=_text(laptop_raw, "peer_user", default="cti-peer"),
        identity_to_bravo=_path(_text(laptop_raw, "identity_to_bravo"), "laptop.identity_to_bravo"),
        ssh_alias_lan=_alias(
            _text(laptop_raw, "ssh_alias_lan", default="cti-laptop-lan"),
            "laptop.ssh_alias_lan",
        ),
        ssh_alias_tail=_alias(
            _text(laptop_raw, "ssh_alias_tail", default="cti-laptop-tail"),
            "laptop.ssh_alias_tail",
        ),
    )
    onepassword = OnePasswordConfig(
        vault=_text(onepassword_raw, "vault"),
        item=_text(onepassword_raw, "item"),
        account=_optional_text(onepassword_raw, "account"),
        trust_file=_path(_text(onepassword_raw, "trust_file"), "onepassword.trust_file"),
        known_hosts_file=_path(
            _text(onepassword_raw, "known_hosts_file"), "onepassword.known_hosts_file"
        ),
    )
    steam = SteamConfig(
        server_app_id=_integer(steam_raw, "server_app_id", default=SERVER_APP_ID),
        client_app_id=_integer(steam_raw, "client_app_id", default=CLIENT_APP_ID),
        proton_version=proton,
        server_install=_path(
            _text(steam_raw, "server_install", default="/home/cti/arma3server"),
            "steam.server_install",
        ),
        library_uuid=_filesystem_uuid(_text(steam_raw, "library_uuid"), "steam.library_uuid"),
        library_mount=_path(
            _text(steam_raw, "library_mount", default=str(STEAM_LIBRARY_MOUNT)),
            "steam.library_mount",
        ),
        library_root=_path(
            _text(steam_raw, "library_root", default=str(STEAM_LIBRARY_ROOT)),
            "steam.library_root",
        ),
        client_install=_path(
            _text(
                steam_raw,
                "client_install",
                default=str(STEAM_LIBRARY_ROOT / "steamapps/common/Arma 3"),
            ),
            "steam.client_install",
        ),
    )
    if steam.server_app_id != SERVER_APP_ID or steam.client_app_id != CLIENT_APP_ID:
        msg = "Steam application IDs are fixed: server 233780, client 107410"
        raise ConfigurationError(msg)
    expected_library = Path(f"/home/{host.runtime_user}/SteamLibrary")
    expected_root = expected_library / "SteamLibrary"
    expected_client = expected_root / "steamapps/common/Arma 3"
    if (
        steam.library_mount != expected_library
        or steam.library_root != expected_root
        or steam.client_install != expected_client
    ):
        msg = (
            "Machine B Steam paths are fixed: filesystem mount /home/cti/SteamLibrary, "
            "registered library root beneath it, and client beneath that root's steamapps"
        )
        raise ConfigurationError(msg)

    wake_value = raw.get("wake_broadcast", "255.255.255.255")
    if not isinstance(wake_value, str):
        msg = "wake_broadcast must be an IPv4 string"
        raise ConfigurationError(msg)
    try:
        wake_broadcast = ipaddress.IPv4Address(wake_value)
    except ipaddress.AddressValueError as exc:
        msg = f"wake_broadcast is not IPv4: {wake_value}"
        raise ConfigurationError(msg) from exc
    trust = _load_trust(onepassword) if require_trust else None
    return MachineBConfig(
        host=host,
        laptop=laptop,
        onepassword=onepassword,
        steam=steam,
        wake_broadcast=wake_broadcast,
        trust=trust,
    )


def redact(value: object, *, key: str = "") -> object:
    """Remove secret-shaped values before inventory reaches stdout or disk."""
    if SENSITIVE_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(item_key): redact(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, key=key) for item in value]
    if isinstance(value, str) and PRIVATE_KEY_MARKER in value:
        return "<redacted>"
    return value


REMOTE_AUDIT: Final = r"""
set -uo pipefail
emit() {
    key="$1"
    shift
    value="$(bash -lc "$*" 2>&1)"
    status=$?
    encoded="$(printf '%s' "$value" | base64 -w0)"
    printf '%s\t%s\t%s\n' "$key" "$status" "$encoded"
}
emit hostname 'hostnamectl --static'
emit os_version '. /etc/os-release && printf "%s" "$VERSION_ID"'
emit os_pretty '. /etc/os-release && printf "%s" "$PRETTY_NAME"'
emit kernel 'uname -r'
emit memory_bytes "awk '/^MemTotal:/ { print \$2 * 1024; exit }' /proc/meminfo"
emit root_free_bytes "df -B1 --output=avail / | tail -1 | tr -d ' '"
emit audit_identity 'id -un'
emit runtime_identity 'id cti'
emit admin_identity 'id __ADMIN_USER__'
emit lan_addresses "ip -4 -o address show scope global | awk '{print \$4}'"
emit wired_mac 'cat /sys/class/net/__INTERFACE__/address'
emit nm_wol "nmcli -g 802-3-ethernet.wake-on-lan connection show '__CONNECTION__'"
emit ethtool 'sudo -n /usr/sbin/ethtool __INTERFACE__'
emit tailscale_ip 'tailscale ip -4'
emit sshd_dropin 'cat /etc/ssh/sshd_config.d/60-arma-cti.conf'
emit sshd_effective 'sudo -n /usr/sbin/sshd -T'
emit ufw 'sudo -n /usr/sbin/ufw status verbose'
emit suspend_targets \
    'systemctl is-enabled sleep.target suspend.target hibernate.target hybrid-sleep.target'
emit gdm 'cat /etc/gdm3/custom.conf'
emit gdm_config_loaded \
    'started=$(systemctl show gdm -p ActiveEnterTimestamp --value) &&
        test -n "$started" &&
        test "$(date -d "$started" +%s)" -ge "$(stat -c %Y /etc/gdm3/custom.conf)" &&
        printf loaded'
emit graphical_session \
    'display=$(loginctl show-user cti -p Display --value) &&
        test -n "$display" &&
        type=$(loginctl show-session "$display" -p Type --value) &&
        printf "%s %s" "$display" "$type"'
emit gpu 'nvidia-smi --query-gpu=name,driver_version --format=csv,noheader'
emit vulkan 'vulkaninfo --summary'
emit steamcmd 'command -v steamcmd'
emit steam 'command -v steam'
emit server_binary 'test -x __SERVER_INSTALL__/arma3server_x64 && printf present'
emit server_manifest 'cat __SERVER_INSTALL__/steamapps/appmanifest_233780.acf'
emit steam_library \
    'live_uuid=$(findmnt --mountpoint __STEAM_LIBRARY__ --noheadings --output UUID) &&
        test "$live_uuid" = "__STEAM_LIBRARY_UUID__" &&
        test "$(findmnt --mountpoint __STEAM_LIBRARY__ --noheadings --output FSTYPE)" = ext4 &&
        live_options=$(findmnt --mountpoint __STEAM_LIBRARY__ --noheadings --output OPTIONS) &&
        case ",$live_options," in *,rw,*);; *) exit 1;; esac &&
        case ",$live_options," in *,nosuid,*);; *) exit 1;; esac &&
        case ",$live_options," in *,nodev,*);; *) exit 1;; esac &&
        case ",$live_options," in *,noexec,*) exit 1;; *) :;; esac &&
        test -w __STEAM_LIBRARY__ &&
        test "$(stat -c %U:%G __STEAM_LIBRARY__)" = cti:cti &&
        test "$(findmnt --fstab --mountpoint __STEAM_LIBRARY__ --noheadings --output SOURCE)" = \
            "UUID=__STEAM_LIBRARY_UUID__" &&
        printf "uuid=%s mount=__STEAM_LIBRARY__ type=ext4 owner=cti:cti options=%s" \
            "$live_uuid" "$live_options"'
emit steam_library_root \
    'test -d "__STEAM_LIBRARY_ROOT__" &&
        test -w "__STEAM_LIBRARY_ROOT__" &&
        test "$(findmnt --target "__STEAM_LIBRARY_ROOT__" --raw --noheadings --output TARGET)" = \
            "__STEAM_LIBRARY__" &&
        printf "mount=__STEAM_LIBRARY__ root=__STEAM_LIBRARY_ROOT__"'
emit client_manifest 'cat "__STEAM_LIBRARY_ROOT__/steamapps/appmanifest_107410.acf"'
emit client_binary 'test -f "__CLIENT_INSTALL__/arma3_x64.exe" && printf present'
emit proton_version 'cat "__STEAM_LIBRARY_ROOT__/steamapps/common/Proton 10.0/version"'
emit steam_compat_config \
    'grep -A8 107410 /home/cti/.steam/steam/config/config.vdf |
        grep -q proton_10 && printf 107410=proton_10'
emit listeners 'ss -H -lntup'
emit client_service \
    'test -f /home/cti/.config/systemd/user/cti-arma-client.service && printf installed'
emit session_type 'loginctl show-user cti -p Display -p State -p Linger'
emit host_ed25519_fingerprint \
    "ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256 | awk '{print \$2}'"
"""


def remote_audit_script(config: MachineBConfig) -> str:
    """Render the read-only remote inventory script from validated host values."""
    replacements = {
        "__ADMIN_USER__": config.host.admin_user,
        "__INTERFACE__": config.host.wired_interface,
        "__CONNECTION__": config.host.network_connection.replace("'", "'\\''"),
        "__SERVER_INSTALL__": str(config.steam.server_install).replace("'", "'\\''"),
        "__STEAM_LIBRARY_UUID__": config.steam.library_uuid,
        "__STEAM_LIBRARY__": str(config.steam.library_mount),
        "__STEAM_LIBRARY_ROOT__": str(config.steam.library_root),
        "__CLIENT_INSTALL__": str(config.steam.client_install),
    }
    script = REMOTE_AUDIT
    for needle, replacement in replacements.items():
        script = script.replace(needle, replacement)
    return script


def _ssh(
    alias: str,
    *arguments: str,
    timeout: int = 20,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        "ssh",
        "-T",
        "-oBatchMode=yes",
        "-oStrictHostKeyChecking=yes",
        "-oConnectTimeout=8",
        "-oServerAliveInterval=5",
        "-oServerAliveCountMax=2",
        "-oClearAllForwardings=yes",
        alias,
        *arguments,
    ]
    try:
        return subprocess.run(  # noqa: S603 — fixed ssh binary and bounded validated alias
            command,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
        )
        return subprocess.CompletedProcess(command, 124, stdout or "", "SSH deadline expired")


def bravo_ssh_target(config: MachineBConfig, alias: str) -> str:
    """Pin operational B connections to the non-admin runtime identity."""
    if alias not in {config.host.ssh_alias_lan, config.host.ssh_alias_tail}:
        msg = f"not a configured bravo alias: {alias}"
        raise ConfigurationError(msg)
    return f"{config.host.runtime_user}@{alias}"


def collect_inventory(config: MachineBConfig) -> dict[str, object]:
    """Collect a read-only, line-framed inventory over the primary LAN alias."""
    bravo_lan = bravo_ssh_target(config, config.host.ssh_alias_lan)
    bravo_tail = bravo_ssh_target(config, config.host.ssh_alias_tail)
    result = _ssh(
        bravo_lan,
        "bash",
        "-s",
        timeout=45,
        input_text=remote_audit_script(config),
    )
    inventory: dict[str, object] = {
        "schema": 1,
        "logical_host": config.host.logical_name,
        "transport": {
            "alias": config.host.ssh_alias_lan,
            "target": bravo_lan,
            "status": result.returncode,
            "stderr": result.stderr.strip(),
        },
        "facts": {},
        "paths": {},
    }
    facts: dict[str, object] = {}
    inventory["facts"] = facts
    if result.returncode != 0:
        return inventory
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != AUDIT_ROW_FIELDS:
            facts["audit_protocol"] = {"status": 1, "value": "malformed remote row"}
            continue
        key, status_text, encoded = parts
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8", errors="replace")
            status = int(status_text)
        except (ValueError, binascii.Error):
            facts[key] = {"status": 1, "value": "malformed remote value"}
            continue
        facts[key] = {"status": status, "value": decoded.strip()}
    reverse_ufw = _ssh(
        bravo_lan,
        "ssh",
        config.laptop.ssh_alias_lan,
        "sudo",
        "-n",
        "/usr/sbin/ufw",
        "status",
        "verbose",
    )
    laptop_to_bravo_tail = _ssh(bravo_tail, "true")
    bravo_to_laptop_lan = _ssh(bravo_lan, "ssh", config.laptop.ssh_alias_lan, "true")
    bravo_to_laptop_tail = _ssh(bravo_tail, "ssh", config.laptop.ssh_alias_tail, "true")
    path_results = {
        "laptop_to_bravo_lan": result,
        "laptop_to_bravo_tail": laptop_to_bravo_tail,
        "bravo_to_laptop_lan": bravo_to_laptop_lan,
        "bravo_to_laptop_tail": bravo_to_laptop_tail,
    }
    inventory["paths"] = {name: path.returncode for name, path in path_results.items()}
    inventory["path_errors"] = {
        name: path.stderr.strip() for name, path in path_results.items() if path.returncode != 0
    }
    inventory["laptop_firewall"] = {
        "status": reverse_ufw.returncode,
        "value": reverse_ufw.stdout.strip(),
    }
    return inventory


def _fact(inventory: dict[str, object], key: str) -> tuple[int, str]:
    facts = inventory.get("facts", {})
    if not isinstance(facts, dict):
        return 1, ""
    row = facts.get(key, {})
    if not isinstance(row, dict):
        return 1, ""
    status = row.get("status", 1)
    value = row.get("value", "")
    return (status if isinstance(status, int) else 1, value if isinstance(value, str) else "")


def steam_mount_options_are_safe(options: str) -> bool:
    """Accept implicit execution, while rejecting an explicit ``noexec`` mount."""
    observed = {option.strip() for option in options.split(",") if option.strip()}
    return {"rw", "nosuid", "nodev"}.issubset(observed) and "noexec" not in observed


def verify_inventory(config: MachineBConfig, inventory: dict[str, object]) -> list[Failure]:
    """Map every commissioning discrepancy onto the stable typed vocabulary."""
    failures: list[Failure] = []

    def require(code: FailureCode, condition: bool, detail: str) -> None:
        if not condition:
            failures.append(Failure(code, detail))

    transport = inventory.get("transport", {})
    transport_status = transport.get("status", 1) if isinstance(transport, dict) else 1
    if transport_status != 0:
        return [Failure(FailureCode.SSH, "primary LAN SSH transport is unavailable")]
    paths = inventory.get("paths", {})
    if isinstance(paths, dict):
        for name in (
            "laptop_to_bravo_lan",
            "laptop_to_bravo_tail",
            "bravo_to_laptop_lan",
            "bravo_to_laptop_tail",
        ):
            require(
                FailureCode.SSH,
                paths.get(name) == 0,
                f"non-interactive SSH path failed: {name}",
            )

    _, os_version = _fact(inventory, "os_version")
    _, hostname = _fact(inventory, "hostname")
    _, audit_identity = _fact(inventory, "audit_identity")
    _, runtime_identity = _fact(inventory, "runtime_identity")
    admin_status, admin_identity = _fact(inventory, "admin_identity")
    require(
        FailureCode.OS,
        os_version == "24.04",
        f"expected Ubuntu 24.04, observed {os_version or 'unknown'}",
    )
    require(
        FailureCode.IDENTITY,
        hostname == config.host.system_hostname,
        f"expected hostname {config.host.system_hostname}, observed {hostname or 'unknown'}",
    )
    require(
        FailureCode.IDENTITY,
        audit_identity == config.host.runtime_user,
        f"read-only audit did not run as the {config.host.runtime_user} runtime identity",
    )
    require(
        FailureCode.IDENTITY,
        runtime_identity.startswith("uid=") and "sudo" not in runtime_identity,
        f"{config.host.runtime_user} identity is absent or has administrative group membership",
    )
    require(
        FailureCode.IDENTITY,
        admin_status == 0
        and admin_identity.startswith("uid=")
        and f"({config.host.admin_user})" in admin_identity,
        f"configured administrative identity {config.host.admin_user} is absent",
    )

    ssh_status, sshd = _fact(inventory, "sshd_dropin")
    required_sshd = (
        "AuthenticationMethods publickey",
        "PasswordAuthentication no",
        "KbdInteractiveAuthentication no",
        "PermitRootLogin no",
        "AllowTcpForwarding no",
        "AllowStreamLocalForwarding no",
        "X11Forwarding no",
        "AllowAgentForwarding no",
        f"AllowUsers {config.host.admin_user} {config.host.runtime_user}",
    )
    require(
        FailureCode.SSH,
        ssh_status == 0 and all(item in sshd for item in required_sshd),
        "OpenSSH hardening drop-in is missing or incomplete",
    )
    effective_status, effective_sshd = _fact(inventory, "sshd_effective")
    required_effective_sshd = (
        "authenticationmethods publickey",
        "passwordauthentication no",
        "kbdinteractiveauthentication no",
        "permitrootlogin no",
        "allowtcpforwarding no",
        "allowstreamlocalforwarding no",
        "x11forwarding no",
        "allowagentforwarding no",
        "listenaddress 0.0.0.0:22",
        "listenaddress [::]:22",
    )
    effective_sshd_folded = effective_sshd.casefold()
    effective_allow_users = {
        user
        for line in effective_sshd_folded.splitlines()
        if line.startswith("allowusers ")
        for user in line.split()[1:]
    }
    require(
        FailureCode.SSH,
        effective_status == 0
        and all(item in effective_sshd_folded for item in required_effective_sshd)
        and {config.host.admin_user, config.host.runtime_user}.issubset(effective_allow_users),
        "effective OpenSSH policy is overridden or does not listen on LAN and Tailscale paths",
    )
    _, host_fingerprint = _fact(inventory, "host_ed25519_fingerprint")
    require(
        FailureCode.SSH,
        host_fingerprint == _trust(config).bravo_host_fingerprint,
        "live Ed25519 host key does not match the console-verified fingerprint",
    )

    ufw_status, ufw = _fact(inventory, "ufw")
    require(
        FailureCode.FIREWALL,
        ufw_status == 0
        and "Status: active" in ufw
        and "Default: deny (incoming), allow (outgoing)" in ufw,
        "UFW is inactive or its default policies are not deny-in/allow-out",
    )
    for source in (str(config.laptop.lan_address), str(config.laptop.tailscale_address)):
        require(
            FailureCode.FIREWALL,
            ufw_status == 0
            and any("22/tcp" in line and source in line for line in ufw.splitlines()),
            f"UFW does not show source-restricted SSH for {source}",
        )
    for port in (2402, 2502, 2602)[: config.host.slots]:
        require(
            FailureCode.FIREWALL,
            ufw_status == 0
            and any(
                f"{port}:{port + 4}/udp" in line and str(config.laptop.lan_address) in line
                for line in ufw.splitlines()
            ),
            f"UFW does not show LAN-only UDP block {port}-{port + 4}",
        )
    allowed_rules = {
        ("22/tcp", str(config.laptop.lan_address)),
        ("22/tcp", str(config.laptop.tailscale_address)),
        *(
            (f"{port}:{port + 4}/udp", str(config.laptop.lan_address))
            for port in (2402, 2502, 2602)[: config.host.slots]
        ),
    }
    unexpected_rules = [
        line
        for line in ufw.splitlines()
        if "ALLOW IN" in line
        and not any(label in line and source in line for label, source in allowed_rules)
    ]
    require(
        FailureCode.FIREWALL,
        not unexpected_rules,
        "UFW has inbound allowances outside the commissioned source/port set",
    )
    laptop_firewall = inventory.get("laptop_firewall", {})
    laptop_ufw_status = laptop_firewall.get("status", 1) if isinstance(laptop_firewall, dict) else 1
    laptop_ufw = laptop_firewall.get("value", "") if isinstance(laptop_firewall, dict) else ""
    laptop_ufw = laptop_ufw if isinstance(laptop_ufw, str) else ""
    require(
        FailureCode.FIREWALL,
        laptop_ufw_status == 0
        and "Status: active" in laptop_ufw
        and "Default: deny (incoming), allow (outgoing)" in laptop_ufw
        and all(
            any(
                str(config.laptop.ssh_port) in line and source in line
                for line in laptop_ufw.splitlines()
            )
            for source in (str(config.host.lan_address), str(config.host.tailscale_address))
        )
        and not any(
            str(config.laptop.ssh_port) in line and "Anywhere" in line
            for line in laptop_ufw.splitlines()
        )
        and any(
            str(config.laptop.ssh_port) in line and str(config.laptop.wsl_proxy_source) in line
            for line in laptop_ufw.splitlines()
        ),
        "laptop WSL UFW is inactive, broad, or missing a bravo source rule",
    )
    require(
        FailureCode.FIREWALL,
        "2302" not in ufw and "2306" not in ufw,
        "UFW exposes reserved ports 2302-2306",
    )

    _, wol = _fact(inventory, "ethtool")
    _, nm_wol = _fact(inventory, "nm_wol")
    _, suspend = _fact(inventory, "suspend_targets")
    require(
        FailureCode.POWER,
        re.search(r"Supports Wake-on:.*g", wol) is not None,
        "NIC does not report magic-packet support",
    )
    require(
        FailureCode.POWER,
        re.search(r"Wake-on:\s*g", wol) is not None and nm_wol == "magic",
        "magic-packet wake is not active in both NIC and NetworkManager",
    )
    require(
        FailureCode.POWER,
        suspend.splitlines().count("masked") == SUSPEND_TARGET_COUNT,
        "sleep/hibernate targets are not all masked",
    )

    _, gdm = _fact(inventory, "gdm")
    require(
        FailureCode.CLIENT,
        "WaylandEnable=false" in gdm
        and "AutomaticLoginEnable=true" in gdm
        and f"AutomaticLogin={config.host.runtime_user}" in gdm
        and f"AutomaticLogin={config.host.admin_user}" not in gdm,
        "GDM is not unambiguously configured for cti X11 autologin",
    )
    gdm_loaded_status, gdm_loaded = _fact(inventory, "gdm_config_loaded")
    require(
        FailureCode.CLIENT,
        gdm_loaded_status == 0 and gdm_loaded == "loaded",
        "GDM has not loaded the commissioned autologin configuration",
    )
    graphical_session_status, graphical_session = _fact(inventory, "graphical_session")
    require(
        FailureCode.CLIENT,
        graphical_session_status == 0 and graphical_session.endswith(" x11"),
        "cti does not have an active X11 graphical session",
    )

    gpu_status, gpu = _fact(inventory, "gpu")
    vulkan_status, vulkan = _fact(inventory, "vulkan")
    require(
        FailureCode.GPU,
        gpu_status == 0 and "NVIDIA" in gpu.upper(),
        "NVIDIA GPU/driver facts are unavailable",
    )
    require(
        FailureCode.GPU,
        vulkan_status == 0 and "device" in vulkan.casefold(),
        "Vulkan enumeration failed",
    )

    steamcmd_status, _ = _fact(inventory, "steamcmd")
    steam_status, _ = _fact(inventory, "steam")
    server_status, server_binary = _fact(inventory, "server_binary")
    _, steamcmd_path = _fact(inventory, "steamcmd")
    _, steam_path = _fact(inventory, "steam")
    require(
        FailureCode.STEAM,
        steamcmd_status == 0 and steam_status == 0 and bool(steamcmd_path) and bool(steam_path),
        "SteamCMD or Steam client is absent",
    )
    steam_library_status, steam_library = _fact(inventory, "steam_library")
    expected_library_prefix = (
        f"uuid={config.steam.library_uuid} mount={config.steam.library_mount} "
        "type=ext4 owner=cti:cti options="
    )
    library_options = (
        steam_library.removeprefix(expected_library_prefix)
        if steam_library.startswith(expected_library_prefix)
        else ""
    )
    require(
        FailureCode.STEAM,
        steam_library_status == 0
        and bool(library_options)
        and steam_mount_options_are_safe(library_options),
        "Steam library is not the configured persistent ext4 mount owned by cti",
    )
    steam_library_root_status, steam_library_root = _fact(inventory, "steam_library_root")
    require(
        FailureCode.STEAM,
        steam_library_root_status == 0
        and steam_library_root
        == f"mount={config.steam.library_mount} root={config.steam.library_root}",
        "Steam's registered library root is not on the configured filesystem mount",
    )
    require(
        FailureCode.ENGINE,
        server_status == 0 and server_binary == "present",
        "native server app 233780 is not installed",
    )
    _, server_manifest = _fact(inventory, "server_manifest")
    require(
        FailureCode.ENGINE,
        '"appid"\t\t"233780"' in server_manifest or '"appid" "233780"' in server_manifest,
        "server appmanifest does not identify app 233780",
    )

    _, listeners = _fact(inventory, "listeners")
    require(
        FailureCode.PORT,
        not any(str(port) in listeners for port in range(2302, 2307)),
        "a process is listening on reserved ports 2302-2306",
    )
    require(
        FailureCode.PORT,
        not any(f":{port} " in listeners for port in range(9099, 9102)),
        "a daemon port is listening outside an active run",
    )

    client_manifest_status, client_manifest = _fact(inventory, "client_manifest")
    client_binary_status, client_binary = _fact(inventory, "client_binary")
    proton_version_status, proton_version = _fact(inventory, "proton_version")
    _, steam_compat_config = _fact(inventory, "steam_compat_config")
    _, client_service = _fact(inventory, "client_service")
    require(
        FailureCode.CLIENT,
        client_manifest_status == 0
        and ('"appid"\t\t"107410"' in client_manifest or '"appid" "107410"' in client_manifest),
        "licensed client app 107410 is not installed",
    )
    require(
        FailureCode.CLIENT,
        client_binary_status == 0 and client_binary == "present",
        "licensed client executable is absent from the configured install",
    )
    require(
        FailureCode.CLIENT,
        proton_version_status == 0 and PROTON_VERSION in proton_version,
        f"Proton is not pinned to {PROTON_VERSION}",
    )
    require(
        FailureCode.CLIENT,
        steam_compat_config == "107410=proton_10",
        "Steam has no app-specific Proton 10 mapping for Arma 3",
    )
    require(
        FailureCode.CLIENT,
        client_service == "installed",
        "cti-arma-client.service is not installed",
    )
    return failures


def _public_key(path: Path) -> str:
    public_path = path if path.suffix == ".pub" else Path(f"{path}.pub")
    try:
        value = public_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        msg = f"cannot read laptop-to-bravo public key {public_path}: {exc}"
        raise ConfigurationError(msg) from exc
    if not value.startswith("ssh-ed25519 ") or PRIVATE_KEY_MARKER in value:
        msg = f"{public_path} is not an Ed25519 public key"
        raise ConfigurationError(msg)
    return value


def _validated_public_key(value: str, label: str) -> tuple[str, str]:
    """Validate one Ed25519 public key and derive its OpenSSH SHA256 fingerprint."""
    if PRIVATE_KEY_MARKER in value or any(character in value for character in "\r\n\0"):
        msg = f"{label} is not a single-line Ed25519 public key"
        raise ConfigurationError(msg)
    parts = value.strip().split(maxsplit=2)
    if len(parts) < PUBLIC_KEY_MIN_PARTS or parts[0] != "ssh-ed25519":
        msg = f"{label} is not an Ed25519 public key"
        raise ConfigurationError(msg)
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        msg = f"{label} has invalid public-key base64"
        raise ConfigurationError(msg) from exc
    if (
        len(blob) != ED25519_BLOB_BYTES
        or blob[:4] != (11).to_bytes(4, "big")
        or blob[4:15] != b"ssh-ed25519"
    ):
        msg = f"{label} has an invalid Ed25519 key blob"
        raise ConfigurationError(msg)
    if blob[15:19] != (32).to_bytes(4, "big"):
        msg = f"{label} has an invalid Ed25519 key length"
        raise ConfigurationError(msg)
    normalized = f"ssh-ed25519 {parts[1]}"
    if len(parts) == PUBLIC_KEY_COMMENT_PARTS:
        normalized = f"{normalized} {parts[2]}"
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")
    return normalized, f"SHA256:{digest}"


def _trust(config: MachineBConfig) -> TrustMaterial:
    if config.trust is None:
        msg = "1Password trust cache is absent; run `just machine-b bootstrap pull`"
        raise ConfigurationError(msg)
    return config.trust


def _load_trust(config: OnePasswordConfig) -> TrustMaterial:
    try:
        mode = config.trust_file.stat().st_mode & 0o777
        raw = json.loads(config.trust_file.read_text(encoding="utf-8"))
    except OSError as exc:
        msg = f"cannot read {config.trust_file}; run `just machine-b bootstrap pull`: {exc}"
        raise ConfigurationError(msg) from exc
    except json.JSONDecodeError as exc:
        msg = f"invalid 1Password trust cache {config.trust_file}: {exc}"
        raise ConfigurationError(msg) from exc
    if mode & 0o077:
        msg = f"1Password trust cache must be mode 0600: {config.trust_file}"
        raise ConfigurationError(msg)
    if not isinstance(raw, dict):
        msg = f"invalid 1Password trust cache object: {config.trust_file}"
        raise ConfigurationError(msg)
    expected_keys = {
        "schema",
        "account",
        "vault",
        "item",
        "item_id",
        "bravo_host_public_key",
        "bravo_host_fingerprint",
        "laptop_host_public_key",
        "laptop_host_fingerprint",
        "laptop_to_bravo_public_key",
    }
    if set(raw) != expected_keys or raw.get("schema") != 1:
        msg = f"invalid 1Password trust cache schema: {config.trust_file}"
        raise ConfigurationError(msg)
    if (
        raw.get("account") != config.account
        or raw.get("vault") != config.vault
        or raw.get("item") != config.item
    ):
        msg = "1Password trust cache belongs to a different account, vault, or item"
        raise ConfigurationError(msg)
    text_values = {key: value for key, value in raw.items() if key not in {"schema", "account"}}
    if not isinstance(raw["account"], str) or not all(
        isinstance(value, str) and value for value in text_values.values()
    ):
        msg = f"invalid empty value in 1Password trust cache: {config.trust_file}"
        raise ConfigurationError(msg)
    bravo_key, bravo_fingerprint = _validated_public_key(
        cast("str", raw["bravo_host_public_key"]), "cached bravo host key"
    )
    laptop_key, laptop_fingerprint = _validated_public_key(
        cast("str", raw["laptop_host_public_key"]), "cached laptop host key"
    )
    forward_key, _ = _validated_public_key(
        cast("str", raw["laptop_to_bravo_public_key"]), "cached laptop automation key"
    )
    if raw["bravo_host_fingerprint"] != bravo_fingerprint:
        msg = "cached bravo fingerprint does not match its public host key"
        raise ConfigurationError(msg)
    if raw["laptop_host_fingerprint"] != laptop_fingerprint:
        msg = "cached laptop fingerprint does not match its public host key"
        raise ConfigurationError(msg)
    return TrustMaterial(
        item_id=cast("str", raw["item_id"]),
        bravo_host_public_key=bravo_key,
        bravo_host_fingerprint=bravo_fingerprint,
        laptop_host_public_key=laptop_key,
        laptop_host_fingerprint=laptop_fingerprint,
        laptop_to_bravo_public_key=forward_key,
    )


def _op_base(account: str) -> list[str]:
    result = [op_executable()]
    if account:
        result.extend(("--account", account))
    return result


def _is_wsl() -> bool:
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8")
    except OSError:
        return False
    return "microsoft" in release.casefold()


def op_executable() -> str:
    """Select the desktop-integrated CLI for the current operating environment."""
    candidates = ("op", "op.exe") if _is_wsl() else ("op",)
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved is not None:
            return resolved
    expected = "op.exe or op" if _is_wsl() else "op"
    msg = f"1Password CLI `{expected}` is not installed"
    raise BootstrapError(msg)


def _op_run(account: str, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(  # noqa: S603 — fixed op binary; public material only
            [*_op_base(account), *arguments],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = "1Password CLI timed out; unlock the laptop desktop app and retry"
        raise BootstrapError(msg) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown 1Password CLI error"
        raise BootstrapError(detail)
    return result


def _op_item_id(vault: str, item: str, account: str) -> str | None:
    result = _op_run(account, ["item", "list", "--vault", vault, "--format", "json"])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        msg = "1Password returned invalid item-list JSON"
        raise BootstrapError(msg) from exc
    if not isinstance(payload, list):
        msg = "1Password returned a non-list item inventory"
        raise BootstrapError(msg)
    matches = [row for row in payload if isinstance(row, dict) and row.get("title") == item]
    if len(matches) > 1:
        msg = f"multiple 1Password items are titled {item!r} in vault {vault!r}"
        raise BootstrapError(msg)
    if not matches:
        return None
    item_id = matches[0].get("id")
    if not isinstance(item_id, str) or not item_id:
        msg = "1Password item has no stable ID"
        raise BootstrapError(msg)
    return item_id


def _op_upsert(
    config: OnePasswordConfig,
    fields: dict[str, str],
    *,
    item_id: str | None = None,
) -> str:
    """Create or update the public-material item without placing secrets on argv."""
    if item_id is None:
        item_id = _op_item_id(config.vault, config.item, config.account)
    assignments = [f"{label}[text]={value}" for label, value in sorted(fields.items())]
    if item_id is None:
        result = _op_run(
            config.account,
            [
                "item",
                "create",
                "--category",
                "Secure Note",
                "--title",
                config.item,
                "--vault",
                config.vault,
                "--format",
                "json",
                *assignments,
            ],
        )
        try:
            payload = json.loads(result.stdout)
            created_id = payload.get("id") if isinstance(payload, dict) else None
        except json.JSONDecodeError as exc:
            msg = "1Password returned invalid created-item JSON"
            raise BootstrapError(msg) from exc
        if not isinstance(created_id, str) or not created_id:
            msg = "1Password did not return the created item's ID"
            raise BootstrapError(msg)
        return created_id
    _op_run(
        config.account,
        ["item", "edit", item_id, "--vault", config.vault, *assignments],
    )
    return item_id


def _op_fields(config: OnePasswordConfig) -> tuple[str, dict[str, str]]:
    item_id = _op_item_id(config.vault, config.item, config.account)
    if item_id is None:
        msg = "bootstrap item is absent; publish it from Machine B's local console first"
        raise BootstrapError(msg)
    result = _op_run(
        config.account,
        ["item", "get", item_id, "--vault", config.vault, "--format", "json", "--reveal"],
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        msg = "1Password returned invalid item JSON"
        raise BootstrapError(msg) from exc
    rows = payload.get("fields") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        msg = "1Password item has no fields list"
        raise BootstrapError(msg)
    fields: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = row.get("label")
        value = row.get("value")
        if isinstance(label, str) and isinstance(value, str) and label in fields:
            msg = f"1Password item has duplicate field {label!r}"
            raise BootstrapError(msg)
        if isinstance(label, str) and isinstance(value, str):
            fields[label] = value
    return item_id, fields


def _mirror_reverse_public_key(
    config: OnePasswordConfig,
    trust: TrustMaterial,
    reverse_key: str,
) -> bool:
    """Mirror public reverse material without making desktop integration a host dependency."""
    try:
        _op_upsert(
            config,
            {"schema_version": "1", "bravo_to_laptop_public_key": reverse_key},
            item_id=trust.item_id,
        )
    except BootstrapError as exc:
        print(
            f"[machine-b] warning: 1Password public-key mirror deferred: {exc}",
            file=sys.stderr,
        )
        return False
    return True


def _require_local_console(action: str) -> None:
    if any(os.environ.get(name) for name in ("SSH_CLIENT", "SSH_CONNECTION", "SSH_TTY")):
        msg = f"bootstrap {action} must run at that machine's local console"
        raise BootstrapError(msg)


def _atomic_write(path: Path, content: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fchmod(handle.fileno(), mode)
    temporary.replace(path)


def _ensure_automation_key(path: Path) -> str:
    public_path = Path(f"{path}.pub")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        key_binary = shutil.which("ssh-keygen")
        if key_binary is None:
            msg = "ssh-keygen is not installed"
            raise BootstrapError(msg)
        result = subprocess.run(  # noqa: S603 — resolved key tool and configured local path
            [
                key_binary,
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "arma-cti laptop to bravo",
                "-f",
                str(path),
            ],
            check=False,
        )
        if result.returncode != 0:
            msg = "could not create the laptop-to-bravo automation key"
            raise BootstrapError(msg)
    try:
        value = public_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        msg = f"cannot read automation public key {public_path}: {exc}"
        raise BootstrapError(msg) from exc
    return _validated_public_key(value, "laptop automation key")[0]


def _render_known_hosts(config: MachineBConfig, host_public_key: str) -> str:
    key = " ".join(host_public_key.split()[:2])
    names = dict.fromkeys(
        (
            config.host.ssh_alias_lan,
            str(config.host.lan_address),
            config.host.ssh_alias_tail,
            str(config.host.tailscale_address),
            config.host.admin_ssh_target,
        )
    )
    return f"{','.join(names)} {key}\n"


def _known_host_target(address: ipaddress.IPv4Address, port: int) -> str:
    """Render OpenSSH's canonical known_hosts target for a validated endpoint."""
    return str(address) if port == SSH_DEFAULT_PORT else f"[{address}]:{port}"


def _render_laptop_ssh_config(config: MachineBConfig) -> str:
    rows: list[str] = []
    for alias, address in (
        (config.host.ssh_alias_lan, config.host.lan_address),
        (config.host.ssh_alias_tail, config.host.tailscale_address),
    ):
        rows.extend(
            (
                f"Host {alias}",
                f"    HostName {address}",
                f"    User {config.host.runtime_user}",
                f"    IdentityFile {config.laptop.identity_to_bravo}",
                "    IdentitiesOnly yes",
                "    BatchMode yes",
                "    StrictHostKeyChecking yes",
                f"    UserKnownHostsFile {config.onepassword.known_hosts_file}",
                "    ConnectTimeout 8",
                "    ServerAliveInterval 5",
                "    ServerAliveCountMax 2",
                "    RequestTTY no",
                "    ClearAllForwardings yes",
                "",
            )
        )
    return "\n".join(rows)


def _install_laptop_trust(config: MachineBConfig, trust: TrustMaterial) -> None:
    _atomic_write(
        config.onepassword.known_hosts_file,
        _render_known_hosts(config, trust.bravo_host_public_key),
        mode=0o600,
    )
    ssh_directory = Path.home() / ".ssh"
    include_directory = ssh_directory / "config.d"
    include_file = include_directory / "arma-cti-machine-b"
    _atomic_write(include_file, _render_laptop_ssh_config(config), mode=0o600)
    root_config = ssh_directory / "config"
    include_line = "Include ~/.ssh/config.d/*"
    try:
        existing = root_config.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    except OSError as exc:
        msg = f"cannot read {root_config}: {exc}"
        raise BootstrapError(msg) from exc
    if include_line not in existing.splitlines():
        _atomic_write(root_config, f"{include_line}\n{existing}", mode=0o600)


def bootstrap_publish(vault: str, item: str, account: str) -> int:
    """Publish only B's locally read host public key and derived fingerprint."""
    _require_local_console("publish")
    try:
        value = LOCAL_HOST_PUBLIC_KEY.read_text(encoding="utf-8").strip()
    except OSError as exc:
        msg = f"cannot read local SSH host public key: {exc}"
        raise BootstrapError(msg) from exc
    public_key, fingerprint = _validated_public_key(value, "bravo host key")
    config = OnePasswordConfig(
        vault=vault,
        item=item,
        account=account,
        trust_file=Path("/dev/null"),
        known_hosts_file=Path("/dev/null"),
    )
    item_id = _op_upsert(
        config,
        {
            "schema_version": "1",
            "bravo_host_public_key": public_key,
            "bravo_host_fingerprint": fingerprint,
        },
    )
    print(f"bootstrap=published item_id={item_id} fingerprint={fingerprint}")
    return 0


def bootstrap_pull(config: MachineBConfig) -> int:
    """Establish laptop trust and publish its public half through 1Password."""
    _require_local_console("pull")
    item_id, fields = _op_fields(config.onepassword)
    if fields.get("schema_version") != "1":
        msg = "1Password bootstrap item has an unsupported schema"
        raise BootstrapError(msg)
    try:
        bravo_key = fields["bravo_host_public_key"]
        published_fingerprint = fields["bravo_host_fingerprint"]
    except KeyError as exc:
        msg = f"1Password bootstrap item is missing {exc.args[0]}"
        raise BootstrapError(msg) from exc
    bravo_key, bravo_fingerprint = _validated_public_key(bravo_key, "published bravo host key")
    if published_fingerprint != bravo_fingerprint:
        msg = "published bravo fingerprint does not match its public host key"
        raise BootstrapError(msg)
    try:
        laptop_value = LOCAL_HOST_PUBLIC_KEY.read_text(encoding="utf-8").strip()
    except OSError as exc:
        msg = f"cannot read laptop SSH host public key: {exc}"
        raise BootstrapError(msg) from exc
    laptop_key, laptop_fingerprint = _validated_public_key(laptop_value, "laptop host key")
    forward_key = _ensure_automation_key(config.laptop.identity_to_bravo)
    _op_upsert(
        config.onepassword,
        {
            "schema_version": "1",
            "laptop_host_public_key": laptop_key,
            "laptop_host_fingerprint": laptop_fingerprint,
            "laptop_to_bravo_public_key": forward_key,
        },
        item_id=item_id,
    )
    trust = TrustMaterial(
        item_id=item_id,
        bravo_host_public_key=bravo_key,
        bravo_host_fingerprint=bravo_fingerprint,
        laptop_host_public_key=laptop_key,
        laptop_host_fingerprint=laptop_fingerprint,
        laptop_to_bravo_public_key=forward_key,
    )
    cache = {
        "schema": 1,
        "account": config.onepassword.account,
        "vault": config.onepassword.vault,
        "item": config.onepassword.item,
        **dataclasses.asdict(trust),
    }
    _atomic_write(
        config.onepassword.trust_file,
        json.dumps(cache, indent=2, sort_keys=True) + "\n",
        mode=0o600,
    )
    _install_laptop_trust(config, trust)
    print(
        "bootstrap=pulled "
        f"item_id={item_id} bravo_fingerprint={bravo_fingerprint} "
        f"laptop_fingerprint={laptop_fingerprint}"
    )
    return 0


def _render_admin_authorized_keys(existing: str, entry: str) -> str:
    """Replace the single repository-owned admin bootstrap block."""
    begin_count = existing.count(ADMIN_KEY_BLOCK_BEGIN)
    end_count = existing.count(ADMIN_KEY_BLOCK_END)
    if begin_count != end_count or begin_count > 1:
        msg = "admin authorized_keys has a malformed machine-b bootstrap block"
        raise BootstrapError(msg)
    block = f"{ADMIN_KEY_BLOCK_BEGIN}\n{entry}\n{ADMIN_KEY_BLOCK_END}\n"
    if begin_count == 0:
        prefix = existing
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        return f"{prefix}{block}"
    start = existing.index(ADMIN_KEY_BLOCK_BEGIN)
    finish = existing.index(ADMIN_KEY_BLOCK_END, start) + len(ADMIN_KEY_BLOCK_END)
    if finish < len(existing) and existing[finish] == "\n":
        finish += 1
    return f"{existing[:start]}{block}{existing[finish:]}"


def bootstrap_authorize(config: MachineBConfig) -> int:
    """Authorize the laptop's published public key for the admin commissioning hop."""
    _require_local_console("authorize")
    if Path.home().name != config.host.admin_user:
        msg = f"bootstrap authorize must run as {config.host.admin_user}"
        raise BootstrapError(msg)
    item_id, fields = _op_fields(config.onepassword)
    if fields.get("schema_version") != "1":
        msg = "1Password bootstrap item has an unsupported schema"
        raise BootstrapError(msg)
    required = (
        "bravo_host_public_key",
        "bravo_host_fingerprint",
        "laptop_host_public_key",
        "laptop_host_fingerprint",
        "laptop_to_bravo_public_key",
    )
    try:
        published = {label: fields[label] for label in required}
    except KeyError as exc:
        msg = f"1Password bootstrap item is missing {exc.args[0]}"
        raise BootstrapError(msg) from exc

    try:
        local_value = LOCAL_HOST_PUBLIC_KEY.read_text(encoding="utf-8").strip()
    except OSError as exc:
        msg = f"cannot read local SSH host public key: {exc}"
        raise BootstrapError(msg) from exc
    local_key, local_fingerprint = _validated_public_key(local_value, "local bravo host key")
    bravo_key, bravo_fingerprint = _validated_public_key(
        published["bravo_host_public_key"], "published bravo host key"
    )
    if (
        bravo_key != local_key
        or bravo_fingerprint != local_fingerprint
        or published["bravo_host_fingerprint"] != local_fingerprint
    ):
        msg = "1Password bravo host material does not match this local console"
        raise BootstrapError(msg)
    _, laptop_fingerprint = _validated_public_key(
        published["laptop_host_public_key"], "published laptop host key"
    )
    if published["laptop_host_fingerprint"] != laptop_fingerprint:
        msg = "published laptop fingerprint does not match its host key"
        raise BootstrapError(msg)
    laptop_key, _ = _validated_public_key(
        published["laptop_to_bravo_public_key"], "published laptop automation key"
    )
    entry = (
        f'from="{config.laptop.lan_address},{config.laptop.tailscale_address}",restrict '
        f"{laptop_key}"
    )
    ssh_directory = Path.home() / ".ssh"
    ssh_directory.mkdir(mode=0o700, exist_ok=True)
    authorized_keys = ssh_directory / "authorized_keys"
    try:
        existing = authorized_keys.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    except OSError as exc:
        msg = f"cannot read {authorized_keys}: {exc}"
        raise BootstrapError(msg) from exc
    _atomic_write(
        authorized_keys,
        _render_admin_authorized_keys(existing, entry),
        mode=0o600,
    )
    print(f"bootstrap=authorized item_id={item_id} admin={config.host.admin_user}")
    return 0


def ansible_vars(config: MachineBConfig, reverse_public_key: str = "") -> dict[str, object]:
    """Render the playbooks' non-secret variable contract."""
    trust = _trust(config)
    return {
        "ansible_python_interpreter": "/usr/bin/python3",
        "cti_logical_host": config.host.logical_name,
        "cti_system_hostname": config.host.system_hostname,
        "cti_admin_user": config.host.admin_user,
        "cti_runtime_user": config.host.runtime_user,
        "cti_host_lan": str(config.host.lan_address),
        "cti_host_tail": str(config.host.tailscale_address),
        "cti_host_mac": config.host.wired_mac,
        "cti_wired_interface": config.host.wired_interface,
        "cti_network_connection": config.host.network_connection,
        "cti_bravo_alias_lan": config.host.ssh_alias_lan,
        "cti_bravo_alias_tail": config.host.ssh_alias_tail,
        "cti_laptop_lan": str(config.laptop.lan_address),
        "cti_laptop_tail": str(config.laptop.tailscale_address),
        "cti_laptop_wsl_proxy_source": str(config.laptop.wsl_proxy_source),
        "cti_laptop_mac": config.laptop.wired_mac,
        "cti_laptop_ssh_port": config.laptop.ssh_port,
        "cti_laptop_tail_port": config.laptop.tailscale_ssh_port,
        "cti_laptop_known_host_lan": _known_host_target(
            config.laptop.lan_address, config.laptop.ssh_port
        ),
        "cti_laptop_known_host_tail": _known_host_target(
            config.laptop.tailscale_address, config.laptop.tailscale_ssh_port
        ),
        "cti_laptop_alias_lan": config.laptop.ssh_alias_lan,
        "cti_laptop_alias_tail": config.laptop.ssh_alias_tail,
        "cti_laptop_peer_user": config.laptop.peer_user,
        "cti_laptop_to_bravo_public_key": _public_key(config.laptop.identity_to_bravo),
        "cti_bravo_to_laptop_public_key": reverse_public_key,
        "cti_slots": config.host.slots,
        "cti_slot_ports": [2402 + (100 * slot) for slot in range(config.host.slots)],
        "cti_server_install": str(config.steam.server_install),
        "cti_steam_library_mount": str(config.steam.library_mount),
        "cti_steam_library_root": str(config.steam.library_root),
        "cti_client_install": str(config.steam.client_install),
        "cti_proton_version": config.steam.proton_version,
        "cti_bravo_host_fingerprint": trust.bravo_host_fingerprint,
        "cti_laptop_host_fingerprint": trust.laptop_host_fingerprint,
        "cti_laptop_host_public_key": "",
        "cti_uv_binary": shutil.which("uv") or "",
        "cti_laptop_to_bravo_identity": str(config.laptop.identity_to_bravo),
        "cti_laptop_known_hosts_file": str(config.onepassword.known_hosts_file),
    }


def _run_ansible(arguments: list[str], *, expect_zero_changes: bool = False) -> int:
    command = ["uv", "run", *arguments]
    result = subprocess.run(  # noqa: S603 — fixed uv/Ansible entrypoints; vars are data files
        command,
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        return result.returncode
    if expect_zero_changes:
        changes = [int(value) for value in re.findall(r"changed=(\d+)", result.stdout)]
        if not changes or any(changes):
            print("[machine-b] idempotence failure: second apply reported changes", file=sys.stderr)
            return 1
    return 0


def _vars_file(directory: Path, variables: dict[str, object]) -> Path:
    path = directory / "vars.json"
    path.write_text(json.dumps(variables, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def apply(config: MachineBConfig) -> int:
    """Run lint, syntax, check mode, apply, and a zero-change second apply."""
    if not sys.stdin.isatty():
        print("[machine-b] apply requires a terminal for sudo prompts", file=sys.stderr)
        return 64
    required = ("ssh", "rsync", "uv")
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        print(f"[machine-b] missing local tool(s): {', '.join(missing)}", file=sys.stderr)
        return 5
    try:
        op_executable()
    except BootstrapError as exc:
        print(f"[machine-b] missing local tool: {exc}", file=sys.stderr)
        return 5
    trust = _trust(config)
    laptop_host_key = LOCAL_HOST_PUBLIC_KEY
    try:
        laptop_host_public_key = laptop_host_key.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"[machine-b] cannot read the laptop Ed25519 host public key: {exc}", file=sys.stderr)
        return 5
    normalized_laptop_key, laptop_fingerprint = _validated_public_key(
        laptop_host_public_key, "local laptop host key"
    )
    if laptop_fingerprint != trust.laptop_host_fingerprint:
        print(
            "[machine-b] laptop host key does not match the console-recorded fingerprint",
            file=sys.stderr,
        )
        return 5
    try:
        known_hosts = config.onepassword.known_hosts_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[machine-b] cannot read bootstrap known_hosts: {exc}", file=sys.stderr)
        return 5
    if (
        _public_key(config.laptop.identity_to_bravo) != trust.laptop_to_bravo_public_key
        or normalized_laptop_key != trust.laptop_host_public_key
        or known_hosts != _render_known_hosts(config, trust.bravo_host_public_key)
    ):
        print(
            "[machine-b] local SSH material differs from the 1Password trust cache; "
            "rerun bootstrap pull",
            file=sys.stderr,
        )
        return 5

    static_commands = (
        ["ansible-playbook", "--syntax-check", "-i", "localhost,", "ops/machine-b/apply.yml"],
        ["ansible-playbook", "--syntax-check", "-i", "localhost,", "ops/machine-b/laptop.yml"],
        ["ansible-lint", "--strict", "ops/machine-b/apply.yml", "ops/machine-b/laptop.yml"],
    )
    for command in static_commands:
        status = _run_ansible(command)
        if status != 0:
            return status

    with tempfile.TemporaryDirectory(prefix="arma-cti-machine-b-") as temp:
        directory = Path(temp)
        reverse_public_key = directory / "bravo-to-laptop.pub"
        variables = ansible_vars(config)
        variables["cti_laptop_host_public_key"] = laptop_host_public_key
        variables["cti_reverse_public_key_fetch"] = str(reverse_public_key)
        variables_file = _vars_file(directory, variables)
        inventory = f"{config.host.admin_ssh_target},"
        base = [
            "ansible-playbook",
            "-i",
            inventory,
            "-u",
            config.host.admin_user,
            "--private-key",
            str(config.laptop.identity_to_bravo),
            "-e",
            f"@{variables_file}",
            "--ssh-common-args",
            (
                f"-oUserKnownHostsFile={config.onepassword.known_hosts_file} "
                "-oStrictHostKeyChecking=yes -oCheckHostIP=no"
            ),
            "--ask-become-pass",
        ]
        status = _run_ansible([*base, "--check", "--diff", "ops/machine-b/apply.yml"])
        if status != 0:
            return status
        status = _run_ansible([*base, "ops/machine-b/apply.yml"])
        if status != 0:
            return status

        try:
            reverse_value = reverse_public_key.read_text(encoding="utf-8").strip()
        except OSError:
            print("[machine-b] could not fetch bravo's public peer key", file=sys.stderr)
            return 5
        reverse_key, _ = _validated_public_key(reverse_value, "bravo automation key")
        _mirror_reverse_public_key(config.onepassword, trust, reverse_key)
        variables = ansible_vars(config, reverse_key)
        variables["cti_laptop_host_public_key"] = laptop_host_public_key
        variables["cti_reverse_public_key_fetch"] = str(reverse_public_key)
        variables_file = _vars_file(directory, variables)
        local_base = [
            "ansible-playbook",
            "-i",
            "localhost,",
            "-c",
            "local",
            "-e",
            f"@{variables_file}",
            "--ask-become-pass",
        ]
        status = _run_ansible([*local_base, "ops/machine-b/laptop.yml"])
        if status != 0:
            return status
        status = _run_ansible([*base, "ops/machine-b/apply.yml"], expect_zero_changes=True)
        if status != 0:
            return status
        return _run_ansible([*local_base, "ops/machine-b/laptop.yml"], expect_zero_changes=True)


def render_steam_library_script(filesystem_uuid: str) -> str:
    """Render the fail-closed local root handoff without executing it."""
    canonical_uuid = _filesystem_uuid(filesystem_uuid, "--uuid")
    template = (REPO / "ops/machine-b/files/mount-steam-library").read_text(encoding="utf-8")
    rendered = template.replace("__STEAM_LIBRARY_UUID__", canonical_uuid).replace(
        "__STEAM_LIBRARY_MOUNT__", str(STEAM_LIBRARY_MOUNT)
    )
    if "__STEAM_LIBRARY_" in rendered:
        msg = "Steam-library script template has an unresolved value"
        raise ConfigurationError(msg)
    return rendered


def steam_library_script(filesystem_uuid: str, output: Path) -> int:
    """Generate, but never run, the root-required persistent-mount handoff."""
    output = output.expanduser()
    if not output.is_absolute():
        print("[machine-b] --output must be an absolute path", file=sys.stderr)
        return 64
    rendered = render_steam_library_script(filesystem_uuid)
    _atomic_write(output, rendered, mode=0o700)
    digest = hashlib.sha256(rendered.encode()).hexdigest()
    print(
        f"steam-library-script=generated path={output} sha256={digest} "
        f"uuid={filesystem_uuid} mount={STEAM_LIBRARY_MOUNT}"
    )
    return 0


def audit(config: MachineBConfig, *, output: Path | None) -> int:
    """Print the redacted inventory and a compact human summary."""
    inventory = cast("dict[str, object]", redact(collect_inventory(config)))
    rendered = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    transport = inventory.get("transport", {})
    status = transport.get("status", 1) if isinstance(transport, dict) else 1
    facts = inventory.get("facts", {})
    fact_count = len(facts) if isinstance(facts, dict) else 0
    print(
        f"[machine-b] bravo-lan transport={status}; {fact_count} fact(s) collected",
        file=sys.stderr,
    )
    return 0


def verify(config: MachineBConfig, *, output: Path | None) -> int:
    """Collect inventory and print one typed line per discrepancy."""
    inventory = cast("dict[str, object]", redact(collect_inventory(config)))
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failures = verify_inventory(config, inventory)
    if not failures:
        print("verify=PASS host=bravo")
        return 0
    for failure in failures:
        print(f"verify=FAIL type={failure.code} detail={failure.detail}")
    return 5 if len(failures) == 1 and failures[0].code is FailureCode.SSH else 1


def wake(config: MachineBConfig, *, wait_seconds: int) -> int:
    """Send one magic packet, then bound recovery checks on both control paths."""
    if wait_seconds < 1 or wait_seconds > MAX_WAKE_WAIT:
        print("[machine-b] --wait must be between 1 and 900 seconds", file=sys.stderr)
        return 64
    wake_binary = shutil.which("wakeonlan")
    if wake_binary is None:
        print("[machine-b] wakeonlan is not installed on the initiating machine", file=sys.stderr)
        return 5
    result = subprocess.run(  # noqa: S603 — fixed binary; MAC/broadcast strictly validated
        [wake_binary, "-i", str(config.wake_broadcast), config.host.wired_mac],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        return 5
    deadline = time.monotonic() + wait_seconds
    recovered: set[str] = set()
    aliases = (config.host.ssh_alias_lan, config.host.ssh_alias_tail)
    while time.monotonic() < deadline and len(recovered) != len(aliases):
        for alias in aliases:
            if alias in recovered:
                continue
            if _ssh(bravo_ssh_target(config, alias), "true", timeout=12).returncode == 0:
                recovered.add(alias)
                print(f"wake_path={alias} status=recovered")
        if len(recovered) != len(aliases):
            time.sleep(5)
    missing = [alias for alias in aliases if alias not in recovered]
    if missing:
        print(f"wake=FAIL type=power detail=no SSH recovery on {','.join(missing)}")
        return 1
    print("wake=PASS paths=lan,tailscale")
    return 0


def windows_firewall(config: MachineBConfig) -> int:
    """Open the bounded Windows and Hyper-V path to the laptop's WSL sshd."""
    powershell = shutil.which("powershell.exe")
    wslpath = shutil.which("wslpath")
    missing = [
        name
        for name, executable in (("powershell.exe", powershell), ("wslpath", wslpath))
        if executable is None
    ]
    if missing:
        print(
            f"[machine-b] windows-firewall must run in laptop WSL; missing {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    script = REPO / "ops/machine-b/files/configure-windows-wsl-firewall.ps1"
    try:
        converted = subprocess.run(  # noqa: S603 — fixed WSL path converter
            [cast("str", wslpath), "-w", str(script)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("[machine-b] wslpath timed out", file=sys.stderr)
        return 2
    if converted.returncode != 0 or not converted.stdout.strip():
        detail = converted.stderr.strip() or "could not convert the script path"
        print(f"[machine-b] {detail}", file=sys.stderr)
        return 2

    command = [
        cast("str", powershell),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        converted.stdout.strip(),
        "-LaptopLanAddress",
        str(config.laptop.lan_address),
        "-LaptopTailscaleAddress",
        str(config.laptop.tailscale_address),
        "-MachineBLanAddress",
        str(config.host.lan_address),
        "-MachineBTailscaleAddress",
        str(config.host.tailscale_address),
    ]
    try:
        result = subprocess.run(  # noqa: S603 — fixed script; validated addresses are data
            command,
            timeout=WINDOWS_FIREWALL_WAIT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("[machine-b] Windows firewall approval timed out", file=sys.stderr)
        return 2
    return result.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the repository command surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("audit", "verify"):
        child = subparsers.add_parser(action)
        child.add_argument("--output", "--out", type=Path)
    subparsers.add_parser("apply")
    subparsers.add_parser("windows-firewall")
    steam_library_parser = subparsers.add_parser("steam-library-script")
    steam_library_parser.add_argument("--uuid", required=True)
    steam_library_parser.add_argument(
        "--output",
        type=Path,
        default=Path.home() / ".arma-cti" / "mount-steam-library.sh",
    )
    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_actions = bootstrap_parser.add_subparsers(dest="bootstrap_action", required=True)
    publish_parser = bootstrap_actions.add_parser("publish")
    publish_parser.add_argument("--vault", required=True)
    publish_parser.add_argument("--item", required=True)
    publish_parser.add_argument("--account", default="")
    bootstrap_actions.add_parser("pull")
    bootstrap_actions.add_parser("authorize")
    wake_parser = subparsers.add_parser("wake")
    wake_parser.add_argument("--wait", type=int, default=180)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one commissioning action."""
    args = parse_args(argv)
    try:
        if args.action == "bootstrap" and args.bootstrap_action == "publish":
            return bootstrap_publish(args.vault, args.item, args.account)
        if args.action == "steam-library-script":
            return steam_library_script(args.uuid, args.output)
        config = load_config(
            args.config,
            require_trust=not (
                args.action == "bootstrap" and args.bootstrap_action in {"pull", "authorize"}
            ),
        )
        if args.action == "bootstrap" and args.bootstrap_action == "pull":
            return bootstrap_pull(config)
        if args.action == "bootstrap" and args.bootstrap_action == "authorize":
            return bootstrap_authorize(config)
        if args.action == "audit":
            return audit(config, output=args.output)
        if args.action == "verify":
            return verify(config, output=args.output)
        if args.action == "apply":
            return apply(config)
        if args.action == "wake":
            return wake(config, wait_seconds=args.wait)
        if args.action == "windows-firewall":
            return windows_firewall(config)
    except ConfigurationError as exc:
        print(f"[machine-b] configuration_invalid: {exc}", file=sys.stderr)
        return 64
    except BootstrapError as exc:
        print(f"[machine-b] bootstrap_failed: {exc}", file=sys.stderr)
        return 5
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
