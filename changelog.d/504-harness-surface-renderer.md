### Added

- Add a versioned harness-bundle renderer whose target capabilities are bound to the renderer's support registry: Claude Code has hooks and project instructions, while Codex has project instructions and no hooks destination.
- Confine dispatched writes to renderer-owned temporary layouts; caller-selected rendering and promotion refuse a live dispatch identity. Promotion checks current effective directory and file access and rejects non-file outputs, but cannot prove that filesystem access will remain unchanged between its preflight and writes.
- Compare generated paths, file bytes, and file modes deterministically, while explicitly excluding mtimes and created-directory modes. Expose render, check, and promote through `just` recipes.
