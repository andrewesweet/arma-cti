/*
 * Author: arma-cti
 * Offers this player the curated loadout menu, on his own body. Runs on a client.
 *
 * Pushed by the server (cti_fnc_loadoutWatch) rather than installed by the
 * client on its own, for cti_fnc_mapObservation's reason: the server is what
 * knows which body a player currently has, and an action list belongs to an
 * object (`addAction` is `eff= local`), so a respawned man has no menu until
 * somebody puts one on him. The watch does that on every new body.
 *
 * **No client-to-server call is added, and that is the design rather than an
 * accident.** The CfgRemoteExec whitelist is one function long — the Command
 * Port's gateway — and ADR-0025's consequence keeps it that way, so a pick here
 * is published as a wish on the player's own object (`setVariable` with the
 * public flag: globally broadcast and JIP-persistent, per the vendored wiki) and
 * the server's watch reads it, judges it and dresses him. A wish is not a
 * Command: it is free, it moves no Funds, and the rules judge nothing (ADR-0056).
 *
 * The action's condition asks cti_fnc_loadoutAtBase, which is the same rule the
 * server grants through — so the menu the player can see and the menu the
 * server will honour are one reading evaluated on two machines. The client's is
 * display; the server's is the rule.
 *
 * Arguments:
 * 0: the player's current body <OBJECT>, as the server sees it
 *
 * Return Value: none
 */
#include "\cti\addons\main\script_component.hpp"

params [["_unit", objNull, [objNull]]];

// One of the doors the server pushes through, and server-to-client remoteExec
// is unrestricted, so `description.ext` offers no protection here and this guard
// is the only thing there is (#118, ADR-0041).
INTERFACE_ONLY(nil);

if (isNull _unit) exitWith {
    diag_log "CTI|FAIL class=assertion_failed loadout_menu_without_unit";
};

private _kits = call cti_fnc_loadoutCatalogue;
if (_kits isEqualTo []) exitWith {
    // cti_fnc_loadoutCatalogue has already logged which failure this is.
    diag_log "CTI|FAIL class=assertion_failed loadout_menu_without_catalogue";
};

// A body carries its own actions and nothing else's. Removing what is already
// there first, because the watch re-offers on a new body and a reconnection can
// hand the same body twice — two menus on one man is the same list drawn twice.
{ _unit removeAction _x } forEach (_unit getVariable ["cti_loadoutActions", []]);

private _installed = [];
{
    private _kit = _x;
    private _id = _kit getOrDefault ["id", ""];
    private _name = _kit getOrDefault ["display_name", _id];
    _installed pushBack (_unit addAction [
        format ["<t color='#87d1ff'>Take %1 kit</t>", _name],
        // The pick, published for the server to judge. `_target` is the object
        // the action sits on, so a player can only ever wish for himself.
        {
            params ["_target", "_caller", "_actionId", "_arguments"];
            _arguments params ["_kitId", "_kitName"];
            _target setVariable ["cti_loadoutWish", _kitId, true];
            hint format ["%1 requested. Your kit arrives in a moment.", _kitName];
        },
        [_id, _name],
        1.5,
        false,
        true,
        "",
        // Evaluated by the engine while the action list is drawn, so it is kept
        // to the one question: the same rule the server grants through.
        "[_target] call cti_fnc_loadoutAtBase",
        // Reach: the menu is on the player's own body, so he is always at zero
        // distance from it. Left at the engine's default rather than widened.
        4
    ]);
} forEach _kits;

_unit setVariable ["cti_loadoutActions", _installed];
diag_log format ["CTI|loadout_menu_offered kits=%1", count _installed];
