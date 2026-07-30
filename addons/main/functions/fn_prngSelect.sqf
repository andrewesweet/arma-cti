/*
 * Author: arma-cti
 * Seeded equivalent of `selectRandom`: picks one element of an array through
 * the stream, so the choice replays identically from the same seed.
 *
 * Arguments:
 * 0: stream <ARRAY> — advanced in place
 * 1: candidates <ARRAY>
 *
 * Return Value: one element of the array, or <NIL> when it is empty
 */
params [["_stream", [0, 0], [[]], 2], ["_candidates", [], [[]]]];

private _count = count _candidates;
if (_count isEqualTo 0) exitWith { nil };

_candidates select ([_stream, _count] call cti_fnc_prngInt)
