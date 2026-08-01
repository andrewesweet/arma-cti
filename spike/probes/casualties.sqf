// probe: casualties
// issues: 39
// window: 150
//
// #39 in-world probe: a death in the world is a row in the daemon's telemetry,
// carrying who died, where, when and to whom.
//
// `just regress casualties`, or by hand `just probe spike/probes/casualties.sqf 150`.
//
// The window is the subject added up: ~20 s for the world to build and the
// report loop to get a cycle in, up to 60 s for two purchases to cross the
// outbox and be held as groups, a few seconds of staging, and ~25 s for the
// report interval to carry the deaths and for the last of them to land. That is
// about 110 s of subject. Nothing here waits on pathfinding or on a firefight
// resolving, which is why it is the default window and not a longer one.
//
// What is asserted here, and what is asserted outside here, are different
// halves and both are needed:
//
//   * this file asserts the world staged what it says it staged, and logs one
//     `casualty_staged` line per death naming only the facts it controls;
//   * `spike/run.sh` then runs `tools/timeline.py --expect` over the *daemon's*
//     telemetry file and fails the run if any of those lines is unaccounted
//     for. That is the crossing this probe exists for. An assertion made inside
//     the world about a record written outside it would only be asserting that
//     the world remembers its own doing.
//
// Deaths are staged rather than fought for. `setDamage [1, true, killer,
// instigator]` on the server is the engine's own way of naming a killer
// (commands/setDamage.wiki, since 2.12) and it drives the real `EntityKilled`
// handler by the real path — so what is under test is the recorder, and the
// ballistics that would otherwise decide *who* shot *whom* are not smuggled
// into the assertion. A firefight left to resolve itself can only be asserted
// on loosely, and loose is the state #35 left us in.
//
// Three deaths, because each is a different shape of row:
//   1. a WEST soldier killed by a named EAST soldier — both sides attributed;
//   2. an EAST soldier killed by a named WEST soldier — the mirror, so a
//      recorder that reads one side's roster and not the other is caught;
//   3. a WEST soldier killed by nobody — objNull instigator, the drowning and
//      falling case, which must still be recorded rather than withheld.
//
// The two Squads stand on different authored Objectives, so a `place` that was
// really taken per victim can be told from one taken once per report.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable casualty_probe_no_shim";
    };

    private _rpc = {
        params ["_envelope"];
        private _raw = ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        fromJSON _raw
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    if (count _objectives < 2) exitWith {
        diag_log "CTI|FAIL class=assertion_failed casualty_probe_needs_two_objectives";
    };

    // Let the world finish building and the report loop get a cycle in.
    private _next = diag_tickTime + 20;
    waitUntil { diag_tickTime >= _next };

    // One Squad a side, through the port, because that is the only way a Squad
    // gets onto the roster the recorder attributes against (ADR-0012).
    {
        [createHashMapFromArray [
            ["id", format ["casualty-probe-buy-%1", _x]],
            ["verb", "command"],
            ["payload", createHashMapFromArray [
                ["command", "purchase"],
                ["side", _x],
                ["args", createHashMapFromArray [["squad_type", "rifle"]]]
            ]]
        ]] call _rpc;
    } forEach ["WEST", "EAST"];

    private _deadline = diag_tickTime + 60;
    waitUntil {
        count (missionNamespace getVariable ["cti_squads", createHashMap]) >= 2
            || { diag_tickTime > _deadline }
    };
    private _squads = missionNamespace getVariable ["cti_squads", createHashMap];
    if (count _squads < 2) exitWith {
        diag_log format ["CTI|FAIL class=timeout casualty_probe_no_squads held=%1", count _squads];
    };

    // Which bought Squad is whose, read off the group rather than off the id's
    // spelling: the daemon mints the id and this probe is not the place to
    // assume its shape.
    private _held = createHashMap;
    {
        _held set [str side _y, [_x, _y]];
    } forEach _squads;
    if (!("WEST" in _held) || { !("EAST" in _held) }) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed casualty_probe_one_sided held=%1", keys _held];
    };

    // Each Squad onto its own authored Objective, and far enough apart that
    // neither can start a firefight the staging did not ask for.
    private _standing = createHashMap;
    {
        _x params ["_sideName", "_index"];
        (_held get _sideName) params ["_squadId", "_group"];
        private _place = _objectives # _index;
        (_place get "position") params ["_east", "_north"];
        {
            _x setPosATL [_east + (_forEachIndex * 4), _north, 0];
        } forEach units _group;
        _standing set [_sideName, [_squadId, _group, _place get "id"]];
        diag_log format ["CTI|casualty_probe_standing squad=%1 side=%2 place=%3 men=%4",
            _squadId, _sideName, _place get "id", count units _group];
    } forEach [["WEST", 0], ["EAST", 1]];

    (_standing get "WEST") params ["_westId", "_west", "_westPlace"];
    (_standing get "EAST") params ["_eastId", "_east", "_eastPlace"];
    if (count units _west < 3 || { count units _east < 2 }) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed casualty_probe_squads_too_small west=%1 east=%2",
            count units _west, count units _east];
    };

    // Settle: a unit moved by setPosATL is still falling for a frame or two, and
    // a death recorded mid-drop would carry a position nobody put it at.
    _next = diag_tickTime + 5;
    waitUntil { diag_tickTime >= _next };

    // The three deaths. Logged before they are staged rather than after, so a
    // claim cannot be quietly withheld by a probe that died between the two.
    private _stage = {
        params ["_victim", "_squad", "_sideName", "_place", "_killer", "_bySquad", "_bySide"];
        diag_log format ["CTI|casualty_staged squad=%1 side=%2 place=%3 type=%4 by_squad=%5 by_side=%6",
            _squad, _sideName, _place, typeOf _victim, _bySquad, _bySide];
        _victim setDamage [1, true, _killer, _killer];
    };

    // Held by hand rather than re-read between kills: `units` is the group's
    // living membership, so reading it again after a death shifts every index
    // after the one that just died.
    private _westMen = units _west;
    private _eastMen = units _east;
    private _westWere = count _westMen;
    private _eastWere = count _eastMen;

    [_westMen # 1, _westId, "WEST", _westPlace, _eastMen # 0, _eastId, "EAST"] call _stage;
    [_eastMen # 1, _eastId, "EAST", _eastPlace, _westMen # 0, _westId, "WEST"] call _stage;
    // Nobody's doing: objNull killer and objNull instigator, which is what the
    // engine hands for a drowning or a fall.
    [_westMen # 2, _westId, "WEST", _westPlace, objNull, "", ""] call _stage;

    // The world's own account, before the record is checked against it. Two
    // fewer WEST and one fewer EAST, or the claims above are about a world that
    // did not happen and the timeline check downstream would be asserting
    // against a fiction.
    _next = diag_tickTime + 5;
    waitUntil { diag_tickTime >= _next };
    private _westNow = { alive _x } count _westMen;
    private _eastNow = { alive _x } count _eastMen;
    if (_westNow != _westWere - 2 || { _eastNow != _eastWere - 1 }) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed casualty_probe_staging_missed west=%1/%2 east=%3/%4",
            _westNow, _westWere, _eastNow, _eastWere];
    };
    diag_log format ["CTI|casualty_probe_staged west=%1 east=%2 alive_west=%3 alive_east=%4",
        _westId, _eastId, _westNow, _eastNow];

    // Two report intervals plus the settling above: the buffer drains on the
    // report loop's own cadence (5 s), so waiting for one interval would leave
    // the last death's arrival to whichever side of the tick it fell.
    _next = diag_tickTime + 15;
    waitUntil { diag_tickTime >= _next };

    diag_log format ["CTI|casualty_probe_done staged=3 undrained=%1",
        count (missionNamespace getVariable ["cti_casualties", []])];
    diag_log "CTI|probe_done casualties";
};
