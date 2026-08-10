"""Decide whether `spike/run.sh` may launch into its observed environment.

The shell owns the observations and process seams; this module owns the
classification required by ADR-0049. A Windows-boundary run requires WSL2
mirrored networking (ADR-0006). A server-only run records the mode but does not
claim to need a boundary it never crosses.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
from typing import NamedTuple

EXIT_INFRA_UNAVAILABLE = 5

RFC1918 = tuple(
    ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class PreflightVerdict(NamedTuple):
    """The environment decision and the LAN observation staged with it."""

    proceed: bool
    lan_ip: str
    lan_status: str
    detail: str


def select_lan_address(addresses: tuple[str, ...], *, readable: bool) -> tuple[str, str]:
    """Choose the first RFC1918 address, or say loudly why there is none."""
    if not readable:
        return "", "unavailable: global IPv4 address inspection failed"
    for raw in addresses:
        try:
            address = ipaddress.IPv4Address(raw)
        except ipaddress.AddressValueError:
            continue
        if any(address in network for network in RFC1918):
            return str(address), "selected_rfc1918"
    shown = ",".join(addresses) if addresses else "<none>"
    return "", f"unavailable: no RFC1918 address among {shown}"


def decide(
    *,
    networking_mode: str,
    needs_windows_boundary: bool,
    addresses: tuple[str, ...],
    addresses_readable: bool,
) -> PreflightVerdict:
    """Apply the networking precondition without gating server-only runs."""
    lan_ip, lan_status = select_lan_address(addresses, readable=addresses_readable)
    if needs_windows_boundary and networking_mode != "mirrored":
        return PreflightVerdict(
            proceed=False,
            lan_ip=lan_ip,
            lan_status=lan_status,
            detail=(
                "a Windows-boundary run requires WSL2 networking mode mirrored; "
                f"observed {networking_mode or '<empty>'}"
            ),
        )
    return PreflightVerdict(
        proceed=True,
        lan_ip=lan_ip,
        lan_status=lan_status,
        detail="",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the observations made by the shell process seam."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--networking-mode", required=True)
    parser.add_argument("--needs-windows-boundary", action="store_true")
    parser.add_argument("--address", action="append", default=[])
    parser.add_argument("--address-inspection", choices=("readable", "failed"), default="readable")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print the tier's key=value contract and return the typed decision."""
    args = parse_args(argv)
    verdict = decide(
        networking_mode=args.networking_mode,
        needs_windows_boundary=args.needs_windows_boundary,
        addresses=tuple(args.address),
        addresses_readable=args.address_inspection == "readable",
    )
    print(f"verdict={'proceed' if verdict.proceed else 'FAIL'}")  # noqa: T201
    print(f"lan_ip={verdict.lan_ip}")  # noqa: T201
    print(f"lan_status={verdict.lan_status}")  # noqa: T201
    if verdict.proceed:
        return 0
    print("failure_class=infra_unavailable")  # noqa: T201
    print(f"failure_detail={verdict.detail}")  # noqa: T201
    return EXIT_INFRA_UNAVAILABLE


if __name__ == "__main__":
    sys.exit(main())
