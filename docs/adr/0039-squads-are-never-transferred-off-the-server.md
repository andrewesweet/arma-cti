# Squads are never transferred off the server

Delegated-decision: no — the human took this one directly
Date: 2026-08-02
Reviewed-by-human: 2026-08-02 — decided by the human in session
Claimed: comment on #117, 2026-08-02, after `git fetch origin` (origin/main at `f1af42d`,
`docs/adr/` topping at 0038) and a scan of open-issue bodies found no claim above 0038

## The decision

Every Squad is owned by the server, for its whole life. `setGroupOwner` is banned in our
SQF outside `spike/desync-load.sqf`, the #8 headless-client desync investigation tool,
whose groups are throwaway load traffic and never Squads.

*(Path amended 2026-08-02 by ADR-0045, #128: the tool was
`addons/main/functions/fn_desyncLoad.sqf` when this was written and is now staged by the <!-- absent-path: the pre-ADR-0045 path, named here because the amendment is about the move -->
harness rather than shipped in the addon. The exemption is the same one and follows the
file; the decision above is untouched.)*

This is #117's Option A, chosen over the alternative on the table: an object-locality
convention (`local`, `groupOwner`, `owner` guards) that would let Squads move and make
each call site defend itself.

## Why

The Order path drives groups entirely through waypoints (`fn_orderApply.sqf:112-166`),
and the #117 investigation read what the vendored wiki declares for each scripting
command on that path:

| Command | `arg=` | `eff=` |
|---|---|---|
| `addWaypoint` | global | global |
| `deleteWaypoint` | global | global |
| `setCurrentWaypoint` | **local** | — |
| `setWaypointBehaviour` | *(none)* | global |
| `setWaypointSpeed` | *(none)* | global |
| `setWaypointType` | *(none)* | *(none)* |
| `setWaypointCombatMode` | *(none)* | *(none)* |
| `setWaypointCompletionRadius` | *(none)* | *(none)* |
| `waypointAttachObject` | *(none)* | *(none)* |

`setCurrentWaypoint` is documented `arg= local`, and `fn_orderApply` calls it on every
Order. On a group the caller does not own, the Order's waypoints would be written and the
group would never be switched onto them: an Order that looks issued and is not. Four more
commands beside it declare no `arg=` at all, and an undeclared `arg` on the BIKI defaults
to local.

Nine engine calls, of which one is documented-local, four are undeclared, and four are
global. A locality convention has to be right at every one of them and re-checked every
time the path grows. The rule has one place to be checked — `setGroupOwner`'s call sites,
currently one — and that place is mechanically checkable, which is why deliverable two of
this decision is a gate rather than a paragraph.

It also costs nothing today. Every group is created server-side in `fn_effectApply`, so
server ownership was already true; it was an unwritten invariant, not a change. This ADR
writes it down and `tools/check_sqf_bans.py` holds it.

## What this is not

It is not a claim that the headless client is useless. The HC still receives AI updates
and still carries the traffic the #8 investigation measures. What it may not do is
*simulate a Squad under Orders*.

It is not a measurement. No probe was run. A green in-world probe would not have licensed
the transfer anyway — `setCurrentWaypoint` would still be documented local — and a red one
only confirms the rule. The probe spec from #117 stands unchanged for whenever it is
needed: transfer one group to the HC, issue an Order from the server, read the waypoint
back, and assert `waypointType` and `currentWaypoint` on both machines.

## What would overturn it

A measured server frame rate, at a real Phase-4 unit count, showing AI saturation on the
server.

If that measurement arrives, the remedy is not this rule relaxed in place. It is a
designed ownership seam — or a headless-client offload with locality guards on the whole
Order path, verified in-world before a single Squad moves — taken as its own piece of
work, with its own ADR. Not an emergency patch under a dropping frame rate.

## Elimination-context caveat

This choice is made against today's unit counts, and an elimination only holds in the
context it was tested. The number to re-measure is the gap between Arma's practical
~200-unit ceiling for one machine's AI and Phase 4's worst case of roughly 256 men across
both sides. Neither figure has been measured in this repo; both are estimates, and the
first of them to be measured for real is what makes the overturn clause live. Until then
the rule stands on the wiki's locality declarations, which do not depend on unit count at
all.

Raised and decided on #117. Related: #111 (the SQF locality review that found it), #8
(the desync investigation that owns the one exempt file).
