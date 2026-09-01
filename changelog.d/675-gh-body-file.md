### Fixed

- Added a fail-closed guard for shell-visible GitHub CLI body options: only recognised file-backed forms pass; inline and unknown forms direct agent and orchestrator posts to `--body-file` or `-F`.
