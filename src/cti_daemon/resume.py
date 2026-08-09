"""Projecting a restored Campaign into a fresh world, in domain order (#292).

#289 landed the snapshot document and its pure restore boundary; #290 will keep
it durable; #291 will replace the live Campaign with the one a snapshot
restored. This module is the step after the live state is back: the Arma world
starts factory-fresh every Play Session (ADR-0008 — it does not exist between
sessions), so a resumed Campaign's strategic state has to be projected *into*
that fresh world through the same ordered Effect outbox every other world
change rides (ADR-0018), and the Campaign held un-playable until the projection
is acknowledged. `reconstruct` is that projection; `Barrier` is that hold.

Order is the whole of the projection. A snapshot is a set of facts whose
application order changes the result, so the order is derived from the domain
and stated here, never left to dictionary iteration:

1. Objective ownership — the public scoreboard. It exists before anything is
   placed on it: a Squad is ordered against a board whose state is already
   settled, and the planner reasons over ownership before it reasons over
   forces.
2. Squads — spawned at their (intact) Base. A Base produces a Squad, so the
   Base is standing first; and a Squad must exist before it can carry an Order.
3. standing Orders — issued to the Squads that now exist. A Squad standing at
   its own Base under Reserve is the spawn default, so a Reserve Order projects
   nothing; only a Capture, Defend or Assault does.

Three things ADR-0008 regenerates are not in this sequence, and each absence is
a refusal rather than a gap:

- Base HQ state. A destroyed HQ ends the Campaign — `campaign.raze` calls
  `_won` the moment it sets a Base destroyed — and ADR-0023 retires the
  resumable snapshot of a completed Campaign. A snapshot that carries a
  destroyed HQ is therefore a document that should never have been resumed, and
  the projection refuses it rather than half-rebuilding a Campaign that was
  already won. Every HQ in a resumable snapshot is intact, which is the fresh
  world's authored default, so HQ state projects no Effect: there is nothing to
  tell a world that already agrees.
- Contested ownership. ADR-0008 resets a Contested Objective to its prior owner
  on resume, but the prior owner is not in the document — capture-in-progress
  is tactical and regenerated, so the stable owner a contest reverts to is
  exactly what a save written mid-contest has forgotten. The save path
  (#289/#290) must normalise a Contested Objective to its stable owner before
  this projection runs; a Contested owner reaching here is refused rather than
  guessed at, because awarding either side a contested Objective is the
  wrong-world outcome the barrier exists to prevent. This is the open question
  the close of #292 names for that save-side ticket.
- Contacts, exact positions, health, ammo, AI knowledge, corpses, weather and
  capture progress. All tactical, all regenerated from the first post-resume
  reports (ADR-0008). The barrier is what holds the world until those reports
  can flow.

Funds and the campaign clock are daemon state, not world state: the world does
not carry either, so both are restored on the live Campaign (#291) and project
no Effect. Chosen loadouts are the same shape — the world owns the choosing and
re-picks from the menu on resume (ADR-0056), reporting the pick back through the
report cycle, so the daemon's restored record is seeded by #291's load and
projected by no Effect here. Player role/Squad is deferred to #25 and absent
from the document (#289); when that decision settles, its projection arrives as
an additive stage in the order above, not a redesign of this one.

The projection is atomic: the snapshot is validated whole against the map
before any Effect is emitted, so a document that cannot be projected in full is
refused with nothing emitted — the same reasoning as #290's torn snapshot, that
a half-rebuilt Campaign continues into a wrong world rather than stopping.

The barrier is fail-closed by construction. It opens only when every
reconstruction Effect is acknowledged, and a reconstruction Effect the world
dead-lettered or that cannot cross one return keeps it shut with a typed
reason. Missing, out-of-order and duplicated Effects need no case of their own:
the high-water-mark acknowledgement the carrier already runs (#69, ADR-0034)
cannot produce them, so the barrier's response to each is simply not to open,
which is the closed state itself. This module is the mechanism; #288's decision
record is what fixes the exact set, and #291 wires it into the live daemon and
its epoch so a world attached to one daemon Campaign cannot resume against
another silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, NoReturn

from cti_daemon.commands import CONTESTED, NEUTRAL, SIDES, Effect
from cti_daemon.observation import DESTROYED
from cti_daemon.squads import NEEDS_PLACE, RESERVE

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cti_daemon.economy import EconomyTable
    from cti_daemon.manifest import MapManifest
    from cti_daemon.snapshot import Snapshot, SquadRecord


class ResumeError(Exception):
    """A restored Campaign cannot be projected into a fresh world whole.

    The one type a caller catches, in the spirit of `snapshot.SnapshotError` and
    `manifest.ManifestError`: what matters is that the projection was refused,
    and the message says why. `reconstruct` raises rather than returning a
    partial sequence, because a save that half-projects is the corrupted-world
    outcome the barrier exists to prevent (ADR-0003, #290).
    """


def _refuse(detail: str) -> NoReturn:
    """Raise the one error type callers catch. See `snapshot._refuse` on why two."""
    raise ResumeError(detail)


# The barrier's two states. `RESUMING` is the closed state a resumed Campaign
# boots into and stays in until every reconstruction Effect is acknowledged;
# `READY` is open. There is no third state: a fault does not open the barrier,
# it keeps it `RESUMING` and records a typed reason, because the response to
# every failure #292 names is "stay shut."
RESUMING: Final = "resuming"
READY: Final = "ready"

# The typed reasons a resuming barrier has not opened. Each is a fault the poll
# path reports, not a timeout: the world dead-lettered a reconstruction Effect
# it could not apply (`EFFECT_REJECTED`), or a reconstruction Effect cannot
# cross one `callExtension` return at all (`EFFECT_OVERSIZED`). Missing,
# out-of-order and duplicated Effects are absent here for the reason the
# barrier's docstring gives — the carrier's high-water mark cannot produce them.
EFFECT_REJECTED: Final = "effect_rejected"
EFFECT_OVERSIZED: Final = "effect_oversized"

# The two sides and Neutral are the scoreboard's own vocabulary, read here
# without restating them as fresh literals (#152). Named locally so the
# projection's vocabulary reads in one place alongside the Effects that speak it.
_SIDES: Final = frozenset(SIDES)
_NEUTRAL: Final = NEUTRAL


def reconstruct(
    snapshot: Snapshot, map_manifest: MapManifest, table: EconomyTable
) -> tuple[Effect, ...]:
    """Render a restored snapshot as the ordered Effects that project it into a fresh world.

    Pure: no outbox, no socket, no clock. The Effects are returned in the
    domain order above for the daemon to push onto the outbox it owns, so the
    sequence numbers the barrier waits for are assigned where every other
    Effect is (#291's wiring, not this boundary). Validates the whole snapshot
    against the map first and raises `ResumeError` with nothing emitted if any
    fact cannot be projected — atomic, for the torn-snapshot reason.

    Tactical state ADR-0008 regenerates is neither read nor emitted: the
    snapshot carries no positions, health or Contacts, so there is nothing here
    to smuggle.
    """
    _validate(snapshot, map_manifest, table)

    effects: list[Effect] = []
    # 1. The scoreboard. An Objective the snapshot holds Neutral is the fresh
    # world's authored default, so it projects nothing; only an Objective a side
    # took does. Manifest order is the domain order — the authored sequence the
    # planner's front line is read off — rather than the dictionary's.
    for objective in map_manifest.objectives:
        owner = snapshot.owners.get(objective.id, _NEUTRAL)
        if owner in _SIDES:
            effects.append(
                Effect(name="objective_captured", side=owner, args={"objective": objective.id})
            )
    # 2. Squads, in the roster order the snapshot carries them — the order they
    # were bought, which is the order ids are minted in and the order a resumed
    # Campaign must re-mint them in (ADR-0003). Spawned at strength, because the
    # head count is strategic and the per-man health around it is regenerated.
    effects.extend(
        Effect(
            name="squad_spawned",
            side=squad.side,
            args={"squad": squad.id, "squad_type": squad.squad_type, "size": squad.size},
        )
        for squad in snapshot.squads
    )
    # 3. standing Orders, to the Squads that now exist. Reserve is the spawn
    # default a Squad wears the moment it is spawned, so a Reserve Order would
    # tell the world what it already holds; only an Order that moves a Squad off
    # its Base is work the world has to carry out.
    for squad in snapshot.squads:
        if squad.order == RESERVE:
            continue
        effects.append(
            Effect(
                name="order_issued",
                side=squad.side,
                args={"squad": squad.id, "order": squad.order.kind, "place": squad.order.place},
            )
        )
    return tuple(effects)


def _validate(snapshot: Snapshot, map_manifest: MapManifest, table: EconomyTable) -> None:
    """Refuse a snapshot that cannot be projected whole, before any Effect is built.

    Every check runs before the first Effect is appended in `reconstruct`, so a
    refusal raises with nothing emitted — the atomicity the issue requires,
    tested at several points in the order rather than only the first.
    """
    objective_ids = {objective.id for objective in map_manifest.objectives}
    base_ids = {base.id for base in map_manifest.bases}
    _validate_hq(snapshot, base_ids)
    _validate_owners(snapshot, objective_ids)
    _validate_squads(snapshot, objective_ids | base_ids, table)


def _validate_hq(snapshot: Snapshot, base_ids: set[str]) -> None:
    """Refuse an HQ half the fresh world cannot agree with.

    A destroyed HQ ended the Campaign (raze calls `_won`), and a completed
    Campaign is archived rather than resumed (ADR-0023), so a destroyed HQ
    reaching here is a document that should never have been loaded as resumable.
    The fresh world's HQs are intact by authoring, so an intact HQ projects
    nothing — there is nothing to refuse about one.
    """
    for base, status in snapshot.hq.items():
        if base not in base_ids:
            _refuse(f"{base!r} is no Base this map has, but the snapshot carries its HQ")
        if status == DESTROYED:
            _refuse(
                f"{base}'s HQ is destroyed, which ends the Campaign: a completed Campaign is "
                f"archived (ADR-0023), not resumed"
            )


def _validate_owners(snapshot: Snapshot, objective_ids: set[str]) -> None:
    """Refuse an ownership half the projection cannot resolve.

    A Contested owner has no stable side to project — the prior owner ADR-0008
    reverts to is not in the document — so it is refused for the save side to
    normalise rather than guessed at here.
    """
    for objective, owner in snapshot.owners.items():
        if objective not in objective_ids:
            _refuse(
                f"{objective!r} is no Objective this map has, but the snapshot carries its owner"
            )
        if owner == CONTESTED:
            _refuse(
                f"{objective} is Contested, whose prior owner the snapshot does not carry: the "
                f"save path must normalise a contest to its stable owner before resume (ADR-0008)"
            )


def _validate_squads(snapshot: Snapshot, places: set[str], table: EconomyTable) -> None:
    """Refuse any Squad record the world cannot spawn or station whole.

    The whole roster is checked before any is spawned, so a bad record on the
    last Squad refuses exactly as one on the first does.
    """
    seen: set[str] = set()
    sold = {squad.id for squad in table.squads}
    for squad in snapshot.squads:
        if squad.id in seen:
            _refuse(f"two Squads carry the same id {squad.id!r}, which the roster mints once")
        seen.add(squad.id)
        if squad.squad_type not in sold:
            _refuse(
                f"{squad.id}: {squad.squad_type!r} is no Squad type this Campaign sells, "
                f"so the world cannot spawn it"
            )
        bought = table.sold(squad.squad_type)
        # `sold` is the table's own forgiving read; a type it sells is one it
        # has a full-strength size for, which is the upper bound a live Squad's
        # head count cannot exceed.
        if bought is not None and squad.size > bought.size:
            _refuse(
                f"{squad.id} carries {squad.size} men but a {squad.squad_type} Squad is bought at "
                f"{bought.size}, so the snapshot carries more than was paid for"
            )
        if squad.at and squad.at not in places:
            _refuse(
                f"{squad.id} stands at {squad.at!r}, which is no Objective or Base this map has"
            )
        _validate_order(squad, places)


def _validate_order(squad: SquadRecord, places: set[str]) -> None:
    """Refuse an Order the world cannot carry out for this Squad.

    Reserve is the absence of a destination (squads.NEEDS_PLACE), so an Order
    that carries a Place alongside it is a document disagreeing with itself
    about what the Squad was told.
    """
    order = squad.order
    if order.kind in NEEDS_PLACE:
        if not order.place:
            _refuse(
                f"{squad.id} carries a {order.kind} Order with no Place: only Reserve names none"
            )
        if order.place not in places:
            _refuse(
                f"{squad.id}'s {order.kind} Order names {order.place!r}, which is no "
                f"Objective or Base this map has"
            )
    elif order.place:
        _refuse(
            f"{squad.id} carries a Reserve Order alongside the Place {order.place!r}: "
            f"Reserve names no destination"
        )


@dataclass(slots=True)
class Barrier:
    """Fail-closed: a resumed Campaign is not playable until its reconstruction is acknowledged.

    Begun with the outbox sequence numbers the reconstruction's Effects were
    pushed under, and observed as the world polls and acknowledges them. It
    opens (`ready`) only when the acknowledgement's high-water mark has covered
    every reconstruction sequence and none was rejected or oversized; every
    other observation leaves it `resuming`. The daemon refuses Commands,
    suppresses AI planning, holds normal reports and serves no live Commander
    view while `resuming` — the explicit resuming state #292 puts the world in
    (#288 fixes the exact set; #291 wires the refusal into the verbs).

    A barrier begun with no sequences is ready at once: a fresh Campaign projects
    nothing, so there is nothing to wait for, and the fresh world already agrees
    with a Campaign that has no Squads, no taken ground and no kits.
    """

    _expecting: set[int] = field(default_factory=set)
    _through: int = 0
    _rejected: set[int] = field(default_factory=set)
    _oversized: set[int] = field(default_factory=set)

    @classmethod
    def awaiting(cls, sequences: Iterable[int]) -> Barrier:
        """Begin a barrier over the reconstruction's outbox sequence numbers."""
        return cls(_expecting=set(sequences))

    def acknowledge(self, *, through: int) -> None:
        """Record the world's high-water-mark acknowledgement.

        Idempotent by construction: the carrier's at-most-once delivery
        (#69, ADR-0034) makes a repeated acknowledgement after a reconnect
        ordinary, and a high-water mark re-asserted at or below its current value
        changes nothing — which is the "reconnect/retry remains idempotent" the
        issue requires.
        """
        self._through = max(self._through, through)

    def rejected(self, sequence: int) -> None:
        """Record that the world dead-lettered a reconstruction Effect it could not apply."""
        self._rejected.add(sequence)

    def oversized(self, sequence: int) -> None:
        """Record that a reconstruction Effect cannot cross one return at all."""
        self._oversized.add(sequence)

    @property
    def _unacknowledged(self) -> set[int]:
        # A high-water mark covers every sequence at or below it — there are no
        # gaps to scan for, so "still waiting" is the set the mark has not yet
        # reached.
        return {sequence for sequence in self._expecting if sequence > self._through}

    @property
    def resuming(self) -> bool:
        """Whether the Campaign is still held behind the barrier."""
        return not self.ready

    @property
    def ready(self) -> bool:
        """Whether every reconstruction Effect is acknowledged and none failed.

        A rejected or oversized Effect keeps this False even once the
        high-water mark has moved past it: the mark records what the world
        *retired*, and a dead-lettered Effect is retired without being applied,
        so the Campaign it would have rebuilt is still short a fact.
        """
        return not self._unacknowledged and not self._rejected and not self._oversized

    @property
    def outstanding(self) -> int:
        """How many reconstruction sequences the barrier is still waiting on."""
        return len(self._unacknowledged)

    @property
    def failure(self) -> str | None:
        """The typed reason the barrier has not opened, or None while it is simply draining.

        `None` is not "open": a barrier mid-drain is `resuming` with no fault,
        and a barrier whose drain has stalled is the same. A fault is a
        reconstruction Effect the world refused or could not carry, and it is
        what turns a held Campaign into a refused one.
        """
        if self._rejected:
            return EFFECT_REJECTED
        if self._oversized:
            return EFFECT_OVERSIZED
        return None
