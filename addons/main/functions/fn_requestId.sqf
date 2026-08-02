/*
 * Author: arma-cti
 * Mints the id one request to the daemon travels under. Runs wherever it is
 * called; in play that is the server.
 *
 * Every request carries an id, and the daemon answers a line it has already
 * answered from its record rather than folding it twice (#69, ADR-0034). So two
 * different requests sharing an id is not only a false correlation in telemetry
 * — it is a second request being answered with the first one's reply.
 *
 * The four call sites each stamped a millisecond clock: `poll-<ms>`,
 * `cmd-<owner>-<ms>`, `obs-<in-game second>-<ms>`, `view-<side>-<ms>`. Two of
 * those firing in the same millisecond after a scheduler stall collide, and the
 * report loop's in-game second collided with itself several times a second
 * (#103, #91). A counter cannot: it advances once per id, whatever the clock did.
 *
 * The clock stays in the id beside it, and deliberately. The counter lives in
 * the mission namespace and so restarts at nought when the mission does, while
 * the daemon may outlive several missions (#96's restart probe does exactly
 * that) — an id that were the counter alone would repeat across a mission
 * boundary and be answered from the previous mission's record. `diag_tickTime`
 * is measured from the start of the *game*, not the mission, so the pair is
 * unique on both axes.
 *
 * Arguments:
 * 0: what kind of request this is <STRING> — the word the telemetry reads by
 * 1: anything more that names it <STRING> (optional, default "") — a side, a
 *    machine id
 *
 * Return Value: <STRING> the id
 */
params [["_kind", "", [""]], ["_of", "", [""]]];

private _ordinal = (missionNamespace getVariable ["cti_requestOrdinal", 0]) + 1;
missionNamespace setVariable ["cti_requestOrdinal", _ordinal];

private _name = _kind;
if (_of isNotEqualTo "") then { _name = format ["%1-%2", _kind, _of] };
format ["%1-%2-%3", _name, round (diag_tickTime * 1000), _ordinal]
