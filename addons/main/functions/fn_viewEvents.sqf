/*
 * Author: arma-cti
 * What changed for this Commander between two Observations. Runs on the client.
 *
 * Interior to the client's own call graph, so it carries no locality guard: its
 * one caller is cti_fnc_mapObservation, which is the guarded door the server
 * pushes an Observation through (#118, ADR-0041). Pure on purpose — it reads
 * its two arguments and touches nothing else — so a probe can hand it any pair
 * of pictures and read the answer without a notification firing.
 *
 * The wire carries *state* and the Commander needs *events* (#176): the two
 * moments playtest 0001 said arrive silently — ground changing hands, and one
 * of his own Squads ceasing to exist — are both visible as a difference between
 * the picture he held and the one arriving. The daemon already knows both
 * moments, but reading them off consecutive pictures keeps the Observation and
 * the effect vocabulary unchanged: a notification is a presentation of a fact
 * the Observation already carries. An event that needed a fact the wire does
 * not have would be #175's decision, not a field for this function to invent.
 *
 * A Squad's death arrives in either of two shapes, and the event is the
 * transition rather than the shape: the world can report a Squad at 0 for one
 * cycle before `Roster.reconcile` drops it from the roster, or the drop can
 * land first and the Squad simply vanishes. Standing-then-not fires once;
 * zero-then-absent, absent-then-absent and an unchanged picture fire nothing —
 * the picture repeats every 5 s, and a channel that re-announced state would
 * be the map's silence replaced with spam.
 *
 * Arguments:
 * 0: the picture this Commander held <HASHMAP> — a served view, or empty when
 *    there has never been one
 * 1: the picture that just arrived <HASHMAP>
 *
 * Return Value: <ARRAY> of events, each a <HASHMAP> — `event` of "place_taken"
 * (`place`, `owner`, `from`) or "squad_wiped" (`squad`)
 */
params [["_was", createHashMap, [createHashMap]], ["_now", createHashMap, [createHashMap]]];

// No baseline, no events: the first picture after joining is a situation to
// take in, not a run of changes to announce — nothing was lost relative to a
// picture never held. Two pictures belonging to different sides have no
// difference worth reporting either, and an empty `_was` is that case too: its
// side is "" and a served view's never is.
private _side = _now getOrDefault ["side", ""];
if (_side isEqualTo "" || { (_was getOrDefault ["side", ""]) isNotEqualTo _side }) exitWith { [] };

private _events = [];

// Ground changing hands, either way (#176): every Place the wire gives an
// owner, against the owner it had. The daemon's whole owner vocabulary —
// WEST, EAST, NEUTRAL, CONTESTED — counts as hands to change between, so a
// town going CONTESTED announces itself the same way a town falling does. A
// Place the held picture had no owner for is baseline, not news.
private _held = _was getOrDefault ["owners", createHashMap];
{
    private _before = _held getOrDefault [_x, ""];
    if (_before isNotEqualTo "" && { _y isNotEqualTo _before }) then {
        _events pushBack createHashMapFromArray [
            ["event", "place_taken"], ["place", _x], ["owner", _y], ["from", _before]];
    };
} forEach (_now getOrDefault ["owners", createHashMap]);

// One of this Commander's own Squads reaching zero (#176). Own by
// construction: a served view's `squads` never carries anyone else's.
private _standing = createHashMap;
{
    _standing set [_x getOrDefault ["id", ""], _x getOrDefault ["size", 0]];
} forEach (_now getOrDefault ["squads", []]);
{
    private _id = _x getOrDefault ["id", ""];
    if ((_x getOrDefault ["size", 0]) > 0
        && { (_standing getOrDefault [_id, 0]) isEqualTo 0 }) then {
        _events pushBack createHashMapFromArray [["event", "squad_wiped"], ["squad", _id]];
    };
} forEach (_was getOrDefault ["squads", []]);

_events
