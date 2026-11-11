[![Logo](https://github.com/dcs-retribution/dcs-retribution/raw/main/resources/ui/splash_screen.png)](https://github.com/AbhayPratapSingh2607/dcs-retribution/tree/Resolution)

(Banner and splash screen artwork by Andriy Dankovych, CC BY-SA 4.0)

# DCS Resolution

**DCS Resolution** is a fork of [DCS Retribution](https://github.com/dcs-retribution/dcs-retribution),
the turn-based dynamic campaign generator for [DCS World](https://www.digitalcombatsimulator.com/en/products/world/).
It keeps everything Retribution does and adds things it doesn't have yet. Downed aircrew become
part of the campaign. Helicopters can operate from forward bases you build yourself. Modded
aircraft get loadout tools that work the way the DCS mission editor does.

Resolution tracks Retribution's `dev` branch. Each feature lives on its own branch so it can be
offered upstream as a separate pull request, and the `Resolution` branch combines all of them into
one build.

> Resolution is an unofficial fork. Please report problems with Resolution-only features
> [here](https://github.com/AbhayPratapSingh2607/dcs-retribution/issues), not on Retribution's tracker.

## What Resolution adds to Retribution

| Feature | What it does | Guide |
|---|---|---|
| **Turn-based CSAR** | Shot-down pilots survive on the map for a few turns. You (or the AI) fly rescue missions to bring them home before they go missing or are captured. | [Combat Search and Rescue](docs/resolution/CSAR.md) |
| **Dynamic FARPs** | Build your own Forward Arming and Refuelling Points near the front. A transport flies the equipment in, and then you station helicopter detachments there. | [Dynamic FARPs](docs/resolution/Dynamic-FARPs.md) |
| **Mission editor-style loadout editor** | Payloads and stations show the names the DCS mission editor uses, and each station's weapons are sorted into category submenus. | [Loadout editor](docs/resolution/Loadout-Editor.md) |
| **UH-60L Armed Blackhawk** | Supports the Armed Blackhawk submod and the ANDR0ID Weapon Pack: MH-60R/S, HH-60G, MH-60M and other airframes, the ESSS stub wings, and 32 extra stores. The submod's loadout rules are applied. | [Armed Blackhawk](docs/resolution/Armed-Blackhawk.md) |
| **On Station start** | A new start type: the flight appears in the air at its station, the racetrack for CAP, AWACS and tankers or the IP for attack packages. Support assets can be on station when the mission starts, as they would be in reality. | [On Station start](docs/resolution/On-Station-Start.md) |
| **Air wing presets** | Set up a whole air wing in one click: US Navy carrier air wings from 1975 to 2020, USMC amphibious ready groups, USAF expeditionary forces, a NATO coalition, or Soviet and Russian air forces. Works on any theater, and the aircraft are bought from the starting budget. | [Air wing presets](docs/resolution/Air-Wing-Presets.md) |
| **Super Hornet fixes** | Works with CJS Super Hornet v2.4.6 payload files. Includes up-to-date weapon names, callsign fixes and mission editor station labels. | [Super Hornet](docs/resolution/Super-Hornet.md) |

The full list of Resolution's changes is in the [Resolution changelog](docs/resolution/Changelog.md).
For everything Resolution inherits from Retribution, see Retribution's [changelog](changelog.md).

### At a glance

**CSAR.** When an aircraft goes down, the pilot appears on the map as a parachute icon showing how
many turns are left to rescue them. Right-click the icon to plan a CSAR package, or let the
auto-planner do it. AI helicopters either hover and winch the survivor aboard or land and let them
walk over. If you fly the rescue yourself, MOOSE Ops.CSAR provides beacons, smoke and an F10 menu.
Pilots you rescue spend a few turns recovering. Pilots you don't rescue go missing in action, or
they are taken prisoner and freed when you capture the base holding them.

**Dynamic FARPs.** Turn the feature on in the settings, and **Wet Wing** and **Fat Cow** buttons
appear in the top bar. Choose one, then move the cursor over friendly ground near the front. The map
checks each spot (terrain, nearby towns, distance from the front, money, available transports) and
tells you why a spot won't work. Click to order the FARP. Next turn a C-130 airdrops the equipment or
a CH-47 lands it. Then you station helicopters at the FARP from its base menu. You pay upkeep every
turn. If the front line moves past the FARP, it is lost.

**Loadouts.** Payloads appear under their mission editor labels (for example
"USN Adv. Extended Range CAP" instead of "AIM-9X\*2, AIM-120C\*2, FUEL\*1"). Stations use the
mod's own labels, so a Super Hornet's cheek station reads `5 | 4`. Each station's weapon list opens as
submenus: AA missiles, AG missiles, guided bombs, bombs, rockets, fuel tanks and pods.

## Saves and compatibility

* Campaigns started in Retribution can be opened in Resolution. New fields are added to old saves
  when they load.
* Campaigns saved in Resolution are **not** guaranteed to open in Retribution, because they contain
  data Retribution doesn't know about, such as downed pilots and FARPs. Back up your saves before
  switching.
* CSAR (for either side), dynamic FARPs and the Armed Blackhawk can each be turned off. Dynamic
  FARPs and the Armed Blackhawk are off by default.

## Getting Resolution

* **Build:** See [Installing and building](docs/resolution/Installing-and-Building.md). The guide
  covers both running from source and building the standalone `retribution_main.exe`.
* **Releases:** Packaged builds are posted on the
  [Releases page](https://github.com/AbhayPratapSingh2607/dcs-retribution/releases) when available.

The full Resolution guide is in [`docs/resolution`](docs/resolution/Home.md).

## About DCS Retribution

DCS Retribution was forked in 2022 from [DCS Liberation](https://github.com/dcs-liberation/dcs_liberation).
Both are turn-based single-player or co-op dynamic campaigns for DCS World. They are external
programs that generate full, complex DCS missions and manage a persistent combat environment.

![Screenshot](https://user-images.githubusercontent.com/315852/120939254-0b4a9f80-c6cc-11eb-82f5-ce3f8d714bfe.png)

General Retribution help is in [Retribution's wiki](https://github.com/dcs-retribution/dcs-retribution/wiki/)
and on their [Discord](https://discord.gg/b4x34Bg4We). Some historical information is in
[Liberation's wiki](https://github.com/dcs-liberation/dcs_liberation/wiki/). It covers campaigns,
the ATO, factions, plugins, and anything else this page doesn't.

## Special thanks

Resolution exists because of the DCS Retribution team and contributors. Credit also goes to shdwp,
who started the original DCS Liberation project. The turn-based CSAR feature began as
[Retribution PR #929](https://github.com/dcs-retribution/dcs-retribution/pull/929).

DCS Liberation, Retribution and Resolution use [pydcs](https://github.com/pydcs/dcs) for mission
generation. They also use the [Mist](https://github.com/mrSkortch/MissionScriptingTools) and
[MOOSE](https://github.com/FlightControl-Master/MOOSE) Lua frameworks for mission scripting.
Resolution's CSAR is built on MOOSE's Ops.CSAR.

Lua scripts used as plugins:

* Ciribob's [JTAC Autolase](https://github.com/ciribob/DCS-JTACAutoLaze) for the JTAC feature.
* Walder's [Skynet-IADS](https://github.com/walder/Skynet-IADS) for integrated air defense systems.
* Carsten's [Arty Spotter](https://www.digitalcombatsimulator.com/en/files/3339128/).
* MBot's [Call Artillery Script](https://forum.dcs.world/topic/310506-call-artillery-script/) for artillery fire missions using in-map artillery and forward observers.

Thanks also to the mod authors whose aircraft Resolution supports: the CJS Super Hornet team, the
UH-60L team, and the authors of the Armed Blackhawk submod and the ANDR0ID Weapon Pack.

Please support these projects too!
