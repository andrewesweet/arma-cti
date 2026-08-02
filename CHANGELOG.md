# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

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
  bought anything: Stratis costs 1,631 bytes of a 9,216-byte budget and carries 70 Squads a side,
  a forty-Objective island carries 24, and a sixty-Objective one does not fit **empty**. The budget
  is therefore checked per map rather than per roster (ADR-0030). Nothing in MVP changes — one map
  ships, and it has five and a half times the headroom it needs.

- **A Contact's age is reported to a tenth of a second.** It was arriving as
  `47.29999999999927`, seventeen characters of binary-subtraction noise on a field carried once per
  place, read downstream as a freshness ratio against a window of minutes. Worth 8% of a large
  island's Observation and no precision anything could use.

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
