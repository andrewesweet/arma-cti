/*
 * Author: arma-cti
 * One server-side reading of every connected user's network health.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * one caller is cti_fnc_desyncWatch, started from
 * `missions/cti.Stratis/initServer.sqf`, which the engine runs on the server and
 * nowhere else (#118, ADR-0040). `getUserInfo`'s own server-execution-only rule
 * is the second fence, and it is the engine's rather than ours.
 *
 * `getUserInfo` index 9 is `networkInfo` — [ping, bandwidth, desync] — which
 * turns "the client felt stuck" into a number (commands/getUserInfo.wiki, since
 * 2.06, server execution only). Phase 0 found it absent from the server.cfg
 * scripting VM, so it has to be read from mission context, which is here.
 *
 * Index 6 is the client state and 7 the headless flag, both carried through so
 * a sample says which rung a client is on rather than leaving it to be guessed.
 *
 * Arguments: none
 *
 * Return Value: <ARRAY> of [name, uid, clientState, isHeadless, ping,
 * bandwidth, desync], one per connected user
 */
private _samples = [];
// No `isNil "allUsers"` guard below: isNil tests a *variable* of that name, and
// `allUsers` is a command, so such a guard always fires and silently returns
// nothing. Phase 0 logged "allUsers unavailable" on every run for exactly that
// reason — the command has been there since 2.06 and this addon requires 2.2.
{
    private _info = getUserInfo _x;
    if (count _info > 9) then {
        (_info # 9) params [["_ping", -1], ["_bandwidth", -1], ["_desync", -1]];
        _samples pushBack [_info # 3, _info # 2, _info # 6, _info # 7, _ping, _bandwidth, _desync];
    };
} forEach allUsers;

_samples
