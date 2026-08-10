# A player squad leader leads a roster Squad that begins as an unassigned shell

Delegated-decision: no
Date: 2026-08-10
Reviewed-by-human: 2026-08-08 — every decision below is a ruling the human took
in session on #25 during the guided human-input review; nine ruling comments,
quoted by number throughout. The ruling date is the sign-off for the
CONTEXT.md term changes that land in this commit.
Claimed: after `git fetch origin` (origin/main at `dc8fe54`, topping at ADR-0069)
and a scan of every open issue's body and comments for an ADR number at or above
0070, which returned nothing.

## Why this is a decision record and not a feature

#14 gives every Order a task through `BIS_fnc_taskCreate` with the group as
owner, so it reaches whoever is in that group. Its one unverifiable acceptance
criterion — "a player-led Squad receives and displays its Order; compliance is
voluntary" — is unverified because the Phase-1 mission is thin per ADR-0007: two
Commander slots and the named `HeadlessClient_F`, so every bought Squad is
all-AI and the task displays to nobody. The mechanism is not missing; the player
is.

#25 was raised to put the player there. Its body named three undecided
questions; the human's review of 2026-08-08 answered those and, in answering
them, opened the economy, the Command Port, the planner, the mission and the
snapshot. The closing ruling directs #25 to close with no production code, an
ADR, and implementation issues in dependency order. This is that ADR.

## The decision

Nine rulings, recorded as the eight behaviours they bind, in the human's own
terms.

1. **Choosing squad leader creates a dedicated Campaign-roster Squad at own
   Base, with the player as its sole member, active and composition-unassigned**
   (ruling: player Squad origin, option B). It is an ordinary roster Squad — it
   receives standing Orders, stays in presence sampling, is snapshot-persisted —
   and it is neither an out-of-roster avatar nor a takeover of whichever AI Squad
   happens to exist. The role is therefore available at Play Session bring-up
   rather than waiting on an AI Commander's Purchase.

   The rejected alternative was a takeover of an existing bought Squad, which
   makes the role's availability depend on the AI Commander's spending and gives
   a joining player a Squad already carrying somebody else's Order in the middle
   of somebody else's ground.

2. **The AI Commander's composition-demand decision prefers an eligible shell to
   a net-new Purchase** (ruling: player Squad economy). When the Commander
   decides a new Squad composition is needed, it first looks for an active,
   composition-unassigned, player-led Squad of its own side at own Base. If one
   is available it fills that Squad; otherwise it Purchases. The strategic
   decision of *when* a composition is needed is unchanged — it is the same
   decision a Purchase is.

3. **The first fill assigns a composition exactly once, at ordinary Reinforce
   pricing** (rulings: composition lifecycle option A, initial fill price option
   A). The shell is assigned the demanded catalogue composition once and filled;
   from then on its composition is fixed and persisted like any other Squad's,
   and later Reinforce restores that composition and never reclassifies it. The
   price is the missing fraction × the assigned composition's price × the
   existing Reinforce discount — for an eight-man composition whose player is
   already standing, 7/8, which `EconomyTable.reinforce_cost` already computes
   (`ceil(100 × 7/8 × 0.8) = 70` on today's placeholder rifle Squad).

   This is what makes the Commander's preference for a shell economically
   coherent as well as an allocation priority: preserving an active Squad is
   cheaper than a net-new Purchase, which is the direction the ruling wants.

4. **A squad leader may not choose his own Squad's initial composition** (ruling:
   Command for first composition fill, option A). The composition-carrying form
   of Reinforce is the Commander's alone. A squad-leader principal may Reinforce
   his own already-assigned Squad under ADR-0040 and nothing more. The ruling
   marks this a temporary ownership rule that a future non-Commander-level
   economy explicitly reopens.

5. **A filled player-led Squad survives disconnect** (ruling: disconnect of a
   filled Squad, option A). It stays active in the roster, keeps its standing
   Order, goes on contributing presence, and proceeds under the engine-selected
   AI leader. Disconnect neither dissolves the Squad nor makes it orderless.

6. **On reconnect the player rejoins the same Squad and leads it, at own Base**
   (ruling: reconnect leadership, option B). Immediately, and regardless of where
   the Squad's AI members currently are. The standing Order stays attached to the
   Squad. The ruling accepts the resulting formation disruption in exchange for
   immediate restoration of the chosen role.

7. **Disconnect before the first fill suspends the same shell** (ruling:
   disconnect before first fill, option A). While suspended it contributes no
   presence, is ineligible for AI composition assignment and for filling, and has
   spent no Funds. Reconnecting reactivates the same roster identity at own Base,
   still composition-unassigned. Suspension is a state of the *shell*: it is
   defined only for a composition-unassigned Squad, which is what keeps rulings 5
   and 7 from contradicting each other.

8. **Every living member of a player-led Squad contributes to Objective presence
   exactly like a member of an AI-led Squad** (ruling: capture presence, option
   A). Leadership and voluntary compliance do not alter the presence rule. A
   suspended unfilled shell contributes nothing because it has no live members in
   the world — an absence of bodies, not an exemption.

   Compliance stays voluntary throughout. The Order is displayed, never imposed:
   a Squad that obeys because a player is in it has failed #14's criterion rather
   than exceeded it.

## What the Command Port gains, stated rather than discovered in the wire

Ruling 8 of the closing comment requires the port's consequences to be recorded
explicitly. They are the following, and the first implementation must carry all
of them as one piece for the reason ADR-0040 gives about its own first
implementation: the first one freezes a reading into the wire and into the
exported SQF constructors.

**The payload is a second catalogue entry, not an optional argument.**
`commands.CATALOGUE` maps a Command name to the argument names it requires, and
`cti_fnc_command` refuses a payload short of them; the catalogue's own comment
makes the fixed argument list load-bearing — "a constructor with a fixed argument
list is a constructor SQF cannot build wrong". An optional `composition` on
`reinforce` would give one name two shapes and put the choice between them inside
a handler. So the composition-carrying form is its own entry with its own fixed
arguments — the Squad and the composition type — and the ordinary
`reinforce: ("squad",)` is untouched. It remains a *form of Reinforce* in
CONTEXT.md's vocabulary, which is what the ruling called it; the wire token is
the implementer's to name.

**The principal restriction falls out of `CommandPort._principal_refusal`
already.** A squad-leader caller is stamped with `acting_squad` and is refused
anything that is not the plain `reinforce`, so a second reinforce-shaped name is
refused to him without a new rule. That is a property to assert, not a mechanism
to build.

**The Judgements are three new typed refusals, and each exists because an
existing code would lie.** A shell reached by the *ordinary* Reinforce cannot be
priced — `Campaign.missing` answers 0 for a Squad whose type the table does not
sell, and `_refill_refusal` then types it `malformed_command`, which tells a
Commander the table is broken when it is not. An already-assigned Squad reached
by the *first-fill* form is the once-only rule being tested, and it is not
`already_held` (which means "at the strength it was bought at"). A suspended
shell is neither. Working names, the implementer's to fix: `composition_unassigned`,
`composition_assigned`, `squad_suspended`. `wrong_ground` already covers a shell
that is not at its own Base, and covers it correctly.

**The Effects are two, and the world cannot do without either.** A shell's
first fill must carry the composition type: `fn_effectApply`'s `squad_reinforced`
branch reads the type off `cti_squadType`, which the world set at spawn — and a
shell was never spawned by an effect, so it carries none. Widening
`squad_reinforced` to carry the type was weighed and rejected: the argument would
be meaningless on every other Reinforce and its arity change would break the
addon's declared-argument check for a fact only one caller needs. So the first
fill travels as its own Effect carrying `squad`, the composition type and the
size — the world learns the composition from the wire once and records it exactly
as a spawn does. And the shell's *formation* needs an Effect of its own: the
daemon mints Squad ids (`Roster.add`, for the resume determinism ADR-0003
requires), the world must know which group answers to the minted id or no Order
can reach the Squad, and the player's group already exists because the engine made
it for the slot. That effect creates nobody and spends nothing; it enrols.

**The inbound half rides the observe report, not the Command Port.** A player
occupying the squad-leader slot is not a Command: it moves no Funds and the rules
judge nothing. The precedent is exact — `loadouts` rides the report for those
words, and folding it writes Campaign state (`Campaign.dress`). The claim is by
player UID, for ADR-0025's reason: respawn hands the player a new unit and
reconnection a new machine id, and neither is a change of who is leading.

**The schema budget moves, and the direction is known.** `SquadView` gains
whatever represents an unassigned composition, and `budget.squad_ceiling` measures
the worst-case Observation against the engine's return cap; the ceiling is
measured rather than authored, so it re-measures for free. A shell is a roster
Squad, so it counts against both ceilings the planner reads in `_fresh_barred` —
the map's one-Squad-per-Objective cap (8 on Stratis) and the wire's force limit
(71). On Stratis that means a side fielding a player shell may buy seven fresh
Squads rather than eight. This is a consequence of ruling 1, not a new decision,
and it is recorded so it is not rediscovered as a bug.

**Compatibility.** ADR-0012's "one wire format for human and AI" is unmoved: both
new Effects and the new Command travel the one schema source and are exported to
SQF by the one generator. ADR-0040's second principal is unmoved and gains its
first stated boundary — the composition-carrying form is outside it. ADR-0025 is
unmoved: a squad leader is not a Commander, and the slot-occupancy latch this
reuses is the same fact-about-the-server's-state argument, applied to a second
slot family. ADR-0052's death timer is unmoved. ADR-0008's persistent set grows
by the shell's two states and its owning UID, which `snapshot.py` already names
as #25's to settle and already promises to take as an additive migration rather
than a redesign.

## Two things the world will get wrong quietly, found before they were built

Recorded here rather than left for an implementer to meet in an Arma run,
because both are the shape where a plausible implementation passes every unit
test and fails in the world.

**A player-led group is not local to the server, and one command on the Order
path is `arg= local`.** #189's 120-second in-world diagnostic measured it: the
moment a group is player-led it leaves the server (`group_local=false`) and does
not come back, and `fn_effectApply`'s Reinforce branch already works around it by
staging replacements into a group of its own and `joinSilent`-ing them across.
`fn_orderApply` runs on the server and is not so careful. Against the vendored
wiki: `addWaypoint` and `deleteWaypoint` are `arg= global, eff= global` and reach
a client-local group fine; `BIS_fnc_taskCreate` is `arg= global, eff= global` and
accepts a Group as owner, so the display half of #14's criterion is sound. But
`setCurrentWaypoint` is **`arg= local`**, and `fn_orderApply`'s last act before
recording the Order is `_group setCurrentWaypoint _first`. Today no Squad is
player-led and the call always lands; the day the slot ships, an Order to a
player-led Squad may record and display correctly while never becoming the
group's current waypoint. The waypoint-property setters (`setWaypointType`,
`setWaypointBehaviour`, `setWaypointCombatMode`, `setWaypointSpeed`,
`setWaypointCompletionRadius`, `waypointAttachObject`) declare no locality on
their vendored pages at all, which is not a claim that they are global — it is an
absence, and the corpus is what settles it.

**`Roster.reconcile` deletes a Squad the world stops reporting, and the world
stops reporting a one-man Squad whose one man is dead.** `fn_squadSample` counts
`{alive _x} count units _group` and omits a Squad at zero; `reconcile` then
removes any `fielded` Squad the report does not name. A filled Squad has AI
members and survives. A shell does not: its player dying — a certainty, and
ADR-0052 makes it a 30-second certainty — empties the Squad's living count while
the corpse is still in the seat (#189 measured that too: no AI is promoted and
the dead player holds `leader` for the whole window). A suspended shell has no
living members by definition and meets the same rule. Either way the Squad is
silently deleted from the roster, which is precisely the first acceptance
criterion's failure — a player-led Squad dropping out of the Campaign — arriving
through a rule that was right for every Squad that existed when it was written.

## Rejected alternatives

- **A player-led Squad outside the roster.** It is the cheap version of ruling 1
  and it fails ruling 8 immediately: presence is sampled from bodies in a radius,
  and a Squad the roster does not hold is a Squad the Observation does not carry,
  the snapshot does not persist and no Order can name. The MVP puts the player as
  Commander *or squad leader*, both first-class (`docs/mvp-scope.md`).
- **A full starting Squad bought for the player at bring-up.** Superseded by the
  human's own custom direction: before a non-Commander-level economy exists, the
  side does not pay upfront for a full starting Squad, and the Commander's
  ordinary composition demand is what fills it.
- **Letting the squad leader pick his Squad's composition.** Ruled out in
  ruling 4 and deferred to a future economy, so the first fill is a Commander
  Command and the leader's port access stays exactly ADR-0040's.
- **Composition mutable after depletion.** Rejected in the composition-lifecycle
  ruling: it would make Reinforce a composition change rather than a refill, and
  Reinforce's whole definition in CONTEXT.md is refill.
- **Dissolving the Squad on disconnect.** Rejected in ruling 5 for a filled
  Squad; for an unfilled shell the ruling chose suspension over dissolution so
  the same roster identity — and its minted id — comes back with the player.

## Consequences

- CONTEXT.md's **Squad**, **Reinforce**, **Command** and **Observation** entries
  are amended in this commit, under the 2026-08-08 ruling as their sign-off. No
  new top-level term is minted: an unassigned shell and a suspended shell are
  states of a Squad, and giving each its own entry would put two nouns in the
  language for one thing.
- No production code lands here. The work is filed as implementation issues in
  dependency order and named in #25's closing comment.
- The snapshot moves to version 2 through an additive migration whose safe
  default is "composition-assigned, active, unowned", which is what every Squad
  written before this decision was.
- `docs/mvp-scope.md` is unchanged: it already puts the player as Commander or
  squad leader, and nothing here widens it.
- #189's open half is untouched. Its ruling — the player keeps leadership through
  death and leads again on respawn, with no succession or reclaim mechanism — is
  the behaviour rulings 5 and 6 are built on top of, and this ADR neither restates
  nor amends it.

## What would overturn this

- **Ruling 2's preference proving unstateable in the planner's own terms.** The
  choice lives in `UtilityPlanner._spend`, deliberately outside `CONSIDERATIONS`,
  because that tuple's fixed count is what the compensation factor's
  rank-preservation proof rests on (ADR-0031). A shell preference that could only
  be expressed as a ninth consideration would be a reason to reopen where the
  choice lives, exactly as #150's ruling said its own Reinforce/Purchase choice
  would migrate into a spending-consideration framework if #136 grows one.
- **The one-Squad-per-Objective cap biting.** If a side fielding a shell it
  cannot get filled is measurably worse off than one that never took the role,
  the shell counting against the map's cap becomes a balance decision rather than
  a consequence, and it goes back to the human.
- **The Order path proving unreachable for a client-local group.** If the corpus
  finds that an Order cannot be made to take effect on a player-led Squad without
  a client-side call, the CfgRemoteExec whitelist is one function long by
  ADR-0025's own acceptance criterion, and widening it is a decision this ADR has
  not taken.
- **A non-Commander-level economy.** The human's ruling names this explicitly as
  what reopens the temporary ownership rule in ruling 4, and with it the question
  of who chooses a Squad's composition.
- **Suspension proving observable as a Squad vanishing.** If a player disconnects
  before the first fill and the shell's suspension is visible to the other side —
  through presence, through a Contact, through anything — then "contributes
  nothing" is doing more work than the ruling asked of it, and the mechanism
  rather than the ruling is what is wrong.
