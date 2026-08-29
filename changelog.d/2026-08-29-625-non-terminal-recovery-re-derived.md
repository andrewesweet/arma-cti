# Fixed

- The controller no longer freezes a recovery verdict at first stamp: `still_live`
  and `unproven` are re-derived on every cycle, so a dispatch classified healthy
  at one cycle can resolve once its agent has died without publishing a result.
  `lost_work` and `finished_and_cleaned` remain conclusions and stay sticky.
