### Fixed

- The check-machine-b leg of `just check` no longer fails when the calling session captures
  its output directly: the recipe's ansible invocations go through `tools/blocking_exec.py`,
  which sets stdin, stdout and stderr to blocking before exec, satisfying ansible-playbook's
  blocking-IO precondition instead of tripping it (#678).
