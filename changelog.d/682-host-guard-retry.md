### Fixed

- The corpus host guard retries a non-zero `tasklist.exe` result twice at one-second gaps,
  giving the observed transient WSL interop failure a bounded chance to clear while still
  refusing when all three checks fail.
- Host-guard refusals retain `infra_unavailable` and identify whether a play session was seen
  or the process-list check failed.
