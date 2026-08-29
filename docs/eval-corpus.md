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
workspace, captured harness streams, the adapter record and the graded outcome per
trial, a run manifest (`run.json`) carrying the toolchain pin — interpreter, runner
bytes, HEAD — and the graded report (`report.txt`).

## What a task is

A task file (`cti.eval-task/1`) declares the work (`prompt`), the expectation
(`classes` + `expected_class`, never an exact string), the repeats, the tolerance, and
its hash-pinned grader. Variants are the ablation arms: each variant seeds the trial
workspace's context file, and `full` derives from the repository's `AGENTS.md` at run
time so it can never drift from the file it ablates.

## Verdicts, not results

- The verdict is a rate over the graded repeats, judged against the task's tolerance.
- A spread beyond tolerance quarantines the case, carrying its reproduction baseline
  (arrangement, run count, outcomes, disagreement, tolerance) — `flake_quarantine`'s
  discipline applied to a stochastic subject.
- A trial stopped by budget, and an infrastructure failure, type as exactly that —
  never a failed configuration.
- The run's exit code is the worst class present; refusals before any trial exit 6.

## Statistics, derived

`power_statement` computes the corpus statistics from the case count — the 95%
normal-approximation half-width at the reference rate, the rule of three where nothing
fails, and a claim-supported flag against the manifest's `min_cases_for_claim` (20).
The shipped corpus holds 3 cases, so a run says `claim=not_supported` out loud: this
corpus catches large regressions, proves the harness and exposes qualitative failures,
and nothing finer.

## Cost

Tokens and wall time are reported per configuration; a currency figure appears only
when the configuration declares `unit_costs`, because a price this repository invents
would be a number nobody can audit.

## What it does not claim

A passing run says the corpus detected no regression. It does not say the configuration
is good, does not compare lanes or profiles, and makes no causal claim. A task's
expected outcome is the corpus author's judgement, held to review, not something the
runner verifies.
