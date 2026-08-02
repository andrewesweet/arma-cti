/*
 * Author: arma-cti
 * The world stops pretending: the daemon that holds this Campaign is gone, and
 * the one answering now holds a different one. Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * one caller is cti_fnc_daemonCall, and nothing speaks to the daemon off the
 * server (ADR-0018) — every path in starts in
 * `missions/cti.Stratis/initServer.sqf` (#118, ADR-0040).
 *
 * The daemon's whole strategic state is in memory and nothing persists it yet
 * (#4 is Phase 2's, ADR-0008/0023). So a restart mid-session is a factory-fresh
 * Campaign: every Objective NEUTRAL again, Funds back to the starting balance,
 * the Domination clock restarted, and every fielded Squad an orphan the new
 * daemon never minted and will not take Orders for. Before the epoch handshake
 * (#96, ADR-0036) the world absorbed all of that in silence, because the shim's
 * reconnect is invisible from SQF and the next poll simply succeeded.
 *
 * What is *not* being built here is resumption. Carrying a Campaign across a
 * restart is #4's, and gated behind a persistence design that does not exist.
 * The requirement this meets is narrower and is the one a player is owed
 * immediately: a Campaign must never be reset silently underneath them.
 *
 * So the world freezes rather than plays on. `cti_fnc_daemonCall` refuses every
 * subsequent call once this latch is set, which means — without any loop being
 * changed for it — no marker repaints to a stranger's ownership, no effect from
 * a Campaign this world was not in is applied, no Commander is shown a view of
 * somebody else's board, and no Command spends Funds that no longer exist. The
 * loops keep turning and cost nothing; the map is left showing the last thing
 * that was true.
 *
 * Frozen rather than ended: `endMission` would take the evidence of the
 * Campaign down with it, and the MVP topology often has nobody to show an end
 * screen to (the same reasoning as cti_fnc_campaignEnd's). What the human gets
 * is a caption saying what happened and what to do about it.
 *
 * Arguments:
 * 0: the epoch the world had been talking to <STRING>
 * 1: the epoch answering now <STRING>
 *
 * Return Value: <BOOL> whether this call was the one that latched it.
 */
params [["_was", "", [""]], ["_now", "", [""]]];

if (missionNamespace getVariable ["cti_campaign_lost", false]) exitWith { false };

// Broadcast, and set before anything else: the caption and the log line below
// both take time, and a second loop reaching the same conclusion in between
// must find the latch already thrown rather than announce it twice.
missionNamespace setVariable ["cti_campaign_lost", true, true];

// The one CTI|FAIL the daemon-call path spends a verdict class on. `node_crashed`
// from CLAUDE.md's table, and it means what the table says: collect what there
// is and escalate to a human, because nothing in the world can recover this.
diag_log format ["CTI|FAIL class=node_crashed daemon_epoch_changed was=%1 now=%2 "
    + "the daemon restarted and this Campaign is gone", _was, _now];

// Clients only (-2): the server has no screen, and server-to-client remoteExec
// is unrestricted, so nothing here needs the mission's mode=1 whitelist
// (ADR-0012). Same direction and same reason as cti_fnc_campaignEnd's caption.
private _caption = "CAMPAIGN LOST. The strategic daemon restarted, so nothing you do now is being recorded. Restart the mission.";
[_caption, "PLAIN DOWN", 1] remoteExec ["titleText", -2];

true
