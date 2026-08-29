### Changed

- **`/orchestrator-tick` is corrected against the code rather than remembered (#643).**
  An audit against `origin/main` found twenty defects in the file, six of them high:
  the `review-loop adjudicate` command it printed omitted two required arguments and
  could not run; it named neither `just review-loop sync` nor `just review-loop
  terminus`; it stopped at `just land` and omitted the landed-issue projection the
  orchestrator must regenerate and commit afterwards; and it stated a global lane
  order of preference that no registry holds. The file now carries the turn-top read,
  the `sync` and `terminus` routes, the landing's `--corpus` obligation, the landing
  exit codes and the four `gate_review=` causes, the post-landing observatory commit,
  the canonical dispatch form, the codex instruction-delivery preflight, the
  cohort-follow rule, ADR-0080's registered human reviewer and ADR-0079's bounded
  implementer self-review. The stale lane-order narration is replaced by a preference
  among admissible lanes, the copied WIP ruling is dropped in favour of reading it
  from `just queue state`, the priority list names kinds rather than issue numbers,
  and every drifted line-number citation is replaced by a symbol or section anchor.
  Harvest now states that review delivery is the dispatcher's rather than the
  orchestrator's and points at `docs/review-dispatch.md` and `deliver_review` for which refusal admits
  a relay rather than restating the state machine;
  it adds the ledger materialisation owed before a run's spend or outcome is quoted,
  and the verbatim `just verdict` paste and `just trial close-audit` a close is judged
  from. The adjudication rule is reduced to the one obligation and a pointer: nothing above
  Low is left open, and which route a finding may take is left to
  `docs/agents/review-severity.md` and `_route_checks`. The file carries only the part
  no check can catch, that `_route_checks` verifies `--conditional-on` is non-empty and
  nothing more.
- **The tick now opens a controller reconciliation cycle, records how a gated path is
  approved, and says who declares an unclaimed change's author (#643).** On the
  human's rulings of 2026-08-29, the turn top runs `just controller reconcile`, which
  no earlier authority had bound to this seat, and it runs before any read that
  selects, `just watch-report`'s own queue report included, because its mutations would
  otherwise stale a selection already taken; the landing section states
  the `just gated-paths` check and approval, the two ADR-0013 standing routes that stand
  in for an approval and what neither authorises, and that `.claude/commands/` is not on
  that list; and it states that a change no dispatch record claims declares its author
  with `just review-loop author`, a dispatched session not being one that writes under
  `.claude/`. The file supplies no mechanism for that last, the mechanism differing by
  lane and none having been verified here. The file also now states that the
  orchestrator seat holds its own waits, which is the opposite of the subagent rule.
