"""The harness environment decision before any world is launched (#70)."""

from __future__ import annotations

import pytest
from conftest import load_tool

harness_preflight = load_tool("harness_preflight")


@pytest.mark.parametrize("mode", ["nat", "unknown"])
def test_networking_mode_is_advisory_without_a_windows_boundary(mode: str) -> None:
    verdict = harness_preflight.decide(
        networking_mode=mode,
        needs_windows_boundary=False,
        addresses=(),
        addresses_readable=True,
    )
    assert verdict.proceed


@pytest.mark.parametrize("mode", ["nat", "unknown", "garbled"])
def test_only_mirrored_mode_can_cross_the_windows_boundary(mode: str) -> None:
    verdict = harness_preflight.decide(
        networking_mode=mode,
        needs_windows_boundary=True,
        addresses=(),
        addresses_readable=True,
    )
    assert not verdict.proceed
    assert "mirrored" in verdict.detail
    assert mode in verdict.detail


def test_mirrored_mode_can_cross_the_windows_boundary() -> None:
    verdict = harness_preflight.decide(
        networking_mode="mirrored",
        needs_windows_boundary=True,
        addresses=(),
        addresses_readable=True,
    )
    assert verdict.proceed


@pytest.mark.parametrize(
    ("addresses", "expected"),
    [
        (("10.42.0.8",), "10.42.0.8"),
        (("172.16.0.2",), "172.16.0.2"),
        (("172.31.255.254",), "172.31.255.254"),
        (("192.168.9.4",), "192.168.9.4"),
        (("203.0.113.9", "10.0.0.7"), "10.0.0.7"),
    ],
)
def test_lan_selection_accepts_every_rfc1918_range(
    addresses: tuple[str, ...], expected: str
) -> None:
    verdict = harness_preflight.decide(
        networking_mode="mirrored",
        needs_windows_boundary=False,
        addresses=addresses,
        addresses_readable=True,
    )
    assert verdict.lan_ip == expected
    assert verdict.lan_status == "selected_rfc1918"


def test_no_private_lan_address_is_recorded_loudly() -> None:
    verdict = harness_preflight.decide(
        networking_mode="mirrored",
        needs_windows_boundary=False,
        addresses=("203.0.113.9", "not-an-address"),
        addresses_readable=True,
    )
    assert verdict.lan_ip == ""
    assert "no RFC1918" in verdict.lan_status


def test_an_address_inspection_failure_is_not_an_empty_success() -> None:
    verdict = harness_preflight.decide(
        networking_mode="mirrored",
        needs_windows_boundary=False,
        addresses=(),
        addresses_readable=False,
    )
    assert verdict.lan_ip == ""
    assert "inspection failed" in verdict.lan_status
