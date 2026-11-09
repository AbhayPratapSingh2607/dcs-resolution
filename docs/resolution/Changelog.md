# Resolution changelog

Changes in Resolution on top of DCS Retribution. Retribution's own changes are listed in the main
[changelog](../../changelog.md).

## Features

* **[CSAR]** Turn-based combat search and rescue. Downed pilots appear on the map and survive for a
  set number of turns. AI and player helicopters can rescue them, with hover or landing extraction
  for the AI and MOOSE Ops.CSAR for players. Unrescued pilots go missing in action or are taken
  prisoner, and prisoners are freed when their base is retaken. Rescued pilots recover for a few
  turns. Pilots who come down near a base are resolved automatically. Nearby pilots can be collected
  by one flight. Rescues and captures are listed in the debriefing, and the settings cover each part
  of the system. (Retribution PR #929) [Guide](CSAR.md)
* **[FARPs]** Dynamic FARPs. Place Wet Wing (C-130) or Fat Cow (CH-47) FARPs on friendly ground near
  the front from the top bar, with live site checks on the map. A transport delivers the equipment
  in the mission. Helicopter detachments fly in from their parent squadrons and can be recalled.
  FARPs cost upkeep. They are lost if they are overrun or their fuel is destroyed, and you get a
  warning when the front gets close. Terrain grids are included for 13 theaters, and there is an
  instant-FARP cheat. [Guide](Dynamic-FARPs.md)
* **[Loadouts]** Payloads are listed by their mission editor label. Payload editor stations use
  mission editor station labels, and each station's weapons are sorted into category submenus.
  [Guide](Loadout-Editor.md)
* **[Modding]** Support for the UH-60L Armed Blackhawk submod (v7.1.4) and the ANDR0ID Weapon Pack.
  Airframe selection, ESSS stub wings, 32 extra stores, and the submod's loadout rules are applied
  in the editor and at mission generation. [Guide](Armed-Blackhawk.md)
* **[Flight Planning]** New start type: **On Station**. The flight appears in the air at its
  station: the start of the racetrack for CAP, AWACS and tankers, the IP for attack packages. It
  appears at its planned time there, or at mission start with ASAP. Support assets no longer need
  a fast-forward to be on station. [Guide](On-Station-Start.md)
* **[Auto Planner]** Doctrine-driven air campaign planner (Western JFACC). Each turn is planned as
  one 6 hour air tasking order:
  * Desert Storm style campaign phases with a DEFENSE override.
  * A prioritized target list from detected targets only, with desired effects and uncertain BDA.
  * Sortie apportionment by phase, with mission-capable rates, turnaround and second sorties.
  * Packages sized to the threat on the planned route, weaponeering with night and weather
    gates, and an estimated-attrition limit fitted to the combat model.
  * Continuous AEW&C, tanker, CAP and HVAA CAP lines, QRA ground alert, CAS vul windows sized to
    the desired effect from each flight's loadout, kill boxes, and Phase IV air assault.

  Before take off you pick which window of the period to fly in DCS. The combat model fights
  what comes before and after it. Western factions use the planner by default, and the legacy
  planner can be chosen per side. The planner buys aircraft through a request for forces: the
  shortfalls that limited the plan first, then replacements for squadrons below strength. The
  Intelligence window has a new Air campaign page.
  [Guide](Air-Campaign-Planner.md)
* **[Campaign AI]** The planner keeps 4 CSAR helicopters owned or on order and buys them before
  any other aircraft, so pilots who go down can be rescued.
* **[Campaign AI]** The planner keeps a theater tanker track and carrier recovery tankers going
  according to its doctrine. The "Automatic Theater tanker package planning" setting now only
  affects the legacy planner.
* **[UI]** The package list is easier to read:
  * Packages are grouped by mission category, with coloured headers and counts, and sorted by TOT.
  * Category chips hide or show each group.
  * Rows give the purpose, the composition, the TOT and its offset into the period, and badges for
    players, the DCS window, missing pilots and estimated risk.
  * Flight rows show each flight's role and key times.

  A new **ATO timeline** window (Timeline button, or View menu) shows the whole period as a Gantt
  chart, with relief chains in one lane and the DCS window shaded. The DCS window picker shows the
  same timeline. [Guide](Air-Campaign-Planner.md#reading-the-ato)

## Fixes

* **[New Game]** Creating a campaign from a script no longer fails because the "squadrons start
  full" option wasn't passed to the generator.

* **[Modding]** Creating Super Hornet flights with CJS Super Hornet v2.4.6 no longer fails with
  "could not convert string to float". Local constants used as pylon keys in Lua payload files are
  now resolved. [Details](Super-Hornet.md)
* **[Modding]** Super Hornet pylon weapons use the current pydcs weapon identifiers.
* **[Modding]** Fixed the Super Hornets' malformed callsign table.
* **[Flight Planning]** Passing the turn no longer fails with "Could not plan AEW&C ... is outside
  the navmesh" when a base is deep inside the enemy's threat zone. The AEW&C orbit is pulled back
  until it can be reached, and a package that still can't be planned is scrubbed. This is also
  offered upstream on branch `aewc-navmesh-fix`.
