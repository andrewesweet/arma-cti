# The Arma tier becomes a pool of slots, and a slot is a port block, an install, a daemon and a world that agree

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on a new ADR, and on the tier-architecture change ADR-0016 assigned to the lock. The one thing this ADR does **not** decide is the port allocation it needs — that line in CLAUDE.md exists to protect the human's play sessions, and widening it is left to them.
Reviewed-by-human: pending

Decided on issue #44, from measurement on the VM (12 GB RAM, 8.6 GB available at rest, 12 cores; Arma 2.20.152984). Everything below is a number this exploration ran, not an estimate, except where it says extrapolated.

## Parallelism is viable, and the constraint is ports, not RAM

The human's recollection was ~2 GB per dedicated server. Measured, sampling RSS every two seconds across six in-world runs:

| process | peak RSS |
|---|---|
| dedicated server, `cti.Stratis` on Stratis | **1.14–1.23 GB** |
| headless client | **1.16–1.20 GB** |
| daemon (`uv run cti-daemon`) | **35 MB** |

So the recollection is right about a *slot* and wrong about a *server*: a slot without a headless client is **~1.2 GB**, a slot with one is **~2.43 GB**. Three of the fourteen probes need a headless client (`two-commanders`, `campaign-end`, `massed-assault` — the `CTI_HOLD_HC=1` header).

CPU is not the constraint and is not close to being one. One slot peaks at 1.1 cores and averages 0.5–0.6. Two heavy slots concurrently peaked at **2.8 cores of 12**, averaged 1.1, and never took `loadavg1` above 2.04. The frame budget ADR-0005 cares about was not disturbed: every probe passed its own assertions in both parallel runs.

RAM at N=2, both slots heavy: **4.89 GB peak, with 4.14 GB still available**. Extrapolated linearly, N=3 all-heavy is ~7.3 GB against 8.6 GB available — the last N that leaves real margin. N=4 all-heavy would be ~9.7 GB and does not fit, though it is also unreachable, because only three probes in the corpus want a headless client at all.

## Two slots do not fit 2402–2406

Measured with `ss -lunp` against a running tier server: the engine binds **three** UDP ports — the game port, +1 (Steam query) and +2 (Steam master). With `battlEye = 0` and `disableVoN = 1` it binds neither +3 nor +4, so slot 0 holds 2402/2403/2404 and leaves 2405/2406 free. Two slots need six ports; the Contract allocates five.

The three cannot be packed. `topics/Arma_3_Dedicated_Server.wiki` states the Steam ports are derived from the game port (`+1` for query, `+2` to-master) and `topics/Arma_3_Server_Config_File.wiki` no longer documents `steamPort` or `steamQueryPort` at all, so there is no override to pack them into. That page also asks for **at least 100 ports between consecutive server port sets** — which is exactly why 2402 was chosen as the second set after the human's 2302.

**A pool therefore needs a port allocation the tier does not have**, on the wiki's own stride: slot *N* at `2402 + 100N`, so 2402–2406, 2502–2506, 2602–2606. That is a CLAUDE.md Contract change and it is not taken here. 2302–2306 stay the human's under every option; the pool must never widen towards them, and a slot index that would reach them is a bug, not a configuration.

The N=2 measurements in this ADR borrowed **2407** for slot 1's Steam master port for their duration and nothing was landed that uses it. 2302–2306 were untouched throughout, verified by `ss` on every run.

## What the wall clock actually bought

Same probes, same machine, same session, serial then concurrent:

| pair | serial | parallel N=2 | saving |
|---|---|---|---|
| `contacts` + `casualties` | 66 + 59 = **125 s** | **66 s** | 47% |
| `two-commanders` + `campaign-end` | 210 + 415 = **625 s** | **365 s** | 42% |

Per-probe degradation is inside the probes' own variance: `contacts` 66 → 66, `casualties` 59 → 65, `two-commanders` 210 → 222, `campaign-end` 415 → 365. (`campaign-end` is a soak on a Campaign reaching its end and ran at 365, 372 and 415 s across three green runs; it is the corpus's least repeatable probe by wall, and that is the probe's nature rather than contention.)

The one real contention cost is in bring-up, which is the 19% of a pass #43 identified as this issue's target. In every parallel run exactly one of the two slots paid roughly double to create its host — 5.35 s becomes 11.46 s — and reached mission-running about 6–8 s late; the other slot was unaffected. The headless client join went 13.3 s to 17.5–19.9 s. So a pair costs about 6–8 s more bring-up than the two runs would have cost apart: **~3–4 s per probe, against a ~20 s per-probe bring-up.** The exact doubling smells like serialisation on something shared rather than like resource pressure, and the shared profile directory is the suspect — `-profiles=` is broken on Linux, so both engines write into the one `~/.local/share/Arma 3`. Worth an experiment during implementation; not worth blocking on, at 3 s a probe.

Projecting onto the corpus: thirteen probes are schedulable (`client-port` needs the Windows host and is excluded), totalling **1,547 s serial**. A pool's pass is bounded below by `max(total/N, longest probe)`, and `campaign-end` at ~390 s is the longest:

| N | bound | binding constraint |
|---|---|---|
| 1 | 1,547 s (26 min) | — |
| 2 | 774 s (13 min) | total work |
| 3 | 516 s (9 min) | total work |
| 4 | 390 s (6.5 min) | **`campaign-end`** |
| 5+ | 390 s | `campaign-end` |

**Recommend N=3.** It is the last N with real RAM margin, the last N before the tail probe becomes the whole schedule, and it needs two additional port blocks. N=2 needs one block and gets most of the win. Past N=4 parallelism buys nothing at all, which is worth knowing before anyone builds for it: the way to go below six minutes is to shorten `campaign-end`, not to add slots.

## The isolation the daemon port did not give

The exploration's first two-slot run had isolated game ports, isolated evidence directories, isolated staging, isolated server installs and a daemon each — and **the two runs still merged**. Slot 1's daemon received *zero* lines; slot 0's daemon received both worlds' telemetry, including the three casualties slot 1 had staged and could not then find. Slot 1 failed `assertion_failed`. **Slot 0 reported PASS.**

The cause: the shim resolves its daemon once per process from `CTI_DAEMON_ADDR`, defaulting to `127.0.0.1:9099`, and `spike/run.sh` never set it. `CTI_DAEMON_PORT` moved the daemon and left the world talking to 9099. The two agreed only because both defaulted to the same number — so this was already a latent bug in the serial harness, not a parallelism one: any run on a non-default daemon port was silently a run against somebody else's daemon, or none. Fixed in this change by exporting `CTI_DAEMON_ADDR` alongside `CTI_DAEMON_PORT`; identical at the default port by construction.

This is the shape of hazard the pool must be designed against, and it is worth stating as a rule: **a slot boundary is only real where something reads it.** A per-slot value that no consumer resolves is decoration, and the failure it produces is a green run, which is the worst kind.

## What a slot owns

Everything two concurrent runs were measured to collide on, plus the one that only reads as a collision afterwards:

| resource | per slot | why |
|---|---|---|
| game port block | `2402 + 100N` .. `+4` | three bound today, five reserved for BattlEye/VoN |
| daemon port | `9099 + N` | |
| **shim daemon address** | `CTI_DAEMON_ADDR=127.0.0.1:<slot daemon port>` | the one above is inert without this |
| server install | `~/arma3server-slotN` | `run.sh` stages the mission PBO, `@cti` and the shim *into* the install with `rm -rf`; two runs sharing one install race on the world under test. A `cp -al` hard-link farm of the 5.1 GB master costs 0.02 s and no disk, with `mpmissions/`, `@cti/` and `cti_shim_x64.so` broken out of the farm so staging cannot write through a link |
| server config | generated per slot | `logFile` is written into the one profile directory the Linux engine insists on |
| evidence dir | `~/.arma-cti/runs/` per slot | ADR-0016's convention, unchanged |
| profile / engine name | **open** | both servers ran as `-name=ctispike` and both headless clients as `ctihc1`, sharing one profile directory, with no observed failure across four concurrent runs — and this is the suspect for the doubled bring-up above |

## Allocation, and the stale holder

ADR-0016's `flock(2)` at `~/.arma-cti/tier.lock` generalises rather than being replaced: **one flock per slot**, `~/.arma-cti/slots/N.lock`, acquired non-blocking in index order until one is taken. The properties that made the single lock right are the ones that make "which server is free?" answerable at all — the kernel releases a slot when its holder dies, so a killed agent frees its slot with no reaper, no heartbeat and no pidfile; that is not a hypothesis, it is what happened when a session limit killed an agent mid-run on 2026-08-01. Holder metadata is written per slot exactly as `tier.lock.info` is written today.

Cleanup after a failure is the same question the single lock already answers, asked N times. ADR-0022's rule holds per slot and not per run: a slot whose evidence directory has no `verdict.json` was interrupted, and whatever server, daemon or staged world its dead holder left is stale state for the *next* holder of that slot to clear before it launches — which is why the state is slot-scoped and not run-scoped. No slot free is `infra_unavailable` with the holder list printed, unchanged in meaning from today; `--wait` bounds a queue on the pool rather than on the one lock.

The host guard is unchanged and stays pool-wide: `arma3_x64.exe` on the Windows host stops every slot, because the thing it protects is the whole machine.

## What would overturn this

- **The pool design**, if a slot count above one is measured to change a verdict. Nothing here is worth a probe that passes alone and fails in a pool; the first such probe is a reason to stop, diagnose, and reconsider the whole approach rather than to quarantine it.
- **N=3**, if the extrapolation from N=2 does not hold — the RAM figure for three slots is arithmetic, not measurement, and the implementation must measure it before the third slot is trusted.
- **Recommending a pool at all**, if `campaign-end` gets materially shorter. Most of the win at N=2 comes from the tail; if the tail goes, the arithmetic in the table above changes and #46's conversions are the cheaper lever.
- **The port stride**, if the 100-port spacing turns out to be advice about routers rather than about the engine. It is BI's own recommendation and the tier already follows it; a measured reason it is unnecessary would let a pool fit in less space.
