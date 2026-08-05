// Shared probe scaffolding, appended to the generated harness by spike/run.sh
// ahead of the probe itself. It lives here rather than in spike/probes/ because
// corpus membership is by directory (docs/regression-tier.md, "What runs"): a
// file in there is a probe, and this asserts nothing.
//
// Not in the addon either. Nothing here is game code; it is the scaffolding a
// probe stands on to ask the world questions, and the addon is the thing under
// test. Nothing in here asserts anything about the code under test either — the
// exceptions state a fault in the *staging*, which is the probe's own.
//
// The `cti_probe_fnc_` prefix keeps it out of the addon's `cti_fnc_` namespace,
// which CfgFunctions owns.
//
// A helper earns a place here by being copied, not by being reusable in
// principle. #86 moved seven idioms in that the corpus had between three and ten
// hand-written copies of, and reconciling the copies is where the drift showed
// up — every reconciliation is recorded on the helper it landed in.

// Wait for the world to be built and for both server loops to have turned once,
// with the caller's deadline. #46 converted eight probes' identical 20 s "let
// the world finish building and the report loop get a cycle in" settles to this
// call, at the same 20 s: the settle was always a proxy for three conditions the
// world states out loud, so a passing run now leaves at ~6 s and a run in which
// a loop never turns carries on at 20 s exactly as it did before, into the same
// assertions and the same class.
//
// The three: the manifest's world is built (`cti_map` holds Objectives), the
// effect pump has polled the daemon (`cti_effectDrain`), and a presence report
// has gone out and had its judgement applied (`cti_presenceReport`, added for
// this). All three are our own counters, which is what makes waiting on them as
// good as an event — we write them.
//
// Arguments:
// 0: deadline in seconds <NUMBER> (optional, default 20 — the settle it replaced)
//
// Return Value: <NUMBER> seconds waited
cti_probe_fnc_worldReady = {
    params [["_by", 20, [0]]];

    private _from = diag_tickTime;
    private _deadline = _from + _by;
    private _polls = 0;
    private _replied = 0;
    private _objectives = 0;
    waitUntil {
        _objectives = count ((missionNamespace getVariable ["cti_map", createHashMap])
            getOrDefault ["objectives", []]);
        _polls = (missionNamespace getVariable ["cti_effectDrain", createHashMap])
            getOrDefault ["polls", 0];
        _replied = (missionNamespace getVariable ["cti_presenceReport", createHashMap])
            getOrDefault ["replied", 0];
        (_objectives > 0 && { _polls > 0 } && { _replied > 0 })
            || { diag_tickTime > _deadline }
    };

    private _waited = diag_tickTime - _from;
    // Logged rather than asserted on: this is the probe's runway, and every
    // probe that calls it has its own assertions about the world immediately
    // after. A world that was not ready in `_by` fails in those, as it did when
    // this was a sleep — the line is here so the evidence says which it was.
    diag_log format ["CTI|probe_world_ready waited=%1 deadline=%2 objectives=%3 polls=%4 reports=%5",
        _waited, _by, _objectives, _polls, _replied];
    _waited
};

// The daemon's synchronous path, through the shim. Nine probes and both cycle
// legs carried a byte-identical copy of this (#86), and `contact-decay` a tenth
// that had drifted by not parsing the reply at all — which is how a refused
// Purchase in that probe surfaced sixty seconds later as `timeout`, a class that
// says the wrong thing about it (#84).
//
// Arguments:
// 0: envelope <HASHMAP> — id, verb and payload as the daemon's protocol spells
//    them
//
// Return Value: the parsed reply <HASHMAP>. `fromJSON` answers nil for a
// document it cannot read, and this passes that on rather than converting it:
// `json-manifest` asserts on exactly that case in its own words.
cti_probe_fnc_rpc = {
    params ["_envelope"];
    private _raw = ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
    fromJSON _raw
};

// One Squad bought through the Command Port, which is the only way a Squad gets
// onto the roster (ADR-0012). Seven probes built this envelope by hand, all
// differing only in the id string (#86), and every one of them threw the reply
// away — so a refusal was invisible until the wait for the Squad ran out and
// reported `timeout`, blaming synchronisation for a judgement (#84).
//
// The status is checked here, on the synchronous call, where a refusal is what
// it actually is: an `assertion_failed` about a Purchase the daemon would not
// take. Callers keep their own `timeout` for the Squad not arriving, which is
// the different failure it was always meant to name.
//
// Arguments:
// 0: the envelope id, unique per call <STRING>
// 1: the side buying <STRING> (optional, default "WEST")
// 2: the Squad type <STRING> (optional, default "rifle")
//
// Return Value: the parsed reply <HASHMAP>, empty if the shim answered nothing
// readable
cti_probe_fnc_buySquad = {
    params [["_id", "", [""]], ["_side", "WEST", [""]], ["_type", "rifle", [""]]];

    private _reply = [createHashMapFromArray [
        ["id", _id],
        ["verb", "command"],
        ["payload", createHashMapFromArray [
            ["command", "purchase"],
            ["side", _side],
            // The stamp the gateway would have written (ADR-0044). A probe runs
            // on the server, inside the boundary the whitelist defends, and
            // speaks to the shim rather than through the gateway — so it stamps
            // for itself. What it skips is the *resolution* of a caller, which
            // is the gateway's; what it may not skip is saying who is acting,
            // because an unstamped line is refused `unknown_caller`.
            ["acting_side", _side],
            ["args", createHashMapFromArray [["squad_type", _type]]]
        ]]
    ]] call cti_probe_fnc_rpc;

    private _status = "unreadable_reply";
    private _shown = "";
    if (!isNil "_reply" && { _reply isEqualType createHashMap }) then {
        _status = _reply getOrDefault ["status", ""];
        _shown = str _reply;
    };
    if (_status isNotEqualTo "ok") then {
        diag_log format ["CTI|FAIL class=assertion_failed probe_purchase_refused id=%1 side=%2 type=%3 status=%4 reply=%5",
            _id, _side, _type, _status, _shown];
    };
    if (isNil "_reply") exitWith { createHashMap };
    _reply
};

// A Place by id, off the index `cti_fnc_worldInit` derives beside `cti_map`
// (#109). Three probes carried a hand-copied linear scan over the concatenated
// objectives and bases arrays; this is the same answer as a lookup, and the
// merge cannot collide because the manifest already enforces one id namespace.
//
// Arguments:
// 0: the Place id <STRING>
//
// Return Value: the Place <HASHMAP>, empty when the id names nothing. An index
// that is not there at all is refused out loud rather than answered as "no such
// Place", because those are different faults and only one of them is the
// caller's.
cti_probe_fnc_placeNamed = {
    params [["_id", "", [""]]];

    private _index = missionNamespace getVariable ["cti_placesById", createHashMap];
    if (count _index isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed probe_places_index_absent id=%1 hint=%2",
            _id, "cti_fnc_worldInit broadcasts cti_placesById beside cti_map"];
        createHashMap
    };
    _index getOrDefault [_id, createHashMap]
};

// The approach line the three assault probes stage on: the bearing from a Base's
// HQ towards the Place the manifest calls adjacent to it, and a point that far
// out along it. Authored ground rather than a bearing off somebody's facing —
// #28's lesson, which cost two probes.
//
// #108 replaced the hand-rolled run/span/normalise/scale block three probes
// each carried with the two engine commands that already ship it:
// `pos1 getDir pos2` (commands/getDir.wiki, alternative syntax — the page says
// it "should be used instead of BIS_fnc_dirTo") and
// `origin getPos [distance, heading]` (commands/getPos.wiki, syntax 3, Arma 3
// since 1.56). The bearing comes back too, because `massed-assault` lays a line
// of men across the approach and wants the axis rather than only the point.
//
// Arguments:
// 0: the HQ's position <ARRAY>
// 1: the position to run towards <ARRAY>
// 2: how far out to stand, in metres <NUMBER> (optional, default 250)
//
// Return Value: [the approach position <ARRAY>, the bearing from the HQ <NUMBER>]
cti_probe_fnc_approach = {
    params ["_hqAt", "_towards", ["_out", 250, [0]]];

    private _dir = _hqAt getDir _towards;
    [_hqAt getPos [_out, _dir], _dir]
};

// Every Squad the world holds for one side, keyed by Squad id. Four probes had a
// copy (#86); two of them returned only a count, which `count` on this answers,
// and the map answers what a count could not.
//
// Arguments:
// 0: the side's name, as the daemon and the manifest both spell it <STRING>
//
// Return Value: <HASHMAP> Squad id -> group
cti_probe_fnc_squadsOf = {
    params [["_name", "", [""]]];

    private _side = (createHashMapFromArray [["WEST", west], ["EAST", east]])
        getOrDefault [_name, sideUnknown];
    private _found = createHashMap;
    {
        if (!isNull _y && { side _y isEqualTo _side }) then { _found set [_x, _y] };
    } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
    _found
};

// How many headless clients are connected, waited for. The MVP test topology is
// a dedicated server plus a headless client, and a run without one is a
// different run — three probes said so in identical words (#86) and each refuses
// under its own name, so this counts and the caller decides.
//
// No engine command lists headless clients; `getUserInfo`'s eighth element is
// the documented way to tell (topics/Arma_3_Headless_Client.wiki offers only
// self-detection), which is why this is a loop rather than a lookup.
//
// Arguments:
// 0: deadline in seconds <NUMBER> (optional, default 120)
//
// Return Value: <NUMBER> headless clients seen, 0 if none arrived in the window
cti_probe_fnc_headlessClients = {
    params [["_by", 120, [0]]];

    private _deadline = diag_tickTime + _by;
    private _headless = 0;
    waitUntil {
        _headless = 0;
        {
            private _info = getUserInfo _x;
            if (count _info > 7 && { _info # 7 }) then { _headless = _headless + 1 };
        } forEach allUsers;
        _headless > 0 || { diag_tickTime > _deadline }
    };
    _headless
};

// The client the server swept into a Commander slot: the side it commands, the
// UID the assignment latched, and the unit holding it. Two probes had a copy
// (#86) and they refuse differently — one in the leg grammar the runner scores,
// one not — so this finds and reports, and the caller says what an empty answer
// means.
//
// Arguments:
// 0: how long to wait for the sweep, in seconds <NUMBER> (optional, default 240)
//
// Return Value: [side name <STRING>, uid <STRING>, unit <OBJECT>]. The side is
// "" when nobody was assigned inside the window; the unit is objNull when the
// latched UID holds none.
cti_probe_fnc_commanderSlot = {
    params [["_by", 240, [0]]];

    private _deadline = diag_tickTime + _by;
    waitUntil {
        count (missionNamespace getVariable ["cti_commanders", createHashMap]) > 0
            || { diag_tickTime > _deadline }
    };

    private _assigned = missionNamespace getVariable ["cti_commanders", createHashMap];
    diag_log format ["CTI|probe_commander_slot players=%1 assigned=%2 waited=%3",
        count allPlayers, keys _assigned, _by];
    if (count _assigned isEqualTo 0) exitWith { ["", "", objNull] };

    private _side = (keys _assigned) # 0;
    private _uid = _assigned get _side;
    private _unit = objNull;
    { if (getPlayerUID _x isEqualTo _uid) exitWith { _unit = _x } } forEach allPlayers;
    [_side, _uid, _unit]
};

// Walk a planted enemy round the compass until the watching side has acquired
// somebody, and hand back the sampler's own answer.
//
// A bearing off the leader's facing is a guess about line of sight, and on an
// airfield it lands behind a hangar often enough to matter: three runs sat at
// `knows_east=0` for a whole window with the men standing 90 m away and nothing
// between them but a building. Re-placing rather than waiting longer is the fix,
// because the wait was never the problem. Nothing here tells the knowledge model
// anything — it arranges for there to be something to see, and the engine still
// decides whether it sees it.
//
// `contacts` and `contact-decay` had near-copies of this and they had drifted:
// one walked in silence, the other logged each placement and a ten-second
// progress line. #86 reconciled to the noisy one. Every finding #28 got out of
// this loop was read off those lines, and a probe that acquires nothing is
// exactly the probe whose evidence has to say why.
//
// Arguments:
// 0: the planted group to walk <GROUP>
// 1: the group doing the watching <GROUP> — its leader is re-read each pass, so
//    a replaced leader is still the observer
// 2: the reporting side's name <STRING> (optional, default "WEST")
// 3: deadline in seconds <NUMBER> (optional, default 150)
//
// Return Value: that side's last contact report <HASHMAP>
cti_probe_fnc_walkIntoView = {
    params ["_planted", "_watchers", ["_for", "WEST", [""]], ["_by", 150, [0]]];

    private _bearings = [0, 45, 90, 135, 180, 225, 270, 315];
    private _attempt = 0;
    private _nextMove = 0;
    private _nextLog = 0;
    private _deadline = diag_tickTime + _by;
    private _report = createHashMap;
    private _enemy = side _planted;
    waitUntil {
        private _watcher = leader _watchers;
        if (diag_tickTime > _nextMove) then {
            _nextMove = diag_tickTime + 15;
            private _bearing = _bearings select (_attempt mod (count _bearings));
            private _where = _watcher getRelPos [100, _bearing];
            {
                _x setPosATL [(_where # 0) + (_forEachIndex * 3), _where # 1, 0];
            } forEach units _planted;
            _attempt = _attempt + 1;
            diag_log format ["CTI|probe_walk_placing attempt=%1 bearing=%2 at=%3",
                _attempt, _bearing, mapGridPosition _where];
        };
        _report = (call cti_fnc_contactSample) getOrDefault [_for, createHashMap];
        if (diag_tickTime > _nextLog) then {
            _nextLog = diag_tickTime + 10;
            diag_log format ["CTI|probe_walk_waiting seen=%1 knows_any=%2 knows_enemy=%3 range=%4 planted_alive=%5 knowsAbout=%6",
                count (_report getOrDefault ["seen", []]),
                count (_watcher targetsQuery [objNull, sideUnknown, "", [], 0]),
                count ((_watcher targetsQuery [objNull, _enemy, "", [], 0]) select {
                    (_x # 2) isEqualTo _enemy
                }),
                _watcher distance2D (leader _planted),
                { alive _x } count units _planted,
                _watcher knowsAbout ((units _planted) # 0)];
        };
        count (_report getOrDefault ["seen", []]) > 0 || { diag_tickTime > _deadline }
    };
    _report
};

// ----------------------------------------------------------------- the leg ledger
//
// The vacuity convention's bookkeeping (ADR-0037, #116). A probe names itself
// and the legs it owes an answer for, strikes each one off as it is measured,
// and reports whatever is still standing when it stops — which the runner reads
// as `infra_unavailable` rather than as a pass.
//
// Five probes had this in three shapes (#193): `dead-principal` and `loadout`
// carried the list and the strike-off verbatim, `respawn-base` a fixed pair
// reported whole, and `client-port` and `reinforce` wrote the unverified lines
// out by hand at each exit. That last shape is the one that lets a leg be
// missed, and it had been missing them: `client-port` abandoned at its second
// step said nothing at all about the five legs after it, so the evidence named
// one unmeasured leg where six were. Under the ledger every exit reports every
// leg it never reached, and no exit has to remember which those are.
//
// The prefix is the probe's own name and it is what every shared line below is
// written under, so a probe names itself once and the ack lines, the leg lines
// and the `<probe>_probe_done` line the runner waits on all agree by
// construction.
//
// Arguments:
// 0: the probe's prefix <STRING>
// 1: the legs it owes an answer for <ARRAY> (optional, default [])
//
// Return Value: <NIL>
cti_probe_fnc_legsOwed = {
    params [["_prefix", "probe", [""]], ["_legs", [], [[]]]];
    cti_probeSelf = createHashMapFromArray [["prefix", _prefix], ["owed", +_legs]];
};

// One leg measured: struck off the ledger and said out loud.
//
// Arguments:
// 0: the leg's name, without the probe's prefix <STRING>
//
// Return Value: <NIL>
cti_probe_fnc_legRan = {
    params [["_leg", "", [""]]];

    // Struck off in place: `commands/getOrDefault.wiki` says the array comes
    // back by reference and the one in the HashMap is updated with it, so there
    // is nothing to write back.
    private _self = missionNamespace getVariable ["cti_probeSelf", createHashMap];
    private _owed = _self getOrDefault ["owed", []];
    private _at = _owed find _leg;
    if (_at >= 0) then { _owed deleteAt _at };
    diag_log format ["CTI|LEG name=%1_%2 status=ran",
        _self getOrDefault ["prefix", "probe"], _leg];
};

// The probe stops, wherever it stopped: every leg still owed is reported
// `unverified` for the given reason, and then the line the runner waits on.
// Called at an early exit with what went wrong, and at the end with nothing —
// where a ledger emptied by `cti_probe_fnc_legRan` leaves only the done line.
//
// Arguments:
// 0: why the outstanding legs were not measured <STRING> (optional, default
//    "fell_through", which is what an end that reached the bottom with legs
//    still owed means)
//
// Return Value: <NIL>
cti_probe_fnc_done = {
    params [["_why", "fell_through", [""]]];

    private _self = missionNamespace getVariable ["cti_probeSelf", createHashMap];
    private _prefix = _self getOrDefault ["prefix", "probe"];
    {
        diag_log format ["CTI|LEG name=%1_%2 status=unverified reason=%3", _prefix, _x, _why];
    } forEach (_self getOrDefault ["owed", []]);
    // Emptied, so a probe that ends twice — an `exitWith` inside a handler, say —
    // reports each leg once rather than once per exit.
    _self set ["owed", []];
    diag_log format ["CTI|%1_probe_done", _prefix];
};

// ------------------------------------------------------- driving a headed client
//
// A judgement from the Command Port arrives on the client that sent the Command,
// through `cti_fnc_portReply`, and can only be read there — so a probe that
// drives a person's machine has to arm that machine to unpack the judgement and
// publish it back. `client-port` wrote this first, `reinforce` copied it and
// `dead-principal` copied it again, which is the third copy #86's rule says
// moves a helper in here (#193).
//
// The report comes back on a public variable rather than a second `remoteExec`
// because the mode=1 whitelist is under test in two of the three probes, and a
// probe that widened it would be testing a mission that does not ship.
// Server-to-client `remoteExec` is unrestricted, which is what lets a probe
// press the key nobody is there to press.
//
// **The drift the three copies had, and how it settles.** All three unpacked the
// judgement into the same ack and disagreed only about slot 4: `client-port`
// read `funds` and took a per-step flag for the steps that were not asking about
// Funds, `reinforce` read `cost`, `dead-principal` read `funds`. None of the
// three readings is the right one to share, because the reply's `result` is
// verb-shaped and only an accepted judgement carries one at all — an accepted
// Purchase answers `funds` and no `cost`, an accepted Reinforce answers both,
// and every refusal answers an empty result (`src/cti_daemon/port.py`,
// `_accept`/`_reject`). A fixed key would therefore write the -1 sentinel into
// slot 4 for a whole probe and read as if it had measured something:
// `reinforce` asserts its refill cost is above zero, which a shared `funds`
// would have made unfalsifiable in the other direction.
//
// `client-port` was closest — it had already made the read a per-step decision —
// but it hardcoded *which* key, which is why the second copy forked rather than
// reused. So the flag generalises into the key itself, `""` meaning read nothing
// and keep -1, and that is the default: no key is right for a verb this scaffold
// cannot see. A step that expects a refusal names nothing, because a refusal has
// nothing to name.
//
// Arguments:
// 0: the client's machine id <NUMBER>, as `owner` gives it
//
// Return Value: <NIL>
cti_probe_fnc_armClient = {
    params [["_target", -1, [0]]];

    cti_probeClient = _target;
    {
        cti_probeJudge = {
            params ["_step", ["_note", ""], ["_result", "", [""]]];
            private _by = diag_tickTime + 60;
            waitUntil { !isNil "cti_lastJudgement" || { diag_tickTime > _by } };
            private _judgement = missionNamespace getVariable ["cti_lastJudgement", createHashMap];
            private _reason = _judgement getOrDefault ["reason", createHashMap];
            private _value = -1;
            if (_result isNotEqualTo "") then {
                _value = (_judgement getOrDefault ["result", createHashMap])
                    getOrDefault [_result, -1];
            };
            cti_probeAck = [
                _step,
                _judgement getOrDefault ["status", "nothing-arrived"],
                _reason getOrDefault ["code", ""],
                _reason getOrDefault ["detail", ""],
                _value,
                _note,
                _result
            ];
            publicVariable "cti_probeAck";
        };
    } remoteExec ["call", _target];
};

// One step driven on the armed client: the ack is cleared, the step's code is
// sent, and the client's own account of what came back is waited for and logged.
//
// Every ack carries the step name it belongs to, so a late one from the step
// before is discarded rather than read as this step's answer — and the wait ends
// `timeout` rather than reading a stale ack as a fresh one.
//
// A step's `_code` is a literal block sent whole rather than a call with
// arguments (`commands/remoteExec.wiki` on what to avoid), which is also why the
// judge is armed once on the client instead of written out per step: a block
// sent from here cannot close over a step's own private variables. What a step
// keeps is genuinely its own — what it sends, the note it sends about itself,
// and which key of the judgement it is asking for.
//
// Arguments:
// 0: the step's name <STRING>
// 1: the code to run on the client <CODE>
// 2: how long to wait for its ack, in seconds <NUMBER> (optional, default 90)
//
// Return Value: the ack <ARRAY> — step, status, code, detail, the value read,
// the note, and the key it was read under — or `[]` when the client stayed
// silent, which is a `timeout` the caller reports as a lost leg.
cti_probe_fnc_drive = {
    params ["_step", "_code", ["_wait", 90, [0]]];

    private _prefix = (missionNamespace getVariable ["cti_probeSelf", createHashMap])
        getOrDefault ["prefix", "probe"];
    private _target = missionNamespace getVariable ["cti_probeClient", -1];
    if (_target < 0) exitWith {
        // A fault in the staging, not in the code under test: without a client
        // to send to, `remoteExec` would broadcast the step to every machine.
        diag_log format ["CTI|FAIL class=assertion_failed %1_probe_client_unarmed step=%2 hint=%3",
            _prefix, _step, "cti_probe_fnc_armClient is what says which machine a step is driven on"];
        []
    };

    cti_probeAck = nil;
    _code remoteExec ["call", _target];
    private _by = diag_tickTime + _wait;
    waitUntil {
        (!isNil "cti_probeAck" && { (cti_probeAck # 0) isEqualTo _step })
            || { diag_tickTime > _by }
    };
    if (isNil "cti_probeAck" || { (cti_probeAck # 0) isNotEqualTo _step }) exitWith {
        diag_log format ["CTI|FAIL class=timeout %1_probe_client_silent step=%2", _prefix, _step];
        []
    };

    private _ack = +cti_probeAck;
    // The key names the number in the evidence, so a line says what it measured
    // rather than which slot it came out of. An ack built on the client by hand
    // rather than by the judge carries no key, and reads as the bare `result` it
    // is; `param` is what tolerates that shorter ack.
    private _key = _ack param [6, ""];
    if (_key isEqualTo "") then { _key = "result" };
    diag_log format ["CTI|%1_probe_ack step=%2 status=%3 code=%4 %5=%6 note=%7",
        _prefix, _ack # 0, _ack # 1, _ack # 2, _key, _ack # 4, _ack # 5];
    _ack
};
