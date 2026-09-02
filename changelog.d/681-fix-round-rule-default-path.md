# Fixed

- **The fix-round report rule now reaches a retro dispatched without `--brief-file` (#681).**
  #374 composed the rule into `just brief --seat retro` output only, so the unnamed-file
  `just dispatch --seat retro` path carried none of it and the unswept issue the rule
  exists to make visible stayed silent by construction. The rule's one home is now
  `dispatch.FIX_ROUND_RULE` in `tools/dispatch.py` — read by the composer and by
  `default_brief()` alike, which emit it to a retro under the same seat predicate — and
  `default_brief()` gains no wording of its own: it imports the constant, so neither
  briefing path carries a copy that can drift.
