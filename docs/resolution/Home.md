# DCS Resolution guide

DCS Resolution is a fork of [DCS Retribution](https://github.com/dcs-retribution/dcs-retribution)
that turns it into a **living air war**. An AI commander on each side plans a realistic air
campaign by its own doctrine, from its own intelligence. Every turn is six hours of that war,
fought by a combat model whether or not DCS is running. The DCS mission is the slice of the war
around your flight.

These pages cover what Resolution adds or changes. For everything it inherits (campaigns,
factions, the ATO editor, plugins), see [Retribution's wiki](https://github.com/dcs-retribution/dcs-retribution/wiki).

## Coming from Retribution

The things that will surprise you first:

* **Begin Campaign** asks for H-hour, the strategic surprise and pre-war reconnaissance, and
  opens the war with a cruise missile salvo. See [The opening](Playing-a-Turn.md#the-opening).
* **Your squadrons start with their aircraft.** Nothing is bought at turn 0. Pick a real air
  wing from a [preset](Air-Wing-Presets.md).
* **The ATO is six hours long and you didn't make it.** The commander did, and it offers you a
  flight from it on the **Your flight** card. See [Your seat](Playing-a-Turn.md#your-seat).
* **The mission starts at your flight,** not at a window you pick. Everything before it has
  already been fought. See [The DCS window](Playing-a-Turn.md#the-dcs-window).
* **Not every package is in DCS.** Only the ones you are likely to meet. See
  [The bubble](Playing-a-Turn.md#the-bubble).
* **The map only shows what blue has found.** See [Fog of war](Intelligence.md#fog-of-war-on-the-map).
* **Shot-down pilots wait for a rescue.** See [CSAR](CSAR.md).

To play closer to Retribution, set **Mission only** on, choose the legacy planner per side, and
turn fog of war off.

## The war

* [Playing a turn](Playing-a-Turn.md): the six hour turn, the opening, road bases, your seat,
  the DCS window, the bubble, after the mission, and reading the ATO and its timeline. **Start
  here.**
* [The commanders](Air-Campaign-Planner.md): how each side's commander plans: phases, the
  target list, apportionment, threat-scaled packages, risk, doctrines, IADS management, GCI and
  buying aircraft.
* [The combat model](Combat-Model.md): how fast forward fights air-to-air, SAMs, strikes, the
  front lines, fuel and aircrew, force quality, and the after-action report.
* [Intelligence, fog of war and morale](Intelligence.md): each side's picture of the enemy,
  satellites and agencies, decoys, IADS health, morale, war-weariness and collateral damage.
* [Fire missions](Fire-Missions.md): Tomahawk, Scud and artillery strikes every turn.

## Aircrew, helicopters and bases

* [Combat Search and Rescue](CSAR.md): downed pilots wait on the map for several turns until
  they are rescued, captured or listed as missing. Includes the [Rescue King](CSAR.md#rescue-king).
* [Dynamic FARPs](Dynamic-FARPs.md): build forward helicopter bases and station detachments at
  them.
* [On Station start](On-Station-Start.md): flights start in the air at their racetrack or IP.

## Air wings and aircraft

* [Air wing presets](Air-Wing-Presets.md): deploy a real air wing by base, on any theater.
* [Loadout editor](Loadout-Editor.md): payload names, station labels and weapon menus match the
  mission editor.
* [UH-60L Armed Blackhawk](Armed-Blackhawk.md): the Armed Blackhawk submod and the ANDR0ID
  Weapon Pack.
* [Super Hornet](Super-Hornet.md): fixes for the CJS Super Hornet mod, including v2.4.6.

## Other pages

* [Installing and building](Installing-and-Building.md)
* [Resolution changelog](Changelog.md)

## Where to find the settings

Retribution's settings window is split into pages, and each page into sections. Resolution's
options go into the existing pages. The settings window's search box finds any of them by
title or description.

| Page | Section | Resolution options |
|---|---|---|
| Campaign Management | HQ Automation | Air campaign planner per side, automatic package planning behavior, Mission only and its lead-in and package guidance, ATO period length, the bubble and its package guidance, acceptable attrition override |
| Campaign Management | Pilots and Squadrons | CSAR on/off per side, survival turns, recovery turns, capture and resolution radii, pilot survival chance, grouping nearby pilots |
| Campaign Management | Dynamic FARPs | FARPs on/off (also needed for the Rescue King), costs, upkeep, capacity, limit, distance from the front |
| Campaign Management | Flight Planner Automation | Single-helicopter CSAR packages |
| Campaign Doctrine | General | Maximum CSAR flights per side each turn |
| Campaign Doctrine | Intelligence, morale and electronic warfare | Intelligence, fog of war, satellites and agencies, intelligence strength, deception, morale, war-weariness, rules of engagement, collateral damage, strategic surprise, opening missile strikes, road bases, fire missions, commander plans your fire missions, limited missile stocks |
| Mission Generator | Gameplay | Resolve combat when fast forwarding by, combat model lethality, historical force quality, front-line battles and their round length, "On Station" in the default start types, CSAR start type, hover or landing extraction, rescuing AI pilots, player hover height and distance, cabin door requirement |
| Cheat Menu | | Enable Instant FARP Cheat |
| New Game wizard | Mods | UH-60L Armed Blackhawk |
| New Game wizard | Air Wing Setup | Presets by base, Advanced editor…, your squadron and mission preference |
| Plugins | | GCI ground alert scrambles, Parking cleanup |
