/*
 * Author: arma-cti
 * What each side's squad leaders have seen of the other. Runs on the server.
 *
 * A fact only the world can report, and the last of them: the engine's own
 * knowledge model, read through `targetsQuery`, which shares instantly within a
 * group and decays to zero after 120 s without sight. We invent no visibility
 * rule. What the sightings *mean* — the echelon band, the posture, the assets,
 * and how long a Contact outlives the engine forgetting it — is decided in the
 * daemon where the rules are testable (ADR-0012).
 *
 * `targetsQuery` returns perceived data, and that is the feature. The type it
 * reports is what the observer made out, so `BIS_fnc_objectType` classifies a
 * perception rather than the truth and an unrecognised contact is honestly
 * unidentified. Correcting it against ground truth would be the
 * perfect-information lever ADR-0012 rejects.
 *
 * Its side argument RANKS, it does not filter. The wiki says so in the first
 * line — "targets, known to the enquirer (including own troops), where the
 * accuracy coefficient reflects how close the result matches the query" — and
 * #28's design read past it. Asking for east and reading the list back gave
 * seven of our own riflemen at accuracy 0.01, in-world, with no enemy on it at
 * all (`spike/probes/contacts.sqf`). So the query is still asked for the enemy,
 * because the ranking is worth having, and the returned `targetSide` is what
 * actually selects. That is still a perception rather than the truth: it is the
 * side the observer believes the target to be, so a man wrongly taken for the
 * enemy is reported as one, which is the honest answer.
 *
 * Two lists per side, and the second is not the first:
 *
 * - `seen` is every enemy that side currently knows about, deduplicated across
 *   its leaders. Without the dedupe, four Squads watching the same eight men
 *   would report thirty-two and the band would read `company`.
 * - `observed` is the places its leaders are actually standing in. It is the
 *   whole of the daemon's removal rule — absence of contact is not evidence,
 *   observed absence is — so it is strict where `seen` is forgiving: a sighting
 *   in open ground is filed under the nearest place, but a leader in open
 *   ground has observed nothing and clears nothing.
 *
 * No Squad, group or unit identity crosses to the daemon: a sighting carries a
 * place, a perceived kind and an age, and nothing that could be traced back to
 * the enemy Squad it was made of.
 *
 * Arguments: none
 *
 * Return Value: <HASHMAP> side name -> HASHMAP of `seen` and `observed`
 */
if (!isServer) exitWith { createHashMap };

private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _objectives = _map getOrDefault ["objectives", []];
private _bases = _map getOrDefault ["bases", []];
private _squads = missionNamespace getVariable ["cti_squads", createHashMap];

// The enemy each side queries for. `targetsQuery` filters by Side, so this is
// what turns "what has WEST seen" into a query the engine can answer.
private _enemyOf = createHashMapFromArray [["WEST", east], ["EAST", west]];

private _report = createHashMap;

{
    private _sideName = _x;
    private _enemy = _y;

    // Deduplicated across the side's leaders, keeping the freshest age: shared
    // knowledge means several leaders report the same man, and an Object cannot
    // be a HashMap key, so identity is its netId — which stays on the server.
    private _byTarget = createHashMap;
    private _observed = [];

    {
        private _group = _x;
        if (!isNull _group && { str side _group isEqualTo _sideName }) then {
            private _leader = leader _group;
            if (alive _leader) then {
                // Where this leader can clear a Contact: strictly the place it
                // is standing in, or nowhere at all.
                private _standing = [getPosATL _leader, _objectives, _bases, false] call cti_fnc_placeOf;
                if (_standing isNotEqualTo "" && { !(_standing in _observed) }) then {
                    _observed pushBack _standing;
                };

                {
                    _x params ["", "_target", "_targetSide", "_targetType", "_targetPosition", "_targetAge"];
                    private _id = netId _target;
                    if (_targetSide isEqualTo _enemy) then {
                        private _held = _byTarget getOrDefault [_id, []];
                        // A negative age is documented and means seen ahead of
                        // the query; the daemon reads age as "seconds ago", so
                        // clamp rather than let a Contact be born in the future.
                        private _age = _targetAge max 0;
                        if (_held isEqualTo [] || { _age < (_held # 1) }) then {
                            _byTarget set [_id, [_targetType, _age, _targetPosition]];
                        };
                    };
                } forEach (_leader targetsQuery [objNull, _enemy, "", [], 0]);
            };
        };
    } forEach values _squads;

    private _seen = [];
    {
        _y params ["_targetType", "_age", "_targetPosition"];
        // A type nobody made out classifies as nothing rather than as an error.
        private _kind = "UnknownObject";
        if (_targetType isNotEqualTo "") then {
            _kind = (_targetType call BIS_fnc_objectType) # 1;
        };
        _seen pushBack (createHashMapFromArray [
            ["at", [_targetPosition, _objectives, _bases, true] call cti_fnc_placeOf],
            ["kind", _kind],
            ["age", _age]
        ]);
    } forEach _byTarget;

    _report set [_sideName, createHashMapFromArray [
        ["seen", _seen],
        ["observed", _observed]
    ]];
} forEach _enemyOf;

_report
