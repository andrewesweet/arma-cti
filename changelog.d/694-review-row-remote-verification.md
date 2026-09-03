# Fixed

- The `just review` command-table row attributes the exchange's remote-SHA verification to the push: `exchange` resolves the issue-named worktree, pushes its HEAD to `refs/heads/issue-N` and verifies the remote resolves that exact SHA, while the `exchange_outside_issue_worktree` refusal only names both paths. The success path's guarantee is stated where it is delivered.
