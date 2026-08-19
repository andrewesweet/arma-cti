### Fixed

- **The prose left behind by routing class 6's retirement now describes the rung that
  replaced it, and the landing rung's pre-gate position is behaviourally covered again
  (#410).** Five of the six low findings filed from #406's two reviews; the sixth is
  proposed rather than landed.

  Three were stale descriptions of a retired rule. `docs/multi-provider-dispatch.md` cited
  class 6 as a fourth reason no dispatched session could land under `.claude/` unilaterally,
  and `tests/unit/test_dispatch.py` called class 6's keep-on-Claude bridge the project's
  other lane-selected refusal in three places. ADR-0073 (#406) retired that bridge, so the
  orchestrator carve-out is the only lane-selected refusal anywhere, and class 6's naming of
  `.claude/hooks/` and `.claude/settings.json` now buys a cross-lane preference on the
  *review* that clears a gate landing rather than a bar on which lane may land. Each is
  corrected in place; the conclusions they support are unchanged, and the doc's says so.
  The migrated `changelog.d/000-existing-unreleased.md` also pointed forward to an entry
  that sits above it and cited an ADR-0073 heading that its second commit had renamed.

  Two were test coverage. `tests/unit/test_land.py` lost `gate.calls == []` when the test
  carrying it was replaced by the two ADR-0073 landings, leaving "the routing rung refuses
  before the gate runs" proven only by a dry run, where no gate exists to observe; it is
  restored as a real landing against a planted refusing row.
  `test_the_retired_exception_markers_no_longer_appear_anywhere` asserted over an exception
  list that ships empty and so observed nothing; it now reads the same predicate over a
  planted document that does declare a withdrawn marker, so a guard that went blind reds.

  Finding 4 is a wording change to `AGENTS.md`, which is a human sign-off gate: the corrected
  wording is proposed on the issue and the file is untouched.
