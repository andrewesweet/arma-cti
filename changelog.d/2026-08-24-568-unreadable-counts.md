### Fixed

- **`just land` and `just land --stage` refuse by name when `git rev-list --count` cannot be
  read, instead of reporting a zero (#568).** Four counts spent `counted`'s "could not be read"
  answer with `or 0`, so an unreadable count masqueraded as a decision: a tree whose count git
  failed to take was refused `nothing_to_land` with "check you committed it" — words that send
  an operator hunting for uncommitted work while the failure was git's — and the report line
  `rebase=already_current`, which a reader consults to decide whether a review verdict still
  binds, was printed on a base whose movement was never established. Every required count now
  refuses `git_failed` naming the exact range that could not be read, the same ladder the
  protocol already used for its ahead-count; the main-checkout count keeps its distinct
  unreadable answer, which `nothing_to_land` already reads as "not a zero". At the three
  ahead-count and recount sites the change is in words only — an unreadable count refused
  before and refuses now — but the two incoming-count sites change what the protocol
  decides: the old code read an unreadable incoming count as zero and carried on, `land`
  through rebase, gate and push and `stage` all the way to `ok=staged`, each report carrying
  the false `rebase=already_current` line, and the new code refuses `git_failed` before the
  rebase.
