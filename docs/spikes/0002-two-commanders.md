# Spike 0002 — the push path at two Commanders

**Run:** 2026-07-31 · **Issue:** [#17](https://github.com/andrewesweet/arma-cti/issues/17) · **Records:** the measured budget [ADR-0015](../adr/0015-two-commanders-one-daemon.md) rests on

Two planners double the traffic on the path that carries work into the world, and #17 asks for
that headroom measured rather than estimated. Two documented ceilings bound it, and neither is
ours to move:

- **The drain.** The engine drains at most 100 `ExtensionCallback`s per frame
  (`topics/Extensions.wiki`, ADR-0004). Effects ride a poll rather than a callback here, but the
  ceiling is the same shape: how much one handover can carry before the world takes it across
  frames.
- **The stall.** A blocking `callExtension` past 1000 ms trips
  `EXECUTION_WARNING_TAKES_TOO_LONG` and stalls the frame (ADR-0005). Both planners run inside the
  world's blocking `observe` call, so that call *is* the budget under load.

## What the runs were

Arma 3 server 2.20.152984, WSL2 dedicated server plus a Linux headless client, Stratis, both sides
under an AI Commander, nobody sending a Command. Two runs, the second the same probe soaked long
enough for ground to change hands:

```
CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4 \
    just probe spike/probes/two-commanders.sqf 600
CTI_PROBE_SOAK=700 CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4 \
    just probe spike/probes/two-commanders.sqf 900
```

Numbers are recorded into `.spike-out/results.env` by the run itself
(`tools/push_path_report.py`), so a later run overwrites them rather than leaving them to be
re-derived.

| Measurement | 300 s run | 12 min run | Against |
|---|---|---|---|
| Largest single drain | 4 effects | **4 effects** | 100 per frame → **×25 headroom** |
| Drains / effects applied / deferred | 4 / 12 / 0 | 9 / 21 / 0 | — |
| Frames a drain spanned, worst | 10 | 10 | not frame-blocking: the pump yields |
| `observe` p50 (both planners inside it) | 770 µs | **746 µs** | 1000 ms stall cap → 0.07 % |
| `observe` p95 / max | 5.03 / 5.41 ms | 5.01 / **8.69 ms** | 1000 ms stall cap → **0.87 %** |
| `observe` calls | 39 | 142 | one every 5 s, per ADR-0005's cadence |
| Decisions traced, WEST / EAST | 150 / 150 | 584 / 562 | — |
| Commands accepted, WEST / EAST | 6 / 6 | 9 / 9 | — |
| `plan_refused` | 0 | **0** | — |
| Replies with `error` or `rejected` | 0 | **0** | — |
| Headless client desync | 0 throughout | 0 throughout | — |

Reading these:

- **The push path is not the constraint at two sides, and is not close.** The largest handover a
  run made was four effects — two Purchases and two Orders landing in one cycle, one per side. The
  analytic worst case is the whole force re-tasking at once: one Purchase and up to eight Orders
  per side on Stratis, 18 effects, still ×5.5 inside the cap. Doubling the sides doubled the
  traffic on a path with a factor of twenty-five to give.
- **A drain is not frame-blocking.** Four effects spanned ten frames, because applying one spawns
  units and creates waypoints and the engine takes that at its own pace. So the 100-per-frame
  ceiling is bounding something this path does not do in one frame anyway — which is the
  reassuring direction to be wrong in.
- **Two planners inside the blocking call cost under a millisecond at the median.** The picture is
  assembled, both scorers run over eight Objectives and their whole force, and both traces are
  written, in 770 µs p50 and 5.4 ms worst. That is 0.54 % of the stall cap, so the cadence has
  room for a much more expensive Commander before ADR-0005's constraint is the thing to design
  against.
- **Nothing was refused.** 300 decisions and 12 accepted Commands across both sides with no
  `plan_refused`, so neither Commander tried to spend Funds it did not have or order ground it
  already held.

## The unattended run itself

The twelve-minute run is what #17's "leave it alone" criterion rests on. The probe asserts, per
side: a force fielded that nobody ordered, no two Squads of one side sent to the same Objective,
ground *closed* rather than reached (the Bases are over a kilometre from anything), a force no
larger than the map's Objective count, the effect pump still polling a daemon still answering, and
no single drain reaching the cap.

What the Campaign did, with nobody sending a Command:

```
23:32:03 order_applied WEST-1 capture agia_marina    EAST-1 capture camp_rogain
23:32:09 order_applied WEST-2 capture camp_tempest   EAST-2 capture lz_baldy
23:32:14 order_applied WEST-3 capture girna          EAST-3 capture old_outpost
23:38:01 objective_captured WEST agia_marina  -> WEST-1 capture lz_baldy
23:41:26 objective_captured EAST lz_baldy     -> EAST-2 capture old_outpost
                                              -> EAST-3 capture agia_marina
23:41:42 objective_captured EAST camp_rogain  -> EAST-1 capture air_station
23:42:02 order_applied WEST-4 capture camp_rogain
[spike] verdict=HOLD-COMPLETE
```

Three Objectives changed hands in twelve minutes, each capture re-tasking the Squad it freed in
the same second, and by the end each side was marching on ground the other had just taken — EAST-3
on Agia Marina, WEST-4 on Camp Rogain. Not a stalemate, and not a deadlock: 356 polls, 1,146
decisions, 18 accepted Commands, nothing refused.

The decision traces stay separable by their `side` column, and with teeth: **no decision row on
either side is about the other side's Squad**, across all 1,146.

```json
{"event":"command_issued","at":605.2,"side":"WEST","command_side":"WEST","command":"order",
 "args":{"squad":"WEST-4","order":"capture","objective":"camp_rogain"}}
{"event":"decision","at":710.5,"side":"WEST","about":"WEST-4","chose":"capture camp_rogain",
 "because":"already under this Order; 1.2 ahead of capture camp_tempest","scored":8}
{"event":"decision","at":710.5,"side":"EAST","about":"EAST-3","chose":"capture agia_marina",
 "because":"already under this Order; 1.7 ahead of capture old_outpost","scored":8}
```
