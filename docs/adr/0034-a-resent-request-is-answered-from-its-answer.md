# A resent request is answered from its answer, never carried out twice

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on a wire-contract change (issue #69, from the #58 review) — the
request `id` and the request line acquire a meaning every future client is bound by
Reviewed-by-human: pending

The shim holds one persistent TCP connection (ADR-0005) and, when an exchange on it fails,
opens a fresh one and sends the payload again. That retry is at-least-once and cannot be
anything else: a write that succeeded before the read failed has already been carried out at
the far end, and the sender cannot tell that from a request that never arrived. Against the
Command Port that is a Purchase spending Funds twice, attributed identically — no rule refuses
it, because as far as the daemon can see two callers asked for the same thing.

**Decision: the receiver deduplicates.** A request line identical to one the daemon has already
answered is answered from the answer it was given, and nothing downstream sees it. The window
is `src/cti_daemon/dedupe.py`, 256 answers deep, keyed on a digest of the whole line.

## Why the receiver, and why the whole line

**Not "drop the retry".** It trades a duplicate Purchase for a lost one. A Command that
vanished on a transport hiccup is worse for a Commander than one that was refused, because
nothing says it happened.

**Not "resend only idempotent verbs".** It is the other candidate the issue named, and it puts
the domain inside the shim. ADR-0005 makes the shim domain-agnostic — payloads are opaque
strings — precisely so that domain changes never require a shim rebuild; a table of which verbs
may be resent is a domain fact that would have to be kept in step with the daemon's verb list
across an FFI boundary and a cross-compile. The verb list is also the wrong axis: `observe` is
a transport verb and folding one twice gives each AI Commander a second turn on one report.

**Keyed on the line, not on the id alone.** A resend is byte-identical by construction: the
shim holds the payload and writes the same bytes. Anything that differs is a different request
whose caller happened to reuse an id, and answering *that* from a cached reply would be a
wrong answer rather than a duplicate refused. Digested rather than held, because an `observe`
line is kilobytes of report the window has no use for.

The window is bounded at 256 because the hazard needs one: the shim resends only the request
whose exchange just failed. A few hundred covers several connections doing it at once and
still bounds a session-long process to a few megabytes.

## What this binds

**A request id must be unique per distinct request**, and the payload must differ when the
request does. This was already true of `cmd-<owner>-<ms>` and `poll-<ms>`; it was not reliably
true of `obs-<in-game second>` and `view-<side>-<in-game second>`, both of which are now
stamped from `diag_tickTime` — in-game time stops when the world is paused and accelerates
when it is not, so it is not a clock that only advances. A future client that stamps ids from
anything coarser is asking for its second request to be answered with its first reply.

Unique **per daemon lifetime**, which is the one place this could bite: `diag_tickTime` counts
from game launch rather than from mission start, so it survives a mission change, but a daemon
outliving the game process it was brought up with would see a client's id counter start again.
Every supported bring-up starts the daemon with the server and stops it with the server, and a
daemon that outlived a world would have a stale Campaign in it long before it had a stale
reply. If a bring-up ever separates the two lifetimes, the ids have to carry something that
does not restart with the game.

**A duplicate is written down**, as a `request_replayed` telemetry row carrying the id and the
verb. A dedupe that worked silently would hide how often the transport is actually failing,
which is the number that says whether the retry is earning its place.

**Effects are still at-least-once in the other direction** and unaffected by this. The pump
re-applies an effect whose acknowledgement was lost (`fn_effectPump.sqf`, ADR-0018); that is a
separate guarantee with its own machinery, and this ADR neither strengthens nor weakens it.

## What would overturn this

A verb whose repetition is genuinely meaningful — two identical requests that must both be
carried out — would break the "identical line means resend" reading. None exists: every verb
carries either a caller-stamped id or a clock reading, and a Command repeated on purpose is a
second Command with a second id. If one appears, the fix is to give that verb a nonce rather
than to widen the key.

A `request_replayed` rate high enough to matter would mean the transport is failing often, and
the question then is why the connection is dropping — not whether to keep deduplicating.

Rejected alongside the two above: **deduplicating only the `command` verb**, which leaves
`observe` free to give both Commanders a second turn; and **an unbounded window**, which is a
leak on a process that lives as long as a Play Session.
