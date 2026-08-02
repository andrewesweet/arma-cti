# An investigation tool is staged by the harness, not shipped in the addon

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on an ADR, on a CLAUDE.md rule's wording, and on amending ADR-0039's exempt path (#128, hole 3 of `docs/command-port-audit.md`)
Reviewed-by-human: 2026-08-02
Claimed: comment on #128, 2026-08-02, alongside ADR-0044

## The decision

A tool that exists to answer an open investigation does not live in the shipped addon or
the shipped mission. It lives beside the harness and is staged into the generated
`harness.sqf` by the run that asks for it.

`spike/run.sh` already states this rule for probes — "the mission is the thing under test,
and a probe that lives in it is one that ships". This extends it to the other kind of
harness-only code, and applies it to the one instance: `addons/main/functions/
fn_desyncLoad.sqf` becomes `spike/desync-load.sqf`, staged when `CTI_DESYNC_LOAD` is set
and absent otherwise. `CTI_DESYNC_LOAD` now decides whether the tool is *present* rather
than whether a shipped one runs.

ADR-0039's `setGroupOwner` exemption moves with the file, in `tools/check_sqf_bans.py` and
in CLAUDE.md's Never list. The rule is unchanged; only where its one exempt file lives.

## Why

#8's load generator spawns thirty-two WEST soldiers standing on the first four Objectives.
Capture is by presence, so as a Campaign that is WEST handed half the island, and the
mission's own comment said so. It was harness-gated behind an environment variable and
still present in every build, including one a person plays — one variable, or one
mis-scoped `setVariable`, from turning a session into a rout. #19's audit found it as the
one shipped path that changes world state without a judgement and named it as a hole.

Gating it harder inside the addon was the alternative. It loses to relocation on the
simplest reading: a build that does not contain the tool cannot mis-trigger it, and no
amount of gating gets to that. It also keeps the addon's function list honest about what
the addon is for.

The staging machinery already existed and needed nothing new: the file is appended after
`spike/probe-prelude.sqf` and before the probe, waits on `cti_probe_fnc_worldReady`
because the harness runs at the top of `initServer.sqf`, and carries the wait-for-a-client
logic that used to sit in the mission.

**The tool is preserved, not deleted.** #8 is open, and what it needs is exactly what it
needed: something that makes a client's link carry real simulation, so a clean desync
reading means the link held rather than that nothing crossed it. That is intact, including
the headed/headless distinction in how the load is applied.

## What would overturn it

- A build that must carry an investigation tool because the investigation is *of* the
  shipped build under conditions the harness cannot stage — a mod-load or PBO-packing
  question, say, where the staged harness is not the thing under test.
- A playtest that needs the load generator in a human's session. It would then be a
  gameplay-affecting fixture, and `spike/playtest/` is where those live (#42), not the
  addon.

## Consequences

- `addons/main/config.cpp` loses `class desyncLoad {}`, and `missions/cti.Stratis/
  initServer.sqf` loses the call site. The desync *watcher* stays: sampling a link is
  diagnostics the mission is entitled to carry, and it changes nothing in the world.
- `check_sqf_bans` gains a test that the vacated addon path has no standing of its own, so
  a file put back there is caught rather than silently exempt.
- The addon no longer contains any function that spawns units outside the effect pump.
