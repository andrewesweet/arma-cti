"""Structural tests for the PBO packer.

The authoritative round-trip check is `hemtt utils pbo inspect`, which validates
the SHA-1 trailer; these tests keep the header arithmetic honest without HEMTT.
"""

from __future__ import annotations

import hashlib
import importlib.util
import struct
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SPEC = importlib.util.spec_from_file_location(
    "pack_pbo", Path(__file__).parents[2] / "tools" / "pack_pbo.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
pack_pbo: ModuleType = importlib.util.module_from_spec(_SPEC)
sys.modules["pack_pbo"] = pack_pbo
_SPEC.loader.exec_module(pack_pbo)


def _read_entries(blob: bytes) -> tuple[list[tuple[str, int, int]], int]:
    """Return the header entries and the offset at which file data begins."""
    entries: list[tuple[str, int, int]] = []
    pos = 0
    while True:
        end = blob.index(b"\0", pos)
        name = blob[pos:end].decode("utf-8")
        pos = end + 1
        packing, original, _, _, size = struct.unpack_from("<5I", blob, pos)
        pos += 20
        if name == "" and packing == pack_pbo.VERSION_MAGIC:
            while blob[pos] != 0:  # property strings, terminated by an empty key
                pos = blob.index(b"\0", pos) + 1
            pos += 1
            continue
        if name == "" and packing == 0 and size == 0:
            return entries, pos
        entries.append((name, original, size))


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    root = tmp_path / "spike.Stratis"
    (root / "sub").mkdir(parents=True)
    (root / "mission.sqm").write_bytes(b"version=54;\n")
    (root / "sub" / "init.sqf").write_bytes(b'diag_log "hi";\n')
    return root


def test_entries_carry_backslashed_relative_names(sample: Path) -> None:
    entries, _ = _read_entries(pack_pbo.build_pbo(sample))
    assert [name for name, _, _ in entries] == ["mission.sqm", "sub\\init.sqf"]


def test_sizes_match_the_source_files(sample: Path) -> None:
    entries, _ = _read_entries(pack_pbo.build_pbo(sample))
    assert {name: size for name, _, size in entries} == {
        "mission.sqm": 12,
        "sub\\init.sqf": 15,
    }


def test_data_follows_the_header_in_entry_order(sample: Path) -> None:
    blob = pack_pbo.build_pbo(sample)
    entries, offset = _read_entries(blob)
    for _, _, size in entries:
        chunk, offset = blob[offset : offset + size], offset + size
        assert len(chunk) == size
    assert blob[offset] == 0, "file data must be followed by the zero byte"


def test_trailer_is_the_sha1_of_everything_before_it(sample: Path) -> None:
    blob = pack_pbo.build_pbo(sample)
    body, trailer = blob[:-20], blob[-20:]
    assert trailer == hashlib.sha1(body[:-1]).digest()  # noqa: S324 - format mandates SHA-1


def test_prefix_property_is_written_when_given(sample: Path) -> None:
    assert b"prefix\0z\\cti\0" in pack_pbo.build_pbo(sample, {"prefix": "z\\cti"})


def test_empty_directory_is_an_error_not_an_empty_pbo(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="nothing to pack"):
        pack_pbo.build_pbo(tmp_path / "empty")


def test_output_is_deterministic(sample: Path) -> None:
    assert pack_pbo.build_pbo(sample) == pack_pbo.build_pbo(sample)
