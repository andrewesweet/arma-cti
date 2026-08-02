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

from typing import TYPE_CHECKING, Any

from cti_daemon import archive, commands, observation, report
from cti_daemon.commands import Effect

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon import campaign as campaign_module
    from cti_daemon import planner
    from cti_daemon.port import CommandPort
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
        self._sight(told.contacts, told.at_time)
        self._decapitation(told.hq, told.at_time)
        self._casualties(told.casualties)
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
        summary = archive.summarise(self._telemetry_path, outcome)
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
                    args=command.args,
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
                args=command.args,
                code=judgement.code,
                detail=judgement.detail,
            )
