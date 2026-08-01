"""The Phase-1 daemon: one request line in, one reply line out."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from cti_daemon import (
    archive,
    campaign,
    commands,
    contacts,
    economy,
    manifest,
    observation,
    planner,
    protocol,
)
from cti_daemon.commands import Effect, serialise_effect
from cti_daemon.outbox import Outbox, UnknownSequenceError
from cti_daemon.port import CommandPort
from cti_daemon.telemetry import Telemetry

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_ECONOMY = Path(__file__).parents[2] / "config" / "economy.json"
DEFAULT_MANIFESTS = Path(__file__).parents[2] / "addons" / "main" / "manifests"
DEFAULT_MAP = "stratis"

# A position is three axes. Named because the check that a death carries one
# reads as arithmetic otherwise.
_POSITION_AXES: Final = 3


class Daemon:
    """Dispatches requests and owns the outbox the game reads from."""

    def __init__(
        self,
        *,
        telemetry_path: Path,
        economy_path: Path | None = None,
        manifests_path: Path | None = None,
        archive_path: Path | None = None,
        map_id: str = DEFAULT_MAP,
    ) -> None:
        """Wire the daemon to its telemetry sink, the economy and the map."""
        self.outbox = Outbox()
        self._telemetry = Telemetry(telemetry_path)
        # Where a won Campaign's record lands, and where its summary is read
        # from (#35, ADR-0023). Beside the telemetry by default, because the two
        # are one run's evidence and separating them would be one more path for
        # a session to get wrong.
        self._telemetry_path = telemetry_path
        self._archive_path = archive_path or telemetry_path.parent / "campaigns"
        table = economy.load(economy_path or DEFAULT_ECONOMY)
        # One campaign object holds ownership, Funds and Squads, and the port
        # judges against it. Two of anything here would be two answers to how
        # much a side has or what it owns.
        self.campaign = campaign.Campaign(
            map_manifest=manifest.load_all(manifests_path or DEFAULT_MANIFESTS)[map_id],
            table=table,
            ledger=economy.Ledger(table.starting_funds),
            outbox=self.outbox,
        )
        self.port = CommandPort(campaign=self.campaign)
        # The last strategic picture written to telemetry per side, so an
        # unchanged one is not written again. Comparison only, never campaign
        # state — and never a place a side's view is read from.
        self._last_observation: dict[str, dict[str, Any]] = {}
        # Which sides are under an AI Commander, and the brain playing each
        # (#16, #17). Empty by default: a side belongs to a human until somebody
        # says otherwise, and a daemon nobody has put under command must not
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

    def commanded_by(self, side: str, brain: planner.Planner) -> None:
        """Put one side under an AI Commander for the rest of the session.

        Set at bring-up rather than passed to the constructor, because a planner
        is built from the manifest and the economy table this object has just
        loaded, and there is no sense in loading them twice to hand them back.

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

    def handle_line(self, line: str) -> str:
        """Answer one request line. Every path produces a reply."""
        started = time.perf_counter_ns()
        request_id: str | None = None
        verb: str | None = None
        # Who the caller was acting for, when the request says. A human-issued
        # Command is then attributable in the same column an AI-issued one is
        # (#17), and #19 has one attribution to audit rather than two.
        acting: str | None = None
        try:
            request = protocol.decode(line)
            request_id, verb = request.id, request.verb
            acting = self._acting_side(request)
            reply = self._dispatch(request)
            encoded = protocol.encode(reply)
        except protocol.MalformedRequestError as exc:
            request_id = exc.request_id
            reply = protocol.failed(request_id, "malformed_request", exc.detail)
            encoded = protocol.encode(reply)
        except Exception as exc:  # noqa: BLE001 — a bug must answer, not hang the caller
            # The shim is blocked on a line. Anything that escapes a handler has
            # to come back as one, or SQF waits out its read timeout instead.
            reply = protocol.failed(request_id, "internal", f"{type(exc).__name__}: {exc}")
            encoded = protocol.encode(reply)
        # A refusal is recorded with its reason, not just its shape. Otherwise
        # every rejection looks identical on disk and the operator learns less
        # about a failure than the caller who caused it.
        refusal = reply.envelope.get("reason") or reply.envelope.get("error") or {}
        self._telemetry.record(
            "request",
            id=request_id,
            verb=verb,
            side=acting,
            status=reply.envelope["status"],
            # `code` for a domain rejection, `class` for an error — one column
            # either way, because when reading a log the question is the same.
            reason_code=refusal.get("code") or refusal.get("class"),
            reason_detail=refusal.get("detail"),
            duration_us=(time.perf_counter_ns() - started) // 1_000,
            # A `callExtension` return caps at 10,240 bytes and truncates in
            # silence (ADR-0004), so how close a reply runs to it is a number
            # worth having on disk rather than a thing to find out in a session.
            reply_bytes=len(encoded),
        )
        return encoded

    @staticmethod
    def _acting_side(request: protocol.Request) -> str | None:
        """Which side a request was issued for, or None when it is nobody's.

        The gateway stamps `acting_side` server-side from its own Commander
        assignment, so that is the honest answer where it exists; `side` is what
        the caller claimed. A transport verb belongs to no side and says so by
        leaving the column empty rather than by guessing.
        """
        for key in ("acting_side", "side"):
            claimed = request.payload.get(key)
            if isinstance(claimed, str) and claimed:
                return claimed
        return None

    def _dispatch(self, request: protocol.Request) -> protocol.Reply:
        handler = self._handlers().get(request.verb)
        if handler is None:
            return protocol.failed(request.id, "unknown_verb", f"no handler for {request.verb!r}")
        return handler(request)

    def _handlers(self) -> dict[str, Callable[[protocol.Request], protocol.Reply]]:
        return {
            "ping": self._ping,
            "poll": self._poll,
            "ack": self._ack,
            "command": self._command,
            "observe": self._observe,
            "view": self._view,
        }

    def _ping(self, request: protocol.Request) -> protocol.Reply:
        result: dict[str, Any] = {"pong": True}
        return protocol.accepted(request.id, result)

    def _view(self, request: protocol.Request) -> protocol.Reply:
        """Hand one Commander the picture it may see (#18).

        A transport verb beside `observe` rather than a Command: nobody is
        instructing anything, and ADR-0012 keeps domain Commands and transport
        verbs out of one namespace. `observe` is the world reporting and gets the
        public picture back (#27) because the server is not a Commander; this is
        the server asking, on behalf of a Commander it has assigned, for the one
        view that Commander is entitled to — and the server forwards it to that
        client alone rather than reading it.

        It is `Campaign.observation(side)` and there is nothing else to serve: the
        projection is the only thing that exists (#27), so the human Commander and
        the in-process planner are reading the same call as well as commanding
        through the same port. That is what makes Commander symmetry cover knowing
        as well as commanding without a second assembly step to keep honest.

        A side under an AI Commander has no view to hand out. Not a technicality:
        that side's Funds, roster and standing Orders are the enemy's secrets to
        whoever asked, and the one door that could leak them is this one.
        """
        side = request.payload.get("side")
        if not isinstance(side, str) or side not in commands.SIDES:
            detail = f"`side` must name a side that is playing, got {side!r}"
            raise protocol.MalformedRequestError(detail, request.id)
        if side in self._commanders:
            return protocol.rejected(
                request.id,
                "wrong_side",
                f"{side} is under an AI Commander and has no human view to hand out",
            )
        return protocol.accepted(request.id, observation.serialise(self.campaign.observation(side)))

    def _observe(self, request: protocol.Request) -> protocol.Reply:
        """Take one report of what the world can see (ADR-0012's `observe`).

        A transport verb rather than a Command: nobody is instructing anything,
        the world is saying what is true. The reply is the whole strategic
        picture (#15), which is what makes this the return leg — a planner has
        something to plan against without a second channel or a second cadence.
        """
        at_time = request.payload.get("time")
        if not isinstance(at_time, (int, float)) or isinstance(at_time, bool):
            detail = "`time` must be the in-game time in seconds"
            raise protocol.MalformedRequestError(detail, request.id)

        presence = request.payload.get("presence", {})
        if not isinstance(presence, dict):
            detail = "`presence` must map Objective ids to the sides present"
            raise protocol.MalformedRequestError(detail, request.id)

        lost = self._reconcile(request)
        self._sight(request, float(at_time))
        self._decapitation(request, float(at_time))
        self._casualties(request)
        paid = self.campaign.observe(float(at_time), presence)
        for payout in paid:
            self._telemetry.record("income", at=at_time, paid=payout)
        for squad_id in lost:
            self._telemetry.record("squad_lost", at=at_time, squad=squad_id)
        for side in commands.SIDES:
            self._record_observation(side)
        # Before the Commanders play, so a Campaign that ended on this report
        # does not get one more cycle of buying and ordering after its own end
        # screen. `_take_command` reads the same completion.
        self._conclude()
        self._take_command(float(at_time))

        # The public picture alone (#27). The server repaints ownership markers
        # from this and needs nothing else, and there is no side whose view it
        # could be handed without putting an unprojected picture on the wire.
        # What each side moved and lost is on disk above, where an operator
        # reads it and a Commander does not.
        return protocol.accepted(request.id, observation.serialise(self.campaign.observation()))

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
        self.outbox.push(
            serialise_effect(
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
        own Funds, roster and Orders, and ownership only moves in `observe`
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

    def _reconcile(self, request: protocol.Request) -> tuple[str, ...]:
        """Fold the world's account of its Squads into the roster.

        Absent entirely, the report says nothing about Squads and the roster is
        left alone. Present but empty, the world is saying it holds none — which
        is a real answer, and pruning on it is the point.
        """
        seen = request.payload.get("squads")
        if seen is None:
            return ()
        if not isinstance(seen, dict):
            detail = "`squads` must map Squad ids to what the world sees of them"
            raise protocol.MalformedRequestError(detail, request.id)

        reported: dict[str, tuple[int, str]] = {}
        for squad_id, seen_squad in seen.items():
            if not isinstance(seen_squad, dict):
                detail = f"`squads.{squad_id}` must be an object"
                raise protocol.MalformedRequestError(detail, request.id)
            size = seen_squad.get("size")
            at = seen_squad.get("at", "")
            if not isinstance(size, int) or isinstance(size, bool) or not isinstance(at, str):
                detail = f"`squads.{squad_id}` needs an integer `size` and a place name `at`"
                raise protocol.MalformedRequestError(detail, request.id)
            reported[squad_id] = (size, at)
        return self.campaign.reconcile(reported)

    #: What a death the world reports must say, beyond its own clock reading and
    #: where it happened. All strings, all allowed to be empty: a garrison
    #: soldier belongs to no Squad and a man drowned by nobody has no killer, and
    #: both of those are answers rather than gaps.
    _CASUALTY_NAMES: Final = (
        "unit",
        "type",
        "squad",
        "side",
        "place",
        "by_unit",
        "by_type",
        "by_squad",
        "by_side",
        "by_vehicle",
    )

    def _casualties(self, request: protocol.Request) -> None:
        """Write down every death the world saw since the last report (#39).

        Observability, like everything else in this file's telemetry: ADR-0003
        keeps the snapshot authoritative, the roster already learns about losses
        from `squads` going quiet, and nothing here is ever read back as state.
        What it buys is the question #35's timeout could not answer — a Squad
        went from eight to three and the record held only the subtraction.

        Each death is written on its own clock reading rather than the report's.
        A report is five seconds of world and a firefight is not, so timing a
        batch to the batch would flatten the sequence the row exists to preserve.

        Position is on the row in metres as well as by place id. That is not a
        breach of ADR-0008, which keeps coordinates out of the *Observation*
        because a Commander reasons about places: no Commander reads this, and
        "3.8 km short of its target" is precisely what a place id cannot say.

        A batch the buffer had to refuse is written down as a refusal rather than
        dropped in silence — a timeline with a hole in it must say so, or the
        hole reads as quiet.
        """
        reported = request.payload.get("casualties")
        if reported is None:
            return
        if not isinstance(reported, dict):
            detail = "`casualties` must carry the deaths since the last report"
            raise protocol.MalformedRequestError(detail, request.id)

        deaths = reported.get("deaths", [])
        if not isinstance(deaths, list):
            detail = "`casualties.deaths` must be a list of deaths"
            raise protocol.MalformedRequestError(detail, request.id)

        for death in deaths:
            self._telemetry.record("casualty", **self._casualty(request, death))

        dropped = reported.get("dropped", 0)
        if not isinstance(dropped, int) or isinstance(dropped, bool):
            detail = "`casualties.dropped` must count the deaths the buffer refused"
            raise protocol.MalformedRequestError(detail, request.id)
        if dropped > 0:
            self._telemetry.record("casualties_dropped", count=dropped)

    def _casualty(self, request: protocol.Request, death: object) -> dict[str, Any]:
        """Read one death off the wire, or refuse the whole report.

        Refusing rather than skipping the bad row: a partly-read batch would
        leave a timeline that looks complete and is not, and a black box nobody
        can trust is worse than an obviously broken one.
        """
        if not isinstance(death, dict):
            detail = "`casualties.deaths` holds something that is not a death"
            raise protocol.MalformedRequestError(detail, request.id)
        # Checked above; the fields it must carry are checked below.
        reported = cast("dict[str, Any]", death)

        at = reported.get("at")
        if not isinstance(at, (int, float)) or isinstance(at, bool):
            detail = "a death needs the in-game `at` it happened at"
            raise protocol.MalformedRequestError(detail, request.id)

        position = reported.get("pos", [])
        if not isinstance(position, list) or len(cast("list[Any]", position)) != _POSITION_AXES:
            detail = "a death needs a `pos` of three coordinates"
            raise protocol.MalformedRequestError(detail, request.id)
        axes = cast("list[Any]", position)
        if any(not isinstance(axis, (int, float)) or isinstance(axis, bool) for axis in axes):
            detail = "a death's `pos` must be three numbers"
            raise protocol.MalformedRequestError(detail, request.id)

        row: dict[str, Any] = {"at": float(at), "pos": [float(axis) for axis in axes]}
        for name in self._CASUALTY_NAMES:
            said = reported.get(name, "")
            if not isinstance(said, str):
                detail = f"a death's `{name}` must be a string"
                raise protocol.MalformedRequestError(detail, request.id)
            row[name] = said
        return row

    def _decapitation(self, request: protocol.Request, at_time: float) -> None:
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
        reported = request.payload.get("hq")
        if reported is None:
            return
        if not isinstance(reported, dict):
            detail = "`hq` must map Base ids to what the world sees of their HQ"
            raise protocol.MalformedRequestError(detail, request.id)

        for base, seen in reported.items():
            side = self.campaign.based(base)
            if side is None:
                # A Base this map does not have cannot be attributed to a side,
                # and a Decapitation filed against nobody is worse than none.
                detail = f"`hq.{base}` names no Base this map has"
                raise protocol.MalformedRequestError(detail, request.id)
            if not isinstance(seen, dict):
                detail = f"`hq.{base}` must be an object"
                raise protocol.MalformedRequestError(detail, request.id)
            destroyed = seen.get("destroyed")
            by = seen.get("by", "")
            if not isinstance(destroyed, bool) or not isinstance(by, str):
                detail = f"`hq.{base}` needs a boolean `destroyed` and a side `by`"
                raise protocol.MalformedRequestError(detail, request.id)
            if not destroyed:
                continue
            # The campaign holds the HQ's state because losing one ends a
            # Campaign and that is a rule (ADR-0012). It answers False for a
            # Base already down, which is what keeps this row to one per Base —
            # and what makes telemetry order mean first destruction.
            if self.campaign.raze(base, at_time=at_time):
                self._telemetry.record("hq_destroyed", at=at_time, base=base, side=side, by=by)

    def _sight(self, request: protocol.Request, at_time: float) -> None:
        """Fold what each side's leaders saw into that side's Contacts (#28).

        Keyed by the side that did the observing, never by the side observed:
        the payload has no place to name an enemy Squad, so a Contact traceable
        to one cannot be built out of what arrives here.

        Absent entirely, the report says nothing about sightings. That matters
        more here than it does for Squads — `observed` is the removal rule, so
        reading silence as observed absence would clear the whole map.

        A malformed report is refused rather than folded in as far as it parses.
        A Commander cannot tell an empty picture from an unreadable one, and one
        of those is a reason to attack.
        """
        seen_by_side = request.payload.get("contacts")
        if seen_by_side is None:
            return
        if not isinstance(seen_by_side, dict):
            detail = "`contacts` must map each side to what its leaders saw"
            raise protocol.MalformedRequestError(detail, request.id)

        for side, report in seen_by_side.items():
            if side not in commands.SIDES:
                # `Contacts` keys on any string it is handed, so a mistyped side
                # would file a picture no observation ever reads and lose the
                # sighting without saying anything.
                detail = f"`contacts.{side}` names no side that is playing"
                raise protocol.MalformedRequestError(detail, request.id)
            if not isinstance(report, dict):
                detail = f"`contacts.{side}` must be an object"
                raise protocol.MalformedRequestError(detail, request.id)
            self.campaign.sight(
                side,
                at_time=at_time,
                seen=self._sightings(request, side, report),
                observed=self._observed(request, side, report),
            )

    def _sightings(
        self, request: protocol.Request, side: str, report: dict[str, Any]
    ) -> tuple[contacts.Sighting, ...]:
        """Read one side's sightings out of its report."""
        seen = report.get("seen", [])
        if not isinstance(seen, list):
            detail = f"`contacts.{side}.seen` must be a list of sightings"
            raise protocol.MalformedRequestError(detail, request.id)

        sightings: list[contacts.Sighting] = []
        for sighting in seen:
            if not isinstance(sighting, dict):
                detail = f"`contacts.{side}.seen` holds something that is not a sighting"
                raise protocol.MalformedRequestError(detail, request.id)
            at = sighting.get("at")
            kind = sighting.get("kind")
            age = sighting.get("age")
            if (
                not isinstance(at, str)
                or not isinstance(kind, str)
                or not isinstance(age, (int, float))
                or isinstance(age, bool)
            ):
                detail = f"a `contacts.{side}` sighting needs a place `at`, a `kind` and an `age`"
                raise protocol.MalformedRequestError(detail, request.id)
            sightings.append(contacts.Sighting(at=at, kind=kind, age=float(age)))
        return tuple(sightings)

    def _observed(
        self, request: protocol.Request, side: str, report: dict[str, Any]
    ) -> tuple[str, ...]:
        """Read the places one side's leaders actually looked at."""
        observed = report.get("observed", [])
        if not isinstance(observed, list) or not all(isinstance(place, str) for place in observed):
            detail = f"`contacts.{side}.observed` must be a list of place names"
            raise protocol.MalformedRequestError(detail, request.id)
        return tuple(observed)

    def _command(self, request: protocol.Request) -> protocol.Reply:
        """Carry one Command to the port and return its judgement (ADR-0012)."""
        try:
            command = commands.parse(request.payload)
        except commands.MalformedCommandError as exc:
            return protocol.rejected(request.id, "malformed_command", str(exc))

        # The SQF gateway stamps the acting side server-side and overwrites the
        # client's, so the two normally agree and `wrong_side` is unreachable
        # through the front door. It stays reachable for an in-process planner
        # bug and for anything that reached the daemon without the gateway —
        # which is the path #19's audit exists to find.
        acting_side = request.payload.get("acting_side", command.side)
        # One Commander per side, whichever kind it is (#18). `commanded_by`
        # already refuses a second AI brain on a side, for the reason ADR-0015
        # gives: two brains on one side are two answers to what that side is
        # doing and both spend the same Funds. A human reaching the wire while an
        # AI plays that side is the same thing arriving through the other door,
        # so it gets the same answer. Checked here rather than in the port
        # because the port is what the in-process planner calls, and a planner
        # refused for being under a Commander would be refused for existing.
        if acting_side in self._commanders:
            return protocol.rejected(
                request.id,
                "wrong_side",
                f"{acting_side} is under an AI Commander: a side has one Commander, "
                f"so bring the world up without an AI on the side you mean to play",
            )
        judgement = self.port.submit(command, acting_side=acting_side)
        if judgement.accepted:
            return protocol.accepted(request.id, judgement.result)
        return protocol.rejected(request.id, judgement.code, judgement.detail)

    def _poll(self, request: protocol.Request) -> protocol.Reply:
        """Hand over everything the game has not acknowledged yet."""
        messages = [
            {"sequence": entry.sequence, "message": entry.message}
            for entry in self.outbox.pending()
        ]
        if messages:
            # How much work one drain hands the world in one go. ADR-0004 has
            # the engine draining at most 100 callbacks per frame, and two
            # Commanders double what arrives at that path (#17) — so the size of
            # a drain is a number to have on disk rather than to estimate.
            # Written only when there is something to hand over: a poll that
            # found nothing is the ordinary case and would bury the rest.
            self._telemetry.record(
                "outbox_handed", handed=len(messages), through=messages[-1]["sequence"]
            )
        return protocol.accepted(request.id, {"messages": messages})

    def _ack(self, request: protocol.Request) -> protocol.Reply:
        """Retire everything up to the sequence the game says it received."""
        through = request.payload.get("through")
        if not isinstance(through, int) or isinstance(through, bool):
            return protocol.failed(
                request.id, "malformed_request", "`through` must be an integer sequence"
            )
        try:
            cleared = self.outbox.ack(through=through)
        except UnknownSequenceError as exc:
            return protocol.rejected(request.id, "unknown_sequence", str(exc))
        return protocol.accepted(request.id, {"cleared": cleared})
