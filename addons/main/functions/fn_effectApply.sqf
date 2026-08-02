/*
 * Author: arma-cti
 * Carries out one effect the daemon has accepted. Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * one caller is the effect pump, which `missions/cti.Stratis/initServer.sqf`
 * starts on the server and nowhere else (#118, ADR-0041).
 *
 * The daemon owns the rules and the game owns the geometry (ADR-0012), which is
 * why an effect says "a rifle Squad for WEST" and never where it goes: the
 * manifest already knows where each side's Base is, and the daemon has no
 * business holding map coordinates.
 *
 * ## Why the answer is a verdict rather than a yes/no
 *
 * The pump acknowledges through a high-water mark, so a "no" holds up every
 * effect behind it. A bare `false` gave the pump no way to tell the two kinds of
 * no apart, and it treated both as the recoverable one: an effect this function
 * can *never* carry out — an effect name the addon does not know, a side that is
 * not playing, a side with no Base — came back on every 2 s poll forever and
 * nothing behind it was ever applied (#100). The Campaign then stops progressing
 * with both sides' Funds already spent, and says nothing.
 *
 * So a refusal is classified at the point that knows: `refused` is permanent —
 * the pump dead-letters it and moves on — and `deferred` is worth another poll.
 * Nothing here returns `deferred` today, and that is a statement rather than an
 * oversight: every way this function can fail is a fact about the effect or the
 * world's shape that the next poll will meet unchanged. The word exists so the
 * first genuinely transient failure has somewhere to go that is not an unbounded
 * retry, and so that the choice has to be made deliberately.
 *
 * Arguments:
 * 0: the effect <HASHMAP> — `effect`, `side`, `args`
 *
 * Return Value: <HASHMAP> the verdict — `outcome` one of "applied", "refused"
 * (permanent: acknowledge and dead-letter it) or "deferred" (transient: leave it
 * unacknowledged and try again), and `reason`, the word its FAIL line carries.
 */
params [["_effect", createHashMap, [createHashMap]]];

// The verdict, in the vocabulary above. `_refused` is every failure below; the
// reason is the same word the accompanying FAIL line names.
private _verdict = {
    params [["_outcome", "", [""]], ["_reason", "", [""]]];
    createHashMapFromArray [["outcome", _outcome], ["reason", _reason]]
};

private _name = _effect getOrDefault ["effect", ""];
private _sideName = _effect getOrDefault ["side", ""];
private _args = _effect getOrDefault ["args", createHashMap];

// An Objective changing hands is announced as an effect and also reflected in
// every observe reply. The reply is what repaints the map; this exists so a
// capture is an event something can react to, not only a state to poll.
if (_name isEqualTo "objective_captured") exitWith {
    diag_log format ["CTI|effect_applied effect=%1 side=%2 objective=%3",
        _name, _sideName, _args getOrDefault ["objective", "?"]];
    ["applied"] call _verdict
};

// The two delegating effects still answer in booleans, because "settled" is the
// whole of what their callers need from them and neither has a failure the next
// poll would meet differently: an unreadable `campaign_won` is unreadable
// forever. So false becomes a permanent refusal here, at the one place that has
// to decide.
//
// The last effect any Campaign produces (#35). The daemon decided the Campaign
// was over; what is left is the world's half of it.
if (_name isEqualTo "campaign_won") exitWith {
    if ([_sideName, _args] call cti_fnc_campaignEnd) then { ["applied"] call _verdict }
    else { ["refused", "campaign_end_refused"] call _verdict }
};

if (_name isEqualTo "order_issued") exitWith {
    private _settled = [_args getOrDefault ["squad", ""],
        _args getOrDefault ["order", ""],
        _args getOrDefault ["place", ""]] call cti_fnc_orderApply;
    if (_settled) then { ["applied"] call _verdict }
    else { ["refused", "order_apply_refused"] call _verdict }
};

// A daemon and an addon out of step after a partial upgrade. Permanent: the same
// name arrives with the same meaning on every poll, and no amount of waiting
// teaches this addon what it is.
if !(_name in ["squad_spawned", "squad_reinforced"]) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed unknown_effect=%1", _name];
    ["refused", "unknown_effect"] call _verdict
};

private _side = switch (toUpper _sideName) do {
    case "WEST": { west };
    case "EAST": { east };
    default { sideUnknown };
};
if (_side isEqualTo sideUnknown) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed effect_unknown_side=%1", _sideName];
    ["refused", "effect_unknown_side"] call _verdict
};

// Through the index cti_fnc_worldInit derives beside the map (#109).
private _base = (missionNamespace getVariable ["cti_basesBySide", createHashMap])
    getOrDefault [toUpper _sideName, createHashMap];

if (count _base isEqualTo 0) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed no_base_for_side=%1", _sideName];
    // A map authors its Bases; a side without one is a world built wrongly, and
    // it will be built the same way on the next poll.
    ["refused", "no_base_for_side"] call _verdict
};

(_base get "position") params ["_east", "_north"];
private _size = _args getOrDefault ["size", 8];
private _squadId = _args getOrDefault ["squad", ""];

// What a Squad is made of is authored data, not a literal here (#79, #82).
// This function used to spawn `_size` copies of one of two hardcoded
// classnames and ignore the `squad_type` the Commander had paid for entirely —
// a design decision living in the outermost layer, invisible to the schema
// pipeline and unreachable by any test that does not boot Arma. It read as
// finished code while being a placeholder.
//
// The roster comes from `config/economy.json` beside the price it was set
// against, exported into `command-schema.json` by the same tool that exports
// the Command catalogue, and read here through cti_fnc_commandSchema — ADR-0017's
// route: ship the authored file, generate only what has none. `just check`
// fails a stale export as `schema_stale`, so the men this spawns cannot drift
// from the table the daemon charged for them.
//
// The roster is ordered and one entry per man, which is what lets a Reinforce
// know *which* men are missing: slot 0 is the man the Squad is built around and
// attrition is accounted from the rear. Today every slot of both rosters is the
// same classname, so that ordering is unobservable — the structure is the
// point, and the values are a **playtest-tuned placeholder** in ADR-0020's
// sense, to be filled by #6 under the human's feel gate.
private _rosterOf = {
    params [["_type", "", [""]]];
    private _entry = ((call cti_fnc_commandSchema) getOrDefault ["squads", createHashMap])
        getOrDefault [_type, createHashMap];
    if !(_entry isEqualType createHashMap) exitWith { [] };
    private _composition = _entry getOrDefault ["composition", createHashMap];
    if !(_composition isEqualType createHashMap) exitWith { [] };
    _composition getOrDefault [toUpper _sideName, []]
};

// A type the exported table does not describe. Permanent, and classified
// `schema_stale` rather than `assertion_failed` because the daemon selling a
// Squad this addon has no roster for is a daemon and an addon out of step —
// the copy on disk is stale, and the response is to regenerate it, not to
// argue with the effect. The next poll reads the same cached schema.
private _noRoster = {
    params [["_type", "", [""]]];
    diag_log format ["CTI|FAIL class=schema_stale no_composition_for squad_type=%1 side=%2",
        _type, _sideName];
    ["refused", "no_composition_for_squad_type"] call _verdict
};

// Replacements for a Squad that is already standing (ADR-0040). The men arrive
// at the Base because that is where the rules made the Squad be before they
// accepted the Reinforce, and they join the group that answers to the id — a
// second group carrying the same id would be a Squad the world holds twice and
// the daemon counts once.
//
// `size` is the strength to bring it back *to*, and how many that is comes from
// counting what is standing here rather than from anything the daemon said: the
// judgement was made a poll ago and a man can have died since. A Squad already
// at strength therefore spawns nobody and is still applied — there is nothing
// left to do and nothing a later poll would do differently.
if (_name isEqualTo "squad_reinforced") exitWith {
    private _group = (missionNamespace getVariable ["cti_squads", createHashMap])
        getOrDefault [_squadId, grpNull];
    if (isNull _group) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed reinforce_unknown_squad=%1", _squadId];
        // Permanent: the world has no group by that id and will not grow one.
        // A Squad the world has lost is one the daemon is about to be told
        // about, and refilling it would put men on the map answering to an id
        // the roster is removing.
        ["refused", "reinforce_unknown_squad"] call _verdict
    };

    // Which Squad this is comes from the world, not from the effect: a
    // `squad_reinforced` carries `squad` and `size` and has never carried the
    // type (`commands.EFFECTS`). The world already records the id on the group
    // it minted; recording the type alongside it at spawn is the same gesture,
    // and it keeps the roster lookup out of the wire. A Squad standing without
    // one is a Squad this addon did not spawn.
    private _squadType = _group getVariable ["cti_squadType", ""];
    private _roster = [_squadType] call _rosterOf;
    if (count _roster isEqualTo 0) exitWith { [_squadType] call _noRoster };

    private _standing = count units _group;
    private _owed = _size - _standing;

    // Spawned into a group of this machine's own and joined across, rather than
    // created into the Squad directly. A Squad a player leads is local to that
    // player's machine — "an AI group with a player-leader will be local to the
    // player's computer" (topics/Multiplayer_Scripting.wiki, vendored) — and
    // `createUnit` takes local arguments (commands/createUnit.wiki), so
    // spawning straight into the target would be the server writing into a
    // group it does not own. That is the Squad Reinforce exists for: the second
    // principal is a squad leader, and the Squad he leads is exactly the one
    // this cannot reach the direct way. `joinSilent` is global in both argument
    // and effect (commands/joinSilent.wiki), so the join is locality-blind.
    //
    // The staging group deletes itself when the last man leaves it, which is
    // the same breath: `createGroup`'s second element is `deleteWhenEmpty`.
    //
    // The replacements are the roster's rear slots — the men a Squad down to
    // `_standing` is missing — rather than `_owed` copies of one classname.
    // Clamped into the roster because `size` arrives from the daemon while the
    // roster is authored: they agree by validation, and if an export ever went
    // stale the last slot repeats rather than the loop reading off the end.
    if (_owed > 0) then {
        private _staging = createGroup [_side, true];
        private _last = count _roster - 1;
        for "_i" from _standing to (_size - 1) do {
            private _class = _roster select ((_i max 0) min _last);
            _staging createUnit [_class, [_east, _north, 0], [], 30, "FORM"];
        };
        (units _staging) joinSilent _group;
    };

    diag_log format ["CTI|effect_applied effect=%1 side=%2 squad=%3 standing=%4 added=%5 units=%6 base=%7",
        _name, _sideName, _squadId, _standing, _owed max 0, count units _group, _base get "id"];

    // No Order is applied here, unlike a spawn. The group already carries the
    // waypoints its standing Order built and the men have joined *it*, so they
    // are under that Order by being in the Squad — which is what a replacement
    // arriving into a Squad should mean. Re-applying it would rebuild the
    // waypoint list of a Squad that is already carrying out its Order, and a
    // Reinforce is not a re-Order.
    ["applied"] call _verdict
};

// The purchased type is what decides the men, so it is read before any of them
// exist: a Squad with no roster must refuse before it has put a group on the
// map, or the refusal leaves the world holding half an effect.
private _squadType = _args getOrDefault ["squad_type", ""];
private _roster = [_squadType] call _rosterOf;
if (count _roster isEqualTo 0) exitWith { [_squadType] call _noRoster };

// One man per roster slot. The count comes from the roster rather than from the
// effect's `size` because the roster *is* the composition — the daemon's `size`
// is what it priced, and `economy._check_composition` is what holds the two
// equal.
private _group = createGroup [_side, true];
{
    _group createUnit [_x, [_east, _north, 0], [], 30, "FORM"];
} forEach _roster;

// The daemon minted the id; the world records which group answers to it, so an
// Order naming that Squad has something to reach (#14). The type is recorded
// with it because a Reinforce arrives without one and has to know what to build.
(missionNamespace getVariable ["cti_squads", createHashMap]) set [_squadId, _group];
_group setVariable ["cti_squad", _squadId, true];
_group setVariable ["cti_squadType", _squadType, true];

diag_log format ["CTI|effect_applied effect=%1 side=%2 squad=%3 squad_type=%4 units=%5 base=%6",
    _name, _sideName, _squadId, _squadType, count units _group, _base get "id"];

// A new Squad is in Reserve until it is told otherwise, which is the daemon's
// view of it too. Applying it here rather than assuming it means a Squad
// standing at its Base is under an Order like any other, not a special case.
//
// The Squad is spawned either way: a Reserve Order that would not settle must
// not put the men back in the box, so this is reported and not retried. Retrying
// it would spawn the Squad a second time.
if ([_squadId, "reserve", ""] call cti_fnc_orderApply) exitWith { ["applied"] call _verdict };
diag_log format ["CTI|FAIL class=assertion_failed squad_spawned_without_reserve squad=%1", _squadId];
["refused", "squad_spawned_without_reserve"] call _verdict
