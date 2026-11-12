# Combat Search and Rescue (CSAR)

In Retribution, a pilot who is shot down is either killed or simply back at the base. In
Resolution, a downed pilot stays in the campaign. They wait on the map for a rescue, and what
happens to them depends on whether a rescue reaches them in time.

This feature started as [Retribution PR #929](https://github.com/dcs-retribution/dcs-retribution/pull/929).

## What happens when an aircraft goes down

1. **Is there a survivor?** If the pilot ejected in DCS, there always is. For losses that DCS didn't
   report an ejection for (AI kills, and every loss on a skipped or fast-forwarded turn), the
   chance of survival starts from **CSAR pilot survival chance** (default 40%). The
   [combat model](Combat-Model.md#aircrew) scales it by what brought the aircraft down: a
   missile at altitude leaves time to eject, and guns at low level often don't. The pilot comes
   down where the aircraft was lost, not at the package's target.
2. **Did they land close to a base?** If the pilot lands within **Control point radius resolving a
   downed pilot** (default 15 nm) of a base, there is no rescue to fly:
   * near a friendly base, they make their own way back and start recovering;
   * near an enemy base, they are captured and listed as missing in action.
3. **Otherwise they become a downed pilot.** A parachute icon (blue or red) appears on the map. Hover
   over it to see the pilot, their squadron and aircraft, and how many turns are left to rescue them.

## How long a pilot can wait

| Where the pilot is | Turns before they go missing | Setting |
|---|---|---|
| Friendly rear area | 3 | Turns a downed pilot survives |
| Hostile territory or near a front line | 2 | Turns a downed pilot survives near the front |

When the timer runs out:

* If the pilot is in enemy territory and within **Capture radius for unrescued pilots** (default
  30 nm) of an enemy base, they are **taken prisoner** and held at that base. If you capture the
  base, the prisoners go free and start recovering.
* Otherwise they are **missing in action** and do not come back.

The debriefing lists the pilots each side recovered and captured that turn, and which base is
holding each prisoner. A squadron's pilot list shows each pilot's status: **Downed**,
**Recovering**, **Missing in action**, and so on.

## Planning a rescue

* **By hand:** right-click a downed pilot's icon on the map. The new package dialog opens with a
  CSAR flight that targets that pilot.
* **Automatically:** the auto-planner plans CSAR packages for both sides, up to **Maximum CSAR
  flights planned per side each turn** (Campaign Doctrine, default 2). Pilots within
  **Collect downed pilots within (m)** of each other (default 1000 m) are picked up by a single
  flight.
* **One helicopter or two:** CSAR packages are flown by a pair unless **Enable single flight CSAR**
  is on. One helicopter costs fewer airframes and pilots, but there is no wingman to cover the
  pickup.
* **Start type:** CSAR flights have their own **Default start type** (default Warm), so a rescue can
  launch before the rest of the ATO.

## AI rescues

The AI helicopter flies to the pickup waypoint and recovers the survivor in one of two ways:

* **Hover extraction** (the default): the helicopter holds a low hover over the survivor, who is
  winched aboard by script.
* **Landing:** with **CSAR hover extraction** turned off, the helicopter lands and the survivor walks
  over and climbs in.

During an AI pickup the survivor pops smoke in their side's colour, so you can see what's happening.

## Flying a rescue yourself

Player rescues use [MOOSE Ops.CSAR](https://flightcontrol-master.github.io/MOOSE_DOCS_DEVELOP/Documentation/Ops.CSAR.html).
Any CSAR-capable helicopter on your side can pick up any downed pilot, including one the
auto-planner gave to an AI flight.

1. Fly to the pickup area and use the **CSAR** entries in the F10 radio menu. They list survivors,
   give you their beacon, and let you request smoke.
2. Pick up the survivor by landing next to them, or by hovering at or below **Player hover pickup
   height** (default 20 m) within **Player hover pickup distance** (default 10 m).
3. If **Require cabin door open** is on, the survivor won't board or get out until you open the door.
4. Fly the survivor back to a friendly airfield or MASH. The rescue counts once you deliver them,
   not when they climb aboard. A helicopter staged at a [Rescue King](#rescue-king) is the
   exception: its rescue counts at boarding, since the King takes the survivor home.

If **CSAR rescues AI-controlled downed pilots** is on (the default), pilots who were shot down while
flying for the AI are also available to player crews in the mission.

## Rescue King

A **Rescue King** is a C-130 circling outside enemy air defenses for one turn, with rescue
helicopters staged under it. It puts CSAR helicopters near where pilots will go down, instead of
at a base far behind the lines, as the HC-130 "King" and its Pave Hawks do in real combat
search and rescue. The callsign is the real one.

**Placing one.** Turn on **Dynamic FARPs** (Campaign Management > Dynamic FARPs; off by
default). **Rescue King** then appears in the top bar's FARPs box. Move the cursor over the map
and click where the King should orbit. The map says why a spot won't do:

* it is inside enemy air defense coverage;
* it is too close to another King;
* no C-130 or KC-130 squadron with **Rescue King** turned on has an aircraft and crew free;
* no CSAR-capable helicopter and crew is free.

The spot can be over land or sea, and the front line doesn't matter. Only blue can place a
King, and the FARPs menu is the only way to deploy one.

**Setting it up.** The King's menu opens as soon as you place it:

* **King aircraft:** every C-130 and KC-130 squadron, nearest first. Squadrons that can't go are
  greyed out with the reason. **Change** replans the orbit with your pick. A KC-130 or KC-130J
  King also refuels the helicopters; a C-130J-30 doesn't.
* **Time on station:** 30 to 360 minutes. **Set** replans the orbit.
* **Stationed detachments:** up to 2 CSAR-capable helicopters move to the King at once. Choose
  which ones.
* **Deploy King** confirms it. Closing the menu instead takes the King away again, with its
  orbit and its helicopters.

**During the turn.**

* The C-130 comes from your air wing. It flies the orbit as a package of its own, under
  Personnel recovery in the ATO, and it can be lost.
* The helicopters start in the air over the King. Rescues are planned by the commander or by
  you, like any CSAR package, and AI helicopters fly back to the King afterwards.
* Rescue flights must fly inside the King's time on station. Dragging a rescue on the timeline
  keeps it inside, and the package dialog warns when one doesn't fit.
* You can drag the King's package on the timeline. Moving the King, or changing its time on
  station or aircraft, offers to move the rescues that no longer fit.
* At the end of the turn the King is dismantled, and the helicopters rejoin their squadron.

## After the rescue

Rescues show in the mission results window and in the debriefing, where a CSAR package reads
"pilot rescued" or "pilot not picked up". A rescue flown by an AI flight in the combat model
counts when that flight survives the turn.

A rescued pilot recovers before flying again. AI pilots take 2 turns (**Turns a rescued AI pilot
recovers**) and player pilots take 1 turn (**Turns a rescued player pilot recovers**).

## Settings reference

| Setting | Page / section | Default |
|---|---|---|
| Enable CSAR for the player coalition | Campaign Management / Pilots and Squadrons | On |
| Enable CSAR for the enemy coalition | Campaign Management / Pilots and Squadrons | On |
| CSAR pilot survival chance (%) | Campaign Management / Pilots and Squadrons | 40 |
| Control point radius resolving a downed pilot (nm) | Campaign Management / Pilots and Squadrons | 15 |
| Capture radius for unrescued pilots (nm) | Campaign Management / Pilots and Squadrons | 30 |
| Collect downed pilots within (m) on one flight | Campaign Management / Pilots and Squadrons | 1000 |
| Turns a downed pilot survives | Campaign Management / Pilots and Squadrons | 3 |
| Turns a downed pilot survives near the front | Campaign Management / Pilots and Squadrons | 2 |
| Turns a rescued AI pilot recovers | Campaign Management / Pilots and Squadrons | 2 |
| Turns a rescued player pilot recovers | Campaign Management / Pilots and Squadrons | 1 |
| Enable single flight CSAR | Campaign Management / Flight Planner Automation | Off |
| Maximum CSAR flights planned per side each turn | Campaign Doctrine / General | 2 |
| Default start type for CSAR flights | Mission Generator / Gameplay | Warm |
| CSAR hover extraction | Mission Generator / Gameplay | On |
| CSAR rescues AI-controlled downed pilots | Mission Generator / Gameplay | On |
| Player hover pickup height (m) | Mission Generator / Gameplay | 20 |
| Player hover pickup distance (m) | Mission Generator / Gameplay | 10 |
| Require cabin door open | Mission Generator / Gameplay | Off |

## Tips

* Set **Control point radius resolving a downed pilot** to 0 if you want every survivor to need a
  rescue flight.
* Set **Capture radius for unrescued pilots** to 0 if you never want unrescued pilots taken prisoner.
* Pilots near the front have less time. Plan those rescues first.
