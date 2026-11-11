# Dynamic FARPs

In Retribution, helicopters can only use the FARPs a campaign comes with. In Resolution, you can
build your own Forward Arming and Refuelling Points close to the front. A transport flies the
equipment in, and then you station helicopter detachments there to fly any task they can perform.

## Turning it on

Open **Settings → Campaign Management → Dynamic FARPs** and tick **Enable player-established
FARPs**. It is off by default. Once it is on, a **FARPs** box with **Wet Wing** and **Fat Cow**
buttons appears in the top bar.

## The two FARP types

The two types follow the same placement rules. They differ in cost, capacity, how the equipment
arrives, and how the site looks.

| | Wet Wing | Fat Cow |
|---|---|---|
| Set up by | A transport plane (such as a C-130) airdrops the equipment. If no transport plane is available, a transport helicopter can fly it in. | A transport helicopter (such as a CH-47) lands at the site |
| Helicopter capacity | 4 (adjustable) | 2 |
| Deployment cost | $250M | $150M |
| Upkeep per turn | $25M | $15M |

All of these except the Fat Cow's capacity can be changed in the settings.

## Placing a FARP

1. Click **Wet Wing** or **Fat Cow** in the top bar.
2. Move the cursor over the map. The tooltip shows the cost and checks the spot under the cursor. If
   the FARP can't go there, it lists every reason, for example:
   * not in friendly territory, or on the wrong side of the front line;
   * too close to the front (default minimum 3 nm) or too far from it (default maximum 20 nm);
   * terrain too uneven, too close to a built-up area, or on water;
   * within 3 nm of another base or 1 nm of a ground object;
   * FARP limit reached (default 4 in total), not enough money, or no transport available.
3. Click to order the FARP, or right-click or press Esc to cancel.

The deployment cost is taken straight away. The FARP shows up on the map as **awaiting equipment**,
and a setup flight is added to the ATO. FARPs are named from a list of callsigns, for example
*FARP Anvil* or *FARP Badger*.

## Setting it up

The setup flight is planned automatically from the nearest suitable squadron. The FARP is built once
that flight delivers its equipment in the mission: the helicopter lands at the site, or the plane
drops over it. Setup flights are also resolved when you fast-forward or skip a turn.

The **Enable Instant FARP Cheat** option (Settings → Cheat Menu) builds FARPs the moment you order them, with no setup
flight.

If you cancel a FARP before it is set up, you get the deployment cost back.

## Stationing helicopters

Open the FARP's base menu (click it on the map) and go to the **FARP** tab.

* **Assign a detachment:** pick a helicopter squadron, choose how many aircraft to send, and click
  **Assign**. The list shows how far away each squadron is, and why a squadron can't be chosen.
  Any helicopter can be stationed at the FARP and fly any task it can perform.
* The detachment ferries to the FARP during the next mission and arrives at the end of the turn. The
  tab and the Air Wing list show it as *en route* until then.
* **Recall** sends a detachment's aircraft and pilots back to their parent squadron. If the
  detachment is still en route, recalling it cancels the move.
* Detachments can't buy aircraft or recruit pilots. To reinforce one, recall it and send a new
  detachment.

The AI plans missions for helicopters at your FARPs the same way it does for any other base. The AI
never builds FARPs of its own.

## Running costs and losing a FARP

* **Upkeep** is charged every turn and is shown in the Finances window. If you can't pay, your newest
  FARPs are abandoned until your budget is no longer negative.
* **Threat warning:** when the front line comes within the minimum building distance of a FARP, you
  get a warning.
* **Overrun:** if the front line moves past a FARP, or the base that owns its territory is captured,
  the FARP is lost. You get no refund. Helicopters stationed there escape to their home base.
* **Destroyed in the mission:** if all of a FARP's fuel is destroyed, the FARP is lost and so are
  the helicopters parked there.
* **Dismantle FARP** (in the FARP tab) removes the FARP. Its helicopters return to their parent
  squadrons.

You get a popup at the end of the turn when a FARP is lost.

## Settings reference

Unless stated otherwise, these settings are under Campaign Management → Dynamic FARPs.

| Setting | Default |
|---|---|
| Enable player-established FARPs | Off |
| Wet Wing FARP deployment cost | 250 |
| Wet Wing FARP upkeep per turn | 25 |
| Wet Wing FARP helicopter capacity | 4 |
| Fat Cow FARP deployment cost | 150 |
| Fat Cow FARP upkeep per turn | 15 |
| Maximum number of FARPs | 4 |
| FARP minimum distance from front (nm) | 3 |
| FARP maximum distance from front (nm) | 20 (0 means no limit) |
| Enable Instant FARP Cheat (Cheat Menu page) | Off |

## Supported maps

FARP sites are checked against a terrain grid that ships for each theater: Afghanistan, Caucasus,
Falklands, Germany (Cold War), Iraq, Kola, Marianas, Nevada, Normandy, Persian Gulf, Sinai, Syria
and The Channel. Developers can regenerate the grids with
`resources/tools/generate_farp_terrain.py`.
