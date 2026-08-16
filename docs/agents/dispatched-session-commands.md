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
| `python3 -c` | refused | refused |
| `uv run python -c` | refused | — |
| `ls`, `cat`, `sed -n`, `jq`, `tr`, `echo`, `printf` | runs | — |

## The three causes

**1. RTK's rewrite, for `grep`, `rg`, `find`, `wc` — the cause that no longer exists.** On 2026-08-10 `~/.claude/settings.json` wired `rtk hook claude` as a `PreToolUse` hook on Bash, and the permission decision was taken on the **rewritten** command. That session's first compound command came back with

```
The following parts require approval: rtk git status --short --branch, rtk git log --oneline -1
```

naming a form nobody typed. `rtk grep …` was not something the harness recognised as a read, so it went to a prompt — and a dispatched session is `--print`, with nobody to answer one. A backslash defeated the rewrite, which is why `\grep` sat on #294's *allowed* list beside `grep` on its *refused* list: they are the same command, and the escape was the whole difference.

**Re-measured 2026-08-16 (#396), RTK removed from the host.** Bare `grep -c … AGENTS.md`, `rg -c … AGENTS.md`, `find . -maxdepth 1 -name AGENTS.md` and `wc -l AGENTS.md` were each attempted individually in a dispatched session and each ran, with no approval prompt. The whole of cause 1 is discharged, and no escape is needed for these four. Caveat on the measurement's reach: it was taken in one session under this repository's own allowlist, so a seat still meeting a refusal on one of these four is meeting something other than the rewrite and should record what.

The generalisable half, kept because the mechanism can return: any hook that rewrites a Bash command before the permission decision changes *what the harness is asked to approve*, so an absence or a refusal seen through it is a fact about the filter and not about the command.

**2. Arbitrary execution, for `awk`, `python3 -c`, `uv run python -c`.** Refused escaped as well as bare. Each can write files and run arbitrary code, so the harness does not auto-approve it under `acceptEdits`. No escape helps and none should.

**3. Compound decomposition.** A `&&`, `;` or `|` chain is split and every part must be permitted on its own, with no read-only auto-approval for the chain as a whole:

```
printf … | tee f      → The following part requires approval: tee …
echo '…' | rtk hook claude  → The following part requires approval: rtk hook claude
```

(The second line is the 2026-08-10 transcript verbatim; `rtk` is no longer installed, so that exact command would now fail on its own account. The decomposition it demonstrates is unchanged.)

A command that runs perfectly well alone can be refused inside a chain — which is how a session loses a turn to a one-line pipeline it had no reason to doubt.

## Two confinements worth knowing before you meet them

- **`grep` is confined to the session's working directory**, and says so: `grep in '…' was blocked. For security, Claude Code may only search for patterns in files from the allowed working directories for this session: '…'`. `cat` on the very same outside path runs. So a dispatched session can *read* a dispatch record under `~/.arma-cti/` and cannot *search* one; pipe it (`cat f | grep …`) when you must. This confinement is the harness's own and has nothing to do with the removed rewrite.
- **The project allowlist is in force and does the deciding for `just`.** `just land --dry-run` runs on its `Bash(just land --dry-run)` grant; `just probe-contract`, which has no grant, is refused. Nothing distinguishes them but the allowlist.

## What to do about it

Nothing that widens anything — #248's ruling puts permissions with the human, and the narrow-recipe pattern (`just discard`, `just mutation-compare`) is the approved shape. What this buys is a brief that costs nothing to compose and a dispatch that does not spend itself rediscovering the list:

- `grep`, `rg`, `find` and `wc` run bare since 2026-08-16; the `\grep` escape is harmless but buys nothing now;
- keep reads out of `&&` chains;
- reach for a `just` recipe rather than `python3 -c` — and note that whatever a recipe's subprocess does is invisible to the permission check, which is why the grant belongs on a *narrow* recipe rather than a general one. `just land --dry-run` created a `.venv` in passing; the harness saw a `just` command and nothing else.

## What this does not establish

- Anything about `awk`, `python3 -c` or `uv run python -c` under the removed rewrite: they were refused on their own merits on 2026-08-10 and were **not** re-measured on 2026-08-16, because nothing about their cause changed. A seat that needs one still reaches for a `just` recipe.
- Anything about a foreign lane. Every row here is `claude-native`; Codex and z.ai reach the shell through different sandboxes and would each have to be measured.
