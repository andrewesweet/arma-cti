/*
 * Author: arma-cti
 * Issues one Squad the weakest transport that seats it, at its own Base, and
 * takes away the one it had. Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * one caller is cti_fnc_transportWatch, which `missions/cti.Stratis/initServer.sqf`
 * starts on the server and nowhere else (#118, ADR-0041).
 *
 * The human's ruling of 2026-08-03 (#170, ADR-0059): "squad leaders (or AI
 * commander on behalf of squad leaders) should be able to access the weakest,
 * most basic form of motorised transport sufficient for their squad size for
 * free at all times". Free means no Funds move, so nothing here is a Command and
 * nothing here crosses the wire — the daemon owns the rules and the game owns
 * the geometry (ADR-0012), and a vehicle that is judged by no rule is geometry.
 *
 * ## Sized to the Squad it was bought at, not to the men standing
 *
 * `cti_squadSize` is the roster length cti_fnc_effectApply recorded at spawn,
 * which is the strength a Reinforce brings the Squad back to. A vehicle sized to
 * today's casualties is one seat short tomorrow, and the Squad that walks is the
 * one that just got its men back.
 *
 * ## One per Squad, and the old one goes
 *
 * The Squad's transport is recorded on its group. A Squad standing at its Base
 * with its transport somewhere else — abandoned at an Objective, or wrecked —
 * would otherwise have to walk back to it, which is the yomping the ruling
 * exists to end. So a new one is issued and the old one is disowned and deleted.
 *
 * Deleted only when nobody is in it. `commands/deleteVehicle.wiki` is explicit:
 * "Do not use this command for a vehicle's crew members as it may lead to all
 * sorts of bugs and ghost objects left on the map". A crewed one is released
 * instead — said out loud, and left on the map as ordinary abandoned kit. It
 * cannot be one of this Squad's own men: the Squad is standing at its Base,
 * which is what earned it the new vehicle, so anyone in the old one is somebody
 * else. `leaveVehicle` is what stops the group owning it either way, and
 * `commands/leaveVehicle.wiki` says it "will not force a player to exit from a
 * vehicle", so releasing one does not throw a person out at speed.
 *
 * ## Who may mount it: anybody who walks up to it
 *
 * There is no side- or group-scoped vehicle lock in the engine — `lock` and
 * `setVehicleLock` distinguish player from AI subordinate and nothing else, and
 * `commands/lock.wiki` says the lock "will not stop player getting into or out
 * of vehicle via script commands". So ownership here is bookkeeping, not
 * permission: it says which vehicle to replace, never who may drive.
 *
 * ## And how the AI comes to use it
 *
 * `groupName addVehicle vehicleName` puts the truck in the group's own vehicle
 * pool — the command's own words are "adds a specified vehicle for use by a
 * specified AI led group" — and `topics/Waypoints.wiki` states the consequence
 * for the Move waypoint cti_fnc_orderApply already lays: "Groups will
 * automatically board any transport vehicles they own if the next waypoint is
 * far enough away". So the AI Commander's Squads ride with no waypoint change,
 * no Order vocabulary change and nothing new on the wire.
 *
 * `addVehicle` and `leaveVehicle` are both `arg= local` (vendored wiki), and an
 * AI group with a player leader is local to that player's machine
 * (`topics/Multiplayer_Scripting.wiki`), so both are asked only where the group
 * is local. That is not a gap being papered over: `topics/AI_Group_Vehicle_Management.wiki`
 * records that the whole mechanism "has no effect on AI lead by a player Group
 * Leader" anyway, and a player squad leader does not need it — he drives. The
 * ruling's two principals get the two halves they can each use.
 *
 * Arguments:
 * 0: the Squad's group <GROUP>
 * 1: the Squad id <STRING>
 * 2: the Squad's own Base, as the manifest carries it <HASHMAP>
 * 3: the transport ladder <ARRAY> — cti_fnc_transportCatalogue's answer
 *
 * Return Value: <OBJECT> the vehicle issued, or objNull when none could be.
 */

params [
    ["_group", grpNull, [grpNull]],
    ["_squadId", "", [""]],
    ["_base", createHashMap, [createHashMap]],
    ["_fleet", [], [[]]]
];

// The strength the Squad was bought at. Nought means a group this addon did not
// spawn, or one from before the size was recorded; the men standing are then the
// only honest answer, and it is said out loud rather than assumed.
private _men = _group getVariable ["cti_squadSize", 0];
if (_men <= 0) then {
    _men = count units _group;
    diag_log format ["CTI|transport_size_unrecorded squad=%1 standing=%2", _squadId, _men];
};

// Weakest first is the authored order, so the first rung that seats the Squad is
// the most basic one that will (`cti_daemon.motorpool` holds the file to that
// order, so this does not have to sort).
private _rung = createHashMap;
{
    if ((_x getOrDefault ["seats", 0]) >= _men) exitWith { _rung = _x };
} forEach _fleet;

if (count _rung isEqualTo 0) exitWith {
    // The Python gate (`motorpool.capacity_covers`) fails `just unit` on a
    // ladder that seats no Squad the economy sells, so reaching this means the
    // shipped catalogue and the shipped economy disagree on the machine playing.
    diag_log format ["CTI|FAIL class=assertion_failed transport_no_rung_for squad=%1 men=%2 rungs=%3",
        _squadId, _men, count _fleet];
    objNull
};

private _class = _rung getOrDefault ["vehicle", ""];
(_base get "position") params ["_east", "_north"];

// `"NONE"` is the engine's own "look for suitable empty position near given
// position before placing vehicle there" (commands/createVehicle.wiki), and the
// placement radius is what stops a second truck landing on the first. Well
// inside the 150 m that counts as standing in a Base (cti_fnc_placeRadius), so a
// vehicle issued here is at the Place the Squad is at.
private _vehicle = createVehicle [_class, [_east, _north, 0], [], 30, "NONE"];
if (isNull _vehicle) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed transport_not_created squad=%1 class=%2 base=%3",
        _squadId, _class, _base get "id"];
    objNull
};

// What the engine says the vehicle seats, against what the file says. `fullCrew`
// with `includeEmpty` returns every position including the empty ones
// (commands/fullCrew.wiki), which is the only documented way to count seats at
// runtime — `emptyPositions "Cargo"` would answer for cargo alone. A vehicle that
// no longer carries the Squad is the Arma build having moved under an authored
// number, which is `engine_drift` by CLAUDE.md's table and not ours to fix.
private _seats = count (fullCrew [_vehicle, "", true]);
if (_seats < _men) exitWith {
    diag_log format ["CTI|FAIL class=engine_drift transport_seats_short squad=%1 class=%2 authored=%3 actual=%4 men=%5",
        _squadId, _class, _rung getOrDefault ["seats", 0], _seats, _men];
    deleteVehicle _vehicle;
    objNull
};

private _previous = _group getVariable ["cti_transport", objNull];

_group setVariable ["cti_transport", _vehicle, true];
// Which Squad this was issued to, on the vehicle itself: the group knows its
// truck, and this is the reading back the other way, which is what a probe and a
// later playtest have to be able to ask of a vehicle standing on the map.
_vehicle setVariable ["cti_transportOf", _squadId, true];

// The group's own vehicle pool, so the engine boards them for a distant Move.
// Only where the group is local, which on a dedicated server is every Squad
// except one a player is leading (ADR-0039 keeps Squads on the server; the
// engine moves a player-led one by itself).
private _mine = local _group;
if (_mine) then {
    _group addVehicle _vehicle;
};

if (!isNull _previous) then {
    if (_mine) then { _group leaveVehicle _previous };
    if (crew _previous isEqualTo []) then {
        deleteVehicle _previous;
    } else {
        diag_log format ["CTI|transport_released squad=%1 crew=%2", _squadId, count crew _previous];
    };
};

diag_log format ["CTI|transport_issued squad=%1 rung=%2 class=%3 men=%4 seats=%5 base=%6 pooled=%7 replaced=%8",
    _squadId, _rung getOrDefault ["id", "?"], _class, _men, _seats, _base get "id", _mine,
    !isNull _previous];

_vehicle
