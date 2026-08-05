# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **A Commander can see his own Squads on the march.** Playtest 0001 lost sight of two
  Squads for the length of a march and read the absence as death — they were alive at
  eight men apiece. The Observation's `SquadView` now carries `pos`, the Squad's map
  position in whole metres, beside the Place-grained `at` it has always had, and
  `cti_fnc_mapRender` draws an own-Squad marker wherever the Squad is rather than only
  where it is standing still. A Squad the world has not yet reported has no position
  rather than a false one, and falls back to its Place exactly as before. `at` is
  untouched, so the fog rule, Contacts and every existing reader are untouched with it;
  the AI Commander deliberately does not read the new field at MVP, which its module
  docstring says out loud. The marker is up to one 5 s push behind its Squad, accepted
  and stated where the rate is set. Human ruling of 2026-08-04 on #175; shape recorded
  in ADR-0058. The wire cost is a fifth of a Squad record: Stratis's worst-case Squad
  ceiling falls from 71 a side to 59, and ADR-0030's per-map trigger is unmoved.

- **A corpus verdict is rendered from its own record now, not read off 25 lines by hand.**
  `just verdict [pool-dir]` reads a finished pool run's `pool.json` and the per-probe
  `verdict.json`s and prints the lines a close quotes into the issue the run gated: worst class,
  counts, wall, SHA and whether the tree was dirty, the runner's own per-probe block verbatim,
  and a detail line per non-pass probe with its evidence path. No argument reads the newest pool.
  It closes a correctness hole as well as a token one — #134 once quoted a "full corpus 20/20"
  banner before any tool result contained one, every figure matching by luck, and since the prune
  deletes passes, pass evidence outlives its own directory only in the quote. A record it cannot
  believe is refused rather than half-rendered: a pool directory with no `pool.json` is a run that
  died before its merge and is not a result (ADR-0022), and a `worst_class` sitting below its own
  worst verdict is quoted at the worse of the two with the disagreement named. `infra_unavailable`
  renders as the stop it is, nothing is interpreted, and nothing is posted. #199.

- **The orchestrator's stall watch is a tool now, and it waits outside the turn.** Six agent
  stalls in one cycle were each caught by an orchestrator polling from inside a turn, and
  ADR-0053 ruled the harness defect underneath out of this repo's scope, so that watching is a
  standing cost — 4.24% of the whole token bill, because a turn that blocks past five minutes
  throws away its prompt cache and a waiting turn is about 110× a working one (#195).
  `just watch <name> <worktree> [subject]` now arms a detached watcher and returns at once;
  `just watch-report [--ack]` prints one actionable line per finding and nothing while every
  watched agent is still working. The stall predicate is mechanical — a completion artefact
  exists, no activity inside a grace window, and the worktree's HEAD has not moved — and it
  distinguishes the two escalations the record separates: a stall on a clean tree is a lost
  dispatch, a stall on uncommitted work is work at risk, so that line names the files and orders
  the commit first. The watcher never messages an agent (prodding stays a judgement), never
  retries an `infra_unavailable` run, and reports "could not observe" as blindness rather than
  health. Orchestrator-facing usage: `docs/agents/recovery.md`. #198.

- **The development process's token bill has been measured, and it is mostly cache traffic.**
  `docs/research/token-efficiency.md` reads the four token classes off all 194 of this project's
  Claude Code session transcripts (17,515 turns) and prices #195's four seed ideas against them.
  What the model writes is 4.6% of the bill; a token that enters the context is re-read 35.7 times,
  so context size is a recurring per-turn cost. The largest recoverable waste is that a turn which
  blocks for more than five minutes loses the prompt cache and pays to rebuild it — 13.6% of
  everything spent so far, split between agents deliberately waiting (4.2%) and test recipes
  outliving the cache (2.8%). `just fast` is now 6 min 30 s, past that line on every invocation;
  the same suite runs in 1 min 44 s under `pytest-xdist`. Compressing agent documentation, the
  seed idea with the most intuitive appeal, measures at 25.6% on a real sample and ~1% of the
  bill, and it deletes the rationale this project has four validated instances of needing. #195.

- **Players choose a kit at their own Base, and keep it.** Under the human's ruling on #172
  (2026-08-04, recorded in ADR-0056), a player standing in his own side's Base is offered a curated
  menu of six kits — rifleman, grenadier, autorifleman, anti-tank, marksman, medic — and may take
  any of them whatever his squad type. It is free, it is players only (AI units keep their default
  loadouts), and it is refused anywhere but at Base. The kit survives death: a respawned player is
  dressed again in what he chose, as is one who joins in progress. The menu is one authored
  document, `addons/main/catalogue/loadouts.json`, read by the world that applies a kit and by the
  daemon that records which one — and what the daemon records is the *choice*, not the engine's
  loadout array, so a session save carries one word per player rather than a photograph of his
  magazines. #172, ADR-0056.

- **A `validated ×N` marker can no longer narrate a use its own count does not reach.** The count
  has lagged what its marker narrates twice: `docs/agents/recovery.md`'s ninth use landed with the
  count still ×8, and convention-lands' #131 exemplar with it still ×3 — that one rode three
  retros' status lines before anyone read the file. The retro skill's same-edit clause pre-priced
  the second violation as escalating to a mechanical check, and `just check` now runs
  `tools/check_validated_markers.py`: it reads the numbered uses in the four `> Status:` headers
  and reds when a header names a use its count does not reach. CLAUDE.md's five exemplar
  parentheticals are out of scope with the reason at the checker — no rule derived from the prose
  counts them, and every candidate miscounts at least two of the five in opposite directions. The
  list-format convention that would make them countable is a proposal on #186, for the human. #186.

- **A dead Commander watches but cannot act.** Under the human's rulings on #169 (ADR-0052), a
  Command issued from a machine whose player unit is dead is refused at the Command Port's door
  with a new judgement, `caller_dead`: "you are dead ... but issues no Command until he is back on
  his feet". The refusal covers both of the port's principals with one code and no asymmetry — a
  Commander's Purchase and a squad leader's Reinforce are turned away alike — because the check is
  asked of the calling machine before the gateway resolves which principal is asking. A dead
  Commander's `view` keeps arriving: watching is not acting. #188, ADR-0052.

- **The playtest observer's body leaves the world while he flies.** Under the human ruling on
  #190 (2026-08-04, the flag #178 left open), entering the Zeus-style observer camera in a
  playtest session now hides the human's own body and stops simulating it, and leaving the camera
  puts both back where he left them. Neither of the alternatives: a body that stays killable is
  what the old debug-console workaround cost him, and an invulnerable visible one is a target the
  AI can see and shoot at forever. Playtest path only, on the same boundary as the observer
  itself — nothing the regression corpus boots contains any of it. #190.

- **The AI Commander Reinforces.** Under the human ruling on #150 (2026-08-04), an understrength
  Squad standing at its own Base is now refilled by an AI-commanded side: when the side is at the
  force limit — where a Purchase is refused and Reinforce is the only way to add men — or when the
  discounted pro-rata refill undercuts the fresh Squad the Commander would otherwise buy. One
  spend per cycle, ties to the fresh Squad, and the funds trace carries both ways to add men with
  the trigger named in its sentence. Nothing about ADR-0040's two-principal port changes: a squad
  leader's own refill works exactly as before. #150, #191.

- **The pool's RAM trace attributes its own share.** The sampler's tier figure is machine-wide by
  `comm` on purpose — the right scope for a memory-ceiling question — but a peak could not be
  read without reconstructing which sibling pools shared the night (the unattributed 9.6 GiB of
  2026-08-02 took exactly that reconstruction). `ram.tsv` and `pool.json` now carry both figures:
  the machine-wide tier RSS and this pool's own, attributed by the values its slots already own —
  engine profiles and daemon ports. The healthy-box re-measure this enabled held the admission
  floor where it was: 2,439–2,463 MiB a slot across the 2026-08-04 full-corpus runs, against the
  2,500 MiB figure. #182, #125.

### Fixed

- **The slot pool's last four bulkhead leaks are walled.** A `kill` aimed at `just regress` —
  unlike a Ctrl-C, which the terminal delivers to the whole tree — used to reach the worker
  subshells and stop there, leaving up to N engines bound to the run's slot ports with nobody
  owning them, and then to *resume* the interrupted wait and go on scheduling probes onto slots
  it had just released; a signal now ends every flight through its watchdog, so each `run.sh`
  tears its own world down, and the pass exits `infra_unavailable` with a durable refusal line,
  because a run stopped from outside measured nothing. The reclaim's kills aim at a process
  rather than at a pid: each swept number is bound to the process's start time and re-checked
  immediately before every signal, so a number recycled between the sweep and the kill is left
  alone instead of `kill -9`-ing whatever inherited it. The install farm no longer reads the
  paths a hand run stages — it skips `mpmissions`, `@cti` and the shim at the copy instead of
  breaking them back out afterwards, so an unrelated `just probe` rewriting slot 0's install can
  no longer turn a pool's bring-up into `infra_unavailable`. And `--wait` queues in a loop: the
  wait establishes only that the client lock was free when it looked, and a third agent taking
  it in the gap used to turn a caller who had asked to queue into a refusal on the second
  contender it met. #151, from #140.
- **A starved machine can no longer forge a probe's class.** Twice, memory starvation arriving
  *after* admission — another agent's corpus, or the OS itself sickening — typed its verdicts
  `timeout` and `node_crashed`: false reds about the code under test, wearing classes whose table
  rows send the reader to the wrong response. A starvation watch now polls the same substitutable
  memory reader as the admission and between-probes readings, and a reading under the 512 MiB
  running floor with a probe in flight stops the pool and the flight: the probe is typed
  `infra_unavailable` — stop, not a result — above every other reading of its run, including a
  recorded pass. Completed verdicts stand. The one sanctioned interruption of work in flight,
  because a starved flight's result is already a non-result wearing a plausible class. #182,
  ADR-0055.
- **Failed pool evidence outlives the run that produced it.** Pool-directory pruning was
  count-only, so the starvation episodes' primary RAM traces were pruned while the issues that
  needed them were still open — only the numbers quoted into the issues survived. `pool.json` now
  records the run's `worst_class`, and the runner prunes only pools whose record reads green, to
  the last five; a failed pool, a torn record, or a run that died before its merge is kept. #182.
- **The regression tier's residual failure paths are typed, and its exit codes stop lying.** A
  `run.sh` the machine killed (an OOM kill above all) is now `infra_unavailable` with the signal
  named, not a "fix the harness" red; an in-mission class typo (`class=timout` — or a smuggled
  `class=pass`, which would have read back as a green verdict) is caught where the line is first
  read, in the class table's Python home; a mistyped flag exits 64 instead of `timeout`'s exit
  code; an unknown worst class exits as the harness bug it is instead of an undocumented 9; a
  failure after slots are acquired (a failed install prep, an evidence directory that cannot be
  created) emits a typed verdict and runs teardown instead of dying untyped with `.info` files
  left behind; a memory reading that fails mid-run says so instead of recording "0 MiB
  available"; a client-lock-blocked tail's evidence outlives the holder that caused it; and every
  pre-flight refusal leaves one durable line under `~/.arma-cti/runs/refusals.log`. #147.

- **The AI Commander no longer unpicks a Squad from a committed assault when its picture of the
  Base flickers.** The force an Assault had to bring was re-derived from the Contact's band every
  cycle, and in-world the band flickers — a leader standing on the Base can lose sight of the
  garrison for one sample — so a committed Squad was re-tasked to a defend twenty seconds after
  being ordered in. A committed assault now carries hysteresis (human ruling, 2026-08-04): the
  Squads already standing under an Assault floor its demanded mass, so the picture may raise what
  an Assault brings and never shed force the Commander committed. Still releasable — a genuinely
  lost assault declines and retreats exactly as before, and a materially better plan clears the
  standing-Order margin as ever. The Commander's trace says when the floor held the number up:
  "1 wanted, 2 committed". #181.

- **The daemon readiness poll stops writing bash errors into the run it is timing.** `grep -c`
  prints its count *and* exits 1 when it matches nothing, so `$(grep -c … || echo 0)` put a second
  line after a substitution that already held one and handed the arithmetic `0\n0` — an untyped
  `syntax error in expression` on stderr for every turn of the poll before the daemon came up, in
  the harness whose own failure-class table calls an untyped red a harness bug. The count now
  lands in a variable before anything reads it, and the fallback it replaces no longer folds "the
  log could not be read" into "the count is zero": that case is `infra_unavailable` naming the log
  it could not read, rather than 90 seconds of spinning reported as a daemon that never said it
  was ready. The restart path's counting is unchanged — it is what tells the second daemon's
  readiness line from the first's. #192.

- **An empty probes directory is a refusal, not a phantom corpus.** Without `nullglob`,
  `spike/regress.sh` read an empty `spike/probes/` as one probe named `*` and the "no probes"
  refusal never fired; it fires now. #162.

- **A keepalive RPC that fails twice reports both failures.** The shim discarded the cached
  connection's error the moment it decided to reconnect, so when the reconnect also failed the
  caller saw only the second error and lost what the cached socket actually died of. Both now
  arrive in the one error payload. #162.

### Changed

- **Two surfaces stopped introducing themselves as throwaway Phase-0 scaffolding, and the spike
  world's stay of execution is written on the world itself.** `spike/run.sh` called itself
  "throwaway measurement scaffolding" that "Phase 1 replaces", having since become the runner every
  in-world gate goes through; its header now says so and points at where the callers can be read off
  rather than listing them. `missions/spike.Stratis` was recorded in two places as "run by nothing",
  which the command-port audit's own last exit-criteria bullet already contradicted — `just spike`
  boots it through `spike/run.sh`'s defaults, so deleting it would have broken a live recipe. It
  stays, its `description.ext` now carries why and when it goes (ADR-0011, Phase 3), and both stale
  claims are corrected to point at the derivation. No behaviour changed anywhere. #165, #158 (F8).

- **`just fast` returns in about a minute and a half instead of seven.** The Python tier runs
  under `pytest-xdist` at one worker per logical CPU, and the same 1,410 tests that took 6 min 22 s
  serially take 56 s. Nothing about what they assert changed: the tier's wall clock was six times
  its user CPU, so it was waiting on locks and bash subprocesses rather than computing, and the
  workers take up that slack. The one test that could not be shared out — a background child that
  had to outlive its run — turned out to be waiting sixty seconds on a descriptor its claim was
  never about, and now settles in a third of a second while still catching the bug it was written
  for. This is the change #195 measured as the largest recoverable waste on the recipe side: a gate
  that outlives the five-minute prompt-cache TTL makes the next agent turn pay to rebuild its whole
  context, and `just fast` had crossed that line on every invocation. #197, #195.

- **Dying costs 30 seconds, at your own Base.** The played mission's respawn timer moves from 5 s
  to 30 s (ADR-0052, ruling 6) — a playtest-tuned placeholder in ADR-0020's sense, documented at
  the line that sets it, so play can move the number without reopening the decision. Where you
  come back was already settled and unchanged: your own Base, no Funds cost, no location choice.
  The phase-0 spike world keeps its 5 s; it is not the mission anyone plays. #189.

- **The pool's merge is decided in Python, not bash.** The regression runner's merge — the
  dead-slot rule, client-lock-blocked typing, the mem-stop overlay, worst-class ranking — and the
  `pool.json` it writes were hand-rolled JSON on both sides: a `printf` writer, an
  indentation-dependent `sed` reader, and a byte-grep pruner, each coupled to the other's exact
  rendering. They are now `tools/pool_merge.py` under `just unit` (ADR-0049's third migration),
  the fallback `verdict.json` a failed typer implies has one writer, and the shell keeps the
  acting: releasing dead slots, deleting pruned passes, exiting the worst class. A merge that
  cannot run fails closed to `infra_unavailable` rather than open to a green pool. #185.

- **The daemon's domain seams tightened along the second DDD pass's low-severity findings.** The
  port now asks the Campaign the two Squad questions it used to read off the roster directly, and
  its test-only `ledger`/`outbox` pass-throughs are gone, so its surface is judgement only. A
  Campaign refuses a Ledger opened at any figure other than its table's `starting_funds`. What a
  Command or an Effect carries is fixed at construction, so an Effect on the outbox can no longer
  be edited between push and delivery. The telemetry `side` column now carries its provenance
  beside it — `side_source` says whether the row holds the gateway's stamp or the payload's own
  claim. And the wire budget's worst case takes the widest side name from `SIDES` rather than
  hardcoding `WEST`, so a longer side name widens the budget by itself. No wire change anywhere.
  #152.

- **`spike/run.sh` refuses a second command-line argument instead of silently dropping it.** A
  mistyped invocation used to run in a mode the caller did not ask for; it is a usage error now,
  exit 2, with nothing brought up. #162.

- **`just regress --slots 1` is the serial tier byte for byte, as its header always claimed.**
  Pool slot 0 wrote engine profile `ctispike0` and headless-client profile `ctihc0` where a hand
  run writes `ctispike` and `ctihc1`; slot 0 now keeps the hand tier's own names, the way it
  already keeps `~/arma3server` and ports 2402–2406. Slots 1+ renumber their headless-client
  profiles to `ctihc2`… with them. #162.

- **Each seam the pool libraries had triplicated has one home.** The host guard's
  free/running/unavailable → verdict ladder ran as three near-verbatim bash copies across the pool
  libraries; it is decided in `tools/host_guard_verdict.py` under `just unit` now (ADR-0049's
  second migration), and a guard whose mapper cannot run fails closed to a stop rather than open to
  a pass. The lock holder's `.info` block and the `infra_unavailable` exit code — each defined in
  three files — have one sourced home each, the hand-run tier lock takes slot 0 through the same
  acquire the pool uses, and `run.sh`'s duplicated verdict sweep — the two-copy structure behind
  #83's misclassification — is one function on both paths. #161.

- **Two daemon hot paths shed rebuilt work.** Dispatch looked its handler up in a verb table
  rebuilt on every request — the shape #90 already removed from the port — and a `poll` re-encoded
  the whole candidate reply once per pending Effect, so pricing one drain read the backlog
  quadratically. The table is now built once, and a drain is priced incrementally, to the byte the
  full encoding gives. The wire is byte-for-byte what it was. #156.

- **The daemon now reads its own Command catalogue instead of restating it.** The catalogue claims
  a Command the game can build and one the daemon accepts cannot drift apart, but the daemon's own
  validation never read it: the handler table restated the verb set, each handler restated its
  Command's arguments, and the five Effects the daemon pushes were held to the declared effect
  schema entirely by hand — so a verb or argument changed on one side landed as an in-world
  discovery. The handler table and every handler's argument reads are now pinned to the catalogue
  by unit tests, and the outbox refuses any Effect whose name or arguments the catalogue does not
  declare, at the one door every world effect leaves through. The wire format is byte-for-byte what
  it was. #145.

- **What a probe's outcome means is now decided in Python, not bash.** The regression runner's
  typing ladder — the watchdog rule, the untyped-red rule, `expect:` inversion, quarantine — and
  its hand-rolled `verdict.json` heredoc were sixty lines of shell, testable only by a bring-up;
  they are now `tools/probe_verdict.py` under `just unit`, so a wrong class is a red unit test
  rather than an in-world discovery. First instance of the standing policy (ADR-0049): non-trivial
  logic lives in Python under pytest, bash keeps the process seams — launching, `flock`,
  environment, timeouts — where the shell is the actual subject. #171.

- **The addon's side vocabulary has one home.** The side-name↔engine-side pairing was restated by
  hand five times across the addon — two switches, a hand-built enemy-of table, a `str` respelling,
  and a membership literal in the presence sampler that was fail-silent: presence on a side the
  literal did not list was simply never reported, and nothing asserted on the gap.
  `cti_fnc_sideVocabulary` now owns the pairing — the names come from the exported schema's
  `sides`, the engine objects are the one half SQF must own — and derives both directions and the
  enemy-of relation once, refusing whole rather than translating in part; the five sites read it,
  as does a sixth born since the finding (`fn_baseAssault`'s destroyed-by attribution). What the
  daemon sees on the wire is unchanged. #149.

### Fixed

- **A squad effect short of a declared argument is refused instead of guessed at.** The world's
  effect receiver used to answer a `squad_spawned` or `squad_reinforced` arriving without `size` by
  inventing an 8-man strength — a number appearing nowhere in the economy the daemon charged
  against, on a fact the daemon owns. The receiver now holds a squad effect's arguments to the
  declared catalogue the daemon's own door already enforces, read from the exported schema rather
  than restated in SQF, and refuses the malformed document with a typed verdict the pump
  dead-letters. #159.

- **The Commander's map picture is readable in the three ways playtest 0001 said it was not.**
  Clicking the map now draws a yellow selection marker on the Place the click named — the answer
  used to live only in the hint's `Place:` line — and a click on open country removes it, because
  open ground deliberately selects nothing. A Squad's marker text and a Contact's no longer print at
  the town centre, which is exactly where the engine prints its own town name, so all three stacked
  into one unreadable pile at every Place: Squads now sit north of the label, Contacts south, and a
  second Squad at the same Place steps further north instead of overprinting the first. And a
  Squad's strength finally has a denominator — `rifle 4/8` instead of `rifle/8`, where the 8 is the
  establishment strength read from the same catalogue the price comes from rather than a number
  written down again in SQF. All of it is presentation on `cti_fnc_mapRender`; the Observation on
  the wire is untouched. #174.

### Added

- **The Commander is now told when ground changes hands and when one of his Squads is wiped.**
  Playtest 0001's summary judgement on the seat: orders went out and nothing came back until the
  map's picture silently differed. Both moments now raise a notification on the Commander's screen
  in the shape Arma's own singleplayer task notifications take, visible with or without the map
  open — an Objective changing hands is named with its new owner (going CONTESTED announces itself
  the same way), and a Squad reaching zero men is named once, not re-announced on every 5 s push.
  Read client-side off the difference between consecutive Observations, so the wire, the mode=1
  whitelist and the AI Commander's inputs are all untouched. Wording and look are a playtest-tuned
  placeholder. #176.

- **A playtest session now has an observer mode: press Y to fly free, press Y to come back.**
  Playtest 0001's feedback stopped at what the Commander's map shows, and the live workaround — a
  camera typed into the debug console — left the map unreachable and the incantation to remember.
  Any session booted on a `spike/playtest/` fixture now assigns the human a Zeus-style curator: the
  engine's own keybind toggles a free-fly camera that spawns no unit and changes nothing the AI can
  perceive, and leaving it lands back in the body the Commander's map is one keypress from. A camera
  with no edit rights, deliberately — no addons, nothing editable, every curator action disabled;
  map markers are the one power the engine keeps free. The regression corpus stages none of it. #178.

- **The Observation a Commander plans against is now a declared wire shape rather than a
  convention.** It was the last family whose two sides were mirrored by hand: the daemon named the
  document's keys as literals in `serialise` and read them back as literals in `parse`, and the map
  UI read them as a third set of literals in SQF — so renaming a Squad's `type` or a Contact's
  `echelon` failed nowhere until a Play Session, on the human's own path. The names are declared
  once in `cti_daemon.observation`, exported into `command-schema.json` beside the inbound report's
  shapes, and the map functions' literals are held to that export by `just unit`. The wire itself is
  byte-for-byte what it was. #163.

- **The daemon can be booted on hand-authored files without editing its source.** Which economy
  table, which manifests directory and which map a daemon plays on have been arguments since #76,
  and nothing could reach them from a command line, so booting a fixture Campaign meant editing the
  composition root. `--economy`, `--manifests` and `--map` now say so directly, defaulting to
  today's authored files, and a map id no manifest in the directory describes is refused in words
  naming both the id and where it looked, rather than a traceback. #164.

- **A delegated decision can no longer land without saying what would overturn it.** ADR-0019 has
  required that section since the day it retrofitted ADR-0015 for missing one, and nothing checked:
  three ADRs reached a guided review of all twenty-nine delegated decisions without it, found only
  because one sitting read every one of them. `just check` now runs `tools/check_adr_form.py`, which
  asks of every ADR carrying `Delegated-decision: yes` that it name its overturning evidence and
  carry the human's `Reviewed-by-human:` review-state line. The three — 0016 on pulling the
  regression tier forward, 0030 on charging the Observation's budget to the map, 0036 on freezing
  the world when the daemon's identity changes — now state theirs. #137.

- **The recall a human signed off is now something the world has been seen to do.** ADR-0031 grew
  the recall radius from 160 m to 1.15 km and named what keeping your own ground is worth; both
  numbers were approved on a 200-seed sweep and neither had ever happened in a running world,
  because no company had ever stood on ground a side held. A new probe stages exactly that — WEST
  holding three Objectives, its Squads marching, and enemy riflemen appearing on the held ground in
  numbers its own leaders have to acquire — and watches the Order that comes back. A platoon is
  ignored for forty-five continuous seconds; a company turns a marching Squad round inside two, from
  a Squad measured a kilometre off the ground it is recalled to. Nothing tells the daemon the men
  are there and nothing asks for the Order. #104.

- **A playtest can start in the middle of a Campaign instead of at its opening.** Half of the first
  playtest's half hour went on reaching a board rather than playing one, because a fresh Campaign
  was the only thing that could be booted. A committed fixture now plays the Campaign into a named
  mid-Campaign state before handing it over — WEST holding three Objectives with a Squad standing on
  each and EAST massing a kilometre off the front — and every part of that state is reached through
  the door the game uses: Squads Purchased through the Command Port, ground captured by standing on
  it, Orders issued through the port, Funds whatever the Campaign says they are. It refuses to open
  the play window on a board it did not actually reach, so a brief that names it is naming something
  that was true. Staging costs about forty seconds and the session clock starts after it. #42.

- **A Squad that has taken losses can be brought back to strength, and its own leader can ask for
  it.** Reinforce joins Purchase and Order as a Command: name a Squad standing at your own Base and
  the men who are missing arrive there, costing the missing fraction of what that Squad cost new,
  discounted. The discount, 0.8, is a playtest-tuned placeholder in the authored economy table and
  wants a session behind it before anybody calls it balanced. Ammunition and equipment restock is
  unaffected: it stays free at Base and is not a Command at all. With it, the Command Port gains a
  second principal — until now every Command came from a side's Commander, and a squad leader may
  now issue Reinforce for the Squad he actually leads, checked on the server against who the engine
  says is leading which group rather than against anything the client sends. Reaching for another
  Squad is refused `not_your_squad`, and Purchase and Order stay the Commander's. A leader can do
  this while both sides are under AI command, which is the MVP's second mode. ADR-0040.

- **The world is now proven to see the enemy standing on your ground.** Every in-game run so far
  had put NATO units on the ground and nothing else, so that the presence sampler reports a CSAT
  squad at all — and reports it as CSAT rather than as nobody — was assumed. If it had been wrong,
  an Objective held by the enemy would have read as empty, never contested, never changed hands and
  kept paying its old owner, with every unit test still green. The in-world probe that already
  watches an Objective change hands now watches it go Contested with both sides inside the radius,
  and then fall to the side left standing there.

- **The audit that Phase 1 exists to produce: no path outside the Command Port.** Every way an
  Order, a Purchase or any other change to strategic state can reach the world is now enumerated in
  `docs/command-port-audit.md`, each with the gate that holds it — one whitelisted function for a
  client, one extension call for the server, one dispatch and one lock in the daemon, one root for
  human and AI Commands alike, and one applier for effects coming back. Three things outside that
  envelope are named and justified rather than left to be discovered, and the holes the audit found
  are written down beside them.

- **The integration demo runs as one thing.** The probe that drives a real client in a Commander
  seat now does it in a world where the other side is being played by the AI Commander, so a single
  world holds both kinds of Commander for the first time. Recorded with it: taking over a side means
  bringing the world up with that side free, because one side has one Commander whichever kind it
  is — there is no handover, and the probe asserts the refusal rather than describing it.

- **The in-world regression tier runs three worlds at once, and a full pass costs eleven minutes
  instead of twenty-six.** `just regress` now schedules the corpus across a pool of slots — a slot
  being a port block, a daemon, a server install, an engine profile and a world that agree — with
  the longest probe started first so no slot idles behind the tail. `--slots 1` is the serial tier,
  unchanged and still correct: slot 0 is the install and the port block the tier has always used, so
  the fast path and the known-correct path are one code path at different N. The two probes that
  drive the Windows client run last and one at a time, because there is one Windows host and the
  guard that protects a live play session cannot tell our client from the human's. A probe that
  fails is a verdict rather than a stop for its siblings; a slot whose worker dies is reported as
  not-a-result and cleared rather than read as a red. Measured: seventeen probes, seventeen passes,
  646 s against 1,599 s serial, peaking at 7.3 GB of tier processes with 1.0 GB still free.

- **A daemon that restarts mid-session can no longer reset your Campaign behind your back.** The
  daemon holds the whole Campaign in memory, so a restart is a factory-fresh Campaign; the shim
  reconnects without saying anything, and nothing in the protocol distinguished one daemon from the
  next. So a mid-session restart repainted every Objective NEUTRAL, put Funds back to the starting
  balance, restarted the Domination clock and turned every Squad you had bought into an orphan that
  kept fighting and would not take Orders — with nothing on screen and one line in a log nobody
  watches. Every reply now carries the identity of the process that gave it, the world latches the
  first one it sees, and a change stops the world rather than letting it play on: the map is left
  showing the last thing that was true, no Command spends Funds that no longer exist, and every
  screen says CAMPAIGN LOST and to restart the mission. Surviving a restart is a later thing
  (Phase 2); being told about one is not. ADR-0036.

### Fixed

- **A Squad bought once is spawned once, even when the wire hiccups.** The game applies an effect
  and only then tells the daemon it has, so an acknowledgement lost on the way back leaves the
  daemon holding the effect and handing it over again on the next poll — which is the design, and
  every effect but one survived it. A repeated Squad spawn did not: it stood a second full Squad on
  the map, pointed the roster at the new one, and left the first group's men on the ground answering
  to nobody — alive, still fighting, reachable by no Order, counted by neither the world nor the
  daemon, and there for the rest of the session. The Campaign said nothing about any of it. The game
  now recognises a Squad it has already spawned and treats the repeat as the redelivery it is,
  saying so once in the log with the sequence and the Squad id. #141.

- **A wedged Arma-tier run now frees its slot instead of holding the pool until a human notices.**
  The tier's own timeout mechanism could fail open. Every deadline in `spike/run.sh` was computed
  through `bc`, and without it `(($(echo … | bc)))` compares an empty operand, which is false — so
  the deadline never fired and each wait ran until the process it watched happened to die. The
  deadlines are bash integer arithmetic now, over bash's own clock, and a run that cannot compute a
  bound refuses at the pre-flight as `infra_unavailable` rather than running without one. The three
  unbounded calls around them are bounded too: the WSL interop calls the play-session guard and
  teardown make, whose wedging is a known failure mode of this machine; every `uv run` the harness
  makes; and teardown's wait for a child it has just killed. Above all of it, `just regress` now
  runs each probe under a watchdog — the probe's own window plus ten minutes for bring-up and
  teardown — and kills the process tree of a run that blows it, typed `infra_unavailable`, which is
  not a result and gates nothing. The watchdog sits above the window and never inside it: a probe
  that outran what it measures is still the `timeout` its own harness typed. #144.

- **Four validators now refuse in their own words rather than through whatever exception fell out
  first.** A manifest whose `position` was not two numbers, or whose `adjacent` was not a list of
  ids, passed the key checks and then raised a bare `IndexError` or `TypeError` from deep inside the
  loader — past the one error type every caller of that module catches — so an authoring slip read
  as a crash rather than as a sentence naming the field and what it costs. `--ai WEST:--5` slipped
  through a sign-stripping digit check and drew argparse's generic complaint instead of the seed
  refusal written for it. Two Campaigns ending on the same condition in the same in-game second
  wrote the same archive filename, and the second silently replaced the first — the record of a
  played Campaign lost to a name; the name is now claimed rather than assumed, and a taken one steps
  aside. And banding an empty sighting returned an empty echelon, a valid-looking band that would
  have put a place on a Commander's picture with nothing standing at it. #155.

- **A wedged daemon now says no instead of quietly collecting a blocked thread per retry.** The
  daemon answers one request at a time and waited on that lock forever, while the transport gave
  every connection a thread of its own with no bound — so a handler stuck on anything, a filesystem
  stall or a planner bug, gathered one more parked thread roughly every two seconds for the rest of
  the session, none of them going anywhere and nothing on disk saying so. A request that cannot be
  reached within 250 ms is now refused with a typed `busy` error, which is inside the shim's own
  500 ms budget, so the world learns the daemon said no rather than guessing it had died. Nothing
  was judged and nothing spent, so asking again carries the request out. Connections that go silent
  for two minutes are closed as well, which is the same pile-up arriving through a half-open peer.
  A healthy daemon is untouched: its requests are three orders of magnitude inside the bound, and
  the wire is unchanged. #142.

- **An outbox that stops draining is visible before it is a session's problem.** Undelivered Effects
  were counted only on a successful poll, which is exactly the row that goes missing in the failure
  that matters: the effect pump dies while income keeps paying and both AI Commanders keep buying,
  and the backlog accumulates in memory all session with nothing written down — a starvation that
  had to be diagnosed from outside the daemon when it happened. Depth is now recorded whenever it
  crosses a band of 25, on the way down as well as up, from the request path rather than the poll.
  #142.

- **A finished regression run hands its slots back the moment it exits, instead of a few seconds
  later.** The pool measures the machine's memory while it works, and the sampler that does it
  sleeps three seconds between readings. Every child of the run inherits the slot locks, so when
  teardown killed the sampler the sleep it had forked survived it holding all three — and a run
  queued behind this one was told the slots were busy by a process that no longer had any business
  with them. The sampler now lets go of every slot before it takes its first reading, since it never
  needed one; nothing else about it changed. An ask for a slot in the first second after a run
  returns was refused five times in five before, and granted five times in five after. #138.

- **An error out of the shim is now always valid JSON, and asking the shim for its address always
  answers an address.** The shim's only escape was rewriting a `"` to a `'`, so any detail carrying
  a backslash — a Windows path out of an io error, most plausibly — or a newline produced a line
  the receiving side could not parse: it would have failed to read the error rather than reporting
  it. Escaping now follows RFC 8259 and leaves everything else alone. Separately, retargeting the
  shim answered `{"error":...}` if a panic elsewhere had poisoned a lock, where the call's contract
  is the address in force and no caller can tell one from the other; the address is a whole string
  replaced in one assignment, so that poison described a panic somewhere else and nothing about the
  address, and it is now recovered rather than propagated. The cached connection is dropped on
  retarget unconditionally, which it was not: a poisoned connection cell used to skip the drop and
  leave the shim answering over a socket to the daemon it had just been moved off. #93.

- **The no-Arma test suite no longer competes with the Arma tier for the machine.** One test that
  drives the harness end to end sends a Windows client, and a run that sends one takes the
  machine-wide lock on the one headed client — for real, because that test alone never moved its
  state directory into a temporary one. So `just unit` quietly took the client away from live
  regression runs for a few seconds at a time, and was refused by them: the refusal is a stop before
  anything launches, and the test then died reading a record the refused run had never written. That
  is the one red in twenty-six suite runs nobody could explain; two suites started at once reproduce
  it every time, with no Arma anywhere. The test now owns its own lock, reports the harness's stated
  reason instead of a bare missing key when a run refuses, and a tripwire fails the suite if another
  test ever reaches for the real one. The pool tests in the same file got the same treatment for
  memory, having gone red about free RAM while a sibling agent's world was up. #132.

- **A regression run no longer launches a world into a slot it failed to clear.** The tier confirms
  that a dead run's leftovers are really gone before reusing a slot, and then the runner threw the
  answer away: a slot whose server and daemon had survived the kill went straight into a bring-up
  that binds those same ports, and the failure came back reading as the world's fault instead of the
  dead holder's. A slot that does not come back clear is now typed `infra_unavailable`, named
  together with the survivors and the ports and install they are still holding, and skipped — the
  run carries on in the slots that were clean, since one dirty slot should cost a slot rather than
  everybody else's results, and the slot's lock is held for the rest of the run so nothing else is
  handed it either. When every slot a run holds fails to clear, nothing was measured and the run
  says so rather than reporting a result. The same applied to a hand run, where slot 0 is the only
  slot there is. #133.

- **A Command now has to say who is issuing it, and the daemon refuses one that does not.** The
  Command Port's audit found that the acting side fell back to whatever side the payload named, so
  anything that reached the daemon's socket without passing the gateway commanded for the side it
  wrote down. The gateway stamps the caller's side alongside his Squad now, and a Command carrying
  no stamp is refused `unknown_caller` — a new refusal in the same vocabulary every other one comes
  back in. Nothing a player does changes: a Commander's Command was always stamped from the
  server's own assignment state. What changes is that the stamp, rather than the socket, is the
  door. #128, ADR-0044.

- **The daemon no longer puts its socket on the LAN for the sessions a human joins.** It bound
  every interface whenever the world was held up for a client, on a Phase-0 reason — the
  measurement mission's clients called the daemon themselves — that the shipped mission has never
  had. The daemon now refuses to listen anywhere but this machine's own loopback, and says so and
  exits rather than starting somewhere it should not be. The socket stays unauthenticated by
  decision, with the reasoning and the evidence that would overturn it written down. #128, ADR-0044.

- **The build no longer carries the tool that can hand WEST half the island.** The desync
  investigation's load generator spawned thirty-two soldiers onto the first four Objectives; it was
  off unless asked for, and present in every build regardless, including one a person could play.
  It now lives beside the harness and is copied in only by a run that asks for it, so a build a
  human plays does not contain it at all. The tool itself is unchanged and the investigation still
  has it. #128, ADR-0045.

- **Clearing a dead run's leftovers now waits for them to actually go.** `kill` returns when the
  signal has been posted, not when the process is gone — it still holds its ports and its install
  until the kernel tears it down — so reclamation sending `SIGKILL` and returning reported a slot
  clear that was not, and the next thing to run was `run.sh` binding those very ports. It now
  confirms the hard kill the way it already waited out the polite one, names anything still in the
  process table afterwards, and reports a failed reclaim rather than a cleared slot. The same
  misreading, on the other side of a death, is what made `test_a_dead_holders_lock_frees_itself`
  flaky twice over: `flock` frees on the *last* descriptor closing, which is not the event
  `proc.wait()` returns on. Measured here at up to 7.4 ms of daylight between them on a loaded box.
  The test now waits for the observable it means — every descriptor on the lock closed — and then
  asserts the kernel's promise in a single non-blocking ask. Acquire is deliberately left
  non-blocking through that window: a grace would let the test pass on the grace rather than on the
  kernel. #130.

- **A regression run no longer starts into a machine that has no room for it.** The slot locks
  serialise agents but say nothing about memory, so two three-slot pool runs took six worlds onto
  one 12 GB machine, drove it to 39 MiB available, and came back twenty minutes later with two
  worlds alive but starved — a loop silent for four minutes, reported as a crashed node, which
  reads like the code's fault and is not. The pool now takes a memory reading before it takes a
  lock, in the same fail-closed shape as the guard that protects a live play session, and answers
  in one of three ways: run, run in fewer slots and say so, or refuse with the reading and launch
  nothing. The floor is `N × 2,500 MiB + 1,024 MiB`, and both numbers come from what the tier has
  actually been measured using rather than from arithmetic. It is re-asked between probes too, so
  somebody else arriving at minute eight stops the pool taking new work instead of starving what is
  already running, and `--wait` queues on the machine the way it already queued on the locks — a
  full machine is somebody else's run as surely as a held lock is. #125.

- **The Arma tier's own test suite no longer fails one full run in two.** The test for the property
  the whole slot design rests on — the kernel frees a dead holder's lock, with no reaper and no
  pidfile — killed only the top of the holder's process tree and then raced its own child. It was
  the test that was wrong, but the thing it was wrong about is real: half a dead holder keeps the
  slot, because the lock is freed by the last descriptor and not the first. So the case is now
  asserted rather than raced, and a run that finds every slot busy prints the pids actually holding
  each lock beside the metadata — which otherwise names the dead parent and sends the reader after
  a process that no longer exists. #121.

- **The Campaign's end-to-end probe no longer stages its own ambush.** `campaign-end` shortens a
  4.4 km march by putting the assaulting Squad 250 m from the enemy HQ, after waiting for the
  defenders to leave. The wait watched a 400 m ring around the HQ and the Squad lands at 250 m on
  the one road out — so "clear" could mean an enemy Squad standing 150 m in front of where eight
  men were about to appear. On one run in six they appeared, turned round, spent three minutes
  winning a firefight the probe had created, never reached the HQ, and the run timed out on an
  assault it had itself prevented. The wait now covers the approach as well as the HQ, and the
  timeout reports the closest range the Squad reached, which is the number that tells "it never
  set off" apart from "it arrived and the assault failed". #106.

- **Two agents testing at once no longer fight over the one Windows client.** The regression pool
  ran its two client probes last and one at a time, which ordered them against the rest of its own
  run and against nothing outside it — so two runs starting from sibling worktrees each drained
  their own pool and then both drove the single headed client on the single Windows host. Each read
  the other's client as a live play session and stopped, and on a tighter race they would have
  joined two worlds through one engine profile. The client leg now takes a machine-wide lock for as
  long as it holds the client, and a second run either queues for the time it was told it may wait
  or is refused and shown whose run it is behind. The guard that protects a real play session is
  unchanged and still refuses to tell one client from another; what the lock adds is that a client
  nobody has claimed is the human's, which is the only case worth stopping for.

- **Running the no-Arma tests no longer kills whatever the Arma tier is running.** The pool's own
  unit tests drive the real `spike/regress.sh`, which reclaims each slot it acquires by killing
  whatever holds that slot's ports or runs out of its install. The tests moved the locks and the
  install into a temporary directory, but a slot's port block is arithmetic no variable moves — so
  a `just unit` on this machine swept 2402/2502/2602 and 9099-9101 and killed a live pool's three
  worlds and their daemons mid-probe, leaving no error line, no dump and a green re-run. Reclaiming
  now asks first whether it is the machine's tier at all, and a run pointed at another state
  directory kills nothing on it. #124.

- **A Campaign can no longer buy its way past what the wire carries.** Nothing bounded a side's
  roster, so a long Campaign with hoarded income could legally buy the Squad whose arrival takes the
  Commander's view past the engine's 10,240-byte return — after which the engine truncates in
  silence, the view stops repainting, and the session degrades every cycle with the cause hours
  behind it. A Purchase that would cross the limit is now refused at the port like any other rule,
  in words a Commander can act on. The number is measured rather than chosen: it is the point at
  which this map's worst-case Observation stops fitting one reply, so a bigger island — which pays
  for its own size in Contacts — gets a smaller one without anybody deciding.

- **One effect the world can never carry out no longer stops the Campaign.** The pump stopped at the
  first effect that failed to apply and retried it every two seconds forever — correct for something
  a later poll could clear, wrong for an effect name this world does not know, a side that is not
  playing, or a side with no Base, none of which any amount of waiting fixes. Everything behind it —
  Squad spawns, Orders, the end of the Campaign itself — never arrived, with both sides' Funds
  already spent and nothing on screen to say why. A refusal is now classified where it happens: a
  permanent one is dead-lettered — a typed failure line in the world's log and a row in the
  Campaign's telemetry — and the queue moves on, while a transient one still waits, and a queue that
  has not moved in three minutes says so whatever the classification claimed.

### Changed

- **What a Squad is made of is now authored data rather than a classname buried in the addon.**
  Every Squad spawned into the world was eight copies of one of two hardcoded soldier classnames,
  and the `squad_type` the Commander had paid for was written to the log and then ignored — a rifle
  Squad and a weapons Squad were the same eight men. Composition is now an ordered roster of unit
  classnames per side, authored in `config/economy.json` beside the price it was set against,
  validated by the schema source, and exported into `command-schema.json` on the route ADR-0017
  lays down for authored data. `fn_effectApply` reads the roster and holds no classnames, so a
  Reinforce refills a Squad from its own composition instead of from a literal, and the men the
  world puts on the ground cannot drift from the table the daemon charged for them. The values are
  deliberately today's: the same classnames in the same numbers, so in-world behaviour is unchanged
  and this is the seam and not a balance change. Filling it in is gameplay content and stays behind
  the human's feel gate. #79, #82.

- **Three decisions from the human, recorded where they bind.** Mid-session Commander takeover is
  out of MVP — a desired long-term feature, up to hot-swap with elections and evictions, but a
  session is still joined as Commander at bring-up (docs/mvp-scope.md, #126). N=3 is confirmed as
  the regression pool's default now that its RAM extrapolation has been measured true (ADR-0028,
  #125). And the Reinforce discount of 0.8 is explicitly held for playtest judgement: the first
  playtest brief gains a scenario for feeling it out from the Commander's chair (#123).

- **A machine-locality check now exists only where it can fire, and can no longer refuse in
  silence.** The addon carried twenty-nine of them — "this function runs on the server, not on your
  machine" — and on the evidence of every call path in the repo only two of them could ever fire,
  because the rest start in the mission's own server-side init. Worse, they refused by handing back
  an empty reading:
  an empty presence map is indistinguishable from "nobody stands anywhere", so a report assembled
  on the wrong machine would have been accepted as a truthful picture of an empty island with
  nothing in any log. Nineteen unreachable checks are gone, each replaced by a sentence in the
  function's header saying why the caller already decides the machine. The ten that remain sit at
  the three real boundaries — the Command Port's door, the two things the server pushes to a
  player's machine, and the seven long-running loops — and every one of them now writes a typed
  failure line naming the function and the machine before it refuses. `just check` rejects the
  hand-rolled form, so the next one written has to be a real boundary or not exist. ADR-0041.

- **Squads are owned by the server for their whole life, and the build now says so.** An Order is
  issued through nine engine calls, one of which — `setCurrentWaypoint` — is documented to work only
  on the machine that owns the group, with four more declaring nothing at all. Handing a Squad to a
  headless client would therefore write its Order and never switch the Squad onto it: an Order that
  looks issued and is not. That every Squad is server-owned was true already but unwritten; it is now
  a rule (ADR-0039), stated under **Squad** in the glossary and enforced by `just check`, which
  rejects `setGroupOwner` anywhere but the headless-client desync diagnostic that predates it.

- **The AI Commander's decision trace says Purchase, the word the rest of the game uses.** Its
  spending rows read `purchase rifle` and "300 Funds purchase no Squad this map sells" where they
  used to say "buy" — the one artefact that exists for a human to read and argue with was written in
  vocabulary the glossary tells everything else to avoid.

- **The rest of the regression corpus now ends when its subject does, and the settles that stayed
  say why in their own probe.** Nine more fixed settles converted to waits on the condition being
  asserted, each keeping its old number as the deadline: eight identical "let the world build" holds
  became one shared wait on the world's own counters and returned in **5.0 s against 20 s, on all
  eight**; the `contacts` probe waits for the overlap between two leaders it needs (1.0 s against
  30 s); `contact-decay` waits for the sighting to actually leave the sample, which records our 120 s
  ageing bound instead of assuming it; `casualties` waits for the men to land, the deaths to
  register and the buffer to reach the daemon. **The first measured full passes of all fourteen
  probes are 23m46s and 23m58s**, against the 26m40s that had only ever been arithmetic — two
  consecutive greens rather than one, because a conversion is the change most likely to introduce a
  flake and this tier never averages runs. Four settles were kept and
  argued for rather than converted — `two-commanders` most importantly, because its 180 s soak is
  the window the largest-observed drain is measured in and an extremum shrinks with its window.
  Converting it would have reported a smaller maximum under the same name, which is worse than the
  settle. The per-probe decisions are in `docs/regression-tier.md`.

- **The AI Commander decides by multiplying considerations through response curves rather than by
  summing eight weights, and a consideration can now veto an option outright.** Each candidate Order
  is normalised to [0, 1] on eight axes, remapped by an authored curve and multiplied, so a zero
  propagates and the evaluator abandons the option — the pattern every serious utility system in
  `docs/research/commander-prior-art.md` uses, and the answer to a scorer where `threat` could make
  ground expensive but never impossible and every axis added diluted the rest. What it plays like is
  meant to be the same: the opening move is still income-bearing ground on every seed, an undefended
  enemy Base is still raided by one Squad, a company at our own Base still turns a Squad round and a
  platoon still does not, and the massing table still sends four Squads at a company and declines
  when it has three. The one behaviour that changed in degree is that a Squad will now be recalled
  to its threatened Base from up to 1.15 km away rather than only from the Base itself. ADR-0031
  carries the reasoning; ADR-0014's four calls survive it and ADR-0027's massing rule is untouched.

- **The decision trace reads differently.** A candidate's `terms` are now the eight considerations
  as factors in [0, 1] rather than signed contributions that sum to the score, `score` is their
  compensated product in [0, 1] rather than a total in income units, margins in `because` carry
  three decimals rather than one, and each decision carries a new `vetoed` count beside `scored` —
  how much of the option space was refused before it was weighed.

- **A map that could never fit its Observation into one `callExtension` return now fails
  `just unit` when it is authored, instead of truncating in silence in a Play Session.** #26 pinned
  the ceiling at about 35 Squads a side and blamed the Squad count; re-measured after the enemy
  roster left a Commander's view (#27) and Contacts took its place (#28), the binding term has
  inverted. Contacts are keyed by place, so an island's size is charged before either side has
  bought anything: Stratis costs 1,611 bytes of a 9,216-byte budget and carries 71 Squads a side,
  a forty-Objective island carries 24, and a sixty-Objective one does not fit **empty**. The budget
  is therefore checked per map rather than per roster (ADR-0030). Nothing in MVP changes — one map
  ships, and it has five and a half times the headroom it needs.

- **A Contact's age is reported in whole seconds.** It was arriving as `47.29999999999927`,
  seventeen characters of binary-subtraction noise on a field carried once per place, read
  downstream as a freshness ratio against a window of minutes — no precision anything could use.
  Truncated rather than rounded, so a sighting can never read fresher than it was.

### Fixed

- **A crashed background loop no longer takes half the game down in silence.** The world runs on six
  long-running threads — effects, income and captures, Commander assignment, the Commander's own
  view, standing Orders, Base assaults — and one scripting error kills the thread it happens in and
  nothing else. Until now the mission carried on looking healthy with effects never spawning, or
  income and captures stopped, or Squads drifting off their Orders, for the rest of the session, and
  the only recovery was the human guessing that something was wrong and restarting. Each loop now
  stamps a heartbeat every turn and one small watchdog reads them: a loop that has gone quiet for
  three of its own cadences, or half a minute, whichever is longer, is named in a typed
  `node_crashed` line and captioned on every screen with what has stopped and that a restart is the
  fix. Nothing is restarted automatically, deliberately: a loop that died on the state it met would
  die again on the next turn, and its counters — which probes and reports read as evidence — would
  silently start again from zero. Being told is the fix; pretending to have recovered is not.

- **An unusable Command Port schema is refused rather than crashing the two callers that read it.**
  `cti_fnc_commandSchema` answers an empty schema when its export is missing or unreadable and says
  callers must treat that as fatal; the Command builder and the Command Port's gateway both read
  straight through it instead. So a broken build met a raw script error — in the gateway's case
  while it was deciding whether a client may command a side at all, and a script error there kills
  the script it happens in — rather than the typed `schema_stale` refusal its siblings already gave.
  Both now ask whether the part they need is present, which covers a missing export and a malformed
  one alike, and a new red-by-design probe (`schema-stale`) asks each guard the question in-world
  and lives to tell.

- **A report the daemon cannot read no longer leaves half of itself behind.** The observe report was
  folded into the Campaign field by field as it was read, so a batch of casualties whose fourth row
  was malformed had already written the first three when the refusal was raised — a timeline that
  looks complete and is not. The whole report is now read before any of it is acted on, so a refusal
  leaves the Campaign and its record exactly as they were. The refusal also names the field that was
  wrong, by its path in the document (`casualties.deaths[3].by_side`), rather than saying that
  something in the report was.

- **A dead daemon is no longer indistinguishable from a quiet one.** The shim reports a transport
  failure as `{"error": "..."}`, which is a JSON object — so it passed every loop's only check and
  read as *success with nothing in it*. The map froze, income stopped, the AI opponent went quiet,
  Commands came back as `? — ?`, and no line anywhere said the daemon was down. Every call now goes
  through one place that tells the four outcomes apart, says so once when the daemon stops answering
  and once when it comes back, refuses a Command it could not get judged rather than showing you a
  transport error as a verdict, and counts a report as completed only when it actually completed.
  The last of those also fixes a counter that several tests and probes had been reading as proof the
  world was healthy.

- **The daemon answers one request at a time, whoever is asking.** Every connection got its own
  thread and the Campaign — ownership, the Ledger, the Roster, Contacts, the outbox — was written
  under no lock at all, so two connections could interleave a mutation and quietly corrupt Funds or
  the outbox sequence. Two connections is not hypothetical: the shim's resend after a failed
  exchange arrives on a fresh connection while the request it duplicates may still be running on the
  old one, which is exactly the moment the duplicate has to meet the record rather than race it. One
  lock around the whole request, rather than a lock per field or a serial server: a request is 746 µs
  at p50 with both planners inside it, and a serial server would have made the resend wait for the
  stuck connection it exists to escape.

- **A stalled daemon can no longer freeze the server frame for ten seconds at a time, and a slow
  call can no longer queue a human Commander's click behind it.** The shim's read and write timeouts
  were 5 s each — five times the engine's own 1000 ms frame-stall budget — and a call that
  reconnects and resends spent that twice, so every loop turn against a hung daemon was a
  multi-second hitch the player felt. A synchronous call now carries a single 500 ms budget for the
  whole round trip — connect, write, read and resend together — which is half the engine's cap and
  still 57× the slowest call ever measured, so a call that gives up does so without the engine
  complaining on our behalf. And `rpc_async` — the path defined as the slow one — now takes its own connection
  instead of the shared one every synchronous judgement queues on, as ADR-0005 required of it before
  it carries production work.

- **A probe can no longer pass green with half of its subject switched off.** `human-commander`'s
  client leg — the only half of it that crosses the machine boundary, a Command built on a real
  client and judged on the server — was gated on an environment variable that defaulted to off, so
  every corpus run of it finished green having tested the server side alone and logged one line
  about it that nothing scored. Optional legs now default **on** in the corpus, declared in the
  probe's own `env:` header, and a leg that did not run reports `unverified` and makes the run
  `infra_unavailable` — which this tier already refuses to read as a result — instead of passing.
  Every verdict now names its legs: `legs: client_port_caller:ran client_port_accepted:ran …` in the
  run summary and in `verdict.json`. `client-port`'s six step exits, which short-circuited to a bare
  completion line, name themselves too. The rule is written down in `docs/regression-tier.md`.

- **A full-corpus run no longer stops itself on its own Windows client.** `taskkill /F` returns when
  the request has been made rather than when the process is gone, so a client probe would pass, the
  run would move on, and the next probe's pre-flight two seconds later would see the still-exiting
  `arma3_x64.exe`, read it as a live play session and abandon the rest of the corpus — reproduced
  twice, on two shas. The host guard was right and is unchanged: it cannot be taught to excuse a
  process it recognises without also being able to excuse the human's, and "a process we did not
  start means stop" stays absolute. Instead the run that launched a client now waits for it to leave
  the host's process list before releasing the tier, and says so in its evidence if it never does.

- **A Campaign that has been won no longer accepts Commands.** The Campaign already refused the
  world's reports after victory and the AI Commanders already stood down, but the Command Port never
  asked: a Purchase arriving after the end screen spent a finished Campaign's Funds, minted a Squad
  and queued a spawn onto an outbox the world may still drain, and an Order rewrote a Squad's
  standing instruction. Both are now refused with a new rejection code, `campaign_over`, which the
  game learns from the generated command schema like every other code — a human Commander whose map
  screen is still open is told why rather than being quietly obeyed. The invariant is stated once,
  at the Campaign itself: buying a Squad, issuing an Order, folding in the world's account of the
  Squads and folding in what a side's leaders saw are now the Campaign's own verbs rather than
  things the port and daemon did to its parts, so a rule about what a won Campaign will not take
  cannot be missed by a caller that never asked.

- **Every way of bringing the Arma tier up now asks whether the human is playing, and waits its turn
  for the machine.** The guard that refuses to load the shared host underneath a live play session
  ran in one place, and `spike/run.sh` asked it only when a run meant to *drive* the Windows host —
  so `just probe` and `just spike` started a daemon, a dedicated server and a staged world on the
  human's machine without ever asking. `just spike` also took no tier lock, so it could stage over a
  locked `just regress` run's server install mid-pass. The guard is now asked by `run.sh` itself,
  before anything is launched, and the `spike` recipe serialises on the same lock as everything else.

- **An in-mission `FAIL class=timeout` is no longer reported as a failed assertion.** `spike/run.sh`
  has two verdict paths, and only the hold/regress one read the class the world declared; the other
  called every red an `assertion_failed`, sending the reader to fix the code under test when the
  failure-class table says investigate synchronisation. Both paths now type the failure off the
  line the world wrote. Alongside it, the harness's staging steps are checked rather than assumed
  (a failed copy is a clean `infra_unavailable` instead of a confusing engine error three steps
  later), a push-path report that dies is recorded instead of silently producing nothing, a value
  containing a newline can no longer forge a second record in `results.env`, a probe header
  containing a quote can no longer break the run's `verdict.json`, and a Windows process the
  harness could not kill on teardown says so.

- **The mission-cycle spike now fails on the freshness axes it was only writing down.** Its own leg
  header promises that every axis is an assertion and that a missing reading fails rather than being
  skipped, but a PRNG stream that carried over into the second mission, and second-mission telemetry
  carrying rows the first mission wrote, were recorded and then reported `verdict=PASS` — the same
  false-green shape #44 found. Both gate now, the telemetry one only where the daemon was restarted
  and carry-over therefore means something, and a reading that could not be taken is a failure
  rather than a blank. Both legs also wait on the world's own counters instead of a flat 20-second
  dwell, which the cycle runner had made impossible by staging them without the shared probe
  prelude.

- **A busy outbox no longer hands the world more effects than one `callExtension` return can
  carry.** The engine truncates a return past 10,240 bytes in silence, and the effects poll handed
  over every pending entry in one reply — so a world polling slowly, or two Commanders in a burst,
  would eventually get broken JSON with the effects past the cut lost and nothing said. A drain is
  now bounded at nine tenths of the cap, the same figure the Commander's view already guards itself
  at, and the acknowledgement cursor delivers the remainder on the next poll. Measured: 72
  `squad_spawned` effects in one drain, against the largest drain two AI Commanders have ever
  produced (4) and the engine's own 100-per-frame limit. A single effect too large to cross one
  return now fails the poll loudly and stays on the outbox instead of being cut in half.

- **A Command the shim had to send twice is no longer carried out twice.** The shim resends a
  request when an exchange fails on its cached connection, and a write that succeeded before the
  read failed had already been executed — so one transport hiccup could spend a side's Funds twice
  on one Purchase, or give both AI Commanders a second turn on one report. The retry stays, because
  losing a Command is worse; the daemon now answers a request line identical to one it has already
  answered from its record rather than acting on it again, and writes the duplicate down. ADR-0034.

- **An unreachable daemon address no longer freezes the client for twenty seconds.** The shim's
  connect had no timeout of its own, so a LAN candidate a joining client cannot reach blocked for
  the OS default — about 21 s on Windows, inside a blocking call that stalls the frame for its whole
  duration. It now gives up after one second, which is a hundred times what a handshake on loopback
  or the same LAN takes.

- **A test run pointed at a different daemon port now actually talks to that daemon.** The shim
  reads its daemon address from `CTI_DAEMON_ADDR` and defaults to port 9099, and the harness set
  only `CTI_DAEMON_PORT` — so moving the daemon moved the daemon and left the world talking to
  whatever still held 9099. The two agreed only because both defaulted to the same number. Found by
  running two worlds side by side for #44: one daemon received both of them, and the run that was
  not checking its telemetry passed. Unchanged at the default port.

### Added

- **`just cycle-spike` runs two test missions in one server process, and proves the second one
  starts clean.** The dedicated server can be made to change mission unattended with nobody
  connected — mission rotation cannot, because it waits for a player, but `serverCommand` with a
  `serverCommandPassword` can — and the switch costs under a second against an eleven-second cold
  start. It is not part of `just regress` and is not being adopted: behind the parallel pool #47
  proposes it would save about half a minute a pass, and the port allocation that pool was waiting
  on has since been granted. It stays only as the fallback if three slots turn out not to fit. The
  measurements, the corpus classified for whether probes could share one world (one of fourteen
  can), and the recommendation across all three speed-up levers are in
  `docs/research/multiplexing-the-arma-tier.md`.

- **The in-world regression tier can now be asked for the probes an earlier issue produced.**
  `just regress --issues 28` runs everything whose `issues:` header names #28; `just regress --list`
  prints what a selection would run — names, and the deadlines they add up to — without taking the
  lock, opening a port or bringing a world up. Two things deliberately did not change. The full
  corpus is still what runs with no arguments and still what gates anything touching an in-world
  surface, because a probe's header records what motivated it rather than what it covers, and
  filtering your own change by your own issue number selects only the probes you just wrote. And a
  filter that matches no probe is an error rather than a very fast green pass — the one way this
  tier could lie is by being narrowed to nothing.

### Changed

- **A probe now ends when its subject has finished, not when a clock says it probably has.**
  Half of a full regression pass — 705 s of 1,405 s — was probes watching a fixed clock rather than
  the world. The `ai-commander` probe, whose 150 s settle was the worst of them, now reads the claim
  it is about to assert continuously and stops the moment it becomes true: **179 s to 44 s**, same
  verdict, three green runs over. A full pass is 21m10s where it was 23m25s. The 150 s survives as the deadline it always was, so a run in which nothing
  moves still fails at the same instant in the same class. The rule this is allowed under, the audit
  behind it, and which of our waits the engine can signal versus which must be polled are in
  `docs/regression-tier.md`.

- **The AI Commander now judges how much force a Base needs, instead of always sending one Squad.**
  It could name the enemy HQ as a target but not take one anybody was standing on: assignment gave
  every Place one Squad, so a raid arrived eight men strong however much of the enemy was reported
  on it, and against a defended Base it died there. The Commander now reads the band of what its
  own men have seen — a team, a squad, a platoon, a company — and details that many Squads to the
  Assault, or, if it cannot find them, calls the Assault off and puts everyone back on the ground
  they were second-best at. An undefended Base is still raided by one Squad exactly as before, and
  the raid still arrives late in a Campaign rather than opening it.

  Two things follow that are worth knowing at the table. Concentration is visible: half the force
  peeling off a held island for one Place is a Commander going for the throat, and the ground it
  leaves stays held. And an old sighting still deters less than a fresh one but never excuses a
  smaller force — a company seen ten minutes ago stops making the Base look expensive, and does not
  stop four Squads being sent, because the only way to find out that it left is to go and look.

### Fixed

- **A client that joined and took the Commander seat is no longer recorded as one that never
  arrived.** The hold harness waited three minutes for a log line only the Phase-0 mission writes,
  then filed the run's evidence as `connected-but-never-entered-mission` — of a client that had
  connected, entered, been assigned a side and been playing for two of those three minutes. It now
  also accepts the Phase-1 mission's own signal, which says strictly more: a player whose unit
  occupies a Commander slot and carries a UID is a person in the mission, not merely a socket.

- **The guard that protects a live play session now actually runs.** The Arma tier asks whether
  Arma 3 is open on the Windows host before it takes the shared machine, and refuses if it is —
  but it asked for `tasklist.exe` by name, which is not on an agent's `PATH` here, so the check
  was skipped in silence and every run proceeded on a question nobody had answered. It now
  resolves the tool by absolute path and fails *closed*: not being able to read the Windows
  process list is `infra_unavailable`, the same stop as seeing the game in it. A run that means
  to drive a client on the Windows host asks the same question before launching anything, so a
  client already open is left alone rather than killed on teardown by a harness that cannot tell
  yours from its own.

### Added

- **The leg between a person's client and the Command Port is now exercised unattended, failures
  and all.** A regression probe launches a real headed client, waits for it to be assigned a side,
  and drives six Commands across the network from it: an accepted Purchase whose judgement comes
  back to that client, a Command whose `side` the client filled in with the enemy's — the Squad
  arrives on the caller's own side and the side it asked for is untouched, which is the server's
  stamp shown rather than asserted — a Command from a machine the server has not assigned, refused
  `wrong_side` by the gateway in its own words without the daemon being asked, and two payloads
  that are not Commands, refused as judgements rather than as silence. Last, the client calls two
  things the mission does not whitelist, having just proved through the gateway that it can call
  the one it does: neither lands, and the engine writes both refusals in its own words to the
  client's log, which the harness now copies back across the WSL2 boundary as evidence.

- **A world can now be held open for a play session.** `spike/playtest/session-hold.sqf` keeps the
  Phase-1 world standing for as long as the boot line asks, or until somebody wins, instead of
  tearing it down the moment a client finishes joining. It lives outside the regression corpus
  because it asserts nothing and waits for a person. The first brief that uses it is
  `docs/playtest/0001-commander-seat.md`: half an hour in the WEST Commander seat against the EAST
  AI, looking at the things automation cannot see.

- **A human can now command a side from the map.** Take a Commander slot, open the map, click a
  Place and press a number: Purchase a Squad, or Order one to Capture, Defend, Assault or Reserve.
  It is crude on purpose — a hint for a panel, local markers for your own Squads and the Contacts
  you have, the number row for verbs — and every visual choice in it is a playtest-tuned
  placeholder that Phase 4 replaces wholesale. What is not crude is where the click goes: the same
  Command Port entry function, the same wire format and the same `remoteExec` whitelist the AI
  Commander's Commands travel through. The verb list is read out of the port's schema rather than
  written down in the UI, so a human cannot express an Order the AI cannot, and the port's typed
  refusals reach the player in the port's own words — `already_held`, `wrong_ground`,
  `insufficient_funds` — rather than as a dead click. A click never waits: it hands the Command to
  `remoteExec` and the judgement arrives on its own.

- **Each Commander now sees its own strategic picture on its own map.** The server asks the daemon
  for the view belonging to the side it has assigned, under a new `view` transport verb, and
  forwards it to that Commander's client alone. It is the same `Campaign.observation(side)` call
  the AI planner reads in-process, so Commander symmetry covers knowing as well as commanding: own
  Funds, own Squads, Contacts for the enemy, and Objective ownership plus Base HQ status as the
  public scoreboard. The server never reads it, and there is no unprojected picture to ask for.

- **The project has a black box.** Every death in the world is now written down as it happens:
  who died — the Squad and side, not an engine id nobody recognises — where, on the authored
  place *and* to the metre, at the death's own clock reading rather than the report's, and by
  whom, naming the killer's Squad and side and the vehicle where one was involved. Deaths with no
  Squad behind them are recorded too, and so are deaths nobody can be blamed for. The rows join
  the daemon's existing telemetry stream rather than opening a second log, and no Commander ever
  reads them: this is the operator's record, not intelligence. The motivating case is a probe that
  timed out with a Squad at three of eight and nothing in the evidence saying where the other five
  went.

- **`tools/timeline.py`** reads a run back out of its telemetry as a sequence a person can follow,
  and every Arma-tier run now leaves one in its evidence directory. Pointed at a probe's own log
  with `--expect`, it also checks that every death the world says it staged is actually in the
  record — which is what lets an in-world casualty test be an assertion instead of a screenshot.

- A `casualties` probe: three staged deaths on two Objectives, each a different shape of row, with
  the harness failing the run when the daemon's file does not account for all three.

- **A Campaign can now be won.** Both conditions the MVP decided are live. **Domination**: one
  side owns every Objective at once and holds the lot for ten sustained in-game minutes — losing
  one Objective, or having it contested, restarts the ten minutes rather than pausing them, and
  the timer is not persisted, so it starts again on every boot. **Decapitation**: a side's Base HQ
  structure is destroyed and the other side wins, whoever brought it down; two HQs falling in the
  same report are resolved by whichever the world reported first, deterministically. There is no
  draw. Until now a Campaign ran until somebody stopped watching.

- **An end screen, and an archive.** On victory the Campaign is marked complete, both AI
  Commanders stand down, income stops and ground stops changing hands. The world is told once,
  through the same outbox every other effect rides, and carries a summary read back off the run's
  own telemetry — the winner, the condition, the board as it finally stood, income paid and
  Commands accepted per side, Squads lost, and the HQ that fell. A headed client sees that as a
  caption; the mission does not end itself, and the laid-out end screen is #18's map UI. The
  completed Campaign is archived as a JSON record beside the telemetry, and the next session
  starts a fresh Campaign — because the archive is a record of what happened rather than a state
  to resume (ADR-0023), so there is nothing to load and the freshness is not a rule anyone has to
  remember.

- **Each Base's HQ, intact or destroyed, is now in every strategic picture** — including the
  public one the server paints markers from. The two win conditions are the scoreboard rather than
  intelligence, so this is the one enemy-shaped fact that crosses the fog boundary, and it was
  decided that way with the fog itself. It costs 54 bytes on the wire and does not grow with the
  Campaign: the map has one Base per side.

- `domination_seconds` in `config/economy.json` (600, a playtest-tuned placeholder like the rest of
  that table).

- A `campaign-end` probe: an unattended two-AI Campaign on the real topology that actually ends, by
  Decapitation. It engineers two things about *position* and nothing about a rule — the island, so
  the Campaign reaches the state in which a Commander plays for the enemy HQ, and the march, so
  nobody waits out the four and a half kilometres between the Bases. The Assault itself is the
  Commander's own decision through the port, and the probe refuses the run if it never comes.

- `just regress` — the in-game regression tier. It runs the probe corpus in `spike/probes/`
  against a fresh Phase-1 world per probe and returns one typed verdict each, mapped onto the
  documented failure classes, with the worst class as the exit code; `just regress <name>...` runs
  a subset while iterating. Before this, every in-world check was a hand-typed invocation with
  five bespoke environment variables that nobody who had not typed it could reproduce, and a
  property proven the day it was built was unprotected the day after. Each probe now declares its
  own deadline, the issues that motivated it, and any world it needs, in a header block the runner
  reads — so the command itself takes no environment variables, and a probe that finishes early
  ends early instead of burning a hold window waiting for a client that a regression run never
  sends.

- A `bareworld` probe, carrying the properties that had no Phase-1 home: the addon resolving by
  name on a dedicated server, the seeded PRNG against the real engine, the daemon echoing a
  request id back through `callExtension`, and the effect pump and presence report actually
  turning. Three of those existed only in the Phase-0 measurement mission, which nothing runs.

- Serialisation of the Arma tier on a machine-scoped lock at `~/.arma-cti/tier.lock`, wrapped
  around `just probe` as well as `just regress`. The tier is single-occupancy — one server
  install, one port range, one machine the human also plays on — while agent worktrees are many
  and short-lived, so a lock inside any worktree would serialise nobody. A held lock reports
  `infra_unavailable` with the holder's metadata and launches nothing; `--wait <secs>` bounds a
  queue. A run also refuses outright if the game is up on the Windows host.

- Evidence directories under `~/.arma-cti/runs/<UTC>-<probe>/`, outside every worktree, carrying
  the verdict, the logs, the daemon telemetry and the probe exactly as it was staged. Passes are
  pruned to the last three per probe.

- **Assault**, the fourth Order kind: close with the enemy Base and destroy its HQ structure —
  Decapitation as an Order (ADR-0020). Until now an Order could only name an Objective, so one of
  the two win conditions the MVP decided was unreachable through the only order path there is, by
  a human Commander and an AI alike. The Command Port accepts an Assault and rides it out on the
  outbox as an `order_issued` effect like any other Order; what the world does with one, and the
  AI Commander that scores a Base worth assaulting, are both below.

- **The AI Commander plays for both win conditions.** It now scores both Bases alongside the
  Objectives: the enemy's as an Assault, and its own as ground to garrison under the same fog rule
  that already had it covering its rear. Where it used to run out of ideas once the island was
  held, it now finishes the Campaign — and it will turn a Squad round for a company reported at
  its own HQ rather than march on and lose the game behind its back. The raid arrives late without
  any rule saying so: what defers it is the four and a half kilometres between the two Bases, so a
  Commander still opens by taking the ground that pays. What a Base is worth is one new number
  (`decapitation`), a playtest-tuned placeholder awaiting feel sign-off like the rest of them; no
  existing weight moved to make room for it.

- Defend now takes the side's **own Base** as well as any Objective, so rear security is something
  a Commander can order rather than hope for.

- **The world now acts on both**: an Assault sends the Squad at the enemy Base's HQ structure and
  the building comes down; a Defend on a side's own Base garrisons it. Until now an Order naming a
  Base was looked up among the Objectives alone, found no ground, and was logged and dropped. The
  Squad walks onto the HQ and is then set on it with the engine's Destroy waypoint, and a Squad
  standing at the HQ under an Assault brings it down in ninety seconds. **The means of destruction
  and the HQ's durability are playtest-tuned placeholders** in the sense ADR-0020 gives the word —
  the structure is the contract, and the numbers are the first thing a playtest will move. They
  are set, with their alternatives, in `addons/main/functions/fn_baseAssault.sqf`.

- An HQ that falls is recorded once, as an `hq_destroyed` telemetry row naming the Base, the side
  that lost it and the side that brought it down. Once per Base, deliberately: the MVP resolves a
  mutual Decapitation by which destruction came first in telemetry, and a second row for the same
  Base would make that a question of which report arrived rather than which HQ died. Any HQ death
  counts, not only an ordered one — the world reports the building's state rather than the
  Assault's outcome.

- One new rejection code, `wrong_ground`: ground the map has that this Order may not name —
  Capture(Base), Assault(Objective), Assault(own Base), Defend(enemy Base). An id the map does not
  have at all stays `malformed_command`, so a typo is not reported as a rules mistake.

- A manifest is refused if an Objective id collides with a Base id, naming the id. An Order names
  a Place of either kind, so one id answering to both is ground the port could not tell apart.

### Changed

- **Commanding authority is now an assignment rather than a uniform.** The gateway used to stamp
  the acting side from the side of the caller's own unit, which would have handed the Command Port
  to every rifleman on the island once players lead squads. It now reads the server's
  commander-assignment state: the person occupying a side's authored Commander slot, latched by
  player UID once per Play Session so respawn and reconnection do not change who commands. A
  machine with no assignment is refused `wrong_side` and told why.

- **A side has one Commander, whichever kind it is.** A Command arriving over the wire for a side
  already under an AI Commander is refused `wrong_side`, and that side's view is not handed out at
  all — the same rule that already refused a second AI brain on one side, arriving through the
  other door. Bring the world up without an AI on the side you mean to play.

- **The Order's ground field is `place`, not `objective`** — in the Command a Commander sends, in
  the `order_issued` effect, in the observation each Commander receives, and in the exported
  Command schema the game reads (`orders_needing_objective` is now `orders_needing_place`). It can
  hold an Objective id or a Base id, and a field named `objective` carrying a Base id would have
  been term drift baked into the wire — and, from Phase 2, into the campaign snapshot. Anything
  built against the old field name will need updating; nothing persisted holds it yet, which is
  why the rename is now.

- An in-world `FAIL` line's own `class=` is now believed. The harness called every in-mission
  failure `assertion_failed`, including the ones the world had explicitly typed `timeout` or
  `oracle_disagreement` — which sent the reader to fix code when the table said investigate
  synchronisation or suspect the capture layer.

- The game reads the authored map manifest itself, instead of a generated SQF copy of it. The
  engine has had a JSON parser since 2.18 and the server runs 2.20, so the addon ships
  `manifests/stratis.json` verbatim in its own PBO and parses it at mission start with `loadFile`
  and `fromJSON`. The generator, the generated file, its Functions Library entry and its freshness
  check are all gone. Before, the same eight Objectives existed twice and a check kept the copies
  honest; now there is one document, and them disagreeing is not a thing that can be expressed.
  The addon resolves its manifest from the world's name — world `Stratis` is `stratis.json` — and
  Python refuses a manifest whose filename the game could never find. See ADR-0017, which amends
  ADR-0012's generated-SQF clause and records what would overturn the decision.

- The Command Port schema is exported as JSON rather than rendered as SQF. The Command catalogue,
  the effect catalogue and the rejection codes live in Python and have no authored file to ship, so
  `just generate` and the `schema_stale` gate survive for that one export — but the hand-rolled SQF
  literals, quoting and all, do not.

### Fixed

- A Squad the world has never held is no longer treated as one it has lost. A Purchase is judged in
  the daemon and carried out in the game, and a report arriving between the two says nothing about
  the Squad on its way — reading that silence as a loss deleted it from the roster, so the group
  that spawned a moment later answered to an id nobody knew: a Squad no Commander could order and
  none counted, and a Commander short of its intended force bought another. A human Commander buys
  a few times a session and would have met this rarely; the AI Commander buys every five seconds.

- None of `targetsQuery`'s arguments can be relied on to select anything, and the Contact design
  was written as though all of them could. Three separate findings, each from an in-world probe
  run and none reachable from a unit test:
  - **The side argument ranks rather than filters.** Asking a NATO leader for east came back with
    seven of its own riflemen at accuracy 0.01 and no enemy on the list at all. The wiki says so
    in its first line — "targets, known to the enquirer (including own troops), where the accuracy
    coefficient reflects how close the result matches the query" — the arguments are query terms
    scored into the accuracy the results are sorted by, not a filter.
  - **The engine does not decay knowledge out of the query.** What decays after 120 s without
    sight is `knowsAbout`; `targetsQuery` goes on returning the memory with a growing age, 132 s
    after the observers had withdrawn 3 km. Unbounded, a leader standing on a place would report a
    ten-minute-old memory of men who had left, and observed absence — the only rule that clears a
    Contact — could never be observed.
  - **The max-age argument filters away targets in plain sight.** The obvious fix for the above
    broke it the other way: a target's age is documented as possibly negative, and a negative age
    does not survive the bound, so six men at 100 m came back as one — the only one the engine
    happened to report at a positive age.
  - So the query asks for the widest answer available and side and age are both selected again on
    what it actually returned. Sightings stay perceptions rather than ground truth: the side is the
    one the observer believes, so a man wrongly taken for the enemy is reported as one.

- The desync load generator is now asked for explicitly (`CTI_DESYNC_LOAD=1`) rather than running
  whenever a client turns up. It spawns thirty-two WEST soldiers standing on the first four
  Objectives, and capture is by presence — so with a headless client brought up on purpose for
  #17's topology it would hand WEST half the island on every run. #8's investigation asks for it;
  a Campaign never does.

- A probe is now waited for over the window the caller asked for, rather than a fixed three
  minutes. The client wait ends the moment a client connects, so a run with a headless client left
  the probe 180 s however long a window was requested — and a probe measuring a Squad marching
  does not fit in three minutes.

- The desync load generator no longer runs when no client turned up. It exists to give a joining
  client traffic to carry (issue #8), and it does that by spawning thirty-two WEST soldiers
  standing on the first four Objectives — which is fine as traffic and is not fine as a Campaign,
  because capture is by presence. Unattended, it was quietly handing WEST half the island four
  minutes into every held run. Found by the first probe to care what the map said it owned.

- None of `targetsQuery`'s arguments can be relied on to select anything, and the Contact design
  was written as though all of them could. Three separate findings, each from an in-world probe
  run and none reachable from a unit test:
  - **The side argument ranks rather than filters.** Asking a NATO leader for east came back with
    seven of its own riflemen at accuracy 0.01 and no enemy on the list at all. The wiki says so
    in its first line — "targets, known to the enquirer (including own troops), where the accuracy
    coefficient reflects how close the result matches the query" — the arguments are query terms
    scored into the accuracy the results are sorted by, not a filter.
  - **The engine does not decay knowledge out of the query.** What decays after 120 s without
    sight is `knowsAbout`; `targetsQuery` goes on returning the memory with a growing age, 132 s
    after the observers had withdrawn 3 km. Unbounded, a leader standing on a place would report a
    ten-minute-old memory of men who had left, and observed absence — the only rule that clears a
    Contact — could never be observed.
  - **The max-age argument filters away targets in plain sight.** The obvious fix for the above
    broke it the other way: a target's age is documented as possibly negative, and a negative age
    does not survive the bound, so six men at 100 m came back as one — the only one the engine
    happened to report at a positive age.
  - So the query asks for the widest answer available and side and age are both selected again on
    what it actually returned. Sightings stay perceptions rather than ground truth: the side is the
    one the observer believes, so a man wrongly taken for the enemy is reported as one.

### Added

- Founding decisions: domain glossary, ADRs, MVP scope, and the agent development process.
- `just` command surface: `check`, `unit`, `build`, `spike`, `probe`, `fast`. The no-Arma gate
  (`just check` + `just unit`) runs in under a second. `just probe <file>` brings the Phase-1
  world up and holds it with a probe from `spike/probes/` appended to its harness, and waits for
  that probe to finish — a probe still working when the hold window closes is a timeout rather
  than a pass nobody earned.
- Pinned toolchain: HEMTT, `just`, Rust with `cargo-xwin` for the Windows shim, and a
  `uv`-managed Python environment.
- HEMTT addon skeleton, with the "no bare `random` or `sleep` in SQF" contract enforced as a
  `banned_commands` lint rather than a grep.
- Rust extension shim on `arma-rs`, round-tripping opaque payloads to the Python daemon over TCP
  loopback and returning replies through `ExtensionCallback`.
- Mission PBO packer (`tools/pack_pbo.py`), since HEMTT packs addons but not missions.
- Phase-0 spike harness and its measurements: `docs/spikes/0001-phase0.md`.
- ADR-0011: the acceptance-harness architecture — Python orchestrator, in-game gtest-style SQF
  asserts, verdict returned through the extension as structured JSON. Bohemia's `-autotest` and
  SQF-VM are rejected as test tiers, with reasons recorded.
- ADR-0012: the Command Port wire format — a domain protocol carried inside the daemon's
  transport envelope, not the envelope itself. The daemon judges Commands against the Funds
  ledger, one whitelisted server-side gateway admits the human UI, and every world effect rides
  the outbox for both Commanders. `CONTEXT.md` gains **Command**.
- `CONTEXT.md` gains **Observation**: the whole strategic picture at one moment, as a Commander
  may know it. Distinct from the Campaign snapshot, which carries the same set of facts durably;
  an Observation is momentary and in memory.
- Fog of war is in the MVP, and `CONTEXT.md` gains **Contact** to name what a Commander learns
  through it. A Commander knows its own side in full; Objective ownership and Base HQ status are
  public, because the win conditions are the scoreboard rather than intelligence; everything else
  about the enemy arrives as Contacts — what that side's squad leaders actually saw, aggregated per
  place, carrying an echelon band, a posture, notable assets and an age. Enemy Funds, force count,
  Squad identity and standing Orders never cross. ADR-0012 amended: Commander symmetry covers
  knowing as well as commanding, and the AI Commander plays under the same fog, enforced by there
  being no unprojected picture for an in-process planner to read. Perfect information as a
  difficulty lever was considered and rejected — it makes "is the scorer any good" unanswerable.
- The return leg: every report the world makes is answered on the same call, so there is no second
  channel, no second cadence and no callback — which is why at-most-once callback delivery never
  arises for it. An **Observation** is what one Commander may know at one moment: which side holds
  each Objective including Contested, what that Commander has to spend, and each of its own Squads
  with its type, head count, standing Order and the Objective or Base it is standing on.
  Deliberately the set ADR-0008 persists and nothing it regenerates, so the Phase-2 snapshot
  schema is this shape rather than a second one. No exact positions, health, ammo or AI knowledge:
  a Commander reasons about places, not coordinates. Held in memory only.
  - Assembled rather than reported wholesale. Ownership, Funds and Orders are the daemon's own;
    the world contributes only the two facts nothing else can see — how many of a Squad are still
    standing, and where it is. A Squad the world stops reporting has been wiped out, and the
    roster says so rather than letting it linger.
  - One side only, and structurally so: Funds are a number rather than a table keyed by side, a
    Squad view carries no side, and no call hands out the whole map's Squads. There is no
    unprojected picture to obtain, which is what makes the fog hold against a planner that reads
    campaign state in-process rather than over the wire. The server, which is not a Commander,
    takes ownership alone — enough to paint its markers and nothing else.
  - A crowded Stratis (every Objective owned, sixteen Squads a side) encodes to 1,932 bytes
    against the engine's 10,240-byte `callExtension` return cap — 8,308 bytes of headroom, about
    107 bytes a Squad, so roughly 90 Squads a side would fit. The server's own reply is 222 bytes.
    Every reply's size is recorded in telemetry, and the game fails the run at nine tenths of the
    cap, because the engine truncates a longer return in silence and the fix is a smaller
    observation rather than a chunking protocol invented in passing.
  - Telemetry carries each side's picture whenever it moves and not otherwise, so tailing it shows
    the moment ownership or Funds changed instead of a hundred rows saying they had not. A row per
    side, because there is no picture carrying both to write.
- **Contacts**: a Commander now learns something of the enemy, and only what its own squad
  leaders saw. One Contact per place rather than per enemy Squad — an Objective or Base, carrying
  an echelon band (`team` 1–3, `squad` 4–8, `platoon` 9–24, `company` 25+) read off the *observed*
  count, a posture from the heaviest vehicle seen, any notable assets, and how long ago it was
  seen. Seeing three of eight reports a team, so a Commander is left under-informed rather than
  over-, and several Squads in one place read as a platoon without naming which ones. A Contact
  carries no enemy Squad id and no Order, and cannot: the sighting it is made of never had one.
  - The engine's own knowledge model is the source, through `targetsQuery` — shared instantly
    within a group, decaying to nothing after 120 s without sight. No visibility rule of ours, and
    no correcting it against ground truth: what a leader made out is what gets reported, so an
    unrecognised contact is honestly unidentified. Classification is `BIS_fnc_objectType`'s own
    vocabulary rather than a table of ours. Armour and air are out of MVP, so `foot` and
    `motorised`, `AT` and `MG` are what the game can currently produce; the rest of the vocabulary
    is defined so the schema does not churn when Phase 4 adds vehicles.
  - Memory is keyed by place, so it is bounded by the island — ten entries on Stratis — and needs
    no ageing rule: a newer sighting supersedes an older one. The one removal rule is that
    **observing a place and finding no enemy clears its Contact**. Absence of contact is not
    evidence; observed absence is. So a Contact outlives the engine forgetting it, with its age
    growing, which is what a Commander planning at the strategic level needs.
  - A crowded Stratis now encodes to 2,939 bytes against the 10,240-byte cap — 7,301 bytes of
    headroom, about 99 bytes a Contact. Contacts are bounded by the map rather than by enemy force
    size, so ten is the ceiling however much the enemy buys. The server's public reply is
    unchanged at 222 bytes and carries no Contacts at all.
  - Measured in-world at the cadence it runs: one `targetsQuery` per squad leader costs 0.0097 ms
    with 13 targets known, or 0.31 ms across the 32 leaders a full Campaign fields, against a
    report every 5 s. The whole sampler is 0.35 ms with two leaders. The wiki's CPU-intensive
    warning is real but nowhere near this scale, so the cadence stands as designed and no
    sampling-versus-frequency trade needed making.
- An **AI Commander** for one side: start the daemon with `--ai-side WEST` and leave it, and that
  side buys Squads, sends them at ground it does not hold, garrisons what is coming under attack,
  and reacts as Objectives change hands. It plays through the same Command Port a human does and
  has no other way in, so the port stays the one thing #19 has to audit.
  - A seeded deterministic utility scorer over the Objective adjacency graph, as a pure function of
    one Observation and the authored map and price table. It returns the Commands it would issue
    and the trace explaining them; writing that trace is the daemon's job, because a function that
    logs is no longer a pure one. The same seed and the same reports produce the same Orders, which
    is property-tested rather than asserted.
  - It plans under the fog, structurally: an Observation is the only input, and there is no
    unprojected one to reach for. So it sees banded, aged Contacts and no enemy roster, and weighs
    staleness — a company seen ten minutes ago stops deciding anything. Ground nobody is looking at
    is scored as holding a team rather than as empty, and a Contact nobody has refreshed decays to
    that same floor rather than to nothing, so old knowledge becomes ignorance instead of good
    news.
  - Every decision reaches telemetry with what was scored, what won and why, each candidate broken
    into its named terms — income, contested, threat, travel, commitment, jitter. Observability
    only (ADR-0003): taking the log away entirely changes nothing about the Campaign, which is how
    that is tested.
  - A Squad keeps going where it was sent unless something beats it by a margin, so two Objectives
    whose scores cross and recross do not turn into countermarching. An unchanged world produces no
    second round of Orders at all.
  - It presses. Two Commanders both sitting on what they hold is not a Campaign worth playing, so
    the weights advance by preference and consolidate only against a real massed incursion: a Squad
    on the line attacks a fresh Contact of any echelon across it, and turns round only for a
    company standing on ground behind it. The first set of weights held at every echelon — and
    went on holding with the threat terms set to zero, because the turtle was never the threat
    terms. Marching cost more per kilometre than an Objective was worth, and a standing Order was
    worth half an Objective on its own, so a Squad that reached the line stopped there.
  - It buys the cheapest Squad it can afford, up to one per Objective the map has: ground is taken
    by standing in a capture radius, so what wins is the number of Squads rather than what each
    carries. A threat-aware purchase is left for when the scorer has a threat model worth spending
    against.
  - The interface is one method — an Observation in, a Plan out — so the HTN escalation ADR-0004
    names, or a post-MVP LLM Commander, changes neither the port nor the trace format. Held by a
    test that drives the daemon with a planner that scores nothing at all.
  - It plays for Domination and not Decapitation: an Order names an Objective and a Base is not
    one, so the port has no way to say "go for the enemy HQ" and neither has this. That is the
    port's vocabulary to widen rather than something for a scorer to route around.
- **Both sides under an AI Commander at once**: start the daemon with `--ai WEST:1 --ai EAST:4`,
  walk away, and come back to two AI sides having fought over Stratis. One planner instance per
  side, each seeded separately, on the dedicated-server-plus-headless-client topology.
  - Neither Commander can see or spend the other's state, and structurally rather than by a guard:
    the only input a planner has is its own side's Observation, there is no call that assembles one
    carrying both sides, and the ledger is keyed by side.
  - Every Command reaching the port is written down against the Commander that issued it, accepted
    ones included, carrying both the issuer and the side the Command named — the pair `wrong_side`
    exists to distinguish. A Command issued for the other side is refused and attributed. Requests
    arriving over the wire carry the same column, so a human Commander's Command is attributable
    the same way an AI's is.
  - Two decision traces share one log and stay separable: every Commander-caused row carries its
    side, and filtering to one side never turns up the other's Squads.
  - The same pair of seeds replays the same Campaign — ownership, Funds, rosters, standing Orders,
    the outbox and the whole decision trace. Commanders play in a fixed side order rather than in
    the order a session registered them, so the replay does not depend on bring-up order.
  - `just probe spike/probes/two-commanders.sqf` with `CTI_HOLD_HC=1` runs it unattended in-world
    and asserts what only appears at two: both sides fielding a force nobody ordered, neither side
    sending two Squads to one Objective, neither side sitting still, neither side's force growing
    without a ceiling, and the push path never reaching the engine's hundred-drains-a-frame cap.
- The push path's budget is measured and recorded by the run itself rather than estimated. The
  effect pump counts what each drain carried and how many frames it spanned, and
  `tools/push_path_report.py` turns a run's telemetry into `results.env` numbers: the largest
  single handover against the 100-per-frame drain cap, and the worst blocking `observe` — which is
  where both planners run — against ADR-0005's 1000 ms stall cap. Measurements from the first
  two-sided unattended run are in `docs/spikes/0002-two-commanders.md`.
- ADR-0015: two Commanders in one daemon — a planner apiece, a fixed turn order, and a pair of
  seeds as the Campaign's identity. Both sides run the same weights, differing only by seed;
  asymmetric weights as a difficulty lever are rejected for the MVP, because they make "is the
  scorer any good" unanswerable in the same way perfect information does.
- Squads take **Orders**, and an Order is standing rather than a waypoint consumed and forgotten.
  A Commander tells one Squad to Capture an Objective, Defend one, or fall back into Reserve, and
  the three are distinct in the world: Capture searches the ground it is sent to, Defend goes
  there and stays, Reserve walks home and holds its fire. The Order outlives the leader who was
  carrying it — waypoints belong to the group, so the engine promotes a replacement and the Squad
  carries on — and a sweep re-asserts it once the engine considers the waypoint finished, so a
  Squad that chased a contact off its Objective goes back. Ordering a Capture on ground your own
  side already holds is refused with a reason rather than accepted as a no-op.
- A bought Squad gets an id its Commander can say out loud (`WEST-1`), counted up per side so a
  resumed campaign mints the same ids in the same order. The Purchase reply carries it, so a
  Squad can be ordered the moment it is bought.
- A player-led Squad is told its Order rather than made to follow it: the engine's own task
  framework puts it in the diary of whoever is in that group, with the ground as its destination.
  Compliance stays voluntary.
- `tools/port_demo.py` issues Orders as well as Purchases, and the Arma tier can boot the Phase-1
  world against `spike/phase1.cfg` with a one-off in-world probe appended to its harness.
- Objectives change hands by presence and pay income. A side alone in the capture radius takes an
  Objective after a held interval; both sides present makes it **Contested**, which is a real
  state that interrupts a capture, shows its own colour on the map and pays nobody. Every 60
  in-game seconds each side is paid the sum over the Objectives it owns plus a flat stipend, so no
  side can be economically locked out. The rules live in the daemon and are unit-tested there; the
  world only reports who is standing where.
- Income accrues in in-game seconds, so it stops when the Play Session does without anything
  having to know what a session is. A report arriving late still pays every tick it covers, and
  time stepping backwards is a mission restart rather than a refund.
- Command Port, in-world side: a single server-side gateway is the only function a client may
  `remoteExec`, with `CfgRemoteExec` locked to mode 1 on **both** `Functions` and `Commands` —
  a mission that locks only `Functions` leaves the whole scripting-command surface open. The
  gateway stamps the commanding side from the caller's own identity and overwrites whatever the
  client claimed. Accepted effects ride the outbox and a server-side pump applies them and
  acknowledges only what it carried out, so a failed effect is redelivered rather than lost.
- SQF speaks the Command format through constructors generated from the same Python source the
  daemon validates with, so the two cannot drift. `toJSON`/`fromJSON` (engine-native since 2.18)
  carry it, which means no hand-rolled JSON encoder and no escaping bugs.
- `tools/port_demo.py` issues Commands to a running daemon the way the AI Commander will.
- Command Port, daemon side: one schema source defines Commands and the effects they produce, the
  daemon is the sole validator, and a single entry function is the only thing that moves strategic
  state. Purchase spends Funds from a per-side ledger, queues its Squad-spawn effect on the outbox
  rather than returning it, and reports only the remaining balance. Insufficient Funds, an unknown
  Command, a malformed Command and commanding a side that is not yours are four distinct typed
  rejections — as against an unknown *transport* verb or an unparseable line, which stay errors.
- Squad prices, the starting balance and the stipend are authored in `config/economy.json`, so
  playtest tuning is an edit rather than a code change.
- Addon functions are declared in `CfgFunctions` and resolve by name as `cti_fnc_*` — from the
  mission, from `remoteExec` and from the addon itself. Verified on the dedicated server, which
  now loads the addon during the Arma tier.
- The Arma tier can drive a real player client end to end with nobody at the keyboard: it
  connects, takes a role and enters the mission by itself. `skipLobby = 1` does the work, because
  the server initialises its own mission before any client connects and there is therefore a
  running mission to be dropped into. No input injection, and no focus taken from other windows.
- Mechanical desync oracle for the open Windows-client desync (#8). The server samples every
  connected client's `networkInfo` and reports the worst reading over a window, so "a client stays
  responsive for a sustained period" is a number rather than a recollection. No client in the
  window is reported as `no_client`, never as steady. The Arma tier can also launch on engine
  defaults instead of the hand-written `basic.cfg`, which is candidate cause 2 on that issue.
- Stratis map manifest: eight Objectives with stable authored IDs, capture radii and an adjacency
  graph, plus both Bases and the HQ structure each would lose to Decapitation. Positions are the
  engine's own, read out of `CfgWorlds`, not eyeballed off the map. Authored once as JSON, read by
  Python directly and by SQF through a generated HashMap, so the two cannot drift.
- Manifests are validated before they can reach a Play Session: ID shape, capture radius, income,
  one Base per side, distinct HQ structures, and the adjacency graph the AI Commander will reason
  over — every edge mutual, every Objective reachable from a Base. A stale generated file fails
  `just check` as `schema_stale`.
- Phase-1 Stratis mission, thin per ADR-0007: two Commander slots, the named `HeadlessClient_F`
  slot, the two Base HQ structures, and nothing else. The addon builds the world from the
  manifest — every Objective marked with its owner, Neutral at boot, both Bases visible — and
  refuses to build at all rather than booting a half-built world.
- The Arma tier takes a mission, a server config and a log prefix, so it can boot the Phase-1
  world as well as the phase-0 spike. The Phase-1 server config keeps `localClient[]` to loopback:
  the LAN address the spike config carries there is candidate cause 1 on the open desync (#8).
- Real daemon (`cti-daemon`), replacing the phase-0 echo stub. Same transport the spike measured —
  newline-delimited JSON on TCP loopback, one connection reused across calls — with an envelope
  worth relying on: every request carries an id and every reply echoes it, and success, a
  domain-level rejection and an error are three outcomes the caller can tell apart. A malformed
  line costs one reply, never the connection.
- Acknowledged delivery for messages the daemon pushes to the game. Callback delivery is
  at-most-once across mission boundaries (ADR-0005), so the daemon holds each pushed message until
  the game acknowledges its sequence number and replays anything unacknowledged. Acknowledging
  twice is ordinary; acknowledging a sequence that was never issued is refused.
- Structured daemon telemetry as JSON lines, per request. Observability only, never read back as
  campaign state (ADR-0003) — which is why a failure to write it is swallowed rather than raised.
- Seeded PRNG adapter: the only sanctioned source of randomness in SQF. It wraps the engine's own
  `seed random x` rather than a hand-rolled generator, and hides both of that command's silent
  footguns — a seed truncated towards zero, and an upper bound that is included where plain
  `random`'s is excluded. A stream is `[seed, draw count]`, so it survives a snapshot and resumes
  where it left off. Determinism, both footguns, the integer range and serial independence are
  asserted against the live engine, not assumed.

### Changed

- ADR-0006 is now accepted unconditionally: the phase-0 contingency is discharged, and the ADR
  absorbs the spike's constraints (port range 2402–2406, missions as PBOs, no RPT file on a Linux
  server) plus a version-parity policy for when Arma 2.22 ships.
- ADR-0004 and ADR-0005 amended with measured constraints: the shim keeps one persistent TCP
  connection (~3× faster than per-call connects), and nothing in the Command Port may require
  sub-frame push latency, because `ExtensionCallback` is frame-bound at 8–17 ms.
- ADR-0005 and ADR-0008 amended with the Observation's delivery decision: the strategic picture is
  pull-only on the synchronous path, because an Observation is *state* — losing one costs nothing,
  since the next report supersedes it — where an effect is an *event* and must ride the outbox's
  acknowledgement and replay. Consequences recorded: the daemon can never volunteer a picture, so
  freshness is the report interval; the whole picture must fit one 10,240-byte return; and delta
  observations are rejected, because a delta is an event and would drag the callback path back in.
  ADR-0008 records that the Observation is the snapshot's set minus the save-only fields, so a
  planner is tested against the schema that survives a resume.
- ADR-0004, ADR-0005 and ADR-0006 amended with engine limits found by cross-referencing phase 0
  against the full wiki snapshot: a `callExtension` return is capped at 10,240 bytes (chunking
  needed before snapshot save/load), a blocking call stalls the frame and warns at 1000 ms, the
  callback path drains at most 100 messages per frame and is at-most-once across mission
  boundaries, and 2.22 changes the extension error surface — prime `engine_drift` suspect on
  update.

- `just` command table in `CLAUDE.md` now lists the recipes that exist; the acceptance tiers are
  marked as Phase 1 work.
- *Read first* in `CLAUDE.md` now explains how to navigate the wiki snapshot: guessable paths,
  `MANIFEST.json` as the lookup, per-directory `INDEX.md` instead of listing a 2,672-file
  directory, and the two traps — categories live in the file header rather than the wikitext, and
  pre-Arma-3-only pages are excluded, so a miss is not proof the wiki lacks the page.
- Vendored snapshot of the Bohemia wiki (`docs/reference/arma-wiki/`), because the live wiki is
  unreachable from this project's environment and Arma 3 has been static at 2.20 for over a year.
  Now the whole wiki rather than nine hand-picked pages: 6,690 pages across scripting commands,
  functions, engine topics, class-name tables and the templates needed to read `{{RV}}` markup.
  Pages are bucketed by subject at predictable paths (`commands/setDamage.wiki`), each carries its
  categories in the header — they are template-generated, so grepping the wikitext finds none —
  and `MANIFEST.json` is the authoritative title-to-file lookup plus the redirect alias map.
- Lint-after-edit hook enabled for SQF, config and Rust edits — advisory only; `just check`
  remains the gate.
- The "no bare `random`" contract is now enforced by `tools/check_sqf_bans.py`, which allows the
  command in the seeded PRNG adapter and nowhere else. HEMTT's `banned_commands` lint is
  all-or-nothing and HEMTT 1.20.1 has no file-scoped suppression, so `random` is exempted there
  and re-banned here with the scope the contract actually wants. `sleep` and `uiSleep` stay banned
  by both.

### Removed

- Phase-0 stub daemon and its test. It echoed requests with timestamps and had no request
  identity, error vocabulary or delivery guarantees; the real daemon supersedes it.

### Fixed

- The shim's round-trip benchmark was timing requests the daemon never understood: it built its
  own payload, left over from when the daemon was an echo stub that accepted anything, and every
  spike run left about a hundred `malformed_request` records in telemetry. The payload now comes
  from the caller, which is also the shape ADR-0005 asks for — the shim has no business knowing
  what the daemon accepts.
- A headless client never entered the mission: its `HeadlessClient_F` slot had no `name`, and an
  unnamed slot is never assigned.
- The auto-format hook ran `rustfmt` at edition 2021 against an edition 2024 crate, so it wrote
  files that `cargo fmt --check` then rejected.
- The scoped SQF ban gate descended into nested agent worktrees under `.claude/worktrees/`,
  where every copy of the PRNG adapter fails the path-based allowlist, so `just check` broke in
  the main checkout whenever a worktree existed. `.claude` is now excluded; each worktree runs
  the gate on its own tree.
