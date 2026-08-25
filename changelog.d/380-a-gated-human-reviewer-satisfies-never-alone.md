### Changed

- **A gated human reviewer satisfies never-alone (ADR-0080).** The rule bars a single actor from
  both proposing and enacting a change unilaterally; it never constrained the reviewer's
  substrate. A different agent instance and the human both satisfy it. `review_same_profile`
  remains absolute, the derived reviewing identity for an agent reviewer is untouched, and the
  human sign-off gates are a separate question that this does not reach.
- **The mechanism does not implement the ruling yet, and fails closed.**
  `review_exchange.record_verdict` derives the reviewing identity from dispatch records and
  accepts nothing about who reviewed, so a human verdict cannot be recorded and `just land` still
  refuses `no_verdict`. Until a path exists, a landing is cleared by a dispatched instance as
  before and a human review is additional assurance on top.
