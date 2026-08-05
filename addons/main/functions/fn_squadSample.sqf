/*
 * Author: arma-cti
 * What the world alone knows about each Squad. Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard:
 * every path into it starts in `missions/cti.Stratis/initServer.sqf`, which the
 * engine runs on the server and nowhere else (#118, ADR-0041).
 *
 * Three facts only: how many of it are still standing, which Place it is in,
 * and where its leader is standing. Its side, what it is and what it was told
 * to do are the daemon's (ADR-0012), and reporting them from here would be
 * inventing a second answer to a question that already has one.
 *
 * `at` is coarse on purpose (ADR-0008): the id of the Objective or Base the
 * Squad is standing on, and empty for the open ground between them. That is the
 * resolution a Commander *plans* at, and it is what the planner reads.
 *
 * `pos` is the same fact before it was rounded to a Place (#175, ADR-0058), and
 * it is here because `at` alone left a marching Squad off the Commander's map
 * for the whole march — indistinguishable from one wiped to the last man. It is
 * reported as the world states any position, three axes; what a Commander is
 * given is the two of them a map can draw, which the daemon decides. Both come
 * off one reading of the leader's position, so the Place and the metres cannot
 * disagree with each other.
 *
 * A Squad the world has lost is simply absent, which is how the daemon learns
 * it is gone.
 *
 * Arguments: none
 *
 * Return Value: <HASHMAP> Squad id -> HASHMAP of `size`, `at` and `pos`
 */
private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _objectives = _map getOrDefault ["objectives", []];
private _bases = _map getOrDefault ["bases", []];
private _seen = createHashMap;

{
    private _squadId = _x;
    private _group = _y;
    if (!isNull _group) then {
        private _living = { alive _x } count units _group;
        if (_living > 0) then {
            // One reading, two answers: the Place it rounds to and the metres
            // it was taken at. Open ground between places is an honest answer
            // for the first, so no nearest-place fallback — a Squad that is
            // marching is marching, and #175 is why the second exists.
            private _pos = getPosATL leader _group;
            private _at = [_pos, _objectives, _bases] call cti_fnc_placeOf;

            // Built through the exported schema (#74): the field names are the
            // daemon's own declaration rather than a copy of it kept in step by
            // hand.
            _seen set [_squadId, ["squad", [["size", _living], ["at", _at], ["pos", _pos]]] call cti_fnc_reportObject];
        };
    };
} forEach (missionNamespace getVariable ["cti_squads", createHashMap]);

_seen
