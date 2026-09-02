### Fixed

- A dispatch process decides its review state root once: `write_record` records the stage
  arrival against the root the process already reads its authorship declarations from,
  `--review-root`'s default honours `CTI_REVIEW_DIR` like `--breaker-dir` honours its own
  variable, and `tools/review_loop.py`'s `--root` defaults do the same — an operator's
  override no longer reaches the stage arrivals while the declarations keep reading home,
  and `seam_env` names the root so a forked seam's arrivals land in the test's tree
  (#677). The `REVIEW_ROOT` constant itself now derives from the variable at import
  (home when it is unset, as before), so the readers that resolve the constant rather
  than calling `review_root()` — `tools/land_review.py`'s authorship root and
  `tools/review_exchange.py`'s two `--review-root` defaults — honour the override too.
  A tilde-valued root — a quoted `--review-root '~/.review'` or a literal `~` in
  `CTI_REVIEW_DIR` — now expands at the flag, the one place the root is decided, so the
  readers and the stage-arrival writer hold one root a process can name (#677).
