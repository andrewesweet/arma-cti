### Fixed

- The stop-sweep closeout is now recognised by one predicate, `dispatch_stop.is_stop_closeout`, derived by all three of its readers (`occupancy.py`, `review_exchange.py`, `observatory.py`) rather than spelled three ways, so a record one reader would accept and another reject — a `terminal_state` block the sweep did not write — can no longer occur. The observatory's stop-sweep reason and `_ended_for` docstring now describe the shape the predicate actually reads. (#558)
