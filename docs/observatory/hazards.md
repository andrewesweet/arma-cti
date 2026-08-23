# The observatory's hazards list

The traps that cost an analyst an hour each, seeded with the ones already known.
Each names its mechanism, because the second occurrence of a trap is always wearing a
different issue number.

## 1. The two spend encodings

Claude emits per-request token counts as attributes on `claude_code.api_request` log
records. Codex emits `codex.turn.token_usage` as a **histogram metric** whose
datapoints carry a `token_type` attribute — no `asInt`/`asDouble` at all; the count
stands in the datapoint's `sum`.

**A reader that understands only one encoding returns rows, looks correct, and books
an entire lane at zero.** That is #458's most-repeated defect in a new place, and
nothing downstream notices, because there is no independent figure to disagree with.

The store reads both (`spend_encoding` names which one a row read) and selects rather
than sums when a dispatch carries both. Two corollaries:

- A lane reading zero is not evidence the lane was cheap — check `spend_encoding` and
  `spend_encoding_reason` first. Absent and cheap are different facts.
- Codex's `total` and `reasoning_output` token types are non-disjoint subsets and are
  excluded, exactly as `tools/ledger.py` excludes them; bucketing either would inflate
  every Codex row and nothing would notice.

## 2. Truncated lines in the archive

The export files are appended while agents run, and a writer killed mid-line leaves a
truncated JSON line behind — four exist in the archive today. A reader that skips
unparseable lines silently is indistinguishable from a reader that read everything
(#496), and the parse boundary took six rounds to get reported rather than swallowed
(#503).

The rebuild counts every unparseable line, names its file, completes, and prints the
count in its coverage line. **If `malformed_lines` grows between rebuilds, that is a
finding about the writers, not noise to absorb** — and a dispatch whose spend was read
despite malformed lines read only the lines that parsed, so its figure is a floor.

## Standing rules beside the traps

- **Never sum spend across lanes** — the negative test in `tests/unit/test_observatory.py`
  exists because this is enforced mechanically or not at all.
- **A lane with no calibration renders `uncalibrated`, never zero, never a smaller
  number.** This session has already conflated absence with a value four separate
  times (#502 twice, #503, #527).
