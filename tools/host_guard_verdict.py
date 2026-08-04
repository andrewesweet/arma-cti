"""Map the host guard's answer onto the tier's verdict (#161, ADR-0049).

`cti_human_client_state` reads the Windows process list and answers one line —
``free``/``running``/``unavailable`` plus detail. What that answer *means* —
proceed, or the `infra_unavailable` stop — is a decision, and it lived as three
near-verbatim bash case ladders: `cti_host_guard_main` in spike/host-guard.sh,
`cti_host_guard` in spike/hosts.sh, and inline above spike/run.sh's launch,
differing only in prefix and one sentence. A rung changed in one copy drifted
from the other two, so the ladder is decided here, where pytest can reach it
(`tests/unit/test_host_guard_verdict.py` pins the bytes), and the shell keeps
only the asking and the acting.

One decision, two renderings:

- ``block``: the `[host-guard]` lines the guards print to stderr, host-prefixed
  when the caller names one.
- ``env``: the tier's `key=value` lines, for the harness to fold a stop's
  `failure_detail` into `results.env` through its own `fail`.

Exit code 0 is proceed; 5 is stop — the number `CTI_EXIT_INFRA_UNAVAILABLE`
names in spike/host-guard.sh, its one bash home, and the pair is asserted
equal. The default rung is fail-closed (#41): a state this ladder has never
heard of — garbage, an empty answer, a truncated line — is a check that could
not run, and that is a stop, never a proceed.
"""

from __future__ import annotations

import argparse
import sys
from typing import Final, NamedTuple

# Must agree with spike/host-guard.sh's CTI_EXIT_INFRA_UNAVAILABLE, the number's
# one bash home; tests/unit/test_host_guard_verdict.py holds the two together.
EXIT_INFRA_UNAVAILABLE: Final = 5

COULD_NOT_RUN: Final = "A check that could not run is not a check that passed."
NOT_A_RESULT: Final = "This is a stop, not a result. Nothing was launched."


class GuardVerdict(NamedTuple):
    """One guard decision, with both renderings of it."""

    proceed: bool
    block: tuple[str, ...]
    env: tuple[str, ...]


def split_answer(answer: str) -> tuple[str, str]:
    """State and detail, exactly as the shell expansions read them.

    ``${answer%% *}`` and ``${answer#* }`` both give the whole string back when
    there is no space in it, and the three ladders were built on that — so the
    one home mirrors it rather than quietly reading a spaceless answer as an
    empty detail.
    """
    state, sep, detail = answer.partition(" ")
    if not sep:
        return answer, answer
    return state, detail


def decide(answer: str, host: str = "") -> GuardVerdict:
    """Apply the module docstring's ladder to one guard answer."""
    state, detail = split_answer(answer)
    prefix = f"[host-guard] {host}: " if host else "[host-guard] "
    verdict_line = "[host-guard] verdict=FAIL failure_class=infra_unavailable" + (
        f" host={host}" if host else ""
    )
    if state == "free":
        return GuardVerdict(
            proceed=True,
            block=(f"{prefix}{detail}",),
            env=("verdict=proceed", f"detail={detail}"),
        )
    if state == "running":
        return GuardVerdict(
            proceed=False,
            block=(
                f"{prefix}{detail} — a play session may be live.",
                verdict_line,
                f"[host-guard] {NOT_A_RESULT}",
            ),
            env=(
                "verdict=FAIL",
                "failure_class=infra_unavailable",
                f"failure_detail={detail} — that is a play session, not ours",
            ),
        )
    # `unavailable`, and every state the ladder has never heard of: fail closed.
    return GuardVerdict(
        proceed=False,
        block=(
            f"{prefix}{detail}",
            verdict_line,
            f"[host-guard] {COULD_NOT_RUN}",
        ),
        env=(
            "verdict=FAIL",
            "failure_class=infra_unavailable",
            f"failure_detail={detail}; refusing to take a machine I cannot check",
        ),
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """One answer line in, plus which rendering and (optionally) whose host."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="")
    parser.add_argument("--format", choices=("block", "env"), default="block")
    parser.add_argument("answer")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Decide, print the chosen rendering, and exit the verdict."""
    args = parse_args(argv)
    verdict = decide(args.answer, host=args.host)
    for line in verdict.block if args.format == "block" else verdict.env:
        print(line)  # noqa: T201 — the shell places these lines
    return 0 if verdict.proceed else EXIT_INFRA_UNAVAILABLE


if __name__ == "__main__":
    sys.exit(main())
