// Runs on the server and on every client, including the headless client.

// Defined everywhere so remoteExec can name it. The HC runs it and reports back.
CTI_SPIKE_HC_TASK = {
    private _reply = [clientOwner, diag_fps, count allUnits];
    cti_spike_hc_echo = _reply;
    publicVariableServer "cti_spike_hc_echo";
};

// The HC announces itself so the server-side harness has a positive signal:
// `entities "HeadlessClient_F"` and `allPlayers` both stay empty for an HC that
// holds no slot, so neither is a usable liveness check.
if (!isServer && {!hasInterface}) then {
    cti_spike_hc_online = clientOwner;
    publicVariable "cti_spike_hc_online";
    diag_log format ["SPIKE_HC|online owner=%1", clientOwner];
};
