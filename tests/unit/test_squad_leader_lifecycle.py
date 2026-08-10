"""What the observe report's `squad_leaders` does to a Campaign (#312).

#310 gave the daemon every verb ADR-0070 needs — `enrol`, `suspend`,
`reactivate`, `first_fill` — and #74's schema gave the report a field to carry
the claim in. Nothing joined the two: `report.parse` read `squad_leaders` and no
caller ever looked at it, so a player could take a slot and the Campaign would
never hear of it. This is that fold, and the four rulings it has to land are
ruling 1 (a claim mints a shell at own Base), ruling 7 (an unfilled shell whose
player stops being named is suspended), ruling 5 (a filled Squad's is not) and
ruling 6 (a returning player leads the same Squad again).

The Campaign's own lifecycle is `test_player_shell`'s and the roster's is
`test_squads`'; what is pinned here is which verb the cycle calls, on what
evidence, and how often.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from conftest import rows
from test_port import EAST_BASE, WEST_BASE

from cti_daemon.report import Report
from cti_daemon.squads import Held, Order
from cti_daemon.transport import build_daemon

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.daemon import Daemon
    from cti_daemon.squads import Squad

# The authored rifle Squad, as `test_player_shell` reads it: eight men for 100,
# so a first fill of a shell whose player is already standing is seven eighths.
RIFLE = "rifle"
UID = "76561198000000001"


def _report(**named: Any) -> Report:  # noqa: ANN401 — a report is a document
    """One observe report, with the fields a test varies and nothing else."""
    return Report(
        at_time=named.get("at_time", 10.0),
        presence=named.get("presence", {}),
        squads=named.get("squads"),
        contacts=None,
        hq=None,
        casualties=None,
        loadouts=None,
        squad_leaders=named.get("squad_leaders"),
    )


def _daemon(tmp_path: Path) -> Daemon:
    """Build a stock daemon on this checkout's authored map, economy and menu."""
    return build_daemon(telemetry_path=tmp_path / "telemetry.jsonl", archive_path=tmp_path / "arch")


def _enrolments(daemon: Daemon) -> list[dict[str, Any]]:
    """Every enrolment effect the Campaign has pushed, in order."""
    return [
        dict(entry.effect.args)
        for entry in daemon.campaign.outbox.pending()
        if entry.effect.name == "squad_enrolled"
    ]


def _led(daemon: Daemon, uid: str = UID) -> Squad:
    """Return the Squad that player leads, refusing a test that thinks he leads one."""
    squad = daemon.campaign.led_by(uid)
    assert squad is not None, f"{uid} leads no Squad"
    return squad


def _filled(daemon: Daemon) -> Squad:
    """Return a player's shell, filled by his Commander and standing in the world.

    Driven through the fold rather than by calling `enrol` directly, because
    what the filled cases are about is a Squad the report has already named — a
    shell the world has never reported is exempt from reconciliation for a
    reason of its own, and arranging one that way would test the exemption
    instead of ruling 5.
    """
    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))
    shell = _led(daemon)
    daemon.campaign.first_fill(shell.id, "WEST", RIFLE)
    daemon.campaign.issue(shell.id, "WEST", Order("defend", WEST_BASE))
    daemon.cycle.fold(
        _report(
            squads={shell.id: Held(size=8, at=WEST_BASE, pos=(1987, 5625))},
            squad_leaders={UID: "WEST"},
        )
    )
    return shell


# --- ruling 1: a claim mints a shell ---------------------------------------


def test_a_reported_slot_mints_a_shell_at_own_base_for_that_side(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)

    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))

    shell = _led(daemon)
    assert (shell.side, shell.size, shell.at) == ("WEST", 1, WEST_BASE)
    assert shell.composition_assigned is False
    assert shell.suspended is False


def test_the_claim_is_read_as_the_side_it_names(tmp_path: Path) -> None:
    # The report says which side's slot he is standing in, and the shell is that
    # side's. Pinned because "WEST" is the default everywhere else in this file
    # and a fold that ignored the argument would pass every test above.
    daemon = _daemon(tmp_path)

    daemon.cycle.fold(_report(squad_leaders={UID: "EAST"}))

    shell = _led(daemon)
    assert (shell.side, shell.at) == ("EAST", EAST_BASE)


def test_the_world_is_told_which_group_answers_to_the_minted_id(tmp_path: Path) -> None:
    # Without the pairing no Order can reach the Squad, which is the whole of
    # why enrolment is an effect at all.
    daemon = _daemon(tmp_path)

    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))

    assert _enrolments(daemon) == [{"squad": _led(daemon).id, "player": UID}]


def test_a_player_who_is_simply_still_there_is_enrolled_once(tmp_path: Path) -> None:
    # Reports arrive every few seconds and say the same thing. A shell per report
    # would be a roster of duplicates; an enrolment effect per report would be an
    # outbox the world never drains.
    daemon = _daemon(tmp_path)

    for _ in range(3):
        daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))

    assert len(daemon.campaign.roster.all()) == 1
    assert len(_enrolments(daemon)) == 1


def test_a_report_that_says_nothing_about_slots_changes_nothing(tmp_path: Path) -> None:
    # Absent is not empty, and it matters more here than for Squads: reading
    # silence as "nobody is leading" would suspend every shell on the first
    # report from a world whose sampler had not started.
    daemon = _daemon(tmp_path)
    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))

    daemon.cycle.fold(_report())

    assert _led(daemon).suspended is False


# --- ruling 7: the unfilled shell is suspended when he goes ----------------


def test_a_report_that_stops_naming_him_suspends_his_unfilled_shell(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))
    minted = _led(daemon).id

    daemon.cycle.fold(_report(squad_leaders={}))

    shell = _led(daemon)
    assert shell.id == minted, "suspension is not dissolution: the roster identity stays"
    assert (shell.suspended, shell.size) == (True, 0)


def test_suspension_is_said_once_rather_than_on_every_report(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = _daemon(tmp_path)
    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))

    for _ in range(3):
        daemon.cycle.fold(_report(squad_leaders={}))

    assert [row["uid"] for row in rows(log, "squad_leader_suspended")] == [UID]


def test_a_shell_that_was_never_claimed_is_not_suspended_by_an_empty_report(
    tmp_path: Path,
) -> None:
    # `active_shells` is derived from the Campaign rather than from what this
    # session happens to remember, so the claim has to be the thing that decides
    # — not merely the absence of a cache entry.
    daemon = _daemon(tmp_path)
    daemon.campaign.enrol("WEST", UID)

    daemon.cycle.fold(_report(squad_leaders={}))

    assert _led(daemon).suspended is True


# --- ruling 5: a filled Squad survives its player leaving ------------------


def test_a_filled_squads_player_leaving_leaves_it_active_and_ordered(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    shell = _filled(daemon)

    daemon.cycle.fold(
        _report(squads={shell.id: Held(size=8, at=WEST_BASE, pos=(1987, 5625))}, squad_leaders={})
    )

    still = _led(daemon)
    assert still.id == shell.id
    assert still.suspended is False, "ruling 5: a filled Squad is never suspended"
    assert still.size == 8
    assert still.order == Order("defend", WEST_BASE)


def test_a_filled_squad_contributes_presence_after_its_player_has_gone(tmp_path: Path) -> None:
    # "Goes on contributing presence" is the world's doing — its AI members are
    # still standing — so what the daemon owes is not to remove them from the
    # roster the sampler's Squads are reconciled against.
    daemon = _daemon(tmp_path)
    shell = _filled(daemon)

    daemon.cycle.fold(
        _report(squads={shell.id: Held(size=8, at=WEST_BASE, pos=(1987, 5625))}, squad_leaders={})
    )

    assert [squad.id for squad in daemon.campaign.roster.roll("WEST")] == [shell.id]


# --- the acceptance criterion: it does not drop out of the Campaign --------


def test_a_shell_survives_a_report_cycle_in_which_its_player_is_dead(tmp_path: Path) -> None:
    # ADR-0052 makes a player's death a thirty-second certainty and #189
    # measured that no AI is promoted for the whole window, so `fn_squadSample`
    # — which counts living men and omits a Squad at zero — stops naming a
    # shell whose one man is a corpse. He is still occupying the slot, so the
    # claim keeps arriving; the Squad must still be on the roster afterwards.
    daemon = _daemon(tmp_path)
    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))
    minted = _led(daemon).id

    daemon.cycle.fold(_report(squads={}, squad_leaders={UID: "WEST"}))

    shell = _led(daemon)
    assert shell.id == minted
    assert shell.suspended is False
    assert daemon.campaign.squad(minted, "WEST") is not None


# --- ruling 6: he comes back ----------------------------------------------


def test_a_returning_player_gets_the_same_shell_back_at_own_base(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))
    minted = _led(daemon).id
    daemon.cycle.fold(_report(squad_leaders={}))

    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))

    back = _led(daemon)
    assert back.id == minted, "the minted id is what suspension was chosen to preserve"
    assert (back.suspended, back.size, back.at) == (False, 1, WEST_BASE)
    assert back.composition_assigned is False


def test_a_returning_player_is_seated_in_the_world_again(tmp_path: Path) -> None:
    # He reconnects on a group the server has never paired with this id, so the
    # pairing has to be sent again — for a shell and for a filled Squad alike.
    daemon = _daemon(tmp_path)
    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))
    daemon.cycle.fold(_report(squad_leaders={}))

    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))

    assert _enrolments(daemon) == [{"squad": _led(daemon).id, "player": UID}] * 2


def test_a_returning_player_rejoins_his_filled_squad_and_nothing_strategic_moves(
    tmp_path: Path,
) -> None:
    daemon = _daemon(tmp_path)
    shell = _filled(daemon)
    held = Held(size=8, at=WEST_BASE, pos=(1987, 5625))
    funds = daemon.campaign.ledger.balance("WEST")
    daemon.cycle.fold(_report(squads={shell.id: held}, squad_leaders={}))
    before = len(_enrolments(daemon))

    daemon.cycle.fold(_report(squads={shell.id: held}, squad_leaders={UID: "WEST"}))

    assert _enrolments(daemon)[before:] == [{"squad": shell.id, "player": UID}]
    assert daemon.campaign.ledger.balance("WEST") == funds
    still = _led(daemon)
    assert (still.size, still.order) == (8, Order("defend", WEST_BASE))
    assert still.suspended is False


def test_a_player_whose_filled_squad_was_wiped_out_gets_a_fresh_shell(tmp_path: Path) -> None:
    # The case the fold's position after `reconcile` decides, and the one the
    # arrival cache must not swallow. A Squad wiped out to the last man takes
    # its player's corpse with it, so `fn_squadSample` stops naming it and
    # `reconcile` removes it — while he is still standing in his slot and still
    # being claimed. What he is owed on the same report is a shell, not a
    # reference to a Squad that no longer exists.
    daemon = _daemon(tmp_path)
    lost = _filled(daemon).id

    daemon.cycle.fold(_report(squads={}, squad_leaders={UID: "WEST"}))

    fresh = _led(daemon)
    assert fresh.id != lost
    assert fresh.composition_assigned is False
    assert daemon.campaign.squad(lost, "WEST") is None


# --- the edges ------------------------------------------------------------


def test_a_claim_naming_a_side_his_squad_is_not_on_is_recorded_and_left_alone(
    tmp_path: Path,
) -> None:
    # Not a case ADR-0070 ruled on — it needs him to have left one side's slot
    # and taken the other's — and a Squad cannot change sides. So the roster's
    # answer stands and the disagreement is written down rather than resolved
    # by minting him a second Squad that `led_by` could not choose between.
    log = tmp_path / "telemetry.jsonl"
    daemon = _daemon(tmp_path)
    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))
    minted = _led(daemon).id

    daemon.cycle.fold(_report(squad_leaders={UID: "EAST"}))

    assert len(daemon.campaign.roster.all()) == 1
    assert _led(daemon).id == minted
    assert [row["held"] for row in rows(log, "squad_leader_wrong_side")] == ["WEST"]


def test_a_won_campaign_takes_no_claim(tmp_path: Path) -> None:
    # Every verb the fold would call refuses a finished Campaign outright, so
    # this is a guard rather than a preference: the world does not know it is
    # over until the effect reaches it and goes on reporting in the meantime.
    daemon = _daemon(tmp_path)
    daemon.campaign.raze(EAST_BASE, at_time=5.0)

    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))

    assert daemon.campaign.led_by(UID) is None


def test_a_resumed_campaign_re_seats_the_player_standing_in_the_slot(tmp_path: Path) -> None:
    # A loaded Campaign is played in a world whose groups this daemon has never
    # paired with a minted id, so the first report after a load has to send the
    # pairing rather than read an unchanged claim as nothing to do (#314 spelled
    # the verbs; this is the fold calling them).
    daemon = _daemon(tmp_path)
    daemon.cycle.fold(_report(squad_leaders={UID: "WEST"}))
    saved = daemon.cycle.snapshot()
    resumed = _daemon(tmp_path / "resumed")
    resumed.cycle.apply(saved)
    assert _enrolments(resumed) == []

    resumed.cycle.fold(_report(squad_leaders={UID: "WEST"}))

    assert _enrolments(resumed) == [{"squad": _led(resumed).id, "player": UID}]
