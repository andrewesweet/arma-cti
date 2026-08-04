# Non-trivial logic lives in Python; bash keeps the process seams

Delegated-decision: yes
Date: 2026-08-04
Stood-in-for: human sign-off on a CLAUDE.md convention (a Toolchains bullet). The direction itself is the human's, stated 2026-08-03 and quoted in #171; what is delegated is its wording as a rule, where the triviality line sits, and the migration discipline.
Reviewed-by-human: 2026-08-04
Claimed: comment on #171, 2026-08-04

## The decision

New non-trivial logic lands in Python under pytest. Non-trivial means: a decision ladder or
classification, aggregation or ranking, reading or writing a structured format (JSON above all),
arithmetic past a counter or a comparison against a constant. If getting it wrong is the kind of
thing a unit test would have caught, it is past the line.

Bash keeps the process seams, because there the shell is the actual subject: launching and holding
processes, `flock`, environment assembly, signals and `timeout`, flag files coordinating workers.
A test of that code *is* a test of the shell's behaviour, which is why the pool suites drive the
real scripts.

The boundary's mechanics, set by the first instance: the logic is a `tools/` script the shell
invokes, bounded by `timeout` like every `uv run` the tier makes (#144), speaking the tier's own
`key=value` line format back to the caller; the shell checks the call at its site and fails
closed — a typer `timeout` killed is `infra_unavailable` (#41's shape: a check that could not run
is not a check that passed), a typer that ran and failed is `untyped_harness_failure`.

Migration of logic already in bash is incremental: one seam per issue, each landing with its
pytest coverage in the same commit — never a big-bang rewrite of the tier that runs the corpus.
The ranked inventory of seams past the line is a comment on #171.

## Why

The human, 2026-08-03: "The bash logic we rely on is getting complicated. We should keep all
non-trivial logic in Python where it is more easily tested and benefits from enhanced language
features and a standard library."

The backlog had already made the case concrete. #144: the tier's own deadline arithmetic ran
through `bc`, and with `bc` absent the arithmetic evaluated empty-to-false and the timeout
mechanism itself failed open — inside the thing that enforces deadlines. #161: the pool libraries
triplicate a guard-verdict ladder, a lock-metadata block and an exit-code definition, because bash
has no importable home a function naturally lands in. #162: a missing `nullglob` turned an empty
probes directory into a literal `*` probe. #83 is the standing precedent: the verdict
classification `run.sh` got wrong twice became a red `just unit` only once it was asserted from
Python, and a wrong class is by definition a harness bug — the exact kind of logic that should
never wait for a bring-up to be found wrong.

Python here is not a preference but the tested path: `ruff` at `select = ["ALL"]`, `ty`, pytest
with hypothesis, and `json`/`argparse` where the shell had a `sed` over an indentation-dependent
heredoc.

First applied instance, landed with this ADR in one commit (the convention rule):
`tools/probe_verdict.py` replaces the sixty-line typing ladder and hand-rolled `verdict.json`
heredoc in `spike/regress.sh` — the watchdog rule (#144), the untyped-red rule (#83), `expect:`
inversion (#80/#96/#102) and quarantine (#130) — under `tests/unit/test_probe_verdict.py`, with
the pool suites still driving the converted runner end to end.

## What would overturn it

- A measured cost that moves a needle: the per-probe `uv run` visibly extending a pool's wall
  time or the no-Arma tier's runtime beyond what the coverage buys. Today's warm invocation is a
  sub-second cost against worlds that take minutes; if that stops being true, re-measure before
  inheriting it.
- A slot host without the repo's Python toolchain — ADR-0032's second machine, if commissioning
  (#52/#53) lands it without `uv` — forcing verdict typing to happen where only the shell exists.
  The likely answer is typing after evidence pull-back rather than repeal, but that is this ADR's
  boundary to redraw, not a silent exception.
- The human revising the direction the policy writes down.

## Consequences

- CLAUDE.md's Toolchains section gains a **Bash** bullet naming the boundary; this ADR is its
  ADR-0013 record.
- #161 and #162 execute under the policy from the day it lands: where a triplicated seam is
  decision logic, it deduplicates into Python rather than into a fourth bash copy; where it is a
  process seam, one sourced bash home is still the right fix.
- `spike/regress.sh` owns one new failure honestly: the verdict typer itself failing is typed at
  its call site, with a minimal fallback `verdict.json` carrying the least the merge reads —
  because a probe with no `verdict.json` reads as a dead worker (ADR-0022) and would reclaim a
  slot that is fine.
- The `key=value` line format is confirmed as the tier's shell-to-Python contract, in both
  directions (`results.env` in, typed lines out).
