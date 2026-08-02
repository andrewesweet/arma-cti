# A locality guard belongs at the boundary, and says so out loud

Delegated-decision: no
Date: 2026-08-02
Reviewed-by-human: 2026-08-02 — accepted by the human in session, on the proposal in #118
Claimed: comment on #118, 2026-08-02. Written as 0040 and renumbered on landing: #117's
0039 (`cde0fd0`) and #62's 0040 (`6218bb5`) both landed while this was in flight, which
is what a claim-by-comment cannot prevent when three agents work the same hour.

## The decision

A locality guard — `isServer` or `hasInterface` asked in order to refuse — exists at a
**boundary**, and nowhere else. A boundary is a call site that does not already decide
which machine the function runs on. Three of them exist in this addon:

1. **Reachable by `remoteExec` from a client.** `cti_fnc_portGateway` alone. The
   mission's `description.ext` fences it at `mode = 1` with `allowedTargets = 2`, so a
   client-initiated call can only land on the server
   (`topics/Arma_3_CfgRemoteExec.wiki:59,68`); the guard is belt and braces against a
   regression in that config, which is the one failure a config cannot defend against
   itself.
2. **Reachable by `remoteExec` from the server onto a client.** `cti_fnc_portReply` and
   `cti_fnc_mapObservation`. Server-to-client `remoteExec` is unrestricted
   (`topics/Arma_3_CfgRemoteExec.wiki:9`), so no config protects these at all and the
   guard is the only thing there is.
3. **The entry point of a supervised loop.** The seven functions that register with
   `cti_fnc_loopRegister`, directly or through `cti_fnc_everyInterval`:
   `cti_fnc_effectPump`, `cti_fnc_presenceReport`, `cti_fnc_commanderAssign`,
   `cti_fnc_commanderView`, `cti_fnc_orderEnforce`, `cti_fnc_baseAssault` and
   `cti_fnc_loopWatch`. A loop is inventoried by name rather than by caller, its guard
   costs one evaluation per session rather than one per turn, and it is the one call
   site a restart would re-enter.

Everywhere else the machine is already decided by the caller, the guard cannot fire, and
it is a comment pretending to be code. **Delete it and say so in the function header**,
in the form "Interior to the server's own call graph, so it carries no locality guard:
every path into it starts in `missions/cti.Stratis/initServer.sqf`, which the engine runs
on the server and nowhere else." A sentence a reader can check beats a branch a reader
cannot reach.

A guard that stays is written as `SERVER_ONLY(<sentinel>)` or
`INTERFACE_ONLY(<sentinel>)`, macros defined in `addons/main/script_component.hpp` and
included by absolute path:

    #include "\cti\addons\main\script_component.hpp"

Each logs one `CTI|FAIL class=assertion_failed locality wanted=… machine=… file=…` line
and then returns the caller's sentinel. `tools/check_sqf_bans.py` rejects the
hand-rolled shape so the convention enforces itself.

## Why

#111's review inventoried 26 guards — 22 `isServer` and 4 `hasInterface` at the sha it
read, 24 and 5 by the time this landed — and found that **none of the `isServer` guards
could fire**. Every call path into all of them originates in
`missions/cti.Stratis/initServer.sqf`, which the engine runs on the server alone, and
`config.cpp`'s `CfgFunctions` declares no `preInit` or `postInit`
(`topics/Arma_3_Functions_Library.wiki:175-183`), so nothing self-starts anywhere.

Seventeen of the sentinels those guards returned were read by nobody, and the five that
were read were read as data. That is #112 and #113: an empty presence map is
indistinguishable from "nobody stands anywhere", an empty squad map from "no Squads
exist", and a bare `false` beside siblings that log before returning theirs is
unattributable. The daemon would have accepted a report assembled off the server as a
truthful picture of an empty island, with no failure line anywhere.

So the choice was never only which macro. It was how many guards should exist at all. A
convention that mechanically macro-ifies unreachable guards spends its churn making dead
code uniform.

The macro is what a lint alone could not supply. A lint can enforce shape; it cannot
write the log line, so #112 and #113 would have stayed open and been re-opened by the
next author. Making the line structural is what stops a sentinel arriving in silence.

## What was rejected

**A `cti_fnc_serverOnly` guard function.** SQF gives a callee no way to return on its
caller's behalf, so every call site would still read
`if !(call cti_fnc_serverOnly) exitWith { … }` — the hand-roll still there, the sentinel
still chosen locally, and a function call added to the hot path.

**Keeping the interior guards as defence in depth.** They defend against a call site that
does not exist, at the cost of nineteen unreachable branches that a reader has to
evaluate and a future author has to keep in step. The header sentence carries the same
information where it can be read.

**`cti_fnc_offServer`, kept as the macro's voice.** It was #112's fix — one function
that logged the typed line and returned a refusal shaped like nothing a caller reads.
Every one of its ten call sites was an interior guard, so deleting those left it dead,
and its name ("off server") does not cover the interface half. Its job moved into the
macros and the function is gone.

## The two things this is honest about

**The include path was unverified in this repo and is now verified twice.** Nothing here
included anything from a `.sqf` before. HEMTT resolves
`#include "\cti\addons\main\script_component.hpp"` through the PBO prefix and errors
`PE12: include not found` on a wrong path, and it parses the macro expansion — a
deliberate syntax error inside the macro body surfaces as `SPE2` at the *use* site. That
is the build tier. The engine's runtime preprocessor is a separate question, and
`spike/probes/locality-guard.sqf` is the answer to it: if the include did not resolve
in-world, `INTERFACE_ONLY(nil)` would reach the compiler as an unknown token,
`cti_fnc_portReply` would not compile, and the probe could not go red the way it is
declared to.

**Only half the convention is exercisable.** `INTERFACE_ONLY` can be tripped from a
server-side probe, because `hasInterface` is false on a dedicated server. `SERVER_ONLY`
cannot, because nothing in the tier runs an addon function on a machine that is not the
server — #116 is the same gap seen from the probe side. `SERVER_ONLY` is verified by
inspection and by sharing the expansion its sibling proves; the two differ by one command
and one word. The macro's contribution to a case no test reaches is that a misfire is
now visible in any run's log rather than silent, which is worth having whether or not a
test ever asks for it.

## Consequences

- Nineteen guards deleted across nineteen files, each gaining a header sentence.
- Ten kept, all behind the macros: eight `SERVER_ONLY`, two `INTERFACE_ONLY`.
- `addons/main/script_component.hpp` is new, and is the first `#include` from SQF in this
  repo. Anything else the addon wants to share as a macro now has somewhere to live.
- `cti_fnc_offServer` is deleted, with its `CfgFunctions` entry. #112 and #113 close.
- `tools/check_sqf_bans.py` gains the guard-shape rule. It bans refusal
  (`if (!isServer) exitWith`), not enquiry (`if (!isServer) then`), so
  `missions/spike.Stratis/init.sqf` finding its headless client stays legal.
- A new locality guard now costs an `#include` and a macro call. That is the intended
  friction: the guards that remain are the ones somebody decided to keep.
