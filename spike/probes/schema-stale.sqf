// probe: schema-stale
// issues: 80
// window: 150
// expect: schema_stale
//
// #80 in-world probe, RED BY DESIGN. A green run of this probe is the bug.
//
// `expect: schema_stale` inverts the verdict for the regression tier: the run
// passes when the guards below refuse in that class and fails when they do not.
//
// `just regress schema-stale`, or by hand
// `just probe spike/probes/schema-stale.sqf`. The raw verdict is
// FAIL / schema_stale, carrying cti_fnc_command's own refusal:
//
//   FAIL class=schema_stale command_built_without_schema=order schema_keys=1
//
// Why it exists. `cti_fnc_commandSchema` answers a schema callers must be able
// to trust, and says an unusable one is fatal. Two callers dereferenced into it
// without checking — `_schema get "commands"` in cti_fnc_command and
// `_schema get "sides"` in cti_fnc_portGateway — so an unusable schema was
// refused by a raw script error rather than by the documented refusal, and in
// the gateway's case in the middle of deciding whether a client may command a
// side at all (#80). A raw error there does not just log badly: it kills the
// script it happens in, which is the same fault class #102 is about.
//
// How the fault is staged, and what was learned staging it. The first attempt
// replaced `cti_fnc_commandSchema` with a stub that answered an empty HashMap.
// It ran green and proved nothing: **a probe cannot stub a `cti_fnc_` function.**
// The Functions Library compiles every CfgFunctions entry with `compileFinal`
// (topics/Arma_3_Functions_Library.wiki), so the assignment is ignored, the
// engine writes `Attempt to override final function - cti_fnc_commandschema` to
// the server log, and the probe carries on testing the real function while
// looking like it tested a stub. Worth knowing before writing the next probe
// that wants to substitute anything in the addon.
//
// What can be staged is the schema *cache*, which is a documented mission
// namespace variable rather than a monkey-patch: `cti_commandSchemaCache` is
// returned as-is whenever it holds anything, so a cache holding something that
// is not a schema is an unusable schema arriving through the front door. That
// is the case both guards are written against — they ask whether the part they
// need is present rather than whether the whole thing is empty, which is one
// condition covering a missing export and a malformed one alike. The wholly
// missing export cannot be staged in-world at all: it ships inside the addon
// PBO, and a runner staging hook to empty it does not exist (the same gap
// `manifest-missing` records for a *corrupted* manifest).
//
// The second half of the proof is the reason this is in-world rather than a
// reading of the source. An unguarded dereference does not return something
// wrong, it throws, and a scripting error kills the scheduled script it happens
// in — this one. Before the guards, this probe would not have lived to log its
// own completion. Note also that the runner ends its wait at the first FAIL, so
// the verdict is carried by the first refusal and the lines after it are written
// in the same frame and collected on the way out.
[] spawn {
    [20] call cti_probe_fnc_worldReady;

    // The world's own parsed schema, put back below. Nothing else asks for one
    // in the window this is staged for: the assignment sweep read it once at
    // mission start, and the probe world has no client to work the map or the
    // port.
    private _real = missionNamespace getVariable ["cti_commandSchemaCache", createHashMap];
    diag_log format ["CTI|schema_stale_probe_staging real_keys=%1", count _real];
    missionNamespace setVariable ["cti_commandSchemaCache",
        createHashMapFromArray [["_not_a_schema", true]]];

    // Guard one: cti_fnc_command, whose contract is "empty HashMap means do not
    // send". An unusable schema must reach that contract rather than a nil.
    private _built = ["order", [["squad", "s1"], ["order", "attack"], ["place", "agia_marina"]]]
        call cti_fnc_command;
    diag_log format ["CTI|schema_stale_probe_command count=%1 type=%2",
        count _built, _built isEqualType createHashMap];

    // Guard two: cti_fnc_portGateway. Called locally, so `remoteExecutedOwner`
    // is 0 and nothing is sent to a client — the dereference under test happens
    // before any of that, which is the whole finding.
    private _sent = [createHashMapFromArray [
        ["command", "order"], ["side", ""], ["args", createHashMap]
    ]] call cti_fnc_portGateway;
    diag_log format ["CTI|schema_stale_probe_gateway sent=%1", _sent];

    missionNamespace setVariable ["cti_commandSchemaCache", _real];

    // The world has its schema back, unharmed: this is the same parsed
    // catalogue, not a second reading of a file that happened to still be there.
    private _schema = call cti_fnc_commandSchema;
    diag_log format ["CTI|schema_stale_probe_restored commands=%1 sides=%2",
        count (_schema getOrDefault ["commands", createHashMap]),
        _schema getOrDefault ["sides", []]];

    // Both refusals are contracts as well as log lines: empty, not partial, and
    // not sent.
    if (count _built > 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed schema_stale_probe_built_a_command=%1",
            _built];
    };
    if (_sent) then {
        diag_log "CTI|FAIL class=assertion_failed schema_stale_probe_gateway_sent_it";
    };
    if !("commands" in _schema) then {
        diag_log "CTI|FAIL class=assertion_failed schema_stale_probe_left_the_world_without_a_schema";
    };

    diag_log "CTI|schema_stale_probe_done";
};
