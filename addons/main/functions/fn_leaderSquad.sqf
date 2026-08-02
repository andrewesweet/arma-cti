/*
 * Author: arma-cti
 * Which Squad a machine's player leads, if any. Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * one caller is cti_fnc_portGateway, which has already decided the machine
 * (#118, ADR-0041).
 *
 * The second principal's half of the stamp (ADR-0040). cti_fnc_commanderSide
 * answers "which side does the server's own assignment state say this machine
 * commands"; this answers "which Squad does the server's own record say this
 * machine's player is leading", and the gateway asks the second only when the
 * first says nobody. Both are facts about the server's state rather than claims
 * in a payload, which is the whole of why the Command Port can take a Command
 * from a rifleman's machine at all.
 *
 * The record is the one cti_fnc_effectApply writes when a Squad is spawned: the
 * group carries `cti_squad`, the id the daemon minted. So a Squad's leader is
 * whoever the engine currently calls `leader` of that group — which is the
 * honest reading of "his own Squad" for a Squad whose leadership passes to the
 * engine AI on death and back to the player on respawn (CONTEXT.md). A player
 * standing in a group nobody bought leads no Squad and gets "", as does one who
 * is in a Squad but is not leading it.
 *
 * Resolved every time rather than cached against the machine id, for the reason
 * cti_fnc_commanderSide gives: a reconnecting player is the same person on a new
 * machine id. Here it also has to be re-read because leadership genuinely moves
 * within one Play Session, which is exactly what a cache would freeze.
 *
 * Arguments:
 * 0: the machine network id <NUMBER>, as remoteExecutedOwner gives it
 *
 * Return Value: <ARRAY> [side name <STRING>, Squad id <STRING>] — the side as
 * the daemon and the manifest spell it, and the Squad that machine's player
 * leads. ["", ""] when it leads none.
 */
params [["_owner", 0, [0]]];

// Zero is not a machine, for the reason cti_fnc_commanderSide gives: it is the
// server calling itself, or a headless client, and neither holds a player.
if (_owner <= 0) exitWith { ["", ""] };

private _answer = ["", ""];
{
    if (owner _x isEqualTo _owner) exitWith {
        private _group = group _x;
        private _squad = _group getVariable ["cti_squad", ""];
        // Leading it, not merely in it. A rifleman in a Squad is not the person
        // the Command Port widened its issuer set for (ADR-0040), and `leader`
        // is the engine's own answer to which of them is.
        if (_squad isNotEqualTo "" && { leader _group isEqualTo _x }) then {
            private _side = switch (side _group) do {
                case west: { "WEST" };
                case east: { "EAST" };
                default { "" };
            };
            // A Squad on a side the daemon does not play is a world built
            // wrongly rather than a caller's mistake, and it stays "" rather
            // than stamping a side nothing can judge.
            if (_side isNotEqualTo "") then { _answer = [_side, _squad] };
        };
    };
} forEach allPlayers;

_answer
