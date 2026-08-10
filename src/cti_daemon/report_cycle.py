"""What one observe report does to the Campaign, in the order it does it.

The report cycle is the daemon's one use case: the world says what it can see,
that account is folded into the Campaign, the moments worth keeping are written
down, a Campaign the rules have just ended is closed, and each AI Commander
plays its turn on the picture that results. #75 found all of it living inside
`Daemon`, beside the wire decoding and the verb dispatch — dependency directions
correct, location wrong, and every Phase-2 snapshot verb and Phase-3 verdict verb
heading for the same class (ADR-0011, ADR-0012).

So it lives here, and `Daemon` decodes a line and delegates. This object holds
what a Campaign in play is made of — the Campaign itself, the Commanders playing
it, and whether its end has been announced — which is exactly the set ADR-0008's
snapshot persists, so `save` and `load` have somewhere to land that is not the
transport.

Nothing here knows what a request or a reply looks like. The one judgement that
can refuse a report from in here is `hq` naming a Base this map does not have,
and it raises `UnknownPlaceError` for the caller to answer in whatever the
caller's language is.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from cti_daemon import archive, commands, observation, report
from cti_daemon.commands import Effect

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon import campaign as campaign_module
    from cti_daemon import planner
    from cti_daemon import snapshot as snapshot_module
    from cti_daemon.port import CommandPort
    from cti_daemon.squads import Squad
    from cti_daemon.telemetry import Telemetry


class UnknownPlaceError(Exception):
    """The report named ground this Campaign's map does not have."""


class ReportCycle:
    """One Campaign in play, and what each report does to it."""

    def __init__(
        self,
        *,
        campaign: campaign_module.Campaign,
        port: CommandPort,
        telemetry: Telemetry,
        telemetry_path: Path,
        archive_path: Path,
    ) -> None:
        """Wire the cycle to the Campaign it plays and the evidence it leaves."""
        self.campaign = campaign
        self.port = port
        self._telemetry = telemetry
        # Where a won Campaign's record lands, and where its summary is read
        # from (#35, ADR-0023).
        self._telemetry_path = telemetry_path
        self._archive_path = archive_path
        # The last strategic picture written to telemetry per side, so an
        # unchanged one is not written again. Comparison only, never campaign
        # state — and never a place a side's view is read from.
        self._last_observation: dict[str, dict[str, Any]] = {}
        # The last kit each player was reported wearing, so an unchanged one is
        # not written down again (#172). Comparison only, like the observation
        # above: the Campaign holds the record, this holds "said so once".
        self._dressed: dict[str, str] = {}
        # Which side each player was last reported leading a Squad for (#312,
        # ADR-0070). Comparison only, like `_dressed` above: it exists so that a
        # player who is simply *still there* is not enrolled, reactivated or
        # re-seated on every report. The Campaign holds who leads what.
        #
        # Only the arrival half reads it. A departure is derived from the
        # Campaign instead (`active_shells`), because a cache is empty after a
        # restart and a shell whose player left while the daemon was down would
        # otherwise stay active for the rest of the Campaign.
        self._leading: dict[str, str] = {}
        # Which sides are under an AI Commander, and the brain playing each
        # (#16, #17). Empty by default: a side belongs to a human until somebody
        # says otherwise, and a Campaign nobody has put under command must not
        # quietly start playing for somebody.
        #
        # One brain per side rather than one brain asked twice. A planner holds
        # a seed and the authored data, and two sides sharing one object would
        # be one character playing both — which is also the shape in which a
        # Commander could carry state from the other side's turn into its own.
        self._commanders: dict[str, planner.Planner] = {}
        # Whether the end of this Campaign has already been announced and
        # archived (#35). Comparison only, like the observation above: the
        # Campaign holds the outcome, this holds nothing but "said so once".
        self._concluded = False

    @property
    def commanders(self) -> tuple[str, ...]:
        """The sides under AI command, in the order they play."""
        return tuple(side for side in commands.SIDES if side in self._commanders)

    def commanded(self, side: str) -> bool:
        """Whether an AI Commander is playing this side."""
        return side in self._commanders

    def commanded_by(self, side: str, brain: planner.Planner) -> None:
        """Put one side under an AI Commander for the rest of the session.

        Called once per side. Both sides at once is what #17 asks for; a second
        Commander on the *same* side is refused, because two brains on one side
        are two answers to what that side is doing and both spend the same Funds.
        """
        if side not in commands.SIDES:
            message = f"no side named {side!r} is playing"
            raise ValueError(message)
        if side in self._commanders:
            message = f"{side} is already under a Commander"
            raise ValueError(message)
        self._commanders[side] = brain

    def snapshot(self) -> snapshot_module.Snapshot:
        """Return a consistent copy of the Campaign's strategic state, for a save (#291).

        The seam `save` reaches for rather than the Campaign: this object is the
        one that holds what a Campaign in play is made of (the docstring's reason
        for existing), so the save path asks the cycle and not the aggregate. A
        frozen value, so a caller may serialise and write it off the request
        lock — the snapshot cannot move under a concurrent report, because it is
        already a photograph rather than the live object it came from.
        """
        return self.campaign.to_snapshot()

    def apply(self, snapshot: snapshot_module.Snapshot) -> tuple[str, ...]:
        """Load a snapshot into the live Campaign, and re-seat the cycle on it (#291).

        The Campaign's `apply_snapshot` validates before it mutates and raises on
        a fault, so reaching past this line means the load succeeded — and what
        this adds is the cycle's own caches. A loaded Campaign's picture differs
        from the one this cycle last wrote down, so the observation and loadout
        dedup caches are cleared to force the next report to record them rather
        than read as no-change, and a resumed Campaign has announced no end.

        The AI Commanders a session wired survive a load: they are session
        wiring, not Campaign state — ADR-0070 put a player-led Squad's own states
        into the snapshot and left which slot a player occupies where ADR-0025
        has it, on the server — so the session that loads is the session that
        decides who is playing. Returns
        the UIDs whose saved kit the menu no longer offers, passed through from
        the Campaign so a caller surfaces them.
        """
        dropped = self.campaign.apply_snapshot(snapshot)
        self._last_observation = {}
        self._dressed = {}
        # Cleared for a stronger reason than the two above: a loaded Campaign is
        # played in a world whose groups this daemon has never paired with a
        # minted Squad id, so the first report after a load has to re-seat every
        # player who is standing in a slot rather than read them as unchanged.
        self._leading = {}
        self._concluded = False
        return dropped

    def fold(self, told: report.Report) -> observation.Observation:
        """Take one report of the world into the Campaign, and play on it.

        The order is the whole of this method and the reason it exists as one
        callable: what the world has lost is reconciled before income is paid on
        what it holds, the Campaign's own rules are given the report before
        anybody acts on the result, and the end of a Campaign is announced
        before its Commanders would otherwise take one more turn inside it.

        What comes back is the public picture (#27): Objective ownership and the
        Base HQs, which is what the server repaints its markers from. No side's
        view leaves here — the server is not a Commander.
        """
        # Absent entirely, the report says nothing about Squads and the roster
        # is left alone. Present but empty, the world is saying it holds none —
        # which is a real answer, and pruning on it is the point.
        lost = () if told.squads is None else self.campaign.reconcile(told.squads)
        # After `reconcile` rather than before it, and the order is load-bearing
        # in one case: a player whose *filled* Squad was wiped out while he was
        # away leads nothing once the world's account of the losses is in, and
        # what he is owed on his return is a fresh shell rather than a reference
        # to a Squad the roster has just deleted.
        self._lead(told.squad_leaders)
        self._sight(told.contacts, told.at_time)
        self._decapitation(told.hq, told.at_time)
        self._casualties(told.casualties)
        self._dress(told.loadouts)
        for payout in self.campaign.observe(told.at_time, told.presence):
            self._telemetry.record("income", at=told.at_time, paid=payout)
        for squad_id in lost:
            self._telemetry.record("squad_lost", at=told.at_time, squad=squad_id)
        for side in commands.SIDES:
            self._record_observation(side)
        # Before the Commanders play, so a Campaign that ended on this report
        # does not get one more cycle of buying and ordering after its own end
        # screen. `_take_command` reads the same completion.
        self._conclude()
        self._take_command(told.at_time)
        return self.campaign.observation()

    def _sight(self, seen_by_side: dict[str, report.SideContacts] | None, at_time: float) -> None:
        """Fold what each side's leaders saw into that side's Contacts (#28).

        Keyed by the side that did the observing, never by the side observed:
        the report has no place to name an enemy Squad, so a Contact traceable
        to one cannot be built out of what arrives here.

        Absent entirely, the report says nothing about sightings. That matters
        more here than it does for Squads — `observed` is the removal rule, so
        reading silence as observed absence would clear the whole map.
        """
        if seen_by_side is None:
            return
        for side, seen in seen_by_side.items():
            self.campaign.sight(side, at_time=at_time, seen=seen.seen, observed=seen.observed)

    def _decapitation(self, reported: dict[str, report.HqSeen] | None, at_time: float) -> None:
        """Write down each Base HQ the world reports destroyed, once (#33).

        Observability, not campaign state: ADR-0003 keeps the snapshot
        authoritative and nothing here is ever read back. What the win-condition
        ticket needs from this is that the row exists, says whose Base fell and
        who brought it down, and that the *first* such row is the first
        destruction — `docs/mvp-scope.md` resolves a mutual Decapitation by
        telemetry order, so a second row for the same Base would make that order
        a matter of which report arrived rather than which HQ died first.

        The world keeps reporting rubble as rubble on every report, which is
        what makes the once-only rule the whole of the logic here.
        """
        if reported is None:
            return
        for base, seen in reported.items():
            side = self.campaign.based(base)
            if side is None:
                # A Base this map does not have cannot be attributed to a side,
                # and a Decapitation filed against nobody is worse than none.
                message = f"`hq.{base}` names no Base this map has"
                raise UnknownPlaceError(message)
            if not seen.destroyed:
                continue
            # The campaign holds the HQ's state because losing one ends a
            # Campaign and that is a rule (ADR-0012). It answers False for a
            # Base already down, which is what keeps this row to one per Base —
            # and what makes telemetry order mean first destruction.
            if self.campaign.raze(base, at_time=at_time):
                self._telemetry.record("hq_destroyed", at=at_time, base=base, side=side, by=seen.by)

    def _casualties(self, reported: report.Casualties | None) -> None:
        """Write down every death the world saw since the last report (#39).

        Observability, like everything else this cycle writes: ADR-0003 keeps
        the snapshot authoritative, the roster already learns about losses from
        `squads` going quiet, and nothing here is ever read back as state. What
        it buys is the question #35's timeout could not answer — a Squad went
        from eight to three and the record held only the subtraction.

        Each death is written on its own clock reading rather than the report's.
        A report is five seconds of world and a firefight is not, so timing a
        batch to the batch would flatten the sequence the row exists to preserve.

        A batch the buffer had to refuse is written down as a refusal rather than
        dropped in silence — a timeline with a hole in it must say so, or the
        hole reads as quiet.
        """
        if reported is None:
            return
        for death in reported.deaths:
            self._telemetry.record("casualty", **death)
        if reported.dropped > 0:
            self._telemetry.record("casualties_dropped", count=reported.dropped)

    def _dress(self, chosen: dict[str, str] | None, /) -> None:
        """Take the world's account of which kit each player has chosen (#172).

        The world owns the choosing — a menu at his own Base, a body dressed
        server-side — and the daemon owns the record, because that record is
        what the snapshot persists (ADR-0056, ADR-0008). Nothing goes back: the
        world already has the man in the kit.

        Absent entirely, the report said nothing about loadouts and the record
        is left alone, which is the same distinction `squads` turns on.

        Written down once per change rather than once per report, for
        `_record_observation`'s reason: reports arrive every few seconds and say
        the same thing, and a row per report would bury the moment somebody
        actually changed kit. `_dressed` is a comparison only, never state a
        Campaign is read from.

        A kit this daemon's catalogue does not offer is written down as a
        mismatch and recorded nowhere, rather than refusing the report: the
        world and the daemon read one authored file, so this is a shipped PBO
        that has drifted from the checkout, and stopping a Campaign over one
        player's kit would be a larger failure than the one being reported.
        """
        if chosen is None:
            return
        for uid, kit in chosen.items():
            if self._dressed.get(uid) == kit:
                continue
            self._dressed[uid] = kit
            if self.campaign.dress(uid, kit):
                self._telemetry.record("loadout_chosen", uid=uid, kit=kit)
            else:
                self._telemetry.record("loadout_unknown", uid=uid, kit=kit)

    def _lead(self, claimed: dict[str, str] | None, /) -> None:
        """Take the world's account of who is occupying a squad-leader slot (#312).

        The world owns the occupying — a person standing in a slot the mission
        authors — and the daemon owns what it *means*, which is ADR-0070's four
        rulings: a claim mints a dedicated roster Squad at own Base with him as
        its sole member, composition-unassigned (ruling 1); an unfilled shell
        whose player stops being named is suspended, keeping its identity and
        its minted id (ruling 7); a filled Squad's is not, because it goes on
        under an engine-selected AI leader with its Order intact (ruling 5); and
        a returning player rejoins the same Squad and leads it (ruling 6).

        Absent entirely, the report said nothing about slots and nothing here
        moves — the distinction `squads` turns on, and it matters more here:
        reading silence as "nobody is leading" would suspend every shell on the
        first report from a world whose sampler had not started.

        Nothing is done to a Campaign that has been won, for `reconcile`'s
        reason: the world does not know it is over until the effect reaches it
        and goes on reporting in the meantime, and every verb below refuses a
        finished Campaign outright rather than ignoring the call.

        The arrival half is acted on once per arrival rather than once per
        report, for `_dress`'s reason — a player who is simply still standing
        there is not re-seated every five seconds — and the effects it pushes
        make that more than tidiness: an enrolment on every report would be an
        outbox the world never drains.

        What the cache may suppress is only that: a player who is here and
        already leads the Squad the report says he does. A claim from somebody
        the roster holds no Squad for is acted on whatever the cache says, and
        that is a case rather than a belt-and-braces — a Squad wiped out to the
        last man takes its player's corpse with it, `fn_squadSample` stops
        naming a Squad with nobody living in it, and `reconcile` removes it while
        he is still standing in his slot. A cache-only reading would leave him
        leading nothing for the rest of the Campaign.
        """
        if claimed is None or self.campaign.complete:
            return

        for uid, side in claimed.items():
            squad = self.campaign.led_by(uid)
            if squad is not None and not squad.suspended and self._leading.get(uid) == side:
                continue
            self._leading[uid] = side
            self._claim(uid, side, squad)

        # Everyone the report has stopped naming, whatever it leaves behind:
        # forgotten here so that his return is an arrival again, and suspended
        # below only if what he left behind is an unfilled shell.
        for uid in [held for held in self._leading if held not in claimed]:
            del self._leading[uid]

        for shell in self.campaign.active_shells():
            if shell.player_uid in claimed:
                continue
            self.campaign.suspend(shell.id, shell.side)
            self._telemetry.record(
                "squad_leader_suspended", uid=shell.player_uid, side=shell.side, squad=shell.id
            )

    def _claim(self, uid: str, side: str, squad: Squad | None) -> None:
        """One player newly reported in a squad-leader slot, in the four cases.

        Which case it is comes from the roster rather than from the report: the
        claim names a UID (ADR-0025, because respawn hands the player a new unit
        and reconnection a new machine id), and the roster is what knows whether
        that UID already answers for a Squad. `squad` is that answer, taken by
        the caller because it is also what decides whether this is called at all.

        A claim naming a side the player's own Squad is not on is written down
        and otherwise left alone. It is not a case ADR-0070 ruled on — it needs
        him to have left one side's slot and taken the other's — and neither
        available answer is obviously right: a Squad cannot change sides, and
        minting him a second one would make `led_by` ambiguous about a player who
        is supposed to have at most one. So the roster's answer stands, the row
        says the two disagreed, and nothing is enrolled, suspended or seated on a
        guess.
        """
        if squad is None:
            minted = self.campaign.enrol(side, uid)
            self._telemetry.record("squad_leader_enrolled", uid=uid, side=side, squad=minted.id)
        elif squad.side != side:
            self._telemetry.record(
                "squad_leader_wrong_side", uid=uid, side=side, squad=squad.id, held=squad.side
            )
        elif squad.suspended:
            self.campaign.reactivate(squad.id, squad.side)
            self._telemetry.record("squad_leader_reactivated", uid=uid, side=side, squad=squad.id)
        else:
            self.campaign.rejoin(squad.id, squad.side)
            self._telemetry.record("squad_leader_rejoined", uid=uid, side=side, squad=squad.id)

    def _record_observation(self, side: str) -> None:
        """Write one side's strategic picture out when it has actually changed.

        Reports arrive every few seconds and mostly say the same thing; writing
        each one would bury the moment ownership moved under a hundred rows
        saying it had not. A row per side rather than one carrying both, because
        there is no picture carrying both to write (#27) — an operator wanting
        the whole board reads two rows. The held copy is a comparison only —
        telemetry is never read back as campaign state (ADR-0003).

        A Contact's `age` is dropped from the comparison for the same reason
        `at` is: both are clock readings that advance on their own, and a
        picture whose only change is that time passed has not moved.
        """
        document = observation.serialise(self.campaign.observation(side))
        moment = {key: value for key, value in document.items() if key != "at"}
        moment["contacts"] = [
            {key: value for key, value in contact.items() if key != "age"}
            for contact in moment.get("contacts", [])
        ]
        if moment == self._last_observation.get(side):
            return
        self._last_observation[side] = moment
        self._telemetry.record("observation", **document)

    def _conclude(self) -> None:
        """Close a Campaign the rules have just ended (#35).

        Everything a won Campaign needs that is not a rule: the world told once
        through the outbox every other effect rides, the summary read back off
        telemetry, and the record archived. Called on every report and does
        nothing on all but one of them — `_concluded` is what makes it once,
        because the world keeps reporting rubble as rubble and a Domination stays
        won on every report after it.

        A fresh Campaign next session needs no code here: the archive is a record
        rather than a resumable state (ADR-0023), so the next boot has nothing to
        load and starts a new one by construction.
        """
        outcome = self.campaign.outcome
        if outcome is None or self._concluded:
            return
        self._concluded = True

        self._telemetry.record(
            "campaign_won",
            at=outcome.at_time,
            side=outcome.winner,
            condition=outcome.condition,
            base=outcome.base,
        )
        # Summarised after the winning row is on disk, so the archive is a
        # complete account of the Campaign rather than one row short of it.
        #
        # Measured, because this reads a file that has grown all session and it
        # does it inside the `observe` the world is blocked on (#103): the read
        # is streamed rather than slurped, and how long it took is a number on
        # disk rather than an assumption, against ADR-0005's 1000 ms stall cap.
        started = time.perf_counter_ns()
        summary = archive.summarise(self._telemetry_path, outcome)
        self._telemetry.record(
            "campaign_summarised", read_us=(time.perf_counter_ns() - started) // 1_000
        )
        # The same outbox every other effect rides, reached through the Campaign
        # that owns it: an end screen is an effect like any other (ADR-0012).
        self.campaign.outbox.push(
            Effect(
                name="campaign_won",
                side=outcome.winner,
                args={
                    "condition": outcome.condition,
                    "at": outcome.at_time,
                    "summary": summary,
                },
            )
        )
        try:
            path = archive.write(self._archive_path, summary)
        except OSError as exc:
            # A Campaign that was genuinely won stays won: the world has already
            # been told, and an unwritable directory is an operator's problem
            # rather than a reason to un-end a Campaign.
            self._telemetry.record("campaign_archive_failed", detail=f"{type(exc).__name__}: {exc}")
            return
        self._telemetry.record("campaign_archived", path=str(path), summary=summary)

    def _take_command(self, at_time: float) -> None:
        """Let each AI Commander play its turn on the picture it can see (#16, #17).

        On the report's cadence rather than one of its own: the Observation is
        the reply to what the world already sends, so there is no second clock
        and nothing to keep in step. The picture is therefore up to one report
        interval old, which ADR-0005 accepted and #16 was told about.

        Each plays through the port every human Command goes through, and there
        is no other way in — that is what makes Commander symmetry structural
        rather than a convention (ADR-0012), and what leaves #19 one path to
        audit.

        Sides play in `commands.SIDES` order rather than in the order somebody
        registered them, so a Campaign replays the same way whichever order a
        session brought its Commanders up in. Nothing one Commander does inside
        a cycle is visible to the other in any case: a Command moves that side's
        own Funds, roster and Orders, and ownership only moves in the fold
        above — so playing them one after another is the same Campaign as
        playing them at once, and cheaper to reason about than a promise of it.

        Nobody plays a Campaign that has been won. An AI Commander that kept its
        turn after the end screen would spend a finished Campaign's Funds and
        fill an outbox the world has stopped acting on.
        """
        if self.campaign.complete:
            return
        for side in self.commanders:
            self._play(side, self._commanders[side], at_time)

    def _play(self, side: str, brain: planner.Planner, at_time: float) -> None:
        """One Commander's turn: decide on its own picture, order through the port."""
        # The projected picture, the same call the wire is served from: there is
        # no unprojected one for an in-process planner to reach (ADR-0012), and
        # it carries this side's Funds, this side's Squads and this side's
        # Contacts alone — which is the whole of per-side isolation (#17).
        plan = brain.plan(self.campaign.observation(side))

        for decision in plan.decisions:
            # `candidates` is the ranking and `chose` is the decision, and the
            # two need not agree (#315): where the planner substituted something
            # for the ranking's winner, the row carries the account of it, and a
            # reader that assumed `chose` was always `candidates[0]` would learn
            # nothing about the substitution from a row that went quiet. Written
            # only where there was one, so every ordinary row stays the shape it
            # has always been and `row.get("substituted")` is the whole test.
            substituted = (
                {
                    "cost": decision.substituted.cost,
                    "instead_of": decision.substituted.instead_of,
                    "price": decision.substituted.price,
                }
                if decision.substituted is not None
                else None
            )
            self._telemetry.record(
                "decision",
                at=at_time,
                side=side,
                about=decision.about,
                chose=decision.chose,
                because=decision.because,
                scored=decision.scored,
                vetoed=decision.vetoed,
                candidates=[
                    {
                        "choice": candidate.choice,
                        "score": round(candidate.score, 3),
                        "terms": {name: round(value, 3) for name, value in candidate.terms.items()},
                    }
                    for candidate in decision.candidates
                ],
                **({"substituted": substituted} if substituted is not None else {}),
            )

        for command in plan.commands:
            judgement = self.port.submit(command, acting_side=side)
            if judgement.accepted:
                # Attribution (#17): every Command reaching the port is written
                # down against the Commander that issued it, accepted ones
                # included. A log that recorded only refusals would answer who
                # did the wrong thing and never who did anything.
                self._telemetry.record(
                    "command_issued",
                    at=at_time,
                    side=side,
                    command_side=command.side,
                    command=command.name,
                    # A plain dict, so the row carries a JSON object rather than
                    # the read-only view's repr (#152).
                    args=dict(command.args),
                )
                continue
            # A refusal here is a planner bug rather than a Commander's mistake,
            # and the world is still waiting on the reply that repaints its map.
            # So it is written down and the cycle finishes.
            self._telemetry.record(
                "plan_refused",
                at=at_time,
                side=side,
                # The side the Command named, beside the Commander that issued
                # it: `wrong_side` is exactly the case where the two differ, and
                # a row carrying one of them cannot say which happened.
                command_side=command.side,
                command=command.name,
                # A plain dict, for the accepted row's reason (#152).
                args=dict(command.args),
                code=judgement.code,
                detail=judgement.detail,
            )
