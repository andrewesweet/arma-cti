/*
 * Author: arma-cti
 * Hands the deaths since the last report to the daemon (#39). Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard:
 * every path into it starts in `missions/cti.Stratis/initServer.sqf`, which the
 * engine runs on the server and nowhere else (#118, ADR-0040).
 *
 * cti_fnc_casualtyWatch buffers; this drains. Every report carries what has
 * happened since the last one and then the buffer is empty, so a death is
 * reported once — unlike cti_fnc_hqSample, which repeats a standing fact every
 * report because rubble stays rubble. A casualty is a moment, not a state.
 *
 * The drain runs unscheduled. The report loop is a scheduled thread and can be
 * suspended between any two statements; the event handler filling the buffer is
 * not, so a death landing between reading the buffer and replacing it would be
 * appended to an array nobody holds any more and lost. `isNil {}` is the
 * engine's own way of forcing a block into the unscheduled environment
 * (commands/isNil.wiki), which makes the swap atomic against the handler.
 *
 * Rides the `observe` request rather than the reply: commands/callExtension.wiki
 * puts no limit on what may be sent *to* an extension, and #26's 10,240-byte cap
 * is on the return. Nothing here is ever projected into an Observation.
 *
 * Arguments: none
 *
 * Return Value: <HASHMAP> `deaths` (the drained records) and `dropped` (how many
 * the buffer's bound refused since the last report)
 */
private _deaths = [];
private _dropped = 0;

isNil {
    _deaths = missionNamespace getVariable ["cti_casualties", []];
    _dropped = missionNamespace getVariable ["cti_casualtiesDropped", 0];
    missionNamespace setVariable ["cti_casualties", []];
    missionNamespace setVariable ["cti_casualtiesDropped", 0];
};

// Built through the exported schema (#74), like every named object in the
// report. The early exit above is the same two fields spelled out, because a
// machine that is not the server has no schema question to ask.
["casualties", [["deaths", _deaths], ["dropped", _dropped]]] call cti_fnc_reportObject
