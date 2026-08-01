# The Phase-1 in-game regression tier

`just regress` runs the whole in-world probe corpus against a fresh Phase-1 world per probe and returns one typed verdict per probe; `just regress <name>...` runs a subset. It is the thin early slice of the Phase-3 acceptance harness that issue #23 asks for, pulled forward under ADR-0016 rather than folded into #5. The orchestration is disposable — grown from `spike/run.sh`, replaced wholesale when ADR-0011's Python orchestrator arrives — but three things it establishes are durable and carry into Phase 3 unchanged: the probe corpus in `spike/probes/`, the machine-scoped lock that serialises the Arma tier, and the evidence-directory convention under `~/.arma-cti/runs/`.

Built 2026-08-01 on #23, to this design. Where the build departed from it, this document has been corrected and says so; the departures are recorded in ADR-0021. The implementation order at the end is kept as the record of how it was staged.

## What runs

The corpus is everything under `spike/probes/`, including **bareworld** — the Phase-1 world with nothing asserted of it but what the mission itself builds. Bareworld is not padding: it carries the properties that had no Phase-1 home at all, and that #23 lists first — the addon resolving by name on a dedicated server, the seeded PRNG against the real engine, the daemon echoing a request id back through `callExtension`, the manifest's world being the world that got built, and the effect pump and presence report actually turning. Three of those lived only in `spike.Stratis`, the Phase-0 measurement mission nothing runs per issue.

Bareworld is a probe file rather than the implicit "mission with no probe appended" this design first described, because a mission with nothing appended has no completion line worth waiting on: `CTI|done` fires before the loops it has just started have polled once, so waiting on it would have meant a sleep after it. See ADR-0021.

The rest of the corpus covers what exists: presence sampling for both sides (`contacts`), Contact survival across engine knowledge decay (`contact-decay`), the projection reply (`projection`), an AI-issued Order landing on real waypoints (`ai-commander`), both sides under Commanders at once (`two-commanders`), an Assault bringing an enemy Base's HQ down and a Defend garrisoning a side's own (`base-assault`), the addon parsing its own authored JSON (`json-manifest`), a Campaign actually ending — an unattended two-AI run won by Decapitation (`campaign-end`) — and the manifest guard refusing rather than half-building (`manifest-missing`, red by design).

`campaign-end` is the corpus's one probe that engineers its **starting state**, and it does so twice: it spawns a rifleman inside each Objective's capture radius, so the Campaign reaches the state in which a Commander plays for the enemy HQ, and it puts the assaulting Squad on its approach 250 m out, as `base-assault` does. Both are licences about *position*, not about the subject — nothing in it reports to the daemon, issues a Command, or shortens a rule's clock, and the Assault that ends the Campaign is the Commander's own decision, waited for and refused if it never comes. The distinction is the one CLAUDE.md draws about windows, one level up: sizing a probe's setup to what is being measured is allowed, and arranging for the measurement to come out right is not.

Domination has no probe, and that is a finding rather than a gap. It was tried on 2026-08-01 with the same staged island: the ground went WEST at t=40 and EAST's Commander contested camp_rogain at t=511, 471 s into the 600 s the rule asks for. The Campaign was behaving correctly and the probe would have been a coin toss, so it is not in the corpus. Nothing could shorten the wait either — `setAccTime` is disabled in multiplayer and `setTimeMultiplier` moves the in-game clock rather than `time`, which is what the rules are written in. The Domination timer is unit-tested against simulated clocks, which is where a ten-minute rule belongs.

One property on #23's list has no probe and is a corpus gap, not a runner feature: `CfgRemoteExec` mode=1 refusing a non-whitelisted call, which overlaps #21 and belongs with it. The broken-manifest refusal, listed here as a second gap when this was written, is now `manifest-missing.sqf` — it asks the guard for a world with no manifest rather than staging a corrupted file, so it needed no runner staging hook. A *corrupted* manifest (present but unparseable) still would.

Each probe carries a machine-readable header block the runner parses — the same facts today's headers state in prose, made loadable:

```
// probe: contacts
// issues: 28
// window: 240
```

`window` is the probe's deadline in seconds, sized to its subject per the rule on the `probe` recipe; the header prose still states the reason. `issues` names what motivated it, which is what makes "run per issue" selectable later. No separate manifest file: the probe is the unit of ownership, and a manifest beside it is a second place to forget.

Three optional lines complete the block:

- `// env: CTI_AI_SIDE=WEST` — what the world must be brought up with for this probe to mean anything. The probe's requirement, not the caller's to remember; `just regress` still takes no environment variables of its own (ADR-0021).
- `// expect: <class>` — a red-by-design probe. The runner passes it exactly when the run fails with that class, and fails it when the class is wrong or when the probe passes. A probe with no `expect:` line expects `PASS`. Added 2026-08-01 under ADR-0019: `manifest-missing.sqf` landed after this design was written, and its green run is the bug.
- `// quarantined: #<issue>` — reports `flake_quarantine` and does not gate. Without an issue number the line does not parse, which is how "quarantine without an open issue is out of policy" is enforced.

`tests/unit/test_probe_headers.py` gates the whole corpus's headers in the no-Arma tier, so a malformed header costs a second rather than a bring-up. The runner re-validates the probes it was asked for before it touches a port.

## The command surface

`just regress [name...]` — no arguments runs the full corpus; names (`contacts`, `contact-decay`, matched against the `probe:` header / filename) run a subset while iterating. Depends on `build-shim build-addon` exactly as `probe` does. No bespoke environment variables: everything `just probe` currently takes from the caller's five variables is either fixed (mission, config, prefix) or read from the probe header (window).

The lock is acquired once for the whole run rather than per probe, so a queued agent takes the tier when the run finishes rather than racing for it between probes. Header validation happens before the lock: a corpus that does not parse costs seconds, not a place in the queue.

The runner is one loop over the selected corpus. Per probe: bring the world up fresh (daemon, server, staging — the existing `run.sh` machinery), append the probe to the generated harness, then **wait directly on the probe's `probe_done` line with the header window as the deadline**. This is the one behavioural difference from `just probe`, and it matters twice over: hold mode today spends the entire hold window waiting for a human client that a regression run never sends, so every probe run costs its full window even when the probe finished in forty seconds; and a regression tier has no business printing a direct-connect banner. `FAIL` ends the wait early and classifies as whatever class that `FAIL` line declared — `assertion_failed` only if it declared none. (The harness used to call every in-mission failure `assertion_failed`, including the ones the world had typed `timeout` or `oracle_disagreement`, which sent the reader to the wrong table row.) Fresh world per probe, not one world running the corpus serially: probes spawn units, march Squads and deliberately corrupt the picture, and the isolation is what lets a probe's header window stay sized to its own subject.

A failing probe fails the run and the command exits non-zero after finishing the remaining probes — report everything, filter later — with the per-probe verdicts summarised last, worst class first. The one exception is `infra_unavailable`, which abandons the remaining corpus: it is not a result, and carrying on past a stop produces more non-results. The exit code names the worst class; the mapping is in ADR-0021.

## Runtime budget

Windows are deadlines, not sleeps, so a passing probe ends when it logs `probe_done` and the run moves on. Measured on the first full green pass, 2026-08-01 (Arma 2.20.152984, eight probes, twelve minutes thirty-eight seconds end to end). `campaign-end` was added afterwards and measured on its own green run the same day:

| probe | window | measured |
|---|---|---|
| `bareworld` | 150 | 20 |
| `manifest-missing` | 150 | 13 |
| `json-manifest` | 150 | 34 |
| `projection` | 150 | 59 |
| `contacts` | 240 | 66 |
| `contact-decay` | 300 | 176 |
| `ai-commander` | 300 | 180 |
| `two-commanders` | 600 | 210 |
| `base-assault` | 480 | 173 |
| `campaign-end` | 750 | 370 |

Every figure includes that probe's own bring-up — daemon, server, staging, mission load — which is about 20 s of it. The corpus's declared windows total 42 minutes; it runs in 16, because no probe fills its window and the longest are sized for a subject (marching, decay, an HQ coming down) whose worst case they do not hit. A full pass is an "over coffee" cost, not an inner-loop one, and the cost-control section below is written to that number. (The probe's own header is authoritative for its window — CLAUDE.md says so — and the runner believes headers.)

## Serialisation

The Arma tier is single-occupancy: one server install, one port range (2402–2406), one machine shared with the human's play sessions. Concurrent agents serialise on an **`flock(2)` lock at `~/.arma-cti/tier.lock`**, taken by `spike/tier-lock.sh`, which wraps `just probe` as well as `just regress` — a hand run that ignored the lock would be exactly the collision it exists to stop — machine-scoped, not repo-scoped, because agent worktrees are siblings and a lock inside any of them serialises nobody. `flock` rather than a pidfile because the kernel releases it when the holder dies, which is precisely the stale-holder failure Phase 0 met on a port (`infra_unavailable` on a daemon nobody had killed). Validated in anger on 2026-08-01, the day it shipped: a session limit killed an agent mid-run and the lock freed itself — no stale holder, no ghost `infra_unavailable`. The dead run's leftovers are the other half of that event: an evidence directory with no `verdict.json` is not a result, and any server, daemon, or staged world the dead holder left is stale state to clear before the next run (ADR-0022).

Acquisition is non-blocking by default. If the lock is held, the runner writes no evidence, touches no port, and exits `infra_unavailable` — per the failure-class table that is a stop, not a result — printing the holder metadata the lock-holder wrote beside the lock (`tier.lock.info`: pid, started-at, worktree, branch, issue, and the command with its probe list), so the queued agent knows what it is waiting behind and roughly how long. The `issue` field comes from `CTI_TIER_ISSUE` and reads `unstated` when nobody set it — it is metadata for a human reading a queue, never something the command needs. `just regress --wait <secs>` bounds a blocking acquire (`flock -w`) for agents that would rather queue than yield; unbounded waiting is not offered, because an agent that would wait forever should be doing other work.

The lock covers agents, not the human. The human is protected first by the port split (their sessions own 2302–2306) and second by a pre-flight check in `spike/host-guard.sh`: if `arma3_x64.exe` is running on the Windows host, a play session may be live and the runner refuses with `infra_unavailable` rather than loading the shared machine underneath it. The human's side of the contract stays what it is: they never need to know the tier exists.

That check **fails closed**, and it says so because for its first day it failed open (#41). It was wrapped in `command -v tasklist.exe`, and the WSL2 interop `PATH` append is not in effect in an agent's shell, so the guard was skipped in silence on every run — a check that could not run, reported as a check that passed. The tool is now resolved by absolute path (`/mnt/c/Windows/System32/tasklist.exe`, overridable with `CTI_WINDOWS_TASKLIST`), and *not being able to read the process list* is the same `infra_unavailable` stop as reading the game in it. Only "the list came back and the game is not in it" is permission to proceed. `taskkill.exe` on teardown is resolved the same way and is now keyed on having launched a Windows process rather than on having been asked to, so a run that refuses at the pre-flight cannot kill the client it just refused to disturb. `tests/unit/test_host_guard.py` exercises both branches without Arma by substituting the tool.

## Verdicts, and what an agent must do with each

Per probe the runner emits the verdict `run.sh` already synthesises — `PASS`, or `FAIL` with a `class` from the CLAUDE.md table — plus the probe name, evidence path, git SHA and Arma version, in a `verdict.json` in the run's evidence directory and as the last lines on stderr. The required responses are the CLAUDE.md table's, unchanged; the tier adds nothing to them and this document does not restate them. Two get regression-tier-specific teeth:

**`timeout`.** The window came from the probe's own header, so a timeout is never answered by editing the header upward unless the *subject* grew — a schema change that doubles the decay being measured, say — and the header prose must say so in the same change. A probe that times out at its declared window and would pass at a larger one, subject unchanged, is a synchronisation bug in the probe, per the `probe` recipe's rule (validated on #28: both fixes were geometry and readiness, neither was a longer wait).

**`flake_quarantine`.** The tier itself never retries: one run, one verdict. If a probe fails and a rerun passes with nothing changed — the definition of a flake — the agent does not average the two into a pass. The probe gains a `// quarantined: #<issue>` header line pointing at an open issue describing the synchronisation suspicion; the runner still executes quarantined probes but reports their verdict as `flake_quarantine` and excludes them from the exit code, so the corpus keeps gathering evidence about the flake without the flake gating anyone. De-quarantining is the fix for the named issue plus removal of the line, in the same commit. A quarantined probe with no open issue is out of policy — the quarantine line without the issue number does not parse.

## Evidence

Every run writes `~/.arma-cti/runs/<UTC-timestamp>-<probe>/`: `verdict.json`, `results.env`, the server stdout log, daemon log, daemon telemetry JSONL, the extracted `CTI|` lines, and the staged `harness.sqf` (the probe *as appended*, so the evidence carries the exact source that ran even if `spike/probes/` has since moved on). Machine-scoped for the same reason the lock is: worktrees are deleted after landing, and evidence that dies with its worktree is the #27 reconstruction-by-luck failure again.

Retention: failures are kept until the issue that consumed them closes; passes are pruned by the runner at startup to the last three per probe. The durable record is not the directory but the issue: a run that gates an issue is quoted into that issue — verdict line, class, evidence path, git SHA — before the issue closes. A later session re-reading why a run passed starts at the issue comment and follows the path; if the directory has been pruned, the comment still carries the verdict and the SHA to re-run it at.

## Cost control: what runs per issue, and who decides

Per issue: any issue whose change touches an in-world surface — `addons/`, `missions/`, `extension/`, the daemon's world-facing half, or the manifests — runs the **full corpus** once, green, before landing, and quotes the verdicts into the issue. Full rather than selected, because at eight probes and under half an hour the selection machinery would cost more than it saves, and because the expensive failures to date have been the unselected kind — a projection change breaking contact sampling is exactly what a per-issue filter would have filtered out. The `issues:` header exists so that *when* the corpus grows past the point this stops being true, selection can be built without touching the probes; growing the corpus is what triggers building it, and that call is a fable-session call. That call was made concrete at the 2026-08-01 retro (ADR-0022): a full pass costs a measured ~1.5–2 minutes of wall per probe including bring-up, so **when a full green pass first exceeds 30 minutes measured — roughly 15–18 probes on the current curve — build selection on the `issues:` header before adding the next probe.** Until then the full corpus stays the per-issue gate.

Not per issue: docs, tooling, process, and changes wholly covered by the unit tier (income arithmetic, rejection codes, wire formats — the things #23 explicitly keeps out). The implementing agent decides which side of that line an issue falls on, by the surface rule above; when genuinely unsure, the answer is to run it — a false half-hour is cheaper than a false green. During development of an issue, `just regress <name>` on the probes nearest the change is iteration, not gating; the full pass at the end is the gate.

Not this tier at all: per-commit or scheduled runs. The tier is per-issue by design; a cron-shaped invocation would contend for the lock against real work and burn the machine the human plays on.

## Boundary with #5 (Phase 3)

Phase 1 (this tier): bash orchestration grown from `spike/run.sh`; verdicts synthesised from `diag_log` lines by grep, as today; probes are plain SQF appended to the harness; evidence directories as above. Explicitly **not** built here, because ADR-0011 assigns them to Phase 3 and #5 owns them: the Python orchestrator, the verdict travelling through the shim as structured JSON, the gtest-style `EXPECT_*`/`ASSERT_*` framework, declarative specs in `tests/specs/`, the independent oracle, failure bundles as a schema, the coverage query, and the `just accept` / `just accept-all` names — those names stay reserved so Phase 3 arrives into a clean slot. When #5 builds the real harness, it inherits the corpus (probes become the seed acceptance specs), the lock, and the evidence convention; the `regress` runner is deleted, and `just regress` either dies with it or becomes an alias for the acceptance tier over the same corpus — the Phase-3 implementer's call.

## Implementation order

Built in this order on 2026-08-01, steps 1–6. Step 7 is outstanding.

1. **Header blocks** on the four existing probes (`probe:` / `issues:` / `window:`), matching the prose already there. No behaviour yet.
2. **The lock**: `~/.arma-cti/` with `flock` acquire/release and `tier.lock.info`, wrapped around the existing `probe` recipe too, so serialisation protects hand runs the moment it exists.
3. **The runner**: the corpus loop with fresh world per probe, direct wait on `probe_done` under the header window (no client banner, no hold-window burn), per-probe verdicts, worst-class exit.
4. **Evidence directories** with `verdict.json` and pass-pruning.
5. **The `just regress` recipe** and the CLAUDE.md command-table row (run-when: before landing any issue that touches an in-world surface) — the row lands with the recipe, not ahead of it, per the Phase-0 retro rule. Authorised in ADR-0016.
6. **Windows pre-flight check** for a live play session.
7. Follow-on probes as their issues land: `CfgRemoteExec` mode=1 refusal (with #21), broken-manifest refusal (needs the runner's staging hook for a corrupted manifest variant).

Step 3 satisfies #23's first two acceptance criteria; steps 4–5 the rest.
