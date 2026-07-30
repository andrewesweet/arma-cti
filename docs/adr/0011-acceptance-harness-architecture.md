# Acceptance harness: Python orchestrator, in-game SQF asserts, verdict through the extension

Decided 2026-07-30, ahead of Phase 3, on the phase-0 spike (docs/spikes/0001-phase0.md) and the prior-art survey (docs/research/arma-automated-testing-prior-art.md). The survey found the architecture already working elsewhere — Relicta's ReSDK boots a version-pinned dedicated server on hosted CI and returns a structured verdict through an extension, verifiably green on real pull requests — so this is adoption of proven precedent, not invention.

The acceptance tier (`just accept <spec-id>` / `just accept-all`) is:

- **A Python orchestrator**, grown from `spike/run.sh`, boots the version-pinned Linux server plus headless client, waits on readiness handshakes rather than sleeps, and owns process supervision and teardown. It synthesises the verdict into the typed failure classes; a missing or malformed verdict is a harness failure, never a pass.
- **Tests run in-game as SQF** against a gtest-style assertion framework — `EXPECT_*` (continue) / `ASSERT_*` (abort test) split, failure counters, `__FILE__`/`__LINE__` in messages — after Relicta's `TestFramework.h`, the best-engineered surveyed precedent.
- **The verdict leaves the game through the shim** to the daemon as structured JSON over the existing TCP channel. Captured stdout is evidence, not the verdict channel (a Linux server writes no RPT file — ADR-0006).
- **Shutdown is remote and deterministic** via the extension channel (HEMTT's `toarma::Control::Exit` pattern), not a PID kill.

Before building the bridge, read HEMTT's `bin/src/controller/`, `arma/src/lib.rs` and `libs/common/src/arma/control.rs` in full — the same crate and author as our build tool drive a live Arma over length-prefixed JSON on loopback there; extending that controller upstream for a dedicated-server target remains an open option.

Rejected as tiers:

- **Bohemia's `-autotest`.** Documented for the client only and unproven on `arma3server`/Linux; the verdict is one pass/fail per whole mission; and there is no success value — pass is silence, indistinguishable from a hang, exactly the conflation the failure-class contract forbids. Revisit only for client-side perceptual automation, where HEMTT's `photoshoot` drives it in production.
- **SQF-VM as a runtime test tier.** Startup is affordable (7–11 ms) but the command set is frozen near Arma 2.16 and it exits 0 on runtime type errors — confirmed empirically — so a harness would have to parse stdout and synthesise its own verdict for an interpreter that cannot run our CBA-era code anyway. HEMTT lints plus `banned_commands` remain the static SQF tier; game-logic unit testing lives in Python (ADR-0004). Reconsider only if a substantial pure-SQF surface with no engine dependency emerges.
