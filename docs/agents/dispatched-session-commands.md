# A dispatched session's command surface

**Outcome: the refused-command list a dispatched session runs into is not one list, it is three causes, and the largest one is ours.** Four of the seven commands #294 recorded as refused — `grep`, `rg`, `find`, `wc` — are refused only because RTK rewrites them before the permission decision is taken. Escaping the rewrite (`\grep`) makes them work. The other three are refused on their own merits and no escape helps.

Measured on 2026-08-10 from inside a dispatched session (#294): `claude --print --model opus --effort high --permission-mode acceptEdits`, lane `claude-native`, seat `implementer`. Every row was provoked in that session, not predicted.

For where a dispatched session may *write*, see `docs/multi-provider-dispatch.md`, "Reserved on every lane: everything under `.claude/`".

## The measurement

| Command | Bare | Escaped (`\cmd`) |
|---|---|---|
| `grep`, `rg`, `find`, `wc` | refused — `This command requires approval` | **runs** |
| `awk` | refused | refused |
| `python3 -c` | refused | refused |
| `uv run python -c` | refused | — |
| `ls`, `cat`, `sed -n`, `jq`, `tr`, `echo`, `printf` | runs | — |

## The three causes

**1. RTK's rewrite, for `grep`, `rg`, `find`, `wc`.** `~/.claude/settings.json` wires `rtk hook claude` as a `PreToolUse` hook on Bash, and the permission decision is taken on the **rewritten** command. This session's first compound command came back with

```
The following parts require approval: rtk git status --short --branch, rtk git log --oneline -1
```

naming a form nobody typed. `rtk grep …` is not something the harness recognises as a read, so it goes to a prompt — and a dispatched session is `--print`, with nobody to answer one. A backslash defeats the rewrite, which is why `\grep` sat on #294's *allowed* list beside `grep` on its *refused* list: they are the same command, and the escape is the whole difference.

This is the RTK.md caution biting in a place it was not written for. That caution is about not trusting an absence seen through the filter; this is the filter changing what the harness is asked to approve.

**2. Arbitrary execution, for `awk`, `python3 -c`, `uv run python -c`.** Refused escaped as well as bare. Each can write files and run arbitrary code, so the harness does not auto-approve it under `acceptEdits`. No escape helps and none should.

**3. Compound decomposition.** A `&&`, `;` or `|` chain is split and every part must be permitted on its own, with no read-only auto-approval for the chain as a whole:

```
printf … | tee f      → The following part requires approval: tee …
echo '…' | rtk hook claude  → The following part requires approval: rtk hook claude
```

A command that runs perfectly well alone can be refused inside a chain — which is how a session loses a turn to a one-line pipeline it had no reason to doubt.

## Two confinements worth knowing before you meet them

- **`grep` is confined to the session's working directory**, and says so: `grep in '…' was blocked. For security, Claude Code may only search for patterns in files from the allowed working directories for this session: '…'`. `cat` on the very same outside path runs. So a dispatched session can *read* a dispatch record under `~/.arma-cti/` and cannot *search* one; pipe it (`cat f | \grep …`) when you must.
- **The project allowlist is in force and does the deciding for `just`.** `just land --dry-run` runs on its `Bash(just land --dry-run)` grant; `just probe-contract`, which has no grant, is refused. Nothing distinguishes them but the allowlist.

## What to do about it

Nothing that widens anything — #248's ruling puts permissions with the human, and the narrow-recipe pattern (`just discard`, `just mutation-compare`) is the approved shape. What this buys is a brief that costs nothing to compose and a dispatch that does not spend itself rediscovering the list:

- prefer `\grep`, `\rg`, `\find`, `\wc`;
- keep reads out of `&&` chains;
- reach for a `just` recipe rather than `python3 -c` — and note that whatever a recipe's subprocess does is invisible to the permission check, which is why the grant belongs on a *narrow* recipe rather than a general one. `just land --dry-run` created a `.venv` in passing; the harness saw a `just` command and nothing else.

## What this does not establish

- Whether `rtk`'s rewrite could be narrowed so that `grep` survives it. That is a change to a user-level hook outside this repository, and it is the human's.
- Anything about a foreign lane. Every row here is `claude-native`; Codex and z.ai reach the shell through different sandboxes and would each have to be measured.
