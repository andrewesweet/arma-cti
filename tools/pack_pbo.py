r"""Pack a directory into an Arma 3 PBO.

HEMTT packs addons but has no mission packer (`hemtt utils pbo` only extracts,
inspects and unpacks), and an unpacked mission folder cannot be transmitted to a
joining client — so missions need a packer of their own.

Format, per the community wiki's PBO description:

  * optional version entry: empty filename, packing method 0x56657273 ("Vers"),
    four zero uint32s, then NUL-terminated key/value strings ended by an empty key
  * one entry per file: NUL-terminated `back\\slashed` name, then five little-endian
    uint32s (packing method, original size, reserved, timestamp, data size)
  * terminating entry: empty filename and five zero uint32s
  * file data, concatenated in header order
  * one zero byte, then the SHA-1 of everything written so far
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

VERSION_MAGIC = 0x56657273  # "Vers"


# The two header fields the format defines and nothing reads: `reserved`, and a
# timestamp Arma does not use. Written as zero rather than as a clock reading, so
# the same directory packs to the same bytes (#90 asked for them to be named).
RESERVED = 0
TIMESTAMP = 0


def _entry(*, name: str, packing: int, original: int, size: int) -> bytes:
    """Render one header entry.

    Keyword-only on purpose: four adjacent uint32s in a binary format is a shape
    where transposing two arguments compiles, packs, and corrupts the PBO.
    """
    return (
        name.encode("utf-8")
        + b"\0"
        + struct.pack("<5I", packing, original, RESERVED, TIMESTAMP, size)
    )


def build_pbo(source: Path, properties: dict[str, str] | None = None) -> bytes:
    """Return the PBO bytes for every file under `source`, sorted for determinism."""
    files = sorted(p for p in source.rglob("*") if p.is_file())
    if not files:
        msg = f"nothing to pack: {source} contains no files"
        raise ValueError(msg)

    header = bytearray(_entry(name="", packing=VERSION_MAGIC, original=0, size=0))
    for key, value in (properties or {}).items():
        header += key.encode("utf-8") + b"\0" + value.encode("utf-8") + b"\0"
    header += b"\0"

    payloads: list[bytes] = []
    for path in files:
        data = path.read_bytes()
        name = str(path.relative_to(source)).replace("/", "\\")
        header += _entry(name=name, packing=0, original=len(data), size=len(data))
        payloads.append(data)
    header += _entry(name="", packing=0, original=0, size=0)

    body = bytes(header) + b"".join(payloads)
    return body + b"\0" + hashlib.sha1(body).digest()  # noqa: S324 - the format mandates SHA-1


def main(argv: list[str] | None = None) -> int:
    """Pack `source` into `output`."""
    parser = argparse.ArgumentParser(description="Pack a directory into an Arma 3 PBO.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--prefix",
        default=None,
        help="value for the PBO's `prefix` property; omit for missions",
    )
    args = parser.parse_args(argv)

    properties = {"prefix": args.prefix} if args.prefix else {}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(build_pbo(args.source, properties))
    print(f"{args.output} ({args.output.stat().st_size} bytes)")  # noqa: T201 - CLI output
    return 0


if __name__ == "__main__":
    sys.exit(main())
