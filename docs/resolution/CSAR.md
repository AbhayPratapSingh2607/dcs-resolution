# Combat Search and Rescue (CSAR)

In Retribution, a pilot who is shot down is either killed or simply back at the base. In
Resolution, a downed pilot stays in the campaign. They wait on the map for a rescue, and what
happens to them depends on whether a rescue reaches them in time.

This feature started as [Retribution PR #929](https://github.com/dcs-retribution/dcs-retribution/pull/929).

## What happens when an aircraft goes down

1. **Is there a survivor?** If the pilot ejected in DCS, there always is. For losses that DCS didn't
   report an ejection for (AI kills, and every loss on a skipped or fast-forwarded turn), the
   chance of survival is set by **CSAR pilot survival chance** (default 40%).
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
   not when they climb aboard.

If **CSAR rescues AI-controlled downed pilots** is on (the default), pilots who were shot down while
flying for the AI are also available to player crews in the mission.

## After the rescue

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
