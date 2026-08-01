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
            class daemonCall {};
            class campaignLost {};
            class prngNew {};
            class prngNext {};
            class prngInt {};
            class prngSelect {};
            class prngSelfTest {};
            class manifestLoad {};
            class commandSchema {};
            class sideMarkerColour {};
            class worldInit {};
            class networkSample {};
            class desyncWatch {};
            class desyncLoad {};
            class command {};
            class commanderAssign {};
            class commanderSide {};
            class commanderView {};
            class portGateway {};
            class portReply {};
            class mapObservation {};
            class mapCommander {};
            class mapRender {};
            class mapVerbs {};
            class mapIssue {};
            class effectApply {};
            class effectPump {};
            class presenceSample {};
            class placeOf {};
            class placePosition {};
            class placeRadius {};
            class squadSample {};
            class contactSample {};
            class hqSample {};
            class casualtyWatch {};
            class casualtySample {};
            class presenceReport {};
            class objectiveOwnerSet {};
            class orderApply {};
            class orderEnforce {};
            class baseAssault {};
            class campaignEnd {};
        };

        // No generated class any more (ADR-0017). The map manifests ship as the
        // authored JSON under manifests/ and the Command Port schema is
        // exported as JSON under generated/; both are read with loadFile +
        // fromJSON at the point of use, so neither is a function to declare.
    };
};
