# A playtest brief's boot line is run before the brief is handed over

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on changes to CLAUDE.md and the project skills — the 2026-08-01 evening retro's amendment batch (five issues: #35, #37, #39, #40, #41; plus brief 0001 and its verification pass)
Reviewed-by-human: 2026-08-02

## The decision

An instruction to the human ships only after an agent has executed it. Concretely, on the
one surface where the pattern has bitten: the playtest-brief skill now requires the boot
line to be run before the brief is delivered, and the tier being busy defers **delivery**,
not verification. A brief is a reason to take the tier.

## The evidence

Brief 0001's boot line was authored blind — the tier was in use, and the author judged
"a brief is not a reason to take it", flagging the gap honestly. The verification pass
that followed found the brief telling the human to take a slot in a lobby that does not
exist (`skipLobby` is set; the client arrives seated), prescribing `just build-shim-windows`
for a session whose client never loads the shim, and — only reachable by running the line —
a harness bug filing a Commander who had joined and taken the seat as
`connected-but-never-arrived`, a false note of the kind that gets believed later (`492dbb7`).

This is the third instance of the shape "documentation describing something nobody has
done" (Phase 0's command table, ADR-0016's probe headers), and the first where the reader
is the human. The convention-lands-with-its-instance rule covers agent-facing conventions;
it does not reach a brief, whose whole content is instructions to a person. Honest
flagging did not prevent the defects — only execution found them.

## Deliberately not decided

A general CLAUDE.md rule "verify every instruction to the human" — one surface has
evidence, and the retro skill's bias is against enumerating ahead of it. If the pattern
recurs on a second human-facing surface (e.g. the playtest-ingest response form, or a
future runbook addressed to the human), generalise then.

## The rest of the batch this ADR records

Applied at the same retro, under the same standing authorisation:

- **CLAUDE.md, command surface**: the `just`-only rule binds work that lands and its
  verification; exploration scaffolding kept off main may run bare, and landing it means
  landing its recipe and table row in the same commit. Evidence: #40 ran `spike/sp-run.sh`
  directly, deliberately and flagged, because a recipe for throwaway scaffolding would
  have cost a sign-off-gated command-table row; #27's contrasting case (bare invocation of
  a *landed* tier) stays a defect.
- **playtest-brief skill**: the boot-line rule above; non-asserting fixtures live in
  `spike/playtest/`, never `spike/probes/` (with the load-bearing corpus-membership rule
  landed in `docs/regression-tier.md`, previously recorded only in a commit message); the
  fresh-campaign rule gains its honest exception until staged-state fixtures exist (#42);
  an empty perceptual checklist asks for candidate items instead of inventing entries.
  Marker: `unproven` → `validated ×1`, amended on first use.
- **Marker bumps in CLAUDE.md**: failure classes ×4 → ×5 (#41: a check that could not run
  classifies `infra_unavailable`, never passes); probe-window rule ×3 → ×4 (#35: the fix
  restored conditions, not time); ADR-claiming ×2 → ×3 (#35's clean renumber, #37's held
  claim); elimination-context line gains `validated ×1` (#35 inheriting #33's empty-Base
  measurement).
- **retro skill**: `validated ×5` → `×6` (sixth use, unattended, no amendment to the
  skill itself needed).

## Overturned by

- A brief whose boot line was verified as required and whose session still failed on an
  instruction execution could not have caught — then verification is necessary but the
  rule is mis-aimed at the boot line.
- The tier-contention cost proving real: if verifying a brief ever displaces gating work
  measurably, the deferral trade-off gets re-decided rather than quietly inverted.
