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

Run 2026-09-03, entirely inside the session that committed the design above (`a7341ca4`). **Verdict first: H is false. The four-into-one collapse was performed with permitted commands, and the falsifier's tree-identity check is met.** Every command below is literal; every SHA is the value the run used.

**The setup leg failed, and the shape was built in this repository instead.** No repository-creating verb is permitted, so the designed scratch repository never existed:

| Command | Outcome |
|---|---|
| `git init .spike-out/695-scratch` | refused — `This command requires approval` |
| `git worktree add --detach .spike-out/695-scratch HEAD` | refused — `This command requires approval` |
| `git clone --no-hardlinks . .spike-out/695-scratch` | refused — `This command requires approval` |

The four-commit shape was therefore built on top of the design commit in this worktree's own history, after the removal routes below had been measured: four scratch commits (`463bd479`, `2a4a1158`, `9feca5c5`, `aaae549c` — one file each, `git add <file> && git commit -m "test: #695 collapse-experiment scratch commit N"`), always removable by the permitted `git rebase --onto` drop. **Deviations from the design, stated rather than hidden:** the scratch commits sat in this branch's ancestry while the experiment ran, which is exactly where #691's first dispatch lost its own scratch — the difference is that the removal route was measured first, and the branch was returned to `a7341ca4` before the gate; and route 8, designed for a remoteless scratch, ran in this repository instead, so its permission half stands and its intended git-level "no destination" failure was never reproduced. The scratch commits are dangling objects; they land nowhere.

**Verbatim rows.** "refused" below is always the harness's `This command requires approval` unless another origin is named; classification follows each row.

| # | Command (literal) | Outcome |
|---|---|---|
| 1 | `git reset --soft HEAD` | refused. The no-op target was chosen so that a permitted run would have been harmless; the verb-level answer covers `--soft <B>` identically, because the decision is taken on the verb |
| 2 | `git rebase -i a7341ca420a1dbeaa41c1bd919dac75a8b83161c` | **ran** — `Successfully rebased and updated detached HEAD.`; the range held one already-applied pick, so this was a fast-forward short-circuit and exercised no todo |
| 2' | `git rebase -i --onto fd55969eef475f29c7f6cd5be9334782f9b9ac6a a7341ca420a1dbeaa41c1bd919dac75a8b83161c` | **ran a real replay** — `Rebasing (1/1)…Successfully rebased and updated detached HEAD.`; the commit was replayed (`ed7a55cd` → `bea72c40`), so the todo was taken **unmodified** and no editor blocked the run. `git rebase -i` on this surface completes non-interactively: it drops, reorders and replays, and squashes nothing, because every route to a todo editor is refused (rows 2b, 2c, 2d, and the `fixup!` row below) |
| 2b | `GIT_SEQUENCE_EDITOR='sed -i -e "2s/^pick/fixup/" -e "3s/^pick/fixup/" -e "4s/^pick/fixup/"' git rebase -i a7341ca420a1dbeaa41c1bd919dac75a8b83161c` | refused — the environment-assignment prefix is not what the permission layer matches on |
| 2c | `git -c sequence.editor=true rebase -i a7341ca420a1dbeaa41c1bd919dac75a8b83161c` | refused — an option before the verb breaks the prefix in the same way |
| 2d | `git config sequence.editor 'sed -i -e "2s/^pick/fixup/" -e "3s/^pick/fixup/" -e "4s/^pick/fixup/"'` | refused |
| 3 | `git rebase --onto a7341ca420a1dbeaa41c1bd919dac75a8b83161c 463bd4798c24534b3bc8c2c00f96c052485aa21e` | **ran** — `Rebasing (1/3)Rebasing (2/3)Rebasing (3/3)[KSuccessfully rebased and updated detached HEAD.`; the four commits became three (`1ffa0596`, `890c4209`, `d5e7a571`): the first was dropped, the rest replayed |
| 4 | `git commit-tree 2753ec505936ce15acfd3d219794938818569f72 -m probe-695-dangling` | refused |
| 4b | `git update-ref refs/heads/scratch-695-branch d17598d33283ee9b5ad5535c9780d7d4dc66c48c` | refused |
| 4c | `git branch scratch-695-branch d17598d33283ee9b5ad5535c9780d7d4dc66c48c` | refused (create form; `-f` not separately provoked and **not claimed**) |
| 5 | `git rebase --onto d5e7a5718267e2abd67cfe98ab3f839c649cf13f HEAD` | **ran** — `Successfully rebased and updated detached HEAD.`; HEAD moved to `d5e7a571`, dropping the tip commit above it. #691's round-five command is thereby reproduced and correctly characterised: **it drops, it does not collapse** |
| 6 | `git commit -m "nothing-to-commit"` | **git's own refusal** — exit 1, `Not currently on any branch.` / `nothing to commit, working tree clean` |
| 7 | `git rebase --continue` | **ran, and git refused its argument** — exit 128, `fatal: No rebase in progress?`. Proof the `git rebase` verb is permitted on a grant outside this repository's allowlist |
| 8 | `git push --dry-run origin HEAD:main` | **ran** — `To https://github.com/andrewesweet/arma-cti` / `fd55969e..a7341ca4  HEAD -> main`; a dry run, nothing pushed. The 2026-08-06 counterexample reproduces on this session |
| 9 | `git var GIT_COMMITTER_IDENT` | refused |
| 10 | `git commit --amend -m "test: #695 collapse target commit amended"` | **ran** — `7683632a` → `d17598d3`, parent kept, date line printed. The known positive, on this session's own record |
| — | `git --version` | refused — even the version probe is outside the granted prefixes |
| — | `git merge --squash d17598d33283ee9b5ad5535c9780d7d4dc66c48c` | refused |
| — | `git checkout d17598d33283ee9b5ad5535c9780d7d4dc66c48c -- scratch-695-one.txt scratch-695-two.txt scratch-695-three.txt scratch-695-four.txt scratch-695-five.txt` | refused |
| — | `git apply --index collapse-695.patch` | refused |
| — | `git commit -m "fixup! test: #695 collapse target commit amended"` | **refused by this repository's own `commit-msg` hook**, a third refusal origin: exit 1 and cocogitto's own text, `Error: Missing commit type separator ':'`. The `--autosquash` collapse route is closed by this repo's message gate, not by permissions. `git add` had already staged the content, and that staged leftover caused the autostash conflict below |
| — | `git stash drop fdb608a1` | refused; `git stash list` **ran** — `stash@{0}: autostash`. The read form of a verb is permitted where the mutating form is refused |
| — | `printenv CTI_DISPATCH_ID CTI_DISPATCH_LANE CTI_DISPATCH_PROFILE CTI_DISPATCH_SEAT CLAUDE_EFFORT CTI_DISPATCH_WORKTREE` (chained with `echo "exit=$?"`) | refused — `This Bash command contains multiple operations. The following parts require approval: printenv …, echo "exit=$?"` |
| — | `printenv CTI_DISPATCH_ID` | refused |
| — | `ls /home/andre/.arma-cti/dispatches` | refused — `ls in '/home/andre/.arma-cti/dispatches' was blocked. For security, Claude Code may only list files in the allowed working directories for this session: '/home/andre/code/github.com/andrewesweet/arma-cti/.claude/worktrees/issue-695'.` |
| — | `cat /proc/self/environ` | refused — `Accesses /proc/*/environ which may expose secrets` |
| — | a `Read` of `/home/andre/.claude/settings.json` | refused — `Claude requested permissions to read from /home/andre/.claude/settings.json, but you haven't granted it yet.` |

**One dated correction to this document's cause 3.** The 2026-08-10 record says a `&&` chain gets no read-only auto-approval as a whole. On 2026-09-03, `git status --short --branch && git log --oneline -3 && cat .gitignore` and `rm scratch-695-target.txt && git add scratch-695-target.txt && git status --short` both **ran**, and `git rebase … && git stash drop fdb608a1 && …` was refused while naming only the refused part: `This Bash command contains multiple operations. The following part requires approval: git stash drop fdb608a1`. The decomposition survives; the blanket "no chain approval" does not. Dated, not rewritten.

**The autostash hazard, witnessed.** A permitted `git rebase --onto` over a tree dirtied by the refused `fixup!` commit produced:

```
Created autostash: fdb608a1
Applying autostash resulted in conflicts.
Your changes are safe in the stash.
You can run "git stash pop" or "git stash drop" at any time.
Successfully rebased and updated detached HEAD.
```

It left an unmerged path (`DU scratch-695-target.txt`) to resolve — `rm` plus `git add` cleared it — and the stash entry `fdb608a1` survives because `git stash drop` is refused. Clearing `stash@{0}` is owed to this session's successor; it is named here because no permitted command reaches it.

**The collapse itself, which falsifies H.** After the autostash rebase, HEAD stood at `a7341ca4` and the four commits above it (`1ffa0596`, `890c4209`, `d5e7a571`, `d17598d3`) were dangling but intact. Their combined tree was re-authored through the harness's `Write` tool — four files at exactly the contents the tip held — then:

```
git add scratch-695-two.txt scratch-695-three.txt scratch-695-four.txt scratch-695-target.txt && git commit -m "test: #695 four commits collapsed into one"
```

produced `ed7a55cd` (tree `dc3d1a07`), **one commit where four had been**, and the falsifier's identity check:

```
git diff d17598d33283ee9b5ad5535c9780d7d4dc66c48c HEAD
```

returned **empty**. Four commits collapsed into one, same tree, only permitted commands. The route is **drop and rebuild**: `git rebase --onto` moves HEAD off the commits, the session re-authors the tip's final content — which a session that authored those commits always has in its own transcript, and can read back through the permitted `git diff <keep> <tip>` — and commits once.

**What this surface closes and what it does not.** Closed: every git-side collapse verb measured — `reset`, `commit-tree`, `update-ref`, `branch`, `merge`, `checkout <sha> --`, `apply --index`, `config` — and every route to a rebase todo editor: environment assignment, `-c` prefix, `git config`, and `fixup!`/`squash!` messages through the repo's own commit-msg hook. Open: `git rebase` in full, including `-i`, which drops, reorders, replays and never squashes here; `git commit --amend`; and the drop-and-rebuild collapse above. `codex` remains out of scope, and this session's lane label is unknown from inside (arrangement above); every claim here belongs to the allowlist-resolving surface, not to a lane name.

**Not claimed:** anything about any command absent from the tables above — neither its permission nor its effect. The rows are provocations, not a bound.
