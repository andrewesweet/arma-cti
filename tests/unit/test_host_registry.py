"""Machine-scoped host registry contract (ADR-0032, issue #53)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

host_registry = load_tool("host_registry")

REGISTRY = """
version = 1

[hosts.local]
ssh_target = ""
server_slots = 6
headed_client = true
human = true
client_driver = "windows"
remote_root = ""

[hosts.bravo]
ssh_target = "bravo-lan"
server_slots = 3
headed_client = true
human = false
client_driver = "proton"
remote_root = "/home/cti/.arma-cti/staging"
"""


def write(tmp_path: Path, text: str = REGISTRY) -> Path:
    path = tmp_path / "hosts.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_absent_registry_preserves_the_local_host(tmp_path: Path) -> None:
    """The fallback's whole shape, slot count included.

    The slot count is pinned here rather than left as a detail because another
    module rests on it: `tests/unit/test_host_seam.py` writes a fixture registry
    whose only observable difference from this fallback is `server_slots`, and
    that difference is what proves the fixture is being read at all.

    This pin is the shape of the fallback, not the canary's guard — it compares
    `default_hosts()` against the symbol it is written from, so it cannot fail
    when `MAX_SLOTS` itself moves. What guards the canary against every edit is
    `test_the_fixture_registry_differs_from_the_fallback`, which asserts the
    difference and rests on neither literal (#356).
    """
    hosts = host_registry.load(tmp_path / "absent.toml")
    assert list(hosts) == ["local"]
    assert hosts["local"].transport == "null"
    assert hosts["local"].human is True
    assert hosts["local"].server_slots == host_registry.MAX_SLOTS


def test_bravo_is_one_whole_pass_ssh_host(tmp_path: Path) -> None:
    hosts = host_registry.load(write(tmp_path))
    assert hosts["bravo"] == host_registry.Host(
        name="bravo",
        ssh_target="bravo-lan",
        server_slots=3,
        headed_client=True,
        human=False,
        client_driver="proton",
        remote_root="/home/cti/.arma-cti/staging",
    )


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('ssh_target = "bravo-lan"', 'ssh_target = "-oProxyCommand=bad"', "SSH alias"),
        ("server_slots = 3", "server_slots = 7", "1..6"),
        (
            'remote_root = "/home/cti/.arma-cti/staging"',
            'remote_root = "relative"',
            "absolute",
        ),
        ('client_driver = "proton"', 'client_driver = "experimental"', "one of"),
        ("headed_client = true", "headed_client = false", "disagree"),
    ],
)
def test_transport_values_fail_closed(tmp_path: Path, old: str, new: str, message: str) -> None:
    with pytest.raises(host_registry.RegistryError, match=message):
        host_registry.load(write(tmp_path, REGISTRY.replace(old, new, 1)))


def test_unknown_key_is_not_silently_ignored(tmp_path: Path) -> None:
    text = REGISTRY.replace('ssh_target = "bravo-lan"', 'ssh_target = "bravo-lan"\nfallback = true')
    with pytest.raises(host_registry.RegistryError, match=r"unknown .*fallback"):
        host_registry.load(write(tmp_path, text))


def test_shell_rows_carry_every_field_without_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host_registry.emit_shell(host_registry.load(write(tmp_path)))
    rows = capsys.readouterr().out.splitlines()
    assert rows[0] == "local\thuman\tnull\t-\t6\t1\twindows\t-"
    assert rows[1] == ("bravo\ttier\tssh\tbravo-lan\t3\t1\tproton\t/home/cti/.arma-cti/staging")
