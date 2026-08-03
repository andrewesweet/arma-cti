// probe: effect-redelivery
// issues: 141
// window: 150
//
// #141 in-world probe: an effect handed to the world twice makes one Squad.
//
// `just regress effect-redelivery`, or by hand
// `just probe spike/probes/effect-redelivery.sqf 150`.
//
// Effect delivery is at-least-once by design (ADR-0018): the pump applies and
// only then acknowledges, so an acknowledgement lost on the wire leaves the
// daemon holding the same sequences and the next poll hands them over again.
// Every effect the addon knows survives that except one — `squad_spawned` was a
// bare `createGroup`, so a redelivery stood a second full Squad on the map,
// overwrote `cti_squads`'s entry with it, and orphaned the first group's men:
// alive, still fighting, in no roster, unreachable by an Order, and reported to
// the daemon by nobody. The guard this probe watches is the receiver
// deduplicating on the Squad id, which is ADR-0034's shape one layer up.
//
// ## Why the redelivery is staged at the receiver rather than on the wire
//
// The lost acknowledgement itself cannot be staged from inside the world. The
// ack goes out through `cti_fnc_daemonCall`, and a probe cannot stub a `cti_fnc_`
// function — the Functions Library `compileFinal`s every CfgFunctions entry, as
// `schema-stale` found out by running green while proving nothing (#80). Nor is
// there a runner hook that drops one reply on the shim's socket.
//
// What a redelivery *is*, though, is entirely receiver-side: the same effect
// document, handed to `cti_fnc_effectApply` a second time. So that is what this
// stages — the first delivery is the real one, through the port, the outbox, the
// pump and the ack; the second is the same document handed straight to the
// function the pump would have handed it to. The subject is the receiver's
// idempotence, and the receiver sees exactly what it would have seen.
//
// ## What stops a green run being vacuous
//
// The redelivered document is rebuilt here rather than intercepted, and a
// rebuild that was wrong could pass by doing nothing. Each way it could be wrong
// is caught by an assertion rather than by inspection:
//
//   * a wrong `effect` name, or a missing `side` — `cti_fnc_effectApply` refuses
//     it, and the verdict is asserted to be `applied`;
//   * a wrong or absent `args.squad` — the id misses the guard, a second group
//     spawns, and the count of groups carrying this Squad's id goes to two;
//   * a document that reached no branch at all — the same assertion, from the
//     other side: the verdict would not be `applied` either.
//
// The count is taken over `allGroups` filtered by the group's own `cti_squad`
// variable rather than over every group of the side, because the world has AI
// Commanders buying Squads of their own throughout the window and a bare group
// count would be a race dressed up as a rule. Filtered that way it is also the
// exact statement of the finding: the orphaned group keeps the id it was minted
// under, so two groups carrying one Squad id is precisely what went wrong.
//
// ## Reproduction baseline
//
// Run twice against the same build on 2026-08-02, at `96eb871`, differing only
// in the guard: with it, PASS in 20 s, `groups=1`, `effect_redelivered
// sequence=1 effect=squad_spawned side=WEST squad=WEST-1 units=8`. With the
// guard's condition forced false and nothing else changed, FAIL
// `assertion_failed redelivery_probe_duplicated_squad squad=WEST-1 groups=2` in
// 21 s — the finding, in the world, in one line. So the probe is red on the bug
// and green on the fix, rather than green on both.
//
// The window is the default 150 and the subject is short: ~20 s for the world to
// build, up to 60 s for one Purchase to cross the outbox and be held as a group,
// and two function calls. Nothing here waits on a firefight or on pathfinding.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable redelivery_probe_no_shim";
        diag_log "CTI|redelivery_probe_done";
    };

    [20] call cti_probe_fnc_worldReady;

    // One Squad through the Command Port, which is the only way a Squad reaches
    // the roster the effect is minted against (ADR-0012). The helper checks the
    // reply, so a refused Purchase is `assertion_failed` here rather than the
    // `timeout` the wait below would otherwise report (#84).
    private _held = count (missionNamespace getVariable ["cti_squads", createHashMap]);
    ["redelivery-probe-buy", "WEST"] call cti_probe_fnc_buySquad;

    private _deadline = diag_tickTime + 60;
    waitUntil {
        count (missionNamespace getVariable ["cti_squads", createHashMap]) > _held
            || { diag_tickTime > _deadline }
    };

    private _squads = ["WEST"] call cti_probe_fnc_squadsOf;
    if (count _squads isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout redelivery_probe_no_squad held=%1", _held];
        diag_log "CTI|redelivery_probe_done";
    };

    // Whichever Squad the world is holding for WEST; which one it is does not
    // matter, only that the world minted a group for it by the real path.
    private _squadId = (keys _squads) # 0;
    private _group = _squads get _squadId;
    private _type = _group getVariable ["cti_squadType", ""];
    private _before = count units _group;

    // How many groups in the whole world answer to this Squad id. One, now.
    private _carrying = {
        params ["_id"];
        count (allGroups select { (_x getVariable ["cti_squad", ""]) isEqualTo _id })
    };
    private _groupsBefore = [_squadId] call _carrying;

    diag_log format ["CTI|redelivery_probe_spawned squad=%1 type=%2 units=%3 groups=%4",
        _squadId, _type, _before, _groupsBefore];

    if (_groupsBefore isNotEqualTo 1) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed redelivery_probe_staging_not_one_group squad=%1 groups=%2",
            _squadId, _groupsBefore];
        diag_log "CTI|redelivery_probe_done";
    };

    // The redelivery: the same document the daemon has been holding since the
    // Purchase, handed to the receiver a second time under the sequence it was
    // first delivered on — which is what the pump does when an ack is lost.
    private _message = createHashMapFromArray [
        ["effect", "squad_spawned"],
        ["side", "WEST"],
        ["args", createHashMapFromArray [
            ["squad", _squadId], ["squad_type", _type], ["size", _before]
        ]]
    ];
    private _verdict = [_message, 1] call cti_fnc_effectApply;
    private _outcome = _verdict getOrDefault ["outcome", ""];

    private _standing = (missionNamespace getVariable ["cti_squads", createHashMap])
        getOrDefault [_squadId, grpNull];
    private _groupsAfter = [_squadId] call _carrying;

    diag_log format ["CTI|redelivery_probe_redelivered squad=%1 outcome=%2 reason=%3 groups=%4 units=%5",
        _squadId, _outcome, _verdict getOrDefault ["reason", ""], _groupsAfter,
        count units _standing];

    // The finding itself: no second group answers to this Squad's id.
    if (_groupsAfter isNotEqualTo 1) then {
        diag_log format ["CTI|FAIL class=assertion_failed redelivery_probe_duplicated_squad squad=%1 groups=%2",
            _squadId, _groupsAfter];
    };

    // The roster still points at the group it pointed at, so nothing was
    // orphaned: a second spawn would have overwritten this entry, which is how
    // the first group's men stopped being anybody's.
    if !(_standing isEqualTo _group) then {
        diag_log format ["CTI|FAIL class=assertion_failed redelivery_probe_roster_rebound squad=%1", _squadId];
    };

    // And the Squad is the Squad it was: no men were added to it either.
    if (count units _standing isNotEqualTo _before) then {
        diag_log format ["CTI|FAIL class=assertion_failed redelivery_probe_men_added squad=%1 before=%2 after=%3",
            _squadId, _before, count units _standing];
    };

    // Applied, not refused. A redelivery the receiver refused would stall the
    // whole outbox behind it or be dead-lettered, and both are worse than the
    // duplicate this replaced.
    if (_outcome isNotEqualTo "applied") then {
        diag_log format ["CTI|FAIL class=assertion_failed redelivery_probe_not_applied squad=%1 outcome=%2 reason=%3",
            _squadId, _outcome, _verdict getOrDefault ["reason", ""]];
    };

    diag_log format ["CTI|redelivery_probe_done squad=%1 groups=%2 units=%3",
        _squadId, _groupsAfter, count units _standing];
};
