/*
 * Author: arma-cti
 * Uniform integer draw in [0, _count - 1] — the range array indexing wants.
 *
 * Built on a [0, 1] draw rather than `floor (stream random _count)` because the
 * engine's upper bound is *included*: flooring a 0..count draw yields `_count`
 * itself when the draw lands on the endpoint, one past the last index. The
 * `min (_count - 1)` closes that hole in the one place it can be closed.
 *
 * Arguments:
 * 0: stream <ARRAY> — advanced in place
 * 1: number of distinct values <NUMBER>
 *
 * Return Value: <NUMBER> integer from 0 to _count - 1
 */
params [["_stream", [0, 0], [[]], 2], ["_count", 1, [0]]];

if (_count <= 1) exitWith { 0 };

private _draw = [_stream, 1] call cti_fnc_prngNext;

(floor (_draw * _count)) min (_count - 1)
