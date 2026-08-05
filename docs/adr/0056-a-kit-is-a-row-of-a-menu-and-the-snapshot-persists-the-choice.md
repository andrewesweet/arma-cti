# A kit is a row of a menu, and the snapshot persists the choice

Delegated-decision: no — the human ruled the shape in session
Date: 2026-08-05
Reviewed-by-human: 2026-08-04 — the guided decision-capture session's closing
comment on #172 ruled all four of scope, cost, place and persistence verbatim
("a curated menu, with no class limit", "Free for MVP for players only with no
class limit. To be reviewed post MVP.", Base only, "the loadout survives
respawn **and** session save"), and routed the snapshot schema change through
this ADR because snapshot schema semantics are human-gated. The three things
that comment left to this ADR — what a menu row *is*, what the snapshot field
holds, and which channel the choice travels on — are flagged below and await
review.
Claimed: comment on #172, 2026-08-05, after `git fetch origin` (`docs/adr/` on
origin/main topping at 0055) and a scan of every open issue's comments and
bodies finding no claim above 0055.

`docs/mvp-scope.md` said nothing about loadout and #172 asked whether
customisation belonged in the MVP at all. The human ruled that it does, in the
shape above. This ADR records the shape and settles the three questions the
ruling's words leave open; the implementation lands with it.

## Ruling 1 — a curated menu, and a menu row is a whole kit

"A curated menu, with no class limit — any player may take any item on the menu
regardless of squad type." The words admit two readings, and this ADR takes the
first: **a row of the menu is one complete kit** (rifleman, grenadier,
autorifleman, anti-tank, marksman, medic), and *no class limit* means any player
may take any of those whatever squad he leads. The other reading — a whitelist
of individual items a player assembles a loadout from — is nearer the
"arsenal-style full freedom" option the same ruling declined, and "class" reads
naturally as the role class each kit is named for.

The reading is worth a sentence because it decides how much there is to author.
A kit names a **vanilla unit class per side** and nothing else:
`setUnitLoadout` takes a class name and extracts the kit from that class's
config (`commands/setUnitLoadout.wiki`, vendored), so the authored document is
six rows rather than several hundred item classnames, and every kit is exactly
what a soldier of that role spawns wearing. Retuning the menu is an edit to one
JSON file.

Rejected: **authoring item lists**. It buys mixing and matching nobody asked
for, at the cost of a document that has to be kept in step with the engine's
item vocabulary by hand, and of a snapshot field that could no longer be one
word (below).

## Ruling 2 — free, and therefore not a Command

"Free for MVP for players only with no class limit. To be reviewed post MVP."
No Funds move, so the economy is untouched: no price table entry, no Ledger
call, no new spending principal beside ADR-0040's two.

That has a consequence the ruling does not spell out and this ADR does. **A kit
is not a Command.** CONTEXT.md fixes the Command vocabulary at Purchase, Order
and Reinforce; a Command is judged by the rules and earns a Judgement, and there
is nothing here for the rules to judge — no Funds to check, no roster to change,
no Effect to deliver. So no fourth Command is minted, CONTEXT.md is not
touched, and `#19`'s no-path-outside-the-port audit is unaffected: nothing that
happens here is an order.

Players only is structural rather than a check: the watch that grants and
applies a kit walks `allPlayers`, so an AI unit is never a candidate.

## Ruling 3 — Base only, through the reading that already exists

Consistent with restock being a free Base activity (ADR-0040's pinned line). The
rule is `cti_fnc_placeOf` against the manifest, compared to the caller's own
side's Base id — which is the same reading a Squad's reported position is
derived from, and the same comparison the port's Reinforce rule makes. One
function, `cti_fnc_loadoutAtBase`, asked on two machines: the server grants
through it, and the client shows its menu action through it. The client's is
display and the server's is the rule, which is the ordinary arrangement for
anything a client can see — but it is one reading evaluated twice rather than
two readings, deliberately, because the one a player could see would otherwise
be the one that was wrong.

## Ruling 4 — the kit survives respawn, and the snapshot persists the choice

Two halves, and only the second needed deciding.

**Respawn is a watch, not a hook.** A server-side loop on the
`cti_fnc_everyInterval` adapter asks one question — *is this man wearing what he
chose?* — and dresses him when he is not. That one rule covers a respawn, a
client joining in progress, and a Campaign resumed with everybody's kit already
recorded; a respawn event handler covers the first of the three and would have
to be joined by something else for the other two. It follows #189's reasoning
for `selectLeader` exactly, and for the same second reason: no new
client-to-server call is added. The client's pick is published as a wish on his
own player object (`setVariable` with the public flag: globally broadcast and
JIP-persistent, `commands/setVariable.wiki`) and the server reads, judges and
applies it, so **the CfgRemoteExec whitelist stays one function long** — the
Command Port's gateway, as ADR-0025's consequence requires. A wish is
client-supplied and is treated as such: the menu is checked server-side, the
Base is checked server-side, and the client's copy of both is display.

`setUnitLoadout` is `arg= global, eff= global` (vendored wiki), which is what
lets the server dress a unit local to a client without a remote call at all.

**The snapshot persists the chosen kit's id, per player UID — never the engine's
loadout array.** This is the human-gated resolution the ruling routed here, and
the reasoning is ADR-0008's own. That ADR persists strategic state and
regenerates tactical state at session boot, naming ammo among the regenerated;
a `getUnitLoadout` array is mostly exactly that, down to the rounds left in each
magazine. What is strategic about a loadout is *which kit he took*. So the field
is one word per player:

    "loadouts": { "<player UID>": "<kit id>" }

ADR-0008 already anticipated this field — "player role/loadout/squad" has been
in its persisted set since it was written, arriving "with Phase 2" — so this
resolves its shape rather than adding to its list. Keyed by UID because that is
the only identity a player carries across a respawn and across a Play Session,
which is ADR-0025's reason for latching the Commander the same way.

Three things follow, and they are why the id wins:

- The persisted vocabulary stays **closed**. A kit id is one of six and is
  checked against the authored menu before it is recorded, so a snapshot cannot
  come to hold a classname somebody typed. That is what makes resume fidelity
  testable against a schema rather than against the engine.
- A resumed Campaign re-applies **today's** catalogue. An engine patch that
  renames an item, or a retune of the menu, lands on resume instead of
  resurrecting a loadout array full of classnames that no longer exist.
- A kit the menu no longer offers **defaults sensibly**, which ADR-0008 requires
  of every new field: the entry is dropped and named at load rather than
  refusing the save, so retuning the menu cannot make last week's Campaign
  unloadable.

**The choice reaches the daemon on the observe report**, as a `loadouts` field
beside `presence`, `squads`, `contacts`, `hq` and `casualties`. It is a fact only
the world can see — a player standing at his Base picked a row off a menu — which
is precisely what that wire is for, and it needs no reply: the world has already
put the man in the kit. It does **not** join the Observation. ADR-0008 keeps
player loadout snapshot-only and CONTEXT.md's Observation is a closed,
human-gated list; a Commander plans against ground, Funds, his own Squads and
Contacts, and what one of his players is wearing is none of those.

**Phase 2 has not been built.** #4 is open and unstarted: nothing under
`src/cti_daemon/` writes or reads a snapshot today. So what lands here is the
record and its round trip — `Chosen.serialise` / `Chosen.restore`, property
tested — held on the Campaign where `ReportCycle`'s own docstring says `save` and
`load` will land. Writing bytes to disk stays #4's, and it inherits a tested
carrier rather than a field to invent.

## Consequences

- One authored document, `addons/main/catalogue/loadouts.json`, read by the
  addon (`loadFile` + `fromJSON`, ADR-0017) and by the daemon
  (`cti_daemon.loadouts`). Not under `addons/main/manifests/`, whose filenames
  are a map lookup; not under `config/`, which the PBO cannot reach. Validated in
  Python over the same file that ships, so a malformed menu is a red `just unit`
  rather than a player in his underwear in a Play Session.
- The observe report grows one field, which is a schema change on both sides at
  once: `cti_daemon.report.SHAPES`, the exported `command-schema.json`, and the
  sampler that fills it. `tests/unit/test_report_schema.py` holds the two sides
  together without Arma.
- The world runs a seventh supervised loop, `loadout_watch`, registered and
  watched like the other six.
- `Campaign` grows a catalogue and a record of who wears what, defaulting to an
  empty menu so a Campaign wired without one offers no kit rather than every kit.
- CONTEXT.md is not edited. No term changes, no new Command, no Observation
  field. Whether "kit" deserves a glossary entry is the human's call at review.
- Cost is out of scope by the ruling's own words and returns post-MVP. The place
  it would attach is the wish's grant, which is the one moment a rule is applied
  to a pick.

## What would overturn this

- **Ruling 1's reading.** The human saying at review that "any item on the menu"
  meant individual items reopens the authored document's shape and, with it, the
  snapshot field: a player-assembled loadout has no single id, so the persisted
  field would become a list of item ids — still not the engine's array, but no
  longer one word.
- **The snapshot field.** A playtest finding that a player wants his *arrangement*
  preserved — a magazine moved to a vest pocket, an optic swapped — is state a kit
  id cannot carry, and would force the array (or a hybrid) with the fidelity cost
  ADR-0008 declined. Nothing short of that does: ammo counts and damage are
  already regenerated by design.
- **The wish channel.** A client found able to publish a wish for somebody else's
  body, or a public variable proving unreliable across a JIP, moves the pick onto
  the Command Port's gateway as a second whitelisted function — which is a
  widening of the audited surface and would need its own decision.
- **The watch.** A measured cost showing the sweep is not free at play scale, or
  a respawn window in which a player is visibly in the wrong kit for long enough
  to matter, argues for the `EntityRespawned` handler beside it. The sweep's
  cadence moving is tuning, not an overturn.
- **Base only.** A playtest finding that re-kitting at a captured Objective is
  what the game wants is a new decision to take, not a tune of this one — it
  would put a rule on ground the Reinforce comparison does not cover.
