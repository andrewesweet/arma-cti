# The Command Port's door is the stamp, not the socket

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on an ADR, and on a wire-format change to ADR-0012 (#128, holes 1 and 2 of `docs/command-port-audit.md`)
Reviewed-by-human: pending
Claimed: comment on #128, 2026-08-02, after `git fetch origin` (origin/main at `92a53f9`,
`docs/adr/` topping at 0042) and a scan of open-issue comments found 0043 claimed by #127's
retro batch

## The decision

Two halves of one question — what makes a caller at the daemon's socket trusted.

**1. A Command carries a server-side `acting_side` stamp, or it is refused.** The gateway
writes the field from the server's own state (a Commander's assignment, ADR-0025, or a
squad leader's slot, ADR-0040) beside the `acting_squad` stamp #123 added. The daemon
refuses a `command` line whose `acting_side` is absent, empty, or not a side that plays,
with a new rejection code `unknown_caller`. The field used to default to `command.side` —
the side the payload named — which meant a line that reached the socket without the
gateway commanded for whichever side it wrote down.

**2. The socket stays unauthenticated, and is loopback-only, and that is the boundary.**
No shared secret, no token on connect. The daemon refuses a non-loopback bind outright
(`transport.check_loopback`), and `spike/run.sh`'s hold-mode widening to `0.0.0.0` is
deleted.

## Why

The two are one decision because the first is what makes the second honest. "Any local
process can command both sides" was true in the strong sense: a stray line naming a side
was judged as that side's Commander. It is now true only in the weak sense that a process
willing to write `acting_side` can still forge one — which is a different risk with a
different answer, because *deliberate* forgery from a process on this machine is not the
hazard we have.

**Why not a shared secret.** Every process on this host that could speak the protocol is
ours and is authorised: the agent sessions all run the tests, and the tests command both
sides. A secret in a file those same processes can read is not an authentication
boundary; it is an accident filter. The accident it would filter — one run's line landing
in another run's daemon — is already prevented twice over: `spike/slots.sh` gives each
slot its own daemon port, and the stamp requirement above means a line that was not built
as a Command is refused rather than judged. #124's lesson is that our own concurrent
processes are the realistic interference on this machine, and both of those mitigations
are aimed at it. A secret would add a key to distribute, a rotation question, and a new
`infra_unavailable` mode, for a threat the machine does not have.

**Why the bind scoping is nevertheless real.** Hold mode bound every interface, which put
the socket on the LAN for exactly the sessions a human joins. The reason was Phase-0:
`missions/spike.Stratis`'s clients call the shim themselves through
`CTI_SPIKE_DAEMON_ADDRS`. The shipped mission has no such caller — ADR-0018 is that a
client never speaks to the daemon — and `just probe` runs the shipped mission, so the
widening had outlived its reason. Refused rather than defaulted, per ADR-0033: an
unauthenticated socket's address is the whole of its guarantee, so a widened one is not a
weaker guarantee but none.

**What #53 does to this.** Nothing. Remote slots reach a remote daemon over SSH, and an
SSH-carried transport is loopback at both ends — which is the point of carrying it over
SSH rather than opening the port.

## What would overturn each

- **The stamp.** A caller that legitimately cannot be resolved to a side server-side.
  None exists today: the AI Commander reaches `CommandPort.submit` in-process and never
  crosses the wire, and probes stamp for themselves because they run on the server, inside
  the boundary the `CfgRemoteExec` whitelist defends. If a Command ever has to arrive
  before its principal is known, this refusal is the wrong shape and the resolution moves.
- **The socket's acceptance.** Any of: a process on this host that is *not* ours (a mod, a
  tool, a service with its own network exposure); a mission in which a client speaks to the
  daemon; a daemon reachable off-host by something other than an SSH tunnel; or an
  occurrence of a cross-run line reaching the wrong daemon despite per-slot ports. The
  first three change who is at the socket; the last would show the accident filter was
  needed after all.
- **The loopback refusal.** A tier topology in which the daemon must be reached across a
  real network without SSH. #53 and #54 are the candidates and neither needs it today.

## Consequences

- `acting_side` is a required field of the `command` verb's payload, which amends
  ADR-0012's wire format. Everything that builds an envelope without the gateway stamps
  it: `spike/probe-prelude.sqf`, `base-assault`, `json-manifest`, `mid-campaign`.
- `unknown_caller` joins `port.REJECTION_CODES`, so it is exported to SQF with the rest of
  the vocabulary and rendered like any other refusal.
- `spike/probes/client-port.sqf` grows an `unstamped` leg: a `command` line sent straight
  to the shim with no stamp, refused `unknown_caller`, with the board unmoved. It is asked
  from the server because the whitelist is what stops a client asking it.
- `transport.main` exits 2 on a non-loopback `--host`, before it creates the telemetry
  directory, so a run that will not start leaves nothing behind.
