### Changed

- **`just land` no longer closes an issue whose thread carries no criterion audit (#461).** #439
  automated the close and, with it, silently dropped the protection the prose close had carried:
  the criterion-by-criterion thread audit (`THREAD_AUDIT_RULE`) that the tracker's own closing rule
  requires. A missing or stale audit could therefore coexist with `issue_closed=yes`. Before
  closing, the landing now reads the issue's thread and withholds the close where no audit is on
  it. The check is presence, not quality: any single comment naming `just check`, `just unit` and
  `just mutation` counts, because a rung cannot judge an audit and every instance of #458's class
  was a check standing in for a judgement. The withheld close never fails the landing — the work is
  already on `origin/main` — and the printed reason keeps the two causes apart:
  `reason=audit_absent` means an audit is owed (post it, then close by hand with the criterion
  comment, since a re-run has nothing left to land), while `reason=audit_unreadable` prefixes `gh`'s
  own vocabulary and means the thread could not be read, so nothing is owed yet. The read adds one
  `gh` round trip to every successful landing, bounded by the same 20 s whole-call deadline that
  kills the `gh` child as the close does (#425's shape, because a socket timeout does not reach
  `getaddrinfo`, #427).
