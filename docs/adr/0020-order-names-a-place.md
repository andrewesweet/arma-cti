# An Order names a Place, and Assault(enemy Base) makes Decapitation a strategy

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: gameplay decision (which win conditions the Order vocabulary must serve, and which failure mode to prefer) and CONTEXT.md term changes (Order, Base; new Assault and Place) — #31, flagged from #16
Reviewed-by-human: pending

#16 shipped an AI Commander that plays for Domination only, and said why: an Order names an
Objective, a Base is not one, so the port cannot express "go for the enemy HQ" — the port's
vocabulary to widen, not something for a scorer to route around. `docs/mvp-scope.md` names two
win conditions, and ADR-0012 says no order path exists outside the port, so until this is decided
one of the two is unreachable by any Commander and undefendable by the AI. #31 asks for the
decision before the win-condition ticket exists. This is it.

**An Order names a Place.** A Place is any authored ground the manifest ids: an Objective or a
Base. The Order's ground field is renamed `objective` → `place` in the same stroke, everywhere it
means ground — the Command catalogue, the `order_issued` effect, `squads.Order`, `SquadView` —
because a field named `objective` that carries Base ids is term drift baked into the wire, and
Phase 2 will freeze this exact shape into the snapshot schema (the Observation is deliberately
the set the snapshot persists, ADR-0008). Rename now, while nothing persisted holds the old name.
One id namespace follows: the manifest must refuse an Objective id that collides with a Base id,
which today it only checks per kind.

**The vocabulary.** Capture(Objective) is unchanged. Defend widens to the side's **own Base** —
the AI cannot defend against Decapitation without it, and neither can a human Commander order it.
One new Order kind, **Assault(enemy Base)**: a standing instruction to close with the enemy Base
and destroy its HQ structure — Decapitation as an Order. Reserve is unchanged. The port types the
refusals: Capture never names a Base, Assault never names an Objective or its own Base, Defend
never names the enemy Base — all one new rejection code, `wrong_ground` (ground the map has, that
this Order may not name); ids the map lacks stay `malformed_command`. ADR-0012's consequences
already anticipate this ("new port verbs are schema additions, not transport changes"), so 0012
itself is not amended.

**Bases do not become Objectives.** Objective ownership by presence, income, and the Domination
count are untouched; a Base still has no owner, pays nothing, and dies rather than changing
hands. What changes is only what an Order may say about it.

**Both win conditions stand, and the anticlimax is the failure to prefer.** Domination and
Decapitation were decided together in `docs/mvp-scope.md` (2026-07-30) and are not reopened here
— this ADR makes the second of them expressible, which is the opposite of dropping it. Between
the two failure modes #31 poses — the grind of a campaign that can only end by taking every
Objective, and the anticlimax of a raid on an undefended Base — prefer the anticlimax, for three
reasons. It is preventable *by play*: this vocabulary gives both Commanders the words to defend a
Base, and the scorer's fog floor already garrisons unwatched own ground unprompted (ADR-0014's
fourth call), so an undefended Base is a Commander's error, not the game's. It is instructive:
losing to a raid teaches rear security, which is tactical content for the squad-leader player;
the grind teaches nothing and punishes the *winning* side with the boring tail of every campaign.
And it keeps the Stipend's promise: a side strangled economically can still win by one raid,
where Domination-only makes a lost position merely slow to lose. The grind, by contrast, is
preventable only by authoring, never at the table.

**What the scorer needs, with ADR-0014 standing.** The adjacency graph already carries both Bases
as nodes with authored distances, and `Squad.at` already names them, so Bases become candidates,
not a new geometry. Own Base: a Defend candidate under the existing `defend`/`threat` machinery,
with the `UNKNOWN_THREAT` floor applying to it as to any held ground — rear security at the Base
falls out of the same rule that bought WEST-4. Enemy Base: an Assault candidate, which needs one
**new value term**, because every existing capture term prices income and a Base pays none — its
value is ending the Campaign. That term's weight is a playtest-tuned placeholder flagged for feel
sign-off in the implementing issue, the same pattern #16 used for the set ADR-0014 then
discharged; the existing eight weights and ADR-0014's four calls do not move here.

**Rejected.** *(a) Bases as Objective-like manifest entries* — hands them owner-by-presence and
income, puts them in the Domination count, and dissolves the loss condition into the capture
rule; the two concepts genuinely differ (a Base is destroyed, an Objective changes hands), and a
schema that merges them makes the difference a flag to forget. *(b) Overloading
Capture(enemy Base)* — a verb whose meaning flips on the ground it names: "ownership by presence"
would be false at exactly one Place, the port could not type the refusal matrix above, and the
trace line "capture west_base" would be a lie about what the Squad was sent to do. *(c)
Decapitation stays player-only emergent for the MVP* — leaves a human Commander missing a whole
victory path through the only order path there is, and an AI that can neither pursue nor defend
its own loss condition; fails the North Star's Commander clause and its competent-opponent clause
at once. *(d) A scored victory* — a third currency, new UI, and a reopening of a win-condition
decision the MVP already took; post-MVP material at most, and not scoped in by this ADR. *(e)
Keeping the wire field named `objective` while it carries Base ids* — the rename costs one
mechanical pass now; the drift costs the Phase-2 snapshot schema forever.

**MVP scope.** Everything above sits inside `docs/mvp-scope.md`'s decided lines: Decapitation,
the AI Commander on both sides, Contacts aggregated per Objective *or Base*, and Base HQ status
public are all already in. Nothing is added. The means of HQ destruction and the HQ's durability
are playtest-tuned placeholders in exactly the sense the economy numbers are — the structure
(Assault order → Squad closes → HQ can die → deterministic telemetry) is the contract.

**What would overturn each decision.** *Order-names-a-Place*: a third kind of addressable ground
that will not fit the Objective-or-Base pair — none exists in the MVP, and construction is
post-MVP; if one arrives, Place is the term to widen or replace, deliberately. *Assault as its
own kind*: play showing the Capture/Assault distinction never refuses anything real and the two
verbs converge — then fold them, with the term system's eyes open. *Preferring the anticlimax*:
playtests where campaigns routinely end by a base rush before a front ever forms — the first fix
is HQ durability and Base-defence tuning, and if that fails, the decision to write is a gate on
Decapitation (say, holding n Objectives arms it), not the removal of Assault. *One new scorer
term*: if a single term cannot make the AI attempt Decapitation when it should and refrain when
it should not, the escalation is a threat-model ticket for purchase and assault together (the
ticket ADR-0014 already anticipates), not a retune of the standing weights.

Approved for `CONTEXT.md` alongside this ADR: **Place** (new), **Assault** (new), **Order**
(reworded to name a Place), **Base** (addressability noted). **Objective** and ownership by
presence are unchanged.
