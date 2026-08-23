### Added

- Add a versioned harness-bundle renderer whose target capabilities are derived from implemented target adapter methods: Claude Code implements hooks and project instructions, while Codex implements project instructions and has no hooks destination.
- Permit dispatched writes only when the central write boundary receives an actual temporary-directory object and derives the destination from it; caller-selected rendering and promotion refuse a live dispatch identity. Promotion checks current effective directory and file access and rejects non-file outputs, but cannot prove that filesystem access will remain unchanged between its preflight and writes.
- Compare generated paths, file bytes, and file modes deterministically, while explicitly excluding mtimes and created-directory modes. Expose render, check, and promote through `just` recipes.
