# Porting this project's instructions and enforcement to Codex and opencode

<!-- absent-path -->
<!-- A dated research record: the repository paths it cites are the tree as it stood when
     the research was done, and some belong to other projects entirely. Neither is a claim
     about this tree today, which is what the marker above tells `just check-doc-paths`. -->

**Explored**: 2026-08-05, research dispatch R4. APM 0.28.0 at `dcbaf65`, rulesync 16.7.0 at `2249ab5`, opencode clone at `/home/andre/code/github.com/anomalyco/opencode`, both compilers installed and run against scratch projects.
**Outcome**: **ruling 7 does not survive as stated.** `apm compile` emits no hook configuration for any target — not Codex, not opencode, not Claude Code. APM does emit `.claude/settings.json` and `.codex/hooks.json`, but from `apm install`, as a *dependency-package* primitive, and it emits **nothing at all** for opencode, which its own targets matrix records as unsupported. A second compiler, **rulesync**, does emit both `.codex/hooks.json` and an opencode plugin module — but the opencode module it generates does not work for hooks shaped like ours, for two reasons demonstrated below.

The practical recommendation: **Codex hook parity is close to free either way; opencode hook parity is a bridge we write ourselves, whichever compiler we pick.** No tool on the market carries a Claude-Code-shaped stdin hook into opencode's in-process plugin API. That is one hand-written file, not a research programme, and it is the same file under APM, under rulesync, and under no compiler at all.

Evidence class is marked per claim: **[ran]** = I executed it here and quote the output; **[source]** = I read the implementation or the type definition; **[docs]** = documented by the vendor but untested here; **[delegated]** = a primary source read by a subagent, not by me; **[inferred]**.

## 1. What APM actually emits

### `apm compile` writes three Markdown files and nothing else

Run against a scratch project carrying `.apm/instructions/`, `.apm/context/`, `.apm/agents/` and `.apm/hooks/`, with `.claude/`, `.codex/`, `.opencode/` and `.cursor/` all present so no target could be skipped for a missing directory **[ran]**:

```
$ apm compile --target all
[i] Compiling for AGENTS.md + CLAUDE.md + GEMINI.md +
.github/copilot-instructions.md + .github/ + .claude/ + .cursor/ + .opencode/ +
.codex/ + .gemini/ + .windsurf/ + .kiro/ + .agents/ - explicit --target flag
...
[+] Compilation completed successfully!

=== FILES PRODUCED ===
./AGENTS.md
./CLAUDE.md
./GEMINI.md
```

The banner names eleven target directories; three files appear. The command's own help string is honest about it: `"Compile APM context into distributed AGENTS.md files"` **[source: `src/apm_cli/commands/compile/cli.py:936`]**. `grep -rni hook src/apm_cli/commands/compile/ src/apm_cli/compilation/` returns no match — the compile subtree contains no reference to hooks at all **[source]**.

So the compile step covers instructions and context. It does not cover agent definitions either — those arrive at install time.

### `apm install` is where hooks live, and opencode is not a target

The same project, installed **[ran]**:

```
$ apm install --target all
  |-- 7 agents integrated -> 7 targets
  |-- 6 rule(s) integrated -> 6 targets
  |-- 7 hook(s) integrated -> 7 targets
  |   PreToolUse: runs ${CLAUDE_PROJECT_DIR}/.claude/hooks/probe/scripts/guard.py
  |   PreToolUse: runs .codex/hooks/probe/scripts/guard.py
  |   preToolUse: runs .github/hooks/scripts/probe/scripts/guard.py
  |   PreToolUse: runs .cursor/hooks/probe/scripts/guard.py
  |   BeforeTool: runs .gemini/hooks/probe/scripts/guard.py
  |   PreToolUse: runs .kiro/hooks/probe/scripts/guard.py
  |   PreToolUse: runs .windsurf/hooks/probe/scripts/guard.py
```

Nine targets were active; seven received the hook. `.opencode/` received exactly one file, `agents/impl.md`. The emitted `.codex/hooks.json` and `.claude/settings.json` are structurally identical apart from the script path, which Claude gets as `${CLAUDE_PROJECT_DIR}`-anchored and Codex gets repo-relative **[ran]**.

This is not an accident of my fixture. `_MERGE_HOOK_TARGETS` in `src/apm_cli/integration/hook_integrator.py:313` holds six entries — claude, cursor, codex, gemini, antigravity, windsurf — and opencode is not among them **[source]**. APM's own reference states the reason:

> **Caveat.** OpenCode has no hooks concept; the `hooks` primitive is silently skipped for this target.
> — `docs/src/content/docs/reference/targets-matrix.md:218` **[source]**

That caveat is **factually wrong as of August 2026**, and the error matters because it is unlikely to be fixed by accident: opencode has had an in-process plugin API with `tool.execute.before`, `permission.ask` and `chat.message` for long enough that the vendored clone documents twenty-six event names (§4). APM has not modelled it because APM's hook abstraction is *a JSON file merged into a config file*, and opencode has no such file. Adopting APM does not put us in the queue for opencode hooks; it puts us in a queue for a feature whose shape APM's design does not accommodate.

APM's authoring guide is blunt about the scope, and this is the sentence to weigh ruling 7 against:

> Hooks and slash commands are the two APM primitives that do not pretend to be portable. Unlike skills or instructions, they ship to a strict subset of harnesses, never get folded into `AGENTS.md`, and rely on each target's own format.
> — `docs/src/content/docs/producer/author-primitives/hooks-and-commands.md` **[source]**

Note also the inverse gap: slash **commands** ship to opencode and *not* to Codex **[source, same doc]**. Neither primitive is portable in the direction ruling 7 needs.

## 2. APM's cost and fit, if we adopt it anyway

**The registry, lockfile and policy layers can be ignored.** My probe project declared `dependencies: {apm: [], mcp: []}` and both `compile` and `install` completed offline, generating a trivial `apm.lock.yaml`; no registry was contacted and no `apm-policy.yml` existed **[ran]**. Policy discovery is org-level and opt-in **[source: `src/apm_cli/policy/discovery.py`]**.

**`--validate` is usable standalone.** `apm compile --validate` parsed the primitives, reported `1 chatmodes, 1 instructions, 1 contexts`, wrote nothing, exit 0 **[ran]**.

**Drift detection exists, and does not cover the file we care most about.** The documented spelling `apm audit --check drift` does not exist in 0.28.0 — `Error: No such option '--check'` — but bare `apm audit` runs the replay **[ran]**. It caught a hand-edit to `.codex/hooks.json`:

```
[x] Drift detected: 1 file(s)
  modified (1):
    - .codex/hooks.json
```

In the same run I had appended a line to the generated `CLAUDE.md`. It was **not** reported, then or on a second run: `CLAUDE.md`, `AGENTS.md` and `GEMINI.md` appear nowhere in `apm.lock.yaml`, and the drift replay diffs only lockfile-tracked deployments **[ran]**. So if `CLAUDE.md` becomes a generated file, APM gives us **no mechanical detection of a hand-edit to it**. The sign-off gate would move to the source primitive and lose its enforcement, not gain one — `.claude/hooks/protect-gated-paths.py` would have to grow a `CLAUDE.md` entry to replace what the gate loses.

**Worse, the generated `CLAUDE.md` is conditionally generated.** After `apm install` populated `.claude/rules/`, a subsequent compile declined to write it at all **[ran]**:

```
$ apm compile --target claude
[i] CLAUDE.md not generated -- Claude Code reads .claude/rules/ directly, no
further action needed
[!] Compilation completed but produced no output files.
```

That is the deduplication path `--force-instructions` / `--no-dedup` overrides **[source: `cli.py:1011`]**. Left at its default, a repository whose governing document is `CLAUDE.md` would carry a stale one that no later compile refreshes. This is a configuration trap, not a blocker, but it is exactly the failure mode a heavily-governed file must not have.

**Partial hand-authorship is available for `AGENTS.md` only.** `agents_md.mode: managed_section` replaces only the text between markers and preserves everything outside them verbatim **[source: `src/apm_cli/compilation/managed_section.py`]**. There is no equivalent for `CLAUDE.md`, which is written whole, headed `<!-- Generated by APM CLI -->` and a `Build ID` **[ran]**.

**Provider-conditional content costs a package split.** Filename routing (`claude-codex-hooks.json`) still works but warns as deprecated **[source: `hook_file_routing.py:63,177`]**. The supported mechanism is a `target:` / `targets:` key in a package's *own* `apm.yml`, intersected with the consumer's active targets:

```text
effective hook targets =
  project active targets
  INTERSECT consumer per-dependency targets (when set)
  INTERSECT package targets (when restrictive)
```
— **[source: hooks-and-commands.md]**

Every selector narrows; none can expand. Expressing "this hook for Claude and Codex, that shim for opencode" therefore means authoring two or three APM packages with distinct `target:` declarations and depending on them from the root manifest. Instruction-level divergence has no per-target conditional at all — an instruction is placed by relevance scoring, not by target.

## 3. The alternatives

**AGENTS.md is a real standard with one holdout, and the holdout is us.** Codex, opencode, Cursor and Copilot all read `AGENTS.md` natively per their own documentation; Claude Code does not — Anthropic's memory docs state plainly that "Claude Code reads `CLAUDE.md`, not `AGENTS.md`", and prescribe either an `@AGENTS.md` import line or a symlink **[delegated: primary sources at agents.md, code.claude.com/docs/en/memory, learn.chatgpt.com/docs/agent-configuration/agents-md, opencode.ai/docs/rules, cursor.com/docs/context/rules, docs.github.com]**. The `@path` import resolves relative to the importing file, recurses to a depth of 4, is not parsed inside code fences, and loads in full at launch — so it organises without reducing context **[delegated]**.

That makes the cheapest option genuinely cheap: **`AGENTS.md` as the single source, `CLAUDE.md` reduced to `@AGENTS.md`**. It needs no compiler, no lockfile and no new failure mode, it keeps `CLAUDE.md` hand-authored and therefore keeps its sign-off gate exactly where it is, and it covers instructions for all four non-Claude lanes at once. It covers no hooks and no agent definitions.

**rulesync is the only compiler I could confirm crosses into hook territory on both lanes.** I ran it **[ran]**:

```
$ npx -y rulesync@latest generate --targets claudecode,codexcli,opencode --features hooks,rules
Written 3 hooks files
    .claude/settings.json
    .codex/hooks.json
    .opencode/plugins/rulesync-hooks.js
Written 2 rules
    CLAUDE.md
    AGENTS.md
```

Its `.codex/hooks.json` is a faithful translation, with per-handler passthrough for Codex-specific fields (`commandWindows`, `statusMessage`, `additionalContextLimit`) **[source: `src/features/hooks/codexcli-hooks.ts`]**. Its opencode output is a Bun-shell plugin, and here is the whole of what it generated from my two-hook fixture **[ran]**:

```js
export const RulesyncHooksPlugin = async ({ $ }) => {
  return {
    "tool.execute.before": async (input) => {
      {
        const __re = new RegExp("Bash");
        if (__re.test(input.tool)) {
          await $`python3 .claude/hooks/block-no-verify.py`;
        }
      }
    },
    ...
```

Two defects make this unusable for hooks shaped like ours, and both are structural rather than bugs to wait out:

1. **The matcher never matches.** `input.tool` carries opencode's own tool id, which is lowercase: `"bash"` **[source: `packages/opencode/src/tool/shell/id.ts:16`]**, `"read"` **[source: `read.ts:39`]**, `"edit"` **[source: `edit.ts:58`]**. `/Bash/.test("bash")` is false. rulesync copies the Claude-side matcher through verbatim without translating the tool vocabulary, so every generated handler is dead code.
2. **No payload reaches the hook.** The generated call is `await $\`python3 …\`` with nothing on stdin **[source: `opencode-style-generator.ts:163`, and no `stdin` anywhere in that file or its tests]**. Every hook in `.claude/hooks/` begins with `json.load(sys.stdin)` and fails **closed** on an unreadable call. If the matcher were fixed, each of our hooks would exit 2 on an empty stdin, Bun's `$` would throw on the non-zero exit, and every matching tool call would be denied.

There is a third, softer point: rulesync maps `permissionRequest` to opencode's `permission.asked` **event** **[source: `src/types/hooks.ts:1117`]**, which is a notification, not the blocking `permission.ask` hook that carries `output.status: "ask" | "deny" | "allow"` (§4). The one clean deny channel opencode offers is not wired.

**ruler** (`intellectronica/ruler`, MIT, v0.3.44, 2026-06-30) emits Markdown rule files for 31+ targets plus MCP server config, and no hook or permission configuration at all **[delegated]**. **agent-rules** is deprecated in favour of agents.md **[delegated]**. **agentsmesh** claims Codex hooks as "Native" and opencode hooks as "Partial", with the opencode output format unspecified in its docs — **could not verify** **[delegated]**.

## 4. The three enforcement models, side by side

| | Claude Code | Codex | opencode |
|---|---|---|---|
| Mechanism | external process | external process | in-process TS/JS module |
| Config | `.claude/settings.json` | `.codex/hooks.json` or `[hooks]` in `.codex/config.toml` **[docs]** | `.opencode/plugins/*.ts`, or npm packages named in `opencode.json` **[source]** |
| Input | JSON on stdin | JSON on stdin **[docs]** | typed `(input, output)` arguments **[source]** |
| Tool field | `tool_name` / `tool_input` | `tool_name` / `tool_input` **[docs]** | `input.tool` / `output.args` **[source]** |
| Tool vocabulary | `Bash`, `Edit`, `Write`, `Read` | `Bash`, `apply_patch` (also matches `Edit`/`Write`), `update_plan`, `spawn_agent`/`Agent`, `mcp__*` **[docs]** | `bash`, `read`, `edit`, `write`, `task`, … (lowercase) **[source]** |
| Deny | exit 2 + stderr | exit 2 + stderr **[docs]** | `throw` in `tool.execute.before`, or `output.status = "deny"` in `permission.ask` **[source]** |
| Other non-zero | treated as approval (hence our `\|\| exit 2` wiring) | "hook failure", reported — **not** a denial **[docs]** | Bun `$` throws, so it denies **[inferred]** |
| Subagent identity | `agent_id` present iff subagent | `agent_id`, `agent_type` on subagent events; `turn_id` on turn-scoped events **[docs]** | none on `tool.execute.before` — only `sessionID` **[source]** |
| Prompt-submit event | `UserPromptSubmit` | `UserPromptSubmit` **[docs]** | `chat.message` **[source]** |

Two corrections to the dispatch brief, both from source rather than marketing pages:

- **opencode does have a `UserPromptSubmit` equivalent**: `"chat.message"?: (input: {sessionID, agent?, model?, messageID?, variant?}, output: {message: UserMessage, parts: Part[]}) => Promise<void>` **[source: `packages/plugin/src/index.ts:233`]**. It can mutate the message as well as observe it.
- **Blocking is not only by throwing.** `"permission.ask"?: (input: Permission, output: {status: "ask" | "deny" | "allow"})` is a first-class deny channel **[source: `index.ts:260`]**. Throwing from `tool.execute.before` also works — the trigger is awaited *before* `item.execute` **[source: `packages/opencode/src/session/tools.ts:88-93`]** — but it produces an exception rather than a reasoned denial.

The load-bearing structural difference is **subagent identity**. `deny-subagent-waits.py` gates entirely on `agent_id` being present, and opencode's `tool.execute.before` carries no agent field at all. A bridge would have to resolve it: the `task` tool creates the child session with `parentID: ctx.sessionID` **[source: `packages/opencode/src/tool/task.ts:155`]**, so a plugin can call `client.session.get({sessionID})` and treat a non-null `parentID` as "in a subagent". That is one SDK call, but it is a call, and it must fail **closed**.

## 5. This repository's hooks, per lane

Inventory as wired in `.claude/settings.json` **[source]**. Note `deny-closing-trailer.py` sits in `.claude/hooks/` and is wired by nothing in `settings.json`; `shell_reading.py` is a shared library, not a hook.

| Hook | Event / matcher | Codex | opencode |
|---|---|---|---|
| `block-no-verify.py` | PreToolUse Bash | **drop-in** — same `tool_name: "Bash"`, same `tool_input.command`, same exit 2 | **shim** — tool id `bash`, command at `output.args.command` |
| `protect-gated-paths.py` | PreToolUse Edit\|Write\|Bash | **shim** — Codex's edit tool is `apply_patch` and its `tool_input` carries a `command`, not a `file_path` **[docs]**; the path-extraction half needs a patch-format reader | **shim** — `edit`/`write` args, plus the same `bash` translation |
| `deny-oversized-reads.py` | PreToolUse Read | **cannot port as written** — no `Read` tool appears in Codex's canonical tool list **[docs]**; the equivalent read path is Bash or MCP, which is a different rule, not a translation | **shim** — `read` tool, `args.filePath`/`offset`/`limit` map cleanly |
| `deny-subagent-waits.py` | PreToolUse Bash | **shim, highest risk** — depends on `agent_id` being present on `PreToolUse` *inside* a subagent. The docs list `agent_id` under subagent-related events; whether a subagent's `PreToolUse` carries it is **unverified** **[docs]**. If it does not, the gate must key on `agent_type` or `turn_id`, or it silently never fires | **shim + SDK call** — resolve `parentID` via `client.session.get`, fail closed |
| `format-on-edit.py` | PostToolUse Edit\|Write | **drop-in** — advisory, never blocks; only the `file_path` extraction needs the `apply_patch` reader | **shim** — `tool.execute.after`; note opencode ships native formatters, which may make this redundant **[docs]** |
| `lint-after-edit.py` | PostToolUse Edit\|Write | as above | as above |

Read that table as: **one drop-in, four translations and one genuine loss on Codex; six translations on opencode, of which one needs an SDK round-trip.** The translations are not per-hook work. They are one payload-translation module per lane, plus a per-hook mapping table — which is precisely the artefact a parity suite should be testing.

The fail-closed convention needs one deliberate carry-over. Our `.claude/settings.json` appends `|| exit 2` to every blocking handler because Claude Code reads any non-2 exit as approval. Codex reads a non-2 non-zero as a *hook failure* rather than an approval **[docs]**, which is arguably safer, but the emitted config must still carry the `|| exit 2` so the two lanes agree — and no compiler surveyed rewrites shell command strings per target.

## 6. What a hook-parity suite has to do

The ruling makes a lane's authority the set of enforcement it *demonstrably runs*. Two tiers, because one of them is cheap and one of them is not, and only the expensive one actually proves the claim.

**Tier 1 — payload parity, inside `just unit`.** A table of `(hook, lane, trigger fixture, expected verdict)`. For each row: take the canonical Claude-shaped payload for the trigger, run it through that lane's translation module, feed the result to the hook, assert the same verdict — exit 2 and a stderr reason, or exit 0. This is fast, hermetic, and catches everything §5 lists as a translation. It proves the hook *would* decide correctly given a correct payload. It proves nothing about whether the lane delivers one.

Its most valuable rows are the negative ones. Every lane must have a row asserting that an **untranslated** payload is denied, not approved — because the rulesync failure in §3 is exactly that shape, and a suite that only tested the happy path would have called that generated plugin green.

**Tier 2 — lane authority, outside `just unit`.** For each `(hook, lane)` pair, drive the lane's own binary against a repository in a known state with a prompt that makes the trigger inevitable, and assert the lane refused. `codex exec` and `opencode run` are the entry points. This is the tier that earns a lane the right to commit, and it is a slot-shaped tier: it needs credentials, it is slow, it is nondeterministic in a way `just unit` is not, and it will need the same "not a result" discipline the Arma tier already has — a lane that could not be reached is `infra_unavailable`, not a pass.

Three things tier 2 must assert that tier 1 structurally cannot:

- that the lane **loaded** the config at all (an unloaded `.codex/hooks.json` and a passing hook are indistinguishable from the outside — this is the same trap as #80's `schema-stale`, where the probe read as if it had tested a stub);
- that the matcher **fired** (the rulesync casing defect is invisible to any test that invokes the handler directly);
- that a hook's **failure** denies rather than approves, on each lane's own exit-code convention.

A lane's authority is then the set of pairs green at tier 2, recorded per lane, and the honest default for an unproven pair is that the lane may not do the thing that hook guards.

## 7. What this changes for ruling 7

Stated as findings, not as a decision — the choice is the human's.

1. **APM's compile step does not do the job ruling 7 assigned it.** It emits `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` and no hook configuration for any target. If APM is adopted, hooks come from `apm install`, as packages, with a `target:` split per divergence.
2. **APM emits nothing for opencode hooks and is not on a path to.** Its model of the primitive is a merged JSON config file; opencode has none. Its docs record opencode as having no hooks concept, which is no longer true.
3. **"Do not build what already exists" pointed at the wrong tool.** rulesync (MIT, v16.7.0, released 2026-08-04) is the compiler that actually spans both lanes, and it too fails on opencode for our hook shape. Neither tool removes the bridge; APM additionally does not attempt it.
4. **Making `CLAUDE.md` generated costs enforcement rather than buying it.** APM's drift detection does not track it, and the default dedup path can stop regenerating it entirely once `.claude/rules/` exists.
5. **A cheaper decomposition is available.** `AGENTS.md` as the single instruction source with `CLAUDE.md` as `@AGENTS.md` covers instructions across all four non-Claude lanes with no compiler at all; the residue is agent definitions and hooks. Agent definitions are a small, well-understood transform. Hooks are one payload-bridge per lane plus the tier-2 suite in §6 — which the authority rule requires no matter which compiler emits the config.

## What I could not verify

- **Codex was never run.** Every Codex claim is from `https://learn.chatgpt.com/docs/hooks` and its sibling pages. In particular: whether `PreToolUse` inside a Codex subagent carries `agent_id` (§5's highest-risk row), and whether Codex has any read-file tool a `deny-oversized-reads` equivalent could bind to.
- **opencode was never run.** Its claims are from the vendored clone's source and docs. Whether a `throw` from `tool.execute.before` surfaces a useful reason to the model, rather than an opaque tool failure, is untested.
- **agentsmesh's opencode hook output format** — claimed "Partial", format unspecified, not inspected.
- **APM's `--global` and user-scope paths** were not exercised; only project scope.
