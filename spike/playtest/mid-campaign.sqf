// Boots the world into a named mid-Campaign state and then holds it open for a
// human play session: **WEST holds three Objectives with a Squad standing on
// each, and EAST is massing a kilometre off Agia Marina.**
//
// Boot line, and it is the whole of what a brief has to quote:
//
//   CTI_AI_SIDE=EAST CTI_AI_SEED=1 CTI_WINDOWS_CLIENT=1 CTI_PROBE_SOAK=1800 \
//       just probe spike/playtest/mid-campaign.sqf 2400
//
// EAST comes up under an AI Commander so the session has an opponent, and WEST
// comes up under nobody because a side that already has a Commander refuses your
// Commands `wrong_side` (ADR-0025). `CTI_PROBE_SOAK` is your half hour; the
// window is that plus the staging below, which takes four to five minutes and
// says out loud when it is done. You will be in the seat while it stages — the
// Campaign is being played into position rather than assembled around you.
//
// Because this fixture marks the session as a human one, run.sh stages the
// Zeus-style observer beside it (spike/playtest/observer.sqf, #178): press Y
// to fly free without touching the world, Y again to come back to your body
// and the Commander's map.
//
// ---- why this exists (#42)
//
// The playtest-brief skill says a boot line boots "a committed fixture that
// lands the player directly in the interesting state" and "never a fresh
// campaign unless the brief is about the opening". Brief 0001 could not honour
// that: the only bootable state was a fresh Campaign, so half an hour went on
// reaching a board rather than playing one. This is the exit.
//
// Deliberately **not** in spike/probes/: `just regress` runs every .sqf in that
// directory, and a fixture whose last act is to sit for half an hour would add
// half an hour of nothing to every corpus run (docs/regression-tier.md). It is
// not a probe: it asserts nothing about the code under test. The two kinds of
// assertion it does make are about its own staging, which is the rule
// `spike/probe-prelude.sqf` already states for the same distinction.
//
// ---- the one rule this fixture is built to
//
// **Every part of the state is reached through the door the Campaign uses.** A
// fixture that set ownership or Funds directly would be a world the game cannot
// reach, and a playtest of it would be a playtest of nothing:
//
//   - The Squads are **Purchased through the Command Port** (`command`/
//     `purchase`), which is the only way a Squad gets onto the roster
//     (ADR-0012, ADR-0020). Refused Purchases are refused out loud.
//   - The ground is **captured by presence**: a Squad standing inside an
//     Objective's capture radius for `capture_seconds` is what makes it WEST's,
//     decided by the daemon and read back off `cti_objectiveOwner`, which the
//     server paints from the daemon's own reply.
//   - The standing Orders are **issued through the port** (`command`/`order`),
//     the same envelope a Commander's click builds.
//   - Funds are whatever three Purchases and the income of three held
//     Objectives have left, because that is what the Campaign says they are.
//     There is no door that sets Funds and this fixture does not invent one.
//   - EAST's Squads are **EAST's Commander's own**, bought off its own picture.
//     Nothing here commands EAST.
//
// The one thing engineered is **position** — Squads are put where a march would
// have taken them, because Stratis is 4 km wide and a march is forty minutes of
// a forty-minute session. That is the licence `campaign-end` and
// `massed-assault` take, and it is the only one taken here.
//
// ---- what it refuses to do
//
// It refuses to open the window on a board it did not actually reach. Every
// claim in the state card is checked before the soak starts, and a claim that
// failed ends the run with a typed FAIL rather than handing over a world whose
// description is wrong — a brief played against a state nobody verified is worse
// than a brief that could not be run.
//
// ---- verified
//
// Three runs on 2026-08-02, at shortened soaks with the window sized to match —
// the subject was the staging, not the half hour, which is brief 0001's
// precedent and the same distinction CLAUDE.md draws about probe windows. The
// board was reached in 40 s, 39 s and 35 s; each run ended `window_closed` and
// `HOLD-COMPLETE` with three Objectives WEST, three WEST Squads under Defend
// Orders and three EAST Squads inside 1,500 m of the front. The first of the
// three massed EAST on the neighbour *behind* WEST's line, because the fixture
// took the first name in the manifest's adjacency list; it now takes whichever
// neighbour lies nearest EAST's own Base, which is the direction an enemy
// arrives from. What is still unverified is the half hour itself: nothing has
// soaked for 1800 s, and no human client has joined this fixture.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable playtest_fixture_no_shim";
        diag_log "CTI|playtest_fixture probe_done reason=no_shim";
    };

    // The state this fixture is named for. Three Objectives WEST can plausibly
    // have taken from its own Base — the two the Base touches and the one behind
    // them — and the front is Agia Marina, which is the ground EAST comes for.
    private _held = ["agia_marina", "camp_tempest", "girna"];
    private _front = "agia_marina";

    [20] call cti_probe_fnc_worldReady;

    // ------------------------------------------------ the doors
    // One Order through the Command Port, in the envelope the gateway builds
    // from a Commander's click. Not in `spike/probe-prelude.sqf` because #86's
    // rule for that file is that a helper earns its place by having been copied,
    // and this is the first copy.
    private _sendOrder = {
        params ["_id", "_squad", "_order", "_place"];
        private _reply = [createHashMapFromArray [
            ["id", _id],
            ["verb", "command"],
            ["payload", createHashMapFromArray [
                ["command", "order"],
                ["side", "WEST"],
                // Stamped by the fixture because there is no gateway on this
                // path (ADR-0044): an unstamped line is refused `unknown_caller`.
                ["acting_side", "WEST"],
                ["args", createHashMapFromArray [
                    ["squad", _squad],
                    ["order", _order],
                    ["place", _place]
                ]]
            ]]
        ]] call cti_probe_fnc_rpc;
        private _status = "unreadable_reply";
        if (!isNil "_reply" && { _reply isEqualType createHashMap }) then {
            _status = _reply getOrDefault ["status", ""];
        };
        if (_status isNotEqualTo "ok") then {
            diag_log format ["CTI|FAIL class=assertion_failed playtest_fixture_order_refused squad=%1 order=%2 place=%3 status=%4",
                _squad, _order, _place, _status];
        };
        _status isEqualTo "ok"
    };

    private _westSquads = { ["WEST"] call cti_probe_fnc_squadsOf };
    private _eastSquads = { ["EAST"] call cti_probe_fnc_squadsOf };

    private _ownedByWest = {
        private _owners = missionNamespace getVariable ["cti_objectiveOwner", createHashMap];
        private _mine = [];
        { if ((_owners getOrDefault [_x, ""]) isEqualTo "WEST") then { _mine pushBack _x } }
            forEach _held;
        _mine
    };

    // ------------------------------------------------ the staging
    private _deadline = 0;
    private _roster = [];
    private _stopped = "";

    // Three Rifle Squads, Purchased. WEST is nobody's side on this boot line, so
    // the port takes them; under an AI Commander it would refuse `wrong_side`,
    // and that refusal is the boot line being wrong rather than the fixture.
    private _buyTheForce = {
        for "_i" from 1 to (count _held) do {
            private _reply = [format ["fixture-buy-%1", _i], "WEST", "rifle"]
                call cti_probe_fnc_buySquad;
            if ((_reply getOrDefault ["status", ""]) isNotEqualTo "ok") exitWith {};
        };
        _deadline = diag_tickTime + 90;
        waitUntil {
            count (call _westSquads) >= count _held || { diag_tickTime > _deadline }
        };
        _roster = (keys (call _westSquads));
        _roster sort true;
        if (count _roster < count _held) exitWith {
            diag_log format ["CTI|FAIL class=timeout playtest_fixture_force_never_arrived squads=%1 wanted=%2 hint=%3",
                count _roster, count _held, "is WEST under an AI Commander?"];
            false
        };
        diag_log format ["CTI|playtest_fixture_bought squads=%1 at=%2", _roster, time];
        true
    };

    // One Squad onto each Objective, and then the daemon's own capture rule does
    // the rest. Position is the only engineered thing here: the walk from the
    // Base is twenty minutes of a session that has thirty.
    private _takeTheGround = {
        {
            private _place = [_x] call cti_probe_fnc_placeNamed;
            if (count _place isEqualTo 0) exitWith {
                diag_log format ["CTI|FAIL class=assertion_failed playtest_fixture_no_such_place place=%1", _x];
            };
            (_place get "position") params ["_east", "_north"];
            private _group = (call _westSquads) get (_roster # _forEachIndex);
            {
                _x setPosATL [_east + (_forEachIndex * 4), _north, 0];
            } forEach units _group;
        } forEach _held;

        _deadline = diag_tickTime + 150;
        waitUntil { count (call _ownedByWest) >= count _held || { diag_tickTime > _deadline } };
        private _mine = call _ownedByWest;
        if (count _mine < count _held) exitWith {
            diag_log format ["CTI|FAIL class=timeout playtest_fixture_ground_never_changed_hands held=%1 wanted=%2 owners=%3",
                _mine, _held, missionNamespace getVariable ["cti_objectiveOwner", createHashMap]];
            false
        };
        diag_log format ["CTI|playtest_fixture_ground_held places=%1 at=%2", _mine, time];
        true
    };

    // Standing Orders, through the port, so the board the human inherits has
    // Squads doing something rather than three Squads in Reserve.
    private _postTheGarrisons = {
        private _issued = 0;
        {
            if ([format ["fixture-order-%1", _forEachIndex], _roster # _forEachIndex, "defend", _x]
                call _sendOrder) then { _issued = _issued + 1 };
        } forEach _held;
        if (_issued < count _held) exitWith { false };
        diag_log format ["CTI|playtest_fixture_orders_issued orders=%1 at=%2", _issued, time];
        true
    };

    // EAST's own Squads, bought by EAST's own Commander off EAST's own picture,
    // moved up to a kilometre short of the front. Where they go next is theirs.
    private _massTheEnemy = {
        _deadline = diag_tickTime + 180;
        waitUntil { count (call _eastSquads) >= 2 || { diag_tickTime > _deadline } };
        private _theirs = call _eastSquads;
        if (count _theirs < 2) exitWith {
            diag_log format ["CTI|FAIL class=timeout playtest_fixture_enemy_never_fielded squads=%1 hint=%2",
                count _theirs, "is CTI_AI_SIDE=EAST set?"];
            false
        };

        private _place = [_front] call cti_probe_fnc_placeNamed;
        (_place get "position") params ["_east", "_north"];
        private _centre = [_east, _north, 0];

        // A kilometre off the front on the line towards whichever of the front's
        // neighbours lies nearest EAST's own Base — the way an enemy would
        // actually arrive, read off the manifest rather than written out. Massing
        // them on the neighbour behind WEST's line would be a state the Campaign
        // cannot reach, which is the one thing this fixture may not do.
        private _theirBase = createHashMap;
        {
            if ((_x getOrDefault ["side", ""]) isEqualTo "EAST") exitWith { _theirBase = _x };
        } forEach ((missionNamespace getVariable ["cti_map", createHashMap])
            getOrDefault ["bases", []]);
        if (count _theirBase isEqualTo 0) exitWith {
            diag_log "CTI|FAIL class=assertion_failed playtest_fixture_no_enemy_base";
            false
        };
        (_theirBase get "position") params ["_theirEast", "_theirNorth"];
        private _theirBaseAt = [_theirEast, _theirNorth, 0];

        private _towards = createHashMap;
        private _closest = 1e10;
        {
            private _neighbour = [_x] call cti_probe_fnc_placeNamed;
            if (count _neighbour > 0) then {
                (_neighbour get "position") params ["_nEast", "_nNorth"];
                private _range = [_nEast, _nNorth, 0] distance2D _theirBaseAt;
                if (_range < _closest) then {
                    _closest = _range;
                    _towards = _neighbour;
                };
            };
        } forEach (_place getOrDefault ["adjacent", []]);
        if (count _towards isEqualTo 0) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed playtest_fixture_front_has_no_neighbour front=%1", _front];
            false
        };
        (_towards get "position") params ["_thatEast", "_thatNorth"];
        ([_centre, [_thatEast, _thatNorth, 0], 1000] call cti_probe_fnc_approach) params ["_at"];

        private _lane = 0;
        {
            {
                private _spot = _at getPos [(_lane * 50) + (_forEachIndex * 5), 90];
                _x setPosATL [_spot # 0, _spot # 1, 0];
            } forEach units _y;
            _lane = _lane + 1;
        } forEach _theirs;
        diag_log format ["CTI|playtest_fixture_enemy_massed squads=%1 grid=%2 range=%3 at=%4",
            count _theirs, mapGridPosition _at, _at distance2D _centre, time];
        true
    };

    // The state card, checked rather than described. Every line of it is read
    // back out of the world after the fact, so a brief that quotes this fixture
    // is quoting something that was true.
    private _readTheCard = {
        private _mine = call _ownedByWest;
        private _ours = call _westSquads;
        private _theirs = call _eastSquads;
        private _place = [_front] call cti_probe_fnc_placeNamed;
        (_place get "position") params ["_east", "_north"];
        private _centre = [_east, _north, 0];
        private _closing = 0;
        {
            if (!isNull _y && { (leader _y) distance2D _centre < 1500 }) then {
                _closing = _closing + 1;
            };
        } forEach _theirs;

        diag_log format ["CTI|playtest_fixture_state held=%1 west_squads=%2 east_squads=%3 massing_within_1500m=%4 front=%5",
            _mine, count _ours, count _theirs, _closing, _front];

        if (count _mine < count _held || { count _ours < count _held } || { _closing < 2 }) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed playtest_fixture_state_not_reached held=%1 west=%2 massing=%3",
                count _mine, count _ours, _closing];
            false
        };
        true
    };

    {
        _x params ["_name", "_phase"];
        if !(call _phase) exitWith { _stopped = _name };
    } forEach [
        ["buy", _buyTheForce],
        ["ground", _takeTheGround],
        ["orders", _postTheGarrisons],
        ["massing", _massTheEnemy],
        ["card", _readTheCard]
    ];
    if (_stopped isNotEqualTo "") exitWith {
        diag_log format ["CTI|playtest_fixture_stopped phase=%1 at=%2", _stopped, time];
        diag_log format ["CTI|playtest_fixture probe_done reason=staging_failed phase=%1", _stopped];
    };

    // ------------------------------------------------ the window
    // From here this is `session-hold.sqf` and nothing else: the session is a
    // person playing for a set time, and the only two ways it ends are the clock
    // running out or the Campaign being won (#35 broadcasts the outcome the
    // moment it is decided). Sized by CTI_PROBE_SOAK so the session length lives
    // on the boot line, and the clock starts here rather than at mission start —
    // the staging above is not part of anybody's half hour.
    private _window = 1800;
    if (!isNil "CTI_PROBE_SOAK" && { CTI_PROBE_SOAK > 0 }) then { _window = CTI_PROBE_SOAK };
    private _until = diag_tickTime + _window;
    diag_log format ["CTI|playtest_fixture_ready window=%1 staged_in=%2", _window, round time];

    waitUntil { !isNil "cti_campaignOutcome" || { diag_tickTime > _until } };

    diag_log format ["CTI|playtest_fixture probe_done reason=%1 at=%2",
        ["window_closed", "campaign_won"] select (!isNil "cti_campaignOutcome"),
        round diag_tickTime];
};
