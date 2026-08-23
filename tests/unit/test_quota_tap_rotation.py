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

import json
import os
import re
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

from conftest import REPO

if TYPE_CHECKING:
    from pathlib import Path

QUOTA_TAP = REPO / "tools" / "quota_tap.sh"

# Every spooled line is an envelope (#488): the render's own timestamp under
# `ts`, the payload byte-identical under `payload`. The timestamp's presence and
# shape are asserted per line rather than per file, because one untimestamped
# line is one render no period can hold.
TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


def spooled(path: Path) -> list[dict[str, object]]:
    """Read one spool file's envelopes, asserting the timestamp contract."""
    lines = [line for line in path.read_text().splitlines() if line]
    envelopes = [json.loads(line) for line in lines]
    for envelope in envelopes:
        ts = envelope.get("ts")
        assert isinstance(ts, str), f"no timestamp: {envelope}"
        assert TS_PATTERN.match(ts), f"timestamp not ISO: {ts}"
        datetime.fromisoformat(ts)
    return envelopes


def payloads(path: Path) -> list[object]:
    """One spool file's payloads, in order — the content the rotation moves."""
    return [envelope["payload"] for envelope in spooled(path)]


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

    assert payloads(spool) == [{"n": 1}, {"n": 2}]
    assert not (spool.parent / "statusline.jsonl.1").exists()


def test_rolled_content_moves_down_the_generations_in_order(tmp_path: Path) -> None:
    spool = tmp_path / "statusline.jsonl"

    # A cap of one byte makes every render after the first roll the spool.
    for n in range(1, 5):
        tap(spool, f'{{"n":{n}}}', max_bytes=1, keep=8)

    assert payloads(spool) == [{"n": 4}]
    assert payloads(spool.parent / "statusline.jsonl.1") == [{"n": 3}]
    assert payloads(spool.parent / "statusline.jsonl.2") == [{"n": 2}]
    assert payloads(spool.parent / "statusline.jsonl.3") == [{"n": 1}]


def test_the_oldest_generation_is_dropped_rather_than_accumulating(
    tmp_path: Path,
) -> None:
    spool = tmp_path / "statusline.jsonl"

    for n in range(1, 8):
        tap(spool, f'{{"n":{n}}}', max_bytes=1, keep=3)

    # `keep` counts rolled generations, so keep=3 is `.1` through `.3` beside
    # the live spool — four payloads of history — and never a `.4`.
    assert payloads(spool) == [{"n": 7}]
    assert payloads(spool.parent / "statusline.jsonl.1") == [{"n": 6}]
    assert payloads(spool.parent / "statusline.jsonl.2") == [{"n": 5}]
    assert payloads(spool.parent / "statusline.jsonl.3") == [{"n": 4}]
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
