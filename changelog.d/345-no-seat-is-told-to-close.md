### Fixed

- **No composed brief instructs its seat to close the issue any more, because closing is
  the landing rung's act (#345, #439).** The Landing section of every brief composed for
  a writable seat ended with *"Close #N with a criterion-by-criterion audit"* — right
  before ADR-0071, stale after it: ruling 4 split proposer, reviewer and lander, and
  #323's seat closed its issue on the composed line alone, before any review existed and
  before anything reached `main`, and the issue had to be reopened. The sentence is not
  softened but replaced, because #439 landed in between and put the close inside `just
  land` itself, on its success path and nowhere else: a seat obeying the old wording now
  walks a second mechanism onto ground the rung already covered and finds the issue
  already closed. The brief for a lander instead names the rung as the closer — the
  landing's own `issue_closed=` line is part of the verbatim paste, and an
  `issue_closed=no reason=…` is reported, never retried by hand.

- **The seat registry gains a `lands` column, and the brief's Landing section composes
  from it in three shapes (#345).** Two rows carry `True`, each on its ruling's own
  words: `implementer` (ruling 2: *"carries the work out … and lands it"*) and `retro`
  (A4: the journal entry *"lands under ruling 4 like any other change"*, one artefact
  scoped in the seat's own reason). A lander keeps the verbatim-paste rule and the
  adjudication routes and is owed the criterion-by-criterion audit as a thread report —
  #449's review reads exactly that paste as its gate record, so the audit was never the
  close's private form. A writable seat the registry does not name as lander (`planner`,
  `fable`, `orchestrator`) keeps the commit instruction and is told, in the section
  itself rather than in orchestrator prose, to leave the issue open: the
  two-disagreeing-instructions shape the issue exists to remove. The forced-read-only
  seats (`review`, `recon`) already landed in that arm via #421's `judgement_only`
  predicate and are untouched.

- **The judgement call that survives is recorded, not implied: `fable` and the
  `orchestrator` are not landers (#345).** No ruling names either as any route's lander —
  every routing route names `implementer`, and class 3 refuses the orchestrator
  outright. `tools/ledger.py`'s `SEAT_LANDS` carries `work` for both, but that table
  classifies what a finished run's record reads as having landed; it is a view over
  records, not a fact a brief is composed from, and the two are held in step by name-set
  only. A unit test pins the lander set to exactly `{implementer, retro}`, so a new seat
  arrives decided rather than silently inheriting the landing protocol.
