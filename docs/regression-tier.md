# The Phase-1 in-game regression tier

`just regress` runs the whole in-world probe corpus against a fresh Phase-1 world per probe and returns one typed verdict per probe; `just regress <name>...` runs a subset. It is the thin early slice of the Phase-3 acceptance harness that issue #23 asks for, pulled forward under ADR-0016 rather than folded into #5. The orchestration is disposable — grown from `spike/run.sh`, replaced wholesale when ADR-0011's Python orchestrator arrives — but three things it establishes are durable and carry into Phase 3 unchanged: the probe corpus in `spike/probes/`, the machine-scoped lock that serialises the Arma tier, and the evidence-directory convention under `~/.arma-cti/runs/`.

Design only as of 2026-07-31; nothing below is built. The implementation order is at the end.

## What runs

The corpus is everything under `spike/probes/` plus one implicit member, **bareworld**: the Phase-1 mission brought up with no probe appended. Bareworld is not padding — it is the run that exercises the ~23 typed assertions already living in the addon and missions (`addon_functions_unresolved`, `prng_selftest`, `no_manifest_for_world`, `daemon_did_not_echo_the_request_id`, …), which between them cover most of #23's engine-dependent property list: functions resolving by name on a dedicated server, the PRNG's determinism against the real engine, the manifest loading, the `callExtension` round trip. The four existing probes cover the rest of what exists: presence sampling for both sides (`contacts`), Contact survival across engine knowledge decay (`contact-decay`), the projection reply (`projection`), and an AI-issued Order landing on real waypoints (`ai-commander`, run with `CTI_AI_SIDE=WEST`).

Two properties on #23's list have no probe yet and are corpus gaps, not runner features: `CfgRemoteExec` mode=1 refusing a non-whitelisted call (overlaps #21, which owns the client-to-gateway leg), and the broken-manifest refusal as a *repeatable* negative test — it has fired once, hand-staged, and a negative probe needs the runner to stage a corrupted manifest variant, which is the one place the runner and a probe must cooperate. Both are follow-on probes, written when their issues land.

Each probe carries a machine-readable header block the runner parses — the same facts today's headers state in prose, made loadable:

```
// probe: contacts
// issues: 28
// window: 240
```

`window` is the probe's deadline in seconds, sized to its subject per the rule on the `probe` recipe; the header prose still states the reason. `issues` names what motivated it, which is what makes "run per issue" selectable later. No separate manifest file: the probe is the unit of ownership, and a manifest beside it is a second place to forget.

## The command surface

`just regress [name...]` — no arguments runs the full corpus; names (`contacts`, `contact-decay`, matched against the `probe:` header / filename) run a subset while iterating. Depends on `build-shim build-addon` exactly as `probe` does. No bespoke environment variables: everything `just probe` currently takes from the caller's five variables is either fixed (mission, config, prefix) or read from the probe header (window).

The runner is one loop over the selected corpus. Per probe: acquire the tier lock, bring the world up fresh (daemon, server, staging — the existing `run.sh` machinery), append the probe to the generated harness, then **wait directly on the probe's `probe_done` line with the header window as the deadline**. This is the one behavioural difference from `just probe`, and it matters twice over: hold mode today spends the entire hold window waiting for a human client that a regression run never sends, so every probe run costs its full window even when the probe finished in forty seconds; and a regression tier has no business printing a direct-connect banner. `FAIL` ends the wait early and classifies as `assertion_failed`, exactly as `CTI_HARNESS_AWAIT` does now. Fresh world per probe, not one world running the corpus serially: probes spawn units, march Squads and deliberately corrupt the picture, and the isolation is what lets a probe's header window stay sized to its own subject.

A failing probe fails the run and the command exits non-zero after finishing the remaining probes — report everything, filter later — with the per-probe verdicts summarised last, worst class first.

## Runtime budget

Bring-up measured 20 s to mission running in Phase 0; with daemon start and staging, call it a minute per probe. Windows are deadlines, not sleeps, so a passing probe ends when it logs `probe_done`. Worst case (every probe running out its window: 150 bareworld + 150 projection + 240 contacts + 300 ai-commander + 300 contact-decay) is ~19 minutes of windows plus ~5 of bring-up — under half an hour. Typical passes finish well inside that, because only contact-decay's subject (120 s of engine decay, twice sampled) genuinely fills its window. A full pass is therefore an "over coffee" cost, not an inner-loop one, and the cost-control section below is written to that number. (CLAUDE.md cites 420 s for contact-decay; the probe's own header, which the justfile makes authoritative, says 300. The runner believes headers.)

## Serialisation

The Arma tier is single-occupancy: one server install, one port range (2402–2406), one machine shared with the human's play sessions. Concurrent agents serialise on an **`flock(2)` lock at `~/.arma-cti/tier.lock`** — machine-scoped, not repo-scoped, because agent worktrees are siblings and a lock inside any of them serialises nobody. `flock` rather than a pidfile because the kernel releases it when the holder dies, which is precisely the stale-holder failure Phase 0 met on a port (`infra_unavailable` on a daemon nobody had killed).

Acquisition is non-blocking by default. If the lock is held, the runner writes no evidence, touches no port, and exits `infra_unavailable` — per the failure-class table that is a stop, not a result — printing the holder metadata the lock-holder wrote beside the lock (`tier.lock.info`: pid, worktree, issue, probe list, started-at), so the queued agent knows what it is waiting behind and roughly how long. `just regress --wait <secs>` bounds a blocking acquire (`flock -w`) for agents that would rather queue than yield; unbounded waiting is not offered, because an agent that would wait forever should be doing other work.

The lock covers agents, not the human. The human is protected first by the port split (their sessions own 2302–2306) and second by a pre-flight check: if `arma3_x64.exe` is running on the Windows host (visible via `tasklist.exe` across the interop boundary), a play session may be live and the runner refuses with `infra_unavailable` rather than loading the shared machine underneath it. The human's side of the contract stays what it is: they never need to know the tier exists.

## Verdicts, and what an agent must do with each

Per probe the runner emits the verdict `run.sh` already synthesises — `PASS`, or `FAIL` with a `class` from the CLAUDE.md table — plus the probe name, evidence path, git SHA and Arma version, in a `verdict.json` in the run's evidence directory and as the last lines on stderr. The required responses are the CLAUDE.md table's, unchanged; the tier adds nothing to them and this document does not restate them. Two get regression-tier-specific teeth:

**`timeout`.** The window came from the probe's own header, so a timeout is never answered by editing the header upward unless the *subject* grew — a schema change that doubles the decay being measured, say — and the header prose must say so in the same change. A probe that times out at its declared window and would pass at a larger one, subject unchanged, is a synchronisation bug in the probe, per the `probe` recipe's rule (validated on #28: both fixes were geometry and readiness, neither was a longer wait).

**`flake_quarantine`.** The tier itself never retries: one run, one verdict. If a probe fails and a rerun passes with nothing changed — the definition of a flake — the agent does not average the two into a pass. The probe gains a `// quarantined: #<issue>` header line pointing at an open issue describing the synchronisation suspicion; the runner still executes quarantined probes but reports their verdict as `flake_quarantine` and excludes them from the exit code, so the corpus keeps gathering evidence about the flake without the flake gating anyone. De-quarantining is the fix for the named issue plus removal of the line, in the same commit. A quarantined probe with no open issue is out of policy — the quarantine line without the issue number does not parse.

## Evidence

Every run writes `~/.arma-cti/runs/<UTC-timestamp>-<probe>/`: `verdict.json`, `results.env`, the server stdout log, daemon log, daemon telemetry JSONL, the extracted `CTI|` lines, and the staged `harness.sqf` (the probe *as appended*, so the evidence carries the exact source that ran even if `spike/probes/` has since moved on). Machine-scoped for the same reason the lock is: worktrees are deleted after landing, and evidence that dies with its worktree is the #27 reconstruction-by-luck failure again.

Retention: failures are kept until the issue that consumed them closes; passes are pruned by the runner at startup to the last three per probe. The durable record is not the directory but the issue: a run that gates an issue is quoted into that issue — verdict line, class, evidence path, git SHA — before the issue closes. A later session re-reading why a run passed starts at the issue comment and follows the path; if the directory has been pruned, the comment still carries the verdict and the SHA to re-run it at.

## Cost control: what runs per issue, and who decides

Per issue: any issue whose change touches an in-world surface — `addons/`, `missions/`, `extension/`, the daemon's world-facing half, or the manifests — runs the **full corpus** once, green, before landing, and quotes the verdicts into the issue. Full rather than selected, because at five probes and under half an hour the selection machinery would cost more than it saves, and because the expensive failures to date have been the unselected kind — a projection change breaking contact sampling is exactly what a per-issue filter would have filtered out. The `issues:` header exists so that *when* the corpus grows past the point this stops being true, selection can be built without touching the probes; growing the corpus is what triggers building it, and that call is a fable-session call.

Not per issue: docs, tooling, process, and changes wholly covered by the unit tier (income arithmetic, rejection codes, wire formats — the things #23 explicitly keeps out). The implementing agent decides which side of that line an issue falls on, by the surface rule above; when genuinely unsure, the answer is to run it — a false half-hour is cheaper than a false green. During development of an issue, `just regress <name>` on the probes nearest the change is iteration, not gating; the full pass at the end is the gate.

Not this tier at all: per-commit or scheduled runs. The tier is per-issue by design; a cron-shaped invocation would contend for the lock against real work and burn the machine the human plays on.

## Boundary with #5 (Phase 3)

Phase 1 (this tier): bash orchestration grown from `spike/run.sh`; verdicts synthesised from `diag_log` lines by grep, as today; probes are plain SQF appended to the harness; evidence directories as above. Explicitly **not** built here, because ADR-0011 assigns them to Phase 3 and #5 owns them: the Python orchestrator, the verdict travelling through the shim as structured JSON, the gtest-style `EXPECT_*`/`ASSERT_*` framework, declarative specs in `tests/specs/`, the independent oracle, failure bundles as a schema, the coverage query, and the `just accept` / `just accept-all` names — those names stay reserved so Phase 3 arrives into a clean slot. When #5 builds the real harness, it inherits the corpus (probes become the seed acceptance specs), the lock, and the evidence convention; the `regress` runner is deleted, and `just regress` either dies with it or becomes an alias for the acceptance tier over the same corpus — the Phase-3 implementer's call.

## Implementation order

1. **Header blocks** on the four existing probes (`probe:` / `issues:` / `window:`), matching the prose already there. No behaviour yet.
2. **The lock**: `~/.arma-cti/` with `flock` acquire/release and `tier.lock.info`, wrapped around the existing `probe` recipe too, so serialisation protects hand runs the moment it exists.
3. **The runner**: the corpus loop with fresh world per probe, direct wait on `probe_done` under the header window (no client banner, no hold-window burn), per-probe verdicts, worst-class exit.
4. **Evidence directories** with `verdict.json` and pass-pruning.
5. **The `just regress` recipe** and the CLAUDE.md command-table row (run-when: before landing any issue that touches an in-world surface) — the row lands with the recipe, not ahead of it, per the Phase-0 retro rule. Authorised in ADR-0016.
6. **Windows pre-flight check** for a live play session.
7. Follow-on probes as their issues land: `CfgRemoteExec` mode=1 refusal (with #21), broken-manifest refusal (needs the runner's staging hook for a corrupted manifest variant).

Step 3 satisfies #23's first two acceptance criteria; steps 4–5 the rest.
