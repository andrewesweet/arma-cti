/*
 * Author: arma-cti
 * The Command Port's only door (ADR-0012). Runs on the server.
 *
 * A human Commander builds a Command client-side and remoteExecs this. The
 * mission whitelists this function alone at CfgRemoteExec mode=1, so it is the
 * only thing a client may call — which is what mechanically closes the
 * client-to-server side of "no order path outside the port". A client that
 * loaded the shim and spoke to the daemon directly would be an order path
 * outside the port, and that is what #19's audit exists to catch.
 *
 * The acting side is stamped here from the caller's own identity and the
 * client's `side` field is overwritten, never validated: a Commander's
 * authority is a fact about the server's state, not a claim in a payload.
 *
 * Arguments:
 * 0: the Command <HASHMAP> as built by cti_fnc_command
 *
 * Return Value: <BOOL> whether the Command was sent to the daemon. The
 * judgement itself comes back to the caller through cti_fnc_portReply.
 */
#include "\cti\addons\main\script_component.hpp"

params [["_command", createHashMap, [createHashMap]]];

// Belt and braces against a `description.ext` regression, which is exactly the
// failure a config cannot defend against itself (#118, ADR-0040).
SERVER_ONLY(false);

private _owner = remoteExecutedOwner;

// remoteExecutedOwner is 0 when the call did not arrive over the network — the
// server calling itself, or the AI Commander, which reaches the port in-process
// on the Python side and should never be here.
//
// The side comes from the server's own commander-assignment state (#18,
// cti_fnc_commanderAssign) rather than from the caller's unit. A squad leader
// fighting for WEST is on WEST and is not WEST's Commander, and stamping the
// group's side would have handed the Command Port to every rifleman on the
// island.
private _side = [_owner] call cti_fnc_commanderSide;
private _schema = call cti_fnc_commandSchema;

// Empty is fatal, and cti_fnc_commandSchema's contract says so. This used to
// read `_schema get "sides"` straight through it, so a server with no export
// answered the door with a script error in the middle of judging identity —
// the one place in the addon where a raw error is also a security surface,
// because the caller is a client and the thing being decided is whether it may
// command a side. Refused here, typed as the schema fault it is (#80), and the
// same guard cti_fnc_commanderAssign already carries.
//
// Asked as "is the side list there" rather than "is the schema empty", for the
// reason cti_fnc_command's guard gives: one condition covers a missing export
// and an export that parsed into something without a side list in it, and the
// second is the one that can be staged in-world.
//
// No judgement goes back to the caller: a rejection is drawn from the schema's
// own code vocabulary and there is no schema to draw one from. A client that
// reached this door at all had a schema of its own to build the Command with,
// so a server that has none is a broken build to escalate rather than a
// Commander's mistake to answer.
if !("sides" in _schema) exitWith {
    diag_log format ["CTI|FAIL class=schema_stale port_gateway_no_schema owner=%1 schema_keys=%2",
        _owner, count _schema];
    false
};

if !(_side in (_schema get "sides")) exitWith {
    // Identity is the gateway's business, so it answers this one itself rather
    // than asking the daemon about a caller the daemon cannot see.
    private _judgement = createHashMapFromArray [
        ["status", "rejected"],
        ["reason", createHashMapFromArray [
            ["code", "wrong_side"],
            ["detail", "this machine commands no side: the Command Port takes "
                + "Commands from the person in a Commander slot and from nobody else"]
        ]]
    ];
    if (_owner > 0) then { [_judgement] remoteExec ["cti_fnc_portReply", _owner] };
    diag_log format ["CTI|port_rejected owner=%1 code=wrong_side", _owner];
    false
};

_command set ["side", _side];

// Synchronous by construction: ADR-0012 makes a Command's reply a judgement and
// never work, so it never waits on anything and stays far inside the engine's
// 1000 ms blocking-call stall cap (ADR-0005).
// Counted rather than clocked: two Commands from two machines in the same
// millisecond after a scheduler stall shared an id, and an id is what the daemon
// deduplicates on (#103, ADR-0034).
private _id = ["cmd", str _owner] call cti_fnc_requestId;
private _answer = [_id, "command", _command] call cti_fnc_daemonCall;
private _outcome = _answer get "outcome";

// A judgement is the only thing worth forwarding. Everything else is the port
// failing to reach the rules rather than the rules speaking, and the Commander
// used to be handed it anyway: a shim error object rendered as `? — ? —` and a
// dead daemon looked exactly like a refusal nobody could argue with (#97). The
// answer here is the port's own, in the port's own vocabulary.
if !(_outcome in ["ok", "rejected"]) exitWith {
    diag_log format ["CTI|port_command id=%1 side=%2 command=%3 outcome=%4",
        _id, _side, _command get "command", _outcome];
    private _judgement = createHashMapFromArray [
        ["status", "rejected"],
        ["reason", createHashMapFromArray [
            ["code", "port_unavailable"],
            ["detail", "the Command Port could not reach the daemon, so this "
                + "Command was not judged and nothing was spent"]
        ]]
    ];
    if (_owner > 0) then { [_judgement] remoteExec ["cti_fnc_portReply", _owner] };
    false
};

private _judgement = _answer get "reply";
diag_log format ["CTI|port_command id=%1 side=%2 command=%3 status=%4",
    _id, _side, _command get "command", _judgement getOrDefault ["status", "?"]];

// Server-to-client remoteExec is unrestricted; mode=1 binds clients only.
if (_owner > 0) then { [_judgement] remoteExec ["cti_fnc_portReply", _owner] };

true
