# Air wing presets

An air wing preset sets up a whole side's air wing in one click: a US Navy carrier air wing from
1975, 1985, 1991, 2005 or 2020, a USMC amphibious ready group, a USAF expeditionary force, a
multinational NATO coalition, or a Soviet or Russian air force. Presets aren't tied to a theater.
Each squadron says which *kind* of base it belongs on (carrier, LHA, airfield or off-map), so the
same preset works on any campaign. The USAF, NATO, Russian and Soviet presets add a strategic bomber
detachment at an off-map base when the campaign defines one for the side (10 of the 70 campaigns do
for blue, `black_sea` also for red); elsewhere they add none. Each preset file notes the deployment
it is drawn from and where DCS lacks the real types.

## Setting up the air wing of a new campaign

When a new campaign is generated, the **Air Wing Setup** window opens with a tab for each side.
Preset selection is the main way to build the air wing:

1. **Pick a preset for each base.** Every base the side owns is listed: carriers, LHAs and
   off-map bases first, then airfields ranked closest to farthest from the battle (see
   [Presets by base](#presets-by-base)). Each base has a drop-down of presets made for it,
   and the line under it shows the squadrons the base will have and any parking warnings.
   * The faction's own presets come first. They are made from the faction's aircraft, so every
     faction has them, including your own factions. A carrier is offered a full air wing, a
     fleet defense wing and a strike group. An LHA is offered an amphibious ready group,
     helicopter assault and STOVL strike. Airfields near the front are offered close air
     support, front-line fighters, strike and SEAD, and helicopter bases. Middle airfields are
     offered balanced, air superiority, deep strike and maritime strike wings. Rear airfields
     are offered support (AEW&C, tankers, airlift), heavy strike and rear air defense. An
     off-map base is offered strategic bombers. Each role is filled by the faction's best
     aircraft for it that can fly from that base. A second squadron of the same role takes
     another type when there is a close one.
   * A preset fits the base: its squadrons are trimmed to the parking left, in order, and one
     with no room is left out. The line under the base says what was trimmed.
   * The historical presets follow (marked *historical*), when the faction has their aircraft.
   * **Keep the campaign's squadrons** leaves the base as the campaign set it up.
     **No squadrons** empties it.
   * **Use the first preset at every base** fills the whole side in one click. **Keep the
     campaign's squadrons everywhere** undoes that.
   * Bases that can't take any of the faction's aircraft (an FOB with no helipads) aren't listed.
2. **Add more aircraft (optional).** **Add aircraft…** adds a squadron of any of the faction's
   aircraft. Pick the base first; only aircraft that can fly from it are listed. Set the number
   of aircraft in the row.
3. **Apply and continue.**

**Save config…** applies the choices so far and saves the side's air wing to
`Saved Games/DCS/Retribution/AirWing`. **Load config…** loads one back. **Advanced editor…**
applies the choices and opens the squadron-by-squadron editor (names, liveries, tasks and sizes).
The **Apply Preset...**, **Presets by Base...** and **Save as Preset...** buttons described below
are in that editor.

## Applying a preset

1. Start a new game. When the **Air Wing Configuration** window opens, choose the Blue or Red tab.
2. Click **Apply Preset...**. Presets closest to the campaign's start year are listed first.
3. Select a preset. The preview shows which base each squadron goes to, how many aircraft are
   deployed at the start, and any warnings.
4. Choose the options:
   * **Replace existing squadrons** (on by default) removes the campaign's own squadrons first.
   * **Add aircraft missing from the faction** lets the preset use stock DCS aircraft the faction
     doesn't normally have. Only this campaign's copy of the faction changes.
5. Click **Apply**. You can still edit, remove or add squadrons afterwards.

**Save as Preset...** saves the side's current air wing so you can reuse it on another theater.
Your presets are stored in `Saved Games/DCS/Retribution/AirWingPresets`.

## Presets by base

**Presets by Base...** fills one base at a time. The window lists the side's bases: carriers
first, then LHAs and off-map bases, then airfields ranked closest to farthest from the battle
(the nearest front line, or the nearest enemy base in a campaign without a ground war). Each
airfield is labelled with its rank, its third and its distance, for example
`#1 Front · Gudauta (31 km from the battle)`. The closest airfield is always Front and the
farthest always Rear.

Pick a base and you are offered only the preset groups made for it:

* a **carrier**: the carrier air wings;
* an **LHA**: the amphibious ready groups;
* a **Front** airfield: groups placed at front or any airfields;
* a **Middle** airfield: groups placed at any, front or rear airfields;
* a **Rear** airfield: groups placed at rear or any airfields (tankers, AWACS, bombers);
* an **off-map** base: the strategic bomber detachments.

The preview shows the squadrons the base gets and the ones it replaces. With **Replace the
squadrons at this base** (on by default) the base's squadrons are swapped for the preset's;
untick it to add them alongside. Squadrons at other bases are never touched.

**Add Squadron** also starts from the location. Pick the base first, in the same ranked and
labelled list; the aircraft list then shows only aircraft that can fly from it, and the
squadron list only squadrons that fly from that kind of base. A carrier offers carrier
aircraft and an LHA offers LHA aircraft. Each squadron's **Base** box uses the same ranked labels.

## Aircraft at the start

Squadrons and detachments start with their aircraft; nothing is bought at turn 0. Each squadron has
a **Deployed at start** box next to **Max size**: a squadron deploys all of its aircraft, a
detachment a few. With **Squadrons start full** (now ticked by default) a squadron without a number
starts full. The starting budget pays for ground forces; aircraft purchases start on turn 1.

## Warnings

When a squadron can't be placed, the preview says which squadron was skipped and why each aircraft
it could use was rejected:

| Reason | What to do |
|---|---|
| `modded aircraft not selected` | Turn the mod on in the wizard's mod settings. Mod aircraft are never added by "Add aircraft missing from the faction". |
| `aircraft not available to faction` | Tick **Add aircraft missing from the faction**, or choose a faction that has it. |
| `cannot operate from a carrier` / `an LHA` / `any owned airfield` | None of your bases of that kind can take the aircraft. |
| `unknown aircraft` | The preset names an aircraft Retribution doesn't know (usually a typo in a custom preset). |

You also get a warning when your side owns no base of a kind the preset needs (for example no
carrier), or when a base doesn't have enough parking for a squadron.

## Writing your own presets

The file format is described in [Air wing presets (modding)](../modding/airwing-presets.md).
