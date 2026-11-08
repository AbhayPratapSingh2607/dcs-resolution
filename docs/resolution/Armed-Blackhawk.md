# UH-60L Armed Blackhawk

Resolution supports the **Armed Blackhawk** submod (v7.1.4) for the UH-60L mod, together with the
**ANDR0ID Weapon Pack**.

## Requirements

* The UH-60L mod (v2.1.5), with the Armed Blackhawk submod and the ANDR0ID Weapon Pack installed in DCS.
* In the **New Game** wizard's mod options, tick both **UH-60L Black Hawk (v2.1.5)** and
  **UH-60L Armed Blackhawk (v7.1.4 + ANDR0ID Weapon Pack)**.

## What you get

The UH-60L and the MH-60L DAP stay the same aircraft types in the campaign. The submod adds stations
and stores to them:

* **Station 8 (ARMED BLACKHAWK)** selects the airframe: MH-60J/K/R/S, HH-60G, MH-60G, MH-60M and
  others. You choose it like any other store.
* **Station 9 (ESSS)** carries the stub wings.
* Every station gets the submod's stores, including 32 from the ANDR0ID Weapon Pack.
* The submod's own payloads, such as "MH-60R Seahawk", appear as normal loadouts.
* The pack's Hellfire and APKWS launchers have been added to Retribution's weapon groups. The AI
  therefore knows their type and introduction year, and which weapons to fall back to when they
  aren't available.

## Loadout rules

The submod requires some stores to go together. For example, the Seahawk's tanks need the MH-60R
airframe and no stub wings. Resolution applies these rules in two places:

* **In the loadout editor:** loading a store also loads the stores it needs, and emptying a station
  removes the stores that depended on it. See [Loadout editor](Loadout-Editor.md).
* **At mission generation:** stores that another airframe needs (such as the Seahawk tanks or
  sonobuoys) are dropped. Payloads made for the base mod, which removed the stub wings with
  `<CLEAN>` on stations 1/2/6/7, are moved to the submod's station 9.

## Turning it off

If the option is off, the extra stations and rules are removed and the submod's payloads are
hidden, so the UH-60L works exactly as it does in Retribution.
