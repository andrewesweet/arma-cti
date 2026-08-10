"""The report cycle's save/load state methods — the seam the daemon reaches (#291).

The Campaign's `to_snapshot`/`apply_snapshot` are the mechanics (pinned in
`test_campaign_snapshot`); this pins what the cycle adds on top: a `snapshot`
that photographs the Campaign it holds, an `apply` that loads one and re-seats
the cycle's own caches on it, and the two things a load must not touch — the AI
Commanders a session wired, and the UIDs a dropped kit was reported against.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from conftest import authored_economy, rows
from test_report_cycle import _cycle, _report

if TYPE_CHECKING:
    from pathlib import Path


def test_snapshot_is_the_campaigns_own_photograph(tmp_path: Path) -> None:
    cycle, _ = _cycle(tmp_path)
    assert cycle.snapshot() == cycle.campaign.to_snapshot()


def test_a_snapshot_round_trips_into_a_fresh_cycle(tmp_path: Path) -> None:
    one, _ = _cycle(tmp_path)
    objective = next(iter(one.campaign.owners()))
    one.campaign.purchase("WEST", authored_economy().squads[0].id)
    one.campaign.observe(at_time=authored_economy().capture_seconds, presence={objective: ["WEST"]})

    snapshot = one.snapshot()
    other, _ = _cycle(tmp_path)
    dropped = other.apply(snapshot)

    assert dropped == ()
    # Tactical fields (pos/fielded) are regenerated, so the resumed Campaign's
    # photograph equals the saved one on every strategic field.
    assert other.campaign.to_snapshot() == snapshot


def test_apply_clears_the_dedup_caches_so_the_next_report_records_again(
    tmp_path: Path,
) -> None:
    # The cycle holds "said so once" caches so a report repeating itself is not
    # written down twice. A load changes the Campaign under those caches, so
    # `apply` clears them — and the proof is that the same report, folded again
    # after a load, records its kit and its observation as if for the first time.
    log = tmp_path / "telemetry.jsonl"
    cycle, _ = _cycle(tmp_path)
    cycle.fold(_report(loadouts={"uid-1": "medic"}))
    chosen_before = len(rows(log, "loadout_chosen"))
    observed_before = len(rows(log, "observation"))

    cycle.apply(cycle.snapshot())
    cycle.fold(_report(loadouts={"uid-1": "medic"}))

    assert len(rows(log, "loadout_chosen")) == chosen_before + 1, (
        "the loadout dedup cache survived the load, so a repeated kit was not re-recorded"
    )
    assert len(rows(log, "observation")) > observed_before, (
        "the observation dedup cache survived the load, so the board was not re-recorded"
    )


def test_apply_passes_through_the_uids_whose_saved_kit_is_no_longer_offered(
    tmp_path: Path,
) -> None:
    cycle, _ = _cycle(tmp_path)
    ghost = replace(cycle.snapshot(), loadouts={"uid-x": "a-kit-nobody-sells"})
    dropped = cycle.apply(ghost)
    assert dropped == ("uid-x",)


def test_a_load_does_not_unseat_the_commanders_the_session_wired(
    tmp_path: Path,
) -> None:
    # Commanders are session wiring, not Campaign state — ADR-0070 put a
    # player-led Squad's own states into the snapshot and left which slot a
    # player occupies where ADR-0025 has it, on the server — so the session that
    # loads keeps the side it put under command.
    cycle, _ = _cycle(tmp_path)
    cycle.commanded_by("WEST", cast("Any", object()))
    assert cycle.commanded("WEST")
    cycle.apply(cycle.snapshot())
    assert cycle.commanded("WEST"), "a load unseated a Commander the session had wired"
