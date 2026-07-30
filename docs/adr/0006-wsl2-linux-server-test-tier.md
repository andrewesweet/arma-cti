# WSL2-native Linux dedicated server is the primary Arma test tier

Status: accepted, contingent on the phase-0 spike.

All Arma-tier automated testing (dedicated server + headless clients + daemon + shim .so) runs inside WSL2 using the native Linux dedicated server build. The Windows host is used only for human play sessions (client connects to the WSL2 server), perceptual checks, and .dll smoke tests. This removes the self-hosted Windows runner from the MVP entirely; hosted CI runs only the no-Arma fast tier.

Spike must verify before this hardens: Linux server build parity with the Windows client branch, SteamCMD anonymous login for app 233780, Windows-client-to-WSL2-server connectivity, and memory behaviour under WSL2. Fallback if parity bites: orchestrate the Windows server executable from WSL2.
