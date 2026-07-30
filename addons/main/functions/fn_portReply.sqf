/*
 * Author: arma-cti
 * Receives the judgement on a Command this client sent. Runs on the client.
 *
 * The judgement is advisory (ADR-0012): it may say the Command was accepted and
 * what Funds remain, but it never instructs the world to change. Every world
 * effect arrives separately, through the outbox, so a human-issued effect and
 * an AI-issued one travel the same path.
 *
 * Arguments:
 * 0: the judgement <HASHMAP> — `status` of "ok" or "rejected", with `reason`
 *    carrying `code` and `detail` when rejected
 *
 * Return Value: none
 */
params [["_judgement", createHashMap, [createHashMap]]];

cti_lastJudgement = _judgement;

private _status = _judgement getOrDefault ["status", "?"];
if (_status isEqualTo "ok") exitWith {
    private _result = _judgement getOrDefault ["result", createHashMap];
    diag_log format ["CTI|judgement status=ok funds=%1", _result getOrDefault ["funds", "?"]];
};

private _reason = _judgement getOrDefault ["reason", createHashMap];
diag_log format ["CTI|judgement status=%1 code=%2 detail=%3",
    _status,
    _reason getOrDefault ["code", "?"],
    _reason getOrDefault ["detail", ""]];
