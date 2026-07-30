/*
 * Author: arma-cti
 * Resolves the extension name the engine actually accepted, or "" if the shim
 * is not loaded. Linux wants the bare name; 64-bit Windows wants <name>_x64.
 *
 * Arguments: none
 * Return Value: extension name <STRING>
 */
private _accepted = "";
{
    if (_accepted isEqualTo "" && {(_x callExtension "ping") isEqualTo "pong"}) then {
        _accepted = _x;
    };
} forEach ["cti_shim", "cti_shim_x64"];
_accepted
