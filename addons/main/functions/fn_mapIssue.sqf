/*
 * Author: arma-cti
 * Turns one keypress on the map into one Command. Runs on the client.
 *
 * Interior to the client's own call graph, so it carries no locality guard: it
 * is reached only from the map display's KeyDown handler, which
 * cti_fnc_mapCommander installs and which no machine without a display can fire
 * (#118, ADR-0041).
 *
 * The whole of the UI's order path, and it is four lines of it: build the
 * Command with cti_fnc_command, hand it to remoteExec, and let the port judge.
 * Nothing here decides anything the daemon decides — not whether the Funds are
 * there, not whose ground that is, not whether the Order suits the Place. A UI
 * that pre-judged would be a second rules engine drifting quietly out of step
 * with the one the AI plays by, and the refusals it produced would be a
 * human-only error channel. So the only thing this refuses to send is a Command
 * that cannot be built at all, and it says so as a UI state rather than dressing
 * it up in a rejection code the port never issued.
 *
 * remoteExec returns immediately and the judgement arrives later through
 * cti_fnc_portReply, so the click costs this frame one message and no wait.
 * That is the async path #18 asks for; there is no synchronous one to choose
 * instead, because a client never speaks to the daemon (ADR-0018).
 *
 * Arguments:
 * 0: the DIK key code <NUMBER>
 *
 * Return Value: none
 */
params [["_key", -1, [0]]];

// UI readiness, which is the only one of #114's two questions left here (#118):
// there is no map to issue an Order from until the first Observation has
// populated one.
if (isNil "cti_uiSide") exitWith {};

private _view = missionNamespace getVariable ["cti_view", createHashMap];
private _squads = _view getOrDefault ["squads", []];

// ---- playtest-tuned placeholder (ADR-0020) ------------------------------
// Tab cycles which of this Commander's own Squads the next Order names. One
// selection rather than a roster panel, because a roster panel is presentation
// and this ticket is the path.
if (_key isEqualTo 15) exitWith {
    private _ids = _squads apply { _x getOrDefault ["id", ""] };
    if (_ids isEqualTo []) exitWith {
        cti_uiNote = "no Squads yet — Purchase one first";
        [] call cti_fnc_mapRender;
    };
    private _next = ((_ids find cti_uiSquad) + 1) % (count _ids);
    cti_uiSquad = _ids # _next;
    cti_uiNote = "";
    [] call cti_fnc_mapRender;
};

private _verb = (call cti_fnc_mapVerbs) select { (_x # 0) isEqualTo _key };
if (_verb isEqualTo []) exitWith {};
(_verb # 0) params ["", "_kind", "_name"];

private _command = createHashMap;

if (_kind isEqualTo "purchase") then {
    _command = ["purchase", [["squad_type", _name]]] call cti_fnc_command;
} else {
    if (_kind isEqualTo "reinforce") exitWith {
        // Names the selected Squad and nothing else (ADR-0040). Whether that
        // Squad is at its Base, whether anybody is missing and what the
        // replacements cost are the port's answers, not this one's — the same
        // rule the Order path above is written to.
        if (cti_uiSquad isEqualTo "") exitWith {
            cti_uiNote = "pick a Squad first — [Tab]";
            [] call cti_fnc_mapRender;
        };
        _command = ["reinforce", [["squad", cti_uiSquad]]] call cti_fnc_command;
    };
    private _schema = call cti_fnc_commandSchema;
    // Which Orders name a Place is the schema's answer, not the UI's (ADR-0020).
    private _needs = _name in (_schema getOrDefault ["orders_needing_place", []]);
    private _place = ["", cti_uiPlace] select _needs;

    if (cti_uiSquad isEqualTo "") exitWith {
        cti_uiNote = "pick a Squad first — [Tab]";
        [] call cti_fnc_mapRender;
    };
    if (_needs && { _place isEqualTo "" }) exitWith {
        cti_uiNote = format ["%1 names a Place — click one on the map", _name];
        [] call cti_fnc_mapRender;
    };

    _command = ["order", [
        ["squad", cti_uiSquad],
        ["order", _name],
        ["place", _place]
    ]] call cti_fnc_command;
};

if (count _command isEqualTo 0) exitWith {
    // cti_fnc_command has already logged which part of the schema it failed.
    cti_uiNote = format ["%1 could not be built — see the log", _name];
    [] call cti_fnc_mapRender;
};

// The one door (ADR-0012). Target 2 is the server, which is the only target the
// mission's mode=1 whitelist allows this call, and cti_fnc_portGateway is the
// only function on that whitelist.
[_command] remoteExec ["cti_fnc_portGateway", 2];

cti_uiNote = format ["sent %1 %2", _kind, _name];
[] call cti_fnc_mapRender;
