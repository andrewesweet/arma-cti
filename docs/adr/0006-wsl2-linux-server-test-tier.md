# WSL2-native Linux dedicated server is the primary Arma test tier

Status: accepted. The phase-0 contingency is discharged — spike verdict GO, 2026-07-30
(docs/spikes/0001-phase0.md).

All Arma-tier automated testing (dedicated server + headless clients + daemon + shim .so) runs inside WSL2 using the native Linux dedicated server build. The Windows host is used only for human play sessions (client connects to the WSL2 server), perceptual checks, and .dll smoke tests. This removes the self-hosted Windows runner from the MVP entirely; hosted CI runs only the no-Arma fast tier.

Measured in phase 0: server boot to mission running in ~20 s, headless client in-mission and executing server-issued code at ~28 s, full cycle ~2 min, server plus headless client peaking at ~2 GiB of the VM's 11 GiB. The fallback (orchestrating the Windows server executable from WSL2) was not needed and is dropped.

Standing requirements from the original research (docs/research/linux-server-steamcmd.md), unchanged: WSL2 must run `networkingMode=mirrored` (Arma is pure UDP; NAT mode drops it), and anonymous SteamCMD for app 233780 fails — a dedicated free Steam account with cached Steam Guard, separate from the playing account, is required.

Constraints the spike attached, binding on everything built on this tier:

- **Ports.** The tier owns 2402–2406 and must never take 2302–2306. Mirrored networking shares one port space between the VM and the Windows host, so a server on 2302 collides with the human's client — observed live when a spike headless client appeared in the human's game.
- **Missions ship as PBOs** (`tools/pack_pbo.py`); an unpacked mission folder cannot be transmitted to a joining client.
- **A native Linux `arma3server` writes no RPT file.** It logs to stdout only. Verdicts and diagnostics come off the captured stdout pipe or through the extension; the RPT-file discovery machinery most published harnesses rely on does not exist here.
- **`-profiles=` is broken on Linux.** Profiles live in `~/.local/share/Arma 3` and `~/.local/share/Arma 3 - Other Profiles`; the harness creates both.

Version parity policy (2026-07-30): client (107410) and server (233780) ship in lockstep, and Steam offers no durable pin — the password-gated `legacy` branch is one generation deep and its access code rotates each release (docs/research/linux-server-steamcmd.md §1.5). When a new stable ships (2.22 is in release-candidate testing), update the server install promptly and re-run the acceptance suite; behavioural changes surface as `engine_drift`, never as fixes to our code. Client/server version skew only blocks the human play path (a mismatched server gates clients); the automated tier is self-consistent on the server install and keeps running. The `legacy` branch is an emergency rollback window of exactly one release, nothing more. Known 2.22 change to watch: the extension surface gains new `callExtension` error codes (400/403/404/412/415, including `EXTENSION_BLOCKED_BY_SCRIPT`, whose blocking mechanism is not yet documented) — on the 2.22 update, extension bring-up is the prime `engine_drift` suspect.

Open risk, deliberately not foreclosed (issue #8): a Windows client joined, spawned, then desynced ("No message received") while the server ran clean at 99 fps. Of the three ranked candidate causes only one — mirrored-mode UDP failing to sustain bidirectional game traffic — would bear on this ADR, and it must be distinguished from the two configuration suspects before any conclusion is drawn. The GO verdict covers everything measured; the human-play path is proven to join-and-spawn, not yet to sustained play.
