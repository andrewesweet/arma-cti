# Added

- `docs/agents/dispatched-session-commands.md` gains a designed experiment for what git
  history rewriting a dispatched session can perform (#695): the arrangement, hypothesis,
  falsifier and route list were committed before any command ran, and a second commit on
  the same branch fills in the results with literal commands and verbatim outcomes. The
  headline result falsifies the experiment's own hypothesis: a genuine four-into-one
  collapse was performed on a dispatched session's surface with permitted commands —
  `git rebase --onto` drops the commits, and the session re-authors the tip's tree and
  commits once — while every git-side collapse verb measured (`reset`, `commit-tree`,
  `update-ref`, `branch`, `merge`, `checkout <sha> --`, `apply --index`, `config`) and
  every route to a rebase todo editor is refused. `git rebase -i` is measured running to
  completion non-interactively with the todo unmodified: it drops, reorders and replays,
  and squashes nothing. #691's `git rebase --onto <parent> HEAD` is reproduced and
  recorded as a drop, not a collapse. Refusals are classified into three witnessed
  origins — harness approval demand, git's own `fatal:`, and this repository's cocogitto
  commit-msg hook.
