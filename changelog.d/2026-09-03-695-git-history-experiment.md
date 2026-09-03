# Added

- `docs/agents/dispatched-session-commands.md` gains a designed experiment for what git
  history rewriting a dispatched session can perform (#695): the arrangement, the
  hypothesis and its falsifier, and the twelve routes to be provoked are committed before
  any command ran, and a second commit on the same branch fills the results rows. The
  collapse shape #668 actually needed — four commits into one — is built on a scratch
  repository inside the worktree, so no scratch commit can reach a landing branch.
