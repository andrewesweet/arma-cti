"""Locate the headed Windows client's newest RPT across user profiles (#73)."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEFAULT_USERS_DIR = Path("/mnt/c/Users")


def newest_client_rpt(*, users_dir: Path, configured_dir: Path | None) -> Path | None:
    """Return the newest readable RPT, respecting an explicit directory boundary."""
    directories = (
        [configured_dir]
        if configured_dir is not None
        else sorted(users_dir.glob("*/AppData/Local/Arma 3"))
    )
    candidates: list[tuple[int, str, Path]] = []
    for directory in directories:
        for path in directory.glob("*.rpt"):
            try:
                modified = path.stat().st_mtime_ns
            except OSError:
                continue
            candidates.append((modified, str(path), path))
    return max(candidates)[2] if candidates else None


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the internal shell-to-Python collection contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users-dir", type=Path, default=DEFAULT_USERS_DIR)
    parser.add_argument("--configured-dir", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Copy the selected RPT and print the evidence fields the shell records."""
    args = parse_args(argv)
    path = newest_client_rpt(users_dir=args.users_dir, configured_dir=args.configured_dir)
    if path is None:
        searched = args.configured_dir if args.configured_dir is not None else args.users_dir
        print(  # noqa: T201 — shell contract
            f"windows_client_rpt=unavailable: no client .rpt under {searched}"
        )
        return 0
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, args.out)
        text = args.out.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"windows_client_rpt=unavailable: could not copy {path}: {exc}")  # noqa: T201
        return 0
    denied = text.casefold().count("is not allowed to be remotely executed")
    print(f"windows_client_rpt={args.out}")  # noqa: T201 — shell contract
    print(f"windows_client_rpt_source={path}")  # noqa: T201 — shell contract
    print(f"windows_client_remoteexec_denied={denied}")  # noqa: T201 — shell contract
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
