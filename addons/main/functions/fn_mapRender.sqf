/*
 * Author: arma-cti
 * Draws this Commander's Observation, and nothing else. Runs on the client.
 *
 * Interior to the client's own call graph, so it carries no locality guard:
 * every path into it comes from cti_fnc_mapObservation, cti_fnc_portReply,
 * cti_fnc_mapCommander or cti_fnc_mapIssue, and the first two are the guarded
 * doors the server pushes through (#118, ADR-0041).
 *
 * The rule is the whole design: it renders what the Observation gives this side
 * and never reaches for anything the world happens to know locally. The engine
 * would happily tell this machine where every enemy unit is; the Commander's
 * picture says a company was seen at Agia Marina ninety seconds ago (#28), and
 * that is what gets drawn. A UI reading the world instead of the Observation
 * would hand the human perfect information while the AI plans on a projection,
 * which is precisely the asymmetry ADR-0012 rejects.
 *
 * Local markers and a hint, because #18 wants the path proved rather than
 * presented. Every visual choice here is a **playtest-tuned placeholder** in the
 * sense ADR-0020 gives the word.
 *
 * Ownership markers are not drawn here: the server already paints those
 * globally from the public picture, and a second set drawn from a Commander's
 * copy would be two answers to who holds a town.
 *
 * Arguments: none
 *
 * Return Value: none
 */
// UI readiness, which is a different question from machine role and is the only
// one left here (#114, #118): `cti_uiSide` is set by cti_fnc_mapObservation when
// the first Observation arrives, so a client that has not had one yet has
// nothing to render.
if (isNil "cti_uiSide") exitWith {};

private _view = missionNamespace getVariable ["cti_view", createHashMap];

// Every marker this UI drew last time. Deleted and redrawn wholesale: a Squad
// that has died or a Contact that has been cleared has to leave the map, and
// tracking what changed would be presentation logic in a placeholder.
{ deleteMarkerLocal _x } forEach (missionNamespace getVariable ["cti_uiMarkers", []]);
private _drawn = [];

private _own = ([cti_uiSide] call cti_fnc_sideMarkerColour);

{
    private _id = _x getOrDefault ["id", ""];
    private _at = [_x getOrDefault ["at", ""]] call cti_fnc_placePosition;
    if (_at isNotEqualTo []) then {
        private _marker = createMarkerLocal [format ["cti_ui_squad_%1", _id], _at];
        _marker setMarkerTypeLocal "mil_triangle";
        _marker setMarkerColorLocal _own;
        _marker setMarkerTextLocal format ["%1 %2/%3 — %4 %5",
            _id,
            _x getOrDefault ["type", "?"],
            _x getOrDefault ["size", "?"],
            _x getOrDefault ["order", "?"],
            _x getOrDefault ["place", ""]];
        _drawn pushBack _marker;
    };
} forEach (_view getOrDefault ["squads", []]);

// A Contact is what was seen, never who it was: no Squad id, no Order, no side
// beyond "the other one" (CONTEXT.md). The marker says the same and no more.
{
    private _place = _x getOrDefault ["at", ""];
    private _at = [_place] call cti_fnc_placePosition;
    if (_at isNotEqualTo []) then {
        private _marker = createMarkerLocal [format ["cti_ui_contact_%1", _place], _at];
        _marker setMarkerTypeLocal "mil_warning";
        _marker setMarkerColorLocal "ColorRed";
        _marker setMarkerTextLocal format ["%1 %2%3 — seen %4s ago",
            _x getOrDefault ["echelon", "?"],
            _x getOrDefault ["posture", "?"],
            if ((_x getOrDefault ["assets", []]) isEqualTo []) then { "" }
                else { format [" (%1)", (_x getOrDefault ["assets", []]) joinString ", "] },
            round (_x getOrDefault ["age", 0])];
        _drawn pushBack _marker;
    };
} forEach (_view getOrDefault ["contacts", []]);

missionNamespace setVariable ["cti_uiMarkers", _drawn];

// ---- playtest-tuned placeholder (ADR-0020) ------------------------------
// A hint is the crudest surface that can hold a legend, a selection and a
// judgement at once, and it costs no dialog resource to throw away in Phase 4.
private _owners = _view getOrDefault ["owners", createHashMap];
private _place = if (cti_uiPlace isEqualTo "") then { "—" } else {
    format ["%1 (%2)", cti_uiPlace, _owners getOrDefault [cti_uiPlace, "Base"]]
};

private _squad = "— [Tab] to pick";
{
    if ((_x getOrDefault ["id", ""]) isEqualTo cti_uiSquad) exitWith {
        _squad = format ["%1 %2/%3 — %4 %5",
            cti_uiSquad,
            _x getOrDefault ["type", "?"],
            _x getOrDefault ["size", "?"],
            _x getOrDefault ["order", "?"],
            _x getOrDefault ["place", ""]];
    };
} forEach (_view getOrDefault ["squads", []]);

private _legend = "";
private _digit = 1;
{
    _x params ["", "_kind", "", "_label"];
    _legend = _legend + format ["[%1] %2%3    ",
        _digit, _label, ["", " — buy"] select (_kind isEqualTo "purchase")];
    _digit = _digit + 1;
} forEach (call cti_fnc_mapVerbs);

private _last = missionNamespace getVariable ["cti_lastJudgementText", ""];

hintSilent parseText format [
    "<t size='1.1'>Commander — %1</t><br/>Funds: %2    Squads: %3    Contacts: %4<br/><br/>"
    + "Place: %5<br/>Squad: %6<br/><br/>%7<br/><br/>%8<br/>%9",
    cti_uiSide,
    _view getOrDefault ["funds", "?"],
    count (_view getOrDefault ["squads", []]),
    count (_view getOrDefault ["contacts", []]),
    _place,
    _squad,
    _legend,
    cti_uiNote,
    _last
];
