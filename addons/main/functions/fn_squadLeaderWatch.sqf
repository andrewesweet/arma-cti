/*
 * Author: arma-cti
 * Who is occupying a squad-leader slot, sweep by sweep. Runs on the server.
 *
 * The world's half of ADR-0070: a person standing in a slot the mission
 * authors. What that means — a dedicated roster Squad at own Base,
 * composition-unassigned, suspended when he leaves before its first fill and
 * the same identity handed back when he returns — is the daemon's (ADR-0012),
 * and it learns of it through `cti_fnc_squadLeaderSample` on the observe
 * report rather than through the Command Port, because occupying a slot is not
 * a Command: no Funds move and the rules judge nothing.
 *
 * A sibling of `cti_fnc_commanderAssign`, and the one place it deliberately
 * parts company with it is the latch. A Commander assignment is latched for the
 * Play Session because two Commanders on one side are two answers to what that
 * side is doing (ADR-0025), and the sweep retires once every slot is filled.
 * Rulings 6 and 7 are about a squad leader leaving and coming back, so this
 * sweep has to be able to see both: it reports occupancy as it stands, and it
 * never retires.
 *
 * **Occupancy is re-read every sweep, and the two engine facts that makes safe
 * are stated rather than assumed.** `allPlayers` is "all units controlled by
 * connected clients ... including dead players" (commands/allPlayers.wiki), so
 * a man serving ADR-0052's thirty-second death timer is still occupying his
 * slot and a disconnected one is simply gone — which is the leaving this has to
 * see. And "respawned unit will have the same vehicleVarName as the corpse left
 * behind" (commands/vehicleVarName.wiki), so the body the engine hands him back
 * still answers to the slot's name. Without the second of those, every respawn
 * would read as a disconnect and the daemon would suspend the shell of a player
 * who never went anywhere.
 *
 * Matched off `vehicleVarName` rather than off the mission-namespace variable,
 * for `cti_fnc_commanderAssign`'s reason: a slot filled by a joining client is
 * then seen the same way one filled at mission start is.
 *
 * Reported by player UID (ADR-0025): respawn hands the player a new unit and
 * reconnection a new machine id, and neither is a change of who is leading.
 *
 * Arguments:
 * 0: seconds between sweeps <NUMBER> (optional, default 5)
 *
 * Return Value: <SCRIPT> the sweep thread
 */
#include "\cti\addons\main\script_component.hpp"

params [["_interval", 5, [0]]];

// The entry point of a supervised loop, which ADR-0041 keeps guarded: this is the
// one call site a future restart would re-enter, and the thread it starts is
// inventoried by name rather than by caller (#118).
SERVER_ONLY(scriptNull);

private _schema = call cti_fnc_commandSchema;
if (count _schema isEqualTo 0) exitWith {
    // Asked before the thread is started rather than inside it (#102): a loop
    // enters the watchdog's register only once it is going to run. Which sides
    // are playing is the schema's answer, as it is `cti_fnc_commanderAssign`'s.
    diag_log "CTI|FAIL class=schema_stale squad_leader_watch_no_schema";
    scriptNull
};

// The slot name each side's squad leader stands in, in the shape the Commander
// slots already use: `cti_squad_leader_<side>` in lower case. A mission that
// names no slot for a side simply has no player squad leader for it, which is
// the honest reading and the same one #18 asked for about Commanders.
private _slots = createHashMap;
{ _slots set [format ["cti_squad_leader_%1", toLower _x], _x] } forEach (_schema get "sides");

diag_log format ["CTI|squad_leader_watch_started interval=%1 slots=%2", _interval, keys _slots];

// Server-local, like `cti_commanders` and `cti_loadoutChosen`: a client has no
// business reading who is leading a Squad on the other side, and this is the one
// place the answer is kept. `cti_fnc_squadLeaderSample` copies it onto the
// report; nothing else reads it.
missionNamespace setVariable ["cti_squadLeaders", createHashMap];

// Comparison only, never the record: who was occupying what on the last sweep,
// so an arrival and a departure are each said once rather than every cadence.
private _said = createHashMap;

// Paced, heartbeated and watched by the one adapter every loop in the addon runs
// on (#85). The first turn is taken before the first wait, because a slot filled
// at mission start is filled before this loop exists and a cadence of silence is
// a cadence in which the daemon believes nobody is leading anything.
["squad_leader_watch", _interval, [_slots, _said], {
    params ["_slots", "_said"];

    // Rebuilt rather than amended, which is what "not latched" means here: what
    // this reports is who is standing in a slot now, and a player who has gone
    // is absent by construction rather than by anything remembering to remove
    // him.
    private _seen = createHashMap;
    {
        private _side = _slots getOrDefault [vehicleVarName _x, ""];
        if (_side isNotEqualTo "") then {
            // A machine with no player unit — a headless client, and the server
            // itself — has no UID and occupies nothing (ADR-0025's reading of
            // the same engine fact, and `cti_fnc_loadoutWatch`'s).
            private _uid = getPlayerUID _x;
            if (_uid isNotEqualTo "") then {
                _seen set [_uid, _side];
            };
        };
    } forEach allPlayers;

    {
        if ((_said getOrDefault [_x, ""]) isNotEqualTo _y) then {
            diag_log format ["CTI|squad_leader_slot_taken uid=%1 side=%2", _x, _y];
        };
    } forEach _seen;
    {
        if !(_x in _seen) then {
            diag_log format ["CTI|squad_leader_slot_left uid=%1 side=%2", _x, _y];
        };
    } forEach _said;

    missionNamespace setVariable ["cti_squadLeaders", _seen];

    // Amended in place rather than rebound: `_said` is the loop's own argument
    // carried across turns, and assigning to the name here would leave the
    // adapter holding the map from the first sweep for the rest of the session.
    { _said deleteAt _x } forEach keys _said;
    { _said set [_x, _y] } forEach _seen;
}, true] call cti_fnc_everyInterval
