// #22 in-world probe, RED BY DESIGN. A green run of this probe is the bug.
//
// Run with `just probe spike/probes/manifest-missing.sqf`. The expected verdict
// is FAIL / assertion_failed, carrying cti_fnc_manifestLoad's own refusal:
//
//   FAIL class=assertion_failed no_manifest_for_world=Altis
//       path=cti\addons\main\manifests\altis.json
//
// Why it exists. The addon now reads the authored JSON out of its own PBO
// (ADR-0017), so "the manifest is missing" is an engine-level failure Python
// cannot see and the green probe cannot provoke: the daemon loads the same
// directory, so deleting the file to stage the failure takes the daemon down
// first and the run stops at infra_unavailable without ever reaching the guard.
// That was tried, and that is what it did. Asking the guard for a world with no
// manifest reaches it directly.
//
// What is being shown is two things at once: that the guard refuses rather than
// returning a half-built world, and that the harness classifies its refusal
// instead of reporting HOLD-COMPLETE over the top of it.
[] spawn {
    private _map = ["Altis"] call cti_fnc_manifestLoad;
    // The guard has already logged the FAIL line above; this is the other half
    // of the contract, which callers depend on: empty, not partial.
    diag_log format ["CTI|manifest_missing_probe_returned count=%1 type=%2",
        count _map, _map isEqualType createHashMap];
    if (count _map > 0) then {
        diag_log "CTI|FAIL class=assertion_failed manifest_missing_probe_returned_a_map";
    };
    // The world the mission actually runs on is untouched by the question.
    diag_log format ["CTI|manifest_missing_probe_world_still_built objectives=%1",
        count ((missionNamespace getVariable ["cti_map", createHashMap]) getOrDefault ["objectives", []])];
    diag_log "CTI|manifest_missing_probe_done";
};
