# DCS Resolution guide

DCS Resolution is a fork of [DCS Retribution](https://github.com/dcs-retribution/dcs-retribution).
These pages cover only what Resolution adds. For everything else (campaigns, the ATO, factions,
plugins), see [Retribution's wiki](https://github.com/dcs-retribution/dcs-retribution/wiki).

## Features

* [Combat Search and Rescue (CSAR)](CSAR.md): downed pilots stay on the map for several turns
  until they are rescued, captured or listed as missing.
* [Dynamic FARPs](Dynamic-FARPs.md): you build forward helicopter bases and station detachments at them.
* [Loadout editor](Loadout-Editor.md): payload names, station labels and weapon menus match the
  mission editor.
* [UH-60L Armed Blackhawk](Armed-Blackhawk.md): support for the Armed Blackhawk submod and the
  ANDR0ID Weapon Pack.
* [Super Hornet](Super-Hornet.md): fixes for the CJS Super Hornet mod, including v2.4.6.
* [On Station start](On-Station-Start.md): flights start in the air at their racetrack or IP,
  so AWACS, tankers and CAP can be on station when the mission begins.

## Other pages

* [Installing and building](Installing-and-Building.md)
* [Resolution changelog](Changelog.md)

## Where to find the settings

Retribution's settings window is split into pages, and each page is split into sections.
Resolution's options go into existing pages:

| Page | Section | Resolution options |
|---|---|---|
| Campaign Management | Pilots and Squadrons | CSAR on/off per side, survival turns, recovery turns, capture and resolution radii, pilot survival chance, grouping nearby pilots |
| Campaign Management | Dynamic FARPs | FARPs on/off, costs, upkeep, capacity, limit, distance from the front |
| Campaign Management | Flight Planner Automation | Single-helicopter CSAR packages |
| Campaign Doctrine | General | Maximum CSAR flights per side each turn |
| Mission Generator | Gameplay | "On Station" in the default start types, CSAR start type, hover or landing extraction, rescuing AI pilots, player hover height and distance, cabin door requirement |
| Cheat Menu | | Enable Instant FARP Cheat |
| New Game wizard | Mods | UH-60L Armed Blackhawk |
