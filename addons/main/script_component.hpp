/*
 * Locality guards, as macros (#118, ADR-0041).
 *
 * A locality guard says "this function runs on that machine and nowhere else".
 * Hand-rolled, it was `if (!isServer) exitWith { <some sentinel> }` — and the
 * sentinel was chosen locally, twenty-six times, with no two authors agreeing on
 * whether to say anything first. #112 and #113 are what that cost: sentinels
 * that read as data (an empty presence map is "nobody stands anywhere") and a
 * bare `false` beside siblings that log before returning theirs.
 *
 * These macros make the log line structural. A guard that fires writes one typed
 * `CTI|FAIL class=assertion_failed` line naming the machine and the file before
 * it returns the caller's sentinel, so a sentinel can never arrive silently.
 * `assertion_failed` is the right class from CLAUDE.md's table: a function
 * running on the wrong machine is a call path that should not exist, which is
 * code to fix and not an environment to wait on.
 *
 * `tools/check_sqf_bans.py` bans the hand-rolled shape, so the convention
 * enforces itself rather than depending on the next author having read this.
 *
 * ## Where a guard belongs
 *
 * Only where the machine identity is *not* already decided by the call site.
 * ADR-0041 has the derivation; the short form is three kinds of site:
 *
 * - reachable by remoteExec from a client — `cti_fnc_portGateway` alone;
 * - reachable by remoteExec from the server onto a client — `cti_fnc_portReply`
 *   and `cti_fnc_mapObservation`, where `description.ext` offers no protection
 *   at all because server-to-client remoteExec is unrestricted;
 * - the entry point of a supervised loop, because a loop is a thread the
 *   watchdog inventories by name and the one place a future restart would
 *   re-enter.
 *
 * Everywhere else the guard is a comment pretending to be code, and the function
 * header says so in words instead.
 *
 * ## Using them
 *
 * Include the absolute path — the PBO prefix is `cti\addons\main`, so this
 * resolves through the addon's own prefix rather than through the including
 * file's directory (topics/PreProcessor_Commands.wiki:368-376):
 *
 *     #include "\cti\addons\main\script_component.hpp"
 *
 * Then, immediately after `params`:
 *
 *     SERVER_ONLY(scriptNull);
 *     INTERFACE_ONLY(nil);
 *
 * The argument is what the function returns when the guard fires, in the
 * function's own return type. `nil` is the one to use when the function returns
 * nothing. It is never a value a caller can mistake for a reading, which is the
 * whole of #112: pick a sentinel that is wrong on purpose, and the log line
 * above it says which function chose it.
 */

// `__FILE__` is the file being preprocessed, which inside a PBO is the addon
// path (topics/PreProcessor_Commands.wiki:421-425). Named rather than the
// function, because a function name is a second thing to keep in step with the
// file and the two drift.

#define SERVER_ONLY(SENTINEL) \
    if (!isServer) exitWith { \
        diag_log format ["CTI|FAIL class=assertion_failed locality wanted=server machine=%1 file=%2", \
            (["headless_client", "client"] select hasInterface), __FILE__]; \
        SENTINEL \
    }

#define INTERFACE_ONLY(SENTINEL) \
    if (!hasInterface) exitWith { \
        diag_log format ["CTI|FAIL class=assertion_failed locality wanted=interface machine=%1 file=%2", \
            (["dedicated_server", "headless_client"] select (!isServer)), __FILE__]; \
        SENTINEL \
    }
