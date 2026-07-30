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
 * match the schema. Callers must treat empty as "do not send".
 */
params [["_name", "", [""]], ["_arguments", [], [[]]]];

private _schema = call cti_fnc_commandSchema;
private _catalogue = _schema get "commands";
private _required = _catalogue getOrDefault [_name, []];

if (isNil "_required" || {!(_name in _catalogue)}) exitWith {
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
