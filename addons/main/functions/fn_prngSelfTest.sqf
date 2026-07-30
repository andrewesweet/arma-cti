/*
 * Author: arma-cti
 * Asserts the seeded PRNG adapter against the live engine and returns the
 * failures it found. Empty return means every assertion held.
 *
 * SQF has no offline runtime tier — SQF-VM is rejected as one (ADR-0011) and
 * HEMTT lints are static — so the determinism and engine-caveat assertions in
 * issue #9 can only run in-game. This function is that test body; the harness
 * that runs it is the caller's problem, which keeps it usable from the phase-0
 * spike mission today and from the ADR-0011 acceptance tier later.
 *
 * On the inclusive upper bound: `seed random x` includes x where plain
 * `random x` excludes it, but for a float result the endpoint has measure zero
 * and cannot be caught by sampling. It is therefore pinned two ways that can
 * fail: every draw stays inside [0, max], and every cti_fnc_prngInt draw stays
 * inside [0, count - 1] — the range that a naive `floor` over an included
 * bound would overflow by one.
 *
 * Arguments: none
 *
 * Return Value: failures <ARRAY of STRING> — empty when the adapter is sound
 */

private _failures = [];
private _fail = {
    params ["_name", "_detail"];
    _failures pushBack (format ["%1: %2", _name, _detail]);
};

private _sequence = {
    params ["_seed", "_length"];
    private _stream = [_seed] call cti_fnc_prngNew;
    private _out = [];
    for "_i" from 1 to _length do {
        _out pushBack ([_stream, 1] call cti_fnc_prngNext);
    };
    _out
};

// ---------------------------------------------------------------- determinism
private _first = [12345, 32] call _sequence;
private _second = [12345, 32] call _sequence;
if (_first isNotEqualTo _second) then {
    ["determinism", format ["same seed diverged: %1 vs %2", _first, _second]] call _fail;
};

// A stub that ignored the seed entirely would pass the assertion above.
if ([12345, 32] call _sequence isEqualTo ([12346, 32] call _sequence)) then {
    ["seed_sensitivity", "adjacent seeds produced an identical sequence"] call _fail;
};

// ---------------------------------------------------------------- seed truncation
// The engine truncates towards zero, not by flooring: -0.9 reads as 0, not -1.
if ([7.9, 8] call _sequence isNotEqualTo ([7, 8] call _sequence)) then {
    ["seed_truncation", "7.9 and 7 are different streams"] call _fail;
};
if ([-0.9, 8] call _sequence isNotEqualTo ([0, 8] call _sequence)) then {
    ["seed_truncation_sign", "-0.9 did not truncate towards zero"] call _fail;
};
if ([-0.9, 8] call _sequence isEqualTo ([-1, 8] call _sequence)) then {
    ["seed_truncation_sign", "-0.9 floored to -1 instead of truncating to 0"] call _fail;
};

// ---------------------------------------------------------------- bounds
private _stream = [98765] call cti_fnc_prngNew;
private _outOfRange = 0;
for "_i" from 1 to 512 do {
    private _draw = [_stream, 1] call cti_fnc_prngNext;
    if (_draw < 0 || {_draw > 1}) then { _outOfRange = _outOfRange + 1 };
};
if (_outOfRange > 0) then {
    ["bounds", format ["%1 of 512 draws left [0, 1]", _outOfRange]] call _fail;
};

// ---------------------------------------------------------------- integer draws
private _buckets = [0, 0, 0, 0];
private _samples = 2048;
private _intStream = [24680] call cti_fnc_prngNew;
private _badIndex = 0;
for "_i" from 1 to _samples do {
    private _index = [_intStream, 4] call cti_fnc_prngInt;
    if (_index < 0 || {_index > 3} || {_index != floor _index}) then {
        _badIndex = _badIndex + 1;
    } else {
        _buckets set [_index, (_buckets select _index) + 1];
    };
};
if (_badIndex > 0) then {
    ["int_range", format ["%1 of %2 draws left [0, 3]", _badIndex, _samples]] call _fail;
};
// A wide band: this catches a degenerate or constant generator, not a subtly
// biased one. Statistical quality of the engine's generator is BI's problem.
private _low = _samples * 0.1;
private _high = _samples * 0.4;
if ((_buckets findIf {_x < _low || {_x > _high}}) >= 0) then {
    ["int_distribution", format ["buckets outside 10-40%% of %1: %2", _samples, _buckets]] call _fail;
};

// ---------------------------------------------------------------- serial correlation
// The stream advances by incrementing the seed, so the assumption it rests on
// is that consecutive seeds are not consecutive outputs. Bucket counts cannot
// see that — a rising ramp fills four buckets perfectly evenly — but the
// direction of each step can: independent draws rise about half the time, a
// ramp rises three times in four. Nine standard deviations of slack at n=2048,
// so this fails on a degenerate generator and not on an unlucky seed.
private _rising = 0;
private _walk = [11223] call cti_fnc_prngNew;
private _previous = [_walk, 1] call cti_fnc_prngNext;
for "_i" from 1 to _samples do {
    private _draw = [_walk, 1] call cti_fnc_prngNext;
    if (_draw > _previous) then { _rising = _rising + 1 };
    _previous = _draw;
};
private _risingShare = _rising / _samples;
if (_risingShare < 0.4 || {_risingShare > 0.6}) then {
    ["serial_correlation", format ["%1 of %2 draws rose", _rising, _samples]] call _fail;
};

// ---------------------------------------------------------------- resume
// Phase 2 has to restore a stream from a snapshot mid-campaign, so a stream
// rebuilt at draw N must continue the same sequence rather than restart it.
private _continuous = [13579] call cti_fnc_prngNew;
for "_i" from 1 to 10 do { [_continuous, 1] call cti_fnc_prngNext };
private _tail = [];
for "_i" from 1 to 8 do { _tail pushBack ([_continuous, 1] call cti_fnc_prngNext) };

private _resumed = [13579, 10] call cti_fnc_prngNew;
private _resumedTail = [];
for "_i" from 1 to 8 do { _resumedTail pushBack ([_resumed, 1] call cti_fnc_prngNext) };

if (_tail isNotEqualTo _resumedTail) then {
    ["resume", format ["resumed stream diverged: %1 vs %2", _tail, _resumedTail]] call _fail;
};

_failures
