# WSL2-native Linux dedicated server is the primary Arma test tier

Status: accepted, contingent on the phase-0 spike.

All Arma-tier automated testing (dedicated server + headless clients + daemon + shim .so) runs inside WSL2 using the native Linux dedicated server build. The Windows host is used only for human play sessions (client connects to the WSL2 server), perceptual checks, and .dll smoke tests. This removes the self-hosted Windows runner from the MVP entirely; hosted CI runs only the no-Arma fast tier.

Research (2026-07-30, docs/research/linux-server-steamcmd.md) resolved the original open questions: Linux and Windows server builds ship in lockstep (no branch lag; pin by disabling client auto-update and updating both sides atomically), and anonymous SteamCMD for app 233780 fails — a dedicated free Steam account with cached Steam Guard, separate from the playing account, is required. WSL2 must run `networkingMode=mirrored` (Arma is pure UDP 2302–2306; NAT mode drops it). Spike still verifies empirically: server boot, Windows-client-to-WSL2-server connectivity, memory behaviour. Fallback if the tier proves nonviable: orchestrate the Windows server executable from WSL2.
