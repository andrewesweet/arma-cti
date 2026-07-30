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
- AI Commander for both sides: prioritise objectives, buy squads, order capture/defend.
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
