"""`tools/bounded_request.py`: the bound is the whole call's, not the socket's (#438).

The module exists so a read on `just land`'s serial path cannot hang (#427), and until this
file nothing in `tests/` measured whether it does. Three properties, the first the one the
module is for:

- the deadline expires a stall a socket timeout cannot reach — resolution, where no socket
  exists yet for a timeout to govern;
- a real answer passes through unchanged, `HTTPError` with its `retry-after` included, because
  a bound that mangled a normal answer would be worse than no bound;
- a read that outlives its deadline is abandoned rather than waited for, and its late
  completion can land only in lists that one call held.

Nothing here reaches the internet. The servers are loopback `http.server` sockets on ephemeral
ports, and the one resolver stall is `socket.getaddrinfo` replaced by a blocker — the same
construction `test_land_review.py` pins the landing rung with, at the exact seam the module's
own docstring names. That construction is honest about what a resolver stall *is*: the call
into resolution never returns, no socket is ever created, and no packet leaves this box. A
stall staged any deeper would need a resolver this box does not have; staged any shallower
(a server that accepts and never answers) it is a *body* stall, where the socket timeout
governs alongside the deadline and the distinction this module exists for is invisible.
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

bounded_request: ModuleType = load_tool("bounded_request")

# A port nothing listens on, for the refused-connection pass-through: inside the tier's own
# allocation [2400, 3000) and away from the slot stride, the same convention `test_breaker`'s
# `DEAD_ENDPOINT` keeps, so a test can never collide with a running world.
DEAD_PORT = 2998


class PathEchoHandler(BaseHTTPRequestHandler):
    """The arrangement's base: no request log, and an answer that names its request.

    The body is the request path, so a test asserting an answer asserts *which* request's
    answer came back rather than trusting any body to be any body.
    """

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Swallow the request log: these reads are staged, not served."""

    def do_GET(self) -> None:
        """Answer 200 with the request path as the body."""
        body = self.path.encode()
        self.send_response(200)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class StallHandler(PathEchoHandler):
    """Accept, then hold the answer past any deadline the tests use."""

    delay = 5.0

    def do_GET(self) -> None:
        """Sleep first; the caller's deadline is what this handler exists to outlive."""
        time.sleep(self.delay)
        super().do_GET()


class UsageLimitedHandler(PathEchoHandler):
    """Answer 429 the way a quota endpoint does: a body, and a `retry-after` header."""

    def do_GET(self) -> None:
        """Send the 429 whose header `breaker` schedules its next read from."""
        body = b'{"error":"quota exhausted"}'
        self.send_response(429)
        self.send_header("retry-after", "27")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _QuietHTTPServer(ThreadingHTTPServer):
    """A server whose handler threads are daemons and whose client losses print nothing.

    `daemon_threads` (inherited from `ThreadingHTTPServer`) keeps a sleeping handler from
    holding `server_close`; the swallowed `handle_error` keeps a client that already left —
    which is exactly what the deadline tests arrange — from printing a broken-pipe traceback
    into the suite's output. Both are the arrangement, not the subject; every assertion lives
    in the tests.
    """

    def handle_error(self, request: object, client_address: object) -> None:
        """Swallow handler errors: a client that left is the arrangement, not a failure."""


def _workers() -> list[threading.Thread]:
    """Return the bounded-request workers alive in this process right now."""
    return [thread for thread in threading.enumerate() if thread.name == "cti-bounded-request"]


def _request(url: str) -> urllib.request.Request:
    """Build the GET every read goes through; one `S310` site for this file's own http."""
    return urllib.request.Request(url)  # noqa: S310 — loopback http this file staged, nothing else


def test_a_stalled_resolver_expires_at_the_calls_deadline_not_the_sockets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one stall a socket timeout cannot reach, expired at the call's own bound.

    `urlopen`'s `timeout` governs a socket, and `getaddrinfo` runs before any socket exists,
    so a resolver that never answers escapes it entirely — the hang this module was written to
    make impossible on `just land`'s serial path. The stall is staged at that seam: the real
    `socket.getaddrinfo` is replaced by one that blocks on an event the test holds, and once
    released it raises rather than resolving, so the whole arrangement touches no network.

    `read` comes back at its deadline with `TimeoutError` while the worker is provably still
    inside resolution — alive, with no socket that could have timed out — which is the
    deadline-versus-socket distinction the module's docstring bets on, as one assertion.
    """
    release = threading.Event()

    def stalled_resolver(*_args: object, **_kwargs: object) -> list[object]:
        release.wait(30.0)  # set in the finally below; the 30 s is only a backstop
        raise socket.gaierror("resolver released by the test")  # noqa: EM101, TRY003 — a seam, not a caller-facing error

    monkeypatch.setattr(socket, "getaddrinfo", stalled_resolver)
    request = _request("http://resolution-stalled.invalid/usage")
    started = time.monotonic()
    with pytest.raises(TimeoutError) as raised:
        bounded_request.read(request, 0.25)
    elapsed = time.monotonic() - started
    try:
        assert elapsed < 1.0
        assert "http://resolution-stalled.invalid/usage" in str(raised.value)
        assert [worker for worker in _workers() if worker.is_alive()], (
            "the worker must still be inside resolution at expiry — a socket timeout "
            "firing here would mean the stall was never a resolver stall"
        )
    finally:
        release.set()
    for worker in _workers():
        worker.join(5.0)  # released, it raises gaierror into its own failure list and dies


def test_a_body_slower_than_the_deadline_expires_at_it() -> None:
    """The plain bound: a handler answering slower than the deadline is a `TimeoutError`.

    On this path the socket carries the same timeout as the call, so a socket timeout fires
    alongside the deadline and this test alone could not tell the two apart — the resolver
    test above is what carries that distinction. What this pins is the contract on the body
    path: the caller sees `TimeoutError` (`socket.timeout` is `TimeoutError`'s alias), never
    a hang and never a partial answer, and sees it at the bound rather than at the handler's
    leisure.
    """
    with _serve(StallHandler) as base:
        request = _request(f"{base}/usage")
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            bounded_request.read(request, 0.25)
        assert time.monotonic() - started < StallHandler.delay / 2


def test_a_live_answer_passes_through_unchanged() -> None:
    """A real response arrives as the `(status, body)` it always was."""
    with _serve(PathEchoHandler) as base:
        read = bounded_request.read(_request(f"{base}/campaign-epoch"), 5.0)
    assert read == (200, b"/campaign-epoch")


def test_an_http_error_reaches_the_caller_as_it_always_did() -> None:
    """A 429's `HTTPError` arrives with its code, its headers and its body intact.

    The module's own docstring bets that a 429's `retry-after` still arrives through the
    bound, because `breaker` schedules its next read at that header's boundary — an
    `HTTPError` flattened into anything else would silently move that schedule. The error is
    raised on the caller's thread by the re-raise, which this also pins.
    """
    with (
        _serve(UsageLimitedHandler) as base,
        pytest.raises(urllib.error.HTTPError) as raised,
    ):
        bounded_request.read(_request(f"{base}/usage"), 5.0)
    assert raised.value.code == 429
    assert raised.value.headers["retry-after"] == "27"
    assert raised.value.read() == b'{"error":"quota exhausted"}'


def test_a_refused_connection_reaches_the_caller_as_it_always_did() -> None:
    """A non-HTTP failure — connection refused — is re-raised unchanged, not re-typed.

    `TimeoutError` is the only exception the bound itself adds; everything the read raises is
    the caller's to see as it was. A refused connection was a `URLError` wrapping
    `ConnectionRefusedError` before the bound existed and still is.
    """
    with pytest.raises(urllib.error.URLError) as raised:
        bounded_request.read(_request(f"http://127.0.0.1:{DEAD_PORT}/usage"), 5.0)
    assert isinstance(raised.value.reason, ConnectionRefusedError)


def test_a_worker_completing_after_its_deadline_cannot_reach_a_moved_on_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The abandonment #427's review established, pinned from outside the module.

    The worker is a daemon and the only join is the bounded one, so a read still running at
    its deadline is left to finish — into lists that exist only inside that one call. The
    construction guarantees the late completion rather than hoping for it: the resolver seam
    blocks on an event until the test sets it, so at the deadline the worker is provably
    still mid-resolution (no socket, hence no socket timeout to end it early), and the
    release then hands back the loopback's real addresses so the abandoned read *succeeds*
    after the caller has its `TimeoutError` — the strongest thing a late completion could try
    to do.

    Pinned: the outcome was delivered before the worker finished; the worker is a daemon while
    it runs and ends once released; and a fresh read through the same module gets its own
    answer, byte-distinct from the one the abandoned call appended late — a module-level
    answer list, the plausible wrong shape, would return the late answer here and go red.
    """
    release = threading.Event()
    real_getaddrinfo = socket.getaddrinfo

    with _serve(PathEchoHandler) as base:
        port = int(base.rsplit(":", 1)[1])
        addresses: list[object] = [*real_getaddrinfo("127.0.0.1", port)]

        def gate_then_resolve(*_args: object, **_kwargs: object) -> list[object]:
            release.wait(30.0)  # set in the finally below; the 30 s is only a backstop
            return addresses

        monkeypatch.setattr(socket, "getaddrinfo", gate_then_resolve)
        try:
            with pytest.raises(TimeoutError) as raised:
                bounded_request.read(_request(f"{base}/abandoned"), 0.25)
            stalled = _workers()
            assert stalled, "the worker must still exist at expiry — it was never joined"
            assert all(worker.daemon for worker in stalled)
        finally:
            release.set()
        for worker in _workers():
            worker.join(5.0)
        assert all(not worker.is_alive() for worker in _workers())
        assert type(raised.value) is TimeoutError  # the late success changed nothing delivered
        fresh = bounded_request.read(_request(f"{base}/after"), 5.0)
        assert fresh == (200, b"/after")


@contextlib.contextmanager
def _serve(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    """Serve `handler` on an ephemeral loopback port; yield the base URL.

    A context manager rather than a fixture on purpose, matching `conftest`'s reasoning: the
    one thing it varies is the handler class, which every test hands it as an argument.
    """
    httpd = _QuietHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(
        target=httpd.serve_forever, daemon=True, name="test-bounded-request-server"
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()  # handler threads are daemons already, so nothing waits on a stall
        httpd.server_close()
        thread.join(5.0)
