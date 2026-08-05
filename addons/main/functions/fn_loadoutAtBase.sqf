/*
 * Author: arma-cti
 * Whether a player is standing in his own side's Base. Runs anywhere.
 *
 * The human's ruling of 2026-08-04 makes loadout customisation a Base activity
 * (ADR-0056), consistent with restock being free at Base and nowhere else
 * (ADR-0040's pinned line). This is that rule, once, and it is asked on two
 * machines: the server grants a kit through it, and a client shows its menu
 * action through it. Two readings of "at Base" would be two answers, and the
 * one a player could see would be the wrong one.
 *
 * `cti_fnc_placeOf` is the reading, not a distance of this function's own: a
 * Squad's reported position is derived that way and the port's own Reinforce
 * rule compares the result to a Base id, so "at Base" means here exactly what
 * it means there. The manifest indexes it reads are broadcast by
 * `cti_fnc_worldInit`, which is what lets a client ask the same question.
 *
 * Arguments:
 * 0: the player <OBJECT>
 *
 * Return Value: <BOOL>. False for a dead man, for a machine with no player unit
 * and for a side with no Base on this map — none of which is at a Base.
 */
params [["_unit", objNull, [objNull]]];

if (isNull _unit || {!alive _unit}) exitWith { false };

private _base = (missionNamespace getVariable ["cti_basesBySide", createHashMap])
    getOrDefault [str side _unit, createHashMap];
private _id = _base getOrDefault ["id", ""];
if (_id isEqualTo "") exitWith { false };

private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _at = [
    getPosATL _unit,
    _map getOrDefault ["objectives", []],
    _map getOrDefault ["bases", []]
] call cti_fnc_placeOf;

_at isEqualTo _id
