# Arma 3 Linux Dedicated Server under WSL2 — SteamCMD, branch parity, and viability

**Research date:** 2026-07-30
**Question:** Can the Arma 3 Linux dedicated server run inside WSL2 as an automated-test tier, with a Windows Steam client connecting to it for play? What are the branch-parity risks?

---

## 0. Method and source-access notes

Several of the requested primary sources actively block automated fetching, so this document records how each fact was actually obtained.

| Source | Direct access | Route used |
|---|---|---|
| `community.bistudio.com/wiki/*` | **403** (Cloudflare) on both WebFetch and curl | MediaWiki API at `https://community.bistudio.com/wikidata/api.php` is **not** behind Cloudflare — page **wikitext** retrieved verbatim via `action=query&prop=revisions&rvslots=main` |
| `developer.valvesoftware.com/wiki/Dedicated_Servers_List` | **403** — Anubis proof-of-work bot wall | Not retrieved. Claims that would have rested on it are instead settled empirically against Steam itself (§2) |
| `steamdb.info/app/233780` | **403** | Not retrieved. SteamDB is only a mirror of Steam's `appinfo`; the **authoritative upstream** was queried directly with SteamCMD (§2, §5) |
| `feedback.bistudio.com/T79316` | **403** | Not retrieved; the same claim is sourced to the BI wiki instead |
| `forums.bohemia.net` | **403** | Not retrieved; SPOTREPs on `dev.arma3.com` are the same publisher and are reachable |
| `dev.arma3.com` (SITREP/SPOTREP) | **200** | Fetched directly — this is Bohemia's official changelog channel |

Because the two "catalogue" sources (SteamDB, Valve's list) were unreachable, the highest-value questions (does anonymous login work? how big is the install? are the branches in parity?) were answered by **querying Steam directly with SteamCMD on this very WSL2 machine**, which is a strictly stronger primary source than either. Raw evidence is in the appendix (§7).

**Secondary sources are explicitly marked `[SECONDARY]`.**

---

## 1. Linux dedicated server status and version parity with the Windows client

### 1.1 The Linux server is current and shipped in lockstep as of the 2.20 cycle

Bohemia's own changelog for the most recent main-branch release lists the Windows and Linux standalone servers as updated **in the same SPOTREP, on the same day, at the same version**:

> `SERVER`
> Updated: Stand-alone Windows Dedicated Server (2.20)
> **Updated: Stand-alone Linux Dedicated Server (2.20)**

— SPOTREP #00119, Hotfix 2.20, Joris-Jan van 't Land, June 25 2025. https://dev.arma3.com/post/spotrep-00119

The identical pairing appears in the preceding feature release, SPOTREP #00118 (Game Update 2.20, June 17 2025): https://dev.arma3.com/post/spotrep-00118

**The historical "Linux server lags at patch boundaries" concern is not observable in the current release cycle.** In both the 2.20 feature update and its hotfix, the Linux server was called out as updated to the same version number as the Windows server, in the release announcement itself, with no "coming later" caveat.

### 1.2 Current version is 2.20, and the game is in a long release trough

The Dev Hub sidebar states `CURRENT VERSION 2.20`, and SPOTREP #00119 (June 25 2025) is the newest SPOTREP in the index (there is no `spotrep-00120`; requesting it returns 404). https://dev.arma3.com/spotrep

An RC for the *next* update is open: `Release Candidate testing: Update 2.22 — Access code: Arma3Update222RC`. https://dev.arma3.com/spotrep

So as of mid-2026 the shipped main branch has been stable at 2.20 for roughly 13 months, with 2.22 in release-candidate testing. **This is favourable for the plan**: parity risk is concentrated at patch boundaries, and no patch boundary has occurred in over a year — but one is visibly imminent.

### 1.3 Steam build metadata corroborates parity of content, with a caveat

Queried live from Steam (`app_info_print`, §7.2):

| App | Branch | Build ID | Branch last updated |
|---|---|---|---|
| 233780 Arma 3 Server | `public` | 18981937 | **2025-06-25 11:37 UTC** |
| 233780 Arma 3 Server | `contact` | 18982089 | 2025-06-25 11:37 UTC |
| 233780 Arma 3 Server | `creatordlc` | 22679086 | 2026-04-07 13:03 UTC |
| 233780 Arma 3 Server | `profiling` | 24335813 | 2026-07-22 14:24 UTC |
| 107410 Arma 3 (client) | `public` | 22679123 | **2026-04-07 13:04 UTC** |
| 107410 Arma 3 (client) | `development` | 23892888 | 2026-06-24 13:17 UTC |
| 107410 Arma 3 (client) | `profiling` | 24335801 | 2026-07-22 14:23 UTC |

The server `public` branch build ID is pinned to the 2.20 hotfix day (2025-06-25), exactly matching SPOTREP #00119. The client `public` branch was rebuilt later, on 2026-04-07 — the same minute as the server's `creatordlc` branch, which is the signature of a Creator-DLC-support mini-update rather than a game version bump (compare SPOTREP #00117, "Game Mini-Update 2.18 (Creator DLC Support)": https://dev.arma3.com/post/spotrep-00117).

Crucially, **the server's core depot content is byte-identical across `public`, `creatordlc` and `profiling`**: depot 233781 (shared data) carries manifest GID `9207897241797719306` on all three, and depot 233783 (Linux binaries) carries manifest GID `8315429281147801686` on all three (§7.2). So the differing build IDs do not imply differing server payloads — the `public` Linux server files are the same core content as the newest server build. Only the `contact` branch differs (distinct GIDs).

> **Caveat on this table:** build IDs are not version strings. The mapping from build ID to a 2.xx version is inferred from date correlation with the SPOTREPs, not read from a Bohemia statement. The authoritative version claim is §1.1 (SPOTREP text), not this table.

### 1.4 A version-mismatched server does gate clients

Bohemia's wiki states the branch-crossing rule directly:

> Since **12th March 2013** the development branch and the stable branch versions are no longer compatible. This means:
> * Only DEV clients can connect to a DEV server
> * Only Stable clients can connect to stable servers

— *Arma 3: Dedicated Server*, "Configuring for stable or Dev branch". https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server

There is additionally an explicit, opt-in server-side minimum-version gate:

> `requiredBuild = xxxxx;` (default `0`) — "Minimum required client version. Clients with version lower than `requiredBuild` will not be able to connect."
> Inline config comment: `// requiredBuild = 12345; // Require clients joining to have at least build 12345 of game, preventing obsolete clients to connect`

— *Arma 3: Server Config File*. https://community.bistudio.com/wiki/Arma_3:_Server_Config_File

So: cross-branch mismatch (dev vs stable) is hard-blocked by the engine; within a branch, `requiredBuild` lets the server refuse older clients but defaults to off. **Practical consequence for this project:** keep both sides on `public`, and do not set `requiredBuild`.

### 1.5 Pinning / downgrading to keep client and server in lockstep

Both the client app and the server app expose a password-protected `legacy` branch, documented on the wiki with the password scheme:

| App | Branch code | Access code | Description (wiki) |
|---|---|---|---|
| 107410 client | `legacy` | `Arma3LegacyXYZ` (XYZ = version, e.g. `150`) | "Old build comparison of the second-last main build" |
| 233780 server | `legacy` | `Arma3LegacyXYZ` | "Old build comparison of the second-last main build" |
| 233780 server | `legacycontact` | `Arma3LegacyXYZ` | as above, with Contact server data |
| 107410 / 233780 | `legacyports` | `Arma3LegacyPorts` | Old build compatibility for Mac client ports |
| 107410 / 233780 | `rc` | shared on Dev Hub during active RC tests | Release-candidate test of imminent updates |
| 107410 client | `development` | n/a | Dev-Branch build |
| 233780 server | `contact`, `creatordlc`, `profiling` | n/a | — |

— *Arma 3: Steam Branches* (wikitext retrieved, page last revised 2025-06-04). https://community.bistudio.com/wiki/Arma_3:_Steam_Branches

The concrete code currently in force is published in the SPOTREP:

> "A **Legacy Build** Steam branch is available for advanced users. It contains the previous significant main branch version (**2.18**). It can be used to compare specific changes between major releases. The access code for this branch is: **`Arma3Legacy218`**"

— SPOTREP #00119. https://dev.arma3.com/post/spotrep-00119

SteamCMD syntax for a password-protected branch, per the wiki:

```
app_update 107410 -beta legacyports -betapassword Arma3LegacyPorts validate
app_update 233780 -beta legacy      -betapassword Arma3Legacy218    validate
```

— *Arma 3: Steam Branches*, "SteamCMD" section. https://community.bistudio.com/wiki/Arma_3:_Steam_Branches

**Two hard limits on this as a pinning strategy:**

1. **Depth of one.** The legacy branch holds only "the previous significant main branch version" / "the second-last main build" — a single generation. It is a *comparison* facility, not an archive. You cannot pin to an arbitrary historical version.
2. **The legacy code is rotated on each release.** The password embeds the version (`Arma3Legacy218`), so when 2.22 ships, `legacy` is expected to move to 2.20 under a new code (`Arma3Legacy220`) and the 2.18 content becomes unreachable. Pinning is therefore a *rolling* one-version window that moves out from under you.
3. Also note, from the wiki: "Steam client does not allow you to maintain multiple parallel branches on your hard drive." (The BI *Game Updater* tool is offered as a workaround for certain branches.) — https://community.bistudio.com/wiki/Arma_3:_Steam_Branches

Neither `legacy` nor `rc` appears in the anonymous `app_info` branch listing for either app, consistent with them being password-gated; the appinfo carries `"privatebranches" "1"` for both apps (§7.2), confirming undisclosed protected branches exist.

---

## 2. Does `steamcmd +login anonymous +app_update 233780` work?

**No. Definitively not.** Anonymous login itself succeeds, but the app has no anonymous licence, so the download is refused.

Tested live on this machine, 2026-07-30 (full transcript §7.1):

```
Connecting anonymously to Steam Public...OK
Waiting for client config...OK
Waiting for user info...OK
ERROR! Failed to install app '233780' (No subscription)
```

`+login anonymous` alone returns `OK` — so the failure is specifically a **licence/subscription** failure on app 233780, not a login failure. Steam's own `app_info` for 233780 is consistent with this: the app is `"type" "Tool"` with `"visibleonlywhensubscribed" "1"` and `"parent" "107410"` (§7.2), i.e. a library item that must be owned rather than an anonymous-serve app.

Bohemia's release notes describe acquiring it the same way — as a library entry, not an anonymous fetch:

> "You can find the servers in the Steam library (switch the filter to \"Tools\") - \"Arma 3 Server\" (based on your OS, it will download the Windows or Linux version). Administrators can also use the command-line **SteamCMD** utility. The app ID is to be **233780**."

— SPOTREP #00119. https://dev.arma3.com/post/spotrep-00119

### 2.1 But the account does *not* need to own Arma 3

This is the important nuance, and it is stated twice on the BI wiki:

> "**Arma 3 Dedicated server package is available for free** (does not require regular Arma 3 to be purchased)."

> "**You do not need to have Arma 3 purchased on the Steam account used here to download the server.** Therefore, you should create a new Steam account with no purchases only for use on this server."

— *Arma 3: Dedicated Server* (page last revised 2026-05-22). https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server

The wiki's *Steam Branches* page phrases the same point in a way that is easy to misread as endorsing anonymous access:

> "The account has to be in possession of Arma 3 in order to download the playable branches. **Server files can be downloaded even without an account.**"

— https://community.bistudio.com/wiki/Arma_3:_Steam_Branches

**That sentence is misleading and is contradicted by the live test above.** Read against the Dedicated Server page, "without an account" means "without an account *that owns Arma 3*" — not "without logging in". Empirically, `login anonymous` is rejected with `No subscription`.

**Net answer:** you need a real, logged-in Steam account; it may be a brand-new free account that owns nothing; it must have "Arma 3 Server" (233780) in its library. Bohemia explicitly recommends a dedicated throwaway account, because "SteamCMD will cache the login credentials and anyone who gains access to your server will be able to log into the account used here", and "you cannot log into a single Steam account from two places at once" (*Arma 3: Dedicated Server*).

> **CI implication, and it is a sharp one.** An unattended pipeline cannot use `login anonymous`. It needs stored credentials plus Steam Guard. The wiki notes the interactive-validation step: "Just after logging into Steam, the console window will hang and ask for a validation key. Steam will have automatically sent you an email with this validation code, which you then need to input at the command prompt." In practice this means seeding the SteamCMD credential cache / `sentry` file once by hand, then reusing it. **Also: "you cannot log into a single Steam account from two places at once" means the CI account must be distinct from the account playing on the Windows client.**

---

## 3. Headless client on Linux — same binary as the dedicated server?

**Yes.** The headless client is the *same executable* as the dedicated server, invoked with `-client`:

> "Headless Client is integrated into game client and dedicated server executable (**Windows and Linux, use `-client` parameter**)"

And the explicit run-options list:

> * Main game executable (Windows only): `arma3.exe` / `arma3.exe -server` / `arma3.exe -client`
> * Windows server executable: `arma3server.exe` / `arma3server.exe -client`
> * **Linux server executable: `arma3server` / `arma3server -client`**

With the invocation:

> Linux: `arma3server -client -connect=xxx.xxx.xxx.xxx -password=yourpass`

— *Arma 3: Headless Client* (page last revised 2024-02-12). https://community.bistudio.com/wiki/Arma_3:_Headless_Client

So on Linux, `arma3server` from app 233780 covers both roles, and **no separate purchase or additional app is needed** — the dedicated server package supplies the headless client binary.

### 3.1 The licence question, and a documented contradiction

The *Dedicated Server* page carries a conflicting claim:

> "Headless Client for Arma 3 requires a **valid active Steam account logged in** to function (see Dwarden's post)"
> "A Headless Client is simply **Arma3.exe** run from the command line with parameters"

— https://community.bistudio.com/wiki/Arma_3:_Headless_Client (cited) / https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server

That passage is written entirely around the **Windows client** binary `arma3.exe` (its examples use `C:\Users\...\Documents\Arma 3 - Other Profiles\HC`), and its "requires a valid active Steam account logged in" claim is sourced to a forum post by Dwarden, not to a first-party spec. It is in direct tension with the *Headless Client* page's statement that the HC is integrated into the **dedicated server executable** on Linux — which is precisely the binary that runs without a Steam client session.

**Assessment:** for the Linux `arma3server -client` path, the dedicated-server licence is what applies; the "needs an active Steam login" caveat pertains to running a headless client out of the *game* (`arma3.exe`) installation. I could not settle this to first-party certainty because the cited forum post (`forums.bohemia.net`) is 403-blocked. **Treat as: very likely fine, verify empirically on first run.** This is the one materially unresolved question in this document.

### 3.2 Headless client operational requirements

- Server must whitelist HC addresses, or arbitrary HC connections are refused: `headlessClients[] = { "127.0.0.1" };`
- For unrestricted bandwidth/latency: `localClient[] = { "127.0.0.1" };`
- "Headless Clients are excluded from signature verification, therefore any mod can be used with the `-mod=` option."
- "`-serverMod=` does not work when used alongside `-client`."
- `allPlayers` includes HCs; `isPlayer` on an HC entity returns `true`; HCs execute `init.sqf` and `initPlayerLocal.sqf` and trigger `initPlayerServer.sqf`.

— https://community.bistudio.com/wiki/Arma_3:_Headless_Client

These last two points matter for an automated-test tier: an HC is *indistinguishable from a player* to much of the standard scripting API, which makes it a usable synthetic-player harness — but also means mission logic keyed on `allPlayers` / `isPlayer` will count it.

---

## 4. Known issues running the Arma 3 Linux server under WSL2

### 4.1 Filesystem case sensitivity — real, documented, and only partly fixable

**The problem is documented first-party by Bohemia**, and it is scoped to **mods**, not base game data:

> "Some mods such as **CUP Terrains** and **@ALiVE** will not function if there are capital letters in any of their file names. If you do not update your mods on a regular basis, you can just use the command
> `find . -depth -exec rename 's/(.*)\/([^\/]*)/$1\/\L$2/' {} \;`
> in the directory where your mods are located. This will recursively search the directory tree and make all the filenames lowercase."

And Bohemia's own recommended structural fix:

> "The solution to this is to use a package called **\"ciopfs\" - Case Insensitive On Purpose Filesystem**. You should first run the \"find . -depth...\" command mentioned above on your mod folder. Then, make an empty directory outside of the mods directory, e.g. `mods_caseinsensitive`. You then mount the directory with:
> `ciopfs mods mods_caseinsensitive`"

— *Arma 3: Dedicated Server*, "Case sensitivity & Mods". https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server

**Confirmed empirically on this box (§7.3):** the WSL2 root filesystem is `ext4` and is case-**sensitive** — creating `Foo.pbo` does not make `foo.pbo` resolve.

**Critical WSL2-specific constraint, from Microsoft (primary):**

> "The case sensitivity attribute can only be set on directories within an NTFS-formatted file system. **Directories in the WSL (Linux) file system are case sensitive by default (and cannot be set to be case insensitive using the `fsutil.exe` tool).**"

> "Default setting: `off` for case sensitivity unavailable (all directories on mounted NTFS drives will be case insensitive)." — and the `case=force` option "is only supported for mounting drives on Linux distributions running as **WSL 1**".

— *Adjust case sensitivity*, Microsoft Learn. https://learn.microsoft.com/en-us/windows/wsl/case-sensitivity

So the two WSL knobs people reach for do **not** help here: `fsutil setCaseSensitiveInfo` only applies to NTFS directories, and `wsl.conf`'s `[automount] options=case=...` only governs mounted Windows drives (and `force` is WSL1-only). **On a WSL2 ext4 install you are on plain case-sensitive Linux semantics, and the fix is Bohemia's: lowercase the mod filenames, or mount mods through `ciopfs`.** `ciopfs` is packaged for Ubuntu (candidate `0.4-0ubuntu4`, §7.3) so the documented fix is one `apt install` away.

Two further notes:
- Installing onto `/mnt/c` to get NTFS case-insensitivity is a bad trade: DrvFs is markedly slower and Arma's data access is I/O heavy. Keep the install on ext4 inside the VM.
- `[SECONDARY]` The community frames the failure mode identically — "Arma3server is unable to read any pbo that has an upper case letter in it"; and LinuxGSM's Arma 3 docs state "Arma 3 server requires that mods have lowercase names", shipping conversion scripts for it. https://docs.linuxgsm.com/game-servers/arma-3

**For a vanilla, unmodded automated-test tier this is a non-issue** — the SteamCMD-delivered files are internally self-consistent. It becomes a real workflow tax the moment the CTI project loads mods, which it will.

### 4.2 Networking — this is the decisive WSL2 issue, and mirrored mode is mandatory

Arma 3 is **entirely UDP**. Per the wiki's port table:

> 2302 UDP (gameport + VON) · 2303 UDP (STEAM query port) · 2304 UDP (STEAM master port) · 2305 UDP (VON reserved) · 2306 UDP (BattlEye traffic port) — "so open ports 2302-2306" and "leave at least **100** ports between the next 2nd server set"
> "Steam ports are now linked to game-port as +1 for query and +2 to-master."

— https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server

This collides head-on with WSL2's **default NAT** mode. Microsoft documents TCP-style localhost forwarding ("you can access it from a Windows app ... using `localhost` (just like you normally would)") and offers `netsh interface portproxy` for LAN access — but:

- `[SECONDARY, well-evidenced]` UDP is **not** forwarded from the Windows host into WSL2 under NAT mode. Tracked in the official WSL repo: [microsoft/WSL#8783 "Can't access UDP services running in WSL on localhost"](https://github.com/microsoft/WSL/issues/8783), [#8868 "UDP port not exposed from WSL2 to host"](https://github.com/microsoft/WSL/issues/8868), [#11194 "UDP port forwarding in WSL2"](https://github.com/microsoft/WSL/issues/11194).
- `netsh interface portproxy` is **TCP-only**, so the workaround Microsoft documents for LAN access cannot carry Arma's traffic either (#11194).

**Mirrored networking mode resolves this.** Microsoft (primary):

> "On machines running **Windows 11 22H2 and higher** you can set `networkingMode=mirrored` under `[wsl2]` in the `.wslconfig` file... Here are the current benefits to enabling this mode: IPv6 support · **Connect to Windows servers from within Linux using the localhost address `127.0.0.1`** · Improved networking compatibility for VPNs · Multicast support · **Connect to WSL directly from your local area network (LAN)**"

> "When the WSL2 is running with the new mirrored mode, the Windows host and WSL2 VM can connect to each other using `localhost` (127.0.0.1) as the destination address, so the trick of using a query peer's IP address is not required."

Inbound may additionally need the Hyper-V firewall opened:

> `Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow`

— *Accessing network applications with WSL*, Microsoft Learn. https://learn.microsoft.com/en-us/windows/wsl/networking

**Verified empirically on this machine (§7.4).** This box already runs `networkingMode=mirrored` (WSL 2.6.3.0, Windows 10.0.26200). A UDP listener bound to `0.0.0.0:2302` inside WSL2 received datagrams sent from the **Windows** side to *both* `127.0.0.1:2302` **and** the mirrored LAN address `192.168.1.36:2302`:

```
RECV from 127.0.0.1:49949    -> b'ARMA3PROBE-from-windows-to-127.0.0.1'
RECV from 192.168.1.36:49950 -> b'ARMA3PROBE-from-windows-to-192.168.1.36'
```

So the exact transport the plan depends on — Windows Steam client → UDP → Arma server in WSL2 — **works on this configuration today**, over both localhost and the LAN IP.

One caveat to carry forward: Bohemia states the server **requires real IPv4**:

> "Arma 3 server does **not** support IPv6 or DSlite IPv4 via IPv6 tunnel. You **must** have a real IPv4 connection."

— https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server

Mirrored mode adds IPv6 support but does not remove IPv4, so this is satisfied; just don't expect to bind the server v6-only.

### 4.3 Memory

Bohemia's stated server minimum is modest: **2 GB RAM minimum / 4 GB recommended**, CPU 2.4 GHz dual-core min / 3.5 GHz quad-core recommended. https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server

This box allocates `memory=12GB` to the WSL2 VM (§7.4), which is comfortably above the recommendation and leaves room for a server plus one or more headless clients. Two WSL2-specific points:

- WSL2's default allocation is a *fraction of host RAM* and the VM reclaims lazily; pin it explicitly in `.wslconfig` (as here) so a CI run cannot be starved. Configuration reference: https://learn.microsoft.com/en-us/windows/wsl/wsl-config
- If server + Windows Steam client + HC all run on one host, they compete for the same physical RAM and cores. For an automated tier that is fine; for a *representative* performance test it is not.

### 4.4 Other Linux-specific gotchas worth pre-loading

All from https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server:

- **`-profiles=` is broken on Linux.** "The `-profiles=` parameter is broken on Linux - you **must** place your profiles in this directory." Create `~/.local/share/Arma 3` and `~/.local/share/Arma 3 - Other Profiles`; the server auto-creates `~/.local/share/Arma 3 - Other Profiles/server/server.Arma3Profile` on first run.
- **Use the 64-bit binary**: `./arma3server_x64 -name=server -config=server.cfg`. "For older 32-bit executable use `./arma3server` instead."
- **`-mod=` paths must be relative** and "within or below the Arma 3 directory. **Symlinks will work.**" (Symlink support is useful for wiring a repo's mission/mod tree into the server install from CI.)
- Do not run as root: "Make sure that you are running it under the steam user and not root or another administrator!"
- The process attaches to the terminal — use `screen`/`tmux`, or a systemd unit (this distro has `systemd=true` in `/etc/wsl.conf`, §7.4).
- SteamCMD's own 32-bit dependency: "If this step fails on a 64-bit OS, you likely need to install 32-bit libraries." Confirmed — bare `steamcmd.sh` failed with `cannot execute: required file not found` until `libc6-i386` and `lib32gcc-s1` were installed (§7.1).
- **Known issue from SPOTREP #00119:** "Steam client modifies the `steam_appid.txt` file incorrectly. In case of issues, verify its content is:" — worth checking if the server misbehaves post-update. https://dev.arma3.com/post/spotrep-00119
- If running server and Steam client on the same host: "make sure you start the server up before you start the steam client. Failing to do this causes steam port issues and your client will not be able to connect to the server." **Directly relevant here** — the plan puts the Windows Steam client on the same physical machine.

---

## 5. Disk size of the dedicated server install (app 233780)

From Steam's authoritative `appinfo` depot manifests (§7.2), `public` branch:

| Depot | Contents | OS | Install size | Download size |
|---|---|---|---|---|
| 233781 | shared server data | any | 5,216,259,829 B (**4.86 GiB**) | 2,058,400,496 B |
| 233783 | server binaries | linux | 168,155,904 B (**160.4 MiB**) | 49,415,920 B |
| 233782 | server binaries | windows | 168,617,012 B | 45,870,400 B |

**Linux dedicated server, `public` branch: ≈ 5.01 GiB on disk (5,384,415,733 B), ≈ 1.96 GiB downloaded.**

Other branches, for planning:

- `contact` branch (Linux): ≈ **5.12 GiB** (depot 233781 grows to 5,328,680,590 B). Note the wiki warns Contact data "is not fully compatible with multiplayer and should only be loaded for advanced use cases".
- `creatordlc` branch (Linux): adds 7 CDLC depots (233788, 233792, 233793, 233794, 233795, 233798, 233799) totalling 16,569,220,315 B (**+15.43 GiB**) → ≈ **20.45 GiB** total.

Bohemia's stated storage requirement is **32 GB HDD minimum / 32 GB SSD recommended** (https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server) — which makes sense once the `creatordlc` branch and mods are in play, and is generous for a vanilla `public` install.

Headroom on this machine: 927 GB free on `/` (§7.3). Not a constraint.

---

## 6. Summary table

| Question | Answer | Confidence |
|---|---|---|
| Linux server current & at parity? | Yes — SPOTREP #00119 ships Windows and Linux servers both at 2.20, same day | **High** (first-party changelog) |
| Current version | 2.20 (June 2025); 2.22 in RC | **High** |
| Version mismatch rejects clients? | Yes across branches (dev↔stable hard-blocked); within branch, opt-in via `requiredBuild` | **High** |
| Pin/downgrade available? | `legacy` branch, password `Arma3Legacy218` — but only one version deep and the code rotates each release | **High** |
| `+login anonymous +app_update 233780`? | **Fails: `No subscription`.** Needs a real logged-in account | **High** (live test) |
| Account must own Arma 3? | **No** — server package is free to any Steam account | **High** (wiki, stated twice) |
| HC = server binary on Linux? | Yes — `arma3server -client` | **High** |
| HC needs own licence? | Dedicated server package covers it; a conflicting wiki note about needing an active Steam login applies to the `arma3.exe` path | **Medium** — cited forum source unreachable |
| Case sensitivity a problem? | Yes for **mods**; not for vanilla. WSL2 ext4 cannot be made case-insensitive; fix is lowercasing or `ciopfs` | **High** (BI wiki + MS docs + live test) |
| Windows client → WSL2 server over UDP? | Works under `networkingMode=mirrored`; **broken under default NAT** (UDP not forwarded) | **High** (live test + MS docs; NAT limitation `[SECONDARY]`) |
| Install size | ≈ **5.01 GiB** Linux `public` (≈1.96 GiB download); ≈20.45 GiB with `creatordlc` | **High** (Steam depot manifests) |

---

## 7. Appendix — raw evidence

All commands run on this machine, 2026-07-30. Kernel `6.6.87.2-microsoft-standard-WSL2`, Ubuntu 24.04, WSL 2.6.3.0, Windows 10.0.26200.8875.

### 7.1 SteamCMD anonymous licence test

Prerequisites (bare `steamcmd.sh` failed with `cannot execute: required file not found`, matching the wiki's 32-bit-libraries note):

```bash
sudo apt-get install -y libc6-i386 lib32gcc-s1
```

Login alone — succeeds:

```
$ ./steamcmd.sh +login anonymous +quit
Connecting anonymously to Steam Public...OK
Waiting for client config...OK
Waiting for user info...OK
```

Download — **fails on licence**:

```
$ ./steamcmd.sh +force_install_dir ./a3server +login anonymous +app_update 233780 +quit
Connecting anonymously to Steam Public...OK
Waiting for client config...OK
Waiting for user info...OK
ERROR! Failed to install app '233780' (No subscription)
```

(exit code 8)

### 7.2 Steam appinfo (authoritative upstream of SteamDB)

```bash
./steamcmd.sh +login anonymous +app_info_update 1 +app_info_print 233780 +quit
./steamcmd.sh +login anonymous +app_info_update 1 +app_info_print 107410 +quit
```

App 233780 identity:

```
"common" { "name" "Arma 3 Server"  "type" "Tool"
           "oslist" "windows,linux" "parent" "107410" }
"extended" { "visibleonlywhensubscribed" "1" }
"config"  { "installdir" "Arma 3 Server" }
```

Depot manifest GIDs (note `public` == `creatordlc` == `profiling` for the core depots):

```
233781 public/creatordlc/profiling gid 9207897241797719306  size 5216259829
       contact                     gid 4190188305589182313  size 5328680590
233783 (linux) public/creatordlc/profiling gid 8315429281147801686 size 168155904
       contact                            gid 3343629397505972102 size 168156122
branches: public 18981937 · contact 18982089 · creatordlc 22679086 · profiling 24335813
"privatebranches" "1"
```

App 107410 branches: `public 22679123` · `development 23892888` · `profiling 24335801`, `"privatebranches" "1"`.

### 7.3 Filesystem

```
$ findmnt -no FSTYPE,SOURCE,TARGET,OPTIONS /
ext4   /dev/sdd /   rw,relatime,discard,errors=remount-ro,data=ordered

$ echo A > Foo.pbo; [ -f foo.pbo ] && echo INSENSITIVE || echo SENSITIVE
CASE-SENSITIVE: Foo.pbo exists but foo.pbo does NOT resolve

$ apt-cache policy ciopfs
ciopfs:  Installed: (none)   Candidate: 0.4-0ubuntu4

$ df -h /home   →  1007G total, 29G used, 927G available
$ free -g       →  11 GiB total in the VM
```

### 7.4 WSL2 configuration and the UDP reachability test

`C:\Users\andre\.wslconfig`:

```ini
[wsl2]
memory=12GB
networkingMode=mirrored
vmIdleTimeout=-1
```

`/etc/wsl.conf`: `[boot] systemd=true`.

Interfaces show mirrored-mode LAN presence: `192.168.1.36/24` on `eth2`, default route `via 192.168.1.1`.

UDP probe — listener inside WSL2, sender on Windows via `powershell.exe` interop:

```bash
# WSL2: bind Arma's game port
python3 -c 'import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);
s.bind(("0.0.0.0",2302));print(s.recvfrom(2048))'
```

```powershell
# Windows side
$u=New-Object System.Net.Sockets.UdpClient
$u.Send($b,$b.Length,"127.0.0.1",2302)      # sent 36 bytes
$u.Send($b,$b.Length,"192.168.1.36",2302)   # sent 39 bytes
```

Received inside WSL2:

```
RECV from 127.0.0.1:49949    -> b'ARMA3PROBE-from-windows-to-127.0.0.1'
RECV from 192.168.1.36:49950 -> b'ARMA3PROBE-from-windows-to-192.168.1.36'
```

### 7.5 Source URLs

- *Arma 3: Dedicated Server* — https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server (wikitext rev. 2026-05-22)
- *Arma 3: Steam Branches* — https://community.bistudio.com/wiki/Arma_3:_Steam_Branches (wikitext rev. 2025-06-04)
- *Arma 3: Headless Client* — https://community.bistudio.com/wiki/Arma_3:_Headless_Client (wikitext rev. 2024-02-12)
- *Arma 3: Server Config File* — https://community.bistudio.com/wiki/Arma_3:_Server_Config_File
- *Arma 3: Play on Linux* — https://community.bistudio.com/wiki/Arma_3:_Play_on_Linux
- SPOTREP #00119 (Hotfix 2.20) — https://dev.arma3.com/post/spotrep-00119
- SPOTREP #00118 (Game Update 2.20) — https://dev.arma3.com/post/spotrep-00118
- SPOTREP #00117 (Mini-Update 2.18, CDLC support) — https://dev.arma3.com/post/spotrep-00117
- SPOTREP index / current version — https://dev.arma3.com/spotrep
- MS Learn, WSL case sensitivity — https://learn.microsoft.com/en-us/windows/wsl/case-sensitivity
- MS Learn, WSL networking — https://learn.microsoft.com/en-us/windows/wsl/networking
- MS Learn, `.wslconfig` reference — https://learn.microsoft.com/en-us/windows/wsl/wsl-config
- `[SECONDARY]` microsoft/WSL UDP issues — https://github.com/microsoft/WSL/issues/8783 · https://github.com/microsoft/WSL/issues/8868 · https://github.com/microsoft/WSL/issues/11194
- `[SECONDARY]` LinuxGSM Arma 3 — https://docs.linuxgsm.com/game-servers/arma-3

---

## VERDICT

**The WSL2-Linux-server plan is viable, and on this machine it is already most of the way there — but two things must be designed for from day one, and neither is the thing the brief worried about.** The feared Linux-server lag is not currently real: Bohemia's own SPOTREP #00119 ships the Windows and Linux standalone servers together at 2.20 on the same day, the core Linux depot content is identical across the `public`, `creatordlc` and `profiling` branches, and the game has sat at 2.20 for ~13 months, so a Windows `public` client and a WSL2 `public` server are in genuine lockstep today. The first thing that must be designed for is that **`steamcmd +login anonymous +app_update 233780` does not work** — it fails with `No subscription` (verified live), so CI needs a real Steam account (a free one that owns nothing is fine, since the server package is free) with a pre-seeded, Steam-Guard-validated credential cache, and that account must be *different* from the one playing on the Windows client because Steam permits only one concurrent session per account. The second is that **`networkingMode=mirrored` is mandatory, not optional**: Arma 3 is pure UDP on 2302-2306, WSL2's default NAT mode does not forward UDP into the VM, and `netsh portproxy` is TCP-only — under mirrored mode I confirmed empirically that Windows reaches a WSL2 UDP listener on port 2302 over both `127.0.0.1` and the LAN IP, so the play path works, but a machine reverted to NAT will fail in a way that looks like a broken server rather than a broken tunnel. On branch-parity risk: the exposure is real but narrow and time-boxed to patch boundaries, and the mitigation is weaker than one would like — the `legacy` branch (currently password `Arma3Legacy218`) is only **one version deep**, its password rotates with each release so the pin slides out from under you when 2.22 ships, and Steam cannot hold two branches on disk simultaneously; so treat legacy as an emergency same-day bridge, not an archive, and instead pin deliberately by disabling Steam auto-update on the Windows client, updating client and server as one atomic step, and keeping `requiredBuild` unset. The residual unknowns are minor: whether `arma3server -client` needs its own Steam session on Linux (the wiki's conflicting note is written around `arma3.exe`, and the cited forum post is unreachable — verify on first run), and mod **case sensitivity**, which is a non-issue for a vanilla test tier but becomes a standing tax once the CTI project loads mods, since WSL2's ext4 cannot be made case-insensitive by any WSL knob and the fix is Bohemia's own: lowercase the filenames or mount mods through `ciopfs`. Budget ~5.01 GiB for the vanilla Linux install (~1.96 GiB download), or ~20.45 GiB on the `creatordlc` branch.
