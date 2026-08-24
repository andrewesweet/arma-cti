## Added

- Seven queues nothing else watched are now sampled whenever the orchestrator's
  turn-top queue read runs: ready work, awaiting a dispatch slot, awaiting a
  reviewer, awaiting a human ruling, awaiting a lane window, awaiting a slot
  lock, and awaiting landing (#492). The sampler folds into `just
  watch-report`'s existing queue rung — no new process, recipe or state
  directory — and an idle sample reads one policy file, three wait journals
  and the review journal, plus the tracker read that rung was already making.
- Each sample carries its queue's depth and, where a record carries the
  instant the oldest item entered, its age. A counted depth of zero, a queue
  no record carries (the slot-lock queue: the tier's bash seam journals
  nothing) and a source the sample could not read render as three different
  states — `counted`, `unrecorded`, `unreadable` — so an empty queue is never
  mistaken for an unread one. Where no record carries an item's entry instant
  (the ready queues' label times, the landing queue's demand side) the age
  states `unrecorded` rather than inventing one.
- The observatory store gains a `queue_depth` table — one row per queue per
  sample, `count` and `oldest_age_s` null where no number was read — with a
  coverage line and a cookbook query for the newest sample per queue. A
  sampler that has not run yet rebuilds as zero rows, never as a refusal.
- A dispatch refusal the planning choke journals as a wait now names its
  issue, so the lane-window queue can say which work a peak band holds.
