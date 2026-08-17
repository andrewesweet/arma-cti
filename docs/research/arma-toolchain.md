# Arma 3 toolchain research: HEMTT, SQF-VM, CBA_A3, just

<!-- absent-path -->
<!-- A dated research record: the repository paths it cites are the tree as it stood when
     the research was done, and some belong to other projects entirely. Neither is a claim
     about this tree today, which is what the marker above tells `just check-doc-paths`. -->

**Researched**: 2026-07-30
**Scope**: Verify the toolchain assumptions in this project's notes against primary sources for a script-only HEMTT addon with a CBA dependency, tested out-of-game with SQF-VM on Linux/WSL2.

Claims marked **VERIFIED LOCALLY** were executed in this environment (WSL2, Linux 6.6) against the real binaries, not just read from docs.

---

## 1. HEMTT

Source repo: <https://github.com/BrettMayson/HEMTT> · Docs: <https://hemtt.dev>

### 1.1 Current version and release cadence

**Latest release: v1.20.1, published 2026-07-24** — six days before this research.
Source: <https://api.github.com/repos/BrettMayson/HEMTT/releases/latest>

Release history (most recent 15, from the GitHub Releases API):

| Version | Published |
|---|---|
| v1.20.1 | 2026-07-24 |
| v1.20.0 | 2026-07-22 |
| v1.19.1 | 2026-05-12 |
| v1.19.0 | 2026-05-02 |
| v1.18.3 | 2026-04-06 |
| v1.18.2 | 2026-02-10 |
| v1.18.1 | 2026-01-07 |
| v1.18.0 | 2025-11-20 |
| v1.17.4 | 2025-11-11 |
| v1.17.2 | 2025-10-04 |
| v1.17.1 | 2025-10-01 |
| v1.17.0 | 2025-09-30 |
| v1.16.4 | 2025-09-09 |
| v1.16.3 | 2025-07-30 |
| v1.16.2 | 2025-06-26 |

Source: <https://api.github.com/repos/BrettMayson/HEMTT/releases>

**Cadence: roughly monthly, 15 releases in the 13 months to 2026-07-24**, with bursts of patch releases within days of a minor (v1.17.0/.1/.2 inside five days; v1.20.0/.1 inside two days). Patch releases follow minors quickly, so pinning an exact version in CI is advisable rather than tracking latest.

> **Caution when researching this repo.** Rendering the GitHub Releases *web page* and asking a model to read the dates yields dates a full two years stale (it reported v1.20.1 as "Jul 24, 2024"), because the page shows relative timestamps. Use the API's absolute `published_at` field. This bit during this research and is worth remembering.

v1.20.1 changelog — note the newly added Workshop publishing command:

```
## Added
* hls: download platform binary
* publish: A new command to publish to the Steam Workshop
## Fixed
* install: fix linux install script
* hls: fix missing binary
```
Source: <https://api.github.com/repos/BrettMayson/HEMTT/releases/latest>

The docs on `main` already reference `1.20.2` in an example, so `main` runs ahead of the latest tag.
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/book/rhai/library/hemtt.md>

### 1.2 `hemtt check` flags for CI — the project note is CORRECT

The project notes claim `hemtt check -p -e` exists. **This is correct.** Both short flags are real and mean what CI would want.

From the clap definition in source:

```rust
#[arg(long, short = 'p', action = clap::ArgAction::SetTrue)]
/// Run all lints that are disabled by default (but not explicitly disabled via project config)
pedantic: bool,
#[arg(long, short = 'e', action = clap::ArgAction::SetTrue)]
/// Treat all help and warning messages as errors
error_on_all: bool,
#[arg(long, short = 'L', action = clap::ArgAction::Append)]
/// Explicit Lints
lints: Vec<String>,
```
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/bin/src/commands/check.rs>

Full flag set for `hemtt check [OPTIONS]`:

| Flag | Long | Meaning |
|---|---|---|
| `-p` | `--pedantic` | Run all default-disabled lints (except those explicitly disabled in project config) |
| `-e` | `--error-on-all` | Treat all help and warning messages as errors |
| `-L` | `--lints <LINTS>` | Enable specific lints by name; repeatable (`-L s01-invalid-command`) |
| `-t` | `--threads <N>` | Thread count, defaults to CPU count |
| `-v...` | | Verbosity, stackable |
| | `--no-color` | Disable coloured output |

Source: <https://hemtt.dev/commands/check.html>

The command's own doc comment states the CI intent explicitly: *"`hemtt check` is the quickest way to check your project for errors. All the same checks are run as `hemtt dev`, but it will not write files to disk... This is ideal for CI/CD pipelines and quick validation during development."*
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/bin/src/commands/check.rs>

**VERIFIED LOCALLY** — built a minimal script-only addon (`.hemtt/project.toml`, one `config.cpp`, two `.sqf` files with deliberate defects) and ran HEMTT 1.20.1's Linux binary with no Arma install, no Arma 3 Tools, and no P drive:

| Invocation | Exit code | Behaviour |
|---|---|---|
| `hemtt check` | **0** | Reported 3 findings (1 help, 2 warnings) but still passed |
| `hemtt check -e` | **1** | Same findings, now fatal |
| `hemtt check -p` | **0** | 7 findings (extra pedantic lints surfaced, incl. `L-S14`) |
| `hemtt check -p -e` | **1** | 7 findings, fatal |

**The `-e` is load-bearing.** Plain `hemtt check` exits 0 even with warnings, so a CI gate that omits `-e` is a no-op for anything short of a hard error. `-p -e` together is the correct strict gate, exactly as the project notes assume.

Two gotchas found locally, both of which cause `hemtt check` to fail before linting anything:
- Without a git repo containing at least one commit, HEMTT errors out unless `git_hash = 0` is set under `[version]` in `project.toml`. Relevant for clean-checkout CI containers and for sandboxes.
- Each addon needs a `$PBOPREFIX$` file, else: `Workspace Error: Addon error: Addon prefix not found: main`.

Also observed: `hemtt check` attempts an online update check and prints `ERROR Failed to check for updates` when it cannot reach GitHub. It is non-fatal (exit code still reflects only lint state), but it will produce noise in an offline/sandboxed CI runner.

### 1.3 Lint coverage

HEMTT ships **57 documented lints** across four categories, all pure-Rust and requiring no Arma installation:

| Category | Count | Source |
|---|---|---|
| SQF | 34 | <https://hemtt.dev/lints/sqf.html> |
| Config | 17 | <https://hemtt.dev/lints/config.html> |
| Stringtables | 3 (`L-L01` sorted, `L-L02` usage, `L-L03` no_newlines_in_tags) | <https://hemtt.dev/lints/stringtables.html> |
| Preprocessor | 3 (`PW1` redefine macro, `PW2` invalid config case, `PW3` padded argument) | <https://hemtt.dev/lints/preprocessor.html> |

The SQF set is the relevant one for a script-only addon and is substantial. Selected lints, with default severity and whether pedantic-only:

| Code | Name | Severity | Default |
|---|---|---|---|
| L-S01 | required_version | Error | Enabled |
| L-S02UE | event_unknown | Warning | Enabled |
| L-S03 | static_typename | Warning | Enabled |
| L-S04 | command_case | Help | Enabled |
| L-S05 | if_assign | Warning | Enabled |
| L-S08 | format_args | Error | Enabled |
| L-S09 | banned_commands | Error | Enabled |
| L-S11 | if_not_else | Help | **Pedantic** |
| L-S12 | unused | Help | **Pedantic** |
| L-S13 | undefined | Help | Enabled |
| L-S15 | shadowed | Help | **Pedantic** |
| L-S16 | not_private | Help | **Pedantic** |
| L-S17 | var_all_caps | Warning | Enabled |
| L-S21 | invalid_comparisons | Error | Enabled |
| L-S22 | this_call | Warning | **Disabled** |
| L-S23 | reasign_reserved_variable | Error | Enabled |
| L-S26 | short_circuit_bool_var | Help | **Pedantic** |
| L-S28 | banned_macros | Error | Enabled |
| L-S32 | missing_file | Warning | Enabled |
| L-S33 | reimplementing_command | Help | Enabled |
| L-S35 | count_skipable | Help | **Pedantic** |
| L-S36 | global_var_in_local | Error | Enabled |

Source: <https://hemtt.dev/lints/sqf.html>

Notably relevant to this project's stated rules: **`L-S09 banned_commands`** and **`L-S28 banned_macros`** are Error-severity and configurable, which is a direct mechanism for the project's "never introduce a bare `random` or bare `sleep` in SQF" contract — that can be enforced by HEMTT config rather than by grep lints. `L-S16 not_private` and `L-S15 shadowed` are pedantic-only, which is part of why `-p` matters.

Lints are configured in `project.toml` under `[lints.*]`, or in a separate `.hemtt/lints.toml` (where the `lints.` prefix is dropped). Three configuration modes: disable (`= false`), change severity (`= "Warning"` / `"Error"` / `"Help"`), or set options:

```toml
[lints.sqf.command_case]
severity = "Error"
options.ignore = ["AGLtoASL", "ASLtoAGL"]
```

Critical lints cannot be disabled or downgraded.
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/book/configuration/lints.md>

### 1.3.1 There is no file- or line-scoped lint suppression (measured, HEMTT 1.20.1)

Every lint configuration above is **project-wide**. HEMTT 1.20.1 offers no way to suppress an SQF
lint for one file, one line, or one addon:

- `#pragma hemtt suppress <code>` exists, but it takes **preprocessor** codes (`pe*`, `pw*`).
  Every lint code tried against it — `s09_banned_command`, `banned_commands`, `L-S09`, `s09`,
  `sqf.banned_commands`, `lints.sqf.banned_commands` — returns
  `error[PE21]: unknown #pragma suppress`.
- The only documented inline escapes are `#pragma hemtt flag pe23_ignore_has_include` and
  `#pragma hemtt ignore_variables [...]` (with its `// IGNORE_PRIVATE_WARNING [...]` alias), which
  serve the `not_private` family alone.
- `banned_commands` accepts two options, `banned` and `ignore`. `ignore` removes a command from
  checking **everywhere**; it cannot name the file allowed to use it.
- `addon.toml` carries `no_bin`, `no_rap`, `properties`, `exclude` and `files`. There is no
  `lints` section, so per-addon severity is not available either.

Measured against the binary directly: `hemtt --version` reports 1.20.1; the pragma vocabulary and
the lint option names above come from its embedded documentation and its own error output, not
from the book.

**Consequence for this project.** The contract wants `random` banned everywhere *except* the
seeded PRNG adapter that wraps it, which is a shape HEMTT cannot express. So `random` is exempted
in `.hemtt/project.toml` via `options.ignore` and re-banned by `tools/check_sqf_bans.py`, a second
step in `just check-sqf` that allows each banned command in a named allow-list of files and
nowhere else. It strips comments and string literals before matching, so prose mentioning a banned
command is not a finding, and it matches case-insensitively because SQF is. `sleep` and `uiSleep`
need no exemption yet and stay banned by both tiers; the same allow-list is where the CBA
scheduler adapter's exemption will go when one exists.

Revisit if HEMTT gains scoped suppression: the tool exists only to supply a scope the linter
cannot, and it should be deleted the day the linter can.

### 1.4 Rhai script hooks for custom pipeline steps

Confirmed. Hooks are Rhai scripts in `.hemtt/hooks/{phase}/`, run in alphabetical order within a phase.

```
.hemtt/hooks/
├── pre_build/01_example.rhai
└── post_build/01_example.rhai
```

Five phases, differing in which filesystem they see:

| Phase | Filesystem | When |
|---|---|---|
| `pre_build` | Virtual | Before preprocessing/binarization/PBO packing — the place to modify files that get packed |
| `post_build` | Virtual | After preprocessing/binarization/packing, before release tasks |
| `pre_release` | Real | `hemtt release` only |
| `archive` | Real | After HEMTT finishes modifying PBOs, before archiving |
| `post_release` | Real | `hemtt release` only, after archives created |

Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/book/rhai/hooks/index.md>

Separately, `hemtt script <name>` runs standalone Rhai scripts from `.hemtt/scripts/`, always on the real filesystem, and hooks can invoke them via `HEMTT.script("name")` and receive a return value.
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/book/rhai/scripts/index.md>

The Rhai API exposes `HEMTT.version()`, `HEMTT.project()`, `HEMTT.mode()`, `HEMTT.is_dev()/is_launch()/is_build()/is_release()`, plus `HEMTT_VFS`/`HEMTT_RFS` filesystem objects, logging (`info`, `print`, `fatal`), project metadata, and time libraries.
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/book/rhai/library/hemtt.md>

**VERIFIED LOCALLY, and this corrects the docs.** Two findings not stated in the documentation:

1. **`pre_build` hooks DO run during `hemtt check`** (only `pre_build`; `post_build` does not fire). Observed output:
   ```
   INFO Running hook: pre_build/01_probe.rhai
   INFO [pre_build/01_probe.rhai] HOOK pre_build ran, mode=check
   ```
2. **`HEMTT.mode()` returns `"check"`** during a check run. The docs list only `dev`, `launch`, `build`, `release`, so `"check"` is an undocumented fifth value.

3. **A Rhai `fatal()` in a `pre_build` hook fails `hemtt check` with exit code 1.** Verified: a hook containing `if HEMTT.mode() == "check" { fatal("..."); }` produced `EXIT=1`, and removing it returned `EXIT=0`.

Consequence for this project: custom validation gates (schema freshness, project-specific grep lints) **can** be wired directly into `hemtt check` via a `pre_build` hook guarded on `HEMTT.mode() == "check"`, rather than living only as separate `just` recipes. Whether that is desirable is a design call — keeping them in `just` is more transparent and debuggable — but the capability exists and is verified.

### 1.5 `hemtt launch` multi-instance support

Confirmed: **`-i, --instances <INSTANCES>` — "Launches multiple instances of the game"**, default 1.

```
Usage: launch [OPTIONS] [CONFIG]... [-- <PASSTHROUGH>...]
```

| Flag | Meaning |
|---|---|
| `-e, --executable <EXECUTABLE>` | Executable to launch, defaults to `arma3_x64.exe` |
| `-i, --instances <INSTANCES>` | Launches multiple instances of the game |
| `-Q, --quick` | Skips the build step, launching the last built version |
| `-F, --no-filepatching` | Disables file patching |
| `-o, --optional <OPTIONAL>` / `-O, --all-optionals` | Include optional addon folders |
| `--no-rap` | Do not rapify (cpp, rvmat, ext, sqm, bikb, bisurf) |
| `-b, --binarize` | Use BI's binarize on supported files |
| `--just <JUST>` | Only build the given addon |
| `-t, --threads <THREADS>` | Thread count |

Source: <https://hemtt.dev/commands/launch.html>

`launch` runs `hemtt dev` internally first, then launches Arma with configured Workshop mods, DLCs and HTML presets. Trailing `-- <PASSTHROUGH>` args are forwarded to the game, which is how server/HC-specific parameters would be supplied.

**Watch the flag collision:** `-e` means `--error-on-all` on `check` but `--executable` on `launch`. Do not copy flags between the two recipes.

Caveat for this project's WSL2 test tier: `launch` targets a real Arma 3 client installation, so it belongs to the Arma-requiring tiers (`just accept`), not to `just check`/`just unit`. The `--just <addon>` flag is unrelated to the `just` command runner — an unfortunate name clash worth noting in recipe comments.

### 1.6 Linux binary availability

Confirmed, first-class. v1.20.1 release assets:

| Asset | Notes |
|---|---|
| `linux-x64` | Bare Linux binary, 51.5 MB |
| `linux-x64.zip` | Zipped Linux binary, 23.6 MB |
| `windows-x64.zip` | |
| `darwin-arm64` | |
| `hls-linux-x64` | HEMTT Language Server, Linux |
| `hls-macos-arm64`, `hls-windows-x64` | HEMTT Language Server |

Source: <https://api.github.com/repos/BrettMayson/HEMTT/releases/latest>

Install options: `winget install hemtt` (Windows); `curl -sSf https://hemtt.dev/install.sh | sh` (Linux and macOS, re-runnable to update); manual download from GitHub Releases; or `cargo install --path bin` from a source checkout (needs latest stable Rust).
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/book/installation/index.md>

**VERIFIED LOCALLY**: downloaded `linux-x64.zip` from the v1.20.1 release, unzipped, `chmod +x`, and ran it on WSL2 with no further dependencies:

```
$ ./hemtt --version
hemtt 1.20.1
```

For CI, pinning the release asset URL by version (and ideally checksum) is preferable to the install script, which tracks latest.

Note also `hls-linux-x64` — HEMTT now ships a **language server** for Linux, new enough that v1.20.1's changelog is still fixing its packaging (`hls: download platform binary`, `hls: fix missing binary`). Potentially useful for agent-driven editing later, but treat as immature.

### 1.7 Is binarization really Windows-only? Nuanced — and irrelevant here

**The blunt claim is wrong for Linux, right for macOS, and moot for this project.** Three separate points:

**(a) The user-facing warning text does say Windows-only.** HEMTT emits diagnostic `BBW2`:

```rust
fn message(&self) -> String { String::from("Platform not supported for binarization.") }
fn note(&self) -> Option<String> { Some(String::from("HEMTT only supports binarization on Windows.")) }
```
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/bin/src/modules/binarize/error/bbw2_platform_not_supported.rs>

**(b) But that warning only fires on macOS.** The non-Windows `init` guards it behind a macOS check and otherwise proceeds to locate Arma 3 Tools and a compatibility layer:

```rust
#[cfg(not(windows))]
fn init(&mut self, ctx: &Context) -> Result<Report, Error> {
    if self.check_only { return Ok(report); }
    if cfg!(target_os = "macos") {
        report.push(PlatformNotSupported::code());
        return Ok(report);
    }
    // ... locate tools at ~/.local/share/arma3tools, $HEMTT_BI_TOOLS, or Steam app 233800
    let path = tools_path.join("Binarize").join("binarize_x64.exe");
    // ... CompatibiltyTool::determine()  -> wine64 / wine / proton
}
```
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/bin/src/modules/binarize/mod.rs>

So **on Linux, binarization works via Wine or Proton** with Arma 3 Tools present. Official guidance: *"HEMTT can use either Proton or Wine to run the tools. `wine` or `wine64` is highly recommended, as using Proton will be much slower and may cause windows to pop up."* Tools are found from `~/.local/share/arma3tools`, or Steam/SteamCMD app 233800, or an explicit `HEMTT_BI_TOOLS` path.
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/book/installation/arma3tools.md>

**(c) None of it matters for a script-only addon.** Binarization is applied only to three model/terrain extensions:

```rust
&& ["rtm", "p3d", "wrp"].contains(&entry.extension().unwrap_or_default().as_str())
```
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/bin/src/modules/binarize/mod.rs>

With no `.p3d`, `.rtm` or `.wrp` files there is nothing to binarize. Further, `hemtt check` constructs the module in check-only mode — `executor.add_module(Box::<Binarize>::new(Binarize::new(true)))` — and `init` returns immediately when `check_only` is set, so **`hemtt check` never even looks for Arma 3 Tools or Wine.**
Source: <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/bin/src/commands/check.rs>

**VERIFIED LOCALLY**: `hemtt check` on the test addon printed `INFO Validated 0 files for binarization` and exited cleanly with no Arma 3 Tools and no Wine installed.

Do not conflate **binarize** (models/terrain; external BI tool; Windows-native or Wine) with **rapify** (config `.cpp` → `.bin`; native Rust; fully cross-platform). Rapification is what a script-and-config addon actually needs, and it ran locally: `INFO Rapified 1 addon configs`, `INFO Compiled 2 sqf files`. A script-only CTI addon can be fully built and checked on Linux with zero Windows dependency.

---

## 2. SQF-VM

Source repo: <https://github.com/SQFvm/runtime>

### 2.1 Is it actively maintained? NO — the project note is WRONG

**The project notes claim SQF-VM is actively maintained. Honest reading of the commit history says otherwise: it is dormant, in build-keep-alive mode only.**

The repo is not archived and the maintainer has not vanished, but **there has been no functional change to the SQF runtime in nearly three years.** Every commit since September 2023 is build/CI plumbing:

| Date | Commit | Nature |
|---|---|---|
| 2026-04-03 | Merge PR #226 from SQFvm/ci-workflow | CI only |
| 2026-04-03 | Add CXXFLAGS to CI workflow for compilers | CI only |
| 2026-04-03 | Update CI workflow and update actions versions | CI only |
| 2024-10-29 | Merge PR #225 from mattysmith22/bugfix-uint32_t-error | Build fix |
| 2024-10-29 | Add header file required to prevent missing uint32_t error on clang | Build fix |
| 2023-09-27 | Merge PR #220 from SpicyBagpipes | Last functional change |
| 2023-09-21 | Add 2.16 dev commands | Last command-set update |
| 2023-09-06 | Update cmds for 2.14 | Command-set update |

Source: <https://api.github.com/repos/SQFvm/runtime/commits>

**That is 5 commits in the 31 months between 2023-09-27 and 2026-04-03**, none of which touched the interpreter. Commit volume by month over the last 100 commits shows the project's real shape — a burst in 2021–2023, then near-silence:

```
2026-04: 3    2023-06: 3    2022-06: 2    2021-08: 3
2024-10: 2    2023-05: 3    2022-04: 2    2021-05: 2
2023-09: 9    2023-03: 4    2022-03: 10   2021-04: 2
              2023-01: 6    2022-02: 19   2021-03: 18
2022-12: 4    2022-10: 3    2021-12: 3
```

Repo metadata: `pushed_at` 2026-04-03, 105 stars, 14 open issues, `archived: false`, licence **LGPL-3.0**, default branch `master`.
Source: <https://api.github.com/repos/SQFvm/runtime>

**Practical implications, which are the point:**
- **The command set is frozen at roughly Arma 3 v2.16.** Anything Bohemia added after late 2023 will not exist in SQF-VM. Code using newer commands will hit "unknown command" at parse time. This dovetails badly with this project's `engine_drift` failure class — SQF-VM cannot be an oracle for current engine behaviour.
- **Do not expect bug fixes.** Any limitation found is a limitation to design around, permanently.
- The upside: a frozen dependency is a *stable* one. Pin the release and it will not move under you.
- The April 2026 CI work does show the maintainer keeps builds green, which is why prebuilt Linux binaries exist and work (below).

**Recommendation: correct the project notes.** Describe SQF-VM as "stable/dormant, frozen at Arma 3 ~2.16 commands, still functional and still the only viable option" rather than "actively maintained." The distinction matters because it changes how much confidence to place in SQF-VM as a behavioural oracle.

### 2.2 Linux build availability — prebuilt, and it works

There is exactly **one modern release: `v2026.04.03-ed9f5f5`, published 2026-04-03**, carrying prebuilt binaries for five targets. Before it, the previous release is **`1.3.2-RC1` from 2019-12-23** — a six-year gap. The scheme is effectively "rolling build of master", tagged by date and short SHA.

| Asset | Size |
|---|---|
| `sqfvm_linux_x64_gcc.zip` | 2.43 MB |
| `sqfvm_linux_x64_clang.zip` | 2.06 MB |
| `sqfvm_macos.zip` | 1.79 MB |
| `sqfvm_windows_x64.zip` | 1.15 MB |
| `sqfvm_windows_win32.zip` | 0.96 MB |

Source: <https://api.github.com/repos/SQFvm/runtime/releases>

**VERIFIED LOCALLY** — downloaded `sqfvm_linux_x64_gcc.zip`, extracted a single `sqfvm` binary, `chmod +x`, ran on WSL2 with no additional dependencies:

```
$ ./sqfvm --version
./sqfvm  version: 2.0.0 - Apr  3 2026 14:30:16 (ed9f5f58a991ed00ff59858e68e01ffcaab89e04)

$ ./sqfvm -a --suppress-welcome --no-execute-print --sqf 'diag_log "hello"; systemChat str (1+1);'
[INF] [L1|C0|__commandline]   [DIAG_LOG] hello
[INF] [L1|C18|__commandline]  [SYSTEM-CHAT] 2
[INF] Context dropped with return value `nil`.
```

**Internal version is 2.0.0**, which does not correspond to any release tag — another reason to pin by tag/SHA (`v2026.04.03-ed9f5f5`) and checksum rather than by version string.

Build-from-source is available and requires a recursive clone: `git clone https://github.com/SQFvm/vm.git --recursive` (or `git submodule init && git submodule update`). Given the prebuilt Linux binary works out of the box, source builds are unnecessary for this project.
Source: <https://raw.githubusercontent.com/SQFvm/runtime/master/README.md>

### 2.3 CLI flags for headless scripted use

All three flags named in the project notes exist and are correct. Verified against the TCLAP declarations in source (`src/cli/cli.cpp`), quoting the help strings verbatim:

| Flag | Type | Description (verbatim) |
|---|---|---|
| `--input-sqf <PATH>` | MultiArg | "Loads provided SQF file from disk. Will be executed as if it was spawned." Case-sensitive. **No short form.** |
| `-a, --automated` | Switch | "Disables CLI prompts." |
| `-v, --virtual <PATH\|VIRTUAL>` | MultiArg | "Creates a mapping for a virtual and a physical path. Mapping is separated by a '\|', with the left side being the physical, and the right argument the virtual path." |
| `-i, --input <PATH>` | MultiArg | "Loads provided file from disk. File-Type is determined using default file extensions (sqf, cpp, hpp, pbo)." |
| `--input-config <PATH>` | MultiArg | "Loads provided config file from disk. Will be parsed prior to files, added using '--input'." |
| `--input-pbo <PATH>` | MultiArg | "Loads provided PBO file from disk and mounts it to SQF-VMs virtual file system (see `--virtual`). If the PBO contains a config.cpp (not binarized), it will be loaded into the config tree." |
| `--sqf <CODE>` | MultiArg | "Loads provided sqf-code directly into the VM. Input is getting preprocessed! Will be executed as if it was spawned." |
| `--config <CODE>` | MultiArg | "Loads provided config-code directly into the VM." |
| `-D, --define <NAME\|NAME=VALUE>` | MultiArg | "Allows to add PreProcessor definitions." |
| `-E, --preprocess-file <PATH>` | MultiArg | "Runs the preprocessor on provided file and prints it to stdout." |
| `-m, --max-runtime <MILLISECONDS>` | ValueArg | "Sets the maximum allowed runtime for the VM. 0 means no restriction in place." |
| `--parse-only` | Switch | "Disables code execution and performs only parsing." |
| `-c, --check-classnames` | Switch | "Enables the config checking for eg. createVehicle." |
| `--suppress-welcome` | Switch | "Suppresses the welcome message during execution." |
| `--no-execute-print` | Switch | "Disables the `Executing...` and two horizontal lines hint printing." |
| `--no-work-print` | Switch | "Prevents the results printing of contexts that reached an empty state." |
| `--no-spawn-player` | Switch | "Prevents automatic player creation." |
| `--no-load-executable-dir` | Switch | "Does not adds the executable path to the virtual file system." |
| `--cli-file <PATH>` | ValueArg | "Allows to provide a file from which to load arguments from. If passed, all other arguments will be ignored! Each argument needs to be separated by line-feed." |
| `--interactive` | Switch | Interactive mode, VM in a separate thread |
| `-V, --verbose` / `-T, --trace` | Switch | Additional / trace output |
| `--pretty-print <PATH>` | MultiArg | Pretty-print an SQF file to console |
| `--command-dummy-nular/unary/binary <NAME>` | MultiArg | "Adds the provided command as dummy." Binary takes `PRECEDENCE\|NAME`. |
| `--sqc`, `--input-sqc`, `--parse-sqc`, `--sqc-to-sqf`, `--sqf-to-sqc` | | SQC dialect support/transpilation |

Source: <https://raw.githubusercontent.com/SQFvm/runtime/master/src/cli/cli.cpp>

Notes for a CI harness:
- **`-a` is mandatory for headless use.** The main loop is `do { ... } while (!m_automated && !m_runtime.is_exit_requested());` — without `-a` it loops waiting for prompts and will hang CI.
- **Virtual path mapping direction is `PHYSICAL|VIRTUAL`** — physical on the left. Easy to invert.
- **`-m/--max-runtime` gives a VM-level timeout**, which is the right way to bound a runaway test. This is preferable to a shell-level timeout because it is the VM's own budget; it also aligns with this project's rule against extending timeouts to make tests pass — set it once, deliberately.
- **`--command-dummy-*` is the sanctioned escape hatch** for the frozen command set (§2.1): commands newer than ~2.16, or engine-only commands, can be declared as dummies so parsing succeeds.
- `--cli-file` is useful for keeping long invocations out of `just` recipes.
- `--suppress-welcome --no-execute-print --no-work-print` together give clean, parseable output.

### 2.4 CRITICAL: SQF-VM does not fail the build on runtime errors

**This is the most important operational finding in this document.** SQF-VM's exit code is nearly useless as a test verdict.

The CLI returns the runtime's exit code only if one was explicitly requested, else zero:

```cpp
auto exitcode = m_runtime.exit_code();
if (exitcode.has_value()) { return exitcode.value(); }
return 0;
```
Source: <https://raw.githubusercontent.com/SQFvm/runtime/master/src/cli/cli.cpp>

And `exit_code()` is only populated when the C++ `exit(int)` method has been called:

```cpp
void exit(int exit_code) { m_exit_code = exit_code; m_is_exit_requested = true; }
std::optional<int> exit_code() const { return m_is_exit_requested ? m_exit_code : std::optional<int>(); }
```
Source: <https://raw.githubusercontent.com/SQFvm/runtime/master/src/runtime/runtime.h>

**VERIFIED LOCALLY** — measured exit codes directly (not through a pipe):

| Input | Exit code | Verdict |
|---|---|---|
| `systemChat "fine";` | 0 | correct |
| `thisIsNotACommand 5;` (parse error) | **255** | correct — parse errors do fail |
| `private _x = "str" + 1;` (runtime type error) | **0** | **WRONG — silently passes** |
| `private _y = _undefinedVar select 0;` | **0** | **WRONG — silently passes** |
| `diag_log "before"; exit;` | 0 | `exit` cannot carry a code |

The runtime type error is not silent in *output* — it prints diagnostics — but the process still exits 0:

```
[ERR] [L1|C19|__commandline]  Unknown input combination STRING + SCALAR.
[FAT] [L1|C19|__commandline]  Stacktrace:<  1 of 1> ...
EXIT=0
```

The SQF-level `exit` command is **nular** (confirmed via `help__ "exit"` → `NULAR 'exit' <exit>`), so `exit 3;` is a *parse error*, not a way to set an exit code. There is no documented SQF-callable way to set a nonzero process exit code.

**Consequence: `sqfvm ... && echo pass` is an invalid test harness.** A test suite must treat stdout as the verdict — scan for `[ERR]`, `[FAT]`, and its own failure markers — and synthesise the exit code itself. Parse errors (255) are the only failure class the exit code reports honestly.

This maps onto this project's failure-class taxonomy: an untyped green from SQF-VM is exactly the "untyped red = harness bug" hazard inverted, and is worth an explicit harness guard. Recommend the harness also assert a *positive* completion marker (e.g. a final `diag_log "SUITE_COMPLETE"`), so a suite that dies halfway cannot masquerade as a pass.

### 2.5 Known limitations with CBA macro-heavy code

Tested empirically rather than inferred. **Headline: CBA's preprocessor macros work well; CBA's runtime functions do not exist at all.**

**What works.** CBA's 68 KB `script_macros_common.hpp` preprocesses cleanly and its macros expand correctly. **VERIFIED LOCALLY** by extracting `cba_main.pbo` from the official v3.18.6 release and mapping it into the VM:

```sh
sqfvm -a --suppress-welcome --no-execute-print \
      -v "cbamain|/x/cba/addons/main" --input-sqf test.sqf
```

with `test.sqf` containing `#include "\x\cba\addons\main\script_macros_common.hpp"`. Results:

```
[DIAG_LOG] QFUNC=cti_core_fnc_doThing QGVAR=cti_core_myVar
[DIAG_LOG] [true,true,true]          // IS_ARRAY, IS_STRING, IS_NUMBER
```

So `PREFIX`/`COMPONENT`-derived macros (`FUNC`, `QFUNC`, `GVAR`, `QGVAR`), the `IS_*` type-check family, and the `TEST_*`/`ASSERT_*` families all expand and evaluate correctly. Macro-heavy CBA-style SQF is genuinely testable in SQF-VM.

**What does not work.** SQF-VM provides no CBA *runtime*. Only the header's macros are available; every `CBA_fnc_*` function is undefined, because CBA's function library is registered at mission init through `CfgFunctions`/XEH, which SQF-VM does not emulate. Two long-standing open enhancement requests cover exactly this gap:

- **#195 "Support CfgFunctions natively"** — open since 2022-02-12
- **#196 "Support referencing functions via virtual path"** — open since 2022-02-12

Source: <https://github.com/SQFvm/runtime/issues>

Both open for over four years, consistent with §2.1's dormancy. Treat as never-fixed.

**The concrete trap.** CBA's `TEST_*` macros call `CBA_fnc_log` on success and `CBA_fnc_error` on failure. Unstubbed, a *failing* test degrades to a warning and the process still exits 0:

```
[WRN] A variable with the name 'CBA_fnc_error' could not be found.
[WRN] Nil value provided for right-handed argument.
[INF] Context dropped with return value `["PREFIX","COMPONENT","Test FAIL","(_a == 6) this one should FAIL","t.sqf",5]`
EXIT=0
```

A failing assertion produces a warning and a success exit code. That is the worst possible default for CI.

**The working recipe.** Stub the two CBA functions and count failures yourself. **VERIFIED LOCALLY:**

```sqf
#define PREFIX cti
#define COMPONENT core
#include "\x\cba\addons\main\script_macros_common.hpp"

cti_failures = 0;
CBA_fnc_log   = { diag_log str _this };
CBA_fnc_error = { cti_failures = cti_failures + 1; diag_log ("TESTFAIL: " + str _this) };

TEST_TRUE(1 == 1, "passing test");
TEST_OP(2,==,2, "op test");
TEST_TRUE(1 == 2, "deliberately failing test");
TEST_FALSE(true, "another deliberate failure");

diag_log format ["FAILURES=%1", cti_failures];
```

Output:

```
[DIAG_LOG] "[CTI] (core) Test OK: (1 == 1) t3.sqf:10"
[DIAG_LOG] "[CTI] (core) Test OK: (2 == 2) t3.sqf:11"
[DIAG_LOG] TESTFAIL: ["cti","core","Test FAIL","(1 == 2) deliberately failing test","t3.sqf",12]
[DIAG_LOG] TESTFAIL: ["cti","core","Test FAIL","(not (true)) another deliberate failure","t3.sqf",13]
[DIAG_LOG] FAILURES=2
```

Note the failure payload is a structured array — prefix, component, `"Test FAIL"`, the stringified condition, source file, and **line number** — which is enough to emit proper per-test CI diagnostics. Combined with §2.4, the harness must still convert `FAILURES=2` into a nonzero exit code itself.

Two further limitations worth designing around:
- **`--input-pbo` did not resolve CBA includes in testing.** Mounting `cba_main.pbo` directly and including `\x\cba\addons\main\script_macros_common.hpp` failed with `FileIO returned no file` (exit 255), despite the PBO carrying the correct `prefix: x\cba\addons\main` property. Extracting the PBO and using `-v "path|/x/cba/addons/main"` worked. **Prefer extract-then-`-v`.**
- **CBA's release zip contains only binarized PBOs, not source headers** (see §3.3), so obtaining `script_macros_common.hpp` requires either unpacking a PBO or fetching CBA source separately.

---

## 3. CBA_A3

Source repo: <https://github.com/CBATeam/CBA_A3> · Docs: <https://cbateam.github.io/CBA_A3/docs/>

### 3.1 Current release version

**v3.18.6, published 2026-04-01.** Recent history:

| Version | Published |
|---|---|
| v3.18.6 | 2026-04-01 |
| v3.18.6-RC1 | 2026-03-27 (pre-release) |
| v3.18.5 | 2025-12-23 |
| v3.18.4 | 2025-07-15 |
| v3.18.3 | 2025-03-20 |

Source: <https://api.github.com/repos/CBATeam/CBA_A3/releases>

Cadence is a few releases a year, each preceded by RC pre-releases. Stable and slow — good for pinning. Minor version has sat at `3.18.x` across all of these.

### 3.2 Licence — GPL-2, with an important carve-out

**GPLv2**, per `LICENSE.md`. Note the file is `LICENSE.md`, not `LICENSE` (fetching the latter 404s).

The README adds a clarification that is directly material to this project:

> "Licensed under GNU General Public License ([GPLv2](LICENSE.md))
>
> Any addon which calls CBA-defined functions need not be licensed under the GPLv2 or released under a free software license. Only if it is directly including CBA code in the addon's binarized PBO or redistributing a modified version of CBA itself would it be considered derivative and therefore be legally required to be released under the terms of the GPL. (And there's no reason to ever do either of these.)"

Source: <https://raw.githubusercontent.com/CBATeam/CBA_A3/master/README.md>

Practical reading for a CTI addon:
- **Calling `CBA_fnc_*` from our addon does not make our addon GPL.** Explicit upstream position.
- **Using CBA's macros needs a moment's thought.** `#include`-ing `script_macros_common.hpp` places CBA-authored preprocessor code into our compiled output, which is nearer the "including CBA code in the addon's binarized PBO" case the README flags. Every major mod (ACE3 included) does exactly this, and CBA plainly intends it, but if this project cares about its own licence terms this is the one point to think about rather than assume. Not legal advice.
- **Vendoring the unmodified release zip is straightforward GPLv2 redistribution**: keep `LICENSE.md` (it is inside the zip) and be able to point at the corresponding source tag. Do not modify it.

### 3.3 Release artefact suitable for vendoring

Yes — a single self-contained zip per release, no Steam Workshop needed.

```
URL:    https://github.com/CBATeam/CBA_A3/releases/download/v3.18.6/CBA_A3_v3.18.6.zip
Size:   1698264 bytes
SHA256: 80fedfbd9cb57b2393a34c84f80a5268ce8a51b31013976d84232be04c72bf8d
```

SHA-256 **computed locally** from the downloaded artefact; verify independently before trusting it in a lockfile.
Asset metadata source: <https://api.github.com/repos/CBATeam/CBA_A3/releases>

Contents (109 files, 4.87 MB unpacked):

```
@CBA_A3/
├── addons/            *.pbo + matching *.bisign (signed, binarized)
├── keys/              .bikey
├── optionals/         cba_cache_disable, diagnostic_*, disable_missing_mod_check, legacy_jr, ...
├── userconfig/cba_settings.sqf
├── LICENSE.md   README.md   meta.cpp   mod.cpp   logo_cba_ca.paa
```

Suitable for vendoring: stable URL, one file, deterministic hash, includes `LICENSE.md` for GPLv2 compliance and `.bikey`/`.bisign` for server signature verification. Installation is just unpacking into the Arma directory and launching with `-mod=@CBA_A3`.
Source: <https://raw.githubusercontent.com/CBATeam/CBA_A3/master/README.md>

**Important caveat for the SQF-VM tier: the zip contains only binarized PBOs — no source headers.** To get `script_macros_common.hpp` for SQF-VM you must either unpack a PBO or vendor CBA source separately. Verified locally with HEMTT's own PBO tooling:

```
$ hemtt utils pbo inspect @CBA_A3/addons/cba_main.pbo
Properties
  - prefix: x\cba\addons\main
  - version: 3.18.6.260327
Checksum (SHA1)  Stored/Actual match
Files: 18 — script_macros_common.hpp (68332 bytes), script_macros.hpp,
        script_macros_config.hpp, script_macros_mission.hpp, script_classes.hpp,
        script_component.hpp, script_eventhandlers.hpp, config.bin, license.txt, ...
```

`hemtt utils pbo unpack <pbo> <dir>` extracts them, which pairs cleanly with the `-v` mapping in §2.5. **This means one vendored CBA zip serves both tiers** — runtime dependency for the Arma tiers, and unpacked headers for the SQF-VM tier — using HEMTT (already a dependency) as the unpacker. No extra tooling required. Pin the zip by SHA-256 and derive everything else from it.

### 3.4 Test and assertion macros

Confirmed present and officially documented. Defined in `addons/main/script_macros_common.hpp`:

| Macro | Line | Purpose |
|---|---|---|
| `TEST_TRUE(CONDITION, MESSAGE)` | 1514 | "Tests that a CONDITION is true. If the condition is not true, an error is raised with the given MESSAGE." |
| `TEST_FALSE(CONDITION, MESSAGE)` | 1541 | Inverse |
| `TEST_OP(A,OPERATOR,B,MESSAGE)` | 1570 | "Tests that (A OPERATOR B) is true. If the test fails, an error is raised with the given MESSAGE." |
| `TEST_DEFINED_AND_OP(A,OPERATOR,B,MESSAGE)` | 1599 | Definedness + comparison |
| `TEST_DEFINED(VARIABLE,MESSAGE)` | 1630 | Variable is defined |
| `TEST_SUCCESS(MESSAGE)` | 1494 | `MESSAGE_WITH_TITLE("Test OK",MESSAGE)` |
| `TEST_FAIL(MESSAGE)` | 1495 | `ERROR_WITH_TITLE("Test FAIL",MESSAGE)` |
| `ASSERT_TRUE(CONDITION,MESSAGE)` | 1416 | "Asserts that a CONDITION is true. When an assertion fails, an error is raised with the given MESSAGE." |
| `ASSERT_FALSE(CONDITION,MESSAGE)` | 1438 | Inverse |
| `ASSERT_OP(A,OPERATOR,B,MESSAGE)` | 1462 | Assert a comparison |
| `ASSERT_DEFINED(VARIABLE,MESSAGE)` | 1485 | Assert definedness |

Source (definitions): <https://raw.githubusercontent.com/CBATeam/CBA_A3/master/addons/main/script_macros_common.hpp>
Source (official docs, with parameters and examples): <https://cbateam.github.io/CBA_A3/docs/files/main/script_macros_common-hpp.html>

Documented examples: `TEST_TRUE(_frogIsDead,"The frog is alive");` and `TEST_OP(_fish,>,5,"Too few fish!");`

`TEST_TRUE` expands to a plain `if (CONDITION) then { TEST_SUCCESS(...) } else { TEST_FAIL(...) }`, capturing the stringified condition via `'(CONDITION)'`, which is why failure output includes the source expression and line number (§2.5).

Also available and useful for defensive checks: the `IS_*` type predicates (`IS_ARRAY`, `IS_BOOL`, `IS_CODE`, `IS_CONFIG`, `IS_STRING`, `IS_SCALAR`, `IS_OBJECT`, `IS_GROUP`, `IS_SIDE`, `IS_INTEGER`, `IS_NUMBER`, and more), all built on `IS_META_SYS(VAR,TYPE)` which is nil-safe.

**Assessment for this project.** These macros are a reasonable assertion vocabulary and are free (already depending on CBA). But they are *not* a test framework: no test discovery, no per-test isolation, no structured report, no exit code. Given §2.4 and the `CBA_fnc_error` stubbing requirement in §2.5, expect to write a thin harness that stubs the CBA logging functions, counts failures, enforces a completion marker, and converts the tally into a process exit code. The macros supply assertions and good failure payloads; everything else is ours.

---

## 4. `just` command runner

Source repo: <https://github.com/casey/just>

**Current state: healthy and fast-moving. Latest release `1.57.0`, published 2026-07-19** — eleven days before this research.
Source: <https://api.github.com/repos/casey/just/releases/latest>

**Install method on Ubuntu: do NOT use `apt`.** The archive versions are badly stale:

| Ubuntu release | apt version | Upstream date of that version | Behind latest |
|---|---|---|---|
| noble (**24.04 LTS**) | `1.21.0-1` | 2023-12-29 | ~2.6 years, 36 minor versions |
| questing (25.10) | `1.40.0-1` | 2025-03-09 | ~1.4 years |
| resolute (**26.04 LTS**) | `1.45.0-1` | 2025-12-10 | ~7 months, 12 minor versions |

Sources: <https://packages.ubuntu.com/search?keywords=just&searchon=names&suite=all&section=all>, cross-checked against <https://raw.githubusercontent.com/casey/just/master/CHANGELOG.md> (`[1.21.0] - 2023-12-29`, `[1.40.0] - 2025-03-09`, `[1.45.0] - 2025-12-10`). Package is in `universe`.

`apt install just` on 24.04 LTS yields **1.21.0 from December 2023**. just's README lists Ubuntu 24.04 under apt without warning about staleness. Anything added since then (newer attributes, functions, module improvements) will fail. The 24.04-vs-26.04 split (1.21.0 vs 1.45.0) is also a real local/CI portability hazard.

The README offers three routes without recommending one: *"Just can be installed using your favorite package manager, by downloading pre-built binaries, or building from source with `cargo install just`."*
Source: <https://raw.githubusercontent.com/casey/just/master/README.md>

**Recommended for this project — prebuilt binary, pinned by tag:**

```sh
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh \
  | bash -s -- --tag 1.57.0 --to ~/.local/bin
```

The `--tag` is not optional in practice. Verbatim from the README:

> "Note that `install.sh` may fail on GitHub Actions, or in other environments where many machines share IP addresses. `install.sh` calls GitHub APIs in order to determine the latest version of `just` to install, and those API calls are rate-limited on a per-IP basis. To make `install.sh` more reliable in such circumstances, pass a specific tag to install with `--tag`."

(This research hit exactly that GitHub API rate limit from a shared IP, so treat the warning as real.) Releases ship `SHA256SUMS`; verify with `shasum --algorithm 256 --ignore-missing --check SHA256SUMS`.

For CI the README points at dedicated actions rather than the script:

```yaml
- uses: extractions/setup-just@v3
  with:
    just-version: 1.57.0
```

`cargo install just` is the third option — always current, needs a Rust toolchain (which this project already has for the arma-rs shim, per ADR-0005, so it is a low-marginal-cost choice).

Pin the same explicit version locally and in CI so the two are provably identical; apt cannot offer that across Ubuntu releases.

---

## 5. Has anything displaced these? A survey of what major mods actually run

**Short answer: HEMTT has won, SQF-VM has no competitor but also no adopters, and this project's intended stack is more modern than ACE3's — with one notable divergence.**

### 5.1 Every major mod uses `arma-actions/hemtt@v1` + `hemtt build`

Surveyed four actively-developed Arma 3 mods' real workflow files:

| Mod | HEMTT in CI | SQF-VM in CI | SQF checking used instead |
|---|---|---|---|
| **acemod/ACE3** | Yes, exclusively | **No** | **HEMTT's native lints** via `.hemtt/lints.toml` + Python validators |
| **CBATeam/CBA_A3** | Yes (+ Mikero pboProject in parallel) | **No** | Hand-rolled `tools/sqf_validator.py` + Python validators |
| **IDI-Systems/acre2** | Yes | **No** | Python validators + archived `sqflint` (`continue-on-error: true`) |
| **zen-mod/ZEN** | Yes | **No** | Python validators + archived `sqflint` (`continue-on-error: true`) |

ACE3's build job, verbatim:

```yaml
- name: Setup HEMTT
  uses: arma-actions/hemtt@v1
  with:
    annotate: true
- name: Run HEMTT build
  run: hemtt build
```
Source: <https://raw.githubusercontent.com/acemod/ACE3/master/.github/workflows/arma.yml>

ACE3's local dev build is the same tool — `build.bat` is two lines: `hemtt.exe build`.
Source: <https://raw.githubusercontent.com/acemod/ACE3/master/build.bat>

ACE3 migrated to HEMTT in **December 2019** and has been fully HEMTT-driven since. The old pipeline is gone from CI: no `Makefile`, no root `build.py`; `tools/make.py` survives on disk but no workflow invokes it, and the root `hemtt.toml` is a dead HEMTT-v0 leftover last touched 2020-03-01 (live config is `.hemtt/project.toml`).
Source: <https://github.com/acemod/ACE3/commits/master/hemtt.toml>

**Two divergences from this project's plan worth deciding about:**

1. **Nobody runs `hemtt check` in CI — they run `hemtt build`.** ACE3 goes straight to the real build. For this project, `hemtt check -p -e` in `just check` is *better* for a fast no-Arma edit loop (§1.2), but `just build` should still exercise `hemtt build`, because `check` skips disk-write paths and can therefore miss packaging failures. Do not treat a green `check` as proof that `build` works.
2. **ACE3 pins the *action*, not the HEMTT version.** `arma-actions/hemtt@v1` defaults its `version` input to `latest`, and ACE3 never overrides it — so ACE3's CI floats on whatever HEMTT released most recently.
   Source: <https://raw.githubusercontent.com/arma-actions/hemtt/v1/action.yml>
   Given HEMTT's ~monthly cadence with same-week patch releases (§1.1), **this project should pin an explicit HEMTT version** rather than copy ACE3 here. A floating toolchain is precisely the thing that produces unexplained `engine_drift`-looking failures.

### 5.2 ACE3 validates SQF with HEMTT lints — direct precedent for §1.3

The most important cross-check: ACE3 does its SQF static analysis *inside* `hemtt build` using HEMTT's own lints, configured in `.hemtt/lints.toml`, annotated onto PRs via `annotate: true`:

```toml
[sqf.banned_commands]
options.ignore = ["addPublicVariableEventHandler", "createSoundSource"]
[sqf.var_all_caps]
options.ignore = ["SLX_*", "ACE_*"]
[sqf.banned_macros]
options.release = ["DEBUG_MODE_FULL", "DISABLE_COMPILE_CACHE", "ENABLE_PERFORMANCE_COUNTERS"]
[sqf.undefined]
enabled = true
options.check_orphan_code = true
[sqf.unused]
#enabled = true #many false positives without DEBUG_MODE_FULL
options.check_params = false
[sqf.shadowed]
enabled = false
[sqf.not_private]
enabled = true
```
Source: <https://raw.githubusercontent.com/acemod/ACE3/master/.hemtt/lints.toml>

Three things to take from this:
- **`banned_commands` is used in production by the largest Arma 3 mod.** Direct precedent for enforcing this project's "no bare `random`, no bare `sleep`" rule as a HEMTT lint (Error severity) instead of a bespoke grep lint.
- **`banned_macros` supports an `options.release` list** — macros banned only in release builds. Useful for debug-only scaffolding.
- **ACE3 disables `shadowed` and leaves `unused` off** because of false positives. Expect to tune, not to adopt `-p` wholesale unexamined; a small greenfield codebase can plausibly hold a stricter line than ACE3 can.

ACE3 supplements lints with Python validators — `config_style_checker.py`, `stringtable_validator.py`, `check_strings.py`, `document_functions.py`, plus `arma-actions/bom-check` — and uses Rhai hooks (`.hemtt/hooks/pre_build/01_set_version.rhai`), confirming §1.4's hook mechanism is used in anger. Its Rust extension is tested separately with `cargo fmt --check`, `cargo clippy --all -Dwarnings`, and `cargo tarpaulin` — a reasonable template for this project's arma-rs shim (ADR-0005).

### 5.3 Nothing has displaced HEMTT

| Tool | Status |
|---|---|
| **HEMTT** | **Current standard.** v1.20.1 (2026-07-24), ~monthly releases, now ships a language server and a `publish` command. Self-describes as "a replacement for tools like Addon Builder and pboProject". |
| **Mikero tools / pboProject** | Alive but legacy; used only for Windows binarizing builds (CBA). Its action is pinned at date tag `2024-10-11`. |
| **armake2** | Effectively dead — no functional commits since 2021-08-30; README still lists unimplemented features. |
| **sqflint** (LordGolias/sqf) | **Archived 2023-08-06, read-only.** Still used by ACRE2/ZEN but wrapped in `continue-on-error: true` due to false positives; its action last updated Oct 2019. |
| **ArmaScriptCompiler / sqfc** | Superseded — HEMTT absorbed SQF compilation (ACE3, Dec 2023); the action last updated Feb 2022. |
| **Arma Reforger / Enfusion Workbench** | **Irrelevant.** Different engine and language (Enforce Script, "syntactically close to C#"), not SQF. Nothing transfers to Arma 3. |
| **sqf-analyzer** | A VSCode extension, not a CI tool; zero adoption in the four mods surveyed. |

Sources: <https://github.com/BrettMayson/HEMTT/releases/latest>, <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/README.md>, <https://github.com/KoffeinFlummi/armake2/commits/master>, <https://github.com/LordGolias/sqf>, <https://github.com/orgs/arma-actions/repositories>, <https://community.bistudio.com/wiki/Arma_Reforger:From_SQF_to_Enforce_Script>

### 5.4 SQF-VM has no competitor — and no adopters

The uncomfortable finding: **SQF-VM is the only tool that executes SQF outside the game, and not one of the four major mods runs it in CI.**

- sqflint's interpreter is archived; HEMTT lints statically but does not *execute* SQF.
- **There is no `arma-actions/sqf-vm` action.** The arma-actions org has exactly 7 repos (hemtt, arma3-tools, mikero-tools, bom-check, workshop-upload, sqfc, sqflint) and SQF-VM is absent.
  Source: <https://github.com/orgs/arma-actions/repositories>
- Both ACE3 and CBA ship a `tools/sqfvmChecker.py`, but it is a **local developer tool only**, never invoked by a workflow. ACE3's hardcodes a Windows `P:` drive:
  ```python
  sqfvm_exe = os.path.join(addon_base_path, "sqfvm.exe")
  virtual_paths = ["P:/a3|/a3", "P:/x/cba|/x/cba", "{}|/z/ace".format(addon_base_path)]
  ```
  Source: <https://raw.githubusercontent.com/acemod/ACE3/master/tools/sqfvmChecker.py>
  Note it uses the same `PHYSICAL|VIRTUAL` mapping form documented in §2.3, and maps CBA at `/x/cba` — corroborating the approach verified in §2.5.
- CBA's actual CI SQF check, `tools/sqf_validator.py`, is a hand-rolled character-by-character bracket/semicolon/string-state checker — no VM at all.
  Source: <https://raw.githubusercontent.com/CBATeam/CBA_A3/master/tools/sqf_validator.py>

**Read this honestly, in both directions.** The major mods evidently judged SQF-VM not worth wiring into CI, preferring static lints plus in-game testing. That is a genuine negative signal, and it explains the rough edges found in §2.4 and §2.5: the exit-code behaviour and the `CBA_fnc_error` trap are the kind of thing that would have been fixed years ago had anyone been gating CI on it. This project will be treading a less-worn path and should expect to own its harness.

Equally, those mods are large, mature, and have human playtesters; this project explicitly aims at "maximal automated testing" with agent-driven development and a no-Arma-required fast tier. For that goal, executing SQF headlessly is worth real effort even without precedent, and §2.5 demonstrates it does work. The mitigation is to keep the SQF-VM tier's scope honest: pure-logic units (economy, orders, objective ownership, PRNG) where the frozen ~2.16 command set (§2.1) and absent CBA runtime are non-issues, and to push anything touching engine behaviour down to the Arma-requiring acceptance tiers rather than trusting SQF-VM as an oracle.

---

## VERDICT

The toolchain is sound and the project's notes are mostly right, with one claim to correct and one operational trap to design around. **HEMTT is unambiguously the right choice and in excellent health** — v1.20.1 shipped 2026-07-24 on a roughly monthly cadence, the Linux binary was verified running natively on this WSL2 box, and the notes' `hemtt check -p -e` invocation is exactly correct (`--pedantic` plus `--error-on-all`), verified end-to-end to exit 1 on lint findings and 0 without them; note that omitting `-e` makes the gate a no-op, since plain `check` passes despite warnings. Its 57 lints, Rhai hooks (which do fire on `check`, in an undocumented `mode() == "check"`, and can fail it via `fatal()`), and `launch -i/--instances` multi-instance support all check out, and the "binarization is Windows-only" worry is doubly moot: Linux binarization actually works via Wine/Proton, only macOS is unsupported, and a script-only addon with no `.p3d`/`.rtm`/`.wrp` files never invokes it at all — `hemtt check` skips the tools entirely, so the whole no-Arma Linux tier is unblocked. **The one claim that must be corrected is SQF-VM's "actively maintained": it is not** — five commits in the 31 months to April 2026, all CI or build plumbing, with the last functional runtime change in September 2023, leaving the command set frozen at roughly Arma 3 v2.16 and two four-year-old open issues (#195, #196) covering precisely the missing CBA `CfgFunctions` support; it is best described as stable-but-dormant, still the *only* way to execute SQF headlessly, and notably not used in CI by ACE3, CBA, ACRE2 or ZEN, all of which rely on HEMTT's own lints instead. The prebuilt Linux binary nonetheless works (verified, internal version 2.0.0), the claimed `--input-sqf`, `-a` and `-v` flags are all real, and CBA's macros — including the `TEST_*` family — do preprocess and evaluate correctly under a `-v "path|/x/cba/addons/main"` mapping; but **the critical trap is that SQF-VM exits 0 on runtime errors and on failed CBA assertions** (only parse errors return 255, and the SQF `exit` command is nular so cannot carry a code), and unstubbed `TEST_*` failures degrade to mere warnings, so the harness must stub `CBA_fnc_log`/`CBA_fnc_error`, count failures, assert a positive completion marker, and synthesise its own exit code. CBA_A3 v3.18.6 (2026-04-01) is GPLv2 with an explicit upstream carve-out that merely calling its functions does not infect our licence, and its single release zip (SHA-256 `80fedfbd…bf8d`) is ideal for SHA-pinned vendoring — with the wrinkle that it ships only binarized PBOs, so the SQF-VM tier must unpack `cba_main.pbo` (conveniently via `hemtt utils pbo unpack`, already a dependency) to obtain `script_macros_common.hpp`. Finally, install `just` (1.57.0) from the pinned prebuilt binary rather than apt, which serves a December-2023 build on Ubuntu 24.04, and pin HEMTT explicitly rather than copying ACE3's floating `arma-actions/hemtt@v1` default.
