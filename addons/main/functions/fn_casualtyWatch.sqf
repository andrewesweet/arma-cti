/*
 * Author: arma-cti
 * Writes down every death the world sees, for the daemon to collect (#39).
 *
 * Runs on the server, and interior to its call graph, so it carries no locality
 * guard: its one caller is `missions/cti.Stratis/initServer.sqf`, which the
 * engine runs on the server and nowhere else (#118, ADR-0041). It is not a
 * supervised loop — it installs an event handler and returns, so there is no
 * thread for cti_fnc_loopWatch to inventory.
 *
 * The engine already has the surface: `EntityKilled` is a mission event handler
 * (topics/Arma_3_Mission_Event_Handlers.wiki, Arma 3 v1.56), registered once on
 * the server, that fires for entities rather than for units somebody remembered
 * to attach a handler to. So no per-unit `addEventHandler`, nothing to re-attach
 * when a Squad is bought, and no death missed because a spawn path forgot.
 *
 * A death here is *telemetry*, not intelligence. Neither Commander reads any of
 * this — it never touches an Observation and never crosses back — so ADR-0020's
 * scoreboard/intelligence line puts it firmly on the operator's side, and
 * ADR-0008's rule that a Commander reasons about places rather than coordinates
 * does not bind it. The row therefore carries both: the authored place id for
 * reading, and the metre coordinate for the question a place id cannot answer,
 * which is the one #35's timeout actually raised — how far from its target did
 * this Squad get before it stopped existing.
 *
 * Identity is the whole value of the row. `netId` names nothing anybody
 * recognises, so a casualty is attributed to the Squad and the side that owned
 * the unit, and the killer likewise where the world knows one. The netIds are
 * kept beside them because they are the only stable keys when the Squad is
 * unknown — a garrison soldier, an editor-placed unit — and a death with no
 * Squad is still recorded rather than dropped.
 *
 * `_instigator` is objNull on a road kill, which the wiki says outright; the
 * fallback below is the one it documents.
 *
 * Arguments: none
 *
 * Return Value: <BOOL> true when the world is being watched
 */
if (!isNil "cti_casualtyWatch") exitWith {
    // Registering twice would file every death twice, and a timeline that
    // double-counts is worse than one that stops early: the second is visibly
    // short, the first reads as a fact.
    diag_log "CTI|casualty_watch already_running";
    true
};

missionNamespace setVariable ["cti_casualties", []];
missionNamespace setVariable ["cti_casualtiesDropped", 0];

cti_casualtyWatch = addMissionEventHandler ["EntityKilled", {
    params ["_unit", "_killer", "_instigator"];

    // The wiki's own workaround, in its own order: a UAV/UGV operator first,
    // then the killer itself for a player-driven road kill.
    if (isNull _instigator) then { _instigator = UAVControl vehicle _killer select 0 };
    if (isNull _instigator) then { _instigator = _killer };

    // The engine hands the victim back as its own killer when nobody killed it
    // — a collision, a fall, a drowning, which the `Killed` page says outright.
    // Left alone that becomes a row saying a Squad shot one of its own, and
    // inventing friendly fire is precisely the kind of guess this whole surface
    // exists to stop. So it is recorded as what it is: nobody's doing. The
    // probe found this; the first cut filed all three of its staged deaths as
    // Squad-on-Squad and one of them was a fall.
    if (_instigator isEqualTo _unit) then { _instigator = objNull; _killer = objNull };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];

    // Which Squad a unit belonged to, and whose side it was on. cti_fnc_effectApply
    // stamps the Squad id on the group as it is bought, so this is a read rather
    // than a sweep of the roster — and it is the same answer, because that stamp
    // and the roster are written in the same breath. A group carrying no stamp
    // is a garrison or an editor-placed unit: no Squad, and still a death.
    private _whose = {
        params ["_who"];
        private _group = group _who;
        if (isNull _group) exitWith { ["", ""] };
        [_group getVariable ["cti_squad", ""], str side _group]
    };

    ([_unit] call _whose) params ["_squad", "_side"];
    ([_instigator] call _whose) params ["_bySquad", "_bySide"];

    private _at = getPosATL _unit;
    // Built through the exported schema (#74): twelve fields is where a copy of
    // the daemon's declaration would drift first, so this is the declaration.
    private _record = ["death", [
        // The death's own clock reading, not the report's: reports are five
        // seconds apart and a firefight is not, so timing every casualty in a
        // batch to the batch would flatten the thing being reconstructed.
        ["at", time],
        ["unit", netId _unit],
        ["type", typeOf _unit],
        ["squad", _squad],
        ["side", _side],
        ["place", [_at, _map getOrDefault ["objectives", []], _map getOrDefault ["bases", []]] call cti_fnc_placeOf],
        ["pos", [round (_at # 0), round (_at # 1), round (_at # 2)]],
        ["by_unit", netId _instigator],
        ["by_type", typeOf _instigator],
        ["by_squad", _bySquad],
        ["by_side", _bySide],
        // The vehicle only when it is not the shooter, so a row saying
        // `by_vehicle` says something happened that a rifle could not do.
        ["by_vehicle", ["", typeOf _killer] select (!isNull _killer && {_killer isNotEqualTo _instigator})]
    ]] call cti_fnc_reportObject;

    private _pending = missionNamespace getVariable ["cti_casualties", []];
    // A bound, because a daemon that has stopped collecting must not be able to
    // grow this without end. Dropping is counted rather than silent: the daemon
    // writes the count down, so a gap in the timeline reads as a gap instead of
    // as quiet.
    if (count _pending >= 512) then {
        missionNamespace setVariable ["cti_casualtiesDropped",
            (missionNamespace getVariable ["cti_casualtiesDropped", 0]) + 1];
    } else {
        _pending pushBack _record;
    };
}];

diag_log "CTI|casualty_watch_started";
true
