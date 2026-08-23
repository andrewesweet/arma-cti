### Added

- Add a versioned harness-bundle renderer whose target capabilities are derived from implemented target adapter methods: Claude Code implements hooks and project instructions, while Codex implements project instructions and has no hooks destination.
- Permit dispatched writes only inside the renderer-owned temporary-layout entry point: it records the path at directory creation, verifies the object's current `.name` still matches that record, and writes to the recorded path. Caller-selected rendering and promotion refuse a live dispatch identity. Promotion checks current effective directory and file access and rejects non-file outputs, but cannot prove that filesystem access will remain unchanged between its preflight and writes.
- Compare generated paths, file bytes, and file modes deterministically, while explicitly excluding mtimes and created-directory modes. Expose render, check, and promote through `just` recipes.
