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
  orchestrator's and names the two narrow cases in which a manual relay is admissible;
  it adds the ledger materialisation owed before a run's spend or outcome is quoted,
  and the verbatim `just verdict` paste and `just trial close-audit` a close is judged
  from. The adjudication rule is stated as the code enforces it: nothing above Low is
  left open, and `accepted_and_filed` needs named work outside the diff on which the
  harm is conditional, so an unconditional defect is fixed rather than filed.
- **The tick now opens a controller reconciliation cycle, records how a gated path is
  approved, and says who declares an unclaimed change's author (#643).** On the
  human's rulings of 2026-08-29, the turn top runs `just controller reconcile`, which
  no earlier authority had bound to this seat, and it runs before the queue reads
  because its mutations would otherwise stale the selection; the landing section states
  the `just gated-paths` check and approval, the two ADR-0013 standing routes that stand
  in for an approval and what neither authorises, and that `.claude/commands/` is not on
  that list; and it states that a change no dispatch record claims declares its author
  with `just review-loop author`, a dispatched session not being one that writes under
  `.claude/`. The file supplies no mechanism for that last, the mechanism differing by
  lane and none having been verified here. The file also now states that the
  orchestrator seat holds its own waits, which is the opposite of the subagent rule.
