//! Phase-0 spike shim: prove the Arma <-> Python daemon RPC path and measure it.
//!
//! Domain-agnostic by design (ADR-0005): payloads are opaque strings, the shim
//! owns transport, framing and callback dispatch only.

use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

use arma_rs::{Context, Extension, arma};

/// Newline-delimited JSON over TCP loopback (ADR-0005: unix sockets do not
/// cross the WSL2/Windows boundary).
const DEFAULT_ADDR: &str = "127.0.0.1:9099";
const IO_TIMEOUT: Duration = Duration::from_secs(5);

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
    fn open() -> Result<Self, String> {
        let stream = TcpStream::connect(daemon_addr()?).map_err(|e| format!("connect: {e}"))?;
        stream
            .set_nodelay(true)
            .map_err(|e| format!("nodelay: {e}"))?;
        stream
            .set_read_timeout(Some(IO_TIMEOUT))
            .map_err(|e| format!("read timeout: {e}"))?;
        stream
            .set_write_timeout(Some(IO_TIMEOUT))
            .map_err(|e| format!("write timeout: {e}"))?;
        let writer = stream.try_clone().map_err(|e| format!("clone: {e}"))?;
        Ok(Self {
            reader: BufReader::new(stream),
            writer,
        })
    }

    fn exchange(&mut self, payload: &str) -> Result<String, String> {
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
fn round_trip_fresh(payload: &str) -> Result<String, String> {
    Connection::open()?.exchange(payload)
}

/// Reuse the cached connection; reconnect once on failure.
fn round_trip_persistent(payload: &str) -> Result<String, String> {
    let mut guard = persistent_cell()
        .lock()
        .map_err(|e| format!("conn lock: {e}"))?;
    if let Some(conn) = guard.as_mut() {
        match conn.exchange(payload) {
            Ok(reply) => return Ok(reply),
            Err(_) => *guard = None,
        }
    }
    let mut conn = Connection::open()?;
    let reply = conn.exchange(payload)?;
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
    round_trip_fresh(&payload).unwrap_or_else(|e| error_json(&e))
}

/// Blocking round trip on the reused connection.
pub fn rpc_keepalive(payload: String) -> String {
    round_trip_persistent(&payload).unwrap_or_else(|e| error_json(&e))
}

/// Time `count` round trips inside the extension and return the distribution as
/// JSON. Keeps the measurement off SQF's frame-quantised clock; `keepalive`
/// selects the reused connection over a fresh one per call.
pub fn bench(count: u32, keepalive: bool) -> String {
    if count == 0 {
        return error_json("count must be > 0");
    }
    let mut micros: Vec<u128> = Vec::with_capacity(count as usize);
    for i in 0..count {
        let payload = format!(r#"{{"cmd":"bench","n":{i}}}"#);
        let started = std::time::Instant::now();
        let outcome = if keepalive {
            round_trip_persistent(&payload)
        } else {
            round_trip_fresh(&payload)
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
pub fn rpc_async(ctx: Context, id: String, payload: String) {
    std::thread::spawn(move || {
        let reply = round_trip_persistent(&payload).unwrap_or_else(|e| error_json(&e));
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
    use std::sync::{Mutex, MutexGuard, OnceLock};
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
        let (output, code) =
            extension.call("bench", Some(vec!["5".to_string(), "true".to_string()]));
        assert_eq!(code, 0);
        assert!(output.contains(r#""n":5"#), "unexpected output: {output}");
        assert!(!output.contains("error"), "unexpected output: {output}");
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
