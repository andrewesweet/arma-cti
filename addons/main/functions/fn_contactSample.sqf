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
 * Do not trust its arguments to select anything. Three probe runs went on
 * finding new ways for them not to:
 *
 * - `targetSide` ranks rather than filters. The first line of the wiki says as
 *   much — "targets, known to the enquirer (including own troops), where the
 *   accuracy coefficient reflects how close the result matches the query" — and
 *   asking a NATO leader for east returned seven of its own riflemen at accuracy
 *   0.01, with no enemy on the list at all.
 * - `targetMaxAge` does filter, and filters away more than it says: a target's
 *   age is documented as possibly negative, and a negative age does not survive
 *   the bound. Six men standing in plain sight at 100 m came back as one, the
 *   only one of them the engine happened to report at a positive age.
 *
 * So both are asked for the widest answer available and everything is selected
 * again here, on what the command actually returned. Selecting on the returned
 * `targetSide` keeps the data a perception rather than the truth: it is the side
 * the observer believes the target to be, so a man wrongly taken for the enemy
 * is reported as one, which is the honest answer.
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

// How old a memory may be and still count as something a leader currently
// knows. #28 has it that the engine's knowledge model decays to nothing after
// 120 s without sight, and it does not: what decays is `knowsAbout`, while
// `targetsQuery` goes on returning the memory with a growing age for as long as
// it is held — 132 s after the last sighting, in-world, with the men long out of
// sight. Unbounded, a leader standing on a place would report a ten-minute-old
// memory of men who had left, and the daemon's removal rule could never fire,
// because observed absence would never be observed. So the bound the design
// assumed is applied explicitly, at the number it assumed. Persistence past it
// is the daemon's memory, which is where #28 wanted it: a Contact outlives the
// sighting rather than the sighting outliving itself.
private _currentKnowledgeSecs = 120;

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
                    // A negative age is documented and means seen ahead of the
                    // query; the daemon reads age as "seconds ago", so clamp
                    // rather than let a Contact be born in the future.
                    private _age = _targetAge max 0;
                    if (_targetSide isEqualTo _enemy && { _age <= _currentKnowledgeSecs }) then {
                        private _held = _byTarget getOrDefault [_id, []];
                        if (_held isEqualTo [] || { _age < (_held # 1) }) then {
                            _byTarget set [_id, [_targetType, _age, _targetPosition]];
                        };
                    };
                    // Asked for any age on purpose. Handing the command the
                    // bound instead drops every target whose age is negative,
                    // which is most of the ones in plain sight: six men at 100 m
                    // came back as one, the only one of them the engine happened
                    // to report at a positive age. The bound is applied above,
                    // to the age the command returns.
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
        // Built through the exported schema (#74): a sighting says a place, a
        // perceived kind and an age, and which words those are is the daemon's
        // declaration rather than a copy kept in step by hand.
        _seen pushBack (["sighting", [
            ["at", [_targetPosition, _objectives, _bases, true] call cti_fnc_placeOf],
            ["kind", _kind],
            ["age", _age]
        ]] call cti_fnc_reportObject);
    } forEach _byTarget;

    _report set [_sideName, ["contact", [
        ["seen", _seen],
        ["observed", _observed]
    ]] call cti_fnc_reportObject];
} forEach _enemyOf;

_report
