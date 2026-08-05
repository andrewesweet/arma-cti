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
            class loopRegister {};
            class loopWatch {};
            class everyInterval {};
            class requestId {};
            class prngNew {};
            class prngNext {};
            class prngInt {};
            class prngSelect {};
            class prngSelfTest {};
            class manifestLoad {};
            class commandSchema {};
            class sideVocabulary {};
            class sideMarkerColour {};
            class worldInit {};
            class networkSample {};
            class desyncWatch {};
            class command {};
            class commanderAssign {};
            class commanderSide {};
            class commanderView {};
            class leaderSquad {};
            class portGateway {};
            class portReply {};
            class mapObservation {};
            class mapCommander {};
            class mapSelect {};
            class mapRender {};
            class mapVerbs {};
            class mapIssue {};
            class viewEvents {};
            class notify {};
            class effectApply {};
            class effectPump {};
            class reportObject {};
            class presenceSample {};
            class loadoutCatalogue {};
            class loadoutAtBase {};
            class loadoutMenu {};
            class loadoutWatch {};
            class loadoutSample {};
            class transportCatalogue {};
            class transportIssue {};
            class transportWatch {};
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

// The Commander's event channel (#176), in the shape Arma's own singleplayer
// task notifications take (topics/Arma_3_Notification.wiki): the two moments
// playtest 0001 said arrive silently, shown by cti_fnc_notify through
// BIS_fnc_showNotification, which draws with or without the map open. Here
// rather than in a mission's description.ext because every rule lives in the
// addon (ADR-0007) and both missions inherit configFile's templates.
//
// ---- playtest-tuned placeholder (ADR-0020) --------------------------------
// Wording, icon, colour and priority are feel, not rules. "wiped" is the
// playtest response's own word; CONTEXT.md has no term for a Squad at zero yet
// and the issue routes that to /domain-modeling rather than settling it here.
class CfgNotifications
{
    // %1 the Place, %2 its new owner, %3 the owner it had. "now %2" rather
    // than "taken by %2" because the owner vocabulary includes NEUTRAL and
    // CONTESTED, and a town nobody took can still stop being yours.
    class cti_PlaceTaken
    {
        title = "%1 — now %2";
        iconPicture = "\A3\ui_f\data\map\mapcontrol\taskIcon_ca.paa";
        description = "was %3";
        priority = 7;
    };

    // %1 the Squad's id.
    class cti_SquadWiped
    {
        title = "Squad %1 wiped";
        iconPicture = "\A3\ui_f\data\map\mapcontrol\taskIcon_ca.paa";
        description = "%1 has no men left standing";
        color[] = {0.9, 0.4, 0.4, 1};
        priority = 7;
    };
};
