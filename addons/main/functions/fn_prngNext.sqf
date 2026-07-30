/*
 * Author: arma-cti
 * Draws the next value from a seeded stream and advances the stream.
 *
 * This is the only file in the codebase permitted to name `random`: the ban
 * exists so that every draw is reproducible, and this adapter is what makes it
 * so. Anything else needing randomness calls this, cti_fnc_prngInt or
 * cti_fnc_prngSelect. HEMTT 1.20.1 has no file-scoped lint suppression, so the
 * scoping lives in tools/check_sqf_bans.py, which allows the token here and
 * nowhere else; see the note in .hemtt/project.toml.
 *
 * Engine contract (commands/random.wiki, syntax 3, engine-native since 1.68 —
 * deliberately not a hand-rolled generator):
 *   - `seed random x` returns a Number from 0 (included) to x (INCLUDED).
 *     Plain `random x` excludes its upper bound; this one does not. Integer
 *     draws therefore go through cti_fnc_prngInt rather than `floor`.
 *   - the seed truncates to an integer towards zero; cti_fnc_prngNew normalises
 *     it, so the base seed reaching this file is already whole.
 *
 * The stream advances by incrementing the draw counter, not by feeding a drawn
 * value back in as the next seed: consecutive seeds cannot collapse into a
 * fixed point or a short cycle, and the stream stays two integers wide.
 *
 * Arguments:
 * 0: stream <ARRAY> — advanced in place
 * 1: upper bound, included <NUMBER> (optional, default 1)
 *
 * Return Value: <NUMBER> from 0 to the upper bound, both included
 */
params [["_stream", [0, 0], [[]], 2], ["_max", 1, [0]]];
_stream params ["_base", "_draw"];

_stream set [1, _draw + 1];

(_base + _draw) random _max
