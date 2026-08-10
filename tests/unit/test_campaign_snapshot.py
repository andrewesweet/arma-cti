"""The Campaign's snapshot/apply boundary — the daemon-owned half of ADR-0008 (#291).

`snapshot.restore(serialise(s)) == s` is the document's round trip, pinned in
`test_snapshot`. This pins the aggregate's: a `Campaign.to_snapshot` of a played
Campaign, applied to a fresh one, leaves both agreeing on every field ADR-0008
carries; a refused apply leaves the live Campaign exactly as it was; and the
tactical set ADR-0008 leaves out comes back blank for the first report after a
resume to set.

The snapshot is the sole authority for strategic state (ADR-0003), so these are
the primitives the Phase-2 `save`/`load` handlers will call — written now so the
handler lands onto tested mechanics rather than discovering them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from conftest import authored_economy, authored_loadouts, live

from cti_daemon.commands import SIDES
from cti_daemon.economy import UnknownSideError
from cti_daemon.observation import DESTROYED, INTACT
from cti_daemon.snapshot import Snapshot
from cti_daemon.squads import Held, Order

if TYPE_CHECKING:
    from cti_daemon.campaign import Campaign


def _played() -> Campaign:
    """Return a Campaign mid-play, with every strategic field off its boot value.

    Driven through the public mutating verbs rather than assembled, so the round
    trip exercises the reads `to_snapshot` makes off a live object: both sides
    have bought a Squad, one has been ordered and the world has reported it
    standing, one Objective has changed hands through a real capture, a Base's
    HQ has fallen, and a player has picked a kit. The capture's window is the
    table's own `capture_seconds`, so this is not a wait for anything to settle.
    """
    campaign = live()
    table = authored_economy()
    west_type = table.squads[0].id
    east_type = table.squads[1].id if len(table.squads) > 1 else west_type

    objective = next(iter(campaign.owners()))
    base = next(iter(campaign.headquarters()))

    campaign.purchase("WEST", west_type)
    campaign.purchase("EAST", east_type)
    # And both states a player-led Squad can be in (ADR-0070): an active shell
    # whose composition nobody has assigned, and a suspended one whose player
    # disconnected before the first fill. Both are roster Squads the snapshot
    # has to put back exactly, ids included — the shell's minted id coming back
    # with the player is the whole reason ruling 7 chose suspension over
    # dissolution.
    campaign.enrol("WEST", "uid-shell")
    suspended = campaign.enrol("EAST", "uid-away")
    campaign.suspend(suspended.id, "EAST")
    west_squad = "WEST-1"
    campaign.issue(west_squad, "WEST", Order(kind="defend", place=objective))
    # The world has seen WEST-1 standing: that turns `fielded` true and fixes a
    # position, both of which are tactical and must not survive the snapshot.
    campaign.reconcile({west_squad: Held(size=7, at=objective, pos=(3421, 5122, 0))})
    # One real capture: WEST alone in the radius for a whole capture window.
    campaign.observe(at_time=table.capture_seconds, presence={objective: ["WEST"]})
    # An HQ fallen by its own line, not through `raze` (which would end the
    # Campaign); the snapshot carries the scoreboard fact without an outcome.
    campaign._hq[base] = DESTROYED  # noqa: SLF001 — the scoreboard under test
    kit = authored_loadouts().ids()[0]
    campaign.dress("uid-1", kit)
    return campaign


def _strategic(campaign: Campaign) -> tuple:
    """Lift the fields ADR-0008 carries off a Campaign, for equality.

    Squads are projected to their persisted shape — id, side, type, size, Order,
    coarse Place — because `pos` and `fielded` are tactical and regenerated on
    the way back in, so a resumed Campaign is meant to differ there (asserted in
    its own test). Everything else is compared whole.
    """
    return (
        campaign.elapsed,
        campaign.owners(),
        campaign.headquarters(),
        campaign.ledger.holdings(),
        tuple(
            (
                squad.id,
                squad.side,
                squad.squad_type,
                squad.size,
                squad.order,
                squad.at,
                squad.player_uid,
                squad.composition_assigned,
                squad.suspended,
            )
            for squad in campaign.roster.all()
        ),
        campaign.dressed(),
    )


def test_a_played_campaign_round_trips_through_a_fresh_one() -> None:
    # The load-bearing property at the aggregate: save a played Campaign, load
    # it into one that was fresh, and the two agree on everything the snapshot
    # owns. Neither side's Funds, Squads or Orders are lost or invented.
    played = _played()
    saved = played.to_snapshot()

    resumed = live()
    resumed.apply_snapshot(saved)

    assert _strategic(resumed) == _strategic(played)


def test_save_then_load_then_save_is_the_same_snapshot() -> None:
    # One step finer than the round trip above: the document that a loaded
    # Campaign would write back is the document that was read, so a save is
    # idempotent across a load (ADR-0003's `load(save(s)) == s` at the value).
    snapshot = _played().to_snapshot()
    resumed = live()
    resumed.apply_snapshot(snapshot)
    assert resumed.to_snapshot() == snapshot


def test_a_loaded_squad_comes_back_un_fielded_with_no_position() -> None:
    # ADR-0008: position and `fielded` are tactical, regenerated at boot. The
    # played Campaign's WEST-1 was reported standing (fielded, with a position);
    # the resumed one's is not, until a report sets it.
    resumed = live()
    resumed.apply_snapshot(_played().to_snapshot())
    squad = resumed.roster.owned_by("WEST-1", "WEST")
    assert squad is not None
    assert squad.fielded is False
    assert squad.pos == ()


def test_a_loaded_campaign_is_undecided_and_holds_no_domination_clock() -> None:
    # The Domination clock is in-memory only and resets on boot
    # (docs/mvp-scope.md); a resumed Campaign has held nothing yet. An HQ fallen
    # in the save does not come back as a decided outcome, because the snapshot
    # carries no outcome (ADR-0023).
    resumed = live()
    resumed.apply_snapshot(_played().to_snapshot())
    assert resumed.outcome is None
    assert resumed._dominant == ""  # noqa: SLF001 — the boot reset under test
    assert resumed._dominated_seconds == 0.0  # noqa: SLF001 — same


def test_a_loaded_roster_mints_the_next_id_not_one_already_held() -> None:
    # A resumed Campaign has to mint the same ids in the same order (ADR-0003),
    # which means the next Purchase continues the count: a save holding WEST-1
    # and WEST-2 mints WEST-3 next, never reusing a live id.
    resumed = live()
    resumed.apply_snapshot(_played().to_snapshot())
    # The played Campaign bought one WEST Squad and enrolled one WEST shell, so
    # the save holds WEST-1 and WEST-2 — a shell counts up on the same counter.
    next_squad = resumed.purchase("WEST", authored_economy().squads[0].id)[0]
    assert next_squad.id == "WEST-3"


def test_a_loaded_shell_comes_back_as_the_shell_it_was_and_answers_to_its_player() -> None:
    # The three fields version 2 added, at the aggregate: a resumed Campaign
    # finds the same player leading the same Squad, still unassigned, and the
    # suspended one still suspended — which is what lets a reconnecting player
    # be given his own Squad back rather than a second one.
    resumed = live()
    resumed.apply_snapshot(_played().to_snapshot())

    shell = resumed.led_by("uid-shell")
    assert shell is not None
    assert (shell.id, shell.side, shell.squad_type) == ("WEST-2", "WEST", "")
    assert shell.composition_assigned is False
    assert shell.suspended is False

    away = resumed.led_by("uid-away")
    assert away is not None
    assert away.suspended is True


# --- a refused apply leaves the live Campaign untouched --------------------


def _fresh_with_captured_objective() -> Campaign:
    """Build a Campaign that differs from `live()` in a field the snapshot owns."""
    campaign = live()
    objective = next(iter(campaign.owners()))
    campaign.observe(at_time=authored_economy().capture_seconds, presence={objective: ["WEST"]})
    assert campaign.owner(objective) == "WEST", "the arrangement did not capture the objective"
    return campaign


def test_a_snapshot_naming_unknown_objectives_is_refused_and_changes_nothing() -> None:
    campaign = _fresh_with_captured_objective()
    before = _strategic(campaign)
    bad = Snapshot(
        clock=1.0,
        owners={"no-such-objective": "WEST"},
        hq=dict.fromkeys(campaign.headquarters(), INTACT),
        funds=dict.fromkeys(SIDES, 100),
        squads=(),
        loadouts={},
    )
    with pytest.raises(ValueError, match="objectives"):
        campaign.apply_snapshot(bad)
    assert _strategic(campaign) == before, "a refused load mutated the live Campaign"


def test_a_snapshot_naming_unknown_bases_is_refused_and_changes_nothing() -> None:
    campaign = _fresh_with_captured_objective()
    before = _strategic(campaign)
    bad = Snapshot(
        clock=1.0,
        owners=dict.fromkeys(campaign.owners(), "NEUTRAL"),
        hq={"no-such-base": DESTROYED},
        funds=dict.fromkeys(SIDES, 100),
        squads=(),
        loadouts={},
    )
    with pytest.raises(ValueError, match="bases"):
        campaign.apply_snapshot(bad)
    assert _strategic(campaign) == before, "a refused load mutated the live Campaign"


def test_a_snapshot_whose_funds_name_an_unknown_side_is_refused_and_changes_nothing() -> None:
    campaign = _fresh_with_captured_objective()
    before = _strategic(campaign)
    bad = Snapshot(
        clock=1.0,
        owners=dict.fromkeys(campaign.owners(), "NEUTRAL"),
        hq=dict.fromkeys(campaign.headquarters(), INTACT),
        funds={"WEST": 100, "EAST": 50, "GREEN": 1},
        squads=(),
        loadouts={},
    )
    with pytest.raises(UnknownSideError):
        campaign.apply_snapshot(bad)
    assert _strategic(campaign) == before, "a refused load mutated the live Campaign"


def test_a_snapshot_whose_funds_are_negative_is_refused_and_changes_nothing() -> None:
    campaign = _fresh_with_captured_objective()
    before = _strategic(campaign)
    bad = Snapshot(
        clock=1.0,
        owners=dict.fromkeys(campaign.owners(), "NEUTRAL"),
        hq=dict.fromkeys(campaign.headquarters(), INTACT),
        funds={"WEST": 100, "EAST": -5},
        squads=(),
        loadouts={},
    )
    with pytest.raises(ValueError, match="whole number"):
        campaign.apply_snapshot(bad)
    assert _strategic(campaign) == before, "a refused load mutated the live Campaign"


def test_a_loaded_roster_reports_kits_the_menu_no_longer_offers() -> None:
    # `apply_snapshot` returns the UIDs whose saved kit the catalogue no longer
    # offers, so a resume can name a player put back into a default rather than
    # dress him in silence (ADR-0008's forward-compatibility rule).
    campaign = live()
    dropped_kit = "a-kit-nobody-sells"
    snapshot = Snapshot(
        clock=0.0,
        owners=dict.fromkeys(campaign.owners(), "NEUTRAL"),
        hq=dict.fromkeys(campaign.headquarters(), INTACT),
        funds=dict.fromkeys(SIDES, campaign.ledger.balance("WEST")),
        squads=(),
        loadouts={"uid-1": authored_loadouts().ids()[0], "uid-2": dropped_kit},
    )
    dropped = campaign.apply_snapshot(snapshot)
    assert dropped == ("uid-2",)
