## Fixed

- The dispatch harness now refuses its own commit when `.dispatch-commit-message` is
  tracked in the commit's tree, holding the push so the artefact cannot reach a review
  branch (#550); the path is also git-ignored, so a broad `git add` no longer stages it.
