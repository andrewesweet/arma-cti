# The Command Port is a domain protocol carried inside the transport envelope

The #10 envelope (`{id, verb, payload}` in, `status` of `ok`/`rejected`/`error` out, ADR-0005
transport beneath it) is the daemon's transport layer, not the Command Port. The port is a domain
protocol layered on it: one new envelope verb, `command`, whose payload is a **Command** — a
Commander instruction in the one wire format both Commanders use. Transport verbs (`ping`, `poll`,
`ack`, later `observe` for #15) and domain Commands never share a namespace.

Inbound, a Command looks like:

```json
{"id": "c-42", "verb": "command",
 "payload": {"command": "purchase", "side": "WEST", "args": {"squadType": "rifle"}}}
```

The reply to a Command is a judgement, never work: `ok` means accepted into the campaign,
`rejected` carries the typed refusal in the envelope's existing `reason: {code, detail}` shape —
`insufficient_funds`, `unknown_command`, `malformed_command`, `wrong_side` for #12. This keeps the
envelope's error/rejection split honest: an unknown *transport* verb stays an `error` (a bug in
our code), an unknown *command* is a `rejected` (a caller the rules refused), which the flat
namespace of "port = envelope" cannot express without re-typing transport faults as domain
outcomes. Because the reply carries judgement only, it stays on the synchronous keepalive path
(0.45–0.65 ms p50, ADR-0005) by construction: no Command reply ever waits on work, so the
1000 ms stall cap and the sub-millisecond discipline (#12) are structural, not aspirational.

**The daemon is the rules authority.** Strategic state — the Funds ledger above all — is
snapshot-owned (ADR-0003) and strategic (ADR-0008), so it lives in the daemon where it is
property-testable. A single Python port entry function validates Commands against it and is the
only mutator of strategic state in the process. The AI planner does not cross the wire: it
constructs the same Command objects and calls the same entry function in-process. Commander
symmetry is therefore one schema, one validator, one entry function — not two implementations
kept honest by convention.

**One server-side gateway, whitelisted alone.** The human UI builds a Command client-side and
`remoteExec`s the single gateway function to the server. `CfgRemoteExec` sets `mode = 1` in
**both** `Functions` and `Commands` classes — a mission that sets only `Functions` leaves
`Commands` at the open default — with the gateway alone whitelisted, `allowedTargets = 2`
(server-only), `jip = 0`. The gateway stamps the commanding side server-side from its own
commander-assignment state (never trusting the client's `side` field), wraps the Command in an
envelope, makes the synchronous `callExtension`, and routes the judgement back to the calling
client (server→client remoteExec is unrestricted; mode=1 binds clients only). The gateway is the
only door: a client loading the shim locally and speaking to the daemon over loopback is an order
path outside the port, and exactly what #19's audit exists to catch.

**All world effects ride the outbox, for both Commanders.** An accepted Purchase spawns its Squad
via an effect message through the poll-and-ack path (ADR-0005, `outbox.py`), not via the
synchronous reply — otherwise human-issued effects would ride the reply while AI-issued effects
(which have no request in flight) ride the outbox, and #19 would have two effect paths to audit.
*(Amended 2026-07-31, ADR-0018: this originally read "a pushed effect message" and cited the
frame-bound callback latency of 8–17 ms p50. Effects are polled, not pushed; their latency bound
is the poll interval — 2 s default, mean 1 s, a declared tuning lever — comfortably inside what
Orders tolerate. The push figure belongs to a path that does not ship; see ADR-0018.)*
Effect messages are schema'd from the same source as Commands. An `ok` result is advisory only —
it may carry data for immediate UI display (remaining Funds, say) but never an instruction to
mutate the world; world mutations are exclusively effect-message-driven.

**`RVExtensionContext` is deliberately unused.** With a server-side gateway, every
`callExtension` originates on the server, so the per-call steamID would identify the server, not
the commanding client. Commander attribution is the gateway's server-side stamp (from
`remoteExecutedOwner` and commander-assignment state). No parallel identity channel is invented;
if a later phase moves calls off the server, this is the paragraph to revisit.

**One format, enforced by construction.** A single schema source in the repo defines Commands and
effect messages. The daemon is the sole validator and carries the round-trip property tests
(#12). SQF constructors are derived from the same source, following #11's manifest→generated-SQF
precedent; the Squad price table is data in that same pipeline, consumed by the daemon for rules
and by the UI for display only. #19's audit becomes mechanical on both sides: SQF-side, no
Command payload leaves except through the gateway; Python-side, no strategic mutation except
through the port entry function.

Rejected: **(a) port = envelope** (domain verbs flat beside `ping`/`poll`/`ack`) — collapses the
error/rejection typing above, makes the planner construct transport envelopes with correlation
ids it has no business holding, and turns #19's audit into maintaining a verb registry instead of
spotting a payload family. **Rules engine in SQF** (daemon calls into a server-side port) — puts
the Funds ledger in the world, outside property testing and the snapshot boundary, and makes the
planner take a wire hop to consult rules it lives next to. **Async-only command log** (Commands
appended and judged via push, no synchronous reply) — uniform with the push path but denies the
UI immediate rejection feedback that the measured sub-millisecond path provides for free.

Amended 2026-07-31 (#27, grilling session): **Commander symmetry covers knowing as well as commanding.** The argument above — one schema, one validator, one entry function, rather than two implementations kept honest by convention — applies with equal force to what each Commander may know. So the daemon holds the Campaign's truth privately and exposes only a per-side projection: a Commander's own Squads and Funds in full, Objective ownership and Base HQ status as public facts, and everything else about the enemy as **Contacts** (`CONTEXT.md`) rather than roster entries. Enemy Funds, force count, Squad identity and standing Orders never leave the daemon.

Enforced structurally rather than by convention, for the same reason: the planner runs in-process (see above), so a projection applied at the wire would be one the planner walks straight past — and the failure is silent, because a planner reading unprojected state passes every test while quietly seeing everything. There is therefore no unprojected Observation to read.

Rejected: **giving the AI Commander perfect information as a difficulty lever.** It is the cheap route to a competent opponent, and it makes "is the scorer any good" unanswerable — competence and omniscience are indistinguishable from the outside — while leaving the two Commanders playing different games.

Consequences: #14, #15, #16/#17 and #18 all bind to the Command/effect schema, not to the
envelope; new port verbs are schema additions, not transport changes. The Phase-2 chunking
protocol stays in the shim's framing layer (ADR-0005) untouched, since payloads remain opaque to
it. Approved for `CONTEXT.md` alongside this ADR: **Command** — one Commander instruction sent
through the Command Port: Purchase, Order, or Reinforce. _Avoid_: message, request, packet;
"command" unqualified for engine scripting commands (say "scripting command").
