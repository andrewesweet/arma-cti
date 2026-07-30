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
