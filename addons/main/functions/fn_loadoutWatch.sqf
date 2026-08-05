/*
 * Author: arma-cti
 * Offers each player the loadout menu, grants a pick at his own Base, and keeps
 * him in the kit he picked. Runs on the server.
 *
 * The human's ruling of 2026-08-04 (ADR-0056): a curated menu, free, players
 * only, at Base only, and the kit survives respawn and the session save. Three
 * of those four are this loop; the fourth is the daemon's, which records the
 * choice off the observe report because the snapshot is what has to carry it.
 *
 * **A watch rather than a respawn event handler**, following #189's reasoning
 * for `selectLeader`: one rule — *a man is not wearing what he chose, so dress
 * him* — covers a respawn, a client joining in progress, and (when #4 lands) a
 * Campaign resumed with everybody's kit already recorded. A respawn hook would
 * cover the first of those three and would have to be joined by something else
 * for the other two.
 *
 * Nothing here is a Command. A kit is free, moves no Funds and is judged by no
 * rule the port owns, so no Command Port entry is added and the CfgRemoteExec
 * whitelist stays one function long: the client publishes a wish on his own
 * body (`cti_fnc_loadoutMenu`) and this reads it. Which means the wish is
 * *client-supplied* and is treated as such — the menu is checked here, the Base
 * is checked here, and the client's own copy of both is display only.
 *
 * AI units are untouched, which is the ruling's "players only": this loop walks
 * `allPlayers` and nothing else.
 *
 * Arguments:
 * 0: seconds between sweeps <NUMBER> (optional, default 5)
 *
 * Return Value: <SCRIPT> the watch thread
 */
#include "\cti\addons\main\script_component.hpp"

params [["_interval", 5, [0]]];

// The entry point of a supervised loop, which ADR-0041 keeps guarded: this is the
// one call site a future restart would re-enter, and the thread it starts is
// inventoried by name rather than by caller (#118).
SERVER_ONLY(scriptNull);

private _kits = call cti_fnc_loadoutCatalogue;
if (_kits isEqualTo []) exitWith {
    // cti_fnc_loadoutCatalogue has already logged which failure this is. Asked
    // before the thread is started rather than inside it (#102): a loop enters
    // the watchdog's register only once it is going to run.
    diag_log "CTI|FAIL class=assertion_failed loadout_watch_no_catalogue";
    scriptNull
};

diag_log format ["CTI|loadout_watch_started interval=%1 kits=%2", _interval, count _kits];

// What each player has been granted, by player UID — the world's live half of
// the record whose durable half is the daemon's (ADR-0056). On the namespace
// because `cti_fnc_loadoutSample` reads it onto the report; server-local,
// because nothing on a client has any business reading another player's kit.
private _chosen = createHashMap;
missionNamespace setVariable ["cti_loadoutChosen", _chosen];

// Comparison only, never the record: the body each man was last seen wearing
// his kit on, the body he was last offered a menu on, and the wish he was last
// refused. Each exists so that something said once is not said every sweep.
private _worn = createHashMap;
private _offered = createHashMap;
private _refused = createHashMap;

// Paced, heartbeated and watched by the one adapter every loop in the addon
// runs on (#85). First turn taken at once, so a player who is already standing
// at his Base when this starts is offered his menu without waiting a cadence.
["loadout_watch", _interval, [_kits, _chosen, _worn, _offered, _refused], {
    params ["_kits", "_chosen", "_worn", "_offered", "_refused"];

    {
        private _unit = _x;
        // A machine with no player unit — a headless client, and the server
        // itself — has no UID and takes no kit (ADR-0025's reading of the same
        // engine fact). `allPlayers` carries dead players, which is deliberate:
        // a corpse still answers for the UID whose kit is being remembered.
        private _uid = getPlayerUID _unit;
        if (_uid isNotEqualTo "") then {
            // An action list belongs to a body and dies with it, so a new body
            // is a new menu. The same signal the dressing below turns on.
            if ((_offered getOrDefault [_uid, objNull]) isNotEqualTo _unit) then {
                _offered set [_uid, _unit];
                [_unit] remoteExec ["cti_fnc_loadoutMenu", owner _unit];
            };

            private _wish = _unit getVariable ["cti_loadoutWish", ""];
            if (_wish isNotEqualTo "" && {_wish isNotEqualTo (_chosen getOrDefault [_uid, ""])}) then {
                private _index = _kits findIf { (_x getOrDefault ["id", ""]) isEqualTo _wish };
                if (_index < 0) then {
                    // A kit no menu offers, which a client cannot reach through
                    // the menu it was given: either a stale PBO or somebody
                    // setting the variable by hand.
                    diag_log format ["CTI|FAIL class=assertion_failed loadout_not_on_menu uid=%1 kit=%2",
                        _uid, _wish];
                } else {
                    if ([_unit] call cti_fnc_loadoutAtBase) then {
                        _chosen set [_uid, _wish];
                        diag_log format ["CTI|loadout_granted uid=%1 kit=%2", _uid, _wish];
                    } else {
                        // Said once per wish rather than once per sweep: the
                        // wish stays published for as long as he is away, and a
                        // line a second would bury the grant that follows it.
                        if ((_refused getOrDefault [_uid, ""]) isNotEqualTo _wish) then {
                            _refused set [_uid, _wish];
                            diag_log format ["CTI|loadout_refused uid=%1 kit=%2 reason=away_from_base",
                                _uid, _wish];
                        };
                    };
                };
            };

            private _kitId = _chosen getOrDefault [_uid, ""];
            // A dead man is left as he fell. The body he respawns into is a
            // different object, which is what brings him back through here.
            if (_kitId isNotEqualTo "" && {alive _unit}
                && {(_worn getOrDefault [_uid, []]) isNotEqualTo [_unit, _kitId]}) then {
                private _kit = _kits # (_kits findIf { (_x getOrDefault ["id", ""]) isEqualTo _kitId });
                private _class = (_kit getOrDefault ["units", createHashMap])
                    getOrDefault [str side _unit, ""];
                if (_class isEqualTo "") then {
                    diag_log format ["CTI|FAIL class=assertion_failed loadout_no_class uid=%1 kit=%2 side=%3",
                        _uid, _kitId, str side _unit];
                } else {
                    // The engine aborts the command outright if the unit is
                    // mid weapon-switch (commands/setUnitLoadout.wiki, 2.20), so
                    // a man caught doing that is left for the next sweep rather
                    // than recorded as dressed when he is not.
                    if !(isSwitchingWeapon _unit) then {
                        // `arg= global, eff= global`: the server dresses a unit
                        // that is local to a client, and every machine sees it.
                        _unit setUnitLoadout _class;
                        _worn set [_uid, [_unit, _kitId]];
                        diag_log format ["CTI|loadout_applied uid=%1 kit=%2 class=%3",
                            _uid, _kitId, _class];
                    };
                };
            };
        };
    } forEach allPlayers;
}, true] call cti_fnc_everyInterval
