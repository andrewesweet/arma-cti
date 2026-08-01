/*
 * Author: arma-cti
 * Which person commands which side. Runs on the server.
 *
 * ADR-0012 says the gateway stamps the acting side "from its own
 * commander-assignment state". This is that state, and it exists because the
 * side a player's *unit* happens to be on is not the same fact: a squad leader
 * fighting for WEST is on WEST and is not WEST's Commander, and reading the
 * group's side would hand every rifleman the Command Port. Authority is a fact
 * about the server's state, not about where somebody is standing.
 *
 * The fact it reads is slot occupancy. The mission authors one Commander slot
 * per side, named `cti_commander_<side>` in lower case — the same shape the HQ
 * structures are named in, and matched off `vehicleVarName` rather than off the
 * mission-namespace variable so a slot filled by a joining client is seen the
 * same way one filled at mission start is. A mission that names no slot for a
 * side simply has no human Commander for it, which is the honest reading and
 * the one #18 asks for: a side belongs to a human until somebody says
 * otherwise, and to nobody until somebody turns up.
 *
 * Latched by UID, once per side per Play Session, for the reason ADR-0015
 * refuses a second AI brain on a side: two Commanders on one side are two
 * answers to what that side is doing. UID rather than the unit, because
 * respawn hands the player a new unit and reconnection hands them a new machine
 * id, and neither is a change of Commander.
 *
 * Arguments:
 * 0: seconds between sweeps <NUMBER> (optional, default 5)
 *
 * Return Value: <SCRIPT> the assignment thread
 */
params [["_interval", 5, [0]]];

if (!isServer) exitWith { scriptNull };

private _schema = call cti_fnc_commandSchema;
if (count _schema isEqualTo 0) exitWith {
    diag_log "CTI|FAIL class=schema_stale commander_assign_no_schema";
    scriptNull
};

// Side to the UID of the person commanding it. Server-local: a client has no
// business knowing who commands the other side, and this is the one place the
// answer is kept.
missionNamespace setVariable ["cti_commanders", createHashMap];

[_interval, _schema get "sides"] spawn {
    params ["_interval", "_sides"];

    private _assigned = missionNamespace getVariable ["cti_commanders", createHashMap];
    private _slots = createHashMap;
    { _slots set [format ["cti_commander_%1", toLower _x], _x] } forEach _sides;

    diag_log format ["CTI|commander_assign_started slots=%1", keys _slots];

    while { true } do {
        {
            private _side = _slots getOrDefault [vehicleVarName _x, ""];
            if (_side isNotEqualTo "" && { !(_side in _assigned) }) then {
                private _uid = getPlayerUID _x;
                if (_uid isNotEqualTo "") then {
                    _assigned set [_side, _uid];
                    diag_log format ["CTI|commander_assigned side=%1 uid=%2 name=%3",
                        _side, _uid, name _x];
                };
            };
        } forEach allPlayers;

        private _next = diag_tickTime + _interval;
        waitUntil { diag_tickTime >= _next };
    };
};
