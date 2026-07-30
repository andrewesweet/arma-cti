# Getting a client into a running Arma 3 mission without a human — role selection, headless clients, and slot assignment

**Research date:** 2026-07-30
**Question:** A real Windows client launched with `-connect/-port/-password` reaches the multiplayer **role selection** screen and stops there until a human clicks a slot and presses OK. A Linux headless client (`arma3server -client -connect=…`) connects, is logged as `Player headlessclient connected (id=HC<pid>)`, and then does nothing: no `init.sqf`, no `onPlayerConnected`, empty `allPlayers`. How does an unattended client get past role selection into a running mission? What do real headless-client deployments do? Is there a server-side SQF route to force a slot? What is `Server error: Player without identity`? Does an HC need a Steam session?

**Context:** Arma 3 **2.20.152984** Linux dedicated server in WSL2. Companion document: `docs/research/linux-server-steamcmd.md` (this document settles its §3.1 open item).

---

## 0. Method and source-access notes

| Source | Direct access | Route used |
|---|---|---|
| `community.bistudio.com/wiki/*` | **403** (Cloudflare) | MediaWiki API at `https://community.bistudio.com/wikidata/api.php` — **but the plain `curl` recipe from the previous research doc now also 403s.** It succeeds when sent with a full browser header set (`User-Agent`, `Accept`, `Accept-Language`, `Sec-Fetch-*`). Verbatim wikitext retrieved this way; see §8.1 |
| `feedback.bistudio.com/T72887`, `/T79316` | **403** (Cloudflare) | Not retrieved. `T72887` ("Server error: Player without identity") is titled in search results but its body was unreachable — §6 is therefore built from the wiki's own client-state table rather than from the ticket |
| `forums.bohemia.net` | **403** (Cloudflare) direct, **and via `r.jina.ai`** (the proxy returns Cloudflare's "Performing security verification" page) | Not retrieved. Where a forum post is the wiki's own citation (Dwarden on HC/Steam), that is recorded as an unverifiable citation, not as evidence |
| `dev.arma3.com` | **200** | Fetched directly — confirms shipped version is still **2.20**, with 2.22 in RC |
| `steamcommunity.com` discussions | **200** via WebFetch | Used only for `[SECONDARY]` corroboration |
| `killzonekid.com` | **200** | `[SECONDARY]` but high-credibility; article text retrieved verbatim |
| GitHub (`gh api`, `raw.githubusercontent.com`) | **200** | Used to read the **actual mission files** of shipping headless-client frameworks — better evidence than any guide |

**Secondary sources are explicitly marked `[SECONDARY]`.** Everything not so marked is Bohemia's own wiki, Bohemia's dev hub, or a file from this repository.

---

## 1. The frame: "the lobby" is two screens and a ten-step state ladder

Before answering anything, the vocabulary needs pinning down, because "stuck in the lobby" covers at least four distinct engine states.

Bohemia documents a numbered client-connection state machine, readable from **both server and clients** via `getClientState` / `getClientStateNumber`:

| # | `getClientState` | Description (verbatim) |
|---|---|---|
| 0 | `"NONE"` | No client (or singleplayer) |
| 1 | `"CREATED"` | Client is created |
| 2 | `"CONNECTED"` | Client is connected to server, message formats are registered |
| 3 | `"LOGGED IN"` | **Identity is created** |
| 4 | `"MISSION SELECTED"` | Mission is selected |
| 5 | `"MISSION ASKED"` | Server was asked to send / not send mission |
| 6 | `"ROLE ASSIGNED"` | **Role was assigned (and confirmed)** |
| 7 | `"MISSION RECEIVED"` | Mission received |
| 8 | `"GAME LOADED"` | Island loaded, vehicles received |
| 9 | `"BRIEFING SHOWN"` | Briefing was displayed |
| 10 | `"BRIEFING READ"` | Ready to play mission |
| 11 | `"GAME FINISHED"` | Game was finished |
| 12 | `"DEBRIEFING READ"` | Debriefing read, ready to continue with next mission |

— *Multiplayer Scripting*, "Client state". https://community.bistudio.com/wiki/Multiplayer_Scripting

**This table is the single most useful artefact in this document.** It says:

- "Role selection" is the transition **5 → 6**. A client sitting in role selection is at state 5.
- "Identity" is a distinct, *earlier* concept — state 3. §6 turns on this.
- The **briefing screen with the CONTINUE button is a separate, later gate** (9 → 10). Two clicks stand between a connected client and a running mission, not one.
- Mission scripts do not exist on the client until well after state 6. `init.sqf` runs after the mission is received and loaded. **Anything you want to happen at or before state 6 cannot be done in mission SQF on that client**, because there is no mission on that client yet.

Corresponding UI identifiers, for anyone contemplating UI automation:

```
#define IDD_MULTIPLAYER            8    // server browser
#define IDD_SERVER_GET_READY      52
#define IDD_CLIENT_GET_READY      53    // the briefing / CONTINUE display
#define IDD_MULTIPLAYER_ROLE      61    // role selection
#define IDD_MP_SETUP              70
```

— *Arma 3: IDD List*. https://community.bistudio.com/wiki/Arma_3:_IDD_List

---

## 2. Question 1 — how an unattended client gets past role selection

### 2.1 `skipLobby = 1` is the documented, first-party answer

> **skipLobby** {{arma3 1.60}}
> When enabled, joining player will join the mission **bypassing role selection screen**.
> The `joinUnassigned` param will be set to 1 automatically, so that player receives **first available role from mission template**. When leaving such mission, player will go straight back to server browser.
> ```cpp
> skipLobby = 1; // 0: disabled - 1: enabled. Default: 0
> ```

— *Description.ext*, "Mission Settings". https://community.bistudio.com/wiki/Description.ext

There is a companion entry confirming the mechanism is real and load-bearing enough to need an opt-out:

> **hostDoesNotSkipLobby** {{arma3 2.06}} — Stops hosting player from skipping the lobby if `skipLobby = 1;` is used.

This is a **mission** setting (`description.ext`), not a server or client setting. It is not currently set in this repo's `missions/spike.Stratis/description.ext`.

### 2.2 `joinUnassigned` means the opposite of what it looks like — and this repo has it backwards

> **joinUnassigned** {{arma3 0.50}}
> By default a new player is **not** auto assigned a free playable slot in the mission lobby in Multiplayer.
> **Disable this setting** to make him auto assigned to the side with least players.
> ```cpp
> joinUnassigned = 0; // 0: disabled - 1: enabled. Default: 1
> ```

— *Description.ext*. https://community.bistudio.com/wiki/Description.ext

The name reads as "may join unassigned", and that is the correct reading: `joinUnassigned = 1` **permits** a client to sit in the lobby with no slot; `joinUnassigned = 0` **forbids** it, so the engine assigns one.

This is confirmed independently and first-party by the 2.22 server-scripting docs, which describe the auto-select path as firing under exactly two conditions:

> **OnAutoSelectRole** — When player joins server and tries to auto select a role (**`joinUnassigned=0` or `skipLobby=1`**).

— *Arma 3: Server Side Scripting*. https://community.bistudio.com/wiki/Arma_3:_Server_Side_Scripting

And `[SECONDARY]`, by the shipping missions that rely on it:

- Apex Framework: `joinUnassigned = 0;  /*/ 0 = players forced into role on join/*/`
- A3Wasteland: `joinUnassigned = 0;`
- Mike Force: `joinUnassigned = 0;`

**This repo's `description.ext` currently sets `joinUnassigned = 1;`, which is the value that keeps a joining client unassigned in the lobby.** The comment in the brief describing it as already-correct configuration is mistaken. (It is also the engine default, so setting it to `1` is a no-op either way.)

Caveat on scope: the wiki says auto-assignment picks "the side with least players", and `skipLobby` says "first available role from mission template". Neither states whether the client still has to confirm with OK. `skipLobby` explicitly says the *screen is bypassed*; `joinUnassigned = 0` only says a slot is *assigned*. **Prefer `skipLobby = 1` if the goal is genuinely zero clicks.**

### 2.3 The briefing/CONTINUE screen is a second gate, and `briefing = 0` may not close it

Bohemia's own text is hedged:

> **briefing** — Skip briefing screen **for SP missions**. If no briefing.html is present, it is skipped anyway.
> `briefing = 0; // 0: disabled - 1: enabled. Default: 1`
> **Briefing will still be displayed until all clients are connected and done loading.**

— *Description.ext*. https://community.bistudio.com/wiki/Description.ext

`[SECONDARY]` Killzone_Kid tested this and reported it flatly broken in MP, along with the reason the first joiner matters so much:

> "there is briefing parameter in description.ext you can set to 0 as well as debriefing parameter. Well, apparently **they are both completely useless in MP** […] until the briefing page is passed, **the mission does not start**. On top of that **only first player joining the server can trigger server start up sequence**. If this player does not complete briefing, the mission never starts. You can sit on the briefing screen for the whole minute without pressing CONTINUE and the mission will not start."

His workaround is to press the button on the client's behalf, from a `preInit` function:

```sqf
if (hasInterface) then {
    if (!isNumber (missionConfigFile >> "briefing")) exitWith {};
    if (getNumber (missionConfigFile >> "briefing") == 1) exitWith {};
    0 = [] spawn {
        waitUntil {
            if (getClientState == "BRIEFING READ") exitWith {true};
            if (!isNull findDisplay 53) exitWith {
                ctrlActivate (findDisplay 53 displayCtrl 1);
                findDisplay 53 closeDisplay 1;
                true
            };
            false
        };
    };
};
```

— `[SECONDARY]` Killzone_Kid, "How To Skip Briefing Screen In MP", 2013-12-19. https://killzonekid.com/arma-scripting-tutorials-how-to-skip-briefing-screen-in-mp/

Two things carry forward. First, `-autoInit` on the server (already in use here) removes the "first joiner must start the mission" problem, which is most of what that article is complaining about. Second, **`ctrlActivate` on a known display/control ID is the community-standard way to click a button unattended** — and it works from `preInit`, i.e. from state 6 onwards. It cannot reach display **61** (role selection), because `preInit` has not run yet at state 5.

`[SECONDARY]` A3Wasteland's `description.ext` annotates `briefing = 0; // if 0, skip Continue button`, so the parameter evidently does something in at least some configurations. Treat "does `briefing = 0` work in MP in 2.20" as **unresolved**; the repo already sets it, and the cheap check is whether display 53 ever appears.

### 2.4 What `respawnOnStart`, `class Params` and `class Header` do *not* do

- **`respawnOnStart`** — "Respawn player when he joins the game. Available only for INSTANT and BASE respawn types." Values `-1` / `0` / `1`. This acts on a player *already in the mission*; it has no bearing on role selection. Setting it will not help. (*Description.ext*)
- **`class Params`** — "These are Multiplayer parameters, available in the lobby **by the server administrator**." They are read at mission start, not a slot mechanism. Worse for this project: **`-autoInit` breaks them.** "This will break the Arma 3: Mission Parameters function, so do not use it when you work with mission parameters, only default values are returned!" (*Arma 3: Startup Parameters*, `autoInit`). That specifically kills the *second* of the two headless-client bootstrap recipes on the HC wiki page — the `class params` + `isGlobal = 1` function route is unusable alongside `-autoInit`. Use the `init.sqf` + `if (!hasInterface && !isServer)` route instead.
- **`class Header` / `maxPlayers`** — cosmetic plus a cap. Server `maxPlayers`: "The final number will be lesser between number given here and number of mission slots." (*Arma 3: Server Config File*). `[SECONDARY]` A3Wasteland documents that HC slots count towards it: `maxPlayers=146; // 144 players, 2 headless clients` — so this repo's `maxPlayers = 2` for 1 rifleman + 1 HC is right.
- **A mission with zero playable slots** is a dead end, not a shortcut: the engine raises "No player select" unless `scriptedPlayer = 1` is set (a Take On Helicopters-era entry), and a client with nothing to slot into cannot enter.

### 2.5 There is no client-side startup parameter for this

The full "Client Network Options" section of *Arma 3: Startup Parameters* contains exactly three entries: `-connect`, `-port`, `-password`. There is no `-autoJoin`, `-slot`, `-role`, or equivalent anywhere on the page (all 83 section headings were enumerated; §8.2). `-client` is documented only as "Launch as client (console). Useful for headless clients."

**Conclusion: role selection cannot be skipped from the client command line. It is skipped by the mission, via `description.ext`.**

One untested lead worth recording, because it is the only client-side hook that runs early enough:

> **`-init`** — Run scripting command once **in the main menu**. For example to start a certain SP mission of choice automatically.
> `arma3_x64.exe -init=playMission["","Test.VR"]`

— *Arma 3: Startup Parameters*. https://community.bistudio.com/wiki/Arma_3:_Startup_Parameters

`-init` executes SQF in the main-menu context, which is where display 61 lives. Combining `-connect … -init="…waitUntil {!isNull findDisplay 61}; …lbSetCurSel…; ctrlActivate…"` is the structurally correct shape for a client-side auto-slotter. **I found no primary documentation and no working example of this combination**, and do not know whether `-init` even fires when `-connect` is also present. Marked **speculative**; it is cheap to test and would be a genuinely reusable capability if it works.

### 2.6 Related server.cfg knobs, and what they actually do

| Entry | Verbatim meaning | Relevance |
|---|---|---|
| `roleTimeOut[] = { 90, 120 };` | "Kicks users from server if they spend too much time in role selection" (default `{90,120}`) | A client parked in role selection is **eventually kicked**, not left forever. Useful as a harness assertion |
| `briefingTimeOut[] = { 60, 90 };` | "Kicks users from server if they spend too much time in briefing (map) screen" | ditto for the second gate |
| `lobbyIdleTimeout = 300;` | "The amount of time the server will wait before **force-starting a mission** without a logged-in Admin." Floor is `MAX(votingTimeout, lobbyTimeout, briefingTimeout, debriefingTimeout) + 5` | Starts the *mission*; does not slot anybody |
| `autoSelectMission = true;` | "the server auto-starts next mission in mission cycle and **waits for players in the role selection**. […] This is lesser-variant (trimmed) of `-autoInit`" | Explicitly confirms that server-side auto-start still parks arriving clients at role selection |
| `headlessClients[] = { "<IP>" };` | HC IP whitelist; required, see §3 | |
| `localClient[] = { "<IP>" };` | "clients with *unlimited* bandwidth and *nearly no latency*" | |

— all from *Arma 3: Server Config File*. https://community.bistudio.com/wiki/Arma_3:_Server_Config_File

**Nothing in server.cfg on 2.20 assigns a slot.** (2.22 changes this — §5.3.)

---

## 3. Question 2 — how real headless-client deployments get the HC into the mission

### 3.1 The engine is supposed to do it, unprompted

> "your client will be **automatically connected to a free headless client slot**"

> "Note: **HCs are automatically assigned to their slots**"

— *Arma 3: Headless Client*. https://community.bistudio.com/wiki/Arma_3:_Headless_Client

`[SECONDARY]` LinuxGSM states the same: "The headless client will connect and **automatically assume the first available headless client slot**." https://docs.linuxgsm.com/game-servers/arma-3

So there is **no** `skipLobby`, `joinUnassigned`, or client parameter in the headless path. The HC has no UI at all (`hasInterface` is false, no displays exist), so it cannot be "clicking OK" and cannot be helped by UI automation. If an HC is not in the mission, the engine's auto-assignment did not fire — and the overwhelmingly documented reason for that is the next point.

### 3.2 An explicit `HeadlessClient_F` slot is **required**, and it **must have a variable name**

Required:

> 1. Add a **Headless Client** entity to the mission:
>    1. Add a player unit
>    2. Then you can insert a Headless Client unit: `SIDE: Game Logic, CLASS: Virtual Entities, UNIT: Headless Client, CONTROL: Playable, NAME: somename`
>    3. **Don't forget to set NAME property, it is necessary for the Headless Client to work correctly.** The name can also be used to identify Headless Clients in scripts (by checking it against `player`).
>    4. **Each Headless Client unit will add one Headless Client slot** — missions may contain multiple Headless Client units

— *Arma 3: Headless Client*. https://community.bistudio.com/wiki/Arma_3:_Headless_Client

That is a first-party "necessary". It is corroborated by four independent, widely-deployed frameworks, all of which set `name=` on the logic entity — read from their actual `mission.sqm`, not their docs:

| Framework | `mission.sqm` HC entity |
|---|---|
| KP Liberation | `dataType="Logic"; … name="HC1"; isPlayable=1; type="HeadlessClient_F";` (also `HC2`, `HC3`) |
| A3Wasteland | `name="A3W_HC1"; isPlayable=1; description="DO NOT RENAME"; … type="HeadlessClient_F";` |
| ALiVE | `name="hc1"; isPlayable=1; type="HeadlessClient_F";` (also `hc2`, `hc3`) |
| Apex Framework | `name="headlessclient1"; isPlayable=1; type="HeadlessClient_F";` (×4) |

`[SECONDARY]` — sources in §8.3. A3Wasteland's `description="DO NOT RENAME"` is a maintainer note to their own users, which tells you how load-bearing the name is treated as being in practice.

And `[SECONDARY]`, the exact failure signature reported by others with the exact fix:

> Thread title: **"Headless Clients will connect but will not slot in"** (Steam, 2018-05-06). Reported again 2019-12 and 2023-04. Solution posted 2023-11 by *Mortibus Ostium*: **"give the Headless Client (HC) a variable name in your mission"**. Confirmed working by another user 2024-02.

— https://steamcommunity.com/app/107410/discussions/1/1696046342868673363/

`[SECONDARY]` Werthles' Headless Module (a widely used HC mod) instructs users to create "**playable, uniquely named**, headless clients". https://steamcommunity.com/sharedfiles/filedetails/?id=510031102

**This repository's HC entity has no `name`.** `missions/spike.Stratis/mission.sqm`, `Mission > Entities > Item1`:

```cpp
class Item1
{
    dataType="Logic";
    class PositionInfo { position[]={1710.5,5.5,5660.5}; };
    isPlayable=1;          // <-- no name= above this line
    id=3;
    type="HeadlessClient_F";
    atlOffset=0;
    class CustomAttributes {};
};
```

versus KP Liberation's working entity, which differs in exactly one line:

```cpp
class Item11
{
    dataType="Logic";
    class PositionInfo { position[]={14513.025,6.9429908,5892.7065}; };
    name="HC1";            // <-- present
    isPlayable=1;
    id=606;
    type="HeadlessClient_F";
    atlOffset=-0.057985783;
};
```

This is the highest-value single finding in this document, and it is testable in one edit.

### 3.3 Ordering: server first, HC second, mission already running is fine

No ordering requirement beyond "server before HC" appears anywhere. `[SECONDARY]` LinuxGSM: "Start your server with `./arma3server start`. Start your headless client with `./arma3server-hc start`." Bohemia's own note implies HCs may also connect *first*:

> "That happens only for GUI clients, **if HC client connects first**, EH does not fire for server."

— *Arma 3: Mission Event Handlers*, `PlayerConnected`. https://community.bistudio.com/wiki/Arma_3:_Mission_Event_Handlers

With `-autoInit` the mission is already running when the HC arrives, i.e. the HC is a JIP client. That is normal and supported. One trap to be aware of, though it does not bite here:

> "Disabling AI units will prevent **JIP into playable units if respawn is disabled**."

— *Description.ext*, `disabledAI`. This repo has `respawn = "BASE"`, so JIP is available. A mission with `disabledAI = 1` **and** no respawn would block JIP outright.

### 3.4 A complete, known-working recipe

Assembled from the sources above; the server and client lines are Bohemia's verbatim, the mission fragment matches all four frameworks.

**server.cfg**
```cpp
headlessClients[] = { "127.0.0.1" };
localClient[]     = { "127.0.0.1" };
persistent        = 1;              // required for -autoInit
class Missions { class MyMission { template = "my.Terrain"; }; };
```

**server**
```
./arma3server_x64 -config=server.cfg -port=2302 -autoInit
```

**headless client** (same box, same binary)
```
./arma3server_x64 -client -connect=127.0.0.1 -port=2302 -password=<server password>
```

**mission.sqm** — one Logic entity per HC, each with a unique `name`:
```cpp
class ItemN
{
    dataType="Logic";
    class PositionInfo { position[]={…}; };
    name="HC1";
    isPlayable=1;
    id=…;
    type="HeadlessClient_F";
};
```

**description.ext** — `class Header { maxPlayers = <players + HCs>; }`.

**init.sqf** — the `-autoInit`-safe HC bootstrap:
```sqf
if (!hasInterface && !isServer) then { execVM "init_HC.sqf"; };
```
— *Arma 3: Headless Client*. (Do **not** use that page's alternative `class params` + `isGlobal=1` route: `-autoInit` breaks mission parameters — §2.4.)

`[SECONDARY]` Two extras from community/wiki practice worth knowing:
- LinuxGSM and the *Dedicated Server* wiki page both say the HC profile needs `battleyeLicense=1;` in `~/.local/share/Arma 3 - Other Profiles/<profile>.Arma3Profile`. Almost certainly moot here (`battlEye = 0;`), but free to add.
- The *Dedicated Server* page also reports "Dwarden suggests that `battleyeLicense=1;` be in the server's config, but it is unclear whether this is actually necessary."

---

## 4. Question 3 — is there a server-side SQF route to force a connected client into a slot?

### 4.1 On 2.20: no. And the reason is structural, not a missing command.

Go back to the state ladder (§1). A client in role selection is at state 5, `"MISSION ASKED"`. It has not received the mission (state 7), has not loaded it (8), and has not run a single line of mission SQF. There is no script VM on that machine holding your functions. `remoteExec`, `publicVariableClient`, mission event handlers, CBA — none of them have anywhere to land. **You cannot script your way onto a machine that has not yet loaded the mission.**

That disposes of the whole question for a *human* client. The individual commands then confirm it:

| Command | Verdict | Source |
|---|---|---|
| `selectPlayer` | `arg= local`, `eff= global`. Must run **on the client whose player is being moved**, which by the above is unreachable at state 5. Also: "Avoid using `selectPlayer` on editor-placed units in multiplayer, as it may, on occasion, lead to some undefined behaviour." Useful for *swapping* a player who is already in the mission — not for admitting one | https://community.bistudio.com/wiki/selectPlayer |
| `setPlayable` | **Dead.** Filed under group **"Broken Commands"**: "This command does not work as intended and **currently does nothing** in Arma 3." | https://community.bistudio.com/wiki/setPlayable |
| `addPlayableUnit` | **Does not exist** — no such wiki page. The nearest live command is `addSwitchableUnit`, which is Team Switch (singleplayer), not MP slots | (wiki 404) |
| `assignAsSafe` | **Does not exist.** The `assignAs*` family (`assignAsDriver`, `assignAsCargo`, …) assigns *vehicle seats* — "Assign a unit as driver of a vehicle. Used together with `orderGetIn`" | https://community.bistudio.com/wiki/assignAsDriver |
| `onPlayerConnected` / `"PlayerConnected"` MEH | Server-side **notification**, no control. The MEH is documented as firing "when client **joins the mission**" — i.e. at/after role assignment, which is exactly why it is silent for a client stuck at state 5 | https://community.bistudio.com/wiki/onPlayerConnected · https://community.bistudio.com/wiki/Arma_3:_Mission_Event_Handlers |
| `serverCommand "#…"` | Requires logged-in admin **or** `serverCommandPassword`, and the command set has no slot verb. `#reassign` = "Start over and reassign roles" (throws *everyone* back to role selection — the opposite of what is wanted); `#userlist`, `#restart`, `#init` (reload server.cfg) | https://community.bistudio.com/wiki/serverCommand · https://community.bistudio.com/wiki/Multiplayer_Server_Commands |
| JIP / respawn machinery | Governs what happens *after* state 6 | — |

### 4.2 What the server **can** do on 2.20: see exactly where a client is stuck

This is the practical payoff, and it needs no mission change.

```sqf
allUsers          // Array of String - "Returns a list of player ids of all the users on an MP
                  //  server." "This also lists Headless Clients."  (serverExec, since 2.06)

getUserInfo _id   // [playerID, owner, playerUID, soldierName, displayName, steamProfileName,
                  //  clientStateNumber, isHeadless, adminState, networkInfo, playerObject]
                  //  index 6 = clientStateNumber, index 7 = isHeadless   (serverExec, since 2.06)
```

— https://community.bistudio.com/wiki/allUsers · https://community.bistudio.com/wiki/getUserInfo

`allUsers` lists users at the **connection** level, so a client parked at state 5 appears there even though `allPlayers`, `playableUnits` and `entities "HeadlessClient_F"` are all empty. `getUserInfo … select 6` then reports the exact rung of the ladder it is stuck on, and `select 7` confirms whether the server considers it a headless client at all. **That single probe distinguishes "no identity (state ≤ 3)" from "no slot available (state 5)", which is the open question in this repo's bug.**

The same commands are available in the **server-side scripting VM** (a separate VM from mission scripting, driven by `server.cfg` callbacks) since 2.18 — `allUsers`, `getUserInfo`, `callExtension`, `missionNamespace`, `uiNamespace`, `getVariable`/`setVariable`, `diag_log`, `waitUntil`. So this works even with no mission loaded:

```cpp
// server.cfg
onUserConnected = "diag_log str (getUserInfo _this);";
```

— *Arma 3: Server Side Scripting*, "Event Handlers" / "Shared Commands". https://community.bistudio.com/wiki/Arma_3:_Server_Side_Scripting

(`onUserConnected` fires on "user has connected" with parameter "user id" — earlier than the mission-level `PlayerConnected`. `regularCheck` — "called time by time for each user" — gives a polling variant.) **Untested here**, but every piece is individually documented.

Also note, directly relevant to this project's Rust shim: **`callExtension` is available inside the server-side VM as of 2.18**, and the wiki documents a full `onPlayerJoinAttempt` → extension → `ACCEPT`/`DELAY`/`REFUSE` handshake pattern, including the mission-side `"ExtensionCallback"` MEH. That is a supported route for the daemon to gate and observe joins without any mission SQF being loaded.

### 4.3 On 2.22 (currently RC, **not** shipped): yes, first-party and exactly what is wanted

> **OnAutoSelectRole** {{arma3 2.22}} — When player joins server and tries to auto select a role (`joinUnassigned=0` or `skipLobby=1`). **This should return the index of the role the player should join into.** Return `-1` to not select any role (Note this will break skipLobby). Return `Nothing` to let the engine code select one.
> Params: `name: String`, `userId: String`

> **OnPlayerSelectRole** {{arma3 2.22}} — When player selects a role. **Return the index of the role the player should be placed into.** Preferably equal to `wantedRoleIndex`, `-1` to block role selection (will break skipLobby), or **a different index to put the player elsewhere**.
> Params: `name: String`, `userId: String`, `wantedRoleIndex: Number`

> **getRoles** {{server-side command}} — Returns array of roles (array index == role index), **to be used in "OnAutoSelectRole" event**. Format `[Side, groupIndex, unitIndex, unit class, isTeamLeader, playerID, roleDescription, unitVarName, flags [Locked, EnabledAI, Forced, **Headless**]]`.

— *Arma 3: Server Side Scripting*. https://community.bistudio.com/wiki/Arma_3:_Server_Side_Scripting

This is a deterministic, server-authoritative slot assignment API, complete with a `Headless` flag per role and a `unitVarName` field — i.e. Bohemia added precisely the hook this project needs, and it is reachable from `server.cfg` with no mission code.

**Availability check (fetched today):** dev.arma3.com still reports `CURRENT VERSION 2.20`; newest SPOTREP is #00119 (2025-06-25, Hotfix 2.20); Update **2.22 is in Release Candidate testing** with published access code `Arma3Update222RC`. https://dev.arma3.com/spotrep

So on the shipped 2.20.152984 build in use here, these three do **not** exist. They are available today only on the `rc` Steam branch. Whether to take that dependency is a project decision, but it should be a conscious one: the RC branch is a **hard fork for connectivity** — "Only DEV clients can connect to a DEV server / Only Stable clients can connect to stable servers" (*Arma 3: Dedicated Server*), so client and server would have to move together.

---

## 5. Question 4 — what `Server error: Player without identity <name> (id N)` means

**No first-party definition exists.** `feedback.bistudio.com/T72887` is titled *"Server error: Player without identity"* but is 403-blocked, and every forum thread on it is likewise unreachable (§0). What follows is inference from the one primary artefact that does describe "identity" in this context, plus `[SECONDARY]` reports.

**Best-evidenced reading:** the string reports that the server has a connection carrying a numeric DirectPlay id but no created identity — i.e. a client at or below **state 2 `"CONNECTED"`, which has not reached state 3 `"LOGGED IN" — "Identity is created"**. The form of the observed message supports this: `Player without identity headlessclient (id 336778391)` carries a **plain numeric DirectPlay id**, not the `HC<pid>` form that the engine uses once a headless client has an identity (§7). In other words, at the moment that line was printed the server knew a connection and a name but had not yet minted the identity record for it.

`[SECONDARY]` corroborating characterisations from search extracts of the (unreachable) threads, offered only as weak support:
- The message is reported as **benign and routine** for the first client connecting to a dedicated server that is starting a mission.
- When it is *not* benign, it is reported alongside failed joins and characterised as "your ID is not valid or not generated" — a Steam-auth or identity-registration failure, sometimes attributed to Steam rather than Arma.
- One thread specifically titles it as caused by a **mission file** on a **Linux** dedicated server.

Sources (titles/extracts only; bodies unreachable): https://feedback.bistudio.com/T72887 · https://forums.bohemia.net/forums/topic/154810-… · https://forums.bohemia.net/forums/topic/145949-… · https://forums.bohemia.net/forums/topic/228192-…

**Confidence: low-to-medium on the mechanism, high on the state-machine mapping.** Do not treat this line as the primary symptom: it appeared in only one of this repo's runs, and the state probe in §4.2 will settle in one measurement what the log line only hints at.

---

## 6. Question 5 — does a headless client need a Steam session/identity to be assigned a role?

**Answer: no.** This closes the open item flagged in `docs/research/linux-server-steamcmd.md` §3.1. Three independent lines of evidence:

**1. The engine mints a synthetic UID for headless clients — it never asks Steam for one.** Bohemia documents the `PlayerConnected` payload for HCs explicitly:

> "Interesting moment for headless clients, for headless clients **instead of `getPlayerUID`, handler gets string like `"HC12160"`, where '12160' is headless client process ID** (matches HC's PID observed in windows task manager)"

— *Arma 3: Mission Event Handlers*, `PlayerConnected`. https://community.bistudio.com/wiki/Arma_3:_Mission_Event_Handlers

`getPlayerUID` **is** the Steam ID in Arma 3 (*onPlayerConnected*: "`_uid` … is `getPlayerUID` of the joining player. In Arma 3 it is also the same as Steam ID"). The engine substituting a PID-derived string for HCs is a first-party statement that HC identity is *not* Steam identity. This repo's own observed log line — `id=HC<pid>` — is exactly that format, which means **the server already assigned this repo's HC a valid headless identity.**

**2. This repo's own experiment shows the whitelist is the Steam-check bypass.** Removing `headlessClients[]` produced `Client kicked due to failed Steam checks: Invalid ticket - Ticket invalid`; restoring it removed the kick. The straightforward reading is that `headlessClients[]` is precisely the mechanism by which the server exempts a whitelisted address from Steam ticket validation. If a Steam session were required regardless, whitelisting could not have made the Steam check go away.

**3. The conflicting wiki note is scoped to the Windows game client.** The *Dedicated Server* page says:

> "Headless Client for Arma 3 requires a **valid active Steam account logged in** to function (see Dwarden's post)"
> "A Headless Client is simply **Arma3.exe** run from the command line with parameters"

— https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server

Every example in that section is `arma3.exe` with `C:\Users\…\Documents\Arma 3 - Other Profiles\HC`. The *Headless Client* page, by contrast, lists `Linux server executable: arma3server -client` as a first-class run option and says nothing about Steam. The cited Dwarden forum post remains unreachable (403), so the citation itself cannot be checked — but the claim is about the `arma3.exe` path, which is not the path in use here.

**Weigh it against the lobby framing, as instructed:** the brief is right that the lobby hypothesis made a Steam explanation look less likely, and the evidence above pushes further in the same direction. **A Steam-identity requirement is not the cause here.** The HC already has a valid engine identity (`HC<pid>` appeared in the log); what it does not have is a slot.

---

## 7. Summary table

| Question | Answer | Confidence |
|---|---|---|
| Can an unattended **GUI client** skip role selection? | **Yes — `skipLobby = 1;` in `description.ext`** (Arma 3 1.60+). "joining player will join the mission bypassing role selection screen" | **High** (BI wiki, verbatim) |
| Does `joinUnassigned` help? | Yes, **but inverted**: `joinUnassigned = 0` forces assignment; `= 1` (this repo's current value, and the engine default) leaves the client unassigned | **High** (BI wiki prose + 2.22 `OnAutoSelectRole` text + 3 shipping missions) |
| Is there a client startup parameter? | **No.** Client Network Options are only `-connect`, `-port`, `-password` | **High** (full page enumerated) |
| `-init=` as an auto-slotter? | Structurally plausible (runs SQF in main menu, where display 61 lives); **no documentation, no known example, untested** | **Speculative** |
| Does `respawnOnStart` / `class Params` / zero-slot mission change it? | **No.** `respawnOnStart` acts post-join; `class Params` is admin-facing **and is broken by `-autoInit`**; a zero-slot mission is a dead end | **High** |
| Is the briefing/CONTINUE screen a second gate? | **Yes** (states 9→10, display 53). `briefing = 0` is documented as SP-oriented and `[SECONDARY]` reported broken in MP; `ctrlActivate (findDisplay 53 displayCtrl 1)` is the community workaround | **Medium** |
| How do real HC deployments slot the HC? | The **engine auto-assigns** it — "HCs are automatically assigned to their slots". No lobby settings involved; the HC has no UI to click with | **High** |
| Is an explicit `HeadlessClient_F` slot required? | **Required.** "Each Headless Client unit will add one Headless Client slot" | **High** |
| Must the HC entity have a variable name? | **Yes.** "Don't forget to set NAME property, it is necessary for the Headless Client to work correctly." All four frameworks examined set it. Missing-name is the exact reported cause of "connects but will not slot in" | **High** (wiki "necessary" + 4 shipping missions + matching `[SECONDARY]` bug report/fix) |
| **Does this repo's `mission.sqm` have it?** | **No — the `HeadlessClient_F` entity has no `name=`.** Prime suspect | **High** (file read) |
| Ordering requirement? | Server before HC. Mission already running (`-autoInit`) is fine; HC joins as JIP | **High** |
| Server-side SQF to force a slot, on **2.20**? | **No.** `setPlayable` is a documented Broken Command; `addPlayableUnit`/`assignAsSafe` do not exist; `selectPlayer` must run on a client that has no mission loaded; `serverCommand` has no slot verb | **High** |
| Server-side SQF to force a slot, on **2.22**? | **Yes** — `OnAutoSelectRole`, `OnPlayerSelectRole`, `getRoles` in the server-side VM, with a per-role `Headless` flag. **2.22 is RC-only today** (code `Arma3Update222RC`); shipped branch is 2.20 | **High** (wiki + dev hub) |
| Can the server *observe* a stuck client on 2.20? | **Yes** — `allUsers` + `getUserInfo` (index 6 = clientStateNumber, 7 = isHeadless), available in mission SQF **and** in the `server.cfg` scripting VM since 2.18 | **High** (documented; probe itself untested) |
| `Server error: Player without identity` | Best reading: a connection at state ≤2 that has not reached state 3 `"LOGGED IN" — "Identity is created"`. Widely reported as benign for the first connector | **Low-medium** (all primary sources 403; inference from the state table) |
| Does an HC need a Steam session to be slotted? | **No.** Engine substitutes `"HC<pid>"` for `getPlayerUID` on HCs; `headlessClients[]` whitelisting is what bypasses the Steam ticket check; the contrary wiki note is scoped to `arma3.exe` | **Medium-high** (settles `linux-server-steamcmd.md` §3.1) |

---

## 8. Appendix — raw evidence

### 8.1 Wiki access recipe that works today

The bare recipe in the previous research document now returns a Cloudflare challenge. This one returns JSON:

```bash
curl -sS --compressed \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36' \
  -H 'Accept: application/json,text/html;q=0.9,*/*;q=0.8' \
  -H 'Accept-Language: en-GB,en;q=0.9' \
  -H 'Sec-Fetch-Dest: empty' -H 'Sec-Fetch-Mode: cors' -H 'Sec-Fetch-Site: same-origin' \
  "https://community.bistudio.com/wikidata/api.php?action=query&prop=revisions&rvslots=main&rvprop=content|timestamp&format=json&redirects=1&titles=Arma%203:%20Headless%20Client"
```

Pages retrieved and their revision timestamps:

| Page | Revision |
|---|---|
| `Arma 3: Headless Client` | 2024-02-12 |
| `Description.ext` | 2026-04-29 |
| `Arma 3: Server Config File` | 2026-05-19 |
| `Arma 3: Dedicated Server` | 2026-05-22 |
| `Arma 3: Startup Parameters` | 2026-05-10 |
| `Arma 3: Server Side Scripting` | 2026-05-08 |
| `Arma 3: Mission Event Handlers` | 2026-05-15 |
| `Multiplayer Scripting` | 2025-12-31 |
| `Multiplayer Server Commands` | 2025-06-11 |
| `Arma 3: IDD List` | 2023-09-10 |
| `selectPlayer` | 2024-03-29 · `setPlayable` 2023-05-30 · `onPlayerConnected` 2024-09-15 · `allUsers` 2026-05-04 · `getUserInfo` 2026-03-10 · `isPlayer` 2024-03-29 · `allPlayers` 2024-11-10 · `serverCommand` 2026-01-04 · `playableUnits` 2026-01-01 |

Pages that do **not** exist (requested, returned `missing`): `Arma 3: Mission Description.ext`, `addPlayableUnit`, `Arma 3: Multiplayer Game Types` (it is `Multiplayer Game Types`), `Arma 3: Multiplayer Scripting` (it is `Multiplayer Scripting`).

`getClientState` and `getClientStateNumber` returned **403 on four attempts** across ~30 s of spacing while neighbouring titles returned 200 — cause unknown. Their content is quoted here from the `Multiplayer Scripting` page's own client-state table instead, which is the same data.

### 8.2 `Arma 3: Startup Parameters` — complete Client Network Options section

```
== Client Network Options ==
=== connect ===   Server IP to connect to.        arma3_x64.exe -connect=168.152.15.147
=== port ===      Server port to connect to.      arma3_x64.exe -port=1337
=== password ===  Server password to connect to.  arma3_x64.exe -password=1337abc
=== host ===      Start a non-dedicated multiplayer host.
```

All 83 `==`/`{{ArgTitle}}` headings on the page were enumerated; no auto-slot, auto-join, or role parameter exists anywhere on it.

### 8.3 Headless-client entities read from shipping missions

```
KP Liberation   Missionbasefiles/kp_liberation.Altis/mission.sqm     name="HC1" | "HC2" | "HC3"
A3Wasteland     ArmA3_Wasteland.Stratis/mission.sqm                  name="A3W_HC1" | "A3W_HC2"
                                                                     description="DO NOT RENAME"
ALiVE           addons/missions/MPScenarios/ALiVE_PF.Cam_Lao_Nam/    name="hc1" | "hc2" | "hc3"
Apex Framework  Apex_framework.terrain/mission.sqm                   name="headlessclient1".."4"
```

- https://github.com/KillahPotatoes/KP-Liberation — `Missionbasefiles/kp_liberation.Altis/mission.sqm`
- https://github.com/A3Wasteland/ArmA3_Wasteland.Stratis — `mission.sqm`
- https://github.com/ALiVEOS/ALiVE.OS — `addons/missions/MPScenarios/ALiVE_PF.Cam_Lao_Nam/mission.sqm`
- https://github.com/auQuiksilver/Apex-Framework — `Apex_framework.terrain/mission.sqm`

GitHub code search for `"HeadlessClient_F" filename:mission.sqm` returns **912** files; the four above were sampled as the best-known/most-deployed.

### 8.4 Lobby settings in the same shipping missions

| Mission | `skipLobby` | `joinUnassigned` | `disabledAI` | Has HC slots |
|---|---|---|---|---|
| KP Liberation | `0` | `1` | `1` | yes |
| A3Wasteland | (absent) | `0` | `1` | yes |
| Apex Framework | `0` (with warning, below) | `0` | `1` | yes |
| ALiVE `ALiVE_PF` | (absent) | `1` | `0` | yes |
| Mike Force | `0` | `0` | `1` | — |
| **Synixe Contractors MissionTemplate** | **`1`** | (absent) | `1` | — |

Apex Framework's inline comment, verbatim:

```cpp
skipLobby = 0;   // Player skips lobby on join. An attractive idea, however many players report
                 // "Stuck on receieving data" when this is enabled due to bugged lobby slots.
                 // So we leave this off for stability.
joinUnassigned = 0;   /*/ 0 = players forced into role on join/*/
```

— `[SECONDARY]` https://github.com/auQuiksilver/Apex-Framework — `Apex_framework.terrain/description.ext`

**Note the gap:** GitHub code search found **zero** repositories containing both `skipLobby = 1` and `HeadlessClient_F`. Every framework that ships headless-client support leaves `skipLobby` off and uses `joinUnassigned = 0` (or nothing). **The `skipLobby = 1` + headless-client combination is unattested in the wild** — that is not evidence it breaks, but it is a reason to change one thing at a time.

### 8.5 This repository's current configuration, as read

`missions/spike.Stratis/description.ext`: `joinUnassigned = 1;` (leaves clients unassigned — §2.2), `disabledAI = 1;`, `briefing = 0;`, `debriefing = 0;`, `respawn = "BASE";`, `respawnDelay = 5;`, `class Header { gameType="Coop"; minPlayers=1; maxPlayers=2; }`. **No `skipLobby`. No `respawnOnStart`.**

`missions/spike.Stratis/mission.sqm`: one `B_Soldier_F` with `isPlayable=1; description="Spike Slot Alpha";` inside a West group; one `HeadlessClient_F` Logic with `isPlayable=1` and **no `name=`**; a `respawn_west` marker.

`spike/server.cfg`: `headlessClients[]`/`localClient[]` both `{"127.0.0.1","localhost","192.168.1.36"}`, `persistent = 1;`, `verifySignatures = 0;`, `battlEye = 0;`, `allowedFilePatching = 2;`, `class Missions { class Spike { template = "spike.Stratis"; difficulty = "veteran"; }; }`. **No `onUserConnected`, no `roleTimeOut` override.**

`spike/run.sh`: server `-config -cfg -port -name=ctispike -world=empty -autoInit -noSound -limitFPS=100`; HC `-client -connect=127.0.0.1 -port=$PORT -password=… -name=ctihc1 -world=empty -noSound -limitFPS=50`. The script's own comment already records the key observation: *"The HC's player name is `headlessclient` regardless of `-name=`, and it is assigned an `id=HC…` rather than a numeric slot id."* That `HC…` form is Bohemia's documented headless identity (§6) — the HC **has** an identity.

### 8.6 Source URLs

Primary (Bohemia):
- *Arma 3: Headless Client* — https://community.bistudio.com/wiki/Arma_3:_Headless_Client
- *Description.ext* — https://community.bistudio.com/wiki/Description.ext
- *Arma 3: Server Config File* — https://community.bistudio.com/wiki/Arma_3:_Server_Config_File
- *Arma 3: Dedicated Server* — https://community.bistudio.com/wiki/Arma_3:_Dedicated_Server
- *Arma 3: Startup Parameters* — https://community.bistudio.com/wiki/Arma_3:_Startup_Parameters
- *Arma 3: Server Side Scripting* — https://community.bistudio.com/wiki/Arma_3:_Server_Side_Scripting
- *Arma 3: Mission Event Handlers* — https://community.bistudio.com/wiki/Arma_3:_Mission_Event_Handlers
- *Multiplayer Scripting* (client-state table, JIP) — https://community.bistudio.com/wiki/Multiplayer_Scripting
- *Multiplayer Server Commands* — https://community.bistudio.com/wiki/Multiplayer_Server_Commands
- *Multiplayer Game Types* — https://community.bistudio.com/wiki/Multiplayer_Game_Types
- *Arma 3: IDD List* — https://community.bistudio.com/wiki/Arma_3:_IDD_List
- *Initialisation Order* — https://community.bistudio.com/wiki/Initialisation_Order
- Commands: `selectPlayer`, `setPlayable`, `onPlayerConnected`, `allUsers`, `getUserInfo`, `serverCommand`, `isPlayer`, `allPlayers`, `playableUnits`, `didJIP`, `assignAsDriver`
- SPOTREP index / current version / 2.22 RC — https://dev.arma3.com/spotrep

`[SECONDARY]`:
- LinuxGSM Arma 3 — https://docs.linuxgsm.com/game-servers/arma-3 (raw: `GameServerManagers/LinuxGSM-Docs/game-servers/arma-3.md`)
- Killzone_Kid, "How To Skip Briefing Screen In MP" — https://killzonekid.com/arma-scripting-tutorials-how-to-skip-briefing-screen-in-mp/
- Steam: "Headless Clients will connect but will not slot in" — https://steamcommunity.com/app/107410/discussions/1/1696046342868673363/
- Werthles' Headless Module — https://steamcommunity.com/sharedfiles/filedetails/?id=510031102
- Mission sources: KP Liberation, A3Wasteland, ALiVE.OS, Apex Framework, Mike Force, Synixe Contractors MissionTemplate (§8.3, §8.4)

Attempted and unreachable (403): `feedback.bistudio.com/T72887`, `feedback.bistudio.com/T79316`, all `forums.bohemia.net` threads (direct and via `r.jina.ai`), Dwarden's HC/Steam posts cited by the wiki.

---

## VERDICT

**Role selection can be skipped, and the way to do it is `skipLobby = 1;` in `description.ext` — but that is almost certainly not what is wrong with the headless client, and the two problems should be fixed separately.** For the Windows GUI client the answer is unambiguous and first-party: `skipLobby = 1` makes a joining player "join the mission bypassing role selection screen" and take "first available role from mission template" (Arma 3 1.60+), with `joinUnassigned = 0` as the weaker sibling that assigns a slot without necessarily bypassing the screen. Note that this repo currently sets `joinUnassigned = 1`, which is the value that *keeps* a client unassigned — the parameter's name is the opposite of its effect, and Bohemia's own 2.22 documentation confirms the auto-assign path fires on "`joinUnassigned=0` or `skipLobby=1`". There is **no client-side startup parameter** for any of this: the entire Client Network Options section is `-connect`, `-port`, `-password`. Budget for a *second* gate too — the briefing/CONTINUE screen (client states 9→10, display 53) is distinct from role selection (state 5→6), `briefing = 0` is documented as an SP-oriented setting and is `[SECONDARY]`-reported as inert in MP, and the community fix is `ctrlActivate (findDisplay 53 displayCtrl 1)` from a `preInit` function.

**The headless client is a different bug and the prime suspect is one missing line.** An HC has no UI, cannot be "in" the role-selection display, and is documented to be slotted by the engine without any lobby settings at all: "your client will be automatically connected to a free headless client slot" and "HCs are automatically assigned to their slots". What the engine needs in order to do that is a `HeadlessClient_F` Logic entity that is `isPlayable=1` **and has a variable name** — the wiki calls the name "necessary for the Headless Client to work correctly", KP Liberation, A3Wasteland, ALiVE and Apex Framework all set it in their shipping `mission.sqm` (A3Wasteland annotates theirs `description="DO NOT RENAME"`), and the exact symptom reported here — "connects but will not slot in" — has a public fix that is precisely "give the HC a variable name". **This repo's HC entity has no `name=`.** That single edit is the first thing to try, and nothing else in this document should be changed at the same time.

**There is no server-side SQF route to force a slot on 2.20, and the reason is structural rather than a missing command.** A client at role selection is at state 5 `"MISSION ASKED"`: it has not received or loaded the mission, so no mission script VM exists on it and nothing can be remote-executed to it. Consistently, `setPlayable` is filed by Bohemia under "Broken Commands" and "currently does nothing", `addPlayableUnit` and `assignAsSafe` do not exist, `selectPlayer` must run on the unreachable client, and `serverCommand` has no slot verb (`#reassign` throws everyone *back* to role selection). What the server *can* do today, with no mission change, is **see** the problem: `allUsers` lists connection-level users including HCs even when `allPlayers` is empty, and `getUserInfo` returns `clientStateNumber` at index 6 and `isHeadless` at index 7 — available in mission SQF and, since 2.18, in the `server.cfg` scripting VM (so `onUserConnected = "diag_log str (getUserInfo _this);";` works before any mission loads). Running that probe converts this whole investigation into one number and should be the very next measurement. Looking forward, **Arma 3 2.22 adds exactly the API this project wants** — `OnAutoSelectRole`, `OnPlayerSelectRole` and `getRoles` (with a per-role `Headless` flag and `unitVarName`) let `server.cfg` deterministically place any joining client into a chosen role index — but 2.22 is still RC-only (`Arma3Update222RC`), the shipped branch is 2.20, and RC and stable cannot interconnect, so adopting it means moving client and server together.

**`Server error: Player without identity` is not the lead it looks like, and a Steam session is not the blocker.** Every primary source for that string is 403-blocked, so the honest answer is *unresolved*; the best-evidenced reading is that it reports a connection that has not reached client state 3 `"LOGGED IN" — "Identity is created"`, and the numeric DirectPlay id in the observed message (rather than the `HC<pid>` form) fits that. It also appeared in only one run, and is `[SECONDARY]`-reported as routine for the first connector. Meanwhile the Steam question from `linux-server-steamcmd.md` §3.1 can now be closed as **no**: Bohemia documents that for headless clients the engine substitutes `"HC<pid>"` for `getPlayerUID` instead of a Steam ID, this repo's own logs already show `id=HC<pid>` (so the HC *has* a valid engine identity), and this repo's own experiment showed that whitelisting in `headlessClients[]` is what makes the Steam ticket check go away. The wiki's contrary "requires a valid active Steam account logged in" note is written entirely around the `arma3.exe` path and cites an unreachable forum post. **The headless client is not short of an identity; it is short of a slot to be put in.**
