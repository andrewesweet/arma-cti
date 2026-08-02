# Reinforce is a Command, and the Command Port has two principals

Delegated-decision: no
Date: 2026-08-02
Reviewed-by-human: 2026-08-02 — accepted by the human in session (the #61/#62/#63
vocabulary batch; option (a) of #62's written proposal)
Claimed: comment on #62, 2026-08-02, after `git fetch origin` (origin/main tops at
0038) and an open-issue scan (#117's agent claimed 0039)

## The decision

CONTEXT.md held two classifications of Reinforce that could not both be true: the
Command entry called it "one **Commander** instruction", the Reinforce entry called it
a "Port verb, usable by squad leader or Commander" — and ADR-0012 is explicit that
transport verbs and domain Commands never share a namespace, so "Port verb" and
"Command" are different kinds of thing in this project's own language (#62).

Two rulings, one of which is only wording:

1. **"Port verb" was loose wording, not a third payload family.** Reinforce spends
   Funds and changes strategic state, which is exactly what `commands.CATALOGUE`
   holds; the transport namespace (`ping`, `poll`, `ack`, `observe`, `view`) is where
   it plainly does not belong. The Reinforce entry now says **Command**, and "port
   verb" joins its Avoid list.

2. **The issuer set is widened deliberately: the Command Port has two principals,
   Commander and squad leader.** A squad leader may issue Reinforce for **his own
   Squad only**; Purchase and Order remain a Commander's. The Command entry stops
   claiming Commanders are the only issuers. The alternative — narrowing Reinforce to
   Commander-only — was the cheaper edit, but it removes the one strategic verb the
   squad-leader slot has: #25 exists to make that slot playable, and a leader who
   cannot refill his own Squad at his own Base plays the MVP's second mode as
   observation with a rifle.

## What the second principal costs, named now rather than discovered in the wire

Today the port has exactly one authority axis: `acting_side`, stamped server-side by
the SQF gateway from its Commander assignment (ADR-0012, ADR-0025) and compared
against `command.side` in `CommandPort.submit`. A squad-leader caller changes this in
three places, and the first implementation of Reinforce must carry all three:

- **Stamping.** The gateway has no Commander assignment for a squad leader; it stamps
  the acting side from the caller's slot. That is a different provenance — "the
  server knows who commands WEST" versus "the server trusts the client's slot" — and
  it is decided here, out loud, rather than falling out of an implementation.
- **Authorisation.** Side is no longer sufficient: a squad leader may Reinforce his
  own Squad, not any of his side's. The port needs a caller-identity → Squad check —
  an axis `Judgement` and the rejection vocabulary do not have. Expect a new
  rejection code (`not_your_squad`) and a caller identity beside `acting_side`.
- **Commander symmetry.** ADR-0012's "one wire format for human and AI" is stated
  over Commanders. A third principal is a real amendment to that model, recorded as
  an amendment note on ADR-0012 pointing here; it is not a schema addition ADR-0012's
  own consequences had already anticipated.

Pinned while it is free: Reinforce is **not** how equipment is restocked — ammo and
equipment restock is free at Base and is not a Command at all (CONTEXT.md).

## Rejected alternatives

- **(b) A distinct payload family for squad-leader verbs.** Invents a family nobody
  has designed for a wire with no room for one: `protocol.decode` dispatches on the
  envelope verb and every domain payload arrives under `command`. All cost, no gain.
- **Narrowing: Reinforce is Commander-only.** One line of CONTEXT.md and no ADR, but
  it scopes #25's squad-leader slot as a tactical seat with no port access — a
  gameplay decision that should be chosen, not defaulted into.

## Consequences

- CONTEXT.md's **Command** and **Reinforce** entries updated in this commit, in the
  proposal's accepted wording.
- No implementation here (#62's own scope): `commands.CATALOGUE` still holds only
  `purchase` and `order`. The implementation — the catalogue entry, the slot-stamped
  principal, the ownership check and its rejection code — is raised as its own issue
  and must land as one piece, because the first implementation freezes one reading
  into the wire and the exported SQF constructors.

## What would overturn this

- The squad-leader slot shipping without port access after all (#25 rescoped) would
  leave the second principal a mechanism without a user, and narrowing would be back
  on the table.
- The ownership check proving unbuildable on the gateway's actual knowledge (the
  server cannot reliably map a caller to a Squad) would force either a Commander-only
  retreat or a real identity channel, which ADR-0012 deliberately declined to invent.
- The human flipping this ADR to rejected reverts cleanly: two CONTEXT.md entries,
  one amendment note on ADR-0012, and one docstring line.
