#### Added

- Every recipe that gates a landing now records a gate-clock row, and every row
  carries its legs. `just check` and `just mutation` join `just unit` and
  `just fast` in `~/.arma-cti/gate-clock/records.jsonl` (#483): the recipes
  hand their legs to a new `run` verb of `tools/gate_clock.py`, which runs them
  in order, records the whole recipe's row and each leg's name, outcome and
  wall seconds, and exits the legs' own status. A red leg stops the run and the
  legs after it are recorded `not_run` — never `passed` — so a recipe that
  short-circuited can no longer read as a fast green one, and a red run's shell
  line names every leg's outcome for the same reason. The row keeps every field
  it had: rows written before this change parse unchanged and read as carrying
  no leg breakdown, which is a fourth fact distinct from both `passed` and
  `not_run`. `mutation`'s body moved into a private `_mutation-body` recipe so
  its arguments still reach it through the runner, and `just fast` records four
  rows where it recorded two (its own plus each nested recipe's), all real
  measurements of real invocations.

#### Changed

- The gate-duration anchor file names every recipe the recorder writes, and the
  two no anchor has been derived for (`check`, `mutation`) carry
  `anchor_seconds: null`: a deliberate unset the loader reads, distinct from a
  dropped key, which remains damage. Those recipes report no drift assessment —
  recording widened, the assessment ladder, its threshold, its window and its
  anchors did not, and setting an anchor for them is the same deliberate
  hand-edit from `just gate-clock-history` it always was.
- The per-recipe recording scaffold (`/proc/uptime` at both ends, load average,
  foreign gate-process count, the collected-test count) moved from duplicated
  shell in each recipe into the one `run` verb, so all four recipes take their
  measurements with the same code. Recording stays advisory: an unreadable
  clock or an unwritable records directory prints to stderr and never changes
  the gate's own exit status.
