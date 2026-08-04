/*
 * Author: arma-cti
 * Tells the Commander one event, on screen with or without the map. Runs on
 * the client.
 *
 * Interior to the client's own call graph, so it carries no locality guard: its
 * one caller is cti_fnc_mapObservation, which is the guarded door the server
 * pushes an Observation through (#118, ADR-0041).
 *
 * The map is state the Commander may not be looking at; this is the event
 * channel playtest 0001 asked for (#176), in the shape Arma's own singleplayer
 * task notifications take: a CfgNotifications template through
 * BIS_fnc_showNotification, which draws whether or not the map is open
 * (topics/Arma_3_Notification.wiki). The templates live in the addon's
 * config.cpp — every rule lives in the addon (ADR-0007), and their wording is
 * a **playtest-tuned placeholder** in ADR-0020's sense.
 *
 * It keeps its own record of the last thing it told the Commander, for the
 * reason cti_lastJudgementText keeps the port's last answer: a probe cannot
 * stub a cti_fnc_ (the Functions Library compileFinals them all), so what this
 * function did has to be readable off what it left behind. `queued` in that
 * record is BIS_fnc_showNotification's own return — the engine accepting the
 * notification, not merely this function asking it to.
 *
 * Arguments:
 * 0: the event <HASHMAP>, as cti_fnc_viewEvents mints them
 *
 * Return Value: none
 */
params [["_event", createHashMap, [createHashMap]]];

private _kind = _event getOrDefault ["event", ""];
private _shown = switch (_kind) do {
    case "place_taken": {
        ["cti_PlaceTaken", [_event getOrDefault ["place", "?"],
            _event getOrDefault ["owner", "?"], _event getOrDefault ["from", "?"]]]
    };
    case "squad_wiped": {
        ["cti_SquadWiped", [_event getOrDefault ["squad", "?"]]]
    };
    default { [] };
};

// An event this function has no words for is a call-graph bug, not a display
// choice: cti_fnc_viewEvents mints the kinds and this is their one presenter.
if (_shown isEqualTo []) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed notify_unknown_event kind=%1", _kind];
};

private _queued = _shown call BIS_fnc_showNotification;

private _told = +_event;
_told set ["queued", _queued];
cti_lastNotification = _told;
cti_notificationCount = (missionNamespace getVariable ["cti_notificationCount", 0]) + 1;

diag_log format ["CTI|commander_notified event=%1 args=%2 queued=%3",
    _kind, _shown # 1, _queued];
