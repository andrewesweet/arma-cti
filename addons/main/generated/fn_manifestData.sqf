// Generated from manifests/*.json by tools/generate_manifest_sqf.py.
// Do not edit by hand: change the JSON and run `just generate`.
/*
 * Author: arma-cti (generated)
 * Every authored map manifest, keyed by map id. Read through
 * cti_fnc_manifestLoad rather than called directly.
 *
 * Arguments: none
 *
 * Return Value: maps <HASHMAP>
 */
createHashMapFromArray [
    ["stratis", createHashMapFromArray [
        ["id", "stratis"],
        ["world", "Stratis"],
        ["display_name", "Stratis"],
        ["bases", [
            createHashMapFromArray [
                ["id", "nato_airbase"],
                ["side", "WEST"],
                ["display_name", "Stratis Air Base"],
                ["position", [1987.31, 5625.9]],
                ["hq", "cti_hq_west"],
                ["adjacent", ["agia_marina", "camp_tempest"]]
            ],
            createHashMapFromArray [
                ["id", "csat_kamino"],
                ["side", "EAST"],
                ["display_name", "Kamino Firing Range"],
                ["position", [6401.97, 5427.13]],
                ["hq", "cti_hq_east"],
                ["adjacent", ["camp_rogain"]]
            ]
        ]],
        ["objectives", [
            createHashMapFromArray [
                ["id", "agia_marina"],
                ["display_name", "Agia Marina"],
                ["position", [2915.2, 6164.52]],
                ["capture_radius", 200],
                ["income", 10],
                ["adjacent", ["camp_tempest", "air_station", "lz_baldy", "camp_rogain"]]
            ],
            createHashMapFromArray [
                ["id", "camp_tempest"],
                ["display_name", "Camp Tempest"],
                ["position", [1941.68, 3556.72]],
                ["capture_radius", 121],
                ["income", 10],
                ["adjacent", ["agia_marina", "girna", "camp_maxwell"]]
            ],
            createHashMapFromArray [
                ["id", "girna"],
                ["display_name", "Girna"],
                ["position", [1935.28, 2722.61]],
                ["capture_radius", 77],
                ["income", 10],
                ["adjacent", ["camp_tempest", "camp_maxwell"]]
            ],
            createHashMapFromArray [
                ["id", "camp_maxwell"],
                ["display_name", "Camp Maxwell"],
                ["position", [3252.96, 2984.3]],
                ["capture_radius", 121],
                ["income", 10],
                ["adjacent", ["girna", "camp_tempest", "air_station"]]
            ],
            createHashMapFromArray [
                ["id", "air_station"],
                ["display_name", "Air Station Mike-26"],
                ["position", [4278.85, 3855.6]],
                ["capture_radius", 151],
                ["income", 10],
                ["adjacent", ["camp_maxwell", "old_outpost", "agia_marina"]]
            ],
            createHashMapFromArray [
                ["id", "old_outpost"],
                ["display_name", "Old Outpost"],
                ["position", [4318.72, 4398.14]],
                ["capture_radius", 121],
                ["income", 10],
                ["adjacent", ["air_station", "lz_baldy"]]
            ],
            createHashMapFromArray [
                ["id", "lz_baldy"],
                ["display_name", "LZ Baldy"],
                ["position", [4604.3, 5284.43]],
                ["capture_radius", 146],
                ["income", 10],
                ["adjacent", ["old_outpost", "camp_rogain", "agia_marina"]]
            ],
            createHashMapFromArray [
                ["id", "camp_rogain"],
                ["display_name", "Camp Rogain"],
                ["position", [4886.45, 5948.26]],
                ["capture_radius", 96],
                ["income", 10],
                ["adjacent", ["lz_baldy", "agia_marina"]]
            ]
        ]]
    ]]
]
