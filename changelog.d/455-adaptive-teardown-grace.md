### Changed

- `spike/run.sh` teardown now ends its SIGTERM grace once every child has exited, while retaining the existing two-second deadline for a child that remains running.
