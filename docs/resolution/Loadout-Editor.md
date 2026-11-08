# Loadout editor

Resolution's loadout screens use the same names and layout as the DCS mission editor, so a payload
you know from the editor is easy to find. There is nothing to turn on. These changes apply to every
aircraft that provides the data.

## Payloads listed by their editor label

A payload file gives each payload an internal name, and usually a label for the mission editor as
well. Some mods use short internal names, such as `AIM-9X*2, AIM-120C*2, FUEL*1`, with descriptive
labels, such as `- USN Adv. Extended Range CAP (...)`.

The flight creator and the flight's **Payload** tab now show the label, without the leading `- `
that the editor uses for sorting. If a payload has no label, they show its name. Loadouts are still
stored by name, so default loadouts and saved flights are not affected.

## Stations labelled like the editor

Aircraft data files can now give each pylon a station label (`pylon_names`). The payload editor shows
that label instead of the bare pylon number, and the number appears in a tooltip. For example, on the
Super Hornet the cheek station (pylon 4) reads `5 | 4`, and the EA-18G's wingtip pods read `3B` and `9B`.

## Weapons sorted into submenus

Clicking a station's weapon selector opens a menu instead of one long list:

* the weapons are sorted into category submenus: **AA missiles, AG missiles, guided bombs, bombs,
  rockets, fuel tanks, pods**;
* versions of the same weapon on different racks are grouped in a submenu of their own;
* tab characters that some mods add to weapon names are removed.

A weapon's category comes from Retribution's weapon data when it has one. Otherwise it is worked out
from the weapon's name.

## Stores that depend on each other

Some mods have rules about which stores go together. For example, the
[Armed Blackhawk](Armed-Blackhawk.md) requires that loading one store also loads others on other
stations. The loadout editor applies these rules the way the mission editor does:

* loading a store also loads the stores it needs on their stations;
* changing or emptying a station removes any stores that depended on what was there.
