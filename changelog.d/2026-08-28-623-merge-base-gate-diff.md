# Fixed

- `just gated-paths check` now diffs against the merge-base of `HEAD` and `origin/main`, so a branch behind `main` on a gated path is no longer refused for an edit it did not make (#623); a branch that does change a gated path is refused exactly as before, and an unreadable or unrelated `origin/main` is a typed `gated_paths_unreadable` refusal rather than a pass.
