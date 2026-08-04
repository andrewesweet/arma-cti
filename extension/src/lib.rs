//! The Arma <-> Python RPC shim: every `callExtension` the mission makes goes
//! through here to reach the daemon. Built as the Phase-0 spike (issue #2), it
//! has carried production traffic since Phase 1.
//!
//! Domain-agnostic by design (ADR-0005): payloads are opaque strings, the shim
//! owns transport, framing and callback dispatch only.

use std::io::{BufRead, BufReader, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use arma_rs::{Context, Extension, arma};

/// Newline-delimited JSON over TCP loopback (ADR-0005: unix sockets do not
/// cross the WSL2/Windows boundary).
const DEFAULT_ADDR: &str = "127.0.0.1:9099";

/// What one **synchronous** call may cost the engine, end to end.
///
/// ADR-0005: a blocking `callExtension` past 1000 ms trips
/// `EXECUTION_WARNING_TAKES_TOO_LONG` and stalls the server frame for its whole
/// duration, and the synchronous path is reserved for round trips that do not
/// come near that. Measured, they do not: `observe` — the chunkiest of them,
/// both planners inside it — runs 746 µs at p50 and 8.69 ms at its worst
/// (docs/spikes/0002-two-commanders.md). Half the cap is therefore ~57× the
/// slowest call we have ever seen, and it is deliberately *under* the cap
/// rather than at it: a call that gives up must not also trip the engine's
/// warning, or our own failure arrives dressed as an engine complaint.
///
/// A budget for the **call**, not a timeout per syscall (#99). The old 5 s read
/// timeout was five times the stall cap on its own, and a call that reconnects
/// and resends spends its timeout more than once: connect, then read, then —
/// after a failed exchange — connect and read again. Timeouts that are each
/// inside the cap still add up to multiples of it, so the deadline is taken
/// once at the top of the call and every wait under it gets only what is left.
///
/// This is the worst one call can cost, not a cure for calling in a loop. A
/// daemon that stays hung is still asked at the loops' cadence until the
/// consecutive-failure latch (#72) stops asking.
const SYNC_BUDGET: Duration = Duration::from_millis(500);

/// What an **asynchronous** call may cost. Off-frame by construction — the
/// reply comes back through `ExtensionCallback` — so the engine's stall cap
/// does not bind it, and ADR-0005 reserves this path for calls that are
/// genuinely slow (Phase-2 snapshot save/load above all). It gets the 5 s that
/// used to be charged to the synchronous path.
const ASYNC_BUDGET: Duration = Duration::from_secs(5);

/// How long a connect may take before it is a failure rather than a wait.
///
/// One frame-stall budget: ADR-0005 has a blocking `callExtension` past 1000 ms
/// tripping the engine's `EXECUTION_WARNING_TAKES_TOO_LONG` and stalling the
/// frame for its whole duration. Without this the OS default applies — about
/// 21 s on Windows — and `daemon_addrs.sqf` deliberately offers a LAN candidate
/// a joining client may not be able to reach, so an unreachable address freezes
/// the client inside one blocking call, per candidate, per retry (#69).
///
/// Generous for what it has to cover: the daemon is on loopback or on the same
/// LAN, and a handshake either way is single-digit milliseconds. A connect that
/// has not been answered in a second is not slow, it is somewhere else. It is
/// the ceiling on any connect and the binding one on the async path, where the
/// budget above would otherwise allow five seconds of handshake; a synchronous
/// call's own deadline binds tighter still, and each of `init.sqf`'s address
/// candidates is a separate `callExtension` with a budget of its own, so a
/// LAN candidate that cannot be reached costs that call and not the next.
const CONNECT_TIMEOUT: Duration = Duration::from_secs(1);

/// The time one call has left before it must stop rather than block further.
///
/// Taken once, at the top of a call, and consulted before every wait it makes.
#[derive(Clone, Copy)]
struct Budget {
    deadline: Instant,
}

impl Budget {
    fn new(total: Duration) -> Self {
        Self {
            deadline: Instant::now() + total,
        }
    }

    /// What is left, or a refusal once nothing is. Never `Some(0)`: the socket
    /// options below read a zero timeout as "block forever", which is the one
    /// thing a spent budget must not do.
    fn remaining(&self) -> Result<Duration, String> {
        let left = self.deadline.saturating_duration_since(Instant::now());
        if left.is_zero() {
            return Err("budget: the call's time is spent".to_string());
        }
        Ok(left)
    }
}

/// The address the shim is pointed at.
///
/// Poison on this one is recovered rather than propagated (see `addr_guard`).
fn addr_cell() -> &'static Mutex<String> {
    static ADDR: OnceLock<Mutex<String>> = OnceLock::new();
    ADDR.get_or_init(|| {
        Mutex::new(std::env::var("CTI_DAEMON_ADDR").unwrap_or_else(|_| DEFAULT_ADDR.to_string()))
    })
}

/// The address lock, poison and all.
///
/// A poisoned mutex means some thread panicked while holding it, and the
/// question is always whether the value it guards can be half-written. Here it
/// cannot: the address is a whole `String` replaced in a single assignment, so
/// there is no torn state for poison to warn about. Propagating it would take
/// the shim's transport down for the life of the process because of a panic
/// somewhere else — and, before #93, would have done so by handing `set_addr`'s
/// caller an `{"error":...}` where its documentation promises an address, which
/// is a thing no caller can tell apart from an address it did not expect.
///
/// The poison is cleared as well as recovered, so a panic somewhere else leaves
/// no lasting mark on a lock it told us nothing about. The connection lock is
/// recovered too but not for the same reason — see `connection_guard`.
fn addr_guard() -> std::sync::MutexGuard<'static, String> {
    let cell = addr_cell();
    match cell.lock() {
        Ok(guard) => guard,
        Err(poisoned) => {
            cell.clear_poison();
            poisoned.into_inner()
        }
    }
}

/// Cached connection, opened on first use and dropped after any failure.
fn persistent_cell() -> &'static Mutex<Option<Connection>> {
    static PERSISTENT: OnceLock<Mutex<Option<Connection>>> = OnceLock::new();
    PERSISTENT.get_or_init(|| Mutex::new(None))
}

/// The connection lock, poison and all.
///
/// Poison here means something the address lock's does not: a panic mid exchange
/// can leave a socket with half a line written down it, so the cached connection
/// really may be unusable. What follows from that is what this file already does
/// after *any* failed exchange — drop the connection and open a new one — so the
/// guard is recovered, emptied, and the poison cleared.
///
/// Propagating it instead would brick the keepalive path for the life of the
/// process over one panic, and the process is an Arma server: every synchronous
/// call goes through here, and nothing short of restarting the game would get
/// them back.
fn connection_guard() -> std::sync::MutexGuard<'static, Option<Connection>> {
    let cell = persistent_cell();
    match cell.lock() {
        Ok(guard) => guard,
        Err(poisoned) => {
            let mut guard = poisoned.into_inner();
            *guard = None;
            cell.clear_poison();
            guard
        }
    }
}

fn daemon_addr() -> String {
    addr_guard().clone()
}

struct Connection {
    reader: BufReader<TcpStream>,
    writer: TcpStream,
}

impl Connection {
    fn open(budget: Budget) -> Result<Self, String> {
        let stream = Self::connect(&daemon_addr(), budget)?;
        stream
            .set_nodelay(true)
            .map_err(|e| format!("nodelay: {e}"))?;
        let writer = stream.try_clone().map_err(|e| format!("clone: {e}"))?;
        let conn = Self {
            reader: BufReader::new(stream),
            writer,
        };
        conn.arm(budget)?;
        Ok(conn)
    }

    /// Point the socket's own timeouts at what the call has left.
    ///
    /// Re-armed before every exchange rather than set once at open: a reused
    /// connection outlives the call that opened it, and the budget that matters
    /// is the caller's, now.
    fn arm(&self, budget: Budget) -> Result<(), String> {
        let left = budget.remaining()?;
        self.reader
            .get_ref()
            .set_read_timeout(Some(left))
            .map_err(|e| format!("read timeout: {e}"))?;
        self.writer
            .set_write_timeout(Some(left))
            .map_err(|e| format!("write timeout: {e}"))
    }

    /// Connect under our own timeout rather than the OS's.
    ///
    /// `TcpStream::connect` takes a host string and applies no deadline;
    /// `connect_timeout` takes one resolved address, so the candidates are
    /// walked here. An address that resolves to several is tried in turn, each
    /// under whichever is smaller of the connect timeout and what the call has
    /// left — so a list of unreachable candidates costs the budget once
    /// between them, not once each.
    fn connect(addr: &str, budget: Budget) -> Result<TcpStream, String> {
        let candidates = addr
            .to_socket_addrs()
            .map_err(|e| format!("connect: resolving {addr}: {e}"))?;
        let mut refusal = format!("connect: {addr} resolved to no address");
        for candidate in candidates {
            let allowed = budget.remaining()?.min(CONNECT_TIMEOUT);
            match TcpStream::connect_timeout(&candidate, allowed) {
                Ok(stream) => return Ok(stream),
                Err(e) => refusal = format!("connect: {candidate}: {e}"),
            }
        }
        Err(refusal)
    }

    fn exchange(&mut self, payload: &str, budget: Budget) -> Result<String, String> {
        self.arm(budget)?;
        self.writer
            .write_all(payload.as_bytes())
            .and_then(|()| self.writer.write_all(b"\n"))
            .and_then(|()| self.writer.flush())
            .map_err(|e| format!("write: {e}"))?;
        let mut line = String::new();
        let read = self
            .reader
            .read_line(&mut line)
            .map_err(|e| format!("read: {e}"))?;
        if read == 0 {
            return Err("read: daemon closed the connection".to_string());
        }
        Ok(line.trim_end_matches(['\r', '\n']).to_string())
    }
}

/// Escape a string so it is legal inside a JSON string literal (RFC 8259 §7:
/// `"`, `\`, and everything below U+0020 must be escaped; nothing else must).
///
/// Written out rather than pulled in with `serde_json`, because this is the only
/// JSON the shim ever *produces* and a dependency for one function on the error
/// path is not worth the build (ADR-0005 keeps the shim thin). Before #93 the
/// only escape was `"` rewritten to `'`, which is lossy where it works and
/// silent where it does not: a detail carrying a `\` — a Windows path out of an
/// `io::Error`, most plausibly — or a newline out of a daemon reply produced a
/// line that is not JSON at all, and the receiver would have failed to parse an
/// error message rather than reporting it.
fn escape_json(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    for c in raw.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            // The remaining C0 controls have no short form; \u form is required
            // for them and permitted for nothing else here.
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

fn error_json(context: &str) -> String {
    format!(r#"{{"error":"{}"}}"#, escape_json(context))
}

/// One connection per call: the worst-case number, TCP handshake included.
///
/// Takes no shared lock, which is why the async path uses it (ADR-0005).
fn round_trip_fresh(payload: &str, budget: Budget) -> Result<String, String> {
    Connection::open(budget)?.exchange(payload, budget)
}

/// Reuse the cached connection; reconnect once on failure.
///
/// The resend is at-least-once and deliberately so: an exchange that failed
/// after the write may already have been carried out at the far end, and the
/// shim cannot tell that from a request that never arrived. Dropping the retry
/// would trade a duplicate for a lost Command, and deciding here which verbs
/// are safe to resend would put the domain inside a shim ADR-0005 keeps
/// domain-agnostic. So the payload goes back **byte for byte**, request id
/// included, and the daemon answers a line it has already answered from its
/// record rather than carrying it out again (ADR-0034). Anything that changes
/// the resent bytes breaks that, which is what the test below pins.
///
/// Every caller in the world queues here, on one mutex over one connection
/// (#99). That is tolerable only because the budget bounds how long the lock
/// can be held: a stalled poll now blocks a human Commander's click for at most
/// one `SYNC_BUDGET`, not for as long as the daemon cares to be silent. Two
/// connections would not have bought more — the daemon answers one request at a
/// time (#98), so the queue moves rather than disappears — while the call that
/// really could hold this for seconds, the async one, no longer takes the lock
/// at all.
fn round_trip_persistent(payload: &str, budget: Budget) -> Result<String, String> {
    let mut guard = connection_guard();
    // The cached connection's failure is kept, not discarded (#162): when the
    // reconnect also fails, the caller gets both halves of the story — what
    // the retry could not do, and what the cached socket died of first. One
    // error where two things went wrong sends the reader after the wrong one.
    let mut cached_failure: Option<String> = None;
    if let Some(conn) = guard.as_mut() {
        match conn.exchange(payload, budget) {
            Ok(reply) => return Ok(reply),
            Err(e) => {
                *guard = None;
                cached_failure = Some(e);
            }
        }
    }
    let report = |retry_failure: String| match &cached_failure {
        Some(first) => {
            format!("{retry_failure} (after the cached connection failed: {first})")
        }
        None => retry_failure,
    };
    let mut conn = Connection::open(budget).map_err(&report)?;
    let reply = conn.exchange(payload, budget).map_err(&report)?;
    *guard = Some(conn);
    Ok(reply)
}

/// Point the shim at a different daemon address. Returns the address in force —
/// always an address, never an error (#93): there is no failure left for this
/// call to have, because both locks it takes recover from poison rather than
/// propagate it (`addr_guard` and `connection_guard`).
pub fn set_addr(addr: String) -> String {
    // The address lock is released before the connection lock is taken, and the
    // scope is what does it. `round_trip_persistent` holds the connection while
    // `Connection::open` reaches for the address, so holding them the other way
    // round here — which this did until #93 — is a lock-order inversion, and the
    // two orders meeting deadlock an Arma server on its own main thread. Nothing
    // needs them both at once: retargeting is a write to one followed by a write
    // to the other.
    let in_force = {
        let mut guard = addr_guard();
        *guard = addr;
        guard.clone()
    };
    // The cached socket is pointed at the *old* daemon, so retargeting must drop
    // it unconditionally. Skipping the drop on a poisoned lock, as this did
    // before #93, would leave the shim answering from the daemon it was just
    // moved off — and dropping is the response to that poison anyway.
    *connection_guard() = None;
    in_force
}

/// Pure FFI cost: no I/O at all.
pub fn ping() -> &'static str {
    "pong"
}

/// Blocking round trip on a fresh connection, reply returned to `callExtension`.
pub fn rpc(payload: String) -> String {
    round_trip_fresh(&payload, Budget::new(SYNC_BUDGET)).unwrap_or_else(|e| error_json(&e))
}

/// Blocking round trip on the reused connection.
pub fn rpc_keepalive(payload: String) -> String {
    round_trip_persistent(&payload, Budget::new(SYNC_BUDGET)).unwrap_or_else(|e| error_json(&e))
}

/// Time `count` round trips inside the extension and return the distribution as
/// JSON. Keeps the measurement off SQF's frame-quantised clock; `keepalive`
/// selects the reused connection over a fresh one per call.
///
/// The payload comes from the caller rather than being built here. The shim is
/// domain-agnostic (ADR-0005) — it has no business knowing what the daemon
/// accepts — and a payload the daemon answers with an error would time the
/// round trip of a request nothing understood.
pub fn bench(count: u32, keepalive: bool, payload: String) -> String {
    if count == 0 {
        return error_json("count must be > 0");
    }
    let mut micros: Vec<u128> = Vec::with_capacity(count as usize);
    for i in 0..count {
        let started = std::time::Instant::now();
        let outcome = if keepalive {
            round_trip_persistent(&payload, Budget::new(SYNC_BUDGET))
        } else {
            round_trip_fresh(&payload, Budget::new(SYNC_BUDGET))
        };

        let elapsed = started.elapsed().as_micros();
        match outcome {
            Ok(_) => micros.push(elapsed),
            Err(e) => return error_json(&format!("call {i}: {e}")),
        }
    }
    micros.sort_unstable();
    let sum: u128 = micros.iter().sum();
    let len = micros.len();
    format!(
        r#"{{"n":{},"keepalive":{},"min_us":{},"p50_us":{},"p95_us":{},"max_us":{},"mean_us":{}}}"#,
        len,
        keepalive,
        micros[0],
        micros[len / 2],
        micros[(len * 95 / 100).min(len - 1)],
        micros[len - 1],
        sum / len as u128,
    )
}

/// Non-blocking round trip; reply arrives on the `ExtensionCallback` event handler.
///
/// On a connection of its own, which ADR-0005 requires of this path before it
/// carries production work and #99 found it was not doing: sharing the
/// persistent connection meant one slow async call held the mutex every
/// synchronous judgement queues on — the effect pump, the presence report, the
/// Commander view and the human's own Command through `fn_portGateway` — so a
/// path defined as slow would have been the thing stalling the frame. A fresh
/// connection per call also needs no resend: there is no cached socket to have
/// gone stale under it.
pub fn rpc_async(ctx: Context, id: String, payload: String) {
    std::thread::spawn(move || {
        let reply = round_trip_fresh(&payload, Budget::new(ASYNC_BUDGET))
            .unwrap_or_else(|e| error_json(&e));
        // Dropped deliberately, and it is the only dropped error in this file.
        // `callback_data` has exactly one failure, `CallbackError::ChannelClosed`
        // (arma-rs 1.12.1), which means the engine is no longer collecting
        // callbacks — the extension is being unloaded or the process is on its
        // way down. The only route this thread has back to anyone who could act
        // is the channel that just closed, so there is nothing to report the
        // failure *to*: logging it would be writing to a world that has stopped
        // reading, and returning it would be returning to a thread nobody joins.
        let _ = ctx.callback_data("cti_shim", &id, reply);
    });
}

#[arma]
fn init() -> Extension {
    Extension::build()
        // Without this, `"cti_shim" callExtension "ping"` returns "" — only the
        // array form `callExtension ["ping", []]` reaches a handler.
        .allow_no_args()
        .version(env!("CARGO_PKG_VERSION").to_string())
        .command("ping", ping)
        .command("addr", set_addr)
        .command("rpc", rpc)
        .command("rpc_keepalive", rpc_keepalive)
        .command("rpc_async", rpc_async)
        .command("bench", bench)
        .finish()
}

#[cfg(test)]
mod tests {
    use std::io::{BufRead, BufReader, Write};
    use std::net::TcpListener;
    use std::sync::{Arc, Mutex, MutexGuard, OnceLock, mpsc};
    use std::time::Duration;

    use super::*;

    /// The shim's connection and address are process-global, so tests that
    /// retarget it must not overlap.
    fn serialise() -> MutexGuard<'static, ()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        let lock = LOCK.get_or_init(|| Mutex::new(()));
        lock.lock().unwrap_or_else(|e| e.into_inner())
    }

    /// Uppercasing echo server on an ephemeral port.
    fn spawn_stub() -> String {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let addr = listener.local_addr().expect("addr").to_string();
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(stream) = stream else { continue };
                std::thread::spawn(move || {
                    let mut writer = stream.try_clone().expect("clone");
                    let mut reader = BufReader::new(stream);
                    let mut line = String::new();
                    while reader.read_line(&mut line).unwrap_or(0) > 0 {
                        let reply = format!("{}\n", line.trim_end().to_uppercase());
                        if writer.write_all(reply.as_bytes()).is_err() {
                            break;
                        }
                        line.clear();
                    }
                });
            }
        });
        addr
    }

    /// A daemon that is hung rather than dead: it accepts the connection, says
    /// who called, and then never answers. The connection is held open so the
    /// caller waits on its read instead of being told the far end is gone —
    /// the shape #99 is about, and the one an OS-level refusal cannot produce.
    fn spawn_hanging_stub() -> (String, mpsc::Receiver<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let addr = listener.local_addr().expect("addr").to_string();
        let (announce, arrivals) = mpsc::channel();
        std::thread::spawn(move || {
            let mut held = Vec::new();
            for stream in listener.incoming() {
                let Ok(stream) = stream else { continue };
                held.push(stream);
                if announce.send(()).is_err() {
                    break;
                }
            }
        });
        (addr, arrivals)
    }

    /// Echo server that also keeps every line it was sent, so a test can assert
    /// what actually went over the wire rather than what it hoped went.
    fn spawn_recording_stub() -> (String, Arc<Mutex<Vec<String>>>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let addr = listener.local_addr().expect("addr").to_string();
        let received = Arc::new(Mutex::new(Vec::new()));
        let sink = Arc::clone(&received);
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(stream) = stream else { continue };
                let sink = Arc::clone(&sink);
                std::thread::spawn(move || {
                    let mut writer = stream.try_clone().expect("clone");
                    let mut reader = BufReader::new(stream);
                    let mut line = String::new();
                    while reader.read_line(&mut line).unwrap_or(0) > 0 {
                        sink.lock()
                            .unwrap_or_else(|e| e.into_inner())
                            .push(line.trim_end().to_string());
                        if writer.write_all(b"{}\n").is_err() {
                            break;
                        }
                        line.clear();
                    }
                });
            }
        });
        (addr, received)
    }

    /// Answers the first line on a connection, then takes the second, records
    /// it, and dies without answering. That is the exact shape of the #69
    /// hazard: the request arrived and was acted on, and the caller learns
    /// nothing except that its read failed.
    fn spawn_acts_then_dies_stub() -> (String, Arc<Mutex<Vec<String>>>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let addr = listener.local_addr().expect("addr").to_string();
        let received = Arc::new(Mutex::new(Vec::new()));
        let sink = Arc::clone(&received);
        std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(stream) = stream else { continue };
                let sink = Arc::clone(&sink);
                std::thread::spawn(move || {
                    let mut writer = stream.try_clone().expect("clone");
                    let mut reader = BufReader::new(stream);
                    let mut line = String::new();
                    let mut taken = 0;
                    while reader.read_line(&mut line).unwrap_or(0) > 0 {
                        sink.lock()
                            .unwrap_or_else(|e| e.into_inner())
                            .push(line.trim_end().to_string());
                        taken += 1;
                        // Acted on, then gone: the caller's read finds a closed
                        // connection and cannot tell that from never arriving.
                        if taken > 1 {
                            break;
                        }
                        if writer.write_all(b"{\"status\":\"ok\"}\n").is_err() {
                            break;
                        }
                        let _ = writer.flush();
                        line.clear();
                    }
                });
            }
        });
        (addr, received)
    }

    /// Answers one line on one connection, then closes the connection and the
    /// listener and says so. The next exchange fails on the cached socket and
    /// the reconnect is refused — the two-failures case, staged.
    fn spawn_answers_once_then_quits() -> (String, mpsc::Receiver<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let addr = listener.local_addr().expect("addr").to_string();
        let (gone, closed) = mpsc::channel();
        std::thread::spawn(move || {
            let (stream, _) = listener.accept().expect("accept");
            let mut writer = stream.try_clone().expect("clone");
            let mut reader = BufReader::new(stream);
            let mut line = String::new();
            let _ = reader.read_line(&mut line);
            let _ = writer.write_all(b"ok\n");
            drop(reader);
            drop(writer);
            drop(listener);
            let _ = gone.send(());
        });
        (addr, closed)
    }

    #[test]
    fn ping_needs_no_daemon() {
        let extension = init().testing();
        let (output, code) = extension.call("ping", None);
        assert_eq!(output, "pong");
        assert_eq!(code, 0);
    }

    /// Panic while holding `lock`, so the mutex is poisoned from here on, with
    /// the panic message swallowed so a deliberate panic does not read as a
    /// failing test. Poison is process-wide, so the next caller of the lock is
    /// what has to survive it — which is exactly the claim under test, and why
    /// the shim's guards clear the poison once they have dealt with it.
    fn poison<T: Send + 'static>(lock: &'static Mutex<T>) {
        let previous = std::panic::take_hook();
        std::panic::set_hook(Box::new(|_| {}));
        let outcome = std::panic::catch_unwind(|| {
            let _held = lock.lock().unwrap_or_else(|e| e.into_inner());
            panic!("poisoning deliberately");
        });
        std::panic::set_hook(previous);
        assert!(outcome.is_err(), "the poisoning panic did not happen");
        assert!(lock.is_poisoned(), "the lock came out unpoisoned");
    }

    #[test]
    fn error_json_survives_a_detail_that_is_not_plain_text() {
        // The old escape rewrote `"` to `'` and left everything else alone, so a
        // backslash or a control character produced a line that is not JSON.
        // Windows paths inside an io::Error are the realistic source of the
        // first, a daemon reply echoed into a message the source of the second.
        assert_eq!(
            error_json(r#"read: C:\Program Files\a "quoted" name"#),
            r#"{"error":"read: C:\\Program Files\\a \"quoted\" name"}"#
        );
        assert_eq!(
            error_json("write: line one\nline two\ttabbed\r\u{7}"),
            r#"{"error":"write: line one\nline two\ttabbed\r\u0007"}"#
        );
    }

    #[test]
    fn error_json_leaves_ordinary_text_alone() {
        // Escaping beyond what RFC 8259 requires would be its own corruption:
        // the reader gets the message back, not a version of it.
        assert_eq!(
            error_json("connect: 127.0.0.1:9099: refused (µs, ≤)"),
            r#"{"error":"connect: 127.0.0.1:9099: refused (µs, ≤)"}"#
        );
    }

    #[test]
    fn set_addr_answers_an_address_even_when_the_lock_is_poisoned() {
        // #93: the doc promises "the address in force" and the old code answered
        // `{"error":...}` on poison — a caller could not tell the two apart. The
        // guarded value is a whole String replaced in one assignment, so poison
        // here reports a panic elsewhere and nothing about this address.
        let _guard = serialise();
        poison(addr_cell());
        let answer = set_addr("127.0.0.1:9042".to_string());
        assert_eq!(answer, "127.0.0.1:9042", "not an address: {answer}");
        assert_eq!(daemon_addr(), "127.0.0.1:9042");
        assert!(
            !addr_cell().is_poisoned(),
            "the poison outlived the call that dealt with it"
        );
    }

    #[test]
    fn a_poisoned_connection_does_not_brick_the_keepalive_path() {
        // Every synchronous call queues on this one lock, so propagating its
        // poison would take the shim's whole synchronous path down for the life
        // of an Arma server. The response is the file's usual one — drop the
        // suspect socket and open another.
        let _guard = serialise();
        let addr = spawn_stub();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec![addr]));

        poison(persistent_cell());
        let (output, code) = extension.call("rpc_keepalive", Some(vec!["after".to_string()]));
        assert_eq!(code, 0);
        assert_eq!(output, "AFTER", "unexpected output: {output}");
        assert!(!persistent_cell().is_poisoned());
    }

    #[test]
    fn retargeting_drops_the_cached_connection_even_when_it_is_poisoned() {
        // A poisoned connection cell used to make `set_addr` skip the drop, which
        // leaves the shim answering over a socket to the daemon it was just moved
        // off. Dropping is the response to that poison, not a casualty of it.
        let _guard = serialise();
        let (first, seen_by_first) = spawn_recording_stub();
        let (second, seen_by_second) = spawn_recording_stub();
        let extension = init().testing();

        let _ = extension.call("addr", Some(vec![first]));
        let (_, code) = extension.call("rpc_keepalive", Some(vec!["to-first".to_string()]));
        assert_eq!(code, 0);

        poison(persistent_cell());
        let _ = extension.call("addr", Some(vec![second]));
        let (_, code) = extension.call("rpc_keepalive", Some(vec!["to-second".to_string()]));
        assert_eq!(code, 0);

        assert_eq!(
            *seen_by_first.lock().unwrap_or_else(|e| e.into_inner()),
            vec!["to-first".to_string()],
            "the old daemon was still being talked to after retargeting"
        );
        assert_eq!(
            *seen_by_second.lock().unwrap_or_else(|e| e.into_inner()),
            vec!["to-second".to_string()]
        );
        assert!(!persistent_cell().is_poisoned());
    }

    #[test]
    fn rpc_reports_a_dead_daemon_instead_of_panicking() {
        let _guard = serialise();
        // Port 1 is privileged and unbound: connect must fail, not panic.
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec!["127.0.0.1:1".to_string()]));
        let (output, code) = extension.call("rpc", Some(vec!["{}".to_string()]));
        assert_eq!(
            code, 0,
            "a transport failure is a payload, not an Arma error"
        );
        assert!(output.contains("\"error\""), "unexpected output: {output}");
    }

    #[test]
    fn rpc_keepalive_reuses_one_connection() {
        let _guard = serialise();
        let addr = spawn_stub();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec![addr]));
        for expected in ["ONE", "TWO", "THREE"] {
            let (output, code) =
                extension.call("rpc_keepalive", Some(vec![expected.to_lowercase()]));
            assert_eq!(code, 0);
            assert_eq!(output, expected);
        }
    }

    #[test]
    fn bench_reports_a_distribution() {
        let _guard = serialise();
        let addr = spawn_stub();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec![addr]));
        let (output, code) = extension.call(
            "bench",
            Some(vec![
                "5".to_string(),
                "true".to_string(),
                "ping".to_string(),
            ]),
        );
        assert_eq!(code, 0);
        assert!(output.contains(r#""n":5"#), "unexpected output: {output}");
        assert!(!output.contains("error"), "unexpected output: {output}");
    }

    #[test]
    fn bench_sends_the_callers_payload_verbatim() {
        // The shim must not decide what the daemon is asked; it only times the
        // asking (ADR-0005: payloads are opaque). Before this, `bench` built its
        // own payload, and the daemon answered every one of them with an error.
        let _guard = serialise();
        let (addr, received) = spawn_recording_stub();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec![addr]));
        let payload = r#"{"id":"bench","verb":"ping"}"#;
        let (_, code) = extension.call(
            "bench",
            Some(vec![
                "3".to_string(),
                "true".to_string(),
                payload.to_string(),
            ]),
        );
        assert_eq!(code, 0);
        let seen = received.lock().unwrap_or_else(|e| e.into_inner());
        assert_eq!(*seen, vec![payload.to_string(); 3]);
    }

    #[test]
    fn a_resend_after_a_failed_exchange_carries_the_identical_request() {
        // #69: the retry cannot be made safe here, only made deduplicable. The
        // daemon refuses a line it has already answered (ADR-0034), and that
        // only works if the resent line is the one it recorded — same id, same
        // payload, byte for byte. A shim that stamped a fresh id per attempt
        // would defeat the receiver silently, so the bytes are the assertion.
        let _guard = serialise();
        let (addr, received) = spawn_acts_then_dies_stub();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec![addr]));

        let first = r#"{"id":"cmd-1","verb":"ping"}"#;
        let (_, code) = extension.call("rpc_keepalive", Some(vec![first.to_string()]));
        assert_eq!(code, 0);

        // This one is taken by the far end and never answered. The shim cannot
        // tell that from a request that never arrived, so it reconnects and
        // sends the same bytes again — and the far end sees it twice.
        let second = r#"{"id":"cmd-2","verb":"command"}"#;
        let (output, code) = extension.call("rpc_keepalive", Some(vec![second.to_string()]));
        assert_eq!(code, 0);
        assert_eq!(output, r#"{"status":"ok"}"#);

        let seen = received.lock().unwrap_or_else(|e| e.into_inner());
        assert_eq!(
            *seen,
            vec![first.to_string(), second.to_string(), second.to_string()],
            "the resend must be the same request, not a new one"
        );
    }

    #[test]
    fn a_failed_retry_reports_the_cached_connections_failure_too() {
        // #162: the first exchange's error used to be discarded on the spot,
        // so a retry that also failed reported only its own connect error and
        // the reader lost what the cached connection actually died of.
        let _guard = serialise();
        let (addr, closed) = spawn_answers_once_then_quits();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec![addr]));

        let (output, code) = extension.call("rpc_keepalive", Some(vec!["one".to_string()]));
        assert_eq!(code, 0);
        assert_eq!(output, "ok", "unexpected output: {output}");

        closed
            .recv_timeout(Duration::from_secs(5))
            .expect("the stub never closed");
        let (output, code) = extension.call("rpc_keepalive", Some(vec!["two".to_string()]));
        assert_eq!(code, 0);
        assert!(output.contains("\"error\""), "unexpected output: {output}");
        assert!(
            output.contains("after the cached connection failed"),
            "the cached connection's failure was discarded: {output}"
        );
    }

    #[test]
    fn connect_gives_up_inside_the_shims_own_timeout() {
        // TEST-NET-1 (RFC 5737) is documentation space: nothing routes it, so a
        // connect either blackholes until a timeout fires or is refused by the
        // local stack. Without `connect_timeout` the first case waits on the OS
        // — about 21 s on Windows — inside a blocking `callExtension`.
        let _guard = serialise();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec!["192.0.2.1:9099".to_string()]));

        let started = std::time::Instant::now();
        let (output, code) = extension.call("rpc", Some(vec!["{}".to_string()]));
        let elapsed = started.elapsed();

        assert_eq!(code, 0);
        assert!(output.contains("\"error\""), "unexpected output: {output}");
        assert!(
            elapsed < CONNECT_TIMEOUT * 3,
            "connect took {elapsed:?}, past the shim's own budget"
        );
    }

    #[test]
    fn the_synchronous_budget_never_exceeds_the_engines_stall_cap() {
        // ADR-0005: a blocking `callExtension` past 1000 ms trips
        // EXECUTION_WARNING_TAKES_TOO_LONG and stalls the frame for as long as
        // it runs. Whatever else is tuned here, a synchronous call has to give
        // up before that rather than at it.
        assert!(SYNC_BUDGET < Duration::from_secs(1));
        assert!(CONNECT_TIMEOUT <= Duration::from_secs(1));
    }

    #[test]
    fn a_hung_daemon_costs_the_synchronous_path_one_budget_not_several() {
        // The whole call is deadlined, not each syscall inside it: this one
        // reads nothing, then reconnects and resends, and the two waits still
        // have to share a single budget. At the old 5 s per read it was ten
        // seconds of frozen frame per call, for as long as the daemon stayed
        // hung.
        let _guard = serialise();
        let (addr, _arrivals) = spawn_hanging_stub();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec![addr]));

        let started = Instant::now();
        let (output, code) = extension.call("rpc_keepalive", Some(vec!["{}".to_string()]));
        let elapsed = started.elapsed();

        assert_eq!(
            code, 0,
            "a transport failure is a payload, not an Arma error"
        );
        assert!(output.contains("\"error\""), "unexpected output: {output}");
        assert!(
            elapsed < SYNC_BUDGET * 2,
            "one call spent {elapsed:?}, more than its budget of {SYNC_BUDGET:?}"
        );
        assert!(
            elapsed >= SYNC_BUDGET / 2,
            "gave up in {elapsed:?}, too early to have been the budget doing it"
        );
    }

    #[test]
    fn the_async_path_never_takes_the_synchronous_paths_connection() {
        // ADR-0005 requires this path to hold its own connection before it
        // carries production work: everything a player does synchronously —
        // their own Command through the gateway included — queues on the
        // persistent connection's mutex, and this path is the one defined as
        // slow. Asserted while an async call is in flight against a daemon that
        // will never answer it, so a shared mutex would be held right now.
        let _guard = serialise();
        let (addr, arrivals) = spawn_hanging_stub();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec![addr]));

        let (_, code) = extension.call(
            "rpc_async",
            Some(vec!["job-slow".to_string(), "hello".to_string()]),
        );
        assert_eq!(code, 0);
        arrivals
            .recv_timeout(Duration::from_secs(5))
            .expect("the async call never reached the daemon");

        assert!(
            persistent_cell().try_lock().is_ok(),
            "a slow async call is holding the connection every synchronous call queues on"
        );
    }

    #[test]
    fn rpc_async_delivers_the_reply_through_extensioncallback() {
        let _guard = serialise();
        let addr = spawn_stub();
        let extension = init().testing();
        let _ = extension.call("addr", Some(vec![addr]));
        let (_, code) = extension.call(
            "rpc_async",
            Some(vec!["job1".to_string(), "hello".to_string()]),
        );
        assert_eq!(code, 0);

        let result = extension.callback_handler(
            |name, func, data| {
                assert_eq!(name, "cti_shim");
                assert_eq!(func, "job1");
                match data {
                    Some(arma_rs::Value::String(s)) => arma_rs::testing::Result::Ok(s),
                    other => arma_rs::testing::Result::Err(format!("unexpected data: {other:?}")),
                }
            },
            Duration::from_secs(5),
        );
        assert_eq!(
            arma_rs::testing::Result::Ok("HELLO".to_string()),
            result,
            "callback did not carry the daemon reply"
        );
    }
}
