# arma-rs (BrettMayson) — primary-source assessment

**Research date:** 2026-07-30
**Subject:** [`arma-rs`](https://crates.io/crates/arma-rs) — Rust library for Arma 3 extensions
**Repository:** <https://github.com/BrettMayson/arma-rs>
**Version examined:** crates.io `1.12.1`; repo `main` at commit [`143f964`](https://github.com/BrettMayson/arma-rs/commit/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc) (2026-05-21)

## Method and limits of this investigation

Sources used were the GitHub REST API for the repository, the crates.io REST API, the repository source tree (cloned at `143f964`), docs.rs, `doc.rust-lang.org`, and the manifests/CI of downstream projects fetched from `raw.githubusercontent.com`.

Two limits are worth stating up front, because they bound the confidence of two claims below:

1. **The Bohemia Interactive Community Wiki is behind a Cloudflare interstitial** that returns HTTP 403 to both `curl` and the fetching tool available here (verified against `https://community.bistudio.com/wiki/Arma_3:_Extensions`, `/wiki/Extensions` and `/wiki/callExtension`). Wiki claims below are therefore attributed to the wiki page that owns them, but the text was recovered via search-engine extracts of those official pages rather than a direct fetch. Anything resting on that is flagged **[wiki, indirect]**.
2. **No Rust toolchain exists on this host** (`rustc`, `cargo`, `rustup`, `clang`, `x86_64-w64-mingw32-gcc` all absent). Nothing in section 3 was empirically compiled. Cross-compilation conclusions are derived from reading arma-rs' own `cfg` gating and dependency graph plus the toolchains' own documentation, not from a successful build.

---

## 1. Is arma-rs actively maintained as of mid-2026?

**Yes, but in bursts, by essentially one maintainer, with a stale release process on the GitHub side.**

### Latest version

- crates.io `max_version` / `newest_version` is **`1.12.1`**, published **2026-01-10T03:52:20Z**. Total downloads 77,161; recent downloads 3,175; 46 published versions since 2021-12-31.
  Source: <https://crates.io/api/v1/crates/arma-rs>
- `1.12.1` metadata: edition **2024**, license field **MIT**, not yanked, no `rust_version` (MSRV) field declared.
  Source: <https://crates.io/api/v1/crates/arma-rs/1.12.1>
- `arma-rs/Cargo.toml` on `main` also reads `version = "1.12.1"`, `edition = "2024"`.
  Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/Cargo.toml>

### Repository activity and health

From `GET /repos/BrettMayson/arma-rs` (unauthenticated, 2026-07-30):

| Field | Value |
|---|---|
| `pushed_at` | 2026-05-21T17:15:13Z |
| `created_at` | 2019-07-31T21:42:12Z |
| `stargazers_count` | 47 |
| `forks_count` | 9 |
| `subscribers_count` | 6 |
| `open_issues_count` | **0** |
| `archived` | false |
| `license.spdx_id` | **GPL-2.0** |

Source: <https://api.github.com/repos/BrettMayson/arma-rs>

`open_issues_count` in the GitHub API counts open issues **and** open pull requests, so the repository currently has zero of either. Issue/PR history (`GET /repos/BrettMayson/arma-rs/issues?state=all`) shows every item from #33 (2023-02) through #57 (2026-05) closed.
Source: <https://api.github.com/repos/BrettMayson/arma-rs/issues?state=all&per_page=25>

Recent commits on `main` (`GET /repos/BrettMayson/arma-rs/commits`):

| Date | Commit | Author | Subject |
|---|---|---|---|
| 2026-05-21 | `143f964` | Grim | `fix(loadout): handle CBA Extended Loadout for IntoArma (#57)` |
| 2026-01-10 | `9b736a7` | Brett Mayson | `handle strings in arrays` |
| 2026-01-10 | `13909bf` | Brett Mayson | `version 1.12.0` |
| 2025-11-09 | `55d6646` | PabstMirror | `call-context - work in debug (#55)` |
| 2025-11-09 | `0ab3bc8` | PabstMirror | `Update for extern changes in rust 1.89 (#54)` |
| 2025-04-05 | `6cac89d` | BrettMayson | `really pub` |
| 2024-12-18 | `adfc323` | BrettMayson | `bump deps, fix uuid` |
| 2024-09-19 | `1eae4e8` | BrettMayson | `fix crashing on 2.16` |

Source: <https://api.github.com/repos/BrettMayson/arma-rs/commits?per_page=40>

Observations drawn from that data:

- **Cadence is bursty, not steady.** Publish dates cluster (2024-09-17/18 saw ten releases in ~28 hours; 2025-04-05 saw three) with multi-month gaps between clusters. Gaps of 6+ months between commits are normal for this repo.
- **Responsiveness varies widely.** Issue #56 (`Loadout::to_arma() skips CBA Extended Loadout info`, opened 2026-05-20) was fixed and merged the next day. By contrast issue #53 (`CTD with CallContext when using non release build`, opened 2024-10-29) stayed open **~12 months** until 2025-11-09, and PR #54 (`Update for extern changes in rust 1.89`, opened 2025-08-07) waited **~3 months** to merge.
- **The project tracks Arma and Rust changes.** `fix crashing on 2.16`, `2.18 Context Features` (#52), and `Update for extern changes in rust 1.89` (#54) are all reactive maintenance to upstream game/compiler changes, which is the signal that matters most for a game-modding dependency.
- **Outside contributors land patches** (PabstMirror — an ACE3 core maintainer, Pepijn Holster, Grim), so it is not strictly a solo project, though Brett Mayson does all releases.
- **GitHub Releases are abandoned.** The most recent GitHub release is `v1.10.0` (2023-09-08), and only three tags exist (`v1.5.1`, `v1.10.0`, `v1.10.2`). Releases happen on crates.io only; do not use the GitHub releases feed to track versions.
  Sources: <https://api.github.com/repos/BrettMayson/arma-rs/releases>, <https://api.github.com/repos/BrettMayson/arma-rs/tags>
- **There is an unreleased fix on `main`.** `143f964` (2026-05-21, the CBA Extended Loadout fix) postdates the `1.12.1` publish (2026-01-10) and is not in any crates.io release. If you need it you must depend on the git rev.

### Two documentation/metadata defects worth knowing

- **License is inconsistent.** `arma-rs/Cargo.toml` declares `license = "MIT"` and crates.io reports MIT, but the repository's `LICENSE` file is the **GNU General Public License v2** (341 lines, GPL-2.0 preamble) and GitHub's licence detector reports `GPL-2.0`. These are not compatible characterisations of the same code. For a mod that links this crate into a distributed `.dll`/`.so`, that ambiguity is a real (if low-probability) legal loose end and should be resolved with the author before shipping.
  Sources: <https://api.github.com/repos/BrettMayson/arma-rs> (`license.spdx_id: GPL-2.0`), <https://crates.io/api/v1/crates/arma-rs/1.12.1> (`license: MIT`), <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/LICENSE>
- **The CI MSRV job is stale.** `.github/workflows/check.yaml` pins an MSRV job at `1.65.0`, but `arma-rs/Cargo.toml` is `edition = "2024"`, which requires Rust 1.85 or newer. The MSRV gate therefore cannot be doing what it claims; treat the real floor as "recent stable".
  Sources: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/.github/workflows/check.yaml>, <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/Cargo.toml>

---

## 2. Does it support the extension callback mechanism (extension → game push)?

**Yes. It is a first-class, documented feature, and it is one of the crate's better-tested paths.**

Arma's push mechanism is: the engine calls the extension's exported `RVExtensionRegisterCallback` at load time, handing it a function pointer; the extension invokes that pointer to fire the SQF-side `ExtensionCallback` mission event handler with `_name`, `_function`, `_data`. **[wiki, indirect]** The wiki gives the C signature as `void CALL_CONVENTION RVExtensionRegisterCallback(RVExtensionCallbackProc* callbackProc)`, and the SQF side as `addMissionEventHandler ["ExtensionCallback", { params ["_name", "_function", "_data"]; ... }]`.
Sources: <https://community.bistudio.com/wiki/Extensions>, <https://community.bistudio.com/wiki/Arma_3:_Mission_Event_Handlers>

arma-rs implements exactly this:

- **The exported entry point is generated for you.** The `#[arma]` attribute macro emits `RVExtensionRegisterCallback` alongside `RVExtensionVersion`, `RVExtension`, `RVExtensionArgs` and `RVExtensionContext`, all as `#[no_mangle] pub unsafe extern "system"` functions. The generated `RVExtensionRegisterCallback` body calls `ext.register_callback(callback); ext.run_callbacks();`.
  Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs-proc/src/lib.rs#L37-L104>
- **The callback type matches the engine's contract:**
  ```rust
  pub type Callback = extern "system" fn(
      *const libc::c_char,
      *const libc::c_char,
      *const libc::c_char,
  ) -> libc::c_int;
  ```
  Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/src/lib.rs#L55-L59>
- **The public API is `Context::callback_data` / `Context::callback_null`**, both of which cite the wiki's `ExtensionCallback` anchor in their own doc comments:
  ```rust
  /// Sends a callback with data into Arma
  /// <https://community.bistudio.com/wiki/Arma_3:_Mission_Event_Handlers#ExtensionCallback>
  pub fn callback_data<V>(&self, name: &str, func: &str, data: V) -> Result<(), CallbackError>
  where V: IntoArma
  ```
  Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/src/context/mod.rs#L69-L93>
- **Delivery is decoupled and back-pressure-aware.** `callback_data` only pushes a `CallbackMessage` onto a `crossbeam-channel`; a dedicated thread spawned by `run_callbacks()` drains it, converts to `CString`, and **retries the engine call every 1 ms until the engine returns a non-negative value**:
  ```rust
  loop {
      if c(name, func, data) >= 0 { break; }
      std::thread::sleep(std::time::Duration::from_millis(1));
  }
  ```
  This matters: it means the extension can fire callbacks from arbitrary worker threads without blocking the command handler, and dropped callbacks (engine queue full → negative return) are retried rather than lost.
  Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/src/lib.rs#L201-L241>
- **Failure mode is explicit**, not a panic: `CallbackError::ChannelClosed`, which itself implements `IntoArma` so it can be returned straight to SQF.
  Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/src/context/mod.rs#L95-L114>
- **The README documents the async push pattern** — add a `ctx: Context` first parameter to a handler, move it into a thread, call `ctx.callback_data(...)`:
  ```rust
  pub fn sleep(ctx: Context, duration: u64, id: String) {
      std::thread::spawn(move || {
          std::thread::sleep(std::time::Duration::from_secs(duration));
          ctx.callback_data("example_timer", "done", Some(id));
      });
  }
  ```
  Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/README.md> ("Callbacks" section)

Relatedly, **call context** (Arma ≥ 2.11) is supported via `CallContext`/`CallContextStackTrace` arguments exposing `caller()`, `source()`, `mission()`, `server()`, `remote_exec_owner()` and `stack_trace()`; since Arma 2.18 arma-rs only requests context from the engine when a handler actually declares a `ArmaCallContext` argument.
Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/README.md> ("Call Context" section)

---

## 3. Windows x64 `.dll` and Linux x64 `.so`; cross-compiling from WSL2

### Does it build both?

**Yes for both, and the crate is genuinely platform-neutral for x64.** The evidence, in order of strength:

1. **All Windows-specific code and dependencies are `cfg`-gated.** In `arma-rs/Cargo.toml`, `winapi ^0.3.9` and `windows ^0.62.2` are declared under `[target.'cfg(windows)'.dependencies]`, and `link_args ^0.6.0` under `cfg(all(target_os="windows", target_arch="x86"))`. Nothing Windows-only is unconditional.
   Sources: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/Cargo.toml>, <https://crates.io/api/v1/crates/arma-rs/1.12.1/dependencies>
2. **The only Windows-specific runtime behaviour is the debug console.** `Extension::handle_call` intercepts the magic function name `"::console"` under `#[cfg(windows)]` to call `AllocConsole()`; there is no `cfg(unix)`/`cfg(target_os = "linux")` special-casing anywhere in the crate (grep over the whole tree returns zero matches for `cfg(unix)`, `target_os = "linux"`, `cfg(not(windows))`).
   Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/src/lib.rs#L170-L180>
3. **`extern "system"` is a no-op on x64.** The generated entry points use `extern "system"`; the Rust Reference states it "is equivalent to `extern "C"` except on Windows x86_32 where it is equivalent to `"stdcall"` for non-variadic functions". So on `x86_64-pc-windows-*` and on `x86_64-unknown-linux-gnu` the ABI is plain C with undecorated `#[no_mangle]` symbols.
   Sources: <https://doc.rust-lang.org/reference/items/external-blocks.html>, <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs-proc/src/lib.rs#L15>
4. **Upstream CI proves the Linux build.** The `test`, `check`, `safety` and `coverage` workflows all run on `ubuntu-latest` (nextest, cargo-hack feature powerset, miri, ASan/LSan against `--target x86_64-unknown-linux-gnu`, llvm-cov), with an additional `os-check` matrix on `macos-latest` and `windows-latest`. docs.rs likewise builds the crate on `x86_64-unknown-linux-gnu`.
   Sources: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/.github/workflows/test.yaml>, <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/.github/workflows/safety.yaml>, <https://docs.rs/arma-rs/latest/arma_rs/>

**Naming, which is a separate concern from building.** **[wiki, indirect]** The engine resolves extension names by file name: for 64-bit Arma the file must be `myExtension_x64.dll` while the SQF name stays `"myExtension"`; Linux uses Shared Object files, and "on Linux the extension name is case-sensitive and should match the name of the `.so` file exactly (minus `.so` part)". arma-rs does nothing about file naming — that is your build script's job (rename/copy the cargo artifact).
Source: <https://community.bistudio.com/wiki/Extensions>

Corroboration from the author's own shipping tooling: HEMTT's in-tree Arma extension is a `crate-type = ["cdylib"]` crate depending on `arma-rs = "1.12.1"`, and its HEMTT project config ships the artefact as `hemtt_comm_x64.dll`.
Sources: <https://github.com/BrettMayson/HEMTT/blob/main/arma/Cargo.toml>, <https://github.com/BrettMayson/HEMTT/blob/main/arma/.hemtt/project.toml>

### Recommended way to cross-compile the Windows x64 `.dll` from a Linux/WSL2 host

**Recommendation: `cargo-xwin` (MSVC ABI, `x86_64-pc-windows-msvc`) as the primary path; `x86_64-pc-windows-gnu` as a viable fallback. Neither is exercised by upstream CI, so validate whichever you choose against a real Arma 3 client/server early.**

Reasoning, from primary sources:

**Case for cargo-xwin / MSVC:**
- It produces artefacts on the same ABI that every other actor in this ecosystem uses. arma-rs' README documents only MSVC toolchains (`rustup toolchain install stable-i686-pc-windows-msvc`), and ACE3 — the largest arma-rs consumer — builds exclusively `i686-pc-windows-msvc` and `x86_64-pc-windows-msvc` on `windows-latest` runners. Choosing MSVC keeps you on the trodden path, which is worth a lot for a project whose failure mode is a game CTD rather than a compiler error.
  Sources: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/README.md> ("Building for x86 (32 Bit)"), <https://github.com/acemod/ACE3/blob/master/.github/workflows/extensions.yml>
- `cargo-xwin` cross-compiles Rust to Windows MSVC targets from non-Windows hosts. Prerequisites: `clang` (a full LLVM install is recommended to avoid issues), `rustup component add llvm-tools` if any dependency has assembly, and optionally `wine` **only** if you want to run tests. It downloads Microsoft's CRT and Windows SDK, and `cargo xwin cache` can pre-seed them for CI/containers. You must accept Microsoft's licence terms. cargo-xwin itself is MIT.
  Source: <https://github.com/rust-cross/cargo-xwin>
- It keeps the 32-bit door open in a way mingw does not (see below), should you ever need an `i686` build.

**Case, and caveats, for `x86_64-pc-windows-gnu` / mingw:**
- The target is **Tier 1 with host tools** in Rust's platform support table ("64-bit MinGW (Windows 10+, Windows Server 2016+)"), the same tier as `x86_64-pc-windows-msvc`. There is no tier-based reason to avoid it.
  Source: <https://doc.rust-lang.org/rustc/platform-support.html>
- arma-rs' `cfg(windows)` dependencies work on gnu targets. `winapi 0.3.9` ships a `winapi-x86_64-pc-windows-gnu` import-library crate, and `windows 0.62.2` resolves through `windows-core` → `windows-link`, whose `windows-targets` dependency graph explicitly carries `windows_x86_64_gnu` for `cfg(all(target_arch = "x86_64", target_env = "gnu", not(target_abi = "llvm"), not(windows_raw_dylib)))`.
  Sources: <https://crates.io/api/v1/crates/windows/0.62.2/dependencies>, <https://crates.io/api/v1/crates/windows-targets/0.53.5/dependencies>
- The extension boundary is pure C — `char*`, `size_t`, `int`, and one function pointer — with no C++ objects, exceptions or allocator ownership crossing it. There is nothing in that interface that an ABI mismatch between mingw-built and MSVC-built code could corrupt, which is why mingw is defensible here even though Arma itself is MSVC-built.
  Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs-proc/src/lib.rs#L56-L114>
- `cross` (Docker/Podman-based) lists `x86_64-pc-windows-gnu` as a supported target with GCC 9.3 and C++ support, and states no Windows-specific caveats; it is the low-friction way to get a mingw sysroot without installing one into WSL2. Requires Docker ≥ 20.10 or Podman ≥ 3.4.
  Source: <https://github.com/cross-rs/cross>
- **Cost of mingw:** you take on any C dependency your extension pulls in. mingw sysroots rarely have prebuilt Windows libraries available, so C-backed crates must be built from source; and mingw-compiled C can introduce runtime DLL dependencies (`libwinpthread-1.dll` and friends) that must then ship alongside your extension. Pure-Rust dependency trees are unaffected. Note that arma-rs consumers routinely do pull C dependencies in — ACE3's extension depends on `arboard` and `git2`.
  Sources: <https://github.com/cross-rs/cross/discussions/1056>, <https://github.com/acemod/ACE3/blob/master/extension/Cargo.toml>

### Known issues specific to Arma extensions

Two are worth recording; only the first is arma-rs-specific and both are source-verified rather than anecdotal.

**(a) 32-bit builds are MSVC-only and cannot be cross-compiled from Linux — by construction.** This is the sharpest finding of section 3. For `i686` Windows targets the `#[arma]` macro emits MSVC linker directives to re-export stdcall-decorated names:

```rust
#[cfg(all(target_os="windows", target_arch="x86"))]
arma_rs::link_args::windows! {
    unsafe {
        raw("/EXPORT:_RVExtensionVersion@8=_safe32_RVExtensionVersion@8");
        raw("/EXPORT:_RVExtension@12=_safe32_RVExtension@12");
        raw("/EXPORT:_RVExtensionArgs@20=_safe32_RVExtensionArgs@20");
        raw("/EXPORT:_RVExtensionRegisterCallback@4=_safe32_RVExtensionRegisterCallback@4");
        raw("/EXPORT:_RVExtensionContext@8=_safe32_RVExtensionContext@8");
    }
}
```

The `link_args` crate's own documentation states it "currently only supports Windows MSVC toolchains" and provides no GNU/MinGW support, so `i686-pc-windows-gnu` is out.

Worse, the `safe32_` symbol prefix that those directives point at is chosen by `#[cfg(all(target_os = "windows", target_arch = "x86"))]` **inside the proc-macro crate**, which is compiled for the *host*, whereas the `link_args` block above is gated on the *target*. The two only agree when the host itself is 32-bit Windows — which is precisely why the README instructs you to install a whole `stable-i686-pc-windows-msvc` **toolchain** rather than merely passing `--target i686-pc-windows-msvc`. On a Linux (or x86_64 Windows) host the prefix resolves to `""` while the `/EXPORT:` directives still reference `_safe32_*` symbols that were never emitted. Conclusion: **do not plan to produce 32-bit Arma extensions from WSL2 with arma-rs.** For x64-only work this is entirely moot (the `cfg` is false and the prefix is empty on both sides).
Sources: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs-proc/src/lib.rs#L23-L54>, <https://docs.rs/link_args/0.6.0/link_args/>, <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/README.md>

**(b) Debug (non-release) builds have a history of crashing the game via call context.** Issue #53, `CTD with CallContext when using non release build`, was open from 2024-10-29 to 2025-11-09 and was fixed by PR #55, `call-context - work in debug`. The fix is in `1.12.0`+. If you ship debug-profile extensions during development, be on ≥ 1.12.0 and be aware this class of bug has bitten before.
Sources: <https://api.github.com/repos/BrettMayson/arma-rs/issues?state=all&per_page=25>, <https://github.com/BrettMayson/arma-rs/commit/55d66462>

A third, adjacent data point: `fix crashing on 2.16` (2024-09-19) and `2.18 Context Features` (#52) show that Arma engine updates have repeatedly required arma-rs changes. Pin your version and re-test after Arma platform updates.
Source: <https://api.github.com/repos/BrettMayson/arma-rs/commits?per_page=40>

---

## 4. Testing story

**Yes — this is arma-rs' strongest dimension, and it is unusually good for a crate of this size.** There are three distinct layers.

**Layer 1 — in-process extension harness (`extension.testing()`).** `Extension::testing()` returns `arma_rs::testing::Extension`, a wrapper that lets `cargo test` drive commands without the game. Its API:

| Method | Purpose |
|---|---|
| `call(function, args) -> (String, c_int)` | invoke a command, get output string + Arma error code |
| `call_with_context(function, args, caller, source, mission, server, remote_exec_owner)` | same, with a synthesised `ArmaCallContext` |
| `callback_handler(handler, timeout) -> Result<T, E>` | drain the callback channel and assert on pushed callbacks |
| `state()` | inspect the extension's persistent state container |
| `context()` | obtain a `Context` for direct use |

Notably the harness uses `const BUFFER_SIZE: libc::size_t = 10240; // The sized used by Arma 3 as of 2021-12-30`, so buffer-overflow behaviour (error code 4) is reproduced faithfully in tests rather than being a production-only surprise. The bespoke `testing::Result` enum has `Ok`/`Err`/`Continue`/`Timeout` variants so a callback handler can consume several events before deciding.
Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/src/testing.rs>

The README documents this directly, including the asynchronous callback case:

```rust
#[test]
fn hello() {
    let extension = init().testing();
    let (output, _) = extension.call("hello:english", None);
    assert_eq!(output, "hello");
}

#[test]
fn sleep_1sec() {
    let extension = Extension::build().group("timer", super::group()).finish().testing();
    let (_, code) = extension.call("timer:sleep", Some(vec!["1".to_string(), "test".to_string()]));
    assert_eq!(code, 0);
    let result = extension.callback_handler(|name, func, data| {
        assert_eq!(name, "timer:sleep");
        assert_eq!(func, "done");
        if let Some(Value::String(s)) = data { Result::Ok(s) } else { Result::Err("Data was not a string".to_string()) }
    }, Duration::from_secs(2));
    assert_eq!(Result::Ok("test".to_string()), result);
}
```

So **the callback path is mockable and assertable in `cargo test`**, with a timeout — which is exactly what you need to test an extension→game push design without a running game.
Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/README.md> ("Testing" section)

**Layer 2 — raw C-interface emulation.** `arma-rs/tests/emulate.rs` (~18 KB) exercises the actual FFI surface: it constructs `extern "system"` callback functions, calls `extension.register_callback(callback)` and `extension.run_callbacks()`, then drives `extension.handle_call` with real `*mut c_char` argument arrays and a fixed output buffer, asserting on the callback stack. It includes adversarial cases such as embedded NUL bytes in callback data (`"dat\0a"`).
Source: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/arma-rs/tests/emulate.rs>

**Layer 3 — CI depth.** Beyond `cargo nextest run --locked --all-features --all-targets` on stable and beta:
- **Miri** (`cargo miri test`) on a pinned nightly;
- **AddressSanitizer and LeakSanitizer** runs against `x86_64-unknown-linux-gnu`;
- **`cargo hack --feature-powerset check --lib --tests`**, so every feature combination compiles;
- **`cargo llvm-cov nextest` uploaded to Codecov** with `fail_ci_if_error: true`;
- clippy on stable + beta, `cargo fmt --check`, `cargo doc --all-features` on nightly;
- **`trybuild` compile-fail tests** for the derive macros, with checked-in `.stderr` expectations (`fail_enum`, `fail_union`, `fail_struct_unit`, `fail_struct_tuple_transparent`, and more).

For a crate whose entire job is `unsafe` FFI across a game-engine boundary, running Miri and ASan/LSan in CI is a materially stronger safety posture than the norm.
Sources: <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/.github/workflows/test.yaml>, <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/.github/workflows/safety.yaml>, <https://github.com/BrettMayson/arma-rs/blob/143f964aceb24a9adaf0be1cccff7f8f80a2d3cc/.github/workflows/check.yaml>

One useful downstream pattern: ACE3 depends on arma-rs with `default-features = false, features = ["extension", "uuid"]` and runs its coverage suite with `cargo tarpaulin --no-default-features`, i.e. the `extension` feature can be switched off so pure business logic tests build without the FFI layer at all.
Sources: <https://github.com/acemod/ACE3/blob/master/extension/Cargo.toml>, <https://github.com/acemod/ACE3/blob/master/.github/workflows/extensions.yml>

---

## 5. Notable production users

GitHub's dependency graph reports **48 dependent repositories** (0 dependent packages), and crates.io reports **0 reverse dependencies** — consistent with arma-rs being consumed by end-product mods rather than by intermediate libraries.
Sources: <https://github.com/BrettMayson/arma-rs/network/dependents>, <https://crates.io/api/v1/crates/arma-rs/reverse_dependencies>

Treat that count with care: a large share of the listed entries are forks of ACE3 (`korrayt/ACE3`, `diwako/ACE3`, `Timi007/ACE3`, `BrettMayson/ACE3`, `ampersand38/ACE3`, `MiszczuZPolski/ACE3`, `gamingzeether/Grunions-ACE3`), and at least one listed repo is a false positive — `uksf/modpack` contains no Rust or arma-rs reference at all. Below are the users I verified by reading their manifests directly.

| Project | Stars | arma-rs version | Evidence |
|---|---|---|---|
| **[acemod/ACE3](https://github.com/acemod/ACE3)** — the dominant Arma 3 realism/feature mod | ~1,098 | **1.12.1** (current) | `extension/Cargo.toml` declares `arma-rs = { version = "1.12.1", default-features = false, features = ["extension", "uuid"] }`; `Cargo.lock` pins `arma-rs 1.12.1` (checksum `4ae6e1d4…`); root `Cargo.toml` workspace member `extension`; dedicated `extensions.yml` workflow builds `ace.dll` for i686 + x86_64 MSVC |
| **[BrettMayson/HEMTT](https://github.com/BrettMayson/HEMTT)** — the de facto modern Arma 3 mod build tool | ~151 | **1.12.1** (current) | `arma/Cargo.toml`: `crate-type = ["cdylib"]`, `arma-rs = "1.12.1"`; `Cargo.lock` pins `arma-rs 1.12.1`; `arma/.hemtt/project.toml` ships `hemtt_comm_x64.dll`; used for the `photoshoot` automation feature (`arma/src/photoshoot.rs`) |
| **[SynixeContractors/Mod](https://github.com/SynixeContractors/Mod)** — community unit mod | — | 1.10.5 | root `Cargo.toml`: `crate-type = ["cdylib"]`, `arma-rs = "1.10.5"`; `Cargo.lock` pins `arma-rs 1.10.5` |

Sources: <https://raw.githubusercontent.com/acemod/ACE3/master/extension/Cargo.toml>, <https://raw.githubusercontent.com/acemod/ACE3/master/Cargo.lock>, <https://raw.githubusercontent.com/acemod/ACE3/master/.github/workflows/extensions.yml>, <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/arma/Cargo.toml>, <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/Cargo.lock>, <https://raw.githubusercontent.com/BrettMayson/HEMTT/main/arma/.hemtt/project.toml>, <https://raw.githubusercontent.com/SynixeContractors/Mod/main/Cargo.toml>

Other names from the dependents list, unverified here but plausible production users: `valmojr/armatak` (28★), `Theseus-Aegis/Mods` (24★), `ArmaForces/Mods` (17★), `BrettMayson/ArmaRadio` (8★), `CreepPork/Beacon` (6★), `itsthedevman/exile_server_manager`, `Dynulo/Arma-Core`, `Inglourious-Basterds-Clan/IBCMod`, `jokoho48/connector`, `Eathox/Arma-CollabEden`.

The two strongest maturity signals are that **ACE3 tracks arma-rs at the very latest version** (a project of ACE3's size does not casually stay current on a dependency it distrusts) and that **an ACE3 core maintainer, PabstMirror, authored two of the last four upstream PRs** (#54, #55) — i.e. the largest consumer contributes fixes back rather than forking away.

---

## Practical risk register for this project

| Risk | Severity | Basis | Mitigation |
|---|---|---|---|
| Licence ambiguity (Cargo.toml MIT vs GPL-2.0 `LICENSE` file) | Medium | §1 | Ask the author to reconcile before distributing binaries; assume GPL-2.0 in the interim |
| Bus factor of one for releases; unreleased fixes sit on `main` for months | Medium | §1 | Vendor or pin a git rev if you need `143f964`; be prepared to fork |
| Arma engine updates have historically broken arma-rs (`2.16` crash, `2.18` context) | Medium | §1, §3(b) | Pin the version, re-run integration tests after every Arma platform update |
| 32-bit Windows builds unavailable from a Linux host | Low (if x64-only) | §3(a) | Commit to x64-only, or keep a Windows build box |
| Neither cross-compilation path is covered by upstream CI | Medium | §3 | Prove the chosen toolchain end-to-end against a real client/server in the first milestone, not the last |
| GitHub Releases feed is stale since 2023 | Low | §1 | Track crates.io, not GitHub releases |

---

## VERDICT

`arma-rs` is the right foundation for a Rust-based Arma 3 extension, and nothing found here argues for building the FFI layer by hand instead. It is maintained — `1.12.1` shipped 2026-01-10, `main` was last pushed 2026-05-21, and there are zero open issues and zero open pull requests — but "maintained" here means bursty, single-maintainer stewardship punctuated by long quiet stretches (a crash report once sat open for twelve months) rather than a steady release train, and the GitHub Releases feed has been dead since 2023, so crates.io is the only reliable version signal. What compensates for the thin maintainer bench is the quality of what is already built and who depends on it: extension-to-game push via `RVExtensionRegisterCallback` is a first-class, documented feature that decouples handlers from the engine through a channel and a retry loop, and — crucially for a test-first project — it is fully mockable inside `cargo test` through `extension.testing()` and `callback_handler(..., timeout)`, on top of raw C-interface emulation tests and a CI matrix that runs Miri, AddressSanitizer, LeakSanitizer and a full feature powerset. ACE3, the largest mod in the ecosystem, tracks arma-rs at the current version and contributes fixes back upstream through its own core maintainer, which is the strongest maturity evidence available. For the specific WSL2 question, both x64 targets are reachable and the crate is genuinely platform-neutral for them, and I would reach for `cargo-xwin` first so that artefacts land on the same MSVC ABI that the README, ACE3's CI and the rest of the ecosystem use, keeping mingw (`x86_64-pc-windows-gnu`, itself Tier 1, ideally via `cross`) as a fallback whose real cost is any C dependency you drag along; note firmly that 32-bit extensions are effectively unbuildable from Linux because arma-rs' `i686` path depends on the MSVC-only `link_args` crate and on a host/target `cfg` coincidence that only holds on a 32-bit Windows toolchain. The two things to do before committing: get the MIT-versus-GPL-2.0 licence contradiction resolved with the author, and prove your chosen cross-compilation toolchain against a real Arma client and Linux server in the first milestone rather than the last, since neither path is covered by upstream CI and nothing in this report was empirically compiled.
