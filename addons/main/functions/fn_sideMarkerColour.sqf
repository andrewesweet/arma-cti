/*
 * Author: arma-cti
 * Marker colour for an Objective or Base owner.
 *
 * Owners are the manifest's own side strings plus the two states an Objective
 * can be in that no side holds, so nothing here needs a translation table.
 *
 * Arguments:
 * 0: owner <STRING> — "WEST", "EAST", "NEUTRAL" or "CONTESTED"
 *
 * Return Value: CfgMarkerColors class name <STRING>
 */
params [["_owner", "NEUTRAL", [""]]];

switch (toUpper _owner) do {
    case "WEST": { "ColorWEST" };
    case "EAST": { "ColorEAST" };
    // Contested reads as "being fought over" rather than "nobody's", so it gets
    // its own colour instead of sharing Neutral's.
    case "CONTESTED": { "ColorOrange" };
    default { "ColorGrey" };
};
