/*
 * Author: arma-cti
 * Receives the judgement on a Command this client sent. Runs on the client.
 *
 * The judgement is advisory (ADR-0012): it may say the Command was accepted and
 * what Funds remain, but it never instructs the world to change. Every world
 * effect arrives separately, through the outbox, so a human-issued effect and
 * an AI-issued one travel the same path.
 *
 * A refusal reaches the player in the port's own words (#18). The code is the
 * one the planner consumes and the detail is the one the daemon wrote — there
 * is no human-readable translation table here, because a table is where the two
 * vocabularies would start to differ, and the daemon's details already say what
 * to do instead ("order Defend to garrison it").
 *
 * Arguments:
 * 0: the judgement <HASHMAP> — `status` of "ok" or "rejected", with `reason`
 *    carrying `code` and `detail` when rejected
 *
 * Return Value: none
 */
#include "\cti\addons\main\script_component.hpp"

params [["_judgement", createHashMap, [createHashMap]]];

// One of the two doors the server pushes through, and server-to-client
// remoteExec is unrestricted (topics/Arma_3_CfgRemoteExec.wiki), so
// `description.ext` offers no protection here and this guard is the only thing
// there is (#114, #118, ADR-0041). `hasInterface` is false for a dedicated
// server and a headless client alike (`commands/hasInterface.wiki`), and a
// judgement is for a person.
INTERFACE_ONLY(nil);

cti_lastJudgement = _judgement;

private _status = _judgement getOrDefault ["status", "?"];
if (_status isEqualTo "ok") exitWith {
    private _result = _judgement getOrDefault ["result", createHashMap];
    diag_log format ["CTI|judgement status=ok funds=%1", _result getOrDefault ["funds", "?"]];
    cti_lastJudgementText = format ["<t color='#88ff88'>accepted</t> — Funds %1",
        _result getOrDefault ["funds", "?"]];
    if !(isNil "cti_uiSide") then { [] call cti_fnc_mapRender };
};

private _reason = _judgement getOrDefault ["reason", createHashMap];
diag_log format ["CTI|judgement status=%1 code=%2 detail=%3",
    _status,
    _reason getOrDefault ["code", "?"],
    _reason getOrDefault ["detail", ""]];

cti_lastJudgementText = format ["<t color='#ff8888'>%1</t> — %2 — %3",
    _status,
    _reason getOrDefault ["code", "?"],
    _reason getOrDefault ["detail", ""]];

// A player who has no UI up still gets told: the first thing a mis-slotted
// client does is send a Command and get `wrong_side` back, and a dead click is
// exactly what #18 exists to stop. This is the UI-readiness question and only
// that — whether this machine is a person's is asked once, at the top (#114).
if (isNil "cti_uiSide") then {
    hint parseText cti_lastJudgementText;
} else {
    [] call cti_fnc_mapRender;
};
