## Fixed

- The dispatch-slot queue's depth now agrees with what `just queue next`
  refuses rather than approximating it: a candidate held out by a package
  reservation is counted, because a reservation is a reason there is no slot,
  exactly as a full WIP list is. The freeze and blocked exclusions are staged
  through the sampler in tests, so the parity with `select`'s own drops is
  asserted rather than argued from shared code (#554).
- A review journal the sampler could not read no longer renders every
  `human_ruling` age as `unrecorded` beside a counted depth: the queue states
  `unreadable`, the same vocabulary a damaged `loop.json` already gets, while
  the terminus prompts of the loops that did read still render (#554).
- The `human_ruling` queue's narrowing — the open above-Low set of loops still
  running, never every open finding — is now stated where the number is read:
  the observatory's queue-depth report line and the cookbook's queue-depth
  paragraph (#554).
