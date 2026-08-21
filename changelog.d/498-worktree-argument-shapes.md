### Fixed

- Real-process seam tests now protect `just worktree archive <name> --ref <ref>` removing a
  tree preserved on that remote ref, `restore <name> --ref <ref>` recreating its exact HEAD,
  and bare `just worktree` refusing a dirty tree through its default pre-flight. Each case also
  requires positional `"$@"` forwarding, so replacing it with interpolated `{{ args }}` makes
  the case fail.

- Worktree recipe-seam coverage does not include a flag without a value, a name containing a
  space, an argument that looks like a flag, or shell metacharacters. The tool layer rejects the
  first three relevant invalid shapes, but those refusals do not cross the recipe process.
