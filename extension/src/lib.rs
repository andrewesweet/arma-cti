//! Phase-0 spike shim: prove the Arma <-> Python daemon RPC path and measure it.
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

fn addr_cell() -> &'static Mutex<String> {
    static ADDR: OnceLock<Mutex<String>> = OnceLock::new();
    ADDR.get_or_init(|| {
        Mutex::new(std::env::var("CTI_DAEMON_ADDR").unwrap_or_else(|_| DEFAULT_ADDR.to_string()))
    })
}

/// Cached connection, opened on first use and dropped after any failure.
fn persistent_cell() -> &'static Mutex<Option<Connection>> {
    static PERSISTENT: OnceLock<Mutex<Option<Connection>>> = OnceLock::new();
    PERSISTENT.get_or_init(|| Mutex::new(None))
}

fn daemon_addr() -> Result<String, String> {
    addr_cell()
        .lock()
        .map(|guard| guard.clone())
        .map_err(|e| format!("addr lock: {e}"))
}

struct Connection {
    reader: BufReader<TcpStream>,
    writer: TcpStream,
}

impl Connection {
    fn open(budget: Budget) -> Result<Self, String> {
        let stream = Self::connect(&daemon_addr()?, budget)?;
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

fn error_json(context: &str) -> String {
    format!(r#"{{"error":"{}"}}"#, context.replace('"', "'"))
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
    let mut guard = persistent_cell()
        .lock()
        .map_err(|e| format!("conn lock: {e}"))?;
    if let Some(conn) = guard.as_mut() {
        match conn.exchange(payload, budget) {
            Ok(reply) => return Ok(reply),
            Err(_) => *guard = None,
        }
    }
    let mut conn = Connection::open(budget)?;
    let reply = conn.exchange(payload, budget)?;
    *guard = Some(conn);
    Ok(reply)
}

/// Point the shim at a different daemon address. Returns the address in force.
pub fn set_addr(addr: String) -> String {
    match addr_cell().lock() {
        Ok(mut guard) => {
            *guard = addr;
            if let Ok(mut conn) = persistent_cell().lock() {
                *conn = None;
            }
            guard.clone()
        }
        Err(e) => error_json(&format!("addr lock: {e}")),
    }
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

    #[test]
    fn ping_needs_no_daemon() {
        let extension = init().testing();
        let (output, code) = extension.call("ping", None);
        assert_eq!(output, "pong");
        assert_eq!(code, 0);
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
