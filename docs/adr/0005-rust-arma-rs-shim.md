# Extension shim in Rust using arma-rs

The Arma-to-daemon shim is written in Rust on the `arma-rs` crate (extension ABI, argument handling, ExtensionCallback, single codebase for .dll and .so, native `cargo test`), replacing the design doc's C++/Catch2 choice. Transport is TCP on 127.0.0.1 to the daemon (unix sockets do not cross the WSL2/Windows boundary), JSON payloads for MVP. The shim stays domain-agnostic: transport, framing, retry, idempotent delivery, callback dispatch — payloads are opaque, so domain changes never require a shim rebuild.

Amended 2026-07-30 (phase-0 measurements, docs/spikes/0001-phase0.md §4): the shim holds one persistent TCP connection and reconnects on failure. Reusing the connection is ~3× faster than connecting per call (0.45–0.65 ms vs 1.34–1.62 ms p50 round trip), and the persistent connection is where retry and idempotent delivery live. Per-call connections are rejected.
