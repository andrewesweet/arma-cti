### Fixed

- Real-process seam tests now protect `just worktree archive <name> --ref <ref>` removing a
  tree preserved on that remote ref, `restore <name> --ref <ref>` recreating its exact HEAD,
  and bare `just worktree` refusing a dirty tree through its default pre-flight. The archive
  and restore cases use a valid Git ref containing literal `$$`; replacing positional `"$@"`
  forwarding with unquoted `{{ args }}` expands it to a shell PID and makes both cases fail
  through changed process behaviour.

- Bare `just worktree` passes zero arguments under both forwarding forms, so its behaviour test
  cannot detect that substitution. Proving positional forwarding for that zero-argument case
  would require a different recipe, a synthetic subcommand, or acceptance that this seam cannot
  be distinguished behaviourally.
