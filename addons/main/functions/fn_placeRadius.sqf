/*
 * Author: arma-cti
 * How close counts as being at one Place. Runs anywhere.
 *
 * An Objective carries an authored capture radius, because standing inside it
 * is the whole capture rule. A Base carries none — it is never captured, only
 * lost to Decapitation (ADR-0020) — so a fixed radius stands in for being at
 * one. One reading of that number, because two would be two answers to whether
 * a Squad is standing in its own Base.
 *
 * Arguments:
 * 0: a manifest Place <HASHMAP> — an Objective or a Base
 *
 * Return Value: <NUMBER> metres
 */
params [["_place", createHashMap, [createHashMap]]];

// The Base radius is a playtest-tuned placeholder in the sense ADR-0020 gives
// the word: wide enough to cover the buildings a Base is made of, narrow enough
// not to swallow the ground around it. Authored radii win where they exist.
_place getOrDefault ["capture_radius", 150]
