"""Emit one OTel log record, and keep a copy of it where the collector cannot lose it (#226).

The breaker has to put every transition in OTel — that is ADR-0061's whole reason for
preferring a breaker we own over LiteLLM's, whose cooldown transitions never reach a
collector at all. This module is the smallest thing that does it honestly.

Two halves, split so that the assertable one is pure:

- **`log_record`** renders an OTLP/HTTP JSON `ExportLogsServiceRequest` from an `Event`.
  No I/O, no clock, no environment — a test reads the document and says what is in it.
- **`post`** puts that document on the box's own collector, which listens on loopback
  (`127.0.0.1:4318`, `/etc/otelcol-contrib/config.yaml`) and exports to a rotating
  JSONL. Nothing leaves this machine and no foreign endpoint is involved.

**Emission never fails a caller.** A breaker transition that could not be exported is
still a transition that happened, and a dispatcher that refused to refuse because a
collector was down would be worse than one with no telemetry. So `emit` makes one
bounded attempt at the collector and then appends the record — carrying whether that
attempt landed — to a local journal. The journal is the durable record; the collector
is the query surface.

The OTLP wire form is verbose by design — every attribute is `{"key": k, "value":
{"stringValue": v}}` — so `attribute` and `attributes` build it once here rather than
at each call site.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `breaker.py` uses to reach here.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes this importable.
import bounded_request

if TYPE_CHECKING:
    from collections.abc import Mapping

# The collector on this box: loopback only, file exporter, no egress. A caller may
# point elsewhere through the standard OTLP variables, which is how #227's spine will
# move this without touching the breaker.
DEFAULT_ENDPOINT: Final = "http://127.0.0.1:4318/v1/logs"

# Bounded, and short: an export is a side effect of a decision that has already been
# taken, so a slow collector must cost a moment, never a turn.
DEFAULT_TIMEOUT_SECS: Final = 2.0

NANOS_PER_SEC: Final = 1_000_000_000

# OTel's severity numbering. INFO is 9; a breaker transition is news, not a fault —
# Nygard's rule that a tripped breaker is expected output rather than an incident.
SEVERITY_INFO: Final = 9


class Event(NamedTuple):
    """One thing that happened: what it is called, when, and what it carried."""

    name: str
    at: float
    attributes: Mapping[str, object]
    resource: Mapping[str, object]


def endpoint_from_environment(environ: Mapping[str, str] | None = None) -> str:
    """Resolve the logs endpoint from the standard OTLP variables, or fall back to loopback.

    `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` is a full URL by the specification;
    `OTEL_EXPORTER_OTLP_ENDPOINT` is a base to which the signal path is appended.
    """
    env = os.environ if environ is None else environ
    specific = env.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "").strip()
    if specific:
        return specific
    base = env.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if base:
        return base.rstrip("/") + "/v1/logs"
    return DEFAULT_ENDPOINT


def attribute(key: str, value: object) -> dict[str, object]:
    """Render one OTLP key/value, choosing the value type the collector will index on."""
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


def attributes(pairs: Mapping[str, object]) -> list[dict[str, object]]:
    """Render a flat mapping as OTLP attributes, in the caller's own key order."""
    return [attribute(key, value) for key, value in pairs.items()]


def log_record(event: Event, scope: str = "cti.breaker") -> dict[str, object]:
    """Render an OTLP `ExportLogsServiceRequest` carrying exactly one event.

    The event name goes in two places on purpose: the record body, which is what a human
    reading the JSONL sees first, and an `event.name` attribute, which is how OTel names
    an event on a log record.
    """
    stamp = str(int(event.at * NANOS_PER_SEC))
    return {
        "resourceLogs": [
            {
                "resource": {"attributes": attributes(event.resource)},
                "scopeLogs": [
                    {
                        "scope": {"name": scope},
                        "logRecords": [
                            {
                                "timeUnixNano": stamp,
                                "observedTimeUnixNano": stamp,
                                "severityNumber": SEVERITY_INFO,
                                "severityText": "INFO",
                                "body": {"stringValue": event.name},
                                "attributes": [
                                    attribute("event.name", event.name),
                                    *attributes(event.attributes),
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def post(
    document: Mapping[str, object],
    endpoint: str = "",
    timeout: float = DEFAULT_TIMEOUT_SECS,
) -> tuple[bool, str]:
    """Put one OTLP document on the collector, and say plainly whether it landed.

    Returns `(exported, detail)`. Every failure is caught: a caller's decision has
    already been taken by the time this runs, and telemetry that could break it would
    be worse than telemetry that is missing.
    """
    target = endpoint or endpoint_from_environment()
    if not target.startswith(("http://", "https://")):
        return False, f"endpoint_not_http:{target}"
    body = json.dumps(document).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 — scheme checked immediately above
        target,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        status, _ = bounded_request.read(request, timeout)
    except urllib.error.HTTPError as error:
        return False, f"http_{error.code}"
    except OSError as error:  # URLError, refused, socket timeout, stalled resolver — all one here
        return False, f"unreachable:{type(error).__name__}"
    return True, f"http_{status}"


def journal_line(event: Event, exported: bool, detail: str) -> str:  # noqa: FBT001 — a journal records what happened, and whether it exported is half of it
    """Render the durable JSONL record of one emission, export outcome included."""
    return json.dumps(
        {
            "event": event.name,
            "at": event.at,
            "attributes": dict(event.attributes),
            "resource": dict(event.resource),
            "exported": exported,
            "export_detail": detail,
        },
        sort_keys=True,
    )


def emit(
    event: Event,
    journal: Path,
    endpoint: str = "",
    timeout: float = DEFAULT_TIMEOUT_SECS,
) -> bool:
    """Export one event and journal it with the export's own outcome.

    The journal is the durable half and the collector is the query half. The collector
    is a service that can be down, restarting or reconfigured, and an event that only
    ever existed in a POST that failed is an event nobody can audit later — so the
    journal line carries `exported` and `export_detail` rather than being written only
    on success. The export attempt is bounded first, so the journal write never waits.
    """
    exported, detail = post(log_record(event), endpoint, timeout)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(journal_line(event, exported, detail) + "\n")
    return exported
