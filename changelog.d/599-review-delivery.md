#### Fixed

- Completed review dispatches now preserve unmarked stdout and plan-file text as explicitly
  unverified recovery when the text can be attributed to the dispatch window. The refusal,
  child return code, missing verdict, and review-loop state remain unchanged.

- Review plan recovery now uses a per-dispatch Claude `plansDirectory` in the disposable
  worktree instead of the shared `~/.claude/plans` directory. More than one regular plan file in
  the dispatch window fails closed without posting either file and records the candidate count;
  issue-comment size validation counts characters to match GitHub's limit.
