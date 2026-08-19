# The commit vocabulary is convention, and the hook enforces cocogitto's type set, not the vocabulary

Delegated-decision: yes
Date: 2026-08-19
Stood-in-for: human sign-off on the `AGENTS.md` sentence under "Commits, changelog, versioning
(ADR-0010)" — `CLAUDE.md` is the committed symlink to it, and that file is a sign-off gate in
CLAUDE.md's list — taken on #340
Reviewed-by-human: pending
Supersedes: none — ADR-0010 stands as written: it commits to Conventional Commits 1.0.0 and names
cocogitto as the enforcement, and it never enumerated a type set. The list corrected here was
`AGENTS.md`'s own editorial parenthesis, which no ADR ever carried, so there is no ruling here to
supersede
Claimed: 0076 — `docs/adr/` on `origin/main` tops at 0074 (`6e85b10`), and #392's unlanded branch
holds 0075 (stated in its handoff; found by searching open issues for the bare number `0075`,
after `ADR-007 in:comments` returned nothing and taught that this search matches whole numbers
only). Searches for `0076`, `0077` and `0078` returned empty, and the search was calibrated
against known answers rather than trusted empty: `0074` finds #412 and #345, `ADR-0071
in:comments` finds twelve issues. Two blind windows remain, per CLAUDE.md's protocol: a claim
whose issue closes before this lands, and a concurrent claim nobody has posted yet — the rebase
backstop catches both

## What happened

#340's finding: a commit typed `style(seats): …` passed the `commit-msg` hook on #324's branch,
though `AGENTS.md` said the hook "rejects everything else" outside a nine-type list. The issue
named two possible moves — the list is stale, or the enforcement should be built — and said the
choice was not mechanical.

Three facts, all checkable from the tree and the history:

1. `cog.toml` configures no commit types. It carries `tag_prefix` and the `commit-msg` script
   chain, nothing else, so the set `cog verify` enforces is cocogitto's built-in default, and it
   always has been. No configuration this project ever wrote expressed the nine-type list.
2. `revert` is missing from the list and in real use: three withdrawals on `origin/main` carry it
   (`27e18b4`, `03a3721`, `b73b810`). Any future `revert:` commit would have contradicted the
   sentence exactly as `style` did — the list was wrong twice over, not once.
3. Across 613 commits on `origin/main`, every type in use is one of the nine plus `revert`, and
   `style` appears exactly once — the commit #340 names. `ci` appears never: it is vocabulary
   that has simply not been needed.

## Decision

**The document moves; the enforcement stays what it is.** `AGENTS.md` now keeps the vocabulary as
convention, adds `revert` to it (a withdrawal carries it here, three times already), and states
what the hook actually enforces: Conventional Commits form against cocogitto's built-in type set,
which admits the vocabulary and `style` alike. No claim of enforcement now reaches further than
a mechanism — which is the whole of #340's general point: a documented rule with a *claimed*
mechanical enforcement that does not enforce it is worse than an unenforced rule, because readers
stop checking.

Declined: mechanically rejecting `style`, the issue's other branch. Grounds:

- It polices one commit in 613. The vocabulary has steered every other commit this project has
  made, without a gate.
- The cheap form of it does not visibly exist: whether cocogitto's `[commit_types]` can *narrow*
  the built-in set was not verifiable from this worktree (no network; cocogitto's documentation
  is not vendored), and this decision does not rest on that answer. The form that certainly
  exists is a tracked commit-msg guard on the `deny-closing-trailer.py` pattern (ADR-0042) — a
  new file, its tests, and the mutation floor over them, bought to catch a type used once, by
  accident, and already caught by review as #324's Low finding.

Provenance of the enforced-set claim, stated rather than smoothed: `style` and `revert`
acceptance are observed (`a1c73b7`; the three reverts), every history type is observed, and the
set's further membership is cocogitto's documented default, not something re-verified against
the binary here. `AGENTS.md`'s new sentence claims no more than that.

## Why this was taken under the standing authorisation rather than referred

`AGENTS.md` is a sign-off gate, and #94's allowlist entry for editing it is the standing
authorisation's mechanical face, so the recording duty is ADR-0013's. The choice between the two
moves, which #340 called not mechanical, resolves on evidence rather than taste: `revert`'s
three uses make the nine-type list wrong under either reading of `style`'s acceptability, so the
document moves under both. What stays genuinely open — whether the human wants the vocabulary to
bind mechanically anyway — is preserved below as an overturning condition, not settled by
omission.

## What would overturn this

Stated so a reviewer can disagree by pointing at evidence rather than at taste (ADR-0019).

1. **The human prefers the vocabulary to bind.** The remedy is then a tracked commit-msg guard
   on the `deny-closing-trailer.py` pattern (ADR-0042), and whether `revert` and `style` sit
   inside the gated set is the human's call rather than this ADR's. This ADR is a stand-in for
   that sign-off, not a substitute for it.
2. **Evidence that cocogitto's configuration can narrow the built-in type set at trivial cost.**
   That would make "enforce the nine" a one-file change rather than a guard plus tests, and the
   declined branch re-opens on its own cost grounds.
3. **`style` recurring.** One landing reviewed as a finding is an accident; a second is a
   pattern, and evidence the vocabulary sentence is not steering anyone — at which point the
   sentence has had its chance and the gate earns its cost.

## Scope

One sentence in `AGENTS.md`, this record, and the changelog entry. `cog.toml` is untouched, no
guard is added, and closing #340 stays with the lander per ruling 4's division (#345).
