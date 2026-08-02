/*
 * Author: arma-cti
 * Builds one named object of the observe report against the schema the daemon
 * reads it with (#74).
 *
 * The report is assembled by five samplers here and taken apart by
 * `cti_daemon.report` there. That was one design decision living in two
 * languages, held together by convention, with a mismatch showing up only in
 * the Arma tier, one field at a time, at run time. The shapes are now declared
 * once in Python and exported into the same generated JSON the Command
 * catalogue rides in, and every named object in the report is built through
 * here so that the declaration is load-bearing rather than documentation.
 *
 * What this catches is the pair of shipped artefacts disagreeing: a PBO built
 * from samplers that carry a field the exported schema does not, or that have
 * stopped carrying one it does. `tests/unit/test_report_schema.py` catches the
 * same drift in the source without Arma; this catches it in what actually
 * shipped, which is the half a static gate cannot see.
 *
 * A mismatch is logged and the object is built anyway, from what the caller
 * offered. The daemon is the validator (ADR-0012) and will refuse the report if
 * this really is drift; a builder that dropped fields on its own authority
 * would turn a loud refusal into a quiet gap in the world's account of itself.
 *
 * Arguments:
 * 0: shape name <STRING>, a key of `observe_report` in the exported schema
 * 1: fields <ARRAY> of [name, value] pairs
 *
 * Return Value: the object <HASHMAP>
 */
params [["_shape", "", [""]], ["_fields", [], [[]]]];

private _object = createHashMapFromArray _fields;
private _schema = call cti_fnc_commandSchema;
private _shapes = _schema getOrDefault ["observe_report", createHashMap];
private _declared = _shapes getOrDefault [_shape, []];
private _offered = _fields apply { _x # 0 };

if (_declared isEqualTo []) exitWith {
    diag_log format ["CTI|FAIL class=schema_stale report_shape_unknown shape=%1 offered=%2",
        _shape, _offered];
    _object
};

private _missing = _declared select { !(_x in _offered) };
private _unknown = _offered select { !(_x in _declared) };
if (_missing isNotEqualTo [] || { _unknown isNotEqualTo [] }) then {
    diag_log format ["CTI|FAIL class=schema_stale report_shape_mismatch shape=%1 missing=%2 unknown=%3",
        _shape, _missing, _unknown];
};

_object
