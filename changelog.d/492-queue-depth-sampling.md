## Added

- Seven queues nothing else watched are now sampled whenever the orchestrator's
  turn-top queue read runs: ready work, awaiting a dispatch slot, awaiting a
  reviewer, awaiting a human ruling, awaiting a lane window, awaiting a slot
  lock, and awaiting landing (#492). The sampler folds into `just
  watch-report`'s existing queue rung — no new process, recipe or state
  directory — and an idle, off-peak sample reads the policy file, the review
  waits journal, the review journal, and the review-root listing and its
  historical issue-directory stats. The dispatch waits journal is read only in
  the published peak band; the queue waits journal is not read by this sampler.
  The report's successful candidate read is shared with the sampler, including
  on a full-WIP turn.
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

## Fixed

- A refused tracker read now records the ready-work, dispatch-slot and
  in-band lane-window samples as `unrecorded`, carrying the refusal kind (for
  example `github_unreadable`) instead of journaling a counted zero. The
  observatory keeps that kind in the null count reason, and a present but
  unreadable queue-depth journal is named as malformed rather than treated as
  a sampler that never ran.
- The dispatch-slot sample keeps ordinarily eligible candidates refused only
  by the WIP limit in its population before subtracting available room, so a
  full-WIP sample reports the held population rather than zero. Boolean counts
  are rejected at the event boundary.
- A dry-run lane-window refusal no longer creates a wait journal, so a peak-band
  rehearsal remains read-only; freeze refusals and real planning refusals
  continue to journal their waits.
