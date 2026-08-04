# Death is a timer at own Base, and a dead principal watches but cannot act

Delegated-decision: no — the human took these in session
Date: 2026-08-04
Reviewed-by-human: 2026-08-04 — six rulings decided by the human in the guided
decision-capture session on #169 and recorded verbatim in that issue's closing
comment; the two names this ADR fixes (the rejection code, the check's exact seat)
were left to it by that comment and are flagged below for review
Claimed: comment on #169, 2026-08-04, after `git fetch origin` (`docs/adr/` on
origin/main topping at 0051) and a scan of every open issue's comments finding no
claim above 0051

`docs/mvp-scope.md` makes player respawn a MUST — player death must not end the
game — and until #169 nothing anywhere defined it: the only MVP MUST with no
design at all. The human walked the full tree on 2026-08-04; this ADR records the
six rulings and settles the two things the session deliberately left to the
implementing ADR. No code lands with it: the implementation is #188 and #189.

**Ruling 1 — a dead player respawns at his side's Base after a fixed timer.** No
Funds cost, no location choice. The location is total because Decapitation makes
it so: a live Campaign always has a Base, since losing it *is* losing. The
mechanism mostly exists — `missions/cti.Stratis/description.ext` already carries
`respawn = "BASE"` with `respawnDialog = 0`, and the per-side markers already sit
exactly at the manifest's Base positions — so #189 is a timer change and a
drift-proofing, not a build.

**Ruling 6 — the timer is 30 s, a playtest-tuned placeholder** in ADR-0020's
sense: documented at the line that sets it (`respawnDelay`, today 5), tunable from
playtest without reopening this decision. Moving the number is tuning; only a
second *kind* of respawn location would be a new decision.

**Ruling 2 — the Commander latch survives death.** ADR-0025 stands as written,
and its own words already decided this: the assignment is latched by player UID
"because respawn hands the player a new unit … and neither is a change of
Commander". Death does not relinquish, the slot never reopens on death, and no
reclaim machinery exists. #135's voluntary mid-session hand-off remains separate
and out of MVP; when it arrives, ADR-0025 already names its shape — an explicit
relinquish, not a longer latch.

**Ruling 3 — a dead Commander watches but cannot act.** `view` is still served to
him; Commands are refused while his unit is dead. **Ruling 5 — one dead-principal
rule**: the identical refusal, with the identical code, applies to the port's
second principal — a dead squad leader's Reinforce (ADR-0040) is refused the same
way. No asymmetry between principals.

The session left two names to this ADR:

**The code is `caller_dead`.** The working name `commander_down` fails ruling 5 by
construction — it names one principal where the refusal covers both. `caller` is
the vocabulary's own word for the resolved principal (`unknown_caller`, its
nearest sibling: both gateway-minted, both about who is asking rather than what is
asked). `dead` over `down` because dead is what the project and the engine say —
CONTEXT.md's "leader death", the scope doc's "player death", the engine's `alive`
— while "down" implies an incapacitated-but-revivable state the MVP deliberately
lacks (squad-member revive is out of scope). The shape parallels `campaign_over`:
subject, then the state that refuses. It joins `port.REJECTION_CODES` the way
`port_unavailable` did — minted at the gateway, never by the daemon, but carried
in the one vocabulary because the exported schema is what tells the world which
codes exist, and a code can never be added quietly.

**The check sits at the wire gateway, before principal resolution, and never in
`CommandPort.submit`.** The first half is ADR-0025's reasoning, which ruling 3
adopts: `submit` is what the in-process planner calls, a planner has no unit to be
dead, and a planner refused for being dead would be refused for existing. The
second half is this ADR's own finding, and it is what makes ruling 5 buildable at
all: a dead squad leader no longer *resolves* as a principal — the engine has
already passed `leader` to his successor, so `cti_fnc_leaderSquad` answers nobody
— and an aliveness check placed after resolution would type him `wrong_side`, the
exact asymmetry ruling 5 refuses. So the gateway asks aliveness as its own
question about the calling machine's player unit (`allPlayers` includes dead
players, by the wiki's own line), one check at the door covering both principals
with the same code. A machine with no player unit — a headless client, the server
calling itself — falls through to the existing path unchanged.

Rejected: **refusing `view` to a dead Commander.** Watching is not acting: no
Funds move and no Order lands on a `view`, and a Commander struck blind for every
30 s death window would re-learn his own side's board by asking it over voice,
which is the wire's job. Rejected: **death as relinquish** — reclaim machinery
ADR-0025 already declined, now declined by the human directly. Rejected:
**`commander_down`** as the landed name, for the asymmetry above.

**Ruling 4 — the Squad under a dead leader is the engine's, and the daemon does
not care.** Engine AI succession leads meanwhile: the vendored wiki's
`topics/Multiplayer_Scripting.wiki` locality list names the new leader the engine
promotes when a player-leader dies, and for us that successor is AI on the server,
so the Squad stays where ADR-0039 keeps it. The standing Order survives because
waypoints belong to the group, not to whoever leads it — `fn_orderApply`'s header
has relied on exactly that since #14. The daemon and the Observation wire are
unaffected by leadership. Engine-owned behaviour gets no implementation issue:
succession itself is not built, only relied on.

The reclaim half is not engine-owned. Nothing in the engine demotes a live
leader, so **the player regains leadership on rejoining the Squad** by mission
SQF: `selectLeader`, server-side (the wiki declares it `arg= local` to the group,
and the group is server-local for life), triggered from the server's own watch
with no new client-to-server call — the CfgRemoteExec whitelist stays one
function long. "On rejoining", not "on respawn", is the ruling's own word and its
own logic: a fresh-spawned leader at Base, kilometres away, would pull the Squad
off its standing Order to form on him, which the same ruling's "keeps executing
its standing Orders" refuses. Between respawn and rejoin he is a rifleman in his
own Squad, and the port already answers him honestly. Flagged for the human at
review rather than edited here: CONTEXT.md's Squad entry says "reclaims
leadership on respawn", which now reads loosely against the ruling — a one-word
term amendment is the human's call, and #189 is told not to touch it.

## Consequences

- #188 (gateway aliveness refusal, `caller_dead`, daemon vocabulary + schema
  export + gateway SQF + probes) and #189 (respawn timer 5 → 30 documented as a
  placeholder, marker↔manifest drift check, `selectLeader` reclaim) carry the
  implementation, both `ready-for-agent`. Independent surfaces; either lands
  first. No third issue exists, deliberately: succession is the engine's.
- `CommandPort.submit` and `fn_commanderView` are explicitly unchanged. The
  in-process planner never meets the refusal, and a dead Commander's `view` keeps
  arriving.
- The 30 s timer and #189's reclaim distance are both ADR-0020 placeholders,
  documented where set; playtest moves them without reopening this ADR.
- No CONTEXT.md edit lands here. One wording flag (Squad entry, above) awaits the
  human's review of this ADR.

## What would overturn this

- **Rulings 1/6**: a playtest wanting respawn *somewhere else in kind* — at the
  Squad, at a captured Objective — is a new decision to take, not a tune of this
  one. The number moving is not an overturn at all.
- **Ruling 2**: play showing a side genuinely headless for the death window —
  that is, the 30 s absence costing Campaigns rather than moments — would reopen
  a deputy or death-relinquish design; #135 arriving does not, since ADR-0025
  already reserves the explicit-relinquish shape for it.
- **Rulings 3/5 and the name**: a revive or incapacitation system arriving
  (out of MVP today) splits "dead" into states and reopens both the predicate and
  `caller_dead`'s name. The human preferring another name at review is one
  identifier to rename, cheap until #188 lands it on the wire and in the exported
  schema — after that it is a schema change with SQF constructors downstream.
- **Ruling 4**: an in-world probe finding a leaderless Squad stalled — succession
  not delivered — would make the behaviour ours to build and mint the issue this
  ADR declined. The human ruling "on respawn" over "on rejoining" at review
  overturns the rejoin reading and #189's trigger condition with it; the
  formation-snap cost would then need its own answer.
