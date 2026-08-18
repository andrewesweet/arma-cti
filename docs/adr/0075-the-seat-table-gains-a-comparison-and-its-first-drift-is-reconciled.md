# The seat table gains a comparison, and its first drift is reconciled

Delegated-decision: yes
Date: 2026-08-18
Stood-in-for: human sign-off on ADR-0071 amendment A5 (an edit to a landed ADR), and on
the `just check` row's wording in `AGENTS.md` (`CLAUDE.md` is the committed symlink to
it) — both human sign-off gates in CLAUDE.md's list, taken on #392
Reviewed-by-human: pending
Supersedes: none — the decisions it records are ADR-0071 amendment A5, marked inline in
that file at the passages it changes and indexed in its `Amended:` header, and one
sentence of command-table wording; this ADR records the delegations and nothing else
Claimed: 0075 — after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0074,
`557d8d2`) and a scan of all 88 open issues' bodies and comments for an ADR number at
or above 0075, which returned nothing. The scan was checked against a known answer
rather than trusted empty: the same query pattern for 0073 and below returns
ADR-0071/0073/0074 on closed issue 397's thread, and the two bare-number hits the
wide patterns did return (issues 216 and 217) were read in context and are the
decimals `0.0095` and `0.0096` in cache-arithmetic prose, not ADR references. The
rebase backstop on landing catches any claim this scan could not see

## What happened

ADR-0071 ruling 2's seat table and `tools/dispatch.py`'s `SEATS` state the same
preference and escalation data on two surfaces, and nothing compared them (#392,
filed from #361 review round 3). The gap bit twice in opposite directions: A1
landed at `eaabf9f` with the ADR's two filled escalation cells ahead of the
registry, and `e19410e` (2026-08-17) renamed `zai-glm52-max` to `zai-glm53-max`
in the registry while the ADR's table and its "the head is" sentence kept naming
the retired profile.

This landing builds the comparison: `tools/check_adr_seat_table.py`, run by
`just check-adr` beside `tools/check_adr_form.py`, parses ruling 2's table and
compares its preference and escalation columns and `orchestrator`'s Claude-only
cell against `SEATS` and `DECLARED_ONLY_SEATS`, exactly, profile-name for
profile-name. Its first run on this tree found the `e19410e` drift and nothing
else, which is the replay its tests pin.

Because the comparison is exact, landing it green required the ADR's two
`zai-glm52-max` cells to move, and ADR text is a human sign-off gate. The
landing also widens routing class 6's path list in
`config/dispatch-routing-policy.json` to name the new checker — the issue's own
words classify any new checker as class 6, and a gate path the list does not
name is uncovered rather than cleared — and extends the `just check` recipe and
its table row, the row living in `AGENTS.md`, which is the gated file.

## The decisions taken on the human's behalf

1. **ADR-0071 amendment A5** reclassifies the table's `implementer` preference
   cell and the "the head is" sentence as tracked data rather than dated
   narration, and moves both to `zai-glm53-max`. `e19410e` had deliberately
   left them naming `zai-glm52-max` on the ground that dated records are true
   of the time they describe; A5 judges that ground inapplicable to these two
   cells, because they state live routing, the registry is the authority for
   it, and from A5 a check refuses the divergence. No routing decision moves:
   the slot was and remains the zai lane's max-effort profile, under whatever
   name the registry gives it.
2. **The `AGENTS.md` command-table wording** for `just check` gains "ADR
   seat-table check" beside "ADR-form check", reflecting the second checker the
   recipe now runs. The recipe line itself is the justfile's, which carries no
   sign-off gate; the row's home does, which is why it is named here.

The class-6 list widening and the checker itself carry no sign-off gate —
their gate is routing class 6's cross-lane review on this very landing, which
is not a gate this ADR can discharge and is not claimed as one.

## What would overturn each decision

A5 is overturned by the human ruling that ADR-0071's table is a frozen record
of the ruling as ratified, not a live surface — the position `e19410e` took
for the whole file. The consistent form of that ruling is not restoring
`zai-glm52-max`; it is the remedy #392's own body names and #390's arbitration
recommended for its sibling: cut the table's data cells down to pointers at
`SEATS` so nothing checkable is left to drift, and delete or shrink this check
with them. That reopens the table's text under sign-off either way.

Decision 2 is overturned by any ruling on how the command table should name
fold-in checkers — a named recipe and row instead of the folded `check-adr`
step — which is a wording preference, cheap to apply, and the only thing it
changes is where the checker is invoked from.

## Bearing on the adjacent issue

#390 (derive the arbiter rule's copy set) shares the defect shape — a second
copy nothing compares — over a different pair of surfaces. #392's body asked
whoever took one to read the other first; this landing did, and the reading is
recorded above rather than silently absorbed: the cheaper answer for #390's
prose copies may be the pointer cut, and for this table the exact comparison
was built instead, because a ratified human decision record's data cells are
not restatement the way a docstring is. Whether that distinction holds is a
retro's question, not this ADR's.
