## Added

- `just ledger-sync` records a terminal state for work that started and did not
  finish (#489): a `terminal_state` block on the dispatch's own `ledger.json` —
  `{"state": "abandoned", "class": <failure class>}` — so abandoned and completed
  work are distinguishable by the record alone. One `cti.terminal.state` event is
  journalled beside the record (`terminal.jsonl`) on the first sync that records
  the block, fail-open over the emission: a failure to record degrades to no
  record and never reaches the dispatch. The event's names and the four-class
  not-a-result vocabulary live in the attribute registry
  (`NOT_A_RESULT_CLASSES`), which `gate_outcome` now reads instead of holding its
  own tuple — one home, derived, never a parallel table.

## Changed

- `gate_outcome` types `untyped_harness_failure` as not a result, which CLAUDE.md
  ranks above every other class and which the old tuple omitted (#489). A run
  whose own closeout failed (`harness_failed_after_child`, `child_state_unknown`)
  now types that class rather than `ok`, and the dispatcher's `outcome`
  classification of its run's log is read: `quota_exhausted` types the run
  quota-exhausted, `provider_error` types it a lane that could not be reached.
  Codex's `You've hit your usage limit` sentence now matches the breaker's quota
  markers, so the next run that dies on it is classified at all — the live death's
  own record keeps the `unclassified` its dispatch-end classification wrote and
  still types `unknown`, because records are immutable and the rebuild reads
  `outcome` rather than re-classifying the log. A refusal that fired
  before the child launched keeps its failure class but reads `never_started`,
  because work that never started is not work that started and did not finish.
  In the observatory's flow view these moves retype work: harness failures and
  log-classified quota deaths move from `stopped` to `abandoned`, and pre-child
  refusals move from `abandoned` to `stopped`. The item's state is weighed by
  seat: only a dispatch of a seat that lands work may brand its issue abandoned,
  so a review or recon dispatch that died not-a-result keeps that outcome on its
  own row and never abandons work whose implementer dispatches succeeded —
  #524 read abandoned on exactly that shape before the weighing.
- `otel_event.emit` no longer raises when its journal cannot be written, closing
  the gap between its stated contract — emission never fails a caller — and the
  one line that could.
