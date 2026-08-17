# Prior art: automated testing against a live Arma 3 process

<!-- absent-path -->
<!-- A dated research record: the repository paths it cites are the tree as it stood when
     the research was done, and some belong to other projects entirely. Neither is a claim
     about this tree today, which is what the marker above tells `just check-doc-paths`. -->

**Researched**: 2026-07-30
**Question**: Which Arma 3 projects run genuine automated tests against a *running* game or server process, and how do they get a verdict out? Not "who lints" — `docs/research/arma-toolchain.md` §5 already established that ACE3, CBA_A3, ACRE2 and ZEN run HEMTT lints plus Python validators in CI and that none of them runs SQF-VM.

Claims marked **VERIFIED LOCALLY** were executed in this environment (WSL2, Linux 6.6) against real binaries. Claims marked `[SECONDARY]` rest on community sources rather than the project or vendor that owns the fact.

---

## 0. Method and source-access notes

| Source | Direct access | Route used |
|---|---|---|
| GitHub **code** search (`gh search code`) | Works, but **10 queries/minute** and the index is partial | Paced batches. Corroborated with repository search and direct tree reads |
| `raw.githubusercontent.com` | **200**, unmetered | Primary route for reading harness source verbatim |
| GitHub Actions **run history** API | **200** | Used to prove whether a workflow has ever actually executed — the decisive test for "real vs aspirational" |
| `community.bistudio.com/wiki/*` | **403** (Cloudflare) | MediaWiki API at `https://community.bistudio.com/wikidata/api.php` — **but only with a browser `User-Agent`**. A bare `curl` to the *API* is now also Cloudflare-challenged, which is a change from what `linux-server-steamcmd.md` §0 recorded. `curl -A "Mozilla/5.0 …"` works |
| BI wiki **search** (`list=search`) | Returns `totalhits: 0` by default, and for `insource:` queries | **`srwhat=text` is required.** With it, search works and was used for the negative results in §4.6 |
| `dev.arma3.com` | **200** | Fetched directly. §4.6's negative counts are over **all 479 posts** mirrored locally (SITREP #001–#00242, SPOTREP #00001–#00119, 57 TECHREPs, 60 OPREPs), not a sample |
| `forums.bohemia.net` | **403** | Not retrieved; claims sourced elsewhere or marked `[SECONDARY]` |

Two further wiki-API operational notes worth recording for the next researcher: Cloudflare rate-limits after roughly 8–10 requests, and the fix is **batching up to 10 page titles per call** with `titles=A|B|C`; `community.bohemia.net` is a live alias useful for spreading load; and `web.archive.org/web/2024/<wiki-url>` is a reliable fallback.

**Attribution caveat.** The BI Community Wiki is Bohemia-hosted but community-editable. Wiki prose is treated here as *documentation of Bohemia-built features*, not as Bohemia's own statement. Where a first-party anchor exists — SPOTREP/SITREP changelogs on `dev.arma3.com` — it is cited.

**A caution about GitHub code search.** It found the ATLAS.OS workflow instantly, but it did **not** find the strongest example in this report (Relicta) under any Arma-related query — because that project renames the Arma server binary to `cmp.exe` and never writes the string `arma3server` in its workflow. I only reached it by searching for the *side effects* of running Arma in CI (`choco install directx`, `vcredist2010`) rather than for Arma itself. Treat the negative results below as "very likely complete", not "provably complete".

---

## 1. The headline

**Two projects genuinely test against a live Arma process — one of them in public CI, on every pull request, and it works — and, separately, HEMTT itself already ships the exact bridge our architecture calls for.**

| | Runs a real Arma process | Automated (no human) | In CI | Verdict is machine-readable |
|---|---|---|---|---|
| **Relicta ReSDK_A3.vr** | Yes — Arma 3 dedicated server | **Yes** | **Yes, GitHub-hosted** | **Yes — process exit code** |
| **mil-sim (DUAS)** | Yes — Arma 3 server via Proton | **Yes** | No (EC2 box) | **Yes — exit code + JSONL** |
| **HEMTT `photoshoot`** | Yes — Arma 3 **client**, via `-autotest` | **Yes** | No (dev command) | n/a — it collects images, not verdicts |
| CySpiegel/ATLAS.OS | Would | Would | Workflow exists, **never run** | Would (RPT grep) |
| ACE3 / CBA / ALiVE / ACRE2 | Yes | **No — human pastes into debug console** | No | No |
| Everyone else | No | No | No | No |

### 1.1 Relicta `ReSDK_A3.vr` — the real thing

- **What it is**: the SDK for *Relicta*, a large Russian total-conversion mod for Arma 3. SQF + C++, MIT, 8 stars, last pushed 2026-05-23.
  <https://github.com/Relicta-Team/ReSDK_A3.vr>
- **Harness**: <https://github.com/Relicta-Team/RBuilder> — a **Python** application (`rb.exe` is a frozen build of it). Readable in full.
- **Relevance to us: maximal.** It is our intended architecture, already built and working: an out-of-process Python driver, an extension bridge into a live Arma 3 dedicated server, tests written in SQF, and a machine-readable verdict.

**It runs on GitHub-hosted `windows-latest` runners, and it passes.** From `.github/workflows/all_build.yml`:

```yaml
  checkserver-vm:
    name: Check server VM
    runs-on: windows-latest
    strategy:
      fail-fast: true
      matrix:
        flags:
          - -d DEBUG
          - -d RELEASE
          - -d TEST_ALL -d DEBUG
          - -d TEST_ALL -d RELEASE
    steps:
      - name: Setup msvc+directx
        run: |
          choco install directx
          choco install vcredist2010
          choco install vcredist2012
      - uses: actions/checkout@v3
      - name: Init RBuilder
        run: ${{env.rb_exe}} -init build -l
      - name: Run RBuilder
        run: ${{ env.rb_exe }} run ${{ matrix.flags }}
```
Source: <https://raw.githubusercontent.com/Relicta-Team/ReSDK_A3.vr/main/.github/workflows/all_build.yml>

Run history proves it executes rather than merely existing — `Check server VM (-d TEST_ALL -d DEBUG) -> success`, repeatedly, taking **6–10 minutes** per matrix leg:

```
run 26236711790  2026-05-21  Check server VM (-d TEST_ALL -d DEBUG)   -> success (15:45:39 .. 15:55:30)
                             Check server VM (-d TEST_ALL -d RELEASE) -> success (15:45:39 .. 15:51:56)
run 26061551634  2026-05-18  Check server VM (-d DEBUG)               -> failure
```
Source: `gh api repos/Relicta-Team/ReSDK_A3.vr/actions/workflows/59138241/runs`

**Where the Arma binary comes from — they vendor it, version-pinned.** `RBuilder/VM/` in the repo is a stripped Arma 3 install: `dta/bin.pbo`, `dta/core.pbo`, `dll/x64/PhysX_64.dll`, `jemalloc_bi_x64.dll`, `steam_appid.txt` containing `107410`. The executable itself is downloaded at `-init` time from a sibling repo:

```python
RBUILDER_NAME = "cmp.exe"
RBUILDER_DOWNLOAD_PATH = "https://raw.github.com/Relicta-Team/rb_vm/main/cmp_220"
```
Sources: <https://raw.githubusercontent.com/Relicta-Team/RBuilder/main/Constants.py>, <https://raw.githubusercontent.com/Relicta-Team/RBuilder/main/deploy.py>

`Relicta-Team/rb_vm` holds `cmp_216` (33.8 MB), `cmp_218` (35.4 MB), `cmp_220` (31.9 MB) — **one Arma 3 server binary per game version, 2.16 / 2.18 / 2.20**. That is a deliberate answer to engine drift: the engine under test is pinned in the same way a language toolchain is. (It is also a redistribution of Bohemia's binary, which we should not copy verbatim — see §7.3 for the licensed equivalent.)

That the process is a genuine Arma 3 **dedicated server** is settled by four independent artefacts, not by inference:

1. `RBuilder/VM/init.cfg` is an Arma server config — `hostName`, `passwordAdmin`, `BattlEye = 0;`, `verifySignatures = 0;`, `loopback=true;`, `allowedFilePatching = 2;`, and `class Missions { class Mission_1 { template = "loader.VR"; difficulty = "Regular";};};`
2. The launch arguments in `Runner.py`:
   ```python
   argsRun = f"-debug -config={cfgFile} -port=5678 -filePatching -autoInit -limitFPS=150 -noSplash"
   srvCli  = f'""-serverMod={srvModAbs}""'   # @server
   prof    = f"""-profiles={getAbsPath(vmDir)}\\profile"""
   ```
3. `RBuilder/loader/init.sqf` shuts the box down with a real server command: `rbuilder_password serverCommand "#shutdown";`
4. `Runner.py` hides the window titled `"Arma 3 Console"`.

**How the verdict escapes — three layers, all worth stealing.**

*(a) Test selection by preprocessor define.* `-d TEST_ALL` becomes a `-D`-style CLI macro handed to the engine, and the SQF side discovers tests by scanning the define map:

```sqf
{
	private _t = tolower _x;
	if (count _t > 5 && {_t select [0,5] == "test_"}) exitWith { _hasTests = true; };
} foreach RBuilder_map_defines;

if (_hasTests) then {
	["Starting tests..."] call cprint;
	loadFile("src\host\UnitTests\init.sqf");
	if isNull(test_run) exitWith { [-470,"Test runner function not found"] call RBuilder_exit; };
	call test_run;
};
```
Source: <https://raw.githubusercontent.com/Relicta-Team/ReSDK_A3.vr/main/Src/host/Tools/RBuilder/RBuilder_init.sqf>

*(b) Exit code, carried out through the extension.* `RBuilder_exit` resolves to `["RBuilder","exit",[_exit]] call rescript_callCommandVoid` — an extension call into their `@server` DLLs. The Python side then reinterprets the code, because Arma hands back a negative int as an unsigned:

```python
def conv_cmp_exitCode(uintCode):
    return cast(pointer(c_uint32(uintCode)),POINTER(c_int32)).contents.value
```
Source: <https://raw.githubusercontent.com/Relicta-Team/RBuilder/main/Runner.py>

*(c) A live TCP side channel.* `RunnerServer` binds `127.0.0.1:9897`, the in-game extension connects to it as a client, and messages are NUL-delimited UTF-8 both ways. It carries a `_preload` readiness handshake — and an `$interact_mode$` message that turns the harness into a **REPL against the live game**, where the developer types SQF at a Python prompt and the return value comes back:

```python
if mes.command=="_preload":
    preloaded = True
elif mes.command=="$interact_mode$" and preloaded:
    if mes.args and mes.args != "any":
        print(f"Return: {mes.args}")
    i = _multiline_input("Command:")
    server.addCallback(i if i else "null")
```
Source: <https://raw.githubusercontent.com/Relicta-Team/RBuilder/main/RunnerServer.py>

**Four supervision tricks in `Runner.py` that we should copy outright:**

- **Finding the RPT without guessing.** Rather than globbing profile directories, it asks the OS which `.rpt` the Arma process currently has open:
  ```python
  def get_opened_rpt_log(pid):
      for f in psutil.Process(pid).open_files():
          if f.path.endswith(".rpt"):
              return f.path
  ```
- **A readiness handshake, not a sleep.** `preload_timeout` bounds the wait, but the wait ends on the game's `_preload` message. Timeout is a *distinct* exit code (`RBUILDER_RUN_LOADING_TIMEOUT = -106`), not a generic failure — the same discipline as our `timeout` failure class.
- **Detecting Arma's fatal modal dialog.** Arma's "Fatal error" popup makes the process hang forever rather than exit. They enumerate the process's windows and treat a modal frame as a hard failure, scraping the dialog text for the message:
  ```python
  if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_DLGMODALFRAME:
      ...
      hndl.kill()
      exitCode = ExitCodes.RBUILDER_RUN_FATAL
  ```
  **This is a real hazard for a headless rig and nothing in the ATLAS.OS-style RPT-grep design catches it** — the workflow would just sit until its timeout.
- **A structured exit-code vocabulary** (`Constants.py`): `-105` run failed, `-106` loading timeout, `-107` fatal, `-108` preload error, `-109` define prep failed, `-400/-401` test load/run failure, `-410` assertion module missing, `-470` runner missing. That is our "failure classes" table, expressed as exit codes.

**The catch: it is Windows-only.** `Runner.py` imports `win32gui`, `win32process`, `win32con`; the modal-dialog detection and window hiding have no Linux analogue; and it runs the Windows server executable. Porting the *design* to a Linux/WSL2 rig is straightforward; porting the *code* is not.

**Its in-mission test framework is a gtest clone**, and the best-engineered SQF test framework found anywhere in this survey — fixtures, setup/teardown, per-test error counters, per-test timings, `__FILE__`/`__LINE__` in failure messages:

```c
#define FIXTURE_SETUP(fixtname) ...
#define FIXTURE_TEARDOWN(fixtname) ...
#define TEST_F(fixtname,testname) ...
#define TEST(testname) ...

#define EXPECT_EQ(expr,expect) if !(equals(expr,expect)) then {__RUT_ONERROR; \
    __RUT_EXPR_MESSAGE(expr,__FILE__,__LINE__,format vec3("Expected '%2'; got '%1'",expr,expect)) \
    call test_expectMessage;};
#define ASSERT_EQ(expr,expect) if !(equals(expr,expect)) then {__RUT_ONERROR; \
    __RUT_EXPR_MESSAGE(expr,__FILE__,__LINE__,...) call test_assertFail; __RUT_STOPTEST(-1)};
```
Source: <https://raw.githubusercontent.com/Relicta-Team/ReSDK_A3.vr/main/Src/host/UnitTests/TestFramework.h>

Note the `EXPECT_*` (continue) versus `ASSERT_*` (stop this test case) split, and that failures increment a counter which the module aggregates — the accumulator that CBA and ALiVE both lack (§3).

### 1.2 `JohnPeng47/mil-sim` (DUAS) — closed-loop control against a live Linux server

- **What it is**: a headless Arma 3 drone-interception scenario used as a simulator, driven entirely programmatically from an EC2 box with no display. C + Python, 0 stars, last pushed 2026-05-28.
  <https://github.com/JohnPeng47/mil-sim>
- **Relevance to us: very high.** It is the Linux half of what Relicta does on Windows, it makes a genuine *behavioural* assertion, and its README documents the gotchas that cost time.

**It runs the Windows server binary on Linux under Proton and Xvfb.** From `scripts/start_server.sh`:

```bash
PROTON_CMD=(
	./proton run ./arma3server_x64.exe
	-server -port="${PORT}" -config="${CONFIG_ARG}" -profiles="${PROFILE_ARG}"
	-name=duas -world="${WORLD}" -noSound -noSplash -autoInit -netlog
)
```
with `SteamAppId=107410`, `steamclient.so` symlinked into `~/.steam/sdk64`, and `xvfb-run` wrapping the launch. The README states the reason plainly: *"Proton/Arma needs a virtual display even for this headless server path; `xvfb` is installed and the start script uses `xvfb-run`."* They chose Proton because their extension is a Windows `.dll`; **we do not need this**, since the native Linux `arma3server` exists (`linux-server-steamcmd.md` §1) and `arma-rs` builds a Linux `.so`.

**Inbound control channel: a 40-line C extension that returns a file's contents.**

```c
__declspec(dllexport) void __stdcall RVExtension(char *output, int output_size, const char *function)
{
	handle = fopen(function, "rb");
	if (handle == NULL) return;
	read_count = fread(output, 1, (size_t)output_size - 1, handle);
	fclose(handle);
	output[read_count] = '\0';
}
```
Source: <https://raw.githubusercontent.com/JohnPeng47/mil-sim/main/scripts/duasbridge.c>

The harness writes SQF into `duas_commands.sqf`; the mission `callExtension`s the path and gets fresh content each time. This sidesteps Arma's aggressive `preprocessFile` caching. Crude, but it is a complete out-of-process command channel in forty lines — a useful fallback if our arma-rs RPC path ever needs a bootstrap.

**Outbound channel: JSONL over `diag_log`, with a documented truncation trap.** The README:

> Arma truncates long `diag_log` lines, so the mission emits one JSON frame header plus one JSON entity record per object instead of one oversized frame line.

`scripts/run_and_parse_state.py` waits for an RPT to appear (raising immediately if the server dies first), tails it, reassembles `DUAS_FRAME` / `DUAS_ENTITY` records, and validates a schema plus internal count consistency:

```python
def validate_frame(frame: dict) -> None:
    for key in ("schema", "time", "frame", "counts", "soldiers", "defenderDrones", "enemyDrones"):
        if key not in frame:
            raise ValueError(f"state frame missing {key!r}")
    ...
        if counts.get(key) != value:
            raise ValueError(f"count mismatch for {key}: counts={counts.get(key)} actual={value}")
```

**The genuine behavioural assertion is in `scripts/control_loop.py`** — this is the only closed-loop acceptance test found in the entire survey. Launch server → tail RPT → parse frames → detect an enemy inside a defender's field of view → write an intercept command → observe the commanded drone's speed change in a *later* frame → exit 0. If the effect never arrives, `raise TimeoutError("no intercept command effect observed")`.

```python
for defender in frame["defenderDrones"]:
    if defender["name"] != commanded_defender: continue
    if frame["frame"] > command_frame and speed(defender) > 1.0:
        print("verified defender={} trajectory changed at frame={} speed={:.2f}".format(...))
        return 0
```

Note the shape: the assertion is *"a later frame shows the effect"*, keyed on a monotonically increasing frame counter emitted by the mission, not on wall-clock sleeps. That is exactly the synchronisation discipline our contract demands.

**It also has a perceptual tier without a display.** `scripts/record_mp4.py` renders telemetry (plus a `DUAS_TERRAIN` / `DUAS_TERRAIN_ROW` elevation grid the mission exports once at startup) into an MP4. The video is reconstructed *from the state stream*, not screen-captured — a plausible model for a perceptual artefact on a headless WSL2 box.

### 1.3 HEMTT itself — an arma-rs extension driving a live Arma over TCP, using `-autotest`

**The build tool this project has already committed to (ADR-0005 stack, `arma-toolchain.md` §1) contains a complete live-Arma control harness.** It is undocumented — there is no `book/commands/photoshoot.md` — so it does not surface in any survey of HEMTT's documented commands. I found it only by listing `bin/src/commands/mod.rs`.

The pieces:

**A Rust `arma-rs` extension, `hemtt_comm_x64.dll`, built from `arma/` in the HEMTT repo:**

```rust
use arma_rs::{Context, ContextState, Extension, arma};

/// TCP port for communication between HEMTT and Arma 3
const HEMTT_TCP_PORT: u16 = 21337;

#[arma]
fn init() -> Extension {
    let ext = Extension::build()
        .command("mission", mission)
        .command("log", log)
        .group("photoshoot", photoshoot::group())
        .finish();
    ...
    std::thread::spawn(move || {
        let mut socket = loop {
            match TcpStream::connect(format!("127.0.0.1:{HEMTT_TCP_PORT}")) { ... }
        };
```
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/arma/src/lib.rs>

**An injected `@hemtt` mod**, embedded in the HEMTT binary via `rust_embed` (`#[folder = "dist/profile"]`) and unpacked into a scratch profile at run time. Its `preInit` function is two lines and establishes the game→harness identity:

```sqf
diag_log format ["setMission: %1", getMissionPath ""];
diag_log format ["response: %1", "hemtt_comm" callExtension ["mission", [getMissionPath ""]]];
```
Sources: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/arma/addons/main/functions/setMission.sqf>, `arma/addons/main/CfgFunctions.hpp` (`preInit = 1`)

**A generated BI `-autotest` config** — HEMTT writes `Users/hemtt/autotest.cfg` programmatically from a list of missions:

```rust
pub fn autotest(ctx: &Context, missions: &[(String, AutotestMission)]) -> Result<(), Error> {
    let mut autotest = File::create(ctx.profile().join("Users/hemtt/autotest.cfg"))?;
    autotest.write_all(b"class TestMissions {")?;
    for (name, file) in missions {
        autotest.write_all(format!(r#"class {} {{campaign = "";mission = "{}";}};"#, name, ...
```
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/bin/src/controller/profile.rs>

**So `-autotest` (§4.1) is not merely documented — HEMTT drives it in production.** That materially raises confidence that the parameter still works in the current engine.

**A length-prefixed JSON protocol, HEMTT as server.** `bin/src/controller/mod.rs` binds `127.0.0.1:21337`, waits for Arma to connect (warning at 120 s, no fixed sleep), then reads `u32` little-endian length + `serde_json` payload on a reader thread and dispatches to per-mission `Action` implementations:

```rust
let listener = TcpListener::bind(format!("127.0.0.1:{HEMTT_TCP_PORT}"))?;
listener.set_nonblocking(true)?;
info!("Waiting for Arma...");
...
if let fromarma::Message::Control(control) = message {
    match control {
        fromarma::Control::Mission(mission) => {
            if let Some((_, mission)) = mission.split_once("\\autotest\\") { current = Some(...) }
```

The message vocabulary (`libs/common/src/arma/control.rs`) is small and instructive:

```rust
pub mod toarma   { pub enum Message { Control(Control), Photoshoot(Photoshoot) }
                   pub enum Control { Exit } }
pub mod fromarma { pub enum Message { Control(Control), Photoshoot(Photoshoot), Log(Level, String) }
                   pub enum Control { Mission(String) }
                   pub enum Level { Trace, Debug, Info, Warn, Error } }
```

Three things to take from this design:

- **`fromarma::Message::Log(Level, String)` is a first-class structured log channel** — Arma's messages are re-emitted through HEMTT's own `tracing` logger at the right level. That is strictly better than RPT scraping: levels survive, there is no truncation, and no file tailing.
- **`toarma::Control::Exit` maps to `std::process::exit(0)` inside the game process** — the harness can terminate the engine cleanly and deterministically rather than killing a PID.
- **Mission identity is carried explicitly** (`Control::Mission`), so results are attributed to the autotest case that produced them. Nothing has to be inferred from interleaved log lines.

**The caveats are significant and must be stated.**

- The only consumer of `Controller` today is `hemtt photoshoot`, which is `#[cfg(windows)]`, prompts *"This feature is experimental, are you sure you want to continue?"*, is 64-bit-Windows-only, and requires `ImageToPAA` from Arma 3 Tools located via `HKCU\Software\Bohemia Interactive\ImageToPAA`.
- The controller's own exit detection is Windows-gated — `if cfg!(windows) { child.try_wait() … }` — so on Linux the run loop has no way to notice Arma has died.
- It launches the **client** through `commands::launch::launcher::Launcher`, which on Linux shells out to Steam (`-applaunch 107410`, plus a flatpak branch). It does not launch a dedicated server.
- The `controller` module is liberally marked `#![allow(clippy::unwrap_used)] // Experimental feature` and panics on malformed messages.

**Assessment.** This is not a testing framework and HEMTT does not present it as one — it is plumbing built to automate item screenshots. But it is *exactly* the plumbing we need, written in Rust against `arma-rs`, by the author of our build tool, and it proves the whole chain end to end: generate an autotest config → launch Arma with an injected addon and extension → the game dials home over TCP → structured bidirectional JSON → clean remote shutdown. Before writing our own bridge we should read `bin/src/controller/`, `arma/src/lib.rs` and `libs/common/src/arma/control.rs` in full, and consider whether the right move is to extend HEMTT's controller for a dedicated-server target upstream rather than build a parallel one.

---

## 2. Near misses: the design exists, the automation does not

### 2.1 `CySpiegel/ATLAS.OS` — our exact design, **never executed**

<https://github.com/CySpiegel/ATLAS.OS> — an AI-commander framework for Arma 3, SQF, 0 stars, last pushed 2026-03-20. Itself agent-authored (branches named `claude/atlas-os-architecture-design-…`).

`.github/workflows/integration-tests.yml` is textbook: `runs-on: [self-hosted, arma3]`, `hemtt dev`, symlink the mod into the server, copy `tests/integration.VR` into `mpmissions/`, launch

```bash
./arma3server_x64 \
  -autoInit -loadMission="$MISSION_NAME" -mod="@CBA_A3;@ATLAS_OS" \
  -config=server.cfg -profiles=testprofiles -name=testprofiles -nosound -world=empty \
  >> /tmp/arma3-test.log 2>&1 &
```

then poll the newest `.rpt` for the completion marker, grep `[ATLAS_TEST] PASS:` / `FAIL:` / `ERROR:`, write a job summary table, `exit 1` on failures, upload the RPT as an artifact, and clean up in `if: always()` steps.

**But: `gh api repos/CySpiegel/ATLAS.OS/actions/workflows/248165419/runs` returns `total_count: 0`.** It has never run once. And `tests/integration.VR/test_runner.sqf` has an empty test list:

```sqf
private _testFiles = [
    // "tests\integration.VR\test_example.sqf"
];
```

Its runner also contains three things our contract forbids or would flag: a bare `sleep 5` "wait for async tests to settle"; a `_passed`/`_failed` counter mutated from inside a `call`-scope closure, which will not accumulate as written; and a `try/catch` around `execVM`, which returns a script handle immediately and therefore cannot catch anything the test throws.

**Verdict: a well-shaped plan, unproven and subtly broken.** Useful as a shape to argue with, not as evidence that the shape works. Take the `-loadMission` + RPT-marker skeleton; do not take the runner.

### 2.2 `Savage-Game-Design/Across-the-Fence` — a real `just`-equivalent, no assertions

<https://github.com/Savage-Game-Design/Across-the-Fence> (default branch `development`), SQF, 11 stars, pushed 2026-06-18. A Python `click` CLI (`build/run.py`) with `launch client`, `launch server`, and a `dev` command that starts **both**:

```python
if not no_server: server_process = launch_arma_server(mod)
if not no_client: client_process = launch_arma(connect="127.0.0.1")
process_handler([server_process, client_process], polling_seconds=polling)
```

`build/vgm/arma.py` handles mission symlinking into `mpmissions/`, templating a server config (`arma_server.example.hpp`, `MISSION_NAME` substitution), Windows path validation, and mod-list construction. Its CI (`.github/workflows/build.yml`) only builds and packages.

**Relevance**: the closest published model for the `just accept` command surface — same problems solved (config templating, mission staging, joint server+client lifecycle, process supervision) — but there is nothing on the other end asserting anything. Read it for the plumbing.

### 2.3 `AdamWaldie/WaldosMissionPack` — good in-mission assertions, deliberately human-driven

<https://github.com/AdamWaldie/WaldosMissionPack>, SQF, 19 stars, pushed 2026-07-29 (active). Also agent-assisted — it ships a `CLAUDE.md`.

**Its in-mission assertion library is the best-designed of the *mission* frameworks**, and uniquely it tags every result with locality:

```sqf
Waldo_QA_fnc_emit = {
    params ["_kind", "_caseId", ["_detail", ""]];
    private _payload = str [_kind, _caseId, _detail, diag_tickTime, clientOwner, isServer, hasInterface];
    diag_log format ["WMP PR AUDIT %1: %2", _kind, _payload];
};

Waldo_QA_fnc_assert = {
    params ["_caseId", "_condition", ["_detail", ""]];
    private _kind = if (_condition) then {"PASS"} else {"FAIL"};
    [_kind, _caseId, _detail] call Waldo_QA_fnc_emit;
    private _results = +(missionNamespace getVariable ["Waldo_QA_LocalResults", []]);
    _results pushBack [_caseId, _condition, _detail];
    missionNamespace setVariable ["Waldo_QA_LocalResults", _results];
    _condition
};

Waldo_QA_fnc_case = {
    params ["_caseId", "_code"];
    ["CASE", _caseId, "BEGIN"] call Waldo_QA_fnc_emit;
    private _before = count (missionNamespace getVariable ["Waldo_QA_LocalResults", []]);
    call _code;
    private _afterResults = missionNamespace getVariable ["Waldo_QA_LocalResults", []];
    if (count _afterResults == _before) then {[_caseId, false, "CASE PRODUCED NO ASSERTION"] call Waldo_QA_fnc_assert;};
    ["CASE", _caseId, "END"] call Waldo_QA_fnc_emit;
};
```
Source: <https://raw.githubusercontent.com/AdamWaldie/WaldosMissionPack/main/releaseVerificationAndDeployment/fullArmaAudit/FullArmaAudit.VR/auditCommon.sqf>

Three ideas worth taking: the `clientOwner`/`isServer`/`hasInterface` tag on every emission (so a verdict is attributable to a node in a server+HC topology); the **vacuous-case guard** that fails a case which produced no assertions at all; and separate `runServerAudit.sqf` / `runClientAudit.sqf` suites.

**It also has a screenshot tier** — `capture_interaction_ui.ps1` uses Win32 `PrintWindow` against the live `arma3_x64` process, with per-monitor DPI awareness so a scaled desktop does not crop the capture. Windows-only, and it needs a real window.

**And it is the most interesting negative data point in this report.** Its CI (`.github/workflows/testing.yml`) is Python validators and `sqflint` only. Its in-engine tier is a documented *manual* process, and `fullArmaAudit/PROCESS.md` is explicit that the automated mode is not trusted:

> Manual mode is the release-review default. It loads the whole development pack but does not run the old state-mutating audit cases. `-Mode Automated` is opt-in and disposable. The generated Eden `WMP_FPA.VR` mission and its launchers remain experimental and **are not evidence** until that mission independently passes the hosted load gate.

> Static validation remains mandatory, but it cannot establish Arma locality, JIP, interaction rendering, mod integration or multiplayer rules.

The document also imposes a **closed-game staging rule** — never rebuild or restage while any Arma process is running, because Arma holds mission files open and a live refresh silently mixes cached and current scripts. That is a real hazard for a `just accept` loop that rebuilds between specs, and both launchers refuse to stage while Arma is running. We should adopt the same interlock.

---

## 3. In-mission SQF test frameworks: who has them, what runs them, what reports

The major mods do have real test suites. **None of them is invoked by anything other than a human typing into the debug console, and none produces a machine-readable verdict.**

| Project | Test files | Runner | Assertions | Verdict escapes as | Automated? |
|---|---|---|---|---|---|
| **Relicta ReSDK** | `Src/host/UnitTests/TestsCollection/` | `test_run` (`init.sqf`) | gtest-style `TEST`/`TEST_F`/`ASSERT_*`/`EXPECT_*` with fixtures | **process exit code via extension** | **Yes** |
| **ACE3** | `addons/*/dev/test_*.sqf` | `ace_common_fnc_runTests` | none — a test file **returns `true`** | `diag_log` text + `systemChat` | No |
| **CBA_A3** | 57 × `addons/*/test_*.sqf` | `CBA_fnc_test` → `execVM` per component | `TEST_TRUE`/`TEST_OP`/`TEST_DEFINED`, `ASSERT_*` | `diag_log` + error popup, **no accumulator** | No |
| **ALiVE** | 124 × `addons/*/tests/test_*.sqf` | per-addon `tests/test.sqf`, invoked by pasting a commented `//execVM …` line | CBA macros + `titleText` | `diag_log` + on-screen text | No |
| **ACRE2** | `addons/api/fnc_tests.sqf` | manual `call compile preprocessFile…` | local `ASSERT_BOOL`/`PASS`/`FAIL` macros | **`acre_api_testResults` array** in a global | No |
| **WMP** | `FullArmaAudit.VR/run*Audit.sqf` | staged audit mission, human plays it | `Waldo_QA_fnc_assert` + accumulator | `diag_log` marker, locality-tagged | No |
| **Antistasi** | 1 file, `fn_timeSpan_formatTests.sqf` | *"Not registered in CfgFunctions. Manually copy and paste."* | inline table-driven | returns `[BOOL, STRING]` | No |
| **code34 `oo_unittest`** | `oo_unittest.vr` | manual, OOP.h class | `OO_UNITTEST` class methods | `dump` to log | No |
| **KP Liberation / BECTI lineage / DUWS / DRO / Vandeanson's** | **none** | — | — | — | No |

Details and file paths worth having:

**ACE3** — `ace_common_fnc_runTests` is the best *discovery* design in the ecosystem: tests are registered declaratively in config, so any addon opts in by adding a class.

```sqf
} forEach (configProperties [configFile >> "ACE_Tests"]);
```
```cpp
class ACE_Tests {
    vehicleTransportInventory = QPATHTOF(dev\test_vehicleInventory.sqf);
    mapConfigs               = QPATHTOF(dev\test_mapConfigs.sqf);
    cfgPatches               = QPATHTOF(dev\test_cfgPatches.sqf);
    configCommands           = QPATHTOF(dev\test_configCommands.sqf);
};
```
Sources: <https://raw.githubusercontent.com/acemod/ACE3/master/addons/common/functions/fnc_runTests.sqf>, `addons/common/config.cpp`

The contract is one boolean per file (`_return isNotEqualTo true` ⇒ fail), and the content is **config integrity, not behaviour** — cfgPatches completeness, hitpoint configs, vehicle inventory tables. It needs the engine's config parser, not gameplay simulation.

**CBA_A3** — 57 test files reached from `addons/main/test.sqf` (itself generated by `tools/functions_config.rb`), entry point `CBA_fnc_test`. The macros are in `addons/main/script_macros_common.hpp` around lines 1494–1637:

```c
#define TEST_TRUE(CONDITION, MESSAGE) \
    if (CONDITION) then { TEST_SUCCESS('(CONDITION)'); } \
    else { TEST_FAIL('(CONDITION) ' + (MESSAGE)); }
```

**The design flaw is the one our harness must not repeat: there is no accumulator, no counter, no return value.** Every assertion independently calls `diag_log` (via `CBA_fnc_error`, which also does `cutRsc` to pop an error dialog). A human counts `Test FAIL` lines. Worse, `LOG`/`WARNING` compile to `/* disabled */` unless a `DEBUG_MODE_*` is defined — get that wrong and *passing* tests emit nothing, so silence is ambiguous. `addons/diagnostic/test_assertions.sqf` deliberately fails every assertion so a human can eyeball the framework's own output — the clearest possible proof that no machine consumes these results.

This corroborates `arma-toolchain.md` §2.4 from the other direction: the `TEST_*` family was never designed to carry a verdict out of the process, under SQF-VM or otherwise.

**ALiVE** is the most ambitious and the most decayed: 124 test files with genuine *behavioural* coverage (profile spawn/despawn, vehicle assignment, waypoints, persistence save/load, OPCOM objectives, map/cluster analysis, a stress test), a dead four-line `.travis.yml` on Python 3.4, and **no `.github/workflows/` at all** despite being pushed 2026-07-30. Its macros include a literal hand-stepped breakpoint:

```sqf
#define STAT1(msg) CONT = false; \
waitUntil{CONT}; \
diag_log ["TEST("+str player+": "+msg]; \
titleText [msg,"PLAIN"]
```

`waitUntil {CONT}` blocks until a human sets `CONT = true` in the debug console. Files prefixed `auto_` rather than `test_` run unattended, but still with `sleep 3` between phases. **Do not copy this pattern.**

**ACRE2** is the only mod that accumulates into a structured value — `acre_api_testResults` as `[[name, bool], …]` — which is one `diag_log`/`callExtension` away from being extractable. Its C++ extension unit tests (`extensions/src/ACRE2Arma/tests/`) exist but are not run by the Arma workflow.

**CTI specifically**: the entire BECTI lineage — `BennyBoy-/BECTI`, `zerty/Benny-Edition-CTI-0.97-Zerty-Modification` (44 stars, the liveliest), `RSpeekenbrink/ArmA-3-BECTI`, and assorted forks — contains **no test file, no assertion macro, no CI config, and no lint step**. There is no CTI testing prior art at all.

---

## 4. First-party Bohemia affordances

### 4.1 `-autotest` — an unattended mission runner with an exit code, that nobody uses

**This is the most significant first-party finding, and it is genuinely obscure.** From the current wiki (revision **2026-05-10**), `Arma 3: Startup Parameters`, section `autotest`:

> Loads automatically a series of defined missions and on error writes to a log file.
> The parameter can be used to automatically run a series of test missions. For example FPS measurement or scripting validation.
> * The game runs in special mode. It runs all missions from the given list.
> * If any mission fails (ends with other than END1), it is logged into the rpt file (search: `<autotest`).
> * **In case of any fail, the game also returns an errorlevel to DOS.** This can be used to issue an notification by a secondary application.
> …
> If possible use simple worlds, like VR, to keep the loading times short. The loading screen command might be useful as well to speed up task that need no rendering.

```cpp
class TestMissions
{
	class TestCase01
	{
		campaign = "";
		mission = "autotest\TestCase01.VR"; // relative path to the arma directory
	};
	class TestCase02
	{
		campaign = "";
		mission = "C:\arma3\autotest\TestCase02.VR"; // absolute path
	};
};
```

```html
<AutoTest result="FAILED">
	EndMode = LOSER
	Mission = autotest\TestCase01.VR
</AutoTest>
```

Invocation: `arma3_x64.exe -autotest=c:\arma3\autotest\autotest.cfg`. If `-profiles` is used, relative paths resolve against the profile path.

Source: <https://community.bistudio.com/wiki/Arma_3:_Startup_Parameters> — retrieved as wikitext via `https://community.bistudio.com/wikidata/api.php?action=query&prop=revisions&rvslots=main&rvprop=content|timestamp&format=json&titles=Arma_3:_Startup_Parameters` **with a browser User-Agent**; rev. 2026-05-10.

**Nobody uses it.** No repository surveyed here — ACE3, CBA, ALiVE, Antistasi, ZEN, KP Liberation, Achilles, ACRE2, Relicta, ATLAS.OS — contains the string `autotest`.

**Four caveats before treating this as a free win:**

1. It is documented against `arma3_x64.exe`, the **client**. `Arma 3: Dedicated Server` (rev. 2026-05-22) does not mention `autotest` at all. Whether `arma3server` honours it is untested and must be settled empirically.
2. Granularity is **one pass/fail per mission**, graded on end mode (`END1` = pass). Assertion-level detail still has to come from `diag_log` or an extension.
3. It requires the mission to actually end — so every test mission needs a deterministic `"END1" call BIS_fnc_endMission`-style terminator, and a hang produces no verdict, only an absent one.
4. "returns an errorlevel to DOS" is 2000s-era wording inherited from the OFP/Arma 2 lineage. Treat "there is an exit code" as claimed-by-Bohemia and unverified until we run it.

**It is not XML.** The brief's premise that `-autotest` takes an XML file is wrong: the input is class syntax, only the RPT *output* is XML-shaped. `Arma 2: Startup Parameters` carries a character-identical section differing only in the example paths, so the feature came forward from the Arma 2 lineage unchanged; there was never an `-autotest=file.xml`.

**It is maintained, and Bohemia has extended it.** First-party changelogs:

- *"Added: `isAutotest` script command"* — SPOTREP #00029, Update 1.24, 14 Jul 2014. <https://dev.arma3.com/post/spotrep-00029>
- *"Added: A text field for the name of the input file of Autotest"* (Launcher changelog) — SPOTREP #00034, Update 1.32, 14 Oct 2014. <https://dev.arma3.com/post/spotrep-00034>

`isAutotest` — *"Returns true if game was started with autotest parameter"*, `arma3 1.24`, group System — lets a mission branch on being under test, which is how a test mission decides to run assertions and end deterministically rather than idle. The retail Launcher still exposes the parameter in its Advanced Parameters UI. Sources: <https://community.bistudio.com/wiki/isAutotest>, <https://community.bistudio.com/wiki/Arma_3:_Launcher_-_Advanced_Parameters>

**Nobody in the mod ecosystem uses it.** No repository surveyed here — ACE3, CBA, ALiVE, Antistasi, ZEN, KP Liberation, Achilles, ACRE2, Relicta, ATLAS.OS — contains the string `autotest`. **HEMTT does** (§1.3), which is a much better precedent than none.

**Four caveats before treating this as a free win:**

1. It sits under *Developer Options* on the wiki and every example is `arma3_x64.exe`, the **client**. `-autoInit` and `-loadMissionToMemory` by contrast are explicitly under *Server Options*. `Arma 3: Dedicated Server` (rev. 2026-05-22) does not mention `autotest` at all. **Whether `arma3server` honours it is documented nowhere and must be settled empirically.**
2. Granularity is **one pass/fail per mission**, graded on end mode (`END1` = pass). Assertion-level detail still has to come from `diag_log` or an extension.
3. It requires the mission to actually end, so every test mission needs a deterministic terminator, and a hang produces no verdict — only an absent one.
4. "returns an errorlevel to DOS" is 2000s-era wording. Treat "there is an exit code" as claimed-by-Bohemia and unverified until we run it — on Linux especially.

**§5 goes deeper**: an undocumented sibling parameter `-autotestSingleMission=`, what binary inspection adds, the missing success value, and the one project using it in anger.

**And one trap that invalidates half the harness designs in this report on our target platform.** From <https://community.bistudio.com/wiki/arma.RPT>, verbatim:

> Linux server outputs the "RPT log" messages on stdout/stderr. Redirect stdout and stderr to a log file of your choosing.

**A native Linux `arma3server` writes no `.rpt` file.** Every RPT-tailing design here — ATLAS.OS's `ls -t "$RPT_DIR"/*.rpt`, Relicta's `psutil.Process(pid).open_files()`, mil-sim's `profile_dir.rglob("*.rpt")` — depends on a file that will not exist for us. mil-sim gets away with it precisely because it runs the *Windows* server under Proton. On our stack the equivalent is capturing the child's stdout, which is simpler, but it means `<AutoTest result=` and any `diag_log` marker protocol must be scanned on a pipe, not a file.

### 4.2 Other engine parameters relevant to a rig

All descriptions verbatim from <https://community.bistudio.com/wiki/Arma_3:_Startup_Parameters> unless noted.

| Parameter | Why it matters here |
|---|---|
| `-init=<cmd>` | *"Run scripting command once in the main menu."* e.g. `-init=playMission["","Test.VR"]`. Mission must live in `arma3\Missions`, not the user directory. A lighter second entry point for driving a **client** into a known state |
| `-autoInit` | *"Automatically initialize mission just like the first client does."* **Requires `persistent = 1;`** in server.cfg or it is skipped (also stated on `Arma 3: Dedicated Server`, rev. 2026-05-22). Warning on the page: *"This will break the Arma 3: Mission Parameters function"* |
| `-preprocDefine=NAME` | **Since 2.06.** Defines a preprocessor macro from the CLI, auto-prefixed `CMD__`. This is the *first-party* form of Relicta's `-d TEST_ALL` trick — compile a test-only build without a separate branch |
| `-doNothing` | *"Engine closes immediately after detecting this option"* — a zero-cost launch smoke test for `just check` |
| `-world=empty` | *"For faster game loading (no default world loaded…)"*. Used by ATLAS.OS and mil-sim |
| `-filePatching` | Needed for unpacked data. Relicta, Across-the-Fence and Relicta's `allowedFilePatching = 2;` all rely on it |
| `-checkSignatures` / `-checkSignaturesFull` | Signature verification with output to the RPT stream |
| `-noLogs` | **Avoid.** Suppresses RPT output — i.e. the verdict channel |
| `-noFreezeCheck` | Disables freeze-dump generation (max 4 per run). Leave *on*: freeze dumps are evidence for `node_crashed` |
| `-par=<file>` | Params from a file, but **does not support** `-cpuCount`, `-malloc`, `-exThreads`, `-maxMem`, `-profiles`, `-debug` |
| `-client` | *"Launch as client (console). Useful for headless clients"* |
| `-cfgDependenciesDebugPrint` | Since 2.20; prints addon load order to the RPT |
| `-dumpAddonDependencyGraph` | Dumps a Graphviz file of all `requiredAddons` |

**There is no `-benchmark` in Arma 3.** It exists only in ArmA 1, documented there as *"Intended for automated benchmarking, but was never finished and is not working."*

### 4.3 Out-of-process control channels the engine already offers

| Channel | Verdict |
|---|---|
| **Named pipe, `-command=<name>`** | Real but unusable for us. <https://community.bistudio.com/wiki/Arma_3:_Named_Pipe> — *"Arma 3 has a fully working implementation of named pipe which allows developers to pass several predefined commands to Arma process… **Works for client and hosting client. Doesn't work for dedicated server.**"* Windows `CreateNamedPipe`, duplex, one instance. Commands: `shutdown`, `message`, `reply`, `session` (returns JSON with playerId/hosting/island/mission/host/hostIP), `connect <JSON>`. Windows-only by construction and explicitly not on dedicated server |
| **`serverCommand` from SQF** | Usable, and stronger than expected. <https://community.bistudio.com/wiki/serverCommand> — the `serverCommandPassword` variant needs no admin login, and per `serverCommandAvailable`: *"The table above does not apply to the command's password variant on a dedicated server as everything is available to it."* This is how Relicta shuts its box down (`rbuilder_password serverCommand "#shutdown";`) |
| **BattlEye RCON** | `Multiplayer Server Commands` opens *"It is recommended to use BattlEye's RCon tool to administrate the server"* and notes RCON *"cannot be affected by in-game script exploits"*. Configured by `RConPassword` in `beserver.cfg`; `RConPort` must avoid 2302-2306. Reaches `#shutdown`, `#restart`, `#missions`, `#mission`, `#init`, `#monitor`, `#userlist`, `#captureframe`, `#captureslowframe`, `#debug checkFile <PBO>`. **Lifecycle control, not a verdict channel** — no RCON command returns a script result |

### 4.4 SQF-side verdict and diagnostic primitives

| Command | Verdict-usable? |
|---|---|
| `endMission "END1"` / `failMission` | **Yes — this *is* the `-autotest` verdict channel.** End types CONTINUE, KILLED, LOSER, END1–END6. `endMission` deletes mission saves; `failMission` does not |
| `forceEnd` | Adjunct — *"Forces mission ending (set with `endMission`) even if a camera effect or any another condition delays the endMission"* |
| `BIS_fnc_endMissionServer` | Ends properly for all players in MP. Noted as *"somewhat deprecated for custom endings since 1.50"* in favour of `["MyEnding", true, 3] remoteExec ["BIS_fnc_endMission", 0, true];` |
| `diag_log` | Yes, for evidence. *"Dumps the argument's value to the report file. Each call creates a new line."* `[SECONDARY]` a long-standing user note on that page puts the per-line limit at 1044 characters — consistent with mil-sim's independently-discovered truncation and its one-record-per-entity workaround |
| `assert` | **No. Do not build on it.** *"Tests a condition and if the condition is false, displays error on screen (if -showscripterrors enabled) and logs error into .rpt file. **It does not interrupt the script execution.**"* |
| `diag_activeSQFScripts` | Introspection only — returns `[scriptName, fileName, isRunning, currentLine]`. Useful for diagnosing a hang |
| `diag_codePerformance` | Micro-benchmark. *"For security purposes, this command will only run for 1 cycle in multiplayer"* unless the debug console is enabled in `description.ext`/Eden — so MP timings are near-useless by default |
| `diag_captureSlowFrame` | **The most interesting one for a server+HC rig.** Since 2.20 it takes `toFile` and `continuousCounter` and accepts string thresholds (`"33ms"`, `"30fps"`). Scopes include **`sLoop` (dedicated server)** and **`cLoop` (headless client)**, and it emits a `.trace` importable into `chrome://tracing` / Perfetto. A machine-readable performance artefact per node, with no UI |
| `diag_logSlowFrame` | **Not usable — *"This command is not implemented in Arma 3 builds."*** Use `diag_captureSlowFrame` with `toFile` |
| `diag_captureFrame` | *"This can also be executed on a dedicated Server and because a Server has no UI it will behave like `diag_captureFrameToFile`"* |

### 4.5 The Diagnostics exe is disqualified

<https://community.bistudio.com/wiki/Arma_3:_Diagnostics_Exe> (`arma3diag_x64.exe`, Dev branch) offers live overlays (`diag_toggle "Animation"`, AI aiming/brain/skill/suppression/driving, dynamic simulation, PhysX, hitpoints, particles) and `diag_mergeConfigFile` for live config reload. But, verbatim:

> **This exe has multiplayer disabled on purpose. There is no way to use this executable in multiplayer as this functionality has been removed completely.**

That rules it out of any server + headless-client acceptance rig. Also note `diag_testScriptSimpleVM` (2.16, diag/prof branches) sounds like a test runner and is not — it is a compiler validator returning `["Success", 360, "<bytecode disassembly>"]`.

### 4.6 There is no Bohemia SQF test framework, and Bohemia never built one for this engine

Full-text wiki search (`srwhat=text`, which is required — the default returns 0 hits): `autotest` → 4 hits, all the same feature; `automated testing` → 4, all false positives; `unit test` → 62, every one of them "unit" in the *game unit* sense; `test framework` → 8, all false positives. **There is no `Arma 3: Unit Testing` or `Arma 3: Automated Testing` page.**

Bohemia's own dev blog is the more interesting evidence. Across **all 479 posts** on dev.arma3.com (SITREP #001–#00242, SPOTREP #00001–#00119, 57 TECHREPs, 60 OPREPs), the terms `regression`, `continuous integration`, `nightly build`, `build verification`, `test farm`, `unit test`, `test suite`, `test harness`, `jenkins`, `teamcity` and `test automation` occur **zero times**. `auto-testing` occurs twice.

What they do say:

> Arma 3 is currently being tested by five full-time embedded specialists. They are supported by a team of varying size (around 30 - 40) in our Prague office… **There is also the automated aspect, which we're expanding in 2015, with elaborate auto-testing of almost everything.**
> — SITREP #00088, Joris-Jan van 't Land, 6 Jan 2015. <https://dev.arma3.com/post/sitrep-00088>

> to illustrate, the '**build checklist**' assembled by our Quality Assurance heroes, which we run through before every update, **takes approximately three weeks**
> — SITREP #00179, 25 Oct 2016. <https://dev.arma3.com/post/sitrep-00179>

> **This daily experimental build undergoes little in-house testing before it is published.**
> — <https://dev.arma3.com/dev-branch>

The 2016 performance-optimisation OPREP for 2.20 benchmarks using the **community's** YAAB rather than an internal suite. The one automated-benchmark citation is SITREP #00162: *"our own automated benchmarks have not shown a significant hit"*. The AI path-following writeup describes ~30 test cases that *"all of them had to be retested after most iterations"* — by hand.

**Read this plainly: Bohemia's automation investment went to the new engine, not this one.** Their current careers page advertises a QA Automation Engineer whose duties are *"Creating and maintaining of auto-tests (using Enforce Script)"* — Arma 4 / Enfusion. <https://careers.bohemia.net/en/open-positions/qa-automation-engineer-mobnycri>

### 4.7 Arma 3 Tools contains no test tooling

39 components (Object Builder, Terrain Builder/Processor, Buldozer, FSM Editor, TexView 2, Binarize, Addon Builder, FileBank, BankRev, CfgConvert, BinMake, ImageToPAA, sound tools, DSCreateKey/DSSignFile/DSCheckSignatures/DSUtils, Publisher, Launcher, Game Updater, Work Drive, ModHashCalculator, Render Worlds, Tools Launcher, Tools Diag, Diagnostics Exe, Analytics, Asset Samples). Windows-only. **No test runner, no assertion library, no linter.**

The one genuine validator is **DSCheckSignatures** — *"verify your signatures match your pbo files… it emulates the signature verification done on the server"* — worth wiring into a pre-publish gate, but not a test framework. Binarize/Addon Builder/CfgConvert fail on malformed input, which is a de-facto "does it compile" check and a side effect of packing.

Note also that `arma-actions/arma3-tools` requires you to supply your own hosted ZIP (`toolsUrl` is a required input) rather than fetching from Steam — Arma 3 Tools cannot be obtained anonymously in CI. Source: <https://raw.githubusercontent.com/arma-actions/arma3-tools/master/action.yml>

### 4.8 Arma Reforger has exactly what we want — and **none of it transfers**

Reforger 1.6.0 shipped a first-party **Autotest Framework**: test groups/suites/cases, `[Test(suite: "...", timeoutS: 5)]` and `[Step(EStage.Setup)]` attributes, an async model where **void steps run once and bool steps poll until true** (no sleeps), `AssertTrue`/`SetResultFailure`, per-suite `GetWorldFile()`, a CLI runner (`-autotest "{6AB9C8EE…}"` / `-autotest MySuite` / `-autotest MySuite_Case`), and **JUnit XML output** via `SCR_AutotestReport::WriteJUnitXML()` to `$logs:/junit.xml` plus `$logs:/autotest_failed.log`. Source: <https://community.bistudio.com/wiki/Arma_Reforger:Autotest_Framework>

**This does not transfer to Arma 3.** Different engine (Enfusion vs Real Virtuality 4), different language (Enforce Script vs SQF). SQF has no classes and **no attribute/annotation syntax at all**, so `[Test(...)]`/`[Step(...)]` have no expressible analogue; there is no Workbench for Arma 3 and no plugin host; there is no binary, script or config path by which Arma 3 could load `SCR_AutotestCaseBase`. Bohemia publishes migration pages precisely because the break is total (`Arma Reforger:From SQF to Enforce Script`). This corroborates `arma-toolchain.md` §5.3's "Reforger is irrelevant" line for the testing question as well as the build question.

Two caveats even inside Reforger: `SCR_TestLib` — the spawn/input/teardown helper the wiki's headline example depends on — is *"not accessible in game code at the moment"*, and every documented invocation is Windows Workbench with Linux `-autotest` undocumented.

**What does transfer is the shape**: a process launched with a CLI argument, running a declared list of scenario tests against a loaded world, exiting with a machine-readable artefact. Arma 3's `-autotest` is a much coarser version of that same shape, and it is the only first-party thing in that shape we get. Reforger's **step model is worth copying** in SQF: a step is either a one-shot `void` or a `bool` that is polled until true — that is a sleep-free async primitive we can express with a scheduler adapter.

### 4.9 BattlEye, signatures and file patching in an automated rig

- **Headless clients bypass signature verification entirely.** `Arma 3: Headless Client`, verbatim: *"Headless Clients are excluded from signature verification, therefore any mod can be used with the `-mod=` option."* That removes the main signing obstacle from an HC-driven rig.
- **But `-serverMod=` does not work alongside `-client`** (same page) — a real constraint on how our shim gets loaded onto an HC.
- HCs must be whitelisted by IP: `headlessClients[] = {"127.0.0.1"};`, plus `localClient[] = {"127.0.0.1"};` for unlimited-bandwidth/no-latency treatment.
- Both hostile switches are config-level and can simply be off for a local rig: `BattlEye = 0;` and `verifySignatures = 0;`. Every live-Arma harness in this report does exactly this (Relicta's `init.cfg`, Across-the-Fence's `arma_server.example.hpp`, WMP's *"BattlEye must always remain disabled for generated QA missions"*).
- `allowedFilePatching`: 0 no clients / **1 headless clients only** / 2 all. Value 1 is the natural setting for a rig that wants unpacked SQF on the HC but not a general file-patching hole.
- `persistent = 1;` is mandatory for `-autoInit`.
- No first-party statement exists on BattlEye's interaction with `-autotest`; treat as unverified and keep `BattlEye = 0` on the rig.

---

## 5. `-autotest` in depth — the one Bohemia-supplied pass/fail oracle

Escalated for its own treatment because it is the only first-party mechanism that produces a machine-readable verdict, and because parts of it are **undocumented**. §4.1 covers the documented surface; this section adds what binary inspection establishes, what the documentation does *not* say, and the one project found using it in anger.

### 5.1 Evidence from binary inspection — clearly marked as inference

The following comes from string extraction against the shipped 2.20.152984 binaries, **not from documentation**, and was performed by the calling session rather than by me. I have not re-run it, so it is reported as their result.

Both `-autotest=` and **`-autotestSingleMission=`** are present as string constants in the Windows client `arma3_x64.exe` **and in the Linux dedicated server `arma3server_x64`**. Error strings recovered:

```
Error: Cannot open AutoTest config file %s
Error: AutoTest config file %s does not contain TestMissions class
Error: TestMissions class of AutoTest config file %s has no subclasses.
```

Result block format strings:

```
<AutoTest result="FAILED">
 EndMode = %s
 Campaign = %s
 Mission = %s
</AutoTest>

<Autotest result="FAILED">
  Unable to start this mission (maybe it does not exist).
</Autotest>
```

**What this corroborates.** The `TestMissions`-class-with-subclasses config shape and the `campaign` / `mission` key pair match the wiki example exactly, across a page last edited 2026-05-10 and an engine build from the same era. That is strong mutual confirmation for a feature that is otherwise sparsely documented.

**What it adds beyond the documentation.**

1. **`-autotestSingleMission=` is entirely undocumented.** It appears on **zero** BI wiki pages — full-text search with `srwhat=text` returns `totalhits: 0` — and produces **zero** hits on GitHub code search and web search. Its existence is established by binary inspection alone. Its argument form, semantics and relationship to `-autotest` are unknown. The name strongly implies "run exactly one mission rather than a config-driven list", which would make it the natural fit for a `just accept <spec-id>` single-spec invocation, but **that is inference from a symbol name and nothing more.**
2. **The binary emits a `Campaign = %s` line that the documented RPT example omits.** Both the Arma 3 and Arma 2 wiki examples show only `EndMode` and `Mission`. Any parser must tolerate the third field.
3. **A second, distinct failure mode exists**: `Unable to start this mission (maybe it does not exist)`, emitted under a differently-cased `<Autotest>` tag rather than `<AutoTest>`. **A case-sensitive grep for `<AutoTest` will silently miss the "mission not found" failure** — which is exactly the failure a misconfigured harness produces first. Match case-insensitively.
4. **The strings being present in `arma3server_x64` does not mean the facility is wired into dedicated-server mode.** The calling session ran `./arma3server_x64 -autotest=/tmp/autotest.cfg -world=empty -noSound` on the Linux dedicated server and reports that it **ignored the parameter and booted as a normal dedicated server**. Shared string tables across binaries are unremarkable — the server and client are built from one codebase. Read this as "not wired into `-server` mode", not as "the facility is broken".

### 5.2 What the documentation does not say

Answering the specific questions, honestly, including where the answer is "nowhere":

| Question | Answer | Confidence |
|---|---|---|
| Exact config syntax | `class TestMissions { class <CaseName> { campaign = "…"; mission = "…"; }; };` | **High** — identical on the Arma 3 and Arma 2 pages, corroborated by binary error strings |
| Full set of accepted keys | **Only `campaign` and `mission` are documented anywhere.** The binary's `EndMode`/`Campaign`/`Mission` output triple implies no others are consumed | **Medium** — absence of evidence; no key list is published |
| Where the result is written | The RPT stream — *"it is logged into the rpt file (search: `<autotest`)"*. **On a native Linux server there is no `.rpt` file** (§4.1); it goes to stdout/stderr | **High** |
| Meaning of `result="FAILED"` | *"If any mission fails (ends with other than `END1`), it is logged"* — so `END1` is pass and everything else (`LOSER`, `KILLED`, `END2`–`END6`, `CONTINUE`) is failure | **High** |
| The success value | **There does not appear to be one.** No `result="OK"`/`"PASSED"` string is documented, and none was recovered from the binaries. The wording says failures *are logged*, implying passes are not | **Medium, and this is the dangerous part** |
| Multiplayer, or singleplayer/campaign only? | **Effectively singleplayer/campaign.** See below | **Medium-high** |
| Anyone using it | Exactly one project found (§5.3), plus HEMTT (§1.3) | **High** |

**The missing success value is the most important finding in this section.** If only failures are logged, then "pass" is signalled by the *absence* of a marker — and absence is indistinguishable from "the mission never loaded", "the engine hung", or "the harness pointed at the wrong path". That is precisely the ambiguity our contract forbids: it collapses `assertion_failed`, `timeout` and `infra_unavailable` into one silent state. The exit code partially rescues this, but it too is only documented as being set *on failure*.

**Mitigation, and it is not optional: do not rely on `-autotest`'s silence.** Have each test mission emit its own positive completion marker (`diag_log` or extension callback) before calling `endMission "END1"`, and treat a run with no completion marker as `timeout`/`infra_unavailable` regardless of exit code. This is the same lesson `arma-toolchain.md` §2.4 drew about SQF-VM exiting 0 on runtime errors — assert on a positive marker, never on the absence of a negative one.

**On multiplayer.** Four independent signals point to singleplayer/campaign sequencing:

- The config keys are `campaign` and `mission`, and the emitted block reports `Campaign` — a singleplayer/campaign concept with no dedicated-server analogue.
- The verdict is the mission *end type* (`END1`), which is a singleplayer mission-outcome concept; MP missions on a persistent server typically never end at all.
- Every documented invocation is `arma3_x64.exe`, the client, and the parameter sits under *Developer Options*; `Arma 3: Dedicated Server` never mentions it.
- The one real user (§5.3) drives the **client** binary in windowed mode.
- And empirically, the Linux dedicated server ignored it (§5.1).

**So for us `-autotest` is an additional tier, not a replacement for the server+HC tier.** It could carry a fast singleplayer logic-and-rendering tier — VR-terrain missions exercising pure-logic units with a real engine and real config parsing, faster and simpler than bringing up a server — but it cannot orchestrate a dedicated server with headless clients, which is where CTI locality, JIP and ownership behaviour actually live. `-autotestSingleMission` might change that picture; nothing published says either way.

### 5.3 Someone does use it in anger: `jokoho48/ArmaWatchdogs`

<https://github.com/jokoho48/ArmaWatchdogs> — Node.js + Vue, 2 stars, created 2020-01-14, last pushed 2023-03-15, no licence. Small and unpolished, but it is a **complete, readable, `-autotest`-driven visual regression harness**, and the only real-world autotest config found on GitHub.

The config (`testConfig.cfg`) is exactly the documented shape:

```cpp
class TestMissions
{
    class TestCase01
    {
        campaign = "";
        mission = "autotest\mission\TestCase01.VR";
    };
};
```

The harness (`index.js`) spawns Arma with the parameter appended and captures stdout, stderr **and the exit code**:

```js
let parameters = process.env.ARMA_STARTUP_PARAMETERS.split(';');
parameters.push("-autotest=" + process.env.ARMA_AUTOTESTCONFIG);

const arma = spawn(process.env.ARMA_PATH, parameters);
arma.stdout.on('data', (data) => { console.log(`stdout: ${data}`); });
arma.stderr.on('data', (data) => { console.error(`stderr: ${data}`); });
arma.on('close', (code) => { ... });
```

On close it compresses today's screenshots, globs them, and image-diffs each against yesterday's run into a `diff/` directory, with a configurable `DIFF_THRESHOLD`. A Vue frontend browses the gallery.

The test mission's `init.sqf` is the other half, and it is the clearest published example of what an autotest mission looks like:

```sqf
diag_log format ["Test Mission"];
hideObject player;
JK_TestData = [];
...
0 spawn {
	private _cam = "camera" camCreate [0,0,0];
	_cam cameraEffect ["internal", "back"];
	_cam camSetFocus [-1,-1];
	_cam camCommit 0;
	{
		_x params ["_pos", "_aimPos", "_name", "_elevation"];
		...
		_cam camSetPos _p;
		_cam camSetDir (_p vectorFromTo (_aimPos call JK_fnc_getPos));
		_cam camCommit 0;
		waitUntil {preloadCamera _p;};
		sleep 1;
		screenshot (_name + ".png");
	} forEach JK_TestData;
	camDestroy _cam;
	endMission "END1";
};
```

Five things to take from it:

- **`endMission "END1"` is the pass signal, written by hand at the end of the mission.** This is the documented contract being honoured in practice.
- **`waitUntil {preloadCamera _p;}`** is the right synchronisation primitive for "the world is actually rendered here" — a condition, not a sleep. (The trailing `sleep 1` is the part not to copy.)
- It runs `arma3profiling_x64.exe` — the **profiling client**, in `-window` mode. Screenshots need a window, so this is a Windows-desktop tier by construction.
- The README carries a hard-won operational warning: ***"!!Importent that this Path is without Spaces else arma does not detect the file !!"*** — the `-autotest=` path must contain no spaces. Worth knowing before losing an afternoon.
- Its whole verdict model is *external* — the engine's pass/fail is barely used; the real assertion is an image diff performed after the process exits. That is a tacit admission of the same gap identified in §5.2.

`CMB:SimplifyTesting` on the wiki, which surfaces on searches for Arma testing, is unrelated — it is a page of manual-testing ergonomics tips (`-window`, `-x`/`-y`, `-noPause`, `-noSplash`) with no automation content.

---

## 6. Headless client as a test driver — nobody does it, and here is what it would buy

**Nobody uses a headless client as a synthetic player in an automated rig.** Every HC result found across GitHub repository search, the web, BI forums and Reddit is AI offload. `10Dozen/ArmaTesqf`, whose description reads "Arma 3 SQF testing framework", is an **empty repository containing only a LICENSE**. The closest anything comes is `ArmaForces/Mods`, which keeps a `.hemtt/missions/test.Stratis` for manual `hemtt launch`.

**What an HC actually gives you over a dedicated server** — the load-bearing question for our blocker. From `Arma 3: Headless Client` and `Multiplayer Scripting`:

| | Dedicated server | Headless client |
|---|---|---|
| `isServer` | true | **false** |
| `hasInterface` | false | **false** |
| `player` | `isNull player` | **returns the HC entity** |
| In `allPlayers` / `isPlayer` | no | **yes** |
| `initPlayerLocal.sqf` | not run | **runs** |
| `initPlayerServer.sqf` | — | **triggers it** |
| `clientOwner` / `remoteExec` target | id 2 | **distinct id ≥ 3** |
| Own log stream | yes | **yes, separate** |

The canonical identity check is `!hasInterface && !isServer`.

**The constraint that decides the design: `hasInterface` is `false` on a headless client.** So an HC buys real *player locality* — a non-null `player`, membership in `allPlayers`, genuine client→server and server→client `remoteExec`/`publicVariable`/JIP paths, and client-side init execution — and buys **nothing at all** on the interface. Every `ctrl*`, `displayCtrl`, `findDisplay`, `cutText` and `hint` render path stays untested, and any code guarded by `if (hasInterface)` **will not execute on an HC**.

**Read that as a scoping decision, not a disappointment.** An HC is a locality driver, not an interface driver. It can carry the whole of a CTI command-and-control acceptance suite — ownership transfer, order dispatch, JIP resync, side-scoped visibility — and none of a UI checklist. Anything perceptual must be budgeted separately, and on our stack that means either mil-sim's telemetry-rendered artefact (§1.2) or WMP's Win32 window capture on a Windows box (§2.3).

**Practical constraints on an HC in a rig** (see also §4.9): HCs are excluded from signature verification so any mod loads with `-mod=`; **`-serverMod=` does not work alongside `-client`**; HCs must be IP-whitelisted via `headlessClients[]` (plus `localClient[]` for unlimited bandwidth); `allowedFilePatching = 1` grants file patching to headless clients only; and on Linux the HC is *the same `arma3server` binary*, so no Wine and no X server are involved.

---

## 7. Out-of-process channels into a live game, ranked

Collecting every mechanism found, with an honest verdict on each as a **driver** (can it make the game do something?) and as an **oracle** (can it tell us what happened?).

| Mechanism | Driver | Oracle | Platform | Notes |
|---|---|---|---|---|
| **`diag_log` → stdout** | no | **yes** | Linux native | `arma.RPT`: *"Linux server outputs the 'RPT log' messages on stdout/stderr."* Zero moving parts, one stream **per node** (server and each HC are separate processes). `[SECONDARY]` ~1044-char line limit; never ship `-noLogs` |
| **arma-rs extension + callback** | **yes** | **yes** | both | Our chosen path. `ctx.callback_data(...)` surfaces in SQF via the **`ExtensionCallback` mission event handler** (Arma 3 v1.96), `params ["_name","_function","_data"]` |
| **HEMTT's controller (arma-rs + TCP JSON)** | **yes** | **yes** | Windows in practice | §1.3. Existing, working, same crate, same author as our build tool |
| **Relicta's extension + TCP** | **yes** | **yes** | Windows | §1.1. Adds an interactive SQF REPL |
| **`-autotest`** | **yes** | **coarse** | client documented; server unverified | §4.1. Mission-granularity pass/fail + exit code |
| **BattlEye RCON** | **yes** | **no** | both | See below |
| **`serverCommand` + `serverCommandPassword`** | **yes** (from inside SQF) | no | both | §4.3. Full command set on a dedicated server without an admin login |
| **Named pipe `-command=`** | yes | partial (`session` returns JSON) | **Windows client only** | §4.3. *"Doesn't work for dedicated server"* |
| **ArmaDebugEngine (WebSocket)** | **yes — arbitrary SQF** | **yes** | **Windows only** | See below |
| **A file the extension reads (`duasbridge`)** | **yes** | no | both | §1.2. 40 lines of C; a viable bootstrap |

### 7.1 `arma-rs` has no live-in-game testing story — and it is Linux-first

`arma-rs/src/testing.rs` wraps an `Extension` and calls its dispatch table directly inside a Rust unit test (`extension.call(...)`, `callback_handler(..., Duration)`); `arma-rs/tests/emulate.rs` drives the raw C ABI (`handle_call` with `*mut i8`, `register_callback`). Both are **out-of-process with no Arma involved**, and CI is `cargo nextest run` on ubuntu/macos/windows. This corroborates `arma-rs.md` §4 and closes the question: the crate mocks the engine, it never talks to one.

**One correction to `arma-rs.md`'s framing.** arma-rs is Linux-first, not Windows-first: in `arma-rs-proc/src/lib.rs` the calling convention is unconditionally `extern "system"`, and the only platform special-case is `#[cfg(all(target_os = "windows", target_arch = "x86"))]` for stdcall name mangling. Native `.so` is the default path, which is good news for the WSL2 tier.

`overfl0/Pythia` (86 stars) is the ecosystem's best answer to testing an extension without Arma: it ships **`PythiaTester`**, a standalone executable that speaks the extension ABI and stands in for the game, driven from `tests/tests.py` under `unittest`. KillzoneKid's `callExtension.exe` is the same idea, Windows-only, binaries without source. If our shim needs a fake host beyond what `extension.testing()` gives, `PythiaTester` is the model.

### 7.2 ArmaDebugEngine — a full SQF eval-and-return channel, Windows-only

<https://github.com/dedmen/ArmaDebugEngine> — *"A still experimental Script Debugger for Arma 3"*, C++, 49 stars, last pushed 2025-02-01. It hooks the live Arma process and runs a **WebSocket server inside it** (`BIDebugEngine/BIDebugEngine/WebSocketServer.cpp`, websocketpp + asio), speaking JSON. The command vocabulary (`NetworkController.h`):

```cpp
enum class NC_CommandType {
    invalid, getVersionInfo, addBreakpoint, delBreakpoint, BPContinue, MonitorDump,
    setHookEnable, getVariable, getCurrentCode, getAllScriptCommands, getAvailableVariables,
    haltNow, ExecuteCode, LoadFile, clearAllBreakpoints, clearFileBreakpoints,
    SetExceptionFilter = 16, FetchAllFunctionsInNamespace = 17, FetchInstructionRef = 18
};
enum class NC_OutgoingCommandType {
    invalid, versionInfo, halt_breakpoint, halt_step, halt_error, halt_scriptAssert,
    halt_scriptHalt, halt_placeholder, ContinueExecution, VariableReturn,
    AvailableVariablesReturn, BreakpointLog, LogMessage, ExecuteCodeResult, ...
};
```

`ExecuteCode` compiles and runs arbitrary SQF and returns the serialised result as `ExecuteCodeResult` — **and it does not require the debugger to be halted first**, per the source's own comment:

```cpp
case NC_CommandType::ExecuteCode: {
    //I don't verify that debugger is halted... please be nice.
```

Note also `halt_error` and `halt_scriptAssert` in the outgoing set: **script errors and failed `assert`s are pushed out of the process over the socket**. That is precisely the oracle `assert` cannot be on its own (§4.4), and it is the only mechanism found anywhere that converts an Arma script error into a structured external event rather than a log line.

**Two hard caveats.** It is **Windows-only** by construction — `.sln`/`.vcxproj`, `DllMain`, `Psapi.lib`, and hand-written MASM hooks (`EngineHookfncx86.asm`, `EngineHookfncx64.asm`). And it hooks engine internals, so it is inherently brittle across Arma builds — exactly the `engine_drift` exposure we are trying to reduce.

**But it is an Intercept client** (`#include <intercept.hpp>`, `intercept::client::invoker_lock`), and <https://github.com/intercept/intercept> (MIT, 243 stars, pushed 2025-08-08) **does build for Linux** — its CI has an `extension-linux` job on `ubuntu-20.04` producing `build-linux64/src/host/intercept_dll/intercept_x64.so`. So "Intercept + a network server = out-of-process control of a live Arma" is a proven pattern with a Linux-capable substrate. Intercept itself ships no testing story and its CI boots nothing.

### 7.3 RCON is a good driver and a bad oracle

The BattlEye RCON protocol (<https://www.battleye.com/downloads/BERConProtocol.txt>) has three packet types: login `0x00`, command `0x01` (request/response, 45 s keepalive mandatory), and **`0x02`, an unsolicited server-message push channel** — *"When the BE Server prints messages to the server console, it also sends them to all connected RCon clients."*

**As a driver it is genuinely useful**: `#mission <name>`, `#missions`, `#restart`, `#reassign`, `#init`, `#lock`/`#unlock`, `#shutdown` all pass through, and BE-native `players` gives a readiness signal that parses a `(Lobby)` state — so you can detect an HC finishing its join without polling the game port.

**As an oracle it is a dead end.** `#exec` drives a deliberately crippled server-administration VM with no `player`, no `allUnits`, no `spawn`/`execVM`. And SQF cannot write *into* the RCON stream: `systemChat`/`globalChat` are local-effect and therefore no-ops on a headless server, while `remoteExec ["systemChat", 0]` makes *clients* print locally — it never sends chat to the server, which is what BattlEye observes. `berconpy`'s `src/berconpy/ext/arma/parser.py` enumerates the complete `0x02` message space: player chat, connect/disconnect, GUID, kick, and RCON-admin echo. Nothing SQF-originated.

One untested path worth a short spike: Arma 3 **2.18** added `callExtension`, `missionNamespace` and `getVariable`/`setVariable` to the server-side admin VM, and `diag_log` was already there. If `#exec` is accepted over the RCON socket, RCON becomes both driver and oracle. No source settles this either way, and Bohemia has previously disabled the analogous `#beserver` pass-through — treat as **unverified**.

Best libraries if we go this way: **`berconpy`** (async Python, typed, sans-io core, exposes the `0x02` event stream, and already uses uv/ruff/ty/pytest — the same stack as our daemon) and `WoozyMasta/bercon-cli` (Go, `--format=json`, convenient from a `just` recipe).

`extDB3` is disqualified regardless of merit: **its extension source is closed** by its own licence.

---

## 8. Containers, Steam credentials and engine pinning

**The container layer is a solved commodity and the verdict layer is greenfield.** Seven container projects were read; none boots Arma in CI.

| Project | Steam credential handling | Headless clients | CI boots a server? |
|---|---|---|---|
| **BrettMayson/Arma3Server** (138★, branch `v2`) | **No SteamCMD** — talks to the Steam CDN through a fork of ValvePython/steam. `api.login(user, pass)` passes **neither** `auth_code` nor `two_factor_code`; README requires Steam Guard **disabled** | Yes — `HEADLESS_CLIENTS`, auto-injects `headlessclients[]`/`localclient[]`. **But HCs are `Popen`'d before the server starts: no readiness gate, no supervision, no exit-code propagation** | No — image build + lint |
| **Pelican/Pterodactyl egg** (`pelican-eggs/games-steamcmd`) | Hard-fails on anonymous; **classifies SteamCMD output into soft/hard/fatal** and exits 1 on `Invalid Password\|two-factor\|No subscription` | Yes, up to 5 via a `-par` file | No |
| **fbuchmeier/arma3-helm-chart** | inherits BrettMayson | Yes — distributed HC pods | No (helm template snapshots) |
| **LinuxGSM** | arma3 default `steamuser="username"` is a hard-fail sentinel — LinuxGSM's own data says arma3 is credentialed-only. Zero Guard handling | **Documented only, not implemented** | **No.** Its `details-check` workflow never installs or starts anything — do not mistake it for a boot test |
| **Dzuelu/arma-3-server** | SteamCMD, must own Arma 3 | **Broken** — `-client -connect=` is nested inside the password branch, so a password-less config launches N extra *servers* | No |
| **c-w-o/Arma3Server_v2** | env/JSON, no Guard | Yes | No (lint/scan only) |
| **IPS-Hosting/game-images** | must own the game, no Guard | Yes — clean `MODE=server\|client` single-image design | No |

**Steam credentials remain the unsolved blocker in the container ecosystem**, exactly as `linux-server-steamcmd.md` predicted: app 233780 is not anonymously downloadable, every implementation requires a real account with **Steam Guard fully disabled**, and none handles TOTP or sentry files. Ownership of Arma 3 is not needed for the server but *is* needed for Workshop mods, and Steam permits one concurrent session per account — **parallel CI jobs sharing an account will fight each other.** The prevailing answer is to download once and cache the tree as a volume.

**Two better answers exist and neither is in a container project.** The Steam-Guard-validated `config.vdf` restored from a base64 repository secret (`Asaayu`, §7.1) keeps Guard *enabled*; and the Pelican egg's soft/hard/fatal SteamCMD taxonomy is a ready-made mapping onto our `infra_unavailable` failure class.

**The one real piece of verdict-layer prior art in the container world** is `fbuchmeier/Arma3Server`'s `launch.py`: it reads the server's stdout line by line, touches `/tmp/arma3_launch_success` when it sees `"Dedicated host created"`, and Kubernetes gates on that via an exec readinessProbe. It also regex-parses `Server load: FPS %d, memory used: %d ... Players: %d` into Prometheus gauges. That is the right shape — the game logs structured lines, a supervisor parses, assertions run off the parse.

**Two proven readiness markers to assert on instead of sleeping**: `Host identity created.` (Pelican) and `Dedicated host created` (fbuchmeier). Compare Relicta's `_preload` handshake and mil-sim's "wait for RPT, fail fast if the process died" — three independent projects converged on the same rule.

**LinuxGSM's `monitor` is disqualified as a test oracle**: on query failure it *restarts* the server and alerts. It repairs rather than reports, so a run that silently restarted a dead server still exits 0.

**Container gotchas that will otherwise be rediscovered** (each from a project that hit it):

1. `libnss-wrapper` plus a synthesised passwd entry — **Arma refuses to start under an arbitrary UID with no passwd entry** (Pelican yolk).
2. Pre-create `~/.local/share/Arma 3` and `~/.local/share/Arma 3 - Other Profiles` or you get segfault 20150 (LinuxGSM `fix_arma3.sh`).
3. Pre-create `~/.local/share/Arma 3/MPMissionsCache` or **the headless client crashes** (`DanAlbert/arma3-headless-client-docker/start.sh`).
4. **`-profiles` does not work on the Linux server.** Directly relevant — ATLAS.OS's workflow depends on it.
5. Mod paths must be lowercase and relative (corroborates `linux-server-steamcmd.md` on case sensitivity).
6. `SIGINT`, not `SIGTERM`, is the clean stop; expect exit code 130.
7. HCs bind around 2502+; reserve roughly 200 ports of headroom or you hit `No more slot to add connection`.

**Client in a container splits cleanly.** A *headless* client on Linux is solved and boring — `arma3server -client -connect= -port= [-password=]` is the same binary, no Wine, no X; six independent projects do it, and `Dahlgren/node-arma-server` (`src/headless.js`, `src/server.js`) is the cleanest readable reference, defaulting HCs to `['-noSound','-world=empty']`. Its consumer `Dahlgren/arma-server-web-admin` (134★) shows the correct sequencing: **poll the server with Gamedig and only spawn HCs once it answers.** A *graphical* client headless under Wine/Xvfb, by contrast, **does not exist**: `aaaler/arma3-wine` is mislabelled (it runs the Windows *server* exe) and its README requires clicking through winetricks over VNC, and `muttleyxd/arma3-unix-launcher` (237★) confirms the community route is Steam/Proton on a real desktop. Perceptual/UI coverage on Linux is pioneering.

---

## 9. What nobody does

Being explicit about the searches that came back empty, because a well-evidenced negative is the point of this exercise:

| Search | Result |
|---|---|
| `arma3server path:.github/workflows` | Only ATLAS.OS (never run) + Docker image builds |
| `arma3server_x64 path:.github/workflows` | **Only ATLAS.OS** |
| `loadMission path:.github/workflows` | **Only ATLAS.OS** |
| `-filePatching path:.github/workflows` | **Nothing** |
| `.rpt path:.github/workflows` | Nothing Arma-related |
| `choco install directx path:.github/workflows` | **Only Relicta** (3 workflows) among Arma projects |
| `autotest` across every surveyed mod repo tree | **Zero hits** (ACE3, CBA, ALiVE, Antistasi, ZEN, KP Liberation, Achilles, ACRE2) |
| `"autotest.cfg" arma` on GitHub code search | **Zero** |
| `"TestMissions" "campaign" extension:cfg` | **One repo: `jokoho48/ArmaWatchdogs`** (§5.3) |
| `"autotestSingleMission"` — GitHub code, web, BI wiki (`srwhat=text`) | **Zero everywhere.** Exists only as a binary symbol |
| BI wiki full-text `unit test` / `test framework` / `automated testing` | 62 / 8 / 4 hits, **all false positives** (§4.6) |
| `regression`, `continuous integration`, `nightly build`, `test farm`, `jenkins` across all 479 dev.arma3.com posts | **Zero** (§4.6) |
| HC as a synthetic player in an automated rig | **Zero.** `10Dozen/ArmaTesqf` ("Arma 3 SQF testing framework") is an **empty repo — LICENSE only** |
| Repo search: "arma3 test", "arma integration test" | **Zero results** |

So: **excluding Relicta, mil-sim and HEMTT's own photoshoot plumbing, no Arma 3 project runs an automated test against a live game process.** Nine major mods, roughly 250 in-mission test files, zero CI integration. The recurring failure is not the tests — CBA and ALiVE wrote real ones — it is that nobody built a verdict channel, so the results decay into log noise a human has stopped reading.

---

## 10. Summary table

| Project | What it is | Automates | Verdict channel | Code readable | Relevance |
|---|---|---|---|---|---|
| [Relicta ReSDK_A3.vr](https://github.com/Relicta-Team/ReSDK_A3.vr) + [RBuilder](https://github.com/Relicta-Team/RBuilder) | Total-conversion SDK + Python harness | Boots a pinned Arma 3 **dedicated server** on GitHub `windows-latest`, runs a gtest-style SQF suite, every PR | **Process exit code** via extension; TCP `127.0.0.1:9897` side channel; RPT tail; modal-dialog detection | **Yes, fully** (MIT) | **Highest.** Our architecture, proven |
| [JohnPeng47/mil-sim](https://github.com/JohnPeng47/mil-sim) | Headless drone scenario driven from Python | Boots Arma server on Linux (Proton+Xvfb), closed-loop detect→command→verify | Exit code; **JSONL over `diag_log`**, RPT-tailed; 40-line C `callExtension` inbound channel | **Yes** | **Very high.** Linux; real behavioural assertion |
| [HEMTT](https://github.com/BrettMayson/HEMTT) `bin/src/controller/`, `arma/` | Our build tool's undocumented `photoshoot` harness | Generates `autotest.cfg`, injects an `@hemtt` addon + arma-rs extension, launches Arma, drives it | **arma-rs extension → TCP `127.0.0.1:21337`, u32-LE-framed JSON**, incl. structured `Log(Level,String)` and remote `Exit` | **Yes** | **Highest.** Same author, same crate, proves the whole chain |
| [jokoho48/ArmaWatchdogs](https://github.com/jokoho48/ArmaWatchdogs) | Node.js visual-regression harness | **Drives `-autotest` for real** — spawns the profiling client, mission moves a camera and `screenshot`s, `endMission "END1"` | Exit code + stdout captured; **real assertion is an image diff vs yesterday's run** | **Yes** (small, no licence) | **High.** The only real-world `-autotest` config and the model for a perceptual tier |
| [CySpiegel/ATLAS.OS](https://github.com/CySpiegel/ATLAS.OS) | AI-commander framework | Nothing — workflow has **0 runs**, test list empty | Would be RPT marker grep | Yes | Shape only; runner is subtly broken |
| [Across-the-Fence](https://github.com/Savage-Game-Design/Across-the-Fence) | Mission pack, Python `click` CLI | Launches server **and** client locally; mission staging, config templating | None — no assertions | Yes | High for `just accept` plumbing |
| [WaldosMissionPack](https://github.com/AdamWaldie/WaldosMissionPack) | MP mission framework | CI lints only; in-engine audit is **deliberately manual** | `diag_log` marker w/ `clientOwner`/`isServer`/`hasInterface`; Win32 `PrintWindow` screenshots | Yes | High for assertion + perceptual design; sobering on trust |
| [ACE3](https://github.com/acemod/ACE3) | Largest Arma 3 mod | CI = HEMTT + Python validators. `ace_common_fnc_runTests` is manual | `diag_log` text, `systemChat` | Yes | Config-driven test **discovery** is worth copying |
| [CBA_A3](https://github.com/CBATeam/CBA_A3) | Community base addons | CI = validators + `hemtt build`. 57 tests, manual | `diag_log` only, **no accumulator** | Yes | Cautionary: the anti-pattern |
| [ALiVE](https://github.com/ALiVEOS/ALiVE.OS) | Persistent-war framework | Nothing — Travis dead, no Actions. 124 tests, human-stepped | `diag_log` + `titleText` | Yes | Cautionary: `waitUntil{CONT}` |
| [ACRE2](https://github.com/IDI-Systems/acre2) | Radio mod | CI = validators + build | **`acre_api_testResults` accumulator** | Yes | The accumulator idea |
| [Antistasi](https://github.com/official-antistasi-community/A3-Antistasi) | Persistent CTI-adjacent campaign | Lint only | one file returns `[BOOL, STRING]`, not registered | Yes | Low |
| KP Liberation, DUWS-R, DRO, Vandeanson's | Mission frameworks | Nothing | — | — | None |
| [BECTI](https://github.com/BennyBoy-/BECTI) + [Zerty fork](https://github.com/zerty/Benny-Edition-CTI-0.97-Zerty-Modification) + forks | The CTI lineage | **Nothing at all** | — | — | **Zero prior art in our own genre** |
| [overfl0/Pythia](https://github.com/overfl0/Pythia) | Python-in-Arma extension | `PythiaTester` — a **fake Arma host** that speaks the extension ABI | `unittest` out-of-game | Yes | Model for testing our shim without Arma |
| [dedmen/ArmaDebugEngine](https://github.com/dedmen/ArmaDebugEngine) | Script debugger hooking the live engine | **WebSocket server inside Arma**; `ExecuteCode` runs arbitrary SQF and returns the result **without halting** | JSON over WebSocket, incl. `halt_error` and `halt_scriptAssert` pushed out of process | **Yes** | High as a design; **Windows-only, MASM engine hooks, brittle** |
| [intercept/intercept](https://github.com/intercept/intercept) | C++ binding to the RV engine | Nothing itself, but **CI builds `intercept_x64.so` on ubuntu** | n/a | Yes (MIT) | Linux-capable substrate for the ArmaDebugEngine pattern |
| [fbuchmeier/Arma3Server](https://github.com/fbuchmeier/arma3-helm-chart) `launch.py` | K8s server image | Parses server **stdout** for `Dedicated host created`, touches a readiness file; regex-parses `Server load: FPS…` into Prometheus | stdout line parsing | Yes | The only verdict-layer prior art in the container world |
| [Dahlgren/node-arma-server](https://github.com/Dahlgren/node-arma-server) | Node server/HC launcher | `arma3server -client -connect=` HC spawning; consumer polls with Gamedig before spawning HCs | n/a | Yes | Cleanest readable HC lifecycle reference |
| [oo_unittest](https://github.com/code34/oo_unittest.vr) | OOP.h unit-test class, 2018 | Manual | log dump | Yes | Historical only |
| [10Dozen/ArmaTesqf](https://github.com/10Dozen/ArmaTesqf) | *"Arma 3 SQF testing framework"* | **Nothing — the repository contains only a LICENSE** | — | — | None. Listed so nobody chases it twice |

---

## 11. What we can borrow, and where we are on our own

### 11.1 Borrowable, with attribution

- **Exit code as the primary verdict, carried out through the extension** (Relicta). Our arma-rs shim already owns the RPC path; making it able to say "the run is over, code N" is a small addition and removes all dependence on log scraping for the top-level answer.
- **A structured exit-code vocabulary** mapped onto our failure classes (Relicta's `Constants.py`): distinct codes for `timeout`, `node_crashed`, `assertion_failed`, harness-internal failures. A generic `1` collapses `assertion_failed` into `infra_unavailable`, which our contract explicitly forbids conflating.
- **Readiness handshake instead of a boot sleep** (Relicta's `_preload`; mil-sim's "wait for RPT, fail fast if the process died first"). Directly serves our "never add a sleep to make a test pass" rule.
- **Find the RPT via the process's open file handles**, not by globbing profile directories (Relicta). On Linux the equivalent is `/proc/<pid>/fd`.
- **Frame-counter-keyed assertions** — "the effect appears in a frame later than the command frame" (mil-sim) rather than "sleep then check".
- **JSONL state export over `diag_log`, one record per entity** — and the reason: Arma truncates long `diag_log` lines (mil-sim, stated from experience).
- **Locality tags on every emitted result** — `clientOwner`, `isServer`, `hasInterface` (WMP). Non-negotiable once headless clients are in the topology.
- **Vacuous-case guard**: a test case that produced no assertions fails (WMP).
- **`EXPECT_*` vs `ASSERT_*`** — continue vs abort-this-case — plus `__FILE__`/`__LINE__` in messages and a per-module error counter (Relicta's `TestFramework.h`).
- **Config-driven test discovery** so addons opt in declaratively (`class ACE_Tests`, ACE3).
- **Closed-game staging interlock**: refuse to rebuild or restage while an Arma process is running (WMP `PROCESS.md`). Arma holds mission files open; a live refresh silently mixes cached and current scripts.
- **Steam credentials in CI**: base64 a Steam-Guard-validated `config.vdf` into a repository secret and restore it before `steamcmd` runs — `Asaayu/integrated-voice-control-system`, `.github/workflows/main-build-upload-release.yml`. This is the concrete form of the "pre-seeded credential cache" that `linux-server-steamcmd.md`'s VERDICT said we would need.
- **HEMTT's control protocol wholesale** (§1.3): u32-LE-framed JSON over loopback TCP, harness as server and game as client (so the game can retry-connect while it boots), an explicit mission-identity message, a structured `Log(Level, String)` channel that replaces RPT scraping, and a `Control::Exit` that shuts the engine down cleanly from outside. Also its `rust_embed`-an-`@hemtt`-profile trick for injecting the harness addon and extension without polluting the mod under test.
- **First-party engine affordances we would otherwise reinvent** (§4.2): `-preprocDefine=NAME` instead of a bespoke test-build mechanism; `isAutotest` so a mission knows it is under test; `-doNothing` as a zero-cost launch smoke check; `serverCommandPassword` + `serverCommand "#shutdown"` for clean teardown; `diag_captureSlowFrame` with `sLoop`/`cLoop` scopes and `toFile` for a per-node Perfetto trace.
- **Reforger's step model, expressed in SQF** (§4.8): a test step is either a one-shot `void` or a `bool` polled until true, with a declared `timeoutS`. That is a sleep-free async primitive and the exact opposite of ALiVE's `sleep 3` / `waitUntil {CONT}`. The framework itself does not transfer; this idea does.
- **`endMission "END1"` as the mission-level pass signal, written explicitly at the end of a test mission** (ArmaWatchdogs, §5.3), and `waitUntil {preloadCamera _p;}` as the "the world is really here" condition instead of a sleep.
- **Readiness markers from stdout, not sleeps** (§8): `Dedicated host created` and `Host identity created.`, and Gamedig-polling the server before spawning headless clients (`Dahlgren/arma-server-web-admin`). Three independent projects converged on this; so did Relicta and mil-sim by other means.
- **The Pelican egg's SteamCMD output taxonomy** — soft/hard/fatal, exiting 1 on `Invalid Password|two-factor|No subscription` — as a ready-made mapping onto our `infra_unavailable` class (§8).

### 11.2 Do not copy

- CBA's fire-and-forget `diag_log` assertions with no accumulator, and its `LOG`-disabled-unless-`DEBUG_MODE` trap where a silent run is ambiguous.
- ALiVE's `waitUntil {CONT}` human breakpoints and `sleep`-separated phases.
- ATLAS.OS's runner: `sleep 5` to "settle", counters mutated across `call` scope, and `try/catch` around `execVM` (which returns a handle immediately and catches nothing). Note also its `-profiles=testprofiles`, which **does not work on the Linux server** (§8).
- Relicta's *implementation* — it is Windows-only (`win32gui`, `win32process`) — and its vendoring of Bohemia's server executable into a public repo.
- **`-autotest`'s silence as a pass signal** (§5.2). Only failures appear to be logged, so "no marker" is indistinguishable from "never started". Always emit a positive completion marker of our own.
- **A case-sensitive grep for `<AutoTest`** — the "mission not found" failure uses `<Autotest>` (§5.1).
- LinuxGSM's `monitor` as an oracle: it restarts a failed server rather than reporting, so a silently-revived dead server still exits 0 (§8).
- BattlEye RCON as a verdict channel (§7.3) — SQF cannot write into the RCON stream at all.

### 11.3 Where we would be treading new ground

- **Nobody has done this on Linux natively.** mil-sim runs the *Windows* server under Proton + Xvfb because its extension is a `.dll`; Relicta is Windows throughout; HEMTT's controller is Windows-gated. A native `arma3server` + `arma-rs` `.so` rig on WSL2 has no published precedent — though `arma-rs` is Linux-first (§7.1) and Intercept ships a Linux `.so` from CI (§7.2), so the substrate is there.
- **Nobody uses a headless client as a synthetic player in an automated rig** (§6). And nobody has a locality-aware verdict channel across a server + HC topology; WMP tags results with `clientOwner`/`isServer`/`hasInterface` but a human reads them.
- **Nobody has combined `hemtt launch`-style mission staging with a verdict extractor.** ACE3's and ZEN's `.hemtt/launch.toml` + checked-in `.VR` missions get a *client* into a reproducible state with one command, but no project pairs that with anything that asserts. Note also that `hemtt launch` on Linux shells out to Steam (`-applaunch 107410`, with a flatpak branch) — it launches the **client** through a desktop Steam session and is therefore useless for a headless WSL2 server rig. Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/bin/src/commands/launch/platforms.rs>. HEMTT's own clap doc calls `launch` "Test your project", but it neither runs nor collects tests.
- **Almost nobody uses `-autotest`, and nobody documents `-autotestSingleMission`.** Exactly one public project drives `-autotest` (ArmaWatchdogs, §5.3) plus HEMTT internally (§1.3). `-autotestSingleMission` has zero presence in documentation, code search or the web — if it turns out to mean "run one named mission", we would be the first users of it anywhere, with no reference implementation and no error-mode documentation.
- **Nobody has combined a stdout-parsing supervisor with in-mission assertions.** `fbuchmeier`'s `launch.py` parses server stdout for readiness and performance but asserts nothing; every project with real assertions writes them to a log nobody parses. Joining those two halves — which on native Linux is *simpler* than what Relicta and mil-sim built, because there is no RPT file to find — is the specific piece of engineering we own.
- **Engine version pinning.** Relicta pins by vendoring `cmp_216`/`cmp_218`/`cmp_220`. The licensed equivalent is SteamCMD's depot download, **VERIFIED LOCALLY** on this machine:
  ```
  download_depot <appid> <depotid> [<target manifestid>] [<delta manifestid>] [<destination folder>]: download a single depot
  ```
  (`./steamcmd.sh +login anonymous +help download_depot +quit`). Combined with the depot manifest GIDs already recorded in `linux-server-steamcmd.md` §7.2, this pins an exact server build without redistributing anything — a real mitigation for the `engine_drift` failure class, and better than the one-version-deep `legacy` branch.

---

## 12. Open questions to settle empirically, cheapest first

Every one of these is currently unverified by any source, and each is a short spike:

1. **Does `-autotest` do anything on `arma3server`?** The calling session reports the Linux dedicated server ignored it in `-server` mode. Retry without `-server`, and on the Windows server binary, before concluding.
2. **What is `-autotestSingleMission=`?** Undocumented everywhere (§5.1). Try `-autotestSingleMission=<path to a .VR folder>` and `=<TestCase name>` on the client and observe. If it takes a single mission path, it maps directly onto `just accept <spec-id>`.
3. **Is there a success value at all?** Run an autotest whose mission ends `END1` and diff the output against one that ends `LOSER`. Capture the exit code in both cases (§5.2).
4. **Does `<AutoTest` reach stdout on a native Linux server**, given there is no `.rpt` file (§4.1)?
5. **Is `#exec` accepted over the RCON socket on 2.18+**, where the admin VM gained `callExtension`, `missionNamespace` and `getVariable`/`setVariable` (§7.3)? If yes, RCON becomes an oracle as well as a driver.
6. **Does `arma3server -client` need its own Steam session on Linux** — still open from `linux-server-steamcmd.md` §6.
7. **Does Arma's fatal-error modal have a Linux analogue**, or does a native Linux server die cleanly? Relicta needs `win32gui` for this; if the Linux server just exits, our supervisor is simpler (§1.1).

---

## VERDICT

**Almost nobody does this, but "almost" is doing real work — three projects run automated tests or automated drives against a live Arma 3 process, and one of them is our own build tool.** The strongest precedent is Relicta's `ReSDK_A3.vr`/`RBuilder`: a Python harness that boots a version-pinned Arma 3 **dedicated server** on a GitHub-hosted `windows-latest` runner, runs a gtest-style SQF suite selected by a `-d TEST_ALL` preprocessor define, and returns a structured process exit code through an extension — and its `Check server VM (-d TEST_ALL -d DEBUG)` job is verifiably green on real pull requests in 6–10 minutes, which settles the "is this even possible in CI" question outright. `JohnPeng47/mil-sim` is the Linux-side proof: it drives a closed loop (detect enemy in FOV → write an intercept command through a 40-line `callExtension` bridge → assert the commanded drone's trajectory changed in a *later* frame), exporting state as JSONL over `diag_log`, and it is the only genuine behavioural acceptance test found anywhere. And **HEMTT itself already ships the exact bridge our architecture calls for** — an undocumented `photoshoot` command backed by `bin/src/controller/` and an `arma-rs` extension (`hemtt_comm_x64.dll`) that generates a BI `-autotest` config, injects an `@hemtt` addon, launches Arma, and talks to it over u32-length-prefixed JSON on `127.0.0.1:21337` with a structured `Log(Level,String)` channel and a remote `Control::Exit`. That is the same crate and the same author as the tool we have already committed to, and it means the arma-rs-extension-to-out-of-process-daemon path is not speculative. **Confidence: high** — all three were read in source, and Relicta's was confirmed against Actions run history rather than taken on trust.

**What we should borrow is mostly the verdict channel, because that is precisely what the rest of the ecosystem never built.** Nine major mods contain roughly 250 in-mission test files — ACE3's config-registered `class ACE_Tests` discovery, CBA's 57 suites, ALiVE's 124, ACRE2's `acre_api_testResults` accumulator, WMP's locality-tagged `Waldo_QA_fnc_assert` — and **not one is invoked by anything but a human pasting into the debug console**, because they log assertions and never accumulate, return, or export them. Take ACE3's declarative discovery, ACRE2's accumulator, WMP's `clientOwner`/`isServer`/`hasInterface` tagging and vacuous-case guard, Relicta's `EXPECT_*`-versus-`ASSERT_*` split with `__FILE__`/`__LINE__` and a per-module error counter, and Reforger's step model (a step is a one-shot `void` or a `bool` polled until true with a declared timeout) — then wire the result to a real channel. On our stack that channel is simpler than anyone else's: **a native Linux `arma3server` has no `.rpt` file at all** (Bohemia's own `arma.RPT` page: *"Linux server outputs the 'RPT log' messages on stdout/stderr"*), so every RPT-discovery trick in this report — Relicta's `psutil.open_files()`, mil-sim's `rglob("*.rpt")`, ATLAS.OS's `ls -t *.rpt` — is machinery we do not need; we read a pipe, per node, with the HC giving its own independent stream. Borrow the sleep-free discipline uniformly: Relicta's `_preload` handshake, mil-sim's frame-counter-keyed assertions, and the `Dedicated host created` / `Host identity created.` stdout markers that three container projects converged on. And take the operational scar tissue that costs real days otherwise — `diag_log` truncates around 1044 characters so emit one record per entity; `-profiles` does not work on the Linux server; `SIGINT` not `SIGTERM`; pre-create `~/.local/share/Arma 3/MPMissionsCache` or the HC crashes; never rebuild while Arma holds mission files open; and a base64 `config.vdf` repository secret keeps Steam Guard enabled where every container project demands it be switched off.

**Bohemia gives us exactly one first-party oracle, and it is coarser and more fragile than it first appears.** `-autotest` is real, documented since the Arma 2 lineage, still maintained (`isAutotest` added in 1.24, a Launcher field in 1.32), used in production by HEMTT and by one public project (`jokoho48/ArmaWatchdogs`, a screenshot-diff regression harness). It grades one whole mission by end type — `END1` passes, anything else writes `<AutoTest result="FAILED">` to the log stream and sets an exit code. But **there appears to be no success value**: only failures are logged, so "pass" is signalled by silence, which is indistinguishable from a hang, a missing mission, or a mispointed config — the exact conflation of `assertion_failed`, `timeout` and `infra_unavailable` our contract forbids. Mitigate by always emitting our own positive completion marker before `endMission "END1"`, and match `<autotest` case-insensitively because the mission-not-found failure uses a differently-cased tag. Its sibling **`-autotestSingleMission=` is undocumented everywhere** — zero hits on the BI wiki with `srwhat=text`, zero on GitHub code search, zero on the web; it is known only from binary strings, and the reading that it runs one named mission is inference from a symbol name. On multiplayer the evidence converges: `campaign`/`mission` keys, an end-type verdict, client-only documentation, the one real user driving the windowed client, and the calling session's own observation that the Linux dedicated server ignored the flag in `-server` mode. **Treat `-autotest` as an additional singleplayer/VR logic tier, not as a replacement for the dedicated-server-plus-headless-client tier** where CTI locality, JIP and ownership actually live. Below that tier there is nothing first-party at all: `assert` explicitly does not halt execution, the Diagnostics exe has multiplayer *"removed completely"*, and no Bohemia SQF test framework exists — across all 479 posts on dev.arma3.com the words `regression`, `continuous integration`, `nightly build`, `test farm` and `jenkins` appear **zero times**, against a QA "build checklist" that *"takes approximately three weeks"*. Bohemia built the framework we want — test attributes, poll-until-true steps, JUnit XML — for **Enfusion**, and none of it transfers to Real Virtuality.

**Where we are genuinely on our own is narrower than the brief feared, and it is worth naming precisely.** No project runs this natively on Linux (mil-sim uses Proton only because its extension is a `.dll`; we build an `.so`, and `arma-rs` is Linux-first while Intercept ships a Linux `.so` from CI). **No project anywhere uses a headless client as a synthetic player** — every HC in the ecosystem is AI offload, and the one repo advertising itself as an "Arma 3 SQF testing framework" contains nothing but a LICENSE. That is our blocker and we own it, but the ceiling is now clear rather than unknown: **`hasInterface` is `false` on a headless client**, so an HC is a *locality* driver and never an *interface* driver — it buys a non-null `player`, membership in `allPlayers`, real `remoteExec`/JIP/publicVariable paths and `initPlayerLocal.sqf` execution, and buys nothing on UI, so anything perceptual needs a separate budget (mil-sim's telemetry-rendered MP4 on Linux, or WMP's Win32 `PrintWindow` capture on Windows; a graphical Arma client headless under Wine/Xvfb does not exist). And **no project has joined a stdout-parsing supervisor to in-mission assertions** — `fbuchmeier`'s `launch.py` parses server stdout for readiness and Prometheus metrics but asserts nothing, while every project with real assertions writes them where nothing reads. Joining those two halves is the work, and on native Linux it is *easier* than what Relicta and mil-sim built. **Confidence in the negative: high but not absolute** — GitHub code search never surfaced Relicta under any Arma query, because it renames the server binary to `cmp.exe`; I reached it only by searching for the side effects of running Arma in CI. Read the negatives as "very likely complete", not "provably complete", and note that the single most valuable thing found in this survey was hiding inside a tool we had already adopted and never read the source of.

