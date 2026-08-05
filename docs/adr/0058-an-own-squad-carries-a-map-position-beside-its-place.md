# An own Squad carries a map position beside its Place

Delegated-decision: no
Date: 2026-08-04
Reviewed-by-human: 2026-08-04 — the direction was ruled by the human in a guided
decision-capture session on #175 ([comment][ruling], four rulings). This ADR records
the shape that ruling left open.
Claimed: comment on #175, 2026-08-04, after `git fetch origin` (origin/main at `e3b5d99`,
highest landed ADR 0057, no open issue comment claiming a number above it).

[ruling]: https://github.com/andrewesweet/arma-cti/issues/175#issuecomment-5183414364

## What was ruled, and what was left open

Playtest 0001 lost two Squads. Not to the enemy — they were alive at eight men apiece,
and the Commander could still `Tab` through them — but to the map, which drew nothing
for them because `SquadView.at` is Place-grained and a Squad on the march is standing in
no Place. A marching Squad, a pinned Squad and a Squad wiped to the last man were one
picture: absent.

The human ruled the direction: `SquadView` gains a real position field **beside** `at`,
`at` stays Place-grained, the planner does not read it at MVP, the 5 s staleness is
accepted and stated, and the wiped-Squad half rides #176 rather than this ticket.

What that leaves is the field's shape — its name, its units, its encoding, and what it
costs — which is what follows.

## The decision

**`pos`, two axes, whole metres, `[]` for a Squad no report has held.**

- **Name.** `pos` on both halves of the wire, matching the position a death already
  carries (`casualties.deaths[].pos`). CONTEXT.md reserves the word *position* for
  coordinates and forbids it as a synonym for *Place*, so this is the vocabulary's own
  word for the thing, used where the vocabulary says to use it.
- **Two axes going out, three coming in.** The world states a position the way it states
  a death's — three axes, unrounded — because that is the value `fn_squadSample` already
  has in hand from `getPosATL leader _group`, the same reading it rounds to a Place. What
  a Commander is handed is the two axes a map can draw. Nothing renders altitude on a
  strategic map, and a field nobody reads is dead weight on every Observation.
- **Whole metres.** Rounded in `cti_daemon.report`, where the reading becomes a domain
  value, and not in `serialise` — ADR-0030's precedent for a Contact's age: the document
  stays a rendering of what the Commander holds rather than a lossy version of it. A
  marker on a strategic map cannot show a metre, so the fractions are precision nothing
  downstream can use, repeated per Squad every five seconds.
- **Empty means unobserved.** `()` in Python, `[]` on the wire, for a Squad bought and
  not yet spawned — the same silence `Roster.reconcile` already refuses to read as a
  loss. `[0, 0]` would be a claim, and the map would draw a marker in the sea for it.
  `cti_fnc_mapRender` falls back to the Place's own position for such a Squad, which is
  the picture exactly as it was before this field existed.
- **Required of the world, optional in the domain.** `report.SHAPES["squad"]` declares
  `pos` `REQUIRED`, like `size` and unlike `at`: a Squad the world is holding has a
  leader standing somewhere, so there is no honest absence for the world to encode, and
  a report that omits it is refused whole rather than read as far as it parses. The
  domain's `Held.pos` defaults to `()` because a caller saying "the world holds eight men
  at Girna" is making a claim about the head count and the ground, not about a
  coordinate it would otherwise have to invent.
- **Own Squads only.** There is no such field on a `Contact` and there is not to be one.
  A Commander knowing where his own Squads are is not enemy intelligence, both Commanders
  receive the same field, and what a Commander may know of the enemy stays Place-grained
  — which is what ADR-0012's fog rule is actually about.

## What it costs

A position rides on a Squad, so an island with no Squads on it pays nothing: the
`empty_bytes` column of `tests/unit/test_budget.py::CEILINGS` did not move by a byte.
What it cost is the Squad ceiling, uniformly — a `pos` of two five-digit axes is about a
fifth again on top of a worst-case Squad record:

| Objectives | Squads a side before #175 | after |
|---|---|---|
| 8 (Stratis) | 71 | 59 |
| 20 | 52 | 44 |
| 30 | 38 | 32 |
| 40 | 24 | 21 |
| 50 | 11 | 9 |
| 60 (Altis-ish) | none | none |

ADR-0030's finding is unmoved by this, which is the reason it was affordable: the row
that fails is still the sixtieth Objective, it still fails before a Squad is bought, and
its trigger for revisiting — the per-map test failing when a second map is authored — is
the same trigger. Stratis's 59 is still well clear of what Stratis's own economy can
fund, which is what `test_every_authored_map_fits_inside_one_callextension_return`
enforces.

`budget.worst_case` measures against `(30_720, 30_720)` — Altis, the largest terrain the
engine ships. Not read off the manifest, because a Squad may march anywhere on the
terrain and a manifest only says where the Places are; and any five-digit pair costs the
wire the same, so a world wider than Altis would have to arrive before it understated
anything.

## What ADR-0008's line becomes

ADR-0008 persists strategic state and regenerates tactical state, and named "exact
positions" among the regenerated. That line holds for the **snapshot**, untouched: a
Squad's position is still regenerated at session boot and there is still nothing to
migrate. What moves is the **Observation**, by exactly one field, and the reason it can
move is that the two documents were never the same document — ADR-0008's own amendment
of 2026-08-01 already moved HQ status across this same line, in the same direction, for
the same kind of reason.

The distinction the field turns on is *seeing* against *planning*. `at` is what an Order
names, what the port's rules judge, what the planner reasons in and what a Contact is
keyed by; `pos` is what a marker is drawn at, and nothing else reads it. That is why the
planner ignoring it is a documented decision rather than an omission
(`cti_daemon.planner`'s module docstring, and #175 ruling 2): making it position-aware is
post-MVP Commander work with consequences to weigh (#173, #177), not a line to add
quietly.

## Staleness

The position rides the 5 s Observation push, so a marker trails its Squad by up to one
interval — a few tens of metres at infantry pace, on a map whose smallest meaningful
distance is a town. Accepted by the ruling and stated at
`cti_fnc_commanderView`, which is where the rate is set. Shortening the interval is not
the lever it looks like: every push is a `view` round trip per human Commander, and what
the position is for — is that Squad alive, and roughly where — does not need a fresher
answer.

## What would overturn this

- A second authored map whose worst case fails `test_every_authored_map_fits…`. The field
  is a fifth of a Squad record and the first thing to weigh against ADR-0030's untaken
  lever, positional encoding.
- A playtest finding that whole metres are too coarse or two axes too few — neither of
  which the strategic map can currently express, so it would arrive as a change to what
  the map draws rather than to what the wire carries.
- The planner becoming position-aware (#173, #177). That does not overturn the field; it
  overturns the sentence in `cti_daemon.planner` saying nothing reads it, and that
  sentence is where such a change has to announce itself.
