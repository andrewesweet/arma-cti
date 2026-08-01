# A reply carries the identity of the process that gave it, and the world freezes when that identity changes

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on a wire-contract change (issues #96 and #97, from the #95 Release It
review) — every reply gains a field, and the world gains a state it can be in
Reviewed-by-human: pending

The daemon's whole strategic state is in memory: ownership, Funds, the roster, Contacts, the
outbox, the Commanders. Nothing persists it — that is #4's, Phase 2's, gated behind ADR-0008 and
ADR-0023. So a daemon that dies mid-session and is restarted holds a factory-fresh Campaign.

The shim reconnects on a failed exchange and says nothing about it (ADR-0005), and until now
nothing in the envelope distinguished the process answering from the one that answered a second
ago. The world therefore could not tell a reconnect from a rebirth. What a player got was every
Objective repainting NEUTRAL, Funds back at the starting balance, the Domination clock restarted,
and every fielded Squad an orphan the new daemon never minted and would not take Orders for — with
one `unknown_sequence` line in a log nobody watches as the only symptom (#96).

During the outage itself the world was equally blind, for a different reason. The shim reports a
transport failure as `{"error": "..."}` of its own making. That is a JSON object, so `fromJSON`
yields a HashMap and every loop's only type check — `isEqualType createHashMap` — passed. A dead
daemon read as *success with nothing in it*: the pump found no messages and looked idle, the
report loop found no owners, repainted nothing, and incremented `replied` anyway, and the Command
Port pushed the raw error object to the human as if it were a judgement (#97).

**Decision, in three parts.**

1. **Every reply carries an `epoch`**, minted once per daemon process from its start time and pid
   (`protocol.mint_epoch`), stamped on every path out of `handle_line` — success, domain
   rejection, error, malformed line and internal bug alike.
2. **One function makes every daemon call** (`cti_fnc_daemonCall`) and returns an outcome the
   caller must branch on: `ok`, `rejected`, `error`, `unreachable`, `unreadable`, `no_shim`,
   `campaign_lost`. It latches the first epoch it sees, and it is the only place a reply is
   classified.
3. **A changed epoch freezes the world** (`cti_fnc_campaignLost`): a latched, broadcast
   `cti_campaign_lost`, a `CTI|FAIL class=node_crashed` line, a caption on every client, and every
   later daemon call refused locally without touching the wire.

## Why `status` is the discriminator, not `error`

Every reply this daemon can produce carries a `status` — `ok`, `rejected` or `error`, three things,
total by construction. The shim's own error object carries no `status` at all, because the shim
never reached anything that could give it one. So **absence of `status` is exactly "the daemon was
not spoken to"**, and unlike the presence of an `error` key it cannot be forged by a daemon reply
that happens to be about an error. The contract is published in the exported schema
(`reply_envelope` in `addons/main/generated/command-schema.json`) so the SQF branch and the
daemon's envelope are generated from one source, as ADR-0012 wants for Commands.

## Why one call site rather than a check per loop

The four loops had four copies of the same reply handling and all four had the same bug. Two of
them also carried the 10,240-byte near-cap backstop as a copied literal, and the fourth had been
written without it. A fifth caller written next week would have inherited whichever copy its author
read. The consolidation is what makes "there is no branch that reads a result without having
established there is one" a property of the code rather than of everyone's memory, and it is where
#56's SQF finding D2 already pointed.

## Why freeze rather than announce and play on

The requirement is that a player must never see a Campaign reset silently underneath them. Playing
on while announcing loudly would still repaint markers to a stranger's ownership, still apply
effects from a Campaign this world was not in, and still let a Commander spend Funds that no longer
exist — it would announce a lie rather than stop telling one. Freezing leaves the map showing the
last thing that was true.

Freezing at `cti_fnc_daemonCall` rather than in each loop means no loop was changed for it, and a
caller added later is frozen by construction. The loops keep turning at their cadence and cost
nothing, which also keeps `#72`'s breaker work on the same surface rather than in seven.

**Not `endMission`.** The MVP topology is a dedicated server plus a headless client with no human
client guaranteed, so there is often nobody to show an end screen to, and tearing the world down
takes the evidence of the Campaign with it. Same reasoning as `cti_fnc_campaignEnd`'s.

**Not resumption.** Carrying a Campaign across a restart is #4's and needs a persistence design
that does not exist. Detecting the reset is a prerequisite of ever surviving it, and it is cheap
now.

## Why the transport failure is not a `CTI|FAIL` line

`CTI|FAIL class=` is the harness's verdict channel: `spike/run.sh` stops waiting at the first one
and classifies the run from it. Typing every failed call that way would end a run at the first
hiccup, before the world could report what it did about it — which is to say no probe could ever
observe the world's response to a dead daemon, including the one that proves this ADR. So the
world's outage lines are plain `CTI|daemon_unreachable` / `CTI|daemon_down` / `CTI|daemon_recovered`,
greppable and typed but not verdicts, and the one verdict class this path spends is `node_crashed`
on the epoch change: the moment the world would otherwise start lying, and the one thing nothing in
the world can recover from.

`cti_daemon_down` is latched and cleared with one line each rather than logged per tick, so a dead
daemon is one line and a recovery is one line. Both it and `cti_campaign_lost` are broadcast, so
#18's map can read them without asking the server; presentation beyond the caption is #18's.

## Cost, and what was rejected

The epoch is 26 bytes on every reply against a 10,240-byte return cap — under a third of a percent,
and the observation budget (ADR-0030) is enforced against the encoded reply, so it is already
counted where it matters.

**Rejected: an epoch on `ping` only, or on a handshake verb.** Nothing calls `ping` during play,
and a handshake is a fact established once and then assumed. The failure being prevented is
precisely a mid-session change, so the identity has to ride the traffic that is already flowing.

**Rejected: a persisted or derived epoch.** A daemon that could recover its predecessor's epoch
would be a daemon claiming to be it, and what it holds is a factory-fresh Campaign. Start time
alone was rejected too: two processes can start inside one clock tick, and nanoseconds with the pid
cannot collide across a restart.

**Rejected: the world re-registering its Squads with the new daemon.** That is resumption with no
design behind it — the new daemon has no ledger, no ownership and no Orders to reconcile them
against, so it would produce a third Campaign that matches neither.

## Consequences

- `spike/run.sh` grew a fault injector: `CTI_DAEMON_RESTART_ON=<line>` kills the daemon and starts
  a fresh one on the same port when the probe logs that line. Triggered on the probe's line rather
  than on a clock, because the probe is what knows when it has a baseline worth losing.
- `spike/probes/daemon-restart.sqf` is the second red-by-design probe in the corpus
  (`expect: node_crashed`). A green run of it is the bug.
- The readiness line gained ` epoch=<id>` and the request telemetry gained an `epoch` column, so one
  run's evidence separates two daemons' records in one appended file.
- `port_unavailable` joins the port's rejection vocabulary — minted by the gateway, like
  `wrong_side`, and meaning that nothing was judged and nothing was spent.
- `cti_presenceReport.replied` now means what its comment always claimed: the whole leg, out and
  back. Every waiter reading it — `spike/probe-prelude.sqf`, `casualties.sqf` — was previously
  satisfiable by a dead daemon.
