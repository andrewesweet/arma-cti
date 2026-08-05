# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human action first — implementation, or the opening step of otherwise-agent work (#52, #54) |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

`ready-for-human` is how the human finds their pending decisions, with two standing exceptions (2026-08-05 audit, which also found and fixed one mislabel, #189): the ADR review queue, tracked by the anchored grep `grep -rl "^Reviewed-by-human: pending" docs/adr/` rather than by any label; and flags raised inside issue closes, which retros consolidate onto the standing pile issue #217 — the current pile is always that issue's newest comment.

Edit the right-hand column to match whatever vocabulary you actually use.
