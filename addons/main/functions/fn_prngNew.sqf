/*
 * Author: arma-cti
 * Creates a seeded pseudo-random stream. A stream is the only sanctioned source
 * of randomness in SQF (CLAUDE.md contract); every draw goes through
 * cti_fnc_prngNext, which is the one file allowed to name `random`.
 *
 * The engine truncates a seed to an integer *towards zero* — -0.9, -0.1, 0.1
 * and 0.9 all read as 0 (commands/random.wiki, syntax 3). Normalising it here
 * means a caller that computes a seed sees the same stream whether the value
 * arrives as 7 or 7.9, rather than discovering the truncation in gameplay.
 * `floor` is the wrong tool below zero — it would send -0.9 to -1 and pick a
 * different stream from the one the engine uses — so the sign decides.
 *
 * A stream is [base seed, draw counter] — two integers, so it serialises into a
 * snapshot (ADR-0003) and resumes at the same position rather than restarting.
 *
 * Arguments:
 * 0: seed <NUMBER>
 * 1: draw counter to resume from <NUMBER> (optional, default 0)
 *
 * Return Value: stream <ARRAY>
 */
params [["_seed", 0, [0]], ["_draw", 0, [0]]];

private _truncate = { [floor _this, ceil _this] select (_this < 0) };

[_seed call _truncate, _draw call _truncate]
