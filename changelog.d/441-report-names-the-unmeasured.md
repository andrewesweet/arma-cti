## Changed

- `just mutation --report` now names the modules a landing introduces that
  nothing measured, in the survey's own `-- path unmeasured:` voice rather than
  the gate's `RED` (#441). The survey is the one non-gating way to preview a
  landing's selection, and it previously named every module the `NO_TEST_MODULE`
  escape excuses and no module the `no_test_module` rung would red — so it could
  preview everything except the rung most likely to red the reader. It still
  never prints `RED` and still always exits 0.
- A refused `just mutation` run keeps its `-- path exempt:` lines (#441). Those
  are statements about the diff, true whatever the run did; the unmeasured lines
  are dropped in either voice, because they are computed from the subjects the
  verdicts selected and a refused run has only some of them. The refusal still
  exits 2.
- The `no_test_module` red now says which gate fetches for the reader — `just
  land` does before it gates, `just fast` never does — because a stale
  `origin/main` is the one cause of a false red here that cannot be computed
  away in-repo, and mid-work `just fast` is exactly where it survives. The
  trade-off is written beside the rung in `tools/mutation_smoke.py`: the wasted
  fetch a reader whose module genuinely is new will run is accepted, because the
  fetch writes nothing while both other remedies write code against a diagnosis
  that may be wrong.
