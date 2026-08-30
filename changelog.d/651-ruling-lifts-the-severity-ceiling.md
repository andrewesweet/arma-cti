### Added

- **`just review-loop adjudicate` takes `--ruling` for `accepted_and_filed` above Medium
  (#651).** The ceiling itself is unchanged: without the flag, an above-Medium
  `accepted_and_filed` still refuses with the same message and its #334 citation. With the
  flag, the adjudication carries the ruling's own words beside the value it authorises —
  the shape `just queue`'s write verbs already use — and the flag is otherwise identical to
  the unflagged form: `--filed-issue` and `--conditional-on` are still both required.

- **The ruling travels with the adjudication.** It is stored in `loop.json`, read back by
  `just review-loop show`, carried on the landing record the terminus writes, and emitted
  as `cti.review.ruling` on the dispute event (registered as
  `conditionally_required` in the attribute registry). An above-Medium adjudication whose
  ruling later vanishes from the record refuses the landing at `stored_route_violations`
  exactly as it did before.

- **A session carrying `CTI_DISPATCH_ID` is refused from supplying a ruling.** A human
  ruling is transcribed by the human's own session; a dispatched agent quoting one would be
  the ruling's author in fact while naming the human as its source. The refusal names
  itself as a mechanical floor and not an identity proof, as `just review-loop author`'s
  and `just gated-paths approve`'s refusals of the same shape already do. Without a
  `--ruling`, a dispatched session's `adjudicate` is unchanged.

- **A ruling offered without words is refused by name at every severity.** `--ruling ""`
  and a whitespace-only ruling both refuse as `RULING_EMPTY_ERROR`, on any route and at
  any severity, rather than being stored or read as no flag at all. The flag's absence is
  distinguished from its text, so the dispatched-session refusal fires on the flag being
  passed rather than on what it carries.

### Changed

- **ADR-0071 ruling 4 and `docs/agents/review-severity.md` record the lifted ceiling
  (#651).** The Medium ceiling on `accepted_and_filed` (human ruling 2026-08-14, #334)
  stands as the default, and a human ruling quoted on a named finding lifts it for that
  finding alone — transcribed as ADR-0071 amendment A11 from the human's ruling of
  2026-08-30 on #643, with the same qualification where the severity guide states the
  ceiling.
