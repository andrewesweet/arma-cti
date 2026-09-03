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
- Anything about a foreign lane. Every row here is `claude-native`; Codex and z.ai reach the shell through different sandboxes and would each have to be measured.

## Git history rewrite: a designed experiment (2026-09-03, #695)

#691's measurement failed twelve review rounds because it ran commands in the course of other work and wrote the table afterwards. This section is written in the opposite order and landed in that order: the design commit carries the arrangement, the hypothesis, the falsifier and the route list, and carries no result; the results commit follows it on the same branch and only fills the results rows. A reader can see from the branch's history that the design predated every result.

### Arrangement

- **The session.** A dispatched session, seat `implementer`, issue #695, worktree `.claude/worktrees/issue-695`, base `fd55969e`. Dispatched is observed, not assumed: the `deny-dispatched-background` hook refused this session's one `run_in_background` Bash call with `inside a dispatched session (env CTI_DISPATCH_ID is set)` — the hook's own bytes.
- **Lane, profile and permission mode are not derivable from inside, and are recorded as such rather than guessed.** `printenv CTI_DISPATCH_ID …` was refused; `ls /home/andre/.arma-cti/dispatches` was refused; `cat /proc/self/environ` was refused; a Read of the user-level `~/.claude/settings.json` — which `docs/multi-provider-dispatch.md` names as the source of at least one out-of-project grant (`Bash(git push *)`) — asked for a permission nobody can answer. Every refusal string is quoted under Results. The dispatching record names the three fields; the landing comment on #695 carries them. What the rows below are scoped to is therefore a **surface**, not a lane label: a session whose Bash decisions resolve through this repository's project allowlist plus whatever the harness auto-approves — the surface both `claude-native` and `zai` inherit, and which #691's rounds showed is neither necessary nor sufficient as a bound. `codex` reads no allowlist at all and is out of scope: this session cannot dispatch (`Bash(just dispatch)` has no grant) and cannot spawn a lane binary, so no Codex row could be provoked from here.
- **The scratch repository.** `.spike-out/695-scratch/` inside this worktree (gitignored), its own history, no remote, one base commit `B` plus four commits `C1`–`C4` above it. The permission decision is taken on the command string, not on which repository the command addresses, so the scratch exercises the same surface without putting a single scratch commit on this branch's ancestry — the specific mistake #691's first dispatch made and four rounds paid for. The scratch is deleted before the gate runs; it lands nowhere.

### Hypothesis and falsifier

**H.** On a session whose Bash decisions resolve through the surface above, every route that collapses four commits into one is closed: each candidate route either meets a harness approval refusal or cannot move a ref, so the only history rewrite available is `git commit --amend` of HEAD.

**Falsifier.** One sequence of commands this session is permitted to run that leaves the scratch branch one commit where it had four, with the same final tree. Either half alone is not enough — a permitted command that cannot move the ref has collapsed nothing, and a ref move that changed the tree is not the shape #668 needed.

**Not claimed.** Nothing about any command absent from the results table. `git push --dry-run` was permitted on this machine with no project grant, so an absent row is absence of measurement, never evidence of refusal.

### The routes, as they will be provoked

`B` is the scratch base commit, `C1`–`C4` the four above it, `<scratch-branch>` its default branch. The results commit carries every invocation literally — no `<B>`-shaped placeholder survives into it; the SHAs are filled with the values the run actually used.

| # | Route | Command shape |
|---|---|---|
| 1 | Soft reset onto the base — the canonical collapse's first half | `git reset --soft <B>` |
| 2 | Interactive rebase to squash | `git rebase -i <B>` |
| 2b | The same verb behind an environment assignment, to see whether a prefix the harness does not recognise changes the decision | `GIT_SEQUENCE_EDITOR=true git rebase -i <B>` |
| 3 | A non-interactive rebase that *does* select commits above its upstream (`<C1>..HEAD` replayed onto `<B>`) — measures the verb, not a collapse | `git rebase --onto <B> <C1>` |
| 4 | Plumbing collapse, first half: mint one commit with the tree of `HEAD` and parent `<B>` | `git commit-tree <tree-of-HEAD> -p <B> -m collapsed` |
| 4b | Plumbing collapse, second half: move the branch ref to what 4 minted | `git update-ref refs/heads/<scratch-branch> <minted>` |
| 4c | The other ref move a collapse would need | `git branch -f <scratch-branch> <minted>` |
| 5 | #691's round-five command reproduced where it can be watched: `--onto <C3> HEAD` selects nothing above its upstream, so if it runs it drops `HEAD` rather than collapsing anything | `git rebase --onto <C3> HEAD` |
| 6 | Control — git's own refusal through a project grant: `git commit` is granted, and on a clean index git itself refuses | `git commit -m nothing-to-commit` |
| 7 | Control — a verb outside the grant whose git execution would be distinctive if it happened: git says `No rebase in progress?` when the verb actually executes | `git rebase --continue` |
| 8 | The known counterexample, re-provoked on a repository with no remote: permitted verb, git-level failure, both facts visible | `git push --dry-run origin HEAD:main` |
| 9 | #691's refused read-only row, re-provoked | `git var GIT_COMMITTER_IDENT` |
| 10 | The known positive, re-provoked so this session's row stands in its own record rather than borrowed from #691's | `git commit --amend -m <message>` |

**Refusal classification.** A refusal is attributed to the harness only on the evidence that git never ran: the text is the harness's approval-demand string and no git framing (`fatal:`, `error:`, usage) appears. A refusal is attributed to git when the output is git's own and an exit status accompanies it. Routes 6 and 7 are the calibration pair — one failure from a granted verb, one from an ungranted verb — so the two shapes are shown side by side rather than argued.

### Results

Filled by the results commit that follows this one. Until then this subsection states only: no route had been provoked when the design above was committed.
