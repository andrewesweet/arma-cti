# The eval corpus

#617 built the measurement half of #615: an operator names a corpus and one or two
agent configurations, and gets a typed verdict per case, a task-by-task comparison and
the cost of the run. The gate that refuses activation on a failure is #618, blocked by
this until now.

## Run it

```
just eval-corpus --configuration C.json [--configuration C2.json] [--corpus evals/corpus] [--dry-run]
```

`--dry-run` names every case, its repeats, tolerance, expected class and budget, and
runs nothing. Evidence lands under `~/.arma-cti/evals/runs/<run-id>/` — per-trial
workspace, live usage sidecar, captured harness streams, the adapter record and the
graded outcome per trial, a run manifest (`run.json`) carrying the resolved executable
and its sha256, runner bytes and HEAD, and the graded report (`report.txt`). The
workspace is run inside a bubblewrap filesystem/PID boundary; host home, repository,
temporary, runtime and prior-run state are not mounted.

## Toolchain prerequisite

The runner requires the Linux `bwrap` executable from bubblewrap. `just prereqs check`
reports it as the `bubblewrap` prerequisite; if it is absent, the runner refuses with
`sandbox_unavailable` and the pipeline tests skip rather than turning a missing host
package into an assertion failure. The runner's boundary was exercised inside an outer
bubblewrap boundary like the Codex lane's, including the shipped synthetic corpus; the
nested invocation completed successfully, so no sandbox bypass or special case is
needed.

## What a task is

A task file (`cti.eval-task/1`) declares the work (`prompt`), the expectation
(`classes` + `expected_class`, never an exact string), the configuration scope
(`configuration: per-run`), the repeats, the tolerance, and its hash-pinned grader.
Variants are the ablation arms: each variant seeds the trial workspace's context file.
The `full` arm reads its repository source at run time. A frozen reduction declares its
derivation source as `derived_from.repo_file` plus a sha256; the loader compares that
pin with the live source and refuses `context_pin_stale` before any trial when they
differ. This keeps the comparison on one known source instead of silently pairing a
live document with an older reduction. Because the full arm reads `AGENTS.md` live,
changing that source intentionally makes the unit gate refuse until the frozen
reduction and its pin are refreshed. A materialized case names the selected
configuration and variant; variants are correlated arms of one task, not independent
observations.

## Verdicts, not results

- The verdict is a rate over graded answers only, judged against the task's tolerance;
  `unclassified` answers are counted separately and make an otherwise passing case
  report `unclassified`. If any repeat stops or fails, the case has no rate and reports
  that typed state.
- The report prints `graded=N unclassified=M`; any rate line says
  `rate_over=graded_answers` so its denominator is explicit.
- Each materialized case reports its rate, and each task reports the worst typed status
  across its variants; no rate is aggregated across correlated variants.
- A spread beyond tolerance quarantines the case, carrying its reproduction baseline
  (arrangement, run count, outcomes, disagreement, tolerance) — `flake_quarantine`'s
  discipline applied to a stochastic subject.
- A complete case with a mid-range rate whose outcomes spread beyond tolerance is
  quarantined deliberately, even when (for example) 3 of 5 repeats meet at tolerance
  0.2. The runner cannot tell that variance from a partial regression without an
  unchanged control, so `outside_tolerance` is reserved for a sufficiently stable
  wrong-class result; quarantine therefore ranks below a budget stop by design.
- A trial stopped by budget, and an infrastructure failure, type as exactly that —
  never a failed configuration.
- The run's exit code is the worst class present; refusals before any trial exit 6.

## Statistics, derived

`power_statement` computes the corpus statistics from the number of independent task
identities, not materialized variants — the 95% normal-approximation half-width at the
reference rate, the rule of three where nothing fails, and a claim-supported flag
against the manifest's `min_cases_for_claim` (20). The shipped corpus holds one
independent task and three materialized arms, so a run says `claim=not_supported` out
loud: this corpus catches large regressions, proves the harness and exposes qualitative
failures, and nothing finer.

## Cost

Tokens, commands and wall time are reported per configuration, including completed,
budget-stopped and infrastructure trials when live usage was available. A currency
figure appears only when the configuration declares `unit_costs` and every trial has
known usage, because a price this repository invents would be a number nobody can
audit.

Graders are copied beneath the run directory, hash-verified before the run, and
re-executed from those bytes for every trial. The adapter must atomically update
`usage.json` while running; the runner watches it and kills the complete process group
when a time, token or command ceiling is reached. Missing or malformed live usage is a
typed harness failure, never a partial passing case.

## What it does not claim

A passing run says the corpus detected no regression. It does not say the configuration
is good, does not compare lanes or profiles, and makes no causal claim. A task's
expected outcome is the corpus author's judgement, held to review, not something the
runner verifies.
