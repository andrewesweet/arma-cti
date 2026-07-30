# Persist strategic state, regenerate tactical state

The campaign snapshot persists only strategic state: Objective ownership, Funds, Squads (side, composition type, member count, Order, coarse position as Objective/Base reference), Base alive/destroyed, campaign clock, player role/loadout/squad. Everything tactical is regenerated at session boot: exact positions, health, ammo, AI knowledge, vehicle damage, corpses, building damage, weather, capture-in-progress (Contested resets to prior owner). This makes resume fidelity testable against a closed schema and eliminates the open-ended capture-fidelity risk from the original design doc.

Accepted consequence: mid-firefight quit-and-resume heals units and resets contests (save-scumming possible) — fine for personal use.

Forward compatibility is a requirement, not an accident: the snapshot schema is versioned with migration tests, so later fidelity additions (vehicle damage states, per-unit health/ammo) are additive schema migrations, never redesigns. New fields must default sensibly when absent from old saves.
