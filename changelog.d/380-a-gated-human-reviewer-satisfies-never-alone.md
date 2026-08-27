### Changed

- **A gated human reviewer satisfies never-alone (ADR-0080).** The rule bars a single actor from
  both proposing and enacting a change unilaterally; it never constrained the reviewer's
  substrate. A different agent instance and the human both satisfy it. `review_same_profile`
  remains absolute, the derived reviewing identity for an agent reviewer is untouched, and the
  human sign-off gates are a separate question that this does not reach.
- **The mechanism now implements the ruling (#586).** `review_exchange.record_human_verdict`
  records a human verdict bound to the exact reviewed SHA and diff identity, and `just land`
  accepts it with `reviewer_kind=declared review_dispatch=none`. The dispatched-session refusal,
  author-cannot-review check and derived agent-review path remain intact.
