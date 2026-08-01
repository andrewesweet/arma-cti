"""Both sides under an AI Commander at once (#17).

One side playing itself is #16 and `test_daemon_planning.py`. What only appears
at two is pinned here: that neither Commander can see or spend the other's
state, that every Command reaching the port is attributable to the Commander
that issued it, that two decision traces sharing one log stay separable, and
that a *pair* of seeds replays the same Campaign.

The world is a stand-in for Arma and only for Arma: it spawns what it is told
and puts Squads where they were sent. The campaign, the port and the planners
are the real ones.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any

import pytest

from cti_daemon import planner, transport
from cti_daemon.commands import SIDES, Command
from cti_daemon.daemon import Daemon
from cti_daemon.observation import serialise
from cti_daemon.planner import Candidate, Decision, Plan

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.observation import Observation

# One per side, and different, because a pair of seeds is what fixes a Campaign.
SEEDS = {"WEST": 1, "EAST": 4}


def reply_to(daemon: Daemon, **envelope: object) -> dict[str, Any]:
    """Send one request and return its decoded reply."""
    return json.loads(daemon.handle_line(json.dumps(envelope)))


def commanded(
    path: Path,
    seeds: dict[str, int] | None = None,
    brains: dict[str, planner.Planner] | None = None,
) -> Daemon:
    """Return a daemon with every named side under its own AI Commander."""
    daemon = Daemon(telemetry_path=path)
    for side, seed in (seeds or SEEDS).items():
        daemon.commanded_by(
            side,
            (brains or {}).get(side)
            or planner.UtilityPlanner(
                map_manifest=daemon.campaign.map_manifest,
                table=daemon.campaign.table,
                seed=seed,
            ),
        )
    return daemon


def turn(daemon: Daemon, step: int) -> dict[str, Any]:
    """One turn of a world that spawns what it is told and goes where it is sent."""
    presence: dict[str, list[str]] = {}
    squads: dict[str, dict[str, Any]] = {}
    for side in SIDES:
        for squad in daemon.campaign.roster.roll(side):
            if squad.order.place:
                presence.setdefault(squad.order.place, []).append(side)
            squads[squad.id] = {"size": squad.size, "at": squad.order.place}
    return reply_to(
        daemon,
        id=f"turn-{step}",
        verb="observe",
        payload={"time": (step + 1) * 30, "presence": presence, "squads": squads},
    )["result"]


def play(daemon: Daemon, turns: int = 8) -> Daemon:
    """Run a Campaign forward, unattended. Nobody sends a Command."""
    for step in range(turns):
        turn(daemon, step)
    return daemon


def rows(path: Path, event: str) -> list[dict[str, Any]]:
    """Return the telemetry rows of one kind."""
    return [
        record
        for line in path.read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line))["event"] == event
    ]


def fingerprint(daemon: Daemon) -> dict[str, Any]:
    """Everything a replay has to reproduce: the Campaign as it stands."""
    return {
        "owners": daemon.campaign.owners(),
        "funds": {side: daemon.campaign.ledger.balance(side) for side in SIDES},
        "squads": {
            side: [
                (squad.id, squad.squad_type, squad.order.kind, squad.order.place)
                for squad in daemon.campaign.roster.roll(side)
            ]
            for side in SIDES
        },
        "effects": [entry.message for entry in daemon.outbox.pending()],
    }


def test_two_commanders_play_one_campaign_unattended(tmp_path: Path) -> None:
    # The demoable thing #17 asks for: nobody sends a Command and two sides
    # fight over the island. Two planner instances, one per side, on the one
    # cadence there is — the world's report (ADR-0005).
    daemon = play(commanded(tmp_path / "telemetry.jsonl"))

    for side in SIDES:
        assert len(daemon.campaign.roster.roll(side)) > 1, f"{side} fielded nothing"
        assert side in daemon.campaign.owners().values(), f"{side} took no ground"


def test_a_side_can_only_be_put_under_one_commander(tmp_path: Path) -> None:
    # Two brains on one side would be two answers to what that side is doing,
    # and both would spend the same Funds.
    daemon = commanded(tmp_path / "telemetry.jsonl", seeds={"WEST": 1})
    second = planner.UtilityPlanner(
        map_manifest=daemon.campaign.map_manifest, table=daemon.campaign.table
    )
    with pytest.raises(ValueError, match="WEST"):
        daemon.commanded_by("WEST", second)


class Recorder:
    """A planner that plays properly and keeps the picture it was handed."""

    def __init__(self, brain: planner.Planner) -> None:
        """Wrap a real planner so what it saw can be read back."""
        self.brain = brain
        self.seen: list[dict[str, Any]] = []

    def plan(self, observation: Observation) -> Plan:
        """Plan as the wrapped brain would, and keep the Observation."""
        self.seen.append(serialise(observation))
        return self.brain.plan(observation)


def recording(daemon: Daemon, seed: int) -> Recorder:
    """Return a Recorder around the scorer this campaign's data implies."""
    return Recorder(
        planner.UtilityPlanner(
            map_manifest=daemon.campaign.map_manifest, table=daemon.campaign.table, seed=seed
        )
    )


def test_neither_commander_is_handed_the_others_state(tmp_path: Path) -> None:
    # Per-side isolation, asked of the only input a planner has. A picture
    # naming the enemy's Squads or Funds would be #27's leak arriving at two
    # sides, and the planner reads campaign state in-process — so there is
    # nowhere else to catch it.
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    watchers = {side: recording(daemon, seed) for side, seed in SEEDS.items()}
    for side, watcher in watchers.items():
        daemon.commanded_by(side, watcher)
    play(daemon)

    for side, watcher in watchers.items():
        assert watcher.seen, f"{side}'s Commander was never asked to plan"
        for picture in watcher.seen:
            assert picture["side"] == side
            assert all(squad["id"].startswith(f"{side}-") for squad in picture["squads"])
            # Ownership and HQ status are public to both sides — the scoreboard,
            # not intelligence (#35) — and are the only place the other side is
            # named.
            assert set(picture) == {
                "at",
                "owners",
                "hq",
                "side",
                "funds",
                "squads",
                "contacts",
            }


class Wanderer:
    """A planner that keeps a note of what it decided last cycle."""

    def __init__(self) -> None:
        """Start with nothing remembered."""
        self.decided: list[Decision] = []

    def plan(self, observation: Observation) -> Plan:
        """Record one decision and issue nothing."""
        decision = Decision(
            about=observation.for_side,
            chose="nothing",
            because="watching",
            scored=1,
            candidates=(Candidate(choice="nothing", score=0.0, terms={"whim": 0.0}),),
        )
        self.decided.append(decision)
        return Plan(commands=(), decisions=(decision,))


class Spendthrift:
    """A planner that buys whatever it can afford, every single cycle."""

    def plan(self, observation: Observation) -> Plan:
        """Spend down to nothing, so the other side's balance has to prove itself."""
        return Plan(
            commands=(Command("purchase", observation.for_side, {"squad_type": "rifle"}),),
            decisions=(),
        )


def test_one_commanders_spending_never_reaches_the_others_funds(tmp_path: Path) -> None:
    # Isolation of the ledger, and the loudest way to ask: one side spends every
    # cycle while the other spends nothing. The Miser's balance is then income
    # alone, and any leak shows up as Funds it never earned or never had.
    daemon = commanded(
        tmp_path / "telemetry.jsonl",
        brains={"WEST": Spendthrift(), "EAST": Wanderer()},
    )
    play(daemon)

    table = daemon.campaign.table
    ticks = int(daemon.campaign.elapsed // table.income_tick_seconds)
    assert daemon.campaign.ledger.balance("EAST") == table.starting_funds + ticks * table.stipend
    assert daemon.campaign.roster.roll("EAST") == ()
    assert daemon.campaign.roster.roll("WEST") != ()


class Interloper:
    """A planner with a bug in it: it commands for the side across the line."""

    def plan(self, observation: Observation) -> Plan:
        """Buy a Squad on the enemy's account."""
        other = next(side for side in SIDES if side != observation.for_side)
        return Plan(commands=(Command("purchase", other, {"squad_type": "rifle"}),), decisions=())


def test_a_command_issued_for_another_side_is_refused_and_attributed(tmp_path: Path) -> None:
    # Attribution, and what it is for: the port judges against the Commander
    # that issued the Command, not against the side written on it. A planner
    # reaching across the line is refused and named in the log.
    log = tmp_path / "telemetry.jsonl"
    daemon = commanded(log, brains={"WEST": Interloper(), "EAST": Wanderer()})
    turn(daemon, 0)

    (refused,) = rows(log, "plan_refused")
    assert refused["code"] == "wrong_side"
    assert refused["side"] == "WEST"
    assert refused["command_side"] == "EAST"
    assert daemon.campaign.roster.roll("EAST") == ()
    assert daemon.campaign.ledger.balance("EAST") >= daemon.campaign.table.starting_funds


def test_every_command_that_reaches_the_port_is_attributable(tmp_path: Path) -> None:
    # "Every order arriving at the port is attributable to the Commander that
    # issued it" — so an accepted one is written down as well as a refused one,
    # or the log answers who did the wrong thing and never who did anything.
    log = tmp_path / "telemetry.jsonl"
    play(commanded(log), turns=4)

    issued = rows(log, "command_issued")
    assert {row["side"] for row in issued} == set(SIDES)
    for row in issued:
        assert row["command_side"] == row["side"]
        assert row["command"] in {"purchase", "order"}
        if row["command"] == "order":
            assert row["args"]["squad"].startswith(f"{row['side']}-")


def test_two_decision_traces_in_one_log_stay_separable(tmp_path: Path) -> None:
    # Interleaved telemetry: one log, two Commanders. Every row a Commander
    # caused carries the side that caused it, and a row filtered to one side
    # never mentions the other's Squads — otherwise "why did the AI do that"
    # is unanswerable for either.
    log = tmp_path / "telemetry.jsonl"
    play(commanded(log), turns=4)

    traced = rows(log, "decision") + rows(log, "command_issued")
    assert {row["side"] for row in traced} == set(SIDES)
    for side in SIDES:
        other = next(name for name in SIDES if name != side)
        mine = [row for row in traced if row["side"] == side]
        assert mine
        assert f"{other}-" not in json.dumps(mine)


def test_the_size_of_every_handover_to_the_world_is_written_down(tmp_path: Path) -> None:
    # Budget under load (#17): two Commanders double what arrives at the path
    # that carries work into the world, and the engine drains at most 100 per
    # frame (ADR-0004). The measurement is off the run's own telemetry, so it
    # has to be there — and a poll that found nothing is the ordinary case and
    # would bury the rest.
    log = tmp_path / "telemetry.jsonl"
    daemon = commanded(log)
    reply_to(daemon, id="poll-0", verb="poll")
    assert rows(log, "outbox_handed") == []

    play(daemon, turns=2)
    reply_to(daemon, id="poll-1", verb="poll")
    (handed,) = rows(log, "outbox_handed")

    assert handed["handed"] == len(daemon.outbox.pending())
    assert handed["through"] == daemon.outbox.pending()[-1].sequence

    reply_to(daemon, id="ack-1", verb="ack", payload={"through": handed["through"]})
    reply_to(daemon, id="poll-2", verb="poll")
    assert len(rows(log, "outbox_handed")) == 1


def test_the_same_pair_of_seeds_replays_the_same_campaign(tmp_path: Path) -> None:
    # Determinism at two sides. Not the planner's property — that is
    # `test_planner.py` — but the Campaign's: two Commanders, one economy, one
    # outbox, and the same pair of seeds has to land in the same place.
    first = play(commanded(tmp_path / "first.jsonl"))
    second = play(commanded(tmp_path / "second.jsonl"))

    assert fingerprint(first) == fingerprint(second)
    assert [
        {key: value for key, value in row.items() if key != "at_ns"}
        for row in rows(tmp_path / "first.jsonl", "decision")
    ] == [
        {key: value for key, value in row.items() if key != "at_ns"}
        for row in rows(tmp_path / "second.jsonl", "decision")
    ]


def test_the_pair_of_seeds_is_what_the_campaign_hangs_on(tmp_path: Path) -> None:
    # Teeth for the test above: a replay that reproduced itself under any seeds
    # would be proving that seeds do nothing. As in `test_planner.py`, the seed
    # only decides what geography has already tied, so this asks a handful of
    # pairs rather than asserting two particular ones must differ.
    played = {
        json.dumps(
            fingerprint(
                play(commanded(tmp_path / f"{west}-{east}.jsonl", {"WEST": west, "EAST": east}))
            )
        )
        for west, east in ((0, 0), (1, 4), (2, 3), (5, 1))
    }
    assert len(played) > 1


def test_the_order_two_commanders_are_registered_in_changes_nothing(tmp_path: Path) -> None:
    # Two Commanders plan inside one report cycle, so *when* each plans is a
    # detail nobody chose. Fixing it to the side order rather than to
    # registration order is what keeps a replay reproducible when a session
    # brings the sides up in the other order.
    first = commanded(tmp_path / "first.jsonl", {"WEST": 1, "EAST": 4})
    second = commanded(tmp_path / "second.jsonl", {"EAST": 4, "WEST": 1})

    assert fingerprint(play(first)) == fingerprint(play(second))


def test_the_daemon_can_be_brought_up_with_both_sides_commanded(tmp_path: Path) -> None:
    # How a session actually starts an unattended run: two flags at bring-up,
    # each carrying its own seed, and nothing else to remember.
    daemon = play(transport.build(tmp_path / "telemetry.jsonl", ai=(("WEST", 1), ("EAST", 4))))

    for side in SIDES:
        assert daemon.campaign.roster.roll(side) != ()


def test_a_bring_up_flag_names_one_side_and_the_seed_it_plays_under() -> None:
    # The flag a session actually types, and the reason side and seed travel
    # together: two sides against one list of seeds is an order to keep straight
    # in somebody's head, and the pair is what a replay hangs on.
    assert [transport.commander(text) for text in ("WEST:1", "east:4", "WEST")] == [
        ("WEST", 1),
        ("EAST", 4),
        ("WEST", 0),
    ]
    for refused in ("NORTH:1", "WEST:soon"):
        with pytest.raises(argparse.ArgumentTypeError):
            transport.commander(refused)


def test_a_daemon_under_nobodys_command_still_plans_nothing(tmp_path: Path) -> None:
    # The default #16 set, unchanged by there being room for two: a daemon
    # nobody has put under command must not quietly start playing for anybody.
    log = tmp_path / "telemetry.jsonl"
    play(Daemon(telemetry_path=log), turns=4)

    assert rows(log, "decision") == []
    assert transport.build(log, ai=()).commanders == ()


def test_a_planner_that_scores_nothing_still_drives_both_sides(tmp_path: Path) -> None:
    # ADR-0004 names HTN as the escalation and an LLM as post-MVP. Neither may
    # change the interface, and a second side does not either: the daemon knows
    # one method and holds one per side.
    log = tmp_path / "telemetry.jsonl"
    daemon = commanded(log, brains={"WEST": Spendthrift(), "EAST": Spendthrift()})
    turn(daemon, 0)

    assert [squad.squad_type for squad in daemon.campaign.roster.roll("WEST")] == ["rifle"]
    assert [squad.squad_type for squad in daemon.campaign.roster.roll("EAST")] == ["rifle"]


def test_both_traces_reach_the_log_on_the_same_cycle(tmp_path: Path) -> None:
    # One report, two Commanders, and both are asked: a cycle that planned for
    # one side and skipped the other would be a stalemate nobody could see.
    log = tmp_path / "telemetry.jsonl"
    daemon = commanded(log, brains={side: Wanderer() for side in SIDES})
    turn(daemon, 0)

    assert [row["about"] for row in rows(log, "decision")] == list(SIDES)
