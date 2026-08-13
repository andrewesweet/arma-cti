"""Read the machine-scoped regression host registry (ADR-0032, issue #53)."""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Final

DEFAULT_PATH: Final = Path.home() / ".arma-cti" / "hosts.toml"
NAME_PATTERN: Final = re.compile(r"^[a-z][a-z0-9-]*$")
SSH_TARGET_PATTERN: Final = re.compile(r"^[A-Za-z0-9_.-]*$")
DRIVERS: Final = {"none", "windows", "proton"}
MAX_SLOTS: Final = 6


class RegistryError(ValueError):
    """The host registry cannot safely drive the tier."""


@dataclasses.dataclass(frozen=True)
class Host:
    """One whole-pass execution host."""

    name: str
    ssh_target: str
    server_slots: int
    headed_client: bool
    human: bool
    client_driver: str
    remote_root: str

    @property
    def transport(self) -> str:
        """Return the one transport the host declares."""
        return "ssh" if self.ssh_target else "null"


def default_hosts() -> dict[str, Host]:
    """Preserve the historical one-host behavior when no registry exists."""
    return {
        "local": Host(
            name="local",
            ssh_target="",
            server_slots=MAX_SLOTS,
            headed_client=True,
            human=True,
            client_driver="windows",
            remote_root="",
        )
    }


def _boolean(table: dict[str, object], key: str) -> bool:
    value = table.get(key)
    if not isinstance(value, bool):
        msg = f"{key} must be true or false"
        raise RegistryError(msg)
    return value


def _text(table: dict[str, object], key: str, *, default: str = "") -> str:
    value = table.get(key, default)
    if not isinstance(value, str) or "\n" in value or "\t" in value:
        msg = f"{key} must be a one-line string"
        raise RegistryError(msg)
    return value


def _host(name: str, value: object) -> Host:
    """Validate and construct one host table."""
    if not NAME_PATTERN.fullmatch(name) or not isinstance(value, dict):
        msg = f"invalid host table: {name}"
        raise RegistryError(msg)
    allowed = {
        "ssh_target",
        "server_slots",
        "headed_client",
        "human",
        "client_driver",
        "remote_root",
    }
    unknown = set(value) - allowed
    if unknown:
        msg = f"unknown hosts.{name} key(s): {', '.join(sorted(unknown))}"
        raise RegistryError(msg)
    slots = value.get("server_slots")
    if isinstance(slots, bool) or not isinstance(slots, int) or not 1 <= slots <= MAX_SLOTS:
        msg = f"hosts.{name}.server_slots must be in 1..{MAX_SLOTS}"
        raise RegistryError(msg)
    ssh_target = _text(value, "ssh_target")
    if not SSH_TARGET_PATTERN.fullmatch(ssh_target):
        msg = f"hosts.{name}.ssh_target must be an SSH alias, not an option or command"
        raise RegistryError(msg)
    driver = _text(value, "client_driver", default="none")
    if driver not in DRIVERS:
        msg = f"hosts.{name}.client_driver must be one of {', '.join(sorted(DRIVERS))}"
        raise RegistryError(msg)
    headed = _boolean(value, "headed_client")
    if (driver != "none") is not headed:
        msg = f"hosts.{name} client_driver and headed_client disagree"
        raise RegistryError(msg)
    remote_root = _text(value, "remote_root")
    if ssh_target and not remote_root.startswith("/"):
        msg = f"hosts.{name}.remote_root must be absolute for SSH transport"
        raise RegistryError(msg)
    if not ssh_target and remote_root:
        msg = f"hosts.{name}.remote_root is valid only for SSH transport"
        raise RegistryError(msg)
    return Host(
        name=name,
        ssh_target=ssh_target,
        server_slots=slots,
        headed_client=headed,
        human=_boolean(value, "human"),
        client_driver=driver,
        remote_root=remote_root,
    )


def load(path: Path = DEFAULT_PATH) -> dict[str, Host]:
    """Load a strict registry, or the compatible local-only default."""
    if not path.exists():
        return default_hosts()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"cannot read host registry {path}: {exc}"
        raise RegistryError(msg) from exc
    if set(raw) != {"version", "hosts"} or raw.get("version") != 1:
        msg = "hosts.toml must contain only version = 1 and [hosts.*] tables"
        raise RegistryError(msg)
    tables = raw.get("hosts")
    if not isinstance(tables, dict) or not tables:
        msg = "hosts.toml declares no hosts"
        raise RegistryError(msg)
    hosts = {name: _host(name, value) for name, value in tables.items()}
    if "local" not in hosts or hosts["local"].transport != "null":
        msg = "hosts.toml must retain local as a null-transport host"
        raise RegistryError(msg)
    return hosts


def emit_shell(hosts: dict[str, Host]) -> None:
    """Emit validated tab-separated rows for spike/hosts.sh."""
    for host in hosts.values():
        role = "human" if host.human else "tier"
        print(  # noqa: T201 — line protocol consumed by the Bash host seam
            "\t".join(
                (
                    host.name,
                    role,
                    host.transport,
                    host.ssh_target or "-",
                    str(host.server_slots),
                    "1" if host.headed_client else "0",
                    host.client_driver,
                    host.remote_root or "-",
                )
            )
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the internal Python-to-Bash contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("shell", "json"))
    parser.add_argument("--config", type=Path, default=DEFAULT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Validate and render the registry."""
    args = parse_args(argv)
    try:
        hosts = load(args.config)
    except RegistryError as exc:
        print(f"host_registry_invalid={exc}", file=sys.stderr)  # noqa: T201 — CLI contract
        return 2
    if args.action == "shell":
        emit_shell(hosts)
    else:
        print(  # noqa: T201 — CLI contract
            json.dumps(
                {name: dataclasses.asdict(host) for name, host in hosts.items()},
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
