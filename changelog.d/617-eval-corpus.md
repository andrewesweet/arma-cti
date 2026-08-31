# Added

- `just eval-corpus` runs the eval corpus (`evals/corpus/`) against one or two agent
  configurations and reports each materialized task/configuration case with a rate
  only when all stated repeats complete and agree within tolerance; otherwise it
  reports the typed status and no partial rate. The worst status is the exit code. The
  `AGENTS.md` ablation is the corpus's first task (full file, imperatives only, absent).
  `just eval-corpus --contract` prints the task↔runner contract from the runner's
  field registries, so a key added to one of those registries appears there.

## Changed

- Eval trials now run in fresh bubblewrap filesystem/PID boundaries with a resolved,
  hash-recorded toolchain, live token/command usage enforcement, and per-run,
  hash-verified grader copies. `just prereqs check` reports the required `bwrap` host
  dependency, and pipeline tests skip when it is absent. Reports retain live usage when
  available and typed outcomes for every trial.
