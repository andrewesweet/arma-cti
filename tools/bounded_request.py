"""One HTTP read, bounded by a deadline the resolver cannot escape (#427).

`urlopen`'s `timeout` is the *socket's*, and a socket exists only once the hostname has
resolved: `getaddrinfo` runs first, takes no timeout of its own, and `socket.setdefaulttimeout`
does not reach it either. So a request carrying a ten-second timeout can stall for as long as
the resolver does before that timeout governs anything — which on `just land`'s serial path is
a landing hanging on a name lookup, with nothing to cancel it.

The bound here is therefore the *call's* rather than the socket's. The read runs on a daemon
thread and the deadline is the join, so a stall anywhere inside it — resolution, connect, body
— expires the same way. A read still running at its deadline is abandoned rather than waited
for, and a daemon thread holds nothing at interpreter exit; that is why this is a bare thread
rather than a `ThreadPoolExecutor`, whose `atexit` join would put the wait back at the end of
the process. The socket timeout is passed as well, because it is the cheaper bound wherever it
does apply.

Every exception the read raises reaches the caller unchanged, `HTTPError` included, so a 429's
`retry-after` still arrives. The deadline itself raises `TimeoutError`, which is an `OSError`:
a caller already turning an unreachable host into its own typed failure lands a stalled
resolver in that same direction rather than in a new one.
"""

from __future__ import annotations

import threading
import urllib.request


def read(request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    """Return one response's `(status, body)`, or raise `TimeoutError` once `timeout` passes."""
    answer: list[tuple[int, bytes]] = []
    failure: list[Exception] = []

    def fetch() -> None:
        # Each caller vouches for its own URL: two module constants in `breaker`, an
        # endpoint whose scheme `otel_event` checks immediately before building it.
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                answer.append((response.status, response.read()))
        except Exception as error:  # noqa: BLE001 — re-raised unchanged on the caller's thread
            failure.append(error)

    worker = threading.Thread(target=fetch, daemon=True, name="cti-bounded-request")
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        message = f"{request.full_url} gave no response within {timeout}s"
        raise TimeoutError(message)
    if failure:
        raise failure[0]
    return answer[0]
