# Multiplexing the Arma tier: two missions in one server, and two probes in one world

**Explored**: 2026-08-01, on issue #45. Arma 2.20.152984, WSL2, ports 2402–2406 throughout; 2302–2306 untouched.
**Outcome**: sequential multiplexing **works and is measured**; concurrent multiplexing is **declined on the corpus we have**. Neither changes the tier now. No ADR — the tier's architecture is unchanged, so this is the research doc ADR-0016's convention asks for, and ADR-0029 is released back to the pool.

Everything below is a number this exploration ran, except where it says arithmetic.

## The headline

| lever | issue | measured worth | status |
|---|---|---|---|
| early exit from fixed settles | #43 landed, #46 open | 135 s measured, ~285 s projected | do first |
| parallel pool of slots | #47, unblocked 2026-08-02 | 1,547 s → ~516 s at N=3 | do second |
| **sequential mission cycling** | this one | **1,547 s → ~1,400 s serial; ~37 s once N=3 exists** | **do not build** |
| **concurrent shared world** | this one | **~11 s, one bring-up per pass** | **declined** |

The recommendation in one line: **build #46, then #47; do not build either shape of multiplexing.**

This was written while #47 was still blocked on the port allocation, and cycling was recommended as the fallback if that decision went the other way. The human granted the tier `[2400, 3000)` on 2026-08-02, so the condition has resolved and the fallback is not needed. The conditional reasoning is kept below rather than rewritten, because the thing that makes cycling worth so little — bring-up is what a pool removes anyway — is the same fact either way, and because ADR-0028's N=3 RAM figure is still arithmetic rather than measurement. If the third slot does not survive contact with the VM, this is the page to come back to.

## Bring-up, re-measured

#44 and #43 both worked against "about 20 s of every probe is bring-up". Measured directly on four runs this session, from the server's own log:

| stage | secs | notes |
|---|---|---|
| staging (two missions packed, shim and addon installed) | 0.09 | |
| daemon ready | 0.22 | |
| server process → host created | 5.4 | |
| host created → `CTI\|mission_running` | 5.6 | |
| **cold bring-up, no headless client** | **11.1** | |
| headless client join | 13.5 | three probes of fourteen ask for one |

So a thirteen-probe schedulable pass (`client-port` excluded — it drives the Windows host) carries `13 × 11.1 + 3 × 13.5 =` **185 s of bring-up, 12% of a 1,547 s pass**. That corrects the ~240 s / 19% figure #43 handed forward, which came from a 20 s estimate rather than from the log. It is the number both this issue and #47 are aimed at.

## Sequential: two missions in one server process

### The mechanism, and why the obvious one does not work

`topics/Arma_3_Server_Config_File.wiki`'s *Mission Rotation* section is explicit: "Without an admin, the server will automatically select a mission when at least one player is connected." A regression run has no player, so `class Missions` rotation alone is not a lever a runner can pull.

The lever that does work is `serverCommand`'s second syntax (`commands/serverCommand.wiki`, `s2exec= server`): with `serverCommandPassword` set in the server config, the server's own scripting VM can execute an admin command without any client logging in. `"<password>" serverCommand "#mission ctycle1.Stratis"` returns `true` and the server switches, unattended, with nobody connected.

Note where that lever lives: **inside the mission**. There is no channel from outside the world to the running server other than BattlEye RCon, which the tier disables. That constrains the design and is the main hazard below.

### What a cycle costs

Three runs, `spike/cycle/cycle.sh`. Evidence in `~/.arma-cti/cycle/`.

| | secs |
|---|---|
| cold start to `mission_running` (leg A) | 10.80, 10.99, 10.91 |
| **switch requested → leg B `mission_running`** | **under 1 s on all three** |
| daemon restart, needed for freshness (below) | 0.22 |

The engine's own log, run `20260801T115051Z`:

```
12:51:53 "CTI|cycle_switch_requested to=ctycle1.Stratis"
12:51:53 "CTI|cycle_switch_returned accepted=true"
12:51:53 Mission ctycle1.Stratis read from bank.
12:51:53 Roles assigned.
12:51:54 "CTI|mission_running world=Stratis tickTime=61.14"
```

The terrain is already loaded and the same on both legs, which is where the ten seconds go. `diag_tickTime` does **not** reset across the cycle (61.14 above); mission `time` does. Every probe's deadlines are relative (`diag_tickTime + N`), so that is safe today, and it is a trap for anything that ever reads `diag_tickTime` as an absolute.

The headless client **survives the mission change**: run `20260801T115732Z` recorded `hc_connects_total=1`, `hc_disconnects_total=0`, `hc_alive_at_end=true`. So the 13.5 s join is paid once per server process rather than once per probe.

Cycling therefore replaces `13 × 11.1 + 3 × 13.5 = 185 s` with `11.1 + 13.5 + 12 × 1.2 = 39 s`. **~146 s off a 1,547 s pass, 9.4%** (arithmetic on the measured per-cycle figure).

### Freshness is not free, and had to be asserted five ways

ADR-0023 makes a fresh Campaign next boot structural. A cycled mission is fresh in the world — the engine tears the mission down — but the Campaign does not live in the world. It lives in the daemon, and **the protocol has no reset verb**: `commands.py`'s catalogue is `purchase` and `order`, the AI Commander sides are process launch arguments, and a `Campaign` object is fresh only because the process is. So the cycle has to restart the daemon, which costs 0.22 s.

Per the #44 lesson — an isolation failure is silent and produces a false green — each axis is an assertion, and a control run was used to prove the assertions can fail. `spike/cycle/leg-a-dirty.sqf` buys two WEST Squads, captures `agia_marina` and draws a seeded stream; `spike/cycle/leg-b-fresh.sqf` asserts the cycled world is clean.

| axis | with the daemon restarted (`20260801T115318Z`, PASS) | control, daemon kept (`20260801T115502Z`, FAIL) |
|---|---|---|
| Campaign, Funds | 300 — the authored start | **115** |
| Campaign, ground | `agia_marina` NEUTRAL | **`agia_marina` WEST** |
| roster | 0 Squads | 0 Squads — **see below** |
| telemetry | leg B's file carries 0 leg-A rows | **3 leg-A rows** |
| shim connection | round trip echoes leg B's own id | echoes |
| PRNG streams | `[312,243,707,265,175]` both legs | identical both legs |

The control run's verdict was `assertion_failed cycle_b_ground_carried_over west_held=["agia_marina"]`, which is what makes the passing runs worth something.

**The roster is not a freshness detector, and this is the finding to carry forward.** In the control the stale daemon reported `squads=0` anyway, because the roster reconciles against reported presence and leg A's Squads no longer existed in the world. An assertion set built on "the roster is empty" would have passed the dirty cycle — the exact shape of #44's false green, met again on a different axis. Funds, ground and telemetry are the axes that carry the signal; the roster self-heals and says nothing.

The shim needed no work: `extension/src/lib.rs` drops its cached connection on any failure and reopens, so a daemon restart under a live server is transparent by construction, and leg B's echo confirms it.

### The hazards, which are the reason this is a fallback rather than a plan

1. **The switch lever is inside the mission.** A probe that wedges its world cannot be cycled out of it, and the recovery is the cold server restart the cycle existed to avoid. A runner would need a harness-level watchdog that fires the switch on window expiry regardless of the probe — buildable, but it is new machinery sitting directly on the path a `timeout` verdict travels, which is the path that most needs to be trustworthy.
2. **One server log holds the whole pass.** ADR-0016's evidence convention is one directory per probe; under cycling those directories are slices of a single stdout, cut at `mission_running` boundaries. A slice that takes the wrong leg's lines produces a green. Same hazard class as the daemon address in #44: a boundary that is only real where something reads it.
3. **The world topology stops being per-probe.** The headless client surviving the cycle is a saving and a coupling: a probe whose `env:` header does not ask for an HC now gets one, unless the runner joins and leaves it per cycle and pays the 13.5 s back. Three probes want one; ten do not.
4. **Every mission must be staged before the server starts.** That is cheap (0.09 s for two) but it fixes the pass's contents at launch, so `--issues` selection has to resolve before any world comes up. It already does.

## Concurrent: the corpus classified for a shared world

### The test a pair has to pass

Two probes can share a world only if neither's **writes** land inside the other's **reads**, and their daemon requirements agree. Four things make that hard here, and all four are structural rather than incidental:

- the presence report samples **every unit on the island**, and the daemon judges and pays ownership from it;
- the casualty watch records **every death on the island** (#39's whole point is that the record has no holes);
- the contact sampler reads **every leader's knowledge of every enemy**;
- there is **one Campaign per daemon** — one Funds pool and one roster per side, one ownership table — and the AI Commander sides are fixed at daemon launch by `env: CTI_AI_SIDE`.

### The fourteen

| probe | writes to the world | reads globally | shareable? |
|---|---|---|---|
| `bareworld` | **nothing** | monotone counters only: effect-pump polls ≥ 3, owner count = objective count | **yes, as a passenger** |
| `json-manifest` | 1 purchase (funds, roster, a Squad at the airbase) | its own reply and the parsed manifest | **yes, with `bareworld`** |
| `human-commander` | 4 purchases | the Commander assignment sweep — one slot per side, globally | no: two probes cannot both own a side's Commander slot |
| `projection` | 1 WEST unit; **an Objective changes hands** | the public reply's key set | no: the capture is a Campaign-wide change |
| `contacts` | 2 purchases, 6 EAST planted and walked | every leader's knowledge | no, by its own design |
| `contact-decay` | as `contacts`, plus a 120 s age-out | same | no |
| `casualties` | 2 purchases, 3 staged deaths | the black box, which records every death | no |
| `base-assault` | 1 purchase, a Squad staged 250 m out, **an HQ brought down** | the assault path | no: an HQ down is Decapitation and can end the shared Campaign |
| `ai-commander` | none of its own; a Commander marches Squads | absence claims: *no* force above the ceiling, *no* Commander playing EAST | no: an absence claim is broken by any co-tenant |
| `two-commanders` | none of its own | both sides' Commanders, plus #17's drain extremum — a **performance** number | no: a co-tenant changes the measurement |
| `massed-assault` | a garrison, plus a Commander's own mass | the size of the force that came | no |
| `campaign-end` | wins the Campaign | that a won Campaign stops handing out work | no: it ends the world for every co-tenant |
| `manifest-missing` | — | needs a world with **no manifest** | no: its world is a different world |
| `client-port` | 3 purchases from a real client | the Windows host, of which there is one | no |

`contacts` states the rule itself, and it is the sharpest reason in the table: *"everything WEST believes to be EAST has to be one of the men actually planted"*, and *"the planted men may not fire back and may not die, because the head count is what the assertions are made of."* Any co-tenant that puts an EAST unit where a WEST leader can see it turns that into `assertion_failed`. The probe was written to own the island, and it says so.

So the shareable set is **`bareworld` plus at most one writer**. One probe of fourteen writes nothing, and that is the whole ceiling.

### The qualifying pair, demonstrated

`bareworld` + `json-manifest`, concatenated into one harness and run in one mission, `~/.arma-cti/cycle/20260801T120100Z-shared-pair/`:

| | solo | shared |
|---|---|---|
| `bareworld` | PASS, 19 s (`20260801T120027Z`) | PASS — `bareworld_probe_done` at +6 s from `mission_running` |
| `json-manifest` | PASS, 34 s (`20260801T120046Z`) | PASS — `json_probe_done` at +20 s |
| FAIL lines in the run | 0 | **0** |

Both verdicts match their solo runs. The pair is safe by construction rather than by luck: `bareworld` writes nothing, and its two waiting assertions are on monotone counters — a co-tenant can make the pump poll sooner or the owner map fill sooner, never later. `json-manifest`'s single purchase moves funds 300 → 200 and adds `WEST-1`, and `bareworld` reads neither.

Serial the pair costs 53 s; shared it costs one bring-up plus the longer probe, about 31 s. That 22 s is the entire measured prize, and it does not generalise: adding any third probe to the world breaks one of the rows in the table above.

### Why that is a decline

The ceiling is one saved bring-up per pass — **~11 s of 1,547 s, 0.7%** — bought with a permanent hazard. A shared world makes every probe's assertions depend on what its co-tenant does, and the corpus grows: #39, #17 and #27 each added a probe that reads the island globally, and nothing suggests the next one will not. The failure mode is the one this project has now met twice (the daemon address in #44, the roster above) — a co-tenancy that quietly makes a red run green.

## The three levers together

They are not additive. **Early exit shortens each probe; the pool divides the number of serial probes; cycling removes bring-up.** Bring-up is the residue the other two leave behind, so cycling is worth most when the pool is smallest.

Projecting onto the thirteen schedulable probes (1,547 s serial today; #46 and #47's figures are theirs, this issue's is measured):

| configuration | pass | what binds |
|---|---|---|
| today | 1,547 s | — |
| + #46 | ~1,262 s | total work |
| + #46 + cycling | ~1,120 s | total work |
| + #46 + #47 at N=3 | ~420 s | total work |
| + #46 + #47 at N=3 + cycling | ~390 s | **`campaign-end`** |
| + #46 + #47 at N=4 | ~390 s | **`campaign-end`** |

Cycling is worth 146 s serial and about 37 s behind a three-slot pool, because a pool of three pays three cold starts instead of thirteen and then hits the tail probe. Past N=3 it is worth nothing at all: `campaign-end` is the floor and no amount of saved bring-up moves it.

### Recommendation

1. **#46 first.** Largest measured lever, no infrastructure risk, no human decision to wait on.
2. **#47 second.** It is the only lever that changes the order of magnitude, and the port allocation it waited on was granted on 2026-08-02 — the tier may now use `[2400, 3000)`.
3. **Mission cycling: do not build it.** It was the fallback if the ports were refused, and they were not. Behind a pool of three it buys 37 s in exchange for a watchdog on the `timeout` path, a log-slicing scheme, and a world topology that is no longer per-probe; that is not a trade worth making. The one thing that would reopen it is #47 failing to reach N=3 — ADR-0028's 7.3 GB figure for three slots is arithmetic, not measurement, and if the third slot does not fit, cycling is the remaining bring-up lever and worth 146 s.
4. **Concurrent shared-world multiplexing: declined.** One probe of fourteen qualifies as a passenger, the ceiling is 0.7% of a pass, and the failure mode is a false green.
5. **The way below six minutes is `campaign-end`**, not any of these three. Every configuration above with a pool in it ends up bound by one 390 s probe.

## Scaffolding

`spike/cycle/`, kept rather than thrown away for one reason: ADR-0028's N=3 is arithmetic, and if the third slot does not fit, this is the lever the tier falls back on. `just cycle-spike [--no-daemon-restart] [--hc]`. It is not part of `just regress` and its two SQF legs live outside `spike/probes/`, so the corpus never sees them. **Delete it once #47 has measured three slots standing up together** — at that point nothing here is a live option and the recipe is surface for its own sake.

The shared-world pair is not scaffolding and did not land: it was the two corpus probes concatenated unchanged and run through the existing `probe` recipe, and a checked-in copy of 360 lines of probe source would rot the moment either probe changed. It reproduces as

```
cat spike/probes/bareworld.sqf spike/probes/json-manifest.sqf > /tmp/pair.sqf
just probe /tmp/pair.sqf 150
```

then read both `bareworld_probe_done` and `json_probe_done` out of the run's `spike-lines.txt` with no `FAIL` beside them. `just probe`'s await matches any line containing `probe_done`, so it ends on whichever probe finishes first and the second one's completion has to be checked in the evidence rather than waited on — which is the first thing a runner would have to fix if a shared world were ever adopted.
