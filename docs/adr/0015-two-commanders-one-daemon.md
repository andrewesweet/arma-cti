# Two Commanders in one daemon: a planner apiece, a fixed turn order, a pair of seeds

Delegated-decision: yes
Date: 2026-07-31
Stood-in-for: gameplay balance/feel sign-off, and the ADR-level choices #17 forced ("both sides AI-commanded, unattended")

#17 puts both sides under an AI Commander in one daemon. Four things had to be decided that one
side never asked, and none of them is reversible cheaply once a Campaign replay depends on it.

**One planner instance per side, held in a map keyed by side.** A planner holds its seed and the
authored data it derived its distances from; one object asked twice would be one character playing
both sides, and would be the shape in which a Commander could carry state out of the other side's
turn into its own. A side may be put under a Commander once — a second is refused rather than
replacing the first, because two brains on one side are two answers to what that side is doing and
both spend the same Funds.

**Isolation stays structural rather than checked.** Each Commander is handed
`Campaign.observation(side)` and there is no other input: that call is the only way to obtain an
Observation, it never assembles one carrying both sides (#27, ADR-0012), and the ledger is keyed by
side. So "neither planner reads or spends the other's state" is a property of what exists, not of a
guard somebody has to remember. The tests ask it the loud way — one side spending every cycle
against one that spends nothing — because a structural claim still wants a witness.

**Commanders play in `commands.SIDES` order, not registration order.** Both plan inside one report
cycle, so *when* each plays is a detail nobody chose, and left to registration order a Campaign
would replay differently depending on how a session brought its sides up. Nothing one Commander
does inside a cycle is visible to the other in any case — a Command moves that side's own Funds,
roster and Orders, and ownership only moves in `observe` — so a fixed sequential order is the same
Campaign as planning them simultaneously, and cheaper to reason about than a promise of it.

**A Campaign's identity is the *pair* of seeds.** `--ai WEST:1 --ai EAST:4` names both sides and
both seeds in one flag apiece, rather than a list of sides against a parallel list of seeds. The
seed belongs to the Commander that plays it; Phase 2 snapshots both, and a resumed two-sided
Campaign keeps both characters.

**Both sides run the same scorer under the same weights, differing only by seed.** This is the
gameplay-feel call. Asymmetric weights would be the obvious lever for "make EAST harder", and it is
rejected for the MVP for the same reason ADR-0012 rejects perfect information: if the two sides
play by different numbers, an unattended run stops being an experiment about whether the scorer is
any good and becomes one about which weight set won. Difficulty is a later, deliberate ticket with
a name; ADR-0014's weight set stands for both sides until then.

## Consequences

- Attribution is recorded at the port for accepted Commands as well as refused ones
  (`command_issued` beside `plan_refused`, both carrying the issuing Commander *and* the side the
  Command named, which is exactly the pair `wrong_side` exists to distinguish). Telemetry only, so
  ADR-0003 is untouched: a log nobody can write changes no Campaign.
- Two decision traces share one log and stay separable by the `side` column every Commander-caused
  row carries. Wire-issued requests carry it too, so a human Commander's Command is attributable in
  the same column an AI's is and #19 has one attribution to audit rather than two.
- The desync load generator is now opt-in (`CTI_DESYNC_LOAD=1`). It spawns thirty-two WEST soldiers
  standing on four Objectives to give a joining client traffic, and capture is by presence — with a
  headless client now brought up *on purpose* for this ticket's topology, it would hand WEST half
  the island on every run. #8's investigation asks for it explicitly; a Campaign never does.
- The push path's budget at two sides is measured rather than assumed, and recorded by the run
  itself: `tools/push_path_report.py` turns a run's telemetry into `results.env` numbers, and
  `spike/probes/two-commanders.sqf` fails the run if a single drain ever reaches the engine's
  hundred-per-frame ceiling. See `docs/spikes/0002-two-commanders.md` for what the first
  unattended run measured.
