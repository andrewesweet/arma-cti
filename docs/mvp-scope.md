# MVP scope

Decided 2026-07-30 (grilling session). Session-based persistent campaign ([ADR-0001](adr/0001-session-based-campaign.md)), greenfield core ([ADR-0002](adr/0002-greenfield-core-component-reuse.md)).

## In

- One map: Stratis. Two vanilla factions: NATO, CSAT.
- Fixed pre-placed main base per side. No construction.
- ~6–10 town objectives, capture by presence (sector-control style).
- Income from held towns; Commander spends on infantry squads and transport.
- Economy structure (numbers are playtest-tuned placeholders; structure is contract):
  - Per-Objective `income` value authored in manifest; tick every 60 in-game s pays each side the sum over owned Objectives. Contested pays nobody.
  - Small flat stipend per side per tick (no total lockout; campaigns stay recoverable).
  - Income accrues only during a Play Session.
  - Squad prices in one config table: rifle squad base, weapons ~1.5x, transport +flat premium. Reinforce = missing fraction x price x ~0.8 discount. Starting Funds ~3 squads. No upkeep, refunds, or selling.
  - Placeholders: income 10/obj/min, stipend 5/min, rifle 100, weapons 150, transport +50, start 300.
  - **Basic motorised transport is free and always available**, and does not touch the table above.
    Human decision, 2026-08-03 (#170): "I find yomping repeatedly to targets to be boring gameplay.
    I think squad leaders (or AI commander on behalf of squad leaders) should be able to access the
    weakest, most basic form of motorised transport sufficient for their squad size for free at all
    times. A civilian open truck perhaps?" Every Squad standing at its own Base is issued one, sized
    to the Squad, costing no Funds and asked for by nobody ([ADR-0059](adr/0059-a-free-ride-is-issued-not-asked-for-and-crosses-no-wire.md)).
    The two do not collide: the free one is a bare unarmed **civilian** vehicle the Squad drives
    itself, and the priced `transport` Squad type is a crewed military transport asset — what +50
    buys is the crew and the asset, not the ability to travel. The priced type is unauthored in
    `config/economy.json` today and is #6's to fill.
- AI Commander for both sides: prioritise objectives, buy squads, order capture/defend.
- Fog of war at the strategic layer (decided 2026-07-31, grilling session; issues #27 and the
  Contact-report issue it blocks). A Commander knows its own side in full — Squads, Orders, Funds.
  Public to both: Objective ownership including Contested, and each Base's HQ intact or destroyed,
  because the two win conditions are the scoreboard rather than intelligence. Everything else
  about the enemy arrives as **Contacts**: what that side's squad leaders have actually seen,
  aggregated per Objective or Base, carrying an echelon band, a posture, notable assets and an
  age. Enemy Funds, force count, Squad identity and standing Orders never cross. The AI Commander
  plays under the same fog as the human, enforced structurally — the daemon exposes only a
  per-side projection, so an in-process planner cannot read past it.
  - Deliberately deferred, not overlooked: reports are instantaneous and perfectly transmitted
    (no radio range, delay or jamming), and exact-position-with-age is used rather than the
    engine's perceived-position-with-error.
- Player roles, both first-class: Commander (map UI orders) or squad leader (leads one squad).
- Player respawn (MUST — player death must not end the game).
- Win, either of:
  - **Domination**: own every Objective simultaneously, sustained 10 in-game minutes within one Play Session (timer not persisted, resets on boot).
  - **Decapitation**: enemy Base HQ structure (manifest-referenced single building) destroyed. Simultaneous mutual destruction: first destruction event in telemetry order wins, deterministic.
  - On victory: Campaign marked complete, end screen with summary from telemetry, archived; fresh Campaign next session. No draw condition.
- Campaign persists between Play Sessions.
- Test topology: dedicated server + headless client from early on. No human-client acceptance tier.

## Out (post-MVP)

- Base building / construction.
- Armour and air entirely (not merely priced out).
- Medical, fatigue, logistics systems; squad-member revive.
- Additional maps (manifest format designed for it; one authored).
- Human multiplayer acceptance testing (architecture stays MP-clean).
- Mid-session Commander takeover — a person taking over a side an AI Commander is playing, or
  Commander hot-swap between players. Human decision, 2026-08-02, on #126: "Very much a desired
  long-term feature. Even hot swapping between players (with elections, evictions, and voting)
  will be desired, but not for MVP." Command stays a bring-up-time assignment (ADR-0025); joining
  a saved Campaign as Commander needs no takeover, only bringing the world up with that side free.
