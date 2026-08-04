/*
 * Author: arma-cti
 * The side vocabulary: name↔engine-side translation, both directions, and the
 * enemy-of relation. The one place in the addon that pairs the daemon's side
 * names with the engine's side objects (#149).
 *
 * The names themselves are the daemon's, exported in `command-schema.json`
 * `sides` and read through cti_fnc_commandSchema. The addon used to restate
 * them by hand five times — two switches, a hand-built enemy-of table, a
 * membership literal and a `str` respelling — and the literal was fail-silent:
 * presence on a side it did not list was simply never reported, and nothing
 * asserted on the gap. The engine objects (`west`, `east`) are the one half
 * SQF must own, because no export can carry an engine value; that pairing
 * lives here and nowhere else.
 *
 * Derived once per machine and cached, like the schema it reads: the sampled
 * paths ask for this every sweep.
 *
 * Arguments: none
 *
 * Return Value: <HASHMAP> with three entries, each with a named consumer and
 * all derived from the schema's `sides` plus the pairing above:
 * - "sideByName": side name <STRING> -> <SIDE>
 * - "nameBySide": <SIDE> -> side name <STRING>
 * - "enemyByName": side name <STRING> -> the enemy's <SIDE>
 * Empty when the vocabulary cannot be built truthfully; a consumer's miss path
 * must stay a refusal or an absence, never a guess.
 */
private _cached = missionNamespace getVariable ["cti_sideVocabularyCache", createHashMap];
if (count _cached > 0) exitWith { _cached };

// The engine half of the pairing. Its keys must cover the schema's `sides`;
// the guard below refuses the whole vocabulary rather than translating in
// part, because a partial translation is the fail-silent shape this exists to
// remove.
private _engineHalf = createHashMapFromArray [["WEST", west], ["EAST", east]];

private _names = (call cti_fnc_commandSchema) getOrDefault ["sides", []];
if (count _names isEqualTo 0) exitWith {
    // cti_fnc_commandSchema has already said why when the export is missing or
    // unreadable; a schema that parsed but carries no sides is the same
    // staleness, and the response is the same regenerate.
    diag_log "CTI|FAIL class=schema_stale side_vocabulary_no_sides";
    createHashMap
};

private _unknown = _names select { !(_x in _engineHalf) };
if (_unknown isNotEqualTo [] || { count _names isNotEqualTo 2 }) exitWith {
    // A side the daemon plays that this addon holds no engine object for, or a
    // side count the enemy-of relation cannot be derived from — the Campaign
    // is one side against one other. Either way the addon is behind the
    // daemon, and the fix is code here, not a regenerate.
    diag_log format ["CTI|FAIL class=assertion_failed side_vocabulary_unbuildable sides=%1 unknown=%2",
        _names, _unknown];
    createHashMap
};

private _sideByName = createHashMap;
private _nameBySide = createHashMap;
{
    private _side = _engineHalf get _x;
    _sideByName set [_x, _side];
    _nameBySide set [_side, _x];
} forEach _names;

// Exactly two sides, so the enemy of each is the other.
private _enemyByName = createHashMap;
{
    _enemyByName set [_x, _sideByName get (_names select (1 - _forEachIndex))];
} forEach _names;

private _vocabulary = createHashMapFromArray [
    ["sideByName", _sideByName],
    ["nameBySide", _nameBySide],
    ["enemyByName", _enemyByName]
];
// Only a vocabulary that built is cached, for cti_fnc_commandSchema's reason:
// an empty one would pin the failure and hide an export that arrived late.
missionNamespace setVariable ["cti_sideVocabularyCache", _vocabulary];
_vocabulary
