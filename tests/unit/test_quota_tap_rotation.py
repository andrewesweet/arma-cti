"""Tests for the quota spool's generational rollover in `tools/quota_tap.sh`.

The spool is the only per-session record of cost, tokens, duration and lines
changed for sessions that no dispatch covers — the orchestrator's own turns and
the human's interactive ones. Until this change it rolled over exactly once, so
each roll destroyed everything older than the previous generation and the file
was a two-generation window rather than a history.

The rotation is pinned by *driving the real script*, never by reimplementing its
arithmetic here: a test that recomputed the generation shuffle would agree with
itself whatever the shell did. Each case feeds the tap a payload on stdin with a
byte cap small enough to force a roll, then reads what is on disk.

Two directions, because a rotation fails in opposite ways. **Forward**: content
must move down the generations in order and the live spool must always end up
holding only the newest payload. **Backward**: nothing rolls while the spool is
under its cap, and the oldest generation is dropped rather than accumulating
without bound — an unbounded spool is the disk-filler the cap exists to stop.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

from conftest import REPO

if TYPE_CHECKING:
    from pathlib import Path

QUOTA_TAP = REPO / "tools" / "quota_tap.sh"


def tap(spool: Path, payload: str, *, max_bytes: int, keep: int | None = None) -> None:
    """Render one status line through the tap, with the spool under `spool`."""
    # The ambient environment is inherited rather than replaced, because the
    # shell mutation arm traces the script through variables it injects and a
    # wiped environment makes this module look as though it executed nothing.
    env = {
        **os.environ,
        "HOME": str(spool.parent),
        "CTI_QUOTA_SPOOL": str(spool),
        "CTI_QUOTA_MAX": str(max_bytes),
        "CTI_QUOTA_OAUTH": "0",  # no endpoint refresh: this tests rotation only
    }
    if keep is not None:
        env["CTI_QUOTA_KEEP"] = str(keep)
    subprocess.run(  # noqa: S603 — this repo's own shell tool, fixed argv
        ["/bin/bash", str(QUOTA_TAP)],
        check=True,
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )


def test_a_spool_under_its_cap_does_not_roll(tmp_path: Path) -> None:
    spool = tmp_path / "statusline.jsonl"

    tap(spool, '{"n":1}', max_bytes=1_000_000)
    tap(spool, '{"n":2}', max_bytes=1_000_000)

    assert spool.read_text() == '{"n":1}\n{"n":2}\n'
    assert not (spool.parent / "statusline.jsonl.1").exists()


def test_rolled_content_moves_down_the_generations_in_order(tmp_path: Path) -> None:
    spool = tmp_path / "statusline.jsonl"

    # A cap of one byte makes every render after the first roll the spool.
    for n in range(1, 5):
        tap(spool, f'{{"n":{n}}}', max_bytes=1, keep=8)

    assert spool.read_text() == '{"n":4}\n'
    assert (spool.parent / "statusline.jsonl.1").read_text() == '{"n":3}\n'
    assert (spool.parent / "statusline.jsonl.2").read_text() == '{"n":2}\n'
    assert (spool.parent / "statusline.jsonl.3").read_text() == '{"n":1}\n'


def test_the_oldest_generation_is_dropped_rather_than_accumulating(
    tmp_path: Path,
) -> None:
    spool = tmp_path / "statusline.jsonl"

    for n in range(1, 8):
        tap(spool, f'{{"n":{n}}}', max_bytes=1, keep=3)

    # `keep` counts rolled generations, so keep=3 is `.1` through `.3` beside
    # the live spool — four payloads of history — and never a `.4`.
    assert spool.read_text() == '{"n":7}\n'
    assert (spool.parent / "statusline.jsonl.1").read_text() == '{"n":6}\n'
    assert (spool.parent / "statusline.jsonl.2").read_text() == '{"n":5}\n'
    assert (spool.parent / "statusline.jsonl.3").read_text() == '{"n":4}\n'
    assert not (spool.parent / "statusline.jsonl.4").exists()


def test_the_tap_still_passes_the_payload_downstream(tmp_path: Path) -> None:
    """Rotation must not disturb the tap's actual job: rendering a status line."""
    spool = tmp_path / "statusline.jsonl"
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "CTI_QUOTA_SPOOL": str(spool),
        "CTI_QUOTA_MAX": "1",
        "CTI_QUOTA_OAUTH": "0",
    }
    result = subprocess.run(  # noqa: S603 — this repo's own shell tool, fixed argv
        ["/bin/bash", str(QUOTA_TAP), "cat"],
        check=True,
        input='{"n":1}',
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout == '{"n":1}\n'
