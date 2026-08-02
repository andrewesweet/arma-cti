// probe: locality-guard
// issues: 118
// window: 150
// expect: assertion_failed
//
// #118 in-world probe, RED BY DESIGN. A green run of this probe is the bug.
//
// `expect: assertion_failed` inverts the verdict for the regression tier: the run
// passes when the guard fires and fails when it does not, the same way
// `manifest-missing` and `schema-stale` stage their faults — by asking a guard the
// question directly.
//
// `just regress locality-guard`, or by hand
// `just probe spike/probes/locality-guard.sqf`. The raw verdict is
// FAIL / assertion_failed, carrying the INTERFACE_ONLY macro's own line:
//
//   FAIL class=assertion_failed locality wanted=interface machine=dedicated_server
//       file=cti\addons\main\functions\fn_portReply.sqf
//
// ## What it proves, and what it cannot
//
// Two things at once, and both were unverified assumptions in #111's review.
//
// 1. **That `#include` resolves at runtime from a CfgFunctions-compiled `.sqf`
//    inside a PBO.** Nothing in this repo included anything from SQF before
//    ADR-0041, and HEMTT resolving the path at build time is not the same
//    question as the engine's runtime preprocessor resolving it — HEMTT has its
//    own virtual filesystem. If the include silently did not resolve,
//    `INTERFACE_ONLY(nil)` would reach the compiler as an unknown token and
//    cti_fnc_portReply would not compile at all, so the guard could not fire and
//    this probe goes red.
// 2. **That the macro's firing branch does what it says**: one typed FAIL line
//    naming the wanted machine and the file, and then the caller's sentinel.
//
// The lever is that `hasInterface` is false on a dedicated server
// (`commands/hasInterface.wiki`), so INTERFACE_ONLY is the one half of the
// convention a server-side probe can actually trip. Calling a client-side
// function on the server is exactly the call path the guard exists to refuse.
//
// What this cannot show is SERVER_ONLY firing, because that needs a machine that
// runs an addon function and is not the server, and nothing in the tier does
// (#116 is the same gap seen from the probe side). SERVER_ONLY is verified by
// inspection and by sharing this one's expansion, and that is the honest limit:
// the two macros differ by one command and one word.
//
// cti_fnc_portReply is the subject rather than cti_fnc_mapObservation because it
// is the door with no config protection at all *and* the one that was missing its
// guard entirely until #114. Its body writes `cti_lastJudgement`, so whether the
// guard refused is a fact this probe can read rather than infer.
[] spawn {
    // The world built, so the FAIL below is the only one in the log and the
    // runner's verdict is unambiguously this probe's.
    [20] call cti_probe_fnc_worldReady;

    // Distinguishable from anything the port could have written, so "the guard
    // refused" and "nobody has sent a judgement yet" are not the same reading.
    cti_lastJudgement = "untouched-by-the-probe";

    private _judgement = createHashMapFromArray [
        ["status", "rejected"],
        ["reason", createHashMapFromArray [
            ["code", "locality_probe"],
            ["detail", "a judgement addressed to a machine with no screen"]
        ]]
    ];

    diag_log "CTI|locality_guard_probe_calling function=cti_fnc_portReply machine=server";

    // The guard fires here and its FAIL line is the verdict. Everything after it
    // is corroboration the runner may or may not still be reading, exactly as in
    // `manifest-missing`.
    [_judgement] call cti_fnc_portReply;

    // The other half of the contract: the sentinel is a refusal and not a write.
    // A guard that logged and then carried on would pass the assertion above and
    // be worse than no guard at all, because the log would say it had stopped.
    private _held = cti_lastJudgement isEqualTo "untouched-by-the-probe";
    diag_log format ["CTI|locality_guard_probe_returned held=%1", _held];
    if (!_held) then {
        diag_log "CTI|FAIL class=assertion_failed locality_guard_probe_ran_the_body";
    };

    diag_log "CTI|locality_guard_probe_done";
};
