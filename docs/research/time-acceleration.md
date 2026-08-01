# Time acceleration for in-world tests

**Recommendation: do not build an accelerated tier.** Multiplayer has no simulation-acceleration lever at all, single player has one that works, and the price of reaching it — the human's GPU machine, a second topology, and a measured loss of simulation fidelity — is more than the sixteen minutes a full regression pass currently costs. One case is deliberately left open at the end: rules with long `time`-based clocks, which have no probe today and no other way to get one.

Issue #40. Measured 2026-08-01 against Arma 3 **2.20.152984**, the same build on both sides. Exploration scaffolding — the probe and the single-player runner — is on the `explore/40-time-acceleration` branch and not on `main`; this document is the result, and the branch is how to re-run it.

## 1. Multiplayer: there is no lever

The wiki is right, and it is right for our topology rather than only for a server full of humans.

> `|mp= Command is disabled in multiplayer.`
> — `docs/reference/arma-wiki/commands/setAccTime.wiki`, revision 338949

The sentence has been on that page since Operation Flashpoint and says nothing about *why*, so the fairness reading — that the restriction protects human clients from each other and might not apply to a server whose only clients are scripts — was worth an hour of the engine's time rather than an assumption. It is wrong. On the tier's own dedicated server (Linux, port 2402, **no client connected at all**, which is the most permissive case there is):

| measurement | before | after `setAccTime 4` |
|---|---|---|
| `accTime` reads back | 1 | **1** |
| `time` per real second | 1.000 | 0.99993 (ratio **1.00**) |
| a rifleman's ground, m per real second | 3.823 | 4.179 (ratio 1.09 — noise) |

The command is not refused, it is ignored: `accTime` never leaves 1. `isMultiplayer` is true on a dedicated server regardless of who is connected, and that is what the restriction keys off. Adding a headless client cannot make it more permissive than an empty server already was.

The same run reconfirms #35's reading of `setTimeMultiplier` in the world rather than on the page:

| measurement | at multiplier 1 | at multiplier 60 |
|---|---|---|
| `dayTime`, in-game hours per real second | 0.000278 | 0.016667 (ratio **60.0**) |
| `time` per real second | 1.000 | **1.000** |

`setTimeMultiplier` moves the sky. Every rule we write — Domination's 600 sustained seconds, contact decay's 120, the 90-second demolition — is written in `time`, and `time` does not move with it. Bohemia's own missions use it the same way: `paramTimeAcceleration` in End Game and Warlords is documented as "Sets a time multiplier for in-game time. See `setTimeMultiplier`" (`topics/Mission_Parameters.wiki`), a day-length control, not a test lever. Nothing in `topics/Multiplayer_Server_Commands.wiki` offers anything else; the server's only time-shaped commands are `#maxping` and `#dctimeout`.

Evidence: `~/.arma-cti/runs/20260801T070726Z-time-acceleration`, verdict PASS in 165 s.

## 2. Single player: the lever works, and so does everything else

The route is `-autotest`, documented in `topics/Arma_3_Startup_Parameters.wiki`: the client loads a named list of missions unattended, in "special mode", and returns an errorlevel. Pointed at `missions/cti.Stratis` in the real Windows client, with the cross-compiled `.dll` in the game root and `@cti` loaded as a mod, the whole stack came up:

```
CTI|sp_topology shim=cti_shim isServer=true isMP=false hasInterface=true version=[..,220,152984,..]
CTI|world_built map=stratis world=Stratis objectives=8 bases=2
CTI|sp_daemon_reachable addr=127.0.0.1:9099
```

Four things that were open questions before this run:

- **`initServer.sqf` runs in single player**, because `isServer` is true, so the addon builds the world exactly as it does on the dedicated server — eight Objectives, two Bases, both HQs found.
- **The shim loads and answers.** `cti_fnc_shimName` resolves, and a full `observe` round trip returns a real Observation.
- **The daemon is reachable from the Windows client on `127.0.0.1`.** WSL2 mirrored-mode loopback carries the shim's TCP connection across the boundary. The VM's LAN address does *not* — `192.168.1.36:9099` times out with `os error 10060`. That is a fact the human-play path (#8) will want: the address to configure is loopback, and the LAN candidate `spike/run.sh` stages second is dead weight.
- **The Command Port works in one process.** `contacts` bought two Squads through the port, the effect pump applied them, and the probe passed.

And the lever itself:

| measurement | at `accTime` 1 | at `accTime` 4 |
|---|---|---|
| `accTime` reads back | 1 | **4** |
| `time` per real second | 0.973 | 3.483 (ratio **3.58**) |
| a rifleman's ground, m per real second | 3.739 | 11.940 (ratio **3.19**) |
| the same, m per *mission* second | 3.843 | 3.428 (**−10.8 %**) |

Evidence: `~/.arma-cti/runs/20260801T071950Z-sp-time-acceleration`, verdict PASS.

Read the last row before the others. A request for 4× buys 3.19× of real speed-up, because the client cannot render and simulate that fast — that part is only a disappointment. The row that matters is that the walking unit covers **11 % less ground per game-second** under acceleration than it does without it. Acceleration is not a fast-forward through the same game: the engine is taking longer simulation steps and losing something in each one, and that loss lands on exactly the subsystem an in-world probe exists to test. `setTimeMultiplier` was unaffected in the same run (`dayTime` ratio 59.98, `time` unchanged), which is the control: the sky clock is independent of both.

## 3. The comparison: `contacts` three ways

`contacts` is the fairest available subject — its claim is about the engine's own knowledge model acquiring men, which is precisely the sort of thing acceleration might quietly change.

| run | topology | acquisition, planted → acquired | of six planted, acquired | verdict |
|---|---|---|---|---|
| `20260801T042802Z-contacts` | MP 1× | 62 s | 5 | PASS |
| `20260801T072304Z-contacts` | MP 1× | 33 s | 2 | PASS |
| `20260801T072434Z-sp-contacts` | SP 1× | 33 s | 6 | PASS |
| `20260801T072621Z-sp-contacts` | SP 4× | **31 s** | 5 | PASS |

Two findings, and the second is the one that settles this.

**`contacts` has no oracle sharp enough to see the divergence.** Both MP runs are the same probe against the same world on the same day, and they disagree with each other by a factor of two on timing and by three men on the count. That is the probe's own header being honest — "acquisition is a natural process with a wide spread" — but it means the 11 % fidelity loss measured in §2 is a third of the run-to-run spread of the thing it would have to be measured against. All four runs pass; none of them can tell you whether the accelerated one measured the same game.

**Acceleration bought nothing: 33 s at 1×, 31 s at 4×.** A world running 3.19× faster finished the probe 6 % sooner. Every wait in the corpus is written in `diag_tickTime` — real seconds — not `time`, and `contacts` alone holds a `+20` settle, a `+30` hold and a `+15` re-aim cadence in wall clock. Those do not shrink by any factor at all; only a wait whose *condition* the accelerated world reaches sooner shrinks, and the fixed settles are most of the runtime. Exploiting acceleration means rewriting probes in `time`, and until that is done the ratio in §2 is a number about the world, not about the test.

## 4. Cost, honestly

An accelerated single-player run costs:

- **The human's GPU machine, exclusively, for the whole run.** The dedicated-server tier shares the box with a play session badly enough that a lock and a port split exist; the client route takes the machine outright — same GPU, same screen. It is not something to leave running while somebody wants to play.
- **About the same bring-up as multiplayer.** Launch to `mission_running` was 25 s (08:24:37 → 08:25:02) against the dedicated server's 17 s. No saving there.
- **A second topology to keep working.** `isMultiplayer` is false, there is no headless client, `CfgRemoteExec` is enforcing against nobody, and locality is trivially local. Everything the MP tier tests about the *distributed* world is untested here by construction — which means a green SP run is not a substitute for a green MP run, and a red one is an `oracle_disagreement` before anyone has looked at it.
- **A second runner.** `spike/sp-run.sh` on the exploration branch is ~200 lines and knows about Windows paths, `-autotest` config files, RPT discovery and interop binaries. It found two of its own bugs in an afternoon (`-autotest=` cannot take a path containing a space; `tasklist.exe` is not on an agent's `PATH`, which turned out to be a real hole in the MP tier too — #41).

Against that: the full corpus runs green in **sixteen minutes** (docs/regression-tier.md), and the per-issue gate is one full pass. The measured saving on the one probe tried was 6 %. Rewriting the corpus's waits in `time` would raise that, but the ceiling is the corpus's sixteen minutes, on a machine that costs more to borrow than the minutes are worth.

## 5. What to do

**Do not build it.** No probe class in the current corpus should run accelerated. The corpus is cheap, its waits are in wall clock anyway, and single player measures a different topology than the one we ship.

**The one case that stays open.** Domination has no probe, and docs/regression-tier.md records why: the rule asks for 600 seconds of sustained ownership, a probe would have been a coin toss at 471, and `setAccTime` was believed unavailable. It *is* available, in single player, at about 3.2× — which turns 600 s of rule into roughly 190 s of wall. That is the only case found where acceleration buys something patience cannot, because the alternative is not a slower test but no test. If that probe is ever wanted, this is the route, and these are its terms:

- It is a **single-probe exception**, not a tier. One probe, one long clock, run by hand or by a recipe that says so.
- **A disagreement with the MP tier is `oracle_disagreement`**, never `assertion_failed`. §2 measured an 11 % fidelity loss per game-second at 4×; anything the accelerated run claims about *rates* — how fast ground is taken, how fast a Base falls — is suspect before the code is. The class exists for "the capture layer is prime suspect", and an accelerated single-player client is a capture layer.
- **What it may assert is a rule firing, not a rate.** Domination's 600-second clock is arithmetic on `time`, and `time` accelerates cleanly (3.58× measured, against a requested 4×). That the rule fires at all, in the real world, with real Commanders contesting ground, is worth knowing. How long the contest took is not.
- It needs `time`-based waits in the probe, and the probe would be the first in the corpus written that way.

Nothing else in #40 survives to `main`. The MP answer is above, with its numbers; the scaffolding that produced it is on the branch.

## Sources

- `docs/reference/arma-wiki/commands/setAccTime.wiki` (rev 338949), `accTime.wiki`, `setTimeMultiplier.wiki` (rev 378416), `useAudioTimeForMoves.wiki`
- `docs/reference/arma-wiki/topics/Arma_3_Startup_Parameters.wiki` § autotest, § `-init`
- `docs/reference/arma-wiki/topics/Mission_Parameters.wiki` (`paramTimeAcceleration`), `topics/Multiplayer_Server_Commands.wiki`, `topics/Extensions.wiki`
- Runs: `~/.arma-cti/runs/20260801T070726Z-time-acceleration`, `20260801T071950Z-sp-time-acceleration`, `20260801T072304Z-contacts`, `20260801T042802Z-contacts`, `20260801T072434Z-sp-contacts`, `20260801T072621Z-sp-contacts`
