# Dispatching work to another provider

The design behind `just dispatch` and `just breaker`. `CLAUDE.md` carries the rules an
agent must not get wrong in the moment — the eligible seats, the credential handling, the
prohibition on exporting a lane variable, the prohibition on inventing a breaker's wait.
Everything here is the reasoning under those rules, moved out of the always-loaded prefix
by the human's ruling on #228 (2026-08-05, Decision 2) so that the prefix carries the rule
and this document carries why it is the rule.

Binding decision: ADR-0061. Implementation: `tools/dispatch.py`, `tools/breaker.py`. The
ledger that records what a dispatch cost is a separate document, `docs/telemetry-ledger.md`.
The **review** seat has a shape of its own — what it is handed, the claims-cite-code contract
it hands back, where those claims route, and how a confirmed one reaches the admission bar —
and that is `docs/review-dispatch.md`.

## Lanes and profiles

A **lane** is a provider and the environment that reaches it. A **profile** is one opaque
`(lane, model, effort)` token in `tools/dispatch.py`'s registry. Week one registers
`claude-native` and `zai`.

The recipe has no `--model` and no `--effort`, and that absence is the design (ADR-0061
Decision 5). Effort vocabularies do not commensurate across providers: GLM Max and Opus
high are not the same quantity, and the mapping between them is not monotonic, so a
dispatcher offered both dimensions separately would be inviting an agent to compose a
pair no one has ever measured. A profile is measured or it is not registered.

The z.ai lane made the argument concrete rather than abstract (#225). Claude Code's five
effort levels differ only in the `thinking.budget_tokens` they send, and that endpoint
ignores the field — a hard prompt at budget 1,024 and at budget 32,000 both thought past
nine thousand tokens and both stopped on `max_tokens`. So on that lane all five efforts
are one configuration, and there is one profile per model rather than five.

## The environment is assembled per invocation

`ANTHROPIC_BASE_URL` in a shell profile, in a `~/.claude/settings.json`, or exported into
a session redirects **every** Claude Code process that inherits it, the orchestrator's own
session included. There is no scope on it smaller than the process tree, which is why the
rule in `CLAUDE.md` is a `Never` rather than a preference.

The dispatcher therefore builds the child's environment for each invocation and exports it
nowhere. Assembly **strips every lane-owned variable from the inherited environment before
adding this lane's**, so a shell that is already carrying one produces the same child as a
clean shell. That property is what makes a dispatch reproducible from its record: without
the strip, the plan in `dispatch.json` would describe the variables the dispatcher added
and be silent about the ones it did not remove.

Credentials come from `~/.arma-cti/credentials.env` at mode 0600, by environment only.
Never on argv, so never in `ps`; never echoed; and the dispatch record names the key it
used and not its value. `just prereqs credentials` is the only writer of that file, it
reads the value off the terminal with echo off, and it refuses if the path ever resolves
inside a git work tree.

## The worktree assertion

The dispatched process asserts `git rev-parse --show-toplevel` against its assignment
before the runner starts, and refuses loudly on a mismatch.

This exists because of #105: worktree assignment handed two agents one tree five times in
one evening, and the failure is silent at the moment it happens — two agents in one tree
both see a clean `git status` and both believe the tree is theirs. A check inside the
dispatcher catches the assignment error while it is still an assignment error, rather than
after one agent's routine reset has destroyed the other's work.

A lane that cannot be reached — no credentials file, no key, no worktree — is
`infra_unavailable`, and `infra_unavailable` is not a result.

## The breaker, and why it never invents a wait

`just breaker` carries two trip families, and the whole design falls out of their
difference.

**Availability.** The lane cannot serve right now; quota exhaustion is the common case. It
is foreseeable, and its wait is *computed from a provider's published window boundary,
never guessed*. That is ADR-0061 Decision 7's requirement, and it is why
`quota_exhausted` earned a failure-class row of its own rather than routing to
`infra_unavailable`. A quota trip auto-resets: at the reset time one dispatch probes the
lane and an ordinary outcome restores it.

**Quality.** The lane is serving, and what it serves is wrong: N consecutive gate failures
or refusals on one profile. This is the only thing that catches a provider swapping the
model behind a name with no announcement. It does not auto-reset, because time does not
fix it. It escalates, and a human clears it with `just breaker reset --lane L --force`.

A third case looks like the first and must not behave like it: N consecutive provider
errors with **no** published reset. That holds the lane rather than scheduling a retry.

### The measured derivation

Inventing a cooldown in that third case is the exact defect that disqualified LiteLLM as
this project's breaker: a five-second reactive damper measured against five-hour and
weekly windows (`docs/research/multi-provider-routing-substrates.md` §3.2). Five seconds
is not a wrong number that could be tuned to a right one — it is the wrong *kind* of
number, a damper for a transient against a window whose boundary is published and
knowable. Against a five-hour window a guessed wait burns the window it was guessing
about.

That is where `CLAUDE.md`'s `Never extend, invent or guess a breaker's wait` comes from,
and it is the `timeout` failure-class row's discipline — *never extend the timeout to
pass* — transposed onto quota. The parenthetical citation stays in the prefix on purpose:
it is what stops the rule being re-derived from first principles by someone who thinks
five seconds sounds reasonable.

## `open` and `closed`, and why the verdict line says neither

`tools/breaker.py` uses the electrical convention internally — a **closed** circuit
conducts, so a closed breaker dispatches — because that is the convention the pattern is
named for and every reference on circuit breakers uses.

Every human-facing line avoids both words, printing `dispatch=refused` or
`dispatch=allowed`. The words mean opposite things to an electrician and to a shopkeeper,
and #226's own issue text used both senses in one document — its acceptance criterion says
an *open* lane proceeds, its scope section says `quota_exhausted` *opens* the lane until
reset — so nothing in that issue settles it. A verdict line that needs its convention
explained is a verdict line that gets misread.

Ratified as implemented by the human's ruling on #228 (Decision 6), and recorded here so
it is not re-litigated at the next breaker change.

## What a dispatched session may do, stated per lane

The human ruled on 2026-08-06 (#221 decision 1 and 2, implemented as #259) that a
dispatched session gets the gate and the commit, so that a foreign lane stops needing a
Claude-side finisher to turn its work into a landing. The ruling was taken with an explicit
caution attached, and this section exists to honour it: **the two lanes are widened by
different mechanisms of different granularity, and nothing here claims they are equivalent.**
ADR-0061 decision 5 makes the same point about effort levels; it applies to permission just
as well.

### Reserved on every lane: everything under `.claude/`

A dispatched session cannot write anywhere under `.claude/`, whatever lane it is on and
whatever the project allowlist says. This is a property of the harness rather than of a
lane, so it is stated once here rather than twice below.

Measured on `claude-native` on 2026-08-10 (#294), from a dispatched session in its own
worktree, reproducing the two refusals #273's Codex dispatch reported three days earlier:

| Attempt | Result |
|---|---|
| `Write` to `.claude/hooks/PERMISSION-PROBE.md` | refused — *"which is a sensitive file"* |
| `Write` to `.claude/notes/PERMISSION-PROBE.md` | refused — *"which is a sensitive file"* |
| `Write` to `.claude/skills/retro/PERMISSION-PROBE.md` | refused — *"you haven't granted it yet"* |
| `Write` to `.claude/agents/PERMISSION-PROBE.md` | refused — *"you haven't granted it yet"* |
| `printf … > .claude/skills/retro/PERMISSION-PROBE.md` | refused — *"you haven't granted it yet"*, naming the path |
| `cp docs/…  .claude/skills/retro/PERMISSION-PROBE.md` | refused — the same, naming the destination |
| `Write` to `docs/PERMISSION-PROBE.md` | written |
| `Write` to an unlisted path at the worktree root | written |

Four readings, in the order they matter:

- **The two refusals are two mechanisms, and the split is not the one the allowlist
  predicts.** `.claude/hooks/` and an invented `.claude/notes/` are classified sensitive;
  `.claude/skills/` and `.claude/agents/` are not, and fall to an ordinary permission ask.
  So the sensitive class is the *default* for the directory and the two content
  subdirectories are exempted from it — into an ask, not into a grant.
- **The project allowlist does not reach it.** `.claude/settings.json` grants both
  `Edit(.claude/skills/**)` and `Write(.claude/skills/**)`, and the write was still asked
  for. In the same session `just fast` ran on its `Bash(just fast)` grant, so the allowlist
  was in force; it is overridden for this directory, not absent.
- **An ask is a refusal here.** A dispatched session is `claude --print` with nobody to
  answer a prompt, which is why the orchestrator's own interactive session lands these
  edits by hand and a dispatch cannot. The barrier is "a human must answer", not "nobody
  may write".
- **The shell is not a way round it.** The harness reads a Bash command's write targets:
  the redirect and the `cp` destination were refused by path, with the same wording as the
  tool call. #265's "re-express it as a shell append" does not reproduce here.

**The routing consequence.** No route a dispatched session can reach exists today. A `just`
recipe that promotes a reviewed file into `.claude/` would need its own `Bash(just …)` grant
in `.claude/settings.json`, which is a permissions decision and therefore the human's
(#248); it is proposed on #294 rather than landed. Meanwhile the wall costs ergonomics
rather than authority: every surface under `.claude/` — the project skills, the seat
definitions, the hooks and the settings file — is human sign-off gated by CLAUDE.md
already, so no dispatched session was ever entitled to land one of these unilaterally. The
route that works is the one #299 already mandates for a gated edit: the dispatched seat
authors the exact replacement text as a proposal, and the orchestrator transcribes it.
`tools/brief.py` says so in the brief when an issue names such a path, so the next dispatch
learns it at composition time instead of spending itself finding out.

**What is not established.** Whether a *user-level* or enterprise settings grant would be
honoured where the project one is not; and whether a write performed inside a subprocess the
harness cannot parse would pass, since `python3 -c` and `uv run` are not on a dispatched
session's command surface and neither could be measured from that seat.

### `zai` — a list of named commands

The lane rides the `claude` binary, so it inherits `.claude/settings.json`'s allowlist.
`--permission-mode` is unchanged at `acceptEdits`. The grant is eight entries and it is
exhaustive: `just check`, `just unit`, `just fast`, `git add`, `git commit`, and read-only
`git status`, `git diff` and `git log`. `just land` and `just land --dry-run` were already
there and remain the only push path — `tools/land.py`'s refspec is a constant no argument
reaches. Bare `git push` and `git commit --no-verify` are deliberately absent.

Measured live by dispatches `d-20260806-163123-e8bed7` and `d-20260806-165934-de5015`, which
between them ran every one of those commands, committed their own work at `73a0d5c`, gated
it and landed it at `a609127` with no Claude-side involvement. Two readings from the same
runs are worth keeping:

- `git commit --no-verify` was **refused**, by the hook rather than by the allowlist. That
  is the whole safety argument for widening: `PreToolUse` fires before any permission-mode
  check, in every permission mode (vendor, `code.claude.com/docs/en/hooks-guide.md`), so
  enforcement sits upstream of permission and a wider allowlist cannot reach it.
- `git push --dry-run origin HEAD:main` was **permitted**, although this repository grants
  no `git push` in any form. The grant came from a user-level `Bash(git push *)` entry on
  this box. So the project allowlist describes what this repository asks for; it does not by
  itself bound what a session on this machine can do.

### `codex` — a filesystem and network policy

The lane does not read `.claude/settings.json`'s allowlist at all. `tools/dispatch.py` maps
the permission mode to a sandbox policy, and `acceptEdits` is `--sandbox workspace-write`
plus, on that mode only, three writable roots and network access. Every command the session
runs inherits all of it; there is no per-command list to consult.

What that buys, measured rather than inferred, over four dispatches and three probes:

- Plain `workspace-write` grants the session's own worktree and nothing above it. `git
  status`, `git log` and `git diff` worked; `git add` did not, because a linked worktree's
  index lives under the main checkout's `.git`.
- Codex refuses a write under a `.git` directory unless **that exact directory** is a
  writable root. Naming an ancestor does not lift it for a nested one — with `<main>/.git`
  granted, `<main>/.git/topA` was created and
  `<main>/.git/worktrees/<name>/subB` was refused in the same command. Both directories are
  therefore derived from git and granted.
- The gate additionally needs `~/.cache/uv`, where `uv` takes a lock before any test runs.
  `~/.cargo` looked as likely and was measured unnecessary, so it is not granted.
- `network_access` defaults off and `just land` fetches and pushes, so it is enabled.

Read-only seats keep the sandbox they always had, and
`--dangerously-bypass-approvals-and-sandbox` was put to the human, declined, and is unused.

**The lane does not reach a landing, and the reason is a recorded ceiling rather than a fix
still owed.** The two capabilities the ruling asked for are exclusive on this lane, isolated
by running `cog check` under each root set in the same worktree at the same commit:

| writable roots | `git add` / `git commit` | `cog check`, the gate's first step |
|---|---|---|
| main checkout, `<main>/.git`, `~/.cache/uv` | refused, `index.lock` read-only | `No errored commits` |
| the same plus `<main>/.git/worktrees/<name>` | exit 0, no escalation | `failed to open repository … could not find repository at '<main>/.git/worktrees/<name>/'` |
| the four-root set with `<name>` replaced by its parent `<main>/.git/worktrees` | refused, `index.lock` read-only (`d-20260808-075346-f27564`) | not reached |

`cog` reads the repository through libgit2, and granting the per-worktree git directory as
a *writable* root is what stops libgit2 opening it — the same directory it opens without
complaint outside the sandbox, and under the three-root set. The mechanism is measured: a
read-only strace over `cog check` in the sandbox (`d-20260807-222221-1a2c7e`) found the
sandbox creates an empty `<main>/.git/worktrees/<name>/.git` directory (mode 0555) — a mount
point injected for that writable root, where no real git layout puts a `.git` — which libgit2
stats during discovery, mistakes for a repository, and reports missing when its `commondir`
and `HEAD` are absent. The refusals read `Read-only file system` (EROFS), not the `EACCES` a
Landlock denial produces, so the sandbox is mount-based (Codex bundles `bwrap`) rather than
Landlock-based; #265's "Landlock composition" first-suspect is refuted by its own recorded
evidence. The parent-grant alternative — the third row — is refuted too: it is the set
`d12a27f` shipped, and the carve-out that holds `.git` read-only does not confer write on a
nested directory merely by naming an ancestor.

So the dichotomy is structural: a commit needs the exact per-worktree directory named, else
its `index.lock` is read-only; the gate needs that same directory not named, else the injected
`.git` defeats libgit2. No `writable_roots` set satisfies both, and
`--dangerously-bypass-approvals-and-sandbox` was declined on #221. The four-root set stands as
the known-good commit baseline, the gate is a recorded ceiling, and a Codex dispatch that
finishes its work lands by a hand finish rather than unaided. Dispatch `d-20260806-172045-9a0a0e`
is the end-to-end attempt under the four-root set: it committed its own work at `fb093fe` under
the sandbox with no escalation, stopped on that red as it was told to, and did not land. The
full finding and the consequence for the admission bar are in §10 of
`docs/research/codex-lane-live-findings.md`; this section implements #259's ruling and carries
#265 as its recorded ceiling rather than stretching #259 to cover it.

### Where they are not comparable

Network access is the clearest case. On `codex` it is a property of the sandbox, so every
command the session runs can reach the network. On `zai` nothing grants network capability
as such; only the commands on the list run at all, and of those only `just land` and `gh`
talk to anything remote. The same intent, delivered by mechanisms whose blast radius does
not match — which is why this section states them separately rather than as one table.

One more asymmetry, and it is a property of this box rather than of either ruling: Codex's
`approvals_reviewer = "auto_review"` can approve a command's escalation *out* of the
sandbox, and dispatch `d-20260806-165944-1b31e5` reached a green landing that way while the
sandbox was still refusing its `git add`. A sandbox that a reviewer model can be asked to
step outside is not a containment boundary in the way an allowlist is.
