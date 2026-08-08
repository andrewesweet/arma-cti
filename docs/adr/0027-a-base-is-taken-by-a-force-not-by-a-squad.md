# A Base is taken by a force, not by a Squad: the Commander's threat model is a mass, not a weight

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: gameplay balance/feel sign-off on how an AI Commander reasons about force — the threat model ADR-0014 anticipated and ADR-0020 named as this escalation (#38)
Reviewed-by-human: 2026-08-02

ADR-0020 wrote down the condition under which this ADR would have to exist: *"if a single
term cannot make the AI attempt Decapitation when it should and refrain when it should not, the
escalation is a threat-model ticket for purchase and assault together (the ticket ADR-0014 already
anticipates), not a retune of the standing weights."* #34 shipped the single term, #35 met the
condition in-world — eight men dropped onto three EAST Squads standing on their own Base, five dead
in twenty-five seconds, the HQ untouched — and #38 is the escalation. **Nothing in ADR-0014's eight
weights moves here, and neither does `decapitation = 8.0`.** They are asserted field by field in
`test_adr_0014s_weight_set_is_the_one_this_ticket_found`.

## The Commander now judges how much force a Place needs, and only a Base needs any

**`ASSAULT_MASS` is a doctrine table from a Contact's echelon band to a number of our own Squads**
— `team: 1, squad: 2, platoon: 3, company: 4` — and it is the whole threat model. An Assault on a
Base brings that many Squads or it does not go.

**A band in, a number of our Squads out.** Nothing in between reconstructs the enemy. #28's
structural guarantee is that a Contact carries no count and none can be recovered, and a rule that
divided observed men by eight would be inventing exactly the number the fog exists to withhold —
and inventing it from a band that is already, by design, an under-count of what is there. Nine men
and twenty-four men are one band and get one answer, which is that guarantee holding rather than a
coincidence (`test_the_force_an_assault_brings_is_read_off_the_band_and_off_nothing_else`).

**It is deliberately not `ECHELON_THREAT`, and deliberately not a weight.** `ECHELON_THREAT` is a
price, in teams, paid through the `threat` weight and discounted by age. This is a size. A term
that made a defended Base merely *expensive* would still send the one Squad that could most afford
the trip — which is precisely the Squad that dies there, and precisely what #35 measured. One term
could not carry both, which is the thing ADR-0020 said would trigger this document.

## Massing is a detail, not a bid

The scorer decides everything else by Squads bidding for Places, one Squad each. A bid is the wrong
shape for concentration: a Squad garrisoning quiet ground would rather stay there than march four
kilometres at a company, so every Squad but the keenest bids the Assault down and what arrives is
one. So the Assault is decided once, at the Commander's level, and the force is then **detailed** to
it:

- **Stage one, the ordinary bid**, answers one question only — *is this Assault worth doing at all?*
  If no Squad ranked the Base first, nothing is sought, and #34's arc is untouched: the raid still
  arrives late, deferred by the 4.7 km between the Bases and not by any rule.
- **Stage two tops that Squad up** to the mass its Contact demands, cheapest trip first, from Squads
  that would rather be elsewhere. The Squad the bid chose is kept rather than recomputed, so an
  Assault that wants one Squad details exactly the Squad it always did — **an undefended Base plans
  identically to #34**, on all 200 seeds.
- **All-or-nothing.** A Base that cannot be given its mass is one no Squad walks onto: the Assault
  is called off, the Base is barred, and the assignment runs again so the Squads it freed go back to
  the ground they were second-best at. The fallback for an unassigned Squad respects the bar too —
  declining an Assault and then letting the loneliest Squad on the map wander onto it would be the
  bug with extra steps.

Concentration costs the advance, not the island: `Campaign._advance` keeps ground once taken, so
four Squads leaving four Objectives to raid do not hand them back. That is what makes this
affordable at all, and it is a consequence of ADR-0014's fourth call rather than a new rule.

## Age discounts what a Base costs and never what taking it needs

#28 left a note for the scorer: *"A Contact can be minutes old, and its age is the only signal of
that — worth weighting."* It is weighted, in one direction only. A ten-minute-old company may well
have marched off, so it stops **deterring** the Assault: `_threat` decays it to the fog floor
exactly as it does for any stale Contact, and the price falls. It does not stop the Assault
**bringing** four Squads.

The asymmetry is deliberate because the two mistakes are not the same size. Four Squads at a Base
that emptied is a wasted march. One Squad at a company that never left is #35 again, and #35 is
where the men die. Only somebody looking lowers the Contact-band-derived demand — and looking
clears the Contact outright, because observed absence is the whole removal rule from #28. That is
the honest way to learn that the reported force is absent. It does not lower total demand below
force already committed: #181 floors demand at the Squads already standing under the Assault until
one of its defined release conditions ends that commitment. The picture may therefore raise what
an Assault brings, or lower its band-derived target, but it never sheds force the Commander has
committed.

## The numbers, measured, and flagged for sign-off

`ASSAULT_MASS` is a **playtest-tuned placeholder and wants gameplay-feel sign-off**, the #16 →
ADR-0014 pattern that #34 used for `decapitation`. Measured on Stratis, from a held island with the
force of eight the map's buy ceiling allows, a fresh company reported at Kamino, 200 seeds:

- **Above eight** the mass can never be assembled — the buy ceiling is one Squad per Objective, so
  eight is the whole force a map of eight Objectives fields. At nine the raid is never sent on any
  of 200 seeds, and one company sighting becomes a permanent veto on a win condition.
- **At eight** the raid takes everything: zero Objectives garrisoned on all 200 seeds. The Commander
  buys Decapitation by abandoning Domination, which is not a choice it should be making silently.
- **At four**, half the force raids and half still garrisons — four and four, on all 200 seeds. One
  more and the garrison is a minority of the island.
- **Below four** the mass arrives at or under parity with the band's floor: three Squads is
  twenty-four men against the twenty-five-plus that banded as a company. That is #35's eight
  into twenty-four at a larger scale. **This end is an extrapolation from #35's in-world
  measurement, not a measurement of its own** — the in-world run on #38 tests the four, not the
  three.

The thinnest margin, and the honest thing to look at before signing off: **the gate is 1.14.** In
that same position the keenest Squad's Assault beats its next option by 4.64 with nothing reported
and by only **1.14** with a company reported (thinnest over 200 seeds, at seed 86) — the company's
four points of `threat` eat three and a half of it. If a heavier band existed the Assault would be
priced out of the bid entirely and the threat model would never fire, because there would be nothing
to top up. Company is the top band on this scale, so 1.14 is the floor; a future band, a heavier
`threat`, or a longer island would all reach it.

## Rejected

**(a) Declining Assault outright against platoon or heavier.** One of the three options #38 named.
It puts a ceiling on the Commander's ambition that no amount of force can lift: a side with the
whole island and eight Squads would still refuse a Base a platoon was sitting on, and the only
counter a player would need is to leave nine men at home forever. Mass-or-decline subsumes it and
keeps the refusal about *what the Commander has* rather than about *what the enemy is*.

**(b) A `mass` weight instead of a mass rule.** Score the Assault down by the force it would need
and let the bid sort it out. This is the thing that does not work and the reason there is an ADR: a
weight changes *whether* the Squad goes, never *how many* go, so its best case is the Commander
declining and its worst case is #35 unchanged. Assignment is where the answer lives.

**(c) Deriving the mass from the observed count rather than the band.** Arithmetically tidier and
it breaks #28's structural guarantee — the planner would hold a number no Commander is allowed to
have, and the fact that it came in as a band would be one refactor away from not mattering.

**(d) Letting age decay the demand as it decays the price.** Symmetrical, and it converts the
threat model into a five-minute delay: the Commander would wait out `stale_seconds` and then send
one Squad at a company it had seen with its own eyes. It was reached for as a fix to a deadlock
that turned out not to exist — with the detail rule above, a force of eight always masses, so the
demand never traps the Campaign. The deadlock is real only for a Commander down to three Squads,
and a Commander down to three Squads declining a defended Base is the correct answer, not a bug.

**(e) Resourcing the raid by purchase.** #34 left this open and it stays open: the Commander still
buys the cheapest Squad and still stops at one per Objective, so it does not buy a Squad *for* the
raid — it details the ones it has. Purchase is the other half of the threat model ADR-0014
anticipated and wants its own ticket, with its own evidence about what firepower returns.

**(f) Reading posture and assets as well as echelon.** A Contact carries both (#28), and neither
means anything until Phase 4 adds vehicles: `posture` is `foot` or `motorised` and `assets` is `AT`
or `MG`. Weighing an unexercisable field would be tuning against a value that cannot vary.

## What would overturn each decision

**The doctrine table**: a playtest where the massed raid loses anyway — then the table rises, and
the ceiling above says it can rise to eight before Decapitation becomes unreachable. Or one where
the Commander strips the island so often that Domination stops happening — then it falls, and the
floor is #35's parity.

**Mass as an assignment rule**: a second thing that wants sizing rather than pricing — purchase is
the candidate — arriving with a shape this rule cannot take. Then the escalation is a force-planning
layer rather than a table, and ADR-0004 already names HTN as where that goes.

**Age one way only**: evidence that the Commander is repeatedly massing against Bases that emptied
long ago — the wasted-march failure this deliberately accepts. The fix would be a *recce* Order that
makes looking something a Commander can decide to do, not a decay curve on the demand.

**All-or-nothing**: play showing a partial Assault is worth sending — it is not, under the MVP's
rules, because a Base is destroyed rather than held and half a mass buys no half-outcome.

No `CONTEXT.md` term changes. `ASSAULT_MASS` is machinery, not vocabulary: what it operates on
(Contact, echelon, Assault, Base, Place, Squad) is all already there and unchanged.
