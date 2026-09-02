### Changed

- `tests/unit/test_pool_slots.py`'s two fixed settles — the 3 s no-respawn
  confirms after the watchdog kill and after the signalled pool's teardown — are
  shortened to 1 s, five of the heartbeat's own 0.2 s periods, and the kept waits
  now state their floors where a reader meets them (#457).
- The module's mutation exemption is re-measured and kept rather than removed:
  the conversion found only 6 s of test-side settle, the shell arm's rate against
  `spike/regress.sh` measured 40% (4/10, sampled) on both sides of the conversion,
  and one serial run remains within seconds of its 199.33 s re-measure — so a
  landing that touches the module still spends the five-minute ceiling on
  `just fast` (#457).
