# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
