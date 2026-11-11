# Air wing presets

An air wing preset is a ready-made air wing, such as a US Navy carrier air wing from
1985, a USAF expeditionary force, or a multinational NATO task force. You apply it in
the new game **Air Wing Configuration** window. The squadrons are placed on the bases
your side owns, and their aircraft are bought from the starting budget.

Presets aren't tied to a theater. Each one says what *kind* of base its squadrons
belong on (carrier, LHA or airfield), not which base, so the same preset works on
any campaign.

## Using a preset

1. Start a new game. When the Air Wing Configuration window opens, pick the Blue or
   Red tab.
2. Click **Apply Preset...**. The list is sorted so that presets closest to the
   campaign's start year come first.
3. Select a preset. The preview shows:
   - which base each squadron goes to;
   - how many aircraft will be bought, and what they cost against your starting
     budget;
   - warnings, for example when your side owns no carrier or the faction doesn't
     have an aircraft.
4. Options:
   - **Replace existing squadrons** (on by default): remove the campaign's squadrons
     first. When it's off, the preset's squadrons are added to the ones already
     there.
   - **Add aircraft missing from the faction**: let the preset use stock DCS
     aircraft the faction doesn't normally have. Only this campaign's copy of the
     faction changes. Mod aircraft are never added this way. Turn the mod on in the
     wizard's mod settings instead.
5. Click **Apply**. You can still edit, remove or add squadrons afterwards.

Each squadron has a **Buy at start** box next to **Max size**. It holds the number
of aircraft bought from the starting budget when the campaign begins. If the money
runs out, aircraft are bought one at a time in turn across squadrons, so every
squadron ends up a little short instead of the last ones getting nothing. Any money
left over is spent by the usual automatic procurement.

If **Squadrons start full** is checked in the wizard, squadrons are filled for free
as before, and the buy counts are ignored.

**Save as Preset...** saves the side's current air wing as a preset file, so you can
reuse it on other theaters.

## Where presets live

- Built-in presets: `resources/airwing_presets/*.yaml`
- Your own presets: `<Saved Games>/DCS/Retribution/AirWingPresets/*.yaml`

## File format

```yaml
name: US Navy Carrier Air Wing (1985)   # shown in the preset list
description: Mid-80s Nimitz-class air wing.
era: 1985                               # optional; used for sorting
side: blue                              # optional: blue, red, or leave out
groups:
  - base: carrier                       # carrier | lha | airfield
    count: 1                            # see below
    squadrons:
      - aircraft: ["F-14A Tomcat (Block 135-GR Late)", "F-14A Tomcat (Block 135-GR Early)"]
        country: USA
        primary: BARCAP
        secondary: air-to-air
        size: 12
        buy: 12
  - base: airfield
    placement: front                    # front | rear | any
    squadrons:
      - {aircraft: ["A-10A Thunderbolt II"], primary: CAS, size: 12}
```

### Groups

A preset is a list of groups. All squadrons in a group go on the same kind of base.

| Key | Meaning |
|---|---|
| `base` | `carrier`, `lha` or `airfield` (default). Airfields include FOBs and FARPs, but not off-map spawns. |
| `count` | Carriers and LHAs: how many of your carriers/LHAs each get the whole group (default 1). Airfields: how many airfields the group may be spread over (default: all). |
| `placement` | Airfields only. `front` fills the airfields closest to the enemy first, `rear` fills the farthest first, and `any` (default) spreads squadrons over the airfields. |

A squadron is only placed on a base where it fits. If no base of the right kind has
room, it goes to the one with the most free parking, and a warning is shown.

### Squadrons

Squadron entries use the same keys as the `squadrons:` section of a campaign file,
plus three of their own:

| Key | Meaning |
|---|---|
| `aircraft` | Preference list of aircraft names (or squadron names). The first one the faction has is used. |
| `primary` | Primary task, e.g. `BARCAP`, `Strike`, `CAS`, `SEAD`, `AEW&C`, `Refueling`, `Transport`, `Air Assault`. |
| `secondary` | Other tasks the squadron is auto-planned for: a list of tasks, or `any`, `air-to-air` or `air-to-ground`. |
| `size` | Maximum squadron size (default 12). |
| `name`, `nickname`, `female_pilot_percentage` | Optional overrides, as in campaign files. |
| `country` | DCS country name (e.g. `UK`, `France`, `Germany`, `Turkey`). Only squadron definitions from that country are used. If there are none, a squadron is generated with that country. The country decides the livery, pilot names and in-mission radio voice. Leave it out to use the faction's country. |
| `squadron` | Name of a squadron definition (from `resources/squadrons`) to use if it's available. |
| `buy` | Aircraft to buy at the start (default: `size`). |

Aircraft names are the names Retribution shows in the game, as used in faction files
(e.g. `F/A-18C Hornet (Lot 20)`). Put older or stock aircraft later in the `aircraft`
list as fallbacks for mod aircraft, e.g.
`["F/A-18E Super Hornet", "F/A-18C Hornet (Lot 20)"]`.
