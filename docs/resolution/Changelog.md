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
