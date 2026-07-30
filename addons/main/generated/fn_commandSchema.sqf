// Generated from src/cti_daemon/commands.py and config/economy.json by
// tools/generate_command_sqf.py. Do not edit by hand: change the source
// and run `just generate`.
/*
 * Author: arma-cti (generated)
 * The Command Port schema, as SQF sees it: which Commands exist and what
 * each needs, which sides command, which Orders a Squad can be given, the
 * rejection codes the daemon can return, and the Squad price table for
 * display.
 *
 * Read through cti_fnc_command rather than called directly.
 *
 * Arguments: none
 *
 * Return Value: schema <HASHMAP>
 */
createHashMapFromArray [
    ["commands", createHashMapFromArray [
        ["purchase", ["squad_type"]],
        ["order", ["squad", "order", "objective"]]
    ]],
    ["effects", createHashMapFromArray [
        ["squad_spawned", ["squad", "squad_type", "size"]],
        ["order_issued", ["squad", "order", "objective"]],
        ["objective_captured", ["objective"]]
    ]],
    ["sides", ["WEST", "EAST"]],
    ["orders", ["capture", "defend", "reserve"]],
    ["orders_needing_objective", ["capture", "defend"]],
    ["rejection_codes", ["already_held", "insufficient_funds", "malformed_command", "unknown_command", "unknown_squad", "wrong_side"]],
    ["starting_funds", 300],
    ["squads", createHashMapFromArray [
        ["rifle", createHashMapFromArray [
                ["display_name", "Rifle Squad"],
                ["price", 100],
                ["size", 8]
            ]],
        ["weapons", createHashMapFromArray [
                ["display_name", "Weapons Squad"],
                ["price", 150],
                ["size", 8]
            ]]
    ]]
]
