### Fixed

- A typed non-result now releases its Work Item scheduling slot once the
  dispatcher's `result.json` has been read: the delivery collector records the
  publication as a Work Run fact (`result_published`), the policy releases the
  slot on that recorded fact rather than inferring it from state and recovery
  kind, and the journal carries the fact across cycles. A journal recorded
  before the field existed recovers at the next collection while its result is
  still published; a non-result with no published result — a pruned
  `result.json` (#625), or a typed delivery envelope, which nothing writes yet
  (#629) — still holds its slot (#624).
