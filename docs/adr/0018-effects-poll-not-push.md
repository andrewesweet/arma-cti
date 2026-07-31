# Effects are delivered by poll-and-ack; the callback push path is reserved, not shipped

Delegated-decision: yes
Date: 2026-07-31
Stood-in-for: human sign-off on a new ADR and on amending ADR-0005/ADR-0012 (issue #12, acceptance criteria 7–8: async path and `ExtensionCallback` registration)

#12 was specified with effects arriving by callback push: `rpc_async` fires, the reply lands on
an `ExtensionCallback` handler registered before the daemon is told to push (ADR-0005's
at-most-once rule). What shipped is `cti_fnc_effectPump`: a server-side loop that polls the
daemon's outbox over the synchronous `rpc_keepalive` every 2 s, applies what it finds, and
acknowledges through a high-water mark only after application. The pivot was half-recorded —
ADR-0012 calls it "the poll-and-ack path" in one clause and a "pushed effect message" with the
callback path's 8–17 ms latency figure in the same paragraph — but never decided. This ADR
decides it: **poll-and-ack is the production effect path, and the callback push path does not
ship in Phase 1.**

## The latency argument, in numbers

What a player experiences on a Command is two latencies, and only one of them is this path:

- **The judgement** — funds drop, accepted/rejected reaches the UI — rides the synchronous
  reply at 0.45–0.65 ms p50 (ADR-0005). The click is answered immediately regardless of how
  effects travel. That is the latency a Commander at the map actually feels, and it is out of
  perceptual range by three orders of magnitude.
- **The effect** — the Squad appears at Base, the waypoint lands — is bounded by the poll
  interval: worst 2 s, mean 1 s at the shipped default. The effect is remote (a Base or a Squad
  kilometres from the camera), so this is a marker updating on a map, not a button ignoring a
  press.

Against that, the push path's floor is 8–17 ms p50, because `ExtensionCallback` is frame-bound
(ADR-0004). So push buys roughly one second of mean effect latency. What it costs:

- **The at-most-once hazard comes back.** Callbacks fired before a handler exists are lost at
  mission boundaries (ADR-0005); the registration-ordering discipline #12's criterion 8
  describes exists to manage a hazard the poll path simply does not have.
- **A second transport channel.** The shim's exchange is strictly one line out, one line back on
  one persistent connection; a line the daemon sent unbidden would be read as the reply to the
  next request (`fn_effectPump.sqf` header). Push means either a dedicated connection or
  `rpc_async` long-polls — and `rpc_async` as written shares the persistent connection's mutex,
  so a call parked waiting for work would block every synchronous judgement behind it.
- **The reliability machinery survives anyway.** Callback delivery is at-most-once, so
  acknowledgement and replay (`outbox.py`, high-water mark, nothing acked until applied) are
  needed under push exactly as under poll. Push replaces only the trigger, not the guarantee.

And the cheap lever makes the comparison lopsided: the interval is `cti_fnc_effectPump`'s one
parameter. Halving it to 0.5 s costs one ~0.6 ms blocking call per half-second — about 0.1 % of
frame time — and brings mean effect latency to 250 ms. There is an order of magnitude of tuning
room before any architectural change is worth its risk.

Throughput does not tip it either. #17's measurements (docs/spikes/0002-two-commanders.md): the
largest drain two AI Commanders produced was 4 effects against the engine's 100-per-frame cap
(×25 headroom); the analytic worst case — both sides re-tasking their whole Stratis force at
once — is 18 (×5.5). A 4-effect drain spanned 10 frames because spawning is engine-paced, so
push would not make effects *land* faster; it would only make them *arrive* at the pump faster.

**What would overturn this.** Any of: a playtest where effect lag on an Order or Purchase is
perceptible and shortening the interval to 0.25–0.5 s does not cure it; a future effect class
that is genuinely latency-sensitive below ~100 ms (none exists in MVP scope — Orders, spawns
and the income tick all tolerate seconds); or effect volume growing until one poll's drain
presses the per-frame budget. Reopening means shipping the push path with everything above —
the registration-before-push ordering, a dedicated connection, and the same ack/replay.

## `rpc_async` is reserved capability, not dead code

Kept, unchanged, with its unit test. Not for #18 or #21: clients never load the shim — a client
speaking to the daemon over loopback is an order path outside the port and exactly what #19's
audit exists to catch (ADR-0012) — so a client's "async" is `remoteExec` to the gateway, which
never blocks the client frame, and the gateway's own call is the sub-millisecond judgement.
Neither ticket touches `rpc_async`.

Its real customer is Phase-2 persistence: snapshot save/load (ADR-0003/0008) is a genuinely
slow single call that must not stall a frame, which is precisely what ADR-0005 reserves the
async path for, and the chunking protocol already gated on Phase 2 lives beside it. Deleting
the one measured, tested implementation of the callback path to re-derive it in Phase 2 would
be waste, not hygiene; six lines of shim is not a maintenance burden. **Binding on first real
use:** before `rpc_async` carries production work it must stop sharing the persistent
connection's mutex and take its own connection, for the blocking reason above. That requirement
travels with ADR-0005's existing "chunking before Phase 2" gate rather than getting a ticket
now.

Rejected: **shipping the push path to satisfy #12's criteria as written** — pays a
registration-ordering hazard and a transport channel to improve a latency the player does not
feel, on a path with ×25 measured headroom. **Deleting `rpc_async`** — removes tested
capability a scoped near-future phase needs. **Splitting effects by urgency** (fast ones
pushed, slow ones polled) — two effect paths is exactly the audit surface ADR-0012 refused
when it kept human- and AI-issued effects on one path.

Consequences: ADR-0005 and ADR-0012 are amended in place to stop contradicting this (ADR-0005's
"effects … over the callback path" and "anything that can be slow (planner, persistence) goes
through the async path"; ADR-0012's "pushed effect message" and its 8–17 ms figure). #12's
criteria 7 and 8 are superseded in part and in whole respectively, marked on the issue with a
pointer here. The poll interval is a declared playtest tuning lever alongside the economy
numbers.
