# Fixed

- The controller re-derives a non-terminal recovery look on every cycle instead
  of freezing it at first stamp, and a non-terminal look now writes only its
  verdict — never the Work Run's workflow state — so a `still_live` reading can
  no longer walk a reviewed, gated, stalled or interrupted run back to
  `running`. `lost_work` and `finished_and_cleaned` stay conclusions only where
  the scan positively found nobody working in the tree — no process, no
  unreadable cwd on a process of the controller's own user, no deleted cwd
  inside the tree, and a `/proc` it could list — because unpushed commits are
  also what a live agent's ordinary progress looks like, and any look that
  could not be made keeps the slot and reads `still_live` rather than
  releasing it onto unproven liveness.
