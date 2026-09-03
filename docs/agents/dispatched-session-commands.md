# A dispatched session's command surface

**Outcome: the refused-command list a dispatched session ran into was not one list, it was three causes, and the largest one was ours.** Four of the seven commands #294 recorded as refused — `grep`, `rg`, `find`, `wc` — were refused only because RTK rewrote them before the permission decision was taken. Escaping the rewrite (`\grep`) made them work. The other three were refused on their own merits and no escape helped.

**That largest cause is gone.** RTK was removed from this host on 2026-08-16: not on `PATH`, `~/.claude/RTK.md` deleted, `~/.claude/settings.json`'s `PreToolUse` hooks array empty, so nothing rewrites a command before the permission decision any more. The four rows below are re-measured accordingly (#396) and the rest of this document is a dated record of 2026-08-10, kept because the other two causes are unaffected and because the shape of the rewrite failure is worth recognising if a rewriting hook is ever wired again.

Measured on 2026-08-10 from inside a dispatched session (#294): `claude --print --model opus --effort high --permission-mode acceptEdits`, lane `claude-native`, seat `implementer`. Every row was provoked in that session, not predicted.

For where a dispatched session may *write*, see `docs/multi-provider-dispatch.md`, "Reserved on every lane: everything under `.claude/`".

## The measurement

| Command | Bare | Escaped (`\cmd`) |
|---|---|---|
| `grep`, `rg`, `find`, `wc` | 2026-08-10: refused — `This command requires approval`. **2026-08-16, RTK removed: runs** | **runs** |
| `awk` | refused | refused |
| `python3 -c` | **not unconditional** — 2026-08-10 (`acceptEdits`): refused. 2026-08-16 (`acceptEdits`): refused. 2026-08-16 (`plan`): **runs**. See cause 2 | refused (2026-08-10) |
| `uv run python -c` | refused | — |
| `ls`, `cat`, `sed -n`, `jq`, `tr`, `echo`, `printf` | runs | — |

## The three causes

**1. RTK's rewrite, for `grep`, `rg`, `find`, `wc` — the cause that no longer exists.** On 2026-08-10 `~/.claude/settings.json` wired `rtk hook claude` as a `PreToolUse` hook on Bash, and the permission decision was taken on the **rewritten** command. That session's first compound command came back with

```
The following parts require approval: rtk git status --short --branch, rtk git log --oneline -1
```

naming a form nobody typed. `rtk grep …` was not something the harness recognised as a read, so it went to a prompt — and a dispatched session is `--print`, with nobody to answer one. A backslash defeated the rewrite, which is why `\grep` sat on #294's *allowed* list beside `grep` on its *refused* list: they are the same command, and the escape was the whole difference.

**Re-measured 2026-08-16 (#396), RTK removed from the host.** Bare `grep -c … AGENTS.md`, `rg -c … AGENTS.md`, `find . -maxdepth 1 -name AGENTS.md` and `wc -l AGENTS.md` were each attempted individually in a dispatched session and each ran, with no approval prompt. The whole of cause 1 is discharged, and no escape is needed for these four. Caveat on the measurement's reach: it was taken in one session under this repository's own allowlist, so a seat still meeting a refusal on one of these four is meeting something other than the rewrite and should record what.

That session's arrangement, stated because the arrangement moves the answer: `claude --print --model opus --effort low --permission-mode acceptEdits`, seat `implementer`, lane `claude-native`, profile `opus-low`, worktree `.claude/worktrees/issue-396`, run 16:42:35→16:51:47Z with the commit carrying the measurement falling inside that window. **The route to those fields is a dispatch's own record** — `~/.arma-cti/dispatches/$CTI_DISPATCH_ID/dispatch.json`, written at dispatch time and carrying `argv`, seat, lane, profile, worktree and base SHA — and a seat that cannot read it there still has `printenv`, which exports `CTI_DISPATCH_SEAT`, `CTI_DISPATCH_LANE`, `CTI_DISPATCH_PROFILE`, `CTI_DISPATCH_ID` and `CLAUDE_EFFORT`. Determine an arrangement from that record before reporting any part of it as unknown.

In that session `ps -eo pid,ppid,args` and `printenv` were each refused with `This command requires approval`, and `ps -o args= -p $PPID` was denied on `Contains simple_expansion` — which is **Claude Code's own Bash permission parser** declining prefix-match auto-approval for a command carrying shell expansion, not a hook of this repository's. Nothing in `.claude/hooks/` contains that string; do not go looking for it there.

**Working-directory confinement, 2026-08-16 (#396) in that `acceptEdits` session: `cat /home/andre/.arma-cti/…` and `ls` on the same path were both blocked** outside the worktree. That is one of three measurements which disagree, so it is dated rather than stated flatly: the 2026-08-10 session's `cat` on an outside path ran, and the reviewer's 2026-08-16 `--permission-mode plan` session had both `cat` and `ls` run there. The "Two confinements" bullet below describes the 2026-08-10 result and is dated to it. An outside-worktree read is therefore not settled — attempt it, and if it is blocked take the block as this session's answer rather than as a contradiction to resolve.

**`python3 -c`, re-measured 2026-08-16 (#396) in that same session: refused** — `This command requires approval`, on `python3 -c 'print(1)'` alone. `awk` and `uv run python -c` were not re-measured here. This is cause 2's row and belongs to it, but it is **not** unconditional: see the three-point record under cause 2.

The generalisable half, kept because the mechanism can return: any hook that rewrites a Bash command before the permission decision changes *what the harness is asked to approve*, so an absence or a refusal seen through it is a fact about the filter and not about the command.

**2. Arbitrary execution, for `awk`, `python3 -c`, `uv run python -c`.** Refused escaped as well as bare. Each can write files and run arbitrary code, so the harness does not auto-approve it under `acceptEdits`. No escape helps and none should.

**`python3 -c` is not refused unconditionally**, and three measurements now exist:

| date | effort | permission mode | `python3 -c` |
|---|---|---|---|
| 2026-08-10 | `high` | `acceptEdits` | refused |
| 2026-08-16, fixing round | `low` | `acceptEdits` | refused |
| 2026-08-16, review | `xhigh` | `plan` | **ran** |

**Permission mode is the candidate variable.** It tracks the answer exactly across all three, effort does not (`high` refused, `low` refused, `xhigh` ran — non-monotonic), and this cause's own sentence supplies the mechanism: *"the harness does not auto-approve it under `acceptEdits`"*. Say candidate and mean it — three points, and effort co-varied across every one of them, so the confound is not separated and nothing here establishes permission mode as the cause. A seat that needs the answer for its own mode measures it in that mode.

**3. Compound decomposition.** A `&&`, `;` or `|` chain is split and every part must be permitted on its own, with no read-only auto-approval for the chain as a whole:

```
printf … | tee f      → The following part requires approval: tee …
echo '…' | rtk hook claude  → The following part requires approval: rtk hook claude
```

(The second line is the 2026-08-10 transcript verbatim; `rtk` is no longer installed, so that exact command would now fail on its own account. The decomposition it demonstrates is unchanged.)

A command that runs perfectly well alone can be refused inside a chain — which is how a session loses a turn to a one-line pipeline it had no reason to doubt.

## Git history rewrite, observed 2026-09-03 (#691)

One verb: **`git commit --amend` succeeded for a dispatched implementer on the `zai` lane — at least three observed successes.** The three named final-candidate amends shared parent `50570ff6`; other observed amends did not — dispatch `d-20260903-141513-4e4825` observed `d7da5ce3` amended to `5e7cadae` on parent `841011b3`, and the initial experiment observed others still. The branch carried scratch commits above its candidate at least once mid-cycle, so single-commit continuity was never a property of it; the surviving candidate is one commit. `57be37c1`, the orchestrator's own collapse, was not the first review's subject — dispatch `d-20260903-124533-08131f` had already reviewed its predecessor `77981976` before the collapse existed. The amending runs observed so far are named by their dispatch records — `d-20260903-135450-be1c90`, `d-20260903-141513-4e4825`, `d-20260903-144702-2c5e2a`, profile `zai-glm53flash-max`, seat `implementer` — observed successes, not an exhaustive list, persisting under `~/.arma-cti/dispatches/` after the branch is gone. Each carries the run's permission mode, this document's named candidate variable under cause 2: all three say `acceptEdits`. A dispatched session on this lane could not read them on 2026-09-03 (`cat`, `sed` and `jq` each blocked outside the worktree), so the mode is stated here rather than left for such a reader to recover. The claim is lane-scoped and dated, and extends no further.

**What the brief must say, demonstrated rather than inferred (#691, criterion 2).** **"Amend HEAD; do not add a commit."** is the sentence as dispatched: dispatch `d-20260903-135450-be1c90` carried it and observed `57be37c1` amended to `841011b3` — one named demonstration with a before-and-after SHA. Later rounds of #691 carried variants of the instruction rather than this sentence (`d-20260903-141513-4e4825`, `152844`, `154559`, `160600`, `161801`; see their brief records), and no single-commit branch is attributed to the wording — `141513`'s single-commit result also required `git rebase --onto` to remove scratch ancestry. It is an observation about what worked, recorded with the exact wording that worked, not a rule about what will: rounds three, four and nine of this issue each removed a derived claim about what a dispatched session would do, and none of them survives here. Its measured bounds are the run's, not the sentence's: lane `zai`, permission mode `acceptEdits`, **HEAD only** — no round demonstrated rewriting anything deeper than HEAD — and **before review rather than after**, because a review verdict binds to the SHA it names and an amended branch rides no earlier approval, so an amend after review buys a fresh verdict.

The wider mapping of what git commands a dispatched session can run is unmeasured, and #695 holds it.

## Two confinements worth knowing before you meet them

- **`grep` is confined to the session's working directory**, and says so: `grep in '…' was blocked. For security, Claude Code may only search for patterns in files from the allowed working directories for this session: '…'`. **On 2026-08-10** `cat` on the very same outside path ran, so a dispatched session could *read* a dispatch record under `~/.arma-cti/` and not *search* one; pipe it (`cat f | grep …`) when that holds. It does not always hold — the 2026-08-16 `acceptEdits` session had `cat` and `ls` blocked on that path too, and the `plan` session had both run (see the dated paragraph under cause 1). This confinement is the harness's own and has nothing to do with the removed rewrite.
- **The project allowlist is in force and does the deciding for `just`.** `just land --dry-run` runs on its `Bash(just land --dry-run)` grant; `just probe-contract`, which has no grant, is refused. Nothing distinguishes them but the allowlist.

## What to do about it

**Update, 2026-08-20 (#436):** `just mutation-compare` no longer exemplifies the narrow-recipe pattern. Landing it as an alias of `mutation` activated its dormant grant over the mutation tool's complete argument surface. That wider surface is deliberate because comparable surveys need arguments such as `--budget`; `just fast` still invokes `mutation` without arguments, so the alias cannot soften the landing gate. The narrow `just discard` grant remains the approved pattern.

What this buys is a brief that costs nothing to compose and a dispatch that does not spend itself rediscovering the list:

- `grep`, `rg`, `find` and `wc` run bare since 2026-08-16; the `\grep` escape is harmless but buys nothing now;
- keep reads out of `&&` chains;
- reach for a `just` recipe rather than `python3 -c` — and note that whatever a recipe's subprocess does is invisible to the permission check, which is why its argument surface must match the capability being granted. `just land --dry-run` created a `.venv` in passing; the harness saw a `just` command and nothing else.

## What this does not establish

- Anything about `awk`, `python3 -c` or `uv run python -c` under the removed rewrite: they were refused on their own merits on 2026-08-10 and were **not** re-measured on 2026-08-16, because nothing about their cause changed. A seat that needs one still reaches for a `just` recipe.
- The command-surface rows above (the measurement table and the three causes) are `claude-native`; the git-verb claim is `zai` — one section per lane, neither generalising over the other. A lane that reaches the shell through a different sandbox has to be measured for each section it matters in, and `codex` is unmeasured for both.
