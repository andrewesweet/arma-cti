"""Type one probe's outcome into the verdict the pool records (#171, ADR-0049).

`spike/regress.sh` launches the probe, holds the slot and owns the pool's flag
files; what happened is then a decision rather than a process, so it is decided
here, where pytest can reach it — #83's precedent, that a wrong class is a
harness bug and the no-Arma tier is where a harness bug should turn red. The
ladder, in the order the shell applied it:

1. The watchdog killed `run.sh` — a `timeout` status of 124, or the follow-up
   SIGKILL's 137 with the deadline actually reached. Its process tree died
   mid-measurement, so whatever half-written `results.env` it left behind is
   not evidence of anything: `infra_unavailable` — stop, not a result (#144).
2. Something *else* killed `run.sh`: any 128+SIG exit, including a SIGKILL
   landing before the watchdog's deadline, which cannot be the watchdog's and
   is the OOM killer's shape (#125). The machine's doing, not the harness's,
   so it is `infra_unavailable` rather than the untyped-red rule below — a
   reader sent to "fix the harness" for a machine event fixes nothing (#147).
3. `run.sh` said PASS: the raw class is `pass`.
4. `run.sh` failed without typing itself. An untyped red is a harness bug, and
   the failure-class table says fix the harness first — so it is reported as
   one (`untyped_harness_failure`) rather than folded into the nearest
   plausible class (#83).
5. `expect:` inverts the verdict for a probe that is red by design, and only
   for the declared class: a negative probe failing for the wrong reason is
   still a failure, and a green run of it is the bug (#80, #96, #102).
6. `quarantined:` is applied last, over whatever the run said: the corpus keeps
   gathering evidence about a flake without the flake gating anyone, and the
   tier never retries — one run, one verdict (#130).

Writes `verdict.json` — the shape the pool's merge, `prune_passes` and the
next slot holder's ADR-0022 check read — and prints `key=value` lines for the
shell to act on, which is the tier's own recording format.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, NamedTuple

# GNU timeout's two statuses for "the deadline was reached": the second is what
# a process killed by the follow-up SIGKILL reports. 137 is also what *any*
# SIGKILL reports — the OOM killer's included — so the deadline having been
# reached is what tells the two apart (#147).
EXIT_TIMED_OUT: Final = 124
EXIT_KILLED: Final = 137
# The shell reports a command killed by signal N as 128+N. Codes past the real
# signal range (255 above all) are a process's own exits, not signal deaths.
SIGNAL_EXIT_BASE: Final = 128
MAX_SIGNAL: Final = 64


def signal_name(number: int) -> str:
    """SIGKILL for 9, and a plain number for a signal the platform has no name for."""
    try:
        return signal.Signals(number).name
    except ValueError:
        return f"signal {number}"


def read_results(path: Path) -> dict[str, str]:
    """Read a run's `results.env` as `key=value` pairs, the last write winning.

    `run.sh` appends, so the final word is the one that stands — the rule the
    old `sed | tail -1` readers applied. A watchdog-killed run may have left no
    file at all; that is data rather than an error, and the ladder's first rung
    is about exactly that run.
    """
    if not path.exists():
        return {}
    results: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            results[key] = value
    return results


@dataclass(frozen=True)
class Outcome:
    """Everything the ladder needs to know about one finished probe run."""

    run_status: int
    results: dict[str, str] = field(default_factory=dict)
    expect: str = ""
    quarantined: str = ""
    window_secs: int = 0
    watchdog_secs: int = 0
    margin_secs: int = 0
    elapsed_secs: int = 0
    evidence: str = ""


class TypedVerdict(NamedTuple):
    """The verdict the pool records, and the raw class it was typed from."""

    verdict: str
    class_: str
    raw_class: str
    detail: str


def type_verdict(outcome: Outcome) -> TypedVerdict:
    """Apply the module docstring's ladder, in that order."""
    raw = outcome.results.get("failure_class", "")
    detail = outcome.results.get("failure_detail", "")

    # 124 is `timeout` saying the deadline was reached, whatever the command
    # then exited; 137 is a SIGKILL, which is only the watchdog's follow-up
    # kill if the deadline had actually passed — before it, nothing of the
    # watchdog's has fired yet and the kill is the machine's (#147).
    if outcome.run_status == EXIT_TIMED_OUT or (
        outcome.run_status == EXIT_KILLED and outcome.elapsed_secs >= outcome.watchdog_secs
    ):
        raw = "infra_unavailable"
        detail = (
            f"run.sh was killed at the {outcome.watchdog_secs}s watchdog "
            f"(probe window {outcome.window_secs}s plus {outcome.margin_secs}s "
            f"for bring-up and teardown), exit {outcome.run_status}; "
            f"see {outcome.evidence}/regress.log"
        )
    elif SIGNAL_EXIT_BASE < outcome.run_status <= SIGNAL_EXIT_BASE + MAX_SIGNAL:
        # Signal-killed, and not by the watchdog: the machine's doing, so the
        # honest class is the stop, not the untyped-red rule — a reader sent
        # to fix the harness for an OOM kill fixes nothing (#147, #125).
        number = outcome.run_status - SIGNAL_EXIT_BASE
        suspect = (
            " — the OOM killer is the usual suspect (#125)" if number == signal.SIGKILL else ""
        )
        raw = "infra_unavailable"
        detail = (
            f"run.sh was killed by {signal_name(number)} (exit {outcome.run_status}) "
            f"{outcome.elapsed_secs}s into its {outcome.watchdog_secs}s watchdog: "
            f"the machine's doing, not the probe's or the harness's{suspect}; "
            f"see {outcome.evidence}/regress.log"
        )
    elif outcome.results.get("verdict") == "PASS":
        raw = "pass"
    elif not raw:
        raw = "untyped_harness_failure"
        detail = detail or (
            f"run.sh exited {outcome.run_status} without recording a class; "
            f"see {outcome.evidence}/regress.log"
        )

    if not outcome.expect:
        typed = raw
    elif raw == outcome.expect:
        typed = "pass"
        detail = f"expected-red: {detail}"
    elif raw == "pass":
        typed = "assertion_failed"
        detail = (
            f"probe expects {outcome.expect} and passed instead; "
            "a green run of this probe is the bug"
        )
    else:
        typed = raw
        detail = f"probe expects {outcome.expect}, got {raw}: {detail}"

    if outcome.quarantined and typed != "pass":
        detail = f"quarantined {outcome.quarantined} (not gating): {typed} — {detail}"
        typed = "flake_quarantine"

    return TypedVerdict(
        verdict="PASS" if typed == "pass" else "FAIL",
        class_=typed,
        raw_class=raw,
        detail=detail,
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the facts `regress.sh` gathered, one flag each.

    All of them are required except the three headers a probe may not carry:
    plumbing that forgot a fact should fail loudly here rather than record a
    verdict with a hole in it.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--verdict-json", required=True, type=Path)
    parser.add_argument("--run-status", required=True, type=int)
    parser.add_argument("--window", required=True, type=int)
    parser.add_argument("--watchdog", required=True, type=int)
    parser.add_argument("--margin", required=True, type=int)
    parser.add_argument("--elapsed", required=True, type=int)
    parser.add_argument("--expect", default="")
    parser.add_argument("--quarantined", default="")
    parser.add_argument("--issues", default="")
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--git-dirty", required=True, choices=("true", "false"))
    parser.add_argument("--slot", required=True, type=int)
    parser.add_argument("--host", required=True)
    parser.add_argument("--evidence", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Type the verdict, write `verdict.json`, print the lines the shell acts on."""
    args = parse_args(argv)
    results = read_results(args.results)
    typed = type_verdict(
        Outcome(
            run_status=args.run_status,
            results=results,
            expect=args.expect,
            quarantined=args.quarantined,
            window_secs=args.window,
            watchdog_secs=args.watchdog,
            margin_secs=args.margin,
            elapsed_secs=args.elapsed,
            evidence=args.evidence,
        )
    )
    document = {
        "probe": args.probe,
        "verdict": typed.verdict,
        "class": typed.class_,
        "raw_class": typed.raw_class,
        "expected": args.expect,
        "quarantined": args.quarantined,
        "legs": results.get("legs", ""),
        "detail": typed.detail,
        "window_secs": args.window,
        "elapsed_secs": args.elapsed,
        "issues": args.issues,
        "started_at": args.stamp,
        "git_sha": args.git_sha,
        "git_dirty": args.git_dirty == "true",
        "slot": args.slot,
        "host": args.host,
        "arma_version": results.get("server_version", ""),
        "evidence": args.evidence,
    }
    # The merge and the pruner read this document as JSON now (#185,
    # tools/pool_merge.py), so no in-repo reader depends on the bytes any
    # more; indent=2 stays because the rendering is the evidence a human
    # greps, and churning it would break every stored run's uniformity.
    args.verdict_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    lines = (
        ("class", typed.class_),
        ("verdict", typed.verdict),
        ("detail", typed.detail),
        ("legs", results.get("legs", "")),
    )
    for key, value in lines:
        print(f"{key}={value}")  # noqa: T201 — the shell reads these lines
    return 0


if __name__ == "__main__":
    sys.exit(main())
