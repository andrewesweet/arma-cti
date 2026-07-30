#include "script_version.hpp"

#define QUOTE(var) #var
#define VERSION_STR MAJOR.MINOR.PATCHLVL.BUILD

class CfgPatches
{
    class cti_main
    {
        name = "Arma CTI - main";
        author = "Andrew Sweet";
        url = "https://github.com/andrewesweet/arma-cti";
        units[] = {};
        weapons[] = {};
        requiredVersion = 2.2;
        requiredAddons[] = {"A3_Data_F"};
        version = QUOTE(VERSION_STR);
        versionAr[] = {MAJOR,MINOR,PATCHLVL,BUILD};
    };
};

// Functions Library declaration. Every function becomes cti_fnc_<name>,
// compiled at mission start on every machine that loads the addon, so SQF is
// addressable by name from the mission, from remoteExec and from the addon
// itself (topics/Arma_3_Functions_Library.wiki).
//
// <ROOT> for an addon config is the *game* root, so `file` must carry the PBO
// prefix in full (addons/main/$PBOPREFIX$). Each entry loads
// <file>\fn_<name>.sqf.
class CfgFunctions
{
    class cti
    {
        class main
        {
            file = "cti\addons\main\functions";
            class shimName {};
            class prngNew {};
            class prngNext {};
            class prngInt {};
            class prngSelect {};
            class prngSelfTest {};
            class manifestLoad {};
            class sideMarkerColour {};
            class worldInit {};
            class networkSample {};
            class desyncWatch {};
            class desyncLoad {};
            class command {};
            class portGateway {};
            class portReply {};
            class effectApply {};
            class effectPump {};
            class presenceSample {};
            class presenceReport {};
            class objectiveOwnerSet {};
            class orderApply {};
            class orderEnforce {};
        };

        // Written by tools/generate_manifest_sqf.py from manifests/*.json.
        // Never hand-edited; `just check` fails stale output as schema_stale.
        class generated
        {
            file = "cti\addons\main\generated";
            class manifestData {};
            class commandSchema {};
        };
    };
};
