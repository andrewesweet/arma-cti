/*
 * Author: arma-cti
 * What the map UI can say, and which key says it. Runs on the client.
 *
 * Read out of the Command Port schema rather than written down here, so the
 * vocabulary the UI offers is the port's vocabulary exactly. If the port grows
 * an Order the UI cannot express, or the UI offers one the port does not judge,
 * the wire format has forked and the guarantee #18 exists for is gone — so the
 * only way to add a verb to this menu is to add it to the schema both
 * Commanders are built from.
 *
 * Which key carries which verb is a **playtest-tuned placeholder** in the sense
 * ADR-0020 gives the word: the number row in schema order, Orders first and
 * Purchases after them. It is the crudest binding that needs no dialog resource
 * and no config class, and it is meant to be replaced wholesale in Phase 4.
 * What is not a placeholder is that the list is derived, not authored.
 *
 * Arguments: none
 *
 * Return Value: <ARRAY> of [key <NUMBER>, kind <STRING>, name <STRING>,
 * label <STRING>], where kind is "order" or "purchase" and name is the word the
 * port judges.
 */
private _schema = call cti_fnc_commandSchema;
if (count _schema isEqualTo 0) exitWith { [] };

private _verbs = [];

// ---- playtest-tuned placeholder (ADR-0020) ------------------------------
// DIK 2 is the "1" key and the number row runs up from there, so the nth verb
// is the nth digit. Ten verbs would run off the row; the schema has six.
private _key = 2;

{
    _verbs pushBack [
        _key,
        "order",
        _x,
        // The port's own word, with the capital CONTEXT.md gives the Order kind.
        toUpper (_x select [0, 1]) + (_x select [1, count _x])
    ];
    _key = _key + 1;
} forEach (_schema getOrDefault ["orders", []]);

private _squads = _schema getOrDefault ["squads", createHashMap];
private _types = keys _squads;
_types sort true;
{
    private _sold = _squads get _x;
    _verbs pushBack [
        _key,
        "purchase",
        _x,
        format ["%1 (%2)", _sold getOrDefault ["display_name", _x], _sold getOrDefault ["price", "?"]]
    ];
    _key = _key + 1;
} forEach _types;

_verbs
