# Removing backlog routing restrictions: authorship and execution are different questions

- Issue: [#296](https://github.com/andrewesweet/arma-cti/issues/296)
- Base: `8fa98f7`
- Lane/profile/seat: `codex` / `codex-sol-xhigh` / `implementer`

## Answer

**Keep `6:gates_themselves` closed. Split class 1, and make class 5 executable.**

The top-30 measurement reproduces exactly: 12 issues are foreign-eligible, 14 first match
`gated_semantic_surfaces`, three first match `in_world_landings`, and one first matches
`gates_themselves`. But the 18 refusals are not 18 instances of one safety property. The policy
currently answers two questions through one first-match list:

1. **May this lane author the work?** This is where semantic competence and independent judging
   belong.
2. **Can the assigned executor perform every required step?** This is where `.claude/` writes,
   `just regress`, and this Codex lane's inability to run `just fast` belong.

Those questions need separate axes. A permission failure is not evidence that Claude must reason
about the work, and a foreign author does not need direct landing authority when a mechanically
specified finisher can perform the remaining step. Conversely, a capable executor is not thereby
qualified to invent policy or alter its own judge.

This report was written by the Codex lane whose eligible workload would grow under parts of the
proposal. That conflict is real. The recommendation against this lane's interest comes first:

- A foreign lane must not author routing policy, admission logic, mutation floors, landing logic,
  or the oracle that judges changes to those gates.
- The `proposal-only` exception is sound because this report cannot change any of them. It is not
  evidence for foreign gate authorship.
- This Codex profile can commit but cannot run `just fast` because `cog check` cannot discover the
  linked repository under its sandbox. Nothing proposed here grants it gate or landing authority.
  [Sources: `config/dispatch-routing-policy.json`; `docs/research/codex-lane-live-findings.md` §10;
  ADR-0061 decisions 2 and 4.]

No policy or routing implementation is changed by this report. The exact policy text proposed for
the human's gate is in §7.

## 1. Method and one correction

The frozen population is the 30 issue numbers in #296, not today's moving queue. I fetched each
issue body and passed it directly to `routing_policy.advisory_match` for a
`zai`/`zai-glm52-max`/`implementer` route at the 2026-08-09 policy clock. That independently
reproduced the issue's table:

| First verdict | Count | Share of blocked | Issues |
|---|---:|---:|---|
| Foreign-eligible | 12 | — | 293, 292, 291, 290, 289, 288, 284, 212, 208, 202, 194, 170 |
| `1:gated_semantic_surfaces` | 14 | 77.8% | 294, 258, 247, 229, 211, 209, 203, 195, 189, 187, 186, 183, 179, 177 |
| `5:in_world_landings` | 3 | 16.7% | 160, 146, 143 |
| `6:gates_themselves` | 1 | 5.6% | 234 |

The count is right. The method note's explanation of the first failed scan is not. On this base,
and already in the original policy commit `70ffe58`, `tools/dispatch.py` calls
`routing_refusal` at lines 1416–1418 and checks `worktree_missing` later at lines 1450–1463. A
`worktree_missing` result therefore means the request cleared the earlier routing rung, assuming
the earlier readiness and queue rungs also cleared. It is not evidence of ineligibility.

The durable method rule is still correct, stated more narrowly:

> A non-routing refusal is not a routing classification. For a census, classify issue bodies
> directly and record every matching restriction.

The last clause matters because `advisory_match` returns the first match, not all matches
(`tools/routing_policy.py:238-246`). The first-verdict table hides that #258 matches classes 1, 3,
and 4; #229 matches 1 and 6; and #189 matches 1 and 5. It measures the current dispatch answer,
not all reasons an issue may be blocked.

## 2. What the class-1 pile actually contains

The human's #258 ruling says the bar falls on **authorship, not path**. The implementation cannot
observe authorship. `issue_match` scans the entire issue body for any configured phrase or path
substring (`tools/routing_policy.py:200-210`), then the policy returns the first matching row. A
path cited as a source is indistinguishable from a path the issue will edit.

The 14 issues make the conflation visible:

| Issue | Why class 1 matched | Underlying restriction | Routing consequence |
|---|---|---|---|
| #294 | `.claude/skills/`, `.claude/hooks/` | **Permission** | Research may leave; direct `.claude/` execution cannot. |
| #258 | `CLAUDE.md`, `.claude/agents/` | **Competence/human authority**, plus incidental citations | The human's routing ruling stays human; the path match is not the reason. |
| #247 | `.claude/hooks/` | **Independent judging + permission** | Hook-guard authorship stays closed; a ruled patch may use a narrow promotion path. |
| #229 | `CLAUDE.md`, `.claude/settings.json` | **Human authority** | Subscription, key, terms, sudo, and sign-off acts are not dispatch work. |
| #211 | `CLAUDE.md` | **Semantic authorship** | Keep closed pending the authorship benchmark. |
| #209 | `CLAUDE.md` cited as an inventory source | **None for the research deliverable** | The study may leave; gated follow-ups are classified when filed. |
| #203 | docs and hooks named as research subjects | **Mixed** | Split cited study from any adopted gated mechanism. |
| #195 | `CLAUDE.md` named as a candidate input | **None for the report** | The assessment may leave. |
| #189 | `CONTEXT.md`, explicitly saying **do not edit it** | **Tooling/class 5** | Class 1 is a false reason; the in-world landing still owes the corpus. |
| #187 | `CONTEXT.md` named only as a complexity measure | **None for the prototype** | The offline prototype may leave; the later structural decision may not. |
| #186 | gated surfaces are data the new checker reads | **Independent judging** | It authors a gate and belongs with class 6, not semantic prose. |
| #183 | `.claude/settings.json` | **Independent judging + permission** | It changes enforcement wiring; keep authorship closed. |
| #179 | `CLAUDE.md` cited for a failure-class rule | **Tooling and human judgement** | Capture engineering may leave once executable; deciding how pixels earn a verdict may not. |
| #177 | `CONTEXT.md` and an ADR are outputs | **Semantic authorship** | Keep closed. |

This is not a claim that eight more issues should immediately dispatch. #229 contains only human
acts; #258 carries human policy authority; #189 remains class 5; #203 is deliberately mixed. It
is a claim that class 1 is giving the wrong reason often enough that exception-by-exception growth
is now design debt. `pure-transcription` and `no-gated-landing` were both added within two days of
the class rule, and `proposal-only` demonstrates the same authorship-versus-reference distinction
for class 6. [Sources: #258 ruling comment `5208222457`; policy issue exceptions at
`config/dispatch-routing-policy.json:160-182`; #296.]

### Class-1 hypothesis

Class 1 contains three real obstacles and one classifier error:

- **Competence:** invented normative wording and domain/schema semantics have no complete
  mechanical oracle.
- **Independent judging:** some listed paths are enforcement, not prose. A foreign lane must not
  author its judge merely because the file also contains text.
- **Permission:** `.claude/` can be unreachable even after wording has been ruled.
- **Reference noise:** an arbitrary mention of a path says nothing about the planned diff.

The first should remain closed until competence evidence exists. The second belongs in class 6.
The third belongs on an executor-capability axis. The fourth should disappear by parsing a small
routing declaration rather than arbitrary prose.

## 3. The permission wall is not a keep-on-Claude class

#294 records two different `.claude/` refusals and a narrower-than-briefed command vocabulary.
#264 and #281 reached the same boundary through symlink creation and the mutation comparison.
These are observations about the harness around a dispatched session, not about its model.

The current policy cannot express that distinction:

- `Rule` has paths, phrases, seats, and a remedy, but no required capability
  (`tools/routing_policy.py:28-38`).
- `Rule.seats` means “refuse when this requested seat matches” (`issue_match`, lines 200–204). It
  does not mean “this seat is an allowed executor.”
- `advisory_match` clears every `claude-native` route before examining a rule (lines 238–241), yet
  #294 shows that a dispatched Claude session can hit the same `.claude/` wall.

Therefore the class-8 proposal in `docs/research/dissolving-the-claude-class-list.md` §3.2 should
**not** be implemented as written. A current-shaped row with `seats: ["orchestrator"]` would block
the orchestrator seat on a foreign lane; it would not require orchestrator hands, and it would say
nothing to a `claude-native` dispatch.

The replacement is a required-executor model. An issue declares operations, not a preferred lane:
`write-dot-claude`, `create-symlink`, `run-full-regress`, `run-just-fast`. Routing then composes a
workflow whose author, long-run executor, finisher, and lander may differ. Unknown capability fails
closed before a dispatch is spent. A narrow recipe may satisfy one operation without widening the
session's general command vocabulary; that is the already approved `just discard` and
`just mutation-compare` shape, not an override.

This matters particularly to the lane writing this report. Codex can author and commit ordinary
work, but it cannot run `just fast`. Recording `run-just-fast` as unsatisfied would route its
finisher elsewhere rather than pretending Codex has authority it does not.

### Permission experiment P1: capability matrix

**Hypothesis:** `.claude/` writes and selected commands fail by deterministic executor capability,
independent of whether the model could perform the task.

Pre-register before the next observation:

- Arms: each dispatchable `(lane, profile, seat)` route, plus orchestrator hands as the control.
- Two fresh sessions per arm, so an inherited approval or first-session cache cannot create a pass.
- Operations: edit a pre-created sentinel under each of `.claude/hooks/`, `.claude/skills/`,
  `.claude/agents/`, and a non-`.claude/` control; create a symlink; invoke `just fast`; invoke a
  harmless narrow recipe. An outside probe driver snapshots and restores those exact sacrificial
  paths after every arm, so a partial capability cannot leave a foreign edit behind.
- Record each operation as `available`, `permission_refused`, `harness_refused`, or
  `tooling_failed`. An approval prompt is a refusal in an unattended dispatch.

**Bar:** a capability is advertised only when both fresh sessions complete the exact operation
without a prompt and leave the tree clean. One refusal marks it unavailable. No percentage or
majority vote is involved: permissions are deterministic configuration.

**Falsifier:** any operation recorded available by the preflight but refused in the next real
dispatch makes the preflight untrusted and fail-closed until its environment derivation is fixed.

### Permission experiment P2: narrow promotion

**Hypothesis:** a foreign lane can author a ruled `.claude/` patch outside the protected tree and a
human-approved recipe can promote those exact bytes without granting arbitrary `.claude/` writes.

Build the recipe only after human approval. Before any live use, require four fixture verdicts:

1. an approved patch with an exact preimage hash and allowed target applies;
2. changed bytes refuse;
3. a path outside the one approved target refuses;
4. a stale preimage refuses.

Then use it once on an already approved real change. **Pass bar:** 4/4 fixture verdicts, the one
live patch byte-identical to the approved artifact, the ordinary gates green, and no new general
command or path grant. Any mismatch keeps orchestrator typing as the honest route. This experiment
removes a permission cost; it does not qualify a foreign lane to invent the patch.

## 4. Class 5 is mostly a tooling and lifecycle gap

The #258 ruling calls class 5 contingent: it dissolves when a dispatched session may run the full
corpus. The policy remedy says the same (`config/dispatch-routing-policy.json:82-112`). No source
attributes the restriction to foreign-model competence.

The missing operation has two parts:

- **Permission:** the full `just regress` invocation is not in the dispatched command surface.
- **Lifecycle:** the unfiltered corpus is a known-long operation. The wait hook deliberately denies
  holding it inside a subagent turn; its measured runs are all longer than the five-minute
  threshold (`.claude/hooks/deny-subagent-waits.py`, header and known-long list).

A foreground allowlist entry alone would therefore encode the wrong workflow. The narrow shape is
a detached, SHA-bound full-corpus runner: start it for the committed candidate, return its run id,
end the authoring turn, and let the watcher wake a permitted finisher. `just verdict --post` already
publishes the finished evidence verbatim; what is missing is binding that evidence to the landing
and allowing a foreign-authored candidate to start the run. [Source: #235 and
`docs/research/dissolving-the-claude-class-list.md` E6.]

Class 5 also has a smaller precision problem. #146 changes glossary words and comments on an
in-world path. A full world run cannot tell whether “buy” should be “Purchase.” That is a missing
lexical gate, not a need for Arma. By contrast #143, #160, and #189 change world behavior and do
owe the corpus. Path is a safe enforcing fallback, but the issue advisory should declare the
behavior and evidence it expects rather than infer both from a cited path.

### Class-5 experiment W1: detached, bound corpus

**Hypothesis:** once a narrow runner and landing binder exist, in-world work is foreign-authorable
without weakening the corpus rule.

The implementation issue must pre-register these five gate cases before code is run:

1. missing corpus verdict: landing refuses;
2. red corpus verdict: landing refuses;
3. green verdict for a different SHA: landing refuses;
4. a filtered or named-probe verdict: landing refuses;
5. a green, unfiltered verdict for the exact candidate SHA: landing may continue.

The runner accepts an issue id and exact committed SHA, no shell string and no probe selector. It
records the unfiltered command, SHA, run id, and evidence directory before returning. A dirty tree,
unresolvable SHA, occupied tier, permission denial, or unfinished run is not a result.

After the five fixture cases are green, run three consecutive real foreign-authored in-world
issues through it. Code reds are ordinary results to fix and do not fail the experiment. **Pass
bar:** 5/5 binder cases, 3/3 final candidate SHAs with a completed unfiltered green corpus, zero
manual repair of the run metadata, and zero permission or untyped-harness refusals. The bar is
fixed before the first real route, per #224.

Clearing W1 removes the class-5 **authorship** restriction. It does not give this Codex profile
direct landing authority: its separate `run-just-fast` capability remains absent until #265's
sandbox ceiling moves.

### Class-5 experiment W2: lexical subset

**Hypothesis:** non-behavioral glossary replacements on in-world paths can be judged without a
world run when a checker owns the exact forbidden/required vocabulary.

Build a checker over the user-facing strings and comments that the glossary governs. Pre-register
four fixtures: forbidden user-facing term, forbidden comment term, allowed metaphorical use, and
correct replacement. **Pass bar:** 4/4 verdicts and one real sweep with no behavioral diff, as
proved by an AST/token-aware or equally bounded mechanism rather than an agent's assertion. Until
such a gate exists, #146 remains conservatively class 5 even though the corpus is the wrong oracle.

## 5. Class 6 should survive

Class 6 is a judging restriction, not a competence estimate. Its core statement is exact: **a
foreign lane must not author the mechanism that judges it**. A better model, more tests, permission
parity, or ten clean ordinary implementations does not remove that conflict.

The current class is imperfectly enumerated. #186 authors a new check and #183/#247 change hook
enforcement, yet first-match classification puts them in class 1. Conversely #234 first matches
class 6 merely because its body cites the admission bar while proposing a new provider. The
declaration-only advisory scan in §6 should fix both directions. The actual landing-path gate stays
fail-closed.

`Routing-exception: proposal-only` is the right narrow exception:

- it is visible in the issue body and excepts only class 6;
- it permits analysis whose output cannot mutate the judge;
- `proposal-only` plus a class-1 landing still refuses at dispatch;
- issue exceptions do not reach `enforcing_match`, so an actual foreign gate diff still refuses at
  landing (`tools/routing_policy.py:223-257`; `tests/unit/test_routing_policy.py:148-165`).

There is no recommended experiment to move gate or oracle authorship. The seeded-diff corpus in
the earlier E7 design is useful validation, but a corpus visible and editable in the same trust
domain is not an independent judge. At most it could qualify **implementation** of a human/Claude
designed gate if all of these were independently fixed before the candidate run: corpus, expected
verdicts, runner, and new-behavior requirement; pass bar 100% old verdict reproduction plus one new
seeded-bad case the old gate misses. The corpus and its oracle remain class 6. That converts work
at the boundary; it does not dissolve the class.

The other out-of-sample restrictions—classes 2, 3, and 4—are not reopened here. Semantic
authorship remains closed until the 24-item authorship replay in
`docs/research/dissolving-the-claude-class-list.md` E4 clears its pre-registered ≥17/24 recovery
and zero-consistency-violation bar. The #181 shape remains until E9 finds no surviving plausible
wrong fix. Class 7's technical access finding also remains a separate credential-policy ruling.

## 6. Classifier experiment: declarations, all matches, and a shadow period

**Hypothesis:** the path false positives come from scanning arbitrary prose, not from a need for a
broader Claude-only rule.

Replace full-body substring scanning with a small `## Routing declaration` block composed by
`just brief`. It names intended landing paths, authorship kind, and required operations. The
evaluator returns every restriction, not only the first. Ordinary prose remains available as
evidence but cannot itself declare scope.

Pre-register this evaluation before implementing it:

- Frozen corpus: the 30 issues in #296, with this report's causal table reviewed by the human or a
  Claude seat before parser results are shown.
- Required discriminators: #189 must lose class 1 and retain class 5; #186 and #183 must name
  independent judging; #209 and #195 must not be blocked by citations; #294 must name an executor
  requirement rather than Claude-only authorship; #234 must distinguish its provider study from a
  future gate diff.
- Shadow corpus: the next ten completed issues. Compare their declared landing paths with the real
  diff and required operations with the recorded commands.

**Pass bar:** 30/30 frozen classifications agree with the reviewed causal labels; then 10/10
shadow issues have no undeclared classified landing path and no undeclared required operation. A
declaration that understates the real diff is a red at landing, not an automatic amendment. One
false clearance retains the current full-body advisory scan while the declaration design is fixed.

This experiment can relax reference-only class-1 refusals. It cannot relax semantic authorship,
permission, class 5's evidence obligation, or class 6.

## 7. Verbatim policy proposal for the human gate

Nothing in this section is landed. This is the exact proposed replacement shape for the routing
policy's matching metadata, class 1, class 5, class 6, and executor requirements. The unchanged
class 2, 3, 4, and 7 objects and the three existing exception objects remain byte-for-byte as they
are. Adopting this text requires a version-2 parser, tests, and the experiments above; pasting it
into today's version-1 file would correctly fail its shape gate.

```json
{
  "version": 2,
  "issue_declaration": {
    "heading": "## Routing declaration",
    "landing_paths_field": "Landing-paths",
    "authorship_field": "Authorship",
    "requirements_field": "Requires",
    "exception_field": "Routing-exception",
    "match_scope": "declaration_only",
    "return_matches": "all_advisory_and_enforcing"
  },
  "replacement_classes": [
    {
      "id": 1,
      "name": "gated_semantic_surfaces",
      "label": "Gated semantic authorship",
      "kind": "competence",
      "issue_path_prefixes": [
        "CLAUDE.md",
        "CONTEXT.md",
        "docs/adr/",
        "tests/specs/",
        ".claude/skills/",
        ".claude/agents/",
        ".claude/settings.json"
      ],
      "issue_phrases": [
        "Authorship: semantic",
        "snapshot schema semantics",
        "project skills"
      ],
      "landing_path_prefixes": [
        "CLAUDE.md",
        "CONTEXT.md",
        "docs/adr/",
        "tests/specs/",
        ".claude/skills/",
        ".claude/agents/",
        ".claude/settings.json"
      ],
      "remedy": "Route invented wording and permission semantics to a Claude seat. Pure transcription is eligible only when the issue declares `Routing-exception: pure-transcription`; a foreign gated-path landing still requires a permitted finisher."
    },
    {
      "id": 5,
      "name": "in_world_landings",
      "label": "In-world behavior requiring the corpus",
      "kind": "gate_and_tooling",
      "issue_path_prefixes": [
        "addons/",
        "missions/",
        "extension/",
        "src/cti_daemon/port.py",
        "src/cti_daemon/outbox.py",
        "src/cti_daemon/commands.py",
        "src/cti_daemon/protocol.py",
        "src/cti_daemon/transport.py",
        "src/cti_daemon/manifest.py"
      ],
      "issue_phrases": [
        "Routing-class: in-world-landings",
        "Requires: run-full-regress"
      ],
      "landing_path_prefixes": [
        "addons/",
        "missions/",
        "extension/",
        "src/cti_daemon/port.py",
        "src/cti_daemon/outbox.py",
        "src/cti_daemon/commands.py",
        "src/cti_daemon/protocol.py",
        "src/cti_daemon/transport.py",
        "src/cti_daemon/manifest.py"
      ],
      "remedy": "Authoring may leave Claude only after the SHA-bound detached-corpus experiment clears. Until then use a Claude seat that can run the full `just regress` corpus."
    },
    {
      "id": 6,
      "name": "gates_themselves",
      "label": "The gates themselves",
      "kind": "independent_judging",
      "issue_path_prefixes": [
        "config/dispatch-routing-policy.json",
        "tools/routing_policy.py",
        "tools/dispatch.py",
        "tools/land.py",
        "tools/mutation_smoke.py",
        "tools/admission.py",
        ".claude/hooks/",
        ".claude/settings.json"
      ],
      "issue_path_globs": [
        "tools/check_*.py"
      ],
      "issue_phrases": [
        "Routing-class: gates-themselves",
        "mutation floors",
        "hook wiring",
        "dispatch permissions",
        "admission bar",
        "Authorship: gate"
      ],
      "landing_path_prefixes": [
        "config/dispatch-routing-policy.json",
        "tools/routing_policy.py",
        "tools/dispatch.py",
        "tools/land.py",
        "tools/mutation_smoke.py",
        "tools/admission.py",
        ".claude/hooks/",
        ".claude/settings.json"
      ],
      "landing_path_globs": [
        "tools/check_*.py"
      ],
      "remedy": "Keep authorship of a judging mechanism and its oracle on Claude. A declared `Routing-exception: proposal-only` may study or propose because it cannot land a change to either."
    }
  ],
  "execution_requirements": [
    {
      "name": "write_dot_claude",
      "kind": "permission",
      "declared_as": "write-dot-claude",
      "satisfied_by": [
        "orchestrator-hands"
      ],
      "remedy": "Route the exact ruled bytes through orchestrator hands or a separately approved narrow promotion recipe."
    },
    {
      "name": "run_full_regress",
      "kind": "tooling",
      "declared_as": "run-full-regress",
      "satisfied_by": [],
      "remedy": "No dispatched executor is trusted for this operation until experiment W1 clears; use a Claude-side corpus run."
    },
    {
      "name": "run_just_fast",
      "kind": "tooling",
      "declared_as": "run-just-fast",
      "known_unavailable_to": [
        "codex/codex-sol-xhigh"
      ],
      "remedy": "Assign a gate-capable finisher; do not treat a Codex commit as a gated result."
    }
  ]
}
```

Two deliberate conservative choices in that text:

1. `run_full_regress.satisfied_by` starts empty. The human should add the detached runner only
   after W1, never on the promise that it will work.
2. Class-1 landing paths remain enforcing. Better advisory precision moves authorship off Claude;
   it does not let a foreign lane assert that its own gated diff was “only a mention.”

There is still no CLI override. Exceptions remain exact, issue-declared, and class-scoped. Actual
diff enforcement remains the last word.

## 8. Decision table

| Restriction | Cause | Recommendation | Evidence needed to move |
|---|---|---|---|
| Class 1, semantic authorship | Competence | **Stay closed** | E4: ≥17/24 recoveries, zero consistency violations. |
| Class 1, reference-only matches | Classifier | **Plausibly relax** | 30/30 reviewed corpus + 10/10 shadow declarations. |
| `.claude/` and command wall | Permission | **Separate axis; route around narrowly** | P1 capability matrix; P2 4/4 fixtures + one exact live promotion. |
| Class 5, behavior changes | Tooling + gate | **Plausibly relax authorship** | W1: 5/5 binder cases + 3/3 real exact-SHA corpus runs. |
| Class 5, lexical-only changes | Missing focused gate | **Stay conservative until gated** | W2: 4/4 fixtures + one bounded real sweep. |
| Class 6, gate/oracle authorship | Independent judging | **Do not move** | No competence or permission experiment can remove self-reference. |
| Class 6, proposal-only analysis | No landing authority | **Existing exception stands** | Current dispatch and landing tests already enforce the boundary. |

The immediate gain is precision, not permission inflation: research and prototypes stop being
blocked for citing the rules they must read; corpus-bound work gets an executable, auditable
handoff; and gate authorship remains where an independent judge exists.

## Sources

- `config/dispatch-routing-policy.json` and `tools/routing_policy.py` — current class data,
  full-body and first-match advisory behavior, exception scope, and landing matching.
- `tools/dispatch.py:1371-1463` — refusal ordering and the worktree check.
- `tools/land.py:261-302` — actual-diff enforcement for a foreign landing.
- `tests/unit/test_routing_policy.py` — class rows, no-override rule, and all three declared
  exceptions.
- `docs/adr/0061-work-leaves-claude-only-where-a-gate-catches-it-and-a-lanes-authority-is-the-enforcement-it-proves.md`
  — authorship rather than path, mechanical-gate eligibility, and demonstrated authority.
- `docs/research/dissolving-the-claude-class-list.md` — prior gate/competence/permission split and
  experiments E4, E6, E7, E8, and E9. This report narrows its class-8 proposal because the current
  `seats` field cannot express a required executor.
- `docs/research/codex-lane-live-findings.md` §10 — this lane's commit-without-gate ceiling.
- `.claude/hooks/deny-subagent-waits.py` — why a full corpus cannot be held in a subagent turn.
- GitHub issues [#219](https://github.com/andrewesweet/arma-cti/issues/219),
  [#224](https://github.com/andrewesweet/arma-cti/issues/224),
  [#234](https://github.com/andrewesweet/arma-cti/issues/234),
  [#258](https://github.com/andrewesweet/arma-cti/issues/258),
  [#262](https://github.com/andrewesweet/arma-cti/issues/262),
  [#266](https://github.com/andrewesweet/arma-cti/issues/266),
  [#281](https://github.com/andrewesweet/arma-cti/issues/281),
  [#294](https://github.com/andrewesweet/arma-cti/issues/294), and
  [#296](https://github.com/andrewesweet/arma-cti/issues/296) — rulings, measured refusals, and the
  frozen backlog population.
