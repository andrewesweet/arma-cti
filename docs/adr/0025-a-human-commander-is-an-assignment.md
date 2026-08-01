# A human Commander is a server-side assignment, and reads the same call the planner does

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on schema semantics (the `view` transport verb and what it may carry) and on a gameplay rule (one Commander per side, across both kinds), for #18
Reviewed-by-human: pending

#18 puts a person where a planner would run. ADR-0012 already fixed the commanding half — one
schema, one validator, one entry function, and a single whitelisted gateway — and its #27
amendment extended Commander symmetry to knowing as well as commanding. What it left open is how
a person *becomes* the Commander of a side, and how the picture they are entitled to reaches
their machine when a client never loads the shim (ADR-0018). Three decisions, none of them
cheaply reversible once #21 and #19's audit bind to them.

**Commanding authority is an assignment held by the server, not a property of the caller's unit.**
The gateway stamped the acting side from `side group` of the player who called it. That reads as
correct while every player is a Commander and stops being correct the moment one is not: a squad
leader fighting for WEST is on WEST, and stamping the group's side would hand the Command Port to
every rifleman on the island. So the server keeps commander-assignment state — which is the phrase
ADR-0012 used and nothing had yet been — and the gateway resolves `remoteExecutedOwner` through it.
The assignment's source is slot occupancy: the mission authors one Commander slot per side, named
`cti_commander_<side>`, and the first person to occupy it holds that side for the Play Session.
Latched by player UID rather than by unit or by machine id, because respawn hands the player a new
unit and reconnection a new machine id, and neither is a change of Commander.

Rejected: **a client claiming its side**, which puts authority in a payload the ADR already refuses
to trust; and **a second whitelisted function to register a Commander**, which buys the same fact
at the cost of the acceptance criterion that nothing but the gateway is whitelisted.

**`view` is a transport verb beside `observe`, not a widening of it.** A Commander's picture is
`Campaign.observation(side)` — the identical call the in-process planner reads, which is what makes
symmetry structural rather than a promise. It could have been folded into the `observe` reply as an
extra key. It is not, for two reasons. `observe` is the *world* reporting and its reply is
deliberately the public picture alone (#27): the server is not a Commander, and a reply carrying a
side's Funds and roster would put an unprojected board on the one machine both Commanders talk to,
which is exactly what #19's audit looks for. And the sizes differ in kind — the public picture
grows with the map, a Commander's grows with its own Squads and Contacts, and two of the latter in
one 10,240-byte reply (ADR-0004) is the shape that invites a chunking protocol invented in passing.
Asked per side, each reply is small and separately cap-checked. The server asks on behalf of the
Commander it has assigned and forwards to that client alone; it never reads what it forwards.

Rejected: **letting the client ask.** A client would have to reach the daemon to do it, and a
client speaking to the daemon is an order path outside the port (ADR-0012, ADR-0018).

**A side has one Commander, whichever kind it is.** ADR-0015 refuses a second AI brain on a side
because two brains are two answers to what that side is doing and both spend the same Funds. A
person reaching the wire while an AI plays that side is the same thing arriving through the other
door, so it gets the same answer: the Command is refused `wrong_side`, and that side's `view` is
not served at all — not a technicality, because that side's Funds, roster and standing Orders are
the enemy's secrets to whoever is asking. The check sits at the wire rather than in
`CommandPort.submit`, because `submit` is what the in-process planner calls and a planner refused
for being under a Commander would be refused for existing.

Rejected: **letting both play one side and calling it co-operative command.** It is a feature with
a name and a ticket, not a side effect of leaving a check out.

**What would overturn these** (ADR-0019). The assignment rule falls the day a Play Session wants to
hand command over mid-session — a hand-off is a change of Commander, and "first occupant holds it
for the session" is exactly what a hand-off contradicts; the replacement is an explicit relinquish,
not a longer latch. `view` as its own verb falls if the per-side picture ever shrinks to something
the public reply can carry without a second projection to keep honest, which the arrival of any
richer Contact model makes less likely rather than more. One-Commander-per-side falls to a
deliberate co-operative-command ticket and to nothing before it; a session that merely finds the
refusal inconvenient should bring the world up without an AI on the side it means to play, which is
what the refusal's own detail says.

## Consequences

- The mission's `CfgRemoteExec` whitelist is unchanged and stays one function long. The
  human-Commander path adds nothing to it: the client's only outbound call is the gateway, and
  everything travelling the other way is server-to-client remoteExec, which mode=1 does not bind.
- The map UI reads its verb list out of the exported Command Port schema rather than declaring one.
  An Order the port judges and the UI cannot express, or the reverse, is then a schema edit rather
  than a drift nobody notices — which is the mechanical form of #18's "if the human UI can express
  an order the AI cannot, the wire format has forked".
- Everything about how that UI *looks* — a hint for a panel, the number row for verbs, local
  markers for own Squads and Contacts — is a playtest-tuned placeholder in ADR-0020's sense,
  documented where it is set and not here. Phase 4 replaces the presentation without touching any
  decision above.
- A headless client cannot stand in for a person on this path, and the reason is the engine's:
  `remoteExecutedOwner` returns 0 for a call arriving from a headless client by design, and a
  headless client holds no player unit to carry a UID. In-world verification of the accepted case
  therefore needs a headed client, which `spike/probes/human-commander.sqf` drives when the run
  sends one and refuses to pretend about when it does not.
