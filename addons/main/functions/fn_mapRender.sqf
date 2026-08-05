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

// ---- playtest-tuned placeholder (ADR-0020) ------------------------------
// Marker text renders at the marker position, a Place's position is the town
// centre, and the town centre is exactly where the engine prints its own town
// name — so anything drawn *at* a Place writes over that label, every Place,
// every time (#174: playtest 0001 found a Squad, a Contact and "Agia Marina"
// in one unreadable stack). Squads are pulled north of the label and Contacts
// south, in world metres so the pair stays with its town at every zoom; a
// second Squad at the same Place stacks a step further north, because two
// Squads in Reserve at one Base is the opening state of every Campaign. Since
// #175 a Squad's clearance is measured from the Squad rather than from the
// Place, so it is the same clearance wherever the Squad has got to.
private _squadOffset = [0, 120];
private _contactOffset = [0, -120];
private _stackStep = 60;

// Current strength is drawn against establishment strength (#174: playtest
// 0001 read `rifle/8` as a fraction, and the live count the daemon serves has
// no denominator). The establishment comes from the same catalogue the price
// does — `command-schema.json`, via the Squad's own type — because writing an
// 8 down here would be #159's finding again: SQF inventing a number the
// daemon owns. A type the catalogue no longer sells renders "?", the same
// honest non-answer the fields around it give.
private _schema = call cti_fnc_commandSchema;
// Reads the enclosing forEach's _x, which is the Squad record at both call
// sites: the marker text below and the hint's Squad line.
private _squadLabel = {
    private _sold = (_schema getOrDefault ["squads", createHashMap])
        getOrDefault [_x getOrDefault ["type", ""], createHashMap];
    format ["%1 %2 %3/%4 — %5 %6",
        _x getOrDefault ["id", ""],
        _x getOrDefault ["type", "?"],
        _x getOrDefault ["size", "?"],
        _sold getOrDefault ["size", "?"],
        _x getOrDefault ["order", "?"],
        _x getOrDefault ["place", ""]]
};

// A Squad is drawn where it is, not only where it is standing still (#175:
// playtest 0001 lost sight of two Squads for the whole march and read the
// absence as death). `pos` is the Observation's own map position in metres,
// which is empty only for a Squad the world has not reported standing yet —
// bought this tick, not yet spawned — and that one falls back to the Place its
// coarse `at` names, which is the picture as it was before this field existed.
// A Squad with neither is not drawn, because there is nothing to draw it at.
private _crowd = createHashMap;
{
    private _id = _x getOrDefault ["id", ""];
    private _place = _x getOrDefault ["at", ""];
    private _pos = _x getOrDefault ["pos", []];
    private _at = if (_pos isNotEqualTo []) then {
        _pos params ["_posEast", "_posNorth"];
        [_posEast, _posNorth, 0]
    } else {
        [_place] call cti_fnc_placePosition
    };
    if (_at isNotEqualTo []) then {
        // Stacked by Place and not by position: two Squads in Reserve at one
        // Base are metres apart in the world and one point apart at map zoom,
        // which is the opening state of every Campaign. Squads in open ground
        // are already spread out and have no Place to be crowded at, so they
        // stack with nothing.
        private _row = 0;
        if (_place isNotEqualTo "") then {
            _row = _crowd getOrDefault [_place, 0];
            _crowd set [_place, _row + 1];
        };
        _at params ["_east", "_north"];
        _squadOffset params ["_offEast", "_offNorth"];
        private _marker = createMarkerLocal [format ["cti_ui_squad_%1", _id],
            [_east + _offEast, _north + _offNorth + _row * _stackStep, 0]];
        _marker setMarkerTypeLocal "mil_triangle";
        _marker setMarkerColorLocal _own;
        _marker setMarkerTextLocal (call _squadLabel);
        _drawn pushBack _marker;
    };
} forEach (_view getOrDefault ["squads", []]);

// A Contact is what was seen, never who it was: no Squad id, no Order, no side
// beyond "the other one" (CONTEXT.md). The marker says the same and no more.
{
    private _place = _x getOrDefault ["at", ""];
    private _at = [_place] call cti_fnc_placePosition;
    if (_at isNotEqualTo []) then {
        _at params ["_east", "_north"];
        _contactOffset params ["_offEast", "_offNorth"];
        private _marker = createMarkerLocal [format ["cti_ui_contact_%1", _place],
            [_east + _offEast, _north + _offNorth, 0]];
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

// What the Commander has selected (#174: playtest 0001 clicked the map and
// read the answer only in the hint's Place line). Drawn at the Place itself —
// it is the one marker whose job is to point at the ground the click named —
// and icon-only, because text here would sit exactly on the engine's label,
// which is the collision the offsets above exist to avoid. Redrawn wholesale
// with the rest, so a click on open country — which cti_fnc_placeOf answers
// with "" on purpose — removes it rather than leaving a stale selection.
if (cti_uiPlace isNotEqualTo "") then {
    private _at = [cti_uiPlace] call cti_fnc_placePosition;
    if (_at isNotEqualTo []) then {
        private _marker = createMarkerLocal ["cti_ui_place", _at];
        _marker setMarkerTypeLocal "mil_pickup";
        _marker setMarkerColorLocal "ColorYellow";
        _drawn pushBack _marker;
    };
};

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
        _squad = call _squadLabel;
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
