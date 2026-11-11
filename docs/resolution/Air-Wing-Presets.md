# Air wing presets

An air wing preset sets up a whole side's air wing in one click: a US Navy carrier air wing from
1975, 1985, 1991, 2005 or 2020, a USMC amphibious ready group, a USAF expeditionary force, a
multinational NATO coalition, or a Soviet or Russian air force. Presets aren't tied to a theater.
Each squadron says which *kind* of base it belongs on (carrier, LHA, airfield or off-map), so the
same preset works on any campaign. The USAF, NATO, Russian and Soviet presets add a strategic bomber
detachment at an off-map base when the campaign defines one for the side (10 of the 70 campaigns do
for blue, `black_sea` also for red); elsewhere they add none. Each preset file notes the deployment
it is drawn from and where DCS lacks the real types.

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
