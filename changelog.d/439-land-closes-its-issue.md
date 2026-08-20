### Added

- **A successful `just land` closes the issue it landed, with a comment naming the SHA (#439).**
  Closing was a prose obligation with no mechanism, and at the time this was filed eighteen landed
  issues were still open, ten of them from previous sessions — an open list that includes finished
  work is a queue nobody can read. The issue is the one the worktree is named for, taken from
  `_issue_from`'s existing derivation rather than a second copy of it, and a landing from a tree
  that is not an `issue-<n>` one says `issue_closed=no reason=issue_unknown` rather than guessing.
  The eighteen were closed by hand under the same instruction; nothing here closes a backlog.

### Changed

- **The close cannot fail a landing, and says so in the landing's own output (#439).** The work is
  on `origin/main` by the time it runs and the issue's state is bookkeeping, so `gh` absent,
  unauthenticated, rate-limited or stalled is one `issue_closed=no issue=<n> reason=…` line and the
  landing still prints `ok=landed` and exits 0 — a landing that reds because GitHub was unreachable
  would be a worse defect than the open issue this fixes. The reason is collapsed to one line and
  capped, so a proxy's error page cannot become the last thing a successful landing says. The call
  is bounded by a 20 s deadline that kills the `gh` child, `worktree.git`'s whole-call property
  (#425) on the subprocess a `gh` read already is, because a socket timeout does not reach
  `getaddrinfo` (#427). The seam is a parameter resolved at call time, and the unit tier replaces
  it for every test in the module, so no test reaches the tracker.
- **`EXIT_LANDED_INCOMPLETE` leaves the issue open, and the re-run that completes the landing
  closes it (#439).** The push has happened there, which is an argument for closing, but that exit
  code means "a step is outstanding" and a closed issue is how an outstanding merge gets forgotten
  — ADR-0042's stale-hook window, which `merge_blocked_by_sandbox` exists to make loud. Nothing is
  lost by waiting: the documented recovery is to run `just land` again, and that re-run reaches the
  same single closing site through its nothing-to-push branch. Both `ok=landed` branches — the
  fast-forward and `landed_from_the_main_checkout` — close through that one site, so "landed" and
  "closed" are one condition rather than two that can disagree.
