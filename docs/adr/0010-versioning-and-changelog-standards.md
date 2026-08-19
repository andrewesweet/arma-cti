# Conventional Commits, Keep a Changelog, and SemVer, enforced by cocogitto

The project adheres to Conventional Commits 1.0.0, Keep a Changelog 1.1.0, and Semantic Versioning 2.0.0. Enforcement: cocogitto (`cog`, single Rust binary) provides a `commit-msg` git hook (`cog verify`) rejecting non-conforming messages, `cog check` over history (added to `just check` when it exists), and `cog bump --auto` deriving the SemVer bump from commit types at release time (tags `vX.Y.Z`).

`CHANGELOG.md` is curated, never generated from the commit log — Keep a Changelog explicitly rejects commit-log dumps. Practice: any commit with user-visible effect (`feat`, `fix`, behaviour-changing others) adds a uniquely named Markdown fragment under `changelog.d/` in the same commit; `cog bump --auto` collects those fragments into a dated version heading and removes them. The fragment directory is `[Unreleased]` between releases (#358, human rulings 2026-08-14 and 2026-08-16).

The versioned artefact is the scenario as a whole (addon + mission + daemon, released together). MVP era is `0.y.z`; `1.0.0` is cut when `docs/mvp-scope.md` is fully playable.
