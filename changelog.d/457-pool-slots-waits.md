### Changed

- `tests/unit/test_pool_slots.py`'s two no-respawn confirms — after the watchdog
  kill and after the signalled pool's teardown — are kept at 3 s and now state
  their argument where a reader meets them: each is an absence window, the
  thing its own assertion bounds, so shortening one would save cost and narrow
  the claim with it; the claim is the reason neither is shortened (#457).
- The module's mutation exemption is re-measured and kept rather than removed:
  the conversion pass found 6 s of test-side settle and removed none of it, and
  the shell arm's rate against `spike/regress.sh` measured 40% (4/10, sampled)
  with its sampled run alone taking 320.0 s against the arm's 150 s budget — so
  a landing that touches the module would, without the exemption, spend the
  five-minute ceiling on `just fast` in the mutation arm alone (#457).
