### Changed

- **An implementer may now run a bounded self-review inside its own Work Run before handing
  work to the independent reviewer (ADR-0079 ruling 1).** CLAUDE.md's rule against additional
  verification passes is amended rather than repealed: the self-review takes no dispatch and no
  subagent, and never substitutes for the independent review it precedes. It is admitted on the
  rule's own cost ground — 67.9% of the issues that reached review needed a second review
  dispatch, each costing an implementer run, a review run and a gate.
- **Behavioural acceptance obligations become executable specifications (ADR-0079 ruling 2).**
  Gherkin structure with the domain vocabulary closed against `CONTEXT.md`'s Language section,
  so an unresolved domain term fails at authoring time rather than at runtime. Recorded here as
  a decision; #379, #382 and #383 carry the work.
- **Cost gains a second unit: US dollars per landed Work Item, per lane (ADR-0079 ruling 3).**
  Plan percentage points remain the unit for deciding what to spend a subscription on;
  `list_price_usd` is re-scoped from "never a decision input" to the correct input for deciding
  whether to hold a subscription at all. Recorded here as a decision; #384 carries the work.
