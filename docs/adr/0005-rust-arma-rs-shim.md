# Extension shim in Rust using arma-rs

The Arma-to-daemon shim is written in Rust on the `arma-rs` crate (extension ABI, argument handling, ExtensionCallback, single codebase for .dll and .so, native `cargo test`), replacing the design doc's C++/Catch2 choice. Transport is TCP on 127.0.0.1 to the daemon (unix sockets do not cross the WSL2/Windows boundary), JSON payloads for MVP. The shim stays domain-agnostic: transport, framing, retry, idempotent delivery, callback dispatch — payloads are opaque, so domain changes never require a shim rebuild.
