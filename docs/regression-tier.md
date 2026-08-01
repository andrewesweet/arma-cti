# The Phase-1 in-game regression tier

`just regress` runs the whole in-world probe corpus against a fresh Phase-1 world per probe and returns one typed verdict per probe; `just regress <name>...` runs a subset. It is the thin early slice of the Phase-3 acceptance harness that issue #23 asks for, pulled forward under ADR-0016 rather than folded into #5. The orchestration is disposable — grown from `spike/run.sh`, replaced wholesale when ADR-0011's Python orchestrator arrives — but three things it establishes are durable and carry into Phase 3 unchanged: the probe corpus in `spike/probes/`, the machine-scoped lock that serialises the Arma tier, and the evidence-directory convention under `~/.arma-cti/runs/`.

Built 2026-08-01 on #23, to this design. Where the build departed from it, this document has been corrected and says so; the departures are recorded in ADR-0021. The implementation order at the end is kept as the record of how it was staged.

## What runs

The corpus is everything under `spike/probes/` — membership is by directory, so a harness file that asserts nothing (a playtest fixture such as `spike/playtest/session-hold.sqf`, which holds a world open for a human) must live outside it, or every `just regress` pays its window for no verdict. Load-bearing since brief 0001 (2026-08-01), which is when the first non-asserting fixture was written. The corpus includes **bareworld** — the Phase-1 world with nothing asserted of it but what the mission itself builds. Bareworld is not padding: it carries the properties that had no Phase-1 home at all, and that #23 lists first — the addon resolving by name on a dedicated server, the seeded PRNG against the real engine, the daemon echoing a request id back through `callExtension`, the manifest's world being the world that got built, and the effect pump and presence report actually turning. Three of those lived only in `spike.Stratis`, the Phase-0 measurement mission nothing runs per issue.

Bareworld is a probe file rather than the implicit "mission with no probe appended" this design first described, because a mission with nothing appended has no completion line worth waiting on: `CTI|done` fires before the loops it has just started have polled once, so waiting on it would have meant a sleep after it. See ADR-0021.

The rest of the corpus covers what exists: presence sampling for both sides (`contacts`), Contact survival across engine knowledge decay (`contact-decay`), the projection reply (`projection`), an AI-issued Order landing on real waypoints (`ai-commander`), both sides under Commanders at once (`two-commanders`), an Assault bringing an enemy Base's HQ down and a Defend garrisoning a side's own (`base-assault`), the addon parsing its own authored JSON (`json-manifest`), a Campaign actually ending — an unattended two-AI run won by Decapitation (`campaign-end`) — a Commander that finds a Base defended sending a force at it rather than a Squad (`massed-assault`), the leg between a real client and the Command Port (`client-port`), and the manifest guard refusing rather than half-building (`manifest-missing`, red by design).

`client-port` is the corpus's one probe that needs a **headed client**, and it says so in its own `env:` header (`CTI_WINDOWS_CLIENT=1 CTI_PROBE_CLIENT=240`) rather than asking the caller to remember. A headless client cannot stand in for the caller on that leg: `remoteExecutedOwner` returns 0 for a call arriving from an HC by engine design and an HC holds no player unit to carry a UID, so it is neither attributable nor assignable (ADR-0025). The run launches the client on the Windows host, `skipLobby` drops it into the first free playable role — the NATO Commander — and the probe waits for the assignment sweep to see it before driving anything. Two consequences worth knowing before running the corpus: the host guard's answer is load-bearing for the whole run, because a live play session makes this probe `infra_unavailable` and `infra_unavailable` abandons the remaining corpus; and this is the one probe whose evidence includes a file from the other side of the WSL2 boundary, the client's own RPT, copied into the evidence directory while the client is still up. The engine writes a refused `remoteExec` to the sender's log and nowhere else, so that copy is the only place a blocked call is observable at all.

`campaign-end` and `massed-assault` are the corpus's probes that engineer their **starting state**. `campaign-end` does it twice: it spawns a rifleman inside each Objective's capture radius, so the Campaign reaches the state in which a Commander plays for the enemy HQ, and it puts the assaulting Squad on its approach 250 m out, as `base-assault` does. `massed-assault` does the same two and adds a third, the garrison it spawns on the enemy Base once EAST's own Squads have marched out of it — `campaign-end` waits for that Base to be *empty*, and the point of this one is that it is not. The Assault is the Commander's own decision in both, waited for and refused if it never comes, and in `massed-assault` so is the size of it — the Contact is acquired by a real leader looking at real men, and the probe counts the Squads that came rather than asking for a number.

`massed-assault` takes one licence beyond position, and it is `contacts.sqf`'s: the garrison is told not to shoot and made unkillable. That is not a shortcut but the same rule `contacts.sqf` states — "the planted men may not fire back and may not die, because the head count is what the assertions are made of" — applied where the head count is the *band* the whole assertion rests on. It was earned rather than assumed. The probe was run seven times on 2026-08-01 while it was being written, and a fighting garrison produced, with staging unchanged: a mass that won (five of eight defenders down, the HQ 39% gone) and a mass that lost (all sixteen attackers dead, the garrison untouched), and then a run where the lone observing Squad was killed before the sampler's next tick, so no Contact formed and the *decision* could not be observed either. A probe gated on a firefight is a flake generator, and this tier does not average runs. So `massed-assault` asserts the decision — Contact acquired, band read, force detailed, Orders crossing the port — and leaves the fight to `base-assault` and `campaign-end`, both of which already assert it. The distinction is the one CLAUDE.md draws about windows, one level up: sizing a probe's setup to what is being measured is allowed, and arranging for the measurement to come out right is not.

Domination has no probe, and that is a finding rather than a gap. It was tried on 2026-08-01 with the same staged island: the ground went WEST at t=40 and EAST's Commander contested camp_rogain at t=511, 471 s into the 600 s the rule asks for. The Campaign was behaving correctly and the probe would have been a coin toss, so it is not in the corpus. Nothing could shorten the wait either — `setAccTime` is disabled in multiplayer and `setTimeMultiplier` moves the in-game clock rather than `time`, which is what the rules are written in. The Domination timer is unit-tested against simulated clocks, which is where a ten-minute rule belongs.

The one property on #23's list that had no probe — `CfgRemoteExec` mode=1 refusing a non-whitelisted call — is now `client-port`'s last step, where #23's design said it belonged: it is only a real observation when the caller is a real client, and the same probe already has one. The client calls `setVariable` on the server and `cti_fnc_portReply` on the server, having just proved through the gateway that its `remoteExec` works at all; neither lands, and the engine writes both refusals to the client's RPT in its own words (`Scripting function 'cti_fnc_portreply' is not allowed to be remotely executed`). The broken-manifest refusal, listed here as a second gap when this was written, is now `manifest-missing.sqf` — it asks the guard for a world with no manifest rather than staging a corrupted file, so it needed no runner staging hook. A *corrupted* manifest (present but unparseable) still would.

Each probe carries a machine-readable header block the runner parses — the same facts today's headers state in prose, made loadable:

```
// probe: contacts
// issues: 28
// window: 240
```

`window` is the probe's deadline in seconds, sized to its subject per the rule on the `probe` recipe; the header prose still states the reason. `issues` names what motivated it, which is what makes "run per issue" selectable later. No separate manifest file: the probe is the unit of ownership, and a manifest beside it is a second place to forget.

Three optional lines complete the block:

- `// env: CTI_AI_SIDE=WEST` — what the world must be brought up with for this probe to mean anything. The probe's requirement, not the caller's to remember; `just regress` still takes no environment variables of its own (ADR-0021).
- `// expect: <class>` — a red-by-design probe. The runner passes it exactly when the run fails with that class, and fails it when the class is wrong or when the probe passes. A probe with no `expect:` line expects `PASS`. Added 2026-08-01 under ADR-0019: `manifest-missing.sqf` landed after this design was written, and its green run is the bug.
- `// quarantined: #<issue>` — reports `flake_quarantine` and does not gate. Without an issue number the line does not parse, which is how "quarantine without an open issue is out of policy" is enforced.

`tests/unit/test_probe_headers.py` gates the whole corpus's headers in the no-Arma tier, so a malformed header costs a second rather than a bring-up. The runner re-validates the probes it was asked for before it touches a port.

## The command surface

`just regress [--wait <secs>] [--issues <n,...>] [--list] [name...]` — no arguments runs the full corpus; names (`contacts`, `contact-decay`, matched against the `probe:` header / filename) run a subset while iterating. Depends on `build-shim build-addon` exactly as `probe` does. No bespoke environment variables: everything `just probe` currently takes from the caller's five variables is either fixed (mission, config, prefix) or read from the probe header (window).

`--issues 28` selects every probe whose `issues:` header names 28; the header is a comma list and matching is on whole numbers, so `--issues 3` never selects the probe written for #32. The flag repeats and takes comma lists, and it unions with names rather than intersecting: `just regress contacts --issues 22` runs `contacts` plus everything #22 motivated, named probes first in the order given, the rest in corpus order, each once. **An `--issues` filter that matches no probe is an error (exit 2), not an empty green pass** — reported per number, so a spec whose three other numbers matched still refuses rather than quietly running the subset that hit. That is the one failure this surface exists to prevent: a tier that can be made to pass by narrowing it to nothing is worse than no tier.

`--list` is the whole selection path with nothing after it: it resolves the filters, validates the headers of what they chose, prints the selection to stdout one name per line with the declared-window budget on stderr, and stops. It takes no lock, opens no port and brings no world up — which is what lets `tests/unit/test_regress_selection.py` gate every selection rule in the no-Arma tier, and what lets an agent see what a filter chose before spending the wall on it.

The lock is acquired once for the whole run rather than per probe, so a queued agent takes the tier when the run finishes rather than racing for it between probes. Header validation happens before the lock: a corpus that does not parse costs seconds, not a place in the queue.

The runner is one loop over the selected corpus. Per probe: bring the world up fresh (daemon, server, staging — the existing `run.sh` machinery), append the probe to the generated harness, then **wait directly on the probe's `probe_done` line with the header window as the deadline**. This is the one behavioural difference from `just probe`, and it matters twice over: hold mode today spends the entire hold window waiting for a human client that a regression run never sends, so every probe run costs its full window even when the probe finished in forty seconds; and a regression tier has no business printing a direct-connect banner. `FAIL` ends the wait early and classifies as whatever class that `FAIL` line declared — `assertion_failed` only if it declared none. (The harness used to call every in-mission failure `assertion_failed`, including the ones the world had typed `timeout` or `oracle_disagreement`, which sent the reader to the wrong table row.) Fresh world per probe, not one world running the corpus serially: probes spawn units, march Squads and deliberately corrupt the picture, and the isolation is what lets a probe's header window stay sized to its own subject.

A failing probe fails the run and the command exits non-zero after finishing the remaining probes — report everything, filter later — with the per-probe verdicts summarised last, worst class first. The one exception is `infra_unavailable`, which abandons the remaining corpus: it is not a result, and carrying on past a stop produces more non-results. The exit code names the worst class; the mapping is in ADR-0021.

## Runtime budget

Windows are deadlines, not sleeps, so a passing probe ends when it logs `probe_done` and the run moves on. Measured on the first full green pass, 2026-08-01 (Arma 2.20.152984, eight probes, twelve minutes thirty-eight seconds end to end). `massed-assault` was added afterwards and is shown at its two consecutive green runs the same day:

| probe | window | measured |
|---|---|---|
| `bareworld` | 150 | 19 |
| `manifest-missing` | 150 | 13 |
| `json-manifest` | 150 | 34 |
| `projection` | 150 | 59 |
| `contacts` | 240 | 77 |
| `contact-decay` | 300 | 176 |
| `ai-commander` | 300 | 44 |
| `two-commanders` | 600 | 210 |
| `base-assault` | 480 | 174 |
| `campaign-end` | 750 | 372 |
| `casualties` | 150 | 59 |
| `human-commander` | 150 | 33 |
| `massed-assault` | 480 | 264, 291 |
| `client-port` | 420 | 66, 66, 66, 67 |

Re-measured on a single green full pass of the whole twelve-probe corpus, 2026-08-01, sha `bd9676d`: **21 minutes 10 seconds**, 1,270 s. `client-port` arrived after that pass and is measured on four green runs of its own, one of them inside a full pass of the corpus as it stood before `massed-assault` landed; the thirteen-probe total is therefore arithmetic — about 22 minutes — rather than a pass anybody has watched end to end. The same pass before #43 converted `ai-commander` from a 150 s settle to an event-driven wait would have been 1,405 s. Every figure includes that probe's own bring-up — daemon, server, staging, mission load — which is about 20 s of it. The corpus's declared windows total 59 minutes; it runs in 21, because no probe fills its window and the longest are sized for a subject (marching, decay, an HQ coming down) whose worst case they do not hit. A full pass is an "over coffee" cost, not an inner-loop one, and the cost-control section below is written to that number.

Summed across all fourteen rows as they stand — the twelve-probe pass at 1,270 s plus `massed-assault` at its first green 264 s and `client-port` at its 66 s — the corpus is **about 1,600 s, 26 m 40 s**. That figure is arithmetic over separately measured runs, not a pass anyone has watched end to end, and it is the number #36 was built against: within four minutes of the 30-minute trigger, close enough that the machinery was built before the trigger rather than during the issue it would first have delayed. A measured fourteen-probe pass is owed and will correct this row when the next full pass is run; #36's own change touches no in-world surface, so it did not buy one. (The probe's own header is authoritative for its window — CLAUDE.md says so — and the runner believes headers.)

## Waiting for the subject

Half of a full pass was a probe watching a clock. Audited on 2026-08-01 for #43: a **fixed settle** is a `waitUntil { diag_tickTime >= _next }` — a wait whose end is a number the author chose, not a condition the world reached. Against the pre-conversion pass of 1,405 s they total **705 s, 50%**. The measured column below is the 2026-08-01 full pass with `ai-commander` shown at its pre-conversion 179 s, so the shares are the ones the audit was made against.

| probe | measured | fixed settle | settle share | what the settle is for |
|---|---|---|---|---|
| `bareworld` | 19 | 0 | — | |
| `manifest-missing` | 13 | 0 | — | |
| `human-commander` | 33 | 20 | 61% | world built, report loop has cycled |
| `json-manifest` | 34 | 20 | 59% | same |
| `casualties` | 59 | 45 | 76% | 20 same; 5+5 units settling after `setPosATL`; 15 two report intervals for the buffer to drain |
| `projection` | 59 | 20 | 34% | same 20 |
| `contacts` | 77 | 50 | 65% | 20 same; 30 for knowledge to spread between two leaders |
| `base-assault` | 174 | 20 | 11% | same 20 |
| `contact-decay` | 176 | 160 | 91% | 20 same; 140 past the engine's 120 s knowledge decay |
| `ai-commander` | 179 → **44** | 150 → **0** | 84% → — | ground closed by a marching Squad — converted, below |
| `two-commanders` | 210 | 180 | 86% | ground closed per side, plus the drain extremum #17 asks to be measured |
| `campaign-end` | 372 | 40 | 11% | 20+20, that a won Campaign stops handing the world work |
| **total** | **1405 → 1270** | **705 → 555** | **50%** | |

`client-port` landed after this audit and is not in its arithmetic. It carries 35 s of fixed settle in a 66 s run: the same 20 s for the world, and 15 s of grace after the client's blocked calls. The second one is the corner the honesty rule names — the claim is that nothing arrived, and there is no condition to wait on for an absence, only a length of time nothing has happened for. Everything else in it waits on the thing it is about to assert: the assignment sweep seeing the client, and each judgement reaching the client that sent the Command.

### The honesty rule

**A probe may exit when its subject has finished, and never when the world looks done.** A settle may be replaced only by a wait on the condition the probe is about to assert, with the old settle kept as the deadline. Then a passing run ends sooner and a failing run fails at the same instant, in the same class, as before — which is the test that a conversion is honest. Exiting on a proxy ("two report cycles have gone by, so the row is probably there") is the flake factory the Contract forbids, and it is not made legal by being fast.

The rule has a corner the conversion of `ai-commander` had to answer. A claim that something is **absent** — a force with no ceiling, a Commander playing a side it should not — draws its strength from how long it was observed, so it cannot simply be re-read at an earlier exit. Two answers, in order of preference: evaluate the absence claim on every pass of the wait, so it fails the instant it is violated rather than only if the violation happened to survive to the end (strictly stronger over the same window, weaker only in that the window is shorter); or, where the claim's failure mode has a known cadence, keep an explicit floor derived from that cadence and say so in the probe's header. What is not allowed is dropping the dwell silently.

### Observable, pollable, or neither

`topics/Arma_3_Mission_Event_Handlers.wiki` is the authority on the first column. Its full event list is 50 entries and contains no waypoint, detection, knowledge, movement or distance event — the conditions our probes actually wait on are almost all in the second column.

| our condition | mechanism | wiki |
|---|---|---|
| a unit died | **event** — `addMissionEventHandler ["EntityKilled"]`, server-wide, no per-unit attachment | `topics/Arma_3_Mission_Event_Handlers.wiki`; #39's rejection table covers `Killed`, `UnitKilled`, `MPKilled`, `HandleDamage`, `Hit` |
| a Squad was spawned or deleted | **event** — `EntityCreated` / `EntityDeleted` (2.10 / 2.18), `GroupCreated` / `GroupDeleted` | same page. Note `EntityCreated`'s argument is the entity, not an array |
| a headless client joined | **event** — `PlayerConnected` / `OnUserClientStateChanged` | same page |
| a waypoint completed | **callback, not an event** — `setWaypointStatements`, whose completion statement runs on completion; `currentWaypoint` inside it is the index being completed | `commands/setWaypointStatements.wiki`. There is no `Waypoint` mission EH |
| a Squad closed ground on its ordered place | **pollable only** — `leader _g distance2D _pos`. No movement or distance event exists | absence from the MEH list above |
| the engine acquired or forgot a target | **pollable only** — `targetsQuery` / `knowsAbout`. No detection event exists, and #28 found `targetsQuery` never stops returning a memory, so the ageing bound is ours and the crossing is ours to read | `commands/targetsQuery.wiki`, `spike/probes/contact-decay.sqf` |
| the report loop has cycled / the outbox drained | **pollable only**, but against our own counters (`cti_effectDrain`, the presence report), which is as good as an event because we write them | — |
| a unit dropped by `setPosATL` has landed | **pollable only** — its own Z | — |
| nothing further happened for N seconds | **neither.** An absence has no event by construction; only dwell measures it | — |

Where a pollable condition wants an engine-side callback rather than a `waitUntil`, `createTrigger` is the engine's own general answer: an arbitrary condition, which the engine checks "approx. every 0.5 second by default" and `setTriggerInterval` (1.98) can speed up to every frame (`commands/createTrigger.wiki`, `commands/setTriggerInterval.wiki`). Our probes already run inside a `spawn`, so a `waitUntil` costs the same and reads better; the trigger matters only for a probe that must not hold a scheduled thread.

### The worked conversion, and what the rest would be worth

`ai-commander` was converted first: its 150 s settle was wholly a proxy — the probe slept, then asked whether any marching Squad had closed more than 50 m on the place it was ordered to, which is a question the world answers at any instant. It now asks continuously, with the 150 s as the deadline.

| | before | after |
|---|---|---|
| measured | 179 s (`20260801T042112Z`) | **45 s**, **45 s**, **44 s** (`…083740Z`, `…084408Z`, `…084556Z`) |
| the wait itself | 150 s, fixed | 14.7 s and 15.2 s, ended by the claim |
| verdict | PASS | PASS, PASS, PASS |

The exit fires on the crossing: WEST-1 had closed 50.7 m and 50.4 m on the two runs, against a threshold of 50. `closed=1 of=2` where the old probe recorded `closed=2 of=2` — the assertion was always "at least one", and a fixed settle simply bought a second Squad's crossing nobody was asserting.

Projected across the corpus, on the audit above and conservatively (the 20 s "world built, report loop cycled" settle assumed to convert to ~3 s against our own counters, and the two-sided and decay waits assumed to converge only near their true crossings):

| | s |
|---|---|
| measured saving, `ai-commander` | 134 |
| the eight remaining 20 s bring-up settles | ~120 |
| `contacts` knowledge spread, `contact-decay` age-out, `casualties` drain and drops | ~65 |
| `two-commanders`, if its drain extremum can keep a floor | ~100 |
| `campaign-end`'s 2 × 20 s | 0 — an absence claim, dwell is the measurement |
| **total against a 1,405 s pass** | **~420, 30%** |

Only the first row is measured. The rest is a projection and should be treated as one; `two-commanders` in particular is the corpus's worst settle-to-subject ratio by wall (180 s of settle against about 30 s of work) but the hardest conversion, because #17's push-path number is the largest drain *observed* and an extremum shrinks with the window it was observed in. It is raised as its own issue rather than done here.

### What the runner needs

Nothing. `spike/regress.sh` already ends a probe on its own `probe_done` line with the header window as the deadline (#23), so every second a probe stops sleeping is a second off the pass with no runner change at all. Windows stay sized to the subject's worst case; they are deadlines, and shortening one because a converted probe now usually finishes sooner would be sizing a window to the good case.

## Serialisation

The Arma tier is single-occupancy: one server install, one port range (2402–2406), one machine shared with the human's play sessions. Concurrent agents serialise on an **`flock(2)` lock at `~/.arma-cti/tier.lock`**, taken by `spike/tier-lock.sh`, which wraps `just probe` as well as `just regress` — a hand run that ignored the lock would be exactly the collision it exists to stop — machine-scoped, not repo-scoped, because agent worktrees are siblings and a lock inside any of them serialises nobody. `flock` rather than a pidfile because the kernel releases it when the holder dies, which is precisely the stale-holder failure Phase 0 met on a port (`infra_unavailable` on a daemon nobody had killed). Validated in anger on 2026-08-01, the day it shipped: a session limit killed an agent mid-run and the lock freed itself — no stale holder, no ghost `infra_unavailable`. The dead run's leftovers are the other half of that event: an evidence directory with no `verdict.json` is not a result, and any server, daemon, or staged world the dead holder left is stale state to clear before the next run (ADR-0022).

Acquisition is non-blocking by default. If the lock is held, the runner writes no evidence, touches no port, and exits `infra_unavailable` — per the failure-class table that is a stop, not a result — printing the holder metadata the lock-holder wrote beside the lock (`tier.lock.info`: pid, started-at, worktree, branch, issue, and the command with its probe list), so the queued agent knows what it is waiting behind and roughly how long. The `issue` field comes from `CTI_TIER_ISSUE` and reads `unstated` when nobody set it — it is metadata for a human reading a queue, never something the command needs. `just regress --wait <secs>` bounds a blocking acquire (`flock -w`) for agents that would rather queue than yield; unbounded waiting is not offered, because an agent that would wait forever should be doing other work.

The lock covers agents, not the human. The human is protected first by the port split (their sessions own 2302–2306) and second by a pre-flight check in `spike/host-guard.sh`: if `arma3_x64.exe` is running on the Windows host, a play session may be live and the runner refuses with `infra_unavailable` rather than loading the shared machine underneath it. The human's side of the contract stays what it is: they never need to know the tier exists.

That check **fails closed**, and it says so because for its first day it failed open (#41). It was wrapped in `command -v tasklist.exe`, and the WSL2 interop `PATH` append is not in effect in an agent's shell, so the guard was skipped in silence on every run — a check that could not run, reported as a check that passed. The tool is now resolved by absolute path (`/mnt/c/Windows/System32/tasklist.exe`, overridable with `CTI_WINDOWS_TASKLIST`), and *not being able to read the process list* is the same `infra_unavailable` stop as reading the game in it. Only "the list came back and the game is not in it" is permission to proceed. `taskkill.exe` on teardown is resolved the same way and is now keyed on having launched a Windows process rather than on having been asked to, so a run that refuses at the pre-flight cannot kill the client it just refused to disturb. `tests/unit/test_host_guard.py` exercises both branches without Arma by substituting the tool.

### Running more than one world at once

Measured on #44 and decided in **ADR-0028**: it works, and the blocker is ports rather than the machine. A dedicated server is **1.14–1.23 GB**, a headless client **1.16–1.20 GB**, the daemon **35 MB** — so a slot is ~1.2 GB, or ~2.43 GB for the three probes that need a headless client, not the ~2 GB per *server* the design was braced for. Two heavy worlds concurrently peaked at 4.89 GB and 2.8 cores of twelve, with every probe still passing its own assertions; the pair `two-commanders` + `campaign-end` ran in 365 s against 625 s serial, and `contacts` + `casualties` in 66 s against 125 s.

The engine binds three UDP ports — game, +1 Steam query, +2 Steam master — so slot 0 holds 2402–2404 and two slots need six ports where the Contract allocates five. A pool needs an allocation change nobody has made yet, which is why the tier is still serial.

One finding is worth carrying whatever happens to the pool: the first two-slot attempt had isolated ports, dirs, installs and daemons and **still merged**, because the shim resolves its daemon from `CTI_DAEMON_ADDR` once per process and `run.sh` set only `CTI_DAEMON_PORT`. One daemon received both worlds; the run not asserting on telemetry went green. `run.sh` now exports the address beside the port. A slot boundary is only real where something reads it.

## Verdicts, and what an agent must do with each

Per probe the runner emits the verdict `run.sh` already synthesises — `PASS`, or `FAIL` with a `class` from the CLAUDE.md table — plus the probe name, evidence path, git SHA and Arma version, in a `verdict.json` in the run's evidence directory and as the last lines on stderr. The required responses are the CLAUDE.md table's, unchanged; the tier adds nothing to them and this document does not restate them. Two get regression-tier-specific teeth:

**`timeout`.** The window came from the probe's own header, so a timeout is never answered by editing the header upward unless the *subject* grew — a schema change that doubles the decay being measured, say — and the header prose must say so in the same change. A probe that times out at its declared window and would pass at a larger one, subject unchanged, is a synchronisation bug in the probe, per the `probe` recipe's rule (validated on #28: both fixes were geometry and readiness, neither was a longer wait).

**`flake_quarantine`.** The tier itself never retries: one run, one verdict. If a probe fails and a rerun passes with nothing changed — the definition of a flake — the agent does not average the two into a pass. The probe gains a `// quarantined: #<issue>` header line pointing at an open issue describing the synchronisation suspicion; the runner still executes quarantined probes but reports their verdict as `flake_quarantine` and excludes them from the exit code, so the corpus keeps gathering evidence about the flake without the flake gating anyone. De-quarantining is the fix for the named issue plus removal of the line, in the same commit. A quarantined probe with no open issue is out of policy — the quarantine line without the issue number does not parse.

## Evidence

Every run writes `~/.arma-cti/runs/<UTC-timestamp>-<probe>/`: `verdict.json`, `results.env`, the server stdout log, daemon log, daemon telemetry JSONL, the extracted `CTI|` lines, and the staged `harness.sqf` (the probe *as appended*, so the evidence carries the exact source that ran even if `spike/probes/` has since moved on). Machine-scoped for the same reason the lock is: worktrees are deleted after landing, and evidence that dies with its worktree is the #27 reconstruction-by-luck failure again.

Retention: failures are kept until the issue that consumed them closes; passes are pruned by the runner at startup to the last three per probe. The durable record is not the directory but the issue: a run that gates an issue is quoted into that issue — verdict line, class, evidence path, git SHA — before the issue closes. A later session re-reading why a run passed starts at the issue comment and follows the path; if the directory has been pruned, the comment still carries the verdict and the SHA to re-run it at.

## Cost control: what runs per issue, and who decides

Per issue: any issue whose change touches an in-world surface — `addons/`, `missions/`, `extension/`, the daemon's world-facing half, or the manifests — runs the **full corpus** once, green, before landing, and quotes the verdicts into the issue. Full rather than selected, because at eight probes and under half an hour the selection machinery would cost more than it saves, and because the expensive failures to date have been the unselected kind — a projection change breaking contact sampling is exactly what a per-issue filter would have filtered out. The `issues:` header exists so that *when* the corpus grows past the point this stops being true, selection can be built without touching the probes; growing the corpus is what triggers building it, and that call is a fable-session call. That call was made concrete at the 2026-08-01 retro (ADR-0022): a full pass costs a measured ~1.5–2 minutes of wall per probe including bring-up, so **when a full green pass first exceeds 30 minutes measured — roughly 15–18 probes on the current curve — build selection on the `issues:` header before adding the next probe.** The machinery landed on #36 before the trigger fired, at fourteen probes and an arithmetic ~26 m 40 s — see the next section for what it selects on and why that does not change what gates. The full corpus stays the per-issue gate. The event-driven conversions above buy headroom against that trigger rather than replacing it: they lower the wall per probe, so the corpus can hold more probes before 30 minutes, and the trigger stays a measured 30 minutes either way.

### The selector, and what it is not

Built 2026-08-01 on #36, ahead of the trigger rather than after it: the fourteen-probe arithmetic total is about 26 m 40 s (below), which is close enough to 30 minutes that building the machinery *after* it fires would mean building it in the middle of the issue it first inconveniences. The selection rules are unit-tested; nothing about the runner's behaviour on a full corpus changed.

**The selector is the `issues:` header, and it selects on provenance — which issue caused a probe to be written — not on blast radius.** That distinction is the whole of when it may gate:

- **What it is for.** Coming back to a surface an earlier issue built: `--issues 32` runs what #32's work produced, and is the fast way to ask "does the thing that issue established still hold?" It is also the honest way to name a subset in an issue comment, because the numbers are in the probes rather than in the reader's memory.
- **What it is not for.** Gating *your own* issue. A probe carries the issue that motivated it, so `--issues <the issue you are working on>` selects the probes you have just written and nothing else — the narrowest possible reading of your own change, chosen by you, which is the definition of a filter that cannot catch what you did not think of. The expensive failures to date have been exactly that kind: a projection change breaking contact sampling. **The full corpus stays the default and the pre-landing gate for wire-touching work**, and "when genuinely unsure, run it all" is unchanged.

A **changed-files selector** was considered and rejected. It is the selector an implementing agent would actually want — it knows its diff, not which probes cover it — but there is no honest map from a file to a probe. Probes declare what motivated them, never which surfaces they exercise; deriving coverage from the commits a probe was landed alongside would infer coverage from history rather than from behaviour, and would be silently wrong in exactly the case that matters, a probe that covers a surface it was not written for. Building that map means a new `covers:` header per probe, maintained by hand, wrong the moment a probe's assertions move, and load-bearing for whether a change is gated at all — a second place to forget, with a green pass riding on it. The one exact git-derived mapping available (the probe *files* a diff touched) selects the probes you just edited, which is iteration, and `just regress <name>` already serves it. When coverage-directed selection is genuinely needed, it belongs to #5's Phase-3 harness, where the coverage query is already on the list and specs declare what they exercise.

Not per issue: docs, tooling, process, and changes wholly covered by the unit tier (income arithmetic, rejection codes, wire formats — the things #23 explicitly keeps out). The implementing agent decides which side of that line an issue falls on, by the surface rule above; when genuinely unsure, the answer is to run it — a false half-hour is cheaper than a false green. During development of an issue, `just regress <name>` on the probes nearest the change is iteration, not gating; the full pass at the end is the gate.

Not this tier at all: per-commit or scheduled runs. The tier is per-issue by design; a cron-shaped invocation would contend for the lock against real work and burn the machine the human plays on.

## Boundary with #5 (Phase 3)

Phase 1 (this tier): bash orchestration grown from `spike/run.sh`; verdicts synthesised from `diag_log` lines by grep, as today; probes are plain SQF appended to the harness; evidence directories as above. Explicitly **not** built here, because ADR-0011 assigns them to Phase 3 and #5 owns them: the Python orchestrator, the verdict travelling through the shim as structured JSON, the gtest-style `EXPECT_*`/`ASSERT_*` framework, declarative specs in `tests/specs/`, the independent oracle, failure bundles as a schema, the coverage query, and the `just accept` / `just accept-all` names — those names stay reserved so Phase 3 arrives into a clean slot. When #5 builds the real harness, it inherits the corpus (probes become the seed acceptance specs), the lock, and the evidence convention; the `regress` runner is deleted, and `just regress` either dies with it or becomes an alias for the acceptance tier over the same corpus — the Phase-3 implementer's call.

## Implementation order

Built in this order on 2026-08-01, steps 1–6. Step 7 is outstanding.

1. **Header blocks** on the four existing probes (`probe:` / `issues:` / `window:`), matching the prose already there. No behaviour yet.
2. **The lock**: `~/.arma-cti/` with `flock` acquire/release and `tier.lock.info`, wrapped around the existing `probe` recipe too, so serialisation protects hand runs the moment it exists.
3. **The runner**: the corpus loop with fresh world per probe, direct wait on `probe_done` under the header window (no client banner, no hold-window burn), per-probe verdicts, worst-class exit.
4. **Evidence directories** with `verdict.json` and pass-pruning.
5. **The `just regress` recipe** and the CLAUDE.md command-table row (run-when: before landing any issue that touches an in-world surface) — the row lands with the recipe, not ahead of it, per the Phase-0 retro rule. Authorised in ADR-0016.
6. **Windows pre-flight check** for a live play session.
7. Follow-on probes as their issues land: `CfgRemoteExec` mode=1 refusal (with #21), broken-manifest refusal (needs the runner's staging hook for a corrupted manifest variant).

Step 3 satisfies #23's first two acceptance criteria; steps 4–5 the rest.
