### Fixed

- `just mutation` now states whether its run was sampled or exhaustive, so an
  implementer's verbatim gate paste carries the distinction without requiring either the
  implementer or reviewer to derive it from the mutant counts. Dropped candidates count as
  sampled, and each module's verdict states its own coverage (#445).
