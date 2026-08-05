"""What the daemon does with one request line."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from conftest import (
    all_rows,
    authored_stratis,
    funds_after_buying,
    observe,
    reply_to,
    rows,
    starting_funds,
)

from cti_daemon import planner
from cti_daemon.commands import Effect
from cti_daemon.transport import build_daemon

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.daemon import Daemon

# One Effect to put on the outbox, the domain object it now holds (#77), in the
# shape the catalogue declares — the outbox refuses any other (#145).
ORDER_ISSUED = Effect(
    name="order_issued",
    side="WEST",
    args={"squad": "WEST-1", "order": "reserve", "place": ""},
)


def test_ping_is_answered_with_the_id_it_was_asked_under(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl", epoch="e-1")
    assert reply_to(daemon, id="r-1", verb="ping") == {
        "id": "r-1",
        "epoch": "e-1",
        "status": "ok",
        "result": {"pong": True},
    }


def test_a_verb_the_daemon_does_not_know_is_an_error_not_a_rejection(tmp_path: Path) -> None:
    # Rejection means "understood and refused"; this was not understood.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(daemon, id="r-2", verb="purchase")
    assert reply["id"] == "r-2"
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "unknown_verb"


def test_a_malformed_line_is_answered_rather_than_dropped(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = json.loads(daemon.handle_line("{not json"))
    assert reply["id"] is None
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "malformed_request"


def test_a_malformed_line_that_still_carried_an_id_is_answered_under_it(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = json.loads(daemon.handle_line('{"id": "r-3", "verb": 7}'))
    assert reply["id"] == "r-3"
    assert reply["error"]["class"] == "malformed_request"


def test_poll_hands_over_pending_messages_with_their_sequences(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push(ORDER_ISSUED)

    reply = reply_to(daemon, id="r-4", verb="poll")
    assert reply["result"] == {
        "messages": [
            {
                "sequence": 1,
                "message": {
                    "effect": "order_issued",
                    "side": "WEST",
                    "args": {"squad": "WEST-1", "order": "reserve", "place": ""},
                },
            }
        ]
    }


def test_polling_twice_without_acknowledging_delivers_the_same_messages(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push(ORDER_ISSUED)

    first = reply_to(daemon, id="r-5", verb="poll")["result"]
    second = reply_to(daemon, id="r-6", verb="poll")["result"]
    assert first == second


def test_acknowledging_clears_the_messages_from_the_next_poll(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push(ORDER_ISSUED)

    acked = reply_to(daemon, id="r-7", verb="ack", payload={"through": 1})
    assert acked["status"] == "ok"
    assert reply_to(daemon, id="r-8", verb="poll")["result"] == {"messages": []}


def test_acknowledging_a_sequence_never_issued_is_a_domain_rejection(tmp_path: Path) -> None:
    # The request was well formed and the daemon understood it. It is refused
    # on the rules, which is the third outcome, not an error.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(daemon, id="r-9", verb="ack", payload={"through": 9})
    assert reply["status"] == "rejected"
    assert reply["reason"]["code"] == "unknown_sequence"


def test_an_acknowledgement_without_a_sequence_is_malformed(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(daemon, id="r-10", verb="ack", payload={"through": "soon"})
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "malformed_request"


def test_an_acknowledgement_records_the_effects_the_world_refused_for_good(
    tmp_path: Path,
) -> None:
    # #100: the world dead-letters an effect it can never apply so the queue
    # behind it moves. The Campaign paid for that effect and never got it, so the
    # row belongs in the record and not only in the server's log.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    daemon.outbox.push(ORDER_ISSUED)

    reply = reply_to(
        daemon,
        id="r-11",
        verb="ack",
        payload={
            "through": 1,
            "dead": [{"sequence": 1, "effect": "arsenal_opened", "reason": "unknown_effect"}],
        },
    )

    assert reply["status"] == "ok"
    dead = rows(log, "effect_dead_letter")
    assert [(row["sequence"], row["effect"], row["reason"]) for row in dead] == [
        (1, "arsenal_opened", "unknown_effect")
    ]


def test_an_acknowledgement_whose_dead_letters_are_not_rows_is_malformed(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push(ORDER_ISSUED)
    reply = reply_to(daemon, id="r-12", verb="ack", payload={"through": 1, "dead": ["1"]})
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "malformed_request"


def test_an_acknowledgement_carrying_no_dead_letters_writes_no_row(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    daemon.outbox.push(ORDER_ISSUED)

    reply_to(daemon, id="r-13", verb="ack", payload={"through": 1, "dead": []})

    assert rows(log, "effect_dead_letter") == []


def test_a_failure_inside_the_daemon_is_answered_as_an_internal_error(tmp_path: Path) -> None:
    # A message that cannot be serialised is the shape of bug a later ticket
    # will produce. The connection must survive it and say what happened.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push(
        Effect(
            name="order_issued",
            side="WEST",
            # Catalogue-shaped, so it clears the door (#145); the Place is what
            # no JSON encoder can carry.
            args={"squad": "WEST-1", "order": "reserve", "place": object()},
        )
    )

    reply = reply_to(daemon, id="r-11", verb="poll")
    assert reply["id"] == "r-11"
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "internal"


def test_every_request_is_recorded_in_telemetry(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    daemon.handle_line(json.dumps({"id": "r-12", "verb": "ping"}))
    daemon.handle_line("{not json")

    records = all_rows(log)
    assert [(record["id"], record["verb"], record["status"]) for record in records] == [
        ("r-12", "ping", "ok"),
        (None, None, "error"),
    ]
    assert all(record["duration_us"] >= 0 for record in records)


def test_a_command_is_carried_inside_the_envelope_not_beside_it(tmp_path: Path) -> None:
    # ADR-0012: transport verbs and Commands never share a namespace.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="c-1",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )
    assert reply["status"] == "ok"
    assert reply["result"] == {"squad": "WEST-1", "funds": funds_after_buying("rifle")}


def test_an_order_reaches_the_port_through_the_same_envelope_as_a_purchase(
    tmp_path: Path,
) -> None:
    # One wire format for every Command (#14): the Order verb is a payload the
    # port judges, not a second transport verb beside `command`.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply_to(
        daemon,
        id="c-7",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )
    reply = reply_to(
        daemon,
        id="c-8",
        verb="command",
        payload={
            "command": "order",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad": "WEST-1", "order": "capture", "place": "agia_marina"},
        },
    )
    assert reply["status"] == "ok"
    assert reply["result"]["order"] == "capture"


def test_an_accepted_command_leaves_its_effect_on_the_outbox(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply_to(
        daemon,
        id="c-2",
        verb="command",
        payload={
            "command": "purchase",
            "side": "EAST",
            "acting_side": "EAST",
            "args": {"squad_type": "rifle"},
        },
    )
    polled = reply_to(daemon, id="c-3", verb="poll")
    (message,) = polled["result"]["messages"]
    assert message["message"]["effect"] == "squad_spawned"
    assert message["message"]["side"] == "EAST"


def test_a_malformed_command_is_a_rejection_while_a_malformed_request_is_an_error(
    tmp_path: Path,
) -> None:
    # The whole typing split ADR-0012 turns on, asserted side by side: the
    # caller being wrong is a rejection, our transport failing is an error.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    rejected = reply_to(daemon, id="c-4", verb="command", payload={"side": "WEST"})
    errored = json.loads(daemon.handle_line("{not json"))
    assert rejected["status"] == "rejected"
    assert rejected["reason"]["code"] == "malformed_command"
    assert errored["status"] == "error"
    assert errored["error"]["class"] == "malformed_request"


def test_an_unknown_command_is_a_rejection_while_an_unknown_verb_is_an_error(
    tmp_path: Path,
) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    rejected = reply_to(
        daemon,
        id="c-5",
        verb="command",
        payload={"command": "bombard", "side": "WEST", "acting_side": "WEST"},
    )
    errored = reply_to(daemon, id="c-6", verb="bombard")
    assert rejected["reason"]["code"] == "unknown_command"
    assert errored["error"]["class"] == "unknown_verb"


def test_a_command_claiming_a_side_the_caller_does_not_hold_is_rejected(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="c-7",
        verb="command",
        payload={"command": "purchase", "side": "EAST", "acting_side": "WEST"},
    )
    assert reply["reason"]["code"] == "wrong_side"


def test_a_command_nobody_stamped_is_refused_rather_than_taken_at_its_word(
    tmp_path: Path,
) -> None:
    # #19's audit found the default that used to sit here: `acting_side` fell
    # back to the side the payload named, so a line that never passed the
    # gateway commanded for whichever side it wrote down. The stamp is the
    # server's own or the caller is nobody (ADR-0044).
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="u-1",
        verb="command",
        payload={"command": "purchase", "side": "WEST", "args": {"squad_type": "rifle"}},
    )
    assert reply["status"] == "rejected"
    assert reply["reason"]["code"] == "unknown_caller"
    # And nothing was spent on the way to that answer.
    assert daemon.campaign.ledger.balance("WEST") == starting_funds()
    assert daemon.outbox.pending() == []


def test_a_stamp_that_is_not_a_side_is_no_stamp_at_all(tmp_path: Path) -> None:
    # The three shapes an unstamped caller arrives in — absent, empty, and a
    # side nobody plays — get one answer, because "who is acting" is not a
    # question the payload gets to answer badly.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    codes = []
    for index, stamp in enumerate(["", "GUER", 7, None]):
        reply = reply_to(
            daemon,
            id=f"u-{index}",
            verb="command",
            payload={
                "command": "purchase",
                "side": "WEST",
                "acting_side": stamp,
                "args": {"squad_type": "rifle"},
            },
        )
        codes.append(reply["reason"]["code"])
    assert codes == ["unknown_caller"] * 4


def test_telemetry_records_why_a_request_was_refused(tmp_path: Path) -> None:
    # Without this, three different rejections are byte-identical server-side:
    # the caller learns which part was wrong and the operator does not.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    reply_to(daemon, id="r-1", verb="command", payload={"command": "purchase", "side": "GUER"})
    reply_to(daemon, id="r-2", verb="bombard")
    reply_to(daemon, id="r-3", verb="ping")

    written = all_rows(log)
    assert [(row["status"], row["reason_code"]) for row in written] == [
        ("rejected", "malformed_command"),
        ("error", "unknown_verb"),
        ("ok", None),
    ]
    assert "side" in written[0]["reason_detail"]
    assert written[2]["reason_detail"] is None


def test_telemetry_says_whether_the_side_column_is_a_stamp_or_a_claim(tmp_path: Path) -> None:
    # B3 of #139 (#152): the `side` column falls back from the gateway's
    # server-side stamp to the side the payload claimed, which are different
    # kinds of fact. The provenance rides beside the value, so an audit can
    # tell a row the server vouched for from one taken at the caller's word —
    # and a verb that belongs to no side leaves both empty.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    reply_to(
        daemon,
        id="s-1",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )
    reply_to(daemon, id="s-2", verb="view", payload={"side": "WEST"})
    reply_to(daemon, id="s-3", verb="ping")

    written = rows(log, "request")
    assert [(row["side"], row["side_source"]) for row in written] == [
        ("WEST", "stamped"),
        ("WEST", "claimed"),
        (None, None),
    ]


def test_observing_presence_moves_ownership_and_pays(tmp_path: Path) -> None:
    # `observe` is the transport verb ADR-0012 reserved for the world telling
    # the daemon what it can see.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="o-1",
        verb="observe",
        payload={"time": 30, "presence": {"agia_marina": ["WEST"]}},
    )
    assert reply["status"] == "ok"
    assert reply["result"]["owners"]["agia_marina"] == "WEST"


def test_a_capture_reaches_the_game_as_an_effect(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply_to(
        daemon,
        id="o-2",
        verb="observe",
        payload={"time": 30, "presence": {"girna": ["EAST"]}},
    )
    polled = reply_to(daemon, id="o-3", verb="poll")
    effects = [entry["message"]["effect"] for entry in polled["result"]["messages"]]
    assert "objective_captured" in effects


def test_an_observation_without_a_time_is_refused(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(daemon, id="o-4", verb="observe", payload={"presence": {}})
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "malformed_request"


def test_the_reply_to_an_observation_is_the_public_picture_and_no_more(tmp_path: Path) -> None:
    # #15's return leg: the world reports what only it can see and gets back
    # what it needs to paint the map, on the same call. No second channel, no
    # second cadence, and no callback — so at-most-once delivery never arises.
    # #27 fixed what "no more" means: the server is not a Commander, so it takes
    # ownership alone and no side's Funds, Squads or standing Orders.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply_to(
        daemon,
        id="o-5",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )
    result = observe(daemon, "o-6", squads={"WEST-1": {"size": 7, "at": "nato_airbase"}})

    # The scoreboard both sides may read (#35) and nothing else: Objective
    # ownership, and each Base's HQ intact or destroyed.
    assert set(result) == {"at", "owners", "hq"}


def test_a_report_that_says_nothing_about_squads_leaves_the_roster_alone(tmp_path: Path) -> None:
    # Absent is not the same as empty: a report carrying no `squads` key has no
    # opinion, and treating it as "the world holds none" would delete the
    # roster on every report that predates the field.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply_to(
        daemon,
        id="o-7",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )
    observe(daemon, "o-8", presence={})
    assert len(daemon.campaign.observation("WEST").squads) == 1


def test_a_report_that_holds_no_squads_says_so_and_the_roster_empties(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply_to(
        daemon,
        id="o-9",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )
    # Reported standing once first: a Squad the world has never held is one
    # still on its way there, not one it has lost (`squads.Roster.reconcile`).
    observe(daemon, "o-10a", squads={"WEST-1": {"size": 8, "at": ""}})
    observe(daemon, "o-10", squads={})
    assert daemon.campaign.observation("WEST").squads == ()
    # A Squad leaving the Campaign is reported to the operator's log rather than
    # to the world, which already knows: it is what said so.
    lost = rows(tmp_path / "telemetry.jsonl", "squad_lost")
    assert [row["squad"] for row in lost] == ["WEST-1"]


def test_a_squad_report_the_daemon_cannot_read_is_refused(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="o-11",
        verb="observe",
        payload={"time": 1, "squads": {"WEST-1": {"size": "eight"}}},
    )
    assert reply["error"]["class"] == "malformed_request"


def test_what_a_sides_leaders_saw_becomes_that_sides_contacts(tmp_path: Path) -> None:
    # #28's return leg: the world reports the engine's own knowledge model,
    # keyed by the side that did the observing, and the daemon bands it.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    observe(
        daemon,
        "o-15",
        contacts={
            "WEST": {
                "seen": [{"at": "girna", "kind": "Infantry", "age": 0} for _ in range(5)],
                "observed": ["girna"],
            }
        },
    )

    (contact,) = daemon.campaign.observation("WEST").contacts
    assert (contact.at, contact.echelon, contact.posture) == ("girna", "squad", "foot")
    assert daemon.campaign.observation("EAST").contacts == ()


def test_a_report_that_says_nothing_about_contacts_leaves_the_picture_alone(
    tmp_path: Path,
) -> None:
    # Absent is not empty here either, and the difference matters more than it
    # does for Squads: treating silence as observed absence would clear every
    # Contact on the map on any report that carried no sightings.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    observe(
        daemon,
        "o-16",
        contacts={
            "WEST": {"seen": [{"at": "girna", "kind": "Infantry", "age": 0}], "observed": ["girna"]}
        },
    )
    observe(daemon, "o-17", presence={})
    assert [contact.at for contact in daemon.campaign.observation("WEST").contacts] == ["girna"]


def test_a_contact_report_the_daemon_cannot_read_is_refused(tmp_path: Path) -> None:
    # A malformed report is a refusal rather than a silently empty picture: a
    # Commander cannot tell "nobody is out there" from "the report was junk",
    # and one of those is a reason to attack.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="o-18",
        verb="observe",
        payload={"time": 1, "contacts": {"WEST": {"seen": [{"at": "girna"}], "observed": []}}},
    )
    assert reply["error"]["class"] == "malformed_request"


def test_a_side_nobody_is_playing_has_no_contacts_to_report(tmp_path: Path) -> None:
    # `Contacts` would key on any string it is handed, so a mistyped side would
    # file a picture no observation ever reads and lose the sighting in silence.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="o-19",
        verb="observe",
        payload={"time": 1, "contacts": {"west": {"seen": [], "observed": []}}},
    )
    assert reply["error"]["class"] == "malformed_request"


def test_a_contact_growing_older_is_not_the_picture_moving(tmp_path: Path) -> None:
    # A Contact's age is a clock reading, like `at`: it advances on its own
    # every report, without anything having happened. Comparing on it would
    # write a row per report and bury the moment the picture actually moved,
    # which is the whole point of writing it out only when it changes.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    observe(
        daemon,
        "o-20",
        time=10,
        contacts={
            "WEST": {"seen": [{"at": "girna", "kind": "Infantry", "age": 0}], "observed": ["girna"]}
        },
    )
    # The clock has to move for the Contact to age, which is exactly the case
    # that would otherwise write a row every five seconds for as long as anyone
    # remembers seeing anything.
    for request_id, at_time in (("o-21", 15), ("o-22", 20), ("o-23", 25)):
        observe(daemon, request_id, time=at_time, presence={})
    assert daemon.campaign.observation("WEST").contacts[0].age == 15

    written = rows(log, "observation")
    assert [row["side"] for row in written] == ["WEST", "EAST"]


def test_the_strategic_picture_is_written_out_when_it_moves_and_not_otherwise(
    tmp_path: Path,
) -> None:
    # The demo is tailing telemetry and watching ownership and Funds move. A row
    # per report would bury the moment they did under rows saying they had not.
    # One row per side, because there is no picture carrying both to write (#27);
    # an operator wanting the whole board reads both rows.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    observe(daemon, "o-13", presence={"agia_marina": ["WEST"]})
    observe(daemon, "o-14", presence={"agia_marina": ["WEST"]})

    def written() -> list[dict[str, Any]]:
        return rows(log, "observation")

    assert [row["side"] for row in written()] == ["WEST", "EAST"]

    reply_to(
        daemon,
        id="o-15",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )
    observe(daemon, "o-16", presence={"agia_marina": ["WEST"]})
    # Only the side that spent moved, so only its row is written again.
    assert [row["side"] for row in written()] == ["WEST", "EAST", "WEST"]
    # The starting balance less what the rifle Squad cost, derived rather than
    # pinned: an authored price change should move this test's arithmetic, not
    # break it.
    assert written()[-1]["funds"] == funds_after_buying("rifle")


def hq_rows(log: Path) -> list[dict[str, Any]]:
    """Every HQ destruction the daemon wrote down."""
    return rows(log, "hq_destroyed")


def test_an_hq_the_world_reports_destroyed_is_written_down_once(tmp_path: Path) -> None:
    # Decapitation is won by destroying a Base's HQ structure, and
    # docs/mvp-scope.md resolves a mutual one by which destruction telemetry
    # holds first — so the event has to be written exactly once per Base,
    # carrying whose Base fell and who brought it down (#33).
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    observe(daemon, "h-1", time=90, hq={"csat_kamino": {"destroyed": True, "by": "WEST"}})
    # The world keeps reporting a destroyed HQ for the rest of the session: the
    # rubble does not stop being rubble, and every later report says so.
    observe(daemon, "h-2", time=95, hq={"csat_kamino": {"destroyed": True, "by": "WEST"}})

    (row,) = hq_rows(log)
    assert (row["base"], row["side"], row["by"], row["at"]) == ("csat_kamino", "EAST", "WEST", 90)


def test_an_hq_still_standing_is_not_an_event(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    observe(daemon, "h-3", hq={"csat_kamino": {"destroyed": False, "by": ""}})

    assert hq_rows(log) == []


def test_an_hq_report_naming_ground_the_map_lacks_is_refused(tmp_path: Path) -> None:
    # A Base id the manifest does not have cannot be attributed to a side, and
    # a Decapitation filed against nobody's Base is worse than none at all.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="h-4",
        verb="observe",
        payload={"time": 1, "hq": {"agia_marina": {"destroyed": True, "by": "WEST"}}},
    )
    assert reply["error"]["class"] == "malformed_request"


def test_an_hq_report_the_daemon_cannot_read_is_refused(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="h-5",
        verb="observe",
        payload={"time": 1, "hq": {"csat_kamino": {"destroyed": "yes", "by": "WEST"}}},
    )
    assert reply["error"]["class"] == "malformed_request"


def test_a_report_that_says_nothing_about_hqs_is_ordinary(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    observe(daemon, "h-6", presence={})

    assert hq_rows(log) == []


def test_every_reply_records_how_close_it_ran_to_the_return_cap(tmp_path: Path) -> None:
    # The engine truncates a return over 10,240 bytes in silence (ADR-0004), so
    # the size of the one reply that grows — the observation — is kept on disk.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    observe(daemon, "o-12", presence={})
    assert 0 < all_rows(log)[-1]["reply_bytes"] < 10_240


# ------------------------------- the second principal, through the wire (ADR-0040)

WEST_BASE = next(base.id for base in authored_stratis().bases if base.side == "WEST")


def a_squad_at_base(daemon: Daemon, request: str, *, size: int) -> str:
    """Buy one WEST Squad and have the world report it home and under strength.

    Through the wire both times: the Purchase is a Command and the head count is
    the world reporting, which are the two paths a Reinforce is judged against.
    """
    reply_to(
        daemon,
        id=f"{request}-buy",
        verb="command",
        payload={
            "command": "purchase",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad_type": "rifle"},
        },
    )
    reply_to(
        daemon,
        id=f"{request}-see",
        verb="observe",
        payload={
            "time": 30,
            "presence": {},
            "squads": {"WEST-1": {"size": size, "at": WEST_BASE}},
        },
    )
    return "WEST-1"


def test_a_squad_leaders_reinforce_reaches_the_port_stamped_with_his_squad(
    tmp_path: Path,
) -> None:
    # The gateway resolves the Squad from the caller's own slot and stamps it
    # beside `acting_side` (ADR-0040); this is the daemon's half of that.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    squad = a_squad_at_base(daemon, "r-1", size=5)

    reply = reply_to(
        daemon,
        id="r-1",
        verb="command",
        payload={
            "command": "reinforce",
            "side": "WEST",
            "acting_side": "WEST",
            "acting_squad": squad,
            "args": {"squad": squad},
        },
    )

    assert reply["status"] == "ok"
    assert reply["result"]["cost"] == 30


def test_a_squad_leader_reaching_for_another_squad_is_refused_not_your_squad(
    tmp_path: Path,
) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    a_squad_at_base(daemon, "r-2", size=5)

    reply = reply_to(
        daemon,
        id="r-2",
        verb="command",
        payload={
            "command": "reinforce",
            "side": "WEST",
            "acting_side": "WEST",
            "acting_squad": "WEST-2",
            "args": {"squad": "WEST-1"},
        },
    )

    assert reply["status"] == "rejected"
    assert reply["reason"]["code"] == "not_your_squad"


def test_a_squad_leader_may_reinforce_on_a_side_an_ai_commander_plays(tmp_path: Path) -> None:
    # The MVP's second mode: both sides AI-commanded while the player leads a
    # Squad (CONTEXT.md). The one-Commander-per-side refusal is about a second
    # Commander, and a squad leader is not one — a check that took his Reinforce
    # away for the AI playing his own side would refuse that mode outright.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    squad = a_squad_at_base(daemon, "r-3", size=5)
    daemon.commanded_by(
        "WEST",
        planner.UtilityPlanner(
            map_manifest=daemon.campaign.map_manifest, table=daemon.campaign.table, seed=1
        ),
    )

    leader = reply_to(
        daemon,
        id="r-3",
        verb="command",
        payload={
            "command": "reinforce",
            "side": "WEST",
            "acting_side": "WEST",
            "acting_squad": squad,
            "args": {"squad": squad},
        },
    )
    person = reply_to(
        daemon,
        id="r-4",
        verb="command",
        payload={
            "command": "reinforce",
            "side": "WEST",
            "acting_side": "WEST",
            "args": {"squad": squad},
        },
    )

    assert leader["status"] == "ok"
    # And the door the AI's own side is behind is still shut to a second
    # Commander, which is what makes the line above about the principal rather
    # than about the check having been dropped.
    assert person["reason"]["code"] == "wrong_side"


def test_a_stamp_that_is_not_a_squad_id_is_read_as_no_stamp_at_all(tmp_path: Path) -> None:
    # The stamp is the server's own; anything else reaching this field is a
    # caller inventing one, and inventing one must not buy authority. Read as
    # absent, so it is judged as the Commander principal and refused for the
    # side it is not commanding rather than admitted as a leader.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    squad = a_squad_at_base(daemon, "r-5", size=5)

    reply = reply_to(
        daemon,
        id="r-5",
        verb="command",
        payload={
            "command": "reinforce",
            "side": "WEST",
            "acting_side": "EAST",
            "acting_squad": {"squad": squad},
            "args": {"squad": squad},
        },
    )

    assert reply["reason"]["code"] == "wrong_side"
