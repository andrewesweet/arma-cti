### Fixed

- A dispatch process decides its review state root once: `write_record` records the stage
  arrival against the root the process already reads its authorship declarations from,
  `--review-root`'s default honours `CTI_REVIEW_DIR` like `--breaker-dir` honours its own
  variable, and `tools/review_loop.py`'s `--root` defaults do the same — an operator's
  override no longer reaches the stage arrivals while the declarations keep reading home,
  and `seam_env` names the root so a forked seam's arrivals land in the test's tree
  (#677).
