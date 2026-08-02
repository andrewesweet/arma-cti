/*
 * Author: arma-cti
 * Says out loud that a server-only function was called somewhere else, and hands
 * back a refusal no caller can read as data.
 *
 * Every server-only function in the addon guards itself with `isServer`, and
 * until #112 most of them refused by returning an empty collection: an empty
 * presence map, an empty squad map, an empty casualty list. None of those is
 * distinguishable from a true reading — "nobody stands anywhere", "no Squads
 * exist", "nobody died" — so a report assembled off the server would have been
 * accepted by the daemon as a truthful picture of an empty island, with no
 * failure line anywhere. The others (#113) returned a bare `false` beside
 * siblings that log before returning theirs, so a `false` with no line was
 * unattributable.
 *
 * One voice for both: a typed failure naming the function and the machine, in
 * the class CLAUDE.md's table sends to "fix the code under test", because a
 * server-only function running elsewhere is a call path that should not exist
 * rather than an environment that is missing something.
 *
 * The refusal it returns is a HashMap deliberately shaped like nothing the
 * callers read. Anything that packs it into a report puts a key the daemon's
 * schema does not have onto the wire, and the daemon refuses the whole report
 * loudly — which is the outcome to want. Callers that answer in booleans log
 * through here and return their own `false`.
 *
 * Unreachable in play, and that is not the point: every call path into the
 * guarded functions starts in `missions/cti.Stratis/initServer.sqf`, which the
 * engine runs on the server alone (#111). This is about what the shape costs the
 * first time a call site is not so lucky.
 *
 * Arguments:
 * 0: the function's name <STRING>
 *
 * Return Value: <HASHMAP> the refusal, carrying no reading of anything.
 */
params [["_function", "", [""]]];

private _machine = ["headless_client", "client"] select hasInterface;
diag_log format ["CTI|FAIL class=assertion_failed off_server function=%1 machine=%2",
    _function, _machine];

createHashMapFromArray [["cti_refused", "off_server"], ["function", _function]]
