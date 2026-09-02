# Added

- **The fix-round report rule, composed into `just brief --seat retro` output (#374).** A
  retro's fix round must list every issue its own pass filed with one verdict —
  `unchanged` or `corrected`, stating what changed or why not — so an unswept issue is
  visible rather than silent; a wrongly-swept one stays outside its reach. Each verdict is
  derived from the round's own sweep or transcribed from a deriver with attribution, never
  inherited wholesale. The rule lives in composed tool text rather than the retro skill
  file: #345/#349's evidence is that composed tool text beats contrary prose, and the
  skill surface is human sign-off gated — the choice and its reason are recorded on #374.
  Its home is `dispatch.FIX_ROUND_RULE` (#681), so the composer and the default brief read
  one wording.
