# The Commander multiplies considerations rather than summing weights

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: gameplay balance/feel sign-off on the AI Commander's scoring shape — the mechanism ADR-0014 fixed and #48's steal-list item S1 proposed replacing (#49)

Reviewed-by-human: pending

ADR-0014 fixed eight summed linear weights and four calls about what the Commander
values. #48 read the prior art and found that every serious utility system multiplies
normalised considerations through authored response curves instead — Lewis's Infinite
Axis Utility System (Game AI Pro 3 ch.13), read in full — and that the reason is exactly
our known limit: a sum lets `threat` make a Base expensive and never impossible, and
every axis added dilutes every axis already there. That is why ADR-0027 had to put a
table *beside* the scorer rather than a ninth weight in it.

**This ADR supersedes ADR-0014's mechanism and keeps every one of its calls.** The four
calls are asserted still holding in
`test_adr_0014s_calls_survive_the_curves_that_replaced_its_weights`, and ADR-0020's and
ADR-0027's measured behaviours are asserted on the same 200-seed sweeps they were
measured on. Nothing about the massing rule moves: ADR-0027 stands unamended.

## An option is a product of eight considerations, and a zero is a veto

Each candidate Order is normalised to [0, 1] on each of eight considerations, remapped by
an authored curve, and multiplied. `CONSIDERATIONS` carries them in evaluation order,
cheapest first, and the product early-outs on the first zero.

Lewis's three classes are the vocabulary, and naming them is half the point of the
change — his diagnosis is that a scorer whose axes are *all* balance/feel has nothing to
gate with, which is what #34's single stretched Assault term was.

| Consideration | Class | Curve |
|---|---|---|
| `legal` | mandatory | 1 or 0 — the port's refusal matrix (ADR-0020) |
| `worth` | distinguishing | the Place's value over the richest value on the map |
| `unfinished` | distinguishing | 1 contested, `unfinished_floor` otherwise |
| `momentum` | balance/feel | 1 under the standing Order, `1 - momentum` otherwise |
| `flavour` | balance/feel | `1 - flavour × seeded(place)` |
| `proximity` | distinguishing | `1 - km / reach_km`, Lewis's published linear |
| `hold` | distinguishing | `hold_floor + (1 - hold_floor) × (T/company)²` |
| `danger` | distinguishing | `1 - danger_bite × (T/company)²` |

The count is fixed. Every option carries every consideration, at 1.0 where its kind makes
one inapplicable, and that is load-bearing rather than tidy — see the compensation factor
below.

**The veto set is `legal`, and two boundaries nothing on Stratis reaches.** A `capture` on
ground the side holds, a `defend` on ground it does not, an `assault` on its own Base:
half the option space every cycle. This is the rule the old scorer obeyed silently by
generating one kind per Place; scoring it instead makes the mandatory class real, gives
the early-out something to do, and puts the claim where the never-rejected property run
through the real `CommandPort` tests it. `worth` reaches zero at a Place that pays
nothing and `proximity` at a march longer than `reach_km`; both are genuine vetoes and
neither is reachable on the authored map, where the graph diameter is about five
kilometres.

**Massing is not in the veto set, deliberately.** S1's proposal was that "a Place we
cannot mass for scores zero instead of being barred by a separate rule". ADR-0027 is the
answer to that and it has not changed: a veto still only decides *whether* a Squad goes
and never *how many*, so folding the mass in would give back exactly the property that
made #35's eight men walk into three Squads. The decline stays an assignment filter.

## ADR-0014's calls, in the units the curves are authored in

**`jitter < travel` stands, at the same three hundred metres.** `flavour` is the whole
span of the seeded preference and `reach_km` is what a kilometre costs, so
`flavour × reach_km` is the seed's reach in kilometres of march, and it is 0.3 — the
number ADR-0014 measured. The 2,065 m march chosen over the 1,076 m one by 0.22 of
flavour is still out of reach, by the same margin.

**`garrison` 0.1 against `income` 1.0 stands, as the `hold` curve's floor.** Quiet held
ground is worth a tenth of fresh ground to a Squad, which is what the weight meant and
what the floor now means. The curve is what the weight could not be: squared, so the fog
floor barely registers and the crossing point where a garrison outbids marching on sits
at about seven teams — between a platoon and a company, nearer the company.

**Cheapest-Squad purchase stands, untouched.** `_buy` is not scored and was not changed.

**The `UNKNOWN_THREAT`-driven garrison stands.** `_threat` is unchanged: unknown ground is
a team, watched-and-empty ground is nothing, and the difference now reads as
`hold(1.0) > hold(0.0)` rather than as a term. ADR-0014's WEST-4 is still bought and still
sent to stand on ground nobody is looking at.

## What a Base is worth to keep had to be said out loud

The one thing a product cannot do that a sum could: under ADR-0020 a Base was worth
`garrison × decapitation` — 0.8 — to stand on, and a company on it added a `defend × threat`
term of 8.0 that had nothing to do with the Base at all. Ten times the Place's own value
arrived through a threat term. Multiplying can only discount, so the value has to be
named: `homeland`, what keeping our own Base is worth, beside `decapitation`, what taking
the enemy's is worth.

This is an honesty improvement rather than a new lever — the number was always there,
smuggled — but it is a new authored value and it is **a playtest-tuned placeholder that
wants gameplay-feel sign-off**, the #16 → ADR-0014 pattern. Measured on Stratis over 200
seeds, where every Objective pays ten:

- **Below 9.087** a fresh company standing on our own Base no longer outbids marching on,
  and the Commander walks away from its HQ at the moment somebody came for it.
- **Above 27.959** a platoon is enough to stop the advance — the Commander that turns
  round for every sighting, which ADR-0014 rejected.
- **Ten sits near the low end rather than in the middle**, and the reason is a coupling
  worth recording: `worth` normalises by the richest value on the map, so while `homeland`
  is at or under the best Objective's income it raises the Base alone, and past that it
  becomes the ceiling and shrinks every other Place's `worth` to make room. Above ten it
  stops being a dial on the HQ and becomes a dial on everything else wearing the HQ's
  name. Ten is the last value where it means what it says.

**The one behaviour that changed in degree, reported rather than buried: the recall
radius grew from 160 m to 1.15 km.** Under the summed scorer a company at our own Base
beat marching on by 0.18 out of 8.8, so only a Squad standing at the Base itself turned
round; a Squad 200 m away did not. Under the curves the margin is 0.047–0.072 out of 0.72
over 200 seeds, and travel eats it at about 1.15 km. Both scorers turn a Squad round for
a company and neither does for a platoon — the relation ADR-0020 pinned — but the new one
will recall a Squad from the next Objective over. That is a defensible reading of "a
Commander that leaves its rear open is not a competent one" and it is not the reading
ADR-0020 measured, so it is called out here for the sign-off rather than left in a diff.

**Sign-off received:** the human approved both flagged placeholders — the 1.15 km recall
radius and `homeland = 10.0` — on 2026-08-01. The ADR's remaining decisions stay
`Reviewed-by-human: pending`; this note covers only the two gameplay-feel values.

## Lewis's compensation factor is applied, and proved unable to decide anything

Multiplying eight normalised considerations drives a good option to about 0.3, which is a
legibility problem in a trace whose whole job is to be argued with. The fix that
circulates is `final = s + (1 - s) × (1 - 1/N) × s`, and #48 could not trace it to a Mark
or Lewis primary — so it is adopted on its algebra and on nothing else.

The algebra: for a fixed `N` that map is strictly increasing on [0, 1], so it cannot
change which option wins, only how far apart the scores read.
`test_the_compensation_factor_cannot_change_which_option_wins` is the proof rather than
the claim. It stops being free the day the consideration set stops being fixed per
option, because two options compensated by different amounts would be reordered by the
transform; the count is fixed for exactly that reason, and changing it is a deliberate
act rather than a drift.

## Rejected

**(a) A `threat` curve that collapses to zero at a company.** #48's phrasing invites it
and it would be a veto with real teeth. It is the Commander that will not go near heavy
ground, which is the turtle ADR-0014's aggression retune was a human decision to stop
being. `danger_bite` is 0.4, so a company costs four tenths of a Place and never all of
it: heavy ground is attacked later than light ground rather than never.

**(b) Lewis's `runtime` curve for `momentum`.** `y = 1 - x⁶` decays a decision the longer
it has been running, and it is the published fix for exactly our anti-thrash term. It
needs the age of the standing Order and `SquadView` does not carry one; adding it is an
Observation change and the Observation is another ticket's surface. `momentum` is the
degenerate case of that curve — a flat step — and the field is where the curve goes.

**(c) A `cooldown` curve.** `y = x⁵` is near-zero until a delay elapses and then spikes,
and it wants the same clock `runtime` does. Same answer.

**(d) Keeping the summed scorer and adding curves to individual terms.** The half
measure: it keeps the dilution — every term added still divides the others' influence —
and it never gets a veto, because a sum of terms one of which is zero is not zero. The
whole argument for the change is that the zero has to propagate.

**(e) Rescaling scores back into income units so the trace reads as it used to.** It would
have kept `because: "0.9 ahead of capture camp_tempest"` looking familiar. A score is now
a compensated product in [0, 1] and pretending otherwise would make the trace lie about
its own arithmetic; the trace format change is recorded in #49 instead.

## What would overturn each decision

**Multiplicative scoring**: a behaviour that a sum expressed and a product cannot. The
one found here — a Base's value to hold arriving through a threat term — was solved by
naming the value, and a second one that cannot be named that way is the evidence. The
retreat is not back to a sum but to Dill's dual utility (rank plus weight, Game AI Pro 2
ch.3), which #48 read and which keeps the veto.

**The veto set**: a mandatory consideration that fires when it should not — a Commander
refusing an Order the port would in fact accept. The never-rejected property run is the
detector and it is green; a `wrong_ground` refusal appearing in it means `legal` and the
port have drifted apart, and the fix is in the scorer, never in the port.

**`homeland = 10.0`**: a playtest where the Commander pulls Squads off the line for
sightings at its HQ that come to nothing — then it falls, and the floor is 9.087, below
which it stops defending the HQ at all. Or one where the HQ is lost while a Squad one
Objective away marched on — then it rises, and the ceiling is where a platoon starts
stopping the advance.

**The compensation factor**: a consideration set that varies per option. The proof above
is conditional on the count being fixed and says so.

**The curve exponents (`hold_power`, `danger_power`, both 2.0)**: a playtest where the
Commander ignores a platoon it should have respected, or respects a squad it should have
ignored. They are the shape of "flat until a platoon", which is #48's reading of the
prior art and not a measured property of our world.

No `CONTEXT.md` term changes. Considerations, curves and vetoes are machinery; what they
operate on (Place, Order, Contact, echelon, Squad, Base, Objective) is all already there
and unchanged.
