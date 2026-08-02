# No path outside the Command Port — the Phase-1 audit

The claim Phase 1 exists to prove is Thesis 2: **one wire format for human and AI orders, and no
order path outside the port** (#3's first acceptance criterion, ADR-0012). Every Phase-1 ticket
contributes to it and none of them proves it, because the claim is about what is *absent*. This
document is the read of the surface #19 asks for: every way an Order, a Purchase, or any other
change to strategic state can reach the world, enumerated, each one either going through the port
or justified in writing.

Read at `dadf65f`, against `missions/cti.Stratis` and the addon as they ship. The three holes
below were closed under #128 on 2026-08-02, and the paths that changed with them are marked in
place; nothing else in this read has been restated. Three instruments,
because no one of them is sufficient: a static inventory of the call graph (what calls the shim,
what mutates Campaign, what mutates the world); the mission's own `CfgRemoteExec`, read out of the
running mission by `human-commander`; and the engine's refusal of a real client's calls, observed
in `client-port`. An audit that read only the source would be asserting that the code matches
itself.

## The shape of the thing

There are two channels between the world and the daemon and they carry opposite directions of
travel. Everything below is one or the other:

- the **Command Port** — a Command in, a judgement out, `verb: "command"`, the only channel that
  changes what a side has decided;
- the **world-report path** — `observe` out, the public picture back, plus the outbox (`poll` /
  `ack`) carrying the effects of judgements already made. Nobody instructs anything on it; the
  world says what is true and then acts on what the daemon decided.

The audit's claim is that the first has exactly one door on each side of every boundary it crosses,
and that the second cannot be used to instruct anything.

## Part 1 — the paths

### 1. A client into the server

| Path | Gate |
|---|---|
| `remoteExec` from a client to a server function | `missions/cti.Stratis/description.ext:39-59`. `CfgRemoteExec` `class Functions` is `mode = 1` with a whitelist of exactly one entry, `cti_fnc_portGateway`, `allowedTargets = 2`, `jip = 0`. `class Commands` is `mode = 1` with an **empty** whitelist, so no scripting command is remote-executable by a client at all. |
| `cti_fnc_portGateway` itself | `addons/main/functions/fn_portGateway.sqf:28` — `SERVER_ONLY(false)` (ADR-0041). Belt-and-braces against a `description.ext` regression, which is the one failure a config cannot defend against itself. The gateway then stamps the acting side from the server's own state and never from the payload, so a client cannot command a side it was not given. |
| the port's **two principals** (ADR-0040) | `fn_portGateway.sqf:41-59`. A Commander's side comes from the assignment state `cti_fnc_commanderAssign` latched (`cti_fnc_commanderSide`); a caller that state does not know may still be a squad leader, and then the side *and the Squad* are stamped from the group the server records as his (`cti_fnc_leaderSquad`). Two different provenances, both the server's own state, neither in the payload. `port.py:179 _principal_refusal` then holds the caller to it: a stamped Squad may issue Reinforce and nothing else, and only for that Squad. Since #128 the side is written to the payload as `acting_side` beside the Squad, and a Command that carries no such stamp is refused `unknown_caller` at the daemon (ADR-0044). |
| the map UI | `fn_mapCommander.sqf:41,55,71` (map click, map open, key down) → `fn_mapIssue.sqf:63,79-83` builds a Command through `cti_fnc_command` → `fn_mapIssue.sqf:95` `remoteExec ["cti_fnc_portGateway", 2]`. The UI decides nothing and refuses only Commands it cannot build (`fn_mapIssue.sqf:10-18, 86-90`); it has no second route. |

**Negative evidence.** `spike/probes/client-port.sqf:357-408` is the leg that asks the engine rather
than the config. A real headed client, having just proved through the gateway that its `remoteExec`
works at all, tries both classes — `[missionNamespace, [...]] remoteExec ["setVariable", 2]` and
`[...] remoteExec ["cti_fnc_portReply", 2]` — and neither lands
(`client_port_probe_command_whitelist_open`, `client_port_probe_function_whitelist_open`). The
engine writes the refusal to the *sender's* log in its own words, which is why the client's RPT is
copied into the evidence directory. `human-commander.sqf:56-72` asserts the config itself out of
the running mission: modes are 1 and 1, and the whitelist is exactly `["cti_fnc_portGateway"]`, so
a careless entry breaks a test rather than quietly voiding the guarantee.

### 2. The server into the daemon

One data-carrying extension call in the whole addon: `fn_daemonCall.sqf:112`,
`callExtension ["rpc_keepalive", …]`. `fn_shimName.sqf:11` is a `ping` with no payload. Five call
sites, one verb each:

| Caller | Verb | Mutates strategic state? |
|---|---|---|
| `fn_portGateway.sqf:93` | `command` | **Yes — this is the port.** |
| `fn_presenceReport.sqf:88` | `observe` | Ownership, income and the win conditions move here, as the daemon's own judgement on what the world reported. Nothing is instructed. |
| `fn_effectPump.sqf:92,184` | `poll`, `ack` | No — retires outbox entries already judged. |
| `fn_commanderView.sqf:79` | `view` | No — read only, and refused for a side under an AI Commander (`daemon.py:275 _view`). |

### 3. Inside the daemon

One transport (`transport.py:59-68`, newline-delimited JSON on 127.0.0.1), one entry
(`daemon.py:158 handle_line`) taking one lock, one dispatch table (`daemon.py:255 _dispatch`,
handlers at `:261-269`). Two of the six verbs can move Campaign state and no others:

- `command` → `daemon.py:360 self.port.submit(...)` → `port.py:132 CommandPort.submit`, which
  checks the acting side, then the caller's principal (`port.py:179 _principal_refusal`), then
  hands to one of three handlers (`port.py:457 HANDLERS`) → `campaign.purchase`,
  `campaign.issue`, `campaign.reinforce`;
- `observe` → `daemon.py:324 self.cycle.fold(...)` → `report_cycle.py:123,127,154,185`
  `campaign.reconcile / observe / sight / raze`.

Every one of those is a method **on the Campaign root**, not a reach through it into `Roster`,
`Contacts` or a `Squad` — #60 moved the mutations there precisely so an invariant could be stated
once where the state lives. No module outside `campaign.py` mutates those parts, and no
`Campaign`/`CommandPort` is constructed anywhere but `daemon.py:119,125`.

### 4. The AI Commander

`report_cycle.py:298 _take_command` → `:328 _play` → **`:357 self.port.submit(command,
acting_side=side)`**. The in-process planner has no privileged route: it plans against
`campaign.observation(side)`, the same projection a human Commander is served (#27), and commands
through `CommandPort.submit`, the same root a human Command reaches. That is the whole of Commander
symmetry, and it is structural rather than conventional — `port.submit` has no other caller in
`src/`, and the AI's turn is taken inside the `observe` handler, under the same lock.

### 5. The daemon back into the world

`missions/cti.Stratis/initServer.sqf:57` starts `cti_fnc_effectPump`, the only start site.
`fn_effectPump.sqf:92` polls, `:115-162` drains, `:118` calls `cti_fnc_effectApply` — **the sole
applier** — and `:181-184` acks a high-water mark. `fn_effectApply.sqf` is where the world actually
changes: `squad_spawned` creates the group and units, `order_issued` goes to `cti_fnc_orderApply`
(`:74`), `campaign_won` to `cti_fnc_campaignEnd` (`:69`), `objective_captured` to the marker path
(`:55`), `squad_reinforced` refills a Squad at its own Base (`:127`, ADR-0040), and an effect it
does not recognise is refused rather than ignored.

Nothing else applies an effect, and no SQF in the addon spawns units outside this path at all —
`fn_desyncLoad.sqf` was the exception when this was read, and #128 moved it out of the addon
entirely (ADR-0045).

### 6. World state that changes without an effect

These are the world-report path's own consequences. None of them is an Order and none of them can
be reached from a client, but the audit is not complete without them:

| Function | What it changes | Why it is not a path outside the port |
|---|---|---|
| `fn_presenceReport.sqf:104` → `fn_objectiveOwnerSet.sqf:25,30-31` | Objective owner and marker colour | Repaints the daemon's judgement; the owner is decided in `campaign.py:422 _advance_capture` and nowhere else. |
| `fn_orderEnforce.sqf:52` | Re-applies a standing Order after leader or waypoint loss | Re-applies the Order the daemon already issued; it cannot originate one. |
| `fn_baseAssault.sqf:49,107,128` | HQ damage | Consequence of a Squad under an Assault Order the port issued; the Campaign only ends when the daemon reads the HQ down. |
| `fn_campaignEnd.sqf:52,66`, `fn_campaignLost.sqf:50,62` | End-of-Campaign latches and the end screen | Both are effects or latches on effects; `fn_campaignLost` freezes `fn_daemonCall.sqf:87` rather than deciding anything. |
| `fn_worldInit.sqf:44-86` | The world's initial build | Runs once, from the manifest, before any Commander exists. |

Locality is guarded at the boundary and only there (ADR-0041, #118): `SERVER_ONLY` on the eight
loop entry points and the gateway, `INTERFACE_ONLY` on the two functions the server pushes to a
client (`fn_portReply.sqf:32`, `fn_mapObservation.sqf:28`), and a lint in
`tools/check_sqf_bans.py` that bans the hand-rolled form. Interior functions carry no guard and say
so in their headers.

## Part 2 — what is outside the envelope, and why that is allowed

Three things are outside it. None is in `missions/cti.Stratis`'s order path, and each is written
down here rather than discovered later.

1. **`missions/spike.Stratis` has no `CfgRemoteExec` at all** (`description.ext:23-34`, deliberate
   and commented), so it runs at the engine's open default, and its clients call the shim directly
   (`init.sqf:33-54`). This is the Phase-0 measurement mission, which nothing runs per issue and
   which ADR-0011 retires when `just accept` arrives. It is not the shipped mission and never
   loads the shipped `description.ext`.
2. **Probes purchase and order by building `verb: "command"` envelopes straight to the shim**
   (`spike/probe-prelude.sqf`, `base-assault.sqf`, `json-manifest.sqf`, `schema-stale.sqf:77`). A
   probe is appended to the harness on the **server**, so it is already inside the boundary the
   whitelist defends. When this was read it skipped the gateway's side stamp altogether; since #128
   it stamps `acting_side` for itself, so what a probe bypasses is the *resolution* of a caller and
   not the statement of who is acting. `client-port.sqf:229-265` asserts that a *client* cannot do
   either.
3. **`fn_desyncLoad.sqf:53-62` spawned 32 soldiers with no daemon involvement**, reachable in the
   shipped mission (`initServer.sqf:114`) behind `CTI_DESYNC_LOAD`, which only the harness sets. It
   is #8's load generator, not a Campaign mechanism: it changes what is standing on the ground and
   therefore what the presence sampler reports, which the mission's own comment already recorded as
   "it hands WEST half the island". It was the one shipped path that changed world state without a
   judgement. **No longer in the envelope's edge case, because it is no longer in the build**:
   `spike/desync-load.sqf`, staged by the run that asks for it (#128, ADR-0045).

## The holes this audit found

Reported rather than filtered, per the review rule; none of them was a client-reachable order path.
All three were closed under #128 on 2026-08-02; what each said when found, and what became of it:

- **`acting_side` defaulted to the caller's claimed side** (`daemon.py:339-343` as read). Safe only
  because `fn_portGateway.sqf` overwrites `side` server-side. Anything that reached the socket
  without the gateway commanded for any side it named — which is exactly what the probes do
  (exception 2), so the default was load-bearing for the corpus as well as a hole.
  **Closed (ADR-0044).** The gateway now stamps `acting_side` beside `acting_squad`, and the daemon
  refuses a `command` line carrying no stamp with a new rejection code, `unknown_caller`. The
  probes stamp for themselves, which is the honest form of exception 2: what a probe skips is the
  *resolution* of a caller, not the statement of who is acting. Asserted at the wire in
  `tests/unit/test_daemon_dispatch.py` and in-world by `client-port.sqf`'s `unstamped` leg.
- **The daemon's socket is unauthenticated loopback** (`transport.py:23`, `extension/src/lib.rs:15`,
  `127.0.0.1:9099`). Any process on the server host can speak the protocol. **Accepted, with the
  bind scoped back (ADR-0044).** No shared secret: every process on this host that could speak the
  protocol is ours and is authorised to command both sides, and a secret those same processes can
  read is an accident filter rather than an authentication boundary — one already covered by
  per-slot daemon ports and, now, by the stamp above. What was closed instead is the widening the
  audit did not catch: hold mode bound `0.0.0.0`, putting the socket on the LAN for exactly the
  sessions a human joins. The daemon now refuses a non-loopback bind and `spike/run.sh` no longer
  asks for one. The guarantee this audit makes remains about the *world's* paths; ADR-0018's "a
  client never speaks to the daemon" is what keeps the two apart.
- **`fn_desyncLoad` shipped**: harness-gated and world-mutating, in every build. **Closed
  (ADR-0045).** It is `spike/desync-load.sqf` now, staged into the generated harness by the run
  that sets `CTI_DESYNC_LOAD` and present in no build otherwise — the rule `spike/run.sh` already
  stated for probes, applied to the other kind of harness-only code. #8's tool is preserved, not
  deleted; its `setGroupOwner` exemption moved with it, and `check_sqf_bans` now catches anything
  put back at the vacated addon path.

## Phase-1 exit criteria, recorded

- **The stub daemon and its test are dead** — deleted earlier in the phase; no `spike` stub remains
  under `src/` or `tests/`.
- **The spike mission is superseded** by `missions/cti.Stratis`, the real thin mission (ADR-0007).
  `missions/spike.Stratis` is still on disk and is run by nothing per issue.
- **The Phase-0 spike harness and `just spike` are still alive, deliberately.** They die when
  `just accept` replaces them in Phase 3 (ADR-0011).
- **No Phase-1 code contradicts ADR-0011's acceptance-harness design.** The in-game regression tier
  built on #23 is explicitly the thin early slice of it, and its orchestration is disposable by
  design (`docs/regression-tier.md`, ADR-0016, ADR-0021).
- **No new config propagates the human's LAN IP into `localClient[]`.** The Phase-1 world boots
  `spike/phase1.cfg`, whose `localClient[]` is loopback only and says why in its own header
  (`:4-7,24`); `just probe` and `spike/regress.sh:531` both pass it explicitly. The Phase-0
  `spike/server.cfg:19` still lists the LAN address, which is #8's candidate cause 1 — it is
  `run.sh`'s default when nothing overrides it, and it is the config the Phase-1 tier never uses.

## The demo

The demo #3 asks for is composed rather than written again. Each part is a probe that already
exists and is run by the corpus:

| Act | What it shows | Where |
|---|---|---|
| Both sides played, nobody watching | Two AI Commanders on the real topology, both reaching the world through one outbox, neither side sitting still | `spike/probes/two-commanders.sqf` |
| …and it ends | An unattended two-AI Campaign won by Decapitation: a Commander's own decision, the Order across the real port, a real building down, the daemon calling it | `spike/probes/campaign-end.sqf` |
| A person in the seat, against a Commander | A headed client swept into the NATO Commander slot builds a Command by the UI path, sends it through the mode=1 whitelist, and is judged — **while CSAT is played by the seeded scorer in the same world** | `spike/probes/human-commander.sqf` |
| A person cannot get round the port | Forged side, unassigned caller, junk, invented verb, and the engine's own refusal of a non-whitelisted call | `spike/probes/client-port.sqf` |
| A person in the field, not in the seat | The port's second principal: a real client leading a Squad refills it and is refused everything else (ADR-0040) | `spike/probes/reinforce.sqf` |
| The human's eyes | The map as rendered and a refusal as it appears on screen | `docs/playtest/0001-commander-seat.md` |

The gap that composition left, and what closed it: **no world had ever held both kinds of Commander
at once.** `two-commanders` and `campaign-end` have no client; `human-commander` used to drive a
real client around a Campaign nobody was playing against. `human-commander` now brings its world up
with `CTI_AI_SIDE=EAST`, waits for that Commander to field a Squad off its own picture, and makes
the enemy roster its per-side isolation assertion is checked against a real one. That is the demo as
one thing rather than as parts.

### Watching it yourself

Act one, both sides played and nobody watching — a long soak rather than the probe's own window:

```bash
CTI_PROBE_SOAK=600 CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4 \
    just probe spike/probes/two-commanders.sqf 900
```

Act two, the seat, against a Commander playing the other side — `docs/playtest/0001-commander-seat.md`
is the briefed version of this, and its boot line is the same shape:

```bash
CTI_AI_SIDE=EAST CTI_AI_SEED=1 CTI_WINDOWS_CLIENT=1 CTI_PROBE_SOAK=1800 \
    just probe spike/playtest/session-hold.sqf 2100
```

Both acts are asserted unattended by `just regress two-commanders campaign-end human-commander
client-port`; the boot lines are for eyes, which is the one thing the tier cannot supply.

**"Take over one side" cannot mean handover, and this is where that was found.** `Daemon._command`
refuses a Command for a side an AI is playing (`daemon.py:332 _command`) and `_view` refuses that
side's picture (`daemon.py:275 _view`) — one Commander per side, whichever kind, for ADR-0015's reason: two
brains on one side are two answers to what that side is doing, and both spend the same Funds. So a
human takes a side by the world being brought up with that side free, and the demo is two acts
against one build rather than one continuous session. `human-commander` asserts both refusals
rather than leaving them as prose. Whether a real handover is wanted — an AI Commander that stands
down when a person takes the slot — is a gameplay decision and travels as #126.

## What asserts what

| Claim | Asserted by |
|---|---|
| `CfgRemoteExec` modes are 1/1 and the whitelist is one function | `human-commander.sqf:56-72` (read out of the running mission) |
| A client's non-whitelisted call does not land, in both classes | `client-port.sqf:357-408` |
| A client cannot command a side it was not assigned | `client-port.sqf:229-265` (forged), `:279-310` (unassigned) |
| A `command` line that reached the daemon without a server-side stamp is refused | `client-port.sqf` (the `unstamped` leg), `tests/unit/test_daemon_dispatch.py` |
| The daemon listens on loopback and nowhere else | `tests/unit/test_daemon_transport.py` (the bind refusal), `spike/run.sh` |
| A squad leader's authority stops at Reinforce for his own Squad | `spike/probes/reinforce.sqf` — a real client leading a Squad refills it, is refused `not_your_squad` for another, and is refused a Purchase (ADR-0040) |
| Malformed and invented Commands are refused by the port | `client-port.sqf:317-330`, `:332-349` |
| The UI's vocabulary is the port's schema, not a fork of it | `human-commander.sqf:74-97` |
| A side under an AI Commander is served no view and takes no Command | `human-commander.sqf` (the one-Commander-per-side leg) |
| Human and AI Commands travel one root | `tests/unit/test_port.py`, `tests/unit/test_report_cycle.py`, and structurally: `port.submit` has one implementation and no other callers |
| Effects reach the world only through the pump | `spike/probes/loop-watch.sqf`, `bareworld.sqf`, and every probe that waits for a bought Squad to arrive |
