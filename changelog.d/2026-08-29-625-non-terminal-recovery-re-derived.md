# Fixed

- The controller re-derives a non-terminal recovery look on every cycle instead
  of freezing it at first stamp, and a non-terminal look now writes only its
  verdict — never the Work Run's workflow state — so a `still_live` reading can
  no longer walk a reviewed, gated, stalled or interrupted run back to
  `running`. `lost_work` and `finished_and_cleaned` stay conclusions only where
  the tree holds no working process: the classifier scans the worktree for a
  live process before concluding, because unpushed commits are also what a live
  agent's ordinary progress looks like, and a concluded run beside its agent
  would release the work's slot.
