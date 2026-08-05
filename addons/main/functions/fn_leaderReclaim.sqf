/*
 * Author: arma-cti
 * Gives a Squad back to its player when he rejoins it. Runs on the server.
 *
 * ADR-0052's ruling 4 splits a leader's death in two, and only half of it is
 * ours. The engine promotes an AI when a player-leader dies, the Squad stays on
 * the server (ADR-0039) and its standing Order survives because waypoints belong
 * to the group rather than to whoever leads it — nothing to build. But nothing
 * in the engine demotes a live leader, so the way back is mission SQF, and this
 * is it.
 *
 * ## On rejoining, not on respawn
 *
 * The ruling's own word, and its own logic. A player respawns at his Base
 * (ruling 1) which may be the far end of the island from his men; handing him
 * the Squad there would have it break off whatever it was told to do and march
 * to form on him, and "the Squad keeps executing its standing Orders" is the
 * same ruling refusing exactly that. So leadership waits on proximity. Between
 * respawn and rejoin he is a rifleman in his own Squad and the Command Port
 * answers him honestly, because cti_fnc_leaderSquad stamps the engine's current
 * `leader` and nothing else.
 *
 * A watch rather than a respawn hook, for ADR-0025's consequence: a client-side
 * hook would need a way to tell the server, and the CfgRemoteExec whitelist is
 * one function long and stays that way. The server can already see everything
 * this decision needs — who is in the group, who leads it, who is alive, and how
 * far apart they are — so it asks itself on a cadence and no new call crosses
 * the wire.
 *
 * ## Why the locality guard is a condition and not an assumption
 *
 * `selectLeader` is `arg= local` (commands/selectLeader.wiki): it does nothing
 * unless the group is local to the machine calling it. A Squad is the server's
 * for its whole life under ADR-0039 — with one engine-owned exception this
 * function is the other side of. An AI group with a player-leader is local to
 * that player's computer, and when the player-leader dies the engine transfers
 * it to wherever the new leader is local, which for an AI successor is the
 * server (topics/Multiplayer_Scripting.wiki:219,231). So the group is the
 * server's exactly while it is being led by AI, which is exactly when there is
 * something to reclaim — and it stops being the server's the instant this
 * succeeds, which is what stops the next sweep repeating the call.
 *
 * The engine's other warning about `selectLeader` cannot bite here: a unit that
 * is not in the group becomes its leader without being able to command it. The
 * claimant is drawn from `units _group`, so there is no such unit to pass.
 *
 * Arguments:
 * 0: seconds between sweeps <NUMBER> (optional, default 5)
 * 1: how close he has to be, in metres <NUMBER> (optional, default 100)
 *
 * Return Value: <SCRIPT> the sweep thread
 */
#include "\cti\addons\main\script_component.hpp"

// ---- playtest-tuned placeholder (ADR-0020) --------------------------------
// 100 m is "back with his Squad" rather than "on the same hill as it": a Squad
// in formation is spread over about fifty, so this is close enough that the
// formation snap on taking command is a few paces and not a march. ADR-0052
// names it a placeholder in the same breath as the 30 s timer — playtest moves
// it without reopening the ruling. Too small and a player jogging alongside his
// men never gets them back; too large and he takes command from across a valley
// he has not crossed, which is the thing the rejoin reading exists to prevent.
params [["_interval", 5, [0]], ["_distance", 100, [0]]];

// The entry point of a supervised loop, which ADR-0041 keeps guarded: this is
// the one call site a future restart would re-enter, and the thread it starts is
// inventoried by name rather than by caller (#118).
SERVER_ONLY(scriptNull);

diag_log format ["CTI|leader_reclaim_started interval=%1 distance=%2", _interval, _distance];

// Paced, heartbeated and watched by the one adapter every loop in the addon
// runs on (#85).
["leader_reclaim", _interval, [_distance], {
    params ["_distance"];

    {
        private _squadId = _x;
        private _group = _y;

        // Squads the world has lost are cti_fnc_orderEnforce's to prune; this
        // sweep only declines to read them. Two loops deleting from one HashMap
        // is a race for no gain.
        if (!isNull _group
            && { units _group isNotEqualTo [] }
            // Not the server's group: someone alive is already leading it from
            // their own machine, and `selectLeader` would do nothing anyway.
            && { local _group }) then {
            private _leader = leader _group;

            // A live player already has it. Without this, a Squad holding two
            // players would hand leadership back and forth every sweep.
            if (!(isPlayer _leader && { alive _leader })) then {
                private _claimant = objNull;
                {
                    if (isPlayer _x
                        && { alive _x }
                        && { _x isNotEqualTo _leader }
                        && { _x distance2D _leader <= _distance }) exitWith { _claimant = _x };
                } forEach units _group;

                if (!isNull _claimant) then {
                    _group selectLeader _claimant;
                    diag_log format ["CTI|leader_reclaimed squad=%1 player=%2 was=%3 distance=%4",
                        _squadId, name _claimant, name _leader,
                        round (_claimant distance2D _leader)];
                };
            };
        };
    } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
}] call cti_fnc_everyInterval
