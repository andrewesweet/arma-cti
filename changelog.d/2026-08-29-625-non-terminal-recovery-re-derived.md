# Fixed

- The controller re-derives a non-terminal recovery look on every cycle instead
  of freezing it at first stamp, and a non-terminal look now writes only its
  verdict — never the Work Run's workflow state — so a `still_live` reading can
  no longer walk a reviewed, gated, stalled or interrupted run back to
  `running`. `lost_work` and `finished_and_cleaned` stay conclusions only where a
  listable `/proc` scan positively finds no dispatch process: no matched or
  deleted-cwd process, and no same-user or owner-unknown process whose cwd could
  not be read unless its `/proc/<pid>/stat` start time proves it predates the
  dispatch record. Foreign-user unreadable cwds, pre-existing unreadable cwds,
  and cwd failures on a known controller-chain process, are excluded by known
  owner, start time or identity. Unpushed commits are also what a live
  agent's ordinary progress looks like, so an incomplete scan keeps the slot
  and reads `still_live` rather than releasing it onto unproven liveness;
  `just dispatch --stop` refuses before signalling when an incomplete scan has
  no positive match, and otherwise signals the matched set while reporting an
  unverified finding if its post-signal visibility is incomplete.
