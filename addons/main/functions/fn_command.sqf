/*
 * Author: arma-cti
 * Builds a Command in the one wire format both Commanders use (ADR-0012).
 *
 * The catalogue this validates against is generated from the same Python
 * source the daemon validates with, so a Command the game can build and a
 * Command the daemon accepts cannot drift apart.
 *
 * The side is deliberately not a parameter. The gateway stamps it server-side
 * from the caller's own identity; anything a client put there would be
 * overwritten, so offering the field would only invite the belief that it
 * means something.
 *
 * Arguments:
 * 0: Command name <STRING>
 * 1: arguments <ARRAY> of [name, value] pairs (optional, default none)
 *
 * Return Value: the Command <HASHMAP>, or an empty HASHMAP when it does not
 * match the schema, or when there is no schema to match it against. Callers
 * must treat empty as "do not send".
 */
params [["_name", "", [""]], ["_arguments", [], [[]]]];

private _schema = call cti_fnc_commandSchema;
// cti_fnc_commandSchema answers an empty HashMap when the export is missing or
// unreadable and says in as many words that callers must treat that as fatal.
// This one used to read `_schema get "commands"` straight through it, so a
// missing export reached the next line as nil and the Command was refused by a
// raw script error rather than by the documented refusal — in a function whose
// whole contract is "empty HashMap means do not send". The same guard as
// cti_fnc_mapVerbs' and cti_fnc_commanderAssign's, typed the same way (#80).
//
// Asked as "is the catalogue there" rather than "is the schema empty", which is
// one condition covering both ways it can be absent: no export at all, and an
// export that parsed into something without a catalogue in it. The second is
// the one a probe can stage, through the documented cache.
if !("commands" in _schema) exitWith {
    diag_log format ["CTI|FAIL class=schema_stale command_built_without_schema=%1 schema_keys=%2",
        _name, count _schema];
    createHashMap
};

private _catalogue = _schema get "commands";
private _required = _catalogue getOrDefault [_name, []];

// `getOrDefault` answers the default rather than nil, so the `isNil "_required"`
// arm this used to carry could not fire; membership is the whole question.
if !(_name in _catalogue) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed unknown_command_built=%1", _name];
    createHashMap
};

private _args = createHashMapFromArray _arguments;
private _missing = _required select { !(_x in _args) };
if (_missing isNotEqualTo []) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed command=%1 missing_args=%2", _name, _missing];
    createHashMap
};

// `side` is a placeholder the gateway overwrites. It is present so the payload
// shape is complete before it leaves the client, not because it is trusted.
createHashMapFromArray [
    ["command", _name],
    ["side", ""],
    ["args", _args]
]
