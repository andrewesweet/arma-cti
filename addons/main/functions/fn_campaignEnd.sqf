/*
 * Author: arma-cti
 * Ends the Campaign in the world: the outcome recorded, and such end screen as
 * this topology can show. Runs on the server.
 *
 * The daemon decides that a Campaign is over — Domination and Decapitation are
 * rules, and rules live where they are testable (ADR-0012) — and says so once
 * through the outbox, like every other effect. What is left here is the part
 * only the world can do: hold the result where anything on any machine can read
 * it, and put it in front of whoever is looking.
 *
 * Deliberately not `endMission`. The MVP test topology is a dedicated server
 * plus a headless client with no human client guaranteed (docs/mvp-scope.md), so
 * there is usually nobody to show an end screen to and tearing the world down
 * would take the evidence of the Campaign with it. What a headed client gets is
 * the caption below; the real end screen — the summary laid out, the campaign
 * board, what to do next — is #18's map UI and #25's surface, and building it
 * here would be building it blind against a topology that cannot show it.
 *
 * The outcome is broadcast rather than kept server-side because a client is
 * where a screen is, and a JIP client should find a finished Campaign finished
 * rather than have to be told again.
 *
 * Arguments:
 * 0: the winning side <STRING> "WEST" or "EAST"
 * 1: the effect's args <HASHMAP> — `condition`, `at`, `summary`
 *
 * Return Value: <BOOL> whether the Campaign was ended here. False means the
 * effect stays unacknowledged and is delivered again.
 */
params [["_side", "", [""]], ["_args", createHashMap, [createHashMap]]];

if (!isServer) exitWith { false };

private _condition = _args getOrDefault ["condition", ""];
if (_side isEqualTo "" || { _condition isEqualTo "" }) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed campaign_won_unreadable side=%1 args=%2",
        _side, _args];
    false
};

private _summary = _args getOrDefault ["summary", createHashMap];
private _outcome = createHashMapFromArray [
    ["side", _side],
    ["condition", _condition],
    ["at", _args getOrDefault ["at", 0]],
    ["summary", _summary]
];
missionNamespace setVariable ["cti_campaignOutcome", _outcome, true];

// The run's own evidence, and the only end screen a dedicated server has.
diag_log format ["CTI|campaign_won side=%1 condition=%2 at=%3 summary=%4",
    _side, _condition, _args getOrDefault ["at", 0], _summary];

// What a headed client would see, and all of it: the result and the two numbers
// that make it a scoreboard rather than an announcement. Sent to clients only
// (-2) because the server has no screen; remoteExec *from* the server is
// unrestricted (ADR-0012), so nothing here needs whitelisting.
private _owners = _summary getOrDefault ["owners", createHashMap];
private _held = count ((keys _owners) select { (_owners get _x) isEqualTo _side });
private _caption = format ["%1 WINS BY %2 — %3 Objectives held, %4 Squads lost",
    _side, toUpper _condition, _held, _summary getOrDefault ["squads_lost", 0]];
[_caption, "PLAIN DOWN", 1] remoteExec ["titleText", -2];

true
