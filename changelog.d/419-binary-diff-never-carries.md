### Changed

- **A verdict is never carried across a moved SHA when the diff changes a binary file
  (#419).** #417's diff identity kept a binary change's `index` line byte for byte, on the
  argument that git will not merge binaries — so a same-file binary edit could not replay
  clean, so under any recorded clean rebase neither blob hash could have moved. The fourth
  review of #417 disproved it: `.gitattributes` decides what git compares as bytes and how
  git merges it independently, and `*.bin -diff merge=union` gives a path git calls binary in
  every diff and replays line-wise anyway — a same-file edit on both sides rebases clean and
  rewrites both blob hashes of the kept line, which is the base-dependence the identity exists
  to remove. `tools/review_exchange.py` now tags such an identity `binary:` where it computes
  it, and `satisfies` refuses `binary_diff_uncarried` on a moved SHA whatever the identity and
  the recorded rebases say. The exact SHA still clears, so the cost of the removed exemption is
  one fresh review of a kind of change this repository rarely makes, and the reasoning behind
  the rest of the identity becomes true rather than nearly true.
