/*
 * Author: arma-cti
 * The one way the world talks to the daemon, and the one place a reply is
 * classified. Runs wherever the shim is loaded, which in play is the server.
 *
 * Every loop used to do this for itself, and every loop got it wrong the same
 * way (#97). The shim answers a transport failure with `{"error": "..."}` of its
 * own making (extension/src/lib.rs), which is a JSON object — so `fromJSON`
 * yields a HashMap, the only check any caller made (`isEqualType createHashMap`)
 * passed, and a dead daemon read as *success with nothing in it*. The pump found
 * no messages and looked idle, the report loop found no owners and repainted
 * nothing while counting the leg as replied, and the Command Port showed a human
 * `? — ?`. The world limped and lied at once, and nothing on screen or in the
 * log said the daemon was down.
 *
 * The distinction that fixes it is not "is there an `error` key" but "is there a
 * `status`". Every reply the daemon can produce carries one — ok, rejected or
 * error, three things, total by construction (`cti_daemon.protocol`, exported as
 * `reply_envelope` in the Command schema). The shim's own error object carries
 * no `status` at all, because the shim never reached anything that could give it
 * one. So absence of `status` is exactly "the daemon was not spoken to", and it
 * cannot be forged by a daemon reply.
 *
 * Callers get a typed outcome they must branch on:
 *
 *   ok             the daemon judged and agreed; `result` carries the judgement
 *   rejected       the daemon judged and refused; `reason` carries the code
 *   error          the daemon could not answer as asked; `error` carries a class
 *   unreachable    the shim never reached the daemon; the world is on its own
 *   unreadable     something answered and it was not a reply (oracle_disagreement)
 *   no_shim        no extension is loaded; nothing was attempted
 *   campaign_lost  the daemon restarted under us; nothing is attempted any more
 *
 * There is no branch that reads a result without having established that there
 * is one, which is the property the four converted call sites lacked.
 *
 * Two pieces of world state are kept here because this is the only place that
 * can see them, and both are broadcast so a client — #18's map, eventually —
 * can read them without asking the server:
 *
 *   cti_daemon_down     <BOOL> the last call did not reach the daemon. Latched
 *                       on the first failure and cleared on the first success,
 *                       each said once, so a dead daemon is one line and a
 *                       recovery is one line rather than a cadence of noise.
 *   cti_daemon_epoch    <STRING> which daemon process the world has been talking
 *                       to (#96). Latched on first contact; a change is a
 *                       different Campaign and goes to cti_fnc_campaignLost.
 *
 * `cti_daemon_down` is deliberately *not* a CTI|FAIL line. A daemon that has
 * gone away is news, and the world says so — but the harness reads `FAIL
 * class=` as a verdict and stops the run at the first one, so typing a
 * transient outage that way would end every run in which the daemon so much as
 * hiccupped before the world could report what it did about it. The verdict
 * class is spent on the epoch change instead: the moment the world would
 * otherwise start lying (ADR-0036).
 *
 * Arguments:
 * 0: request id <STRING> — unique per request; the daemon deduplicates on the
 *    whole line (#69, ADR-0034), so a reused id on identical content is a replay
 * 1: verb <STRING>
 * 2: payload <HASHMAP> (optional, default empty)
 *
 * Return Value: <HASHMAP> with `outcome` <STRING> and, according to it,
 * `result` / `reason` / `error` <HASHMAP>, plus `reply` <HASHMAP> (the whole
 * decoded reply, for forwarding to a Commander) and `raw` <STRING>.
 */
params [["_id", "", [""]], ["_verb", "", [""]], ["_payload", createHashMap, [createHashMap]]];

// Built once here rather than at seven call sites, so that adding a key to the
// outcome cannot leave a caller reading a key that is missing.
private _answer = {
    params ["_outcome", ["_reply", createHashMap], ["_raw", ""]];
    createHashMapFromArray [
        ["outcome", _outcome],
        ["reply", _reply],
        ["raw", _raw],
        ["result", _reply getOrDefault ["result", createHashMap]],
        ["reason", _reply getOrDefault ["reason", createHashMap]],
        ["error", _reply getOrDefault ["error", createHashMap]]
    ]
};

// Once the Campaign is lost there is nothing honest left to ask for: the daemon
// on the other end holds a different Campaign, and every answer it gives is
// about a world this one is not in. Refused here rather than in each loop, so
// that a caller added later is frozen by construction rather than by memory.
if (missionNamespace getVariable ["cti_campaign_lost", false]) exitWith {
    ["campaign_lost"] call _answer
};

private _extension = call cti_fnc_shimName;
if (_extension isEqualTo "") exitWith {
    diag_log format ["CTI|FAIL class=infra_unavailable daemon_call_no_shim verb=%1", _verb];
    ["no_shim"] call _answer
};

// The running account of the wire, for whatever wants to read it back: a probe
// cannot read the server log it is writing into, and "how many calls actually
// completed" is the number #97 found being answered with a lie.
private _tally = missionNamespace getVariable ["cti_daemonCall", createHashMap];
if (count _tally isEqualTo 0) then {
    _tally = createHashMapFromArray [["calls", 0], ["ok", 0], ["unreachable", 0]];
    missionNamespace setVariable ["cti_daemonCall", _tally];
};
_tally set ["calls", (_tally get "calls") + 1];

private _envelope = createHashMapFromArray [
    ["id", _id],
    ["verb", _verb],
    ["payload", _payload]
];
private _raw = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;

// The engine caps a `callExtension` return at 10,240 bytes and truncates in
// silence (ADR-0004). Both directions guard themselves upstream — the
// observation path at nine tenths per map in `just unit` (ADR-0030), the drain
// at nine tenths in the daemon (#67) — so reaching this is a fault rather than
// a busy world, and it is worth one line whatever the verb.
//
// The threshold is read from the generated schema rather than written here
// (#78, ADR-0017). It used to be a literal held equal to `cti_daemon.budget`'s
// by a test that grepped this file's source; the exported document is the seam
// that carries a number to SQF, so a changed budget reaches the guard that
// enforces it through `just generate` instead of through whoever remembered.
// A missing or unparseable export is already a `schema_stale` FAIL from
// cti_fnc_commandSchema, which is louder than this line and fires first.
private _guard = (call cti_fnc_commandSchema) getOrDefault ["reply_guard_bytes", 0];
if (_guard > 0 && { count _raw >= _guard }) then {
    diag_log format ["CTI|FAIL class=assertion_failed reply_near_return_cap verb=%1 chars=%2",
        _verb, count _raw];
};

private _reply = fromJSON _raw;
// `fromJSON` answers nil for anything it cannot parse, and a truncated reply is
// exactly that. Checked before the type test rather than after, because
// `isEqualType` against an undefined variable is a scripting error, and a
// scripting error kills the calling loop for the rest of the session (#102).
if (isNil "_reply" || { !(_reply isEqualType createHashMap) }) exitWith {
    // The bytes arrived even if they say nothing, so the transport is back —
    // the rule fn_effectPump.sqf's `_recordTransport` already states ("Any
    // reply proves the wire is back"). Ending the run here is what keeps the
    // outage after a truncated reply audible: without it the run stays at the
    // latch threshold, every `CTI|` transport line stays unwritten, and the
    // second outage is never announced (#684).
    _tally set ["consecutive_unreachable", 0];
    diag_log format ["CTI|FAIL class=oracle_disagreement daemon_reply_unreadable verb=%1 raw=%2",
        _verb, _raw];
    ["unreadable", createHashMap, _raw] call _answer
};

// The shim's own failure: it never reached anything that could set a status.
//
// The consecutive-unreachable run is counted here because this is the one place
// every caller's transport failure passes through, and the latch is #72's: a
// daemon that died mid-run used to earn an identical `daemon_unreachable` line
// at every loop's poll cadence for the rest of the window — noise in the
// evidence, load on nothing. After the run reaches the latch threshold, the
// per-call line goes quiet and the fact is said once. The calls themselves
// never stop: the first reply to get through is what lets the world notice a
// restarted daemon (cti_fnc_campaignLost reads the epoch off it), so a call-
// suppressing latch here would trade legible evidence for a world that can
// never hear that the daemon came back. The effect pump paces its own asks
// after the threshold; this function still sends every call its caller makes.
if !("status" in _reply) exitWith {
    _tally set ["unreachable", (_tally get "unreachable") + 1];
    private _run = (_tally getOrDefault ["consecutive_unreachable", 0]) + 1;
    _tally set ["consecutive_unreachable", _run];
    // This run counts transport errors from every caller of cti_fnc_daemonCall.
    // Five effect-pump poll intervals at its default cadence span ten seconds;
    // the pump's ack and other callers can make this shared run reach five
    // sooner. That is long enough that nothing transient is still being waited
    // out, and short enough that the latch arrives inside any probe window long
    // enough to care about it. This shared threshold is independent from
    // fn_effectPump.sqf's pump-only `_latchAfter` in both the ways two counters
    // can be independent: in denominator (every caller's transport error lands
    // here; the pump counts only its own polls) and in reset condition (this
    // run ends on any reply that arrives and parses — `unreadable` included,
    // by the same rule the pump's `_recordTransport` states — while the pump
    // resets on any outcome that is not `unreachable`). Read from the tally
    // rather than a local, so a caller reading `cti_daemonCall` sees the run
    // the log is being quieted against.
    private _latchAfter = 5;
    if (_run < _latchAfter) then {
        diag_log format ["CTI|daemon_unreachable verb=%1 detail=%2",
            _verb, _reply getOrDefault ["error", "(none given)"]];
    };
    if (_run isEqualTo _latchAfter) then {
        diag_log format ["CTI|daemon_gone_latched consecutive=%1 detail=%2 "
            + "— daemon_unreachable lines quiet until the daemon answers",
            _run, _reply getOrDefault ["error", "(none given)"]];
    };
    if !(missionNamespace getVariable ["cti_daemon_down", false]) then {
        missionNamespace setVariable ["cti_daemon_down", true, true];
        diag_log "CTI|daemon_down the world has stopped hearing from the daemon";
        ["The strategic daemon has stopped answering. Nothing on the map is "
            + "moving until it does.", "PLAIN DOWN", 1] remoteExec ["titleText", -2];
    };
    ["unreachable", _reply, _raw] call _answer
};

// The daemon answered, so whatever it said, the transport is back: the run of
// consecutive transport errors ends here — as it already ended on the
// `unreadable` exit above, by the same rule — and the quieted log line
// unquiets with it (the latch is said again on the next outage, not on this
// recovery — the recovery has its own line below).
_tally set ["consecutive_unreachable", 0];

// Who answered (#96, ADR-0036). Read before the status is acted on: a reply from
// a daemon that is not the one this Campaign belongs to must not be applied,
// whatever it says.
private _epoch = _reply getOrDefault ["epoch", ""];
if (_epoch isEqualTo "") then {
    // Addon and daemon ship together, so a reply without one is a mismatched
    // build rather than a fault of the run.
    diag_log format ["CTI|FAIL class=assertion_failed daemon_reply_without_epoch verb=%1", _verb];
} else {
    private _known = missionNamespace getVariable ["cti_daemon_epoch", ""];
    if (_known isEqualTo "") then {
        missionNamespace setVariable ["cti_daemon_epoch", _epoch, true];
        diag_log format ["CTI|daemon_epoch_latched epoch=%1", _epoch];
    } else {
        if (_epoch isNotEqualTo _known) then { [_known, _epoch] call cti_fnc_campaignLost };
    };
};
if (missionNamespace getVariable ["cti_campaign_lost", false]) exitWith {
    ["campaign_lost", _reply, _raw] call _answer
};

if (missionNamespace getVariable ["cti_daemon_down", false]) then {
    missionNamespace setVariable ["cti_daemon_down", false, true];
    diag_log "CTI|daemon_recovered the world is hearing from the daemon again";
    ["The strategic daemon is answering again.", "PLAIN DOWN", 1] remoteExec ["titleText", -2];
};

private _status = _reply getOrDefault ["status", ""];
switch (_status) do {
    case "ok": {
        _tally set ["ok", (_tally get "ok") + 1];
        ["ok", _reply, _raw] call _answer
    };
    // Understood and refused on the rules. A caller's mistake, not a fault, and
    // it belongs in front of whoever made it rather than in a FAIL line.
    case "rejected": { ["rejected", _reply, _raw] call _answer };
    default {
        // The daemon could not answer as asked: `internal`, `malformed_request`,
        // `unknown_verb`, `oversized_message`. Every one of them is our bug.
        private _error = _reply getOrDefault ["error", createHashMap];
        diag_log format ["CTI|FAIL class=assertion_failed daemon_error verb=%1 error=%2 detail=%3",
            _verb,
            _error getOrDefault ["class", "?"],
            _error getOrDefault ["detail", ""]];
        ["error", _reply, _raw] call _answer
    };
};
