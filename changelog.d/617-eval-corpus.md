# Added

- `just eval-corpus` runs the eval corpus (`evals/corpus/`) against one or two agent
  configurations and reports a typed verdict per case — a rate over the task's stated
  repeats, judged against its tolerance — with the worst class as the exit code. The
  `AGENTS.md` ablation is the corpus's first task (full file, imperatives only, absent).
  `just eval-corpus --contract` prints the task↔runner contract, derived from the
  runner, so a key added to it appears there.
