[![Logo](https://github.com/dcs-retribution/dcs-retribution/raw/main/resources/ui/splash_screen.png)](https://github.com/AbhayPratapSingh2607/dcs-resolution)

(Banner and splash screen artwork by Andriy Dankovych, CC BY-SA 4.0)

# DCS Resolution

**A living air war for DCS World, where you fly as one cog in the machine.**

DCS Resolution is a fork of [DCS Retribution](https://github.com/dcs-retribution/dcs-retribution),
the turn-based dynamic campaign generator. Retribution builds a mission around you. Resolution
fights a whole war and puts you in it.

On each side an AI commander plans a full air campaign by its own doctrine, from its own
intelligence. Every turn is six hours of that war for both sides. A combat model fights it
whether or not DCS is running. The DCS mission is the slice of the war around your flight.

> Resolution is an unofficial fork. Report problems with Resolution
> [here](https://github.com/AbhayPratapSingh2607/dcs-resolution/issues), not on Retribution's tracker.

## How it differs from Retribution

| | Retribution | Resolution |
|---|---|---|
| **A turn** | One mission. The ATO is built to fill it. | Six hours of air war for both sides. You fly part of it, and the combat model fights the rest, before, during and after your mission. |
| **The planner** | A priority list of tasks that fill the mission. | A commander for each side that plans by doctrine: Desert Storm-style phases for the West, massed raids for Russia and the Soviets, homeland defense for client states. It plans routine lines, strike waves and a main push. |
| **What the AI knows** | Everything. | Only what its own radars, satellites, agents, pilots and reconnaissance have found. Battle damage assessment can be wrong, and decoys fool it. |
| **Fast forward** | Coin flips, or pause and fly. | A combat model built from sensors, weapons, pilot skill, weather, fuel and doctrine, calibrated against Desert Storm, Allied Force, Linebacker II and Yom Kippur. |
| **Your place** | The mission is built around you. | You get a flight from the commander's real plan, matched to your preferred squadron or mission. The plan doesn't bend for you. |
| **The DCS mission** | Every flight in the ATO window. | The flights you are likely to meet (the "bubble"). The rest of the war is fought in the combat model over the same time. |
| **Campaign start** | Buy an air wing. | Deploy a real air wing from a preset, choose H-hour and how surprised the enemy is, and open the war with a cruise missile salvo. |
| **Downed pilots** | Killed, or back at base. | Down on the map, waiting for a rescue for a few turns. |
| **Helicopters** | Fly from airfields and FARPs in the campaign file. | You can also build FARPs near the front and stage rescue helicopters under a C-130 orbit. |

Everything Retribution does still works. You can turn most of Resolution off and play it like
Retribution: **Mission only** turns, the legacy planner, fog of war off.

## What Resolution adds

### The war

| Feature | What it does | Guide |
|---|---|---|
| **The 6 hour turn** | Each turn is six hours of air war. The mission starts when your flight does. Everything earlier has already been fought, and everything after is fought when you quit. | [Playing a turn](docs/resolution/Playing-a-Turn.md) |
| **Air campaign commanders** | Doctrine-driven planners for Western, Russian, Soviet, client-state and irregular air forces. They work through phases, a target list with BDA, apportionment, threat-scaled packages, a risk limit, GCI scrambles and IADS management. | [The commanders](docs/resolution/Air-Campaign-Planner.md) |
| **Combat model** | Fast forward fights it out. It models air-to-air, SAMs, strikes, the front lines, fuel and tankers, and what happens to each crew that goes down. An after-action report tells the story. | [Combat model](docs/resolution/Combat-Model.md) |
| **Intelligence and fog of war** | Each side has its own picture of the enemy, built from radars, satellites, agencies and reconnaissance. Morale, war-weariness, decoys, rules of engagement and collateral damage are modelled too. | [Intelligence](docs/resolution/Intelligence.md) |
| **The opening** | Pick H-hour, the opening emphasis and the strategic surprise. Reconnoitre before the war, fire the opening cruise missile salvo, and watch the enemy react. | [The opening](docs/resolution/Playing-a-Turn.md#the-opening) |
| **Fire missions** | Tomahawk, Scud and artillery strikes every turn, from campaign magazines. Planned from the map or the timeline. | [Fire missions](docs/resolution/Fire-Missions.md) |
| **Road bases** | An enemy whose runways are cratered keeps flying part of its force from road strips. | [Road bases](docs/resolution/Playing-a-Turn.md#road-bases) |

### Aircrew, helicopters and bases

| Feature | What it does | Guide |
|---|---|---|
| **Turn-based CSAR** | Shot-down pilots survive on the map for a few turns. You or the AI fly rescues before they go missing or are captured. | [CSAR](docs/resolution/CSAR.md) |
| **Rescue King** | Place a C-130 orbit outside enemy air defenses. Two CSAR helicopters stage under it for the turn. | [Rescue King](docs/resolution/CSAR.md#rescue-king) |
| **Dynamic FARPs** | Build Wet Wing (C-130) or Fat Cow (CH-47) FARPs near the front and station helicopter detachments there. Sites are checked against terrain, towns and the front. | [Dynamic FARPs](docs/resolution/Dynamic-FARPs.md) |
| **On Station start** | A start type that puts a flight in the air at its racetrack or IP, so AWACS, tankers and CAP are on station when the mission begins. | [On Station start](docs/resolution/On-Station-Start.md) |

### Air wings and aircraft

| Feature | What it does | Guide |
|---|---|---|
| **Air wing presets** | Deploy a real air wing by base: carrier air wings from 1975 to 2020, Marine ARGs, USAF expeditionary wings, NATO, Soviet and Russian air forces, plus presets made from every faction's aircraft. | [Air wing presets](docs/resolution/Air-Wing-Presets.md) |
| **Loadout editor** | Payloads and stations use the DCS mission editor's names, and each station's weapons are sorted into category submenus. | [Loadout editor](docs/resolution/Loadout-Editor.md) |
| **UH-60L Armed Blackhawk** | Support for the Armed Blackhawk submod and the ANDR0ID Weapon Pack. | [Armed Blackhawk](docs/resolution/Armed-Blackhawk.md) |
| **Super Hornet** | Works with CJS Super Hornet v2.4.6, with current weapon names and callsign fixes. | [Super Hornet](docs/resolution/Super-Hornet.md) |

The full list of changes is in the [Resolution changelog](docs/resolution/Changelog.md). The
complete guide starts at [docs/resolution](docs/resolution/Home.md).

## Saves and compatibility

* Campaigns started in Retribution open in Resolution. New fields are added when they load. A
  campaign keeps the turn model it was saved with.
* Campaigns saved in Resolution are **not** guaranteed to open in Retribution. They contain data
  Retribution doesn't know about, such as downed pilots, FARPs, intelligence pictures and fire
  missions. Back up your saves before switching.
* No campaign file needs changing. Off-map bases in a campaign host strategic bomber
  detachments where one is defined.

## Getting Resolution

* **Build from source:** see [Installing and building](docs/resolution/Installing-and-Building.md).
  It covers running from source and building the standalone `retribution_main.exe`.
* **Releases:** packaged builds are posted on the
  [Releases page](https://github.com/AbhayPratapSingh2607/dcs-resolution/releases) when available.

## About DCS Retribution

DCS Retribution was forked in 2022 from [DCS Liberation](https://github.com/dcs-liberation/dcs_liberation).
Both are turn-based single-player or co-op dynamic campaigns for DCS World. They are external
programs that generate full, complex DCS missions and manage a persistent combat environment.
Resolution builds on everything they do.

![Screenshot](https://user-images.githubusercontent.com/315852/120939254-0b4a9f80-c6cc-11eb-82f5-ce3f8d714bfe.png)

For everything Resolution inherits (campaigns, factions, the ATO editor, plugins), see
[Retribution's wiki](https://github.com/dcs-retribution/dcs-retribution/wiki/), their
[Discord](https://discord.gg/b4x34Bg4We) and [Liberation's wiki](https://github.com/dcs-liberation/dcs_liberation/wiki/).
Retribution's own changes are in its [changelog](changelog.md).

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
