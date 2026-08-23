# The observatory cookbook

The queries this project has already asked, in the form that answers them. Every
query here runs against the shipped store in `tests/unit/test_observatory.py` — a
cookbook that does not run is worse than none — and the tables and columns are those
of `docs/observatory/schema-reference.md`, verbatim.

Rebuild first; the store is a cache and never a source of truth:

```
just observatory
```

## What a landed issue cost, per lane, in that lane's own meter

The store's first question (#482). Spend is per lane and never summed — the three
meters do not convert (ADR-0061 Decision 5) — so the answer is always a set of rows,
one per lane, each in its own meter. Never aggregate over this table's lanes.

```sql
SELECT issue, lane, dispatches, spend_dispatches, output_tokens, meter, cost, cost_reason
FROM issue_cost
WHERE landed = 1
ORDER BY issue, lane
```

Reading it: the Claude lane's `cost` is five-hour-window points; every other lane's
`cost` is `null` with an `uncalibrated` `cost_reason`, and its `output_tokens` is the
provider's own counter — the number to read, not a substitute cost.

Before quoting any figure, read its denominator in the rebuild's coverage line: how
many dispatches were seen, how many carried spend, how many issues landed. A lane
whose rows rest on three dispatches out of forty is a lane whose cost is a floor.
