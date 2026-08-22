### Fixed

- **`just land` no longer infers a close audit from three recipe-name substrings (#499).**
  `AUDIT_MARKERS`, `AuditRead`, `read_audit` and the issue-comment scan are removed. A review
  quoting `just check`, `just unit` and `just mutation`, a comment asserting those records are
  absent, and an audit split across existing comments now have the same effect: none can satisfy
  the close because the closing path never reads them.

- A real landing now requires `--audit-file FILE`. The file supplies one complete UTF-8
  criterion audit and is read before any repository step. After the push and main-checkout merge,
  the rung posts that body plus the landed SHA through one bounded
  `gh issue comment --body-file -` call. Only that call's successful receipt reaches the separate
  `gh issue close`; `audit_recorded=no` withholds the close without changing the successful
  landing result. The documented split-audit false negative is resolved at the author interface:
  the complete audit is supplied in one file and posted in one comment. The implementer's earlier
  gate report remains a separate thread comment for the reviewer.

- `audit_recorded=yes` reports `verified=posting_call` and
  `not_verified=content_or_quality`. The mechanism does not inspect whether the supplied body is
  complete, accurate or an audit, and it does not judge audit quality; those remain review and
  human judgements. A caller can deliberately supply non-audit prose. This protects the close
  from incidental or quoted comments, not from deceptive use of the explicit audit input.

- A stricter heading or sentinel was rejected because it would be another caller-emittable token.
  Removing automatic close was also rejected: it would restore one hand action to every landing,
  after #439 measured eighteen landed issues left open under that arrangement. The successful path
  still makes two bounded tracker calls; #461's read-plus-close pair becomes post-plus-close.

- The post and close remain separate because `gh issue close` has no body-file input. A process
  death between them can therefore leave a rung-posted audit on an open issue. A returned close
  failure after `audit_recorded=yes` authorises the documented hand close; there is no automatic
  retry or deduplication, and a timed-out post may already have reached GitHub.
