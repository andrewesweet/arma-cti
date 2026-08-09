# Dissolving the keep-on-Claude class list: gate obstacles, competence obstacles, and the third kind

**Researched**: 2026-08-09
**Question** (#262, commissioned by the human on 2026-08-06 in the guided decision session, against the class rule ruled the same day on #258): separate the obstacles that keep work on Claude into the ones a gate dissolves and the ones only model-competence evidence dissolves, answer E1 outright, and design each remaining experiment well enough to file as its own issue.

**Answer in one line**: the split is real but **incomplete — there are three kinds, not two**, and the third is *permission*: what a dispatched session may **execute** and **write**, which is neither a gate question nor a competence one and which currently blocks E1's own measurement, E6's foreign corpus run, and every landing under `.claude/`. On the two-kind question the issue asked: **class 7 dissolves** — a non-session read of the Anthropic plan meter already exists in this repository at `tools/breaker.py:689`, hits a hard-coded `api.anthropic.com` URL rather than `ANTHROPIC_BASE_URL`, and therefore cannot be affected by a base-URL redirect at all. And the programme is **cheap in the currency that binds**: the whole nine-experiment series costs on the order of **2 seven-day points** of Claude plan cap, about 2% of one week. Quota is not what is stopping this; permission and wall-clock are.

---

## 0. Method, evidence grades, and what this session could not do

**Seat and route.** Written on `claude-native` at `opus/high`, implementer seat. This issue is **class 3 by its own classification** (it reasons about the class rule) and additionally class 6 (the routing policy is the artefact it would touch). It was **not** drafted under the time-boxed draft-foreign widening ruled on #258, which #262 asks to be declared either way. That widening expires 2026-08-10T14:00Z and was not used.

**Evidence grades**, used per claim throughout, following `docs/research/multi-provider-routing-substrates.md` §0:

- **[read]** — the file, line, or issue body was read this session and the quotation is verbatim from it.
- **[observed]** — something happened in this session and is reported as it happened, including refusals.
- **[inferred]** — a conclusion drawn from the above. Reasoning, not fact.
- **[proposal]** — a recommendation for the human. Nothing here is ruled.

**What was not done, and why it matters to criterion 2.** The issue asks for "a recorded observation of the statusline payload under a redirected base URL". **This session could not make that observation**, and the reason is itself a finding of §3. Concretely, in this session:

| Attempt | Result |
|---|---|
| `Read` of `~/.arma-cti/quota/statusline.jsonl` | *"Claude requested permissions to read from … but you haven't granted it yet"* |
| `tail -c 3000 ~/.arma-cti/quota/statusline.jsonl` | *"For security, Claude Code may only read the end of files from the allowed working directories for this session"* |
| `grep …` (unescaped) on a repository file | *"This command requires approval"* |
| `python3 -c …` | *"This command requires approval"* |

All four are [observed]. `\grep`, `cat`, `ls`, `head` and `git log` were available; the spool file lives outside every worktree by design (`docs/telemetry-ledger.md`, and CLAUDE.md's "Evidence lands in `~/.arma-cti/dispatches/<id>/`, outside every worktree"), and a dispatched session cannot read outside its worktree. So **the evidence path for E1 is outside the reach of the seat E1 was dispatched to.** §2.5 gives the single command that closes the residual and names who can run it.

That is not a reason to leave E1 unanswered. The question E1 asks is decidable from source, and §2 decides it.

---

## 1. Three kinds of obstacle, not two

### 1.1 The issue's two

**Gate-coverage obstacles.** No mechanical gate reads the surface, so a wrong answer from any lane lands green. Dissolved by *building the gate*. No model-equivalence question arises. Classes 4, 5, 6, and the data half of 1.

**Competence obstacles.** The judgement is un-gateable in principle — wording that means what was ruled, a routing verdict, a retro amendment. Dissolved only by evidence that a candidate is equivalently competent at *this project's* judgement. Classes 2, 3, and the prose half of 1.

Both stand. Nothing below overturns them.

### 1.2 The third: permission obstacles

**A permission obstacle is one where the destination lane is the only lane the routing policy permits, and that lane cannot execute or write the work.** It is not about gates — the gate may exist and be perfect. It is not about competence — the model may be fully capable. It is about what the *harness* around the seat will let the seat do.

Three issues this week are permission obstacles, and none of them is expressible in the current class list:

- **#281** [read] — a mutation-engine prototype, correctly Claude-only under class 6 (`tools/mutation_smoke.py` is in `gates_themselves`'s path list; "a foreign lane must not author the gate that judges it"). The Claude lane then could not run it: the comparison needs `uv`, `just --list` and `python3 -c`, none of which are in a dispatched session's command vocabulary. Undispatchable in both directions until one narrow recipe — `just mutation-compare` — was allowlisted (`2bd3e8f`, "build: allowlist just mutation-compare for the #281 prototype") [read].
- **#264** [read] — the `AGENTS.md` symlink. The close records: *"The dispatched session could not create a symlink by any spelling — `ln -s`, `/usr/bin/ln -s`, `bash -c`, `python3 -c os.symlink`, `uv run python`, `perl -e symlink`, `git mv` — while plain `mv` was **allowed**. Its probe against an ungated destination (`zz-probe-link`) was refused identically, which proves the denial is **command-level, not path-level**."* The ruling's rename half was reachable from a dispatched session and its symlink half was not.
- **#294** [read] — no dispatched session on any lane can write under `.claude/`, by **two different mechanisms**: `.claude/hooks/` refuses as *"a sensitive file"* (a harness classification above the project allowlist), while `.claude/skills/` refuses as an ordinary permission ask *despite* `Write(.claude/skills/**)` being granted. Cost to date: five pieces of human-approved work done by the orchestrator's own hands (#274, #285, #279, #273's three hook patches, #265's first probe).

This session adds a fourth instance, on the analysis issue itself [observed]: the `.claude/settings.json` allowlist this worktree runs under grants `Edit(docs/**)`, `Edit(AGENTS.md)`, `Edit(CLAUDE.md)`, `Edit(CONTEXT.md)`, `Edit(CHANGELOG.md)`, `Edit(.claude/skills/**)` and eleven `Bash` verbs — and **no grant for `.claude/agents/` or `.claude/settings.json`**, which are two of the four paths E8 exists to turn into golden-file data. E8's own landing is a permission obstacle before it is anything else.

### 1.3 Why the third kind needs its own name rather than a footnote

The two-kind split is a claim about *why a wrong answer would not be caught*. The third kind is a claim about *whether an answer can be produced at all*. They dissolve by opposite means: a gate obstacle is dissolved by adding machinery, a permission obstacle by removing a restriction or by routing around it with a narrow grant (`just discard`, `just mutation-compare` — the shape approved twice, per #294's scope note).

They also fail differently, and this is the operational reason to separate them. A gate obstacle that is wrong lands bad code. A permission obstacle that is wrong **costs a whole dispatch to discover**, because nothing in `tools/routing_policy.py` checks whether a destination lane can run what it is sent — the module's own docstring says it "decides whether a class may leave Claude under ADR-0061 and #258" [read], and capability is not in `Rule`'s fields (`issue_path_prefixes`, `issue_phrases`, `seats`, `landing_path_prefixes`, `remedy`) [read]. #294 states the same consequence independently: *"nothing in the routing policy checks whether a destination lane can run the work it is sent."*

### 1.4 The class list, re-assigned

| # | Class | Issue's kind | **Revised kind** | Status after this analysis |
|---|---|---|---|---|
| 1 | Gated semantic surfaces | Both | **Gate + competence + permission** | Data half is E8; prose half is E3/E4; **and the landing is blocked by #294 whatever the evidence says** |
| 2 | Orchestration | Competence | Competence | E5, needs E3 |
| 3 | Retros and ADR authorship | Competence | Competence | E4 |
| 4 | The #181 shape | Gate | Gate | E9; may already be mostly gated by ADR-0064 |
| 5 | In-world landings | Gate | **Gate + permission** | E6; #235 landed the first half, but a dispatched session is *denied* the unfiltered corpus by `.claude/hooks/deny-subagent-waits.py` |
| 6 | The gates themselves | Gate | Gate | E7 |
| 7 | The Anthropic plan meter | Access | **Dissolved** | §2 |

Two rows changed kind, and both changes have a consequence for sequencing:

- **Class 5 is not purely a gate obstacle.** `deny-subagent-waits.py` holds exactly one entry on its denial list, and it is *"the unfiltered full regression corpus, in both its spellings (`just regress` and the `spike/regress.sh` it wraps)"* [read, `.claude/hooks/deny-subagent-waits.py` lines 35–36]. A dispatched session on any lane — Claude included — is denied the run E6 wants a foreign lane to perform. Building the SHA-bound landing check does not by itself make a foreign corpus run possible; the corpus must be reached by the detached path CLAUDE.md's working-style rule sanctions, or by the `just dispatch --lane claude-native` session fallback. **E6's design must name which, and it is a design choice the current issue text does not make.**
- **Class 1's data half cannot land where it is aimed.** E8's golden file is cheap; landing a test that reads `.claude/agents/` and `.claude/settings.json` is fine (the *test* lives in `tests/`), but any later *amendment* to those files stays the orchestrator's hands until #294 is resolved. E8 therefore converts class 1's data half from "un-gated" to "gated but orchestrator-landed" — a real gain, but a smaller one than the issue's table implies.

---

## 2. E1, answered

### 2.1 There are two feeds, and the issue's framing conflates them

`tools/quota_tap.sh` sits ahead of the human's configured status line, spools the payload, and runs the original command with the same payload on its stdin [read]. Its header states both load-bearing properties: *"stdout is never touched"* and *"the tap fails open"*. It then does two separate things with the payload:

1. **The status-line feed.** `reading_from_status_line` parses Claude Code's status-line stdin document. Its docstring [read, `tools/breaker.py:731`]: *"`rate_limits` appears on Pro/Max only and only after the first API response of a session, and each of the two windows is independently optional."*
2. **The endpoint feed.** In the background, single-flighted under `flock -n`, the tap runs `breaker.py … tap --lane claude-native --oauth-usage`, which calls `refresh_claude_usage` → `query_claude_usage`.

The issue's E1 note describes both as *"session-local injections rather than an API"*. **That is correct for feed 1 and wrong for feed 2.**

### 2.2 The endpoint feed cannot be affected by a base-URL redirect

Three facts from source, all [read]:

```
tools/breaker.py:437   CLAUDE_USAGE_URL: Final = "https://api.anthropic.com/api/oauth/usage"
tools/breaker.py:439   DEFAULT_CLAUDE_CREDENTIALS: Final = Path.home() / ".claude" / ".credentials.json"
tools/breaker.py:698   request = urllib.request.Request(
                           CLAUDE_USAGE_URL,
                           headers={"Authorization": f"Bearer {token}",
                                    "anthropic-beta": "oauth-2025-04-20"},
                       )
```

The URL is a module constant. `ANTHROPIC_BASE_URL` appears nowhere in the request. The credential is `claudeAiOauth.accessToken` read from `~/.claude/.credentials.json` by `_claude_oauth_token`, whose docstring is *"Read Claude Code's OAuth token without ever putting it in output or on argv"* [read, line 665]. The whole call is `urllib.request.urlopen` against a fixed host with a bearer token off disk.

**Therefore**: the plan meter's primary feed is readable by any process on this box that can read the credentials file and reach `api.anthropic.com`. It needs no Claude Code session, no status line, and no particular value of `ANTHROPIC_BASE_URL`. A session redirected to z.ai reads the Anthropic meter exactly as well as one that is not, because the read does not go through the session at all. [inferred, from the three reads above — the inference is only that a constant URL is unaffected by an environment variable it does not consult.]

The parsed shape is vendored at `tests/fixtures/claude-usage-poll.json` [read]: `limits[]` entries carrying `kind` (`session`, `weekly_all`, `weekly_scoped`), `percent`, `severity`, `resets_at`, `scope.model.display_name`, and `is_active` — the last being how `reading_from_claude_usage` "select[s] the limit the provider marks as binding" [read, line 625].

### 2.3 The status-line feed under redirect

[inferred, not observed] `rate_limits` arrives *"only after the first API response of a session"* [read]. Under a redirected base URL every API response in that session comes from the foreign provider, which has no reason to emit Anthropic's `rate_limits` block. The expected behaviour is therefore that the status-line half reports the typed absence `rate_limits_absent` or `rate_limits_empty` — which `reading_from_status_line` already models as *"the feed said nothing — never a zero"* [read, lines 736–737].

**This does not matter to class 7.** `refresh_claude_usage` uses the status-line document only as `fallback`, and only when the endpoint reading is unavailable [read, lines 1426–1429]. The base-URL-independent feed is the primary; the session-local one is the backstop.

### 2.4 Verdict on class 7

**Class 7 dissolves, on the access question as posed.** [inferred from §2.2]

- *Does a non-session read of the plan meter exist?* **Yes**, and this repository already implements it.
- *Does it survive a base-URL redirect?* **The question does not arise for the read that matters.** The primary feed never consults the redirect.
- *Does the status-line payload survive a redirect?* **Almost certainly not**, and it does not need to.

Two residuals, both small and both worth naming rather than hiding:

1. **The reading process must be able to read `~/.claude/.credentials.json`.** That is a *permission* condition, not an access one — §1.2's category, arriving immediately. A dispatched session cannot read that file for the same reason this session could not read the spool. So class 7 becomes: the meter is readable by **the box**, not by **an arbitrary seat**. In practice the reader is the orchestrator or a `just` recipe, both of which run outside the dispatched-session restriction.
2. **Whether a foreign lane *should* read it.** The Consumer Terms question the sweep settled runs the other way — `docs/research/multi-provider-routing-substrates.md` records that reaching an *Anthropic* subscription by non-Anthropic means is what §3 bars, and that `claude-code-router` doing exactly this (*"reading `~/.claude/.credentials.json` and replaying the OAuth token at `api.anthropic.com`"*) is why it was rejected [read]. **Reading the usage endpoint is not inference and consumes no model quota, but it is the same credential and the same host, and the distinction should be ruled rather than assumed.** [proposal] Keep the meter read on the Claude side of the fence: it is one command a week and there is no benefit to moving it.

With residual 2 taken conservatively, the honest statement is: **class 7 is not a technical barrier and never was — it is a one-line policy choice about where a credential is used.** The target the issue set ("class 7 only, and eliminate that too if the meter is readable outside a session") is therefore reachable in principle, and the programme's real end state is "nothing on the list for technical reasons".

### 2.5 The residual observation, and who can make it

One command closes the empirical half. It must be run **outside** a dispatched session — from the orchestrator seat or a human shell — because it reads `~/.claude/.credentials.json` and writes under `~/.arma-cti/`:

```bash
# 1. Baseline: the endpoint feed with no redirect in the environment.
echo '{}' | uv run python tools/breaker.py tap --lane claude-native --oauth-usage
just breaker state --lane claude-native

# 2. The same read with the environment a foreign lane would have.
#    NOTE: this exports nothing into the shell's parent; it is a single-invocation env.
env ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic \
    sh -c "echo '{}' | uv run python tools/breaker.py tap --lane claude-native --oauth-usage"
just breaker state --lane claude-native

# 3. The status-line half, for the record: the newest spooled payload from a
#    redirected session, and whether it carries rate_limits at all.
tail -n 1 ~/.arma-cti/quota/statusline.jsonl | jq '.rate_limits // "absent"'
```

Predicted [inferred]: steps 1 and 2 produce **identical** binding windows and scope. Step 3 prints `"absent"` for a redirected session and a `rate_limits` object for a native one. A disagreement between 1 and 2 would falsify §2.2 and is the only result that reopens class 7.

**CLAUDE.md's `export ANTHROPIC_BASE_URL` prohibition is respected**: step 2 uses `env` for one invocation and exports nothing.

---

## 3. The permission category, and what to do about it

### 3.1 What is established

[read, across #264, #281, #294 and this session] A dispatched Claude Code session's real constraint is **what it may execute**, not what it may edit:

| Surface | State | Evidence |
|---|---|---|
| `.claude/hooks/**` | write refused as a harness-classified "sensitive file", above the project allowlist | #294 |
| `.claude/skills/**` | write refused as an ordinary ask, *despite* a granted `Write(.claude/skills/**)` | #294 |
| `.claude/agents/**`, `.claude/settings.json` | not granted in this worktree's allowlist at all | this session [observed] |
| symlink creation, by every spelling | refused command-level, not path-level | #264 |
| `grep`, `rg`, `find`, `awk`, `wc`, `python3 -c`, `uv run python -c` | refused | #294; `grep` and `python3 -c` re-confirmed this session [observed] |
| `ls`, `cat`, `sed`, `jq`, `tr`, `\grep`, `head` | allowed | #294; `\grep`, `cat`, `head`, `ls` used throughout this session [observed] |
| reads outside the worktree | refused | this session [observed] |
| the unfiltered `just regress` corpus | denied by `.claude/hooks/deny-subagent-waits.py`, one-entry denial list | [read] |

### 3.2 The proposal

[proposal — nothing here is landed; `config/dispatch-routing-policy.json` encodes the human's #258 ruling and is not this issue's to amend.]

**Add a class 8, `dispatched_session_incapable`, and give `Rule` a capability field.** The class list today answers "may this leave Claude?" It should also answer "can the destination run it?" — the two questions have the same consumer (`just dispatch`, `just brief`) and the same cost of being wrong (a burned dispatch).

The minimal shape, matching the existing data-not-branches design of `tools/routing_policy.py`:

```jsonc
{
  "id": 8,
  "name": "dispatched_session_incapable",
  "label": "Beyond a dispatched session's reach",
  "issue_path_prefixes": [".claude/hooks/", ".claude/skills/", ".claude/agents/",
                          ".claude/settings.json"],
  "landing_path_prefixes": [".claude/hooks/", ".claude/skills/", ".claude/agents/",
                            ".claude/settings.json"],
  "issue_phrases": ["Routing-class: orchestrator-hands", "symlink", "ln -s"],
  "seats": ["orchestrator"],
  "remedy": "No dispatched session on any lane can write under `.claude/` or create a symlink (#264, #294). Land from the orchestration seat, or route the change through a narrow `just` recipe on the `just discard` / `just mutation-compare` shape."
}
```

Three properties this deliberately has:

- **It is a seat class, not a lane class.** Unlike classes 1–7 it does not say "keep on Claude"; it says "keep in the orchestrator's hands, on whichever lane". That is a different axis and the field that carries it is `seats`, which already exists.
- **It refuses early rather than late.** `just brief` composes its gate from `tools/admission.py`'s in-world list today; a capability class lets it also say "this cannot be dispatched" before a dispatch is spent.
- **It is falsifiable and self-retiring.** The day #294 establishes that `.claude/skills/**` *is* configurable, the row's path list shrinks by one entry and the diff says so.

**What this is not**: it is not a widening of the dispatched-session command vocabulary. #294's scope note is explicit that widening is the human's decision under #248, and the narrow-recipe pattern is the approved shape.

### 3.3 The consequence for the programme

Two of the nine experiments have a permission prerequisite that must be discharged before, not during:

- **E6** cannot be run by a dispatched session at all while `deny-subagent-waits.py` holds `just regress`. Its design must choose the detached path or the `just dispatch --lane <foreign>` session fallback, and say so.
- **E8** can *build* its golden file from a dispatched seat but cannot *amend* the files it golden-files. Fine for the experiment; it should be stated so that nobody files a follow-up that assumes otherwise.

---

## 4. The decision-replay benchmark: corpus, packets, contamination, scoring

This is E3 and E4's shared substrate. Designing it once and citing it twice is the whole reason it has its own section.

### 4.1 The population

Two artefact families, both of which pair *the inputs a session had* with *the ruling a human actually made*:

- **ADRs** — `docs/adr/`, numbered `0001`–`0065` with `0059` absent (a renumber casualty). Count and dates derive from:
  ```bash
  ls docs/adr | wc -l
  git log --diff-filter=A --date=short --name-only --format=%ad -- docs/adr
  ```
  The second command is the authoritative date source: an ADR's *landing* date, not any date in its text. [read — run this session, modulo `wc`, which a dispatched session cannot run; the listing was read directly.]
- **Retros** — `docs/process-log.md`, one `##` heading per entry. Twenty-seven are retros; six are bootstrap or user-directed amendments and are **excluded**, because a user-directed amendment has no agent-framed option set and so no judgement to replay. Derivation:
  ```bash
  \grep -n "^## " docs/process-log.md          # 33 headings, 2026-07-30 → 2026-08-08
  \grep -c "^## .* — retro" docs/process-log.md # 27
  ```
  [read — the first command was run this session; the counts are from its output.]

Population: **64 ADRs + 27 retros = 91 replayable items**, spanning 2026-07-30 to 2026-08-08.

### 4.2 The scored subset, and why it is not the population

The issue's label-quality requirement is decisive here: *"Where the human chose from options an agent framed, the 'right answer' is partly the agent's framing. Score the ruling, not the framing, and weight the corpus toward items where the human ruled against the recommendation."*

An item where the human ratified the agent's single recommendation carries almost no signal — a candidate agreeing with it has agreed with the framing, not the judgement. **The discriminating items are the ones where the human overrode, amended, or reframed.**

Fifteen such items were identified from artefacts read this session. This list is evidence, not a sample frame — §4.6 says how to complete it to N = 24.

| Item | Date | What the human did that the agent did not propose | Source [read] |
|---|---|---|---|
| #258 class rule | 2026-08-06 | Declined the options put; asked for a class mechanism instead | #262 body |
| #281 mutation engine | 2026-08-08 | *"declined to ratify the bespoke mutation engine without a fair build-on-top comparison"* | #281 body |
| #221 D2 → #264 | 2026-08-05T21:14Z | Confirmed the substance, **changed the mechanism** (symlink, not `@import`) | #264 body |
| #224 admission bar | 2026-08-05T20:00Z | Approved both parts **and added the retry rule** the derivation had not proposed | `tools/admission.py` docstring |
| #242 ruling 1 | 2026-08-06 | Adopted the seat drop *"on the gate argument, not the budget one"* — rejected the offered rationale | `tools/admission.py:1539` |
| #219 verdict reading | 2026-08-05 | *"no fifth seat was ratified"*; the variable was the instruction, not the seat | AGENTS.md |
| #220 verification rule | 2026-08-05 | Re-based a quality rule as a first-order cost rule | AGENTS.md |
| #218 waits | 2026-08-05 | Retired the cache arithmetic; kept the rule on the stall record; added the session fallback | AGENTS.md |
| #201 RTK | 2026-08-05 | Ruled `rtk gain` inadmissible as evidence of cost saved | RTK.md |
| #217 retro allowance | 2026-08-08 | A **self-expiring** allowance with a mechanical reapply instant | AGENTS.md, routing policy |
| #237 context size | 2026-08-06 | Ruled context worth ≤ ~4% of the plan meter — killed the argument, kept the work | #264 body |
| Model roles | 2026-08-04 | Replaced a two-role list with a four-seat `(model, effort)` mapping | AGENTS.md |
| Effort default | 2026-08-05 | Lowered the opus default from xhigh to high; reserved xhigh by named reason | AGENTS.md |
| #47 port range | 2026-08-02 | Set `[2400, 3000)` and the 2302–2306 exclusion by hand | AGENTS.md |
| #117 / ADR-0039 | (ADR-0039) | Banned `setGroupOwner` outside one file, with a mechanical enforcer | AGENTS.md |

### 4.3 Cutting a packet

A packet is the repository and the issue thread **as they stood at the item's own moment**, and nothing after. Runnable today with `git` and `gh` alone — no new tool is needed for the cut, which is why this design does not propose one:

```bash
ITEM=0064; CUT=2026-08-05T00:00:00Z
SHA=$(git rev-list -1 --before="$CUT" origin/main)

# The repository half — by construction cannot contain a forward reference.
mkdir -p packets/$ITEM && git archive "$SHA" \
    docs/adr docs/process-log.md AGENTS.md CONTEXT.md docs/agents \
  | tar -x -C packets/$ITEM

# The thread half — comments must be filtered by date; gh does not do it for you.
gh issue view "$ISSUE" --json body,createdAt,comments \
  --jq '{body, comments: [.comments[] | select(.createdAt < "'"$CUT"'")]}' \
  > packets/$ITEM/thread.json
```

Two properties worth stating because they are easy to lose:

- **The repository half is contamination-proof by construction.** `git archive` at a pre-cut commit cannot contain a document that did not exist. This is why the cut is a git operation rather than a filter over the current tree.
- **The thread half is not**, and is where every real leak will be. `gh` returns all comments; the `select` is the only thing standing between the packet and the answer.

### 4.4 The mechanical contamination check

Per item, a **pre-registered forbidden-token list**, authored *before* the packet is cut, containing the ruling's distinctive nouns, its ADR number, its title slug words, and any phrase the ruling coined:

```bash
# items/0064/forbidden-tokens.txt, one token or phrase per line, e.g.
#   mutation smoke
#   NO_PYTHON_SUBJECT
#   ADR-0064
#   notice the code changing

\grep -rniFf items/$ITEM/forbidden-tokens.txt packets/$ITEM/ \
  && { echo "CONTAMINATED: $ITEM"; exit 1; } \
  || echo "CLEAN: $ITEM"
```

`-F` is load-bearing (tokens are literals, not patterns); `-i` because casing drifts; `-r` because the packet is a tree. **A packet that fails this is discarded, not repaired** — repairing it by hand is how a leak survives.

The check has one honest weakness and it should be written into the item file rather than argued away: it catches *lexical* leaks, not *semantic* ones. A packet that contains an issue comment reasoning toward the ruling in different words passes. The mitigation is that the token list is authored by whoever knows the ruling, and that the scored subset is weighted toward items where the human overrode — in exactly those items, the packet's reasoning points at the *rejected* answer, so a semantic leak actively misleads a candidate rather than helping it.

### 4.5 Scoring, blinding, and who judges

**The candidate never sees the outcome.** It receives the packet and the question in the form the session actually faced.

**Agreement is scored mechanically where it can be.** For items with an enumerable option set — which the fifteen above mostly have, because the framing agent enumerated them — the item file carries the options and the candidate's answer is matched to one. Exact match to the human's choice is agreement. This removes the judge from the majority of the scoring.

**Where it cannot be mechanised**, use the project's existing rule rather than inventing one: *"Two providers over one diff is one review pass with two lenses, not a second pass"* (AGENTS.md). One Claude lens and one foreign lens, both blind to the outcome and to each other, human breaks ties. **The candidate's own family never scores its own arm** — self-preference is the obvious confound and the two-lens rule already prevents it.

**Reasoning soundness is scored separately from agreement**, on a three-point rubric fixed before any observation: `0` — reasoning contradicts a rule in force at the cut date; `1` — sound but does not reach the decisive consideration; `2` — reaches the decisive consideration the human's ruling turned on. Scored by the same two lenses. **A candidate may agree and still score 0**, which is the point of separating them.

### 4.6 How many items, and what the bar is

Pre-registered before any observation, per #224's rule that the one thing pre-registration cannot survive is a number that moves once the numbers are in.

**N = 24 discriminating items** (the fifteen above, plus nine completed by the same override criterion applied across the remaining 76 population items).

**Bar: ≥ 17 of 24 agreements**, plus **no item scoring 0 on soundness**.

The arithmetic, stated so it can be checked: under H₀ *"the candidate is no better than a coin"* (p = 0.5), P(X ≥ 17 | n = 24) ≈ 0.032, so the bar is a one-sided α ≈ 0.03 test. Against a truly 80%-agreeing candidate, P(X ≥ 17 | p = 0.8) ≈ 0.92, so power ≈ 0.92. Sixteen items would give power ≈ 0.79 at the same α, which is the cheaper design if 24 packets prove too slow — **it is not the default, and swapping to it after seeing any result is exactly the move pre-registration forbids.**

H₀ at p = 0.5 is **conservative**: most items have more than two live options, so a chance-level candidate scores well below 0.5. A candidate that clears this bar has cleared a harder test than the arithmetic claims.

**The asymmetry the human ruled on #262 governs the read-out**: clearing is a strong pass and needs no Claude arm, because the candidate beat a session that had live tools and human dialogue. Failing is inconclusive. **Only on failure**, spend one Claude arm at `opus/high` over a 6–8 item subset, purely to detect gross packet loss — a Claude arm that also fails says the packets are lossy; one that clears says the candidate is the difference. **Never run the effort ladder.**

---

## 5. Per-experiment designs

Each is written to the standard criterion 3 sets: an implementer should be able to file the issue from this section without a further design turn.

### E3 — Decision-replay benchmark, judgement arm

**Dissolves**: 2, 3, and class 1's prose half (jointly with E4).
**Prerequisites**: §4 in full; E2 (hook parity) for any lane whose result is to be trusted.
**What is measured**: agreement with the human's real ruling on 24 blind, date-cut, contamination-checked items, plus a separate three-point reasoning-soundness score.
**Pass bar**: ≥ 17/24 agreements **and** no soundness `0`. Pre-registered; immutable once the first item is scored.
**Evidence that closes it**: the 24 item files with their forbidden-token lists; the packet directories with a `CLEAN` line each; per-candidate answer files; the two-lens score sheets; the tally against the bar. A Claude arm's results **only** if the bar was missed.
**Refusals that are not results**: a packet that fails the contamination check is discarded and re-cut, not scored. A candidate run that hits `quota_exhausted` or `provider_refused` is not a failed item.
**Scope note**: designing and running this is class 1 and class 3 work by the project's own rule. The programme's design cannot leave Claude until the programme succeeds. That is unavoidable and is stated rather than worked around.

### E4 — Decision-replay benchmark, authorship arm

**Dissolves**: class 1's prose half and class 3.
**Prerequisites**: §4; can share packets with E3 but **must not share items scored in the same run** — a candidate that saw the item as a judgement question has seen the ruling.
**What is measured**: given a ruling already taken (supplied verbatim) and the pre-cut packet, the candidate writes the `AGENTS.md` amendment or the ADR. Two scores: (a) **recovery** — a blind reader, given only the produced text, states what was ruled; agreement with the actual ruling is a pass on that item; (b) **consistency** — does the text contradict a rule in force at the cut date?
**Pass bar**: ≥ 17/24 recoveries **and zero** consistency violations. Zero is right here and 17/24 is not: a rule that contradicts another rule is not a near miss, it is a defect that the project's gates do not catch, which is the entire reason class 1's prose half exists.
**Evidence that closes it**: produced texts, blind readers' recovered rulings, the consistency check per item with the contradicted rule named where one is found, the tally.
**Design note**: the blind reader is a *third* seat — not the candidate, not the scorer of E3. Cheapest honest arrangement is a `cti-recon` seat given only the produced text and the question "what was ruled here?".

### E5 — Orchestration-seat trial on a foreign lane

**Dissolves**: class 2.
**Prerequisites**: E3 cleared by that candidate (an orchestration seat that cannot judge should not be trialled); E2 for that lane; the breaker and ledger already exist.
**What is measured**: ten consecutive dispatch cycles against the five pre-registered criteria already coded at `tools/admission.py:1625` — `freeze_or_reservation`, `non_result_treated_as_result`, `landing_in_window`, `gated_surface_approved`, `no_drafting_slack_transcribed`. Three are tool-checkable, two are hand-asserted, and the tool refuses to render a hand criterion as a tool pass [read].
**Pass bar**: 10/10 clean cycles. The trial fails on any one criterion in any one cycle.
**Evidence that closes it**: `just admission trial-report` at ten cycles, with each cycle's `dispatch_id` and landing SHA.
**The one thing that must be built**: a **new `TRIAL_BAR_ID`**. The existing `cti.admission.orchestration-trial/242` is the *opus/high* trial and the module's own rule is that *"a record added under a different `bar_id` is refused, so amending the criteria means minting a new id, clearing the trial and starting fresh"* [read, `tools/admission.py:1558–1562`]. A foreign-lane orchestration trial is a different object under the same machinery, and minting its id is a human act because it is a pre-registration.
**Permission note**: `TRIAL_GATED_PREFIXES` includes `.claude/skills/` [read], and criterion `gated_surface_approved` reads landings against it. A foreign orchestration seat that cannot write under `.claude/` will pass that criterion vacuously. **State this in the issue** — a criterion passed because the seat could not reach the surface is #41's shape and is not a pass.

### E7 — Seeded-bad and seeded-good diff corpus for gate changes

**Dissolves**: class 6.
**Prerequisites**: none. This is the most independent experiment in the series.
**The self-reference it breaks**: today, a change to `tools/mutation_smoke.py` or `tools/land.py` is judged by the gate it changes. A corpus that **predates the gate change** and whose expected verdicts were fixed **before** it breaks the loop: the changed gate must reproduce every prior verdict.
**What is measured**: over a corpus of N diffs, each with a pre-registered expected verdict, the changed gate's actual verdicts. `tests/fixtures/gate-corpus/` already exists in the tree and is the natural home [read].
**Pass bar**: **100%** reproduction of expected verdicts on the pre-existing corpus, plus the new behaviour demonstrated on at least one new seeded-bad diff the old gate missed. 100% is right because any regression is a gate that got weaker, and a gate that got weaker is precisely what class 6 exists to prevent.
**Corpus composition** (pre-registered, per gate): for each of `just check`, `just unit`, `just mutation`, `just land` — at least 4 seeded-bad diffs the gate must red, at least 4 seeded-good diffs it must pass, and at least 2 *near-miss* pairs differing by one line across the red/green boundary. The near-miss pairs are the discriminating ones; without them a corpus of obvious cases passes any gate that is roughly right.
**Evidence that closes it**: the corpus committed with expected verdicts; a runner that replays it; the reproduction table; the new-behaviour demonstration.
**What it does not dissolve**: E7 makes gate changes *foreign-eligible*. It does not make gate **authorship** foreign-eligible, because a corpus written by the same lane that changes the gate is the same self-reference one level up. [proposal] The corpus is authored on Claude once and thereafter is a fixed asset; changes to the corpus itself stay class 6.

### E8 — Settings and seat definitions as golden-file data

**Dissolves**: class 1's data half.
**Prerequisites**: none technically; **#294 for the follow-through** (§3.3).
**What is measured**: whether the *effective* permission grants and seat `(model, effort)` pairs match a checked-in golden file. "Effective" is the whole point: a golden copy of the file's bytes catches nothing a diff does not already catch. The assertion must be over the **parsed, resolved** values — every `allow` entry, normalised and sorted; every `.claude/agents/*.md` frontmatter's model and effort.
**Pass bar**: the test reds on (a) a granted permission removed, (b) a permission widened, (c) a seat's model changed, (d) a seat's effort changed, (e) a seat added or removed. Five reds, one per way it can break — the shape `just check-source-link` already uses (*"Seven tests, one per way it can break"*, #264 close [read]).
**Evidence that closes it**: the golden file; the five red-first tests; `just check` wired.
**What it does not do**: it does not make `.claude/settings.json` or `.claude/agents/` **editable** by a foreign lane or by any dispatched session. It makes an edit *mechanically checked*, which converts the surface from "no gate reads it" to "a gate reads it, and the orchestrator lands it". That is the honest claim and the issue should make it.

### E9 — #181-shape catch-rate against real past defects

**Dissolves**: class 4, or bounds it.
**Prerequisites**: none. ADR-0064's mutation rung already ships.
**The hypothesis under test**: class 4 is much smaller than written, because `tools/mutation_smoke.py` already catches tests that do not notice the code changing — *"which is a substantial part of 'a plausible wrong fix would also have gone green'"* (#262).
**What is measured**: over a set of historical defects (the natural frame is the ~15 issues whose closes record a diagnosis), for each: reconstruct the **plausible wrong fix** — the fix a competent agent would have written from the same symptom — and run it through `just fast` + the mutation rung + a two-lens review. Record whether the wrong fix goes green.
**Pass bar**: this is a **measurement, not a pass/fail**. It reports a catch rate with a denominator. The decision rule pre-registered before the measurement: a residue of **zero** dissolves class 4; a residue of one or more keeps class 4 alive **and the surviving cases become its definition**, replacing today's prose test with a named list.
**Evidence that closes it**: per defect — the real fix, the reconstructed plausible wrong fix, the three verdicts, and the classification. The residue list.
**The methodological trap, and the control for it**: the person reconstructing the wrong fix knows the right one, so every reconstruction is biased toward being obviously wrong. **Control**: the reconstruction is done by a seat given only the symptom and the pre-fix tree — never the fix — and the reconstructions are frozen before any gate is run. Without this control E9 measures the reconstructor, not the gates.

### E6 — restated, because its kind changed

**Dissolves**: class 5, the largest single unblock in the queue (#91, #160, #143, #194, #70, #72).
**Status**: `just verdict --post` **landed** — #235 is closed [read].
**Remaining**: (a) the landing gate binds the posted verdict's SHA to the diff, making forgery a mechanical red; (b) a foreign lane actually runs the corpus.
**The design decision the issue text does not make** (§1.4): a dispatched session on *any* lane is denied `just regress` unfiltered by `.claude/hooks/deny-subagent-waits.py`. So (b) must be either the detached path CLAUDE.md sanctions — commit, arm `just watch`, write a handoff, end the turn — or `just dispatch --lane <foreign>` as a session with the result read from the ledger. **Pick one and write it into the issue**, because an implementer who does not know will discover it as a denial mid-run.
**Pass bar for (a)**: the landing gate reds when the posted verdict's SHA does not equal the diff's base, reds when no verdict is posted for an in-world landing, and passes when they match. Three tests.

---

## 6. Cost, in the measured currency

Per #232's ledger basis and #218's calibration, cost is **percentage points of the binding Claude plan window**, not dollars. The constants, all [read] from `docs/research/token-efficiency-plan-currency.md`:

| Constant | Value | Grade |
|---|---|---|
| One five-hour point | 30,209 output tokens | measured (#218 control) |
| One seven-day point | 181,253 output tokens | measured |
| Output plan weight | 33.10 pp₅ₕ/Mtok · 5.52 pp₇d/Mtok | measured |
| Cache write, either TTL | < 0.0096 pp/Mtok | bounded |
| Per request / per session | 0 | measured |
| A foreign lane's Claude `cap_fraction` | **0** — *"consumes no Anthropic quota"* | read |

**The working unit**, and its provenance: `docs/telemetry-ledger.md` describes one Claude five-hour point as *"30,209 output tokens, several median agent runs"* [read]. Taking "several" as 3–6 gives a median dispatched run of **5,000–10,000 output tokens**. Every figure below uses **10,000** — the conservative end. [inferred] Replace with measurement via `just ledger-sync show --dispatch <id>` as soon as any arm of this programme runs.

| # | Experiment | Claude output tokens [inferred] | pp₅ₕ | pp₇d | Where the cost is |
|---|---|---|---|---|---|
| E1 | Plan-meter access | ~2k | 0.07 | 0.01 | Two commands; **already answered analytically** |
| E8 | Golden-file settings/seats | ~20k | 0.7 | 0.11 | 2 implementer dispatches |
| E7 | Seeded gate corpus | ~40k | 1.3 | 0.22 | Corpus authorship must stay Claude (§5, E7) |
| E9 | #181-shape catch rate | ~40k | 1.3 | 0.22 | Reconstruction + 15 gate runs |
| E6 | SHA-bound landing + foreign corpus | ~30k | 1.0 | 0.17 | (a) is Claude; (b) is foreign, **0** Claude points |
| E3 | Replay, judgement arm | ~140k | 4.6 | 0.77 | 24 packets (~30k) + one Claude scoring lens over 24×3 (~110k). Candidate runs are foreign, **0** |
| E4 | Replay, authorship arm | ~110k | 3.6 | 0.61 | Blind readers + consistency checks. Candidate writes are foreign, **0** |
| E5 | Foreign orchestration trial | ~20k | 0.7 | 0.11 | 10 assessment records; the cycles themselves are foreign, **0** |
| E2 | Hook parity | — | — | — | Underway on #225 (closed for z.ai); Codex parity is #273's neighbourhood |
| | **Programme total** | **~400k** | **13.2** | **2.2** | |
| | *Conditional Claude arm* (only if E3 misses its bar) | +80k | +2.6 | +0.44 | 8 items at `opus/high` |

**The headline, and it changes the sequencing argument.** The entire programme costs about **2.2 seven-day points** — roughly **2% of one week's cap** — against a week that has run at 79–89% [read, `tests/fixtures/claude-usage-poll.json`]. **Quota is not the constraint on this programme.** What constrains it is wall-clock (E3 and E4 are 24-item pipelines), the WIP limit of three, and §3's permission obstacles.

**What would falsify the table**: any measured dispatch above ~30k output tokens moves every row proportionally. The `cap_fraction.est` field exists for exactly this and the first real ledger row should replace the inference. Note also the ledger's own recorded weakness: *"The observed half of every `cap_fraction` is missing"* [read, `docs/telemetry-ledger.md:269`], so these are estimator figures and the observed side is integer-resolution and will read 0 per dispatch.

---

## 7. Sequencing

Ordered by leverage over cost and prerequisite, not by experiment number:

1. **E1** — done here; §2.5's three commands are the residual and cost 0.07 points.
2. **#294** — not an experiment, but the permission obstacle gating class 1's follow-through and appearing in E5's criterion 4 as a vacuous pass. Cheapest thing on this list with the widest reach.
3. **E8** — small, independent, immediately converts class 1's data half.
4. **E6(a)** — the SHA-bound landing check. Three tests. Unblocks six queued issues once (b) follows.
5. **E7** — independent, and it is the precondition for ever letting a foreign lane near `tools/`.
6. **E9** — independent; may delete class 4 outright, which is the cheapest possible dissolution.
7. **E3** — the centrepiece, and the expensive one. Everything competence-shaped waits on it.
8. **E4** — shares E3's substrate; run after, on disjoint items.
9. **E5** — needs E3, and needs a new `TRIAL_BAR_ID` minted by the human.

---

## 8. What is measured, what is inferred, what is for the human

**Measured or read from source:**
- `CLAUDE_USAGE_URL` is a module constant naming `api.anthropic.com`; the request never consults `ANTHROPIC_BASE_URL`; the credential comes from `~/.claude/.credentials.json`.
- The status-line `rate_limits` block is documented in-tree as arriving only after a session's first API response, and is the *fallback*, not the primary feed.
- `deny-subagent-waits.py` holds exactly one denial entry: the unfiltered regression corpus, in both spellings.
- The five orchestration-trial criteria, the immutable-`bar_id` rule, and `TRIAL_GATED_PREFIXES` including `.claude/skills/`.
- The plan-currency constants and the zero-Claude-cost property of a foreign lane.
- This session's own refusals: reads outside the worktree, `grep`, `python3 -c`; and the absence of any `.claude/agents/` or `.claude/settings.json` grant in this worktree's allowlist.

**Inferred, and flagged as reasoning:**
- That the status-line half goes silent under a redirect (from the "first API response of a session" docstring). Not observed.
- That a constant URL is unaffected by an environment variable it does not read. Trivial, but it is the load-bearing step in dissolving class 7 and should be confirmed by §2.5.
- Every cost figure, from a "several median agent runs" phrase rather than a ledger row.
- N = 24 and the 17/24 bar. The arithmetic is exact; the choice of 0.5 as H₀ and 0.8 as the alternative is a design decision.

**For the human to rule on:**

1. **Class 7's residual is a policy question, not a technical one.** The plan-meter read uses the Anthropic OAuth credential against `api.anthropic.com`. The sweep rejected `claude-code-router` for doing exactly that for *inference*; a usage read is not inference and consumes no quota, but it is the same credential and host. Recommendation: keep the meter read on the Claude side. It costs one command a week.
2. **Whether to add class 8 (§3.2)**, giving the routing policy a capability axis so a permission obstacle refuses before a dispatch is spent rather than after.
3. **Minting `TRIAL_BAR_ID` for a foreign orchestration trial** (E5). A pre-registration is a human act by the module's own design.
4. **E5's vacuous-pass problem**: a foreign orchestration seat that cannot write under `.claude/` passes `gated_surface_approved` by being unable to fail it. Whether the trial should be run at all before #294 resolves.
5. **N = 24 versus N = 16** for the replay corpus (§4.6). Both are stated with their power; picking after seeing any result is barred.

---

## 9. Sources

All repository paths are as of this worktree's base, `576eead`, on `origin/main`.

- `config/dispatch-routing-policy.json`, `tools/routing_policy.py` — the class list as ruled on #258 and its reader.
- `tools/breaker.py` — `CLAUDE_USAGE_URL` (437), `DEFAULT_CLAUDE_CREDENTIALS` (439), `_claude_oauth_token` (665), `query_claude_usage` (689), `reading_from_status_line` (731), `refresh_claude_usage` (1408), `run_tap` (1852).
- `tools/quota_tap.sh` — the tap, its fail-open and stdout-untouched properties.
- `tools/admission.py` — Part A (213), the bar's docstring (1–120), the orchestration trial (1537–1653).
- `.claude/hooks/deny-subagent-waits.py` — the one-entry denial list (35–36), `THRESHOLD` (119).
- `tests/fixtures/claude-usage-poll.json` — the endpoint's parsed shape.
- `docs/research/token-efficiency-plan-currency.md` — the plan-currency constants; the foreign-lane zero.
- `docs/telemetry-ledger.md` — `cap_fraction`, the estimator, the missing observed half.
- `docs/research/multi-provider-routing-substrates.md` — the Consumer Terms finding on credential replay.
- `docs/process-log.md`, `docs/adr/` — the replay population.
- GitHub issues #225, #235, #258, #262, #264, #273, #281, #294 — read this session.
