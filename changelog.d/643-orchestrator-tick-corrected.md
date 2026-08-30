### Changed

- **`/orchestrator-tick` is corrected against the code rather than remembered (#643).**
  An audit against `origin/main` found that
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
  Low is left open, and which route a finding may take, outside the cap the human's ruling
  sets, is left to
  `docs/agents/review-severity.md` and `_route_checks`. The file carries only the part
  no check can catch, that `_route_checks` verifies `--conditional-on` is non-empty and
  nothing more.
- **The tick now runs a controller reconciliation cycle, records how a gated path is
  approved, and says who declares an unclaimed change's author (#643).** On the
  human's rulings of 2026-08-29, the turn top runs `just controller reconcile` after
  `just watch-report`, a recipe no earlier authority had bound to this seat; the
  landing section states
  the `just gated-paths` check and approval, the two ADR-0013 standing routes that stand
  in for an approval and what neither authorises, and that `.claude/commands/` is not on
  that list; and it states that a change no dispatch record claims declares its author
  with `just review-loop author`, a dispatched session not being one that writes under
  `.claude/`. The file supplies no mechanism for that last, the mechanism differing by
  lane and none having been verified here. The file also now states that the
  orchestrator seat holds its own waits, which is the opposite of the subagent rule.
- **The tick's three missing review and dispatch obligations are restored, and the
  two-review cap is kept over the ADR that contradicts it (#643).** Harvest dispatches
  the `review` seat it had skipped between exchanging a branch and recording a verdict;
  the landing section adds the post-landing `review` pass, bound to the landed SHA by a
  re-exchange and a `--base-sha`, since `just land` pushes `HEAD:main` alone and never
  moves the issue ref review dispatch restores; and dispatch preparation names
  `just worktree add` and the continuation's first `just handoff` read. A gate-clock
  drift line is given the response it lacked, `just gate-clock-history` before an anchor
  move is proposed. Three claims about the code are corrected: exit code 0 is the
  invocation's success rather than proof of a landing, since a clean `--dry-run` or
  `--stage` also exits 0 and prints `landed=no`;
  `just queue next` returns eligible candidates in issue-number order rather than a
  ranking of kinds; and `quota_exhausted` is taken off the escalation list, the response
  being another lane or the provider's published reset. The false justification for
  running the controller first is deleted rather than replaced, `default_controller`
  wiring its worktree, dispatch and evidence ports to a refusing
  `UnsupportedActionPort`. On the human's ruling of 2026-08-29 the two-review cap binds
  and ADR-0071's three fix rounds are the error: the file records that, says the cap
  counts review rounds rather than findings, states that a deletion or a narrowing at
  the cap still owes a fresh verdict on the SHA it produces, and points #645 at both the
  ADR's correction and the cap's missing in-tree home.
