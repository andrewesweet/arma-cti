# Fixed

- `just gated-paths` again compares every substantive field of the record it finds at the content-addressed name against the current binding — `issue`, `path`, `base_sha`, the recorded result payload and the binary flag, with only the `change_id` tolerated as moved — so a record altered behind the gate is refused `approval_unreadable` rather than cleared as recorded. A moved `change_id` alone is still named `not_carried=change_id_mismatch` with the fresh commands printed (#623).
