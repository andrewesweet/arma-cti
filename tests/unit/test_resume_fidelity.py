"""Resume fidelity for a player-led Squad, through the real save and load path (#314).

#310 landed the document half: snapshot version 2, the additive 1->2 migration and
the three roster fields, round-tripped at the pure `serialise`/`restore` boundary
(`test_snapshot`) and at the aggregate's `to_snapshot`/`apply_snapshot` boundary
(`test_campaign_snapshot`). What a schema test cannot answer is whether a resumed
Campaign is *playable* from where the save left it, and that is what is pinned
here — through the daemon's own control lane and a real `SnapshotStore` on disk,
across a Play Session boundary rather than inside one aggregate.

The Play Session boundary is the whole arrangement. ADR-0070's rulings 5, 6 and 7
are about a player who goes away and comes back, and the Arma world does not exist
between sessions (ADR-0008) — so every test below saves from one daemon and loads
into a *second* one built over the same store directory. A resumed Campaign that
happened to be the same object in memory would prove nothing about either ruling.

Three things stay where the decisions put them, and each is asserted rather than
assumed:

- `pos` and `fielded` are tactical and regenerated (ADR-0008), and a shell is no
  exception. The strategic facts are *composition-unassigned* and *suspended*;
  where the player was standing is not one of them.
- The Funds claim of ruling 7 is an assertion across the whole cycle, not a
  comment: enrol, suspend, save, load and reactivate move nothing.
- The once-only first fill (ruling 3) is once-only across the resume too.

What is *not* here, and where it lives instead: the world-side lifecycle of the
slot — a player occupying it, disconnecting and reclaiming leadership on a new
machine — is #312's, and the report's `squad_leaders` half is parsed
(`report.py`) but not yet folded into the Campaign. So "the player returns" is
spelled here as the Campaign verbs a fold would call (`led_by`, `reactivate`),
which is the daemon's half of ruling 6 and the half a save and a load can decide.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from conftest import authored_economy, starting_funds
from test_port import EAST_BASE, WEST_BASE

from cti_daemon import snapshot, transport
from cti_daemon.daemon import Daemon
from cti_daemon.squads import Held, Order
from cti_daemon.store import (
    CHECKSUM_ALGORITHM,
    CURRENT,
    DIR_MODE,
    FRAME_VERSION,
    SnapshotStore,
    checksum,
)

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.campaign import Campaign

# The authored rifle Squad every arrangement below is written against: price 100,
# size 8, so a first fill for a player already standing is 70 and an ordinary
# Reinforce of three missing men is 30 (ADR-0070 ruling 3's own worked example).
RIFLE = "rifle"

# The three field names version 2 added to a squad record (ADR-0070). Named here
# because a version-1 save is defined by their absence, and `_version_one` below
# has to be able to say it really removed them.
VERSION_TWO_FIELDS = frozenset({"player", "assigned", "suspended"})


# --- the two Play Sessions, and the store they share -----------------------


def _session(tmp_path: Path, name: str) -> Daemon:
    """Bring up one Play Session's daemon over the store every session shares.

    A fresh daemon each time, deliberately: a resumed Campaign has to come back
    out of the bytes rather than out of a live object that never went away. The
    telemetry path is per-session so two sessions' rows do not interleave, and the
    store directory is not, because the store is the thing being resumed through.
    """
    return Daemon(
        wiring=transport.wire(telemetry_path=tmp_path / f"{name}.jsonl"),
        store=SnapshotStore(tmp_path / "saves"),
    )


def _control(daemon: Daemon, request_id: str, verb: str) -> dict[str, Any]:
    """Send one save or load down the control lane and return its decoded reply."""
    return json.loads(
        daemon.handle_control_line(json.dumps({"id": request_id, "verb": verb, "payload": {}}))
    )


def _saved(daemon: Daemon, request_id: str = "s-1") -> dict[str, Any]:
    """Save through the real path, refusing to continue on anything but an ack."""
    reply = _control(daemon, request_id, "save")
    assert reply["status"] == "ok", f"the arrangement's save was refused: {reply}"
    return reply


def _loaded(daemon: Daemon, request_id: str = "l-1") -> dict[str, Any]:
    """Load through the real path, refusing to continue on anything but an ack."""
    reply = _control(daemon, request_id, "load")
    assert reply["status"] == "ok", f"the arrangement's load was refused: {reply}"
    return reply


def _command(
    daemon: Daemon, request_id: str, name: str, side: str, args: dict[str, object]
) -> dict[str, Any]:
    """Submit one Command down the command lane, as a Commander's UI would."""
    return json.loads(
        daemon.handle_line(
            json.dumps(
                {
                    "id": request_id,
                    "verb": "command",
                    "payload": {
                        "command": name,
                        "side": side,
                        "acting_side": side,
                        "args": args,
                    },
                }
            )
        )
    )


# --- what the snapshot owns, lifted for equality ---------------------------


def _price(squad_type: str) -> int:
    """Return the authored price of a Squad type, narrowed off the table's forgiving read.

    The assert is a narrowing on the arrangement rather than a claim about the
    code under test, exactly as `conftest.funds_after_buying`'s is: a Squad type
    the authored menu does not sell means this call is misspelt.
    """
    price = authored_economy().price(squad_type)
    assert price is not None, f"the authored economy sells no {squad_type!r} Squad"
    return price


def _persisted(campaign: Campaign) -> tuple[tuple[object, ...], ...]:
    """Lift every Squad's persisted shape off a Campaign, in roster order.

    Exactly the criterion's list — id, side, composition, size, Order, coarse
    Place, owning UID and both state flags — and nothing tactical. `pos` and
    `fielded` are left out because a resumed Campaign is *meant* to differ there
    (ADR-0008), which is asserted on its own below rather than smuggled into an
    equality that would then have to be weakened.
    """
    return tuple(
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
    )


def _three_kinds(daemon: Daemon) -> None:
    """Play a Campaign into all three states a Squad can now be in (ADR-0070).

    An ordinary bought Squad under a standing Order that the world has reported
    standing somewhere; an active, composition-unassigned shell owned by a UID;
    and a suspended shell on the other side. Driven through the Command lane and
    the Campaign's own verbs rather than assembled, so what is saved is what a
    played Campaign actually holds.
    """
    bought = _command(daemon, "c-1", "purchase", "WEST", {"squad_type": RIFLE})
    assert bought["status"] == "ok", bought
    squad_id = bought["result"]["squad"]
    ordered = _command(
        daemon, "c-2", "order", "WEST", {"squad": squad_id, "order": "capture", "place": "girna"}
    )
    assert ordered["status"] == "ok", ordered

    shell = daemon.campaign.enrol("WEST", "uid-lead")
    away = daemon.campaign.enrol("EAST", "uid-away")
    daemon.campaign.suspend(away.id, "EAST")

    # The world has seen both of the standing Squads: that fixes a position and
    # turns `fielded` true on each, neither of which may survive the save.
    daemon.campaign.reconcile(
        {
            squad_id: Held(size=6, at="girna", pos=(4180, 5230, 0)),
            shell.id: Held(size=1, at=WEST_BASE, pos=(1987, 5625, 0)),
        }
    )


# --- criterion 1: all three kinds survive the real save and load -----------


def test_all_three_kinds_of_squad_come_back_equal_in_a_later_session(tmp_path: Path) -> None:
    saved = _session(tmp_path, "first")
    _three_kinds(saved)
    before = _persisted(saved.campaign)
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)

    assert _persisted(resumed.campaign) == before
    # And the arrangement really did carry all three, so the equality above is
    # not two empty rosters agreeing with each other.
    assert len(before) == 3
    kinds = {(record[7], record[8]) for record in before}
    assert kinds == {(True, False), (False, False), (False, True)}


def test_the_resumed_shell_answers_to_its_player_and_the_suspended_one_stays_suspended(
    tmp_path: Path,
) -> None:
    # The three version-2 fields as a resumed session reads them back: the same
    # player leads the same Squad, still unassigned, and the one whose player
    # left is still suspended — which is what lets a returning player be handed
    # his own Squad rather than minted a second one (ruling 7).
    saved = _session(tmp_path, "first")
    _three_kinds(saved)
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)

    shell = resumed.campaign.led_by("uid-lead")
    assert shell is not None
    assert (shell.side, shell.squad_type, shell.at) == ("WEST", "", WEST_BASE)
    assert shell.composition_assigned is False
    assert shell.suspended is False

    away = resumed.campaign.led_by("uid-away")
    assert away is not None
    assert (away.side, away.suspended, away.size) == ("EAST", True, 0)


def test_the_resumed_roster_mints_the_next_id_rather_than_one_the_save_holds(
    tmp_path: Path,
) -> None:
    # ADR-0003: a resumed Campaign mints the same ids in the same order, so the
    # counter continues rather than colliding. The saved Campaign holds WEST-1
    # (bought) and WEST-2 (the shell, on the same counter), so the next Purchase
    # in the later session is WEST-3.
    saved = _session(tmp_path, "first")
    _three_kinds(saved)
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)
    minted = _command(resumed, "c-9", "purchase", "WEST", {"squad_type": RIFLE})

    assert minted["status"] == "ok", minted
    assert minted["result"]["squad"] == "WEST-3"
    assert resumed.campaign.squad("WEST-3", "WEST") is not None


# --- criterion 3's other half: what is regenerated stays regenerated -------


def test_no_resumed_squad_keeps_a_position_or_its_fielded_flag_the_shell_included(
    tmp_path: Path,
) -> None:
    # ADR-0008's line, unmoved by ADR-0070: `pos` and `fielded` come back blank
    # for the first report after a resume to set, and a shell is no exception —
    # the strategic facts are *composition-unassigned* and *suspended*, not where
    # the player was standing. The arrangement reports both the bought Squad and
    # the shell at a position first, so this is a loss and not an absence.
    saved = _session(tmp_path, "first")
    _three_kinds(saved)
    shell = saved.campaign.led_by("uid-lead")
    assert shell is not None
    assert (shell.fielded, shell.pos) == (True, (1987, 5625, 0)), (
        "the arrangement never had the world report the shell standing"
    )
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)

    for squad in resumed.campaign.roster.all():
        assert squad.fielded is False, f"{squad.id} came back already fielded"
        assert squad.pos == (), f"{squad.id} came back carrying a map position"


def test_the_coarse_place_a_squad_stands_on_does_survive_the_resume(tmp_path: Path) -> None:
    # The other side of the line above, and the one it would be easy to get
    # backwards: `at` is the coarse Place an Order names and the ground a
    # Reinforce is judged on (ADR-0008), so it is strategic and it does come
    # back. Only the metres underneath it do not.
    saved = _session(tmp_path, "first")
    _three_kinds(saved)
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)

    assert {squad.id: squad.at for squad in resumed.campaign.roster.all()} == {
        "WEST-1": "girna",
        "WEST-2": WEST_BASE,
        "EAST-1": EAST_BASE,
    }


# --- criterion 3: the suspended shell across a Play Session boundary -------


def test_a_shell_suspended_at_save_time_reactivates_in_a_later_session_unchanged(
    tmp_path: Path,
) -> None:
    # Ruling 7 end to end and across the boundary it was written for: the same
    # roster identity — and its minted id — comes back with the player, at own
    # Base and still composition-unassigned.
    saved = _session(tmp_path, "first")
    bought = _command(saved, "c-1", "purchase", "WEST", {"squad_type": RIFLE})
    assert bought["status"] == "ok", bought
    shell = saved.campaign.enrol("WEST", "uid-away")
    saved.campaign.suspend(shell.id, "WEST")
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)
    returning = resumed.campaign.led_by("uid-away")
    assert returning is not None
    assert returning.suspended is True, "the save did not carry the suspension"

    back = resumed.campaign.reactivate(returning.id, "WEST")

    assert back.id == shell.id
    assert (back.suspended, back.size, back.at) == (False, 1, WEST_BASE)
    assert back.composition_assigned is False
    assert back.player_uid == "uid-away"


def test_the_whole_suspend_save_load_reactivate_cycle_moves_no_funds(tmp_path: Path) -> None:
    # The claim ruling 7 actually bought, asserted directly rather than left as a
    # comment. A Purchase runs first so the balance under test is 200 and not the
    # 300 a fresh session would hold anyway — otherwise "unchanged after the
    # load" would pass just as well against a load that never happened.
    saved = _session(tmp_path, "first")
    bought = _command(saved, "c-1", "purchase", "WEST", {"squad_type": RIFLE})
    assert bought["status"] == "ok", bought
    spent = starting_funds() - _price(RIFLE)
    assert saved.campaign.ledger.balance("WEST") == spent

    shell = saved.campaign.enrol("WEST", "uid-away")
    assert saved.campaign.ledger.balance("WEST") == spent, "enrolling a shell moved Funds"
    saved.campaign.suspend(shell.id, "WEST")
    assert saved.campaign.ledger.balance("WEST") == spent, "suspending a shell moved Funds"
    _saved(saved)
    assert saved.campaign.ledger.balance("WEST") == spent, "the save moved Funds"

    resumed = _session(tmp_path, "second")
    _loaded(resumed)
    assert resumed.campaign.ledger.balance("WEST") == spent, "the load moved Funds"
    assert spent != starting_funds(), "the arrangement cannot tell a load from a fresh Campaign"

    returning = resumed.campaign.led_by("uid-away")
    assert returning is not None
    resumed.campaign.reactivate(returning.id, "WEST")

    assert resumed.campaign.ledger.holdings() == saved.campaign.ledger.holdings()
    assert resumed.campaign.ledger.balance("WEST") == spent, "reactivating a shell moved Funds"


def test_a_reactivated_shell_is_then_filled_at_the_price_it_would_have_cost_before(
    tmp_path: Path,
) -> None:
    # The player left before the first fill, the Campaign was saved and resumed,
    # and the Commander's first fill still costs what ruling 3 prices it at:
    # seven eighths of 100 at the 0.8 discount, for a player already standing.
    saved = _session(tmp_path, "first")
    shell = saved.campaign.enrol("WEST", "uid-away")
    saved.campaign.suspend(shell.id, "WEST")
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)
    returning = resumed.campaign.led_by("uid-away")
    assert returning is not None
    resumed.campaign.reactivate(returning.id, "WEST")

    filled = _command(
        resumed,
        "c-1",
        "reinforce_composition",
        "WEST",
        {"squad": returning.id, "squad_type": RIFLE},
    )

    assert filled["status"] == "ok", filled
    assert filled["result"] == {
        "squad": shell.id,
        "funds": starting_funds() - 70,
        "cost": 70,
        "size": 8,
    }


# --- criterion 4: the filled player-led Squad the player was away from -----


def _filled_and_ordered(daemon: Daemon) -> str:
    """Fill a player's shell, order it, and bring it home under strength.

    The Squad ruling 5 describes: filled, carrying a standing Order, and going on
    without its player. Returned home at five of eight so the ordinary Reinforce
    below has both something to replace and the ground to do it on.
    """
    shell = daemon.campaign.enrol("WEST", "uid-lead")
    filled = _command(
        daemon, "f-1", "reinforce_composition", "WEST", {"squad": shell.id, "squad_type": RIFLE}
    )
    assert filled["status"] == "ok", filled
    ordered = _command(
        daemon,
        "f-2",
        "order",
        "WEST",
        {"squad": shell.id, "order": "capture", "place": "girna"},
    )
    assert ordered["status"] == "ok", ordered
    daemon.campaign.reconcile({shell.id: Held(size=5, at=WEST_BASE, pos=(1987, 5625, 0))})
    return shell.id


def test_a_filled_player_led_squad_resumes_under_its_standing_order(tmp_path: Path) -> None:
    # Ruling 5 across the Play Session boundary, and the daemon's half of ruling
    # 6: the Squad is found under the Order it was carrying, still answering to
    # the player who leads it, so a returning player takes back a Squad rather
    # than an orderless one. The world-side reclaim is #312's.
    saved = _session(tmp_path, "first")
    squad_id = _filled_and_ordered(saved)
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)

    led = resumed.campaign.led_by("uid-lead")
    assert led is not None
    assert led.id == squad_id
    assert led.order == Order(kind="capture", place="girna")
    assert led.squad_type == RIFLE
    assert led.composition_assigned is True
    assert led.suspended is False


def test_a_resumed_player_led_squad_is_refillable_by_the_ordinary_reinforce(
    tmp_path: Path,
) -> None:
    # Ruling 3's second half surviving the resume: from the first fill the
    # composition is fixed and persisted like any other Squad's, so a later
    # Reinforce restores it at the ordinary price — three of eight men of a
    # 100-Funds Squad at the 0.8 discount is 30, which is what every other rifle
    # Squad pays.
    saved = _session(tmp_path, "first")
    squad_id = _filled_and_ordered(saved)
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)
    funds = resumed.campaign.ledger.balance("WEST")

    refilled = _command(resumed, "c-1", "reinforce", "WEST", {"squad": squad_id})

    assert refilled["status"] == "ok", refilled
    assert refilled["result"] == {
        "squad": squad_id,
        "funds": funds - 30,
        "cost": 30,
        "size": 8,
    }


# --- criterion 5: the first fill stays once-only across the resume ---------


def test_a_squad_filled_before_the_save_cannot_be_first_filled_after_it(tmp_path: Path) -> None:
    # The once-only rule (ruling 3) is a fact about the Squad, so it has to
    # survive the document that carries the Squad. `composition_fixed` rather
    # than `already_held`: the refusal is about what the Squad *is*, not about
    # how many men are standing in it — and the Squad here is three men short.
    saved = _session(tmp_path, "first")
    squad_id = _filled_and_ordered(saved)
    _saved(saved)

    resumed = _session(tmp_path, "second")
    _loaded(resumed)
    funds = resumed.campaign.ledger.balance("WEST")

    again = _command(
        resumed,
        "c-1",
        "reinforce_composition",
        "WEST",
        {"squad": squad_id, "squad_type": "weapons"},
    )

    assert again["status"] == "rejected", again
    assert again["reason"]["code"] == "composition_fixed"
    assert resumed.campaign.ledger.balance("WEST") == funds
    refused = resumed.campaign.squad(squad_id, "WEST")
    assert refused is not None
    assert refused.squad_type == RIFLE


# --- criterion 2: a version-1 save migrates and is then playable -----------


def _version_one(document: dict[str, Any]) -> dict[str, Any]:
    """Render a current document as the version-1 save that predates ADR-0070.

    Derived from today's serialiser rather than authored beside it, so a save
    written before the decision is defined by exactly what the decision added:
    the version number and the three squad fields, and nothing else drifts when
    the authored map or the rest of the document does.
    """
    older = dict(document)
    older["version"] = 1
    older["squads"] = [
        {key: value for key, value in squad.items() if key not in VERSION_TWO_FIELDS}
        for squad in document["squads"]
    ]
    return older


def _write_generation(directory: Path, document: dict[str, Any], generation: int = 1) -> None:
    """Lay one framed generation down as the store's trusted slot.

    The store's own frame, built with the store's own public checksum, so the
    document reaches `restore` through the same gate a real save's bytes do —
    a hand-rolled digest would be refused as corrupt and the migration under test
    would never run.
    """
    directory.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    frame = {
        "frame": FRAME_VERSION,
        "algorithm": CHECKSUM_ALGORITHM,
        "checksum": checksum(document),
        "generation": generation,
        "snapshot": document,
    }
    (directory / CURRENT).write_text(
        json.dumps(frame, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def _version_one_store(tmp_path: Path) -> str:
    """Leave a genuine version-1 save in the shared store, and name its Squad.

    Written from a Campaign holding bought Squads alone, which is what every save
    at version 1 could hold: a shell is minted only by a player taking the
    squad-leader role, and no build before version 2 could mint one.
    """
    author = _session(tmp_path, "authoring")
    bought = _command(author, "c-1", "purchase", "WEST", {"squad_type": RIFLE})
    assert bought["status"] == "ok", bought
    squad_id = bought["result"]["squad"]
    author.campaign.reconcile({squad_id: Held(size=5, at=WEST_BASE, pos=(1987, 5625, 0))})

    document = _version_one(snapshot.serialise(author.cycle.snapshot()))
    assert document["squads"], "the arrangement wrote a version-1 save with no Squads in it"
    for squad in document["squads"]:
        assert not VERSION_TWO_FIELDS & set(squad), (
            "the version-1 document still carries a field ADR-0070 introduced"
        )
    _write_generation(tmp_path / "saves", document)
    return str(squad_id)


def test_a_version_one_save_loads_as_assigned_active_and_unowned(tmp_path: Path) -> None:
    # The migration's documented safe default, read at the far end of the real
    # load path: every Squad written before ADR-0070 was composition-assigned,
    # active and owned by no player, because there was no other kind.
    _version_one_store(tmp_path)
    stored = json.loads((tmp_path / "saves" / CURRENT).read_text(encoding="utf-8"))
    assert stored["snapshot"]["version"] == 1, "the arrangement did not write a version-1 save"

    resumed = _session(tmp_path, "resumed")
    ack = _loaded(resumed)

    # The ack names the version the document was restored *to*, which is what
    # says the 1 -> 2 migration ran rather than a version-1 document being read
    # as-is (`snapshot.restore` walks the steps or refuses; it never reads at an
    # older version).
    assert ack["result"]["version"] == snapshot.CURRENT_VERSION
    roster = resumed.campaign.roster.all()
    assert roster, "the version-1 load produced an empty roster"
    for squad in roster:
        assert squad.composition_assigned is True
        assert squad.suspended is False
        assert squad.player_uid == ""
    assert resumed.campaign.led_by("uid-lead") is None


def test_a_migrated_version_one_campaign_is_then_playable(tmp_path: Path) -> None:
    # The half a schema test cannot answer. A migrated Squad is judged by the
    # ordinary rules and not by the shell's: an ordinary Reinforce on it must be
    # priced rather than refused `composition_unassigned`, which is precisely what
    # a migration that defaulted the other way would have earned.
    squad_id = _version_one_store(tmp_path)

    resumed = _session(tmp_path, "resumed")
    _loaded(resumed)
    funds = resumed.campaign.ledger.balance("WEST")

    purchased = _command(resumed, "c-1", "purchase", "WEST", {"squad_type": RIFLE})
    ordered = _command(
        resumed, "c-2", "order", "WEST", {"squad": squad_id, "order": "capture", "place": "girna"}
    )
    refilled = _command(resumed, "c-3", "reinforce", "WEST", {"squad": squad_id})

    assert purchased["status"] == "ok", purchased
    assert ordered["status"] == "ok", ordered
    assert refilled["status"] == "ok", refilled
    assert refilled["result"]["cost"] == 30
    assert resumed.campaign.ledger.balance("WEST") == funds - _price(RIFLE) - 30


# --- criterion 6: a refused load leaves the live Campaign as it was --------


def test_a_refused_load_leaves_a_campaign_holding_all_three_kinds_untouched(
    tmp_path: Path,
) -> None:
    # ADR-0003's validate-then-mutate property, against the state this issue
    # adds: a store whose only generation is corrupt refuses, and the live
    # Campaign — shell, suspension, Funds and all — is exactly what it was. The
    # corruption is a payload edited under a checksum that no longer covers it,
    # which is what a torn or byte-rotted generation looks like to the gate.
    live_session = _session(tmp_path, "live")
    _three_kinds(live_session)
    before = _persisted(live_session.campaign)
    holdings = live_session.campaign.ledger.holdings()

    document = snapshot.serialise(live_session.cycle.snapshot())
    frame = {
        "frame": FRAME_VERSION,
        "algorithm": CHECKSUM_ALGORITHM,
        "checksum": checksum(document),
        "generation": 1,
        "snapshot": {**document, "clock": document["clock"] + 1},
    }
    saves = tmp_path / "saves"
    saves.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    (saves / CURRENT).write_text(
        json.dumps(frame, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    refusal = _control(live_session, "l-1", "load")

    assert refusal["status"] == "error"
    assert refusal["error"]["class"] == "corrupt"
    assert _persisted(live_session.campaign) == before, "a refused load mutated the live roster"
    assert live_session.campaign.ledger.holdings() == holdings
