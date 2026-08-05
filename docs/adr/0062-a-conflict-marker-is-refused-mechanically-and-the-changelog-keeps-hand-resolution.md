# A conflict marker is refused mechanically, and the changelog keeps hand resolution

Delegated-decision: yes
Date: 2026-08-05
Stood-in-for: human sign-off on a new ADR, and on #195's secondary-list `merge=union`
mitigation for `CHANGELOG.md` — priced there but never adopted, and #231 asks for it to be
taken or declined with the reason stated
Reviewed-by-human: pending
Claimed: comment on #231, 2026-08-05, after `git fetch origin` (`docs/adr/` on `origin/main`
topping at 0061) and a scan of every open issue's comments, whose highest claim was 0061

## What happened

From #227's close comment. A stray common-ancestor marker — `||||||| parent of 7bea7f6`,
written mid-line here so this file passes its own gate — reached the changelog inside
2b4f99b, the resolution of #230's own rebase. The next landing, 5a966f3, resolved *its*
rebase against the already-corrupt file and cut everything from that line onwards: 1,669
lines, every release before this cycle. #227 restored the file in a885306 with no entry
lost, and reported the mechanism rather than absorbing it.

The mechanism is the part worth naming. A marker is not untidiness that a later reader
tidies away — git's merge machinery reads the region as structure, so a marker in the base
is a **loaded trap for the next agent's resolution**, and the agent who springs it is not
the agent who set it. Nothing in the tier could see it: a marker is ordinary text to
`ruff`, to HEMTT, to `cog` and to `gitleaks`, and it is ordinary text to the human reading
a diff of a file 3,500 lines long.

## Decision 1: the four marker forms are refused mechanically, in tracked files

`tools/check_conflict_markers.py`, wired into `just check` as `check-conflicts` and into
`tools/land.py`'s ladder as a `conflict_markers` refusal.

**The forms.** The opener (`<`), the diff3 common-ancestor line (`|`) and the closer (`>`)
are findings wherever they begin a line. The separator (`=`) is a finding **only between an
unclosed opener and its closer**.

That asymmetry is the decision, and it is not fastidiousness. Alone on a line a run of `=`
is a setext heading rule, and six vendored wiki pages under `docs/reference/arma-wiki/`
carry one today — `Mission_Readme_Template.wiki` twenty times. An unconditional rule would
red `just check` on the tree the gate exists to protect, which is the failure mode #186 and
#207 already taught the project once. The cost is stated rather than hidden: **a lone
separator, every marker around it deleted by hand, is not caught here.** It is also the one
form that cannot poison a later merge by itself, because it is the region delimiters that
git re-reads.

Runs are matched at **seven or more**, so a path raising `conflict-marker-size` is covered
without a second rule. Matching is anchored to the start of a line, which is why this ADR
and the checker can both name the forms in prose.

**Where it runs.** Two places, and the difference between them is honest rather than
additive. `just check` is the coverage: it reds before a marker can be committed, and
`just land`'s gate runs `just fast`, so every landing already passes through it. The ladder
rung adds two things a `gate_red` cannot: the refusal arrives **by name, with the file and
line**, and it arrives **before the gate's minute** rather than buried in its output.

**It is judged on the rebased tree**, which means a marker inherited from `origin/main`
refuses this landing too. Deliberately: #231's mechanism is that the base poisons the next
resolution, and the next resolution is exactly what the rung stands in front of. It does
not deadlock — the landing that removes the marker passes.

**Scope is tracked files.** What lands is what is tracked, and #105 says a tool must not
judge an agent's untracked files at all.

**The checker never spells a marker.** Every one is derived from its character and `SIZE`,
in the tool and in its tests, and the fixtures are written into temporary trees rather than
committed. `test_the_live_repository_carries_no_conflict_markers` is the assertion that
keeps it so.

## Decision 2: `merge=union` for `CHANGELOG.md` is declined, and the reason is measured

**Declined.** #195's secondary list priced it as removing most of the hand resolution that
produces markers, which is true and is not enough.

Measured before deciding, on a scratch repository reproducing a concurrent landing — two
agents each adding one entry under `### Added` and one under `### Fixed`, the second
rebasing onto the first:

```
### Added

- Base entry, from before the cycle.
- A: the breaker.

### Fixed

- A: a fix.
- B: the ledger.        <- B's Added entry, silently filed under Fixed

### Fixed

- B: another fix.
```

The rebase exits 0. No conflict, no marker, no signal of any kind. Union merge concatenates
the conflicting hunks in order, so **entry ordering is fine** — it comes out chronological
by landing — but the *section* an entry lands in does not survive, and the category heading
is duplicated. The control, the same rebase without the attribute, conflicts loudly and
produces exactly #231's marker shape.

So the trade on offer is: a loud failure that is now caught mechanically, exchanged for a
silent failure that nothing catches at all. Silence is the property that let this defect run
twice; buying more of it to avoid a class of error the same commit makes impossible is the
wrong direction. CLAUDE.md requires the changelog to be curated for humans, and a driver
that misfiles entries under headings it duplicates is not curation.

The judgement that makes this cheap: with Decision 1 landed, **hand resolution is safe
again**, because a bad resolution now reds. `tools/land.py`'s `rebase_conflict` refusal
already tells the resolver what to do — "CHANGELOG.md is the only conflict 264 landings have
produced; take both entries, keep both" — and that instruction is correct, one-line, and now
enforced.

No `.gitattributes` is created by this decision. The repository has none, and this is not a
reason to start one.

## Decision 3: no command-table row is owed

`check-conflicts` is a `check-*` sub-recipe. ADR-0060 Decision 2 settled the rule while
sweeping for row-less recipes: "the `check-*`/`unit-*`/`build-*` sub-recipes have never
carried rows, being components of rows that exist". `just check` already has its row and
this changes nothing about when to run it. Nothing is routed to #228.

## Not taken, and why

**A `pre-commit` hook rather than a gate step.** The tier's hooks are Claude Code hooks
governing agent edits, not git hooks; a marker can reach a tracked file by rebase resolution
as well as by an edit, and only a tree-scanning gate sees both.

**Scanning the diff rather than the tree.** A diff-scoped check passes a landing whose
markers came in on the base, which is the half of #231 that did the damage.

**Refusing the separator unconditionally, with an allowlist for the wiki.** An allowlist is
a list that goes stale against 6,690 vendored pages nobody in this project authored.

**Reading every tracked file.** `git grep` shortlists and Python decides, so a clean tree
costs one `git grep` — measured at 0.17 s including `uv` start-up — and reads no files at
all. Reading 6,690 wiki pages on every `just check` would be a gate people route around.

## What would overturn this

**Decision 1** is overturned by a false positive on a legitimate tracked file — a marker
form the gate flags that git did not write — or by a marker reaching `main` despite the
gate, which would mean the scope (tracked files, rebased tree) is wrong rather than the
patterns. The stated blind spot is the lone separator; a real instance of one causing damage
would be evidence for widening the rule and accepting an allowlist after all.

**Decision 2** is overturned by evidence that changelog conflicts are frequent enough for
their hand resolution to be a real cost now that it is gated — a run of `rebase_conflict`
refusals on `CHANGELOG.md` in one cycle would say so — or by a merge driver that preserves
Keep a Changelog's section structure. `merge=union` is not that driver, and the measurement
above is what would have to be shown wrong.

**Decision 3** is overturned if the human wants `check-*` sub-recipes in the command table,
which would reopen ADR-0060 Decision 2 rather than this one.
