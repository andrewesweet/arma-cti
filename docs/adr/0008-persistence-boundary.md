# Persist strategic state, regenerate tactical state

The campaign snapshot persists only strategic state: Objective ownership, Funds, Squads (side, composition type, member count, Order, coarse position as Objective/Base reference), Base alive/destroyed, campaign clock, player role/loadout/squad. Everything tactical is regenerated at session boot: exact positions, health, ammo, AI knowledge, vehicle damage, corpses, building damage, weather, capture-in-progress (Contested resets to prior owner). This makes resume fidelity testable against a closed schema and eliminates the open-ended capture-fidelity risk from the original design doc.

Accepted consequence: mid-firefight quit-and-resume heals units and resets contests (save-scumming possible) — fine for personal use.

Amended 2026-07-31 (#15): the **Observation** (`CONTEXT.md`) carries this same set, minus what only a save needs — Base alive/destroyed and player role/loadout arrive with Phase 2. That is deliberate rather than convenient: a planner tested against the Observation schema is tested against the one that survives a resume, so "does the AI Commander still make sense after a reload" is a property of the schema rather than a thing to discover. The two stay separate words. An Observation is momentary and held only in memory; a snapshot is durable. When Phase 2 arrives, the snapshot is expected to be this shape plus the save-only fields, not a second design.

Forward compatibility is a requirement, not an accident: the snapshot schema is versioned with migration tests, so later fidelity additions (vehicle damage states, per-unit health/ammo) are additive schema migrations, never redesigns. New fields must default sensibly when absent from old saves.
