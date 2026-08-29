"""A deterministic reference adapter: pipeline smoke, never a model.

This adapter exists so the runner can be exercised end to end without a lane, a
credential or a budget — the same role the synthetic adapters in
tests/unit/test_eval_corpus.py play. Its answer is fixed, so a run against it proves
the pipeline (isolation, grading, budgets, reporting) and proves nothing about any
configuration's quality, which is exactly what an eval of a model would be for.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ANSWER: str = (
    "I would dispatch the work as a detached session and end my turn, having armed "
    "a watcher and written a handoff, so nothing waits on me."
)

record = {
    "answer": ANSWER,
    "stopped_by": "completed",
    "tokens_in": 0,
    "tokens_out": 0,
    "commands": 0,
    "harness": "synthetic-echo/1",
    "env_seen": sorted(os.environ),
}

with open("trial.json", "w", encoding="utf-8") as handle:
    json.dump(record, handle)

# The prompt is read to show the adapter sees only what the workspace holds.
prompt = Path("task.txt").read_text(encoding="utf-8")
assert "subagent" in prompt
